#!/usr/bin/env python3
"""Targeted probe for the human-observed one-frame background hitch on a turret kill.

Hypothesis: a fatal turret kill runs awardKillScore -> displayScore synchronously
inside updateObjects on the kill frame; the extra CPU pushes the raster line that
prepareBackgroundCoarse is reached at; on a frame that is also a coarse
transition and already under load, that crosses BG_COARSE_LATEST_START (184) and
the coarse copy is safely deferred (BG_COARSE_DEFERRED++), holding fine scroll
one extra frame while the PAL frame stays exactly 19656 cycles.

Part A  isolated CPU cost of the fatal-hit chain vs an ordinary non-fatal hit,
        and the next-frame DEAD-style underlay publication, over a score sweep
        (displayScore is a repeated-subtraction decimal conversion).

Part B  real IRQ/display/scroller. Break at every prepareBackgroundCoarse and
        record the raster line it is reached at + BG_COARSE_PENDING/DEFERRED,
        building the reached-raster distribution on real coarse frames and how
        near the 184 cutoff they naturally sit.

Part C  matched causal test. At updatePlayerFire on a real frame: dump a VICE
        snapshot, force this frame to be a coarse frame, run the FATAL kill,
        record prepare's reached raster + deferral; undump; run the identical
        frame with a NON-FATAL hit; compare. Repeat across many real frames and
        score magnitudes.
"""
import argparse, json, re, socket, subprocess, time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

DIV = 3
CUTOFF = 184
SNAP = '/tmp/vice_killtiming.vsf'


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
    m.cmd('delete')
    m.cmd('resourceset "JoyPort2Device" "37"')
    m.cmd(f'break {sym["waitFireRelease"]:04x}')
    m.cmd('jpdb 1 ef')
    m.cmd('x')
    m.cmd('jpdb 1 ff')
    m.cmd('delete')
    m.cmd(f'break {sym["applyFineScroll"]:04x}')
    m.cmd('x')
    m.cmd('delete')


