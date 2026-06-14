"""QA-corpus harvest (CLAUDE.md section 8): export G0's NPC-sourced social
exchanges as engine-format scenario YAMLs — the missing "Wojslaw-commands-X"
corpus.

Each harvested scenario captures the reactor persona, the inbound provoking
event, AND the reactor's pre-tick context (global_state + relations toward the
source), so re-running it reproduces the action the NPC actually took in the live
inn run. Reproduction is VERIFIED here (under the inn's shipped persona loader),
and only verified scenarios are written — the corpus is a deterministic
regression set, not a pile of lone events.

Determinism note: the actions were observed under the inn's engine_overrides
(vent/cooldown/reactive_window, burst overlay OFF), so the YAML header records
the loader context; an engine-default run may differ. Run:
    python -m experiments.harvest
"""

from __future__ import annotations

from pathlib import Path

import yaml

from inn.config import load_inn_config
from inn.engine_surface import init_runtime, tick, RawEvent
from inn.loop import make_persona_loader
from inn.session import run_session
import inn.metrics as M

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0" / "harvest"

# Reactive SOCIAL actions worth a QA corpus (the same-event-different-action
# claim): negative reactions to provocations + the positive answers.
HARVEST_ACTIONS = ("outburst", "cold_response", "complain", "refuse",
                   "cooperate", "positive_response")
NON_PERSONA_SOURCES = ("marta", "player", "world")


NEGATIVE_ACTIONS = ("outburst", "cold_response", "complain", "refuse")


def _candidates(records: list[dict], cast_ids: set[str]) -> list[dict]:
    """One candidate per (persona, action, source, inbound type) — the distinct
    in-context exchanges, deduped so the corpus is diverse, not repetitive.

    Ordered so the QA-valuable cases come first: NPC-to-NPC (source is a cast
    member, the genuine social emergence) before reactions to the probe source
    (marta), and negative reactions before the positive answers. With a small
    cap this surfaces the 'Wojslaw-commands-X' corpus instead of a pile of
    identical meal acknowledgements."""
    seen: set[tuple] = set()
    out = []
    for rec in records:
        for pid, p in rec["personas"].items():
            sel = p.get("selection")
            ev = p.get("event")
            if not (isinstance(sel, dict) and ev):
                continue
            action, src = sel.get("action"), ev.get("source")
            if action not in HARVEST_ACTIONS or not src or src == pid:
                continue
            key = (pid, action, src, ev.get("type"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"t": rec["t"], "persona": pid, "action": action,
                        "event": ev, "snapshot": p["snapshot"]})
    # priority: NPC-to-NPC first, then negative-before-positive, then by tick
    out.sort(key=lambda c: (c["event"]["source"] not in cast_ids,
                            c["action"] not in NEGATIVE_ACTIONS,
                            c["t"]))
    return out


def _scenario(cand: dict, idx: int) -> dict:
    snap = cand["snapshot"]
    ev = cand["event"]
    rels = {src: {d: round(v, 6) for d, v in dims.items()}
            for src, dims in snap.get("relations", {}).items()}
    gstate = {k: round(v, 6) for k, v in snap.get("global", {}).items() if v}
    return {
        "id": f"inn_harvest_{idx:02d}_{cand['persona']}_{cand['action']}_to_{ev['source']}",
        "persona": cand["persona"],
        "initial_overrides": {"global_state": gstate, "relations": rels},
        "events": [{
            "type": ev["type"], "t": 0, "source": ev["source"],
            "intensity": round(ev.get("intensity", 0.0), 6),
            "context": dict(ev.get("context", {})),
        }],
        # annotation (not engine input): what the inn observed, for QA assertion
        "expect_action": cand["action"],
    }


def _reproduces(cfg, scenario: dict, loader) -> bool:
    """Re-run the scenario under the inn's shipped loader and check the persona
    selects the recorded action — the QA property that makes it corpus-worthy."""
    rt = init_runtime(loader(scenario["persona"]),
                      scenario["initial_overrides"])
    ev = scenario["events"][0]
    raw = RawEvent(type=ev["type"], t=0, source=ev["source"],
                   intensity=ev["intensity"], context=ev["context"])
    trace = tick(rt, 0, raw)
    return trace.selection.action == scenario["expect_action"]


def harvest(max_scenarios: int = 12, validate: bool = True) -> list[Path]:
    cfg = load_inn_config(ROOT / "inn.yaml")
    # canonical shipped session (deterministic): the impulse protocol on the
    # default profile is where the NPC-sourced exchanges live.
    import tempfile
    td = Path(tempfile.mkdtemp())
    run_session(cfg, "impulse", td)
    records = M.load_records(td / "trace.jsonl.gz")

    loader = make_persona_loader(
        cfg.resolved_engine_overrides(cfg.default_profile), burst=cfg.burst_overlay)

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.yaml"):  # rebuild cleanly each run
        stale.unlink()

    cast_ids = {c.id for c in cfg.cast}
    written, kept, n_cand, n_failed = [], 0, 0, 0
    for cand in _candidates(records, cast_ids):
        n_cand += 1
        if kept >= max_scenarios:
            break
        scn = _scenario(cand, kept + 1)
        if validate and not _reproduces(cfg, scn, loader):
            n_failed += 1
            continue
        header = (f"# Harvested from the canonical inn impulse run (CLAUDE.md S8 "
                  f"QA corpus).\n# {scn['persona']} answered a {cand['event']['type']} "
                  f"from {cand['event']['source']} with {cand['action']}, in the "
                  f"relation context below.\n# Observed under the inn's shipped "
                  f"loader (semantic profile, burst overlay OFF); engine-default "
                  f"calibration may differ.\n")
        p = OUT / f"{scn['id']}.yaml"
        p.write_text(header + yaml.safe_dump(scn, sort_keys=False), encoding="utf-8")
        written.append(p)
        kept += 1

    manifest = {
        "source": "canonical inn impulse run (default profile)",
        "engine_commit": cfg.engine_commit,
        "validated": validate,
        "candidates_seen": n_cand,
        "scenarios_written": kept,
        "rejected_no_repro": n_failed,
        "scenarios": [p.name for p in written],
    }
    (OUT / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return written


if __name__ == "__main__":
    paths = harvest()
    print(f"wrote {len(paths)} verified scenario(s) to {OUT}")
    for p in paths:
        print(f"  {p.name}")
