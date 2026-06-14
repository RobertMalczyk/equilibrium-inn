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

from inn.chronicle import event_line, who, why_chain
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
META = ("wait", "look", "why", "sleep", "help", "quit")


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

    # -- advancing ---------------------------------------------------------

    def _advance(self, max_ticks: int, stop_when_quiet: int = 0) -> list[str]:
        """Step up to max_ticks; collect observable beats. If stop_when_quiet>0,
        stop early after that many consecutive quiet ticks (so a turn ends when
        the room settles). Nights compress to a single line."""
        beats: list[str] = []
        quiet = 0
        announced_night = False
        for _ in range(max_ticks):
            if self.t >= self.n_ticks:
                self.done = True
                beats.append("_(The third day ends. The inn closes.)_")
                break
            rec = self.loop._step(self.t)
            self.records.append(rec)
            self.t += 1
            if rec["night"]:
                if not announced_night:
                    beats.append("_Night falls; the inn sleeps. Tempers cool, "
                                 "but grudges keep._")
                    announced_night = True
                continue
            announced_night = False
            beat = event_line(rec)
            if beat is None:
                quiet += 1
                if stop_when_quiet and quiet >= stop_when_quiet:
                    break
                continue
            quiet = 0
            beats.append(f"**{self.clock()}** — {beat}.")
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
        if verb == "help":
            return [self._help_text()]
        if verb == "look":
            return [self.footer()]
        if verb == "why":
            if not args:
                return ["why who? (`why <name>`)"]
            name = self._resolve(args[0])
            if name is None:
                return [self._suggest(args[0])]
            return why_chain(self.records, name)
        if verb == "wait":
            n = int(args[0]) if args and args[0].isdigit() else 5
            self.verb_log.append((self.t, f"wait {n}"))
            beats = self._advance(n)
            return beats or [f"_({n} quiet ticks pass.)_"]
        if verb == "sleep":
            self.verb_log.append((self.t, "sleep"))
            beats = self._advance(self.n_ticks, stop_when_quiet=0) \
                if self._at_night_or_evening() else self._advance(40)
            return beats or ["_(You sleep. Morning comes.)_"]

        if verb in VERBS:
            if not args:
                return [f"{verb} who? ({verb} <name>)"]
            name = self._resolve(args[0])
            if name is None:
                return [self._suggest(args[0])]
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

    def _help_text(self) -> str:
        return (
            "Three days at the inn. Time moves in 2-minute ticks; you act, the "
            "room reacts.\n"
            "  insult/command/help/praise/serve <name> — act on someone present\n"
            "  wait [n] — let n ticks pass   sleep — until morning\n"
            "  look — who's here   why <name> — trace their last act   quit\n"
            "Example:  insult Halgrim   then   why Halgrim")

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
