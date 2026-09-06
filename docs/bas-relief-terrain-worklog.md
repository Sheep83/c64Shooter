# Bas-relief terrain tileset + wrapping test level — worklog

## Task
Replace the diagnostic scrolling background with a monochrome hires bas-relief
terrain tileset + a hand-authored wrapping test level ~5 gameplay screens tall.
ART / LEVEL-DATA only. Do NOT touch scroller / metatile decoder / raster
scheduler / HUD / multiplexer / BUILD-LIVE.

## Engine constraints found (traced in decodeStageCharacterRow, main.asm ~4871)

The metatile decoder uses **8-bit absolute,X/Y indexing** with no high byte:

- `stageMetatileRows` index = `metatileRow*METATILES_PER_ROW(10) + col`.
  `metatileRow*10` is built with `asl`/`adc` on ONE byte, then `+col`. Must stay
  <= 255 -> **STAGE_METATILE_ROWS <= 25** (25*10 = 250, last index 24*10+9 = 249).
  Existing guard: `STAGE_METATILE_ROWS * METATILES_PER_ROW > 256 -> error`.
- `metatileDefs` index = `id*16 + internalRowOfs`. `id*16` is 4x `asl` on one
  byte; id >= 16 shifts bits out -> **METATILE_DEF_COUNT <= 16**.
  Existing guard: `METATILE_DEF_COUNT > 16 -> error`.

Task target was ~27-30 metatile rows and (implicitly) >16 metatiles. Both are
blocked by these 8-bit assumptions. Per the task's explicit instruction
("stop and report rather than silently redesigning it") the decoder is NOT
being changed. Implementing the **maximum the decoder supports**:

- 25 metatile rows = 100 logical character rows.
- 16 metatile definitions.
- ~40 terrain character primitives.

100 char rows / 22 visible terrain rows ~= **4.5 gameplay screen heights**
(not 5). Reported as a constraint, not a redesign.

## Charset namespace (from the audit)
- `TERRAIN_GLYPH_BASE = 160`, `TERRAIN_GLYPH_COUNT = 40` -> codes 160..199,
  bitmaps $3800 + 160*8 = **$3D00 .. $3E3F**. 200..223 left free for future
  terrain art. 146..159 untouched (HUD reserve). 224/225 untouched (diagnostic).
  240..251 untouched (starfield).

## Memory
- `terrainGlyphs` (320 B) placed next to `bgDiagnosticGlyphs` in the $2920
  control segment (headroom to $3000 was ~1.3 KB).
- `metatileDefs` 16*16 = 256 B, `stageMetatileRows` 25*10 = 250 B in
  `stage_test.asm` ($4000 segment, headroom to $6000 was ~2 KB).
- Init: one extra copy loop in `initBackground` after the 224/225 copy.

## Design
- 40 primitives 160..199: fills, thin+thick edges (T/B/L/R), thin+thick frame
  corners, filled triangles (slopes), 1px+2px diagonals, staircase steps,
  diamond apex/side pieces, horizontal/vertical ribs, black slots, inner-corner
  notches.
