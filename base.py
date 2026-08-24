from abc import ABC, abstractmethod
class ProspectProvider(ABC):
    name='base'
    @abstractmethod
    async def discover_prospects(self, query): ...
