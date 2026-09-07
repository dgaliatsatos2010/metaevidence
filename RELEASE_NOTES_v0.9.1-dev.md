# MetaEvidence v0.9.1-dev release notes

## Focus: seven-source live retrieval coverage

v0.9.1-dev extends the live-source layer while preserving the external-validation and stable-release gates.

### Added

- `COREAdapter` for CORE v3 works search.
- `ScopusAdapter` for the official Elsevier Scopus Search API.
- `WebOfScienceStarterAdapter` for Clarivate Web of Science Starter API v2.
- `core` canonical query translator.
- `web_of_science_starter` compiler using Starter-safe field tags rather than Expanded-only syntax.
- `adapter_options` on `EvidenceSearch.run()` for per-source credentials/options without hard-coding secrets.
- environment placeholders for CORE, Scopus and Web of Science credentials.
- source-coverage documentation and source-specific reproducibility warnings.
- mock-conformance tests for authentication headers, pagination, date handling, normalization and secret non-disclosure.

### Safety / scientific reporting behavior

- Scopus fails clearly before network execution when no API key is configured.
- Web of Science Starter fails clearly before network execution when no API key is configured.
- Scopus entitlement/view limitations are preserved in warnings and execution metadata.
- Web of Science Starter is explicitly distinguished from API Expanded; no abstract is invented when Starter does not return one.
- CORE date bounds are locally post-filtered in this milestone and the unfiltered meaning of `total_available` is recorded.
- one-sided Web of Science Starter year bounds are locally post-filtered and warned.
- credentials are sent in HTTP headers and are not written to MetaEvidence request logs/audit metadata.

### QA

- Existing 101-test regression suite preserved.
- New source-adapter/translator/orchestrator tests increase the suite to 109 tests.

### Still deliberately blocked

- No public PyPI/Zenodo stable release.
- No external-performance claims before third-party gold-standard execution.
- No claim that seven API sources constitute all scholarly literature.
- No Web of Science API Expanded implementation yet.
