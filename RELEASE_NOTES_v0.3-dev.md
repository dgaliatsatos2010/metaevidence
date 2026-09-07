# MetaEvidence v0.3-dev release notes

## Milestone
M3 — live open-source bibliographic API execution layer.

## Added
- PubMed adapter using ESearch History + batched EFetch XML parsing.
- OpenAlex Works adapter with cursor pagination and abstract reconstruction.
- Crossref Works adapter with cursor pagination and metadata normalization.
- Europe PMC core-result adapter with cursorMark pagination.
- Multi-source `EvidenceSearch` orchestrator.
- `AdapterResult` execution summaries and source failure isolation.
- Exponential-backoff HTTP transport for transient failures.
- Secret-redacted request logs.
- SHA-256 response provenance.
- Optional gzip raw-response archive.
- Optional local response cache.
- Extended Search Reproducibility Manifest entries.
- Environment-variable credential/identification support.

## Safety / scientific non-claims
- PubMed searches above the ordinary 10,000-UID ESearch retrieval ceiling are flagged as truncated.
- Crossref relevance querying is not represented as Boolean-equivalent to specialist review databases.
- OpenAlex public access is distinguished from API-key-backed usage.
- No paywalled full-text downloading is implemented.
- Translation fidelity scores remain unvalidated engineering diagnostics until the benchmark milestone.

## Validation status
- 26 unit/integration-style mocked tests passing.
- Python bytecode compilation passes.
- Wheel build succeeds using setuptools.
- Clean-wheel import QA passes.
