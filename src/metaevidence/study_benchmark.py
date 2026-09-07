from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import EvidenceRecord
from .study_linkage import StudyLinkDecision, StudyLinkageEngine


@dataclass(slots=True, frozen=True)
class StudyLabeledPair:
    left_index: int
    right_index: int
    same_study: bool


@dataclass(slots=True)
class StudyLinkageMetrics:
    count: int
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
    false_link_rate: float
    review_fraction: float


@dataclass(slots=True)
class StudyThresholdResult:
    threshold: float
    precision: float
    recall: float
    f1: float
    false_positive: int
    false_negative: int


class StudyLinkageBenchmark:
    """Evaluation helpers for independently labelled report-to-study pairs."""

    def __init__(self, engine: StudyLinkageEngine | None = None) -> None:
        self.engine = engine or StudyLinkageEngine()

    def evaluate(
        self,
        records: list[EvidenceRecord],
        labels: Iterable[StudyLabeledPair],
        *,
        threshold: float | None = None,
    ) -> StudyLinkageMetrics:
        threshold = self.engine.same_study_threshold if threshold is None else threshold
        tp = tn = fp = fn = review = count = 0
        brier = 0.0
        for item in labels:
            a = self.engine.assess_pair(
                records[item.left_index], records[item.right_index],
                item.left_index, item.right_index,
            )
            # Duplicate publications are positive for underlying-study identity,
            # although benchmark datasets should generally be deduplicated first.
            pred = a.study_probability >= threshold or a.decision is StudyLinkDecision.DUPLICATE_PUBLICATION
            truth = bool(item.same_study)
            if pred and truth:
                tp += 1
            elif pred and not truth:
                fp += 1
            elif not pred and truth:
                fn += 1
            else:
                tn += 1
            if a.decision is StudyLinkDecision.REVIEW:
                review += 1
            y = 1.0 if truth else 0.0
            brier += (a.study_probability - y) ** 2
            count += 1
        if count == 0:
            raise ValueError("labels must not be empty")
        sensitivity = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        precision = tp / (tp + fp) if tp + fp else 0.0
        f1 = 2 * precision * sensitivity / (precision + sensitivity) if precision + sensitivity else 0.0
        accuracy = (tp + tn) / count
        false_link_rate = fp / (fp + tn) if fp + tn else 0.0
        return StudyLinkageMetrics(
            count, tp, tn, fp, fn, sensitivity, specificity, precision, f1,
            accuracy, brier / count, false_link_rate, review / count,
        )

    def optimize_threshold(
        self,
        records: list[EvidenceRecord],
        labels: Iterable[StudyLabeledPair],
        *,
        minimum_precision: float = 0.995,
        step: float = 0.005,
    ) -> StudyThresholdResult:
        labels = list(labels)
        if not labels:
            raise ValueError("labels must not be empty")
        if not 0 < minimum_precision <= 1:
            raise ValueError("minimum_precision must be in (0, 1]")
        probs: list[tuple[float, bool]] = []
        for item in labels:
            a = self.engine.assess_pair(records[item.left_index], records[item.right_index], item.left_index, item.right_index)
            probs.append((a.study_probability, bool(item.same_study)))

        best: StudyThresholdResult | None = None
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
            candidate = StudyThresholdResult(round(t, 6), precision, recall, f1, fp, fn)
            if precision >= minimum_precision and (
                best is None or (candidate.recall, candidate.f1, candidate.threshold) > (best.recall, best.f1, best.threshold)
            ):
                best = candidate
            t += step
        if best is None:
            raise RuntimeError("no threshold satisfies minimum_precision")
        return best
