"""G0 report: per-cell verdicts, envelope/clamp tables, FFT, corridor check,
plus the harvest export (NPC-sourced exchanges in the engine's scenario
format — the missing Wojslaw-commands-Halgrim style QA corpus).

Usage: python -m experiments.g0_report
Reads experiments/out/g0/sweep_results.json (run g0_sweep first).
"""

from __future__ import annotations

import json
from pathlib import Path

from inn.config import load_inn_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "out" / "g0"


def _plots(results: list[dict]) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    made = []
    impulse = [r for r in results if r["plan"] == "impulse"]
    scales = sorted({r["scale"] for r in impulse})
    richness = sorted({r["richness"] for r in impulse})

    # incident count heatmap (recovery on), scale x richness
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, rec_on in zip(axes, (True, False)):
        grid = [[next((r["incident_count"] for r in impulse
                       if r["scale"] == s and r["richness"] == rich
                       and r["recovery"] == rec_on), float("nan"))
                 for rich in richness] for s in scales]
        im = ax.imshow(grid, aspect="auto", cmap="magma")
        ax.set_xticks(range(len(richness)), richness)
        ax.set_yticks(range(len(scales)), scales)
        ax.set_xlabel("catalog richness")
        ax.set_ylabel("transducer scale")
        ax.set_title(f"incidents / 3-day impulse (recovery {'on' if rec_on else 'off'})")
        for i, row in enumerate(grid):
            for j, v in enumerate(row):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", color="w", fontsize=8)
        fig.colorbar(im, ax=ax)
    fig.tight_layout()
    p = OUT / "incidents_heatmap.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    made.append(p.name)

    # anger envelope + saturation dwell per cell (impulse)
    fig, ax = plt.subplots(figsize=(10, 4))
    cells = [r["cell"] for r in impulse]
    dwell = [r["max_upper_clamp_dwell"] for r in impulse]
    ax.bar(range(len(cells)), dwell)
    ax.axhline(0.20, color="r", ls="--", label="saturation threshold")
    ax.set_xticks(range(len(cells)), cells, rotation=90, fontsize=6)
    ax.set_ylabel("max upper-clamp dwell")
    ax.legend()
    fig.tight_layout()
    p = OUT / "clamp_dwell.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    made.append(p.name)
    return made


