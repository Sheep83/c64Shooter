# Terrain Authoring Blockers + Native C64 Terrain Tile Generation

Branch `terrain-asset-workshop` · starting HEAD `3a72c13` · **uncommitted**
(this pass builds on the two earlier uncommitted Terrain Asset Workshop passes).
This report is a deliverable; it is also printed to the terminal. Companion:
`docs/level-editor-worklog.md` (new milestone). No commit, no push.

Three coupled objectives: (1) substantially expand the terrain glyph budget;
(2) fix false refusal when deleting an unused level metatile; (3) generate an
original native C64 bas-relief sci-fi terrain vocabulary and install it into
Level 1.

---

## 1. Current charset usage audit

`STAR_CHARSET = $3800`, VIC bank 0, one charset (256 codes, `$3800..$3FFF`), no
D018 flip / bank switch. `setupStarfieldCharset` copies the ROM charset to
`$3800` **once at boot**; HUD / terrain / starfield glyphs are then copied over
fixed sub-ranges. Menu, gameplay, GAME OVER and hi-score entry all share this
one charset for its whole lifetime.

**Screen codes actually stamped into the `$0400` matrix, by state:**

| source | codes used |
|---|---|
| title "MY FIRST C64 SHOOTER" | letters 1..25, space 32, digits `6`=54 `4`=52 |
| "FIRE TO START" / "HIGH SCORES" / "ENTER YOUR INITIALS" | letters + space (≤ 32) |
| "GAME OVER" (`gameOverLabel`) | 7,1,13,5,32,15,22,5,18 |
| "SCORE 00000" (`scoreLabel`) | 19,3,15,18,5,32,48×5 |
| "LIVES 3" (`livesLabel`) | 12,9,22,5,19,32,51 |
| hi-score names / `randomLetter` | 1..26 (A..Z) |
| score / hi-score digits | 48..57 |
| **HUD row 0 (gameplay)** | **private** 128..145 (never ROM 48..57) |
| terrain rows 1..23 (gameplay) | 160..223 |
| shared turret body (gameplay) | 226..229 |
| starfield | 240..251 |
| diagnostic rail/diagonal | 224..225 |

**The maximum ROM screen code displayed anywhere, in any state, is 54.** Codes
**55..127** of the resident ROM copy are never rendered. The HUD's stock glyphs
(space, `SCORE`, digits, `F`, `R`) are *copied from* ROM codes 3,5,6,15,18,19,
32,48..57 into a private block once per game by `initFixedHud`, then only the
private codes are used during the frame loop - so even those ROM source codes
are not needed after game start.

**Also unused in every state:** 146..159 (old "reserved for HUD expansion",
referenced nowhere), 230..239, 252..255.

**ROM-copy 0..127 residency:** only 1..54 (letters/space/digits) must stay
resident, and only for the menu / GAME OVER / hi-score screens. 55..127 are
dead. Reserved HUD 146..159: genuinely unused. All "free" ranges confirmed
free. No menu/game-over/diagnostic interaction needs codes above 54 or in
146..159 / 230..239 / 252..255.

---

## 2. New terrain glyph capacity and reclaimed code ranges

`TERRAIN_GLYPH_BASE 160 -> 96`, `TERRAIN_GLYPH_NAMESPACE 64 -> 128`.
The terrain namespace is now **codes 96..223 (128 glyphs)**, bitmaps
**`$3B00..$3EFF`** - exactly half the `$3800` charset. Only ONE region moved:
the HUD private glyphs, `HUD_GLYPH_BASE 128 -> 64` (into never-displayed
ROM-copy space 64..81). Diagnostic (224/225), shared turret body (226..229) and
starfield (240..251) are untouched - the terrain ceiling stays 223.

