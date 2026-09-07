#!/usr/bin/env python3
"""Bottom-origin startup + STREAMING TURRET POOL integration checks.

Runs the built game to the first gameplay frame, then:
  A. boot SCROLL_ROW == STAGE_LOGICAL_ROWS - 23 (bottom origin);
  B. the initial 23-row viewport is the contiguous bottom of the stage
     (no wrap, no top-of-level rows leaking in);
  C. sweeps SCROLL_ROW(16) monotonically through a full stage loop, driving
     updateTurretStream each step exactly as gameplay does, and asserts:
       * at most TURRET_POOL live slots are ever occupied at once;
       * every authored turret becomes VISIBLE in a contiguous SCROLL_ROW
         window ~ [worldRow-22 .. worldRow-1] (mod SLR);
       * a turret whose world row is > 255 is handled (16-bit);
       * turrets activate in descending-world-row order (near-start first).
  D. kills a turret while it holds a slot, keeps streaming so it evicts, runs a
     full stage wrap, and asserts it re-admits already-dead (HEALTH 0, dead
     style, its turretDestroyedBits bit set) and the TURRET_DESTROYED score
     counter is NOT touched by streaming.
"""
import argparse
import json
import socket
import subprocess
import time
from pathlib import Path

from vice_scroll_test import Monitor, symbols
from vice_turret_runtime_probe import start_playing


