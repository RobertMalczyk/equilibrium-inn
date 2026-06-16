"""Optional LLM semantic input seam (CLAUDE.md M-H).

A convenience layer that maps observer FREE TEXT to a *structured intervention
candidate* — nothing more. It is OFF by default and is never in the simulation
loop, never mutates engine state, and never executes anything on its own:

  free text -> LLM proposes a candidate -> strict schema validation ->
  the observer CONFIRMS -> executed through the EXACT M-G manual path
  (inn.cli._execute_intervention -> InnLoop.queue_intervention).

The canonical mode is the finite, no-LLM palette of M-G. This seam only widens
the input grammar. Hard rules: the LLM never controls NPC decisions, never sits
in the engine loop, never produces unstructured events that bypass validation.

Enablement: set EQUILIBRIUM_INN_LLM_PROVIDER (and the matching API key). With no
provider set, enabled() is False and the CLI hides/declines free text. Tests run
with the seam disabled and, where they exercise mapping, inject a FAKE client —
no network, no real API call, ever. The API key is read from the environment at
call time and handed to the SDK client only; it is NEVER placed in any structure
that reaches the trace, the session header, or a log line.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from inn.intervention import ACTION_PALETTE, PALETTE_VERBS, validate_target

ENV_PROVIDER = "EQUILIBRIUM_INN_LLM_PROVIDER"
ENV_API_KEY = "EQUILIBRIUM_INN_LLM_API_KEY"
ENV_MODEL = "EQUILIBRIUM_INN_LLM_MODEL"

_DOTENV_LOADED = False


def _load_dotenv_once() -> None:
    """Populate os.environ from a repo-root `.env` (KEY=VALUE lines), without
    overriding anything already set in the real environment. Dependency-free and
    idempotent. The `.env` file is gitignored — the key never leaves the machine,
    and (like all key handling here) is read at call time only, never persisted to
    the trace, session, or any log."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    p = Path(__file__).resolve().parents[1] / ".env"
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

# default model per provider when EQUILIBRIUM_INN_LLM_MODEL is unset
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}


def enabled() -> bool:
    """True only when a provider is configured. No provider -> the seam is off
    and the finite palette is the sole input path. (Reads os.environ only — the
    CLI loads any repo-root `.env` into the environment at startup via
    _load_dotenv_once, keeping this pure for tests.)"""
    return bool(os.environ.get(ENV_PROVIDER))


@dataclass(frozen=True)
class InterventionCandidate:
    actor: str            # always the controlled subject ("controlled_subject")
    action: str           # must be in ACTION_PALETTE
    target: str | None
    intensity: float      # [0, 1]
    public: bool
    confidence: float     # [0, 1]
    rationale: str
    original_text: str
    validation_notes: str = ""


@dataclass(frozen=True)
class MapResult:
    ok: bool
    message: str
    candidate: InterventionCandidate | None = None
    provenance: dict | None = None  # trace-safe (NO api key, NO secrets)


_SYSTEM_PROMPT = (
    "You translate an observer's natural-language instruction into a single "
    "structured intervention for a controlled character in a behavioural "
    "simulation. You do NOT decide anything autonomously; you only map the text. "
    "Respond with STRICT JSON and nothing else, with keys: action, target, "
    "intensity, public, confidence, rationale. `action` MUST be one of: "
    f"{', '.join(PALETTE_VERBS)}. `target` is a present character id or null. "
    "`intensity` and `confidence` are floats in [0,1]. `public` is a boolean."
)


def _user_prompt(text: str, subject: str, present: list[str]) -> str:
    return (f"Controlled subject: {subject}\n"
            f"Characters present with them: {', '.join(present) or '(none)'}\n"
            f"Observer instruction: {text!r}\n"
            f"Return the JSON intervention.")


def build_prompt(text: str, *, cfg, presence, subject: str) -> tuple[str, str]:
    """The deterministic prompt pair (system, user). Exposed for tests."""
    present = [p for p in presence.cohort(presence.room_of(subject)) if p != subject]
    return _SYSTEM_PROMPT, _user_prompt(text, subject, present)


