#!/usr/bin/env python3
"""Isolated investigation diagnostic; see README.md. Not a production HUD test."""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from vice_scroll_test import Monitor,symbols
from PIL import Image
out=Path('build/fixed-hud-codex/probes').resolve()
s=symbols(out/'gating.vs')
m=Monitor(6531)
m.trace_file=(out/'gating-monitor.log').open('w')
m.cmd('delete')
b=int(re.search(r'BREAK: (\d+)',m.cmd('break exec 0000 ffff if RL == $137'))[1])
m.cmd('x')
results=[]
for mode in range(4):
    m.cmd(f'> {s["mode"]:04x} {mode:02x}')
    for _ in range(2):
        m.cmd(f'condition {b} if RL == $000');m.cmd('x')
        m.cmd(f'condition {b} if RL == $137');m.cmd('x')
    p=out/f'gating-{mode}.png'
    m.cmd(f'screenshot "{p}" 2')
    im=Image.open(p).convert('RGB')
    counts=[]
    for raster in range(40,85):
        count=sum(im.getpixel((x,raster-16))==(255,255,255) for x in range(108,132))
        if count: counts.append([raster,count])
    results.append({'mode':mode,'white_pixels_by_raster':counts,'registers':m.cmd('r')})
(out/'gating-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
m.cmd('delete');m.sock.sendall(b'x\n');m.sock.close()
