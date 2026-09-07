# Terrain Asset Workshop + 64‑Metatile Per‑Level Capacity — worklog

Task: raise live per‑level metatile capacity 16 → 64; widen the engine
metatile‑definition lookup to a 16‑bit offset; recalculate the safe stage‑row
maximum from the real assembled layout; add an editor‑side reusable Terrain
Asset Repository + native C64 multicolour metatile Workshop + PNG spritesheet
importer + glyph deduplication + level metatile‑set management; keep export
deterministic and per‑level; migrate existing terrain unchanged.

Branch: `terrain-asset-workshop`  ·  starting HEAD: `9838b16`
("ignorefile updated, leagcy files deleted"), working tree clean at task start.

---

## 1. Current state established by inspection (authoritative over stale prompt assumptions)

### Git / integration
- Phase‑1 ("Pre‑Merge Level Authoring Pass") is **committed** — `8d0b0a8`
  (turrets + wave director + editor) and `9838b16` (ignore/cleanup). Tree clean.
- Streaming turret pool with **one shared 4‑code body glyph set** (codes
  226–229), colour‑RAM hit flash, `TURRET_POOL = 8`, `turretGroundCodes`,
  `restoreDeadTurretCells` — all present in `src/background_turrets.asm`. The old
  "4 private glyph codes per turret / 3‑visible cap" design is **gone**. Do not
  reintroduce it.
- `src/generated/` now holds `level1/` and `level2/` only (5 files each,
  both committed). The flat `src/generated/stage_*.asm` files are removed.
  `main.asm` `#import`s `generated/level1/*` only; `level2/` is generated,
  committed, never imported.
- **The game currently assembles cleanly** (`cd src && java -jar
  …/KickAss.jar main.asm -odir ../build -o ../build/shooter.prg -vicesymbols`).
  Assembled map: `metatileDefs+stageMetatileRows` occupy `$6600–$6AE7`
  (`STAGE_TEST_END = $6AE8`); next used region is `background_turrets.asm` at
  `$8800`.

### Pre‑existing inconsistency to resolve (not a blocker)
`tools/level_editor/levels/level1/level.json` (source of truth: 9 turrets,
5 wave triggers, palette mc2=14/char=1) does **not** match the committed
`src/generated/level1/{stage_config,stage_turrets,stage_waves}.asm` (built from
an earlier 2‑turret / 2‑trigger state, palette mc2=8/char=7).
`python3 tools/level_editor/build_levels.py` regenerates them to match the JSON
and the game still assembles. This is a stale build art(not user authoring) and
will be re‑synced when Phase‑2 regenerates all level packages under the new
schema. Flagged here so a resuming session does not mistake the regen diff for
its own change. (Inspection ran `build_levels.py` once and immediately
`git checkout --` the 3 files to restore the committed state.)

### Engine metatile decode — the widen point
`decodeStageCharacterRow` (`src/main.asm:5213`). Per stage row it builds a 16‑bit
pointer `TEXT_SRC = stageMetatileRows + rowBase` and walks 10 columns. For each
column (`src/main.asm:5284`–`5314`):

```
ldy BG_COL
lda (TEXT_SRC),y        ; metatile ID
asl asl asl asl         ; id*16  <-- 8-bit, WRAPS for id >= 16   <<< truncation point
clc / adc BG_TILE_ROW_OFS
sta BG_DEF_BASE          ; 8-bit metatileDefs offset
ldy BG_DEF_BASE
.for s in 0..3 { lda metatileDefs,y ; sta BG_INCOMING_ROW,x ; iny/inx }
```

`BG_TILE_ROW_OFS = (logicalRow & 3) * 4` (0..12). For id 0..63 the offset
`id*16 + ofs` ranges 0..1020 → needs a 16‑bit address into `metatileDefs`.

### Metatile / capacity constants
- `src/main.asm:159‑162`: `METATILE_W=4`, `METATILE_H=4`, `METATILES_PER_ROW=10`,
  **`METATILE_DEF_COUNT = 16`** (the "16" to raise).
- `src/main.asm:172‑173`: guard `.if (METATILE_DEF_COUNT > 16) .error "…id*16 no
  longer fits an 8‑bit metatileDefs offset"` — removed by the 16‑bit rewrite.
- `src/main.asm:6115‑6116`: `.if (METATILE_DEFS_END - metatileDefs !=
  METATILE_DEF_COUNT * METATILE_W * METATILE_H) .error` — keep, now with the
  derived count.
- `src/main.asm:6122`/`6125`: `.if (STAGE_TEST_END > $8800) .error` and
  `> $a000`. **These are label‑based and already exact for any table size** —
  they do not need a magic row constant.
