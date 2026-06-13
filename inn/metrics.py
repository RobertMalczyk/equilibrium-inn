"""Metric families (CLAUDE.md section 7). All analysis reads the society
trace, never live objects."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from inn.trace import read_trace


def load_records(path: str | Path) -> list[dict]:
    return list(read_trace(path))


# -- incidents and cascades --------------------------------------------------

@dataclass(frozen=True)
class Incident:
    event_id: str
    t: int
    day: int
    clock: str
    actor: str
    action: str
    provoked_by: str | None


def incidents(records: list[dict], incident_actions: tuple[str, ...]) -> list[Incident]:
    """Incident = a transduced (socially visible) hostile action.
    Selections that fired but transduced nothing are not incidents."""
    seen: set[str] = set()
    out: list[Incident] = []
    for rec in records:
        for tr in rec["transductions"]:
            if tr["action"] in incident_actions and tr["event_id"] not in seen:
                seen.add(tr["event_id"])
                out.append(Incident(tr["event_id"], rec["t"], rec["day"],
                                    rec["clock"], tr["actor"], tr["action"],
                                    tr["provoked_by"]))
    return out


def cascade_stats(incs: list[Incident]) -> dict:
    """Provenance-graph cascades: chains of provoked_by links."""
    by_id = {i.event_id: i for i in incs}
    children: dict[str, list[str]] = defaultdict(list)
    roots = []
    for i in incs:
        if i.provoked_by in by_id:
            children[i.provoked_by].append(i.event_id)
        else:
            roots.append(i.event_id)

    def walk(root: str) -> dict:
        """Iterative subtree walk (cascades can be thousands of hops deep)."""
        depth_of = {root: 1}
        t_max = by_id[root].t
        size = 0
        stack = [root]
        while stack:
            eid = stack.pop()
            size += 1
            t_max = max(t_max, by_id[eid].t)
            for k in children.get(eid, []):
                depth_of[k] = depth_of[eid] + 1
                stack.append(k)
        return {"root": root, "depth": max(depth_of.values()), "size": size,
                "duration_ticks": t_max - by_id[root].t}

    cascades = [walk(r) for r in roots]
    return {
        "n_incidents": len(incs),
        "n_cascades": len(cascades),
        "max_depth": max((c["depth"] for c in cascades), default=0),
        "max_size": max((c["size"] for c in cascades), default=0),
        "max_duration_ticks": max((c["duration_ticks"] for c in cascades), default=0),
        "cascades": cascades,
    }


# -- routine, variety, recovery ----------------------------------------------

def routine_adherence(records: list[dict]) -> dict[str, float]:
    """% of waking ticks engaged (BUSY) or calm-idle (IDLE/COOLDOWN with no
    reactive interruption). SEEKING without an answer and reactive actions
    count against routine."""
    ok: Counter = Counter()
    total: Counter = Counter()
    for rec in records:
        if rec["night"]:
            continue
        for pid, tt in rec["personas"].items():
            total[pid] += 1
            sel = tt["selection"]
            if tt["state_after_post"]["mode"] in ("BUSY", "SLEEP") or (
                    sel["kind"] in ("idle", "continue", "proactive")
                    and not sel["interrupted"]):
                ok[pid] += 1
    return {pid: ok[pid] / total[pid] for pid in total}


def action_entropy(records: list[dict]) -> dict[str, float]:
    """Shannon entropy (bits) of non-idle action choice per persona —
    the degeneracy detector."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for rec in records:
        for pid, tt in rec["personas"].items():
            a = tt["selection"]["action"]
            if a not in ("idle", "continue"):
                counts[pid][a] += 1
    out = {}
    for pid, c in counts.items():
        n = sum(c.values())
        out[pid] = -sum((k / n) * math.log2(k / n) for k in c.values()) if n else 0.0
    return out


