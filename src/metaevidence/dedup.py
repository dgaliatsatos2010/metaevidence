from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
import math
import re
import unicodedata
from typing import Iterable

from .models import EvidenceRecord


_STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on",
    "or", "the", "to", "with", "without", "using", "use", "study", "analysis",
}


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _tokens(value: str | None) -> list[str]:
    return [t for t in _norm_text(value).split() if t]


def _substantive_tokens(value: str | None) -> set[str]:
    # Numeric tokens can distinguish otherwise generic titles (e.g. part 1 vs part 2).
    return {t for t in _tokens(value) if (len(t) > 2 or t.isdigit()) and t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def _similarity(a: str | None, b: str | None) -> float | None:
    aa, bb = _norm_text(a), _norm_text(b)
    if not aa or not bb:
        return None
    return SequenceMatcher(None, aa, bb).ratio()


def _lead_author_key(record: EvidenceRecord) -> str | None:
    if not record.authors:
        return None
    toks = _tokens(record.authors[0])
    names = [t for t in toks if len(t) > 1]
    if not names:
        return toks[0] if toks else None
    # Handles both "Smith J" and "J Smith" without assuming order.
    return max(names, key=len)


def _author_similarity(a: EvidenceRecord, b: EvidenceRecord) -> float | None:
    if not a.authors or not b.authors:
        return None

    def keys(authors: list[str]) -> set[str]:
        out: set[str] = set()
        for author in authors:
            toks = _tokens(author)
            names = [t for t in toks if len(t) > 1]
            if names:
                out.add(max(names, key=len))
            elif toks:
                out.add(toks[0])
        return out

    return _jaccard(keys(a.authors), keys(b.authors))


def _year_similarity(a: int | None, b: int | None) -> float | None:
    if a is None or b is None:
        return None
    d = abs(a - b)
    if d == 0:
        return 1.0
    if d == 1:
        return 0.75
    if d == 2:
        return 0.25
    return 0.0


def _metadata_text(record: EvidenceRecord, *keys: str) -> str | None:
    for key in keys:
        value = record.metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _field_exact(a: str | None, b: str | None) -> float | None:
    aa, bb = _norm_text(a), _norm_text(b)
    if not aa or not bb:
        return None
    return 1.0 if aa == bb else 0.0


def _publication_form(record: EvidenceRecord) -> str | None:
    values: list[str] = []
    for key in ("type", "publication_type", "source_record_type"):
        value = record.metadata.get(key)
        if value:
            values.append(str(value))
    pub_types = record.metadata.get("publication_types")
    if isinstance(pub_types, (list, tuple, set)):
        values.extend(str(v) for v in pub_types if v)
    text = " ".join(values).lower()
    if not text:
        return None
    if "preprint" in text or "posted-content" in text or "posted content" in text:
        return "preprint"
    if "conference" in text or "proceedings" in text or "meeting abstract" in text:
        return "conference"
    if "journal" in text or "journal-article" in text or "article" in text:
        return "journal_article"
    if "book" in text or "chapter" in text:
        return "book"
    if "thesis" in text or "dissertation" in text:
        return "thesis"
    return None


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class DeduplicationDecision(str, Enum):
    AUTO_MERGE = "AUTO_MERGE"
    REVIEW = "REVIEW"
    KEEP_SEPARATE = "KEEP_SEPARATE"


@dataclass(slots=True)
class MatchFeatures:
    doi_exact: float = 0.0
    doi_conflict: float = 0.0
    strong_id_exact: float = 0.0
    strong_id_conflict: float = 0.0
    publication_form_conflict: float = 0.0
    title_similarity: float | None = None
    title_token_jaccard: float | None = None
    author_similarity: float | None = None
    year_similarity: float | None = None
    journal_similarity: float | None = None
    volume_exact: float | None = None
    issue_exact: float | None = None
    pages_exact: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "doi_exact": self.doi_exact,
            "doi_conflict": self.doi_conflict,
            "strong_id_exact": self.strong_id_exact,
            "strong_id_conflict": self.strong_id_conflict,
            "publication_form_conflict": self.publication_form_conflict,
            "title_similarity": self.title_similarity,
            "title_token_jaccard": self.title_token_jaccard,
            "author_similarity": self.author_similarity,
            "year_similarity": self.year_similarity,
            "journal_similarity": self.journal_similarity,
            "volume_exact": self.volume_exact,
            "issue_exact": self.issue_exact,
            "pages_exact": self.pages_exact,
        }


