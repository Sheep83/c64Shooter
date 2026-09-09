# Stage 4E — Publish coarse scroll by $D018 page flip — worklog

Continues directly from the Stage 4D dirty working tree (`M src/main.asm`).
Branch `experimental-border-hud`, HEAD `f07b81f`. No commit/push/tag.

## Session start state
```
git branch: experimental-border-hud
git HEAD:   f07b81fbcdb3240fde92e49c8f3694392e0e59df
git status: M src/main.asm
            ?? docs/stage4d-incremental-inactive-screen-worklog.md
            ?? reports/stage4d-incremental-inactive-screen-build.md
git diff --stat: src/main.asm | 356 (+353 -3)
```
4D hashes (must be preserved by the 4E toggle when 4E is OFF):
- Mode 1 (`OPT_SECOND_SCREEN` off): `f2abc225159e81bf…` (= Stage 3 baseline)
- Mode 2 (SS on, builder off):      `326f1686f3cf3d05…` (= 4A+4B+4C)
- Mode 3 (4D builder on, 4E off):   `b73c765e9bcc54ec…`

## 4E.0 — coarse publication path audit (from the real code)

### gameLoop `!frameLoop` order (main.asm ~848-909)
```
updateTurretStream; updateWaveTriggers; positionBackgroundTurrets;    <- turret SCREEN COORDS from OLD SCROLL_ROW
pulseTurretColour;                                                    <- turret COLOUR RAM from OLD SCROLL_ROW ($D800, page-independent)
updateTurretPressure; updateEnemyHitEffects; updatePlayerCombatEffects;
updateObjects; updateEnemyFire; updateBackgroundTurrets; updatePlayerState;
(endGame check)
updateSpawner;
updateBackgroundScroll;          <- sets BG_COARSE_PENDING when fine==7 on the divider tick
buildSortedObjectList; sortObjectsByY; buildInitialSpriteSnapshot;
buildBatchSpriteSchedule; planCoarseBulletSuppression;
predecodeNextStageRow;           <- Stage-2 predecode (stages BG_PREDECODED_ROW)
prepareBackgroundCoarse;         <- (1) gate, (2) on admit: waitRead>=160, saveCrossingRow, shiftBackgroundUpper
                                    (3840cy), SCROLL_ROW -= 1 (wrap 0->SLR-1 sets TURRET/WAVE_REWIND),
                                    renderStageRowToScreen(row0), SCROLL_FINE=0, BG_COARSE_FINISH=1, COARSE_ADMIT++
noteCoarseSuppressionOutcome;    <- (4D tick tail-called here: ssInactiveBuildTick)
refreshScoreIfDirty;
waitForGameFrame;                <- blocks to next physical-frame top (beam ~0); sets RASTER_PRESENT_READY=1
publishTurretGlyphs;             <- frame-top, beam in border: republish body glyph charset + restoreDeadTurretCells
                                    (dead-turret CHAR revert, page-A hardcoded, one-shot TURRET_DEAD_RESTORED latch)
applyFineScroll;                 <- SCROLL_FINE -> RASTER_DISPLAY_FINE  (in $9280 segment)
swapRenderPlans; renderSprites;  <- initial hw sprite pointers -> $07F8 (page A), ~raster 5-20
armFirstBatch;                   <- publishRasterPlan: RASTER_PRESENT_READY=0, arms multiplexIRQ (mid-frame batches)
finishBackgroundCoarse;          <- if BG_COARSE_FINISH: shiftBackgroundLower (3520cy) + restoreCrossingRow  (in $9280)
jmp !frameLoop
```

### Answers to the 8 required audit points
1. **Caller** of `prepareBackgroundCoarse`: gameLoop `!frameLoop`, once/frame, after
   `predecodeNextStageRow`, before `noteCoarseSuppressionOutcome`.
