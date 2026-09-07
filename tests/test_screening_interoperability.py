import csv
import json

import pytest

from metaevidence import (
    EvidenceRecord,
    ScreeningDecision,
    ScreeningLedger,
    ScreeningStage,
    SourceHit,
    StudyLinkageEngine,
    read_csv,
    read_ris,
    stable_record_id,
    write_asreview_csv,
    write_bibtex,
    write_csv,
    write_jsonl,
    write_ris,
    write_screening_bundle,
)


def sample_records():
    return [
        EvidenceRecord(
            title="Protocol of the ORBIT trial",
            authors=["Smith J", "Jones A"],
            year=2020,
            journal="Trials",
            abstract="Registered as NCT01234567.",
            doi="10.1000/orbit.protocol",
            source_hits=[SourceHit("pubmed", "1")],
            metadata={"report_role": "PROTOCOL"},
        ),
        EvidenceRecord(
            title="Primary results of ORBIT",
            authors=["J Smith", "Brown P"],
            year=2022,
            journal="Example Journal",
            abstract="ClinicalTrials.gov NCT01234567.",
            doi="10.1000/orbit.results",
            source_hits=[SourceHit("openalex", "W2")],
            metadata={"report_role": "PRIMARY_RESULTS"},
        ),
        EvidenceRecord(
            title="Unrelated study",
            authors=["Other A"],
            year=2021,
            abstract="Another study.",
        ),
    ]


def test_stable_record_id_prefers_doi_and_has_fallback():
    a = EvidenceRecord(title="A", doi="https://doi.org/10.1/X")
    b = EvidenceRecord(title="Fallback", authors=["Smith J"], year=2020)
    assert stable_record_id(a) == "DOI:10.1/x"
    assert stable_record_id(b).startswith("META:")
    assert stable_record_id(b) == stable_record_id(EvidenceRecord(title="Fallback", authors=["Smith J"], year=2020))


def test_full_text_exclusion_requires_reason():
    ledger = ScreeningLedger()
    with pytest.raises(ValueError):
        ledger.add("R1", ScreeningDecision.EXCLUDE, stage=ScreeningStage.FULL_TEXT)
    ledger.add("R1", ScreeningDecision.EXCLUDE, stage=ScreeningStage.FULL_TEXT, reason_code="WRONG_OUTCOME")
    assert ledger.final_decision("R1", ScreeningStage.FULL_TEXT) is ScreeningDecision.EXCLUDE


def test_reason_cannot_be_attached_to_include():
    ledger = ScreeningLedger()
    with pytest.raises(ValueError):
        ledger.add("R1", ScreeningDecision.INCLUDE, reason_code="OTHER")


def test_double_screening_conflict_and_adjudication():
    ledger = ScreeningLedger()
    ledger.add("R1", ScreeningDecision.INCLUDE, reviewer="a", timestamp="2026-01-01T00:00:00+00:00")
    ledger.add("R1", ScreeningDecision.EXCLUDE, reviewer="b", timestamp="2026-01-01T00:01:00+00:00")
    assert len(ledger.conflicts()) == 1
    assert ledger.final_decision("R1", ScreeningStage.TITLE_ABSTRACT) is ScreeningDecision.NOT_SCREENED
    ledger.adjudicate("R1", ScreeningDecision.INCLUDE, stage=ScreeningStage.TITLE_ABSTRACT, timestamp="2026-01-01T00:02:00+00:00")
    assert ledger.conflicts() == []
    assert ledger.final_decision("R1", ScreeningStage.TITLE_ABSTRACT) is ScreeningDecision.INCLUDE


def test_asreview_label_does_not_coerce_maybe():
    r = EvidenceRecord(title="A")
    ledger = ScreeningLedger()
    ledger.add(r, ScreeningDecision.MAYBE)
    assert ledger.asreview_label(r) is None
    ledger.adjudicate(r, ScreeningDecision.INCLUDE, stage=ScreeningStage.TITLE_ABSTRACT)
    assert ledger.asreview_label(r) == 1


def test_ledger_jsonl_roundtrip(tmp_path):
    ledger = ScreeningLedger()
    ledger.add("R1", ScreeningDecision.EXCLUDE, reviewer="alice", reason_code="WRONG_POPULATION", timestamp="2026-01-01T00:00:00+00:00")
    p = ledger.write_jsonl(tmp_path / "audit.jsonl")
    loaded = ScreeningLedger.read_jsonl(p)
    assert len(loaded.events) == 1
    assert loaded.events[0].reason_code == "WRONG_POPULATION"


def test_asreview_csv_columns_and_labels(tmp_path):
    records = sample_records()
    ledger = ScreeningLedger()
    ledger.add(records[0], ScreeningDecision.INCLUDE)
    ledger.add(records[1], ScreeningDecision.EXCLUDE)
    ledger.add(records[2], ScreeningDecision.MAYBE)
    p = write_asreview_csv(records, tmp_path / "asreview.csv", ledger=ledger)
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == ["title", "abstract", "authors", "year", "doi", "url", "included"]
    assert rows[0]["included"] == "1"
    assert rows[1]["included"] == "0"
    assert rows[2]["included"] == ""