| codes | before | after |
|---|---|---|
| 1..54 | ROM text | ROM text (resident, menu/game-over/hi-score) |
| 55..63 | ROM (dead) | dead gap |
| 64..81 | ROM (dead) | **HUD private glyphs** (18) |
| 82..95 | ROM (dead) | reserved (HUD expansion) |
| 96..127 | ROM (dead) | **terrain glyphs** |
| 128..145 | HUD private | **terrain glyphs** |
| 146..159 | reserved (unused) | **terrain glyphs** |
| 160..223 | terrain (64) | **terrain glyphs** |
| 224..255 | diag / turret / free / starfield / free | unchanged |

Reclaimed for terrain: **codes 96..159** (64 new slots on top of the old 64) -
32 dead ROM codes (96..127) + the old HUD band (128..145) + the old reserved
band (146..159). No runtime charset switching; no bank switch; no D018 flip.

`.label` exports added for the oracles / editor cross-checks:
`HUD_GLYPH_BASE_CODE`, `TERRAIN_GLYPH_BASE_CODE`, `TERRAIN_GLYPH_NAMESPACE_CODE`.

The 64-metatile-ID vocabulary is unchanged and independent: map cells stay one
byte, IDs 0..63, `STAGE_METATILE_COUNT` per level.

---

## 3. Memory-map implications and guards

### `$3800` charset

`terrainGlyphs` copied to `STAR_CHARSET + TERRAIN_GLYPH_BASE*8 = $3B00`; a full
128-glyph block is `$3B00..$3EFF` (1024 B), ending exactly at `$3F00` where the
diagnostic glyph 224 begins - no overlap (`.if (STAR_CHARSET + (96+128)*8 >
$3f00)` passes at equality). HUD private glyphs at `$3A00..$3A8F` (codes
64..81), clear of the clipped sprite pool (`CLIP_SPRITE_POOL_END ≤ $3800`). New
guard: `.if (STAR_CHARSET + HUD_GLYPH_BASE*8 < $3800 + $200)` (HUD base ≥ 64,
past the resident text glyphs).

### `terrainGlyphs` data segment: `$5c00 -> $5a00`

The variable-size `stage_charset.asm` block is `#import`-ed into its own fixed
segment (established last pass). It moved `$5c00 -> $5a00` so a full 128-glyph
(1024-byte) block ends at **`$5e00`**, 512 bytes clear of `raster_scheduler` at
`$6000`. Guards (worst-case, namespace not count):

```
.if (* > TERRAIN_CHARSET_SEGMENT)                       // $4000 code seg vs the block
.if (TERRAIN_CHARSET_SEGMENT + TERRAIN_GLYPH_NAMESPACE*8 > $6000)   // reserve fits a full block
.if (TERRAIN_CHARSET_END > $6000)                       // actual overrun
```

### `$2920` background-control segment - no generated-data dependency

`initBackground`'s terrain glyph copy was an `.for` unroll of
`TERRAIN_GLYPH_COUNT / 8` steps - the last thing whose *code size* scaled with
the glyph count. It is now a **fixed-size runtime loop** (whole-page copy + tail
copy; the count appears only in `ldx #>(...)` / `ldy #<(...)` terminators). So
**nothing** in this timing segment's length depends on generated data. The
`BACKGROUND_CONTROL_END > HEALTH_SPRITE_BASE` guard is a permanent belt-and-braces.

### Measured addresses (`build/main.vs`)

| symbol | committed Level 1 (40 glyphs) | full 128-glyph fixture |
|---|---|---|
| `HUD_GLYPH_BASE_CODE` | `$40` (64) | `$40` |
| `TERRAIN_GLYPH_BASE_CODE` | `$60` (96) | `$60` |
| `TERRAIN_GLYPH_NAMESPACE_CODE` | `$80` (128) | `$80` |
| `terrainGlyphs .. terrainGlyphsEnd` | `$5a00 .. $5b40` (320 B) | `$5a00 .. $5e00` (1024 B) |
| `TERRAIN_CHARSET_END` | `$5b40` | `$5e00` (**512 B** below `$6000`) |
| `BACKGROUND_CONTROL_END` | `$2e56` (**426 B** below `HEALTH_SPRITE_BASE $3000`) | `$2e56` |
| `BACKGROUND_CODE_END` | `$5642` | `$5642` (**958 B** below `$5a00`) |

