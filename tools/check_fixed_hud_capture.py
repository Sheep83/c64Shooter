#!/usr/bin/env python3
"""Independent fixed-region matrix, stock-glyph, pixel and physical edge-motion oracle."""
import argparse
import json
import re
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
from check_scroll_capture import load_metatile_stage, make_row_codes
from mc_terrain import load_palette_config, load_colour_ram


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    args = p.parse_args()
    root = args.capture
    sym = json.loads((root/'symbols.json').read_text())
    records = json.loads((root/'frames.json').read_text())
    charset = (root/'charset.bin').read_bytes()
    stage = load_metatile_stage(root/'metatiledefs.bin', root/'stagemetatilerows.bin')
    rows = make_row_codes(*stage)
    # Private HUD glyphs 128..145: space, S, C, O, R, E, digits 0..9, F, R.
    stock = [32,19,3,15,18,5,48,49,50,51,52,53,54,55,56,57,6,18]
    HUD_DIGIT = 134
    FREE_LABEL = [144,145,133,133,128]      # "FREE " private glyphs at columns 28..32.
    # Fixed row-0 layout: cols 8..12 = live score digits; cols 28..37 = the
    # development FREE counter ("FREE " + five digits). The FREE numeric field is
    # the rolling-minimum diagnostic and only refreshes ~once/second, so its five
    # cells are trusted from screen RAM and validated structurally, not pinned to
    # a value derived from one state snapshot.
    hud_prefix = [128,128,129,130,131,132,133,128]
    def hud_row(score, free_region):
        digits = [HUD_DIGIT + int(d) for d in f'{score % 100000:05d}']
        return bytes(hud_prefix + digits + [128]*15 + list(free_region) + [128]*2)
    failures = []
    for i, source in enumerate(stock):
        if charset[(128+i)*8:(129+i)*8] != charset[source*8:(source+1)*8]:
            failures.append(['stock glyph copy', i, source])
    if set((root/'metatiledefs.bin').read_bytes()) & set(range(128,146)):
        failures.append(['terrain/HUD charset collision'])
    glyphs = [charset[c*8:(c+1)*8] for c in range(256)]
    # Mixed hires / global-multicolour render model. The playfield runs global
    # char MCM during PLAYING; terrain + turret cells are multicolour (fixed
    # colour RAM), the fixed HUD row stays hires. Palette registers come from
    # the capture's vic.bin, else from src/main.asm - never a literal here.
    cfg = load_palette_config(root)
    if not cfg.mcm_on:
        failures.append(['global char MCM not enabled during PLAYING'])
    if not (8 <= cfg.terrain_cram <= 15):
        failures.append(['terrain colour RAM not a multicolour selector 8..15', cfg.terrain_cram])
    if cfg.hud_cram & 0x08:
        failures.append(['HUD colour RAM is not hires', cfg.hud_cram])
    stage_codes = {code for r in range(stage[2]) for code in rows(r)}
    if stage_codes - set(range(160, 224)):
        failures.append(['terrain glyph outside 160..223', sorted(stage_codes - set(range(160, 224)))])
    terrain_cram_seen = set()
    turrets = 'TURRET_STATE_BEGIN' in sym
    # Turret private glyph code base (relocated out of the 160..223 terrain
    # namespace); exported as a label so this oracle carries no literal.
    tbase = sym.get('TURRET_GLYPH_BASE_CODE', 200)
    placements, ground, art = [], [], b''
    if turrets:
        data = (root/'turret-placements.bin').read_bytes()
        count = len(data)//2
        _rhi = (root/'turret-placements-hi.bin').read_bytes() if (root/'turret-placements-hi.bin').exists() else bytes(count)
        placements = [(data[i], data[count+i] + 256*(_rhi[i] if i < len(_rhi) else 0))
                      for i in range(count)]
        if not (226 <= tbase and tbase + count*4 <= 238):
            failures.append(['turret private glyphs outside 226..237', tbase, count])
        if set((root/'metatiledefs.bin').read_bytes()) & set(range(tbase,tbase+count*4)):
            failures.append(['raw terrain uses turret private glyphs'])
        art = (root/'turret-art.bin').read_bytes()
        for col,world in placements:
            ground.append(b''.join(glyphs[rows(world+dy)[col+dx]] for dy in range(2) for dx in range(2)))
        if (root/'turret-ground.bin').read_bytes() != b''.join(ground):
            failures.append(['turret underlay cache differs from stage/charset'])
    def visual_rows(world):
        codes = list(rows(world))
        for t,(col,top) in enumerate(placements):
            dy = (world-top)%stage[2]
            if dy < 2:codes[col:col+2] = [tbase+t*4+dy*2,tbase+1+t*4+dy*2]
        return codes
    def private_pixels(styles):
        return b''.join(ground[t] if style==7 else art[style*32:(style+1)*32] for t,style in enumerate(styles))
    @lru_cache(maxsize=1280)
    def expected_pixels(row, phase, hud, styles, turret_cram):
        current_glyphs = list(glyphs)
        private = private_pixels(styles)
        for c in range(len(private)//8):current_glyphs[tbase+c] = private[c*8:c*8+8]
        out = bytearray()
        for raster in range(55,247):
            if raster < 63:
                # Fixed HUD row: hires (colour RAM hud_cram) even under global MCM.
                out.extend(cfg.row_bytes(hud, raster-55, current_glyphs, cfg.hud_cram))
            elif raster < 71:
                out.extend(bytes(320*3))
            else:
                # Terrain: one fixed colour RAM value. Turret private-glyph cells
                # pulse the fourth multicolour colour (all turrets in phase).
                terrain_row, gy = divmod(raster-(64+phase),8)
                codes = visual_rows(row+terrain_row)
                cram = [turret_cram if tbase <= c < tbase+4*len(placements) else cfg.terrain_cram
                        for c in codes]
                out.extend(cfg.row_bytes(codes, gy, current_glyphs, cram))
        return Image.frombytes('RGB',(320,192),bytes(out))
    def nonzero(im):
        # RGB difference -> a binary mask: any nonzero component is a mismatch.
        r,g,b = im.split()
        return ImageChops.lighter(ImageChops.lighter(r,g),b).point(lambda v:255 if v else 0)
    clocks, phases, positions = [], [], []
    checks = hud_checks = edge_checks = wraps = max_active = max_batches = max_deferred = 0
    previous = previous_mask = None
    previous_styles, previous_origin = (), None
    previous_score = None
    delayed_scores = []
    for record in records:
        frame = record['frame']
        state = (root/f'{frame:05d}.state').read_bytes()
        bg = (root/f'{frame:05d}.bg').read_bytes()
        raster_state = (root/f'{frame:05d}.raster').read_bytes()
        turret_state = (root/f'{frame:05d}.turret').read_bytes() if turrets else b''
        ram = (root/f'{frame:05d}.ram').read_bytes()
        def get(name,index=0):
            addr = sym[name]+index
            if 0x2000 <= addr < 0x2400:return state[addr-0x2000]
            if 0x2920 <= addr < 0x3000:return bg[addr-0x2920]
            if turrets and sym['TURRET_STATE_BEGIN'] <= addr < sym['TURRET_STATE_END']:
                return turret_state[addr-sym['TURRET_STATE_BEGIN']]
            return raster_state[addr-sym['RASTER_STATE_BEGIN']]
        phase = record['physical_fine']
        # SCROLL_ROW is 16-bit little-endian once a stage exceeds 255 logical
        # rows (SCROLL_ROW_HI absent in pre-widening captures -> plain byte).
        row = get('SCROLL_ROW') + (256 * get('SCROLL_ROW_HI') if 'SCROLL_ROW_HI' in sym else 0)
        finish, live = get('BG_COARSE_FINISH'), get('LIVE_PLAN')
        styles = tuple(get('TURRET_SHOWN_STYLE',t) for t in range(len(placements)))
        if any(style>7 for style in styles):
            failures.append([frame,'uninitialized turret glyph style',styles])
            styles = tuple(min(style,7) for style in styles)
        if turrets:
            actual_charset = (root/f'{frame:05d}.charset').read_bytes()
            expected_charset = charset[:tbase*8]+private_pixels(styles)+charset[tbase*8+32*len(placements):]
            if actual_charset != expected_charset:
                failures.append([frame,'private glyph publication/charset integrity'])
        colour_ram = load_colour_ram(root, frame, cfg)
        if len(colour_ram) == 1000:
            # Ordinary terrain colour RAM is written once and never scrolled:
            # every cell below the HUD stays the one fixed multicolour value.
            # The exception is the cells currently holding a turret private
            # glyph (codes tbase..tbase+11): those pulse the fourth multicolour
            # colour (see pulseTurretColour). They must stay a valid multicolour
            # selector (bit 3 set, low 3 in 0..7) but their low 3 bits vary.
            turret_glyph_cells = {c for c in range(40, 1000)
                                  if tbase <= ram[c] < tbase + 4*len(placements)}
            # A turret changes matrix row on a coarse step; its pulse colour can
            # sit on the row it is leaving/entering for one frame. Exclude the
            # turret columns +/-1 row from the "fixed terrain colour" check.
            turret_zone = set()
            for c in turret_glyph_cells:
                mr, mc = divmod(c, 40)
                for r in (mr-1, mr, mr+1, mr+2):
                    if 1 <= r <= 24:
                        turret_zone.add(r*40 + mc)
            terrain_cells = set(colour_ram[c] for c in range(40, 1000)
                                if c not in turret_zone)
            terrain_cram_seen.update(terrain_cells)
            if terrain_cells - {cfg.terrain_cram}:
                failures.append([frame,'terrain colour RAM not fixed',sorted(terrain_cells)])
            for c in turret_glyph_cells:
                if not (colour_ram[c] & 0x08):        # bit 3 must stay set (cell stays multicolour)
                    failures.append([frame,'turret colour RAM lost the MC selector bit',c,colour_ram[c]])
            if set(colour_ram[:40]) - {cfg.hud_cram}:
                failures.append([frame,'HUD colour RAM changed',sorted(set(colour_ram[:40]))])
        score = get('SCORE_LO') + 256*get('SCORE_HI')
        free_region = ram[28:38]                       # "FREE " + five digits, or ten blanks when disabled.
        hud = hud_row(score, free_region)
        if free_region[0] == 144:                      # FREE counter enabled: validate its structure.
            if list(free_region[:5]) != FREE_LABEL:
                failures.append([frame,'FREE label',list(free_region[:5])])
            if not all(HUD_DIGIT <= b <= HUD_DIGIT+9 for b in free_region[5:]):
                failures.append([frame,'FREE digits not private glyphs',list(free_region[5:])])
        elif set(free_region) != {128}:
            failures.append([frame,'FREE area not blank',list(free_region)])
        terrain = bytearray(hud)
        for r in range(1,24):terrain.extend(visual_rows(row+r-1+(1 if finish and r>=13 else 0)))
        terrain.extend([32]*40)
        if ram[:1000] != terrain:
            failures.append([frame,'matrix',[i for i in range(1000) if ram[i] != terrain[i]][:12]])
        if finish:
            if bytes(get('BG_INCOMING_ROW',i) for i in range(40)) != bytes(rows(row)):
                failures.append([frame,'incoming buffer'])
            if bytes(get('BG_CROSSING_ROW',i) for i in range(40)) != bytes(visual_rows(row+12)):
                failures.append([frame,'crossing buffer'])
        if get('RASTER_DISPLAY_LATE'):
            failures.append([frame,'late display event',get('RASTER_DISPLAY_LATE')])
        if phase != get('RASTER_DISPLAY_FINE'):
            failures.append([frame,'display publication',phase,get('RASTER_DISPLAY_FINE')])
        if phases and phase != phases[-1] and phase != (phases[-1]+1)%8:
            failures.append([frame,'fine step',phases[-1],phase])
        if phases and phases[-1]==7 and phase==0:wraps+=1
        if positions and row != positions[-1] and row != (positions[-1]-1)%stage[2]:
            failures.append([frame,'stage step'])
        positions.append(row)
        regs = re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n',record['registers'])
        clocks.append(int(regs[3])-63*int(regs[1])-int(regs[2]))
        max_active=max(max_active,sum(get('OBJECT_ACTIVE',i) for i in range(16)))
        max_batches=max(max_batches,get('BATCH_COUNT',live))
        max_deferred=max(max_deferred,get('BG_COARSE_DEFERRED'))
        im = Image.open(root/f'{frame:05d}.png').convert('RGB').crop((32,39,352,231))
        mask = Image.new('L',(320,192))
        draw = ImageDraw.Draw(mask)
        assignments=sum(get('BATCH_ASSIGN_COUNT',live+i) for i in range(get('BATCH_COUNT',live)))
        for prefix,count in [('INITIAL',get('RENDER_COUNT',live)),('ASSIGN',assignments)]:
            for i in range(count):
                x=get(prefix+'_X',live+i)+256*get(prefix+'_X_MSB',live+i)-24
                y=get(prefix+'_Y',live+i)+1-55
                draw.rectangle((x,y,x+23,y+20),fill=255)
        # Turret private-glyph cells pulse the fourth multicolour colour (a
        # deliberate prototype). Their bitmaps are validated by the charset
        # integrity check + check_turret_capture, and their colour RAM by the
        # selector check above; exclude their pixels from the terrain diff,
        # which models one static terrain colour.
        for c in range(40,1000):
            if tbase <= ram[c] < tbase+4*len(placements):
                mrow,mcol = divmod(c,40)
                ty0 = 9+phase+(mrow-2)*8            # +/-1 matrix row for the coarse-step transient
                draw.rectangle((mcol*8, ty0-1, mcol*8+7, ty0+8+16), fill=255)
        # Never excuse HUD/separator contamination as a sprite-covered pixel.
        draw.rectangle((0,0,319,15),fill=0)
        # The five FREE digit cells (cols 33..37) are rewritten late in BUILD
        # once per ~PAL second, so on that one frame the screenshot still shows
        # the previous value. They are validated structurally (label + glyph
        # range) above; exclude them from the exact HUD pixel comparison.
        if free_region[0] == 144:
            draw.rectangle((33*8, 0, 38*8-1, 7), fill=255)
        # Turret private-glyph cells pulse the fourth multicolour colour; read
        # this frame's pulse value (all turrets pulse in phase). Fall back to the
        # fixed terrain value on builds without the pulse.
        turret_cram = get('TURRET_PULSE_COLOUR') if turrets and 'TURRET_PULSE_COLOUR' in sym else cfg.terrain_cram
        if not (turret_cram & 0x08):
            turret_cram = cfg.terrain_cram
        if frame:
            difference=nonzero(ImageChops.difference(im,expected_pixels((row+finish)%stage[2],phase,hud,styles,turret_cram)))
            difference=ImageChops.subtract(difference,mask)
            bad=difference.getbbox()
            if bad and previous_score is not None and score != previous_score:
                # A real kill can update score RAM AFTER row0's badline55 fetch.
                # Allow exactly the complete prior score for that one frame;
                # still compare every HUD pixel (no score-area exclusion).
                old_hud=hud_row(previous_score,free_region)
                old_diff=nonzero(ImageChops.difference(im,expected_pixels((row+finish)%stage[2],phase,old_hud,styles,turret_cram)))
                old_diff=ImageChops.subtract(old_diff,mask)
                if not old_diff.getbbox():
                    delayed_scores.append(frame)
                    bad=None
            if bad:failures.append([frame,'physical pixels',bad,difference.histogram()[255]])
            checks+=320*192-mask.histogram()[255]
            hud_checks+=320*16
            # Independent captured-pixel motion oracle at BOTH physical edges.
            # Newly entering row71 is checked above against stage pixels. For
            # rows72..78 and240..246, one fine step must move prior pixels down1.
            if previous is not None and phase==(phases[-1]+1)%8:
                current_edge_mask,old_edge_mask = mask.copy(),previous_mask.copy()
                for t,(col,world) in enumerate(placements):
                    if styles[t] == previous_styles[t]:continue
                    # A deliberate aim/hit/death change is still checked by the
                    # absolute pixel oracle; only its motion comparison differs.
                    for target,origin,fine in [(current_edge_mask,(row+finish)%stage[2],phase),
                                               (old_edge_mask,previous_origin,phases[-1])]:
                        offset=(world-origin)%stage[2]
                        if offset==stage[2]-1:offset=-1
                        if -1<=offset<23:
                            top=64+fine+8*offset-55
                            ImageDraw.Draw(target).rectangle((col*8,max(16,top),col*8+15,top+15),fill=255)
                for lo,hi in [(72,79),(240,247)]:
                    box=(0,lo-55,320,hi-55)
                    prevbox=(0,lo-56,320,hi-56)
                    diff=nonzero(ImageChops.difference(im.crop(box),previous.crop(prevbox)))
                    excluded=ImageChops.lighter(current_edge_mask.crop(box),old_edge_mask.crop(prevbox))
                    diff=ImageChops.subtract(diff,excluded)
                    edge_checks+=320*(hi-lo)-excluded.histogram()[255]
                    if diff.getbbox():failures.append([frame,'edge motion',lo,diff.getbbox()])
        previous,previous_mask=im,mask
        previous_styles,previous_origin=styles,(row+finish)%stage[2]
        previous_score=score
        phases.append(phase)
    deltas=sorted(set(b-a for a,b in zip(clocks,clocks[1:])))
    if deltas != [19656]:failures.append(['PAL cadence',deltas])
    if len(terrain_cram_seen) > 1:
        failures.append(['terrain colour RAM varied across run',sorted(terrain_cram_seen)])
    result=dict(frames=len(records), phases=sorted(set(phases)), coarse_transitions=wraps,
                stage_circuits=wraps/stage[2],max_active=max_active,max_batches=max_batches,
                deferred=max_deferred,frame_cycle_deltas=deltas,pixel_checks=checks,
                unmasked_hud_separator_checks=hud_checks,physical_edge_motion_checks=edge_checks,
                score_visible_next_frame=delayed_scores,
                render_model=cfg.source, char_mcm=cfg.mcm_on,
                palette_registers=dict(d021=cfg.d021,d022=cfg.d022,d023=cfg.d023),
                terrain_colour_ram=sorted(terrain_cram_seen) or [cfg.terrain_cram],
                failure_count=len(failures),failures=failures[:24])
    (root/'fixed-hud-verification.json').write_text(json.dumps(result,indent=2))
    (root/'fixed-hud-failures.json').write_text(json.dumps(failures,indent=2))
    print(json.dumps(result,indent=2))
    raise SystemExit(bool(failures))

if __name__=='__main__':main()
