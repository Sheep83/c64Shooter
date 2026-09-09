# Stage 4D — Incremental Inactive-Screen Construction — worklog

Branch `experimental-border-hud`. Task: build the exact next coarse-scroll screen
state incrementally in the INACTIVE character page, byte-correct and cheap enough
for a later Stage 4E `$D018` flip-on-coarse. Do NOT touch the reason-1
(`COARSE_DEFER_LIVE`) gate. Do NOT implement 4E. No commit/push/tag.

## Session start state

- Local checkout was 1 commit BEHIND `origin/experimental-border-hud`. The Stage
  4A–4C baseline (`f07b81f` "VIC Bank memory reclaim for screen 2 stage 1
  complete": +`reports/stage4-second-screen-scroller-architecture.md`, +208 lines
  in `src/main.asm`, all behind `#if OPT_SECOND_SCREEN`) was only on origin.
  The task's "modified src/main.asm / all Stage 4 work behind #if OPT_SECOND_SCREEN"
  wording assumed that work was present as uncommitted changes; it was actually
  committed & pushed. **User explicitly authorised a fast-forward** (`git merge
  --ff-only origin/experimental-border-hud`) to `f07b81f`, overriding the task's
  "no pull" limit for that one lossless step (f07b81f is a direct child of the
  prior HEAD `223a820`, clean tree).
- After FF: branch `experimental-border-hud`, HEAD `f07b81f…`, `git status` clean,
  `git diff --stat` empty.
- Stage 4 toggles (`src/main.asm:148-155`): `//#define OPT_SECOND_SCREEN`
  (default OFF) which gates `OPT_SS_RELOCATE` / `OPT_SS_PAGE_B` /
  `OPT_SS_FLIP_PROOF` (each implies the previous). Also on by default:
  `OPT_BG_ROW_PREDECODE`, `OPT_BG_COARSE_EXTENDED_DEADLINE`, `SCROLL_HITCH_DIAG`.
- Build hashes to reproduce (to be re-measured this task):
  - Stage 4 OFF == Stage 3 baseline: `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991`
  - 4A+4B+4C ON: `326f1686f3cf3d05…` (per stage4 report §16)

## 4D.0 — data-flow audit (COMPLETE)

### Memory map with `OPT_SECOND_SCREEN` ON (measured)

```
$080e-$1efe  main code            -> next used $1f00  => ~2 BYTES headroom (report §17.5)
$2000-$23fe  engine state block   (protected, not relocated)
$2400-$26ff  sprite bitmaps       (VIC-visible; attack data that was $2700-$290e moved out)
$2700-$27ff  FREE  (256 B, VIC bank 0)      <- freed by 4A, unclaimed
$2800-$2bff  bgScreenB  (page B, sprite-ptr table $2bf8-$2bff)
$2c00-$2eff  FREE  (768 B, VIC bank 0)      <- freed by 4A, unclaimed
$2f00-$2fff  HUD sprite bitmaps
$3000-$37ff  health + clip sprite pools
$3800-$3fff  charset  (shared by BOTH pages; $D018 char nibble never changes on a flip)
$9000-$920e  relocated attack/fragment tables (527 B)
$9280-$984e  relocated background-control code + coarse state (1487 B)
$984f-$98ff  FREE  (~177 B)
$9900-$995d  Stage-4 support (ssStage4Base..ssStage4End: BG_ACTIVE_PAGE, SS_*, ssInitPageB,
             ssMirrorSpritePtrs, ssFlipPage)
$995e-$9fff  FREE  (~1698 B)   <- 4D routines + state land here (CPU-only, outside VIC bank 0)
```

Page constants (`src/main.asm` ~351-395):
`BG_SCREEN_A=$0400  BG_SCREEN_A_D018=$1E  BG_SPRITE_PTRS_A=$07F8`
`BG_SCREEN_B=$2800  BG_SCREEN_B_D018=$AE  BG_SPRITE_PTRS_B=$2BF8`
`BG_ACTIVE_PAGE` byte (0=A displayed, 1=B displayed).

### EXACT current single-screen coarse transformation (derived from code, not prose)

Matrix = 25 rows × 40 cols. `SCROLL_ROW`(16-bit) = logical stage row shown at
**matrix row 1**. Row 0 = incoming overflow (world `SCROLL_ROW-1`); rows 1..23 =
body; row 24 = outgoing overflow (world `SCROLL_ROW+23`). Scroll direction:
new scenery enters at the TOP; `SCROLL_ROW` DECREMENTS by 1 per coarse step
(wrap 0 -> `STAGE_LOGICAL_ROWS-1`).

