#!/usr/bin/env python3
"""Physical-frame coarse-admission audit; passive trace commands never stop the CPU.

Without an overlay the runtime code matches the baseline. All cases restore one
complete VICE snapshot, including CIA phase. Frame311 input writes and optional
code overlays are explicit diagnostic interventions. --plain
omits tracepoints for an observer-neutrality control. Raw branch traces and
memory dumps retain the exact LIVE generation instead of guessing from counts.
"""
import argparse
import json
import re
import socket
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

CASES=('movement','enemy-nofire','fire-no-kills','hits-kills','explosions',
       'turret-heavy','bullet-heavy','combined')
REG=re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')


def run(args, mode):
    out=(args.out/mode).resolve();out.mkdir(parents=True,exist_ok=True)
    s=symbols(args.symbols)
    with socket.socket() as check:
        if check.connect_ex(('127.0.0.1',args.port))==0:raise RuntimeError('Port occupied')
    proc=subprocess.Popen(['/opt/homebrew/bin/x64sc','-default','-pal','-warp','+sound',
        '-remotemonitor','-remotemonitoraddress',f'ip4://127.0.0.1:{args.port}',
        '-autostartprgmode','1','-autostart',str(args.prg.resolve())],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(2)
    m=Monitor(args.port)
    try:
        m.cmd('delete');m.cmd(f'undump "{args.snapshot.resolve()}"');m.cmd('delete')
        m.cmd('sidefx off')
        def put(name,values,index=0):
            if isinstance(values,int):values=[values]
            addr=s[name]+index if isinstance(name,str) else name+index
            for offset in range(0,len(values),64):
                m.cmd(f'> {addr+offset:04x} '+' '.join(f'{v&255:02x}' for v in values[offset:offset+64]))
        # Optional code-only A/B overlay; all registers/RAM/VIC/CIA state stays
        # from the common snapshot. Variant builds must preserve symbol layout.
        if args.initial_overlay:
            for row in json.loads(args.initial_overlay.read_text()):put(row['address'],row['bytes'])
        if args.overlay and args.overlay_at_frame is None:
            patch=json.loads(args.overlay.read_text())
            for row in patch:put(row['address'],row['bytes'])
        put('PLAYER_LIVES',255)
        trace_map={}
        def trace(label,addr,command=None,condition='',kind='exec',end=None):
            r=m.cmd(f'trace {kind} {addr:04x}'+(f' {end:04x}' if end is not None else '')+condition)
            ident=int(re.search(r'TRACE: (\d+)',r)[1]);trace_map[ident]=label
            if command:m.cmd(f'command {ident} "{command}"')
        if not args.plain:
            m.cmd(f'logname "{out/"timing.log"}"');m.cmd('log on')
            p=s['prepareBackgroundCoarse']
            data=args.prg.read_bytes();load=int.from_bytes(data[:2],'little')
            code=data[2+p-load:2+p-load+32]
            assert code[16]==0x90 and code[21]==0x30 and code[28]==0xb0,code.hex()
            defer=p+18+int.from_bytes(code[17:18],'little',signed=True)
            memory='; '.join(f'm {lo:04x} {hi:04x}' for lo,hi in [
                (0x30,0x45),(0x2000,0x23ff),
                (s['BG_COARSE_PENDING'],s['BG_INCOMING_ROW']+39),
                (s['RASTER_STATE_BEGIN'],s['RASTER_STATE_END']-1),
                (s['TURRET_STATE_BEGIN'],s['TURRET_STATE_END']-1)])
            trace('prepare',p)
            trace('pending_context',p,memory,f' if @ram:${s["BG_COARSE_PENDING"]:04x} != $00')
            for label,addr in [('batch_gate',p+16),('high_gate',p+21),('deadline_gate',p+28),('defer',defer)]:
                trace(label,addr,memory if label=='defer' else None)
            for name in ('positionBackgroundTurrets','updateEnemyHitEffects','updatePlayerCombatEffects',
                         'updateObjects','updateEnemyFire','updateBackgroundTurrets','updatePlayerState',
                         'updateSpawner','updateBackgroundScroll','buildSortedObjectList','sortObjectsByY',
                         'buildInitialSpriteSnapshot','buildBatchSpriteSchedule','updateCycleDebug',
                         'refreshScoreIfDirty','displayScore','displayCycleMinimum','updateEnemyHealthSprite','publishTurretGlyphs',
                         'applyFineScroll','swapRenderPlans','renderSprites','armFirstBatch',
                         'finishBackgroundCoarse','bgUpperReady','bgLowerReady','rasterFrameReset',
                         'applyLiveRasterBatch','rasterAssignmentApplied','rasterInitialApplied',
                         'rasterInitialMasksApplied','rasterBatchMasksApplied','rasterDisplayRestored',
                         'rasterBadlineRestored','tracePlayerCannon','damageEnemy','hitCannonTarget',
                         'awardKillScore','findFreeObject','spawnEnemyBullet','spawnEnemyBulletAt',
                         'startRandomWave'):
                if name in s:trace(name,s[name])
            for name,count in [('OBJECT_ACTIVE',16),('OBJECT_HEALTH',16),('TURRET_HEALTH',3),
                               ('SCORE_DIRTY',1),('TURRET_SHOTS_FIRED',1),('OBJECT_DEATH_TIMER',16)]:
                trace('store_'+name,s[name],kind='store',end=s[name]+count-1)
            trace('D012',0xd012,kind='store')
            # Fire opportunities are actual timer-expiry entries, not guesses
            # based on a later frame's visibility or bullet count.
            timer=s['TURRET_FIRE_TIMER']
            pattern=bytes([0xa9,100,0x9d,timer&255,timer>>8])
            lo=s['updateBackgroundTurrets']-load+2
            hi=s['aimBackgroundTurret']-load+2
            matches=[i for i in range(lo,hi) if data[i:i+5]==pattern]
            assert len(matches)==2,matches  # Offscreen reset first, actual expiry second.
            trace('turret_opportunity',matches[1]+load-2)
            wait=s['waitForGameFrame']
            pattern=bytes([0x20,wait&255,wait>>8])
            for i in range(s['gameLoop']-load+2,s['endGame']-load+2):
                if data[i:i+3]==pattern:trace('waitForGameFrame',i+load-2)
        (out/'trace-map.json').write_text(json.dumps(trace_map,indent=2))
        (out/'symbols.json').write_text(json.dumps(s,indent=2))
        bp=int(re.search(r'BREAK: (\d+)',m.cmd('break exec 0000 ffff if RL == $137'))[1])
        m.cmd('x')
        frames=[]
        for n in range(args.frames):
            reg=m.cmd('r');line,cycle,clock=map(int,REG.search(reg).groups())
            chunks={}
            for ext,lo,hi in [('state',0x2000,0x23ff),('ram',0x0400,0x07ff),('bg',0x2920,0x2fff),
                              ('raster',s['RASTER_STATE_BEGIN'],s['RASTER_STATE_END']-1),
                              ('turret',s['TURRET_STATE_BEGIN'],s['TURRET_STATE_END']-1)]:
                file=out/f'{n:05d}.{ext}';m.cmd(f'bsave "{file}" 0 {lo:04x} {hi:04x}')
                chunks[ext]=(lo,file.read_bytes())
            if args.pixels:
                m.cmd(f'screenshot "{out / f"{n:05d}.png"}" 2')
                for ext,lo,hi in [('charset',0x3800,0x3fff),('colour',0xd800,0xdbff),('pools',0x3000,0x37ff)]:
                    m.cmd(f'bsave "{out / f"{n:05d}.{ext}"}" 0 {lo:04x} {hi:04x}')
            def get(name,i=0):
                addr=s[name]+i
                for lo,b in chunks.values():
                    if lo<=addr<lo+len(b):return b[addr-lo]
                raise KeyError(name)
            io=m.cmd('m d010 d010')
            msb=int(re.search(r'>C:d010\s+([0-9a-fA-F]{2})',io)[1],16)
            frames.append(dict(frame=n,registers=reg,physical_fine=get('RASTER_DISPLAY_FINE'),
                physical_x_msb=msb,clock=clock-63*line-cycle,
                deferred=get('BG_COARSE_DEFERRED'),fine=get('SCROLL_FINE'),row=get('SCROLL_ROW'),
                turret_shots=get('TURRET_SHOTS_FIRED'),score=get('SCORE_LO')+256*get('SCORE_HI'),
                wave=get('WAVE_ATTACK_ID'),
                sorted=get('SORTED_COUNT'),active=sum(get('OBJECT_ACTIVE',i)!=0 for i in range(16))))
            # Same 19-frame movement cycle as the former probe; fire is HITSCAN.
            direction=[0xfe,0xfd,0xf7,0xfb,0xff][(n//19)%5]
            fire=mode in ('fire-no-kills','hits-kills','combined') or mode=='explosions' and n%120<80
            if mode in ('hits-kills','explosions'):
                candidates=[i for i in range(1,16) if get('OBJECT_ACTIVE',i) and get('OBJECT_TYPE',i)==2
                            and get('OBJECT_HEALTH',i) and 72<=get('OBJECT_Y',i)<210]
                if candidates:
                    target=max(candidates,key=lambda i:get('OBJECT_Y',i))
                    dx=get('OBJECT_X',target)+256*get('OBJECT_X_MSB',target)-4-get('OBJECT_X')-256*get('OBJECT_X_MSB')
                    direction=0xfb if dx<-2 else 0xf7 if dx>2 else 0xff
                else:direction=0xff
            if fire:direction &= 0xef
            m.cmd(f'jpdb 1 {direction:02x}')
            if mode in ('movement','turret-heavy'):
                put('SPAWN_TIMER',255);put('WAVE_GAP_TIMER',255)
            if mode in ('movement','enemy-nofire','bullet-heavy'):
                put('TURRET_FIRE_TIMER',[255]*3)
            if mode=='bullet-heavy':put('ENEMY_FIRE_TIMER',1)
            if mode=='fire-no-kills':
                for i in range(1,16):
                    if get('OBJECT_ACTIVE',i) and get('OBJECT_TYPE',i)==2 and get('OBJECT_HEALTH',i):
                        put('OBJECT_HEALTH',6,i)
                put('TURRET_HEALTH',[3]*3)
            if args.overlay and args.overlay_at_frame==n:
                for row in json.loads(args.overlay.read_text()):put(row['address'],row['bytes'])
            m.cmd(f'condition {bp} if RL == $000');m.cmd('x')
            m.cmd(f'condition {bp} if RL == $137');m.cmd('x')
            if n%500==0:
                (out/'frames.json').write_text(json.dumps(frames))
                print(mode,n,'/',args.frames,flush=True)
        (out/'frames.json').write_text(json.dumps(frames))
        for name,lo,hi in [('charset.bin',0x3800,0x3fff),('vic.bin',0xd000,0xd02f),
            ('metatiledefs.bin',s['metatileDefs'],s['METATILE_DEFS_END']-1),
            ('stagemetatilerows.bin',s['stageMetatileRows'],s['STAGE_METATILE_ROWS_END']-1),
            ('turret-placements.bin',s['turretWorldCol'],s['turretWorldXLo']-1),
            ('turret-art.bin',s['turretArt'],s['turretArtEnd']-1),
            ('turret-ground.bin',s['turretGroundGlyphs'],s['turretGroundGlyphs']+95)]:
            m.cmd(f'bsave "{out / name}" 0 {lo:04x} {hi:04x}')
        (out/'case.json').write_text(json.dumps(dict(mode=mode,plain=args.plain,frames=args.frames,
            snapshot=str(args.snapshot),overlay=str(args.overlay),initial_overlay=str(args.initial_overlay),
            overlay_at_frame=args.overlay_at_frame,pixels=args.pixels),indent=2))
        m.cmd('log off')
    finally:
        m.sock.sendall(b'quit\n');m.sock.close();proc.wait(timeout=10)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=6581)
    p.add_argument('--frames',type=int,default=6000)
    p.add_argument('--modes',default=','.join(CASES))
    p.add_argument('--out',type=Path,default=Path('build/scroll-hitch/baseline'))
    p.add_argument('--snapshot',type=Path,default=Path('build/scroll-hitch/start.vsf'))
    p.add_argument('--prg',type=Path,default=Path('build/scroll-hitch/baseline.prg'))
    p.add_argument('--symbols',type=Path,default=Path('build/scroll-hitch/baseline.vs'))
    p.add_argument('--overlay',type=Path)
    p.add_argument('--initial-overlay',type=Path,help='Optional common starting variant for a delayed matched intervention')
    p.add_argument('--overlay-at-frame',type=int,help='Apply code-only intervention after this physical frame for a matched next-frame test')
    p.add_argument('--plain',action='store_true')
    p.add_argument('--pixels',action='store_true',help='Capture screenshots, glyphs, colour RAM and sprite pools for physical oracles')
    args=p.parse_args()
    for mode in args.modes.split(','):
        if mode not in CASES:raise ValueError(mode)
        run(args,mode)


if __name__=='__main__':main()
