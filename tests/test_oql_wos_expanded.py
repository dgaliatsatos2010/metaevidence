import json

import httpx
import pytest

from metaevidence import EvidenceSearch, SearchQuery, translate
from metaevidence.adapters import OpenAlexOQLAdapter, WebOfScienceExpandedAdapter
from metaevidence.http import RetryPolicy


def test_openalex_oql_translation_preserves_fielded_boolean_and_years():
    q = SearchQuery('title:"machine learning" AND abstract:(diabetes OR glucose)', year_from=2020, year_to=2026)
    tx = translate(q, "openalex_oql")
    assert tx.source == "openalex_oql"
    assert tx.translated.startswith("works where ")
    assert 'title has ("machine learning")' in tx.translated
    assert "abstract has" in tx.translated
    assert "year >= (2020)" in tx.translated
    assert "year <= (2026)" in tx.translated
    assert tx.requires_review is False


def test_openalex_oql_translation_uses_native_proximity_and_quoted_wildcard():
    q = SearchQuery('("machine learning" NEAR/5 predict*) AND diabetes')
    tx = translate(q, "openalex_oql")
    assert 'within 5 ("machine learning", "predict*")' in tx.translated
    assert '"predict*"' in tx.translated


def test_openalex_oql_cursor_pagination_header_auth_and_x_query():
    seen = []
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer OASECRET"
        assert request.method == "GET"
        assert request.url.path == "/"
        cursor = request.url.params["cursor"]
        seen.append(cursor)
        item = {
            "id": f"https://openalex.org/W{len(seen)}",
            "title": f"OQL paper {len(seen)}",
            "publication_year": 2024,
            "authorships": [{"author": {"display_name": "Ada Author"}}],
            "primary_location": {"source": {"display_name": "OQL Journal"}},
        }
        if cursor == "*":
            return httpx.Response(200, json={"meta": {"count": 2, "next_cursor": "NEXT", "cost_usd": 0.001, "x_query": {"oql": "works where title has (diabetes)"}}, "results": [item]})
        return httpx.Response(200, json={"meta": {"count": 2, "next_cursor": None, "cost_usd": 0.001}, "results": [item]})

    adapter = OpenAlexOQLAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="OASECRET",
        retry_policy=RetryPolicy(max_attempts=1),
    )
    result = adapter.search(SearchQuery("diabetes"), max_records=2, page_size=1)
    assert seen == ["*", "NEXT"]
    assert result.retrieved_count == 2
    assert result.records[0].source_hits[0].source == "openalex_oql"
    assert result.metadata["api_variant"] == "oql"
    assert result.metadata["x_query"]["oql"].startswith("works where")
    assert "OASECRET" not in str([x.to_dict() for x in result.request_log])


def test_openalex_oql_long_query_switches_to_post():
    long_term = "a" * 6100
    q = SearchQuery(long_term, fields=("all",))
    def handler(request: httpx.Request):
        assert request.method == "POST"
        body = json.loads(request.content.decode())
        assert body["oql"].startswith("works where")
        assert body["cursor"] == "*"
        return httpx.Response(200, json={"meta": {"count": 0, "next_cursor": None}, "results": []})
    adapter = OpenAlexOQLAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(max_attempts=1),
    )
    result = adapter.search(q, max_records=1)
    assert result.metadata["used_post_for_long_query"] is True
    assert result.request_log[0].method == "POST"


def _expanded_record(uid: str, doi: str, title: str):
    return {
        "UID": uid,
        "static_data": {
            "summary": {
                "pub_info": {"pubyear": 2024, "vol": 10, "issue": 2, "pubtype": "Journal", "page": {"content": "10-20"}},
                "names": {"name": [{"role": "author", "display_name": "Smith, Jane"}]},
                "doctypes": {"doctype": ["Article"]},
                "titles": {"title": [
                    {"type": "item", "content": title},
                    {"type": "source", "content": "Expanded Journal"},
                ]},
            },
            "fullrecord_metadata": {
                "abstracts": {"abstract": {"abstract_text": {"p": "Rich abstract."}}},
                "keywords": {"keyword": ["evidence", "synthesis"]},
                "refs": {"count": 33},
                "addresses": {"address_name": [{"address_spec": {"country": "Greece"}}]},
                "fund_ack": {"fund_text": {"p": "Funding text"}},
            },
            "item": {"keywords_plus": {"keyword": ["META-ANALYSIS"]}},
        },
        "dynamic_data": {
            "cluster_related": {"identifiers": {"identifier": [
                {"type": "doi", "value": doi},
                {"type": "pmid", "value": "12345"},
            ]}},
            "citation_related": {"tc_list": {"silo_tc": [{"coll_id": "WOS", "local_count": 12}]}}
        },
    }


