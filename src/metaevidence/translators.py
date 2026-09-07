from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable

from .query import (
    Boolean,
    ControlledVocabulary,
    Field,
    Not,
    Phrase,
    Proximity,
    QueryNode,
    SearchField,
    SearchQuery,
    Term,
    literal_text,
    render,
)


class TranslationStatus(str, Enum):
    EXACT = "exact"
    APPROXIMATED = "approximated"
    EXPANDED = "expanded"
    UNSUPPORTED = "unsupported"
    REVIEW_REQUIRED = "review_required"


_STATUS_SCORE = {
    TranslationStatus.EXACT: 1.0,
    TranslationStatus.EXPANDED: 0.90,
    TranslationStatus.APPROXIMATED: 0.70,
    TranslationStatus.REVIEW_REQUIRED: 0.40,
    TranslationStatus.UNSUPPORTED: 0.0,
}


@dataclass(frozen=True, slots=True)
class TranslationDiagnostic:
    source: str
    canonical: str
    translated: str
    feature: str
    status: TranslationStatus
    note: str = ""


@dataclass(frozen=True, slots=True)
class Translation:
    source: str
    original: str
    translated: str
    notes: tuple[str, ...] = ()
    diagnostics: tuple[TranslationDiagnostic, ...] = ()
    params: tuple[tuple[str, str], ...] = ()

    @property
    def fidelity_score(self) -> float:
        if not self.diagnostics:
            return 1.0
        # Score only feature-bearing leaf/special diagnostics, avoiding double-counting
        # container Boolean nodes when leaf diagnostics are available.
        meaningful = [d for d in self.diagnostics if d.feature != "boolean"] or list(self.diagnostics)
        return round(sum(_STATUS_SCORE[d.status] for d in meaningful) / len(meaningful), 4)

    @property
    def loss_score(self) -> float:
        return round(1.0 - self.fidelity_score, 4)

    @property
    def requires_review(self) -> bool:
        return any(
            d.status in {TranslationStatus.REVIEW_REQUIRED, TranslationStatus.UNSUPPORTED}
            for d in self.diagnostics
        )

    def diagnostics_by_status(self, status: TranslationStatus) -> tuple[TranslationDiagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.status == status)


@dataclass
class _Compiled:
    text: str
    diagnostics: list[TranslationDiagnostic]


_FIELD_MAPS: dict[str, dict[SearchField, str | None]] = {
    "pubmed": {
        SearchField.ALL: "All Fields",
        SearchField.TITLE: "Title",
        SearchField.ABSTRACT: "Abstract",
        SearchField.TITLE_ABSTRACT: "Title/Abstract",
        SearchField.KEYWORDS: "Other Term",
        SearchField.AUTHOR: "Author",
        SearchField.JOURNAL: "Journal",
        SearchField.AFFILIATION: "Affiliation",
    },
    "scopus": {
        SearchField.ALL: "ALL",
        SearchField.TITLE: "TITLE",
        SearchField.ABSTRACT: "ABS",
        SearchField.TITLE_ABSTRACT: "TITLE-ABS",
        SearchField.KEYWORDS: "KEY",
        SearchField.AUTHOR: "AUTH",
        SearchField.JOURNAL: "SRCTITLE",
        SearchField.AFFILIATION: "AFFIL",
    },
    "web_of_science": {
        SearchField.ALL: "ALL",
        SearchField.TITLE: "TI",
        SearchField.ABSTRACT: "AB",
        SearchField.TITLE_ABSTRACT: "TS",  # Topic is broader than title+abstract.
        SearchField.KEYWORDS: "AK",
        SearchField.AUTHOR: "AU",
        SearchField.JOURNAL: "SO",
        SearchField.AFFILIATION: "AD",
    },
    "web_of_science_starter": {
        SearchField.ALL: "TS",
        SearchField.TITLE: "TI",
        SearchField.ABSTRACT: "TS",
        SearchField.TITLE_ABSTRACT: "TS",
        SearchField.KEYWORDS: "TS",
        SearchField.AUTHOR: "AU",
        SearchField.JOURNAL: "SO",
        SearchField.AFFILIATION: "OG",
    },
    "core": {
        SearchField.ALL: None,
        SearchField.TITLE: "title",
        SearchField.ABSTRACT: "abstract",
        SearchField.TITLE_ABSTRACT: None,
        SearchField.KEYWORDS: None,
        SearchField.AUTHOR: "authors",
        SearchField.JOURNAL: None,
        SearchField.AFFILIATION: None,
    },
    "europe_pmc": {
        SearchField.ALL: None,
        SearchField.TITLE: "TITLE",
        SearchField.ABSTRACT: "ABSTRACT",
        SearchField.TITLE_ABSTRACT: None,
        SearchField.KEYWORDS: "KW",
        SearchField.AUTHOR: "AUTH",
        SearchField.JOURNAL: "JOURNAL",
        SearchField.AFFILIATION: "AFF",
    },
}