def variety_under_repetition(records: list[dict]) -> dict:
    """Distribution of responses to the Nth identical stimulus (type+source)
    vs the 1st — the anti-arrow-in-the-knee metric."""
    seen: dict[tuple, int] = Counter()
    by_n: dict[int, Counter] = defaultdict(Counter)
    for rec in records:
        for pid, tt in rec["personas"].items():
            ev = tt["event"]
            if ev is None or ev["type"] not in ("insult", "command", "help"):
                continue
            key = (pid, ev["type"], ev["source"])
            seen[key] += 1
            by_n[min(seen[key], 5)][tt["selection"]["action"]] += 1
    return {n: dict(c) for n, c in sorted(by_n.items())}


def recovery_time(records: list[dict], incs: list[Incident],
                  state: str = "anger", threshold: float = 0.1) -> dict:
    """Ticks from each cascade root until every persona's `state` is back
    under threshold."""
    series: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        for pid, tt in rec["personas"].items():
            series[pid].append(tt["state_after_post"]["global"][state])
    out = {}
    roots = {i.event_id: i.t for i in incs if i.provoked_by is None}
    n_ticks = len(records)
    for eid, t0 in roots.items():
        rec_t = None
        for t in range(t0, n_ticks):
            if all(series[pid][t] < threshold for pid in series):
                rec_t = t - t0
                break
        out[eid] = rec_t  # None = never recovered within the run
    return out


def grudge_carryover(records: list[dict], day_ticks: int) -> dict:
    """Relation tensor at each dawn (offset 0 of each day): does day-2 morning
    measurably differ after a day-1 incident?"""
    dawns = {}
    for rec in records:
        if rec["t"] % day_ticks == 0:
            day = rec["day"]
            dawns[day] = {
                pid: tt["state_after_post"]["relations"]
                for pid, tt in rec["personas"].items()
            }
    return dawns


# -- G0 stability observables --------------------------------------------------

def envelopes(records: list[dict], states: tuple[str, ...] = ("anger", "stress",
              "frustration", "boredom")) -> dict:
    env: dict[str, dict[str, dict]] = defaultdict(dict)
    series = state_series(records, states)
    for pid, per_state in series.items():
        for st, xs in per_state.items():
            env[pid][st] = {"min": min(xs), "max": max(xs),
                            "mean": sum(xs) / len(xs)}
    return dict(env)


def clamp_dwell(records: list[dict], states: tuple[str, ...] = ("anger", "stress",
                "frustration", "boredom")) -> dict:
    """Fraction of ticks spent at the clamps (0.0 or 1.0) per persona/state."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    series = state_series(records, states)
    for pid, per_state in series.items():
        for st, xs in per_state.items():
            out[pid][st] = sum(1 for x in xs if x <= 0.0 or x >= 1.0) / len(xs)
    return dict(out)


def state_series(records: list[dict], states: tuple[str, ...]) -> dict:
    series: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        for pid, tt in rec["personas"].items():
            g = tt["state_after_post"]["global"]
            for st in states:
                series[pid][st].append(g[st])
    return {pid: dict(d) for pid, d in series.items()}


def fft_dominant(records: list[dict], dt: float,
                 states: tuple[str, ...] = ("anger", "stress", "frustration")) -> dict:
    """Dominant oscillation period (hours) and relative power per persona/state.
    Limit-cycle detector for G0."""
    import numpy as np

    out: dict[str, dict[str, dict]] = defaultdict(dict)
    series = state_series(records, states)
    for pid, per_state in series.items():
        for st, xs in per_state.items():
            x = np.asarray(xs) - np.mean(xs)
            if np.allclose(x, 0):
                out[pid][st] = {"period_h": None, "rel_power": 0.0}
                continue
            spec = np.abs(np.fft.rfft(x)) ** 2
            freqs = np.fft.rfftfreq(len(x), d=dt)
            k = int(np.argmax(spec[1:]) + 1)
            out[pid][st] = {
                "period_h": float(1 / freqs[k] / 3600) if freqs[k] > 0 else None,
                "rel_power": float(spec[k] / spec[1:].sum()),
            }
    return dict(out)
