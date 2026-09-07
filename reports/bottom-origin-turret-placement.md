# Bottom-origin stage startup + editor turret placement integration

PAL C64 shooter + level editor. HEAD `cfb78db` "Level editor integrated into
repo". **Not committed** - reviewable in the working tree.

Workflow now: **author terrain -> place turrets -> save/export -> build -> play
the authored level**, beginning at the authored bottom.

---

## 1. Summary of changes

### Part 1 - Bottom-origin startup (engine)

`initBackground` seeds the 16-bit `SCROLL_ROW` to `STAGE_LOGICAL_ROWS - 23`
(new `.const STAGE_START_ROW`) instead of `0`, **before** the loop that renders
the initial 23 terrain rows. Because `renderStageRowToScreen` places logical row
`(SCROLL_ROW + BG_DEST_ROW - 1)` at matrix row `BG_DEST_ROW` (1..23), matrix row
23 (aperture bottom) then shows the authored last row `STAGE_LOGICAL_ROWS-1`, and
the whole initial viewport is the **contiguous** range
`[STAGE_LOGICAL_ROWS-23 .. STAGE_LOGICAL_ROWS-1]` - no modulo wrap, no
top-of-level rows. The existing coarse-scroll decrement (`SCROLL_ROW--`, wrap
`0 -> STAGE_LOGICAL_ROWS-1`) then walks the viewport upward through the whole
authored level to logical row 0, and only then loops back to the bottom.

No ring-buffer / decoder / scroller rewrite: `renderStageRowToScreen`,
`decodeStageCharacterRow`, `wrapBgLogicalRow`, `prepareBackgroundCoarse`,
`shiftBackgroundUpper/Lower`, the crossing-row buffer - all unchanged. Only the
one initial value moved. Guard `STAGE_LOGICAL_ROWS >= 24` added.

### Parts 2-5 - Turret placement is editor-owned

- **JSON schema**: V2 `objects` now carries
  `{ "type": "turret", "metatileRow": R, "metatileCol": C }`. Editor owns
  PLACEMENT only.
- **Editor UI**: `Mode: Terrain | Turrets` toolbar radio. Turret mode: click a
  metatile to place / select; right-click, Ctrl-click, Delete key, or the
  `Delete turret` button removes; markers draw on the level canvas; place/delete
  are undoable; impossible placements are refused (status message + bell); new
  projects seed one turret so they are export-ready.
- **Export**: new generated file `src/generated/stage_turrets.asm` (constants +
  assembler lists only - no bytes/segment/PC). Emits the engine's existing
  representation directly: `.const TURRET_COUNT`, `.var turretCols`,
  `.var turretRows`. Deterministic `(metatileRow, metatileCol)` ordering.
- **Engine**: `background_turrets.asm` no longer defines those three symbols
  (imported from the generated file, early, in `main.asm`); it keeps every guard
  that validates them and 100% of turret behaviour. `updateTurretPressure` uses
  `ldx #TURRET_COUNT - 1` now that the value is resolvable; the old
  `.if (TURRET_COUNT != 3)` guard is replaced by a `1..3` range guard in
  `background_turrets.asm`.

### Coordinate model

`world char row = metatileRow*4 + 1`, `world char col = metatileCol*4 + 1` (the
2x2 body centred in the 4x4 metatile). This is exactly where the previous
hand-authored turrets sat (`17/29/13 == col*4+1`, `13/29/57 == row*4+1`). World
rows are full 16-bit - values above 255 are first-class (proven: 281, 357, and
synthetic 1024).

---

## 2. Files changed