`updateBackgroundScroll` (frame loop): `inc SCROLL_FRAME_COUNT`; every
`SCROLL_FRAME_DIVIDER` (=2) frames, `SCROLL_FINE` 0->7; at 7 sets
`BG_COARSE_PENDING=1`.

`prepareBackgroundCoarse` (after BUILD, before frame-start wait):
1. If `BG_COARSE_PENDING==0` -> rts. Else clear it.
2. **Gate (DO NOT TOUCH)** — 3 checks, each records a reason then `!defer`:
   - reason 1: `RASTER_BATCH_OFFSET != RASTER_BATCH_END` (a pending LIVE reuse
     batch) -> `COARSE_DEFER_LIVE++`, `COARSE_LAST_REASON=1`.
   - reason 2: `$D011` bit7 set (beam past line 0 / wrapped) -> `COARSE_DEFER_BEAM++`.
   - reason 3: `bgCoarseReason3Defer` (extended deadline) or `RASTER >=
     BG_COARSE_LATEST_START` -> `COARSE_DEFER_CUTOFF++`.
   `!defer`: `BG_COARSE_DEFERRED++`; `SCROLL_FRAME_COUNT = SCROLL_FRAME_DIVIDER-1`
   (retry next frame); rts. Nothing in the matrix or VIC phase changed.
3. Admit path: spin `!waitRead` until `RASTER >= 160`.
4. `saveCrossingRow` — copy matrix row 12 (40 bytes) -> `BG_CROSSING_ROW`.
5. `shiftBackgroundUpper` — `for row=12..1: SCREEN[row] = SCREEN[row-1]` (hi->lo,
   no overwrite). Result: matrix rows 1..12 = old rows 0..11. 3840 cy + rts.
6. `SCROLL_ROW -= 1` (16-bit; if it was 0: set to `STAGE_LOGICAL_ROWS` then -1 =
   SLR-1, and set `TURRET_STREAM_REWIND=1` + `WAVE_TRIGGER_REWIND=1`).
7. `BG_DEST_ROW=0`; `renderStageRowToScreen` -> decode world
   `(SCROLL_ROW_new - 1) mod SLR` == `(SCROLL_ROW_old - 2) mod SLR` into matrix
   row 0, then `installTurretRow` overlays live turret body glyphs for that row.
8. `SCROLL_FINE=0`; `BG_COARSE_FINISH=1`; `COARSE_ADMIT++`.

`finishBackgroundCoarse` (next frame top, beam in border, after `armFirstBatch`):
1. If `BG_COARSE_FINISH==0` -> rts. Else clear it.
2. `shiftBackgroundLower` — `for row=24..14: SCREEN[row] = SCREEN[row-1]`. Result:
   matrix rows 14..24 = old rows 13..23. 3520 cy + rts.
3. `restoreCrossingRow` — copy `BG_CROSSING_ROW` (40 bytes) -> matrix row 13.

**NET transform (both frames combined):**
`newRow[r] = oldRow[r-1]` for every r in 1..24, and
`newRow[0] = decodeTerrain((SCROLL_ROW_old - 2) mod SLR) + live turret overlay`.
The two-frame split + `BG_CROSSING_ROW` for row 12->13 is PURELY a beam-timing
device for the in-place single-screen case (row 12 is the last VIC-cached row
when the upper copy runs at raster >=160). In the INACTIVE page there is NO beam
constraint: the whole thing is just `INACTIVE[r] = ACTIVE[r-1]` for r=1..24 plus
one decoded+overlaid row 0. Row-mapping direction CONFIRMED from real code, not
assumed.

### Stage 2 predecode (the piece 4D dovetails with)

- `predecodeNextStageRow` (frame loop, after BUILD/suppression, BEFORE
  `prepareBackgroundCoarse`): `target(16) = (SCROLL_ROW - 2) mod SLR`. If
  `BG_PREDECODE_VALID` and `BG_PREDECODE_ROW_LO/HI == target` -> no-op (this is
  the fine-7 held-frame no-op). Else `decodeStageCharacterRow` (TERRAIN ONLY) ->
  copy 40 bytes to `BG_PREDECODED_ROW`, tag `BG_PREDECODE_ROW_LO/HI = target`,
  `BG_PREDECODE_VALID=1`, `BG_PREDECODE_PREPARED++`.
- `bgConsumePredecodedRow` (inside `renderStageRowToScreen`, only for
  `BG_DEST_ROW==0`): if `BG_PREDECODE_VALID` and not `TURRET_STREAM_REWIND` and
  tag matches `BG_LOGICAL_ROW` -> copy staged row to screen row 0, clear VALID,
  C=1 (caller skips decode). Else C=0 (in-window decode fallback);
  `TAGMISS`/`INVAL`/`MISS` counters.
