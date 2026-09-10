#!/usr/bin/env python3
"""Score / high-score acceptance checks on the running game.

1. Presented-frame period under score churn. `applyFineScroll` runs exactly once
   per PRESENTED frame, so the CPU-cycle delta between consecutive calls is
   19656 (PAL) unless a frame was dropped. Measured in three regimes: idle, a
   realistic award every frame, and the pathological 999999 rebuild every frame.

High-score insertion/rendering above 65535 is covered end to end by
tools/vice_lifecycle_loop.py through the real insertHiscore path.
"""
import argparse, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
PAL_FRAME = 19656


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6680)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--frames', type=int, default=300)
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

        def cyc():
            """Absolute CPU cycle of the START of the current raster frame.

            STOPWATCH alone jitters by a few cycles because the cycle at which
            the main loop reaches applyFineScroll varies with IRQ latency.
            Normalising by the raster position (STOPWATCH - 63*LIN - CYC) --
            the same normalisation check_raster_capture.py uses -- removes that
            and makes an undropped presented frame exactly 19656.
            """
            t = mon.cmd('r')
            m = re.search(r'^\.;[0-9a-f]{4}(?:\s+[0-9a-f]{2}){6}\s+[01]{8}\s+'
                          r'(\d+)\s+(\d+)\s+(\d+)', t, re.M)
            lin, rc, sw = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return sw - 63 * lin - rc

        def peek(addr, n=1):
            t = mon.cmd(f'm {addr:04x} {addr + n - 1:04x}')
            o = []
            for line in t.splitlines():
                m = re.match(r'>C:([0-9a-fA-F]{4})\s+((?:[0-9a-fA-F]{2}[ ]+)+)', line)
                if m:
                    o += [int(b, 16) for b in m.group(2).split()]
            return o[:n]

        def poke(addr, *v):
            mon.cmd(f'> {addr:04x} ' + ' '.join(f'{x:02x}' for x in v))

        bpf = int(re.search(r'BREAK: (\d+)',
                  mon.cmd('break exec 0000 ffff if RL == $137'))[1])

        def step(n=1):
            for _ in range(n):
                mon.cmd(f'condition {bpf} if RL == $000'); mon.cmd('x')
                mon.cmd(f'condition {bpf} if RL == $137'); mon.cmd('x')

        for _ in range(300):
            step()
            if peek(sym['GAME_STATE'])[0] == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if peek(sym['GAME_STATE'])[0] == 1:
                break
        step(10)
        mon.cmd(f'delete {bpf}')

        # ---------- 1. presented-frame period ------------------------------
        mon.cmd(f'break {sym["applyFineScroll"]:04x}')
        print('presented-frame period (applyFineScroll -> applyFineScroll):')
        for label, setup in (
                ('score idle', None),
                ('realistic: +100 every frame', 'award'),
                ('pathological: 999999 rebuild every frame', 'ceiling')):
            mon.cmd('x'); prev = cyc()
            deltas = {}
            for _ in range(a.frames):
                if setup == 'award':
                    poke(sym['SCORE_ADD_LO'], 100, 0, 0)
                    poke(sym['SCORE_DIRTY'], 1)
                elif setup == 'ceiling':
                    poke(sym['SCORE_LO'], 0x3f, 0x42, 0x0f)
                    poke(sym['SCORE_DIRTY'], 1)
                mon.cmd('x')
                c = cyc(); d = c - prev; prev = c
                deltas[d] = deltas.get(d, 0) + 1
            dropped = sum(n for d, n in deltas.items() if d != PAL_FRAME)
            print(f'  {label:<42} deltas={sorted(deltas)}  dropped={dropped}/{a.frames}')
        mon.cmd('delete')

        # 24-bit high-score insertion / rendering above 65535 is proven end to
        # end through the REAL insertHiscore path by tools/vice_lifecycle_loop.py,
        # which compares every rendered attract row against the stored table.
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()


if __name__ == '__main__':
    main()
