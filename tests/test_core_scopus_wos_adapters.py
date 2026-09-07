import httpx
import pytest

from metaevidence import EvidenceSearch, SearchQuery, translate
from metaevidence.adapters import COREAdapter, ScopusAdapter, WebOfScienceStarterAdapter
from metaevidence.http import RetryPolicy


def test_core_translation_audits_local_year_filter_and_field_scope():
    q = SearchQuery('title:"machine learning" AND diabetes', year_from=2020, year_to=2026)
    tx = translate(q, "core")
    assert 'title:("machine learning")' in tx.translated
    assert tx.requires_review is True
    assert any(d.feature == "date_filter" and d.status.value == "review_required" for d in tx.diagnostics)


def test_wos_starter_translation_uses_starter_safe_topic_scope():
    q = SearchQuery('abstract:"machine learning" AND diabetes')
    tx = translate(q, "web_of_science_starter")
    assert "AB=(" not in tx.translated
    assert "TS=(\"machine learning\")" in tx.translated
    assert tx.fidelity_score < 1.0


def test_core_offset_pagination_local_year_filter_and_normalization():
    seen_offsets = []

    def handler(request: httpx.Request):
        assert request.url.path.endswith("/v3/search/works/")
        seen_offsets.append(int(request.url.params["offset"]))
        if request.url.params["offset"] == "0":
            payload = {
                "totalHits": 3,
                "limit": 2,
                "offset": 0,
                "results": [
                    {"id": 1, "title": "Old", "yearPublished": 2019, "authors": [{"name": "Old Author"}]},
                    {
                        "id": 2,
                        "title": "In range",
                        "yearPublished": 2024,
                        "authors": [{"name": "Jane Smith"}],
                        "doi": "10.9/CORE",
                        "abstract": "Open abstract",
                        "downloadUrl": "https://example.org/paper.pdf",
                        "journals": [{"title": "OA Journal"}],
                        "documentType": "journal-article",
                    },
                ],
            }
        else:
            payload = {
                "totalHits": 3,
                "limit": 2,
                "offset": 2,
                "results": [{"id": 3, "title": "Second in range", "yearPublished": 2025, "authors": ["John Doe"]}],
            }
        return httpx.Response(200, json=payload)

    q = SearchQuery("diabetes", year_from=2020, year_to=2026)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = COREAdapter(client=client, api_key="CORESECRET", retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(q, max_records=2, page_size=2)
    assert seen_offsets == [0, 2]
    assert result.total_available == 3
    assert [r.title for r in result.records] == ["In range", "Second in range"]
    assert result.records[0].doi == "10.9/core"
    assert result.records[0].authors == ["Jane Smith"]
    assert result.records[0].metadata["download_url"] == "https://example.org/paper.pdf"
    assert result.records[0].metadata["full_text_available"] is True
    assert result.metadata["local_year_filter"] is True
    assert any("applied locally" in w for w in result.warnings)


def test_scopus_requires_api_key():
    adapter = ScopusAdapter(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))), retry_policy=RetryPolicy(max_attempts=1))
    with pytest.raises(ValueError, match="API key"):
        adapter.search(SearchQuery("diabetes"), max_records=1)


