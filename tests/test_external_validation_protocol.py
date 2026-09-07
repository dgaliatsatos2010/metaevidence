

def test_frozen_validation_lock_matches_repository_bytes():
    from pathlib import Path
    from metaevidence.validation_lock import verify_frozen_validation_lock

    root = Path(__file__).parents[1]
    report = verify_frozen_validation_lock(
        root / "benchmarks" / "frozen_validation_lock.json", root
    )
    assert report.ok
    locked = {check.path: check.expected_sha256 for check in report.checks}
    assert locked["src/metaevidence/dedup.py"] == (
        "3dfe93fb3b1a495a6e26ddca8ab0ab4b0f64bac047de3de07d1d5f1f893dca50"
    )


def test_frozen_validation_lock_fails_closed_on_tampering(tmp_path):
    import hashlib
    import json
    from metaevidence.validation_lock import verify_frozen_validation_lock

    target = tmp_path / "engine.py"
    target.write_text("frozen\n", encoding="utf-8")
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({
        "schema_version": "test",
        "validation_runner_version": "test",
        "frozen_engine_version": "test",
        "locked_method_files": [{
            "path": "engine.py", "role": "test engine", "sha256": expected
        }],
        "locked_benchmark_manifests": [],
    }), encoding="utf-8")
    assert verify_frozen_validation_lock(lock, tmp_path).ok
    target.write_text("changed\n", encoding="utf-8")
    import pytest
    with pytest.raises(RuntimeError, match="Frozen external-validation lock failed"):
        verify_frozen_validation_lock(lock, tmp_path)


def test_external_validation_workflow_derives_beller_matrix_from_manifest():
    from pathlib import Path

    workflow = Path(__file__).parents[1] / ".github" / "workflows" / "external-validation.yml"
    text = workflow.read_text(encoding="utf-8")
    assert 'Path("benchmarks/beller_endnote_manifest.json")' in text
    assert 'manifest["files"]' in text
    assert "Build pinned EndNote matrix directly from frozen manifest" in text
    assert "all_files = [\n              \"blue-light.xml\"" not in text
    assert "verify_frozen_validation.py" in text


def test_validation_run_manifest_hashes_results_without_raw_data(tmp_path):
    from pathlib import Path
    from metaevidence.validation_provenance import write_validation_run_manifest

    root = Path(__file__).parents[1]
    results = tmp_path / "results"
    results.mkdir()
    (results / "metrics.json").write_text('{"sensitivity": 0.9}\n', encoding="utf-8")
    out = results / "provenance" / "validation_run_manifest.json"
    payload = write_validation_run_manifest(
        out,
        results_root=results,
        lock_file=root / "benchmarks" / "frozen_validation_lock.json",
        repository_root=root,
        benchmark="beller-secondary",
        selection="tafenoquine.xml",
        software_version="0.9.9.dev0",
    )
    assert payload["raw_third_party_data_included"] is False
    assert payload["frozen_validation_lock"]["ok"] is True
    assert [row["path"] for row in payload["result_files"]] == ["metrics.json"]
    assert out.is_file()


def test_beller_python_constants_match_frozen_manifest():
    import json
    from pathlib import Path
    from metaevidence.external_sources import (
        BELLER_ENDNOTE_COMMIT,
        BELLER_ENDNOTE_FILES,
        BELLER_ENDNOTE_REPOSITORY,
    )

    root = Path(__file__).parents[1]
    manifest = json.loads((root / "benchmarks" / "beller_endnote_manifest.json").read_text(encoding="utf-8"))
    expected = {
        item["name"]: {"git_blob_sha": item["git_blob_sha"], "size_bytes": item["size_bytes"]}
        for item in manifest["files"]
    }
    assert manifest["repository"] == BELLER_ENDNOTE_REPOSITORY
    assert manifest["commit"] == BELLER_ENDNOTE_COMMIT
    assert manifest["repository_path"] == "test/data"
    assert expected == BELLER_ENDNOTE_FILES