`check_terrain_glyph_budget.py` substitutes a deterministic 128-glyph
`stage_charset.asm`, assembles, and asserts every boundary above with room to
spare, then restores the originals. The prior pass's fix
(`Background control code overlaps health sprite RAM`) is not regressed - no
generated-data size can relocate timing code.

---

## 4. Root cause and fix for unused-metatile deletion

**Root cause.** `_metatile_remove_unused` only ever inspected *trailing*
metatiles:

```python
for i in range(count - 1, 15, -1):
    if i in used: break          # <- stops at the FIRST used id from the top
    removable.append(i)
if not removable:
    "The highest metatile ID is still used by the map ... Repaint those cells first."
```

If the highest metatile ID was painted anywhere, `removable` was empty and
*every* deletion was refused - even deleting a genuinely-unused *lower* metatile
the user had selected. There was no "delete this metatile and renumber"
operation at all, and a `count <= 16` floor blocked removing any of the first 16.

**Fix.** `project.remove_metatile(project, index)`:

1. `metatile_id_usage(project)` -> if the map still references `index`, raise
   `MetatileInUseError` with a clear message (how many cells, repaint first);
2. otherwise `pop(index)` from `level_metatile_set` (shifting later entries down
   one) and rewrite every map cell: `c - 1 if c > index else c` (cells `< index`
   unchanged; `== index` cannot exist). The painted stage is logically and
   visually identical.
3. Refuses deleting the last remaining metatile.

**Other structures storing scenery metatile IDs:** only `metatile_rows` (the
map). `metatile_metadata` is an always-empty free-form dict (nothing keys it by
metatile ID). Turret objects store `metatileRow`/`metatileCol` (grid
positions); wave triggers store `worldRow` - **neither is a scenery metatile ID
and both are deliberately left untouched** (a regression test asserts this).

**Editor UX:** the metatile-set toolbar gains a per-selection **"Delete"**
button (`_metatile_delete_selected`) - confirms, rejects a used tile with the
count, renumbers on success, fixes selection. **"Trim unused"** is rebuilt on
the same primitive (delete every unused ID from highest down so renumbering is
stable).

`test_metatile_delete.py` (7 checks): delete END unused; delete MIDDLE unused
(higher IDs renumber down, rendered map identical via a base-independent
fingerprint); delete unused just below the highest USED id; a USED tile is
refused with nothing changed; turret + wave data untouched; save/reload/export
deterministic after a delete; the last remaining metatile cannot be deleted.

---

## 5. Generated native terrain design approach

`tools/level_editor/native_terrain_tiles.py`. Authored **directly** as native
16x32 logical-multicolour grids (values 0..3) - no PNG, crop, palette
conversion or manual cleanup. Built from a small library of reusable **4x8
logical cells** so the editor's real glyph packer/deduper does the work:

- fields: `PLATE`, `PLATE_RIVET`, `SCUFF`, `PANEL_INNER`
- edges: `EDGE_T/B/L/R`
- bevels (raised): `BEV_TL/TR/BL/BR`; recess corners: `REC_TL/TR/BL/BR`
- seams / ribs: `SEAM_H`, `SEAM_V`, `RIB_WIDE`
- machinery: `VENT`, `GRILLE`, `CONDUIT_H`, `CONDUIT_V`, `CONDUIT_BEND_TR`
- accents: `HAZARD` (chevrons), `BRACE_D` / `BRACE_A` (chunky diagonals)
- open structure: `VOID`, `PIT_WALL_L/R`, `PIT_LIP`, `PIT_FLOOR`
- landmark: `CORE_TL/TR/BL/BR` (glowing reactor quadrants)

Composed row-major (4 cells x 4 rows) into **31 metatiles**. Original work in
the broad 1980s C64 tradition; no tile, map section, sprite or surface from
Uridium / Paradroid / Parallax is reproduced or traced.

