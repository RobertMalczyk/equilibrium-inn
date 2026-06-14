"""Validation report: does busy/activity raise fatigue (vs idle)?
Usage: python -m experiments.report_activity_fatigue"""

from __future__ import annotations

from inn import observe as O
from experiments.report_lib import CAST, canonical_trace, write_md


def render(records: list[dict]) -> list[str]:
    r = O.report_activity_fatigue(records, CAST)
    lines = ["# Activity / busy -> fatigue", "",
             f"**Verdict:** {r['verdict']}", "",
             "| persona | fatigue Δ/tick busy | fatigue Δ/tick idle |",
             "|---|---|---|"]
    for pid, p in r["per_persona"].items():
        lines.append(f"| {pid} | {p['fatigue_delta_busy']} | "
                     f"{p['fatigue_delta_idle']} |")
    return lines


def main() -> None:
    lines = render(canonical_trace("impulse"))
    p = write_md("activity_fatigue", lines)
    print("\n".join(lines))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
