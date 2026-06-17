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
        subject||'',mode||'auto',initial);
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
function opts(arr,desc){return arr.map(p=>`<option title="${desc[p]||''}">${p}</option>`).join('');}
function buildControls(){
  const c=document.getElementById('controls'); c.style.display='flex';
  c.innerHTML=`<label title="The inn's character — which behavioural profile the cast runs under.">profile <select id="c_profile">${opts(PROFILES,PROFILE_DESC)}</select></label>
    <label title="What gets injected into the run — the canonical probe protocol.">protocol <select id="c_plan">${opts(PLANS,PLAN_DESC)}</select></label>
    <label title="Deterministic RNG seed. Same profile + protocol + seed → byte-identical run.">seed <input id="c_seed" type="number" value="7" style="width:64px"></label>
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
  renderCycle(); buildRibbons(); render(); buildLiveConsole();
}
// "Review autonomous run": one autonomous live session advanced to the end, then
// reviewed read-only (history scrubber). Intervention happens via Start live
// intervention, which leaves a mid-run frontier to act on.
async function doRun(){
  window.afterRender=updateLiveControls;
  await liveStart('', 'auto', 1000000000);   // advance_all (clamped to run length)
}
async function boot(){
  buildControls();
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
from inn.engine_surface import believable_day_layout
from inn.live import LiveSession
import inn.observe as O
import js
CFG = load_inn_config("inn.yaml")
DAY = believable_day_layout()["day_ticks"]
TOTAL = CFG.days*DAY
HOUR = max(1, round(DAY/24))          # ticks per in-world hour
SEED_TICKS = 2*HOUR                    # seed the first ~2 hours of day 1 so there
                                       # is a scene to act on; the rest is the user's
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
    if first: js.init()       # one-time wiring (scrub/play/dev handlers)
    js.liveRefresh()          # follow the frontier + (re)build the live console
def live_start(profile, plan, seed, subject, mode, initial):
    init = int(initial)
    init = (SEED_TICKS if init <= 0 else init)       # seed ~2 h of day 1, rest is live
    SESS["s"] = LiveSession(CFG, profile, plan, int(seed), TOTAL,
                            subject=(subject or None), mode=(mode or "auto"))
    SESS["s"].advance(init)
    _emit(first=True)
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
    boot = CONTROLS_AND_BOOT.replace("__PYODIDE__", _pyodide_base())
    assets = OB.load_assets()  # embed the same asset pack as the static export
    adata = json.dumps(assets, ensure_ascii=False)
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<link rel='icon' href='data:,'>"  # suppress the browser favicon request (no 404)
        "<title>Living Inn Observatory — live</title>"
        "<style>" + OB.STYLE + "</style><style>" + OB._asset_css(assets) + "</style></head>"
        "<body>" + OB.BODY +
        "<script>window.ASSETS=" + adata + ";</script>"
        "<script>" + OB.SCRIPT + "</script>" + boot +
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
