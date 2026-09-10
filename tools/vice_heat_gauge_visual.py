#!/usr/bin/env python3
"""Measure the rendered heat gauge in pixels, at a range of heat values.

Screenshots the running game (VICE `screenshot ... 2`, 384x272, y ~= raster-16)
and reports, for the gauge's X band: the lit rows, the filled span, and the
colour. Also confirms the score digits are still present and unmoved in the same
frame, so the gauge cannot be shown to have disturbed them.
"""
import argparse, json, re, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
HEATS = [0, 60, 150, 240, 299, 300]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=7960)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--scratch', default=tempfile.gettempdir() + '/c64-gauge')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    out = Path(a.scratch); out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path(a.symbols).resolve())
    proc = subprocess.Popen(
        [X64SC, '-default', '-pal', '-warp', '+sound', '-remotemonitor',
         '-remotemonitoraddress', f'ip4://127.0.0.1:{a.port}',
         '-autostartprgmode', '1', '-autostart', str(Path(a.prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    mon = Monitor(a.port)
    rows = []
    try:
        mon.cmd('delete'); mon.cmd('resourceset "JoyPort2Device" "37"')
        bp = int(re.search(r'BREAK: (\d+)',
                 mon.cmd('break exec 0000 ffff if RL == $137'))[1])

        def step(n=1):
            for _ in range(n):
                mon.cmd(f'condition {bp} if RL == $000'); mon.cmd('x')
                mon.cmd(f'condition {bp} if RL == $137'); mon.cmd('x')

        def peek(addr, n=1):
            t = mon.cmd(f'm {addr:04x} {addr + n - 1:04x}')
            o = []
            for line in t.splitlines():
                m = re.match(r'>C:([0-9a-fA-F]{4})\s+((?:[0-9a-fA-F]{2}[ ]+)+)', line)
                if m:
                    o += [int(b, 16) for b in m.group(2).split()]
            return o[:n]

        def g(n):
            return peek(sym[n])[0]

        def poke(addr, *v):
            mon.cmd(f'> {addr:04x} ' + ' '.join(f'{x:02x}' for x in v))

        for _ in range(300):
            step()
            if g('GAME_STATE') == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if g('GAME_STATE') == 1:
                break
        poke(sym['PLAYER_LIVES'], 255)
        step(20)
        mon.cmd(f"f {sym['OBJECT_ACTIVE'] + 1:04x} {sym['OBJECT_ACTIVE'] + 15:04x} 00")

        for h in HEATS:
            poke(sym['WEAPON_HEAT_LO'], h & 0xff, h >> 8)
            poke(sym['WEAPON_OVERHEATED'], 0)
            # let updateWeaponHeat recompute the width and the HUD phase compose+publish
            for _ in range(6):
                mon.cmd(f"f {sym['OBJECT_ACTIVE'] + 1:04x} {sym['OBJECT_ACTIVE'] + 15:04x} 00")
                poke(sym['WEAPON_HEAT_LO'], h & 0xff, h >> 8)
                poke(sym['WEAPON_OVERHEATED'], 0)
                step()
            width = g('HEAT_GAUGE_WIDTH')
            png = out / f'gauge_{h:03d}.png'
            mon.cmd(f'screenshot "{png}" 2')
            step(1)
            im = Image.open(png).convert('RGB'); w, hh = im.size
            px = im.load()
            # The gauge and the score are the only light-green things in the
            # opened top border; a plain non-black test picks up terrain, so
            # filter on the colour and on the HUD's own row band.
            # HUD_Y 22 -> sprite row 0 at screenshot y 6; rules at rows 8/13 -> y 14/19.
            def isgreen(c):
                return c[1] > 200 and c[0] < 220 and c[2] < 200 and c[1] - c[2] > 40
            lit = [(x, y) for y in range(8, 26) for x in range(220, 300)
                   if isgreen(px[x, y])]
            score = [(x, y) for y in range(0, 30) for x in range(150, 210)
                     if isgreen(px[x, y])]
            rec = dict(heat=h, width_var=width)
            if lit:
                xs = sorted({x for x, _ in lit}); ys = sorted({y for _, y in lit})
                rec.update(gauge_x=(xs[0], xs[-1]), gauge_rows=(ys[0], ys[-1]),
                           gauge_lit_px=len(lit),
                           gauge_colours=sorted({px[x, y] for x, y in lit}))
            else:
                rec.update(gauge_x=None)
            rec['score_lit_px'] = len(score)
            if score:
                sxs = sorted({x for x, _ in score})
                rec['score_x'] = (sxs[0], sxs[-1])
            rows.append(rec)
            if not a.keep:
                png.unlink(missing_ok=True)
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
    for r in rows:
        print(json.dumps(r))
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
