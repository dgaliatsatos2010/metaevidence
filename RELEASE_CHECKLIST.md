# MetaEvidence public release checklist

A public GitHub/PyPI/Zenodo release should not be made merely because the package builds. Complete the gates below.

## Scientific gates

- [ ] Obtain external gold-standard files from their official sources under applicable terms.
- [ ] Record immutable source-file SHA-256 values.
- [ ] Pass `strict=True` integrity checks against the frozen external benchmark plan.
- [ ] Complete development datasets without inspecting held-out outcomes.
- [ ] Freeze feature definitions and blocking strategy.
- [ ] Fit calibration/thresholds on the predeclared calibration dataset only.
- [ ] Lock model/configuration before Depression and SRSR held-out tests.
- [ ] Run all Bateup 2026 sets as independent benchmark 2 without tuning.
- [ ] Report all datasets and error cases, not only favorable results.
- [ ] Separate synthetic QA results from external performance claims.

## Software gates

- [ ] All tests pass on Python 3.10–3.13 in GitHub Actions.
- [ ] Clean wheel and sdist build.
- [ ] Clean-environment installation/import test.
- [ ] No secrets in repository history.
- [ ] License and third-party data redistribution reviewed.
- [ ] README/API examples verified against the release wheel.
- [ ] Version synchronized in `pyproject.toml`, `__init__.py`, `CITATION.cff`, changelog and release notes.
- [ ] Git tag matches version.

## Distribution gates

- [ ] Create public GitHub repository and set repository URLs in package metadata.
- [ ] Enable branch protection / required CI as appropriate.
- [ ] Configure PyPI Trusted Publishing for the GitHub `pypi` environment.
- [ ] Confirm the final distribution name is available on PyPI immediately before first upload.
- [ ] Publish a release candidate before stable `1.0.0`.
- [ ] Connect GitHub repository to Zenodo and archive the release.
- [ ] Add Zenodo DOI/version DOI to release metadata and citation instructions.
- [ ] Archive external benchmark result bundle without redistributing restricted source records.

## External-validation release gate

- [ ] Dedicated `dgaliatsatos2010/metaevidence` repository created (current lookup returns 404 / unused under this account).
- [ ] Manual `External validation` workflow executed for all five pinned Beller/IEBH corpora.
- [ ] Result artifacts downloaded and SHA-256 archived; raw third-party XML not archived in the release.
- [ ] ASySD development/calibration workflow executed before any held-out run.
- [ ] Thresholds/features/calibration frozen before setting `confirm_held_out=true`.
- [ ] Held-out workflow run URL/ID and artifact hashes recorded in the manuscript supplement.
