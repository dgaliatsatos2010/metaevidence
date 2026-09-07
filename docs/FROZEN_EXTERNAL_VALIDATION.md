# Frozen external-validation execution protocol (v0.9.9-dev)

## Objective

The v0.9.9 external-validation layer is designed to make it difficult to change the evaluated method after seeing external outcomes. The benchmark is not a tuning loop.

## Two independent integrity layers

### 1. MetaEvidence method/runner lock

`benchmarks/frozen_validation_lock.json` stores SHA-256 values for:

- the publication-deduplication engine;
- its consumed record model;
- EndNote gold parsing/label mapping;
- blind record-removal evaluation semantics;
- ASySD execution/metric-contract code;
- frozen Beller and ASySD benchmark manifests; and
- the validation CLI, source fetcher, workflow, provenance writer and reporting layer.

Before any external scoring, run:

```bash
python benchmarks/verify_frozen_validation.py \
  --lock benchmarks/frozen_validation_lock.json \
  --repository-root .
```

or, after installation:

```bash
metaevidence verify-validation-lock benchmarks/frozen_validation_lock.json \
  --repository-root .
```

Any missing file or SHA-256 mismatch is a hard failure.

### 2. Third-party Beller/IEBH source integrity

The five EndNote XML files are not shipped with MetaEvidence. At run time they are downloaded from the immutable commit:

`IEBH/dedupe-sweep@66a7ed5f5ea95cafc5f76ba6ec60bb4eb3cd381a`

For every file, MetaEvidence checks both exact byte size and canonical Git blob SHA-1 before parsing. A partial, modified or wrong-path file is deleted/refused and never scored.

The authoritative local source list is `benchmarks/beller_endnote_manifest.json`. The GitHub Actions matrix reads this manifest directly rather than maintaining a second dataset list.

## Blind-primary rule

The primary external endpoint uses deployable `engine_quality` representative retention. Gold-preferred representative retention is a clearly labelled secondary reproduction analysis and must never replace the blind primary result.

## Held-out rule

ASySD held-out roles require both:

1. `confirm_held_out=true` in the manual workflow; and
2. the CLI `--allow-held-out` switch.

Held-out outcomes must not inform feature engineering, threshold changes, blocking changes, calibration changes, retention changes, or label interpretation.

## Run provenance

Every executed result tree receives `validation_run_manifest.json` containing:

- MetaEvidence version;
- frozen lock SHA-256 and verification status;
- Python/platform information;
- available GitHub repository/commit/run metadata; and
- SHA-256 and size of each result artifact in that run tree.

Raw third-party benchmark files are not included in this result manifest and are not uploaded as workflow artifacts.

## First execution order

1. Create the dedicated public repository `dgaliatsatos2010/metaevidence`.
2. Push the v0.9.9-dev source tree without third-party benchmark data.
3. Confirm ordinary CI passes.
4. Manually run `beller-secondary` with `beller_dataset=tafenoquine.xml`.
5. Confirm source integrity, parser completion, frozen-lock verification and result artifacts.
6. Run `beller-secondary` with `beller_dataset=all`.
7. Archive the aggregate result artifact and workflow run identifiers/hashes.
8. Run ASySD development/calibration according to the frozen manifest.
9. Open held-out ASySD outcomes only after all permitted development/calibration decisions are frozen.
10. Populate manuscript Results/Table 4 only from archived authentic outputs.

## What requires a new prospective validation version

Any change to a locked method file after external outcomes are inspected requires a new version, a documented reason, and a new prospectively declared held-out/external benchmark for claims about the changed method. Existing test-set outcomes cannot be reused as if they remained unseen.
