#!/usr/bin/env python3
"""Host-side proof of the widened 16-bit stage-addressing arithmetic.

This re-implements, instruction for instruction, the byte-level 6502 math that
src/main.asm decodeStageCharacterRow / wrapBgLogicalRow / renderStageRowToScreen
and src/background_turrets.asm positionBackgroundTurrets now perform, using only
8-bit stores and explicit car/borrow like the CPU. It then checks the result
against an independent Python reference (divmod / //) for every logical row of a
1,600-row (400 metatile-row) stage, plus the specific boundary values the task
requires proven. No emulator required; this isolates the arithmetic.
"""
import sys

MASK = 0xFF


def lo(v): return v & MASK
def hi(v): return (v >> 8) & MASK


# --- decodeStageCharacterRow: logical row -> metatile row, subrow, row base ----
def decode_row_math(bg_logical_row):
    """Returns (metatile_row_16, subrow, row_base_16) exactly as the ASM computes."""
    row_lo, row_hi = lo(bg_logical_row), hi(bg_logical_row)

    # lda BG_LOGICAL_ROW / and #METATILE_H-1 / asl / asl
    subrow = ((row_lo & 3) << 2) & MASK

    # metatileRow = logicalRow >> 2  (16-bit)
    #   lda BG_LOGICAL_ROW_HI / lsr            -> A, C
    a = row_hi
    c = a & 1
    a >>= 1
    mrow_hi = a                       # sta BG_METATILE_ROW_HI
    #   lda BG_LOGICAL_ROW / ror              -> A uses C from above
    a = row_lo
    new_c = a & 1
    a = ((a >> 1) | (c << 7)) & MASK
    c = new_c
    #   lsr BG_METATILE_ROW_HI
    c2 = mrow_hi & 1
    mrow_hi >>= 1
    #   ror  (A)
    a = ((a >> 1) | (c2 << 7)) & MASK
    mrow_lo = a                      # sta BG_METATILE_ROW
    metatile_row = mrow_lo | (mrow_hi << 8)

    # rowBase = metatileRow*2 + metatileRow*8   (16-bit)
    #   lda BG_METATILE_ROW / asl / sta BG_ROW_BASE
    a = mrow_lo
    c = (a >> 7) & 1
    a = (a << 1) & MASK
    rb_lo = a
    #   lda BG_METATILE_ROW_HI / rol / sta BG_ROW_BASE_HI
    a = mrow_hi
    a = ((a << 1) | c) & MASK
    rb_hi = a                         # rowBase = metatileRow*2
    #   lda BG_ROW_BASE / asl / sta TEXT_SRC
    a = rb_lo
    c = (a >> 7) & 1
    a = (a << 1) & MASK
    t_lo = a
    #   lda BG_ROW_BASE_HI / rol / sta TEXT_SRC+1
    a = rb_hi
    a = ((a << 1) | c) & MASK
    t_hi = a                          # TEXT_SRC = metatileRow*4
    #   asl TEXT_SRC / rol TEXT_SRC+1
    c = (t_lo >> 7) & 1
    t_lo = (t_lo << 1) & MASK
    t_hi = ((t_hi << 1) | c) & MASK   # TEXT_SRC = metatileRow*8
    #   lda BG_ROW_BASE / clc / adc TEXT_SRC / sta BG_ROW_BASE
    s = rb_lo + t_lo
    rb_lo = s & MASK
    c = 1 if s > MASK else 0
    #   lda BG_ROW_BASE_HI / adc TEXT_SRC+1 / sta BG_ROW_BASE_HI
    s = rb_hi + t_hi + c
    rb_hi = s & MASK
    row_base = rb_lo | (rb_hi << 8)

    return metatile_row, subrow, row_base


# --- wrapBgLogicalRow: reduce BG_LOGICAL_ROW(16) mod STAGE_LOGICAL_ROWS --------
def wrap_bg_logical_row(value, stage_logical_rows):
    v_lo, v_hi = lo(value), hi(value)
    slr_lo, slr_hi = lo(stage_logical_rows), hi(stage_logical_rows)
    # lda HI / cmp #>SLR
    if v_hi < slr_hi:
        return v_lo | (v_hi << 8)
    if v_hi == slr_hi:
        if v_lo < slr_lo:
            return v_lo | (v_hi << 8)
    # subtract SLR (16-bit)
    s = v_lo - slr_lo
    r_lo = s & MASK
    borrow = 0 if s >= 0 else 1
    s = v_hi - slr_hi - borrow
    r_hi = s & MASK
    return r_lo | (r_hi << 8)


