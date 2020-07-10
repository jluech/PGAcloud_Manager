import logging
import os
import warnings

import docker
import requests

from orchestrator.orchestrator import Orchestrator
from utililities import utils


class DockerOrchestrator(Orchestrator):
    def __init__(self, master_host):
        self.host = master_host
        self.docker_master_client = self.__create_docker_client(
            host_ip=master_host,
            host_port=2376
            # default docker port; Note above https://docs.docker.com/engine/security/https/#secure-by-default
        )

    def setup_pga(self, services, setups, operators, population, properties):
        self.__create_network()
        # trigger connector build
        connector = self.__connect_to_network(self.pga_network.id)
        self.__deploy_stack(services=services, setups=setups, operators=operators)
        # call connector, add use_init bool as param
        self._trigger_connector(connector)
        # self.__distribute_properties(properties)
        # self.__initialize_population(population)

    def scale_component(self, network_id, service_name, scaling):
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

        for service_key in [*setups]:
            service = setups.get(service_key)
            new_service = self.__create_docker_service(service, self.pga_network)
            self.scale_component(network_id=self.pga_network.id, service_name=new_service.name,
                                 scaling=service.get("scaling"))

        for service_key in [*operators]:
            service = operators.get(service_key)
            new_service = self.__create_docker_service(service, self.pga_network)
            self.scale_component(network_id=self.pga_network.id, service_name=new_service.name,
                                 scaling=service.get("scaling"))

    def _trigger_connector(self, connector):
        pga_id = connector.name.split(Orchestrator.name_separator)[0]
        requests.get(
            url="https://{host_}:5001/{pga_}/ls".format(
                host_=connector.name,
                pga_=pga_id
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
        # check docker tutorial votingapp for container api requests (runner needs api, distinguish different runners)

    def __distribute_properties(self, properties):
        logging.debug("DISTRIBUTE PROPERTIES")  # TODO
        logging.debug(properties)
        # TODO 104: store properties in DB from Runner container
        # separate method store_properties() in class RedisHandler extending abstract DatabaseHandler
        # class RabbitMessageQueue extending abstract MessageHandler

    def __connect_to_network(self, network_id):
        # Creates an intermediary container acting as an interface to the PGA.
        pga_network = self.docker_master_client.networks.get(network_id)
        bridge_network = self.__get_bridge_network()
        connector = self.docker_master_client.services.create(
            image="jluech/pga-cloud-connector",
            name="connector{sep_}{id_}".format(
                name_="connector",
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            hostname="connector",
            networks=[pga_network.name, bridge_network.name],
            labels={"PGAcloud": "PGA-{id_}".format(id_=self.pga_id)},
            endpoint_spec={
                "Ports": [
                    {"Protocol": "tcp", "PublishedPort": 5001, "TargetPort": 5000},
                ]
            },
        )

        # Updates the service with SSL secrets.
        script_path = os.path.join(os.getcwd(), "utilities/docker_service_update_secrets.sh")
        script_args = "--certs {certs_} --host {host_}"
        utils.execute_command(
            command=script_path + " " + script_args.format(
                certs_="/run/secrets",
                host_=self.host
            ),
            working_directory=os.curdir,
            environment_variables=None,
            executor="DockerOrchestrator",
            livestream=True
        )
        return connector

    def __disconnect_from_network(self, network_id):
        # Disconnects the manager service from the PGA network.
        logging.debug("DISCONNECTING FROM NETWORK {id_}".format(id_=network_id))  # TODO
        # manager_container = self.docker_local_client.containers.list(
        #     filters={"label": "com.docker.swarm.service.name=manager"})[0]
        # network = self.docker_master_client.networks.get(network_id, verbose=True, scope="swarm")
        # network.disconnect(manager_container)

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
            base_url="tcp://{ip_}:{port_}".format(
                ip_=host_ip,
                port_=host_port
            ),
            tls=tls_config,
        )
        return docker_client

    def __get_bridge_network(self):
        # Gets the docker network to bridge the manager to the connector.
        return self.docker_master_client.networks.list(filters={"labels": "PGAcloud=PGA-Connection"})

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
        )