- No `METATILE_DEF_COUNT` / metatile‑count constant is currently emitted by the
  exporter; the engine hard‑codes 16.

### Memory recalculation (from the real assembled layout, not assumed)
- Free span for `metatileDefs + stageMetatileRows`: `$8800 - $6600 = $2200 =
  8704` bytes. (`background_turrets.asm` at `$8800` is the hard ceiling; the
  `> $a000` guard is a secondary sanity net.)
- Historical `ENGINE_MAX_STAGE_ROWS = 844` was `(8704 − 256) / 10` with a
  **256‑byte** (16‑entry) def table.
- 64 metatile defs = **1024 bytes**. Worst‑case rows =
  `(8704 − 1024) / 10 = 768` exactly
  (`$6600 + 1024 + 768*10 = $8800`; guard `> $8800` passes).
- **Decision:** editor bound `ENGINE_MAX_STAGE_ROWS = 768` — the uniform
  64‑metatile worst case — regardless of how many metatiles a given level
  actually defines. Simplest correct choice ("a slightly lower max is fine";
  intended levels are ~188–200 rows). The engine's label‑based `> $8800` guard
  stays and remains exact. Not doing a broad memory‑map redesign to preserve
  844.

### Terrain glyph namespace — already level‑owned, already 64 (Phase 1)
- Codes **160–223 = 64‑slot terrain glyph namespace** (`$3D00–$3EFF`),
  `TERRAIN_GLYPH_BASE=160`, `TERRAIN_GLYPH_NAMESPACE=64`. Bitmaps are generated
  per level in `src/generated/level<N>/stage_charset.asm`
  (`terrainGlyphs:`…`terrainGlyphsEnd:`, size‑guarded against
  `TERRAIN_GLYPH_COUNT*8`). `TERRAIN_GLYPH_COUNT` (multiple of 8, ≤ 64) declared
  in `stage_config.asm`.
- §22 engine glyph‑ownership transfer is **already done** — this task does not
  need a charset‑assembly redesign. Remaining §19–21/§28 work is editor‑side:
  decompose a native metatile → sixteen 8‑byte glyphs, deduplicate against the
  level glyph set, show the `X / 64` budget, block export over budget.
- Charset guards unaffected by the metatile‑capacity change: metatile defs are
  4×4 arrangements of glyph *codes*; the glyph *namespace* is a separate axis
  already at 64.
- Diagnostic 224–225 (`$3F00`); shared turret body 226–229; starfield 240–251.
  `background_turrets.asm:59` guards turret glyphs clear of `160..223` + `224/5`.

### Editor contract (Python, `tools/level_editor/`)
- `project.py`: `FORMAT_VERSION = 3`, `SUPPORTED_FORMAT_VERSIONS = (1,2,3)`.
  `LevelProject.tileset = {"glyphCount", "glyphs": [[8]…], "metatileDefs":
  [[16]…]}`. `_validate_tileset` hard‑requires **exactly `METATILE_DEF_COUNT`
  (=16)** metatileDefs entries and glyph codes within
  `160..160+len(glyphs)-1`. Map cell IDs validated `0 <= id < METATILE_DEF_COUNT`.
  `MAX_STAGE_ROWS = ENGINE_MAX_STAGE_ROWS` (844). V1→V2→V3 migration in
  `project_from_dict`; `_migrate_tileset(raw, default_tileset)` fills the tileset
  from the engine baseline for pre‑V3 files.
- `engine_data.py`: the constants above + `METATILE_NAMES` (16‑tuple),
  `load_engine_data(repo_root)` parses the generated level1 files (per‑level
  layout preferred, flat fallback) + the attack catalogue from `main.asm`.
- `ka_export.py`: `render_stage_config` / `render_stage_charset` /
  `render_stage_asm` (emits `metatileDefs:` from `project.tileset["metatileDefs"]`
  then `stageMetatileRows:`) / `render_stage_turrets` / `render_stage_waves`;
  `export_level(project, out_dir, *, engine_data, metatiles)` writes the 5 files.
  No metatile‑count constant emitted.
- `editor.py`: Tkinter, cached `PhotoImage` per metatile (`_get_metatile_image`,
  keyed on `(tile_id, palette, id(tileset))`). `_draw_palette` iterates the
  16‑tuple `METATILE_NAMES` with a fixed `item_height = 46` and a
  `len(METATILE_NAMES)` scrollregion; `_palette_click` does
  `int((canvasy-4)//46)` bounded by `len(METATILE_NAMES)`. Modes: Terrain /
  Turrets / Waves. `_restore_state` unpacks a 9‑tuple incl. `tileset_json`.
  `build_levels.py` + `level2_tileset.py` build both packages deterministically.

