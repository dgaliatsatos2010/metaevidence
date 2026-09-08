# MetaEvidence

**Status:** v1.0.0 stable public release

MetaEvidence is an open-source Python framework for reproducible, cross-database scholarly evidence retrieval for systematic reviews and meta-analysis.

## Core design principle

A systematic-review search is treated as a **versioned computational experiment**, not as a transient search-box action. MetaEvidence exposes semantic differences, retrieval limitations, uncertainty, and provenance instead of silently pretending that one query or one duplicate-removal rule is universally exact.

The framework is designed around seven linked contributions:

1. **Canonical Search Representation (CSR)** — source-neutral query language and AST;
2. **Auditable Query Translation Graph (AQTG)** — clause-level translation diagnostics;
3. **Evidence Provenance Graph (EPG)** — normalized records retaining every source hit;
4. **Confidence-aware Multi-stage Deduplication (CMD)** — publication-level merge/review decisions with uncertainty and audit trails;
5. **Study-level Publication Linkage (SPL)** — uncertainty-aware grouping of distinct reports from one underlying study;
6. **Search Reproducibility Manifest (SRM)** — machine-readable run metadata;
7. **PRISMA-oriented accounting** — planned identification/deduplication exports without claiming that software alone makes a review PRISMA-compliant.




## New in v0.9.9-dev — frozen external-validation integrity gate

v0.9.9 is a **validation-infrastructure-only** checkpoint. The publication-deduplication engine is unchanged from the frozen v0.9.4 implementation and remains byte-identical to v0.9.8 (`dedup.py` SHA-256 `3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50`).

Added safeguards include:

- `benchmarks/frozen_validation_lock.json`, which cryptographically locks method-critical files, benchmark manifests and execution-layer files;
- `metaevidence verify-validation-lock ...`, which aborts before external scoring if a locked file has drifted;
- a GitHub Actions Beller matrix generated directly from the pinned benchmark manifest rather than from a second hard-coded dataset list;
- re-verification of the frozen lock in guard, execution and reporting jobs;
- per-run `validation_run_manifest.json` provenance with result-file SHA-256 hashes and GitHub/runtime metadata;
- 90-day results-only artifact retention and a workflow-page manuscript-oriented summary; and
- a strict rule that no feature, weight, threshold, blocking rule, retention policy, gold label or held-out role may be changed using external outcomes.

Third-party raw Beller XML and ASySD CSV files remain download-at-run-time inputs and are not distributed in the source package, wheel or GitHub result artifacts. See `docs/FROZEN_EXTERNAL_VALIDATION.md`.

## New in v0.9.8-dev — publication-oriented statistical reporting

v0.9.8 adds a downstream statistical-reporting layer for **already-computed blind external-validation results**. It does not alter matching features, deduplication thresholds, retention rules, gold labels, or the frozen v0.9.4 deduplication engine.

Implemented outputs include:

- Wilson confidence intervals for dataset-level and pooled micro sensitivity, specificity, precision, and accuracy;
- pooled micro confusion-matrix summaries across benchmark datasets;
- unweighted review-level macro sensitivity, specificity, precision, and F1;
- deterministic review-level percentile-bootstrap confidence intervals for macro estimates;
- explicit safety counts/rates for false unique removals and missed duplicates;
- manuscript-ready CSV and Markdown outputs generated directly from blind engine-quality result bundles;
- `metaevidence summarize-removal-results ...` CLI support; and
- automatic statistical summary artifacts in the manual external-validation GitHub Actions workflow.

The review/dataset is the bootstrap resampling unit. Related citation records are never treated as independent bootstrap units for macro uncertainty. Gold-preferred reproduction outputs are excluded from the primary statistical summary whenever blind outputs are available. See `docs/M8_STATISTICAL_REPORTING.md`.

## New in v0.9.7-dev — GitHub-executable frozen validation

v0.9.7 adds a manual-only GitHub Actions external-validation workflow without changing the frozen deduplication engine. The five pinned IEBH/Beller EndNote corpora can run in a dataset matrix, and the ASySD development/calibration or explicitly unlocked held-out roles can run on a networked GitHub-hosted runner. Raw third-party benchmark files are never uploaded as artifacts; only results, hashes and provenance are retained.

The workflow supports single-file EndNote execution through `--file`, allowing the large diabetes corpus to run independently from smaller datasets. See `docs/GITHUB_EXTERNAL_VALIDATION.md`.

