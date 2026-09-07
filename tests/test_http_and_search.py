import httpx

from metaevidence import EvidenceSearch, SearchQuery
from metaevidence.http import RetryingClient, RetryPolicy


def test_retrying_client_retries_429_and_records_attempts():
    calls = {"n": 0}
    slept = []
    def handler(request: httpx.Request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "slow"}, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    rc = RetryingClient(source="test", client=client, retry_policy=RetryPolicy(max_attempts=2, backoff_base_seconds=0), sleeper=slept.append)
    response = rc.get("https://example.test/api", params={"api_key": "SECRET"})
    assert response.status_code == 200
    assert calls["n"] == 2
    assert [x.status_code for x in rc.logs] == [429, 200]
    assert rc.logs[0].params["api_key"] == "***REDACTED***"


def test_multisearch_isolates_failure_and_keeps_success_manifest():
    q = SearchQuery("diabetes")

    def openalex_handler(request: httpx.Request):
        return httpx.Response(200, json={"meta": {"count": 1, "next_cursor": None}, "results": [{
            "id": "https://openalex.org/W1", "title": "One", "publication_year": 2024,
            "authorships": [], "primary_location": {"source": {"display_name": "Journal"}}
        }]})

    def crossref_handler(request: httpx.Request):
        return httpx.Response(503, json={"error": "down"})

    clients = {
        "openalex": httpx.Client(transport=httpx.MockTransport(openalex_handler)),
        "crossref": httpx.Client(transport=httpx.MockTransport(crossref_handler)),
    }
    search = EvidenceSearch(retry_policy=RetryPolicy(max_attempts=1))
    result = search.run(q, sources=("openalex", "crossref"), max_records_per_source=1, clients=clients)
    assert result.total_retrieved == 1
    assert "openalex" in result.source_results
    assert "crossref" in result.failures
    assert len(result.manifest.searches) == 1
    assert len(result.manifest.failures) == 1