### Fixture tooling metatile assumptions
- `tools/make_stage_fixture.py`: hard‑codes `DEF_COUNT = 16` and `id =
  (offset*7 + offset//256 + row) % 16`; parses the real 16 defs out of
  `src/generated/level1/stage_test.asm`. Needs a 64‑def mode (or a sibling
  fixture) to exercise IDs 15/16/31/32/63 for the widen probe.
- `tools/run_stage_fixture.sh <N>`: backs up/writes minimal `level1/`
  `stage_{config,test,turrets,waves}.asm`, builds, runs
  `vice_stage_widen_probe.py`, restores from `/tmp` byte copies (not git).
- `tools/check_stage_addressing.py` proves the 16‑bit row decode arithmetic for
  every logical row; it is decoder‑arithmetic focused (not def‑table focused).

### DithArt fixture (external; do NOT bundle)
`~/Desktop/Ditharts_Free_Scifi_Tileset_v01/` (+ `.zip`).
`texture/tileset_for_free.png` = 256×480 RGBA = 8×15 grid of 32×32 = 120 tiles.
`LICENSE` permits embedded derivative works "clearly defined as such"; forbids
redistributing the raw pack. Pillow is available. Provenance string:
"Dithart's FREE Sci‑fi Tileset v0.1".

---

## 2. Design decisions

1. **Metatile table is variable‑length, no padding.** Exporter emits
   `.const STAGE_METATILE_COUNT = <1..64>` in `stage_config.asm`. Engine derives
   `.const METATILE_DEF_COUNT = STAGE_METATILE_COUNT` (replaces the literal 16),
   keeps `.if (METATILE_DEF_COUNT > 64) .error`, keeps the byte‑size guard,
   validates map IDs `< STAGE_METATILE_COUNT`. No scattered magic 16 (§27).
2. **16‑bit metatile‑def lookup (§8, legal NMOS 6502).** In
   `decodeStageCharacterRow`: read the row's 10 IDs into a small scratch buffer
   first (frees `TEXT_SRC`), then per column compute
   `TEXT_SRC(16) = metatileDefs + (id << 4) + BG_TILE_ROW_OFS` with a 16‑bit
   add and copy 4 bytes via `lda (TEXT_SRC),y` / `y = 0..3`. `id<<4` low byte is
   always a multiple of 16 (≤ $F0), so `+ ofs` (≤ 12) never carries into the
   high byte before the base add. No second zero‑page pair needed; keeps
   register/zp ownership. Does not restructure the row/scroll logic.
3. **`ENGINE_MAX_STAGE_ROWS = 768`** (uniform 64‑metatile worst case). Update
   `engine_data.py`, `project.py` `MAX_STAGE_ROWS`, the editor spinboxes,
   `test_turret_integration.py` (844→768), docs. The engine `> $8800` label
   guard is exact and unchanged.
4. **Repository:** `tools/level_editor/terrain_repository/` —
   `repository.json` (schema‑versioned, deterministic key order, no volatile
   timestamps) + `assets/<assetId>.json` per asset. Asset =
   `{ id, name, schemaVersion, native: { width:16, height:32, pixels:[0..3]…},
   provenance: { sourcePack, sourceTileIndex, sourceCoords, licenceNote,
   localSourcePath? }, notes, tags }`. Native representation = 16 logical MC
   pixels across × 32 rows, values 0..3 (logical indices, never RGB / never a
   level palette). Independent of live glyph IDs (§21).
5. **Schema V4** (`FORMAT_VERSION = 4`, `SUPPORTED = (1,2,3,4)`): add
   `levelMetatileSet` — a list of up to 64 entries each snapshotting a native
   16×32 representation + display name + optional repo `assetId` + provenance.
   `tileset` (packed glyphs + metatileDefs) stays as the compiled output,
   regenerated on save from the level metatile set + dedup. V2/V3 load →
   synthesize `levelMetatileSet` from the existing 16 metatileDefs by
   round‑tripping each through the glyph bitmaps into native 16×32 (visual
   identity preserved, §29). Adding a repo asset **copies** its native data into
   the project (later repo edits/deletes cannot break a build, §25).
6. **Conversion (§16):** deterministic nearest‑colour. Source 32×32 → 16 logical
   MC pixels: average each horizontal pair of source columns (documented
   pair‑reduction policy), keep 32 rows, map each to the nearest of the 4
   project‑palette colours in the existing `C64_COLOURS` table (no second RGB
   table), emit 0..3. Pillow for PNG decode only.
