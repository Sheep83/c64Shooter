#!/usr/bin/env python3
"""Isolated investigation diagnostic; see README.md. Not a production HUD test."""
import json,re
from pathlib import Path
root=Path('build/fixed-hud-codex')
results={}
for case in ('baseline','baseline-stress'):
    path=root/case;s=json.loads((path/'symbols.json').read_text());events=[]
    pattern=r'#\d+ \(Trace  exec ([0-9a-f]+)\)\s+(\d+)/\$[0-9a-f]+,\s+(\d+)/\$[0-9a-f]+\n\.C:[^\n]*? (\d+)\n'
    for m in re.finditer(pattern,(path/'timing.log').read_text()):events.append(tuple(int(x,16) if i==0 else int(x) for i,x in enumerate(m.groups())))
    timing={}
    for first,last in [('shiftBackgroundUpper','bgUpperCopied'),('shiftBackgroundUpper','bgUpperReady'),('shiftBackgroundLower','bgLowerReady')]:
        spans=[];start=None
        for e in events:
            if e[0]==s[first]:start=e
            if e[0]==s[last] and start:
                spans.append((start,e));start=None
        timing[first+'..'+last]={'count':len(spans),'entry_raster_minmax':[min(v[0][1] for v in spans),max(v[0][1] for v in spans)],'exit_raster_minmax':[min(v[1][1] for v in spans),max(v[1][1] for v in spans)],'elapsed_cycle_minmax':[min(v[1][3]-v[0][3] for v in spans),max(v[1][3]-v[0][3] for v in spans)]} if spans else {}
    records=json.loads((path/'frames.json').read_text());bad=[];playerstates={};deferframes=[];lastdefer=0
    for rec in records:
        n=rec['frame'];state=(path/f'{n:05d}.state').read_bytes();bg=(path/f'{n:05d}.bg').read_bytes();ram=(path/f'{n:05d}.ram').read_bytes()
        def get(name,i=0):
            a=s[name]+i;return state[a-0x2000] if a<0x2400 else bg[a-0x2920]
        live=get('LIVE_PLAN');count=get('RENDER_COUNT',live);ptr=[get('INITIAL_SPRITE',live+i) for i in range(count)]
        assign=sum(get('BATCH_ASSIGN_COUNT',live+i) for i in range(get('BATCH_COUNT',live)))
        for i in range(assign):ptr[get('ASSIGN_SLOT',live+i)]=get('ASSIGN_SPRITE',live+i)
        if ram[1016:1016+count]!=bytes(ptr):bad.append(n)
        ps=get('PLAYER_STATE');playerstates[ps]=playerstates.get(ps,0)+1
        d=get('BG_COARSE_DEFERRED')
        if d!=lastdefer:deferframes.append({'frame':n,'fine':rec['physical_fine'],'counter':d});lastdefer=d
    results[case]={'timing':timing,'pointer_mismatch_frames':bad,'player_state_counts':playerstates,'defer_frames':deferframes}
(root/'baseline-extra-results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
