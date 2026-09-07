#!/usr/bin/env python3
"""Host-side proof of the widened 16-bit metatile-definition lookup.

src/main.asm decodeStageCharacterRow used to compute the metatileDefs offset as
an 8-bit `id*16 + subrowOffset` (correct only for id 0..15). With up to 64
metatile definitions per level the offset is 0..1020, so the lookup now builds a
16-bit pointer:

    TEXT_SRC(16) = metatileDefs + (id << 4) + BG_TILE_ROW_OFS

This re-implements that pointer construction instruction-for-instruction, with
only 8-bit stores and explicit carry like the NMOS 6502, and checks it against a
plain Python reference for every id 0..63, every sub-row offset {0,4,8,12}, and a
spread of `metatileDefs` base addresses (including bases whose low byte forces
the add to carry). No emulator required; this isolates the arithmetic the way
tools/check_stage_addressing.py isolates the row math.
"""
import sys

MASK = 0xFF


def lo(v):
    return v & MASK


def hi(v):
    return (v >> 8) & MASK


def def_ptr_math(metatile_defs, tile_id, tile_row_ofs):
    """Return the 16-bit pointer exactly as the ASM builds it.

        lda BG_ROW_IDS,y        ; A = id
        sta BG_DEF_BASE
        lsr : lsr : lsr : lsr   ; A = id >> 4              (high byte of id*16)
        clc
        adc #>metatileDefs
        sta TEXT_SRC+1          ; provisional high byte
        lda BG_DEF_BASE
        asl : asl : asl : asl   ; A = (id << 4) & $FF      (low byte of id*16)
        clc
        adc BG_TILE_ROW_OFS     ; + sub-row offset (0..12; cannot carry)
        clc
        adc #<metatileDefs      ; + base low byte          (may carry)
        sta TEXT_SRC
        bcc +
        inc TEXT_SRC+1
    +
    """
    assert 0 <= tile_id <= 63
    assert tile_row_ofs in (0, 4, 8, 12)

    base_lo, base_hi = lo(metatile_defs), hi(metatile_defs)

    a = tile_id
    def_base = a                       # sta BG_DEF_BASE

    # A = id >> 4  (four LSRs). Carry after the LSRs is discarded by the CLC.
    a = a >> 4
    a = lo(a + base_hi)                # clc / adc #>metatileDefs  (0..3 + hi: no wrap here)
    text_src_hi = a                    # sta TEXT_SRC+1

    # A = (id << 4) & $FF  (four ASLs). Carry after the ASLs is discarded by CLC.
    a = lo(def_base << 4)
    a = a + tile_row_ofs               # clc / adc BG_TILE_ROW_OFS
    assert a <= MASK, "sub-row offset add must not carry (max $F0 + $0C)"
    total = a + base_lo                # clc / adc #<metatileDefs
    text_src_lo = lo(total)
    if total > MASK:                   # bcc + / inc TEXT_SRC+1
        text_src_hi = lo(text_src_hi + 1)

    return text_src_lo | (text_src_hi << 8)


def main():
    # decodeStageCharacterRow is entered with a full metatile-def table placed at
    # metatileDefs (currently $6600). Cover that, plus bases that stress the
    # low-byte carry and page-crossing paths.
    bases = [0x6600, 0x6608, 0x66F0, 0x66F8, 0x6700, 0x67FE, 0x6A00, 0x8000, 0x1234]
    failures = []
    checked = 0

    for base in bases:
        for tile_id in range(64):
            for ofs in (0, 4, 8, 12):
                got = def_ptr_math(base, tile_id, ofs)
                want = base + (tile_id << 4) + ofs
                checked += 1
                if got != want:
                    failures.append(
                        f"base=${base:04x} id={tile_id} ofs={ofs}: "
                        f"got ${got:04x} want ${want:04x}"
                    )

    # The four bytes actually copied per column are metatileDefs[off .. off+3]
    # via `lda (TEXT_SRC),y` for y = 0..3; prove the base pointer + y stays a
    # correct linear index for the id=63 / last sub-row corner.
    corner = def_ptr_math(0x6600, 63, 12)
    for y in range(4):
        got = corner + y
        want = 0x6600 + 63 * 16 + 12 + y
        checked += 1
        if got != want:
            failures.append(f"id=63 ofs=12 y={y}: got ${got:04x} want ${want:04x}")
    # id 63, sub-row 3 -> offset 1020..1023: the last bytes of a 64-entry
    # (1024-byte) table. One past the end would be 1024.
    assert 0x6600 + 63 * 16 + 12 + 3 == 0x6600 + 1023

    if failures:
        print(f"FAIL: {len(failures)} mismatch(es) of {checked} checks")
        for line in failures[:40]:
            print("  " + line)
        sys.exit(1)

    print("PASS: widened 16-bit metatileDefs lookup matches reference for")
    print(f"  - every id 0..63 x sub-row offset {{0,4,8,12}} x {len(bases)} base addresses")
    print("  - low-byte carry / page-cross bases ($66F8, $67FE, ...)")
    print("  - id 63 sub-row 3 reaches table offset 1020..1023 (64-entry / 1024-byte table)")
    print(f"  - {checked} arithmetic checks total")


if __name__ == "__main__":
    main()
