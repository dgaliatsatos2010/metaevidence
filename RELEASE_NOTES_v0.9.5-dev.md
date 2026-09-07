# MetaEvidence v0.9.5-dev

## External-validation reproducibility hardening

This development release freezes the public ASySD validation contract in executable Python code. It does not add or claim external performance results.

### Added

- `ASySDPerformanceContract` and `calculate_asysd_performance_contract()` implementing the official record-level confusion-matrix convention.
- `metaevidence fetch-asysd` to retrieve the five official validation files from OSF node `2b8uq` when OSF is reachable.
- `metaevidence validate-asysd` to execute the frozen external-validation manifest.
- Per-dataset `asysd_metric_contract.json`.
- Consolidated `asysd_compatibility_summary.json` and `.csv`.
- Exact blind-versus-gold-preferred retention reporting using one unchanged MetaEvidence clustering.

### Interpretation

`blind_engine_quality` is the primary deployable result because representative selection is blind to the gold labels. `gold_preferred_reproduction` is a secondary reproduction endpoint that mirrors the retention consequence of ASySD's public `keep_label="Unique"` validation setting; it must not be used as the primary external claim.

### Verification

- 127/127 automated tests pass.
- External ASySD CSV execution remains pending because the official OSF node is not retrievable from the current runtime.
- No performance values are imputed or simulated as external results.
