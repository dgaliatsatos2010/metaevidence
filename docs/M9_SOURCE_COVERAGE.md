# M9 source-coverage expansion — CORE, Scopus, Web of Science Starter/Expanded, OpenAlex OQL

MetaEvidence v0.9.2-dev provides seven scholarly source families with nine adapter modes while retaining a strict distinction between **source coverage** and **exhaustive evidence coverage**.

## Live sources

| Source | Adapter | Authentication | Pagination | Important reporting limitation |
|---|---|---|---|---|
| PubMed | `PubMedAdapter` | email recommended; API key optional | NCBI History + EFetch | ordinary PubMed ESearch retrieval has a 10,000-UID ceiling |
| OpenAlex classic | `OpenAlexAdapter` | API key supported | cursor | classic search field semantics can differ from the canonical query |
| OpenAlex OQL | `OpenAlexOQLAdapter` | API key supported | cursor; POST for long queries | direct keyword fields exclude canonical keyword-only scope unless separately resolved; diagnostics remain required |
| Crossref | `CrossrefAdapter` | mailto recommended; Plus token optional | cursor | `query.bibliographic` is relevance-oriented, not a substitute for specialist Boolean databases |
| Europe PMC | `EuropePMCAdapter` | no MetaEvidence credential required | cursorMark | indexing/synonym behavior differs from PubMed |
| CORE | `COREAdapter` | `CORE_API_KEY` recommended | offset | v0.9.1 applies publication-year bounds locally and reports the source total before that local filter |
| Scopus | `ScopusAdapter` | `SCOPUS_API_KEY`; optional institutional token | start/count | accessible metadata, result depth and views depend on Elsevier entitlements |
| Web of Science Starter | `WebOfScienceStarterAdapter` | `WOS_API_KEY` | page/limit | Starter is basic metadata and is **not** the paid API Expanded/full-record service |
| Web of Science Expanded | `WebOfScienceExpandedAdapter` | `WOS_EXPANDED_API_KEY` or entitled `WOS_API_KEY` | firstRecord/count | paid, quota/edition dependent; `FR` consumes full-record quota |

## Credentials

No credential is bundled in the repository. Environment variables are preferred:

```bash
CORE_API_KEY=...
SCOPUS_API_KEY=...
SCOPUS_INSTTOKEN=...       # optional / entitlement dependent
WOS_API_KEY=...
WOS_EXPANDED_API_KEY=...    # paid Expanded entitlement
```

Programmatic injection is also supported without changing the canonical query:

```python
run = search.run(
    query,
    sources=("core", "scopus", "web_of_science", "openalex_oql", "web_of_science_expanded"),
    adapter_options={
        "core": {"api_key": "..."},
        "scopus": {"api_key": "...", "view": "STANDARD"},
        "web_of_science": {"api_key": "..."},
        "web_of_science_expanded": {"api_key": "...", "option_view": "FR"},
    },
)
```

Credentials are placed in HTTP headers and are not serialized into `RequestLogEntry` or raw-audit metadata.

## CORE policy in v0.9.1

The CORE adapter normalizes title, authors, abstract, DOI, year, journal, document type and open-access/full-text links where returned by the API. The canonical query translator supports direct `title`, `abstract` and `authors` scoping plus an expanded title/abstract mapping. Other field scopes are explicitly degraded and audited.

To avoid silently assuming equivalence with a changing source query-dialect range syntax, publication-year bounds are post-filtered locally in this milestone. Therefore:

- `total_available` is the source total for the unfiltered query;
- `metadata["total_available_scope"]` records this fact;
- additional pages may be fetched to satisfy a narrow in-range `max_records` target;
- a warning is always emitted when local date filtering is active.

A future adapter may promote a documented server-side range syntax after live conformance testing.

## Scopus policy in v0.9.1

The Scopus adapter uses the official Scopus Search API and its existing MetaEvidence translator. Publication years are carried in the translated Boolean query through `PUBYEAR` bounds. The adapter uses `start`/`count`, defaults to the conservative `STANDARD` view and allows `COMPLETE` only when explicitly requested.

MetaEvidence does not treat an API key as proof of full Scopus entitlement. The result manifest therefore records:

- requested view;
- presence of institutional token;
- `entitlement_dependent=True`;
- exact translated query;
- retrieved count, source-reported total and truncation state.

## Web of Science Starter policy in v0.9.1

The live Web of Science adapter targets **Starter API v2** rather than pretending Starter is equivalent to Web of Science API Expanded.

A separate `web_of_science_starter` compiler is used internally. Starter-safe mappings include:

- title → `TI`;
- author → `AU`;
- source title → `SO`;
- default topic / abstract / keyword intent → `TS` with an approximation diagnostic;
- affiliation intent → `OG` with an approximation diagnostic.

For a fully bounded year range the adapter sends `publishTimeSpan`. One-sided year constraints are post-filtered locally and flagged. Starter records are normalized without inventing an abstract when the endpoint does not provide one.

## Why these adapters are not enabled in the default source tuple

The default `EvidenceSearch.run()` source tuple remains the four sources that do not require institutional/commercial credentials in the MetaEvidence workflow. Scopus and Web of Science must be explicitly requested because credentials and entitlements are user/institution specific. CORE is also explicit so that source expansion does not unexpectedly change network volume or rate-limit behavior for existing users. OpenAlex OQL and Web of Science Expanded are opt-in modes because they change query semantics or entitlement/quota behavior.

## Exhaustiveness non-claim

Adding seven live sources does **not** make a search exhaustive by definition. A systematic review can still miss studies because of:

- database coverage;
- indexing delays;
- source-specific query semantics;
- subscription/API entitlements;
- API result-depth limits;
- incomplete metadata;
- unavailable grey literature;
- citation searching and other discovery methods not represented by database APIs.

MetaEvidence's scientific objective is to make those differences observable, reproducible and auditable rather than to hide them behind a single `search_all()` claim.


## OpenAlex OQL policy in v0.9.2

OQL is exposed as `openalex_oql`, not as a silent replacement for `openalex`. Canonical title, abstract, title/abstract and affiliation text fields map to OQL text-search fields; author maps to byline with an approximation diagnostic. Free-text journal names require source-entity resolution for exact semantics and therefore remain review-required/unsupported rather than being presented as exact. Canonical default title+abstract+keywords scope is marked as an approximation because this OQL mode uses direct title/abstract text search and does not pretend keyword-only matches are identical.

The adapter executes at the OpenAlex API root. Queries above the conservative GET threshold use JSON POST to avoid request-line limits, and `meta.x_query` is retained in adapter metadata for round-trip inspection.

## Web of Science API Expanded policy in v0.9.2

Expanded is a separate paid product from Starter. The adapter records the database, optional edition, query ID, view mode, page size, quota-consuming status and entitlement dependence. `FR` normalizes rich full-record fields when present; `SR` intentionally has Starter-like field depth; `FS` only returns selected fields. The API's `firstRecord` ceiling is treated as a hard retrieval limitation and produces an explicit truncated warning rather than an exhaustiveness claim.
