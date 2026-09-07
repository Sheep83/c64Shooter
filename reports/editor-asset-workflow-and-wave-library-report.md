# Level Editor Asset Workflow & Wave Library — implementation report

Editor/tooling pass. No engine, memory-layout, raster, multiplexer, BUILD/LIVE,
coarse-scroll, collision or PAL-timing change. No commit, no push.

---

## 1. Starting branch and HEAD

| | |
| --- | --- |
| Branch | `terrain-asset-workshop` |
| HEAD | `3a72c13ab50554b7e90ac591872dfa569a350bd0` — *"Tile editor and tileset import added to stage editor"* |
| Working tree at start | dirty from earlier terrain/editor passes (Tasks 1–3). This pass is additive on top. |
| Project format | V5 (unchanged — see §10) |

The separate HUD/RSEL/display-geometry investigation was **not** touched. Runtime
geometry (RSEL=0, HUD row 0 + terrain rows 1..23, 23-logical-row aperture,
bottom-origin) is treated as fixed input; the only viewport change here is the
editor-side outline-only overlay (§6), whose geometry is unchanged.

---

## 2. Complete changed-file list

### Modified (tracked)

| File | Change |
| --- | --- |
| `tools/level_editor/project.py` | + `unique_metatile_name()`, `duplicate_metatile()`; `import re`. No schema/format change. |
| `tools/level_editor/editor.py` | Metatile toolbar → **Edit Selected / Duplicate / New Tile / Import PNG… / Save to Repo / Rename… / Repository… / Delete / Trim unused**. New methods `_metatile_duplicate_selected`, `_metatile_save_to_repository`. Terrain Repository dialog gains **Edit asset…**, **Import from Project…**, **Recover generated set** (+ `_import_project_metatiles_dialog`). Wave panel → **New / Duplicate / Delete** + **Add from Library… / Save to Library**, label *Apply to def* → *Apply changes*; new methods `_duplicate_wave_def`, `_wave_def_save_to_library`, `_wave_library_dialog`. Global `WaveRepository` loaded in `__init__`. Viewport overlay → outline-only (§6). |
| `tools/level_editor/terrain_repository/repository.json` | +31 generated native terrain assets appended as `asset_0010`..`asset_0040` (§5). The 9 pre-existing user assets `asset_0001`..`asset_0009` are byte-for-byte unchanged. |
| `tools/level_editor/test_editor_workshop_gui.py` | Fixed a stale glyph-count bound (`<= 64` → `<= TERRAIN_GLYPH_NAMESPACE` = 128). Pre-existing latent failure, unrelated to this pass — see §13. |

### New (untracked)

| File | Purpose |
| --- | --- |
| `tools/level_editor/wave_repository.py` | Global **Wave Definition Repository** (`WaveRepository`), schema v1, deterministic JSON, snapshot semantics (§7). |
| `tools/level_editor/wave_repository/repository.json` | The empty global wave library (`{"definitions": [], "schemaVersion": 1}`). |
| `tools/level_editor/recover_generated_terrain.py` | `recover_generated_set(repo)` + CLI: copy the authoritative `native_terrain_tiles.py` output into the Terrain Asset Repository, fingerprint-deduped (§5). |
| `tools/level_editor/test_metatile_edit.py` | Edit-selected metatile (used/unused, IDs stable, whole-level repack, over-budget safe, save/reload, repo source untouched). |
| `tools/level_editor/test_metatile_duplicate.py` | Duplicate metatile (deep copy, `_COPY`/`_COPY_2` naming, IDs/map stable, independence, 64 cap, budget, save/reload). |
| `tools/level_editor/test_metatile_save_to_repository.py` | Promote level metatile → terrain repo (exact snapshot, two-way independence, provenance, name clash, determinism, existing preserved). |
| `tools/level_editor/test_import_from_project.py` | Import from another V4/V5 project (subset + select-all, used/unused, dup names, malformed file, source untouched). |
| `tools/level_editor/test_generated_set_recovery.py` | Generated-set recovery (authoritative generator, count 31, exact pixels, user assets preserved, idempotent, partial). |
| `tools/level_editor/test_repository_editing.py` | Edit a repository asset in place (same id, mirror/flip round-trip, determinism, level snapshots unaffected). |
| `tools/level_editor/test_wave_repository.py` | Global wave library (save→global, add→level, two-way snapshot independence, rename/delete safe, duplicate, determinism, reload, no `worldRow`). |
| `tools/level_editor/test_editor_asset_workflow_gui.py` | Headless Tk smoke: outline-only viewport + activation edge + geometry/bottom-origin/no-wrap/drag; Duplicate; Save to Repo; repo-dialog import + recover; wave library wired. |

