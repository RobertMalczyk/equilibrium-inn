# CLAUDE.md — equilibrium-inn

**What this is:** the project document for building the inn platform — a living-world test
bed on top of equilibrium-engine. Drop this at the repo root as `CLAUDE.md`. It is the
contract Claude Code works under; where this document and an ad-hoc instinct disagree,
this document wins until the user amends it.

**Status:** unverified design (v1), produced from a design session, audited by the user
but not yet validated by any experiment. Gate G0 exists to convert its central assumption
(coupled stability) from belief to observation. Treat every quantitative choice in here
as provisional until a gate confirms it.

**House rules inherited from the engine project:** spec/contract first, code second.
Hard gates between deliberation and commitment. The user audits at every checkpoint
marked AUDIT. No silent workarounds — if something can't be done within the contracts
below, stop and file it as a finding instead of hacking around it.

---

## 0. HARD RULES (non-negotiable; violating one is a stop-the-line event)

These are absolute. They are not trade-offs to be balanced against convenience, and
they outrank every other instruction in this file or any ad-hoc request. If a task
appears to require breaking one, STOP and surface it as a finding — do not proceed.

1. **The engine repo is READ-ONLY. It is strictly forbidden to modify, write, create,
   delete, stage, commit, push, or otherwise mutate ANYTHING in the
   `equilibrium-engine/` checkout — code, config, tests, calibration, goldens, git
   state, or working tree.** The inn never edits the engine to make the inn work. The
   engine is layer 0, consumed read-only at a pinned commit through its public surface
   only (§3, §4). This includes: no `git` write commands against the engine clone
   (`commit`, `push`, `checkout -b`, `merge`, `rebase`, `add`, `restore`, `stash`, …);
   no editing engine source/YAML; no regenerating engine goldens; no "quick patch" to
   an engine file even if it would fix an inn problem. The ONLY permitted engine git
   operations are read/pin-management ones the inn needs: `fetch`, `rev-parse`,
   `log`/`show`/`diff`/`status` (read), and `checkout <pinned-commit>` solely to put
   the clone AT the pin the inn already declares. Bumping the pin is an inn-side change
   (`PINNED_COMMIT` + `meta.engine_commit`), never an engine-side one.

2. **Any need that cannot be met through the engine's public surface is filed as an
   engine FINDING, never worked around by reaching into engine internals or vendoring
   a modified copy.** Engine changes are made by the user (or in a separate, explicitly
   engine-scoped session) in the engine repo itself — then the inn consumes the result
   by a deliberate pin bump. (Example done right this milestone: the S3 social-mapper
   events were added to the engine by the user; the inn only bumped the pin and wired
   the transducer — §4.2.)

3. **No behavior-shaping numeric literal lives in inn code** — it lives in `inn.yaml`
   (§4.1). 4. **Analysis reads only the society trace**, never live engine objects
   (§4.2). 5. **No LLM anywhere in the simulation loop** (§6). 6. **Work proceeds
   through the gates; the user audits at every AUDIT checkpoint** before the next stage
   is authorized (§8).

Rules 3–6 restate frozen decisions elaborated below; rules 1–2 are the engine-isolation
boundary and are the hardest of the hard. When in doubt about whether an action touches
the engine repo, treat it as forbidden and ask.

---

## 1. Purpose — what this platform is for

This is an **instrument, not a game and not a showcase**. Its job is to run a small
living world on the engine, measure the result at the society level, and convert
findings into next engine iterations. A playable CLI and a public demo page fall out as
byproducts, in that order of priority.

The framing is the *game* baseline, not social science. We are not modeling real
society. The industry standard NPC is a schedule automaton (the baker bakes 8 h, eats,
sleeps) plus a trigger→bark table; the celebrated high end (Nemesis system) is
persistent relational memory toward one agent. Against that baseline the engine's claim
is: **the schedule stays; the engine decides how the schedule gets performed today.**
The unit of value is the *incident* — a rare, explainable, remembered deviation from
routine. A good run is a mostly-boring inn with occasional, causally-traceable texture.
A chaotic inn is a failure. A dead inn is a failure. Quantifying that corridor is the
instrument's first job.

Setting: a roadside inn, 5–7 personas from the existing cast (Wojsław, Halgrim, Cichy,
Edda, Welf, Lutek, Branic — Marta exists only as an event source label and needs no
interior), simulated for a canonical **3 in-world days** including nights, since sleep
is where fast states reset while grudges persist and compound (verified engine behavior,
see `eval/night_runner.py`).

