# MetaEvidence v0.9.11-dev

## ASySD Neuroimaging integrity-metadata correction

This release corrects only the pre-execution integrity metadata for the ASySD Neuroimaging corpus.

- `expected_records`: 3434 -> 3438
- `expected_gold_publications`: 2136 -> 2140
- `expected_gold_duplicates_removed`: remains 1298

The official OSF labelled CSV contains 3438 records. Hair et al. (2023) Table 3 also reports
3438 citations obtained, and all published Table 7 confusion matrices sum to 3438. For ASySD,
TN + FP = 2137 + 3 = 2140 negatives. The Results narrative and Table 6 instead report N=3434
and 2136 remaining, creating an internal source inconsistency.

The correction was triggered by a fail-closed integrity check and was made before Neuroimaging
MetaEvidence scoring. No Neuroimaging result artifact or statistical summary was published by
the failed run.

No changes were made to the frozen deduplication method, matching features, scores, thresholds,
weights, blocking/retention rules, gold labels, dataset roles, or held-out authorization policy.

Frozen deduplication-engine SHA-256:
`3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50`
