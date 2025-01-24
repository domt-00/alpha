from alpha.agent import Agent
from alpha.person import Person

from abc import abstractmethod

class Proxy(Agent):

    def __init__(self, person: Person):
        raise NotImplementedError
    
class ProxyFactory:
    
    @abstractmethod
    def __call__(self, person: Person) -> Proxy:
        pass