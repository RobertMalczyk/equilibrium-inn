"""Validation report: do rest and sleep reduce fast states (fatigue/stress/anger)?
Usage: python -m experiments.report_rest_sleep_recovery"""

from __future__ import annotations

from inn import observe as O
from experiments.report_lib import CAST, canonical_trace, write_md


def render(records: list[dict]) -> list[str]:
    r = O.report_rest_sleep_recovery(records, CAST)
    lines = ["# Rest / sleep -> recovery", "",
             f"**Verdict:** {r['verdict']}", "",
             "| persona | fatigue Δ/tick resting | night Δfatigue | "
             "night Δstress | night Δanger |",
             "|---|---|---|---|---|"]
    for pid, p in r["per_persona"].items():
        nr = p["night_recovery"]
        lines.append(f"| {pid} | {p['fatigue_delta_resting']} | "
                     f"{nr['fatigue']} | {nr['stress']} | {nr['anger']} |")
    return lines


def main() -> None:
    # 3 full days so at least two nights are present for night-recovery deltas.
    lines = render(canonical_trace("impulse"))
    p = write_md("rest_sleep_recovery", lines)
    print("\n".join(lines))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
