import itertools
from abc import ABC, abstractmethod


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
    def distribute_properties(self, properties):
        # Triggers the distribution and storing of the PGA properties.
        pass

    @abstractmethod
    def initialize_population(self, population):
        # Triggers the initialization of the population.
        pass

    @abstractmethod
    def scale_component(self, component, scaling):
        # Scales the given service to the given scaling amount. Network identified by service naming.
        # raise Warning("Scaling aborted: Scaling of runner or manager services not permitted!")
        pass
