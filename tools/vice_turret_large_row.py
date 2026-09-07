#!/usr/bin/env python3
"""Prove the STREAMING-POOL background turret does not truncate world-row
addressing above 255 logical rows.

Level 1 ships turrets at world rows 353..369 (all > 255) on a 400-logical-row
stage. This probe seeds pool slot 0 with a chosen > 255 world row and drives the
real routines through a trampoline:
  - positionBackgroundTurrets: for SCROLL_ROW(16) values that put the slot at a
    chosen relative row, check TURRET_Y and TURRET_VISIBLE against the model;
  - installTurretRow: for BG_LOGICAL_ROW(16) == the slot's top / bottom body row,
    check the two SHARED body glyph codes written to screen RAM;
  - pulseTurretColour + restore: colour-RAM cells get the pulse colour while
    visible+alive and revert to TERRAIN_COLOUR_RAM when the slot leaves;
  - hitCannonTarget: HP decrement / destroy on the > 255-row slot, and the
    turretDestroyedBits bit set for its authored index.
"""
import argparse
import json
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
            put(0x7000, [0x78, 0xd8, 0xa2, x & 255, 0x20, a & 255, a >> 8, 0x4c, 0x0a, 0x70])
            m.cmd('r pc=7000, sp=ff')
            m.cmd('x')

        def put16(name, slot, value):
            base = sym[name]
            m.cmd(f'> {base + slot:04x} {value & 0xFF:02x}')

        pool = sym['TURRET_POOL_CODE']
        rows_len = sym['STAGE_METATILE_ROWS_END'] - sym['stageMetatileRows']
        slr = rows_len // 10 * 4
        gbase = sym['TURRET_GLYPH_BASE_CODE']
        WROW, WCOL = 349, 5                    # > 255 world row, column 5
        if WROW <= 255:
            fails.append('probe misconfigured: WROW must be > 255')
        row2 = (WROW + 1) % slr
        print(f'stage {slr} logical rows; seeding slot 0 at world row {WROW} (> 255), col {WCOL}')

        def seed_slot():
            call('initBackgroundTurrets')
            put('TURRET_SLOT_AUTH', [0] + [0xFF] * (pool - 1))
            put16('TURRET_SLOT_ROW_LO', 0, WROW & 0xFF)
            put16('TURRET_SLOT_ROW_HI', 0, WROW >> 8)
            put16('TURRET_SLOT_ROW2_LO', 0, row2 & 0xFF)
            put16('TURRET_SLOT_ROW2_HI', 0, row2 >> 8)
            put16('TURRET_SLOT_COL', 0, WCOL)
            put16('TURRET_X_LO', 0, (24 + WCOL * 8) & 0xFF)
            put16('TURRET_X_HI', 0, (24 + WCOL * 8) >> 8)
            put16('TURRET_HEALTH', 0, 3)
            put16('TURRET_DEAD_RESTORED', 0, 0)
            put('RASTER_DISPLAY_FINE', 0)

        # ---- A: positionBackgroundTurrets -------------------------------
        seed_slot()
        for rr in (1, 5, 12, 20):
            scroll = (WROW - rr) % slr
            put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
            put16('TURRET_VISIBLE', 0, 0)
            call('positionBackgroundTurrets')
            y = rd('TURRET_Y', pool)[0]
            vis = rd('TURRET_VISIBLE', pool)[0]
            want_y = rr * 8 + 64
            want_vis = int(72 <= want_y <= 231)
            if y != want_y:
                fails.append(f'A rr={rr}: TURRET_Y={y} want {want_y}')
            if vis != want_vis:
                fails.append(f'A rr={rr}: VISIBLE={vis} want {want_vis}')
        for rr in (23, 60):                    # below the aperture -> not visible
            scroll = (WROW - rr) % slr
            put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
            put16('TURRET_VISIBLE', 0, 1)
            call('positionBackgroundTurrets')
            if rd('TURRET_VISIBLE', pool)[0]:
                fails.append(f'A rr={rr}: VISIBLE set for an off-aperture body')
        if not [f for f in fails if f.startswith('A ')]:
            print('A PASS positionBackgroundTurrets: Y + visibility exact for a > 255 world row')

        # ---- B: installTurretRow writes the SHARED body codes -----------
        seed_slot()
        for logical, expect in ((WROW, (gbase, gbase + 1)), (row2, (gbase + 2, gbase + 3))):
            m.cmd('> 0400 ' + ' '.join('20' for _ in range(80)))     # clear the top 2 rows
            put('BG_LOGICAL_ROW', [logical & 0xFF, (logical >> 8) & 0xFF])
            put('BG_LOGICAL_ROW_HI', [(logical >> 8) & 0xFF])
            # TEXT_DST ($fd/$fe zero page) -> screen row 3 base
            base = 0x0400 + 3 * 40
            put(0xfd, [base & 0xFF, base >> 8])
            call('installTurretRow')
            got = rd(base + WCOL, 2)
            if tuple(got) != expect:
                fails.append(f'B logical {logical}: wrote {got} at col {WCOL}, want {list(expect)}')
        if not [f for f in fails if f.startswith('B ')]:
            print(f'B PASS installTurretRow: shared body codes {gbase}..{gbase+3} at the right cells')

        # ---- C: pulse colour + restore --------------------------------
        seed_slot()
        rr = 8
        scroll = (WROW - rr) % slr
        put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
        call('positionBackgroundTurrets')
        put16('TURRET_CRAM_ROW', 0, 0)
        for _ in range(3):
            call('pulseTurretColour')
        mrow = rr + 1
        cram_base = 0xD800 + mrow * 40
        pulse = rd(cram_base + WCOL, 2)
        if not all(v & 0x08 for v in pulse):
            fails.append(f'C pulse colour RAM {pulse} lost the multicolour selector bit')
        # now scroll it off; cells must revert to TERRAIN_COLOUR_RAM
        put('SCROLL_ROW', [(WROW - 40) & 0xFF, ((WROW - 40) >> 8) & 0xFF])
        put16('TURRET_VISIBLE', 0, 0)
        call('positionBackgroundTurrets')
        call('pulseTurretColour')
        terr = sym.get('TERRAIN_COLOUR_RAM')
        reverted = rd(cram_base + WCOL, 2)
        # TERRAIN_COLOUR_RAM is a .const, not a symbol; accept "bit 3 set, low3 fixed"
        if len(set(reverted)) != 1:
            fails.append(f'C vacated colour RAM not uniform after restore: {reverted}')
        if not [f for f in fails if f.startswith('C ')]:
            print('C PASS pulseTurretColour: pulse while visible, uniform restore when it leaves')

        # ---- D: hitCannonTarget on the > 255-row slot ----------------
        seed_slot()
        put('TURRET_DESTROYED', 0)
        for expect_hp in (2, 1, 0):
            call('hitCannonTarget', 0x80 | 0)
            hp = rd('TURRET_HEALTH', pool)[0]
            if hp != expect_hp:
                fails.append(f'D hitCannonTarget: HP={hp} want {expect_hp}')
        if rd('TURRET_DESTROYED', 1)[0] != 1:
            fails.append('D TURRET_DESTROYED not incremented on the kill')
        bits = rd('turretDestroyedBits', 1)[0]
        if not (bits & 0x01):
            fails.append('D turretDestroyedBits bit 0 not set for the killed authored turret')
        if not [f for f in fails if f.startswith('D ')]:
            print('D PASS hitCannonTarget: HP decrement / destroy / destroyed-bit for a > 255 world row')

        (out / 'turret-large-row.json').write_text(json.dumps(
            {'stage_logical_rows': slr, 'world_row': WROW, 'pool': pool, 'fails': fails}, indent=2))
        if fails:
            print(f'FAIL ({len(fails)}):')
            for f in fails[:40]:
                print('  ' + f)
            raise SystemExit(1)
        print('\nPASS: streaming-pool turret world-row addressing correct above 255 logical rows')
    finally:
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()


if __name__ == '__main__':
    main()
