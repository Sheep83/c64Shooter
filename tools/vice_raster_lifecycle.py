#!/usr/bin/env python3
"""Exercise real death, respawn, game-over, menu and restart paths in fresh VICE."""
import json
import argparse
import re
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('build/raster-scheduler/lifecycle'))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    proc = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
                             '-remotemonitor', '-remotemonitoraddress', 'ip4://127.0.0.1:6547',
                             '-autostartprgmode', '1', '-autostart', str(Path('build/shooter.prg').resolve())],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    mon = Monitor(6547)
    mon.trace_file = (out/'monitor.log').open('w')
    mon.cmd('delete')
    mon.cmd('resourceset "JoyPort2Device" "37"')
    mon.cmd(f'break {sym["waitFireRelease"]:04x}')
    mon.cmd('jpdb 1 ef')
    mon.cmd('x')
    mon.cmd('jpdb 1 ff')
    mon.cmd('delete')
    mon.cmd(f'break {sym["applyFineScroll"]:04x}')
    mon.cmd('x')
    mon.cmd('delete')
    mon.cmd(f'> {sym["PLAYER_LIVES"]:04x} 02')
    if 'TURRET_HEALTH' in sym:
        mon.cmd(f'> {sym["TURRET_HEALTH"]:04x} 00')
        mon.cmd(f'> {sym["TURRET_DESIRED_STYLE"]:04x} 07')
    bp = int(re.search(r'BREAK: (\d+)', mon.cmd('break exec 0000 ffff if RL == $137'))[1])
    mon.cmd('x')
    first_hit = second_hit = saw_respawn = saw_menu = False
    restart_pressed = restarted = False
    previous = None
    restart_frame = None
    transitions, failures = [], []
    last_game = last_jiffy = None
    gameplay_jiffy_changes = menu_jiffy_changes = 0
    turret_reset_checked = False
    for frame in range(1200):
        path = out/f'{frame:04d}.state'
        mon.cmd(f'bsave "{path}" 0 2000 23ff')
        state = path.read_bytes()
        def get(name):return state[sym[name]-0x2000]
        game, player = get('GAME_STATE'), get('PLAYER_STATE')
        m = re.search(r'>C:00a0\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})', mon.cmd('m 00a0 00a2'))
        jiffy = int(''.join(m.groups()),16)
        if last_jiffy is not None and jiffy != last_jiffy and game == last_game:
            if game == 1:gameplay_jiffy_changes += 1
            else:menu_jiffy_changes += 1
        last_game,last_jiffy = game,jiffy
        signature = (game, player, get('PLAYER_LIVES'))
        if signature != previous:
            enable = int(re.search(r'>C:d01a\s+([0-9a-fA-F]{2})', mon.cmd('m d01a d01a'))[1],16)
            vector = re.search(r'>C:0314\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})', mon.cmd('m 0314 0315'))
            vector = int(vector[1],16)+256*int(vector[2],16)
            transitions.append(dict(frame=frame, game=game, player=player, lives=signature[2], irq_enable=enable, irq_vector=vector))
            if game != 1 and (enable & 1 or vector != 0xea31):
                failures.append([frame, 'game IRQ survived teardown', enable, vector])
            previous = signature
        if game == 1 and not first_hit:
            mon.cmd(f'> {sym["PLAYER_HIT"]:04x} 01')
            first_hit = True
        if player == 2:
            saw_respawn = True
            if 'TURRET_HEALTH' in sym:
                health = int(re.search(r'>C:[0-9a-f]+\s+([0-9a-fA-F]{2})',mon.cmd(f'm {sym["TURRET_HEALTH"]:04x} {sym["TURRET_HEALTH"]:04x}'))[1],16)
                if health:
                    failures.append([frame,'respawn resurrected turret',health])
        if saw_respawn and player == 0 and game == 1 and not second_hit:
            mon.cmd(f'> {sym["PLAYER_HIT"]:04x} 01')
            second_hit = True
        if game == 0 and second_hit:
            saw_menu = True
            if not restart_pressed:
                mon.cmd('jpdb 1 ef')
                restart_pressed = True
        if restart_pressed and get('OBJECT_TYPE') != 1:
            failures.append([frame, 'logical player identity changed'])
        if restart_pressed and frame > transitions[-1]['frame']+3:
            mon.cmd('jpdb 1 ff')
        if saw_menu and game == 1:
            restarted = True
            if restart_frame is None:
                restart_frame = frame
            if frame >= restart_frame+4:
                if 'TURRET_HEALTH' in sym:
                    path = out/'restarted-turret.bin'
                    mon.cmd(f'bsave "{path}" 0 {sym["TURRET_HEALTH"]:04x} {sym["TURRET_HEALTH"]+2:04x}')
                    turret_reset_checked = path.read_bytes() == bytes([3,3,3])
                    if not turret_reset_checked:
                        failures.append([frame,'new-game turret reset',list(path.read_bytes())])
                enable = int(re.search(r'>C:d01a\s+([0-9a-fA-F]{2})', mon.cmd('m d01a d01a'))[1],16)
                vector = re.search(r'>C:0314\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})', mon.cmd('m 0314 0315'))
                vector = int(vector[1],16)+256*int(vector[2],16)
                if not enable & 1 or vector != sym['multiplexIRQ']:
                    failures.append([frame, 'scheduler failed to restart', enable, vector])
                transitions.append(dict(frame=frame, restarted_scheduler=True, irq_enable=enable, irq_vector=vector))
                break
        mon.cmd(f'condition {bp} if RL == $000')
        mon.cmd('x')
        mon.cmd(f'condition {bp} if RL == $137')
        mon.cmd('x')
    if not (saw_respawn and saw_menu and restarted):
        failures.append(['missing lifecycle state', saw_respawn, saw_menu, restarted])
    if 'initFixedHud' in sym and (gameplay_jiffy_changes or not menu_jiffy_changes):
        failures.append(['CIA/KERNAL lifecycle',gameplay_jiffy_changes,menu_jiffy_changes])
    result = dict(transitions=transitions, gameplay_jiffy_changes=gameplay_jiffy_changes,
                  menu_jiffy_changes=menu_jiffy_changes, turret_reset_checked=turret_reset_checked, failures=failures)
    (out/'results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    mon.cmd('delete')
    mon.sock.sendall(b'quit\n')
    mon.sock.close()
    proc.wait(timeout=10)
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
