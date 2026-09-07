from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from metaevidence import (
    ExternalDatasetSpecification,
    ExternalRemovalGoldDataset,
    RemovalLabelBenchmark,
    load_external_gold_dataset,
    validate_external_dataset,
)
from metaevidence.external_sources import OSFPublicFileFetcher


def _write_asysd_like(path: Path) -> None:
    rows = [
        {"record_id":"1","title":"Bayesian networks in diabetes","author":"Smith J","year":"2024","journal":"J Med","doi":"10.1/a","label":"Unique"},
        {"record_id":"2","title":"Bayesian networks in diabetes","author":"J Smith","year":"2024","journal":"J Med","doi":"https://doi.org/10.1/a","label":"Duplicate"},
        {"record_id":"3","title":"Unrelated trial","author":"Jones A","year":"2023","journal":"Other","doi":"10.1/b","label":"Unique"},
    ]
    with path.open("w", newline="", encoding="utf-8") as h:
        w=csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def test_asysd_removal_loader_and_metrics(tmp_path):
    path=tmp_path/"Diabetes_duplicates_labelled.csv"
    _write_asysd_like(path)
    ds=ExternalRemovalGoldDataset.from_delimited(path)
    assert ds.n_records == 3
    assert ds.n_gold_duplicates_removed == 1
    assert ds.n_gold_publications == 2
    result=RemovalLabelBenchmark.evaluate(ds)
    assert result.metrics.true_positive == 1
    assert result.metrics.false_positive == 0
    assert result.metrics.false_negative == 0
    assert result.metrics.sensitivity == 1.0
    assert result.metrics.specificity == 1.0


def test_manifest_dispatches_removal_label_and_integrity(tmp_path):
    path=tmp_path/"gold.csv"; _write_asysd_like(path)
    spec=ExternalDatasetSpecification(
        id="toy", role="development", source="test", filename="gold.csv",
        gold_standard_type="removal_label", expected_records=3,
        expected_gold_duplicates_removed=1, expected_gold_publications=2,
    )
    ds=load_external_gold_dataset(path, spec, strict=True)
    assert isinstance(ds, ExternalRemovalGoldDataset)
    assert validate_external_dataset(ds, spec).passed


def test_unknown_removal_label_fails(tmp_path):
    path=tmp_path/"bad.csv"
    path.write_text("record_id,title,label\n1,A,Maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown removal gold label"):
        ExternalRemovalGoldDataset.from_delimited(path)


class _Response:
    def __init__(self, payload: bytes): self.payload=payload; self.pos=0
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n=-1):
        if n < 0:
            out=self.payload[self.pos:]; self.pos=len(self.payload); return out
        out=self.payload[self.pos:self.pos+n]; self.pos += len(out); return out


def test_osf_fetcher_walks_folder_and_writes_hash_manifest(tmp_path):
    root="https://api.osf.io/v2/nodes/node123/files/osfstorage/?page%5Bsize%5D=100"
    child="https://api.osf.io/v2/files/folder123/children/"
    d1="https://files.example/a.csv"; d2="https://files.example/b.csv"
    root_payload={"data":[
        {"id":"file1","attributes":{"name":"A.csv","kind":"file"},"links":{"download":d1}},
        {"id":"folder123","attributes":{"name":"nested","kind":"folder"},"relationships":{"files":{"links":{"related":{"href":child}}}}},
    ],"links":{"next":None}}
    child_payload={"data":[
        {"id":"file2","attributes":{"name":"B.csv","kind":"file"},"links":{"download":d2}}
    ],"links":{"next":None}}
    payloads={root:json.dumps(root_payload).encode(), child:json.dumps(child_payload).encode(), d1:b"a,b\n1,2\n", d2:b"x,y\n3,4\n"}
    def fake_urlopen(request, timeout=0):
        url=request.full_url
        assert url in payloads
        return _Response(payloads[url])
    fetcher=OSFPublicFileFetcher(urlopen_fn=fake_urlopen)
    rows=fetcher.fetch("node123", ("A.csv","B.csv"), tmp_path)
    assert [r.name for r in rows] == ["A.csv","B.csv"]
    assert all(len(r.sha256)==64 for r in rows)
    manifest=json.loads((tmp_path/"external_source_manifest.json").read_text())
    assert manifest["node_id"] == "node123"
    assert len(manifest["files"]) == 2


