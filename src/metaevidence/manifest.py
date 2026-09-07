from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapters.base import AdapterResult


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SearchManifest:
    canonical_query: str
    package_version: str
    searches: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    created_at_utc: str = field(default_factory=_utcnow)
    schema_version: str = "1.0"

    def add_search(self, *, source: str, translated_query: str, count: int | None = None, metadata: dict | None = None) -> None:
        """Backward-compatible compact search entry."""
        self.searches.append({
            "source": source,
            "translated_query": translated_query,
            "count": count,
            "metadata": metadata or {},
        })

    def add_execution(self, result: "AdapterResult") -> None:
        self.searches.append(result.to_dict(include_records=False))

    def add_failure(self, *, source: str, error: str) -> None:
        self.failures.append({"source": source, "error": error, "recorded_at_utc": _utcnow()})

    def to_dict(self) -> dict:
        return asdict(self)

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
