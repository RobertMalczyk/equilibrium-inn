"""Observation layer (CLAUDE.md M-D): derive readable behavioural facts from the
society trace, never from live engine objects (hard rule 0.4). The single source
of derivations for the CLI Observation Mode, the validation reports, and the
Living Inn Observatory — none of them re-derive.

This module is pure analysis over trace records (the gzipped-JSONL dicts produced
by ``inn.loop.InnLoop`` / read by ``inn.metrics.load_records``). It adds NO
dynamics and reads NO behaviour-shaping numbers: the only constants here are
display thresholds (mood/label cut points), which live in inn.yaml's
``observation`` block and are passed in as ``cfg.observation`` — never consulted
by the simulation loop, so the golden trace is unaffected.

What the engine already records, that we surface:
  * mode lifecycle      personas[pid].state_after_post.mode  (IDLE/SEEKING/BUSY/
                        COOLDOWN/SLEEP) — the boredom->seeking->busy->rest->sleep
                        cycle is literally a mode walk.
  * need/affect states  personas[pid].state_after_post.global[...] (GLOBAL_STATES)
  * drivers             selection.action + the state that crossed (boredom for
                        seek_stimulus, fatigue for rest, sleep_pressure for sleep,
                        anger for outburst) + selection.explanation
  * supply/contention   record offers / contention_losers
  * provenance          transductions[*].provoked_by (via inn.chronicle.why_chain)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

import inn.metrics as M
from inn.chronicle import event_line, observer_action_label, who, why_chain
from inn.intervention import ACTION_PALETTE

# -- display thresholds (inn.yaml `observation`; defaults if absent) -----------
# Pure annotation knobs: which value counts as "high" for a need/affect channel,
# used for mood labels and threshold-crossing markers. NOT read by the loop.
DEFAULT_HIGH = {
    "boredom": 0.60,
    "fatigue": 0.70,
    "hunger": 0.70,
    "stress": 0.60,
    "frustration": 0.60,
    "anger": 0.50,
    "sleep_pressure": 0.70,
}
# Channels grouped by family for colour-coding in the UI / report ordering.
NEED_STATES = ("boredom", "fatigue", "hunger")
AFFECT_STATES = ("stress", "frustration", "anger")
SLEEP_STATES = ("sleep_pressure",)
CARD_STATES = NEED_STATES + AFFECT_STATES + SLEEP_STATES

MODE_LABEL = {
    "IDLE": "idle", "SEEKING": "seeking", "BUSY": "busy",
    "COOLDOWN": "cooldown", "SLEEP": "sleep",
}

# Observer-facing phrasing for a mode label. Engine mode IDLE means "awake and
# unoccupied" — NOT rest/recovery — so the observer view avoids the bare word
# "idle" (Developer view keeps the raw mode id). MODE_LABEL values double as the
# Observatory's colour keys, so they stay unchanged; this map is display-only.
OBSERVER_MODE = {"idle": "unoccupied"}


def observer_mode(label: str) -> str:
    """The observer-facing word for a MODE_LABEL value (idle -> unoccupied)."""
    return OBSERVER_MODE.get(label, label)


def high_thresholds(cfg=None) -> dict[str, float]:
    """Display 'high' thresholds, inn.yaml `observation.high` overriding defaults."""
    out = dict(DEFAULT_HIGH)
    obs = getattr(cfg, "observation", None) if cfg is not None else None
    if obs:
        out.update({k: float(v) for k, v in (obs.get("high") or {}).items()})
    return out


# -- per-tick accessors --------------------------------------------------------

def mode_of(rec: dict, pid: str) -> str:
    return rec["personas"][pid]["state_after_post"]["mode"]


def state_of(rec: dict, pid: str, name: str) -> float:
    return rec["personas"][pid]["state_after_post"]["global"][name]


def action_of(rec: dict, pid: str) -> str:
    return rec["personas"][pid]["selection"]["action"]


def mood_label(rec: dict, pid: str, high: dict[str, float]) -> str:
    """A readable mood from mode + affect/need state (Observer View). Priority
    favours the most salient signal: sleep/rest posture, then heat, then drain."""
    mode = mode_of(rec, pid)
    if mode == "SLEEP":
        return "sleeping"
    g = rec["personas"][pid]["state_after_post"]["global"]
    if mode == "BUSY" and action_of(rec, pid) == "rest":
        return "resting"
    if g["anger"] >= high["anger"] or g["stress"] >= high["stress"]:
        return "irritated"
    if g["fatigue"] >= high["fatigue"]:
        return "tired"
    if mode == "BUSY":
        return "focused"
    if g["boredom"] >= high["boredom"]:
        return "bored"
    return "calm"


def driver_of(rec: dict, pid: str) -> tuple[str, float] | None:
    """The need/affect channel that best explains this tick's action — the
    'why' behind a proactive or reactive choice. None for idle/neutral."""
    tt = rec["personas"][pid]
    g = tt["state_after_post"]["global"]
    a = tt["selection"]["action"]
    if a == "seek_stimulus":
        return ("boredom", g["boredom"])
    if a == "rest":
        return ("fatigue", g["fatigue"])
    if a == "sleep":
        return ("sleep_pressure", g["sleep_pressure"])
    if a == "outburst":
        return ("anger", g["anger"])
    if a in ("self_activity", "external"):
        return ("engagement", 1.0)
    if a in ("cooperate", "positive_response"):
        return ("warmth", g.get("satisfaction", 0.0))
    if a in ("complain", "cold_response", "refuse"):
        return ("frustration", g["frustration"])
    if a == "command_other":
        return ("duty", g.get("duty", 0.0))
    return None


# -- mode transitions ----------------------------------------------------------

@dataclass(frozen=True)
class Transition:
    pid: str
    t: int
    day: int
    clock: str
    prev: str
    new: str
    action: str
    driver: str | None
    driver_value: float | None


def mode_transitions(records: list[dict], pid: str | None = None) -> list[Transition]:
    """Every mode change per persona (CLAUDE.md M-D §2): IDLE->SEEKING->BUSY->
    REST(BUSY/rest)->SLEEP etc., with the action and likely driver at the edge."""
    pids = [pid] if pid else list(records[0]["personas"]) if records else []
    prev: dict[str, str] = {}
    out: list[Transition] = []
    for rec in records:
        for p in pids:
            cur = mode_of(rec, p)
            was = prev.get(p)
            if was is not None and cur != was:
                drv = driver_of(rec, p)
                out.append(Transition(
                    pid=p, t=rec["t"], day=rec["day"], clock=rec["clock"],
                    prev=was, new=cur, action=action_of(rec, p),
                    driver=drv[0] if drv else None,
                    driver_value=round(drv[1], 4) if drv else None))
            prev[p] = cur
    return out


# -- threshold crossings -------------------------------------------------------

@dataclass(frozen=True)
class Crossing:
    pid: str
    t: int
    day: int
    clock: str
    state: str
    value: float
    threshold: float


def threshold_crossings(records: list[dict], high: dict[str, float],
                        pid: str | None = None) -> list[Crossing]:
    """Rising edges where a need/affect channel first exceeds its 'high' mark
    (annotation only — no behaviour changes)."""
    pids = [pid] if pid else list(records[0]["personas"]) if records else []
    over: dict[tuple[str, str], bool] = {}
    out: list[Crossing] = []
    for rec in records:
        for p in pids:
            g = rec["personas"][p]["state_after_post"]["global"]
            for st, thr in high.items():
                v = g.get(st)
                if v is None:
                    continue
                key = (p, st)
                now = v >= thr
                if now and not over.get(key, False):
                    out.append(Crossing(p, rec["t"], rec["day"], rec["clock"],
                                        st, round(v, 4), thr))
                over[key] = now
    return out


# -- ambient summaries ---------------------------------------------------------

def _hours(n_ticks: int, dt: float) -> str:
    h = n_ticks * dt / 3600.0
    if h >= 0.75:
        n = round(h)
        return f"{n} quiet hour{'s' if n != 1 else ''} pass" + ("" if n != 1 else "es")
    n = round(n_ticks * dt / 60.0)
    return f"{n} quiet minutes pass"


def _span_clause(records: list[dict], pid: str, high: dict[str, float]) -> str | None:
    """One deterministic clause for what `pid` did across a span of records:
    the dominant occupation, plus the most notable threshold crossing."""
    modes = Counter()
    last_activity = None
    crossed = None
    for rec in records:
        modes[mode_of(rec, pid)] += 1
        for o in rec.get("offers", []):
            if o["pid"] == pid:
                last_activity = o["activity"]
        g = rec["personas"][pid]["state_after_post"]["global"]
        for st in ("boredom", "fatigue", "frustration"):
            if crossed is None and g.get(st, 0.0) >= high[st]:
                crossed = st
    if not modes:
        return None
    dom = modes.most_common(1)[0][0]
    name = who(pid)
    act = last_activity.replace("_", " ") if last_activity else None
    if dom == "SLEEP":
        clause = f"{name} sleeps"
    elif dom == "BUSY" and act:
        clause = f"{name} is busy with {act}"
    elif dom == "BUSY":
        clause = f"{name} keeps busy"
    elif dom == "SEEKING":
        clause = (f"{name} seeks something to do"
                  + (f", then takes up {act}" if act else ""))
    else:  # IDLE / COOLDOWN
        clause = f"{name} is unoccupied"
    if crossed and dom not in ("SLEEP",):
        clause += f" ({crossed} rising)"
    return clause


def ambient_summary(records: list[dict], high: dict[str, float],
                    cast: list[str] | None = None, dt: float = 120.0) -> str:
    """Deterministic prose for a span of quiet ticks (CLAUDE.md M-D §1): replaces
    the opaque '(N quiet ticks pass.)' with who idled / sought / worked / rested /
    slept. Never an LLM. Pure read — does not mutate records."""
    if not records:
        return ""
    cast = cast or list(records[0]["personas"])
    head = _hours(len(records), dt).capitalize()
    clauses = [c for c in (_span_clause(records, p, high) for p in cast) if c]
    if not clauses:
        return f"{head}."
    return f"{head}. " + "; ".join(clauses) + "."


# -- per-persona daily summaries ----------------------------------------------

@dataclass(frozen=True)
class DaySummary:
    pid: str
    day: int
    pct: dict          # mode label -> fraction of the day's ticks
    top_activities: list
    max_boredom: float
    max_fatigue: float
    max_frustration: float
    offers_ok: int
    offers_contended: int
    incidents_caused: int
    incidents_received: int
    interpretation: str

    def to_dict(self) -> dict:
        return asdict(self)


def _interpret(pct: dict, max_fatigue: float, contended: int) -> str:
    busy = pct.get("busy", 0.0)
    sleep = pct.get("sleep", 0.0)
    if busy >= 0.2 and sleep >= 0.15 and max_fatigue >= 0.4:
        base = "plausible work-rest cycle"
    elif busy < 0.05:
        base = "little engagement — mostly idle/seeking"
    elif sleep < 0.10:
        base = "thin sleep recovery"
    else:
        base = "active day"
    if contended >= 3:
        base += "; notable activity contention"
    return base


def daily_summary(records: list[dict], pid: str, day: int,
                  incident_actions: tuple[str, ...]) -> DaySummary:
    day_recs = [r for r in records if r["day"] == day]
    n = len(day_recs)
    modes = Counter(mode_of(r, pid) for r in day_recs)
    pct = {MODE_LABEL[m]: round(c / n, 4) for m, c in modes.items()} if n else {}
    acts = Counter(o["activity"] for r in day_recs for o in r.get("offers", [])
                   if o["pid"] == pid)
    maxg = {st: max((state_of(r, pid, st) for r in day_recs), default=0.0)
            for st in ("boredom", "fatigue", "frustration")}
    offers_ok = sum(1 for r in day_recs for o in r.get("offers", []) if o["pid"] == pid)
    contended = sum(1 for r in day_recs if pid in r.get("contention_losers", []))
    incs = M.incidents(day_recs, incident_actions)
    caused = sum(1 for i in incs if i.actor == pid)
    received = 0
    for r in day_recs:
        for tr in r["transductions"]:
            if (tr["action"] in incident_actions and tr["role"] == "target"
                    and tr["target_inferred"] == pid):
                received += 1
    return DaySummary(
        pid=pid, day=day, pct=pct,
        top_activities=[a for a, _ in acts.most_common(3)],
        max_boredom=round(maxg["boredom"], 4),
        max_fatigue=round(maxg["fatigue"], 4),
        max_frustration=round(maxg["frustration"], 4),
        offers_ok=offers_ok, offers_contended=contended,
        incidents_caused=caused, incidents_received=received,
        interpretation=_interpret(pct, maxg["fatigue"], contended))


# -- generalized causality (why) ----------------------------------------------

def why(records: list[dict], pid: str) -> list[str]:
    """Causal account of `pid`'s most recent notable act — works for NORMAL
    behaviour, not just outbursts (CLAUDE.md M-D §6). For a reactive act, walk
    the provenance chain (inn.chronicle.why_chain). For a proactive act
    (seek/rest/sleep/activity), explain from the driver that crossed."""
    last = None
    for rec in records:
        a = action_of(rec, pid)
        if a not in ("neutral", "continue", "idle"):
            last = rec
    # M-G: a manual override is the observer's act, not the engine's. If the
    # subject's most recent notable moment was an override, attribute it to the
    # observer and contrast it with what the engine would have selected.
    last_override = None
    for rec in records:
        iv = rec.get("intervention")
        if iv and iv.get("subject") == pid and iv.get("selected_by") == "manual_override":
            last_override = rec
    if last_override is not None and (last is None or last_override["t"] >= last["t"]):
        iv = last_override["intervention"]
        tgt = iv.get("target")
        at = f" at {who(tgt)}" if tgt else ""
        lines = [f"{who(pid)} — MANUAL OVERRIDE by the observer "
                 f"({last_override['clock']}, day {last_override['day']}).",
                 f"  you chose: {observer_action_label(iv['user_selected_action'])}{at}",
                 f"  the engine would have selected: "
                 f"{iv['engine_would_have_selected']}."]
        if iv.get("llm"):
            lines.append(f"  (from free text: \"{iv['llm'].get('original_text', '')}\")")
        return lines
    if last is None:
        return [f"{who(pid)} has done nothing worth tracing yet."]
    a = action_of(last, pid)
    # reactive / socially-visible acts have a provenance chain
    if a in ("outburst", "cooperate", "positive_response", "refuse",
             "complain", "cold_response"):
        chain = why_chain(records, pid, action_filter=(a,))
        if chain and "nothing worth tracing" not in chain[0]:
            return chain
    # proactive: explain from the crossing driver
    drv = driver_of(last, pid)
    expl = last["personas"][pid]["selection"].get("explanation")
    head = f"{who(pid)} chose to {a.replace('_', ' ')} ({last['clock']}, day {last['day']})."
    lines = [head]
    if drv:
        st, val = drv
        lines.append(f"← {st} was {round(val, 3)} when the drive crossed threshold.")
    if expl:
        lines.append(f"  ({expl})")
    return lines


# -- intervention report (M-G) ------------------------------------------------

def interventions_in(records: list[dict]) -> list[dict]:
    """The observer's manual overrides in a trace (subject, action, target,
    engine_would_have_selected), oldest first."""
    out = []
    for rec in records:
        iv = rec.get("intervention")
        if iv and iv.get("selected_by") == "manual_override":
            out.append({"t": rec["t"], "clock": rec["clock"], "day": rec["day"],
                        **iv})
    return out


def report_intervention(records_manual: list[dict],
                        records_auto: list[dict] | None,
                        cast: list[str],
                        incident_actions: tuple[str, ...]) -> dict:
    """Intervention-aware summary (CLAUDE.md M-G §Reports): how many manual
    overrides, by action, which targets, the incidents/reactions that followed,
    and (if an autonomous counterfactual is supplied) the incident-count delta.
    Pure read over the trace — never re-runs the sim."""
    ivs = interventions_in(records_manual)
    by_action = Counter(iv["user_selected_action"] for iv in ivs)
    targets = Counter(iv["target"] for iv in ivs if iv.get("target"))

    # reactions attributed to a controlled subject AFTER an override (the social
    # consequence): target-role transductions whose target_inferred is a subject
    # the observer drove, occurring at/after that subject's first override.
    subjects = {iv["subject"] for iv in ivs}
    first_override_t = min((iv["t"] for iv in ivs), default=None)
    incs = M.incidents(records_manual, incident_actions)
    incidents_after = [i for i in incs
                       if first_override_t is not None and i.t >= first_override_t]
    reactions_to_subject = []
    for rec in records_manual:
        if first_override_t is None or rec["t"] < first_override_t:
            continue
        for tr in rec.get("transductions", []):
            if tr["role"] == "target" and tr.get("target_inferred") in subjects \
                    and tr["actor"] not in subjects:
                reactions_to_subject.append(
                    {"t": rec["t"], "clock": rec["clock"], "actor": tr["actor"],
                     "as": tr["as"], "toward": tr["target_inferred"]})

    out = {
        "n_overrides": len(ivs),
        "by_action": dict(by_action),
        "targets": dict(targets),
        "subjects": sorted(subjects),
        "overrides": ivs,
        "incidents_after": len(incidents_after),
        "reactions_to_subject": reactions_to_subject,
        "llm_assisted": sum(1 for iv in ivs if iv.get("llm")),
    }
    if records_auto is not None:
        out["incidents_auto"] = len(M.incidents(records_auto, incident_actions))
        out["incidents_manual"] = len(incs)
    return out


def intervention_ui_model(records: list[dict], cfg, interventions: list[dict],
                          incident_actions: tuple[str, ...]) -> dict:
    """The Observatory's intervention descriptor (M-I): the finite action palette
    (valid_actions), whether the optional LLM seam is enabled, the controlled
    subject(s) seen in this run, and a concise intervention summary. Read-only —
    the UI consumes this rather than recomputing engine behaviour or duplicating
    the palette. `llm_enabled` reflects the environment of whoever built the model
    (False in the browser/Pyodide cockpit, where no provider is configured)."""
    from inn import llm_seam  # local import: optional seam, no engine deps
    palette = [{"verb": v, "label": v.replace("_", " "),
                "needs_target": e.needs_target, "route": e.route}
               for v, e in ACTION_PALETTE.items()]
    subjects = sorted({iv["subject"] for iv in interventions})
    summary = None
    if interventions:
        r = report_intervention(records, None, [c.id for c in cfg.cast],
                                incident_actions)
        summary = {"n_overrides": r["n_overrides"], "by_action": r["by_action"],
                   "targets": r["targets"], "incidents_after": r["incidents_after"],
                   "llm_assisted": r["llm_assisted"]}
    return {"palette": palette, "llm_enabled": llm_seam.enabled(),
            "controlled_subjects": subjects, "summary": summary}


# -- aggregate metrics (UI dashboard) -----------------------------------------

def time_budget(records: list[dict], pid: str) -> dict:
    n = len(records)
    modes = Counter(mode_of(r, pid) for r in records)
    return {MODE_LABEL[m]: round(c / n, 4) for m, c in modes.items()} if n else {}


def aggregate_metrics(records: list[dict], cfg) -> dict:
    """The validation dashboard: time budgets, max needs, activity success,
    contention/starvation, incidents, recovery — all from the trace."""
    inc_actions = tuple(cfg.g0["incident_def"]["actions"])
    cast = [c.id for c in cfg.cast]
    incs = M.incidents(records, inc_actions)
    casc = M.cascade_stats(incs)
    rec_time = M.recovery_time(records, incs)
    rec_vals = [v for v in rec_time.values() if v is not None]
    envel = M.envelopes(records, ("boredom", "fatigue", "frustration"))
    total_offers = sum(len(r.get("offers", [])) for r in records)
    total_contended = sum(len(r.get("contention_losers", [])) for r in records)
    denom = total_offers + total_contended
    return {
        "time_budget": {p: time_budget(records, p) for p in cast},
        "max_needs": {p: {st: round(envel.get(p, {}).get(st, {}).get("max", 0.0), 4)
                          for st in ("boredom", "fatigue", "frustration")}
                      for p in cast},
        "activity_success_rate": round(total_offers / denom, 4) if denom else None,
        "offers_total": total_offers,
        "contention_total": total_contended,
        "incidents": len(incs),
        "cascade_max_depth": casc["max_depth"],
        "recovery_ticks_mean": round(sum(rec_vals) / len(rec_vals), 2) if rec_vals else None,
    }


# -- validation reports (CLAUDE.md M-D §4) ------------------------------------
# Each returns structured data answering one validation question, built from the
# trace alone. The experiments/report_*.py scripts render these to Markdown; the
# CLI and Observatory reuse the same builders. No dynamics, no tuning.

def _mode_spans(records: list[dict], pid: str):
    """Yield (mode, [records]) contiguous runs of one mode for a persona."""
    cur, bucket = None, []
    for rec in records:
        m = mode_of(rec, pid)
        if m != cur and bucket:
            yield cur, bucket
            bucket = []
        cur = m
        bucket.append(rec)
    if bucket:
        yield cur, bucket


def report_boredom_activity(records: list[dict], cast: list[str]) -> dict:
    """Does boredom drive seeking, and does seeking find activity? Counts
    IDLE->SEEKING edges and their boredom level, plus SEEKING->BUSY (answered)
    vs SEEKING->IDLE/COOLDOWN (timed out)."""
    per = {}
    for pid in cast:
        trs = mode_transitions(records, pid)
        seeks = [t for t in trs if t.new == "SEEKING"]
        answered = sum(1 for t in trs if t.prev == "SEEKING" and t.new == "BUSY")
        timed_out = sum(1 for t in trs if t.prev == "SEEKING"
                        and t.new in ("IDLE", "COOLDOWN"))
        bores = [t.driver_value for t in seeks if t.driver == "boredom"
                 and t.driver_value is not None]
        per[pid] = {
            "seek_starts": len(seeks),
            "mean_boredom_at_seek": round(sum(bores) / len(bores), 4) if bores else None,
            "answered_with_activity": answered,
            "timed_out": timed_out,
        }
    total_seeks = sum(p["seek_starts"] for p in per.values())
    verdict = ("boredom drives seeking and most seeks find activity"
               if total_seeks and sum(p["answered_with_activity"]
                                      for p in per.values()) >= total_seeks * 0.4
               else "weak boredom->activity coupling")
    return {"question": "boredom -> seeking -> activity", "per_persona": per,
            "verdict": verdict}


def _mean_delta(records: list[dict], pid: str, state: str, when) -> float | None:
    deltas = []
    for a, b in zip(records, records[1:]):
        if when(a, pid):
            deltas.append(state_of(b, pid, state) - state_of(a, pid, state))
    return round(sum(deltas) / len(deltas), 6) if deltas else None


def report_activity_fatigue(records: list[dict], cast: list[str]) -> dict:
    """Does activity/busy raise fatigue (vs idle)? Mean per-tick fatigue delta
    while engaged on an activity vs while idle."""
    per = {}
    busy = lambda r, p: action_of(r, p) in ("self_activity", "external")
    idle = lambda r, p: mode_of(r, p) == "IDLE"
    for pid in cast:
        per[pid] = {
            "fatigue_delta_busy": _mean_delta(records, pid, "fatigue", busy),
            "fatigue_delta_idle": _mean_delta(records, pid, "fatigue", idle),
        }
    ups = [p["fatigue_delta_busy"] for p in per.values()
           if p["fatigue_delta_busy"] is not None]
    verdict = ("activity raises fatigue" if ups and sum(ups) / len(ups) > 0
               else "no clear activity->fatigue rise")
    return {"question": "activity/busy -> fatigue", "per_persona": per,
            "verdict": verdict}


def report_rest_sleep_recovery(records: list[dict], cast: list[str]) -> dict:
    """Do rest and sleep reduce fast states? Mean per-tick delta while resting
    (action==rest) and the dusk->dawn change across each night."""
    per = {}
    resting = lambda r, p: action_of(r, p) == "rest"
    days = sorted({r["day"] for r in records})
    for pid in cast:
        night_drops = {st: [] for st in ("fatigue", "stress", "anger")}
        for d in days[:-1]:
            dusk = [r for r in records if r["day"] == d and not r["night"]]
            dawn = [r for r in records if r["day"] == d + 1 and not r["night"]]
            if dusk and dawn:
                for st in night_drops:
                    night_drops[st].append(
                        state_of(dawn[0], pid, st) - state_of(dusk[-1], pid, st))
        per[pid] = {
            "fatigue_delta_resting": _mean_delta(records, pid, "fatigue", resting),
            "night_recovery": {st: (round(sum(v) / len(v), 4) if v else None)
                               for st, v in night_drops.items()},
        }
    rests = [p["fatigue_delta_resting"] for p in per.values()
             if p["fatigue_delta_resting"] is not None]
    verdict = ("rest and night reduce fast states"
               if rests and sum(rests) / len(rests) < 0
               else "rest->recovery not evident in this run")
    return {"question": "rest/sleep -> recovery", "per_persona": per,
            "verdict": verdict}


# -- full observation model (Observatory) -------------------------------------

def build_model(records: list[dict], cfg, meta: dict | None = None,
                stride: int = 1) -> dict:
    """Assemble the ObservationModel the Living Inn Observatory renders. JSON-
    serialisable; identical whether built in CPython or in-browser (Pyodide).
    `stride` downsamples the per-tick timeline (1 = full fidelity)."""
    high = high_thresholds(cfg)
    cast = [c.id for c in cfg.cast]
    inc_actions = tuple(cfg.g0["incident_def"]["actions"])
    days = sorted({r["day"] for r in records})

    ticks = []
    for rec in records[::stride]:
        people = {}
        for p in cast:
            tt = rec["personas"][p]
            g = tt["state_after_post"]["global"]
            people[p] = {
                "mode": MODE_LABEL[mode_of(rec, p)],
                "mood": mood_label(rec, p, high),
                "room": rec["presence"].get(p),
                "action": action_of(rec, p),
                "states": {st: round(g[st], 6) for st in CARD_STATES if st in g},
                "raw": {k: round(v, 6) for k, v in g.items()},  # Developer View
            }
        beat = event_line(rec)
        ticks.append({
            "t": rec["t"], "day": rec["day"], "clock": rec["clock"],
            "night": rec["night"], "rain": rec.get("rain", False),
            "personas": people,
            "event": beat,
            "world": rec.get("world", {}),
        })

    # Categorized event stream (full fidelity — never strided), so the UI can
    # colour-code input vs output vs custom:
    #   inputs    = external stimuli (probes); source "player" == a custom poke
    #   reactions = NPC outputs (target-role transductions: outburst/refusal/…)
    inputs, reactions = [], []
    for rec in records:
        for pr in rec.get("probes", []):
            parts = pr["probe"].split(":")  # "{t}:{source}:{type}:probe"
            if len(parts) >= 3:
                inputs.append({"t": rec["t"], "clock": rec["clock"],
                               "source": parts[1], "type": parts[2],
                               "custom": parts[1] == "player"})
        for tr in rec.get("transductions", []):
            if tr["role"] == "target":
                reactions.append({"t": rec["t"], "clock": rec["clock"],
                                  "actor": tr["actor"], "as": tr["as"],
                                  "action": tr["action"],
                                  "target": tr.get("target_inferred")})

    # M-G: observer interventions (present only when a subject was controlled).
    # Added as a non-empty key ONLY when interventions exist, so an autonomous
    # model (and the G2 parity hash built from it) is unchanged.
    interventions = []
    for rec in records:
        iv = rec.get("intervention")
        if iv and iv.get("selected_by") in ("manual_override", "manual_noop"):
            interventions.append({"t": rec["t"], "clock": rec["clock"],
                                  "day": rec["day"], **iv})

    incs = M.incidents(records, inc_actions)
    daily = {p: {d: daily_summary(records, p, d, inc_actions).to_dict() for d in days}
             for p in cast}
    model = {
        "meta": meta or {},
        "cast": cast,
        "display_names": {p: who(p) for p in cast},
        "rooms": list(cfg.rooms),
        "days": days,
        "high_thresholds": high,
        "state_families": {"need": list(NEED_STATES), "affect": list(AFFECT_STATES),
                           "sleep": list(SLEEP_STATES)},
        "ticks": ticks,
        "stride": stride,
        "transitions": [asdict(x) for x in mode_transitions(records)],
        "crossings": [asdict(x) for x in threshold_crossings(records, high)],
        "incidents": [{"t": i.t, "clock": i.clock, "day": i.day, "actor": i.actor,
                       "action": i.action, "event_id": i.event_id,
                       "provoked_by": i.provoked_by} for i in incs],
        "daily": daily,
        "why": {p: why(records, p) for p in cast},
        "inputs": inputs,
        "reactions": reactions,
        "metrics": aggregate_metrics(records, cfg),
        # M-I: always present so the UI can render the intervention console (the
        # palette + LLM-enabled state) even before any override exists.
        "intervention_ui": intervention_ui_model(records, cfg, interventions,
                                                  inc_actions),
    }
    if interventions:
        model["interventions"] = interventions
    return model
