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

import inn.observatory as OB
from inn.engine_surface import ENGINE_ROOT, verify_pin

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "observatory"
if str(ROOT) not in sys.path:           # allow `python observatory/build_bundle.py`
    sys.path.insert(0, str(ROOT))       # so `experiments` / `observatory` resolve
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
let PY=null, runLive=null, runControlled=null, PALETTE=[], INTERVENTIONS=[];
function setStatus(t){const s=document.getElementById('c_status'); if(s)s.textContent=t;}
// live intervention console (cockpit only). Mirrors the M-G semantics + labels:
// controlled subject, AUTO/MANUAL, finite palette, valid targets only, engine
// suggestion (read-only), then a deterministic re-run with the queued overrides.
function iv_tickIdx(t){const T=(window.MODEL||{}).ticks||[];let b=0;
  for(let i=0;i<T.length;i++){if(T[i].t<=t)b=i;else break;}return b;}
function iv_presentWith(subj,t){const T=(window.MODEL||{}).ticks||[];const tk=T[iv_tickIdx(t)];
  if(!tk||!tk.personas[subj])return [];const room=tk.personas[subj].room;
  return (window.MODEL.cast||[]).filter(p=>p!==subj&&tk.personas[p]&&tk.personas[p].room===room);}
function iv_palEntry(v){return (((window.MODEL||{}).intervention_ui||{}).palette||[])
  .find(e=>e.verb===v)||{needs_target:true};}
