# MetaEvidence v0.5.0-dev — M5 Study-Level Publication Linkage

## Added

- `StudyLinkageEngine` for linking distinct reports to one underlying study.
- Explicit separation between publication deduplication and study linkage.
- Four relationship decisions: `SAME_STUDY`, `REVIEW`, `DIFFERENT_STUDY`, `DUPLICATE_PUBLICATION`.
- Normalization/extraction of common international trial-registry identifiers.
- Publication-role classification: protocol, primary, secondary, subgroup, follow-up, conference abstract, preprint, review, other.
- Study-link feature vector using registry, acronym, investigator, date, sample-size, country, intervention and population evidence.
- Transparent provisional logistic scoring and optional external calibrator hook.
- Review/meta-analysis safeguard for incidental registry mentions.
- Disjoint-registry conflict gate.
- Multi-registry ambiguity safeguard.
- Cluster-level consistency checking to prevent transitive bridging of incompatible registered trials.
- Stable deterministic `STUDY-...` family identifiers.
- Study-family provenance across source databases.
- Double-counting risk warnings for meta-analysis.
- JSON and CSV exports for families, all pair edges, review queue and double-counting risks.
- `StudyLinkageBenchmark` with pair-level performance metrics and precision-constrained threshold tuning.
- `docs/M5_STUDY_LINKAGE.md` and `examples/study_linkage.py`.

## Scientific status

The default study-link score is an expert-weighted engineering model and is **not yet claimed to be an externally calibrated probability**. No superiority claim is made over existing trial-publication linkage methods. Independent labelled development, calibration and external-test datasets remain required.

## QA

- Full test suite: **52/52 tests passing**.
- Python compile check: **PASS**.
- Wheel build: **PASS**.
- Clean wheel installation/import: **PASS**.
- Clean-install smoke test: shared NCT protocol/results pair -> `SAME_STUDY` at the provisional registry-anchored score.
- Package version: `0.5.0.dev0`.
