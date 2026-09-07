from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import csv
import json
from pathlib import Path
from typing import Iterable
import math
from uuid import uuid4

from .ids import stable_record_id
from .models import EvidenceRecord


class ScreeningStage(str, Enum):
    TITLE_ABSTRACT = "TITLE_ABSTRACT"
    FULL_TEXT = "FULL_TEXT"


class ScreeningDecision(str, Enum):
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"
    MAYBE = "MAYBE"
    NOT_SCREENED = "NOT_SCREENED"


@dataclass(frozen=True, slots=True)
class ExclusionReason:
    code: str
    label: str
    description: str | None = None


DEFAULT_EXCLUSION_REASONS: tuple[ExclusionReason, ...] = (
    ExclusionReason("WRONG_POPULATION", "Wrong population"),
    ExclusionReason("WRONG_INTERVENTION_EXPOSURE", "Wrong intervention/exposure"),
    ExclusionReason("WRONG_COMPARATOR", "Wrong comparator"),
    ExclusionReason("WRONG_OUTCOME", "Wrong outcome"),
    ExclusionReason("WRONG_STUDY_DESIGN", "Wrong study design"),
    ExclusionReason("NOT_PRIMARY_RESEARCH", "Not primary research"),
    ExclusionReason("NOT_RETRIEVABLE", "Full text not retrievable"),
    ExclusionReason("OTHER", "Other"),
)


class ReasonCodebook:
    def __init__(self, reasons: Iterable[ExclusionReason] = DEFAULT_EXCLUSION_REASONS) -> None:
        self._items = {x.code.upper(): x for x in reasons}

    def add(self, reason: ExclusionReason) -> None:
        self._items[reason.code.upper()] = reason

    def get(self, code: str | None) -> ExclusionReason | None:
        return self._items.get((code or "").upper())

    def validate(self, code: str | None) -> bool:
        return code is None or self.get(code) is not None

    def to_dict(self) -> dict[str, dict[str, str | None]]:
        return {k: asdict(v) for k, v in sorted(self._items.items())}


@dataclass(slots=True)
class ScreeningEvent:
    record_id: str
    stage: ScreeningStage
    decision: ScreeningDecision
    reviewer: str
    timestamp: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    reason_code: str | None = None
    reason_text: str | None = None
    note: str | None = None
    adjudication: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["stage"] = self.stage.value
        d["decision"] = self.decision.value
        return d


@dataclass(slots=True)
class ScreeningConflict:
    record_id: str
    stage: ScreeningStage
    reviewer_decisions: dict[str, ScreeningDecision]


@dataclass(slots=True)
class ReviewerAgreement:
    reviewer_a: str
    reviewer_b: str
    stage: ScreeningStage
    n_double_screened: int
    agreements: int
    percent_agreement: float | None
    cohens_kappa: float | None


