# M4 — Confidence-aware Multi-stage Deduplication (CMD)

## Purpose

M4 turns publication deduplication from a binary hidden rule into an auditable record-linkage process. For every candidate pair, MetaEvidence produces:

- normalized bibliographic features;
- an estimated match probability;
- the contribution of each feature to the score;
- deterministic identity/conflict rules;
- one of three actions: `AUTO_MERGE`, `REVIEW`, or `KEEP_SEPARATE`;
- provenance-preserving merged records;
- a review queue for ambiguous pairs;
- benchmark metrics and threshold/calibration utilities.

The default numerical score is **not yet an empirically calibrated probability**. In v0.4 it is an expert-weighted logistic engineering model. It becomes a calibrated probability only after a calibrator is fitted on labelled validation data.

## Why this is not claimed as the first deduplication algorithm

Strong deduplication tools already exist. Examples include the Systematic Review Assistant Deduplication Module (SRA-DM), Deduklick, and ASySD. ASySD reported sensitivity of roughly 0.95–0.99 across evaluated datasets, and Deduklick has reported very high precision/recall in its development study. A 2026 comparison of eight tools found that no single tool dominated every outcome.

Therefore, MetaEvidence does **not** claim novelty merely from fuzzy matching, rule-based matching, similarity scores, or explainability. The intended contribution is the integration of:

1. cross-database retrieval provenance;
2. explicit uncertainty and human-review bands;
3. probability calibration on external labelled datasets;
4. source-aware metadata conflict preservation;
5. publication-form safety rules;
6. later study-level publication linkage that intentionally distinguishes a duplicate citation from a distinct report of the same study;
7. reproducible benchmark and threshold selection artifacts.

Key comparison literature:

- Rathbone et al. Better duplicate detection for systematic reviewers: evaluation of Systematic Review Assistant-Deduplication Module. *Systematic Reviews*. 2015;4:6. doi:10.1186/2046-4053-4-6.
- Borissov et al. Reducing systematic review burden using Deduklick: a novel, automated, reliable, and explainable deduplication algorithm to foster medical research. *Systematic Reviews*. 2022;11:172. doi:10.1186/s13643-022-02045-9.
- Hair et al. The Automated Systematic Search Deduplicator (ASySD): a rapid, open-source, interoperable tool to remove duplicate citations in biomedical systematic reviews. *BMC Biology*. 2023;21:189. doi:10.1186/s12915-023-01686-z.
- Bateup et al. Evaluating the accuracy and speed of eight deduplication tools: A comparative study. *Research Synthesis Methods*. 2026. doi:10.1017/rsm.2026.10100.

## Feature model

Current pairwise features include:

- exact normalized DOI agreement;
- conflicting DOI;
- exact/conflicting PMID, Web of Science UT, Scopus EID, and OpenAlex ID;
- title character similarity;
- title token Jaccard similarity;
- author-surname overlap;
- publication-year compatibility;
- journal-title similarity;
- volume, issue, and page agreement when available;
- publication-form conflict (e.g. preprint vs journal article).

The current uncalibrated base model uses a transparent logistic score:

\[
\hat{p}_{raw} = \sigma\left(\beta_0 + \sum_j \beta_j x_j\right)
\]

where `sigma` is the logistic function, `x_j` are normalized agreement/conflict features, and `beta_j` are versioned expert-defined weights. Each non-zero contribution is returned to the caller.

The weights are intentionally visible in `ConfidenceDeduplicationEngine.DEFAULT_WEIGHTS`; they are not hidden model parameters.

## Deterministic safety rules

Probabilistic scoring does not override strong bibliographic evidence.

### Identity anchors

- exact normalized DOI -> near-certain identity floor;
- exact strong database identifier -> near-certain identity floor.

### Safety gates

