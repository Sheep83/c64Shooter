# Level editor ↔ engine integration worklog

## Milestone: generated config/data integration (first end-to-end)

**Status: done, uncommitted.** HEAD `187a222`. Working tree carries this
integration plus the pre-existing `AGENTS.md` VICE-focus edit (user work,
untouched).

### Goal achieved

The engine now consumes level-editor–generated build inputs directly:

```
Python level editor  ->  V2 JSON project  ->  tools/level_editor exporter
  ->  src/generated/stage_config.asm  (constants only)
  ->  src/generated/stage_test.asm    (metatileDefs + stageMetatileRows)
  ->  KickAssembler  ->  VICE
```

Changing stage height / terrain palette / scroll divider / metatile map now
requires **only** editing+exporting the project. `main.asm` is never touched
between levels.

### Generated-file contract (permanent)

| file | kind | owns |
|---|---|---|
| `src/generated/stage_config.asm` | **constants-only** include (no bytes, no segment, no PC change). Imported in `main.asm` immediately after `#import "variables.asm"`. | `STAGE_METATILE_ROWS`, `SCROLL_FRAME_DIVIDER`, `TERRAIN_BACKGROUND_COLOUR`, `TERRAIN_MC_COLOUR_1`, `TERRAIN_MC_COLOUR_2`, `TERRAIN_CHARACTER_COLOUR`, `TERRAIN_COLOUR_RAM` (= `8 \| TERRAIN_CHARACTER_COLOUR`) |
| `src/generated/stage_test.asm` | bulk data. Imported once at `* = $6600` (unchanged assembly location). | `metatileDefs` / `METATILE_DEFS_END` (256 B), `stageMetatileRows` / `STAGE_METATILE_ROWS_END` (`N*10` B) |

Engine still owns the DERIVED `STAGE_LOGICAL_ROWS = STAGE_METATILE_ROWS *
METATILE_H`, all size/memory guards after the `#import`, the 16-bit widened
stage decoder, terrain glyph bitmap data (`terrainGlyphs`, `TERRAIN_GLYPH_COUNT`
in `main.asm` — deliberately NOT moved this milestone), and turret placement.

### Runtime palette mapping

`TERRAIN_BACKGROUND_COLOUR → $D021` (set in `initBackground`, restored to `0`
for the menu in `endGame`), `TERRAIN_MC_COLOUR_1 → $D022`, `TERRAIN_MC_COLOUR_2
→ $D023`, `TERRAIN_CHARACTER_COLOUR → colour-RAM low 3 bits`, colour-RAM bit 3
set → multicolour terrain. HUD row 0 stays hires (colour RAM 1) — the one-time
`$d800` fill uses `TERRAIN_COLOUR_RAM`, then `initFixedHud` overwrites row 0.

### Exporter contract amendment (`tools/level_editor/ka_export.py`)

`render_stage_config()` now emits the **named** `TERRAIN_CHARACTER_COLOUR` and
derives `TERRAIN_COLOUR_RAM = 8 | TERRAIN_CHARACTER_COLOUR` (was a hidden
`8 | <literal>`). Order: rows, divider, background, mc1, mc2, character, colour_ram.

### Editor loader (`tools/level_editor/engine_data.py`)

`load_engine_data()` now reads:
- stage height / palette / scroll divider / colour-RAM → `src/generated/stage_config.asm`
  (new `_parse_generated_config()`, validates `TERRAIN_COLOUR_RAM == 8 |
  TERRAIN_CHARACTER_COLOUR` and colour ranges; **no fallback to stale main.asm**).
- `metatileDefs` / `stageMetatileRows` → `src/generated/stage_test.asm`.
- `TERRAIN_GLYPH_COUNT` + `terrainGlyphs` → still `src/main.asm`.
- `EngineData` gains `source_colour_ram`.

### Acceptance level

`tools/level_editor/build_acceptance_level.py` deterministically (re)builds the
100-metatile-row inspection level: 25-row committed bas-relief map tiled ×4
(rows 0 and 99 all-M0 for a clean wrap seam; M14 MACH housings stay under
turret cols/rows 17/29/13 @ logical 13/29/57), palette `bg=0 mc1=11 mc2=14
character=1`, divider 2. Writes `tools/level_editor/projects/inspection-100.json`
(V2, deterministic) and exports the two generated files. Re-running is
byte-identical.