7. **Dedup (§20):** each metatile's 16 cells → 8‑byte glyph bitmaps; identical
   bitmaps share one code; budget readout `Terrain glyphs: N / 64` and
   `This asset: 16 cells, R existing reused, U new unique required`. Export path
   hard‑blocks > 64 unique (§28) — no silent alias/drop.
8. **Determinism / no regex‑patching main.asm (§26).** All new bytes/labels flow
   through the per‑level generated includes with compile‑time guards. Level 1 &
   Level 2 dirs stay independent.

---

## 3. Plan / progress

- [x] Mandatory inspection (AGENTS.md §1 of task) — done, findings above.
- [x] Worklog created (this file).
- [x] **Engine: `STAGE_METATILE_COUNT` + derived `METATILE_DEF_COUNT`; 16‑bit def
      lookup; guard updates.** `src/main.asm`:
      - `.const METATILE_DEF_COUNT = STAGE_METATILE_COUNT`; the `> 16` guard
        replaced with a `1..64` range check.
      - `decodeStageCharacterRow`: reads the row's 10 IDs into a new
        `BG_ROW_IDS` scratch (10 bytes, placed in the `$2920` segment next to
        `BG_INCOMING_ROW` — the `$2000` engine‑state block was full), then per
        column builds `TEXT_SRC(16) = metatileDefs + (id<<4) + BG_TILE_ROW_OFS`
        and copies 4 bytes via `lda (TEXT_SRC),y`. High byte = `id>>4 +
        >metatileDefs`; low add carry folded with `bcc/inc`. Legal NMOS only.
      - `ka_export.render_stage_config` emits `.const STAGE_METATILE_COUNT`.
      - Cost: `decodeStageCharacterRow` 1697 cyc (was ~1050). No cadence
        impact — see tests below.
- [x] **Engine memory: `ENGINE_MAX_STAGE_ROWS 844 → 768`.** `engine_data.py`
      (`METATILE_CAPACITY = 64`, `ENGINE_MAX_STAGE_ROWS = 768`, loader reads the
      variable def count), `project.py` (`METATILE_CAPACITY` import; map‑ID
      check against the level's actual metatile count; `_validate_tileset`
      accepts 1..64 defs), `test_turret_integration.py` (844→768). Engine
      `.if (STAGE_TEST_END > $8800) .error` unchanged — still exact.
- [x] **Engine validation (fixture + probes).**
      - `tools/check_metatile_def_lookup.py` (new): host‑side byte‑exact model
        of the 16‑bit pointer build; 2308 checks, id 0..63 × ofs {0,4,8,12} ×
        9 bases incl. carry/page‑cross. PASS.
      - `tools/make_stage_fixture.py` + `run_stage_fixture.sh`: `[D]` arg for
        1..64 synthetic defs; pins interior cells to ids 15/16/31/32/D‑1.
      - `tools/vice_stage_widen_probe.py`: def table read is now
        capacity‑agnostic (`METATILE_DEFS_END - metatileDefs`); call trampoline
        moved $7000 → $6400 (a 768‑row fixture map fills to $8800 and overlapped
        $7000). On the real 6502: `run_stage_fixture.sh 200 64` and `768 64`
        both PASS (logical rows to 3071 decode byte‑exact); `769 64` → assembler
        error "Metatile stage data collides with the background turret segment
        ($8800)".
      - `check_stage_addressing.py` PASS (row math unchanged).
      - Real Level 1 (16 defs, 9 turrets) `vice_stage_widen_probe` PASS.
      - **`check_raster_capture`**: plain 1200‑frame + stress 900‑frame runs
        both `frame_cycle_deltas [19656]`, 0 service failures, 0 sprite‑start
        misses, 0 catchups.
      - **`check_scroll_capture`** (correct per‑run `charset.bin`): plain
        1200‑frame run **0 failures / 65.1M pixel checks, 74 wraps**,
        `first_transition_ok`. `--stress` run: 4 transient pixel hiccups at one
        raster line (y=55) across frames 92–95 of one coarse transition —
        matches the pre‑existing stress‑harness hiccup documented in
        `docs/encounter-budget-worklog.md`; needs a HEAD‑baseline confirm but
        not a regression (plain run is spotless).
- [x] **Stale generated `level1/` re‑synced.** `build_levels.py` regenerated
      `src/generated/level1/{stage_config,stage_turrets,stage_waves}.asm` +
      `level2/stage_config.asm` from the committed `level.json` source of truth
      (they were built from an earlier 2‑turret / 2‑trigger / different‑palette
      state) and to carry `STAGE_METATILE_COUNT`. `level.json` untouched.
