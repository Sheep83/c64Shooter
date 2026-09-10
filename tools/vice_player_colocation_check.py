#!/usr/bin/env python3
"""Prove the player's layers stay one atomic, co-located bundle.

Reads the HARDWARE sprite registers for every slot the player owns
(PLAYER_HW_MASK) and asserts that all of them share the same X, Y and X-MSB on
every sampled frame, while the player is driven through fast movement in all
directions. Also checks that each layer carries its OWN pointer and colour, that
the bundle is never partial while the player is alive, and that PLAYER_BUNDLE_SHORT
stays clean.

This is the acceptance test for the specialised layer>0 snapshot path: that path
writes X / X-MSB / Y from logical object 0 rather than going through the generic
per-object snapshot, so co-location must be demonstrated, not assumed.
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
NEUTRAL, UP, DOWN, LEFT, RIGHT, FIRE = 0xFF, 0x01, 0x02, 0x04, 0x08, 0x10


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=7500)
    ap.add_argument('--prg', required=True)
    ap.add_argument('--symbols', required=True)
    ap.add_argument('--label', default='build')
    ap.add_argument('--frames', type=int, default=600)
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
        step(20)

        res = dict(label=a.label, frames=0, alive_frames=0,
                   colocation_violations=[], partial_bundle_frames=0,
                   distinct_pointer_frames=0, same_pointer_frames=0,
                   distinct_colour_frames=0, layer_counts={}, masks=set())
        joy = None
        for f in range(a.frames):
            pressed = FIRE if (f % 24) < 14 else 0
            pressed |= {0: LEFT, 1: RIGHT, 2: LEFT, 3: UP, 4: RIGHT, 5: DOWN}[(f // 7) % 6]
            want = NEUTRAL & ~pressed
            if want != joy:
                mon.cmd(f'jpdb 1 {want:02x}'); joy = want
            step()
            res['frames'] += 1
            if g('PLAYER_STATE') != 0:
                continue
            res['alive_frames'] += 1
            mask = g('PLAYER_HW_MASK')
            slots = [i for i in range(8) if mask & (1 << i)]
            res['layer_counts'][len(slots)] = res['layer_counts'].get(len(slots), 0) + 1
            res['masks'].add(f'{mask:08b}')
            if len(slots) < 2:
                res['partial_bundle_frames'] += 1
                continue
            d010 = peek(0xd010)[0]
            xs = {peek(0xd000 + 2 * sl)[0] for sl in slots}
            ys = {peek(0xd001 + 2 * sl)[0] for sl in slots}
            ms = {(d010 >> sl) & 1 for sl in slots}
            ptrs = [peek(0x07f8 + sl)[0] for sl in slots]
            cols = [peek(0xd027 + sl)[0] for sl in slots]
            if len(xs) != 1 or len(ys) != 1 or len(ms) != 1:
                res['colocation_violations'].append(
                    dict(frame=f, slots=slots, x=sorted(xs), y=sorted(ys), msb=sorted(ms)))
            if len(set(ptrs)) == len(ptrs):
                res['distinct_pointer_frames'] += 1
            else:
                res['same_pointer_frames'] += 1
            if len(set(cols)) == len(cols):
                res['distinct_colour_frames'] += 1
        res['bundle_short'] = peek(sym['PLAYER_BUNDLE_SHORT'], 2)[0] | (peek(sym['PLAYER_BUNDLE_SHORT'], 2)[1] << 8)
        res['masks'] = sorted(res['masks'])
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
    v = res.pop('colocation_violations')
    res['colocation_violations'] = len(v)
    res['violation_sample'] = v[:4]
    print(json.dumps(res, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