- `bgPredecodeReset` (initBackground, before SCROLL_ROW reseed): VALID=0, zero
  the stats + (Stage 3) deadline-class state.
- Invalidation is the TAG: any discontinuous `SCROLL_ROW` change makes the
  required row != tag -> fallback + restage. Stage wrap additionally forces
  fallback via `TURRET_STREAM_REWIND`.
- **4D reuses this exact pattern**: terrain-only into the inactive page, tagged by
  the `SCROLL_ROW` it was built for, invalidated by tag mismatch / wrap / reinit.

### Turret handling (relevant to 4D.7)

- `installTurretRow` (tail of `renderStageRowToScreen`): for the ONE row just
  decoded, scans `TURRET_POOL` slots; for an ALIVE slot whose
  `TURRET_SLOT_ROW_LO/HI` or `..ROW2_LO/HI` == `BG_LOGICAL_ROW`, writes the
  shared body glyph codes (`TURRET_GLYPH_BASE..+3`, 2 cells) into `(TEXT_DST),y`
  at `TURRET_SLOT_COL`. CHARACTER codes only.
- Dead turrets: `restoreDeadTurretCells` (from `publishTurretGlyphs`, frame-top
  safe window) reverts a just-killed turret's 2×2 cells back to terrain code +
  `TERRAIN_COLOUR_RAM`. So the ACTIVE matrix is kept current wrt turret life.
- Turret COLOUR: `pulseTurretColour` writes only colour-RAM cells at the turret's
  current screen position (recomputed each frame from `SCROLL_ROW` by
  `positionBackgroundTurrets`). Colour RAM is single, not double-buffered.
- Consequence for 4D: an incremental `INACTIVE[r]=ACTIVE[r-1]` verbatim copy
  carries BAKED-IN turret glyphs. A turret that dies AFTER its cells are copied
  into INACTIVE but BEFORE the flip would show a live body on reveal =
  resurrection (report §17.3). 4D must either (a) build terrain-only into INACTIVE
  and overlay turrets at flip time (Stage 4E, against post-flip SCROLL_ROW), or
  (b) run a cheap turret-reconcile pass over INACTIVE at flip time. Chosen
  approach recorded in 4D.7.

### Frame-loop call order (main.asm ~840-909)

```
gameLoop entry:  waitForGameFrame; publishTurretGlyphs; applyFineScroll;
                 renderSprites; armFirstBatch; finishBackgroundCoarse
!frameLoop:      updateTurretStream; updateWaveTriggers; positionBackgroundTurrets;
                 pulseTurretColour; updateTurretPressure; updateEnemyHitEffects;
                 updatePlayerCombatEffects; updateObjects; updateEnemyFire;
                 updateBackgroundTurrets; updatePlayerState;
                 (endGame check)
                 updateSpawner; updateBackgroundScroll;
                 buildSortedObjectList; sortObjectsByY; buildInitialSpriteSnapshot;
                 buildBatchSpriteSchedule; planCoarseBulletSuppression;
   >>>>>>>>>>>>  predecodeNextStageRow          <-- 4D incremental slice goes adjacent here
                 prepareBackgroundCoarse;       <-- gate (untouched) + in-place mutation
                 noteCoarseSuppressionOutcome; refreshScoreIfDirty;
                 waitForGameFrame; publishTurretGlyphs; applyFineScroll;
                 swapRenderPlans; renderSprites; armFirstBatch;
                 finishBackgroundCoarse
                 jmp !frameLoop
```

`ssInitPageB` is called once from `startGame` (line 804) right after
`initBackground`. `ssMirrorSpritePtrs` / `ssFlipPage` are NOT wired into the loop
in the 4A-4C baseline (kept out to preserve the byte-off build + the near-full
`$080e` segment).

### Divider-2 frame budget between coarse steps

`SCROLL_FRAME_DIVIDER=2`, 8 fine phases -> ~16 physical frames per coarse cycle
(one coarse step every 8 fine advances, each advance every 2 frames). A full
inactive rebuild = 24 row-copies (960 B ≈ 5,700 cy for abs LDA/STA) + 1 decoded
row (~1,400 cy) ≈ 7,100 cy — does not fit one frame's slack, must spread. At
~2 rows/frame that's ~12 slice frames of the ~16 available.

## Plan for 4D.1 .. 4D.8

- 4D.1 page-aware addressing: `ssActiveBase`/`ssInactiveBase` (lo/hi) +
  `ssActive/InactiveD018` from `BG_ACTIVE_PAGE` (3-entry table lookups, no branch
  tree). Parameterise `copyIncomingRowToScreen` + new `ssShiftInactiveSlice` by
  destination page. Keep the single-screen ACTIVE path byte-identical with the
  builder disabled. New sub-toggle `OPT_SS_INACTIVE_BUILD` under `OPT_SECOND_SCREEN`.
