from __future__ import annotations

import os
from typing import Any

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery


def _first_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    if isinstance(value, dict):
        for key in ("title", "name", "displayName", "value"):
            text = _first_text(value.get(key))
            if text:
                return text
    return None


def _authors(value: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(value, list):
        return out
    for author in value:
        if isinstance(author, str):
            name = author.strip()
        elif isinstance(author, dict):
            name = str(author.get("name") or author.get("displayName") or "").strip()
        else:
            name = ""
        if name:
            out.append(name)
    return out


def _year(value: Any) -> int | None:
    try:
        year = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    return year if 1000 <= year <= 3000 else None


class COREAdapter(BaseAdapter):
    """CORE v3 open-access works search adapter.

    v0.9.1 intentionally uses conservative offset pagination and applies canonical
    one-/two-sided publication-year bounds locally. This keeps date semantics auditable
    when the public CORE query dialect changes, at the cost of potentially fetching
    additional pages for narrow year windows.
    """

    source = "core"
    ENDPOINT = "https://api.core.ac.uk/v3/search/works/"

    def __init__(self, *, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("CORE_API_KEY")

    @staticmethod
    def _record(item: dict[str, Any], *, query: str, retrieved_at: str, rank: int) -> EvidenceRecord:
        core_id = item.get("id")
        journals = item.get("journals") or item.get("journal")
        journal = _first_text(journals)
        doi = _first_text(item.get("doi"))
        year = _year(item.get("yearPublished") or item.get("publishedDate"))
        full_text = item.get("fullText")
        download_url = _first_text(item.get("downloadUrl"))
        title = _first_text(item.get("title")) or "[Untitled CORE record]"
        return EvidenceRecord(
            title=title,
            authors=_authors(item.get("authors")),
            year=year,
            journal=journal,
            abstract=_first_text(item.get("abstract")),
            doi=doi,
            source_hits=[SourceHit("core", source_id=str(core_id) if core_id is not None else doi, query=query, retrieved_at=retrieved_at, rank=rank)],
            metadata={
                "core_id": core_id,
                "download_url": download_url,
                "full_text_available": bool(full_text or download_url),
                "document_type": item.get("documentType"),
                "language": item.get("language"),
                "publisher": item.get("publisher"),
                "oai": item.get("oai"),
                "arxiv_id": item.get("arxivId"),
                "data_providers": item.get("dataProviders"),
                "open_access_source": True,
            },
        )

    @staticmethod
    def _year_ok(record: EvidenceRecord, query: SearchQuery) -> bool:
        if record.year is None:
            # Unknown publication year is retained rather than silently excluded.
            return True
        if query.year_from is not None and record.year < query.year_from:
            return False
        if query.year_to is not None and record.year > query.year_to:
            return False
        return True

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 100), 100)
        records: list[EvidenceRecord] = []
        pages = 0
        offset = 0
        total: int | None = None
        warnings: list[str] = []
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        local_year_filter = query.year_from is not None or query.year_to is not None
        source_exhausted = False
        while not source_exhausted:
            if max_records is not None and len(records) >= max_records:
                break
            params: dict[str, Any] = {"q": translation.translated, "limit": page_size, "offset": offset}
            response = self.http.get(self.ENDPOINT, params=params, headers=headers, cacheable=True)
            payload = response.json() or {}
            if total is None:
                try:
                    total = int(payload.get("totalHits"))
                except (TypeError, ValueError):
                    total = None
            batch = payload.get("results") or []
            retrieved_at = utcnow()
            for i, item in enumerate(batch):
                rec = self._record(item, query=translation.translated, retrieved_at=retrieved_at, rank=offset + i + 1)
                if not self._year_ok(rec, query):
                    continue
                records.append(rec)
                if max_records is not None and len(records) >= max_records:
                    break
            pages += 1
            offset += len(batch)
            source_exhausted = not batch or len(batch) < page_size or (total is not None and offset >= total)

        if not self.api_key:
            warnings.append("CORE_API_KEY was not supplied. Availability and rate limits for unauthenticated requests may be more restrictive; register a CORE API key for reproducible production searches.")
        if local_year_filter:
            warnings.append("CORE publication-year bounds are applied locally in v0.9.1. total_available therefore refers to the unfiltered CORE query, and narrow year windows may require extra API pages.")
        if translation.fidelity_score < 1.0:
            warnings.append("CORE query-field semantics are not assumed to be identical to the canonical MetaEvidence field model; inspect translation diagnostics for systematic-review use.")
        truncated = bool(max_records is not None and len(records) >= max_records and not source_exhausted)
        return AdapterResult(
            source=self.source,
            translation=translation,
            records=records,
            total_available=total,
            pages_retrieved=pages,
            request_log=list(self.http.logs),
            warnings=warnings,
            truncated=truncated,
            started_at_utc=started,
            finished_at_utc=utcnow(),
            metadata={
                "api_version": "v3",
                "pagination": "offset",
                "page_size": page_size,
                "authenticated": bool(self.api_key),
                "local_year_filter": local_year_filter,
                "total_available_scope": "pre_local_year_filter" if local_year_filter else "query",
                "open_access_corpus": True,
            },
        )
