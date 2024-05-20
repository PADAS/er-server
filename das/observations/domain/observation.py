from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID


@dataclass
class ObservationData:
    additional: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    das_tenant: Optional[UUID] = None
    exclusion_flags: Optional[int] = None
    id: Optional[UUID] = None
    location: Optional[Dict[str, Any]] = None
    recorded_at: Optional[datetime] = None
    source: Optional[UUID] = None

    @classmethod
    def build_in_bulk(cls, data: Dict[str, Any]):
        return [ObservationData(**d) for d in data]

    def dict(self):
        return {k: str(v) for k, v in asdict(self).items()}
