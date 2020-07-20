import itertools
from abc import ABC, abstractmethod

import requests


class Orchestrator(ABC):
    new_id = itertools.count().__next__
    name_separator = "--"

    def __init__(self, pga_id=None):
        if not pga_id:
            self.pga_id = Orchestrator.new_id()
        else:
            self.pga_id = pga_id

    @abstractmethod
    def setup_pga(self, services, setups, operators, population, properties, file_names):
        # Creates and deploys all components required for a new PGA.
        pass

    @abstractmethod
    def scale_component(self, component, scaling):
        # Scales the given service to the given scaling amount. Network identified by service naming.
        # raise Warning("Scaling aborted: Scaling of runner or manager services not permitted!")
        pass

    def distribute_properties(self, properties):
        requests.put(
            url="http://runner{sep_}{id_}:5000/{id_}/properties".format(
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            data=properties,
            verify=False
        )

    def initialize_population(self, population):
        # TODO: remove connector image and repo since no longer needed
        requests.post(
            url="http://runner{sep_}{id_}:5000/{id_}/population".format(
                sep_=Orchestrator.name_separator,
                id_=self.pga_id
            ),
            data=population,
            verify=False
        )
