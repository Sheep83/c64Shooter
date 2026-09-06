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
