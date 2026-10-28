"""Job-source adapter contract and the Compliance Registry (spec §7.1, docs/sources.md)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from app.services.job_parser import JobDraft


@dataclass(frozen=True)
class AdapterCapabilities:
    discover: bool = False
    import_: bool = True
    verify_listing: bool = False
    assisted_apply: bool = False
    api_apply: bool = False


@dataclass(frozen=True)
class ComplianceInfo:
    tos_url: str
    reviewed_on: str
    allowed_methods: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class RawJob:
    payload: Any
    ref: str = ""


@dataclass
class FetchContext:
    params: dict[str, Any]


class JobSourceAdapter(Protocol):
    id: str
    name: str
    capabilities: AdapterCapabilities
    compliance: ComplianceInfo
    settings_flag: str | None

    def fetch(self, ctx: FetchContext) -> AsyncIterator[RawJob]: ...

    def normalize(self, raw: RawJob) -> JobDraft: ...


@dataclass(frozen=True)
class DisabledSource:
    """A source we deliberately do not automate, listed so the UI can explain why."""

    id: str
    name: str
    reason: str
    manual_path: str
    tos_url: str
    reviewed_on: str


def describe(adapter: JobSourceAdapter, enabled: bool) -> dict[str, Any]:
    caps = asdict(adapter.capabilities)
    caps["import"] = caps.pop("import_")
    return {
        "id": adapter.id,
        "name": adapter.name,
        "enabled": enabled,
        "capabilities": caps,
        "compliance": asdict(adapter.compliance),
    }