def _diag(source: str, node: QueryNode, translated: str, feature: str, status: TranslationStatus, note: str = "") -> TranslationDiagnostic:
    return TranslationDiagnostic(source, render(node), translated, feature, status, note)


def _quote(value: str) -> str:
    return '"' + value.replace('"', r'\"') + '"'


def _compile_passthrough(node: QueryNode, source: str) -> _Compiled:
    """Compile Boolean/phrase grammar for engines with close Boolean semantics."""
    if isinstance(node, Term):
        status = TranslationStatus.EXACT
        note = ""
        if node.has_wildcard and source == "pubmed":
            status = TranslationStatus.REVIEW_REQUIRED
            note = "PubMed truncation behavior should be reviewed for systematic-review sensitivity."
        return _Compiled(node.value, [_diag(source, node, node.value, "wildcard" if node.has_wildcard else "term", status, note)])
    if isinstance(node, Phrase):
        text = _quote(node.value)
        return _Compiled(text, [_diag(source, node, text, "phrase", TranslationStatus.EXACT)])
    if isinstance(node, ControlledVocabulary):
        if node.vocabulary.lower() == "mesh" and source == "pubmed":
            text = f"{_quote(node.term)}[MeSH Terms]"
            return _Compiled(text, [_diag(source, node, text, "controlled_vocabulary", TranslationStatus.EXACT, "Mapped to PubMed MeSH Terms field.")])
        if node.vocabulary.lower() == "mesh" and source == "europe_pmc":
            text = f'MESH:{_quote(node.term)}'
            return _Compiled(text, [_diag(source, node, text, "controlled_vocabulary", TranslationStatus.EXPANDED, "Europe PMC supports MeSH-based search but indexing coverage differs from PubMed.")])
        text = _quote(node.term)
        return _Compiled(text, [_diag(source, node, text, "controlled_vocabulary", TranslationStatus.APPROXIMATED, f"{node.vocabulary} concept degraded to free text for this source.")])
    if isinstance(node, Field):
        inner = _compile_passthrough(node.child, source)
        fmap = _FIELD_MAPS.get(source, {})
        mapped = fmap.get(node.field)
        if source == "pubmed" and mapped:
            text = f"{inner.text}[{mapped}]"
            status = TranslationStatus.EXACT
            note = ""
        elif source == "scopus" and mapped:
            text = f"{mapped}({inner.text})"
            status = TranslationStatus.EXACT
            note = ""
        elif source == "web_of_science" and mapped:
            text = f"{mapped}=({inner.text})"
            status = TranslationStatus.APPROXIMATED if node.field == SearchField.TITLE_ABSTRACT else TranslationStatus.EXACT
            note = "Web of Science Topic (TS) is broader than title+abstract." if node.field == SearchField.TITLE_ABSTRACT else ""
        elif source == "web_of_science_starter" and mapped:
            text = f"{mapped}=({inner.text})"
            exact_fields = {SearchField.TITLE, SearchField.AUTHOR, SearchField.JOURNAL}
            status = TranslationStatus.EXACT if node.field in exact_fields else TranslationStatus.APPROXIMATED
            if node.field in {SearchField.ABSTRACT, SearchField.TITLE_ABSTRACT, SearchField.KEYWORDS, SearchField.ALL}:
                note = "Web of Science Starter maps this canonical scope to Topic (TS), which is broader than the requested field scope."
            elif node.field == SearchField.AFFILIATION:
                note = "Web of Science Starter maps affiliation intent to organization name (OG); address-level affiliation semantics are not preserved."
            else:
                note = ""
        elif source == "core" and mapped:
            text = f"{mapped}:({inner.text})"
            status = TranslationStatus.EXACT
            note = ""
        elif source == "core" and node.field == SearchField.TITLE_ABSTRACT:
            text = f"(title:({inner.text}) OR abstract:({inner.text}))"
            status = TranslationStatus.EXPANDED
            note = "Canonical title+abstract scope expanded to two CORE fields."
        elif source == "europe_pmc" and mapped:
            text = f"{mapped}:({inner.text})"
            status = TranslationStatus.EXACT
            note = ""
        elif source == "europe_pmc" and node.field == SearchField.TITLE_ABSTRACT:
            text = f"(TITLE:({inner.text}) OR ABSTRACT:({inner.text}))"
            status = TranslationStatus.EXPANDED
            note = "Canonical title+abstract scope expanded to two Europe PMC fields."
        else:
            text = inner.text
            status = TranslationStatus.APPROXIMATED
            note = f"Field {node.field.value} is not represented exactly and was degraded to source default search scope."
        return _Compiled(text, inner.diagnostics + [_diag(source, node, text, "field", status, note)])
    if isinstance(node, Not):
        inner = _compile_passthrough(node.child, source)
        text = f"NOT ({inner.text})"
        return _Compiled(text, inner.diagnostics + [_diag(source, node, text, "not", TranslationStatus.EXACT)])
    if isinstance(node, Boolean):
        parts = [_compile_passthrough(child, source) for child in node.children]
        text = f" {node.operator} ".join(f"({part.text})" for part in parts)
        diagnostics = [d for part in parts for d in part.diagnostics]
        diagnostics.append(_diag(source, node, text, "boolean", TranslationStatus.EXACT))
        return _Compiled(text, diagnostics)
    if isinstance(node, Proximity):
        return _compile_proximity(node, source)
    raise TypeError(type(node))


