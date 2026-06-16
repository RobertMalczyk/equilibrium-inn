# Observatory — browser smoke checklist (M-I)

A manual, real-browser smoke test for the intervention UI. The cockpit runs the
inn in-browser under Pyodide (tens of MB), so this is a documented checklist
rather than an automated headless test. The non-browser layers (model fields, the
static export, the cockpit page build, and the cockpit/shared JS syntax) are
covered by `tests/test_intervention_ui.py` + `node --check` in CI.

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

## Smoke scenario

1. Open the **landing page** (`/` from `build_site`, or `index.html` directly for
   the cockpit).
2. Open the **live cockpit**; wait for “ready”.
3. **Run simulation** (default profile/protocol/seed). The scene, cards, ribbons,
   and stream populate. The **Intervention console** card appears with the tag
   **“live cockpit”**.
4. In the console, select one NPC as the **controlled subject**.
5. Switch **mode** to **MANUAL**. The “Controlled subject” box shows the subject
   with a **MANUAL** badge, its room/mode, and “latest action: …”.
6. Click **Suggest** → the hint shows *“engine would select for &lt;name&gt; at
   tick T: &lt;action&gt;”* (read-only). The “Engine suggestion” box mirrors this.
7. Choose a **valid target** — the dropdown lists only cast **present with the
   subject** at the chosen tick. (Pick a tick where the subject shares a room;
   otherwise the hint says they are alone and targeted actions are unavailable.)
8. Execute a manual action (e.g. **praise** or **insult**): **Add override** then
   **Run with control**.
9. Confirm the UI shows, for the override:
   - **selected_by: manual override** (badge “manual” / “LLM-assisted”),
   - **user_selected_action** (e.g. *insult*),
   - **engine would have: …** (the autonomous choice),
   - **route** (e.g. *transduce* for insult, *probe* for command/serve).
   Note: a manual `insult` routes through the engine action `outburst` — the UI
   shows **you selected: insult** + **route**, and never implies the NPC had a
   spontaneous outburst.
10. Open the **Why — causality** panel for the subject → it reads
    *“MANUAL OVERRIDE by the observer … the engine would have selected: …”*.
11. Scrub the timeline past the override tick → observe the **target NPC reacting**
    (one-tick latency) in the stream/cards, attributed back to the subject. A
    **teal marker** sits on the subject’s ribbon at the override tick.
12. Switch mode to **AUTO** and **Run with control** (or **Release** by selecting a
    different subject) → the subject is observed autonomously again; the “latest
    action” reads **engine-selected (autonomous)**.
13. Confirm autonomous behaviour resumes (no overrides; the panel summary updates).
14. Confirm the **LLM panel** reads *“Natural language intervention is optional and
    currently disabled”* (the browser has no provider/key) and the **palette stays
    fully usable**.
15. Open the browser **console** → **no JS errors**.

## Observer vs Developer view

- **Developer view** (toggle in the top bar) adds provenance to the intervention
  result: `selected_by`, tick, route, and LLM candidate/provenance when present.
- **Observer view** keeps friendly labels and no raw floats.

## Expected limitations (by design)

- The cockpit re-runs the whole 3-day session deterministically with the queued
  overrides (batch), rather than stepping one tick at a time — overrides are
  reproducible and replayable.
- The **M-H LLM seam is browser-disabled** (no network provider in Pyodide). Use
  the **CLI** (`say "…"` → `confirm`) to exercise the LLM path with a configured
  provider. Tests use a fake client — never a real API call.
- `rest` / `seek_activity` are **not** offered: there is no clean world/transducer
  path to make the engine rest or seek on command without mutating engine state
  (forbidden). This is documented as future work needing an engine-side seam.
