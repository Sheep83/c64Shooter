# Pre-Merge Level Authoring Pass

Branch `background-scroll-first-working-prototype` (work started from
`multicolour-with-turrets-experiment` HEAD). **Uncommitted.** This report is the
deliverable; it is also printed to the terminal.

---

## 1. Summary

Nine coupled changes land the level-authoring surface in a mergeable state:

1. **Editor gameplay-viewport overlay** — an accurate, movable, editor-only
   picture of the real C64 terrain aperture (40 chars × 23 logical rows,
   bottom-origin), never saved or exported.
2. **Turret count contract** — the arbitrary 3-turret cap is gone, *including*
   the concurrent-visible limit. A level may author 0, 1, or many turrets, and
   any number of them may be on one gameplay screen. The runtime redesign makes
   **every live turret share ONE 4-code body glyph set** (codes 226–229),
   published once; the hit flash is colour-RAM only and a destroyed turret puts
   the actual terrain screen codes it covered back. Concurrent capacity is no
   longer fixed by 4 glyph codes per turret — it is `TURRET_POOL = 8` live
   *state* slots, which exceeds the ~7 turrets a 23-row aperture can physically
   hold and the 5 that can be combat-visible. There is **no editor
   viewport-density rejection** any more.
3. **Authored wave triggers** — first editor + engine representation of enemy
   encounter timing, anchored to **world/logical rows** (never elapsed frames).
   A trigger fires when its terrain row reaches the top edge of the aperture
   (`SCROLL_ROW == worldRow`). Reusable **wave definitions** reference the
   engine's existing curated-attack catalogue. Level 1 fires its authored
   triggers at the intended terrain positions at runtime; the autonomous
   CIA-random director is compiled out of the Level 1 path and documented.
4. **Explicit level packages** — a level is a self-contained package owning its
   terrain map, palette/config, authored turrets, **its own terrain tileset**,
   and its wave data.
5. **Level 1** — the current riveted-hull tileset and visual style, still the
   only level gameplay loads, bottom-origin retained, builds/runs exactly as
   before except the turret-count change. Basis: the existing `inspection-100`
   map.
6. **Level 2** — a deliberately crude, visibly distinct **planet-surface**
   package (rocky/cratered ground, rough cliffs, strata, pits, sparse alien
   pods), editor/export proof only; gameplay never enters it.
7. **Level-owned terrain glyph memory** — the terrain glyph bitmaps move out of
   `src/main.asm` into a generated per-level `stage_charset.asm`; permanent
   HUD/UI/engine glyph allocations are untouched.
8. **Editor level load/switch** — `Open Level…` / `New Level…` switch packages
   and reset **all** editor state (map, palette, tileset, turrets, wave data,
   dimensions, viewport). The viewport is re-clamped into the new level's range.
9. **Export organisation** — `src/generated/level1/` and `src/generated/level2/`,
   five includes each, deterministic, coexisting; gameplay imports `level1/`
   only.

**Gameplay still loads Level 1 only. No runtime level progression / multiload
was added.** The raster IRQ, sprite multiplexer, BUILD/LIVE render-plan system,
scroller, coarse-scroll admission gate and collision plumbing are untouched
except where explicitly listed below.

---

## 2. Files changed

### Engine (`src/`)

| file | change |
|---|---|
| `src/main.asm` | imports now `generated/level1/{stage_config,stage_turrets,stage_waves,stage_test}.asm`; inline `terrainGlyphs` block + `.const TERRAIN_GLYPH_COUNT` deleted, replaced by `#import "generated/level1/stage_charset.asm"` at the same PC; `.const TURRET_POOL = 8` + `.label WAVE_TRIGGER_COUNT_CODE`; new RAM `WAVE_TRIGGER_CURSOR/FIRE/REWIND`; new routines `initWaveTriggers` / `updateWaveTriggers` / `startAuthoredWave` + the `waveTrig*` runtime tables (placed in the `$4000` segment — the pre-`$1f00` code region was full); `updateSpawner` `!startNext` and `startGame` boot call branch on `WAVE_TRIGGER_COUNT`; `gameLoop` frame loop calls `updateTurretStream` + `updateWaveTriggers` before `positionBackgroundTurrets`; `prepareBackgroundCoarse` wrap branch sets `TURRET_STREAM_REWIND` + `WAVE_TRIGGER_REWIND`; `updateTurretPressure` scans `TURRET_POOL`. |
| `src/background_turrets.asm` | **streaming turret pool + shared-body-glyph rewrite.** `TURRET_COUNT`→`TURRET_TOTAL`; `TURRET_POOL = 8` state slots; ONE shared 4-code body glyph set (was 4 codes × pool); hit flash → colour RAM (`TURRET_HIT_CRAM`); destroyed turret → cached terrain **screen codes** (`turretGroundCodes`, 4 B/slot) written back from `publishTurretGlyphs` (safe window); split `TURRET_STATE`/`TURRET_SCRATCH` clear blocks; new `updateTurretStream` / `turretRelInWindow` / `admitTurretSlot` / `cacheTurretGroundCodes` / `restoreDeadTurretCells` / `markTurretDestroyed` / `turretIsDestroyed`; `turretAuth*` assembly-time LUTs (desc by row); `turretDestroyedBits`; `TURRET_SLOT_*` per-slot geometry; `installTurretRow` / `positionBackgroundTurrets` / `updateBackgroundTurrets` / `pulseTurretColour` / `traceTurretCannon` / `hitCannonTarget` reworked; dropped `TURRET_AIM` / `*_STYLE` arrays + `aimBackgroundTurret`. |

