"""M-H — Optional LLM Semantic Input Seam acceptance tests.

The seam is OFF unless EQUILIBRIUM_INN_LLM_PROVIDER is set; the finite M-G
palette is always usable without it. Mapping is exercised with a FAKE client —
no network, no real API call. A confirmed candidate executes through the exact
M-G manual path. The API key never reaches the trace, header, or logs.
"""

import json
from pathlib import Path

from inn import llm_seam
from inn.cli import CliSession
from inn.config import load_inn_config
from inn.intervention import make_intervention

ROOT = Path(__file__).resolve().parents[1]
CFG = load_inn_config(ROOT / "inn.yaml")

SUBJECT = "welf"
TARGET = "halgrim"
TICK = 200


class FakeClient:
    """Stand-in for a provider SDK: returns a canned completion, records calls.
    No network. Used so tests never touch a real API."""
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.payload


def _session_at(tmp_path: Path, tick: int = TICK) -> CliSession:
    s = CliSession(CFG, seed=7, out_dir=tmp_path)
    s.do(f"wait {tick}")
    s.do("control welf")
    s.do("manual")
    return s


def _cand(action="command", target=TARGET, intensity=0.4, confidence=0.82):
    return json.dumps({"action": action, "target": target, "intensity": intensity,
                       "public": True, "confidence": confidence,
                       "rationale": "the observer wants this"})


# 1 — disabled by default (no provider env var).
def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EQUILIBRIUM_INN_LLM_PROVIDER", raising=False)
    assert llm_seam.enabled() is False


# 2 — the finite palette works with the LLM disabled.
def test_finite_palette_works_without_llm(monkeypatch, tmp_path):
    monkeypatch.delenv("EQUILIBRIUM_INN_LLM_PROVIDER", raising=False)
    assert make_intervention("insult", TARGET).route == "transduce"
    s = _session_at(tmp_path)
    out = s.do("say \"tell halgrim to rest\"")
    assert "off" in out[0].lower() and "palette" in out[0].lower()


# 3 — malformed LLM output is rejected (never coerced into an action).
def test_malformed_candidate_rejected(tmp_path):
    s = _session_at(tmp_path)
    r = llm_seam.map_text("do something", cfg=CFG, presence=s.loop.presence,
                          subject=SUBJECT, client=FakeClient("not json at all"))
    assert r.ok is False and r.candidate is None


# 4 — an invalid (absent/unreachable) target is rejected.
def test_invalid_target_rejected(tmp_path):
    s = _session_at(tmp_path)
    present = set(s._present_to(SUBJECT))
    absent = [c.id for c in CFG.cast if c.id != SUBJECT and c.id not in present][0]
    r = llm_seam.map_text("yell", cfg=CFG, presence=s.loop.presence, subject=SUBJECT,
                          client=FakeClient(_cand(action="insult", target=absent)))
    assert r.ok is False and "isn't with" in r.message


# 5 — an action outside the palette is rejected.
def test_invalid_action_rejected(tmp_path):
    s = _session_at(tmp_path)
    r = llm_seam.map_text("dance", cfg=CFG, presence=s.loop.presence, subject=SUBJECT,
                          client=FakeClient(_cand(action="dance")))
    assert r.ok is False and "palette" in r.message


# 6 — a valid mocked candidate requires explicit confirmation before execution.
def test_valid_candidate_requires_confirmation(monkeypatch, tmp_path):
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_PROVIDER", "openai")
    fake = FakeClient(_cand())
    monkeypatch.setattr(llm_seam, "map_text", lambda text, **kw: _real_map(text, kw, fake))
    s = _session_at(tmp_path)
    before = len(s.interventions)
    out = s.do("say \"tell halgrim to rest\"")
    assert any("confirm" in ln.lower() for ln in out)
    assert s._pending_say is not None
    assert len(s.interventions) == before  # nothing executed yet


def _real_map(text, kw, fake):
    # call the genuine validator with the fake client (no network)
    import inn.llm_seam as L
    return L.schema_validate(json.loads(fake.complete("", "")), cfg=kw["cfg"],
                             presence=kw["presence"], subject=kw["subject"],
                             original_text=text)


# 7 + 8 — confirmed candidate executes via the M-G path; trace records the
#         original text and the structured candidate.
def test_confirmed_executes_through_mg_path(monkeypatch, tmp_path):
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_PROVIDER", "openai")
    fake = FakeClient(_cand(action="command", target=TARGET))
    monkeypatch.setattr(llm_seam, "map_text", lambda text, **kw: _real_map(text, kw, fake))
    s = _session_at(tmp_path)
    s.do("say \"order halgrim to rest\"")
    s.do("confirm")
    assert s.interventions and s.interventions[-1]["verb"] == "command"
    iv = [r["intervention"] for r in s.records
          if r.get("intervention", {}).get("selected_by") == "manual_override"]
    assert iv and iv[-1]["llm"]["original_text"] == "order halgrim to rest"
    assert iv[-1]["llm"]["structured_candidate"]["action"] == "command"
    assert iv[-1]["llm"]["source"] == "llm_semantic_mapper"


# 9 — the API key is never written to the trace, header, or any log line.
def test_api_key_never_persisted(monkeypatch, tmp_path):
    secret = "sk-SECRET-TOKEN-DO-NOT-LEAK"
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_PROVIDER", "openai")
    monkeypatch.setenv("EQUILIBRIUM_INN_LLM_API_KEY", secret)
    fake = FakeClient(_cand(action="insult", target=TARGET))
    monkeypatch.setattr(llm_seam, "map_text", lambda text, **kw: _real_map(text, kw, fake))
    s = _session_at(tmp_path)
    s.do("say \"insult halgrim\"")
    s.do("confirm")
    path = s.save_session()
    blob = (tmp_path / "trace.jsonl.gz").read_bytes()
    assert secret.encode() not in blob
    assert secret not in path.read_text(encoding="utf-8")
    assert all(secret not in f"{t} {v}" for t, v in s.verb_log)
    assert all(secret not in json.dumps(iv) for iv in s.interventions)


# 10 — no real API call happens during tests (the fake client is the only path).
def test_no_real_api_call(tmp_path):
    s = _session_at(tmp_path)
    fake = FakeClient(_cand())
    r = llm_seam.map_text("x", cfg=CFG, presence=s.loop.presence, subject=SUBJECT,
                          client=fake)
    assert fake.calls == 1 and r.ok is True