No file under `src/` was modified by this pass. (`src/main.asm`, `src/generated/**`
and other `M`/`??` entries in `git status` are the uncommitted output of the
earlier Tasks 1–3 and predate this work.)

---

## 3. Terrain editing / duplicate / repository UX

The **Level metatile set** panel toolbar now reads, left-to-right / top-to-bottom:

```
Edit Selected   Duplicate   New Tile
Import PNG…      Save to Repo   Rename…
Repository…      Delete        Trim unused
```

- **Edit Selected** — opens the selected `levelMetatileSet` entry in the existing
  native 16×32 editor (`WorkshopDialog` / `NativeMetatileEditor`: paint, undo/redo,
  Mirror H, Flip V, palette preview, live glyph-cost). Save replaces that entry's
  native pixels, keeps the metatile ID, keeps `source`/provenance, then runs the
  **whole-level** pack/dedupe/budget path (never a single-glyph patch — glyphs
  are shared across metatiles). Editing a map-used metatile is allowed; every
  cell referencing that ID immediately shows the new artwork. An edit that would
  exceed the 128-glyph terrain budget is rejected with a clear message and the
  project is left valid (the previous entry is restored and repacked).
- **Duplicate** (`_metatile_duplicate_selected` → `project.duplicate_metatile`) —
  deep-copies the selected metatile to the next free ID with a unique
  `NAME_COPY` / `NAME_COPY_2` / … name (an already-suffixed name keeps its stem).
  Existing IDs and every painted map cell are untouched; the copy is selected and
  fully independent (editing it never mutates the source). Repacks through the
  normal path; respects the 64-metatile vocabulary limit and the 128-glyph
  budget. Undoable. Supports *select wall → Duplicate → Edit → Mirror → tweak →
  Rename*.
- **New Tile** — unchanged: a blank native tile to draw from scratch.
- **Save to Repo** (`_metatile_save_to_repository`) — snapshots the selected
  level metatile into `tools/level_editor/terrain_repository/repository.json` as a
  new asset (`repo.add_asset`), asking for a name (defaulting to the metatile
  name). A name clash is not a silent overwrite: a new, independent `asset_NNNN`
  id is created after a confirm. Provenance records `promoted from level
  '<name>' metatile <i>`; any original-source `sourcePack` from the level entry
  is carried into `licenceNote`. Repository copy and level copy are independent
  thereafter in both directions.

### Terrain Asset Repository dialog (Repository…)

Existing: list assets (with per-level usage count), **Add snapshot to level**,
**Rename…**, **Delete** (with the "level snapshots are independent" warning).
Added:

- **Edit asset…** — opens the selected repository asset in the native editor
  (`WorkshopDialog`); Save writes back via `repo.update_asset(id, name=…,
  native_pixels=…)` so the asset's **id is preserved**; deterministic re-save.
  Because levels hold independent snapshots, editing the asset never changes a
  level that copied it earlier. This makes the repository a real reusable
  graphics library, not just a storage/import list.
- **Import from Project…** — see §4.
- **Recover generated set** — see §5.

---

## 4. How "Import from Project" works

`Repository… → Import from Project…`:

1. File picker for a V4 or V5 editor project JSON (`levels/*/level.json` or any
   `*.json`).
