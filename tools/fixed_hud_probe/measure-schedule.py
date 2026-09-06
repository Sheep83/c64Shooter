#!/usr/bin/env python3
"""Isolated investigation diagnostic; see README.md. Not a production HUD test."""
import sys,re,json,subprocess,time
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from vice_scroll_test import Monitor,symbols
out=Path('build/fixed-hud-codex/probes').resolve();s=symbols(Path('build/main.vs'))
cases={'early24':[49]+[0]*8+[36,85,121,157,193,229,255], 'player37':[49]+[0]*8+[85,121,157,193,229,255,255], 'late243':[49]+[219]*7+[255]*8, 'overlap55':[67]+[0]*8+[85,121,157,193,229,255,255]}
results=[]
for index,(name,ys) in enumerate(cases.items()):
    if len(sys.argv)>1 and name!=sys.argv[1]:continue
    port=6535+index
    proc=None
    proc=subprocess.Popen(['/opt/homebrew/bin/x64sc','-default','-pal','-warp','+sound','-remotemonitor','-remotemonitoraddress',f'ip4://127.0.0.1:{port}','-autostartprgmode','1','-autostart',str(Path('build/shooter.prg').resolve())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(2)
    m=Monitor(port);m.trace_file=(out/f'{name}-monitor.log').open('w')
    m.cmd('delete');m.cmd('resourceset "JoyPort2Device" "37"')
    m.cmd(f'break {s["waitFireRelease"]:04x}');m.cmd('jpdb 1 ef');m.cmd('x');m.cmd('jpdb 1 ff');m.cmd('delete')
    m.cmd(f'break {s["buildSortedObjectList"]:04x}');m.cmd('x')
    def put(name,values):m.cmd(f'> {s[name]:04x} '+' '.join(f'{v:02x}' for v in values))
    put('OBJECT_ACTIVE',[1]*16);put('OBJECT_Y',ys);put('OBJECT_X',[100]*16);put('OBJECT_X_MSB',[0]*16);put('OBJECT_SPRITE',[s['blankSprite']//64]*16);put('OBJECT_COLOUR',[1]*16)
    m.cmd('delete');m.cmd(f'break {s["drawHudDiagnostic"]:04x}');m.cmd('x');m.cmd('delete')
    dump=out/f'{name}.state';m.cmd(f'bsave "{dump}" 0 2000 23ff');state=dump.read_bytes()
    def get(name,i=0):return state[s[name]+i-0x2000]
    live=get('LIVE_PLAN');count=get('BATCH_COUNT',live)
    plan=[{'raster':get('BATCH_RASTER',live+i),'count':get('BATCH_ASSIGN_COUNT',live+i),'first':get('BATCH_FIRST_ASSIGN',live+i)} for i in range(count)]
    m.cmd('> d011 17') # Isolate the fixed HUD's first badline at55, no production source edits.
    m.cmd('> 6000 58 4c 01 60');m.cmd('r pc=6000')
    log=out/f'{name}-timing.log';m.cmd(f'logname "{log}"');m.cmd('log on')
    for addr in (s['multiplexIRQ'],0xea31,0xea81):m.cmd(f'trace exec {addr:04x}')
    m.cmd('break exec 0000 ffff if RL == $137');m.cmd('x');m.cmd('log off')
    results.append({'name':name,'ys':ys,'live':live,'batches':plan,'timing_log':str(log),'final_registers':m.cmd('r')})
    m.cmd('delete');m.sock.sendall(b'quit\n');m.sock.close()
    if proc:proc.wait(timeout=10)
(out/('schedule-'+sys.argv[1]+'-results.json' if len(sys.argv)>1 else 'schedule-results.json')).write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
