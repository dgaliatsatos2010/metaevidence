"""Minimal live MetaEvidence search example.

Set source credentials/identification in environment variables before production use.
"""
from metaevidence import EvidenceSearch, SearchQuery

query = SearchQuery(
    '("bayesian network" OR "bayesian networks") AND diabetes',
    year_from=2020,
    year_to=2026,
)

run = EvidenceSearch(cache_dir=".metaevidence-cache").run(
    query,
    sources=("pubmed", "openalex", "crossref", "europe_pmc"),
    max_records_per_source=100,
)

for source, result in run.source_results.items():
    print(source, result.retrieved_count, result.total_available, result.warnings)

run.manifest.write_json("search_manifest.json")