- 16 metatiles M0..M15: open, horizontal feature, vertical channel, slab,
  open-frame slab, wide-slab L/R halves, diamond, stepped pyramid, filled
  slope `/` and `\` halves, asymmetric corner, junction, detail block,
  horizontal + vertical transitional connectors. Long edges (166/163/192) and
  diagonals (182..185) chain across the 32px metatile seams by construction.
- Level 25 metatile rows x 10, 5 sections of 5 rows:
  S1 intro/open, S2 square architecture, S3 pyramid field, S4 channel/industrial,
  S5 complex/combined then fade to open. Metatile row 0 and row 24 are both
  all-open (M0) so the logical row 99 -> 0 wrap shows continuous black.

## Implementation (done)
- `src/main.asm`:
  - `METATILE_DEF_COUNT` 12 -> 16, `STAGE_METATILE_ROWS` 20 -> 25 (+ comments).
  - `TERRAIN_GLYPH_BASE = 160`, `TERRAIN_GLYPH_COUNT = 40` + 7 assembler guards
    (>=160, clears 146..159, <=223, no 224/225 collision, bitmaps begin $3D00,
    bitmaps stay < $4000, count == 40).
  - `initBackground`: unrolled x5 copy loop (one 0..63 X pass = 320 bytes)
    moving `terrainGlyphs` into the RAM charset at $3D00, right after the
    existing 224/225 diagnostic-glyph copy.
  - `terrainGlyphs:` 320-byte `.byte` block next to `bgDiagnosticGlyphs`, plus
    a `terrainGlyphsEnd - terrainGlyphs == TERRAIN_GLYPH_COUNT*8` guard.
- `src/stage_test.asm`: replaced `metatileDefs` (12 -> 16 defs) and
  `stageMetatileRows` (20 -> 25 rows) with the bas-relief tileset + 5-section
  wrapping level; rewrote the header legend. Existing size guards in main.asm
  (256 B defs, 250 B rows) pass unchanged.

## Build
KickAssembler v5.25 (openjdk 1.8.0_472), clean, all guards pass.
Final PRG SHA-256 `b36264f1983ad1b1e55e7fe444f7111b0bbcdca934651bf9f7c64fa83ab07e94`.
PRG image size unchanged at 23377 B (growth lands in existing inter-segment
gaps below the $6000 raster scheduler).

Two later data-only revisions after first render review: M7-M13 rebuilt on the
filled slope triangles / staircase / inner-notch primitives so the pyramid
field reads as solid relief (was hollow chevrons); then a 1-byte M7 triangle
swap to make the diamond point top+bottom instead of pinching to a bowtie.
Charset init and all constants unchanged across both; only stage_test.asm data.

Resident growth:
- $2920 control segment: $2ad7 -> $2c3c  (+357 B: 320 B glyph data + 37 B loop).
  Guard end <= $3000: 964 B headroom left.
- $4000 segment: $57cf -> $5841  (+114 B: stage data only, no code).
  Guard end <= $6000: 1983 B headroom left.
- $6000-$634f raster scheduler: untouched.

## Validation (final build, capture build/scroll-test/terrain-v2)
- `check_fixed_hud_capture.py`, 5200-frame non-stress run (physical, trace):
  **0 failures**. 216 coarse transitions = 2.16 full level circuits. PAL cadence
  exactly [19656]. phases 0..7. HUD/SCORE/FREE structurally valid every frame,
  matrix + incoming + crossing buffers exact, physical-pixel + both-edge motion
  oracles clean across the wrap. ~305M pixel checks, ~26.6M unmasked HUD/
  separator checks, ~7.5M physical-edge-motion checks.
- `check_raster_capture.py` same run: 0 service failures, 0 sprite-start misses,
  cadence [19656].
- `vice_raster_lifecycle.py`: `failures: []` (death/respawn/game-over/menu/
  restart + scheduler restart), gameplay jiffy drift 0.
- `vice_raster_cases.py` (17 scheduler cases incl. parked-LIVE + coarse DMA):
  all `coarse_*` cases 0/0; injected sprite-overload cases show the same
  nondeterministic saturation service-failure counts as a HEAD rebuild
  (compared side by side), never worse in aggregate; 0 sprite-start misses.
- `--stress` runs (1400 frames) show only the pre-existing raster 71-73
  straddler-DMA transient; a HEAD isolated rebuild reproduces the identical
  signature (HEAD 70 / terrain 110 pixel flickers, HEAD 11 / terrain 6 mask
  misses - load-nondeterministic, same region, not introduced here).
- Minimum FREE reading across the representative non-stress runs: **1386** free
  cycles (steady state; first 49 frames read 00000 before the first rolling-
  minimum refresh; other runs bottomed at 1449 / 3402 - FREE is a rolling
  50-frame free-cycle minimum and is load/RNG dependent). Comfortably positive
  (no raster-budget overrun). Stress runs bottom lower under artificial
  saturation but that is the documented overload case, not a regression, and
  the engine was not touched.

## Section screenshots
`build/terrain-shots/{S1..S5,wrap99,wrap00}.png` pulled from the 5200-frame
capture at SCROLL_ROW 2 / 24 / 48 / 68 / 88 / 99 / 0. Five sections render
visually distinct; wrap seam shows continuous black, no torn row, no garbage.

## Status: implemented, not committed. Awaiting human VICE playtest.
