"""G0 formal analysis: piecewise linearization of the coupled inn.

The closed-loop system (engine personas + transducer + witnessing) is
threshold/clamp non-smooth, so a single linearization cannot exist. We
extract a numeric Jacobian of one full 3-phase inn tick by state
perturbation, at two operating points:

  quiescent — mid-evening of the control run, no events in flight. The
      transducer fires nothing, so the Jacobian is block-diagonal
      (intra-persona decay); expected spectral radius < 1.
  provoked — a few ticks after the impulse probe, cascade active. The
      transducer rows are live, so cross-persona blocks are populated;
      this is the worst-case coupling regime.

State vector: per persona, the 11 global states + relation dims toward the
other cast members. Everything is reached through public surfaces only
(deep-copied PersonaRuntime fields are public dataclass attributes).

Per CLAUDE.md section 8, the EMPIRICAL sweep is authoritative; this analysis
is the paired formal check (user decision, section 10.4).

Usage: python -m experiments.g0_formal
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from inn.config import load_inn_config
from inn.engine_surface import GLOBAL_STATES, RELATION_DIMS
from inn.loop import InnLoop

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0"
EPS = 1e-4


class _NullTrace:
    def emit(self, record: dict) -> None:
        pass


def _state_index(cfg) -> list[tuple[str, str, str | None]]:
    """(persona, name, relation_other|None) for every state-vector component."""
    idx = []
    cast_ids = [c.id for c in cfg.cast]
    for pid in cast_ids:
        for s in GLOBAL_STATES:
            idx.append((pid, s, None))
        for other in cast_ids:
            if other == pid:
                continue
            for d in RELATION_DIMS:
                idx.append((pid, d, other))
    return idx


def _read(loop: InnLoop, idx) -> np.ndarray:
    x = np.empty(len(idx))
    for i, (pid, name, other) in enumerate(idx):
        rt = loop.runtimes[pid]
        if other is None:
            x[i] = rt.global_state.get(name, 0.0)
        else:
            x[i] = rt.relations.get(other, {}).get(name, 0.0)
    return x


def _write(loop: InnLoop, idx, x: np.ndarray) -> None:
    for i, (pid, name, other) in enumerate(idx):
        rt = loop.runtimes[pid]
        if other is None:
            rt.global_state[name] = float(x[i])
        else:
            rt.relations.setdefault(other, {d: 0.0 for d in RELATION_DIMS})[name] = float(x[i])


def _loop_at(cfg, plan: str, t_stop: int) -> InnLoop:
    loop = InnLoop(cfg, seed=cfg.g0["seed"], probe_plan=plan, trace=_NullTrace())
    loop.run(t_stop)
    return loop


def jacobian(cfg, plan: str, t_op: int) -> tuple[np.ndarray, list]:
    """Numeric Jacobian of one inn tick at operating tick t_op."""
    base = _loop_at(cfg, plan, t_op)
    idx = _state_index(cfg)
    x0 = _read(base, idx)

    base_step = copy.deepcopy(base)
    base_step._step(t_op)
    fx0 = _read(base_step, idx)

    n = len(idx)
    J = np.empty((n, n))
    for j in range(n):
        pert = copy.deepcopy(base)
        xj = x0.copy()
        xj[j] = min(1.0, xj[j] + EPS)  # states are clamped [0,1]
        eps_eff = xj[j] - x0[j]
        if eps_eff == 0.0:  # at upper clamp: perturb downward
            xj[j] = x0[j] - EPS
            eps_eff = -EPS
        _write(pert, idx, xj)
        pert._step(t_op)
        J[:, j] = (_read(pert, idx) - fx0) / eps_eff
    return J, idx


def coupling_summary(J: np.ndarray, idx, cfg) -> dict:
    cast_ids = [c.id for c in cfg.cast]
    pid_of = [i[0] for i in idx]
    blocks = {}
    for a in cast_ids:
        for b in cast_ids:
            rows = [i for i, p in enumerate(pid_of) if p == a]
            cols = [i for i, p in enumerate(pid_of) if p == b]
            blocks[f"{a}<-{b}"] = float(np.abs(J[np.ix_(rows, cols)]).max())
    eig = np.linalg.eigvals(J)
    return {
        "spectral_radius": float(np.abs(eig).max()),
        "max_offdiag_block_gain": max(v for k, v in blocks.items()
                                      if k.split("<-")[0] != k.split("<-")[1]),
        "block_gains": blocks,
    }


def main() -> dict:
    cfg = load_inn_config(ROOT / "inn.yaml")
    clock_probe = None
    # operating points: quiescent = control day1 20:00; provoked = impulse +3 ticks
    from inn.clock import Clock
    from inn.engine_surface import believable_day_layout
    clock = Clock.from_layout(believable_day_layout())
    t_quiet = clock.tick_at(1, "20:00")
    t_prov = clock.tick_at(1, "20:00") + 3  # impulse probe lands at day1 20:00

    out = {}
    for name, plan, t_op in (("quiescent", "control", t_quiet),
                             ("provoked", "impulse", t_prov)):
        print(f"jacobian @ {name} (t={t_op})...", flush=True)
        J, idx = jacobian(cfg, plan, t_op)
        summary = coupling_summary(J, idx, cfg)
        out[name] = summary
        np.save(OUT / f"jacobian_{name}.npy", J)
        print(f"  rho(A) = {summary['spectral_radius']:.4f}, "
              f"max cross-persona block gain = {summary['max_offdiag_block_gain']:.4f}")
    OUT.mkdir(parents=True, exist_ok=True)
    slim = {k: {kk: vv for kk, vv in v.items() if kk != "block_gains"} | {
        "block_gains_nonzero": {b: g for b, g in v["block_gains"].items()
                                if g > 1e-9 and b.split("<-")[0] != b.split("<-")[1]}}
        for k, v in out.items()}
    (OUT / "formal_analysis.json").write_text(json.dumps(slim, indent=2),
                                              encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
