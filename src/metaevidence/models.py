from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


def _norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    value = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value or None


@dataclass(slots=True)
class SourceHit:
    source: str
    source_id: str | None = None
    query: str | None = None
    retrieved_at: str | None = None
    rank: int | None = None


@dataclass(slots=True)
class EvidenceRecord:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    abstract: str | None = None
    doi: str | None = None
    pmid: str | None = None
    wos_ut: str | None = None
    scopus_eid: str | None = None
    openalex_id: str | None = None
    source_hits: list[SourceHit] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.doi = _norm_doi(self.doi)

    @property
    def identifiers(self) -> dict[str, str]:
        pairs = {
            "doi": self.doi,
            "pmid": self.pmid,
            "wos_ut": self.wos_ut,
            "scopus_eid": self.scopus_eid,
            "openalex_id": self.openalex_id,
        }
        return {k: v for k, v in pairs.items() if v}

    @property
    def sources(self) -> list[str]:
        return sorted({h.source for h in self.source_hits})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
