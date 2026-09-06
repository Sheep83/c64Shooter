#!/usr/bin/env python3
"""Independent fixed-region matrix, stock-glyph, pixel and physical edge-motion oracle."""
import argparse
import json
import re
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
from check_scroll_capture import load_metatile_stage, make_row_codes


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
    stock = [32,19,3,15,18,5,48,49,50,53]
    hud = bytes([128,128,129,130,131,132,133,128,134,135,136,137,134,134]+[128]*26)
    failures = []
    for i, source in enumerate(stock):
        if charset[(128+i)*8:(129+i)*8] != charset[source*8:(source+1)*8]:
            failures.append(['stock glyph copy', i, source])
    if set((root/'metatiledefs.bin').read_bytes()) & set(range(128,138)):
        failures.append(['terrain/HUD charset collision'])
    glyphs = [charset[c*8:(c+1)*8] for c in range(256)]
    @lru_cache(maxsize=640)
    def expected_pixels(row, phase):
        out = bytearray()
        for raster in range(55,247):
            if raster < 63:
                codes, gy, colour = hud, raster-55, bytes((255,255,255))
            elif raster < 71:
                out.extend(bytes(320*3))
                continue
            else:
                terrain_row, gy = divmod(raster-(64+phase),8)
                codes, colour = rows(row+terrain_row), bytes((119,83,0))
            for code in codes:
                bits = glyphs[code][gy]
                for bit in range(7,-1,-1):
                    out.extend(colour if bits & (1<<bit) else bytes(3))
        return Image.frombytes('RGB',(320,192),bytes(out))
    def nonzero(im):
        # RGB difference -> a binary mask: any nonzero component is a mismatch.
        r,g,b = im.split()
        return ImageChops.lighter(ImageChops.lighter(r,g),b).point(lambda v:255 if v else 0)
    clocks, phases, positions = [], [], []
    checks = hud_checks = edge_checks = wraps = max_active = max_batches = max_deferred = 0
    previous = previous_mask = None
    for record in records:
        frame = record['frame']
        state = (root/f'{frame:05d}.state').read_bytes()
        bg = (root/f'{frame:05d}.bg').read_bytes()
        raster_state = (root/f'{frame:05d}.raster').read_bytes()
        ram = (root/f'{frame:05d}.ram').read_bytes()
        def get(name,index=0):
            addr = sym[name]+index
            if 0x2000 <= addr < 0x2400:return state[addr-0x2000]
            if 0x2920 <= addr < 0x3000:return bg[addr-0x2920]
            return raster_state[addr-sym['RASTER_STATE_BEGIN']]
        phase = record['physical_fine']
        row, finish, live = get('SCROLL_ROW'), get('BG_COARSE_FINISH'), get('LIVE_PLAN')
        terrain = bytearray(hud)
        for r in range(1,24):terrain.extend(rows(row+r-1+(1 if finish and r>=13 else 0)))
        terrain.extend([32]*40)
        if ram[:1000] != terrain:
            failures.append([frame,'matrix',[i for i in range(1000) if ram[i] != terrain[i]][:12]])
        if finish:
            if bytes(get('BG_INCOMING_ROW',i) for i in range(40)) != bytes(rows(row)):
                failures.append([frame,'incoming buffer'])
            if bytes(get('BG_CROSSING_ROW',i) for i in range(40)) != bytes(rows(row+12)):
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
        # Never excuse HUD/separator contamination as a sprite-covered pixel.
        draw.rectangle((0,0,319,15),fill=0)
        if frame:
            difference=nonzero(ImageChops.difference(im,expected_pixels((row+finish)%stage[2],phase)))
            difference=ImageChops.subtract(difference,mask)
            bad=difference.getbbox()
            if bad:failures.append([frame,'physical pixels',bad,difference.histogram()[255]])
            checks+=320*192-mask.histogram()[255]
            hud_checks+=320*16
            # Independent captured-pixel motion oracle at BOTH physical edges.
            # Newly entering row71 is checked above against stage pixels. For
            # rows72..78 and240..246, one fine step must move prior pixels down1.
            if previous is not None and phase==(phases[-1]+1)%8:
                for lo,hi in [(72,79),(240,247)]:
                    box=(0,lo-55,320,hi-55)
                    prevbox=(0,lo-56,320,hi-56)
                    diff=nonzero(ImageChops.difference(im.crop(box),previous.crop(prevbox)))
                    excluded=ImageChops.lighter(mask.crop(box),previous_mask.crop(prevbox))
                    diff=ImageChops.subtract(diff,excluded)
                    edge_checks+=320*(hi-lo)-excluded.histogram()[255]
                    if diff.getbbox():failures.append([frame,'edge motion',lo,diff.getbbox()])
        previous,previous_mask=im,mask
        phases.append(phase)
    deltas=sorted(set(b-a for a,b in zip(clocks,clocks[1:])))
    if deltas != [19656]:failures.append(['PAL cadence',deltas])
    result=dict(frames=len(records), phases=sorted(set(phases)), coarse_transitions=wraps,
                stage_circuits=wraps/stage[2],max_active=max_active,max_batches=max_batches,
                deferred=max_deferred,frame_cycle_deltas=deltas,pixel_checks=checks,
                unmasked_hud_separator_checks=hud_checks,physical_edge_motion_checks=edge_checks,
                failure_count=len(failures),failures=failures[:24])
    (root/'fixed-hud-verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    raise SystemExit(bool(failures))

if __name__=='__main__':main()
