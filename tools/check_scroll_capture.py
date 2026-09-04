#!/usr/bin/env python3
"""Check every captured matrix and visible background pixel, including wraps."""
import argparse
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw


def row_codes(row_id):
    digits = list(range(48, 58)) + list(range(1, 7))
    row = [32] * 40
    row[1:3] = [digits[row_id >> 4], digits[row_id & 15]]
    row[6] = row[33] = 224
    row[8 + (row_id & 15)] = 225
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--charset', type=Path, default=Path('/tmp/shooter-charset.bin'))
    args = parser.parse_args()
    root = args.capture
    sym = json.loads((root / 'symbols.json').read_text())
    records = json.loads((root / 'frames.json').read_text())
    charset = args.charset.read_bytes()
    failures = []
    clocks, fine, rows, active, batches, deferred, scores = [], [], [], [], [], [], []
    frames = []
    pixel_checks = 0
    for record in records:
        f = record['frame']
        state = (root / f'{f:05d}.state').read_bytes()
        bg = (root / f'{f:05d}.bg').read_bytes()
        ram = (root / f'{f:05d}.ram').read_bytes()
        def get(name):
            addr = sym[name]
            return state[addr - 0x2000] if addr < 0x2400 else bg[addr - 0x2920]
        fine.append(record.get('physical_fine', get('SCROLL_FINE')))
        rows.append(get('SCROLL_ROW'))
        deferred.append(get('BG_COARSE_DEFERRED'))
        active.append(sum(state[sym['OBJECT_ACTIVE']-0x2000:sym['OBJECT_ACTIVE']-0x2000+16]))
        batches.append(max(get('BATCH_COUNT'),state[sym['BATCH_COUNT']-0x2000+8]))
        scores.append(get('SCORE_LO') + 256 * get('SCORE_HI'))
        match = re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n', record['registers'])
        assert match, record
        clocks.append(int(match[3]) - int(match[1])*63 - int(match[2]))
        finish = get('BG_COARSE_FINISH')
        expected_ram = bytes(c for row in range(25) for c in row_codes((rows[-1] + row + (1 if finish and row >= 13 else 0)) & 255))
        if 'physical_fine' not in record and ram[:1000] != expected_ram:
            failures.append({'frame': f, 'kind': 'matrix', 'offsets': [i for i in range(1000) if ram[i] != expected_ram[i]][:20]})
        if f == 0:
            continue
        # This breakpoint is before the next D011 write: image = completed prior frame.
        phase = record.get('physical_fine', fine[-2])
        top_id = (rows[-1] + finish) & 255
        im = Image.open(root / f'{f:05d}.png').convert('RGB')
        pix = im.load()
        # Mask the full rectangles of sprites in the displayed LIVE plan.
        # Muzzle flashes can use the same brown as the terrain.
        live = get('LIVE_PLAN')
        boxes = []
        for prefix, count in [('INITIAL', state[sym['RENDER_COUNT']-0x2000+live]), ('ASSIGN', 8)]:
            for i in range(count):
                def plan(field): return state[sym[prefix+'_'+field]-0x2000+live+i]
                sx, sy = plan('X') + 256*plan('X_MSB') + 8, plan('Y') - 16
                boxes.append((sx, sy, sx+24, sy+21))
        mask = Image.new('1', im.size)
        draw = ImageDraw.Draw(mask)
        for x0,y0,x1,y1 in boxes:
            draw.rectangle((x0,y0,x1-1,y1-1), fill=1)
        maskpix = mask.load()
        bad = []
        for y in range(39, 231):  # Interior common to all fine phases; no edge/HUD assumption.
            screenrow, gy = divmod(y - (32 + phase), 8)
            codes = row_codes((top_id + screenrow) & 255)
            for x in range(32, 352):
                if maskpix[x, y]:
                    continue
                actual = pix[x, y]
                if actual not in ((0, 0, 0), (119, 83, 0)):
                    continue  # Foreground sprite pixels; character colour is fixed brown.
                col, gx = divmod(x - 32, 8)
                bit = (charset[codes[col]*8 + gy] >> (7-gx)) & 1
                pixel_checks += 1
                if (actual != (0,0,0)) != bool(bit):
                    bad.append((x,y))
        if bad:
            failures.append({'frame': f, 'kind': 'pixels', 'count': len(bad), 'positions': bad[:12], 'fine':phase, 'top':top_id})
        if 300 <= f < 420:
            frames.append(im)
    transitions = [i for i in range(1,len(fine)) if fine[i-1] == 7 and fine[i] == 0]
    deltas = [b-a for a,b in zip(clocks,clocks[1:])]
    report = {'frames':len(records), 'wraps':len(transitions), 'max_active':max(active), 'max_batches':max(batches), 'max_score':max(scores), 'deferred':max(deferred), 'frame_cycle_deltas':sorted(set(deltas)), 'pixel_checks':pixel_checks, 'failures':failures[:30], 'failure_count':len(failures)}
    (root/'verification.json').write_text(json.dumps(report,indent=2))
    if frames:
        frames[0].save(root/'continuous.gif',save_all=True,append_images=frames[1:],duration=20,loop=0)
    print(json.dumps({**report, 'failures': failures[:3]},indent=2))
    if failures or any(d != 19656 for d in deltas):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
