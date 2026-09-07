from metaevidence import EvidenceRecord, SourceHit
from metaevidence.dedup import (
    ConfidenceDeduplicationEngine,
    DeduplicationDecision,
)
from metaevidence.benchmark import DeduplicationBenchmark, LabeledPair, PlattCalibrator


def test_exact_doi_is_auto_merge_and_explainable():
    a = EvidenceRecord(title="A trial", doi="https://doi.org/10.1000/ABC")
    b = EvidenceRecord(title="A trial updated metadata", doi="doi:10.1000/abc")
    x = ConfidenceDeduplicationEngine().assess_pair(a, b)
    assert x.decision is DeduplicationDecision.AUTO_MERGE
    assert x.probability >= 0.999
    assert x.features.doi_exact == 1.0
    assert any("DOI" in line for line in x.explanation)


def test_conflicting_dois_block_automatic_merge_even_with_same_title():
    a = EvidenceRecord(title="Identical title", authors=["Smith J"], year=2024, doi="10.1000/a")
    b = EvidenceRecord(title="Identical title", authors=["J Smith"], year=2024, doi="10.1000/b")
    x = ConfidenceDeduplicationEngine().assess_pair(a, b)
    assert x.features.doi_conflict == 1.0
    assert x.decision is DeduplicationDecision.KEEP_SEPARATE
    assert x.probability < 0.2


def test_ambiguous_bibliographic_pair_goes_to_review_queue():
    a = EvidenceRecord(
        title="Deep learning for cancer diagnosis",
        authors=["Smith J"],
        year=2024,
        journal="Cancer Research",
    )
    b = EvidenceRecord(
        title="Deep learning model for cancer diagnosis",
        authors=["J Smith"],
        year=2024,
        journal="Cancer Research",
    )
    result = ConfidenceDeduplicationEngine().deduplicate([a, b])
    assert len(result.records) == 2
    assert len(result.review_queue) == 1
    assert result.review_queue[0].decision is DeduplicationDecision.REVIEW


def test_merge_preserves_provenance_and_conflicting_metadata():
    a = EvidenceRecord(
        title="Machine learning prediction of diabetes outcomes",
        authors=["Smith J"],
        year=2024,
        journal="Diabetes Care",
        abstract="Long abstract",
        source_hits=[SourceHit("pubmed", "1")],
    )
    b = EvidenceRecord(
        title="Machine-learning prediction of diabetes outcome",
        authors=["J Smith"],
        year=2024,
        journal="Diabetes Care",
        source_hits=[SourceHit("openalex", "W1")],
    )
    result = ConfidenceDeduplicationEngine(fuzzy_threshold=0.94).deduplicate([a, b])
    assert len(result.records) == 1
    merged = result.records[0]
    assert set(merged.sources) == {"pubmed", "openalex"}
    assert merged.metadata["metaevidence_cluster_size"] == 2
    assert result.links[0].rule == "title_fuzzy_confidence"


def test_large_dataset_uses_blocking_and_still_finds_exact_doi():
    records = [EvidenceRecord(title=f"Unique record {i}", year=2020 + (i % 3)) for i in range(12)]
    records[3].doi = "10.1234/shared"
    records[10].doi = "10.1234/shared"
    engine = ConfidenceDeduplicationEngine(exhaustive_limit=5)
    result = engine.deduplicate(records)
    assert result.stats is not None
    assert result.stats.used_exhaustive_pairing is False
    assert len(result.records) == 11
    assert any(link.rule == "doi_exact" for link in result.links)


def test_benchmark_metrics_are_computed_from_labelled_pairs():
    records = [
        EvidenceRecord(title="Paper A", doi="10.1/a"),
        EvidenceRecord(title="Paper A alternative metadata", doi="10.1/a"),
        EvidenceRecord(title="Completely different paper", doi="10.1/b"),
    ]
    labels = [LabeledPair(0, 1, True), LabeledPair(0, 2, False)]
    metrics = DeduplicationBenchmark().evaluate(records, labels)
    assert metrics.true_positive == 1
    assert metrics.true_negative == 1
    assert metrics.false_positive == 0
    assert metrics.false_negative == 0
    assert metrics.f1 == 1.0
    assert 0.0 <= metrics.brier_score <= 1.0


def test_platt_calibrator_fit_and_predict():
    calibrator = PlattCalibrator().fit(
        [0.02, 0.10, 0.75, 0.95],
        [False, False, True, True],
        epochs=500,
    )
    low = calibrator.predict(0.10)
    high = calibrator.predict(0.90)
    assert calibrator.fitted
    assert 0 <= low < high <= 1


def test_short_exact_title_without_corroboration_is_not_auto_merged():
    a = EvidenceRecord(title="Editorial", year=2024)
    b = EvidenceRecord(title="Editorial", year=2024)
    x = ConfidenceDeduplicationEngine().assess_pair(a, b)
    assert x.decision is not DeduplicationDecision.AUTO_MERGE


def test_preprint_and_journal_article_are_not_collapsed_as_duplicate_publications():
    a = EvidenceRecord(
        title="A new treatment for disease X",
        authors=["Smith J"],
        year=2024,
        metadata={"type": "posted-content"},
    )
    b = EvidenceRecord(
        title="A new treatment for disease X",
        authors=["J Smith"],
        year=2024,
        metadata={"type": "journal-article"},
    )
    x = ConfidenceDeduplicationEngine().assess_pair(a, b)
    assert x.features.publication_form_conflict == 1.0
    assert x.decision is DeduplicationDecision.KEEP_SEPARATE
    assert x.probability <= 0.45


def test_threshold_optimizer_can_enforce_precision_floor():
    records = [
        EvidenceRecord(title="Paper A", doi="10.1/a"),
        EvidenceRecord(title="Paper A metadata variant", doi="10.1/a"),
        EvidenceRecord(title="Different paper", doi="10.1/b"),
        EvidenceRecord(title="Deep learning for cancer diagnosis", authors=["Smith J"], year=2024, journal="Cancer Research"),
        EvidenceRecord(title="Deep learning model for cancer diagnosis", authors=["J Smith"], year=2024, journal="Cancer Research"),
    ]
    labels = [
        LabeledPair(0, 1, True),
        LabeledPair(0, 2, False),
        LabeledPair(3, 4, False),
    ]
    result = DeduplicationBenchmark().optimize_threshold(records, labels, minimum_precision=1.0, step=0.01)
    assert result.precision == 1.0
    assert 0.0 <= result.threshold <= 1.0
