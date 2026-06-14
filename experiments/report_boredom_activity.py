"""Validation report: does boredom lead to seeking and activity?
Usage: python -m experiments.report_boredom_activity"""

from __future__ import annotations

from inn import observe as O
from experiments.report_lib import CAST, canonical_trace, write_md


def render(records: list[dict]) -> list[str]:
    r = O.report_boredom_activity(records, CAST)
    lines = ["# Boredom -> seeking -> activity", "",
             f"**Verdict:** {r['verdict']}", "",
             "| persona | seek starts | mean boredom @ seek | answered | timed out |",
             "|---|---|---|---|---|"]
    for pid, p in r["per_persona"].items():
        lines.append(f"| {pid} | {p['seek_starts']} | "
                     f"{p['mean_boredom_at_seek']} | "
                     f"{p['answered_with_activity']} | {p['timed_out']} |")
    return lines


def main() -> None:
    lines = render(canonical_trace("impulse"))
    p = write_md("boredom_activity", lines)
    print("\n".join(lines))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
