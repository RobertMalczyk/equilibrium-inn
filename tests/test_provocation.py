"""Provocation tracking + reactive attribution across the S3 social events.

Closing the S3 gap made cold_reply/refusal/complaint affect persona state; this
suite proves the SECOND-order fix: those events also become the recipient's
current provocation, so a later reactive action is attributed back to the right
source (loop._last_prov -> transducer target inference).

Two seams are exercised:
  * the world loop (InnLoop._step) for _last_prov bookkeeping (tasks A-E), and
  * the transducer directly for target inference (attribution regression).
Both are deterministic (seed fixed, control plan = no probes, explicit inject).
"""

from pathlib import Path

from inn.config import load_inn_config
from inn.engine_surface import ActionSelection, RawEvent
from inn.loop import InnLoop
from inn.trace import TraceWriter
from inn.transducer import transduce

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")

SPEAKER = "wojslaw"
LISTENER = "halgrim"


def _loop(tmp_path, extra):
    return InnLoop(CFG, seed=7, probe_plan="control",
                   trace=TraceWriter(tmp_path / "t.jsonl.gz"),
                   extra_events=extra)


def _inject_and_step(tmp_path, ev_type, source=SPEAKER, recipient=LISTENER, t=0):
    """Inject one event of ev_type from `source` to `recipient` at tick t, run
    that tick, and return the loop (so its _last_prov can be inspected)."""
    ev = RawEvent(type=ev_type, t=t, source=source, intensity=0.6,
                  context={"public": True})
    loop = _loop(tmp_path, [(t, recipient, ev)])
    for tick_i in range(t + 1):
        loop._step(tick_i)
    return loop


def _prov_source(loop, pid=LISTENER):
    return loop._last_prov[pid][1]


# -- 1. the new social events record their source as the provocation ---------

def test_cold_reply_records_source_as_provocation(tmp_path):
    loop = _inject_and_step(tmp_path, "cold_reply")
    assert _prov_source(loop) == SPEAKER


def test_refusal_records_source_as_provocation(tmp_path):
    loop = _inject_and_step(tmp_path, "refusal")
    assert _prov_source(loop) == SPEAKER


def test_complaint_records_source_as_provocation(tmp_path):
    loop = _inject_and_step(tmp_path, "complaint")
    assert _prov_source(loop) == SPEAKER


# -- 2. existing behavior preserved ------------------------------------------

def test_insult_still_records_source(tmp_path):
    loop = _inject_and_step(tmp_path, "insult")
    assert _prov_source(loop) == SPEAKER


def test_command_still_records_source(tmp_path):
    loop = _inject_and_step(tmp_path, "command")
    assert _prov_source(loop) == SPEAKER


# -- 3. neutral / non-provoking events do NOT overwrite the provocation ------

def test_non_provoking_event_does_not_overwrite(tmp_path):
    """A provoking event from A, then a non-provoking (but perceivable) event
    from B one tick later, must leave the recorded provocation pointing at A.
    `help` is perceivable but deliberately absent from provoking_event_types."""
    insult = RawEvent(type="insult", t=0, source=SPEAKER, intensity=0.6,
                      context={"public": True})
    helpful = RawEvent(type="help", t=1, source="cichy", intensity=0.6)
    loop = _loop(tmp_path, [(0, LISTENER, insult), (1, LISTENER, helpful)])
    loop._step(0)
    assert _prov_source(loop) == SPEAKER       # set by the insult
    loop._step(1)
    assert _prov_source(loop) == SPEAKER       # help from cichy did NOT overwrite


def test_config_drives_the_provoking_set():
    """The loop's live provoking set is the config's, and it is exactly the five
    documented types (no neutral/unknown leakage)."""
    assert set(CFG.provoking_event_types) == {
        "insult", "command", "cold_reply", "refusal", "complaint"}
    # all perceivable; none is a neutral surface
    assert "help" not in CFG.provoking_event_types
    assert "food_given" not in CFG.provoking_event_types
    assert "activity" not in CFG.provoking_event_types


# -- 4. attribution: a reaction provoked by a new social event targets its src

def _sel(action, score):
    return ActionSelection(action=action, score=score, kind=None,
                           interrupted=False, post_effects=None, explanation="")


def _reaction_target(provoking_type):
    """Simulate the loop->transducer seam: a persona was provoked by
    provoking_type from SPEAKER (so _last_prov.source = SPEAKER), then selects a
    reactive action whose target must be inferred. Assert it targets SPEAKER."""
    # an outburst is the canonical reaction; target inference uses provoking_source
    r = transduce(CFG, 100, LISTENER, _sel("outburst", 0.7),
                  provoking_source=SPEAKER,
                  provoking_id=f"99:{SPEAKER}:{provoking_type}",
                  cohort=[LISTENER, SPEAKER, "cichy"])
    targets = [a.recipient for a in r.addressed if a.role == "target"]
    return targets


def test_reaction_to_cold_reply_targets_source():
    assert _reaction_target("cold_reply") == [SPEAKER]


def test_reaction_to_refusal_targets_source():
    assert _reaction_target("refusal") == [SPEAKER]


def test_reaction_to_complaint_targets_source():
    assert _reaction_target("complaint") == [SPEAKER]
