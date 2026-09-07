# M8 — Scientific benchmarking and validation protocol

MetaEvidence v0.8.0-dev adds a reproducible benchmarking layer. The code in this
release is validation infrastructure; synthetic results are engineering QA and MUST
NOT be reported as evidence of real-world accuracy.

## 1. Scientific questions

### Q1 — Query translation
Does a MetaEvidence-generated target-database query retrieve the same evidence as an
expert-reviewed translation of the same canonical search strategy?

Primary metrics:
- retrieval recall relative to the expert reference set;
- eligible-study recall when a gold-standard included-study set is available;
- retrieval precision;
- F1 and Jaccard overlap;
- relative count error;
- association between MetaEvidence translation fidelity/loss score and empirical
  retrieval loss.

The benchmark compares retrieved identifiers, not superficial query-string similarity.
Searches should be executed on the same date or against a frozen/snapshotted index when
possible, because database contents change over time.

### Q2 — Publication-level deduplication
Can M4 remove duplicate citations while protecting unique records?

Primary metrics:
- sensitivity/duplicate recall;
- specificity;
- precision/positive predictive value;
- F1;
- false-merge rate (safety-critical);
- review fraction;
- Brier score and expected calibration error for probabilistic output;
- wall-clock time and candidate-pair reduction.

### Q3 — Study-level publication linkage
Can M5 group distinct reports from the same underlying study without joining reports
from different studies?

Primary metrics:
- sensitivity;
- specificity;
- precision;
- F1;
- false-link rate (safety-critical);
- review fraction;
- Brier score;
- family-level error analysis, including transitive-bridge errors.

### Q4 — Robustness
How does performance change when metadata are missing or inconsistent?

Experiments:
1. independent field dropout at 10%, 25%, 50% and 75%;
2. field-specific dropout (DOI only, author only, year only, etc.);
3. realistic database-profile dropout once empirical missingness profiles are measured;
4. conflicting identifiers;
5. preprint/final-article and conference/journal stress cases;
6. multi-registry trial reports.

### Q5 — Contribution of individual features
One-feature-at-a-time ablation is performed for M4 and M5. A useful feature should
improve the primary safety/performance trade-off, not merely increase a raw score.

### Q6 — Scalability
Measure wall-clock time, records/second, candidate pairs and assessed pairs over
increasing corpus sizes. Report CPU, OS, Python version, memory and package version.
Timing should never be compared across tools without documenting hardware and I/O.

## 2. External validation datasets

### Deduplication benchmark A — ASySD public gold standards
Hair et al. (2023) evaluated ASySD on five unseen biomedical systematic-search
collections, ranging from 1,845 to 79,880 citations. Their article reports the following
reference counts:

| Dataset | Final evaluated citations | Consensus duplicate removals | Consensus retained citations |
|---|---:|---:|---:|
| Diabetes | 1,845 | 1,261 | 584 |
| Neuroimaging | 3,434 | 1,298 | 2,136 |
| Cardiac | 8,948 | 3,530 | 5,418 |
| Depression | 79,880 | 10,135 | 69,745 |
| SRSR | 53,001 | 16,855 | 36,146 |

These are the **final consensus Results counts**, not the earlier human-removal counts
reported when describing the original searches. The distributed ASySD validation files
use representative-sensitive `Unique`/`Duplicate` removal labels; therefore MetaEvidence
uses `RemovalLabelBenchmark` for this corpus rather than pretending those labels are a
publication-group partition. The paper states that the underlying datasets and analysis
code are available through OSF. These datasets are suitable candidates for external
validation because they were not used to create MetaEvidence.

### Deduplication benchmark B — contemporary multi-tool comparison
Bateup et al. (2026) evaluated eight tools on five rerun Cochrane-review searches. If
those gold-standard files are obtainable under their sharing terms, they should be used
as an additional independent benchmark. MetaEvidence should be compared on the same
record sets and outcome definitions; do not compare published timing values measured on
different hardware as if they were head-to-head timings.

