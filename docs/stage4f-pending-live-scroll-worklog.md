# Stage 4F — Remove the structural pending-LIVE scroll block — worklog

Branch `experimental-border-hud`. HEAD `931dca1` (tag `stable-double-buffered-scroller`
= Stage 4D+4E). Clean tree at start. No commit/push/tag.

## Toggle
`OPT_SS_ALLOW_PENDING_LIVE_FLIP` under `OPT_SS_FLIP_COARSE`. Relaxes ONLY reason 1
(`COARSE_DEFER_LIVE`) for the prepared-page flip path; reasons 2/3 kept; legacy
fallback keeps reason 1.

## Modes / hashes
- A (`OPT_SECOND_SCREEN` off): `f2abc225159e81bf…` (= Stage 3 baseline, bit-identical)
- B (4D+4E, 4F off): `98eb5bbbc2fb385e…` (= tag `stable-double-buffered-scroller` M4, bit-identical)
- C (4D+4E+4F): `d3ba25a996c348df…`
`$9900` block `$9900-$9de1`; `$9280` block `$9280-$98fa`; guards pass. build/ left at A.

## Design
- `prepareBackgroundCoarse` reason-1 branch: still `inc COARSE_DEFER_LIVE`. If
  `OPT_SS_ALLOW_PENDING_LIVE_FLIP` and (`SS_BUILD_STATE==2` && `SS_INACTIVE_VALID`
  && `SS_PTR_MIRROR_READY`): `inc SS_PENDING_LIVE_FLIP_ATTEMPT`, set
  `SS_PLF_BYPASSED`, `jmp !gateBeam` (skip reason 1; 2/3 still run). Else
  `inc SS_WOULD_DEFER_LIVE`, defer as before.
- `!legacyCoarsePath`: if `SS_PLF_BYPASSED` (bypassed then flip-tag failed) ->
  `SS_PLF_TAG_DEFER++`, defer (never run the legacy in-window mutation with a
  pending batch).
- `ssFlipNoteAdmit`: if bypassed -> `SS_PENDING_LIVE_FLIP_ADMIT++`,
  `SS_PLF_PUBLISH_PENDING=1`. `ssPublishCoarseFlip`: -> `SS_PENDING_LIVE_FLIP_PUBLISH++`.
- **Sprite-pointer coherence for a live $D018 flip** (the 4E "frozen page-B table"
  gap, now load-bearing because 199/235 has a reuse batch every frame):
  - `applyLiveRasterBatch` (raster IRQ): the pointer store `sta $07f8,x` becomes
    `ssBatchPtrStore: sta $07f8,x` with its **hi byte self-modified** (from the
    main thread, at each flip in `ssPublishCoarseFlip`) to the ACTIVE page's table
    ($07F8 / $2BF8). Zero per-assignment cost; ~11 cy once per flip.
  - `ssFlipMirrorPtrs`: under 4F, ALWAYS mirrors `$07F8 -> $2BF8` every frame
    (from `finishBackgroundCoarse`), so page B carries the frame's initial
    (renderSprites) pointers.
  - `hudBorderSetup` / `hudBorderHandoff`: `bit SS_PAGEB_ACTIVE / bpl / sta $2bf8..`
    -- also write page B only while it is the displayed page.
  - `SS_PAGEB_ACTIVE` ($80 when B active) maintained by `ssPublishCoarseFlip`.

## Results

### Decisive question -- YES
199/235 fixture (8 enemies Y=199 + player Y=235), Mode C, per-frame probe over 700
frames: `SCROLL_ROW` 392 -> 359 (**33 rows advanced**), **33 fine 7->0 crossings**,
no longer pinned at fine 7. `COARSE_DEFER_LIVE` still counts every reason-1 fire;
`SS_PENDING_LIVE_FLIP_ADMIT` 32, `SS_FLIP_FALLBACK` 0, `SS_LEGACY_COARSE_PATH_COUNT`
0. Mode B baseline on the same fixture: `SCROLL_ROW_moves 0`, `COARSE_DEFER_LIVE`
300/300, 0 flips -- permanently pinned, as Stage 4E.

### LIVE batch service -- correct
- `RASTER_INCOMPLETE_FRAMES = 0` over 700 frames (every expected assignment
  completes in its physical frame).
- `RASTER_LAST_EXPECTED == RASTER_LAST_DONE` (byte) on all sampled frames incl.
  transition frames.
- `check_raster_capture` `sprite_start_miss_count = 0` on the 199/235 scrolling
  capture (400 frames) and on `vice_raster_cases coarse_late_dma` (16 Y199/235
  objects, parked-main raster stress: `service_failure_count 0`, `sprite_start_miss 0`).
- **Active-page pointer table == expected final pointers (render-plan initial +
  serviced LIVE assignments): 200/200 frames** at raster 300, A active and B active.
  -> no flip-frame pointer lag/corruption.

### Regression (check_raster_capture, Mode C vs Mode B)
| fixture | replay | catchup | [19656] | service fail | sprite-start miss |
| idle 300 | 0 | 0 | yes | 0 | 0 |
| authored wave (seed 382) 320 | 0 | 0 | yes | 0 | 0 |
| stage wrap (seed 12) 340 | 4 | 1 | yes | 0 | 0 |  (<= 4E baseline 8)
| 199/235 scrolling 400 | 10 | 0 | yes | **198 "final sprite pointers" (oracle)** | 0 |
| --dense 16-obj 200 | 99 | 1393 | yes | 0 | **17 (Mode B baseline 3)** |

## Bounded items (=> AMBER)
1. **check_raster_capture "final sprite pointers"** (198/400 on 199/235): the oracle
   reads page A's `$07F8` unconditionally; with a live `$D018` flip the ACTIVE
   table alternates to `$2BF8`. The ACTIVE table is provably correct (200/200 live
   match). The capture does not dump `$2BF8` / `BG_ACTIVE_PAGE`, so a full oracle
   fix needs a `vice_scroll_test.py` capture change + `check_raster_capture.py`
   page-awareness -- deferred; documented like the Stage 4D `initial snapshot
   trace` / `check_scroll_edges` RSEL=1 oracle caveats.
2. **--dense +14 sprite-start misses** and **199/235 ~2.5% replay frames**: same
   root cause -- 4F un-freezes the coarse scroll on permanently-pending-LIVE
   scenes, so the incremental builder's ~16,000 cy/coarse-cycle now RUNS on them
   (in Stage 4E those scenes were reason-1-frozen and the builder idled). All such
   frames are still fully serviced (`[19656]`, 0 catchup, 0 incomplete, 0 service
   failure, 0 sprite-start miss on supported gameplay). Real gameplay
   (idle/wave/wrap) shows NO regression.

## Verdict: AMBER
The double-buffered `$D018` scroller CAN progress through the pending-LIVE
sprite-reuse condition without compromising raster service (batches serviced,
cadence exact `[19656]`, active-page pointers correct 200/200, matrix/logical
coherent, wrap unchanged). Reason 1 is architecturally obsolete FOR THE PREPARED-
PAGE FLIP PATH -- the flip touches no sprite hardware and no batch state -- but
its removal is not zero-cost: the incremental builder load it was implicitly
gating now lands on formerly-frozen scenes. Kept AMBER (not GREEN) for: the oracle
update, and the measured synthetic-worst-case builder-load cost.
Reasons 2/3 retained. Legacy fallback keeps reason 1. Relaxation isolated behind
`OPT_SS_ALLOW_PENDING_LIVE_FLIP`. Modes A & B bit-identical. Soft-edge untouched.
No commit/push/tag.
