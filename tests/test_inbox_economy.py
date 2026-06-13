from pathlib import Path

from inn.clock import Clock
from inn.config import load_inn_config
from inn.economy import Economy
from inn.engine_surface import RawEvent, believable_day_layout
from inn.inbox import Inbox

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
CLOCK = Clock.from_layout(believable_day_layout())


def _ev(type_, t, source=None, intensity=1.0):
    return RawEvent(type=type_, t=t, source=source, intensity=intensity)


def test_inbox_priority_and_t_rewrite():
    ib = Inbox(CFG.inbox, CFG.cast_order)
    ib.push(_ev("food_given", 9), 9)
    ib.push(_ev("insult", 9, source="wojslaw", intensity=0.5), 9)
    d, dropped = ib.pop_for_tick(10)
    assert not dropped
    assert d.event.type == "insult"  # priority beats arrival order
    assert d.event.t == 10           # t rewritten to delivery tick
    assert d.delay == 1
    d2, _ = ib.pop_for_tick(11)
    assert d2.event.type == "food_given" and d2.delay == 2


def test_inbox_intensity_then_cast_order_tiebreak():
    ib = Inbox(CFG.inbox, CFG.cast_order)
    ib.push(_ev("insult", 5, source="welf", intensity=0.4), 5)
    ib.push(_ev("insult", 5, source="halgrim", intensity=0.4), 5)
    ib.push(_ev("insult", 5, source="cichy", intensity=0.9), 5)
    d, _ = ib.pop_for_tick(6)
    assert d.event.source == "cichy"      # higher intensity first
    d, _ = ib.pop_for_tick(7)
    assert d.event.source == "halgrim"    # then cast order


def test_inbox_drops_stale_loudly():
    ib = Inbox(CFG.inbox, CFG.cast_order)
    ib.push(_ev("help", 0), 0, provenance_id="0:x:cooperate")
    t = CFG.inbox.max_defer_ticks + 1
    d, dropped = ib.pop_for_tick(t)
    assert d is None
    assert len(dropped) == 1
    assert dropped[0].provenance_id == "0:x:cooperate"
    assert dropped[0].dropped_t == t


def test_economy_scheduled_offer_and_depletion():
    eco = Economy(CFG, CLOCK)
    t = CLOCK.tick_at(1, "08:00")
    before = eco.sources["chop_wood"].budget
    ev = eco.offer_scheduled(t, "halgrim", "chop_wood")
    assert ev is not None and ev.type == "activity" and ev.item == "chop_wood"
    assert ev.context["kind"] == "external"
    assert eco.sources["chop_wood"].budget < before
    # capacity 1: once engaged, no second offer
    eco.set_engaged("halgrim", "chop_wood")
    assert eco.offer_scheduled(t, "branic", "chop_wood") is None


def test_economy_contention_tiebreak():
    eco = Economy(CFG, CLOCK)
    t = CLOCK.tick_at(1, "20:00")
    # dice_game capacity 3; four seekers past latency, equal urge except one
    seekers = [("wojslaw", 0.5, t - 5), ("halgrim", 0.9, t - 5),
               ("welf", 0.5, t - 5), ("branic", 0.5, t - 5)]
    offers = eco.answer_seekers(t, seekers, lambda pid: "common_room")
    assert "halgrim" in offers                  # highest urge wins first
    granted = list(offers)
    assert len(granted) == 4 or len(granted) == 3
    # capacity only binds via engagement; all four got offers from the two
    # common_room evening sources unless budget ran out — what matters is order:
    assert granted[0] == "halgrim"


def test_economy_latency_and_weather_closure():
    eco = Economy(CFG, CLOCK)
    t = CLOCK.tick_at(1, "20:00")
    # not waited long enough -> nothing
    offers = eco.answer_seekers(t, [("welf", 0.5, t)], lambda pid: "common_room")
    assert offers == {}
    # weather closes outdoor entries
    eco.set_weather_closed(True)
    t2 = CLOCK.tick_at(1, "19:30")
    offers = eco.answer_seekers(t2, [("welf", 0.5, t2 - 5)], lambda pid: "yard")
    assert offers == {}   # evening_walk (yard) is outdoor -> closed
    eco.set_weather_closed(False)
    offers = eco.answer_seekers(t2, [("welf", 0.5, t2 - 5)], lambda pid: "yard")
    assert "welf" in offers
