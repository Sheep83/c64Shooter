#!/usr/bin/env python3
"""Fresh-VICE functional/CPU probes for world turrets, separate from pixel tests."""
import argparse
import json
import re
import socket
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=6570)
    parser.add_argument('--out', type=Path, default=Path('build/bg-turret-test/functions'))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    with socket.socket() as check:
        if check.connect_ex(('127.0.0.1',args.port)) == 0:
            raise RuntimeError('Refusing occupied VICE port')
    proc = subprocess.Popen(['/opt/homebrew/bin/x64sc','-default','-pal','-warp','+sound',
        '-remotemonitor','-remotemonitoraddress',f'ip4://127.0.0.1:{args.port}',
        '-autostartprgmode','1','-autostart',str(Path('build/shooter.prg').resolve())],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(2)
    mon = Monitor(args.port)
    mon.trace_file = (out/'monitor.log').open('w')
    checks, costs = [], {}
    try:
        mon.cmd('delete')
        mon.cmd('resourceset "JoyPort2Device" "37"')
        mon.cmd(f'break {sym["waitFireRelease"]:04x}')
        mon.cmd('jpdb 1 ef')
        mon.cmd('x')
        mon.cmd('jpdb 1 ff')
        mon.cmd('delete')
        mon.cmd(f'break {sym["applyFineScroll"]:04x}')
        mon.cmd('x')
        mon.cmd('delete')
        # CPU-only subroutine probes; physical tests keep the real IRQ/display.
        mon.cmd('> d01a 00')
        mon.cmd('> dc0d 7f')
        mon.cmd('> d015 00')
        mon.cmd('> d011 00')

        def put(name, values, index=0):
            if isinstance(values,int): values=[values]
            addr = sym[name]+index if isinstance(name,str) else name+index
            mon.cmd(f'> {addr:04x} '+' '.join(f'{v:02x}' for v in values))

        def read(addr, count=1):
            if isinstance(addr,str): addr=sym[addr]
            path=out/'scratch.bin'
            mon.cmd(f'bsave "{path}" 0 {addr:04x} {addr+count-1:04x}')
            return path.read_bytes()

        def clock(reg):
            return int(re.search(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n',reg)[3])

        def call(name, x=0):
            addr=sym[name]
            # Save returned carry/X without depending on monitor register parsing.
            code=[0x78,0xd8,0xa2,x,0x20,addr&255,addr>>8,0x08,0x68,
                  0x8d,0x00,0x7e,0x8e,0x01,0x7e,0x4c,0x0f,0x70]
            put(0x7000,code)
            mon.cmd('r pc=7000, sp=ff')
            start=clock(mon.cmd('r'))
            mon.cmd('x')
            cycles=clock(mon.cmd('r'))-start
            # 6 cycles prefix + JSR6 + PHP3/PLA4/STA4/STX4 =27 outside body.
            costs.setdefault(name,[]).append(cycles-27)
            status,index=read(0x7e00,2)
            return status&1,index

        def expect(label, actual, expected):
            if actual != expected: raise AssertionError((label,actual,expected))
            checks.append(label)

        mon.cmd('break 700f')
        # Independently enumerate all origins/phases, including the99/0 footprint.
        rows=list(read('turretWorldRow',3))
        for origin in range(100):
            put('SCROLL_ROW',origin)
            for fine in range(8):
                put('RASTER_DISPLAY_FINE',fine)
                call('positionBackgroundTurrets')
                visible=read('TURRET_VISIBLE',3)
                ys=read('TURRET_Y',3)
                for t,world in enumerate(rows):
                    delta=(world-origin)%100
                    if delta==99:delta=-1
                    y=64+fine+8*delta
                    expected=int(-1<=delta<23 and 72<=y<=231)
                    assert visible[t]==expected,(origin,fine,t,'visibility')
                    if -1<=delta<23:assert ys[t]==y,(origin,fine,t,'Y')
        checks.append('all100 origins x8 phases x3 turret positions/eligibility')
        put('OBJECT_ACTIVE',[1]+[0]*15)
        put('OBJECT_TYPE',1)
        put('OBJECT_Y',240)
        put('TURRET_VISIBLE',[1,0,0])
        put('TURRET_Y',[100,100,100])
        put('TURRET_HEALTH',[3,3,3])
        tx=list(read('TURRET_X_LO',3)); th=list(read('TURRET_X_HI',3))
        x0=tx[0]+256*th[0]                      # turret 0 world X (from its authored column)
        for ray, expected in ((x0-1,255),(x0,128),(x0+15,128),(x0+16,255)):
            put('HITSCAN_X_LO',ray&255);put('HITSCAN_X_MSB',ray>>8)
            expect(f'turret ray{ray}',call('tracePlayerCannon')[1],expected)
        put('HITSCAN_X_LO',x0&255);put('HITSCAN_X_MSB',x0>>8)
        put('OBJECT_ACTIVE',1,1);put('OBJECT_TYPE',2,1)
        put('OBJECT_X',x0&255,1);put('OBJECT_X_MSB',x0>>8,1)
        for y,expected in ((80,128),(150,1),(100,1)):
            put('OBJECT_Y',y,1)
            expect(f'nearest enemy Y{y}',call('tracePlayerCannon')[1],expected)
        put('OBJECT_ACTIVE',0,1)
        put('TURRET_VISIBLE',[0,1,0])
        x1=tx[1]+256*th[1]                      # turret 1 world X
        put('HITSCAN_X_LO',(x1+4)&255);put('HITSCAN_X_MSB',(x1+4)>>8)
        expect('turret1 ninth-X-bit bbox',call('tracePlayerCannon')[1],129)
        put('TURRET_VISIBLE',[1,0,0])
        put('SCORE_LO',0);put('SCORE_HI',0)
        for hp in (2,1,0):
            call('hitCannonTarget',128)
            expect(f'damage HP{hp}',read('TURRET_HEALTH')[0],hp)
            expect(f'damage style HP{hp}',read('TURRET_DESIRED_STYLE')[0],6 if hp else 7)
        call('hitCannonTarget',128)
        expect('single kill reward',int.from_bytes(read('SCORE_LO',2),'little'),100)
        expect('one destruction',read('TURRET_DESTROYED')[0],1)
        call('publishTurretGlyphs')
        expect('death restores exact terrain glyph bytes',read(sym['TURRET_GLYPH_BASE_CODE']*8+0x3800,32),read('turretGroundGlyphs',32))
        # Body never allocates: only the player is active after all hits.
        expect('no body logical allocations',list(read('OBJECT_ACTIVE',16)),[1]+[0]*15)
        put('TURRET_HEALTH',3)
        # player X relative to turret 0: well left (<-24 deadband), centred, well right (>=+24)
        for y,offset in ((50,0),(240,3)):
            put('OBJECT_Y',y)
            for x,aim in ((x0-64,0),(x0,1),(x0+80,2)):
                put('OBJECT_X',x&255);put('OBJECT_X_MSB',x>>8)
                call('aimBackgroundTurret')
                expect(f'aim dx{x-x0} Y{y}',read('TURRET_AIM')[0],aim+offset)
        put('OBJECT_X',20);put('OBJECT_X_MSB',1)
        call('aimBackgroundTurret')
        expect('aim ninth X bit',read('TURRET_AIM')[0],5)
        put('OBJECT_X',x0&255);put('OBJECT_X_MSB',x0>>8);put('OBJECT_Y',240)
        put('PLAYER_STATE',0);put('TURRET_HIT_TIMER',[0,0,0])
        put('TURRET_FIRE_TIMER',[0,0,0]);put('ENEMY_BULLET_COUNT',0)
        call('updateBackgroundTurrets')
        expect('world turret fired',read('TURRET_SHOTS_FIRED')[0],1)
        expect('projectile logical slot1',read('OBJECT_TYPE',2),bytes([1,3]))
        expect('projectile muzzle',read(sym['OBJECT_Y']+1)[0],112)
        expect('projectile speed',read(sym['OBJECT_VEL_Y']+1)[0],3)
        for _ in range(2):expect('shared allocator success',call('spawnEnemyBulletAt')[0],0)
        expect('cap remains3',read('ENEMY_BULLET_COUNT')[0],3)
        expect('cap rejection',call('spawnEnemyBulletAt')[0],1)
        expect('slot0 retained',read('OBJECT_TYPE')[0],1)
        for slot in (1,2,3):
            put('OBJECT_Y',249,slot)
            call('moveEnemyBullet',slot)
        expect('bullet despawn releases cap',read('ENEMY_BULLET_COUNT')[0],0)
        put('OBJECT_ACTIVE',[1]*16)
        expect('full object pool rejection',call('spawnEnemyBulletAt')[0],1)
        expect('failed allocation leaves bullet count',read('ENEMY_BULLET_COUNT')[0],0)
        put('OBJECT_ACTIVE',[1]+[0]*15)
        for player_y,turret_y in ((80,100),(240,72),(240,208)):
            put('OBJECT_Y',player_y);put('TURRET_Y',turret_y);put('TURRET_FIRE_TIMER',0)
            call('updateBackgroundTurrets')
            expect(f'fire margin/player above {player_y}/{turret_y}',read('ENEMY_BULLET_COUNT')[0],0)
        put('TURRET_VISIBLE',[0,0,0])
        call('updateBackgroundTurrets')
        # Exercise maximum-index live/ground publication and queued requests.
        put('TURRET_DESIRED_STYLE',[0,1,2]);put('TURRET_SHOWN_STYLE',[0,1,0])
        call('publishTurretGlyphs')
        expect('last body publication',read('TURRET_SHOWN_STYLE',3),bytes([0,1,2]))
        put('TURRET_DESIRED_STYLE',[7,7,7])
        for _ in range(3):call('publishTurretGlyphs')
        expect('queued publication drained',read('TURRET_SHOWN_STYLE',3),bytes([7,7,7]))
        expect('all destroyed underlay exact',read(sym['TURRET_GLYPH_BASE_CODE']*8+0x3800,96),read('turretGroundGlyphs',96))
        call('initBackgroundTurrets')
        expect('new game health reset',read('TURRET_HEALTH',3),bytes([3,3,3]))
        result=dict(checks=checks,check_count=len(checks),cpu_cycles={k:dict(min=min(v),max=max(v)) for k,v in costs.items()},failures=[])
        (out/'results.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:
        mon.sock.sendall(b'quit\n')
        mon.sock.close()
        proc.wait(timeout=10)


if __name__=='__main__':main()
