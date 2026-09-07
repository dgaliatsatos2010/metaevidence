# MetaEvidence v0.9.9-dev — external-validation readiness

## Status

**Ready for authentic external execution; empirical external performance remains intentionally unreported.**

The current environment could not retrieve the pinned `tafenoquine.xml` because the available GitHub raw-file connector enforces a 1,000,000-byte limit while the frozen file is 1,292,166 bytes. No partial corpus was scored.

## Frozen method

The publication-deduplication engine is unchanged from v0.9.8 and the engine frozen from v0.9.4-dev.

`src/metaevidence/dedup.py` SHA-256:

`3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50`

Six method-critical files were byte-compared with v0.9.8 and were identical:

- `dedup.py`
- `models.py`
- `endnote_gold.py`
- `external_validation.py`
- `external_runner.py`
- `asysd_compat.py`

## Integrity controls

- 17 locked method/manifest/runner files verified by SHA-256.
- Beller files are independently checked at download time by exact size and canonical Git blob SHA-1.
- The Beller Actions matrix reads the authoritative frozen manifest directly.
- ASySD held-out execution retains two explicit gates.
- Every executed result tree receives a cryptographic `validation_run_manifest.json`.
- Workflow artifacts omit raw third-party benchmark files.

## Local QA

- 147/147 tests passed.
- compileall passed.
- wheel build passed.
- clean wheel install passed with version `0.9.9.dev0`.
- workflow YAML parsing passed.
- corrected CLI frozen-lock smoke test returned 0.

## Remaining external step

A dedicated GitHub repository is required because the connected GitHub tooling available in this session does not expose repository creation and no public `dgaliatsatos2010/metaevidence` repository was found during the latest lookup.

After creating the empty repository, push this source tree, run ordinary CI, then manually execute:

1. `beller-secondary` + `tafenoquine.xml`;
2. `beller-secondary` + `all` if the smoke run succeeds;
3. ASySD development/calibration according to the frozen manifest;
4. held-out ASySD only after all permitted decisions are frozen.

Do not modify the algorithm in response to these outcomes. Manuscript performance tables should be populated only from the archived authentic result artifacts.
