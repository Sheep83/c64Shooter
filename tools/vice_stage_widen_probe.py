#!/usr/bin/env python3
"""Drive the widened stage decoder on the real (emulated) 6502 and compare it,
byte for byte, against the independent Python model in check_stage_addressing.py
and a plain metatile expansion of the stage tables dumped from the running image.

For each probed BG_LOGICAL_ROW (16-bit) it calls decodeStageCharacterRow via a
tiny $7000 trampoline and reads back BG_TILE_ROW_OFS, BG_METATILE_ROW(_HI),
BG_ROW_BASE(_HI) and the 40-byte BG_INCOMING_ROW. Also exercises wrapBgLogicalRow
directly with out-of-range inputs. No screen capture; this isolates arithmetic.

    python3 tools/vice_stage_widen_probe.py --port 6571
"""
import argparse
import subprocess
import time
import socket
from pathlib import Path

from vice_scroll_test import Monitor, symbols
from vice_turret_runtime_probe import start_playing
from check_stage_addressing import decode_row_math, wrap_bg_logical_row

import re as _re
_RREG = _re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')


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
    ap.add_argument('--port', type=int, default=6571)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/stage-widen'))
    ap.add_argument('--timing', action='store_true')
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    proc, m = launch(args.port)
    failures = []
    try:
        m.trace_file = (out / 'monitor.log').open('w')
        start_playing(m, sym)

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

        m.cmd('delete')
        m.cmd('break 700a')                  # halt address for the call trampoline

        def call(name):
            a = sym[name]
            code = [0x78, 0xd8, 0x20, a & 255, a >> 8, 0x08, 0x68,
                    0x8d, 0x00, 0x7e, 0x4c, 0x0a, 0x70]
            put(0x7000, code)
            m.cmd('r pc=7000, sp=ff')
            m.cmd('x')

        def clk():
            return int(_RREG.search(m.cmd('r'))[3])

        def time_call(name, x=0):
            """Cycle cost of one `jsr name` (sei/cld, IRQs/DMA off), minus stub."""
            a = sym[name]
            code = [0x78, 0xd8, 0xa2, x & 255, 0x20, a & 255, a >> 8,
                    0x4c, 0x07, 0x70]
            put(0x7000, code)
            m.cmd('r pc=7000, sp=ff')
            t0 = clk()
            m.cmd('x')
            return clk() - t0 - 11           # 11 = sei+cld+ldx#+jmp overhead

        if args.timing:
            m.cmd('delete')
            m.cmd('break 7007')
            m.cmd('> d01a 00'); m.cmd('> dc0d 7f')
            m.cmd('> d015 00'); m.cmd('> d011 00')
            put('SCROLL_ROW', [40, 0])
            put('BG_DEST_ROW', 1)
            samples = {}
            for label, fn in [
                    ('decodeStageCharacterRow', lambda: time_call('decodeStageCharacterRow')),
                    ('renderStageRowToScreen', lambda: (put('BG_DEST_ROW', 1),
                                                        time_call('renderStageRowToScreen'))[1]),
                    ('installTurretRow', lambda: time_call('installTurretRow')),
                    ('positionBackgroundTurrets', lambda: time_call('positionBackgroundTurrets')),
                    ('wrapBgLogicalRow', lambda: time_call('wrapBgLogicalRow'))]:
                vals = []
                for _ in range(5):
                    try:
                        vals.append(fn())
                    except Exception as e:
                        vals.append(f'ERR {e}')
                samples[label] = vals
            print(__import__('json').dumps(samples, indent=2))
            return

        # Stage tables straight from the running image.
        defs = rd('metatileDefs', 256)
        metatile_defs = [defs[i:i + 16] for i in range(0, 256, 16)]
        rows_len = sym['STAGE_METATILE_ROWS_END'] - sym['stageMetatileRows']
        raw = rd('stageMetatileRows', rows_len)
        stage_rows = [raw[i:i + 10] for i in range(0, rows_len, 10)]
        n_rows = len(stage_rows)
        slr = n_rows * 4
        print(f'stage: {n_rows} metatile rows, {slr} logical rows, {rows_len}-byte map')

        def expected_incoming(logical_row):
            mrow, sub = divmod(logical_row, 4)
            ids = stage_rows[mrow]
            o = []
            for col in range(10):
                d = metatile_defs[ids[col]]
                o += d[sub * 4:sub * 4 + 4]
            return o

        probe_rows = sorted(set(
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 15, 16, 40, 99, 100, 101, 255, 256,
             257, 300, 511, 512, 1020, 1023, 1024, 1025, 1027, 1279, 1280,
             1596, 1599] +
            [slr - 1, slr - 2, slr - 4, slr - 5, slr // 2, slr // 2 + 1] +
            list(range(0, slr, max(1, slr // 53)))))
        probe_rows = [r for r in probe_rows if 0 <= r < slr]

        for row in probe_rows:
            put('BG_LOGICAL_ROW', [row & 0xFF, (row >> 8) & 0xFF])
            put('BG_INCOMING_ROW', [0xEE] * 40)
            call('decodeStageCharacterRow')
            tile_ofs = rd('BG_TILE_ROW_OFS')[0]
            mrow = rd('BG_METATILE_ROW', 2)
            rbase = rd('BG_ROW_BASE', 2)
            incoming = rd('BG_INCOMING_ROW', 40)
            got_mrow = mrow[0] | (mrow[1] << 8)
            got_rbase = rbase[0] | (rbase[1] << 8)

            want_mrow, want_sub, want_rbase = decode_row_math(row)
            if got_mrow != want_mrow or got_mrow != row >> 2:
                failures.append(f'row {row}: BG_METATILE_ROW={got_mrow} '
                                f'want {want_mrow}/{row >> 2}')
            if got_rbase != want_rbase or got_rbase != (row >> 2) * 10:
                failures.append(f'row {row}: BG_ROW_BASE={got_rbase} '
                                f'want {want_rbase}/{(row >> 2) * 10}')
            if tile_ofs != want_sub or tile_ofs != (row & 3) * 4:
                failures.append(f'row {row}: BG_TILE_ROW_OFS={tile_ofs} '
                                f'want {(row & 3) * 4}')
            if incoming != expected_incoming(row):
                diff = [i for i in range(40) if incoming[i] != expected_incoming(row)[i]]
                failures.append(f'row {row}: BG_INCOMING_ROW mismatch at {diff[:8]} '
                                f'got {[incoming[i] for i in diff[:8]]} '
                                f'want {[expected_incoming(row)[i] for i in diff[:8]]}')

        # wrapBgLogicalRow with deliberately out-of-range inputs.
        for v in [slr, slr + 1, slr + 22, 2 * slr - 1, slr - 1, 0, slr // 2,
                  slr + slr // 3]:
            put('BG_LOGICAL_ROW', [v & 0xFF, (v >> 8) & 0xFF])
            call('wrapBgLogicalRow')
            got = rd('BG_LOGICAL_ROW', 2)
            got = got[0] | (got[1] << 8)
            want = wrap_bg_logical_row(v, slr)
            want_ref = v % slr if v < 2 * slr else None
            if got != want or (want_ref is not None and got != want_ref):
                failures.append(f'wrap({v}) = {got} want {want}/{want_ref}')

        report = {
            'stage_metatile_rows': n_rows,
            'stage_logical_rows': slr,
            'map_bytes': rows_len,
            'probed_rows': len(probe_rows),
            'max_probed_row': max(probe_rows),
            'failures': failures,
        }
        (out / 'stage-widen.json').write_text(__import__('json').dumps(report, indent=2))
        if failures:
            print(f'FAIL ({len(failures)}):')
            for f in failures[:40]:
                print('  ' + f)
            raise SystemExit(1)
        print(f'PASS: {len(probe_rows)} logical rows (max {max(probe_rows)}) decoded '
              f'on the 6502 exactly match the model and a plain tile expansion; '
              f'wrapBgLogicalRow correct for out-of-range inputs.')
    finally:
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()


if __name__ == '__main__':
    main()
