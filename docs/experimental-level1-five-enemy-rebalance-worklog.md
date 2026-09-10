# Level 1 five-enemy rebalance — worklog

Branch `experimental-three-layer-player` @ `e94ccf5` (no commits). Continues the
three-layer player experiment; level content/data task.

## The drift that had to be fixed first
`src/generated/level1/*.asm` (what the game builds) had diverged badly from every
authored source:

| | levels/level1/level.json + build_levels.py | generated ASM (live) |
|---|---|---|
| metatile rows | 100 (400 logical) | **105 (420 logical)** |
| metatile defs | engine set | **34** |
| glyphs | engine set | **72** |
| palette | bg 0 / mc 11 / mc 14 | **bg 12 / mc 15 / mc 11** |
| turrets | 9 | **10** |
| wave triggers | 5 | **16** |

`build_level1()` reconstructed the level from hard-coded Python constants plus
the *git-committed* `stage_test.asm`. Running `build_levels.py` would silently
have replaced the live level with that stale reconstruction.

## Approach
1. `tools/level_editor/import_generated_level.py` (new) inverts `ka_export`
   exactly and recovers the LIVE level into `level.json`. Round-trip verified:
   re-export is byte-identical to the generated ASM.
2. `tools/level_editor/author_level1_five_enemy.py` (new) applies the rebalance
   at AUTHOR TIME with a fixed seed and bakes explicit triggers into the JSON.
3. `build_levels.py` `build_level1()` now just `load_project(level.json)`.

## Key measurement: 120 frames is not reachable from level data
* 1 logical row = 8 fine steps x SCROLL_FRAME_DIVIDER(2) = **16 frames**, so
  120 frames = 7.5 rows -> schedule alternates 8/7-row gaps, mean exactly 7.5
  rows = **exactly 120 frames** of authored trigger spacing.
* But measured wave STARTS are ~210-222 frames apart. Model, confirmed exactly
  against VICE for every interval:

      gap = (WAVE_ENEMY_COUNT - 1) * spawnInterval + WAVE_GAP
      interval 15/16/17/18 -> predicted 210/214/218/222 == observed

  `WAVE_GAP = 150` is an ENGINE constant (`src/main.asm:788`) and alone exceeds
  120, so **no level data can produce 120-frame wave starts**. Reported, not
  worked around; the one-line option is left for the user to decide.

## Engine file touched (and why)
53 triggers x 6 tables = 318 bytes of level data lived inline in the
background/HUD code block, which is capped at $5a00 by the terrain glyph block
(~211 bytes headroom) -> build error. The tables were moved to their own
`$7100` segment with PC save/restore, following the codebase's own documented
precedent for `terrainGlyphs` ($5a00) and the metatile stage tables ($6600):
a variable-length LEVEL block must not sit inside a code segment.

## Side effect worth knowing
Encounter fixtures `J_wave_start_deferred_then_starts` and
`L_pressure_clear_wave_eligible` — documented as pre-existing failures in the
previous two reports — now PASS. Cause identified: the fixture latches trigger 0
and asserts `WAVE_ENEMY_COUNT == 5`; Level 1's old trigger 0 was a SIX-enemy
wave. Verified both ways on otherwise-identical builds.
