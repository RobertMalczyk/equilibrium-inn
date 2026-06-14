"""Validation report: how does catalog scarcity change activity starvation,
seeking, frustration, and incidents? Runs thin/normal/rich side-by-side.
Usage: python -m experiments.report_scarcity"""

from __future__ import annotations

from inn import metrics as M
from inn import observe as O
from experiments.report_lib import CAST, RICHNESS, run_trace, write_md


def _row(tag: str, records: list[dict]) -> dict:
    contended = sum(len(r.get("contention_losers", [])) for r in records)
    offers = sum(len(r.get("offers", [])) for r in records)
    seek = sum(1 for r in records for p in CAST if O.mode_of(r, p) == "SEEKING")
    max_frust = max((O.state_of(r, p, "frustration")
                     for r in records for p in CAST), default=0.0)
    incs = len(M.incidents(records, ("outburst",)))
    return {"tag": tag, "offers": offers, "contended": contended,
            "seek_ticks": seek, "max_frustration": round(max_frust, 3),
            "incidents": incs}


def render() -> list[str]:
    rows = []
    for tag in ("thin", "normal", "rich"):
        recs = run_trace("step", RICHNESS[tag], f"scarcity_{tag}")
        rows.append(_row(tag, recs))
    lines = ["# Scarcity: thin / normal / rich catalog", "",
             "Same rainy-day (step) protocol; only catalog richness varies.", "",
             "| richness | offers | contended | seek ticks | max frustration | incidents |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['tag']} | {r['offers']} | {r['contended']} | "
                     f"{r['seek_ticks']} | {r['max_frustration']} | {r['incidents']} |")
    lines += ["", "_Note (DEC-8): under the semantic profile the gradient is "
              "expected to be near-flat; a thin<rich gradient would be a finding._"]
    return lines


def main() -> None:
    lines = render()
    p = write_md("scarcity", lines)
    print("\n".join(lines))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
