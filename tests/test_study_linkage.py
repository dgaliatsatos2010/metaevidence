from metaevidence import EvidenceRecord, SourceHit
from metaevidence.study_linkage import (
    PublicationRole,
    StudyLinkDecision,
    StudyLinkageEngine,
    classify_publication_role,
    extract_registry_ids,
    extract_study_acronyms,
)
from metaevidence.study_benchmark import StudyLabeledPair, StudyLinkageBenchmark


def test_registry_extraction_normalizes_common_identifiers():
    r = EvidenceRecord(
        title="Trial report NCT01234567 and ISRCTN 12345678",
        metadata={"trial_registration": "ACTRN12612000985864"},
    )
    ids = extract_registry_ids(r)
    assert "NCT:01234567" in ids
    assert "ISRCTN:12345678" in ids
    assert "ACTRN:12612000985864" in ids


def test_same_nct_links_distinct_protocol_and_primary_report():
    a = EvidenceRecord(
        title="ABC trial protocol",
        authors=["Smith J", "Jones A"],
        year=2020,
        abstract="Registered as NCT01234567.",
        metadata={"report_role": "PROTOCOL", "sample_size": 400},
    )
    b = EvidenceRecord(
        title="Primary outcomes of the ABC trial",
        authors=["J Smith", "Brown P"],
        year=2022,
        abstract="ClinicalTrials.gov NCT01234567.",
        metadata={"report_role": "PRIMARY_RESULTS", "sample_size": 398},
    )
    x = StudyLinkageEngine().assess_pair(a, b)
    assert x.decision is StudyLinkDecision.SAME_STUDY
    assert x.study_probability >= 0.998
    assert x.left_role is PublicationRole.PROTOCOL
    assert x.right_role is PublicationRole.PRIMARY_RESULTS


def test_duplicate_publication_is_not_mislabelled_as_two_reports():
    a = EvidenceRecord(title="A report", doi="10.1000/a", abstract="NCT01234567")
    b = EvidenceRecord(title="A report metadata variant", doi="10.1000/a", abstract="NCT01234567")
    x = StudyLinkageEngine().assess_pair(a, b)
    assert x.decision is StudyLinkDecision.DUPLICATE_PUBLICATION
    assert x.publication_probability > 0.99


def test_review_article_registry_mention_cannot_auto_link_to_trial_report():
    a = EvidenceRecord(
        title="Systematic review of treatments",
        abstract="Included trial NCT01234567.",
        metadata={"publication_type": "systematic review"},
    )
    b = EvidenceRecord(
        title="Results of treatment trial",
        abstract="NCT01234567",
        metadata={"publication_type": "clinical trial"},
    )
    x = StudyLinkageEngine().assess_pair(a, b)
    assert x.left_role is PublicationRole.REVIEW
    assert x.decision is not StudyLinkDecision.SAME_STUDY
    assert x.study_probability <= 0.60


def test_disjoint_registry_ids_block_automatic_same_study_decision():
    a = EvidenceRecord(title="ABC trial results", authors=["Smith J"], abstract="NCT01234567")
    b = EvidenceRecord(title="ABC trial follow-up", authors=["J Smith"], abstract="NCT99999999")
    x = StudyLinkageEngine().assess_pair(a, b)
    assert x.features.registry_conflict == 1.0
    assert x.decision is not StudyLinkDecision.SAME_STUDY
    assert x.study_probability <= 0.74


def test_acronym_extraction_uses_explicit_trial_context():
    r = EvidenceRecord(title="Long-term outcomes from the HEART trial", metadata={"trial_acronym": "HEART"})
    assert "HEART" in extract_study_acronyms(r)


def test_non_registry_multifeature_pair_can_be_sent_to_review():
    a = EvidenceRecord(
        title="Treatment X in adults with disease Y",
        authors=["Smith J", "Jones A"], year=2020,
        metadata={
            "trial_acronym": "ORBIT", "sample_size": 300, "country": "Greece",
            "intervention": "Treatment X", "condition": "Disease Y",
            "recruitment_start": "2018-01-01", "recruitment_end": "2019-12-31",
            "report_role": "PROTOCOL",
        },
    )
    b = EvidenceRecord(
        title="Clinical outcomes of ORBIT",
        authors=["J Smith", "Brown P"], year=2022,
        metadata={
            "study_acronym": "ORBIT", "sample_size": 296, "country": "Greece",
            "intervention": "Treatment X", "condition": "Disease Y",
            "recruitment_start": "2018", "recruitment_end": "2019",
            "report_role": "PRIMARY_RESULTS",
        },
    )
    x = StudyLinkageEngine().assess_pair(a, b)
    assert x.study_probability >= 0.65
    assert x.decision in {StudyLinkDecision.REVIEW, StudyLinkDecision.SAME_STUDY}


def test_link_builds_stable_study_family_without_discarding_reports():
    records = [
        EvidenceRecord(title="Protocol", abstract="NCT01234567", metadata={"report_role": "PROTOCOL"}, source_hits=[SourceHit("pubmed", "1")]),
        EvidenceRecord(title="Primary results", abstract="NCT01234567", metadata={"report_role": "PRIMARY_RESULTS"}, source_hits=[SourceHit("openalex", "2")]),
        EvidenceRecord(title="Five year follow-up", abstract="NCT01234567", metadata={"report_role": "FOLLOW_UP"}, source_hits=[SourceHit("crossref", "3")]),
        EvidenceRecord(title="Unrelated study", abstract="NCT99999999", source_hits=[SourceHit("pubmed", "4")]),
    ]
    result = StudyLinkageEngine().link(records)
    family = result.family_for_record(0)
    assert family is not None
    assert family.member_indices == [0, 1, 2]
    assert family.study_id.startswith("STUDY-")
    assert family.registry_ids == ["NCT:01234567"]
    assert set(family.sources) == {"pubmed", "openalex", "crossref"}
    assert len(result.families) == 2
    assert result.stats.same_study_pairs >= 2


