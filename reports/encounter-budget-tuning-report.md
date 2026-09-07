# Encounter-budget tuning pass — final report

PAL C64 shooter/engine · branch `multicolour-with-turrets-experiment`
Small gameplay-policy refinement of the uncommitted Phase-2 encounter budget.
No renderer / scheduler / scroller / turret-rendering / suppression redesign.
**Not committed. Not pushed.**

---

## 1. Starting state

| | |
|---|---|
| branch | `multicolour-with-turrets-experiment` |
| HEAD | `dab89dc` "Re-validate stage-widening checkpoint" (parent `3dfe4c4` widening, `fff83be`) |
| working tree at start | `src/main.asm` modified (+246/-1) + untracked `docs/encounter-budget-worklog.md`, `tools/vice_encounter_fixtures.py`, `tools/check_encounter_load.py` |
| difference vs previous Phase-2 report | `SCROLL_FRAME_DIVIDER` was already `2` (the previous report left it at `1`; task step A anyway asks for `2`). All other Phase-2 code identical to the previous report. Not a material/unexpected divergence — proceeded. |

Read: `AGENTS.md`, `docs/encounter-budget-worklog.md`, the full Phase-2 diff, the
encounter-policy implementation and the wave/spawner logic in `src/main.asm`.

---

## 2. Files changed

- **`src/main.asm`** only (the tuning pass adds ~+50 lines net over the Phase-2 state).
- Updated tests/docs (untracked): `tools/vice_encounter_fixtures.py` (rewritten
  A–R), `tools/check_encounter_load.py` (rename + `WAVE_START_DEFERRED` +
  per-frame `WAVE_ENEMY_COUNT`), `docs/encounter-budget-worklog.md`.
- **`src/background_turrets.asm` and `src/raster_scheduler.asm` NOT modified.**

---

## 3. `SCROLL_FRAME_DIVIDER` final value

**`2`** (`src/main.asm:108`). Divider 1 is retained only as an explicit
stress-test configuration; the source is left at 2. Scroll algorithm and
fine/coarse semantics unchanged; not adaptive.

---

## 4. Exact normal-wave-size rule

`startRandomWave` stores **`WAVE_ENEMY_COUNT = NORMAL_WAVE_SIZE (5)` unconditionally**:

```asm
    lda #NORMAL_WAVE_SIZE
    sta WAVE_ENEMY_COUNT
```

The authored `attackEnemyCount` table is untouched (still holds 5s and 6s) for
future boss/set-piece directors. Two compile-time guards (next to the attack
tables) assert, for every attack `i`:

```asm
.if (attackEnemyCountData.get(i) < NORMAL_WAVE_SIZE) { .error "... fewer than NORMAL_WAVE_SIZE authored members" }
.if ((attackSpriteStartData.get(i) + NORMAL_WAVE_SIZE) > ENEMY_SPRITE_SEQUENCE_LEN) { .error "... visual window cannot hold NORMAL_WAVE_SIZE members" }
```

so a normal wave can never read past a formation's data.

---

## 5. Do any authored formations contain fewer than five valid members?

**No.** `attackEnemyCountData = {6,6,5,5,6,6,6,5,5,6,5,5}` — minimum 5.
`attackSpriteStartData = {0,8,16,24,...}` — worst case `24 + 5 = 29 ≤ 32`
(`ENEMY_SPRITE_SEQUENCE_LEN`). All 12 attacks pass both new build guards; the
build is clean. Forcing exactly five is safe for every current attack.

---

## 6. Exact whole-wave deferral behaviour

In `updateSpawner`, once the current wave is complete (`WAVE_SPAWNED >=
WAVE_ENEMY_COUNT`) and its inter-attack gap has elapsed:

```asm
!mayStart:
    lda TURRET_PRESSURE_ACTIVE
    beq !startNext+                 ; no pressure -> start the next full wave
    ; POLICY_DIAG: inc WAVE_START_DEFERRED (16-bit)
    lda #1
    sta WAVE_GAP_TIMER             ; re-check next frame; DO NOT call startRandomWave
    rts
!startNext:
    jsr startRandomWave
```

While `TURRET_PRESSURE_ACTIVE`: `startRandomWave` is not called, so
`WAVE_ENEMY_COUNT` / `WAVE_SPAWNED` / `WAVE_SPRITE_INDEX` are not reset and no
member spawns. Nothing is despawned or marked spawned. When pressure clears the
very next `updateSpawner` starts a complete five-enemy wave. `WAVE_START_DEFERRED`
counts the held frames (diagnostic).

The **per-member** spawn gate from the previous implementation
(`countActiveEnemies >= TURRET_ENEMY_LIMIT` → hold) is **removed**, and
`TURRET_ENEMY_LIMIT` is **deleted**.

