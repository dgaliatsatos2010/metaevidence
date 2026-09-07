# Protocol amendment: ASySD Neuroimaging integrity metadata

**Date:** 2026-09-07
**Scope:** Integrity metadata only; no algorithmic or outcome-informed tuning.

## Trigger

The ASySD development/calibration workflow failed closed while validating the official
`NeuroImaging_duplicates_labelled.csv` file. The distributed file contained 3,438 records,
1,298 records labelled `Duplicate`, and therefore 2,140 records labelled `Unique`.

The frozen manifest had expected 3,434 records and 2,136 retained records, following the
Results narrative/Table 6 of Hair et al. (2023).

## External source reconciliation

Hair et al. (2023) is internally inconsistent for this corpus:

- Table 3 reports 3,438 citations obtained.
- The Results narrative reports N=3,434.
- Table 6 reports 1,298 true duplicate removals and 2,136 remaining (total 3,434).
- Every Table 7 confusion matrix sums to 3,438.
- For ASySD specifically: TP=1,279, TN=2,137, FN=19, FP=3; total=3,438 and
  gold negatives TN+FP=2,140.

The distributed OSF labelled file therefore agrees with Table 3 and the published performance
denominators in Table 7.

## Amendment

The Neuroimaging integrity metadata is corrected to:

- expected records = 3,438
- expected gold duplicate removals = 1,298 (unchanged)
- expected gold retained/publications = 2,140

## Blinding and method integrity

The triggering workflow aborted during the integrity check before Neuroimaging MetaEvidence
scoring and before publication of any result artifact or statistical summary. This amendment
does not depend on MetaEvidence Neuroimaging performance.

The deduplication engine, features, weights, thresholds, blocking rules, retention rules,
gold-label semantics, dataset roles, and held-out-test policy are unchanged.
