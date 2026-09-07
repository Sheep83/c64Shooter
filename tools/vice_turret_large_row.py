#!/usr/bin/env python3
"""Prove background-turret world-row addressing does not truncate above 255
logical rows. Expects a build whose turretRows are placed >255 (e.g. 255, 260,
1024) on a >=1024-logical-row stage.

Drives the real routines through a trampoline:
  - positionBackgroundTurrets: for SCROLL_ROW(16) values that put each turret at
    a chosen relative row, check TURRET_Y and TURRET_VISIBLE against the model.
  - installTurretRow: for BG_LOGICAL_ROW(16) == each turret's top / bottom body
    row, check the two glyph codes written to screen RAM at the right columns.
  - pulseTurretColour + restoration: colour-RAM cells get the pulse colour while
    visible+alive and revert to TERRAIN_COLOUR_RAM when the turret leaves.
  - hitCannonTarget: HP decrement / destroy path with a >255 turret.
"""
import argparse
import subprocess
import socket
import time
from pathlib import Path

from vice_scroll_test import Monitor, symbols
from vice_turret_runtime_probe import start_playing
from check_stage_addressing import turret_relative_row

SCREEN = 0x0400
CRAM = 0xD800


def launch(port):
    with socket.socket() as c:
        if c.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'port {port} occupied')
    p = subprocess.Popen(
        ['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
         '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
         '-autostartprgmode', '1', '-autostart',
         str(Path('build/shooter.prg').resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p, Monitor(port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=6611)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/turret-large-row'))
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
        m.cmd('> d01a 00'); m.cmd('> dc0d 7f')
        m.cmd('> d015 00'); m.cmd('> d011 00')

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

        def call(name, x=0):
            a = sym[name]
            code = [0x78, 0xd8, 0xa2, x & 255, 0x20, a & 255, a >> 8,
                    0x4c, 0x0a, 0x70]
            put(0x7000, code)
            m.cmd('r pc=7000, sp=ff')
            m.cmd('x')

        tcount = 3
        rows_len = sym['STAGE_METATILE_ROWS_END'] - sym['stageMetatileRows']
        slr = rows_len // 10 * 4
        world_lo = rd('turretWorldRow', tcount)
        world_hi = rd('turretWorldRowHi', tcount)
        world = [world_lo[i] | (world_hi[i] << 8) for i in range(tcount)]
        cols = rd('turretWorldCol', tcount)
        row2_lo = rd('turretWorldRow2', tcount)
        row2_hi = rd('turretWorldRow2Hi', tcount)
        row2 = [row2_lo[i] | (row2_hi[i] << 8) for i in range(tcount)]
        gbase = sym['TURRET_GLYPH_BASE_CODE']
        print(f'stage {slr} logical rows; turret world rows {world}; row2 {row2}; '
              f'cols {cols}; glyph base {gbase}')
        if max(world) <= 255:
            fails.append(f'build turret rows {world} are not >255 - patch turretRows')

        # ---- positionBackgroundTurrets: choose SCROLL_ROW so turret t sits at
        #      relative row rr (visible band 0..22), check Y and visibility.
        put('RASTER_DISPLAY_FINE', 0)
        for t in range(tcount):
            for rr in (2, 10, 22, 23, slr - 1):     # 23 -> not visible, slr-1 -> "above"
                scroll = (world[t] - rr) % slr
                put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
                put('TURRET_VISIBLE', [0, 0, 0])
                call('positionBackgroundTurrets')
                ty = rd('TURRET_Y', tcount)[t]
                vis = rd('TURRET_VISIBLE', tcount)[t]
                rel = turret_relative_row(world[t], scroll, slr)
                if rel == slr - 1:
                    exp_y, exp_vis = 56, 0
                elif rel >= 23:
                    exp_y, exp_vis = None, 0
                else:
                    exp_y = rel * 8 + 64
                    exp_vis = 1 if 72 <= exp_y <= 231 else 0
                if vis != exp_vis:
                    fails.append(f'pos t{t} rr{rr} scroll{scroll}: visible={vis} want {exp_vis}')
                if exp_y is not None and ty != exp_y:
                    fails.append(f'pos t{t} rr{rr} scroll{scroll}: Y={ty} want {exp_y}')

        # ---- installTurretRow: top and bottom body row -> correct glyph pair.
        put('BG_DEST_ROW', 5)
        dst = SCREEN + 5 * 40
        m.cmd(f"> 00fd {dst & 0xFF:02x} {dst >> 8:02x}")
        for t in range(tcount):
            for which, wr, g0 in [('top', world[t], gbase + t * 4),
                                  ('bot', row2[t], gbase + t * 4 + 2)]:
                m.cmd(f'> {dst:04x} ' + ' '.join('20' for _ in range(40)))
                put('BG_LOGICAL_ROW', [wr & 0xFF, (wr >> 8) & 0xFF])
                call('installTurretRow')
                scr = rd(dst, 40)
                c = cols[t]
                if scr[c] != g0 or scr[c + 1] != g0 + 1:
                    fails.append(f'install t{t} {which} row{wr}: cols {c}/{c+1} = '
                                 f'{scr[c]}/{scr[c+1]} want {g0}/{g0+1}')
                if any(scr[i] != 0x20 for i in range(40) if i not in (c, c + 1)):
                    fails.append(f'install t{t} {which}: wrote outside the 2 body cells')

        # ---- pulseTurretColour: cell colour while visible+alive, revert after.
        put('RASTER_DISPLAY_FINE', 0)
        t = tcount - 1                                   # the >1023-row turret
        rr = 10
        scroll = (world[t] - rr) % slr
        put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
        put('TURRET_HEALTH', [3, 3, 3])
        put('TURRET_VISIBLE', [0, 0, 0])
        put('TURRET_CRAM_ROW', [0, 0, 0])
        call('positionBackgroundTurrets')
        put('TURRET_VISIBLE', [0] * t + [1] + [0] * (tcount - t - 1))
        c = cols[t]
        terr = 8 | 1
        for _ in range(3):
            call('pulseTurretColour')
        mrow = rd('TURRET_CRAM_ROW', tcount)[t]          # matrix row the engine painted
        if mrow == 0:
            fails.append(f'pulse t{t}: engine painted no row (TURRET_CRAM_ROW=0) '
                         f'for a visible+alive >1023-row turret')
        else:
            flat = [v & 0x0F for v in (rd(CRAM + mrow * 40 + c, 2) +
                                        rd(CRAM + (mrow + 1) * 40 + c, 2))]
            if not all((v & 0x08) and (v & 7) in (1, 2, 7) for v in flat):
                fails.append(f'pulse t{t}: cells {flat} not a legal multicolour pulse value')
            # turret leaves -> the four cells revert to TERRAIN_COLOUR_RAM
            put('TURRET_VISIBLE', [0, 0, 0])
            call('pulseTurretColour')
            restored = [v & 0x0F for v in (rd(CRAM + mrow * 40 + c, 2) +
                                            rd(CRAM + (mrow + 1) * 40 + c, 2))]
            if any(v != terr for v in restored):
                fails.append(f'pulse t{t}: cells {restored} not restored to '
                             f'TERRAIN_COLOUR_RAM ({terr})')

        # ---- hitCannonTarget on the >255-row turret (X = 0x80 | t).
        put('TURRET_HEALTH', [3, 3, 3])
        put('TURRET_DESTROYED', 0)
        for expect_hp in (2, 1, 0):
            call('hitCannonTarget', 0x80 | t)
            hp = rd('TURRET_HEALTH', tcount)[t]
            if hp != expect_hp:
                fails.append(f'hitCannonTarget t{t}: HP={hp} want {expect_hp}')
        dead_style = rd('TURRET_DESIRED_STYLE', tcount)[t]
        if dead_style != 7:
            fails.append(f'hitCannonTarget t{t}: desired style {dead_style} want 7 (dead)')

        report = {'stage_logical_rows': slr, 'turret_world_rows': world,
                  'turret_row2': row2, 'fails': fails}
        (out / 'turret-large-row.json').write_text(__import__('json').dumps(report, indent=2))
        if fails:
            print(f'FAIL ({len(fails)}):')
            for f in fails[:40]:
                print('  ' + f)
            raise SystemExit(1)
        print('PASS: turret world-row addressing correct above 255 logical rows '
              '(position/visibility, glyph install, colour pulse + restore, '
              'hit/destroy).')
    finally:
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()


if __name__ == '__main__':
    main()
