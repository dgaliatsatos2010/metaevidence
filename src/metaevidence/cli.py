from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .external_runner import run_external_validation_plan
from .external_sources import fetch_asysd_validation_files, fetch_beller_endnote_validation_files, verify_beller_endnote_validation_files, BELLER_ENDNOTE_FILES
from .endnote_gold import load_endnote_xml_gold
from .external_validation import RemovalLabelBenchmark, write_external_removal_validation_result, write_removal_retention_comparison
from .asysd_compat import calculate_asysd_performance_contract
from .statistical_reporting import summarize_removal_result_directory
from .validation_lock import verify_frozen_validation_lock
from .validation_provenance import write_validation_run_manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metaevidence",
        description="MetaEvidence command-line utilities for reproducible evidence workflows.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser(
        "fetch-asysd",
        help="Fetch the five official ASySD validation CSVs from OSF node 2b8uq.",
    )
    fetch.add_argument("destination", type=Path)
    fetch.add_argument("--overwrite", action="store_true")

    validate = sub.add_parser(
        "validate-asysd",
        help="Run the frozen MetaEvidence external-validation plan on local ASySD files.",
    )
    validate.add_argument("manifest", type=Path)
    validate.add_argument("data_directory", type=Path)
    validate.add_argument("output_directory", type=Path)
    validate.add_argument(
        "--role",
        action="append",
        dest="roles",
        choices=("development", "calibration", "held_out_test"),
        help="Dataset role to execute. Repeat for multiple roles. Defaults to development+calibration.",
    )
    validate.add_argument(
        "--allow-held-out",
        action="store_true",
        help="Explicitly unlock held-out test datasets. Do not use during development/tuning.",
    )

    endnote = sub.add_parser(
        "validate-endnote-gold",
        help="Validate MetaEvidence on an EndNote XML corpus whose caption 'Duplicate' is gold truth.",
    )
    endnote.add_argument("xml_file", type=Path)
    endnote.add_argument("output_directory", type=Path)
    endnote.add_argument("--name", default=None)
    endnote.add_argument("--duplicate-caption", default="Duplicate")
    endnote.add_argument(
        "--allow-unknown-captions",
        action="store_true",
        help="Audit unknown nonblank captions as retained instead of failing closed.",
    )

    fetch_beller = sub.add_parser(
        "fetch-beller-endnote",
        help="Fetch the five pinned public EndNote XML validation corpora from IEBH/dedupe-sweep.",
    )
    fetch_beller.add_argument("destination", type=Path)
    fetch_beller.add_argument("--overwrite", action="store_true")
    fetch_beller.add_argument(
        "--file", action="append", dest="files", choices=tuple(BELLER_ENDNOTE_FILES),
        help="Fetch only one pinned XML file. Repeat to fetch multiple files. Defaults to all five.",
    )

    validate_beller = sub.add_parser(
        "validate-beller-endnote",
        help="Run blind MetaEvidence validation on all five local pinned EndNote XML corpora.",
    )
    validate_beller.add_argument("data_directory", type=Path)
    validate_beller.add_argument("output_directory", type=Path)
    validate_beller.add_argument(
        "--file", action="append", dest="files", choices=tuple(BELLER_ENDNOTE_FILES),
        help="Validate only one pinned XML file. Repeat for multiple files. Defaults to all five.",
    )

    lock = sub.add_parser(
        "verify-validation-lock",
        help="Verify frozen external-validation method and manifest SHA-256 hashes before execution.",
    )
    lock.add_argument("lock_file", type=Path)
    lock.add_argument("--repository-root", type=Path, default=Path("."))

    provenance = sub.add_parser(
        "write-validation-run-manifest",
        help="Hash already-computed external-validation result artifacts and record frozen-run provenance.",
    )
    provenance.add_argument("output_file", type=Path)
    provenance.add_argument("results_root", type=Path)
    provenance.add_argument("--lock", type=Path, default=Path("benchmarks/frozen_validation_lock.json"))
    provenance.add_argument("--repository-root", type=Path, default=Path("."))
    provenance.add_argument("--benchmark", required=True)
    provenance.add_argument("--selection", required=True)

    summarize = sub.add_parser(
        "summarize-removal-results",
        help="Create publication-oriented statistical summaries from blind removal-validation results.",
    )
    summarize.add_argument("input_directory", type=Path)
    summarize.add_argument("output_directory", type=Path)
    summarize.add_argument("--confidence", type=float, default=0.95)
    summarize.add_argument("--bootstrap-replicates", type=int, default=5000)
    summarize.add_argument("--bootstrap-seed", type=int, default=20260907)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "fetch-asysd":
        files = fetch_asysd_validation_files(args.destination, overwrite=args.overwrite)
        print(json.dumps([f.to_dict() for f in files], indent=2, ensure_ascii=False))
        return 0

    if args.command == "validate-asysd":
        roles = tuple(args.roles or ("development", "calibration"))
        results = run_external_validation_plan(
            args.manifest,
            args.data_directory,
            args.output_directory,
            roles=roles,
            allow_held_out=args.allow_held_out,
        )
        print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
        return 0

    if args.command == "fetch-beller-endnote":
        files = fetch_beller_endnote_validation_files(
            args.destination, overwrite=args.overwrite, names=args.files
        )
        print(json.dumps([f.to_dict() for f in files], indent=2, ensure_ascii=False))
        return 0

    if args.command == "validate-beller-endnote":
        # Refuse benchmark execution on wrong or upstream-modified bytes.
        selected_files = tuple(args.files or BELLER_ENDNOTE_FILES)
        verify_beller_endnote_validation_files(args.data_directory, names=selected_files)
        args.output_directory.mkdir(parents=True, exist_ok=True)
        rows = []
        for filename in selected_files:
            source = args.data_directory / filename
            if not source.is_file():
                raise FileNotFoundError(f"Pinned EndNote validation file not found: {source}")
            imported = load_endnote_xml_gold(source, name=Path(filename).stem)
            result = RemovalLabelBenchmark.evaluate(imported.dataset, retention_mode="engine_quality")
            comparison = RemovalLabelBenchmark.compare_retention_modes(
                imported.dataset, deduplication_result=result.deduplication
            )
            out = args.output_directory / Path(filename).stem
            write_external_removal_validation_result(
                result, out / "blind_engine_quality", dataset=imported.dataset
            )
            write_removal_retention_comparison(
                comparison, out / "retention_reproduction", dataset=imported.dataset
            )
            contract = calculate_asysd_performance_contract(
                imported.dataset.gold_removed, result.predicted_removed
            )
            row = {
                "dataset": imported.dataset.name,
                "source_file": filename,
                "source_sha256": imported.stats.sha256,
                **result.metrics.to_dict(),
                "sensitivity_percent": contract.sensitivity_percent,
                "specificity_percent": contract.specificity_percent,
            }
            rows.append(row)
        (args.output_directory / "beller_endnote_validation_summary.json").write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if args.command == "verify-validation-lock":
        report = verify_frozen_validation_lock(args.lock_file, args.repository_root)
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "write-validation-run-manifest":
        from . import __version__
        payload = write_validation_run_manifest(
            args.output_file,
            results_root=args.results_root,
            lock_file=args.lock,
            repository_root=args.repository_root,
            benchmark=args.benchmark,
            selection=args.selection,
            software_version=__version__,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.command == "summarize-removal-results":
        report = summarize_removal_result_directory(
            args.input_directory, args.output_directory,
            confidence=args.confidence,
            bootstrap_replicates=args.bootstrap_replicates,
            bootstrap_seed=args.bootstrap_seed,
        )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "validate-endnote-gold":
        imported = load_endnote_xml_gold(
            args.xml_file,
            name=args.name,
            duplicate_caption=args.duplicate_caption,
            strict_captions=not args.allow_unknown_captions,
        )
        dataset = imported.dataset
        result = RemovalLabelBenchmark.evaluate(dataset, retention_mode="engine_quality")
        comparison = RemovalLabelBenchmark.compare_retention_modes(
            dataset, deduplication_result=result.deduplication
        )
        out = args.output_directory
        write_external_removal_validation_result(result, out / "blind_engine_quality", dataset=dataset)
        write_removal_retention_comparison(comparison, out / "retention_reproduction", dataset=dataset)
        payload = {
            "dataset": dataset.name,
            "import": imported.stats.to_dict(),
            "blind_engine_quality": result.metrics.to_dict(),
            "asysd_style_blind_contract": calculate_asysd_performance_contract(
                dataset.gold_removed, result.predicted_removed
            ).to_dict(),
            "gold_preferred_reproduction": comparison.gold_preferred_reproduction.metrics.to_dict(),
            "gold_label_used_by_engine": False,
        }
        out.mkdir(parents=True, exist_ok=True)
        (out / "endnote_gold_validation_summary.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
