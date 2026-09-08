# Full-gameplay-aperture reconciliation — worklog

Branch `experimental-border-hud`, from working tree = the uncommitted overflow-row
experiment on HEAD `d547c80`. No commit, no push.

Goal: reconcile the visual terrain aperture with the sprite/gameplay aperture
after the overflow-row fix. Manual playtest found (1) a top band where terrain
shows but sprites don't render, (2) the bottom still feels cropped.

## Part A — Y-boundary audit (all source gates)

| Gate (main.asm) | Rule | Historical reason | Still valid? | New rule |
| --- | --- | --- | --- | --- |
| `GAMEPLAY_SPRITE_MIN_Y` (was `71`) | full-bitmap floor; below it `snapshotSpritePointer`/`buildClippedInitialSprite` blank the top `MIN_Y - Y` rows | old fixed HUD row 0 (r55-62) + BMM+ECM separator (r63-70); "no sprite DMA in the HUD transition" | **NO** — HUD + separator gone (Phase 1.5), `rasterDisplayHook` is a no-op | `51 + 4*(1-GAMEPLAY_RSEL)` = **55** (RSEL=0 aperture top) |
| `GAMEPLAY_SPRITE_CLIP_MIN_Y` = `MIN_Y - 20` (was `51`) | objects below it are dropped (no VIC slot), `buildSortedObjectList` | coupled to MIN_Y (clip pool blanks <=20 rows) | follows MIN_Y | **35** |
| `buildSortedObjectList` (`cmp #CLIP_MIN` / `cmp #END_Y`) | keep `CLIP_MIN <= Y < 246` | as above | follows the two consts | 35..246 |
| `snapshotSpritePointer` / `buildClippedInitialSprite` (`cmp #MIN_Y`, `d = MIN_Y - Y`) | top-clip Y in `CLIP_MIN..MIN_Y-1` | HUD | follows MIN_Y | belt-and-braces now (the RSEL=0 border FF also masks the sprite top above r55) |
| player move-up clamp (`cmp #GAMEPLAY_SPRITE_MIN_Y`, main.asm ~1681) | player Y >= MIN_Y | "same viewport as every rendered object" | follows MIN_Y -> **55** | player can now fly up to r55 |
| player move-down clamp (`cmp #230`, main.asm ~1700) | player Y <= 230 | bottom margin (magic number) | ship at Y=230 clips 4 px into the r246 crop; kept -- see Part D | (unchanged; documented) |
| hitscan target eligibility (`cmp #MIN_Y`, ~1806) | enemy Y >= MIN_Y to be hittable | "off-screen ingress not a target" | follows MIN_Y -> 55 | enemies in the top band are now hittable |
| enemy-fire eligibility (`cmp #MIN_Y` .. `cmp #190`, ~2156) | shooter Y in `MIN_Y..190` | HUD floor + readability ceiling | floor follows MIN_Y -> 55; 190 ceiling unchanged | |
| `checkCapturedPlayerCollision` (`cmp #MIN_Y` / `cmp #END_Y`, ~3563) | confirm only `MIN_Y <= Y < 246` | "culled ingress cannot cause an invisible software collision" | follows MIN_Y -> 55; top-band enemies are now visible so collisions there are fair | |
| `buildBatchSpriteSchedule` (`cmp #12`, ~3004) | batched obj needs `Y >= 12` (compute `Y-12` IRQ compare) | real "compare raster can't be < 0" limit | **YES** (not a HUD gate) | unchanged; irrelevant -- topmost sprites are always the initial-8, never batched |
| `PLAYER_START_Y = 220`, `PLAYER_RESPAWN` uses it | fine | | yes | unchanged |
| `GAMEPLAY_SPRITE_END_Y = 246` | enemy cull / player collision ceiling | RSEL=0 aperture bottom | **YES** -- still the clean crop (Part D) | unchanged |

One coherent knob: `GAMEPLAY_SPRITE_MIN_Y`, now derived from the RSEL aperture.
Everything else keys off it. Only `#230` (player down) and `#190` (fire ceiling)
remain independent magic numbers -- both bottom-side, both left as-is (documented).