class ScreeningLedger:
    """Append-only screening audit trail with reviewer-level decisions.

    The ledger deliberately keeps ``MAYBE`` distinct from unscreened records and
    never silently coerces it to a binary label.  Full-text exclusions require a
    reason by default because those reasons are needed for transparent review
    reporting.
    """

    def __init__(
        self,
        events: Iterable[ScreeningEvent] | None = None,
        *,
        codebook: ReasonCodebook | None = None,
        require_full_text_exclusion_reason: bool = True,
    ) -> None:
        self.events = list(events or [])
        self.codebook = codebook or ReasonCodebook()
        self.require_full_text_exclusion_reason = require_full_text_exclusion_reason

    @staticmethod
    def _record_id(record_or_id: EvidenceRecord | str) -> str:
        return stable_record_id(record_or_id) if isinstance(record_or_id, EvidenceRecord) else str(record_or_id)

    def add(
        self,
        record_or_id: EvidenceRecord | str,
        decision: ScreeningDecision | str,
        *,
        stage: ScreeningStage | str = ScreeningStage.TITLE_ABSTRACT,
        reviewer: str = "reviewer-1",
        reason_code: str | None = None,
        reason_text: str | None = None,
        note: str | None = None,
        timestamp: str | None = None,
        adjudication: bool = False,
        metadata: dict[str, str] | None = None,
    ) -> ScreeningEvent:
        decision = ScreeningDecision(decision)
        stage = ScreeningStage(stage)
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer must be non-empty")
        if reason_code and not self.codebook.validate(reason_code):
            raise ValueError(f"Unknown exclusion reason code: {reason_code}")
        if decision is not ScreeningDecision.EXCLUDE and (reason_code or reason_text):
            raise ValueError("Exclusion reasons can only be attached to EXCLUDE decisions")
        if (
            self.require_full_text_exclusion_reason
            and stage is ScreeningStage.FULL_TEXT
            and decision is ScreeningDecision.EXCLUDE
            and not (reason_code or (reason_text or "").strip())
        ):
            raise ValueError("FULL_TEXT exclusions require reason_code or reason_text")

        event = ScreeningEvent(
            record_id=self._record_id(record_or_id),
            stage=stage,
            decision=decision,
            reviewer=reviewer,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            reason_code=reason_code.upper() if reason_code else None,
            reason_text=reason_text,
            note=note,
            adjudication=adjudication,
            metadata=dict(metadata or {}),
        )
        self.events.append(event)
        return event

    def adjudicate(
        self,
        record_or_id: EvidenceRecord | str,
        decision: ScreeningDecision | str,
        *,
        stage: ScreeningStage | str,
        reviewer: str = "adjudicator",
        reason_code: str | None = None,
        reason_text: str | None = None,
        note: str | None = None,
        timestamp: str | None = None,
    ) -> ScreeningEvent:
        return self.add(
            record_or_id,
            decision,
            stage=stage,
            reviewer=reviewer,
            reason_code=reason_code,
            reason_text=reason_text,
            note=note,
            timestamp=timestamp,
            adjudication=True,
        )

    def events_for(self, record_or_id: EvidenceRecord | str, stage: ScreeningStage | str | None = None) -> list[ScreeningEvent]:
        rid = self._record_id(record_or_id)
        stage_enum = ScreeningStage(stage) if stage is not None else None
        return [e for e in self.events if e.record_id == rid and (stage_enum is None or e.stage is stage_enum)]

    def _latest_per_reviewer(self, rid: str, stage: ScreeningStage) -> dict[str, ScreeningEvent]:
        """Return the most recently appended decision for each reviewer.

        Append order, not timestamp text, defines revision order. Timestamps are provenance
        and may be imported from different systems, clocks, or time zones; using them as the
        conflict-resolution key can resurrect an older decision when a later audit event carries
        an earlier explicit timestamp.
        """
        latest: dict[str, ScreeningEvent] = {}
        for event in self.events:
            if event.record_id == rid and event.stage is stage and not event.adjudication:
                latest[event.reviewer] = event
        return latest

    def final_event(self, record_or_id: EvidenceRecord | str, stage: ScreeningStage | str) -> ScreeningEvent | None:
        rid = self._record_id(record_or_id)
        stage = ScreeningStage(stage)
        latest = self._latest_per_reviewer(rid, stage)
        reviewer_positions = [
            i for i, e in enumerate(self.events)
            if e.record_id == rid and e.stage is stage and not e.adjudication
        ]
        latest_reviewer_pos = max(reviewer_positions, default=-1)
        adjudications = [
            (i, e) for i, e in enumerate(self.events)
            if e.record_id == rid and e.stage is stage and e.adjudication
            and i >= latest_reviewer_pos
        ]
        if adjudications:
            return adjudications[-1][1]
        if not latest:
            return None
        decisions = {e.decision for e in latest.values()}
        if len(decisions) != 1:
            return None
        # Return the last appended event among the reviewers' current decisions.
        latest_ids = {e.event_id for e in latest.values()}
        for event in reversed(self.events):
            if event.event_id in latest_ids:
                return event
        return None

    def final_decision(self, record_or_id: EvidenceRecord | str, stage: ScreeningStage | str) -> ScreeningDecision:
        event = self.final_event(record_or_id, stage)
        return event.decision if event else ScreeningDecision.NOT_SCREENED

    def conflicts(self) -> list[ScreeningConflict]:
        keys = {(e.record_id, e.stage) for e in self.events}
        out: list[ScreeningConflict] = []
        for rid, stage in sorted(keys, key=lambda x: (x[0], x[1].value)):
            latest = self._latest_per_reviewer(rid, stage)
            if not latest:
                continue
            reviewer_positions = [
                i for i, e in enumerate(self.events)
                if e.record_id == rid and e.stage is stage and not e.adjudication
            ]
            latest_reviewer_pos = max(reviewer_positions, default=-1)
            adjudications = [
                e for i, e in enumerate(self.events)
                if e.record_id == rid and e.stage is stage and e.adjudication
                and i >= latest_reviewer_pos
            ]
            if adjudications:
                continue
            decisions = {e.decision for e in latest.values()}
            if len(decisions) > 1:
                out.append(ScreeningConflict(rid, stage, {r: e.decision for r, e in sorted(latest.items())}))
        return out

    def agreement(
        self, reviewer_a: str, reviewer_b: str, *, stage: ScreeningStage | str = ScreeningStage.TITLE_ABSTRACT
    ) -> ReviewerAgreement:
        """Calculate observed agreement and unweighted Cohen's kappa.

        Only records screened by both named reviewers are included. Adjudication
        events are excluded because this statistic describes the independent
        reviewer decisions rather than the resolved consensus.
        """
        stage = ScreeningStage(stage)
        keys = sorted({e.record_id for e in self.events if e.stage is stage and not e.adjudication})
        pairs: list[tuple[ScreeningDecision, ScreeningDecision]] = []
        for rid in keys:
            latest = self._latest_per_reviewer(rid, stage)
            if reviewer_a in latest and reviewer_b in latest:
                pairs.append((latest[reviewer_a].decision, latest[reviewer_b].decision))
        n = len(pairs)
        if n == 0:
            return ReviewerAgreement(reviewer_a, reviewer_b, stage, 0, 0, None, None)
        agreements = sum(a is b for a, b in pairs)
        observed = agreements / n
        categories = list(ScreeningDecision)
        pa = {c: sum(a is c for a, _ in pairs) / n for c in categories}
        pb = {c: sum(b is c for _, b in pairs) / n for c in categories}
        expected = sum(pa[c] * pb[c] for c in categories)
        if math.isclose(expected, 1.0):
            kappa = 1.0 if math.isclose(observed, 1.0) else None
        else:
            kappa = (observed - expected) / (1.0 - expected)
        return ReviewerAgreement(reviewer_a, reviewer_b, stage, n, agreements, observed, kappa)

    def counts(self, stage: ScreeningStage | str) -> dict[str, int]:
        stage = ScreeningStage(stage)
        record_ids = sorted({e.record_id for e in self.events if e.stage is stage})
        counts = {d.value: 0 for d in ScreeningDecision}
        for rid in record_ids:
            counts[self.final_decision(rid, stage).value] += 1
        return counts

    def asreview_label(self, record_or_id: EvidenceRecord | str) -> int | None:
        # Prefer a resolved full-text decision, then title/abstract.
        full = self.final_decision(record_or_id, ScreeningStage.FULL_TEXT)
        decision = full if full is not ScreeningDecision.NOT_SCREENED else self.final_decision(record_or_id, ScreeningStage.TITLE_ABSTRACT)
        if decision is ScreeningDecision.INCLUDE:
            return 1
        if decision is ScreeningDecision.EXCLUDE:
            return 0
        return None

    def write_jsonl(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for event in self.events:
                fh.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return out

    def write_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "event_id", "record_id", "stage", "decision", "reviewer", "timestamp",
            "reason_code", "reason_text", "note", "adjudication", "metadata",
        ]
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for event in self.events:
                row = event.to_dict()
                row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True)
                writer.writerow(row)
        return out

    @classmethod
    def read_jsonl(cls, path: str | Path, **kwargs: object) -> "ScreeningLedger":
        events: list[ScreeningEvent] = []
        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                row["stage"] = ScreeningStage(row["stage"])
                row["decision"] = ScreeningDecision(row["decision"])
                events.append(ScreeningEvent(**row))
        return cls(events, **kwargs)
