from __future__ import annotations

import os
from typing import Any

from .base import AdapterResult, BaseAdapter, utcnow
from ..models import EvidenceRecord, SourceHit
from ..query import SearchQuery
from ..translators import Translation, translate


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("content", "value", "display_name", "full_name", "p"):
            if key in value:
                text = _as_text(value.get(key))
                if text:
                    return text
    return None


def _flatten_text(value: Any) -> str | None:
    parts: list[str] = []
    def walk(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            t = v.strip()
            if t:
                parts.append(t)
        elif isinstance(v, list):
            for item in v:
                walk(item)
        elif isinstance(v, dict):
            # Abstract text commonly lives under p; this also tolerates XML-to-JSON variants.
            if "p" in v:
                walk(v["p"])
            elif "content" in v:
                walk(v["content"])
            else:
                for item in v.values():
                    if isinstance(item, (str, list, dict)):
                        walk(item)
    walk(value)
    return " ".join(parts) or None


def _pick_title(summary: dict[str, Any], kind: str) -> str | None:
    titles = ((summary.get("titles") or {}).get("title"))
    candidates = _listify(titles)
    for item in candidates:
        if isinstance(item, dict) and str(item.get("type", "")).lower() == kind.lower():
            text = _as_text(item)
            if text:
                return text
    if kind == "item":
        for item in candidates:
            text = _as_text(item)
            if text:
                return text
    return None


def _authors(summary: dict[str, Any]) -> list[str]:
    out: list[str] = []
    names = ((summary.get("names") or {}).get("name"))
    for item in _listify(names):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "author")).lower()
        if role and role not in {"author", "authors"}:
            continue
        name = _as_text(item.get("display_name")) or _as_text(item.get("full_name")) or _as_text(item.get("wos_standard"))
        if name:
            out.append(name)
    return out


def _identifiers(record: dict[str, Any]) -> dict[str, str]:
    dynamic = record.get("dynamic_data") or {}
    cluster = dynamic.get("cluster_related") or {}
    ids = cluster.get("identifiers") or {}
    values: dict[str, str] = {}
    for item in _listify(ids.get("identifier")):
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type") or "").lower().replace(" ", "")
        value = _as_text(item.get("value")) or _as_text(item.get("content"))
        if typ and value:
            values[typ] = value
    return values


def _times_cited(record: dict[str, Any]) -> int | None:
    dynamic = record.get("dynamic_data") or {}
    tc = ((dynamic.get("citation_related") or {}).get("tc_list") or {}).get("silo_tc")
    candidates: list[tuple[str, int]] = []
    for item in _listify(tc):
        if not isinstance(item, dict):
            continue
        try:
            count = int(item.get("local_count"))
        except (TypeError, ValueError):
            continue
        candidates.append((str(item.get("coll_id") or ""), count))
    for coll, count in candidates:
        if coll.upper() == "WOS":
            return count
    return max((count for _, count in candidates), default=None)


