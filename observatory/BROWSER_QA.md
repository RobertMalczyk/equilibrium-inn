# Observatory — browser smoke checklist (M-I)

A real-browser smoke test for the live-frontier intervention UI. The cockpit runs
the inn in-browser under Pyodide, so CI relies on a documented checklist plus the
non-browser layers (model fields, static export, cockpit page build, JS
`node --check`) covered by `tests/test_intervention_ui.py`,
`tests/test_intervention_frontier.py` (incl. live-frontier == batch equivalence and
execution-time target validation).

## Last automated headless run — 2026-06-17 (Chrome, puppeteer-core) — 11/11 PASS, 0 console errors

Driven against `python -m http.server -d observatory` with the system Chrome
(headless). All checks below were exercised programmatically and passed:

| Check | Result |
|---|---|
| Pyodide boots + autonomous run renders the console | PASS |
| `Start live intervention` (welf, MANUAL) starts at a mid-run frontier | PASS |
| Target dropdown lists only co-located cast (`["wojslaw"]` at the seed frontier) | PASS |
| `LIVE FRONTIER — interventions enabled` tag visible; Apply enabled | PASS |
| `Apply intervention` applies (manual_override recorded, target wojslaw) | PASS |
| Teal marker present + interactive (canvas cursor=pointer, onclick+onmousemove wired) | PASS |
| Hovering a marker pops the note tooltip | PASS |
| Scrub to history → action/Apply/Advance disabled, `REVIEWING HISTORY` tag, Return visible | PASS |
| `⟲ Return to live frontier` re-enables controls, `LIVE FRONTIER` tag returns | PASS |
| No app console errors (favicon request suppressed via `<link rel=icon href='data:,'>`) | PASS |

Reproduce: install `puppeteer-core` (uses the system Chrome — no Chromium
download), serve `observatory/`, and drive the page (select `#iv_subj`, `#iv_mode`,
click `#iv_start` / `#iv_apply`, scrub `#scrub`, click `#iv_return`), asserting on
`liveInfo()` / `window.MODEL.interventions` / the `#iv_live` state tag. Note: `LIVE`
is a script-lexical `let` (not on `window`); read frontier state via the global
`liveInfo()` instead.

This stays an **observatory, not a game**: there are no quests, goals, score,
inventory, progression, win/loss, or combat — only observation, controlled
intervention, and causal explanation.

## Build + serve

```bash
python observatory/build_bundle.py            # builds inn_bundle.zip + index.html
python -m http.server 8000 -d observatory     # fetch needs http
# open http://localhost:8000/
```

(For the full published site — landing + static export + cockpit + parity
reference — use `python observatory/build_site.py` and serve `observatory/_site/`.)

## Smoke scenario (live-frontier model)

The observer acts **only at the live frontier**; the future emerges from that new
state. There is **no future-queue**: you act now and the sim advances.

1. Open the **live cockpit**; wait for “ready”.
2. **Run full simulation** (default profile/protocol/seed) → the whole run computes
   for **read-only review**; scrub the timeline as history. The **Intervention
   console** card appears tagged **“live cockpit”**.
3. In the console, pick a **controlled subject** and **MANUAL**, then click
   **Start live session** → a fresh run advances to a mid-run frontier you can act
   at. The live line reads **“LIVE — at the frontier (day D HH:MM)”**.
4. Click **Engine would…** → the hint shows the engine’s read-only suggestion for
   the subject (never forced). The “Engine suggestion” box mirrors it.
5. Choose a **valid target** — the dropdown lists only cast **co-located with the
   subject at the live frontier**. If the subject is alone, targeted actions are
   disabled with a hint to **Advance ▶** to a gathering.
6. Click **Apply now and continue** (e.g. **praise** or **insult**). The action is
   validated against the frontier at execution time, applied at the frontier tick
   through the normal world path, and the sim advances. The playhead follows the
   new frontier.
7. Confirm the panels show, for the override: **you selected: …**, **engine would
   have: …**, **route** (*transduce* for insult, *probe* for command/serve). A
   manual `insult` routes through engine action `outburst` — the UI says **you
   selected: insult**, never implying a spontaneous outburst.
8. **Why — causality** for the subject reads *“MANUAL OVERRIDE by the observer …
   the engine would have selected: …”* — and follows the playhead (no day-3 act
   shown while on day 1).
9. A **teal marker** sits on the subject’s ribbon at the override tick; the target
   **reacts** (one-tick latency) in the stream, attributed back to the subject.
10. **Scrub back** into history → all intervention controls **disable** and the
    line reads **“Reviewing history — return to the live frontier to intervene.”**
    Click **Return to live frontier** → controls re-enable.
11. Switch mode to **AUTO** and **Advance ▶** → the engine drives the subject again.
    Selecting **— none (observe) —** releases control.
12. Confirm the **LLM panel** reads *“Natural language intervention is optional and
    currently disabled”* (no browser provider/key) and the **palette stays usable**.
13. Open the browser **console** → **no JS errors**.

## Observer vs Developer view

- **Developer view** (toggle in the top bar) adds provenance to the intervention
  result: `selected_by`, tick, route, and LLM candidate/provenance when present.
- **Observer view** keeps friendly labels and no raw floats.

## Expected limitations (by design)

- The cockpit drives the run forward **incrementally from the live frontier**
  (`inn.live.LiveSession`); this is **byte-identical** to a batch run carrying the
  same `(control, interventions)`, so overrides stay reproducible and replayable
  while remaining honest about emergent future state. There is **no** future-queue
  and **no** arbitrary-future scheduling.
- The **M-H LLM seam is browser-disabled** (no network provider in Pyodide). Use
  the **CLI** (`say "…"` → `confirm`) to exercise the LLM path with a configured
  provider. Tests use a fake client — never a real API call.
- `rest` / `seek_activity` are **not** offered: there is no clean world/transducer
  path to make the engine rest or seek on command without mutating engine state
  (forbidden). This is documented as future work needing an engine-side seam.
