# MetaEvidence v0.9.6-dev — EndNote XML external-benchmark interoperability

## Added

- Memory-efficient streaming parser for EndNote XML citation libraries.
- Record-level duplicate-removal gold semantics from EndNote `caption=Duplicate`.
- Gold-label isolation: the caption is never part of the deduplication feature vector.
- `metaevidence validate-endnote-gold` for a single compatible XML corpus.
- Pinned five-corpus secondary benchmark from `IEBH/dedupe-sweep` at commit `66a7ed5f5ea95cafc5f76ba6ec60bb4eb3cd381a`.
- `metaevidence fetch-beller-endnote` and `metaevidence validate-beller-endnote`.
- Byte-size and Git blob SHA integrity gates before benchmark execution.
- Frozen benchmark manifest at `benchmarks/beller_endnote_manifest.json`.

## Scientific interpretation

The IEBH/dedupe-sweep corpora are a secondary external test path and must not be used to tune MetaEvidence thresholds. The pre-specified ASySD sequence remains benchmark-1. Primary performance uses blind engine-quality representative retention; gold-preferred retention is reproduction-only. No performance number from these XML corpora is claimed until the pinned source files are actually executed.

## QA

- 133/133 tests passing before release packaging.
- Streaming parser, strict caption handling, gold-feature isolation and pinned GitHub fetch integrity are covered by regression tests.