# --- renderStageRowToScreen: incoming logical row from SCROLL_ROW + dest -------
def render_incoming_row(scroll_row, bg_dest_row, stage_logical_rows):
    sr_lo, sr_hi = lo(scroll_row), hi(scroll_row)
    # lda SCROLL_ROW / clc / adc BG_DEST_ROW / sta BG_LOGICAL_ROW
    s = sr_lo + bg_dest_row
    l_lo = s & MASK
    c = 1 if s > MASK else 0
    # lda SCROLL_ROW_HI / adc #0
    s = sr_hi + c
    l_hi = s & MASK
    # lda BG_LOGICAL_ROW / sec / sbc #1
    s = l_lo - 1
    l_lo = s & MASK
    borrow = 0 if s >= 0 else 1
    s = l_hi - borrow
    l_hi = s & MASK
    return wrap_bg_logical_row(l_lo | (l_hi << 8), stage_logical_rows)


# --- prepareBackgroundCoarse: 16-bit world-row step-back with wrap ------------
def coarse_step_back(scroll_row, stage_logical_rows):
    sr_lo, sr_hi = lo(scroll_row), hi(scroll_row)
    if (sr_lo | sr_hi) == 0:
        sr_lo, sr_hi = lo(stage_logical_rows), hi(stage_logical_rows)
    s = sr_lo - 1
    r_lo = s & MASK
    borrow = 0 if s >= 0 else 1
    s = sr_hi - borrow
    r_hi = s & MASK
    return r_lo | (r_hi << 8)


# --- positionBackgroundTurrets: relative row (16-bit) ------------------------
def turret_relative_row(turret_world_row, scroll_row, stage_logical_rows):
    tw_lo, tw_hi = lo(turret_world_row), hi(turret_world_row)
    sr_lo, sr_hi = lo(scroll_row), hi(scroll_row)
    s = tw_lo - sr_lo
    rel_lo = s & MASK
    borrow = 0 if s >= 0 else 1
    s = tw_hi - sr_hi - borrow
    rel_hi = s & MASK
    carry_set = s >= 0
    if not carry_set:
        s = rel_lo + lo(stage_logical_rows)
        rel_lo = s & MASK
        c = 1 if s > MASK else 0
        s = rel_hi + hi(stage_logical_rows) + c
        rel_hi = s & MASK
    return rel_lo | (rel_hi << 8)


