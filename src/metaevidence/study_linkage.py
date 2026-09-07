from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha1
import csv
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

from .dedup import ConfidenceDeduplicationEngine, DeduplicationDecision
from .models import EvidenceRecord


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _tokens(value: str | None) -> set[str]:
    stop = {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on",
        "or", "the", "to", "with", "without", "study", "trial", "analysis",
    }
    return {t for t in _norm_text(value).split() if len(t) > 2 and t not in stop}


def _jaccard(a: set[str], b: set[str]) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def _seq_similarity(a: str | None, b: str | None) -> float | None:
    # Token Jaccard is deliberately used here rather than character-edit distance:
    # study reports often have legitimately different titles.
    return _jaccard(_tokens(a), _tokens(b))


def _author_keys(record: EvidenceRecord) -> set[str]:
    out: set[str] = set()
    for author in record.authors:
        toks = re.findall(r"[A-Za-zÀ-ÿ0-9]+", author.lower())
        names = [t for t in toks if len(t) > 1]
        if names:
            out.add(max(names, key=len))
        elif toks:
            out.add(toks[0])
    return out


def _author_similarity(a: EvidenceRecord, b: EvidenceRecord) -> float | None:
    return _jaccard(_author_keys(a), _author_keys(b))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _flatten(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        out: list[str] = []
        for v in value.values():
            out.extend(_flatten(v))
        return out
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for v in value:
            out.extend(_flatten(v))
        return out
    return [str(value)]


_REGISTRY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("NCT", re.compile(r"\bNCT\s*[-:]?\s*(\d{8})\b", re.I)),
    ("ISRCTN", re.compile(r"\bISRCTN\s*[-:]?\s*(\d{8})\b", re.I)),
    ("ACTRN", re.compile(r"\bACTRN\s*[-:]?\s*(\d{14})\b", re.I)),
    ("DRKS", re.compile(r"\bDRKS\s*[-:]?\s*(\d{8})\b", re.I)),
    ("CHICTR", re.compile(r"\bChiCTR\s*[-:]?\s*([A-Za-z0-9]{8,18})\b", re.I)),
    ("UMIN", re.compile(r"\b(?:JPRN[-:]?)?UMIN\s*[-:]?\s*(\d{9})\b", re.I)),
    ("TCTR", re.compile(r"\bTCTR\s*[-:]?\s*(\d{11})\b", re.I)),
    ("IRCT", re.compile(r"\bIRCT\s*[-:]?\s*([A-Za-z0-9-]{8,32})\b", re.I)),
    ("NTR", re.compile(r"\bNTR\s*[-:]?\s*(\d{3,8})\b", re.I)),
    ("CTRI", re.compile(r"\bCTRI\s*/\s*(\d{4})\s*/\s*(\d{2})\s*/\s*(\d{3,8})\b", re.I)),
    ("EUCTR", re.compile(r"\b(?:EUCTR|EudraCT)\s*[:#-]?\s*(\d{4}-\d{6}-\d{2})\b", re.I)),
)


_METADATA_REGISTRY_KEYS = {
    "registry_ids", "registry_id", "trial_registry", "trial_registration",
    "trial_registration_number", "clinical_trial_id", "clinicaltrials_gov_id",
    "nct_id", "registration", "registration_number", "trial_id",
}


def extract_registry_ids(record: EvidenceRecord) -> set[str]:
    """Extract normalized trial-registry identifiers from citation-level evidence.

    The function scans title/abstract and registry-oriented metadata fields. It does
    not treat arbitrary numbers as registry identifiers. Full-text can be supplied
    explicitly in ``metadata['full_text']`` but callers should preserve the source
    and section location when using full-text-derived identifiers.
    """

    texts = [record.title, record.abstract or ""]
    for key, value in record.metadata.items():
        lk = str(key).lower()
        if lk in _METADATA_REGISTRY_KEYS or any(tok in lk for tok in ("registry", "registration", "trial_id", "nct")):
            texts.extend(_flatten(value))
    # Opt-in full text / methods extraction when a previous adapter explicitly stores it.
    for key in ("methods_text", "full_text"):
        if key in record.metadata:
            texts.extend(_flatten(record.metadata[key]))

    found: set[str] = set()
    blob = "\n".join(t for t in texts if t)
    for scheme, pattern in _REGISTRY_PATTERNS:
        for match in pattern.finditer(blob):
            groups = match.groups()
            if scheme == "CTRI":
                value = f"{groups[0]}/{groups[1]}/{groups[2]}"
            else:
                value = groups[0]
            found.add(f"{scheme}:{value.upper()}")
    return found


