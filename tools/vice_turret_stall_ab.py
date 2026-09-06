#!/usr/bin/env python3
"""Least-perturbing A/B for the no-player-fire background-scroll stall.

Breaks ONCE per frame at applyFineScroll (the same frame-start sync
vice_scroll_test.py uses) and lets the machine free-run the whole rest of the
frame, so prepareBackgroundCoarse's coarse-admission decision happens at
natural timing (an earlier probe that broke AT prepareBackgroundCoarse every
frame perturbed that decision).

Modes (player never fires unless the name says 'fire'):
  fire                  player fires continuously (control)
  nofire                turrets fire on their normal cadence
  nofire-noturretfire   turret firing fully suppressed (TURRET_FIRE_TIMER pinned)
  nofire-egressonly     WAVE-PHASE RULE (hold semantics): each frame, if any
                        enemy is fire-eligible by the engine's own predicate
                        (TYPE_ENEMY, DEATH_TIMER==0, OBJECT_STAGE!=EGRESS,
                        71<=Y<190), pin TURRET_FIRE_TIMER high so turrets cannot
                        fire this frame. When no enemy is eligible, turrets fire
                        normally. Timer is left high -> no burst when the window
                        opens; turrets resume on their normal interval.
  nofire-egressonly-drain
                        same rule, DRAIN semantics: while enemies are eligible,
                        hold each turret's timer at 1 instead of pinning it, so
                        every turret that was ready fires on the frame the window
                        opens - used to measure the burst risk Task E asks about.

Run against a build with the SORTED_COUNT>=8 turret-fire mitigation compiled
out:  KickAss ... -define TURRET_FIRE_NO_MITIGATION -o build/shooter-nomit.prg
Pass --prg build/shooter-nomit.prg --symbols build/nomit/main.vs.
"""
import argparse, json, re, socket, subprocess, time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

DIV = 3
CUTOFF = 184
TCOUNT = 3
TYPE_ENEMY = 2
TYPE_ENEMY_BULLET = 3
STAGE_EGRESS = 2
FIRE_Y_LO, FIRE_Y_HI = 71, 190       # updateEnemyFire's Y band
TURRET_Y_LO, TURRET_Y_HI = 88, 201   # updateBackgroundTurrets !fire Y band


