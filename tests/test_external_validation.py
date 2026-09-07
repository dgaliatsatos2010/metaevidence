from pathlib import Path

from metaevidence import (
    ConfidenceDeduplicationEngine,
    DedupPartitionBenchmark,
    ExternalGoldDataset,
    published_2026_baselines,
    write_published_2026_baselines,
)


def _write_gold(path: Path) -> None:
    path.write_text(
        "record_id,title,author,year,journal,doi,duplicate_id\n"
        "r1,Machine learning for diabetes,Smith J,2024,Journal A,10.1/a,G1\n"
        "r2,Machine-learning for diabetes,J Smith,2024,Journal A,10.1/a,G1\n"
        "r3,Distinct diabetes paper,Jones K,2024,Journal A,10.1/b,\n",
        encoding="utf-8",
    )


def test_external_gold_loader_detects_group_and_singleton(tmp_path: Path):
    p = tmp_path / "gold.csv"
    _write_gold(p)
    ds = ExternalGoldDataset.from_delimited(p, name="gold")
    assert ds.n_records == 3
    assert ds.n_gold_publications == 2
    assert ds.n_gold_duplicates_removed == 1
    assert ds.gold_group_ids[0] == ds.gold_group_ids[1]
    assert ds.gold_group_ids[2].startswith("__SINGLETON__")
    assert ds.records[0].doi == "10.1/a"


def test_partition_benchmark_perfect_on_exact_doi(tmp_path: Path):
    p = tmp_path / "gold.csv"
    _write_gold(p)
    ds = ExternalGoldDataset.from_delimited(p, name="gold")
    r = DedupPartitionBenchmark.evaluate(ds)
    assert r.metrics.predicted_publications == 2
    assert r.metrics.removed_singulars == 0
    assert r.metrics.missed_duplicates == 0
    assert r.metrics.singular_retention == 1.0
    assert r.metrics.duplicate_recall == 1.0


def test_partition_benchmark_reports_missed_duplicate(tmp_path: Path):
    p = tmp_path / "gold.csv"
    _write_gold(p)
    ds = ExternalGoldDataset.from_delimited(p, name="gold")
    engine = ConfidenceDeduplicationEngine(auto_merge_threshold=1.0, review_threshold=0.999999)
    r = DedupPartitionBenchmark.evaluate(ds, engine=engine)
    # Exact DOI rule produces 0.99999, below a threshold of 1.0.
    assert r.metrics.missed_duplicates == 1
    assert r.metrics.duplicate_recall == 0.0


def test_partition_benchmark_reports_removed_singular(tmp_path: Path):
    p = tmp_path / "badmerge.csv"
    p.write_text(
        "id,title,author,year,journal,duplicate_group\n"
        "a,Identical title,Smith J,2024,J,GA\n"
        "b,Identical title,Smith J,2024,J,GB\n",
        encoding="utf-8",
    )
    ds = ExternalGoldDataset.from_delimited(p)
    r = DedupPartitionBenchmark.evaluate(ds)
    assert r.metrics.removed_singulars == 1
    assert r.metrics.singular_retention == 0.5


def test_loader_allows_column_overrides(tmp_path: Path):
    p = tmp_path / "custom.tsv"
    p.write_text("RID\tT\tG\n1\tPaper one\tX\n2\tPaper one\tX\n", encoding="utf-8")
    ds = ExternalGoldDataset.from_delimited(
        p,
        field_overrides={"record_id": "RID", "title": "T"},
        group_column="G",
    )
    assert ds.n_gold_publications == 1


def test_published_2026_baselines_have_eight_tools(tmp_path: Path):
    rows = published_2026_baselines()
    assert len(rows) == 8
    asysd = next(x for x in rows if x.tool == "ASySD")
    assert asysd.removed_singulars == 22
    assert asysd.missed_duplicates == 34
    out = write_published_2026_baselines(tmp_path / "baseline.csv")
    assert out.exists()


def test_external_dataset_integrity_check_passes_and_strict_failure(tmp_path):
    from metaevidence import ExternalDatasetSpecification, validate_external_dataset

    path = tmp_path / "gold.csv"
    path.write_text(
        "id,title,duplicate_id\n"
        "1,Alpha,G1\n"
        "2,Alpha,G1\n"
        "3,Beta,\n",
        encoding="utf-8",
    )
    dataset = ExternalGoldDataset.from_delimited(path)
    spec = ExternalDatasetSpecification(
        id="demo",
        role="held_out_test",
        source="synthetic fixture",
        expected_records=3,
        expected_gold_duplicates_removed=1,
        expected_gold_publications=2,
    )
    check = validate_external_dataset(dataset, spec, strict=True)
    assert check.passed
    assert check.observed_gold_publications == 2

    bad = ExternalDatasetSpecification(
        id="bad",
        role="held_out_test",
        source="synthetic fixture",
        expected_records=4,
    )
    import pytest
    with pytest.raises(ValueError):
        validate_external_dataset(dataset, bad, strict=True)


def test_load_external_dataset_specifications(tmp_path):
    from metaevidence import load_external_dataset_specifications
    import json

    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"datasets": [
        {
            "id": "a",
            "task": "publication_deduplication",
            "role": "development",
            "source": "x",
            "expected_records": 10,
            "expected_gold_duplicates_removed": 2,
            "expected_gold_publications": 8,
        },
        {"id": "q", "task": "query_translation", "role": "prospective_benchmark", "source": "y"},
    ]}), encoding="utf-8")
    specs = load_external_dataset_specifications(plan)
    assert len(specs) == 1
    assert specs[0].id == "a"
    assert specs[0].expected_gold_publications == 8


def test_external_validation_export_contains_gold_and_source_hash(tmp_path):
    from metaevidence import (
        ExternalDatasetSpecification,
        write_external_validation_result,
    )
    import csv
    import json

    p = tmp_path / "gold.csv"
    _write_gold(p)
    ds = ExternalGoldDataset.from_delimited(p, name="gold")
    result = DedupPartitionBenchmark.evaluate(ds)
    spec = ExternalDatasetSpecification(
        id="gold",
        role="held_out_test",
        source="fixture",
        expected_records=3,
        expected_gold_duplicates_removed=1,
        expected_gold_publications=2,
    )
    out = write_external_validation_result(result, tmp_path / "out", dataset=ds, specification=spec)
    manifest = json.loads((out / "external_validation_manifest.json").read_text())
    assert manifest["dataset"]["source_sha256"]
    assert manifest["integrity_check"]["passed"] is True
    rows = list(csv.DictReader((out / "partition_assignments.csv").open()))
    assert rows[0]["record_id"] == "r1"
    assert rows[0]["gold_group"] == "G1"
