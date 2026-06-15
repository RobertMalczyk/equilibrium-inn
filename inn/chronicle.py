"""Deterministic rendering of society-trace records into observable prose.

The single source of the chronicle vocabulary for both the batch chronicle
(experiments/chronicle.py) and the interactive CLI (inn/cli.py). NEVER an LLM
(CLAUDE.md section 6): every line is a table lookup over the engine's de-biased
narration vocabulary, re-exported through the engine seam.

Two views over the same trace records:
  * event_line(rec)        -> one observable beat for a tick (or None if quiet)
  * why_chain(records, who)-> the provenance walk behind a persona's last act
                              (the text form of the CLI's `why <name>`).
"""

from __future__ import annotations

from inn.engine_surface import DISPLAY, REACTIVE_TIERS, WHO


def who(name: str | None) -> str:
    if not name:
        return "someone"
    return WHO.get(name, DISPLAY.get(name, name.capitalize()))


def reaction_phrase(action: str, score: float) -> str:
    """Tiered observable phrase for a reactive action at a given selection score
    (higher score -> stronger phrasing). Falls back to the bare action id."""
    tiers = REACTIVE_TIERS.get(action)
    if not tiers:
        return action
    phrase = tiers[0][1]
    for thr, ph in tiers:
        if score >= thr:
            phrase = ph
    return phrase


def _probe_beat(pid: str) -> str | None:
    """An external act (probe / player verb), reconstructed from its id
    `{t}:{source}:{type}:probe`."""
    parts = pid.split(":")
    if len(parts) < 3:
        return None
    src, etype = parts[1], parts[2]
    if etype == "insult":
        return f"{who(src)} makes a scene — a public insult cuts across the room"
    if etype == "command":
        return f"{who(src)} gives an order"
    if etype == "help":
        return f"{who(src)} lends a hand"
    if etype == "food_given":
        return f"{who(src)} serves food"
    if etype == "weather":
        return "rain sets in; the yard empties and the common room fills"
    return None


def event_line(rec: dict) -> str | None:
    """One observable beat for tick `rec`, or None if nothing notable happened.
    Built from external acts (probes/player verbs) + the transduction log (the
    social acts everyone in the room can see), target-role lines only."""
    parts: list[str] = []
    for p in rec.get("probes", []):
        beat = _probe_beat(p["probe"])
        if beat:
            parts.append(beat)
    for tr in rec.get("transductions", []):
        if tr["role"] != "target":
            continue
        actor, target = who(tr["actor"]), who(tr["target_inferred"])
        phrase = reaction_phrase(tr["action"], tr["score"])
        if tr["target_inferred"] and tr["target_inferred"] != tr["actor"]:
            parts.append(f"{actor} {phrase} at {target}")
        else:
            parts.append(f"{actor} {phrase}")
    if not parts:
        return None
    line = "; ".join(parts)
    # M-G: mark a beat the observer caused via a controlled subject, so the
    # chronicle never makes an intervention look like autonomous behaviour.
    iv = rec.get("intervention")
    if iv and iv.get("selected_by") == "manual_override":
        line = f"(your intervention) {line}"
    return line


def _link_text(event_id: str, records_by_id: dict) -> str | None:
    tr = records_by_id.get(event_id)
    if tr is None:
        return None
    tgt = tr["target_inferred"]
    at = f" at {who(tgt)}" if tgt and tgt != tr["actor"] else " (unprovoked)"
    return f"{who(tr['actor'])}'s {tr['action']}{at} ({tr['clock']})"


def why_chain(records: list[dict], name: str, action_filter=("outburst",)) -> list[str]:
    """Provenance chain behind `name`'s most recent notable act — each step
    walks `provoked_by` back toward the root probe. The CLI's `why <name>`."""
    by_id: dict[str, dict] = {}
    for rec in records:
        for tr in rec.get("transductions", []):
            by_id[tr["event_id"]] = {**tr, "clock": rec["clock"], "day": rec["day"]}
    # most recent act by this persona (prefer the filtered actions, else any)
    acts = [tr for tr in by_id.values() if tr["actor"] == name]
    notable = [tr for tr in acts if tr["action"] in action_filter] or acts
    if not notable:
        return [f"{who(name)} has done nothing worth tracing."]
    inc = notable[-1]
    chain = [f"{who(inc['actor'])} {inc['action']} "
             f"({inc['clock']}, day {inc['day']})"]
    cur = inc["provoked_by"]
    guard = 0
    while cur is not None and guard < 50:
        guard += 1
        if cur.endswith(":probe"):
            parts = cur.split(":")
            chain.append(f"← {who(parts[1])}'s {parts[2]} (external)")
            break
        link = _link_text(cur, by_id)
        if link is None:
            break
        chain.append(f"← {link}")
        cur = by_id[cur]["provoked_by"]
    return chain
