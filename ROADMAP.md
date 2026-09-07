# MetaEvidence roadmap

## M0 — Scientific definition [DONE in v0.1-dev]
- scope/non-claims
- innovation pillars
- evaluation hypotheses

## M1 — Core data model [DONE in v0.1-dev]
- normalized record
- source provenance
- canonical query container
- deterministic dedup baseline
- search manifest

## M2 — Formal query language [DONE in v0.2-dev; empirical validation remains]
- tokenizer + AST
- AND/OR/NOT groups
- exact phrases and escaping
- truncation/wildcards
- field restrictions
- proximity operations
- MeSH/controlled vocabulary concepts
- PICO/PECO builder
- translation-loss diagnostics

## M3 — Live source adapters [SEVEN SOURCE FAMILIES + ADVANCED MODES DONE through v0.9.2-dev]
Implemented:
1. PubMed/NCBI
2. OpenAlex
3. Crossref
4. Europe PMC
5. CORE
6. Scopus Search API (user/institution API credentials required)
7. Web of Science Starter API v2 (user API credentials required)
8. common retries/backoff
9. cursor/history/offset/page pagination as source-appropriate
10. optional caching and raw-response audit
11. secret-redacted request provenance
12. schema normalization
13. multi-source orchestration, per-source options and failure isolation

Still to add within/after M3:
- Web of Science API Expanded adapter [DONE v0.9.2] for entitled users needing richer full-record metadata
- OpenAlex OQL execution path for field-rich queries
- source-specific exhaustive retrieval strategies for searches exceeding normal API limits

## M4 — Publication deduplication research engine [CORE IMPLEMENTATION DONE in v0.4-dev; external validation remains]
Implemented:
- exact identifier anchors and conflict gates
- bibliographic feature vector
- title/author/year/journal/volume/issue/page similarity
- publication-form conflict protection
- transparent provisional probability model
- explainable feature contributions
- `AUTO_MERGE` / `REVIEW` / `KEEP_SEPARATE`
- human review queue
- provenance-preserving graph clustering
- deterministic candidate blocking for large libraries
- benchmark metrics including false-merge rate and calibration metrics
- precision-constrained threshold tuning
- Platt calibration utility

Still required before scientific performance claims:
- independent labelled development/calibration/test datasets
- blocking-recall evaluation
- external tool comparisons
- missing-metadata and multilingual stress tests
- ablation studies
- runtime/memory scaling
- validated threshold selection

## M5 — Study-level publication linkage [CORE IMPLEMENTATION DONE in v0.5-dev; external validation remains]
Implemented:
- trial/registry ID extraction and normalization
- explicit separation of publication duplicates from same-study reports
- publication-role classification
- study-link feature vector for registry/acronym/authors/dates/sample size/country/intervention/population
- provisional probability/uncertainty model distinct from M4
- `SAME_STUDY` / `REVIEW` / `DIFFERENT_STUDY` / `DUPLICATE_PUBLICATION`
- review-article registry-mention safeguard
- multi-registry ambiguity protection
- transitive cluster-consistency gate
- stable publication-family graph IDs
- provenance-preserving family summaries
- double-counting risk warnings for meta-analysis
- JSON/CSV family, edge, review and risk exports
- pair-level benchmark and precision-constrained threshold tuning

Still required before scientific performance claims:
- independent labelled study-family development/calibration/test sets
- cross-registry equivalence validation
- full-text registry-mention section/context features
- external comparison with trial-publication linkage systems where fair datasets/interfaces exist
- observational/non-randomized study-family benchmarks
- multilingual and missing-metadata stress tests
- graph-clustering ablation and transitive-error analysis
- calibrated probability validation

## M6 — Screening interoperability [CORE IMPLEMENTATION DONE in v0.6-dev; broader round-trip validation remains]
Implemented:
- stable record IDs for workflow handoff
- CSV/RIS/BibTeX/JSONL export
- CSV and common-RIS import
- ASReview-compatible CSV conventions
- ASReview-compatible RIS N1 labels
- append-only inclusion/exclusion audit log
- title/abstract and full-text stages
- controlled exclusion reasons
- double-screening disagreement/adjudication
- reviewer percent agreement and Cohen's kappa
- conservative handling of MAYBE/unresolved decisions
- screening bundle with SHA-256 manifest
- integration with M5 study-family/double-counting outputs

Still required before broad interoperability claims:
- real ASReview round-trip integration tests against pinned releases
- additional citation-manager RIS corpora
- large-file/encoding/malformed-input stress tests
- vendor-specific Rayyan/Covidence interchange only where format documentation and permissions support reliable implementation
- audit schema migrations/versioning

## M7 — PRISMA/reproducibility layer [CORE IMPLEMENTATION DONE in v0.7-dev]
Implemented:
- identification counts by database plus optional registers/other sources
- duplicate, automation and other pre-screening removal accounting
- record/report/study-level distinction
- title/abstract and full-text screening accounting
- non-retrieval vs eligibility-exclusion separation
- full-text exclusion reason aggregation
- included-study counts through M5 study families
- arithmetic consistency validation
- source/platform/date/full-strategy search reporting
- PRISMA-S 16-item automatic/user-input support matrix
- JSON/CSV/Markdown exports
- editable Mermaid flow source
- reproducibility bundle with SHA-256/runtime manifest

Still required before broad reporting claims:
- real-world comparison against published PRISMA flow examples
- updated-review and “other methods” flow templates
- validated export/import against external PRISMA diagram tooling where stable interfaces exist
- user testing with systematic reviewers/information specialists
- schema version migration tests

