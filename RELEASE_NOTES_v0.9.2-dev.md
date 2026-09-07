# MetaEvidence v0.9.2-dev release notes

This development release adds two advanced retrieval modes while preserving backward compatibility with the classic OpenAlex and Web of Science Starter adapters.

## Added

- `OpenAlexOQLAdapter` / source `openalex_oql`
  - native OQL fielded search compilation;
  - nested Boolean text-search logic;
  - `within N (...)` proximity;
  - quoted wildcard handling;
  - OQL year filters;
  - cursor pagination;
  - POST fallback for long queries;
  - `meta.x_query` audit capture.
- `WebOfScienceExpandedAdapter` / source `web_of_science_expanded`
  - official paid Expanded endpoint;
  - `firstRecord`/`count` pagination;
  - `FR`, `SR`, and `FS` modes;
  - normalization of abstracts, identifiers, authors, addresses, funding, references and times-cited when returned;
  - Clarivate quota-header capture and explicit full-record quota warnings.
- HTTP POST retry/audit support.

## Correctness change

`ScreeningLedger` now treats append order as the revision sequence. Timestamps remain provenance metadata. This prevents a later imported correction carrying an earlier wall-clock timestamp from being ignored by PRISMA accounting.

## Validation status

- 116 regression/unit tests pass.
- External gold-standard performance validation remains required before any superiority or calibrated-probability claim.
- OpenAlex OQL and Web of Science Expanded behavior is covered with deterministic mocked responses based on their current documented response/parameter structures; real entitlement-dependent WoS Expanded smoke testing requires user credentials.

## External validation data

The frozen ASySD external-validation protocol remains unchanged. The public ASySD validation code identifies OSF node `2b8uq` as the source of the five labelled datasets. Those third-party records are not bundled in MetaEvidence. No external-performance claim is made in this release until the source files are retrieved and their integrity gate passes.
