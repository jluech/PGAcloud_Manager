import json
import logging
import os
import traceback
import warnings

import docker

from orchestrator.orchestrator import Orchestrator
from utilities import utils

WAIT_FOR_CONFIRMATION_DURATION = 45.0
WAIT_FOR_CONFIRMATION_EXCEEDING = 15.0
WAIT_FOR_CONFIRMATION_TROUBLED = 30.0
WAIT_FOR_CONFIRMATION_SLEEP = 3  # seconds


class DockerOrchestrator(Orchestrator):
    def __init__(self, master_host, pga_id):
        super().__init__(pga_id)

        self.host = master_host
        self.docker_master_client = self.__create_docker_client(
            host_ip=master_host,
            host_port=2376
            # default docker port; Note above https://docs.docker.com/engine/security/https/#secure-by-default
        )

# Common orchestrator functionality.
    def setup_pga(self, model_dict, services, setups, operators, population, properties, file_names):
        self.__create_network()
        configs = self.__create_configs(file_names)
        deploy_init = (not population.get("use_initial_population") or properties.get("USE_INIT"))
        self.__deploy_stack(services=services, setups=setups, operators=operators,
                            configs=configs, model_dict=model_dict, deploy_initializer=deploy_init)

    def scale_component(self, service_name, scaling):
        if service_name.__contains__(Orchestrator.name_separator):
            effective_name = service_name.split(Orchestrator.name_separator)[0]
        else:
            effective_name = service_name

        if effective_name in ("runner", "manager"):
            warnings.warn("Scaling aborted: Scaling of runner or manager services not permitted!")
        else:
            found_services = self.docker_master_client.services.list(filters={"name": service_name})
            if not found_services.__len__() > 0:
                raise Exception("No service {name_} found for scaling!".format(name_=service_name))
            service = found_services[0]
            service.scale(replicas=scaling)

# Commands to control the orchestrator.
    def __deploy_stack(self, services, setups, operators, configs, model_dict, deploy_initializer):
        # Creates a service for each component defined in the configuration.
        # Deploy the support services (e.g., MSG and DB).
        supports = {}
        for support_key in [*services]:
            support = services.get(support_key)
            new_service = self.__create_docker_service(service_dict=support, network=self.pga_network)
            self.__update_service_with_configs(configs=configs, service_name=new_service.name)
            supports[support.get("name")] = new_service
        # Ensure services are starting up in the background while waiting for them.
        for support_key in [*supports]:
            support = supports.get(support_key)  # actual docker service
            self.__wait_for_service(service_name=support.name)

        # Deploy the setup services (e.g., RUN or INIT).
        setup_services = {}
        for setup_key in [*setups]:
            setup = setups.get(setup_key)
            setup_name = setup.get("name")
            if setup_name == "runner":
                # Creates the runner service with bridge network.
                new_service = self.docker_master_client.services.create(
                    image=setup.get("image"),
                    name="runner{sep_}{id_}".format(
                        sep_=Orchestrator.name_separator,
                        id_=self.pga_id
                    ),
                    hostname=setup.get("name"),
                    networks=[self.pga_network.name, "pga-management"],
                    labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
                    endpoint_spec={
                        "Mode": "dnsrr"
                    },
                )
            elif setup_name == "initializer":
                if deploy_initializer:
                    new_service = self.__create_docker_service(service_dict=setup, network=self.pga_network)
                else:
                    continue  # no need to deploy initializer if initial population is provided.
            else:
                new_service = self.__create_docker_service(service_dict=setup, network=self.pga_network)

            self.scale_component(service_name=new_service.name, scaling=setup.get("scaling"))
            container_config_name = self.__create_container_config(new_service.name, setup_key, model_dict)
            self.__update_service_with_configs(configs=configs, service_name=new_service.name,
                                               container_config=container_config_name)
            setup_services[setup_name] = new_service

        # Deploy the genetic operator services.
        for operator_key in [*operators]:
            operator = operators.get(operator_key)
            new_service = self.__create_docker_service(service_dict=operator, network=self.pga_network)
            self.scale_component(service_name=new_service.name, scaling=operator.get("scaling"))
            container_config_name = self.__create_container_config(new_service.name, operator_key, model_dict)
            self.__update_service_with_configs(configs=configs, service_name=new_service.name,
                                               container_config=container_config_name)

        # Wait for setups before initiating properties or population.
        if deploy_initializer:
            initializer = setup_services.get("initializer")
            self.__wait_for_service(service_name=initializer.name)
        for setup_key in [*setup_services]:
            if setup_key == "initializer":
                continue  # no need to wait for initializer if not deployed, or already waited for
            setup = setup_services.get(setup_key)  # actual docker service
            self.__wait_for_service(service_name=setup.name)

