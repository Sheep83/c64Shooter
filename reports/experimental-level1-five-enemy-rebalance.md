# 19656 — Experimental Level 1 Five-Enemy Rebalance

**Result: GREEN, with one measured constraint reported rather than worked
around.** Level 1 is now recurring five-enemy waves with no six-enemy wave
anywhere, the four-turret cluster is reduced to its lower two, and
`levels/level1/level.json` is genuinely authoritative for regeneration. The one
thing level data *cannot* deliver — a literal 120-frame gap between wave starts
— is measured, explained and left for a decision (§7).

---

## 1. Starting branch and HEAD

Branch **`experimental-three-layer-player`**, HEAD **`e94ccf5`**
("High Score screen corruption fixed") — no commits made on the branch, as
before. The worktree carried the three-layer player experiment, which was left
intact and still builds both ways (§14).

## 2. Files changed

```
 M src/generated/level1/stage_turrets.asm      (generated)
 M src/generated/level1/stage_waves.asm        (generated)
 M tools/level_editor/levels/level1/level.json (canonical source)
 M tools/level_editor/build_levels.py          (Level 1 now loads the JSON)
 M src/main.asm                                (wave-trigger tables relocated - §7.3)
?? tools/level_editor/import_generated_level.py    (new: generated ASM -> level.json)
?? tools/level_editor/author_level1_five_enemy.py  (new: author-time rebalance)
?? tools/vice_wave_cadence_probe.py                (new: runtime cadence measurement)
?? docs/experimental-level1-five-enemy-rebalance-worklog.md
?? reports/experimental-level1-five-enemy-rebalance.md
```

`src/generated/level1/stage_config.asm`, `stage_charset.asm` and
`stage_test.asm` are **byte-identical** after regeneration, and
`src/generated/level2/` is untouched. `src/raster_scheduler.asm` carries only
the earlier three-layer work.

### 2.1 A drift that had to be fixed first

The generated ASM the game actually builds had diverged from every authored
source in the repo. Running `build_levels.py` as it stood would have **silently
destroyed the live level**:

| | `level.json` + `build_levels.py` | generated ASM (live) |
|---|---|---|
| metatile rows | 100 (400 logical) | **105 (420 logical)** |
| metatile defs | — | **34** |
| glyphs | — | **72** |
| palette (bg/mc1/mc2) | 0 / 11 / 14 | **12 / 15 / 11** |
| turrets | 9 | **10** |
| wave triggers | 5 | **16** |

`build_level1()` rebuilt the level from hard-coded Python constants plus the
*git-committed* `stage_test.asm`. This is exactly the hazard the task named, so
it was fixed before any content change (§10–11).

## 3. Previous Level 1 wave structure

16 authored triggers — **10 of them six-enemy waves**:

| worldRow | attack | size | enemyType | gap from previous |
|---|---|---|---|---|
| 377 | 11 | **6** | 1 | — |
| 360 | 10 | **6** | 0 | 17 rows / 272 f |
| 312 | 10 | **6** | 0 | 48 rows / 768 f |
| 292 | 3 | 5 | 0 | 20 rows / 320 f |
| 276 | 10 | **6** | 0 | 16 rows / 256 f |
| 256 | 10 | **6** | 0 | 20 rows / 320 f |
| 240 | 11 | **6** | 1 | 16 rows / 256 f |
| 196 | 3 | 5 | 0 | 44 rows / 704 f |
| 176 | 2 | 5 | 0 | 20 rows / 320 f |
| 160 | 10 | **6** | 0 | 16 rows / 256 f |
| 144 | 11 | **6** | 1 | 16 rows / 256 f |
| 128 | 10 | **6** | 0 | 16 rows / 256 f |
| 88 | 3 | 5 | 0 | 40 rows / 640 f |
| 69 | 2 | 5 | 0 | 19 rows / 304 f |
| 48 | 3 | 5 | 0 | 21 rows / 336 f |
| 32 | 10 | **6** | 0 | 16 rows / 256 f |

Size histogram: **{6: 10, 5: 6}**. Only 4 attack ids used (2, 3, 10, 11), the
level's last 100 rows carried nothing, and gaps ranged 256–768 frames.

## 4. New five-enemy wave scheduling

