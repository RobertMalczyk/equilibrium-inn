# M-J — Time Plots subpage (engine-study instrument)

**Status:** PLAN (grilled & locked 2026-06-17, by the user, in writing). Not yet built.
**Goal:** A new self-contained "Time Plots" page on the Observatory site showing
time-series line plots of engine state variables across the canonical runs, so the
observer can *read the engine's actual dynamics* — fast spike-and-vent vs. slow
permanent relational marks — rather than only the mode-ribbon abstraction.

**Hard-rule posture:** Observability/rendering ONLY. Reads the society trace, never live
engine objects (rule 0.4). ZERO dynamics changes; golden trace + import contract +
G2 parity all untouched. The engine repo is not touched in any way (rules 0.1/0.2).

---

## Locked decisions (the grilled design tree)

| # | Decision | Ruling |
|---|---|---|
| Q1 | Primary purpose | **Causality / incidents** (goal b). Incidents are the **spine**; dynamics-intuition falls out for free. |
| Q2 | Navigation unit | **Overview + drill-down** (a). Full-run strip for orientation; zoom for legibility. Incidents are sparse (12 transduction-ticks / 2151). |
| Q3/Q4 | Interaction | **Interactive** — click an incident to jump+zoom, plus free zoom/pan to widen back to the big picture. Driver = **brush + buttons** (Q4a): drag-select on an always-visible overview strip; incident shortcut buttons (outburst-only jump targets); zoom-out / full-run / next-prev buttons. |
| — | Data fidelity | **Full-resolution embed** (no build-time downsampling). ~7 personas × 10 states + room_tension ≈ 150k numbers, quantized to 3 decimals ≈ ~1 MB/run. Render decimates on-the-fly per zoom level. |
| Q5 | Focus content | **Faceted small-multiples, shared time-window** (a). One small chart per state; all personas overlaid (color = persona). Brush sets ONE window across the whole grid → vertical read across states at an instant. Persona-mute legend. |
| Q5b | Default facets | **7 high-signal open**: anger, stress, frustration, self_control, sleep_pressure, boredom, room_tension. **3 collapsed**: duty, hunger, satisfaction. (room_tension = single world line, not per-persona.) |
| Q6 | Incident markers | **Tiered, mark all transductions** (b): outbursts = bold/tall (the spine, per DEC-8 `incident_def`=outburst-only); S3 social events (refusal/complaint/cold_reply) = faint/short (the interesting near-misses). Hover any marker → provenance tuple (actor→target, action, intensity, `provoked_by`). Incident **shortcut buttons** remain outburst-only. |
| Q7 | Runs | **All three protocols, switchable** (b): impulse / step (rain) / control (nothing). Protocol selector swaps the embedded dataset. Reads as the regression-protocol viewer. |
| Q8 | Relations tensor | **Include now, collapsed** (a). Same render machinery. Default: **only directed pairs that moved** (max−min > epsilon); "show all pairs" toggle. Closes the loop: fast vent (state facet) vs. slow permanent resentment step (relation facet) on the SAME x-axis. |
| Q9 | x-axis | **Both** (c): in-world Day/HH:MM primary labels + night shading + day-boundary gridlines; raw tick + exact value + persona in the hover readout (ties incidents to `why`/provenance IDs like `418:wojslaw:outburst`). |
| Q10/Q11 | Persona colors | **Fixed palette in `inn.yaml`** (Q10a): optional `color: "#rrggbb"` per cast entry. **Generated hue-ramp fallback** (Q10b) if omitted. Defaults drawn from the existing `observatory.py` theme accents (`--incident #b5532e`, `--seeking #d99a2b`, `--busy #7c9e5e`, `--sleep #4655bf`, …) so the palette is native to the site. Persistent legend maps name→color across all facets. Loader: one tolerant optional read in `inn/config.py`, no validation tightening. |
| Q12 | Hosts | **Both** (b): shared JS render layer consumed by (1) static `plots.html` and (2) the live Pyodide cockpit. |
| Q13 | Tech + guardrails | **Canvas** + on-the-fly per-zoom decimation over full-res embedded data. Tests: model-shape, export smoke, golden+import untouched. |
| Q14 | (b) scope + parity | Cockpit plotting reads the LIVE trace and renders only — does NOT touch sim/trace/golden, so **G2 parity unaffected**. |

---

## Components

1. **`inn/timeplots.py`** (new — analysis + render, sibling to `inn/observatory.py`)
   - `build_plot_model(records, cfg, meta=None) -> dict` — full-res per-persona series for
     all 10 states + `world.room_tension.*`; relation tensor reduced to **moved pairs**
     (with an `all_pairs` payload behind the toggle); day/night/rain bands; tiered incident
     markers (tick, time, actor, target, action, intensity, `provoked_by`, tier). Pure read
     over trace dicts + `metrics.state_series` (metrics.py:196) and the relations read
     (metrics.py:166). Numbers quantized to 3 decimals.
   - Persona color resolution: `inn.yaml` `cast[].color` → else generated hue-ramp, by
     canonical cast order.
   - `render_js()` / shared canvas render module — the SHARED layer (Q12b). Faceted grid,
     brush+buttons, tiered markers, hover readout, protocol selector hook, collapsible
     relations section, legend mutes.
   - `page(model, assets=None) -> str` and `export_html(trace_dir, out_html) -> Path`
     (self-contained; mirrors `observatory.export_html`). Reuses `observatory.load_assets`
     + `_asset_css` for theme consistency.
   - `main(argv)` — `python -m inn.timeplots <trace_dir> -o plots.html`.

2. **`inn/config.py`** — tolerant optional read of `cast[].color`; surface per-persona color
   in the loaded config. No required-field / validation changes.

3. **`inn.yaml`** — add optional `color:` to each of the 7 cast entries (theme-derived).

4. **`observatory/build_site.py`** — new step: run the **three** protocols (impulse already
   run for the static Observatory; add step + control), and emit `plots.html` with all three
   datasets embedded + switchable. (Three deterministic ~2 s runs at build time.)

5. **Cockpit** (`observatory/build_bundle.py` / `build_index`) — bundle the shared render
   module; add a **"Time Plots" panel/tab** fed the live run's trace, regenerated
   client-side. Plot panel reads-only; no sim/trace coupling.

6. **`observatory/landing.html`** — third button **"Open time plots"** + one-line blurb
   ("raw engine state trajectories across the three regression protocols, for study").

7. **Tests** (match `observatory` test style):
   - `build_plot_model` shape: series present, lengths == tick count, markers tiered,
     moved-pairs filter correct, color resolution (config + fallback).
   - `export_html` smoke: file builds, contains `<canvas>`, embedded data for all 3 protocols.
   - Explicit assertion: golden trace SHA + import contract unchanged (observability-only).

---

## Scope guardrails / non-goals
- NO changes to `inn/loop.py`, transducer, economy, schedule, or any dynamics.
- NO trace-schema change; G2 parity surface untouched.
- Three canonical protocol runs only (deterministic, CI-stable). No live-regeneration on
  the static page (cockpit handles "run your own").
- Relations default to moved-pairs to avoid 42 flat lines; full tensor behind a toggle.

## Open / deferred
- Reorder/save facet layout — not in v1 (facets collapse/expand only).
- Export-to-PNG of a facet — nice-to-have, deferred.
- Register file `registers/m_j.yaml` to be created at the M-J AUDIT checkpoint.
