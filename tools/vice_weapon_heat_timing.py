#!/usr/bin/env python3
"""Measure the weapon overheat timings on real hardware timing, at PAL 50 Hz.

Drives the joystick FIRE line frame by frame and counts PHYSICAL FRAMES between
the state transitions the design specifies:

  1. cold -> overheat, firing continuously          target 150 frames / 3.0 s
  2. overheat -> firing re-enabled (latch cleared)   target  50 frames / 1.0 s
  3. overheat -> fully cold (heat == 0)              target 100 frames / 2.0 s
  4. re-fire from the re-enable threshold -> overheat target 75 frames / 1.5 s

Also samples the gauge width against heat so the HUD mapping can be checked, and
watches the flash colour while the lock is latched.

Joystick is neutral except for the explicit FIRE this test needs. The player is
held alive so a collision cannot end a measurement early.
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
NEUTRAL, FIRE = 0xFF, 0xEF          # bit 4 low = fire pressed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=7900)
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

        def g(n):
            return peek(sym[n])[0]

        def heat():
            v = peek(sym['WEAPON_HEAT_LO'], 2)
            return v[0] | (v[1] << 8)

        def poke(addr, *v):
            mon.cmd(f'> {addr:04x} ' + ' '.join(f'{x:02x}' for x in v))

        def alive():
            # Death calls resetWeaponHeat, which would silently restart a timing
            # measurement. Poking PLAYER_HIT at a frame boundary cannot prevent
            # that (capture and consumption both happen inside the frame), so
            # clear the enemy pool instead -- one fill command, no collisions,
            # and no effect whatsoever on the heat accumulator.
            mon.cmd(f"f {sym['OBJECT_ACTIVE'] + 1:04x} {sym['OBJECT_ACTIVE'] + 15:04x} 00")
            poke(sym['PLAYER_HIT'], 0)
            poke(sym['PLAYER_STATE'], 0)

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
        # start from a guaranteed-cold, unlocked weapon
        mon.cmd(f'r pc={sym["resetWeaponHeat"]:04x}')   # not executed; reset via poke instead
        poke(sym['WEAPON_HEAT_LO'], 0, 0)
        poke(sym['WEAPON_OVERHEATED'], 0)
        alive(); step(2); alive()
        res['heat_at_start'] = heat()

        # ---- 1. cold -> overheat, FIRE held ------------------------------
        mon.cmd(f'jpdb 1 {FIRE:02x}')
        frames = 0
        samples = []
        for _ in range(400):
            step(); frames += 1; alive()
            if frames % 25 == 0:
                samples.append((frames, heat(), g('HEAT_GAUGE_WIDTH')))
            if g('WEAPON_OVERHEATED'):
                break
        res['t1_cold_to_overheat_frames'] = frames
        res['t1_seconds'] = round(frames / 50.0, 2)
        res['t1_heat_at_lock'] = heat()
        res['t1_width_at_lock'] = g('HEAT_GAUGE_WIDTH')
        res['t1_samples_frame_heat_width'] = samples

        # ---- 2/3. release FIRE: overheat -> re-enable -> fully cold -------
        mon.cmd(f'jpdb 1 {NEUTRAL:02x}')
        f_reenable = f_cold = None
        frames = 0
        for _ in range(400):
            step(); frames += 1; alive()
            if f_reenable is None and g('WEAPON_OVERHEATED') == 0:
                f_reenable = frames
                res['t2_heat_at_reenable'] = heat()
                res['t2_width_at_reenable'] = g('HEAT_GAUGE_WIDTH')
            if heat() == 0:
                f_cold = frames
                break
        res['t2_overheat_to_reenable_frames'] = f_reenable
        res['t2_seconds'] = round(f_reenable / 50.0, 2) if f_reenable else None
        res['t3_overheat_to_cold_frames'] = f_cold
        res['t3_seconds'] = round(f_cold / 50.0, 2) if f_cold else None
        res['t3_width_when_cold'] = g('HEAT_GAUGE_WIDTH')

        # ---- 4. FIRE held right through the lockout ----------------------
        # The natural player case: never release FIRE. Measures from the frame
        # the latch CLEARS (heat == HEAT_REENABLE) to the frame it re-latches,
        # which is the burst length available straight off the threshold.
        poke(sym['WEAPON_HEAT_LO'], 0, 0)
        poke(sym['WEAPON_OVERHEATED'], 0)
        alive(); step(2); alive()
        mon.cmd(f'jpdb 1 {FIRE:02x}')
        for _ in range(400):                       # heat up to the lock, FIRE held
            step(); alive()
            if g('WEAPON_OVERHEATED'):
                break
        for _ in range(400):                       # stay locked, FIRE still held
            step(); alive()
            if g('WEAPON_OVERHEATED') == 0:
                break
        res['t4_heat_at_unlock'] = heat()
        frames = 0
        for _ in range(400):
            step(); frames += 1; alive()
            if g('WEAPON_OVERHEATED'):
                break
        res['t4_threshold_to_overheat_frames'] = frames
        res['t4_seconds'] = round(frames / 50.0, 2)
        res['t4_note'] = 'FIRE held continuously; measured unlock -> re-lock'

        # ---- flash while latched -----------------------------------------
        cols = []
        for _ in range(40):
            step(); alive()
            cols.append(peek(sym['hudProofColour'] + 2)[0])
        res['flash_colours_while_locked'] = sorted(set(cols))
        runs, cur = [], cols[0]
        n = 0
        for c in cols:
            if c == cur:
                n += 1
            else:
                runs.append(n); cur = c; n = 1
        runs.append(n)
        res['flash_run_lengths'] = runs

        # ---- flash stops at re-enable -------------------------------------
        mon.cmd(f'jpdb 1 {NEUTRAL:02x}')
        for _ in range(200):
            step(); alive()
            if g('WEAPON_OVERHEATED') == 0:
                break
        cols2 = []
        for _ in range(30):
            step(); alive()
            cols2.append(peek(sym['hudProofColour'] + 2)[0])
        res['colours_after_reenable'] = sorted(set(cols2))
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
