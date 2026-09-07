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

---

## Milestone: pre-merge level-authoring pass — viewport overlay, streaming
## turret pool, authored wave triggers, two level packages

**Status: done, uncommitted.** See `reports/pre-merge-level-authoring-pass.md`
for the full report. Summary of the permanent contracts introduced here:

### Generated-file layout is now per-level

`src/generated/<level>/` holds **five** includes:

| file | kind | owns |
|---|---|---|
| `stage_config.asm` | consts | `STAGE_METATILE_ROWS`, `SCROLL_FRAME_DIVIDER`, `TERRAIN_*` palette, `TERRAIN_COLOUR_RAM`, **`TERRAIN_GLYPH_COUNT`** (moved here from `main.asm`) |
| `stage_charset.asm` | consts+data | **NEW** — `terrainGlyphs` / `terrainGlyphsEnd` byte block + size guard. The swappable tileset unit. Imported at the old inline-block PC in the `$2920` segment. |
| `stage_test.asm` | data | `metatileDefs` (from the level's tileset) + `stageMetatileRows` |
| `stage_turrets.asm` | consts+lists | **`TURRET_TOTAL`** (was `TURRET_COUNT`; 0..255) + `turretCols`/`turretRows` **sorted descending by world row** |
| `stage_waves.asm` | consts+lists | **NEW** — `WAVE_TRIGGER_COUNT` + resolved `waveTrigger*` lists (rows desc) |

`main.asm` imports the `level1/` set only. `level2/` is generated + committed but
never `#import`-ed. The flat `src/generated/stage_*.asm` files are removed.

### Char-memory ownership (unchanged addresses, clarified ownership)

| codes | region | owner |
|---|---|---|
| 0–127 | ROM copy | permanent |
| 128–159 | HUD/UI private (128–145 used, 146–159 reserved) | permanent engine/UI |
| **160–223** | terrain glyph namespace, `$3D00–$3EFF`, 64 slots | **level-owned** — `TERRAIN_GLYPH_COUNT` authored (multiple of 8); bytes come from `stage_charset.asm` |
| 224–225 | diagnostic rail/diagonal, `$3F00` | permanent |
| 226–229 | ONE shared turret body glyph set (all live turrets) | engine runtime |
| 230–239 | free | — |
| 240–251 | starfield | permanent |
| 252–255 | free | — |

Future multiload: DMA/copy the next level's `terrainGlyphs` blob (always 64
slots) into `$3D00` and patch `TERRAIN_GLYPH_COUNT` during the load transition.
No format change required; not implemented this pass.

### Streaming turret pool + shared body glyphs (`src/background_turrets.asm`)

Authored count `TURRET_TOTAL` is unbounded (0..255, 8-bit stream cursor).
`updateTurretStream` (frame loop, before `positionBackgroundTurrets`) admits an
authored turret into a free pool slot once `SCROLL_ROW <= authRow + MARGIN`
(cursor walks the desc-sorted list, never skipping) and evicts it once its `rel`
leaves the visible window + margin. `turretDestroyedBits` (one bit per authored
turret, never cleared) keeps a killed turret dead across evict/re-admit and stage
loops; `TURRET_STREAM_CURSOR` rewinds to 0 on each stage wrap.

**Concurrent visible capacity is NOT limited by glyph codes.** Every live turret
shares ONE 4-code body glyph set (codes 226–229, `turretArt` style 4), published
once. The hit flash is colour-RAM only (`TURRET_HIT_CRAM`); a destroyed turret
writes the 4 decoded terrain screen codes it covered (`turretGroundCodes`) back
into its cells - from `publishTurretGlyphs`, at frame start, a safe window - then
it is plain terrain. The only bound is `TURRET_POOL = 8` per-slot *state* slots
(15 one-byte arrays × 8 ≤ 128, the signed-X clear loop), which exceeds the ~7
turrets a 23-row aperture can hold and the 5 that can be combat-visible; a full
pool just defers the next admit a frame. **No editor viewport-density
rejection** - `turret_screen_peak` is an informational hint only.

