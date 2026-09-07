# MetaEvidence v0.8.1-dev release notes

## Focus: external-validation readiness

v0.8.1-dev extends the M8 benchmark framework from synthetic/scaffold testing toward audit-ready external gold-standard evaluation.

### Added

- `ExternalGoldDataset` loader for labelled citation partitions.
- Flexible source-column autodetection and explicit field overrides.
- `DedupPartitionBenchmark` with workflow-level outcomes:
  - removed singular publications;
  - missed duplicates;
  - singular retention;
  - duplicate recall;
  - predicted/gold partition sizes;
  - candidate/assessed pair statistics.
- `ExternalDatasetSpecification` and strict integrity validation.
- Frozen development/calibration/held-out roles in `benchmarks/external_benchmark_manifest.json`.
- Consensus-gold counts for the ASySD 2023 corpus, distinguished from original human-removal counts.
- Five completely independent Bateup 2026 Cochrane benchmark specifications.
- Published aggregate results for eight 2026 comparator tools in `benchmarks/published_baselines_2026.csv`.
- Audit-ready external result export with gold/predicted partitions and source-file SHA-256.
- `docs/M8_EXTERNAL_VALIDATION.md` and runnable example.

## Scientific non-claim

This release does **not** report MetaEvidence performance on the third-party gold-standard files. The files are not redistributed in the package and were not available locally for execution in this build environment. Real-world sensitivity, false-merge, calibration or superiority claims remain blocked until the frozen protocol is executed against the source datasets.

## Validation policy frozen before outcome inspection

- ASySD Diabetes + Neuroimaging: development.
- ASySD Cardiac: calibration/threshold locking.
- ASySD Depression + SRSR: held-out test.
- Bateup 2026 five Cochrane datasets: independent benchmark 2; no tuning.

This split is by entire dataset rather than randomly by citation pair to reduce leakage from near-identical records.
