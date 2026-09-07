import pytest

from metaevidence import (
    Boolean,
    ConceptBlock,
    ControlledVocabulary,
    Field,
    PICOBuilder,
    PECOBuilder,
    Proximity,
    QuerySyntaxError,
    SearchField,
    SearchQuery,
    TranslationStatus,
    parse_query,
    render,
    translate,
)


def test_boolean_precedence_and_round_trip():
    q = SearchQuery('diabetes OR obesity AND "machine learning"')
    assert isinstance(q.ast, Boolean)
    assert q.ast.operator == "OR"
    assert "obesity AND \"machine learning\"" in q.canonical


def test_field_and_mesh_parse():
    ast = parse_query('title:"machine learning" AND mesh:"Diabetes Mellitus"')
    assert isinstance(ast, Boolean)
    assert isinstance(ast.children[0], Field)
    assert ast.children[0].field == SearchField.TITLE
    assert isinstance(ast.children[1], ControlledVocabulary)


def test_proximity_parse():
    ast = parse_query('"machine learning" NEAR/5 predict*')
    assert isinstance(ast, Proximity)
    assert ast.distance == 5
    assert render(ast) == '"machine learning" NEAR/5 predict*'


def test_invalid_query_fails_early():
    with pytest.raises(QuerySyntaxError):
        SearchQuery('(diabetes AND "machine learning"')


def test_pico_builder():
    q = PICOBuilder(
        population=ConceptBlock(("type 2 diabetes", "T2DM"), ("Diabetes Mellitus, Type 2",)),
        intervention=("machine learning", "artificial intelligence"),
        outcome=("mortality", "survival"),
        year_from=2018,
        year_to=2026,
    ).build()
    assert 'mesh:"Diabetes Mellitus, Type 2"' in q.canonical
    assert q.year_from == 2018
    assert q.ast is not None


def test_peco_builder():
    q = PECOBuilder(
        population="adults",
        exposure=("air pollution", "PM2.5"),
        outcome="mortality",
    ).build()
    assert '"air pollution"' in q.canonical
    assert "mortality" in q.canonical


def test_pubmed_mesh_and_date_translation():
    q = SearchQuery('mesh:"Diabetes Mellitus" AND title:"bayesian network"', year_from=2015, year_to=2026)
    t = translate(q, "pubmed")
    assert '"Diabetes Mellitus"[MeSH Terms]' in t.translated
    assert '[Title]' in t.translated
    assert '2015:2026[dp]' in t.translated
    assert t.fidelity_score > 0.9


def test_scopus_default_scope_and_proximity():
    q = SearchQuery('"machine learning" NEAR/4 diabetes', year_from=2020)
    t = translate(q, "scopus")
    assert t.translated.startswith("TITLE-ABS-KEY(")
    assert "W/4" in t.translated
    assert "PUBYEAR > 2019" in t.translated


def test_wos_title_abstract_scope_is_audited():
    q = SearchQuery('title_abstract:"machine learning" AND diabetes')
    t = translate(q, "web_of_science")
    assert "TS=(" in t.translated
    assert any(d.feature == "field" and d.status == TranslationStatus.APPROXIMATED for d in t.diagnostics)


def test_openalex_wildcard_requires_review():
    q = SearchQuery('predict* AND diabetes')
    t = translate(q, "openalex")
    assert t.requires_review
    assert any(d.feature == "wildcard" for d in t.diagnostics)


def test_crossref_reports_semantic_loss():
    q = SearchQuery('(diabetes OR obesity) AND NOT pediatric*', year_from=2010, year_to=2026)
    t = translate(q, "crossref")
    assert t.loss_score > 0
    assert t.requires_review
    assert any(d.status == TranslationStatus.UNSUPPORTED for d in t.diagnostics)
    assert ("filter.from-pub-date", "2010") in t.params


def test_europe_pmc_field_and_year():
    q = SearchQuery('title:"bayesian network" AND diabetes', year_from=2020, year_to=2026)
    t = translate(q, "europe_pmc")
    assert "TITLE:(" in t.translated
    assert "PUB_YEAR:[2020 TO 2026]" in t.translated


def test_scopus_default_scope_still_applies_with_mesh_concept():
    q = SearchQuery('mesh:"Diabetes Mellitus" OR diabetes')
    t = translate(q, "scopus")
    assert t.translated.startswith("TITLE-ABS-KEY(")


def test_openalex_wildcard_inside_proximity_is_review_required():
    q = SearchQuery('"machine learning" NEAR/5 predict*')
    t = translate(q, "openalex")
    assert t.requires_review
    assert any(d.feature == "wildcard" and d.status == TranslationStatus.REVIEW_REQUIRED for d in t.diagnostics)
