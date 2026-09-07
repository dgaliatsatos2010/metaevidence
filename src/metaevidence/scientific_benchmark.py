from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time
from typing import Callable, Iterable, Sequence

from .benchmark import DeduplicationBenchmark, LabeledPair
from .dedup import ConfidenceDeduplicationEngine
from .models import EvidenceRecord
from .study_benchmark import StudyLabeledPair, StudyLinkageBenchmark
from .study_linkage import StudyLinkageEngine
from .translators import Translation


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


@dataclass(frozen=True, slots=True)
class RetrievalSetMetrics:
    reference_count: int
    candidate_count: int
    intersection_count: int
    precision: float
    recall: float
    f1: float
    jaccard: float
    relative_count_error: float

    @classmethod
    def from_sets(cls, reference_ids: Iterable[str], candidate_ids: Iterable[str]) -> "RetrievalSetMetrics":
        reference = {str(x).strip() for x in reference_ids if str(x).strip()}
        candidate = {str(x).strip() for x in candidate_ids if str(x).strip()}
        inter = reference & candidate
        precision = _safe_div(len(inter), len(candidate))
        recall = _safe_div(len(inter), len(reference))
        f1 = _safe_div(2 * precision * recall, precision + recall)
        union = reference | candidate
        jaccard = _safe_div(len(inter), len(union))
        count_error = _safe_div(abs(len(candidate) - len(reference)), len(reference)) if reference else float(bool(candidate))
        return cls(len(reference), len(candidate), len(inter), precision, recall, f1, jaccard, count_error)


@dataclass(frozen=True, slots=True)
class QueryTranslationBenchmarkCase:
    case_id: str
    source: str
    reference_ids: frozenset[str]
    candidate_ids: frozenset[str]
    canonical_query: str = ""
    expert_query: str | None = None
    generated_query: str | None = None
    fidelity_score: float | None = None
    loss_score: float | None = None
    requires_review: bool | None = None


@dataclass(frozen=True, slots=True)
class QueryTranslationBenchmarkResult:
    case_id: str
    source: str
    metrics: RetrievalSetMetrics
    fidelity_score: float | None
    loss_score: float | None
    requires_review: bool | None
    canonical_query: str
    expert_query: str | None
    generated_query: str | None


class QueryTranslationBenchmark:
    """Evaluate translated searches by retrieval equivalence, not string similarity.

    The reference set should be produced by an expert-reviewed target-database query.
    Candidate IDs should come from the MetaEvidence-generated translation executed in
    the same target database and, ideally, within the same frozen index/date window.
    """

    @staticmethod
    def evaluate(case: QueryTranslationBenchmarkCase) -> QueryTranslationBenchmarkResult:
        metrics = RetrievalSetMetrics.from_sets(case.reference_ids, case.candidate_ids)
        return QueryTranslationBenchmarkResult(
            case.case_id,
            case.source,
            metrics,
            case.fidelity_score,
            case.loss_score,
            case.requires_review,
            case.canonical_query,
            case.expert_query,
            case.generated_query,
        )

    @staticmethod
    def from_translation(
        *,
        case_id: str,
        translation: Translation,
        reference_ids: Iterable[str],
        candidate_ids: Iterable[str],
        expert_query: str | None = None,
    ) -> QueryTranslationBenchmarkResult:
        case = QueryTranslationBenchmarkCase(
            case_id=case_id,
            source=translation.source,
            reference_ids=frozenset(reference_ids),
            candidate_ids=frozenset(candidate_ids),
            canonical_query=translation.original,
            expert_query=expert_query,
            generated_query=translation.translated,
            fidelity_score=translation.fidelity_score,
            loss_score=translation.loss_score,
            requires_review=translation.requires_review,
        )
        return QueryTranslationBenchmark.evaluate(case)


@dataclass(frozen=True, slots=True)
class AblationResult:
    task: str
    ablated_feature: str
    sensitivity: float
    specificity: float
    precision: float
    f1: float
    false_positive_rate: float
    review_fraction: float
    brier_score: float