2. **SCROLL_ROW decremented**: inside `prepareBackgroundCoarse` admit path
   (`bgUpperCopied:` .. `!stageNoWrap:`), 16-bit, `0 -> STAGE_LOGICAL_ROWS` then `-1`
   (= SLR-1) with `TURRET_STREAM_REWIND=1`+`WAVE_TRIGGER_REWIND=1` on the wrap.
3. **SCROLL_FINE**: advanced/reset by `updateBackgroundScroll` (inc to 7 on the
   divider tick); on a coarse admit `prepareBackgroundCoarse` sets it to 0 at
   `bgUpperReady:`. Published to `RASTER_DISPLAY_FINE` by `applyFineScroll` at the
   next frame top.
4. **BG_COARSE_PENDING**: set by `updateBackgroundScroll` (`!coarse:`), cleared at
   the top of `prepareBackgroundCoarse` (admit OR defer). On a defer,
   `SCROLL_FRAME_COUNT := DIVIDER-1` so the next frame re-requests it.
   **BG_COARSE_FINISH**: set at `bgUpperReady:` on admit, cleared by
   `finishBackgroundCoarse` the following frame top (before its lower shift).
5. **finishBackgroundCoarse runs**: gameLoop line ~908 (present chain), AFTER
   `waitForGameFrame`/`renderSprites`/`armFirstBatch` -> beam already past the top
   border (~raster 20-25, measure), still well before the first badline (raster
   48 at YSCROLL=0). Also once at gameLoop entry (~846).
6. **Turret pos/colour vs the coarse state change**: `positionBackgroundTurrets` +
   `pulseTurretColour` run at the TOP of `!frameLoop` -- i.e. on the frame AFTER
   the admit they run with the ALREADY-decremented SCROLL_ROW (post-coarse). So
   colour RAM is reconciled to the post-coarse positions by the existing
   `pulseTurretColour` before any 4E flip in that same frame. `pulseTurretColour`
   tracks `TURRET_CRAM_ROW,x` and reverts a vacated / dead turret's colour cells
   to `TERRAIN_COLOUR_RAM` -- **page-independent ($D800), needs no 4E work**.
   `restoreDeadTurretCells` (CHAR revert, from `publishTurretGlyphs`) is page-A
   hardcoded and one-shot -> **the dead-turret CHAR revert must be redone on the
   new page by 4E**.
7. **Sprite pointers last coherent**: initial table written by `renderSprites`
   (line ~906) to `$07F8`; further mid-frame writes by `applyLiveRasterBatch` in
   the raster IRQ (only when `max_batches>=1`, i.e. the 9+ / reuse case -- normal
   <=8-sprite gameplay has `max_batches=0`, so the table is complete right after
   `renderSprites`). Page B's table is `$2BF8`.
8. **Intended $D018 write point**: frame top, before the first badline. 4C proved
   a frame-boundary flip raster-safe. Candidate: `finishBackgroundCoarse` (present
   chain, after renderSprites/armFirstBatch, ~raster 20-25) -- reuses the ~3520 cy
   the legacy lower shift would have spent, so the flip path is a big net saving
   on that frame. Confirm the raster with a probe before committing.

### 4E design (to implement)
- Toggle `OPT_SS_FLIP_COARSE` under `OPT_SS_INACTIVE_BUILD`.
- `prepareBackgroundCoarse`, after the (unchanged) gate passes: if flip prereqs
  hold (`SS_INACTIVE_VALID`, `SS_BUILD_TARGET_ROW == (SCROLL_ROW-1) mod SLR`,
  `SS_PTR_MIRROR_READY`, no discontinuity) -> **flip admit**: decrement SCROLL_ROW
  (reuse the existing wrap block), `SCROLL_FINE=0`, `SS_FLIP_PENDING=1`,
  `COARSE_ADMIT++` / `SS_FLIP_ADMIT++` / `SS_FLIP_PATH_COUNT++`; SKIP
  saveCrossingRow / shiftBackgroundUpper / renderStageRowToScreen; do NOT set
  `BG_COARSE_FINISH`. Prereq fail -> legacy fallback (fall through to `!waitRead`)
  + `SS_FLIP_FALLBACK++` + reason counter + `SS_LEGACY_COARSE_PATH_COUNT++`.