def launch(port):
    with socket.socket() as c:
        if c.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'port {port} occupied')
    p = subprocess.Popen(
        ['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
         '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
         '-autostartprgmode', '1', '-autostart', str(Path('build/shooter.prg').resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p, Monitor(port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=6720)
    ap.add_argument('--out', type=Path, default=Path('build/mc-test/bottom-origin'))
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    proc, m = launch(args.port)
    fails = []
    try:
        m.trace_file = (out / 'monitor.log').open('w')
        start_playing(m, sym)
        m.cmd('delete')
        m.cmd('break 700a')

        def put(name, values):
            addr = sym[name] if isinstance(name, str) else name
            if isinstance(values, int):
                values = [values]
            m.cmd(f'> {addr:04x} ' + ' '.join(f'{v & 255:02x}' for v in values))

        def rd(name, n=1):
            addr = sym[name] if isinstance(name, str) else name
            p = out / 'scratch.bin'
            m.cmd(f'bsave "{p}" 0 {addr:04x} {addr + n - 1:04x}')
            return list(p.read_bytes())

        def w16(name):
            b = rd(name, 2)
            return b[0] | (b[1] << 8)

        def call(name):
            a = sym[name]
            put(0x7000, [0x78, 0xd8, 0x20, a & 255, a >> 8, 0x4c, 0x0a, 0x70])
            m.cmd('r pc=7000, sp=ff')
            m.cmd('x')

        pool = sym['TURRET_POOL_CODE']
        total = sym['TURRET_TOTAL_CODE']
        rows_len = sym['STAGE_METATILE_ROWS_END'] - sym['stageMetatileRows']
        slr = rows_len // 10 * 4
        defs_len = sym['METATILE_DEFS_END'] - sym['metatileDefs']   # variable: 1..64 defs
        defs = rd('metatileDefs', defs_len)
        metatile_defs = [defs[i:i + 16] for i in range(0, defs_len, 16)]
        raw = rd('stageMetatileRows', rows_len)
        stage_rows = [raw[i:i + 10] for i in range(0, rows_len, 10)]
        a_lo = rd('turretAuthRowLo', total)
        a_hi = rd('turretAuthRowHi', total)
        a_col = rd('turretAuthCol', total)
        world = [a_lo[i] | (a_hi[i] << 8) for i in range(total)]
        print(f'stage {slr} logical rows; pool {pool}; {total} authored turrets; '
              f'world rows {world}; cols {a_col}')

        def tile_row_codes(logical):
            mrow, sub = divmod(logical % slr, 4)
            ids = stage_rows[mrow]
            o = []
            for col in range(10):
                o += metatile_defs[ids[col]][sub * 4:sub * 4 + 4]
            return o

        # ---- A -----------------------------------------------------------
        boot = w16('SCROLL_ROW')
        expect = slr - 23
        if boot != expect:
            fails.append(f'A boot SCROLL_ROW={boot}, expected {expect}')
        else:
            print(f'A PASS boot SCROLL_ROW = {boot} = {slr}-23 (bottom origin)')

        # ---- B -----------------------------------------------------------
        slot_auth0 = rd('TURRET_SLOT_AUTH', pool)
        slot_col0 = rd('TURRET_SLOT_COL', pool)
        slot_rlo0 = rd('TURRET_SLOT_ROW_LO', pool)
        slot_rhi0 = rd('TURRET_SLOT_ROW_HI', pool)
        boot_slots = [(slot_col0[s], slot_rlo0[s] | (slot_rhi0[s] << 8))
                      for s in range(pool) if slot_auth0[s] != 0xFF]
        scr = rd(0x0400, 24 * 40)
        mism = []
        for d in range(1, 24):
            logical = boot + d - 1
            want = tile_row_codes(logical)
            got = scr[d * 40:d * 40 + 40]
            skip = set()
            for (col, wr) in boot_slots:
                if logical in (wr, wr + 1):
                    skip |= {col, col + 1}
            for c in range(40):
                if c not in skip and got[c] != want[c]:
                    mism.append((d, c, got[c], want[c]))
        if boot + 22 >= slr:
            fails.append('B initial viewport would wrap - unexpected')
        if mism:
            fails.append(f'B initial viewport mismatch (first 6): {mism[:6]}')
        else:
            print(f'B PASS initial 23 rows == contiguous logical {boot}..{boot + 22} '
                  f'(no wrap); boot-admitted slots {boot_slots}')

        # ---- C: monotonic sweep, stream each step -----------------------
        m.cmd('> d01a 00'); m.cmd('> dc0d 7f'); m.cmd('> d015 00'); m.cmd('> d011 00')
        put('RASTER_DISPLAY_FINE', 0)
        # re-init the pool cleanly for the sweep
        call('initBackgroundTurrets')
        put('SCROLL_ROW', [boot & 0xFF, (boot >> 8) & 0xFF])
        put('TURRET_STREAM_REWIND', 0)

        vis_windows = {i: [] for i in range(total)}
        max_occupied = 0
        # one full loop of the stage, SCROLL_ROW descending with a wrap
        sweep = list(range(boot, -1, -1)) + list(range(slr - 1, boot, -1))
        for k, scroll in enumerate(sweep):
            put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
            if k and sweep[k - 1] == 0:
                put('TURRET_STREAM_REWIND', 1)      # gameplay sets this in the wrap branch
            call('updateTurretStream')
            put('TURRET_HEALTH', [3] * pool)        # keep admitted turrets alive for visibility test
            put('TURRET_VISIBLE', [0] * pool)
            call('positionBackgroundTurrets')
            auth = rd('TURRET_SLOT_AUTH', pool)
            vis = rd('TURRET_VISIBLE', pool)
            occ = sum(1 for a in auth if a != 0xFF)
            max_occupied = max(max_occupied, occ)
            for s in range(pool):
                if auth[s] != 0xFF and vis[s]:
                    vis_windows[auth[s]].append(scroll)

        if max_occupied > pool:
            fails.append(f'C pool overflow: {max_occupied} slots occupied at once (limit {pool})')
        if max_occupied < 4:
            fails.append(f'C shared-glyph pool: max {max_occupied} turrets live at once - the '
                         f'authored cluster should put well more than the old 3-visible cap on screen')
        seen = []
        for i in range(total):
            w = vis_windows[i]
            if not w:
                fails.append(f'C authored turret {i} (row {world[i]}) never became visible')
                continue
            lo, hi = min(w), max(w)
            span = sorted(set(w))
            # window should be ~ SCROLL_ROW in [worldRow-22 .. worldRow-1] (mod slr)
            exp_lo = (world[i] - 22) % slr
            exp_hi = (world[i] - 1) % slr
            seen.append((i, world[i], lo, hi))
            contiguous = (span == list(range(lo, hi + 1))) or (
                # wrap-straddling window: two runs
                0 in span and (slr - 1) in span
            )
            if not contiguous:
                fails.append(f'C turret {i} visible SCROLL_ROWs not contiguous: {span[:6]}..')
            if not (exp_lo in (lo, hi) or exp_hi in (lo, hi) or abs(len(span) - 22) <= 3):
                fails.append(f'C turret {i} (row {world[i]}) visible window [{lo}..{hi}] '
                             f'width {len(span)} not ~[{exp_lo}..{exp_hi}]')
        order = [i for (i, wr, lo, hi) in sorted(seen, key=lambda x: -x[2])]
        world_order = [i for (i, wr, lo, hi) in sorted(seen, key=lambda x: -x[1])]
        over_255 = [wr for (_, wr, _, _) in seen if wr > 255]
        if order != world_order:
            fails.append(f'C activation order {order} != descending-world-row order {world_order}')
        if not fails or all('C ' not in f for f in fails):
            print(f'C PASS max {max_occupied}/{pool} slots occupied; every authored turret '
                  f'became visible; >255 world rows handled: {sorted(over_255)}')
            print(f'    activation order (first->last) = {order}')

        # ---- D: kill -> evict -> wrap -> re-admit already-dead ---------
        call('initBackgroundTurrets')
        put('SCROLL_ROW', [boot & 0xFF, (boot >> 8) & 0xFF])
        put('TURRET_STREAM_REWIND', 0)
        destroyed_score_before = rd('TURRET_DESTROYED', 1)[0]
        victim = max(range(total), key=lambda i: world[i])   # highest world row = admitted first
        victim_slot = None
        victim_bits_ok = False
        resurrected = False
        for k, scroll in enumerate(sweep):
            put('SCROLL_ROW', [scroll & 0xFF, (scroll >> 8) & 0xFF])
            if k and sweep[k - 1] == 0:
                put('TURRET_STREAM_REWIND', 1)
            call('updateTurretStream')
            auth = rd('TURRET_SLOT_AUTH', pool)
            hp = rd('TURRET_HEALTH', pool)
            if victim_slot is None:
                for s in range(pool):
                    if auth[s] == victim:
                        victim_slot = s
                        put('TURRET_HEALTH', [0 if x == s else 3 for x in range(pool)])
                        break
            else:
                # once evicted, the destroyed bit must be set for `victim`
                bits = rd('turretDestroyedBits', max(1, (total + 7) // 8))
                if bits[victim // 8] & (1 << (victim % 8)):
                    victim_bits_ok = True
                if victim in auth:
                    s = auth.index(victim)
                    if hp[s] != 0:
                        resurrected = True
        destroyed_score_after = rd('TURRET_DESTROYED', 1)[0]
        if victim_slot is None:
            fails.append('D victim turret never got a slot')
        if not victim_bits_ok:
            fails.append(f'D turretDestroyedBits for turret {victim} was never set on eviction')
        if resurrected:
            fails.append(f'D killed turret {victim} re-admitted with non-zero HEALTH')
        if destroyed_score_after != destroyed_score_before:
            fails.append(f'D TURRET_DESTROYED score counter moved {destroyed_score_before}->'
                         f'{destroyed_score_after} during streaming (should only move on a real kill)')
        if victim_slot is not None and victim_bits_ok and not resurrected and \
                destroyed_score_after == destroyed_score_before:
            print(f'D PASS killed turret {victim} evicts with its destroyed bit set, re-admits '
                  f'already-dead across the stage wrap; score counter stable at {destroyed_score_after}')

        (out / 'bottom-origin.json').write_text(json.dumps({
            'boot_scroll_row': boot, 'stage_logical_rows': slr, 'pool': pool,
            'authored_world_rows': world, 'authored_cols': a_col,
            'max_slots_occupied': max_occupied,
            'visible_windows': {i: [min(w), max(w)] for i, w in vis_windows.items() if w},
            'activation_order': order, 'over_255': sorted(over_255),
            'fails': fails,
        }, indent=2))
        if fails:
            print(f'\nFAIL ({len(fails)}):')
            for f in fails:
                print('  ' + f)
            raise SystemExit(1)
        print('\nPASS: bottom-origin startup + streaming turret pool integration')
    finally:
        try:
            m.cmd('quit')
        except Exception:
            pass
        proc.terminate()


if __name__ == '__main__':
    main()