| file | change |
|---|---|
| `src/main.asm` | `#import "generated/stage_turrets.asm"` (early); `STAGE_START_ROW` const + `>=24` guard; `initBackground` seeds `SCROLL_ROW = STAGE_START_ROW`; `updateTurretPressure` `ldx #TURRET_COUNT-1`; dropped the `TURRET_COUNT != 3` guard |
| `src/background_turrets.asm` | removed `.const TURRET_COUNT` + `.var turretCols/turretRows`; added `TURRET_COUNT` 1..3 guard; comment updates. **All behaviour code byte-identical.** |
| `src/generated/stage_turrets.asm` | **new** - generated turret placement |
| `src/generated/stage_config.asm` | regenerated: `Project` comment -> `inspection-100`; `TERRAIN_MC_COLOUR_2` `10 -> 14` (see note below). Scalar values otherwise unchanged. |
| `src/generated/stage_test.asm` | regenerated: recognisable FAR band (rows 1-5 = M13 GRILLE) + START band (rows 94-97 = M1 R_FILL) + 3 M14 turret housings; wrap-seam rows 0/99 all-M0 |
| `tools/level_editor/project.py` | `objects` turret schema + validation (`type`, in-range `metatileRow/Col`, <=3, distinct rows); `export_readiness_errors` (>=1 turret); `canonical_objects` (deterministic); `iter_turrets` / `turret_world_row/col` helpers; V1/V2 absent-`objects` backward compat |
| `tools/level_editor/ka_export.py` | `render_stage_turrets`; `export_project` returns 3 paths; uses `export_readiness_errors` |
| `tools/level_editor/engine_data.py` | `_parse_generated_turrets` (reads `stage_turrets.asm` -> metatile-grid objects); `EngineData.source_turrets` |
| `tools/level_editor/editor.py` | turret mode UI, markers, place/select/delete, undo integration, mode-aware status, seeded default turret, 3-file export dialog |
| `tools/level_editor/build_acceptance_level.py` | fixed (reads `HEAD:src/generated/stage_test.asm`); stamps marker bands + 3 turrets; writes project + 3 generated files |
| `tools/vice_scroll_test.py` | also dumps `turret-placements-hi.bin` (`turretWorldRowHi`) |
| `tools/check_scroll_capture.py`, `tools/check_turret_capture.py`, `tools/check_fixed_hud_capture.py` | reconstruct 16-bit turret world rows (`lo + 256*hi`) |
| `tools/run_stage_fixture.sh` | back up / write a minimal `stage_turrets.asm` for synthetic fixtures |
| `tools/vice_bottom_origin_probe.py` | **new** - automated bottom-origin + turret-placement regression probe |
| `tools/level_editor/test_turret_integration.py` | **new** - headless turret schema / export / persistence tests |
| `docs/level-editor-worklog.md` | milestone appended |

`src/raster_scheduler.asm`, HUD code, collision plumbing, general object pool,
sprite multiplexer, render-plan architecture: **untouched**.

---

## 3. Final editor JSON object schema

```jsonc
{
  "formatVersion": 2,
  // ...
  "objects": [
    { "type": "turret", "metatileRow": 30, "metatileCol": 3 },
    { "type": "turret", "metatileRow": 70, "metatileCol": 7 },
    { "type": "turret", "metatileRow": 89, "metatileCol": 4 }
  ]
}
```

- `type` (string): `"turret"` is the only supported type this iteration; the
  list-of-typed-dicts shape accommodates more object types later without a
  schema break.
- `metatileRow` (int, `0 .. height-1`): metatile-grid row. World / logical
  CHARACTER row = `metatileRow*4 + 1` (16-bit; >255 supported).
- `metatileCol` (int, `0 .. 9`): metatile-grid column. World CHARACTER column =
  `metatileCol*4 + 1`; the body occupies cols `[c, c+1]`.
- Constraints: `1 .. 3` turrets (private glyph namespace 226..239); distinct
  `metatileRow` per turret (=> distinct, non-colliding 2-row bodies).
- Deterministic on save: turrets emitted in `(metatileRow, metatileCol)` order
  with a fixed key order.
- Backward compatible: files with absent or empty `objects` load
  (`validate_project` passes; `export_readiness_errors` flags the missing
  turret only at export time).

---

## 4. Final generated ASM turret contract

`src/generated/stage_turrets.asm` (constants + assembler lists; **no bytes, no
segment, no PC change**; `#import`ed in `main.asm` right after
`stage_config.asm`):

```asm
.const TURRET_COUNT = 3
.var turretCols = List().add(13, 29, 17)   // world CHARACTER columns
.var turretRows = List().add(121, 281, 357) // world CHARACTER / logical rows (16-bit)
```

