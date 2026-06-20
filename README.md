# equilibrium-inn

A small **living-world instrument** built on
[equilibrium-engine](https://github.com/RobertMalczyk/equilibrium-engine): a
roadside inn of 7 characters, simulated over 3 in-world days and measured at the
*society* level. The point is **not a game** — it is an **observation and
validation cockpit** for the engine: a way to see whether coupled NPCs get bored,
seek activities, grow busy, tire, rest, sleep, recover, retain slower memory, and
react socially in **bounded, explainable** ways — and to convert what we learn
into the next engine iteration.

The unit of value is the **incident**: a rare, explainable, remembered deviation
from routine. A good run is a mostly-boring inn with occasional, causally
traceable texture. A constant brawl is a failure; a dead inn is a failure.

> ## ⚠️ Work in progress
>
> An **early-stage research instrument**, not a finished product or a playable
> game. Milestones **M-A** (instrument + G0 stability), **M-B** (G1 audit
> follow-through, Social Event Mapper Pack, two-profile split), **M-C**
> (interactive CLI stepper), **M-D** (Observation Mode + the Living Inn
> Observatory), **M-E** (baseline cast + regression harness), **M-F** (parity
> button + GitHub Pages), **M-G** (Controlled Subject / Intervention Mode),
> **M-H** (optional LLM semantic input seam), and **M-I** (intervention UI in the
> Observatory — a **live-frontier** cockpit: the observer acts only at the latest
> computed tick and the simulation unfolds forward from there) are complete;
> **G0/G1/G2** have all passed (G2 verified in-browser 2026-06-15). Quantitative
> choices remain provisional. See the per-milestone logs in
> [`registers/`](registers/).

## What works today

- **The full world layer:** schedule compiler, room presence + witnessing, the
  action→event transducer with provenance, the activity economy, the three-phase
  synchronous tick loop, deterministic session logging, and the complete society
  trace. A 7-persona, 3-day run takes ~5 s and is reproducible to a golden
  SHA-256.
- **The shared observation layer** (`inn/observe.py`): the single source of
  behavioural derivations — mood/mode labels, mode transitions (with driver
  inference), threshold crossings, deterministic ambient summaries, per-persona
  daily summaries, generalized causal `why`, validation reports, and the
  `build_model` the UI renders. The CLI and the Observatory both consume it; the
  UI never re-derives behaviour. **Reads only the trace.** No LLM is used in the
  simulation loop or in autonomous behaviour; the optional M-H seam (below) can
  map *observer* free text into a validated intervention candidate, but it is
  disabled by default and never required.
- **CLI Observation Mode** (`inn/cli.py`): a turn-based observer over the trace.
  Quiet stretches read as deterministic ambient prose, not "(N quiet ticks
  pass.)". Lenses: `observe`, `report`, `plot`, generalized `why`.
- **The Living Inn Observatory** (`inn/observatory.py`): a warm, hand-rolled
  SVG/Canvas page with an embedded visual asset pack (no CDN), shipped two ways —
  a **self-contained HTML export** of any run and a **Pyodide live cockpit** that
  runs the inn in-browser.
- **Controlled Subject / Intervention Mode** (`inn/intervention.py`, M-G): the
  observer can take manual control of **one** existing cast member. The subject
  stays a normal NPC — the engine still ticks it and computes its full interior
  (boredom/fatigue/anger/relations/potentials); the observer overrides only the
  **outward action**, routed through the **normal world/transducer/probe path** so
  the rest of the cast perceives and reacts. The trace records both
  `engine_would_have_selected` and `user_selected_action`. No engine state is ever
  mutated; the `intervention` record is emitted only when a subject is controlled,
  so autonomous runs stay byte-identical. Still **not a game**: no quests, goals,
  score, inventory, progression, or combat.
- **Optional LLM semantic input seam** (`inn/llm_seam.py`, M-H): **disabled by
  default**, enabled only via env vars. It maps observer *free text* into a
  *structured intervention candidate*, requires strict schema validation and an
  explicit `confirm`, then executes through the **exact M-G path**. It never sits
  in the engine loop, never mutates engine state, and never stores API keys in the
  trace, session log, or any output.
- **G0 stability experiment** and a suite of **validation reports**
  (`experiments/report_*.py`) answering the core questions: boredom→seeking,
  activity→fatigue, rest/sleep→recovery, scarcity, persona contrast.