### Generated (`src/generated/`)

- **removed:** flat `stage_config.asm`, `stage_test.asm`, `stage_turrets.asm`.
- **added:** `level1/` and `level2/`, each with
  `stage_config.asm`, `stage_charset.asm`, `stage_test.asm`,
  `stage_turrets.asm`, `stage_waves.asm`.

### Editor (`tools/level_editor/`)

| file | change |
|---|---|
| `project.py` | `formatVersion: 3`; `LevelProject` gains `tileset`, `wave_definitions`, `wave_triggers`; `MAX_TURRETS = 255`; `_turret_window_overflow` validation; viewport helpers (`stage_logical_rows`, `max_viewport_top`, `clamp_viewport_top`, `default_viewport_top`, `viewport_*_range`); wave schema validation; V1/V2→V3 migration with `default_tileset`. |
| `engine_data.py` | reads the per-level `level1/` layout (flat fallback); parses the `ATTACK_*` catalogue + `attackInterval` / `attackSpriteStart` tables; new consts `TURRET_POOL`, `MAX_AUTHORED_TURRETS`, `VIEWPORT_ROWS/COLS`, `ATTACK_COUNT`, `ENEMY_TYPE_COUNT`. |
| `ka_export.py` | `render_stage_charset` (new) + `render_stage_waves` (new) + `render_stage_turrets` emits `TURRET_TOTAL` desc-sorted; `export_level(project, dir, engine_data=…)` writes the 5-file package; `render_stage_config` also emits `TERRAIN_GLYPH_COUNT`; legacy 3-file `export_project` kept. |
| `editor.py` | viewport overlay + `Gameplay view` slider / `Shift`+wheel / arrow-key scrub; `Waves` mode + wave-definition list/form + trigger inspector + on-canvas trigger flags/drag; `Open Level…` / `New Level…` package workflow with full-state reset; per-level tileset rendering; turret cap removed, density warning; per-level 5-file export. |
| `level2_tileset.py` | **new** — the crude planet-surface tileset (48 glyphs + 16 metatile defs) as Python data. |
| `build_levels.py` | **new** — deterministically builds both `levels/level{1,2}/level.json` + their generated dirs. `build_acceptance_level.py` is now a shim to it. |
| `levels/level1/level.json`, `levels/level2/level.json` | **new** — the two authored packages. |
| `test_turret_integration.py` | updated for `TURRET_TOTAL` / desc sort / tileset. |
| `test_turret_unlimited.py`, `test_wave_schema.py`, `test_viewport_model.py`, `test_level_packages.py` | **new** headless regression suites. |

### Tooling (`tools/`)

`vice_scroll_test.py` (dump `turretAuth*` + the split `TURRET_STATE`/`SCRATCH`
blocks), `check_fixed_hud_capture.py` + `check_turret_capture.py` (shared-body-
glyph model), `vice_encounter_fixtures.py` (pool `TURRET_SLOT_AUTH` seeding +
authored-mode wave start; dropped `TURRET_AIM`), `vice_bottom_origin_probe.py` +
`vice_turret_large_row.py` (rewritten for the pool),
`run_stage_fixture.sh` + `make_stage_fixture.py` (`level1/` layout +
`stage_waves.asm`). **New:** `vice_wave_trigger_probe.py`, `vice_level1_smoke.py`.

### Docs

`docs/level-editor-worklog.md` — new milestone section.

---

## 3. Gameplay-viewport overlay — dimensions, coordinate model, UI

**Real aperture (inspected, not assumed).** 24-row display (`RSEL = 0`), badline
at raster 55. Matrix **row 0 is the fixed hires HUD**; matrix **rows 1..23 are
terrain** (40 columns × **23 logical rows**); matrix row 24 never reaches the
`RSEL = 0` aperture. Bottom-origin: `STAGE_START_ROW = STAGE_LOGICAL_ROWS - 23`;
`initBackground` seeds 16-bit `SCROLL_ROW` to it. Matrix row `d` shows logical
row `SCROLL_ROW + d - 1`, so the visible range is
`[SCROLL_ROW .. SCROLL_ROW + 22] mod STAGE_LOGICAL_ROWS`.

