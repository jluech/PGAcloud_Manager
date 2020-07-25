import logging
import os
import time
import traceback
import warnings

import docker
import requests

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
    def setup_pga(self, services, setups, operators, population, properties, file_names):
        self.__create_network()
        configs = self.__create_configs(file_names)
        deploy_init = (not population.get("use_initial_population") or properties.get("USE_INIT"))
        self.__deploy_stack(services=services, setups=setups, operators=operators,
                            configs=configs, deploy_initializer=deploy_init)

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
    def __deploy_stack(self, services, setups, operators, configs, deploy_initializer):
        # Creates a service for each component defined in the configuration.
        # Deploy the support services (e.g., MSG and DB).
        supports = {}
        for support_key in [*services]:
            support = services.get(support_key)
            new_service = self.__create_docker_service(service_dict=support, network=self.pga_network)
            self.__update_service_with_configs(configs, new_service.name)
            supports[support.get("name")] = new_service
        # Ensure services are starting up in the background while waiting for them.
        for support_key in [*supports]:
            support = supports.get(support_key)  # actual docker service
            self.__wait_for_service(service_name=support.name)

        # Deploy the setup services (e.g., RUN or INIT).
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
                    continue  # no need to deploy initializer if initial population is provided
            else:
                new_service = self.__create_docker_service(service_dict=setup, network=self.pga_network)

            self.scale_component(service_name=new_service.name, scaling=setup.get("scaling"))
            self.__update_service_with_configs(configs, new_service.name)

        # Deploy the genetic operator services.
        for operator_key in [*operators]:
            operator = operators.get(operator_key)
            new_service = self.__create_docker_service(service_dict=operator, network=self.pga_network)
            self.scale_component(service_name=new_service.name, scaling=operator.get("scaling"))
            self.__update_service_with_configs(configs, new_service.name)

        # Waits for WAIT_FOR_CONFIRMATION_DURATION seconds or until runner is up and its API ready.
        runner_running = False
        runner_status = "NOK"
        exceeding = False
        troubled = False
        duration = 0.0
        logging.info("Waiting for runner service.")
        start = time.perf_counter()
        while not runner_running and duration < WAIT_FOR_CONFIRMATION_DURATION:
            try:
                response = requests.get(
                    url="http://runner{sep_}{id_}:5000/status".format(
                        sep_=Orchestrator.name_separator,
                        id_=self.pga_id
                    ),
                    verify=False
                )
                runner_status = response.content.decode("utf-8")
            except:
                pass
            finally:
                runner_running = runner_status == "OK"

            if duration >= WAIT_FOR_CONFIRMATION_EXCEEDING and not exceeding:
                logging.info("This is taking longer than usual...")
                exceeding = True  # only print this once

            if duration >= WAIT_FOR_CONFIRMATION_TROUBLED and not troubled:
                logging.info("Oh come on! You can do it...")
                troubled = True  # only print this once

            time.sleep(WAIT_FOR_CONFIRMATION_SLEEP)  # avoid network overhead
            duration = time.perf_counter() - start

        if duration >= WAIT_FOR_CONFIRMATION_DURATION:
            logging.info("Exceeded waiting time of {time_} seconds. It may have encountered an error. "
                         "Please verify or try again shortly.".format(time_=WAIT_FOR_CONFIRMATION_DURATION))
        else:
            logging.info("Runner service ready.")

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

    def __update_service_with_configs(self, configs, service_name):
        # Updates the given service with the new configs.
        logging.info("Updating {name_} with docker configs.".format(name_=service_name))
        config_param = self.__prepare_array_as_script_param(configs)
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
    def __prepare_array_as_script_param(self, array):
        param = ""
        for elem in array:
            param += "{} ".format(elem)
        param += "--"
        return param
