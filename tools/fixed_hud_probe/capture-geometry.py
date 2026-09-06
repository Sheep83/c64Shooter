#!/usr/bin/env python3
"""Isolated investigation diagnostic; see README.md. Not a production HUD test."""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from vice_scroll_test import Monitor,symbols
from PIL import Image
out=Path('build/fixed-hud-codex/probes').resolve()
s=symbols(out/'geometry.vs')
m=Monitor(6532)
m.trace_file=(out/'geometry-monitor.log').open('w')
m.cmd('delete')
b=int(re.search(r'BREAK: (\d+)',m.cmd('break exec 0000 ffff if RL == $137'))[1])
m.cmd('x')
results=[]
reference_hud=None
for mask in range(2):
    for fine in range(8):
        m.cmd(f'> {s["mask"]:04x} {mask:02x}')
        m.cmd(f'> {s["fine"]:04x} {fine:02x}')
        for _ in range(2):
            m.cmd(f'condition {b} if RL == $000');m.cmd('x')
            m.cmd(f'condition {b} if RL == $137');m.cmd('x')
        p=out/f'geometry-{mask}-{fine}.png'
        m.cmd(f'screenshot "{p}" 2')
        im=Image.open(p).convert('RGB')
        hud=list(im.crop((32,55-16,352,63-16)).getdata())
        if reference_hud is None: reference_hud=hud
        mismatches=[]
        for raster in range(71,247):
            offset=raster-(64+fine)
            row,py=divmod(offset,8);row+=1
            byte=((row*17)^(py*13))&255
            for x in range(320):
                want=(255,255,255) if byte&(128>>(x%8)) else (0,0,0)
                if im.getpixel((x+32,raster-16))!=want:
                    if len(mismatches)<20: mismatches.append([raster,x,row,py])
        nonblack=[r for r in range(63,71) if any(im.getpixel((x,r-16))!=(0,0,0) for x in range(32,352))]
        results.append({'mask':mask,'fine':fine,'hud_mismatches':sum(a!=b for a,b in zip(hud,reference_hud)),'separator_nonblack_rasters':nonblack,'terrain_first_mismatches':mismatches})
(out/'geometry-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
m.cmd('delete');m.sock.sendall(b'x\n');m.sock.close()