- 4D.2 target/tag: `SS_BUILD_TARGET_ROW_LO/HI` = the `SCROLL_ROW` value the
  completed inactive page represents = `SCROLL_ROW_current - 1` (post-coarse), i.e.
  the same value `prepareBackgroundCoarse` would install. Its decoded top row is
  `(target - 1) mod SLR` = `(SCROLL_ROW_current - 2) mod SLR` — identical to the
  Stage 2 predecode target, so the two share the decoded row.
- 4D.3 incremental build + matrix-equivalence reference test (legacy transform in
  a scratch buffer vs the incremental builder, all 25×40 bytes, across
  mid-stage / near-wrap / wrap / metatile patterns / turret states / fine phases).
- 4D.4 scheduler + slice-size sweep (1/2/3 rows) with full counter capture.
- 4D.5 prolonged 199/235 hold: build once, complete once, VALID stays, tag
  constant, zero repeated work over hundreds of held frames.
- 4D.6 invalidation (initBackground / restart / wrap / SCROLL_ROW poke / repaint).
- 4D.7 turret stale-state proof + colour-RAM ordering conclusion.
- 4D.8 sprite-pointer Option A (dual write) vs Option B (8-byte late mirror) cost.

## 4D.1 — page-aware addressing (DONE, both baselines bit-exact)

New sub-toggle `#define OPT_SS_INACTIVE_BUILD` under `OPT_SECOND_SCREEN` (guarded:
needs `SCROLL_HITCH_DIAG` + `OPT_BG_ROW_PREDECODE`). All 4D code/state lives in the
`$9900` Stage-4 block, behind that toggle.

Page addressing = hi-byte deltas from page A, indexed by `BG_ACTIVE_PAGE`
(page B rows = page A rows + $2400, so only the address hi byte changes):
`ssActiveHiDelta[2] = {$00,$24}`, `ssInactiveHiDelta[2] = {$24,$00}`,
`ssActiveD018[2]`, `ssInactiveD018[2]`. `ssCopyOneInactiveRow` /
`ssInstallInactiveRow0` build `TEXT_SRC`/`TEXT_DST` from `starRowLo/Hi[r]` + the
delta — one table lookup, no branch tree, no hard-coded `$0400`/`$2800` maths.

Two hooks, both in roomy relocated segments -> **zero bytes added to the ~2-byte
`$080e` gameLoop segment**:
- `predecodeNextStageRow` `!done:` -> `jmp ssInactiveBuildTick` (tail-call, ends
  in rts). Shares `BG_PREDECODED_ROW` + the `(SCROLL_ROW-2)` target with predecode.
- `bgPredecodeReset` -> `jmp ssInactiveBuildReset` (tail-call).

### Build hashes (3 modes)

