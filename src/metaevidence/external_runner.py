from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .dedup import ConfidenceDeduplicationEngine
from .asysd_compat import calculate_asysd_performance_contract
from .external_validation import (
    DedupPartitionBenchmark,
    ExternalGoldDataset,
    ExternalRemovalGoldDataset,
    RemovalLabelBenchmark,
    write_removal_retention_comparison,
    validate_external_dataset,
    load_external_dataset_specifications,
    load_external_gold_dataset,
    write_external_removal_validation_result,
    write_external_validation_result,
)


def _sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class ExternalRunSummary:
    dataset_id: str
    role: str
    gold_standard_type: str
    input_records: int
    gold_duplicates_removed: int
    predicted_duplicates_removed: int
    removed_singulars: int
    missed_duplicates: int
    sensitivity_or_duplicate_recall: float
    specificity_or_singular_retention: float
    source_sha256: str
    result_directory: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_external_validation_plan(
    manifest_path: str | Path,
    data_directory: str | Path,
    output_directory: str | Path,
    *,
    roles: Iterable[str] = ('development', 'calibration'),
    allow_held_out: bool = False,
    engine: ConfidenceDeduplicationEngine | None = None,
) -> list[ExternalRunSummary]:
    """Execute only pre-specified external datasets whose role is authorized.

    Held-out datasets are protected by a separate explicit switch. This makes an
    accidental ``run all`` less likely to reveal test outcomes during development.
    The function never copies the third-party source CSV into the result bundle.
    """
    manifest_path=Path(manifest_path)
    data_directory=Path(data_directory)
    output_directory=Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    allowed={str(r) for r in roles}
    if not allow_held_out and 'held_out_test' in allowed:
        raise PermissionError('held_out_test requires allow_held_out=True')

    specs=load_external_dataset_specifications(manifest_path)
    engine=engine or ConfidenceDeduplicationEngine()
    summaries: list[ExternalRunSummary]=[]
    secondary_artifacts: list[dict[str, object]]=[]
    asysd_compatibility_rows: list[dict[str, object]]=[]

    for spec in specs:
        if spec.role not in allowed:
            continue
        if spec.role == 'held_out_test' and not allow_held_out:
            raise PermissionError(f'Refusing to reveal held-out outcome for {spec.id}')
        if not spec.filename:
            continue
        source=data_directory/spec.filename
        if not source.is_file():
            raise FileNotFoundError(f'External validation file not found: {source}')
        dataset=load_external_gold_dataset(source, spec, strict=True)
        out=output_directory/spec.id
        if isinstance(dataset, ExternalRemovalGoldDataset):
            # Primary result: deployable, blind-to-gold representative selection.
            result=RemovalLabelBenchmark.evaluate(dataset, engine=engine, retention_mode='engine_quality')
            write_external_removal_validation_result(result, out, dataset=dataset, specification=spec)

            # Secondary reproduction result: same predicted clustering, but choose a
            # gold-Unique representative when one exists, mirroring ASySD 2023's
            # keep_label="Unique" validation setting. This is deliberately labelled
            # as gold-informed and must not become the primary external claim.
            comparison=RemovalLabelBenchmark.compare_retention_modes(
                dataset, deduplication_result=result.deduplication
            )
            retention_dir=out/'retention_reproduction'
            write_removal_retention_comparison(
                comparison, retention_dir, dataset=dataset, specification=spec
            )
            secondary_artifacts.append({
                'dataset_id':spec.id,
                'type':'gold_preferred_retention_reproduction',
                'uses_gold_labels':True,
                'directory':str(retention_dir),
            })

            # Record exact ASySD R-style TP/TN/FN/FP and percentage metrics for
            # both retention policies. These are derived from the same clustering.
            blind_contract = calculate_asysd_performance_contract(
                dataset.gold_removed, comparison.blind.predicted_removed
            )
            reproduction_contract = calculate_asysd_performance_contract(
                dataset.gold_removed, comparison.gold_preferred_reproduction.predicted_removed
            )
            contract_payload = {
                'dataset_id': spec.id,
                'official_metric_positive_class': 'Duplicate',
                'official_metric_negative_class': 'Unique',
                'blind_engine_quality': blind_contract.to_dict(),
                'gold_preferred_reproduction': reproduction_contract.to_dict(),
                'same_predicted_partition': True,
                'gold_preferred_uses_reference_labels_for_retention_only': True,
            }
            (out/'asysd_metric_contract.json').write_text(
                json.dumps(contract_payload, indent=2, ensure_ascii=False), encoding='utf-8'
            )
            for mode, contract in (
                ('blind_engine_quality', blind_contract),
                ('gold_preferred_reproduction', reproduction_contract),
            ):
                row={'dataset_id':spec.id,'mode':mode, **contract.to_dict()}
                asysd_compatibility_rows.append(row)

            # If the same source file also exposes a verified duplicate/publication
            # group column (e.g. duplicate_id), evaluate the partition as a
            # representative-insensitive secondary endpoint. Never assume such a
            # column exists merely because the file carries removal labels.
            try:
                partition=ExternalGoldDataset.from_delimited(source, name=spec.id+'__partition_secondary')
            except (ValueError, KeyError):
                partition=None
            if partition is not None:
                integrity=validate_external_dataset(partition, spec, strict=False)
                if integrity.passed:
                    partition_result=DedupPartitionBenchmark.evaluate(partition, engine=engine)
                    partition_dir=out/'partition_secondary'
                    write_external_validation_result(
                        partition_result, partition_dir, dataset=partition, specification=spec
                    )
                    secondary_artifacts.append({
                        'dataset_id':spec.id,
                        'type':'representative_insensitive_partition',
                        'uses_gold_labels':False,
                        'group_column':partition.group_column,
                        'directory':str(partition_dir),
                    })
                else:
                    secondary_artifacts.append({
                        'dataset_id':spec.id,
                        'type':'partition_secondary_not_run',
                        'reason':'detected group column failed pre-specified count integrity checks',
                        'mismatches':list(integrity.mismatches),
                    })

            m=result.metrics
            summary=ExternalRunSummary(
                dataset_id=spec.id, role=spec.role, gold_standard_type='removal_label',
                input_records=m.input_records,
                gold_duplicates_removed=m.gold_duplicates_removed,
                predicted_duplicates_removed=m.predicted_duplicates_removed,
                removed_singulars=m.removed_singulars,
                missed_duplicates=m.missed_duplicates,
                sensitivity_or_duplicate_recall=m.sensitivity,
                specificity_or_singular_retention=m.specificity,
                source_sha256=_sha256(source), result_directory=str(out),
            )
        elif isinstance(dataset, ExternalGoldDataset):
            result=DedupPartitionBenchmark.evaluate(dataset, engine=engine)
            write_external_validation_result(result, out, dataset=dataset, specification=spec)
            m=result.metrics
            summary=ExternalRunSummary(
                dataset_id=spec.id, role=spec.role, gold_standard_type='partition_group',
                input_records=m.input_records,
                gold_duplicates_removed=m.gold_duplicates_removed,
                predicted_duplicates_removed=m.predicted_duplicates_removed,
                removed_singulars=m.removed_singulars,
                missed_duplicates=m.missed_duplicates,
                sensitivity_or_duplicate_recall=m.duplicate_recall,
                specificity_or_singular_retention=m.singular_retention,
                source_sha256=_sha256(source), result_directory=str(out),
            )
        else:  # pragma: no cover
            raise TypeError(type(dataset))
        summaries.append(summary)

    rows=[s.to_dict() for s in summaries]
    (output_directory/'external_validation_summary.json').write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    csv_path=output_directory/'external_validation_summary.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as h:
        if rows:
            w=csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        else:
            h.write('dataset_id,role,gold_standard_type\n')
    compat_json = output_directory/'asysd_compatibility_summary.json'
    compat_json.write_text(json.dumps(asysd_compatibility_rows, indent=2, ensure_ascii=False), encoding='utf-8')
    compat_csv = output_directory/'asysd_compatibility_summary.csv'
    with compat_csv.open('w', newline='', encoding='utf-8') as h:
        if asysd_compatibility_rows:
            w=csv.DictWriter(h, fieldnames=list(asysd_compatibility_rows[0])); w.writeheader(); w.writerows(asysd_compatibility_rows)
        else:
            h.write('dataset_id,mode,true_negative,true_positive,false_negative,false_positive,sensitivity_percent,specificity_percent\n')

    run_manifest={
        'schema_version':'1.0',
        'source_manifest':str(manifest_path),
        'source_manifest_sha256':_sha256(manifest_path),
        'roles_requested':sorted(allowed),
        'allow_held_out':allow_held_out,
        'datasets_executed':[s.dataset_id for s in summaries],
        'primary_removal_retention_mode':'engine_quality_blind_to_gold',
        'secondary_artifacts':secondary_artifacts,
        'third_party_records_redistributed':False,
        'asysd_compatibility_summary_json':compat_json.name,
        'asysd_compatibility_summary_csv':compat_csv.name,
    }
    (output_directory/'external_validation_run_manifest.json').write_text(
        json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return summaries
