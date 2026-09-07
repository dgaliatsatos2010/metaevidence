# Dedicated MetaEvidence GitHub repository bootstrap

The intended public repository is:

`dgaliatsatos2010/metaevidence`

A repository lookup performed during the v0.9.9 preparation returned **404 / Not Found**, so that exact repository did not exist under the account at that checkpoint. The available ChatGPT GitHub connector can modify existing repositories but does not expose repository creation; therefore the first empty repository must be created once through GitHub itself.

## One-time creation

Create a **public** repository named `metaevidence` under `dgaliatsatos2010` with:

- no generated README;
- no generated `.gitignore`;
- no generated license (the package already contains the MIT license);
- default branch `main`.

Then upload/push the contents of the MetaEvidence v0.9.9-dev source package to the repository root. Do not upload the outer `MetaEvidence_v0.9.9-dev/` directory as an extra nesting level.

## Repository root expected after upload

Key paths should include:

- `pyproject.toml`
- `README.md`
- `LICENSE`
- `CITATION.cff`
- `src/metaevidence/`
- `tests/`
- `benchmarks/`
- `docs/`
- `.github/workflows/ci.yml`
- `.github/workflows/external-validation.yml`
- `.github/workflows/publish-pypi.yml`

Do **not** commit downloaded third-party ASySD CSV or Beller/IEBH XML benchmark files.

## First GitHub checks

After the initial push:

1. Confirm the `CI` workflow passes on Python 3.10, 3.11, 3.12 and 3.13.
2. Open **Actions → External validation → Run workflow**.
3. Run `beller-secondary` first, preferably one small corpus (`tafenoquine.xml`) as a smoke run.
4. If successful, rerun with `beller_dataset=all` to execute the five-corpus matrix.
5. Download the `beller-external-validation-summary` artifact and preserve its workflow run ID/URL and hashes.
6. Run `asysd-development-calibration` next if OSF is reachable from GitHub Actions.
7. Do not run `asysd-held-out` until development/calibration decisions are frozen. Held-out execution requires `confirm_held_out=true` and the CLI `--allow-held-out` gate.

## PyPI release gate

Do not publish the final stable release merely because CI passes. The `publish-pypi.yml` workflow is triggered only by a GitHub Release and expects a protected `pypi` environment configured for PyPI Trusted Publishing. External-validation results and manuscript result tables should be frozen first.

## Zenodo gate

After the public GitHub release and final tag are stable, connect the repository to Zenodo/GitHub archival, create the versioned archival release, record the DOI in `CITATION.cff`, README and manuscript, and regenerate final checksums.
