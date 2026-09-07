#!/usr/bin/env python3
"""Disposable CPU-cost experiments; original src and symbol layout stay intact.

Assemble copies of the investigated baseline routines into unused diagnostic RAM.
Variants cover health/clip caching, hidden-row copy removal, stable insertion-sort
progression, optional FREE refresh scheduling, and the original plain fast path.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from vice_scroll_test import symbols

root=Path('build/scroll-hitch')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--lean',action='store_true',help='Bypass source normalization for wholly visible sprites')
parser.add_argument('--trim',action='store_true',help='Do not copy source rows that will immediately be zeroed')
parser.add_argument('--free-defer',action='store_true',help='Keep the FREE refresh pending while a coarse transition is due')
parser.add_argument('--sort',action='store_true',help='Resume insertion sort at the next original input item')
args=parser.parse_args();suffix='-trim' if args.trim else ''
suffix += '-sort' if args.sort else ''
suffix += '-free' if args.free_defer else ''
suffix += '-lean' if args.lean else ''
s=symbols(root/'baseline.vs')
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()=='d96eb7cc60d681c9b703ac4c0fc776d7ef90ea6f','Requires the investigated baseline revision'
subprocess.run(['git','diff','--quiet','--','src/main.asm','src/variables.asm'],check=True)
src=Path('src/main.asm').read_text()
prg=(root/'baseline.prg').read_bytes();base=int.from_bytes(prg[:2],'little')
assert hashlib.sha256(prg).hexdigest()=='955708c0bdb5868c26415466d51f4fa6c2287cedbe553e8c4a518183ea9191ad','Requires the fresh baseline PRG'
# Keep these coupled to the current source; an art/layout change must fail.
for name,value in [('GAMEPLAY_SPRITE_MIN_Y','71'),('HEALTH_SPRITE_BASE','$3000'),
                   ('CLIP_SPRITE_POOL','$3400')]:
    match=re.search(r'\.const '+name+r'\s*=\s*([^\s/]+)',src)
    assert match and match[1].lower()==value,(name,match[1] if match else None)
health=src[src.index('updateEnemyHealthSprite:'):src.index('// --- Routine: storeHealthBarByte')]
health=health.replace('updateEnemyHealthSprite:','probeHealth:').replace('healthCopySource','probeCopySource').replace('healthCopyDest','probeCopyDest')
needle='    stx HEALTH_OBJECT_INDEX'
pos=health.index('\n',health.index(needle))
health=health[:pos]+'''\n    txa
    clc
    adc #HEALTH_SPRITE_BASE_PTR
    cmp OBJECT_SPRITE,x
    php                                     // Z says the original body is already in this private slot.
'''+health[pos:]
health=health.replace('    ldy #0                                  // Clone', '''    plp
    beq !bodyReady+
    ldy #0                                  // Clone''')
health=health.replace('    ldx HEALTH_OBJECT_INDEX                 // Recover','!bodyReady:\n    ldx HEALTH_OBJECT_INDEX                 // Recover')
clip=src[src.index('snapshotSpritePointer:'):src.index('// --- Routine: buildBatchSpriteSchedule')]
clip=clip.replace('snapshotSpritePointer:','probeSnapshot:').replace('buildClippedInitialSprite','probeClipped')
clip=clip.replace('OBJECT_SPRITE,x','PROBE_CLIP_SOURCE')
# X,Y and the logical object remain unchanged; only this BUILD's source key changes.
clip=clip.replace('probeSnapshot:\n','''probeSnapshot:
    lda OBJECT_SPRITE,x
    sta PROBE_CLIP_SOURCE
    cmp #HEALTH_SPRITE_BASE_PTR
    bcc !sourceReady+
    cmp #HEALTH_SPRITE_BASE_PTR + 16
    bcs !sourceReady+
    lda OBJECT_Y,x
    cmp #GAMEPLAY_SPRITE_MIN_Y - 1
    bcs !sourceReady+                        // Depth0/1 may show health pixels: keep original mutable source.
    lda OBJECT_BASE_SPRITE,x
    sta PROBE_CLIP_SOURCE                    // Depth>=2 conceals exactly the only modified rows.
!sourceReady:
''')
if args.lean:
    # Preserve the original fast path for every sprite wholly inside the
    # aperture. Only a genuine straddler needs the effective-source key.
    first=clip.index('    lda OBJECT_Y,x\n    cmp #GAMEPLAY_SPRITE_MIN_Y\n')
    end=clip.index('\n',clip.index('    bcs !plain+',first))+1
    clip=clip[:first]+clip[end:]
    clip=clip.replace('probeSnapshot:\n','probeSnapshot:\n    lda OBJECT_Y,x\n    cmp #GAMEPLAY_SPRITE_MIN_Y\n    bcs !plain+\n',1)
    plain=clip.index('!plain:')
    clip=clip[:plain]+clip[plain:].replace('    lda PROBE_CLIP_SOURCE','    lda OBJECT_SPRITE,x',1)
if args.trim:
    begin=clip.index('    ldy #62                                 // New bitmap')
    end=clip.index('\n!record:',begin)
    clip=clip[:begin]+'''    lda #0
    ldy CLIP_DEPTH_BYTES
!blank:
    dey
    sta (CLIP_DST),y
    bne !blank-
    ldy CLIP_DEPTH_BYTES                    // Hidden rows already have their final zero value.
!copy:
    lda (CLIP_SRC),y
    sta (CLIP_DST),y
    iny
    cpy #63
    bne !copy-
'''+clip[end:]
# Existing #plain must always publish the real object pointer (the normalizer
# intentionally only changes sources at Y<71, so equivalence still holds).
constants='''
.const GAMEPLAY_SPRITE_MIN_Y = 71
.const HEALTH_SPRITE_BASE_PTR = $c0
.const CLIP_SPRITE_POOL_PTR = $d0
.const CLIP_SPRITE_POOL = $3400
.label PROBE_CLIP_SOURCE = $7e12
'''
constants += '\n'.join(re.findall(r'^\.var (?:TEXT_(?:SRC|DST)|TEMP_OBJECT\s|TEMP_SORT_Y\s|VIC_CONTROL_1\s|RASTER\s).*$', Path('src/variables.asm').read_text(), re.M)) + '\n'
aliases='\n'.join(f'.label {name} = ${addr:04x}' for name,addr in s.items())
sort=src[src.index('sortObjectsByY:'):src.index('// --- Routine: buildInitialSpriteSnapshot')]
sort=sort.replace('sortObjectsByY:', 'probeSort:').replace('!outer:\n', '!outer:\n    sty $7e13\n')
sort=sort.replace('!next:\n    iny', '!next:\n    ldy $7e13\n    iny',1)
sort=sort.replace('    iny                                     // Increment Y by one.\n    iny                                     // Increment Y by one.', '    iny                                     // Advance past the original input item.')
free=src[src.index('updateCycleDebug:'):src.index('// --- Routine: displayCycleMinimum')]
free=free.replace('updateCycleDebug:', 'probeFree:')
free=free.replace('.if (DEBUG_SHOW_FREE_CYCLES == 1) {', """    lda BG_COARSE_PENDING
    beq !format+
    lda #DEBUG_FRAMES - 1
    sta DEBUG_FRAME_COUNT
    jmp !sample+
