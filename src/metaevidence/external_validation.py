from __future__ import annotations

from dataclasses import asdict, dataclass, field
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Sequence

from .dedup import ConfidenceDeduplicationEngine, DeduplicationResult
from .models import EvidenceRecord, SourceHit


def _safe_div(a: float, b: float, *, empty: float = 0.0) -> float:
    return a / b if b else empty


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "record_id": ("recordid", "record_id", "id", "citationid", "citation_id", "refid", "ref_id"),
    "title": ("title", "ti", "articletitle", "primarytitle"),
    "authors": ("authors", "author", "au", "creator", "creators"),
    "year": ("year", "py", "publicationyear", "pubyear", "date", "publicationdate"),
    "journal": ("journal", "journaltitle", "secondarytitle", "source", "publication", "jo"),
    "abstract": ("abstract", "ab", "summary"),
    "doi": ("doi", "digitalobjectidentifier"),
    "pmid": ("pmid", "pubmedid"),
    "volume": ("volume", "vol", "vl"),
    "issue": ("issue", "number", "is"),
    "pages": ("pages", "page", "pagerange", "sp"),
    "database": ("database", "db", "source_database", "sourcedatabase"),
    "gold_group": (
        "goldgroup", "gold_group", "duplicateid", "duplicate_id", "duplicategroup",
        "duplicate_group", "dedupgroup", "dedup_group", "groupid", "group_id",
        "publicationid", "publication_id", "clusterid", "cluster_id", "matchid", "match_id",
    ),
    "removal_label": (
        "label", "goldlabel", "gold_label", "removallabel", "removal_label",
        "deduplabel", "dedup_label", "classification",
    ),
}


def _detect_column(headers: Sequence[str], aliases: Sequence[str]) -> str | None:
    norm_to_original = {_norm_header(h): h for h in headers}
    for alias in aliases:
        hit = norm_to_original.get(_norm_header(alias))
        if hit is not None:
            return hit
    return None


def _split_authors(value: str | None) -> list[str]:
    if not value:
        return []
    text = str(value).strip()
    if not text:
        return []
    # Prefer explicit citation-list separators. Do not split commas because many
    # bibliographic exports use "Surname, Initials" for one author.
    if ";" in text:
        parts = text.split(";")
    elif "|" in text:
        parts = text.split("|")
    elif re.search(r"\s+and\s+", text, flags=re.I):
        parts = re.split(r"\s+and\s+", text, flags=re.I)
    else:
        parts = [text]
    return [p.strip() for p in parts if p.strip()]


def _parse_year(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"\b(18|19|20|21)\d{2}\b", str(value))
    return int(match.group(0)) if match else None


