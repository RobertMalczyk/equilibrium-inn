"""Time Plots — an engine-study instrument (CLAUDE.md M-J).

A self-contained page of time-series line plots over a run's society trace, built
to *read the engine's dynamics*: the fast spike-and-vent of the affect states
around an incident, and — on the same x-axis — the slow, permanent relational mark
the incident leaves behind. It complements the Observatory's mode-ribbon
abstraction with the raw state trajectories.

Design (grilled & locked 2026-06-17; see registers/m_j_timeplots_plan.md):
  * Incidents are the spine: overview strip + brush/zoom focus, tiered incident
    markers (outburst = bold, S3 social events = faint near-misses).
  * Faceted small-multiples sharing ONE time-window: one chart per state, all
    personas overlaid (color = persona). 7 high-signal facets open by default.
  * Full-resolution state series embedded (no build-time downsampling — zoom must
    stay sharp); relations sampled coarsely (they move on 28-42 h half-lives).
  * x-axis in in-world Day/HH:MM; raw tick in the hover readout.
  * Persona colors from inn.yaml cast[].color, generated hue-ramp fallback.
  * Shared render layer (this module's STYLE/BODY/SCRIPT). Its primary home is a
    live "Time plots" TAB in the Pyodide cockpit (observatory/build_bundle.py),
    rendering the run you are watching on the Observatory tab. The same layer also
    powers a developer CLI export of a single trace (below) — handy offline, not a
    published site page.

Hard rules: reads ONLY the society trace (rule 0.4); pure analysis + rendering, no
dynamics, no LLM, engine repo untouched. The golden trace is unaffected.

  python -m inn.timeplots <trace_dir> -o plots.html   # dev/offline export
"""

from __future__ import annotations

import json
from pathlib import Path

import inn.observatory as OB  # reuse the asset pack + theme CSS for visual consistency

ROOT = Path(__file__).resolve().parents[1]

# State facets. Order = display order; the 7 high-signal ones open by default
# (DEC: anger/stress/frustration/self_control/sleep_pressure/boredom + room_tension),
# the remaining global states collapsed. room_tension is a single WORLD line, not
# per-persona, and is rendered as its own facet kind.
PERSONA_STATES_OPEN = ("anger", "stress", "frustration", "self_control",
                       "sleep_pressure", "boredom")
PERSONA_STATES_COLLAPSED = ("duty", "hunger", "satisfaction")
RELATION_STRIDE = 4          # relations move slowly; ~8 min sampling loses nothing
RELATION_EPSILON = 0.02      # a directed channel "moved" if max-min exceeds this


def _mins(clock: str) -> int:
    h, m = clock.split(":")
    return int(h) * 60 + int(m)


def _runs(records: list[dict], key: str) -> list[list[int]]:
    """Contiguous [start_t, end_t] tick spans where rec[key] is truthy."""
    spans: list[list[int]] = []
    start = None
    for rec in records:
        if rec.get(key):
            if start is None:
                start = rec["t"]
            last = rec["t"]
        elif start is not None:
            spans.append([start, last])
            start = None
    if start is not None:
        spans.append([start, last])
    return spans


def _hue_ramp(ids: list[str]) -> dict[str, str]:
    """Deterministic evenly-spaced hues, fixed S/L tuned to read on parchment.
    Used only as the fallback when a cast entry omits an explicit color."""
    n = max(1, len(ids))
    out = {}
    for i, pid in enumerate(ids):
        hue = round(360 * i / n)
        out[pid] = f"hsl({hue},58%,42%)"
    return out


def _resolve_colors(cfg) -> dict[str, str]:
    ids = [c.id for c in cfg.cast]
    fallback = _hue_ramp(ids)
    return {c.id: (c.color or fallback[c.id]) for c in cfg.cast}


def _relations(records: list[dict], cast: list[str]) -> dict:
    """Per directed (src -> dst) relation channel, a coarsely-sampled series.
    Returns {'moved': [...], 'flat': [...]} where each entry is
    {src, dst, channel, series:[...]} for moved channels and a flat summary for
    the rest. Forward/back-filled so a channel that appears mid-run draws cleanly.
    Sampled at RELATION_STRIDE (relations have 28-42 h half-lives — fine coarse)."""
    sampled = records[::RELATION_STRIDE]
    # collect raw values with None for "channel absent at this sample"
    raw: dict[tuple[str, str, str], list] = {}
    for rec in sampled:
        for src in cast:
            tt = rec["personas"].get(src)
            if not tt:
                continue
            rels = tt["state_after_post"]["relations"]
            for dst, chans in rels.items():
                for ch, v in chans.items():
                    raw.setdefault((src, dst, ch), [None] * len(sampled))
    # second pass to place values at their sample index
    for k in raw:
        src, dst, ch = k
        for j, rec in enumerate(sampled):
            tt = rec["personas"].get(src)
            if not tt:
                continue
            v = tt["state_after_post"]["relations"].get(dst, {}).get(ch)
            if v is not None:
                raw[k][j] = round(float(v), 4)

    def _fill(xs: list) -> list[float]:
        last = None
        for j in range(len(xs)):           # forward fill
            if xs[j] is None:
                xs[j] = last
            else:
                last = xs[j]
        first = next((x for x in xs if x is not None), 0.0)
        return [first if x is None else x for x in xs]   # back fill the head

    moved, flat = [], []
    for (src, dst, ch), xs in raw.items():
        ser = _fill(xs)
        span = (max(ser) - min(ser)) if ser else 0.0
        entry = {"src": src, "dst": dst, "channel": ch}
        if span > RELATION_EPSILON:
            moved.append({**entry, "series": ser})
        else:
            flat.append({**entry, "value": round(ser[-1] if ser else 0.0, 3)})
    moved.sort(key=lambda e: (max(e["series"]) - min(e["series"])), reverse=True)
    return {"moved": moved, "flat": flat,
            "stride": RELATION_STRIDE, "n_samples": len(sampled)}


