#!/usr/bin/env python3
"""Firing / hitscan behaviour across the overheat lockout.

Parks a live enemy directly in front of the player's cannons and holds FIRE,
checking that:
  * a COLD weapon fires, flashes the muzzle and damages the enemy;
  * a LOCKED weapon fires nothing, arms no cadence, shows no muzzle flash and
    does no damage, however long FIRE is held;
  * heat does not rise while locked;
  * firing and damage resume once the lock clears.
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
FIRE, NEUTRAL = 0xEF, 0xFF


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=7920)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
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

        def heat():
            v = peek(sym['WEAPON_HEAT_LO'], 2)
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
        poke(sym['PLAYER_LIVES'], 255)
        step(20)
        mon.cmd(f"f {sym['OBJECT_ACTIVE'] + 1:04x} {sym['OBJECT_ACTIVE'] + 15:04x} 00")

        def target():
            """A stationary enemy directly above the player, well clear of its
            collision box so it can be shot without killing the player."""
            poke(sym['OBJECT_ACTIVE'] + 1, 1)
            poke(sym['OBJECT_TYPE'] + 1, 2)
            poke(sym['OBJECT_X'] + 1, g('OBJECT_X'))
            poke(sym['OBJECT_X_MSB'] + 1, g('OBJECT_X_MSB'))
            poke(sym['OBJECT_Y'] + 1, 120)
            poke(sym['OBJECT_HEALTH'] + 1, 200)
            poke(sym['OBJECT_DEATH_TIMER'] + 1, 0)
            poke(sym['OBJECT_HIT_TIMER'] + 1, 0)
            poke(sym['OBJECT_VEL_X'] + 1, 0)
            poke(sym['OBJECT_VEL_Y'] + 1, 0)
            poke(sym['OBJECT_PATH_TIMER'] + 1, 255)

        def hold():
            mon.cmd(f"f {sym['OBJECT_ACTIVE'] + 2:04x} {sym['OBJECT_ACTIVE'] + 15:04x} 00")
            poke(sym['PLAYER_HIT'], 0)
            poke(sym['PLAYER_STATE'], 0)
            poke(sym['OBJECT_ACTIVE'] + 1, 1)
            poke(sym['OBJECT_Y'] + 1, 120)

        # ---- COLD: must fire, flash and damage ---------------------------
        mon.cmd(f'jpdb 1 {FIRE:02x}')          # FIRE held for the whole test
        poke(sym['WEAPON_HEAT_LO'], 0, 0); poke(sym['WEAPON_OVERHEATED'], 0)
        target(); step(2); hold()
        hp0 = g('OBJECT_HEALTH', 1)
        volleys = muzzle = 0
        for _ in range(60):
            step(); hold()
            if g('PLAYER_FIRE_COOLDOWN_TIMER') == 8:
                volleys += 1
            if g('PLAYER_MUZZLE_TIMER'):
                muzzle += 1
        res['cold_hp_before'] = hp0
        res['cold_hp_after'] = g('OBJECT_HEALTH', 1)
        res['cold_damage_dealt'] = hp0 - g('OBJECT_HEALTH', 1)
        res['cold_volleys'] = volleys
        res['cold_muzzle_frames'] = muzzle
        res['cold_heat_rose_to'] = heat()

        # ---- LOCKED: must not fire, flash, heat or damage ----------------
        poke(sym['WEAPON_HEAT_LO'], 300 & 0xff, 300 >> 8)
        poke(sym['WEAPON_OVERHEATED'], 1)
        poke(sym['OBJECT_HEALTH'] + 1, 200)
        poke(sym['PLAYER_FIRE_COOLDOWN_TIMER'], 0)
        poke(sym['PLAYER_MUZZLE_TIMER'], 0)
        hold(); step(1); hold()
        hp1 = g('OBJECT_HEALTH', 1)
        h_prev = heat()
        volleys = muzzle = rose = 0
        for _ in range(40):                 # 40 frames < the 50-frame lockout
            step(); hold()
            if g('PLAYER_FIRE_COOLDOWN_TIMER'):
                volleys += 1
            if g('PLAYER_MUZZLE_TIMER'):
                muzzle += 1
            h = heat()
            if h > h_prev:
                rose += 1
            h_prev = h
        res['locked_hp_before'] = hp1
        res['locked_hp_after'] = g('OBJECT_HEALTH', 1)
        res['locked_damage_dealt'] = hp1 - g('OBJECT_HEALTH', 1)
        res['locked_cadence_frames'] = volleys
        res['locked_muzzle_frames'] = muzzle
        res['locked_heat_rise_frames'] = rose
        res['locked_still_latched'] = g('WEAPON_OVERHEATED')

        # ---- after unlock: firing and damage resume ----------------------
        for _ in range(60):
            step(); hold()
            if g('WEAPON_OVERHEATED') == 0:
                break
        poke(sym['OBJECT_HEALTH'] + 1, 200)
        hp2 = 200
        volleys = 0
        for _ in range(40):
            step(); hold()
            if g('PLAYER_FIRE_COOLDOWN_TIMER') == 8:
                volleys += 1
        res['unlocked_damage_dealt'] = hp2 - g('OBJECT_HEALTH', 1)
        res['unlocked_volleys'] = volleys
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
