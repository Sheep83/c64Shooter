#!/usr/bin/env python3
"""Check the two-marker proof against independent terrain and fixed pixel positions.

Use a --physical capture from vice_scroll_test.py. Requires Pillow, like the
existing scrolling checker. Sprite-covered pixels cannot establish HUD
visibility; count and test every remaining HUD pixel instead.
"""
import argparse
import json
import re
from pathlib import Path
from PIL import Image, ImageDraw
from check_scroll_capture import load_metatile_stage, make_row_codes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    root = args.capture
    sym = json.loads((root / 'symbols.json').read_text())
    records = json.loads((root / 'frames.json').read_text())
    charset = (root / 'charset.bin').read_bytes()
    stage = load_metatile_stage(root / 'metatiledefs.bin', root / 'stagemetatilerows.bin')
    row_codes = make_row_codes(*stage)
    cells = [3*40+2, 4*40+2, 3*40+31, 4*40+31]
    markers = [[0x3c, 0x42, 0x81, 0x81, 0x81, 0x81, 0x42, 0x3c],
               [0x81, 0x42, 0x24, 0x18, 0x18, 0x24, 0x42, 0x81]]
    failures, clocks, phases, positions = [], [], [], []
    pixels_checked = hud_pixels_checked = wraps = max_active = max_batches = max_deferred = 0
    hud_visible_frames = 0
    for record in records:
        n = record['frame']
        phase = record['physical_fine']
        state = (root / f'{n:05d}.state').read_bytes()
        bg = (root / f'{n:05d}.bg').read_bytes()
        ram = (root / f'{n:05d}.ram').read_bytes()

        def get(name, index=0):
            addr = sym[name] + index
            return state[addr-0x2000] if addr < 0x2400 else bg[addr-0x2920]

        finish, row, live = get('BG_COARSE_FINISH'), get('SCROLL_ROW'), get('LIVE_PLAN')
        terrain = bytearray(c for r in range(25) for c in row_codes(row+r+(1 if finish and r >= 13 else 0)))
        if get('HUD_PATCHED'):
            saved = bytes(get('HUD_TERRAIN', i) for i in range(4))
            if saved != bytes(terrain[c] for c in cells):
                failures.append([n, 'saved terrain'])
            for c, code in zip(cells, [128+2*phase, 129+2*phase, 144+2*phase, 145+2*phase]):
                terrain[c] = code
        if ram[:1000] != terrain:
            failures.append([n, 'matrix', [i for i in range(1000) if ram[i] != terrain[i]][:12]])
        if phases and phases[-1] == 7 and phase == 0:
            wraps += 1
        if positions and row != positions[-1] and row != (positions[-1]-1) % stage[2]:
            failures.append([n, 'stage step'])
        phases.append(phase)
        positions.append(row)
        match = re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n', record['registers'])
        clocks.append(int(match[3])-int(match[1])*63-int(match[2]))
        max_active = max(max_active, sum(get('OBJECT_ACTIVE', i) for i in range(16)))
        max_batches = max(max_batches, get('BATCH_COUNT', live))
        max_deferred = max(max_deferred, get('BG_COARSE_DEFERRED'))
        if n == 0:
            continue
        im = Image.open(root / f'{n:05d}.png').convert('RGB')
        mask = Image.new('1', im.size)
        draw = ImageDraw.Draw(mask)
        assignments = sum(get('BATCH_ASSIGN_COUNT', live+i) for i in range(get('BATCH_COUNT', live)))
        for prefix, count in [('INITIAL', get('RENDER_COUNT', live)), ('ASSIGN', assignments)]:
            for i in range(count):
                x = get(prefix+'_X', live+i)+256*get(prefix+'_X_MSB', live+i)+8
                y = get(prefix+'_Y', live+i)-16
                draw.rectangle((x, y, x+23, y+21), fill=1)
        pix, masked = im.load(), mask.load()
        bad, visible_hud = [], 0
        for y in range(39, 231):
            screenrow, gy = divmod(y-(32+phase), 8)
            codes = row_codes(row+finish+screenrow)
            for x in range(32, 352):
                if masked[x, y]:
                    continue
                col, gx = divmod(x-32, 8)
                in_patch = screenrow in (3, 4) and col in (2, 31)
                if in_patch:
                    # Compute pixels directly from fixed Y=80 (image row 64),
                    # independently of the assembly's phase-glyph lookup.
                    bit = (markers[(col == 31)][y-64] >> (7-gx)) & 1 if 64 <= y < 72 else 0
                    hud_pixels_checked += 1
                    visible_hud += int(64 <= y < 72)
                else:
                    bit = (charset[codes[col]*8+gy] >> (7-gx)) & 1
                expected = (119, 83, 0) if bit else (0, 0, 0)
                pixels_checked += 1
                if pix[x, y] != expected:
                    if len(bad) < 12:
                        bad.append([x, y, list(pix[x, y]), list(expected)])
        if visible_hud:
            hud_visible_frames += 1
        if bad:
            failures.append([n, 'pixels', bad])
    gaps = sorted(set(b-a for a,b in zip(clocks, clocks[1:])))
    if gaps != [19656]:
        failures.append(['physical frame gaps', gaps])
    result = dict(frames=len(records), wraps=wraps, phases=sorted(set(phases)),
                  max_active=max_active, max_batches=max_batches, deferred=max_deferred,
                  frame_cycle_deltas=gaps, pixel_checks=pixels_checked,
                  hud_pixel_checks=hud_pixels_checked, hud_visible_frames=hud_visible_frames,
                  failure_count=len(failures), failures=failures[:20])
    (root / 'hud-verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