!format:
.if (DEBUG_SHOW_FREE_CYCLES == 1) {""",1)
constants+='\n.const DEBUG_FRAMES=50\n.const DEBUG_SHOW_FREE_CYCLES=1\n'
asm=aliases+'\n'+constants+'\n*=$7300\n'+health+'\nprobeHealthEnd:\n*=$7500\n'+clip+'\nprobeClipEnd:\n*=$7800\n'+sort+'\nprobeSortEnd:\n*=$7900\n'+free+'\nprobeFreeEnd:\n'
path=root/f'cpu-ab{suffix}.asm';path.write_text(asm)
subprocess.run(['java','-jar','/Users/brianmorrice/dev/tools/kickassembler/KickAss.jar',str(path),
 '-odir',str(root.resolve()),'-o',str((root/f'cpu-ab{suffix}.prg').resolve()),'-vicesymbols'],check=True)
a=symbols(root/f'cpu-ab{suffix}.vs');code=(root/f'cpu-ab{suffix}.prg').read_bytes();origin=int.from_bytes(code[:2],'little')
assert a['probeHealthEnd']<=0x7500 and a['probeClipEnd']<=0x7800
patches={}
for mode,entry,new,end in [('health-cache','updateEnemyHealthSprite','probeHealth','probeHealthEnd'),
                           ('clip-source','snapshotSpritePointer','probeSnapshot','probeClipEnd')]:
 addr=a[new];patches[mode]=[dict(address=s[entry],bytes=[0x4c,addr&255,addr>>8]),
                           dict(address=addr,bytes=list(code[2+addr-origin:2+a[end]-origin]))]
addr=a['probeSort'];sort_patch=[dict(address=s['sortObjectsByY'],bytes=[0x4c,addr&255,addr>>8]),dict(address=addr,bytes=list(code[2+addr-origin:2+a['probeSortEnd']-origin]))]
assert a['probeSortEnd'] < 0x7900
(root/'sort-only.json').write_text(json.dumps(sort_patch,indent=2))
addr=a['probeFree'];free_patch=[dict(address=s['updateCycleDebug'],bytes=[0x4c,addr&255,addr>>8]),dict(address=addr,bytes=list(code[2+addr-origin:2+a['probeFreeEnd']-origin]))]
assert a['probeFreeEnd']<0x7b00
(root/'free-defer-only.json').write_text(json.dumps(free_patch,indent=2))
for mode,patch in [*patches.items(),('cpu-cache',patches['health-cache']+patches['clip-source'])]:
 if args.sort:patch=patch+sort_patch
 if args.free_defer:patch=patch+free_patch
 mode+=suffix
 (root/f'{mode}.json').write_text(json.dumps(patch,indent=2))
 image=bytearray(prg)
 for row in patch:
  at=row['address']-base+2;image[at:at+len(row['bytes'])]=bytes(row['bytes'])
 (root/f'{mode}.prg').write_bytes(image)
 print(mode,[(hex(r['address']),len(r['bytes'])) for r in patch])