`--sheet` prints an ASCII contact sheet (each logical pixel doubled
horizontally for the 2:1 aspect, ramp ` .:#`) for dev inspection - no image
dependency added.

---

## 6. Lighting / bas-relief convention

Consistent light from the **top-left**. Four palette roles:

| role | meaning |
|---|---|
| `0` D021 background | void / deep recess / gap between structures |
| `1` D022 mid | the metal body / field of every panel |
| `2` D023 shadow | bevels facing away from the light (bottom / right), seam lines, recess interiors |
| `3` char highlight | bevels facing the light (top / left), rivet gleam, conduit crowns, hazard chevrons |

A **raised** panel = highlight on top+left edges, shadow on bottom+right, body
in the field. A **recessed** panel is the exact inverse. Bands are 1-3 logical
pixels (each is 2 physical px wide), no high-frequency dither. An automated
check bounds isolated single-logical-pixel counts per tile (worst tile: 8, well
under a checker/dither field).

---

## 7. Level 1 metatiles added / retained / replaced

Level 1's previous 16 metatiles were the pre-workshop `METATILE_NAMES`
"riveted-hull" set (`PLATE, R_FILL, R_T..R_BR, CHAN_V/H, RECESS, GRILLE, MACH,
STEP`) painted over the `inspection-100` **test** map. The real authored content
of Level 1 is its **turrets and wave triggers**, not that placeholder terrain.

`install_level1_terrain.py` (deterministic, re-runnable):

- **replaced** the 16 placeholder metatiles with the **31 generated native
  tiles**;
- **remapped** every painted map cell old-id -> new-id (`PLATE->DECK_PLAIN`,
  `R_T->WALL_TOP`, `CHAN_H->CONDUIT_H`, `GRILLE->GRILLE_BANK`, `MACH->MACHINE_A`,
  `STEP->SEAM_HORIZ`, ...) so the scrolling stage keeps its structure;
- **added a 3-row demo patch** at rows 2-4 (blank in the committed map, no
  turret or wave trigger within the aperture there) laying all 31 tiles side by
  side for visual validation;
- **retained unchanged:** 9 turrets, 2 wave definitions, 5 wave triggers,
  palette, height 100, scroll divider.

Level 2 artwork is untouched (its `level2_tileset.py` vocabulary is unchanged;
only the exported glyph *code numbers* re-base 160 -> 96).

---

## 8. Exact metatile count

**Level 1: 31 metatiles** (`STAGE_METATILE_COUNT = 31`), IDs 0..30.
Native library: 31. Target was ~20..32.

---

## 9. Exact unique terrain glyph count after dedupe

- Native library standalone: **31 metatiles -> 36 unique 8-byte terrain glyphs**
  (avg 1.2 glyph/metatile; a naive "16 new glyphs per metatile" import would be
  **496** - the generated set is ~**14x** denser).
- Installed in Level 1 (`repack_tileset_from_metatile_set` pads to a multiple of
  8): **`TERRAIN_GLYPH_COUNT = 40`** of the 128 available.

---

## 10. Examples / categories of generated tiles

| category | tiles |
|---|---|
| plain / lightly-detailed deck | `DECK_PLAIN`, `DECK_RIVET`, `DECK_SCUFFED`, `DECK_PANEL` |
| raised / recessed armour | `PLATE_RAISED`, `PLATE_RECESSED`, `ARMOUR_PLATE`, `HATCH` |
| structural seams | `SEAM_HORIZ`, `SEAM_VERT`, `SEAM_CROSS` |
| edges / walls / corners | `WALL_LEFT/RIGHT/TOP/BOTTOM`, `CORNER_TL`, `CORNER_BR` |
| machinery | `VENT_BANK`, `GRILLE_BANK`, `RIB_FIELD`, `MACHINE_A`, `MACHINE_B` |
| conduits | `CONDUIT_H`, `CONDUIT_V`, `CONDUIT_BEND` |
| hazard / brace | `HAZARD_BAND`, `BRACE_X` |
| open structure | `PIT_MOUTH`, `GAP` |
| landmarks | `CORE` (glowing reactor), `DAMAGED` |

