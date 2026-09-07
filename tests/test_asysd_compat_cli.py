import csv
import json
from pathlib import Path

import pytest

from metaevidence.asysd_compat import calculate_asysd_performance_contract
from metaevidence.cli import main


def test_asysd_metric_contract_matches_published_equations():
    # Gold: 3 Duplicate (positive), 2 Unique (negative)
    gold = [True, True, True, False, False]
    pred = [True, False, True, False, True]
    out = calculate_asysd_performance_contract(gold, pred)
    assert out.true_positive == 2
    assert out.false_negative == 1
    assert out.true_negative == 1
    assert out.false_positive == 1
    assert out.sensitivity_percent == pytest.approx(2/3*100)
    assert out.specificity_percent == pytest.approx(50.0)


def test_asysd_metric_contract_rejects_length_mismatch():
    with pytest.raises(ValueError):
        calculate_asysd_performance_contract([True], [True, False])


def test_cli_validate_asysd_runs_tiny_frozen_plan(tmp_path: Path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    csv_path = data / "tiny.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=["record_id", "title", "author", "year", "label"])
        w.writeheader()
        w.writerow({"record_id":"1","title":"Same title","author":"Smith J","year":"2024","label":"Unique"})
        w.writerow({"record_id":"2","title":"Same title","author":"J Smith","year":"2024","label":"Duplicate"})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"datasets":[{
        "id":"tiny","task":"publication_deduplication","role":"development",
        "source":"unit-test","filename":"tiny.csv","gold_standard_type":"removal_label",
        "expected_records":2,"expected_gold_duplicates_removed":1,"expected_gold_publications":1
    }]}), encoding="utf-8")
    out = tmp_path / "out"
    rc = main(["validate-asysd", str(manifest), str(data), str(out), "--role", "development"])
    assert rc == 0
    assert (out / "external_validation_summary.json").exists()
    payload = json.loads((out / "external_validation_summary.json").read_text())
    assert payload[0]["dataset_id"] == "tiny"
    assert payload[0]["gold_standard_type"] == "removal_label"
    assert "tiny" in capsys.readouterr().out

def test_cli_writes_asysd_compatibility_summary(tmp_path: Path):
    data = tmp_path / "data2"
    data.mkdir()
    csv_path = data / "tiny.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=["record_id", "title", "author", "year", "label"])
        w.writeheader()
        w.writerow({"record_id":"1","title":"Duplicate study","author":"Smith J","year":"2024","label":"Unique"})
        w.writerow({"record_id":"2","title":"Duplicate study","author":"Smith J","year":"2024","label":"Duplicate"})
    manifest = tmp_path / "manifest2.json"
    manifest.write_text(json.dumps({"datasets":[{
        "id":"tiny","task":"publication_deduplication","role":"development",
        "source":"unit-test","filename":"tiny.csv","gold_standard_type":"removal_label",
        "expected_records":2,"expected_gold_duplicates_removed":1,"expected_gold_publications":1
    }]}), encoding="utf-8")
    out = tmp_path / "out2"
    assert main(["validate-asysd", str(manifest), str(data), str(out), "--role", "development"]) == 0
    rows = json.loads((out / "asysd_compatibility_summary.json").read_text())
    assert {r["mode"] for r in rows} == {"blind_engine_quality", "gold_preferred_reproduction"}
    assert (out / "tiny" / "asysd_metric_contract.json").exists()
