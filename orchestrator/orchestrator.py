import itertools
from abc import ABC, abstractmethod


class Orchestrator(ABC):
    new_id = itertools.count().__next__
    pga_id = None  # define in child constructor as shown in abstract constructor below

    name_separator = "--"

    @abstractmethod
    def __init__(self):
        # self.pga_id = Orchestrator.new_id()
        pass

    @abstractmethod
    def setup_pga(self, services, setups, operators, population, properties):
        pass

    @abstractmethod
    def scale_component(self, network, component, scaling):
        # raise Warning("Scaling aborted: Scaling of runner or manager services not permitted!")
        pass