## Quick start

```bash
git clone https://github.com/RobertMalczyk/equilibrium-inn
cd equilibrium-inn
git clone https://github.com/RobertMalczyk/equilibrium-engine
# the seam pins commit 0176dbd — check it out if main has moved on:
#   git -C equilibrium-engine checkout 0176dbd
python -m pip install -e ".[dev]"
python -m pytest tests -q          # full suite incl. the golden session
```

The inn consumes the engine **only** through a pinned commit, via a single seam
module (`inn/engine_surface.py`); the engine is a separate repo, **not** vendored
here. To bump the pin, edit `PINNED_COMMIT` in `inn/engine_surface.py` and
`meta.engine_commit` in `inn.yaml`, then regenerate the golden trace.

## Observe the inn (CLI)

```bash
python -m inn.cli                  # turn-based observer (Observation Mode on)
```

Inside, the observation verbs (all derived from `inn.observe`):

```
observe all                 # one-line mood/mode/room per NPC
observe <name>              # full state card: mood, mode, activity, need gauges
report day [N]              # per-persona time budget (busy/idle/seek/rest/sleep)
report npc <name>           # a persona across days + current card
report activity             # offers granted / contended / success
report sleep                # dusk→dawn fast-state recovery
report scarcity             # seekers denied an activity (starvation)
report incidents            # incident roster + cascade depth/breadth
plot <name> boredom fatigue # ASCII sparklines from the trace
why <name>                  # why their last act happened (manual vs autonomous)
wait [n] · sleep · mode · look · help · quit
```

You may also *perturb* the world as an outside probe
(`insult`/`help`/`command`/`serve <name>`) — the player is a probe source, not a
character.

### Controlled Subject / Intervention Mode (M-G)

Take manual control of one existing cast member. The engine keeps computing the
subject's full internal state; you override only its outward action, and that
action travels the same world/transducer/probe path an autonomous action would —
so the rest of the cast reacts normally (one-tick latency). `suggest` shows what
the engine *would* do; `why` distinguishes a manual override from autonomous
behaviour.

```
control welf        # take over Welf (starts in AUTO — you observe)
manual              # switch to MANUAL — your acts now drive the outward action
suggest             # what the engine is inclined to do + the legal palette
act insult halgrim  # a manual action, routed through the normal world path
why welf            # "MANUAL OVERRIDE … engine would have selected: …"
release             # hand Welf back to autonomous behaviour
```

Action palette: `insult`, `help`, `praise`, `serve`, `command`, `complain`,
`refuse`, `cold`/`cold_reply` (targeted), plus `observe`/`noop` (the subject
visibly does nothing — you just watch). Targets must be present/reachable with the
subject; there is no telepathic action. (`rest`/`seek_activity` are intentionally
**not** offered — there is no clean path to make the engine rest/seek on command
without mutating its state; that is future work.) This remains an observatory: no
quests, goals, score, inventory, progression, or combat.

### Optional LLM free-text seam (M-H)

**Off by default.** When enabled via env vars, free text is mapped to a structured
candidate, schema-validated, and shown for an explicit `confirm` before it runs —
through the *same* M-G path. The LLM never decides NPC behaviour, never enters the
engine loop, never mutates state, and its API key is never written to any trace,
session log, or output.

```bash
set EQUILIBRIUM_INN_LLM_PROVIDER=openai      # or: anthropic  (Linux/macOS: export)
set EQUILIBRIUM_INN_LLM_API_KEY=...          # read at call time only; never stored
# (optional) set EQUILIBRIUM_INN_LLM_MODEL=...
```

```
control welf
manual
say "tell Halgrim to calm down"   # -> proposed action + target + confidence
confirm                            # only now does it execute, via the M-G path
```

With no provider configured, `say`/`llm` print a clear "disabled" message and the
finite palette above remains fully usable.

## Baseline cast & regression harness

A deliberately **fair control** — the industry-standard NPC (schedule automaton +
trigger→bark table) — runs side-by-side with the engine on the *same* schedule,
world layer, and probes, so the comparison isolates the brain. It reuses the world
layer unchanged and emits the same trace schema, so every metric reads it.

```bash
python -m experiments.baseline_compare   # engine vs baseline metrics (Markdown)
python -m experiments.regression         # canonical protocols vs the frozen golden
python -m experiments.regression --freeze  # re-baseline the regression golden (ritual)
```

