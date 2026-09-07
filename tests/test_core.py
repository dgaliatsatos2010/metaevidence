from metaevidence import EvidenceRecord, SourceHit, SearchQuery, DeduplicationEngine
from metaevidence.translators import translate


def test_doi_normalization_and_deduplication():
    a = EvidenceRecord(
        title="Bayesian Networks for Diabetes Prediction",
        doi="https://doi.org/10.1000/ABC",
        source_hits=[SourceHit("pubmed", "1")],
    )
    b = EvidenceRecord(
        title="Bayesian networks for diabetes prediction",
        doi="doi:10.1000/abc",
        source_hits=[SourceHit("scopus", "2")],
    )
    result = DeduplicationEngine().deduplicate([a, b])
    assert len(result.records) == 1
    assert set(result.records[0].sources) == {"pubmed", "scopus"}
    assert result.links[0].rule == "doi_exact"


def test_guarded_fuzzy_title():
    a = EvidenceRecord(title="Machine learning prediction of diabetes outcomes", authors=["Smith J"], year=2024)
    b = EvidenceRecord(title="Machine-learning prediction of diabetes outcome", authors=["J Smith"], year=2024)
    result = DeduplicationEngine(fuzzy_threshold=0.90).deduplicate([a, b])
    assert len(result.records) == 1


def test_pubmed_translation_date_filter():
    q = SearchQuery('("bayesian network" OR "bayesian networks") AND diabetes', year_from=2015, year_to=2026)
    t = translate(q, "pubmed")
    assert "2015:2026[dp]" in t.translated


def test_scopus_translation():
    q = SearchQuery('"machine learning" AND diabetes', year_from=2020)
    t = translate(q, "scopus")
    assert t.translated.startswith("TITLE-ABS-KEY(")
    assert "PUBYEAR > 2019" in t.translated


def test_translation_exposes_fidelity_metrics():
    q = SearchQuery('diabetes AND "machine learning"')
    t = translate(q, "pubmed")
    assert 0 <= t.loss_score <= 1
    assert 0 <= t.fidelity_score <= 1
