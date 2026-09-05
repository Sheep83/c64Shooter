#!/usr/bin/env python3
"""Isolate VIC edge geometry in emulator RAM; never writes engine source.

Run after a normal game capture so the fresh engine has initialized VIC and
charset. This deliberately replaces screen RAM, colour RAM, and CPU execution
in that disposable emulator. The probe records all changes in monitor.log.
"""
import argparse
import json
import re
from pathlib import Path
from vice_scroll_test import Monitor


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    mon = Monitor(args.port)
    mon.trace_file = (out / 'monitor.log').open('w')
    cmd = mon.cmd
    cmd('delete')
    cmd('> d01a 00')
    cmd('> c000 78 4c 01 c0')  # SEI; JMP $c001: CPU cannot update screen/VIC.
    cmd('r pc=c000')
    cmd('> d015 00')
    cmd('> d020 06')  # Blue border separates actual border from black idle output.
    cmd('> d021 00')
    cmd('> d016 c8')
    cmd('> d018 1e')  # Existing $0400 matrix, $3800 charset, bank zero.
    cmd('> dd00 03')
    cmd('fill 0400 07e7 e0')  # Existing vertical-rail glyph in every cell.
    cmd('fill d800 dbe7 01')  # White rail; no sprite or palette ambiguity.
    cmd('> 3f00 18 18 18 18 18 18 18 18')
    cmd('> 3fff 00')
    bp = int(re.search(r'BREAK: (\d+)', cmd('break exec 0000 ffff if RL == $137'))[1])
    cmd('x')
    records = []
    # 24-row mode is a monitor-only comparison, not an engine fix.
    for rsel in (1, 0):
        for phase in range(8):
            cmd(f'> d011 {0x10 | (rsel << 3) | phase:02x}')
            for _ in range(2):
                cmd(f'condition {bp} if RL == $000')
                cmd('x')
                cmd(f'condition {bp} if RL == $137')
                cmd('x')
            name = f'rsel{rsel}-fine{phase}.png'
            cmd(f'screenshot "{out / name}" 2')
            records.append(dict(rsel=rsel, fine=phase, image=name, registers=cmd('r')))
    (out / 'frames.json').write_text(json.dumps(records, indent=2))
    cmd('delete')
    mon.sock.sendall(b'x\n')
    mon.sock.close()
    print(f'Captured 16 isolated edge geometries in {out}')


if __name__ == '__main__':
    main()