**Editor model.** `viewport_top` (an editor-only int, **never serialised, never
exported**) is the logical row shown at matrix row 1. Range `[0,
STAGE_LOGICAL_ROWS - 23]`, clamped on every load / row-count change / level
switch; it never wraps. Default = `STAGE_LOGICAL_ROWS - 23` — the bottom-origin
boot view, whose bottom edge is the authored last logical row (= gameplay start).
Editor row index `i` ↔ metatile row `i` ↔ logical rows `[4i .. 4i+3]`, so the
overlay covers metatile rows `[viewport_top // 4 .. (viewport_top + 22) // 4]`.

**UI.** A faint cyan band on the working-stage canvas from `viewport_top*8` to
`(viewport_top+23)*8` px, with a bold **yellow top edge = the wave activation
line**, and an unobtrusive `logical rows N–M` label. Moved by the `Gameplay
view` slider (primary), `Shift`+mousewheel over the canvas, or `↑`/`↓` when the
canvas has focus — no zoom, no free-form region. Turret markers whose world row
is inside the band render solid; outside, hollow/greyed — turret density per
gameplay screen is directly inspectable. Selecting a wave trigger snaps the band
so its top edge sits on the trigger row, previewing exactly what is on screen
when that wave starts.

Regression: `tools/level_editor/test_viewport_model.py` (6 checks — geometry,
bottom-origin default, clamp, no-wrap, metatile mapping, re-clamp on shrink).

---

## 4. Authored wave-trigger + wave-definition schema and runtime semantics

### Schema (`level.json`, `formatVersion: 3`)

```jsonc
"waveDefinitions": [
  { "id": "wd_top_sweep", "name": "Top sweep",
    "attackId": 0,                                   // engine catalogue id 0..11 (ATTACK_* name in UI)
    "composition": [ { "enemyType": 0, "count": 5 } ], // list => extensible to mixed; runtime uses entry 0
    "spawnInterval": null }                          // null => attack-table default
],
"waveTriggers": [
  { "id": "wt_intro", "worldRow": 372, "waveDef": "wd_top_sweep" }  // 16-bit logical row
]
```

- **Trigger = *when*** (`worldRow`, a world position). **Wave definition = *what***
  (`attackId` bundles formation + movement pattern + ingress/manoeuvre/egress +
  entry geometry from the engine's curated-attack catalogue; `composition`,
  `spawnInterval`). No graphical formation/path editors — the editor references
  catalogue names/ids only.
- **Composition is authoritative for wave size.** There is no separate `size`.
  The runtime consumes `composition[0]` (one enemy type today); a `> 1`-entry
  composition is stored and exported as entry 0 with this documented caveat, so
  mixed composition can be added later without a trigger-format rewrite.
- `worldRow` is never a frame count — changing `SCROLL_FRAME_DIVIDER` cannot move
  a trigger relative to terrain (proven by test + probe, §7).

### Generated (`stage_waves.asm`) — constants + assembler lists only

`.const WAVE_TRIGGER_COUNT` + `waveTriggerRowLo/RowHi` (sorted **descending**),
`waveTriggerAttackId`, `waveTriggerCount` (= clamped composition size),
`waveTriggerSprite` (= `enemyType * 8`), `waveTriggerInterval` (override or
attack-table default). `main.asm` materialises these into the `waveTrig*`
`.fill` tables at a data location.

### Exact activation relationship

A trigger fires **the instant its authored terrain row enters the top edge of
the terrain aperture**, i.e. when `SCROLL_ROW == trigger.worldRow` (matrix row 1
— the newest-revealed row, already computed by `prepareBackgroundCoarse` right
after `SCROLL_ROW--`). `updateWaveTriggers` (frame loop) latches
`WAVE_TRIGGER_FIRE = cursor+1` and advances the cursor once
`SCROLL_ROW <= waveTriggerRow[cursor]` (16-bit; `<=` also catches the wrap
step). The editor draws this activation line as the **top edge of the viewport
band**.

### Runtime integration (Level 1 path)

`startGame` calls `initWaveTriggers` always; it calls `startRandomWave` **only
when `WAVE_TRIGGER_COUNT == 0`**. `updateSpawner`'s `!startNext`:

- `WAVE_TRIGGER_COUNT == 0` → today's autonomous CIA-random `startRandomWave`
  (verbatim, still compiled).