def _call_provider(system: str, user: str) -> str:
    """Dispatch on EQUILIBRIUM_INN_LLM_PROVIDER. Returns the model's raw text.
    Imports the SDK lazily so the seam (and the rest of the inn) never depends on
    a provider package unless actually used."""
    provider = (os.environ.get(ENV_PROVIDER) or "").lower()
    api_key = os.environ.get(ENV_API_KEY)  # used here only; never returned/stored
    model = os.environ.get(ENV_MODEL) or _DEFAULT_MODELS.get(provider)
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        return resp.choices[0].message.content or ""
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=512, system=system,
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    raise RuntimeError(f"unknown LLM provider {provider!r} "
                       f"(set {ENV_PROVIDER} to 'openai' or 'anthropic')")


def _coerce_raw(raw: str) -> dict:
    """Parse the model's text as JSON. Raises ValueError on malformed output —
    we never silently coerce unstructured text into an action."""
    raw = (raw or "").strip()
    if raw.startswith("```"):  # tolerate a fenced code block
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"model did not return valid JSON ({e})")
    if not isinstance(obj, dict):
        raise ValueError("model JSON is not an object")
    return obj


def schema_validate(raw: dict, *, cfg, presence, subject: str,
                    original_text: str,
                    confidence_threshold: float | None = None) -> MapResult:
    """Strictly validate a raw candidate dict against the palette + target rules.
    Returns a failed MapResult (with a clear message) rather than raising, so the
    CLI/UI can show why an instruction was rejected."""
    action = raw.get("action")
    if not isinstance(action, str) or action not in ACTION_PALETTE:
        return MapResult(False, f"action {action!r} is not in the palette "
                                f"({', '.join(PALETTE_VERBS)}).")
    entry = ACTION_PALETTE[action]
    target = raw.get("target")
    if target in ("", "null", "none"):
        target = None
    if target is not None and not isinstance(target, str):
        return MapResult(False, "target must be a character id or null.")

    def _num(name, default):
        v = raw.get(name, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    intensity = _num("intensity", entry.intensity)
    confidence = _num("confidence", 1.0)
    if intensity is None or not (0.0 <= intensity <= 1.0):
        return MapResult(False, "intensity must be a number in [0, 1].")
    if confidence is None or not (0.0 <= confidence <= 1.0):
        return MapResult(False, "confidence must be a number in [0, 1].")

    err = validate_target(cfg, presence, subject, action, target)
    if err is not None:
        return MapResult(False, err)
    if confidence_threshold is not None and confidence < confidence_threshold:
        return MapResult(False, f"confidence {confidence:.2f} below threshold "
                                f"{confidence_threshold:.2f}.")

    cand = InterventionCandidate(
        actor="controlled_subject", action=action,
        target=(target if entry.needs_target else None),
        intensity=intensity, public=bool(raw.get("public", entry.public)),
        confidence=confidence, rationale=str(raw.get("rationale", "")),
        original_text=original_text, validation_notes="ok")
    provenance = {
        "source": "llm_semantic_mapper",
        "original_text": original_text,
        "structured_candidate": {  # trace-safe: no api key, no secrets
            "action": cand.action, "target": cand.target,
            "intensity": cand.intensity, "public": cand.public,
            "confidence": cand.confidence, "rationale": cand.rationale},
        "validation_result": "ok",
        "confirmed_by_user": True,  # set true only when executed via confirm
        "final_executed_action": {"action": cand.action, "target": cand.target,
                                   "intensity": cand.intensity},
    }
    return MapResult(True, "ok", candidate=cand, provenance=provenance)


def map_text(text: str, *, cfg, presence, subject: str, client=None,
             confidence_threshold: float | None = None) -> MapResult:
    """Map observer free text to a validated intervention candidate.

    `client`, when given, is a fake/stub with `.complete(system, user) -> str`
    (used by tests — no network). When omitted, the configured provider is
    called. The returned MapResult NEVER contains an API key."""
    system, user = build_prompt(text, cfg=cfg, presence=presence, subject=subject)
    try:
        raw_text = client.complete(system, user) if client is not None \
            else _call_provider(system, user)
        raw = _coerce_raw(raw_text)
    except Exception as e:  # noqa: BLE001 — surface any mapping failure cleanly
        return MapResult(False, str(e))
    return schema_validate(raw, cfg=cfg, presence=presence, subject=subject,
                           original_text=text,
                           confidence_threshold=confidence_threshold)
