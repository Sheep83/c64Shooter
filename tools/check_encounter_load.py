#!/usr/bin/env python3
"""Summarise the gameplay/presentation load of a vice_scroll_test capture dir.

Reads the per-frame $2000-$23ff (.state) and $2920-$2fff (.bg) dumps plus the
register lines and reports the metrics the calmer-encounter-budget task asks
for. Works on captures from any build; policy counters are only shown when the
symbols exist.
"""
import json
import re
import sys
from pathlib import Path
from collections import Counter

TYPE_ENEMY, TYPE_BULLET = 2, 3


def main():
    root = Path(sys.argv[1])
    sym = json.loads((root / 'symbols.json').read_text())
    records = json.loads((root / 'frames.json').read_text())

    def has(n):
        return n in sym

    def region(state, bg, addr, n=1):
        if addr < 0x2400:
            return state[addr - 0x2000: addr - 0x2000 + n]
        return bg[addr - 0x2920: addr - 0x2920 + n]

    clk = re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')
    max_enemies = max_bullets = max_sorted = max_active = 0
    max_shooters = 0
    wave_counts = set()
    deferred_last = None
    defer_events = 0
    cur_run = longest_run = 0
    clocks = []
    turret_active_frames = 0
    for rec in records:
        f = rec['frame']
        state = (root / f'{f:05d}.state').read_bytes()
        bg = (root / f'{f:05d}.bg').read_bytes()
        act = region(state, bg, sym['OBJECT_ACTIVE'], 16)
        typ = region(state, bg, sym['OBJECT_TYPE'], 16)
        dth = region(state, bg, sym['OBJECT_DEATH_TIMER'], 16)
        enemies = sum(1 for i in range(1, 16)
                      if act[i] and typ[i] == TYPE_ENEMY and not dth[i])
        bullets = sum(1 for i in range(1, 16) if act[i] and typ[i] == TYPE_BULLET)
        max_enemies = max(max_enemies, enemies)
        max_bullets = max(max_bullets, bullets)
        max_active = max(max_active, sum(act))
        sc = region(state, bg, sym['SORTED_COUNT'])[0]
        max_sorted = max(max_sorted, sc)
        if has('WAVE_ENEMY_COUNT'):
            wc = region(state, bg, sym['WAVE_ENEMY_COUNT'])[0]
            if wc:
                wave_counts.add(wc)
        d = region(state, bg, sym['BG_COARSE_DEFERRED'])[0]
        if deferred_last is not None:
            step = (d - deferred_last) & 0xff
            if step:
                defer_events += step
                cur_run += 1
                longest_run = max(longest_run, cur_run)
            else:
                cur_run = 0
        deferred_last = d
        if has('ENEMY_SHOOTER_ID'):
            ids = region(state, bg, sym['ENEMY_SHOOTER_ID'],
                         sym['ENEMY_ACTIVE_COUNT'] - sym['ENEMY_SHOOTER_ID'])
            max_shooters = max(max_shooters, sum(1 for v in ids if v != 0xff))
        if has('TURRET_PRESSURE_ACTIVE') and \
                region(state, bg, sym['TURRET_PRESSURE_ACTIVE'])[0]:
            turret_active_frames += 1
        mm = clk.search(rec['registers'])
        clocks.append(int(mm[3]) - int(mm[1]) * 63 - int(mm[2]))

    deltas = sorted(set(b - a for a, b in zip(clocks, clocks[1:])))

    last_state = (root / f"{records[-1]['frame']:05d}.state").read_bytes()
    last_bg = (root / f"{records[-1]['frame']:05d}.bg").read_bytes()

    def w(name):
        b = region(last_state, last_bg, sym[name], 2)
        return b[0] + 256 * b[1]

    out = {
        'frames': len(records),
        'frame_cycle_deltas': deltas,
        'authored_wave_sizes_observed (WAVE_ENEMY_COUNT)': sorted(wave_counts),
        'min_authored_wave_size': min(wave_counts) if wave_counts else None,
        'max_authored_wave_size': max(wave_counts) if wave_counts else None,
        'max_active_objects': max_active,
        'max_active_enemies': max_enemies,
        'max_active_hostile_bullets': max_bullets,
        'max_sorted_count': max_sorted,
        'coarse_deferral_events': defer_events,
        'longest_consecutive_deferral_run': longest_run,
    }
    for label, name in [('suppress_total', 'SUPPRESS_TOTAL'),
                        ('suppress_resolved', 'SUPPRESS_RESOLVED'),
                        ('suppress_unresolved', 'SUPPRESS_UNRESOLVED'),
                        ('turret_pressure_frames_counter', 'POLICY_TURRET_FRAMES'),
                        ('wave_start_deferred', 'WAVE_START_DEFERRED'),
                        ('enemy_member_spawn_deferred', 'ENEMY_SPAWN_DEFERRED'),
                        ('enemy_fire_reject_normal', 'ENEMY_FIRE_REJECT_NORMAL'),
                        ('enemy_fire_reject_turret', 'ENEMY_FIRE_REJECT_TURRET')]:
        if has(name):
            out[label] = w(name)
    if has('POLICY_MAX_BULLETS'):
        # Engine gauges maintained per-frame by updateTurretPressure's diag tail.
        # (POLICY_MAX_ENEMIES is only updated when countActiveEnemies is called,
        #  which the tuned policy no longer does in the frame path -> omitted.)
        out['policy_max_bullets_gauge'] = region(last_state, last_bg, sym['POLICY_MAX_BULLETS'])[0]
        out['policy_max_sorted_gauge'] = region(last_state, last_bg, sym['POLICY_MAX_SORTED'])[0]
    out['turret_pressure_frames_observed'] = turret_active_frames
    if has('ENEMY_SHOOTER_ID'):
        out['max_designated_shooters'] = max_shooters
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