`background_turrets.asm` consumes these exactly as it previously consumed its
own hand-authored `.var` lists: `turretWorldCol` / `turretWorldRow(+Hi)` /
`turretWorldXLo/Hi` / `turretWorldRow2(+Hi)` are `.fill`ed from
`turretCols.get(i)` / `turretRows.get(i)`, and every existing placement guard
(count match, col 0..38, row `< STAGE_LOGICAL_ROWS`, distinct world rows,
glyph-namespace bounds) still runs against them. Turret BEHAVIOUR
(`initBackgroundTurrets`, `positionBackgroundTurrets`, `installTurretRow`,
`updateBackgroundTurrets`, `pulseTurretColour`, `traceTurretCannon`,
`hitCannonTarget`, `aimBackgroundTurret`, all `TURRET_*` state) is unchanged.

**Placement is editor-owned; behaviour is engine-owned.**

---

## 5. Corrected initial-viewport calculation

`renderStageRowToScreen`:

```
BG_LOGICAL_ROW = wrapBgLogicalRow( SCROLL_ROW(16) + BG_DEST_ROW - 1 )   // BG_DEST_ROW 1..23
```

so matrix row `d` shows logical row `(SCROLL_ROW + d - 1) mod STAGE_LOGICAL_ROWS`.

- Old: `SCROLL_ROW = 0` at boot -> matrix rows 1..23 show logical rows `0..22`
  (the **top** of the editor). The authored bottom only appeared after one full
  wrap.
- New: `SCROLL_ROW = STAGE_LOGICAL_ROWS - 23` at boot. Solving
  `SCROLL_ROW + 22 = STAGE_LOGICAL_ROWS - 1` (aperture bottom = authored last
  row). Matrix rows 1..23 then show logical rows
  `[STAGE_LOGICAL_ROWS-23 .. STAGE_LOGICAL_ROWS-1]`. Since `BG_DEST_ROW <= 23`
  and `SCROLL_ROW + 22 = STAGE_LOGICAL_ROWS - 1 < STAGE_LOGICAL_ROWS`, the sum
  never reaches `STAGE_LOGICAL_ROWS` -> `wrapBgLogicalRow` never subtracts ->
  **no wrap, no top-of-level row in the initial viewport**.

`initBackground` runs the same `renderStageRowToScreen` for all 23 initial rows
that the scroller uses later, so the initial screen and the scrolled-in rows are
one representation. `initBackgroundTurrets` (which runs before the row loop) uses
`turretWorldRow` directly and is unaffected by the `SCROLL_ROW` value. Verified
on the running engine: boot `SCROLL_ROW == 377` (`= 400 - 23`), and screen RAM
rows 1..23 equal a plain tile expansion of logical rows `377..399` (turret body
cells excepted), with **no GRILLE (M13, top-band) glyph anywhere on the initial
screen**.

The widened 16-bit stage addressing is used throughout; no 8-bit row assumption
was reintroduced.

---

## 6. Stage-wrap / turret-reset semantics

Chosen behaviour (documented, deliberate; existing behaviour preserved, not
redesigned):

- Turrets are **per playthrough**. `initBackgroundTurrets` seeds
  `TURRET_HEALTH = TURRET_START_HEALTH` once at game start.
- `positionBackgroundTurrets` recomputes `TURRET_VISIBLE` every frame from
  `rel = (turretWorldRow - SCROLL_ROW) mod STAGE_LOGICAL_ROWS`; a turret is
  VISIBLE while `rel in [1, 20]`, i.e. `SCROLL_ROW in [worldRow-20 ..
  worldRow-1]`. This is idempotent - no allocation, no per-frame spawn.
- When the stage loops (`SCROLL_ROW` wraps `0 -> STAGE_LOGICAL_ROWS-1`) a turret
  re-enters its visible window, but **HEALTH / TURRET_DESTROYED / kill score are
  NOT reset**. A destroyed turret stays destroyed for the whole game: it renders
  its cached terrain underlay (style 7), `pulseTurretColour` skips it,
  `updateBackgroundTurrets` holds it at DEAD style, `traceTurretCannon` /
  `hitCannonTarget` ignore it (`HEALTH == 0`). No duplication, no re-spawn, no
  state corruption.
- There is deliberately **no per-loop turret respawn**. If a future design wants
  "each lap re-arms the turrets", that is one explicit hook (loop counter ->
  re-run the `initBackgroundTurrets` health seed), not an accidental side
  effect.

