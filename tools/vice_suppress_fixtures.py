#!/usr/bin/env python3
"""Deterministic fixtures for presentation-only hostile-projectile suppression.

Loads build/shooter.prg in a fresh warp VICE with display/IRQs off, seeds the
logical object arrays + BUILD plan state, calls the real BUILD chain
(buildSortedObjectList .. buildBatchSpriteSchedule .. planCoarseBulletSuppression)
via a SEI;JSR;JMP trampoline, and checks the outcome. Fixtures A-J from the task.
"""
import argparse, json, re, socket, subprocess, time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

CLK = re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')
TYPE_PLAYER, TYPE_ENEMY, TYPE_BULLET = 1, 2, 3


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6601)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--out', type=Path, default=Path('build/scroll-hitch/suppress-fixtures.json'))
    a = ap.parse_args()
    s = symbols(Path(a.symbols))
    with socket.socket() as c:
        assert c.connect_ex(('127.0.0.1', a.port)) != 0, 'port occupied'
    proc = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
        '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{a.port}',
        '-autostartprgmode', '1', '-autostart', str(Path(a.prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    m = Monitor(a.port)
    results = {}
    try:
        m.cmd('delete'); m.cmd('resourceset "JoyPort2Device" "37"')
        m.cmd(f'break {s["waitFireRelease"]:04x}')
        m.cmd('jpdb 1 ef'); m.cmd('x'); m.cmd('jpdb 1 ff'); m.cmd('delete')
        # a few frames of real gameplay so plan bases / masks are sane, then freeze
        m.cmd(f'break {s["applyFineScroll"]:04x}')
        for _ in range(30):
            m.cmd('x')
        m.cmd('delete')
        m.cmd('> d01a 00'); m.cmd('> d015 00'); m.cmd('> d011 00'); m.cmd('> dc0d 7f'); m.cmd('m dc0d dc0d')

        def put(name, data, index=0):
            if isinstance(data, int):
                data = [data]
            addr = (s[name] if isinstance(name, str) else name) + index
            for o in range(0, len(data), 64):
                m.cmd(f'> {addr + o:04x} ' + ' '.join(f'{b & 255:02x}' for b in data[o:o + 64]))

        def get(name, n=1, index=0):
            addr = (s[name] if isinstance(name, str) else name) + index
            f = Path('/tmp/vsf_read.bin')
            m.cmd(f'bsave "{f}" 0 {addr:04x} {addr + n - 1:04x}')
            return f.read_bytes()

        def word(name):
            b = get(name, 2); return b[0] + 256 * b[1]

        # Trampoline at $7d00; landing pad BRK-equivalent breakpoint at $7d80.
        m.cmd('break 7d80')
        m.cmd('> 7d80 ea ea')
        def call_seq(names, x=0):
            code = [0x78, 0xa2, x & 255]                 # SEI ; LDX #x
            for nm in names:
                a2 = s[nm]
                code += [0x20, a2 & 255, a2 >> 8]        # JSR nm
            code += [0x08, 0x68, 0x8d, 0x00, 0x7e]       # PHP ; PLA ; STA $7e00  (final flags)
            code += [0x4c, 0x80, 0x7d]                   # JMP $7d80
            put(0x7d00, code)
            m.cmd('r pc=7d00, sp=ff')
            m.cmd('x')

        def call_chain(with_suppress=True):
            names = ['buildSortedObjectList', 'sortObjectsByY', 'buildInitialSpriteSnapshot',
                     'buildBatchSpriteSchedule']
            if with_suppress:
                names.append('planCoarseBulletSuppression')
            call_seq(names)

        def call1(name, x=0):
            call_seq([name], x=x)

        def last_carry():
            return get(0x7e00)[0] & 1 == 1

        def seed(objs, pending=1, player=(160, 150)):
            # objs: list of (id, type, x, y) for ids 1..15. Player is object 0 and
            # is always active/in-band (as in real gameplay).
            put('OBJECT_ACTIVE', [1] + [0] * 15)
            put('OBJECT_DEATH_TIMER', [0] * 16)
            put('OBJECT_HIT_TIMER', [0] * 16)
            put('OBJECT_X', [player[0]] + [0] * 15)
            put('OBJECT_X_MSB', [0] * 16)
            put('OBJECT_Y', [player[1]] + [0] * 15)
            put('OBJECT_TYPE', [TYPE_PLAYER] + [0] * 15)
            put('OBJECT_SPRITE', [s['blankSprite'] // 64] * 16)
            put('OBJECT_COLOUR', [1] * 16)
            put('ENEMY_BULLET_COUNT', sum(1 for o in objs if o[1] == TYPE_BULLET))
            for (oid, ty, x, y) in objs:
                put('OBJECT_ACTIVE', 1, oid)
                put('OBJECT_TYPE', ty, oid)
                put('OBJECT_X', x & 255, oid)
                put('OBJECT_X_MSB', x >> 8, oid)
                put('OBJECT_Y', y, oid)
            put('PLAYER_STATE', 0)
            put('BG_COARSE_PENDING', pending)

        def snap():
            return dict(
                total=word('SUPPRESS_TOTAL'), resolved=word('SUPPRESS_RESOLVED'),
                unresolved=word('SUPPRESS_UNRESOLVED'), no_eligible=word('SUPPRESS_NO_ELIGIBLE'),
                defer_after=word('SUPPRESS_DEFER_AFTER'), returned=word('SUPPRESS_RETURNED'),
                last_id=get('SUPPRESS_LAST_ID')[0], last_y=get('SUPPRESS_LAST_Y')[0],
                consec=get('SUPPRESS_CONSEC')[0], consec_max=get('SUPPRESS_CONSEC_MAX')[0],
                sorted_count=get('SORTED_COUNT')[0],
                build=get('BUILD_PLAN')[0], live=get('LIVE_PLAN')[0])

        def batch_info():
            build = get('BUILD_PLAN')[0]
            bc = get('BATCH_COUNT', 16)[build]
            rasters = [get('BATCH_RASTER', 16)[build + i] for i in range(bc)]
            return bc, rasters

        def run_fixture(name, objs, pending=1, expect_suppress=None):
            pre = snap()
            seed(objs, pending=pending)
            call_chain(with_suppress=True)
            post = snap()
            bc, rasters = batch_info()
            d_total = (post['total'] - pre['total']) & 0xffff
            d_res = (post['resolved'] - pre['resolved']) & 0xffff
            d_unres = (post['unresolved'] - pre['unresolved']) & 0xffff
            d_ne = (post['no_eligible'] - pre['no_eligible']) & 0xffff
            # logical integrity of every bullet
            act = get('OBJECT_ACTIVE', 16); ty = get('OBJECT_TYPE', 16)
            bullets_ok = all(act[oid] == 1 and ty[oid] == TYPE_BULLET
                             for (oid, t, _x, _y) in objs if t == TYPE_BULLET)
            ebc = get('ENEMY_BULLET_COUNT')[0]
            row = dict(fixture=name, suppress_total_delta=d_total, resolved_delta=d_res,
                       unresolved_delta=d_unres, no_eligible_delta=d_ne,
                       sorted_count=post['sorted_count'], batch_count=bc, batch_rasters=rasters,
                       last_id=post['last_id'], last_y=post['last_y'],
                       bullets_still_active_and_typed=bullets_ok,
                       enemy_bullet_count=ebc)
            if expect_suppress is not None:
                row['PASS'] = (bool(d_total) == expect_suppress)
            results[name] = row
            return row

        # player + N enemies climbing in Y; helpers keep "N sprites" meaning
        # player included (as in real gameplay).
        def enemies(n, y0=80, dy=5):
            return [(i, TYPE_ENEMY, 90 + i * 8, y0 + i * dy) for i in range(1, n + 1)]

        # ---- A: 8 sprites (player + 7 enemies) -> no batch, no suppression ----
        run_fixture('A_eight_sprites', enemies(7), expect_suppress=False)

        # ---- B: 9 sprites, 9th is a HIGH bullet -> legal early batch, no suppression ----
        B = enemies(7) + [(8, TYPE_BULLET, 150, 120)]
        run_fixture('B_nine_legal_early', B, expect_suppress=False)

        # ---- C: 9 sprites, 9th = LOW hostile projectile -> exactly one suppression ----
        C = enemies(7) + [(8, TYPE_BULLET, 150, 236)]
        run_fixture('C_low_bullet_suppressed', C, expect_suppress=True)

        # ---- D: 9th (lowest) object is the PLAYER -> never suppressed, deferral stands ----
        pre = snap(); seed(enemies(8, y0=80, dy=4), pending=1, player=(150, 238))
        call_chain(True); post = snap(); bc, rasters = batch_info()
        results['D_player_late_not_suppressed'] = dict(
            fixture='D', suppress_total_delta=(post['total'] - pre['total']) & 0xffff,
            no_eligible_delta=(post['no_eligible'] - pre['no_eligible']) & 0xffff,
            sorted_count=post['sorted_count'], batch_count=bc, batch_rasters=rasters,
            PASS=(((post['total'] - pre['total']) & 0xffff) == 0
                  and ((post['no_eligible'] - pre['no_eligible']) & 0xffff) == 1))

        # ---- E: 9th (lowest) object is an ENEMY -> not suppressed, deferral stands ----
        E = enemies(7) + [(8, TYPE_ENEMY, 150, 236)]
        row = run_fixture('E_enemy_late_not_suppressed', E, expect_suppress=False)
        row['PASS'] = row['PASS'] and row['no_eligible_delta'] == 1

        # ---- F: two low bullets, only one binding -> suppress exactly one ----
        F = enemies(7) + [(8, TYPE_BULLET, 150, 230), (9, TYPE_BULLET, 170, 244)]
        row = run_fixture('F_two_bullets_one_suppressed', F, expect_suppress=True)
        row['PASS'] = row['PASS'] and row['suppress_total_delta'] == 1

        # ---- G: suppressed bullet overlaps player -> collision still detectable ----
        G = enemies(7) + [(8, TYPE_BULLET, 158, 236)]
        pre = snap(); seed(G, pending=1, player=(158, 232)); call_chain(True); post = snap()
        act = get('OBJECT_ACTIVE', 16); ty = get('OBJECT_TYPE', 16)
        call1('checkBulletPlayerOverlap', x=8)           # C set == projectile box overlaps the player
        carryset = last_carry()
        results['G_suppressed_bullet_still_collides'] = dict(
            fixture='G', suppress_total_delta=(post['total'] - pre['total']) & 0xffff,
            bullet_active=act[8], bullet_type=ty[8], enemy_bullet_count=get('ENEMY_BULLET_COUNT')[0],
            checkBulletPlayerOverlap_carry=carryset,
            PASS=(act[8] == 1 and ty[8] == TYPE_BULLET and carryset is True
                  and ((post['total'] - pre['total']) & 0xffff) == 1))

        # ---- H: suppressed bullet survives -> next presentation renders it ----
        H = enemies(7) + [(8, TYPE_BULLET, 150, 236)]
        seed(H, pending=1); call_chain(True)
        p1 = get('SORTED_COUNT')[0]
        put('OBJECT_Y', 150, 8)                          # next frame: bullet no longer low
        pre = snap(); call_chain(True); post = snap()
        sc2 = get('SORTED_COUNT')[0]
        so = list(get('SORTED_OBJECTS', 16))[:sc2]
        results['H_suppressed_bullet_returns'] = dict(
            fixture='H', first_sorted_count=p1, second_sorted_count=sc2,
            bullet_in_second_sorted_list=(8 in so),
            second_suppress_delta=(post['total'] - pre['total']) & 0xffff,
            PASS=(8 in so and ((post['total'] - pre['total']) & 0xffff) == 0))

        # ---- I: suppressed bullet despawns -> ENEMY_BULLET_COUNT stays correct ----
        I = enemies(7) + [(8, TYPE_BULLET, 150, 236)]
        seed(I, pending=1); call_chain(True)
        ebc_before = get('ENEMY_BULLET_COUNT')[0]
        put('OBJECT_Y', 252, 8)                          # past the despawn edge
        call1('moveEnemyBullet', x=8)
        ebc_after = get('ENEMY_BULLET_COUNT')[0]; act8 = get('OBJECT_ACTIVE', 16)[8]
        results['I_suppressed_bullet_despawns'] = dict(
            fixture='I', ebc_before=ebc_before, ebc_after=ebc_after, bullet_active_after=act8,
            PASS=(ebc_before == 1 and ebc_after == 0 and act8 == 0))

        # ---- J: coarse not pending -> no suppression ----
        J = enemies(7) + [(8, TYPE_BULLET, 150, 236)]
        run_fixture('J_no_coarse_pending', J, pending=0, expect_suppress=False)

    finally:
        m.sock.sendall(b'quit\n'); m.sock.close()
        try: proc.wait(timeout=10)
        except Exception: proc.kill()

    a.out.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    fails = [k for k, v in results.items() if v.get('PASS') is False]
    print('\nFIXTURE PASS/FAIL:')
    for k, v in results.items():
        print(f'  {k}: {"PASS" if v.get("PASS") else "FAIL" if v.get("PASS") is False else "info"}')
    raise SystemExit(1 if fails else 0)


if __name__ == '__main__':
    main()