def main():
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append(f"{label}: got {got}, want {want}")

    STAGE_METATILE_ROWS = 400
    SLR = STAGE_METATILE_ROWS * 4          # 1600
    MPR = 10

    # 1. Full sweep: every logical row of the 400-row stage.
    for row in range(SLR):
        mrow, subrow, row_base = decode_row_math(row)
        check(f"metatileRow(row={row})", mrow, row >> 2)
        check(f"subrow(row={row})", subrow, (row & 3) * 4)
        check(f"rowBase(row={row})", row_base, (row >> 2) * MPR)

    # 2. Arithmetic head-room well past the required range (6000 metatile rows).
    for mrow in list(range(0, 6001)) + [6500, 6553]:
        row = mrow * 4 + 3
        m2, sub, rb = decode_row_math(row)
        check(f"headroom metatileRow(mrow={mrow})", m2, mrow)
        check(f"headroom rowBase(mrow={mrow})", rb, mrow * MPR)

    # 3. Task-required explicit metatile-row base offsets.
    for mrow, want in [(0, 0), (1, 10), (25, 250), (255, 2550),
                       (256, 2560), (399, 3990)]:
        _, _, rb = decode_row_math(mrow * 4)
        check(f"row {mrow} base", rb, want)
    # row 399, column 9 -> map offset 3999
    _, _, rb = decode_row_math(399 * 4)
    check("row 399 col 9 offset", rb + 9, 3999)

    # 4. Task-required map offsets around the 8-bit page boundary and beyond.
    for mrow in (0, 1, 25, 255, 256, 399):
        _, _, rb = decode_row_math(mrow * 4)
        for col in range(MPR):
            check(f"offset r{mrow}c{col}", rb + col, mrow * MPR + col)
    explicit = {0: (0, 0), 10: (1, 0), 250: (25, 0), 255: (25, 5),
                256: (25, 6), 257: (25, 7), 2550: (255, 0), 2560: (256, 0),
                3990: (399, 0), 3999: (399, 9)}
    for off, (mrow, col) in explicit.items():
        _, _, rb = decode_row_math(mrow * 4)
        check(f"explicit offset {off}", rb + col, off)

    # 5. logical row / metatile row boundary crossings.
    for row, mrow, sub in [(1023, 255, 3), (1024, 256, 0),
                           (1020, 255, 0), (1027, 256, 3),
                           (1599, 399, 3), (1596, 399, 0), (0, 0, 0)]:
        m, s, _ = decode_row_math(row)
        check(f"logical {row} -> metatile row", m, mrow)
        check(f"logical {row} -> subrow", s, sub // 1 * 4 if False else sub * 4)

    # 6. Full-stage wrap: SCROLL_ROW steps 1599 -> 1598 -> ... -> 0 -> 1599.
    sr = 0
    seen = []
    for _ in range(SLR + 5):
        sr = coarse_step_back(sr, SLR)
        seen.append(sr)
    # from sr=0 the first step must yield 1599
    check("coarse wrap 0 -> SLR-1", seen[0], SLR - 1)
    # strictly decreasing by 1 with a single wrap back to SLR-1
    for i in range(1, len(seen)):
        prev, cur = seen[i - 1], seen[i]
        expect = SLR - 1 if prev == 0 else prev - 1
        check(f"coarse step {i}", cur, expect)

    # 7. renderStageRowToScreen incoming row across the seam, all dest rows.
    for scroll in list(range(0, 40)) + [SLR - 25, SLR - 5, SLR - 1]:
        for dest in range(1, 24):
            got = render_incoming_row(scroll, dest, SLR)
            want = (scroll + dest - 1) % SLR
            check(f"incoming(scroll={scroll},dest={dest})", got, want)

    # 8. Decode of the wrapped incoming row 1599 must be metatile row 399 sub 3.
    inc = render_incoming_row(SLR - 1, 1, SLR)      # top matrix row shows SCROLL_ROW-...
    # (scroll=SLR-1, dest=1) -> incoming (SLR-1) ; then next world row after wrap:
    check("incoming(SLR-1, dest1)", inc, SLR - 1)
    m, s, rb = decode_row_math(SLR - 1)
    check("decode(1599) metatile row", m, 399)
    check("decode(1599) subrow", s, 12)
    check("decode(1599) rowBase", rb, 3990)
    # world row after 1599 in the engine's descending progression is 1598 (the
    # coarse step decrements); the end->start wrap is 0 -> 1599 (proven in 6).

    # 9. Turret relative-row math above 255 logical rows.
    for tw, sr in [(255, 0), (256, 0), (1023, 0), (1024, 0), (1599, 0),
                   (256, 250), (1599, 1590), (5, 10), (0, 1599)]:
        got = turret_relative_row(tw, sr, SLR)
        want = (tw - sr) % SLR
        check(f"turret rel(tw={tw},sr={sr})", got, want)

    # 10. 25-row compatibility: identical results to a plain reference.
    SLR25 = 100
    for row in range(SLR25):
        m, s, rb = decode_row_math(row)
        check(f"25-row metatileRow({row})", m, row >> 2)
        check(f"25-row rowBase({row})", rb, (row >> 2) * 10)
    sr = 0
    for _ in range(SLR25 * 2 + 3):
        sr = coarse_step_back(sr, SLR25)
        assert sr < SLR25
    for scroll in range(SLR25):
        for dest in range(1, 24):
            got = render_incoming_row(scroll, dest, SLR25)
            check(f"25-row incoming({scroll},{dest})", got,
                  (scroll + dest - 1) % SLR25)

    if failures:
        print(f"FAIL ({len(failures)} problems)")
        for f in failures[:40]:
            print("  " + f)
        sys.exit(1)
    print("PASS: widened stage arithmetic matches reference for")
    print(f"  - every logical row 0..{SLR-1} of a 400-metatile-row stage")
    print("  - metatile-row headroom to 6553 rows")
    print("  - row bases 0/10/250/2550/2560/3990, offset 3999")
    print("  - offsets 0 10 250 255 256 257 2550 2560 3990 3999")
    print("  - logical 1023->255/3, 1024->256/0, 1599->399/3")
    print(f"  - full {SLR}-row coarse wrap (0 -> {SLR-1}) and back")
    print("  - incoming-row seam for all matrix rows 1..23")
    print("  - turret relative rows above 255")
    print("  - 25-row stage unchanged vs reference")


if __name__ == '__main__':
    main()
