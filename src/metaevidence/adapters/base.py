from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import httpx

from ..http import DiskResponseCache, RawAuditStore, RequestLogEntry, RetryingClient, RetryPolicy
from ..models import EvidenceRecord
from ..query import SearchQuery
from ..translators import Translation, translate


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class AdapterResult:
    source: str
    translation: Translation
    records: list[EvidenceRecord]
    total_available: int | None
    pages_retrieved: int
    request_log: list[RequestLogEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def retrieved_count(self) -> int:
        return len(self.records)

    def to_dict(self, *, include_records: bool = False) -> dict[str, Any]:
        data = {
            "source": self.source,
            "translated_query": self.translation.translated,
            "fidelity_score": self.translation.fidelity_score,
            "loss_score": self.translation.loss_score,
            "requires_review": self.translation.requires_review,
            "total_available": self.total_available,
            "retrieved_count": self.retrieved_count,
            "pages_retrieved": self.pages_retrieved,
            "warnings": list(self.warnings),
            "truncated": self.truncated,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "metadata": self.metadata,
            "request_log": [x.to_dict() for x in self.request_log],
        }
        if include_records:
            data["records"] = [r.to_dict() for r in self.records]
        return data


class BaseAdapter:
    source = "base"

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout: float = 30.0,
        cache: DiskResponseCache | None = None,
        audit_store: RawAuditStore | None = None,
    ):
        self.http = RetryingClient(
            source=self.source,
            client=client,
            retry_policy=retry_policy,
            timeout=timeout,
            cache=cache,
            audit_store=audit_store,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def compile(self, query: SearchQuery) -> Translation:
        return translate(query, self.source)

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        raise NotImplementedError