def build_plot_model(records: list[dict], cfg, meta: dict | None = None,
                     dt: float | None = None) -> dict:
    """A compact, self-contained model of a run's state trajectories for the time
    plots. Pure read over the trace (hard rule 0.4).

    `dt` (seconds per in-world tick) is recorded for the page's tick-resolution
    readout; None when unknown (display metadata only — curves are unaffected)."""
    from inn.metrics import state_series

    cast = [c.id for c in cfg.cast]
    states = PERSONA_STATES_OPEN + PERSONA_STATES_COLLAPSED
    series_raw = state_series(records, states)
    # quantize to 3 decimals to keep the embed lean without losing curve shape
    series = {pid: {st: [round(v, 3) for v in xs] for st, xs in d.items()}
              for pid, d in series_raw.items()}

    ticks = [rec["t"] for rec in records]
    day = [rec["day"] for rec in records]
    mins = [_mins(rec["clock"]) for rec in records]
    days = sorted({rec["day"] for rec in records})

    # day boundaries (first tick-index of each day) for axis gridlines
    day_starts = {}
    for i, d in enumerate(day):
        day_starts.setdefault(d, i)

    world = {"room_tension": {}}
    for rec in records:
        for room, v in (rec.get("world", {}).get("room_tension", {}) or {}).items():
            world["room_tension"].setdefault(room, []).append(round(float(v), 3))

    # tiered incident markers: outburst = the spine (tier 'incident'); the S3
    # social events (refusal/complaint/cold_reply) = faint near-misses ('social').
    seen: set[str] = set()
    incidents = []
    idx_of = {t: i for i, t in enumerate(ticks)}
    for rec in records:
        for tr in rec["transductions"]:
            eid = tr["event_id"]
            if eid in seen:
                continue
            seen.add(eid)
            incidents.append({
                "t": rec["t"], "i": idx_of[rec["t"]], "day": rec["day"],
                "clock": rec["clock"], "actor": tr["actor"],
                "target": tr.get("recipient") or tr.get("target_inferred"),
                "action": tr["action"], "as": tr.get("as"),
                "intensity": round(float(tr.get("intensity", 0.0)), 3),
                "provoked_by": tr.get("provoked_by"),
                "tier": "incident" if tr["action"] == "outburst" else "social",
            })

    return {
        "meta": meta or {},
        "cast": cast,
        "display_names": {c: c.capitalize() for c in cast},
        "colors": _resolve_colors(cfg),
        "dt": dt,                       # seconds/tick (resolution readout); None if unknown
        "n": len(records),
        "ticks": ticks,
        "day": day,
        "mins": mins,
        "days": days,
        "day_starts": day_starts,
        "night": _runs(records, "night"),
        "rain": _runs(records, "rain"),
        "states_open": list(PERSONA_STATES_OPEN),
        "states_collapsed": list(PERSONA_STATES_COLLAPSED),
        "series": series,
        "world": world,
        "incidents": incidents,
        "relations": _relations(records, cast),
    }


# -- the shared render layer (Canvas; host-agnostic) ---------------------------

PLOT_STYLE = """
.tp{position:relative;z-index:1}
.tp .tpbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:10px 0;
  padding:9px 14px;border-radius:12px;border:1px solid var(--line);box-shadow:var(--shadow);
  background:var(--a-panel,var(--panel));background-size:cover;background-blend-mode:overlay}
.tp .tpbar .grow{flex:1}
.tp .ovwrap{border:1px solid var(--line);border-radius:12px;padding:8px 10px 4px;
  background:var(--panel);box-shadow:var(--shadow);margin-bottom:8px}
.tp .ovwrap .ovh{font-size:11px;text-transform:uppercase;letter-spacing:1.1px;color:var(--muted);
  margin-bottom:4px}
.tp canvas{display:block;width:100%;cursor:crosshair}
.tp .legend{display:flex;flex-wrap:wrap;gap:8px;font-size:12px;color:var(--ink);
  margin:7px 0;padding:8px 11px;background:var(--panel);border:1px solid var(--line);
  border-radius:10px;box-shadow:var(--shadow)}
.tp .legend .pl,.tp .legend .mk{background:#fffdf6;border:1px solid var(--line);
  border-radius:14px;padding:2px 9px}
.tp .legend .pl{display:inline-flex;align-items:center;gap:5px;cursor:pointer;user-select:none}
.tp .legend .pl.off{opacity:.4;text-decoration:line-through}
.tp .legend .sw{width:13px;height:4px;border-radius:3px}
.tp .legend .mk{display:inline-flex;align-items:center;gap:5px}
.tp .legend .mk i{display:inline-block;width:3px;height:13px;border-radius:1px}
.tp .facets{display:grid;gap:11px;grid-template-columns:repeat(auto-fit,minmax(330px,1fr))}
.tp .facet{border:1px solid var(--line);border-radius:11px;background:var(--panel);
  box-shadow:var(--shadow);overflow:hidden}
.tp .facet h4{margin:0;font-size:12px;font-weight:600;letter-spacing:.4px;color:var(--ink);
  padding:7px 11px;cursor:pointer;display:flex;align-items:center;gap:7px;
  border-bottom:1px solid var(--line);background:#f7eed7}
.tp .facet h4 .car{color:var(--muted);font-size:11px;width:11px}
.tp .facet h4 .rng{margin-left:auto;color:var(--muted);font-weight:400;font-size:11px;
  font-variant-numeric:tabular-nums}
.tp .facet .body{padding:6px 9px 9px}
.tp .facet.closed .body{display:none}
.tp details.relwrap{margin-top:12px;border:1px solid var(--line);border-radius:11px;
  background:var(--panel);box-shadow:var(--shadow);padding:6px 12px}
.tp details.relwrap summary{cursor:pointer;font-size:12.5px;font-weight:600;color:var(--ink);padding:4px 0}
.tp details.relwrap .sub{color:var(--muted);font-size:12px;margin:4px 0 8px}
.tp .flatpairs{font-size:11.5px;color:var(--muted);line-height:1.6;margin-top:8px}
.tp .rdt{position:fixed;z-index:70;background:#2a2018;color:#f3e9d2;font-size:11.5px;
  line-height:1.5;padding:7px 9px;border-radius:8px;pointer-events:none;display:none;
  box-shadow:0 5px 16px rgba(0,0,0,.32);max-width:240px}
.tp .rdt b{color:#7fd6da}.tp .rdt .hd{color:#f0e2c2;font-weight:600;margin-bottom:3px}
.tp .rdt .rv{display:flex;justify-content:space-between;gap:10px}
.tp .rdt .rv .sw{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px}
.tp .hint{font-size:12px;color:var(--muted);margin:4px 2px}
"""


