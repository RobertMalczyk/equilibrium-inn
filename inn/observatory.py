"""The Living Inn Observatory (CLAUDE.md M-D, Phase 3): a beautiful, calm,
slightly-scientific window onto the engine's living world — an OBSERVATORY, not a
game (no quests/goals/score/inventory/combat). It renders the shared
ObservationModel (inn.observe.build_model) with hand-rolled inline SVG/Canvas/CSS
— no CDN, no network — so the same render layer serves two deliverables:

  * PRIMARY  — a Pyodide live cockpit (observatory/index.html) that runs the inn
               in-browser and calls build_model live; it imports STYLE/BODY/SCRIPT
               from here so there is ONE render layer.
  * SECONDARY — a self-contained HTML export of one run:
               python -m inn.observatory <trace_dir> -o run.html
               (embeds a CPython-built model as JSON; fully offline). This is the
               shareable report AND the mandated G2-parity fallback.

Everything shown comes from the trace via inn.observe (hard rule 0.4). No LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import inn.observe as O

# -- shared render layer (inlined by both deliverables) ------------------------

STYLE = """
:root{
  --parchment:#f3e9d2; --ink:#3a2f24; --muted:#7c6f5d; --line:#d8c9a8;
  --panel:#fbf4e3; --shadow:0 1px 3px rgba(80,60,30,.18);
  --idle:#c9b48f; --seeking:#d99a2b; --busy:#7c9e5e; --cooldown:#bd8a5a;
  --sleep:#6a79a6; --incident:#b5532e; --need:#caa24b; --affect:#b5683e;
  --sleepf:#6a79a6;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 50% -10%,#fbf3df,#ecdcb8);
  color:var(--ink);font:15px/1.5 "Iowan Old Style",Georgia,"Times New Roman",serif}
h1,h2,h3{font-weight:600;letter-spacing:.2px;margin:0}
.wrap{max-width:1180px;margin:0 auto;padding:22px}
.title{display:flex;align-items:baseline;gap:14px;margin-bottom:4px}
.title h1{font-size:27px}
.sub{color:var(--muted);font-style:italic}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:14px;margin:14px 0;
  padding:12px 16px;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;box-shadow:var(--shadow)}
