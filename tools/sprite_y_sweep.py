#!/usr/bin/env python3
"""Deterministic upper-Y sprite sweep (Part B of the full-gameplay-aperture task).

Self-launches a background x64sc (no focus steal), drives Level 1 to PLAYING,
then for each candidate OBJECT_Y sweeps ONE controlled gameplay enemy (logical
object 1) through that Y -- frozen (STAGE_EGRESS, zero velocity, re-poked every
frame) -- and reports, per Y, whether the object is:

  active | in SORTED_OBJECTS | in the LIVE render plan | assigned a hw slot |
  batch-scheduled | VIC-enabled ($D015 bit) | pixels actually visible (screenshot)
  | first visible raster | collision-eligible (software-confirm Y gate)

Nothing is written to the repo tree. Monitor RAM pokes only. Emulator killed on
exit.  Usage:  python3 tools/sprite_y_sweep.py [--port N] [--out DIR] [--lo 30 --hi 96]
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
GAMEPLAY_SPRITE_MIN_Y = 71          # current source value, for the collision-gate column
GAMEPLAY_SPRITE_END_Y = 246


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


def wr(m, addr, *v):
    m.cmd(f"> {addr:04x} " + " ".join(f"{x & 0xFF:02x}" for x in v))


def start_playing(m, sym, prg):
    m.cmd("delete")
    m.cmd("> d01a 00"); m.cmd("> 0314 31 ea"); m.cmd("> d015 00"); m.cmd("> d011 1b")
    m.cmd(f'load "{prg}" 0')
    m.cmd(f'r pc={sym["init"]:04x}, sp=ff')
    m.cmd('resourceset "JoyPort2Device" "37"')
    m.cmd(f'break {sym["waitFireRelease"]:04x}')
    m.cmd("jpdb 1 ef"); m.cmd("x"); m.cmd("jpdb 1 ff"); m.cmd("delete")
    m.cmd(f'break {sym["applyFineScroll"]:04x}'); m.cmd("x"); m.cmd("jpdb 1 ff"); m.cmd("delete")
    m.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')


MARKER_PTR = 0x1fc0 // 64          # BORDER_MARKER_SPRITE: 63x $ff solid block
MARKER_COL = 2                     # red individual sprite colour


def _poke_one(m, sym, i, y, x):
    wr(m, sym["OBJECT_ACTIVE"] + i, 1)
    wr(m, sym["OBJECT_TYPE"] + i, 2)                 # TYPE_ENEMY
    wr(m, sym["OBJECT_STAGE"] + i, 2)               # STAGE_EGRESS: coasts, never fires
    wr(m, sym["OBJECT_SPRITE"] + i, MARKER_PTR)
    wr(m, sym["OBJECT_COLOUR"] + i, MARKER_COL)
    wr(m, sym["OBJECT_X"] + i, x)
    wr(m, sym["OBJECT_X_MSB"] + i, 0)
    wr(m, sym["OBJECT_Y"] + i, y)
    wr(m, sym["OBJECT_VEL_X"] + i, 0)
    wr(m, sym["OBJECT_VEL_Y"] + i, 0)
    wr(m, sym["OBJECT_PATH_TIMER"] + i, 255)
    wr(m, sym["OBJECT_DEATH_TIMER"] + i, 0)
    wr(m, sym["OBJECT_HIT_TIMER"] + i, 0)


def poke_enemy(m, sym, y, batched=False):
    _poke_one(m, sym, 1, y, 120)                    # the swept enemy, X=120 (screen x ~128)
    if batched:
        # 8 filler enemies at mid-Y so the swept one falls into a later batch
        for k in range(8):
            _poke_one(m, sym, 2 + k, 150 + 2 * k, 40 + 20 * k)


def live_plan(m, sym):
    live = rd(m, sym["LIVE_PLAN"])[0]
    count = rd(m, sym["RENDER_COUNT"] + live)[0]
    owners = rd(m, sym["INITIAL_OBJECT"] + live, count) if count else []
    ys = rd(m, sym["INITIAL_Y"] + live, count) if count else []
    nb = rd(m, sym["BATCH_COUNT"] + live)[0]
    batch = []
    for b in range(nb):
        first = rd(m, sym["BATCH_FIRST_ASSIGN"] + live + b)[0]
        cnt = rd(m, sym["BATCH_ASSIGN_COUNT"] + live + b)[0]
        braster = rd(m, sym["BATCH_RASTER"] + b)[0]
        aobj = rd(m, sym["ASSIGN_OBJECT"] + first, cnt) if cnt else []
        aslot = rd(m, sym["ASSIGN_SLOT"] + first, cnt) if cnt else []
        ay = rd(m, sym["ASSIGN_Y"] + first, cnt) if cnt else []
        batch.append(dict(raster=braster, objs=aobj, slots=aslot, ys=ay))
    return dict(count=count, owners=owners, ys=ys, batches=batch)


def _near(a, b, t):
    return all(abs(p - q) <= t for p, q in zip(a, b))


# x64sc PAL: sprite X 120 (+ X-MSB 0) -> screen-crop x ~= 120 + 8 .. +32 ; the
# solid marker is red (colour 2 ~ (104,55,43)) -- distinct from grey terrain.
def first_sprite_raster(png, x_lo=126, x_hi=150, target=(136, 33, 32)):
    from PIL import Image
    im = Image.open(png).convert("RGB")
    for raster in range(44, 140):
        y = raster - 16
        hits = sum(1 for x in range(x_lo, x_hi)
                   if _near(im.getpixel((x, y)), target, 60) and im.getpixel((x, y))[0] > im.getpixel((x, y))[2])
        if hits >= 6:
            return raster
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6560)
    ap.add_argument("--out", type=Path, default=REPO / "build" / "sprite-y-sweep")
    ap.add_argument("--prg", type=Path, default=REPO / "build" / "shooter.prg")
    ap.add_argument("--lo", type=int, default=28)
    ap.add_argument("--hi", type=int, default=96)
    ap.add_argument("--settle", type=int, default=6, help="frames to hold each Y before sampling")
    ap.add_argument("--batched", action="store_true",
                    help="also seed 8 filler enemies so the swept object goes through the batch path")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(REPO / "build" / "main.vs")
    proc, m = launch(args.port, args.prg)
    rows = []
    try:
        m.trace_file = (out / "monitor.log").open("w")
        start_playing(m, sym, args.prg)
        for y in range(args.lo, args.hi + 1, 2):
            for _ in range(args.settle):
                m.cmd(f'break {sym["applyFineScroll"]:04x}'); m.cmd("x"); m.cmd("delete")
                poke_enemy(m, sym, y, batched=args.batched)
            # sample at applyFineScroll (LIVE plan is this frame's presented plan)
            m.cmd(f'break {sym["applyFineScroll"]:04x}'); m.cmd("x"); m.cmd("delete")
            poke_enemy(m, sym, y, batched=args.batched)
            sc = rd(m, sym["SORTED_COUNT"])[0]
            so = rd(m, sym["SORTED_OBJECTS"], sc) if sc else []
            lp = live_plan(m, sym)
            # advance into the visible region and screenshot
            res = m.cmd("break exec 0000 ffff if RL == $90")   # raster 144, well past the sprite
            bp = int(re.search(r"BREAK: (\d+)", res)[1])
            m.cmd("x")
            d015 = rd(m, 0xD015)[0]
            spr = [rd(m, 0xD000 + 2 * s, 2) for s in range(8)]
            png = out / f"y{y:03d}.png"
            m.cmd(f'screenshot "{png}" 2')
            m.cmd(f"delete {bp}")
            in_slot = 1 in lp["owners"]
            slot = lp["owners"].index(1) if in_slot else None
            in_batch = any(1 in b["objs"] for b in lp["batches"])
            batch_raster = next((b["raster"] for b in lp["batches"] if 1 in b["objs"]), None)
            vis_raster = first_sprite_raster(png)
            rows.append(dict(
                y=y,
                active=bool(rd(m, sym["OBJECT_ACTIVE"] + 1)[0]),
                in_sorted=(1 in so),
                in_live_plan=in_slot, hw_slot=slot,
                in_batch=in_batch, batch_raster=batch_raster,
                d015_bit=(bool(d015 & (1 << slot)) if slot is not None else None),
                spr_y_reg=(spr[slot][1] if slot is not None else None),
                first_visible_raster=vis_raster,
                collision_eligible=(GAMEPLAY_SPRITE_MIN_Y <= y < GAMEPLAY_SPRITE_END_Y),
            ))
            print(rows[-1])
        (out / "sweep.json").write_text(json.dumps(rows, indent=2))
        # summary
        vis = [r["y"] for r in rows if r["first_visible_raster"]]
        planned = [r["y"] for r in rows if r["in_live_plan"] or r["in_batch"]]
        print("\n--- SUMMARY ---")
        print("first Y in a render plan/batch:", min(planned) if planned else None)
        print("first Y with visible sprite pixels:", min(vis) if vis else None)
        print("collision-eligible floor (source GAMEPLAY_SPRITE_MIN_Y):", GAMEPLAY_SPRITE_MIN_Y)
        print("artifacts:", out)
    finally:
        try:
            m.cmd("quit")
        except Exception:
            pass
        proc.terminate()


if __name__ == "__main__":
    main()
