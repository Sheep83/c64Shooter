#!/usr/bin/env python3
"""Measure player physical-sprite ownership and the player bundle's deadline margin.

Works on both the single-sprite baseline and the three-layer build.

Per sampled frame it records:
  * SORTED_COUNT, RENDER_COUNT[LIVE], BATCH_COUNT[LIVE]
  * PLAYER_HW_MASK -- which physical slots the player owns (popcount == layers
    actually presented)
  * whether the player was an INITIAL entry or came from a LIVE reuse batch
  * the deadline margin, in raster lines, between the moment the batch carrying
    the player finished being written and the player's own sprite Y.

A margin <= 0 means the player's registers were still being written when the VIC
had already started (or passed) its sprite fetch for that line.

Fixtures: ordinary play, plus synthetic near-player density built ONLY out of
the shipping object pool (no gameplay changes) -- enemies parked in the
non-recyclable band just above the player, and real TYPE_ENEMY_BULLET
projectiles low on the screen.

Transient output goes to a scratch dir outside the repo.
"""
import argparse, json, re, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'


def popcount(v):
    return bin(v).count('1')


class Probe:
    def __init__(self, port, prg, sym):
        self.proc = subprocess.Popen(
            [X64SC, '-default', '-pal', '-warp', '+sound', '-remotemonitor',
             '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
             '-autostartprgmode', '1', '-autostart', str(prg)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5)
        self.mon = Monitor(port)
        self.sym = sym
        self.mon.cmd('delete')
        self.mon.cmd('resourceset "JoyPort2Device" "37"')

    def close(self):
        try: self.mon.cmd('quit')
        except Exception: pass
        try: self.proc.wait(timeout=5)
        except Exception: self.proc.kill()

    def peek(self, addr, n=1):
        t = self.mon.cmd(f'm {addr:04x} {addr + n - 1:04x}')
        out = []
        for line in t.splitlines():
            m = re.match(r'>C:([0-9a-fA-F]{4})\s+((?:[0-9a-fA-F]{2}[ ]+)+)', line)
            if m:
                out += [int(b, 16) for b in m.group(2).split()]
        return out[:n]

    def poke(self, addr, *v):
        self.mon.cmd(f'> {addr:04x} ' + ' '.join(f'{x:02x}' for x in v))

    def g(self, name, i=0):
        return self.peek(self.sym[name] + i)[0]

    def regs(self):
        t = self.mon.cmd('r')
        m = re.search(r'^\.;[0-9a-f]{4}(?:\s+[0-9a-f]{2}){6}\s+[01]{8}\s+'
                      r'(\d+)\s+(\d+)\s+(\d+)', t, re.M)
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    def arm_frame(self):
        self.bp = int(re.search(r'BREAK: (\d+)',
                      self.mon.cmd('break exec 0000 ffff if RL == $137'))[1])

    def step(self, n=1):
        for _ in range(n):
            self.mon.cmd(f'condition {self.bp} if RL == $000'); self.mon.cmd('x')
            self.mon.cmd(f'condition {self.bp} if RL == $137'); self.mon.cmd('x')


FIXTURES = {
    # name: (enemy Y list, bullet Y list)  -- X spread across the player column
    'ordinary':            (None, None),
    'near_player_2':       ([196, 200], []),
    'near_player_4':       ([190, 196, 200, 204], []),
    'near_player_5':       ([188, 192, 196, 200, 204], []),
    'player_plus_1_bullet': ([], [206]),
    'player_plus_2_bullets': ([], [204, 210]),
    'player_plus_3_bullets': ([], [200, 206, 212]),
    'lower_pressure':      ([190, 198, 206], [202, 210]),
    'player_top':          (None, None),      # player forced to its upper bound
    'player_bottom':       (None, None),      # player forced to its lower bound
}


def clear_pool(p):
    """Release logical objects 1..15. Slot 0 is the player and is never touched
    (protected engine invariant)."""
    sym = p.sym
    for i in range(1, 16):
        p.poke(sym['OBJECT_ACTIVE'] + i, 0)
        p.poke(sym['OBJECT_DEATH_TIMER'] + i, 0)
    p.poke(sym['ENEMY_BULLET_COUNT'], 0)


def run_fixture(p, name, frames):
    sym = p.sym
    enemies, bullets = FIXTURES[name]
    if enemies is not None:
        clear_pool(p)                 # fixtures must not inherit the previous one
        p.step(2)
    # Player position for the geometry cases
    if name == 'player_top':
        p.poke(sym['OBJECT_Y'], 55)
    elif name == 'player_bottom':
        p.poke(sym['OBJECT_Y'], 237)
    if enemies is not None:
        # Park synthetic enemies/bullets in the shipping pool. Slots 1.. are the
        # generic allocation range; slot 0 stays the player (protected invariant).
        idx = 1
        for y in enemies:
            p.poke(sym['OBJECT_ACTIVE'] + idx, 1)
            p.poke(sym['OBJECT_TYPE'] + idx, 2)          # TYPE_ENEMY
            p.poke(sym['OBJECT_Y'] + idx, y)
            p.poke(sym['OBJECT_X'] + idx, 60 + 26 * idx)
            p.poke(sym['OBJECT_X_MSB'] + idx, 0)
            p.poke(sym['OBJECT_PATH_TIMER'] + idx, 255)
            p.poke(sym['OBJECT_VEL_X'] + idx, 0)
            p.poke(sym['OBJECT_VEL_Y'] + idx, 0)
            p.poke(sym['OBJECT_DEATH_TIMER'] + idx, 0)
            idx += 1
        for y in bullets:
            p.poke(sym['OBJECT_ACTIVE'] + idx, 1)
            p.poke(sym['OBJECT_TYPE'] + idx, 3)          # TYPE_ENEMY_BULLET
            p.poke(sym['OBJECT_Y'] + idx, y)
            p.poke(sym['OBJECT_X'] + idx, 70 + 20 * idx)
            p.poke(sym['OBJECT_X_MSB'] + idx, 0)
            p.poke(sym['OBJECT_VEL_X'] + idx, 0)
            p.poke(sym['OBJECT_VEL_Y'] + idx, 0)
            p.poke(sym['OBJECT_DEATH_TIMER'] + idx, 0)
            idx += 1

    masks, layers, sorted_counts, rc, bc = [], [], [], [], []
    margins = []
    for _ in range(frames):
        p.step()
        if enemies is not None:            # hold the fixture geometry steady
            i = 1
            for y in enemies:
                p.poke(sym['OBJECT_Y'] + i, y); p.poke(sym['OBJECT_ACTIVE'] + i, 1); i += 1
            for y in bullets:
                p.poke(sym['OBJECT_Y'] + i, y); p.poke(sym['OBJECT_ACTIVE'] + i, 1); i += 1
        if name == 'player_top':
            p.poke(sym['OBJECT_Y'], 55)
        elif name == 'player_bottom':
            p.poke(sym['OBJECT_Y'], 237)
        m = p.g('PLAYER_HW_MASK')
        masks.append(m); layers.append(popcount(m))
        sorted_counts.append(p.g('SORTED_COUNT'))
        live = p.g('LIVE_PLAN')
        rc.append(p.g('RENDER_COUNT', live))
        bc.append(p.g('BATCH_COUNT', live))
    return dict(fixture=name,
                frames=frames,
                player_layers_min=min(layers), player_layers_max=max(layers),
                player_layers_hist={k: layers.count(k) for k in sorted(set(layers))},
                player_masks=sorted({f'{m:08b}' for m in masks}),
                sorted_count_max=max(sorted_counts),
                render_count_max=max(rc), batch_count_max=max(bc))


def margin_probe(p, frames):
    """Worst deadline margin for the batch carrying the player.

    Breaks at rasterBatchMasksApplied (end of a LIVE batch, all its assignments
    written) and, when that batch's BATCH_PLAYER_MASK is non-zero, records
    OBJECT_Y(player) - current raster line.
    """
    sym = p.sym
    # A LIVE batch only exists when SORTED_COUNT >= 9, and the player only lands
    # in one when it is not among the first eight sorted (lowest-Y) objects. Seed
    # a stack of enemies ABOVE the player so batches are guaranteed and the
    # player is the last sorted object -- the geometry this experiment is about.
    clear_pool(p)
    for i in range(1, 13):
        p.poke(sym['OBJECT_ACTIVE'] + i, 1)
        p.poke(sym['OBJECT_TYPE'] + i, 2)
        p.poke(sym['OBJECT_Y'] + i, 60 + 11 * i)
        p.poke(sym['OBJECT_X'] + i, 40 + 16 * i)
        p.poke(sym['OBJECT_X_MSB'] + i, 0)
        p.poke(sym['OBJECT_PATH_TIMER'] + i, 255)
        p.poke(sym['OBJECT_VEL_X'] + i, 0)
        p.poke(sym['OBJECT_VEL_Y'] + i, 0)
        p.poke(sym['OBJECT_DEATH_TIMER'] + i, 0)
    p.poke(sym['OBJECT_Y'], 220)
    p.step(3)
    p.mon.cmd('delete')
    p.mon.cmd(f'break {sym["rasterBatchMasksApplied"]:04x}')
    worst = None
    samples = []
    for _ in range(frames):
        try:
            p.mon.cmd('x')
        except Exception:
            break                     # breakpoint never reached (no LIVE batches)
        lin, _, _ = p.regs()
        off = p.g('RASTER_BATCH_OFFSET')
        live = p.g('LIVE_PLAN')
        # RASTER_BATCH_OFFSET has not been incremented yet at this label.
        #
        # BATCH_PLAYER_MASK is CUMULATIVE hardware-ownership state, not "this
        # batch touched the player": it is seeded from the INITIAL entries and
        # carried forward, so a batch that never assigns the player still shows
        # the player's bit. Measuring on that gives meaningless negative margins
        # for batches firing below the player. Only batches that actually
        # ASSIGN logical object 0 have a player deadline.
        first = p.g('BATCH_FIRST_ASSIGN', off)
        cnt = p.g('BATCH_ASSIGN_COUNT', off)
        owners = [p.g('ASSIGN_OBJECT', live + first + k) for k in range(cnt)] if cnt else []
        assigns_player = 0 in owners
        pm = p.g('BATCH_PLAYER_MASK', off)
        if assigns_player:
            # hold the fixture: the seeded enemies are inert but the engine still
            # ages them out, and the player must stay low.
            p.poke(sym['OBJECT_Y'], 220)
            py = p.g('OBJECT_Y')
            margin = py - lin
            samples.append(dict(raster=lin, player_y=py, margin=margin,
                                player_mask=f'{pm:08b}',
                                layers_in_mask=popcount(pm),
                                player_assigns_in_batch=owners.count(0),
                                batch_size=cnt))
            if worst is None or margin < worst:
                worst = margin
    p.mon.cmd('delete')
    p.arm_frame()
    return dict(player_assigning_batches=len(samples), worst_margin_lines=worst,
                max_player_assigns_in_one_batch=max(
                    (x['player_assigns_in_batch'] for x in samples), default=0),
                sample=samples[:6])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6800)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--frames', type=int, default=60)
    ap.add_argument('--warmup', type=int, default=260,
                    help='frames of real play before the ordinary fixture, so the '
                         'wave director has actually spawned enemies')
    ap.add_argument('--label', default='build')
    ap.add_argument('--fixtures', nargs='+', default=list(FIXTURES))
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    sym = symbols(Path(a.symbols).resolve())
    p = Probe(a.port, Path(a.prg).resolve(), sym)
    results = {'label': a.label, 'fixtures': [], 'margin': None}
    try:
        p.arm_frame()
        for _ in range(300):
            p.step()
            if p.g('GAME_STATE') == 0:
                break
        p.mon.cmd('jpdb 1 ef'); p.step(4); p.mon.cmd('jpdb 1 ff'); p.step(4)
        for _ in range(300):
            p.step()
            if p.g('GAME_STATE') == 1:
                break
        p.poke(sym['PLAYER_LIVES'], 255)
        p.step(20)
        for name in a.fixtures:
            if name == 'ordinary':
                p.step(a.warmup)      # let the director actually spawn a wave
            r = run_fixture(p, name, a.frames)
            results['fixtures'].append(r)
            print(json.dumps(r), flush=True)
        results['margin'] = margin_probe(p, 400)
        print(json.dumps(results['margin'], indent=2), flush=True)
    finally:
        p.close()
    if a.out:
        Path(a.out).write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