def plot_body(root_id: str = "tp", with_selector: bool = True) -> str:
    """The plot UI markup inside #<root_id>. with_selector adds the protocol
    picker (static page only — the cockpit feeds a single live model)."""
    sel = ('<label>protocol <select id="%s_proto"></select></label>' % root_id
           if with_selector else "")
    return f"""
<div class="tp" id="{root_id}">
  <div class="tpbar">
    {sel}
    <button data-tp="full">⤢ Full run</button>
    <button data-tp="zoomout">– Zoom out</button>
    <button data-tp="prev">‹ Prev incident</button>
    <button data-tp="next">Next incident ›</button>
    <button data-tp="fit" title="Fit Y: rescale each facet's vertical axis to the data visible in the current window, so low-amplitude curves (e.g. anger 0.06–0.29) fill the chart instead of hugging the bottom of the 0–1 axis. Toggle off for absolute 0–1.">⤢ Fit Y</button>
    <label title="What hovering highlights: the incident under the cursor, the per-persona values at that instant, or — as now — both depending on whether you are over an incident marker.">highlight
      <select data-tp-hover>
        <option value="both">both (auto)</option>
        <option value="incident">incident</option>
        <option value="values">values</option>
      </select></label>
    <span class="grow"></span>
    <span class="hint" data-tp-dt></span>
    <span class="hint">Drag on the overview to zoom · click an incident marker to focus it</span>
  </div>
  <div class="ovwrap">
    <div class="ovh">whole run — drag to set the window · ▌outburst ·│social event · night shaded · rain banded · x-axis: in-world time (Day HH:MM)</div>
    <canvas data-tp-ov width="1180" height="64"></canvas>
  </div>
  <div class="legend" data-tp-legend></div>
  <div class="facets" data-tp-facets></div>
  <details class="relwrap" data-tp-rel>
    <summary>Relations — grudges &amp; trust over time (slow; pairs that moved)</summary>
    <div class="sub">The fast affect states above vent within hours; the relational
      mark an incident leaves persists on 28-42 h half-lives. Only directed pairs
      whose relation actually moved are plotted (sampled coarsely).</div>
    <div class="facets" data-tp-relfacets></div>
    <div class="flatpairs" data-tp-flat></div>
  </details>
  <div class="rdt" data-tp-rdt></div>
</div>
"""