@dataclass(slots=True)
class ExternalGoldDataset:
    """Record-level gold-standard partition for external deduplication validation.

    ``gold_group_ids`` identify the underlying bibliographic publication represented
    by each input citation. Records with the same group are duplicates. Blank group
    cells in source files are converted to deterministic singleton groups, which is
    a common convention in deduplication gold standards.
    """

    name: str
    records: list[EvidenceRecord]
    gold_group_ids: list[str]
    record_ids: list[str]
    source_path: str | None = None
    group_column: str | None = None
    field_map: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = len(self.records)
        if len(self.gold_group_ids) != n or len(self.record_ids) != n:
            raise ValueError("records, gold_group_ids and record_ids must have equal length")
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("record_ids must be unique")
        if any(not str(g).strip() for g in self.gold_group_ids):
            raise ValueError("gold_group_ids must be non-empty after normalization")

    @property
    def n_records(self) -> int:
        return len(self.records)

    @property
    def n_gold_publications(self) -> int:
        return len(set(self.gold_group_ids))

    @property
    def n_gold_duplicates_removed(self) -> int:
        return self.n_records - self.n_gold_publications

    @classmethod
    def from_delimited(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        delimiter: str | None = None,
        group_column: str | None = None,
        record_id_column: str | None = None,
        field_overrides: dict[str, str] | None = None,
        encoding: str = "utf-8-sig",
    ) -> "ExternalGoldDataset":
        path = Path(path)
        if delimiter is None:
            delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab", ".txt"} else ","
        with path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            rows = list(reader)
            headers = list(reader.fieldnames or [])
        if not rows:
            raise ValueError(f"No rows found in {path}")

        overrides = field_overrides or {}
        fmap: dict[str, str] = {}
        for field_name, aliases in _FIELD_ALIASES.items():
            explicit = overrides.get(field_name)
            if explicit:
                if explicit not in headers:
                    raise KeyError(f"Column {explicit!r} not present in {path}")
                fmap[field_name] = explicit
            else:
                hit = _detect_column(headers, aliases)
                if hit:
                    fmap[field_name] = hit

        if group_column:
            if group_column not in headers:
                raise KeyError(f"group_column {group_column!r} not present in {path}")
            fmap["gold_group"] = group_column
        if record_id_column:
            if record_id_column not in headers:
                raise KeyError(f"record_id_column {record_id_column!r} not present in {path}")
            fmap["record_id"] = record_id_column

        if "title" not in fmap:
            raise ValueError("Could not detect a title column; supply field_overrides={'title': ...}")
        if "gold_group" not in fmap:
            raise ValueError(
                "Could not detect a gold duplicate/publication group column; "
                "supply group_column=... or field_overrides={'gold_group': ...}"
            )

        warnings: list[str] = []
        records: list[EvidenceRecord] = []
        groups: list[str] = []
        record_ids: list[str] = []
        seen_ids: set[str] = set()

        for i, row in enumerate(rows):
            raw_id = str(row.get(fmap.get("record_id", ""), "") or "").strip()
            rid = raw_id or f"ROW-{i+1:07d}"
            if rid in seen_ids:
                rid = f"{rid}__ROW{i+1}"
                warnings.append(f"Duplicate record ID normalized at row {i+1}")
            seen_ids.add(rid)

            raw_group = str(row.get(fmap["gold_group"], "") or "").strip()
            group = raw_group if raw_group else f"__SINGLETON__:{rid}"

            metadata: dict[str, object] = {
                "external_record_id": rid,
                "external_gold_group": group,
            }
            for key in ("volume", "issue", "pages"):
                col = fmap.get(key)
                value = str(row.get(col, "") or "").strip() if col else ""
                if value:
                    metadata[key] = value
            database_col = fmap.get("database")
            database = str(row.get(database_col, "") or "").strip() if database_col else ""
            source_hits = [SourceHit(source=database, source_id=rid)] if database else []

            def val(field_name: str) -> str | None:
                col = fmap.get(field_name)
                if not col:
                    return None
                value = str(row.get(col, "") or "").strip()
                return value or None

            records.append(EvidenceRecord(
                title=val("title") or "",
                authors=_split_authors(val("authors")),
                year=_parse_year(val("year")),
                journal=val("journal"),
                abstract=val("abstract"),
                doi=val("doi"),
                pmid=val("pmid"),
                source_hits=source_hits,
                metadata=metadata,
            ))
            groups.append(group)
            record_ids.append(rid)

        return cls(
            name=name or path.stem,
            records=records,
            gold_group_ids=groups,
            record_ids=record_ids,
            source_path=str(path),
            group_column=fmap["gold_group"],
            field_map=fmap,
            warnings=warnings,
        )


