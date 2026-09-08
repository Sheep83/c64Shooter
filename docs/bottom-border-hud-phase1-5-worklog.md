# Bottom-Border HUD — Phase 1.5 worklog

Task: replace the legacy RSEL=0 top-char-HUD presentation with a clean RSEL=1
gameplay geometry; open the lower border with only a late RSEL 1->0 dodge;
prove the lowest terrain row is *temporally* stable while scrolling; re-test the
deep-lower-border diagnostic sprite. Geometry/border proof only — NOT the HUD.

No commit, no push. VICE background/head-less only, no `open -a`, no focus steal.

## 0. Start state
- Branch `terrain-asset-workshop`, HEAD `1cd8513` ("First bottom border HUD
  experiment"), working tree **clean**.
- HEAD build sha256(build/shooter.prg) = `6272b25e1d342181ecfc085bf79283c5ec4811e936184d4ffc01f4b759730e46`
  (matches Phase-1 report "experiment ON").
- Toolchain: `java -jar /Users/brianmorrice/Dev/Tools/KickAssembler/KickAss.jar`,
  `/opt/homebrew/bin/x64sc` + `x64`, `/opt/homebrew/bin/c1541`. Build cmd:
  `java -jar .../KickAss.jar src/main.asm -odir build -o build/shooter.prg -vicesymbols`

## 1. Phase-1 changes present at HEAD (commit 1cd8513)
- `src/main.asm`: `#define BORDER_PROOF_ENABLE` toggle (line 10); guarded
  `BORDER_MARKER_SPRITE` (64B solid, `$1fc0`, ptr `$7f`).
- `src/raster_scheduler.asm`: guarded `RASTER_EVENT_BORDER`=3, `RASTER_BORDER_LINE`=240,
  `RASTER_BORDER_PENDING`, dispatch of the terminal border event, `borderOpenHook`
  (marker + RSEL 0->1 @ r243 + RSEL 1->0 @ r250 — the hybrid dodge).
- `tools/vice_border_phase1.py`, `tools/border_phase1_analyze.py` (new harnesses).

## 2. Architecture facts (source-verified)
- Permanent RSEL=0: `init` clears $D011 bit3 (`main.asm:423`). `rasterFrameReset`
  writes `$D011=$17` every physical frame (`raster_scheduler.asm:136`).
  `publishRasterPlan` writes `$17` once at game start.
- `rasterDisplayHook` (r56 event) does the HUD/terrain $D011 split:
  `$11`(r59) -> `$71`(r62 invalid BMM+ECM) -> `$70|fine`/`$77`(r63/64 invalid) ->
  `$10|fine`(r70/71 terrain). This is the *only* mid-frame $D011 machinery.
- `RASTER_DISPLAY_FINE` = presented YSCROL phase, set by `applyFineScroll` from
  `SCROLL_FINE` each frame. Currently only read by the hook.
- Matrix layout: row 0 = fixed char HUD (`initFixedHud`, `BG_SCREEN_A`), rows
  1..23 = terrain (scroller), row 24 = blank `#32` spacer (`initFixedHud`,
  `BG_SCREEN_A+24*40`). **Scroller writes rows 1..23 only** — `shiftBackgroundUpper`
  writes dst rows 2..12 (src 1..11), `shiftBackgroundLower` dst 14..23 (src 13..22),
  `prepareBackgroundCoarse` writes row 1, `save/restoreCrossingRow` rows 12/13.
  **Rows 0 and 24 are never touched by the scroller** — only `initFixedHud`.
- HUD presentation writers into row 0: `initFixedHud` (SCORE/FREE text + glyph
  copy + `displayScore`), `setupScoreDisplay` (`SCORE_SCREEN=$0400+29`),
  `setupLivesDisplay` (`LIVES_SCREEN=$0400+17`), `refreshScoreIfDirty->displayScore`
  (`HUD_SCORE_CELL=$0400+8`, per frame after a kill). `displayLives` already
  early-outs during PLAYING. `updateCycleDebug`/`displayCycleMinimum` not called.
- Score *bookkeeping* to KEEP: `SCORE_LO/HI`, `awardKillScore`, `SCORE_DIRTY`,
  `PLAYER_LIVES`.

## 3. Plan (minimal blast radius — keep 23 terrain rows, scroller untouched)
1. `init`: stop clearing RSEL -> `ora #%00011000` (RSEL=1, DEN=1), preserve rest.
2. `publishRasterPlan`: `$17` -> `$1b` (pre-first-frame; overwritten within 1 frame).
3. `rasterFrameReset`: `lda #$17` -> `lda RASTER_DISPLAY_FINE / ora #$18` (RSEL=1,
   DEN=1, YSCROL=presented fine) at raster ~1. Whole field now scrolls uniformly.
4. `rasterDisplayHook`: neuter to `lda #0 / sta RASTER_DISPLAY_PENDING / rts`.
   Delete `rasterHblankDelay` + page-cross guards + `RASTER_DISPLAY_NORMAL`.
   DISPLAY event becomes a documented ~10-cyc no-op at r56 (dispatcher plumbing
   left intact = no sprite-scheduler risk).
5. `borderOpenHook`: drop the RSEL 0->1 poll-to-243 write. Keep marker setup.
   Keep poll-to-~250 then RSEL 1->0 (`$D011 &= ~$08`). Measure exact raster/cycle.
6. `initFixedHud`: rewrite -> fill matrix row 0 AND row 24 with `#32` blank
   spacer; drop SCORE/FREE text, glyph copy, `displayScore` call.
7. `refreshScoreIfDirty`: body -> `lda #0 / sta SCORE_DIRTY / rts` (keep score
   value bookkeeping; stop writing screen). `displayScore` becomes dead — retain.
8. RSEL=1 restore next frame = step 3 (`rasterFrameReset` @ r~1, before line-51
   top compare).
- Diagnostic sprite: retained, still `BORDER_PROOF_ENABLE`-guarded.
- Terrain rows stay 1..23 (23 rows). Row 0 reclaim as a 24th needs a scroller
  row-range change -> out of scope, report as Phase-2 option.

## 4. Progress log
- [done] Recon, reports read, architecture mapped, worklog created.
- [done] Source edits 1-7 applied. Build clean (guards pass), code shrank.
- [done] **publishRasterPlan gotcha**: it is called every frame via
  `armFirstBatch` (main.asm:3515) at ~line 17, and its `$D011` seed write was
  clobbering the fine phase to a constant. Fixed: its write is now the SAME
  `RASTER_DISPLAY_FINE | $18` as rasterFrameReset (both pre-badline). Verified in
  VICE: fine scroll advances, terrain scrolls, rows 0/24 blank, border opens.
- [MEAS smoke] RSEL 1->0 write lands **line 250, cycle ~18-23**, `$D011` $1B->$13.
  rasterFrameReset RSEL restore **line 1, cycle ~9-22**, `$D011` -> `fine|$18`.
  Open lower border = clean $D021 rasters ~246-252 full width (no pop). Open
  TOP border present above ~raster 51 (single-FF consequence, expected).
- [OBS smoke] Diagnostic marker sprite in the deep lower border still renders
  wrong (grey/mixed, not solid white) from ~raster 254 down — Phase-1
  deep-border corruption appears to persist. Needs precise re-measure.
- [done] check_raster_capture (trusted oracle), 180 physical frames, ordinary
  play, border proof ON: `frame_cycle_deltas [19656]`, catchups 0, replay 0,
  service_failure 0, sprite_start_miss 0. PASS.
- [MEAS - BOTTOM EDGE POP CONFIRMED] Per-frame lowest-terrain-edge raster series
  (`scratchpad/edgeseries.py`) on the RSEL=1 build: the lowest terrain edge
  climbs **239 -> 246** across fine 0..7 then **snaps back to 239** at every
  fine 7->0 coarse step (~every 16 frames at divider 2), full screen width,
  exposing the blank spacer. A **7 px discontinuity every coarse transition.**
  This matches the user's manual VICE + MiSTer observation.
  A/B: clean RSEL=0 HEAD (BORDER_PROOF off, sha 2a605428) is **rock stable** at
  raster 246 every phase -- because RSEL=0's aperture bottom (246) sits *inside*
  the fetched-terrain stack (rows ~21..24 are below the crop), so terrain always
  fills to the crop. RSEL=1 extends the aperture past the true bottom of the
  25-row fetch, so the terrain's real bottom edge (row 23) becomes visible and
  its fine-scroll overflow (which has nowhere to go -- row 24 is reserved blank
  and the coarse copy discards row 23's outgoing content) is seen as the pop.
- [ANALYSIS] The pop is the documented "outgoing-row 7->0 bottom snap"
  (docs/scroll-edge-investigation.md) of the finite 25-row-fetch scroller. Row
  24 blank absorbs the *idle strip* and mode transition, NOT the outgoing-row
  *content* snap. With row 24 required blank + RSEL=1 + border open + no hybrid
  0->1 dodge, the visible aperture necessarily shows below the last terrain row,
  so the pop is unavoidable without a scroller change. => task decision **case C**
  for scroll stability; display-geometry conversion itself is otherwise GREEN.
- [done] `tools/check_scroll_edges_rsel1.py` (new) model-free temporal oracle +
  `tools/phase15_geometry_test.py` (new) capture harness with a NON-DESTRUCTIVE
  <=5-enemy runtime fixture (clamps the `waveTrigCount` RAM table only).
- [done] All cases (ordinary / wave5 / dense / lowy / contrast D021=7 / div1 /
  wave6): `check_raster_capture` = `frame_cycle_deltas [19656]`, service_failure
  0, sprite_start_miss 0. lowy synthetic (8xY=245) = 8 dispatcher catchups, 0
  misses, cadence exact (overdue-handling path, not a regression).
- [done] Temporal oracle: diffs ONLY at fine 7->0. Body (rasters ~64..231) =
  0 diffs. TOP seam (~56..63) and BOTTOM seam (~240..247) each snap 7 px at
  every coarse step, full width, on normal + wave5 + contrasting-yellow $D021.
  Fine phases 0..7 themselves: 0 diffs. Magnified consecutive-frame strips
  saved (`build/p15-*/phase15-evidence/`).
- [done] Diagnostic marker sprite: deep-lower-border garble PERSISTS under the
  corrected RSEL=1 history -- byte-identical x64sc AND x64, rasters ~254..273.
  Phase-1's "RSEL history" hypothesis disproven. Arm/skip/leak/collision
  behaviour unchanged from Phase-1.
- VERDICT: display-geometry conversion GREEN; scroll temporal stability RED
  (criterion 8, the 7->0 coarse-seam snap at both edges, previously masked by
  RSEL=0's edge crops); lower-border sprite-HUD feasibility RED. Overall AMBER,
  task decision **case C**.
- [done] Report written -> /reports/bottom-border-hud-phase1-5-display-geometry-report.md
- [pending] Build + VICE timing iteration (exact RSEL 1->0 raster/cycle).
- [pending] Temporal scroll-edge oracle for RSEL=1 (adapt check_scroll_edges).
- [pending] <=5-enemy test fixture (non-destructive).
- [pending] Test battery + diagnostic-sprite re-measure.
- [pending] Report -> /reports/bottom-border-hud-phase1-5-display-geometry-report.md