_ACRONYM_STOP = {
    "RCT", "MRI", "CT", "AI", "ML", "COVID", "SARS", "WHO", "CONSORT",
    "PRISMA", "BMI", "DNA", "RNA", "ICU", "ECG", "EEG", "PET", "USA",
}


def extract_study_acronyms(record: EvidenceRecord) -> set[str]:
    values: list[str] = []
    for key in ("study_acronym", "trial_acronym", "acronym"):
        values.extend(_flatten(record.metadata.get(key)))
    title = record.title or ""
    values.extend(re.findall(r"\(([A-Z][A-Z0-9-]{2,11})\)", title))
    values.extend(re.findall(r"\b([A-Z][A-Z0-9-]{2,11})\s+(?:trial|study)\b", title))
    return {
        v.strip().upper() for v in values
        if 3 <= len(v.strip()) <= 12 and v.strip().upper() not in _ACRONYM_STOP
    }


class PublicationRole(str, Enum):
    PROTOCOL = "PROTOCOL"
    PRIMARY_RESULTS = "PRIMARY_RESULTS"
    SECONDARY_ANALYSIS = "SECONDARY_ANALYSIS"
    SUBGROUP_ANALYSIS = "SUBGROUP_ANALYSIS"
    FOLLOW_UP = "FOLLOW_UP"
    CONFERENCE_ABSTRACT = "CONFERENCE_ABSTRACT"
    PREPRINT = "PREPRINT"
    REVIEW = "REVIEW"
    OTHER = "OTHER"


def classify_publication_role(record: EvidenceRecord) -> PublicationRole:
    explicit = str(record.metadata.get("report_role") or "").upper().strip()
    if explicit in PublicationRole.__members__:
        return PublicationRole[explicit]

    text_parts = [record.title]
    for key in ("type", "publication_type", "source_record_type"):
        text_parts.extend(_flatten(record.metadata.get(key)))
    text_parts.extend(_flatten(record.metadata.get("publication_types")))
    text = " ".join(text_parts).lower()

    if "systematic review" in text or "meta-analysis" in text or "meta analysis" in text or "review article" in text:
        return PublicationRole.REVIEW
    if "protocol" in text:
        return PublicationRole.PROTOCOL
    if "subgroup" in text:
        return PublicationRole.SUBGROUP_ANALYSIS
    if "secondary analysis" in text or "secondary outcome" in text or "post hoc" in text or "post-hoc" in text:
        return PublicationRole.SECONDARY_ANALYSIS
    if "follow-up" in text or "follow up" in text or "long-term" in text or "long term" in text:
        return PublicationRole.FOLLOW_UP
    if "conference" in text or "meeting abstract" in text or "proceedings" in text:
        return PublicationRole.CONFERENCE_ABSTRACT
    if "preprint" in text or "posted-content" in text or "posted content" in text:
        return PublicationRole.PREPRINT
    if "randomized controlled trial" in text or "randomised controlled trial" in text or "clinical trial" in text:
        return PublicationRole.PRIMARY_RESULTS
    return PublicationRole.OTHER


def _metadata_tokens(record: EvidenceRecord, keys: Iterable[str]) -> set[str]:
    vals: list[str] = []
    for key in keys:
        vals.extend(_flatten(record.metadata.get(key)))
    return _tokens(" ".join(vals))


def _metadata_similarity(a: EvidenceRecord, b: EvidenceRecord, keys: Iterable[str]) -> float | None:
    return _jaccard(_metadata_tokens(a, keys), _metadata_tokens(b, keys))


def _sample_size(record: EvidenceRecord) -> int | None:
    for key in ("sample_size", "enrollment", "enrolment", "enrollment_count", "n_participants", "participants"):
        value = record.metadata.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
        m = re.search(r"\b(\d{1,8})\b", str(value).replace(",", ""))
        if m:
            return int(m.group(1))
    return None


def _sample_size_similarity(a: EvidenceRecord, b: EvidenceRecord) -> float | None:
    aa, bb = _sample_size(a), _sample_size(b)
    if not aa or not bb:
        return None
    ratio = min(aa, bb) / max(aa, bb)
    if ratio >= 0.95:
        return 1.0
    if ratio >= 0.80:
        return 0.8
    if ratio >= 0.60:
        return 0.5
    if ratio >= 0.35:
        return 0.2
    return 0.0