## Part B — sprite-Y sweep (tools/sprite_y_sweep.py, new)

Baseline (MIN_Y=71): objects Y 51..70 get a hw slot + `$D015` bit + true
`SPR_Y`, **but the bitmap's top `71-Y` rows are blanked** -> nothing draws above
raster ~71. Objects Y<51 dropped. => the "top dead zone" = **rasters ~55..71**
(visible terrain, sprite bitmaps forcibly blanked, collisions not confirmed).

After (MIN_Y=55): full bitmap for Y>=55; clip pool only for Y 35..54 (and those
are border-masked anyway); collision confirmed Y>=55. `player_top_test.png`
visibly shows the player ship rendering at Y=55/64/72 in the old dead band.
`build/p15-wave5` real combat: an authored enemy at Y=51 renders as a clean
sprite at the aperture top (`wave5_top.png`).

Topmost sprites are ALWAYS the initial-8 (Y-sorted ascending, first 8 -> initial
snapshot written by `renderSprites` at frame top ~raster 10). Batched sprites
(9-16) are always the LOWER-on-screen ones; earliest measured
`rasterAssignmentApplied` = raster 127 (dense). => MIN_Y=55 adds zero mux
scheduling pressure; the topmost sprite is unscheduled by construction.

## Part C — change

`main.asm`: `GAMEPLAY_SPRITE_MIN_Y = 51 + 4*(1 - GAMEPLAY_RSEL)` (55 for the
shipped RSEL=0). `GAMEPLAY_SPRITE_CLIP_MIN_Y` follows to 35. Stale comments on
`snapshotSpritePointer` / `buildClippedInitialSprite` updated. No other code
change -- every gate already keyed off `GAMEPLAY_SPRITE_MIN_Y`.

## Part D — bottom real-estate

RSEL=0 aperture = raster 55..246 (192 px). The overflow-row report already
proved: extending past 246 (globally RSEL=1, or the asymmetric candidate below)
re-exposes the overflow row-24's OWN uncroppable bottom edge -> a temporal pop.

Tested here: `GAMEPLAY_BOTTOM_EXTEND = 1` -> `borderOpenHook` does RSEL 0->1 @
r242 (miss the RSEL=0 close @247) then RSEL 1->0 @ r252 (after the RSEL=1 close
@251 has SET the FF) -> aperture 55..250, top crop unchanged. Temporal oracle at
aperture 55..250: **`lastrow` diffs at raster 247 on EVERY fine step** (4160
px/step, not just 7->0). => the +4 px band is not temporally clean.

**Conclusion: raster 246 is the clean maximum for this single-matrix 25-row
scroller.** Shipped `GAMEPLAY_BOTTOM_EXTEND = 0`. `#230` player-down clamp left
as-is (ship at Y=230 clips 4 px into the r246 crop -- standard bottom-hug;
lowering it wastes mobility, raising it clips more). Cosmetic option noted in the
report: set `$D020` = `TERRAIN_BACKGROUND_COLOUR` so the crop border blends
instead of a hard black line.

## Timing / regression (trusted `vice_scroll_test.py --physical --trace` + check_raster_capture)

| run | frames | frame_cycle_deltas | service_failure | sprite_start_miss |
| --- | --- | --- | --- | --- |
| ordinary | 240 | `[19656]` | 0 | 0 |
| dense (16) | 200 | `[19656]` | 0 | 0 (catchups 1393 = pre-existing --dense synthetic stress) |
| stage wrap (SCROLL_ROW 0) | 320 | `[19656]` | 0 | 0 |

Scroll-edge oracle (RSEL=0, turret cols excluded): ordinary / wave5 / contrast
($D021=7) / div1 (22 coarse) all `body 0 / lastrow 0 / coarse_edge_median_jump
[0,1]` -- the overflow-row fix is NOT regressed by MIN_Y=55.

## Status: GREEN (top dead zone) + AMBER (bottom = proven max). Report:
/reports/border-hud-full-gameplay-aperture-report.md
Final build: GAMEPLAY_RSEL=0, GAMEPLAY_BOTTOM_EXTEND=0, sha256(prg) b67c89917025.
