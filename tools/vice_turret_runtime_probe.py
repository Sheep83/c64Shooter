#!/usr/bin/env python3
"""No-player-fire turret runtime hitch probe.

New human evidence: the visible one-frame background scroll hitch still occurs
with the player weapon NEVER fired, twice while the left-most turret (turret 2,
world col 13, screen X 128) was roughly mid-screen. So the hitch is turret
related but does not need turret damage. Suspects: per-frame turret aim/style
work, turret firing, projectile allocation, private-glyph republication.

Mechanism under test (unchanged, proven safe): on a coarse-transition frame the
cumulative BUILD-side CPU from waitForGameFrame -> ... -> prepareBackgroundCoarse
can push the raster line prepareBackgroundCoarse is reached at past
BG_COARSE_LATEST_START (184); the coarse copy is then safely deferred
(BG_COARSE_DEFERRED++), holding fine scroll one extra frame. Physical frame
stays exactly 19656 cycles. We want to know which turret operation supplies the
tipping cost on the visible hitch frame.

Part A  isolated CPU cost of every variable turret path (call() trampoline,
        DEN / sprite DMA / IRQs disabled).

Part B  real game, player never fires. Break at every prepareBackgroundCoarse;
        record the reached raster + full turret / coarse / object context.
        Flag each BG_COARSE_DEFERRED increment and dump the deferral frame plus
        the two before and one after. Build the correlation of deferral vs
        {turret fired this frame, aim changed, glyph published, which turret
        visible and its screen Y}. Emit matched non-deferral frames at similar
        SCROLL_ROW.

Part C  matched causal isolation. Break at the frame-start publishTurretGlyphs;
        dump a VICE snapshot; run the frame to prepareBackgroundCoarse and
        record the reached raster; undump and re-run with, in turn: the glyph
        publication forced clean, all turrets frozen (not visible), turret fire
        suppressed, and only the left-most turret active. The reached-raster
        delta from baseline isolates each operation's contribution, and whether
        removing it removes the deferral.
"""
import argparse, json, re, socket, subprocess, time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

DIV = 3
CUTOFF = 184
SNAP = '/tmp/vice_turret_runtime.vsf'
TCOUNT = 3


