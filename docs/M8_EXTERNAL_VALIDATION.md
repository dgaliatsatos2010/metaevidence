# M8 External validation protocol

## Purpose

This document freezes the first real-world validation design for MetaEvidence before external outcome metrics are inspected. Synthetic datasets and unit tests remain engineering QA and are not evidence of real-world superiority.

The external evaluation uses **two non-interchangeable gold-standard types**:

1. **record-removal labels** — the exact citation is labelled retain/remove (ASySD 2023);
2. **publication partitions** — citations have duplicate/publication group IDs (used when the external corpus actually provides them).

Both quantify the two practical harms of interest: a unique citation incorrectly removed
(false positive / removed singular) and a true duplicate citation left behind (false
negative / missed duplicate). Partition metrics are representative-invariant; removal-
label metrics intentionally reproduce the source study's representative-sensitive
classification task.

## Benchmark 1 — ASySD 2023 validation corpus

Hair et al. (BMC Biology, 2023; DOI 10.1186/s12915-023-01686-z) report five external validation datasets and state that the protocol, search datasets, results and analysis code are publicly available in the ASySD OSF project (`c9evs`). Their validation code uses labelled files named:

- `Diabetes_duplicates_labelled.csv`
- `NeuroImaging_duplicates_labelled.csv`
- `Cardiac_duplicates_labelled.csv`
- `Depression_duplicates_labelled.csv`
- `SRSR_duplicates_labelled.csv`

### Frozen roles

The role split is by **whole dataset**, never by randomly splitting citation pairs. This reduces leakage from near-identical citations belonging to the same publication.

| Dataset | Role | Final evaluated N | Consensus duplicate citations | Gold publications |
|---|---|---:|---:|---:|
| Diabetes | development | 1,845 | 1,261 | 584 |
| Neuroimaging | development | 3,434 | 1,298 | 2,136 |
| Cardiac | calibration | 8,948 | 3,530 | 5,418 |
| Depression | held-out test | 79,880 | 10,135 | 69,745 |
| SRSR | held-out test | 53,001 | 16,855 | 36,146 |

### Important count distinction

The ASySD paper's earlier dataset-description table reports the number of citations originally removed by human reviewers (for example 896 in Diabetes, 3,153 in Cardiac and 9,418 in Depression). The Results section explains that discrepancies across human and automated approaches were manually adjudicated to produce a new **consensus gold standard**. MetaEvidence therefore validates against the final consensus counts, not the original human-removal counts.

The Neuroimaging paper also reports 3,438 initial search returns in its earlier dataset table but evaluates a final corpus of N=3,434 in the Results section. The frozen integrity check uses the final evaluated corpus. If the distributed labelled file has a documented version-specific count that differs, the file/version must be documented and the plan amended **before** viewing MetaEvidence performance.

### ASySD gold-label semantics

The ASySD methods describe final duplicate groups in terms of one citation to **KEEP**
and the remaining citations to **REMOVE**; the public validation script then evaluates
the labelled CSVs using `label == "Unique"` versus `label == "Duplicate"`. MetaEvidence
therefore freezes `gold_standard_type="removal_label"` for all five ASySD files. It does
not infer publication partitions from a binary label column.

This matters because a partition metric is invariant to which equivalent citation is
retained, whereas the ASySD sensitivity/specificity analysis is based on the exact
record selected for removal. Both are useful, but they answer different questions.

### Leakage rule

- Development datasets may inform feature engineering and blocking changes.
- The Cardiac calibration dataset may be used to fit/lock calibration and thresholds only after feature choices are frozen.
- Depression and SRSR are held out. Their metrics must not inform any subsequent model/threshold change in the same reported experiment.
- If a change is made after viewing held-out results, those results become exploratory and a new independent test set is required.

## Benchmark 2 — Bateup et al. 2026 Cochrane gold standards

Bateup et al. (Research Synthesis Methods, 2026; DOI 10.1017/rsm.2026.10100) created five gold-standard sets by rerunning five Cochrane review searches and compared eight deduplication tools. The paper states that the gold-standard sets are available via OSF (`xu3tj`).

All five are frozen as **independent_benchmark_2** and are not available for tuning:

