from __future__ import annotations

import os
from typing import Any

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value).strip() or None


def _year_from_date(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(text[:4])
    except ValueError:
        return None


def _authors(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    raw = entry.get("author") or []
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list):
        for author in raw:
            if not isinstance(author, dict):
                continue
            name = _text(author.get("authname"))
            if not name:
                surname = _text(author.get("surname")) or ""
                given = _text(author.get("given-name")) or _text(author.get("initials")) or ""
                name = " ".join(x for x in (surname, given) if x).strip() or None
            if name:
                out.append(name)
    if not out:
        creator = _text(entry.get("dc:creator"))
        if creator:
            out.append(creator)
    return out


class ScopusAdapter(BaseAdapter):
    source = "scopus"
    ENDPOINT = "https://api.elsevier.com/content/search/scopus"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        insttoken: str | None = None,
        view: str = "STANDARD",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("SCOPUS_API_KEY") or os.getenv("ELSEVIER_API_KEY")
        self.insttoken = insttoken or os.getenv("SCOPUS_INSTTOKEN") or os.getenv("ELSEVIER_INSTTOKEN")
        view = view.upper()
        if view not in {"STANDARD", "COMPLETE"}:
            raise ValueError("Scopus view must be STANDARD or COMPLETE")
        self.view = view

    @staticmethod
    def _record(entry: dict[str, Any], *, query: str, retrieved_at: str, rank: int) -> EvidenceRecord:
        eid = _text(entry.get("eid"))
        scopus_id = _text(entry.get("dc:identifier"))
        title = _text(entry.get("dc:title")) or "[Untitled Scopus record]"
        doi = _text(entry.get("prism:doi"))
        return EvidenceRecord(
            title=title,
            authors=_authors(entry),
            year=_year_from_date(entry.get("prism:coverDate")) or _year_from_date(entry.get("prism:coverDisplayDate")),
            journal=_text(entry.get("prism:publicationName")),
            abstract=_text(entry.get("dc:description")),
            doi=doi,
            scopus_eid=eid,
            source_hits=[SourceHit("scopus", source_id=eid or scopus_id or doi, query=query, retrieved_at=retrieved_at, rank=rank)],
            metadata={
                "scopus_id": scopus_id,
                "cover_date": entry.get("prism:coverDate"),
                "issn": entry.get("prism:issn"),
                "eissn": entry.get("prism:eIssn"),
                "volume": entry.get("prism:volume"),
                "issue": entry.get("prism:issueIdentifier"),
                "pages": entry.get("prism:pageRange"),
                "cited_by_count": entry.get("citedby-count"),
                "subtype": entry.get("subtype"),
                "subtype_description": entry.get("subtypeDescription"),
                "open_access": entry.get("openaccess"),
                "aggregation_type": entry.get("prism:aggregationType"),
            },
        )

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        if not self.api_key:
            raise ValueError("Scopus requires an Elsevier API key. Set SCOPUS_API_KEY (or ELSEVIER_API_KEY) or pass api_key=...")
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        # The service-level maximum can vary. A conservative 25 works across common tiers.
        page_size = min(max(1, page_size or 25), 25)
        records: list[EvidenceRecord] = []
        pages = 0
        start = 0
        total: int | None = None
        source_exhausted = False
        warnings: list[str] = []
        headers = {"Accept": "application/json", "X-ELS-APIKey": self.api_key}
        if self.insttoken:
            headers["X-ELS-Insttoken"] = self.insttoken

        while not source_exhausted:
            if max_records is not None and len(records) >= max_records:
                break
            remaining = None if max_records is None else max_records - len(records)
            take = page_size if remaining is None else min(page_size, remaining)
            params = {"query": translation.translated, "start": start, "count": take, "view": self.view}
            response = self.http.get(self.ENDPOINT, params=params, headers=headers, cacheable=True)
            root = response.json().get("search-results") or {}
            if total is None:
                try:
                    total = int(root.get("opensearch:totalResults", 0))
                except (TypeError, ValueError):
                    total = None
            batch = root.get("entry") or []
            retrieved_at = utcnow()
            records.extend(self._record(entry, query=translation.translated, retrieved_at=retrieved_at, rank=start + i + 1) for i, entry in enumerate(batch))
            pages += 1
            start += len(batch)
            source_exhausted = not batch or len(batch) < take or (total is not None and start >= total)

        warnings.append("Scopus metadata depth and accessible result ranges depend on API entitlements and institutional subscription. Preserve the API plan/view in the search manifest when reporting a systematic review.")
        if self.view == "STANDARD":
            warnings.append("Scopus STANDARD search results may not contain full abstracts or complete author metadata. Use COMPLETE only when your entitlement permits it and document the view used.")
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
                "pagination": "offset",
                "view": self.view,
                "institution_token": bool(self.insttoken),
                "entitlement_dependent": True,
                "page_size": page_size,
            },
        )
