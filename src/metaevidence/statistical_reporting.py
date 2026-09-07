from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist, mean
from typing import Iterable, Sequence

from .external_validation import RemovalLabelMetrics


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    estimate: float
    lower: float
    upper: float
    confidence: float = 0.95
    method: str = "wilson"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DatasetRemovalStatistics:
    dataset: str
    input_records: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    sensitivity: ConfidenceInterval
    specificity: ConfidenceInterval
    precision: ConfidenceInterval
    accuracy: ConfidenceInterval
    f1: float
    false_unique_removals: int
    missed_duplicates: int

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset,
            "input_records": self.input_records,
            "true_positive": self.true_positive,
            "true_negative": self.true_negative,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "sensitivity": self.sensitivity.to_dict(),
            "specificity": self.specificity.to_dict(),
            "precision": self.precision.to_dict(),
            "accuracy": self.accuracy.to_dict(),
            "f1": self.f1,
            "false_unique_removals": self.false_unique_removals,
            "missed_duplicates": self.missed_duplicates,
        }


@dataclass(frozen=True, slots=True)
class MacroMetric:
    metric: str
    estimate: float
    lower: float
    upper: float
    bootstrap_replicates: int
    seed: int
    method: str = "review_level_percentile_bootstrap"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RemovalStatisticalReport:
    datasets: tuple[DatasetRemovalStatistics, ...]
    micro: dict[str, ConfidenceInterval | float | int]
    macro: dict[str, MacroMetric]
    pooled_confusion: dict[str, int]
    false_unique_removals: int
    missed_duplicates: int
    bootstrap_replicates: int
    bootstrap_seed: int

    def to_dict(self) -> dict[str, object]:
        def convert(value: object) -> object:
            if hasattr(value, "to_dict"):
                return value.to_dict()  # type: ignore[no-any-return]
            return value
        return {
            "schema_version": "1.0",
            "primary_endpoint": "blind_engine_quality",
            "datasets": [d.to_dict() for d in self.datasets],
            "micro": {k: convert(v) for k, v in self.micro.items()},
            "macro": {k: v.to_dict() for k, v in self.macro.items()},
            "pooled_confusion": dict(self.pooled_confusion),
            "false_unique_removals": self.false_unique_removals,
            "missed_duplicates": self.missed_duplicates,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_seed": self.bootstrap_seed,
        }


def _safe_div(num: float, den: float, *, empty: float = 0.0) -> float:
    return num / den if den else empty


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> ConfidenceInterval:
    """Wilson score interval for one binomial proportion."""
    if successes < 0 or total < 0 or successes > total:
        raise ValueError("Require 0 <= successes <= total")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    if total == 0:
        return ConfidenceInterval(float("nan"), float("nan"), float("nan"), confidence)
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    p = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denom
    half = z * math.sqrt((p * (1.0 - p) / total) + z2 / (4.0 * total * total)) / denom
    return ConfidenceInterval(p, max(0.0, center - half), min(1.0, center + half), confidence)


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return float("nan")
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _macro_bootstrap(
    metrics: Sequence[RemovalLabelMetrics],
    attribute: str,
    *,
    replicates: int,
    seed: int,
    confidence: float,
) -> MacroMetric:
    values = [float(getattr(m, attribute)) for m in metrics]
    if not values:
        raise ValueError("At least one dataset is required")
    estimate = mean(values)
    if len(values) == 1:
        return MacroMetric(attribute, estimate, estimate, estimate, replicates, seed)
    rng = random.Random(seed)
    boots: list[float] = []
    n = len(values)
    for _ in range(replicates):
        boots.append(mean(values[rng.randrange(n)] for _ in range(n)))
    alpha = (1.0 - confidence) / 2.0
    return MacroMetric(
        attribute,
        estimate,
        _percentile(boots, alpha),
        _percentile(boots, 1.0 - alpha),
        replicates,
        seed,
    )


def _dataset_statistics(m: RemovalLabelMetrics, confidence: float) -> DatasetRemovalStatistics:
    tp, tn, fp, fn = m.true_positive, m.true_negative, m.false_positive, m.false_negative
    return DatasetRemovalStatistics(
        dataset=m.dataset,
        input_records=m.input_records,
        true_positive=tp,
        true_negative=tn,
        false_positive=fp,
        false_negative=fn,
        sensitivity=wilson_interval(tp, tp + fn, confidence),
        specificity=wilson_interval(tn, tn + fp, confidence),
        precision=wilson_interval(tp, tp + fp, confidence),
        accuracy=wilson_interval(tp + tn, tp + tn + fp + fn, confidence),
        f1=m.f1,
        false_unique_removals=fp,
        missed_duplicates=fn,
    )