def _compile_proximity(node: Proximity, source: str) -> _Compiled:
    if source == "openalex":
        left = _compile_openalex(node.left)
        right = _compile_openalex(node.right)
    else:
        left = _compile_passthrough(node.left, source)
        right = _compile_passthrough(node.right, source)
    ltxt = literal_text(node.left)
    rtxt = literal_text(node.right)
    status = TranslationStatus.EXACT
    note = ""

    if source == "scopus":
        text = f"({left.text} W/{node.distance} {right.text})"
    elif source in {"web_of_science", "web_of_science_starter"}:
        text = f"({left.text} NEAR/{node.distance} {right.text})"
    elif source == "openalex":
        if ltxt is not None and rtxt is not None:
            text = f'{_quote(ltxt)}~{node.distance}~{_quote(rtxt)}'
        else:
            text = f"({left.text}) AND ({right.text})"
            status = TranslationStatus.REVIEW_REQUIRED
            note = "Complex proximity operands cannot be represented safely in the classic OpenAlex search string; degraded to AND."
    elif source == "pubmed":
        # PubMed's proximity syntax scopes a quoted set of search terms to a supported field.
        # Without an explicit field in the canonical node, title/abstract is used and flagged.
        if ltxt is not None and rtxt is not None:
            joined = f"{ltxt} {rtxt}"
            text = f'{_quote(joined)}[Title/Abstract:~{node.distance}]'
            status = TranslationStatus.APPROXIMATED
            note = "Canonical unscoped proximity mapped to PubMed Title/Abstract proximity; review field intent."
        else:
            text = f"({left.text}) AND ({right.text})"
            status = TranslationStatus.REVIEW_REQUIRED
            note = "Complex PubMed proximity degraded to AND."
    else:
        text = f"({left.text}) AND ({right.text})"
        status = TranslationStatus.UNSUPPORTED if source == "crossref" else TranslationStatus.REVIEW_REQUIRED
        note = "Source-specific proximity is not safely represented by this compiler; degraded to AND."

    diagnostics = left.diagnostics + right.diagnostics
    diagnostics.append(_diag(source, node, text, "proximity", status, note))
    return _Compiled(text, diagnostics)