## M8 — Scientific benchmark suite [EXTERNAL-VALIDATION HARNESS DONE in v0.8.1-dev; real gold-file execution remains]
Implemented:
- retrieval-set query-translation benchmark (precision/recall/F1/Jaccard/count error)
- linkage to translation fidelity/loss diagnostics
- M4 one-feature-at-a-time ablation
- M5 one-feature-at-a-time ablation
- deterministic missing-metadata stress testing
- deduplication and study-linkage scalability instrumentation
- bootstrap proportion confidence intervals
- deterministic synthetic QA datasets
- benchmark CSV/JSON bundle with SHA-256 manifest
- external benchmark manifest and leakage-safe validation protocol
- partition-level external gold loader/evaluator
- strict expected-count integrity gate
- frozen development/calibration/held-out dataset roles
- Bateup 2026 eight-tool aggregate comparator table
- source-file SHA-256 + gold/predicted partition audit export

External work still required before performance claims:
- obtain the ASySD public gold files from their source repository and pass frozen integrity checks
- independently reproduce/inspect labels and document any source-version corrections before outcome inspection
- obtain/use the five Bateup 2026 Cochrane gold sets under their applicable sharing terms
- execute the pre-frozen ASySD development → calibration → held-out test sequence
- fit calibration only on the frozen Cardiac calibration data and lock final thresholds before Depression/SRSR
- execute Bateup 2026 as a completely independent second benchmark
- prospectively curate expert query-translation reference searches
- prospectively adjudicate study-family linkage gold standards
- compare against established tools on identical records and settings
- add multilingual and empirically realistic missingness profiles
- run large-scale runtime/memory benchmarks on documented hardware
- generate final publication tables, confidence intervals and error taxonomy

## M9 — Packaging/release [RELEASE ENGINEERING CORE PREPARED in v0.9-dev; public release blocked on validation]
Implemented locally:
- GitHub Actions test matrix for Python 3.10–3.13
- package build + clean wheel installation check
- protected PyPI Trusted Publishing workflow template
- CITATION.cff
- CONTRIBUTING / SECURITY / code-of-conduct files
- changelog and release checklist
- reproducible release procedure
- gitignore rules for secrets/private benchmark data

Still required before/at public release:
- execute frozen external validation and archive results
- add coverage and type-checking gates after baseline cleanup
- add secret/dependency scanning appropriate to the public host
- finalize public documentation site
- create/push public GitHub repository
- set final repository URLs/author metadata
- configure protected PyPI Trusted Publishing environment
- publish PyPI release candidate
- connect GitHub release to Zenodo and mint DOI
- archive benchmark artifacts and final checksums

## M10 — Scientific paper
Suggested framing: a methodological/software paper centered on reproducible cross-database evidence retrieval, translation fidelity, provenance-preserving uncertainty-aware deduplication, and study-level linkage, validated on real systematic-review search tasks.


### v0.9.4 external-validation hardening
- [x] Separate blind/deployable retention from gold-preferred ASySD reproduction.
- [x] Add representative-insensitive partition secondary endpoint when verified group IDs exist.
- [x] Preserve held-out gates and source hashes.
- [ ] Execute public ASySD files once the runtime can access OSF or the files are supplied locally.

### v0.9.5 external-validation hardening
- [x] ASySD-compatible metric contract
- [x] Blind versus gold-preferred retention report
- [x] CLI fetch/validate entry points
- [ ] Execute five official ASySD CSVs without threshold changes

### v0.9.6 secondary external benchmark interoperability
- [x] Streaming EndNote XML gold-standard importer.
- [x] Gold-label isolation from matching features.
- [x] Pin IEBH/dedupe-sweep benchmark source to immutable commit and Git blob identifiers.
- [x] Fail-closed byte-size/blob-SHA integrity validation.
- [x] CLI fetch and single/batch validation entry points.
- [ ] Execute the five pinned XML files on a network-enabled runner; do not tune thresholds on these secondary data.
- [ ] Archive resulting machine-readable blind metrics beside ASySD results once benchmark-1 is available.


### v0.9.7 checkpoint

- ✅ GitHub-executable frozen external validation (`workflow_dispatch` only).
- ✅ Beller/IEBH matrix benchmark with pinned bytes and results-only artifacts.
- ✅ ASySD held-out workflow/CLI dual gate.
- ⏳ Execute authentic external corpora and archive result artifacts before final release.


### v0.9.8 checkpoint — statistical external-result reporting

- ✅ Wilson confidence intervals for dataset-level and pooled micro sensitivity/specificity/precision/accuracy.
- ✅ Review-level deterministic percentile bootstrap for macro sensitivity/specificity/precision/F1.
- ✅ Explicit false-unique-removal and missed-duplicate safety summaries.
- ✅ Machine-readable and manuscript-ready tables generated directly from blind validation artifacts.
- ✅ GitHub Actions integration without uploading raw third-party benchmark data.
- ✅ Frozen deduplication engine remains unchanged.
- ⏳ Populate the statistical report with authentic external benchmark outcomes only after networked execution.

### v0.9.9 checkpoint — cryptographically frozen external execution

- ✅ Validation-only patch; publication-deduplication engine remains byte-identical to v0.9.8/v0.9.4 freeze.
- ✅ SHA-256 lock for method-critical files, benchmark manifests and validation-runner files.
- ✅ Fail-closed pre-execution integrity verification.
- ✅ Beller matrix derived directly from the authoritative pinned manifest.
- ✅ Per-run result-file hashes and GitHub/runtime provenance.
- ✅ Results-only artifacts retained for 90 days; raw third-party benchmark data are excluded.
- ⏳ Create the dedicated public `dgaliatsatos2010/metaevidence` repository and execute `tafenoquine.xml` first.
- ⏳ If the smoke run passes integrity + parsing + scoring, execute the full five-corpus Beller matrix without tuning.
- ⏳ Populate manuscript performance tables only from archived authentic external-validation artifacts.

