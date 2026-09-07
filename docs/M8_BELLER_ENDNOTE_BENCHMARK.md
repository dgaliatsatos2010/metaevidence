# Secondary external benchmark: EndNote XML / dedupe-sweep

## Purpose

This benchmark provides an independent secondary test of publication-level duplicate removal using publicly documented EndNote XML libraries. It is not a replacement for the frozen ASySD primary validation sequence and must not be used for parameter tuning.

## Frozen source

- Repository: `IEBH/dedupe-sweep`
- Commit: `66a7ed5f5ea95cafc5f76ba6ec60bb4eb3cd381a`
- Path: `test/data/`
- Files: `blue-light.xml`, `copper.xml`, `diabetes.xml`, `tafenoquine.xml`, `uti.xml`

The package records expected file sizes and Git blob SHA identifiers. Validation fails before outcome inspection if local bytes differ. Third-party XML files are never packaged or redistributed by MetaEvidence.

## Gold semantics

The benchmark analysis code in the source repository treats records with `caption == 'Duplicate'` as positive duplicate records and records without a caption as non-duplicates. MetaEvidence maps this to a record-removal gold standard:

- `caption='Duplicate'` -> `gold_removed=True`
- absent/blank caption -> `gold_removed=False`

Unknown nonblank captions fail closed by default.

## Leakage prevention

The XML caption is retained only in audit metadata and the separate gold-label vector. The confidence deduplication engine consumes title, author, year, journal, identifiers and selected bibliographic fields only; it never consumes `external_gold_*` metadata.

## Execution

```bash
metaevidence fetch-beller-endnote external/beller
metaevidence validate-beller-endnote external/beller results/beller
```

For a single file:

```bash
metaevidence validate-endnote-gold external/beller/tafenoquine.xml results/tafenoquine
```

## Outcomes

Primary: blind record-removal sensitivity, specificity, precision, F1, false-positive and false-negative counts using frozen MetaEvidence defaults.

Secondary: gold-preferred representative-retention reproduction, labelled explicitly as reference-informed.

No numerical results are inserted into the manuscript until execution on the pinned bytes is complete.
