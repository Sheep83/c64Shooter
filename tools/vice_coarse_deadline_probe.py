#!/usr/bin/env python3
"""Why the terrain stops: where in the frame does coarse admission get decided?

The coarse scroll is admitted only if prepareBackgroundCoarse reaches its gate
before raster BG_COARSE_LATEST_START (184). Every extra player layer adds
main-loop work AHEAD of that call (one more sorted entry to insert-sort, one more
plan entry to snapshot, one more slot to mask), so the call drifts later in the
frame. This samples the raster line at prepareBackgroundCoarse entry and reports
the distribution against the deadline -- the direct causal measurement behind the
scroll stops.
"""
import argparse, json, re, statistics, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
DEADLINE = 184
NEUTRAL = 0xFF


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6980)
    ap.add_argument('--prg', required=True)
    ap.add_argument('--symbols', required=True)
    ap.add_argument('--label', default='build')
    ap.add_argument('--samples', type=int, default=500)
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

        def g(n):
            return peek(sym[n])[0]

        def raster_line():
            t = mon.cmd('r')
            m = re.search(r'^\.;[0-9a-f]{4}(?:\s+[0-9a-f]{2}){6}\s+[01]{8}\s+(\d+)', t, re.M)
            return int(m.group(1))

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
        step(30)
        mon.cmd(f'delete {bp}')
        mon.cmd(f'break {sym["prepareBackgroundCoarse"]:04x}')
        lines = []
        for i in range(a.samples):
            if i % 24 < 14:
                mon.cmd('jpdb 1 ef')
            else:
                mon.cmd('jpdb 1 ff')
            mon.cmd('x')
            lines.append(raster_line())
        late = [l for l in lines if l >= DEADLINE]
        res = dict(label=a.label, samples=len(lines), deadline=DEADLINE,
                   min=min(lines), median=int(statistics.median(lines)),
                   mean=round(statistics.mean(lines), 1), max=max(lines),
                   pct_past_deadline=round(100 * len(late) / len(lines), 1),
                   past_deadline=len(late),
                   p90=sorted(lines)[int(0.90 * len(lines))],
                   p99=sorted(lines)[int(0.99 * len(lines))])
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
