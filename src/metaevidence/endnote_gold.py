from __future__ import annotations

"""Streaming import of EndNote XML gold-standard deduplication corpora.

The Beller/Systematic Review Accelerator benchmark corpora distributed in EndNote
XML encode duplicate-removal truth through the record ``caption`` field: records
captioned ``Duplicate`` are removable duplicate citations; an absent/blank caption
is treated as the retained/unique citation.  This module deliberately imports the
truth label separately from bibliographic metadata so the deduplication engine
never receives the gold label as an input feature.
"""

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Iterator

from .external_validation import ExternalRemovalGoldDataset
from .models import EvidenceRecord, SourceHit


def _node_text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    text = " ".join("".join(node.itertext()).split())
    return text or None


def _first_text(record: ET.Element, *paths: str) -> str | None:
    for path in paths:
        value = _node_text(record.find(path))
        if value:
            return value
    return None


def _all_text(record: ET.Element, path: str) -> list[str]:
    values: list[str] = []
    for node in record.findall(path):
        value = _node_text(node)
        if value:
            values.append(value)
    return values


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(18|19|20|21)\d{2}\b", value)
    return int(match.group(0)) if match else None


def _normalise_label(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class EndNoteXMLImportStats:
    path: str
    sha256: str
    records: int
    duplicates_removed: int
    retained_records: int
    labelled_records: int
    unrecognised_captions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "records": self.records,
            "duplicates_removed": self.duplicates_removed,
            "retained_records": self.retained_records,
            "labelled_records": self.labelled_records,
            "unrecognised_captions": list(self.unrecognised_captions),
        }


@dataclass(slots=True)
class EndNoteXMLGoldImport:
    dataset: ExternalRemovalGoldDataset
    stats: EndNoteXMLImportStats
    warnings: list[str] = field(default_factory=list)


class EndNoteXMLGoldReader:
    """Read EndNote XML as a record-level duplicate-removal gold standard.

    The reader uses ``xml.etree.ElementTree.iterparse`` so corpora tens of
    megabytes in size can be processed without loading the complete XML tree.
    Gold labels are stored only in ``ExternalRemovalGoldDataset.gold_removed``
    and audit metadata; ``EvidenceRecord`` matching fields never contain the
    caption value.
    """

    def __init__(
        self,
        *,
        duplicate_caption: str = "Duplicate",
        strict_captions: bool = True,
        blank_caption_is_retained: bool = True,
    ) -> None:
        self.duplicate_caption = _normalise_label(duplicate_caption)
        self.strict_captions = strict_captions
        self.blank_caption_is_retained = blank_caption_is_retained

    def _iter_records(self, path: Path) -> Iterator[ET.Element]:
        # The benchmark files use a compact, often single-line EndNote XML
        # representation, hence line-oriented parsing is inappropriate.
        for event, elem in ET.iterparse(path, events=("end",)):
            if elem.tag == "record":
                yield elem
                elem.clear()

    def read(self, path: str | Path, *, name: str | None = None) -> EndNoteXMLGoldImport:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)

        records: list[EvidenceRecord] = []
        gold_removed: list[bool] = []
        record_ids: list[str] = []
        warnings: list[str] = []
        unknown_labels: set[str] = set()
        labelled = 0
        seen_ids: set[str] = set()

        for index, record in enumerate(self._iter_records(path), start=1):
            raw_id = _first_text(record, "rec-number") or f"ROW-{index:07d}"
            rid = raw_id
            if rid in seen_ids:
                rid = f"{rid}__ROW{index}"
                warnings.append(f"Duplicate rec-number normalized at record {index}")
            seen_ids.add(rid)

            raw_caption = _first_text(record, "caption")
            norm_caption = _normalise_label(raw_caption)
            if norm_caption == self.duplicate_caption:
                is_removed = True
                labelled += 1
            elif not norm_caption and self.blank_caption_is_retained:
                is_removed = False
            else:
                if raw_caption:
                    unknown_labels.add(raw_caption)
                if self.strict_captions:
                    raise ValueError(
                        f"Unrecognised EndNote caption {raw_caption!r} at record {rid}; "
                        f"expected {self.duplicate_caption!r} or blank"
                    )
                is_removed = False
                warnings.append(
                    f"Unrecognised caption {raw_caption!r} treated as retained at record {rid}"
                )

            title = _first_text(record, "titles/title") or ""
            authors = _all_text(record, "contributors/authors/author")
            journal = _first_text(
                record,
                "periodical/full-title",
                "titles/secondary-title",
                "titles/alt-title",
            )
            year = _parse_year(_first_text(record, "dates/year", "dates/pub-dates/date", "edition"))
            abstract = _first_text(record, "abstract")
            doi = _first_text(record, "electronic-resource-num")
            accession = _first_text(record, "accession-num")
            database = _first_text(record, "database")

            # EndNote exports commonly put a PubMed ID in accession-num for NLM
            # records.  We only promote purely numeric accessions to PMID.
            pmid = accession if accession and accession.isdigit() else None

            metadata: dict[str, object] = {
                "external_record_id": rid,
                # Label is retained for audit only. The matching engine never
                # consumes metadata keys containing external_gold_*.
                "external_gold_removal_label": raw_caption or "",
                "external_gold_removed": is_removed,
                "endnote_ref_type": _first_text(record, "ref-type"),
            }
            for key, paths in {
                "volume": ("volume",),
                "issue": ("number",),
                "pages": ("pages",),
                "language": ("language",),
                "pmc_id": ("custom2",),
            }.items():
                value = _first_text(record, *paths)
                if value:
                    metadata[key] = value

            source_hits = [SourceHit(source=database, source_id=rid)] if database else []
            records.append(
                EvidenceRecord(
                    title=title,
                    authors=authors,
                    year=year,
                    journal=journal,
                    abstract=abstract,
                    doi=doi,
                    pmid=pmid,
                    source_hits=source_hits,
                    metadata=metadata,
                )
            )
            gold_removed.append(is_removed)
            record_ids.append(rid)

        if not records:
            raise ValueError(f"No <record> elements found in EndNote XML: {path}")

        dataset = ExternalRemovalGoldDataset(
            name=name or path.stem,
            records=records,
            gold_removed=gold_removed,
            record_ids=record_ids,
            source_path=str(path),
            label_column="EndNote <caption>",
            field_map={
                "record_id": "rec-number",
                "title": "titles/title",
                "authors": "contributors/authors/author",
                "year": "dates/year",
                "journal": "periodical/full-title|titles/secondary-title",
                "abstract": "abstract",
                "doi": "electronic-resource-num",
                "pmid": "accession-num when numeric",
                "removal_label": "caption",
            },
            warnings=list(warnings),
        )
        stats = EndNoteXMLImportStats(
            path=str(path),
            sha256=_sha256(path),
            records=dataset.n_records,
            duplicates_removed=dataset.n_gold_duplicates_removed,
            retained_records=dataset.n_gold_publications,
            labelled_records=labelled,
            unrecognised_captions=tuple(sorted(unknown_labels)),
        )
        return EndNoteXMLGoldImport(dataset=dataset, stats=stats, warnings=warnings)


def load_endnote_xml_gold(
    path: str | Path,
    *,
    name: str | None = None,
    duplicate_caption: str = "Duplicate",
    strict_captions: bool = True,
) -> EndNoteXMLGoldImport:
    """Convenience wrapper for :class:`EndNoteXMLGoldReader`."""
    return EndNoteXMLGoldReader(
        duplicate_caption=duplicate_caption,
        strict_captions=strict_captions,
    ).read(path, name=name)
