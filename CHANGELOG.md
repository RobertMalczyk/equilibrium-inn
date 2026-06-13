# Changelog — equilibrium-inn

All notable changes to the inn's behavior-shaping configuration. Parameter
locations: `inn.yaml` (world config) and `inn/engine_surface.py` (engine pin).
The instrument code (`inn/*.py`, `experiments/*.py`) is described where a change
required new mechanics, not just data.

---

## [M-A] G0 stability — coupled inn brought into the incident corridor

**Goal:** gate G0 — does a 7-persona coupled inn settle, saturate, or
limit-cycle after a canonical insult? Target corridor: **4–10 incidents per
3-day impulse run** (user decision §10.2).

### Starting point (initial design, v1)

Engine pinned at commit **`0f90b5e`** (pre-burst main).

| Parameter | Initial value | Location |
|---|---|---|
| Transducer hop scale | `1.0` | `inn.yaml` transducer.intensity.scale |
| Floor policy | none — floor applied on **every** hop | (implicit) |
| `outburst` floor | `0.30` | transducer.rows.outburst |
| `hostile_action` floor | `0.50` | transducer.rows.hostile_action |
| Witness attenuation (all events) | `0.5` | witnessing.co_located_attenuation |
| Burst machinery | n/a (engine had none) | — |
| Idle recovery | engine default (on: stress/anger −0.010/tick) | — |
| Persona reaction params | engine calibrated defaults | — |

**Result at starting point:** total saturation. One public insult →
**~2000 incidents**, a single cascade of depth ~400, anger pinned at the
clamp for most of the run. **Every** swept cell (scale 0.5–2.0 × recovery
on/off × catalog richness) saturated; 0 cells reached the corridor.
Diagnosis: world-loop gain > 1 (intensity floors × witness fan-out), which no
swept axis could damp.

### Step 1 — engine pin bump + enable burst machinery

