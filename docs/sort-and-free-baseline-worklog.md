# Sorter fix + FREE-disable production baseline

Bounded task following the Codex scroll-hitch investigation
(docs/scroll-hitch-worklog.md / docs/scroll-hitch-investigation.md, untracked).
Two independently justified changes only; then re-measure the hitch.

Branch `multicolour-with-turrets-experiment`, HEAD
`d96eb7cc60d681c9b703ac4c0fc776d7ef90ea6f`. Clean tree at start (Codex
diagnostics untracked). No commits/pushes.

## Task A - current tree verified
- Branch/HEAD match the handoff exactly.
- Baseline production PRG SHA-256
  `955708c0bdb5868c26415466d51f4fa6c2287cedbe553e8c4a518183ea9191ad`
  (== build/scroll-hitch/baseline.prg).
- Score-defer fix present: `SCORE_DIRTY`, `awardKillScore` (binary score +
  dirty flag only), `refreshScoreIfDirty` after `prepareBackgroundCoarse`.
- SORTED_COUNT>=8 turret-fire mitigation present (behind
  `#if !TURRET_FIRE_NO_MITIGATION`, default on).
- `updateCycleDebug` in the frame path (gameLoop, after
  `buildBatchSpriteSchedule`, before `prepareBackgroundCoarse`);
  `displayCycleMinimum` called from it every 50th frame.
- Main frame ordering matches the handoff exactly.
- `sortObjectsByY` progression bug CONFIRMED (see Task B).

## Task B - insertion-sort progression bug + fix

Bug: `!outer` loads Y = outer input index, saves the key, then `dey` and the
`!inner` shift loop walks Y DOWN through the sorted prefix. `!next` then does
`iny / iny` from wherever the shift stopped:
- front insertion (Y == $ff after the shift) -> `iny iny` -> Y = 1 -> the whole
  pass restarts;
- mid insertion at position j -> Y = j+2, which re-scans the sorted prefix
  whenever j < outer-1.
Output stays correct and stable (re-inserting into a sorted prefix is a no-op),
but the wasted re-scans cost CPU right before `prepareBackgroundCoarse`.

