#!/usr/bin/env python3
"""Collision semantics with three overlapping player sprites.

Three co-located hardware sprites set each OTHER's bits in $D01E every frame, so
the `lda $D01E / and PLAYER_HW_MASK` fast-path GATE in capturePlayerCollision is
permanently open. This measures whether that is merely a lost optimisation or an
actual correctness break.

Tests:
  A  isolated player, no other objects, many frames -> must NEVER take a hit
  B  isolated player, invulnerable window / respawn unaffected
  C  real enemy overlapping the player -> MUST still register a hit
  D  real enemy NOT overlapping -> must not
  E  real TYPE_ENEMY_BULLET overlapping -> MUST still register a hit
  F  gate-open rate: how often $D01E & PLAYER_HW_MASK is non-zero
  G  one hit produces exactly ONE life lost (no triple damage from 3 layers)
"""
import argparse, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6830)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--label', default='build')
    a = ap.parse_args()
    sym = symbols(Path(a.symbols).resolve())
    proc = subprocess.Popen(
        [X64SC, '-default', '-pal', '-warp', '+sound', '-remotemonitor',
         '-remotemonitoraddress', f'ip4://127.0.0.1:{a.port}',
         '-autostartprgmode', '1', '-autostart', str(Path(a.prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    mon = Monitor(a.port)
    res = {}
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

        def poke(addr, *v):
            mon.cmd(f'> {addr:04x} ' + ' '.join(f'{x:02x}' for x in v))

        def clear_pool():
            for i in range(1, 16):
                poke(sym['OBJECT_ACTIVE'] + i, 0)
                poke(sym['OBJECT_DEATH_TIMER'] + i, 0)
            poke(sym['ENEMY_BULLET_COUNT'], 0)

        def spawn(idx, typ, x, y):
            poke(sym['OBJECT_ACTIVE'] + idx, 1)
            poke(sym['OBJECT_TYPE'] + idx, typ)
            poke(sym['OBJECT_X'] + idx, x)
            poke(sym['OBJECT_X_MSB'] + idx, 0)
            poke(sym['OBJECT_Y'] + idx, y)
            poke(sym['OBJECT_VEL_X'] + idx, 0)
            poke(sym['OBJECT_VEL_Y'] + idx, 0)
            poke(sym['OBJECT_PATH_TIMER'] + idx, 255)
            poke(sym['OBJECT_DEATH_TIMER'] + idx, 0)
            poke(sym['OBJECT_HIT_TIMER'] + idx, 0)

        for _ in range(300):
            step()
            if g('GAME_STATE') == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if g('GAME_STATE') == 1:
                break
        poke(sym['PLAYER_LIVES'], 200)
        step(60)

        # ---- A: isolated player, no other objects -------------------------
        clear_pool(); step(4)
        poke(sym['PLAYER_HIT'], 0)
        hits = 0; gate_open = 0; N = 200
        for _ in range(N):
            step()
            poke(sym['OBJECT_Y'], 200)
            clear_pool()
            if g('PLAYER_HIT'):
                hits += 1
                poke(sym['PLAYER_HIT'], 0)
        lives_after = g('PLAYER_LIVES')
        res['A_isolated_player_false_hits'] = hits
        res['A_player_state'] = g('PLAYER_STATE')
        res['A_lives_still'] = lives_after
        res['A_player_mask'] = f"{g('PLAYER_HW_MASK'):08b}"

        # ---- F: gate-open rate -------------------------------------------
        # Sample $D01E & PLAYER_HW_MASK. NOTE: reading $D01E from the monitor
        # does NOT clear it (VICE monitor reads are side-effect free), so this
        # observes the latch as the game's own read would find it.
        opens = 0; M = 120
        for _ in range(M):
            step()
            poke(sym['OBJECT_Y'], 200)
            clear_pool()
            if peek(0xd01e)[0] & g('PLAYER_HW_MASK'):
                opens += 1
        res['F_gate_open_frames'] = f'{opens}/{M}'

        # ---- C: real enemy overlapping the player -------------------------
        clear_pool(); step(4)
        poke(sym['PLAYER_HIT'], 0)
        px = peek(0xd000)[0]
        lives_before = g('PLAYER_LIVES')
        spawn(1, 2, g('OBJECT_X'), 200)          # TYPE_ENEMY exactly on the player
        poke(sym['OBJECT_Y'], 200)
        saw_hit = 0
        for _ in range(90):
            step()
            if g('PLAYER_HIT') or g('PLAYER_STATE') != 0:
                saw_hit = 1
                break
        res['C_enemy_overlap_hit'] = bool(saw_hit)
        # let the death/respawn cycle complete and count lives lost
        states = set()
        for _ in range(300):
            step()
            states.add(g('PLAYER_STATE'))
            if g('PLAYER_STATE') == 0 and 2 in states:
                break
        res['C_states_seen'] = sorted(states)
        res['G_lives_lost_for_one_hit'] = lives_before - g('PLAYER_LIVES')

        # ---- D: enemy far away -------------------------------------------
        clear_pool(); step(8)
        poke(sym['PLAYER_HIT'], 0)
        poke(sym['OBJECT_Y'], 200)
        spawn(1, 2, 40, 80)                       # nowhere near the player
        false_hits = 0
        for _ in range(120):
            step()
            poke(sym['OBJECT_Y'], 200)
            poke(sym['OBJECT_Y'] + 1, 80)
            poke(sym['OBJECT_ACTIVE'] + 1, 1)
            if g('PLAYER_HIT'):
                false_hits += 1
                poke(sym['PLAYER_HIT'], 0)
        res['D_distant_enemy_false_hits'] = false_hits

        # ---- E: real projectile overlapping -------------------------------
        clear_pool(); step(8)
        poke(sym['PLAYER_HIT'], 0)
        poke(sym['OBJECT_Y'], 200)
        spawn(1, 3, g('OBJECT_X'), 200)           # TYPE_ENEMY_BULLET on the player
        saw = 0
        for _ in range(90):
            step()
            if g('PLAYER_HIT') or g('PLAYER_STATE') != 0:
                saw = 1
                break
        res['E_bullet_overlap_hit'] = bool(saw)

        # ---- H: WORST CASE -- layers that SHARE pixels --------------------
        # The diagnostic layers deliberately set disjoint pixels, and VIC
        # sprite/sprite collision only fires on OVERLAPPING non-transparent
        # pixels, so they never collide with each other. Real layered ship art
        # may well share pixels, which is the case that actually stresses the
        # $D01E gate. Force it: copy layer 0's bitmap over layers 1 and 2 so all
        # three are pixel-identical and maximally overlapping.
        if 'playerLayer0' in sym:
            base = sym['playerLayer0']
            src = peek(base, 63)
            for layer in (1, 2):
                dst = base + 64 * layer
                for off in range(0, 63, 8):
                    poke(dst + off, *src[off:off + 8])
            clear_pool(); step(8)
            poke(sym['PLAYER_HIT'], 0)
            opens = 0; hits = 0; K = 150
            for _ in range(K):
                step()
                poke(sym['OBJECT_Y'], 200)
                clear_pool()
                if peek(0xd01e)[0] & g('PLAYER_HW_MASK'):
                    opens += 1
                if g('PLAYER_HIT'):
                    hits += 1
                    poke(sym['PLAYER_HIT'], 0)
            res['H_overlapping_layers_gate_open'] = f'{opens}/{K}'
            res['H_overlapping_layers_false_hits'] = hits
            res['H_player_state'] = g('PLAYER_STATE')
            res['H_lives_still'] = g('PLAYER_LIVES')
            # and a real hit must still work with overlapping layers
            clear_pool(); step(4)
            poke(sym['PLAYER_HIT'], 0); poke(sym['OBJECT_Y'], 200)
            spawn(1, 2, g('OBJECT_X'), 200)
            saw = 0
            for _ in range(90):
                step()
                if g('PLAYER_HIT') or g('PLAYER_STATE') != 0:
                    saw = 1; break
            res['H_real_hit_still_detected'] = bool(saw)
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
    print(f'--- {a.label} ---')
    for k, v in res.items():
        print(f'  {k:<36} {v}')


if __name__ == '__main__':
    main()
