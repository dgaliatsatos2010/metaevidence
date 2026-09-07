from __future__ import annotations

from pathlib import Path

import pytest

from metaevidence import (
    ConfidenceDeduplicationEngine,
    EndNoteXMLGoldReader,
    RemovalLabelBenchmark,
    load_endnote_xml_gold,
)


def _write_xml(path: Path, caption_second: str = "Duplicate") -> Path:
    path.write_text(
        f'''<?xml version="1.0" encoding="UTF-8"?>
<xml><records>
<record>
  <database>PubMed</database><rec-number>101</rec-number><ref-type>Journal Article</ref-type>
  <contributors><authors><author><style>Smith, J.</style></author><author><style>Doe, A.</style></author></authors></contributors>
  <titles><title><style>Machine learning for diabetes prediction</style></title><secondary-title><style>Example Journal</style></secondary-title></titles>
  <periodical><full-title><style>Example Journal</style></full-title></periodical>
  <pages><style>10-20</style></pages><volume><style>5</style></volume><number><style>2</style></number>
  <dates><year><style>2024</style></year></dates><accession-num><style>12345678</style></accession-num>
  <abstract><style>First abstract.</style></abstract>
  <electronic-resource-num><style>https://doi.org/10.1000/test</style></electronic-resource-num>
</record>
<record>
  <database>Scopus</database><rec-number>202</rec-number><ref-type>Journal Article</ref-type>
  <contributors><authors><author><style>J Smith</style></author><author><style>A Doe</style></author></authors></contributors>
  <titles><title><style>Machine-learning for diabetes prediction</style></title><secondary-title><style>Example Journal</style></secondary-title></titles>
  <pages><style>10-20</style></pages><volume><style>5</style></volume><number><style>2</style></number>
  <dates><year><style>2024</style></year></dates>
  <electronic-resource-num><style>10.1000/TEST</style></electronic-resource-num>
  <caption><style>{caption_second}</style></caption>
</record>
</records></xml>''',
        encoding="utf-8",
    )
    return path


def test_streaming_endnote_reader_maps_gold_and_metadata(tmp_path: Path):
    path = _write_xml(tmp_path / "gold.xml")
    imported = load_endnote_xml_gold(path, name="real_structure_fixture")
    ds = imported.dataset
    assert ds.n_records == 2
    assert ds.gold_removed == [False, True]
    assert ds.n_gold_duplicates_removed == 1
    assert ds.record_ids == ["101", "202"]
    assert ds.records[0].authors == ["Smith, J.", "Doe, A."]
    assert ds.records[0].journal == "Example Journal"
    assert ds.records[0].year == 2024
    assert ds.records[0].pmid == "12345678"
    assert ds.records[0].doi == "10.1000/test"
    assert ds.records[0].metadata["volume"] == "5"
    assert ds.records[0].metadata["issue"] == "2"
    assert imported.stats.records == 2
    assert imported.stats.duplicates_removed == 1
    assert len(imported.stats.sha256) == 64


def test_gold_caption_is_not_a_matching_feature(tmp_path: Path):
    path = _write_xml(tmp_path / "gold.xml")
    ds = load_endnote_xml_gold(path).dataset
    engine = ConfidenceDeduplicationEngine()
    assessment = engine.assess_pair(ds.records[0], ds.records[1])
    features = assessment.features.to_dict()
    assert not any("gold" in key or "caption" in key for key in features)
    result = RemovalLabelBenchmark.evaluate(ds, engine=engine, retention_mode="engine_quality")
    assert result.metrics.input_records == 2
    assert result.metrics.gold_duplicates_removed == 1


def test_unknown_caption_fails_closed_by_default(tmp_path: Path):
    path = _write_xml(tmp_path / "bad.xml", caption_second="Maybe Duplicate")
    with pytest.raises(ValueError, match="Unrecognised EndNote caption"):
        EndNoteXMLGoldReader().read(path)


