#!/usr/bin/env python3
"""Check every captured matrix and visible background pixel, including wraps."""
import argparse
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw
from mc_terrain import load_palette_config


METATILE_W = 4                          # Format constants (not stage-specific data): the 4x4 metatile
METATILE_H = 4                          # shape itself, same as decodeStageCharacterRow assumes.


def load_metatile_stage(defs_path, rows_path):
    """Ground truth for the checker: the literal metatile definitions and
    stage metatile-row IDs actually assembled into the program, read back
    from a live emulator memory dump (tools/vice_scroll_test.py bsaves
    metatileDefs/stageMetatileRows verbatim). Table sizes come from these
    dumps, never a constant typed into this file, so the checker cannot
    silently drift from the real METATILE_DEF_COUNT/STAGE_METATILE_ROWS. This
    only knows the literal definitions/IDs and the public 4x4 tile shape; it
    independently expands them with plain Python divmod, not the 6502
    addressing (single-page 8-bit index tricks, shift-based id*16) under
    test, so a bug in that addressing cannot also be present here."""
    defs_data = defs_path.read_bytes()
    tile_bytes = METATILE_W * METATILE_H
    assert len(defs_data) % tile_bytes == 0, f'{defs_path}: not a whole number of {tile_bytes}-byte tiles'
    defs = [defs_data[i:i + tile_bytes] for i in range(0, len(defs_data), tile_bytes)]

    metatiles_per_row = 40 // METATILE_W
    rows_data = rows_path.read_bytes()
    assert len(rows_data) % metatiles_per_row == 0, \
        f'{rows_path}: not a whole number of {metatiles_per_row}-ID stage rows'
    stage_rows = [rows_data[i:i + metatiles_per_row] for i in range(0, len(rows_data), metatiles_per_row)]
    for row in stage_rows:
        for tile_id in row:
            assert tile_id < len(defs), f'stage row references undefined metatile {tile_id}'

    total_logical_rows = len(stage_rows) * METATILE_H
    return stage_rows, defs, total_logical_rows


