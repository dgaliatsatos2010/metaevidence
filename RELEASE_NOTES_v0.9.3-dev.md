# MetaEvidence v0.9.3-dev release notes

This milestone strengthens external-validation validity rather than changing production deduplication thresholds.

## Added

- `ExternalRemovalGoldDataset` for exact retain/remove gold labels.
- `RemovalLabelBenchmark` with TP/TN/FP/FN, sensitivity, specificity, precision, F1 and safety/error counts.
- Manifest-driven `load_external_gold_dataset()` so gold semantics are frozen before outcome inspection.
- `OSFPublicFileFetcher` and `fetch_asysd_validation_files()` for the five public ASySD validation files identified by the source authors' validation code.
- `run_external_validation_plan()` plus scripts for source retrieval and development/calibration/held-out execution.
- Explicit held-out disclosure gate and source SHA-256 provenance.

## Methodological correction

ASySD 2023's labelled validation files are treated as representative-sensitive `Unique`/`Duplicate` removal labels. They are not treated as publication partitions unless a separate source file actually supplies duplicate-group IDs. This avoids evaluating a different gold-standard task than the source study defined.

## Status

No real MetaEvidence external performance numbers are reported in this release because the OSF source files could not be fetched in the current execution environment. The frozen roles and thresholds remain unexposed to held-out outcomes.