_RREG = re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')
def clk(reg): return int(_RREG.search(reg)[3])
def rl(reg):  return int(_RREG.search(reg)[1])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6560)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/kill-timing'))
    ap.add_argument('--frames', type=int, default=1600)
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

        # ---------------- Part A ----------------------------------------
        start_playing(m, sym)
        m.cmd('> d01a 00'); m.cmd('> dc0d 7f'); m.cmd('> d015 00'); m.cmd('> d011 00')
        m.cmd('break 700f')
        tx = rd('TURRET_X_LO', 3); txh = rd('TURRET_X_HI', 3)
        tx0 = tx[0] + 256 * txh[0]
        A = {'turret0_X': tx0, 'non_fatal_hit': [], 'fatal_hit': {}, 'displayScore': {},
             'dead_publication': []}
        for _ in range(3):
            put('TURRET_HEALTH', [3, 0, 0]); put('TURRET_VISIBLE', [1, 0, 0])
            put('TURRET_DESIRED_STYLE', [0, 0, 0])
            A['non_fatal_hit'].append(call('hitCannonTarget', 0x80)[0])
        for sc in (0, 2500, 9900, 45500, 65500):
            s = []
            for _ in range(3):
                put('TURRET_HEALTH', [1, 0, 0]); put('TURRET_VISIBLE', [1, 0, 0])
                put('TURRET_DESTROYED', 0); put('SCORE_LO', [sc & 255, sc >> 8])
                s.append(call('hitCannonTarget', 0x80)[0])
            A['fatal_hit'][sc] = s
            put('SCORE_LO', [(sc + 100) & 255, (sc + 100) >> 8])
            A['displayScore'][sc + 100] = [call('displayScore')[0] for _ in range(3)]
        put('TURRET_DESIRED_STYLE', [7, 0, 0]); put('TURRET_SHOWN_STYLE', [0, 0, 0])
        A['dead_publication'] = [call('publishTurretGlyphs')[0] for _ in range(3)]
        R['partA'] = A

        # ---------------- fresh boot for real-run parts ----------------
        m.sock.sendall(b'quit\n'); m.sock.close(); proc.wait(timeout=10)
        proc, m = launch(args.port, out)
        start_playing(m, sym)
        put('PLAYER_LIVES', 0xff)
        m.cmd(f'break {S("prepareBackgroundCoarse"):04x}')
        for _ in range(200):
            m.cmd('x')                       # stabilise the scroll cycle

        # ---------------- Part B : reached-raster distribution --------
        B = []
        for _ in range(args.frames):
            m.cmd('x')
            reg = m.cmd('r')
            pend = rd('BG_COARSE_PENDING')[0]
            defr = rd('BG_COARSE_DEFERRED')[0]
            bo = rd('RASTER_BATCH_OFFSET')[0]; be = rd('RASTER_BATCH_END')[0]
            B.append(dict(rl=rl(reg), pending=pend, deferred=defr,
                          batches_left=(be - bo) & 255))
        R['partB_raw'] = B
        coarse = [r for r in B if r['pending']]
        near = [r for r in coarse if 184 - 20 <= r['rl'] < 184]
        over = [r for r in coarse if r['rl'] >= 184]
        R['partB'] = dict(
            total_prepare_calls=len(B), coarse_frames=len(coarse),
            coarse_rl_min=min((r['rl'] for r in coarse), default=None),
            coarse_rl_max=max((r['rl'] for r in coarse), default=None),
            coarse_rl_sorted=sorted(r['rl'] for r in coarse),
            coarse_within_20_of_cutoff=len(near),
            coarse_at_or_over_cutoff=len(over),
            deferrals_seen=(B[-1]['deferred'] - B[0]['deferred']) & 255 if B else 0)
        m.cmd('delete')

        # ---------------- Part C : matched fatal vs non-fatal on a NATURAL
        # coarse frame (do not distort the frame's pacing by forcing fine=7) --
        def run_variant(fatal, score, force_coarse):
            if force_coarse:
                put('SCROLL_FINE', 7); put('SCROLL_FRAME_COUNT', DIV - 1)
            put(0x30, 0xef)                                             # JOY_STATE: fire held
            put('PLAYER_STATE', 0); put('PLAYER_FIRE_COOLDOWN_TIMER', 0)
            put(S('OBJECT_X') + 0, tx0 & 255); put(S('OBJECT_X_MSB') + 0, tx0 >> 8)
            put(S('OBJECT_Y') + 0, 230); put('OBJECT_TYPE', 1)
            put('TURRET_HEALTH', [1 if fatal else 3, 0, 0])
            put('TURRET_VISIBLE', [1, 1, 1]); put(S('TURRET_Y') + 0, 190)
            put('TURRET_DESTROYED', 0); put('SCORE_LO', [score & 255, score >> 8])
            pre_def = rd('BG_COARSE_DEFERRED')[0]
            pre_des = rd('TURRET_DESTROYED')[0]
            m.cmd(f'break {S("prepareBackgroundCoarse"):04x}')
            m.cmd('x'); reg = m.cmd('r')
            reached = rl(reg); pend = rd('BG_COARSE_PENDING')[0]
            m.cmd('delete')
            m.cmd(f'break {S("finishBackgroundCoarse"):04x}')
            m.cmd('x'); m.cmd('delete')
            post_def = rd('BG_COARSE_DEFERRED')[0]
            post_des = rd('TURRET_DESTROYED')[0]
            sc = rd('SCORE_LO', 2); hp = rd('TURRET_HEALTH')[0]
            fin = rd('BG_COARSE_FINISH')[0]
            return dict(fatal=fatal, score=score, reached_raster=reached,
                        coarse_frame=bool(pend),
                        deferred=(post_def - pre_def) & 255,
                        coarse_finish_armed=fin,
                        kill=(post_des - pre_des) & 255,
                        score_after=sc[0] + 256 * sc[1], hp_after=hp)

        C = []
        m.cmd(f'break {S("updatePlayerFire"):04x}')
        i = 0
        while len(C) < 40 and i < 4000:
            i += 1
            m.cmd('x'); m.cmd('delete')
            fine = rd('SCROLL_FINE')[0]; cnt = rd('SCROLL_FRAME_COUNT')[0]
            natural_coarse = (fine == 7 and cnt == DIV - 1)
            # 4700 = a representative mid-game score (digit sum 11); also a cheap one
            score = 4700 if len(C) % 2 == 0 else 10000
            m.cmd(f'dump "{SNAP}"')
            fa = run_variant(True, score, force_coarse=not natural_coarse)
            m.cmd(f'undump "{SNAP}"')
            nf = run_variant(False, score, force_coarse=not natural_coarse)
            C.append(dict(natural_coarse=natural_coarse, fatal=fa, nonfatal=nf,
                          delta_raster=fa['reached_raster'] - nf['reached_raster'],
                          fatal_deferred=fa['deferred'], nonfatal_deferred=nf['deferred']))
            m.cmd(f'break {S("updatePlayerFire"):04x}')
        m.cmd('delete')
        R['partC'] = C

    finally:
        try:
            m.cmd('log off'); m.sock.sendall(b'quit\n'); m.sock.close()
        except Exception:
            pass
        try: proc.wait(timeout=10)
        except Exception: proc.kill()

    (out / 'kill-timing.json').write_text(json.dumps(R, indent=2))

    A = R['partA']
    nf = A['non_fatal_hit']
    print('== Part A  isolated CPU cost ==')
    print(f'  non-fatal hit          : {min(nf)}..{max(nf)} cyc')
    for sc, s in A['fatal_hit'].items():
        d = A['displayScore'][sc + 100]
        print(f'  fatal hit @score {sc:>6} : {min(s)}..{max(s)} cyc   (displayScore alone @{sc+100:>6}: {min(d)}..{max(d)})')
    dp = A['dead_publication']
    print(f'  DEAD publication (n+1)  : {min(dp)}..{max(dp)} cyc  (runs at frame start, far from prepare)')
    lo = min(min(v) for v in A['fatal_hit'].values()) - max(nf)
    hi = max(max(v) for v in A['fatal_hit'].values()) - min(nf)
    print(f'  => fatal adds ~{lo}..{hi} cyc synchronously on the kill frame  (~{lo//63}..{hi//63} raster lines)')

    b = R['partB']
    print('\n== Part B  real coarse frames: raster line prepareBackgroundCoarse is reached at ==')
    print(f'  coarse frames sampled  : {b["coarse_frames"]}')
    print(f'  reached-raster min/max : {b["coarse_rl_min"]} / {b["coarse_rl_max"]}   (cutoff {CUTOFF})')
    print(f'  within 20 lines of cutoff: {b["coarse_within_20_of_cutoff"]}   at/over cutoff: {b["coarse_at_or_over_cutoff"]}')
    print(f'  natural deferrals over run: {b["deferrals_seen"]}')

    print('\n== Part C  matched fatal vs non-fatal on the SAME coarse frame ==')
    print('  nat score  reached(F)  reached(NF)  d_raster  def(F)  def(NF)  kill hp')
    tipped = 0
    for c in R['partC']:
        f, n = c['fatal'], c['nonfatal']
        tip = c['fatal_deferred'] and not c['nonfatal_deferred']
        tipped += bool(tip)
        print(f"  {int(c.get('natural_coarse',0))!s:>3} {f['score']:>5}  {f['reached_raster']:>10}  "
              f"{n['reached_raster']:>11}  {c['delta_raster']:>8}  {c['fatal_deferred']:>6}  "
              f"{c['nonfatal_deferred']:>7}  {f['kill']:>4} {f['hp_after']}"
              f"{'   <-- FATAL-ONLY DEFERRAL' if tip else ''}")
    print(f'  frames where the fatal kill ALONE tipped a coarse frame into deferral: {tipped}/{len(R["partC"])}')
    


if __name__ == '__main__':
    main()