def launch(port, out):
    with socket.socket() as c:
        if c.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'port {port} occupied')
    p = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
        '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
        '-autostartprgmode', '1', '-autostart', str(Path('build/shooter.prg').resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    m = Monitor(port)
    m.trace_file = (out / 'monitor.log').open('w')
    return p, m


def start_playing(m, sym):
    """Drive the menu with one fire press, then leave the fire bit HIGH forever."""
    m.cmd('delete')
    m.cmd('resourceset "JoyPort2Device" "37"')
    m.cmd(f'break {sym["waitFireRelease"]:04x}')
    m.cmd('jpdb 1 ef')                       # fire held: start the game
    m.cmd('x')
    m.cmd('jpdb 1 ff')                       # fire released and never pressed again
    m.cmd('delete')
    m.cmd(f'break {sym["applyFineScroll"]:04x}')
    m.cmd('x')
    m.cmd('delete')


_RREG = re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')
def clk(reg): return int(_RREG.search(reg)[3])
def rl(reg):  return int(_RREG.search(reg)[1])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6562)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/turret-runtime'))
    ap.add_argument('--frames', type=int, default=5000)
    ap.add_argument('--ab-samples', type=int, default=48)
    args = ap.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    S = lambda n: sym[n]
    proc, m = launch(args.port, out)
    R = {}
    try:
        def put(addr, values):
            addr = sym[addr] if isinstance(addr, str) else addr
            if isinstance(values, int): values = [values]
            m.cmd(f'> {addr:04x} ' + ' '.join(f'{v & 255:02x}' for v in values))

        def rd(addr, n=1):
            addr = sym[addr] if isinstance(addr, str) else addr
            p = out / 'scratch.bin'
            m.cmd(f'bsave "{p}" 0 {addr:04x} {addr + n - 1:04x}')
            return p.read_bytes()

        def call(name, x=0):
            a = sym[name] if isinstance(name, str) else name
            code = [0x78, 0xd8, 0xa2, x & 255, 0x20, a & 255, a >> 8, 0x08, 0x68,
                    0x8d, 0x00, 0x7e, 0x8e, 0x01, 0x7e, 0x4c, 0x0f, 0x70]
            put(0x7000, code)
            m.cmd('r pc=7000, sp=ff')
            t0 = clk(m.cmd('r')); m.cmd('x'); cyc = clk(m.cmd('r')) - t0 - 27
            st = rd(0x7e00, 2)
            return cyc, st[0] & 1, st[1]

        def turrets(n=TCOUNT):
            base = S('TURRET_STATE_BEGIN')
            g = lambda name: list(rd(name, n))
            return dict(health=g('TURRET_HEALTH'), visible=g('TURRET_VISIBLE'),
                        y=g('TURRET_Y'), aim=g('TURRET_AIM'),
                        desired=g('TURRET_DESIRED_STYLE'), shown=g('TURRET_SHOWN_STYLE'),
                        fire_timer=g('TURRET_FIRE_TIMER'), hit_timer=g('TURRET_HIT_TIMER'),
                        shots=rd('TURRET_SHOTS_FIRED')[0],
                        publications=rd('TURRET_GLYPH_PUBLICATIONS')[0],
                        x=[rd('TURRET_X_LO', n)[i] + 256 * rd('TURRET_X_HI', n)[i] for i in range(n)])

        # ================= Part A : isolated CPU cost =================
        start_playing(m, sym)
        m.cmd('> d01a 00'); m.cmd('> dc0d 7f'); m.cmd('> d015 00'); m.cmd('> d011 00')
        m.cmd('break 700f')
        tx = [rd('TURRET_X_LO', TCOUNT)[i] + 256 * rd('TURRET_X_HI', TCOUNT)[i] for i in range(TCOUNT)]
        A = {'turret_X': tx}

        def measure(label, setup, name, x=0, reps=3):
            vals = []
            for _ in range(reps):
                setup()
                vals.append(call(name, x)[0])
            A[label] = [min(vals), max(vals)]

        # position: constant work, all three turrets
        measure('positionBackgroundTurrets', lambda: put('SCROLL_ROW', 40),
                'positionBackgroundTurrets')

        # aim: player below (down aim) vs above (up aim); centred vs far L/R
        def aim_setup(px, py):
            put(S('OBJECT_X') + 0, px & 255); put(S('OBJECT_X_MSB') + 0, px >> 8)
            put(S('OBJECT_Y') + 0, py)
            put(S('TURRET_Y') + 0, 150)
            put('TURRET_AIM', [4, 0, 0])
        measure('aim_centre_below', lambda: aim_setup(tx[0], 200), 'aimBackgroundTurret', 0)
        measure('aim_centre_above', lambda: aim_setup(tx[0], 90), 'aimBackgroundTurret', 0)
        measure('aim_far_left', lambda: aim_setup(tx[0] - 120, 200), 'aimBackgroundTurret', 0)
        measure('aim_far_right', lambda: aim_setup(tx[0] + 120, 200), 'aimBackgroundTurret', 0)

        # updateBackgroundTurrets under representative whole-frame states
        def ubt_setup(**kw):
            put('TURRET_HEALTH', kw.get('health', [3, 3, 3]))
            put('TURRET_VISIBLE', kw.get('visible', [0, 0, 0]))
            put('TURRET_FIRE_TIMER', kw.get('fire_timer', [90, 90, 90]))
            put('TURRET_HIT_TIMER', [0, 0, 0])
            put('TURRET_DESIRED_STYLE', kw.get('desired', [4, 4, 4]))
            put('TURRET_SHOWN_STYLE', kw.get('shown', [4, 4, 4]))
            put('TURRET_Y', kw.get('ty', [150, 150, 150]))
            put('PLAYER_STATE', 0)
            put(S('OBJECT_Y') + 0, kw.get('py', 240))
            put(S('OBJECT_X') + 0, tx[0] & 255); put(S('OBJECT_X_MSB') + 0, tx[0] >> 8)
            put('ENEMY_BULLET_COUNT', kw.get('bullets', 0))
            put('OBJECT_ACTIVE', kw.get('active', [1] + [0] * 15))
            put('TURRET_SHOTS_FIRED', 0)

        measure('ubt_none_visible', lambda: ubt_setup(visible=[0, 0, 0]), 'updateBackgroundTurrets')
        measure('ubt_all_dead', lambda: ubt_setup(health=[0, 0, 0], visible=[1, 1, 1]),
                'updateBackgroundTurrets')
        measure('ubt_1vis_noFire', lambda: ubt_setup(visible=[1, 0, 0], fire_timer=[90, 90, 90]),
                'updateBackgroundTurrets')
        measure('ubt_3vis_noFire', lambda: ubt_setup(visible=[1, 1, 1], fire_timer=[90, 90, 90]),
                'updateBackgroundTurrets')
        measure('ubt_1vis_fire_spawn',
                lambda: ubt_setup(visible=[1, 0, 0], fire_timer=[0, 90, 90], bullets=0,
                                  active=[1] + [0] * 15), 'updateBackgroundTurrets')
        measure('ubt_3vis_fire_spawn',
                lambda: ubt_setup(visible=[1, 1, 1], fire_timer=[0, 0, 0], bullets=0,
                                  active=[1] + [0] * 15), 'updateBackgroundTurrets')
        measure('ubt_1vis_fire_capfull',
                lambda: ubt_setup(visible=[1, 0, 0], fire_timer=[0, 90, 90], bullets=3),
                'updateBackgroundTurrets')

        # spawnEnemyBulletAt: findFreeObject search grows with occupied slots
        def spawn_setup(occupied):
            act = [1] * occupied + [0] * (16 - occupied)
            put('OBJECT_ACTIVE', act)
            put('ENEMY_BULLET_COUNT', 0)
            put(S('OBJECT_X') + 0, tx[0] & 255); put(S('OBJECT_X_MSB') + 0, tx[0] >> 8)
        for occ in (1, 4, 8, 12, 15):
            measure(f'spawnEnemyBulletAt_occ{occ}', lambda o=occ: spawn_setup(o), 'spawnEnemyBulletAt')

        # publishTurretGlyphs: scan-only vs one full 32-byte copy vs dead underlay
        measure('publish_clean',
                lambda: (put('TURRET_DESIRED_STYLE', [4, 4, 4]), put('TURRET_SHOWN_STYLE', [4, 4, 4])),
                'publishTurretGlyphs')
        measure('publish_1_aimstyle',
                lambda: (put('TURRET_DESIRED_STYLE', [2, 4, 4]), put('TURRET_SHOWN_STYLE', [4, 4, 4])),
                'publishTurretGlyphs')
        measure('publish_1_deadstyle',
                lambda: (put('TURRET_DESIRED_STYLE', [7, 4, 4]), put('TURRET_SHOWN_STYLE', [4, 4, 4])),
                'publishTurretGlyphs')
        R['partA'] = A

        # ================= fresh boot for the real run =================
        m.sock.sendall(b'quit\n'); m.sock.close(); proc.wait(timeout=10)
        proc, m = launch(args.port, out)
        start_playing(m, sym)
        put('PLAYER_LIVES', 0xff)

        # gentle directional-only movement so turret aim actually changes, but
        # the fire bit is never set.
        DIRS = [0xfe, 0xfd, 0xf7, 0xfb, 0xff]   # up, down, left, right, neutral (bit4 stays high)

        OBJ_ACT = S('OBJECT_ACTIVE'); OBJ_Y = S('OBJECT_Y'); OBJ_TYPE = S('OBJECT_TYPE')
        TYPE_ENEMY_BULLET = 3                   # src/main.asm .const TYPE_ENEMY_BULLET

        def objects():
            act = rd(OBJ_ACT, 16); ys = rd(OBJ_Y, 16); ty = rd(OBJ_TYPE, 16)
            return [dict(s=s, y=ys[s], type=ty[s]) for s in range(16) if act[s]]

        # ---------------- Part B : per-frame trace at prepareBackgroundCoarse
        m.cmd(f'break {S("prepareBackgroundCoarse"):04x}')
        for _ in range(150):
            m.cmd('x')

        B = []
        prev = None
        for i in range(args.frames):
            if i % 23 == 0:
                m.cmd(f'jpdb 1 {DIRS[(i // 23) % len(DIRS)]:02x}')
            m.cmd('x')
            reg = m.cmd('r')
            t = turrets()
            bo = rd('RASTER_BATCH_OFFSET')[0]; be = rd('RASTER_BATCH_END')[0]
            live = rd('LIVE_PLAN')[0] if 'LIVE_PLAN' in sym else 0
            bcount = rd('BATCH_COUNT', 16)[live] if 'BATCH_COUNT' in sym else 0
            braster = rd('BATCH_RASTER', 16)[bo] if 'BATCH_RASTER' in sym else 0
            objs = objects()
            rec = dict(
                i=i, rl=rl(reg),
                pending=rd('BG_COARSE_PENDING')[0],
                deferred=rd('BG_COARSE_DEFERRED')[0],
                batch_off=bo, batch_end=be, batch_left=(be - bo) & 255,
                batch_count=bcount, batch_raster=braster,
                scroll_row=rd('SCROLL_ROW')[0], scroll_fine=rd('SCROLL_FINE')[0],
                frame_count=rd('SCROLL_FRAME_COUNT')[0],
                bullets=rd('ENEMY_BULLET_COUNT')[0],
                active=len(objs),
                bullet_ys=sorted(o['y'] for o in objs if o['type'] == TYPE_ENEMY_BULLET),
                obj_ys=sorted(o['y'] for o in objs),
                t=t)
            if prev is not None:
                rec['fired'] = (t['shots'] - prev['t']['shots']) & 255
                rec['published'] = (t['publications'] - prev['t']['publications']) & 255
                rec['aim_changed'] = [a != b for a, b in zip(t['aim'], prev['t']['aim'])]
                rec['style_changed'] = [a != b for a, b in zip(t['desired'], prev['t']['desired'])]
                rec['dirty'] = [d != s for d, s in zip(t['desired'], t['shown'])]
                rec['defer_step'] = (rec['deferred'] - prev['deferred']) & 255
                rec['defer_cause'] = ('batch' if rec['batch_left'] else
                                      'raster' if rec['rl'] >= CUTOFF else
                                      'other') if rec.get('defer_step') else None
            B.append(rec)
            prev = rec
        R['partB_frames'] = B

        # deferral events with local context
        events = []
        for k, rec in enumerate(B):
            if rec.get('defer_step'):
                ctx = B[max(0, k - 2):k + 2]
                events.append(dict(at=rec['i'], scroll_row=rec['scroll_row'],
                                   reached_raster=rec['rl'], context=ctx))
        R['partB_deferrals'] = events

        coarse = [r for r in B if r['pending']]
        defr_frames = [r for r in B if r.get('defer_step')]
        def vis_set(r): return tuple(j for j in range(TCOUNT) if r['t']['visible'][j])
        R['partB_summary'] = dict(
            frames=len(B),
            total_deferrals=(B[-1]['deferred'] - B[0]['deferred']) & 255 if B else 0,
            coarse_frames=len(coarse),
            coarse_rl_sorted=sorted(r['rl'] for r in coarse),
            coarse_within_15_of_cutoff=sum(1 for r in coarse if CUTOFF - 15 <= r['rl'] < CUTOFF),
            deferral_frames=[dict(i=r['i'], rl=r['rl'], scroll_row=r['scroll_row'],
                                  fired=r.get('fired'), published=r.get('published'),
                                  dirty=r.get('dirty'), aim_changed=r.get('aim_changed'),
                                  visible=vis_set(r),
                                  turret_y=[r['t']['y'][j] for j in vis_set(r)],
                                  bullets=r['bullets'], active=r['active'])
                             for r in defr_frames],
            deferral_fired_frac=_frac(defr_frames, lambda r: r.get('fired')),
            deferral_published_frac=_frac(defr_frames, lambda r: r.get('published')),
            deferral_any_dirty_frac=_frac(defr_frames, lambda r: any(r.get('dirty') or [])),
            nondeferral_fired_frac=_frac([r for r in coarse if not r.get('defer_step')],
                                        lambda r: r.get('fired')),
            nondeferral_published_frac=_frac([r for r in coarse if not r.get('defer_step')],
                                             lambda r: r.get('published')),
        )
        m.cmd('delete')

        # ---------------- Part C : frame-start causal isolation --------------
        # Break at positionBackgroundTurrets (first call of the logical frame,
        # BEFORE this frame's updateBackgroundTurrets / BUILD / batch schedule).
        # On a frame that WILL be a coarse frame and already has >8 active
        # objects, snapshot, then re-run the whole frame with, in turn:
        #   remove_enemy_bullets  - clear every TYPE_ENEMY_BULLET object
        #   remove_one_enemy      - clear one non-bullet enemy (count -> 8)
        #   turrets_not_visible   - TURRET_VISIBLE = 0 (no aim/fire/publish work)
        #   glyphs_forced_clean   - TURRET_SHOWN_STYLE := TURRET_DESIRED_STYLE
        # and record whether prepareBackgroundCoarse then admits the coarse copy.
        variants = ['baseline', 'remove_enemy_bullets', 'remove_one_bullet',
                    'remove_one_enemy', 'turrets_not_visible', 'glyphs_forced_clean']

        def apply_variant(v):
            act = list(rd(OBJ_ACT, 16)); ty = rd(OBJ_TYPE, 16)
            if v == 'remove_enemy_bullets':
                for s in range(16):
                    if act[s] and ty[s] == TYPE_ENEMY_BULLET:
                        put(OBJ_ACT + s, 0)
                put('ENEMY_BULLET_COUNT', 0)
            elif v == 'remove_one_bullet':
                for s in range(16):
                    if act[s] and ty[s] == TYPE_ENEMY_BULLET:
                        put(OBJ_ACT + s, 0)
                        b = rd('ENEMY_BULLET_COUNT')[0]
                        put('ENEMY_BULLET_COUNT', max(0, b - 1))
                        break
            elif v == 'remove_one_enemy':
                for s in range(1, 16):
                    if act[s] and ty[s] == 2:            # TYPE_ENEMY
                        put(OBJ_ACT + s, 0)
                        break
            elif v == 'turrets_not_visible':
                put('TURRET_VISIBLE', [0, 0, 0])
            elif v == 'glyphs_forced_clean':
                put('TURRET_SHOWN_STYLE', list(rd('TURRET_DESIRED_STYLE', TCOUNT)))

        def run_frame_to_prepare():
            pre = rd('BG_COARSE_DEFERRED')[0]
            m.cmd(f'break {S("prepareBackgroundCoarse"):04x}')
            m.cmd('x'); reg = m.cmd('r')
            pend = rd('BG_COARSE_PENDING')[0]
            bo = rd('RASTER_BATCH_OFFSET')[0]; be = rd('RASTER_BATCH_END')[0]
            live = rd('LIVE_PLAN')[0] if 'LIVE_PLAN' in sym else 0
            bc = rd('BATCH_COUNT', 16)[live] if 'BATCH_COUNT' in sym else 0
            br = rd('BATCH_RASTER', 16)[bo] if 'BATCH_RASTER' in sym else 0
            m.cmd('delete')
            post = rd('BG_COARSE_DEFERRED')[0]
            return dict(reached_raster=rl(reg), pending=pend,
                        batch_left=(be - bo) & 255, batch_count=bc, batch_raster=br,
                        deferred=(post - pre) & 255)

        m.cmd(f'break {S("positionBackgroundTurrets"):04x}')
        C = []
        i = 0
        while len(C) < args.ab_samples and i < 60000:
            i += 1
            m.cmd('x')
            fine = rd('SCROLL_FINE')[0]; cnt = rd('SCROLL_FRAME_COUNT')[0]
            if not (fine == 7 and cnt == DIV - 1):
                continue
            objs = objects(); t0 = turrets()
            m.cmd('delete')
            m.cmd(f'dump "{SNAP}"')
            base = run_frame_to_prepare()
            if not base['deferred']:
                m.cmd(f'undump "{SNAP}"')
                m.cmd(f'break {S("positionBackgroundTurrets"):04x}')
                continue
            row = {'sample': len(C), 'scroll_row': rd('SCROLL_ROW')[0],
                   'active': len(objs),
                   'enemy_bullets': sum(1 for o in objs if o['type'] == TYPE_ENEMY_BULLET),
                   'bullet_ys': sorted(o['y'] for o in objs if o['type'] == TYPE_ENEMY_BULLET),
                   'obj_ys': sorted(o['y'] for o in objs),
                   'visible': [j for j in range(TCOUNT) if t0['visible'][j]],
                   'turret_y': [t0['y'][j] for j in range(TCOUNT) if t0['visible'][j]],
                   'results': {'baseline': base}}
            for v in variants[1:]:
                m.cmd(f'undump "{SNAP}"')
                apply_variant(v)
                row['results'][v] = run_frame_to_prepare()
            C.append(row)
            m.cmd(f'undump "{SNAP}"')
            m.cmd(f'break {S("positionBackgroundTurrets"):04x}')
        m.cmd('delete')
        R['partC'] = C

    finally:
        try:
            m.cmd('log off'); m.sock.sendall(b'quit\n'); m.sock.close()
        except Exception:
            pass
        try: proc.wait(timeout=10)
        except Exception: proc.kill()

    (out / 'turret-runtime.json').write_text(json.dumps(R, indent=2))
    _report(R)


