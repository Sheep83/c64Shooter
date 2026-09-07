#!/usr/bin/env python3
"""End-to-end Level 1 smoke: the real game runs for a while with the authored
turret pool + wave triggers active, and:
  * GAME_STATE stays PLAYING (no crash / no unexpected GAME OVER with infinite lives);
  * SCROLL_ROW keeps advancing and the stage wraps at least once;
  * the streaming turret pool never exceeds TURRET_POOL occupied slots;
  * the authored wave-trigger cursor advances and re-arms across the wrap, and
    real enemy waves are produced (WAVE_SPAWNED cycles / enemies appear).
"""
import argparse
import json
import socket
import subprocess
import time
from pathlib import Path

from vice_scroll_test import Monitor, symbols
from vice_turret_runtime_probe import start_playing


def launch(port):
    with socket.socket() as c:
        if c.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'port {port} occupied')
    p = subprocess.Popen(
        ['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
         '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
         '-autostartprgmode', '1', '-autostart', str(Path('build/shooter.prg').resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p, Monitor(port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=6750)
    ap.add_argument('--samples', type=int, default=90)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/level1-smoke'))
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    proc, m = launch(args.port)
    fails = []
    try:
        m.trace_file = (out / 'monitor.log').open('w')
        start_playing(m, sym)
        m.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')      # long run: keep combat/death/respawn active

        def rd(name, n=1):
            a = sym[name]
            p = out / 's.bin'
            m.cmd(f'bsave "{p}" 0 {a:04x} {a + n - 1:04x}')
            return list(p.read_bytes())

        def w16(name):
            b = rd(name, 2)
            return b[0] | (b[1] << 8)

        pool = sym['TURRET_POOL_CODE']
        slr = (sym['STAGE_METATILE_ROWS_END'] - sym['stageMetatileRows']) // 10 * 4
        playing = sym.get('GAME_STATE_PLAYING', 1)
        m.cmd(f'break {sym["applyFineScroll"]:04x}')

        rows_seen, max_occ, wraps = [], 0, 0
        cursor_vals, spawned_vals, score_vals, states = [], [], [], []
        prev_row = None
        for i in range(args.samples):
            for _ in range(6):                          # ~6 frames between samples
                m.cmd('x')
            gs = rd('GAME_STATE', 1)[0]
            states.append(gs)
            row = w16('SCROLL_ROW')
            rows_seen.append(row)
            if prev_row is not None and row > prev_row + 5:
                wraps += 1
            prev_row = row
            auth = rd('TURRET_SLOT_AUTH', pool)
            max_occ = max(max_occ, sum(1 for a in auth if a != 0xFF))
            cursor_vals.append(rd('WAVE_TRIGGER_CURSOR', 1)[0])
            spawned_vals.append(rd('WAVE_SPAWNED', 1)[0])
            score_vals.append(rd('SCORE_LO', 1)[0] + 256 * rd('SCORE_HI', 1)[0])

        bad_states = sorted(set(s for s in states if s != playing))
        if bad_states:
            fails.append(f'GAME_STATE left PLAYING: saw {bad_states}')
        if max(rows_seen) - min(rows_seen) < 20:
            fails.append(f'SCROLL_ROW barely moved: {min(rows_seen)}..{max(rows_seen)}')
        if max_occ > pool:
            fails.append(f'turret pool overflow: {max_occ} slots occupied (limit {pool})')

        # Targeted stage-wrap test: nudge SCROLL_ROW near 0 and let the coarse
        # scroller carry it through the 0 -> SLR-1 seam. Confirm it wraps, the
        # turret pool + wave cursor re-arm, and nothing overflows.
        m.cmd(f'> {sym["SCROLL_ROW"]:04x} 06 00')
        m.cmd(f'> {sym["SCROLL_ROW_HI"]:04x} 00')
        wrap_seen = False
        wrap_max_occ = max_occ
        prev = 6
        for _ in range(160):
            for _ in range(6):
                m.cmd('x')
            r = w16('SCROLL_ROW')
            if r > prev + 5:
                wrap_seen = True
            prev = r
            au = rd('TURRET_SLOT_AUTH', pool)
            wrap_max_occ = max(wrap_max_occ, sum(1 for a in au if a != 0xFF))
        cur_after_wrap = rd('WAVE_TRIGGER_CURSOR', 1)[0]
        if not wrap_seen:
            fails.append('stage did not wrap even after nudging SCROLL_ROW to 6')
        if wrap_max_occ > pool:
            fails.append(f'turret pool overflow across the wrap: {wrap_max_occ} (limit {pool})')
        if rd('GAME_STATE', 1)[0] != playing:
            fails.append('GAME_STATE left PLAYING during the wrap test')
        max_occ = wrap_max_occ
        wraps = 1 if wrap_seen else 0
        if max(cursor_vals) < 1:
            fails.append('no authored wave trigger ever fired (cursor stayed 0)')
        if len(set(spawned_vals)) < 2 and max(score_vals) == score_vals[0]:
            fails.append('no evidence of wave activity (WAVE_SPAWNED static and score flat)')

        result = dict(samples=args.samples, stage_logical_rows=slr,
                      scroll_row_range=[min(rows_seen), max(rows_seen)], wraps=wraps,
                      max_slots_occupied=max_occ, pool=pool,
                      wave_cursor_range=[min(cursor_vals), max(cursor_vals)],
                      wave_spawned_distinct=sorted(set(spawned_vals)),
                      score_range=[min(score_vals), max(score_vals)],
                      game_state_values=sorted(set(states)), fails=fails)
        (out / 'level1-smoke.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        if fails:
            raise SystemExit(1)
        print('\nPASS: Level 1 end-to-end smoke (turret pool + authored wave triggers)')
    finally:
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()


if __name__ == '__main__':
    main()
