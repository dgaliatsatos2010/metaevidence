#!/usr/bin/env python3
"""Repository-level integrity gate for frozen external validation.

This script intentionally runs before package installation in GitHub Actions. It
adds ``src`` to sys.path, verifies SHA-256 locks, prints a JSON audit record, and
returns a non-zero exit status on any drift.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("benchmarks/frozen_validation_lock.json"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()

    root = args.repository_root.resolve()
    # Load the stdlib-only verifier directly so this pre-install gate cannot be
    # blocked by package dependencies that have not yet been installed.
    import importlib.util
    module_path = root / "src" / "metaevidence" / "validation_lock.py"
    spec = importlib.util.spec_from_file_location("metaevidence_frozen_validation_lock", module_path)
    if spec is None or spec.loader is None:
        print(json.dumps({"ok": False, "error": f"Cannot load {module_path}"}, indent=2), file=sys.stderr)
        return 66
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    verify_frozen_validation_lock = module.verify_frozen_validation_lock

    try:
        report = verify_frozen_validation_lock(args.lock, root, raise_on_failure=True)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 65
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
