"""Validation report: under the SAME environment, how do personas differ?
One canonical run; per-persona daily behaviour compared side-by-side.
Usage: python -m experiments.report_persona_contrast"""

from __future__ import annotations

from inn import observe as O
from experiments.report_lib import CAST, canonical_trace, write_md

INC = ("outburst",)


def render(records: list[dict]) -> list[str]:
    days = sorted({r["day"] for r in records})
    lines = ["# Persona contrast (same environment)", "",
             "Same impulse protocol, same seed; personas differ only by trait.", "",
             "| persona | day | busy% | idle% | seek% | rest% | sleep% | "
             "maxfat | maxbore | activities | interpretation |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for pid in CAST:
        for d in days:
            ds = O.daily_summary(records, pid, d, INC)
            if not ds.pct:
                continue
            p = ds.pct
            lines.append(
                f"| {pid} | {d} | {p.get('busy', 0):.0%} | {p.get('idle', 0):.0%} | "
                f"{p.get('seeking', 0):.0%} | {p.get('cooldown', 0):.0%} | "
                f"{p.get('sleep', 0):.0%} | {ds.max_fatigue:.2f} | "
                f"{ds.max_boredom:.2f} | {', '.join(ds.top_activities) or '—'} | "
                f"{ds.interpretation} |")
    return lines


def main() -> None:
    lines = render(canonical_trace("impulse"))
    p = write_md("persona_contrast", lines)
    print("\n".join(lines))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