| mode | toggles | sha256(prg) | vs baseline |
|---|---|---|---|
| 1 | `OPT_SECOND_SCREEN` OFF (default) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` | **== Stage 3 baseline (bit-identical)** |
| 2 | `OPT_SECOND_SCREEN` ON, `OPT_SS_INACTIVE_BUILD` OFF | `326f1686f3cf3d0526579de167dcb6a6806da48c035fd4a9ad93b90852ff8ab9` | **== 4A+4B+4C baseline (bit-identical)** |
| 3 | `OPT_SECOND_SCREEN` ON, `OPT_SS_INACTIVE_BUILD` ON | `b840e5b696ebce3c42b5f6992b1d231a8551bf3d3712ce4c6cae58f07f3951f1` | new; guards pass, `$9900` block $9900-$99cx |

Modes 1 & 2 are unchanged binaries, so no timing regression is possible with the
builder disabled — 4D.1 acceptance met without a separate run.

## 4D.2 — target / tag semantics (DONE, implemented)

`SS_BUILD_TARGET_ROW(16)` = **the post-coarse `SCROLL_ROW`** the finished INACTIVE
page represents = `(SCROLL_ROW_current - 1) mod SLR` (exactly the value
`prepareBackgroundCoarse` installs; SCROLL_ROW==0 folds to SLR-1). The INACTIVE
page's decoded top row is `(SS_BUILD_TARGET - 1) mod SLR` = `(SCROLL_ROW - 2) mod
SLR` — **identical** to the Stage-2 predecode target, so `BG_PREDECODED_ROW` is
shared and never decoded twice (`ssRow0TargetMatchesPredecode` gates completion on
`BG_PREDECODE_VALID` + tag match).

`ssInactiveBuildRefreshTarget` classifies a changed tag:
- unchanged -> keep build / stay VALID (the fine-7 held-frame no-op);
- `stored - target == 1 (mod SLR)` -> **normal advance** (a coarse step; seamless
  across a stage wrap, since wrap keeps the -1 target delta) -> restart build,
  `SS_BUILD_ADVANCE_COUNT++`;
- any other delta -> **discontinuity** (fixture poke / repaint) -> restart,
  `SS_BUILD_INVALIDATE_COUNT++` + `SS_INVAL_DISCONT++`.
`ssInactiveBuildReset` (initBackground) drops everything + zeroes counters.

Diagnostics (all in `$9900`, no IRQ cost): `SS_BUILD_STATE` (0 idle/1 building/2
valid), `SS_INACTIVE_VALID`, `SS_BUILD_NEXT_ROW`, `SS_BUILD_TARGET_ROW_LO/HI`,
`SS_BUILD_SLICE_ROWS` (pokeable, default 2), `SS_BUILD_START_COUNT`,
`SS_BUILD_COMPLETE_COUNT`, `SS_BUILD_ADVANCE_COUNT`, `SS_BUILD_INVALIDATE_COUNT`,
`SS_INVAL_DISCONT`, `SS_BUILD_SLICE_WORK` (rows copied), `SS_BUILD_REDUNDANT_WORK`
(rows copied while VALID — MUST stay 0), `SS_BUILD_ROW0_WAIT`.

## 4D.3 — incremental build: FIRST MEASUREMENT (partial)

Builder implemented: per frame, `ssInactiveBuildSlice` copies up to
`SS_BUILD_SLICE_ROWS` rows `INACTIVE[r] <- ACTIVE[r-1]` (~674 cy/row via
`(ptr),y`), then installs row 0 from `BG_PREDECODED_ROW` and sets VALID.

**Mode 3 vs Mode 2, natural idle play, 240 physical frames (`check_raster_capture`):**

| metric | Mode 2 (4D off) | Mode 3 (4D on, slice=2) |
|---|---|---|
| `frame_cycle_deltas` | `[19656]` | `[19656]` |
| `service_failure_count` | 0 | 0 |
| `sprite_start_miss_count` | 0 | 0 |
| `catchups` | 0 | 0 |
| **`replay_frames`** | **0** | **14** |

=> Cadence exact and no sprite/service failure, BUT the naive 2-row slice at the
`predecodeNextStageRow` tail (late in the frame, just before
`prepareBackgroundCoarse` + `waitForGameFrame`) adds ~1,350 cy that pushes ~6% of
frames past the frame boundary into the IRQ replay path. This is exactly the
decisive risk called out in stage4 report §17.1.

### 4D.4 direction (next)

The slice needs a **bounded scheduler** rather than "run every frame":
- do NOT slice on the coarse-admit frame or the frame `BG_COARSE_PENDING` is set
  (the heaviest frame — `shiftBackgroundUpper` 3840 cy + decode);
- optionally gate on `RASTER < threshold` at slice entry and skip (bounded: >=16
  frames available, need ~12 at 2 rows/frame, so a few skips are safe and the
  build still completes before the earliest next coarse step);
- and/or move the slice call earlier in the frame (piggyback a different roomy
  tail, e.g. `updateBackgroundScroll`, which runs before the sort/BUILD block
  where there is more slack) — still zero `$080e` bytes.
Then sweep slice size 1/2/3 rows and capture the full counter set.

## 4D.3 — MATRIX EQUIVALENCE: **PROVEN byte-exact** (scratchpad/s4d_equiv.py)

Method (per seeded SCROLL_ROW): force the builder to rebuild, hold coarse off,
run until `SS_INACTIVE_VALID`, snapshot the INACTIVE page; then let the engine
perform ONE real **legacy** coarse admit and snapshot the resulting ACTIVE page;
compare all 25x40 = 1000 character cells.

Seeds: 200, 60, 380 (mid-stage), 2, 1 (near-wrap), 0 (stage wrap -> target
SLR-1 = 419), 419, 300.

| seed SCROLL_ROW | tag (post-coarse) | INACTIVE vs ACTIVE-after-real-legacy-coarse |
|---|---|---|
| 200 | 199 | **0 cell diffs** |
| 60  | 59  | **0 cell diffs** |
| 380 | 379 | **0 cell diffs** |
| 2   | 1   | **0 cell diffs** |
| 1   | 0   | **0 cell diffs** |
| 0   | 419 (wrap) | **0 cell diffs** |
| 419 | 418 | **0 cell diffs** |
| 300 | 299 | **0 cell diffs** |

INACTIVE row 0 == `BG_PREDECODED_ROW` on every seed. Sprite-pointer bytes
(`$xBF8..$xBFF`) are correctly **untouched** by the builder (they are Option A/B
territory, 4D.8) -- the row copies only ever write cols 0..39 of rows 0..24.

(The looser "static" check -- `INACTIVE[r] == ACTIVE[r-1]` snapshotted at the same
instant -- shows diffs, but that is a reference-capture artifact: the game is live
between the builder's slices and the snapshot, so `ACTIVE[r-1]` at snapshot time
is not what the builder copied several frames earlier. The DYNAMIC check runs the
legacy transform on the SAME frozen input the builder used, and that is the
task's specified methodology -- 0 diffs.)

## 4D.4 — slice-size sweep + bounded scheduler (partial)

`ssInactiveBuildTick` (from `predecodeNextStageRow`'s tail) withholds the WHOLE
tick on the two coarse-critical frames per cycle (`BG_COARSE_PENDING` = the
fine-7 admit-candidate frame; `BG_COARSE_FINISH` = the post-admit frame owing
`shiftBackgroundLower`) and once `$D011` bit7 shows the beam wrapped. Slice size
`SS_BUILD_SLICE_ROWS` (default 2) is monitor-pokeable.

Idle play, 400 physical frames, `SS_BUILD_SLICE_ROWS` swept 0/1/2/3:

| metric | Mode 2 (4D off) | Mode 3, slice 0 | 1 | 2 | 3 |
|---|---|---|---|---|---|
| `frame_cycle_deltas` | `[19656]` | `[19656]` | `[19656]` | `[19656]` | `[19656]` |
| `RASTER_CATCHUPS` | 0 | 0 | 0 | 0 | 0 |
| `RASTER_INCOMPLETE_FRAMES` | 0 | 0 | 0 | 0 | 0 |
| `RASTER_BORDER_BAILS` | 0 | 0 | 0 | 0 | 0 |
| **`RASTER_REPLAY_FRAMES`** | **0** | **25** | **25** | **25** | **25** |
| builds start / complete | - | 25 / 25 | 25 / 25 | 25 / 25 | 25 / 25 |
| `SS_BUILD_REDUNDANT_WORK` | - | 0 | 0 | 0 | 0 |
| `SS_BUILD_ROW0_WAIT` | - | 0 | 0 | 0 | 0 |
| `SS_INACTIVE_VALID` (end) | - | 1 | 1 | 1 | 1 |
| `COARSE_ADMIT` | 25 | 25 | 25 | 25 | 25 |

**KEY FINDING.** `RASTER_REPLAY_FRAMES` == `COARSE_ADMIT` count, and is
**identical for every slice size incl. 0** (whole 24-row build in one frame) and
every gating variant tried. So it is NOT the slice cost -- it is the ~10-20 cy of
*unconditional per-frame scheduler overhead* that `predecodeNextStageRow`'s tail
now always pays, landing on the **coarse-admit frame** whose main-thread budget in
the `f07b81f` baseline is near-full (the routine's own comments count individual
bytes). One extra replay per coarse admit; the replay path services it correctly
-- `[19656]` exact, 0 catchup / 0 incomplete / 0 border-bail / 0 service-failure /
0 sprite-start-miss in every run.

Status: this is a **narrow-timing-margin bounded issue** = the task's explicit
AMBER example. Attempts to zero it (withhold whole tick on `BG_COARSE_PENDING` |
`BG_COARSE_FINISH`; cheapest single-flag gate at the predecode tail) did not --
the residual ~8-20 cy still tips the admit frame. Candidate fixes not yet tried:
move the tick call to AFTER `prepareBackgroundCoarse` (so its cost never precedes
`shiftBackgroundUpper`/`bgUpperReady` on the admit frame) e.g. tail-call from
`refreshScoreIfDirty` or `noteCoarseSuppressionOutcome`; or hook a routine that is
already skipped on the admit frame.

## 4D.5 — prolonged 199/235 reason-1 hold: **PROVEN** (scratchpad/s4d_hold.py)

8 enemies Y=199 + player Y=235, 600 held frames after the build had completed:

- `SCROLL_ROW` 395 -> 395, `SCROLL_FINE` pinned 7, `dCOARSE_DEFER_LIVE` +600,
  `dCOARSE_ADMIT` 0 -- **reason-1 gate unchanged** (as required).
- `SS_BUILD_STATE` = 2, `SS_INACTIVE_VALID` = 1 throughout; `SS_BUILD_TARGET_ROW`
  394 -> 394 (constant).
- `SS_BUILD_START_COUNT` 0, `COMPLETE` 0, `SLICE_WORK` 0, `REDUNDANT_WORK` 0,
  `INVALIDATE_COUNT` 0, `ROW0_WAIT` 0, `SKIP_COUNT` 0 over the 600 frames --
  **zero work of any kind**; no rebuild, no re-decode, no drift.
- `RASTER_REPLAY_FRAMES` 0 during the hold (the +1/admit cost needs a coarse
  admit, which a reason-1 hold never reaches).

## 4D.4 (cont.) — hook relocated after prepareBackgroundCoarse

The per-frame tick is now tail-called from `noteCoarseSuppressionOutcome` (both
exits), which runs AFTER `prepareBackgroundCoarse`. Modes 1 & 2 stay
**bit-identical** (`f2abc225…` / `326f1686…`) -- the two `jmp ssInactiveBuildTick`
are fully `#if OPT_SS_INACTIVE_BUILD`-guarded.

