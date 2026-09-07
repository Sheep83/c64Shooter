#!/usr/bin/env python3
"""Decode exact coarse branches and immutable LIVE reuse intervals from passive logs."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import re

HEAD=re.compile(r'#(\d+) \(Trace[^\n]*\)\s+(\d+)/\$[0-9a-f]+,\s+(\d+)/\$[0-9a-f]+')
CPU=re.compile(r'^\.C:([0-9a-fA-F]{4})\s+(.*?)\s+- A:([0-9a-fA-F]+) X:([0-9a-fA-F]+) Y:([0-9a-fA-F]+) SP:([0-9a-fA-F]+)\s+([.A-Z-]+)\s+(\d+)')
MEM=re.compile(r'^>C:([0-9a-fA-F]{4})\s{2}(.*)')


def events(path, mapping):
    event=None
    with path.open(errors='replace') as f:
        for line in f:
            m=HEAD.search(line)
            if m:
                if event and 'clock' in event:yield event
                event=dict(name=mapping[m[1]],line=int(m[2]),cycle=int(m[3]))
                continue
            if event is None:continue
            m=CPU.match(line)
            if m and 'clock' not in event:
                event.update(pc=int(m[1],16),instruction=m[2],a=int(m[3],16),x=int(m[4],16),
                             y=int(m[5],16),sp=int(m[6],16),flags=m[7],clock=int(m[8]))
            m=MEM.match(line)
            if m:
                mem=event.setdefault('memory',{})
                addr=int(m[1],16)
                # VICE may use4 or16 columns; double spaces separate groups,
                # while three spaces start padding/PETSCII, never RAM bytes.
                for i,v in enumerate(m[2].split('   ',1)[0].split()):mem[addr+i]=int(v,16)
    if event and 'clock' in event:yield event


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path)
    args=p.parse_args();root=args.capture
    s=json.loads((root/'symbols.json').read_text());frames=json.loads((root/'frames.json').read_text())
    mapping=json.loads((root/'trace-map.json').read_text());base=frames[0]['clock']
    per=defaultdict(lambda:dict(events=Counter(),phases={},allocations=[],despawns=[],hits=[],kills=[],scores=[],score_dirty_writes=[],batches=[]))
    deferrals=[];pending=[];last_context=None;last_gate=None
    phase=None;spawn=None;generation=[0]*16;birth={}
    planned_birth={};live_birth={}
    counts=Counter()
    clock_adjustments=Counter()
    def get(mem,name,i=0):return mem[s[name]+i]
    def context(e):
        mem=e['memory'];g=lambda n,i=0:get(mem,n,i)
        live=g('LIVE_PLAN');objects=[]
        for i in range(16):
            if g('OBJECT_ACTIVE',i):
                objects.append(dict(id=i,type=g('OBJECT_TYPE',i),x=g('OBJECT_X',i)+256*g('OBJECT_X_MSB',i),
                    y=g('OBJECT_Y',i),health=g('OBJECT_HEALTH',i),death=g('OBJECT_DEATH_TIMER',i),
                    stage=g('OBJECT_STAGE',i),generation=generation[i],birth=birth.get(i)))
        slots={i:dict(id=g('INITIAL_OBJECT',live+i),y=g('INITIAL_Y',live+i)) for i in range(g('RENDER_COUNT',live))}
        batches=[]
        for bi in range(g('BATCH_COUNT',live)):
            idx=live+bi;assignments=[]
            first=g('BATCH_FIRST_ASSIGN',idx);number=g('BATCH_ASSIGN_COUNT',idx)
            for ai in range(first,first+number):
                a=live+ai;slot=g('ASSIGN_SLOT',a);old=slots.get(slot,dict(id=None,y=-24))
                oid=g('ASSIGN_OBJECT',a);y=g('ASSIGN_Y',a)
                assignments.append(dict(id=oid,slot=slot,y=y,x=g('ASSIGN_X',a)+256*g('ASSIGN_X_MSB',a),
                    current_type=g('OBJECT_TYPE',oid),previous_id=old['id'],previous_y=old['y'],
                    release=old['y']+24,deadline=y-12,birth=live_birth.get(oid)))
                slots[slot]=dict(id=oid,y=y)
            batches.append(dict(index=idx,compare=g('BATCH_RASTER',idx),
                earliest=max(a['release'] for a in assignments),latest=min(a['deadline'] for a in assignments),
                outstanding=idx>=g('RASTER_BATCH_OFFSET'),assignments=assignments))
        return dict(frame=e['frame'],raster=e['line'],cycle=e['cycle'],clock=e['clock'],
            pending=g('BG_COARSE_PENDING'),fine=g('SCROLL_FINE'),row=g('SCROLL_ROW'),
            live=live,build=g('BUILD_PLAN'),offset=g('RASTER_BATCH_OFFSET'),end=g('RASTER_BATCH_END'),
            batch_count=g('BATCH_COUNT',live),batches=batches,
            sorted_count=g('SORTED_COUNT'),sorted_ids=[g('SORTED_OBJECTS',i) for i in range(g('SORTED_COUNT'))],
            initial_ids=[g('INITIAL_OBJECT',live+i) for i in range(g('RENDER_COUNT',live))],
            objects=objects,active_count=len(objects),enemy_count=sum(o['type']==2 for o in objects),
            hostile_bullet_count=g('ENEMY_BULLET_COUNT'),hostile_bullets=[o for o in objects if o['type']==3],
            explosions=[o for o in objects if o['death']],
            turret=[{n:g('TURRET_'+n.upper(),i) for n in ['health','visible','y','aim','fire_timer','hit_timer']} for i in range(3)],
            player_fire_held=not bool(mem[0x30]&16),player_fire_cooldown=g('PLAYER_FIRE_COOLDOWN_TIMER'),
            score=g('SCORE_LO')+256*g('SCORE_HI'),score_dirty=g('SCORE_DIRTY'),
            replay=g('RASTER_REPLAY_FRAMES')+256*g('RASTER_REPLAY_FRAMES',1),
            catchups=g('RASTER_CATCHUPS')+256*g('RASTER_CATCHUPS',1),
            incomplete=g('RASTER_INCOMPLETE_FRAMES')+256*g('RASTER_INCOMPLETE_FRAMES',1))
    for e in events(root/'timing.log',mapping):
        # Only the first CPU line following a trace header belongs to it.
        # Later monitor breakpoint disassembly must not replace its timestamp
        # or registers. Cross-check the independent header beam; never repair
        # a clock silently to fit the expected epoch.
        e['raw_clock']=e['clock']
        adjustment=(e['clock']-base-e['line']*63-e['cycle'])%19656
        if adjustment:clock_adjustments[adjustment]+=1
        n=(e['clock']-base)//19656;e['frame']=n
        if not 0<=n<len(frames):continue
        name=e['name'];counts[name]+=1;f=per[n];f['events'][name]+=1
        # Logical slots can be despawned/reallocated while the prior plan is
        # still LIVE. Associate assignment provenance with its BUILD/swap,
        # not the main thread's newer allocation generation at admission.
        if name=='buildBatchSpriteSchedule':planned_birth=dict(birth)
        if name=='swapRenderPlans':live_birth=dict(planned_birth)
        if name in ('updateObjects','updateEnemyFire','updateBackgroundTurrets','updateSpawner'):
            phase=name;spawn=None
        if name=='spawnEnemyBulletAt':spawn=dict(source='turret' if phase=='updateBackgroundTurrets' else 'enemy',source_id=e['x'] if phase=='updateBackgroundTurrets' else e['y'])
        if name=='store_OBJECT_ACTIVE':
            oid=e['x'] if ',X' in e['instruction'] else e['y'] if ',Y' in e['instruction'] else 0
            if e['a']==1:
                generation[oid]+=1;birth[oid]=dict(frame=n,phase=phase,generation=generation[oid],**(spawn or {}));f['allocations'].append(dict(id=oid,**birth[oid]));spawn=None
            elif e['a']==0:f['despawns'].append(dict(id=oid,raster=e['line'],cycle=e['cycle']))
        if name in ('store_OBJECT_HEALTH','store_TURRET_HEALTH') and 'DEC ' in e['instruction']:
            f['hits'].append(dict(kind='enemy' if name=='store_OBJECT_HEALTH' else 'turret',id=e['x'],raster=e['line'],cycle=e['cycle']))
        if name=='store_OBJECT_DEATH_TIMER' and phase=='updateObjects' and 'STA ' in e['instruction'] and s['damageEnemy']<=e['pc']<s['updateEnemyHealthSprite']:
            f['kills'].append(dict(kind='enemy',id=e['x'],raster=e['line'],cycle=e['cycle']))
        if name=='awardKillScore':
            f['scores'].append(dict(id=e['x'],raster=e['line'],cycle=e['cycle']))
            if phase=='updateObjects':f['kills'].append(dict(kind='turret',id=e['x'],raster=e['line'],cycle=e['cycle']))
        if name=='store_SCORE_DIRTY':f['score_dirty_writes'].append(dict(value=e['a'],raster=e['line'],cycle=e['cycle']))
        if name=='applyLiveRasterBatch':f['batches'].append(dict(raster=e['line'],cycle=e['cycle'],clock=e['clock']))
        if name in ('prepare','updateObjects','updateEnemyFire','updateBackgroundTurrets','updateEnemyHitEffects',
                    'buildSortedObjectList','sortObjectsByY','buildInitialSpriteSnapshot','buildBatchSpriteSchedule','updateCycleDebug','refreshScoreIfDirty',
                    'waitForGameFrame','swapRenderPlans','bgUpperReady','bgLowerReady','displayScore'):
            f['phases'].setdefault(name,[]).append([e['line'],e['cycle']])
        if name=='pending_context':
            last_context=context(e);pending.append(last_context)
        elif name in ('batch_gate','high_gate','deadline_gate'):
            last_gate={k:v for k,v in e.items() if k!='memory'}
        elif name=='defer':
            d=context(e);d['admission']=last_context;d['branch']=last_gate
            d['cause']={'batch_gate':'batch-not-consumed','high_gate':'high-raster','deadline_gate':'raster-deadline'}[last_gate['name']]
            deferrals.append(d)
    runs=[]
    for d in deferrals:
        n=d['frame'];d['activity']=per[n]
        if not runs or n!=runs[-1][-1]['frame']+1:runs.append([])
        runs[-1].append(d);d['consecutive_deferral']=len(runs[-1])
    observed=sum((b['deferred']-a['deferred'])%256 for a,b in zip(frames,frames[1:]))
    traced=sum(d['frame']>0 for d in deferrals)
    failures=[]
    for frame in frames:
        data=(root/f'{frame["frame"]:05d}.state').read_bytes()
        g=lambda name,i=0:data[s[name]-0x2000+i]
        bullets=sum(g('OBJECT_ACTIVE',i)!=0 and g('OBJECT_TYPE',i)==3 for i in range(1,16))
        if bullets>3 or bullets!=g('ENEMY_BULLET_COUNT'):failures.append([frame['frame'],'hostile bullet cap/count',bullets,g('ENEMY_BULLET_COUNT')])
        if not g('OBJECT_ACTIVE') or g('OBJECT_TYPE')!=1:failures.append([frame['frame'],'player logical slot0'])
        if {g('LIVE_PLAN'),g('BUILD_PLAN')}!={0,8}:failures.append([frame['frame'],'BUILD/LIVE ownership'])
    if clock_adjustments:failures.append(['trace clock disagrees with header beam',dict(clock_adjustments)])
    if observed!=traced:failures.append(['counter vs actual defer traces',observed,traced])
    deltas=sorted(set(b['clock']-a['clock'] for a,b in zip(frames,frames[1:])))
    if deltas!=[19656]:failures.append(['PAL cadence',deltas])
    coarse=sum(a['fine']==7 and b['fine']==0 for a,b in zip(frames,frames[1:]))
    shots=sum((b['turret_shots']-a['turret_shots'])%256 for a,b in zip(frames,frames[1:]))
    longest=max(runs,key=len,default=[])
    summary=dict(frames=len(frames),deferrals=len(deferrals),stall_count=len(runs),
        stall_lengths=sorted((len(r) for r in runs),reverse=True),
        cause_breakdown=dict(Counter(d['cause'] for d in deferrals)),
        coarse_transitions=coarse,stage_circuits=coarse/100,frame_cycle_deltas=deltas,
        turret_shots=shots,turret_opportunities=counts['turret_opportunity'],
        hits=sum(len(v['hits']) for v in per.values()),score_awards=counts['awardKillScore'],
        kills=sum(len(v['kills']) for v in per.values()),
        hostile_spawn_attempts=counts['spawnEnemyBulletAt'],
        allocations=sum(len(v['allocations']) for v in per.values()),despawns=sum(len(v['despawns']) for v in per.values()),
        max_active=max(f['active'] for f in frames),phase7_frame_count=sum(f['fine']==7 for f in frames),
        trace_events=dict(counts),longest_stall_frames=[d['frame'] for d in longest],failures=failures)
    summary['trace_clock_adjustments']=dict(clock_adjustments)
    (root/'hitch-summary.json').write_text(json.dumps(summary,indent=2))
    (root/'deferrals.json').write_text(json.dumps(deferrals,indent=2))
    (root/'coarse-admissions.json').write_text(json.dumps(pending,indent=2))
    (root/'frame-activity.json').write_text(json.dumps(per))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('trace_events','trace_clock_adjustments')},indent=2))
    for d in longest:
        outstanding=[b for b in d['batches'] if b['outstanding']]
        print(d['frame'],d['cause'],'admit',d['admission']['raster'],'LIVE',d['live'],
              [(b['compare'],b['earliest'],[(a['id'],a['current_type'],a['y'],a['previous_id'],a['release']) for a in b['assignments']]) for b in outstanding])
    raise SystemExit(bool(failures))


if __name__=='__main__':main()