The regression harness freezes a compact metric fingerprint per canonical protocol
(impulse/step/control) at `tests/golden/regression_metrics.json`; `tests/test_regression.py`
asserts it. Baseline tunables live in `inn.yaml`'s `baseline` block.

## Generate validation reports

Each reads a trace (running one seeded session if absent) and writes Markdown to
`experiments/out/g0/reports/`:

```bash
python -m experiments.report_boredom_activity     # boredom → seeking → activity
python -m experiments.report_activity_fatigue     # activity/busy → fatigue
python -m experiments.report_rest_sleep_recovery  # rest/sleep → recovery
python -m experiments.report_scarcity             # thin / normal / rich catalog
python -m experiments.report_persona_contrast     # personas under one environment
```

## Build / export the Observatory

**Self-contained HTML export** (offline, shareable; no server, no Pyodide):

```bash
# produce a run, then export it to one standalone .html
python -c "from inn.config import load_inn_config; from inn.session import run_session; \
run_session(load_inn_config('inn.yaml'),'impulse','observatory/_run_impulse')"
python -m inn.observatory observatory/_run_impulse -o observatory/run.html --stride 2
# open observatory/run.html in any browser
```

The static export is **read-only**: it replays a recorded run. Its time scrubber
reviews history; it carries no live controls.

**Pyodide live cockpit** (runs the inn in-browser; profile/protocol/seed
controls). It is **interactive** — but only at the **live frontier**: the time
scrubber is a read-only history reviewer, and intervention is enabled only when the
playhead is at the frontier (see *Intervention console* below):

```bash
python observatory/build_bundle.py            # builds inn_bundle.zip + index.html
python -m http.server 8000 -d observatory     # serve (fetch needs http)
# open http://localhost:8000/
```

The cockpit bundles the inn + the **pinned engine** read-only (a `.engine_commit`
sentinel is written into the *bundle copy* only — the engine checkout is never
modified). Its visuals are fully embedded; the only network use is the **Pyodide
runtime**, which loads from the official CDN by default.

#### Intervention console in the Observatory (M-I)

The Observatory surfaces M-G/M-H as an **intervention console** — an observatory
control panel, not an RPG HUD (no quests/score/inventory/levels). The UI consumes
the model's intervention fields (`intervention_ui`, `interventions`); it never
recomputes engine behaviour. It shows the **controlled subject** (room, mode,
observer-facing state, and whether the latest outward action was *engine-selected*,
a *manual override*, or an *LLM-assisted* override), the **engine suggestion** (what
the autonomous NPC would have done — read-only), the **action palette** (the same
finite M-G actions; `rest`/`seek_activity` are intentionally absent, and
`observe`/`noop` are labelled as silence), the **latest intervention** (you-chose vs
engine-would-have, route, and the reactions it caused), a concise **summary**, and
teal timeline markers for overrides.

The cockpit uses a **live-frontier** model (`inn/live.py` `LiveSession`), *not* a
future-queue. The observer influences the world only at the **live frontier** (the
latest computed tick); the future then emerges from that new state. There is no
arbitrary-future scheduling: an action is validated against the live state **at
execution time** (no telepathy — the target must be co-located *now*), applied at the
frontier tick through the exact M-G path, and then the simulation advances. The same
`LiveSession` runs in CPython (pinned by the tests) and in Pyodide, so the browser
path is the tested path. Driving the live session forward incrementally is
byte-identical to a batch run carrying the same `(control, interventions)`.

- **Live cockpit** (`observatory/index.html`): `Run full simulation` computes the
  whole run for read-only review; `Start live session` (in the console) drives a
  mid-run frontier you can act at. Pick a subject, choose **AUTO** (engine drives) or
  **MANUAL** (you act), `Engine would…` (read-only suggestion), select a *valid
  target* (only cast co-located at the frontier), then **`Apply now and continue`**.
  The time scrubber is a **history reviewer**: scrub back and intervention controls
  disable with *“Reviewing history — return to the live frontier to intervene.”* The
  natural-language (M-H) box stays **disabled in the browser** (no provider/key is
  available there); the finite palette is fully functional.
- **Static export**: labelled **“static replay mode”** — it *renders* any recorded
  intervention trace (overrides, causality, teal markers) but offers no live controls.

