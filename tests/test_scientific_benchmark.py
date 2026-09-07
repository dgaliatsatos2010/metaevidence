from pathlib import Path

from metaevidence import (
    DeduplicationAblationBenchmark,
    MetadataStressBenchmark,
    QueryTranslationBenchmark,
    QueryTranslationBenchmarkCase,
    RetrievalSetMetrics,
    ScalabilityBenchmark,
    ScientificBenchmarkBundle,
    StudyLinkageAblationBenchmark,
    bootstrap_proportion_ci,
    synthetic_deduplication_dataset,
    synthetic_study_linkage_dataset,
    synthetic_unique_records,
)


def test_retrieval_set_metrics_exact_match():
    m = RetrievalSetMetrics.from_sets({"a", "b"}, {"a", "b"})
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.jaccard == 1.0
    assert m.relative_count_error == 0.0


def test_retrieval_set_metrics_partial():
    m = RetrievalSetMetrics.from_sets({"a", "b", "c"}, {"b", "c", "d"})
    assert m.intersection_count == 2
    assert round(m.precision, 4) == 0.6667
    assert round(m.recall, 4) == 0.6667
    assert m.jaccard == 0.5


def test_query_translation_benchmark_case():
    case = QueryTranslationBenchmarkCase(
        case_id="q1",
        source="pubmed",
        reference_ids=frozenset({"1", "2", "3"}),
        candidate_ids=frozenset({"1", "2", "4"}),
        fidelity_score=0.9,
        loss_score=0.1,
        requires_review=True,
    )
    r = QueryTranslationBenchmark.evaluate(case)
    assert r.case_id == "q1"
    assert r.metrics.intersection_count == 2
    assert r.requires_review is True


def test_synthetic_dedup_dataset_contains_positive_and_negative_labels():
    records, labels = synthetic_deduplication_dataset(15, duplicate_fraction=0.8, seed=1)
    assert len(records) >= 15
    assert any(x.is_duplicate for x in labels)
    assert any(not x.is_duplicate for x in labels)


def test_dedup_ablation_has_baseline_and_requested_feature():
    records, labels = synthetic_deduplication_dataset(12, duplicate_fraction=0.9, seed=3)
    rows = DeduplicationAblationBenchmark().evaluate(records, labels, features=["doi_exact"])
    assert [x.ablated_feature for x in rows] == ["<none>", "doi_exact"]
    assert all(0 <= x.f1 <= 1 for x in rows)


def test_synthetic_study_dataset_and_ablation():
    records, labels = synthetic_study_linkage_dataset(5, seed=2)
    assert any(x.same_study for x in labels)
    assert any(not x.same_study for x in labels)
    rows = StudyLinkageAblationBenchmark().evaluate(records, labels, features=["registry_exact"])
    assert [x.ablated_feature for x in rows] == ["<none>", "registry_exact"]


def test_metadata_stress_is_deterministic():
    records, _ = synthetic_deduplication_dataset(8, duplicate_fraction=0.5, seed=4)
    a = MetadataStressBenchmark.degrade(records, missing_rate=0.5, fields=["doi", "authors"], seed=99)
    b = MetadataStressBenchmark.degrade(records, missing_rate=0.5, fields=["doi", "authors"], seed=99)
    assert [(x.doi, x.authors) for x in a] == [(x.doi, x.authors) for x in b]


def test_metadata_stress_dedup_evaluation():
    records, labels = synthetic_deduplication_dataset(10, duplicate_fraction=0.7, seed=5)
    rows = MetadataStressBenchmark.evaluate_deduplication(
        records, labels, missing_rates=[0.0, 0.5], repeats=1, fields=["doi", "authors", "year"]
    )
    assert len(rows) == 2
    assert rows[0].missing_rate == 0.0
    assert 0 <= rows[1].precision <= 1


def test_metadata_stress_study_evaluation():
    records, labels = synthetic_study_linkage_dataset(4, seed=6)
    rows = MetadataStressBenchmark.evaluate_study_linkage(
        records, labels, missing_rates=[0.0, 0.5], repeats=1, fields=["doi", "authors", "year"]
    )
    assert len(rows) == 2
    assert rows[1].task == "study_linkage"


def test_scalability_benchmark_small():
    rows = ScalabilityBenchmark.deduplication(synthetic_unique_records, [5, 8], repeats=1)
    assert len(rows) == 2
    assert all(x.elapsed_seconds >= 0 for x in rows)
    assert all(x.output_groups == x.n_records for x in rows)


def test_bootstrap_ci_bounds():
    ci = bootstrap_proportion_ci([1, 1, 1, 0, 0], n_bootstrap=200, seed=1)
    assert 0 <= ci.low <= ci.estimate <= ci.high <= 1
    assert ci.estimate == 0.6


def test_scientific_benchmark_bundle_writes_hash_manifest(tmp_path: Path):
    case = QueryTranslationBenchmarkCase(
        case_id="q1", source="pubmed",
        reference_ids=frozenset({"1", "2"}), candidate_ids=frozenset({"1", "2"}),
    )
    bundle = ScientificBenchmarkBundle(
        name="unit-test",
        query_translation=[QueryTranslationBenchmark.evaluate(case)],
        notes=["engineering QA"],
    )
    root = bundle.write(tmp_path / "bench")
    assert (root / "query_translation.csv").exists()
    assert (root / "benchmark_results.json").exists()
    assert (root / "benchmark_manifest.json").exists()


def test_blocking_recall_exhaustive_small():
    from metaevidence import BlockingRecallBenchmark
    records, labels = synthetic_deduplication_dataset(10, duplicate_fraction=0.8, seed=13)
    r = BlockingRecallBenchmark.deduplication(records, labels)
    assert r.used_exhaustive_pairing is True
    assert r.blocking_recall == 1.0
    assert r.pair_reduction_fraction == 0.0


def test_blocking_recall_large_forced_blocking():
    from metaevidence import BlockingRecallBenchmark, ConfidenceDeduplicationEngine
    records, labels = synthetic_deduplication_dataset(25, duplicate_fraction=0.8, seed=14)
    engine = ConfidenceDeduplicationEngine(exhaustive_limit=5)
    r = BlockingRecallBenchmark.deduplication(records, labels, engine=engine)
    assert r.used_exhaustive_pairing is False
    assert 0 <= r.blocking_recall <= 1
    assert r.pair_reduction_fraction > 0