### Authored wave triggers (`src/main.asm`)

A stage with `WAVE_TRIGGER_COUNT > 0` drives encounter timing from world-row
triggers: a trigger fires the instant its row reaches the **top edge of the
terrain aperture** (`SCROLL_ROW == worldRow`, checked in `updateWaveTriggers`).
`worldRow` is a world position, so `SCROLL_FRAME_DIVIDER` cannot move it relative
to terrain. `startAuthoredWave` reuses `startRandomWave`'s body but takes the
attack id from the trigger and the wave size / sprite seed / interval from the
resolved trigger (composition size is authoritative — `NORMAL_WAVE_SIZE` is not
forced). The CIA-random `startRandomWave` selection is compiled out of
`updateSpawner`'s `!startNext` and `startGame`'s boot call for such a stage;
everything else (per-member spawn loop, ingress/manoeuvre/egress, turret-pressure
gate) is reused unchanged. The cursor rewinds on stage wrap, so authored triggers
deliberately **re-fire once per stage loop**; a single `WAVE_TRIGGER_FIRE` latch
+ forward-only, never-skip cursor rules out duplicate firing within a loop.

### Editor

`levels/<name>/level.json` is a `formatVersion: 3` self-contained package (map +
palette + turrets + embedded `tileset` + `waveDefinitions` + `waveTriggers`).
V1/V2 files still load (tileset migrated from the engine baseline). New modes:
`Waves` (place/move/assign/delete world-row triggers, edit reusable wave
definitions against the engine attack catalogue); an editor-only, never-saved
`Gameplay view` overlay (40×23 logical rows, bottom-origin, clamped, non-wrapping;
its top edge is the wave activation line). `Open Level…` / `New Level…` switch
packages and reset **all** editor state.

### Tests

New headless: `test_turret_unlimited.py`, `test_wave_schema.py`,
`test_viewport_model.py`, `test_level_packages.py`;
`test_turret_integration.py` updated for `TURRET_TOTAL` + desc sort + tileset.
New VICE: `vice_wave_trigger_probe.py`, `vice_level1_smoke.py`;
`vice_bottom_origin_probe.py` rewritten for the pool. `check_fixed_hud_capture.py`
/ `check_turret_capture.py` / `vice_scroll_test.py` / `run_stage_fixture.sh` /
`make_stage_fixture.py` updated for the pool + `level1/` layout.

---

## Milestone: Terrain Asset Workshop + 64-metatile per-level capacity

**Status: done, uncommitted.** Full report:
`reports/terrain-asset-workshop-report.md`. See also
`docs/terrain-asset-workshop-worklog.md`.

### Live per-level metatile capacity: 16 -> 64

`STAGE_METATILE_COUNT` is a new level-owned `.const` in the generated
`stage_config.asm` (1..64, the level's real metatile count - no padding, no
magic 16). The engine derives `.const METATILE_DEF_COUNT = STAGE_METATILE_COUNT`
(`src/main.asm`); the old `.if (METATILE_DEF_COUNT > 16)` guard is replaced with
a `1..64` range check. The metatile-definition table is variable length
(`STAGE_METATILE_COUNT * 16` bytes).

### Engine metatile-definition lookup is 16-bit

`decodeStageCharacterRow` previously formed the `metatileDefs` offset as an
8-bit `id*16 + subrowOffset` (correct only for id 0..15). It now reads the
row's 10 IDs into a `BG_ROW_IDS` scratch buffer once, then per column builds a
16-bit pointer `TEXT_SRC = metatileDefs + (id<<4) + BG_TILE_ROW_OFS` and copies
4 bytes via `lda (TEXT_SRC),y`. Legal NMOS 6502 only; the row/scroll/wrap logic
is unchanged. `BG_ROW_IDS` lives in the `$2920` segment next to
`BG_INCOMING_ROW` (the `$2000` engine-state block is full). Cost:
`decodeStageCharacterRow` ~1050 -> 1697 cycles; PAL frame cadence, raster
servicing and sprite starts are unaffected (measured).

