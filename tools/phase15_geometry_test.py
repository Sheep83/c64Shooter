#!/usr/bin/env python3
"""Phase 1.5 display-geometry / bottom-border capture harness.

Self-launches a background x64sc (no focus steal), drives Level 1 to PLAYING,
optionally applies a NON-DESTRUCTIVE runtime fixture that clamps every authored
scrolling wave to <= 5 enemies (RAM patch of the waveTrigCount table only -- the
generated level assets on disk are never touched), optionally seeds SCROLL_ROW
so authored waves fire quickly, then captures N physical PAL frames in the exact
layout tools/check_raster_capture.py and tools/check_scroll_edges_rsel1.py
consume (frames.json / symbols.json / NNNNN.{png,state,raster,ram,bg} +
timing.log traces).

Cases (choose with --case):
  ordinary   player only (default)
  wave5      <=5-enemy authored waves via the runtime fixture + seeded scroll
  wave6      authored waves AS EXPORTED (some 6-enemy) -- known-overload demo
  dense      16 stationary legal objects (8 tight batches)
  lowy       8 gameplay sprites forced to Y=245
  contrast   player only, $D021 forced to a bright non-black value
  div1       divider-1-like stress (SCROLL_FRAME_COUNT pumped each frame)

Nothing is written to the repo tree. Monitor RAM writes only. Emulator killed
on exit.  Usage:  python3 tools/phase15_geometry_test.py --case wave5 --out build/p15-wave5
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from vice_scroll_test import Monitor, symbols

X64SC = "/opt/homebrew/bin/x64sc"


def launch(port, prg, core):
    p = subprocess.Popen(
        [core, "-default", "-pal", "-warp", "+sound",
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


def wr(m, addr, *vals):
    m.cmd(f"> {addr:04x} " + " ".join(f"{v & 0xFF:02x}" for v in vals))


def start_playing(m, sym, prg, seed_scroll=None):
    m.cmd("delete")
    m.cmd("> d01a 00"); m.cmd("> 0314 31 ea"); m.cmd("> d015 00"); m.cmd("> d011 1b")
    m.cmd(f'load "{prg}" 0')
    m.cmd(f'r pc={sym["init"]:04x}, sp=ff')
    m.cmd('resourceset "JoyPort2Device" "37"')
    m.cmd(f'break {sym["waitFireRelease"]:04x}')
    m.cmd("jpdb 1 ef"); m.cmd("x"); m.cmd("jpdb 1 ff"); m.cmd("delete")
    if seed_scroll is not None:
        m.cmd(f'break {sym["initBackground"]:04x}'); m.cmd("x")
        wr(m, sym["SCROLL_ROW"], seed_scroll & 0xFF, (seed_scroll >> 8) & 0xFF)
        m.cmd("delete")
        m.cmd(f'break {sym["renderStageRowToScreen"]:04x}'); m.cmd("x")
        wr(m, sym["SCROLL_ROW"], seed_scroll & 0xFF, (seed_scroll >> 8) & 0xFF)
        m.cmd("delete")
    m.cmd(f'break {sym["applyFineScroll"]:04x}'); m.cmd("x"); m.cmd("jpdb 1 ff"); m.cmd("delete")
    m.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')


def clamp_waves(m, sym, cap=5):
    n = sym["waveTrigCount"] and 16
    cur = rd(m, sym["waveTrigCount"], 16)
    new = [min(v, cap) for v in cur]
    wr(m, sym["waveTrigCount"], *new)
    return cur, new


def put(m, sym, name, values):
    m.cmd(f'> {sym[name]:04x} ' + ' '.join(f'{v:02x}' for v in values))


def seed_dense(m, sym, low_y=False):
    put(m, sym, "OBJECT_ACTIVE", [1] * 16)
    put(m, sym, "OBJECT_TYPE", [1] + [2] * 15)
    if low_y:
        put(m, sym, "OBJECT_Y", [150] + [245] * 7 + [244, 243, 242, 241, 240, 238, 236, 234])
    else:
        put(m, sym, "OBJECT_Y", list(range(96, 125, 4)) + list(range(160, 189, 4)))
    put(m, sym, "OBJECT_X", [24 + 16 * (i % 12) for i in range(16)])
    put(m, sym, "OBJECT_X_MSB", [0] * 16)
    put(m, sym, "OBJECT_SPRITE", [sym["blankSprite"] // 64] * 16)
    put(m, sym, "OBJECT_PATH_TIMER", [255] * 16)
    put(m, sym, "OBJECT_STAGE", [2] * 16)
    for nm in ("OBJECT_VEL_X", "OBJECT_VEL_Y", "OBJECT_TARGET_VEL_X",
               "OBJECT_TARGET_VEL_Y", "OBJECT_HIT_TIMER", "OBJECT_DEATH_TIMER"):
        put(m, sym, nm, [0] * 16)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="ordinary",
                    choices=["ordinary", "wave5", "wave6", "dense", "lowy", "contrast", "div1"])
    ap.add_argument("--port", type=int, default=6540)
    ap.add_argument("--frames", type=int, default=220)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--prg", type=Path, default=REPO / "build" / "shooter.prg")
    ap.add_argument("--core", default=X64SC)
    ap.add_argument("--d021", type=lambda s: int(s, 0), default=0x07, help="contrast case backdrop")
    args = ap.parse_args()
    out = (args.out or REPO / "build" / f"p15-{args.case}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(REPO / "build" / "main.vs")
    proc, m = launch(args.port, args.prg, args.core)
    meta = {"case": args.case, "core": args.core}
    try:
        m.trace_file = (out / "monitor.log").open("w")
        seed = 382 if args.case in ("wave5", "wave6") else None
        start_playing(m, sym, args.prg, seed_scroll=seed)
        if args.case == "wave5":
            meta["wave_counts_before"], meta["wave_counts_after"] = clamp_waves(m, sym, 5)
        if args.case == "wave6":
            meta["wave_counts_before"] = rd(m, sym["waveTrigCount"], 16)
        if args.case in ("dense", "lowy"):
            m.cmd(f'break {sym["applyFineScroll"]:04x}'); m.cmd("x"); m.cmd("delete")
            seed_dense(m, sym, low_y=(args.case == "lowy"))
        if args.case == "contrast":
            wr(m, 0xD021, args.d021)

        # tracepoints for check_raster_capture.py
        m.cmd(f'logname "{out / "timing.log"}"'); m.cmd("log on")
        for name in ("rasterAssignmentApplied", "rasterInitialApplied",
                     "rasterInitialMasksApplied", "rasterBatchMasksApplied"):
            if name in sym:
                m.cmd(f'trace exec {sym[name]:04x}')
        m.cmd("trace store d012 d012")
        m.cmd("trace store d011 d011")

        res = m.cmd("break exec 0000 ffff if RL == $137")
        pbreak = int(re.search(r"BREAK: (\d+)", res)[1])
        m.cmd("x")
        records = []
        for frame in range(args.frames):
            if args.case == "contrast":
                wr(m, 0xD021, args.d021)
            if args.case == "div1":
                wr(m, sym["SCROLL_FRAME_COUNT"], 0)
            regs = m.cmd("r")
            m.cmd(f'bsave "{out / f"{frame:05d}.ram"}" 0 0400 07ff')
            m.cmd(f'bsave "{out / f"{frame:05d}.state"}" 0 2000 23ff')
            m.cmd(f'bsave "{out / f"{frame:05d}.bg"}" 0 2920 2fff')
            m.cmd(f'bsave "{out / f"{frame:05d}.raster"}" 0 {sym["RASTER_STATE_BEGIN"]:04x} {sym["RASTER_STATE_END"] - 1:04x}')
            m.cmd(f'screenshot "{out / f"{frame:05d}.png"}" 2')
            io = m.cmd("m d010 d011")
            v = re.search(r">C:d010\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})", io)
            records.append(dict(frame=frame, registers=regs,
                                physical_x_msb=int(v[1], 16),
                                physical_fine=int(v[2], 16) & 7))
            m.cmd(f"condition {pbreak} if RL == $000"); m.cmd("x")
            m.cmd(f"condition {pbreak} if RL == $137"); m.cmd("x")
        m.cmd("log off"); m.cmd("delete")
        b = sym["RASTER_STATE_BEGIN"]
        def w(name):
            return rd(m, sym[name])[0] | (rd(m, sym[name] + 1)[0] << 8)
        meta["counters_end"] = dict(
            incomplete=w("RASTER_INCOMPLETE_FRAMES"), replay=w("RASTER_REPLAY_FRAMES"),
            catchups=w("RASTER_CATCHUPS"), display_late=rd(m, sym["RASTER_DISPLAY_LATE"])[0],
            frame=w("RASTER_FRAME"),
            max_objects=max(sum(rd(m, sym["OBJECT_ACTIVE"] + i)[0] for i in range(16)) for _ in [0]),
        )
        (out / "frames.json").write_text(json.dumps(records, indent=2))
        (out / "symbols.json").write_text(json.dumps(sym, indent=2))
        (out / "meta.json").write_text(json.dumps(meta, indent=2))
        print(json.dumps(meta, indent=2))
        print("artifacts:", out)
    finally:
        try:
            m.cmd("quit")
        except Exception:
            pass
        proc.terminate()


if __name__ == "__main__":
    main()