def _frac(rows, pred):
    rows = [r for r in rows if r is not None]
    if not rows:
        return None
    n = sum(1 for r in rows if pred(r))
    return [n, len(rows)]


def _report(R):
    A = R['partA']
    print('\n== Part A  isolated turret-path CPU cost (cyc, DEN/DMA/IRQ off) ==')
    for k in sorted(A):
        if k == 'turret_X':
            continue
        print(f'  {k:<26} {A[k][0]:>5} .. {A[k][1]:<5}')

    s = R.get('partB_summary', {})
    print('\n== Part B  real run, player never fires ==')
    print(f'  frames sampled at prepareBackgroundCoarse : {s.get("frames")}')
    print(f'  total BG_COARSE_DEFERRED increments       : {s.get("total_deferrals")}')
    print(f'  coarse frames                            : {s.get("coarse_frames")}')
    print(f'  coarse frames within 15 lines of cutoff  : {s.get("coarse_within_15_of_cutoff")}')
    print(f'  deferral & turret-fired-that-frame       : {s.get("deferral_fired_frac")}')
    print(f'  deferral & glyph-published-that-frame    : {s.get("deferral_published_frac")}')
    print(f'  deferral & a turret glyph was dirty      : {s.get("deferral_any_dirty_frac")}')
    print(f'  non-deferral coarse & turret-fired       : {s.get("nondeferral_fired_frac")}')
    print(f'  non-deferral coarse & glyph-published    : {s.get("nondeferral_published_frac")}')
    causes = {}
    for r in R.get('partB_frames', []):
        if r.get('defer_step'):
            causes[r.get('defer_cause')] = causes.get(r.get('defer_cause'), 0) + 1
    print(f'  deferral cause breakdown                 : {causes}')
    for d in s.get('deferral_frames', []):
        print(f'   defer i={d["i"]:<5} rl={d["rl"]:>3} row={d["scroll_row"]:>3} '
              f'fired={d["fired"]} pub={d["published"]} dirty={d["dirty"]} '
              f'vis={d["visible"]} tY={d["turret_y"]} blts={d["bullets"]} act={d["active"]}')

    print('\n== Part C  frame-start causal isolation on frames that DEFER at baseline ==')
    hdr = R.get('partC', [])
    if hdr:
        vs = list(hdr[0]['results'].keys())
        for c in hdr:
            b = c['results']['baseline']
            print(f'  smp {c["sample"]} row {c["scroll_row"]} act {c["active"]} '
                  f'eb {c["enemy_bullets"]} vis {c["visible"]} tY {c["turret_y"]} '
                  f'bulletYs {c.get("bullet_ys")}')
            print(f'      baseline: reached r{b["reached_raster"]} batch_left {b["batch_left"]} '
                  f'batch_count {b["batch_count"]} batch_raster {b["batch_raster"]} -> DEFER')
            for v in vs[1:]:
                r = c['results'][v]
                tag = 'DEFER' if r['deferred'] else 'ADMIT'
                print(f'      {v:<22} reached r{r["reached_raster"]:>3} '
                      f'batch_left {r["batch_left"]} batch_raster {r["batch_raster"]:>3} -> {tag}')
        print()
        base_def = sum(1 for c in hdr if c['results']['baseline']['deferred'])
        for v in vs[1:]:
            removed = sum(1 for c in hdr if not c['results'][v]['deferred'])
            saved = [c['results']['baseline']['reached_raster'] - c['results'][v]['reached_raster']
                     for c in hdr]
            avg = round(sum(saved) / len(saved), 1) if saved else None
            print(f'  {v:<22} ADMITS in {removed}/{base_def} baseline-deferring frames; '
                  f'mean raster saved {avg}')


if __name__ == '__main__':
    main()
