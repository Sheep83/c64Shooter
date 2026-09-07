# Calmer normal-scrolling encounter budget — worklog

Phase 2 of the overnight task. **Uncommitted** — reviewable in the working tree
for human playtest. HEAD is the stage-widening checkpoint (`dab89dc`, parent
`3dfe4c4`).

## Design intent

Normal scrolling gameplay is authored around a conservative sprite/presentation
budget. The multiplexer, `MAX_OBJECTS`, `MAX_ENEMY_BULLETS` and every renderer /
scheduler / coarse-scroll safety net are unchanged. These are **gameplay /
spawner / fire-policy limits**, structured so a future non-scrolling boss
director can raise or ignore them. No attempt to "solve" the mathematical
low-late-sprite vs coarse-deadline conflict.

## Changes (src/main.asm only)

| # | change | location |
|---|---|---|
| 1 | `SCROLL_FRAME_DIVIDER` 2 -> **1** (fastest contemplated scroll). Same algorithm, same fine/coarse semantics. `!defer` path stores `#SCROLL_FRAME_DIVIDER-1 = 0`; `updateBackgroundScroll` still retries next frame — no divide-by-zero / negative immediate. | line 101 |
| 2 | New consts: `NORMAL_MAX_FORMATION=5`, `NORMAL_SHOOTER_BUDGET=2`, `TURRET_SHOOTER_BUDGET=1`, `TURRET_ENEMY_LIMIT=3`, `ENEMY_SHOOTER_SLOTS=2`, `POLICY_DIAG=1` | ~line 26 |
| 3 | `startRandomWave`: clamp `WAVE_ENEMY_COUNT` to `NORMAL_MAX_FORMATION`. `attackEnemyCount` table keeps its authored 5/6 values for future boss/set-piece directors. | ~line 3746 |
| 4 | `updateEnemyFire`: `jsr refreshShooterBudget` at `!tryFire`; `jsr shooterEligible / bcc !next` gate before `spawnEnemyBullet`. | ~line 1997 |
| 5 | `updateSpawner`: at `!spawn`, if `TURRET_ENCOUNTER_ACTIVE` and `countActiveEnemies >= TURRET_ENEMY_LIMIT`, set `SPAWN_TIMER=1` and return — **non-destructive** hold (`WAVE_SPAWNED` untouched). | ~line 3900 |
| 6 | Frame loop: `jsr updateTurretEncounter` after `pulseTurretColour`. | ~line 456 |
| 7 | `init`: `jsr initEncounterPolicy`. | ~line 395 |
| 8 | New routines + state block in the `$2920` background-control segment: `updateTurretEncounter`, `refreshShooterBudget`, `shooterEligible`, `countActiveEnemies`, `initEncounterPolicy`, `ENCOUNTER_POLICY_BEGIN..END`. | before `BACKGROUND_CONTROL_END` |
| 9 | Post-`#import` guard: `.if (TURRET_COUNT != 3) .error` (updateTurretEncounter hardcodes `ldx #2` because the `.const` is not forward-resolvable there). | end of file |

Segment `$2920` now ends `$2f93` (was `$2e92`); guard `BACKGROUND_CONTROL_END >
HEALTH_SPRITE_BASE ($3000)` still holds (~109 B spare).

## Policy definitions

**Formation size** — `startRandomWave` stores `min(attackEnemyCount[id], 5)`.
Authored table unchanged (still has 6s), so a boss director reading the raw
table is unaffected.

**Normal mobile-shooter limit** — a 2-entry designated-shooter id list
(`ENEMY_SHOOTER_ID`). `updateEnemyFire` only lets a candidate fire if it is
already in the list within `ENEMY_SHOOTER_BUDGET`, or claims a free slot within
budget. `refreshShooterBudget` (each fire tick) prunes ids whose enemy is no
longer an active `TYPE_ENEMY`, so the two designated shooters roll over as the
formation cycles. Only one shot ever launches per `updateEnemyFire` call
(unchanged); the list caps how many *distinct* enemies get to be that shooter.