## New in v0.9.2-dev — OpenAlex OQL and Web of Science API Expanded

v0.9.2 adds two advanced, opt-in execution modes without removing the conservative adapters already used by existing workflows:

- **OpenAlex OQL** (`OpenAlexOQLAdapter`, source `openalex_oql`) executes the new OpenAlex Query Language at the API root, preserving nested Boolean fielded text queries, native `within N (...)` proximity, quoted wildcards and year comparisons more faithfully than classic URL search. Long queries automatically use POST. The response `meta.x_query` is retained for audit/round-trip inspection.
- **Web of Science API Expanded** (`WebOfScienceExpandedAdapter`, source `web_of_science_expanded`) uses the official paid Expanded endpoint with `firstRecord`/`count` pagination and explicit `FR`/`SR`/`FS` view modes. Full-record metadata such as abstracts, addresses, funding, identifiers, references and citation counts are normalized when returned by the user's entitlement.
- Clarivate quota headers are now captured by the HTTP audit layer. `FR` is explicitly marked as quota-consuming; Starter and Expanded remain separate products/modes.
- Screening revision order is now defined by append order rather than timestamp text, preventing imported clock/time-zone differences from resurrecting an older reviewer decision.

The default search tuple remains conservative and does not silently opt users into commercial or higher-cost modes.

## New in v0.7-dev — PRISMA 2020 / PRISMA-S reporting support

v0.7 converts the search, deduplication, study-linkage and screening state into auditable reporting artifacts while explicitly avoiding an automatic “PRISMA compliant” claim.

Implemented capabilities:

- database-by-database identification counts;
- optional registry and other-source counts;
- separate record, report and underlying-study accounting;
- duplicate, automation and other pre-screening removal counts;
- title/abstract screening and exclusion counts;
- full-text retrieval, non-retrieval and eligibility accounting;
- full-text exclusion reasons from the M6 screening ledger;
- included-study counts from M5 study families;
- arithmetic consistency checks and strict validation;
- source/platform, exact executed strategy, search date, retrieval count and truncation reporting;
- 16-item PRISMA-S support matrix separating automatic capture from required human input;
- JSON/CSV/Markdown reporting exports;
- editable Mermaid flow source;
- SHA-256 reproducibility bundle manifest with runtime metadata.

```python
from metaevidence import PrismaBuilder, PrismaSearchContext, write_prisma_bundle

flow = PrismaBuilder.build_flow(
    search=run,
    deduplication=dedup,
    ledger=ledger,
    records=dedup.records,
    linkage=linked,
)

report = PrismaBuilder.build_search_report(
    run,
    deduplication=dedup,
    context=PrismaSearchContext(
        study_registries=["ClinicalTrials.gov"],
        peer_review="Document the actual search peer-review process here, if performed.",
    ),
)

write_prisma_bundle("prisma_bundle", flow=flow, search_report=report, search=run)
```

**Scientific caution:** M7 supports PRISMA 2020 and PRISMA-S reporting; it does not certify compliance or search quality. Human methodological details are marked as required rather than inferred.


## New in v0.6-dev — screening interoperability and audit

v0.6 adds the handoff from evidence retrieval/linkage to reproducible screening workflows. It includes:

- stable record IDs;
- append-only title/abstract and full-text screening decisions;
- editable exclusion-reason codebook and required reasons for full-text exclusions;
- independent double screening, disagreement detection and adjudication;
- percent agreement and Cohen's kappa;
- CSV, JSONL, RIS and BibTeX interchange;
- ASReview-compatible CSV and RIS label conventions;
- conservative handling of `MAYBE` and unresolved disagreement (left unlabeled rather than coerced);
- screening bundles that include study-family/double-counting outputs;
- SHA-256 manifest for exact artifact identification.

```python
from metaevidence import (
    ScreeningDecision, ScreeningLedger, ScreeningStage,
    write_screening_bundle,
)

ledger = ScreeningLedger()
ledger.add(records[0], ScreeningDecision.INCLUDE, reviewer="reviewer-A")
ledger.add(records[0], ScreeningDecision.EXCLUDE, reviewer="reviewer-B")

ledger.adjudicate(
    records[0],
    ScreeningDecision.INCLUDE,
    stage=ScreeningStage.TITLE_ABSTRACT,
    reviewer="adjudicator",
)

write_screening_bundle(records, "review_bundle", ledger=ledger, linkage=linked)
```

