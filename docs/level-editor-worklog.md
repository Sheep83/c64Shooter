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
