# MetaEvidence v0.9.8-dev

## Purpose

This checkpoint adds publication-oriented statistical reporting for **already-computed external deduplication results**. It is a downstream reporting release: the frozen publication-deduplication engine, its thresholds, matching features, retention policy, and external gold labels are not modified.

## Added

- `metaevidence.statistical_reporting` module.
- Wilson score intervals for sensitivity, specificity, precision, and accuracy at dataset and pooled-micro levels.
- Unweighted macro summaries across reviews/datasets.
- Deterministic review-level percentile bootstrap confidence intervals for macro sensitivity, specificity, precision, and F1.
- Pooled false-unique-removal and missed-duplicate counts/rates.
- Blind-result loader that prioritizes `blind_engine_quality` outputs and avoids gold-preferred reproduction results in the primary summary.
- `metaevidence summarize-removal-results INPUT OUTPUT` CLI command.
- Publication-oriented artifacts:
  - `removal_statistical_report.json`
  - `removal_dataset_statistics.csv`
  - `removal_aggregate_statistics.csv`
  - `manuscript_deduplication_table.csv`
  - `manuscript_deduplication_summary.md`
- Automatic statistical summaries in the manual external-validation GitHub Actions workflow.

## Statistical interpretation

The pooled micro estimates aggregate record-level confusion counts across datasets. Macro estimates are unweighted means across review/dataset-level metrics. Macro uncertainty is obtained by resampling **reviews/datasets**, not individual citations or candidate pairs, preserving the dependence structure within each systematic-review corpus.

Wilson intervals are reported for binomial proportions. F1 is reported as a point estimate at the micro level and with review-level bootstrap uncertainty for the macro summary; MetaEvidence does not pretend that a simple binomial Wilson interval applies directly to F1.

## Safety and leakage controls

- No statistical function reads citation text or changes deduplication decisions.
- Gold-preferred representative retention remains reproduction-only.
- The blind engine-quality result remains the primary external endpoint.
- ASySD held-out outcome gates remain unchanged.
- Third-party raw benchmark records remain excluded from GitHub Actions artifacts.

## QA

- 141/141 automated tests passed before release packaging.
- Includes deterministic-bootstrap, Wilson-interval, blind-loader, output-bundle, and CLI regression tests.

## External performance

No authentic external benchmark performance numbers are claimed in this release. Statistical tables remain empty of empirical MetaEvidence scores until the frozen corpora are executed on a network-enabled runner.