def test_ris_asreview_notes_and_roundtrip_labels(tmp_path):
    records = sample_records()[:2]
    ledger = ScreeningLedger()
    ledger.add(records[0], ScreeningDecision.INCLUDE)
    ledger.add(records[1], ScreeningDecision.EXCLUDE)
    p = write_ris(records, tmp_path / "asreview.ris", ledger=ledger, asreview_labels=True)
    text = p.read_text(encoding="utf-8")
    assert "N1  - ASReview_relevant" in text
    assert "N1  - ASReview_irrelevant" in text
    imported = read_ris(p)
    assert len(imported.records) == 2
    assert imported.ledger.asreview_label(imported.records[0]) == 1
    assert imported.ledger.asreview_label(imported.records[1]) == 0


def test_csv_import_reads_asreview_labels_and_warns_on_bad_rows(tmp_path):
    p = tmp_path / "input.csv"
    p.write_text(
        "title,abstract,authors,year,doi,included\n"
        'Paper A,Abstract A,"Smith J; Jones A",2024,10.1000/a,1\n'
        "Paper B,Abstract B,Brown P,2023,10.1000/b,0\n"
        ",,,,,\n",
        encoding="utf-8",
    )
    result = read_csv(p)
    assert len(result.records) == 2
    assert len(result.warnings) == 1
    assert result.ledger.asreview_label(result.records[0]) == 1
    assert result.ledger.asreview_label(result.records[1]) == 0


def test_generic_csv_jsonl_and_bibtex_exports(tmp_path):
    records = sample_records()[:2]
    linkage = StudyLinkageEngine().link(records)
    ledger = ScreeningLedger()
    ledger.add(records[0], ScreeningDecision.INCLUDE)
    csv_path = write_csv(records, tmp_path / "records.csv", ledger=ledger, linkage=linkage)
    jsonl_path = write_jsonl(records, tmp_path / "records.jsonl", ledger=ledger, linkage=linkage)
    bib_path = write_bibtex(records, tmp_path / "records.bib")
    assert "study_id" in csv_path.read_text(encoding="utf-8")
    first = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert first["study_id"].startswith("STUDY-")
    assert "@article{" in bib_path.read_text(encoding="utf-8")


def test_screening_bundle_contains_expected_artifacts(tmp_path):
    records = sample_records()[:2]
    ledger = ScreeningLedger()
    ledger.add(records[0], ScreeningDecision.INCLUDE)
    ledger.add(records[1], ScreeningDecision.EXCLUDE)
    linkage = StudyLinkageEngine().link(records)
    paths = write_screening_bundle(records, tmp_path / "bundle", ledger=ledger, linkage=linkage)
    expected = {
        "records_csv", "records_jsonl", "records_ris", "records_bibtex",
        "asreview_csv", "asreview_ris", "screening_audit_jsonl",
        "screening_audit_csv", "study_families_csv", "double_counting_csv", "manifest",
    }
    assert expected <= set(paths)
    for key in expected:
        assert paths[key].exists()


def test_screening_counts_include_unresolved_conflict_as_not_screened():
    ledger = ScreeningLedger()
    ledger.add("R1", ScreeningDecision.INCLUDE, reviewer="a")
    ledger.add("R1", ScreeningDecision.EXCLUDE, reviewer="b")
    ledger.add("R2", ScreeningDecision.INCLUDE, reviewer="a")
    counts = ledger.counts(ScreeningStage.TITLE_ABSTRACT)
    assert counts["NOT_SCREENED"] == 1
    assert counts["INCLUDE"] == 1


def test_reviewer_agreement_and_kappa():
    ledger = ScreeningLedger()
    for rid, a, b in [
        ("R1", ScreeningDecision.INCLUDE, ScreeningDecision.INCLUDE),
        ("R2", ScreeningDecision.EXCLUDE, ScreeningDecision.EXCLUDE),
        ("R3", ScreeningDecision.INCLUDE, ScreeningDecision.EXCLUDE),
        ("R4", ScreeningDecision.EXCLUDE, ScreeningDecision.EXCLUDE),
    ]:
        ledger.add(rid, a, reviewer="a")
        ledger.add(rid, b, reviewer="b")
    agreement = ledger.agreement("a", "b")
    assert agreement.n_double_screened == 4
    assert agreement.agreements == 3
    assert agreement.percent_agreement == 0.75
    assert agreement.cohens_kappa is not None


def test_new_reviewer_decision_after_adjudication_can_reopen_conflict():
    ledger = ScreeningLedger()
    ledger.add("R1", ScreeningDecision.INCLUDE, reviewer="a", timestamp="2026-01-01T00:00:00+00:00")
    ledger.add("R1", ScreeningDecision.EXCLUDE, reviewer="b", timestamp="2026-01-01T00:01:00+00:00")
    ledger.adjudicate("R1", ScreeningDecision.INCLUDE, stage=ScreeningStage.TITLE_ABSTRACT, timestamp="2026-01-01T00:02:00+00:00")
    assert not ledger.conflicts()
    ledger.add("R1", ScreeningDecision.EXCLUDE, reviewer="a", timestamp="2026-01-01T00:03:00+00:00")
    assert len(ledger.conflicts()) == 0  # both latest reviewer decisions now agree on EXCLUDE
    assert ledger.final_decision("R1", ScreeningStage.TITLE_ABSTRACT) is ScreeningDecision.EXCLUDE


def test_bundle_manifest_contains_hashes(tmp_path):
    records = sample_records()[:1]
    paths = write_screening_bundle(records, tmp_path / "bundle")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["files"]["records_csv"]["sha256"]
    assert manifest["files"]["records_csv"]["bytes"] > 0
