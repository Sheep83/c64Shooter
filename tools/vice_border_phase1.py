#!/usr/bin/env python3
"""Bottom-border HUD experiment - Phase 1 "prove the border" measurement harness.

Self-launches a background x64sc (no focus steal), drives Level 1 to PLAYING with
one joystick fire press, then measures the quarantined lower-border-open + static
diagnostic marker sprite added in src/raster_scheduler.asm (borderOpenHook):

  * physical PAL cadence (raster-311 cycle deltas) -> expect [19656]
  * scheduler health counters (incomplete / replay / catchup / display-late)
  * exact raster + $D011 value of each RSEL transition write
  * marker sprite setup (slot, ptr, colour, X, Y, enable, $D010)
  * next-frame register leak ($D015 / $D010 / slot-7 ptr/colour/X/Y at raster ~5)
  * $D01E collision latch / PLAYER_HIT behaviour
  * screenshots at every fine-scroll phase, across coarse 7->0 transitions,
    for divider 2 (authored) and forced divider 1, ordinary + dense + low-Y
    loads, and a contrasting non-black $D021
  * a Y sweep of the marker to bound the usable opened-border depth

Run:  python3 tools/vice_border_phase1.py [--port N] [--out DIR] [--frames N]
Nothing is written to the repo. Monitor RAM pokes only. Emulator killed on exit.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from vice_scroll_test import Monitor, symbols  # noqa: E402

X64SC = "/opt/homebrew/bin/x64sc"


def launch(port, prg):
    p = subprocess.Popen(
        [X64SC, "-default", "-pal", "-warp", "+sound",
         "-remotemonitor", "-remotemonitoraddress", f"ip4://127.0.0.1:{port}",
         "-autostartprgmode", "1", "-autostart", str(prg)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p, Monitor(port)


def rd(m, addr, n=1):
    r = m.cmd(f"m {addr:04x} {addr + n - 1:04x}")
    vals = []
    for grp in re.findall(r">C:[0-9a-f]{4}((?:\s+[0-9a-fA-F]{2})+)", r):
        vals += [int(x, 16) for x in grp.split()]
    return vals[:n]


def rd8(m, addr):
    return rd(m, addr, 1)[0]


def wr(m, addr, *vals):
    m.cmd(f"> {addr:04x} " + " ".join(f"{v & 0xFF:02x}" for v in vals))


def cycles(m):
    """STOPWATCH (cumulative CPU cycles) from the monitor 'r' data line:
       .;ADDR A X Y SP 00 01 FLAGS  LIN CYC  STOPWATCH"""
    r = m.cmd("r")
    mm = re.search(r"\.;[0-9a-fA-F]{4}(?:\s+\S+){7}\s+(\d+)\s+(\d+)\s+(\d+)", r)
    return int(mm.group(3)) if mm else None


def raster(m):
    d011 = rd8(m, 0xD011)
    return rd8(m, 0xD012) | ((d011 & 0x80) << 1)


def start_playing(m, sym, prg):
    m.cmd("delete")
    m.cmd("> d01a 00"); m.cmd("> 0314 31 ea"); m.cmd("> d015 00"); m.cmd("> d011 1b")
    m.cmd(f'load "{prg}" 0')
    m.cmd(f'r pc={sym["init"]:04x}, sp=ff')
    m.cmd('resourceset "JoyPort2Device" "37"')
    m.cmd(f'break {sym["waitFireRelease"]:04x}')
    m.cmd("jpdb 1 ef"); m.cmd("x"); m.cmd("jpdb 1 ff"); m.cmd("delete")
    m.cmd(f'break {sym["applyFineScroll"]:04x}')
    m.cmd("x"); m.cmd("jpdb 1 ff"); m.cmd("delete")
    m.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')


def counters(m, sym):
    b = sym["RASTER_STATE_BEGIN"]
    def w(name):
        o = sym[name] - b
        return rd8(m, sym[name]) | (rd8(m, sym[name] + 1) << 8)
    return dict(
        incomplete=w("RASTER_INCOMPLETE_FRAMES"),
        replay=w("RASTER_REPLAY_FRAMES"),
        catchups=w("RASTER_CATCHUPS"),
        display_late=rd8(m, sym["RASTER_DISPLAY_LATE"]),
        frame=w("RASTER_FRAME"),
    )


def cadence_run(m, sym, n):
    """Break at raster 311 each physical frame; record CPU-cycle deltas."""
    m.cmd("delete")
    res = m.cmd("break exec 0000 ffff if RL == $137")
    bp = int(re.search(r"BREAK: (\d+)", res)[1])
    m.cmd("x")
    prev = cycles(m)
    deltas = []
    for _ in range(n):
        m.cmd(f"condition {bp} if RL == $000")
        m.cmd("x")
        m.cmd(f"condition {bp} if RL == $137")
        m.cmd("x")
        c = cycles(m)
        deltas.append(c - prev)
        prev = c
    m.cmd(f"delete {bp}")
    return deltas


def trace_border_writes(m, sym, frames=12):
    """Trace borderOpenHook entry/exit + $D011 stores; return per-frame events."""
    out = Path(m.trace_file.name).parent / "border_trace.log"
    m.cmd("delete")
    m.cmd(f'logname "{out}"'); m.cmd("log on")
    m.cmd("trace store d011 d011")
    for lbl in ("borderOpenHook", "borderOpenRestored", "rasterDisplayRestored",
                "rasterFrameReset", "rasterAssignmentApplied"):
        if lbl in sym:
            m.cmd(f"trace exec {sym[lbl]:04x}")
    m.cmd(f'break {sym["rasterFrameReset"]:04x}')
    for _ in range(frames):
        m.cmd("x")
    m.cmd("log off"); m.cmd("delete")
    return out


def parse_border_trace(path, sym):
    a_hook = sym["borderOpenHook"]
    a_done = sym["borderOpenRestored"]
    lines = Path(path).read_text(errors="replace").splitlines()
    hdr = None
    d011_writes = []          # (raster_line, cycle_in_line, value)
    hook_raster = []
    done_raster = []
    for ln in lines:
        h = re.match(r"#\d+ \(Trace\s+\w+ [^)]*\)\s+(\d+)/\$[0-9a-f]+,\s+(\d+)/", ln)
        if h:
            hdr = (int(h.group(1)), int(h.group(2)))
            continue
        c = re.match(r"\.C:([0-9a-fA-F]{4})\s+(\S\S)\s", ln)
        if c and hdr is not None:
            addr = int(c.group(1), 16)
            if addr == a_hook:
                hook_raster.append(hdr[0])
            elif addr == a_done:
                done_raster.append(hdr[0])
            hdr = None
            continue
        s = re.match(r"\.C:([0-9a-fA-F]{4})\s+8D 11 D0\s+STA \$D011\s+- A:([0-9a-fA-F]{2})", ln)
        if s and hdr is not None:
            d011_writes.append((hdr[0], hdr[1], int(s.group(2), 16)))
            hdr = None
    return dict(hook_raster=hook_raster, done_raster=done_raster, d011_writes=d011_writes)


def snap_regs(m):
    d = rd(m, 0xD000, 0x30)
    ptrs = rd(m, 0x07F8, 8)
    return dict(x=d[0:16:2], y=d[1:16:2], d010=d[0x10], d015=d[0x15],
               d01c=d[0x1C], d021=d[0x21], colours=d[0x27:0x2F], ptrs=ptrs)


def screenshot(m, path):
    m.cmd(f'screenshot "{path}" 2')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6577)
    ap.add_argument("--out", type=Path, default=REPO / "build" / "border-phase1")
    ap.add_argument("--frames", type=int, default=400)
    ap.add_argument("--prg", type=Path, default=REPO / "build" / "shooter.prg")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(REPO / "build" / "main.vs")
    proc, m = launch(args.port, args.prg)
    report = {}
    try:
        m.trace_file = (out / "monitor.log").open("w")
        start_playing(m, sym, args.prg)

        report["counters_start"] = counters(m, sym)

        # 1. cadence, ordinary load
        d = cadence_run(m, sym, args.frames)
        from collections import Counter
        report["cadence_ordinary"] = {str(k): v for k, v in Counter(d).most_common()}

        # 2. border write timing
        bt = trace_border_writes(m, sym, frames=16)
        report["border_trace"] = parse_border_trace(bt, sym)

        # 3. marker sprite state + screenshots per fine phase
        fine_shots = {}
        seen_fine = set()
        m.cmd("delete")
        m.cmd(f'break {sym["applyFineScroll"]:04x}')
        for _ in range(200):
            m.cmd("x")
            f = rd8(m, sym["RASTER_DISPLAY_FINE"])
            if f not in seen_fine and 0 <= f <= 7:
                seen_fine.add(f)
                # advance to the terminal region so the marker is armed
                m.cmd("delete")
                res = m.cmd("break exec 0000 ffff if RL == $118")   # raster 280
                b2 = int(re.search(r"BREAK: (\d+)", res)[1])
                m.cmd("x")
                screenshot(m, out / f"fine{f}.png")
                r = snap_regs(m)
                fine_shots[f] = dict(marker_y=r["y"][7], marker_x=r["x"][7],
                                     ptr7=r["ptrs"][7], col7=r["colours"][7],
                                     d015=r["d015"], d010=r["d010"], d021=r["d021"])
                m.cmd(f"delete {b2}")
                m.cmd(f'break {sym["applyFineScroll"]:04x}')
            if len(seen_fine) == 8:
                break
        m.cmd("delete")
        report["fine_phase_marker"] = fine_shots

        # 4. next-frame leak: registers at raster ~5 (just after renderSprites)
        m.cmd("delete")
        res = m.cmd("break exec 0000 ffff if RL == $005")
        b5 = int(re.search(r"BREAK: (\d+)", res)[1])
        leak = []
        for _ in range(12):
            m.cmd("x")
            r = snap_regs(m)
            leak.append(dict(d015=r["d015"], d010=r["d010"], y7=r["y"][7],
                             x7=r["x"][7], ptr7=r["ptrs"][7], col7=r["colours"][7]))
        m.cmd(f"delete {b5}")
        report["frametop_regs"] = leak

        # 5. collision latch / PLAYER_HIT over a run
        ph = []
        d01e = []
        m.cmd("delete")
        res = m.cmd("break exec 0000 ffff if RL == $137")
        b6 = int(re.search(r"BREAK: (\d+)", res)[1])
        for _ in range(120):
            m.cmd(f"condition {b6} if RL == $000"); m.cmd("x")
            m.cmd(f"condition {b6} if RL == $137"); m.cmd("x")
            ph.append(rd8(m, sym["PLAYER_HIT"]))
        m.cmd(f"delete {b6}")
        report["player_hit_seen"] = sorted(set(ph))

        # 6. Y sweep to bound usable border depth (poke SPR_Y[7], screenshot)
        m.cmd("delete")
        res = m.cmd("break exec 0000 ffff if RL == $118")
        b7 = int(re.search(r"BREAK: (\d+)", res)[1])
        for y in (230, 240, 246, 250, 252, 256, 260, 266, 270, 276, 282, 288):
            m.cmd("x")
            wr(m, 0xD00F, y)                 # slot 7 Y
            wr(m, 0xD015, rd8(m, 0xD015) | 0x80)
            m.cmd("x")
            screenshot(m, out / f"ysweep_{y}.png")
        m.cmd(f"delete {b7}")

        # 7. dense load (16 legal objects) + cadence + screenshot
        m.cmd("delete"); m.cmd("jpdb 1 ff")
        def put(name, values):
            m.cmd(f'> {sym[name]:04x} ' + ' '.join(f'{v:02x}' for v in values))
        m.cmd(f'break {sym["applyFineScroll"]:04x}'); m.cmd("x"); m.cmd("delete")
        put("OBJECT_ACTIVE", [1] * 16)
        put("OBJECT_TYPE", [1] + [2] * 15)
        put("OBJECT_Y", list(range(96, 125, 4)) + list(range(160, 189, 4)))
        put("OBJECT_X", [24 + 16 * (i % 12) for i in range(16)])
        put("OBJECT_X_MSB", [0] * 16)
        put("OBJECT_SPRITE", [sym["blankSprite"] // 64] * 16)
        put("OBJECT_PATH_TIMER", [255] * 16)
        put("OBJECT_STAGE", [2] * 16)
        for nm in ("OBJECT_VEL_X", "OBJECT_VEL_Y", "OBJECT_TARGET_VEL_X",
                   "OBJECT_TARGET_VEL_Y", "OBJECT_HIT_TIMER", "OBJECT_DEATH_TIMER"):
            put(nm, [0] * 16)
        d = cadence_run(m, sym, 250)
        report["cadence_dense"] = {str(k): v for k, v in Counter(d).most_common()}
        m.cmd("delete")
        res = m.cmd("break exec 0000 ffff if RL == $118")
        b8 = int(re.search(r"BREAK: (\d+)", res)[1])
        m.cmd("x"); screenshot(m, out / "dense.png")
        r = snap_regs(m)
        report["dense_marker"] = dict(d015=r["d015"], y7=r["y"][7], x7=r["x"][7])
        m.cmd(f"delete {b8}")

        # 8. lowest-Y load (8 gameplay sprites forced to Y=245) + cadence
        put("OBJECT_Y", [150] + [245] * 7 + [244, 243, 242, 241, 240, 238, 236, 234])
        d = cadence_run(m, sym, 250)
        report["cadence_lowY"] = {str(k): v for k, v in Counter(d).most_common()}
        m.cmd("delete")
        res = m.cmd("break exec 0000 ffff if RL == $118")
        b9 = int(re.search(r"BREAK: (\d+)", res)[1])
        m.cmd("x"); screenshot(m, out / "lowY.png")
        r = snap_regs(m)
        report["lowY_marker"] = dict(d015=r["d015"], y7=r["y"][7])
        m.cmd(f"delete {b9}")

        # 9. contrasting non-black $D021 + coarse transitions
        m.cmd("delete"); m.cmd("jpdb 1 ff")
        m.cmd(f'break {sym["applyFineScroll"]:04x}'); m.cmd("x"); m.cmd("delete")
        put("OBJECT_ACTIVE", [1] + [0] * 15)     # back to just the player
        m.cmd(f'> {0xD021:04x} 07')               # yellow backdrop (contrast)
        m.cmd("delete")
        res = m.cmd("break exec 0000 ffff if RL == $118")
        bA = int(re.search(r"BREAK: (\d+)", res)[1])
        for i in range(6):
            for _ in range(20):
                m.cmd("x")
            screenshot(m, out / f"contrast_d021_{i}.png")
        m.cmd(f"delete {bA}")

        # 10. divider-1 stress: force SCROLL_FRAME_DIVIDER path by pumping the
        #     divider counter every frame (coarse work every 8 frames)
        m.cmd("delete")
        res = m.cmd("break exec 0000 ffff if RL == $137")
        bB = int(re.search(r"BREAK: (\d+)", res)[1])
        prev = cycles(m); d = []
        for _ in range(250):
            m.cmd(f"condition {bB} if RL == $000"); m.cmd("x")
            m.cmd(f"> {sym['SCROLL_FRAME_COUNT']:04x} 00")   # keep divider hot
            m.cmd(f"condition {bB} if RL == $137"); m.cmd("x")
            c = cycles(m); d.append(c - prev); prev = c
        report["cadence_div1ish"] = {str(k): v for k, v in Counter(d).most_common()}
        m.cmd(f"delete {bB}")

        report["counters_end"] = counters(m, sym)
        (out / "report.json").write_text(__import__("json").dumps(report, indent=2))
        print(__import__("json").dumps(report, indent=2))
        print("\nartifacts in", out)
    finally:
        try:
            m.cmd("quit")
        except Exception:
            pass
        proc.terminate()


if __name__ == "__main__":
    main()