@dataclass(slots=True)
class ExternalRemovalGoldDataset:
    """Gold standard where each citation is labelled retained vs removed.

    This matches validation files such as the ASySD 2023 labelled datasets, in
    which one representative citation is labelled ``Unique`` and citations to be
    removed are labelled ``Duplicate``. It is intentionally separate from
    :class:`ExternalGoldDataset`: binary removal labels do not reveal the
    underlying duplicate-group partition and must not be treated as if they did.
    """

    name: str
    records: list[EvidenceRecord]
    gold_removed: list[bool]
    record_ids: list[str]
    source_path: str | None = None
    label_column: str | None = None
    field_map: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = len(self.records)
        if len(self.gold_removed) != n or len(self.record_ids) != n:
            raise ValueError("records, gold_removed and record_ids must have equal length")
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("record_ids must be unique")

    @property
    def n_records(self) -> int:
        return len(self.records)

    @property
    def n_gold_duplicates_removed(self) -> int:
        return sum(self.gold_removed)

    @property
    def n_gold_publications(self) -> int:
        return self.n_records - self.n_gold_duplicates_removed

    @classmethod
    def from_delimited(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        delimiter: str | None = None,
        label_column: str | None = None,
        record_id_column: str | None = None,
        removed_labels: Iterable[str] = ("duplicate", "removed", "remove", "1", "true"),
        retained_labels: Iterable[str] = ("unique", "retained", "keep", "kept", "0", "false"),
        field_overrides: dict[str, str] | None = None,
        encoding: str = "utf-8-sig",
    ) -> "ExternalRemovalGoldDataset":
        path = Path(path)
        if delimiter is None:
            delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab", ".txt"} else ","
        with path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            rows = list(reader)
            headers = list(reader.fieldnames or [])
        if not rows:
            raise ValueError(f"No rows found in {path}")

        overrides = field_overrides or {}
        fmap: dict[str, str] = {}
        for field_name, aliases in _FIELD_ALIASES.items():
            explicit = overrides.get(field_name)
            if explicit:
                if explicit not in headers:
                    raise KeyError(f"Column {explicit!r} not present in {path}")
                fmap[field_name] = explicit
            else:
                hit = _detect_column(headers, aliases)
                if hit:
                    fmap[field_name] = hit

        if label_column:
            if label_column not in headers:
                raise KeyError(f"label_column {label_column!r} not present in {path}")
            fmap["removal_label"] = label_column
        if record_id_column:
            if record_id_column not in headers:
                raise KeyError(f"record_id_column {record_id_column!r} not present in {path}")
            fmap["record_id"] = record_id_column
        if "title" not in fmap:
            raise ValueError("Could not detect a title column; supply field_overrides={'title': ...}")
        if "removal_label" not in fmap:
            raise ValueError(
                "Could not detect a retained/removed gold label column; "
                "supply label_column=... or field_overrides={'removal_label': ...}"
            )

        removed = {_norm_header(v) for v in removed_labels}
        retained = {_norm_header(v) for v in retained_labels}
        if removed & retained:
            raise ValueError("removed_labels and retained_labels overlap after normalization")

        warnings: list[str] = []
        records: list[EvidenceRecord] = []
        gold_removed: list[bool] = []
        record_ids: list[str] = []
        seen_ids: set[str] = set()

        for i, row in enumerate(rows):
            raw_id = str(row.get(fmap.get("record_id", ""), "") or "").strip()
            rid = raw_id or f"ROW-{i+1:07d}"
            if rid in seen_ids:
                rid = f"{rid}__ROW{i+1}"
                warnings.append(f"Duplicate record ID normalized at row {i+1}")
            seen_ids.add(rid)

            raw_label = str(row.get(fmap["removal_label"], "") or "").strip()
            label = _norm_header(raw_label)
            if label in removed:
                is_removed = True
            elif label in retained:
                is_removed = False
            else:
                raise ValueError(
                    f"Unknown removal gold label {raw_label!r} at row {i+1}; "
                    "supply explicit removed_labels/retained_labels if needed"
                )

            metadata: dict[str, object] = {
                "external_record_id": rid,
                "external_gold_removal_label": raw_label,
                "external_gold_removed": is_removed,
            }
            for key in ("volume", "issue", "pages"):
                col = fmap.get(key)
                value = str(row.get(col, "") or "").strip() if col else ""
                if value:
                    metadata[key] = value
            database_col = fmap.get("database")
            database = str(row.get(database_col, "") or "").strip() if database_col else ""
            source_hits = [SourceHit(source=database, source_id=rid)] if database else []

            def val(field_name: str) -> str | None:
                col = fmap.get(field_name)
                if not col:
                    return None
                value = str(row.get(col, "") or "").strip()
                return value or None

            records.append(EvidenceRecord(
                title=val("title") or "",
                authors=_split_authors(val("authors")),
                year=_parse_year(val("year")),
                journal=val("journal"),
                abstract=val("abstract"),
                doi=val("doi"),
                pmid=val("pmid"),
                source_hits=source_hits,
                metadata=metadata,
            ))
            gold_removed.append(is_removed)
            record_ids.append(rid)

        return cls(
            name=name or path.stem,
            records=records,
            gold_removed=gold_removed,
            record_ids=record_ids,
            source_path=str(path),
            label_column=fmap["removal_label"],
            field_map=fmap,
            warnings=warnings,
        )


@dataclass(frozen=True, slots=True)
class ExternalDatasetSpecification:
    """Pre-specified expectations for one external validation dataset.

    Expected counts are used as integrity checks only; they are never inferred from
    MetaEvidence predictions.  ``role`` should be frozen before performance is
    inspected (for example ``development``, ``calibration`` or ``held_out_test``).
    """

    id: str
    role: str
    source: str
    expected_records: int | None = None
    expected_gold_duplicates_removed: int | None = None
    expected_gold_publications: int | None = None
    filename: str | None = None
    gold_standard_type: str = "partition_group"
    notes: str | None = None

    @classmethod
    def from_dict(cls, row: dict[str, object]) -> "ExternalDatasetSpecification":
        return cls(
            id=str(row["id"]),
            role=str(row.get("role", "unspecified")),
            source=str(row.get("source", "")),
            expected_records=(int(row["expected_records"]) if row.get("expected_records") is not None else None),
            expected_gold_duplicates_removed=(
                int(row["expected_gold_duplicates_removed"])
                if row.get("expected_gold_duplicates_removed") is not None else None
            ),
            expected_gold_publications=(
                int(row["expected_gold_publications"])
                if row.get("expected_gold_publications") is not None else None
            ),
            filename=(str(row["filename"]) if row.get("filename") else None),
            gold_standard_type=str(row.get("gold_standard_type", "partition_group")),
            notes=(str(row["notes"]) if row.get("notes") else None),
        )


