# MetaEvidence v0.9.7-dev

## GitHub-executable frozen external validation

This development release adds a manual-only GitHub Actions workflow for executing the already frozen external-validation protocols on a networked GitHub-hosted runner. It does **not** change the publication-deduplication scoring engine, thresholds, blocking rules, or retention semantics.

### Added

- `.github/workflows/external-validation.yml` with explicit `workflow_dispatch` only.
- Parallel matrix execution for the five pinned IEBH/Beller EndNote XML corpora.
- Single-file `--file` selection for `fetch-beller-endnote` and `validate-beller-endnote`.
- Dual held-out protection for ASySD: a workflow confirmation gate plus the existing CLI `--allow-held-out` gate.
- Results-only artifact policy; downloaded third-party gold files are never uploaded as workflow artifacts.
- Per-job runner provenance: MetaEvidence version, Git commit, Python/runtime information and external-source manifest.
- Aggregated Beller benchmark CSV/JSON artifact.
- `docs/GITHUB_EXTERNAL_VALIDATION.md` describing leakage prevention, data handling and reproducibility requirements.

### Validation semantics

- The primary Beller/IEBH endpoint remains blind `engine_quality` retention.
- The ASySD held-out Depression/SRSR sets remain inaccessible to normal development/calibration runs.
- The deduplication engine remains frozen from v0.9.4 for external performance claims.
- No external performance values are claimed by this release until the workflow is executed on the authentic source bytes.
