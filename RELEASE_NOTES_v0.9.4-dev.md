# MetaEvidence v0.9.4-dev

This release hardens the external-validation methodology before any ASySD gold-standard outcomes are inspected.

## Main change
The official ASySD 2023 validation pipeline preferentially retains citations carrying the gold `Unique` label. Because record-removal metrics depend on which duplicate representative is kept, MetaEvidence now distinguishes:

- **blind `engine_quality` retention** — primary, deployable, never reads the gold label;
- **`gold_preferred_reproduction`** — secondary reproduction-only mode using the gold label solely to select a representative inside the already predicted cluster;
- **partition-secondary evaluation** — automatically run when a verified duplicate/publication group field is available and passes frozen count checks.

The reproduction mode is explicitly marked as gold-informed and must not be reported as the primary external-validation performance.

## QA
- 123/123 tests passing.
- Python compile check passed.
- External benchmark manifest JSON, GitHub Actions YAML and `CITATION.cff` validation passed.
- Wheel `metaevidence-0.9.4.dev0-py3-none-any.whl` built successfully.
- Clean installation/import from the built wheel passed.
- No ASySD external performance values are fabricated or inferred from published ASySD results.
- Held-out gates remain unchanged.
