# M3 — Live source adapters

MetaEvidence v0.3-dev introduced the auditable execution layer for four open/public scholarly APIs; v0.9.1-dev extends the same architecture to CORE, Scopus and Web of Science Starter; v0.9.2 adds OpenAlex OQL and Web of Science API Expanded as separate opt-in modes:

- PubMed through NCBI E-utilities;
- OpenAlex Works API;
- Crossref Works REST API;
- Europe PMC REST API;
- CORE v3 Works search;
- Elsevier Scopus Search API;
- Clarivate Web of Science Starter API v2.

## Design goals

1. Preserve the canonical query and the exact translated query sent to each source.
2. Normalize heterogeneous API responses into `EvidenceRecord` without discarding source IDs.
3. Record pagination, request status, response SHA-256, rate-limit headers, timestamps, warnings, and truncation.
4. Retry transient HTTP failures (`429`, `500`, `502`, `503`, `504`) using exponential backoff.
5. Never write API keys or bearer tokens into request logs/audit metadata.
6. Keep raw-response archival and response caching opt-in.
7. Isolate source failures during multi-database searches so successful sources remain usable and the failure is recorded in the manifest.

## Source behavior

### PubMed

The adapter uses `ESearch` with `usehistory=y`, then retrieves batches through `EFetch`. This minimizes request counts and preserves NCBI's query translation in execution metadata. MetaEvidence explicitly marks searches with more than 10,000 PubMed matches as truncated because PubMed/PMC ESearch does not expose arbitrary result sets above this threshold through ordinary ESearch retrieval. Large exhaustive reviews should be segmented by date or use an appropriate NCBI bulk/EDirect workflow.

Recommended environment variables:

```bash
NCBI_EMAIL=researcher@example.org
NCBI_API_KEY=...
```

### OpenAlex

The adapter uses `/works`, cursor paging (`cursor=*` followed by `meta.next_cursor`), `per_page<=100`, and publication-date filters. An API key is supported through `OPENALEX_API_KEY` but is not hard-coded or required by MetaEvidence.

```bash
OPENALEX_API_KEY=...
OPENALEX_EMAIL=researcher@example.org
```

### Crossref

The adapter uses `/works`, `query.bibliographic`, publication-date filters, and cursor pagination. Crossref is treated as a relevance-oriented metadata search rather than as a guaranteed Boolean-equivalent substitute for specialist systematic-review databases. When canonical query semantics are approximated, an execution warning is retained.

```bash
CROSSREF_MAILTO=researcher@example.org
CROSSREF_API_KEY=...  # optional Metadata Plus token
```

### Europe PMC

The adapter uses `/search` with `resultType=core`, JSON output, page sizes up to 1000, and `cursorMark` / `nextCursorMark` deep paging. Optional source-side synonym expansion can be enabled on the adapter.

```bash
EUROPE_PMC_EMAIL=researcher@example.org
```

## Reproducibility and audit

Each HTTP request creates a `RequestLogEntry` containing:

- source;
- endpoint;
- redacted parameters;
- HTTP status;
- attempt number;
- elapsed time;
- UTC retrieval timestamp;
- SHA-256 digest of the response body;
- selected rate-limit headers;
- cache-hit flag.

To preserve response bodies locally for audit/reanalysis, opt in to `audit_dir`. Bodies are gzip-compressed and content-addressed by SHA-256. Users remain responsible for source licences, terms, institutional policies, and copyright restrictions governing retention and redistribution of metadata/full text.

## Multi-source execution

```python
from metaevidence import EvidenceSearch, SearchQuery

query = SearchQuery(
    '("bayesian network" OR "bayesian networks") AND diabetes',
    year_from=2015,
    year_to=2026,
)

search = EvidenceSearch(
    cache_dir=".metaevidence-cache",
    audit_dir=".metaevidence-audit",
)

run = search.run(
    query,
    sources=("pubmed", "openalex", "crossref", "europe_pmc"),
    max_records_per_source=1000,
)

print(run.total_retrieved)
print(run.failures)
run.manifest.write_json("search_manifest.json")
```

The `max_records_per_source` parameter is deliberately explicit. A pilot run can therefore be bounded, while a production review can request a larger or source-specific exhaustive workflow.

## What the live-source layer does not claim

- CORE, Scopus and Web of Science Starter are implemented as of v0.9.1; OpenAlex OQL and Web of Science API Expanded are implemented as distinct opt-in modes in v0.9.2.
- It does not claim equivalence between relevance search and exact Boolean database semantics.
- It does not guarantee exhaustive retrieval beyond source API limitations.
- It does not yet provide calibrated probabilistic deduplication or study-level publication linkage.
- It does not download paywalled full text.


## v0.9.1 source expansion

Detailed credential, entitlement, date-filter and query-semantics behavior for CORE, Scopus and Web of Science Starter is documented in `M9_SOURCE_COVERAGE.md`. These sources are opt-in and are not silently added to the default network call.


## v0.9.2 advanced execution modes

`OpenAlexOQLAdapter` executes OQL at `https://api.openalex.org/`, retains `meta.x_query`, uses cursor paging and switches to POST for long queries. It is separate from the backward-compatible classic `/works?search=...` adapter so benchmark studies can compare translation modes explicitly.

`WebOfScienceExpandedAdapter` executes the paid Expanded search API, caps page size at 100, records the API `QueryID`, respects the documented `firstRecord` ceiling, and exposes `FR`, `SR`, and `FS` modes. `FR` runs are flagged as full-record-quota consuming.