2. `project.load_project(path, default_tileset=<engine baseline>)` — the **existing
   migration/loading code** (V1→…→V5), so V4 and V5 both load without ad-hoc
   parsing. `ensure_level_metatile_set()` derives the native set for older files.
3. The source project's `levelMetatileSet` is listed by index + name in a
   multi-select list with **Select All**.
4. **Import selected** copies each chosen entry's native 16×32 pixels *exactly*
   into the Terrain Asset Repository via `repo.add_asset(name, pixels,
   provenance={"sourcePack": "imported from project '<name>' metatile <i> …"},
   tags=["imported"])`, then one `repo.save()`.

Guarantees (test-covered):

- Presence in `levelMetatileSet` is sufficient — a metatile need **not** be
  painted on the source map.
- Native pixel data is preserved exactly; no packed runtime glyph codes become
  repository identity (assets store logical 0..3 pixels only).
- Duplicate names → new independent `asset_NNNN` ids, never an overwrite.
- A malformed / unsupported project file raises a `ProjectValidationError`,
  shows a clear error, and leaves the repository **byte-identical**.
- The source project file is never written.

---

## 5. How the original generated terrain set was recovered — and the count

`tools/level_editor/recover_generated_terrain.py` (`recover_generated_set(repo)`,
also wired to **Repository… → Recover generated set**).

- **Authoritative source:** `tools/level_editor/native_terrain_tiles.py` —
  `native_terrain_tiles.metatiles()`, the deterministic generator that authors
  the bas-relief sci-fi vocabulary directly in native 16×32 logical-multicolour
  form from reusable 4×8 cells. No artwork is reconstructed from descriptions.
- **Count recovered: 31.** `native_terrain_tiles.names()` = 31 metatiles:
  `DECK_PLAIN, DECK_RIVET, DECK_SCUFFED, DECK_PANEL, PLATE_RAISED, PLATE_RECESSED,
  ARMOUR_PLATE, HATCH, SEAM_HORIZ, SEAM_VERT, SEAM_CROSS, WALL_LEFT, WALL_RIGHT,
  WALL_TOP, WALL_BOTTOM, CORNER_TL, CORNER_BR, VENT_BANK, GRILLE_BANK, RIB_FIELD,
  MACHINE_A, MACHINE_B, CONDUIT_H, CONDUIT_V, CONDUIT_BEND, HAZARD_BAND, BRACE_X,
  PIT_MOUTH, GAP, CORE, DAMAGED`.
- **Conflict / duplicate handling:** a deterministic fingerprint = the exact
  16×32 logical pixel grid. A generated metatile whose artwork is already present
  in the repository (any id) is **skipped**, not duplicated. The user's existing
  assets are never overwritten or removed.
- **Applied to the committed repository:** the 9 pre-existing user assets
  (`asset_0001`..`asset_0009`: *slab, quad-slab, pyr-*, wedge-*, vent-1*) had no
  fingerprint collision, so **all 31** were added as `asset_0010`..`asset_0040`,
  tagged `["generated", "sci-fi-terrain"]` with provenance
  `sourcePack = "19656 generated native terrain set (native_terrain_tiles.py)"`.
  Repository: **9 → 40 assets.** A second run adds 0 (all 31 skipped as
  identical). Serialisation stays deterministic, no timestamps.
- The recovered entries are ordinary repository assets — editable, importable,
  promotable like any other.

---

## 6. Viewport overlay change

`editor.py : _draw_viewport_overlay`. Before: a stipple-filled blue rectangle
tinting the whole aperture plus two edge lines. After:

- **Transparent interior** — no fill, no stipple, no tint over the terrain.
- **Blue outline only** (`VIEWPORT_EDGE`, width 2) as a rectangle around the
  exact gameplay aperture.
- The **yellow top/activation edge** (`VIEWPORT_ACTIVATION`, the
  `SCROLL_ROW == worldRow` wave-trigger line) and its small row-range label are
  retained.
