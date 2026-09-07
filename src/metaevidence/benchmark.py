from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .dedup import ConfidenceDeduplicationEngine, DeduplicationDecision
from .models import EvidenceRecord


@dataclass(frozen=True, slots=True)
class LabeledPair:
    left_index: int
    right_index: int
    is_duplicate: bool


@dataclass(slots=True)
class BenchmarkMetrics:
    n_pairs: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    sensitivity: float
    specificity: float
    precision: float
    f1: float
    accuracy: float
    brier_score: float
    expected_calibration_error: float
    false_merge_rate: float
    review_fraction: float
    auto_merge_count: int
    review_count: int
    keep_separate_count: int


@dataclass(slots=True)
class ThresholdResult:
    threshold: float
    precision: float
    recall: float
    f1: float
    false_positive: int
    false_negative: int


class PlattCalibrator:
    """Small dependency-free logistic calibrator for deduplication probabilities.

    Fit on a labelled validation set that is separate from the final test set.
    This class deliberately stays simple so that calibration is auditable.
    """

    def __init__(self) -> None:
        self.a = 1.0
        self.b = 0.0
        self.fitted = False

    @staticmethod
    def _logit(p: float) -> float:
        p = min(1 - 1e-6, max(1e-6, p))
        return math.log(p / (1 - p))

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1 / (1 + z)
        z = math.exp(x)
        return z / (1 + z)

    def fit(self, probabilities: Iterable[float], labels: Iterable[bool], *, epochs: int = 2000, learning_rate: float = 0.02, l2: float = 1e-4) -> "PlattCalibrator":
        xs = [self._logit(float(p)) for p in probabilities]
        ys = [1.0 if y else 0.0 for y in labels]
        if len(xs) != len(ys) or not xs:
            raise ValueError("probabilities and labels must be non-empty and equal length")
        if len(set(ys)) < 2:
            raise ValueError("calibration requires both duplicate and non-duplicate labels")

        a, b = 1.0, 0.0
        n = len(xs)
        for _ in range(epochs):
            ga = gb = 0.0
            for x, y in zip(xs, ys):
                p = self._sigmoid(a * x + b)
                e = p - y
                ga += e * x
                gb += e
            ga = ga / n + l2 * a
            gb = gb / n
            a -= learning_rate * ga
            b -= learning_rate * gb
        self.a, self.b, self.fitted = a, b, True
        return self

    def predict(self, probability: float) -> float:
        if not self.fitted:
            raise RuntimeError("calibrator must be fitted before predict")
        return self._sigmoid(self.a * self._logit(float(probability)) + self.b)


class DeduplicationBenchmark:
    def __init__(self, engine: ConfidenceDeduplicationEngine | None = None) -> None:
        self.engine = engine or ConfidenceDeduplicationEngine()

    def evaluate(self, records: list[EvidenceRecord], labels: Iterable[LabeledPair], threshold: float | None = None) -> BenchmarkMetrics:
        threshold = self.engine.auto_merge_threshold if threshold is None else threshold
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be in [0, 1]")

        tp = tn = fp = fn = 0
        brier = 0.0
        count = 0
        predictions: list[tuple[float, float]] = []
        auto_merge_count = review_count = keep_count = 0
        for item in labels:
            assessment = self.engine.assess_pair(records[item.left_index], records[item.right_index], item.left_index, item.right_index)
            pred = assessment.probability >= threshold
            truth = bool(item.is_duplicate)
            if pred and truth:
                tp += 1
            elif pred and not truth:
                fp += 1
            elif not pred and truth:
                fn += 1
            else:
                tn += 1
            y = 1.0 if truth else 0.0
            brier += (assessment.probability - y) ** 2
            predictions.append((assessment.probability, y))
            if assessment.decision is DeduplicationDecision.AUTO_MERGE:
                auto_merge_count += 1
            elif assessment.decision is DeduplicationDecision.REVIEW:
                review_count += 1
            else:
                keep_count += 1
            count += 1

        if count == 0:
            raise ValueError("labels must not be empty")
        sensitivity = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        precision = tp / (tp + fp) if tp + fp else 0.0
        f1 = 2 * precision * sensitivity / (precision + sensitivity) if precision + sensitivity else 0.0
        accuracy = (tp + tn) / count
        ece = self._expected_calibration_error(predictions)
        false_merge_rate = fp / (fp + tn) if fp + tn else 0.0
        review_fraction = review_count / count
        return BenchmarkMetrics(
            count, tp, tn, fp, fn, sensitivity, specificity, precision, f1, accuracy,
            brier / count, ece, false_merge_rate, review_fraction,
            auto_merge_count, review_count, keep_count
        )


    @staticmethod
    def _expected_calibration_error(predictions: list[tuple[float, float]], bins: int = 10) -> float:
        if not predictions:
            return 0.0
        total = len(predictions)
        ece = 0.0
        for k in range(bins):
            lo, hi = k / bins, (k + 1) / bins
            bucket = [(p, y) for p, y in predictions if (lo <= p < hi) or (k == bins - 1 and p == 1.0)]
            if not bucket:
                continue
            confidence = sum(p for p, _ in bucket) / len(bucket)
            observed = sum(y for _, y in bucket) / len(bucket)
            ece += (len(bucket) / total) * abs(confidence - observed)
        return ece

    def optimize_threshold(self, records: list[EvidenceRecord], labels: Iterable[LabeledPair], *, minimum_precision: float = 0.995, step: float = 0.005) -> ThresholdResult:
        labels = list(labels)
        if not labels:
            raise ValueError("labels must not be empty")
        if not 0 < minimum_precision <= 1:
            raise ValueError("minimum_precision must be in (0, 1]")
        if not 0 < step <= 0.1:
            raise ValueError("step must be in (0, 0.1]")

        probs: list[tuple[float, bool]] = []
        for item in labels:
            a = self.engine.assess_pair(records[item.left_index], records[item.right_index], item.left_index, item.right_index)
            probs.append((a.probability, bool(item.is_duplicate)))

        best: ThresholdResult | None = None
        t = 0.0
        while t <= 1.0000001:
            tp = fp = fn = 0
            for p, truth in probs:
                pred = p >= t
                if pred and truth:
                    tp += 1
                elif pred and not truth:
                    fp += 1
                elif not pred and truth:
                    fn += 1
            precision = tp / (tp + fp) if tp + fp else 1.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            candidate = ThresholdResult(round(t, 6), precision, recall, f1, fp, fn)
            if precision >= minimum_precision and (best is None or (candidate.recall, candidate.f1, candidate.threshold) > (best.recall, best.f1, best.threshold)):
                best = candidate
            t += step

        if best is None:
            raise RuntimeError("no threshold satisfies minimum_precision")
        return best
