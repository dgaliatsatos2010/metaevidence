from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import csv
import json
import platform
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

from .dedup import DeduplicationResult
from .ids import stable_record_id
from .models import EvidenceRecord
from .screening import ScreeningDecision, ScreeningLedger, ScreeningStage
from .search import MultiSearchResult
from .study_linkage import StudyLinkageResult


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PrismaAccountingError(ValueError):
    """Raised when PRISMA accounting is internally inconsistent in strict mode."""


@dataclass(slots=True)
class PrismaFlow:
    """Machine-readable PRISMA 2020 study-selection accounting.

    The object stores *observed workflow counts*.  It supports PRISMA reporting but
    intentionally does not assert that a review is PRISMA-compliant; compliance
    depends on the complete review report and human methodological decisions.
    """

    databases: dict[str, int] = field(default_factory=dict)
    registers: dict[str, int] = field(default_factory=dict)
    other_sources: dict[str, int] = field(default_factory=dict)
    duplicates_removed: int = 0
    automation_removed_before_screening: int = 0
    other_removed_before_screening: int = 0
    records_screened: int = 0
    records_excluded: int = 0
    reports_sought_for_retrieval: int = 0
    reports_not_retrieved: int = 0
    reports_assessed_for_eligibility: int = 0
    reports_excluded: dict[str, int] = field(default_factory=dict)
    studies_included: int | None = None
    reports_included: int = 0
    generated_at_utc: str = field(default_factory=_utcnow)
    warnings: list[str] = field(default_factory=list)
    schema_version: str = "MetaEvidence-PRISMA-flow-1"

    @property
    def records_identified_databases(self) -> int:
        return sum(self.databases.values())

    @property
    def records_identified_registers(self) -> int:
        return sum(self.registers.values())

    @property
    def records_identified_other_sources(self) -> int:
        return sum(self.other_sources.values())

    @property
    def total_records_identified(self) -> int:
        return self.records_identified_databases + self.records_identified_registers + self.records_identified_other_sources

    @property
    def records_after_pre_screening_removals(self) -> int:
        return max(
            0,
            self.total_records_identified
            - self.duplicates_removed
            - self.automation_removed_before_screening
            - self.other_removed_before_screening,
        )

    @property
    def reports_excluded_total(self) -> int:
        return sum(self.reports_excluded.values())

    def consistency_warnings(self) -> list[str]:
        warnings: list[str] = []
        nonnegative = {
            "duplicates_removed": self.duplicates_removed,
            "automation_removed_before_screening": self.automation_removed_before_screening,
            "other_removed_before_screening": self.other_removed_before_screening,
            "records_screened": self.records_screened,
            "records_excluded": self.records_excluded,
            "reports_sought_for_retrieval": self.reports_sought_for_retrieval,
            "reports_not_retrieved": self.reports_not_retrieved,
            "reports_assessed_for_eligibility": self.reports_assessed_for_eligibility,
            "reports_included": self.reports_included,
        }
        for name, value in nonnegative.items():
            if value < 0:
                warnings.append(f"{name} cannot be negative")
        if self.duplicates_removed > self.total_records_identified:
            warnings.append("duplicates_removed exceeds total records identified")
        if self.records_screened > self.records_after_pre_screening_removals:
            warnings.append("records_screened exceeds records remaining after pre-screening removals")
        if self.records_excluded > self.records_screened:
            warnings.append("records_excluded exceeds records_screened")
        expected_reports_sought = self.records_screened - self.records_excluded
        if self.records_screened and self.reports_sought_for_retrieval != expected_reports_sought:
            warnings.append(
                "reports_sought_for_retrieval does not equal records_screened - records_excluded; "
                "the selection flow may be incomplete or contain unresolved records"
            )
        if self.reports_not_retrieved > self.reports_sought_for_retrieval:
            warnings.append("reports_not_retrieved exceeds reports_sought_for_retrieval")
        expected_assessed = self.reports_sought_for_retrieval - self.reports_not_retrieved
        if self.reports_assessed_for_eligibility != expected_assessed:
            warnings.append(
                "reports_assessed_for_eligibility does not equal reports_sought_for_retrieval - reports_not_retrieved"
            )
        resolved_reports = self.reports_excluded_total + self.reports_included
        if resolved_reports > self.reports_assessed_for_eligibility:
            warnings.append("full-text exclusions plus included reports exceed reports assessed for eligibility")
        elif self.reports_assessed_for_eligibility and resolved_reports < self.reports_assessed_for_eligibility:
            warnings.append("one or more reports assessed for eligibility do not yet have a resolved include/exclude outcome")
        if self.studies_included is not None and self.studies_included > self.reports_included:
            warnings.append("studies_included exceeds reports_included")
        return warnings

    def validate(self, *, strict: bool = False) -> list[str]:
        warnings = self.consistency_warnings()
        if strict and warnings:
            raise PrismaAccountingError("; ".join(warnings))
        return warnings

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["summary"] = {
            "records_identified_databases": self.records_identified_databases,
            "records_identified_registers": self.records_identified_registers,
            "records_identified_other_sources": self.records_identified_other_sources,
            "total_records_identified": self.total_records_identified,
            "records_after_pre_screening_removals": self.records_after_pre_screening_removals,
            "reports_excluded_total": self.reports_excluded_total,
        }
        data["consistency_warnings"] = self.consistency_warnings()
        return data

    def write_json(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return out

    def write_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        rows: list[tuple[str, str, int | str]] = []
        rows.extend(("database", k, v) for k, v in sorted(self.databases.items()))
        rows.extend(("register", k, v) for k, v in sorted(self.registers.items()))
        rows.extend(("other_source", k, v) for k, v in sorted(self.other_sources.items()))
        scalar_rows = {
            "duplicates_removed": self.duplicates_removed,
            "automation_removed_before_screening": self.automation_removed_before_screening,
            "other_removed_before_screening": self.other_removed_before_screening,
            "records_screened": self.records_screened,
            "records_excluded": self.records_excluded,
            "reports_sought_for_retrieval": self.reports_sought_for_retrieval,
            "reports_not_retrieved": self.reports_not_retrieved,
            "reports_assessed_for_eligibility": self.reports_assessed_for_eligibility,
            "reports_included": self.reports_included,
            "studies_included": "" if self.studies_included is None else self.studies_included,
        }
        rows.extend(("flow", k, v) for k, v in scalar_rows.items())
        rows.extend(("full_text_exclusion", k, v) for k, v in sorted(self.reports_excluded.items()))
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["category", "label", "count"])
            writer.writerows(rows)
        return out

    def write_mermaid(self, path: str | Path) -> Path:
        """Write an editable Mermaid flow representation, not an official PRISMA template."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        studies = "?" if self.studies_included is None else str(self.studies_included)
        text = f"""flowchart TD
    A[Records identified\\nDatabases: {self.records_identified_databases}\\nRegisters: {self.records_identified_registers}\\nOther: {self.records_identified_other_sources}]
    B[Removed before screening\\nDuplicates: {self.duplicates_removed}\\nAutomation: {self.automation_removed_before_screening}\\nOther: {self.other_removed_before_screening}]
    C[Records screened\\nn={self.records_screened}]
    D[Records excluded\\nn={self.records_excluded}]
    E[Reports sought for retrieval\\nn={self.reports_sought_for_retrieval}]
    F[Reports not retrieved\\nn={self.reports_not_retrieved}]
    G[Reports assessed for eligibility\\nn={self.reports_assessed_for_eligibility}]
    H[Reports excluded\\nn={self.reports_excluded_total}]
    I[Included\\nStudies: {studies}\\nReports: {self.reports_included}]
    A --> B --> C
    C --> D
    C --> E
    E --> F
    E --> G
    G --> H
    G --> I
