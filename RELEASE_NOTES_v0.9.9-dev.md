# MetaEvidence v0.9.9-dev

## Purpose

This is a **validation-infrastructure-only** checkpoint immediately before authentic external execution. It does not change the publication-deduplication algorithm, matching features, weights, thresholds, blocking rules, representative-retention rules, gold-label semantics, or held-out role assignments.

The frozen `src/metaevidence/dedup.py` SHA-256 remains:

`3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50`

This is identical to the v0.9.8 tree and the engine frozen from v0.9.4-dev.

## Added

- `benchmarks/frozen_validation_lock.json`.
- `metaevidence verify-validation-lock LOCK --repository-root ROOT`.
- Pre-install repository verifier: `benchmarks/verify_frozen_validation.py`.
- `metaevidence write-validation-run-manifest ...` for hashing already-computed result bundles and recording runtime/GitHub provenance.
- Manifest-derived Beller dataset matrix in the manual GitHub Actions workflow.
- Lock re-verification in guard, scoring and reporting jobs.
- Workflow-page manuscript-oriented result summary.
- 90-day retention for results-only external-validation artifacts.

## Frozen lock

The lock covers method-critical code, the two frozen benchmark manifests, and validation-runner files. External validation fails before scoring if any locked SHA-256 differs.

The Beller source itself remains independently protected by exact byte size and canonical Git blob SHA-1 checks at the pinned `IEBH/dedupe-sweep` commit.

## No external performance claim yet

No authentic external performance number is introduced by this checkpoint. The local ChatGPT/container environment could not retrieve the 1,292,166-byte pinned `tafenoquine.xml` through the available connector because that route has a 1,000,000-byte fetch limit. The correct path, size and Git blob identity were established, but partial data were not scored.

The authentic evaluation is therefore intentionally delegated to the manual network-enabled GitHub Actions workflow after the dedicated repository is created.

## QA

- 147/147 automated tests passed.
- `python -m compileall -q src benchmarks` passed.
- Frozen validation lock passed all 17 locked-file checks.
- GitHub Actions YAML parsed successfully in local QA.
- Wheel built successfully: `metaevidence-0.9.9.dev0-py3-none-any.whl`.
- Clean wheel installation imported version `0.9.9.dev0` and the new validation modules successfully.
- Console-script metadata exposes `metaevidence = metaevidence.cli:main`.
