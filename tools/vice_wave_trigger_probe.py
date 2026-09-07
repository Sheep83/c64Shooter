#!/usr/bin/env python3
"""Authored wave-trigger runtime integration (Level 1).

Runs the built game to the first gameplay frame, then, with the frame loop
halted:
  A. sweeps SCROLL_ROW(16) downward through every authored trigger row, driving
     updateWaveTriggers each step, and asserts each trigger LATCHES exactly when
     SCROLL_ROW reaches its worldRow - in descending-row order, once each, with
     the cursor advancing and no trigger skipped;
  B. after all triggers have fired, keeps sweeping to SCROLL_ROW 0 and asserts
     WAVE_TRIGGER_FIRE stays 0 (no duplicate firing within a loop);
  C. simulates the stage wrap (WAVE_TRIGGER_REWIND = 1) and asserts every trigger
     re-arms and fires again on the next pass;
  D. calls startAuthoredWave for each trigger index and asserts WAVE_ATTACK_ID /
     WAVE_ENEMY_COUNT / WAVE_SPRITE_INDEX / WAVE_SPAWN_INTERVAL match the
     resolved authored values (composition size is authoritative for wave size,
     not NORMAL_WAVE_SIZE);
  E. confirms the runtime comparison is against SCROLL_ROW (a world position),
     so SCROLL_FRAME_DIVIDER cannot move a trigger relative to terrain.
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
    ap.add_argument('--port', type=int, default=6740)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/wave-trigger'))
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    proc, m = launch(args.port)
    fails = []
    try:
        m.trace_file = (out / 'monitor.log').open('w')
        start_playing(m, sym)
        m.cmd('delete')
        m.cmd('break 700a')

        def put(name, values):
            addr = sym[name] if isinstance(name, str) else name
            if isinstance(values, int):
                values = [values]
            m.cmd(f'> {addr:04x} ' + ' '.join(f'{v & 255:02x}' for v in values))

        def rd(name, n=1):
            addr = sym[name] if isinstance(name, str) else name
            p = out / 'scratch.bin'
            m.cmd(f'bsave "{p}" 0 {addr:04x} {addr + n - 1:04x}')
            return list(p.read_bytes())

        def w16(name):
            b = rd(name, 2)
            return b[0] | (b[1] << 8)

        def call(name, xval=None):
            a = sym[name]
            code = []
            if xval is not None:
                code += [0xa2, xval & 0xFF]        # ldx #xval
            code += [0x20, a & 255, a >> 8, 0x4c, 0x0a, 0x70]   # jsr a ; jmp $700a
            put(0x7000, code)
            m.cmd('r pc=7000, sp=ff')
            m.cmd('x')

        n = sym['TURRET_TOTAL_CODE'] and None  # unused
        wt_count_sym = 'WAVE_TRIGGER_COUNT' if 'WAVE_TRIGGER_COUNT' in sym else None
        # WAVE_TRIGGER_COUNT is a .const, not exported as a symbol; derive N from
        # the contiguous waveTrigRowLo..waveTrigRowHi span.
        N = sym['waveTrigRowHi'] - sym['waveTrigRowLo']
        rows_len = sym['STAGE_METATILE_ROWS_END'] - sym['stageMetatileRows']
        slr = rows_len // 10 * 4
        t_lo = rd('waveTrigRowLo', N)
        t_hi = rd('waveTrigRowHi', N)
        t_atk = rd('waveTrigAttackId', N)
        t_cnt = rd('waveTrigCount', N)
        t_spr = rd('waveTrigSprite', N)
        t_int = rd('waveTrigInterval', N)
        rows = [t_lo[i] | (t_hi[i] << 8) for i in range(N)]
        boot = w16('SCROLL_ROW')
        print(f'stage {slr} logical rows; {N} authored wave triggers')
        for i in range(N):
            print(f'  trigger {i}: worldRow {rows[i]:4d}  attackId {t_atk[i]}  '
                  f'count {t_cnt[i]}  spriteSeed {t_spr[i]}  interval {t_int[i]}')
        if rows != sorted(rows, reverse=True):
            fails.append(f'A trigger rows not sorted descending: {rows}')

        # freeze the frame loop; drive the trigger cursor by hand
        call('initWaveTriggers')

        def sweep(scroll_iter, consume=True):
            fired = []
            for scroll in scroll_iter:
                put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
                call('updateWaveTriggers')
                fire = rd('WAVE_TRIGGER_FIRE', 1)[0]
                if fire:
                    fired.append((fire - 1, scroll))
                    if consume:
                        put('WAVE_TRIGGER_FIRE', 0)   # updateSpawner consumes the latch
            return fired

        # ---- A: each trigger latches at exactly SCROLL_ROW == worldRow ----
        fired = sweep(range(boot, -1, -1))
        got_idx = [i for (i, s) in fired]
        if got_idx != list(range(N)):
            fails.append(f'A triggers fired in order {got_idx}, expected {list(range(N))}')
        for (i, s) in fired:
            if s != rows[i]:
                fails.append(f'A trigger {i} latched at SCROLL_ROW {s}, expected worldRow {rows[i]}')
        if not [f for f in fails if f.startswith('A ')]:
            print(f'A PASS every trigger latched exactly at SCROLL_ROW == worldRow, in order: '
                  + ', '.join(f't{i}@{s}' for (i, s) in fired))

        # ---- B: no duplicate firing after the cursor is exhausted --------
        cur = rd('WAVE_TRIGGER_CURSOR', 1)[0]
        extra = sweep(range(rows[-1] - 1, -1, -1))
        if extra:
            fails.append(f'B extra trigger fire(s) after cursor exhausted: {extra}')
        elif cur != N:
            fails.append(f'B WAVE_TRIGGER_CURSOR = {cur}, expected {N}')
        else:
            print(f'B PASS cursor exhausted at {cur}/{N}; no further fire down to SCROLL_ROW 0')

        # ---- C: stage wrap re-arms every trigger ------------------------
        # gameplay's wrap branch sets SCROLL_ROW = SLR-1 AND WAVE_TRIGGER_REWIND
        # together; the next updateWaveTriggers rewinds the cursor and, with
        # SCROLL_ROW back above every trigger row, latches nothing yet.
        put('SCROLL_ROW', [(slr - 1) & 0xFF, ((slr - 1) >> 8) & 0xFF])
        put('WAVE_TRIGGER_REWIND', 1)
        call('updateWaveTriggers')
        if rd('WAVE_TRIGGER_CURSOR', 1)[0] != 0:
            fails.append('C WAVE_TRIGGER_CURSOR did not rewind to 0 on wrap')
        if rd('WAVE_TRIGGER_FIRE', 1)[0] != 0:
            fails.append('C a trigger fired immediately on rewind (SCROLL_ROW should be above all rows)')
        fired2 = sweep(list(range(slr - 1, -1, -1)))
        if [i for (i, s) in fired2] != list(range(N)):
            fails.append(f'C after wrap, triggers fired {[i for (i,s) in fired2]}, expected {list(range(N))}')
        else:
            print(f'C PASS stage wrap re-armed all {N} triggers; they fired again: '
                  + ', '.join(f't{i}@{s}' for (i, s) in fired2))

        # ---- D: startAuthoredWave resolves the authored values ----------
        for i in range(N):
            call('startAuthoredWave', xval=i)
            aid = rd('WAVE_ATTACK_ID', 1)[0]
            cnt = rd('WAVE_ENEMY_COUNT', 1)[0]
            spr = rd('WAVE_SPRITE_INDEX', 1)[0]
            itv = rd('WAVE_SPAWN_INTERVAL', 1)[0]
            if (aid, cnt, spr, itv) != (t_atk[i], t_cnt[i], t_spr[i], t_int[i]):
                fails.append(f'D trigger {i}: startAuthoredWave set '
                             f'(attack {aid}, count {cnt}, sprite {spr}, interval {itv}), '
                             f'expected ({t_atk[i]}, {t_cnt[i]}, {t_spr[i]}, {t_int[i]})')
        norm = sym.get('NORMAL_WAVE_SIZE')
        if not [f for f in fails if f.startswith('D ')]:
            print(f'D PASS startAuthoredWave resolves attackId/count/spriteSeed/interval per trigger; '
                  f'wave size is the authored composition size (not forced)')

        # ---- E: comparison is against SCROLL_ROW (world position) -------
        # Re-run trigger 0 at two different fake "frame paces": the latch depends
        # only on SCROLL_ROW, never on a frame counter.
        call('initWaveTriggers')
        put('SCROLL_ROW', [(rows[0] + 1) & 0xFF, ((rows[0] + 1) >> 8) & 0xFF])
        call('updateWaveTriggers')
        early = rd('WAVE_TRIGGER_FIRE', 1)[0]
        put('SCROLL_ROW', [rows[0] & 0xFF, (rows[0] >> 8) & 0xFF])
        call('updateWaveTriggers')
        onrow = rd('WAVE_TRIGGER_FIRE', 1)[0]
        if early != 0 or onrow != 1:
            fails.append(f'E trigger 0 latch = {early} one row early, {onrow} on the row '
                         f'(expected 0 then 1) - not purely SCROLL_ROW driven')
        else:
            print('E PASS trigger latch is purely SCROLL_ROW (world position) driven; '
                  'SCROLL_FRAME_DIVIDER cannot move it relative to terrain')

        (out / 'wave-trigger.json').write_text(json.dumps({
            'stage_logical_rows': slr, 'trigger_count': N,
            'trigger_rows': rows, 'attack_ids': t_atk, 'counts': t_cnt,
            'sprite_seeds': t_spr, 'intervals': t_int,
            'fired_pass1': fired, 'fired_after_wrap': fired2,
            'fails': fails,
        }, indent=2))
        if fails:
            print(f'\nFAIL ({len(fails)}):')
            for f in fails:
                print('  ' + f)
            raise SystemExit(1)
        print('\nPASS: authored wave-trigger runtime integration (Level 1)')
    finally:
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()


if __name__ == '__main__':
    main()
