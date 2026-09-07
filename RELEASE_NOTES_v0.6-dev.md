# MetaEvidence v0.6.0-dev — M6 Screening Interoperability

## Added

- Stable citation-level `record_id` generation using DOI/PMID/WoS/Scopus/OpenAlex identifiers with deterministic fallback fingerprints.
- `ScreeningLedger` append-only audit trail.
- Title/abstract and full-text screening stages.
- `INCLUDE`, `EXCLUDE`, `MAYBE`, `NOT_SCREENED` decisions.
- Controlled/editable exclusion-reason codebook.
- Full-text exclusion-reason safeguard.
- Double-screening disagreement detection.
- Non-destructive adjudication events.
- Percent agreement and unweighted Cohen's kappa for reviewer pairs.
- Generic CSV and JSONL citation/screening exports.
- RIS export/import for common evidence-synthesis fields.
- BibTeX export.
- ASReview-compatible CSV export/import conventions.
- ASReview-compatible RIS `N1` labels.
- Conservative mapping of unresolved/MAYBE records to ASReview not-seen rather than forcing a binary label.
- `write_screening_bundle(...)` for reproducible review handoff packages.
- SHA-256 and byte-size manifest for every bundle artifact.
- Optional study-family and double-counting exports inside screening bundles.
- M6 documentation and end-to-end example.

## Scientific / interoperability status

M6 does not claim that file compatibility alone makes a systematic review valid, PRISMA-compliant, or reproducible. The ASReview mapping follows the current public data-format conventions, but broader real-world round-trip validation across software versions remains necessary before a strong compatibility claim. Generic RIS support targets common fields and does not claim exhaustive support for all vendor-specific extensions.

## QA

- Full regression suite: **67/67 tests passing**.
- Python compile check: **PASS**.
- Wheel build: **PASS** (`metaevidence-0.6.0.dev0-py3-none-any.whl`).
- Clean wheel installation/import: **PASS**.
- Clean-install ASReview CSV screening-label smoke test: **PASS**.
- Tests cover ASReview labels, RIS round trips, CSV imports, audit-ledger round trips, disagreement/adjudication, kappa, study-family export integration and bundle checksums.
