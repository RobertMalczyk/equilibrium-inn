"""Interactive CLI stepper (CLAUDE.md S6). Drives CliSession.do() directly —
the REPL is a thin wrapper, so the verb->probe->report path is fully testable
without stdin. Deterministic (fixed seed, control plan + explicit verbs)."""

import tempfile
from pathlib import Path

from inn.config import load_inn_config
from inn.cli import CliSession, VERBS

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")


def _sess():
    return CliSession(CFG, seed=7, out_dir=Path(tempfile.mkdtemp()))


def test_player_verb_injects_a_probe_and_is_logged():
    s = _sess()
    out = s.do("insult Halgrim")
    assert any("insult" in line.lower() or "scene" in line.lower() for line in out)
    assert s.verb_log and s.verb_log[0][1] == "insult halgrim"


def test_player_verb_provokes_an_attributed_reaction():
    """The player is a probe source with an id; an NPC's reaction is attributed
    back to 'player' (the second-order attribution path, through the CLI)."""
    s = _sess()
    s.do("insult Halgrim")
    # the trace should carry a transduced reaction targeting the player
    targeted_player = [tr for rec in s.records for tr in rec["transductions"]
                       if tr["role"] == "target" and tr["target_inferred"] == "player"]
    assert targeted_player, "no reaction was attributed to the player"


def test_why_traces_to_the_external_root():
    s = _sess()
    s.do("insult Halgrim")
    chain = s.do("why Halgrim")
    assert chain and "Halgrim" in chain[0]
    assert any("external" in line for line in chain)  # walks back to the probe


def test_forgiving_errors():
    s = _sess()
    assert "who?" in s.do("insult")[0].lower()                 # bare verb
    assert "don't know" in s.do("frobnicate Halgrim")[0].lower()  # unknown verb
    assert "why who" in s.do("why")[0].lower()


def test_footer_lists_present_targets_and_verbs():
    s = _sess()
    foot = s.footer()
    assert "common room" in foot
    for v in VERBS:
        assert v in foot


def test_meta_verbs_and_session_log():
    s = _sess()
    assert s.do("look")
    assert s.do("wait 3")
    assert s.do("help")
    out = s.do("quit")
    assert s.done and out
    path = s.save_session()
    import json
    hdr = json.loads(path.read_text(encoding="utf-8"))
    assert hdr["seed"] == 7 and hdr["profile"] == "game_semantic_profile"
    assert "injected_verbs" in hdr


def test_name_resolution_accepts_display_and_id():
    s = _sess()
    assert s._resolve("halgrim") == "halgrim"
    assert s._resolve("Halgrim") == "halgrim"
    assert s._resolve("nobody") is None


def test_menu_maps_number_to_verb():
    s = _sess()
    verb = s._menu_to_verb(1)
    assert verb.split()[0] in VERBS


def test_observation_commands():
    s = _sess()
    s.do("wait 60")
    assert any("Welf" in ln or "Wojs" in ln for ln in s.do("observe all"))
    assert s.do("report day")[0].startswith("Day")
    assert "Incidents" in s.do("report incidents")[0]
    assert any("boredom" in ln for ln in s.do("plot welf boredom fatigue"))
    assert s.do("mode")[0].startswith("Observation Mode")
