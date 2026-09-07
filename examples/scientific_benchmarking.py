from metaevidence import (
    BlockingRecallBenchmark,
    ConfidenceDeduplicationEngine,
    DeduplicationAblationBenchmark,
    MetadataStressBenchmark,
    QueryTranslationBenchmark,
    QueryTranslationBenchmarkCase,
    ScalabilityBenchmark,
    ScientificBenchmarkBundle,
    StudyLinkageAblationBenchmark,
    synthetic_deduplication_dataset,
    synthetic_study_linkage_dataset,
    synthetic_unique_records,
)

# Everything in this example is synthetic engineering QA only.
dedup_records, dedup_labels = synthetic_deduplication_dataset(30, duplicate_fraction=0.6)
study_records, study_labels = synthetic_study_linkage_dataset(10)

query_demo = QueryTranslationBenchmark.evaluate(
    QueryTranslationBenchmarkCase(
        case_id="synthetic-query-demo",
        source="pubmed",
        reference_ids=frozenset({"PMID1", "PMID2", "PMID3", "PMID4"}),
        candidate_ids=frozenset({"PMID1", "PMID2", "PMID3", "PMID5"}),
        canonical_query='("machine learning" OR AI) AND diabetes',
        expert_query="synthetic expert reference",
        generated_query="synthetic MetaEvidence translation",
        fidelity_score=0.9,
        loss_score=0.1,
        requires_review=False,
    )
)

bundle = ScientificBenchmarkBundle(
    name="metaevidence-v0.8-synthetic-demo",
    query_translation=[query_demo],
    dedup_ablation=DeduplicationAblationBenchmark().evaluate(
        dedup_records, dedup_labels,
        features=["doi_exact", "title_similarity", "author_similarity"],
    ),
    blocking_recall=[
        BlockingRecallBenchmark.deduplication(
            dedup_records, dedup_labels, engine=ConfidenceDeduplicationEngine(exhaustive_limit=10)
        )
    ],
    study_ablation=StudyLinkageAblationBenchmark().evaluate(
        study_records, study_labels,
        features=["registry_exact", "author_similarity", "intervention_similarity"],
    ),
    metadata_stress=MetadataStressBenchmark.evaluate_deduplication(
        dedup_records, dedup_labels, missing_rates=[0, 0.25, 0.5], repeats=2,
    ),
    scalability=ScalabilityBenchmark.deduplication(
        synthetic_unique_records, sizes=[50, 200, 2100], repeats=1,
    ),
    notes=[
        "Synthetic QA results must not be used for scientific accuracy claims.",
        "The 2100-record case intentionally crosses the default exhaustive-pairing boundary.",
    ],
)

bundle.write("benchmark_demo")