def launch(port, out, prg):
    with socket.socket() as c:
        if c.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'port {port} occupied')
    p = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
        '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
        '-autostartprgmode', '1', '-autostart', str(Path(prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    m = Monitor(port)
    m.trace_file = (out / 'monitor.log').open('w')
    return p, m


def run(mode, port, out, frames, prg, vs):
    sym = symbols(Path(vs))
    S = lambda n: sym[n]
    proc, m = launch(port, out, prg)
    try:
        m.cmd('delete')
        m.cmd('resourceset "JoyPort2Device" "37"')
        m.cmd(f'break {S("waitFireRelease"):04x}')
        m.cmd('jpdb 1 ef'); m.cmd('x'); m.cmd('jpdb 1 ff')
        m.cmd('delete')
        m.cmd(f'break {S("applyFineScroll"):04x}')
        m.cmd('x')

        def put(a, v):
            a = sym[a] if isinstance(a, str) else a
            if isinstance(v, int): v = [v]
            m.cmd(f'> {a:04x} ' + ' '.join(f'{x & 255:02x}' for x in v))

        def rd(a, n=1):
            a = sym[a] if isinstance(a, str) else a
            p = out / 'scratch.bin'
            m.cmd(f'bsave "{p}" 0 {a:04x} {a + n - 1:04x}')
            return p.read_bytes()

        put('PLAYER_LIVES', 0xff)
        OBJ_ACT = S('OBJECT_ACTIVE'); OBJ_Y = S('OBJECT_Y'); OBJ_TYPE = S('OBJECT_TYPE')
        OBJ_DT = S('OBJECT_DEATH_TIMER'); OBJ_ST = S('OBJECT_STAGE')
        TFT = S('TURRET_FIRE_TIMER')
        DIRS = [0xfe, 0xfd, 0xf7, 0xfb, 0xff]
        FIRE_DIRS = [0xee, 0xed, 0xe7, 0xeb, 0xef]

        for _ in range(150):
            m.cmd('x')

        F = []
        prev_def = rd('BG_COARSE_DEFERRED')[0]
        prev_shots = rd('TURRET_SHOTS_FIRED')[0]
        for i in range(frames):
            if i % 19 == 0:
                d = (FIRE_DIRS if mode == 'fire' else DIRS)[(i // 19) % 5]
                m.cmd(f'jpdb 1 {d:02x}')

            act = rd(OBJ_ACT, 16); ys = rd(OBJ_Y, 16); ty = rd(OBJ_TYPE, 16)
            dt = rd(OBJ_DT, 16); st = rd(OBJ_ST, 16)
            tvis = list(rd('TURRET_VISIBLE', TCOUNT)); tY = list(rd('TURRET_Y', TCOUNT))
            tft0 = list(rd(TFT, TCOUNT))
            eligible = any(act[s] and ty[s] == TYPE_ENEMY and dt[s] == 0
                           and st[s] != STAGE_EGRESS and FIRE_Y_LO <= ys[s] < FIRE_Y_HI
                           for s in range(1, 16))
            turret_ready_in_band = [j for j in range(TCOUNT)
                                    if tvis[j] and TURRET_Y_LO <= tY[j] <= TURRET_Y_HI
                                    and tft0[j] <= 1]
            bullets_now = rd('ENEMY_BULLET_COUNT')[0]
            suppressed_now = 0
            hold = False
            if mode == 'nofire-noturretfire':
                hold = True
            elif mode == 'nofire-egressonly':
                hold = eligible
            elif mode == 'nofire-egressonly-drain':
                if eligible:
                    put(TFT, [1, 1, 1])
                    suppressed_now = len(turret_ready_in_band)
            elif mode == 'nofire-poolheadroom':
                hold = bullets_now >= 2
            elif mode == 'nofire-poolany':
                hold = bullets_now >= 1
            elif mode == 'nofire-egress-or-poolheadroom':
                hold = eligible and bullets_now >= 2
            elif mode == 'nofire-egress-or-poolany':
                hold = eligible and bullets_now >= 1
            if hold:
                put(TFT, [120, 120, 120])
                suppressed_now = len(turret_ready_in_band)

            m.cmd('x')                                       # free-run one whole frame

            df = rd('BG_COARSE_DEFERRED')[0]
            shots = rd('TURRET_SHOTS_FIRED')[0]
            act = rd(OBJ_ACT, 16); ys = rd(OBJ_Y, 16); ty = rd(OBJ_TYPE, 16)
            objs = [(s, ys[s], ty[s]) for s in range(16) if act[s]]
            live = rd('LIVE_PLAN')[0] if 'LIVE_PLAN' in sym else 0
            bc = rd('BATCH_COUNT', 16)[live] if 'BATCH_COUNT' in sym else 0
            br = rd('BATCH_RASTER', 16)[live] if 'BATCH_RASTER' in sym else 0
            rec = dict(i=i, deferred=df, defer_step=(df - prev_def) & 255,
                       shots_step=(shots - prev_shots) & 255,
                       eligible=eligible, suppressed_now=suppressed_now,
                       turret_ready_in_band=len(turret_ready_in_band),
                       fine=rd('SCROLL_FINE')[0], row=rd('SCROLL_ROW')[0],
                       fc=rd('SCROLL_FRAME_COUNT')[0],
                       bullets=rd('ENEMY_BULLET_COUNT')[0],
                       active=len(objs),
                       bullet_ys=sorted(y for _, y, t in objs if t == TYPE_ENEMY_BULLET),
                       obj_ys=sorted(y for _, y, _t in objs),
                       batch_count=bc, batch_raster=br,
                       tvis=list(rd('TURRET_VISIBLE', TCOUNT)),
                       tY=list(rd('TURRET_Y', TCOUNT)))
            F.append(rec)
            prev_def = df
            prev_shots = shots
        return F
    finally:
        try:
            m.cmd('log off'); m.sock.sendall(b'quit\n'); m.sock.close()
        except Exception:
            pass
        try: proc.wait(timeout=10)
        except Exception: proc.kill()


def summarise(mode, F):
    steps = [r for r in F if r['defer_step']]
    total = (F[-1]['deferred'] - F[0]['deferred']) & 255 if F else 0
    stalls, run_ = [], []
    for r in F:
        if r['defer_step']:
            run_.append(r)
        elif run_:
            stalls.append(run_); run_ = []
    if run_:
        stalls.append(run_)

    def cause(r):
        if r['batch_count'] >= 1:
            return 'batch-not-consumed'
        return 'other-guard'
    causes = {}
    for r in steps:
        causes[cause(r)] = causes.get(cause(r), 0) + 1

    total_shots = sum(r['shots_step'] for r in F)
    frames_eligible = sum(1 for r in F if r['eligible'])
    frames_turret_in_band = sum(1 for r in F if r['turret_ready_in_band'])
    suppressed = sum(r['suppressed_now'] for r in F)
    # longest run of consecutive shot frames right after an eligibility->clear edge
    burst = 0
    for k in range(1, len(F)):
        if F[k - 1]['eligible'] and not F[k]['eligible']:
            c = 0
            j = k
            while j < len(F) and j < k + 8 and F[j]['shots_step']:
                c += F[j]['shots_step']; j += 1
            burst = max(burst, c)

    return dict(
        mode=mode, frames=len(F), total_deferrals=total,
        deferral_frames=len(steps), stall_count=len(stalls),
        stall_lengths=sorted((len(s) for s in stalls), reverse=True),
        cause_breakdown=causes,
        deferrals_with_active_ge9=sum(1 for r in steps if r['active'] >= 9),
        deferrals_with_low_bullet=sum(1 for r in steps if any(y >= 200 for y in r['bullet_ys'])),
        turret_shots_fired=total_shots,
        frames_enemy_fire_eligible=frames_eligible,
        frames_turret_ready_in_band=frames_turret_in_band,
        turret_opportunities_suppressed_by_rule=suppressed,
        max_shots_in_8_frames_after_window_opens=burst,
        deferral_samples=[dict(
            i=r['i'], row=r['row'], cause=cause(r), active=r['active'],
            hostile_bullets=r['bullets'], lowest_bullet_ys=r['bullet_ys'][-3:],
            batch_count=r['batch_count'], batch_raster=r['batch_raster'],
            enemy_fire_eligible=r['eligible'],
            turret_visible=[j for j in range(TCOUNT) if r['tvis'][j]],
            turret_y=[r['tY'][j] for j in range(TCOUNT) if r['tvis'][j]])
            for r in steps[:80]],
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6564)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/turret-stall-ab'))
    ap.add_argument('--frames', type=int, default=6000)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--modes', default='nofire,nofire-egressonly')
    args = ap.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    R = {}
    for mode in args.modes.split(','):
        F = run(mode, args.port, out, args.frames, args.prg, args.symbols)
        (out / f'{mode}-frames.json').write_text(json.dumps(F))
        R[mode] = summarise(mode, F)
    (out / 'stall-ab.json').write_text(json.dumps(R, indent=2))
    print(json.dumps(R, indent=2))
    print('\n== SUMMARY (prg=%s) ==' % args.prg)
    for mode, s in R.items():
        print(f'  {mode}')
        print(f'    deferrals={s["total_deferrals"]}  stalls={s["stall_count"]} '
              f'lengths={s["stall_lengths"][:15]}  causes={s["cause_breakdown"]}')
        print(f'    turret shots fired={s["turret_shots_fired"]}  '
              f'opportunities suppressed by rule={s["turret_opportunities_suppressed_by_rule"]}  '
              f'frames enemy-fire-eligible={s["frames_enemy_fire_eligible"]}/{s["frames"]}')
        print(f'    max turret shots in 8 frames after a window opens={s["max_shots_in_8_frames_after_window_opens"]}')


if __name__ == '__main__':
    main()
