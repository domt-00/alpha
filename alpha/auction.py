from abc import ABC, abstractmethod

from alpha.scenario import Scenario, Bundle
from alpha.agent import Agent

AgentOutcome = tuple[Bundle, float]
Allocation = list[AgentOutcome]

class Auction(ABC):
    
    @abstractmethod
    def __call__(
        scenario: Scenario = None,
        agents: list[Agent] = None
    ) -> Allocation:
        raise NotImplementedError