PLOT_SCRIPT = r"""
(function(){
const TP={pm:null,lo:0,hi:0,muted:{},open:{},rootSel:null,hoverMode:'both',autoscale:false};
function $(root,q){return root.querySelector(q);}
function hhmm(m){const h=(m/60|0),mm=m%60;return (h<10?'0':'')+h+':'+(mm<10?'0':'')+mm;}
function nm(id){return (TP.pm.display_names&&TP.pm.display_names[id])||id;}
function labelAt(i){const pm=TP.pm;return 'Day '+pm.day[i]+' '+hhmm(pm.mins[i]);}

// device-pixel-ratio aware sizing so canvases stay crisp and match CSS width
function fit(cv){const dpr=window.devicePixelRatio||1, w=cv.clientWidth||cv.width;
  const h=parseInt(cv.getAttribute('height'),10);
  cv.width=Math.round(w*dpr); cv.height=Math.round(h*dpr);
  const ctx=cv.getContext('2d'); ctx.setTransform(dpr,0,0,dpr,0,0);
  return {ctx,w:w,h:h};}

// draw a series within window [lo,hi] into rect, decimating via a min/max
// envelope per pixel column so spikes survive any zoom level.
function drawSeries(ctx,arr,lo,hi,x0,y0,w,h,color,ymin,ymax){
  const n=hi-lo+1; if(n<=0)return;
  const Y=v=>y0+h-(Math.max(ymin,Math.min(ymax,v))-ymin)/(ymax-ymin)*h;
  ctx.strokeStyle=color; ctx.lineWidth=1.4; ctx.beginPath();
  if(n<=w){                                   // sparse: a clean polyline
    for(let k=0;k<n;k++){const i=lo+k, px=x0+(n===1?0:k/(n-1)*w), py=Y(arr[i]);
      k?ctx.lineTo(px,py):ctx.moveTo(px,py);} ctx.stroke();
  } else {                                    // dense: min/max envelope per column
    for(let px=0;px<w;px++){
      const i0=lo+Math.floor(px/w*n), i1=lo+Math.floor((px+1)/w*n);
      let mn=Infinity,mx=-Infinity;
      for(let i=i0;i<i1;i++){const v=arr[i]; if(v<mn)mn=v; if(v>mx)mx=v;}
      if(mn===Infinity)continue;
      ctx.moveTo(x0+px+0.5,Y(mx)); ctx.lineTo(x0+px+0.5,Y(mn));}
    ctx.stroke();
  }
}
function bands(ctx,spans,lo,hi,x0,y0,w,h,fill){const pm=TP.pm;
  ctx.fillStyle=fill;
  spans.forEach(s=>{const a=Math.max(lo,idxOfT(s[0])),b=Math.min(hi,idxOfT(s[1]));
    if(b<a)return; const px=x0+(a-lo)/(hi-lo)*w, pw=Math.max(1,(b-a)/(hi-lo)*w);
    ctx.fillRect(px,y0,pw,h);});}
function idxOfT(t){const pm=TP.pm; let best=0;
  for(let i=0;i<pm.ticks.length;i++){if(pm.ticks[i]<=t)best=i;else break;} return best;}

function facetArrays(f){const pm=TP.pm;
  if(f.kind==='world')return [{id:'__rt',color:'#8a5a2e',arr:pm.world.room_tension[f.room]}];
  if(f.kind==='rel')return [{id:'__rel',color:relColor(f.channel),arr:f.series,stride:pm.relations.stride}];
  return pm.cast.filter(p=>!TP.muted[p]).map(p=>({id:p,color:pm.colors[p],arr:pm.series[p][f.key]}));}
function relColor(ch){return ch==='resentment'?'#b5532e':ch==='trust'?'#3d7a8a':ch==='respect'?'#7c9e5e':'#8a6a2e';}
// y-axis range for a facet: absolute 0..1, or (Fit Y) the visible data range padded.
function yRange(f,lo,hi){ if(!TP.autoscale) return [0,1];
  let mn=Infinity,mx=-Infinity;
  facetArrays(f).forEach(s=>{if(!s.arr)return;
    if(s.stride){const a=Math.max(0,Math.floor(lo/s.stride)),b=Math.min(s.arr.length-1,Math.ceil(hi/s.stride));
      for(let j=a;j<=b;j++){const v=s.arr[j]; if(v<mn)mn=v; if(v>mx)mx=v;}}
    else for(let i=lo;i<=hi;i++){const v=s.arr[i]; if(v<mn)mn=v; if(v>mx)mx=v;}});
  if(mn===Infinity)return [0,1];
  if(mx-mn<1e-6){return [Math.max(0,mn-0.05),Math.min(1,mn+0.05)];}   // flat -> small band
  const pad=(mx-mn)*0.1; return [Math.max(0,mn-pad), Math.min(1,mx+pad)];
}

const AXIS_H=13;   // bottom strip reserved for the x-axis (in-world time) labels
function drawFacet(cv,f){const {ctx,w,h}=fit(cv); const pm=TP.pm, lo=TP.lo, hi=TP.hi;
  ctx.clearRect(0,0,w,h);
  const x0=2,y0=2,W=w-4,H=(h-4)-AXIS_H;   // H = plot area; the rest is the time axis
  bands(ctx,pm.night,lo,hi,x0,y0,W,H,'rgba(40,30,80,.07)');
  bands(ctx,pm.rain,lo,hi,x0,y0,W,H,'rgba(70,90,150,.10)');
  // y range: absolute 0..1, or — with Fit Y — the visible data range so low-amplitude
  // curves fill the chart instead of hugging the bottom.
  const yr=yRange(f,lo,hi), ymin=yr[0], ymax=yr[1];
  ctx.strokeStyle='rgba(120,110,90,.18)'; ctx.lineWidth=1;
  ctx.fillStyle='#9b9079'; ctx.font='8px Georgia'; ctx.textBaseline='alphabetic';
  [ymin,(ymin+ymax)/2,ymax].forEach(v=>{const y=y0+H-(v-ymin)/(ymax-ymin)*H;
    ctx.beginPath();ctx.moveTo(x0,y);ctx.lineTo(x0+W,y);ctx.stroke();});
  // y value labels (top = ymax, bottom = ymin) so the scale is legible when fitted
  ctx.fillText(ymax.toFixed(2), x0+2, y0+8);
  ctx.fillText(ymin.toFixed(2), x0+2, y0+H-2);
  // day boundaries within the window
  ctx.strokeStyle='rgba(120,110,90,.4)';
  pm.days.forEach(d=>{const i=pm.day_starts[d]; if(i>=lo&&i<=hi){
    const px=x0+(i-lo)/(hi-lo)*W; ctx.beginPath();ctx.moveTo(px,y0);ctx.lineTo(px,y0+H);ctx.stroke();}});
  // incident markers (tiered) within the window
  pm.incidents.forEach(inc=>{if(inc.i<lo||inc.i>hi)return;
    const px=x0+(inc.i-lo)/(hi-lo)*W;
    ctx.strokeStyle=inc.tier==='incident'?'rgba(181,83,46,.85)':'rgba(169,118,47,.45)';
    ctx.lineWidth=inc.tier==='incident'?2:1; ctx.beginPath();ctx.moveTo(px,y0);ctx.lineTo(px,y0+H);ctx.stroke();});
  // the lines
  facetArrays(f).forEach(s=>{if(!s.arr)return;
    if(s.stride){ // relation series live on a coarser index grid -> map to ticks
      drawRelSeries(ctx,s.arr,s.stride,lo,hi,x0,y0,W,H,s.color,ymin,ymax);
    } else drawSeries(ctx,s.arr,lo,hi,x0,y0,W,H,s.color,ymin,ymax);});
  drawTimeAxis(ctx,x0,y0+H,W,AXIS_H);   // x-axis in-world time scale for THIS window
  cv._f=f;
}
// x-axis time scale: evenly spaced Day HH:MM ticks across the current window. The
// left label carries the day; interior labels are HH:MM (day shown again if it rolls).
function drawTimeAxis(ctx,x0,yTop,W,H){const pm=TP.pm, lo=TP.lo, hi=TP.hi;
  ctx.strokeStyle='rgba(120,110,90,.30)';ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(x0,yTop+0.5);ctx.lineTo(x0+W,yTop+0.5);ctx.stroke();
  ctx.fillStyle='#7c6f5d';ctx.font='9px Georgia';ctx.textBaseline='alphabetic';
  const N=5; let lastDay=null;
  for(let k=0;k<N;k++){const f=k/(N-1), i=Math.round(lo+f*(hi-lo));
    const px=x0+f*W; ctx.strokeStyle='rgba(120,110,90,.30)';
    ctx.beginPath();ctx.moveTo(px,yTop);ctx.lineTo(px,yTop+3);ctx.stroke();
    const d=pm.day[i], lab=(d!==lastDay?('D'+d+' '):'')+hhmm(pm.mins[i]); lastDay=d;
    ctx.textAlign=k===0?'left':k===N-1?'right':'center';
    ctx.fillText(lab, k===0?x0:k===N-1?x0+W:px, yTop+11);}
  ctx.textAlign='left';
}
// relation arrays are sampled every `stride` ticks; expand index space to ticks.
function drawRelSeries(ctx,arr,stride,lo,hi,x0,y0,w,h,color,ymin,ymax){
  const pm=TP.pm, N=pm.n;
  const Y=v=>y0+h-(Math.max(ymin,Math.min(ymax,v))-ymin)/(ymax-ymin)*h;
  ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.beginPath();let started=false;
  for(let j=0;j<arr.length;j++){const i=Math.min(N-1,j*stride);
    if(i<lo-stride||i>hi+stride)continue;
    const px=x0+(i-lo)/(hi-lo)*w, py=Y(arr[j]);
    started?ctx.lineTo(px,py):ctx.moveTo(px,py);started=true;}
  ctx.stroke();}

function drawOverview(){const root=document.querySelector(TP.rootSel);
  const cv=$(root,'[data-tp-ov]'); const {ctx,w,h}=fit(cv); const pm=TP.pm;
  ctx.clearRect(0,0,w,h);
  const x0=0,y0=0,W=w,H=h, n0=0,n1=pm.n-1;
  // full-run bands
  const fb=(spans,fill)=>{ctx.fillStyle=fill;spans.forEach(s=>{const a=idxOfT(s[0]),b=idxOfT(s[1]);
    const px=a/(pm.n-1)*W,pw=Math.max(1,(b-a)/(pm.n-1)*W);ctx.fillRect(px,0,pw,H);});};
  fb(pm.night,'rgba(40,30,80,.10)'); fb(pm.rain,'rgba(70,90,150,.13)');
  // day labels
  ctx.fillStyle='#7c6f5d';ctx.font='10px Georgia';
  pm.days.forEach(d=>{const i=pm.day_starts[d],px=i/(pm.n-1)*W;
    ctx.strokeStyle='rgba(120,110,90,.4)';ctx.beginPath();ctx.moveTo(px,0);ctx.lineTo(px,H);ctx.stroke();
    ctx.fillText('day '+d,px+3,11);});
  // a faint composite of mean stress to give the strip some life
  // (light gray envelope; orientation only)
  // incident markers (tiered)
  pm.incidents.forEach(inc=>{const px=inc.i/(pm.n-1)*W;
    ctx.strokeStyle=inc.tier==='incident'?'rgba(181,83,46,.9)':'rgba(169,118,47,.5)';
    ctx.lineWidth=inc.tier==='incident'?2:1;ctx.beginPath();
    ctx.moveTo(px,inc.tier==='incident'?0:H*0.35);ctx.lineTo(px,H);ctx.stroke();});
  // whole-run x-axis time scale: HH:MM (with the day) every ~12 h along the bottom.
  ctx.fillStyle='#6b5836';ctx.font='9px Georgia';ctx.textBaseline='alphabetic';
  const HALF=Math.max(1,Math.round((pm.n-1)/(pm.days.length*2)));  // ~12h in ticks
  let lastD=null;
  for(let i=0;i<pm.n;i+=HALF){const px=i/(pm.n-1)*W;
    ctx.strokeStyle='rgba(120,110,90,.28)';ctx.beginPath();ctx.moveTo(px,H-9);ctx.lineTo(px,H);ctx.stroke();
    const d=pm.day[i], lab=(d!==lastD?('D'+d+' '):'')+hhmm(pm.mins[i]); lastD=d;
    ctx.textAlign=i===0?'left':'center'; ctx.fillText(lab, i===0?2:px, H-1);}
  ctx.textAlign='left';
  // the current window highlight
  const a=TP.lo/(pm.n-1)*W,b=TP.hi/(pm.n-1)*W;
  ctx.fillStyle='rgba(201,136,58,.16)';ctx.fillRect(a,0,Math.max(2,b-a),H);
  ctx.strokeStyle='#a9762f';ctx.lineWidth=1.5;ctx.strokeRect(a+0.5,0.5,Math.max(2,b-a),H-1);
  cv._W=W;
}

function facetSpecs(){const pm=TP.pm; const specs=[];
  pm.states_open.forEach(k=>specs.push({key:k,label:k,kind:'state',open:true}));
  // room_tension world facet sits with the open group
  Object.keys(pm.world.room_tension||{}).forEach(room=>
    specs.push({key:'rt_'+room,label:'room tension · '+room.replace(/_/g,' '),kind:'world',room:room,open:true}));
  pm.states_collapsed.forEach(k=>specs.push({key:k,label:k,kind:'state',open:false}));
  return specs;}

function buildFacets(){const root=document.querySelector(TP.rootSel);
  const host=$(root,'[data-tp-facets]'); host.innerHTML='';
  facetSpecs().forEach(f=>{
    if(TP.open[f.key]===undefined)TP.open[f.key]=f.open;
    const div=document.createElement('div'); div.className='facet'+(TP.open[f.key]?'':' closed');
    div.innerHTML=`<h4><span class="car">${TP.open[f.key]?'▾':'▸'}</span>${f.label}
      <span class="rng"></span></h4><div class="body"><canvas height="120"></canvas></div>`;
    host.appendChild(div);
    const cv=$(div,'canvas');
    $(div,'h4').onclick=()=>{TP.open[f.key]=!TP.open[f.key];
      div.classList.toggle('closed',!TP.open[f.key]);
      $(div,'.car').textContent=TP.open[f.key]?'▾':'▸';
      if(TP.open[f.key]){drawFacet(cv,f);}};
    attachHover(cv);
    div._cv=cv; div._f=f;
    if(TP.open[f.key])requestAnimationFrame(()=>drawFacet(cv,f));
  });
}

function buildRelFacets(){const root=document.querySelector(TP.rootSel);
  const host=$(root,'[data-tp-relfacets]'); if(!host)return; host.innerHTML='';
  const moved=(TP.pm.relations&&TP.pm.relations.moved)||[];
  moved.forEach(m=>{const div=document.createElement('div');div.className='facet';
    div.innerHTML=`<h4>${nm(m.src)} → ${nm(m.dst)} · ${m.channel}
      <span class="rng" style="color:${relColor(m.channel)}">●</span></h4>
      <div class="body"><canvas height="110"></canvas></div>`;
    host.appendChild(div);
    const cv=$(div,'canvas'); const f={kind:'rel',channel:m.channel,series:m.series,
      label:nm(m.src)+'→'+nm(m.dst)+' '+m.channel};
    attachHover(cv); div._cv=cv; div._f=f;
    requestAnimationFrame(()=>drawFacet(cv,f));});
  const flat=(TP.pm.relations&&TP.pm.relations.flat)||[];
  $(root,'[data-tp-flat]').textContent = flat.length
    ? flat.length+' other directed relation(s) stayed flat this run (e.g. '
      +flat.slice(0,6).map(e=>`${nm(e.src)}→${nm(e.dst)} ${e.channel} ${e.value}`).join('; ')+').'
    : '';
  // render relation facets only when the section is first opened (cheaper)
}

function buildLegend(){const root=document.querySelector(TP.rootSel);
  const host=$(root,'[data-tp-legend]'); const pm=TP.pm;
  host.innerHTML=pm.cast.map(p=>`<span class="pl${TP.muted[p]?' off':''}" data-p="${p}">
    <span class="sw" style="background:${pm.colors[p]}"></span>${nm(p)}</span>`).join('')
    +`<span class="mk"><i style="background:rgba(181,83,46,.9)"></i>outburst (incident)</span>`
    +`<span class="mk"><i style="background:rgba(169,118,47,.6)"></i>social event</span>`;
  host.querySelectorAll('.pl').forEach(el=>el.onclick=()=>{const p=el.dataset.p;
    TP.muted[p]=!TP.muted[p]; el.classList.toggle('off',TP.muted[p]); redrawFacets();});
}

function redrawFacets(){const root=document.querySelector(TP.rootSel);
  root.querySelectorAll('[data-tp-facets] .facet,[data-tp-relfacets] .facet').forEach(div=>{
    if(div._cv&&div._f&&!div.classList.contains('closed'))drawFacet(div._cv,div._f);});}
function redrawAll(){drawOverview();redrawFacets();}

// shared crosshair + readout across all open facets (vertical read at one instant)
function attachHover(cv){
  cv.addEventListener('mousemove',ev=>{const f=cv._f; if(!f)return;
    const r=cv.getBoundingClientRect(), w=r.width;
    const frac=Math.max(0,Math.min(1,(ev.clientX-r.left)/w));
    const i=Math.round(TP.lo+frac*(TP.hi-TP.lo));
    // highlight per the selected mode: incident under cursor, per-persona values,
    // or (both) the incident when near a marker else the values.
    const tol=Math.max(1,(TP.hi-TP.lo)/w*5), inc=incidentNear(i,tol);
    if(TP.hoverMode==='values'){showReadout(i,ev.clientX,ev.clientY,f);}
    else if(TP.hoverMode==='incident'){
      if(inc)showIncidentTip(inc,ev.clientX,ev.clientY); else hideReadout();}
    else{if(inc)showIncidentTip(inc,ev.clientX,ev.clientY);
      else showReadout(i,ev.clientX,ev.clientY,f);}
    drawCrosshair(i);});
  cv.addEventListener('mouseleave',()=>{hideReadout();redrawFacets();});
}
function drawCrosshair(i){const root=document.querySelector(TP.rootSel);
  redrawFacets();
  root.querySelectorAll('[data-tp-facets] .facet,[data-tp-relfacets] .facet').forEach(div=>{
    if(div.classList.contains('closed')||!div._cv)return;
    const cv=div._cv,dpr=window.devicePixelRatio||1,ctx=cv.getContext('2d');
    const w=cv.clientWidth, px=2+(i-TP.lo)/(TP.hi-TP.lo)*(w-4);
    ctx.save();ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.strokeStyle='rgba(58,47,36,.5)';ctx.lineWidth=1;ctx.beginPath();
    ctx.moveTo(px,2);ctx.lineTo(px,cv.clientHeight-2);ctx.stroke();ctx.restore();});}
function showReadout(i,x,y,f){const root=document.querySelector(TP.rootSel);
  const box=$(root,'[data-tp-rdt]'); const pm=TP.pm;
  if(i<0||i>=pm.n){hideReadout();return;}
  let rows='';
  if(f.kind==='world'){rows=`<div class="rv"><span>room tension</span><b>${(pm.world.room_tension[f.room][i]).toFixed(3)}</b></div>`;}
  else if(f.kind==='rel'){const j=Math.min(f.series.length-1,Math.round(i/pm.relations.stride));
    rows=`<div class="rv"><span>${f.label}</span><b>${f.series[j].toFixed(3)}</b></div>`;}
  else {rows=pm.cast.filter(p=>!TP.muted[p]).map(p=>
    `<div class="rv"><span><span class="sw" style="background:${pm.colors[p]}"></span>${nm(p)}</span>`
    +`<b>${pm.series[p][f.key][i].toFixed(3)}</b></div>`).join('');}
  box.innerHTML=`<div class="hd">${labelAt(i)} · tick ${pm.ticks[i]}</div>`
    +`<div style="color:#cdbfa3;margin-bottom:3px">${f.label}</div>`+rows;
  box.style.display='block';
  box.style.left=Math.min(x+13,window.innerWidth-248)+'px';
  box.style.top=Math.min(y+13,window.innerHeight-160)+'px';}
function hideReadout(){const root=document.querySelector(TP.rootSel);
  const b=$(root,'[data-tp-rdt]'); if(b)b.style.display='none';}
// nearest incident within tolIdx tick-indices of i (for hover designation)
function incidentNear(i,tolIdx){const pm=TP.pm; let best=null,bd=tolIdx;
  (pm.incidents||[]).forEach(inc=>{const d=Math.abs(inc.i-i); if(d<=bd){bd=d;best=inc;}});
  return best;}
function incidentTipHtml(inc){const pm=TP.pm;
  const at=inc.target?(' → '+nm(inc.target)):'';
  const tier=inc.tier==='incident'?'OUTBURST (incident)':'social event';
  return `<div class="hd">${tier} · Day ${pm.day[inc.i]} ${hhmm(pm.mins[inc.i])} · tick ${inc.t}</div>`
    +`<div class="rv"><span>${nm(inc.actor)}${at}</span><b>${fmt(inc.action)}</b></div>`
    +(inc.as?`<div class="rv"><span>seen as</span><b>${fmt(inc.as)}</b></div>`:'')
    +`<div class="rv"><span>intensity</span><b>${(inc.intensity).toFixed(3)}</b></div>`
    +(inc.provoked_by?`<div style="color:#cdbfa3;margin-top:3px">provoked by ${inc.provoked_by}</div>`:'');}
function showIncidentTip(inc,x,y){const root=document.querySelector(TP.rootSel);
  const box=$(root,'[data-tp-rdt]'); box.innerHTML=incidentTipHtml(inc);
  box.style.display='block';
  box.style.left=Math.min(x+13,window.innerWidth-260)+'px';
  box.style.top=Math.min(y+13,window.innerHeight-150)+'px';}

function setWindow(lo,hi){const pm=TP.pm; const n=pm.n;
  lo=Math.max(0,Math.round(lo)); hi=Math.min(n-1,Math.round(hi));
  if(hi-lo<4)hi=Math.min(n-1,lo+4);          // a sane minimum span
  TP.lo=lo;TP.hi=hi; redrawAll();}
function focusIncident(k){const pm=TP.pm; if(!pm.incidents.length)return;
  const inc=pm.incidents[(k%pm.incidents.length+pm.incidents.length)%pm.incidents.length];
  const pad=Math.round(pm.n*0.04)||30; setWindow(inc.i-pad,inc.i+pad); TP._inc=k;}

function wireOverview(){const root=document.querySelector(TP.rootSel);
  const cv=$(root,'[data-tp-ov]'); let drag=null;
  const fracX=ev=>{const r=cv.getBoundingClientRect();
    return Math.max(0,Math.min(1,(ev.clientX-r.left)/r.width));};
  cv.addEventListener('mousedown',ev=>{drag={a:fracX(ev)};});
  // hover (not dragging): designate the incident marker under the cursor. The
  // overview only carries incidents, so in 'values' mode it stays quiet.
  cv.addEventListener('mousemove',ev=>{if(drag)return; const pm=TP.pm;
    if(TP.hoverMode==='values'){hideReadout(); cv.style.cursor='crosshair'; return;}
    const i=fracX(ev)*(pm.n-1), tol=(pm.n-1)/cv.getBoundingClientRect().width*5;
    const inc=incidentNear(i,tol);
    if(inc){showIncidentTip(inc,ev.clientX,ev.clientY); cv.style.cursor='pointer';}
    else{hideReadout(); cv.style.cursor='crosshair';}});
  cv.addEventListener('mouseleave',hideReadout);
  window.addEventListener('mousemove',ev=>{if(!drag)return;drag.b=fracX(ev);
    const pm=TP.pm;const lo=Math.min(drag.a,drag.b)*(pm.n-1),hi=Math.max(drag.a,drag.b)*(pm.n-1);
    if(Math.abs(drag.a-drag.b)>0.003)setWindow(lo,hi);});
  window.addEventListener('mouseup',ev=>{if(!drag)return;
    const pm=TP.pm;
    if(drag.b===undefined){ // a click, not a drag: jump to nearest incident marker
      const fx=drag.a*(pm.n-1); let best=-1,bd=1e9;
      pm.incidents.forEach((inc,k)=>{const d=Math.abs(inc.i-fx);if(d<bd){bd=d;best=k;}});
      if(best>=0&&bd<pm.n*0.02)focusIncident(best);}
    drag=null;});
}
function wireToolbar(){const root=document.querySelector(TP.rootSel);
  root.querySelectorAll('[data-tp]').forEach(b=>{const k=b.getAttribute('data-tp');
    b.onclick=()=>{const pm=TP.pm,n=pm.n;
      if(k==='full')setWindow(0,n-1);
      else if(k==='zoomout'){const c=(TP.lo+TP.hi)/2,w=(TP.hi-TP.lo)*2;setWindow(c-w/2,c+w/2);}
      else if(k==='prev')focusIncident((TP._inc==null?0:TP._inc-1));
      else if(k==='next')focusIncident((TP._inc==null?0:TP._inc+1));
      else if(k==='fit'){TP.autoscale=!TP.autoscale; b.classList.toggle('on',TP.autoscale); redrawFacets();}};});
}

// public entry: render a plot model. opts.keepView preserves the window (live use).
function render(model,opts){opts=opts||{};
  TP.pm=model; TP.rootSel=model.__root||TP.rootSel||'#tp';
  if(!opts.keepView||TP.hi===0){TP.lo=0;TP.hi=model.n-1;}
  else {TP.hi=Math.min(TP.hi,model.n-1);TP.lo=Math.max(0,Math.min(TP.lo,TP.hi-4));}
  // tick-resolution readout: seconds/tick + points/day + total points
  const dtEl=document.querySelector(TP.rootSel+' [data-tp-dt]');
  if(dtEl){const dt=model.dt, perDay=model.days&&model.days.length?Math.round(model.n/model.days.length):null;
    dtEl.textContent=(dt?('tick ≈ '+dt.toFixed(dt<10?2:1)+' s · '):'')
      +(perDay?(perDay+' ticks/day · '):'')+model.n+' points';}
  buildLegend(); buildFacets(); buildRelFacets(); wireOnce();
  drawOverview();
  // (re)draw on resize so canvases stay crisp/full-width
  if(!TP._resize){TP._resize=true;window.addEventListener('resize',()=>{clearTimeout(TP._rt);
    TP._rt=setTimeout(redrawAll,120);});}
}
let _wired=false;
function wireOnce(){if(_wired)return;_wired=true;wireOverview();wireToolbar();
  const root0=document.querySelector(TP.rootSel);
  const hv=root0&&root0.querySelector('[data-tp-hover]');
  if(hv){hv.value=TP.hoverMode; hv.onchange=()=>{TP.hoverMode=hv.value;};}
  // lazily draw relation facets when the section opens
  const root=document.querySelector(TP.rootSel);const rel=root&&root.querySelector('[data-tp-rel]');
  if(rel)rel.addEventListener('toggle',()=>{if(rel.open)redrawFacets();});}

window.TimePlots={render:render};
})();
"""


