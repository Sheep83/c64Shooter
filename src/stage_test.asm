// ============================================================================
// 4x4 character metatile test stage (deliberately wasteful test art, not
// final game graphics - see docs/background-engine.md and the comment above
// decodeStageCharacterRow in main.asm for the addressing scheme).
//
// Two tables:
//
//   metatileDefs       - METATILE_DEF_COUNT definitions, METATILE_W*METATILE_H
//                         (16) literal character bytes each, row-major
//                         (definition's row 0 first, then row 1, 2, 3).
//   stageMetatileRows  - STAGE_METATILE_ROWS rows of METATILES_PER_ROW (10)
//                         metatile IDs each, one screen width per row.
//
// decodeStageCharacterRow (main.asm) expands these into a plain 40-byte
// character row on request; it does not care that the source is a metatile
// table rather than a raw row or, eventually, a compressed/loaded format.
// Runtime output depends on the actual stored IDs and definitions below -
// nothing is reconstructed from a row-number formula.
//
// Tile legend (ID: name - shape):
//   0  EMPTY        - all space.
//   1  SOLID        - solid rail block, all 16 cells.
//   2  WALL_L       - rail down the left column only.
//   3  WALL_R       - rail down the right column only.
//   4  NARROW_MID   - a 2x2 rail obstruction centred in the tile.
//   5  ASYM         - left-heavy top, right-heavy bottom (asymmetric).
//   6  GAP          - both side walls with a one-row gap (passage) at row 2.
//   7  STAIR        - a diagonal that moves one column per internal row -
//                     the shape changes across all four internal rows.
//   8  MARKER       - two sparse marker glyphs, otherwise empty.
//   9  DOUBLE_WALL  - both side walls, solid (no gap).
//   10 TOP_BAR      - a solid bar across internal row 0 only.
//   11 BOTTOM_BAR   - a solid bar across internal row 3 only.
// ============================================================================

metatileDefs:
    .byte 32,32,32,32,  32,32,32,32,  32,32,32,32,  32,32,32,32              // 0  EMPTY
    .byte 224,224,224,224,  224,224,224,224,  224,224,224,224,  224,224,224,224  // 1  SOLID
    .byte 224,32,32,32,  224,32,32,32,  224,32,32,32,  224,32,32,32          // 2  WALL_L
    .byte 32,32,32,224,  32,32,32,224,  32,32,32,224,  32,32,32,224          // 3  WALL_R
    .byte 32,32,32,32,  32,224,224,32,  32,224,224,32,  32,32,32,32          // 4  NARROW_MID
    .byte 224,32,32,32,  224,224,32,32,  32,32,224,224,  32,32,32,224        // 5  ASYM
    .byte 224,32,32,224,  224,32,32,224,  32,32,32,32,  224,32,32,224        // 6  GAP
    .byte 225,32,32,32,  32,225,32,32,  32,32,225,32,  32,32,32,225          // 7  STAIR
    .byte 32,32,32,32,  32,42,32,32,  32,32,35,32,  32,32,32,32              // 8  MARKER
    .byte 224,32,32,224,  224,32,32,224,  224,32,32,224,  224,32,32,224      // 9  DOUBLE_WALL
    .byte 224,224,224,224,  32,32,32,32,  32,32,32,32,  32,32,32,32          // 10 TOP_BAR
    .byte 32,32,32,32,  32,32,32,32,  32,32,32,32,  224,224,224,224          // 11 BOTTOM_BAR
METATILE_DEFS_END:

// Stage metatile rows: 10 IDs per row (one screen width), hand-placed - not
// a repeating or row-number-derived sequence. STAGE_METATILE_ROWS = 20 rows
// expand to 80 logical character rows, well past the 25 visible at once, so
// several ordinary coarse transitions occur before the stage wraps.
stageMetatileRows:
    .byte  2,0,0,7,0,0,0,0,3,0    // metatile row  0
    .byte  2,0,9,0,4,0,0,0,3,8    // metatile row  1
    .byte  0,6,0,0,0,10,0,5,0,2   // metatile row  2
    .byte  0,0,0,3,0,0,7,0,0,9    // metatile row  3
    .byte  1,0,2,0,0,0,3,0,4,0    // metatile row  4
    .byte  0,8,0,0,11,0,0,0,6,0   // metatile row  5
    .byte  2,0,0,5,0,3,0,0,0,7    // metatile row  6
    .byte  0,0,9,0,0,0,4,0,2,0    // metatile row  7
    .byte  0,3,0,0,10,0,0,6,0,0   // metatile row  8
    .byte  2,0,0,0,7,0,3,0,0,8    // metatile row  9
    .byte  0,0,5,0,0,0,0,9,0,2    // metatile row 10
    .byte  3,0,0,4,0,11,0,0,0,0   // metatile row 11
    .byte  0,2,0,0,0,0,6,0,3,0    // metatile row 12
    .byte  0,0,7,0,9,0,0,0,0,2    // metatile row 13
    .byte  3,0,0,8,0,0,5,0,0,0    // metatile row 14
    .byte  0,4,0,0,2,0,0,0,3,10   // metatile row 15
    .byte  0,0,0,6,0,7,0,0,0,0    // metatile row 16
    .byte  2,0,9,0,0,0,3,0,0,5    // metatile row 17
    .byte  0,0,0,0,8,0,0,4,0,2    // metatile row 18
    .byte  3,0,7,0,0,0,0,0,9,0    // metatile row 19
STAGE_METATILE_ROWS_END:
// Size guards, and the final BASIC-ROM overlap guard, live in main.asm right
// after this file's #import - KickAssembler resolves .if against the
// METATILE_*/STAGE_METATILE_ROWS constants more reliably there than inside
// an imported file (see the raw-row provider's equivalent historical note).
// This file stays pure literal data with no dependency on any external
// constant beyond what's needed to read it (nothing here computes a size).
