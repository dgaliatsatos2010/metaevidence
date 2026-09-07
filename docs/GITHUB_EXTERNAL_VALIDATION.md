# GitHub Actions external-validation workflow

MetaEvidence v0.9.9-dev includes `.github/workflows/external-validation.yml`, a **manual-only** workflow for executing the frozen external-validation protocols on a GitHub-hosted runner with normal Internet access.

## Why manual-only?

External gold standards are not unit tests. In particular, the ASySD Depression and SRSR datasets are frozen held-out test sets. Running them automatically on every push or pull request would expose held-out outcomes during development and create test-set leakage. The workflow therefore uses `workflow_dispatch` only.

## Secondary pinned EndNote benchmark

Choose `benchmark = beller-secondary`. The workflow:

1. creates a matrix over all five pinned XML corpora, or a selected single corpus;
2. downloads each file from `IEBH/dedupe-sweep` at frozen commit `66a7ed5f5ea95cafc5f76ba6ec60bb4eb3cd381a`;
3. validates byte size and canonical Git blob SHA before analysis;
4. runs the frozen blind `engine_quality` retention benchmark;
5. stores results, runtime provenance and the external-source manifest;
6. uploads **results only**. Raw third-party XML is never uploaded as an artifact or committed to MetaEvidence;
7. aggregates dataset-level JSON summaries into CSV/JSON artifacts.

The workflow runs one dataset per matrix job. This isolates failures and prevents the large `diabetes.xml` corpus from blocking smaller datasets.

## ASySD development/calibration

Choose `benchmark = asysd-development-calibration`. The workflow downloads the five official files from OSF node `2b8uq`, but executes only the manifest roles `development` and `calibration`.

## ASySD held-out test

Choose `benchmark = asysd-held-out` **and** explicitly set `confirm_held_out = true`. A guard job exits before download/evaluation if that confirmation is absent. The CLI also requires `--allow-held-out`, giving two independent gates.

Held-out results must not be used to alter thresholds, features, blocking, calibration, or retention rules. Any such change requires a new prospectively declared external test set.

## Artifact policy

The workflow deliberately excludes third-party raw benchmark data from uploaded artifacts. Artifacts contain only:

- blind performance metrics;
- retention-reproduction metrics when generated;
- record-level predictions/results created by MetaEvidence;
- source hashes and immutable source identifiers;
- MetaEvidence version/commit and Python/runtime provenance;
- aggregate JSON/CSV result tables.

Before journal submission or archival release, save the workflow run URL/ID and the result artifact hashes in the reproducibility supplement.