- Geometry is byte-identical: `y0 = top*8`, `y1 = (top + VIEWPORT_ROWS)*8`,
  `VIEWPORT_ROWS = 23`. Bottom-origin default, no-wrap clamping, scale/drag/Up-Down
  nudge, and all viewport/world-row calculations are unchanged (verified by
  `test_viewport_model.py` + `test_editor_asset_workflow_gui.py`).

---

## 7. Global Wave Definition Repository — schema and location

**Location:** `tools/level_editor/wave_repository/repository.json`
**Module:** `tools/level_editor/wave_repository.py` (`WaveRepository`, analogous to
`TerrainRepository`).

```jsonc
{
  "schemaVersion": 1,
  "definitions": [                       // sorted by id
    {
      "id": "wave_0001",                 // stable, unique, sortable (wave_NNNN)
      "name": "Alpha sweep",
      "attackId": 0,                     // engine ATTACK_* catalogue id (0..11)
      "composition": [ { "enemyType": 0, "count": 5 } ],
      "spawnInterval": null,             // null => attack-table default; else 1..255
      "notes": "",
      "tags": ["intro"]
    }
  ]
}
```

- Holds **only** the reusable "what": name, attack id/reference, composition,
  enemy count (via composition), spawn interval, notes, tags. It **rejects**
  `worldRow` — trigger placement is level-local, never global. It does not invent
  engine `ATTACK_*` ids.
- Deterministic: `json.dumps(sort_keys=True, indent=2)` + trailing newline,
  definitions sorted by id, **no timestamps**. Re-saving an unchanged library is
  a no-op diff.
- `schemaVersion` is explicit; an unknown version is rejected on load.

### Editor operations (Waves panel)

```
Wave definitions (reusable)
[ listbox ]
New   Duplicate   Delete
Add from Library…   Save to Library
  Name / Formation / Enemy type / Count / Spawn interval   [ Apply changes ]
```

- **New** — a fresh local definition (unchanged `_add_wave_def`).
- **Duplicate** (`_duplicate_wave_def`) — deep-copies the selected **local**
  definition to a fresh local id, name `"… copy"`; triggers still reference the
  original; the copy is independent.
- **Delete** — unchanged (refused while a trigger references it).
- **Apply changes** — edits the selected local definition (renamed from
  *Apply to def* for clarity: this edits the *local* copy).
- **Save to Library** (`_wave_def_save_to_library`) — snapshots the selected
  local definition into the global library
  (`wave_repository.add_from_level_definition`), asking for a library name;
  strips the local id and never stores `worldRow`.
- **Add from Library…** (`_wave_library_dialog`) — a manager listing global
  definitions with **Add to level (snapshot)** (copies into
  `project.waveDefinitions` under a fresh level-local `wd<N>` id), **Rename…**,
  and **Delete** (with the "levels keep their own local copy" confirm).

---

## 8. Exact snapshot semantics

```
Terrain:   repo asset  --repo.snapshot()-->  level.levelMetatileSet[i]        (level owns the pixels)
Waves:     library def  --wave_repo.snapshot(local_id=…)-->  level.waveDefinitions[i]   --ref--  triggers
```

For **both** repositories, copying is a one-way deep copy:

- After a copy, the level holds the **authoritative** data. Later
  rename / edit / delete of the source (repository asset or library definition)
  **cannot** change the level, and the level cannot build-fail because of it.
- Editing the level copy **cannot** mutate the source.
- No live link is stored. Terrain snapshots keep a `source.repositoryAssetId`
  breadcrumb for provenance/usage display only. Wave snapshots keep **only** the
  fields the level's own wave-definition schema already stores, so a
  library-derived definition is shape-identical to a hand-authored one and the
  level stays fully self-contained.
- Level-local wave definitions still persist inside `level.json` exactly as
  before; triggers continue to reference local definition ids; library changes
  never touch a project's triggers.

Verified in both directions by `test_metatile_save_to_repository.py`,
`test_repository_editing.py`, `test_wave_repository.py`,
`test_editor_asset_workflow_gui.py`.

---

## 9. Project-format / schema changes and migrations

