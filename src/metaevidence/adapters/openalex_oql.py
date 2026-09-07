from __future__ import annotations

from typing import Any

from .base import AdapterResult, utcnow
from .openalex import OpenAlexAdapter
from ..query import SearchQuery
from ..translators import Translation, translate


class OpenAlexOQLAdapter(OpenAlexAdapter):
    """OpenAlex OQL adapter for high-fidelity Boolean and fielded text retrieval.

    OQL is executed at the OpenAlex API root, not ``/works``. Cursor paging uses the
    standard response ``meta.next_cursor``. Long queries automatically switch to POST so
    they are not constrained by the HTTP request-line limit documented by OpenAlex.
    """

    source = "openalex_oql"
    ENDPOINT = "https://api.openalex.org/"
    GET_QUERY_LIMIT = 6000

    def compile(self, query: SearchQuery) -> Translation:
        return translate(query, "openalex_oql")

    def search(self, query: SearchQuery, *, max_records: int | None = 1000, page_size: int | None = None) -> AdapterResult:
        self.http.logs.clear()
        started = utcnow()
        translation = self.compile(query)
        page_size = min(max(1, page_size or 100), 100)
        cursor: str | None = "*"
        records = []
        pages = 0
        total: int | None = None
        warnings: list[str] = []
        cost_usd = 0.0
        first_x_query: dict[str, Any] | None = None
        used_post = False

        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            # Header auth keeps the key out of query strings and MetaEvidence request logs.
            headers["Authorization"] = f"Bearer {self.api_key}"

        while cursor:
            remaining = None if max_records is None else max_records - len(records)
            if remaining is not None and remaining <= 0:
                break
            take = page_size if remaining is None else min(page_size, remaining)

            if len(translation.translated.encode("utf-8")) <= self.GET_QUERY_LIMIT:
                params: dict[str, Any] = {
                    "oql": translation.translated,
                    "per-page": take,
                    "cursor": cursor,
                }
                if self.email and not self.api_key:
                    params["mailto"] = self.email
                response = self.http.get(self.ENDPOINT, params=params, headers=headers, cacheable=True)
            else:
                used_post = True
                body: dict[str, Any] = {
                    "oql": translation.translated,
                    "per_page": take,
                    "cursor": cursor,
                }
                response = self.http.post(self.ENDPOINT, headers={**headers, "Content-Type": "application/json"}, json_body=body)

            payload = response.json() or {}
            meta = payload.get("meta") or {}
            if total is None:
                try:
                    total = int(meta.get("count", 0))
                except (TypeError, ValueError):
                    total = None
            if first_x_query is None and isinstance(meta.get("x_query"), dict):
                first_x_query = meta.get("x_query")
            try:
                cost_usd += float(meta.get("cost_usd") or 0)
            except (TypeError, ValueError):
                pass

            batch = payload.get("results") or []
            retrieved_at = utcnow()
            start_rank = len(records) + 1
            records.extend(
                self._record(
                    item,
                    query=translation.translated,
                    retrieved_at=retrieved_at,
                    rank=start_rank + i,
                    source_name=self.source,
                )
                for i, item in enumerate(batch)
            )
            pages += 1
            next_cursor = meta.get("next_cursor")
            if not batch or not next_cursor or next_cursor == cursor:
                cursor = None
            else:
                cursor = str(next_cursor)
            if len(batch) < take:
                break

        if not self.api_key:
            warnings.append("OpenAlex API key not supplied; public access may have lower daily credit budgets.")
        if translation.requires_review:
            warnings.append("One or more canonical clauses were not represented exactly in OQL; inspect translation diagnostics before claiming exhaustive equivalence.")
        truncated = total is not None and len(records) < total and max_records is not None and len(records) >= max_records
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
                "api_variant": "oql",
                "cursor_pagination": True,
                "estimated_api_cost_usd": round(cost_usd, 6),
                "used_post_for_long_query": used_post,
                "x_query": first_x_query,
            },
        )
