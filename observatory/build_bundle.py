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
import zipfile
from pathlib import Path

import inn.observatory as OB
from inn.engine_surface import ENGINE_ROOT, verify_pin

ROOT = Path(__file__).resolve().parents[1]
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
let PY=null, runLive=null;
function setStatus(t){const s=document.getElementById('c_status'); if(s)s.textContent=t;}
function buildControls(){
  const c=document.getElementById('controls'); c.style.display='flex';
  c.innerHTML=`<label>profile <select id="c_profile">${PROFILES.map(p=>`<option>${p}</option>`).join('')}</select></label>
    <label>protocol <select id="c_plan">${PLANS.map(p=>`<option>${p}</option>`).join('')}</select></label>
    <label>seed <input id="c_seed" type="number" value="7" style="width:64px"></label>
    <button id="c_run" disabled>Run simulation</button>
    <span id="c_status" class="sub">booting Pyodide…</span>`;
  document.getElementById('c_run').onclick=()=>doRun();
}
async function doRun(){
  if(!runLive){setStatus('still booting…');return;}
  setStatus('simulating… (a few seconds)');
  await new Promise(r=>setTimeout(r,30));   // let the status paint first
  try{
    await runLive(document.getElementById('c_profile').value,
      document.getElementById('c_plan').value,
      parseInt(document.getElementById('c_seed').value||'7',10));
    setStatus('live · Pyodide');
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
`);
    runLive=(p,pl,sd)=>PY.globals.get("run_live")(p,pl,sd);
    const btn=document.getElementById('c_run'); if(btn)btn.disabled=false;
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
    print(f"wrote {z} ({z.stat().st_size // 1024} KB)")
    print(f"wrote {i}")
    print("serve it:  python -m http.server -d observatory  "
          "then open http://localhost:8000/")


if __name__ == "__main__":
    main()
