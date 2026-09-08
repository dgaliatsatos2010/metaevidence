# MetaEvidence v1.0.0 release-lock transition

The protected external-validation runs were executed under the v0.9.11 development
runner and its frozen validation lock. Before the public v1.0.0 software release,
package-version metadata in `pyproject.toml` and `src/metaevidence/__init__.py` was
updated from the development version to `1.0.0`.

Those two files are included in the validation lock as runner/package metadata.
Their byte hashes therefore changed even though the publication-deduplication
decision engine and benchmark semantics did not.

For provenance, the exact pre-release external-execution lock is preserved as:

`benchmarks/frozen_validation_lock_v0.9.11_external_execution.json`

The active `benchmarks/frozen_validation_lock.json` was synchronized only to the
v1.0.0 package-metadata bytes and records `validation_runner_version = "1.0.0"`.

The frozen publication-deduplication engine remains:

`src/metaevidence/dedup.py`

SHA-256:

`3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50`

No feature, weight, threshold, blocking rule, retention rule, gold-label mapping,
held-out role, or benchmark decision semantics were changed during this release
transition.