def _extract_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and 1800 <= value <= 2200:
        return value
    m = re.search(r"\b(19|20|21)\d{2}\b", str(value))
    return int(m.group(0)) if m else None


def _recruitment_interval(record: EvidenceRecord) -> tuple[int, int] | None:
    starts = ["recruitment_start", "start_date", "study_start", "enrollment_start"]
    ends = ["recruitment_end", "completion_date", "study_end", "enrollment_end"]
    start = next((_extract_year(record.metadata.get(k)) for k in starts if _extract_year(record.metadata.get(k))), None)
    end = next((_extract_year(record.metadata.get(k)) for k in ends if _extract_year(record.metadata.get(k))), None)
    if start is None and end is None:
        return None
    if start is None:
        start = end
    if end is None:
        end = start
    assert start is not None and end is not None
    if end < start:
        start, end = end, start
    return start, end


def _recruitment_similarity(a: EvidenceRecord, b: EvidenceRecord) -> float | None:
    ia, ib = _recruitment_interval(a), _recruitment_interval(b)
    if not ia or not ib:
        return None
    a0, a1 = ia
    b0, b1 = ib
    if max(a0, b0) <= min(a1, b1):
        return 1.0
    gap = max(b0 - a1, a0 - b1)
    if gap <= 1:
        return 0.6
    if gap <= 3:
        return 0.2
    return 0.0


def _publication_year_compatibility(a: EvidenceRecord, b: EvidenceRecord) -> float | None:
    if a.year is None or b.year is None:
        return None
    d = abs(a.year - b.year)
    if d <= 1:
        return 1.0
    if d <= 3:
        return 0.8
    if d <= 7:
        return 0.55
    if d <= 15:
        return 0.25
    return 0.0


def _role_complementarity(a: PublicationRole, b: PublicationRole) -> float:
    if a == b:
        return 0.0
    complementary = {
        frozenset((PublicationRole.PROTOCOL, PublicationRole.PRIMARY_RESULTS)),
        frozenset((PublicationRole.PROTOCOL, PublicationRole.FOLLOW_UP)),
        frozenset((PublicationRole.CONFERENCE_ABSTRACT, PublicationRole.PRIMARY_RESULTS)),
        frozenset((PublicationRole.PREPRINT, PublicationRole.PRIMARY_RESULTS)),
        frozenset((PublicationRole.PRIMARY_RESULTS, PublicationRole.SECONDARY_ANALYSIS)),
        frozenset((PublicationRole.PRIMARY_RESULTS, PublicationRole.SUBGROUP_ANALYSIS)),
        frozenset((PublicationRole.PRIMARY_RESULTS, PublicationRole.FOLLOW_UP)),
    }
    return 1.0 if frozenset((a, b)) in complementary else 0.25


class StudyLinkDecision(str, Enum):
    SAME_STUDY = "SAME_STUDY"
    REVIEW = "REVIEW"
    DIFFERENT_STUDY = "DIFFERENT_STUDY"
    DUPLICATE_PUBLICATION = "DUPLICATE_PUBLICATION"


@dataclass(slots=True)
class StudyLinkFeatures:
    registry_exact: float = 0.0
    registry_conflict: float = 0.0
    multi_registry_ambiguous: float = 0.0
    acronym_exact: float = 0.0
    title_similarity: float | None = None
    author_similarity: float | None = None
    year_compatibility: float | None = None
    sample_size_similarity: float | None = None
    country_similarity: float | None = None
    intervention_similarity: float | None = None
    population_similarity: float | None = None
    recruitment_similarity: float | None = None
    role_complementarity: float = 0.0
    review_record: float = 0.0

    def to_dict(self) -> dict[str, float | None]:
        return {
            "registry_exact": self.registry_exact,
            "registry_conflict": self.registry_conflict,
            "multi_registry_ambiguous": self.multi_registry_ambiguous,
            "acronym_exact": self.acronym_exact,
            "title_similarity": self.title_similarity,
            "author_similarity": self.author_similarity,
            "year_compatibility": self.year_compatibility,
            "sample_size_similarity": self.sample_size_similarity,
            "country_similarity": self.country_similarity,
            "intervention_similarity": self.intervention_similarity,
            "population_similarity": self.population_similarity,
            "recruitment_similarity": self.recruitment_similarity,
            "role_complementarity": self.role_complementarity,
            "review_record": self.review_record,
        }