.clock{font-size:22px;font-variant-numeric:tabular-nums}
.phase{padding:2px 10px;border-radius:20px;background:#efe2c2;border:1px solid var(--line)}
.grow{flex:1}
input[type=range]{width:100%;accent-color:#a9762f}
button{font:inherit;background:#efe2c2;border:1px solid var(--line);
  border-radius:8px;padding:5px 12px;cursor:pointer;color:var(--ink)}
button:hover{background:#e7d6ad}
button.on{background:#c9883a;color:#fff;border-color:#a9762f}
.grid{display:grid;gap:16px}
.cols{grid-template-columns:1.15fr .85fr}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;box-shadow:var(--shadow)}
.card h3{font-size:13px;text-transform:uppercase;letter-spacing:1.2px;
  color:var(--muted);margin-bottom:10px}
.scene{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.room{min-height:78px;background:#f7eed6;border:1px solid var(--line);
  border-radius:10px;padding:8px}
.room .rn{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted)}
.tok{display:inline-flex;align-items:center;gap:5px;margin:4px 5px 0 0;
  padding:3px 8px;border-radius:18px;background:#fff;border:1px solid var(--line);font-size:13px}
.dot{width:10px;height:10px;border-radius:50%}
.person{border-top:1px solid var(--line);padding:9px 0}
.person:first-child{border-top:0}
.prow{display:flex;align-items:center;gap:10px}
.pname{width:88px;font-weight:600}
.ptags{color:var(--muted);font-size:13px}
.gauges{display:grid;grid-template-columns:repeat(2,1fr);gap:3px 16px;margin-top:6px}
.g{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}
.g .lab{width:78px}
.gbar{flex:1;height:7px;background:#e9dcbd;border-radius:5px;overflow:hidden}
.gfill{height:100%;border-radius:5px}
.ribbons{overflow-x:auto}
.rib{display:flex;align-items:center;gap:8px;margin:3px 0}
.rib .pn{width:84px;font-size:13px;text-align:right;color:var(--muted)}
.stream{max-height:320px;overflow:auto;font-size:13px}
.ev{padding:4px 0;border-top:1px dotted var(--line);display:flex;gap:8px}
.ev .tt{color:var(--muted);font-variant-numeric:tabular-nums;width:48px;flex:none}
.ev.inc{color:var(--incident);font-weight:600}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.metric{background:#f7eed7;border:1px solid var(--line);border-radius:9px;padding:8px 10px}
.metric .v{font-size:21px}
.metric .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:5px}
.night body,.isnight{filter:saturate(.85)}
canvas{display:block}
"""

BODY = """
<div class="wrap">
  <div class="title"><h1>Living Inn Observatory</h1>
    <span class="sub" id="sub">watching the engine's living world</span></div>
  <div class="bar">
    <span class="clock" id="clock">--:--</span>
    <span class="phase" id="phase">—</span>
    <span class="phase" id="weather" style="display:none">rain</span>
    <span class="grow"></span>
    <button id="play">▶ play</button>
    <button id="devtoggle">Developer view</button>
  </div>
  <div class="bar" id="controls" style="display:none"></div>
  <div class="bar"><input type="range" id="scrub" min="0" max="0" value="0"></div>
  <div class="grid cols">
    <div class="card"><h3>The inn</h3><div class="scene" id="scene"></div>
      <div class="legend" id="legend" style="margin-top:10px"></div></div>
    <div class="card"><h3>Who, and how they feel</h3><div id="cards"></div></div>
  </div>
  <div class="card" style="margin-top:16px"><h3>Behavioural cycle — idle · seeking · busy · rest · sleep</h3>
    <div class="ribbons" id="ribbons"></div></div>
  <div class="grid cols" style="margin-top:16px">
    <div class="card"><h3>What is happening</h3><div class="stream" id="stream"></div></div>
    <div class="card"><h3>Validation metrics</h3><div class="metrics" id="metrics"></div></div>
  </div>
</div>
"""

SCRIPT = r"""
const MODE_COLOR={idle:'#c9b48f',seeking:'#d99a2b',busy:'#7c9e5e',
  cooldown:'#bd8a5a',sleep:'#6a79a6'};
const MOOD_COLOR={calm:'#8fae6e',focused:'#7c9e5e',bored:'#d9c24a',
  tired:'#bd8a5a',irritated:'#b5532e',resting:'#9aa6c4',sleeping:'#6a79a6'};
let frame=0, dev=false, playing=false, timer=null;
const $=id=>document.getElementById(id);

function phaseOf(clock,night){
  if(night) return 'night';
  const h=parseInt(clock.split(':')[0],10);
  if(h<9) return 'morning'; if(h<18) return 'workday'; return 'evening';
}
function fmt(s){return s.replace(/_/g,' ');}

function renderHeader(){
  const tk=MODEL.ticks[frame];
  $('clock').textContent='Day '+tk.day+'  '+tk.clock;
  $('phase').textContent=phaseOf(tk.clock,tk.night);
  $('weather').style.display=tk.rain?'inline':'none';
  document.body.classList.toggle('isnight',!!tk.night);
}

function renderScene(){
  const tk=MODEL.ticks[frame], byRoom={};
  MODEL.rooms.forEach(r=>byRoom[r]=[]);
  MODEL.cast.forEach(p=>{const r=tk.personas[p].room; if(byRoom[r])byRoom[r].push(p);});
  $('scene').innerHTML=MODEL.rooms.map(r=>{
    const toks=byRoom[r].map(p=>{const ps=tk.personas[p];
      return `<span class="tok"><span class="dot" style="background:${MOOD_COLOR[ps.mood]||'#aaa'}"></span>${MODEL.display_names[p]}</span>`;}).join('');
    return `<div class="room"><div class="rn">${fmt(r)}</div>${toks||'<span class="ptags">·</span>'}</div>`;
  }).join('');
  $('legend').innerHTML=Object.entries(MOOD_COLOR).map(([k,c])=>
    `<span><span class="dot" style="background:${c}"></span>${k}</span>`).join('');
}

function gauge(lab,v,fam){
  const col=fam==='affect'?'var(--affect)':fam==='sleep'?'var(--sleepf)':'var(--need)';
  return `<div class="g"><span class="lab">${lab}</span>
    <span class="gbar"><span class="gfill" style="width:${(v*100).toFixed(0)}%;background:${col}"></span></span>
    ${dev?'<span>'+v.toFixed(2)+'</span>':''}</div>`;
}
function renderCards(){
  const tk=MODEL.ticks[frame], fam=MODEL.state_families;
  const which=s=>fam.affect.includes(s)?'affect':fam.sleep.includes(s)?'sleep':'need';
  $('cards').innerHTML=MODEL.cast.map(p=>{
    const ps=tk.personas[p], states=dev?ps.raw:ps.states;
    const gs=Object.entries(states).map(([s,v])=>gauge(s,v,which(s))).join('');
    return `<div class="person"><div class="prow">
      <span class="dot" style="background:${MOOD_COLOR[ps.mood]||'#aaa'}"></span>
      <span class="pname">${MODEL.display_names[p]}</span>
      <span class="ptags">${ps.mood} · ${ps.mode}${ps.action&&ps.action!=='neutral'?' · '+fmt(ps.action):''}</span>
      </div><div class="gauges">${gs}</div></div>`;
  }).join('');
}

function buildRibbons(){
  const n=MODEL.ticks.length, w=Math.min(900,Math.max(360,n)), h=16;
  $('ribbons').innerHTML=MODEL.cast.map(p=>
    `<div class="rib"><span class="pn">${MODEL.display_names[p]}</span>
      <canvas data-p="${p}" width="${w}" height="${h}"></canvas></div>`).join('')
    +`<div class="rib"><span class="pn"></span><canvas id="axis" width="${w}" height="14"></canvas></div>`
    +`<div class="legend" style="margin-top:6px">`+
      Object.entries(MODE_COLOR).map(([k,c])=>`<span><span class="dot" style="background:${c}"></span>${k}</span>`).join('')+
      ` <span><span class="dot" style="background:var(--incident)"></span>incident</span></div>`;
  document.querySelectorAll('#ribbons canvas[data-p]').forEach(cv=>{
    const p=cv.dataset.p, ctx=cv.getContext('2d'), W=cv.width, H=cv.height;
    for(let i=0;i<n;i++){const m=MODEL.ticks[i].personas[p].mode;
      ctx.fillStyle=MODEL.ticks[i].night?'#e6dcc2':(MODE_COLOR[m]||'#ccc');
      ctx.fillRect(i/n*W,0,Math.ceil(W/n)+0.6,H);}
    ctx.fillStyle='#b5532e';
    MODEL.incidents.forEach(inc=>{const i=tickIndex(inc.t); if(i<0)return;
      ctx.fillRect(i/n*W,0,2,H);});
  });
  drawPlayhead();
}
function drawPlayhead(){
  const n=MODEL.ticks.length, ax=$('axis'); if(!ax)return;
  const ctx=ax.getContext('2d'); ctx.clearRect(0,0,ax.width,ax.height);
  ctx.fillStyle='#3a2f24'; ctx.fillRect(frame/n*ax.width,0,2,ax.height);
  ctx.fillStyle='#7c6f5d'; ctx.font='10px Georgia';
  MODEL.days.forEach(d=>{const i=MODEL.ticks.findIndex(t=>t.day===d);
    if(i>=0)ctx.fillText('day '+d,i/n*ax.width+3,11);});
}
function tickIndex(t){
  let best=-1; for(let i=0;i<MODEL.ticks.length;i++){if(MODEL.ticks[i].t<=t)best=i;else break;}
  return best;
}

function renderStream(){
  const cur=MODEL.ticks[frame].t;
  const items=[];
  MODEL.ticks.forEach(tk=>{if(tk.event)items.push({t:tk.t,clock:tk.clock,txt:tk.event,inc:false});});
  MODEL.incidents.forEach(i=>items.push({t:i.t,clock:i.clock,txt:MODEL.display_names[i.actor]+' — '+i.action,inc:true}));
  MODEL.transitions.filter(x=>['SEEKING','BUSY','SLEEP'].includes(x.new)&&x.driver).forEach(x=>
    items.push({t:x.t,clock:x.clock,txt:MODEL.display_names[x.pid]+' '+x.prev.toLowerCase()+'→'+x.new.toLowerCase()+(x.driver?' ('+x.driver+' '+x.driver_value+')':''),inc:false}));
  items.sort((a,b)=>a.t-b.t);
  $('stream').innerHTML=items.map(it=>
    `<div class="ev ${it.inc?'inc':''}" style="opacity:${it.t<=cur?1:.32}">
      <span class="tt">${it.clock}</span><span>${it.txt}</span></div>`).join('')||'<div class="ev">quiet…</div>';
  const active=[...$('stream').querySelectorAll('.ev')].reverse().find(e=>parseFloat(e.style.opacity)===1);
  if(active)active.scrollIntoView({block:'nearest'});
}

function renderMetrics(){
  const m=MODEL.metrics;
  const cells=[['incidents',m.incidents],['cascade depth',m.cascade_max_depth],
    ['activity success',m.activity_success_rate==null?'—':(m.activity_success_rate*100).toFixed(0)+'%'],
    ['offers',m.offers_total],['contention',m.contention_total],
    ['recovery ticks',m.recovery_ticks_mean==null?'—':m.recovery_ticks_mean]];
  // average time budget across cast
  const tb={}; MODEL.cast.forEach(p=>{const b=m.time_budget[p]||{};
    Object.entries(b).forEach(([k,v])=>tb[k]=(tb[k]||0)+v/MODEL.cast.length);});
  ['busy','idle','seeking','sleep'].forEach(k=>{if(tb[k]!=null)cells.push(['avg '+k,(tb[k]*100).toFixed(0)+'%']);});
  $('metrics').innerHTML=cells.map(([k,v])=>
    `<div class="metric"><div class="v">${v}</div><div class="k">${k}</div></div>`).join('');
}

function render(){renderHeader();renderScene();renderCards();renderStream();renderMetrics();drawPlayhead();}

function step(){frame=(frame+1)%MODEL.ticks.length;$('scrub').value=frame;render();}
function init(){
  $('sub').textContent=(MODEL.meta&&MODEL.meta.subtitle)||$('sub').textContent;
  const sc=$('scrub'); sc.max=MODEL.ticks.length-1;
  sc.oninput=()=>{frame=+sc.value;render();};
  $('devtoggle').onclick=e=>{dev=!dev;e.target.classList.toggle('on',dev);
    e.target.textContent=dev?'Observer view':'Developer view';renderCards();};
  $('play').onclick=e=>{playing=!playing;e.target.classList.toggle('on',playing);
    e.target.textContent=playing?'❚❚ pause':'▶ play';
    if(playing)timer=setInterval(step,90);else clearInterval(timer);};
  buildRibbons(); render();
}
if(window.MODEL) init();
"""


def page(model: dict, meta_subtitle: str | None = None) -> str:
    """A self-contained Observatory HTML page embedding `model` (static export)."""
    if meta_subtitle:
        model = {**model, "meta": {**model.get("meta", {}), "subtitle": meta_subtitle}}
    data = json.dumps(model, ensure_ascii=False, separators=(",", ":"))
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Living Inn Observatory</title><style>" + STYLE + "</style></head>"
        "<body>" + BODY +
        "<script>window.MODEL=" + data + ";</script>"
        "<script>" + SCRIPT + "</script></body></html>"
    )


def export_html(trace_dir: str | Path, out_html: str | Path,
                inn_yaml: str | Path | None = None, stride: int = 1) -> Path:
    """Build a self-contained Observatory page from a run's trace directory."""
    from inn.config import load_inn_config
    from inn.metrics import load_records

    trace_dir = Path(trace_dir)
    root = Path(__file__).resolve().parents[1]
    cfg = load_inn_config(inn_yaml or root / "inn.yaml")
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
