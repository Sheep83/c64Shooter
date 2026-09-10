#!/usr/bin/env python3
"""Lifecycle page-ownership probe.

Drives GAME -> death -> GAME OVER -> HIGH SCORE (initials) -> MENU -> NEW GAME
in a fresh VICE, choosing the frame of the fatal hit so that the game ends on a
chosen BG_ACTIVE_PAGE. Records $D018 / BG_ACTIVE_PAGE / SCROLL_ROW and where the
non-gameplay text actually landed versus what the VIC was displaying.

All transient output goes to a scratch directory OUTSIDE the repo by default.
Joystick is neutral except for the explicit presses the lifecycle needs.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vice_scroll_test import Monitor, symbols

X64SC = '/opt/homebrew/bin/x64sc'
LIVES_LABEL = bytes([12, 9, 22, 5, 19, 32, 51])   # "LIVES 3" screen codes


class Probe:
    def __init__(self, port, prg, sym, scratch):
        # Direct Popen (never `open -a`): does not activate/focus the VICE app.
        self.proc = subprocess.Popen(
            [X64SC, '-default', '-pal', '-warp', '+sound', '-remotemonitor',
             '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
             '-autostartprgmode', '1', '-autostart', str(prg)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5)
        self.mon = Monitor(port)
        self.sym = sym
        self.scratch = scratch
        self.mon.cmd('delete')
        self.mon.cmd('resourceset "JoyPort2Device" "37"')

    def close(self):
        try:
            self.mon.cmd('quit')
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    # --- primitives -------------------------------------------------------
    def peek(self, addr, count=1):
        end = addr + count - 1
        text = self.mon.cmd(f'm {addr:04x} {end:04x}')
        out = []
        for line in text.splitlines():
            m = re.match(r'>C:([0-9a-fA-F]{4})\s+((?:[0-9a-fA-F]{2}[ ]+)+)', line)
            if m:
                out += [int(b, 16) for b in m.group(2).split()]
        return out[:count]

    def poke(self, addr, *values):
        self.mon.cmd(f'> {addr:04x} ' + ' '.join(f'{v:02x}' for v in values))

    def s(self, name, count=1):
        v = self.peek(self.sym[name], count)
        return v[0] if count == 1 else v

    def dump(self, addr, length):
        path = self.scratch / 'page.bin'
        self.mon.cmd(f'bsave "{path}" 0 {addr:04x} {addr + length:04x}')
        data = path.read_bytes()
        path.unlink(missing_ok=True)
        return data

    def joy(self, value):
        self.mon.cmd(f'jpdb 1 {value:02x}')

    def fire_tap(self):
        self.joy(0xef)
        self.step_frames(4)
        self.joy(0xff)
        self.step_frames(4)

    def arm_frame_break(self):
        """One stop per physical frame, valid in EVERY game state.

        A single `RL == $137` condition is NOT enough: the condition stays true
        for the whole raster line, so `x` re-breaks after one instruction. Ping-
        ponging the condition between two raster lines forces real forward
        progress of ~one frame per step() -- the same technique
        tools/vice_raster_lifecycle.py uses.
        """
        self.bp = int(re.search(r'BREAK: (\d+)',
                                self.mon.cmd('break exec 0000 ffff if RL == $137'))[1])

    def step(self, n=1):
        for _ in range(n):
            self.mon.cmd(f'condition {self.bp} if RL == $000')
            self.mon.cmd('x')
            self.mon.cmd(f'condition {self.bp} if RL == $137')
            self.mon.cmd('x')

    def step_frames(self, n=1):
        self.step(n)
    # ----------------------------------------------------------------------


def run(args):
    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path(args.symbols).resolve())
    p = Probe(args.port, Path(args.prg).resolve(), sym, scratch)
    log = {'kill_delay': args.kill_delay, 'events': [], 'failures': []}

    def note(tag, **kw):
        rec = dict(tag=tag,
                   game=p.s('GAME_STATE'),
                   player=p.s('PLAYER_STATE'),
                   lives=p.s('PLAYER_LIVES'),
                   d018=p.peek(0xd018)[0],
                   bg_active_page=p.s('BG_ACTIVE_PAGE'),
                   pageb_active=p.s('SS_PAGEB_ACTIVE'),
                   scroll_row=p.s('SCROLL_ROW') | (p.s('SCROLL_ROW_HI') << 8),
                   scroll_fine=p.s('SCROLL_FINE'))
        rec.update(kw)
        log['events'].append(rec)
        return rec

    try:
        # Free-running raster breakpoint = one stop per physical frame.
        p.arm_frame_break()

        # --- boot to the attract menu, then start a game --------------------
        for _ in range(400):
            p.step()
            if p.s('GAME_STATE') == 0:
                break
        note('attract_menu')
        p.fire_tap()
        for _ in range(400):
            p.step()
            if p.s('GAME_STATE') == 1:
                break
        note('game_started')

        # Qualify for the high-score table and put the player on its last life.
        p.poke(sym['SCORE_LO'], 0x40, 0xe2, 0x01)     # 123456
        p.poke(sym['PLAYER_LIVES'], 1)

        # --- run kill_delay frames, then kill the player --------------------
        # kill_delay is what makes the two outcomes reachable deterministically:
        # endGame runs several frames after the fatal hit (explosion animation),
        # so the page the game *ends* on is a function of the kill frame.
        p.step(args.kill_delay)
        note('before_fatal_hit')
        p.poke(sym['PLAYER_HIT'], 1)

        # --- GAME OVER (this is the first sample AFTER endGame) -------------
        for _ in range(600):
            if p.s('GAME_STATE') == 2:
                break
            p.step()
        note('game_over_entry')

        # --- initials / high-score entry ------------------------------------
        for _ in range(1200):
            if p.s('GAME_STATE') == 3:
                break
            p.step()
        g = p.s('GAME_STATE')
        if g == 3:
            p.step_frames(4)
            a = p.dump(0x0400, 0x400)
            b = p.dump(0x2800, 0x400)
            prompt = 10 * 40 + 10
            note('initials_screen',
                 rank=p.s('NEW_SCORE_RANK'),
                 prompt_row_pageA=list(a[prompt:prompt + 19]),
                 prompt_row_pageB=list(b[prompt:prompt + 19]),
                 nonspace_pageA=sum(1 for c in a[:1000] if c not in (32, 0)),
                 nonspace_pageB=sum(1 for c in b[:1000] if c not in (32, 0)))
            # commit the initials
            p.fire_tap()
        else:
            log['failures'].append(f'did not reach ENTER_INITIALS (state {g})')

        for _ in range(600):
            if p.s('GAME_STATE') == 0:
                break
            p.step()
        a = p.dump(0x0400, 0x400)
        b = p.dump(0x2800, 0x400)
        note('menu_after_initials',
             nonspace_pageA=sum(1 for c in a[:1000] if c not in (32, 0)),
             nonspace_pageB=sum(1 for c in b[:1000] if c not in (32, 0)))

        # --- new game -------------------------------------------------------
        p.step_frames(20)
        p.fire_tap()
        for _ in range(600):
            p.step()
            if p.s('GAME_STATE') == 1:
                break
        rec = note('new_game_first_frames')
        p.step_frames(8)
        rec = note('new_game_settled')
        visible = 0x0400 if (rec['d018'] & 0xf0) == 0x10 else 0x2800
        vis = p.dump(visible, 0x400)
        other = p.dump(0x2800 if visible == 0x0400 else 0x0400, 0x400)
        found_vis = [i for i in range(0, 1000 - 7)
                     if bytes(vis[i:i + 7]) == LIVES_LABEL]
        found_other = [i for i in range(0, 1000 - 7)
                       if bytes(other[i:i + 7]) == LIVES_LABEL]
        note('new_game_screen',
             visible_page=('A' if visible == 0x0400 else 'B'),
             lives_label_in_visible=[(o // 40, o % 40) for o in found_vis],
             lives_label_in_other=[(o // 40, o % 40) for o in found_other])

        # --- let it scroll a while and re-scan ------------------------------
        for _ in range(700):
            p.step()
        rec = note('new_game_after_scroll')
        visible = 0x0400 if (rec['d018'] & 0xf0) == 0x10 else 0x2800
        vis = p.dump(visible, 0x400)
        found_vis = [i for i in range(0, 1000 - 7)
                     if bytes(vis[i:i + 7]) == LIVES_LABEL]
        note('new_game_after_scroll_screen',
             visible_page=('A' if visible == 0x0400 else 'B'),
             lives_label_in_visible=[(o // 40, o % 40) for o in found_vis])
    finally:
        p.close()

    print(json.dumps(log, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(log, indent=2))
    return log


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kill-delay', type=int, default=60,
                    help='frames of normal play before the fatal hit')
    ap.add_argument('--port', type=int, default=6551)
    ap.add_argument('--prg', default='build/shooter.prg')
    ap.add_argument('--symbols', default='build/main.vs')
    ap.add_argument('--scratch', default=tempfile.gettempdir() + '/c64-lifecycle')
    ap.add_argument('--out', default=None)
    run(ap.parse_args())