## 2. Verified facts this design stands on

These were measured live against the engine (commit at the pinned tag), not assumed:

- Believable timescale: `eval.calibrated.believable_day_layout()` → dt ≈ 120 s/tick,
  **717 ticks/day**, 508 waking ticks. Three full days of one persona ≈ 0.27 s wall
  time; a six-persona inn for 3 days is **~2 s**. Parameter sweeps are minutes. Nights
  are simulated honestly; "fast-forward" is a display concern only.
- Relations integrate dynamically from events: one public insult moved the target's
  `resentment[source]` 0.20 → 0.561, persisting. Relation half-lives are ~28–42 h of
  game time, so relational dynamics are **invisible in short runs** and require the
  multi-day horizon at believable timescale.
- Priming works: the same insult that Halgrim absorbs at rest produces a sustained
  `cold_response` when frustration/stress are pre-elevated. Scarcity-induced frustration
  therefore changes incident probability with no rule saying so.
- NPC-sourced events are first-class (litmus scenarios already use `source: wojslaw`).
- The proactive loop closes against an external reactive driver (`eval/mock_world.py`):
  boredom → SEEKING → offer → engage → relief, or timeout → frustration. The inn's
  activity economy is this mechanism generalized.
- The mapper's perceivable-event vocabulary: `food_given, insult, help, command,
  nightfall, weather, activity`. The action catalog is wider than this — see the
  declared lossiness in §4.
- `ActionSelection` does **not** expose the reaction target; the selector knows it
  internally. The world layer can infer target = provoking event's source. An explicit
  trace field is an engine/spec change and is deferred (§9).

## 3. Repository strategy

Build first as a directory inside the **private** repo, where the world layer can
co-evolve with any spec findings at zero ceremony. The public repo `equilibrium-inn` is
created as the *artifact of G1 passing*: when the user's audit freezes the transducer
table and the engine-facing surface, extract against a **pinned engine tag**
(`equilibrium-engine @ git+...@vX.Y`). From then on the inn consumes the engine only
through its public surface: `engine.simulation.tick`, the loaders
(`engine.yaml_io.load_persona`, `eval.calibrated.load_eval_persona_timescale`,
`believable_day_layout`), and the narration vocabulary (`eval/render_narration.py`).
Any need that cannot be met through that surface is filed as an engine finding — never
worked around by importing internals.

The existing replay demo (`demo/`) stays in the engine repo: showcases live with the
engine; anything owning a mechanism or a research question gets its own repo.

## 4. Architecture

Four layers. The engine is layer 0 and is **never modified by this project**.

### 4.1 The inn as data — `inn.yaml`

The entire inn is configuration: cast with room assignments; rooms; per-persona
schedules as day-blocks; meal times and a menu rotation; the activity catalog (§5); the
transducer table; witnessing attenuations; the probe plan. No numeric literal that
shapes behavior may live in code. The *scenario* concept shrinks accordingly: in the
living world, a scenario is just the probe plan — the possibilities are the catalog,
and the day precipitates out of schedule × catalog × cast.

### 4.2 The world layer — components and contracts

| Component | Owns | Never |
|---|---|---|
| Schedule compiler | Time arithmetic; day-blocks → per-persona event streams (activity *offers*, `food_given` with menu rotation, `nightfall`) | Forcing behavior (it offers, the engine decides); reading persona state |
| Presence | Room label per persona per tick, driven by schedule and activity engagement; witnessing policy: direct target full intensity, co-located witnesses attenuated with `public: true`, other rooms nothing | Geometry, coordinates, pathfinding, travel time (sub-tick at dt = 2 min) |
| Transducer | Action → perceivable event per the YAML table below; intensity policy `f(potential at selection, world attenuation)`, f linear initially; **provenance stamping** on every emitted event (which action, provoked by which event, recursively) | Reading/writing persona state; emitting events the mapper cannot perceive; same-tick delivery |
| Activity economy | The supply side of stimulation: catalog availability, capacity, depletion/replenish per source (mock_world style); answering SEEKING queries; deterministic contention tiebreak | Tracking the persona's *perceived* staleness — that is the engine's repetition/novelty history, fed by passing the activity id as the event `item`. No duplicated novelty bookkeeping |
| Inn loop | The three-phase synchronous tick (§4.3); the clock and day/night; **sole caller of `tick()`** | Touching equations; holding state outside engine runtimes + inboxes + world states |
| World states | Standalone one-pole integrators owned by the world (room tension fed by transduced conflict; pot contents), declared world physics | Injecting channels the mapper doesn't know; masquerading as persona dynamics |
| Session log | The determinism tuple: (engine tag, inn.yaml hash, calibration hashes, seed, ordered player-event log); replay | Wall clock, network, unseeded randomness anywhere in the loop |
| Society trace | Complete per-tick record: all interiors (full TickTrace fidelity), the relation tensor, world states, presence, the transduction log with provenance | Lossy emission; the completeness standard is inherited from the engine, not relaxed |

**Transducer table v0 (lossiness is declared in the config file itself):**

| ActionId | Perceived as | Direct target | Witnesses in room |
|---|---|---|---|
| outburst | `insult`, source = actor | full intensity | attenuated, `public: true` |
| cooperate, positive_response | `help`, source = actor | full | none (MVP) |
| refuse | `refusal`, source = actor | full | attenuated, `public: true` |
| complain | `complaint`, source = actor | full | none (MVP) |
| cold_response | `cold_reply`, source = actor | full | none (MVP) |
| seek_stimulus, rest, activities | none (MVP) | — | — |

**S3 gap CLOSED (engine `0b7df59`, Social Event Mapper Pack).** The authority loop now
closes both ways: the three negative-but-not-insult social actions map to their own
relational events (`refusal`/`complaint`/`cold_reply`), each its own engine channel
(NOT aliased to `insult`). `refuse` is witnessed — "my request was publicly refused" is
the canonical pride input — while `complaint`/`cold_reply` are direct-only in the MVP.
Floors are provisional, tuned by the M-B semantic-profile G0 sweep. The flagship spec
extension that this gap was waiting on is the engine change that landed these events.

**Second-order (attribution) gap also closed.** A first-order fix (the event affects
state) is not enough: the world loop must also record the new event as the recipient's
current *provocation* so a later reactive action is attributed back to the right source
(`loop._last_prov` → transducer target inference, §2). The provoking-event set is now
config-driven — `world.provoking_event_types` in `inn.yaml`
(`[insult, command, cold_reply, refusal, complaint]`); omitting the block falls back to
the historical safe default `[insult, command]`, and every entry must be perceivable
(neutral/unknown names fail config load, so nothing becomes provoking by accident).
Player-verb routing through this path remains separate and is not yet implemented (M-C).

### 4.3 The tick loop — frozen semantics

Synchronous, **one-tick social latency**:

- Phase A — deliver frozen inboxes for tick t (schedule + probes + last tick's social
  events); call `tick()` for every persona; order irrelevant by construction.
- Phase B — collect all `ActionSelection`s.
- Phase C — transduce through presence and witnessing; stamp provenance; deliver the
  resulting events to inboxes for **t+1**. Emit the society trace record for t.

Order-invariance for the whole society holds by construction, not by discipline. The
one-tick delay between provocation and reaction-to-reaction is behaviorally honest.
Same-tick delivery is rejected; reopening it requires a spec-level argument.

### 4.4 Determinism contract

A session is fully determined by its tuple (§4.2 Session log). No randomness outside
the session seed; any inherited stochastic choice (e.g. activity-kind picks in the
mock_world style) draws from the seeded generator. CI runs one canonical session and
asserts a golden SHA-256 over the full society trace. Interactive CLI sessions append
player verbs to the log and therefore replay identically. Contention tiebreak (§5) is
part of this contract.

## 5. The activity economy — how the world is a world

Demand is the engine's, untouched: work blocks integrate fatigue; idleness drifts
boredom; `urge_boredom` crosses threshold → SEEKING; unanswered seeking times out into
frustration. The engine never knows *what* there is to do — only that it wants
something.

Supply is the world's, as data. Catalog entries carry: room, kind (work / leisure /
social), time window, capacity, depletion-on-use and replenish-per-tick (the
generalization of mock_world's single novelty budget into a per-source schedule). When
a persona is SEEKING, the inn loop queries: available in this room, at this hour, with
free capacity, with novelty remaining → make an offer (`activity` event; the engine
decides whether to engage) or offer nothing and let the timeout do its work.

Scarcity is therefore a config knob, and the work→tire→bore→fray loop closes with no
rule stating it: schedule → fatigue; evening idleness → boredom; thin evening catalog →
some seekers find nothing → frustration; frustration is priming; the common room
concentrates the primed, the provocations, and the witnesses. `weather: rain` is the
canonical amplifier and is double-plumbed by design: engine-side stress channel + world-
side closure of outdoor catalog entries (supply shock + irritability + forced
co-location).

**Contention rule (deterministic):** multiple seekers, limited capacity → highest
current urge wins; ties broken by fixed cast order as listed in `inn.yaml`; rule
documented in the config. The loser's timeout-frustration is intended texture: social
coupling through pure scarcity, no transducer involved.

## 6. The CLI — playing the instrument

Turn-based, derived entirely from the trace; structurally interactive fiction over
discrete 2-minute ticks. Loop: advance → report → prompt. Player verbs compile to
`RawEvents` through the same path as batch probes (the player is a probe source with a
room and an id, no interior). Reporting is event-driven: chronicle lines (rendered with
the `render_narration` vocabulary — deterministic, never an LLM) only when something
happens; quiet stretches and nights compress to one line.

Discoverability is **derived, not documented**: the verb set = the mapper's perceivable
vocabulary (insult, praise/help, command, serve, weather) + meta-verbs
(`wait`, `look`, `why <name>`, `sleep`, `quit`), so the contextual footer is generated
from `inn.yaml` + the event vocabulary and stays correct as the vocabulary grows.
Affordances, all cheap: footer after every report listing verbs and present targets;
readline tab completion (verbs + names present); forgiving errors (suggest, never
scold; bare verb prompts for target); three-line first-run example; and a `--menu` flag
rendering numbered choices instead of a grammar — both modes compile to identical
events and an identical session log.

`why <name>` renders the provenance chain as text (outburst @13:04 ← your insult
@13:02, witnessed by …, anger 0.71 crossed threshold at esc 0.19). This is the
debuggability claim made playable; treat it as a first-class feature, not a debug
afterthought.

No LLM anywhere in the loop. Optional, later, off by default, at the engine's
sanctioned seams only: expression (dramatizing the story_trace digest for a public
page; derived text, cacheable, never feeding back) and perception (free text → events
as a convenience over the grammar). The blind-judge harness remains offline analysis.

## 7. Measurement — what the trace is read for

All analysis reads the society trace, never live objects. Metric families, game-framed:

- **Routine adherence** (% of waking ticks on schedule/engaged) — high is good; this is
  a believability target, not a rigidity bug.
- **Incident statistics** — rate per day (corridor target, e.g. a handful, tuned at
  G0), clustering around causes vs. uniform firing, and **cascade budget**: depth/
  breadth/duration from provenance. The system is *meant* to be strongly damped; a good
  incident dies in 2–3 hops.
- **Variety under repetition** — distribution of responses to the Nth identical
  stimulus vs. the 1st (the anti–arrow-in-the-knee metric); action entropy per persona
  and cast (degeneracy detector — the automated form of the QA finding on degenerate
  command/help intensities).
- **Recovery & carryover** — time back to routine after an incident; grudge carryover
  (does day-2 morning measurably differ after a day-1 incident; grudge half-life
  estimation against the ~28–42 h constants).
- **Cost** — persona-ticks/second (the games argument).

**Baseline cast:** a deliberately fair control implementation (schedule automaton +
trigger-bark table, same schedule quality, same probes) runs the same 3 days
side-by-side. The comparison page/report shows engine vs. baseline on the metrics
above — the litmus philosophy aimed at the industry standard.

**Regression harness:** canonical 3-day protocols frozen like golden traces — impulse
(one public insult into a calm evening), step (a rainy day), control (nothing) — re-run
on every engine version; metric diffs reported. Findings land in a deficiency taxonomy
that maps to a next-step *type*: too chaotic → calibration/damping; too dead →
transducer gains or vocabulary gap; repetitive → history features/selector; amnesia or
implausible permanence → relation time constants/timescale; one-way social loops → the
declared spec extension.

Note: this platform is effectively the **D5 milestone's integration test** (closed-loop
boredom suppression against a reactive world, at scale). Findings about seek timeouts,
offer latency, and replenish rates feed that milestone directly.

## 8. Gates and workflow

Work proceeds strictly through gates; each ends in an AUDIT checkpoint where the user
reviews artifacts before the next stage is authorized.

| Gate | Question | Method | On failure |
|---|---|---|---|
| **G0 stability** | Does a 4–6 persona coupled inn settle, saturate at clamps, or limit-cycle after canonical probes? | Headless 3-day runs on the instrument; sweep transducer intensity × recovery on/off × catalog richness; inspect envelopes, clamp dwell, FFT of state traces | Saturation → recovery layer + world-side damping factor (world config, not engine calibration). Persistent oscillation → judged on believability; may be a feature |
| **G1 semantics** | Are the transducer table, witnessing policy, contention rule and catalog semantics right? | User audits the YAML + G0 traces + chronicles | Revise — it is data |
| **G2 parity** (only if/when a browser build is pursued) | Pyodide byte-identical to CPython? | Fixed 1,000-tick session, full-trace SHA-256 both interpreters | Server-backed fallback; the world layer is transport-agnostic |
| **G3 build-out** | Scope sign-off for CLI polish / viewer extension / public extraction | — | — |

G0 is also a harvest: its NPC-sourced exchanges are exported in the existing scenario
format and become the missing Wojsław-commands-Halgrim QA corpus.

**Milestones:** M-A instrument (compiler, presence, transducer+provenance, economy, inn
loop, session log, society trace, metrics skeleton) + the G0 experiment and report.
M-B G1 audit, corpus export, table revisions. M-C CLI stepper with discoverability +
chronicle. M-D viewer extension (day bands, night compression, relation-graph
snapshots, chronicle column) reusing the engine repo's demo viewer components.
M-E baseline cast + regression harness + canonical protocols frozen. M-F (optional,
post-G2) public extraction, Pyodide cockpit, equilibrium-engine.dev page.

Per-milestone register: keep a `registers/` YAML log (state, decisions, findings,
open questions) in the project's usual style; update it at every AUDIT.

## 9. Frozen decisions and the deferred list

**Frozen (change requires the user, in writing, here):** one-tick social latency; the
engine is consumed at a pinned tag through its public surface only; no LLM in the loop;
all behavior-shaping numbers live in `inn.yaml`; analysis reads only the trace;
deterministic contention tiebreak; nights simulated honestly. (The transducer's S3
declared gap was a frozen decision through G1; it is now CLOSED by the engine's Social
Event Mapper Pack — see §4.2.)

**Deferred, named, not in this build:** ~~symmetric social perception event types~~
(DONE — landed as the engine's Social Event Mapper Pack `0b7df59` and wired in M-B, §4.2);
`ActionSelection.target` as an explicit
trace field (touches the frozen trace shape — goes through spec + golden regeneration);
world states as engine citizens (GlobalState vocabulary generalization); incident
choreography (storm-off room changes); more rooms / economy beyond the pot; LLM
expression and free-text perception seams; formal coupled-system stability analysis
(linearizations + sparse coupling matrix + spectral radius — revisit if G0's empirical
answer is ambiguous).

## 10. Open decisions awaiting the user

1. Cast size and roster for the canonical inn (proposal: Wojsław, Halgrim, Cichy, Edda,
   Welf, +Lutek).
2. The incident-rate corridor G0 should tune toward (proposal: 2–6 incidents per
   3-day run under the impulse protocol).
3. Transduced-intensity shape confirmation: linear in selection potential, scaled by
   world attenuation, as world config.
4. Whether G0's stability check stays purely empirical or is paired with the formal
   linearized analysis from the start.

### G1 audit rulings (decided 2026-06-13, by the user, in writing)

Following the G1 semantic audit (`experiments/out/g0/G1_audit.md`):

- **DEC-1 (scarcity fork): TWO PROFILES.** Keep the current hearth config as
  `g0_stability_profile` (frozen, proven, the G0 golden). Add `game_semantic_profile`
  (Option B: frustration-only idle recovery, weaker fallback, scarcity restored) and make
  it the shipped game default. M-B must re-run the G0 sweep to recharacterize the corridor
  for the semantic profile.
- **DEC-2 (idle recovery):** `game_semantic_profile` uses PARTIAL recovery — frustration
  recovers when idle, stress/anger do not. `g0_stability_profile` keeps idle recovery fully
  off (unchanged).
- **DEC-3/4/5 (overrides): BLESSED as intended v1 semantics** — the outburst anger vent
  (−0.50), `reactive_window_ticks=1`, and the root/hop witnessing asymmetry (0.5 / 0.15).
  An engine finding is still filed for the outburst vent (the engine's `outburst` should
  vent its own anger).
- **S3 (transducer gap): KEEP as a declared gap for G1.** `refuse`/`cold_response`/`complain`
  ship mute; file an engine finding to add symmetric social-perception event types,
  co-designed with the engine's pride→insult-anger work (§9 deferred). Not a blocker for G1.

G1 semantics are signed off on this basis; M-B implements the two-profile split + the
semantic-profile sweep + the engine findings.
