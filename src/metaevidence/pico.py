from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .query import Boolean, ControlledVocabulary, Phrase, QueryNode, SearchQuery, Term


@dataclass(frozen=True, slots=True)
class ConceptBlock:
    """Synonymous free-text and controlled-vocabulary terms for one review concept."""

    free_terms: tuple[str, ...] = ()
    mesh_terms: tuple[str, ...] = ()

    def to_ast(self) -> QueryNode | None:
        nodes: list[QueryNode] = []
        for item in self.free_terms:
            item = item.strip()
            if not item:
                continue
            nodes.append(Phrase(item) if " " in item else Term(item))
        for item in self.mesh_terms:
            item = item.strip()
            if item:
                nodes.append(ControlledVocabulary("MeSH", item))
        if not nodes:
            return None
        return nodes[0] if len(nodes) == 1 else Boolean("OR", tuple(nodes))


def _block(value: ConceptBlock | Iterable[str] | str | None) -> ConceptBlock:
    if value is None:
        return ConceptBlock()
    if isinstance(value, ConceptBlock):
        return value
    if isinstance(value, str):
        return ConceptBlock((value,))
    return ConceptBlock(tuple(value))


@dataclass(frozen=True, slots=True)
class PICOBuilder:
    population: ConceptBlock | Iterable[str] | str
    intervention: ConceptBlock | Iterable[str] | str | None = None
    comparison: ConceptBlock | Iterable[str] | str | None = None
    outcome: ConceptBlock | Iterable[str] | str | None = None
    year_from: int | None = None
    year_to: int | None = None

    def build(self) -> SearchQuery:
        blocks = [
            _block(self.population).to_ast(),
            _block(self.intervention).to_ast(),
            _block(self.comparison).to_ast(),
            _block(self.outcome).to_ast(),
        ]
        nodes = tuple(node for node in blocks if node is not None)
        if not nodes:
            raise ValueError("PICO query requires at least one non-empty concept")
        ast = nodes[0] if len(nodes) == 1 else Boolean("AND", nodes)
        return SearchQuery.from_ast(ast, year_from=self.year_from, year_to=self.year_to)


@dataclass(frozen=True, slots=True)
class PECOBuilder:
    population: ConceptBlock | Iterable[str] | str
    exposure: ConceptBlock | Iterable[str] | str | None = None
    comparison: ConceptBlock | Iterable[str] | str | None = None
    outcome: ConceptBlock | Iterable[str] | str | None = None
    year_from: int | None = None
    year_to: int | None = None

    def build(self) -> SearchQuery:
        return PICOBuilder(
            population=self.population,
            intervention=self.exposure,
            comparison=self.comparison,
            outcome=self.outcome,
            year_from=self.year_from,
            year_to=self.year_to,
        ).build()
