from __future__ import annotations

import os
from typing import Any

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery
from ..translators import Translation, translate


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value).strip() or None


def _year(value: Any) -> int | None:
    try:
        result = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    return result if 1000 <= result <= 3000 else None


def _authors(hit: dict[str, Any]) -> list[str]:
    names = hit.get("names") or {}
    raw = names.get("authors") or []
    if isinstance(raw, dict):
        raw = [raw]
    out: list[str] = []
    for author in raw:
        if isinstance(author, dict):
            name = _text(author.get("displayName") or author.get("wosStandard") or author.get("name"))
        else:
            name = _text(author)
        if name:
            out.append(name)
    return out


def _citation_count(hit: dict[str, Any]) -> int | None:
    values: list[int] = []
    for item in hit.get("citations") or []:
        if not isinstance(item, dict):
            continue
        try:
            values.append(int(item.get("count")))
        except (TypeError, ValueError):
            pass
    return max(values) if values else None


class WebOfScienceStarterAdapter(BaseAdapter):
    """Web of Science Starter API v2 adapter.

    The Starter API is deliberately treated as a basic-metadata endpoint, distinct from
    the paid Web of Science API Expanded. Its compiler uses Starter-safe field tags and
    records approximations explicitly.
    """

    source = "web_of_science"
    ENDPOINT = "https://api.clarivate.com/apis/wos-starter/v2/documents"

    def __init__(self, *, api_key: str | None = None, database: str = "WOS", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("WOS_API_KEY") or os.getenv("WEB_OF_SCIENCE_API_KEY")
        self.database = database

    def compile(self, query: SearchQuery) -> Translation:
        return translate(query, "web_of_science_starter")

    @staticmethod
    def _record(hit: dict[str, Any], *, query: str, retrieved_at: str, rank: int) -> EvidenceRecord:
        identifiers = hit.get("identifiers") or {}
        source = hit.get("source") or {}
        doi = _text(identifiers.get("doi"))
        pmid = _text(identifiers.get("pmid"))
        uid = _text(hit.get("uid"))
        return EvidenceRecord(
            title=_text(hit.get("title")) or "[Untitled Web of Science record]",
            authors=_authors(hit),
            year=_year(source.get("publishYear") or hit.get("publishYear")),
            journal=_text(source.get("sourceTitle")),
            abstract=None,
            doi=doi,
            pmid=pmid,
            wos_ut=uid,
            source_hits=[SourceHit("web_of_science", source_id=uid or doi, query=query, retrieved_at=retrieved_at, rank=rank)],
            metadata={
                "api_variant": "starter_v2",
                "document_types": hit.get("types"),
                "volume": source.get("volume"),
                "issue": source.get("issue"),
                "pages": source.get("pages"),
                "article_number": source.get("articleNumber"),
                "publish_month": source.get("publishMonth"),
                "issn": identifiers.get("issn"),
                "eissn": identifiers.get("eissn"),
                "isbn": identifiers.get("isbn"),
                "author_keywords": (hit.get("keywords") or {}).get("authorKeywords") if isinstance(hit.get("keywords"), dict) else None,
                "times_cited": _citation_count(hit),
                "links": hit.get("links"),
            },
        )

    @staticmethod
    def _year_ok(record: EvidenceRecord, query: SearchQuery) -> bool:
        if record.year is None:
            return True
        if query.year_from is not None and record.year < query.year_from:
            return False
        if query.year_to is not None and record.year > query.year_to:
            return False
        return True

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        if not self.api_key:
            raise ValueError("Web of Science Starter requires an API key. Set WOS_API_KEY (or WEB_OF_SCIENCE_API_KEY) or pass api_key=...")
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 50), 50)
        records: list[EvidenceRecord] = []
        pages = 0
        page = 1
        total: int | None = None
        warnings: list[str] = []
        headers = {"Accept": "application/json", "X-ApiKey": self.api_key}

        bounded_server_date = query.year_from is not None and query.year_to is not None
        local_year_filter = (query.year_from is not None or query.year_to is not None) and not bounded_server_date
        source_exhausted = False
        while not source_exhausted:
            if max_records is not None and len(records) >= max_records:
                break
            params: dict[str, Any] = {"db": self.database, "q": translation.translated, "limit": page_size, "page": page}
            if bounded_server_date:
                params["publishTimeSpan"] = f"{query.year_from}-01-01 {query.year_to}-12-31"
            response = self.http.get(self.ENDPOINT, params=params, headers=headers, cacheable=True)
            payload = response.json() or {}
            metadata = payload.get("metadata") or {}
            if total is None:
                try:
                    total = int(metadata.get("total", 0))
                except (TypeError, ValueError):
                    total = None
            batch = payload.get("hits") or []
            retrieved_at = utcnow()
            base_rank = (page - 1) * page_size
            for i, hit in enumerate(batch):
                rec = self._record(hit, query=translation.translated, retrieved_at=retrieved_at, rank=base_rank + i + 1)
                if local_year_filter and not self._year_ok(rec, query):
                    continue
                records.append(rec)
                if max_records is not None and len(records) >= max_records:
                    break
            pages += 1
            page += 1
            source_exhausted = not batch or len(batch) < page_size or (total is not None and base_rank + len(batch) >= total)

        warnings.append("Web of Science Starter returns basic bibliographic metadata and is not equivalent to the richer paid Web of Science API Expanded; abstracts/full records may be unavailable.")
        warnings.append("Starter API plans have different request/day limits and times-cited entitlements. Record the plan used when reporting a reproducible search.")
        if local_year_filter:
            warnings.append("A one-sided Web of Science year bound was applied locally because Starter publishTimeSpan is emitted only for fully bounded ranges in MetaEvidence v0.9.1.")
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
                "api_variant": "starter_v2",
                "database": self.database,
                "pagination": "page_limit",
                "page_size": page_size,
                "bounded_server_date_filter": bounded_server_date,
                "local_year_filter": local_year_filter,
                "entitlement_dependent": True,
            },
        )
