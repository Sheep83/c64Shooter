// ============================================================================
// Bas-relief terrain metatile stage (background art + hand-authored wrapping
// test level - see docs/background-engine.md and the comment above
// decodeStageCharacterRow in main.asm for the addressing scheme).
//
// Three tables (all future editor-generated):
//
//   metatileDefs       - METATILE_DEF_COUNT (16) definitions,
//                         METATILE_W*METATILE_H (16) literal character bytes
//                         each, row-major (definition's row 0 first, then row
//                         1, 2, 3). Cells are terrain char codes (160..223) or
//                         32 for open black.
//   metatileColours    - the parallel 16 colour-RAM values per metatile, same
//                         4x4 row-major layout. 0..7 hires colour; 8..15
//                         multicolour (see the block above metatileColours).
//   stageMetatileRows  - STAGE_METATILE_ROWS (25) rows of METATILES_PER_ROW
//                         (10) metatile IDs each, one screen width per row.
//                         25 metatile rows -> 100 logical character rows
//                         (~4.5 visible gameplay screen heights). The wrap
//                         is metatile row 24 -> row 0; both are all-M0 (open
//                         black) so logical row 99 -> 0 shows continuous black.
//
// decodeStageCharacterRow (main.asm) expands these into a plain 40-byte
// character row plus a parallel 40-byte colour row on request; it does not
// care that the source is a metatile table rather than a raw row or,
// eventually, a compressed/loaded format.
//
// Terrain glyph legend (bitmaps in main.asm terrainGlyphs, codes 160..199):
//   160 SOLID   161 STIPPLE 162 EDGE_T  163 EDGE_B  164 EDGE_L  165 EDGE_R
//   166 EDGE_T2 167 EDGE_B2 168 EDGE_L2 169 EDGE_R2 170..173 thin frame corners
//   174..177 thick frame corners       178..181 filled slope triangles
//   182 DIAG_F  183 DIAG_B  184 DIAG_F2 185 DIAG_B2 186 STEP_F 187 STEP_B
//   188 APEX_T  189 APEX_B  190 APEX_L  191 APEX_R  192 RIB_H  193 RIB_V
//   194 SLOT_V  195 SLOT_H  196..199 inner-corner notches
//
// Metatile legend (ID: name - shape):
//   0  OPEN       - all black (also the seamless wrap row).
//   1  FLOOR_H    - raised horizontal band, chains left-right across seams.
//   2  CHANNEL_V  - open trench with 2px walls, chains up-down across seams.
//   3  SLAB       - 32x32 thick-bordered solid slab.
//   4  SLAB_OPEN  - bordered frame, black interior (negative space).
//   5  SLAB_L     - left half of a wide slab (open right edge -> M6).
//   6  SLAB_R     - right half of a wide slab.
//   7  DIAMOND    - solid 32x32 diamond built from four filled slope triangles.
//   8  STEP_PYR   - staircase apex (STEP_F/STEP_B) over a solid base.
//   9  SLOPE_F    - filled '/' ramp, chains diagonally up-right across seams.
//   10 SLOPE_B    - filled '\' ramp, chains diagonally up-left across seams.
//   11 CORNER     - asymmetric L, thin inner-corner glyphs at the steps.
//   12 JUNCTION   - ribbed cross intersection, chains all four ways.
//   13 DETAIL     - dense technological block (slots + inner notches + stipple).
//   14 CONNECT_H  - two thin rules spanning full width (transitional).
//   15 CONNECT_V  - two thin rules spanning full height (transitional).
// ============================================================================