Verified on the running engine (`vice_bottom_origin_probe.py` section D): a
turret killed at game start stays `HEALTH == 0` through a full
`0 <-> STAGE_LOGICAL_ROWS-1` sweep of `SCROLL_ROW`, and `TURRET_DESTROYED` does
not change.

---

## 7. Tests performed

### Headless (`tools/level_editor/test_turret_integration.py`) - 8/8 pass

coordinate model; widened vertical coordinate (world rows to 2801, >255);
JSON persistence save/reload exact + byte-deterministic; ASM export
deterministic + authoring-order-independent; V1/V2 absent-`objects` backward
compat; impossible-placement rejection (dup row / >MAX / bad type / out of
range); `engine_data` reads generated placement (3 turrets, world rows
`[121, 281, 357]`, has >255); `export_project` writes exactly the 3 engine
files.

### Emulator - `tools/vice_bottom_origin_probe.py` - A/B/C/D pass

- **A** boot `SCROLL_ROW == 377 == 400 - 23` (bottom origin).
- **B** initial 23 rows == contiguous logical `377..399` - no wrap, no
  top-of-level rows.
- **C** turret VISIBLE windows vs `SCROLL_ROW`:
  `t0@row121:[101..120]`, `t1@row281:[261..280]`, `t2@row357:[337..356]`;
  activation order (first -> last) `[2, 1, 0]` = higher world row (nearer the
  authored bottom) activates first; `>255` world rows (281, 357) handled.
- **D** killed near-bottom turret stays dead across a full stage loop;
  `TURRET_DESTROYED` stable; no duplication / re-init.

### Emulator - capture suites (acceptance level, divider 2)

| capture | frames | result |
|---|---|---|
| `check_scroll_capture` (boot) | 1000 | 0 failures, `frame_cycle_deltas [19656]`, deferred 0, `stage_logical_rows 400`, ~48.6M pixel checks |
| `check_scroll_capture` (`--seed-scroll 270`) | 1600 | 0 failures, `stage_step_errors []` (crosses logical row 255/256 boundary), 86M pixel checks |
| `check_scroll_capture` (`--seed-scroll 14`) | 800 | 0 failures, `stage_loops 1` (full `0 -> 399` wrap), `stage_step_errors []` |
| `check_fixed_hud_capture` | 1000 | 0 failures; `$D021/$D022/$D023 = 0 / 11 / 14`; `char_mcm true`; terrain cRAM 9; HUD row 0 hires |
| `check_turret_capture` | 1000 | 0 failures, deferrals 0 |
| `check_raster_capture` | 1000 | `service_failure_count 0`, `sprite_start_miss_count 0`, `frame_cycle_deltas [19656]` |

### Emulator - unchanged-behaviour regression

| suite | result |
|---|---|
| `vice_suppress_fixtures.py` A..J | 10/10 pass |
| `vice_encounter_fixtures.py` A..R | 18/18 pass |
| `run_stage_fixture.sh` 25 / 64 / 256 / 400 (widened 16-bit stage decode) | all pass |
| `vice_turret_large_row.py` (synthetic turrets at world rows 255 / 260 / 1024) | pass - position/visibility, glyph install, colour pulse + restore, hit/destroy above 255 |
| `check_stage_addressing.py` (host model) | pass |

### Determinism

`build_acceptance_level.py` run twice -> `stage_config.asm`, `stage_test.asm`,
`stage_turrets.asm`, `inspection-100.json` all byte-identical
(`12c91f06`, `cb69132f`, `7dd2cb5a`, `5d4d1cbf`). KickAssembler build clean each
time.

---

## 8. Diagnostic / runtime results

- **Frame cadence**: exactly `[19656]` on every capture.
- **Raster service failures**: 0. **Sprite-start misses**: 0.
- **Coarse-scroll deferrals**: 0 in the boot capture; `check_scroll_capture`
  `deferred 0`. Presentation suppression not exercised.
- **Palette from generated config**: `$D021 = 0`, `$D022 = 11`, `$D023 = 14`,
  terrain colour RAM `9` - all from `stage_config.asm`.
- **Scroll divider**: `SCROLL_FRAME_DIVIDER = 2` from generated config; behaves
  as the divider-2 baseline (0 deferrals, exact cadence).