ASReview interoperability follows its public tabular/RIS field conventions. This does not mean MetaEvidence depends on or is endorsed by ASReview, and broader real-world round-trip validation remains planned.


## New in v0.5-dev — study-level publication linkage

v0.5 separates **publication identity** from **underlying-study identity**. A protocol, conference abstract, preprint, primary results paper, subgroup analysis and follow-up may all be distinct publications from one study. M5 links them without deleting them.

Implemented capabilities:

- normalized extraction of NCT, ISRCTN, ACTRN, DRKS, ChiCTR, UMIN, TCTR, IRCT, NTR, CTRI and EudraCT/EUCTR identifiers;
- publication-role classification;
- study-link features for registry IDs, acronyms, investigators, year, sample size, country/site, intervention/exposure, population and recruitment dates;
- separate provisional `study_probability` and M4 `publication_probability`;
- `SAME_STUDY`, `REVIEW`, `DIFFERENT_STUDY`, and `DUPLICATE_PUBLICATION`;
- review-article registry-mention safeguards;
- multi-registry ambiguity protection;
- transitive cluster-consistency checks;
- stable `STUDY-...` family identifiers;
- double-counting risk flags for meta-analysis;
- JSON/CSV family, edge, review-queue and risk exports;
- labelled-pair benchmark and threshold optimization.

```python
from metaevidence import EvidenceRecord, StudyLinkageEngine

records = [
    EvidenceRecord(
        title="ABC trial protocol",
        abstract="Registered as NCT01234567",
        metadata={"report_role": "PROTOCOL"},
    ),
    EvidenceRecord(
        title="Primary outcomes of ABC",
        abstract="ClinicalTrials.gov NCT01234567",
        metadata={"report_role": "PRIMARY_RESULTS"},
    ),
    EvidenceRecord(
        title="Five-year follow-up of ABC",
        abstract="NCT01234567",
        metadata={"report_role": "FOLLOW_UP"},
    ),
]

linked = StudyLinkageEngine().link(records)

for family in linked.families:
    print(family.study_id, family.member_indices, family.publication_roles)

for warning in linked.double_counting_risks:
    print(warning.severity, warning.reason)
```

**Scientific caution:** the M5 study-link score is still an expert-weighted engineering model. It is not yet an externally calibrated probability and no superiority claim is made before independent validation.

## v0.4-dev — confidence-aware publication deduplication

v0.4 adds an explainable publication-level record-linkage engine with:

- DOI/PMID/WoS UT/Scopus EID/OpenAlex identity evidence;
- conflict-aware safety rules;
- title character and token similarity;
- author, year, journal, volume, issue, and page evidence;
- publication-form conflict detection;
- provisional match probabilities;
- `AUTO_MERGE`, `REVIEW`, and `KEEP_SEPARATE` decisions;
- a human review queue;
- provenance-preserving cluster merging;
- deterministic blocking for larger libraries;
- labelled-pair benchmarking;
- precision/recall/F1/specificity/false-merge metrics;
- Brier score and expected calibration error;
- threshold tuning subject to a precision floor;
- optional Platt calibration.

**Scientific caution:** the default v0.4 match probability is an expert-weighted engineering score, not yet an empirically calibrated probability. Calibration and external benchmark validation are planned before any superiority claim.

### Example

```python
from metaevidence import ConfidenceDeduplicationEngine, EvidenceRecord

records = [
    EvidenceRecord(
        title="Machine learning prediction of diabetes outcomes",
        authors=["Smith J"],
        year=2024,
        journal="Diabetes Care",
    ),
    EvidenceRecord(
        title="Machine-learning prediction of diabetes outcome",
        authors=["J Smith"],
        year=2024,
        journal="Diabetes Care",
    ),
]

result = ConfidenceDeduplicationEngine().deduplicate(records)

for pair in result.assessments:
    print(pair.probability, pair.decision.value)
    print(*pair.explanation, sep="\n")

print("unique publications:", len(result.records))
print("manual-review pairs:", len(result.review_queue))
```

A preprint and a journal article are intentionally not collapsed simply because title/authors/year are similar. M5 can instead link them as distinct reports from one underlying study when the evidence supports that relationship.

## Live database execution (v0.3+, expanded through v0.9.2)

The package has live adapters for:

