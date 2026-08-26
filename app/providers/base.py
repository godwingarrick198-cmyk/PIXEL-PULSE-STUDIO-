from abc import ABC, abstractmethod

class ProspectProvider(ABC):
    name = 'provider'
    @abstractmethod
    async def discover_prospects(self, query):
        raise NotImplementedError