class WebOfScienceExpandedAdapter(BaseAdapter):
    """Web of Science API Expanded adapter.

    Expanded is a paid, entitlement-dependent product distinct from Starter. ``FR`` full
    records count against the contractual full-record quota; ``SR`` returns a short record
    similar in depth to Starter and is preserved as a separate mode in the run metadata.
    """

    source = "web_of_science_expanded"
    ENDPOINT = "https://api.clarivate.com/api/wos"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        database: str = "WOS",
        edition: str | None = None,
        option_view: str = "FR",
        view_fields: str | None = None,
        lang: str = "en",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv("WOS_EXPANDED_API_KEY") or os.getenv("WOS_API_KEY") or os.getenv("WEB_OF_SCIENCE_API_KEY")
        self.database = database
        self.edition = edition
        self.option_view = option_view.upper()
        self.view_fields = view_fields
        self.lang = lang
        if self.option_view not in {"FR", "SR", "FS"}:
            raise ValueError("option_view must be FR, SR, or FS")
        if self.option_view == "FS" and not self.view_fields:
            raise ValueError("view_fields is required when option_view='FS'")

    def compile(self, query: SearchQuery) -> Translation:
        # The existing web_of_science compiler targets the Advanced Search grammar used by
        # API Expanded (TS, TI, AB, AU, SO, AD, AK, PY, NEAR/n).
        tx = translate(query, "web_of_science")
        return Translation(
            source="web_of_science_expanded",
            original=tx.original,
            translated=tx.translated,
            notes=tx.notes + ("Executed through Web of Science API Expanded.",),
            diagnostics=tuple(
                type(d)("web_of_science_expanded", d.canonical, d.translated, d.feature, d.status, d.note)
                for d in tx.diagnostics
            ),
            params=tx.params,
        )

    @staticmethod
    def _record(item: dict[str, Any], *, query: str, retrieved_at: str, rank: int, option_view: str) -> EvidenceRecord:
        static = item.get("static_data") or {}
        summary = static.get("summary") or {}
        pub_info = summary.get("pub_info") or {}
        full = static.get("fullrecord_metadata") or {}
        ids = _identifiers(item)
        uid = _as_text(item.get("UID"))

        abstract = None
        abstracts = full.get("abstracts") or {}
        abstract_obj = abstracts.get("abstract")
        if isinstance(abstract_obj, dict):
            abstract = _flatten_text((abstract_obj.get("abstract_text") or {}).get("p"))
        elif abstract_obj is not None:
            abstract = _flatten_text(abstract_obj)

        doi = ids.get("doi") or ids.get("doi.org")
        pmid = ids.get("pmid") or ids.get("pubmedid")
        pages = pub_info.get("page") or {}
        if isinstance(pages, dict):
            page_text = _as_text(pages.get("content"))
            if not page_text:
                begin, end = pages.get("begin"), pages.get("end")
                page_text = f"{begin}-{end}" if begin is not None and end is not None else _as_text(begin)
        else:
            page_text = _as_text(pages)

        try:
            year = int(pub_info.get("pubyear")) if pub_info.get("pubyear") is not None else None
        except (TypeError, ValueError):
            year = None

        return EvidenceRecord(
            title=_pick_title(summary, "item") or "[Untitled Web of Science Expanded record]",
            authors=_authors(summary),
            year=year,
            journal=_pick_title(summary, "source"),
            abstract=abstract,
            doi=doi,
            pmid=pmid,
            wos_ut=uid,
            source_hits=[SourceHit("web_of_science_expanded", source_id=uid or doi, query=query, retrieved_at=retrieved_at, rank=rank)],
            metadata={
                "api_variant": "expanded",
                "option_view": option_view,
                "publication_type": pub_info.get("pubtype"),
                "document_types": (summary.get("doctypes") or {}).get("doctype"),
                "volume": pub_info.get("vol"),
                "issue": pub_info.get("issue"),
                "pages": page_text,
                "cover_date": pub_info.get("coverdate"),
                "sort_date": pub_info.get("sortdate"),
                "keywords": (full.get("keywords") or {}).get("keyword"),
                "keywords_plus": ((static.get("item") or {}).get("keywords_plus") or {}).get("keyword"),
                "languages": (full.get("languages") or {}).get("language"),
                "addresses": (full.get("addresses") or {}).get("address_name"),
                "funding": full.get("fund_ack"),
                "reference_count": (full.get("refs") or {}).get("count"),
                "times_cited": _times_cited(item),
                "identifiers": ids,
            },
        )

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        if not self.api_key:
            raise ValueError("Web of Science API Expanded requires a paid-license API key. Set WOS_EXPANDED_API_KEY/WOS_API_KEY or pass api_key=...")
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 100), 100)
        records: list[EvidenceRecord] = []
        pages = 0
        first_record = 1
        total: int | None = None
        query_id: str | None = None
        warnings: list[str] = []
        headers = {"Accept": "application/json", "X-ApiKey": self.api_key}
        hit_first_record_cap = False

        while True:
            if max_records is not None and len(records) >= max_records:
                break
            if first_record > 100000:
                hit_first_record_cap = True
                break
            remaining = None if max_records is None else max_records - len(records)
            take = page_size if remaining is None else min(page_size, remaining)
            params: dict[str, Any] = {
                "databaseId": self.database,
                "lang": self.lang,
                "usrQuery": translation.translated,
                "count": take,
                "firstRecord": first_record,
                "optionView": self.option_view,
            }
            if self.edition:
                params["edition"] = self.edition
            if query.year_from is not None and query.year_to is not None:
                params["publishTimeSpan"] = f"{query.year_from}-01-01 {query.year_to}-12-31"
            if self.option_view == "FS" and self.view_fields:
                params["viewField"] = self.view_fields

            response = self.http.get(self.ENDPOINT, params=params, headers=headers, cacheable=False)
            payload = response.json() or {}
            qr = payload.get("QueryResult") or {}
            if total is None:
                try:
                    total = int(qr.get("RecordsFound"))
                except (TypeError, ValueError):
                    total = None
                query_id = _as_text(qr.get("QueryID"))
            rec_container = (((payload.get("Data") or {}).get("Records") or {}).get("records") or {})
            batch = _listify(rec_container.get("REC"))
            batch = [x for x in batch if isinstance(x, dict)]
            retrieved_at = utcnow()
            base_rank = first_record
            for i, item in enumerate(batch):
                records.append(self._record(item, query=translation.translated, retrieved_at=retrieved_at, rank=base_rank + i, option_view=self.option_view))
                if max_records is not None and len(records) >= max_records:
                    break
            pages += 1
            if not batch or len(batch) < take:
                break
            if total is not None and first_record - 1 + len(batch) >= total:
                break
            first_record += len(batch)

        if self.option_view == "FR":
            warnings.append("Web of Science Expanded optionView=FR retrieves full records and consumes the contractual full-record quota; report the entitlement/plan used.")
        elif self.option_view == "SR":
            warnings.append("Web of Science Expanded optionView=SR returns short records with Starter-like field depth and does not represent Expanded full-record metadata.")
        else:
            warnings.append("Web of Science Expanded optionView=FS returns only the requested custom fields; missing metadata may reflect viewField selection rather than source absence.")
        warnings.append("Web of Science Expanded access, covered databases/editions, throttling, and record quotas are entitlement-dependent.")
        if hit_first_record_cap:
            warnings.append("Web of Science Expanded firstRecord is capped at 100,000 by the API; retrieval stopped and the run is marked truncated.")

        capped_by_user = bool(total is not None and max_records is not None and len(records) >= max_records and len(records) < total)
        truncated = capped_by_user or hit_first_record_cap or bool(total is not None and total > 100000 and len(records) < total and first_record > 100000)
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
                "api_variant": "expanded",
                "database": self.database,
                "edition": self.edition,
                "option_view": self.option_view,
                "view_fields": self.view_fields,
                "pagination": "firstRecord_count",
                "page_size": page_size,
                "query_id": query_id,
                "entitlement_dependent": True,
                "full_record_quota_consuming": self.option_view == "FR",
                "first_record_limit": 100000,
            },
        )
