from abc import ABC, abstractmethod
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from app.normalization import NormalizedEventRecord

class SourceFetchResult(BaseModel):
    source_name: str
    status: str  # "success", "restricted", "error"
    events: List[NormalizedEventRecord] = Field(default_factory=list)
    events_count: int = 0
    notes: str
    error_message: Optional[str] = None

class BaseEventSourceAdapter(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the event source (e.g. 'Devfolio', 'Unstop', 'MLH')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Indicates whether permitted automated public access is available."""
        pass

    @abstractmethod
    def get_limitations(self) -> str:
        """Documents safety and access limitations for this adapter."""
        pass

    @abstractmethod
    def fetch_events(
        self,
        limit: int = 15,
        client: Optional[Any] = None,
        criteria: Optional[dict] = None,
    ) -> SourceFetchResult:
        """Fetches and normalizes publicly available events based on student criteria."""
        pass