### Stage-row maximum recalculated: 844 -> 768

From the real assembled layout: `metatileDefs + stageMetatileRows` occupy
`$6600..$8800` (`$2200` = 8704 bytes); a full 64-entry def table is 1024 bytes,
leaving `(8704 - 1024) / 10 = 768` whole rows. `ENGINE_MAX_STAGE_ROWS = 768`
(`tools/level_editor/engine_data.py`), used by `project.MAX_STAGE_ROWS` and the
editor spinboxes. The engine's own `.if (STAGE_TEST_END > $8800) .error` is
label-based and stays exact (a 16-metatile level could still reach 844; the
editor deliberately uses the uniform 64-metatile worst case). One row beyond
768 with a 64-def table fails assembly with
`"Metatile stage data collides with the background turret segment ($8800)"`.

### Terrain Asset Repository (editor-side, reusable across projects)

`tools/level_editor/terrain_repository/repository.json` - one deterministic,
schema-versioned (v1) JSON document (`sort_keys`, sorted assets, **no
timestamps** so re-saving an unchanged repo is a no-op diff). Each asset:
stable `asset_NNNN` id, display name, native 16x32 logical-multicolour grid
(values 0..3), provenance (`sourcePack`, `sourceTileIndex`, `sourceCoords`,
`sourceTileSize`, `licenceNote`, optional `localSourcePath`), free-form notes
and tags. Assets store **logical pixels only** - never a live char code.
`TerrainRepository.snapshot(id)` returns a standalone deep copy for embedding
into a level, so a later repository edit or delete can never make a level fail
to build. Module: `tools/level_editor/terrain_repository.py`.

### Native 16x32 multicolour representation + glyph packing / dedup

`tools/level_editor/native_metatile.py`. A metatile is 16 logical multicolour
pixels across x 32 rows; char cell (cr,cc) covers native rows `cr*8..cr*8+7`,
cols `cc*4..cc*4+3`, and its 8 bytes pack each row's 4 pixels as
`(p0<<6)|(p1<<4)|(p2<<2)|p3` - exactly what the engine/VIC consume.
`pixels_to_glyphs` / `glyphs_to_pixels` round-trip losslessly.
`pack_metatiles` deduplicates: identical 8-byte glyphs share one code, repeats
within and across metatiles reuse IDs, glyph order is first-seen and
deterministic, and the glyph list is padded to a multiple of 8 (engine copy
constraint). `GlyphBudgetExceeded` is raised - never a silent alias or drop -
when a level's metatiles need more than the 64-slot terrain glyph namespace.
The editor shows `Metatiles: N / 64   Terrain glyphs: U / 64` and, in the
Workshop, `this metatile: 16 cells, R existing reused, X new unique required`.

### Spritesheet import + colour conversion

`tools/level_editor/spritesheet.py` - `slice_sheet(path, tile_w=32, tile_h=32)`;
configurable tile size; incomplete edge cells are **warned, never cropped**
into short tiles; Pillow for PNG decode only.
`tools/level_editor/terrain_convert.py` - deterministic nearest-colour
conversion of a source tile to the native 16x32 grid, against the FOUR colours
the current project palette uses (the one editor C64 table, moved to
`engine_data.C64_PALETTE_RGB` / `_HEX`). Horizontal pair-reduction policy: a
32-wide source row's columns `2x, 2x+1` are RGB-averaged into native pixel `x`;
a non-32 source is nearest-resampled to 32x32 first. The conversion is a
starting point only - manual editing in the Workshop is authoritative.

### Terrain Asset Workshop (editor UI)