class DeduplicationAblationBenchmark:
    """One-feature-at-a-time ablation for the M4 transparent scoring model."""

    def __init__(self, engine: ConfidenceDeduplicationEngine | None = None) -> None:
        self.engine = engine or ConfidenceDeduplicationEngine()

    def evaluate(self, records: list[EvidenceRecord], labels: Iterable[LabeledPair], features: Sequence[str] | None = None) -> list[AblationResult]:
        labels = list(labels)
        names = list(features or self.engine.weights.keys())
        out: list[AblationResult] = []
        for name in ["<none>", *names]:
            weights = dict(self.engine.weights)
            if name != "<none>":
                if name not in weights:
                    raise KeyError(f"Unknown deduplication feature: {name}")
                weights[name] = 0.0
            engine = ConfidenceDeduplicationEngine(
                auto_merge_threshold=self.engine.auto_merge_threshold,
                review_threshold=self.engine.review_threshold,
                fuzzy_threshold=self.engine.fuzzy_threshold,
                exhaustive_limit=self.engine.exhaustive_limit,
                weights=weights,
                intercept=self.engine.intercept,
            )
            m = DeduplicationBenchmark(engine).evaluate(records, labels)
            out.append(AblationResult(
                "deduplication", name, m.sensitivity, m.specificity, m.precision, m.f1,
                m.false_merge_rate, m.review_fraction, m.brier_score,
            ))
        return out


class StudyLinkageAblationBenchmark:
    """One-feature-at-a-time ablation for the M5 report-to-study linkage model."""

    def __init__(self, engine: StudyLinkageEngine | None = None) -> None:
        self.engine = engine or StudyLinkageEngine()

    def evaluate(self, records: list[EvidenceRecord], labels: Iterable[StudyLabeledPair], features: Sequence[str] | None = None) -> list[AblationResult]:
        labels = list(labels)
        names = list(features or self.engine.weights.keys())
        out: list[AblationResult] = []
        for name in ["<none>", *names]:
            weights = dict(self.engine.weights)
            if name != "<none>":
                if name not in weights:
                    raise KeyError(f"Unknown study-link feature: {name}")
                weights[name] = 0.0
            engine = StudyLinkageEngine(
                same_study_threshold=self.engine.same_study_threshold,
                review_threshold=self.engine.review_threshold,
                exhaustive_limit=self.engine.exhaustive_limit,
                weights=weights,
                intercept=self.engine.intercept,
                publication_engine=self.engine.publication_engine,
            )
            m = StudyLinkageBenchmark(engine).evaluate(records, labels)
            out.append(AblationResult(
                "study_linkage", name, m.sensitivity, m.specificity, m.precision, m.f1,
                m.false_link_rate, m.review_fraction, m.brier_score,
            ))
        return out


@dataclass(frozen=True, slots=True)
class StressPoint:
    task: str
    missing_rate: float
    replicate: int
    sensitivity: float
    specificity: float
    precision: float
    f1: float
    false_positive_rate: float
    review_fraction: float
    brier_score: float


class MetadataStressBenchmark:
    """Evaluate robustness under controlled metadata missingness.

    Missingness is injected independently per record and selected field. This is a
    sensitivity/stress experiment, not a model of any specific database's missingness.
    """

    DEFAULT_FIELDS = (
        "doi", "pmid", "wos_ut", "scopus_eid", "openalex_id",
        "authors", "year", "journal", "abstract", "volume", "issue", "pages",
    )

    @staticmethod
    def _drop_field(record: EvidenceRecord, field_name: str) -> None:
        if field_name in {"doi", "pmid", "wos_ut", "scopus_eid", "openalex_id", "year", "journal", "abstract"}:
            setattr(record, field_name, None)
        elif field_name == "authors":
            record.authors = []
        elif field_name in {"volume", "issue", "pages"}:
            aliases = {
                "volume": ("volume",),
                "issue": ("issue", "number"),
                "pages": ("pages", "page", "page_range"),
            }
            for key in aliases[field_name]:
                record.metadata.pop(key, None)
        else:
            raise KeyError(f"Unsupported stress-test field: {field_name}")

    @classmethod
    def degrade(cls, records: list[EvidenceRecord], *, missing_rate: float, fields: Sequence[str] | None = None, seed: int = 0) -> list[EvidenceRecord]:
        if not 0 <= missing_rate <= 1:
            raise ValueError("missing_rate must be in [0, 1]")
        fields = tuple(fields or cls.DEFAULT_FIELDS)
        rng = random.Random(seed)
        out = deepcopy(records)
        for record in out:
            for name in fields:
                if rng.random() < missing_rate:
                    cls._drop_field(record, name)
        return out

    @classmethod
    def evaluate_deduplication(
        cls,
        records: list[EvidenceRecord],
        labels: Iterable[LabeledPair],
        *,
        missing_rates: Sequence[float] = (0.0, 0.1, 0.25, 0.5, 0.75),
        repeats: int = 5,
        fields: Sequence[str] | None = None,
        seed: int = 1729,
        engine: ConfidenceDeduplicationEngine | None = None,
    ) -> list[StressPoint]:
        labels = list(labels)
        out: list[StressPoint] = []
        for rate in missing_rates:
            for rep in range(repeats):
                degraded = cls.degrade(records, missing_rate=rate, fields=fields, seed=seed + rep + int(rate * 10000))
                m = DeduplicationBenchmark(engine).evaluate(degraded, labels)
                out.append(StressPoint("deduplication", rate, rep, m.sensitivity, m.specificity, m.precision, m.f1, m.false_merge_rate, m.review_fraction, m.brier_score))
        return out

    @classmethod
    def evaluate_study_linkage(
        cls,
        records: list[EvidenceRecord],
        labels: Iterable[StudyLabeledPair],
        *,
        missing_rates: Sequence[float] = (0.0, 0.1, 0.25, 0.5, 0.75),
        repeats: int = 5,
        fields: Sequence[str] | None = None,
        seed: int = 2718,
        engine: StudyLinkageEngine | None = None,
    ) -> list[StressPoint]:
        labels = list(labels)
        out: list[StressPoint] = []
        for rate in missing_rates:
            for rep in range(repeats):
                degraded = cls.degrade(records, missing_rate=rate, fields=fields, seed=seed + rep + int(rate * 10000))
                m = StudyLinkageBenchmark(engine).evaluate(degraded, labels)
                out.append(StressPoint("study_linkage", rate, rep, m.sensitivity, m.specificity, m.precision, m.f1, m.false_link_rate, m.review_fraction, m.brier_score))
        return out


