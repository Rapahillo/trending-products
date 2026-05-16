from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CollectorResult:
    source: str
    items: list
    errors: list[str]


class BaseCollector(ABC):
    @abstractmethod
    async def collect(self) -> list:
        """Fetch data from the source. Returns list of parsed items."""
        ...

    @abstractmethod
    def parse_response(self, data: dict) -> list:
        """Parse raw API response into structured items."""
        ...
