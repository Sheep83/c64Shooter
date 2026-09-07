#!/usr/bin/env python3
"""Bottom-origin startup + editor-turret-placement integration checks.

Runs the built game to the first gameplay frame, then:
  A. asserts the boot SCROLL_ROW == STAGE_LOGICAL_ROWS - 23 (bottom origin);
  B. asserts the initial 23-row viewport is the contiguous bottom of the stage
     (screen RAM matches a plain tile expansion of logical rows
     STAGE_START_ROW..STAGE_START_ROW+22, with NO wrap and NO top-of-level rows);
  C. sweeps SCROLL_ROW(16) across the whole stage and records, per turret, the
     SCROLL_ROW window in which positionBackgroundTurrets marks it VISIBLE -
     proving near-bottom turrets activate first and that a turret whose world
     row is > 255 is handled (16-bit);
  D. kills one turret, sweeps SCROLL_ROW through a full 0->SLR-1 loop, and
     asserts HEALTH stays 0 and TURRET_DESTROYED is not re-incremented - no
     duplication / re-spawn / state corruption across the stage wrap.
"""
import argparse
import socket
import subprocess
import time
from pathlib import Path

from vice_scroll_test import Monitor, symbols
from vice_turret_runtime_probe import start_playing


def launch(port):
    with socket.socket() as c:
        if c.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'port {port} occupied')
    p = subprocess.Popen(
        ['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
         '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
         '-autostartprgmode', '1', '-autostart', str(Path('build/shooter.prg').resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p, Monitor(port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=6720)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/bottom-origin'))
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    proc, m = launch(args.port)
    fails = []
    try:
        m.trace_file = (out / 'monitor.log').open('w')
        start_playing(m, sym)
        m.cmd('delete')
        m.cmd('break 700a')

        def put(name, values):
            addr = sym[name] if isinstance(name, str) else name
            if isinstance(values, int):
                values = [values]
            m.cmd(f'> {addr:04x} ' + ' '.join(f'{v & 255:02x}' for v in values))

        def rd(name, n=1):
            addr = sym[name] if isinstance(name, str) else name
            p = out / 'scratch.bin'
            m.cmd(f'bsave "{p}" 0 {addr:04x} {addr + n - 1:04x}')
            return list(p.read_bytes())

        def w16(name):
            b = rd(name, 2)
            return b[0] | (b[1] << 8)

        def call(name):
            a = sym[name]
            put(0x7000, [0x78, 0xd8, 0x20, a & 255, a >> 8, 0x4c, 0x0a, 0x70])
            m.cmd('r pc=7000, sp=ff')
            m.cmd('x')

        tcount = sym['turretWorldXLo'] - sym['turretWorldRow']  # TURRET_COUNT bytes
        rows_len = sym['STAGE_METATILE_ROWS_END'] - sym['stageMetatileRows']
        slr = rows_len // 10 * 4
        defs = rd('metatileDefs', 256)
        metatile_defs = [defs[i:i + 16] for i in range(0, 256, 16)]
        raw = rd('stageMetatileRows', rows_len)
        stage_rows = [raw[i:i + 10] for i in range(0, rows_len, 10)]
        wlo = rd('turretWorldRow', tcount)
        whi = rd('turretWorldRowHi', tcount)
        world = [wlo[i] | (whi[i] << 8) for i in range(tcount)]
        cols = rd('turretWorldCol', tcount)
        print(f'stage {slr} logical rows; {tcount} turrets; world rows {world}; cols {cols}')

        def tile_row_codes(logical):
            mrow, sub = divmod(logical % slr, 4)
            ids = stage_rows[mrow]
            o = []
            for col in range(10):
                o += metatile_defs[ids[col]][sub * 4:sub * 4 + 4]
            return o

        # ---- A: boot SCROLL_ROW ---------------------------------------------
        boot = w16('SCROLL_ROW')
        expect = slr - 23
        if boot != expect:
            fails.append(f'A boot SCROLL_ROW={boot}, expected STAGE_LOGICAL_ROWS-23={expect}')
        else:
            print(f'A PASS boot SCROLL_ROW = {boot} = {slr}-23 (bottom origin)')

        # ---- B: initial viewport is the contiguous bottom, no wrap ---------
        scr = rd(0x0400, 24 * 40)
        mism = []
        for d in range(1, 24):                  # matrix rows 1..23
            logical = boot + d - 1               # no % : must NOT wrap for d<=23
            want = tile_row_codes(logical)
            got = scr[d * 40:d * 40 + 40]
            # skip the turret's 2 body cells (installTurretRow overwrites them)
            skip = set()
            for t in range(tcount):
                if logical == world[t]:
                    skip |= {cols[t], cols[t] + 1}
                if logical == (world[t] + 1):
                    skip |= {cols[t], cols[t] + 1}
            for c in range(40):
                if c not in skip and got[c] != want[c]:
                    mism.append((d, c, got[c], want[c]))
        if boot + 22 >= slr:
            fails.append('B initial viewport would wrap (STAGE too short) - unexpected')
        if mism:
            fails.append(f'B initial viewport mismatch (first 6): {mism[:6]}')
        else:
            print(f'B PASS initial 23 rows == contiguous logical {boot}..{boot + 22} '
                  f'(no wrap, no top-of-level rows)')

        # ---- C: turret VISIBLE window vs SCROLL_ROW -----------------------
        m.cmd('> d01a 00'); m.cmd('> dc0d 7f'); m.cmd('> d015 00'); m.cmd('> d011 00')
        put('RASTER_DISPLAY_FINE', 0)
        put('TURRET_HEALTH', [3] * tcount)
        vis_windows = [[] for _ in range(tcount)]
        for scroll in range(0, slr):
            put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
            put('TURRET_VISIBLE', [0] * tcount)
            call('positionBackgroundTurrets')
            v = rd('TURRET_VISIBLE', tcount)
            for t in range(tcount):
                if v[t]:
                    vis_windows[t].append(scroll)
        windows = []
        for t in range(tcount):
            if vis_windows[t]:
                lo, hi = min(vis_windows[t]), max(vis_windows[t])
                windows.append((t, world[t], lo, hi))
                contiguous = vis_windows[t] == list(range(lo, hi + 1))
                # positionBackgroundTurrets: VISIBLE iff rel in [1,20] where
                # rel = (worldRow - SCROLL_ROW) mod SLR, so the window is
                # SCROLL_ROW in [worldRow-20 .. worldRow-1] (width 20).
                if not contiguous:
                    fails.append(f'C turret{t} visible window not contiguous: {vis_windows[t][:5]}...')
                if (lo, hi) != ((world[t] - 20) % slr, (world[t] - 1) % slr):
                    fails.append(f'C turret{t} (row {world[t]}) visible SCROLL_ROW [{lo}..{hi}], '
                                 f'expected [{(world[t]-20)%slr}..{(world[t]-1)%slr}]')
            else:
                fails.append(f'C turret{t} never became visible in a full sweep')
        # ordering: gameplay SCROLL_ROW decreases from boot; a turret visible at a
        # higher SCROLL_ROW activates earlier. Higher world row -> earlier.
        activation_order = [t for (t, wr, lo, hi) in sorted(windows, key=lambda x: -x[3])]
        world_order = [t for (t, wr, lo, hi) in sorted(windows, key=lambda x: -x[1])]
        if activation_order != world_order:
            fails.append(f'C activation order {activation_order} != world-row order {world_order}')
        else:
            print(f'C PASS turret VISIBLE windows (SCROLL_ROW): ' +
                  ', '.join(f't{t}@row{wr}:[{lo}..{hi}]' for (t, wr, lo, hi) in windows))
            print(f'    activation order (first->last) = {activation_order}  '
                  f'(near-bottom/high-row first); >255 rows handled: '
                  f'{[wr for (_, wr, _, _) in windows if wr > 255]}')

        # ---- D: kill one turret, full wrap sweep, no resurrection ---------
        victim = max(range(tcount), key=lambda t: world[t])   # near-bottom turret
        put('TURRET_HEALTH', [3] * tcount)
        put('TURRET_DESTROYED', 0)
        put('TURRET_HEALTH', [0 if t == victim else 3 for t in range(tcount)])
        destroyed_before = rd('TURRET_DESTROYED', 1)[0]
        bad = False
        for scroll in list(range(boot, -1, -1)) + list(range(slr - 1, boot - 1, -1)):
            put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
            call('positionBackgroundTurrets')
            call('updateBackgroundTurrets')
            hp = rd('TURRET_HEALTH', tcount)
            if hp[victim] != 0:
                bad = True
                fails.append(f'D killed turret{victim} HEALTH resurrected to {hp[victim]} at SCROLL_ROW {scroll}')
                break
        destroyed_after = rd('TURRET_DESTROYED', 1)[0]
        if destroyed_after != destroyed_before:
            fails.append(f'D TURRET_DESTROYED changed {destroyed_before}->{destroyed_after} during a wrap sweep '
                         f'(unintended re-spawn/re-kill)')
        if not bad and destroyed_after == destroyed_before:
            print(f'D PASS killed turret{victim} stays dead across a full 0<->{slr-1} wrap; '
                  f'TURRET_DESTROYED stable at {destroyed_after}; no duplication/re-init')

        (out / 'bottom-origin.json').write_text(__import__('json').dumps({
            'boot_scroll_row': boot, 'stage_logical_rows': slr,
            'turret_world_rows': world, 'turret_cols': cols,
            'turret_visible_windows': [[w[2], w[3]] for w in windows],
            'activation_order': activation_order,
            'fails': fails,
        }, indent=2))
        if fails:
            print(f'\nFAIL ({len(fails)}):')
            for f in fails:
                print('  ' + f)
            raise SystemExit(1)
        print('\nPASS: bottom-origin startup + editor turret placement integration')
    finally:
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()


if __name__ == '__main__':
    main()