| Dataset | Records | Gold duplicates removed | Gold records after deduplication |
|---|---:|---:|---:|
| Arora 2022 | 3,299 | 533 | 2,766 |
| Cox 2021 | 5,258 | 397 | 4,861 |
| Freak-Poli 2020 | 12,432 | 5,145 | 7,287 |
| Noone 2020 | 3,265 | 397 | 2,868 |
| Pisano 2021 | 2,524 | 775 | 1,749 |
| **Total** | **26,778** | **7,247** | **19,531** |

One narrative paragraph in the article states 22,778 records, but the five dataset counts and the article's Table 3 sum to 26,778. MetaEvidence records this discrepancy explicitly and uses the internally consistent 26,778 value for published comparator tables.

### Published comparator values

`benchmarks/published_baselines_2026.csv` stores the aggregate values reported for ASySD, Covidence, Deduklick, EPPI-Reviewer, PICO Portal, Rayyan, SRA Focused and SRA Relaxed. These are **literature reference values**, not MetaEvidence calibration data. Fair claims require identical source records and equivalent settings.

## Gold-standard loader

The frozen manifest selects the loader before performance is inspected:

```python
from metaevidence import (
    load_external_dataset_specifications,
    load_external_gold_dataset,
)

specs = load_external_dataset_specifications(
    "benchmarks/external_benchmark_manifest.json"
)
spec = next(x for x in specs if x.id == "asysd_diabetes")
dataset = load_external_gold_dataset(
    "external_validation_data/asysd_2023/Diabetes_duplicates_labelled.csv",
    spec,
    strict=True,
)
```

For ASySD this yields `ExternalRemovalGoldDataset`; for a true group-based corpus it
yields `ExternalGoldDataset`. Strict integrity checking verifies final record count,
consensus removals and retained-publication count before benchmarking.

## ASySD record-removal evaluation

```python
from metaevidence import RemovalLabelBenchmark

result = RemovalLabelBenchmark.evaluate(dataset)
print(result.metrics.sensitivity)
print(result.metrics.specificity)
```

The result includes TP/TN/FP/FN, sensitivity, specificity, precision, F1, accuracy,
false-positive/false-negative rates, the number of records predicted removed and engine
candidate/review statistics. Here `false_positive` is a gold-`Unique` record removed by
MetaEvidence and `false_negative` is a gold-`Duplicate` record left behind.

## Partition-level evaluation when group IDs exist

```python
from metaevidence import ExternalGoldDataset, DedupPartitionBenchmark

partition_gold = ExternalGoldDataset.from_delimited(
    "partition_gold.csv", group_column="Duplicate ID"
)
partition_result = DedupPartitionBenchmark.evaluate(partition_gold)
```

Partition metrics compute removed singulars, missed duplicates, singular retention and
duplicate recall without depending on which member of a correctly identified duplicate
group is retained. They must only be used when the source gold standard actually
contains group identities.

## Audit-ready output

For ASySD removal-label gold data:

```python
from metaevidence import write_external_removal_validation_result

write_external_removal_validation_result(
    result, "results/diabetes", dataset=dataset, specification=spec
)
```

This writes `external_removal_metrics.json`, record-level gold/predicted removal
assignments and `external_validation_manifest.json`. Partition gold standards use
`write_external_validation_result` and `partition_assignments.csv` instead.

The manifest records the source-file SHA-256 when the source file is local, detected field mapping, gold counts, warnings, the frozen dataset specification and integrity-check result. The original third-party benchmark file itself does not need to be redistributed.

## Calibration and threshold locking

The default M4 score is still an engineering score until external calibration is performed. The intended sequence is:

1. freeze feature design on development datasets;
2. generate labelled pair/partition evidence from the calibration dataset;
3. fit calibration (for example the existing Platt calibrator) only on calibration data;
4. choose thresholds under a **precision/safety constraint** rather than maximizing F1 alone;
5. freeze the model, blocking and thresholds;
6. run Depression + SRSR held-out tests once;
7. run all five Bateup 2026 datasets as a second independent benchmark;
8. report every dataset, not only favorable subsets.

No test-set threshold optimization is permitted for confirmatory claims.

## Proposed primary/secondary endpoints

