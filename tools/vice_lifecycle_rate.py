#!/usr/bin/env python3
"""Pre/post-fix rate probe: which screen page does the game END on?

For each kill delay: start a game, play that many frames, apply one fatal hit,
and record $D018 / BG_ACTIVE_PAGE once GAME_STATE reaches GAME_OVER -- i.e. the
first sample after endGame. A game that ends with $D018 selecting page B leaves
the VIC displaying $2800 while every menu / GAME OVER / high-score routine draws
into $0400.

Transient output goes to a scratch dir outside the repo. Joystick neutral except
the single fire tap that starts the game.
"""
import argparse, json, re, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
# "ENTER YOUR INITIALS" in screencode_upper, as drawInitialsScreen stamps it.
PROMPT = bytes([5, 14, 20, 5, 18, 32, 25, 15, 21, 18, 32, 9, 14, 9, 20, 9, 1, 12, 19])


def one(port, prg, sym, delay, probe_initials=False, scratch=None):
    proc = subprocess.Popen(
        [X64SC, '-default', '-pal', '-warp', '+sound', '-remotemonitor',
         '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
         '-autostartprgmode', '1', '-autostart', str(prg)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    mon = Monitor(port)
    try:
        mon.cmd('delete')
        mon.cmd('resourceset "JoyPort2Device" "37"')
        bp = int(re.search(r'BREAK: (\d+)',
                 mon.cmd('break exec 0000 ffff if RL == $137'))[1])

        def step(n=1):
            for _ in range(n):
                mon.cmd(f'condition {bp} if RL == $000'); mon.cmd('x')
                mon.cmd(f'condition {bp} if RL == $137'); mon.cmd('x')

        def peek(addr, count=1):
            text = mon.cmd(f'm {addr:04x} {addr + count - 1:04x}')
            out = []
            for line in text.splitlines():
                m = re.match(r'>C:([0-9a-fA-F]{4})\s+((?:[0-9a-fA-F]{2}[ ]+)+)', line)
                if m:
                    out += [int(b, 16) for b in m.group(2).split()]
            return out[:count]

        def g(name):
            return peek(sym[name])[0]

        for _ in range(300):
            step()
            if g('GAME_STATE') == 0:
                break
        mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)
        for _ in range(300):
            step()
            if g('GAME_STATE') == 1:
                break
        mon.cmd(f'> {sym["SCORE_LO"]:04x} 40 e2 01')
        mon.cmd(f'> {sym["PLAYER_LIVES"]:04x} 01')
        step(delay)
        mon.cmd(f'> {sym["PLAYER_HIT"]:04x} 01')
        for _ in range(400):
            if g('GAME_STATE') == 2:
                break
            step()
        rec = dict(delay=delay, game=g('GAME_STATE'), d018=peek(0xd018)[0],
                   bg_active_page=g('BG_ACTIVE_PAGE'))
        rec['visible_page'] = 'A' if (rec['d018'] & 0xf0) == 0x10 else 'B'
        rec['bad'] = rec['visible_page'] != 'A'
        if probe_initials:
            for _ in range(600):
                if g('GAME_STATE') == 3:
                    break
                step()
            if g('GAME_STATE') == 3:
                step(4)
                path = Path(scratch) / f'p{port}.bin'
                mon.cmd(f'bsave "{path}" 0 0400 0800'); a = path.read_bytes()
                mon.cmd(f'bsave "{path}" 0 2800 2c00'); b = path.read_bytes()
                path.unlink(missing_ok=True)
                pr = 10 * 40 + 10
                rec['prompt_in_pageA'] = bytes(a[pr:pr + 19]) == PROMPT
                rec['prompt_in_pageB'] = bytes(b[pr:pr + 19]) == PROMPT
                rec['visible_has_prompt'] = (rec['prompt_in_pageA']
                                             if rec['visible_page'] == 'A'
                                             else rec['prompt_in_pageB'])
                vis = a if rec['visible_page'] == 'A' else b
                rec['visible_nonspace'] = sum(1 for c in vis[:1000] if c not in (32, 0))
        return rec
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--delays', type=int, nargs='+',
                    default=list(range(20, 200, 12)))
    ap.add_argument('--port', type=int, default=6560)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--initials', action='store_true')
    ap.add_argument('--scratch', default=tempfile.gettempdir() + '/c64-lifecycle')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    Path(a.scratch).mkdir(parents=True, exist_ok=True)
    sym = symbols(Path(a.symbols).resolve())
    prg = Path(a.prg).resolve()
    rows = []
    for i, d in enumerate(a.delays):
        r = one(a.port + i, prg, sym, d, a.initials, a.scratch)
        rows.append(r); print(r, flush=True)
    bad = sum(1 for r in rows if r['bad'])
    summary = dict(runs=len(rows), ended_on_page_B=bad,
                   rate=f'{bad}/{len(rows)}', rows=rows)
    print(json.dumps(summary, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(summary, indent=2))
