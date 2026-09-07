# M5 — Study-Level Publication Linkage (SPL)

## Purpose

Publication deduplication and study linkage are different scientific tasks.

- **M4 asks:** are two records the same publication?
- **M5 asks:** are two distinct publications reports from the same underlying study?

This distinction is essential in evidence synthesis. Protocols, conference abstracts, preprints, primary result papers, subgroup analyses, secondary outcome papers and long-term follow-ups may all belong to one study. They should not be deleted as citation duplicates, but they also should not be counted as independent studies in a meta-analysis.

## Current M5 architecture

The core M5 implementation provides:

1. trial-registry identifier extraction and normalization;
2. publication-role classification;
3. a separate study-link feature vector;
4. a transparent provisional study-link probability;
5. four-way decisions:
   - `SAME_STUDY`
   - `REVIEW`
   - `DIFFERENT_STUDY`
   - `DUPLICATE_PUBLICATION`
6. family-level clustering with stable `STUDY-...` identifiers;
7. transitive cluster-consistency safeguards;
8. human-review queues;
9. explicit double-counting risk warnings;
10. JSON/CSV exports for families, edges and review queues;
11. pair-level benchmark and threshold-selection utilities.

## Registry identifiers

The current extractor recognizes normalized forms for common identifiers including:

- ClinicalTrials.gov (`NCT`)
- ISRCTN
- ANZCTR/ACTRN
- DRKS
- ChiCTR
- UMIN/JPRN-UMIN
- TCTR
- IRCT
- NTR
- CTRI
- EudraCT/EUCTR

The extractor scans title and abstract plus registry-oriented metadata fields. Full text can be supplied explicitly through metadata, but M5 does **not** assume that every registry-number mention means that an article reports that trial. Reviews may mention many registry IDs, and full-text location can matter.

## Publication roles

The prototype classifies reports into:

- `PROTOCOL`
- `PRIMARY_RESULTS`
- `SECONDARY_ANALYSIS`
- `SUBGROUP_ANALYSIS`
- `FOLLOW_UP`
- `CONFERENCE_ABSTRACT`
- `PREPRINT`
- `REVIEW`
- `OTHER`

Explicit structured metadata (`report_role`) takes priority over heuristic title/type classification.

## Feature vector

For a candidate pair \(i,j\), M5 derives features such as:

- exact shared registry identifier;
- contradictory/disjoint registry identifiers;
- multi-registry ambiguity;
- shared study acronym;
- title-token similarity;
- investigator/author overlap;
- publication-year compatibility;
- sample-size compatibility;
- country/site similarity;
- intervention/exposure similarity;
- population/condition similarity;
- recruitment-period compatibility;
- complementary publication roles;
- review/meta-analysis safeguard.

The current engineering score uses a logistic form:

\[
\hat p_{ij}=\sigma\left(\beta_0+\sum_k w_k x_{ijk}\right),
\]

where the default weights are transparent expert-defined values. **The resulting number is not yet claimed to be an externally calibrated probability.** Calibration must be fitted only on development/calibration data and evaluated on an independent test set.

## Strong evidence and safety rules

### Shared registry ID

A shared single registry identifier between two non-review reports is treated as very strong same-study evidence. This can link, for example, a protocol to a primary report or a primary report to a follow-up.

### Review safeguard

A systematic review or meta-analysis may mention a registry ID without being a report of that trial. Therefore a review record cannot be automatically linked into a trial family solely through registry-number overlap.

### Disjoint registry IDs

Different registry IDs block automatic `SAME_STUDY`. The pair can remain for manual review because cross-registration exists and a trial can occasionally have identifiers in more than one registry.

### Multi-registry ambiguity

If one report contains multiple non-identical registry IDs and only one overlaps another report, automatic family linkage is blocked. This prevents a multi-trial publication from becoming a bridge that incorrectly joins multiple trials.

### Cluster-consistency safeguard

Pairwise similarity is not enough for graph clustering. Consider:

```
A (NCT-1)  <->  B (no registry)  <->  C (NCT-2)
```

Even if both pairwise edges score highly, joining all three would combine two incompatible registered trials. Before each union operation, M5 checks the registry evidence already accumulated by both candidate clusters. A merge that would combine disjoint registry families is converted to `REVIEW`.

This is a deliberate protection against transitive false linkage.

## Study families

Accepted edges create a publication-family graph. A family may look like:

```
STUDY-A1B2C3D4E5F6
├── protocol
├── conference abstract
├── primary results article
├── subgroup analysis
└── five-year follow-up
```

The stable family ID is derived from normalized registry identifiers when available. When no registry ID exists, a deterministic publication fingerprint is used.

Each family retains:

- member indices;
- registry IDs;
- report roles;
- source databases;
- a conservative family confidence based on accepted linkage edges.

## Double-counting risk

If multiple outcome-bearing reports belong to one family, MetaEvidence emits a `HIGH` double-counting risk warning. It does not select which result belongs in a specific meta-analysis; that remains an outcome/timepoint/design decision by the reviewer.

Example:

```
STUDY-...
├── primary results
├── subgroup analysis
└── follow-up

Risk: HIGH
Reason: do not count these reports as three independent studies.
```

Families containing multiple reports but fewer than two clearly outcome-bearing roles receive a general `REVIEW` warning.

## Exports

`StudyLinkageResult` can write:

```python
result.write_json("study_linkage.json")
result.write_families_csv("study_families.csv")
result.write_edges_csv("study_edges.csv")
result.write_review_csv("study_review_queue.csv")
result.write_double_counting_csv("double_counting_risks.csv")
```

This supports auditability, downstream screening tools and later PRISMA/review reporting.

## Benchmarking

M5 includes `StudyLinkageBenchmark` for labelled publication pairs. Current metrics include:

- sensitivity/recall;
- specificity;
- precision;
- F1;
- accuracy;
- false-link rate;
- Brier score;
- review fraction;
- precision-constrained threshold optimization.

### Required external validation before performance claims

A publishable validation should use independently curated study families and should separate development/calibration/test data at the review or study-family level. Pairwise random splits are unsafe because reports from the same trial can leak across splits.

Recommended evaluation strata:

1. registered randomized trials;
2. observational cohorts;
3. diagnostic studies;
4. protocols vs primary reports;
5. conference abstract vs journal article;
6. preprint vs journal article;
7. primary vs secondary/subgroup/follow-up reports;
8. missing registry ID;
9. conflicting or multiple registry IDs;
10. sparse/missing authors, sample size or dates;
11. multilingual titles/metadata;
12. multi-study publications.

Important baselines include registry-ID-only linkage, author/title heuristics, and existing trial-publication linking approaches where comparable datasets and interfaces permit fair evaluation.

## Novelty positioning

MetaEvidence does **not** claim to be the first system that links trials to publications. Prior work and currently maintained tools already use registry identifiers, metadata, natural-language processing and machine learning for trial-publication linkage.

The intended contribution is broader and must be validated empirically: a single evidence-synthesis framework that combines cross-database retrieval, auditable query translation, provenance-preserving publication deduplication, uncertainty-aware multi-registry study-family linkage, graph-level consistency checks, double-counting warnings, and reproducible exports.

## Key methodological references informing M5

- Cochrane Handbook, Chapter 5: systematic reviews treat studies rather than reports as the unit of interest; multiple reports of one study should be collated, not discarded.
- Bashir et al. / Dunn et al.: systematic work on linking clinical-trial registrations to published results demonstrates that automatic registry-publication links are incomplete and manual processes remain important.
- Smalheiser/Holt and collaborators: Trials to Publications and later full-text registry-mention work demonstrate machine-learning and registry-number approaches for finding trial-linked publications, including the importance of where registry identifiers occur in article text.

These prior systems are treated as related work and potential benchmark comparators, not as features that MetaEvidence can claim as first-in-field innovations.