@dataclass(slots=True)
class StudyEvidenceContribution:
    feature: str
    value: float
    weight: float
    contribution: float
    note: str | None = None


@dataclass(slots=True)
class StudyLinkAssessment:
    left_index: int
    right_index: int
    study_probability: float
    publication_probability: float
    decision: StudyLinkDecision
    features: StudyLinkFeatures
    left_registry_ids: set[str] = field(default_factory=set)
    right_registry_ids: set[str] = field(default_factory=set)
    left_role: PublicationRole = PublicationRole.OTHER
    right_role: PublicationRole = PublicationRole.OTHER
    contributions: list[StudyEvidenceContribution] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    calibrated: bool = False

    @property
    def explanation(self) -> list[str]:
        lines = list(self.rules)
        ranked = sorted(self.contributions, key=lambda x: abs(x.contribution), reverse=True)
        for item in ranked[:8]:
            sign = "+" if item.contribution >= 0 else ""
            lines.append(
                f"{item.feature}: value={item.value:.3f}, weight={item.weight:.2f}, "
                f"contribution={sign}{item.contribution:.3f}"
            )
        return lines


@dataclass(slots=True)
class StudyFamily:
    study_id: str
    member_indices: list[int]
    registry_ids: list[str]
    publication_roles: dict[int, str]
    sources: list[str]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "member_indices": list(self.member_indices),
            "registry_ids": list(self.registry_ids),
            "publication_roles": dict(self.publication_roles),
            "sources": list(self.sources),
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class DoubleCountingRisk:
    study_id: str
    member_indices: list[int]
    severity: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "member_indices": list(self.member_indices),
            "severity": self.severity,
            "reason": self.reason,
        }


@dataclass(slots=True)
class StudyLinkageStats:
    input_records: int
    candidate_pairs: int
    assessed_pairs: int
    same_study_pairs: int
    duplicate_publication_pairs: int
    review_pairs: int
    families: int
    singleton_families: int
    used_exhaustive_pairing: bool


@dataclass(slots=True)
class StudyLinkageResult:
    families: list[StudyFamily]
    assessments: list[StudyLinkAssessment]
    review_queue: list[StudyLinkAssessment]
    duplicate_publication_pairs: list[StudyLinkAssessment]
    double_counting_risks: list[DoubleCountingRisk]
    stats: StudyLinkageStats

    def family_for_record(self, index: int) -> StudyFamily | None:
        for family in self.families:
            if index in family.member_indices:
                return family
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "families": [f.to_dict() for f in self.families],
            "review_queue": [self._assessment_row(a) for a in self.review_queue],
            "duplicate_publication_pairs": [self._assessment_row(a) for a in self.duplicate_publication_pairs],
            "double_counting_risks": [r.to_dict() for r in self.double_counting_risks],
            "stats": {
                "input_records": self.stats.input_records,
                "candidate_pairs": self.stats.candidate_pairs,
                "assessed_pairs": self.stats.assessed_pairs,
                "same_study_pairs": self.stats.same_study_pairs,
                "duplicate_publication_pairs": self.stats.duplicate_publication_pairs,
                "review_pairs": self.stats.review_pairs,
                "families": self.stats.families,
                "singleton_families": self.stats.singleton_families,
                "used_exhaustive_pairing": self.stats.used_exhaustive_pairing,
            },
        }

    @staticmethod
    def _assessment_row(a: StudyLinkAssessment) -> dict[str, Any]:
        return {
            "left_index": a.left_index,
            "right_index": a.right_index,
            "study_probability": a.study_probability,
            "publication_probability": a.publication_probability,
            "decision": a.decision.value,
            "left_registry_ids": sorted(a.left_registry_ids),
            "right_registry_ids": sorted(a.right_registry_ids),
            "left_role": a.left_role.value,
            "right_role": a.right_role.value,
            "rules": list(a.rules),
        }

    def write_json(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    def write_families_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "study_id", "member_indices", "registry_ids", "publication_roles", "sources", "confidence"
            ])
            writer.writeheader()
            for family in self.families:
                writer.writerow({
                    "study_id": family.study_id,
                    "member_indices": ";".join(map(str, family.member_indices)),
                    "registry_ids": ";".join(family.registry_ids),
                    "publication_roles": ";".join(f"{i}:{r}" for i, r in sorted(family.publication_roles.items())),
                    "sources": ";".join(family.sources),
                    "confidence": f"{family.confidence:.6f}",
                })
        return out

    def write_review_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "left_index", "right_index", "study_probability", "publication_probability", "decision",
            "left_registry_ids", "right_registry_ids", "left_role", "right_role", "rules"
        ]
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for assessment in self.review_queue:
                row = self._assessment_row(assessment)
                row["left_registry_ids"] = ";".join(row["left_registry_ids"])
                row["right_registry_ids"] = ";".join(row["right_registry_ids"])
                row["rules"] = " | ".join(row["rules"])
                writer.writerow(row)
        return out

    def write_edges_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "left_index", "right_index", "study_probability", "publication_probability", "decision",
            "left_registry_ids", "right_registry_ids", "left_role", "right_role", "rules"
        ]
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for assessment in self.assessments:
                row = self._assessment_row(assessment)
                row["left_registry_ids"] = ";".join(row["left_registry_ids"])
                row["right_registry_ids"] = ";".join(row["right_registry_ids"])
                row["rules"] = " | ".join(row["rules"])
                writer.writerow(row)
        return out

    def write_double_counting_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["study_id", "member_indices", "severity", "reason"])
            writer.writeheader()
            for risk in self.double_counting_risks:
                writer.writerow({
                    "study_id": risk.study_id,
                    "member_indices": ";".join(map(str, risk.member_indices)),
                    "severity": risk.severity,
                    "reason": risk.reason,
                })
        return out


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


