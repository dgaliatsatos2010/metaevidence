# M2 Formal Query Language and Translation Fidelity

## Purpose

M2 converts a systematic-review strategy into an explicit abstract syntax tree (AST). The AST is the source-neutral object that later adapters compile into database-specific queries. This separates **review intent** from **database syntax**.

## Canonical grammar implemented in v0.2-dev

Precedence, from strongest to weakest:

1. `NOT`
2. `NEAR/n`
3. `AND`
4. `OR`

Supported primary operands are unquoted terms, quoted phrases, parenthesized groups, bibliographic field prefixes, and MeSH concepts.

Examples:

```text
(diabetes OR obesity) AND "machine learning"
title:"machine learning" AND abstract:prediction
mesh:"Diabetes Mellitus, Type 2" AND predict*
"machine learning" NEAR/5 outcome
```

## AST node types

- `Term`
- `Phrase`
- `Boolean`
- `Not`
- `Field`
- `ControlledVocabulary`
- `Proximity`

## Auditable translation statuses

Every source-specific compilation can emit diagnostics using five statuses:

- `EXACT`: intended semantics represented directly;
- `EXPANDED`: semantics preserved by an explicit expansion into multiple source clauses;
- `APPROXIMATED`: close mapping, but the source scope/operator is not identical;
- `REVIEW_REQUIRED`: automated translation is possible only with a consequential assumption that a reviewer should inspect;
- `UNSUPPORTED`: the target source cannot safely represent the canonical feature in the current compiler mode.

The v0.2 prototype uses a transparent provisional scoring map:

| Status | Score |
|---|---:|
| EXACT | 1.00 |
| EXPANDED | 0.90 |
| APPROXIMATED | 0.70 |
| REVIEW_REQUIRED | 0.40 |
| UNSUPPORTED | 0.00 |

`fidelity_score` is the mean feature score and `loss_score = 1 - fidelity_score`. These values are **research diagnostics, not yet validated measurements of retrieval equivalence**. M8 will empirically validate or recalibrate them against paired database-search experiments.

## Scientific rationale

The central hypothesis is that query translation should be treated as an observable transformation with an audit trail rather than an invisible string rewrite. Future validation will compare canonical-to-source automated translations with expert manual translations and evaluate retrieval overlap, missed eligible studies, excess retrieval, clause-level disagreements, and reviewer adjudication.

## Current deliberate limitations

- OpenAlex field-rich translation will move to its current OQL surface in the live-adapter milestone.
- Crossref `query.bibliographic` is treated as a relevance-oriented metadata query, not as a Boolean-equivalent systematic-review engine.
- Controlled vocabularies other than the currently modeled MeSH concept are not yet implemented.
- Default field-set equivalence is flagged when a source cannot express the canonical scope as one exact operation.
- The provisional fidelity weights must not yet be interpreted as calibrated probabilities.