- `finishBackgroundCoarse`: if `SS_FLIP_PENDING` -> `jmp ssPublishCoarseFlip`.
- `ssPublishCoarseFlip` ($9900+): mirror `$07F8->inactive+$3F8`; reconcile turret
  CHAR cells on the inactive (about-to-be-active) page vs post-coarse SCROLL_ROW
  (alive->body glyphs, dead/absent->cached turretGroundCodes); `$D018 :=
  ssInactiveD018[BG_ACTIVE_PAGE]`; `BG_ACTIVE_PAGE ^= 1`; `SS_PAGE_SWAP_COUNT++`;
  `SS_FLIP_PENDING=0`.
- Per-frame `ssMirrorSpritePtrs` (active->inactive) on the non-flip
  `finishBackgroundCoarse` path too, setting `SS_PTR_MIRROR_READY`.
- The 4D builder is already page-role-driven (`ssActiveHiDelta`/`ssInactiveHiDelta`
  keyed on `BG_ACTIVE_PAGE`) -> after the swap it naturally builds into the new
  inactive page for the new `(SCROLL_ROW-1)` target.

### Known risk carried from 4D
`RASTER_REPLAY_FRAMES` +1 per coarse admit (=~20cy of 4D tick on a <20cy-slack
admit frame). 4E removes ~5,500 cy of legacy admit-frame work -> the hard 4E
acceptance criterion is that this replay regression goes to **0**. If it does not,
STOP and investigate.

## Implemented (4E.1..4E.9)

- **4E.1 toggle** `OPT_SS_FLIP_COARSE` under `OPT_SS_INACTIVE_BUILD`. Modes:
  M1 `f2abc225…` (bit-identical Stage 3), M2 `326f1686…` (bit-identical 4A+4B+4C),
  M3 (4D-only) hash **changed** `b73c765e…` -> `95f03ff2…` because the raster-budget
  guard added to `ssInactiveBuildSlice` (see 4E.replay) is `#if OPT_SS_INACTIVE_BUILD`
  and so also applies to 4D -- a strict scheduler improvement (it also removes 4D's
  own replay AMBER; 4D builder still byte-exact, re-verified). M4 (4D+4E) `98eb5bbb…`.
- **4E.2 prereqs** `ssFlipPrereqOK`: `SS_BUILD_STATE==2` && `SS_INACTIVE_VALID` &&
  `SS_PTR_MIRROR_READY` && `SS_BUILD_TARGET_ROW == (SCROLL_ROW-1) mod SLR`. Fail ->
  bumps `SS_FLIP_INVALID_PAGE` / `SS_FLIP_TAG_MISMATCH` / `SS_FLIP_POINTER_NOT_READY`
  and the caller takes the legacy in-window path (`SS_FLIP_FALLBACK++`,
  `SS_LEGACY_COARSE_PATH_COUNT++`).
- **4E.3 legacy skip** `prepareBackgroundCoarse`: on a flip admit the gate result
  routes to a new `!admitDecided` block that decrements `SCROLL_ROW` (same code as
  legacy, incl. wrap + `TURRET/WAVE_REWIND`), sets `SCROLL_FINE=0`, `SS_FLIP_PENDING`,
  `COARSE_ADMIT++`, and RETURNS -- `!waitRead` / `saveCrossingRow` /
  `shiftBackgroundUpper` / `renderStageRowToScreen` are NOT executed. Measured:
  `SS_LEGACY_COARSE_PATH_COUNT == 0`, `SS_FLIP_ADMIT == COARSE_ADMIT` in a 400-frame
  idle run -> 100% flip publication.
