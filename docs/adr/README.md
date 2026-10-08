# Architecture Decision Records — groundmeas

This directory tracks the architectural decisions taken in `groundmeas`.
The format is intentionally lightweight (Michael Nygard short form): a
context, a decision, and the consequences, each in plain Markdown.

Each ADR is numbered in the order it was accepted. Once accepted, an
ADR is not edited — superseding decisions are landed as new ADRs that
reference the older one in their *Status* line.

## Index

| ID       | Status   | Title                                              |
|----------|----------|----------------------------------------------------|
| 0001     | Accepted | Compatibility-shim deprecation strategy            |

## When to write an ADR

- A choice between two technologies or libraries with non-trivial
  trade-offs (driver, ORM, plotting backend, …).
- A migration window or removal timeline for a public-API element.
- A cross-repo convention that `groundmeas` adopts (for example, the
  prospective ADR-0013 in `groundfield` about `show_versions`).
- A non-obvious test-strategy decision that future contributors will
  question.

If a change is local to one file or one PR, prefer a CHANGELOG entry
and an inline docstring. ADRs are for decisions that future maintainers
need to understand *without* reading the relevant code.

## See also

- The same ADR practice is used in the sister package
  `groundfield/docs/adr/`; `groundinsight` has no ADR directory yet.
