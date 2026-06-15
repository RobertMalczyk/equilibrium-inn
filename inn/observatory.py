"""The Living Inn Observatory (CLAUDE.md M-D): a beautiful, warm, slightly-
magical window onto the engine's living world — an OBSERVATORY, not a game (no
quests/goals/score/inventory/combat). It renders the shared ObservationModel
(inn.observe.build_model) with hand-rolled inline SVG/Canvas/CSS plus an embedded
visual asset pack — no CDN, no network — so the same render layer serves two
deliverables:

  * PRIMARY  — a Pyodide live cockpit (observatory/build_bundle.py -> index.html)
               that runs the inn in-browser and calls build_model live, reusing
               STYLE/BODY/SCRIPT and the embedded assets from here.
  * SECONDARY — a self-contained HTML export of one run:
               python -m inn.observatory <trace_dir> -o run.html
               (embeds a CPython-built model + the asset pack as base64). The
               shareable report AND the mandated G2-parity fallback.

Everything shown comes from the trace via inn.observe (hard rule 0.4). No LLM.
Visual assets live in observatory/assets/ and are base64-embedded at build time;
missing files degrade to warm CSS fallbacks (always presentable).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import inn.observe as O

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "observatory" / "assets"

# All asset names the render layer knows. Present files are embedded; absent ones
# fall back to CSS gradients / inline diagrams.
ASSET_NAMES = (
    "bg_observatory_warm.png", "hero_inn_header.png", "scene_inn_rooms.png",
    "panel_parchment_soft.png", "promo_behavior_cycle.png",
    "divider_lantern_vine.svg", "npc_token_base.svg",
    "icon_boredom.svg", "icon_fatigue.svg", "icon_stress.svg", "icon_sleep.svg",
    "icon_activity.svg", "icon_causality.svg", "overlay_fireflies_soft.svg",
    "equilibrium_observatory_emblem.svg",
)
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".svg": "image/svg+xml", ".webp": "image/webp"}

# Per-asset max pixel dimension for the web-optimization pass. Icons render tiny,
# so a 1.5 MB source PNG is downscaled hard; full-bleed art keeps resolution.
# Keeps all 15 pictures while shrinking the embedded page from ~50 MB to a few MB.
_MAXDIM = {
    "icon_boredom.svg": 72, "icon_fatigue.svg": 72, "icon_stress.svg": 72,
    "icon_sleep.svg": 72, "icon_activity.svg": 72, "icon_causality.svg": 96,
    "npc_token_base.svg": 128, "equilibrium_observatory_emblem.svg": 192,
    "divider_lantern_vine.svg": 900, "overlay_fireflies_soft.svg": 1200,
    "bg_observatory_warm.png": 1800, "hero_inn_header.png": 1800,
    "scene_inn_rooms.png": 1600, "panel_parchment_soft.png": 1024,
    "promo_behavior_cycle.png": 1400,
}


def _resolve(d: Path, name: str) -> Path | None:
    """Find an asset by exact name, or by stem with any image extension — so the
    art pack works whether a logical asset ships as .svg or .png."""
    if (d / name).is_file():
        return d / name
    stem = Path(name).stem
    for ext in (".png", ".svg", ".webp", ".jpg", ".jpeg"):
        if (d / (stem + ext)).is_file():
            return d / (stem + ext)
    return None


def _read_optimized(p: Path, max_dim: int, optimize: bool) -> tuple[bytes, str]:
    """Return (bytes, mime) for an asset. Raster images are downscaled to max_dim
    and re-encoded as WebP (best-effort; needs Pillow). SVGs and any failure pass
    through unchanged. Determinism: scaling/encoding is fixed and input-only."""
    raw = p.read_bytes()
    mime = _MIME.get(p.suffix.lower(), "application/octet-stream")
    if not optimize or mime == "image/svg+xml":
        return raw, mime
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGBA")
        if max(im.size) > max_dim:
            im.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="WEBP", quality=82, method=6)
        return buf.getvalue(), "image/webp"
    except Exception:
        return raw, mime  # Pillow absent or unsupported format -> raw embed


def load_assets(assets_dir: str | Path = ASSETS_DIR,
                optimize: bool = True) -> dict[str, str]:
    """Read every present asset and return {name: data-URI}. Missing -> omitted.
    Each logical name is keyed under its canonical ASSET_NAMES entry regardless of
    the on-disk extension (so dropping in PNGs for SVG-named slots just works).
    With optimize=True (default) raster art is downscaled+WebP-encoded so the
    embedded page stays a few MB instead of tens of MB."""
    d = Path(assets_dir)
    out: dict[str, str] = {}
    for name in ASSET_NAMES:
        p = _resolve(d, name)
        if p is not None:
            data, mime = _read_optimized(p, _MAXDIM.get(name, 1200), optimize)
            b64 = base64.b64encode(data).decode("ascii")
            out[name] = f"data:{mime};base64,{b64}"
    return out


def _asset_css(assets: dict[str, str]) -> str:
    """CSS custom properties for the image-background assets (present only); the
    main stylesheet references them with warm fallbacks via var(--x, fallback)."""
    pairs = {
        "--a-bg": "bg_observatory_warm.png",
        "--a-hero": "hero_inn_header.png",
        "--a-scene": "scene_inn_rooms.png",
        "--a-panel": "panel_parchment_soft.png",
        "--a-fireflies": "overlay_fireflies_soft.svg",
    }
    decls = [f"{var}:url('{assets[name]}');" for var, name in pairs.items()
             if name in assets]
    return ":root{" + "".join(decls) + "}" if decls else ""


STYLE = """
:root{
  --parchment:#f3e9d2; --ink:#3a2f24; --muted:#7c6f5d; --line:#d8c9a8;
  --panel:#fbf4e3; --shadow:0 2px 6px rgba(90,66,30,.16);
  --idle:#c9b48f; --seeking:#d99a2b; --busy:#7c9e5e; --cooldown:#bd8a5a;
  --sleep:#4655bf; --incident:#b5532e; --need:#caa24b; --affect:#b5683e; --sleepf:#4655bf;
}
*{box-sizing:border-box}
html{scroll-behavior:auto}
body{margin:0;color:var(--ink);
  font:15px/1.55 "Iowan Old Style",Georgia,"Times New Roman",serif;
  background:var(--a-bg, radial-gradient(circle at 50% -8%,#fbf3df,#ecdcb8)) fixed;
  background-size:cover;}
.fireflies{position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.5;
  background:var(--a-fireflies,none);background-size:cover;mix-blend-mode:screen}
.wrap{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:0 22px 60px}
h1,h2,h3{font-weight:600;letter-spacing:.2px;margin:0}
.hero{display:flex;align-items:center;gap:18px;margin:18px 0 6px;padding:22px 26px;
  border-radius:16px;border:1px solid var(--line);box-shadow:var(--shadow);
  background:var(--a-hero, linear-gradient(105deg,#f6ebcf,#efd9a8 60%,#e9c987));
  background-size:cover;background-position:center}
.hero .emblem{width:74px;height:74px;flex:none;filter:drop-shadow(0 1px 2px rgba(80,50,10,.25))}
.hero h1{font-size:30px}
.hero .tag{color:#6b5836;font-style:italic;margin-top:3px}
.hero .pill{display:inline-block;margin-top:8px;font-size:12px;color:#6b5836;
  background:rgba(255,255,255,.55);border:1px solid var(--line);border-radius:20px;padding:2px 11px}
.divider{width:100%;height:26px;margin:14px 0 4px;opacity:.9;
  background:var(--div) center/contain no-repeat}
.divider.plain{background:none;border-top:1px solid var(--line);height:1px;margin:22px 0}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:14px;margin:12px 0;
  padding:11px 16px;border-radius:13px;border:1px solid var(--line);box-shadow:var(--shadow);
  background:var(--a-panel,var(--panel));background-size:cover;background-blend-mode:overlay}
.bar.sticky{position:sticky;top:8px;z-index:5;backdrop-filter:saturate(1.1)}
.clock{font-size:21px;font-variant-numeric:tabular-nums}
.phase{padding:2px 10px;border-radius:20px;background:#efe2c2;border:1px solid var(--line)}
.grow{flex:1}
input[type=range]{width:100%;accent-color:#a9762f}
select,input[type=number]{font:inherit;border:1px solid var(--line);border-radius:7px;
  padding:3px 6px;background:#fffdf6;color:var(--ink)}
label{font-size:13px;color:var(--muted)}
button{font:inherit;background:#efe2c2;border:1px solid var(--line);border-radius:8px;
  padding:5px 12px;cursor:pointer;color:var(--ink)}
button:hover{background:#e7d6ad}
button.on{background:#c9883a;color:#fff;border-color:#a9762f}
.grid{display:grid;gap:16px}
.cols{grid-template-columns:1.18fr .82fr}
.cols3{grid-template-columns:1.3fr .7fr}
@media(max-width:900px){.cols,.cols3{grid-template-columns:1fr}}
.card{border:1px solid var(--line);border-radius:14px;padding:15px 17px;box-shadow:var(--shadow);
  background:var(--a-panel,var(--panel));background-size:cover;background-blend-mode:overlay;
  background-color:var(--panel)}
.card h3{display:flex;align-items:center;gap:8px;font-size:12.5px;text-transform:uppercase;
  letter-spacing:1.3px;color:var(--muted);margin-bottom:11px}
.card h3 img{width:18px;height:18px}
.scene{position:relative;border-radius:12px;overflow:hidden;min-height:230px;padding:10px;
  background:var(--a-scene,#f5ead0) center/cover;border:1px solid var(--line)}
.rooms{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
.room{min-height:84px;background:rgba(251,244,227,.82);border:1px solid var(--line);
  border-radius:10px;padding:8px}
.room .rn{font-size:10.5px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted)}
.tok{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;
  width:52px;height:52px;margin:5px 5px 0 0;border-radius:50%;cursor:pointer;
  background:var(--tokbg) center/contain no-repeat;background-color:#fff;
  border:1px solid var(--line);font-size:10.5px;text-align:center;line-height:1.05;transition:transform .12s}
.tok:hover{transform:translateY(-2px)}
.tok.sel{box-shadow:0 0 0 3px #d99a2b}
.tok .dot{width:11px;height:11px;border-radius:50%;margin-bottom:2px}
.person{border-top:1px solid var(--line);padding:9px 2px;cursor:pointer}
.person:first-child{border-top:0}
.person.sel{background:rgba(217,154,43,.12);border-radius:8px}
.prow{display:flex;align-items:center;gap:10px}
.pname{width:84px;font-weight:600}
.ptags{color:var(--muted);font-size:13px}
.gauges{display:grid;grid-template-columns:repeat(2,1fr);gap:3px 16px;margin-top:7px}
.g{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.g img{width:14px;height:14px;flex:none}
.g .lab{width:74px}
.gbar{flex:1;height:7px;background:#e9dcbd;border-radius:5px;overflow:hidden}
.gfill{height:100%;border-radius:5px}
.cycle{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:12px}
.stage{display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border-radius:22px;
  background:#f7eed7;border:1px solid var(--line);font-size:13px}
.stage img{width:17px;height:17px}
.stage .sw{width:11px;height:11px;border-radius:50%}
.arrow{color:var(--muted)}
.promo{max-width:100%;border-radius:10px;border:1px solid var(--line);margin-top:6px}
.ribbons{overflow-x:auto;margin-top:6px}
.rib{display:flex;align-items:center;gap:8px;margin:3px 0}
.rib .pn{width:84px;font-size:13px;text-align:right;color:var(--muted)}
.stream{height:330px;overflow:auto;font-size:13px}
.ev{padding:4px 0;border-top:1px dotted var(--line);display:flex;gap:8px}
.ev .tt{color:var(--muted);font-variant-numeric:tabular-nums;width:50px;flex:none}
.ev.inp{color:#9a6a16}                 /* input: external stimulus */
.ev.cust{color:#1f7a72;font-weight:600}/* custom: your injected action */
.ev.react{color:#9a4a26}               /* output: an NPC reaction */
.ev.inc{color:var(--incident);font-weight:600} /* output: an incident (outburst) */
.ev.amb{font-style:italic;color:#6b5836}        /* behaviour: mode transition */
.ev.hl{background:rgba(181,83,46,.13);border-left:3px solid var(--incident);
  padding-left:7px;border-radius:0 5px 5px 0;font-weight:600}
.ev.hl .tt{color:var(--incident)}
.ev.intv{color:#1f6f72;font-weight:600;border-left:3px solid #2a9aa0;padding-left:7px}
.ev.intv .sub{font-weight:400}
.intvlog{margin-top:8px;max-height:240px;overflow:auto}
.llmtag{color:#6b5836;font-style:italic;font-weight:400}
#intvconsole label{display:flex;gap:5px;align-items:center;font-size:13px}
#intvconsole select,#intvconsole input{font:inherit;padding:2px 4px}
.intvchip{display:inline-block;background:rgba(42,154,160,.13);border:1px solid #2a9aa0;
  border-radius:5px;padding:1px 7px;margin:2px;font-size:12px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px}
.metric{background:#f7eed7;border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.metric .v{font-size:20px}
.metric .k{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;
  display:flex;align-items:center;gap:5px}
.metric .k img{width:13px;height:13px}
.why{font-size:13.5px}
.why .head{font-weight:600;margin-bottom:6px}
.why .ln{padding:2px 0 2px 6px;border-left:2px solid var(--seeking);margin:3px 0;color:#5a4a33}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted);margin-top:8px}
.legend span{display:inline-flex;align-items:center;gap:5px}
.dot{width:10px;height:10px;border-radius:50%}
.footer{text-align:center;color:var(--muted);font-size:12px;margin-top:22px}
.footer img{width:28px;height:28px;vertical-align:middle;opacity:.8}
.isnight .scene{filter:saturate(.8) brightness(.94)}
canvas{display:block}
"""

BODY = """
<div class="fireflies"></div>
<div class="wrap">
  <div class="hero">
    <img class="emblem" id="emblem" alt="">
    <div>
      <h1>Living Inn Observatory</h1>
      <div class="tag">A living observatory for Equilibrium&nbsp;Engine behaviour.</div>
      <span class="pill">watch NPCs grow bored · seek · work · tire · rest · sleep · recover · remember</span>
    </div>
  </div>
  <div class="bar sticky">
    <span class="clock" id="clock">--:--</span>
    <span class="phase" id="phase">—</span>
    <span class="phase" id="weather" style="display:none">rain</span>
    <span class="grow"></span>
    <button id="play">▶ play</button>
    <button id="hltoggle">⚑ Highlight insults</button>
    <button id="devtoggle">Developer view</button>
  </div>
  <div class="bar" id="controls" style="display:none"></div>
  <div class="bar"><input type="range" id="scrub" min="0" max="0" value="0"></div>
  <div class="divider" id="d1"></div>
  <div class="grid cols">
    <div class="card"><h3>The inn — who is where</h3><div class="scene"><div class="rooms" id="rooms"></div></div>
      <div class="legend" id="moodlegend"></div></div>
    <div class="card"><h3>Who, and how they feel</h3><div id="cards"></div></div>
  </div>
  <div class="divider" id="d2"></div>
  <div class="card"><h3>Behavioural cycle — idle · seeking · busy · rest · sleep</h3>
    <div class="cycle" id="cycle"></div>
    <div class="grid cols3">
      <div class="ribbons" id="ribbons"></div>
      <img class="promo" id="promo" alt="boredom → seeking → activity → fatigue → rest → sleep → recovery" style="display:none">
    </div>
  </div>
  <div class="divider" id="d3"></div>
  <div class="grid cols">
    <div class="card"><h3>What is happening</h3>
      <div class="legend" id="streamleg"></div>
      <div class="stream" id="stream"></div></div>
    <div>
      <div class="card"><h3>Validation metrics</h3><div class="metrics" id="metrics"></div></div>
      <div class="card" style="margin-top:16px"><h3><img id="whyicon" alt="">Why — causality</h3>
        <div class="why" id="why"></div></div>
    </div>
  </div>
  <div class="divider plain" id="d4" style="display:none"></div>
  <div class="card" id="intvpanel" style="display:none">
    <h3>Intervention console — observer control</h3>
    <div class="sub" id="intvhint">Take manual control of one subject; the engine
      still computes their interior — you override only the outward action, routed
      through the normal world path. This is a behavioural probe, not a game.</div>
    <div class="bar" id="intvconsole"></div>
    <div class="intvlog" id="intvlog"></div>
  </div>
  <div class="footer"><img id="footemblem" alt=""><br>
    An instrument for observing Equilibrium Engine — not a game.</div>
</div>
"""

SCRIPT = r"""
const MODE_COLOR={idle:'#c9b48f',seeking:'#d99a2b',busy:'#7c9e5e',cooldown:'#bd8a5a',sleep:'#4655bf'};
const MOOD_COLOR={calm:'#8fae6e',focused:'#7c9e5e',bored:'#d9c24a',tired:'#bd8a5a',
  irritated:'#b5532e',resting:'#7d8bd6',sleeping:'#4655bf'};
const STATE_ICON={boredom:'icon_boredom.svg',fatigue:'icon_fatigue.svg',
  stress:'icon_stress.svg',sleep_pressure:'icon_sleep.svg'};
const A=(window.ASSETS||{});
let frame=0, dev=false, playing=false, timer=null, selected=null, hilite=true;
const $=id=>document.getElementById(id);
function asset(n){return A[n]||null;}
function img(n,cls){const u=asset(n);return u?`<img class="${cls||''}" src="${u}" alt="">`:'';}

function phaseOf(clock,night){if(night)return 'night';
  const h=parseInt(clock.split(':')[0],10);return h<9?'morning':h<18?'workday':'evening';}
function fmt(s){return (s||'').replace(/_/g,' ');}
function nm(id){return (MODEL.display_names&&MODEL.display_names[id])||
  (id?id.charAt(0).toUpperCase()+id.slice(1):'someone');}

function renderHeader(){const tk=MODEL.ticks[frame];
  $('clock').textContent='Day '+tk.day+'  '+tk.clock;
  $('phase').textContent=phaseOf(tk.clock,tk.night);
  $('weather').style.display=tk.rain?'inline':'none';
  document.body.classList.toggle('isnight',!!tk.night);}

function renderScene(){const tk=MODEL.ticks[frame], byRoom={};
  MODEL.rooms.forEach(r=>byRoom[r]=[]);
  MODEL.cast.forEach(p=>{const r=tk.personas[p].room; if(byRoom[r])byRoom[r].push(p);});
  const tokbg=asset('npc_token_base.svg');
  $('rooms').innerHTML=MODEL.rooms.map(r=>{
    const toks=byRoom[r].map(p=>{const ps=tk.personas[p];
      return `<span class="tok ${selected===p?'sel':''}" data-p="${p}" style="--tokbg:${tokbg?`url('${tokbg}')`:'none'}">
        <span class="dot" style="background:${MOOD_COLOR[ps.mood]||'#aaa'}"></span>${MODEL.display_names[p]}</span>`;}).join('');
    return `<div class="room"><div class="rn">${fmt(r)}</div>${toks||'<span class="ptags">·</span>'}</div>`;}).join('');
  document.querySelectorAll('#rooms .tok').forEach(t=>t.onclick=()=>select(t.dataset.p));
  $('moodlegend').innerHTML=Object.entries(MOOD_COLOR).map(([k,c])=>
    `<span><span class="dot" style="background:${c}"></span>${k}</span>`).join('');}

function level(lab,v){const hi=(MODEL.high_thresholds&&MODEL.high_thresholds[lab])||0.6;
  if(v>=hi)return['high','#b5532e'];
  if(v>=hi*0.55)return['building','#a9762f'];
  if(v>=0.12)return['low','#5d7a45'];
  return['—','#9b9079'];}
function gauge(lab,v,fam){const col=fam==='affect'?'var(--affect)':fam==='sleep'?'var(--sleepf)':'var(--need)';
  // Observer view: a readable level word (no raw floats). Developer view: the float.
  const lv=level(lab,v);
  const tag=dev?`<span style="width:42px;text-align:right;color:var(--muted)">${v.toFixed(2)}</span>`
    :`<span style="width:56px;text-align:right;font-weight:600;color:${lv[1]}">${lv[0]}</span>`;
  return `<div class="g">${img(STATE_ICON[lab])}<span class="lab">${lab}</span>
    <span class="gbar"><span class="gfill" style="width:${(v*100).toFixed(0)}%;background:${col}"></span></span>
    ${tag}</div>`;}
function renderCards(){const tk=MODEL.ticks[frame], fam=MODEL.state_families;
  const which=s=>fam.affect.includes(s)?'affect':fam.sleep.includes(s)?'sleep':'need';
  $('cards').innerHTML=MODEL.cast.map(p=>{const ps=tk.personas[p], states=dev?ps.raw:ps.states;
    const gs=Object.entries(states).map(([s,v])=>gauge(s,v,which(s))).join('');
    return `<div class="person ${selected===p?'sel':''}" data-p="${p}"><div class="prow">
      <span class="dot" style="background:${MOOD_COLOR[ps.mood]||'#aaa'}"></span>
      <span class="pname">${MODEL.display_names[p]}</span>
      <span class="ptags">${ps.mood} · ${ps.mode}${ps.action&&ps.action!=='neutral'?' · '+fmt(ps.action):''}</span>
      </div><div class="gauges">${gs}</div></div>`;}).join('');
  document.querySelectorAll('#cards .person').forEach(c=>c.onclick=()=>select(c.dataset.p));}

function renderCycle(){
  const stages=[['Idle','idle'],['Seeking','seeking','icon_activity.svg'],['Busy','busy','icon_activity.svg'],
    ['Rest','cooldown','icon_sleep.svg'],['Sleep','sleep','icon_sleep.svg']];
  $('cycle').innerHTML=stages.map((s,i)=>
    `<span class="stage">${s[2]?img(s[2]):''}<span class="sw" style="background:${MODE_COLOR[s[1]]}"></span>${s[0]}</span>`
    +(i<stages.length-1?'<span class="arrow">→</span>':'')).join('');
  const pr=asset('promo_behavior_cycle.png'); if(pr){$('promo').src=pr;$('promo').style.display='block';}}

function buildRibbons(){const n=MODEL.ticks.length, w=Math.min(880,Math.max(320,n)), h=15;
  $('ribbons').innerHTML=MODEL.cast.map(p=>
    `<div class="rib"><span class="pn">${MODEL.display_names[p]}</span>
      <canvas data-p="${p}" width="${w}" height="${h}"></canvas></div>`).join('')
    +`<div class="rib"><span class="pn"></span><canvas id="axis" width="${w}" height="14"></canvas></div>`
    +`<div class="legend">`+Object.entries(MODE_COLOR).map(([k,c])=>`<span><span class="dot" style="background:${c}"></span>${k}</span>`).join('')
    +` <span><span class="dot" style="background:var(--incident)"></span>incident</span></div>`;
  document.querySelectorAll('#ribbons canvas[data-p]').forEach(cv=>{
    const p=cv.dataset.p, ctx=cv.getContext('2d'), W=cv.width, H=cv.height;
    for(let i=0;i<n;i++){const m=MODEL.ticks[i].personas[p].mode;
      ctx.fillStyle=MODE_COLOR[m]||'#ccc';                 // paint the mode, incl. SLEEP
      ctx.fillRect(i/n*W,0,Math.ceil(W/n)+0.6,H);
      if(MODEL.ticks[i].night){ctx.fillStyle='rgba(40,30,60,.10)'; // faint night veil over the colour
        ctx.fillRect(i/n*W,0,Math.ceil(W/n)+0.6,H);}}
    ctx.fillStyle='#b5532e';
    MODEL.incidents.forEach(inc=>{const i=tickIndex(inc.t);if(i>=0)ctx.fillRect(i/n*W,0,2,H);});});
  drawPlayhead();}
function drawPlayhead(){const n=MODEL.ticks.length, ax=$('axis'); if(!ax)return;
  const ctx=ax.getContext('2d'); ctx.clearRect(0,0,ax.width,ax.height);
  ctx.fillStyle='#3a2f24'; ctx.fillRect(frame/n*ax.width,0,2,ax.height);
  ctx.fillStyle='#7c6f5d'; ctx.font='10px Georgia';
  MODEL.days.forEach(d=>{const i=MODEL.ticks.findIndex(t=>t.day===d);
    if(i>=0)ctx.fillText('day '+d,i/n*ax.width+3,11);});}
function tickIndex(t){let best=-1;for(let i=0;i<MODEL.ticks.length;i++){if(MODEL.ticks[i].t<=t)best=i;else break;}return best;}

function renderStream(){const cur=MODEL.ticks[frame].t; const items=[];
  (MODEL.inputs||[]).forEach(i=>items.push({t:i.t,clock:i.clock,
    cls:i.custom?'cust':'inp', insult:i.type==='insult',
    txt:(i.custom?'You':nm(i.source))+' '+fmt(i.type)+(i.custom?' — your action':' — input')}));
  (MODEL.reactions||[]).forEach(r=>items.push({t:r.t,clock:r.clock,
    cls:r.action==='outburst'?'inc':'react', insult:r.as==='insult',
    txt:nm(r.actor)+' '+fmt(r.as)+(r.target&&r.target!==r.actor?' → '+nm(r.target):'')+' — reaction'}));
  MODEL.transitions.filter(x=>['SEEKING','BUSY','SLEEP'].includes(x.new)&&x.driver).forEach(x=>
    items.push({t:x.t,clock:x.clock,cls:'amb',
      txt:nm(x.pid)+' '+x.prev.toLowerCase()+'→'+x.new.toLowerCase()+(x.driver?' ('+x.driver+' '+x.driver_value+')':'')}));
  // A LIVE feed: show only what has happened up to the current playhead, so the
  // log fills in as you scrub/play instead of dumping the whole run at once.
  const shown=items.filter(it=>it.t<=cur).sort((a,b)=>a.t-b.t);
  const box=$('stream');
  box.innerHTML=shown.map(it=>`<div class="ev ${it.cls}${hilite&&it.insult?' hl':''}">`
      +`<span class="tt">${it.clock}</span><span>${it.txt}</span></div>`).join('')
    ||'<div class="ev amb">quiet so far…</div>';
  // Keep newest in view by scrolling the CONTAINER ONLY (never the page). render()
  // only runs on a frame change, so a paused user can still scroll back freely.
  box.scrollTop=box.scrollHeight;}

function renderMetrics(){const m=MODEL.metrics;
  const cells=[['incidents',m.incidents,'icon_stress.svg'],['cascade depth',m.cascade_max_depth,'icon_causality.svg'],
    ['activity success',m.activity_success_rate==null?'—':(m.activity_success_rate*100).toFixed(0)+'%','icon_activity.svg'],
    ['offers',m.offers_total,'icon_activity.svg'],['contention',m.contention_total,''],
    ['recovery ticks',m.recovery_ticks_mean==null?'—':m.recovery_ticks_mean,'icon_sleep.svg']];
  const tb={}; MODEL.cast.forEach(p=>{const b=m.time_budget[p]||{};
    Object.entries(b).forEach(([k,v])=>tb[k]=(tb[k]||0)+v/MODEL.cast.length);});
  const ICO={busy:'icon_activity.svg',idle:'icon_boredom.svg',seeking:'icon_activity.svg',sleep:'icon_sleep.svg'};
  ['busy','idle','seeking','sleep'].forEach(k=>{if(tb[k]!=null)cells.push(['avg '+k,(tb[k]*100).toFixed(0)+'%',ICO[k]]);});
  $('metrics').innerHTML=cells.map(([k,v,ic])=>
    `<div class="metric"><div class="v">${v}</div><div class="k">${ic?img(ic):''}${k}</div></div>`).join('');}

function renderWhy(){const p=selected||MODEL.cast[0]; const lines=(MODEL.why&&MODEL.why[p])||[];
  $('why').innerHTML=`<div class="head">${MODEL.display_names[p]}</div>`+
    (lines.length?lines.map((l,i)=>`<div class="${i===0?'head':'ln'}">${l}</div>`).join('')
      :'<div class="ln">nothing to explain yet.</div>');}

// M-G: read-only intervention log. Shown only when the run carried observer
// overrides (autonomous runs never set MODEL.interventions), so the autonomous
// page and the G2 parity model are unchanged.
function renderInterventions(){const iv=MODEL.interventions||[]; const panel=$('intvpanel');
  if(!panel)return;
  const cur=MODEL.ticks[frame].t;
  if(!iv.length && !(window.IS_COCKPIT)){panel.style.display='none';return;}
  panel.style.display='block'; const d4=$('d4'); if(d4)d4.style.display='block';
  const overrides=iv.filter(x=>x.selected_by==='manual_override');
  const shown=overrides.filter(x=>x.t<=cur);
  $('intvlog').innerHTML = overrides.length
    ? `<div class="sub">${overrides.length} manual override(s) this run; `
      +`${shown.length} so far at the playhead.</div>`
      +shown.map(x=>{const at=x.target?(' at '+nm(x.target)):'';
        const llm=x.llm?` <span class="llmtag">via text: “${(x.llm.original_text||'')}”</span>`:'';
        return `<div class="ev intv"><span class="tt">${x.clock}</span><span>`
          +`<b>${nm(x.subject)}</b> ${fmt(x.user_selected_action)}${at} `
          +`<span class="sub">(engine would have: ${fmt(x.engine_would_have_selected)})</span>${llm}`
          +`</span></div>`;}).join('')
    : '<div class="ev amb">no overrides yet — the subject is autonomous.</div>';}

function select(p){selected=p;renderScene();renderCards();renderWhy();}
function render(){renderHeader();renderScene();renderCards();renderStream();renderMetrics();renderWhy();renderInterventions();drawPlayhead();}
function step(){frame=(frame+1)%MODEL.ticks.length;$('scrub').value=frame;render();}

function init(){
  if(asset('equilibrium_observatory_emblem.svg')){$('emblem').src=asset('equilibrium_observatory_emblem.svg');
    $('footemblem').src=asset('equilibrium_observatory_emblem.svg');}
  if(asset('icon_causality.svg'))$('whyicon').src=asset('icon_causality.svg');
  const SL=[['input','#9a6a16'],['your action (custom)','#1f7a72'],
    ['reaction (output)','#9a4a26'],['incident','#b5532e'],['behaviour','#6b5836']];
  $('streamleg').innerHTML=SL.map(([k,c])=>
    `<span><span class="dot" style="background:${c}"></span>${k}</span>`).join('');
  const dv=asset('divider_lantern_vine.svg');
  if(dv)['d1','d2','d3'].forEach(id=>$(id).style.setProperty('--div',`url('${dv}')`));
  else ['d1','d2','d3'].forEach(id=>$(id).classList.add('plain'));
  selected=MODEL.cast[0];
  const sc=$('scrub'); sc.max=MODEL.ticks.length-1; frame=Math.min(frame,MODEL.ticks.length-1); sc.value=frame;
  sc.oninput=()=>{frame=+sc.value;render();};
  $('devtoggle').onclick=e=>{dev=!dev;e.target.classList.toggle('on',dev);
    e.target.textContent=dev?'Observer view':'Developer view';renderCards();};
  const hb=$('hltoggle'); hb.classList.toggle('on',hilite);
  hb.onclick=e=>{hilite=!hilite;e.target.classList.toggle('on',hilite);renderStream();};
  $('play').onclick=e=>{playing=!playing;e.target.classList.toggle('on',playing);
    e.target.textContent=playing?'❚❚ pause':'▶ play';
    if(playing)timer=setInterval(step,90);else clearInterval(timer);};
  renderCycle(); buildRibbons(); render();
}
if(window.MODEL) init();
"""


def page(model: dict, assets: dict[str, str] | None = None,
         meta_subtitle: str | None = None) -> str:
    """A self-contained Observatory HTML page embedding `model` + the asset pack."""
    assets = assets if assets is not None else load_assets()
    if meta_subtitle:
        model = {**model, "meta": {**model.get("meta", {}), "subtitle": meta_subtitle}}
    data = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    adata = json.dumps(assets, ensure_ascii=False)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Living Inn Observatory</title>"
        "<style>" + STYLE + "</style><style>" + _asset_css(assets) + "</style></head>"
        "<body>" + BODY +
        "<script>window.ASSETS=" + adata + ";window.MODEL=" + data + ";</script>"
        "<script>" + SCRIPT + "</script></body></html>"
    )


def export_html(trace_dir: str | Path, out_html: str | Path,
                inn_yaml: str | Path | None = None, stride: int = 1) -> Path:
    """Build a self-contained Observatory page from a run's trace directory."""
    from inn.config import load_inn_config
    from inn.metrics import load_records

    trace_dir = Path(trace_dir)
    cfg = load_inn_config(inn_yaml or ROOT / "inn.yaml")
    records = load_records(trace_dir / "trace.jsonl.gz")
    session = {}
    sp = trace_dir / "session.json"
    if sp.is_file():
        session = json.loads(sp.read_text(encoding="utf-8"))
    model = O.build_model(records, cfg, meta={"source": str(trace_dir),
                          "session": session}, stride=stride)
    html = page(model, meta_subtitle=f"{trace_dir.name} · {len(records)} ticks")
    out_html = Path(out_html)
    out_html.write_text(html, encoding="utf-8")
    return out_html


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Export a run as a self-contained "
                                 "Living Inn Observatory HTML page.")
    ap.add_argument("trace_dir", help="directory containing trace.jsonl.gz")
    ap.add_argument("-o", "--out", default="observatory.html")
    ap.add_argument("--stride", type=int, default=1,
                    help="downsample the timeline (1 = full fidelity)")
    args = ap.parse_args(argv)
    p = export_html(args.trace_dir, args.out, stride=args.stride)
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