Replay result is UNCHANGED: still exactly `COARSE_ADMIT` count (25/400 idle,
19/260 wave, 27/320 wrap). Root cause pinned by tracing `RASTER_PRESENT_READY`:
the `f07b81f` baseline's **coarse-admit frame reaches `waitForGameFrame` with
< ~20 cy of slack before frame top**; the ~20 cy of unconditional 4D
scheduler/guard code on that frame's path tips `RASTER_PRESENT_READY` to 0 at
line 1 -> the replay path services it (correctly: `[19656]`, 0 catchup/incomplete/
bail/service/sprite-miss). Independent of slice size (0/1/2/3 all == admit count)
and of tick placement (before / after `prepareBackgroundCoarse`). The only truly
zero-cost window is between `waitForGameFrame` (READY=1) and `armFirstBatch`
(READY=0), which is the beam-critical `swapRenderPlans`/`renderSprites` span --
not safe for a ~1,350 cy slice.

**This is 4D's one bounded cost, and it is expected to invert under 4E:** 4E
removes `shiftBackgroundUpper` (3840 cy) + the in-window decode (~1400 cy) +
`saveCrossingRow`/`restoreCrossingRow` from the admit frame (replaced by a 4-cy
`$D018` write), freeing far more admit-frame slack than the 4D tick consumes. 4D
measured in isolation pays the builder cost while the legacy admit still does all
its in-window work -- double coarse-frame load.

