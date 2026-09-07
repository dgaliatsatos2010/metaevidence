from __future__ import annotations

import os
from typing import Any

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery


def _reconstruct_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, locs in index.items():
        positions.extend((int(pos), word) for pos in locs)
    return " ".join(word for _, word in sorted(positions)) or None


class OpenAlexAdapter(BaseAdapter):
    source = "openalex"
    ENDPOINT = "https://api.openalex.org/works"

    def __init__(self, *, api_key: str | None = None, email: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("OPENALEX_API_KEY")
        self.email = email or os.getenv("OPENALEX_EMAIL")

    @staticmethod
    def _record(item: dict[str, Any], *, query: str, retrieved_at: str, rank: int, source_name: str = "openalex") -> EvidenceRecord:
        ids = item.get("ids") or {}
        pmid = ids.get("pmid")
        if pmid and "/" in pmid:
            pmid = pmid.rstrip("/").rsplit("/", 1)[-1]
        source = ((item.get("primary_location") or {}).get("source") or {})
        authors = [
            (a.get("author") or {}).get("display_name")
            for a in item.get("authorships") or []
            if (a.get("author") or {}).get("display_name")
        ]
        oa_id = item.get("id")
        return EvidenceRecord(
            title=item.get("title") or item.get("display_name") or "[Untitled OpenAlex record]",
            authors=authors,
            year=item.get("publication_year"),
            journal=source.get("display_name"),
            abstract=_reconstruct_abstract(item.get("abstract_inverted_index")),
            doi=item.get("doi") or ids.get("doi"),
            pmid=pmid,
            openalex_id=oa_id,
            source_hits=[SourceHit(source_name, source_id=oa_id, query=query, retrieved_at=retrieved_at, rank=rank)],
            metadata={
                "publication_date": item.get("publication_date"),
                "type": item.get("type"),
                "language": item.get("language"),
                "cited_by_count": item.get("cited_by_count"),
                "is_retracted": item.get("is_retracted"),
                "open_access": item.get("open_access"),
                "source_issn_l": source.get("issn_l"),
                "source_issn": source.get("issn"),
                "primary_location": item.get("primary_location"),
            },
        )

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 100), 100)
        cursor: str | None = "*"
        records: list[EvidenceRecord] = []
        pages = 0
        total: int | None = None
        warnings: list[str] = []
        cost_usd = 0.0

        while cursor:
            remaining = None if max_records is None else max_records - len(records)
            if remaining is not None and remaining <= 0:
                break
            take = page_size if remaining is None else min(page_size, remaining)
            params: dict[str, Any] = {
                "search": translation.translated,
                "per_page": take,
                "cursor": cursor,
            }
            filters: list[str] = []
            if query.year_from:
                filters.append(f"from_publication_date:{query.year_from}-01-01")
            if query.year_to:
                filters.append(f"to_publication_date:{query.year_to}-12-31")
            if filters:
                params["filter"] = ",".join(filters)
            if self.api_key:
                params["api_key"] = self.api_key
            elif self.email:
                params["mailto"] = self.email

            response = self.http.get(self.ENDPOINT, params=params, cacheable=True)
            payload = response.json()
            meta = payload.get("meta") or {}
            if total is None:
                total = int(meta.get("count", 0))
            try:
                cost_usd += float(meta.get("cost_usd") or 0)
            except (TypeError, ValueError):
                pass
            batch = payload.get("results") or []
            retrieved_at = utcnow()
            start_rank = len(records) + 1
            records.extend(self._record(item, query=translation.translated, retrieved_at=retrieved_at, rank=start_rank + i) for i, item in enumerate(batch))
            pages += 1
            next_cursor = meta.get("next_cursor")
            if not batch or not next_cursor or next_cursor == cursor:
                cursor = None
            else:
                cursor = next_cursor
            if len(batch) < take:
                break

        if not self.api_key:
            warnings.append("OpenAlex API key not supplied; public access may have lower budgets/rate limits.")
        truncated = total is not None and len(records) < total and max_records is not None and len(records) >= max_records
        return AdapterResult(
            source=self.source, translation=translation, records=records, total_available=total,
            pages_retrieved=pages, request_log=list(self.http.logs), warnings=warnings,
            truncated=truncated, started_at_utc=started, finished_at_utc=utcnow(),
            metadata={"cursor_pagination": True, "estimated_api_cost_usd": round(cost_usd, 6)},
        )