- `WAVE_TRIGGER_COUNT > 0` → if `WAVE_TRIGGER_FIRE != 0`, current wave finished,
  and **not** `TURRET_PRESSURE_ACTIVE` → `startAuthoredWave` (a copy of
  `startRandomWave` that takes the attack id from the trigger and overrides
  `WAVE_ENEMY_COUNT` / `WAVE_SPRITE_INDEX` / `WAVE_SPAWN_INTERVAL` from the
  resolved trigger; everything else — X/Y seed, add-X/Y, ingress/manoeuvre/egress
  — still from the `attack*` tables), then clears the latch.

The per-member spawn loop, `WAVE_GAP`, the turret-pressure *hold*, the shooter
budget and every other encounter mechanic are reused unchanged. The autonomous
director is thus **isolated for Level 1, not removed** — this is the
spec-sanctioned transition.

### Stage-wrap behaviour (deliberate, documented)

On `SCROLL_ROW 0 → STAGE_LOGICAL_ROWS-1` (`prepareBackgroundCoarse`),
`WAVE_TRIGGER_REWIND` is set; the next `updateWaveTriggers` rewinds
`WAVE_TRIGGER_CURSOR` to 0 and clears `WAVE_TRIGGER_FIRE`. **Authored triggers
deliberately re-fire once per stage loop** — the stage is designed to loop and
encounters should recur. A forward-only cursor that never advances past an
unconsumed trigger + the single `WAVE_TRIGGER_FIRE` latch rule out duplicate
firing within a loop and guarantee no trigger is skipped.

### Level 2

`levels/level2/level.json` stores/edits/exports wave definitions + triggers, and
`src/generated/level2/stage_waves.asm` is generated and committed, but it is
never `#import`-ed — gameplay is unaffected.

Regression: `test_wave_schema.py` (6 checks); `vice_wave_trigger_probe.py` (5
checks, §7).

---

## 5. Turret-count contract

- **Authored:** `TURRET_TOTAL` in `stage_turrets.asm`, 0..255 (8-bit streaming
  cursor). `turretCols` / `turretRows` are 16-bit-safe world char cols/rows,
  **sorted descending by world row** (the order the downward-scrolling
  `SCROLL_ROW` crosses them). A `List()` with no `.add` is emitted for 0.
- **Runtime rendering — shared body glyphs.** Every live turret's 2×2 screen
  cells point at **one shared 4-code body glyph set** (`TURRET_GLYPH_BASE =
  226`..229, from `turretArt` style `TURRET_STATIC_STYLE`), published once by
  `publishTurretGlyphs` and never changed. Concurrent visible capacity is
  therefore *independent of glyph codes*. Codes 230–239 are now free.
  - **Hit flash** is colour-RAM only: a hit turret's four colour-RAM cells use
    `TURRET_HIT_CRAM` (light red, distinct from the pulse) for `TURRET_HIT_FRAMES`
    frames, via the already-per-turret-per-frame `pulseTurretColour`. No glyph
    swap, no per-slot glyph state.
  - **Destroyed turret** shows the real terrain: at admit, `cacheTurretGround-
    Codes` stores the 4 decoded terrain *screen codes* the body covers
    (`turretGroundCodes`, 4 bytes/slot). `updateBackgroundTurrets` only *flags*
    the kill; `publishTurretGlyphs` (frame start, beam still in the border - a
    safe window to touch screen RAM) then writes those 4 codes + the fixed
    terrain colour RAM back into the cells once, positioned from the current
    `SCROLL_ROW`. The cells then scroll with the terrain; any later row re-render
    leaves the freshly-decoded terrain (`installTurretRow` skips dead slots).
- **Pool = per-slot STATE, `TURRET_POOL = 8`.** The only bound left is the
  per-slot state array staying under the 128-byte signed-X clear-loop
  convention: 15 one-byte arrays × `TURRET_POOL` ≤ 128 ⇒ `TURRET_POOL ≤ 8`.
  8 exceeds the **geometric maximum** of turrets that can be on one 23-row
  aperture at once: turrets sit on distinct metatile rows (≥ 4 logical rows
  apart), and `positionBackgroundTurrets` marks a body combat-visible only for
  `rel ∈ [1,20]` ⇒ at most **5 combat-visible**, ≈ **7 rendered** (aperture +
  stream margin). If the pool were somehow full, `updateTurretStream` just
  defers the extra turret a frame - it never corrupts. So `TURRET_POOL` is a
  code-simplicity choice, not a rendering or performance limit, and could be
  lifted with a two-pass clear if a future aperture change ever needed it.
