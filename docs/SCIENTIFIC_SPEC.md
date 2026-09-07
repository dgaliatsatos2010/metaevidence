# MetaEvidence Scientific Specification v0.5

## Research problem

Systematic reviewers commonly execute semantically similar strategies independently in multiple bibliographic databases, export heterogeneous records, manually reconcile metadata, deduplicate publications, and reconstruct search histories for reporting. These steps introduce avoidable translation ambiguity, provenance loss, false-merge risk, and reproducibility problems.

## Proposed contribution

MetaEvidence models multi-database evidence retrieval and reconciliation as a reproducible computational pipeline with explicit provenance and uncertainty.

### Contribution C1 — Canonical Search Representation (CSR)
A source-neutral representation of Boolean groups, phrases, truncation, fields, proximity operators, date limits and controlled-vocabulary concepts.

### Contribution C2 — Auditable Query Translation Graph (AQTG)
Every canonical clause is mapped to source-specific syntax and receives a translation status: exact, approximated, expanded, unsupported, or user-review-required. This exposes semantic drift rather than hiding it.

### Contribution C3 — Evidence Provenance Graph (EPG)
Each normalized publication retains source records, source identifiers, retrieval timestamps, translated queries, ranks and merge evidence rather than losing provenance after reconciliation.

### Contribution C4 — Confidence-aware Multi-stage Deduplication (CMD)
Publication-level duplicate classification combines persistent identifiers, bibliographic similarity, conflict evidence and publication-form safeguards. Each candidate pair receives an auditable feature vector, provisional probability, feature contributions and a three-way decision (`AUTO_MERGE`, `REVIEW`, `KEEP_SEPARATE`). Only automatic high-confidence edges are clustered; ambiguous pairs remain available for human review. Source hits and conflicting metadata are retained after merge.

The default v0.4 score is **not yet an empirically calibrated probability**. Calibration and threshold selection must be performed on labelled validation datasets, and final performance must be measured on independent test datasets.

### Contribution C5 — Study-level Publication Linkage (SPL)
A separate implemented layer distinguishes publication duplicates from multiple distinct publications reporting the same underlying study. M5 combines normalized registry IDs, study acronyms, investigator overlap, sample-size compatibility, countries/sites, recruitment periods, interventions/exposures, populations and publication roles. It produces a separate provisional study-link probability and four-way relationship decision, then constructs provenance-preserving study families. Review-article registry mentions, multiple registry IDs and transitive graph merges are protected by explicit safety gates. Families with multiple outcome-bearing reports receive double-counting warnings for meta-analysis.

As in M4, the default M5 score is not yet claimed to be externally calibrated. Study-linkage performance and thresholds require independently labelled development/calibration/test datasets.

### Contribution C6 — Search Reproducibility Manifest (SRM)
Every run records package version, source metadata when obtainable, translated source query, retrieval date/time, filters, API mode, result counts, pagination and warnings.

### Contribution C7 — PRISMA-oriented accounting
The pipeline will retain counts needed for identification and deduplication reporting and export machine-readable flow data. It will support PRISMA reporting without claiming that software use alone makes a review PRISMA-compliant.

## Novelty positioning

MetaEvidence will not claim novelty for fuzzy citation matching alone. Established tools such as SRA-DM, Deduklick and ASySD already demonstrate effective automated deduplication. The intended methodological novelty must be evaluated as the *combined* framework: cross-database semantic translation, retrieval provenance, uncertainty-aware deduplication, calibrated human-review triage, study-level publication-family linkage, and reproducible evidence-flow accounting.

## Non-claims

The project will not claim:

- complete universal literature coverage;
- semantic equivalence where a database cannot express a canonical operator;
- unrestricted access to subscription databases;
- lawful redistribution of paywalled full text;
- calibrated match probability before empirical calibration;
- superiority over existing deduplication or trial-publication linkage tools before external benchmarking;
- that similar publications necessarily represent duplicate citations;
- that software use alone makes a systematic review PRISMA-compliant.

## Validation hypotheses

H1: Canonical translation reduces inter-database query-construction inconsistencies relative to independent manual translation.

H2: After calibration and threshold selection on development data, confidence-aware deduplication achieves higher duplicate recall at an equivalent false-merge rate than DOI-only and exact-title-only baselines.

H3: The explicit `REVIEW` band reduces false automatic merges while keeping manual workload materially lower than full pairwise review.

H4: Provenance-preserving merging enables reconstruction of database-specific identification counts after deduplication.

H5: After independent calibration/validation, study-level linkage identifies related publication families that publication-level deduplication intentionally retains while maintaining a low false-family-link rate.

H6: Source-aware conflict features and publication-form safeguards improve robustness under missing or inconsistent metadata.

## Primary evaluation dimensions

- query translation fidelity
- retrieval overlap and unique contribution by source
- publication-deduplication precision, recall, F1 and specificity
- **false-merge rate** (high-priority safety metric)
- duplicate records retained
- calibration (Brier score, calibration error/curve)
- human-review workload
- candidate-blocking recall
- study-linkage precision, recall and F1
- reproducibility of reruns
- runtime and API-call efficiency
- robustness to missing DOI/authors/year/abstract
- robustness to publication-form differences and multilingual metadata

## Benchmark design principle

Development, probability calibration, threshold tuning and final testing must be separated at the systematic-review/dataset level where possible. Citation pairs originating from the same review should not be split naively across train and test sets because this can create leakage through shared source conventions, topics and metadata patterns.
