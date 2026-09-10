#!/usr/bin/env python3
"""How much lower-screen traffic can the player bundle tolerate?

A physical slot can be recycled for the player only if its previous owner's DMA
is finished in time: SLOT_FREE_RASTER = ownerY + 24 must be <= playerY - 12.
So objects with Y <= playerY - 36 release their slot to the player, and objects
in the band (playerY-36, playerY] hold theirs.

This sweeps N objects INSIDE that blocking band and N objects ABOVE it, and
reports how many player layers actually reach the hardware
(popcount(PLAYER_HW_MASK)) plus the engine's own PLAYER_BUNDLE_SHORT counter.

Works on the single-layer baseline too (expected: always 1 layer).
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
PLAYER_Y = 220


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6840)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--label', default='build')
    ap.add_argument('--frames', type=int, default=40)
    ap.add_argument('--max-n', type=int, default=7)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
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

        def g(n, i=0):
            return peek(sym[n] + i)[0]

        def poke(addr, *v):
            mon.cmd(f'> {addr:04x} ' + ' '.join(f'{x:02x}' for x in v))

        def word(n):
            v = peek(sym[n], 2)
            return v[0] | (v[1] << 8)

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
        step(60)
        has_counter = 'PLAYER_BUNDLE_SHORT' in sym

        for band in ('blocking', 'above'):
            for n in range(0, a.max_n + 1):
                for i in range(1, 16):
                    poke(sym['OBJECT_ACTIVE'] + i, 0)
                    poke(sym['OBJECT_DEATH_TIMER'] + i, 0)
                poke(sym['ENEMY_BULLET_COUNT'], 0)
                ys = ([PLAYER_Y - 30 + 4 * k for k in range(n)] if band == 'blocking'
                      else [90 + 9 * k for k in range(n)])
                for k, y in enumerate(ys):
                    i = k + 1
                    poke(sym['OBJECT_ACTIVE'] + i, 1)
                    poke(sym['OBJECT_TYPE'] + i, 2)
                    poke(sym['OBJECT_Y'] + i, y)
                    poke(sym['OBJECT_X'] + i, 40 + 18 * i)
                    poke(sym['OBJECT_X_MSB'] + i, 0)
                    poke(sym['OBJECT_PATH_TIMER'] + i, 255)
                    poke(sym['OBJECT_VEL_X'] + i, 0)
                    poke(sym['OBJECT_VEL_Y'] + i, 0)
                    poke(sym['OBJECT_DEATH_TIMER'] + i, 0)
                if has_counter:
                    poke(sym['PLAYER_BUNDLE_SHORT'], 0, 0)
                layers = []
                for _ in range(a.frames):
                    step()
                    # These fixtures deliberately park enemies ON TOP of the
                    # player, which with collision live would kill it -- and the
                    # three-layer build reverts to single-sprite presentation
                    # while PLAYER_STATE != 0. Hold the player alive so this
                    # measures SLOT ALLOCATION capacity, not death handling.
                    poke(sym['PLAYER_HIT'], 0)
                    poke(sym['PLAYER_STATE'], 0)
                    poke(sym['OBJECT_Y'], PLAYER_Y)
                    for k, y in enumerate(ys):
                        poke(sym['OBJECT_Y'] + k + 1, y)
                        poke(sym['OBJECT_ACTIVE'] + k + 1, 1)
                    layers.append(bin(g('PLAYER_HW_MASK')).count('1'))
                rows.append(dict(band=band, n=n,
                                 layers_min=min(layers), layers_max=max(layers),
                                 hist={k: layers.count(k) for k in sorted(set(layers))},
                                 bundle_short=word('PLAYER_BUNDLE_SHORT') if has_counter else None,
                                 sorted_count=g('SORTED_COUNT')))
                print(json.dumps(rows[-1]), flush=True)
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
    print(f'\n--- {a.label} ---')
    print(f"{'band':<10}{'N':<4}{'sorted':<8}{'layers':<18}{'bundle_short'}")
    for r in rows:
        print(f"{r['band']:<10}{r['n']:<4}{r['sorted_count']:<8}{str(r['hist']):<18}{r['bundle_short']}")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
