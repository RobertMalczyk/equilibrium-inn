"""Intervention-aware report (CLAUDE.md M-G §Reports).

Runs one canonical control session WITH a scripted observer intervention
(control welf -> manual -> insult a present cast member) and the SAME seed/plan
WITHOUT control as the autonomous counterfactual, then contrasts them: how many
manual overrides, by action, which targets, what the engine would have selected,
and the social incidents/reactions that followed — vs the autonomous baseline.

A simple report (no full comparative dashboard). Trace-only via inn.observe;
no dynamics are tuned. experiments/ is exempt from the inn import contract.

Run: python -m experiments.report_intervention
"""

from __future__ import annotations

from pathlib import Path

from inn import metrics as M
from inn import observe as O
from inn.chronicle import who
from inn.config import load_inn_config
from inn.intervention import ControlState
from inn.session import run_session

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0" / "reports"
CFG = load_inn_config(ROOT / "inn.yaml")
CAST = [c.id for c in CFG.cast]
INCIDENT_ACTIONS = tuple(CFG.g0["incident_def"]["actions"])

# A deterministic mid-day override: control welf, command halgrim to rest then
# insult them — both routed through the normal world path (probe + transducer).
SUBJECT = "welf"
SCRIPT = [
    {"t": 200, "subject": SUBJECT, "verb": "command", "target": "halgrim"},
    {"t": 205, "subject": SUBJECT, "verb": "insult", "target": "halgrim"},
]


def _run() -> tuple[list[dict], list[dict]]:
    auto_dir = OUT / "_intervention_auto"
    man_dir = OUT / "_intervention_manual"
    run_session(CFG, "control", auto_dir, seed=7)
    run_session(CFG, "control", man_dir, seed=7,
                control=ControlState(SUBJECT, "manual"), interventions=SCRIPT)
    return (M.load_records(man_dir / "trace.jsonl.gz"),
            M.load_records(auto_dir / "trace.jsonl.gz"))


def render(records_manual: list[dict], records_auto: list[dict]) -> list[str]:
    r = O.report_intervention(records_manual, records_auto, CAST, INCIDENT_ACTIONS)
    lines = ["# Controlled-subject intervention report", "",
             f"Subject under control: **{who(SUBJECT)}**  ", "",
             f"- manual overrides: **{r['n_overrides']}**"
             + (f" ({r['llm_assisted']} LLM-assisted)" if r['llm_assisted'] else ""),
             f"- by action: {r['by_action'] or '—'}",
             f"- targets: { {who(k): v for k, v in r['targets'].items()} or '—'}",
             f"- incidents after first override: {r['incidents_after']}",
             f"- incidents (manual run / autonomous run): "
             f"{r.get('incidents_manual', '?')} / {r.get('incidents_auto', '?')}",
             "",
             "## Each override (engine would have vs you chose)", "",
             "| time | you chose | target | engine would have | route |",
             "|---|---|---|---|---|"]
    for iv in r["overrides"]:
        lines.append(f"| day {iv['day']} {iv['clock']} | {iv['user_selected_action']} "
                     f"| {who(iv.get('target')) if iv.get('target') else '—'} "
                     f"| {iv['engine_would_have_selected']} | {iv['route']} |")
    lines += ["", "## Reactions attributed to the controlled subject afterward", ""]
    if not r["reactions_to_subject"]:
        lines.append("(none — the room did not react)")
    for x in r["reactions_to_subject"][:20]:
        lines.append(f"- {x['clock']} {who(x['actor'])} → {x['as']} toward "
                     f"{who(x['toward'])}")
    return lines


def main() -> None:
    man, auto = _run()
    lines = render(man, auto)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "intervention.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
