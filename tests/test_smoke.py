"""Engine-surface smoke test: the seam imports, the pin holds, facts hold."""

from inn import engine_surface as es


def test_pin():
    assert es.verify_pin() == es.PINNED_COMMIT


def test_surface_symbols():
    for name in es.__all__:
        assert getattr(es, name) is not None


def test_day_layout_facts():
    layout = es.believable_day_layout()
    assert abs(layout["dt"] - 120.0) < 1.0  # dt ~ 120 s/tick (CLAUDE.md section 2)
    assert layout["day_ticks"] == 717
    assert layout["waking_ticks"] == 508


def test_personas_load():
    for pid in ["wojslaw", "halgrim", "cichy", "edda", "welf", "lutek", "branic"]:
        cfg = es.load_eval_persona_timescale(pid)
        assert cfg.id == pid


def test_tick_signature():
    import inspect

    params = list(inspect.signature(es.tick).parameters)
    assert params[:3] == ["runtime", "t", "event"]
