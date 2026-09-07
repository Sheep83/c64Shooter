#!/usr/bin/env python3
"""Byte-exact health/clip cache audit in fresh VICE, with CPU timing isolated.

Calls real NMOS routines with display/IRQs disabled. This is a bitmap equivalence
check, not a substitute for physical raster/pixel regression in running gameplay.
"""
import argparse
import json
import re
import random
import socket
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,default=6584)
p.add_argument('--overlay',type=Path,default=Path('build/scroll-hitch/cpu-cache.json'))
p.add_argument('--out',type=Path,default=Path('build/scroll-hitch/cpu-cases'))
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);a.out=a.out.resolve()
s=symbols(Path('build/scroll-hitch/baseline.vs'))
with socket.socket() as check:
 assert check.connect_ex(('127.0.0.1',a.port))!=0,'Port occupied'
proc=subprocess.Popen(['/opt/homebrew/bin/x64sc','-default','-pal','-warp','+sound',
 '-remotemonitor','-remotemonitoraddress',f'ip4://127.0.0.1:{a.port}',
 '-autostartprgmode','1','-autostart',str(Path('build/scroll-hitch/baseline.prg').resolve())],
 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(2);m=Monitor(a.port)
try:
 m.cmd('delete');m.cmd(f'undump "{Path("build/scroll-hitch/start.vsf").resolve()}"');m.cmd('delete')
 def put(name,data,index=0):
  if isinstance(data,int):data=[data]
  addr=s[name]+index if isinstance(name,str) else name+index
  for offset in range(0,len(data),64):
   m.cmd(f'> {addr+offset:04x} '+' '.join(f'{b:02x}' for b in data[offset:offset+64]))
 def get(addr,n):
  file=a.out/'read.bin';m.cmd(f'bsave "{file}" 0 {addr:04x} {addr+n-1:04x}');return file.read_bytes()
 for patch in json.loads(a.overlay.read_text()):put(patch['address'],patch['bytes'])
 put(0xd01a,0);put(0xd015,0);put(0xd011,0);put(0xdc0d,127);m.cmd('m dc0d dc0d')
 m.cmd('break 7d04')
 def call(name,x=0,y=0):
  addr=s[name];put(0x7d00,[0x78,0x20,addr&255,addr>>8,0x4c,4,0x7d])
  m.cmd(f'r pc=7d00, sp=ff, x={x:02x}, y={y:02x}')
  before=int(re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n',m.cmd('r'))[3])
  m.cmd('x');after=int(re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n',m.cmd('r'))[3]);return after-before
 art=[s['enemySpriteA']//64,s['enemySpriteB']//64]
 sources={ptr:get(ptr*64,64) for ptr in art}
 bars=[get(s['healthBarByte'+str(i)],7) for i in range(3)]
 failures=[];health_cycles=[];clip_cycles=[];cases=0
 # Reuse cache slots across depth changes, HP changes, object identity and base
 # art changes. Depth1 must retain row1's health bar; depth2..20 must match the
 # same actual mutable source after its top rows are zeroed.
 for obj in (1,7,15):
  for slot in (0,7,8,15):
   put('CLIP_SHADOW_PTR',[0]*16);put('CLIP_SHADOW_D',[0]*16)
   for ptr in art:
    put('OBJECT_BASE_SPRITE',ptr,obj);put('OBJECT_SPRITE',ptr,obj)
    for depth in list(range(20,-1,-1))+list(range(0,21)):
     hp=1+(cases%5)
     put('OBJECT_HEALTH',hp,obj)
     health_cycles.append(call('updateEnemyHealthSprite',obj))
     expected=bytearray(sources[ptr]);expected[:6]=bytes([bars[i][hp] for i in range(3)]*2)
     actual=get((192+obj)*64,64)
     if actual!=expected:failures.append([cases,'health',obj,ptr,hp])
     put('OBJECT_Y',71-depth,obj);put('SNAPSHOT_INDEX',slot)
     put('CLIP_FULL_BUDGET',8)
     clip_cycles.append(call('snapshotSpritePointer',obj,slot))
     want=bytes(depth*3)+expected[depth*3:63]
     actual=get(0x3400+slot*64,63)
     if depth and actual!=want:failures.append([cases,'clip',obj,slot,ptr,hp,depth])
     if get(s['OBJECT_SPRITE']+obj,1)!=bytes([192+obj]):failures.append([cases,'logical pointer changed'])
     if get(s['INITIAL_SPRITE']+slot,1)!=bytes([208+slot if depth else 192+obj]):failures.append([cases,'BUILD pointer'])
     cases+=1
 sort_results=[]
 patch_rows=json.loads(a.overlay.read_text())
 sort_entry=next((row['bytes'] for row in patch_rows if row['address']==s['sortObjectsByY']),None)
 if sort_entry:
  baseline=Path('build/scroll-hitch/baseline.prg').read_bytes();load=int.from_bytes(baseline[:2],'little')
  original=list(baseline[2+s['sortObjectsByY']-load:5+s['sortObjectsByY']-load])
  rng=random.Random(19656)
  for trial in range(340):
   count=trial%17;ids=list(range(16));rng.shuffle(ids);ids=ids[:count]
   ys=[rng.randrange(51,246) if trial%2 else rng.choice([71,100,150,220]) for _ in range(16)]
   want=bytes(sorted(ids,key=lambda i:ys[i]))
   times=[]
   for entry in (original,sort_entry):
    put('sortObjectsByY',entry);put('SORTED_COUNT',count);put('SORTED_OBJECTS',ids+[0]*(16-count));put('OBJECT_Y',ys)
    times.append(call('sortObjectsByY'))
    if count and get(s['SORTED_OBJECTS'],count)!=want:failures.append([trial,'stable sort',entry==sort_entry])
   sort_results.append(times)
 result=dict(cases=cases,sort_cases=len(sort_results),
  sort_cpu_cycles= dict(baseline_max=max((v[0] for v in sort_results),default=0),optimized_max=max((v[1] for v in sort_results),default=0),max_saved=max((v[0]-v[1] for v in sort_results),default=0)),failure_count=len(failures),failures=failures[:30],
  health_cpu_cycles=dict(min=min(health_cycles),max=max(health_cycles)),
  clip_cpu_cycles=dict(min=min(clip_cycles),max=max(clip_cycles)),overlay=str(a.overlay))
 (a.out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
 if failures:raise SystemExit(1)
finally:
 m.sock.sendall(b'quit\n');m.sock.close();proc.wait(timeout=10)
