# Changelog

## 0.9.9-dev

- Added cryptographic frozen-validation lock for method-critical files, benchmark manifests and execution-layer files.
- Added fail-closed `verify-validation-lock` CLI and pre-install repository verifier.
- Made the Beller GitHub Actions matrix derive its dataset list from the pinned manifest.
- Added per-run cryptographic validation provenance manifests and workflow-page summaries.
- Increased results-only external-validation artifact retention to 90 days.
- Preserved the v0.9.4 publication-deduplication engine byte-for-byte; no features, weights, thresholds, blocking or retention rules changed.
- Test suite: 147 passing tests before packaging.

## 0.9.8-dev

- Added publication-oriented uncertainty summaries downstream of frozen blind external-validation results.
- Added Wilson confidence intervals for dataset-level and pooled micro proportions.
- Added deterministic review-level percentile bootstrap intervals for unweighted macro metrics.
- Added pooled safety reporting for false unique removals and missed duplicates.
- Added `summarize-removal-results` CLI plus manuscript-ready JSON/CSV/Markdown outputs.
- Integrated statistical result generation into the manual GitHub Actions external-validation workflow.
- Preserved the frozen deduplication engine and blind-primary/gold-preferred-secondary validation contract.
- Test suite: 141 passing tests before release packaging.

## 0.9.7-dev

- Added manual-only GitHub Actions external-validation workflow.
- Added matrix execution for pinned EndNote XML corpora and explicit ASySD held-out gates.
- Added single-file `--file` fetch/validation support for the Beller/IEBH benchmark.
- Workflow artifacts exclude raw third-party gold data and include provenance/source manifests.

## 0.9.6-dev

- Added streaming EndNote XML gold-standard importer for large citation corpora.
- Added explicit `caption=Duplicate` removal-label semantics with fail-closed unknown-caption handling.
- Added pinned secondary external benchmark source for five verified IEBH/dedupe-sweep libraries at commit `66a7ed5f5ea95cafc5f76ba6ec60bb4eb3cd381a`.
- Added Git blob SHA-1 and byte-size integrity gates for downloaded/local benchmark files.
- Added `fetch-beller-endnote`, `validate-endnote-gold`, and `validate-beller-endnote` CLI workflows.
- Ensured gold captions are never consumed as deduplication matching features.
- Test suite: 133 passing tests before release packaging.

## 0.9.5-dev

- Formalized the published ASySD record-level metric contract (Duplicate positive class, Unique negative class; TP/TN/FN/FP, sensitivity and specificity).
- Added `metaevidence fetch-asysd` and `metaevidence validate-asysd` command-line workflows.
- Added consolidated blind-versus-gold-preferred ASySD compatibility reports.
- Added exact metric-contract and CLI regression tests.
- Preserved the frozen rule that gold-informed retention is secondary reproduction only.

## 0.9.4.dev0

- Added explicit blind versus gold-preferred representative-retention evaluation for ASySD-style removal-label gold standards.
- Blind `engine_quality` retention is the primary external endpoint; `gold_preferred_reproduction` is marked as gold-informed and reproduction-only.
- Added automatic representative-insensitive partition evaluation when a verified duplicate/publication group column is present in a removal-label source file.
- Added side-by-side retention comparison artifacts and run-manifest provenance.
- Added regression tests for representative-selection sensitivity and secondary partition output.
- Test suite: 123 passing tests before release packaging.


## 0.9.3.dev0

- Corrected external-validation semantics: ASySD 2023 labelled files are evaluated as representative-sensitive `Unique`/`Duplicate` removal labels, not fabricated publication partitions.
- Added `ExternalRemovalGoldDataset`, `RemovalLabelBenchmark`, strict manifest-driven gold loader and auditable removal-label result bundles.
- Added public OSF file-tree fetcher for the five ASySD validation filenames on official node `2b8uq`, with source-file SHA-256 and no third-party redistribution.
- Added frozen-role external validation runner with a separate held-out disclosure gate.
- Regression suite expanded to 121 tests.

## 0.9.2.dev0

- Added `OpenAlexOQLAdapter` with native OQL fielded Boolean/proximity/wildcard/year compilation, cursor paging, `meta.x_query` capture and POST fallback for long queries.
- Added `WebOfScienceExpandedAdapter` with official Expanded `firstRecord`/`count` paging, `FR`/`SR`/`FS` modes, rich metadata normalization and explicit full-record quota/entitlement reporting.
- Added HTTP POST retry/audit support and Clarivate quota-header capture.
- Changed screening revision resolution to append-order semantics so timestamps remain provenance rather than an unsafe ordering key.
- Expanded regression coverage to 116 tests.


All notable pre-release milestones are summarized here. Detailed notes remain in the version-specific release-note files.

## 0.9.0-dev — release engineering
- GitHub Actions CI across Python 3.10–3.13.
- clean artifact build/install validation.
- protected Trusted-Publishing workflow template for PyPI.
- citation, contribution, security and release-governance files.
- external-validation release gate retained.

## 0.8.1-dev — external-validation readiness
- external gold-partition loader and integrity gate.
- partition-level removed-singular/missed-duplicate metrics.
- frozen development/calibration/held-out protocol.
- Bateup 2026 comparator baselines.
- audit-ready gold/predicted partition exports with source SHA-256.

## 0.8.0-dev — scientific benchmark harness
- query-translation retrieval benchmark, ablations, missingness stress tests, scalability, blocking recall and bootstrap utilities.

## 0.7.0-dev — PRISMA/reproducibility
- record/report/study accounting, PRISMA-S support matrix and reproducibility bundles.

## 0.6.0-dev — screening interoperability
- screening ledger, dual-review adjudication, RIS/BibTeX/CSV/JSONL and ASReview interchange.

## 0.5.0-dev — study-level linkage
- publication-family linkage, registry safeguards and double-counting warnings.

## 0.4.0-dev — confidence-aware deduplication
- explainable matching, review band, safety gates, calibration/benchmark infrastructure.

## 0.3.0-dev — live open-source adapters
- PubMed, OpenAlex, Crossref and Europe PMC retrieval with provenance/auditing.

## 0.2.0-dev — canonical query language
- AST, fielded/proximity/controlled-vocabulary expressions and source-specific compilers.

## 0.1.0-dev — core prototype
- common evidence record, provenance and deterministic baseline components.

## [0.9.1-dev] - 2026-09-06

### Added
- CORE v3, Scopus Search API and Web of Science Starter API v2 live adapters.
- Starter-safe Web of Science query compilation and CORE query compilation.
- Per-source `adapter_options` for credentials/configuration.
- Source-specific entitlement/date-semantics warnings and M9 source-coverage documentation.
- Expanded live-source test suite (109 tests total).

