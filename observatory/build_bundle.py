"""Build the Living Inn Observatory Pyodide cockpit (CLAUDE.md M-D, PRIMARY).

Produces, under observatory/:
  * inn_bundle.zip — the inn package + the PINNED engine subset + inn.yaml,
    plus a `.engine_commit` sentinel (the real git rev-parse at bundle time), so
    the page can import and run the inn in-browser via Pyodide.
  * index.html     — the cockpit: the SHARED render layer (inn.observatory
    STYLE/BODY/SCRIPT) + a Pyodide bootstrap that runs the inn live and builds
    the ObservationModel with inn.observe — same code path as CPython.

HARD RULE 0.1: this reads the engine checkout READ-ONLY. It copies engine files
into the bundle staging dir; it NEVER writes into equilibrium-engine/. The
`.engine_commit` sentinel is written into the bundle copy only.

Usage: python observatory/build_bundle.py
Then serve over http (fetch needs it): python -m http.server -d observatory
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

# Make the script runnable from the repo root with no PYTHONPATH / editable install:
# put the repo root on sys.path BEFORE importing inn.* (and so `experiments` /
# `observatory` resolve too). Must precede the inn imports below.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import inn.observatory as OB  # noqa: E402  (import after sys.path setup, by design)
from inn.engine_surface import ENGINE_ROOT, verify_pin  # noqa: E402

HERE = ROOT / "observatory"
STAGE = HERE / "_stage"
ENGINE_SUBDIRS = ("engine", "eval", "data", "calibration")
PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/"
# M-F (self-hosted cockpit): if a Pyodide distribution is dropped into
# observatory/pyodide/ (download the v0.26.2 "full" build there), the cockpit uses
# it instead of the CDN — fully offline. Not vendored here (it is tens of MB).
PYODIDE_LOCAL = HERE / "pyodide"


def _pyodide_base() -> str:
    return "pyodide/" if (PYODIDE_LOCAL / "pyodide.js").is_file() else PYODIDE_CDN


def _copy_engine(stage_engine: Path) -> None:
    """Copy only the engine subset the inn needs at runtime (read-only)."""
    for sub in ENGINE_SUBDIRS:
        src = ENGINE_ROOT / sub
        if src.is_dir():
            shutil.copytree(src, stage_engine / sub,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                          "tests", ".git"))


def build_bundle() -> Path:
    commit = verify_pin()  # READ-ONLY: confirms the pin, returns the SHA
    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "equilibrium-engine").mkdir(parents=True)
    # inn package + config
    shutil.copytree(ROOT / "inn", STAGE / "inn",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "inn.yaml", STAGE / "inn.yaml")
    # pinned engine subset + commit sentinel (bundle copy only)
    _copy_engine(STAGE / "equilibrium-engine")
    (STAGE / "equilibrium-engine" / ".engine_commit").write_text(commit, encoding="utf-8")

    zip_path = HERE / "inn_bundle.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(STAGE).as_posix())
    shutil.rmtree(STAGE)
    return zip_path


# -- the cockpit page (shared render layer + Pyodide bootstrap) ----------------

CONTROLS_AND_BOOT = r"""
<script src="__PYODIDE__pyodide.js"></script>
<script>
const PROFILES=["game_semantic_profile","g0_stability_profile"];
const PLANS=["impulse","step","control"];
const PROFILE_DESC={
  game_semantic_profile:"shipped default — partial idle recovery + restored scarcity",
  g0_stability_profile:"the frozen, hearth-stable G0 baseline (no idle recovery)"};
const PLAN_DESC={
  impulse:"one public insult into a calm evening (day 1, 20:00)",
  step:"a rainy day 2 (outdoor work closes; stress rises)",
  control:"nothing scripted — the calm baseline"};