Bumped engine pin **`0f90b5e` → `3dcf4a3`** (the "burst & saturation" main).
The burst system ships dormant; enabled it for the whole cast via a new
`engine_overrides` block in `inn.yaml`, stacked on `timescale_overrides()`
through `make_persona_loader()` (`inn/loop.py`). Initial enabling values
(engine eval's `BURST_ON`/`LOOP2_ON` demo set):

```yaml
thresholds: {burst_enter.anger: 0.80, burst_enter.stress: 0.60,
             burst_exit: 0.30, burst_confirm_ticks: 2, theta_displace: 0.55}
burst_extinction: {anger: 0.02, stress: 0.02}
derived_weights: {urge_boredom: {stress: 0.60}}   # Loop-2 relief-seeking
```

**Result:** still saturated (impulse ~2100, depth grew to ~836). Worse:
**rain alone now ignited a full cascade** (step protocol 0 → ~1500 incidents)
because displaced discharge + the relief-seeking loop turned priming into
ignition. Extinction at 0.02/tick was far too weak to beat social re-injection.

### Steps 2–6 — damping iterations A–E (to reach the corridor)

Each change below is cumulative. Full narrative in `registers/m_a.yaml`.

**A. Witnessing + floors (pure `inn.yaml`).**
- `co_located_attenuation` `0.5 → 0.15`, then split (see C).
- Added `floor_policy: roots_only` to `transducer.intensity` (new mechanic in
  `inn/transducer.py` + `inn/config.py`): floors back only reactions to
  **external** events (probes/player); reaction-to-reaction hops carry pure
  `scale × score`, so cascades decay geometrically.
- Burst tuning: `theta_displace 0.55 → 0.75`, `burst_extinction 0.02 → 0.10`.
- *Outcome:* DEAD inn (0 incidents). Discovery: the probe's direct target
  (Halgrim) answers `cold_response` — a **declared gap** that emits nothing —
  so ignition is always **witness-borne**; weak witnessing killed it entirely.

**B. Asymmetric witnessing.** Root events (probes/player) hit witnesses at
`0.5`; reaction hops at `0.15`. Split kept the dramatic stranger-scene while
damping internal hops. *Outcome:* rain/control clean, impulse still ~1780.

**C. Cooldowns (dead end) + latch thresholds.** Set `outburst`/`hostile_action`
`cooldown: 15` — **no effect** (engine lets reactive actions bypass cooldowns
by design). Lowered latch entry `burst_enter.anger 0.80 → 0.70`,
`burst_enter.stress 0.60 → 0.40` so the latch actually trips during fights;
`burst_extinction 0.10 → 0.15`.

**D. The two decisive changes.**
- `reactive_window_ticks: 1` — reactions answer only a **fresh** provocation
  (also added an expiring `_last_prov` in `inn/loop.py` so a reaction is never
  attributed to a stale/cross-night provocation).
- **Outbursts now VENT**: `outburst.post_effects.global.anger: -0.50`. The
  engine default discharged *no* anger (booked only target resentment), so
  anger stayed pinned and re-fired forever. This is the single load-bearing
  change — with it, hop scale finally has authority.

**E. Scale landscape mapped.** Hop scale is sharply **non-monotonic**:
`≤ 0.70` stable (~2 incidents), `≥ 0.75` chaotic (100–2000). No corridor via
scale alone while idle recovery was on.

### Final canonical configuration (in corridor)

| Parameter | Final value | Change from start |
|---|---|---|
| Engine pin | `3dcf4a3` | ← `0f90b5e` |
| Transducer hop scale | **`0.5`** | ← `1.0` |
| Floor policy | **`roots_only`** | ← floor on every hop (new mechanic) |
| `outburst` / `hostile_action` floor | `0.30` / `0.50` | unchanged (now roots-only) |
| Witness attenuation — root events | `0.5` | unchanged |
| Witness attenuation — reaction hops | **`0.15`** | ← `0.5` |
| `outburst` anger vent (post_effect) | **`-0.50`** | ← `0` (engine default) |
| `reactive_window_ticks` | **`1`** | ← engine calibrated default (wider) |
| `burst_enter.anger` / `.stress` | **`0.70` / `0.40`** | ← `0.80` / `0.60` |
| `burst_exit` / `burst_confirm_ticks` | `0.30` / `2` | (burst demo defaults) |
| `theta_displace` | **`0.75`** | ← `0.55` |
| `burst_extinction` (anger, stress) | **`0.15`** each | ← `0.02` |
| `derived_weights.urge_boredom.stress` | `0.60` | (Loop-2, enabled) |
| Idle recovery (stress, anger) | **`0.0`** (off) | ← engine default −0.010/tick |
| G0 sweep `transducer_scale` axis | `[0.4, 0.45, 0.5, 0.55, 0.6]` | ← `[0.5, 0.75, 1.0, 1.5, 2.0]` |
| G0 sweep `recovery` axis meaning | `false`=canonical, `true`=restore default | semantics flipped |

**Result:** canonical cell (`s0.5_roff_normal`) = **10 incidents / 3-day
impulse, 6 cascades, max depth 3, verdict "settles".** Day-1 insult → 3
hotheads flare and it dies in ≤3 hops; day-1 grudge resurfaces as shallow
pre-lunch flares on days 2–3. Control = 0 incidents in all 30 cells. 9/30 cells
in corridor (all recovery-off, normal+rich catalog). Thin catalog destabilizes
at scale ≥ 0.55 (225–472 incidents) — scarcity instability, by design.
Formal: provoked ρ(A) ≈ 1.006 (near-critical; bounded by the nonlinear
vent/latch machinery, not by linear stability).

### Supporting code changes (not behavior parameters)

- `inn/transducer.py`, `inn/config.py`: `floor_policy` (all | roots_only).
- `inn/loop.py`: `make_persona_loader()` stacks `engine_overrides`; expiring
  `_last_prov` provocation attribution.
- `experiments/g0_sweep.py`: recovery axis now toggles engine default recovery
  back **on**; `limit_cycles` verdict re-defined as incident count > 3× corridor
  (the inn's designed daily meal/sleep rhythm makes raw FFT day-periodicity a
  false positive).
- Golden canonical-session hash re-baselined at each config change
  (`python -m experiments.regen_golden`).

### Open audit items for G1 (unverified design values)

1. Idle recovery disabled inn-wide — reverses the engine's D10/D11 fix in this
   context. Alternative: recovery on + corridor revised to ~2 incidents.
2. `outburst` anger vent `-0.50` is inn-authored; engine calibration does not
   own it — file as engine finding.
3. `reactive_window_ticks: 1` adopted from the engine burst eval, not from
   calibrated defaults.
4. Root-vs-hop witnessing asymmetry (`0.5` vs `0.15`) is new world semantics;
   G1 should bless or revise the transducer table.

### Thin-catalog hardening + chronicle (2026-06-13)

- **Hearth fallback** (`inn.yaml` activities: `hearth_idle`). The thin-catalog
  limit cycles (2 cells at 225/472 incidents) were a *frustration ratchet*: with
  idle recovery off, a starved evening catalog pinned frustration at 1.0 with no
  relief, leaving the room permanently primed by day 3. A high-capacity
  always-present indoor occupation caps the ratchet. **Result: all 30 cells
  settle** (was 28); 11 in corridor; worst clamp dwell 0.00. Golden re-baselined.
  - **Trade-off finding**: the hearth also neutralizes scarcity (thin ≈ normal ≈
    rich). Documented in `registers/m_a.yaml` with **Option B** (frustration-only
    idle recovery) — preserves a thin>rich gradient but recenters the corridor.
    Left as a G1 decision; not committed.
- **Chronicle renderer** (`experiments/chronicle.py`): renders a society trace as
  observable prose + per-incident why-chains (text form of the CLI `why <name>`),
  reusing the engine's de-biased narration vocabulary. Wired into `g0_report.py`;
  written to `<canonical>/chronicle.md` as the G1 believability artifact.

### Report generator: data-derived findings

`g0_report.py` previously emitted hardcoded "FINDING" prose from the
saturating-era config (floors 0.30/0.50 every hop, witnesses 0.5), which went
stale once the config changed. Replaced with `_summary_findings()`, which
derives the summary from the sweep results themselves (verdict counts, corridor
hits, recovery-axis effect, scarcity instability, scale landscape). The report
now tracks the config automatically instead of asserting a fixed conclusion.
