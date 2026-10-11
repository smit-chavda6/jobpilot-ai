"""Job source adapter interface, protocols, and compliance data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol


@dataclass
class AdapterCapabilities:
    discover: bool = False
    import_listing: bool = True
    verify_listing: bool = True
    assisted_apply: bool = False
    api_apply: bool = False


@dataclass
class ComplianceInfo:
    tos_url: Optional[str]
    reviewed_on: str
    allowed_methods: List[str]
    notes: str
    is_enabled: bool = True


@dataclass
class RawJob:
    source_id: str
    external_id: Optional[str]
    raw_payload: Dict[str, Any]
    retrieved_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobDraft:
    title: str
    company: str
    description: str
    location: Optional[str] = None
    remote_type: str = "on-site"
    employment_type: str = "full-time"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "USD"
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    source_id: str = "manual"
    source_url: Optional[str] = None
    posted_at: Optional[datetime] = None


class JobSourceAdapter(Protocol):
    id: str
    capabilities: AdapterCapabilities
    compliance: ComplianceInfo

    async def fetch(self, ctx: Dict[str, Any]) -> AsyncIterator[RawJob]: ...

    def normalize(self, raw: RawJob) -> JobDraft: ...
