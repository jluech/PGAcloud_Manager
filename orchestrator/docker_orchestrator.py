import logging
import warnings

import docker

from orchestrator.orchestrator import Orchestrator


class DockerOrchestrator(Orchestrator):
    def __init__(self):
        self.docker_master_client = self.__create_docker_client(
            host_ip="192.168.2.59",
            host_port=2376
            # default docker port; Note above https://docs.docker.com/engine/security/https/#secure-by-default
        )

    def setup_pga(self, components, services, population, properties):
        self.__create_network()
        # self.__connect_to_network(self.pga_network.id)
        self.__deploy_stack(components, services)
        self.__distribute_properties(properties)
        self.__initialize_population(population)
        # self.__disconnect_from_network(self.pga_network.id)

    def scale_component(self, network_id, service_name, scaling):
        if service_name.__contains__(Orchestrator.name_separator):
            effective_name = service_name.split(Orchestrator.name_separator)[1]
        else:
            effective_name = service_name

        if effective_name in ("runner", "manager"):
            warnings.warn("Scaling aborted: Scaling of runner or manager services not permitted!")
        else:
            # self.__connect_to_network(network_id)
            service = self.docker_master_client.services.list(filters={"name": service_name})
            service.scale(replicas=scaling)
            # self.__disconnect_from_network(network_id)

    def __create_network(self):
        # Creates a new docker network.
        self.pga_id = Orchestrator.new_id()
        self.pga_network = self.docker_master_client.networks.create(
            name="overlay-pga-{id_}".format(id_=self.pga_id),
            driver="overlay",
            check_duplicate=True,
            attachable=True,
            scope="swarm",
            labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
        )

    def __deploy_stack(self, components, services):
        # Creates a service for each component defined in the configuration.
        for support_key in [*services]:
            support = services.get(support_key)
            new_support = self.__create_docker_service(support, self.pga_network)

        for service_key in [*components]:
            service = components.get(service_key)
            new_service = self.__create_docker_service(service, self.pga_network)
            self.scale_component(network_id=self.pga_network.id, service_name=new_service.name,
                                 scaling=service.get("scaling"))

    def __initialize_population(self, population):
        # if population.get("use_initial_population"):
        #     file_path = population.get("population_file_path")
        #     filename = utils.get_filename_from_path(file_path)
        #     files = utils.get_uploaded_files_dict()
        #     population_file = files.get(filename)
        logging.debug("INITIALIZE POPULATION")  # TODO
        logging.debug(population)

    def __distribute_properties(self, properties):
        logging.debug("DISTRIBUTE PROPERTIES")  # TODO
        logging.debug(properties)

    def __connect_to_network(self, network_id):
        # Connects the manager service to the network to communicate with the PGA.
        logging.debug("CONNECTING TO NETWORK {id_}".format(id_=network_id))  # TODO
        # manager_container = self.docker_local_client.containers.list(
        #     filters={"label": "com.docker.swarm.service.name=manager"})[0]
        # nets = self.docker_master_client.networks.list(filters={"label": "PGAcloud=PGA-{id_}".format(id_=network_id)})
        # nets[0].connect(manager_container)
        # network = self.docker_master_client.networks.get(network_id, verbose=True, scope="swarm")
        # network.connect(manager_container)

    def __disconnect_from_network(self, network_id):
        # Disconnects the manager service from the PGA network.
        logging.debug("DISCONNECTING FROM NETWORK {id_}".format(id_=network_id))  # TODO
        # manager_container = self.docker_local_client.containers.list(
        #     filters={"label": "com.docker.swarm.service.name=manager"})[0]
        # network = self.docker_master_client.networks.get(network_id, verbose=True, scope="swarm")
        # network.disconnect(manager_container)

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
            base_url="tcp://{ip_}:{port_}".format(
                ip_=host_ip,
                port_=host_port
            ),
            tls=tls_config,
        )
        return docker_client

    def __create_docker_service(self, service_dict, network):
        return self.docker_master_client.services.create(
                image=service_dict.get("image"),
                name="pga-{id_}{sep_}{name_}".format(
                    id_=self.pga_id,
                    sep_=Orchestrator.name_separator,
                    name_=service_dict.get("name")
                ),
                networks=[network.name],
                labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
            )
