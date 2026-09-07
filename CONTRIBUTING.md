# Contributing to MetaEvidence

Contributions are welcome, especially reproducible bug reports, source-adapter tests, benchmark datasets that can legally be shared, query-translation edge cases, and systematic-review workflow feedback.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

## Pull-request expectations

1. Add or update tests for behavior changes.
2. Preserve backwards compatibility unless a breaking change is documented.
3. Do not weaken deduplication/study-linkage safety gates merely to improve recall on one benchmark.
4. Do not tune against held-out external datasets.
5. Clearly distinguish engineering/synthetic results from external scientific validation.
6. Update relevant documentation and release notes.

## Data and credentials

Do not commit API keys, tokens, institutional credentials, private review data, paywalled full text, or third-party benchmark files whose redistribution terms are unclear. Prefer synthetic fixtures in tests. External benchmark manifests may store source citations, expected counts and checksums without redistributing the underlying records.

## Scientific claims

A pull request should not introduce claims such as “complete retrieval,” “PRISMA compliant,” “calibrated probability,” “first tool,” or “superior performance” without evidence appropriate to that claim.