@dataclass(frozen=True, slots=True)
class ScalabilityPoint:
    task: str
    n_records: int
    replicate: int
    elapsed_seconds: float
    records_per_second: float
    candidate_pairs: int
    assessed_pairs: int
    output_groups: int
    used_exhaustive_pairing: bool


class ScalabilityBenchmark:
    """Wall-clock benchmarking with explicit environment-independent raw timings.

    Results must be reported with CPU/OS/Python metadata because elapsed time is not
    portable across machines. No hidden parallelism is used by this helper.
    """

    @staticmethod
    def deduplication(record_factory: Callable[[int], list[EvidenceRecord]], sizes: Sequence[int], *, repeats: int = 3, engine: ConfidenceDeduplicationEngine | None = None) -> list[ScalabilityPoint]:
        engine = engine or ConfidenceDeduplicationEngine()
        out: list[ScalabilityPoint] = []
        for size in sizes:
            if size < 1:
                raise ValueError("sizes must contain positive integers")
            for rep in range(repeats):
                records = record_factory(size)
                t0 = time.perf_counter()
                result = engine.deduplicate(records)
                elapsed = time.perf_counter() - t0
                stats = result.stats
                assert stats is not None
                out.append(ScalabilityPoint(
                    "deduplication", size, rep, elapsed, _safe_div(size, elapsed),
                    stats.candidate_pairs, stats.assessed_pairs, stats.output_records,
                    stats.used_exhaustive_pairing,
                ))
        return out

    @staticmethod
    def study_linkage(record_factory: Callable[[int], list[EvidenceRecord]], sizes: Sequence[int], *, repeats: int = 3, engine: StudyLinkageEngine | None = None) -> list[ScalabilityPoint]:
        engine = engine or StudyLinkageEngine()
        out: list[ScalabilityPoint] = []
        for size in sizes:
            if size < 1:
                raise ValueError("sizes must contain positive integers")
            for rep in range(repeats):
                records = record_factory(size)
                t0 = time.perf_counter()
                result = engine.link(records)
                elapsed = time.perf_counter() - t0
                stats = result.stats
                out.append(ScalabilityPoint(
                    "study_linkage", size, rep, elapsed, _safe_div(size, elapsed),
                    stats.candidate_pairs, stats.assessed_pairs, stats.families,
                    stats.used_exhaustive_pairing,
                ))
        return out


@dataclass(frozen=True, slots=True)
class BlockingRecallResult:
    task: str
    n_records: int
    gold_positive_pairs: int
    candidate_pairs: int
    positive_pairs_retrieved: int
    blocking_recall: float
    pair_reduction_fraction: float
    used_exhaustive_pairing: bool


