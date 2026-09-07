# MetaEvidence v0.9.10-dev

## Purpose

Technical I/O-compatibility hotfix discovered during the first ASySD development/calibration execution. The official ASySD CSV bytes are not uniformly UTF-8; v0.9.9-dev aborted with a UnicodeDecodeError before any ASySD performance metric was produced.

## Changes

- Adds a byte-level ASySD encoding-normalization step that creates derived UTF-8-SIG copies while preserving the downloaded raw files unchanged.
- Records source SHA-256, detected source encoding, and normalized SHA-256 in an auditable encoding-normalization manifest.
- The normalizer never parses CSV columns or gold labels.
- GitHub Actions validates ASySD against the normalized derived copies and archives the normalization manifest with provenance.

## Method integrity

No deduplication feature, score, weight, threshold, blocking rule, representative-retention rule, gold-label semantic, dataset role, or held-out policy changed. The six method-critical files remain byte-identical to v0.9.9-dev, including `src/metaevidence/dedup.py` with SHA-256 `3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50`.

The hotfix was motivated solely by a text-decoding exception, not by external performance outcomes. The failed ASySD run produced no performance metrics.
