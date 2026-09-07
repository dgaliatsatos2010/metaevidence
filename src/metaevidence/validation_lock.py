from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ValidationLockCheck:
    path: str
    role: str
    expected_sha256: str
    observed_sha256: str | None
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationLockReport:
    schema_version: str
    runner_version: str
    frozen_engine_version: str
    lock_file: str
    checks: tuple[ValidationLockCheck, ...]

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "runner_version": self.runner_version,
            "frozen_engine_version": self.frozen_engine_version,
            "lock_file": self.lock_file,
            "ok": self.ok,
            "checks": [check.to_dict() for check in self.checks],
        }


def sha256_file(path: str | Path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_entries(payload: dict[str, object]) -> Iterable[dict[str, str]]:
    groups = ("locked_method_files", "locked_benchmark_manifests", "locked_runner_files")
    found = False
    for group in groups:
        raw = payload.get(group, [])
        if not isinstance(raw, list):
            raise ValueError(f"Validation lock field {group!r} must be a list")
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError(f"Validation lock entry in {group!r} must be an object")
            path = str(item.get("path", "")).strip()
            role = str(item.get("role", "")).strip()
            expected = str(item.get("sha256", "")).strip().lower()
            if not path or not role or len(expected) != 64:
                raise ValueError(f"Invalid validation lock entry in {group!r}: {item!r}")
            found = True
            yield {"path": path, "role": role, "sha256": expected}
    if not found:
        raise ValueError("Validation lock contains no files")


def verify_frozen_validation_lock(
    lock_file: str | Path,
    repository_root: str | Path = ".",
    *,
    raise_on_failure: bool = True,
) -> ValidationLockReport:
    """Verify that frozen method/benchmark files match their preregistered hashes.

    This is a pre-execution integrity gate. It deliberately performs no benchmark
    scoring and does not inspect gold outcomes.
    """
    lock_file = Path(lock_file)
    root = Path(repository_root)
    payload = json.loads(lock_file.read_text(encoding="utf-8"))
    checks: list[ValidationLockCheck] = []
    for entry in _iter_entries(payload):
        relative = entry["path"]
        target = root / relative
        if not target.is_file():
            checks.append(ValidationLockCheck(
                path=relative,
                role=entry["role"],
                expected_sha256=entry["sha256"],
                observed_sha256=None,
                ok=False,
                error="file_missing",
            ))
            continue
        observed = sha256_file(target)
        checks.append(ValidationLockCheck(
            path=relative,
            role=entry["role"],
            expected_sha256=entry["sha256"],
            observed_sha256=observed,
            ok=observed == entry["sha256"],
            error=None if observed == entry["sha256"] else "sha256_mismatch",
        ))

    report = ValidationLockReport(
        schema_version=str(payload.get("schema_version", "")),
        runner_version=str(payload.get("validation_runner_version", "")),
        frozen_engine_version=str(payload.get("frozen_engine_version", "")),
        lock_file=str(lock_file),
        checks=tuple(checks),
    )
    if raise_on_failure and not report.ok:
        failures = ", ".join(
            f"{c.path} ({c.error})" for c in report.checks if not c.ok
        )
        raise RuntimeError(f"Frozen external-validation lock failed: {failures}")
    return report