---

## 11. Files changed

### Engine
| file | change |
|---|---|
| `src/main.asm` | `HUD_GLYPH_BASE 128->64`; `TERRAIN_GLYPH_BASE 160->96`, `TERRAIN_GLYPH_NAMESPACE 64->128`; guards for the new layout + a HUD-base guard; `HUD_G_*` consts replace two hard-coded HUD `.byte` rows; `.label HUD_GLYPH_BASE_CODE / TERRAIN_GLYPH_BASE_CODE / TERRAIN_GLYPH_NAMESPACE_CODE`; `initBackground` terrain glyph copy -> fixed-size runtime loop; `terrainGlyphs` segment `$5c00 -> $5a00` (`.const TERRAIN_CHARSET_SEGMENT`); guards + comments updated for the 1024-byte worst case |
| `src/generated/level1/*` | re-exported: 31 native metatiles, `TERRAIN_GLYPH_COUNT 48->40`, `STAGE_METATILE_COUNT 16->31`, glyph codes 96.., `WAVE_TRIGGER_COUNT 5` |
| `src/generated/level2/{stage_charset,stage_test}.asm` | re-exported at glyph base 96 (artwork unchanged) |

### Editor
| file | change |
|---|---|
| `tools/level_editor/engine_data.py` | `TERRAIN_GLYPH_BASE 96`, `TERRAIN_GLYPH_NAMESPACE 128`, `TERRAIN_GLYPH_BASE_LEGACY 160`; `load_engine_data` auto-remaps a stale generated tree's glyph base |
| `tools/level_editor/project.py` | `FORMAT_VERSION 5`; `_migrate_tileset` shifts pre-v5 glyph codes 160->96; `remove_metatile()` + `metatile_id_usage()` + `MetatileInUseError`; capacity comments |
| `tools/level_editor/native_metatile.py` | `capacity` / `glyph_base` defaults from `engine_data` |
| `tools/level_editor/editor.py` | glyph base from `engine_data` (no literal 160); `_metatile_delete_selected` + "Delete" button; "Trim unused" rebuilt on `remove_metatile`; capacity strings use `TERRAIN_GLYPH_NAMESPACE` |
| `tools/level_editor/ka_export.py`, `build_levels.py`, `level2_tileset.py` | glyph base from `engine_data`; comment text |
| `tools/level_editor/native_terrain_tiles.py` | **new** - the native bas-relief tile library + dedup stats + ASCII contact sheet |
| `tools/level_editor/install_level1_terrain.py` | **new** - deterministic Level 1 installer (swap set, remap map, demo patch, re-export) |
| `tools/level_editor/levels/level{1,2}/level.json` | Level 1: 31 native metatiles + remapped map + demo patch (turrets/waves preserved). Level 2: fmt-5 migration (codes re-based). |
| `tools/level_editor/terrain_repository/repository.json` | untouched by this pass (11 user-authored assets preserved) |

### Tests / tooling
| file | change |
|---|---|
| `tools/check_fixed_hud_capture.py` | HUD/terrain code ranges read from the exported `_CODE` labels (fallbacks to old values) |
| `tools/check_terrain_glyph_budget.py` | rewritten for a full **128**-glyph fixture + `$5a00` window + all reserved-region guards |
| `tools/level_editor/test_metatile_delete.py` | **new** (7 checks) |
| `tools/level_editor/test_native_terrain_tiles.py` | **new** (8 checks) |
| `test_{native_metatile,metatile_capacity,turret_integration,turret_unlimited,wave_schema,editor_workshop_gui}.py`, `make_stage_fixture.py`, `vice_bottom_origin_probe.py`, `acceptance_terrain_workshop.py` | parameterised on `TERRAIN_GLYPH_BASE` / relative counts (was hard-coded 160 / 16 / 17) |

