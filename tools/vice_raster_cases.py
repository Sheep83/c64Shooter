#!/usr/bin/env python3
"""Fresh-VICE scheduler cases, including repeated LIVE frames with main parked."""
import argparse
import json
import re
import socket
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

CASES = {
    'early24': [49]+[0]*8+[36,85,121,157,193,229,255],
    'player37': [49]+[0]*8+[85,121,157,193,229,255,255],
    'overlap55': [67]+[0]*8+[85,121,157,193,229,255,255],
    'late243': [49]+[219]*7+[255]*8,
    'close4': list(range(100,129,4))+list(range(136,165,4)),
    'zero': [],
    'one': [100],
    'eight': list(range(100,129,4)),
    'viewport_edges': [71,0,49,50,69,70,71,72,245,246,247,254,255,100,150,200],
    'clip_eight': [220,51,54,57,60,63,66,69,70,150,150,150,150,150,150,150],
    'clip_boundary': [220,50,51,70,71,72,90,105,120,135,150,165,180,195,210,240],
    'viewport_top_dma': [71]*8+[107,143,179,215,220,225,230,245],
    'viewport_early95': [71]*8+[107]*8,
    'viewport_late233': [71]+[209]*7+[245]*8,
    'coarse_late_dma': [199]*8+[235]*8,
    'coarse_residual_dma': [220]+[235]*7,
    'coarse_sparse_dma': [190,197,204,211,218,225,232,239],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--port', type=int, default=6542)
    parser.add_argument('--frames', type=int, default=12)
    parser.add_argument('--all-phases', action='store_true', help='Cycle YSCROLL on each parked-main physical frame')
    parser.add_argument('--solid', action='store_true', help='Solid white diagnostic sprites at guarded scratch2fc0; capture pixels')
    parser.add_argument('--prg', type=Path, default=Path('build/shooter.prg'))
    parser.add_argument('--symbols', type=Path, default=Path('build/main.vs'))
    parser.add_argument('--prepare-at', type=int, help='After capture, call real coarse prepare at this physical raster under the seeded LIVE schedule')
    parser.add_argument('--copy-cpu', action='store_true', help='Measure prepare CPU cycles for all stage origins with DEN/sprites/IRQs off')
    parser.add_argument('--publish-turret', action='store_true', help='Measure a worst-index dirty glyph publication before real LIVE initial sprite writes')
    parser.add_argument('--beam-race', action='store_true', help='Inject an overdue LIVE event across255->256 at32 instruction alignments')
    parser.add_argument('--out', type=Path, default=Path('build/raster-scheduler/cases'))
    args = parser.parse_args()
    sym = symbols(args.symbols)
    for name, ys in CASES.items():
        if args.case and args.case != name:
            continue
        out = (args.out/name).resolve()
        out.mkdir(parents=True, exist_ok=True)
        # Refuse to attach to a pre-existing process on this port.
        with socket.socket() as check:
            if check.connect_ex(('127.0.0.1', args.port)) == 0:
                raise RuntimeError(f'Port {args.port} is already occupied')
        proc = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp',
                                 '+sound', '-remotemonitor', '-remotemonitoraddress',
                                 f'ip4://127.0.0.1:{args.port}', '-autostartprgmode', '1',
                                 '-autostart', str(args.prg.resolve())],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        mon = Monitor(args.port)
        mon.trace_file = (out/'monitor.log').open('w')
        mon.cmd('delete')
        mon.cmd('resourceset "JoyPort2Device" "37"')
        mon.cmd(f'break {sym["waitFireRelease"]:04x}')
        mon.cmd('jpdb 1 ef')
        mon.cmd('x')
        mon.cmd('jpdb 1 ff')
        mon.cmd('delete')
        mon.cmd(f'break {sym["buildSortedObjectList"]:04x}')
        mon.cmd('x')

        def put(label, values):
            mon.cmd(f'> {sym[label]:04x} '+' '.join(f'{value:02x}' for value in values))

        put('OBJECT_ACTIVE', [1]*len(ys)+[0]*(16-len(ys)))
        put('OBJECT_Y', ys+[0]*(16-len(ys)))
        put('OBJECT_X', [24+24*(i%8) for i in range(16)] if args.solid else [100]*16)
        put('OBJECT_X_MSB', [0]*16 if args.solid else [i%2 for i in range(16)])
        if args.solid:
            assert sym['BACKGROUND_CONTROL_END'] <= 0x2fc0
            # Multicolour pair10 selects each sprite's colour register (white).
            mon.cmd('> 2fc0 '+' '.join(['aa']*63+['00']))
        put('OBJECT_SPRITE', [0xbf if args.solid else sym['blankSprite']//64]*16)
        put('OBJECT_COLOUR', [1]*16)
        mon.cmd('delete')
        presentation = sym.get('gameplayPresented', sym.get('drawHudDiagnostic'))
        mon.cmd(f'break {presentation:04x}')
        mon.cmd('x')
        mon.cmd('delete')
        # The engine lives at6000+, so the old probe's6000 loop is unsafe here.
        mon.cmd('> 7f00 58 4c 01 7f')
        mon.cmd('r pc=7f00')
        def set_phase(phase):
            if 'RASTER_DISPLAY_FINE' in sym:
                put('RASTER_DISPLAY_FINE', [phase])
            else:
                mon.cmd(f'> d011 {0x10 | phase:02x}')
        set_phase(0 if args.all_phases else 7)
        mon.cmd(f'logname "{out / "timing.log"}"')
        mon.cmd('log on')
        for label in ('rasterInitialApplied', 'rasterAssignmentApplied', 'rasterFrameReset', 'rasterDisplayHook', 'applyLiveRasterBatch'):
            if label in sym:
                mon.cmd(f'trace exec {sym[label]:04x}')
        for label in ('rasterDisplayRestored', 'rasterBadlineRestored', 'rasterInitialMasksApplied', 'rasterBatchMasksApplied'):
            if label in sym:
                mon.cmd(f'trace exec {sym[label]:04x}')
        mon.cmd('trace store d012 d012')
        mon.cmd('trace store d011 d011')
        result = mon.cmd('break exec 0000 ffff if RL == $137')
        bp = int(re.search(r'BREAK: (\d+)', result)[1])
        mon.cmd('x')
        records = []
        for frame in range(args.frames):
            records.append({'frame': frame, 'registers': mon.cmd('r'), 'physical_fine': frame % 8 if args.all_phases else 7})
            if args.solid:
                mon.cmd(f'screenshot "{out / f"{frame:05d}.png"}" 2')
            for extension, low, high in [('state', 0x2000, 0x23ff), ('ram', 0x0400, 0x07ff),
                                         ('raster', sym['RASTER_STATE_BEGIN'], sym['RASTER_STATE_END']-1)]:
                mon.cmd(f'bsave "{out / f"{frame:05d}.{extension}"}" 0 {low:04x} {high:04x}')
            if args.all_phases:
                set_phase((frame+1) % 8)
            mon.cmd(f'condition {bp} if RL == $000')
            mon.cmd('x')
            mon.cmd(f'condition {bp} if RL == $137')
            mon.cmd('x')
        (out/'frames.json').write_text(json.dumps(records, indent=2))
        (out/'symbols.json').write_text(json.dumps(sym, indent=2))
        mon.cmd(f'bsave "{out / "charset.bin"}" 0 3800 3fff')
        if args.publish_turret:
            mon.cmd(f'delete {bp}')
            put('TURRET_DESIRED_STYLE',[4,4,0])
            put('TURRET_SHOWN_STYLE',[4,4,4])
            entry_label=sym['publishTurretGlyphs']
            entry_bp=int(re.search(r'BREAK: (\d+)',mon.cmd(f'break {entry_label:04x}'))[1])
            mon.cmd(f'r pc={sym["gameLoop"]:04x}, sp=ff')
            mon.cmd('x')
            entry=mon.cmd('r')
            mon.cmd(f'delete {entry_bp}')
            end_bp=int(re.search(r'BREAK: (\d+)',mon.cmd(f'break {sym["backgroundTurretGlyphsPublished"]:04x}'))[1])
            mon.cmd('x')
            end=mon.cmd('r')
            mon.cmd(f'delete {end_bp}')
            ready_bp=int(re.search(r'BREAK: (\d+)',mon.cmd(f'break {presentation:04x}'))[1])
            mon.cmd('x')
            ready=mon.cmd('r')
            mon.cmd(f'delete {ready_bp}')
            def beam(reg):
                m=re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n',reg)
                return tuple(map(int,m.groups()))
            a,b,c=map(beam,(entry,end,ready))
            # Earliest legal visible-ingress DMA starts Y51. Sprite writes and
            # display arming must complete before then, even with eight slots.
            assert b[0]<55 and c[0]<51,(name,a,b,c)
            result=dict(entry=entry,exit=end,presented=ready,publication_cycles=b[2]-a[2])
            (out/'turret-publication.json').write_text(json.dumps(result,indent=2))
            print(name,'glyph cycles',b[2]-a[2],'presentation raster',c[0],flush=True)
            # This probe intentionally leaves main at presentation. Do not
            # combine it with probes depending on the old parked-loop bp.
            assert not (args.copy_cpu or args.beam_race or args.prepare_at is not None)
        if args.beam_race:
            # A direct dispatcher call models a delayed event; IRQs stay masked
            # during each call. No event may escape by arming a past compare.
            state = (out/'00000.state').read_bytes()
            live = state[sym['LIVE_PLAN']-0x2000]
            count = state[sym['BATCH_COUNT']+live-0x2000]
            assert count
            mon.cmd('delete')
            mon.cmd('> d01a 00')
            mon.cmd('trace store d012 d012')
            results = []
            for padding in range(32):
                bp_race = int(re.search(r'BREAK: (\d+)',mon.cmd('break exec 0000 ffff if RL == $0ff'))[1])
                mon.cmd('x')
                mon.cmd(f'delete {bp_race}')
                put('RASTER_BATCH_OFFSET',[live])
                put('RASTER_BATCH_END',[live+count])
                put('BATCH_INDEX',[0])
                put('RASTER_DISPLAY_PENDING',[0])
                addr = sym['dispatchRasterEvents']
                code = [0x78]+[0xea]*padding+[0x20,addr&255,addr>>8]
                done = 0x7000+len(code)
                code += [0x4c,done&255,done>>8]
                mon.cmd('> 7000 '+' '.join(f'{v:02x}' for v in code))
                mon.cmd('r pc=7000')
                end_bp = int(re.search(r'BREAK: (\d+)',mon.cmd(f'break {done:04x}'))[1])
                entry=mon.cmd('r')
                mon.cmd('x')
                results.append(dict(padding=padding,entry=entry,exit=mon.cmd('r')))
                mon.cmd(f'delete {end_bp}')
            (out/'beam-race.json').write_text(json.dumps(results,indent=2))
        if args.copy_cpu:
            mon.cmd(f'delete {bp}')
            mon.cmd('> d01a 00')
            mon.cmd('> d015 00')
            mon.cmd('> d011 07')
            addr = sym['prepareBackgroundCoarse']
            mon.cmd(f'> 7000 20 {addr & 255:02x} {addr >> 8:02x} 4c 03 70')
            results = []
            logical_rows = (sym['STAGE_METATILE_ROWS_END']-sym['stageMetatileRows'])//10*4
            for row in range(logical_rows):
                mon.cmd('delete')
                mon.cmd('break exec 0000 ffff if RL == $0b4')
                mon.cmd('x')
                put('SCROLL_ROW',[row])
                put('SCROLL_FINE',[7])
                put('BG_COARSE_PENDING',[1])
                mon.cmd('delete')
                mon.cmd('break 7003')
                mon.cmd('r pc=7000')
                entry = mon.cmd('r')
                mon.cmd('x')
                end = mon.cmd('r')
                def clock(reg):return int(re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n',reg)[3])
                results.append(dict(row=row,cycles=clock(end)-clock(entry),entry=entry,exit=end))
            (out/'copy-cpu.json').write_text(json.dumps(results,indent=2))
            print('Prepare pure CPU cycles including JSR:',min(r['cycles'] for r in results),max(r['cycles'] for r in results),flush=True)
        if args.prepare_at is not None:
            set_phase(7)
            put('SCROLL_FINE',[7])
            put('BG_COARSE_PENDING',[1])
            mon.cmd(f'condition {bp} if RL == ${args.prepare_at:03x}')
            mon.cmd('x')
            entry = mon.cmd('r')
            mon.cmd(f'delete {bp}')
            addr = sym['prepareBackgroundCoarse']
            mon.cmd(f'> 7000 20 {addr & 255:02x} {addr >> 8:02x} 4c 03 70')
            mon.cmd('r pc=7000')
            mon.cmd('break 7003')
            mon.cmd('x')
            result = dict(requested_raster=args.prepare_at, entry=entry, exit=mon.cmd('r'))
            mon.cmd(f'bsave "{out / "coarse.bg"}" 0 2920 2fff')
            bg = (out/'coarse.bg').read_bytes()
            result['finish_pending'] = bg[sym['BG_COARSE_FINISH']-0x2920]
            result['deferred'] = bg[sym['BG_COARSE_DEFERRED']-0x2920]
            (out/'coarse-entry.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result,indent=2),flush=True)
        mon.cmd('log off')
        mon.cmd('delete')
        mon.sock.sendall(b'quit\n')
        mon.sock.close()
        proc.wait(timeout=10)
        print(name, 'captured', args.frames, 'physical frames', flush=True)


if __name__ == '__main__':
    main()