@dataclass(slots=True)
class EvidenceContribution:
    feature: str
    value: float
    weight: float
    contribution: float
    note: str | None = None


@dataclass(slots=True)
class MatchAssessment:
    left_index: int
    right_index: int
    probability: float
    decision: DeduplicationDecision
    features: MatchFeatures
    contributions: list[EvidenceContribution] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    calibrated: bool = False

    @property
    def explanation(self) -> list[str]:
        lines = list(self.rules)
        ranked = sorted(self.contributions, key=lambda x: abs(x.contribution), reverse=True)
        for item in ranked[:6]:
            sign = "+" if item.contribution >= 0 else ""
            suffix = f" ({item.note})" if item.note else ""
            lines.append(
                f"{item.feature}: value={item.value:.3f}, weight={item.weight:.2f}, "
                f"contribution={sign}{item.contribution:.3f}{suffix}"
            )
        return lines


@dataclass(slots=True)
class DuplicateLink:
    kept_index: int
    removed_index: int
    rule: str
    score: float
    decision: DeduplicationDecision = DeduplicationDecision.AUTO_MERGE


@dataclass(slots=True)
class DeduplicationStats:
    input_records: int
    candidate_pairs: int
    assessed_pairs: int
    auto_merge_pairs: int
    review_pairs: int
    output_records: int
    used_exhaustive_pairing: bool


@dataclass(slots=True)
class DeduplicationResult:
    records: list[EvidenceRecord]
    links: list[DuplicateLink]
    assessments: list[MatchAssessment] = field(default_factory=list)
    review_queue: list[MatchAssessment] = field(default_factory=list)
    stats: DeduplicationStats | None = None


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