def test_same_family_id_is_invariant_to_input_order_when_registry_exists():
    a = EvidenceRecord(title="Protocol", abstract="NCT01234567", metadata={"report_role": "PROTOCOL"})
    b = EvidenceRecord(title="Results", abstract="NCT01234567", metadata={"report_role": "PRIMARY_RESULTS"})
    x = StudyLinkageEngine().link([a, b]).families[0].study_id
    y = StudyLinkageEngine().link([b, a]).families[0].study_id
    assert x == y


def test_large_dataset_blocking_finds_shared_registry():
    records = [EvidenceRecord(title=f"Unique paper {i}") for i in range(15)]
    records[2].abstract = "NCT01234567"
    records[13].abstract = "NCT01234567"
    result = StudyLinkageEngine(exhaustive_limit=5).link(records)
    assert result.stats.used_exhaustive_pairing is False
    assert result.family_for_record(2).study_id == result.family_for_record(13).study_id


def test_study_linkage_benchmark_metrics():
    records = [
        EvidenceRecord(title="Protocol A", abstract="NCT01234567", metadata={"report_role": "PROTOCOL"}),
        EvidenceRecord(title="Results A", abstract="NCT01234567", metadata={"report_role": "PRIMARY_RESULTS"}),
        EvidenceRecord(title="Results B", abstract="NCT99999999", metadata={"report_role": "PRIMARY_RESULTS"}),
    ]
    labels = [StudyLabeledPair(0, 1, True), StudyLabeledPair(0, 2, False)]
    metrics = StudyLinkageBenchmark().evaluate(records, labels)
    assert metrics.true_positive == 1
    assert metrics.true_negative == 1
    assert metrics.false_positive == 0
    assert metrics.false_negative == 0
    assert metrics.precision == 1.0


def test_role_classifier_separates_followup_from_review():
    a = EvidenceRecord(title="Ten-year follow-up of the ABC trial")
    b = EvidenceRecord(title="ABC trial: a systematic review and meta-analysis")
    assert classify_publication_role(a) is PublicationRole.FOLLOW_UP
    assert classify_publication_role(b) is PublicationRole.REVIEW


def test_multi_registry_bridge_is_sent_to_review_not_auto_linked():
    a = EvidenceRecord(title="Trial A results", abstract="NCT01234567")
    b = EvidenceRecord(title="Paper mentioning two registrations", abstract="NCT01234567 and NCT99999999")
    x = StudyLinkageEngine().assess_pair(a, b)
    assert x.features.multi_registry_ambiguous == 1.0
    assert x.decision is StudyLinkDecision.REVIEW


def test_cluster_consistency_blocks_transitive_bridge_between_registered_trials():
    # B has no registry ID but enough structured metadata to resemble both reports.
    common = {
        "trial_acronym": "ORBIT", "country": "Greece", "intervention": "Treatment X",
        "condition": "Disease Y", "sample_size": 300,
        "recruitment_start": "2018", "recruitment_end": "2019",
    }
    a = EvidenceRecord(title="ORBIT trial protocol", authors=["Smith J"], year=2020, abstract="NCT01234567", metadata={**common, "report_role": "PROTOCOL"})
    b = EvidenceRecord(title="ORBIT outcomes", authors=["J Smith"], year=2022, metadata={**common, "report_role": "PRIMARY_RESULTS"})
    c = EvidenceRecord(title="ORBIT follow-up", authors=["Smith J"], year=2023, abstract="NCT99999999", metadata={**common, "report_role": "FOLLOW_UP"})
    engine = StudyLinkageEngine(same_study_threshold=0.90)
    result = engine.link([a, b, c])
    # No final family may contain both conflicting NCT identifiers.
    for family in result.families:
        assert not ({"NCT:01234567", "NCT:99999999"} <= set(family.registry_ids))
    assert any("Cluster-consistency" in " ".join(x.rules) for x in result.review_queue)


def test_result_exports_json_and_csv(tmp_path):
    records = [
        EvidenceRecord(title="Protocol", abstract="NCT01234567", metadata={"report_role": "PROTOCOL"}),
        EvidenceRecord(title="Results", abstract="NCT01234567", metadata={"report_role": "PRIMARY_RESULTS"}),
    ]
    result = StudyLinkageEngine().link(records)
    json_path = result.write_json(tmp_path / "families.json")
    csv_path = result.write_families_csv(tmp_path / "families.csv")
    review_path = result.write_review_csv(tmp_path / "review.csv")
    assert json_path.exists() and "STUDY-" in json_path.read_text()
    assert csv_path.exists() and "study_id" in csv_path.read_text()
    assert review_path.exists() and "left_index" in review_path.read_text()


def test_double_counting_risk_is_flagged_for_multiple_outcome_reports(tmp_path):
    records = [
        EvidenceRecord(title="Primary results", abstract="NCT01234567", metadata={"report_role": "PRIMARY_RESULTS"}),
        EvidenceRecord(title="Subgroup results", abstract="NCT01234567", metadata={"report_role": "SUBGROUP_ANALYSIS"}),
        EvidenceRecord(title="Five-year follow-up", abstract="NCT01234567", metadata={"report_role": "FOLLOW_UP"}),
    ]
    result = StudyLinkageEngine().link(records)
    assert len(result.double_counting_risks) == 1
    assert result.double_counting_risks[0].severity == "HIGH"
    p = result.write_double_counting_csv(tmp_path / "double_counting.csv")
    assert "HIGH" in p.read_text()
    e = result.write_edges_csv(tmp_path / "edges.csv")
    assert "study_probability" in e.read_text()