**53 triggers, every one a five-enemy wave**, covering world rows **390 → 0** —
the full playable length, where the old schedule stopped at row 32 and left the
first 17 rows and the tail sparse.

* first trigger at row 390, just below `STAGE_START_ROW` (397), so the opening
  wave arrives shortly after the level begins;
* gaps alternate **8 and 7 logical rows** (see §7);
* wave size is 5 in every definition, so `waveTriggerCount` is uniformly 5;
* `spawnInterval` is left null in every definition, resolving to the engine's
  own per-attack default (15–18) — the waves stay inside the curated
  vocabulary rather than being overridden.

Generated result:

```
.const WAVE_TRIGGER_COUNT = 53
.var waveTriggerCount = List().add(5, 5, 5, 5, 5, ... 5)     // all 53 entries
```

## 5. How the random selection is produced — author time, not runtime

**Author time, baked into the JSON. There is no runtime nondeterminism and none
left in the build path.**

`tools/level_editor/author_level1_five_enemy.py` draws, per trigger, an
`(attackId, enemyType)` pair from the engine's existing curated vocabulary —
**12 attacks × 4 enemy types = 48 combinations** — using `random.Random(19656)`,
a fixed documented seed. It then writes explicit wave definitions and explicit
triggers into `level.json` and exits. From that moment the JSON contains a
literal schedule; `build_levels.py` only exports it.

Variety actually achieved in the shipped schedule:

| measure | value |
|---|---|
| distinct attack ids used | **12 of 12** (0–11) |
| distinct enemy types used | **4 of 4** (sprite seeds 0/8/16/24) |
| distinct (attack, enemyType) pairs | **33 of 48** |
| longest run of the same attack | **3** |
| member intervals resolved | 15, 16, 17, 18 |

Re-rolling the schedule is a deliberate act (re-run the authoring script,
optionally with `--seed`), never a side effect of building.

## 6. Proof that no six-enemy wave remains

Three independent checks:

1. **Authored source** — every one of the 33 wave definitions in `level.json`
   has `composition[0].count == 5`.
2. **Generated ASM** — `waveTriggerCount` is 53 entries, `sorted(set(...)) ==
   [5]`, `count(6) == 0`, `max == 5`.
3. **Runtime, in VICE** — `tools/vice_wave_cadence_probe.py` breaks at
   `startAuthoredWave` and reads the wave's size from `waveTrigCount[X]` using
   the routine's own entry argument (reading `WAVE_ENEMY_COUNT` at the
   breakpoint would return the *previous* wave's value). Over 18 consecutive
   waves: **`wave sizes seen: [5]`, `six-enemy waves: 0`**, 11 distinct attack
   ids observed.

## 7. The 120-frame interval

### 7.1 What the authoring model can express

Authored triggers fire on **terrain position**, not on a frame counter: a
trigger fires when `SCROLL_ROW` descends to its `worldRow`. The conversion is
fixed by the engine — one logical row = 8 fine steps × `SCROLL_FRAME_DIVIDER`.
Level 1 has divider 2, so:

```
1 logical row = 16 frames        120 frames = 7.5 logical rows
```

7.5 is not an integer, so **no uniform row gap can express 120 frames**. The
schedule therefore alternates **8-row and 7-row gaps (128 / 112 frames)**:

```
gaps (rows)  : [7, 8]        frames: [112, 128]
mean gap     : 7.5000 rows = 120.00 frames   (target 120)
rows span    : 390 .. 0      (53 triggers)
```

Authored trigger spacing is therefore **exactly 120 frames on average and never
more than 8 frames off**, which is the closest the row-triggered model can
represent. It is deliberate quantisation, not approximation.

### 7.2 What actually happens at runtime — and why it is not 120

Measured wave **starts** are ~210–222 frames apart, not 120. This is not the
level data: the engine gates every wave start behind its own sequencer
(`updateSpawner`). Model, derived from the source and confirmed exactly against
VICE for every interval the schedule produces:

```
gap = (WAVE_ENEMY_COUNT - 1) * spawnInterval + WAVE_GAP        WAVE_GAP = 150

  interval 15 -> predicted 210   observed 210   ✓
  interval 16 -> predicted 214   observed 214   ✓
  interval 17 -> predicted 218   observed 218   ✓
  interval 18 -> predicted 222   observed 222   ✓
```

