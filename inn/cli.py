"""Interactive CLI stepper (CLAUDE.md section 6): play the instrument.

Turn-based interactive fiction over discrete 2-minute ticks. Loop: advance ->
report -> prompt. Player verbs compile to RawEvents through the SAME probe path
as batch probes (the player is a probe source with a room and an id, no
interior). Reporting is event-driven: chronicle lines (deterministic narration
vocabulary, never an LLM) only when something happens; quiet stretches and nights
compress. Discoverability is derived, not documented: the verb set is the
mapper's perceivable vocabulary + meta-verbs, so the footer stays correct as the
vocabulary grows.

Run: python -m inn.cli [--menu] [--seed N]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from inn import metrics as M
from inn import observe as O
from inn.chronicle import event_line, who
from inn.config import InnConfig, Probe, load_inn_config
from inn.engine_surface import PINNED_COMMIT, believable_day_layout
from inn.loop import InnLoop
from inn.trace import TraceWriter

ROOT = Path(__file__).resolve().parents[1]

# Player verb -> (event type, default intensity, public?). The grammar is the
# mapper's perceivable vocabulary; `praise` is an alias for `help`.
VERBS: dict[str, tuple[str, float, bool]] = {
    "insult": ("insult", 0.8, True),
    "help": ("help", 0.8, False),
    "praise": ("help", 0.8, False),
    "command": ("command", 1.0, True),
    "serve": ("food_given", 1.0, False),
}
# Meta verbs. `observe`/`report`/`plot` are the Observation-Mode lens onto the
# living world (CLAUDE.md M-D); `mode` toggles ambient summaries on/off.
META = ("wait", "look", "observe", "report", "plot", "why", "mode",
        "sleep", "help", "quit")


def _bar(value: float, width: int = 12) -> str:
    """A soft ASCII gauge for a [0,1] value (Observer View, no raw float)."""
    value = max(0.0, min(1.0, value))
    filled = round(value * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"


def _sparkline(xs: list[float]) -> str:
    blocks = " ▁▂▃▄▅▆▇█"
    if not xs:
        return ""
    lo, hi = min(xs), max(xs)
    rng = hi - lo or 1.0
    return "".join(blocks[min(8, int((x - lo) / rng * 8))] for x in xs)


class CliSession:
    """Drives an InnLoop one player turn at a time. The REPL is a thin wrapper;
    `do()` is the testable core (returns the lines it would print)."""

    def __init__(self, cfg: InnConfig, seed: int, out_dir: Path,
                 profile: str | None = None, player_room: str = "common_room"):
        self.cfg = cfg
        layout = believable_day_layout()
        self.n_ticks = cfg.days * layout["day_ticks"]
        self.loop = InnLoop(cfg, seed=seed, probe_plan="control",
                            trace=TraceWriter(out_dir / "trace.jsonl.gz"),
                            profile=profile)
        self.t = 0
        self.player_room = player_room
        self.records: list[dict] = []
        self.verb_log: list[tuple[int, str]] = []
        self.seed = seed
        self.out_dir = out_dir
        self.done = False
        # Observation Mode (CLAUDE.md M-D): quiet stretches render as deterministic
        # ambient summaries (who idled / sought / worked / rested / slept) instead
        # of an opaque count. On by default — that is the whole point of the lens.
        self.observe_mode = True
        self.high = O.high_thresholds(cfg)
        self.cast_ids = [c.id for c in cfg.cast]
        self.incident_actions = tuple(cfg.g0["incident_def"]["actions"])

    # -- advancing ---------------------------------------------------------

    def _advance(self, max_ticks: int, stop_when_quiet: int = 0) -> list[str]:
        """Step up to max_ticks; collect observable beats. If stop_when_quiet>0,
        stop early after that many consecutive quiet ticks (so a turn ends when
        the room settles). Nights compress to a single line. In Observation Mode
        a quiet stretch flushes as a deterministic ambient summary instead of an
        opaque '(N quiet ticks pass.)'."""
        beats: list[str] = []
        quiet_recs: list[dict] = []
        announced_night = False

        def flush_quiet() -> None:
            if not quiet_recs:
                return
            if self.observe_mode:
                beats.append("_" + O.ambient_summary(
                    quiet_recs, self.high, self.cast_ids,
                    self.loop.clock.dt) + "_")
            else:
                n = len(quiet_recs)
                beats.append(f"_({n} quiet tick{'s' if n != 1 else ''} pass"
                             f"{'' if n != 1 else 'es'}.)_")
            quiet_recs.clear()

        for _ in range(max_ticks):
            if self.t >= self.n_ticks:
                flush_quiet()
                self.done = True
                beats.append("_(The third day ends. The inn closes.)_")
                break
            rec = self.loop._step(self.t)
            self.records.append(rec)
            self.t += 1
            if rec["night"]:
                flush_quiet()
                if not announced_night:
                    beats.append("_Night falls; the inn sleeps. Fast states "
                                 "(boredom, fatigue, stress) recover; grudges keep._")
                    announced_night = True
                continue
            announced_night = False
            beat = event_line(rec)
            if beat is None:
                quiet_recs.append(rec)
                if stop_when_quiet and len(quiet_recs) >= stop_when_quiet:
                    break
                continue
            flush_quiet()
            beats.append(f"**{self.clock()}** — {beat}.")
        flush_quiet()
        return beats

    def clock(self) -> str:
        return self.loop.clock.clock_str(max(0, self.t - 1))

    # -- verbs -------------------------------------------------------------

    def _player_probe(self, etype: str, target: str, intensity: float,
                      public: bool) -> Probe:
        c = self.loop.clock
        return Probe(day=c.day_of(self.t), hhmm=c.clock_str(self.t), type=etype,
                     intensity=intensity, source="player", target=target,
                     room=self.player_room,
                     context={"public": True} if public else {})

    def _present(self) -> list[str]:
        return [p for p in self.loop.presence.cohort(self.player_room)
                if p in {c.id for c in self.cfg.cast}]

    def footer(self) -> str:
        present = ", ".join(who(p) for p in self._present()) or "no one"
        return (f"[{self.clock()}] In the {self.player_room.replace('_', ' ')} "
                f"with: {present}.\n"
                f"verbs: {', '.join(VERBS)} <name> | "
                f"{', '.join(META)}")

    def do(self, line: str) -> list[str]:
        """Execute one player input; return the lines to display."""
        line = line.strip()
        if not line:
            return ["(say something — or `help`.)"]
        parts = line.split()
        verb, args = parts[0].lower(), parts[1:]

        if verb == "quit":
            self.done = True
            return ["You step out into the night."]
        # Bare `help` is the help screen; `help <name>` is the praise verb
        # (alias). Disambiguated so the two no longer collide.
        if verb == "help" and not args:
            return [self._help_text()]
        if verb == "look":
            return [self.footer()]
        if verb == "mode":
            self.observe_mode = not self.observe_mode
            return [f"Observation Mode {'on' if self.observe_mode else 'off'}."]
        if verb == "observe":
            return self._observe(args)
        if verb == "report":
            return self._report(args)
        if verb == "plot":
            return self._plot(args)
        if verb == "why":
            if not args:
                return ["why who? (`why <name>`)"]
            name = self._resolve(args[0])
            if name is None:
                return [self._suggest(args[0])]
            return O.why(self.records, name)
        if verb == "wait":
            n = int(args[0]) if args and args[0].isdigit() else 5
            self.verb_log.append((self.t, f"wait {n}"))
            beats = self._advance(n)
            return beats or [f"_({n} quiet ticks pass.)_"]
        if verb == "sleep":
            self.verb_log.append((self.t, "sleep"))
            beats = self._advance(self.n_ticks, stop_when_quiet=0) \
                if self._at_night_or_evening() else self._advance(40)
            return beats or ["_(Time advances; the inn rests and fast states "
                             "recover by morning.)_"]

        if verb in VERBS:
            if not args:
                return [f"{verb} who? ({verb} <name>)"]
            name = self._resolve(args[0])
            if name is None:
                return [self._suggest(args[0])]
            if name not in self._present():
                here = ", ".join(who(p) for p in self._present()) or "no one"
                return [f"{who(name)} isn't in the {self.player_room.replace('_', ' ')}. "
                        f"Here now: {here}."]
            etype, intensity, public = VERBS[verb]
            self.loop.inject_player_probe(
                self.t, self._player_probe(etype, name, intensity, public))
            self.verb_log.append((self.t, f"{verb} {name}"))
            beats = self._advance(8, stop_when_quiet=3)
            return beats or [f"_(You {verb} {who(name)}. Nothing comes of it — yet.)_"]

        return [self._suggest(verb)]

    # -- helpers -----------------------------------------------------------

    def _resolve(self, token: str) -> str | None:
        token = token.lower()
        ids = {c.id for c in self.cfg.cast}
        if token in ids:
            return token
        for cid in ids:  # match on display name too
            if who(cid).lower() == token:
                return cid
        return None

    def _suggest(self, token: str) -> str:
        names = [who(p) for p in self._present()]
        return (f"I don't know '{token}'. Try a verb ({', '.join(VERBS)}, "
                f"{', '.join(META)}) and someone here ({', '.join(names) or 'no one'}).")

    def _at_night_or_evening(self) -> bool:
        return self.loop.clock.is_night(self.t)

    # -- observation lens (CLAUDE.md M-D) ----------------------------------

    def _need_recently(self, pid: str) -> str | None:
        """Most recent activity offered to `pid`, for the state card."""
        for rec in reversed(self.records[-30:]):
            for o in rec.get("offers", []):
                if o["pid"] == pid:
                    return o["activity"]
        return None

    def _card(self, pid: str) -> list[str]:
        rec = self.records[-1]
        mood = O.mood_label(rec, pid, self.high)
        mode = O.MODE_LABEL[O.mode_of(rec, pid)]
        room = (rec["presence"].get(pid) or "?").replace("_", " ")
        act = self._need_recently(pid)
        head = (f"{who(pid)} — {mood} | {mode}" + (f" | {act}" if act else "")
                + f"  ({rec['clock']}, in the {room})")
        g = rec["personas"][pid]["state_after_post"]["global"]
        lines = [head]
        for fam in ("need", "affect", "sleep"):
            states = {"need": O.NEED_STATES, "affect": O.AFFECT_STATES,
                      "sleep": O.SLEEP_STATES}[fam]
            cells = [f"{st:<12}{_bar(g[st])} {g[st]:.2f}"
                     for st in states if st in g]
            lines.append("  " + "   ".join(cells))
        return lines

    def _observe(self, args: list[str]) -> list[str]:
        if not self.records:
            return ["Nothing observed yet — `wait` to let time pass."]
        if not args or args[0].lower() == "all":
            out = []
            rec = self.records[-1]
            for pid in self.cast_ids:
                mood = O.mood_label(rec, pid, self.high)
                mode = O.MODE_LABEL[O.mode_of(rec, pid)]
                room = (rec["presence"].get(pid) or "?").replace("_", " ")
                out.append(f"{who(pid):<9} {mood:<9} {mode:<9} {room}")
            return out
        name = self._resolve(args[0])
        if name is None:
            return [self._suggest(args[0])]
        return self._card(name)

    def _report(self, args: list[str]) -> list[str]:
        if not self.records:
            return ["No trace yet — `wait` to let time pass, then `report`."]
        sub = args[0].lower() if args else "day"
        if sub == "day":
            day = int(args[1]) if len(args) > 1 and args[1].isdigit() \
                else self.loop.clock.day_of(max(0, self.t - 1))
            out = [f"Day {day} — per-persona budget (busy/idle/seek/rest/sleep):"]
            for pid in self.cast_ids:
                ds = O.daily_summary(self.records, pid, day, self.incident_actions)
                if not ds.pct:
                    continue
                p = ds.pct
                out.append(
                    f"  {who(pid):<9} busy {p.get('busy', 0):.0%}  "
                    f"idle {p.get('idle', 0):.0%}  seek {p.get('seeking', 0):.0%}  "
                    f"rest {p.get('cooldown', 0):.0%}  sleep {p.get('sleep', 0):.0%}  "
                    f"| maxfat {ds.max_fatigue:.2f} maxbore {ds.max_boredom:.2f}  "
                    f"| {ds.interpretation}")
            return out
        if sub == "npc" and len(args) > 1:
            name = self._resolve(args[1])
            if name is None:
                return [self._suggest(args[1])]
            out = self._card(name)
            for day in sorted({r["day"] for r in self.records}):
                ds = O.daily_summary(self.records, name, day, self.incident_actions)
                if not ds.pct:
                    continue
                out.append(f"  day {day}: {ds.interpretation}; activities "
                           f"{', '.join(ds.top_activities) or '—'}; "
                           f"offers {ds.offers_ok} (contended {ds.offers_contended})")
            return out
        if sub == "sleep":
            return self._report_sleep()
        if sub == "activity":
            return self._report_activity()
        if sub == "scarcity":
            return self._report_scarcity()
        if sub == "incidents":
            return self._report_incidents()
        return ["report what? (day [N] | npc <name> | sleep | activity | "
                "scarcity | incidents)"]

    def _report_sleep(self) -> list[str]:
        """Does night recover fast states? Fatigue/stress at each day's last
        waking tick vs the next day's first waking tick."""
        days = sorted({r["day"] for r in self.records})
        out = ["Night recovery (dusk -> dawn, fast states):"]
        for pid in self.cast_ids:
            drops = []
            for d in days[:-1]:
                dusk = [r for r in self.records if r["day"] == d and not r["night"]]
                dawn = [r for r in self.records if r["day"] == d + 1 and not r["night"]]
                if not dusk or not dawn:
                    continue
                f0 = O.state_of(dusk[-1], pid, "fatigue")
                f1 = O.state_of(dawn[0], pid, "fatigue")
                drops.append((f0, f1))
            if drops:
                f0, f1 = drops[0]
                out.append(f"  {who(pid):<9} fatigue {f0:.2f} -> {f1:.2f} "
                           f"({f1 - f0:+.2f})")
        if len(out) == 1:
            out.append("  (advance through a night first)")
        return out

    def _report_activity(self) -> list[str]:
        from collections import Counter
        offered = Counter(o["activity"] for r in self.records
                          for o in r.get("offers", []))
        total = sum(offered.values())
        contended = sum(len(r.get("contention_losers", [])) for r in self.records)
        denom = total + contended
        out = [f"Activity supply: {total} offers granted, {contended} contended"
               f" (success {total / denom:.0%})" if denom else "No offers yet."]
        for aid, n in offered.most_common(8):
            out.append(f"  {aid:<14} {n}")
        return out

    def _report_scarcity(self) -> list[str]:
        from collections import Counter
        lost = Counter(p for r in self.records for p in r.get("contention_losers", []))
        out = ["Scarcity — seekers denied an activity (contention/starvation):"]
        if not lost:
            out.append("  none — supply has met demand so far")
        for pid in self.cast_ids:
            if lost.get(pid):
                out.append(f"  {who(pid):<9} denied {lost[pid]}x")
        return out

    def _report_incidents(self) -> list[str]:
        incs = M.incidents(self.records, self.incident_actions)
        if not incs:
            out = ["Incidents: none so far — the inn has stayed calm."]
        else:
            cs = M.cascade_stats(incs)
            out = [f"Incidents: {len(incs)} in {cs['n_cascades']} cascade(s); "
                   f"max depth {cs['max_depth']}, max breadth {cs['max_size']}."]
            for i in incs[:12]:
                root = " (rooted)" if i.provoked_by is None else ""
                out.append(f"  day {i.day} {i.clock}  {who(i.actor)} — {i.action}{root}")
        return out

    def _plot(self, args: list[str]) -> list[str]:
        if len(args) < 2:
            return ["plot <name> <state> [state ...]  e.g. plot welf boredom fatigue"]
        name = self._resolve(args[0])
        if name is None:
            return [self._suggest(args[0])]
        states = tuple(s.lower() for s in args[1:])
        bad = [s for s in states if s not in O.CARD_STATES + ("satisfaction",)]
        if bad:
            return [f"unknown state(s) {bad}; try {', '.join(O.CARD_STATES)}"]
        if not self.records:
            return ["No trace yet — `wait` first."]
        series = M.state_series(self.records, states)
        out = [f"{who(name)} over {len(self.records)} ticks:"]
        for st in states:
            xs = series[name][st]
            out.append(f"  {st:<12}{_sparkline(xs)}  ({min(xs):.2f}-{max(xs):.2f})")
        return out

    def _help_text(self) -> str:
        return (
            "Three days at the inn — an observatory, not a game. Time moves in "
            "2-minute ticks; you watch (and may perturb) a living world.\n"
            "  insult/command/help/praise/serve <name> — act on someone present\n"
            "  wait [n] — let n ticks pass   sleep — advance to morning\n"
            "  observe all | observe <name> — state cards (mood/mode/needs)\n"
            "  report day [N] | npc <name> | sleep | activity | scarcity | incidents\n"
            "  plot <name> <state...> — sparkline (e.g. plot welf boredom fatigue)\n"
            "  why <name> — why their last act happened (works for routine too)\n"
            "  mode — toggle ambient summaries   look — who's here   quit\n"
            "Example:  wait 60   then   observe all   then   why welf")

    # -- session log -------------------------------------------------------

    def save_session(self) -> Path:
        self.loop.trace.close()
        header = {
            "engine_commit": PINNED_COMMIT,
            "inn_yaml_sha256": self.cfg.yaml_sha256,
            "seed": self.seed,
            "profile": self.loop.profile,
            "ticks_played": self.t,
            "injected_verbs": [{"t": t, "verb": v} for t, v in self.verb_log],
        }
        p = self.out_dir / "session.json"
        p.write_text(json.dumps(header, indent=2), encoding="utf-8")
        return p

    # -- REPL --------------------------------------------------------------

    def run_repl(self, menu: bool = False) -> None:
        # the narration vocabulary uses unicode (em-dash, arrows); keep the
        # console from choking on a non-UTF-8 codepage (Windows cp1250 etc.).
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        print("The Inn — three days, a roadside common room.\n"
              "Type `help` for verbs. `quit` to leave.\n")
        print(self.footer())
        _try_readline(self)
        while not self.done:
            try:
                line = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if menu and line.isdigit():
                line = self._menu_to_verb(int(line))
            for out in self.do(line):
                print(out)
            if not self.done:
                print("\n" + self.footer())
        path = self.save_session()
        print(f"\nSession log: {path}")

    def _menu_to_verb(self, n: int) -> str:
        options = [f"{v} {p}" for p in self._present() for v in VERBS]
        return options[n - 1] if 1 <= n <= len(options) else "look"


def _try_readline(session: CliSession) -> None:
    """Tab completion over verbs + present names; silently skipped if the
    platform has no readline."""
    try:
        import readline
    except ImportError:
        return
    vocab = list(VERBS) + list(META)

    def completer(text: str, state: int):
        names = [who(p) for p in session._present()]
        opts = [w for w in vocab + names if w.lower().startswith(text.lower())]
        return opts[state] if state < len(opts) else None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")


def main(argv: list[str] | None = None) -> None:
    import argparse
    import tempfile
    ap = argparse.ArgumentParser(description="Play the inn.")
    ap.add_argument("--menu", action="store_true", help="numbered choices")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    cfg = load_inn_config(ROOT / "inn.yaml")
    out_dir = Path(args.out) if args.out else Path(tempfile.mkdtemp())
    out_dir.mkdir(parents=True, exist_ok=True)
    CliSession(cfg, seed=args.seed, out_dir=out_dir,
               profile=args.profile).run_repl(menu=args.menu)


if __name__ == "__main__":
    main(sys.argv[1:])