**None.** Project format stays **V5**. `LevelProject`, `to_dict()`,
`canonical_*`, `validate_project`, all migrations and `save_project` are
unchanged. No new keys in `level.json`. The two repositories are **separate**
documents outside any level package:

- Terrain: `terrain_repository/repository.json`, `schemaVersion 1` (existing).
- Wave: `wave_repository/repository.json`, `schemaVersion 1` (new, this pass).

`project.duplicate_metatile` produces an ordinary `levelMetatileSet` entry
(`canonical_metatile_set_entry`), carrying the source `source` block verbatim.

---

## 10. Tests added / updated

Added (plain-assert scripts, house style, run via `python3 <file>`):
`test_metatile_edit.py`, `test_metatile_duplicate.py`,
`test_metatile_save_to_repository.py`, `test_import_from_project.py`,
`test_generated_set_recovery.py`, `test_repository_editing.py`,
`test_wave_repository.py`, `test_editor_asset_workflow_gui.py` (headless Tk,
self-skips with exit 0 when no display).

Updated: `test_editor_workshop_gui.py` — stale `len(glyphs) <= 64` bound →
`<= TERRAIN_GLYPH_NAMESPACE` (128); imports `METATILE_CAPACITY`,
`TERRAIN_GLYPH_NAMESPACE`.

Coverage vs the task's section-11 checklist: level-metatile edit (unused / used /
IDs stable / pixels change / whole-level repack / over-budget safe-reject /
save-reload); duplicate (deep copy / unique name / source unaffected / 64 limit /
save-reload / budget); save-to-repository (exact snapshot / two-way independence /
provenance / dup handling / deterministic / existing preserved); import-from-project
(V4 / V5 / used+unused / subset / Select All / malformed / dup / source untouched);
generated recovery (authoritative generator / count 31 / exact deterministic
output / no loss / idempotent / partial); repository editing (paint / mirror /
flip / persistence / level snapshots unchanged); viewport (no fill / blue outline
/ yellow edge / 23-row geometry / bottom-origin / no-wrap / drag); global wave
repo (save→global / add→level / two-way independence / rename-delete safe /
duplicate / deterministic / reload / trigger refs / no `worldRow`).

---

## 11. Full test results

### Editor suite — `python3 tools/level_editor/test_*.py` (21 files)

```
test_colour_conversion.py             All 7 colour-conversion checks passed.
test_editor_asset_workflow_gui.py     All 6 editor asset-workflow GUI smoke checks passed.
test_editor_workshop_gui.py           All 9 editor-workshop GUI smoke checks passed.
test_generated_set_recovery.py        All 5 generated-set-recovery checks passed.
test_import_from_project.py           All 4 import-from-project checks passed.
test_level_packages.py                All 6 level-package checks passed.
test_metatile_capacity.py             All 7 metatile-capacity / migration checks passed.
test_metatile_delete.py               All 7 metatile-delete checks passed.
test_metatile_duplicate.py            All 7 metatile-duplicate checks passed.
test_metatile_edit.py                 All 6 metatile-edit checks passed.
test_metatile_save_to_repository.py   All 4 save-to-repository checks passed.
test_native_metatile.py               All 7 native-metatile checks passed.
test_native_terrain_tiles.py          All 8 native-terrain-tiles checks passed.
test_repository_editing.py            All 4 repository-editing checks passed.
test_spritesheet.py                   All 6 spritesheet checks passed.
test_terrain_repository.py            All 6 terrain-repository checks passed.
test_turret_integration.py            All 8 turret-integration checks passed. (TURRET_POOL=8, MAX_TURRETS=255)
test_turret_unlimited.py              All 5 unlimited-turret checks passed.
test_viewport_model.py                All 6 viewport-model checks passed.
test_wave_repository.py               All 7 wave-repository checks passed.
test_wave_schema.py                   All 6 wave-schema checks passed.

SUITE: 21 passed, 0 failed   (128 individual checks)
```

### Engine / export regression

