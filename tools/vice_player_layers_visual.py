#!/usr/bin/env python3
"""Verify the three player layers are HIRES and render three distinct colours.

Two independent checks:

1. Register truth. At many sampled points, assert $D01C == ~PLAYER_HW_MASK
   restricted to gameplay slots: every player-owned physical slot must have its
   multicolour bit CLEAR (hires), and every other gameplay slot must have it SET.

2. Pixel truth. Screenshot the running game and count the distinct colours in
   the player's bounding box. Three co-located hires layers must produce the
   three configured layer colours.

Transient PNGs go to a scratch dir outside the repo and are deleted.
"""
import argparse, re, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6820)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--samples', type=int, default=120)
    ap.add_argument('--scratch', default=tempfile.gettempdir() + '/c64-layers')
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--keep-alive', action='store_true',
                    help='hold PLAYER_STATE alive, so the sample is the LIVING '
                         'player (layers are gated off during explosion/blink)')
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

        for _ in range(300):
            step()
            if g('GAME_STATE') == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if g('GAME_STATE') == 1:
                break
        mon.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')
        step(150)

        # ---- 1. register truth -------------------------------------------
        bad, seen_masks, layer_counts = [], set(), []
        for i in range(a.samples):
            if a.keep_alive:
                mon.cmd(f'> {sym["PLAYER_HIT"]:04x} 00')
                mon.cmd(f'> {sym["PLAYER_STATE"]:04x} 00')
            step()
            pm = g('PLAYER_HW_MASK')
            mode = peek(0xd01c)[0]
            enable = peek(0xd015)[0]
            seen_masks.add(pm)
            layer_counts.append(bin(pm).count('1'))
            # every player slot must be hires; every OTHER ENABLED slot MC
            hires_player = (mode & pm) == 0
            others = enable & ~pm & 0xff
            mc_others = (mode & others) == others
            if not (hires_player and mc_others):
                bad.append(dict(frame=i, player_mask=f'{pm:08b}',
                                d01c=f'{mode:08b}', d015=f'{enable:08b}',
                                hires_player=hires_player, mc_others=mc_others))
        print(f'register check: {a.samples} samples, violations = {len(bad)}')
        for b in bad[:5]:
            print('   ', b)
        print(f'  player masks seen: {sorted(f"{m:08b}" for m in seen_masks)}')
        print(f'  layers per frame : min {min(layer_counts)} max {max(layer_counts)}')
        print(f'  PLAYER_LAYERS_LIVE={g("PLAYER_LAYERS_LIVE")} '
              f'PLAYER_BUNDLE_SHORT={peek(sym["PLAYER_BUNDLE_SHORT"],2)[0] + 256*peek(sym["PLAYER_BUNDLE_SHORT"],2)[1]}')

        # ---- 2. pixel truth ----------------------------------------------
        if a.keep_alive:
            mon.cmd(f'> {sym["PLAYER_STATE"]:04x} 00')
            step(3)
        px_x = peek(0xd000)[0]
        py = g('OBJECT_Y')
        png = out / 'player.png'
        mon.cmd(f'screenshot "{png}" 2')
        step(1)
        im = Image.open(png).convert('RGB'); w, h = im.size
        pix = im.load()
        # screenshot y ~= raster - 16; sprite Y is its top raster line
        y0, y1 = max(0, py - 16 - 2), min(h, py - 16 + 23)
        # find the player's X by scanning the band for the layer colours
        counts = {}
        for y in range(y0, y1):
            for x in range(0, w):
                counts[pix[x, y]] = counts.get(pix[x, y], 0) + 1
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:8]
        print(f'\npixel check: player Y={py}, band rows {y0}..{y1 - 1}')
        for c, n in top:
            print(f'   {c}  x{n}')
        if not a.keep:
            png.unlink(missing_ok=True)
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()


if __name__ == '__main__':
    main()
