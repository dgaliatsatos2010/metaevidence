from __future__ import annotations

from dataclasses import dataclass, field
import csv
import json
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable, Sequence

from .ids import stable_record_id
from .models import EvidenceRecord, SourceHit
from .screening import ScreeningDecision, ScreeningLedger, ScreeningStage
from .study_linkage import StudyLinkageResult


@dataclass(slots=True)
class ImportWarning:
    row: int | None
    message: str


@dataclass(slots=True)
class ImportResult:
    records: list[EvidenceRecord]
    ledger: ScreeningLedger = field(default_factory=ScreeningLedger)
    warnings: list[ImportWarning] = field(default_factory=list)


def _join(values: Iterable[str]) -> str:
    return "; ".join(v for v in values if v)


def _study_map(linkage: StudyLinkageResult | None) -> dict[int, str]:
    if linkage is None:
        return {}
    out: dict[int, str] = {}
    for family in linkage.families:
        for i in family.member_indices:
            out[i] = family.study_id
    return out


def _screening_fields(record: EvidenceRecord, ledger: ScreeningLedger | None) -> dict[str, str | int | None]:
    if ledger is None:
        return {
            "title_abstract_decision": None,
            "full_text_decision": None,
            "exclusion_reason_code": None,
            "exclusion_reason_text": None,
        }
    ta = ledger.final_event(record, ScreeningStage.TITLE_ABSTRACT)
    ft = ledger.final_event(record, ScreeningStage.FULL_TEXT)
    final = ft or ta
    return {
        "title_abstract_decision": ta.decision.value if ta else ScreeningDecision.NOT_SCREENED.value,
        "full_text_decision": ft.decision.value if ft else ScreeningDecision.NOT_SCREENED.value,
        "exclusion_reason_code": final.reason_code if final and final.decision is ScreeningDecision.EXCLUDE else None,
        "exclusion_reason_text": final.reason_text if final and final.decision is ScreeningDecision.EXCLUDE else None,
    }


def record_to_row(
    record: EvidenceRecord,
    *,
    index: int | None = None,
    ledger: ScreeningLedger | None = None,
    linkage: StudyLinkageResult | None = None,
) -> dict[str, object]:
    study_id = _study_map(linkage).get(index) if index is not None else None
    row: dict[str, object] = {
        "record_id": stable_record_id(record),
        "title": record.title,
        "abstract": record.abstract or "",
        "authors": _join(record.authors),
        "year": record.year or "",
        "journal": record.journal or "",
        "doi": record.doi or "",
        "pmid": record.pmid or "",
        "wos_ut": record.wos_ut or "",
        "scopus_eid": record.scopus_eid or "",
        "openalex_id": record.openalex_id or "",
        "sources": _join(record.sources),
        "study_id": study_id or "",
    }
    row.update(_screening_fields(record, ledger))
    return row


