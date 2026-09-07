from __future__ import annotations

from copy import deepcopy
import random

from .benchmark import LabeledPair
from .models import EvidenceRecord, SourceHit
from .study_benchmark import StudyLabeledPair


def synthetic_deduplication_dataset(n_unique: int = 40, *, duplicate_fraction: float = 0.35, seed: int = 7) -> tuple[list[EvidenceRecord], list[LabeledPair]]:
    """Create a deterministic engineering dataset with labelled duplicate pairs.

    This generator is for tests, examples and scaling checks only. It is deliberately
    not labelled as a scientific validation set.
    """
    if n_unique < 2:
        raise ValueError("n_unique must be >= 2")
    if not 0 <= duplicate_fraction <= 1:
        raise ValueError("duplicate_fraction must be in [0, 1]")
    rng = random.Random(seed)
    records: list[EvidenceRecord] = []
    duplicate_groups: list[list[int]] = []
    for i in range(n_unique):
        doi = f"10.5555/meta.{i:05d}"
        base = EvidenceRecord(
            title=f"Evidence synthesis benchmark article {i} for chronic disease prediction",
            authors=[f"Author{i % 11} A", f"Researcher{i % 7} B"],
            year=2015 + (i % 11),
            journal=f"Journal of Evidence {i % 5}",
            abstract=f"Synthetic abstract for benchmark record {i} with reproducible metadata.",
            doi=doi,
            pmid=str(80000000 + i),
            source_hits=[SourceHit(source="pubmed", source_id=str(80000000 + i))],
            metadata={"volume": str(10 + i % 8), "issue": str(1 + i % 4), "pages": f"{100+i}-{105+i}", "publication_type": "journal article"},
        )
        idx = len(records)
        records.append(base)
        group = [idx]
        if rng.random() < duplicate_fraction:
            dup = deepcopy(base)
            dup.title = dup.title.replace("benchmark article", "benchmark study article")
            dup.authors = [f"A Author{i % 11}", f"B Researcher{i % 7}"]
            dup.pmid = None
            dup.source_hits = [SourceHit(source="openalex", source_id=f"W{900000+i}")]
            dup.openalex_id = f"W{900000+i}"
            dup.metadata["issue"] = ""
            group.append(len(records))
            records.append(dup)
        duplicate_groups.append(group)

    labels: list[LabeledPair] = []
    duplicate_pairs = set()
    for group in duplicate_groups:
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                duplicate_pairs.add((group[a], group[b]))
                labels.append(LabeledPair(group[a], group[b], True))

    # Deterministic hard-negative pairs, including similar journals/years.
    target_neg = max(len(labels) * 3, n_unique)
    seen = set(duplicate_pairs)
    attempts = 0
    while sum(not x.is_duplicate for x in labels) < target_neg and attempts < target_neg * 50:
        i, j = sorted(rng.sample(range(len(records)), 2))
        attempts += 1
        if (i, j) in seen:
            continue
        if records[i].doi and records[i].doi == records[j].doi:
            continue
        seen.add((i, j))
        labels.append(LabeledPair(i, j, False))
    return records, labels


def synthetic_study_linkage_dataset(n_studies: int = 18, *, seed: int = 11) -> tuple[list[EvidenceRecord], list[StudyLabeledPair]]:
    """Create deterministic protocol/results/follow-up families for engineering QA."""
    if n_studies < 2:
        raise ValueError("n_studies must be >= 2")
    rng = random.Random(seed)
    records: list[EvidenceRecord] = []
    families: list[list[int]] = []
    for i in range(n_studies):
        nct = f"NCT{10000000+i:08d}"
        authors = [f"Investigator{i % 7} A", f"Clinician{i % 5} B"]
        common = {
            "authors": authors,
            "journal": "Trials" if i % 2 == 0 else "Clinical Research",
        }
        protocol = EvidenceRecord(
            title=f"Protocol for the TEST{i} randomized trial of intervention {i}",
            year=2016 + (i % 6),
            abstract=f"Registered trial {nct}. Recruitment planned for 240 participants.",
            doi=f"10.7777/protocol.{i}",
            metadata={"publication_type": "protocol", "registry_id": nct, "sample_size": 240, "country": "Greece", "intervention": f"intervention {i}", "population": "adults"},
            **common,
        )
        primary = EvidenceRecord(
            title=f"Primary outcomes of the TEST{i} randomized trial",
            year=2018 + (i % 6),
            abstract=f"Results from {nct}; 238 participants were analysed.",
            doi=f"10.7777/results.{i}",
            metadata={"publication_type": "journal article", "registry_id": nct, "sample_size": 238, "country": "Greece", "intervention": f"intervention {i}", "population": "adults"},
            **common,
        )
        follow = EvidenceRecord(
            title=f"Long-term follow-up of TEST{i}",
            year=2021 + (i % 5),
            abstract=f"Five-year follow-up of participants from trial {nct}.",
            doi=f"10.7777/followup.{i}",
            metadata={"publication_type": "follow-up", "registry_id": nct, "sample_size": 201, "country": "Greece", "intervention": f"intervention {i}", "population": "adults"},
            **common,
        )
        family = [len(records), len(records)+1, len(records)+2]
        records.extend([protocol, primary, follow])
        families.append(family)

    labels: list[StudyLabeledPair] = []
    seen = set()
    for fam in families:
        for a in range(len(fam)):
            for b in range(a+1, len(fam)):
                i, j = fam[a], fam[b]
                labels.append(StudyLabeledPair(i, j, True))
                seen.add((i, j))
    target_neg = len(labels) * 2
    neg = 0
    attempts = 0
    while neg < target_neg and attempts < target_neg * 50:
        i, j = sorted(rng.sample(range(len(records)), 2))
        attempts += 1
        if (i, j) in seen:
            continue
        ri = records[i].metadata.get("registry_id")
        rj = records[j].metadata.get("registry_id")
        if ri == rj:
            continue
        seen.add((i, j))
        labels.append(StudyLabeledPair(i, j, False))
        neg += 1
    return records, labels


def synthetic_unique_records(n: int, *, seed: int = 99) -> list[EvidenceRecord]:
    """Fast deterministic factory for scalability tests."""
    if n < 1:
        raise ValueError("n must be positive")
    rng = random.Random(seed + n)
    out = []
    for i in range(n):
        out.append(EvidenceRecord(
            title=f"Unique scalability citation {i} topic {i % 103}",
            authors=[f"Author{i % 211} A"],
            year=2000 + (i % 26),
            journal=f"Journal {i % 53}",
            doi=f"10.9999/scale.{i:08d}",
            metadata={"volume": str(1+i % 40), "issue": str(1+i % 12), "pages": str(1 + rng.randrange(900))},
        ))
    return out