- **Assembled stage data**: `metatileDefs $6600`, `stageMetatileRows $6700`,
  `STAGE_TEST_END $6AE8` (< `$8800` guard, ~6.9 KB headroom).
  `turretWorldRow $8CC5`, `turretWorldRowHi $8CCE`.
- **Memory map segments** unchanged: `$6000-$634f`, `$6600-$6ae7`,
  `$8800-$8edf`. `stage_turrets.asm` adds 0 bytes.
- **Human-test build**: `build/shooter.prg` SHA256
  `75fabcaf2d10d243cd45c98eca3e1b31be7b5989d988974dad2118f2323d4b92`;
  `build/shooter.d64` SHA256
  `077b586de187bd9514f12d6467b7289fd7b9850682b5927eafe873e75653a4e5`.
  Boots at the authored bottom (R_FILL start band on screen), scrolls upward
  through the level, reaches the GRILLE far band and the wrap seam; three
  turrets activate near-bottom -> mid (>row 255) -> later.

---

## 9. Remaining limitations / recommended next steps

- **1..3 turrets required** by the engine (private glyph namespace 226..239). A
  level with 0 turrets is structurally valid in the editor but not
  export-ready; supporting 0 needs a `.if (TURRET_COUNT > 0)` guard around ~5
  turret loops - deferred.
- **Per-loop turret respawn** is not implemented (documented as intentional).
  Add a loop counter -> health-seed hook if desired.
- **`build_acceptance_level.py`** reads `HEAD:src/generated/stage_test.asm` for
  the tileset + base map; after this work is committed it reads the committed
  (stamped) version - idempotent, but a plain in-repo path would be cleaner.
- The committed `src/generated/stage_config.asm` had drifted
  (`TERRAIN_MC_COLOUR_2 = 10`, `Project: stage_test`) from
  `inspection-100.json` (`14`, `inspection-100`); this regeneration makes the
  whole chain consistent at the authored `11 / 14`. A committed `.json`/`.asm`
  consistency check in CI would prevent recurrence.
- Terrain glyph ownership, multi-object schema, multi-level packaging: still
  deferred per the prior milestone.

---

## 10. YES/NO acceptance

| criterion | result |
|---|---|
| an authored level begins at its bottom | **YES** (`SCROLL_ROW = STAGE_LOGICAL_ROWS - 23` at boot; probe A) |
| initial screen population is correct (no top rows leak in) | **YES** (probe B; 0 pixel/matrix failures) |
| editor can visually place / select / remove turrets | **YES** (turret mode, markers, click/right-click/Delete/button) |
| turret placements survive save / load | **YES** (headless test 3; exact + deterministic) |
| turret placements export deterministically | **YES** (headless test 4; order-independent; md5-stable) |
| engine consumes generated placements | **YES** (`#import "generated/stage_turrets.asm"`; probe C/D; captures) |
| hand-maintained level turret positions no longer required | **YES** (removed from `background_turrets.asm`) |
| turret placement works across the full stage height (>255) | **YES** (world rows 281 & 357 shipped; 1024 synthetic; probe C, `vice_turret_large_row`) |
| existing turret runtime behaviour preserved | **YES** (behaviour code byte-identical; `check_turret_capture` + fixtures pass) |
| stable raster / multiplexer / renderer behaviour preserved | **YES** (0 raster-service failures, 0 sprite-start misses, cadence `[19656]`; those files untouched) |
| no unrelated architectural rewrite | **YES** (init value + placement data source only) |
| bg-gfx hitch not reintroduced | **YES** (`deferred 0`, exact cadence, 0 scroll failures) |
| full-stage wrap still correct | **YES** (`stage_loops 1`, `stage_step_errors []`) |
| logical-row 255 boundary still correct | **YES** (`--seed-scroll 270`, `stage_step_errors []`) |
| palette still from generated config; divider 2 correct | **YES** (`0/11/14`, cRAM 9; divider-2 baseline) |
| existing engine/editor tests pass | **YES** (suppress 10/10, encounter 18/18, widen 25/64/256/400, host oracle, headless 8/8) |

---

## Source control

Nothing committed or pushed. Working tree: 16 modified files + 3 new
(`src/generated/stage_turrets.asm`, `tools/vice_bottom_origin_probe.py`,
`tools/level_editor/test_turret_integration.py`). HEAD remains `cfb78db`.