- **PubMed / NCBI E-utilities** — History-backed search plus batched EFetch;
- **OpenAlex classic** — cursor-paged Works search;
- **OpenAlex OQL** — opt-in high-fidelity OQL execution with cursor pagination and POST fallback for long queries;
- **Crossref** — cursor-paged Works metadata retrieval;
- **Europe PMC** — `core` metadata with cursorMark pagination;
- **CORE** — open-access works metadata/full-text links with offset pagination;
- **Scopus** — official Elsevier Scopus Search API using user/institution credentials;
- **Web of Science Starter** — Clarivate Starter API v2 basic bibliographic metadata;
- **Web of Science API Expanded** — opt-in paid full/short/custom record modes with entitlement-aware metadata and quota reporting.

The common HTTP layer adds:

- transient-error retries and exponential backoff;
- request/response SHA-256 audit records;
- secret redaction in logs;
- optional local response cache;
- optional gzip raw-response audit archive;
- rate-limit header capture;
- source failure isolation in multi-database runs;
- explicit `truncated` and warning states.

## Installation during development

```bash
pip install -e .
```

Current runtime dependency: `httpx`.

## Live multi-database example

```python
from metaevidence import EvidenceSearch, SearchQuery

query = SearchQuery(
    '(mesh:"Diabetes Mellitus, Type 2" OR "type 2 diabetes") '
    'AND ("machine learning" NEAR/5 predict*)',
    year_from=2018,
    year_to=2026,
)

search = EvidenceSearch(
    cache_dir=".metaevidence-cache",
    audit_dir=".metaevidence-audit",
)

run = search.run(
    query,
    sources=(
        "pubmed", "openalex", "crossref", "europe_pmc",
        "core", "scopus", "web_of_science",
    ),
    max_records_per_source=1000,
    adapter_options={
        "scopus": {"view": "STANDARD"},
    },
)

run.manifest.write_json("search_manifest.json")
```

## Recommended credentials / identification

Credentials are read from the environment and are never distributed with the package:

```bash
NCBI_EMAIL=researcher@example.org
NCBI_API_KEY=...
OPENALEX_API_KEY=...
OPENALEX_EMAIL=researcher@example.org
CROSSREF_MAILTO=researcher@example.org
CROSSREF_API_KEY=...        # optional Crossref Metadata Plus
EUROPE_PMC_EMAIL=researcher@example.org
CORE_API_KEY=...
SCOPUS_API_KEY=...
SCOPUS_INSTTOKEN=...        # optional / entitlement dependent
WOS_API_KEY=...
WOS_EXPANDED_API_KEY=...    # paid Web of Science Expanded entitlement
```

Do **not** commit `.env`, API keys, bearer tokens, institutional credentials, or raw licensed datasets to GitHub.

Advanced opt-in retrieval modes can be requested explicitly:

```python
advanced = search.run(
    query,
    sources=("openalex_oql", "web_of_science_expanded"),
    adapter_options={
        "web_of_science_expanded": {"option_view": "FR"},
    },
)
```

`openalex_oql` uses native OQL semantics and switches to POST for long requests. `web_of_science_expanded` is entitlement-dependent; `FR` consumes the Clarivate full-record quota and is never silently substituted for Starter.

## Canonical query language

The source-neutral language supports:

- `AND`, `OR`, `NOT` with precedence and parentheses;
- quoted phrases;
- `*` and `?` wildcards;
- fields including `title:`, `abstract:`, `tiab:`, `author:`, `journal:`;
- `mesh:` concepts;
- proximity such as `"machine learning" NEAR/5 predict*`;
- PICO and PECO builders;
- normalized round-trip rendering;
- translation states `exact`, `expanded`, `approximated`, `unsupported`, `review_required`;
- numeric prototype `fidelity_score` / `loss_score` diagnostics.

The translation fidelity score is currently an engineering diagnostic, **not yet a validated scientific metric**.

## Provenance-preserving records

All adapters normalize their source schema into `EvidenceRecord`, while preserving identifiers such as DOI, PMID and OpenAlex ID plus one or more `SourceHit` objects. During deduplication, source hits are unioned rather than discarded, and conflicting metadata are retained in `metadata["metaevidence_conflicts"]`.

## Current tests

v0.9.2-dev includes **116 tests** covering the prior pipeline plus OpenAlex OQL, Web of Science Expanded, POST audit handling and append-order screening resolution. The regression suite includes tests for:

- data model and DOI normalization;
- canonical query grammar and translators;
- retries, secret redaction and multi-source failure isolation;
- PubMed/OpenAlex/Crossref/Europe PMC/CORE/Scopus/Web of Science Starter adapters;
- exact-ID and fuzzy bibliographic deduplication;
- conflicting DOI safety rules;
- publication-form separation;
- human-review triage;
- large-library blocking;
- provenance-preserving merging;
- benchmark metrics;
- threshold optimization;
- calibration utilities;
- registry-ID extraction and publication-role classification;
- same-study vs duplicate-publication decisions;
- review and multi-registry safeguards;
- transitive cluster-consistency protection;
- stable study-family identifiers;
- double-counting warnings;
- study-linkage benchmark/export utilities;
- stable screening record IDs;
- full-text exclusion-reason safeguards;
- double-screening disagreement and adjudication;
- reviewer agreement/kappa;
- CSV/RIS/JSONL/BibTeX interchange;
- ASReview CSV/RIS label mapping and round trips;
- screening bundle checksums;
- PRISMA record/report/study accounting;
- full-text exclusion and non-retrieval separation;
- PRISMA-S support-matrix generation;
- PRISMA bundle SHA-256 manifests and flow consistency validation.
- retrieval-set query-translation benchmark metrics;
- M4/M5 feature ablation;
- deterministic metadata-missingness stress testing;
- scalability timing/candidate-pair instrumentation;
- blocking recall and pair-reduction measurement for large-corpus candidate generation;
- bootstrap proportion confidence intervals;
- benchmark bundle CSV/JSON exports with SHA-256 manifests.

## Scientific benchmarking and external validation (M8)

MetaEvidence now includes a benchmark harness for evaluating the research claims rather than relying on unit tests alone:

```python
from metaevidence import (
    DeduplicationAblationBenchmark,
    MetadataStressBenchmark,
    synthetic_deduplication_dataset,
)

records, labels = synthetic_deduplication_dataset(30)

ablation = DeduplicationAblationBenchmark().evaluate(
    records, labels, features=["doi_exact", "title_similarity", "author_similarity"]
)

stress = MetadataStressBenchmark.evaluate_deduplication(
    records, labels, missing_rates=[0, 0.25, 0.5], repeats=3
)
```

Synthetic benchmark generators are **engineering QA only**. Real scientific performance claims require the external gold-standard protocols in `docs/M8_SCIENTIFIC_BENCHMARKING.md` and `docs/M8_EXTERNAL_VALIDATION.md`. Query translation is evaluated by retrieved-record overlap against expert target-database searches, not by string similarity.

### External gold-standard deduplication

The frozen manifest declares the semantics of each gold standard before outcomes are
inspected. ASySD 2023 uses exact record-removal labels (`Unique`/`Duplicate`), while
partition-based corpora use duplicate/publication group identifiers.

```python
from metaevidence import (
    load_external_dataset_specifications,
    load_external_gold_dataset,
    RemovalLabelBenchmark,
)

spec = next(
    s for s in load_external_dataset_specifications("benchmarks/external_benchmark_manifest.json")
    if s.id == "asysd_diabetes"
)
ds = load_external_gold_dataset(
    "external_validation_data/asysd_2023/Diabetes_duplicates_labelled.csv",
    spec,
    strict=True,
)
# Primary external estimate: deployable retention, blind to gold labels.
result = RemovalLabelBenchmark.evaluate(ds, retention_mode="engine_quality")

# Secondary reproduction only: the same predicted clusters, but a gold-Unique
# record is preferentially retained to mirror ASySD 2023's validation setting.
comparison = RemovalLabelBenchmark.compare_retention_modes(ds)
assert comparison.reproduction_uses_gold_labels is True
```

Why both? The official ASySD validation code calls `dedup_citations(...,
keep_label="Unique")`. That uses the reference label to choose the retained member of
an already-detected cluster. MetaEvidence therefore reports blind/deployable metrics as
the primary result and labels gold-preferred retention as a reproduction-only secondary
analysis. If the source CSV also contains a verified `duplicate_id`/group field, the
external runner additionally emits a representative-insensitive partition benchmark.

To obtain the five ASySD files reproducibly without committing them to the package:

```bash
python benchmarks/fetch_asysd_validation.py
python benchmarks/run_external_validation.py --roles development
```

The runner has an explicit held-out gate: `held_out_test` cannot be executed unless
`--allow-held-out` is supplied. The source SHA-256 is stored with every benchmark run,
and the third-party bibliographic records remain outside the public package/repository.