- [x] **Editor data layer — new modules under `tools/level_editor/`:**
      `native_metatile.py` (native grid model, lossless `pixels_to_glyphs` /
      `glyphs_to_pixels`, `GlyphSet` dedup + `GlyphBudgetExceeded`,
      deterministic `pack_metatiles` padding glyphs to a multiple of 8);
      `terrain_repository.py` (`TerrainRepository` at
      `terrain_repository/repository.json`, schema v1, deterministic, **no
      timestamps**, `snapshot()` deep copy, assets carry logical pixels + name +
      provenance + notes + tags, **never live glyph IDs**);
      `terrain_convert.py` (deterministic nearest‑colour, one editor C64 table
      moved to `engine_data.C64_PALETTE_RGB/_HEX`, documented 32→16 horizontal
      pair‑average); `spritesheet.py` (`slice_sheet`, edge cells warned not
      cropped, Pillow decode); `make_test_spritesheet.py` →
      `testdata/synthetic_tileset.png` (120 tiles, committed).
- [x] **Schema V4** (`project.py`): `FORMAT_VERSION = 4`,
      `SUPPORTED = (1,2,3,4)`; `LevelProject.level_metatile_set`;
      `derive_metatile_set_from_tileset` (V1‑3 migration keeps packed `tileset`
      byte‑identical → identical visuals); `repack_tileset_from_metatile_set`;
      `metatile_set_glyph_cost`; `_validate_metatile_set` (1..64);
      `export_readiness_errors` hard‑blocks a >64‑glyph level (§28).
- [x] **Exporter** (`ka_export.py`): `.const STAGE_METATILE_COUNT` (level's real
      count 1..64); `metatileDefs` up to 64. Level 1 / Level 2 dirs still
      independent; `build_levels.py` re‑emits both (level.json migrated to V4).
- [x] **Editor unit tests (§31):** `test_native_metatile.py` (7),
      `test_terrain_repository.py` (6), `test_colour_conversion.py` (7),
      `test_spritesheet.py` (6), `test_metatile_capacity.py` (7) — all pass;
      the 5 existing editor test files still pass (64 editor checks total).
- [x] **Editor GUI** (`editor.py` + new `workshop_ui.py`): `NativeMetatileEditor`
      (zoomed 16×32 paint, 4 project‑palette swatches, click/drag, 4×4 guides,
      undo/redo, live glyph‑cost); `WorkshopDialog` (source preview + native
      editor + Save‑to‑level / Save‑to‑repository); `ImportDialog` (choose PNG,
      tile W/H, cached thumbnails, pick tile). editor palette → level metatile
      set (up to 64, scrollable) with Workshop / New / Import PNG / From repo /
      Rename / Trim‑unused (trailing only, never renumbers); `Metatiles N/64 ·
      Terrain glyphs U/64` in the palette header + status bar. Undo state
      carries the metatile set. Headless smoke: `test_editor_workshop_gui.py`
      (6/6).
- [x] **Migration confirmed:** V1‑3 load keeps packed `tileset` byte‑for‑byte;
      final Level 1 build `check_scroll_capture` 0 failures / 76M px / 87 wraps.
- [x] **Engine VICE (§32/§33):** `vice_metatile64_smoke.py` (64‑def stage, max
      map id 63, boots/scrolls/wraps, live decode byte‑exact);
      `run_stage_fixture.sh 200/300/768 64` PASS, `769 64` → assembler error;
      `check_raster_capture` `[19656]` / 0 / 0 on both the final Level 1 (1400 f)
      and the 64‑def build (900 f); `check_scroll_capture` 0 failures on both;
      `check_fixed_hud_capture` / `check_turret_capture` / `vice_wave_trigger_probe`
      / `vice_level1_smoke` all PASS.
- [x] **Docs:** `docs/level-editor-worklog.md` milestone appended (§40).
- [x] **Report:** `reports/terrain-asset-workshop-report.md` with the 33‑row
      acceptance table (all YES); printed to terminal.

## 4. Constraints (standing)

Legal NMOS 6502 only; ±128 branch range. Exact PAL frame = 19656 cycles.
Preserve raster IRQ / sprite multiplexer / BUILD‑LIVE render plan / scroller /
`prepareBackgroundCoarse`/`finishBackgroundCoarse` split / 16‑bit stage‑row
logic / descending scroll / streaming turret pool. Logical object slot 0 =
player. No commit/push. No `git reset`/`checkout --`/`clean` over user work. Do
not bundle the DithArt pack. VICE automation must not steal macOS keyboard focus
(remote monitor only; background launch).
