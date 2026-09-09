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
    parser.add_argument('--dense', action='store_true', help='Seed16 stationary legal objects producing8 closely spaced batches; keep real scrolling/main loop')
    parser.add_argument('--y199', action='store_true', help='Stage 4F: 8 enemies Y=199 + player Y=235 (pending-LIVE reuse); keep real scrolling')
    parser.add_argument('--turret-playtest', action='store_true', help='Aim real player cannons at turret0 near a coarse transition and turret2 near bottom exit; capture subsequent wraps')
    parser.add_argument('--symbols', type=Path, default=Path('build/main.vs'))
    parser.add_argument('--out', type=Path, default=Path('build/scroll-test'))
    parser.add_argument('--prg', type=Path, default=Path('build/shooter.prg'))
    parser.add_argument('--frames', type=int, default=600)
    parser.add_argument('--command', action='append', default=[])
    parser.add_argument('--seed-scroll', type=int, default=None,
                        help='After the game starts, force SCROLL_ROW (16-bit) '
                             'to this logical row so a large stage reaches its '
                             'end->start wrap within the capture window.')
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
    if args.seed_scroll is not None:
        # Force the stage position BEFORE initBackground draws the first screen,
        # so the whole matrix is rendered consistently for the seeded row (no
        # transient while the scroller replaces stale rows one per coarse step).
        mon.cmd(f'break {sym["initBackground"]:04x}')
        mon.cmd('x')
        mon.cmd(f'> {sym["SCROLL_ROW"]:04x} {args.seed_scroll & 0xff:02x} '
                f'{(args.seed_scroll >> 8) & 0xff:02x}')
        # initBackground's own `lda #0 / sta SCROLL_ROW(_HI)` would undo the poke;
        # step past those two stores (they are the first thing it does after the
        # coarse-flag clears). Re-poke right after instead, at the row loop.
        mon.cmd('delete')
        mon.cmd(f'break {sym["renderStageRowToScreen"]:04x}')
        mon.cmd('x')
        mon.cmd(f'> {sym["SCROLL_ROW"]:04x} {args.seed_scroll & 0xff:02x} '
                f'{(args.seed_scroll >> 8) & 0xff:02x}')
        mon.cmd('delete')
    mon.cmd(f'break {sym["applyFineScroll"]:04x}')
    mon.cmd('x')
    mon.cmd('jpdb 1 ef')
    if args.dense or args.y199:
        def put(name, values):
            mon.cmd(f'> {sym[name]:04x} '+' '.join(f'{v:02x}' for v in values))
        if args.y199:
            # Stage 4F fixture: 8 enemies at Y=199 + player at Y=235 -> a LIVE reuse
            # batch outstanding around raster ~223 on every frame (the historical
            # reason-1 / COARSE_DEFER_LIVE trigger). Real scrolling / main loop kept.
            put('OBJECT_ACTIVE',[1]*9+[0]*7)
            put('OBJECT_TYPE',[1]+[2]*8+[0]*7)
            put('OBJECT_Y',[235]+[199]*8+[0]*7)
            put('OBJECT_X',[80]+[40+24*i for i in range(8)]+[0]*7)
        else:
            put('OBJECT_ACTIVE',[1]*16)
            put('OBJECT_TYPE',[1]+[2]*15)
            put('OBJECT_Y',list(range(100,129,4))+list(range(136,165,4)))
            put('OBJECT_X',[24+32*(i%8) for i in range(16)])
        put('OBJECT_X_MSB',[0]*16)
        put('OBJECT_SPRITE',[sym['blankSprite']//64]*16)
        put('OBJECT_PATH_TIMER',[255]*16)
        put('OBJECT_STAGE',[2]*16)  # Valid egress coast; no eligible enemy firing source.
        for name in ('OBJECT_VEL_X','OBJECT_VEL_Y','OBJECT_TARGET_VEL_X','OBJECT_TARGET_VEL_Y','OBJECT_HIT_TIMER','OBJECT_DEATH_TIMER'):
            put(name,[0]*16)
        mon.cmd('jpdb 1 ff')
    if args.trace:
        mon.cmd(f'logname "{out / "timing.log"}"')
        mon.cmd('log on')
        for name in ('armFirstBatch', 'multiplexIRQ', 'gameplayPresented', 'shiftBackgroundUpper', 'bgUpperCopied', 'bgUpperReady', 'shiftBackgroundLower', 'bgLowerReady', 'rasterFrameReset', 'rasterInitialApplied', 'hudSlotReclaimed', 'rasterAssignmentApplied', 'rasterDisplayHook'):
            if name in sym:
                mon.cmd(f'trace exec {sym[name]:04x}')
        if 'RASTER_STATE_BEGIN' in sym:
            for name in ('rasterDisplayRestored', 'rasterBadlineRestored', 'rasterInitialMasksApplied', 'rasterBatchMasksApplied'):
                if name in sym:
                    mon.cmd(f'trace exec {sym[name]:04x}')
            mon.cmd('trace store d012 d012')
            mon.cmd('trace store d011 d011')
        for name in ('publishTurretGlyphs', 'backgroundTurretGlyphsPublished', 'installTurretRow'):
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
    turret_events = []
    attacking = None
    for frame in range(args.frames):
        if args.stress:
            for name in ('SPAWN_TIMER', 'WAVE_GAP_TIMER'):
                mon.cmd(f'> {sym[name]:04x} 01')
        regs = mon.cmd('r')
        mon.cmd(f'bsave "{out / f"{frame:05d}.ram"}" 0 0400 07ff')
        mon.cmd(f'bsave "{out / f"{frame:05d}.state"}" 0 2000 23ff')
        mon.cmd(f'screenshot "{out / f"{frame:05d}.png"}" 2')
        mon.cmd(f'bsave "{out / f"{frame:05d}.bg"}" 0 2920 2fff')
        mon.cmd(f'bsave "{out / f"{frame:05d}.colour"}" 0 d800 dbff')
        if 'TURRET_STATE_BEGIN' in sym:
            mon.cmd(f'bsave "{out / f"{frame:05d}.turret"}" 0 {sym["TURRET_STATE_BEGIN"]:04x} {sym.get("TURRET_SCRATCH_END", sym["TURRET_STATE_END"])-1:04x}')
            mon.cmd(f'bsave "{out / f"{frame:05d}.charset"}" 0 3800 3fff')
        if 'RASTER_STATE_BEGIN' in sym:
            mon.cmd(f'bsave "{out / f"{frame:05d}.raster"}" 0 {sym["RASTER_STATE_BEGIN"]:04x} {sym["RASTER_STATE_END"]-1:04x}')
        record = {'frame': frame, 'registers': regs}
        if args.physical:
            io = mon.cmd('m d010 d011')
            values = re.search(r'>C:d010\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})', io)
            record['physical_x_msb'] = int(values[1], 16)
            record['physical_fine'] = int(values[2], 16) & 7
        records.append(record)
        (out / 'frames.json').write_text(json.dumps(records, indent=2))
        (out / 'symbols.json').write_text(json.dumps(sym, indent=2))
        if frame % 100 == 0:
            print(f'Captured {frame}/{args.frames}', flush=True)
        direction = 4 if (frame // 70) % 2 else 8
        if args.turret_playtest:
            turret = (out / f'{frame:05d}.turret').read_bytes()
            def turret_get(name, index):
                return turret[sym[name]-sym['TURRET_STATE_BEGIN']+index]
            if attacking is not None and not turret_get('TURRET_HEALTH', attacking):
                turret_events.append(dict(frame=frame, destroyed=attacking, y=turret_get('TURRET_Y',attacking)))
                attacking = None
            if attacking is None:
                for t, minimum_y in ((0,112),(2,224)):
                    if (turret_get('TURRET_HEALTH',t) and turret_get('TURRET_VISIBLE',t)
                            and turret_get('TURRET_Y',t) >= minimum_y
                            and (t == 2 or record['physical_fine'] == 7)):
                        attacking = t
                        turret_events.append(dict(frame=frame, attack=t, y=turret_get('TURRET_Y',t)))
                        break
            if attacking is not None:
                x = turret_get('TURRET_X_LO',attacking)+256*turret_get('TURRET_X_HI',attacking)-4
                mon.cmd(f'> {sym["OBJECT_X"]:04x} {x&255:02x}')
                mon.cmd(f'> {sym["OBJECT_X_MSB"]:04x} {x>>8:02x}')
                mon.cmd(f'> {sym["OBJECT_Y"]:04x} f0')
                mon.cmd('jpdb 1 ef')
            else:
                mon.cmd(f'jpdb 1 {255 ^ direction:02x}')
            (out/'turret-events.json').write_text(json.dumps(turret_events,indent=2))
        else:
            mon.cmd('jpdb 1 ff' if args.dense else f'jpdb 1 {255 ^ (16 | direction):02x}')
        if args.physical:
            mon.cmd(f'condition {physical_break} if RL == $000')
            mon.cmd('x')
            mon.cmd(f'condition {physical_break} if RL == $137')
        mon.cmd('x')
    (out / 'frames.json').write_text(json.dumps(records, indent=2))
    (out / 'symbols.json').write_text(json.dumps(sym, indent=2))
    mon.cmd(f'bsave "{out / "charset.bin"}" 0 3800 3fff')
    # VIC-II register image ($D000..$D02F): the terrain oracles read $D016
    # (global char MCM), $D021/$D022/$D023 (the multicolour palette registers)
    # from here rather than hard-coding them.
    mon.cmd(f'bsave "{out / "vic.bin"}" 0 d000 d02f')
    if 'TURRET_STATE_BEGIN' in sym:
        # Streaming turret pool: turretAuth* are the AUTHORED placement LUTs
        # (turretAuthCol / turretAuthRowLo / turretAuthRowHi kept contiguous so
        # the dump is [cols(N), rowsLo(N)] + [rowsHi(N)], N = TURRET_TOTAL).
        col_lbl = 'turretAuthCol' if 'turretAuthCol' in sym else 'turretWorldCol'
        row_lbl = 'turretAuthRowLo' if 'turretAuthRowLo' in sym else 'turretWorldRow'
        rowhi_lbl = 'turretAuthRowHi' if 'turretAuthRowHi' in sym else 'turretWorldRowHi'
        n = sym[row_lbl] - sym[col_lbl]  # TURRET_TOTAL bytes
        dumps = [('turret-placements.bin', sym[col_lbl], sym[row_lbl] + n - 1),
                 ('turret-art.bin', sym['turretArt'], sym['turretArtEnd'] - 1)]
        if 'turretGroundCodes' in sym:          # shared-glyph pool: cached terrain codes, POOL*4 bytes
            gc = sym['turretGroundCodes']
            dumps.append(('turret-ground.bin', gc, gc + sym.get('TURRET_POOL_CODE', 8) * 4 - 1))
        elif 'turretGroundGlyphs' in sym:
            dumps.append(('turret-ground.bin', sym['turretGroundGlyphs'], sym['turretGroundGlyphs'] + 95))
        if rowhi_lbl in sym:
            dumps.append(('turret-placements-hi.bin',
                          sym[rowhi_lbl], sym[rowhi_lbl] + n - 1))
        for name, low, high in dumps:
            mon.cmd(f'bsave "{out / name}" 0 {low:04x} {high:04x}')
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
