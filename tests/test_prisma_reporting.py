import json
from pathlib import Path

import pytest

from metaevidence import (
    AdapterResult,
    ConfidenceDeduplicationEngine,
    EvidenceRecord,
    MultiSearchResult,
    PrismaAccountingError,
    PrismaBuilder,
    PrismaFlow,
    PrismaSearchContext,
    ScreeningDecision,
    ScreeningLedger,
    ScreeningStage,
    SearchManifest,
    SearchQuery,
    SourceHit,
    StudyLinkageEngine,
    Translation,
    write_prisma_bundle,
)


def _record(title, doi, *, year=2024, registry=None, role=None, source="pubmed"):
    metadata = {}
    if registry:
        metadata["trial_registration_number"] = registry
    if role:
        metadata["publication_type"] = role
    return EvidenceRecord(
        title=title,
        authors=["Smith J", "Jones A"],
        year=year,
        journal="Evidence Journal",
        doi=doi,
        source_hits=[SourceHit(source=source, source_id=doi)],
        metadata=metadata,
    )


def _workflow():
    q = SearchQuery('("diabetes" OR "type 2 diabetes") AND prediction', year_from=2020, year_to=2026)
    r1 = _record("Prediction trial primary results NCT01234567", "10.1000/a", registry="NCT01234567", role="primary results")
    r1_dup = _record("Prediction trial primary results NCT01234567", "10.1000/a", registry="NCT01234567", role="primary results", source="openalex")
    r2 = _record("Five year follow-up of prediction trial NCT01234567", "10.1000/b", year=2026, registry="NCT01234567", role="follow-up", source="openalex")
    r3 = _record("Unrelated diabetes prediction study", "10.1000/c")

    pub = AdapterResult(
        source="pubmed",
        translation=Translation("pubmed", q.canonical, '(diabetes OR "type 2 diabetes") AND prediction'),
        records=[r1, r3],
        total_available=2,
        pages_retrieved=1,
        started_at_utc="2026-09-06T18:00:00+00:00",
        finished_at_utc="2026-09-06T18:00:01+00:00",
    )
    oa = AdapterResult(
        source="openalex",
        translation=Translation("openalex", q.canonical, '(diabetes OR "type 2 diabetes") AND prediction'),
        records=[r1_dup, r2],
        total_available=2,
        pages_retrieved=1,
        started_at_utc="2026-09-06T18:00:01+00:00",
        finished_at_utc="2026-09-06T18:00:02+00:00",
    )
    manifest = SearchManifest(q.canonical, "0.7.0.dev0")
    manifest.add_execution(pub)
    manifest.add_execution(oa)
    search = MultiSearchResult(q, {"pubmed": pub, "openalex": oa}, [r1, r3, r1_dup, r2], manifest)
    dedup = ConfidenceDeduplicationEngine().deduplicate(search.records)
    assert len(dedup.records) == 3

    by_doi = {r.doi: r for r in dedup.records}
    ledger = ScreeningLedger()
    ledger.add(by_doi["10.1000/a"], ScreeningDecision.INCLUDE, reviewer="A")
    ledger.add(by_doi["10.1000/b"], ScreeningDecision.INCLUDE, reviewer="A")
    ledger.add(by_doi["10.1000/c"], ScreeningDecision.EXCLUDE, reviewer="A")
    ledger.add(by_doi["10.1000/a"], ScreeningDecision.INCLUDE, stage=ScreeningStage.FULL_TEXT, reviewer="A")
    ledger.add(by_doi["10.1000/b"], ScreeningDecision.INCLUDE, stage=ScreeningStage.FULL_TEXT, reviewer="A")
    linkage = StudyLinkageEngine().link(dedup.records)
    return search, dedup, ledger, linkage


def test_prisma_flow_end_to_end_counts():
    search, dedup, ledger, linkage = _workflow()
    flow = PrismaBuilder.build_flow(
        search=search,
        deduplication=dedup,
        ledger=ledger,
        records=dedup.records,
        linkage=linkage,
    )
    assert flow.total_records_identified == 4
    assert flow.duplicates_removed == 1
    assert flow.records_screened == 3
    assert flow.records_excluded == 1
    assert flow.reports_sought_for_retrieval == 2
    assert flow.reports_assessed_for_eligibility == 2
    assert flow.reports_included == 2
    assert flow.studies_included == 1
    assert flow.validate() == []


def test_full_text_exclusion_reasons_and_not_retrieved_are_separate():
    search, dedup, ledger, _ = _workflow()
    by_doi = {r.doi: r for r in dedup.records}
    # Replace r2's final full-text status with a later exclusion for a genuine eligibility reason.
    ledger.add(
        by_doi["10.1000/b"], ScreeningDecision.EXCLUDE,
        stage=ScreeningStage.FULL_TEXT, reviewer="A", reason_code="WRONG_OUTCOME",
        timestamp="2026-09-06T20:00:00+00:00",
    )
    # r3 was title/abstract excluded, so add a synthetic report that was sought but not retrieved.
    ledger.add(
        by_doi["10.1000/c"], ScreeningDecision.EXCLUDE,
        stage=ScreeningStage.FULL_TEXT, reviewer="A", reason_code="NOT_RETRIEVABLE",
        timestamp="2026-09-06T20:00:00+00:00",
    )
    flow = PrismaBuilder.build_flow(search=search, deduplication=dedup, ledger=ledger, records=dedup.records)
    assert flow.reports_sought_for_retrieval == 3
    assert flow.reports_not_retrieved == 1
    assert flow.reports_assessed_for_eligibility == 2
    assert flow.reports_excluded == {"WRONG_OUTCOME": 1}
    assert flow.reports_included == 1


