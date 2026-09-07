import json
import httpx

from metaevidence import SearchQuery
from metaevidence.adapters import PubMedAdapter, OpenAlexAdapter, CrossrefAdapter, EuropePMCAdapter
from metaevidence.http import RetryPolicy


Q = SearchQuery('"bayesian network" AND diabetes', year_from=2020, year_to=2026)


def test_pubmed_history_fetch_normalizes_and_redacts_api_key():
    xml = b'''<?xml version="1.0"?>
    <PubmedArticleSet><PubmedArticle><MedlineCitation>
      <PMID>123456</PMID>
      <Article>
        <ArticleTitle>Bayesian <i>network</i> for diabetes</ArticleTitle>
        <Abstract><AbstractText Label="BACKGROUND">Useful abstract.</AbstractText></Abstract>
        <AuthorList><Author><LastName>Smith</LastName><ForeName>Jane</ForeName></Author></AuthorList>
        <Journal><Title>Journal of Evidence</Title><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
        <Language>eng</Language><PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
      </Article>
    </MedlineCitation><PubmedData><ArticleIdList>
      <ArticleId IdType="doi">10.1000/Test</ArticleId><ArticleId IdType="pmc">PMC999</ArticleId>
    </ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>'''

    def handler(request: httpx.Request):
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"count": "1", "webenv": "WEB", "querykey": "1", "querytranslation": "translated"}})
        if request.url.path.endswith("efetch.fcgi"):
            return httpx.Response(200, content=xml, headers={"Content-Type": "application/xml"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = PubMedAdapter(client=client, api_key="SECRET", email="test@example.org", retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(Q, max_records=10, page_size=10)
    assert result.total_available == 1
    assert result.retrieved_count == 1
    rec = result.records[0]
    assert rec.pmid == "123456"
    assert rec.doi == "10.1000/test"
    assert rec.title == "Bayesian network for diabetes"
    assert rec.authors == ["Smith Jane"]
    assert rec.metadata["pmcid"] == "PMC999"
    assert rec.source_hits[0].source == "pubmed"
    assert all(log.params.get("api_key") == "***REDACTED***" for log in result.request_log if "api_key" in log.params)


def test_pubmed_marks_over_10000_as_truncated_without_fetching_when_max_zero():
    def handler(request: httpx.Request):
        return httpx.Response(200, json={"esearchresult": {"count": "12001", "webenv": "WEB", "querykey": "1"}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = PubMedAdapter(client=client, retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(Q, max_records=0)
    assert result.truncated is True
    assert result.retrieved_count == 0
    assert any("10,000" in w for w in result.warnings)


def test_openalex_cursor_pagination_and_abstract_reconstruction():
    seen = []
    def handler(request: httpx.Request):
        cursor = request.url.params.get("cursor")
        seen.append(cursor)
        if cursor == "*":
            payload = {
                "meta": {"count": 2, "next_cursor": "NEXT", "cost_usd": 0.0001},
                "results": [{
                    "id": "https://openalex.org/W1", "title": "Paper one", "publication_year": 2024,
                    "publication_date": "2024-02-03", "doi": "https://doi.org/10.1/ONE",
                    "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/111"},
                    "authorships": [{"author": {"display_name": "Ada Author"}}],
                    "abstract_inverted_index": {"Diabetes": [0], "model": [1]},
                    "primary_location": {"source": {"display_name": "J1", "issn_l": "1234-5678"}},
                    "cited_by_count": 7, "type": "article", "language": "en"
                }]
            }
        else:
            payload = {"meta": {"count": 2, "next_cursor": None, "cost_usd": 0.0001}, "results": [{
                "id": "https://openalex.org/W2", "title": "Paper two", "publication_year": 2025,
                "authorships": [], "primary_location": {"source": {"display_name": "J2"}}
            }]}
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OpenAlexAdapter(client=client, api_key="OAKEY", retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(Q, max_records=2, page_size=1)
    assert seen == ["*", "NEXT"]
    assert result.retrieved_count == 2
    assert result.records[0].abstract == "Diabetes model"
    assert result.records[0].pmid == "111"
    assert result.records[0].doi == "10.1/one"
    assert result.metadata["estimated_api_cost_usd"] == 0.0002


def test_crossref_cursor_pagination_and_markup_cleanup():
    def handler(request: httpx.Request):
        cursor = request.url.params.get("cursor")
        item = {
            "DOI": "10.2/ABC", "title": ["Crossref paper"], "container-title": ["Meta Journal"],
            "author": [{"given": "John", "family": "Doe"}], "published": {"date-parts": [[2023, 5, 4]]},
            "abstract": "<jats:p>Clean <b>abstract</b>.</jats:p>", "type": "journal-article", "URL": "https://doi.org/10.2/ABC"
        }
        if cursor == "*":
            message = {"total-results": 2, "next-cursor": "C2", "items": [item]}
        else:
            item2 = dict(item, DOI="10.2/DEF", title=["Second"])
            message = {"total-results": 2, "next-cursor": "C3", "items": [item2]}
        return httpx.Response(200, json={"message": message})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = CrossrefAdapter(client=client, mailto="me@example.org", retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(Q, max_records=2, page_size=1)
    assert result.retrieved_count == 2
    assert result.records[0].abstract == "Clean abstract ." or result.records[0].abstract == "Clean abstract."
    assert result.records[0].year == 2023
    assert result.records[0].metadata["publication_date"] == "2023-05-04"
    assert result.metadata["polite_pool"] is True
    assert result.translation.fidelity_score < 1.0
    assert any("review retrieval sensitivity" in w for w in result.warnings)


def test_europe_pmc_cursor_pagination_core_records():
    def handler(request: httpx.Request):
        cursor = request.url.params.get("cursorMark")
        item = {
            "source": "MED", "id": "999", "pmid": "999", "pmcid": "PMC999", "doi": "10.3/EPMC",
            "title": "Europe PMC paper", "pubYear": "2022", "abstractText": "Abstract",
            "authorList": {"author": [{"fullName": "Jane Smith"}]},
            "journalInfo": {"journal": {"title": "PMC Journal"}}, "citedByCount": 3,
            "pubTypeList": {"pubType": ["research article"]}, "isOpenAccess": "Y"
        }
        if cursor == "*":
            payload = {"hitCount": 2, "nextCursorMark": "N", "resultList": {"result": [item]}}
        else:
            item2 = dict(item, id="1000", pmid="1000", doi="10.3/EPMC2", title="Europe PMC second")
            payload = {"hitCount": 2, "resultList": {"result": [item2]}}
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = EuropePMCAdapter(client=client, retry_policy=RetryPolicy(max_attempts=1))
    result = adapter.search(Q, max_records=2, page_size=1)
    assert result.retrieved_count == 2
    assert result.records[0].authors == ["Jane Smith"]
    assert result.records[0].doi == "10.3/epmc"
    assert result.metadata["result_type"] == "core"
