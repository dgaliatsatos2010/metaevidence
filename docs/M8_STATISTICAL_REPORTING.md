# M8 statistical reporting for frozen external deduplication results

MetaEvidence v0.9.8-dev adds a downstream reporting layer. It does **not** change publication-matching features, deduplication thresholds, blocking rules, representative-retention policy, or any external gold labels.

## Primary analysis

The primary input is the blind `engine_quality` removal result for each external systematic-review corpus. Gold-preferred representative selection is a reproduction/sensitivity analysis and is excluded from primary statistical summaries whenever blind results are available.

## Dataset and pooled micro intervals

Sensitivity, specificity, precision and accuracy are binomial proportions. Dataset-level and pooled-micro 95% confidence intervals therefore use the Wilson score interval. Micro estimates are computed after summing TP, TN, FP and FN across corpora, so they are record weighted. F1 is reported as a point estimate at the micro level and is not assigned a Wilson interval.

## Macro review-level uncertainty

Macro sensitivity, specificity, precision and F1 are unweighted arithmetic means across systematic-review corpora. Uncertainty is estimated by deterministic percentile bootstrap resampling of the **review/corpus unit**, not individual citations or candidate pairs. The default is 5,000 resamples with seed `20260907`.

This preserves the within-review dependence structure and avoids pseudo-replication of related citation records.

## Safety endpoints

Absolute false unique removals (FP) and missed duplicate removals (FN) are reported alongside conventional discrimination metrics. These counts map directly to two practically important harms: losing unique evidence before screening and retaining duplicates that increase downstream workload.

## Outputs

`metaevidence summarize-removal-results INPUT OUTPUT` writes:

- `removal_statistical_report.json`
- `removal_dataset_statistics.csv`
- `removal_aggregate_statistics.csv`
- `manuscript_deduplication_table.csv`
- `manuscript_deduplication_summary.md`

The command only reads already-computed removal-validation metrics. It does not inspect citation text or modify predictions.
