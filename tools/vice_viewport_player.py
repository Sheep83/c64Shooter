#!/usr/bin/env python3
"""Hold real joystick UP through the normal game loop; verify the viewport player bound."""
import json
import re
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

out = Path('build/raster-scheduler/viewport-player').resolve()
out.mkdir(parents=True, exist_ok=True)
sym = symbols(Path('build/main.vs'))
proc = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
                         '-remotemonitor', '-remotemonitoraddress', 'ip4://127.0.0.1:6551',
                         '-autostartprgmode', '1', '-autostart', str(Path('build/shooter.prg').resolve())],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
mon = Monitor(6551)
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
mon.cmd('jpdb 1 fe')
bp = int(re.search(r'BREAK: (\d+)', mon.cmd('break exec 0000 ffff if RL == $137'))[1])
mon.cmd('x')
ys, failures = [], []
for frame in range(360):
    path = out/f'{frame:04d}.state'
    mon.cmd(f'bsave "{path}" 0 2000 23ff')
    state = path.read_bytes()
    def get(name): return state[sym[name]-0x2000]
    y = get('OBJECT_Y')
    ys.append(y)
    if y < 71 or get('OBJECT_TYPE') != 1 or not get('OBJECT_ACTIVE'):
        failures.append([frame, 'player identity/viewport', y, get('OBJECT_TYPE'), get('OBJECT_ACTIVE')])
    mon.cmd(f'condition {bp} if RL == $000')
    mon.cmd('x')
    mon.cmd(f'condition {bp} if RL == $137')
    mon.cmd('x')
if ys[-32:] != [71]*32:
    failures.append(['did not reach/hold upper bound', ys[-32:]])
result = dict(frames=len(ys), start_y=ys[0], minimum_y=min(ys), first_bound_frame=ys.index(71) if 71 in ys else None, failures=failures)
(out/'results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
mon.cmd('delete')
mon.sock.sendall(b'quit\n')
mon.sock.close()
proc.wait(timeout=10)
raise SystemExit(bool(failures))