The optional LLM free-text seam is exercised from the **CLI** (`say "…"` →
`confirm`); see *Optional LLM free-text seam (M-H)* above. A real-browser smoke
checklist lives at [`observatory/BROWSER_QA.md`](observatory/BROWSER_QA.md).

**Offline runtime (optional).** For a fully-offline cockpit, fetch the Pyodide
runtime locally (it is **not** committed to git):

```bash
python observatory/fetch_pyodide.py     # downloads Pyodide v0.26.2 -> observatory/pyodide/
python observatory/build_bundle.py      # build_bundle.py now uses the local copy
```

For release packaging, host the runtime via **Git LFS or a GitHub Release asset**,
never a raw git commit.

**Verify G2 parity (in-browser).** Run `python -m experiments.g2_parity` to write
the CPython reference (`observatory/g2_reference.json`) + a static fallback. Then
in the live cockpit click **Verify parity**: it runs the fixed 1,000-tick session
in Pyodide and compares its trace SHA-256 to the reference, showing pass/fail with
both SHAs. **G2 is closed only after a successful in-browser check.** Until then
the static export is the deterministic, blessed fallback — and a parity failure
does not break the Observatory (it just flags live mode as not-yet-blessed).

### Publish the public showcase (GitHub Pages)

One builder assembles the site (landing page + static Observatory + cockpit +
parity reference); preview it exactly as published:

```bash
python observatory/build_site.py                  # -> observatory/_site/
python -m http.server -d observatory/_site        # http://localhost:8000/
```

`.github/workflows/pages.yml` runs the same builder on every push to `main` and
deploys to GitHub Pages — **no secrets, no custom DNS** required. To enable it:
repo **Settings → Pages → Source: GitHub Actions**; the site then lives at the
`*.github.io` URL. **Custom domain (optional, later):** add a file
`observatory/CNAME` containing your domain (e.g. `equilibrium-engine.dev`) — the
builder copies it into the published site — and point the domain's DNS at GitHub
Pages.

### Visual assets

The Observatory's art pack lives in
[`observatory/assets/`](observatory/assets/) — currently **15 PNG files**
(backgrounds, hero, inn scene, parchment panel, behaviour-cycle promo, emblem,
lantern divider, NPC token frame, the need/affect/sleep/activity/causality icons,
and a fireflies overlay). At build/export time `inn.observatory.load_assets`
reads them, **web-optimizes** raster art (downscale + WebP via Pillow,
best-effort) and **base64-embeds** everything, so both deliverables stay offline
and a few MB rather than tens. The loader resolves each slot by **stem**, so an
asset may ship as `.png`, `.svg`, `.webp`, or `.jpg` interchangeably; any missing
file **falls back to a warm CSS gradient/texture**, so the page is always
presentable. See [`observatory/assets/README.md`](observatory/assets/README.md).

## Layout

```
inn/            world layer + observe.py (shared observation) + cli.py + observatory.py
                + intervention.py (M-G controlled subject) + llm_seam.py (M-H, optional)
observatory/    build_bundle.py (Pyodide cockpit + intervention console) + assets/
experiments/    g0_sweep/g0_report/chronicle/harvest, report_*.py, report_intervention, g2_parity
tests/          unit + determinism/import-contract + golden + observe/reports/observatory
                + test_intervention.py (M-G) + test_llm_seam.py (M-H)
registers/      m_a..m_e + m_g_h.yaml — running decision/finding logs (read for context)
inn.yaml        the entire inn as data (all behaviour-shaping numbers)
CLAUDE.md       the binding project contract
```

## AI-Assisted Development

This repository openly uses AI-assisted coding tools, including
[Claude Code](https://claude.com/claude-code), as an implementation accelerator —
for example, drafting code from explicit specs, test scaffolding, refactoring, and
documentation drafts. The conceptual model, architecture decisions, validation, and
final responsibility are **human-owned**: AI output is treated as a reviewed
implementation draft, not as authoritative, and is accepted only when it satisfies
the project contract ([`CLAUDE.md`](CLAUDE.md)) and passes the automated checks
(determinism, golden traces, scenario replay, and around 250 tests). See
[`AI_USAGE.md`](AI_USAGE.md) for the full policy.

## License

[Apache License 2.0](LICENSE). Copyright 2026 Robert Malczyk.