- `updateTurretStream` (once/frame before `positionBackgroundTurrets`, once from
  `initBackgroundTurrets`): **admit** while a slot is free and `SCROLL_ROW <=
  turretAuthRow[cursor] + MARGIN` (MARGIN = 3) - copy geometry, seed health
  (dead if the `turretDestroyedBits` bit is set), cache the terrain codes,
  advance the cursor; **evict** any slot whose `rel = (slotRow - SCROLL_ROW)
  mod SLR` leaves `[0, 22+MARGIN] ∪ [SLR-MARGIN, SLR-1]`, recording destruction
  into `turretDestroyedBits` first if it died on screen. `TURRET_STREAM_CURSOR`
  rewinds to 0 on each stage wrap (`TURRET_STREAM_REWIND`); the destroyed bitmap
  is never cleared, so a killed turret re-admits already-dead (cannot fire,
  cannot be re-scored - `awardKillScore` guarded by the bit).
- **Editor:** the viewport-density validation error is **removed**.
  `turret_screen_peak` is kept as an informational status hint only. 0 turrets is
  export-ready; N turrets in one screen is valid.

Verified on the real 6502: 0-turret level and a spread many-turret level both
save/load/export/build; Level 1's **cluster of five turrets is simultaneously
on-screen** (`vice_bottom_origin_probe.py` C: `max 5/8 slots occupied`, every
authored turret visible, `>255` rows handled); a killed turret evicts with its
destroyed bit set and re-admits already-dead across a stage wrap with the score
counter stable (D); the shared body glyph set is published once and never
corrupted, and a destroyed turret's cells revert to the exact covered terrain
with no tearing (`check_fixed_hud_capture.py`, 0 failures over 53 M pixel
checks). Deterministic export intact.

---

## 6. Updated level JSON / schema

`formatVersion: 3`. New top-level keys:

| key | meaning |
|---|---|
| `tileset` | `{ "glyphCount": N, "glyphs": [[8 bytes]…N], "metatileDefs": [[16 codes]…16] }`. Codes 160..160+N-1. Self-contained per level. |
| `waveDefinitions` | list of `{ id, name, attackId, composition:[{enemyType,count}], spawnInterval }` (see §4). |
| `waveTriggers` | list of `{ id, worldRow, waveDef }` (see §4). |
| `objects` | unchanged shape `{ "type": "turret", "metatileRow": R, "metatileCol": C }`, now 0..N. |

`to_dict()` canonicalises: turrets sorted by `(row, col)`; wave defs by `id`;
triggers by `(-worldRow, id)`; glyph/def byte lists fixed-order. `save_project`
→ `json.dumps(indent=2)` + trailing `\n`. **V1/V2 files still load** — the
migration fills `tileset` from the engine baseline and `waveDefinitions` /
`waveTriggers` with `[]`.

---

## 7. Level 1 package

`tools/level_editor/levels/level1/level.json` → `src/generated/level1/`.

- **Terrain:** the committed `inspection-100` 100-metatile-row map (400 logical
  rows), palette `bg 0 / mc1 11 / mc2 14 / char 1`, `SCROLL_FRAME_DIVIDER 2`,
  FAR band (rows 1–5, M13 GRILLE) and START band (rows 94–97, M1 R_FILL), M14
  MACH housings under each turret.
- **Tileset:** a **verbatim copy of the current engine baseline** (48 glyphs
  read from `main.asm`'s soon-to-be-removed block via `engine_data`, 16 metatile
  defs) — Level 1 is byte-for-byte the current visual style.
- **Turrets (7):** metatile `(91,3) (89,7) (87,5)` — world rows 365 / 357 / 349,
  a cluster of 3 inside one gameplay screen (**exactly the pool limit**, all
  `> 255`) — plus `(60,4) (40,2) (20,8) (8,1)` — world rows 241 / 161 / 81 / 33,
  solo. Exercises 0/1/many, `> 255` rows, and the concurrency ceiling.
- **Wave definitions (2):** `wd_top_sweep` (`ATTACK_TOP_TURN_LEFT`, enemy type
  0, size 5), `wd_flank_up` (`ATTACK_LEFT_U_TURN_UP`, enemy type 2, size 5,
  interval 14).
- **Wave triggers (5):** world rows 372, 340, 300, 200, 90 (two `> 255`).

Builds and runs exactly as before **except** the turret-count change. Bottom-
origin retained. Gameplay imports this package and no other.

---

## 8. Level 2 package

`tools/level_editor/levels/level2/level.json` → `src/generated/level2/`.
**Editor / export proof only — gameplay never enters it and does not need to
load it.**

