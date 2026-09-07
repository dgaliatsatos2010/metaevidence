from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

from .validation_lock import sha256_file, verify_frozen_validation_lock


def _hash_tree(root: Path, *, exclude: set[Path] | None = None) -> list[dict[str, object]]:
    excluded = {p.resolve() for p in (exclude or set())}
    rows: list[dict[str, object]] = []
    if not root.exists():
        return rows
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.resolve() in excluded:
            continue
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        })
    return rows


def write_validation_run_manifest(
    output_file: str | Path,
    *,
    results_root: str | Path,
    lock_file: str | Path,
    repository_root: str | Path,
    benchmark: str,
    selection: str,
    software_version: str,
) -> dict[str, object]:
    """Write provenance for one already-computed external-validation result tree.

    The function verifies the frozen lock first and hashes result artifacts only;
    it never reads or redistributes third-party raw benchmark records.
    """
    output = Path(output_file)
    results = Path(results_root)
    lock = Path(lock_file)
    root = Path(repository_root)
    report = verify_frozen_validation_lock(lock, root, raise_on_failure=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    github_env_keys = (
        "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW", "GITHUB_JOB",
    )
    github = {key.lower(): os.environ[key] for key in github_env_keys if os.environ.get(key)}
    payload: dict[str, object] = {
        "schema_version": "MetaEvidence-validation-run-1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark": str(benchmark),
        "selection": str(selection),
        "metaevidence_version": str(software_version),
        "python_version": sys.version,
        "platform": platform.platform(),
        "frozen_validation_lock": {
            "path": str(lock),
            "sha256": sha256_file(lock),
            "ok": report.ok,
            "frozen_engine_version": report.frozen_engine_version,
        },
        "github": github,
        "result_files": _hash_tree(results, exclude={output}),
        "raw_third_party_data_included": False,
    }
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