const ADV_STEP=30;   // "Advance ▶" step (~1 in-world hour)
let PY=null, LIVE=null, PALETTE=[];
function setStatus(t){const s=document.getElementById('c_status'); if(s)s.textContent=t;}
function profileVal(){return (document.getElementById('c_profile')||{}).value||'game_semantic_profile';}
function planVal(){return (document.getElementById('c_plan')||{}).value||'control';}
function seedVal(){return parseInt((document.getElementById('c_seed')||{}).value||'7',10);}
function burstVal(){return !!(document.getElementById('c_burst')||{}).checked;}
function resVal(){return parseFloat((document.getElementById('c_res')||{}).value||'1');}
function speedVal(){return parseFloat((document.getElementById('c_speed')||{}).value||'1');}

// ---- M-I LIVE-FRONTIER cockpit ------------------------------------------------
// The observer influences the world ONLY at the live frontier (the latest computed
// tick); the future then emerges from that new state. No future-queue: an action
// is validated against the live state at execution time and applied at the
// frontier tick, then the sim advances. All the driving logic is the Python
// inn.live.LiveSession (the SAME class the tests pin); JS only orchestrates calls.
function liveInfo(){try{return JSON.parse(LIVE.frontier_info());}catch(e){return {};}}
function livePresent(){try{return LIVE.present_with().toJs();}catch(e){return [];}}
function liveEngineWould(){try{return LIVE.engine_would();}catch(e){return 'neutral';}}
function ivActionLabel(v){return (v==='observe'||v==='noop')
  ?fmt(v)+' (stay silent)':fmt(v);}