def _flatten_for_crossref(node: QueryNode) -> tuple[str, list[TranslationDiagnostic]]:
    source = "crossref"
    diagnostics: list[TranslationDiagnostic] = []

    if isinstance(node, Term):
        text = node.value.replace("*", "").replace("?", "")
        status = TranslationStatus.APPROXIMATED if node.has_wildcard else TranslationStatus.EXACT
        note = "Crossref bibliographic query does not preserve wildcard semantics." if node.has_wildcard else ""
        diagnostics.append(_diag(source, node, text, "wildcard" if node.has_wildcard else "term", status, note))
        return text, diagnostics
    if isinstance(node, Phrase):
        text = node.value
        diagnostics.append(_diag(source, node, text, "phrase", TranslationStatus.APPROXIMATED, "Crossref query.bibliographic is relevance-oriented rather than an exact Boolean phrase engine."))
        return text, diagnostics
    if isinstance(node, ControlledVocabulary):
        text = node.term
        diagnostics.append(_diag(source, node, text, "controlled_vocabulary", TranslationStatus.APPROXIMATED, "Controlled vocabulary degraded to free bibliographic text."))
        return text, diagnostics
    if isinstance(node, Field):
        text, child_diag = _flatten_for_crossref(node.child)
        diagnostics.extend(child_diag)
        diagnostics.append(_diag(source, node, text, "field", TranslationStatus.APPROXIMATED, "Crossref field restriction is degraded to query.bibliographic."))
        return text, diagnostics
    if isinstance(node, Not):
        text, child_diag = _flatten_for_crossref(node.child)
        diagnostics.extend(child_diag)
        diagnostics.append(_diag(source, node, text, "not", TranslationStatus.UNSUPPORTED, "Crossref query.bibliographic cannot guarantee canonical NOT semantics."))
        return text, diagnostics
    if isinstance(node, Proximity):
        left, dl = _flatten_for_crossref(node.left)
        right, dr = _flatten_for_crossref(node.right)
        text = f"{left} {right}"
        diagnostics.extend(dl + dr)
        diagnostics.append(_diag(source, node, text, "proximity", TranslationStatus.UNSUPPORTED, "Crossref query.bibliographic cannot guarantee canonical proximity semantics."))
        return text, diagnostics
    if isinstance(node, Boolean):
        parts: list[str] = []
        for child in node.children:
            text, child_diag = _flatten_for_crossref(child)
            parts.append(text)
            diagnostics.extend(child_diag)
        combined = " ".join(parts)
        status = TranslationStatus.APPROXIMATED if node.operator == "AND" else TranslationStatus.UNSUPPORTED
        note = "Crossref relevance query approximates conjunction." if node.operator == "AND" else "Crossref query.bibliographic does not preserve canonical OR grouping."
        diagnostics.append(_diag(source, node, combined, "boolean", status, note))
        return combined, diagnostics
    raise TypeError(type(node))


def _compile_openalex(node: QueryNode) -> _Compiled:
    source = "openalex"
    if isinstance(node, Field):
        inner = _compile_openalex(node.child)
        # OpenAlex classic URL search has useful searchable filters, but preserving arbitrary
        # nested fielded Boolean logic may require OQL. v0.2 degrades field restrictions while
        # retaining an explicit audit warning; M3 will add an OQL adapter.
        status = TranslationStatus.APPROXIMATED
        note = "Field restriction is degraded in classic OpenAlex search mode; OQL compilation is planned for the live adapter."
        return _Compiled(inner.text, inner.diagnostics + [_diag(source, node, inner.text, "field", status, note)])
    if isinstance(node, ControlledVocabulary):
        text = _quote(node.term)
        return _Compiled(text, [_diag(source, node, text, "controlled_vocabulary", TranslationStatus.APPROXIMATED, "MeSH is degraded to free text in classic OpenAlex search mode.")])
    if isinstance(node, Proximity):
        return _compile_proximity(node, source)
    if isinstance(node, Term):
        text = node.value
        status = TranslationStatus.EXACT
        note = ""
        if node.has_wildcard:
            status = TranslationStatus.REVIEW_REQUIRED
            note = "OpenAlex wildcard search requires exact/unstemmed search mode; adapter must select search.exact."
        return _Compiled(text, [_diag(source, node, text, "wildcard" if node.has_wildcard else "term", status, note)])
    if isinstance(node, Phrase):
        text = _quote(node.value)
        return _Compiled(text, [_diag(source, node, text, "phrase", TranslationStatus.EXACT)])
    if isinstance(node, Not):
        inner = _compile_openalex(node.child)
        text = f"NOT ({inner.text})"
        return _Compiled(text, inner.diagnostics + [_diag(source, node, text, "not", TranslationStatus.EXACT)])
    if isinstance(node, Boolean):
        parts = [_compile_openalex(child) for child in node.children]
        text = f" {node.operator} ".join(f"({p.text})" for p in parts)
        diagnostics = [d for p in parts for d in p.diagnostics]
        diagnostics.append(_diag(source, node, text, "boolean", TranslationStatus.EXACT))
        return _Compiled(text, diagnostics)
    raise TypeError(type(node))



