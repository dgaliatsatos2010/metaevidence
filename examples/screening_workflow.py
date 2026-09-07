from pathlib import Path

from metaevidence import (
    EvidenceRecord,
    ScreeningDecision,
    ScreeningLedger,
    ScreeningStage,
    StudyLinkageEngine,
    write_screening_bundle,
)

records = [
    EvidenceRecord(
        title="ORBIT trial protocol",
        authors=["Smith J"],
        year=2020,
        abstract="Registered as NCT01234567.",
        doi="10.1000/orbit.protocol",
        metadata={"report_role": "PROTOCOL"},
    ),
    EvidenceRecord(
        title="Primary outcomes of ORBIT",
        authors=["J Smith"],
        year=2022,
        abstract="ClinicalTrials.gov NCT01234567.",
        doi="10.1000/orbit.results",
        metadata={"report_role": "PRIMARY_RESULTS"},
    ),
]

ledger = ScreeningLedger()
ledger.add(records[0], ScreeningDecision.INCLUDE, reviewer="reviewer-A")
ledger.add(records[0], ScreeningDecision.EXCLUDE, reviewer="reviewer-B")
ledger.adjudicate(
    records[0], ScreeningDecision.INCLUDE,
    stage=ScreeningStage.TITLE_ABSTRACT,
    reviewer="adjudicator",
)
ledger.add(records[1], ScreeningDecision.INCLUDE, reviewer="reviewer-A")
ledger.add(records[1], ScreeningDecision.INCLUDE, reviewer="reviewer-B")

linkage = StudyLinkageEngine().link(records)
paths = write_screening_bundle(records, Path("review_bundle"), ledger=ledger, linkage=linkage)

print("study families:", len(linkage.families))
print("screening conflicts:", len(ledger.conflicts()))
print("agreement:", ledger.agreement("reviewer-A", "reviewer-B"))
for name, path in sorted(paths.items()):
    print(name, path)