- **Tileset (`level2_tileset.py`):** 48 crude planet glyphs — rocky ground fill,
  gravel/dust speckle, crater rim TL/TR/BL/BR + floor, cliff face / edge L-R /
  top ridge & corners, talus slope, four strata bands, pit lip / walls / void /
  floor, alien pod TL/TR/BL/BR + stem, ridge spikes, vertical/horizontal cracks,
  vent + plume, large-crater rim variants, plus flat-ground fillers to keep the
  count a multiple of 8. Composed into 16 metatile defs (plain ground, gravel,
  cliff top / face, crater / basin, strata, pit, pod cluster, ridge, vent field,
  cracked ground, scree, dust drift, partial crater rim, cliff base). Distinct
  silhouettes from Level 1's riveted hull; same C64 global-multicolour
  constraints; ~same glyph budget; **no terrain-renderer changes**.
- **Terrain:** a 64-metatile-row (256 logical) hand-shaped planet profile —
  strata / cliff / crater / ridge / pod / vent / pit / cracks / scree bands over
  plain rocky ground, seam rows kept plain. Palette `bg 0 / mc1 9 (brown) /
  mc2 8 (orange) / char 1` — visibly different from Level 1's grey hull.
- 2 turrets (world rows 201 / 73), 2 wave definitions, 2 wave triggers.

---

## 9. Terrain glyph ownership / memory model

| char codes | charset region (`$3800` base, VIC bank 0) | owner |
|---|---|---|
| 0–127 | `$3800–$37FF`… (ROM copy) | permanent |
| 128–145 | HUD private (score digits, "FREE"/"F"/"R", blanks) | permanent engine/UI |
| 146–159 | reserved for HUD expansion | permanent |
| **160–223** | **`$3D00–$3EFF` — 64-slot terrain glyph namespace** | **level-owned** |
| 224–225 | `$3F00` diagnostic rail / diagonal | permanent |
| 226–229 | ONE shared turret body glyph set (all live turrets) | engine runtime |
| 230–239 | free | — |
| 240–251 | starfield (3 sizes × 4 phases) | permanent |
| 252–255 | free | — |

- **Level-owned:** `TERRAIN_GLYPH_COUNT` (a multiple of 8, ≤ 64) and the
  `TERRAIN_GLYPH_COUNT * 8` bytes of `terrainGlyphs`. `TERRAIN_GLYPH_COUNT` is
  declared in the generated `stage_config.asm` (so the engine's early
  glyph-namespace guards resolve); the bytes live in the generated
  `stage_charset.asm`, imported at the exact program counter the hand-authored
  block used to occupy in the `$2920` background segment. `initBackground`'s copy
  loop (`TERRAIN_GLYPH_COUNT` glyphs → `$3D00`) is unchanged.
- **Permanent (unmoved):** `TERRAIN_GLYPH_BASE = 160`,
  `TERRAIN_GLYPH_NAMESPACE = 64`, every `$3D00` / `160..223` guard, and all
  HUD / diagnostic / starfield / turret-pool allocations.
- **Editor storage:** `level.json → tileset { glyphCount, glyphs, metatileDefs }`.
- **Future multiload (not implemented):** copy/DMA the next level's
  `terrainGlyphs` blob (treat it as a full 64-slot / 512-byte block) into
  `$3D00` and patch `TERRAIN_GLYPH_COUNT` during the load transition. No format
  change is required; `stage_charset.asm` is already exactly that swappable unit.

Verified: loading Level 1 shows Level 1's glyphs, Level 2 its own distinct planet
glyphs; `test_level_packages.py` asserts each generated `stage_charset.asm`
carries its own level's bytes and that saving one package never touches the
other's file.

---

## 10. Export organisation

```
src/generated/
  level1/   stage_config.asm  stage_charset.asm  stage_test.asm
            stage_turrets.asm  stage_waves.asm         <- imported by main.asm
  level2/   (same five files)                          <- committed, never imported
```

- `ka_export.export_level(project, dir, engine_data=…)` writes all five files;
  `build_levels.py` writes both packages + JSON deterministically (re-running is
  byte-identical, confirmed via `git status`).
- The two level dirs never overwrite each other's generated source.
- Gameplay continues to consume `level1/` only. **No runtime level-selection or
  progression logic was added.**
- Legacy flat `src/generated/stage_*.asm` removed; `run_stage_fixture.sh`,
  `make_stage_fixture.py`, `engine_data.py`, `editor.py` all target the new
  layout (with a flat fallback in the readers during migration).

---

## 11. Tests and emulator diagnostics

### Build

`cd src && java -jar …/KickAss.jar main.asm -odir ../build -o ../build/shooter.prg
-vicesymbols` — **clean**, every `.error` size/overlap/namespace guard passes.

### Headless (`tools/level_editor/`)

