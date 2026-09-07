import hashlib
import json
from pathlib import Path


def test_asysd_neuroimaging_integrity_metadata_matches_published_denominator():
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "benchmarks" / "external_benchmark_manifest.json").read_text(encoding="utf-8")
    )
    spec = next(d for d in manifest["datasets"] if d["id"] == "asysd_neuroimaging")
    assert spec["expected_records"] == 3438
    assert spec["expected_gold_duplicates_removed"] == 1298
    assert spec["expected_gold_publications"] == 2140
    assert spec["expected_records"] == (
        spec["expected_gold_duplicates_removed"] + spec["expected_gold_publications"]
    )
    amendments = manifest.get("integrity_metadata_amendments", [])
    assert any(a.get("dataset_id") == "asysd_neuroimaging" for a in amendments)


def test_frozen_engine_hash_is_unchanged_in_v0911():
    root = Path(__file__).parents[1]
    observed = hashlib.sha256(
        (root / "src" / "metaevidence" / "dedup.py").read_bytes()
    ).hexdigest()
    assert observed == "3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50"