## 4D.6 — invalidation (scratchpad s4d_inval.py)

| step | result |
|---|---|
| 120 frames natural play | `start==complete==8`, `adv=7`, `inval=0`, `discont=0`, `redund=0`, VALID, tag == SCROLL_ROW-1 |
| discontinuous `SCROLL_ROW := 50` poke | `SS_BUILD_INVALIDATE_COUNT` 0->1, `SS_INVAL_DISCONT` 0->1 (**counted exactly once**), build restarts (`start` 8->10), recovers to VALID with the new tag; `redund=0` |
| +60 frames natural (incl. coarse advances) | `inval` still 1 -- **no spurious invalidation** from ordinary coarse steps / seamless wraps; `start==complete`, `redund=0` |
| stage wrap (seed 0 -> tag 419, in the equivalence run) | classified as a normal -1 advance, DYNAMIC 0 cell diffs -- **seamless, not an invalidation** |
| game restart (`initBackground` -> `bgPredecodeReset` -> `ssInactiveBuildReset`) | wired + code-verified; the automated probe did not cleanly re-enter PLAYING (needs a fire press) so not measured this pass |

## Regression pass (MODE3 vs MODE2, check_raster_capture)

| fixture | frames | `[19656]` | service fail | sprite-start miss | replay (M3 / M2) | catchups |
|---|---|---|---|---|---|---|
| idle | 400 | exact | 0 | 0 / 0 | **25** / 0 | 0 / 0 |
| authored wave (seed 382) | 260 | exact | 0 | 0 / 0 | **19** / 0 | 1 / 0 |
| stage wrap (seed 12) | 320 | exact | 0 | 0 / 0 | **27** / 0 | 1 / 0 |
| dense 16-obj synthetic | 200 | exact | 0 | 2 / **3** (baseline; 4D not the cause) | 100 / 99 | 1393 / 1393 |

Only new regression: **+1 `RASTER_REPLAY_FRAME` per coarse admit** (0 during a
reason-1 hold). Cadence, service, sprite-start (real gameplay), catchups,
incomplete frames, border bails: all unchanged. Dense sprite-start misses are a
pre-existing `--dense` baseline property (MODE2 has 3, MODE3 has 2).

## 4D.7 / 4D.8 (design + measurement summary)

