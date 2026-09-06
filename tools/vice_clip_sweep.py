#!/usr/bin/env python3
"""Sweep a single enemy's Y through the top gameplay boundary in the real game
loop and prove the top-clip relationship pixel-for-pixel.

The engine keeps running (scroller, HUD raster scheduler, multiplexer). Each
physical frame one test enemy (logical slot 1) is pinned to a target Y with a
solid white sprite; every other enemy slot is cleared. The captured screenshot
must show white sprite pixels exactly on rasters max(Y+1, 72)..min(Y+21, 246)
and nothing above raster 72.
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

SOLID = 0x2fc0                       # Guarded scratch below the HUD/scheduler.
SOLID_PTR = SOLID // 64             # 0xbf
TEST_X = 160


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6562)
    ap.add_argument('--out', type=Path, default=Path('build/raster-scheduler/clip-sweep'))
    ap.add_argument('--lo', type=int, default=48)
    ap.add_argument('--hi', type=int, default=74)
    ap.add_argument('--src', default='solid',
                    help='solid | player | enemyA | a sprite-pointer value (decimal/0x..)')
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    prg = Path('build/shooter.prg').resolve()
    proc = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
                             '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{args.port}',
                             '-autostartprgmode', '1', '-autostart', str(prg)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    mon = Monitor(args.port)
    mon.trace_file = (out / 'monitor.log').open('w')
    mon.cmd('delete')
    mon.cmd('resourceset "JoyPort2Device" "37"')
    mon.cmd(f'break {sym["waitFireRelease"]:04x}')
    mon.cmd('jpdb 1 ef')
    mon.cmd('x')
    mon.cmd('jpdb 1 ff')
    mon.cmd('delete')
    mon.cmd(f'break {sym["applyFineScroll"]:04x}')
    mon.cmd('x')
    mon.cmd('jpdb 1 ef')
    mon.cmd('delete')

    def put(label, values, index=0):
        mon.cmd(f'> {sym[label] + index:04x} ' + ' '.join(f'{v & 0xff:02x}' for v in values))

    mon.cmd(f'> {SOLID:04x} ' + ' '.join(['aa'] * 63 + ['00']))
    mon.cmd('> d025 0b')
    mon.cmd('> d026 0f')
    mon.cmd('> d01c ff')
    put('PLAYER_LIVES', [0xff])

    src_ptr = {'solid': SOLID_PTR,
               'player': sym['playerSprite'] // 64,
               'enemyA': sym['enemySpriteA'] // 64}.get(args.src)
    if src_ptr is None:
        src_ptr = int(args.src, 0)
    src_addr = src_ptr * 64
    # Dump the source bitmap once (static for solid/player/enemyA).
    src_dump = out / 'source.bin'
    mon.cmd(f'bsave "{src_dump}" 0 {src_addr:04x} {src_addr+63:04x}')
    source = src_dump.read_bytes()[:63]

    bp = int(re.search(r'BREAK: (\d+)', mon.cmd('break exec 0000 ffff if RL == $137'))[1])
    mon.cmd('x')

    def pin(y):
        # Freeze the spawner and wipe every enemy except the inert pinned test slot.
        put('SPAWN_TIMER', [0xff])
        put('WAVE_GAP_TIMER', [0xff])
        put('OBJECT_ACTIVE', [1, 1] + [0] * 14)
        put('OBJECT_TYPE', [1, 2] + [0] * 14)
        put('OBJECT_SPRITE', [src_ptr], index=1)
        put('OBJECT_COLOUR', [1], index=1)
        put('OBJECT_X', [TEST_X & 0xff], index=1)
        put('OBJECT_X_MSB', [TEST_X >> 8], index=1)
        put('OBJECT_Y', [y], index=1)
        put('OBJECT_PATH_TIMER', [0xff], index=1)
        put('OBJECT_STAGE', [2], index=1)              # Egress coast: no path Y motion.
        for extra in ('OBJECT_HEALTH', 'OBJECT_HIT_TIMER', 'OBJECT_DEATH_TIMER', 'OBJECT_PATH_STEP',
                      'OBJECT_VEL_X', 'OBJECT_VEL_Y', 'OBJECT_TARGET_VEL_X', 'OBJECT_TARGET_VEL_Y'):
            if extra in sym:
                put(extra, [0], index=1)

    def step_frame():
        mon.cmd(f'condition {bp} if RL == $000')
        mon.cmd('x')
        mon.cmd(f'condition {bp} if RL == $137')
        mon.cmd('x')

    targets = list(range(args.hi, args.lo - 1, -1)) + list(range(args.lo, args.hi + 1))
    records, failures = [], []
    for i, y in enumerate(targets):
        # Hold the pinned Y for several frames so it settles through
        # BUILD -> swap -> display before the screenshot is taken.
        for _ in range(4):
            pin(y)
            step_frame()
        png = out / f'{i:03d}_y{y}.png'
        mon.cmd(f'screenshot "{png}" 2')
        state_path = out / f'{i:03d}.state'
        mon.cmd(f'bsave "{state_path}" 0 2000 23ff')
        pool_path = out / f'{i:03d}.pool'
        mon.cmd(f'bsave "{pool_path}" 0 3400 37ff')
        state = state_path.read_bytes()
        pool = pool_path.read_bytes()
        def g(name, index=0): return state[sym[name] + index - 0x2000]
        actual_y = g('OBJECT_Y', 1)
        live = g('LIVE_PLAN')
        slot = next((k for k in range(g('RENDER_COUNT', live)) if g('INITIAL_OBJECT', live + k) == 1), None)
        rec = {'index': i, 'target_y': y, 'object_y': actual_y, 'live_plan': live, 'slot': slot}
        if slot is not None:
            rec['plan_sprite'] = g('INITIAL_SPRITE', live + slot)
            rec['pool_slot'] = pool[(live + slot) * 64:(live + slot) * 64 + 63]
        records.append(rec)

    mon.cmd('log off')
    mon.cmd('delete')
    mon.sock.sendall(b'quit\n')
    mon.sock.close()
    proc.wait(timeout=10)

    from PIL import Image
    xlo, xhi = TEST_X + 8, TEST_X + 8 + 24
    checks = 0
    for rec in records:
        y = rec['object_y']
        if rec['target_y'] != y:
            failures.append([rec['index'], 'Y not pinned', rec['target_y'], y])
            continue
        im = Image.open(out / f"{rec['index']:03d}_y{rec['target_y']}.png").convert('RGB')
        white_rasters = set()
        for raster in range(44, 247):
            if any(im.getpixel((px, raster - 16)) == (255, 255, 255) for px in range(xlo, xhi)):
                white_rasters.add(raster)
        first = max(y + 1, 72)
        last = min(y + 21, 246)
        expected = set(range(first, last + 1)) if first <= last else set()
        checks += 203
        rec['white_rasters'] = sorted(white_rasters)
        rec['expected_rasters'] = sorted(expected)
        rec['visible_rows'] = len(white_rasters)
        if args.src == 'solid':
            # The solid diagnostic sprite fills every visible body row with white
            # and nothing else, so white_rasters == expected proves both the
            # clip depth and the absence of any sprite pixel above raster 72.
            # Real art (player/enemyA) is validated byte-exact below.
            if white_rasters != expected:
                failures.append([rec['index'], 'clip rasters', y, sorted(expected), sorted(white_rasters)])
            if any(r < 72 for r in white_rasters):
                failures.append([rec['index'], 'sprite white above raster 72', y, sorted(white_rasters)])
        # Byte-exact clip-pool proof, independent of rendering / graphics.
        if 51 <= y <= 70:
            d3 = (71 - y) * 3
            want = bytes(d3) + source[d3:]
            if rec.get('pool_slot') != want:
                diff = [k for k in range(63) if rec['pool_slot'][k] != want[k]][:8]
                failures.append([rec['index'], 'clip-pool bytes', y, diff])
            expect_ptr = 0xd0 + rec['live_plan'] + rec['slot']
            if rec.get('plan_sprite') != expect_ptr:
                failures.append([rec['index'], 'plan pointer', y, rec.get('plan_sprite'), expect_ptr])
        rec.pop('pool_slot', None)

    result = dict(frames=len(records), y_range=[args.lo, args.hi], raster_checks=checks,
                  failure_count=len(failures), failures=failures[:20], records=records)
    (out / 'clip-sweep.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ('frames', 'y_range', 'raster_checks', 'failure_count', 'failures')}, indent=2))
    # Compact human-readable depth table.
    for rec in records:
        if 'visible_rows' in rec:
            print(f"Y={rec['object_y']:3d}  visible rows={rec['visible_rows']:2d}  "
                  f"rasters {rec['white_rasters'][:1]}..{rec['white_rasters'][-1:]} "
                  f"(expect {rec['expected_rasters'][:1]}..{rec['expected_rasters'][-1:]})")
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