---

## 7. Does an in-progress wave always complete?

**Yes.** `updateSpawner`'s first test is `WAVE_SPAWNED < WAVE_ENEMY_COUNT →
!waveActive` (spawn the next member at the normal `WAVE_SPAWN_INTERVAL`). Turret
pressure is only consulted on the `!mayStart` path, which is unreachable until
the current wave has emitted all five members. A wave that has begun spawning is
never truncated, its members are never culled, and the director never advances to
the next wave early. Fixture **K** proves: mid-wave (2/5 spawned) + pressure
activates → `WAVE_SPAWNED` reaches 5, exactly +3 enemies, no dip in active-enemy
count during completion.

---

## 8. Exact turret-pressure condition

`updateTurretPressure`, once per frame after
`positionBackgroundTurrets`/`pulseTurretColour`:

```
TURRET_PRESSURE_ACTIVE = 1  iff  EXISTS turret t with
      TURRET_VISIBLE[t] != 0        (full body inside the raster-72..231 aperture; unchanged meaning)
  AND TURRET_HEALTH[t]  != 0        (alive)
  AND TURRET_Y[t] < TURRET_PRESSURE_MAX_Y   (= 180; existing screen-space Y, no world-row maths)
```

3-iteration scan, ~40 cycles. `TURRET_VISIBLE` is not redefined. A turret that is
alive + visible but at `Y >= 180` reports `TURRET_PRESSURE_ACTIVE = 0` yet keeps
firing / colliding / taking damage exactly as before.

---

## 9. Exact threshold comparison at Y = 179 / 180

```asm
    lda TURRET_Y,x
    cmp #TURRET_PRESSURE_MAX_Y      ; #180
    bcs !next+                      ; TURRET_Y >= 180  -> this turret exerts NO pressure
    ...                             ; TURRET_Y <  180  -> pressure
```

- `TURRET_Y = 179` → `bcs` not taken → **pressure active** (fixture E).
- `TURRET_Y = 180` → `bcs` taken → **pressure inactive** (fixture F).
- `TURRET_Y = 200` → pressure inactive (fixture G).

---

## 10. Shooter budgets

`refreshShooterBudget` (each enemy-fire tick):

```asm
    lda TURRET_PRESSURE_ACTIVE
    beq !normal+
    lda #TURRET_SHOOTER_BUDGET      ; 1
    ...
!normal:
    lda #NORMAL_SHOOTER_BUDGET      ; 2