**"Turret active"** — `updateTurretEncounter`, once per frame after
`positionBackgroundTurrets`/`pulseTurretColour` set fresh state:
`TURRET_ENCOUNTER_ACTIVE = 1` iff any turret has `TURRET_VISIBLE != 0` (its full
16px body is inside the raster-72..231 combat aperture — the existing
per-frame flag) **and** `TURRET_HEALTH != 0`. A destroyed turret (`HP 0`) or a
turret hundreds of rows away (`VISIBLE 0`) imposes nothing. 3-iteration scan,
~30 cycles.

**Turret-active mobile-enemy limit** — `updateSpawner` defers a new spawn
(non-destructively; `SPAWN_TIMER=1`, retry next frame) while
`TURRET_ENCOUNTER_ACTIVE` and `countActiveEnemies() >= 3`. Existing enemies,
their movement and `WAVE_SPAWNED` are untouched; the wave resumes when active
mobile-enemy count falls back to budget.

**Turret-active mobile-shooter limit** — `refreshShooterBudget` sets
`ENEMY_SHOOTER_BUDGET = 1` while `TURRET_ENCOUNTER_ACTIVE`, so only slot 0 of
the designated-shooter list is consulted. A second shooter that was already
firing simply stops getting new turns; its live bullets are untouched.

**Turret cadence** — `TURRET_FIRE_INTERVAL` and all turret firing / HP / pulse
/ aim-at-fire-time / death / restoration code are **unchanged**.

## Instrumentation (`POLICY_DIAG = 1`, raw counters, no HUD/decimal)

`ENCOUNTER_POLICY_BEGIN..END` ($2e93, in the capture `.bg` dump range):
`TURRET_ENCOUNTER_ACTIVE`, `ENEMY_SHOOTER_BUDGET`, `ENEMY_SHOOTER_ID[2]`,
`ENEMY_ACTIVE_COUNT`, `POLICY_MAX_ENEMIES/BULLETS/SORTED`,
`POLICY_TURRET_FRAMES`, `ENEMY_SPAWN_DEFERRED`,
`ENEMY_FIRE_REJECT_NORMAL/TURRET`. Per-frame cost when enabled: ~15 cycles
(3 gauge compares); peak active-enemy / shooter counts are reconstructed by the
test tooling from the object dumps, not scanned in the frame.

## Validation

- Build clean. `frame_cycle_deltas == [19656]` on every capture.
- **Encounter fixtures** `tools/vice_encounter_fixtures.py` A..K: all PASS.
- **Suppression fixtures** `tools/vice_suppress_fixtures.py` A..J: all PASS.
- 25-row scroll/HUD/turret/raster capture (900 f, divider=1): 0 failures,
  cadence [19656], 0 deferrals, 0 sprite-start misses.
- 400-row decode probe + 1000-frame full wrap: PASS, cadence [19656],
  `stage_step_errors []`, stage_loops 1.
- turret >255-row fixture: PASS.
- **Load, 3000 frames real gameplay** (`tools/check_encounter_load.py`):

| metric | before (dab89dc, div 2, no policy) | after (div 1 + policy) |
|---|---|---|
| max active objects | 9 | 8 |
| max active enemies | 6 | 5 |
| max active hostile bullets | 3 (at cap) | 2 |
| max SORTED_COUNT | 8 | 8 |
| coarse deferral events | 0 | 0 |
| longest consecutive deferral run | 0 | 0 |
| suppression total | 0 | 0 |
| turret-encounter frames | n/a | 1305 / 3000 |
| enemy spawns deferred (turret) | n/a | 445 |
| fire opportunities rejected (normal / turret) | n/a | 5 / 7 |
| max designated shooters | n/a | 2 |

- `--stress` mode (forces the spawner to flood the pool every frame, defeating
  the policy — not a fair policy test): heavy deferral on both builds, cadence
  exactly [19656] on both; the policy build has *fewer* pixel-oracle transients
  (110 vs 135). These `check_scroll_capture` pixel hiccups pre-exist on HEAD.

## Human-test build

