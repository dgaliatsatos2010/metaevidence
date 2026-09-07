from metaevidence import (
    ConfidenceDeduplicationEngine,
    EvidenceRecord,
    SourceHit,
)

records = [
    EvidenceRecord(
        title="Machine learning prediction of diabetes outcomes",
        authors=["Smith J"],
        year=2024,
        journal="Diabetes Care",
        source_hits=[SourceHit("pubmed", "123")],
    ),
    EvidenceRecord(
        title="Machine-learning prediction of diabetes outcome",
        authors=["J Smith"],
        year=2024,
        journal="Diabetes Care",
        source_hits=[SourceHit("openalex", "W123")],
    ),
]

engine = ConfidenceDeduplicationEngine()
result = engine.deduplicate(records)

for assessment in result.assessments:
    print(assessment.left_index, assessment.right_index)
    print("probability:", assessment.probability)
    print("decision:", assessment.decision.value)
    for line in assessment.explanation:
        print(" -", line)

print("unique publications:", len(result.records))
print("review queue:", len(result.review_queue))