---

## 12. Tests added / updated

New: `test_metatile_delete.py`, `test_native_terrain_tiles.py`,
`check_terrain_glyph_budget.py` (rewritten). Updated: `check_fixed_hud_capture.py`
(base labels), and 8 editor tests / tools de-hard-coded off `160` / `64` / a
fixed engine baseline.

---

## 13. Editor test results

```
test_colour_conversion.py       All 7 passed
test_editor_workshop_gui.py     All 9 passed
test_level_packages.py          All 6 passed
test_metatile_capacity.py       All 7 passed
test_metatile_delete.py         All 7 passed          (NEW)
test_native_metatile.py         All 7 passed
test_native_terrain_tiles.py    All 8 passed          (NEW)
test_spritesheet.py             All 6 passed
test_terrain_repository.py      All 6 passed
test_turret_integration.py      All 8 passed
test_turret_unlimited.py        All 5 passed
test_viewport_model.py          All 6 passed
test_wave_schema.py             All 6 passed
acceptance_terrain_workshop.py  PASS (8 steps)
check_metatile_def_lookup.py    PASS (2308 arithmetic checks)
check_stage_addressing.py       PASS
```

---

## 14. Max-capacity / over-capacity results

- `check_terrain_glyph_budget.py`: a full **128-glyph** Level 1 assembles;
  `terrainGlyphs $5a00..$5e00` (1024 B), `BACKGROUND_CONTROL_END $2e56`
  (426 B below `$3000`), `TERRAIN_CHARSET_END $5e00` (512 B below `$6000`),
  `BACKGROUND_CODE_END $5642` (958 B below `$5a00`); committed Level 1 unaffected.
- `test_native_metatile.py` still proves `GlyphBudgetExceeded` fires when a set
  needs more unique glyphs than capacity (no silent alias/drop) - exercised with
  an explicit capacity.
- `run_stage_fixture.sh 768 64` decodes **ID 63** byte-exact on the 6502
  (logical rows to 3071); `run_stage_fixture.sh 769 64` -> assembler error
  `Metatile stage data collides with the background turret segment ($8800)`.
- `vice_metatile64_smoke.py` - 64-metatile stage, **max map id 63**, boots to
  PLAYING, scrolls, wraps, live `decodeStageCharacterRow` byte-exact.
- Editor candidate-cost UI shows `Terrain glyphs: U / 128` (capacity from
  `TERRAIN_GLYPH_NAMESPACE`); over-budget adds are blocked at Workshop save and
  at `export_readiness_errors`.

---

## 15. Metatile-delete regression result

`test_metatile_delete.py` - **7/7**: END / MIDDLE / just-below-highest-used
removal all renumber the map so the rendered stage is byte-identical (verified
via a base-independent per-cell fingerprint); a used metatile is refused with a
clear count and nothing changes; turret grid positions and wave-trigger world
rows are untouched; save / reload / export are deterministic after a delete;
the last remaining metatile cannot be deleted.

---

## 16. VICE visual / runtime result

Background `x64sc`, remote monitor only, no `open -a`, no keyboard-focus steal.
On the **new Level 1** (31 native bas-relief metatiles, 40 glyphs at codes
96..135, HUD at code 64, demo patch at rows 2-4):