def make_row_codes(stage_rows, defs, total_logical_rows):
    metatiles_per_row = 40 // METATILE_W
    def row_codes(logical_row):
        metatile_row, internal_row = divmod(logical_row % total_logical_rows, METATILE_H)
        ids = stage_rows[metatile_row]
        out = []
        for col in range(metatiles_per_row):
            tile = defs[ids[col]]
            out.extend(tile[internal_row * METATILE_W:(internal_row + 1) * METATILE_W])
        return out
    return row_codes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--charset', type=Path, default=Path('/tmp/shooter-charset.bin'))
    args = parser.parse_args()
    root = args.capture
    sym = json.loads((root / 'symbols.json').read_text())
    records = json.loads((root / 'frames.json').read_text())
    charset = args.charset.read_bytes()
    stage_rows, defs, total_logical_rows = load_metatile_stage(
        root / 'metatiledefs.bin', root / 'stagemetatilerows.bin')
    row_codes = make_row_codes(stage_rows, defs, total_logical_rows)
    # Mixed hires / global-multicolour render model (palette registers from the
    # capture's vic.bin, else src/main.asm). Terrain cells are multicolour with
    # one fixed colour-RAM value; the fixed HUD row (when present) is hires and
    # is validated by check_fixed_hud_capture, so it is skipped here.
    cfg = load_palette_config(root)
    glyphs = [charset[c*8:(c+1)*8] for c in range(256)]
    hud_present = 'initFixedHud' in sym
    # Turret private-glyph columns are published per frame and validated
    # exhaustively by check_fixed_hud_capture / check_turret_capture; this
    # independent terrain oracle skips those 2-wide cells rather than duplicate
    # the turret glyph-publication model.
    turret_spans = []
    if (root / 'turret-placements.bin').exists():
        d = (root / 'turret-placements.bin').read_bytes()
        half = len(d) // 2
        turret_spans = list(zip(d[:half], d[half:]))
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
        expected_ram = bytes(c for row in range(25) for c in row_codes(rows[-1] + row + (1 if finish and row >= 13 else 0)))
        if 'physical_fine' not in record and ram[:1000] != expected_ram:
            failures.append({'frame': f, 'kind': 'matrix', 'offsets': [i for i in range(1000) if ram[i] != expected_ram[i]][:20]})
        if f == 0:
            continue
        # This breakpoint is before the next D011 write: image = completed prior frame.
        phase = record.get('physical_fine', fine[-2])
        top_id = rows[-1] + finish
        im = Image.open(root / f'{f:05d}.png').convert('RGB')
        pix = im.load()
        # Mask the full rectangles of sprites in the displayed LIVE plan. A
        # sprite at plan Y covers rasters Y+1..Y+21 (image rows Y-15..Y+5);
        # terrain now shares the sprites' greys/white so the box must be exact.
        live = get('LIVE_PLAN')
        boxes = []
        for prefix, count in [('INITIAL', state[sym['RENDER_COUNT']-0x2000+live]), ('ASSIGN', 8)]:
            for i in range(count):
                def plan(field): return state[sym[prefix+'_'+field]-0x2000+live+i]
                sx, sy = plan('X') + 256*plan('X_MSB') + 8, plan('Y') - 15
                boxes.append((sx, sy, sx+24, sy+21))
        mask = Image.new('1', im.size)
        draw = ImageDraw.Draw(mask)
        for x0,y0,x1,y1 in boxes:
            draw.rectangle((x0,y0,x1-1,y1-1), fill=1)
        maskpix = mask.load()
        bad = []
        top_y = 55 if hud_present else 39  # Skip the hires fixed-HUD band when present.
        for y in range(top_y, 231):  # Interior common to all fine phases.
            # Raster 71 == first scrolled terrain row (matrix row 1) under the
            # permanent 24-row RSEL=0 display; matches check_fixed_hud_capture.
            screenrow, gy = divmod(y - (48 + phase), 8)
            if screenrow < 0:
                continue
            logical = top_id + screenrow
            codes = row_codes(logical)
            skip_cols = set()
            for col, world in turret_spans:
                # +/-1 logical row: a turret changes matrix row on a coarse step
                # and its pulsed fourth colour can sit on the leaving/entering
                # row for one frame.
                if (logical - world + 1) % total_logical_rows < 4:
                    skip_cols |= {col, col + 1}
            # One fixed multicolour colour-RAM value for the whole playfield.
            row_rgb = cfg.row_bytes(codes, gy, glyphs, cfg.terrain_cram)
            for x in range(32, 352):
                if maskpix[x, y]:
                    continue
                col, gx = divmod(x - 32, 8)
                if col in skip_cols:
                    continue
                pixel_checks += 1
                expected = tuple(row_rgb[(col*8 + gx)*3:(col*8 + gx)*3 + 3])
                if tuple(pix[x, y]) != expected:
                    bad.append((x, y))
        if bad:
            failures.append({'frame': f, 'kind': 'pixels', 'count': len(bad), 'positions': bad[:12], 'fine':phase, 'top':top_id})
        if 300 <= f < 420:
            frames.append(im)
    transitions = [i for i in range(1,len(fine)) if fine[i-1] == 7 and fine[i] == 0]
    deltas = [b-a for a,b in zip(clocks,clocks[1:])]

    # Explicit stage-position continuity: every time the captured SCROLL_ROW
    # actually changes, it must have stepped back by exactly one stage row,
    # mod the true (dump-derived) row count - not zero (a duplicated
    # incoming row) and not two-or-more (a skipped one). This deliberately
    # does NOT key off the fine 7->0 "transitions" list: under --physical
    # capture, SCROLL_ROW (a RAM value) updates inside prepareBackgroundCoarse
    # well before the following frame's applyFineScroll publishes the new
    # fine value to the $D011 hardware register, so the two sequences are
    # offset by one physical-frame capture from each other. Scanning `rows`
    # directly for its own changes sidesteps that capture-timing artifact
    # and checks the real invariant: whatever SCROLL_ROW does, it is always
    # exactly one step. Independent of the matrix/pixel checks above; this
    # looks only at the position counter.
    n = total_logical_rows
    row_changes = [i for i in range(1, len(rows)) if rows[i] != rows[i-1]]
    stage_step_errors = []
    for i in row_changes:
        expected = (rows[i-1] - 1) % n
        if rows[i] != expected:
            stage_step_errors.append({'frame': records[i]['frame'], 'prev_row': rows[i-1], 'actual_row': rows[i], 'expected_row': expected})
    failures.extend({'frame': e['frame'], 'kind': 'stage_step', **e} for e in stage_step_errors)
    # A "stage loop" is a wrap through the raw table's own end (index 0 -> n-1),
    # distinct from an ordinary coarse step; several of these across a long
    # run demonstrate the end -> beginning wrap repeatedly, not just once.
    stage_loops = sum(1 for i in row_changes if rows[i] > rows[i-1])
    first_transition_ok = True
    if row_changes:
        i0 = row_changes[0]
        first_transition_ok = rows[0] < n and rows[i0] == (rows[0] - 1) % n

    report = {'frames':len(records), 'wraps':len(transitions), 'max_active':max(active), 'max_batches':max(batches), 'max_score':max(scores), 'deferred':max(deferred), 'frame_cycle_deltas':sorted(set(deltas)), 'pixel_checks':pixel_checks, 'stage_logical_rows':n, 'stage_loops':stage_loops, 'first_transition_ok':first_transition_ok, 'stage_step_errors':stage_step_errors[:10], 'failures':failures[:30], 'failure_count':len(failures)}
    (root/'verification.json').write_text(json.dumps(report,indent=2))
    if frames:
        frames[0].save(root/'continuous.gif',save_all=True,append_images=frames[1:],duration=20,loop=0)
    print(json.dumps({**report, 'failures': failures[:3]},indent=2))
    if failures or any(d != 19656 for d in deltas):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
