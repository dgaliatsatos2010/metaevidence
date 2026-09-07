from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import httpx

from .adapters import (
    COREAdapter,
    CrossrefAdapter,
    EuropePMCAdapter,
    OpenAlexAdapter,
    OpenAlexOQLAdapter,
    PubMedAdapter,
    ScopusAdapter,
    WebOfScienceStarterAdapter,
    WebOfScienceExpandedAdapter,
)
from .adapters.base import AdapterResult
from .dedup import DeduplicationEngine, DeduplicationResult
from .http import DiskResponseCache, RawAuditStore, RetryPolicy
from .manifest import SearchManifest
from .models import EvidenceRecord
from .query import SearchQuery


_SOURCE_FACTORIES = {
    "pubmed": PubMedAdapter,
    "openalex": OpenAlexAdapter,
    "openalex_oql": OpenAlexOQLAdapter,
    "oql": OpenAlexOQLAdapter,
    "crossref": CrossrefAdapter,
    "europe_pmc": EuropePMCAdapter,
    "europepmc": EuropePMCAdapter,
    "core": COREAdapter,
    "scopus": ScopusAdapter,
    "web_of_science": WebOfScienceStarterAdapter,
    "webofscience": WebOfScienceStarterAdapter,
    "wos": WebOfScienceStarterAdapter,
    "web_of_science_expanded": WebOfScienceExpandedAdapter,
    "wos_expanded": WebOfScienceExpandedAdapter,
}


@dataclass(slots=True)
class MultiSearchResult:
    query: SearchQuery
    source_results: dict[str, AdapterResult]
    records: list[EvidenceRecord]
    manifest: SearchManifest
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def total_retrieved(self) -> int:
        return len(self.records)

    def deduplicate(self, engine: DeduplicationEngine | None = None) -> DeduplicationResult:
        return (engine or DeduplicationEngine()).deduplicate(self.records)


class EvidenceSearch:
    """Execute one canonical query across multiple bibliographic sources.

    Source failures are isolated by default so a temporary outage does not erase successful
    results from other databases. The manifest records both successes and failures.
    """

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        audit_dir: str | Path | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout: float = 30.0,
    ):
        self.cache = DiskResponseCache(cache_dir) if cache_dir else None
        self.audit_store = RawAuditStore(audit_dir) if audit_dir else None
        self.retry_policy = retry_policy
        self.timeout = timeout

    def run(
        self,
        query: SearchQuery,
        *,
        sources: Iterable[str] = ("pubmed", "openalex", "crossref", "europe_pmc"),
        max_records_per_source: int | None = 1000,
        page_size: int | None = None,
        raise_on_error: bool = False,
        clients: dict[str, httpx.Client] | None = None,
        adapter_options: dict[str, dict[str, object]] | None = None,
    ) -> MultiSearchResult:
        from . import __version__

        manifest = SearchManifest(canonical_query=query.canonical, package_version=__version__)
        results: dict[str, AdapterResult] = {}
        records: list[EvidenceRecord] = []
        failures: dict[str, str] = {}

        for raw_source in sources:
            source = raw_source.lower().replace(" ", "_")
            if source == "europepmc":
                source = "europe_pmc"
            if source in {"webofscience", "wos"}:
                source = "web_of_science"
            if source in {"openalex-oql", "oql"}:
                source = "openalex_oql"
            if source in {"webofscience_expanded", "wos_expanded"}:
                source = "web_of_science_expanded"
            if source not in _SOURCE_FACTORIES:
                raise ValueError(f"Unsupported live source: {raw_source}")
            cls = _SOURCE_FACTORIES[source]
            source_options = dict((adapter_options or {}).get(source, {}))
            adapter = cls(
                client=(clients or {}).get(source), retry_policy=self.retry_policy,
                timeout=self.timeout, cache=self.cache, audit_store=self.audit_store,
                **source_options,
            )
            try:
                result = adapter.search(query, max_records=max_records_per_source, page_size=page_size)
                results[source] = result
                records.extend(result.records)
                manifest.add_execution(result)
            except Exception as exc:
                failures[source] = f"{type(exc).__name__}: {exc}"
                manifest.add_failure(source=source, error=failures[source])
                if raise_on_error:
                    raise
            finally:
                adapter.close()

        return MultiSearchResult(query=query, source_results=results, records=records, manifest=manifest, failures=failures)
