#!/usr/bin/env python3
"""Deterministic fixtures for the calmer normal-scrolling encounter budget
(tuning pass: atomic five-enemy waves + turret-pressure Y threshold).

Loads build/shooter.prg in a fresh warp VICE (display/IRQs off), seeds the
logical object arrays + turret runtime state, drives the real policy routines
(updateTurretPressure / refreshShooterBudget / updateEnemyFire / updateSpawner /
startRandomWave / updateBackgroundTurrets) through a SEI;JSR;JMP trampoline.

 A  normal wave: effective WAVE_ENEMY_COUNT == exactly 5
 B  authored 6-enemy attack selected: presented wave contract still == 5
 C  no normal wave produces an effective WAVE_ENEMY_COUNT of 1..4
 D  turret alive+visible Y=100  -> TURRET_PRESSURE_ACTIVE == 1
 E  turret alive+visible Y=179  -> pressure active
 F  turret alive+visible Y=180  -> pressure INACTIVE
 G  turret alive+visible Y=200  -> pressure INACTIVE
 H  turret dead (HP0)   Y=100   -> pressure inactive
 I  turret offscreen (VISIBLE 0) -> pressure inactive
 J  pressure active before a wave starts -> next 5-wave START deferred, nothing
    partially emitted; clears and starts once pressure ends
 K  pressure activates after a 5-wave has begun -> wave completes to 5, no member
    culled or skipped
 L  pressure clears at Y>=180 -> next complete 5-wave becomes eligible to start
 M  five active enemies, normal -> <= 2 distinct mobile shooters
 N  five active enemies, pressure active -> <= 1 distinct mobile shooter
 O  existing hostile projectiles survive pressure-active<->inactive transitions
 P  ENEMY_BULLET_COUNT / real bullet objects never exceed 3
 Q  no encounter-policy call despawns or kills an enemy
 R  turret firing operational BOTH below (Y=150) and above (Y=200) the threshold
"""
import argparse
import json
import socket
import subprocess
import time
from pathlib import Path
from vice_scroll_test import symbols, Monitor

