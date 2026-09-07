from __future__ import annotations

from html import unescape
import os
import re
from typing import Any

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery


def _strip_markup(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip() or None


def _date_parts(item: dict[str, Any]) -> tuple[int | None, str | None]:
    for key in ("published", "published-print", "published-online", "issued", "created"):
        obj = item.get(key) or {}
        parts = obj.get("date-parts") or []
        if parts and parts[0]:
            vals = parts[0]
            year = int(vals[0]) if vals and vals[0] else None
            if year:
                month = int(vals[1]) if len(vals) > 1 and vals[1] else 1
                day = int(vals[2]) if len(vals) > 2 and vals[2] else 1
                return year, f"{year:04d}-{month:02d}-{day:02d}"
    return None, None


class CrossrefAdapter(BaseAdapter):
    source = "crossref"
    ENDPOINT = "https://api.crossref.org/works"

    def __init__(self, *, mailto: str | None = None, api_key: str | None = None, user_agent: str = "MetaEvidence/0.3", **kwargs):
        super().__init__(**kwargs)
        self.mailto = mailto or os.getenv("CROSSREF_MAILTO")
        self.api_key = api_key or os.getenv("CROSSREF_API_KEY")
        self.user_agent = user_agent

    @staticmethod
    def _record(item: dict[str, Any], *, query: str, retrieved_at: str, rank: int) -> EvidenceRecord:
        year, publication_date = _date_parts(item)
        authors: list[str] = []
        for author in item.get("author") or []:
            family = (author.get("family") or "").strip()
            given = (author.get("given") or "").strip()
            literal = (author.get("name") or "").strip()
            name = " ".join(x for x in (family, given) if x) or literal
            if name:
                authors.append(name)
        title_values = item.get("title") or []
        container = item.get("container-title") or []
        doi = item.get("DOI")
        return EvidenceRecord(
            title=(title_values[0] if title_values else "[Untitled Crossref record]"),
            authors=authors,
            year=year,
            journal=(container[0] if container else None),
            abstract=_strip_markup(item.get("abstract")),
            doi=doi,
            source_hits=[SourceHit("crossref", source_id=doi or item.get("URL"), query=query, retrieved_at=retrieved_at, rank=rank)],
            metadata={
                "publication_date": publication_date,
                "type": item.get("type"),
                "url": item.get("URL"),
                "issn": item.get("ISSN"),
                "isbn": item.get("ISBN"),
                "publisher": item.get("publisher"),
                "subject": item.get("subject"),
                "is_referenced_by_count": item.get("is-referenced-by-count"),
                "references_count": item.get("references-count"),
            },
        )

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 500), 1000)
        cursor: str | None = "*"
        records: list[EvidenceRecord] = []
        pages = 0
        total: int | None = None
        warnings: list[str] = []
        headers = {"User-Agent": self.user_agent}
        if self.api_key:
            headers["Crossref-Plus-API-Token"] = f"Bearer {self.api_key}"

        while cursor:
            remaining = None if max_records is None else max_records - len(records)
            if remaining is not None and remaining <= 0:
                break
            take = page_size if remaining is None else min(page_size, remaining)
            params: dict[str, Any] = {
                "query.bibliographic": translation.translated,
                "rows": take,
                "cursor": cursor,
            }
            filters: list[str] = []
            if query.year_from:
                filters.append(f"from-pub-date:{query.year_from}-01-01")
            if query.year_to:
                filters.append(f"until-pub-date:{query.year_to}-12-31")
            if filters:
                params["filter"] = ",".join(filters)
            if self.mailto:
                params["mailto"] = self.mailto

            response = self.http.get(self.ENDPOINT, params=params, headers=headers, cacheable=True)
            message = response.json().get("message") or {}
            if total is None:
                total = int(message.get("total-results", 0))
            batch = message.get("items") or []
            retrieved_at = utcnow()
            start_rank = len(records) + 1
            records.extend(self._record(item, query=translation.translated, retrieved_at=retrieved_at, rank=start_rank + i) for i, item in enumerate(batch))
            pages += 1
            next_cursor = message.get("next-cursor")
            if not batch or len(batch) < take or not next_cursor or next_cursor == cursor:
                cursor = None
            else:
                cursor = next_cursor

        if not self.mailto and not self.api_key:
            warnings.append("Crossref polite-pool identification was not supplied. Set CROSSREF_MAILTO for production use.")
        if translation.fidelity_score < 1.0:
            warnings.append("Crossref relevance-oriented bibliographic querying does not guarantee canonical Boolean/field semantics; review retrieval sensitivity before using it as a primary systematic-review database search.")
        truncated = total is not None and len(records) < total and max_records is not None and len(records) >= max_records
        return AdapterResult(
            source=self.source, translation=translation, records=records, total_available=total,
            pages_retrieved=pages, request_log=list(self.http.logs), warnings=warnings,
            truncated=truncated, started_at_utc=started, finished_at_utc=utcnow(),
            metadata={"cursor_pagination": True, "polite_pool": bool(self.mailto), "plus_api": bool(self.api_key)},
        )
