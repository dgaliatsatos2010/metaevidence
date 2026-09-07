# Reproducible release procedure

## 1. Start from a clean checkout

```bash
git status --short
python -m pytest -q
python -m compileall -q src
```

## 2. Build distributions

```bash
python -m pip install build
python -m build
```

## 3. Test the wheel in a clean environment

```bash
python -m venv /tmp/metaevidence-release-test
/tmp/metaevidence-release-test/bin/python -m pip install dist/*.whl
/tmp/metaevidence-release-test/bin/python -c "import metaevidence; print(metaevidence.__version__)"
```

## 4. Hash release artifacts

Generate SHA-256 for source archives, wheels, benchmark result bundles and frozen configuration files. Keep hashes with the release/Zenodo deposit.

## 5. Release candidate first

Until real external validation and API stability are complete, use pre-release versions rather than `1.0.0`. Scientific claims in README/paper must correspond to archived benchmark artifacts from the exact release candidate.

## 6. PyPI

Use Trusted Publishing via the protected GitHub `pypi` environment. Avoid long-lived PyPI API tokens in repository secrets where OIDC is available.

## 7. Zenodo

After connecting the public GitHub repository to Zenodo, archive a tagged GitHub release. Cite the version DOI for exact reproducibility and the concept DOI when referring to the evolving software project.