- **4E.4 / 4E.8 flip frame** `finishBackgroundCoarse` -> `ssPublishCoarseFlip` when
  `SS_FLIP_PENDING`: (1) `ssFlipMirrorPtrs` ($07F8 -> inactive page +$3F8), (2)
  `ssReconcileTurretsOnNewPage`, (3) `$D018 := ssInactiveD018[BG_ACTIVE_PAGE]`,
  (4) `BG_ACTIVE_PAGE ^= 1`. Measured `$D018` write raster = **26** (before the
  first badline at 48 -> no matrix split; 4C-safe window). `finishBackgroundCoarse`
  runs in the present chain AFTER renderSprites/armFirstBatch, so the flip cost
  cannot precede or delay the beam-critical sprite writes.
- **4E.5 turret reconcile** `ssReconcileTurretsOnNewPage` / `ssReconcileTurretSlot`
  / `ssReconcileTurretRow`: per pool slot, CHAR cells of the 2x2 body on the
  about-to-be-active page vs post-coarse SCROLL_ROW -- alive -> body glyphs 226..229,
  dead/absent -> cached `turretGroundCodes`. Colour RAM untouched (page-independent;
  `pulseTurretColour` already reconciled it this frame). Diag
  `SS_TURRET_RECONCILE_COUNT` / `_MAX`.
- **4E.6 colour** conclusion from 4E.0 holds: `pulseTurretColour` (top of !frameLoop)
  runs with the post-coarse SCROLL_ROW before the flip, reverts vacated/dead turret
  colour cells to `TERRAIN_COLOUR_RAM` -- $D800 is page-independent, no 4E colour
  work, no second buffer.
- **4E.7 pointers** Option B: `ssFlipMirrorPtrs` at the flip + an every-frame mirror
  from `finishBackgroundCoarse`'s `!done`. No IRQ dual-write. `SS_PTR_MIRROR_READY`
  gates the flip.
- **4E.9 role swap** `BG_ACTIVE_PAGE ^= 1` once per flip; the 4D builder is already
  page-role-driven so it retargets the (new) inactive page for the next
  `(SCROLL_ROW-1)`. Measured `SS_PAGE_SWAP_COUNT == SS_FLIP_ADMIT == COARSE_ADMIT`
  (25 over 400 idle frames); `SS_BUILD_START/COMPLETE/ADVANCE == 25`,
  `SS_BUILD_REDUNDANT_WORK == 0`.

## THE decisive replay result

MODE4 idle play, 400 frames: **`RASTER_REPLAY_FRAMES == 0`** (was +1 per coarse
admit in 4D). `RASTER_CATCHUPS 0`, `RASTER_INCOMPLETE_FRAMES 0`,
`RASTER_BORDER_BAILS 0`, `[19656]`.

Root cause of the 4D replay (traced via the interrupted-PC on the stack at the
`inc RASTER_REPLAY_FRAMES` site): main was inside `ssCopyOneInactiveRow` (a 4D
build slice) when the line-1 IRQ fired, on ONE frame per coarse cycle where the
build phase ran late. NOT the legacy shift (which `SS_LEGACY_COARSE_PATH_COUNT`
confirms never runs). Fix: a raster-budget guard in `ssInactiveBuildSlice` --
stop the slice before a row copy if the beam is already past raster
`SS_SLICE_RASTER_CUTOFF` (220) or wrapped; the unbuilt rows resume next frame
(`SS_BUILD_SLICE_DEFER_COUNT` diag). The build still completes every cycle with
margin.

## Correctness so far

- 4D builder still byte-exact with the raster cap: `s4d_equiv.py` DYNAMIC on M3
  (`95f03ff2…`) -- INACTIVE == real legacy coarse, **0 / 1000 cell diffs**, all 8
  seeds incl. stage wrap (SCROLL_ROW 0 -> 419).
