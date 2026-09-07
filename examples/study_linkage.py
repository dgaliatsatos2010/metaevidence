from metaevidence import EvidenceRecord, SourceHit, StudyLinkageEngine

records = [
    EvidenceRecord(
        title="ABC trial protocol",
        authors=["Smith J", "Jones A"],
        year=2020,
        abstract="Registered as NCT01234567.",
        metadata={"report_role": "PROTOCOL", "sample_size": 400},
        source_hits=[SourceHit("pubmed", "P1")],
    ),
    EvidenceRecord(
        title="Primary outcomes of the ABC trial",
        authors=["J Smith", "Brown P"],
        year=2022,
        abstract="ClinicalTrials.gov identifier NCT01234567.",
        metadata={"report_role": "PRIMARY_RESULTS", "sample_size": 398},
        source_hits=[SourceHit("openalex", "W2")],
    ),
    EvidenceRecord(
        title="Five-year follow-up of ABC",
        authors=["Smith J", "Green L"],
        year=2027,
        abstract="NCT01234567.",
        metadata={"report_role": "FOLLOW_UP"},
        source_hits=[SourceHit("crossref", "C3")],
    ),
]

result = StudyLinkageEngine().link(records)

for family in result.families:
    print(family.study_id, family.member_indices, family.registry_ids, family.publication_roles)

for risk in result.double_counting_risks:
    print("double-counting risk:", risk.severity, risk.reason)

result.write_json("study_linkage.json")
result.write_families_csv("study_families.csv")
result.write_edges_csv("study_edges.csv")
result.write_review_csv("study_review_queue.csv")
result.write_double_counting_csv("double_counting_risks.csv")
