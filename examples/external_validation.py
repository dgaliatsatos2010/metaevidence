"""External gold-standard deduplication example.

Run only after obtaining the third-party benchmark file from its official public
source.  Do not treat synthetic/unit-test results as external validation.
"""

from pathlib import Path

from metaevidence import (
    DedupPartitionBenchmark,
    ExternalGoldDataset,
    load_external_dataset_specifications,
    validate_external_dataset,
    write_external_validation_result,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks" / "external_benchmark_manifest.json"
DATA_FILE = Path("Diabetes_duplicates_labelled.csv")
DATASET_ID = "asysd_diabetes"


if __name__ == "__main__":
    specs = load_external_dataset_specifications(PLAN)
    spec = next(x for x in specs if x.id == DATASET_ID)

    dataset = ExternalGoldDataset.from_delimited(DATA_FILE, name=DATASET_ID)
    integrity = validate_external_dataset(dataset, spec, strict=True)
    print("Integrity:", integrity)

    result = DedupPartitionBenchmark.evaluate(dataset)
    print("Metrics:", result.metrics)

    write_external_validation_result(
        result,
        ROOT / "external_results" / DATASET_ID,
        dataset=dataset,
        specification=spec,
    )
