#!/usr/bin/env python3
"""Build disposable, address-preserving scheduler A/B overlays; never edit src/.

Original slot reuse (+24), object-start deadlines (-12), payloads, masks and
coarse admission stay intact. Helpers in guarded diagnostic RAM add conservative
extra CPU overhead compared with a possible inline implementation.
"""
import hashlib
import json
from pathlib import Path
from vice_scroll_test import symbols

root=Path('build/scroll-hitch')
s=symbols(root/'baseline.vs');prg=(root/'baseline.prg').read_bytes();base=int.from_bytes(prg[:2],'little')
assert hashlib.sha256(prg).hexdigest()=='955708c0bdb5868c26415466d51f4fa6c2287cedbe553e8c4a518183ea9191ad','Requires the investigated baseline PRG'
lo=s['buildBatchSpriteSchedule']-base+2;hi=s['setupLivesDisplay']-base+2

def absolute(op,name):
    addr=s[name] if isinstance(name,str) else name
    return bytes([op,addr&255,addr>>8])

def locate(pattern):
    matches=[i for i in range(lo,hi) if prg[i:i+len(pattern)]==pattern]
    assert len(matches)==1,(pattern.hex(),matches)
    return matches[0]+base-2

reset=locate(absolute(0x8d,'SCHED_BATCH_SIZE'))
finish=locate(absolute(0xad,'SCHED_BATCH_LATEST')+absolute(0x9d,'BATCH_RASTER'))
# Find original LDA zeropage / CMP absolute / BCS at slotFound.
compare=locate(absolute(0xcd,'SCHED_BATCH_LATEST')+bytes([0xb0]))
assert prg[compare-base]==0xa5  # Header2: opcode2bytes before compare.
temp=prg[compare-base+1]
slot_found=compare-2
selected_init=locate(bytes([0xa9,0])+absolute(0x8d,'SCHED_SELECTED_FREE'))
selected_compare=locate(absolute(0xcd,'SCHED_SELECTED_FREE')+bytes([0x90]))
helper0=absolute(0x8d,'SCHED_BATCH_SIZE')+absolute(0x8d,0x7e10)+bytes([0x60])
helper1=(absolute(0xad,'SCHED_SELECTED_FREE')+absolute(0xcd,0x7e10)+bytes([0x90,3])+
         absolute(0x8d,0x7e10)+bytes([0xa5,temp])+absolute(0xcd,'SCHED_BATCH_LATEST')+bytes([0x60]))
prepare=s['prepareBackgroundCoarse']
assert prg[prepare-base+7:prepare-base+12] == bytes([0xa9,0])+absolute(0x8d,'BG_COARSE_PENDING')
# Diagnostic ordering only: wait for the already-mandatory row12 fetch window
# before applying ALL original admission guards. High raster exits immediately;
# neither this helper nor the existing code waits for an outstanding late batch.
helper2=(bytes([0xa9,0])+absolute(0x8d,'BG_COARSE_PENDING')+
         absolute(0xad,0xd011)+bytes([0x30,7])+absolute(0xad,0xd012)+
         bytes([0xc9,160,0x90,0xf4,0x60]))
for mode in ('asap','earliest-asap','earliest-asap-wait'):
    changes=[(reset,absolute(0x20,0x7000)),(slot_found,absolute(0x20,0x7100)+bytes([0xea,0xea])),
             (finish,absolute(0xad,0x7e10)),(0x7000,helper0),(0x7100,helper1)]
    if mode.startswith('earliest-asap'):changes += [(selected_init+1,bytes([255])),(selected_compare+3,bytes([0xb0]))]
    if mode.endswith('-wait'):
        changes += [(prepare+5,absolute(0x20,0x7200)+bytes([0xea,0xea])),(0x7200,helper2)]
    overlay=[dict(address=addr,bytes=list(code)) for addr,code in changes]
    (root/f'{mode}.json').write_text(json.dumps(overlay,indent=2))
    image=bytearray(prg)
    for addr,code in changes:image[addr-base+2:addr-base+2+len(code)]=code
    (root/f'{mode}.prg').write_bytes(image)
    print(mode,'overlay',[(hex(a),len(b)) for a,b in changes])

# Controlled A/B: CIA-derived choices otherwise change when CPU work changes.
# Both sides use the same finite tape for wave choice and shooter-scan seed.
# This is a diagnostic overlay only, never a production RNG change.
import random
rng=random.Random(19656);tape=list(range(256));rng.shuffle(tape)
def tape_reader(index):
    return (bytes([0x8a,0x48])+absolute(0xae,index)+absolute(0xbd,0x7c00)+
            absolute(0x8d,0x7e17)+absolute(0xee,index)+bytes([0x68,0xaa])+
            absolute(0xad,0x7e17)+bytes([0x60]))
wave=s['startRandomWave']
assert prg[wave-base+2:wave-base+5]==absolute(0xad,0xdc04)
start=s['updateEnemyFire']-base+2;end=s['spawnEnemyBullet']-base+2
matches=[i for i in range(start,end) if prg[i:i+3]==absolute(0xad,0xdc04)]
assert len(matches)==1
fixed=[(wave,absolute(0x20,0x7b00)),(matches[0]+base-2,absolute(0x20,0x7b40)),
       (0x7b00,tape_reader(0x7e14)),(0x7b40,tape_reader(0x7e15)),
       (0x7c00,bytes(tape)),(0x7e14,bytes([0,0]))]
(root/'random-tape.json').write_text(json.dumps([dict(address=a,bytes=list(b)) for a,b in fixed],indent=2))
