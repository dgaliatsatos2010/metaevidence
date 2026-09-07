# Push MetaEvidence v0.9.9-dev first

The package is ready for a dedicated repository named:

`dgaliatsatos2010/metaevidence`

## One-time GitHub UI action

Create an empty **public** repository named `metaevidence` under `dgaliatsatos2010`.

Do not initialize it with a GitHub README, `.gitignore`, or license because those files already exist in this source tree.

## What to push

Push the **contents of this directory to repository root**. Do not create an extra outer `MetaEvidence_v0.9.9-dev/` directory in the repository.

Do not upload downloaded Beller XML or ASySD CSV benchmark files.

## First validation run

After CI passes:

1. GitHub → Actions → **External validation** → Run workflow.
2. `benchmark`: `beller-secondary`
3. `beller_dataset`: `tafenoquine.xml`
4. `confirm_held_out`: `false`
5. Run.

The run must pass the frozen SHA-256 lock before download/scoring, then pass exact Beller byte-size + Git-blob integrity before parsing.

If the smoke run succeeds, run again with `beller_dataset=all`. Do not alter the deduplication code or thresholds in response to the smoke/full-matrix outcomes.
