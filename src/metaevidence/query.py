from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Iterable, Iterator


class QuerySyntaxError(ValueError):
    """Raised when a canonical MetaEvidence query cannot be parsed."""


class SearchField(str, Enum):
    ALL = "all"
    TITLE = "title"
    ABSTRACT = "abstract"
    TITLE_ABSTRACT = "title_abstract"
    KEYWORDS = "keywords"
    AUTHOR = "author"
    JOURNAL = "journal"
    AFFILIATION = "affiliation"


class QueryNode:
    """Marker base class for canonical search AST nodes."""


@dataclass(frozen=True, slots=True)
class Term(QueryNode):
    value: str

    @property
    def has_wildcard(self) -> bool:
        return "*" in self.value or "?" in self.value


@dataclass(frozen=True, slots=True)
class Phrase(QueryNode):
    value: str


@dataclass(frozen=True, slots=True)
class Boolean(QueryNode):
    operator: str
    children: tuple[QueryNode, ...]

    def __post_init__(self) -> None:
        op = self.operator.upper()
        if op not in {"AND", "OR"}:
            raise ValueError("Boolean operator must be AND or OR")
        if len(self.children) < 2:
            raise ValueError("Boolean nodes require at least two children")
        object.__setattr__(self, "operator", op)


@dataclass(frozen=True, slots=True)
class Not(QueryNode):
    child: QueryNode


@dataclass(frozen=True, slots=True)
class Field(QueryNode):
    field: SearchField
    child: QueryNode


@dataclass(frozen=True, slots=True)
class ControlledVocabulary(QueryNode):
    vocabulary: str
    term: str
    explode: bool = True


@dataclass(frozen=True, slots=True)
class Proximity(QueryNode):
    left: QueryNode
    right: QueryNode
    distance: int

    def __post_init__(self) -> None:
        if self.distance < 0:
            raise ValueError("Proximity distance cannot be negative")


