# Observatory visual assets

These files are wired into the Living Inn Observatory render layer
(`inn/observatory.py`). At build/export time every present file here is read,
**web-optimized** (raster art downscaled + WebP re-encoded; SVG passed through —
best-effort via Pillow), and **base64-embedded** into the page
(`inn.observatory.load_assets`), so the self-contained export and the Pyodide
cockpit both stay offline and a few MB rather than tens of MB. Missing files
degrade gracefully to warm CSS gradients/textures, so the page is always
presentable.

The loader keys each asset by its **stem**, so a slot works whether it ships as
`.png` or `.svg` — the current pack is all PNG.

| file | used for |
|---|---|
| `bg_observatory_warm.png` | page background |
| `hero_inn_header.png` | top hero/header band |
| `scene_inn_rooms.png` | base image under the room map |
| `panel_parchment_soft.png` | card/panel texture |
| `promo_behavior_cycle.png` | illustration in the behaviour-cycle section |
| `equilibrium_observatory_emblem.png` | header / footer emblem |
| `divider_lantern_vine.png` | section dividers |
| `npc_token_base.png` | frame behind NPC tokens in the scene |
| `icon_boredom.png` | boredom gauge/metric |
| `icon_fatigue.png` | fatigue gauge/metric |
| `icon_stress.png` | stress gauge/metric |
| `icon_sleep.png` | sleep / rest / recovery |
| `icon_activity.png` | activity / seeking / busy |
| `icon_causality.png` | why / causality panel |
| `overlay_fireflies_soft.png` | low-opacity ambient overlay |

Replace any file in place (same name) and rebuild:
`python observatory/build_bundle.py` (cockpit) or
`python -m inn.observatory <trace_dir> -o run.html` (static export). Per-asset
downscale caps live in `inn.observatory._MAXDIM`.
