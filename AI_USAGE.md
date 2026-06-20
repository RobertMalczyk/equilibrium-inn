# AI Usage Policy

This project uses AI-assisted development tools, including
[Claude Code](https://claude.com/claude-code), as part of the implementation
workflow. This document states how that assistance is used and where
responsibility lies.

## How AI assistance is used

AI assistance may be used for:

- drafting implementation code from explicit specifications,
- generating test scaffolding,
- refactoring,
- documentation drafts,
- exploratory prototypes.

## How AI assistance is *not* used

AI assistance is **not** treated as a source of truth. The maintainer remains
responsible for:

- the conceptual model,
- architecture decisions,
- acceptance criteria,
- review and validation,
- test coverage,
- licensing and maintainability,
- final repository content.

All AI-assisted output is treated as an **untrusted implementation draft** until
it has been reviewed, tested, and aligned with the project specification. A draft
is not accepted because it looks plausible; it is accepted because it satisfies a
stated contract and passes the project's checks.

## What keeps the work auditable

The project is developed around explicit specifications, traces, scenario-based
validation, and automated tests, so AI-assisted contributions can be held to the
same standard as any other change:

- a binding written contract — [`CLAUDE.md`](CLAUDE.md) — defines the
  architecture, hard rules, and gates;
- per-milestone decision and finding logs live in [`registers/`](registers/);
- runs are deterministic and replayable (a session is fixed by its inputs;
  scenarios are lossless and reproduce bit-for-bit), and a golden trace guards
  against silent behavioural drift;
- the repository carries a substantial automated test suite (currently around 250
  automated tests) covering determinism, contracts, semantics, observability, and
  stability.

AI may assist with implementation, but the model must remain **explainable,
testable, and auditable**.

---

In short: **AI-assisted, human-owned, spec-driven, and test-validated.**
