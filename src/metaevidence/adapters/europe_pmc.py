from __future__ import annotations

import os
from typing import Any

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery


class EuropePMCAdapter(BaseAdapter):
    source = "europe_pmc"
    ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, *, email: str | None = None, synonym: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.email = email or os.getenv("EUROPE_PMC_EMAIL")
        self.synonym = synonym

    @staticmethod
    def _record(item: dict[str, Any], *, query: str, retrieved_at: str, rank: int) -> EvidenceRecord:
        authors: list[str] = []
        for author in ((item.get("authorList") or {}).get("author") or []):
            name = author.get("fullName") or " ".join(x for x in (author.get("lastName"), author.get("firstName")) if x)
            if name:
                authors.append(name)
        journal = (((item.get("journalInfo") or {}).get("journal") or {}).get("title"))
        pmid = item.get("pmid")
        source_id = f"{item.get('source')}:{item.get('id')}" if item.get("source") or item.get("id") else pmid
        pub_types = ((item.get("pubTypeList") or {}).get("pubType") or [])
        try:
            year = int(item.get("pubYear")) if item.get("pubYear") else None
        except (TypeError, ValueError):
            year = None
        return EvidenceRecord(
            title=item.get("title") or "[Untitled Europe PMC record]",
            authors=authors,
            year=year,
            journal=journal,
            abstract=item.get("abstractText"),
            doi=item.get("doi"),
            pmid=pmid,
            source_hits=[SourceHit("europe_pmc", source_id=source_id, query=query, retrieved_at=retrieved_at, rank=rank)],
            metadata={
                "pmcid": item.get("pmcid"),
                "source": item.get("source"),
                "external_id": item.get("id"),
                "first_publication_date": item.get("firstPublicationDate"),
                "journal_issn": (((item.get("journalInfo") or {}).get("journal") or {}).get("issn")),
                "publication_types": pub_types,
                "cited_by_count": item.get("citedByCount"),
                "is_open_access": item.get("isOpenAccess"),
                "has_pdf": item.get("hasPDF"),
                "has_full_text": item.get("hasTextMinedTerms") or item.get("inPMC"),
                "mesh_heading_list": item.get("meshHeadingList"),
            },
        )

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 1000), 1000)
        cursor: str | None = "*"
        records: list[EvidenceRecord] = []
        pages = 0
        total: int | None = None
        warnings: list[str] = []

        while cursor:
            remaining = None if max_records is None else max_records - len(records)
            if remaining is not None and remaining <= 0:
                break
            take = page_size if remaining is None else min(page_size, remaining)
            params: dict[str, Any] = {
                "query": translation.translated,
                "format": "json",
                "resultType": "core",
                "pageSize": take,
                "cursorMark": cursor,
            }
            if self.synonym:
                params["synonym"] = "TRUE"
            if self.email:
                params["email"] = self.email
            response = self.http.get(self.ENDPOINT, params=params, cacheable=True)
            payload = response.json()
            if total is None:
                total = int(payload.get("hitCount", 0))
            batch = ((payload.get("resultList") or {}).get("result") or [])
            retrieved_at = utcnow()
            start_rank = len(records) + 1
            records.extend(self._record(item, query=translation.translated, retrieved_at=retrieved_at, rank=start_rank + i) for i, item in enumerate(batch))
            pages += 1
            next_cursor = payload.get("nextCursorMark")
            if not batch or len(batch) < take or not next_cursor or next_cursor == cursor:
                cursor = None
            else:
                cursor = next_cursor

        truncated = total is not None and len(records) < total and max_records is not None and len(records) >= max_records
        return AdapterResult(
            source=self.source, translation=translation, records=records, total_available=total,
            pages_retrieved=pages, request_log=list(self.http.logs), warnings=warnings,
            truncated=truncated, started_at_utc=started, finished_at_utc=utcnow(),
            metadata={"cursor_pagination": True, "result_type": "core", "synonym_expansion": self.synonym},
        )