class ConfidenceDeduplicationEngine:
    """Explainable publication-level record linkage for systematic-review citations.

    The default scoring model is intentionally transparent and *provisional*. Its
    output is an estimated match probability derived from expert-defined weights;
    it is not an empirically calibrated probability until a fitted calibrator is
    supplied. Exact identifiers and explicit conflicts are handled by high-priority
    rules before the weighted bibliographic evidence is interpreted.

    Parameters
    ----------
    auto_merge_threshold:
        Pairs at or above this threshold are automatically clustered.
    review_threshold:
        Pairs at or above this threshold but below auto_merge_threshold are sent
        to human review.
    fuzzy_threshold:
        Backward-compatible high-similarity rule threshold. If title similarity is
        at least this value and compatible author/year evidence is present, the
        pair may be promoted to AUTO_MERGE unless conflicting identifiers exist.
    exhaustive_limit:
        For datasets up to this size, all pairs are assessed to maximize recall.
        Larger datasets use deterministic blocking to avoid O(n^2) comparisons.
    calibrator:
        Optional object exposing ``predict(probability: float) -> float``.
    """

    DEFAULT_WEIGHTS = {
        "doi_exact": 10.0,
        "doi_conflict": -10.0,
        "strong_id_exact": 8.0,
        "strong_id_conflict": -5.0,
        "publication_form_conflict": -4.0,
        "title_similarity": 4.8,
        "title_token_jaccard": 2.2,
        "author_similarity": 2.0,
        "year_similarity": 1.2,
        "journal_similarity": 1.0,
        "volume_exact": 0.45,
        "issue_exact": 0.25,
        "pages_exact": 0.55,
    }

    def __init__(
        self,
        auto_merge_threshold: float = 0.985,
        review_threshold: float = 0.75,
        fuzzy_threshold: float = 0.94,
        exhaustive_limit: int = 2000,
        calibrator: object | None = None,
        weights: dict[str, float] | None = None,
        intercept: float = -7.5,
    ) -> None:
        if not 0 < review_threshold < auto_merge_threshold <= 1:
            raise ValueError("Require 0 < review_threshold < auto_merge_threshold <= 1")
        if not 0 < fuzzy_threshold <= 1:
            raise ValueError("fuzzy_threshold must be in (0, 1]")
        if exhaustive_limit < 2:
            raise ValueError("exhaustive_limit must be >= 2")
        self.auto_merge_threshold = auto_merge_threshold
        self.review_threshold = review_threshold
        self.fuzzy_threshold = fuzzy_threshold
        self.exhaustive_limit = exhaustive_limit
        self.calibrator = calibrator
        self.weights = dict(self.DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        self.intercept = intercept

    def assess_pair(self, a: EvidenceRecord, b: EvidenceRecord, left_index: int = 0, right_index: int = 1) -> MatchAssessment:
        features = self._features(a, b)
        probability, contributions = self._weighted_probability(features)
        rules: list[str] = []

        # High-confidence exact-identifier rules.
        if features.doi_exact:
            probability = max(probability, 0.99999)
            rules.append("Exact normalized DOI agreement")
        elif features.strong_id_exact:
            probability = max(probability, 0.9995)
            rules.append("Exact database-identifier agreement")

        # Conflicting identifiers are deliberately conservative. A different DOI
        # usually indicates a distinct publication even when titles are similar.
        if features.doi_conflict:
            probability = min(probability, 0.10)
            rules.append("Conflicting non-empty DOIs: automatic merge blocked")
        elif features.strong_id_conflict and not features.doi_exact:
            probability = min(probability, 0.55)
            rules.append("Conflicting same-system identifiers: review/merge constrained")

        if features.publication_form_conflict and not features.doi_exact and not features.strong_id_exact:
            probability = min(probability, 0.45)
            rules.append("Different publication forms (e.g. preprint/conference/journal): keep as separate publications")

        # Backward-compatible high-similarity bibliographic rule. It requires
        # compatible author and year evidence, and never overrides identifier conflict.
        if not features.doi_conflict and not features.strong_id_conflict and not features.publication_form_conflict:
            title_ok = (features.title_similarity or 0.0) >= self.fuzzy_threshold
            # Fuzzy-title auto-merge requires positive author evidence; missing author
            # metadata is insufficient for an automatic decision.
            author_ok = features.author_similarity is not None and features.author_similarity >= 0.5
            year_ok = features.year_similarity is None or features.year_similarity >= 0.75
            if title_ok and author_ok and year_ok:
                probability = max(probability, 0.990)
                rules.append("High title similarity with compatible author/year metadata")

        # Exact normalized title alone is powerful but not sufficient when publication
        # forms may differ; author/year support is required for automatic promotion.
        ta, tb = _norm_text(a.title), _norm_text(b.title)
        if ta and ta == tb and not features.doi_conflict and not features.publication_form_conflict:
            author_support = features.author_similarity is not None and features.author_similarity >= 0.5
            journal_support = features.journal_similarity is not None and features.journal_similarity >= 0.95
            year_ok = features.year_similarity is None or features.year_similarity >= 0.75
            if (author_support or journal_support) and year_ok:
                probability = max(probability, 0.995)
                rules.append("Exact normalized title with corroborating bibliographic metadata")

        calibrated = False
        if self.calibrator is not None:
            predict = getattr(self.calibrator, "predict", None)
            if predict is None:
                raise TypeError("calibrator must expose predict(probability)")
            probability = float(predict(probability))
            probability = min(1.0, max(0.0, probability))
            calibrated = True
            rules.append("Probability adjusted by fitted calibrator")

        # Deterministic identity/safety rules remain authoritative after optional calibration.
        if features.doi_exact:
            probability = max(probability, 0.99999)
        elif features.strong_id_exact:
            probability = max(probability, 0.9995)
        if features.doi_conflict:
            probability = min(probability, 0.10)
        if features.publication_form_conflict and not features.doi_exact and not features.strong_id_exact:
            probability = min(probability, 0.45)

        if probability >= self.auto_merge_threshold and not features.doi_conflict and not features.publication_form_conflict:
            decision = DeduplicationDecision.AUTO_MERGE
        elif probability >= self.review_threshold:
            decision = DeduplicationDecision.REVIEW
        else:
            decision = DeduplicationDecision.KEEP_SEPARATE

        return MatchAssessment(
            left_index=left_index,
            right_index=right_index,
            probability=probability,
            decision=decision,
            features=features,
            contributions=contributions,
            rules=rules,
            calibrated=calibrated,
        )

    def deduplicate(self, records: list[EvidenceRecord]) -> DeduplicationResult:
        n = len(records)
        if n <= 1:
            return DeduplicationResult(
                records=[deepcopy(r) for r in records],
                links=[],
                assessments=[],
                review_queue=[],
                stats=DeduplicationStats(n, 0, 0, 0, 0, n, True),
            )

        pairs, exhaustive = self._candidate_pairs(records)
        assessments: list[MatchAssessment] = []
        review_queue: list[MatchAssessment] = []
        uf = _UnionFind(n)

        for i, j in sorted(pairs):
            assessment = self.assess_pair(records[i], records[j], i, j)
            assessments.append(assessment)
            if assessment.decision is DeduplicationDecision.AUTO_MERGE:
                uf.union(i, j)
            elif assessment.decision is DeduplicationDecision.REVIEW:
                review_queue.append(assessment)

        clusters: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            clusters[uf.find(i)].append(i)

        merged_records: list[EvidenceRecord] = []
        links: list[DuplicateLink] = []
        assessment_by_pair = {(a.left_index, a.right_index): a for a in assessments}

        for indices in sorted(clusters.values(), key=lambda xs: min(xs)):
            representative_index = max(indices, key=lambda idx: self._record_quality(records[idx]))
            merged = deepcopy(records[representative_index])
            for idx in indices:
                if idx == representative_index:
                    continue
                self._merge(merged, records[idx])
                pair = (min(representative_index, idx), max(representative_index, idx))
                assessment = assessment_by_pair.get(pair)
                if assessment is None:
                    # Transitive cluster edge: locate any AUTO_MERGE edge joining the
                    # record to another member of the same cluster.
                    candidates = [
                        a for a in assessments
                        if a.decision is DeduplicationDecision.AUTO_MERGE
                        and idx in (a.left_index, a.right_index)
                        and (a.left_index in indices and a.right_index in indices)
                    ]
                    assessment = max(candidates, key=lambda a: a.probability) if candidates else None
                links.append(
                    DuplicateLink(
                        kept_index=representative_index,
                        removed_index=idx,
                        rule=(self._rule_code(assessment, records[representative_index], records[idx]) if assessment else "transitive_auto_merge"),
                        score=(assessment.probability if assessment else 1.0),
                        decision=DeduplicationDecision.AUTO_MERGE,
                    )
                )
            merged.metadata.setdefault("metaevidence_cluster_size", len(indices))
            merged.metadata.setdefault("metaevidence_cluster_members", sorted(indices))
            merged_records.append(merged)

        stats = DeduplicationStats(
            input_records=n,
            candidate_pairs=len(pairs),
            assessed_pairs=len(assessments),
            auto_merge_pairs=sum(a.decision is DeduplicationDecision.AUTO_MERGE for a in assessments),
            review_pairs=len(review_queue),
            output_records=len(merged_records),
            used_exhaustive_pairing=exhaustive,
        )
        return DeduplicationResult(merged_records, links, assessments, review_queue, stats)

    def _features(self, a: EvidenceRecord, b: EvidenceRecord) -> MatchFeatures:
        doi_exact = float(bool(a.doi and b.doi and a.doi == b.doi))
        doi_conflict = float(bool(a.doi and b.doi and a.doi != b.doi))

        exacts = 0
        conflicts = 0
        for attr in ("pmid", "wos_ut", "scopus_eid", "openalex_id"):
            av, bv = getattr(a, attr), getattr(b, attr)
            if av and bv:
                if str(av).strip().lower() == str(bv).strip().lower():
                    exacts += 1
                else:
                    conflicts += 1

        form_a, form_b = _publication_form(a), _publication_form(b)
        form_conflict = float(bool(form_a and form_b and form_a != form_b))

        title_sim = _similarity(a.title, b.title)
        title_jaccard = _jaccard(_substantive_tokens(a.title), _substantive_tokens(b.title))
        author_sim = _author_similarity(a, b)
        year_sim = _year_similarity(a.year, b.year)
        journal_sim = _similarity(a.journal, b.journal)

        return MatchFeatures(
            doi_exact=doi_exact,
            doi_conflict=doi_conflict,
            strong_id_exact=1.0 if exacts else 0.0,
            strong_id_conflict=1.0 if conflicts else 0.0,
            publication_form_conflict=form_conflict,
            title_similarity=title_sim,
            title_token_jaccard=title_jaccard,
            author_similarity=author_sim,
            year_similarity=year_sim,
            journal_similarity=journal_sim,
            volume_exact=_field_exact(_metadata_text(a, "volume"), _metadata_text(b, "volume")),
            issue_exact=_field_exact(_metadata_text(a, "issue", "number"), _metadata_text(b, "issue", "number")),
            pages_exact=_field_exact(
                _metadata_text(a, "pages", "page", "page_range"),
                _metadata_text(b, "pages", "page", "page_range"),
            ),
        )

    def _weighted_probability(self, features: MatchFeatures) -> tuple[float, list[EvidenceContribution]]:
        logit = self.intercept
        contributions: list[EvidenceContribution] = []
        for name, value in features.to_dict().items():
            if value is None:
                continue
            weight = self.weights.get(name, 0.0)
            contribution = weight * float(value)
            logit += contribution
            if float(value) != 0.0:
                contributions.append(EvidenceContribution(name, float(value), weight, contribution))
        return _sigmoid(logit), contributions

    def candidate_pairs(self, records: list[EvidenceRecord]) -> tuple[set[tuple[int, int]], bool]:
        """Return candidate pairs and whether exhaustive all-pairs comparison was used.

        Exposed for benchmarking blocking recall and computational reduction. Callers
        should not interpret absence from a blocked candidate set as proof that two
        records are different.
        """
        return self._candidate_pairs(records)

    def _candidate_pairs(self, records: list[EvidenceRecord]) -> tuple[set[tuple[int, int]], bool]:
        n = len(records)
        if n <= self.exhaustive_limit:
            return {(i, j) for i in range(n) for j in range(i + 1, n)}, True

        blocks: dict[str, list[int]] = defaultdict(list)
        for idx, r in enumerate(records):
            if r.doi:
                blocks[f"doi:{r.doi}"].append(idx)
            for attr in ("pmid", "wos_ut", "scopus_eid", "openalex_id"):
                value = getattr(r, attr)
                if value:
                    blocks[f"{attr}:{str(value).lower()}"].append(idx)

            title = _norm_text(r.title)
            if title:
                blocks[f"title_exact:{title}"].append(idx)
                sig_tokens = sorted(_substantive_tokens(r.title))[:4]
                if sig_tokens:
                    sig = "|".join(sig_tokens)
                    if r.year is not None:
                        for y in (r.year - 1, r.year, r.year + 1):
                            blocks[f"title_sig_year:{sig}:{y}"].append(idx)
                    else:
                        blocks[f"title_sig:{sig}"].append(idx)

            lead = _lead_author_key(r)
            if lead and r.year is not None:
                for y in (r.year - 1, r.year, r.year + 1):
                    blocks[f"author_year:{lead}:{y}"].append(idx)

            journal = _norm_text(r.journal)
            volume = _metadata_text(r, "volume")
            pages = _metadata_text(r, "pages", "page", "page_range")
            if journal and volume and pages:
                blocks[f"jvp:{journal}:{_norm_text(volume)}:{_norm_text(pages)}"].append(idx)

        pairs: set[tuple[int, int]] = set()
        for members in blocks.values():
            unique = sorted(set(members))
            # Extremely broad blocks can recreate quadratic behavior; skip them.
            if len(unique) > 500:
                continue
            for p, i in enumerate(unique):
                for j in unique[p + 1:]:
                    pairs.add((i, j))
        return pairs, False


    @staticmethod
    def _rule_code(assessment: MatchAssessment, a: EvidenceRecord, b: EvidenceRecord) -> str:
        if assessment.features.doi_exact:
            return "doi_exact"
        for attr in ("pmid", "wos_ut", "scopus_eid", "openalex_id"):
            av, bv = getattr(a, attr), getattr(b, attr)
            if av and bv and str(av).strip().lower() == str(bv).strip().lower():
                return f"{attr}_exact"
        if _norm_text(a.title) and _norm_text(a.title) == _norm_text(b.title):
            return "title_exact_guarded"
        if (assessment.features.title_similarity or 0.0) >= 0.9:
            return "title_fuzzy_confidence"
        return "confidence_auto_merge"

    @staticmethod
    def _record_quality(record: EvidenceRecord) -> float:
        score = 0.0
        score += 4.0 if record.doi else 0.0
        score += 2.0 if record.abstract else 0.0
        score += min(len(record.authors), 5) * 0.3
        score += 1.0 if record.journal else 0.0
        score += 0.8 if record.year else 0.0
        score += len(record.identifiers) * 0.5
        score += min(len(record.source_hits), 5) * 0.25
        score += min(len(record.title), 200) / 200.0
        return score

    @staticmethod
    def _merge(target: EvidenceRecord, other: EvidenceRecord) -> None:
        seen = {(h.source, h.source_id) for h in target.source_hits}
        for hit in other.source_hits:
            if (hit.source, hit.source_id) not in seen:
                target.source_hits.append(deepcopy(hit))
                seen.add((hit.source, hit.source_id))

        conflicts: dict[str, list[object]] = target.metadata.setdefault("metaevidence_conflicts", {})
        for attr in ("doi", "pmid", "wos_ut", "scopus_eid", "openalex_id", "abstract", "journal", "year"):
            tv, ov = getattr(target, attr), getattr(other, attr)
            if tv in (None, "") and ov not in (None, ""):
                setattr(target, attr, deepcopy(ov))
            elif tv not in (None, "") and ov not in (None, "") and tv != ov:
                bucket = conflicts.setdefault(attr, [])
                for value in (tv, ov):
                    if value not in bucket:
                        bucket.append(deepcopy(value))
        if not target.authors and other.authors:
            target.authors = list(other.authors)
        elif target.authors and other.authors and target.authors != other.authors:
            conflicts.setdefault("authors", [])
            for value in (target.authors, other.authors):
                if value not in conflicts["authors"]:
                    conflicts["authors"].append(deepcopy(value))

        for k, v in other.metadata.items():
            if k not in target.metadata:
                target.metadata[k] = deepcopy(v)


# Public default from v0.4 onward. The old constructor's ``fuzzy_threshold``
# remains accepted for compatibility with v0.1-v0.3 code.
DeduplicationEngine = ConfidenceDeduplicationEngine
