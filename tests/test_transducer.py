from pathlib import Path

from inn.config import load_inn_config
from inn.engine_surface import ActionSelection
from inn.transducer import transduce

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


def _sel(action, score):
    return ActionSelection(action=action, score=score, kind=None,
                           interrupted=False, post_effects=None, explanation="")


COHORT = ["wojslaw", "halgrim", "cichy", "edda"]


def test_outburst_targets_and_witnesses():
    r = transduce(CFG, 100, "halgrim", _sel("outburst", 0.8),
                  provoking_source="wojslaw", provoking_id="99:wojslaw:command",
                  cohort=COHORT, scale=1.0)
    assert not r.gaps
    by_role = {a.recipient: a for a in r.addressed}
    assert by_role["wojslaw"].role == "target"
    assert by_role["wojslaw"].event.type == "insult"
    # non-root hop (provoked by another reaction): pure scale*score, no floor
    assert by_role["wojslaw"].event.intensity == 0.8
    assert by_role["cichy"].role == "witness"
    assert abs(by_role["cichy"].event.intensity - 0.12) < 1e-9  # attenuation 0.15
    assert by_role["cichy"].event.context["public"] is True
    assert all(a.provenance.provoked_by == "99:wojslaw:command" for a in r.addressed)
    assert r.conflict_intensity == 0.8
    assert "halgrim" not in by_role  # actor never receives own event


def test_floor_applies():
    r = transduce(CFG, 100, "halgrim", _sel("hostile_action", 0.1),
                  provoking_source="wojslaw", provoking_id=None, cohort=COHORT)
    target = next(a for a in r.addressed if a.role == "target")
    assert target.event.intensity == 0.5  # floor for hostile_action


def test_declared_gap_emits_nothing_but_is_logged():
    r = transduce(CFG, 100, "cichy", _sel("cold_response", 0.6),
                  provoking_source="wojslaw", provoking_id="99:w:command",
                  cohort=COHORT)
    assert r.addressed == []
    assert len(r.gaps) == 1
    assert r.gaps[0].action == "cold_response"
    assert r.gaps[0].provoked_by == "99:w:command"


def test_silent_actions_and_help_has_no_witnesses():
    r = transduce(CFG, 100, "welf", _sel("rest", 0.2),
                  provoking_source=None, provoking_id=None, cohort=COHORT)
    assert r.addressed == [] and r.gaps == []
    r = transduce(CFG, 100, "welf", _sel("cooperate", 0.9),
                  provoking_source="edda", provoking_id=None,
                  cohort=["welf", "edda", "branic"])
    assert [a.recipient for a in r.addressed] == ["edda"]  # no witnesses (MVP)
    assert r.addressed[0].event.type == "help"
    assert r.conflict_intensity == 0.0


def test_scale_override():
    r = transduce(CFG, 100, "halgrim", _sel("outburst", 0.4),
                  provoking_source="wojslaw", provoking_id=None,
                  cohort=COHORT, scale=2.0)
    target = next(a for a in r.addressed if a.role == "target")
    assert target.event.intensity == 0.8