def test_scopus_offset_pagination_headers_and_record_normalization():
    seen = []

    def handler(request: httpx.Request):
        assert request.headers["X-ELS-APIKey"] == "SCOPUSSECRET"
        assert request.headers["X-ELS-Insttoken"] == "INST"
        assert request.url.params["view"] == "STANDARD"
        seen.append(int(request.url.params["start"]))
        start = int(request.url.params["start"])
        entry = {
            "eid": f"2-s2.0-{start+1}",
            "dc:identifier": f"SCOPUS_ID:{start+1}",
            "dc:title": "Scopus one" if start == 0 else "Scopus two",
            "dc:creator": "Smith, Jane",
            "prism:publicationName": "Scopus Journal",
            "prism:coverDate": "2024-03-15",
            "prism:doi": f"10.10/S{start+1}",
            "citedby-count": "5",
        }
        return httpx.Response(200, json={"search-results": {"opensearch:totalResults": "2", "entry": [entry]}})

    q = SearchQuery("diabetes", year_from=2020, year_to=2026)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ScopusAdapter(client=client, api_key="SCOPUSSECRET", insttoken="INST", retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(q, max_records=2, page_size=1)
    assert seen == [0, 1]
    assert result.retrieved_count == 2
    assert result.records[0].scopus_eid == "2-s2.0-1"
    assert result.records[0].doi == "10.10/s1"
    assert result.records[0].year == 2024
    assert "PUBYEAR" in result.translation.translated
    assert result.metadata["entitlement_dependent"] is True
    assert "SCOPUSSECRET" not in str([log.to_dict() for log in result.request_log])
    assert "INST" not in str([log.to_dict() for log in result.request_log])


def test_wos_starter_requires_api_key():
    adapter = WebOfScienceStarterAdapter(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))), retry_policy=RetryPolicy(max_attempts=1))
    with pytest.raises(ValueError, match="API key"):
        adapter.search(SearchQuery("diabetes"), max_records=1)


def test_wos_starter_page_pagination_date_filter_and_normalization():
    seen_pages = []

    def handler(request: httpx.Request):
        assert request.headers["X-ApiKey"] == "WOSSECRET"
        assert request.url.params["db"] == "WOS"
        assert request.url.params["publishTimeSpan"] == "2020-01-01 2026-12-31"
        page = int(request.url.params["page"])
        seen_pages.append(page)
        hit = {
            "uid": f"WOS:000{page}",
            "title": f"WoS paper {page}",
            "types": ["Article"],
            "source": {"sourceTitle": "Evidence Journal", "publishYear": 2024, "volume": "10", "issue": "2", "pages": "1-8"},
            "names": {"authors": [{"displayName": "Ada Author"}]},
            "identifiers": {"doi": f"10.20/WOS{page}", "pmid": str(100 + page), "issn": "1234-5678"},
            "citations": [{"db": "WOS", "count": page * 3}],
            "keywords": {"authorKeywords": ["evidence"]},
            "links": {"record": "https://www.webofscience.com/"},
        }
        return httpx.Response(200, json={"metadata": {"total": 2, "page": page, "limit": 1}, "hits": [hit]})

    q = SearchQuery('"machine learning" AND diabetes', year_from=2020, year_to=2026)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = WebOfScienceStarterAdapter(client=client, api_key="WOSSECRET", retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(q, max_records=2, page_size=1)
    assert seen_pages == [1, 2]
    assert result.retrieved_count == 2
    rec = result.records[0]
    assert rec.wos_ut == "WOS:0001"
    assert rec.pmid == "101"
    assert rec.doi == "10.20/wos1"
    assert rec.authors == ["Ada Author"]
    assert rec.abstract is None
    assert rec.metadata["times_cited"] == 3
    assert result.translation.source == "web_of_science_starter"
    assert result.metadata["api_variant"] == "starter_v2"
    assert "WOSSECRET" not in str([log.to_dict() for log in result.request_log])


def test_evidence_search_accepts_adapter_options_for_scopus():
    def handler(request: httpx.Request):
        assert request.headers["X-ELS-APIKey"] == "PROGRAMMATIC"
        return httpx.Response(200, json={"search-results": {"opensearch:totalResults": "1", "entry": [{
            "eid": "2-s2.0-99", "dc:title": "One", "prism:coverDate": "2024-01-01"
        }]}})

    search = EvidenceSearch(retry_policy=RetryPolicy(max_attempts=1))
    result = search.run(
        SearchQuery("diabetes"),
        sources=("scopus",),
        max_records_per_source=1,
        clients={"scopus": httpx.Client(transport=httpx.MockTransport(handler))},
        adapter_options={"scopus": {"api_key": "PROGRAMMATIC"}},
    )
    assert result.total_retrieved == 1
    assert "scopus" in result.source_results