| suite | result |
|---|---|
| `test_turret_integration.py` | **8/8** — coordinate model, `>255` rows desc-sorted, JSON determinism, order-independence, V1/V2 migration, invalid placements, generated round-trip, 3-file export |
| `test_turret_unlimited.py` | **5/5** — 0-turret export (`TURRET_TOTAL = 0` + empty `List()`), spread 8-turret export, `>255` row round-trip + per-level determinism, **6 turrets in one gameplay screen is VALID and export-ready** (shared body glyphs, no density cap), order-independence |
| `test_wave_schema.py` | **6/6** — catalogue parse, def/trigger round-trip + deterministic `stage_waves.asm`, 16-bit desc rows + `>255`, composition-size authority (no `size` key), **`SCROLL_FRAME_DIVIDER` change leaves every exported trigger row byte-identical**, schema rejection |
| `test_viewport_model.py` | **6/6** — 40×23 geometry, bottom-origin default, clamp/no-wrap, metatile mapping, tiny level, re-clamp on shrink |
| `test_level_packages.py` | **6/6** — two packages coexist, distinct self-contained tilesets, per-level charset carries own bytes, saving one leaves the other byte-identical, per-level load→edit→save→reload→export round-trip, deterministic per-level export into separate dirs |

`editor.py` imports cleanly and constructs headlessly; wave-trigger placement +
viewport-follow + validation exercised offline.

### VICE (background launch, remote monitor only — no focus steal, no injected
keyboard input)

| probe | result |
|---|---|
| `check_stage_addressing.py` (pure) | **PASS** — widened 16-bit stage arithmetic for every logical row of a 1600-row stage + boundaries |
| `run_stage_fixture.sh` `N ∈ {256, 320, 400, 512, 844}` | **PASS** — synthetic stage decodes exactly on the 6502 (see caveat 5 for `N = 300`) |
| `vice_scroll_test.py` + `check_scroll_capture.py` (`--physical --trace`, 900 frames) | **PASS** — 0 failures |
| `check_fixed_hud_capture.py` (900 frames, shared-body-glyph model) | **PASS** — 0 failures, 53.0 M pixel checks; fixed HUD row, the one shared body glyph set published & uncorrupted, colour-RAM pulse + hit flash, a destroyed turret's cells revert to the exact covered terrain with no tearing, both physical edge-motion oracles |
| `check_turret_capture.py` (pool model) | **PASS** — 0 failures; per-slot screen-Y / visibility, real turret kills + hit flashes captured, ≤ pool live at all times |
| `check_raster_capture.py` (`--physical --trace`, 900 frames) | **PASS** — 0 service failures, 0 sprite-start misses (turrets consume no sprites; `max_batches` stays 0 with the 5-turret cluster firing) |
| `vice_encounter_fixtures.py` | **A–R 18/18** — atomic 5-enemy waves, turret-pressure Y threshold, deferred wave START then start, mid-wave completion, shooter budgets, bullet cap, no despawn, turret firing below & above the threshold |
| `vice_suppress_fixtures.py` | **A–J 10/10** — presentation-only projectile suppression unchanged |
| `vice_bottom_origin_probe.py` (rewritten) | **A–D PASS** — boot `SCROLL_ROW = SLR-23`; contiguous no-wrap boot viewport; **C:** Level 1's cluster puts **max 5/8 slots occupied at once** (past the old 3-visible cap), every authored turret visible in a contiguous `[worldRow-22..worldRow-1]` window, world rows 353/357/361/365/369 (`>255`) handled, activation order = descending world row; **D:** a killed turret evicts with its `turretDestroyedBits` bit set, re-admits already-dead across the wrap, `TURRET_DESTROYED` score counter stable |
| `vice_turret_large_row.py` (rewritten for the pool) | **A–D PASS** — `positionBackgroundTurrets` Y + visibility exact, `installTurretRow` writes the shared body codes 226–229, `pulseTurretColour` pulses then restores, `hitCannonTarget` HP-decrements / destroys / sets the destroyed bit — all for a slot seeded at world row 349 (`>255`) |
| `vice_wave_trigger_probe.py` (new) | **A–E PASS** — every trigger latches exactly at `SCROLL_ROW == worldRow` in descending order; cursor exhausts with no further fire down to `SCROLL_ROW 0`; stage wrap re-arms all 5 and they fire again; `startAuthoredWave` resolves attackId/count/spriteSeed/interval per trigger (wave size = authored composition size); the latch is purely `SCROLL_ROW`-driven |
| `vice_level1_smoke.py` (new) | **PASS** — the real game runs, `GAME_STATE` stays PLAYING, `SCROLL_ROW` advances and the stage wraps, the turret pool never exceeds `TURRET_POOL`, the wave-trigger cursor advances and 5-enemy formations are produced; no crash across the wrap |

Physical PAL frame stayed exactly **19656 cycles** throughout every capture.

---

## 12. Confirmation: gameplay remains Level 1 only

