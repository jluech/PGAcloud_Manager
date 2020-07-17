import logging
import time
import warnings

import docker
import requests

from orchestrator.orchestrator import Orchestrator

WAIT_FOR_CONFIRMATION_DURATION = 45.0
WAIT_FOR_CONFIRMATION_EXCEEDING = 15.0
WAIT_FOR_CONFIRMATION_TROUBLED = 30.0
WAIT_FOR_CONFIRMATION_SLEEP = 3  # seconds


class DockerOrchestrator(Orchestrator):
    def __init__(self, master_host):
        self.pga_id = Orchestrator.new_id()
        self.host = master_host
        self.docker_master_client = self.__create_docker_client(
            host_ip=master_host,
            host_port=2376
            # default docker port; Note above https://docs.docker.com/engine/security/https/#secure-by-default
        )

    def setup_pga(self, services, setups, operators, population, properties):
        self.__create_network()
        self.__deploy_stack(services=services, setups=setups, operators=operators)

        self._trigger_connection(self.pga_id)
        # self.__distribute_properties(properties)
        # self.__initialize_population(population)

    def scale_component(self, network_id, service_name, scaling):
        # Scales the given service in the given network to the given scaling amount.
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

# Commands to control the orchestrator
    def __deploy_stack(self, services, setups, operators):
        # Creates a service for each component defined in the configuration.
        for support_key in [*services]:
            support = services.get(support_key)
            self.__create_docker_service(support, self.pga_network)

        for setup_key in [*setups]:
            setup = setups.get(setup_key)
            if setup.get("name") == "runner":
                new_service = self.docker_master_client.services.create(
                    image=setup.get("image"),
                    name="runner{sep_}{id_}".format(
                        sep_=Orchestrator.name_separator,
                        id_=self.pga_id
                    ),
                    hostname=setup.get("name"),
                    networks=[self.pga_network.name, "bridge-pga"],
                    labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
                    endpoint_spec={
                        "Mode": "dnsrr"  # TODO: check if required
                    },
                )
            else:
                new_service = self.__create_docker_service(setup, self.pga_network)
            self.scale_component(network_id=self.pga_network.id, service_name=new_service.name,
                                 scaling=setup.get("scaling"))

        for operator_key in [*operators]:
            operator = operators.get(operator_key)
            new_service = self.__create_docker_service(operator, self.pga_network)
            self.scale_component(network_id=self.pga_network.id, service_name=new_service.name,
                                 scaling=operator.get("scaling"))

        # Waits for WAIT_FOR_CONFIRMATION_DURATION seconds or until runner is up and its API ready.
        runner_running = False
        runner_status = "NOK"
        exceeding = False
        troubled = False
        duration = 0.0
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
                logging.debug("This is taking longer than usual...")
                exceeding = True  # only print this once

            if duration >= WAIT_FOR_CONFIRMATION_TROUBLED and not troubled:
                logging.debug("Oh come on! You can do it...")
                troubled = True  # only print this once

            time.sleep(WAIT_FOR_CONFIRMATION_SLEEP)  # avoid network overhead
            duration = time.perf_counter() - start

        if duration >= WAIT_FOR_CONFIRMATION_DURATION:
            logging.debug("Exceeded waiting time of {time_} seconds. It may have encountered an error. "
                          "Please verify or try again shortly.".format(time_=WAIT_FOR_CONFIRMATION_DURATION))
        else:
            logging.debug("Successfully created runner service.")

    def _trigger_connection(self, pga_id):
        # TODO: remove connector image and repo since no longer needed
        requests.get(
            url="http://runner{sep_}{id_}:5000/{id_}".format(
                sep_=Orchestrator.name_separator,
                id_=pga_id
            ),
            verify=False
        )

    def __initialize_population(self, population):
        # if population.get("use_initial_population"):
        #     file_path = population.get("population_file_path")
        #     filename = utils.get_filename_from_path(file_path)
        #     files = utils.get_uploaded_files_dict()
        #     population_file = files.get(filename)
        logging.debug("INITIALIZE POPULATION")  # TODO
        logging.debug(population)
        # TODO 104: init pop from Runner container (method initialize() )

    def __distribute_properties(self, properties):
        logging.debug("DISTRIBUTE PROPERTIES")  # TODO
        logging.debug(properties)
        # TODO 104: store properties in DB from Runner container
        # separate method store_properties() in class RedisHandler extending abstract DatabaseHandler
        # class RabbitMessageQueue extending abstract MessageHandler

# Commands to for docker stuff
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
            name="overlay-pga-{id_}".format(id_=self.pga_id),
            driver="overlay",
            check_duplicate=True,
            attachable=True,
            scope="swarm",
            labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
        )

    def __create_docker_service(self, service_dict, network):
        return self.docker_master_client.services.create(
            image=service_dict.get("image"),
            name="{name_}{sep_}{id_}".format(  # TODO: check if numbering is required across networks
                name_=service_dict.get("name"),
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            hostname=service_dict.get("name"),
            networks=[network.name],
            labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
            endpoint_spec={
                "Mode": "dnsrr"  # TODO: check if required
            },
        )
