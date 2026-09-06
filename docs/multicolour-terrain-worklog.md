# Multicolour + per-cell-colour terrain — active worklog

Branch: `multicolour-with-turrets-experiment` (from `bg-turret-test`).
Baseline HEAD `96c6924 Prototype background-mounted turrets`.
Baseline PRG SHA-256 `fd3d3a68099d2832ee71840c82bc51a6123424caa98d75745b43af6fc61acbb2`
(fresh KickAssembler 5.25 build, clean working tree confirmed before edits).

ENGINE-only task. Keep `STAGE_METATILE_ROWS = 25`; no long-stage / 16-bit stage
indexing. Do not redesign the scroller/raster/multiplexer. Turret gameplay is a
protected regression target. No commits/pushes.

## Inspection findings (authoritative from current source)

### Charset ($3800..$3FFF, 256 glyphs) — full allocation audit
- 0..127   : ROM charset copy (`setupStarfieldCharset` copies all $D000..$D7FF).
             1..26 letters, 32 space, 48..57 digits used by menu/GAME OVER/
             HISCORE text. Rest = ROM graphics, present but unreferenced.
- 128..145 : HUD private glyphs, written by `initFixedHud`. $3C00..$3CCF.
- 146..159 : ROM-copy filler, UNREFERENCED. "HUD expansion reserve" — keep.
- 160..199 : terrain art, written by `initBackground` from `terrainGlyphs`.
             $3D00..$3E3F. `TERRAIN_GLYPH_BASE=160`, `TERRAIN_GLYPH_COUNT=40`.
- 200..211 : turret private glyphs (`TURRET_GLYPH_BASE=200`, 12 = TURRET_COUNT*4),
             written by `initBackgroundTurrets`/`publishTurretGlyphs`. $3E40..$3E9F.
- 212..223 : ROM-copy filler, UNREFERENCED. $3E60..$3EFF. (verified: no code or
             metatile byte references 212..239 or 252..255.)
- 224..225 : diagnostic rail/diagonal (`bgDiagnosticGlyphs`), written by
             `initBackground`. $3F00..$3F0F. Not referenced by the bas-relief
             metatiles but still installed each game start. Leave alone.
- 226..239 : ROM-copy filler, UNREFERENCED. $3F10..$3F7F.
- 240..251 : starfield glyphs (`STAR_CHAR_BASE=240`), `setupStarfieldCharset`.
             $3F80..$3FDF.
- 252..255 : ROM-copy filler, UNREFERENCED. $3FE0..$3FFF.

Free code ranges: 146..159 (reserved), **212..223**, **226..239**, 252..255.

