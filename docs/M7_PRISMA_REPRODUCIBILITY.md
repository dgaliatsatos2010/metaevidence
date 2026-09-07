# M7 — PRISMA 2020 and PRISMA-S reporting support

## Purpose

M7 turns MetaEvidence workflow state into auditable reporting artifacts for systematic reviews. It is deliberately a **reporting-support layer**, not a certification system. A software-generated flow cannot establish that a review is methodologically sound or fully compliant with PRISMA.

The implementation is aligned with:

- Page MJ, McKenzie JE, Bossuyt PM, et al. *The PRISMA 2020 statement: an updated guideline for reporting systematic reviews*. BMJ. 2021;372:n71. doi:10.1136/bmj.n71.
- Rethlefsen ML, Kirtley S, Waffenschmidt S, et al. *PRISMA-S: an extension to the PRISMA Statement for Reporting Literature Searches in Systematic Reviews*. Systematic Reviews. 2021;10:39. doi:10.1186/s13643-020-01542-z.

PRISMA 2020 flow templates and checklists are available from https://www.prisma-statement.org/.

## 1. Record/report/study distinction

M7 keeps the levels separate:

- **record**: citation-level search result used during title/abstract screening;
- **report**: a document sought/retrieved and assessed at full text;
- **study**: the underlying investigation represented by one or more reports.

This distinction is essential because M5 can link multiple included reports to one study. MetaEvidence therefore does not automatically set `studies_included = reports_included`.

## 2. `PrismaFlow`

`PrismaFlow` stores:

- records identified by each database;
- records identified by registries and other sources when supplied;
- duplicate removals;
- records removed by automation before screening;
- other pre-screening removals;
- records screened;
- records excluded at title/abstract stage;
- reports sought for retrieval;
- reports not retrieved;
- reports assessed for eligibility;
- full-text exclusion counts by reason;
- reports included;
- studies included when M5 linkage is available.

The object exposes arithmetic validation and can raise `PrismaAccountingError` in strict mode.

## 3. Why the counts are based on imported records

For database searches, PRISMA identification counts reflect records actually imported into the review workflow. If an adapter is truncated by API limits, the flow is explicitly marked with a warning. `total_available` from an API is retained separately in the search report and must not silently replace the actual imported count.

## 4. Full-text exclusions

M6 already requires a reason for a resolved full-text exclusion. M7 aggregates those reasons automatically.

`NOT_RETRIEVABLE` is treated separately from eligibility exclusions because PRISMA distinguishes reports not retrieved from reports retrieved and excluded after eligibility assessment.

## 5. Study counts

When included reports exist and a `StudyLinkageResult` is supplied, M7 counts distinct M5 study families containing included reports. If linkage is absent, `studies_included` remains unknown rather than being guessed.

## 6. PRISMA-S support matrix

The 16 PRISMA-S items are represented by a support matrix with states such as:

- `AUTOMATIC`
- `AUTOMATIC+USER`
- `PARTIAL`
- `USER_SUPPLIED`
- `USER_INPUT_REQUIRED`
- `NOT_APPLICABLE`
- `MISSING`

MetaEvidence automatically captures source/platform names, executed source-specific strategies, API execution dates, source-specific record counts, date limits, and the MetaEvidence deduplication description when available.

Items requiring human methodological context are not invented. These include, depending on the review:

- study registries not searched through a MetaEvidence adapter;
- targeted websites or browsing;
- backward/forward citation searching;
- contacts with authors/experts/manufacturers;
- other methods;
- justification for limits;
- published search filters;
- adapted prior work;
- search-update methods;
- search-strategy peer review.

## 7. Translation fidelity in the search report

For every database, the report stores both:

1. the canonical MetaEvidence query; and
2. the exact source-specific query generated/executed by the adapter.

It also stores translation `fidelity_score`, `loss_score`, `requires_review`, warnings, truncation state, execution timestamps, records retrieved, and source-reported total availability.

The translation score remains an engineering diagnostic until M8 validation; it is not presented as a validated PRISMA metric.

## 8. Reproducibility bundle

`write_prisma_bundle()` produces:

```text
prisma_bundle/
├── prisma_flow.json
├── prisma_flow.csv
├── prisma_flow.mmd
├── prisma_search_report.json
├── prisma_search_report.md
├── prisma_sources.csv
├── prisma_search_strategies.csv
├── prisma_s_support_matrix.csv
├── search_manifest.json
└── reproducibility_manifest.json
```

The Mermaid file is an editable MetaEvidence visualization of the flow counts; it is **not** represented as an official PRISMA flow-template reproduction.

The reproducibility manifest includes SHA-256 hashes, byte sizes, UTC generation time, Python version and runtime platform.

## 9. Example

```python
from metaevidence import (
    PrismaBuilder,
    PrismaSearchContext,
    write_prisma_bundle,
)

flow = PrismaBuilder.build_flow(
    search=search_run,
    deduplication=dedup,
    ledger=ledger,
    records=dedup.records,
    linkage=linked,
)

search_report = PrismaBuilder.build_search_report(
    search_run,
    deduplication=dedup,
    context=PrismaSearchContext(
        study_registries=["ClinicalTrials.gov"],
        peer_review="Search strategy peer reviewed using PRESS.",
        limits_and_restrictions="Publication years 2020-2026 were used as prespecified in the protocol.",
    ),
)

write_prisma_bundle(
    "prisma_bundle",
    flow=flow,
    search_report=search_report,
    search=search_run,
)
```

## 10. Safety and non-claims

M7 does not claim:

- that MetaEvidence makes a review PRISMA-compliant;
- that a search is comprehensive merely because multiple databases were searched;
- that an API-reported total equals the number actually imported;
- that `reports_included` necessarily equals `studies_included`;
- that missing human reporting items can be inferred safely;
- that the current translation fidelity score is clinically or methodologically validated.

## 11. M8 validation hooks

M7 creates auditable outputs needed for M8, including database-specific counts, source-specific queries, translation diagnostics, duplicate-removal counts, review queues, study-family accounting, and screening exclusions. These artifacts will support query-recall benchmarking, deduplication/study-linkage error analysis, reproducibility studies, and ablation experiments.