def _summary_findings(impulse: list[dict], control: list[dict],
                      corridor: list[int]) -> list[str]:
    """Findings derived from the sweep itself, so the report tracks the config
    instead of asserting a stale hand-written conclusion."""
    lo, hi = corridor
    n = len(impulse)
    n_sat = sum(1 for r in impulse if r["verdict"] == "saturates")
    n_lc = sum(1 for r in impulse if r["verdict"] == "limit_cycles")
    n_settle = sum(1 for r in impulse if r["verdict"] == "settles")
    corridor_cells = [r for r in impulse if r["in_corridor"]]
    out = [
        f"- {n_settle}/{n} impulse cells settle, {n_lc} limit-cycle, "
        f"{n_sat} saturate; {len(corridor_cells)} land in the corridor "
        f"[{lo}, {hi}].",
        f"- Control protocol: "
        f"{'all cells 0 incidents (clean)' if all(r['incident_count'] == 0 for r in control) else 'NON-ZERO — investigate'}.",
    ]

    # Verdict per overall outcome.
    if n_sat == 0 and corridor_cells:
        out.append(
            f"- VERDICT: the coupled inn is brought into the corridor. "
            f"Worst-case clamp dwell across all cells is "
            f"{max(r['max_upper_clamp_dwell'] for r in impulse):.2f} "
            f"(< 0.20 saturation line); deepest corridor cascade is "
            f"{max((r['incidents']['max_depth'] for r in corridor_cells), default=0)} hops.")
    elif n_sat:
        out.append(
            f"- VERDICT: {n_sat} cells still saturate — the coupled loop gain "
            "exceeds 1 somewhere in the swept region; damping is incomplete.")

    # Recovery axis effect (canonical = recovery off).
    by_rec = {False: [], True: []}
    for r in impulse:
        by_rec[r["recovery"]].append(r["incident_count"])
    if by_rec[False] and by_rec[True]:
        med_off = sorted(by_rec[False])[len(by_rec[False]) // 2]
        med_on = sorted(by_rec[True])[len(by_rec[True]) // 2]
        out.append(
            f"- FINDING (idle recovery): recovery-off cells produce "
            f"~{med_off} incidents (median) vs ~{med_on} with the engine's "
            f"default idle recovery restored. The corridor lives in the "
            f"recovery-{'off' if lo <= med_off <= hi else 'on'} regime; "
            f"recovery-{'on' if med_on < lo else 'off'} is "
            f"{'sub-corridor (stable but flat)' if med_on < lo else 'in range'}.")

    # Catalog-richness gradient (recovery-off, where the corridor lives):
    # scarcity should raise incident probability, ideally without runaway.
    rec_off = [r for r in impulse if not r["recovery"]]
    by_rich: dict[str, list[int]] = {}
    for r in rec_off:
        by_rich.setdefault(r["richness"], []).append(r["incident_count"])
    if by_rich:
        grad = {k: round(sum(v) / len(v), 1) for k, v in sorted(by_rich.items())}
        spread = max(grad.values()) - min(grad.values())
        unstable = [r for r in impulse if r["verdict"] != "settles"]
        if unstable:
            scales = sorted({r["scale"] for r in unstable})
            out.append(
                f"- FINDING (scarcity instability): mean incidents by catalog "
                f"richness {grad}; non-settling cells remain at "
                f"{sorted({r['richness'] for r in unstable})} × scale {scales}. "
                f"Thin catalog + higher hop scale still tips the inn out of the "
                f"corridor.")
        elif spread < 1.0:
            out.append(
                f"- FINDING (scarcity neutralized): mean incidents by catalog "
                f"richness {grad} — essentially flat. The hearth fallback that "
                f"hardened the thin-catalog runaway ALSO absorbs scarcity as a "
                f"texture knob: incident count no longer responds to the catalog "
                f"(CLAUDE.md §5 expects it to). Trade-off, not a free win. The "
                f"frustration-recovery alternative (register: 'Option B') keeps "
                f"a thin>rich gradient but recenters the corridor — a G1 decision.")
        else:
            out.append(
                f"- FINDING (scarcity gradient): mean incidents by catalog "
                f"richness {grad} — a thin catalog raises incident probability "
                f"WITHOUT runaway. Scarcity is a believable knob (CLAUDE.md §5/§7).")

    # Scale landscape (is the corridor monotonic in scale?).
    corr_scales = sorted({r["scale"] for r in corridor_cells})
    if corr_scales:
        out.append(
            f"- FINDING (scale landscape): corridor is reached at hop "
            f"scale(s) {corr_scales}. The incident response to scale is "
            f"non-monotonic near the stability edge — read the verdict table, "
            f"do not interpolate.")
    return out


def main() -> Path:
    cfg = load_inn_config(ROOT / "inn.yaml")
    results = json.loads((OUT / "sweep_results.json").read_text(encoding="utf-8"))
    corridor = cfg.g0["corridor"]["incidents_per_impulse_run"]
    impulse = [r for r in results if r["plan"] == "impulse"]
    control = [r for r in results if r["plan"] == "control"]
    formal_path = OUT / "formal_analysis.json"
    formal = (json.loads(formal_path.read_text(encoding="utf-8"))
              if formal_path.is_file() else None)
    plots = _plots(results)
    from experiments.harvest import harvest  # formalized QA-corpus harvest
    harvested = harvest()

    lines = [
        "# G0 stability report",
        "",
        f"Corridor target: {corridor[0]}-{corridor[1]} incidents per 3-day impulse run.",
        f"Cells: {len(impulse)} (scale x recovery x richness), 3 protocols each.",
        "",
        "## Verdicts (impulse protocol)",
        "",
        "| cell | incidents | verdict | in corridor | max clamp dwell | max cascade depth |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(impulse, key=lambda x: (x["scale"], not x["recovery"], x["richness"])):
        lines.append(
            f"| {r['cell']} | {r['incident_count']} | {r['verdict']} | "
            f"{'YES' if r['in_corridor'] else 'no'} | "
            f"{r['max_upper_clamp_dwell']:.2f} | {r['incidents']['max_depth']} |")
    lines += [
        "",
        "## Control protocol sanity",
        "",
        f"Control incidents across all cells: "
        f"{sorted(set(r['incident_count'] for r in control))} (must be all 0).",
        "",
        "## Summary",
        "",
        *_summary_findings(impulse, control, corridor),
        "",
        "## Formal analysis",
        "",
    ]
    if formal:
        for regime, s in formal.items():
            lines.append(f"- {regime}: spectral radius rho(A) = "
                         f"{s['spectral_radius']:.4f}, max cross-persona block "
                         f"gain = {s['max_offdiag_block_gain']:.4f}")
        lines.append("")
        lines.append("Empirical sweep remains authoritative (CLAUDE.md section 8); "
                     "the linearization is piecewise and regime-local.")
    else:
        lines.append("(formal_analysis.json not found — run experiments.g0_formal)")
    lines += [
        "",
        "## Artifacts",
        "",
        *[f"- {p}" for p in plots],
        f"- harvest: {len(harvested)} scenario YAMLs under out/g0/harvest/",
        "",
        "## Delivery-delay audit (one-tick latency contract)",
        "",
    ]
    delays: dict[str, int] = {}
    for r in results:
        for k, v in r["delivery_delays"].items():
            delays[k] = delays.get(k, 0) + v
    total = sum(delays.values())
    for k in sorted(delays, key=int):
        lines.append(f"- delay {k}: {delays[k]} ({delays[k]/total:.1%})")
    # Canonical-run chronicle (the believability artifact for the G1 audit).
    canonical = OUT / "s0.5_roff_normal" / "impulse"
    if (canonical / "trace.jsonl.gz").is_file():
        from experiments.chronicle import render as render_chronicle
        (canonical / "chronicle.md").write_text(
            render_chronicle(canonical, cfg), encoding="utf-8")
        lines += ["", "## Chronicle",
                  "", f"Canonical-run prose + why-chains: `{canonical}/chronicle.md`."]

    report = OUT / "g0_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", report)
    return report


if __name__ == "__main__":
    main()