### Primary safety endpoint

For removal-label gold standards: false positives / gold-`Unique` records incorrectly
removed. For partition gold standards: `removed_singulars`. Report the count and an
appropriate denominator.

### Primary duplicate-detection endpoint

For removal-label gold standards: false negatives and sensitivity. For partition gold
standards: `missed_duplicates` and duplicate recall.

### Secondary endpoints

- number of records removed;
- predicted publication count error;
- pairwise precision/recall/F1 where pair labels are available;
- review-queue size/fraction;
- blocking recall;
- candidate-pair reduction;
- runtime and peak memory on documented hardware;
- calibration error/Brier score if interpretable probabilities are fitted;
- performance under controlled missing metadata and language strata.

## Statistical reporting

For proportions, report confidence intervals in addition to point estimates. For cross-dataset summaries, preserve dataset-level results and avoid treating millions/billions of possible negative pairs as independent evidence. Tool comparisons should emphasize practical harms (false merges and missed duplicates) rather than only an inflated all-pairs specificity.

Any hypothesis test should be pre-specified and secondary to effect sizes and confidence intervals. If the same gold corpus is used to select thresholds, its performance is not an independent test estimate.

## Query-translation external validation

The query-language contribution requires a separate prospective benchmark. For each review/database pair:

1. an information specialist/expert writes the reference target-database query;
2. MetaEvidence compiles the same canonical concept strategy;
3. both are executed against the same database as close in time as possible;
4. compare retrieved record IDs and, most importantly, known eligible studies;
5. record translation diagnostics and whether `fidelity_score` predicts actual retrieval loss.

String similarity between query text is **not** the primary outcome.

## Study-family linkage external validation

M5 needs a separate adjudicated gold standard in which publications are grouped by underlying study. Splits must occur by complete study family, never by publication pair. The primary objective is high precision/safety because falsely merging two different trials can cause incorrect meta-analytic unit-of-analysis decisions.

## Current execution status

As of v0.8.1-dev:

- the external partition loader is implemented;
- integrity checks and frozen dataset roles are implemented;
- Bateup 2026 aggregate baselines are encoded;
- audit-ready external result export is implemented;
- unit/regression and synthetic engineering QA pass;
- **no real MetaEvidence performance estimate from the third-party gold files is claimed yet**.

The public data sources have been identified, but the third-party gold-standard files are not bundled with MetaEvidence. They must be obtained from their source repositories under applicable terms before executing the real benchmark.


## Representative-retention sensitivity (v0.9.4)

The ASySD 2023 repository's official validation code retrieves the five labelled CSVs
from OSF node `2b8uq` and evaluates `dedup_citations` with `keep_label="Unique"`.
Consequently, its record-level TP/TN/FP/FN calculation is **representative-sensitive**:
which record is retained inside a correctly detected duplicate cluster can change the
confusion matrix. This is distinct from the question of whether the duplicate cluster was
detected correctly.

MetaEvidence therefore freezes three possible readouts:

1. **Blind engine-quality retention (primary).** The production engine selects the
   representative using bibliographic completeness/quality and never reads the gold
   `Unique`/`Duplicate` label. This is the unbiased deployable record-removal estimate.
2. **Gold-preferred reproduction (secondary only).** The predicted clustering is kept
   fixed, but a gold-`Unique` record is retained when one is present in the predicted
   cluster. This mirrors the retention consequence of ASySD's published validation
   setting and is explicitly marked `uses_gold_labels=True`. It must not be used as the
   primary MetaEvidence performance claim.
3. **Representative-insensitive partition endpoint (preferred secondary endpoint when
   available).** If the source file contains a verified `duplicate_id` or equivalent
   publication-group column and its counts pass the frozen integrity checks, MetaEvidence
   also evaluates the predicted publication partition. This measures false merges and
   retained duplicates without depending on which member is kept.

The same MetaEvidence clustering is used for modes 1 and 2. Any difference between those
record-level scores therefore quantifies **representative-selection sensitivity**, not a
change in duplicate detection.

Reference implementation inspected prospectively before external execution:
`https://github.com/camaradesuk/ASySD/tree/master/validation`
(`Check_performance.R` and `calculate_performance_function.R`).
