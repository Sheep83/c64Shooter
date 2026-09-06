#!/usr/bin/env python3
"""Measure physical edge continuity from pairs of PAL screenshots.

Unlike the terrain oracle, the temporal test does not decode a screen row or
read a character bitmap. On a one-pixel scroll it compares each observed
pixel to the observed pixel immediately above it in the previous frame.
Only sprite-covered samples and the newly entering top scanline are excluded.
Known 25-row idle-window discontinuities are counted separately from errors.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from PIL import Image, ImageDraw
from check_scroll_capture import load_metatile_stage, make_row_codes
from mc_terrain import load_palette_config

# Visible aperture of the production build. The engine now runs RSEL=0 (24-row)
# permanently (docs/scroll-edge-investigation.md), so the border comparisons sit
# at raster 55/246 instead of the 25-row 51/250. Only check_capture() hard-codes
# this; check_geometry() already parameterises it from each probe frame's rsel.
APERTURE_TOP, APERTURE_BOTTOM = 55, 246


def sprite_mask(root, sym, frame, size):
    state = (root / f'{frame:05d}.state').read_bytes()

    def get(name, index=0):
        return state[sym[name] + index - 0x2000]

    live = get('LIVE_PLAN')
    assignments = sum(get('BATCH_ASSIGN_COUNT', live+i) for i in range(get('BATCH_COUNT', live)))
    mask = Image.new('1', size)
    draw = ImageDraw.Draw(mask)
    for prefix, count in [('INITIAL', get('RENDER_COUNT', live)), ('ASSIGN', assignments)]:
        for i in range(count):
            x = get(prefix+'_X', live+i) + 256*get(prefix+'_X_MSB', live+i) + 8
            y = get(prefix+'_Y', live+i) - 16
            draw.rectangle((x, y, x+23, y+21), fill=1)
    return mask


def check_capture(root):
    records = json.loads((root / 'frames.json').read_text())
    sym = json.loads((root / 'symbols.json').read_text())
    charset = (root / 'charset.bin').read_bytes()
    stage = load_metatile_stage(root / 'metatiledefs.bin', root / 'stagemetatilerows.bin')
    row_codes = make_row_codes(*stage)
    # Mixed hires / global-multicolour render model. Terrain cells are
    # multicolour (one fixed colour-RAM value); palette registers come from the
    # capture's vic.bin, else src/main.asm.
    cfg = load_palette_config(root)
    glyphs = [charset[c*8:(c+1)*8] for c in range(256)]
    hud_present = 'initFixedHud' in sym
    total_logical_rows = stage[2]
    turret_spans = []
    if (root / 'turret-placements.bin').exists():
        d = (root / 'turret-placements.bin').read_bytes()
        half = len(d) // 2
        turret_spans = list(zip(d[:half], d[half:]))  # published turret glyph cells; skipped here.
    stats = defaultdict(lambda: dict(pairs=0, checks=0, differences=0, raster_rows=defaultdict(int)))
    failures, examples = [], []
    spatial_checks = 0
    previous = None
    for record in records:
        n, phase = record['frame'], record['physical_fine']
        im = Image.open(root / f'{n:05d}.png').convert('RGB')
        if im.size != (384, 272):
            raise ValueError('Expected the default PAL 384x272 crop (raster origin 16)')
        mask = sprite_mask(root, sym, n, im.size)
        if previous is not None:
            # Complement (do not replace) the image-to-image test with exact
            # edge pixels: border, idle gaps, and fetched character data.
            state = (root / f'{n:05d}.state').read_bytes()
            bg = (root / f'{n:05d}.bg').read_bytes()
            row = state[sym['SCROLL_ROW']-0x2000]
            finish = bg[sym['BG_COARSE_FINISH']-0x2920]
            pix, masked = im.load(), mask.load()
            bad = []
            for raster in list(range(44, 71)) + list(range(231, 260)):
                border = not APERTURE_TOP <= raster <= APERTURE_BOTTOM
                # Raster 71 is the first scrolled terrain line (matrix row 1)
                # under the permanent 24-row RSEL=0 display; 55..70 are the fixed
                # hires HUD + separator band (owned by check_fixed_hud_capture).
                screenrow, gy = divmod(raster - 64 - phase, 8)
                hud_band = not border and (raster < 71 or screenrow < 0)
                active = not border and not hud_band
                skip_cols = set()
                if active:
                    logical = row+finish+screenrow
                    codes = row_codes(logical)
                    row_rgb = cfg.row_bytes(codes, gy, glyphs, cfg.terrain_cram)
                    for col, world in turret_spans:
                        if (logical - world) % total_logical_rows < 2:
                            skip_cols |= {col, col + 1}
                y = raster-16
                for x in range(32, 352):
                    if hud_band:
                        continue
                    if not border and masked[x, y]:
                        continue
                    col, gx = divmod(x-32, 8)
                    if active and col in skip_cols:
                        continue
                    expected = (0, 0, 0)  # Current engine has black border/background.
                    if active:
                        expected = tuple(row_rgb[(col*8 + gx)*3:(col*8 + gx)*3 + 3])
                    spatial_checks += 1
                    if tuple(pix[x, y]) != expected and len(bad) < 12:
                        bad.append([x, raster, list(pix[x, y]), list(expected)])
            if bad:
                failures.append([n, 'edge spatial pixels', bad])
        if previous is not None:
            old, oldmask, oldphase, oldframe = previous
            if phase == oldphase:
                dy = 0
            elif phase == (oldphase+1) % 8:
                dy = 1
            else:
                failures.append([n, 'unexpected phase step', oldphase, phase])
                previous = im, mask, phase, n
                continue
            key = f'{oldphase}->{phase}'
            pix, oldpix, m, om = im.load(), old.load(), mask.load(), oldmask.load()
            for edge, first, last in [('top', 51, 70), ('bottom', 231, 250)]:
                stat = stats[key+':'+edge]
                stat['pairs'] += 1
                unexpected = []
                for raster in range(first, last+1):
                    if not APERTURE_TOP <= raster <= APERTURE_BOTTOM:
                        continue  # 24-row crop: this scanline is border, not a scrolled row.
                    if hud_present and raster < 71:
                        continue  # Fixed hires HUD + separator band: does not scroll.
                    if raster-dy < APERTURE_TOP:
                        continue  # One genuinely new pixel row may enter through the border.
                    y = raster-16
                    # Turret private glyphs are republished on aim/hit/death; that
                    # deliberate content change is covered by check_fixed_hud_capture
                    # and check_turret_capture, not by this motion comparison.
                    turret_x = set()
                    if turret_spans:
                        logical = row + finish + (raster - 64 - phase) // 8
                        for tcol, tworld in turret_spans:
                            if (logical - tworld) % total_logical_rows < 2:
                                turret_x |= {32 + tcol*8 + k for k in range(16)}
                    for x in range(32, 352):
                        if x in turret_x:
                            continue
                        if m[x, y] or om[x, y-dy]:
                            continue
                        stat['checks'] += 1
                        if pix[x, y] == oldpix[x, y-dy]:
                            continue
                        stat['differences'] += 1
                        stat['raster_rows'][raster] += 1
                        geometry_pop = oldphase == 7 and phase == 0 and (
                            52 <= raster <= 55 or 248 <= raster <= 250)
                        if not geometry_pop and len(unexpected) < 12:
                            unexpected.append([x, raster])
                if unexpected:
                    failures.append([oldframe, n, edge, unexpected])
            if oldphase == 7 and phase == 0:
                examples.append([oldframe, n])
        previous = im, mask, phase, n
    result = dict(frames=len(records), phases=sorted({r['physical_fine'] for r in records}),
                  edge_spatial_checks=spatial_checks,
                  coarse_pairs=len(examples), coarse_examples=examples[:8],
                  temporal=dict(stats), unexpected_failure_count=len(failures), failures=failures[:20])
    (root / 'edge-verification.json').write_text(json.dumps(result, indent=2))
    if examples:
        # Retain magnified, unaltered edge pixels around the first coarse step.
        # Phase ordering is chronological: 4,5,6,7,0,1,2,3.
        pivot = examples[0][1]
        selected = []
        for phase in (4, 5, 6, 7):
            candidates = [r for r in records if r['frame'] < pivot and r['physical_fine'] == phase]
            if candidates:
                selected.append(candidates[-1])
        for phase in range(4):
            candidates = [r for r in records if r['frame'] >= pivot and r['physical_fine'] == phase]
            if candidates:
                selected.append(candidates[0])
        sheet = Image.new('RGB', (1380, 30+60*len(selected)), '#202020')
        draw = ImageDraw.Draw(sheet)
        draw.text((85, 8), f'TOP: rasters 47..70 (display starts {APERTURE_TOP})', fill='white')
        draw.text((740, 8), f'BOTTOM: rasters 231..254 (display ends {APERTURE_BOTTOM})', fill='white')
        for index, record in enumerate(selected):
            y = 30+60*index
            draw.text((4, y+8), f"fine {record['physical_fine']}\nframe {record['frame']}", fill='white')
            source = Image.open(root / f"{record['frame']:05d}.png").convert('RGB')
            for x, first in ((85, 47), (740, 231)):
                crop = source.crop((32, first-16, 352, first-16+24))
                sheet.paste(crop.resize((640, 48), Image.Resampling.NEAREST), (x, y))
        sheet.save(root / 'edge-phases.png')
    brief = {k:v for k,v in result.items() if k not in ('temporal', 'failures')}
    brief['differences'] = {k:dict(v['raster_rows']) for k,v in stats.items() if v['differences']}
    brief['failures'] = failures[:3]
    print(json.dumps(brief, indent=2))
    return bool(failures)


def check_geometry(root):
    records = json.loads((root / 'frames.json').read_text())
    result, failures = [], []
    white, black, blue = (255, 255, 255), (0, 0, 0), (44, 61, 236)
    for record in records:
        rsel, phase = record['rsel'], record['fine']
        im = Image.open(root / record['image']).convert('RGB')
        top, bottom = (51, 250) if rsel else (55, 246)
        terrain_lines, idle_lines = [], []
        for raster in range(44, 260):
            expected = blue if not top <= raster <= bottom else (
                white if 48+phase <= raster <= 247+phase else black)
            # Check all 40 rails rather than a single potentially accidental pixel.
            for col in range(40):
                actual = im.getpixel((35+8*col, raster-16))
                if actual != expected:
                    failures.append([record['image'], col, raster, actual, expected])
            actual = im.getpixel((35, raster-16))
            if actual == white:
                terrain_lines.append(raster)
            elif actual == black:
                idle_lines.append(raster)
        result.append(dict(rsel=rsel, fine=phase, terrain_first=min(terrain_lines),
                           terrain_last=max(terrain_lines), idle_lines=idle_lines))
    summary = dict(geometries=result, failure_count=len(failures), failures=failures[:20])
    (root / 'geometry-verification.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return bool(failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--geometry', action='store_true', help='Check a vice_edge_probe.py capture')
    args = parser.parse_args()
    raise SystemExit(check_geometry(args.capture) if args.geometry else check_capture(args.capture))


if __name__ == '__main__':
    main()