_OQL_FIELD_MAP: dict[SearchField, tuple[str, TranslationStatus, str]] = {
    SearchField.TITLE: ("title", TranslationStatus.EXACT, ""),
    SearchField.ABSTRACT: ("abstract", TranslationStatus.EXACT, ""),
    SearchField.TITLE_ABSTRACT: ("title/abstract", TranslationStatus.EXACT, ""),
    SearchField.AUTHOR: ("byline", TranslationStatus.APPROXIMATED, "Canonical author search is mapped to OpenAlex byline text search."),
    SearchField.AFFILIATION: ("raw affiliation", TranslationStatus.EXACT, ""),
    SearchField.KEYWORDS: ("title/abstract", TranslationStatus.REVIEW_REQUIRED, "OpenAlex OQL does not expose a direct author-keyword text search field; degraded to title/abstract."),
    SearchField.JOURNAL: ("title/abstract", TranslationStatus.UNSUPPORTED, "Free-text journal/source names require source entity resolution for exact OQL filtering; degraded to title/abstract and must be reviewed."),
    SearchField.ALL: ("title/abstract", TranslationStatus.APPROXIMATED, "Canonical all-fields intent is narrowed to OpenAlex title/abstract text search."),
}


def _oql_escape(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', r'\"')


def _oql_value(node: QueryNode, source: str = "openalex_oql") -> _Compiled:
    """Compile a canonical subtree into one OpenAlex OQL ``has (...)`` value.

    This preserves nested Boolean logic when all clauses share one text field. Explicit
    field nodes are handled by :func:`_compile_openalex_oql` instead.
    """
    if isinstance(node, Term):
        if node.has_wildcard:
            text = _quote(node.value)
            status = TranslationStatus.EXACT
            note = "OpenAlex OQL wildcards are emitted in quoted/no-stem form."
        else:
            text = node.value
            status = TranslationStatus.EXACT
            note = ""
        return _Compiled(text, [_diag(source, node, text, "wildcard" if node.has_wildcard else "term", status, note)])
    if isinstance(node, Phrase):
        text = _quote(node.value)
        return _Compiled(text, [_diag(source, node, text, "phrase", TranslationStatus.EXACT)])
    if isinstance(node, ControlledVocabulary):
        text = _quote(node.term)
        return _Compiled(text, [_diag(source, node, text, "controlled_vocabulary", TranslationStatus.APPROXIMATED, f"{node.vocabulary} concept is searched as exact title/abstract text because OpenAlex OQL does not provide that controlled vocabulary directly.")])
    if isinstance(node, Not):
        inner = _oql_value(node.child, source)
        text = f"not ({inner.text})" if isinstance(node.child, Boolean) else f"not {inner.text}"
        return _Compiled(text, inner.diagnostics + [_diag(source, node, text, "not", TranslationStatus.EXACT)])
    if isinstance(node, Boolean):
        parts = [_oql_value(child, source) for child in node.children]
        op = node.operator.lower()
        text = f" {op} ".join(f"({part.text})" for part in parts)
        diagnostics = [d for part in parts for d in part.diagnostics]
        diagnostics.append(_diag(source, node, text, "boolean", TranslationStatus.EXACT))
        return _Compiled(text, diagnostics)
    if isinstance(node, Proximity):
        left_text = literal_text(node.left)
        right_text = literal_text(node.right)
        if left_text is None or right_text is None:
            left = _oql_value(node.left, source)
            right = _oql_value(node.right, source)
            text = f"({left.text}) and ({right.text})"
            diagnostics = left.diagnostics + right.diagnostics
            diagnostics.append(_diag(source, node, text, "proximity", TranslationStatus.REVIEW_REQUIRED, "Complex proximity operands cannot be expressed as one OpenAlex OQL within-list; degraded to AND."))
            return _Compiled(text, diagnostics)
        left_exact = isinstance(node.left, Phrase) or (isinstance(node.left, Term) and node.left.has_wildcard)
        right_exact = isinstance(node.right, Phrase) or (isinstance(node.right, Term) and node.right.has_wildcard)
        status = TranslationStatus.EXACT
        note = ""
        if left_exact != right_exact:
            status = TranslationStatus.APPROXIMATED
            note = "Mixed stemmed/exact proximity operands were normalized to exact quoted OQL operands."
        quote_operands = left_exact or right_exact
        if quote_operands:
            a, b = _quote(left_text), _quote(right_text)
        else:
            a, b = left_text, right_text
        text = f"within {node.distance} ({a}, {b})"
        return _Compiled(text, [_diag(source, node, text, "proximity", status, note)])
    if isinstance(node, Field):
        # A nested field inside a single-value context cannot safely be represented here;
        # the outer compiler handles field-aware Boolean branching.
        inner = _oql_value(node.child, source)
        return _Compiled(inner.text, inner.diagnostics + [_diag(source, node, inner.text, "field", TranslationStatus.REVIEW_REQUIRED, "Nested explicit field requires field-aware OQL compilation.")])
    raise TypeError(type(node))


def _contains_explicit_field(node: QueryNode) -> bool:
    if isinstance(node, Field):
        return True
    if isinstance(node, Boolean):
        return any(_contains_explicit_field(c) for c in node.children)
    if isinstance(node, Not):
        return _contains_explicit_field(node.child)
    if isinstance(node, Proximity):
        return _contains_explicit_field(node.left) or _contains_explicit_field(node.right)
    return False


def _compile_openalex_oql(node: QueryNode, *, default_field: str = "title/abstract") -> _Compiled:
    source = "openalex_oql"
    if isinstance(node, Field):
        mapped, field_status, field_note = _OQL_FIELD_MAP[node.field]
        inner = _oql_value(node.child, source)
        text = f"{mapped} has ({inner.text})"
        return _Compiled(text, inner.diagnostics + [_diag(source, node, text, "field", field_status, field_note)])
    if isinstance(node, Boolean) and _contains_explicit_field(node):
        parts = [_compile_openalex_oql(child, default_field=default_field) for child in node.children]
        op = node.operator.lower()
        text = f" {op} ".join(f"({part.text})" for part in parts)
        diagnostics = [d for part in parts for d in part.diagnostics]
        diagnostics.append(_diag(source, node, text, "boolean", TranslationStatus.EXACT))
        return _Compiled(text, diagnostics)
    if isinstance(node, Not) and _contains_explicit_field(node.child):
        # OQL negation is expressed inside a condition's value. Negating a heterogeneous
        # field group cannot be represented as a generic top-level NOT filter without
        # rewriting by De Morgan; retain a conservative review-required approximation.
        child = _compile_openalex_oql(node.child, default_field=default_field)
        text = child.text
        return _Compiled(text, child.diagnostics + [_diag(source, node, text, "not", TranslationStatus.REVIEW_REQUIRED, "NOT over heterogeneous field filters requires manual review; the positive child query is emitted rather than inventing unsafe semantics.")])
    if isinstance(node, Proximity) and _contains_explicit_field(node):
        # Different fields inside a single proximity window have no direct OQL analogue.
        left = _compile_openalex_oql(node.left, default_field=default_field)
        right = _compile_openalex_oql(node.right, default_field=default_field)
        text = f"({left.text}) and ({right.text})"
        return _Compiled(text, left.diagnostics + right.diagnostics + [_diag(source, node, text, "proximity", TranslationStatus.REVIEW_REQUIRED, "Cross-field proximity degraded to AND because OpenAlex OQL proximity is scoped within one search field.")])
    inner = _oql_value(node, source)
    text = f"{default_field} has ({inner.text})"
    return _Compiled(text, inner.diagnostics)


def _translate_openalex_oql(query: SearchQuery) -> Translation:
    source = "openalex_oql"
    fields = {f.lower() for f in query.fields}
    default_field = "title/abstract"
    compiled = _compile_openalex_oql(query.ast, default_field=default_field)
    filters = compiled.text
    diagnostics = list(compiled.diagnostics)
    notes: list[str] = [
        "OpenAlex OQL is executed at the API root and preserves nested Boolean text-search logic more faithfully than classic URL search.",
    ]
    if not _contains_explicit_field(query.ast):
        if fields == {"title", "abstract", "keywords"}:
            diagnostics.append(TranslationDiagnostic(
                source, "<default fields>", "title/abstract", "default_scope",
                TranslationStatus.APPROXIMATED,
                "Canonical default includes keywords, while OpenAlex OQL direct text search is scoped to title/abstract here; keyword-only matches may differ.",
            ))
        elif fields == {"all"}:
            diagnostics.append(TranslationDiagnostic(
                source, "<default fields>", "title/abstract", "default_scope",
                TranslationStatus.APPROXIMATED,
                "Canonical all-fields search is narrowed to title/abstract for deterministic OQL text retrieval.",
            ))
    date_parts: list[str] = []
    if query.year_from is not None:
        date_parts.append(f"year >= ({query.year_from})")
    if query.year_to is not None:
        date_parts.append(f"year <= ({query.year_to})")
    if date_parts:
        filters = f"({filters}) and " + " and ".join(date_parts)
        diagnostics.append(TranslationDiagnostic(
            source, "<year range>", " and ".join(date_parts), "date_filter",
            TranslationStatus.EXACT, "Mapped to OpenAlex OQL year comparisons.",
        ))
    text = f"works where {filters}"
    return Translation(source, query.canonical, text, tuple(notes), tuple(diagnostics), (("oql", text),))

def _default_scope(ast_text: str, source: str, fields: Iterable[str]) -> tuple[str, TranslationDiagnostic | None]:
    field_set = {f.lower() for f in fields}
    if source == "scopus" and field_set == {"title", "abstract", "keywords"}:
        text = f"TITLE-ABS-KEY({ast_text})"
        return text, TranslationDiagnostic(source, "<default fields>", text, "default_scope", TranslationStatus.EXACT, "Mapped to TITLE-ABS-KEY.")
    if source == "web_of_science" and field_set == {"title", "abstract", "keywords"}:
        text = f"TS=({ast_text})"
        return text, TranslationDiagnostic(source, "<default fields>", text, "default_scope", TranslationStatus.APPROXIMATED, "WoS Topic (TS) also includes additional indexed topic fields beyond the canonical default set.")
    if source == "web_of_science_starter" and field_set == {"title", "abstract", "keywords"}:
        text = f"TS=({ast_text})"
        return text, TranslationDiagnostic(source, "<default fields>", text, "default_scope", TranslationStatus.APPROXIMATED, "Web of Science Starter Topic (TS) is broader than an exact title+abstract+keywords scope.")
    return ast_text, None


def translate(query: SearchQuery, source: str) -> Translation:
    """Compile a canonical query and expose clause-level translation fidelity.

    This API intentionally returns diagnostics instead of silently pretending that all
    bibliographic search languages have equivalent semantics.
    """
    src = source.lower().replace(" ", "_")
    if src == "wos":
        src = "web_of_science"
    if src in {"wos_starter", "webofscience_starter"}:
        src = "web_of_science_starter"
    if src == "europepmc":
        src = "europe_pmc"
    if src in {"openalex_oql", "openalex-oql", "oql"}:
        src = "openalex_oql"
    if src in {"wos_expanded", "webofscience_expanded", "web_of_science_expanded"}:
        src = "web_of_science"

    supported = {"pubmed", "scopus", "web_of_science", "web_of_science_starter", "openalex", "openalex_oql", "crossref", "europe_pmc", "core"}
    if src not in supported:
        raise ValueError(f"Unsupported source translator: {source}")

    if src == "openalex_oql":
        return _translate_openalex_oql(query)

    if src == "crossref":
        text, diagnostics = _flatten_for_crossref(query.ast)
        params: list[tuple[str, str]] = [("query.bibliographic", text)]
        if query.year_from:
            params.append(("filter.from-pub-date", str(query.year_from)))
        if query.year_to:
            params.append(("filter.until-pub-date", str(query.year_to)))
        notes = ["Crossref uses query.bibliographic plus publication-date filters; Boolean equivalence is not assumed."]
        return Translation(src, query.canonical, text, tuple(notes), tuple(diagnostics), tuple(params))

    compiled = _compile_openalex(query.ast) if src == "openalex" else _compile_passthrough(query.ast, src)
    text = compiled.text
    diagnostics = list(compiled.diagnostics)
    params: list[tuple[str, str]] = []
    notes: list[str] = []

    # Apply default search scope only when the canonical expression itself contains no
    # explicit bibliographic Field node. Controlled-vocabulary nodes (e.g. mesh:) are
    # not field overrides for the surrounding free-text clauses.
    def _has_explicit_field(node: QueryNode) -> bool:
        if isinstance(node, Field):
            return True
        if isinstance(node, Boolean):
            return any(_has_explicit_field(c) for c in node.children)
        if isinstance(node, Not):
            return _has_explicit_field(node.child)
        if isinstance(node, Proximity):
            return _has_explicit_field(node.left) or _has_explicit_field(node.right)
        return False

    if not _has_explicit_field(query.ast):
        text, scope_diag = _default_scope(text, src, query.fields)
        if scope_diag:
            diagnostics.append(scope_diag)
        elif src in {"pubmed", "openalex", "europe_pmc", "core"} and set(f.lower() for f in query.fields) != {"all"}:
            diagnostics.append(TranslationDiagnostic(
                src,
                "<default fields>",
                text,
                "default_scope",
                TranslationStatus.APPROXIMATED,
                "Canonical default field set is not represented by one exact global scope in this compiler mode; source-default search scope is retained and audited.",
            ))

    if src == "pubmed":
        if query.year_from or query.year_to:
            lo = query.year_from or 1000
            hi = query.year_to or 3000
            text = f"({text}) AND ({lo}:{hi}[dp])"
            diagnostics.append(TranslationDiagnostic(src, "<year range>", f"{lo}:{hi}[dp]", "date_filter", TranslationStatus.EXACT, "Publication date mapped to PubMed [dp]."))
        notes.append("PubMed field tags and publication-date syntax are emitted directly.")
    elif src == "scopus":
        if query.year_from:
            text += f" AND PUBYEAR > {query.year_from - 1}"
        if query.year_to:
            text += f" AND PUBYEAR < {query.year_to + 1}"
        if query.year_from or query.year_to:
            diagnostics.append(TranslationDiagnostic(src, "<year range>", text, "date_filter", TranslationStatus.EXACT, "Mapped to PUBYEAR bounds."))
        notes.append("Canonical default title/abstract/keyword scope maps to TITLE-ABS-KEY.")
    elif src == "web_of_science":
        if query.year_from or query.year_to:
            lo = query.year_from or 1900
            hi = query.year_to or 2100
            text += f" AND PY=({lo}-{hi})"
            diagnostics.append(TranslationDiagnostic(src, "<year range>", f"PY=({lo}-{hi})", "date_filter", TranslationStatus.EXACT, "Mapped to publication year.") )
        notes.append("Topic (TS) is used for the canonical default field set and is flagged as broader than an exact title+abstract+keywords mapping.")
    elif src == "web_of_science_starter":
        if query.year_from and query.year_to:
            params.append(("publishTimeSpan", f"{query.year_from}-01-01 {query.year_to}-12-31"))
            diagnostics.append(TranslationDiagnostic(src, "<year range>", "Starter publishTimeSpan", "date_filter", TranslationStatus.EXACT, "Fully bounded publication dates are carried as a Starter API filter."))
        elif query.year_from or query.year_to:
            diagnostics.append(TranslationDiagnostic(src, "<year range>", "local post-filter", "date_filter", TranslationStatus.REVIEW_REQUIRED, "One-sided year bounds are applied locally by the live Starter adapter in v0.9.1."))
        notes.append("This compiler targets Web of Science Starter-safe field tags. Topic (TS) approximations are explicitly audited; API Expanded remains a distinct endpoint/product.")
    elif src == "core":
        if query.year_from or query.year_to:
            diagnostics.append(TranslationDiagnostic(src, "<year range>", "local post-filter", "date_filter", TranslationStatus.REVIEW_REQUIRED, "Publication-year bounds are applied locally by the CORE live adapter in v0.9.1 to avoid assuming undocumented range syntax equivalence."))
        notes.append("CORE fielded Boolean syntax is emitted where mapped; publication-year bounds are currently post-filtered by the live adapter and audited.")
    elif src == "openalex":
        params.append(("search", text))
        if query.year_from:
            params.append(("filter.from_publication_date", f"{query.year_from}-01-01"))
        if query.year_to:
            params.append(("filter.to_publication_date", f"{query.year_to}-12-31"))
        if query.year_from or query.year_to:
            diagnostics.append(TranslationDiagnostic(src, "<year range>", "API publication-date filters", "date_filter", TranslationStatus.EXACT, "Date constraints are carried separately from search text."))
        notes.append("OpenAlex classic search supports Boolean/phrase/proximity; field-rich OQL compilation is reserved for the live adapter milestone.")
    elif src == "europe_pmc":
        if query.year_from or query.year_to:
            lo = query.year_from or 1000
            hi = query.year_to or 3000
            text = f"({text}) AND PUB_YEAR:[{lo} TO {hi}]"
            diagnostics.append(TranslationDiagnostic(src, "<year range>", f"PUB_YEAR:[{lo} TO {hi}]", "date_filter", TranslationStatus.EXACT, "Mapped to Europe PMC publication-year range."))
        notes.append("Europe PMC field syntax is emitted where a canonical field has a direct mapping.")

    return Translation(src, query.canonical, text, tuple(notes), tuple(diagnostics), tuple(params))
