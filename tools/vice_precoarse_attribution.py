#!/usr/bin/env python3
"""Attribute the pre-coarse main-loop cost, routine by routine, in CPU cycles.

Coarse-scroll admission is gated on the raster line reached at
prepareBackgroundCoarse. Everything the main loop does between the top of
gameLoop's !frameLoop and that call pushes the gate later. This breaks on each
routine in that chain and uses VICE's free-running cycle counter (STOPWATCH) to
time each SEGMENT, so the 1-layer -> 2-layer difference can be attributed to
actual code rather than guessed at.

STOPWATCH deltas include stolen badline / sprite-DMA cycles, which is exactly
what matters here.
"""
import argparse, json, re, statistics, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'

CHAIN = ['updateTurretStream', 'buildSortedObjectList', 'sortObjectsByY',
         'buildInitialSpriteSnapshot', 'buildBatchSpriteSchedule',
         'planCoarseBulletSuppression', 'predecodeNextStageRow',
         'prepareBackgroundCoarse']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=7100)
    ap.add_argument('--prg', required=True)
    ap.add_argument('--symbols', required=True)
    ap.add_argument('--label', default='build')
    ap.add_argument('--frames', type=int, default=200)
    ap.add_argument('--warmup', type=int, default=260,
                    help='frames of real play before sampling, so the authored wave '
                         'director has actually spawned enemies. Without this the '
                         'sorted list holds ONLY the player layers (SORTED_COUNT=2) '
                         'and the measurement is of an empty scene.')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    sym = symbols(Path(a.symbols).resolve())
    chain = [n for n in CHAIN if n in sym]
    addr_of = {sym[n]: n for n in chain}
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

        def regs():
            """(pc, raster line, absolute cycle)"""
            t = mon.cmd('r')
            m = re.search(r'^\.;([0-9a-f]{4})(?:\s+[0-9a-f]{2}){6}\s+[01]{8}\s+'
                          r'(\d+)\s+(\d+)\s+(\d+)', t, re.M)
            return int(m.group(1), 16), int(m.group(2)), int(m.group(4))

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
        step(a.warmup)
        mon.cmd(f'delete {bp}')
        for n in chain:
            mon.cmd(f'break {sym[n]:04x}')

        segs = {n: [] for n in chain}
        sorted_counts = []
        totals = []           # frameLoop-start -> prepareBackgroundCoarse
        gate_raster = []
        prev_name = prev_cyc = None
        loop_start_cyc = None
        # representative burst-fire input, same shape as the scroll-stop fixture
        for i in range(a.frames * len(chain)):
            if (i // len(chain)) % 24 < 14:
                mon.cmd('jpdb 1 ef')
            else:
                mon.cmd('jpdb 1 ff')
            mon.cmd('x')
            pc, lin, cyc = regs()
            name = addr_of.get(pc)
            if name is None:
                continue
            if prev_name is not None and prev_cyc is not None:
                segs[prev_name].append(cyc - prev_cyc)
            if name == 'updateTurretStream':
                loop_start_cyc = cyc
                sorted_counts.append(g('SORTED_COUNT'))
            if name == 'prepareBackgroundCoarse':
                gate_raster.append(lin)
                if loop_start_cyc is not None:
                    totals.append(cyc - loop_start_cyc)
                    loop_start_cyc = None
            prev_name, prev_cyc = name, cyc

        def stats(v):
            if not v:
                return None
            v = sorted(v)
            return dict(n=len(v), median=int(statistics.median(v)),
                        mean=round(statistics.mean(v), 1),
                        p90=v[int(0.90 * len(v))], max=v[-1])

        res = dict(label=a.label,
                   sorted_count=stats(sorted_counts),
                   segments={n: stats(segs[n]) for n in chain if segs[n]},
                   precoarse_total=stats(totals),
                   gate_raster=stats(gate_raster))
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
    print(json.dumps(res, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
