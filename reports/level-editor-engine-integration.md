# Level editor → generated assembler → engine → VICE integration

First real integration milestone. Generated level **configuration** and **stage
data** are now boring, deterministic KickAssembler build inputs. No manual
patching of `main.asm` between levels. Stage system, 16-bit widened world-row
implementation, renderer, raster scheduler, sprite multiplexer, BUILD/LIVE
ownership, encounter-budget behaviour and turret behaviour are unchanged.

---

## 1. Starting state

| | |
|---|---|
| branch | `multicolour-with-turrets-experiment` |
| HEAD | `187a222` "Enemy waves culled to avoid multiplexer conflicts with scrolling engine" |
| working-tree diff at start | `M AGENTS.md` only (+27 lines: the user's "VICE launch / focus discipline" section) |
| `tools/level_editor/` | present at the Milestone-3 checkpoint: `editor.py`, `engine_data.py`, `ka_export.py`, `project.py`, empty `projects/` |
| `docs/level-editor-worklog.md` | did **not** exist (created by this task) |
| `src/generated/` | did **not** exist |
| `src/stage_test.asm` | hand-authored, imported by `main.asm` |

**Pre-existing uncommitted work preserved:** `AGENTS.md` was not touched by this
task — `git diff AGENTS.md` still contains only the user's 27-line VICE-focus
addition. Nothing was reset / checked out / stashed / reverted.

---

## 2. Files changed

Modified (tracked):

| file | change |
|---|---|
| `src/main.asm` | early `#import "generated/stage_config.asm"`; removed the 7 duplicate level-owned `.const`s; kept `STAGE_LOGICAL_ROWS` derived; `$D021` ← `TERRAIN_BACKGROUND_COLOUR` in `initBackground`, restored to `0` in `endGame`; `#import "stage_test.asm"` → `#import "generated/stage_test.asm"` (still at `* = $6600`); added `TERRAIN_COLOUR_RAM == 8\|TERRAIN_CHARACTER_COLOUR` and `TERRAIN_BACKGROUND_COLOUR` range guards |
| `src/stage_test.asm` | **deleted** — moved to `src/generated/stage_test.asm` (generated) |
| `tools/level_editor/ka_export.py` | `render_stage_config()` emits the named `TERRAIN_CHARACTER_COLOUR` and `TERRAIN_COLOUR_RAM = 8 \| TERRAIN_CHARACTER_COLOUR` (was a hidden `8 \| <literal>`); ordering: rows, divider, background, mc1, mc2, character, colour_ram; expanded header comment |
| `tools/level_editor/engine_data.py` | new `_parse_generated_config()`; `load_engine_data()` reads height/palette/divider/colour-RAM from `src/generated/stage_config.asm` (no fallback to stale `main.asm`), stage data from `src/generated/stage_test.asm`, glyphs still from `src/main.asm`; validates `TERRAIN_COLOUR_RAM == 8 \| TERRAIN_CHARACTER_COLOUR` and colour ranges; `EngineData` gains `source_colour_ram` |
| `tools/level_editor/editor.py` | repo-root probe now checks `src/generated/stage_test.asm` |
| `tools/check_fixed_hud_capture.py`, `tools/check_turret_capture.py`, `tools/check_scroll_edges.py` | read `SCROLL_ROW` as 16-bit LE (`+ 256*SCROLL_ROW_HI` when the symbol exists) — the same fix `check_scroll_capture.py` already carried; needed because the 100-row acceptance level has 400 logical rows (`SCROLL_ROW` ≥ 256) |
| `tools/make_stage_fixture.py`, `tools/run_stage_fixture.sh` | target `src/generated/`; restore the generated files from a byte copy (not `git`, since they are new/untracked) |
| `AGENTS.md` | untouched by this task (pre-existing user edit) |

New (untracked):

- `src/generated/stage_config.asm`
- `src/generated/stage_test.asm`
- `tools/level_editor/projects/inspection-100.json` (V2, deterministic)
- `tools/level_editor/build_acceptance_level.py` (reproducible acceptance-level generator)
- `docs/level-editor-worklog.md`
- `reports/level-editor-engine-integration.md` (this file)

`src/background_turrets.asm`, `src/raster_scheduler.asm`, `src/variables.asm`:
**untouched** (empty diff).

`git diff --stat` (excl. AGENTS.md / new files): `src/main.asm` +47/-28,
`src/stage_test.asm` -100, tooling small.

---

## 3. Exact generated-file paths

- **`src/generated/stage_config.asm`** — constants-only include.
- **`src/generated/stage_test.asm`** — `metatileDefs` + `stageMetatileRows` bulk data.

---

## 4. Ownership before → after

| value | before | after |
|---|---|---|
| `STAGE_METATILE_ROWS` | `.const` in `main.asm` (25) | `src/generated/stage_config.asm` (100) |
| `SCROLL_FRAME_DIVIDER` | `.const` in `main.asm` (2) | `src/generated/stage_config.asm` (2) |
| `TERRAIN_BACKGROUND_COLOUR` | not a constant — engine wrote literal `#0` to `$D021` | `src/generated/stage_config.asm` (0); `initBackground` writes it to `$D021` |
| `TERRAIN_MC_COLOUR_1` | `.const` in `main.asm` (12) | `src/generated/stage_config.asm` (11) |
| `TERRAIN_MC_COLOUR_2` | `.const` in `main.asm` (15) | `src/generated/stage_config.asm` (14) |
| `TERRAIN_CHARACTER_COLOUR` | did not exist (fourth colour hidden in `8 \| 1`) | `src/generated/stage_config.asm` (1) |
| `TERRAIN_COLOUR_RAM` | `.const` in `main.asm` (`8 \| 1`) | `src/generated/stage_config.asm` (`8 \| TERRAIN_CHARACTER_COLOUR` = 9) |
| `STAGE_LOGICAL_ROWS` | derived in `main.asm` | **still** derived in `main.asm` = `STAGE_METATILE_ROWS * METATILE_H` |
| `metatileDefs` / `stageMetatileRows` | `src/stage_test.asm` (hand-authored) | `src/generated/stage_test.asm` (generated) |
| terrain glyph bitmaps, `TERRAIN_GLYPH_COUNT` | `src/main.asm` | **unchanged** — `src/main.asm` (deferred) |
| turret placement (`turretCols`, world rows) | `src/background_turrets.asm` | **unchanged** (deferred) |

There is no longer a generated value and a separately-maintained engine value
for any of the seven level-owned constants. `grep -cE '^\s*\.const\s+<name>' src/main.asm`
= 0 for all seven.

---

## 5. Import order (`src/main.asm`)

```
line   4:  #import "variables.asm"
line  15:  #import "generated/stage_config.asm"     <-- constants only; before every consumer
line 115:  .if (TERRAIN_COLOUR_RAM != (8 | TERRAIN_CHARACTER_COLOUR)) { .error ... }
line 140:  .const STAGE_LOGICAL_ROWS = STAGE_METATILE_ROWS * METATILE_H
 ...
line 5979: #import "raster_scheduler.asm"
line 5990: * = $6600
line 5991: #import "generated/stage_test.asm"        <-- bulk data; unchanged $6600 location
line 5992: .if (METATILE_DEFS_END - metatileDefs != METATILE_DEF_COUNT*METATILE_W*METATILE_H) { .error }
line 5995: .if (STAGE_METATILE_ROWS_END - stageMetatileRows != STAGE_METATILE_ROWS*METATILES_PER_ROW) { .error }
line 5998: STAGE_TEST_END:
line 5999: .if (STAGE_TEST_END > $8800) { .error }
line 6001: .if (STAGE_TEST_END > $a000) { .error }
line 6007: #import "background_turrets.asm"
```

`stage_config.asm` is imported at PC ≈ `$080d` (inside the BASIC upstart
region); being `.const`-only it emits no bytes, defines no segment, and does not
move the PC — the assembled memory map is structurally identical to before
(only the `$6600` block grew from the larger map).

---

## 6. Exporter changes (`ka_export.py`)

`render_stage_config()` now produces:

```asm
.const STAGE_METATILE_ROWS     = <height>
.const SCROLL_FRAME_DIVIDER    = <divider>
.const TERRAIN_BACKGROUND_COLOUR = <background>
.const TERRAIN_MC_COLOUR_1     = <mc1>
.const TERRAIN_MC_COLOUR_2     = <mc2>
.const TERRAIN_CHARACTER_COLOUR = <character>
.const TERRAIN_COLOUR_RAM      = 8 | TERRAIN_CHARACTER_COLOUR
```

No per-cell colour data. `render_stage_asm()` unchanged (still 16 metatile defs
+ `N` rows of 10 IDs). `export_project()` unchanged (writes `stage_config.asm`
and `stage_test.asm` into the given directory — called with `src/generated`).

---

## 7. Editor loader / parser changes (`engine_data.py`)

`_parse_generated_config(src/generated/stage_config.asm)`:
- parses the six scalar `.const`s + `TERRAIN_COLOUR_RAM`;
- accepts `TERRAIN_COLOUR_RAM = 8 | TERRAIN_CHARACTER_COLOUR` (or a resolved
  literal that must equal `8 | character`), else raises;
- range-checks `background`/`mc1`/`mc2` ∈ 0..15 and `character` ∈ 0..7.

`load_engine_data()` obtains stage height / palette / divider / colour-RAM from
that config (raises if the file is missing — **no** silent fallback to
`main.asm`), stage data from `src/generated/stage_test.asm`, and
`TERRAIN_GLYPH_COUNT` + glyph bitmaps still from `src/main.asm`. Cross-check
(pre-existing) that the config's `STAGE_METATILE_ROWS` equals the actual
`stageMetatileRows` row count is retained.

Verified: `load_engine_data('.')` returns `source_stage_rows=100`,
`source_scroll_frame_divider=2`,
`source_palette={'background':0,'multicolour1':11,'multicolour2':14,'character':1}`,
`source_colour_ram=9`, `glyph_count=48`, 16×16 metatiles, 100×10 stage rows,
all IDs 0..15.

---

## 8. Resulting generated 100-row config

`src/generated/stage_config.asm`:

```asm
.const STAGE_METATILE_ROWS     = 100
.const SCROLL_FRAME_DIVIDER    = 2
.const TERRAIN_BACKGROUND_COLOUR = 0
.const TERRAIN_MC_COLOUR_1     = 11
.const TERRAIN_MC_COLOUR_2     = 14
.const TERRAIN_CHARACTER_COLOUR = 1
.const TERRAIN_COLOUR_RAM      = 8 | TERRAIN_CHARACTER_COLOUR
```

Derived: `STAGE_LOGICAL_ROWS = 400`. Nominal duration at divider 2 ≈ 2:08.

---

## 9. Stage-map / metatile-def byte counts

| | bytes |
|---|---|
| `metatileDefs` (`METATILE_DEFS_END - metatileDefs`) | **256** (16 defs × 16) |
| `stageMetatileRows` (`STAGE_METATILE_ROWS_END - stageMetatileRows`) | **1000** (100 × 10) |

Both engine guards pass:
`METATILE_DEFS_END - metatileDefs == METATILE_DEF_COUNT*METATILE_W*METATILE_H`
and `STAGE_METATILE_ROWS_END - stageMetatileRows == STAGE_METATILE_ROWS*METATILES_PER_ROW`.
All map IDs are 0..15; `STAGE_METATILE_ROWS_END` immediately follows the map.

---

## 10. Exact assembled memory ranges

| symbol | address |
|---|---|
| `metatileDefs` | `$6600` |
| `METATILE_DEFS_END` / `stageMetatileRows` | `$6700` |
| `STAGE_METATILE_ROWS_END` / `STAGE_TEST_END` | `$6AE8` |
| generated stage-data end | `$6AE8` |
| raster_scheduler segment | `$6000–$634F` (unchanged) |
| background_turrets segment | `$8800–$8EDF` (unchanged) |

Assembly memory map segments: `$6000-$634f`, `$6600-$6ae7`, `$8800-$8edf`
(+ the lower engine segments, unchanged).

---

## 11. `$8800` guard result

`.if (STAGE_TEST_END > $8800) { .error ... }` — **PASS**. `STAGE_TEST_END =
$6AE8`; headroom to `$8800` = **7448 bytes**. The `$8800` boundary and the
editor's 844-row hard maximum were **not** loosened.

---

## 12. Palette verification (VICE, acceptance level)

`check_fixed_hud_capture` reads `$D021/$D022/$D023` from the capture's `vic.bin`:

| register | value | source |
|---|---|---|
| `$D021` | `0` | `TERRAIN_BACKGROUND_COLOUR` |
| `$D022` | `11` | `TERRAIN_MC_COLOUR_1` (was 12 in the old engine) |
| `$D023` | `14` | `TERRAIN_MC_COLOUR_2` (was 15 in the old engine) |
| terrain colour RAM | `9` | `TERRAIN_COLOUR_RAM = 8 \| 1` |
| `char_mcm` (`$D016` bit 4) | `true` | global multicolour text mode |

`check_fixed_hud_capture` `failure_count = 0` over the 1200-frame acceptance
capture (~64.6M pixel checks in `check_scroll_capture`, which renders every
terrain glyph through the captured `11/14` palette).

**Change-detection proof:** `TERRAIN_MC_COLOUR_1` was swapped 11 → 5 in the
project (editor + re-export only; `src/main.asm` md5 **unchanged**), rebuilt,
captured: `$D022 & 0x0F = 5` in the running engine; `check_fixed_hud_capture`
reported `d022: 5`, 0 failures. Restored to 11.

---

## 13. `$D021 / $D022 / $D023` verification

As table §12. `$D021` is now driven by `initBackground` from
`TERRAIN_BACKGROUND_COLOUR` (was a literal `#0`) and reset to `0` by `endGame`
for the menu / GAME OVER. `$D022 / $D023` continue to be written by
`initBackground`, now from the generated `TERRAIN_MC_COLOUR_1 / _2`. Terrain
colour-RAM fill continues to use `TERRAIN_COLOUR_RAM` once, then `initFixedHud`
overwrites row 0.

---

## 14. HUD hires verification

`check_fixed_hud_capture` validates the hires fixed-HUD band (row 0) and the
HUD/terrain separator exactly; `failure_count = 0`. HUD colour RAM is not
filled with `TERRAIN_COLOUR_RAM` (bit 3 clear on row 0 → hires). Screen row 24
remains engine/space.

---

## 15. Scroll-divider verification

`SCROLL_FRAME_DIVIDER = 2` comes from `src/generated/stage_config.asm`; zero
`.const SCROLL_FRAME_DIVIDER` definitions remain in `main.asm`. Scroll behaviour
is the unchanged divider-2 baseline: `check_scroll_capture` `deferred = 0`, 74
fine wraps over 1200 frames, `frame_cycle_deltas = [19656]`.

---

## 16. 16-bit addressing / wrap results

| test | result |
|---|---|
| `tools/check_stage_addressing.py` (host arithmetic model) | PASS |
| `tools/vice_stage_widen_probe.py` on the acceptance build | `stage: 100 metatile rows, 400 logical rows, 1000-byte map`; 80 logical rows (max 399) decoded on the 6502 byte-exact vs model + tile expansion; `wrapBgLogicalRow` correct for out-of-range inputs |
| `STAGE_LOGICAL_ROWS` | **400** (derived from generated `STAGE_METATILE_ROWS = 100`) |
| `tools/run_stage_fixture.sh` at 25 / 64 / 256 / 400 metatile rows (synthetic maps written to `src/generated/`, restored after) | all PASS — decode byte-exact to logical rows 99 / 255 / 1023 / 1599 |
| full-stage wrap (`--seed-scroll 12`, 900 frames) | `stage_loops = 1` (SCROLL_ROW 0↔399), `first_transition_ok = true`, `stage_step_errors = []` (every step −1 mod 400), descending seam preserved, 0 matrix/pixel failures |

---

## 17. VICE runtime result (acceptance level, divider 2, 1200 frames, `--physical --trace`)

| checker | result |
|---|---|
| `check_scroll_capture` | **PASS** — `failure_count 0`, `frame_cycle_deltas [19656]`, `deferred 0`, `wraps 74`, `stage_loops 1`, `first_transition_ok true`, `stage_logical_rows 400`, `pixel_checks 64,651,362` |
| `check_fixed_hud_capture` | **PASS** — `failure_count 0`; d021/d022/d023 = 0/11/14; `char_mcm true`; terrain cRAM 9 |
| `check_turret_capture` | **PASS** — `failure_count 0`, `deferrals 0` |
| `check_raster_capture` | **PASS** — `service_failure_count 0`, `sprite_start_miss_count 0`, `frame_cycle_deltas [19656]` |

Load (`tools/check_encounter_load.py`): authored wave sizes `{5}`, max active
enemies 5, max hostile bullets 2, max `SORTED_COUNT` 8, coarse deferral events
0, longest run 0, suppression TOTAL/RESOLVED/UNRESOLVED 0/0/0.

---

## 18. Raster service failures

**0** (`check_raster_capture` on the acceptance capture).

## 19. Sprite-start misses

**0**.

## 20. Coarse deferrals / suppression metrics

Coarse deferral events **0**; longest consecutive deferral run **0**;
presentation suppression TOTAL/RESOLVED/UNRESOLVED **0/0/0**, over the
1200-frame acceptance capture. No new coarse-scroll regression.

## 21. Frame-cycle deltas

`[19656]` on every capture in this task (acceptance 1200 f, wrap 900 f, palette
swap 300 f, stage-widen fixtures, turret >255 fixture).

---

## 22. Turret regression result

| test | result |
|---|---|
| `check_turret_capture` (acceptance capture) | PASS — 0 failures, 0 deferrals |
| `tools/vice_turret_large_row.py` (400-row generated stage, `turretRows` 255/260/1024) | PASS — position/visibility, glyph install, colour pulse + restore, hit/destroy correct above 255 logical rows |
| `tools/vice_suppress_fixtures.py` A–J | 10/10 PASS |
| `tools/vice_encounter_fixtures.py` A–R | 18/18 PASS (encounter-budget behaviour unchanged) |

Turret placement, HP, pulse, aim-at-fire-time, death/restoration and rendering
are byte-identical (`src/background_turrets.asm` untouched). Turrets on the
generated terrain behave as before.

---

## 23. Deterministic re-export result

`tools/level_editor/build_acceptance_level.py` run twice → `stage_config.asm`,
`stage_test.asm` and `inspection-100.json` md5 **byte-identical** across runs
(`12c91f06…`, `27857252…`, `aa0128b9…`). `run_stage_fixture.sh` backup/restore
leaves the generated files byte-identical.

---

## 24. Stop conditions

**None occurred.** The constants-only config imported early with a single
`#import` line (no engine reorganisation). Stage data stayed at `$6600` (no
protected code/asset moved). `$8800` not loosened. The 100-row map is exactly
1000 bytes. The 16-bit widened row logic was not touched. No
renderer/scheduler/raster-IRQ change. No existing uncommitted user work was
discarded. All VICE tests used the remote monitor / process control (no
keyboard-focus automation).

---

## 25. Final working-tree status

```
 M AGENTS.md                              (pre-existing user edit, untouched by this task)
 M src/main.asm
 D src/stage_test.asm
 M tools/check_fixed_hud_capture.py
 M tools/check_scroll_edges.py
 M tools/check_turret_capture.py
 M tools/level_editor/editor.py
 M tools/level_editor/engine_data.py
 M tools/level_editor/ka_export.py
 M tools/make_stage_fixture.py
 M tools/run_stage_fixture.sh
?? docs/level-editor-worklog.md
?? reports/level-editor-engine-integration.md
?? src/generated/
?? tools/level_editor/build_acceptance_level.py
?? tools/level_editor/projects/
```

HEAD is still `187a222`. **Nothing was committed or pushed.**

Acceptance build (for reference): `build/shooter.prg` SHA256
`037c735d13a43789427d6476c893c525d8e1e3789998793c7baa7376bfad3b64`;
`build/shooter.d64` SHA256
`7d09ca2f30b8915f28b7c990bcf88f722dfac88c8726ccdf0a687e4c67953443`.

---

## 26. Remaining follow-up work

- **Terrain glyph ownership deferred.** `terrainGlyphs` bitmaps and
  `TERRAIN_GLYPH_COUNT` remain hand-authored in `src/main.asm`; namespace
  `160..223`, 48 authored. No glyph editing. The editor still reads glyphs from
  engine source.
- **Gameplay-object / turret export deferred.** V2 JSON `"objects": []` is
  reserved; its schema is not defined. Turret placement stays engine-owned
  (`turretCols` / turret world rows in `background_turrets.asm`); `MACH` is art,
  not a magic tile. No object placement table in generated data.
- **Multi-level packaging/selection deferred.** One generated level unit.
- `check_hud_capture.py` is a stale checker (`KeyError: HUD_PATCHED`, old HUD
  design) — not in the maintained suite, not fixed here.

---

## 27. Acceptance table

| # | criterion | YES/NO |
|---|---|---|
| 1 | `stage_config.asm` imported before any dependent constant | **YES** (main.asm line 15, first consumer line 115) |
| 2 | `stage_config.asm` is constants-only, emits no bytes / segment / PC change | **YES** |
| 3 | No duplicate level-owned `.const`s remain in `main.asm` (all 7) | **YES** (grep count 0 each) |
| 4 | `STAGE_LOGICAL_ROWS` derives from generated `STAGE_METATILE_ROWS` | **YES** (= 400) |
| 5 | Editor loader reads the generated config, not stale `main.asm` | **YES** (no fallback) |
| 6 | Generated config emits the full named palette contract incl. `TERRAIN_CHARACTER_COLOUR` | **YES** |
| 7 | Generated `TERRAIN_COLOUR_RAM` derives from `TERRAIN_CHARACTER_COLOUR` | **YES** (`8 \| TERRAIN_CHARACTER_COLOUR`) |
| 8 | Generated stage = exactly 16 metatile definitions | **YES** |
| 9 | Metatile definitions = exactly 256 bytes | **YES** |
| 10 | 100-row map = exactly 1000 bytes | **YES** |
| 11 | All map IDs 0..15 | **YES** |
| 12 | `STAGE_METATILE_ROWS_END` immediately follows the map | **YES** (`$6AE8`) |
| 13 | Stage data assembles at `$6600` | **YES** |
| 14 | Reported start/end: `metatileDefs $6600`, `stageMetatileRows $6700`, end `$6AE8` | **YES** |
| 15 | Stage-size consistency guard passes | **YES** |
| 16 | `$8800` upper-memory guard passes | **YES** (7448 B headroom, not loosened) |
| 17 | `STAGE_LOGICAL_ROWS == 400` | **YES** |
| 18 | Widened 16-bit addressing tests pass | **YES** (host oracle + 6502 probe + 25/64/256/400 fixtures) |
| 19 | Full stage wrap passes | **YES** (`stage_loops 1`, `stage_step_errors []`) |
| 20 | Descending scroll direction / seam semantics preserved | **YES** |
| 21 | Runtime `$D021` driven by generated background colour | **YES** (0) |
| 22 | Runtime `$D022` = generated MC1 = 11 | **YES** |
| 23 | Runtime `$D023` = generated MC2 = 14 | **YES** |
| 24 | Ordinary terrain cRAM = generated 9 | **YES** |
| 25 | HUD row 0 remains hires | **YES** (`check_fixed_hud_capture` 0 failures) |
| 26 | 11/14 acceptance palette observable in VICE / oracle | **YES** |
| 27 | One generated value changed → engine picks it up with no engine-source edit → restored | **YES** (`TERRAIN_MC_COLOUR_1` 11→5→11) |
| 28 | `SCROLL_FRAME_DIVIDER = 2` from generated config | **YES** |
| 29 | No duplicate engine-local divider | **YES** |
| 30 | Scroll behaviour = divider-2 baseline | **YES** |
| 31 | Generated 100-row stage scrolls correctly | **YES** |
| 32 | Raster service failures = 0 | **YES** |
| 33 | Sprite-start misses = 0 | **YES** |
| 34 | PAL cadence `[19656]` | **YES** |
| 35 | No new coarse-scroll regression | **YES** (deferred 0) |
| 36 | Projectile presentation-suppression fixtures pass | **YES** (A–J) |
| 37 | Turret regression fixtures pass | **YES** (turret capture, >255 fixture, suppress, encounter) |
| 38 | Turret placement/HP/pulse/fire/death unchanged | **YES** (`background_turrets.asm` untouched) |
| 39 | No renderer/scheduler changes required | **YES** |
| 40 | Editor can load the new generated baseline | **YES** (`load_engine_data` verified) |
| 41 | Saving/exporting a V2 project is deterministic | **YES** |
| 42 | Re-exporting produces byte-identical generated files | **YES** (md5 stable) |
| 43 | A future level export needs no manual `main.asm` edit | **YES** |
| — | Pre-existing uncommitted work preserved | **YES** (`AGENTS.md` untouched) |
| — | Nothing committed or pushed | **YES** |