function buildIntvConsole(){
  const box=document.getElementById('intvconsole'); if(!box||!window.MODEL)return;
  const cast=window.MODEL.cast||[], nm=id=>(window.MODEL.display_names||{})[id]||id;
  const curT=(window.MODEL.ticks[Math.min(frame,window.MODEL.ticks.length-1)]||{}).t||0;
  const castOpts=cast.map(p=>`<option value="${p}">${nm(p)}</option>`).join('');
  const palOpts=PALETTE.map(v=>`<option value="${v}">${fmt(v)}</option>`).join('');
  box.innerHTML=`<label title="Take manual control of one cast member. The engine still computes their interior.">subject <select id="iv_subj">${castOpts}</select></label>
    <label title="AUTO: observe the autonomous NPC. MANUAL: your queued actions override the outward action.">mode <select id="iv_mode"><option value="manual">MANUAL</option><option value="auto">AUTO</option></select></label>
    <label title="When (tick) the override fires — defaults to the current playhead.">tick <input id="iv_tick" type="number" value="${curT}" style="width:78px"></label>
    <label title="The outward action — finite, engine-compatible palette.">action <select id="iv_action">${palOpts}</select></label>
    <label title="Valid targets only — cast present in the subject's room at that tick.">target <select id="iv_target"></select></label>
    <button id="iv_suggest" title="What the engine would do for this subject at this tick (read-only).">Suggest</button>
    <button id="iv_add" title="Queue this override (validated: target must be present).">Add override</button>
    <button id="iv_run" title="Deterministically re-run live with the queued overrides.">Run with control</button>
    <button id="iv_clear" title="Discard queued overrides.">Clear</button>
    <div style="flex-basis:100%" id="iv_hint" class="sub"></div>
    <div style="flex-basis:100%" id="iv_list"></div>`;
  const $i=id=>document.getElementById(id);
  const refreshTargets=()=>{const subj=$i('iv_subj').value, t=+($i('iv_tick').value||curT);
    const present=iv_presentWith(subj,t);
    const needs=iv_palEntry($i('iv_action').value).needs_target;
    $i('iv_target').innerHTML=(needs?'':'<option value="">(no target)</option>')
      +present.map(p=>`<option value="${p}">${nm(p)}</option>`).join('');
    if(needs&&!present.length)$i('iv_hint').textContent=
      `${nm(subj)} is alone at tick ${t}; targeted actions are unavailable — pick another tick or action.`;
    else $i('iv_hint').textContent='';};
  const refreshList=()=>{$i('iv_list').innerHTML=
    INTERVENTIONS.length?INTERVENTIONS.map((x,i)=>
      `<span class="intvchip">t${x.t} ${nm(x.subject)} ${fmt(x.verb)}${x.target?(' → '+nm(x.target)):''}`
      +` <a href="#" data-i="${i}" class="iv_del">×</a></span>`).join('')
      :'<span class="sub">no overrides queued — Add some, then Run with control.</span>';
    document.querySelectorAll('.iv_del').forEach(a=>a.onclick=ev=>{ev.preventDefault();
      INTERVENTIONS.splice(+a.dataset.i,1);refreshList();});};
  $i('iv_subj').onchange=()=>{window.CONTROLLED=$i('iv_subj').value;refreshTargets();render();};
  $i('iv_mode').onchange=()=>{window.CONTROL_MODE=$i('iv_mode').value;render();};
  $i('iv_action').onchange=refreshTargets; $i('iv_tick').onchange=refreshTargets;
  $i('iv_suggest').onclick=()=>{const subj=$i('iv_subj').value,t=+($i('iv_tick').value||curT);
    const ps=(window.MODEL.ticks[iv_tickIdx(t)]||{}).personas||{};
    const a=(ps[subj]||{}).action||'neutral';
    $i('iv_hint').textContent=`engine would select for ${nm(subj)} at tick ${t}: ${fmt(a)} (read-only — what the autonomous NPC would do).`;};
  $i('iv_add').onclick=()=>{const subj=$i('iv_subj').value, verb=$i('iv_action').value,
    t=parseInt($i('iv_tick').value||'0',10), needs=iv_palEntry(verb).needs_target,
    target=needs?($i('iv_target').value||null):null;
    if(needs&&!target){$i('iv_hint').textContent=`${fmt(verb)} needs a present target.`;return;}
    INTERVENTIONS.push({t,subject:subj,verb,target}); refreshList();};
  $i('iv_clear').onclick=()=>{INTERVENTIONS=[];refreshList();};
  $i('iv_run').onclick=()=>doRunControlled();
  window.CONTROLLED=$i('iv_subj').value; window.CONTROL_MODE=$i('iv_mode').value;
  refreshTargets(); refreshList();
}
async function doRunControlled(){
  if(!runControlled){setStatus('still booting…');return;}
  const subj=window.CONTROLLED||(document.getElementById('iv_subj')||{}).value;
  const mode=window.CONTROL_MODE||'manual';
  setStatus(mode==='manual'?'simulating with intervention…':'simulating (controlled, AUTO)…');
  await new Promise(r=>setTimeout(r,30));
  try{
    await runControlled(document.getElementById('c_profile').value,
      document.getElementById('c_plan').value,
      parseInt(document.getElementById('c_seed').value||'7',10),
      subj, mode, mode==='manual'?JSON.stringify(INTERVENTIONS):'[]');
    setStatus('live · controlled ('+mode+')'); buildIntvConsole();
  }catch(e){console.error(e); setStatus('controlled run failed: '+e);}
}
function opts(arr,desc){return arr.map(p=>`<option title="${desc[p]||''}">${p}</option>`).join('');}
function buildControls(){
  const c=document.getElementById('controls'); c.style.display='flex';
  c.innerHTML=`<label title="The inn's character — which behavioural profile the cast runs under.">profile <select id="c_profile">${opts(PROFILES,PROFILE_DESC)}</select></label>
    <label title="What gets injected into the run — the canonical probe protocol.">protocol <select id="c_plan">${opts(PLANS,PLAN_DESC)}</select></label>
    <label title="Deterministic RNG seed. Same profile + protocol + seed → byte-identical run.">seed <input id="c_seed" type="number" value="7" style="width:64px"></label>
    <button id="c_run" disabled title="Re-run the full 3-day, 7-NPC simulation in-browser with these settings.">Run simulation</button>
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
      +`<b>Run simulation</b> recomputes in-browser; <b>Verify parity</b> checks Pyodide matches CPython.`;};
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
async function doRun(){
  if(!runLive){setStatus('still booting…');return;}
  setStatus('simulating… (a few seconds)');
  await new Promise(r=>setTimeout(r,30));   // let the status paint first
  try{
    await runLive(document.getElementById('c_profile').value,
      document.getElementById('c_plan').value,
      parseInt(document.getElementById('c_seed').value||'7',10));
    setStatus('live · Pyodide'); buildIntvConsole();
  }catch(e){console.error(e); setStatus('run failed: '+e);}
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
from inn.loop import InnLoop
from inn.engine_surface import believable_day_layout
import inn.observe as O
import js
CFG = load_inn_config("inn.yaml")
DAY = believable_day_layout()["day_ticks"]
class _Mem:
    def __init__(s): s.records=[]
    def emit(s,r): s.records.append(r)
    def close(s): return ""
def run_live(profile, plan, seed):
    m=_Mem()
    InnLoop(CFG, seed=int(seed), probe_plan=plan, trace=m, profile=profile).run(CFG.days*DAY)
    model=O.build_model(m.records, CFG, meta={"subtitle":"live · Pyodide"}, stride=2)
    js.window.MODEL = js.JSON.parse(json.dumps(model))
    js.init()
def run_parity(seed, n):
    # Fixed G2 session, identical params to experiments.g2_parity; returns the
    # full-trace SHA-256 (TraceWriter.close()) for in-browser parity comparison.
    from inn.session import run_session
    import tempfile
    h = run_session(CFG, "control", tempfile.mkdtemp(), seed=int(seed),
                    n_ticks=int(n), profile="game_semantic_profile")
    return h["trace_sha256"]
def run_live_controlled(profile, plan, seed, subject, mode, interventions_json):
    # M-G: same live run, but with the observer controlling one subject. The
    # engine still ticks that subject; in MANUAL the queued actions override only
    # the outward action, routed through the normal world/transducer + probe path.
    # In AUTO the subject is observed (engine-selected) — no overrides.
    from inn.intervention import ControlState, make_intervention
    ivs = json.loads(interventions_json) if interventions_json else []
    control = ControlState(subject, mode or "manual") if subject else None
    m=_Mem()
    loop=InnLoop(CFG, seed=int(seed), probe_plan=plan, trace=m, profile=profile,
                 control=control)
    for iv in ivs:
        loop.queue_intervention(int(iv["t"]),
                                make_intervention(iv["verb"], iv.get("target")))
    loop.run(CFG.days*DAY)
    model=O.build_model(m.records, CFG, meta={"subtitle":"live · intervention"}, stride=2)
    js.window.MODEL = js.JSON.parse(json.dumps(model))
    js.init()
def palette_verbs():
    from inn.intervention import PALETTE_VERBS
    return list(PALETTE_VERBS)
`);
    runLive=(p,pl,sd)=>PY.globals.get("run_live")(p,pl,sd);
    runControlled=(p,pl,sd,subj,mode,ivs)=>PY.globals.get("run_live_controlled")(p,pl,sd,subj,mode,ivs);
    PALETTE=PY.globals.get("palette_verbs")().toJs();
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
