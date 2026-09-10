#!/usr/bin/env python3
"""Measure VISIBLE scroll stops under representative Level 1 play.

Why this exists
---------------
Every previous automated pass called the three-layer player healthy while manual
play showed heavy scroll stops. The reason is an instrumentation gap, not a
disagreement: `frame_cycle_deltas [19656]` measures the PRESENTED FRAME PERIOD,
and with a per-physical-frame breakpoint that is exact by construction. A scroll
stop is not a dropped frame -- the machine keeps presenting perfect PAL frames
while the TERRAIN STOPS MOVING, because coarse-scroll admission is deferred.

So this probe measures what the eye actually sees: it samples
(SCROLL_FINE, SCROLL_ROW) every physical frame and counts CONSECUTIVE frames in
which that pair does not change. That run length is the visible stall.

Input is a deterministic, frame-indexed play pattern (movement + firing) so all
layer counts are driven identically; nothing depends on wall-clock or host speed.

All transient output goes to a scratch dir outside the repo.
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
NEUTRAL = 0xFF
UP, DOWN, LEFT, RIGHT, FIRE = 0x01, 0x02, 0x04, 0x08, 0x10


def joy_for_frame(f, mode):
    """Deterministic, frame-indexed joystick state (bits are ACTIVE LOW)."""
    if mode == 'passive':
        return NEUTRAL
    pressed = 0
    if mode in ('play', 'fire'):
        # Fire in bursts rather than held forever: held fire destroys turrets and
        # has previously invalidated 'passive symptom' captures.
        if (f % 24) < 14:
            pressed |= FIRE
    if mode in ('play', 'move'):
        phase = (f // 45) % 6
        pressed |= {0: LEFT, 1: RIGHT, 2: LEFT, 3: UP, 4: RIGHT, 5: DOWN}[phase]
    return NEUTRAL & ~pressed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6950)
    ap.add_argument('--prg', required=True)
    ap.add_argument('--symbols', required=True)
    ap.add_argument('--label', default='build')
    ap.add_argument('--frames', type=int, default=2400)
    ap.add_argument('--mode', default='play',
                    choices=('play', 'passive', 'move', 'fire'))
    ap.add_argument('--stop-threshold', type=int, default=6,
                    help='runs at least this long are recorded with context')
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

        def w(n):
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
        mon.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')   # long run; combat stays live
        step(30)

        scroll_addr = sym['SCROLL_FINE']             # FINE, ROW, ROW_HI contiguous
        prev = None
        run = 0
        runs = []            # (start_frame, length)
        events = []
        coarse_steps = 0
        fine_steps = 0
        prev_row = None
        joy = None
        max_objects = max_batches = 0
        for f in range(a.frames):
            want = joy_for_frame(f, a.mode)
            if want != joy:
                mon.cmd(f'jpdb 1 {want:02x}')
                joy = want
            step()
            fine, lo, hi = peek(scroll_addr, 3)
            row = lo | (hi << 8)
            state = (fine, row)
            if prev_row is not None and row != prev_row:
                coarse_steps += 1
            if prev is not None and state != prev:
                fine_steps += 1
                if run:
                    runs.append((f - run, run))
                    if run >= a.stop_threshold:
                        live = g('LIVE_PLAN')
                        events.append(dict(
                            frame=f - run, length=run, row=row,
                            sorted_count=g('SORTED_COUNT'),
                            batches=g('BATCH_COUNT', live),
                            render_count=g('RENDER_COUNT', live),
                            active=sum(peek(sym['OBJECT_ACTIVE'], 16)),
                            player_y=g('OBJECT_Y'),
                            turret_pressure=g('TURRET_PRESSURE_ACTIVE'),
                            bullets=g('ENEMY_BULLET_COUNT'),
                            wave_spawned=g('WAVE_SPAWNED'),
                            wave_size=g('WAVE_ENEMY_COUNT'),
                            player_layers=bin(g('PLAYER_HW_MASK')).count('1')))
                run = 0
            elif prev is not None:
                run += 1
            prev, prev_row = state, row
            if f % 17 == 0:                 # cheap periodic pressure sampling
                live = g('LIVE_PLAN')
                max_objects = max(max_objects, g('SORTED_COUNT'))
                max_batches = max(max_batches, g('BATCH_COUNT', live))
        if run:
            runs.append((a.frames - run, run))

        diag = peek(sym['COARSE_DEFER_LIVE'], 11)
        result = dict(
            label=a.label, mode=a.mode, frames=a.frames,
            coarse_steps=coarse_steps,
            frames_per_coarse=round(a.frames / coarse_steps, 2) if coarse_steps else None,
            scroll_state_changes=fine_steps,
            stopped_frames=sum(l for _, l in runs),
            stopped_pct=round(100 * sum(l for _, l in runs) / a.frames, 1),
            longest_stop_frames=max((l for _, l in runs), default=0),
            stop_runs_ge_4=sum(1 for _, l in runs if l >= 4),
            stop_runs_ge_8=sum(1 for _, l in runs if l >= 8),
            stop_runs_ge_16=sum(1 for _, l in runs if l >= 16),
            stop_run_histogram={k: sum(1 for _, l in runs if l == k)
                                for k in sorted({l for _, l in runs})},
            coarse_defer_live=diag[0] | (diag[1] << 8),
            coarse_defer_beam=diag[2] | (diag[3] << 8),
            coarse_defer_cutoff=diag[4] | (diag[5] << 8),
            coarse_admit=diag[6] | (diag[7] << 8),
            coarse_hold_max=diag[9],
            coarse_hold_max_reason=diag[10],
            flip_admit=w('SS_FLIP_ADMIT'), flip_fallback=w('SS_FLIP_FALLBACK'),
            legacy_pageb_block=w('SS_LEGACY_PAGEB_BLOCK'),
            catchups=w('RASTER_CATCHUPS'), replay_frames=w('RASTER_REPLAY_FRAMES'),
            bundle_short=w('PLAYER_BUNDLE_SHORT'),
            layers_live=g('PLAYER_LAYERS_LIVE'),
            max_sorted=max_objects, max_batches=max_batches,
            worst_events=sorted(events, key=lambda e: -e['length'])[:8])
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('stop_run_histogram', 'worst_events')}, indent=2))
    print('worst stalls:')
    for e in result['worst_events']:
        print('   ', e)
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