TYPE_PLAYER, TYPE_ENEMY, TYPE_BULLET = 1, 2, 3


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6603)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--out', type=Path,
                    default=Path('build/mc-test/encounter-fixtures.json'))
    a = ap.parse_args()
    s = symbols(Path(a.symbols))
    with socket.socket() as c:
        assert c.connect_ex(('127.0.0.1', a.port)) != 0, 'port occupied'
    proc = subprocess.Popen(
        ['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
         '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{a.port}',
         '-autostartprgmode', '1', '-autostart', str(Path(a.prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    m = Monitor(a.port)
    results = {}
    try:
        m.cmd('delete')
        m.cmd('resourceset "JoyPort2Device" "37"')
        m.cmd(f'break {s["waitFireRelease"]:04x}')
        m.cmd('jpdb 1 ef'); m.cmd('x'); m.cmd('jpdb 1 ff'); m.cmd('delete')
        m.cmd(f'break {s["applyFineScroll"]:04x}')
        for _ in range(20):
            m.cmd('x')
        m.cmd('delete')
        m.cmd('> d01a 00'); m.cmd('> d015 00'); m.cmd('> d011 00'); m.cmd('> dc0d 7f')
        m.cmd('break 7d80'); m.cmd('> 7d80 ea ea')

        def put(name, data, index=0):
            if isinstance(data, int):
                data = [data]
            addr = (s[name] if isinstance(name, str) else name) + index
            for o in range(0, len(data), 64):
                m.cmd(f'> {addr + o:04x} ' +
                      ' '.join(f'{b & 255:02x}' for b in data[o:o + 64]))

        def get(name, n=1, index=0):
            addr = (s[name] if isinstance(name, str) else name) + index
            f = Path('/tmp/vef_read.bin')
            m.cmd(f'bsave "{f}" 0 {addr:04x} {addr + n - 1:04x}')
            return list(f.read_bytes())

        def word(name, index=0):
            b = get(name, 2, index)
            return b[0] + 256 * b[1]

        def call(names, x=0):
            if isinstance(names, str):
                names = [names]
            code = [0x78, 0xa2, x & 255]
            for nm in names:
                addr = s[nm] if isinstance(nm, str) else nm
                code += [0x20, addr & 255, addr >> 8]
            code += [0x08, 0x68, 0x8d, 0x00, 0x7e, 0x4c, 0x80, 0x7d]
            put(0x7d00, code)
            m.cmd('r pc=7d00, sp=ff')
            m.cmd('x')

        TCOUNT = 3
        s_slots = s['ENEMY_ACTIVE_COUNT'] - s['ENEMY_SHOOTER_ID']
        assert s_slots >= 1

        def seed_objects(enemy_ids, bullet_ids=(), y=120):
            put('OBJECT_ACTIVE', [1] + [0] * 15)
            put('OBJECT_TYPE', [TYPE_PLAYER] + [0] * 15)
            put('OBJECT_DEATH_TIMER', [0] * 16)
            put('OBJECT_HIT_TIMER', [0] * 16)
            put('OBJECT_STAGE', [0] * 16)
            put('OBJECT_X', [160] + [40] * 15)
            put('OBJECT_X_MSB', [0] * 16)
            put('OBJECT_Y', [210] + [y] * 15)
            put('OBJECT_SPRITE', [s['blankSprite'] // 64] * 16)
            put('OBJECT_HEALTH', [0] + [1] * 15)
            for i, oid in enumerate(enemy_ids):
                put('OBJECT_ACTIVE', 1, oid)
                put('OBJECT_TYPE', TYPE_ENEMY, oid)
                put('OBJECT_X', 40 + 16 * i, oid)
                put('OBJECT_Y', y, oid)
            for oid in bullet_ids:
                put('OBJECT_ACTIVE', 1, oid)
                put('OBJECT_TYPE', TYPE_BULLET, oid)
            put('ENEMY_BULLET_COUNT', len(bullet_ids))
            put('PLAYER_STATE', 0)
            put('TURRET_PRESSURE_ACTIVE', 0)
            put('ENEMY_SHOOTER_BUDGET', 0)
            put('ENEMY_SHOOTER_ID', [0xff] * s_slots)
            put('WAVE_START_DEFERRED', [0, 0])
            put('ENEMY_SPAWN_DEFERRED', [0, 0])
            put('ENEMY_FIRE_REJECT_NORMAL', [0, 0])
            put('ENEMY_FIRE_REJECT_TURRET', [0, 0])

        def seed_turrets(states):
            # states: (visible, health, y) per turret; y default 100
            def col(idx, default):
                return [st[idx] if len(st) > idx else default for st in states] + \
                       [default] * (TCOUNT - len(states))
            put('TURRET_VISIBLE', col(0, 0))
            put('TURRET_HEALTH', col(1, 0))
            put('TURRET_Y', col(2, 100))

        def enemy_count():
            act = get('OBJECT_ACTIVE', 16)
            typ = get('OBJECT_TYPE', 16)
            return sum(1 for i in range(1, 16)
                       if act[i] and typ[i] == TYPE_ENEMY)

        def drive_fire(rounds=48):
            fired = set()
            maxbul = get('ENEMY_BULLET_COUNT')[0]
            for _ in range(rounds):
                put('ENEMY_FIRE_TIMER', 0)
                before = get('ENEMY_BULLET_COUNT')[0]
                act_before = get('OBJECT_ACTIVE', 16)
                call('updateEnemyFire')
                after = get('ENEMY_BULLET_COUNT')[0]
                maxbul = max(maxbul, after)
                if after > before:
                    fired.add(get('ENEMY_FIRE_SOURCE')[0])
                    act_after = get('OBJECT_ACTIVE', 16)
                    for oid in range(1, 16):
                        if act_after[oid] and not act_before[oid]:
                            put('OBJECT_ACTIVE', 0, oid)
                            put('OBJECT_TYPE', 0, oid)
                    put('ENEMY_BULLET_COUNT', before)
            return fired, maxbul

        def record(key, ok, **info):
            results[key] = {'PASS': bool(ok), **info}

        # ---- A / B / C : wave size is always exactly 5 --------------------
        counts = []
        for _ in range(48):
            call('startRandomWave')
            counts.append(get('WAVE_ENEMY_COUNT')[0])
        raw = get('attackEnemyCount', 12)
        record('A_normal_wave_is_5', set(counts) == {5}, observed=sorted(set(counts)))
        record('B_authored6_presented_as_5',
               max(raw) >= 6 and set(counts) == {5},
               attackEnemyCount_table=raw, observed=sorted(set(counts)))
        record('C_no_1_to_4_wave', not (set(counts) & {1, 2, 3, 4}),
               observed=sorted(set(counts)))

        # ---- D..I : turret-pressure Y threshold -------------------------
        def pressure_for(vis, hp, y):
            seed_objects([1, 2])
            seed_turrets([(vis, hp, y), (0, 3, 100), (0, 3, 100)])
            call('updateTurretPressure')
            return get('TURRET_PRESSURE_ACTIVE')[0]

        record('D_turret_Y100_pressure',  pressure_for(1, 3, 100) == 1, y=100)
        record('E_turret_Y179_pressure',  pressure_for(1, 3, 179) == 1, y=179)
        record('F_turret_Y180_no_pressure', pressure_for(1, 3, 180) == 0, y=180)
        record('G_turret_Y200_no_pressure', pressure_for(1, 3, 200) == 0, y=200)
        record('H_turret_dead_no_pressure',  pressure_for(1, 0, 100) == 0)
        record('I_turret_offscreen_no_pressure', pressure_for(0, 3, 100) == 0)

        # ---- J : pressure active BEFORE a wave starts -> START deferred --
        seed_objects([1, 2])
        seed_turrets([(1, 3, 120), (0, 3, 100), (0, 3, 100)])
        call('updateTurretPressure')
        put('WAVE_ENEMY_COUNT', 5)
        put('WAVE_SPAWNED', 5)          # wave complete -> director wants to start the next
        put('WAVE_GAP_TIMER', 0)
        put('SPAWN_TIMER', 0)
        wsd0 = word('WAVE_START_DEFERRED')
        ec0 = enemy_count()
        for _ in range(12):
            call('updateSpawner')
        held = (enemy_count() == ec0
                and get('WAVE_SPAWNED')[0] == 5          # startRandomWave never ran (would zero this)
                and word('WAVE_START_DEFERRED') > wsd0
                and word('ENEMY_SPAWN_DEFERRED') == 0)   # no per-member dribble
        # now pressure clears -> the next wave may start
        seed_turrets([(1, 3, 190), (0, 3, 100), (0, 3, 100)])   # Y>=180
        call('updateTurretPressure')
        put('SPAWN_TIMER', 0); put('WAVE_GAP_TIMER', 0); put('WAVE_SPAWN_INTERVAL', 0)
        call('updateSpawner')
        started = (get('WAVE_SPAWNED')[0] >= 1 and get('WAVE_ENEMY_COUNT')[0] == 5
                   and enemy_count() >= ec0 + 1)
        record('J_wave_start_deferred_then_starts', held and started,
               held=held, started=started,
               wave_start_deferred_delta=word('WAVE_START_DEFERRED') - wsd0)
        record('L_pressure_clear_wave_eligible', started, started=started)

        # ---- K : pressure activates mid-wave -> wave completes to 5 -----
        seed_objects([1, 2])                      # 2 members already spawned; slots 3..15 free
        seed_turrets([(0, 3, 100), (0, 3, 100), (0, 3, 100)])
        call('updateTurretPressure')             # inactive
        put('WAVE_ENEMY_COUNT', 5)
        put('WAVE_SPAWNED', 2)
        put('WAVE_GAP_TIMER', 0)
        put('WAVE_SPAWN_INTERVAL', 0)
        put('WAVE_ADD_X_VALUE', 0); put('WAVE_ADD_Y_VALUE', 0)
        put('SPAWN_TIMER', 0)
        seed_turrets([(1, 3, 120), (0, 3, 100), (0, 3, 100)])   # pressure enters NOW
        call('updateTurretPressure')
        ec_before = enemy_count()
        min_seen = ec_before
        for _ in range(30):
            put('SPAWN_TIMER', 0)
            call('updateSpawner')
            min_seen = min(min_seen, enemy_count())
            if get('WAVE_SPAWNED')[0] >= 5:
                break
        ws = get('WAVE_SPAWNED')[0]
        ec_after = enemy_count()
        record('K_inprogress_wave_completes',
               ws == 5 and ec_after == ec_before + 3 and min_seen >= ec_before,
               wave_spawned=ws, enemies_before=ec_before, enemies_after=ec_after,
               min_enemies_during=min_seen)

        # ---- M : 5 enemies, normal -> <=2 distinct shooters -------------
        seed_objects([1, 2, 3, 4, 5])
        seed_turrets([(0, 3, 100), (0, 3, 100), (0, 3, 100)])
        call('updateTurretPressure')
        fired, maxbul = drive_fire(64)
        record('M_normal_5_shooters', len(fired) <= 2 and maxbul <= 3,
               distinct_shooters=sorted(fired), max_bullets=maxbul)

        # ---- N : 5 enemies, pressure active -> <=1 distinct shooter -----
        seed_objects([1, 2, 3, 4, 5])
        seed_turrets([(1, 3, 150), (0, 3, 100), (0, 3, 100)])
        call('updateTurretPressure')
        pa = get('TURRET_PRESSURE_ACTIVE')[0]
        fired, maxbul = drive_fire(64)
        record('N_pressure_5_shooters',
               pa == 1 and len(fired) <= 1 and maxbul <= 3,
               pressure_active=pa, distinct_shooters=sorted(fired), max_bullets=maxbul)

        # ---- O : bullets survive pressure transitions ------------------
        seed_objects([1, 2], bullet_ids=[8, 9, 10])
        bc0 = get('ENEMY_BULLET_COUNT')[0]
        act0 = get('OBJECT_ACTIVE', 16)
        for y in (150, 190, 150, 250):
            seed_turrets([(1, 3, y), (0, 3, 100), (0, 3, 100)])
            call(['updateTurretPressure', 'refreshShooterBudget'])
        record('O_bullets_survive',
               get('ENEMY_BULLET_COUNT')[0] == bc0
               and get('OBJECT_ACTIVE', 16) == act0
               and all(get('OBJECT_ACTIVE', 16)[i] for i in (8, 9, 10)),
               bullet_count_before=bc0, bullet_count_after=get('ENEMY_BULLET_COUNT')[0])

        # ---- P : bullet cap ------------------------------------------
        seed_objects([1, 2, 3, 4, 5])
        seed_turrets([(0, 3, 100), (0, 3, 100), (0, 3, 100)])
        call('updateTurretPressure')
        worst = 0
        for _ in range(80):
            put('ENEMY_FIRE_TIMER', 0)
            call('updateEnemyFire')
            act = get('OBJECT_ACTIVE', 16); typ = get('OBJECT_TYPE', 16)
            worst = max(worst, get('ENEMY_BULLET_COUNT')[0],
                        sum(1 for i in range(1, 16) if act[i] and typ[i] == TYPE_BULLET))
        record('P_bullet_cap', worst <= 3, worst_hostile_bullets=worst)

        # ---- Q : no policy call despawns / kills an enemy --------------
        seed_objects([1, 2, 3])
        seed_turrets([(1, 3, 120), (0, 3, 100), (0, 3, 100)])
        base = get('OBJECT_ACTIVE', 16)
        ok = True
        for seq in (['updateTurretPressure'], ['refreshShooterBudget'],
                    ['updateTurretPressure', 'refreshShooterBudget'],
                    ['updateEnemyFire'], ['countActiveEnemies']):
            put('ENEMY_FIRE_TIMER', 0)
            call(seq)
            now = get('OBJECT_ACTIVE', 16)
            # every enemy that was active is still active
            if any(base[i] and not now[i] for i in (1, 2, 3)):
                ok = False
        record('Q_no_despawn', ok)

        # ---- R : turret fires both below and above the Y threshold -----
        def turret_fires(y):
            seed_objects([1, 2])
            put('OBJECT_Y', 240, 0)              # player low: turret fires downward freely
            seed_turrets([(1, 3, y), (0, 3, 100), (0, 3, 100)])
            put('TURRET_FIRE_TIMER', [0, 200, 200])
            put('TURRET_HIT_TIMER', [0, 0, 0])
            put('TURRET_AIM', [4, 4, 4])
            put('SORTED_COUNT', 0)
            put('ENEMY_BULLET_COUNT', 0)
            put('TURRET_SHOTS_FIRED', 0)
            put('PLAYER_STATE', 0)
            call('updateTurretPressure')
            call('updateBackgroundTurrets')
            return get('TURRET_SHOTS_FIRED')[0]

        below = turret_fires(150)
        above = turret_fires(200)
        record('R_turret_fires_below_and_above',
               below >= 1 and above >= 1, shots_below_thresh=below,
               shots_above_thresh=above)

    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2))
        fails = [k for k, v in results.items() if not v['PASS']]
        print('\nFIXTURE PASS/FAIL:')
        for k, v in results.items():
            print(f'  {k}: {"PASS" if v["PASS"] else "FAIL"}')
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()
    raise SystemExit(1 if (not results or any(
        not v['PASS'] for v in results.values())) else 0)


if __name__ == '__main__':
    main()
