import itertools
import logging
from abc import ABC, abstractmethod

import requests


class Orchestrator(ABC):
    new_id = itertools.count().__next__
    name_separator = "--"

    def __init__(self, pga_id=None):
        if pga_id is None:
            self.pga_id = Orchestrator.new_id()
        else:
            self.pga_id = pga_id

    @abstractmethod
    def setup_pga(self, model, services, setups, operators, population, properties, file_names):
        # Creates and deploys all components required for a new PGA.
        pass

    @abstractmethod
    def scale_component(self, component, scaling):
        # Scales the given service to the given scaling amount. Network identified by service naming.
        # raise Warning("Scaling aborted: Scaling of runner or manager services not permitted!")
        pass

    @abstractmethod
    def remove_pga(self):
        # Removes the components of the PGA.
        pass

    def distribute_properties(self, properties):
        response = requests.put(
            url="http://runner{sep_}{id_}:5000/{id_}/properties".format(
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            data=properties,
            verify=False
        )
        logging.info("PUT - http://runner{sep_}{id_}:5000/{id_}/properties - {status_}".format(
            sep_=Orchestrator.name_separator,
            id_=self.pga_id,
            status_=response.status_code,
        ))

    def initialize_population(self, population):
        response = requests.post(
            url="http://runner{sep_}{id_}:5000/{id_}/population".format(
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            data=population,
            verify=False
        )
        logging.info("POST - http://runner{sep_}{id_}:5000/{id_}/population - {status_}".format(
            sep_=Orchestrator.name_separator,
            id_=self.pga_id,
            status_=response.status_code,
        ))

    def start_pga(self):
        return requests.put(
            url="http://runner{sep_}{id_}:5000/{id_}/start".format(
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            verify=False
        )

    def stop_pga(self):
        response = requests.put(
            url="http://runner{sep_}{id_}:5000/stop".format(
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            verify=False
        )
        return response.status_code
