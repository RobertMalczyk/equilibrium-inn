from pathlib import Path

from inn.clock import Clock
from inn.config import load_inn_config
from inn.engine_surface import believable_day_layout
from inn.presence import Presence
from inn.schedule import ScheduleStream

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")
CLOCK = Clock.from_layout(believable_day_layout())
STREAM = ScheduleStream(CFG, CLOCK)


def test_clock_arithmetic():
    assert CLOCK.hhmm_to_offset("06:00") == 0
    assert CLOCK.tick_at(2, "06:00") == CLOCK.day_ticks
    assert CLOCK.clock_str(0) == "06:00"
    assert CLOCK.is_night(CLOCK.waking_ticks)
    assert not CLOCK.is_night(CLOCK.waking_ticks - 1)
    # 23:00 is the end of the 508-tick waking window
    assert abs(CLOCK.hhmm_to_offset("23:00") - CLOCK.waking_ticks) <= 1


def test_meals_and_rotation():
    # halgrim has 3 meal blocks; each emits exactly one food_given at block start
    meals = []
    for t in range(CLOCK.day_ticks * CFG.days):
        for ev in STREAM.events_for("halgrim", t):
            if ev.type == "food_given":
                meals.append((t, ev.item))
    assert len(meals) == 3 * CFG.days
    items_day1 = [i for _, i in meals[:3]]
    items_day2 = [i for _, i in meals[3:6]]
    assert items_day1 == list(CFG.menu_rotation[:3])
    assert items_day2 == list(CFG.menu_rotation[3:6])  # rotation continues across days


def test_nightfall_once_per_day_per_persona():
    nf = [t for t in range(CLOCK.day_ticks * CFG.days)
          for ev in STREAM.events_for("cichy", t) if ev.type == "nightfall"]
    assert len(nf) == CFG.days
    assert all(CLOCK.offset_in_day(t) == CLOCK.waking_ticks for t in nf)


def test_planned_rooms_and_presence():
    t_morning = CLOCK.tick_at(1, "08:00")
    assert STREAM.planned_room("halgrim", t_morning) == "yard"
    assert STREAM.scheduled_activity("halgrim", t_morning) == "chop_wood"
    t_evening = CLOCK.tick_at(1, "20:00")
    assert STREAM.planned_room("halgrim", t_evening) == "common_room"
    assert STREAM.scheduled_activity("halgrim", t_evening) is None

    p = Presence(CFG, STREAM, CLOCK)
    p.update(t_evening)
    cohort = p.cohort("common_room")
    assert cohort == [c.id for c in CFG.cast if c.room_home or True
                      ][0:0] + [pid for pid in
                                ["wojslaw", "halgrim", "cichy", "edda", "welf", "lutek", "branic"]
                                if STREAM.planned_room(pid, t_evening) == "common_room"]
    # everyone is in the common room in the evening
    assert len(cohort) == 7
    # at night everyone is home
    t_night = CLOCK.tick_at(1, "06:00") + CLOCK.waking_ticks + 5
    p.update(t_night)
    assert p.room_of("cichy") == "stable"
    # engagement overrides planned room
    p.set_engaged("halgrim", "dice_game")
    p.update(t_evening)
    assert p.room_of("halgrim") == "common_room"
    p.set_engaged("halgrim", "ride_out")
    p.update(t_evening)
    assert p.room_of("halgrim") == "yard"
