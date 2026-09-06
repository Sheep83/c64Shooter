#!/usr/bin/env python3
"""Check solid-sprite viewport captures against physical pixels and logical eligibility."""
import argparse
import json
from pathlib import Path
from PIL import Image

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('capture', type=Path)
a = p.parse_args()
sym = json.loads((a.capture/'symbols.json').read_text())
records = json.loads((a.capture/'frames.json').read_text())
failures, checks, phases = [], 0, set()
for record in records[1:]:
    frame = record['frame']
    state = (a.capture/f'{frame:05d}.state').read_bytes()
    def get(name, index=0): return state[sym[name]+index-0x2000]
    live = get('LIVE_PLAN')
    # Straddlers (51..70) are rendered top-clipped; only bodies wholly above
    # raster 72 (Y < 51) own no VIC slot.
    expected_ids = {i for i in range(16) if get('OBJECT_ACTIVE', i) and 51 <= get('OBJECT_Y', i) < 246}
    count = get('RENDER_COUNT', live)
    assignments = sum(get('BATCH_ASSIGN_COUNT', live+i) for i in range(get('BATCH_COUNT', live)))
    actual_ids = {get(prefix+'_OBJECT', live+i) for prefix, n in [('INITIAL', count), ('ASSIGN', assignments)] for i in range(n)}
    if actual_ids != expected_ids:
        failures.append([frame, 'render eligibility', sorted(expected_ids), sorted(actual_ids)])
    im = Image.open(a.capture/f'{frame:05d}.png').convert('RGB')
    expected = set()
    if 'initFixedHud' in sym:
        charset = (a.capture/'charset.bin').read_bytes()
        ram = (a.capture/f'{frame:05d}.ram').read_bytes()
        expected.update((32+col*8+bit,39+line) for col in range(40) for line in range(8)
                        for bit in range(8) if charset[ram[col]*8+line] & (128>>bit))
        if im.crop((32,47,352,55)).getbbox():
            failures.append([frame, 'nonblack HUD separator'])
    for obj in expected_ids:
        x = get('OBJECT_X', obj)+256*get('OBJECT_X_MSB', obj)+8
        y = get('OBJECT_Y', obj)
        # Body rows raster y+1..y+21, but the top 71-y rows of a straddler are
        # blanked so nothing is drawn before raster 72 (raster 71 stays
        # terrain-only). d = max(0, 71-y).
        first = max(y+1, 72)
        expected.update((px, raster-16) for raster in range(first, min(y+22,247)) for px in range(x,x+24) if 32 <= px < 352)
    actual = {(x, raster-16) for raster in range(55,247) for x in range(32,352) if im.getpixel((x,raster-16)) == (255,255,255)}
    if actual != expected:
        failures.append([frame, 'white pixels', len(expected-actual), len(actual-expected), sorted(expected-actual)[:8], sorted(actual-expected)[:8]])
    # No sprite white in the terrain-guard band 55..71: expected holds only HUD
    # glyph pixels there, so any straddler pixel above raster 72 lands in
    # actual-expected above and is reported by the check just above. Record the
    # band population for the report.
    leak = sorted(px for px in (actual - expected) if px[1] < 72-16)
    if leak:
        failures.append([frame, 'sprite pixels above raster 72', leak[:12]])
    checks += 320*192
    phases.add(record['physical_fine'])
result = dict(frames=len(records)-1, phases=sorted(phases), physical_pixel_checks=checks, failure_count=len(failures), failures=failures[:12])
(a.capture/'viewport-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
raise SystemExit(bool(failures))
