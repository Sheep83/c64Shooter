#!/usr/bin/env python3
"""Measure composeScoreSprites cost in situ, and prove double buffering holds.

Cost is (raster line, raster cycle) at publishScoreBuffer minus the same at
composeScoreSprites, in PAL cycles (312 lines x 63 cycles). Measured on the real
game with the real raster IRQ and multiplexer running, so ambient badline and
sprite DMA inflation is included -- that is the number that matters.

Also records, at every compose, which pair the compositor is drawing into
(SCORE_BACKBUF) and which pair is published (hudProofPtr), so a compose into the
pair the VIC is fetching would be caught.
"""
import argparse, re, statistics, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
LINES, CYCLES = 312, 63


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6640)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--samples', type=int, default=40)
    ap.add_argument('--label', default='build')
    a = ap.parse_args()
    sym = symbols(Path(a.symbols).resolve())
    proc = subprocess.Popen(
        [X64SC, '-default', '-pal', '-warp', '+sound', '-remotemonitor',
         '-remotemonitoraddress', f'ip4://127.0.0.1:{a.port}',
         '-autostartprgmode', '1', '-autostart', str(Path(a.prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    mon = Monitor(a.port)
    costs, entries, pairs = [], [], []
    try:
        mon.cmd('delete'); mon.cmd('resourceset "JoyPort2Device" "37"')

        def rlrc():
            """(raster line, absolute CPU cycle) from the monitor register dump.

            VICE prints `... NV-BDIZC LIN CYC  STOPWATCH`; STOPWATCH is a free
            running CPU-cycle counter, so its delta is the exact in-situ cost
            including every stolen badline / sprite-DMA cycle.
            """
            t = mon.cmd('r')
            m = re.search(r'^\.;[0-9a-f]{4}(?:\s+[0-9a-f]{2}){6}\s+[01]{8}\s+'
                          r'(\d+)\s+(\d+)\s+(\d+)', t, re.M)
            if not m:
                raise RuntimeError('cannot parse register line:\n' + t)
            return int(m.group(1)), int(m.group(3))

        def peek(addr, n=1):
            t = mon.cmd(f'm {addr:04x} {addr + n - 1:04x}')
            o = []
            for line in t.splitlines():
                m = re.match(r'>C:([0-9a-fA-F]{4})\s+((?:[0-9a-fA-F]{2}[ ]+)+)', line)
                if m:
                    o += [int(b, 16) for b in m.group(2).split()]
            return o[:n]

        def state():
            return peek(sym['GAME_STATE'])[0]

        bpf = int(re.search(r'BREAK: (\d+)',
                  mon.cmd('break exec 0000 ffff if RL == $137'))[1])

        def step(n=1):
            for _ in range(n):
                mon.cmd(f'condition {bpf} if RL == $000'); mon.cmd('x')
                mon.cmd(f'condition {bpf} if RL == $137'); mon.cmd('x')

        for _ in range(300):
            step()
            if state() == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if state() == 1:
                break
        step(10)
        mon.cmd(f'delete {bpf}')
        mon.cmd(f'break {sym["composeScoreSprites"]:04x}')
        mon.cmd(f'break {sym["publishScoreBuffer"]:04x}')
        score = 111111
        for i in range(a.samples):
            score = 999999 if i % 3 == 0 else (123456 if i % 3 == 1 else 808080)
            mon.cmd(f'> {sym["SCORE_LO"]:04x} '
                    f'{score & 0xff:02x} {(score >> 8) & 0xff:02x} {(score >> 16) & 0xff:02x}')
            mon.cmd(f'> {sym["SCORE_DIRTY"]:04x} 01')
            mon.cmd('x')                                  # -> composeScoreSprites
            l0, c0 = rlrc()
            back = peek(sym['SCORE_BACKBUF'])[0]
            pub = peek(sym['hudProofPtr'], 2)
            mon.cmd('x')                                  # -> publishScoreBuffer
            l1, c1 = rlrc()
            d = c1 - c0                       # absolute stopwatch delta
            costs.append(d); entries.append(l0)
            # SCORE_BACKBUF is the offset of the pair being DRAWN ($00 front / $80 back)
            drawn = 'front' if back == 0 else 'back'
            published = 'front' if pub[0] == sym_ptr_front(sym) else 'back'
            pairs.append((drawn, published, tuple(pub)))
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

    print(f'--- {a.label} ---')
    print(f'compose cost cycles: min {min(costs)}  max {max(costs)}  '
          f'median {int(statistics.median(costs))}  (n={len(costs)})')
    print(f'raster lines: min {min(costs) / CYCLES:.1f}  max {max(costs) / CYCLES:.1f}')
    print(f'entry raster observed: {min(entries)}..{max(entries)}')
    violations = [p for p in pairs if p[0] == p[1]]
    print(f'composes into the PUBLISHED pair: {len(violations)} / {len(pairs)}')
    seen = sorted({p[2] for p in pairs})
    print(f'published pointer pairs seen: {[tuple(hex(v) for v in s) for s in seen]}')


def sym_ptr_front(sym):
    return 0x2f00 // 64          # $bc


if __name__ == '__main__':
    main()