- `STAGE_METATILE_ROWS = 100` → `STAGE_LOGICAL_ROWS = 400`
- stage-map bytes = 1000, metatile-def bytes = 256
- assembled: `metatileDefs $6600–$66FF`, `stageMetatileRows $6700–$6AE7`,
  `STAGE_TEST_END = $6AE8` (guard `$8800` — ~6.9 KB headroom; editor max
  unchanged at 844 rows)

### `11/14` MC colours — proof the engine consumes generated config

Old engine test palette was `12/15`. The acceptance level uses `11/14`. VICE
capture reports `$D022 = 11`, `$D023 = 14`. A one-value swap
(`TERRAIN_MC_COLOUR_1` 11→5) via the editor only — `main.asm` md5 unchanged —
produced `$D022 = 5` in the running engine, then was restored.

### Follow-up (deliberately deferred)

- Terrain glyph ownership (`terrainGlyphs`, `TERRAIN_GLYPH_COUNT`) stays
  engine-owned. Glyph editing not built.
- Gameplay-object / turret export: V2 JSON `"objects": []` reserved; schema not
  defined. `turretCols` / turret world rows stay hand-authored in
  `background_turrets.asm`. `MACH` is art, not a magic turret tile.
- Multi-level selection/packaging: not started.

### Tooling touched for the 100-row stage

`check_fixed_hud_capture.py`, `check_turret_capture.py`, `check_scroll_edges.py`
now read `SCROLL_ROW` as 16-bit LE (`+ 256*SCROLL_ROW_HI` when present) — same
fix `check_scroll_capture.py` already had. `make_stage_fixture.py` /
`run_stage_fixture.sh` retarget `src/generated/` and restore from a byte copy
(not `git`). `editor.py` repo-root probe checks `src/generated/stage_test.asm`.

---

## Milestone: bottom-origin startup + editor turret placement

**Status: done, uncommitted.** HEAD `cfb78db`.

### Bottom-origin startup (engine)

The editor stores/exports rows top-to-bottom in visual order (unchanged). For
this upward-scrolling game the editor convention is now: **top of editor = far
end of stage; bottom of editor = beginning**. Gameplay boots at the authored
bottom and scrolls upward.

`renderStageRowToScreen` puts logical row `(SCROLL_ROW + BG_DEST_ROW - 1)` at
matrix row `BG_DEST_ROW` (1..23). For the aperture bottom (matrix row 23) to
show the authored last row `STAGE_LOGICAL_ROWS-1` at boot:

    SCROLL_ROW = STAGE_LOGICAL_ROWS - 23        (new .const STAGE_START_ROW)

`initBackground` now seeds `SCROLL_ROW` (16-bit) to `STAGE_START_ROW` before the
row loop, so the whole initial 23-row viewport is the contiguous bottom range
`[STAGE_LOGICAL_ROWS-23 .. STAGE_LOGICAL_ROWS-1]` - no wrap, no top-of-level rows
leak in. The existing coarse-scroll decrement then walks upward
(`SCROLL_ROW--`, wrap `0 -> STAGE_LOGICAL_ROWS-1`) through the whole authored
level; the loop-back seam now sits at the natural "reached the far end, loop to
the start" point. Guard: `STAGE_LOGICAL_ROWS >= 24`. Not a ring-buffer rewrite -
`renderStageRowToScreen` / `decodeStageCharacterRow` / `wrapBgLogicalRow` /
`prepareBackgroundCoarse` are unchanged; only the initial value changed.

### Turret placement is editor-owned

New generated file **`src/generated/stage_turrets.asm`** (constants + assembler
lists, no bytes/segment/PC). Imported in `main.asm` right after
`stage_config.asm`. Owns:

    .const TURRET_COUNT           (1..3 - private glyph namespace 226..239)
    .var   turretCols   List()    world CHARACTER columns
    .var   turretRows   List()    world CHARACTER / logical rows (full 16-bit height)