def test_wos_expanded_requires_key():
    adapter = WebOfScienceExpandedAdapter(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        retry_policy=RetryPolicy(max_attempts=1),
    )
    with pytest.raises(ValueError, match="paid-license API key"):
        adapter.search(SearchQuery("diabetes"), max_records=1)


def test_wos_expanded_full_record_pagination_normalization_and_quota_headers():
    first_records = []
    def handler(request: httpx.Request):
        assert request.headers["X-ApiKey"] == "WOSXPSECRET"
        assert request.url.path == "/api/wos"
        assert request.url.params["databaseId"] == "WOS"
        assert request.url.params["optionView"] == "FR"
        assert request.url.params["publishTimeSpan"] == "2020-01-01 2026-12-31"
        first = int(request.url.params["firstRecord"])
        first_records.append(first)
        rec = _expanded_record(f"WOS:000{first}", f"10.50/EXP{first}", f"Expanded {first}")
        return httpx.Response(
            200,
            json={
                "QueryResult": {"QueryID": "77", "RecordsSearched": 2, "RecordsFound": 2},
                "Data": {"Records": {"records": {"REC": [rec]}}},
            },
            headers={"X-REC-AmtPerYear-Remaining": "49999", "X-REQ-ReqPerSec-Remaining": "1"},
        )

    adapter = WebOfScienceExpandedAdapter(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="WOSXPSECRET",
        option_view="FR",
        retry_policy=RetryPolicy(max_attempts=1),
    )
    q = SearchQuery('abstract:"machine learning" AND diabetes', year_from=2020, year_to=2026)
    result = adapter.search(q, max_records=2, page_size=1)
    assert first_records == [1, 2]
    assert result.retrieved_count == 2
    rec = result.records[0]
    assert rec.wos_ut == "WOS:0001"
    assert rec.doi == "10.50/exp1"
    assert rec.pmid == "12345"
    assert rec.title == "Expanded 1"
    assert rec.journal == "Expanded Journal"
    assert rec.abstract == "Rich abstract."
    assert rec.authors == ["Smith, Jane"]
    assert rec.metadata["times_cited"] == 12
    assert rec.metadata["reference_count"] == 33
    assert result.metadata["full_record_quota_consuming"] is True
    assert result.metadata["query_id"] == "77"
    assert result.request_log[0].rate_limit["x-rec-amtperyear-remaining"] == "49999"
    assert "WOSXPSECRET" not in str([x.to_dict() for x in result.request_log])


def test_evidence_search_supports_oql_and_wos_expanded_aliases():
    def oa_handler(request: httpx.Request):
        return httpx.Response(200, json={"meta": {"count": 0, "next_cursor": None}, "results": []})
    def wos_handler(request: httpx.Request):
        return httpx.Response(200, json={"QueryResult": {"QueryID": "1", "RecordsFound": 0}, "Data": {"Records": {"records": {"REC": []}}}})
    search = EvidenceSearch(retry_policy=RetryPolicy(max_attempts=1))
    result = search.run(
        SearchQuery("diabetes"),
        sources=("openalex_oql", "wos_expanded"),
        clients={
            "openalex_oql": httpx.Client(transport=httpx.MockTransport(oa_handler)),
            "web_of_science_expanded": httpx.Client(transport=httpx.MockTransport(wos_handler)),
        },
        adapter_options={"web_of_science_expanded": {"api_key": "KEY"}},
        max_records_per_source=1,
    )
    assert "openalex_oql" in result.source_results
    assert "web_of_science_expanded" in result.source_results