### $D016 (VIC_CONTROL_2 / multicolour + XSCROLL)
Grep of all src/*.asm: **$D016 is never read or written anywhere.** The scroller
is vertical-only; horizontal fine scroll (XSCROLL) is unused. KERNAL leaves
$D016 = $C8 (CSEL=1, XSCROLL=0, MCM=0). Enabling MCM (bit 4) once at init is
therefore independent of all fine-scroll behaviour (which lives entirely in
$D011 YSCROLL, owned by the raster display hook).

### Coarse-scroll timing budget (from fixed-hud-codex-worklog.md + turret worklog)
- `prepareBackgroundCoarse` (UPPER char shift, frame N): waits for RASTER>=160,
  then unrolled `shiftBackgroundUpper` (rows1..11->2..12, 440 cells, 3520 cyc) +
  `saveCrossingRow` (40, 320) + `renderStageRowToScreen` for row1 (~561+copy).
  Pure CPU incl. caller JSR measured 5881..5928 cyc. Admission cutoff RASTER<184,
  all LIVE batches done. Window [184,312]=8064 cyc; budget model 6000 CPU + 1056
  sprite-DMA + 430 badline = 7486; ~578 cyc theoretical margin. Typical real:
  copy begins ~165..180, ready ~261..278.
- `finishBackgroundCoarse` (LOWER char shift, frame N+1, ~raster 5..110):
  `shiftBackgroundLower` (rows13..22->14..23, 400 cells, 3200 cyc) +
  `restoreCrossingRow` (40, 320). Deadline = row13 badline ~160. Slack ~3400 cyc.

### Scroller data contract
- `decodeStageCharacterRow(BG_LOGICAL_ROW)` -> `BG_INCOMING_ROW` (40 char codes),
  from `metatileDefs` (16*16). `copyIncomingRowToScreen(BG_DEST_ROW)` copies
  `BG_INCOMING_ROW` -> screen row; **colour RAM not touched anywhere in the
  scroller.** `initBackground` blanket-fills all 1000 colour cells with
  `TERRAIN_COLOUR=9`, then `initFixedHud` overwrites row0 colour with 1 (white).
- `renderStageRowToScreen` tail `jmp installTurretRow` (turret hook): O(1),
  writes 2 stable turret screen codes for a world row via `turretRowGlyph`/
  `turretRowColumn` lookup. Never touches `BG_INCOMING_ROW` or colour RAM.
- Turret bodies: screen codes 200..211 are permanent world content; on death the
  private glyph BITMAPS are rewritten to the cached underlying terrain glyphs
  (`turretGroundGlyphs`, 96 B). Turret never patches screen RAM at runtime.

## Plan (staged)

**Stage 1 — charset namespace + turret relocation + guards (no behaviour change).**
- Terrain namespace -> **160..223** (64 codes), bitmaps $3D00..$3EFF.
  `TERRAIN_GLYPH_COUNT` stays 40 (used); add `TERRAIN_GLYPH_NAMESPACE=64`.
  Generalise the glyph-copy loop (was hard-unrolled x5 for 40) to copy
  `TERRAIN_GLYPH_COUNT` glyphs, <=64.
- Turret private glyphs **200..211 -> 226..237** (one const:
  `TURRET_GLYPH_BASE 200 -> 226`; everything else derives). Bitmaps $3F10..$3F6F,
  clear of terrain (<=223), diagnostic (224/225) and starfield (240..251).
- Compile-time guards for both ranges + no-overlap.
- Build; run turret + scroll + raster + lifecycle oracles; confirm zero change.

**Stage 2 — multicolour mode + per-cell colour data + decoder + initial render.**
- Set $D016 MCM bit once at init (preserve other bits).
- `metatileColours` (16*16) parallel to `metatileDefs`; new decoder output
  `BG_INCOMING_COLOUR`; `copyIncomingRowToScreen` writes colour RAM too.
- `initBackground` fills terrain colour from decoded per-cell values.
- Author the regression stage's colours: mostly a 0..7 hires colour; one
  metatile as the deliberate multicolour proof (D021 bg + D022/D023 shared +
  per-cell low-3-bit colour). Keep turret placements on hires cells.
- Turret colour: `installTurretRow` leaves decoded colour in place -> turret
  cells inherit authored terrain colour; guard that every turret cell's
  authored metatile colour is hires (0..7) so private glyphs render hires.

**Stage 3 — colour RAM lockstep in coarse scroll (performance-critical).**
- Move colour bytes with char bytes in `shiftBackgroundUpper/Lower`,
  `saveCrossingRow`/`restoreCrossingRow`, incoming-row insertion.
- OPEN RISK: doubling the coarse copy does not obviously fit the proven
  [160,312] upper window (~578 cyc margin today). Options under evaluation:
  split colour work across prepare(N)/finish(N+1) by per-row badline deadline;
  relocate expanded copy code (free RAM: $6350..$6FFF below the $7000 test
  scratch, and $C000..$CFFF); tighten the admission cutoff and rely on the
  existing SAFE coarse deferral for heavy frames (measure + report rate).
- If no safe fit is found: STOP and report with measurements rather than ship a
  light-load-only timing assumption.

## Stage 1 DONE — charset namespace + turret relocation (no behaviour change)

Source changes:
- `src/main.asm`: `TERRAIN_GLYPH_NAMESPACE = 64` (codes 160..223); `TERRAIN_GLYPH_COUNT`
  stays 40 but is now a soft value guarded `1..namespace` and `% 8 == 0`; glyph
  copy loop generalised (`TERRAIN_GLYPH_COUNT / 8` 64-byte chunks, was hard 5);
  namespace bitmap guard tightened to end `<= $3EFF` (before diagnostic $3F00).
- `src/background_turrets.asm`: `TURRET_GLYPH_BASE 200 -> 226` (one const;
  `turretRowGlyph` table, `publishTurretGlyphs` dest, `installTurretRow` codes all
  derive). New guards: clears terrain namespace + diagnostic (`>= 226`), clears
  starfield (`+ TURRET_COUNT*4 <= 240`), bitmap end `<= $3F80`. Added exported
  label `TURRET_GLYPH_BASE_CODE` (KA exports labels, not `.const`) so the capture
  oracles locate the private-glyph code/charset region with no literal.
- `tools/check_fixed_hud_capture.py`: turret glyph base read from
  `sym['TURRET_GLYPH_BASE_CODE']` (was literal 200 / byte 1600).
- `tools/vice_turret_cases.py`: underlay-restore reads
  `sym['TURRET_GLYPH_BASE_CODE']*8+0x3800` (was literal `$3E40`).

Build: clean, all guards pass. Memory map unchanged (`$4000-$5841`, `$6000-$634f`,
`$8800-$8edf`). PRG SHA-256 `683e18f345e118f761bb5e8610af8a00f059d8a0c806ab55b1b0ef766f4726f5`
(differs from baseline only by 200->226 in turret glyph dest addrs + row table).

Validation (build/mc-test/s1-smoke, 900 physical frames):
- check_fixed_hud_capture: **0 failures**, cadence [19656], 37 coarse transitions;
  private-glyph publication/charset-integrity check passes at the new $3F10 region.
- check_raster_capture: 0 service failures, 0 sprite-start misses, cadence [19656].
- vice_turret_cases: 45 checks, **0 failures** (incl. "death restores exact
  terrain glyph bytes" and "all destroyed underlay exact" at $3F10). CPU bodies
  unchanged: publish 469..503, aim 59..74, position 116..159, update 126..522.
- vice_raster_lifecycle: **0 failures**, turret_reset_checked, gameplay jiffy drift 0.

Final terrain glyph ownership: codes **160..223** (64), bitmaps **$3D00..$3EFF**;
40 authored so far (160..199, $3D00..$3E3F), 200..223 reserved for editor output.
Final turret private glyph ownership: codes **226..237** (12 = TURRET_COUNT*4),
bitmaps **$3F10..$3F6F**. Between diagnostic (224/225, $3F00..$3F0F) and starfield
(240..251, $3F80..$3FDF). 238/239 and 252..255 remain free filler.

## Stage 2 DONE — multicolour text mode + per-cell colour data + initial render

Source changes (on top of Stage 1):
- `src/variables.asm`: `COLOUR_DST = $f7` (colour-RAM write pointer);
  `VIC_CONTROL_2 = $d016`, `EXTRA_COLOUR_1 = $d022`, `EXTRA_COLOUR_2 = $d023`.
- `src/main.asm`:
  - `TERRAIN_COLOUR 9 -> 1` (white; brown is not a hires colour under mixed
    hires/MC text mode). `TERRAIN_MC_COLOUR_1 = 11`, `TERRAIN_MC_COLOUR_2 = 12`
    for $D022/$D023. Guard `TERRAIN_COLOUR <= 7`.
  - `initBackground`: set $D016 MCM bit (preserve CSEL/XSCROLL/unused); set
    $D022/$D023. `endGame`: clear $D016 MCM bit (menu/GAME OVER are plain hires;
    verified $D016 = $C8 at the menu, and $D016 is otherwise untouched anywhere).
  - `decodeStageCharacterRow`: parallel `metatileColours` lookup -> new
    `BG_INCOMING_COLOUR` (40 B) using the identical id*16 + row*4 + s offset.
  - Split colour write out of `copyIncomingRowToScreen` into
    `applyIncomingRowColour` (COLOUR_DST = screen ptr, hi + $D4).
    `renderStageRowToScreen` now writes the CHARACTER row only.
  - `initBackground` row loop: `renderStageRowToScreen` + `applyIncomingRowColour`.
  - `finishBackgroundCoarse`: applies the new top row's colour there (frame N+1,
    deadline badline ~55, runs ~raster 15) instead of in `prepareBackgroundCoarse`
    (frame N, tighter budget). `BG_INCOMING_COLOUR` is stable between the two.
- `src/stage_test.asm`: `metatileColours` (16x16), `METATILE_COLOURS_END`; header
  updated to "three tables". Regression stage: mostly hires white (1), hires
  accents (2/9/10 cyan, 7/8 yellow), and metatile 13 (DETAIL) is the deliberate
  MULTICOLOUR proof (all cells >= 8: 9/11/13/15 varied per cell + shared
  $D022/$D023). Turret metatiles 0/5/12 kept fully hires.
- `src/main.asm` post-import: `metatileColours` size guard (256 B).
- `src/background_turrets.asm`: comment - `installTurretRow` writes chars only,
  turret cells inherit their (hires) terrain colour.

Build: clean, all guards pass. Segments $2920-$2cb9, $4000-$5941, $6000-$634f,
$8800-$8edf. PRG SHA-256 `96566f684761e9df048d094e6907e86b9106027f2f0a12429ecacc54a152380b`.

Timing measurements (tools/vice_raster_cases.py --copy-cpu, all 100 origins):
- baseline prepareBackgroundCoarse CPU incl. JSR: 5881..5928
- Stage 2a (colour written in prepare): 6651..6731  (+~770; long run -> 16
  coarse deferrals / 107 transitions ~= 15%: a material regression)
- Stage 2b (row-1 colour deferred to finishBackgroundCoarse): 6232..6312
  (+~350, all in decodeStageCharacterRow's 40 colour stores; long run -> **0
  deferrals** / 108 transitions; raster oracle 0 svc/start/catchup/replay;
  cadence [19656]; turret oracle 0; lifecycle 0; 17 scheduler cases 0/0)
- Stage 2b FREE (2600-frame normal): min 567, median 4599, max 10395. min varies
  with wave RNG run-to-run (Stage 2a min 1638; turret-baseline runs 1575/4473).
  No overrun (0 replay, exact cadence). Re-measure in the consolidated pass.

Visual: MCM confirmed working; terrain recognisable (white bas-relief + hires
yellow/cyan accents); metatile 13 renders as a visibly distinct 3-tone
multicolour block; HUD/sprites/menu unaffected; no tearing.

Oracle note: `check_fixed_hud_capture.py`'s PIXEL model still renders terrain as
brown hires, so it reports ~5.3k physical-pixel mismatches/frame (colour-model
only). Its STRUCTURAL checks (matrix, charset integrity, stock glyphs, HUD,
cadence, coarse) all pass. Teaching that model per-cell colour + MCM bit-pairs
is a follow-up (see report).

## Stage 3 — colour RAM lockstep in coarse scroll: STOPPED (measured blocker)

Requirement 8: colour RAM must shift with screen RAM during a coarse step.
The coarse step is deliberately split: `prepareBackgroundCoarse` (frame N,
starts at RASTER>=160, ends ~raster 260-278, ~52 lines / ~3.3k cyc real slack to
frame end) shifts CHAR rows 1..11 -> 2..12 + saves the crossing row + renders
the new row 1; `finishBackgroundCoarse` (frame N+1, ~raster 15..70, deadline row
13 badline ~160, ~3.4k cyc slack) shifts CHAR rows 13..22 -> 14..23 + restores
the crossing row.

Adding the parallel COLOUR movement costs ~+3520 cyc (upper 11-row shift) +
~+3200 (lower 10-row shift) + ~+640 (crossing save/restore), all unrolled at
8 cyc/cell. Measured/derived findings:

1. The UPPER colour shift cannot go in frame N. `prepareBackgroundCoarse`
   already runs raster 160 -> ~260-278 at Stage 2b (6232-6312 CPU + DMA). It
   cannot start before raster 160 (VIC caches row 12 at ~151). +3520 cyc ->
   ends ~raster 316-340, i.e. 4..28 lines INTO frame N+1. That delays frame
   N+1's applyFineScroll / renderSprites / armFirstBatch / finishBackgroundCoarse
   by that much, which cascades: `finishBackgroundCoarse` (itself now heavier)
   would start ~raster 45-60 and, with its own +3200 colour work, miss the row
   13 badline (~160) by ~10-15 lines. Confirmed unsafe.
2. The UPPER colour shift cannot go in frame N+1 either. `finishBackgroundCoarse`
   starts ~raster 15; a clobber-safe DESCENDING colour shift of 11 rows
   (3520 cyc = 56 lines) finishes ~raster 71, but colour row 2's badline is
   ~63 -> misses by ~5-8 lines. An ASCENDING shift needs the pre-shift rows
   1..11 saved to a 440-byte buffer first, and that 3520-cyc save has no
   deadline-free home in either frame's window.
3. No code-space for fully-unrolled colour copies (~5.5 KB). The $4000 copy
   segment has 1727 B free to its $6000 guard; the only clean holes are
   $6350..$6FFF (~3.2 KB, below the $7000 test-injection scratch used by
   vice_raster_cases.py / vice_turret_cases.py) and $C000..$CFFF (4 KB) - each
   too small for both the upper and lower unrolled colour copies.

Per AGENTS.md / the task ("optimise the colour-copy path carefully before
considering architectural changes"; "a technically honest stop with measured
blockers is preferable to an unvalidated implementation"; "STOP and report ...
before inventing a larger architectural change"), Stage 3 is NOT forced through.
It requires an approved change to the protected scroller. Options for a
follow-up task, in rough order of invasiveness, are in the end-of-task report.

Consequence for now: during the ~1 frame a coarse step is in flight, the 21
scrolled rows keep their PREVIOUS colour while their characters advance one row
(a 1-row colour lag that resolves on the next coarse step). The incoming row's
colour, initial render, wrap seam (rows 0/24 are OPEN/black -> colour-agnostic)
and all non-scrolling areas are correct. Turret cells inherit terrain colour and
have the same 1-row lag as the terrain they sit on; turret gameplay/restoration
of CHARACTER data is unaffected (regression oracles pass).

## Status: Stages 1 & 2b complete and validated. Stage 3 stopped with measured
## blockers - see docs and end-of-task report. No commits/pushes.

## ================================================================
## FOLLOW-UP TASK - global fixed terrain multicolour palette (no colour scroll)
## ================================================================
## (Stages 1 & 2b checkpointed as commit 2744b35; this section works on top.)

Decision: abandon per-cell colour RAM for ordinary scrolling terrain. Use ONE
fixed stage-global multicolour colour-RAM value for the whole playfield, so
colour RAM is written once and NEVER scrolled. All visual detail lives in the
glyph bitmaps as authored 2-bit multicolour pixels. This drops the entire
Stage-2/3 colour-copy path.

### Retained from the previous experiment
- `$D016` MCM enable (initBackground) / disable (endGame); `VIC_CONTROL_2`,
  `EXTRA_COLOUR_1/2` in variables.asm.
- Terrain glyph namespace 160..223 (64), generalised glyph copy, guards (Stage 1).
- Turret private glyphs relocated to 226..237; exported `TURRET_GLYPH_BASE_CODE`;
  charset ownership guards (Stage 1).
- Tool changes deriving the turret glyph base from the symbol (Stage 1).
- `TERRAIN_MC_COLOUR_1` = 11 ($D022). `TERRAIN_MC_COLOUR_2` retuned 12 -> 15
  ($D023) for a clearer dark/light spread.

### Removed (dead per-cell-colour machinery)
- `metatileColours` table + `METATILE_COLOURS_END` + its size guard.
- `BG_INCOMING_COLOUR` buffer; `applyIncomingRowColour` routine; the parallel
  `metatileColours` stores in `decodeStageCharacterRow`; the row-1 colour apply
  in `finishBackgroundCoarse`; the per-row colour apply in the init row loop.
- `COLOUR_DST` zero-page pointer.
- `.const TERRAIN_COLOUR` (0..7 hires fallback) -> replaced by
  `.const TERRAIN_COLOUR_RAM = 8|1` (fixed multicolour value: bit3 MC, low3 = 1
  = white), guarded 8..15.

### New model
- `initBackground` fills all 1000 colour-RAM cells with `TERRAIN_COLOUR_RAM`
  once; `initFixedHud` then repaints row 0 (white hires HUD). Colour RAM is
  static thereafter. No crossing-colour buffer, no coarse colour shift, no
  incoming-colour copy.
- `decodeStageCharacterRow` / `renderStageRowToScreen` / `copyIncomingRowToScreen`
  are back to character-only. `finishBackgroundCoarse` / `prepareBackgroundCoarse`
  add zero colour work.
- Stage palette: $D021 = 0 (black), $D022 = 11 (dark grey), $D023 = 15 (light
  grey), TERRAIN_COLOUR_RAM & 7 = 1 (white). Four tones per glyph.

### Multicolour art proof
12 terrain glyphs re-authored as true 4-colour multicolour:
- SLAB bevel: 166 EDGE_T2, 167 EDGE_B2, 168 EDGE_L2, 169 EDGE_R2, 174..177
  thick corners -> light-grey lit top/left edge, dark-grey shadow bottom/right
  edge, white interior. Makes metatiles 3 (SLAB), 4 (SLAB_OPEN), 5 (SLAB_L),
  6 (SLAB_R), 11 (CORNER), 13 (DETAIL frame) render as bevelled bas-relief.
- DETAIL panel: 194 SLOT_V (light/white/dark/white ribs), 195 SLOT_H (light rib
  / dark rib), 197/198 NOTCH (white block + dark-grey notch) -> metatile 13
  reads as a shaded ribbed tech panel.
The remaining glyphs stay 2-tone (00/11 = black/white), identical to the old
mono relief. `CHANNEL_V` (uses 168/169) picks up the light/dark bevel walls.

### Turrets
7 `turretArt` templates re-authored as multicolour bitmaps (common white dome on
a dark-grey base + a light-grey barrel nub per aim; style 6 = white flash). No
gameplay/publication/cache logic changed. Turret screen cells carry the same
fixed `TERRAIN_COLOUR_RAM`; destroyed turrets restore the cached (now MC)
terrain glyph bitmaps - colour is automatic. `installTurretRow` still writes
characters only.

### Build
Clean, all guards pass. Segments $2920-$2c53, $4000-$5841 (back to the Stage-1
size; `metatileColours` gone), $6000-$634f, $8800-$8edf. PRG SHA-256
`27b7441827a3679f90c8d330468cb374d56a5ec0825a3ada8d908ba8032818af`.

### Measurements
- `prepareBackgroundCoarse` pure CPU incl. JSR, all 100 origins:
  **5881..5928 = byte-for-byte the turret baseline** (Stage 2b was 6232..6312).
  Zero coarse-scroll colour cost.
- Matched 3000-frame `--physical --trace` capture, this build vs baseline
  `96c6924` (built to build/base96):
  | metric | baseline 96c6924 | this build |
  |---|---|---|
  | coarse transitions | 123 | 124 |
  | safe coarse deferrals | 45 | **11** |
  | FREE min / median / max | 1575 / 6237 / 11277 | 2079 / 6489 / 11655 |
  | raster svc / start / replay | 0 / 0 / 0 | 0 / 0 / 0 |
  | frame cadence | [19656] | [19656] |
  Deferrals and FREE are BETTER than the turret baseline; deterministic (two
  runs identical). No new coarse-scroll timing regression.
- turret functional cases: 45 checks, 0 failures. lifecycle: 0 failures, turret
  reset OK, jiffy drift 0. 17 scheduler cases: 0/0.
- Visual: bevelled multicolour slabs + ribbed DETAIL panels clearly show
  black/dark-grey/light-grey/white; terrain+colour fully coherent through scroll
  and wrap; **no top-row colour artefact** (colour RAM is uniform - nothing can
  desync). HUD/sprites/menu unaffected ($D016 = $C8 at menu).
- Oracle note: `check_fixed_hud_capture.py`'s pixel model still renders terrain
  as brown hires -> `physical pixels` class flags on ~24 sampled frames
  (colour-model only). Structural checks (matrix, charset integrity, stock
  glyphs, HUD, cadence, coarse) all pass. Updating that model to multicolour is
  still the outstanding follow-up.

### Status: complete. Ordinary terrain = fixed multicolour palette, no colour
### scroll. Stage-3 per-cell colour path fully removed. No commits/pushes.

## ================================================================
## FOLLOW-UP - full continuous bas-relief hull stage (visual/data proof)
## ================================================================
## (Fixed-palette engine checkpointed as a24afbe; this is ART/DATA only.)

Goal: replace the mixed legacy test art with a complete 10x25 stage that reads
as one continuous constructed grey surface (Uridium-style depth from four
colours), so the human can judge whether the fixed-4-colour-per-stage model is
visually sufficient. No engine change beyond ONE palette constant.

### Palette retune (the only non-data change)
`TERRAIN_MC_COLOUR_1` 11 -> 12 (so $D022 = grey 12 = the dominant BASE plating).
`TERRAIN_MC_COLOUR_2` stays 15 ($D023 = light grey = raised/bevel). $D021 = 0
(black = DEPTH only). `TERRAIN_COLOUR_RAM` unchanged (8|1 -> white highlight).
Ramp: black < grey(base) < light-grey(raised) < white(highlight).
Sprite shared colours ($D025=11, $D026=15) left untouched; player individual
colour 2 (red) contrasts strongly with the grey surface.

### Data changes
- `src/main.asm`: `TERRAIN_GLYPH_COUNT` 40 -> 48; `terrainGlyphs` replaced with
  41 authored + 7 reserved glyphs (codes 160..207, bitmaps $3D00..$3E7F; 208..223
  still free). Comment above the block rewritten.
- `src/stage_test.asm`: `metatileDefs` + `stageMetatileRows` fully replaced; new
  16-metatile construction kit + 25-row stage; header legend rewritten.
- `src/background_turrets.asm`: `turretCols` [10,28,6] -> [17,29,13];
  `turretRows` [99,32,65] -> [13,29,57]. Each turret now sits on the interior of
  a M14 MACH housing (platform A, section-B platform, section-D massif) so it
  reads as machinery emerging from the hull. Disjoint-row guard still satisfied.
- `tools/vice_turret_cases.py`: the hitscan/aim/fire sub-tests derived their ray
  and player-X coordinates from a hard-coded turret-0 X of 104 (old column 10).
  Now computed from the turret's authored X (`TURRET_X_LO/HI`), mirroring the
  Stage-1 practice of reading placement from the running program. Turret GAMEPLAY
  is unchanged; only stale test literals moved.
- Generator: `scratchpad/relief.py` (glyph/metatile/stage designer + ASCII
  preview + KA emitter). Not part of the build.

### 16-metatile construction kit
M0 PLATE (grey base + faint 32px plate grid) | M1 R_FILL (raised interior) |
M2..M5 R_T/R_B/R_L/R_R (raised platform edges) | M6..M9 R_TL/R_TR/R_BL/R_BR
(raised platform outer corners) | M10 CHAN_V (vertical groove, tiles T-B) |
M11 CHAN_H (full-width shallow groove, tiles L-R) | M12 RECESS (inset panel:
grey floor, shadow N/W, lit S/E; tiles into fields) | M13 GRILLE (raised-louvre
vent bank) | M14 MACH (machinery housing; turret mount) | M15 STEP (quiet base
+ a small stepped detail). M2..M9 + M1 build raised platforms of any size.

### Stage composition (25 rows, wraps grey->grey)
r0-1 intro grey plating | r2-4 platform A (96px tall, width-spanning) + turret 0
| r5 grey | r6-9 section B: vertical channels W, inset-panel field, platform E +
turret 1 | r10 grey | r11 full-width channel/plate-boundary | r12 grey+grille |
r13-17 section D: 160px structural massif + grille + machinery + turret 2 | r18
grey | r19-20 section E: paired channels flanking a grille bank | r21 grey |
r22-23 platform F | r24 grey plating (wrap seam).

### Continuous grey surface / lighting / four colours
Base is grey (01) everywhere - PLATE and STEP fill the quiet rows; no metatile
is "open black". Black (00) appears only as: plate-seam grooves, channel floors,
recess shadow walls, machinery slots, the thin drop-shadow line under raised
S/E edges. Light source is top-left across the whole stage: raised N/W rims and
"/" bevels are white (11); raised faces are light grey (10); S/E edges step
grey->thin black; recesses are dark on their N/W inner walls, light on S/E.
All four values carry structure.

### Build + validation (final build)
Clean, all guards pass. PRG SHA-256
`ea803ed1d06de7aed53a4eaa2d4da9e83b8ff8e7844a18dd400e3b2c08632024`.
- `prepareBackgroundCoarse` CPU (all 100 origins): **5881..5931 = the turret
  baseline exactly**. The scroller code path is untouched; zero timing change.
- raster oracle (2600-3000 frames): 0 service failures, 0 sprite-start misses,
  0 catchups, 0 replay frames, frame cadence deltas [19656].
- turret functional probes: 45 checks, 0 failures (hitscan/aim/fire/damage/
  destruction/underlay-restore/cap all pass with the new placements).
- turret capture oracle: 0 failures (per-frame visibility/screen-Y vs presented
  origin, health, shared bullet cap, slot-0 identity, dead reentry).
- lifecycle: 0 failures, turret reset checked, gameplay jiffy drift 0.
- 17 raster scheduler cases (all 8 phases): 0/0.
- safe coarse deferrals: 5..21 per stage circuit across runs (turret baseline
  itself is ~36; previous fixed-palette build ~9). Within band, all the SAFE
  kind (0 replay frames, cadence never lost). The turret repositioning clusters
  active turrets so per-frame turret CPU peaks more often - it exercises the
  existing hold-and-retry more, it does not break it.
- FREE (rolling 50-frame min, deterministic test): min 630..1386 across runs,
  median ~5900. Lower than the 2079 of the previous checkpoint because the three
  turrets are now closer together (more simultaneously active). No frame
  overran (0 replay, exact cadence). Worth watching if turret load grows.
- HUD structural oracle: matrix / charset-integrity / stock-glyph / FREE /
  edge-motion / PAL-cadence all pass. Its `physical pixels` class fails on ~24
  sampled frames ONLY because `expected_pixels` still renders terrain as brown
  hires - it has no MCM model. This was already stale before this task; it is
  NOT a regression and no engine behaviour was changed to satisfy it.
- Visual (build/mc-test/f-*.png, rf-*.png): the whole playfield reads as one
  grey constructed surface; large raised platforms with bevelled rims; channels,
  inset panels, grille banks; turrets sit inside machinery housings; seamless
  grey wrap; player/enemies/bullets clearly readable against the grey.

### Multicolour-resolution compromises
Each char is 4 double-wide MC pixels, so bevels/rims are 1-2 MC pixels (2-4
hires px) wide - shapes are drawn across several chars/metatiles, not per char.
Diagonal "/" and "\" bevels are coarse. The recess "hole" in a M12 tile is only
2 chars, so recessed regions are shown as tiled panel fields rather than one
smooth pit. The base plate texture (studs/seams) is deliberately light so it
reads as machined surface, not noise.

### Status: complete - full bas-relief hull proof stage. No commits/pushes.

## ================================================================
## FOLLOW-UP - turret-kill scroll hitch + stale multicolour visual oracle
## ================================================================
## (Works on top of c4cbe44. Engine fix in src/main.asm; tools only otherwise.
##  No commits/pushes.)

### Task A/B - turret-kill single-frame background scroll hitch (DONE)

Hypothesis PROVEN. On the kill frame `updatePlayerFire -> hitCannonTarget`
(fatal branch) -> `awardKillScore` -> `displayScore` runs a repeated-subtraction
5-digit decimal conversion synchronously inside `updateObjects`
(~267..892 cyc, scaling with the score's digit sum). That delays every later
gameLoop step so `prepareBackgroundCoarse` is reached ~5..15 raster lines later.
On a frame that is ALSO a coarse-transition frame where prepare was already
being reached within ~15 lines of the raster-184 admission cutoff, the extra
delay crosses 184 -> coarse admission rejected -> `BG_COARSE_DEFERRED++`,
fine-scroll safely held one frame, physical frame still exactly 19656 cyc ->
one visible single-frame background hitch.

Direct evidence (tools/vice_turret_kill_timing.py):
- Part A isolated CPU: non-fatal hit critical path ~44 cyc; fatal hit
  (score-dependent) ~309..934 cyc; `displayScore` alone 267..892; next-frame
  DEAD underlay publication `publishTurretGlyphs` 58..469 cyc but runs at frame
  START ~170+ lines before that frame's prepare -> cannot cause a coarse defer.
- Part C matched dump/undump pairs (identical machine state, only
  `TURRET_HEALTH` 1 vs 3): 1/40 natural-coarse frames tipped from reached-raster
  173 -> exactly 184, deferring only in the fatal case (def(F)=1, def(NF)=0).

Fix (src/main.asm, +32/-8): `SCORE_DIRTY` flag. `awardKillScore` now only adds
the 100-point value and sets `SCORE_DIRTY` (removed its now-needless `txa/pha
.. pla/tax`); new `refreshScoreIfDirty` runs `displayScore` once, called from
`gameLoop` immediately AFTER `prepareBackgroundCoarse` and before
`waitForGameFrame` (off the gameplay->coarse critical path, still before the
end-of-frame capture so screen RAM digits are current). `setupScoreDisplay`
clears the flag on a new game. Score VALUE updates immediately; the kill and
the 100-point award still occur exactly once; observable HUD timing unchanged
(same 1-frame digit lag the inline path already had, already tolerated by
check_fixed_hud_capture).

After fix: fatal-hit critical path 44 -> ~75 cyc (adds ~31, vs the ~309..934 it
removed). Part C: 0/40 fatal-only deferrals, delta_raster ~0. A 3000-frame
playtest capture's 6 deferrals all cluster at phase-7 frames far from any kill
frame (score_dirty=0 there) - the kill frames no longer defer. All standard
oracles green; PAL cadence [19656]; >=1 full 25-row stage circuit.

### Task C - stale pre-multicolour visual validation (IN PROGRESS)

Audit of every capture oracle for pre-multicolour hires/brown assumptions:

| tool | stale assumption | verdict |
|---|---|---|
| check_fixed_hud_capture.py | `expected_pixels` renders terrain as brown (119,83,0) hires, 8 one-bit px/byte | FIX - primary MC pixel oracle |
| check_scroll_capture.py | pixel check filters to black/`(119,83,0)` and tests 1 bit/px | FIX - port to MC model |
| check_scroll_edges.py | `check_capture()` expects set terrain bit -> `(119,83,0)` | FIX `check_capture()`; `check_geometry()` untouched (its probe forces D016=$C8 + white hires colour RAM deliberately) |
| check_viewport_capture.py | "only white playfield pixels are sprites+HUD" - MC bit-pair 11 is white too | FIX - model terrain white pixels |
| check_hud_capture.py | old two-marker HUD proof; needs `HUD_PATCHED`/`HUD_TERRAIN` symbols that no longer exist in source | OBSOLETE - superseded by check_fixed_hud_capture.py; left as-is, not in current flow |
| check_turret_capture.py | none (no pixel work) | no change |
| check_raster_capture.py | none (timing only) | no change |
| vice_raster_lifecycle / vice_turret_cases / vice_raster_cases (non-solid) | none relevant | no change |

Correct mixed hires / global-MCM oracle model (`tools/mc_terrain.py`, shared):
global char MCM is on during PLAYING. Per cell, colour-RAM bit 3 CLEAR => HIRES
(8 one-bit px: 1->colour-RAM&15, 0->$D021); bit 3 SET => MULTICOLOUR (4
double-width px from bit pairs; 00->$D021 01->$D022 10->$D023 11->colour-RAM&7).
The fixed HUD row stays hires (its colour RAM is 1). Terrain+turret cells use
one fixed colour-RAM value (`TERRAIN_COLOUR_RAM`).

Register/colour values are read from the capture: `tools/vice_scroll_test.py`
now also dumps `vic.bin` ($D000..$D02F, once) and `NNNNN.colour`
($D800..$DBFF, per frame); `tools/vice_raster_cases.py --solid` dumps the same.
When those files are absent (older captures) `mc_terrain` parses
`src/main.asm`'s `.const`s instead, so no palette-register literals live in
Python. Palette index->RGB is the fixed VICE 3.10 `screenshot 2` table
(indices 0/1/12/15 verified against project captures).

Added regression assertions (check_fixed_hud_capture.py): global char MCM
enabled during PLAYING; terrain colour RAM is one fixed value across the whole
run and is a valid multicolour selector 8..15; HUD colour RAM stays hires
(bit 3 clear) and unchanged; terrain glyph codes stay in 160..223; turret
private glyphs stay in 226..237; ownership ranges disjoint.

Tool changes:
- NEW `tools/mc_terrain.py` - shared `PaletteConfig` + `scanline()`/`row_bytes()`
  mixed hires/MCM renderer; `load_palette_config()` (vic.bin -> src/main.asm
  fallback); `load_colour_ram()` (per-frame `.colour`, masked to 4 bits, ->
  synthesised model fallback); `VICE_PALETTE` (VICE 3.10 `screenshot 2` RGB,
  indices 0/1/12/15 verified against project captures; index 11 vs 12 corrected
  after first run showed $D022=colour 12 renders (148,148,148) not (98,98,98)).
- `vice_scroll_test.py`: dump `vic.bin` (once) + `NNNNN.colour` (per frame).
- `vice_raster_cases.py --solid`: same two dumps.
- `check_fixed_hud_capture.py`: `expected_pixels` renders per-cell hires vs MC;
  HUD stays hires; + the regression asserts above; JSON now reports
  render_model / char_mcm / palette_registers / terrain_colour_ram.
- `check_scroll_capture.py`: pixel oracle ported to the MC model
  (`row_bytes`); geometry corrected to raster-71 first terrain row
  (`y-(48+phase)`, was `y-(32+phase)` = 2 rows high); sprite mask box
  y-alignment corrected by 1px (Y-15..Y+5); turret columns skipped (covered by
  check_fixed_hud_capture / check_turret_capture); brown filter removed.
- `check_scroll_edges.py` `check_capture()`: spatial terrain expectation ->
  MC model, `raster-64-phase` mapping, HUD+separator band (55..70) excluded
  from both spatial and temporal checks, turret spans excluded from both.
  `check_geometry()` untouched (its probe forces D016=$C8 + white hires
  colour RAM).
- `check_viewport_capture.py`: terrain bit-pair-11 white pixels modelled into
  `expected` from `ram`+`.colour`; `raster-64-phase` mapping; first
  post-park phase-step frame exempt from the physical-pixel assertions
  (one-line monitor-poke YSCROLL transient; render-eligibility still checked).
- `check_hud_capture.py`: NOT modified - obsolete (needs `HUD_PATCHED` /
  `HUD_TERRAIN` symbols removed from source long ago); superseded by
  check_fixed_hud_capture.py; not in the current validation flow.

### Task C - validation results (build PRG SHA-256 8f74e1b761d7bed2632d20065ef964a8bef51a3e12b62413f9032e02c1a6d88a)

Fresh 2700-frame `--physical --trace` capture `build/mc-test/taskc-scroll`
(112 coarse transitions = 1.12 stage circuits; raw-table end->start wrap seen
twice; 0 stage-step errors; every frame delta exactly 19656):
- check_fixed_hud_capture: **0 failures**, 158.9M physical-pixel checks under
  the MC model; char MCM enabled; terrain colour RAM fixed at 9 (a valid 8..15
  multicolour selector) for the whole run; HUD colour RAM stays 1 (hires);
  terrain glyphs 160..223; turret glyphs 226..237; ranges disjoint.
- check_scroll_capture: **0 failures**, 145.1M MC pixel checks; stage_loops 2.
- check_scroll_edges: **0 failures** (33.6M edge spatial checks + temporal),
  112 coarse pairs, temporal differences {}.
- check_scroll_edges --geometry (`build/mc-test/taskc-geometry`): 0 failures.
- check_raster_capture: 0 service failures, 0 sprite-start misses, 0 catchups,
  0 replay frames, cadence [19656].
- check_turret_capture: 0 failures.
- check_viewport_capture (6 solid cases viewport_edges / viewport_top_dma /
  viewport_early95 / viewport_late233 / clip_eight / clip_boundary): 0
  failures each (1.41M physical-pixel checks per case).
- vice_turret_cases: 45 checks, 0 failures (`hitCannonTarget` CPU 22..75).
- vice_raster_lifecycle: 0 failures, turret reset checked, gameplay jiffy
  drift 0.
- vice_raster_cases scheduler battery (early24/player37/overlap55/late243/
  eight/zero/one/close4/coarse_late_dma/coarse_sparse_dma, all phases): 0
  service failures, 0 sprite-start misses, cadence [19656] in every case.
- vice_turret_kill_timing re-run on this build: Part A fatal-hit critical path
  now a flat **75 cyc** for every score (was 353..978, scaling with digit
  sum); `displayScore` itself unchanged at 267..892 but off the path; Part C
  **0/40** frames where the fatal kill alone tips a coarse frame into
  deferral; d_raster fatal-vs-nonfatal ~ -2..-3 (fatal path now slightly
  earlier). Natural background deferrals still occur under load (9 over the
  run) but are position-driven, not kill-correlated.

### Remaining limitations / blind spots
- `VICE_PALETTE` index->RGB is calibrated to VICE 3.10 `-default` `screenshot 2`
  output; a different emulator, VICE version, or configured `.vpl` would need
  the four terrain entries (0/1/12/15) re-sampled. `vic.bin` still gives the
  correct register *indices* regardless.
- check_scroll_capture / check_scroll_edges skip the 2-wide turret glyph
  columns in their pixel checks (turret pixels are covered exhaustively by
  check_fixed_hud_capture's absolute + edge-motion oracles and
  check_turret_capture).
- check_viewport_capture exempts one frame (first post-park YSCROLL step) from
  the physical-pixel assertions - a monitor-injection artifact, not engine
  behaviour.
- Human VICE/MiSTer confirmation of the turret-kill hitch fix on real hardware
  timing is still worthwhile (the probe proves the coarse-admission logic, not
  the subjective "no visible hitch").

### Status: Tasks A, B, C complete and validated. src/main.asm carries the
### deferred-score fix; tools carry the MCM visual model. No commits/pushes.

## ================================================================
## FOLLOW-UP - no-player-fire background hitch (turret runtime, NOT kills)
## ================================================================
## New human evidence: the one-frame background scroll hitch still occurs with
## the player weapon NEVER fired, seen twice with a turret ~mid-screen. So it is
## turret-related but needs no turret damage. Investigate turret runtime.
## New tools (probes, no gameplay change): tools/vice_turret_runtime_probe.py,
## tools/vice_turret_stall_ab.py. No commits/pushes.

### Interim findings (probe: vice_turret_runtime_probe.py, player never fires)

- The hitch REPRODUCES with the player never firing (4..26 BG_COARSE_DEFERRED
  increments per ~5000 frames across runs, load/RNG dependent).
- **Every deferral in the no-fire runs is the BATCH-NOT-CONSUMED gate**, NOT the
  raster-184 gate. `prepareBackgroundCoarse` admission:
  `ldx RASTER_BATCH_OFFSET / cpx RASTER_BATCH_END / bcc !defer` fires first, and
  it is the one that trips. Cause breakdown over one run: batch 22, "other" 4,
  raster>=184 **0**. This is a DIFFERENT mechanism from the fatal-kill
  investigation (that one was raster-184 via displayScore).
- Deferral frames: `active object count == 9`, `BATCH_COUNT == 1`, and the
  batch's `BATCH_RASTER` is LOW-SCREEN (measured 229..232) because the 9th
  sorted object is an enemy bullet very low on screen (Y ~196..247).
  `prepareBackgroundCoarse` is reached at raster ~160..195, before the IRQ has
  serviced that low batch -> defer.
- A deferral re-arms `BG_COARSE_PENDING` for the very next frame
  (`updateBackgroundScroll` re-sets it while SCROLL_FINE stays 7), so the defer
  REPEATS every frame until an object despawns and the count drops below 9.
  Observed stall lengths: 1..12 consecutive frames = a 1..12-frame background
  scroll FREEZE (the "single-frame hitch" is the short end of this).
- Turret per-frame CPU is NOT the tipping cost. In matched isolation
  (`turrets_not_visible`, `glyphs_forced_clean`) the reached raster is
  byte-identical - `positionBackgroundTurrets` + `updateBackgroundTurrets` aim/
  style + `publishTurretGlyphs` do not move the coarse margin here.
  `remove_enemy_bullets` moved the reached raster by ~25..30 lines (the BUILD
  sprite-schedule cost of the extra objects) but that is a side effect; the
  deferral is the low BATCH_RASTER, not the reached raster.
- Turret involvement is INDIRECT: turrets periodically fire projectiles into the
  shared enemy-bullet pool (`spawnEnemyBulletAt`, cap MAX_ENEMY_BULLETS=3);
  those bullets travel straight down and dwell in the lower playfield for tens
  of frames. A turret may fire while `TURRET_Y` is as low as 201, spawning a
  bullet at Y~213 - lower than any enemy can (enemy fire band Y < 190). So a
  turret is the object source most able to place the 9th sprite low enough to
  push BATCH_RASTER past where the coarse copy is admitted.

### Reproducibility note
Breaking AT prepareBackgroundCoarse every frame (runtime probe Part B)
over-reports deferrals vs the least-perturbing method (break once/frame at
applyFineScroll, free-run the rest). vice_turret_stall_ab.py does the latter and
A/Bs nofire vs nofire+turret-fire-suppressed vs fire. Result pending.

### Root cause (working, pending the A/B confirmation)
Coarse-transition frame + a 9th active sprite low on screen (an enemy bullet,
supply boosted and placed lowest by turret fire) => LIVE sprite batch scheduled
at raster ~200..232 => `prepareBackgroundCoarse` batch-not-consumed gate defers
the coarse copy, and re-defers every following frame until the object count
drops below 9 => multi-frame background-scroll freeze. The safe deferral gate
itself is behaving correctly.

### Proven root cause (A/B confirmed)

vice_turret_stall_ab.py - breaks once/frame at applyFineScroll, free-runs the
rest, so the coarse-admission decision happens at natural timing. 6000 frames,
matched boot + deterministic directional input, three modes:

| mode | BG_COARSE_DEFERRED increments | stalls (consecutive-frame runs) |
|---|---|---|
| nofire (turrets fire normally)        | 27 | 2  (15 and 12 frames) |
| nofire + turret fire suppressed       |  4 | 1  (4 frames) |
| fire (player fires too - control)     | 54 | 3  (25, 19, 10 frames) |

Every deferral: `BATCH_COUNT>=1`, a turret visible, a bullet low on screen
(Y>=200), `BATCH_RASTER` measured 229..232. Suppressing turret fire removes
~85% of the deferrals and every multi-frame freeze -> **turret firing is the
dominant driver**; turret per-frame CPU is not involved.

Mechanism: coarse-transition frame + >=9 render-eligible sprites where the 9th
(lowest, sorted by Y) is a projectile at Y~200..247 -> buildBatchSpriteSchedule
emits one LIVE batch at BATCH_RASTER ~229 -> prepareBackgroundCoarse (reached
raster ~160..195) fails its "all LIVE batches consumed" gate
(`ldx RASTER_BATCH_OFFSET / cpx RASTER_BATCH_END / bcc !defer`) -> safe defer,
re-armed every following frame until an object despawns -> multi-frame
background-scroll freeze. Turrets feed this because they share the 3-slot
enemy-bullet pool AND may fire while TURRET_Y is as low as 201 (bullet spawns
Y~213, lower than any enemy's <190 fire band), so a turret shot is the sprite
most able to sit low enough to push BATCH_RASTER past the admission point.

### Fix (src/background_turrets.asm, +11 lines, turret code only)

In `updateBackgroundTurrets` `!fire`, after the existing Y-band / player-above /
PLAYER_STATE gates and before `spawnEnemyBulletAt`:

    lda SORTED_COUNT      // previous frame's render-eligible object count
    cmp #8
    bcs !next+           // >=8 -> a turret shot would be the 9th sprite; hold fire

A turret withholds one fire cycle when the playfield is already at the
sprite-multiplex threshold, instead of adding the sprite that makes
buildBatchSpriteSchedule emit the low batch that blocks the coarse copy. Enemy
fire, the shared cap, the allocator, aim, projectile lifecycle, the scroller,
the raster IRQ and the safe-deferral gate are all unchanged. SORTED_COUNT is one
byte, already maintained, ~7 cyc to test; `updateBackgroundTurrets` worst case
126..529 cyc (was ..522). Semantic change: a visible turret occasionally skips a
shot during heavy sprite load - a minor, arguably fair, gameplay effect
justified by removing a visible multi-frame scroll freeze.
tools/vice_turret_cases.py: two `put('SORTED_COUNT',0)` added so the functional
fire tests exercise the fire path rather than the new hold (harness state only).

### Fix A/B (vice_turret_stall_ab.py, same matched boot/input, 6000 frames)

| mode | before | after |
|---|---|---|
| nofire | 27 deferrals, stalls [15, 12] | **5 deferrals, stalls [1,1,1,1,1]** |
| fire   | 54 deferrals, stalls [25,19,10] | 40 deferrals, stalls [18,4,3,10,5] |

nofire (the human's scenario): the multi-frame background freezes are gone; the
5 residual deferrals are all single-frame and only 1 is the batch gate (the
other 4 are the rare non-batch path). fire mode is improved but not eliminated -
player bullets can still be the low 9th sprite and player fire is core gameplay
(not gated).

### Full validation - fixed build PRG SHA-256
955708c0bdb5868c26415466d51f4fa6c2287cedbe553e8c4a518183ea9191ad
(memory map unchanged: $2920-$2c53, $4000-$5841, $6000-$634f, $8800-$8eea)

Fresh 2700-frame `--physical --trace` capture (build/mc-test/turretfix-scroll,
112 coarse transitions = 1.12 stage circuits, raw-table wrap x2, 0 stage-step
errors, every frame delta 19656):
- check_fixed_hud_capture : 0 failures, MCM model, char MCM on, terrain colour
  RAM fixed 9, cadence [19656].
- check_scroll_capture    : 0 failures, 145.2M MC pixel checks, stage_loops 2.
- check_scroll_edges      : 0 failures (33.6M edge checks), 112 coarse pairs.
- check_raster_capture    : 0 service failures, 0 sprite-start misses, 0
  catchups, 0 replay frames, cadence [19656].
- check_turret_capture    : 0 failures.
- check_viewport_capture  : 0 failures (viewport_edges/top_dma, clip_eight/
  clip_boundary solid captures).
- vice_turret_cases       : 45 checks, 0 failures (world turret fired, single
  kill reward, underlay restore, shared cap all pass).
- vice_raster_lifecycle   : 0 failures, gameplay jiffy drift 0, turret reset ok.
- vice_raster_cases       : 9 scheduler cases (early24/late243/eight/close4/
  overlap55/coarse_late_dma/coarse_sparse_dma/zero/one) - 0 service failures,
  0 sprite-start misses, cadence [19656] each.
- vice_turret_kill_timing : Task B deferred-score fix still intact - fatal-hit
  critical path flat 75 cyc all scores, 0/40 fatal-only deferrals.

### Remaining limitations / needs human testing
- Player-fire case: a player bullet low on screen can still be the 9th sprite
  and cause a short coarse stall (fire mode 54 -> 40). Player fire is core
  gameplay and is not gated. If this proves visible in play, the same
  SORTED_COUNT-style hold could be considered for the player's shot cadence, but
  that is a larger gameplay decision.
- The remaining 4 non-batch ("other") single-frame deferrals in the nofire run
  were not fully classified (likely the raster>=256 `VIC_CONTROL_1 bmi` guard or
  probe read jitter); they are single-frame and pre-date this task.
- SORTED_COUNT is one frame stale; a same-frame spawn could still momentarily
  reach 9 sprites. Bounded mitigation, not a hard guarantee.
- Human VICE / MiSTer confirmation that the mid-screen-turret background hitch is
  no longer visible in normal play (no player fire) is the key remaining check.

### Status: no-player-fire turret background hitch - root cause proven, bounded
### turret-fire hold-under-load fix applied and validated. No commits/pushes.

## ================================================================
## FOLLOW-UP - wave-phase turret firing rule (controlled test)
## ================================================================
## Hypothesis: turrets should only fire during wave egress / between-wave
## periods, when enemies are no longer firing, so enemy + turret fire never both
## keep the shared MAX_ENEMY_BULLETS=3 pool populated. Test it against a build
## with the SORTED_COUNT>=8 mitigation compiled out
## (KickAss -define TURRET_FIRE_NO_MITIGATION -> build/nomit/shooter-nomit.prg,
## SHA 8f74e1b7..., == the Task-B-only build).

### Task A - existing wave / enemy-fire state
There is NO global "wave phase" or "enemy firing phase" flag. The wave system
has: WAVE_SPAWNED vs WAVE_ENEMY_COUNT (spawn progress of the current attack),
WAVE_GAP_TIMER (post-attack inter-wave countdown, 0 while spawning else
WAVE_GAP=150..0), SPAWN_TIMER, ENEMY_FIRE_TIMER (global 42-frame fire cadence,
not a phase). Enemy fire eligibility is emergent PER OBJECT in updateEnemyFire:
  OBJECT_TYPE==TYPE_ENEMY && OBJECT_DEATH_TIMER==0 &&
  OBJECT_STAGE!=STAGE_EGRESS && GAMEPLAY_SPRITE_MIN_Y(71) <= OBJECT_Y < 190
"Enemies have stopped firing" == updateEnemyFire's bounded 15-slot scan finds no
such object. That result is computed every cadence tick but not stored.
Per the task's STOP instruction: reported here rather than building a wave FSM.
The probe emulates the rule exactly (same per-object predicate) with harness
pokes; a permanent version would publish the scan result as one byte.

### Task B/D - A/B (probe vice_turret_stall_ab.py, nomit build 8f74e1b7,
### player never fires, 6000 frames, matched boot + deterministic input)

| mode | deferrals | stalls (lengths) | cause | turret shots |
|---|---|---|---|---|
| nofire (turrets fire normally)      | 23 | 7 (6,5,4,3,3,1,1) | batch 21, other 2 | 20 |
| nofire-egressonly (HOLD)            | **1** | 1 (1)          | other 1           | **1** |
| nofire-egressonly-drain             | 9  | 4 (6,1,1,1)       | batch 6, other 3  | 16 |
| nofire-noturretfire (turrets off)   | 5  | 3 (2,2,1)         | other 3, batch 2  | 0 |

- Egress-only (hold) ELIMINATES the batch-not-consumed multi-frame stalls
  (21 -> 0; the single residual deferral is a 1-frame non-batch guard).
- BUT enemies are fire-eligible on **4168/6000 = 69%** of frames (waves overlap;
  previous-wave enemies keep manoeuvring in-band through most of the 150-frame
  gap), so the turret firing window is only ~31% of the time and a turret's
  100-frame cooldown almost never lands in it: **1 turret shot in 6000 frames**
  (vs 20 baseline). As literally specified the rule STARVES the turrets - it
  fails Task D question 2 ("still firing often enough to be useful?").
- TURRET_FIRE_TIMER while forbidden: the existing !fire code resets the timer to
  TURRET_FIRE_INTERVAL BEFORE any eligibility gate, so a forbidden turret's
  timer is reset every 100 frames on its own tick and never accumulates.
  Measured: max turret shots in the 8 frames after a window opens = 0 (hold) /
  1 (drain). No burst either way; hold is strictly better on stalls.

### Decision
Egress-only as specified is NOT shippable (turret firing collapses). Testing
looser variants that keep the wave idea but let turrets fire when the shared
pool is actually quiet (results pending):
  poolheadroom            hold turret fire iff ENEMY_BULLET_COUNT >= 2
  egress-or-poolheadroom  hold iff enemy-eligible AND ENEMY_BULLET_COUNT >= 2
  egress-or-poolany       hold iff enemy-eligible AND ENEMY_BULLET_COUNT >= 1
  poolany                 hold iff ENEMY_BULLET_COUNT >= 1

### Task B/D round 2 - looser pool-based variants (nomit 8f74e1b7, nofire, 6000f)

| rule (hold turret fire when...) | deferrals | stalls (lengths) | turret shots (baseline 20) |
|---|---|---|---|
| - (baseline)                       | 19 | 1 (19)          | 20 |
| ENEMY_BULLET_COUNT >= 2            | **3**  | 2 (2,1)     | **14** |
| enemy-eligible AND BULLET_COUNT>=2 | 49 | 7 (28,11,4,..)  | 12  (WORSE - fires when pool light mid-wave) |
| enemy-eligible AND BULLET_COUNT>=1 | 0  | 0               | 1   (starves) |
| ENEMY_BULLET_COUNT >= 1            | 7  | 2 (5,2)         | 2   (starves) |

Reference: SORTED_COUNT>=8 build (955708c0), nofire: 7 deferrals, stalls (4,2,1)
(turret-shot count not cleanly measured this round - build/main.vs had been
clobbered with the nomit symbol layout by a stray -vicesymbols; rebuilt, turret
symbols shift +7 bytes with the mitigation, main.asm symbols unaffected so all
deferral/bullet data stands).

### Conclusion (Task F)
- The wave-phase "egress-only" rule as specified is NOT SHIPPABLE: it removes the
  stalls but collapses turret firing to ~1 shot / 6000 frames, because enemies
  are fire-eligible 69% of the time (waves overlap) and a turret's 100-frame
  cooldown almost never coincides with a no-enemy-fire window. It fails Task F's
  "while retaining useful turret behaviour" condition, so per the task it is not
  implemented.
- The SORTED_COUNT>=8 mitigation is therefore NOT superseded and is kept
  (build 955708c0 unchanged).
- Data-supported alternative for a future decision: hold turret fire iff
  ENEMY_BULLET_COUNT >= 2 (a turret may be at most the 2nd of the 3 shared
  hostile bullets, never the last). 19 -> 3 deferrals, all short; 14/20 shots
  retained; needs no wave state, only the existing shared projectile count. This
  is a hostile-projectile-budget rule, not the requested wave-phase rule, so the
  swap is left to the user.
- TURRET_FIRE_TIMER while forbidden: unchanged - the existing !fire path resets
  it to TURRET_FIRE_INTERVAL before any eligibility gate, so a forbidden turret
  never accumulates a pending shot. Measured burst after a window opens: 0 (hold)
  / 1 (naive drain). No change needed.

### Source delta this round
- src/background_turrets.asm: the SORTED_COUNT mitigation is now wrapped in
  `#if !TURRET_FIRE_NO_MITIGATION ... #endif` - a build-time A/B switch only.
  Default build byte-identical (PRG SHA 955708c0). `-define TURRET_FIRE_NO_MITIGATION`
  produces the mitigation-free baseline (PRG SHA 8f74e1b7 == the Task-B-only build).
- No gameplay behaviour change. No permanent wave-phase rule added.

### Status: wave-phase turret-fire rule TESTED and REJECTED (turret starvation).
### SORTED_COUNT mitigation retained. No commits/pushes.
