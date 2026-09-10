#!/usr/bin/env python3
"""Measure the rendered HUD score font in the running game, in pixels.

Screenshots the live game (VICE `screenshot ... 2`, 384x272, y ~= raster - 16)
for a set of score values and reports, per value: the lit rows, glyph height,
horizontal span, centre, and how many distinct colours the digits use. Centre
stability across values is what proves the number does not shift horizontally.

Transient PNGs go to a scratch dir outside the repo and are deleted unless
--keep is given.
"""
import argparse, re, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
VALUES = [0, 123456, 999999, 65536, 111111, 888888]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6620)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--scratch', default=tempfile.gettempdir() + '/c64-fontmeasure')
    ap.add_argument('--values', type=int, nargs='+', default=VALUES)
    ap.add_argument('--keep', action='store_true')
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
    rows_out = []
    try:
        mon.cmd('delete'); mon.cmd('resourceset "JoyPort2Device" "37"')
        bp = int(re.search(r'BREAK: (\d+)',
                 mon.cmd('break exec 0000 ffff if RL == $137'))[1])

        def step(n=1):
            for _ in range(n):
                mon.cmd(f'condition {bp} if RL == $000'); mon.cmd('x')
                mon.cmd(f'condition {bp} if RL == $137'); mon.cmd('x')

        def state():
            t = mon.cmd(f'm {sym["GAME_STATE"]:04x} {sym["GAME_STATE"]:04x}')
            return int(re.search(r'>C:[0-9a-f]{4}\s+([0-9a-fA-F]{2})', t)[1], 16)

        for _ in range(300):
            step()
            if state() == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if state() == 1:
                break
        step(20)
        for v in a.values:
            mon.cmd(f'> {sym["SCORE_LO"]:04x} '
                    f'{v & 0xff:02x} {(v >> 8) & 0xff:02x} {(v >> 16) & 0xff:02x}')
            mon.cmd(f'> {sym["SCORE_DIRTY"]:04x} 01')
            step(24)                       # 7-frame deferred rebuild, with margin
            png = out / f'score_{v:06d}.png'
            mon.cmd(f'screenshot "{png}" 2')
            step(1)
            im = Image.open(png).convert('RGB')
            w, h = im.size
            px = im.load()
            # The score is the only light-green thing in the opened top border.
            band = [(x, y) for y in range(0, 60) for x in range(w)
                    if px[x, y][1] > 200 and px[x, y][0] < 220 and px[x, y][2] < 200
                    and px[x, y][1] - px[x, y][2] > 40]
            if not band:
                rows_out.append((v, None)); continue
            ys = sorted({y for _, y in band}); xs = sorted({x for x, _ in band})
            colours = {px[x, y] for x, y in band}
            rows_out.append((v, dict(rows=(ys[0], ys[-1]), height=ys[-1] - ys[0] + 1,
                                     x=(xs[0], xs[-1]), span=xs[-1] - xs[0] + 1,
                                     centre=(xs[0] + xs[-1]) / 2,
                                     lit=len(band), colours=len(colours),
                                     colour=sorted(colours)[0])))
            if not a.keep:
                png.unlink(missing_ok=True)
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

    print(f'{"value":>7} {"rows":>10} {"h":>3} {"x":>10} {"span":>5} {"centre":>7} '
          f'{"lit":>5} {"cols":>5}  colour')
    for v, r in rows_out:
        if r is None:
            print(f'{v:>7}  NO GREEN PIXELS FOUND'); continue
        print(f'{v:>7} {str(r["rows"]):>10} {r["height"]:>3} {str(r["x"]):>10} '
              f'{r["span"]:>5} {r["centre"]:>7} {r["lit"]:>5} {r["colours"]:>5}  {r["colour"]}')
    centres = {r['centre'] for _, r in rows_out if r}
    heights = {r['height'] for _, r in rows_out if r}
    print(f'\ncentre stable across values: {len(centres) == 1} {sorted(centres)}')
    print(f'height stable across values: {len(heights) == 1} {sorted(heights)}')


if __name__ == '__main__':
    main()