# -- the standalone static page ------------------------------------------------

def page(models: dict, default: str | None = None,
         assets: dict | None = None) -> str:
    """A self-contained Time Plots page. `models` maps protocol name -> plot model
    (all embedded, switchable). Reuses the Observatory theme + asset pack."""
    assets = assets if assets is not None else OB.load_assets()
    names = list(models)
    default = default or names[0]
    # tag each model with the root selector the render layer scopes to
    for m in models.values():
        m["__root"] = "#tp"
    data = json.dumps(models, ensure_ascii=False, separators=(",", ":"))
    adata = json.dumps(assets, ensure_ascii=False)
    selector_init = json.dumps(names)
    boot = f"""
<script>window.ASSETS={adata};window.TP_DATA={data};window.TP_NAMES={selector_init};
window.TP_DEFAULT={json.dumps(default)};</script>
<script>{PLOT_SCRIPT}</script>
<script>
(function(){{
  const sel=document.getElementById('tp_proto');
  if(sel){{sel.innerHTML=window.TP_NAMES.map(n=>`<option${{n===window.TP_DEFAULT?' selected':''}}>${{n}}</option>`).join('');
    sel.onchange=()=>window.TimePlots.render(window.TP_DATA[sel.value]);}}
  window.TimePlots.render(window.TP_DATA[window.TP_DEFAULT]);
}})();
</script>
"""
    header = """
<div class="wrap">
  <div class="hero"><img class="emblem" id="emblem" alt="">
    <div><h1>Time Plots — engine dynamics</h1>
      <div class="tag">Raw interior-state trajectories across the canonical protocols, for study.</div>
      <span class="pill">fast affect spikes &amp; vents · slow relational marks · incidents as the spine</span>
    </div></div>
"""
    emblem_js = ""
    if "equilibrium_observatory_emblem.svg" in assets:
        # runs AFTER `boot` defines window.ASSETS, and guards in case it is absent
        emblem_js = ("<script>if(window.ASSETS&&window.ASSETS['equilibrium_observatory_emblem.svg'])"
                     "document.getElementById('emblem').src="
                     "window.ASSETS['equilibrium_observatory_emblem.svg'];</script>")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<link rel='icon' href='data:,'>"
        "<title>Equilibrium Inn — Time Plots</title>"
        "<style>" + OB.STYLE + PLOT_STYLE + "</style>"
        "<style>" + OB._asset_css(assets) + "</style></head><body>"
        + header + plot_body("tp", with_selector=len(names) > 1)
        + "</div>" + boot + emblem_js + "</body></html>"
    )


