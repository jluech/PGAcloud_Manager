import itertools
from abc import ABC, abstractmethod


class Orchestrator(ABC):
    new_id = itertools.count().__next__
    name_separator = "--"

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def setup_pga(self, components, services, population, properties):
        pass

    @abstractmethod
    def scale_component(self, network, component, scaling):
        # raise Warning("Scaling aborted: Scaling of runner or manager services not permitted!")
        pass
