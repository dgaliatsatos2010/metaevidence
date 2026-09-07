# MetaEvidence v0.7-dev release notes

## M7 — PRISMA/reproducibility reporting layer

### Added

- `PrismaFlow` machine-readable PRISMA 2020 study-selection accounting.
- Separate database, registry and other-source identification counts.
- Record/report/study level distinction.
- Duplicate, automation and other pre-screening removal counts.
- Title/abstract screening and exclusion accounting from `ScreeningLedger`.
- Full-text retrieval/eligibility accounting.
- Aggregated full-text exclusion reasons.
- `NOT_RETRIEVABLE` separation from eligibility exclusions.
- Included-study counting through M5 `StudyLinkageResult`.
- arithmetic consistency diagnostics and strict validation.
- `PrismaSearchReport` with source/platform, executed strategy, retrieval date, record count, truncation and translation diagnostics.
- `PrismaSearchContext` for human-supplied methods that cannot be safely inferred.
- 16-item PRISMA-S support matrix.
- JSON, CSV and Markdown search-report exports.
- editable Mermaid flow source (`.mmd`).
- `write_prisma_bundle()` with SHA-256 reproducibility manifest and runtime metadata.
- `docs/M7_PRISMA_REPRODUCIBILITY.md`.

### Scientific safeguards

- No automatic claim of “PRISMA compliance”.
- No conversion of API `total_available` into imported-record counts.
- Truncated searches generate explicit warnings.
- `studies_included` is not guessed when study-level linkage is missing.
- Human-only PRISMA-S items are marked `USER_INPUT_REQUIRED` rather than invented.
- Full-text reports that were not retrieved are kept separate from retrieved reports excluded for eligibility reasons.

### Validation status

- Full regression suite: **78 passed** at release QA stage.
- PRISMA flow arithmetic tests added.
- study/report counting tests added.
- PRISMA-S automatic-vs-human reporting tests added.
- reproducibility-bundle hash tests added.

### Remaining validation

M7 is a reporting-support implementation, not independent validation of PRISMA adherence. M8 will evaluate the scientific performance of query translation, deduplication and study linkage on external benchmark datasets.
