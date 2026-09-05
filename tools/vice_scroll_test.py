#!/usr/bin/env python3
"""Capture consecutive emulated frames via VICE's text monitor (localhost:6510)."""
import argparse
import json
from pathlib import Path
import re
import socket


class Monitor:
    def __init__(self, port=6510):
        self.sock = socket.create_connection(('127.0.0.1', port), 5)
        self.sock.settimeout(20)
        self.sock.sendall(b'r\n')
        self.read()
        self.sock.settimeout(0.1)
        try:
            while self.sock.recv(65536):
                pass
        except socket.timeout:
            pass
        self.sock.settimeout(20)

    def read(self):
        result = b''
        while not re.search(rb'\(C:\$[0-9a-fA-F]+\)\s*$', result):
            part = self.sock.recv(65536)
            if not part:
                raise RuntimeError('VICE disconnected')
            result += part
        return result.decode(errors='replace')

    def cmd(self, command):
        self.sock.sendall((command + '\n').encode())
        result = self.read()
        if getattr(self, 'trace_file', None):
            self.trace_file.write(command + '\n' + result)
            self.trace_file.flush()
        if any(error in result for error in ('ERROR', 'Unknown resource', 'Illegal port.', 'Illegal value.')):
            raise RuntimeError(command + '\n' + result)
        return result


def symbols(path):
    return {name: int(addr, 16) for addr, name in re.findall(r'al C:([0-9a-fA-F]+) \.(\w+)', path.read_text())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=6510)
    parser.add_argument('--physical', action='store_true', help='Capture raster 311 of every physical PAL frame')
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--stress', action='store_true', help='Accelerate the existing spawner through monitor data writes')
    parser.add_argument('--symbols', type=Path, default=Path('build/main.vs'))
    parser.add_argument('--out', type=Path, default=Path('build/scroll-test'))
    parser.add_argument('--prg', type=Path, default=Path('build/shooter.prg'))
    parser.add_argument('--frames', type=int, default=600)
    parser.add_argument('--command', action='append', default=[])
    args = parser.parse_args()
    mon = Monitor(args.port)
    if args.command:
        for command in args.command:
            print(mon.cmd(command))
        return
    sym = symbols(args.symbols)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.trace:
        mon.trace_file = (out / 'monitor.log').open('w')
    mon.cmd('delete')
    mon.cmd('> d01a 00')
    mon.cmd('> 0314 31 ea')
    mon.cmd('> d015 00')
    mon.cmd('> d011 1b')
    mon.cmd(f'load "{args.prg.resolve()}" 0')
    mon.cmd(f'r pc={sym["init"]:04x}, sp=ff')
    mon.cmd('resourceset "JoyPort2Device" "37"')
    # A real joystick fire press starts the game through its normal menu path.
    mon.cmd(f'break {sym["waitFireRelease"]:04x}')
    mon.cmd('jpdb 1 ef')
    mon.cmd('x')
    mon.cmd('jpdb 1 ff')
    mon.cmd('delete')
    mon.cmd(f'break {sym["applyFineScroll"]:04x}')
    mon.cmd('x')
    mon.cmd('jpdb 1 ef')
    if args.trace:
        mon.cmd(f'logname "{out / "timing.log"}"')
        mon.cmd('log on')
        for name in ('armFirstBatch', 'multiplexIRQ', 'hudDiagnosticReady', 'shiftBackgroundUpper', 'bgUpperCopied', 'bgUpperReady', 'shiftBackgroundLower', 'bgLowerReady'):
            if name in sym:
                mon.cmd(f'trace exec {sym[name]:04x}')
    physical_break = None
    if args.physical:
        # Replace the presentation breakpoint; tracepoints remain installed.
        result = mon.cmd('break')
        for bp in re.findall(r'BREAK: (\d+)', result):
            mon.cmd(f'delete {bp}')
        result = mon.cmd('break exec 0000 ffff if RL == $137')
        physical_break = int(re.search(r'BREAK: (\d+)', result)[1])
        mon.cmd('x')
    mon.cmd(f'> {sym["PLAYER_LIVES"]:04x} ff')  # Long-run test stock; combat/death/respawn stay active.
    records = []
    for frame in range(args.frames):
        if args.stress:
            for name in ('SPAWN_TIMER', 'WAVE_GAP_TIMER'):
                mon.cmd(f'> {sym[name]:04x} 01')
        regs = mon.cmd('r')
        mon.cmd(f'bsave "{out / f"{frame:05d}.ram"}" 0 0400 07ff')
        mon.cmd(f'bsave "{out / f"{frame:05d}.state"}" 0 2000 23ff')
        mon.cmd(f'screenshot "{out / f"{frame:05d}.png"}" 2')
        mon.cmd(f'bsave "{out / f"{frame:05d}.bg"}" 0 2920 2fff')
        record = {'frame': frame, 'registers': regs}
        if args.physical:
            io = mon.cmd('m d011 d011')
            record['physical_fine'] = int(re.search(r'>C:d011\s+([0-9a-fA-F]{2})', io)[1], 16) & 7
        records.append(record)
        (out / 'frames.json').write_text(json.dumps(records, indent=2))
        (out / 'symbols.json').write_text(json.dumps(sym, indent=2))
        if frame % 100 == 0:
            print(f'Captured {frame}/{args.frames}', flush=True)
        direction = 4 if (frame // 70) % 2 else 8
        mon.cmd(f'jpdb 1 {255 ^ (16 | direction):02x}')
        if args.physical:
            mon.cmd(f'condition {physical_break} if RL == $000')
            mon.cmd('x')
            mon.cmd(f'condition {physical_break} if RL == $137')
        mon.cmd('x')
    (out / 'frames.json').write_text(json.dumps(records, indent=2))
    (out / 'symbols.json').write_text(json.dumps(sym, indent=2))
    mon.cmd(f'bsave "{out / "charset.bin"}" 0 3800 3fff')
    # Raw ground truth for the checker: the literal metatile definitions and
    # stage metatile-row IDs actually assembled into the program, dumped from
    # the running emulator rather than retyped in Python. Table sizes are
    # derived from these ranges, not hard-coded, so the checker never assumes
    # METATILE_DEF_COUNT/STAGE_METATILE_ROWS's values.
    mon.cmd(f'bsave "{out / "metatiledefs.bin"}" 0 {sym["metatileDefs"]:04x} {sym["METATILE_DEFS_END"]-1:04x}')
    mon.cmd(f'bsave "{out / "stagemetatilerows.bin"}" 0 {sym["stageMetatileRows"]:04x} {sym["STAGE_METATILE_ROWS_END"]-1:04x}')
    mon.cmd('log off')
    mon.cmd('delete')
    mon.sock.sendall(b'x\n')
    mon.sock.close()
    print(f'Captured {args.frames} consecutive frames in {out}')


if __name__ == '__main__':
    main()
