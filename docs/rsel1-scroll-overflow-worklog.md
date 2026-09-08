# RSEL=1 coarse-scroll edge-pop experiment — worklog

Branch `experimental-border-hud`, from HEAD `d547c80` ("Establish RSEL1 border
HUD experimental baseline"). No commit, no push. VICE background/head-less only.

## Goal
Make the RSEL=1 scroller temporally continuous at BOTH visible edges through the
fine 7->0 coarse transition, by maintaining valid neighbour terrain in the
matrix edge rows (0 and 24) instead of keeping them permanently blank.

## Experiment A — mechanism (row-state trace, scratchpad/rowtrace.py)
Confirmed the fine 0..7 -> coarse cycle for the BLANK-spacer baseline:
- fine 0..7: matrix rows stable. Row 0 = `$20` blank, rows 1..23 = terrain
  (world SCROLL_ROW .. SCROLL_ROW+22), row 24 = `$20` blank.
- coarse upper phase (prepareBackgroundCoarse, ~raster 160-272): saveCrossingRow
  (row 12) -> shiftBackgroundUpper (dst 2..12 <- src 1..11) -> SCROLL_ROW-- ->
  render new row 1. Rows 13..24 untouched. SCROLL_FINE:=0.
- coarse lower phase (finishBackgroundCoarse, frame start): shiftBackgroundLower
  (dst 14..23 <- src 13..22) -> restoreCrossingRow (saved row 12 -> row 13).
- => TOP pop: the incoming row (world SCROLL_ROW-1 after the decrement) is not
  pre-staged; it appears as a fresh matrix row 1 at the coarse step = a 7 px
  jump. BOTTOM pop: the outgoing row (world old-SCROLL_ROW+22) is DISCARDED by
  shiftBackgroundLower (row 24 never written) instead of moving into row 24 = a
  7 px jump. All 25 rows are already fetched by the VIC (blank rows are
  fetched-but-empty); no badline/fetch constraint blocks filling them.

Hypothesis: **CORRECT** -- blank rows 0/24 are the cause.

## Experiment B/C — overflow-row implementation (src/main.asm only)
Row model kept as `W(r) = SCROLL_ROW + r - 1` for r = 0..24 (unchanged formula,
extended range): row 0 = incoming overflow (SCROLL_ROW-1), rows 1..23 = body,
row 24 = outgoing overflow (SCROLL_ROW+23).

| Change | Detail |
| --- | --- |
| `shiftBackgroundUpper` | `.for row = 12..2` -> `12..1` (also shift row 0 -> row 1). +40 B / +320 cyc. |
| `shiftBackgroundLower` | `.for row = 23..14` -> `24..14` (also shift row 23 -> row 24). +40 B / +320 cyc. |
| `prepareBackgroundCoarse` | render the fresh row into `BG_DEST_ROW = 0` (was 1). |
| `wrapBgLogicalRow` | leading `bpl` underflow branch: fold `-1` ($FFFF) up by one STAGE_LOGICAL_ROWS. Pre-existing callers (>=0) unaffected. |
| `initBackground` row loop | `ldx #1 .. cpx #24` -> `ldx #0 .. cpx #25` (render all 25 rows). |
| `initFixedHud` | emptied -> `rts`. Rows 0/24 are no longer blank spacers; colour RAM for row 0 is left at the stage-global `TERRAIN_COLOUR_RAM` from initBackground (was overwritten to 1). |
| `GAMEPLAY_RSEL` const (main.asm) + `GAMEPLAY_D011_BASE` | toggle the gameplay $D011 RSEL bit (0/1); wired into `init`, `publishRasterPlan`, `rasterFrameReset`. |

Crossing row (12->13) and beam-race split unchanged. Invariant
`W(r) = SCROLL_ROW + r - 1` verified steady through the coarse transaction and
the stage wrap.

## Result

| config | body (rows 1..23) 7->0 | top overflow edge (r 52-55) | bottom overflow edge (r 247-250) |
| --- | --- | --- | --- |
| BLANK spacers (baseline d547c80), RSEL=1 | **7 px pop** (r 60-63 + 240-247) | pop | pop |
| overflow rows, **RSEL=1** | **0 diffs** (r 56-246 flawless) | ~4 px residual | ~4 px residual |
| overflow rows, **RSEL=0** (GAMEPLAY_RSEL=0) | **0 diffs** | **0** (cropped at r 55) | **0** (cropped at r 246) |

Key: RSEL=1's aperture (51..250) does not crop the overflow rows' OWN outer
edges (no row -1 / row 25 to feed them). RSEL=0's border FF crops exactly those
edges at raster 55 / 246, so **RSEL=0 + overflow rows = both edges fully clean**.
RSEL does NOT gate the 25-row DMA (DEN + YSCROL do), so RSEL=0 fetches the same
25 rows.

Temporal proof (tools/check_scroll_edges_rsel1.py, model-free, turret cols
excluded): RSEL=0+overflow = `body_temporal_diffs 0`, `lastrow_temporal_diffs 0`,
`coarse_edge_median_jump [0,1]` across ordinary / wave5 / contrast($D021=7) /
dense / low-Y AND a 320-frame run through the SCROLL_ROW 0->420 stage wrap
(19 coarse transitions).

Cadence/scheduler (canonical `vice_scroll_test.py --physical --trace` +
`check_raster_capture.py`): RSEL=0+overflow = `frame_cycle_deltas [19656]`,
service_failure 0, sprite_start_miss 0, on ordinary + seeded-wave + wrap runs.
(NB: `phase15_geometry_test.py`'s own `check_raster_capture` numbers are an
unreliable trace-parse artifact -- use `vice_scroll_test.py` for that oracle.)

Colour RAM: uniform `TERRAIN_COLOUR_RAM` ($F9 => colour 9) across rows 0/1/12/24
at runtime -- no colour-row scroll, no 8 px colour flash.

## Decision
Ship **`GAMEPLAY_RSEL = 0`** (RSEL=0 + overflow rows): GREEN, both edges clean,
~24 visible terrain rows, [19656], scheduler clean, no invalid VIC mode, legacy
top HUD + BMM+ECM separator stay removed. The `GAMEPLAY_RSEL = 1` variant is
retained (toggle) and is AMBER (body clean, ~4 px edge residuals).

## Cost
+80 bytes shift code / measured ~+1000 cyc on the coarse-upper phase
(`bgUpperReady` ~271 -> **288**; `bgUpperCopied` 233 unchanged; `bgLowerReady`
median 20 unchanged). `$4000` segment `$4000-$56ab` -> `$4000-$5879` (+462 B,
~391 B headroom to `$5a00`). Cadence `[19656]` exact, 0 service failures / 0
sprite-start misses on the trusted `vice_scroll_test.py --physical --trace` +
`check_raster_capture.py` oracle (ordinary / seeded-wave / stage-wrap).

## Status: COMPLETE. GREEN.
Report: /reports/rsel1-scroll-overflow-rows-experiment-report.md
Final build: GAMEPLAY_RSEL = 0, sha256(prg) b8fdfe495a797d31, sha256(d64) 17ae896c770e3b1b.
Battery: ordinary / wave5 / contrast($D021=7) / dense / low-Y / divider-1 (24
coarse steps) / stage wrap (SCROLL_ROW 0->420, 19 coarse steps) -- all
body_temporal_diffs 0, edge diffs 0, coarse_edge_median_jump [0,1].
