# MetaEvidence v0.4-dev release notes

## Milestone

M4 — Confidence-aware Multi-stage Deduplication (core implementation).

## Added

- `ConfidenceDeduplicationEngine` (also exposed as backward-compatible `DeduplicationEngine`)
- three-way decisions: `AUTO_MERGE`, `REVIEW`, `KEEP_SEPARATE`
- pairwise `MatchFeatures`
- explainable `EvidenceContribution` objects
- `MatchAssessment` with provisional probability and audit rules
- DOI and strong-ID identity anchors
- identifier-conflict safety gates
- publication-form conflict detection
- title, token, author, year, journal, volume, issue, and page evidence
- conservative fuzzy-title auto-merge requirements
- exhaustive development mode plus scalable deterministic blocking
- graph/union-find auto-merge clustering
- representative-record quality selection
- provenance-preserving merge with conflict retention
- review queue
- deduplication run statistics
- `DeduplicationBenchmark`
- sensitivity, specificity, precision, F1, accuracy, false-merge rate
- Brier score and expected calibration error
- review workload accounting
- threshold optimization with a precision floor
- dependency-free `PlattCalibrator`
- M4 methodology/validation documentation
- confidence-deduplication example

## Safety / scientific interpretation

The default probability is an expert-weighted **uncalibrated engineering score**. It must not be described as an empirically calibrated probability until a calibrator has been fitted and externally evaluated on labelled data. v0.4 does not claim superiority over existing deduplication systems.

Distinct publication forms such as preprints and journal articles are intentionally not collapsed solely because title/authors/year are highly similar. They may later be linked by the M5 study-level publication linkage layer.

## QA status for this development snapshot

- pytest: **36 passed**
- Python compile check: passed
- wheel build: passed using installed setuptools/wheel with `--no-build-isolation`
- clean wheel install/import: passed
- installed version verified as `0.4.0.dev0`

The execution environment used for this snapshot did not provide the optional `ruff` executable, so linting is not claimed as completed here. CI lint/type/security checks remain part of M9.
