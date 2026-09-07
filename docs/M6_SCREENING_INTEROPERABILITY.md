# M6 — Screening interoperability and audit trail

## Goal

M6 turns the output of retrieval, publication deduplication and study linkage into a screening-ready evidence package without forcing reviewers to discard provenance or collapse nuanced decisions into a binary label prematurely.

The design separates three layers:

1. **citation interchange** — CSV, JSONL, RIS and BibTeX;
2. **screening state** — append-only reviewer decisions, exclusion reasons and adjudication;
3. **tool interoperability** — ASReview-compatible CSV/RIS exports using the field and label conventions documented by ASReview LAB.

## Screening model

`ScreeningLedger` is append-only. Each event records:

- stable `record_id`;
- screening stage (`TITLE_ABSTRACT` or `FULL_TEXT`);
- decision (`INCLUDE`, `EXCLUDE`, `MAYBE`, `NOT_SCREENED`);
- reviewer;
- timestamp;
- optional controlled exclusion reason;
- free-text reason/note;
- adjudication flag;
- event metadata.

A resolved decision is not silently overwritten: the earlier events remain in the ledger. This allows the sequence of screening decisions to be audited.

### Full-text exclusion safeguard

By default, a `FULL_TEXT` exclusion requires either a reason code or a free-text reason. This is intended to prevent later PRISMA accounting from discovering that full-text exclusions were recorded without reasons.

The bundled generic reason codebook is deliberately editable. It is not presented as a universal ontology.

## Double screening and adjudication

The ledger keeps the latest independent decision per reviewer. If reviewers disagree, the record has no resolved final decision until consensus/adjudication or a later set of reviewer decisions resolves the conflict.

`ledger.conflicts()` exposes unresolved disagreements. `ledger.adjudicate(...)` adds an adjudication event rather than rewriting previous decisions.

`ledger.agreement(...)` reports:

- number of records screened by both reviewers;
- raw agreement count;
- percent agreement;
- unweighted Cohen's kappa.

Kappa is a descriptive workflow statistic, not a guarantee of screening validity.

## ASReview interoperability

Current ASReview LAB documentation accepts tabular data containing a title or abstract and recognizes fields including `authors`, `doi`, `url` and an `included`/`label` binary screening field. For RIS, ASReview recognizes the notes `ASReview_relevant`, `ASReview_irrelevant` and `ASReview_not_seen` in `N1`.

MetaEvidence therefore writes:

- `asreview.csv` with `title, abstract, authors, year, doi, url, included`;
- `asreview.ris` with the corresponding ASReview `N1` notes.

Mapping is deliberately conservative:

- resolved `INCLUDE` -> `1` / `ASReview_relevant`;
- resolved `EXCLUDE` -> `0` / `ASReview_irrelevant`;
- `MAYBE`, unresolved disagreement or unscreened -> blank / `ASReview_not_seen`.

No uncertain decision is silently coerced into a binary label.

## Generic interchange

`write_csv` and `write_jsonl` retain MetaEvidence-specific fields such as stable record ID, database identifiers, source provenance, study family and screening decisions.

`write_ris` and `write_bibtex` provide common citation-manager interchange. The built-in RIS parser intentionally implements the common tags required by this workflow rather than claiming exhaustive support for every vendor-specific RIS extension.

`read_csv` accepts common ASReview-style column aliases and can reconstruct binary screening labels. `read_ris` recognizes ASReview `N1` labels.

## Screening bundle

`write_screening_bundle(...)` creates a directory containing:

- `records.csv`
- `records.jsonl`
- `records.ris`
- `records.bib`
- `asreview.csv`
- `asreview.ris`
- `screening_audit.jsonl` (when a ledger is supplied)
- `screening_audit.csv`
- `study_families.csv` (when study linkage is supplied)
- `double_counting_risks.csv`
- `bundle_manifest.json`

The manifest contains SHA-256 and byte size for each generated artifact. This supports exact identification of the files used in a review workflow.

## Example

```python
from metaevidence import (
    ScreeningDecision,
    ScreeningLedger,
    ScreeningStage,
    StudyLinkageEngine,
    write_screening_bundle,
)

ledger = ScreeningLedger()
ledger.add(records[0], ScreeningDecision.INCLUDE, reviewer="reviewer-A")
ledger.add(records[0], ScreeningDecision.EXCLUDE, reviewer="reviewer-B")

# Resolve disagreement without deleting either original decision.
ledger.adjudicate(
    records[0],
    ScreeningDecision.INCLUDE,
    stage=ScreeningStage.TITLE_ABSTRACT,
    reviewer="adjudicator",
)

# Full-text exclusions carry a reason.
ledger.add(
    records[1],
    ScreeningDecision.EXCLUDE,
    stage=ScreeningStage.FULL_TEXT,
    reviewer="reviewer-A",
    reason_code="WRONG_OUTCOME",
)

families = StudyLinkageEngine().link(records)
write_screening_bundle(records, "review_bundle", ledger=ledger, linkage=families)
```

## Validation still required

M6 is format/interoperability infrastructure rather than a validated screening algorithm. Before release-level interoperability claims, the project should add:

- round-trip tests with several real-world RIS exporters;
- direct import tests in a pinned ASReview release;
- encoding and malformed-file stress tests;
- very large file streaming benchmarks;
- additional vendor-specific interoperability tests only where public formats and licenses permit them;
- audit-log schema versioning/migrations.