`build/shooter.prg` SHA256
`540d06fad55ef0f9491219c3227b5988826c299f133487d5c56956b28e8c46be`.
divider=1, policy enabled, real 25-row bas-relief stage.

## Not done / notes

- Turret cadence deliberately left alone (§17) — human to tune.
- No boss mode, no multiplexer change, no global 5-enemy engine cap (§18).
- Phase 2 stays uncommitted.

---

# Tuning pass (post human playtest)

## Human test results feeding this pass

1. Background-graphics hitching is essentially gone / imperceptible.
2. `SCROLL_FRAME_DIVIDER = 1` is very smooth but too fast — background turrets
   sink below a useful firing position before they arm, so they rarely threaten.
3. `SCROLL_FRAME_DIVIDER = 2` gives turrets enough screen time and is still
   acceptably smooth. **Divider 2 is now the intended gameplay value.** Divider 1
   is retained as an explicit engineering / stress-test config only.
4. Dynamically shrinking a normal wave to 1/2/3/4 enemies looks wrong/sparse.
   **Every normal scrolling wave must present as a complete five-enemy
   formation.** Partial 1–4 waves are prohibited.
5. Turret throttling started too early / lasted too long (whole visible life of
   the turret). Once a turret sinks to ~Y >= 180 it has no useful firing
   solution and should stop suppressing the next wave.

## Changes made (src/main.asm only)

| # | change |
|---|---|
| A | `SCROLL_FRAME_DIVIDER` 1 -> **2** (already 2 in the tree when this pass started; comment corrected). |
| B | `startRandomWave` now stores `WAVE_ENEMY_COUNT = NORMAL_WAVE_SIZE (5)` **unconditionally** (was `min(attackEnemyCount, 5)`). Every normal wave is exactly 5. |
| B | New build guards: every `attackEnemyCount` entry `>= NORMAL_WAVE_SIZE`, and every attack's visual window holds `>= NORMAL_WAVE_SIZE` entries. **All 12 authored attacks pass** (min authored count = 5; `attackSpriteStart` max 24, 24+5 = 29 <= 32). |
| C | `TURRET_ENCOUNTER_ACTIVE` renamed `TURRET_PRESSURE_ACTIVE`; `updateTurretEncounter` renamed `updateTurretPressure` and now also requires `TURRET_Y < TURRET_PRESSURE_MAX_Y (180)`. Reads only the existing screen-space `TURRET_Y`; no world-row / stage-map work; `TURRET_VISIBLE`'s meaning is unchanged. |
| C/6 | New `.const TURRET_PRESSURE_MAX_Y = 180`. Comparison: `lda TURRET_Y,x / cmp #180 / bcs !next` — `Y < 180` => pressure; `Y >= 180` => no pressure (`Y=179` pressure, `Y=180` no pressure). Turret firing / collision / HP are untouched by the threshold. |
| 7/8 | `updateSpawner`: **removed** the per-member `!spawn` gate (`countActiveEnemies >= TURRET_ENEMY_LIMIT` -> hold). `.const TURRET_ENEMY_LIMIT` **deleted**. New gate at the wave-start point only: while `TURRET_PRESSURE_ACTIVE`, do not call `startRandomWave`; bump `WAVE_START_DEFERRED`; set `WAVE_GAP_TIMER = 1` and retry next frame. An in-progress wave (`WAVE_SPAWNED < WAVE_ENEMY_COUNT`) always continues to 5 — the pressure branch is only reachable after the current wave is complete. |
| D/9 | `refreshShooterBudget` unchanged in logic; it now keys off `TURRET_PRESSURE_ACTIVE`, so the 1-shooter limit follows the Y<180 window, not alive+visible. Normal budget 2; pressure budget 1. |
| — | `countActiveEnemies` + `ENEMY_ACTIVE_COUNT` retained as a utility the fixtures call directly; no longer in the frame path. `POLICY_MAX_ENEMIES` therefore not auto-updated (tooling computes peak enemies from object dumps). New diag `WAVE_START_DEFERRED` (.word); `ENEMY_SPAWN_DEFERRED` kept as an "expected 0" proof that member dribble no longer happens. |
| 10 | `TURRET_FIRE_INTERVAL` **unchanged at 100** (`src/background_turrets.asm` not touched). |

