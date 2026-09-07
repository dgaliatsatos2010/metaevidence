# MetaEvidence v0.9.0-dev release notes

## Focus: release engineering without premature publication

v0.9.0-dev prepares the repository for a public open-source lifecycle while preserving the external-validation gate established in v0.8.1.

### Added

- GitHub Actions CI for Python 3.10, 3.11, 3.12 and 3.13.
- Package build + clean-wheel-install job.
- PyPI Trusted Publishing workflow template protected by a `pypi` GitHub environment.
- `CITATION.cff`.
- `CONTRIBUTING.md`.
- `SECURITY.md`.
- `CODE_OF_CONDUCT.md`.
- `CHANGELOG.md`.
- `.gitignore` protecting local credentials, caches and private benchmark data.
- public `RELEASE_CHECKLIST.md` with explicit scientific and software gates.
- reproducible release documentation.

### Deliberately not done

- No PyPI upload.
- No GitHub public repository creation/push.
- No Zenodo release/DOI.
- No stable `1.0.0` claim.
- No external-performance claim before the third-party gold-standard datasets are actually executed under the frozen protocol.

The `metaevidence` project URL currently returns no active PyPI project page at the time of release preparation, but name availability can change and must be rechecked immediately before first publication.