- conflicting non-empty DOIs strongly block automatic merging;
- conflicting same-system identifiers constrain merging;
- fuzzy-title auto-merge requires positive author evidence;
- a short/exact title without corroborating metadata is not sufficient for automatic merge;
- different publication forms (such as a preprint and subsequent journal article) remain separate publications unless a strong shared identifier demonstrates that the source classifications themselves differ.

The last rule is important because publication-level deduplication and study-level linkage are different tasks. M4 should remove duplicate *citations of the same publication*. M5 will link distinct publications that may describe the same study.

## Three-way decision model

Default engineering thresholds in v0.4 are:

- `AUTO_MERGE`: probability >= 0.985;
- `REVIEW`: 0.75 <= probability < 0.985;
- `KEEP_SEPARATE`: probability < 0.75.

These defaults are provisional. They must be re-estimated using labelled development/validation data before publication-quality claims are made.

A particularly important target is a very low false-merge rate. In systematic reviews, incorrectly deleting a unique reference can be more damaging than retaining a duplicate for later screening.

## Candidate generation and scalability

For <= 2,000 records, v0.4 uses exhaustive pair assessment to maximize candidate recall during research development.

For larger datasets, deterministic blocking is used to reduce O(n^2) comparisons. Blocks currently use:

- persistent identifiers;
- exact normalized title;
- title-token signatures with compatible year windows;
- lead-author/year windows;
- journal/volume/pages when available.

Blocking performance itself must be benchmarked because a missed candidate can never be recovered by the scorer. M8 will therefore report both candidate-generation recall and final deduplication performance.

## Provenance-preserving cluster merge

Only `AUTO_MERGE` edges create publication clusters. `REVIEW` edges do not silently merge records.

Within an auto-merge cluster, MetaEvidence selects the highest-information record as the representative and then:

- unions all `SourceHit` objects;
- fills missing canonical fields from other members;
- preserves conflicting values under `metadata["metaevidence_conflicts"]`;
- records cluster size and original member indices.

This design prevents deduplication from destroying the source-level evidence needed for PRISMA accounting and later audit.

## Calibration

`PlattCalibrator` provides a dependency-free logistic calibration layer. It must be fitted on labelled data that are separate from the final evaluation set.

Example:

```python
from metaevidence import PlattCalibrator

calibrator = PlattCalibrator().fit(
    validation_probabilities,
    validation_labels,
)
```

Then:

```python
from metaevidence import ConfidenceDeduplicationEngine

engine = ConfidenceDeduplicationEngine(calibrator=calibrator)
```

For the final paper, calibration should be evaluated using at least Brier score and calibration error/curves, with dataset-level validation that avoids leakage between related citation pairs.

## Benchmarking

The v0.4 benchmark layer provides:

- sensitivity/recall;
- specificity;
- precision;
- F1;
- accuracy;
- false-merge rate;
- Brier score;
- expected calibration error;
- review fraction/workload;
- threshold optimization subject to a minimum precision requirement.

Recommended primary safety metric: **false-merge rate / specificity**.

Recommended performance reporting: precision, recall, F1, specificity, false-merge count, duplicates retained, human-review burden, runtime, and calibration.

## Required validation before publication claims

M4 is an implementation milestone, not yet a validated scientific result. Before claiming superiority or calibrated probability, we need:

1. public labelled deduplication datasets where licensing permits reuse;
2. independent development, calibration, and test partitions at the review/dataset level;
3. comparison with DOI-only and exact-title baselines;
4. comparison with established tools where technically and legally feasible;
5. missing-metadata stress tests;
6. multilingual/non-English tests;
7. preprint/conference/journal-form stress tests;
8. blocking-recall analysis for large datasets;
9. ablation studies for each feature group;
10. runtime and memory scaling experiments.

## Current non-claims

v0.4 does not claim that its default probability is calibrated, that its default thresholds are optimal, or that it outperforms ASySD, Deduklick, SRA-DM, Rayyan, Covidence, or other established tools. Those are empirical questions reserved for M8.
