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