def write_csv(
    records: Sequence[EvidenceRecord],
    path: str | Path,
    *,
    ledger: ScreeningLedger | None = None,
    linkage: StudyLinkageResult | None = None,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [record_to_row(r, index=i, ledger=ledger, linkage=linkage) for i, r in enumerate(records)]
    fieldnames = list(rows[0].keys()) if rows else ["record_id", "title", "abstract"]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out


def write_jsonl(
    records: Sequence[EvidenceRecord],
    path: str | Path,
    *,
    ledger: ScreeningLedger | None = None,
    linkage: StudyLinkageResult | None = None,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for i, record in enumerate(records):
            row = record_to_row(record, index=i, ledger=ledger, linkage=linkage)
            row["metadata"] = record.metadata
            row["source_hits"] = [h.__dict__ if hasattr(h, "__dict__") else {
                "source": h.source, "source_id": h.source_id, "query": h.query,
                "retrieved_at": h.retrieved_at, "rank": h.rank,
            } for h in record.source_hits]
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return out


def _doi_url(doi: str | None) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def write_asreview_csv(records: Sequence[EvidenceRecord], path: str | Path, *, ledger: ScreeningLedger | None = None) -> Path:
    """Write a tabular dataset accepted by current ASReview LAB versions.

    ``MAYBE`` and unresolved disagreements remain blank rather than being coerced
    into a binary relevance label.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["title", "abstract", "authors", "year", "doi", "url", "included"]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            label = ledger.asreview_label(record) if ledger else None
            writer.writerow({
                "title": record.title,
                "abstract": record.abstract or "",
                "authors": _join(record.authors),
                "year": record.year or "",
                "doi": record.doi or "",
                "url": _doi_url(record.doi),
                "included": "" if label is None else label,
            })
    return out


def _ris_clean(value: str | None) -> str:
    return " ".join((value or "").replace("\r", " ").replace("\n", " ").split())


def _ris_type(record: EvidenceRecord) -> str:
    value = str(record.metadata.get("publication_type") or record.metadata.get("type") or "").lower()
    if "conference" in value:
        return "CONF"
    if "book" in value:
        return "BOOK"
    if "thesis" in value or "dissertation" in value:
        return "THES"
    return "JOUR"


def write_ris(
    records: Sequence[EvidenceRecord],
    path: str | Path,
    *,
    ledger: ScreeningLedger | None = None,
    asreview_labels: bool = False,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            def tag(name: str, value: object) -> None:
                text = _ris_clean(str(value)) if value not in (None, "") else ""
                if text:
                    fh.write(f"{name}  - {text}\n")

            tag("TY", _ris_type(record))
            tag("ID", stable_record_id(record))
            tag("TI", record.title)
            for author in record.authors:
                tag("AU", author)
            tag("PY", record.year)
            tag("JO", record.journal)
            tag("AB", record.abstract)
            tag("DO", record.doi)
            if record.doi:
                tag("UR", _doi_url(record.doi))
            if record.pmid:
                tag("AN", f"PMID:{record.pmid}")
            for source in record.sources:
                tag("N1", f"MetaEvidence_source:{source}")
            if asreview_labels:
                label = ledger.asreview_label(record) if ledger else None
                note = "ASReview_not_seen" if label is None else ("ASReview_relevant" if label == 1 else "ASReview_irrelevant")
                tag("N1", note)
            fh.write("ER  -\n\n")
    return out


def _bib_escape(value: str) -> str:
    value = value.replace("\\", "\\textbackslash{}")
    for char in ("{", "}", "#", "%", "&", "_"):
        value = value.replace(char, "\\" + char)
    return value.replace("\n", " ").replace("\r", " ")


def _bib_key(record: EvidenceRecord, index: int) -> str:
    surname = "record"
    if record.authors:
        tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+", record.authors[0])
        if tokens:
            surname = tokens[0].lower()
    return re.sub(r"[^a-zA-Z0-9:_-]+", "", f"{surname}{record.year or 'nd'}_{index+1}") or f"record{index+1}"


def write_bibtex(records: Sequence[EvidenceRecord], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for i, record in enumerate(records):
            fh.write(f"@article{{{_bib_key(record, i)},\n")
            fields = [
                ("title", record.title),
                ("author", " and ".join(record.authors)),
                ("journal", record.journal or ""),
                ("year", str(record.year) if record.year else ""),
                ("doi", record.doi or ""),
                ("abstract", record.abstract or ""),
            ]
            populated = [(k, v) for k, v in fields if v]
            for j, (key, value) in enumerate(populated):
                comma = "," if j < len(populated) - 1 else ""
                fh.write(f"  {key} = {{{_bib_escape(value)}}}{comma}\n")
            fh.write("}\n\n")
    return out


def _split_authors(value: str) -> list[str]:
    if not value.strip():
        return []
    if " and " in value:
        return [x.strip() for x in value.split(" and ") if x.strip()]
    return [x.strip() for x in re.split(r"\s*;\s*", value) if x.strip()]


def _first(row: dict[str, str], *names: str) -> str:
    lowered = {k.strip().lower(): (v or "") for k, v in row.items()}
    for name in names:
        if lowered.get(name.lower(), "").strip():
            return lowered[name.lower()].strip()
    return ""


def read_csv(path: str | Path, *, source: str = "csv_import", reviewer: str = "import") -> ImportResult:
    records: list[EvidenceRecord] = []
    ledger = ScreeningLedger(require_full_text_exclusion_reason=False)
    warnings: list[ImportWarning] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row_number, row in enumerate(reader, start=2):
            title = _first(row, "title", "primary_title")
            abstract = _first(row, "abstract", "abstract_note", "abstract note")
            if not title and not abstract:
                warnings.append(ImportWarning(row_number, "Skipped row without title or abstract"))
                continue
            year_text = _first(row, "year", "publication_year", "py")
            year = int(year_text) if year_text.isdigit() and len(year_text) == 4 else None
            doi = _first(row, "doi")
            if doi.startswith("http://doi.org/") or doi.startswith("https://doi.org/"):
                doi = doi.split("doi.org/", 1)[1]
            record = EvidenceRecord(
                title=title or abstract[:120],
                abstract=abstract or None,
                authors=_split_authors(_first(row, "authors", "author_names", "author names", "first_authors")),
                year=year,
                journal=_first(row, "journal", "jo", "source") or None,
                doi=doi or None,
                source_hits=[SourceHit(source=source, source_id=_first(row, "record_id", "id") or None)],
            )
            records.append(record)
            label = _first(row, "included", "label", "final_included", "label_included", "included_label", "included_final", "included_flag", "include")
            if label != "":
                normalized = label.strip().lower()
                if normalized in {"1", "true", "yes", "include", "included", "relevant"}:
                    ledger.add(record, ScreeningDecision.INCLUDE, reviewer=reviewer, metadata={"source": source})
                elif normalized in {"0", "false", "no", "exclude", "excluded", "irrelevant"}:
                    ledger.add(record, ScreeningDecision.EXCLUDE, reviewer=reviewer, metadata={"source": source})
                else:
                    warnings.append(ImportWarning(row_number, f"Unrecognized screening label: {label}"))
    return ImportResult(records, ledger, warnings)


def _parse_ris(path: str | Path) -> list[dict[str, list[str]]]:
    records: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    with Path(path).open("r", encoding="utf-8-sig", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            match = re.match(r"^([A-Z0-9]{2})  -(?:\s?(.*))?$", line)
            if match:
                tag, value = match.group(1), (match.group(2) or "").strip()
                if tag == "ER":
                    if current:
                        records.append(current)
                    current = {}
                else:
                    current.setdefault(tag, []).append(value)
            elif line.strip() and current:
                # Continuation line: append to the most recently emitted tag.
                last_tag = next(reversed(current))
                current[last_tag][-1] += " " + line.strip()
    if current:
        records.append(current)
    return records


def read_ris(path: str | Path, *, source: str = "ris_import", reviewer: str = "import") -> ImportResult:
    records: list[EvidenceRecord] = []
    ledger = ScreeningLedger(require_full_text_exclusion_reason=False)
    warnings: list[ImportWarning] = []
    for i, item in enumerate(_parse_ris(path), start=1):
        title = (item.get("TI") or item.get("T1") or [""])[0]
        abstract = (item.get("AB") or item.get("N2") or [""])[0]
        if not title and not abstract:
            warnings.append(ImportWarning(i, "Skipped RIS record without title or abstract"))
            continue
        py = (item.get("PY") or item.get("Y1") or [""])[0]
        m = re.search(r"\b(19|20|21)\d{2}\b", py)
        doi = (item.get("DO") or [""])[0]
        record = EvidenceRecord(
            title=title or abstract[:120],
            abstract=abstract or None,
            authors=list(item.get("AU") or item.get("A1") or []),
            year=int(m.group(0)) if m else None,
            journal=(item.get("JO") or item.get("JF") or item.get("T2") or [""])[0] or None,
            doi=doi or None,
            source_hits=[SourceHit(source=source, source_id=(item.get("ID") or [None])[0])],
        )
        records.append(record)
        notes = item.get("N1", [])
        if any(x == "ASReview_relevant" for x in notes):
            ledger.add(record, ScreeningDecision.INCLUDE, reviewer=reviewer, metadata={"source": source})
        elif any(x == "ASReview_irrelevant" for x in notes):
            ledger.add(record, ScreeningDecision.EXCLUDE, reviewer=reviewer, metadata={"source": source})
        # ASReview_not_seen intentionally yields no event.
    return ImportResult(records, ledger, warnings)


def write_screening_bundle(
    records: Sequence[EvidenceRecord],
    directory: str | Path,
    *,
    ledger: ScreeningLedger | None = None,
    linkage: StudyLinkageResult | None = None,
) -> dict[str, Path]:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "records_csv": write_csv(records, out / "records.csv", ledger=ledger, linkage=linkage),
        "records_jsonl": write_jsonl(records, out / "records.jsonl", ledger=ledger, linkage=linkage),
        "records_ris": write_ris(records, out / "records.ris", ledger=ledger),
        "records_bibtex": write_bibtex(records, out / "records.bib"),
        "asreview_csv": write_asreview_csv(records, out / "asreview.csv", ledger=ledger),
        "asreview_ris": write_ris(records, out / "asreview.ris", ledger=ledger, asreview_labels=True),
    }
    if ledger is not None:
        paths["screening_audit_jsonl"] = ledger.write_jsonl(out / "screening_audit.jsonl")
        paths["screening_audit_csv"] = ledger.write_csv(out / "screening_audit.csv")
    if linkage is not None:
        paths["study_families_csv"] = linkage.write_families_csv(out / "study_families.csv")
        paths["double_counting_csv"] = linkage.write_double_counting_csv(out / "double_counting_risks.csv")
    manifest = {
        "format_version": "MetaEvidence-screening-bundle-1",
        "record_count": len(records),
        "files": {
            k: {
                "name": v.name,
                "sha256": sha256(v.read_bytes()).hexdigest(),
                "bytes": v.stat().st_size,
            }
            for k, v in sorted(paths.items())
        },
    }
    manifest_path = out / "bundle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    paths["manifest"] = manifest_path
    return paths