- **4D.7 turret**: the DYNAMIC equivalence check compared ALL 1000 cells incl.
  turret-overlay cells and got 0 diffs -- the builder carries ACTIVE's baked
  turret glyphs verbatim and the legacy admit shifts the same baked glyphs, so
  the built page equals the legacy page. The stale-turret case (a turret dies
  between build and flip) is a **flip-time (4E) reconcile**: at the flip, for each
  `TURRET_POOL` slot, write its 2x2 body glyphs (alive) or `turretGroundCodes`
  terrain (dead/absent) into the INACTIVE page against the post-flip `SCROLL_ROW`
  -- few slots, ~a few dozen cells, cheap; the prepared TERRAIN page is fully
  compatible with that (row 0 is already terrain-only from `BG_PREDECODED_ROW`).
  **Colour RAM**: single, cannot be double-buffered; terrain colour is one global
  value (scrolling it is a no-op); only turret body colour cells are dynamic and
  are already recomputed each frame from `SCROLL_ROW` by `positionBackgroundTurrets`
  / `pulseTurretColour`. Required 4E ordering: run the turret colour update
  against the POST-flip `SCROLL_ROW` on the flip frame (same discipline
  `installTurretRow` already uses for char cells). No colour buffer needed.
- **4D.8 sprite pointers**: the builder does NOT touch `$xBF8..$xBFF` (verified:
  INACTIVE ptr table stays stale). Option A (dual write at all 5 sites, +~8-10 cy
  per LIVE batch in the raster IRQ) vs Option B (`ssMirrorSpritePtrs`, 8-byte
  late copy, ~50 cy, no IRQ change -- already implemented). Given how
  admit-frame/IRQ-margin-sensitive this HEAD is (4D.4), **Option B is
  recommended**: it adds nothing to the raster hot path; its "displayed page one
  frame stale" caveat is void if 4E schedules the flip so the newly-active page
  was the inactive page (and was mirrored) the previous frame.

## Progress — 4D COMPLETE, verdict AMBER

- [DONE] 4D.0 audit.
- [DONE] 4D.1 page-aware addressing -- modes 1 & 2 **bit-identical** to their
  baselines (`f2abc225…` / `326f1686…`); mode 3 `b73c765e…`, guards pass.
- [DONE] 4D.2 target/tag semantics (post-coarse `SCROLL_ROW`; shares the Stage-2
  predecode target/buffer).
- [DONE] 4D.3 matrix equivalence -- **byte-exact vs a real legacy coarse admit,
  8 seeds incl. stage wrap, 0 of 1000 cell diffs each**.
- [DONE] 4D.4 slice sweep + bounded scheduler -- builds complete every cycle at
  every slice size; **residual +1 `RASTER_REPLAY_FRAME` per coarse admit**
  (slice-size- and placement-independent; root-caused to ~20 cy on a
  <20-cy-slack admit frame; correctly serviced; expected to invert under 4E).
  Default `SS_BUILD_SLICE_ROWS = 2`.
- [DONE] 4D.5 prolonged 199/235 hold (600 frames) -- VALID holds, zero redundant
  work, tag constant, reason-1 gate defers every frame, 0 replay during the hold.
- [DONE] 4D.6 invalidation -- discontinuous `SCROLL_ROW` poke counted once and
  recovered; ordinary coarse/wrap = no spurious invalidation; reset route wired
  via `bgPredecodeReset` (interactive restart not auto-measured).
- [DONE] 4D.7 turret -- byte-equiv covers overlay cells (0 diffs); flip-time
  reconcile designed for 4E; colour-RAM stays single with a post-flip ordering
  rule.
- [DONE] 4D.8 sprite pointers -- builder leaves them untouched; **Option B
  (`ssMirrorSpritePtrs`, no IRQ cost) recommended**.
- [DONE] regression matrix (idle/wave/wrap/dense) -- `[19656]` exact, 0 service,
  0 sprite-start miss in real gameplay, +1 replay/admit the only delta.
- [DONE] report `/reports/stage4d-incremental-inactive-screen-build.md`.

Build left at Mode 1 default (`f2abc225…`). `git status`: `M src/main.asm`
(+worklog +report). No commit / push / tag / branch change beyond the one
user-authorised fast-forward to `f07b81f` at session start.

### Verdict: AMBER
Builder correctness **proven** byte-exact incl. wrap; the completed page holds
indefinitely through a reason-1 hold with zero redundant work; cadence `[19656]`
exact; no capacity/terrain/collision impact; reason-1 gate untouched; soft-edge
untouched. One bounded open item: +1 replay frame per coarse admit (narrow
admit-frame margin on this HEAD; not corruption; correctly serviced; expected to
turn positive once 4E removes ~5500 cy of in-window work from the admit frame).