Fix (src/main.asm sortObjectsByY, src/variables.asm):
- New ZP scratch `TEMP_SORT_I = $0033` (the one free byte in the $2e..$36
  scratch block; referenced nowhere else in src, including the raster IRQ, and
  the IRQ replay path's renderSprites save/restore list does not touch it).
- `!outer` first instruction: `sty TEMP_SORT_I` (capture the outer INPUT index
  before `dey`).
- `!next`: `ldy TEMP_SORT_I / iny` instead of `iny / iny` - resume from the
  input index, advance exactly once.
Inner loop, insert logic, tie handling (`bcc`/`beq !insert` -> stable),
membership and list layout all unchanged. Not a sort-algorithm change.

### Task D - direct sort A/B (tools/vice_sort_verify.py, fresh VICE, IRQ off)
baseline.prg (955708c0) vs candidate build/shooter.prg, 1703 trials each:
counts 0..16; sorted / reverse / all-equal / paired-ties / random-heavy-ties;
player id 0 at every position; random shuffles + random Y.

| metric | baseline | candidate |
|---|---|---|
| stable-order failures | **0 / 1703** | **0 / 1703** |
| worst-case cycles | 10673 | **4373** |
| by count 16 (min..max) | 818..10673 | 878..4373 |
| by count 8  (min..max) | 394..2641  | 422..1185 |
| trivial-case overhead | - | +4..+60 cyc (sorted input) |

Identical stable output on every trial. Worst-case cost 10673 -> 4373
(max saved 6300). Small fixed overhead on already-sorted input; large saving
on the layouts that actually cost time. Codex measured 7396->3302 over a
narrower distribution; this broader battery (incl. 16-object reverse) shows a
bigger swing and the same zero mismatches.

## Task C - FREE cycle diagnostic disabled

`jsr updateCycleDebug` in gameLoop is commented out with a full explanation
(one line to restore). `updateCycleDebug`, `displayCycleMinimum`,
`setupDebugDisplay` and all `DEBUG_*` symbols/counters are left in the source
(tooling links); they are simply never called during a gameplay frame.
`DEBUG_SHOW_FREE_CYCLES` unchanged. `setupDebugDisplay` still runs once at init
(zeroes counters, sets rolling min to $ffff); `initFixedHud` still paints the
static "FREE 00000" label. No replacement formatting added.

### Task D - FREE non-execution proof
- Static: the only `jsr updateCycleDebug` is commented; `jsr displayCycleMinimum`
  exists only inside `updateCycleDebug` (now unreachable).
- Runtime: 2000 breakpoint stops during steady gameplay with breakpoints on
  `updateCycleDebug`, `displayCycleMinimum` and `prepareBackgroundCoarse`:
  updateCycleDebug 0, displayCycleMinimum 0, prepareBackgroundCoarse 2000.
- `DEBUG_MIN_LO/HI` stays `$FFFF` (its `setupDebugDisplay` init value) after
  1500 gameplay frames -> the rolling-min sample code never executed.
- `updateCycleDebug` only ever wrote private `DEBUG_*` ZP and (via
  `displayCycleMinimum`) the 5 FREE HUD glyph cells; it read only
  `VIC_CONTROL_1`/`RASTER`. Removing its call cannot touch game state, score,
  scroll, BUILD/LIVE, the raster scheduler or turrets - only the FREE digits
  (now static) and the DEBUG_* ZP (now static).

## Build
Clean, all guards pass. New PRG SHA-256
`b2a453aa5164284f2e03ab6c9dfa91ce776b8cf575ca07b4ef95763935e268da`.
Memory map: `$2000-$23f7`, `$2920-$2c99`, `$4000-$5841`, `$6000-$634f`,
turrets `$8800-...` - protected regions unchanged.

## Task E - new 8-case hitch baseline: RUNNING
tools/vice_scroll_hitch.py passive trace, 3500 frames/case, candidate build,
fresh snapshot build/scroll-hitch/start-candidate.vsf. Classification via
check_scroll_hitch.py (exact branch: batch-not-consumed / high-raster /
raster-deadline; consecutive run lengths; replay/catchup/incomplete counts).

## Task E - new 8-case hitch baseline (DONE)

Candidate build b2a453aa, 3500 frames/case (~1.45 stage circuits, ~145 coarse
transitions each), tools/vice_scroll_hitch.py passive trace +
check_scroll_hitch.py exact-branch classification.

| case | deferrals | stalls (lengths) | cause (batch / deadline / high) | cadence | max_active | replay | turret shots/opps |
|---|---|---|---|---|---|---|---|
| movement      | 0  | -        | -            | [19656] | 3  | 0 | 0/0 |
| enemy-nofire  | 0  | -        | -            | [19656] | 9  | 0 | 0/0 |
| fire-no-kills | 17 | 1 (17)   | 16 / 1 / 0   | [19656] | 9  | 0 | 9/13 |
| hits-kills    | 5  | 1 (5)    | 5 / 0 / 0    | [19656] | 9  | 0 | 4/5 |
| explosions    | 12 | 3 (8,3,1)| 12 / 0 / 0   | [19656] | 9  | 0 | 6/7 |
| turret-heavy  | 0  | -        | -            | [19656] | 3  | 0 | 9/13 |
| bullet-heavy  | 0  | -        | -            | [19656] | 7  | 0 | 0/0 |
| combined      | 16 | 1 (16)   | 15 / 1 / 0   | [19656] | 10 | 0 | 6/8 |
| TOTAL         | 50 | 6 stalls | 48 / 2 / 0   | [19656] | -  | 0 | - |

- All 8: cadence exactly [19656], 0 replay/catchup, 0 check failures (hostile
  bullet cap <=3, player slot 0, BUILD/LIVE ownership, trace-clock all verified).
- Every multi-frame stall is BATCH-NOT-CONSUMED: a hostile projectile (or the
  player sprite reassigned to a slot) sits low on screen (Y 212..245) so the 9th
  sprite needs a multiplex batch whose earliest slot release / compare is
  204..232 - past the raster-184 coarse cutoff. It defers every frame until the
  object leaves (sorted 9 -> 8). This is Codex's proven architecturally
  unavoidable class (Task G): no slot choice or compare retiming makes a
  release>=184 batch compatible with a cutoff<184. NOT chased.
- vs Codex HEAD baseline (same 8 cases): high-raster 5 -> 0; raster-deadline
  (CPU-only) 14 -> 2. The sort fix + FREE-disable removed essentially all
  CPU-lateness deferrals.

## Task F - CPU-only multi-frame stall: NONE remaining

The only two raster-deadline (CPU-only, outstanding_batches=0) deferrals are
single isolated frames embedded inside longer batch-gate stalls
(fire-no-kills f1945 admit 213; combined f1177 admit 219), not a standalone
consecutive CPU hold. Codex's combined 5975..5978 class did not recur.

Routine timing for the worst one (combined f1177, prepare reached raster 219 vs
~160 on neighbours f1176/f1178):
  updateObjects entry 32:62 (same as neighbours) but updateEnemyFire entry
  129:43 vs 77:42 -> ~52 raster lines (~3300 cyc) added INSIDE updateObjects.
  f1177 has one non-fatal hitscan hit on enemy 4; the damage path runs
  updateEnemyHealthSprite (a 64-byte base-sprite clone on every non-fatal hit -
  Codex's separate finding). Everything downstream shifts by that ~52 lines so
  prepare crosses 184. Single frame; not a multi-frame CPU stall.
  updateEnemyHealthSprite optimisation is explicitly out of scope for this task.

## Task H - full regression (candidate b2a453aa)

Fresh 2700-frame --physical --trace capture (build/mc-test/sortfree-scroll):
- check_fixed_hud_capture : 0 failures, cadence [19656], MC model + terrain
  colour RAM + matrix + edge-motion all pass, 158.5M pixel checks, 112 coarse
  = 1.12 circuits. FREE field validates as static "FREE 00000" (label +
  in-range private digits) - structural HUD check unaffected.
- check_scroll_capture    : 0 failures, 144.9M MC pixel checks, stage_loops 2,
  0 stage-step errors, cadence [19656].
- check_scroll_edges      : 0 failures, 33.6M edge checks, 112 coarse pairs.
- check_raster_capture    : 0 service failures, 0 sprite-start misses,
  0 catchups, 0 replay frames, cadence [19656].
- check_turret_capture    : 0 failures (player slot 0, bullet cap, coarse all
  pass). FREE stat now reports "disabled" instead of crashing on the empty
  sample set - the only test change, turret correctness checks untouched.
- check_viewport_capture  : 0 failures (viewport_edges, clip_eight solid).
- vice_turret_cases       : 45 checks, 0 failures. Turret CPU unchanged.
- vice_raster_lifecycle   : 0 failures, gameplay jiffy drift 0, turret reset ok.
- vice_raster_cases       : 11 scheduler cases (early24/late243/eight/close4/
  overlap55/coarse_late_dma/coarse_sparse_dma/zero/one/viewport_edges/
  clip_boundary) - 0 service failures, 0 sprite-start misses, cadence [19656].
- vice_turret_kill_timing : score-defer fix intact - fatal-hit path flat 75 cyc,
  0/40 fatal-only deferrals.
- vice_turret_stall_ab (candidate, 6000f): nofire 8 deferrals [4,4] all
  batch-not-consumed, 18 turret shots; fire 19 [19] all batch. SORTED_COUNT
  mitigation unchanged and still active.
- direct sort A/B (vice_sort_verify.py): 0 stable-order failures on either
  build over 1703 trials; worst-case cycles 10673 -> 4373.

Required invariants: frame_cycle_deltas == [19656] everywhere; 0 replay frames;
0 raster service failures; 0 sprite-start misses; safe coarse-deferral gate
untouched; player logical slot 0 unchanged; BUILD/LIVE ownership unchanged;
MAX_ENEMY_BULLETS still 3; sorted-list membership unchanged. All hold.

## Baseline finding NOT fixed (as instructed)
Codex noted applyLiveRasterBatch collision narrow-phase work can delay sprite
assignment writes (checkCapturedPlayerCollision reads logical OBJECT arrays in
the IRQ). Not observed as a sprite-start miss in these 8 candidate captures
(all 0), but this is a separate bounded investigation - not touched.

## Status: sorter progression fix + FREE runtime disable landed. Clean baseline
## established. Multi-frame stalls that remain are the proven batch-gate class.
## No commits/pushes.

## ================================================================
## FOLLOW-UP - presentation-only projectile suppression + static turrets + pulse
## ================================================================
## Starts from HEAD d186d5901d0ed... (sorter fix + FREE-disable committed as
## "bg-gfx stall identified, pre-fix commit"). Baseline PRG b2a453aa.
## New PRG for this pass: 03e4f7a95139ab36028ee5d7be898939be1d94722b92b78deeffa802a5bda7c0
## No commits/pushes.

### Task A/B - presentation-only hostile-projectile suppression

New routines in src/main.asm, in the $2920 background segment near
prepareBackgroundCoarse (main pre-$1f00 region was full):
- `planCoarseBulletSuppression` - called in gameLoop right AFTER
  buildBatchSpriteSchedule, BEFORE prepareBackgroundCoarse. If BG_COARSE_PENDING
  and the just-built BUILD plan has a batch with BATCH_RASTER >=
  BG_COARSE_LATEST_START (184) - a batch the IRQ cannot consume before the
  coarse copy would be admitted - it scans that batch's assignments for a
  TYPE_ENEMY_BULLET (never id 0 / player, never type 2 / enemy), picks the
  lowest-Y one (the constraint that binds BATCH_RASTER = min(ASSIGN_Y-12)),
  removes it from SORTED_OBJECTS (main-thread scratch), and re-runs
  buildBatchSpriteSchedule (idempotent; beginRasterPlanMasks fully rebuilds).
  It re-checks; RESOLVED if no obstructing batch remains, UNRESOLVED otherwise
  (the projectile stays omitted - strictly fewer sprites - and the existing safe
  deferral stands; it does NOT cascade into dropping more objects). NO_ELIGIBLE
  when the obstruction is a player/enemy assignment (nothing is dropped).
  Collision safety: on the omitted frame it runs the exact `checkBulletPlayerOverlap`
  test the IRQ path uses (guarded by DEBUG_PLAYER_INVULNERABLE, like the engine's
  own !hit), so a suppressed projectile can still hit the player.
- `noteCoarseSuppressionOutcome` - called right AFTER prepareBackgroundCoarse
  (which is UNTOUCHED). Counts DEFER_AFTER (a coarse deferral still happened on
  a suppression frame) and RETURNED (a previously omitted, still-active
  projectile presented normally again), and resets the consecutive-run tracker.

The logical projectile is never modified: still OBJECT_ACTIVE, still its type,
still moving, still in ENEMY_BULLET_COUNT / the 3-cap, normal lifetime, not
delayed/frozen/killed, re-rendered next presentation. Only its entry in the
main-thread SORTED_OBJECTS for one BUILD is removed; LIVE, the IRQ, and the
coarse-admission gate are untouched. BUILD/LIVE ownership preserved.

Instrumentation (SUPPRESS_* memory words/bytes in the background control block,
reset by initBackground; no HUD, no formatting): TOTAL, RESOLVED, UNRESOLVED,
NO_ELIGIBLE, DEFER_AFTER, RETURNED, LAST_ID, LAST_Y, LAST_PLAYER_Y, PREV_ID,
CONSEC, CONSEC_MAX, THIS_FRAME, PRE_DEFER. ~20 bytes. Per-frame cost on a
non-suppression frame: `lda BG_COARSE_PENDING / beq` (or the BATCH_COUNT==0
exit) - a few cycles. Real work only on the rare obstruction frame.

### Task I - deterministic fixtures A-J (tools/vice_suppress_fixtures.py): ALL PASS
- A (8 sprites): batch_count 0, no suppression.
- B (9 sprites, 9th a HIGH bullet, BATCH_RASTER 138 < 184): no suppression.
- C (9th a LOW bullet, BATCH_RASTER 224): 1 suppression, RESOLVED, sorted 9->8,
  batch gone; bullet still active/type 3; ENEMY_BULLET_COUNT unchanged.
- D (player id 0 lowest, Y 238, BATCH_RASTER 226): 0 suppressions, NO_ELIGIBLE=1;
  the deferral would stand.
- E (enemy lowest, Y 236): 0 suppressions, NO_ELIGIBLE=1.
- F (two low bullets Y 230 + Y 244): exactly 1 suppression, UNRESOLVED=1
  (a batch at raster 232 remains); does not drop a second object.
- G (bullet overlapping the player): 1 suppression; bullet still active/type 3;
  checkBulletPlayerOverlap returns carry set -> collision still detectable.
- H (bullet survives, moves up next frame): re-run -> back in SORTED_OBJECTS,
  no second suppression -> rendered normally.
- I (bullet despawns): ENEMY_BULLET_COUNT 1 -> 0, object inactive.
- J (BG_COARSE_PENDING = 0): obstructing batch present, 0 suppressions.

### Task C/D - static turrets, aim-at-fire-time
src/background_turrets.asm: `updateBackgroundTurrets` `!visible` no longer calls
`aimBackgroundTurret`; the visible body is `TURRET_STATIC_STYLE = 4` (down-facing
turretArt) unless flashing from a hit (style 6) or destroyed (style 7).
`aimBackgroundTurret` kept in source (unreferenced by gameplay; still used by the
functional test). ALL other turret behaviour retained: HP, hit detection,
damage/hit-flash, death, underlay restore, stage wrap/reset, score,
fire-timer/cadence, shared projectile allocation, MAX_ENEMY_BULLETS=3, the
SORTED_COUNT>=8 turret-fire mitigation.
Aimed fire unchanged: `spawnEnemyBulletAt` already computes the full
player-relative X slope (chooseEnemyBulletSlope) from live OBJECT_X at spawn
time; TURRET_AIM never fed the projectile - it was glyph-only. A static turret
firing from the same spot at the same player position produces the identical
projectile vector.
CPU: `updateBackgroundTurrets` isolated cost 126..529 -> 126..452 (removed the
per-visible-turret 59..74-cyc aim calc). Net reduction.

### Task E/F - turret fourth-colour pulse
`pulseTurretColour` (called once/frame after positionBackgroundTurrets, ~raster
20, before any terrain colour badline): steps a restrained
white/red/yellow/red table (`turretPulseTable = 1,2,7,2`; bit 3 ORed in so the
cell stays multicolour; TURRET_PULSE_INTERVAL = 8 frames) and writes the current
value to exactly the 4 colour-RAM cells of each visible, alive turret (matrix
row from TURRET_Y - RASTER_DISPLAY_FINE; `cramRowLo/Hi` lookup). When a turret
changes matrix row (coarse step) the vacated 4 cells are restored to
TERRAIN_COLOUR_RAM first. $D021/$D022/$D023 and all non-turret colour RAM are
untouched (oracle confirms terrain colour RAM stays the single value 9).
All turrets pulse in phase. Colour changes only ~every 8 frames + on a row
change; ~4-12 colour-RAM writes/turret/step.
11-pixel coverage: turretArt style 4 is ~50%+ bit-pair-11 pixels (the $ff dome/
base rows), so the pulse is strongly visible; the $55/$54 barrel-detail rows are
$D022/$D023 and stay static. No glyph change needed.

### Task H - 8-case hitch results (3500 frames/case, candidate 03e4f7a9)

| case | prior (sort+FREE) | NEW | suppress TOTAL / RESOLVED / NO_ELIGIBLE / DEFER_AFTER | CONSEC_MAX |
|---|---|---|---|---|
| movement      | 0            | 0            | 0/0/0/0   | 0 |
| enemy-nofire  | 0            | 0            | 0/0/0/0   | 0 |
| fire-no-kills | 17 [17]      | 15 [11,3,1]  | 8/8/9/6   | 3 |
| hits-kills    | 5 [5]        | 2 [2]        | 2/2/0/2   | 2 |
| explosions    | 12 [8,3,1]   | 5 [5]        | 0/0/4/0   | 0 |
| turret-heavy  | 0            | 0            | 0/0/0/0   | 0 |
| bullet-heavy  | 0            | 0            | 0/0/0/0   | 0 |
| combined      | 16 [16]      | 0           | 0/0/0/0   | 0 |
| TOTAL         | 50, worst 17 | 22, worst 11 | - | - |

- All 8: cadence [19656], 0 presentation replays / catchups, 0 check failures
  (hostile bullet cap <=3, player logical slot 0, BUILD/LIVE {0,8}, trace-clock).
- combined: 16-frame stall -> 0 (mostly CIA-timing divergence: 0 suppressions;
  not a matched A/B).
- hits-kills 5->2, explosions 12->5, fire-no-kills 17 -> [11,3,1]: where a low
  HOSTILE PROJECTILE binds the obstructing batch, suppression clears it
  (RESOLVED); multi-frame freezes shrink to short holds.
- Remaining stalls: the obstructing batch is bound by a NON-projectile - the
  fire-no-kills 11-frame stall (frames 2327-2337) is bound by
  `(0, 1, 219)` = the PLAYER sprite low on screen (never suppressible); the
  explosions 5-frame stall is bound by a low exploding ENEMY (NO_ELIGIBLE=4).
  These are Codex's proven scheduler impossibility with a non-projectile late
  object; not addressable by this mechanism.
- DEFER_AFTER (fire-no-kills 6, hits-kills 2): the suppression + rebuild CPU on
  the suppression frame can push prepareBackgroundCoarse past 184, turning that
  one frame's batch-not-consumed defer into a raster-deadline defer. Net still a
  1-frame hold, then the next frame admits. Acceptable per the task (occasional
  safe deferral allowed; target is removal of visible multi-frame freezes).

### Task J - full regression (candidate 03e4f7a9, 2700-frame --physical --trace)
- check_fixed_hud_capture : 0 failures, 157.5M pixel checks, cadence [19656], MC
  model + matrix + edge-motion pass, ordinary terrain colour RAM = single value
  9 (turret pulse cells excluded from the fixed-colour check; validated instead
  as legal MC selectors + by charset integrity + check_turret_capture).
- check_scroll_capture    : 0 failures, 144.4M pixel checks, stage_loops 2.
- check_scroll_edges      : 0 failures, 33.6M edge checks.
- check_raster_capture    : 0 service failures, 0 sprite-start misses, 0 catchups,
  0 replay frames, cadence [19656].
- check_turret_capture    : 0 failures (positioning, HP, hit flash, death,
  underlay restore, wrap re-entry, shared bullet cap, player slot 0, coarse).
- check_viewport_capture  : 0 failures (viewport_edges, clip_eight, clip_boundary
  solid captures).
- vice_turret_cases       : 45 checks, 0 failures (hitscan/aim/fire/damage/
  destruction/underlay/cap). updateBackgroundTurrets CPU 126..452 (was ..529).
- vice_raster_lifecycle   : 0 failures, gameplay jiffy drift 0, turret reset ok.
- vice_raster_cases       : 9 scheduler cases - 0 service failures, 0 sprite-
  start misses, cadence [19656] each. (Legacy caveat: early24/player37/
  overlap55/late243 emit 0 batches under the current viewport filter and no
  longer exercise those numeric compares.)
- vice_turret_kill_timing : score dirty/deferred rendering intact - fatal-hit
  critical path flat 75 cyc, 0/40 fatal-only deferrals.
- sortObjectsByY direct A/B : 0 stable-order failures; worst-case 10673 -> 4373
  (unchanged - the corrected sort is not touched by this pass).

### Known separate issue (NOT fixed here, as instructed)
The two raster-deadline (CPU-only) deferrals per run - isolated single frames,
one still traceable to updateEnemyHealthSprite's 64-byte clone on a non-fatal
hit. Left for a separate bounded task. applyLiveRasterBatch collision-narrow-
phase: not observed as a sprite-start miss in these 8 candidate captures.

### Status: presentation-only projectile suppression + static turrets + fourth-
### colour pulse implemented and validated. All fixtures A-J pass. No STOP
### condition hit. No commits/pushes.