class BlockingRecallBenchmark:
    """Quantify the safety/computational trade-off of candidate blocking."""

    @staticmethod
    def deduplication(records: list[EvidenceRecord], labels: Iterable[LabeledPair], *, engine: ConfidenceDeduplicationEngine | None = None) -> BlockingRecallResult:
        engine = engine or ConfidenceDeduplicationEngine()
        candidates, exhaustive = engine.candidate_pairs(records)
        positive = {(min(x.left_index, x.right_index), max(x.left_index, x.right_index)) for x in labels if x.is_duplicate}
        hit = len(positive & candidates)
        total_pairs = len(records) * (len(records) - 1) // 2
        return BlockingRecallResult(
            "deduplication", len(records), len(positive), len(candidates), hit,
            _safe_div(hit, len(positive)) if positive else 1.0,
            1.0 - _safe_div(len(candidates), total_pairs) if total_pairs else 0.0,
            exhaustive,
        )

    @staticmethod
    def study_linkage(records: list[EvidenceRecord], labels: Iterable[StudyLabeledPair], *, engine: StudyLinkageEngine | None = None) -> BlockingRecallResult:
        engine = engine or StudyLinkageEngine()
        candidates, exhaustive = engine.candidate_pairs(records)
        positive = {(min(x.left_index, x.right_index), max(x.left_index, x.right_index)) for x in labels if x.same_study}
        hit = len(positive & candidates)
        total_pairs = len(records) * (len(records) - 1) // 2
        return BlockingRecallResult(
            "study_linkage", len(records), len(positive), len(candidates), hit,
            _safe_div(hit, len(positive)) if positive else 1.0,
            1.0 - _safe_div(len(candidates), total_pairs) if total_pairs else 0.0,
            exhaustive,
        )


@dataclass(frozen=True, slots=True)
class BootstrapCI:
    estimate: float
    low: float
    high: float
    confidence: float
    n_bootstrap: int


def bootstrap_proportion_ci(values: Sequence[bool | int | float], *, confidence: float = 0.95, n_bootstrap: int = 2000, seed: int = 2026) -> BootstrapCI:
    if not values:
        raise ValueError("values must not be empty")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    if n_bootstrap < 100:
        raise ValueError("n_bootstrap must be >= 100")
    xs = [float(bool(v)) for v in values]
    estimate = statistics.fmean(xs)
    rng = random.Random(seed)
    boots = []
    n = len(xs)
    for _ in range(n_bootstrap):
        boots.append(statistics.fmean(xs[rng.randrange(n)] for _ in range(n)))
    boots.sort()
    alpha = (1 - confidence) / 2
    lo_idx = max(0, min(n_bootstrap - 1, int(math.floor(alpha * (n_bootstrap - 1)))))
    hi_idx = max(0, min(n_bootstrap - 1, int(math.ceil((1 - alpha) * (n_bootstrap - 1)))))
    return BootstrapCI(estimate, boots[lo_idx], boots[hi_idx], confidence, n_bootstrap)


@dataclass(slots=True)
class ScientificBenchmarkBundle:
    name: str
    query_translation: list[QueryTranslationBenchmarkResult] = field(default_factory=list)
    dedup_ablation: list[AblationResult] = field(default_factory=list)
    study_ablation: list[AblationResult] = field(default_factory=list)
    blocking_recall: list[BlockingRecallResult] = field(default_factory=list)
    metadata_stress: list[StressPoint] = field(default_factory=list)
    scalability: list[ScalabilityPoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def _write_rows(path: Path, rows: Sequence[object]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        dicts = [asdict(r) for r in rows]
        # Flatten one nested dataclass used by query-translation results.
        flat = []
        for row in dicts:
            metrics = row.pop("metrics", None)
            if isinstance(metrics, dict):
                row.update({f"retrieval_{k}": v for k, v in metrics.items()})
            flat.append(row)
        fields = list(flat[0].keys())
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(flat)

    def write(self, directory: str | Path) -> Path:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        files = {
            "query_translation.csv": self.query_translation,
            "dedup_ablation.csv": self.dedup_ablation,
            "study_ablation.csv": self.study_ablation,
            "blocking_recall.csv": self.blocking_recall,
            "metadata_stress.csv": self.metadata_stress,
            "scalability.csv": self.scalability,
        }
        for filename, rows in files.items():
            self._write_rows(root / filename, rows)

        payload = {
            "name": self.name,
            "notes": self.notes,
            "query_translation": [asdict(x) for x in self.query_translation],
            "dedup_ablation": [asdict(x) for x in self.dedup_ablation],
            "study_ablation": [asdict(x) for x in self.study_ablation],
            "blocking_recall": [asdict(x) for x in self.blocking_recall],
            "metadata_stress": [asdict(x) for x in self.metadata_stress],
            "scalability": [asdict(x) for x in self.scalability],
        }
        (root / "benchmark_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        hashes: dict[str, dict[str, object]] = {}
        for path in sorted(root.iterdir()):
            if path.is_file() and path.name != "benchmark_manifest.json":
                data = path.read_bytes()
                hashes[path.name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        manifest = {
            "bundle_name": self.name,
            "files": hashes,
            "important": "Synthetic/unit-test benchmark results are engineering QA only; external gold-standard validation is required for scientific performance claims.",
        }
        (root / "benchmark_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return root
