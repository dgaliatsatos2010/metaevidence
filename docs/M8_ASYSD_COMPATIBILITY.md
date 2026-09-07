# ASySD-compatible external-validation contract

MetaEvidence v0.9.5-dev formalizes the exact record-level metric convention used by the public ASySD validation scripts while keeping the deployable evaluation blind to reference labels.

## Official validation convention reproduced

The public ASySD validation script loads five labelled datasets from OSF node `2b8uq`:

- `Diabetes_duplicates_labelled.csv`
- `NeuroImaging_duplicates_labelled.csv`
- `Cardiac_duplicates_labelled.csv`
- `Depression_duplicates_labelled.csv`
- `SRSR_duplicates_labelled.csv`

The reference label `Duplicate` is treated as the positive class and `Unique` as the negative class. The reported equations are:

- TP: gold `Duplicate`, predicted `Duplicate`
- TN: gold `Unique`, predicted `Unique`
- FN: gold `Duplicate`, predicted `Unique`
- FP: gold `Unique`, predicted `Duplicate`
- Sensitivity = TP / (TP + FN) × 100
- Specificity = TN / (TN + FP) × 100

`calculate_asysd_performance_contract()` reproduces those equations exactly.

## Why MetaEvidence reports two retention modes

ASySD's public validation code calls its deduplicator with `keep_label="Unique"`. This means the gold label may influence which member of a detected duplicate set is retained. Because record-level removal metrics depend on the chosen representative, MetaEvidence reports:

1. **engine_quality (primary):** representative choice is blind to gold labels. This estimates deployable behavior.
2. **gold_preferred_reproduction (secondary):** the predicted MetaEvidence clusters are unchanged, but a gold-`Unique` citation is retained when a predicted cluster contains one. This is only a reproduction/sensitivity endpoint.

When a verified duplicate-group identifier is available, MetaEvidence also reports representative-insensitive partition metrics.

## One-command workflow

```bash
metaevidence fetch-asysd external/asysd
metaevidence validate-asysd \
  benchmarks/external_benchmark_manifest.json \
  external/asysd \
  benchmark_results/asysd \
  --role development
```

Held-out data require the additional explicit `--allow-held-out` switch.

## Interpretation rule

Gold-preferred retention must never be used as MetaEvidence's primary external-validation claim. It is included only to reproduce the representative-selection convention used in the published ASySD validation workflow.