- 4E flip verified live: `flipped=True` every admit, `$D018` toggles `$1E`/`$AE`,
  `BG_ACTIVE_PAGE` toggles, `SCROLL_ROW` decrements correctly incl. the wrap
  `0 -> 419`, `SS_INACTIVE_VALID==1` before each flip.

## Verification results

- **199/235 control (M4, 600 held frames)**: `SCROLL_ROW` 395->395, `SCROLL_FINE`
  pinned 7, `dCOARSE_DEFER_LIVE +600`, `dCOARSE_ADMIT 0` -> **no flip while blocked,
  reason-1 gate unchanged**. `SS_INACTIVE_VALID 1`, all SS_BUILD counters 0 over
  the hold, `replay 0 / catchup 0 / incomplete 0`.
- **Turret reconcile (M4, seed 355, live authored turret slot 7 @ worldRow 345)**:
  - CASE A alive across a flip: flipped page matrixRow 3 cells = `[226,227,228,229]`
    = body glyphs -> **OK**.
  - CASE B killed between the incremental build and the flip: flipped page
    matrixRow 4 cells = `[112,112,112,112]` = terrain, colour RAM `$09`
    (`TERRAIN_COLOUR_RAM`) -> **no resurrection, OK**.
- **Regression (check_raster_capture)**:
  | fixture | M4 replay | M2 (no 4D/4E) replay | Δcyc | svc | sprite-miss | catchup |
  | idle 300/500 | **0 / 0** | 0 | [19656] | 0 | 0 | 0 |
  | authored wave (seed 382) 300 | 1 | 4 | [19656] | 0 | 0 | 1 |
  | stage wrap (seed 12) 340 | 4 | 8 | [19656] | 0 | 0 | 1 |
  | dense 16-obj 200 | 99 | 99 (baseline) | [19656] | 0 | 3 (baseline) | 1393 |
  M4 replay <= M2 on every fixture; idle (coarse admits isolated) = 0. The Stage-4D
  +1-per-admit regression is gone in BOTH M3 (raster-cap) and M4.
- **Scroll edges (M4, 500f, `check_scroll_edges_rsel1 --aperture 55 246`)**: exit 0,
  body/lastrow temporal diffs 0 -- terrain aperture unchanged.
- **M3 re-validation (raster-cap, 400f)**: `replay 0` -- the guard also removes 4D's
  own replay AMBER. 4D builder still byte-exact (s4d_equiv DYNAMIC 0/1000, 8 seeds
  incl. wrap).

## Final hashes
| mode | sha256(prg) |
| M1 `OPT_SECOND_SCREEN` off | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` (= Stage 3) |
| M2 4A+4B+4C | `326f1686f3cf3d0526579de167dcb6a6806da48c035fd4a9ad93b90852ff8ab9` (= 4A-4C) |
| M3 4D (raster-cap) | `95f03ff2110721a85fb9aa5b8abbcf49d2c0944814868d225fb2f504099cc6fb` (was `b73c765e…`) |
| M4 4D+4E flip | `98eb5bbbc2fb385efeace6060e876c17c5d87ce9970303e7f2187b9bdc718cd2` |

`$9900` block `$9900-$9d7d`; `$9280` block `$9280-$98b4`; guards pass. `build/` left at M1.

## Verdict: GREEN
16/16 GREEN criteria met. The +1 replay/coarse-admit is gone; flip publication is
100% (0 legacy fallback); terrain byte-exact (via the unchanged, re-verified 4D
builder); turret reconcile proven both directions incl. kill-before-flip; reason-1
gate and soft-edge untouched; `[19656]` everywhere; earlier toggle modes reversible
(M1/M2 bit-identical, M3 strictly improved).

## Progress
- [done] 4E.0-4E.9, replay elimination, 199/235, turret reconcile, regression,
  scroll edges, M3 re-validation, hashes.
- [done] report /reports/stage4e-d018-coarse-publication.md
