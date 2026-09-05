// ============================================================================
// Raw test-stage data (deliberately wasteful: 40 literal bytes per row).
//
// This exists ONLY to prove that the working coarse/fine scroller can carry
// arbitrary screen content across a coarse transition, not just its own
// procedurally-generated diagnostic pattern. The scrolling engine in
// main.asm (applyFineScroll / updateBackgroundScroll / prepareBackgroundCoarse
// / finishBackgroundCoarse / BG_CROSSING_ROW) does not know or care that
// these bytes came from a table - it only ever asks for "the next 40 bytes
// to place at the top of the screen" and physically preserves whatever it
// is given. A future metatile/compressed stage format replaces this table
// without touching any of that scrolling machinery.
//
// Each row's first two bytes are a pre-baked two-digit hex row serial
// (0-TEST_STAGE_ROWS-1), using the same digit screen-codes the old
// diagnostic renderer used, purely so every row is visually and byte-wise
// unique and a skipped or duplicated row is obvious on screen or in a
// capture. Nothing at runtime derives these bytes from a row index - they
// are ordinary literal data, identical in kind to the rail/diagonal/marker
// bytes beside them. Column 2 and column 39 are a one-character gutter;
// columns 3-38 are a hand-designed "shape": narrow/wide corridors, an
// off-centre opening, a five-row diagonal drift (rows straddle several
// coarse transitions), asymmetric left/right walls and sparse markers.
//
// TEST_STAGE_ROWS itself is declared in main.asm (near SCROLL_FRAME_DIVIDER):
// code earlier in that file references it before this include is reached.
// ============================================================================

testStageData:
    // Layout per 40-byte row: [hex-hi][hex-lo][space][36-byte shape body][space].
    .byte 48,48,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32  // stage row  0: wide corridor
    .byte 48,49,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32  // stage row  1: narrow corridor (left)
    .byte 48,50,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,35,32,32,32,32,32,32  // stage row  2: single left wall, right marker
    .byte 48,51,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32  // stage row  3: narrow corridor (right)
    .byte 48,52,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row  4: bounded, solid middle wall
    .byte 48,53,32,224,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,224,32  // stage row  5: bounded, sparse markers
    .byte 48,54,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row  6: diagonal drift step 0/4
    .byte 48,55,32,224,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,224,32  // stage row  7: diagonal drift step 1/4
    .byte 48,56,32,224,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,224,32  // stage row  8: diagonal drift step 2/4
    .byte 48,57,32,224,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,224,32  // stage row  9: diagonal drift step 3/4
    .byte 48,1,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,224,32  // stage row 10: diagonal drift step 4/4
    .byte 48,2,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32  // stage row 11: near-full-width corridor
    .byte 48,3,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32  // stage row 12: narrow corridor (left)
    .byte 48,4,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 13: bounded, open middle (no wall)
    .byte 48,5,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,35,32,32,32,32,32,32  // stage row 14: single left wall, right marker
    .byte 48,6,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32  // stage row 15: wide corridor
    .byte 49,48,32,224,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,224,32  // stage row 16: bounded, sparse markers
    .byte 49,49,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32  // stage row 17: narrow corridor (right)
    .byte 49,50,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,224,32  // stage row 18: diagonal drift step 4/4 (reversing)
    .byte 49,51,32,224,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,224,32  // stage row 19: diagonal drift step 3/4
    .byte 49,52,32,224,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,224,32  // stage row 20: diagonal drift step 2/4
    .byte 49,53,32,224,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 21: diagonal drift step 1/4
    .byte 49,54,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 22: diagonal drift step 0/4
    .byte 49,55,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 23: bounded, solid middle wall
    .byte 49,56,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32  // stage row 24: near-full-width corridor
    .byte 49,57,32,224,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,224,32  // stage row 25: bounded, sparse markers
    .byte 49,1,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32  // stage row 26: narrow corridor (left)
    .byte 49,2,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 27: bounded, open middle (no wall)
    .byte 49,3,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,35,32,32,32,32,32,32  // stage row 28: single left wall, right marker
    .byte 49,4,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32  // stage row 29: wide corridor
    .byte 49,5,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32  // stage row 30: narrow corridor (right)
    .byte 49,6,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 31: diagonal drift step 0/4
    .byte 50,48,32,224,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 32: diagonal drift step 1/4
    .byte 50,49,32,224,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,224,32  // stage row 33: diagonal drift step 2/4
    .byte 50,50,32,224,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,224,32  // stage row 34: diagonal drift step 3/4
    .byte 50,51,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,224,32  // stage row 35: diagonal drift step 4/4
    .byte 50,52,32,224,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,224,32  // stage row 36: bounded, sparse markers
    .byte 50,53,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32  // stage row 37: near-full-width corridor
    .byte 50,54,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 38: bounded, solid middle wall
    .byte 50,55,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32  // stage row 39: narrow corridor (left)
    .byte 50,56,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,35,32,32,32,32,32,32  // stage row 40: single left wall, right marker
    .byte 50,57,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,224,32,32,32,32,32  // stage row 41: narrow corridor (right)
    .byte 50,1,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32  // stage row 42: wide corridor
    .byte 50,2,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 43: bounded, open middle (no wall)
    .byte 50,3,32,224,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,32,32,32,42,32,32,32,32,32,32,224,32  // stage row 44: bounded, sparse markers
    .byte 50,4,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32  // stage row 45: near-full-width corridor
    .byte 50,5,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,224,32  // stage row 46: diagonal drift step 4/4
    .byte 50,6,32,224,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,32,32,32,224,32,32,32,32,32,32,32,32,32,32,32,32,224,32  // stage row 47: diagonal drift step 0/4
TEST_STAGE_DATA_END:
// Size guard, row-address tables (stageRowLo/stageRowHi) and the final
// BASIC-ROM overlap guard live in main.asm, right after this file's
// #import - KickAssembler resolves .if/.for script directives against
// TEST_STAGE_ROWS more reliably there than inside an imported file. This
// file stays pure literal row data with no dependency on any external
// constant.