"""
        out.write_text(text, encoding="utf-8")
        return out


@dataclass(slots=True)
class PrismaSearchContext:
    """Human-supplied PRISMA-S context that cannot be inferred safely from APIs."""

    study_registries: list[str] = field(default_factory=list)
    online_resources: list[str] = field(default_factory=list)
    citation_searching: str | None = None
    contacts: str | None = None
    other_methods: str | None = None
    limits_and_restrictions: str | None = None
    limits_justification: str | None = None
    search_filters: str | None = None
    prior_work: str | None = None
    updates: str | None = None
    peer_review: str | None = None
    search_designer: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class PrismaSSupportItem:
    item: int
    topic: str
    status: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PrismaSearchSource:
    source: str
    database_name: str
    platform: str
    translated_query: str
    canonical_query: str
    retrieved_count: int
    total_available: int | None
    search_started_at_utc: str | None
    search_finished_at_utc: str | None
    fidelity_score: float | None
    loss_score: float | None
    requires_review: bool
    truncated: bool
    warnings: list[str] = field(default_factory=list)
    limits: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PLATFORM_MAP: dict[str, tuple[str, str]] = {
    "pubmed": ("PubMed", "NCBI E-utilities API"),
    "openalex": ("OpenAlex", "OpenAlex API"),
    "crossref": ("Crossref", "Crossref REST API"),
    "europe_pmc": ("Europe PMC", "Europe PMC REST API"),
    "europepmc": ("Europe PMC", "Europe PMC REST API"),
    "scopus": ("Scopus", "Elsevier Scopus API"),
    "web_of_science": ("Web of Science", "Clarivate Web of Science API"),
}


@dataclass(slots=True)
class PrismaSearchReport:
    canonical_query: str
    package_version: str
    sources: list[PrismaSearchSource]
    support_matrix: list[PrismaSSupportItem]
    deduplication_description: str | None = None
    context: PrismaSearchContext = field(default_factory=PrismaSearchContext)
    generated_at_utc: str = field(default_factory=_utcnow)
    disclaimer: str = (
        "This report supports PRISMA 2020 and PRISMA-S reporting. It does not by itself establish "
        "PRISMA compliance or methodological quality."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_query": self.canonical_query,
            "package_version": self.package_version,
            "sources": [x.to_dict() for x in self.sources],
            "support_matrix": [x.to_dict() for x in self.support_matrix],
            "deduplication_description": self.deduplication_description,
            "context": asdict(self.context),
            "generated_at_utc": self.generated_at_utc,
            "disclaimer": self.disclaimer,
        }

    def write_json(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return out

    def write_sources_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "source", "database_name", "platform", "retrieved_count", "total_available",
            "search_started_at_utc", "search_finished_at_utc", "fidelity_score", "loss_score",
            "requires_review", "truncated", "limits", "warnings",
        ]
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for source in self.sources:
                row = source.to_dict()
                row.pop("translated_query")
                row.pop("canonical_query")
                row["limits"] = json.dumps(row["limits"], ensure_ascii=False, sort_keys=True)
                row["warnings"] = " | ".join(row["warnings"])
                writer.writerow(row)
        return out

    def write_strategies_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "source", "database_name", "platform", "canonical_query", "translated_query",
                "fidelity_score", "loss_score", "requires_review", "search_finished_at_utc",
            ])
            for source in self.sources:
                writer.writerow([
                    source.source, source.database_name, source.platform, source.canonical_query,
                    source.translated_query, source.fidelity_score, source.loss_score,
                    source.requires_review, source.search_finished_at_utc,
                ])
        return out

    def write_support_matrix_csv(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["item", "topic", "status", "evidence"])
            writer.writeheader()
            for item in self.support_matrix:
                writer.writerow(item.to_dict())
        return out

    def write_markdown(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# MetaEvidence search reproducibility report",
            "",
            self.disclaimer,
            "",
            f"Generated: {self.generated_at_utc}",
            f"MetaEvidence version: {self.package_version}",
            "",
            "## Canonical search",
            "",
            "```text",
            self.canonical_query,
            "```",
            "",
            "## Information sources and executed strategies",
            "",
        ]
        for src in self.sources:
            lines.extend([
                f"### {src.database_name}",
                "",
                f"- Platform/interface: {src.platform}",
                f"- Records retrieved: {src.retrieved_count}",
                f"- Total available reported by source: {src.total_available if src.total_available is not None else 'not reported'}",
                f"- Search completed (UTC): {src.search_finished_at_utc or 'not recorded'}",
                f"- Translation fidelity diagnostic: {src.fidelity_score if src.fidelity_score is not None else 'not available'}",
                f"- Translation requires human review: {src.requires_review}",
                f"- Retrieval truncated: {src.truncated}",
                "",
                "Executed strategy:",
                "",
                "```text",
                src.translated_query,
                "```",
                "",
            ])
            if src.warnings:
                lines.append("Warnings: " + "; ".join(src.warnings))
                lines.append("")
        lines.extend(["## Deduplication", "", self.deduplication_description or "Not documented in this report.", ""])
        lines.extend(["## PRISMA-S support matrix", "", "| Item | Topic | Status | Evidence |", "|---:|---|---|---|"])
        for item in self.support_matrix:
            evidence = item.evidence.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {item.item} | {item.topic} | {item.status} | {evidence} |")
        lines.extend(["", "## Human-supplied context", ""])
        for key, value in asdict(self.context).items():
            if value:
                lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out


class PrismaBuilder:
    """Build PRISMA 2020 flow accounting and PRISMA-S search documentation."""

    @staticmethod
    def build_flow(
        *,
        search: MultiSearchResult | None = None,
        deduplication: DeduplicationResult | None = None,
        ledger: ScreeningLedger | None = None,
        records: Sequence[EvidenceRecord] | None = None,
        linkage: StudyLinkageResult | None = None,
        registers: dict[str, int] | None = None,
        other_sources: dict[str, int] | None = None,
        automation_removed_before_screening: int = 0,
        other_removed_before_screening: int = 0,
        not_retrieved_record_ids: Iterable[str] | None = None,
        strict: bool = False,
    ) -> PrismaFlow:
        databases = {}
        if search:
            for source, result in search.source_results.items():
                database_name, _ = _PLATFORM_MAP.get(source, (source.replace("_", " ").title(), source))
                databases[database_name] = result.retrieved_count
        flow_warnings: list[str] = []
        if search:
            for source, result in search.source_results.items():
                if result.truncated:
                    flow_warnings.append(
                        f"{source} retrieval was truncated; PRISMA identification counts reflect records actually imported, not all potentially available records."
                    )
            if search.failures:
                flow_warnings.append("One or more information sources failed during retrieval: " + ", ".join(sorted(search.failures)))

        if deduplication and deduplication.stats:
            duplicates_removed = deduplication.stats.input_records - deduplication.stats.output_records
            workflow_records = list(records or deduplication.records)
        else:
            duplicates_removed = 0
            workflow_records = list(records or (search.records if search else []))

        records_screened = 0
        records_excluded = 0
        reports_sought = 0
        reports_not_retrieved = 0
        reports_assessed = 0
        reports_included = 0
        exclusion_reasons: dict[str, int] = {}
        included_ids: set[str] = set()

        if ledger is not None:
            ta_ids = {e.record_id for e in ledger.events if e.stage is ScreeningStage.TITLE_ABSTRACT}
            records_screened = len(ta_ids)
            records_excluded = sum(
                ledger.final_decision(rid, ScreeningStage.TITLE_ABSTRACT) is ScreeningDecision.EXCLUDE
                for rid in ta_ids
            )

            ft_ids = {e.record_id for e in ledger.events if e.stage is ScreeningStage.FULL_TEXT}
            explicit_not_retrieved = {str(x) for x in (not_retrieved_record_ids or [])}
            inferred_not_retrieved: set[str] = set()
            for rid in ft_ids:
                event = ledger.final_event(rid, ScreeningStage.FULL_TEXT)
                if event and event.decision is ScreeningDecision.EXCLUDE and event.reason_code == "NOT_RETRIEVABLE":
                    inferred_not_retrieved.add(rid)
            not_retrieved = explicit_not_retrieved | inferred_not_retrieved
            reports_sought = len(ft_ids | not_retrieved)
            reports_not_retrieved = len(not_retrieved)
            assessed_ids = ft_ids - not_retrieved
            reports_assessed = len(assessed_ids)

            for rid in assessed_ids:
                event = ledger.final_event(rid, ScreeningStage.FULL_TEXT)
                if not event:
                    continue
                if event.decision is ScreeningDecision.INCLUDE:
                    included_ids.add(rid)
                elif event.decision is ScreeningDecision.EXCLUDE:
                    reason = event.reason_code or (event.reason_text or "OTHER").strip() or "OTHER"
                    exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1
            reports_included = len(included_ids)

            unresolved = ledger.conflicts()
            if unresolved:
                flow_warnings.append(f"{len(unresolved)} unresolved screening conflict(s) remain in the screening ledger.")
        elif not_retrieved_record_ids:
            flow_warnings.append("not_retrieved_record_ids were supplied without a ScreeningLedger and were not used for stage accounting.")

        studies_included: int | None = None
        if reports_included:
            if linkage is not None and workflow_records:
                index_by_id = {stable_record_id(record): idx for idx, record in enumerate(workflow_records)}
                included_indices = {index_by_id[rid] for rid in included_ids if rid in index_by_id}
                missing_ids = included_ids - set(index_by_id)
                family_ids = {
                    family.study_id
                    for family in linkage.families
                    if included_indices.intersection(family.member_indices)
                }
                studies_included = len(family_ids)
                if missing_ids:
                    flow_warnings.append(
                        f"{len(missing_ids)} included report(s) could not be mapped to the records used for study linkage."
                    )
            else:
                flow_warnings.append(
                    "Included reports are present but study-level linkage was not supplied; studies_included is therefore unknown."
                )

        flow = PrismaFlow(
            databases=databases,
            registers=dict(registers or {}),
            other_sources=dict(other_sources or {}),
            duplicates_removed=duplicates_removed,
            automation_removed_before_screening=automation_removed_before_screening,
            other_removed_before_screening=other_removed_before_screening,
            records_screened=records_screened,
            records_excluded=records_excluded,
            reports_sought_for_retrieval=reports_sought,
            reports_not_retrieved=reports_not_retrieved,
            reports_assessed_for_eligibility=reports_assessed,
            reports_excluded=exclusion_reasons,
            studies_included=studies_included,
            reports_included=reports_included,
            warnings=flow_warnings,
        )
        arithmetic = flow.validate(strict=strict)
        for warning in arithmetic:
            if warning not in flow.warnings:
                flow.warnings.append(warning)
        return flow

    @staticmethod
    def build_search_report(
        search: MultiSearchResult,
        *,
        deduplication: DeduplicationResult | None = None,
        context: PrismaSearchContext | None = None,
    ) -> PrismaSearchReport:
        from . import __version__

        context = context or PrismaSearchContext()
        sources: list[PrismaSearchSource] = []
        for source_name, result in search.source_results.items():
            database_name, platform_name = _PLATFORM_MAP.get(
                source_name, (source_name.replace("_", " ").title(), source_name)
            )
            limits: dict[str, Any] = {}
            if search.query.year_from is not None:
                limits["year_from"] = search.query.year_from
            if search.query.year_to is not None:
                limits["year_to"] = search.query.year_to
            sources.append(
                PrismaSearchSource(
                    source=source_name,
                    database_name=database_name,
                    platform=platform_name,
                    translated_query=result.translation.translated,
                    canonical_query=search.query.canonical,
                    retrieved_count=result.retrieved_count,
                    total_available=result.total_available,
                    search_started_at_utc=result.started_at_utc,
                    search_finished_at_utc=result.finished_at_utc,
                    fidelity_score=result.translation.fidelity_score,
                    loss_score=result.translation.loss_score,
                    requires_review=result.translation.requires_review,
                    truncated=result.truncated,
                    warnings=list(result.warnings),
                    limits=limits,
                )
            )

        dedup_description = None
        if deduplication and deduplication.stats:
            stats = deduplication.stats
            dedup_description = (
                f"MetaEvidence {__version__} confidence-aware publication deduplication was applied to "
                f"{stats.input_records} records. {stats.input_records - stats.output_records} record(s) were removed "
                f"through automatic duplicate clustering; {stats.review_pairs} candidate pair(s) were retained for human review. "
                "Exact identifiers, bibliographic similarity, explicit conflict safeguards, and provenance-preserving merges were used."
            )

        def present(value: Any) -> bool:
            if isinstance(value, (list, tuple, dict, set)):
                return bool(value)
            return bool(value and str(value).strip())

        limits_auto = any(src.limits for src in sources)
        matrix = [
            PrismaSSupportItem(1, "Database name", "AUTOMATIC" if sources else "MISSING", "Database and API/platform are recorded for each live adapter."),
            PrismaSSupportItem(2, "Multi-database searching", "NOT_APPLICABLE", "MetaEvidence executes source-specific API adapters independently rather than a simultaneous multi-file platform search."),
            PrismaSSupportItem(3, "Study registries", "USER_SUPPLIED" if present(context.study_registries) else "USER_INPUT_REQUIRED", ", ".join(context.study_registries) if context.study_registries else "No registry-search information supplied."),
            PrismaSSupportItem(4, "Online resources and browsing", "USER_SUPPLIED" if present(context.online_resources) else "USER_INPUT_REQUIRED", ", ".join(context.online_resources) if context.online_resources else "No additional online/browsing sources supplied."),
            PrismaSSupportItem(5, "Citation searching", "USER_SUPPLIED" if present(context.citation_searching) else "USER_INPUT_REQUIRED", context.citation_searching or "No citation-searching method supplied."),
            PrismaSSupportItem(6, "Contacts", "USER_SUPPLIED" if present(context.contacts) else "USER_INPUT_REQUIRED", context.contacts or "No contact-based searching information supplied."),
            PrismaSSupportItem(7, "Other methods", "USER_SUPPLIED" if present(context.other_methods) else "USER_INPUT_REQUIRED", context.other_methods or "No other search methods supplied."),
            PrismaSSupportItem(8, "Full search strategies", "AUTOMATIC" if sources else "MISSING", "Canonical and executed source-specific strategies are preserved exactly as sent by the adapters."),
            PrismaSSupportItem(
                9, "Limits and restrictions",
                ("AUTOMATIC+USER" if limits_auto and present(context.limits_and_restrictions or context.limits_justification)
                 else "PARTIAL" if limits_auto
                 else "USER_SUPPLIED" if present(context.limits_and_restrictions or context.limits_justification)
                 else "USER_INPUT_REQUIRED"),
                (("Automatic date limits: " + ", ".join(f"{k}={v}" for src in sources for k, v in src.limits.items())) if limits_auto else "No automatic date limits recorded.")
                + (f" User documentation: {context.limits_and_restrictions or context.limits_justification}" if present(context.limits_and_restrictions or context.limits_justification) else " Other limits/restrictions and justification require user documentation."),
            ),
            PrismaSSupportItem(10, "Search filters", "USER_SUPPLIED" if present(context.search_filters) else "USER_INPUT_REQUIRED", context.search_filters or "No published-filter information supplied."),
            PrismaSSupportItem(11, "Prior work", "USER_SUPPLIED" if present(context.prior_work) else "USER_INPUT_REQUIRED", context.prior_work or "No reused/adapted prior search information supplied."),
            PrismaSSupportItem(12, "Updates", "USER_SUPPLIED" if present(context.updates) else "USER_INPUT_REQUIRED", context.updates or "No search-update method supplied."),
            PrismaSSupportItem(13, "Dates of searches", "AUTOMATIC" if sources and all(x.search_finished_at_utc for x in sources) else "PARTIAL", "Adapter execution timestamps are retained for each source."),
            PrismaSSupportItem(14, "Peer review", "USER_SUPPLIED" if present(context.peer_review) else "USER_INPUT_REQUIRED", context.peer_review or "No search-strategy peer-review process supplied."),
            PrismaSSupportItem(15, "Total records", "AUTOMATIC" if sources else "MISSING", "Retrieved counts are recorded separately for each source."),
            PrismaSSupportItem(16, "Deduplication", "AUTOMATIC" if dedup_description else "MISSING", dedup_description or "No deduplication result supplied."),
        ]
        return PrismaSearchReport(
            canonical_query=search.query.canonical,
            package_version=__version__,
            sources=sources,
            support_matrix=matrix,
            deduplication_description=dedup_description,
            context=context,
        )


def write_prisma_bundle(
    directory: str | Path,
    *,
    flow: PrismaFlow,
    search_report: PrismaSearchReport | None = None,
    search: MultiSearchResult | None = None,
) -> dict[str, Path]:
    """Write a reproducibility-oriented PRISMA/PRISMA-S reporting bundle."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {
        "prisma_flow_json": flow.write_json(out / "prisma_flow.json"),
        "prisma_flow_csv": flow.write_csv(out / "prisma_flow.csv"),
        "prisma_flow_mermaid": flow.write_mermaid(out / "prisma_flow.mmd"),
    }
    if search_report is not None:
        paths.update({
            "search_report_json": search_report.write_json(out / "prisma_search_report.json"),
            "search_report_markdown": search_report.write_markdown(out / "prisma_search_report.md"),
            "search_sources_csv": search_report.write_sources_csv(out / "prisma_sources.csv"),
            "search_strategies_csv": search_report.write_strategies_csv(out / "prisma_search_strategies.csv"),
            "prisma_s_matrix_csv": search_report.write_support_matrix_csv(out / "prisma_s_support_matrix.csv"),
        })
    if search is not None:
        manifest_path = out / "search_manifest.json"
        search.manifest.write_json(manifest_path)
        paths["search_manifest"] = manifest_path

    manifest = {
        "format_version": "MetaEvidence-prisma-bundle-1",
        "generated_at_utc": _utcnow(),
        "disclaimer": "Reporting-support artifact; does not by itself establish PRISMA compliance.",
        "runtime": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "files": {},
    }
    for key, path in sorted(paths.items()):
        payload = path.read_bytes()
        manifest["files"][key] = {
            "name": path.name,
            "sha256": sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    manifest_path = out / "reproducibility_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    paths["reproducibility_manifest"] = manifest_path
    return paths
