#!/usr/bin/env python3
"""Design source of truth for the six-digit HUD score font.

The glyphs are held here as ASCII art, NOT as the assembled byte table, so the
verifier in this file is an independent oracle: it re-derives the expected bytes
from the drawing and compares them against what KickAssembler actually emitted
into the PRG.

Geometry
--------
6 px wide inside an 8 px byte-aligned digit cell (2 px inter-digit gap), so each
digit owns exactly one whole bitmap byte per row and the compositor is a plain
STA per row per digit. Glyph pixels occupy bits 7..2; bits 1..0 are the gap.

HUD Phase 1.2 reduced the height from 21 rows to 16. Horizontal geometry is
UNCHANGED (6 px glyph, 8 px pitch, 46 px span, X 161 / 185).

Structural grid (16 rows): bar rows at 0 / 7 / 15, stems at columns 0 and 5.
Row 7 is the shared structural middle -- 3's waist, 4's crossbar, 5's and 6's
shoulder, 8's middle bar -- exactly as rows 0/10/20 were at 21 rows.
Single unmodulated 1 px stroke everywhere. 6 and 9 remain exact 180 rotations.

Usage:
    python3 tools/score_font_design.py --emit        # KickAssembler .byte rows
    python3 tools/score_font_design.py --verify build/shooter.prg
"""
import argparse
import sys

HEIGHT = 16
WIDTH = 6

GLYPHS = {
0: """
.####.
#....#
#....#
#....#
#....#
#....#
#....#
#....#
#....#
#....#
#....#
#....#
#....#
#....#
#....#
.####.
""",
1: """
...##.
..#.#.
.#..#.
....#.
....#.
....#.
....#.
....#.
....#.
....#.
....#.
....#.
....#.
....#.
....#.
.#####
""",
2: """
.####.
#....#
#....#
.....#
.....#
.....#
.....#
....#.
....#.
...#..
..#...
..#...
.#....
#.....
#.....
######
""",
3: """
.####.
#....#
#....#
.....#
.....#
.....#
....#.
..###.
....#.
.....#
.....#
.....#
.....#
#....#
#....#
.####.
""",
4: """
....#.
...##.
...##.
..#.#.
..#.#.
.#..#.
#...#.
######
....#.
....#.
....#.
....#.
....#.
....#.
....#.
....#.
""",
5: """
######
#.....
#.....
#.....
#.....
#.....
#.....
#####.
.....#
.....#
.....#
.....#
.....#
#....#
#....#
.####.
""",
6: """
..####
.#....
#.....
#.....
#.....
#.....
#.....
#####.
#....#
#....#
#....#
#....#
#....#
#....#
#....#
.####.
""",
7: """
######
.....#
.....#
....#.
....#.
...#..
...#..
..#...
..#...
..#...
.#....
.#....
.#....
#.....
#.....
#.....
""",
8: """
.####.
#....#
#....#
#....#
#....#
#....#
#....#
.####.
#....#
#....#
#....#
#....#
#....#
#....#
#....#
.####.
""",
9: """
.####.
#....#
#....#
#....#
#....#
#....#
#....#
#....#
.#####
.....#
.....#
.....#
.....#
.....#
....#.
####..
""",
}


def rows(digit):
    art = [r for r in GLYPHS[digit].strip('\n').split('\n')]
    if len(art) != HEIGHT:
        raise SystemExit(f'digit {digit}: {len(art)} rows, expected {HEIGHT}')
    out = []
    for r in art:
        if len(r) != WIDTH:
            raise SystemExit(f'digit {digit}: row {r!r} is not {WIDTH} wide')
        byte = 0
        for col, ch in enumerate(r):
            if ch == '#':
                byte |= 1 << (7 - col)          # col 0 -> bit 7 ... col 5 -> bit 2
            elif ch != '.':
                raise SystemExit(f'digit {digit}: bad char {ch!r}')
        out.append(byte)
    return out


def table():
    return [b for d in range(10) for b in rows(d)]


def checks():
    """Structural properties the design claims. Reported, not assumed."""
    result = {}
    # 6 and 9 are exact 180-degree rotations of one another.
    six, nine = rows(6), rows(9)
    def rot180(g):
        out = []
        for b in reversed(g):
            m = 0
            for col in range(WIDTH):
                if b & (1 << (7 - col)):
                    m |= 1 << (7 - (WIDTH - 1 - col))
            out.append(m)
        return out
    result['9 == rot180(6)'] = rot180(six) == nine
    # single 1 px stroke: no horizontal run longer than the deliberate bars
    # Deliberate multi-pixel features: the horizontal bars/chamfers, plus 0x18 --
    # the 2 px diagonal join in `1`'s flag and `4`'s stroke, which appears
    # identically in the 21 px design this font replaces.
    bars = {0x00, 0xfc, 0xf8, 0x7c, 0x78, 0x3c, 0x38, 0xf0, 0x18}
    stroke = True
    for d in range(10):
        for i, b in enumerate(rows(d)):
            if b in bars:
                continue
            runs, run = [], 0
            for col in range(WIDTH):
                if b & (1 << (7 - col)):
                    run += 1
                else:
                    if run:
                        runs.append(run)
                    run = 0
            if run:
                runs.append(run)
            if any(r > 1 for r in runs):
                stroke = False
                result.setdefault('thick_rows', []).append((d, i, f'{b:08b}'))
    result['single 1px stroke outside bars'] = stroke
    # low two bits are always the inter-digit gap
    result['gap bits clear'] = all(b & 0x03 == 0 for b in table())
    # every glyph uses the full height
    result['all glyphs use row 0 and row 15'] = all(
        rows(d)[0] and rows(d)[HEIGHT - 1] for d in range(10))
    return result


def emit():
    lines = []
    for d in range(10):
        g = rows(d)
        for chunk in range(0, HEIGHT, 8):
            part = g[chunk:chunk + 8]
            text = ', '.join(f'%{b:08b}' for b in part)
            tag = f'   // {d}' if chunk == 0 else ''
            lines.append(f'    .byte {text}{tag}')
    return '\n'.join(lines)


def verify(prg, load=0x0801, font_addr=None):
    data = open(prg, 'rb').read()
    origin = data[0] | (data[1] << 8)
    body = data[2:]
    if font_addr is None:
        raise SystemExit('--font-addr required')
    off = font_addr - origin
    got = list(body[off:off + 10 * HEIGHT])
    want = table()
    if got == want:
        print(f'scoreFont at ${font_addr:04x}: {len(want)} bytes MATCH the design')
        return 0
    print('MISMATCH')
    for i, (a, b) in enumerate(zip(want, got)):
        if a != b:
            print(f'  digit {i // HEIGHT} row {i % HEIGHT}: '
                  f'design %{a:08b} != prg %{b:08b}')
    return 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--emit', action='store_true')
    ap.add_argument('--verify')
    ap.add_argument('--font-addr', type=lambda s: int(s, 0))
    ap.add_argument('--checks', action='store_true')
    a = ap.parse_args()
    if a.emit:
        print(emit())
    if a.checks:
        for k, v in checks().items():
            print(f'{k}: {v}')
    if a.verify:
        sys.exit(verify(a.verify, font_addr=a.font_addr))
