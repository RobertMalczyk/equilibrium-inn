# equilibrium-inn

A small **living-world instrument** built on
[equilibrium-engine](https://github.com/RobertMalczyk/equilibrium-engine): a
roadside inn of 7 characters, simulated over 3 in-world days and measured at the
*society* level. The point is not a game — it is an instrument for studying how
the engine's individual character dynamics behave when they are **coupled**, and
for converting what we learn into the next engine iteration.

The unit of value is the **incident**: a rare, explainable, remembered deviation
from routine. A good run is a mostly-boring inn with occasional, causally
traceable texture. A constant brawl is a failure; a dead inn is a failure.
Quantifying that corridor is the instrument's first job.

> ## ⚠️ Work in progress
>
> This is an **early-stage research instrument**, not a finished product or a
> playable game. The design is **unverified** — every quantitative choice is
> provisional. Milestone **M-A** (the instrument + the G0 stability experiment)
> is complete and the **G0 gate has passed**; the project is currently paused at
> the **G1 audit** (semantics review). Expect rough edges, churn, and parameters
> that may change wholesale after the audit. See **[Current status & open
> issues](#current-status--open-issues)** below.

## What works today

- The full world layer: schedule compiler, room presence + witnessing, the
  action→event transducer with provenance, the activity economy, the
  three-phase synchronous tick loop, deterministic session logging, and the
  complete society trace.
- A deterministic, replayable simulation — a 7-persona, 3-day run takes ~5 s and
  is reproducible to a golden SHA-256.
- The **G0 stability experiment**: a parameter sweep (transducer intensity ×
  recovery × catalog richness) over impulse / step / control protocols, a
  formal linearized-stability check, and a generated report.
- A prose **chronicle** renderer with per-incident "why-chains" (the text form
  of the planned CLI's `why <name>`).

## Current status & open issues

G0 passed: across all 30 swept cells the inn **settles** (none saturate, none
limit-cycle), the canonical run sits **in the 4–10 incident corridor**, and the
control protocol is silent. Getting there required substantial damping work
(full account in [`registers/m_a.yaml`](registers/m_a.yaml) and
[`CHANGELOG.md`](CHANGELOG.md)).

**Open issues / decisions awaiting the G1 audit** — these parameters tamed the
inn but are **not yet blessed as legitimate world-design**:

1. **Scarcity fork (the big one).** The committed "hearth fallback" hardened a
   thin-catalog runaway but, as tuned, makes the inn *scarcity-immune* (thin ≈
   normal ≈ rich). The alternative (frustration-only idle recovery) preserves a
   thin>rich gradient but recenters the corridor. The instrument's character
   hinges on this choice.
2. **Idle recovery disabled inn-wide** — reverses an engine homeostasis fix in
   this context; the corridor depends on it.
3. **Outburst vents anger (−0.50)** — the single load-bearing damping change,
   but it is inn-authored; the engine's calibration does not own it.
4. **`reactive_window_ticks = 1`** — adopted from the engine's burst eval, not
   from calibrated defaults.
5. **Root-vs-hop witnessing asymmetry** (0.5 vs 0.15) — new world semantics.

**Known declared gap (by design, not a bug):** the transducer cannot perceive
`refuse` / `cold_response` / `complain` — the authority loop closes one way
only. This ships stated and is the flagship candidate for the first engine spec
extension.

**Other notes:** the formal stability analysis is a *piecewise* linearization
and is regime-local; the empirical sweep is authoritative. Several modules
(CLI stepper, viewer, baseline cast, regression harness) are planned but not
built (milestones M-C..M-F).

## Setup

The inn consumes the engine **only** through a pinned commit, via a single seam
module (`inn/engine_surface.py`). The engine is a separate repo and is **not**
vendored here. Clone it as a sibling directory inside this repo:

```bash
git clone https://github.com/RobertMalczyk/equilibrium-inn
cd equilibrium-inn
git clone https://github.com/RobertMalczyk/equilibrium-engine
# the seam pins commit 3dcf4a3 — check it out if main has moved on:
#   git -C equilibrium-engine checkout 3dcf4a3
python -m pip install -e ".[dev]"
```

The engine's `eval/` package is not pip-installable, so the seam puts the engine
checkout on `sys.path` and asserts the pinned commit at import. To bump the pin,
edit `PINNED_COMMIT` in `inn/engine_surface.py` and `meta.engine_commit` in
`inn.yaml`, then regenerate the golden trace.

## Running

```bash
python -m pytest tests -q                 # 31 tests incl. the golden session
python -m experiments.g0_sweep            # the G0 parameter sweep
python -m experiments.g0_formal           # linearized-stability analysis
python -m experiments.g0_report           # build the report + chronicle
python -m experiments.chronicle           # prose chronicle of the canonical run
python -m experiments.regen_golden        # deliberately re-baseline the golden
```

Outputs land in `experiments/out/` (gitignored). The report is written to
`experiments/out/g0/g0_report.md`.

## Layout

```
inn/            world layer (engine_surface, config, schedule, presence,
                transducer, economy, inbox, world_state, loop, session,
                trace, metrics)
experiments/    g0_sweep, g0_formal, g0_report, chronicle, regen_golden
tests/          unit + determinism/import-contract + golden
registers/      m_a.yaml — running decision/finding log (read this for context)
inn.yaml        the entire inn as data (all behavior-shaping numbers)
CLAUDE.md       the binding project contract
CHANGELOG.md    parameter history, starting point → current
```

## License

[Apache License 2.0](LICENSE). Copyright 2026 Robert Malczyk.
