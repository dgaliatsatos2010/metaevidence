from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_losslessly(raw: bytes) -> tuple[str, str]:
    # This is an I/O-compatibility transform only. It never parses columns or labels.
    # Prefer Unicode encodings; fall back to common Windows-1252 used by bibliographic exports.
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", raw, 0, 1, "no supported lossless text decoding")


def normalize_directory(source_dir: Path, output_dir: Path) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for source in sorted(source_dir.glob("*.csv")):
        raw = source.read_bytes()
        text, detected = _decode_losslessly(raw)
        normalized = text.encode("utf-8-sig")
        target = output_dir / source.name
        target.write_bytes(normalized)
        rows.append({
            "filename": source.name,
            "source_sha256": _sha256(raw),
            "source_size_bytes": len(raw),
            "detected_encoding": detected,
            "normalized_encoding": "utf-8-sig",
            "normalized_sha256": _sha256(normalized),
            "normalized_size_bytes": len(normalized),
        })
    if not rows:
        raise SystemExit(f"No CSV files found in {source_dir}")
    manifest = {
        "schema_version": "MetaEvidence-ASySD-encoding-normalization-1",
        "purpose": "Lossless text-encoding normalization only; no CSV columns or gold labels are parsed or inspected.",
        "files": rows,
    }
    (output_dir / "encoding_normalization_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    rows = normalize_directory(args.source_dir, args.output_dir)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