def export_html(trace_dirs, out_html, inn_yaml=None) -> Path:
    """Build the static Time Plots page from one or more run trace dirs.
    `trace_dirs` is a {protocol_name: dir} mapping (or a single dir)."""
    from inn.config import load_inn_config
    from inn.metrics import load_records

    if isinstance(trace_dirs, (str, Path)):
        trace_dirs = {Path(trace_dirs).name: trace_dirs}
    cfg = load_inn_config(inn_yaml or ROOT / "inn.yaml")
    models = {}
    for name, d in trace_dirs.items():
        d = Path(d)
        records = load_records(d / "trace.jsonl.gz")
        dt = None                       # read the run's seconds/tick from session.json
        sp = d / "session.json"
        if sp.is_file():
            dt = (json.loads(sp.read_text(encoding="utf-8")).get("layout") or {}).get("dt")
        models[name] = build_plot_model(records, cfg, dt=dt, meta={"protocol": name,
                                        "source": str(d), "ticks": len(records)})
    out_html = Path(out_html)
    out_html.write_text(page(models), encoding="utf-8")
    return out_html


def main(argv: list[str] | None = None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Export a run's state trajectories as "
                                 "a self-contained Time Plots HTML page.")
    ap.add_argument("trace_dir", help="directory containing trace.jsonl.gz")
    ap.add_argument("-o", "--out", default="plots.html")
    args = ap.parse_args(argv)
    p = export_html(args.trace_dir, args.out)
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