```
tools/level_editor/acceptance_terrain_workshop.py   PASS (8 steps)
tools/check_terrain_glyph_budget.py                  PASS (full 128-glyph build; all reserved-region guards hold)
tools/check_stage_addressing.py                      PASS (widened stage arithmetic vs reference)
tools/check_metatile_def_lookup.py                   PASS (2308 arithmetic checks; 64-entry / 1024-byte def table)
export level1 + level2 via ka_export.export_level    deterministic (re-export byte-identical); both validate;
                                                     export_readiness_errors == [] for both
```

VICE-capture regressions (`check_scroll_capture`, `check_fixed_hud_capture`,
`check_raster_capture`, `check_turret_capture`, encounter fixtures) were **not**
run — they exercise the running engine PRG, which this editor-only pass does not
change; no engine/generated source was modified.

---

## 12. KickAssembler / VICE results

**KickAssembler:**
`java -jar …/KickAss.jar src/main.asm -odir build -o build/shooter.prg -vicesymbols`
→ clean build, no errors, all `.error` guards pass; `build/shooter.prg`,
`build/main.vs`, `main.sym` written. Memory map unchanged
(`$6000-$634f`, `$6600-$6c39`, `$8800-$8fdf` …). This only confirms the tree
still assembles — no engine or generated `.asm` was touched by this pass.

**VICE:** not launched. No focus-grabbing `open -a` was used anywhere (§13).

---

## 13. Confirmation: no focus theft / no commit / no push

- **VICE focus:** no VICE automation was run in this pass. No `open -a`. The one
  emulator-adjacent action (KickAssembler) is a headless `java -jar` build.
- **No commit / no push:** no `git commit`, `git push`, `git add`, tag or branch
  op. `HEAD` is still `3a72c13`. All changes remain in the working tree.
- **Pre-existing failure fixed as housekeeping:** `test_editor_workshop_gui.py`
  line 119 asserted `len(glyphs) <= 64` — a stale bound from before the terrain
  glyph namespace grew to 128. It failed on `3a72c13` + the Task-1–3 working
  tree (the committed generated Level 1 now packs 72 glyphs) *before* this pass.
  Corrected to `<= TERRAIN_GLYPH_NAMESPACE`. No feature behaviour changed.

---

## 14. Known limitations / follow-up

- **`build_levels.py build_level1` remains the known canonical-JSON wart** — see
  §15. Not addressed (out of scope; nothing here required it).
- Exporting `levels/level1/level.json` does **not** reproduce the committed
  `src/generated/level1/*.asm` (the generated tree is the separately-tested
  105-row level; `level.json` is the 100-row / 31-metatile authored source).
  Pre-existing drift, untouched here. `levels/level2/` round-trips exactly.
- **Import from Project** and the repository/library manager dialogs show name +
  index lists, not rendered thumbnails, for the source metatiles. Functional,
  not polished (as directed).
- **Edit asset…** uses `WorkshopDialog` with `cost_fn=None` (a repository asset
  has no single owning level, so there is no live per-level glyph budget to show).
- The global wave library manager offers Add-to-level / Rename / Delete;
  `Update from Library` (re-sync a level copy) is deliberately **not** provided —
  snapshot semantics are the baseline and no live link exists.
- `wave_repository/repository.json` ships empty; it fills as the user runs
  *Save to Library*.
- Headless GUI smokes stub `simpledialog`/`messagebox` so modal actions can run
  without a display; interactive behaviour of those dialogs is exercised by hand
  only.

---

## 15. `build_levels.py build_level1` — canonical-JSON wart status

**Still outstanding, unchanged.** `build_levels.build_level1()` reconstructs
Level 1 from `git show HEAD:src/generated/level1/stage_test.asm` plus hard-coded
Python (`L1_PALETTE`, `L1_TURRETS`, `L1_WAVE_DEFS`, `L1_WAVE_TRIGGERS`,
`L1_TOP_BAND` / `L1_BOTTOM_BAND` band overwrites) rather than round-tripping the
canonical `tools/level_editor/levels/level1/level.json`. This pass did not touch
`build_levels.py` and did not need to; it is documented here as remaining
follow-up work.
