# Terrain Asset Workshop — Final Usability + Memory-Safety Pass

Branch `terrain-asset-workshop` · starting HEAD `3a72c13` ("Tile editor and
tileset import added to stage editor") · **uncommitted**. This report is a
deliverable; it is also printed to the terminal. Companion:
`docs/level-editor-worklog.md` (new milestone).

Five bounded amendments only — persistent PNG import session, native
mirror/flip, individual repository rename/delete, correct VIC-II 2:1 preview,
and the memory-layout build failure for a full-budget level. No system redesign.
No commit, no push.

---

## 1. Files changed

### Engine
| file | change |
|---|---|
| `src/main.asm` | `#import "generated/level1/stage_charset.asm"` (variable-size `terrainGlyphs`) moved out of the `$2920` background-control code segment into its own fixed segment `* = $5c00`; new guards `.if (* > $5c00)`, `.if ($5c00 + TERRAIN_GLYPH_NAMESPACE*8 > $6000)`, `.if (TERRAIN_CHARSET_END > $6000)`; clarifying comments on `BACKGROUND_CONTROL_END` and the `initBackground` copy unroll |

### Generated (re-sync to the authored `level.json` — pre-existing inconsistency, see §8)
| file | change |
|---|---|
| `src/generated/level1/stage_config.asm` | `STAGE_METATILE_COUNT 17 → 16` |
| `src/generated/level1/stage_waves.asm` | `WAVE_TRIGGER_COUNT 0 → 5` + the resolved trigger lists |
| `src/generated/level1/stage_test.asm` | 17 → 16 metatile defs (matches `level.json`) |
| `src/generated/level1/stage_charset.asm` | glyph bytes re-exported from `level.json` `tileset` (still 48 glyphs) |

### Editor
| file | change |
|---|---|
| `tools/level_editor/workshop_ui.py` | `NativeMetatileEditor`: 2:1 logical-pixel display (`zx = 2*unit`, `zy = unit`), corrected hit-test/paint/guides; `mirror_horizontal()` / `flip_vertical()` (one undoable edit each); Mirror/Flip/Undo/Redo toolbar; `on_change` also fires on undo/redo/transform. `WorkshopDialog`: `on_back` → "◄ Back to Source" button; `Ctrl+M` / `Ctrl+F` shortcuts. `ImportDialog`: accepts an already-sliced `sheet=` + `select_index=`; `show()` / `hide()` (withdraw, not destroy); `on_pick(rgb, prov, dialog)`; selected-tile highlight; sheet name in the info line |
| `tools/level_editor/editor.py` | persistent `self._import_dialog` session (`_metatile_import_png` reuses/re-shows it; `_import_session_pick` hides it and opens the Workshop with `on_back=_reopen_import_session`; `_close_import_session` on window-close and `_on_close`); `_metatile_from_repo` rebuilt as a repository manager with **Add snapshot / Rename… / Delete** (delete confirmed; both persist immediately; neither touches level snapshots); "From repo…" button → "Repository…" |
| `tools/level_editor/test_editor_workshop_gui.py` | extended 6 → 9 checks; boots against the committed count (not hard-coded 16); uses a temp repository |
| `tools/level_editor/test_metatile_capacity.py` | migration fixture uses the first 16 baseline defs (was assuming a 16-def engine baseline) |
| `tools/make_stage_fixture.py` | `real_metatile_defs()` accepts 1..64 committed defs (was asserting exactly 16); `metatile_defs(D)` slices/pads from the real count |
| `tools/vice_bottom_origin_probe.py` | reads `metatileDefs` by its real byte span (`METATILE_DEFS_END - metatileDefs`), not a fixed 256 |
| `tools/check_terrain_glyph_budget.py` | **new** — assembles a full 64-glyph level, asserts every reserved-region guard, restores originals |

`tools/level_editor/terrain_repository/repository.json` — **not modified**
(tests use a temp path).

---

## 2. Persistent PNG import-session design and workflow

**State.** `LevelEditor._import_dialog` holds a single live `ImportDialog`,
withdrawn (not destroyed) between uses. The dialog owns:

- `_path` — source PNG path
- `sheet` — the decoded + sliced `spritesheet.SpriteSheet` (`rows` = the full
  decoded RGB image; `tile_w/tile_h`, `cols_count/rows_count`, cached tiles)
- `last_index` — the last picked source cell
- `tw`/`th` Tk vars — the import geometry

Nothing is written to any level/project file. Provenance handed to the
Workshop still carries an optional `localSourcePath` string (descriptive
metadata only; correctness never depends on it), unchanged from the prior pass.

**Workflow.**

```
Import PNG…            -> ImportDialog opens (or re-shows the existing session)
choose PNG once        -> slice_sheet(path, tw, th); thumbnail grid
click source tile A    -> ImportDialog._pick(A): records last_index=A,
                          calls on_pick(tileA, prov, dialog)
                          editor: dialog.hide(); convert A -> native 16x32;
                          open WorkshopDialog(on_back=_reopen_import_session)
convert / edit A       -> native editor (mirror/flip/paint/undo)
Save to level / repo   -> WorkshopDialog closes
◄ Back to Source       -> _reopen_import_session(): dialog.show()   (same object,
                          NO re-read, tile A highlighted)
click source tile B    -> ... repeat ...
Choose PNG… (new file) -> _choose(): new slice replaces the session in place,
                          last_index cleared
window close (X)       -> _close_import_session(): dialog destroyed, session gone
```

"Import PNG…" invoked again while a session exists simply re-shows it. The
session also survives switching level packages (it is a workshop resource, not
level data) and is destroyed on editor close.

---

## 3. Mirror / Flip implementation and undo behaviour

`NativeMetatileEditor._apply_transform(fn)`:

```python
before = [row[:] for row in self.pixels]
new = fn(self.pixels)
if new == self.pixels: return          # no-op transforms don't touch undo
self._undo.append(before); self._redo.clear()
self.pixels = new; self._redraw()
if self.on_change: self.on_change()
```

- **Mirror Horizontal** — `fn = lambda px: [list(reversed(row)) for row in px]`
- **Flip Vertical** — `fn = lambda px: [row[:] for row in reversed(px)]`

Both operate on the canonical 16×32 logical-pixel grid (values 0..3), **before**
`pixels_to_glyphs` decomposition/dedup. The source PNG, runtime glyph IDs and
packed charset bytes are never transformed.

Each transform pushes exactly one entry to the shared `_undo` stack, so a
single mirror or flip is one `Undo`. Determinism (proved in
`test_editor_workshop_gui.py`, check 5, on a seeded random 16×32 grid):

- `mirror_horizontal(); mirror_horizontal()` == original
- `flip_vertical(); flip_vertical()` == original
- `mirror_horizontal(); undo()` == original (exact previous logical pixels)
- `redo()` == the mirrored grid

No rotation added.

---

## 4. Repository rename / delete semantics

`_metatile_from_repo` is now the **Terrain Asset Repository** manager
(`TerrainRepository` already had `update_asset` / `remove`; this wires them to
the UI — no new architecture).

**Rename.** `simpledialog.askstring` → `repository.update_asset(id, name=new)` →
`repository.save()`.
- artwork and `native.pixels` unchanged; `id` (the identity) unchanged
- empty / whitespace-only name rejected with an error
- a display name already used by another asset prompts a confirm (names are
  labels; the `asset_NNNN` id is the identity — same convention as wave
  definitions, whose names are also non-unique)
- level metatiles previously snapshotted from the asset are **not** touched
  (they are independent deep copies; `source.repositoryAssetId` is descriptive
  provenance, not a live reference)

**Delete.** `messagebox.askyesno` confirmation (the message states that
already-copied level metatiles are unaffected, and shows how many this level
uses) → `repository.remove(id)` → `repository.save()`.
- level packages are unchanged — `test_editor_workshop_gui.py` check 8 asserts a
  level snapshot's pixels are byte-identical before/after both rename and delete,
  and that the change is persisted (`TerrainRepository.load` no longer has the id)
- list selection moves to a sane neighbouring row
- no destructive "Clear Repository" operation exists

---

## 5. VIC-II 2:1 logical-pixel display

`NativeMetatileEditor` stores one `unit` (default 10) and derives:

```
self.zx = unit * 2      # a logical multicolour pixel is a DOUBLE-WIDTH physical pixel
self.zy = unit
```

- canvas: `NATIVE_W*zx  ×  NATIVE_H*zy`  = `16*20 × 32*10` = **320 × 320**
  (a square — the equivalent of a 32×32 physical tile), instead of the old
  `16*14 × 32*14` = 224 × 448 squashed strip
- `_redraw` / `_paint_drag`: cell rectangles are `x*zx, y*zy, x*zx+zx, y*zy+zy`
- 4×4 char guides: verticals at `c*CHAR_W*zx`, horizontals at `r*CHAR_H*zy`
- `_cell(event)`: `x = canvasx // self.zx`, `y = canvasy // self.zy` — maps a
  mouse position straight back to a logical 0..15 / 0..31 cell

`test_editor_workshop_gui.py` checks 3–4 assert `zx == 2*zy`, the canvas is
square, corner clicks resolve to `(15,0)` / `(0,31)` / `(1,1)`, and a
`_paint_start` at the middle of cell `(3,7)` writes `pixels[7][3]`.

**Not changed:** canonical data (16×32 logical, values 0..3), the `"0".."3"`
row-string serialisation, `pixels_to_glyphs`, the exporter. The source-image
preview in `WorkshopDialog` stays square (it shows real image pixels). Import
thumbnails stay square.

---

## 6. Root cause of the background-control / health-sprite overlap

**Symptom.** Exporting a valid custom level that uses the full supported terrain
glyph budget (`TERRAIN_GLYPH_COUNT = TERRAIN_GLYPH_NAMESPACE = 64`) failed:

```
Error: Background control code overlaps health sprite RAM      (main.asm ~5941)
```

**Investigation.**

- `src/main.asm:5386` (before the fix) `#import`-ed
  `generated/level1/stage_charset.asm` — the `terrainGlyphs` byte block,
  `TERRAIN_GLYPH_COUNT * 8` bytes — **in the middle of the `* = $2920`
  background-control code segment**, between `bgDiagnosticGlyphs` and
  `updateBackgroundScroll`.
- Everything after it in that segment (`updateBackgroundScroll`,
  `prepareBackgroundCoarse`, … `countActiveEnemies`, ending at
  `BACKGROUND_CONTROL_END`) is therefore displaced upward by the block size.
- `HEALTH_SPRITE_BASE = $3000` (`main.asm:101`); the segment start `$2920` is
  fixed. Window = `$3000 - $2920 = $6E0` = 1760 bytes.
- Committed Level 1 (`TERRAIN_GLYPH_COUNT = 48` → 384-byte block):
  `terrainGlyphs = $2b05`, `terrainGlyphsEnd = $2c85`,
  `BACKGROUND_CONTROL_END = $2fd1` — only **47 bytes** below `$3000`.
- A 64-glyph level's block is `64*8 = 512` bytes, `128` bytes larger →
  `BACKGROUND_CONTROL_END = $3051` → `> $3000` → the guard fires. (Even 56
  glyphs, +64 bytes, overflows: `$3011`.)

So code placement was **accidentally dependent on the generated charset data
size**. It is not an assembler location-counter/import-ordering bug and no
other reserved region was near its boundary in the passing build
(`HEALTH_SPRITE_POOL_END` and `CLIP_SPRITE_POOL_END` had ample margin;
`BACKGROUND_CODE_END` at `$55xx` was far from `$6000`). The workshop merely made
larger glyph counts reachable, exposing the latent assumption that
`terrainGlyphs` is "small".

Reproduced before the fix by substituting a deterministic 64-glyph
`stage_charset.asm` + `TERRAIN_GLYPH_COUNT = 64`: `Error: Background control code
overlaps health sprite RAM`, exactly as reported.

---

## 7. Before / after memory map

Addresses from `build/main.sym` (KickAssembler `-vicesymbols`).
`HEALTH_SPRITE_BASE = $3000`, `raster_scheduler` origin `$6000`.

### Before (committed HEAD, 48-glyph Level 1)

| region | span | note |
|---|---|---|
| `$2920` background-control segment | `$2920 … $2fd0` | **contains `terrainGlyphs` ($2b05..$2c85, 384 B)** |
| `BACKGROUND_CONTROL_END` | `$2fd1` | **47 bytes** below `HEALTH_SPRITE_BASE $3000** |
| `HEALTH_SPRITE_BASE` pool | `$3000 … $33ff` | |
| `CLIP_SPRITE_POOL` | `$3400 … $37ff` | |
| `$4000` background/HUD code + raster_scheduler | `$4000 … $56xx`, then `* = $6000` | `$56xx … $5fff` unused |
| stage tables | `* = $6600` | metatileDefs + stageMetatileRows |

A 64-glyph Level 1 → `terrainGlyphs` 512 B → `BACKGROUND_CONTROL_END = $3051`
→ **build fails**.

### After (this fix)

| region | span | note |
|---|---|---|
| `$2920` background-control segment | `$2920 … $2e50` | **no `terrainGlyphs`**; only the ≤ 8-step copy unroll depends on the glyph count |
| `BACKGROUND_CONTROL_END` | `$2e51` (48 glyphs) / `$2e5d` (64 glyphs) | **~430 / ~419 bytes** clear of `$3000` |
| `HEALTH_SPRITE_BASE` pool | `$3000 … $33ff` | unchanged |
| `CLIP_SPRITE_POOL` | `$3400 … $37ff` | unchanged |
| `$4000` background/HUD code + raster_scheduler | `$4000 … $56f5`, then `* = $6000` | `BACKGROUND_CODE_END` ≈ `$55f3`; guard `.if (* > $5c00)` (~1.3 KB margin) |
| **`terrainGlyphs` (relocated)** | **`* = $5c00 … TERRAIN_CHARSET_END`** | 48 glyphs → `$5d80`; **64 glyphs → `$5e00`** (`≤ $6000`, 512 B reserve; ≥ 512 B always clear) |
| `raster_scheduler` | `* = $6000 … ~$634f` | unchanged |
| stage tables | `* = $6600` | unchanged |

`check_terrain_glyph_budget.py` output for the full 64-glyph build:

```
terrainGlyphs $5c00..$5e00 (512B) | BACKGROUND_CONTROL_END $2e5d (headroom 419B to $3000)
                                  | TERRAIN_CHARSET_END $5e00 (headroom 512B to $6000)
```

---

## 8. Memory-layout fix and why it is robust for valid exported levels

`terrainGlyphs` is **not code and not VIC-bank data** — `initBackground` copies
it to the live charset at `$3D00` with a plain absolute-indexed CPU loop
(`lda terrainGlyphs + b*64,x`), so its own address / VIC bank below `$A000` is
irrelevant. It was only inside the `$2920` code segment for historical reasons
(it replaced a hand-authored inline block).

**Fix:** give it a dedicated fixed segment `* = $5c00`, in the previously-empty
`$56xx…$5fff` window before `raster_scheduler` at `$6000` — the same pattern
already used for the metatile stage tables at `$6600`. This makes the `$2920`
timing/control segment size **independent of the generated tileset**, and gives
multiload a fixed target ("replace exactly this byte block").

**Why it is robust for any valid level, not just the committed one:**

- The reservation is checked worst-case, not for the current count:
  `.if ($5c00 + TERRAIN_GLYPH_NAMESPACE * 8 > $6000)` — a full 64-glyph
  (512-byte) block ends at `$5e00`, 512 bytes clear of `$6000`, for **every**
  level.
- `.if (TERRAIN_CHARSET_END > $6000)` catches any actual overrun.
- `.if (* > $5c00)` catches the background/HUD code (`$4000` segment) growing
  into the reserved window; current margin ≈ 1.3 KB.
- The only residual `TERRAIN_GLYPH_COUNT` dependency anywhere in the `$2920`
  segment is the `initBackground` copy-loop unroll, bounded at
  `TERRAIN_GLYPH_NAMESPACE / 8 = 8` steps; the existing
  `.if (BACKGROUND_CONTROL_END > HEALTH_SPRITE_BASE)` guard is proven to pass
  at that worst case with ~419 bytes to spare.

No guard was deleted, weakened or blindly relocated; `HEALTH_SPRITE_BASE` was
not moved; no timing-sensitive code was reshuffled (the `$2920` routines keep
their order and contents; they simply sit ~380 bytes lower).

### Related pre-existing defect: generated Level 1 out of sync

Commit `3a72c13` committed `src/generated/level1/*.asm` inconsistent with the
authored `tools/level_editor/levels/level1/level.json`:

| | `level.json` (authored) | committed generated |
|---|---|---|
| metatile count | 16 | `STAGE_METATILE_COUNT = 17` |
| wave triggers | 5 | `WAVE_TRIGGER_COUNT = 0` |
| turrets | 9 | 9 (consistent) |

The game built (the generated files were self-consistent) but did not reflect
the authored level, and `vice_wave_trigger_probe.py` had nothing to test. Fixed
by re-exporting `src/generated/level1/` **straight from the committed
`level.json`** via `load_project` + `export_level`. `build_levels.py` was *not*
used for this — its `build_level1` reconstructs Level 1 from a hard-coded Python
spec plus the (stale) `stage_test.asm`, so it cannot break the loop; that wart
is noted but out of scope. `level.json` authoring content was not modified.
Three probes/tests that hard-assumed a 16-def baseline were made count-agnostic
(`test_metatile_capacity.py`, `make_stage_fixture.py`, `vice_bottom_origin_probe.py`).

---

## 9. New / updated compile-time guards

| location | guard | purpose |
|---|---|---|
| `main.asm` after `fixedHudFreeLabel` | `.if (* > $5c00) .error "Background/HUD code overlaps the terrain glyph block at $5c00"` | protects the relocated block from the `$4000` code segment growing |
| `main.asm` after the charset import | `.if ($5c00 + TERRAIN_GLYPH_NAMESPACE * 8 > $6000) .error` | **worst-case**: the reserved window holds a full 64-glyph block for any level |
| `main.asm` `TERRAIN_CHARSET_END:` | `.if (TERRAIN_CHARSET_END > $6000) .error "terrain glyph block overruns its reserved window"` | catches an actual overrun into `raster_scheduler` |
| `main.asm` `BACKGROUND_CONTROL_END` | (unchanged) `.if (BACKGROUND_CONTROL_END > HEALTH_SPRITE_BASE)` — now with a comment that only the copy-loop unroll is level-dependent here | still fires on the real end; proven with ~419 B margin at 64 glyphs |

`stage_charset.asm`'s own
`.if (terrainGlyphsEnd - terrainGlyphs != TERRAIN_GLYPH_COUNT * 8)` size guard
is retained.

---

## 10. Editor test results

```
test_colour_conversion.py       All 7 colour-conversion checks passed.
test_editor_workshop_gui.py     All 9 editor-workshop GUI smoke checks passed.
test_level_packages.py          All 6 level-package checks passed.
test_metatile_capacity.py       All 7 metatile-capacity / migration checks passed.
test_native_metatile.py         All 7 native-metatile checks passed.
test_spritesheet.py             All 6 spritesheet checks passed.
test_terrain_repository.py      All 6 terrain-repository checks passed.
test_turret_integration.py      All 8 turret-integration checks passed.
test_turret_unlimited.py        All 5 unlimited-turret checks passed.
test_viewport_model.py          All 6 viewport-model checks passed.
test_wave_schema.py             All 6 wave-schema checks passed.
acceptance_terrain_workshop.py  PASS (8 steps; synthetic committed fixture — DithArt no longer present locally)
```

`test_editor_workshop_gui.py` (9) explicitly covers: 2:1 aspect + square canvas
+ corner hit-tests; click-paint lands on the intended 16×32 cell after aspect
correction; mirror/flip idempotent ×2 and each one undoable edit; Workshop save
appends + repacks a valid tileset; persistent import session
(pick → Workshop → Back to Source → pick again, same object, no re-read);
repository rename/delete leave level snapshots byte-identical and persist to
disk; 65th live metatile refused.

---

## 11. Build / export determinism results

- `src/main.asm` assembles clean (48-glyph committed Level 1 and a substituted
  64-glyph level).
- Re-exporting `src/generated/level1|2/` from the authored `level.json` twice is
  byte-identical (`md5` of `stage_test.asm` unchanged across runs).
- V4 `save → load → save` is byte-identical (`test_metatile_capacity.py` check 6).
- `test_level_packages.py` (6/6): per-level deterministic export, `level1/` and
  `level2/` independent.
- Mirror/flip/import/repository operations do not affect serialisation format.

---

## 12. VICE / runtime regression results

Background `x64sc` launch, remote monitor only, no `open -a`, no keyboard-focus
steal.

| probe | result |
|---|---|
| `vice_stage_widen_probe.py` (real Level 1) | **PASS** — 80 logical rows decode byte-exact on the 6502 |
| `run_stage_fixture.sh 300 64` | **PASS** — 64-def synthetic stage, logical rows to 1199 byte-exact |
| `run_stage_fixture.sh 769 64` | **assembler error** `Metatile stage data collides with the background turret segment ($8800)` (stage-row maximum guard still fires) |
| `vice_metatile64_smoke.py --rows 240 --defs 64` | **PASS** — 64-metatile stage, **max map id 63**, boots to PLAYING, scrolls, wraps, live `decodeStageCharacterRow` for a row containing id 63 byte-exact |
| `check_terrain_glyph_budget.py` | **PASS** — full 64-glyph level assembles; `terrainGlyphs $5c00`, `BACKGROUND_CONTROL_END $2e5d` (419 B clear of `$3000`), `TERRAIN_CHARSET_END $5e00` (512 B clear of `$6000`); 48-glyph Level 1 unaffected |
| `check_stage_addressing.py`, `check_metatile_def_lookup.py` | **PASS** (row math / 16-bit def-lookup arithmetic, 2308 checks) |
| `vice_scroll_test.py --physical --trace` 1400 f + `check_raster_capture.py` | `frame_cycle_deltas [19656]`, **service_failure_count 0**, **sprite_start_miss_count 0**, catchups 0 |
| `check_scroll_capture.py` (1400 f, per-run charset) | **failure_count 0** / 76.05M pixel checks / **87 wraps** / `first_transition_ok` / no stage-step errors / `[19656]` |
| `check_fixed_hud_capture.py` | **0 failures** — HUD row 0 hires intact |
| `check_turret_capture.py` | **0 failures** — shared turret body glyphs / flash / ground-code restore intact |
| `vice_wave_trigger_probe.py` | **PASS** — 5 authored triggers latch on `SCROLL_ROW`, re-arm across the wrap, resolve authored attack/count/sprite/interval; `SCROLL_FRAME_DIVIDER`-independent |
| `vice_bottom_origin_probe.py` | **PASS** — bottom-origin startup; streaming turret pool ≤ 8; a killed turret stays dead across the wrap |
| `vice_level1_smoke.py` | **PASS** — end-to-end: turret pool + authored waves, `GAME_STATE` PLAYING, scroll + wrap |

**Known stress-harness artefact (not a new regression).**
`vice_scroll_test.py --physical --stress` + `check_scroll_capture.py`: 5
transient pixel mismatches, **all at raster line y = 55**, frames 92–95, during
one coarse transition at `top = 372`, with `frame_cycle_deltas [19656]` and 0
raster service failures / 0 sprite-start misses. Same signature and location as
the pre-existing hiccup documented in `docs/encounter-budget-worklog.md` and the
prior Terrain Asset Workshop report (there "4 … at one raster line (y=55) across
frames 92–95"); the per-run count varies. The non-stress capture is clean.

---

## 13. Exact PAL cadence result

`check_raster_capture.py` `frame_cycle_deltas` = **`[19656]`** (a single value —
no jitter) on:

- the committed 48-glyph Level 1 (1400 physical frames, with 87 stage wraps)
- the 64-metatile-definition stress build (`vice_metatile64_smoke` window)
- the `--stress` capture (900 frames)

`service_failure_count = 0`, `sprite_start_miss_count = 0`, `catchups = 0` in
every case. The `$2920` timing/control routines were only shifted ~380 bytes
lower in address; none was reordered or rewritten.

---

## 14. Caveats

1. **Reserved terrain-glyph window is 512 bytes at `$5c00`.** A future need for
   > 64 terrain glyphs (the namespace is fixed at 64) or for the background/HUD
   code to exceed ~1.3 KB of new growth would require choosing a different
   origin; the three new guards make either condition a clean build error, not a
   silent overlap.
2. **`build_levels.py` `build_level1` does not round-trip `level.json`.** It
   reconstructs Level 1 from a hard-coded Python spec plus the committed
   `stage_test.asm`. It was not used for the re-sync (it cannot break the
   staleness loop). Making it export from `level.json` is a sensible follow-up,
   out of scope here.
3. **DithArt sheet is no longer present** at
   `~/Desktop/Ditharts_Free_Scifi_Tileset_v01/`. The automated acceptance falls
   back to the committed synthetic fixture, which exercises the same code paths;
   DithArt remains the intended human/manual acceptance source when available.
4. **`--stress` scroll-capture hiccup at y=55** persists unchanged (see §12).
5. **Repository rename/delete are not on the project undo stack** — they act on
   `repository.json` immediately, matching the existing repository-write pattern
   (import-to-repo also saves immediately). Deletion is confirmed; there is no
   undo for it beyond re-importing.

No stop condition was hit: no sprite-multiplexer rewrite, no replacement
scroller, no second screen buffer, no shadow matrix, no sprite reservation
reducing game capacity, no change to logical slot 0, no unsafe memory overlap,
no illegal/undocumented 6502, no timing assumption surviving only a light test.