### Query-translation benchmark
The 2025 AHRQ guide identifies Polyglot Search as a dedicated translation tool and
explicitly warns that translations require expert review. A prior randomized trial of
Polyglot found faster translation with fewer errors but still substantial residual error.
We therefore propose an expert-searcher reference benchmark rather than treating any
single automated translator as ground truth.

Recommended design:
- at least 30 systematic-review search strategies from multiple clinical/scientific
  domains;
- expert reference translations per target database;
- blinded independent adjudication of disagreements;
- execute expert and MetaEvidence translations on the same day;
- compare retrieval IDs and eligible-study recall;
- report results per database and macro-averaged across strategies.

### Study-linkage benchmark
Cochrane requires reports from the same study to be collated and lists registry IDs,
authors, sponsor/location, interventions, participant counts and study dates as useful
linkage evidence. A benchmark should therefore contain manually adjudicated report
families, not only identical citations.

Candidate sources:
- ClinicalTrials.gov trial-publication links;
- public Trials-to-Publications results as candidate evidence, followed by independent
  manual adjudication;
- included-study report families from published systematic reviews where multiple
  reports are explicitly linked.

The final test set must remain untouched until rules, thresholds and calibration are
frozen.

## 3. Data splitting and leakage prevention

For M4/M5 probabilistic evaluation:
1. development set — feature/rule development;
2. calibration set — Platt calibration and threshold selection;
3. locked external test set — final performance only.

Pairs from the same publication cluster/study family must not be split across development
and test partitions. Query strategies from the same review should also remain in one
partition.

## 4. Calibration

Report:
- Brier score;
- expected calibration error;
- reliability plot/table;
- calibration intercept/slope when an external statistical workflow is used.

The engineering scores in v0.8 are not called calibrated probabilities until fitted and
validated on independent labels.

## 5. Threshold selection

Automatic merge/link thresholds should be selected on the calibration set with a
pre-specified minimum precision constraint (for example >= 0.995 where the data support
it), because a false merge/link can remove or double-count evidence. The human-review
band is evaluated as a workload/safety trade-off.

## 6. Statistical reporting

For each external dataset report confusion matrices and 95% confidence intervals.
Prefer bootstrap confidence intervals at the review/dataset level for aggregate metrics.
For paired comparisons, preserve the paired unit (same review/search strategy) and avoid
treating millions of citation pairs as independent evidence of superiority.

## 7. M8 software components

- `QueryTranslationBenchmark`
- `RetrievalSetMetrics`
- `DeduplicationAblationBenchmark`
- `StudyLinkageAblationBenchmark`
- `MetadataStressBenchmark`
- `ScalabilityBenchmark`
- `BlockingRecallBenchmark` for candidate-generation recall and pair-reduction fraction
- `bootstrap_proportion_ci`
- deterministic synthetic QA generators
- `ScientificBenchmarkBundle` with CSV/JSON and SHA-256 manifest

## 8. Claims policy

Before external validation, acceptable wording is:

> MetaEvidence provides a reproducible benchmark harness for evaluating query
> translation, deduplication, study linkage, calibration, robustness and scalability.

Do NOT claim:
- superior deduplication performance;
- externally calibrated probabilities;
- first-ever trial-publication linkage;
- exhaustive retrieval of all papers;
- PRISMA compliance solely because the package generated a report.

## 9. Planned publication analyses

1. Baseline external performance table by dataset.
2. Calibration table/curve.
3. Missing-metadata degradation curves.
4. Feature ablation table.
5. Query translation empirical-recall table by source database.
6. Study-linkage error taxonomy.
7. Scalability curve.
8. Comparison with established tools under matched datasets/settings.
9. Sensitivity analyses for merge/link thresholds.
10. Reproducible benchmark artifact deposited with versioned DOI.
