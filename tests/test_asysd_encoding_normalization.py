from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).parents[1] / "benchmarks" / "normalize_asysd_encoding.py"
    spec = importlib.util.spec_from_file_location("normalize_asysd_encoding", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cp1252_is_normalized_losslessly(tmp_path):
    mod = _load_module()
    source = tmp_path / "raw"
    output = tmp_path / "utf8"
    source.mkdir()
    text = 'Title,Label\n"Copyright © example",Unique\n'
    (source / "sample.csv").write_bytes(text.encode("cp1252"))
    rows = mod.normalize_directory(source, output)
    assert rows[0]["detected_encoding"] == "cp1252"
    assert (output / "sample.csv").read_text(encoding="utf-8-sig") == text
    manifest = json.loads((output / "encoding_normalization_manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"][0]["filename"] == "sample.csv"


def test_utf8_is_preserved_as_text(tmp_path):
    mod = _load_module()
    source = tmp_path / "raw"
    output = tmp_path / "utf8"
    source.mkdir()
    text = 'Title,Label\n"Café",Duplicate\n'
    (source / "sample.csv").write_bytes(text.encode("utf-8"))
    mod.normalize_directory(source, output)
    assert (output / "sample.csv").read_text(encoding="utf-8-sig") == text
