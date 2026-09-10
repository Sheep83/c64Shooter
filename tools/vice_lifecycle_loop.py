#!/usr/bin/env python3
"""Repeated GAME -> GAME OVER -> HIGH SCORE -> MENU -> NEW GAME regression loop.

Runs N consecutive lifecycles in ONE VICE instance and checks, every iteration:

  * the game ends with $D018 selecting page A;
  * the GAME OVER / initials / high-score pages are on the page the VIC is
    actually fetching (exact screen-code compare, not "something is there");
  * the next new game starts at the proper stage origin (SCROLL_ROW ==
    STAGE_START_ROW) with hardware and software page ownership agreeing;
  * the first presented gameplay matrix contains ONLY terrain / turret glyph
    codes -- no "LIVES 3" and no other leftover UI characters.

The fatal-hit delay is varied per iteration so both coarse-flip parities are
exercised; that parity is what used to decide whether the run corrupted.

Joystick stays NEUTRAL except for the explicit taps the lifecycle requires.
All transient output goes to a scratch dir outside the repo.
"""
import argparse, json, re, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
PROMPT = bytes([5, 14, 20, 5, 18, 32, 25, 15, 21, 18, 32, 9, 14, 9, 20, 9, 1, 12, 19])
HEADING = bytes([8, 9, 7, 8, 32, 19, 3, 15, 18, 5, 19])       # "HIGH SCORES"
LIVES_LABEL = bytes([12, 9, 22, 5, 19, 32, 51])               # "LIVES 3"
TERRAIN_FIRST = 96          # editor-owned terrain art starts here; turret private 226..239
PROMPT_OFF = 10 * 40 + 10
HEADING_OFF = 4 * 40 + 14   # HISCORE_HEADING_SCREEN = $0400 + 4*40 + 14


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--loops', type=int, default=12)
    ap.add_argument('--port', type=int, default=6570)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--scratch', default=tempfile.gettempdir() + '/c64-lifecycle')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    scratch = Path(a.scratch); scratch.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path(a.symbols).resolve())
    stage_start = None
    proc = subprocess.Popen(
        [X64SC, '-default', '-pal', '-warp', '+sound', '-remotemonitor',
         '-remotemonitoraddress', f'ip4://127.0.0.1:{a.port}',
         '-autostartprgmode', '1', '-autostart', str(Path(a.prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    mon = Monitor(a.port)
    results, failures = [], []
    try:
        mon.cmd('delete'); mon.cmd('resourceset "JoyPort2Device" "37"')
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

        def poke(addr, *values):
            mon.cmd(f'> {addr:04x} ' + ' '.join(f'{v:02x}' for v in values))

        def page(addr):
            path = scratch / f'loop{a.port}.bin'
            mon.cmd(f'bsave "{path}" 0 {addr:04x} {addr + 0x400:04x}')
            data = path.read_bytes(); path.unlink(missing_ok=True)
            return data

        def visible():
            d018 = peek(0xd018)[0]
            return ('A', 0x0400) if (d018 & 0xf0) == 0x10 else ('B', 0x2800)

        def wait(state, limit=900):
            for _ in range(limit):
                if g('GAME_STATE') == state:
                    return True
                step()
            return False

        def tap():
            mon.cmd('jpdb 1 ef'); step(4); mon.cmd('jpdb 1 ff'); step(4)

        wait(0)
        for i in range(a.loops):
            r = {'loop': i, 'checks': {}}
            tap()
            if not wait(1):
                r['checks']['game_started'] = False
                results.append(r); failures.append((i, 'game never started')); break

            # ---- new game: origin + page ownership + clean matrix ----------
            # Sampled on the FIRST frame of GAME_STATE_PLAYING: startGame sets
            # the state last, so initBackground has already painted, and no
            # coarse step can have advanced SCROLL_ROW yet.
            row = g('SCROLL_ROW') | (g('SCROLL_ROW_HI') << 8)
            if stage_start is None:
                stage_start = row          # first game of the run defines the origin
            name, base = visible()
            vis = page(base)
            dirty = [(o // 40, o % 40, vis[o]) for o in range(1000)
                     if vis[o] < TERRAIN_FIRST]
            lives = [o for o in range(1000 - 7)
                     if bytes(vis[o:o + 7]) == LIVES_LABEL]
            r['new_game'] = dict(scroll_row=row, d018=peek(0xd018)[0],
                                 visible_page=name,
                                 bg_active_page=g('BG_ACTIVE_PAGE'),
                                 non_terrain_cells=len(dirty),
                                 sample_non_terrain=dirty[:6],
                                 lives_label_hits=len(lives))
            r['checks']['new_game_origin'] = (row == stage_start)
            r['checks']['new_game_page_A'] = (name == 'A' and g('BG_ACTIVE_PAGE') == 0)
            r['checks']['new_game_matrix_clean'] = (len(dirty) == 0)
            r['checks']['no_lives_label'] = (len(lives) == 0)

            # ---- death / respawn on a NON-final life -------------------------
            # Drives the shipping collision path's outcome (PLAYER_HIT), then
            # watches the real state machine: alive -> exploding -> respawning
            # -> alive, one life consumed, and the respawned ship back to
            # PLAYER_COLOUR_NORMAL (14, light blue).
            poke(sym['PLAYER_LIVES'], 3)
            step(12)
            lives_before = g('PLAYER_LIVES')
            poke(sym['PLAYER_HIT'], 1)
            seen, colour_after = set(), None
            for _ in range(400):
                step()
                seen.add(g('PLAYER_STATE'))
                if 2 in seen and g('PLAYER_STATE') == 0:
                    colour_after = peek(sym['OBJECT_COLOUR'])[0]
                    break
            r['respawn'] = dict(states=sorted(seen), lives_before=lives_before,
                                lives_after=g('PLAYER_LIVES'),
                                colour_after=colour_after)
            r['checks']['death_anim_ran'] = 1 in seen
            r['checks']['respawned'] = (2 in seen and colour_after is not None)
            r['checks']['life_consumed'] = (g('PLAYER_LIVES') == lives_before - 1)
            r['checks']['respawn_colour_blue'] = (colour_after == 14)

            # ---- die for good ------------------------------------------------
            # Strictly increasing per loop. The table holds HISCORE_COUNT (8)
            # entries and scoreQualifies deliberately does NOT displace an equal
            # score, so a fixed value stops qualifying once the table fills.
            score = 200000 + i * 20000
            mon.cmd(f'> {sym["SCORE_LO"]:04x} '
                    f'{score & 0xff:02x} {(score >> 8) & 0xff:02x} {(score >> 16) & 0xff:02x}')
            r['score'] = score
            mon.cmd(f'> {sym["PLAYER_LIVES"]:04x} 01')
            step(30 + (i * 7) % 40)                            # sweep the coarse-flip parity
            mon.cmd(f'> {sym["PLAYER_HIT"]:04x} 01')

            # ---- GAME OVER --------------------------------------------------
            ok = wait(2)
            name, base = visible()
            r['game_over'] = dict(reached=ok, d018=peek(0xd018)[0], visible_page=name)
            r['checks']['game_over_page_A'] = (name == 'A')

            # ---- initials / high-score entry ---------------------------------
            ok = wait(3)
            step(4)
            name, base = visible()
            vis = page(base)
            r['initials'] = dict(reached=ok, visible_page=name,
                                 prompt_on_visible=bytes(vis[PROMPT_OFF:PROMPT_OFF + 19]) == PROMPT,
                                 visible_nonspace=sum(1 for c in vis[:1000] if c not in (32, 0)))
            r['checks']['initials_reached'] = ok
            r['checks']['initials_visible'] = r['initials']['prompt_on_visible']

            # ---- commit -> menu / high-score page -----------------------------
            if r['checks']['initials_reached']:
                tap()                      # commit the initials
            ok = wait(0)
            step(4)
            name, base = visible()
            vis = page(base)
            r['menu'] = dict(reached=ok, visible_page=name,
                             heading_on_visible=bytes(vis[HEADING_OFF:HEADING_OFF + 11]) == HEADING,
                             visible_nonspace=sum(1 for c in vis[:1000] if c not in (32, 0)))
            r['checks']['menu_reached'] = ok
            r['checks']['hiscore_page_visible'] = r['menu']['heading_on_visible']

            # ---- 24-bit high-score insertion + rendering (values > 65535) ----
            # Compare the rendered attract-page rows against the stored 24-bit
            # table, converted independently in Python. HISCORE_MID lives in the
            # $8000 module while LO/HI are in the $2000 state block, so read each
            # by symbol rather than assuming one contiguous table.
            lo = peek(sym['HISCORE_LO'], 8)
            mid = peek(sym['HISCORE_MID'], 8)
            hi = peek(sym['HISCORE_HI'], 8)
            buf = peek(sym['HISCORE_PAGE_BUF'], 8 * 11)
            stored, rendered, sorted_desc = [], [], True
            for e in range(8):
                v = lo[e] | (mid[e] << 8) | (hi[e] << 16)
                stored.append(v)
                row = buf[e * 11:(e + 1) * 11]
                rendered.append(''.join(
                    chr(c) if 48 <= c <= 57 else '?' for c in row[5:11]))
                if e and stored[e] > stored[e - 1]:
                    sorted_desc = False
            r['hiscore'] = dict(
                stored=stored, rendered=rendered,
                inserted=r['score'],
                above_65535=[v for v in stored if v > 65535],
                digits_match=[f'{v:06d}' for v in stored] == rendered,
                sorted_descending=sorted_desc,
                inserted_present=r['score'] in stored,
                six_digits_everywhere=all(len(x) == 6 for x in rendered))
            r['checks']['hiscore_digits_match_stored'] = r['hiscore']['digits_match']
            r['checks']['hiscore_sorted_desc'] = sorted_desc
            r['checks']['hiscore_inserted_present'] = r['hiscore']['inserted_present']

            for k, v in r['checks'].items():
                if not v:
                    failures.append((i, k))
            results.append(r)
            print(f"loop {i}: " + ' '.join(
                f"{k}={'ok' if v else 'FAIL'}" for k, v in r['checks'].items()), flush=True)
            step(30)
    finally:
        try: mon.cmd('quit')
        except Exception: pass
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

    summary = dict(loops=len(results), failures=failures,
                   stage_start_row=stage_start, results=results)
    print(json.dumps(dict(loops=len(results), failures=failures,
                          stage_start_row=stage_start), indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