| probe | result |
|---|---|
| `vice_stage_widen_probe.py` | **PASS** - 80 logical rows decode byte-exact |
| `vice_metatile64_smoke.py` | **PASS** - 64-def stage, max map id 63, boots/scrolls/wraps, live decode byte-exact |
| `check_raster_capture.py` (1200 f) | `frame_cycle_deltas [19656]`, **service_failure_count 0**, **sprite_start_miss_count 0**, catchups 0, replay_frames 0 |
| `check_scroll_capture.py` (1200 f, per-run charset) | **failure_count 0** / 64.8M pixel checks / **74 wraps** / `first_transition_ok` / no stage-step errors - the new terrain glyphs at `$3B00` render pixel-perfect through every fine phase and wrap |
| `check_fixed_hud_capture.py` | **0 failures** - HUD private glyphs at code 64 render correctly, stock-glyph copies verified, no terrain/HUD charset collision |
| `check_turret_capture.py` | **0 failures** - shared turret body glyphs / flash / ground-code restore intact |
| `vice_wave_trigger_probe.py` | **PASS** - 5 authored triggers latch / re-arm across the wrap / resolve authored values |
| `vice_bottom_origin_probe.py` | **PASS** - bottom-origin startup; streaming turret pool ≤ 8; killed turret stays dead across the wrap |
| `vice_level1_smoke.py` | **PASS** - end-to-end: turret pool + authored waves, `GAME_STATE` PLAYING, scroll + wrap |

**Known stress-harness artefact (not new):** `vice_scroll_test.py --stress` +
`check_scroll_capture.py` shows 5 transient pixel mismatches, all at raster line
**y = 55**, frames 92-95, during one coarse transition, with
`frame_cycle_deltas [19656]` and 0 raster service failures. Same signature and
location as the pre-existing hiccup documented in
`docs/encounter-budget-worklog.md` and the previous two reports; the non-stress
capture is spotless.

Visual check (ASCII contact sheet + the scroll-capture pixel oracle, which
renders every terrain cell from the dumped charset): recognisable raised /
recessed bevel geometry, chunky readable bands, no one-pixel logical noise
(worst tile 8 isolated pixels), seamless tiling where intended (`DECK_PLAIN` /
`SEAM_*` / `WALL_*` runs), and - because there is no external conversion step -
zero conversion artefacts.

---

## 17. PAL cadence result

`check_raster_capture.py` `frame_cycle_deltas` = **`[19656]`** (single value,
no jitter) on the new Level 1 (1200 physical frames, 74 wraps), the 64-def
fixture, and the `--stress` capture. `service_failure_count = 0`,
`sprite_start_miss_count = 0`, `catchups = 0` in every case. The terrain glyph
copy moved to init-time only and is now fixed size; no frame-loop code changed.

---

## 18. Remaining caveats

1. **Terrain namespace ceiling is code 223** (diagnostic starts at 224). 128 is
   the maximum without also relocating the diagnostic / turret / starfield
   glyphs; the three guards make an over-reach a clean build error.
2. **`terrainGlyphs` reserved window is 1024 bytes at `$5a00`** (`$5a00..$5e00`,
   512 B clear of `$6000`). A future need to grow the `$4000` background/HUD code
   past ~958 bytes, or the namespace past 128, is a clean guard error, not a
   silent overlap.
3. **formatVersion 5 re-bases stored glyph codes 160 -> 96 on load.** Native
   `levelMetatileSet` pixels are unaffected; the packed `tileset` codes shift
   (bitmaps identical). A pre-v5 `level.json` opened and re-saved is migrated in
   place; `load_engine_data` also tolerates a stale generated tree.
4. **`build_levels.py` still does not round-trip `level.json`** for Level 1 (it
   reconstructs from a Python spec). The Level 1 terrain install uses
   `install_level1_terrain.py` and the direct `load_project` + `export_level`
   path; `build_levels.py`'s `build_level1` reconstruction is a documented,
   out-of-scope wart.
5. **`--stress` scroll-capture y=55 hiccup** persists unchanged (see §16).
6. **HUD private glyphs live at codes 64..81** now. Any external tool that
   hard-codes 128 for the HUD needs the exported `HUD_GLYPH_BASE_CODE`
   (`check_fixed_hud_capture.py` was updated).

No stop condition was hit: no second screen matrix / shadow matrix / D018 flip /
separate background IRQ; no sprite-multiplexer, scroller, raster-scheduler,
render-plan, collision, player-slot-0 or bottom-origin change; legal NMOS 6502
only; exact `[19656]` PAL cadence preserved.