metatileDefs:
    .byte  32, 32, 32, 32,   32, 32, 32, 32,   32, 32, 32, 32,   32, 32, 32, 32   //  0 OPEN
    .byte  32, 32, 32, 32,  192,192,192,192,  192,192,192,192,   32, 32, 32, 32   //  1 FLOOR_H
    .byte 169, 32, 32,168,  169, 32, 32,168,  169, 32, 32,168,  169, 32, 32,168   //  2 CHANNEL_V
    .byte 174,166,166,175,  168,160,160,169,  168,160,160,169,  176,167,167,177   //  3 SLAB
    .byte 174,166,166,175,  168, 32, 32,169,  168, 32, 32,169,  176,167,167,177   //  4 SLAB_OPEN
    .byte 174,166,166,166,  168,160,160,160,  168,160,160,160,  176,167,167,167   //  5 SLAB_L
    .byte 166,166,166,175,  160,160,160,169,  160,160,160,169,  167,167,167,177   //  6 SLAB_R
    .byte  32,181,180, 32,  181,160,160,180,  179,160,160,178,   32,179,178, 32   //  7 DIAMOND
    .byte  32,186,187, 32,  186,160,160,187,  160,160,160,160,  160,160,160,160   //  8 STEP_PYR
    .byte  32, 32, 32,180,   32, 32,180,160,   32,180,160,160,  180,160,160,160   //  9 SLOPE_F
    .byte 181, 32, 32, 32,  160,181, 32, 32,  160,160,181, 32,  160,160,160,181   // 10 SLOPE_B
    .byte 174,166,166,166,  168,160,160,173,  168,160,173, 32,  176,167, 32, 32   // 11 CORNER
    .byte  32,193,193, 32,  192,160,160,192,  192,160,160,192,   32,193,193, 32   // 12 JUNCTION
    .byte 174,195,197,175,  168,194,194,169,  168,198,161,169,  176,161,167,177   // 13 DETAIL
    .byte  32, 32, 32, 32,  166,166,166,166,   32, 32, 32, 32,  163,163,163,163   // 14 CONNECT_H
    .byte  32,165, 32,164,   32,165, 32,164,   32,165, 32,164,   32,165, 32,164   // 15 CONNECT_V
METATILE_DEFS_END:

// Per-cell colour-RAM values, one 16-byte block per metatile, identical 4x4
// row-major layout to metatileDefs. decodeStageCharacterRow reads this with the
// same offset it uses for metatileDefs. Global multicolour text mode is on:
//   value 0..7  -> hires cell, value = foreground colour   (bg = $D021 black)
//   value 8..15 -> multicolour cell: bitpair 01->$D022, 10->$D023, 11->(value&7)
// Regression stage keeps the mono relief readable (mostly white = 1) with a few
// hires accents; metatile 13 (DETAIL) is the deliberate multicolour proof.
// Metatiles 0 / 5 / 12 carry the three prototype turret bodies and are kept
// fully hires (0..7) so the private turret glyphs render as hires.
metatileColours:
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   //  0 OPEN      (hires white; turret 0)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   //  1 FLOOR_H   (hires white)
    .byte  3, 3, 3, 3,   3, 3, 3, 3,   3, 3, 3, 3,   3, 3, 3, 3   //  2 CHANNEL_V (hires cyan)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   //  3 SLAB      (hires white)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   //  4 SLAB_OPEN (hires white)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   //  5 SLAB_L    (hires white; turret 1)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   //  6 SLAB_R    (hires white)
    .byte  7, 7, 7, 7,   7, 7, 7, 7,   7, 7, 7, 7,   7, 7, 7, 7   //  7 DIAMOND   (hires yellow)
    .byte  7, 7, 7, 7,   7, 7, 7, 7,   7, 7, 7, 7,   7, 7, 7, 7   //  8 STEP_PYR  (hires yellow)
    .byte  3, 3, 3, 3,   3, 3, 3, 3,   3, 3, 3, 3,   3, 3, 3, 3   //  9 SLOPE_F   (hires cyan)
    .byte  3, 3, 3, 3,   3, 3, 3, 3,   3, 3, 3, 3,   3, 3, 3, 3   // 10 SLOPE_B   (hires cyan)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   // 11 CORNER    (hires white)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   // 12 JUNCTION  (hires white; turret 2)
    .byte 15,13,11, 9,  13,11, 9,15,  11, 9,15,13,   9,15,13,11   // 13 DETAIL    (MULTICOLOUR proof; all >= 8)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   // 14 CONNECT_H (hires white)
    .byte  1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1,   1, 1, 1, 1   // 15 CONNECT_V (hires white)
METATILE_COLOURS_END:

// Stage metatile rows: 10 IDs per row (one screen width), hand-placed in five
// vertical sections. Metatile row 0 and row 24 are both all-M0 (open black),
// so the logical row 99 -> 0 wrap is a continuous black seam.
stageMetatileRows:
    // --- SECTION 1: INTRO / OPEN RELIEF ---
    .byte  0, 0, 0, 0, 0, 0, 0, 0, 0, 0   // metatile row  0  (logical rows 0-3)
    .byte  0, 0, 3, 0, 0, 0, 0, 5, 6, 0   // metatile row  1  (logical rows 4-7)
    .byte  0, 0, 0, 0, 0, 1, 1, 0, 0, 0   // metatile row  2  (logical rows 8-11)
    .byte  3, 0, 0, 0, 0, 0, 0, 0, 0, 3   // metatile row  3  (logical rows 12-15)
    .byte  0, 0,14,14,14,14,14,14, 0, 0   // metatile row  4  (logical rows 16-19)
    // --- SECTION 2: SQUARE ARCHITECTURE ---
    .byte  5, 6, 0, 0, 4, 0, 0, 5, 6, 0   // metatile row  5  (logical rows 20-23)
    .byte  0, 0, 0, 5, 6, 5, 6, 0, 0, 3   // metatile row  6  (logical rows 24-27)
    .byte  4, 0, 5, 6, 0, 0, 5, 6, 0, 4   // metatile row  7  (logical rows 28-31)
    .byte  0, 5, 6, 5, 6, 0, 0, 5, 6, 0   // metatile row  8  (logical rows 32-35)
    .byte 14,14,14,14,14,14,14,14,14,14   // metatile row  9  (logical rows 36-39)
    // --- SECTION 3: PYRAMID FIELD ---
    .byte  0, 7, 0, 0,10, 9, 0, 0, 7, 0   // metatile row 10  (logical rows 40-43)
    .byte  7, 0,10, 9, 0, 0,10, 9, 0, 7   // metatile row 11  (logical rows 44-47)
    .byte 10, 9, 0, 7, 0, 0, 7, 0,10, 9   // metatile row 12  (logical rows 48-51)
    .byte  0,10, 9,10, 9,10, 9,10, 9, 0   // metatile row 13  (logical rows 52-55)
    .byte  7, 0, 7, 0, 7, 0, 7, 0, 7, 0   // metatile row 14  (logical rows 56-59)
    // --- SECTION 4: CHANNEL / INDUSTRIAL ---
    .byte  2, 0, 2, 0, 2, 0, 2, 0, 2, 0   // metatile row 15  (logical rows 60-63)
    .byte  2,12, 2,13, 2, 0, 2,12, 2,13   // metatile row 16  (logical rows 64-67)
    .byte  2, 0, 2, 0,12, 0, 2, 0, 2, 0   // metatile row 17  (logical rows 68-71)
    .byte 15, 2,13, 2, 0, 1, 1, 2,13, 2   // metatile row 18  (logical rows 72-75)
    .byte  2,12, 2, 0, 2,12, 2, 0, 2,12   // metatile row 19  (logical rows 76-79)
    // --- SECTION 5: COMPLEX / COMBINED -> fade to open ---
    .byte  5, 6,13, 0, 7, 0,11,12, 5, 6   // metatile row 20  (logical rows 80-83)
    .byte 13, 0,10, 9, 4, 5, 6,13, 0, 9   // metatile row 21  (logical rows 84-87)
    .byte  0,11, 0, 1, 1,12, 0,11, 7, 0   // metatile row 22  (logical rows 88-91)
    .byte  3, 0,14,14,14,14,14,14, 0, 3   // metatile row 23  (logical rows 92-95)
    .byte  0, 0, 0, 0, 0, 0, 0, 0, 0, 0   // metatile row 24  (logical rows 96-99)
STAGE_METATILE_ROWS_END:
// Size guards, and the final BASIC-ROM overlap guard, live in main.asm right
// after this file's #import - KickAssembler resolves .if against the
// METATILE_*/STAGE_METATILE_ROWS constants more reliably there than inside
// an imported file (see the raw-row provider's equivalent historical note).
// This file stays pure literal data with no dependency on any external
// constant beyond what's needed to read it (nothing here computes a size).
