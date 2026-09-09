# Fable review — seamless scroll edges without hitching — worklog

**STATUS: COMPLETE.** Full review: `/reports/stage5a-fable-edge-solution-review.md`.
Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed. Working
tree carries the reviewed prototype in `src/main.asm` + `src/raster_scheduler.asm`
(supersedes the Stage 5A candidate in place); the Stage 5A candidate as tested is
kept verbatim in `reports/stage5a-candidate-as-tested.patch`.

## Binaries
- `SCROLL_EDGE_MASK` off: `80d5b0461c070fe2…` = accepted Mode C, byte-identical
  (re-verified after every edit; caught one leak — an unconditional `lda #1`).
- Stage 5A candidate: `d06724c6587e2f81…` (busy-wait in the DISPLAY IRQ).
- Final prototype: `b719de4ca86c7f54…`.

## What was measured (tool: scratchpad `vst_review.py` / `run_review.sh` /
`s5r_analyse.py`; traces `prepareBackgroundCoarse`, `bgCoarseReason3Defer`,
`rasterDisplayHook/Restored`, `edgeMask*`; per-frame dump of the COARSE_* block)
1. OFF / ON / wait-STUB on the 6-enemy wave (seed 382) and `--stress`:
   Stage 5A holds the DISPLAY IRQ to raster 60 every frame → display-phase IRQ
   occupancy 755 cycles flat vs OFF 187 p50 / 553 max. Gate/replay/deferral
   deltas are within run-to-run variance (0 real deferrals in all builds) — so
   the hitch link is mechanistic (~570 cycles/frame denied at p50), not
   reproduced as deferrals. `publishRasterPlan` never ran past raster 37
   (latent ECM black-frame hazard, now guarded).
2. Prototype iterations:
   - v1: mask as `RASTER_EVENT_MASK`, arm T−2 → LATE 239/320: compare→hook
     latency is 2–3 lines (KERNAL `$FF48` stub + dispatcher + a badline).
   - v2: arm T−4/−5, catchup-free arming → LATE 28; late frames all on the
     phases with a badline between arm and target.
   - v3: arm T−5/−6 → LATE 0, FALLBACK 3 (badline-phase zero margin at T=57).
   - v4: T=58 → LATE 0 / FALLBACK 0 on wave. **But `--dense` 508 misses**: the
     per-batch `!select` pending check (6 cy) + `!service` `cmp #MASK` (5 cy)
     × 8 batches ate the ~30-cycle catch-up slack.
   - v5 (final): 2-phase `RASTER_DISPLAY_PENDING` (2/1/0) replaces the extra
     flag; SPRITES tested first in `!service` and `rasterIRQ` → batch dispatch
     3 cy cheaper than baseline → `--dense` **0 misses**.
3. Final suite (idle/wave/wrap/y199/dense/turret/stress): `[19656]` all, 0
   incomplete, 0 sprite-start misses, 0 real coarse deferrals, page-aware oracle
   ok; wrap 3 service failures = 2 known HUD flip-transition caveats + frame 88
   (pre-existing 4F race: `ssFlipMirrorPtrs` ran after a LIVE batch on a late
   main-thread frame — both hardware tables agree, oracle expects the batch
   value). Aperture 58..247 on 750/750 frames; HUD band present 450/450.
   Occupancy final: 424 p50 / 680 max (OFF 187 / 553).

## Gotchas
- Nothing may be added to `dispatchRasterEvents` `!select` / `!service` per-batch
  paths; `--dense` has ~30 cycles of slack per frame at the last batch.
- Exact-line VIC writes from this scheduler need the CPU spinning ≥2 lines
  before the line; arm 5 lines early (6 on the badline phase of the target).
- Unpaired runs diverge with CIA jitter; compare occupancy (design property),
  not gate rasters, across builds.
- KickAssembler writes the `.vs` beside `-o`, not into `-odir`.

## Open decisions for the user
- Visual acceptance of `b719de4c…` (edges still, no hitch in 6-enemy waves,
  black surround, sprites visible in the letterbox).
- `EDGE_MASK_BODY_RASTER` 58 → 59 if a single-frame edge flicker is ever seen.
- Bounded follow-up: `ssFlipMirrorPtrs`-after-batch race (wrap frame 88).
