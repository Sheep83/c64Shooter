#!/usr/bin/env python3
"""Isolated investigation diagnostic; see README.md. Not a production HUD test."""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from vice_scroll_test import Monitor,symbols
from PIL import Image
out=Path('build/fixed-hud-codex/probes').resolve();s=symbols(out/'geometry.vs');m=Monitor(6533)
m.trace_file=(out/'geometry-dma-monitor.log').open('w');m.cmd('delete')
b=int(re.search(r'BREAK: (\d+)',m.cmd('break exec 0000 ffff if RL == $137'))[1]);m.cmd('x')
m.cmd('> 2000 '+ ' '.join(['00']*64));m.cmd('> 07f8 '+ ' '.join(['80']*8))
m.cmd('> d000 '+ ' '.join(['64','32']*8));m.cmd('> d017 00');m.cmd('> d01b 00 00 00')
m.cmd(f'> {s["mask"]:04x} 01');results=[]
for dma in (0,1,7,128,248,255):
    m.cmd(f'> d015 {dma:02x}')
    for fine in range(8):
        m.cmd(f'> {s["fine"]:04x} {fine:02x}')
        for _ in range(2):
            m.cmd(f'condition {b} if RL == $000');m.cmd('x')
            m.cmd(f'condition {b} if RL == $137');m.cmd('x')
        p=out/f'geometry-dma-{dma:02x}-{fine}.png';m.cmd(f'screenshot "{p}" 2')
        im=Image.open(p).convert('RGB');mismatches=[];count=0
        for raster in range(71,247):
            row,py=divmod(raster-(64+fine),8);row+=1
            byte=((row*17)^(py*13))&255
            for x in range(320):
                want=(255,255,255) if byte&(128>>(x%8)) else (0,0,0)
                if im.getpixel((x+32,raster-16))!=want:
                    count+=1
                    if len(mismatches)<12:mismatches.append([raster,x,row,py])
        leaks=[[r,sum(im.getpixel((x,r-16))!=(0,0,0) for x in range(32,352))] for r in range(63,71)]
        leaks=[v for v in leaks if v[1]]
        results.append({'dma':dma,'fine':fine,'separator_leaks':leaks,'terrain_mismatch_count':count,'terrain_first_mismatches':mismatches})
(out/'geometry-dma-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps([r for r in results if r['separator_leaks'] or r['terrain_mismatch_count']],indent=2))
print('cases',len(results),'failures',sum(bool(r['separator_leaks'] or r['terrain_mismatch_count']) for r in results))
m.cmd('delete');m.sock.sendall(b'x\n');m.sock.close()