_TOKEN_RE = re.compile(
    r'''\s*(?:
        (?P<LPAREN>\()|
        (?P<RPAREN>\))|
        (?P<COLON>:)|
        (?P<NEAR>NEAR/\d+)|
        (?P<AND>AND\b)|
        (?P<OR>OR\b)|
        (?P<NOT>NOT\b)|
        (?P<PHRASE>"(?:\\.|[^"\\])*")|
        (?P<WORD>[^\s():]+)
    )''',
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    position: int


def _unescape_phrase(token: str) -> str:
    inner = token[1:-1]
    return inner.replace(r'\"', '"').replace(r"\\", "\\")


def tokenize(expression: str) -> tuple[_Token, ...]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(expression):
        match = _TOKEN_RE.match(expression, pos)
        if not match:
            if expression[pos:].strip() == "":
                break
            raise QuerySyntaxError(f"Unexpected character at position {pos}: {expression[pos:pos+20]!r}")
        kind = match.lastgroup
        assert kind is not None
        value = match.group(kind)
        tokens.append(_Token(kind.upper(), value, match.start()))
        pos = match.end()
    return tuple(tokens)


_FIELD_ALIASES = {
    "all": SearchField.ALL,
    "title": SearchField.TITLE,
    "ti": SearchField.TITLE,
    "abstract": SearchField.ABSTRACT,
    "abs": SearchField.ABSTRACT,
    "title_abstract": SearchField.TITLE_ABSTRACT,
    "title-abstract": SearchField.TITLE_ABSTRACT,
    "tiab": SearchField.TITLE_ABSTRACT,
    "keyword": SearchField.KEYWORDS,
    "keywords": SearchField.KEYWORDS,
    "kw": SearchField.KEYWORDS,
    "author": SearchField.AUTHOR,
    "au": SearchField.AUTHOR,
    "journal": SearchField.JOURNAL,
    "source": SearchField.JOURNAL,
    "affiliation": SearchField.AFFILIATION,
    "aff": SearchField.AFFILIATION,
}

_CONTROLLED_ALIASES = {
    "mesh": "MeSH",
    "mesh_terms": "MeSH",
}


class QueryParser:
    """Recursive-descent parser for the MetaEvidence canonical query language.

    Grammar (highest to lowest precedence): NOT, NEAR/n, AND, OR.
    Field prefixes can scope a term, phrase, or parenthesized group.
    """

    def __init__(self, expression: str):
        self.expression = expression
        self.tokens = tokenize(expression)
        self.i = 0

    def parse(self) -> QueryNode:
        if not self.tokens:
            raise QuerySyntaxError("Search expression cannot be empty")
        node = self._parse_or()
        if self._peek() is not None:
            tok = self._peek()
            raise QuerySyntaxError(f"Unexpected token {tok.value!r} at position {tok.position}")
        return node

    def _peek(self, offset: int = 0) -> _Token | None:
        idx = self.i + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _accept(self, kind: str) -> _Token | None:
        tok = self._peek()
        if tok and tok.kind == kind:
            self.i += 1
            return tok
        return None

    def _expect(self, kind: str) -> _Token:
        tok = self._accept(kind)
        if tok is None:
            found = self._peek()
            detail = "end of expression" if found is None else repr(found.value)
            raise QuerySyntaxError(f"Expected {kind}, found {detail}")
        return tok

    def _parse_or(self) -> QueryNode:
        children = [self._parse_and()]
        while self._accept("OR"):
            children.append(self._parse_and())
        return children[0] if len(children) == 1 else Boolean("OR", tuple(children))

    def _parse_and(self) -> QueryNode:
        children = [self._parse_near()]
        while self._accept("AND"):
            children.append(self._parse_near())
        return children[0] if len(children) == 1 else Boolean("AND", tuple(children))

    def _parse_near(self) -> QueryNode:
        node = self._parse_not()
        while True:
            tok = self._accept("NEAR")
            if tok is None:
                break
            distance = int(tok.value.split("/", 1)[1])
            right = self._parse_not()
            node = Proximity(node, right, distance)
        return node

    def _parse_not(self) -> QueryNode:
        if self._accept("NOT"):
            return Not(self._parse_not())
        return self._parse_primary()

    def _parse_primary(self) -> QueryNode:
        if self._accept("LPAREN"):
            node = self._parse_or()
            self._expect("RPAREN")
            return node

        tok = self._peek()
        if tok is None:
            raise QuerySyntaxError("Unexpected end of expression")

        # Prefix syntax: title:..., abstract:..., mesh:...
        if tok.kind == "WORD" and self._peek(1) and self._peek(1).kind == "COLON":
            prefix = tok.value.lower()
            self.i += 2
            child = self._parse_primary()
            if prefix in _CONTROLLED_ALIASES:
                text = literal_text(child)
                if text is None:
                    raise QuerySyntaxError(f"Controlled vocabulary prefix {prefix}: requires a term or phrase")
                return ControlledVocabulary(_CONTROLLED_ALIASES[prefix], text)
            if prefix not in _FIELD_ALIASES:
                raise QuerySyntaxError(f"Unknown field prefix: {tok.value}")
            return Field(_FIELD_ALIASES[prefix], child)

        if tok.kind == "PHRASE":
            self.i += 1
            return Phrase(_unescape_phrase(tok.value))
        if tok.kind == "WORD":
            self.i += 1
            return Term(tok.value)

        raise QuerySyntaxError(f"Unexpected token {tok.value!r} at position {tok.position}")


def parse_query(expression: str) -> QueryNode:
    return QueryParser(expression).parse()


def _escape_phrase(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', r'\"')


def render(node: QueryNode) -> str:
    """Render an AST back to normalized canonical MetaEvidence syntax."""
    if isinstance(node, Term):
        return node.value
    if isinstance(node, Phrase):
        return f'"{_escape_phrase(node.value)}"'
    if isinstance(node, ControlledVocabulary):
        vocab = node.vocabulary.lower()
        prefix = "mesh" if vocab == "mesh" else vocab
        return f'{prefix}:"{_escape_phrase(node.term)}"'
    if isinstance(node, Field):
        return f"{node.field.value}:{render(node.child)}"
    if isinstance(node, Not):
        child = render(node.child)
        if isinstance(node.child, Boolean):
            child = f"({child})"
        return f"NOT {child}"
    if isinstance(node, Proximity):
        left = render(node.left)
        right = render(node.right)
        return f"{left} NEAR/{node.distance} {right}"
    if isinstance(node, Boolean):
        parts: list[str] = []
        for child in node.children:
            text = render(child)
            if isinstance(child, Boolean) and child.operator != node.operator:
                text = f"({text})"
            parts.append(text)
        return f" {node.operator} ".join(parts)
    raise TypeError(f"Unsupported node type: {type(node)!r}")


def literal_text(node: QueryNode) -> str | None:
    if isinstance(node, (Term, Phrase)):
        return node.value
    return None


def walk(node: QueryNode) -> Iterator[QueryNode]:
    yield node
    if isinstance(node, Boolean):
        for child in node.children:
            yield from walk(child)
    elif isinstance(node, Not):
        yield from walk(node.child)
    elif isinstance(node, Field):
        yield from walk(node.child)
    elif isinstance(node, Proximity):
        yield from walk(node.left)
        yield from walk(node.right)


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Source-neutral systematic-review search specification."""

    expression: str
    year_from: int | None = None
    year_to: int | None = None
    fields: tuple[str, ...] = field(default_factory=lambda: ("title", "abstract", "keywords"))

    def __post_init__(self) -> None:
        if not self.expression.strip():
            raise ValueError("Search expression cannot be empty")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from cannot be greater than year_to")
        # Fail early: malformed search strategies must never be silently transmitted.
        parse_query(self.expression)

    @property
    def ast(self) -> QueryNode:
        return parse_query(self.expression)

    @property
    def canonical(self) -> str:
        return render(self.ast)

    @classmethod
    def from_ast(
        cls,
        ast: QueryNode,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        fields: Iterable[str] = ("title", "abstract", "keywords"),
    ) -> "SearchQuery":
        return cls(render(ast), year_from=year_from, year_to=year_to, fields=tuple(fields))