def test_unknown_caption_can_be_audited_non_strict(tmp_path: Path):
    path = _write_xml(tmp_path / "non_strict.xml", caption_second="Needs review")
    imported = EndNoteXMLGoldReader(strict_captions=False).read(path)
    assert imported.dataset.gold_removed == [False, False]
    assert imported.stats.unrecognised_captions == ("Needs review",)
    assert imported.warnings


def test_pinned_github_fetcher_verifies_git_blob_and_size(tmp_path: Path):
    from metaevidence.external_sources import GitHubPinnedFileFetcher
    import hashlib
    import io

    payload = b"benchmark bytes\n"
    git_sha = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()

    class Response(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()

    def fake_urlopen(request, timeout=0):
        assert "raw.githubusercontent.com" in request.full_url
        return Response(payload)

    fetcher = GitHubPinnedFileFetcher(urlopen_fn=fake_urlopen)
    files = fetcher.fetch_pinned(
        repository="owner/repo",
        commit="abc123",
        files={"x.xml": {"git_blob_sha": git_sha, "size_bytes": len(payload)}},
        repository_prefix="data",
        destination=tmp_path,
    )
    assert len(files) == 1
    assert (tmp_path / "x.xml").read_bytes() == payload
    assert (tmp_path / "external_source_manifest.json").is_file()


def test_pinned_github_fetcher_deletes_corrupt_download(tmp_path: Path):
    from metaevidence.external_sources import GitHubPinnedFileFetcher
    import io

    payload = b"wrong"

    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()

    fetcher = GitHubPinnedFileFetcher(urlopen_fn=lambda *a, **k: Response(payload))
    with pytest.raises(ValueError, match="Size mismatch"):
        fetcher.fetch_pinned(
            repository="owner/repo",
            commit="abc123",
            files={"x.xml": {"git_blob_sha": "0" * 40, "size_bytes": 999}},
            repository_prefix="data",
            destination=tmp_path,
        )
    assert not (tmp_path / "x.xml").exists()


def test_beller_subset_fetch_passes_only_selected_manifest_entry(tmp_path: Path):
    from metaevidence.external_sources import fetch_beller_endnote_validation_files

    captured = {}

    class FakeFetcher:
        def fetch_pinned(self, **kwargs):
            captured.update(kwargs)
            return []

    fetch_beller_endnote_validation_files(
        tmp_path,
        names=("tafenoquine.xml",),
        fetcher=FakeFetcher(),
    )
    assert tuple(captured["files"]) == ("tafenoquine.xml",)
    assert captured["repository_prefix"] == "test/data"


def test_beller_subset_rejects_unknown_filename(tmp_path: Path):
    from metaevidence.external_sources import fetch_beller_endnote_validation_files

    class FakeFetcher:
        def fetch_pinned(self, **kwargs):  # pragma: no cover - should not be reached
            raise AssertionError("invalid filename should fail before network fetch")

    with pytest.raises(ValueError, match="Unknown pinned EndNote benchmark file"):
        fetch_beller_endnote_validation_files(
            tmp_path,
            names=("not-a-gold-file.xml",),
            fetcher=FakeFetcher(),
        )


def test_external_validation_workflow_is_manual_and_contains_held_out_gate():
    workflow = Path(__file__).parents[1] / ".github" / "workflows" / "external-validation.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "confirm_held_out" in text
    assert "Held-out ASySD validation requires confirm_held_out=true" in text
    assert "fetch-beller-endnote" in text
    assert "validate-beller-endnote" in text
    assert "raw third-party" in text


def test_validation_lock_cli_passes_on_frozen_repository(capsys):
    from pathlib import Path
    from metaevidence.cli import main

    root = Path(__file__).parents[1]
    rc = main([
        "verify-validation-lock",
        str(root / "benchmarks" / "frozen_validation_lock.json"),
        "--repository-root", str(root),
    ])
    assert rc == 0
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["ok"] is True