@dataclass(frozen=True, slots=True)
class ExternalDatasetIntegrityCheck:
    dataset: str
    specification_id: str
    passed: bool
    observed_records: int
    observed_gold_duplicates_removed: int
    observed_gold_publications: int
    mismatches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_external_dataset(
    dataset: ExternalGoldDataset | ExternalRemovalGoldDataset,
    specification: ExternalDatasetSpecification,
    *,
    strict: bool = False,
) -> ExternalDatasetIntegrityCheck:
    """Check a loaded gold standard against pre-specified published counts.

    This catches wrong files, wrong label columns and the common mistake of using
    original human deduplication counts as if they were the final consensus gold
    standard.  In strict mode a mismatch raises ``ValueError`` before benchmarking.
    """
    mismatches: list[str] = []

    def check(label: str, observed: int, expected: int | None) -> None:
        if expected is not None and observed != expected:
            mismatches.append(f"{label}: observed={observed}, expected={expected}")

    check("records", dataset.n_records, specification.expected_records)
    check(
        "gold_duplicates_removed",
        dataset.n_gold_duplicates_removed,
        specification.expected_gold_duplicates_removed,
    )
    check("gold_publications", dataset.n_gold_publications, specification.expected_gold_publications)

    result = ExternalDatasetIntegrityCheck(
        dataset=dataset.name,
        specification_id=specification.id,
        passed=not mismatches,
        observed_records=dataset.n_records,
        observed_gold_duplicates_removed=dataset.n_gold_duplicates_removed,
        observed_gold_publications=dataset.n_gold_publications,
        mismatches=tuple(mismatches),
    )
    if strict and mismatches:
        raise ValueError(
            f"External dataset {dataset.name!r} failed integrity check for {specification.id!r}: "
            + "; ".join(mismatches)
        )
    return result


