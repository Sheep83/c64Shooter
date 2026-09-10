#!/usr/bin/env python3
"""Measure the authored wave cadence of the running level.

Breaks at startAuthoredWave and records, per wave: the physical frame it started,
its size (WAVE_ENEMY_COUNT), its attack id, its member spawn interval and the
SCROLL_ROW it fired at. Reports the frame gaps between consecutive wave starts,
which is the number Goal 1 is about.

Joystick stays NEUTRAL throughout except the single tap that starts the game, so
nothing is shot and the cadence is the level's own.
"""
import argparse, json, re, statistics, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
PAL_FRAME = 19656


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6900)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--waves', type=int, default=24)
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
    waves = []
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

        def regs():
            """(X register, absolute cycle of this raster frame's start).

            X is startAuthoredWave's entry argument: the trigger index. Reading
            WAVE_ENEMY_COUNT at the breakpoint would return the PREVIOUS wave's
            values, because the routine sets them after entry -- so the wave's
            real size/attack are read from the trigger tables via X instead.
            """
            t = mon.cmd('r')
            m = re.search(r'^\.;[0-9a-f]{4}\s+[0-9a-f]{2}\s+([0-9a-f]{2})'
                          r'(?:\s+[0-9a-f]{2}){4}\s+[01]{8}\s+(\d+)\s+(\d+)\s+(\d+)', t, re.M)
            if not m:
                raise RuntimeError('cannot parse registers:\n' + t)
            x = int(m.group(1), 16)
            lin, rc, sw = int(m.group(2)), int(m.group(3)), int(m.group(4))
            return x, sw - 63 * lin - rc

        def frame_cycle():
            """Absolute cycle of the current raster frame's start -- turning the
            free-running stopwatch into a stable frame counter."""
            t = mon.cmd('r')
            m = re.search(r'^\.;[0-9a-f]{4}(?:\s+[0-9a-f]{2}){6}\s+[01]{8}\s+'
                          r'(\d+)\s+(\d+)\s+(\d+)', t, re.M)
            lin, rc, sw = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return sw - 63 * lin - rc

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
        mon.cmd(f'delete {bp}')
        mon.cmd(f'break {sym["startAuthoredWave"]:04x}')
        for _ in range(a.waves):
            mon.cmd('x')
            idx, cyc = regs()
            waves.append(dict(cycle=cyc, trigger=idx,
                              size=g('waveTrigCount', idx),
                              attack=g('waveTrigAttackId', idx),
                              interval=g('waveTrigInterval', idx),
                              trig_row=g('waveTrigRowLo', idx) | (g('waveTrigRowHi', idx) << 8),
                              scroll_row=g('SCROLL_ROW') | (g('SCROLL_ROW_HI') << 8)))
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

    gaps = [round((waves[i]['cycle'] - waves[i - 1]['cycle']) / PAL_FRAME)
            for i in range(1, len(waves))]
    print(f"{'#':>3} {'trig':>5} {'trigRow':>8} {'atRow':>6} {'size':>5} {'atk':>4} {'iv':>3}  gap(frames)")
    for i, w in enumerate(waves):
        gp = '' if i == 0 else f"{gaps[i-1]:>6}"
        print(f"{i:>3} {w['trigger']:>5} {w['trig_row']:>8} {w['scroll_row']:>6} "
              f"{w['size']:>5} {w['attack']:>4} {w['interval']:>3} {gp}")
    print()
    print(f"waves observed        : {len(waves)}")
    print(f"wave sizes seen       : {sorted(set(w['size'] for w in waves))}")
    print(f"six-enemy waves       : {sum(1 for w in waves if w['size'] == 6)}")
    print(f"distinct attack ids   : {sorted(set(w['attack'] for w in waves))}")
    print(f"gaps (frames)         : {sorted(set(gaps))}")
    print(f"mean gap              : {statistics.mean(gaps):.2f} frames (target 120)")
    if a.out:
        Path(a.out).write_text(json.dumps(dict(waves=waves, gaps=gaps), indent=2))


if __name__ == '__main__':
    main()
