#!/usr/bin/env python3
"""Audit every LIVE assignment in its physical PAL frame, independently of terrain."""
import argparse
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    root = args.capture
    symbols = json.loads((root / 'symbols.json').read_text())
    records = json.loads((root / 'frames.json').read_text())
    assignments = []
    trace = (root / 'timing.log').read_text(errors='replace')
    address = symbols['rasterAssignmentApplied']
    pattern = (rf'#\d+ \(Trace  exec {address:04x}\)\s+(\d+)/\$[0-9a-f]+,\s+'
               r'(\d+)/\$[0-9a-f]+\n\.C:[^\n]*?Y:([0-9A-Fa-f]+)[^\n]*? (\d+)\n')
    for match in re.finditer(pattern, trace):
        line, cycle, index, clock = match.groups()
        assignments.append((int(clock), int(line), int(cycle), int(index, 16)))
    initial = []
    if 'rasterInitialApplied' in symbols:
        address = symbols['rasterInitialApplied']
        pattern = (rf'#\d+ \(Trace  exec {address:04x}\)\s+(\d+)/\$[0-9a-f]+,\s+'
                   r'(\d+)/\$[0-9a-f]+\n\.C:[^\n]*?X:([0-9A-Fa-f]+)[^\n]*? (\d+)\n')
        initial = [(int(m[4]), int(m[1]), int(m[2]), int(m[3], 16))
                   for m in re.finditer(pattern, trace)]
    masks = {}
    for label in ('rasterInitialMasksApplied','rasterBatchMasksApplied'):
        if label in symbols:
            pattern = (rf'#\d+ \(Trace  exec {symbols[label]:04x}\)\s+(\d+)/\$[0-9a-f]+,\s+'
                       r'(\d+)/\$[0-9a-f]+\n\.C:[^\n]*?X:([0-9A-Fa-f]+)[^\n]*? (\d+)\n')
            masks[label] = [(int(m[4]),int(m[1]),int(m[2]),int(m[3],16)) for m in re.finditer(pattern,trace)]
    failures, deadlines = [], []
    compare_writes = []
    write_pattern = (r'#\d+ \(Trace store d012\)\s+(\d+)/\$[0-9a-f]+,\s+'
                     r'(\d+)/\$[0-9a-f]+\n\.C:[^\n]*?A:([0-9A-Fa-f]+)[^\n]*? (\d+)\n')
    for match in re.finditer(write_pattern, trace):
        line, cycle, value, clock = match.groups()
        line, value = int(line), int(value, 16)
        compare_writes.append((line, value))
        if value and (line >= 256 or value <= line):
            failures.append(['compare written behind beam', line, int(cycle), value, int(clock)])
    frames, total, previous_epoch = 0, 0, None
    max_batches = max_objects = max_catchups = max_replays = 0
    clocks = []
    for record in records:
        frame = record['frame']
        state = (root / f'{frame:05d}.state').read_bytes()
        raster = (root / f'{frame:05d}.raster').read_bytes()
        matrix = (root / f'{frame:05d}.ram').read_bytes()

        def get(name, index=0):
            addr = symbols[name] + index
            if 0x2000 <= addr < 0x2400:
                return state[addr - 0x2000]
            return raster[addr - symbols['RASTER_STATE_BEGIN']]

        def word(name):
            return get(name) + 256 * get(name, 1)

        regs = re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n', record['registers'])
        start = int(regs[3]) - 63 * int(regs[1]) - int(regs[2])
        clocks.append(start)
        live = get('LIVE_PLAN')
        batches = get('BATCH_COUNT', live)
        expected = sum(get('BATCH_ASSIGN_COUNT', live+i) for i in range(batches))
        done = get('RASTER_ASSIGNMENTS_DONE')
        epoch = word('RASTER_FRAME')
        if previous_epoch is not None and epoch != (previous_epoch+1) % 65536:
            failures.append([frame, 'physical reset epoch', previous_epoch, epoch])
        previous_epoch = epoch
        if get('RASTER_EXPECTED_ASSIGNMENTS') != expected or done != expected:
            failures.append([frame, 'assignment service', expected, get('RASTER_EXPECTED_ASSIGNMENTS'), done])
        if get('BATCH_INDEX') != batches:
            failures.append([frame, 'unfinished batch', get('BATCH_INDEX'), batches])
        if word('RASTER_INCOMPLETE_FRAMES'):
            failures.append([frame, 'reset found incomplete frame', word('RASTER_INCOMPLETE_FRAMES')])
        count = get('RENDER_COUNT', live)
        pointers = [get('INITIAL_SPRITE', live+i) for i in range(count)]
        owners = [get('INITIAL_OBJECT', live+i) for i in range(count)]
        msbs = [get('INITIAL_X_MSB', live+i) for i in range(count)]
        for i in range(expected):
            slot = get('ASSIGN_SLOT', live+i)
            pointers[slot] = get('ASSIGN_SPRITE', live+i)
            owners[slot] = get('ASSIGN_OBJECT', live+i)
            msbs[slot] = get('ASSIGN_X_MSB', live+i)
        player_mask = sum(1 << slot for slot, owner in enumerate(owners) if owner == 0)
        x_mask = sum(1 << slot for slot, msb in enumerate(msbs) if msb)
        if get('PLAYER_HW_MASK') != player_mask:
            failures.append([frame, 'player hardware ownership', get('PLAYER_HW_MASK'), player_mask])
        if 'physical_x_msb' in record and record['physical_x_msb'] != x_mask:
            failures.append([frame, 'X high hardware mask', record['physical_x_msb'], x_mask])
        if matrix[1016:1016+count] != bytes(pointers):
            failures.append([frame, 'final sprite pointers'])
        events = [event for event in assignments if start <= event[0] < start+19656]
        if frame:  # Initial capture can start partway through an already running frame.
            for label, all_events in masks.items():
                writes = [event for event in all_events if start <= event[0] < start+19656]
                initial_mask = label == 'rasterInitialMasksApplied'
                expected_writes = int(count > 0) if initial_mask else batches
                if len(writes) != expected_writes:
                    failures.append([frame,'mask write count',label,len(writes),expected_writes])
                for _,line,cycle,index in writes:
                    if initial_mask:
                        y = min(get('INITIAL_Y',live+i) for i in range(count))
                    else:
                        first = get('BATCH_FIRST_ASSIGN',index)+live
                        y = min(get('ASSIGN_Y',i) for i in range(first,first+get('BATCH_ASSIGN_COUNT',index)))
                    if line*63+cycle > y*63+55:
                        deadlines.append([frame,'mask',label,index,y,line,cycle])
            if 'rasterInitialApplied' in symbols:
                starts = [event for event in initial if start <= event[0] < start+19656]
                if [event[3] for event in starts] != list(range(count)):
                    failures.append([frame, 'initial snapshot trace', starts, count])
                for _, line, cycle, slot in starts:
                    y = get('INITIAL_Y', live+slot)
                    if line*63+cycle > y*63+55:
                        deadlines.append([frame, 'initial', slot, y, line, cycle])
            indices = [event[3] for event in events]
            if indices != list(range(live, live+expected)):
                failures.append([frame, 'physical assignment trace', indices, list(range(live, live+expected))])
            for _, line, cycle, index in events:
                y = get('ASSIGN_Y', index)
                if line*63+cycle > y*63+55:
                    deadlines.append([frame, index-live, y, line, cycle])
        total += expected
        frames += 1
        max_batches = max(max_batches, batches)
        max_objects = max(max_objects, sum(get('OBJECT_ACTIVE', i) for i in range(16)))
        max_catchups = max(max_catchups, word('RASTER_CATCHUPS'))
        max_replays = max(max_replays, word('RASTER_REPLAY_FRAMES'))
    deltas = sorted(set(b-a for a,b in zip(clocks, clocks[1:])))
    if deltas != [19656]:
        failures.append(['physical clock deltas', deltas])
    result = dict(frames=frames, assignments=total, initial_writes_traced=len(initial), max_objects=max_objects,
                  max_batches=max_batches, catchups=max_catchups, replay_frames=max_replays,
                  frame_cycle_deltas=deltas, compare_writes_checked=len(compare_writes),
                  service_failure_count=len(failures),
                  service_failures=failures[:20], sprite_start_miss_count=len(deadlines),
                  sprite_start_misses=deadlines[:20])
    (root / 'raster-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(failures or deadlines))


if __name__ == '__main__':
    main()
