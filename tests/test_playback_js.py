"""M-K — playback math (the ▶ play loop) unit-tested under node.

These pin the bug class that slipped past "code-present" assertions: after a run the
playhead is parked at the last frame, and a clamp-at-end loop made ▶ play a no-op
(dead-on-arrival). The playback math is pure + DOM-free (inn.observatory.PLAYBACK_JS)
precisely so it can be exercised here without a browser.
"""

import shutil
import subprocess

import pytest

from inn import observatory as OB

HARNESS = OB.PLAYBACK_JS + r"""
function assert(c, m){ if(!c){ console.error("FAIL: " + m); process.exit(1); } }

// 1. dead-on-arrival: pressing play while parked at the end restarts from 0.
assert(playStartFrame(2150, 2151) === 0, "restart when parked at end");
assert(playStartFrame(100, 2151) === 100, "resume in place when mid-run");
assert(playStartFrame(0, 0) === 0, "empty run is safe");

// 2. from the start, play actually advances (never stuck) — 200x at the 120s default.
let f = 0, acc = 0; const len = 2151, P = 120, tps = 200 / 120.0;
for (let i = 0; i < 200; i++){ const r = playAdvance(f, len, acc, tps, P); f = r.frame; acc = r.acc; }
assert(f > 0, "advances from the start at 200x/120s within 200 fires (was stuck at 0)");

// 3. reaches the end, clamps there, and reports done (so the loop can stop cleanly).
let g = len - 3, a = 0, done = false;
for (let i = 0; i < 500 && !done; i++){ const r = playAdvance(g, len, a, tps, P); g = r.frame; a = r.acc; done = r.done; }
assert(done, "reports done near the end");
assert(g === len - 1, "clamps at the last frame, never past it");

// 4. 1x is real-time: ~dt real-seconds per tick (advances ~1 tick after ~dt seconds).
let h = 0, b = 0; const dt = 15;
const fires = Math.round(dt / (P / 1000)) + 2;
for (let i = 0; i < fires; i++){ const r = playAdvance(h, len, b, 1 / dt, P); h = r.frame; b = r.acc; }
assert(h >= 1, "1x advances ~1 tick after ~dt seconds (real-time)");

// 5. fractional remainder is carried (no permanent <1 stall): slow rate still advances.
let s = 0, c = 0; const slowTps = 1 / 120.0;  // 1x at 120s
let moved = false;
for (let i = 0; i < 2000 && !moved; i++){ const r = playAdvance(s, len, c, slowTps, P); s = r.frame; c = r.acc; moved = s > 0; }
assert(moved, "even the slowest rate eventually advances (fractional acc carried)");

console.log("OK");
"""


def test_playback_helpers():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    import tempfile
    from pathlib import Path
    p = Path(tempfile.mkdtemp()) / "harness.js"
    p.write_text(HARNESS, encoding="utf-8")
    r = subprocess.run([node, str(p)], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_script_uses_the_restart_fix():
    # the SCRIPT must call playStartFrame on play (so the dead-on-arrival fix can't
    # silently regress) and route the speed loop through playAdvance.
    assert "playStartFrame(frame" in OB.SCRIPT
    assert "playAdvance(frame" in OB.SCRIPT