`tools/level_editor/workshop_ui.py` (Tkinter, no new framework).
`NativeMetatileEditor` is a zoomed 16x32 paint canvas with 4 project-palette
swatches (rendered in the current palette but storing logical 0..3), click and
drag paint, visible 4x4-char boundary guides, undo/redo and a live glyph-cost
readout. `WorkshopDialog` shows an optional source-image preview beside the
native editor and can Save to the level metatile set and/or Save to the
repository (with provenance). `ImportDialog` picks a PNG, sets the tile size,
browses cached thumbnails and opens one tile in the Workshop. In `editor.py`
the metatile palette now iterates the level metatile set (up to 64, scrollable)
with per-entry names; buttons: Workshop / New / Import PNG / From repo / Rename
/ Trim unused. "Trim unused" only drops **trailing** unused metatiles - IDs are
never silently renumbered (that would corrupt painted maps); a metatile below a
still-used higher ID must be repainted first.

### Project format: V4

`formatVersion 4` adds `levelMetatileSet` - up to 64 entries, each
`{name, native:{width:16,height:32,pixels:[[0..3]*16]*32], source: null | {repositoryAssetId, provenance}}`.
It is the authored source of truth; `tileset` (packed glyphs + defs) is a
derived cache, regenerated by `repack_tileset_from_metatile_set` whenever a
native metatile is edited or a repository asset is added. V1/V2/V3 files load
unchanged: the packed `tileset` is kept byte-for-byte and a native
`levelMetatileSet` is *derived* from it (names default to the historical
`METATILE_NAMES`), so a migrated level renders and exports exactly as before
until a metatile is edited. `SUPPORTED_FORMAT_VERSIONS = (1, 2, 3, 4)`;
`project_from_dict` migration is deterministic (save -> reload -> save is
byte-identical). `MACH` stays a terrain metatile, not a gameplay object.

### Generated engine ownership (unchanged boundary)

Char codes 160..223 remain the permanent 64-slot terrain glyph namespace,
already level-owned via generated `stage_charset.asm` (from the prior pass).
This task adds editor-authored terrain but does **not** move any ownership:
`stage_charset.asm` still carries only `terrainGlyphs` (codes 160..), and the
HUD (128..159), diagnostic (224/225), shared turret body (226..229) and
starfield (240..251) glyphs are untouched. Export path enforces the 64-glyph
budget before generating any bytes.

### Deterministic export

`ka_export.render_stage_config` emits `.const STAGE_METATILE_COUNT`;
`render_stage_asm` emits up to 64 metatile defs. `build_levels.py` re-emits
both `level1/` and `level2/` (level.json migrated to V4); the two generated
dirs stay independent and gameplay imports only `level1/`. The editor never
patches `main.asm`.

### Tests

