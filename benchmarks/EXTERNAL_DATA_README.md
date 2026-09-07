# External benchmark data

This directory intentionally does **not** redistribute third-party validation records.

MetaEvidence stores only:

- pre-specified dataset roles and expected integrity counts;
- published aggregate comparator results;
- code for loading, checking and evaluating locally obtained gold-standard files.

Before running a benchmark, obtain the source data from the authors' public repository under its applicable terms, preserve the original files, and record their checksums. Do not commit licensed or restricted bibliographic exports to a public repository.

The ASySD validation script/publication identifies labelled files including `Diabetes_duplicates_labelled.csv`, `NeuroImaging_duplicates_labelled.csv`, `Cardiac_duplicates_labelled.csv`, `Depression_duplicates_labelled.csv`, and `SRSR_duplicates_labelled.csv`. The `external_benchmark_manifest.json` freezes the intended development/calibration/held-out roles before MetaEvidence outcomes are inspected.


## Reproducible ASySD retrieval

The official ASySD validation script retrieves the labelled validation material from
OSF node `2b8uq`. MetaEvidence provides a public-file walker that discovers the five
named CSV files by filename rather than relying on a brittle file-list row number:

```bash
python benchmarks/fetch_asysd_validation.py \
  --destination external_validation_data/asysd_2023
```

The command writes `external_source_manifest.json` with source URLs, file IDs, byte
sizes and SHA-256 values. The downloaded records are intentionally ignored by Git.

ASySD 2023 is evaluated as a **record-removal label** benchmark. A row labelled
`Duplicate` is a gold citation to remove; a row labelled `Unique` is a gold citation to
retain. Those binary labels do not by themselves reveal the duplicate-group partition.

Run only development/calibration roles during model development:

```bash
python benchmarks/run_external_validation.py --roles development,calibration
```

Held-out outcomes require the separate `--allow-held-out` switch after model/threshold
freezing.

## ASySD representative-retention note

The official ASySD validation scripts use `keep_label="Unique"` when computing record-level confusion matrices. MetaEvidence v0.9.4 therefore reports blind engine-quality retention as the primary external estimate and a separately labelled gold-preferred reproduction result. If a verified `duplicate_id` column is present, a representative-insensitive partition result is also written.
