from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
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
    def build(cls, data: Dict[str, Any]) -> "ObservationData":
        return ObservationData(**data)

    @classmethod
    def build_in_bulk(cls, data: List[Dict[str, Any]]) -> List["ObservationData"]:
        return [ObservationData(**d) for d in data]

    def to_dict(self):
        return {k: str(v) for k, v in asdict(self).items()}