def test_strict_validation_rejects_impossible_accounting():
    flow = PrismaFlow(databases={"x": 2}, duplicates_removed=0, records_screened=3)
    with pytest.raises(PrismaAccountingError):
        flow.validate(strict=True)


def test_truncated_search_is_flagged():
    search, dedup, ledger, _ = _workflow()
    search.source_results["openalex"].truncated = True
    flow = PrismaBuilder.build_flow(search=search, deduplication=dedup, ledger=ledger, records=dedup.records)
    assert any("truncated" in w.lower() for w in flow.warnings)


def test_prisma_s_report_captures_source_specific_strategy_and_dates():
    search, dedup, _, _ = _workflow()
    report = PrismaBuilder.build_search_report(search, deduplication=dedup)
    assert len(report.sources) == 2
    assert {s.database_name for s in report.sources} == {"PubMed", "OpenAlex"}
    assert all(s.translated_query for s in report.sources)
    assert all(s.search_finished_at_utc for s in report.sources)
    matrix = {x.item: x for x in report.support_matrix}
    assert matrix[1].status == "AUTOMATIC"
    assert matrix[8].status == "AUTOMATIC"
    assert matrix[13].status == "AUTOMATIC"
    assert matrix[15].status == "AUTOMATIC"
    assert matrix[16].status == "AUTOMATIC"


def test_prisma_s_human_context_is_explicit_not_invented():
    search, dedup, _, _ = _workflow()
    context = PrismaSearchContext(
        study_registries=["ClinicalTrials.gov"],
        peer_review="PRESS peer review by an independent information specialist.",
        limits_justification="Publication years were restricted to 2020-2026 to match the protocol.",
    )
    report = PrismaBuilder.build_search_report(search, deduplication=dedup, context=context)
    matrix = {x.item: x for x in report.support_matrix}
    assert matrix[3].status == "USER_SUPPLIED"
    assert matrix[14].status == "USER_SUPPLIED"
    assert matrix[5].status == "USER_INPUT_REQUIRED"


def test_missing_linkage_does_not_fake_study_count():
    search, dedup, ledger, _ = _workflow()
    flow = PrismaBuilder.build_flow(search=search, deduplication=dedup, ledger=ledger, records=dedup.records)
    assert flow.reports_included == 2
    assert flow.studies_included is None
    assert any("study-level linkage" in w for w in flow.warnings)


def test_register_and_other_source_counts_are_supported():
    flow = PrismaBuilder.build_flow(registers={"ClinicalTrials.gov": 7}, other_sources={"Citation searching": 3})
    assert flow.records_identified_registers == 7
    assert flow.records_identified_other_sources == 3
    assert flow.total_records_identified == 10


def test_mermaid_is_editable_and_contains_counts(tmp_path):
    flow = PrismaFlow(databases={"PubMed": 12}, duplicates_removed=2, records_screened=10)
    path = flow.write_mermaid(tmp_path / "flow.mmd")
    text = path.read_text()
    assert "flowchart TD" in text
    assert "Duplicates: 2" in text
    assert "Records screened" in text


def test_prisma_bundle_has_hash_manifest_and_reporting_artifacts(tmp_path):
    search, dedup, ledger, linkage = _workflow()
    flow = PrismaBuilder.build_flow(search=search, deduplication=dedup, ledger=ledger, records=dedup.records, linkage=linkage)
    report = PrismaBuilder.build_search_report(search, deduplication=dedup)
    paths = write_prisma_bundle(tmp_path, flow=flow, search_report=report, search=search)
    expected = {
        "prisma_flow_json", "prisma_flow_csv", "prisma_flow_mermaid", "search_report_json",
        "search_report_markdown", "search_sources_csv", "search_strategies_csv",
        "prisma_s_matrix_csv", "search_manifest", "reproducibility_manifest",
    }
    assert expected.issubset(paths)
    manifest = json.loads(paths["reproducibility_manifest"].read_text())
    assert manifest["format_version"] == "MetaEvidence-prisma-bundle-1"
    assert manifest["files"]["prisma_flow_json"]["sha256"]
    assert "does not by itself establish PRISMA compliance" in manifest["disclaimer"]


def test_search_report_markdown_contains_non_compliance_disclaimer(tmp_path):
    search, dedup, _, _ = _workflow()
    report = PrismaBuilder.build_search_report(search, deduplication=dedup)
    path = report.write_markdown(tmp_path / "report.md")
    text = path.read_text()
    assert "does not by itself establish" in text
    assert "## PRISMA-S support matrix" in text
    assert "PubMed" in text