class StudyLinkageEngine:
    """Uncertainty-aware linkage of distinct publications to underlying studies.

    This M5 model is deliberately transparent and provisional. Its default score
    is not claimed to be an externally calibrated probability. Registry identifiers
    are treated as the strongest evidence, but review articles are protected from
    automatic linkage because registry IDs may be mentioned rather than reported.

    Publication-level deduplication remains a separate task. If the M4 engine says
    two records are the same publication, this engine returns
    ``DUPLICATE_PUBLICATION`` rather than pretending that they are two study reports.
    """

    DEFAULT_WEIGHTS = {
        "registry_exact": 10.0,
        "registry_conflict": -6.0,
        "multi_registry_ambiguous": -2.5,
        "acronym_exact": 3.0,
        "title_similarity": 1.4,
        "author_similarity": 2.0,
        "year_compatibility": 0.7,
        "sample_size_similarity": 0.9,
        "country_similarity": 0.7,
        "intervention_similarity": 1.1,
        "population_similarity": 0.9,
        "recruitment_similarity": 1.4,
        "role_complementarity": 0.5,
        "review_record": -7.0,
    }

    def __init__(
        self,
        same_study_threshold: float = 0.95,
        review_threshold: float = 0.65,
        exhaustive_limit: int = 1500,
        calibrator: object | None = None,
        weights: dict[str, float] | None = None,
        intercept: float = -5.8,
        publication_engine: ConfidenceDeduplicationEngine | None = None,
    ) -> None:
        if not 0 < review_threshold < same_study_threshold <= 1:
            raise ValueError("Require 0 < review_threshold < same_study_threshold <= 1")
        if exhaustive_limit < 2:
            raise ValueError("exhaustive_limit must be >= 2")
        self.same_study_threshold = same_study_threshold
        self.review_threshold = review_threshold
        self.exhaustive_limit = exhaustive_limit
        self.calibrator = calibrator
        self.weights = dict(self.DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        self.intercept = intercept
        self.publication_engine = publication_engine or ConfidenceDeduplicationEngine()

    def assess_pair(
        self,
        a: EvidenceRecord,
        b: EvidenceRecord,
        left_index: int = 0,
        right_index: int = 1,
    ) -> StudyLinkAssessment:
        publication = self.publication_engine.assess_pair(a, b, left_index, right_index)
        registry_a, registry_b = extract_registry_ids(a), extract_registry_ids(b)
        role_a, role_b = classify_publication_role(a), classify_publication_role(b)
        features = self._features(a, b, registry_a, registry_b, role_a, role_b)
        probability, contributions = self._weighted_probability(features)
        rules: list[str] = []

        if publication.decision is DeduplicationDecision.AUTO_MERGE:
            return StudyLinkAssessment(
                left_index, right_index, 1.0, publication.probability,
                StudyLinkDecision.DUPLICATE_PUBLICATION, features,
                registry_a, registry_b, role_a, role_b, contributions,
                ["M4 classified the pair as the same publication; deduplicate before study-family linkage"],
                publication.calibrated,
            )

        common_registry = registry_a & registry_b
        registry_conflict = bool(registry_a and registry_b and not common_registry)

        if common_registry:
            probability = max(probability, 0.998)
            rules.append(f"Shared trial-registry identifier(s): {', '.join(sorted(common_registry))}")

        multi_registry_ambiguous = bool(
            common_registry and (len(registry_a) > 1 or len(registry_b) > 1) and registry_a != registry_b
        )
        if multi_registry_ambiguous:
            probability = min(probability, 0.90)
            rules.append(
                "Multiple non-identical registry IDs detected: shared-ID evidence requires human review to avoid multi-trial bridging"
            )

        # A review may legitimately mention registry IDs without being a report of that trial.
        if role_a is PublicationRole.REVIEW or role_b is PublicationRole.REVIEW:
            probability = min(probability, 0.60)
            rules.append("Review/meta-analysis safeguard: registry mention alone cannot create a study-family link")

        # Disjoint registry IDs are strong contradictory evidence, but not made fully
        # deterministic because the same trial can be cross-registered in >1 registry.
        if registry_conflict:
            raw = probability
            probability = min(probability, 0.74)
            rules.append("Disjoint registry identifiers: automatic SAME_STUDY decision blocked")
            if raw >= self.review_threshold:
                probability = max(probability, self.review_threshold)

        # Identical acronyms are useful only as corroborating evidence.
        acronyms = extract_study_acronyms(a) & extract_study_acronyms(b)
        if acronyms:
            rules.append(f"Shared study acronym(s): {', '.join(sorted(acronyms))}")

        calibrated = False
        if self.calibrator is not None and not common_registry:
            predict = getattr(self.calibrator, "predict", None)
            if predict is None:
                raise TypeError("calibrator must expose predict(probability)")
            probability = min(1.0, max(0.0, float(predict(probability))))
            calibrated = True
            rules.append("Study-link probability adjusted by fitted calibrator")

        # Re-apply safety rules after calibration.
        if role_a is PublicationRole.REVIEW or role_b is PublicationRole.REVIEW:
            probability = min(probability, 0.60)
        if registry_conflict:
            probability = min(probability, 0.74)
        if multi_registry_ambiguous:
            probability = min(probability, 0.90)
        if common_registry and not multi_registry_ambiguous and role_a is not PublicationRole.REVIEW and role_b is not PublicationRole.REVIEW:
            probability = max(probability, 0.998)

        if probability >= self.same_study_threshold and not registry_conflict and not multi_registry_ambiguous:
            decision = StudyLinkDecision.SAME_STUDY
        elif probability >= self.review_threshold:
            decision = StudyLinkDecision.REVIEW
        else:
            decision = StudyLinkDecision.DIFFERENT_STUDY

        return StudyLinkAssessment(
            left_index, right_index, probability, publication.probability, decision,
            features, registry_a, registry_b, role_a, role_b,
            contributions, rules, calibrated,
        )

    def link(self, records: list[EvidenceRecord]) -> StudyLinkageResult:
        n = len(records)
        pairs, exhaustive = self._candidate_pairs(records)
        assessments: list[StudyLinkAssessment] = []
        review_queue: list[StudyLinkAssessment] = []
        duplicate_pairs: list[StudyLinkAssessment] = []
        uf = _UnionFind(n)
        accepted_edges: dict[tuple[int, int], float] = {}
        cluster_registry: dict[int, set[str]] = {i: set(extract_registry_ids(records[i])) for i in range(n)}

        for i, j in sorted(pairs):
            assessment = self.assess_pair(records[i], records[j], i, j)
            assessments.append(assessment)
            if assessment.decision is StudyLinkDecision.SAME_STUDY:
                ri, rj = uf.find(i), uf.find(j)
                ids_i = cluster_registry.get(ri, set())
                ids_j = cluster_registry.get(rj, set())
                # Prevent transitive A-B-C bridges from silently combining two
                # incompatible registered trials through an unregistered report.
                if ri != rj and ids_i and ids_j and not (ids_i & ids_j):
                    assessment.decision = StudyLinkDecision.REVIEW
                    assessment.study_probability = min(assessment.study_probability, 0.90)
                    assessment.rules.append(
                        "Cluster-consistency safeguard: candidate merge would combine disjoint registry-ID families"
                    )
                    review_queue.append(assessment)
                    continue
                uf.union(i, j)
                root = uf.find(i)
                combined = set(ids_i) | set(ids_j)
                cluster_registry[root] = combined
                if ri != root:
                    cluster_registry.pop(ri, None)
                if rj != root:
                    cluster_registry.pop(rj, None)
                accepted_edges[(i, j)] = assessment.study_probability
            elif assessment.decision is StudyLinkDecision.DUPLICATE_PUBLICATION:
                # Same publication necessarily refers to the same underlying study,
                # but it is reported separately so M4 can be applied first.
                ri, rj = uf.find(i), uf.find(j)
                ids_i = cluster_registry.get(ri, set())
                ids_j = cluster_registry.get(rj, set())
                uf.union(i, j)
                root = uf.find(i)
                cluster_registry[root] = set(ids_i) | set(ids_j)
                if ri != root:
                    cluster_registry.pop(ri, None)
                if rj != root:
                    cluster_registry.pop(rj, None)
                duplicate_pairs.append(assessment)
                accepted_edges[(i, j)] = 1.0
            elif assessment.decision is StudyLinkDecision.REVIEW:
                review_queue.append(assessment)

        clusters: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            clusters[uf.find(i)].append(i)

        families: list[StudyFamily] = []
        for members in sorted(clusters.values(), key=lambda xs: min(xs) if xs else -1):
            member_set = set(members)
            registry_ids = sorted(set().union(*(extract_registry_ids(records[i]) for i in members))) if members else []
            roles = {i: classify_publication_role(records[i]).value for i in members}
            sources = sorted(set().union(*(set(records[i].sources) for i in members))) if members else []
            edge_scores = [
                score for (i, j), score in accepted_edges.items()
                if i in member_set and j in member_set
            ]
            confidence = min(edge_scores) if edge_scores else 1.0
            families.append(
                StudyFamily(
                    study_id=self._stable_family_id(records, members, registry_ids),
                    member_indices=sorted(members),
                    registry_ids=registry_ids,
                    publication_roles=roles,
                    sources=sources,
                    confidence=confidence,
                )
            )

        double_counting_risks = self._double_counting_risks(families)

        stats = StudyLinkageStats(
            input_records=n,
            candidate_pairs=len(pairs),
            assessed_pairs=len(assessments),
            same_study_pairs=sum(a.decision is StudyLinkDecision.SAME_STUDY for a in assessments),
            duplicate_publication_pairs=len(duplicate_pairs),
            review_pairs=len(review_queue),
            families=len(families),
            singleton_families=sum(len(f.member_indices) == 1 for f in families),
            used_exhaustive_pairing=exhaustive,
        )
        return StudyLinkageResult(families, assessments, review_queue, duplicate_pairs, double_counting_risks, stats)

    def _features(
        self,
        a: EvidenceRecord,
        b: EvidenceRecord,
        registry_a: set[str],
        registry_b: set[str],
        role_a: PublicationRole,
        role_b: PublicationRole,
    ) -> StudyLinkFeatures:
        common_registry = registry_a & registry_b
        conflict = bool(registry_a and registry_b and not common_registry)
        common_acronym = extract_study_acronyms(a) & extract_study_acronyms(b)
        return StudyLinkFeatures(
            registry_exact=1.0 if common_registry else 0.0,
            registry_conflict=1.0 if conflict else 0.0,
            multi_registry_ambiguous=1.0 if (common_registry and (len(registry_a) > 1 or len(registry_b) > 1) and registry_a != registry_b) else 0.0,
            acronym_exact=1.0 if common_acronym else 0.0,
            title_similarity=_seq_similarity(a.title, b.title),
            author_similarity=_author_similarity(a, b),
            year_compatibility=_publication_year_compatibility(a, b),
            sample_size_similarity=_sample_size_similarity(a, b),
            country_similarity=_metadata_similarity(a, b, ("country", "countries", "study_country", "sites")),
            intervention_similarity=_metadata_similarity(a, b, ("intervention", "interventions", "treatment", "exposure")),
            population_similarity=_metadata_similarity(a, b, ("population", "condition", "conditions", "disease", "participants_description")),
            recruitment_similarity=_recruitment_similarity(a, b),
            role_complementarity=_role_complementarity(role_a, role_b),
            review_record=1.0 if role_a is PublicationRole.REVIEW or role_b is PublicationRole.REVIEW else 0.0,
        )

    def _weighted_probability(self, features: StudyLinkFeatures) -> tuple[float, list[StudyEvidenceContribution]]:
        logit = self.intercept
        contributions: list[StudyEvidenceContribution] = []
        for name, value in features.to_dict().items():
            if value is None:
                continue
            weight = self.weights.get(name, 0.0)
            contribution = weight * float(value)
            logit += contribution
            if float(value) != 0.0:
                contributions.append(StudyEvidenceContribution(name, float(value), weight, contribution))
        return _sigmoid(logit), contributions

    def candidate_pairs(self, records: list[EvidenceRecord]) -> tuple[set[tuple[int, int]], bool]:
        """Return candidate pairs and whether exhaustive all-pairs comparison was used.

        Exposed for benchmarking blocking recall and computational reduction. Callers
        should not interpret absence from a blocked candidate set as proof that two
        records are different.
        """
        return self._candidate_pairs(records)

    def _candidate_pairs(self, records: list[EvidenceRecord]) -> tuple[set[tuple[int, int]], bool]:
        n = len(records)
        if n <= self.exhaustive_limit:
            return {(i, j) for i in range(n) for j in range(i + 1, n)}, True

        blocks: dict[str, list[int]] = defaultdict(list)
        for i, record in enumerate(records):
            for rid in extract_registry_ids(record):
                blocks[f"registry:{rid}"].append(i)
            for acronym in extract_study_acronyms(record):
                blocks[f"acronym:{acronym}"].append(i)
            authors = sorted(_author_keys(record))[:2]
            if authors:
                # Broad year bands preserve long-term follow-up candidates while
                # avoiding one huge author-only block.
                band = (record.year or 0) // 5
                for author in authors:
                    for delta in (-1, 0, 1):
                        blocks[f"author:{author}:{band + delta}"].append(i)
            title_tokens = sorted(_tokens(record.title))[:3]
            for token in title_tokens:
                blocks[f"title:{token}"].append(i)

        pairs: set[tuple[int, int]] = set()
        for members in blocks.values():
            unique = sorted(set(members))
            # Protect against pathological generic blocks.
            if len(unique) > 500:
                continue
            for pos, i in enumerate(unique):
                for j in unique[pos + 1:]:
                    pairs.add((i, j))
        return pairs, False

    @staticmethod
    def _double_counting_risks(families: list[StudyFamily]) -> list[DoubleCountingRisk]:
        outcome_roles = {
            PublicationRole.PRIMARY_RESULTS.value,
            PublicationRole.SECONDARY_ANALYSIS.value,
            PublicationRole.SUBGROUP_ANALYSIS.value,
            PublicationRole.FOLLOW_UP.value,
            PublicationRole.CONFERENCE_ABSTRACT.value,
            PublicationRole.PREPRINT.value,
        }
        risks: list[DoubleCountingRisk] = []
        for family in families:
            outcome_members = [i for i, role in family.publication_roles.items() if role in outcome_roles]
            if len(outcome_members) >= 2:
                risks.append(DoubleCountingRisk(
                    study_id=family.study_id,
                    member_indices=sorted(outcome_members),
                    severity="HIGH",
                    reason=(
                        "Multiple distinct outcome-bearing reports are linked to one underlying study; "
                        "do not count them as independent studies without outcome/timepoint/report adjudication."
                    ),
                ))
            elif len(family.member_indices) >= 2:
                risks.append(DoubleCountingRisk(
                    study_id=family.study_id,
                    member_indices=sorted(family.member_indices),
                    severity="REVIEW",
                    reason=(
                        "Multiple reports are linked to one study family; verify which report supplies each meta-analysis datum."
                    ),
                ))
        return risks

    @staticmethod
    def _stable_family_id(records: list[EvidenceRecord], members: list[int], registry_ids: list[str]) -> str:
        if registry_ids:
            seed = "registry|" + "|".join(registry_ids)
        else:
            fingerprints: list[str] = []
            for i in members:
                r = records[i]
                fingerprints.append(
                    "|".join([
                        r.doi or "",
                        _norm_text(r.title),
                        str(r.year or ""),
                        ",".join(sorted(_author_keys(r))),
                    ])
                )
            seed = "reports|" + "||".join(sorted(fingerprints))
        return "STUDY-" + sha1(seed.encode("utf-8")).hexdigest()[:12].upper()
