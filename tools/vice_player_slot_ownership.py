#!/usr/bin/env python3
"""Does the engine ALREADY hand the player its slots late in the frame?

The requested "late-frame reservation" is: all 8 physical sprites usable earlier
in the frame, with a pair reclaimed for the player as the raster approaches the
player band. The existing LIVE reuse batch is exactly that mechanism -- a
scheduled raster event that reprograms a slot whose previous owner's DMA has
provably completed (SLOT_FREE_RASTER[s] <= Y - 12).

Per frame this reports, for the LIVE plan:
  * RENDER_COUNT / BATCH_COUNT;
  * whether the player's slots were written by the INITIAL snapshot or by a
    LIVE batch;
  * for batch-assigned player slots, WHICH object held that slot initially --
    a different object means a genuine same-frame early reuse of a player slot;
  * the batch raster, i.e. the actual handoff line, and its margin to the
    player's sprite DMA.
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=7200)
    ap.add_argument('--prg', required=True)
    ap.add_argument('--symbols', required=True)
    ap.add_argument('--label', default='build')
    ap.add_argument('--frames', type=int, default=600)
    ap.add_argument('--seed-enemies', type=int, default=0,
                    help='synthetic: park N enemies ABOVE the player so the sorted '
                         'list exceeds 8 and the reuse-batch (late handoff) path '
                         'actually engages')
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

        for _ in range(300):
            step()
            if g('GAME_STATE') == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if g('GAME_STATE') == 1:
                break
        mon.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')
        step(30)

        stats = dict(frames=0, player_alive_frames=0,
                     player_all_initial=0, player_any_batch=0,
                     early_reuse_of_player_slot=0, render_count_hist={},
                     batch_count_hist={}, handoff_margins=[],
                     player_slots_hist={})
        def poke(addr, *v):
            mon.cmd(f'> {addr:04x} ' + ' '.join(f'{x:02x}' for x in v))

        def seed():
            for i in range(1, a.seed_enemies + 1):
                poke(sym['OBJECT_ACTIVE'] + i, 1)
                poke(sym['OBJECT_TYPE'] + i, 2)
                poke(sym['OBJECT_Y'] + i, 70 + 11 * i)
                poke(sym['OBJECT_X'] + i, 40 + 16 * i)
                poke(sym['OBJECT_X_MSB'] + i, 0)
                poke(sym['OBJECT_PATH_TIMER'] + i, 255)
                poke(sym['OBJECT_VEL_X'] + i, 0)
                poke(sym['OBJECT_VEL_Y'] + i, 0)
                poke(sym['OBJECT_DEATH_TIMER'] + i, 0)

        joy = None
        for f in range(a.frames):
            if a.seed_enemies:
                seed()
                poke(sym['PLAYER_HIT'], 0)
                poke(sym['PLAYER_STATE'], 0)
                poke(sym['OBJECT_Y'], 220)
            want = 0xEF if (f % 24) < 14 else 0xFF
            if want != joy:
                mon.cmd(f'jpdb 1 {want:02x}'); joy = want
            step()
            stats['frames'] += 1
            if g('PLAYER_STATE') != 0:
                continue
            stats['player_alive_frames'] += 1
            live = g('LIVE_PLAN')
            rc = g('RENDER_COUNT', live)
            bc = g('BATCH_COUNT', live)
            stats['render_count_hist'][rc] = stats['render_count_hist'].get(rc, 0) + 1
            stats['batch_count_hist'][bc] = stats['batch_count_hist'].get(bc, 0) + 1
            init_owner = [g('INITIAL_OBJECT', live + s) for s in range(rc)]
            py = g('OBJECT_Y')
            batch_player_slots = []
            for b in range(bc):
                first = g('BATCH_FIRST_ASSIGN', live + b)
                cnt = g('BATCH_ASSIGN_COUNT', live + b)
                braster = g('BATCH_RASTER', live + b)
                for k in range(cnt):
                    idx = live + first + k
                    if g('ASSIGN_OBJECT', idx) == 0:
                        slot = g('ASSIGN_SLOT', idx)
                        batch_player_slots.append((slot, braster))
                        prev = init_owner[slot] if slot < len(init_owner) else 0xFF
                        if prev not in (0, 0xFF):
                            stats['early_reuse_of_player_slot'] += 1
                        stats['handoff_margins'].append(py - braster)
            n_player = bin(g('PLAYER_HW_MASK')).count('1')
            stats['player_slots_hist'][n_player] = stats['player_slots_hist'].get(n_player, 0) + 1
            if batch_player_slots:
                stats['player_any_batch'] += 1
            else:
                stats['player_all_initial'] += 1
        m = stats.pop('handoff_margins')
        stats['handoff_margin_min'] = min(m) if m else None
        stats['handoff_margin_samples'] = len(m)
        stats['label'] = a.label
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
    print(json.dumps(stats, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main()