function buildLiveConsole(){
  const box=document.getElementById('intvconsole'); if(!box||!window.MODEL)return;
  const cast=window.MODEL.cast||[], nm=id=>(window.MODEL.display_names||{})[id]||id;
  const info=liveInfo();
  const castOpts=['<option value="">— none (observe) —</option>'].concat(
    cast.map(p=>`<option value="${p}"${p===info.subject?' selected':''}>${nm(p)}</option>`)).join('');
  const palOpts=PALETTE.map(v=>`<option value="${v}">${ivActionLabel(v)}</option>`).join('');
  box.innerHTML=`<label title="Take control of one cast member at the live frontier. The engine still computes their full interior.">Controlled subject <select id="iv_subj">${castOpts}</select></label>
    <label title="AUTO: the engine drives. MANUAL: your action replaces the outward action at the frontier (silent on ticks you don't act).">Mode <select id="iv_mode"><option value="auto"${info.mode!=='manual'?' selected':''}>AUTO — observe</option><option value="manual"${info.mode==='manual'?' selected':''}>MANUAL — you act</option></select></label>
    <label title="The outward action — finite, engine-compatible palette.">Manual intervention <select id="iv_action">${palOpts}</select></label>
    <label title="Valid targets only — cast co-located with the subject at the live frontier.">Target <select id="iv_target"></select></label>
    <button id="iv_apply" title="Route this action through the normal world path at the live frontier, then advance.">Apply intervention</button>
    <label title="How many ticks the live simulation advances right after your action, so the world can respond (8 ticks ≈ 16 min).">then advance <input id="iv_advn" type="number" min="1" max="120" value="8" style="width:52px"> ticks</label>
    <button id="iv_adv" title="Advance the live simulation ~1 in-world hour without acting.">Advance 1 h ▶</button>
    <button id="iv_suggest" title="What the engine would do for this subject (read-only).">Engine would…</button>
    <button id="iv_start" title="Start (or restart) a live-frontier session controlling this subject from a mid-run frontier.">Start live intervention</button>
    <button id="iv_return" style="display:none" title="Jump the playhead back to the live frontier to intervene.">⟲ Return to live frontier</button>
    <button id="iv_dump" title="Download a lossless scenario file (profile/protocol/seed/advanced-outburst + every manual override) — inputs only, no results. Replay it later to reproduce this exact run and debug it: python -m inn.scenario replay scenario.json -o out">⤓ Dump scenario</button>
    <div style="flex-basis:100%" id="iv_live" class="sub"></div>
    <div style="flex-basis:100%" id="iv_hint" class="sub"></div>`;
  const $i=id=>document.getElementById(id);
  const subjRoom=()=>{const t=window.MODEL.ticks[window.FRONTIER||0]||window.MODEL.ticks[window.MODEL.ticks.length-1]||{};
    return fmt(((t.personas||{})[info.subject]||{}).room||'their room');};
  const refreshTargets=()=>{
    const present=livePresent();
    const pe=((window.MODEL.intervention_ui||{}).palette||[]).find(e=>e.verb===$i('iv_action').value)||{needs_target:true};
    $i('iv_target').innerHTML=(pe.needs_target?'':'<option value="">(no target)</option>')
      +present.map(p=>`<option value="${p}">${nm(p)}</option>`).join('');
    if(pe.needs_target&&!present.length)$i('iv_hint').textContent=
      info.subject
        ?`No valid target: ${nm(info.subject)} is alone in the ${subjRoom()}. Advance until someone enters the same room (or pick a no-target action like observe).`
        :`Pick a controlled subject first, then a co-located target.`;
    else $i('iv_hint').textContent='';};
  $i('iv_subj').onchange=()=>{const v=$i('iv_subj').value;
    if(v)LIVE.take_control(v,$i('iv_mode').value); else LIVE.release();
    setStatus('live · frontier'+(v?(' · controlling '+nm(v)):''));};
  $i('iv_mode').onchange=()=>{const v=$i('iv_subj').value;
    if(v)LIVE.take_control(v,$i('iv_mode').value); else LIVE.set_mode($i('iv_mode').value);};
  $i('iv_action').onchange=refreshTargets;
  $i('iv_start').onclick=()=>liveStart($i('iv_subj').value,$i('iv_mode').value,0);
  $i('iv_suggest').onclick=()=>{$i('iv_hint').innerHTML=
    `Engine would select for ${nm(info.subject||'the subject')}: <b>${fmt(liveEngineWould()||'neutral')}</b> `
    +`<span class="sub">— read-only, what the autonomous NPC would do. Not forced.</span>`;};
  $i('iv_apply').onclick=()=>doIntervene($i('iv_action').value,$i('iv_target').value||null,
    parseInt(($i('iv_advn')||{}).value||'8',10));
  $i('iv_adv').onclick=()=>liveAdvance(ADV_STEP);
  $i('iv_return').onclick=()=>{frame=window.FRONTIER||0;
    const sc=$('scrub'); if(sc)sc.value=frame; render();};
  $i('iv_dump').onclick=()=>dumpScenario();
  refreshTargets(); if(window.afterRender)window.afterRender();
}
// Enable/disable the controls by frontier vs history — called after every render
// (window.afterRender), so scrubbing into the past disables intervention.
function updateLiveControls(){
  if(!window.LIVE_ACTIVE||!document.getElementById('iv_subj'))return;
  const nm=id=>(window.MODEL.display_names||{})[id]||id;
  const atFrontier=frame>=(window.FRONTIER||0), info=liveInfo();
  // Always available (they reconfigure / restart the session, not act on the
  // current frontier): subject, mode, Start live session.
  // Disabled while reviewing history (they act on the live frontier): action,
  // target, Engine would…, Apply, Advance.
  ['iv_action','iv_target','iv_suggest','iv_apply','iv_adv']
    .forEach(id=>{const e=document.getElementById(id); if(e)e.disabled=!atFrontier;});
  ['iv_subj','iv_mode','iv_start']
    .forEach(id=>{const e=document.getElementById(id); if(e)e.disabled=false;});
  const ret=document.getElementById('iv_return'); if(ret)ret.style.display=atFrontier?'none':'inline-block';
  const apply=document.getElementById('iv_apply');
  if(apply&&atFrontier)apply.disabled=!!info.at_end||info.mode!=='manual'||!info.subject;
  const adv=document.getElementById('iv_adv'); if(adv&&atFrontier)adv.disabled=!!info.at_end;
  const live=document.getElementById('iv_live'); if(!live)return;
  const tk=window.MODEL.ticks[frame]||{};
  // a slim teal progress bar: how much of the 3 days the live frontier has reached.
  const pct=info.total?Math.round(100*(info.frontier||0)/info.total):0;
  const bar=`<div class="frontwrap"><div class="frontbar"><span style="width:${pct}%"></span></div>`
    +`<span class="frontpct">${pct}% of the simulation computed</span></div>`;
  // An impossible-to-miss state tag: live (interventions enabled) vs history (disabled).
  if(!atFrontier){
    live.innerHTML=`<span class="statetag hist">REVIEWING HISTORY — interventions disabled</span>`
      +`<div class="livehint">Viewing day ${tk.day} ${tk.clock} (before the live frontier). `
      +`Use <b>⟲ Return to live frontier</b> to intervene again.</div>`+bar;}
  else if(info.at_end){
    live.innerHTML=`<span class="statetag end">END OF RUN — all ${info.total} ticks computed</span>`
      +`<div class="livehint">Scrub to review, or <b>Start live intervention</b> to drive a fresh mid-run frontier.</div>`+bar;}
  else{
    live.innerHTML=`<span class="statetag live">LIVE FRONTIER — interventions enabled</span>`
      +` <span class="sub">day ${tk.day} ${tk.clock}</span>`+bar
      +`<div class="livehint">The first ~2 hours are seeded so there is a scene to act on. `
      +`The remaining simulation will unfold from your interventions. `
      +(info.subject?(info.mode==='manual'
          ?`<b>Manual mode holds ${nm(info.subject)}'s outward action unless you act. `
            +`Switch to AUTO to let the engine drive again.</b> `
            +`Pick an action + target and <b>Apply intervention</b>, or <b>Advance 1 h ▶</b>.`
          :`AUTO lets the engine drive ${nm(info.subject)}; switch to <b>MANUAL</b> to intervene, or <b>Advance 1 h ▶</b>.`)
        :`Pick a <b>controlled subject</b> to intervene, or <b>Advance 1 h ▶</b> to watch.`)
      +`</div>`;}
}
async function liveStart(subject,mode,initial){
  if(!PY){setStatus('still booting…');return;}
  setStatus('starting live intervention…'); await new Promise(r=>setTimeout(r,20));
  try{ await PY.globals.get('live_start')(profileVal(),planVal(),seedVal(),
        subject||'',mode||'auto',initial,burstVal(),resVal());
    setStatus('live · frontier'+(subject?(' · controlling '+subject):''));
  }catch(e){console.error(e); setStatus('live start failed: '+e);}
}
async function liveAdvance(n){
  if(!LIVE){setStatus('still booting…');return;}
  setStatus('advancing…'); await new Promise(r=>setTimeout(r,10));
  try{ await PY.globals.get('live_advance')(n); setStatus('live · frontier'); }
  catch(e){console.error(e); setStatus('advance failed: '+e);}
}
async function doIntervene(verb,target,adv){
  if(!LIVE)return;
  setStatus('intervening at the frontier…'); await new Promise(r=>setTimeout(r,10));
  try{ const err=await PY.globals.get('live_intervene')(verb,target||'',adv||8);
    if(err){const h=document.getElementById('iv_hint'); if(h)h.textContent=err;
      setStatus('live · frontier');}
    else setStatus('live · intervention applied');
  }catch(e){console.error(e); setStatus('intervention failed: '+e);}
}
async function dumpScenario(){
  if(!PY||!SESS_READY()){setStatus('still booting…');return;}
  setStatus('dumping scenario…');
  try{
    const json=await PY.globals.get('scenario_json')();
    const info=liveInfo();
    const fn=`scenario_${profileVal()}_${planVal()}_seed${seedVal()}`
      +(info.subject?('_'+info.subject):'')+'.json';
    const blob=new Blob([json],{type:'application/json'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob); a.download=fn; document.body.appendChild(a);
    a.click(); a.remove(); URL.revokeObjectURL(a.href);
    setStatus('scenario downloaded — replay: python -m inn.scenario replay '+fn+' -o out');
  }catch(e){console.error(e); setStatus('dump failed: '+e);}
}
function SESS_READY(){try{return !!liveInfo().total;}catch(e){return false;}}
function opts(arr,desc){return arr.map(p=>`<option title="${desc[p]||''}">${p}</option>`).join('');}
function buildControls(){
  const c=document.getElementById('controls'); c.style.display='flex';
  c.innerHTML=`<label title="The inn's character — which behavioural profile the cast runs under.">profile <select id="c_profile">${opts(PROFILES,PROFILE_DESC)}</select></label>
    <label title="What gets injected into the run — the canonical probe protocol.">protocol <select id="c_plan">${opts(PLANS,PLAN_DESC)}</select></label>
    <label title="Deterministic RNG seed. Same profile + protocol + seed → byte-identical run.">seed <input id="c_seed" type="number" value="7" style="width:64px"></label>
    <label title="Advanced/experimental: flip the engine's calibrated burst overlay (latch/escalation/extinction) ON. Ships OFF — in the coupled 7-NPC room it can amplify to runaway (see M-B). For experiments only; recorded in the scenario so it stays reproducible.">advanced outburst <input id="c_burst" type="checkbox"></label>
    <label title="Tick resolution: finer dt = more ticks for the same 3 days = smoother plots. The real-time trajectory is preserved (engine resolution_factor). 120s = canonical (byte-identical); finer dt is a new operating point. Heavier (8x ticks at 15s).">resolution <select id="c_res"><option value="1">120 s (canonical)</option><option value="4">30 s</option><option value="8">15 s</option></select></label>
    <label title="Playback speed. 1x = real-time (one tick per dt real-seconds); higher = faster. At the 120s default even 20x is slow, so high multipliers (up to 200x) make play watchable; at finer dt lower ones suffice. Preserves the 3 game-days as the unit being traversed. Playback only — no effect on dynamics.">speed <select id="c_speed"><option value="1">1x</option><option value="2">2x</option><option value="4">4x</option><option value="8">8x</option><option value="20">20x</option><option value="50">50x</option><option value="100">100x</option><option value="200" selected>200x</option><option value="500">500x</option><option value="750">750x</option><option value="1000">1000x</option><option value="2000">2000x</option></select></label>
    <button id="c_run" disabled title="Compute the full 3-day, 7-NPC autonomous run in-browser and review it (read-only history). To intervene, use Start live intervention below.">Review autonomous run</button>
    <span class="grow"></span>
    <button id="c_parity" disabled title="Run the fixed G2 session (control · seed 7 · 1000 ticks) in-browser and compare its trace SHA-256 to the CPython reference. Closes the G2 parity gate when it matches.">Verify parity</button>
    <span id="p_status" class="sub">parity: idle</span>
    <span id="c_status" class="sub">booting Pyodide…</span>
    <div id="c_help" style="flex-basis:100%;font-size:12px;color:var(--muted);line-height:1.5"></div>
    <div id="p_detail" style="flex-basis:100%;font-size:12px;color:var(--muted)"></div>`;
  document.getElementById('c_run').onclick=()=>doRun();
  document.getElementById('c_parity').onclick=()=>verifyParity();
  const refresh=()=>{const pf=document.getElementById('c_profile').value,
    pl=document.getElementById('c_plan').value;
    document.getElementById('c_help').innerHTML=
      `<b>profile</b> ${pf}: ${PROFILE_DESC[pf]} · <b>protocol</b> ${pl}: ${PLAN_DESC[pl]} `
      +`· <b>seed</b>: deterministic — same settings reproduce the same run. `
      +`<b>Review autonomous run</b> computes the whole run to review (read-only); `
      +`<b>Start live intervention</b> (below) drives a live frontier you can intervene at; `
      +`<b>Verify parity</b> checks Pyodide matches CPython.`;};
  document.getElementById('c_profile').onchange=refresh;
  document.getElementById('c_plan').onchange=refresh;
  // M-K: the speed selector drives the shared real-time playback loop live.
  window.PLAY_SPEED=speedVal();
  document.getElementById('c_speed').onchange=()=>{window.PLAY_SPEED=speedVal();};
  refresh();
}
function pstat(t,color){const s=document.getElementById('p_status');
  if(s){s.textContent='parity: '+t; s.style.color=color||'';}}
async function verifyParity(){
  if(!PY){pstat('still booting…');return;}
  pstat('running…','#9a6a16');
  document.getElementById('p_detail').textContent='';
  try{
    const ref=await (await fetch('g2_reference.json')).json();
    await new Promise(r=>setTimeout(r,20));
    const actual=await PY.globals.get("run_parity")(ref.seed, ref.n_ticks);
    const ok=actual===ref.trace_sha256;
    pstat(ok?'passed ✅':'failed ❌', ok?'#3a7d2c':'#b5532e');
    document.getElementById('p_detail').innerHTML=
      (ok?'✅ CPython and Pyodide outputs match — live mode blessed.'
        :'❌ mismatch; the static export remains the blessed path.')+
      `<br>expected SHA: <code>${ref.trace_sha256}</code><br>actual&nbsp;&nbsp;SHA: <code>${actual}</code>`;
  }catch(e){console.error(e); pstat('error ⚠️','#b5532e');
    document.getElementById('p_detail').textContent='⚠️ error running parity check: '+e;}
}
// Re-render after a live advance/intervention WITHOUT resetting the user's
// selection: regrow the scrubber, follow the frontier, rebuild ribbons/console.
// Python calls this (js.liveRefresh) after each frontier change.
function liveRefresh(){
  const sc=$('scrub'); if(sc)sc.max=MODEL.ticks.length-1;
  window.FRONTIER=MODEL.ticks.length-1;
  frame=MODEL.ticks.length-1;            // follow the live frontier
  if(sc)sc.value=frame;
  renderCycle(); buildRibbons(); render(); buildLiveConsole(); renderPlotsLive();
}
// M-J: render the Time Plots panel from the live trace (same shared render layer
// as the static plots.html). keepView after the first render so advancing the
// frontier doesn't reset the observer's zoom window.
function renderPlotsLive(){
  if(!window.TPMODEL||!window.TimePlots)return;
  // The Time Plots tab is a sibling view; its canvases size to 0 while hidden,
  // so only draw when the tab is visible (tab switch re-calls this).
  const v=document.getElementById('view_plots');
  if(!v||v.style.display==='none')return;
  try{window.TimePlots.render(window.TPMODEL,{keepView:!!window._tpInit});
    window._tpInit=true;}catch(e){console.error('time plots:',e);}
}
// Subpage switch between the Observatory and the live Time Plots (same session).
function tpShowView(which){
  const obs=document.getElementById('view_obs'), pl=document.getElementById('view_plots');
  if(!obs||!pl)return; const onPlots=which==='plots';
  obs.style.display=onPlots?'none':''; pl.style.display=onPlots?'':'none';
  const tb=document.getElementById('tab_obs'), tp=document.getElementById('tab_plots');
  if(tb)tb.classList.toggle('on',!onPlots); if(tp)tp.classList.toggle('on',onPlots);
  if(onPlots)renderPlotsLive();
}
function wireTabs(){const tb=document.getElementById('tab_obs'),tp=document.getElementById('tab_plots');
  if(tb)tb.onclick=()=>tpShowView('obs'); if(tp)tp.onclick=()=>tpShowView('plots');}
// "Review autonomous run": one autonomous live session advanced to the end, then
// reviewed read-only (history scrubber). Intervention happens via Start live
// intervention, which leaves a mid-run frontier to act on.
async function doRun(){
  window.afterRender=updateLiveControls;
  await liveStart('', 'auto', 1000000000);   // advance_all (clamped to run length)
}
async function boot(){
  buildControls(); wireTabs();
  try{
    PY=await loadPyodide({indexURL:"__PYODIDE__"});
    setStatus('installing packages…');
    await PY.loadPackage(["micropip","numpy"]);  // engine.stability needs numpy
    setStatus('loading the inn…');
    await PY.runPythonAsync(`
import micropip
await micropip.install("pyyaml")
from pyodide.http import pyfetch
import io, os, sys, json, zipfile
resp = await pyfetch("inn_bundle.zip")
zipfile.ZipFile(io.BytesIO(await resp.bytes())).extractall(".")
root = os.getcwd()
if root not in sys.path: sys.path.insert(0, root)
from inn.config import load_inn_config
from inn.live import LiveSession
import inn.observe as O
import inn.timeplots as TP
import js
CFG = load_inn_config("inn.yaml")
# M-I live-frontier: ONE persistent session. The observer acts only at the live
# frontier (inn.live.LiveSession — the same class the CPython tests pin); the
# future emerges from that new state. No future-queue.
SESS = {"s": None}
def _emit(first=False):
    s = SESS["s"]
    model = O.build_model(s.records, CFG, meta={"subtitle":"live · cockpit"}, stride=1)
    js.window.MODEL = js.JSON.parse(json.dumps(model))
    js.window.LIVE_ACTIVE = True
    js.window.CONTROLLED = s.subject
    js.window.CONTROL_MODE = s.mode
    # M-J: the SAME render layer as the static plots.html, fed the live trace.
    # Observability only — reads s.records, never re-runs/changes the sim.
    pm = TP.build_plot_model(s.records, CFG, dt=float(s.loop.clock.dt),
                             meta={"subtitle":"live · cockpit"})
    pm["__root"] = "#tpc"
    js.window.TPMODEL = js.JSON.parse(json.dumps(pm))
    js.window.PLAY_DT = float(s.loop.clock.dt)   # M-K: seconds/tick for real-time playback
    if first: js.init()       # one-time wiring (scrub/play/dev handlers)
    js.liveRefresh()          # follow the frontier + (re)build the live console
def live_start(profile, plan, seed, subject, mode, initial, burst=False, resolution=1.0):
    # M-K: resolution refines dt; total ticks derive from the refined clock so the
    # 3 game-days hold. SEED_TICKS (~2 h of day 1) is computed from the refined day.
    SESS["s"] = LiveSession(CFG, profile, plan, int(seed), None,
                            subject=(subject or None), mode=(mode or "auto"),
                            burst_overlay=bool(burst),
                            resolution_factor=float(resolution))
    day = SESS["s"].loop.clock.day_ticks
    init = int(initial)
    init = (2*max(1, round(day/24)) if init <= 0 else init)
    SESS["s"].advance(init)
    _emit(first=True)
def scenario_json():
    # lossless, input-only dump of the live session (CLAUDE.md M-J). inn.yaml is at
    # CWD in the bundle, so dump_scenario can embed it.
    return json.dumps(SESS["s"].dump_scenario("inn.yaml"), indent=2)
def live_advance(n):
    SESS["s"].advance(int(n)); _emit()
def live_take_control(subject, mode):
    SESS["s"].take_control(subject or None, mode or "manual"); _emit()
def live_release():
    SESS["s"].release(); _emit()
def live_set_mode(mode):
    SESS["s"].set_mode(mode or "auto"); _emit()
def live_intervene(verb, target, adv=8):
    # Validates against the live frontier at EXECUTION time; applies at the
    # frontier tick; advances adv ticks so the world responds. Returns "" or err.
    err = SESS["s"].intervene(verb, target or None, advance=int(adv))
    _emit(); return err or ""
def live_present_with():
    return list(SESS["s"].present_with())
def live_engine_would():
    return SESS["s"].engine_would() or "neutral"
def live_frontier_info():
    s = SESS["s"]
    return json.dumps({"frontier": s.frontier, "total": s.total,
                       "at_end": s.at_end(), "subject": s.subject, "mode": s.mode})
def run_parity(seed, n):
    # Fixed G2 session, identical params to experiments.g2_parity; returns the
    # full-trace SHA-256 (TraceWriter.close()) for in-browser parity comparison.
    from inn.session import run_session
    import tempfile
    h = run_session(CFG, "control", tempfile.mkdtemp(), seed=int(seed),
                    n_ticks=int(n), profile="game_semantic_profile")
    return h["trace_sha256"]
def palette_verbs():
    from inn.intervention import PALETTE_VERBS
    return list(PALETTE_VERBS)
`);
    LIVE={frontier_info:()=>PY.globals.get("live_frontier_info")(),
          present_with:()=>PY.globals.get("live_present_with")(),
          engine_would:()=>PY.globals.get("live_engine_would")(),
          take_control:(s,m)=>PY.globals.get("live_take_control")(s,m),
          release:()=>PY.globals.get("live_release")(),
          set_mode:(m)=>PY.globals.get("live_set_mode")(m)};
    PALETTE=PY.globals.get("palette_verbs")().toJs();
    window.afterRender=updateLiveControls;
    window.IS_COCKPIT=true;
    const btn=document.getElementById('c_run'); if(btn)btn.disabled=false;
    const pbtn=document.getElementById('c_parity'); if(pbtn)pbtn.disabled=false;
    setStatus('ready — running first simulation…');
    await doRun();
  }catch(e){console.error(e); setStatus('boot failed: '+e+' (see console)');}
}
boot();
</script>
"""


def build_index() -> Path:
    import json
    import inn.timeplots as TP
    boot = CONTROLS_AND_BOOT.replace("__PYODIDE__", _pyodide_base())
    assets = OB.load_assets()  # embed the same asset pack as the static export
    adata = json.dumps(assets, ensure_ascii=False)
    # M-J: the cockpit is two subpages of the SAME live session — the Observatory
    # and the live Time Plots — switched by a sticky tab bar (tpShowView in the
    # boot script). The Time Plots view renders the shared layer from window.TPMODEL
    # (built each frontier change from the live trace). Observability only.
    tabnav = (
        "<div class='tabnav'>"
        "<button id='tab_obs' class='on'>Observatory</button>"
        "<button id='tab_plots'>Time plots</button>"
        "<span class='tabnote'>two views of the same live run</span></div>"
    )
    plots_view = (
        "<div class='wrap' id='view_plots' style='display:none'>"
        "<div class='hero'><div>"
        "<h1>Time plots — live engine dynamics</h1>"
        "<div class='tag'>Interior-state trajectories of the run you are watching "
        "on the Observatory tab.</div>"
        "<span class='pill'>fast affect spikes &amp; vents · slow relational marks · "
        "incidents as the spine</span></div></div>"
        + TP.plot_body("tpc", with_selector=False) + "</div>"
    )
    tabcss = (".tabnav{position:sticky;top:0;z-index:20;display:flex;align-items:center;"
              "gap:8px;padding:8px 22px;background:rgba(243,233,210,.92);"
              "backdrop-filter:saturate(1.1);border-bottom:1px solid var(--line)}"
              ".tabnav .tabnote{color:var(--muted);font-size:12px;font-style:italic;margin-left:6px}")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<link rel='icon' href='data:,'>"  # suppress the browser favicon request (no 404)
        "<title>Living Inn Observatory — live</title>"
        "<style>" + OB.STYLE + TP.PLOT_STYLE + tabcss + "</style>"
        "<style>" + OB._asset_css(assets) + "</style></head>"
        "<body>" + tabnav + "<div id='view_obs'>" + OB.BODY + "</div>" + plots_view +
        "<script>window.ASSETS=" + adata + ";</script>"
        "<script>" + OB.SCRIPT + "</script>"
        "<script>" + TP.PLOT_SCRIPT + "</script>" + boot +
        "</body></html>"
    )
    p = HERE / "index.html"
    p.write_text(html, encoding="utf-8")
    return p


def main() -> None:
    z = build_bundle()
    i = build_index()
    # Ensure the cockpit's "Verify parity" button has a reference to fetch.
    from experiments.g2_parity import REFERENCE, ensure_reference
    ensure_reference()
    print(f"wrote {z} ({z.stat().st_size // 1024} KB)")
    print(f"wrote {i}")
    print(f"parity reference: {REFERENCE}")
    print("serve it:  python -m http.server -d observatory  "
          "then open http://localhost:8000/")


if __name__ == "__main__":
    main()
