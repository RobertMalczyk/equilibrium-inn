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
> (interactive CLI stepper), and **M-D** (Observation Mode + the Living Inn
> Observatory) are complete; **G0** has passed and **G1 semantics are signed
> off**. Quantitative choices remain provisional. See the per-milestone logs in
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
  UI never re-derives behaviour. **Reads only the trace; no LLM anywhere.**
- **CLI Observation Mode** (`inn/cli.py`): a turn-based observer over the trace.
  Quiet stretches read as deterministic ambient prose, not "(N quiet ticks
  pass.)". Lenses: `observe`, `report`, `plot`, generalized `why`.
- **The Living Inn Observatory** (`inn/observatory.py`): a warm, hand-rolled
  SVG/Canvas page with an embedded visual asset pack (no CDN), shipped two ways —
  a **self-contained HTML export** of any run and a **Pyodide live cockpit** that
  runs the inn in-browser.
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
why <name>                  # why their last act happened — routine acts too
wait [n] · sleep · mode · look · help · quit
```

You may also *perturb* the world (`insult`/`help`/`command`/`serve <name>`) — the
player is a probe source, not a character. This stays an observatory: there are
no quests, goals, score, inventory, or progression.

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

**Pyodide live cockpit** (runs the inn in-browser; profile/protocol/seed
controls):

```bash
python observatory/build_bundle.py            # builds inn_bundle.zip + index.html
python -m http.server 8000 -d observatory     # serve (fetch needs http)
# open http://localhost:8000/
```

The cockpit bundles the inn + the **pinned engine** read-only (a `.engine_commit`
sentinel is written into the *bundle copy* only — the engine checkout is never
modified). The page's visuals are fully embedded (no other network use).

**Offline runtime (optional).** The **Pyodide runtime** loads from its official
CDN by default. For a fully-offline cockpit, fetch it locally (it is **not**
committed to git):

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
observatory/    build_bundle.py (Pyodide cockpit) + assets/ (visual pack)
experiments/    g0_sweep/g0_report/chronicle/harvest, report_*.py, g2_parity
tests/          unit + determinism/import-contract + golden + observe/reports/observatory
registers/      m_a..m_d.yaml — running decision/finding logs (read for context)
inn.yaml        the entire inn as data (all behaviour-shaping numbers)
CLAUDE.md       the binding project contract
```

## License

[Apache License 2.0](LICENSE). Copyright 2026 Robert Malczyk.