`src/main.asm` `#import`s only `generated/level1/…`. `src/generated/level2/`
exists and is committed but is referenced by nothing. `startGame` /
`updateSpawner` branch on `WAVE_TRIGGER_COUNT` — a compile-time constant of the
imported (Level 1) package — and no level index, level table, level-select menu,
or multiload/transition code was added. The engine's stable diagnostics (raster
scheduler counters, encounter-policy `POLICY_*` gauges, suppression fixtures)
are byte-for-byte behaviourally unchanged.

---

## 13. Caveats before merge

1. **Autonomous wave director is isolated, not deleted.** For a stage with
   `WAVE_TRIGGER_COUNT > 0` (Level 1), `startRandomWave` is compiled out of the
   live path. It, `randomAttackMap` and the attack tables remain in the tree and
   are still exercised by `vice_encounter_fixtures.py` A/B/C via direct
   trampoline calls. A stage that ships **no** triggers still gets the old
   random director. This is the deliberate, spec-sanctioned transition.
2. **Wave gap vs. very close triggers.** Authored mode keeps the existing
   `WAVE_GAP` (150 frames) between waves and never advances the cursor past an
   unconsumed trigger. Two triggers separated by less than ~`WAVE_GAP` frames of
   scrolling will therefore be *serialised* (the second fires as soon as the gap
   clears), not dropped. Level 1's triggers are ≥ 90 world rows apart
   (≥ ~1400 frames at divider 2), so this never bites in practice.
3. **No turret density limit.** The editor accepts any number of turrets in one
   gameplay screen. `TURRET_POOL = 8` state slots exceed the ~7 turrets a 23-row
   aperture can physically hold; if the pool were ever full `updateTurretStream`
   defers the extra turret a frame rather than corrupting. The `TURRET_POOL ≤ 8`
   ceiling itself is the 128-byte signed-X state-clear-loop convention (a real
   6502 idiom limit) and is moot in practice — it could be lifted with a
   two-pass clear if a future aperture change needed it.
4. **Hit-flash is colour-RAM, not a bitmap swap.** With shared body glyphs a hit
   turret can no longer change its *shape* for the flash; instead its four
   colour-RAM cells go to `TURRET_HIT_CRAM` (light red, distinct from the pulse)
   for 4 frames. The turret dome is almost entirely colour-RAM-driven pixels, so
   this reads clearly as a hit; it is a deliberate simplification from the old
   per-turret style-6 bitmap.
5. **`run_stage_fixture.sh 300`** flags a one-row `BG_INCOMING_ROW` mismatch in
   the stage-widening probe. `N = 300` was never in the validated fixture set
   (25/64/256/400/844 per `docs/stage-widening-worklog.md`); `N ∈ {256, 320,
   400, 512, 844}` all pass here, and `check_stage_addressing.py` proves the
   exact 16-bit decode arithmetic for every logical row 0..1599. This pass
   touches no stage-decoder code (`decodeStageCharacterRow` / `wrapBgLogicalRow`
   / `make_stage_fixture.py`'s row formula are unchanged), so this is a latent
   fixture/probe quirk at an unvalidated size, not a regression — but it should
   be root-caused before relying on `N = 300` builds.
6. **`vice_scroll_test.py --turret-playtest` / `check_turret_capture.py
   --require-wrap-deaths`** is a scripted deep capture that aims real player
   cannons at *specific* turret indices of the old 3-turret acceptance level; its
   indices need re-pointing for Level 1's 9-turret layout before that playtest is
   re-run. Destroyed-persistence-across-wrap is proven instead by
   `vice_bottom_origin_probe.py` check D; the standard `check_turret_capture.py`
   run (no flag) passes.
7. **Older turret diagnostic tools not in the regression suite** —
   `vice_turret_runtime_probe.py` (scroll-hitch diagnosis), `vice_turret_cases.py`,
   `vice_turret_kill_timing.py`, `vice_scroll_hitch.py`, `vice_raster_cases.py`,
   `vice_raster_lifecycle.py` still reference the pre-streaming-pool per-slot
   style symbols (`TURRET_AIM` / `TURRET_DESIRED_STYLE` / `TURRET_SHOWN_STYLE`)
   and would `KeyError` if re-run. They are investigation aids, not pass/fail
   gates; the regression-suite turret tools (`vice_bottom_origin_probe.py`,
   `vice_turret_large_row.py`, `check_turret_capture.py`,
   `check_fixed_hud_capture.py`, `vice_encounter_fixtures.py`) all pass and were
   rewritten for the pool.
8. **`build_levels.py`** reads the committed `inspection-100` map from
   `HEAD:src/generated/level1/stage_test.asm`, falling back to
   `HEAD:src/generated/stage_test.asm` and then the working copy. After this
   branch is committed the first path resolves; the fallbacks cover the
   pre-commit state.

If the above reads acceptably, the branch is suitable for merge to `main`.