def test_external_runner_protects_heldout_and_runs_development(tmp_path):
    from metaevidence.external_runner import run_external_validation_plan
    data=tmp_path/"data"; data.mkdir()
    dev=data/"dev.csv"; _write_asysd_like(dev)
    held=data/"held.csv"; _write_asysd_like(held)
    manifest=tmp_path/"plan.json"
    manifest.write_text(json.dumps({"datasets":[
        {"id":"dev","task":"publication_deduplication","role":"development","source":"test","filename":"dev.csv","gold_standard_type":"removal_label","expected_records":3,"expected_gold_duplicates_removed":1,"expected_gold_publications":2},
        {"id":"held","task":"publication_deduplication","role":"held_out_test","source":"test","filename":"held.csv","gold_standard_type":"removal_label","expected_records":3,"expected_gold_duplicates_removed":1,"expected_gold_publications":2},
    ]}), encoding="utf-8")
    out=tmp_path/"out"
    rows=run_external_validation_plan(manifest,data,out,roles=("development",))
    assert [r.dataset_id for r in rows] == ["dev"]
    assert (out/"dev"/"external_validation_manifest.json").exists()
    assert not (out/"held").exists()
    with pytest.raises(PermissionError):
        run_external_validation_plan(manifest,data,tmp_path/"bad",roles=("held_out_test",))


def _write_retention_sensitive(path: Path, *, include_group: bool = False) -> None:
    fieldnames = ["record_id","title","author","year","journal","doi","abstract","label"]
    if include_group:
        fieldnames.append("duplicate_id")
    rows = [
        {"record_id":"U1","title":"Same publication","author":"Smith J","year":"2024","journal":"J Med","doi":"10.1/x","abstract":"","label":"Unique"},
        {"record_id":"D1","title":"Same publication","author":"Smith J; Jones A","year":"2024","journal":"J Med","doi":"10.1/x","abstract":"A much richer abstract that makes this record the engine-quality representative.","label":"Duplicate"},
        {"record_id":"U2","title":"Independent publication","author":"Brown B","year":"2023","journal":"Other","doi":"10.1/y","abstract":"","label":"Unique"},
    ]
    if include_group:
        rows[0]["duplicate_id"]="PUB-1"
        rows[1]["duplicate_id"]="PUB-1"
        rows[2]["duplicate_id"]="PUB-2"
    with path.open("w", newline="", encoding="utf-8") as h:
        w=csv.DictWriter(h, fieldnames=fieldnames); w.writeheader(); w.writerows(rows)


def test_retention_comparison_separates_blind_from_gold_preferred(tmp_path):
    path=tmp_path/"retention.csv"; _write_retention_sensitive(path)
    ds=ExternalRemovalGoldDataset.from_delimited(path)
    comparison=RemovalLabelBenchmark.compare_retention_modes(ds)
    blind=comparison.blind.metrics
    repro=comparison.gold_preferred_reproduction.metrics
    # Blind deployment keeps the richer gold-Duplicate record and therefore gets
    # the representative-sensitive labels wrong even though the cluster is right.
    assert blind.false_positive == 1
    assert blind.false_negative == 1
    # ASySD-compatible reproduction uses the reference Unique label only to select
    # the representative in that already-predicted cluster.
    assert repro.false_positive == 0
    assert repro.false_negative == 0
    assert comparison.reproduction_uses_gold_labels


def test_external_runner_writes_retention_reproduction_and_partition_secondary(tmp_path):
    from metaevidence.external_runner import run_external_validation_plan
    data=tmp_path/"data"; data.mkdir()
    source=data/"dev.csv"; _write_retention_sensitive(source, include_group=True)
    manifest=tmp_path/"plan.json"
    manifest.write_text(json.dumps({"datasets":[
        {"id":"dev","task":"publication_deduplication","role":"development","source":"test",
         "filename":"dev.csv","gold_standard_type":"removal_label","expected_records":3,
         "expected_gold_duplicates_removed":1,"expected_gold_publications":2}
    ]}), encoding="utf-8")
    out=tmp_path/"out"
    rows=run_external_validation_plan(manifest,data,out,roles=("development",))
    assert len(rows)==1
    assert (out/"dev"/"retention_reproduction"/"retention_mode_comparison.json").exists()
    assert (out/"dev"/"partition_secondary"/"external_dedup_metrics.json").exists()
    run_manifest=json.loads((out/"external_validation_run_manifest.json").read_text())
    types={x["type"] for x in run_manifest["secondary_artifacts"]}
    assert "gold_preferred_retention_reproduction" in types
    assert "representative_insensitive_partition" in types