`WAVE_GAP = 150` (`src/main.asm:788`, *"Frames between completed spawn
formations"*) is an **engine constant, and 150 alone already exceeds 120**.
Therefore **no level content change of any kind can produce 120-frame wave
starts.** The authored triggers are never the binding constraint — they are
always latched and waiting; the probe shows the fire row lagging further and
further behind the trigger row as the level runs.

Larger observed gaps (411, 507 frames) are the existing turret-pressure
deferral, which holds the start of a whole wave while a turret is exerting
pressure. That is existing, intended behaviour and was not touched.

### 7.3 What reaching a literal 120 would take — flagged, not done

Two values, one of which is engine-owned:

```
gap = 4 * spawnInterval + WAVE_GAP = 120
  pin spawnInterval 15 in the wave definitions (LEVEL data, already supported)
  set WAVE_GAP 150 -> 60            (ENGINE constant, one line)
```

I have **not** made that change. `WAVE_GAP` is a global gameplay-pacing constant
that also governs the autonomous director used by any level with
`WAVE_TRIGGER_COUNT == 0`, and this task is explicitly level content/data only.
It is a one-line change whenever you want it; the level side is already
compatible.

### 7.4 One engine file was touched, and this is why

53 triggers × 6 tables = **318 bytes** of level data. Those tables were emitted
*inline in the background/HUD code block*, which is capped at `$5a00` by the
terrain glyph block and had only ~211 bytes of headroom — so the build failed
with `"Background/HUD code overlaps the terrain glyph block at $5a00"`.

The tables were moved into their own `$7100` segment with the program counter
saved and restored around them, so no code moved. This follows the codebase's
own documented precedent rather than inventing anything — `main.asm` already
records that `terrainGlyphs` was moved to `$5a00` and the metatile stage tables
to `$6600` for exactly this reason: *a variable-length LEVEL block must not sit
inside a code segment*. A new guard errors if the tables ever overflow `$8000`.

Resulting map (background/HUD block back under its ceiling, no overlaps):

```
$4000-$58d5   background/HUD code   (ceiling $5a00)
$7000-$70d6   three-layer player helper
$7100-$723d   authored wave-trigger tables (318 bytes, guard at $8000)
```

## 8. Turret cluster change

The four-turret cluster is world rows **321 / 329 / 337 / 345**. The stage is
bottom-origin and screen position increases with logical row, so within the
cluster the **smaller** world rows are the ones nearest the **top** of the
screen.

**Removed the upper two — world rows 321 and 329. Kept 337 and 345.**
No other turret was touched.

```
before: TURRET_TOTAL = 10
        turretRows = 345, 337, 329, 321, 225, 217, 117, 109, 25, 5
after : TURRET_TOTAL = 8
        turretRows = 345, 337,           225, 217, 117, 109, 25, 5
        turretCols =  17,  25,            29,   9,  25,  13, 25, 13
```

Verified: `TURRET_TOTAL == 8`, both lists are 8 long, rows remain sorted
descending (streaming-cursor order), cluster rows present `[337, 345]`, removed
`[321, 329]`. This also matches the reduced two-turret variant the earlier
four-turret flicker forensics used (`345 + 337`).

## 9. JSON path

```
tools/level_editor/levels/level1/level.json
```

Unchanged location — it is where the level package already lived, next to
`levels/level2/level.json`, is already git-tracked, and is the path
`build_levels.py` already printed as the package source. Choosing anywhere else
would have been the surprising option.

## 10. JSON is now authoritative for regeneration

`build_level1()` no longer reconstructs anything:

```python
def build_level1(engine):
    """Load Level 1 from its canonical JSON. No reconstruction, no defaults."""
    json_path = LEVELS_DIR / L1_NAME / "level.json"
    if not json_path.exists():
        raise SystemExit(...)          # explicit, with the recovery command
    return load_project(json_path)
```

Proof that regeneration cannot revert the content: `build_levels.py` was run
three times after authoring, and all five generated files were byte-identical
each time, with `TURRET_TOTAL = 8` and `WAVE_TRIGGER_COUNT = 53` throughout
(§13). The stale reconstruction path is **deleted**, not bypassed — `L1_TURRETS`,
`L1_WAVE_DEFS`, `L1_WAVE_TRIGGERS`, `L1_PALETTE`, `L1_DIVIDER`, the band
constants, `_committed_stage_test()` and `_parse_byte_rows()` are all gone, along
with the now-dead `subprocess` import.

The engine/editor contract is preserved: JSON is editable source, generated ASM
is build input, the editor does not patch `main.asm`, `stage_config.asm` still
owns palette/divider/stage height, `stage_test.asm` still owns metatile
layout, gameplay objects/waves stay separate from terrain, and bottom-origin
semantics are unchanged.

## 11. Tooling change required to achieve that

Two new tools plus the `build_levels.py` edit. Deliberately narrow — the editor
itself was not refactored, and Level 2 still builds from its existing path.

**`tools/level_editor/import_generated_level.py`** — recovers a level package
*from* its generated includes, inverting `ka_export` exactly: config constants,
glyph bitmaps, metatile defs, the metatile map, turret world rows/cols back to
metatile coordinates, and wave triggers back into one definition per distinct
resolved `(attackId, count, enemyType, interval)` tuple. Correctness is not
asserted, it is **proved by round-trip**: `--verify` re-exports the recovered
project and requires byte-identical output against the real generated ASM.

```
level1: 105 metatile rows, 34 metatile defs, 72 glyphs, 10 turrets,
        16 wave triggers, 4 wave definitions
round-trip: re-export is byte-identical to the generated ASM
```

That is what made it safe to adopt the live level as canonical instead of the
stale reconstruction.

**`tools/level_editor/author_level1_five_enemy.py`** — the author-time step
(§5). Imports the live level, drops the two upper cluster turrets, replaces the
wave data with the seeded five-enemy schedule, and saves `level.json`. Supports
`--dry-run` and `--seed`.

## 12. Generated ASM / config paths

```
src/generated/level1/stage_config.asm    unchanged (105 rows, divider 2, palette 12/15/11, 72 glyphs)
src/generated/level1/stage_charset.asm   unchanged (72 glyph bitmaps)
src/generated/level1/stage_test.asm      unchanged (34 metatile defs + 105x10 map)
src/generated/level1/stage_turrets.asm   CHANGED  (TURRET_TOTAL 10 -> 8)
src/generated/level1/stage_waves.asm     CHANGED  (WAVE_TRIGGER_COUNT 16 -> 53, all size 5)
```

Only the two files the task is about changed. That is the direct evidence for
validation item 8: **stage dimensions, origin, palette, scroll divider, tileset
and terrain map are provably unchanged** — those three files are byte-identical.

## 13. Deterministic regeneration proof

`build_levels.py` run three times, hashing all five Level 1 includes after each:

```
stage_charset.asm  02fc743968ba24de...
stage_config.asm   0e8cc7e9836535c6...
stage_test.asm     2403ee39a368c886...
stage_turrets.asm  70409f35be4180e9...
stage_waves.asm    6af030b6f87aa469...

2nd regeneration: byte-identical   PASS
3rd regeneration: byte-identical   PASS
```

`level.json` is not rewritten by the build, so the source cannot drift either.

## 14. Build / runtime validation

| check | result |
|---|---|
| Level 1 builds from the JSON source | **pass** — clean assemble, 0 errors, 0 warnings |
| three-layer branch build | **pass** — `1ad122ee5a05f1d50238f44651e206ba7cd26974675c7fc9d2cdd0ef768dfb3b` |
| single-layer toggle build (same tree) | **pass** — `0c8643263fa10040606e9b5ab88d901bc54599fda4c166b7cb731bf61af370c8` |
| memory map | background/HUD block `$4000-$58d5` (ceiling `$5a00`), wave tables `$7100-$723d`, no overlaps |
| 1400-frame capture, exact PAL | **`[19656]`** |
| service failures / sprite-start misses | **0 / 0** |
| page-aware fallback | `page_aware: true`, 692 / 708 frames on pages A / B |
| max concurrent objects | **8** (was 9 with six-enemy waves — the lighter load is visible) |
| runtime wave sizes over 18 waves | **all 5**, zero six-enemy |
| runtime attack variety | 11 distinct attack ids in the first 18 waves |
| level-editor suites | `test_level_packages` 6/6, `test_wave_schema` 6/6, `test_wave_repository` 7/7, `test_turret_integration` 8/8, `test_turret_unlimited` 5/5, `test_import_from_project` 4/4, `test_generated_set_recovery` 5/5 — **all pass** |
| encounter fixtures A–R | **18 / 18 PASS** (see §15) |

## 15. Test fixtures

**No fixture needed updating.** The only fixture that mentions six enemies,
`B_authored6_presented_as_5`, tests the *engine's* `attackEnemyCount` table
against the autonomous director — not Level 1's authored data — and still
passes.

More interesting: **`J_wave_start_deferred_then_starts` and
`L_pressure_clear_wave_eligible` now PASS.** Both were reported as pre-existing
failures in the previous two reports, on both `main` and the three-layer build.

The cause is now identified and verified, and it is this task's subject matter.
The fixture latches trigger 0 (`WAVE_TRIGGER_FIRE = 1`), calls `updateSpawner`,
and asserts `WAVE_ENEMY_COUNT == 5`. Level 1's **old trigger 0 was a six-enemy
wave**, so the assertion saw 6:

```
old waveTriggerCount = List().add(6, 6, 6, 5, ...)   -> J: started=False  FAIL
new waveTriggerCount = List().add(5, 5, 5, 5, ...)   -> J: started=True   PASS
```

Confirmed both ways on otherwise-identical builds: the pre-change level data
fails, the post-change level data passes, and `held=True` in both (the
turret-pressure half of the contract always worked). So those two failures were
never an engine defect — they were the fixture correctly reporting that Level 1
violated the five-enemy encounter-budget contract.

## 16. Build / test artifact cleanup and final disk usage

* Every emulator capture went to a scratch root **outside the repository**;
  `run_regression_suite.sh` deletes each capture directory immediately after
  analysing it (peak ~70 MB, one at a time).
* Repository `build/`: **304 KB, 4 files** (`shooter.prg`, `shooter.d64`,
  `main.vs`, `main.sym`) — unchanged in shape.
* Scratch after cleanup: **504 KB**, JSON summaries and a few 40 KB PRG copies
  kept only for like-for-like comparison.
* Repo growth from this task is level data only: `src/generated` 64 KB,
  `tools/level_editor/levels` 120 KB.
* `import_generated_level.py --verify` uses a `TemporaryDirectory`, so its
  round-trip check leaves nothing behind.
* No VICE processes left running. All instances launched directly via
  `subprocess.Popen` — never `open -a` — so nothing stole keyboard focus.

## 17. Manual test checklist

1. `python3 tools/level_editor/build_levels.py`, then build and run.
   Level 1 should report `105 metatile rows (420 logical), 8 turrets,
   53 wave triggers`.
2. **No six-enemy waves.** Watch several waves: every one should be five
   enemies. This is the headline change.
3. **Recurring waves the whole way down.** Waves should keep arriving for the
   entire level, including near the start and near the end, where the old
   schedule was silent.
4. **Variety.** Consecutive waves should use visibly different
   formations/approach patterns and enemy colours — not one repeated formation.
5. **Cadence.** Expect a wave roughly every 210–222 frames (~3.6 s), *not*
   every 120 — that floor is `WAVE_GAP` and is explained in §7.2. If you want
   true 120, §7.3 has the two values to change.
6. **Turret cluster.** At the cluster, only **two** turrets should appear, the
   lower pair. The top-heavy pair is gone.
7. **Other turrets unchanged.** Six further turrets remain spread through the
   level (world rows 225, 217, 117, 109, 25, 5).
8. **Terrain identical.** The map, palette and scroll speed should look exactly
   as before — `stage_config/charset/test.asm` are byte-identical.
9. **Three-layer player still fine.** The ship still renders as three hires
   layers; with five-enemy waves the lower-screen pressure should be lighter
   than the previous six-enemy pattern.
10. **Regeneration is safe.** Re-run `build_levels.py` and `git diff` — it
    should be empty. Level 1 now comes from `level.json`.

**Branch `experimental-three-layer-player`. Not committed, tagged, merged or
pushed.**