`background_turrets.asm` no longer defines `TURRET_COUNT` / `turretCols` /
`turretRows`; it keeps every guard that VALIDATES them and all turret BEHAVIOUR
(AI/cadence/HP/rendering/activation/collision/pulse/aim-at-fire) unchanged.
`main.asm` `updateTurretPressure` now uses `ldx #TURRET_COUNT - 1` (resolvable
because the import is early); the old `.if (TURRET_COUNT != 3)` guard is gone.

### JSON schema (V2 `objects`)

    "objects": [ { "type": "turret", "metatileRow": R, "metatileCol": C }, ... ]

- editor owns PLACEMENT only; behaviour/state/AI/sprites stay engine-owned.
- `metatileRow` 0..height-1, `metatileCol` 0..9 (metatile grid - the editor's
  paint granularity). Engine world coords: `row*4 + 1`, `col*4 + 1` (2x2 body
  centred in the 4x4 metatile - exactly where the previous hand-authored
  turrets sat: 17/29/13 == col*4+1, 13/29/57 == row*4+1).
- 1..3 turrets; distinct metatile rows (=> distinct, non-colliding world rows).
- backward compatible: V1/V2 files with absent/empty `objects` load fine
  (`validate_project` allows 0; `export_readiness_errors` requires >=1).
- `to_dict()` emits turrets in deterministic `(metatileRow, metatileCol)` order.

### Editor UI

Toolbar `Mode: Terrain | Turrets` radio. In turret mode: click a metatile to
place (or select an existing) turret; right-click / Ctrl-click / Delete key /
`Delete turret` button removes; markers (red box + 2x2 body footprint + "T",
white when selected) draw on the level canvas; place/delete are undoable
(`objects` are part of the undo state via a hashable key form). Impossible
placements are refused with a status message + bell. New projects seed one
turret near the start so they are export-ready. Export writes all three
generated files.

### Stage-wrap / turret-reset semantics (documented, unchanged)

Turrets are **per playthrough**. `initBackgroundTurrets` runs once at game
start; `positionBackgroundTurrets` recomputes VISIBLE every frame from
`rel = (turretWorldRow - SCROLL_ROW) mod STAGE_LOGICAL_ROWS`. A turret is
VISIBLE while `rel in [1,20]`, i.e. `SCROLL_ROW in [worldRow-20 .. worldRow-1]`.
When the stage loops (`SCROLL_ROW` wraps `0 -> STAGE_LOGICAL_ROWS-1`) a turret
becomes visible again, but its HEALTH / TURRET_DESTROYED / kill-score are NOT
reset - a destroyed turret stays destroyed (shows its cached underlay, cannot
fire, cannot be re-killed) for the whole game. There is deliberately no
per-loop turret respawn; adding one later is a small explicit hook
(loop counter -> re-run initBackgroundTurrets health seed).

### Acceptance level

`tools/level_editor/build_acceptance_level.py` (fixed: reads the tileset +
committed 100-row map from `HEAD:src/generated/stage_test.asm`) stamps a
recognisable FAR band (rows 1-5 = M13 GRILLE) and START band (rows 94-97 =
M1 R_FILL), M14 housings under 3 turrets, and writes the project +
3 generated files. Turrets:

| metatile (row,col) | world char row | when |
|---|---|---|
| (89, 4) | 357 | near the BEGINNING (activates first) |
| (70, 7) | 281 | ABOVE logical row 255 (16-bit world row) |
| (30, 3) | 121 | later in the playthrough |

Note: the committed generated `stage_config.asm` had drifted to
`TERRAIN_MC_COLOUR_2 = 10` / `Project: stage_test` while `inspection-100.json`
said `14` / `inspection-100`; regeneration makes the whole chain consistent at
the authored `11 / 14` (the prior milestone's acceptance palette).

### Capture-tooling change

Turret world rows are now 16-bit; `vice_scroll_test.py` additionally dumps
`turret-placements-hi.bin` (`turretWorldRowHi`), and `check_scroll_capture.py`
/ `check_turret_capture.py` / `check_fixed_hud_capture.py` reconstruct world
rows as `lo + 256*hi`. `run_stage_fixture.sh` backs up / writes a minimal
`stage_turrets.asm` for synthetic fixtures.