# Commands for docker stuff.
    def __create_docker_client(self, host_ip, host_port):
        tls_config = docker.tls.TLSConfig(
            ca_cert="/run/secrets/SSL_CA_PEM",
            client_cert=(
                "/run/secrets/SSL_CERT_PEM",
                "/run/secrets/SSL_KEY_PEM"
            ),
            verify=True
        )
        docker_client = docker.DockerClient(
            base_url="tcp://{host_}:{port_}".format(
                host_=host_ip,
                port_=host_port
            ),
            tls=tls_config,
        )
        return docker_client

    def __create_network(self):
        # Creates a new docker network.
        self.pga_network = self.docker_master_client.networks.create(
            name="pga-overlay-{id_}".format(id_=self.pga_id),
            driver="overlay",
            check_duplicate=True,
            attachable=True,
            scope="swarm",
            labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
        )

    def __create_configs(self, file_names):
        # Creates docker configs for file sharing.
        configs = []
        stored_files_path = utils.get_uploaded_files_path(self.pga_id)

        for file_name in file_names:
            try:
                file_path = os.path.join(stored_files_path, file_name)

                file = open(file_path, mode="rb")
                file_content = file.read()
                file.close()

                config_name = "{id_}{sep_}{name_}".format(
                        id_=self.pga_id,
                        sep_=Orchestrator.name_separator,
                        name_=file_name
                    )
                self.docker_master_client.configs.create(
                    name=config_name,
                    data=file_content,
                    labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)}
                )
                configs.append(config_name)
            except Exception as e:
                traceback.print_exc()
                logging.error(traceback.format_exc())

        return configs

    def __create_container_config(self, service_name, service_key, model_dict):
        effective_name = service_name.split(Orchestrator.name_separator)[0]
        config_name = "{id_}{sep_}{name_}-config.yml".format(
            id_=self.pga_id,
            sep_=Orchestrator.name_separator,
            name_=effective_name
        )
        config_content = model_dict[service_key]
        config_content["pga_id"] = self.pga_id
        self.docker_master_client.configs.create(
            name=config_name,
            data=json.dumps(config_content),
            labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)}
        )
        return config_name

    def __create_docker_service(self, service_dict, network):
        return self.docker_master_client.services.create(
            image=service_dict.get("image"),
            name="{name_}{sep_}{id_}".format(
                name_=service_dict.get("name"),
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            hostname=service_dict.get("name"),
            networks=[network.name],
            labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
            endpoint_spec={
                "Mode": "dnsrr"
            },
        )

    def __update_service_with_configs(self, configs, service_name, container_config=None):
        # Updates the given service with the new configs.
        logging.info("Updating {name_} with docker configs.".format(name_=service_name))
        config_param = self.__prepare_array_as_script_param(configs, container_config)
        script_path = os.path.join(os.getcwd(), "utilities/docker_service_update_configs.sh")
        script_args = "--service {service_} --host {host_} --configs {confs_}"
        utils.execute_command(
            command=script_path + " " + script_args.format(
                service_=service_name,
                host_=self.host,
                confs_=config_param,
            ),
            working_directory=os.curdir,
            environment_variables=None,
            executor="StackDeploy",
        )

    def __wait_for_service(self, service_name):
        # Waits until the given service has at least one instance which is running and ready.
        logging.info("Waiting for {name_} service.".format(name_=service_name))
        script_path = os.path.join(os.getcwd(), "utilities/docker_service_wait_until_running.sh")
        script_args = "--service {service_} --host {host_}"
        utils.execute_command(
            command=script_path + " " + script_args.format(
                service_=service_name,
                host_=self.host,
            ),
            working_directory=os.curdir,
            environment_variables=None,
            executor="StackDeploy",
        )

# Auxiliary commands.
    def __prepare_array_as_script_param(self, general_configs, container_config):
        param = ""
        for conf in general_configs:
            param += "{} ".format(conf)
        if container_config is None:
            param += "--"
        else:
            param += container_config
            param += " --"
        return param
