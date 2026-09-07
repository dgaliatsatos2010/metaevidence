# Security policy

## Supported versions

MetaEvidence is pre-release software. Security fixes are applied to the newest development line.

## Reporting a vulnerability

Please use GitHub's **private security advisory** feature rather than a public issue for vulnerabilities involving credential exposure, request signing, cache/audit leakage, path traversal, unsafe parsing, or supply-chain concerns.

Do not include live API keys or institutional credentials in a report. Revoke any credential that may already have been exposed.

## Secret-handling design

MetaEvidence is designed to read credentials from environment variables and redact known secrets from request logs. Raw-response auditing is opt-in. Users remain responsible for the permissions, licensing and sensitivity of data they choose to cache or archive.