New headless (`tools/level_editor/`): `test_native_metatile.py`,
`test_terrain_repository.py`, `test_colour_conversion.py`,
`test_spritesheet.py`, `test_metatile_capacity.py`,
`test_editor_workshop_gui.py`; end-to-end `acceptance_terrain_workshop.py`
(import -> convert -> edit -> save to repo -> snapshot into one level -> prove
the other level's tileset is independent -> export both). New host arithmetic
`tools/check_metatile_def_lookup.py`. New VICE `tools/vice_metatile64_smoke.py`
(64-def stage boots/scrolls/wraps, live decode of a map row containing id 63).
`make_stage_fixture.py` / `run_stage_fixture.sh` gained a `[D]` def-count arg;
`vice_stage_widen_probe.py` reads the def table by its real byte span and its
call trampoline moved to `$6400` (a 768-row fixture map now fills to `$8800`).
Committed fixture: `tools/level_editor/testdata/synthetic_tileset.png`.

### Current limitations

- The editor deliberately caps stage height at 768 rows for every level (the
  64-metatile worst case), even though a small-metatile level could assemble
  taller.
- Repacking on a native edit may re-order / shrink a hand-authored glyph set
  (identical bitmaps collapse). The render is visually identical; the exported
  `terrainGlyphs` bytes may differ from a pre-edit export.
- `check_scroll_capture --stress` shows 4 transient pixel hiccups at one raster
  line during one coarse transition (matches the pre-existing artefact in
  `docs/encounter-budget-worklog.md`); the plain capture is clean.

### Future object-layer boundary (unchanged)

Terrain metatiles stay terrain. Gameplay objects (turrets today) remain a
separate authored layer. No object-placement, boss-editor, wave-authoring-beyond-
triggers, runtime charset streaming or bank-switching work is in scope here.

---

## Milestone: Terrain Asset Workshop - final usability + memory-safety pass

**Status: done, uncommitted.** Full report:
`reports/terrain-workshop-final-usability-pass.md`. Five bounded amendments; no
system redesign.

### Memory-layout fix: terrain glyph block relocated to $5c00

`#import "generated/level1/stage_charset.asm"` (the `terrainGlyphs` byte block,
`TERRAIN_GLYPH_COUNT * 8` bytes, 384 at 48 glyphs, **512 at the full 64-glyph
budget**) used to sit INSIDE the `$2920` background-control code segment. Its
size displaced every routine after it, so a valid full-budget level pushed
`BACKGROUND_CONTROL_END` past `HEALTH_SPRITE_BASE` ($3000):
`Error: Background control code overlaps health sprite RAM`.

It is now `* = $5c00` in its own fixed segment (like the metatile stage tables
at `$6600`) - the previously-empty `$56xx..$5fff` window before
`raster_scheduler` at `$6000`. `initBackground` copies it to `$3D00` by absolute
addressing, so bank/placement below `$A000` is unconstrained. New guards:
`.if (* > $5c00)` on the background/HUD code, `.if ($5c00 +
TERRAIN_GLYPH_NAMESPACE*8 > $6000)` (worst-case reservation), and
`.if (TERRAIN_CHARSET_END > $6000)`. The `$2920` segment now ends at `$2e51`
(was `$2fd1`): ~430 bytes clear of `$3000` instead of 47. The only remaining
`TERRAIN_GLYPH_COUNT` dependency in that segment is the `initBackground` copy
unroll (<= 8 steps), and the existing `BACKGROUND_CONTROL_END` guard proves the
worst case still clears the boundary.

### Editor: persistent PNG import session

The `ImportDialog` is now kept alive (hidden between uses) as an editor-runtime
import session: source PNG path, decoded+sliced sheet, tile geometry and last
selected cell. A `WorkshopDialog` opened from a picked tile has a
**"Back to Source"** button that re-shows the same dialog without
reopening/re-reading the file. Choosing a different PNG replaces the session in
place. Never persisted to level/project files.

### Editor: native tile Mirror H / Flip V

`NativeMetatileEditor` gains **Mirror Horizontal** and **Flip Vertical**,
operating on the 16x32 logical-pixel artwork before glyph decomposition (the
source PNG, glyph IDs and packed bytes are untouched). Each is exactly one
undoable edit; mirror-twice / flip-twice are identities; no rotation.

### Editor: VIC-II 2:1 aspect-ratio display

`NativeMetatileEditor` renders each logical multicolour pixel `2*unit` wide by
`unit` tall, so a 16x32 logical metatile appears as a 32x32 physical square
instead of a squashed strip. Stored data stays 16x32 logical / values 0..3 /
serialisation unchanged. Painting, hit-testing and 4x4 guides map mouse
coordinates back to the 16x32 cells (`zx`/`zy` split, no duplicated pixels).

### Editor: individual repository rename / delete

The repository picker is now a small manager: **Add snapshot to level**,
**Rename...** (artwork/id unchanged; empty rejected, duplicate display names
confirmed), **Delete** (explicit confirmation). Repository assets and level
metatiles stay separate snapshot concepts: rename/delete never touch metatiles
already copied into any level package. Changes persist to `repository.json`
immediately (no destructive "Clear Repository").

### Generated Level 1 re-synced (pre-existing inconsistency)

Commit `3a72c13` committed `src/generated/level1/*.asm` inconsistent with the
authored `tools/level_editor/levels/level1/level.json`
(`STAGE_METATILE_COUNT = 17` vs the level's 16; `WAVE_TRIGGER_COUNT = 0` vs 5).
The generated files were re-exported straight from the committed `level.json`
via `load_project` + `export_level` (not `build_levels.py`, whose `build_level1`
reconstructs from a hard-coded Python spec + the stale `stage_test.asm` and so
could not break the loop). `level.json` was not modified. `test_metatile_capacity.py`
(which hard-asserted a 16-def engine baseline) and `make_stage_fixture.py` /
`vice_bottom_origin_probe.py` (which hard-read a 256-byte / 16-def metatile
table) were made count-agnostic.

### Tests

New: `tools/check_terrain_glyph_budget.py` (assembles a full 64-glyph level,
asserts every reserved-region guard). `test_editor_workshop_gui.py` extended to
9 checks (2:1 aspect + hit-test, mirror/flip idempotence + undo, persistent
import session, repository rename/delete vs level snapshots). Full editor suite
+ VICE battery (raster/scroll/HUD/turret/wave-trigger/bottom-origin/level1
smoke) green; PAL cadence exactly `[19656]`; the known `--stress`
scroll-capture pixel hiccup at y=55 is unchanged in character.

---

## Milestone: terrain glyph capacity 64 -> 128, unused-metatile delete, native tiles

**Status: done, uncommitted.** Full report:
`reports/terrain-authoring-blockers-and-native-tiles-report.md`.

### Charset audit + terrain glyph capacity 64 -> 128

Audited every screen code stamped into the `$0400` matrix in any game state.
Menu / gameplay / GAME OVER / hi-score text uses only codes 1..26 (letters),
32 (space) and 48..57 (digits) - the highest is **54** ('6'). Codes **55..127**
of the resident ROM copy are never displayed anywhere; nor are 146..159
(old reserved HUD band), 230..239, 252..255.

New charset map (`$3800`, 256 codes):

| codes | region |
|---|---|
| 1..54 (57 resident) | ROM text glyphs - menu / GAME OVER / hi-score |
| 64..81 | **HUD private glyphs** (`HUD_GLYPH_BASE` 128 -> **64**) - dead ROM space |
| 82..95 | reserved (HUD expansion) |
| **96..223** | **terrain glyph namespace** (`TERRAIN_GLYPH_BASE` 160 -> **96**, `TERRAIN_GLYPH_NAMESPACE` 64 -> **128**), bitmaps **`$3B00..$3EFF`** = exactly half the charset |
| 224..225 | diagnostic rail/diagonal |
| 226..229 | shared turret body glyphs |
| 240..251 | starfield |

Only the HUD private block moved (into never-displayed ROM space); the terrain
namespace grew *downward* to code 96 and *up to* 223 (unchanged ceiling).
Diagnostic / turret / starfield are untouched. `HUD_GLYPH_BASE_CODE`,
`TERRAIN_GLYPH_BASE_CODE`, `TERRAIN_GLYPH_NAMESPACE_CODE` are exported for the
capture oracles (no literals). Two hard-coded HUD `.byte` rows now use the
constants.

`initBackground`'s terrain glyph copy is now a **fixed-size runtime loop**
(count only in the page/tail terminators), so the `$2920` timing segment length
no longer depends on the glyph count at all. The terrain glyph data segment
moved `$5c00 -> $5a00`; at the 128-glyph worst case it fills `$5a00..$5e00`,
512 bytes clear of `raster_scheduler` at `$6000`, and `BACKGROUND_CONTROL_END`
is `$2e56` - 426 bytes below `HEALTH_SPRITE_BASE $3000`. Guards updated for the
1024-byte block; `check_terrain_glyph_budget.py` now assembles a full 128-glyph
level and asserts every reserved-region boundary.

### Project format 5

`FORMAT_VERSION = 5`, `SUPPORTED = (1..5)`. A tileset saved by formatVersion <= 4
stored metatile-def glyph codes at base 160; `_migrate_tileset` shifts them to
`TERRAIN_GLYPH_BASE` (96) on load. Native `levelMetatileSet` pixels are
base-independent (no change). `load_engine_data` also auto-detects a stale
generated tree's base and remaps. `engine_data.TERRAIN_GLYPH_BASE_LEGACY = 160`.

### Unused-metatile deletion fixed

**Root cause:** `_metatile_remove_unused` only ever considered *trailing*
metatiles and refused every deletion the moment the *highest* metatile ID was
still painted - it had no notion of deleting a chosen unused metatile with
renumbering. **Fix:** `project.remove_metatile(project, index)` - refuses if the
map references `index`, else drops the set entry, shifts later entries down one,
and decrements every map cell whose ID was `> index` (cells `< index`
unchanged), keeping the painted stage identical. Turrets store grid positions
and wave triggers store world rows - never scenery metatile IDs - so they are
deliberately untouched. Editor: a per-selection **"Delete"** button plus a
"Trim unused" batch built on the same primitive. `MetatileInUseError`.
`test_metatile_delete.py` covers end / middle / just-below-highest-used
removal, refusal of a used tile, turret/wave immunity, and
save/reload/export determinism.

### Generated native bas-relief terrain (`native_terrain_tiles.py`)

31 original metallic-industrial-panel metatiles authored directly in the native
16x32 logical-multicolour format from ~40 reusable 4x8 cells (plate, edge
light/shadow, bevels TL/TR/BL/BR, recess corners, H/V seams, ribs, vent,
grille, H/V conduit + elbow, rivet, diagonal brace, hazard chevron, pit walls,
glowing core). Lighting convention: `0` void, `1` mid body, `2` shadow
(bevels facing away / seams / recess), `3` highlight (bevels facing the
top-left light / rivet gleam / conduit crown). No external PNG / conversion
step. **31 metatiles -> 36 unique terrain glyphs after dedupe (naive would be
496 - ~14x denser)** - proving purpose-designed native art is far more
charset-efficient than imported 32x32 pixel art. `--sheet` prints an ASCII
contact sheet (no image deps).

`install_level1_terrain.py` swaps Level 1's metatile set for the 31 native
tiles (the old 16 `METATILE_NAMES` "riveted hull" tiles were the pre-workshop
test baseline), remaps the painted test map old-id -> new-id so the scroller
stays structured, lays a 3-row demo patch (rows 2-4, previously blank, no
turrets/triggers nearby) showing all 31 tiles side by side, and re-exports.
**Turrets (9), wave definitions/triggers (5), palette, height, scroll divider
unchanged.** Level 1 now: 31 metatiles, 40 packed terrain glyphs (of 128).
Level 2 artwork unchanged (its codes re-based 160 -> 96 on export only).

### Tests / VICE

New: `test_metatile_delete.py` (7), `test_native_terrain_tiles.py` (8);
`check_terrain_glyph_budget.py` rewritten for 128; `check_fixed_hud_capture.py`
parameterised on the exported base labels. 94 editor checks green. VICE on the
new Level 1: raster `[19656]` / 0 service failures / 0 sprite-start misses,
scroll 0 failures / 64.8M pixel checks / 74 wraps, HUD 0, turret 0, wave-trigger
/ bottom-origin / level1 smoke all PASS; `run_stage_fixture 768 64` decodes ID
63 byte-exact, `769 64` rejected. The known `--stress` y=55 pixel hiccup
persists unchanged in character.
