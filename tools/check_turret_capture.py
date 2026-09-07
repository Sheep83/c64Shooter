#!/usr/bin/env python3
"""Audit turret lifetime/coordinates across real physical captures and report FREE."""
import argparse
import json
import statistics
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--require-wrap-deaths',action='store_true')
    args=parser.parse_args()
    root=args.capture
    sym=json.loads((root/'symbols.json').read_text())
    records=json.loads((root/'frames.json').read_text())
    placement=(root/'turret-placements.bin').read_bytes()
    count=len(placement)//2
    rows=placement[count:]
    stage_rows=len((root/'stagemetatilerows.bin').read_bytes())//10*4
    failures=[]
    previous_hp=[3]*count
    previous_visible=[0]*count
    dead_since=[None]*count
    dead_reentries=[0]*count
    hit_styles=set()
    deaths=[]
    samples={name:[] for name in ('offscreen','visible','firing')}
    displayed=[]
    previous_shots=0
    coarse=0
    previous_phase=None
    deferrals=0
    previous_deferred=0
    for record in records:
        n=record['frame']
        state=(root/f'{n:05d}.state').read_bytes()
        turret=(root/f'{n:05d}.turret').read_bytes()
        bg=(root/f'{n:05d}.bg').read_bytes()
        ram=(root/f'{n:05d}.ram').read_bytes()
        def get(name,i=0):
            addr=sym[name]+i
            if 0x2000<=addr<0x2400:return state[addr-0x2000]
            if 0x2920<=addr<0x3000:return bg[addr-0x2920]
            return turret[addr-sym['TURRET_STATE_BEGIN']]
        phase=record['physical_fine']
        origin=(get('SCROLL_ROW')+get('BG_COARSE_FINISH'))%stage_rows
        if previous_phase==7 and phase==0:coarse+=1
        previous_phase=phase
        deferred=get('BG_COARSE_DEFERRED')
        deferrals+=(deferred-previous_deferred)%256
        previous_deferred=deferred
        for t,world in enumerate(rows):
            hp,visible,y,style=(get(name,t) for name in ('TURRET_HEALTH','TURRET_VISIBLE','TURRET_Y','TURRET_SHOWN_STYLE'))
            delta=(world-origin)%stage_rows
            if delta==stage_rows-1:delta=-1
            expected_y=64+phase+8*delta
            expected_visible=int(-1<=delta<23 and 72<=expected_y<=231)
            if n and visible!=expected_visible:failures.append([n,t,'visibility',visible,expected_visible])
            if n and -1<=delta<23 and y!=expected_y:failures.append([n,t,'screen Y',y,expected_y])
            if hp>previous_hp[t]:failures.append([n,t,'health resurrected',previous_hp[t],hp])
            if previous_hp[t] and not hp:
                dead_since[t]=n
                deaths.append(dict(frame=n,turret=t,y=y,phase=phase,coarse_count=coarse))
            if style==6:hit_styles.add(t)
            if dead_since[t] is not None:
                if n>dead_since[t]+3 and style!=7:failures.append([n,t,'death glyph not published',style])
                if visible and not previous_visible[t] and n>dead_since[t]:dead_reentries[t]+=1
            previous_hp[t],previous_visible[t]=hp,visible
        if get('OBJECT_TYPE')!=1:failures.append([n,'logical player slot0 changed'])
        bullets=sum(get('OBJECT_ACTIVE',i)!=0 and get('OBJECT_TYPE',i)==3 for i in range(1,16))
        if bullets!=get('ENEMY_BULLET_COUNT') or bullets>3:failures.append([n,'shared bullet cap/count',bullets,get('ENEMY_BULLET_COUNT')])
        shots=get('TURRET_SHOTS_FIRED')
        free=get('DEBUG_FREE_LO')+256*get('DEBUG_FREE_HI')
        group='firing' if shots!=previous_shots else 'visible' if any(get('TURRET_VISIBLE',t) and get('TURRET_HEALTH',t) for t in range(count)) else 'offscreen'
        samples[group].append(free)
        previous_shots=shots
        if all(134<=d<=143 for d in ram[33:38]):displayed.append(int(''.join(str(d-134) for d in ram[33:38])))
    if args.require_wrap_deaths:
        if coarse<stage_rows*2:failures.append(['fewer than two complete stage circuits',coarse])
        for t in (0,2):
            if dead_since[t] is None or not dead_reentries[t]:failures.append([t,'missing destroyed wrap reentry'])
            if t not in hit_styles:failures.append([t,'no captured hit flash'])
        if not any(d['turret']==2 and d['y']>=224 for d in deaths):failures.append(['missing destruction before bottom exit'])
    # The FREE cycle diagnostic is intentionally disabled in this build (its
    # runtime update contributes zero gameplay-frame CPU), so the FREE digits
    # are static "00000" and DEBUG_FREE_* stays 0. Report that instead of
    # crashing on the now-empty sample set; the turret correctness checks above
    # are unchanged.
    live_free=[v for v in displayed if v]
    nonzero_samples={k:[v for v in vs if v] for k,vs in samples.items()}
    summary=dict(frames=len(records),coarse_transitions=coarse,stage_circuits=coarse/stage_rows,
        deaths=deaths,dead_reentries=dead_reentries,hit_flash_turrets=sorted(hit_styles),
        deferrals=deferrals,shots_fired_mod256=previous_shots,
        hud_free=(dict(min=min(live_free),median=statistics.median(live_free),max=max(live_free))
                  if live_free else 'disabled (static FREE display)'),
        free_samples=({k:dict(count=len(v),min=min(v),median=statistics.median(v),max=max(v))
                       for k,v in nonzero_samples.items() if v}
                      or 'disabled (FREE diagnostic not updated at runtime)'),
        failure_count=len(failures),failures=failures[:24])
    (root/'turret-verification.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    raise SystemExit(bool(failures))


if __name__=='__main__':main()