`src/background_turrets.asm` and `src/raster_scheduler.asm` NOT modified.
Segment `$2920` now ends `$2f9c` (guard `> $3000` still holds).

## TURRET_ENEMY_LIMIT verdict

Removed. Its only purpose was to stop individual formation members spawning once
three enemies existed — exactly the mechanism that produced the visually sparse
1→2→3→stall partial formations. Formation integrity (always 5) now takes
priority. Turret encounters stay conservative because (a) no *new* wave starts
while pressure is active and (b) only one mobile enemy may fire.

## Fixture results — `tools/vice_encounter_fixtures.py` (all PASS)

A wave size == 5 · B authored-6 presented as 5 · C no 1–4 wave · D Y=100 pressure ·
E Y=179 pressure · F Y=180 no pressure · G Y=200 no pressure · H dead no pressure ·
I offscreen no pressure · J pressure-before-start defers the whole 5-wave (12
defers, nothing spawned) then starts when pressure clears · K pressure mid-wave
-> wave completes to 5, exactly +3 enemies, min-during unchanged (no cull) ·
L pressure clear (Y>=180) -> next wave eligible · M normal 5 enemies <=2 shooters ·
N pressure 5 enemies <=1 shooter · O 3 bullets survive 4 pressure transitions ·
P bullet cap <=3 · Q no policy call despawns an enemy · R turret fires 1 shot both
at Y=150 and Y=200.

Suppression fixtures A–J: all PASS.

## Load — 3000 frames real gameplay, divider = 2

| metric | value |
|---|---|
| authored wave sizes observed (`WAVE_ENEMY_COUNT`) | **{5}** (min 5, max 5) |
| max active mobile enemies | 5 |
| max designated mobile shooters | 2 |
| max active hostile bullets | 3 |
| max `SORTED_COUNT` | 8 |
| frames with turret pressure active | 1017 / 3000 (~34%) |
| whole-wave STARTS deferred by pressure (`WAVE_START_DEFERRED`) | 134 |
| individual formation-member spawn defers (`ENEMY_SPAWN_DEFERRED`) | **0** |
| coarse deferral events | 0 |
| longest consecutive coarse-deferral run | 0 |
| projectile presentation suppression TOTAL / RESOLVED / UNRESOLVED | 0 / 0 / 0 |
| raster service failures | 0 |
| sprite-start misses | 0 |
| `frame_cycle_deltas` | [19656] |

## Divider-1 stress pass (1400 frames, then reverted to 2)

`frame_cycle_deltas [19656]`; coarse deferrals 0; longest run 0; suppression 0;
raster service failures 0; sprite-start misses 0; wave sizes all 5. Source left
at `SCROLL_FRAME_DIVIDER = 2`.

## Regression

- Build clean; `frame_cycle_deltas == [19656]` everywhere.
- 25-row scroll/HUD/multicolour/matrix/pixel (900 f, divider 2): 0 failures.
- 400-row decode probe + 1000-frame full wrap: PASS, `stage_step_errors []`,
  cadence [19656]. Turret >255-row fixture: PASS.
- `check_turret_capture` / `check_fixed_hud_capture` / `check_raster_capture`:
  0 failures.
- Host stage-addressing oracle: PASS.

## Human-test build (tuning pass)

`build/shooter.prg` SHA256
`e6855c7a1b20664e8fd10935198b964761dd8ac4736d2a1b92af4530d6c4feab`
`build/shooter.d64` SHA256
`958088fe352b1d45e9074ccd065f880cfaf1393c4a035dc73d7e2a2ce00443c9`
divider=2, `NORMAL_WAVE_SIZE=5`, `NORMAL_SHOOTER_BUDGET=2`,
`TURRET_SHOOTER_BUDGET=1`, `TURRET_PRESSURE_MAX_Y=180`,
`TURRET_FIRE_INTERVAL=100`. Real 25-row bas-relief stage.

Phase 2 stays uncommitted. HEAD unchanged at `dab89dc`.