def load_external_dataset_specifications(path: str | Path) -> list[ExternalDatasetSpecification]:
    """Load dataset specifications from a MetaEvidence external-validation plan JSON."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("datasets", [])
    return [
        ExternalDatasetSpecification.from_dict(row)
        for row in rows
        if row.get("task") == "publication_deduplication" and row.get("expected_records") is not None
    ]


@dataclass(frozen=True, slots=True)
class DedupPartitionMetrics:
    dataset: str
    input_records: int
    gold_publications: int
    predicted_publications: int
    gold_duplicates_removed: int
    predicted_duplicates_removed: int
    removed_singulars: int
    missed_duplicates: int
    singular_retention: float
    duplicate_recall: float
    partition_error_fraction: float
    candidate_pairs: int
    assessed_pairs: int
    auto_merge_pairs: int
    review_pairs: int
    used_exhaustive_pairing: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class ExternalDeduplicationResult:
    metrics: DedupPartitionMetrics
    predicted_group_ids: list[str]
    deduplication: DeduplicationResult


class DedupPartitionBenchmark:
    """Evaluate deduplication as a partitioning task.

    This mirrors the practical outcomes used in contemporary deduplication studies:
    * ``removed_singulars`` — unique bibliographic publications lost by false merges;
    * ``missed_duplicates`` — extra duplicate citations retained because a gold
      publication was split across more than one predicted cluster.

    The calculation does not depend on which member of a duplicate group is kept.
    """

    @staticmethod
    def _predicted_groups(n: int, result: DeduplicationResult) -> list[str]:
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for link in result.links:
            union(link.kept_index, link.removed_index)
        roots = [find(i) for i in range(n)]
        root_to_label: dict[int, str] = {}
        out: list[str] = []
        for root in roots:
            if root not in root_to_label:
                root_to_label[root] = f"PRED-{len(root_to_label)+1:07d}"
            out.append(root_to_label[root])
        return out

    @classmethod
    def evaluate(
        cls,
        dataset: ExternalGoldDataset,
        *,
        engine: ConfidenceDeduplicationEngine | None = None,
    ) -> ExternalDeduplicationResult:
        engine = engine or ConfidenceDeduplicationEngine()
        result = engine.deduplicate(dataset.records)
        predicted = cls._predicted_groups(dataset.n_records, result)
        gold = dataset.gold_group_ids

        predicted_clusters: dict[str, list[int]] = {}
        for i, pg in enumerate(predicted):
            predicted_clusters.setdefault(pg, []).append(i)
        gold_clusters: dict[str, list[int]] = {}
        for i, gg in enumerate(gold):
            gold_clusters.setdefault(gg, []).append(i)

        removed_singulars = 0
        for indices in predicted_clusters.values():
            distinct_gold = {gold[i] for i in indices}
            removed_singulars += max(0, len(distinct_gold) - 1)

        missed_duplicates = 0
        for indices in gold_clusters.values():
            distinct_pred = {predicted[i] for i in indices}
            missed_duplicates += max(0, len(distinct_pred) - 1)

        n = dataset.n_records
        gold_publications = len(gold_clusters)
        predicted_publications = len(predicted_clusters)
        gold_duplicates = n - gold_publications
        predicted_duplicates = n - predicted_publications
        singular_retention = 1.0 - _safe_div(removed_singulars, gold_publications, empty=0.0)
        duplicate_recall = 1.0 - _safe_div(missed_duplicates, gold_duplicates, empty=0.0) if gold_duplicates else 1.0
        error_fraction = min(1.0, _safe_div(removed_singulars + missed_duplicates, n, empty=0.0))

        metrics = DedupPartitionMetrics(
            dataset=dataset.name,
            input_records=n,
            gold_publications=gold_publications,
            predicted_publications=predicted_publications,
            gold_duplicates_removed=gold_duplicates,
            predicted_duplicates_removed=predicted_duplicates,
            removed_singulars=removed_singulars,
            missed_duplicates=missed_duplicates,
            singular_retention=singular_retention,
            duplicate_recall=duplicate_recall,
            partition_error_fraction=error_fraction,
            candidate_pairs=result.stats.candidate_pairs,
            assessed_pairs=result.stats.assessed_pairs,
            auto_merge_pairs=result.stats.auto_merge_pairs,
            review_pairs=result.stats.review_pairs,
            used_exhaustive_pairing=result.stats.used_exhaustive_pairing,
        )
        return ExternalDeduplicationResult(metrics, predicted, result)


@dataclass(frozen=True, slots=True)
class RemovalLabelMetrics:
    """Representative-sensitive record-removal metrics."""

    dataset: str
    input_records: int
    gold_duplicates_removed: int
    predicted_duplicates_removed: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    sensitivity: float
    specificity: float
    precision: float
    f1: float
    accuracy: float
    false_positive_rate: float
    false_negative_rate: float
    candidate_pairs: int
    assessed_pairs: int
    auto_merge_pairs: int
    review_pairs: int
    used_exhaustive_pairing: bool

    @property
    def removed_singulars(self) -> int:
        return self.false_positive

    @property
    def missed_duplicates(self) -> int:
        return self.false_negative

    def to_dict(self) -> dict[str, object]:
        out = asdict(self)
        out["removed_singulars"] = self.removed_singulars
        out["missed_duplicates"] = self.missed_duplicates
        return out


@dataclass(slots=True)
class ExternalRemovalValidationResult:
    metrics: RemovalLabelMetrics
    predicted_removed: list[bool]
    deduplication: DeduplicationResult


class RemovalLabelBenchmark:
    """Evaluate record-removal labels with explicit representative-retention semantics.

    The default ``engine_quality`` mode is blind to the gold labels and therefore
    represents deployable MetaEvidence behavior.  ``gold_preferred_reproduction``
    is provided only to reproduce label-aware benchmarks such as the ASySD 2023
    validation code, which calls ``dedup_citations(..., keep_label="Unique")``.
    That reproduction mode MUST NOT be interpreted as an unbiased external result
    because the gold label is used to choose which member of a predicted cluster is
    retained.  Duplicate detection/clustering itself is unchanged.
    """

    VALID_RETENTION_MODES = {"engine_quality", "gold_preferred_reproduction"}

    @staticmethod
    def _metrics(
        dataset: ExternalRemovalGoldDataset,
        predicted: list[bool],
        result: DeduplicationResult,
    ) -> RemovalLabelMetrics:
        tp = sum(g and p for g, p in zip(dataset.gold_removed, predicted))
        tn = sum((not g) and (not p) for g, p in zip(dataset.gold_removed, predicted))
        fp = sum((not g) and p for g, p in zip(dataset.gold_removed, predicted))
        fn = sum(g and (not p) for g, p in zip(dataset.gold_removed, predicted))
        sensitivity = _safe_div(tp, tp + fn, empty=1.0)
        specificity = _safe_div(tn, tn + fp, empty=1.0)
        precision = _safe_div(tp, tp + fp, empty=1.0)
        f1 = _safe_div(2 * precision * sensitivity, precision + sensitivity, empty=0.0)
        accuracy = _safe_div(tp + tn, dataset.n_records, empty=0.0)
        return RemovalLabelMetrics(
            dataset=dataset.name,
            input_records=dataset.n_records,
            gold_duplicates_removed=dataset.n_gold_duplicates_removed,
            predicted_duplicates_removed=sum(predicted),
            true_positive=tp,
            true_negative=tn,
            false_positive=fp,
            false_negative=fn,
            sensitivity=sensitivity,
            specificity=specificity,
            precision=precision,
            f1=f1,
            accuracy=accuracy,
            false_positive_rate=_safe_div(fp, fp + tn),
            false_negative_rate=_safe_div(fn, fn + tp),
            candidate_pairs=result.stats.candidate_pairs,
            assessed_pairs=result.stats.assessed_pairs,
            auto_merge_pairs=result.stats.auto_merge_pairs,
            review_pairs=result.stats.review_pairs,
            used_exhaustive_pairing=result.stats.used_exhaustive_pairing,
        )

    @staticmethod
    def _gold_preferred_predictions(
        dataset: ExternalRemovalGoldDataset,
        result: DeduplicationResult,
    ) -> list[bool]:
        """Choose a gold-retained member within each predicted cluster when possible.

        This mirrors the *retention* consequence of ASySD's ``keep_label="Unique"``
        validation setting without changing which records MetaEvidence clustered.
        It is intentionally isolated from the production deduplication engine.
        """
        predicted_groups = DedupPartitionBenchmark._predicted_groups(dataset.n_records, result)
        clusters: dict[str, list[int]] = {}
        for i, group in enumerate(predicted_groups):
            clusters.setdefault(group, []).append(i)
        predicted_removed = [False] * dataset.n_records
        for indices in clusters.values():
            gold_retained = [i for i in indices if not dataset.gold_removed[i]]
            representative = gold_retained[0] if gold_retained else indices[0]
            for i in indices:
                predicted_removed[i] = i != representative
        return predicted_removed

    @classmethod
    def evaluate(
        cls,
        dataset: ExternalRemovalGoldDataset,
        *,
        engine: ConfidenceDeduplicationEngine | None = None,
        retention_mode: str = "engine_quality",
    ) -> ExternalRemovalValidationResult:
        if retention_mode not in cls.VALID_RETENTION_MODES:
            raise ValueError(
                f"Unknown retention_mode {retention_mode!r}; expected one of "
                f"{sorted(cls.VALID_RETENTION_MODES)}"
            )
        engine = engine or ConfidenceDeduplicationEngine()
        result = engine.deduplicate(dataset.records)
        if retention_mode == "engine_quality":
            removed_indices = {link.removed_index for link in result.links}
            predicted = [i in removed_indices for i in range(dataset.n_records)]
        else:
            predicted = cls._gold_preferred_predictions(dataset, result)
        return ExternalRemovalValidationResult(cls._metrics(dataset, predicted, result), predicted, result)

    @classmethod
    def compare_retention_modes(
        cls,
        dataset: ExternalRemovalGoldDataset,
        *,
        engine: ConfidenceDeduplicationEngine | None = None,
        deduplication_result: DeduplicationResult | None = None,
    ) -> "RemovalRetentionComparison":
        # Reuse an existing blind run when supplied; otherwise cluster exactly once.
        if deduplication_result is None:
            engine = engine or ConfidenceDeduplicationEngine()
            result = engine.deduplicate(dataset.records)
        else:
            result = deduplication_result
        blind_removed = [i in {link.removed_index for link in result.links} for i in range(dataset.n_records)]
        gold_removed = cls._gold_preferred_predictions(dataset, result)
        blind = ExternalRemovalValidationResult(cls._metrics(dataset, blind_removed, result), blind_removed, result)
        reproduction = ExternalRemovalValidationResult(cls._metrics(dataset, gold_removed, result), gold_removed, result)
        return RemovalRetentionComparison(
            blind=blind,
            gold_preferred_reproduction=reproduction,
            same_predicted_partition=True,
            reproduction_uses_gold_labels=True,
        )


@dataclass(slots=True)
class RemovalRetentionComparison:
    """Blind versus gold-preferred record-retention evaluation on one clustering."""

    blind: ExternalRemovalValidationResult
    gold_preferred_reproduction: ExternalRemovalValidationResult
    same_predicted_partition: bool = True
    reproduction_uses_gold_labels: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "blind_engine_quality": self.blind.metrics.to_dict(),
            "gold_preferred_reproduction": self.gold_preferred_reproduction.metrics.to_dict(),
            "same_predicted_partition": self.same_predicted_partition,
            "reproduction_uses_gold_labels": self.reproduction_uses_gold_labels,
            "interpretation": (
                "Blind engine-quality retention is the unbiased deployable estimate. "
                "Gold-preferred reproduction uses the reference label only to choose the "
                "retained representative inside each MetaEvidence-predicted cluster and "
                "must not be used as the primary external performance claim."
            ),
        }


def load_external_gold_dataset(
    path: str | Path,
    specification: ExternalDatasetSpecification,
    *,
    strict: bool = True,
) -> ExternalGoldDataset | ExternalRemovalGoldDataset:
    """Load external gold data using semantics frozen in the manifest."""
    kind = specification.gold_standard_type.strip().lower()
    if kind in {"removal_label", "binary_removal", "asysd_removal_label"}:
        dataset = ExternalRemovalGoldDataset.from_delimited(path, name=specification.id)
    elif kind in {"partition_group", "duplicate_partition", "groups"}:
        dataset = ExternalGoldDataset.from_delimited(path, name=specification.id)
    else:
        raise ValueError(f"Unsupported gold_standard_type: {specification.gold_standard_type!r}")
    validate_external_dataset(dataset, specification, strict=strict)
    return dataset


@dataclass(frozen=True, slots=True)
class PublishedDeduplicationBaseline:
    tool: str
    input_records: int
    duplicates_removed: int
    records_remaining: int
    removed_singulars: int
    missed_duplicates: int
    time_minutes: int
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def published_2026_baselines() -> list[PublishedDeduplicationBaseline]:
    """Aggregate published comparison values from Bateup et al. (2026).

    These values are literature reference points, not MetaEvidence results and not
    calibration data. Keep them separate from any gold-standard records used to tune
    thresholds.
    """
    source = "Bateup et al. 2026, Research Synthesis Methods, doi:10.1017/rsm.2026.10100"
    rows = [
        ("ASySD", 26778, 7248, 19530, 22, 34, 53),
        ("Covidence", 26778, 6985, 19793, 8, 276, 32),
        ("Deduklick", 26778, 7189, 19589, 11, 81, 14),
        ("EPPI-Reviewer", 26778, 7209, 19569, 20, 74, 63),
        ("PICO Portal", 26778, 7129, 19649, 16, 136, 307),
        ("Rayyan", 26778, 7222, 19556, 2, 40, 1234),
        ("SRA Deduplicator: Focused", 26778, 7191, 19587, 9, 81, 178),
        ("SRA Deduplicator: Relaxed", 26778, 6976, 19802, 11, 280, 1),
    ]
    return [PublishedDeduplicationBaseline(*row, source) for row in rows]


def write_published_2026_baselines(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = published_2026_baselines()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].to_dict()))
        writer.writeheader()
        writer.writerows(row.to_dict() for row in rows)
    return path


def write_external_removal_validation_result(
    result: ExternalRemovalValidationResult,
    root: str | Path,
    *,
    dataset: ExternalRemovalGoldDataset | None = None,
    specification: ExternalDatasetSpecification | None = None,
) -> Path:
    """Write auditable record-removal validation artifacts without source redistribution."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    metrics_path = root / "external_removal_metrics.json"
    metrics_path.write_text(json.dumps(result.metrics.to_dict(), indent=2), encoding="utf-8")

    assignments = root / "removal_assignments.csv"
    with assignments.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if dataset is None:
            writer.writerow(["row_index", "predicted_removed"])
            for i, pred in enumerate(result.predicted_removed):
                writer.writerow([i, int(pred)])
        else:
            writer.writerow(["row_index", "record_id", "gold_removed", "predicted_removed"])
            for i, (gold, pred) in enumerate(zip(dataset.gold_removed, result.predicted_removed)):
                writer.writerow([i, dataset.record_ids[i], int(gold), int(pred)])

    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "gold_standard_type": "removal_label",
        "metrics_file": metrics_path.name,
        "assignments_file": assignments.name,
        "metrics": result.metrics.to_dict(),
    }
    if dataset is not None:
        source_path = Path(dataset.source_path) if dataset.source_path else None
        manifest["dataset"] = {
            "name": dataset.name,
            "source_path": dataset.source_path,
            "source_sha256": (
                _file_sha256(source_path) if source_path is not None and source_path.is_file() else None
            ),
            "records": dataset.n_records,
            "gold_publications": dataset.n_gold_publications,
            "gold_duplicates_removed": dataset.n_gold_duplicates_removed,
            "label_column": dataset.label_column,
            "field_map": dataset.field_map,
            "warnings": dataset.warnings,
        }
    if specification is not None:
        manifest["specification"] = asdict(specification)
        if dataset is not None:
            manifest["integrity_check"] = validate_external_dataset(dataset, specification).to_dict()
    (root / "external_validation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return root


def write_removal_retention_comparison(
    comparison: RemovalRetentionComparison,
    root: str | Path,
    *,
    dataset: ExternalRemovalGoldDataset | None = None,
    specification: ExternalDatasetSpecification | None = None,
) -> Path:
    """Write blind and gold-preferred retention metrics side-by-side.

    No third-party citation text is copied into the result bundle.  Assignments
    contain only row/record IDs and binary decisions.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    payload = comparison.to_dict()
    (root / "retention_mode_comparison.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    assignments = root / "retention_mode_assignments.csv"
    with assignments.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "row_index", "record_id", "gold_removed",
            "blind_predicted_removed", "gold_preferred_predicted_removed"
        ])
        for i, (blind, repro) in enumerate(zip(
            comparison.blind.predicted_removed,
            comparison.gold_preferred_reproduction.predicted_removed,
        )):
            rid = dataset.record_ids[i] if dataset is not None else str(i)
            gold = int(dataset.gold_removed[i]) if dataset is not None else ""
            writer.writerow([i, rid, gold, int(blind), int(repro)])
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "primary_mode": "blind_engine_quality",
        "secondary_reproduction_mode": "gold_preferred_reproduction",
        "secondary_mode_uses_gold_labels_for_retention": True,
        "same_predicted_partition": comparison.same_predicted_partition,
        "comparison_file": "retention_mode_comparison.json",
        "assignments_file": assignments.name,
    }
    if dataset is not None:
        manifest["dataset"] = {
            "name": dataset.name,
            "records": dataset.n_records,
            "gold_duplicates_removed": dataset.n_gold_duplicates_removed,
            "source_path": dataset.source_path,
            "source_sha256": (
                _file_sha256(Path(dataset.source_path))
                if dataset.source_path and Path(dataset.source_path).is_file() else None
            ),
        }
    if specification is not None:
        manifest["specification"] = asdict(specification)
    (root / "retention_mode_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return root


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_external_validation_result(
    result: ExternalDeduplicationResult,
    root: str | Path,
    *,
    dataset: ExternalGoldDataset | None = None,
    specification: ExternalDatasetSpecification | None = None,
) -> Path:
    """Write audit-ready external validation artifacts.

    If ``dataset`` is supplied, the output stores record IDs, gold and predicted
    partitions side-by-side plus the SHA-256 of the untouched source file when it
    exists locally.  This makes it possible to reproduce exactly which benchmark
    file was evaluated without redistributing that third-party file.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    metrics_path = root / "external_dedup_metrics.json"
    metrics_path.write_text(json.dumps(result.metrics.to_dict(), indent=2), encoding="utf-8")

    groups_path = root / "partition_assignments.csv"
    with groups_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if dataset is None:
            writer.writerow(["row_index", "predicted_group"])
            for i, group in enumerate(result.predicted_group_ids):
                writer.writerow([i, group])
        else:
            if dataset.n_records != len(result.predicted_group_ids):
                raise ValueError("dataset and result contain different numbers of records")
            writer.writerow(["row_index", "record_id", "gold_group", "predicted_group"])
            for i, group in enumerate(result.predicted_group_ids):
                writer.writerow([i, dataset.record_ids[i], dataset.gold_group_ids[i], group])

    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "metrics_file": metrics_path.name,
        "assignments_file": groups_path.name,
        "metrics": result.metrics.to_dict(),
    }
    if dataset is not None:
        source_path = Path(dataset.source_path) if dataset.source_path else None
        manifest["dataset"] = {
            "name": dataset.name,
            "source_path": dataset.source_path,
            "source_sha256": (
                _file_sha256(source_path) if source_path is not None and source_path.is_file() else None
            ),
            "records": dataset.n_records,
            "gold_publications": dataset.n_gold_publications,
            "gold_duplicates_removed": dataset.n_gold_duplicates_removed,
            "group_column": dataset.group_column,
            "field_map": dataset.field_map,
            "warnings": dataset.warnings,
        }
    if specification is not None:
        manifest["specification"] = asdict(specification)
        if dataset is not None:
            manifest["integrity_check"] = validate_external_dataset(dataset, specification).to_dict()

    (root / "external_validation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return root