## Release engineering (M9 preparation)

The v0.9.4 development tree includes GitHub Actions CI, clean wheel-build/install validation, a protected PyPI Trusted Publishing workflow template, `CITATION.cff`, contribution/security policies, changelog, an explicit public-release checklist, seven source families and nine adapter modes (including OpenAlex classic/OQL and Web of Science Starter/Expanded). Commercial/entitlement-based modes remain opt-in.

**Publication remains gated.** The repository should not be promoted as a validated stable `1.0.0` release until the frozen external gold-standard protocol has been executed and the corresponding benchmark artifacts are archived.


## Documentation

- `docs/SCIENTIFIC_SPEC.md` — scientific architecture and non-claims
- `docs/M2_QUERY_LANGUAGE.md` — canonical query language
- `docs/M3_LIVE_ADAPTERS.md` — live-source architecture and API behavior
- `docs/M4_CONFIDENCE_DEDUPLICATION.md` — deduplication model, safety rules and validation plan
- `docs/M5_STUDY_LINKAGE.md` — study-family linkage, cluster safeguards and double-counting risk
- `docs/M6_SCREENING_INTEROPERABILITY.md` — screening audit, interchange formats and ASReview handoff
- `docs/M7_PRISMA_REPRODUCIBILITY.md` — PRISMA 2020/PRISMA-S accounting and reproducibility exports
- `docs/M8_SCIENTIFIC_BENCHMARKING.md` — query retrieval-equivalence metrics, ablation, robustness and scalability
- `docs/M8_EXTERNAL_VALIDATION.md` — frozen real-world gold-standard validation protocol and leakage controls
- `docs/M9_SOURCE_COVERAGE.md` — CORE, Scopus and Web of Science Starter execution/entitlement semantics
- `ROADMAP.md` — remaining milestones

## Important scope statement

MetaEvidence does not claim to retrieve “all papers in existence.” Coverage depends on source indexing, entitlements, query semantics, metadata quality, retrieval date, API limits, and source availability. It also does not yet claim superior deduplication, query-translation, or study-linkage performance relative to established tools. Where exact translation, exhaustive retrieval, or confident duplicate classification is not possible, the framework records that limitation rather than hiding it.

## External validation CLI

MetaEvidence v0.9.6-dev provides a command-line path for the frozen ASySD external-validation workflow:

```bash
metaevidence fetch-asysd external/asysd
metaevidence validate-asysd benchmarks/external_benchmark_manifest.json external/asysd results/asysd --role development
```

The primary removal-label endpoint uses blind `engine_quality` retention. A secondary `gold_preferred_reproduction` endpoint reproduces the representative-selection convention used by the public ASySD validation code, but it is explicitly reference-label-informed and cannot be used as the primary deployable performance claim.


## EndNote XML secondary external benchmark (v0.9.6-dev)

MetaEvidence can now stream EndNote XML gold corpora whose record-level truth is encoded as `caption=Duplicate`. The label is held outside the matching feature set, so the engine remains blind to the gold standard during deduplication.

The secondary benchmark is pinned to `IEBH/dedupe-sweep` commit `66a7ed5f5ea95cafc5f76ba6ec60bb4eb3cd381a` and includes `blue-light.xml`, `copper.xml`, `diabetes.xml`, `tafenoquine.xml`, and `uti.xml`. Downloads are verified against both expected byte size and Git blob SHA before validation; third-party XML is not bundled in the MetaEvidence wheel or source archive.

```bash
metaevidence fetch-beller-endnote external/beller
metaevidence validate-beller-endnote external/beller results/beller
```

A single compatible EndNote XML file can be evaluated with:

```bash
metaevidence validate-endnote-gold library.xml results/library
```

The primary endpoint remains blind `engine_quality` retention. Gold-preferred representative selection is emitted only as a secondary reproduction/sensitivity analysis. This secondary corpus does not replace the pre-specified ASySD benchmark-1 or the held-out validation gates.

## Manual external validation on GitHub Actions

MetaEvidence ships a manual-only `.github/workflows/external-validation.yml` workflow. It can run the pinned five-corpus EndNote benchmark in parallel or the frozen ASySD development/calibration protocol on a GitHub-hosted runner. ASySD held-out execution requires an explicit `confirm_held_out=true` workflow input **and** the CLI held-out unlock; raw third-party gold files are not uploaded as artifacts. See `docs/GITHUB_EXTERNAL_VALIDATION.md`.