def summarize_removal_metrics(
    metrics: Sequence[RemovalLabelMetrics],
    *,
    confidence: float = 0.95,
    bootstrap_replicates: int = 5000,
    bootstrap_seed: int = 20260907,
) -> RemovalStatisticalReport:
    """Summarize frozen blind record-removal results for publication reporting.

    Micro estimates pool confusion counts and are therefore record weighted.
    Macro estimates are unweighted means over review/corpus units.  Their
    uncertainty is obtained by resampling review/corpus units rather than
    individual citations.
    """
    rows = tuple(metrics)
    if not rows:
        raise ValueError("At least one removal-metric result is required")
    if bootstrap_replicates < 1:
        raise ValueError("bootstrap_replicates must be >= 1")

    tp = sum(m.true_positive for m in rows)
    tn = sum(m.true_negative for m in rows)
    fp = sum(m.false_positive for m in rows)
    fn = sum(m.false_negative for m in rows)
    micro_precision = _safe_div(tp, tp + fp, empty=1.0)
    micro_sensitivity = _safe_div(tp, tp + fn, empty=1.0)
    micro_f1 = _safe_div(2 * micro_precision * micro_sensitivity, micro_precision + micro_sensitivity)

    micro: dict[str, ConfidenceInterval | float | int] = {
        "sensitivity": wilson_interval(tp, tp + fn, confidence),
        "specificity": wilson_interval(tn, tn + fp, confidence),
        "precision": wilson_interval(tp, tp + fp, confidence),
        "accuracy": wilson_interval(tp + tn, tp + tn + fp + fn, confidence),
        "f1": micro_f1,
        "records": tp + tn + fp + fn,
    }
    macro = {
        name: _macro_bootstrap(
            rows, name,
            replicates=bootstrap_replicates,
            seed=bootstrap_seed,
            confidence=confidence,
        )
        for name in ("sensitivity", "specificity", "precision", "f1")
    }
    return RemovalStatisticalReport(
        datasets=tuple(_dataset_statistics(m, confidence) for m in rows),
        micro=micro,
        macro=macro,
        pooled_confusion={"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        false_unique_removals=fp,
        missed_duplicates=fn,
        bootstrap_replicates=bootstrap_replicates,
        bootstrap_seed=bootstrap_seed,
    )


def _metrics_from_payload(payload: dict[str, object]) -> RemovalLabelMetrics:
    required = {
        "dataset", "input_records", "gold_duplicates_removed", "predicted_duplicates_removed",
        "true_positive", "true_negative", "false_positive", "false_negative",
        "sensitivity", "specificity", "precision", "f1", "accuracy",
        "false_positive_rate", "false_negative_rate", "candidate_pairs", "assessed_pairs",
        "auto_merge_pairs", "review_pairs", "used_exhaustive_pairing",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"Removal metrics payload is missing fields: {', '.join(missing)}")
    return RemovalLabelMetrics(**{k: payload[k] for k in required})  # type: ignore[arg-type]


def load_blind_removal_metrics(root: str | Path) -> list[RemovalLabelMetrics]:
    """Load primary blind removal metrics and exclude gold-informed reproduction outputs."""
    root = Path(root)
    candidates = [root] if root.is_file() else sorted(root.rglob("external_removal_metrics.json"))
    blind = [p for p in candidates if "blind_engine_quality" in p.parts]
    selected = blind or [
        p for p in candidates
        if "gold_preferred_reproduction" not in p.parts and "retention_reproduction" not in p.parts
    ]
    metrics: list[RemovalLabelMetrics] = []
    seen: set[tuple[str, str]] = set()
    for path in selected:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected object in {path}")
        item = _metrics_from_payload(payload)
        key = (item.dataset, str(path.resolve()))
        if key in seen:
            continue
        seen.add(key)
        metrics.append(item)
    if not metrics:
        raise FileNotFoundError(f"No blind external_removal_metrics.json files found under {root}")
    metrics.sort(key=lambda m: m.dataset.lower())
    return metrics


def write_removal_statistical_report(report: RemovalStatisticalReport, root: str | Path) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "removal_statistical_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    dataset_csv = root / "removal_dataset_statistics.csv"
    fields = [
        "dataset", "input_records", "tp", "tn", "fp", "fn",
        "sensitivity", "sensitivity_ci_low", "sensitivity_ci_high",
        "specificity", "specificity_ci_low", "specificity_ci_high",
        "precision", "precision_ci_low", "precision_ci_high",
        "f1", "accuracy", "accuracy_ci_low", "accuracy_ci_high",
        "false_unique_removals", "missed_duplicates",
    ]
    with dataset_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for d in report.datasets:
            writer.writerow({
                "dataset": d.dataset, "input_records": d.input_records,
                "tp": d.true_positive, "tn": d.true_negative, "fp": d.false_positive, "fn": d.false_negative,
                "sensitivity": d.sensitivity.estimate, "sensitivity_ci_low": d.sensitivity.lower, "sensitivity_ci_high": d.sensitivity.upper,
                "specificity": d.specificity.estimate, "specificity_ci_low": d.specificity.lower, "specificity_ci_high": d.specificity.upper,
                "precision": d.precision.estimate, "precision_ci_low": d.precision.lower, "precision_ci_high": d.precision.upper,
                "f1": d.f1,
                "accuracy": d.accuracy.estimate, "accuracy_ci_low": d.accuracy.lower, "accuracy_ci_high": d.accuracy.upper,
                "false_unique_removals": d.false_unique_removals, "missed_duplicates": d.missed_duplicates,
            })

    aggregate_csv = root / "removal_aggregate_statistics.csv"
    with aggregate_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["aggregation", "metric", "estimate", "ci_low", "ci_high", "method"])
        for name in ("sensitivity", "specificity", "precision", "accuracy"):
            ci = report.micro[name]
            assert isinstance(ci, ConfidenceInterval)
            writer.writerow(["micro", name, ci.estimate, ci.lower, ci.upper, ci.method])
        writer.writerow(["micro", "f1", report.micro["f1"], "", "", "point_estimate"])
        for name, value in report.macro.items():
            writer.writerow(["macro", name, value.estimate, value.lower, value.upper, value.method])

    manuscript_csv = root / "manuscript_deduplication_table.csv"
    with manuscript_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Dataset", "N", "Sensitivity (95% CI)", "Specificity (95% CI)", "Precision (95% CI)", "F1", "False unique removals", "Missed duplicates"])
        for d in report.datasets:
            fmt = lambda ci: f"{ci.estimate:.4f} ({ci.lower:.4f}-{ci.upper:.4f})"
            writer.writerow([d.dataset, d.input_records, fmt(d.sensitivity), fmt(d.specificity), fmt(d.precision), f"{d.f1:.4f}", d.false_unique_removals, d.missed_duplicates])

    markdown = root / "manuscript_deduplication_summary.md"
    lines = [
        "# MetaEvidence external deduplication statistical summary",
        "",
        "Primary endpoint: blind engine-quality retention.",
        "",
        f"Datasets: {len(report.datasets)}; pooled records: {report.micro['records']}; false unique removals: {report.false_unique_removals}; missed duplicates: {report.missed_duplicates}.",
        "",
        "## Pooled micro estimates",
    ]
    for name in ("sensitivity", "specificity", "precision", "accuracy"):
        ci = report.micro[name]
        assert isinstance(ci, ConfidenceInterval)
        lines.append(f"- {name}: {ci.estimate:.4f} (95% CI {ci.lower:.4f}-{ci.upper:.4f})")
    lines.append(f"- F1: {float(report.micro['f1']):.4f}")
    lines.extend(["", "## Unweighted macro review-level estimates"])
    for name, item in report.macro.items():
        lines.append(f"- {name}: {item.estimate:.4f} (95% bootstrap interval {item.lower:.4f}-{item.upper:.4f})")
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def summarize_removal_result_directory(
    input_root: str | Path,
    output_root: str | Path,
    *,
    confidence: float = 0.95,
    bootstrap_replicates: int = 5000,
    bootstrap_seed: int = 20260907,
) -> RemovalStatisticalReport:
    metrics = load_blind_removal_metrics(input_root)
    report = summarize_removal_metrics(
        metrics,
        confidence=confidence,
        bootstrap_replicates=bootstrap_replicates,
        bootstrap_seed=bootstrap_seed,
    )
    write_removal_statistical_report(report, output_root)
    return report
