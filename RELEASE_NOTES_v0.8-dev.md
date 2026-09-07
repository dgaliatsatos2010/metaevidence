# MetaEvidence v0.8.0-dev — Scientific Benchmarking

## Added

- `QueryTranslationBenchmark` based on retrieved-identifier equivalence rather than query-string similarity.
- Retrieval precision, recall, F1, Jaccard overlap and relative count error.
- `DeduplicationAblationBenchmark` for one-feature-at-a-time M4 ablation.
- `StudyLinkageAblationBenchmark` for one-feature-at-a-time M5 ablation.
- `MetadataStressBenchmark` with deterministic field dropout.
- `ScalabilityBenchmark` with wall-clock, records/sec, candidate-pair and assessed-pair accounting.
- Bootstrap confidence interval helper for proportions.
- Deterministic synthetic deduplication, study-linkage and scalability datasets for engineering QA.
- `ScientificBenchmarkBundle` exporting CSV/JSON artifacts with SHA-256 integrity manifest.
- External validation protocol and candidate external dataset manifest.

## Scientific design changes

The M8 design explicitly separates three evidence levels:

1. **unit/regression tests** — software correctness;
2. **synthetic benchmark** — engineering stress/ablation behavior;
3. **external gold-standard validation** — required before real-world accuracy/superiority claims.

Query-translation quality is evaluated through retrieval equivalence against expert-reviewed target-database strategies. Similar-looking query strings are not treated as evidence of equivalent retrieval.

## External validation status

No external gold-standard performance result is claimed in v0.8-dev. Candidate deduplication benchmarks include the five public ASySD validation datasets described by Hair et al. (2023), plus the five Cochrane-derived gold-standard sets from the 2026 eight-tool comparison if the source files and reuse terms permit matched analysis.

## QA

- 92 unit/regression tests pass at the M8 implementation checkpoint.
- Synthetic benchmark artifacts are labelled as engineering QA only.
