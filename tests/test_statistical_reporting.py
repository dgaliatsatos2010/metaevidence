from __future__ import annotations

import json
from pathlib import Path

import pytest

from metaevidence.cli import main
from metaevidence.external_validation import RemovalLabelMetrics
from metaevidence.statistical_reporting import (
    load_blind_removal_metrics,
    summarize_removal_metrics,
    wilson_interval,
    write_removal_statistical_report,
)


def metric(name: str, tp: int, tn: int, fp: int, fn: int) -> RemovalLabelMetrics:
    sensitivity = tp / (tp + fn) if tp + fn else 1.0
    specificity = tn / (tn + fp) if tn + fp else 1.0
    precision = tp / (tp + fp) if tp + fp else 1.0
    f1 = 2 * precision * sensitivity / (precision + sensitivity) if precision + sensitivity else 0.0
    n = tp + tn + fp + fn
    return RemovalLabelMetrics(
        dataset=name, input_records=n,
        gold_duplicates_removed=tp + fn, predicted_duplicates_removed=tp + fp,
        true_positive=tp, true_negative=tn, false_positive=fp, false_negative=fn,
        sensitivity=sensitivity, specificity=specificity, precision=precision, f1=f1,
        accuracy=(tp + tn) / n,
        false_positive_rate=fp / (tn + fp) if tn + fp else 0.0,
        false_negative_rate=fn / (tp + fn) if tp + fn else 0.0,
        candidate_pairs=10, assessed_pairs=10, auto_merge_pairs=1, review_pairs=0,
        used_exhaustive_pairing=True,
    )


def test_wilson_interval_known_value():
    ci = wilson_interval(50, 100)
    assert ci.estimate == 0.5
    assert ci.lower == pytest.approx(0.4038, abs=5e-4)
    assert ci.upper == pytest.approx(0.5962, abs=5e-4)


def test_micro_and_macro_are_distinct_and_review_weighted():
    report = summarize_removal_metrics([
        metric("small", 9, 9, 1, 1),
        metric("large", 10, 890, 90, 10),
    ], bootstrap_replicates=200, bootstrap_seed=7)
    assert report.micro["sensitivity"].estimate == pytest.approx(19 / 30)  # type: ignore[union-attr]
    assert report.macro["sensitivity"].estimate == pytest.approx((0.9 + 0.5) / 2)
    assert report.false_unique_removals == 91
    assert report.missed_duplicates == 11


def test_macro_bootstrap_is_deterministic():
    rows = [metric("a", 9, 90, 10, 1), metric("b", 8, 95, 5, 2), metric("c", 7, 98, 2, 3)]
    a = summarize_removal_metrics(rows, bootstrap_replicates=250, bootstrap_seed=20260907)
    b = summarize_removal_metrics(rows, bootstrap_replicates=250, bootstrap_seed=20260907)
    assert a.macro["f1"] == b.macro["f1"]


def test_blind_loader_excludes_gold_preferred_when_blind_exists(tmp_path: Path):
    blind = tmp_path / "review" / "blind_engine_quality"
    gold = tmp_path / "review" / "gold_preferred_reproduction"
    blind.mkdir(parents=True); gold.mkdir(parents=True)
    blind_payload = metric("review", 8, 90, 2, 2).to_dict()
    gold_payload = metric("review-gold", 10, 90, 0, 0).to_dict()
    (blind / "external_removal_metrics.json").write_text(json.dumps(blind_payload), encoding="utf-8")
    (gold / "external_removal_metrics.json").write_text(json.dumps(gold_payload), encoding="utf-8")
    loaded = load_blind_removal_metrics(tmp_path)
    assert [x.dataset for x in loaded] == ["review"]


def test_writer_and_cli_create_publication_bundle(tmp_path: Path):
    inp = tmp_path / "input" / "d1" / "blind_engine_quality"
    inp.mkdir(parents=True)
    (inp / "external_removal_metrics.json").write_text(
        json.dumps(metric("d1", 9, 90, 10, 1).to_dict()), encoding="utf-8"
    )
    out = tmp_path / "out"
    assert main(["summarize-removal-results", str(tmp_path / "input"), str(out), "--bootstrap-replicates", "50"]) == 0
    expected = {
        "removal_statistical_report.json", "removal_dataset_statistics.csv",
        "removal_aggregate_statistics.csv", "manuscript_deduplication_table.csv",
        "manuscript_deduplication_summary.md",
    }
    assert expected.issubset({p.name for p in out.iterdir()})
