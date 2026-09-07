from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ASySDPerformanceContract:
    """Record-level performance using the published ASySD validation convention.

    The official ASySD validation code treats ``Duplicate`` as the positive class
    and ``Unique`` as the negative class. Sensitivity and specificity are reported
    as percentages. This class reproduces that metric contract only; it does not
    reproduce ASySD's duplicate-detection algorithm or its gold-informed
    representative-retention policy.
    """

    true_negative: int
    true_positive: int
    false_negative: int
    false_positive: int
    sensitivity_percent: float
    specificity_percent: float

    @property
    def sensitivity(self) -> float:
        return self.sensitivity_percent / 100.0

    @property
    def specificity(self) -> float:
        return self.specificity_percent / 100.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def calculate_asysd_performance_contract(
    gold_removed: Sequence[bool],
    predicted_removed: Sequence[bool],
) -> ASySDPerformanceContract:
    """Reproduce the TP/TN/FN/FP equations used by ASySD's validation R code.

    Parameters
    ----------
    gold_removed:
        ``True`` for a citation labelled ``Duplicate`` in the reference set and
        ``False`` for a citation labelled ``Unique``.
    predicted_removed:
        ``True`` when the evaluated workflow removes the citation and ``False``
        when it retains it.
    """
    if len(gold_removed) != len(predicted_removed):
        raise ValueError("gold_removed and predicted_removed must have equal length")

    tp = sum(bool(g) and bool(p) for g, p in zip(gold_removed, predicted_removed))
    tn = sum((not bool(g)) and (not bool(p)) for g, p in zip(gold_removed, predicted_removed))
    fn = sum(bool(g) and (not bool(p)) for g, p in zip(gold_removed, predicted_removed))
    fp = sum((not bool(g)) and bool(p) for g, p in zip(gold_removed, predicted_removed))

    sensitivity = (tp / (tp + fn) * 100.0) if (tp + fn) else 100.0
    specificity = (tn / (tn + fp) * 100.0) if (tn + fp) else 100.0
    return ASySDPerformanceContract(
        true_negative=tn,
        true_positive=tp,
        false_negative=fn,
        false_positive=fp,
        sensitivity_percent=sensitivity,
        specificity_percent=specificity,
    )