```

- Normal mobile-shooter budget: **2** (`NORMAL_SHOOTER_BUDGET`).
- Turret-pressure mobile-shooter budget: **1** (`TURRET_SHOOTER_BUDGET`).
- The 1-shooter limit now follows `TURRET_PRESSURE_ACTIVE`, i.e. alive + visible
  + `Y < 180` — not merely alive + visible. Turret at Y=150 or Y=179 → max 1
  mobile shooter; turret at Y=180 or Y=200 → normal max 2. Existing hostile
  bullets are untouched across the transition (fixture O).

---

## 11. Does `TURRET_ENEMY_LIMIT = 3` remain?

**No — removed.** Its sole use was the per-member spawn gate that produced the
sparse partial formations. Formation integrity (always 5) now takes priority.
Conservative turret encounters are preserved by (a) holding the *start* of the
next wave while pressure is active and (b) the 1-shooter pressure budget.

---

## 12. Did turret firing cadence change?

**No.** `TURRET_FIRE_INTERVAL = 100` (`src/background_turrets.asm:15`),
unchanged. That file was not modified. Fixture **R** confirms the turret fires a
shot both below (Y=150) and above (Y=200) the pressure threshold.

---

## 13. Fixture results — `tools/vice_encounter_fixtures.py`

All 18 PASS (drives the real routines via a SEI;JSR trampoline):

| id | check | result |
|---|---|---|
| A | normal wave: `WAVE_ENEMY_COUNT` == exactly 5 (48 draws) | PASS — observed {5} |
| B | authored 6-enemy attack selected → presented as 5 | PASS — table still has 6s, observed {5} |
| C | no normal wave has effective count 1–4 | PASS — observed {5} |
| D | turret alive+visible Y=100 → pressure active | PASS |
| E | turret alive+visible Y=179 → pressure active | PASS |
| F | turret alive+visible Y=180 → pressure INACTIVE | PASS |
| G | turret alive+visible Y=200 → pressure INACTIVE | PASS |
| H | turret dead (HP0) Y=100 → pressure inactive | PASS |
| I | turret offscreen (VISIBLE 0) → pressure inactive | PASS |
| J | pressure active before start → whole 5-wave START deferred (12 held frames, 0 spawned), then starts when pressure clears | PASS |
| K | pressure activates mid-wave (2/5) → completes to 5, +3 enemies, no cull (min-during == before) | PASS |
| L | pressure clears at Y≥180 → next complete 5-wave eligible | PASS |
| M | 5 active enemies, normal → ≤2 distinct mobile shooters | PASS |
| N | 5 active enemies, pressure → ≤1 distinct mobile shooter | PASS |
| O | 3 existing hostile bullets survive 4 pressure transitions | PASS |
| P | `ENEMY_BULLET_COUNT` / real bullet objects never exceed 3 | PASS |
| Q | no encounter-policy call despawns / kills an enemy | PASS |
| R | turret fires at Y=150 AND at Y=200 (threshold does not gate firing) | PASS |

Hostile-projectile presentation-suppression fixtures **A–J: all PASS**.

---

## 14. Observed wave-size range (normal scrolling director)

`WAVE_ENEMY_COUNT` sampled every frame over a 3000-frame gameplay capture at
divider 2: **{5}**. `min_authored_wave_size = 5`, `max_authored_wave_size = 5`.

Wave size is read directly from the authored `WAVE_ENEMY_COUNT` contract, **not**
inferred from active-object count. Active mobile-enemy count (`max_active_enemies`
= 5) is reported separately.

---

## 15. Load metrics — divider 2, 3000 frames real gameplay

| metric | value |
|---|---|
| observed normal wave sizes (`WAVE_ENEMY_COUNT`) | {5} |
| minimum normal wave size | **5** |
| maximum normal wave size | **5** |
| maximum active mobile enemies | 5 |
| maximum designated mobile shooters | 2 |
| maximum hostile bullets | 3 |
| maximum `SORTED_COUNT` | 8 |
| frames with turret pressure active | 1017 / 3000 (~34 %) |
| whole-wave STARTS deferred by turret pressure | 134 |
| individual formation-member spawn deferrals | **0** |
| coarse deferral count | 0 |
| longest consecutive coarse-deferral run | 0 |
| projectile presentation suppression TOTAL / RESOLVED / UNRESOLVED | 0 / 0 / 0 |
| raster service failures | 0 |
| sprite-start misses | 0 |
| `frame_cycle_deltas` | **[19656]** |
| `check_scroll_capture` matrix/pixel | 0 failures |

---

## 16. Divider-1 stress metrics (1400 frames, then reverted to 2)

| metric | value |
|---|---|
| `frame_cycle_deltas` | **[19656]** |
| coarse deferrals | 0 |
| longest consecutive deferral run | 0 |
| projectile presentation suppression | 0 |
| raster service failures | 0 |
| sprite-start misses | 0 |
| observed wave sizes | {5} |

Source restored to `SCROLL_FRAME_DIVIDER = 2` and rebuilt afterward.

---

## 17. Coarse-deferral / suppression metrics (both configs)

No coarse deferrals and no presentation suppressions were observed in the
plain 3000-frame (divider 2) or 1400-frame (divider 1) gameplay captures. The
renderer/scroller safety nets remain in place and were simply not exercised —
which is the intended outcome of the calmer authored load.

---

## 18. Raster service / sprite-start

`check_raster_capture`: `service_failure_count 0`, `sprite_start_miss_count 0`,
`frame_cycle_deltas [19656]` on the divider-2 25-row trace capture and the
divider-1 stress capture.

---

## 19. Frame cadence

`frame_cycle_deltas == [19656]` on **every** capture in this pass: 25-row
(divider 2), 3000-frame load (divider 2), 1400-frame stress (divider 1),
400-row full wrap.

---

## 20. 400-row stage-addressing regression

- Host arithmetic oracle `check_stage_addressing.py`: PASS.
- Real-6502 decode probe on a 400-row build (4000-byte map): byte-exact to
  logical row 1599; `wrapBgLogicalRow` correct for out-of-range inputs.
- 400-row seeded 1000-frame full-stage wrap: `failure_count 0`, `stage_loops 1`,
  `first_transition_ok true`, `stage_step_errors []`, `frame_cycle_deltas
  [19656]`, 53.8M pixel checks.

**Intact.**

---

## 21. Turret regression

- Turret >255 world-row fixture (`turretRows 255/260/1024` on a 400-row stage):
  PASS — position/visibility, glyph install, colour pulse + restore, hit/destroy.
- `check_turret_capture` on the 25-row divider-2 capture: `failure_count 0`,
  `deferrals 0`, `dead_reentries [0,0,0]`.
- Fixture R: turret fires below and above the pressure threshold.
- `src/background_turrets.asm` unchanged — static rendering, pulse, hit/death/
  restoration and aim-at-fire-time are byte-identical to HEAD.

---

## 22. PRG / D64 (human-test build, divider 2)

| | |
|---|---|
| PRG path | `build/shooter.prg` |
| PRG SHA256 | `e6855c7a1b20664e8fd10935198b964761dd8ac4736d2a1b92af4530d6c4feab` |
| D64 path | `build/shooter.d64` |
| D64 SHA256 | `958088fe352b1d45e9074ccd065f880cfaf1393c4a035dc73d7e2a2ce00443c9` |
| effective normal wave size | 5 (exactly, always) |
| normal shooter budget | 2 |
| turret-pressure shooter budget | 1 |
| turret pressure Y threshold | `TURRET_Y < 180` |
| turret firing interval | 100 (unchanged) |

Expected human-visible behaviour: scroll back to divider-2 speed; every ordinary
formation is a full five-enemy formation (no 1–4 partial waves from encounter
culling); turret sections are calmer because only one mobile enemy fires while a
turret is above Y=180; the next full formation can begin once a turret sinks to
Y≥180 even though it is still visible and still firing; background scrolling
remains smooth.

---

## 23. Source-control state

- **Not committed. Not pushed.** Phase-1 commits untouched.
- HEAD = `dab89dc`.
- Working tree: `src/main.asm` (modified) + untracked
  `docs/encounter-budget-worklog.md`, `tools/vice_encounter_fixtures.py`,
  `tools/check_encounter_load.py`, `reports/encounter-budget-tuning-report.md`.

---

## 24. Anything requiring human judgement

- Whether divider 2 + the shorter (Y<180) turret pressure window make turret
  sections feel threatening but fair.
- Whether `TURRET_PRESSURE_MAX_Y = 180` is the right cut-off (turret's own
  firing window is Y ∈ [88, 201); 180 leaves it ~21px of "still shoots, no
  longer throttles").
- Whether holding the *entire* next wave during pressure (vs. e.g. allowing it
  after a short grace) produces good pacing, or feels too quiet around long
  turret passes (`WAVE_START_DEFERRED = 134` over 3000 frames ≈ short holds).
- `TURRET_FIRE_INTERVAL` tuning is explicitly deferred to human testing.

---

## Explicit YES/NO

1. Is `SCROLL_FRAME_DIVIDER` restored to 2? **YES**
2. Are normal scrolling waves exactly five enemies? **YES** (`WAVE_ENEMY_COUNT = NORMAL_WAVE_SIZE = 5`, unconditional; observed {5} over 3000 frames)
3. Can turret pressure truncate a five-enemy wave to 1–4 enemies? **NO** (per-member gate removed; in-progress waves always complete — fixture K)
4. Is a new full wave deferred while meaningful turret pressure is active? **YES** (`updateSpawner` `!mayStart` gate; `WAVE_START_DEFERRED` counts it)
5. If a five-enemy wave has already begun, is it allowed to complete? **YES**
6. Is turret pressure active at Y=179? **YES**
7. Is turret pressure inactive at Y=180? **YES**
8. Does a visible/alive turret below the threshold keep functioning normally even though it no longer throttles encounters? **YES** (fixture R; no change to turret firing/HP/collision/rendering)
9. Is the normal mobile-shooter budget still 2? **YES**
10. Is the turret-pressure mobile-shooter budget still 1? **YES**
11. Is `TURRET_FIRE_INTERVAL` still 100? **YES**
12. Is `MAX_ENEMY_BULLETS` still 3? **YES**
13. Are renderer/scroller safety mechanisms unchanged? **YES** (suppression, one-omission-per-frame, no player/enemy suppression, `SORTED_COUNT>=8` mitigation, coarse admission gate, BUILD/LIVE, raster IRQ, multiplexer, coarse split — all untouched)
14. Is exact PAL cadence still 19656? **YES** (`frame_cycle_deltas == [19656]` on every capture)
15. Does 400-row stage support still pass? **YES** (decode probe + full wrap + turret >255)
16. Is the divider-2 human-test build ready? **YES** — `build/shooter.prg`, SHA256 `e6855c7a1b20664e8fd10935198b964761dd8ac4736d2a1b92af4530d6c4feab`

---

## Stop conditions

None triggered. Every authored formation has ≥ 5 valid members; no
renderer/scheduler change was needed; no destructive despawning; turret
rendering / projectile suppression / coarse-scroll gate / cadence / 400-row
addressing / raster service all preserved; the background-graphics hitch did not
return (0 coarse deferrals, 0 suppressions, exact cadence).
