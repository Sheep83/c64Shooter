# Historical scroll hitch — Phase B(a) safe fallback gate — worklog

**STATUS: COMPLETE — AMBER. Do not ship alone.**
Full report: `/reports/historical-scroll-hitch-phase-b-safe-fallback.md`.

Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed. Repair +
instrumentation left uncommitted alongside the pre-existing Stage 5A/5B work.

## What was done
Guard at `!legacyCoarsePath` (`main.asm:6324`): if `BG_ACTIVE_PAGE != 0`, refuse
the fixed-`$0400` legacy coarse path and `jmp !defer` (the EXISTING defer path —
no second mechanism). Page A behaviour byte-for-byte unchanged.
Counters appended to `ssFlipStats`: `SS_LEGACY_PAGEB_BLOCK`,
`SS_LEGACY_BLOCK_STREAK`, `SS_LEGACY_BLOCK_STREAK_MAX`. New `COARSE_LAST_REASON=4`.

## Result
- **0 visible 7px snaps, 0 duplicated turrets** across 13 captures (before: 10
  snaps, up to 256 duplicated frames). `SCROLL_ROW` stays aligned with the
  visible page on every frame.
- **But**: terrain stalls of 3–36 frames replace the 1-frame snap (baseline 2).
  Only 18.8% of refusals clear on the next frame. Worst case 36 frames = 0.72 s.
- Verdict AMBER; recommend **Phase B(b)** (page-aware legacy fallback), not
  builder tuning — throughput would need ~3× under peak load (measured 1.52
  rows/frame at low load vs 0.50 during the stall).

## Regression
Exact PAL `[19656]` on all 7 fixtures. 0 sprite-start misses incl. `--dense`.
dense catchups/replay 1386/100 = identical to pre-patch baseline. wrap service
failures 2 (pre-patch 3). Aperture 58..247 on 130/130 for wave/wrap/dense/turret/
stress. Title screen ECM=0, YSCROLL=3, 12 star glyphs — Stage 5B intact.

## Binaries
- Mode A patched `f2abc225159e81bf` = **byte-identical** to the
  `stable-single-screen-scroller` tag build (guard is inside `#if OPT_SS_FLIP_COARSE`).
- mask-OFF: `80d5b046…` → `00a25b367e0151ab` — **intentional** drift (engine bug
  fix, compiled unconditionally in double-buffered builds; §14 says do not contort).
- default: `69224428ddb05c8a` → `e966903477a03a91`.

## Gotchas
- **Segment overflow**: the guard pushed the relocated background-control block
  from `$98fa` past the Stage-4 block at `$9900` ("memoryblock overlaps"). Fixed
  by moving that CPU-only block to `SS_STAGE4_BASE_ADDR = $9980` (now
  `$9980-$9e6f`, still below `$a000`) plus a named `.error` assert.
- **`BG_COARSE_DEFERRED` ($979e) is NOT inside the `.coarse` dump** (which starts
  at `COARSE_DEFER_LIVE`, $979f). Reading it by offset gives a negative index and
  silently returns garbage — this invalidated the deferral figures in the earlier
  forensic report (since corrected there). Use the reason counters instead.
- **Stall oracle must exclude the sprite-pointer table**: comparing the whole
  `$0400-$07ff` dump makes every frame differ, hiding stalls completely. Compare
  terrain rows 2..23 only, together with the live fine value.
- Reversing exactly the three hunks reproduces `69224428ddb05c8a`, which is a
  cheap containment proof worth repeating on future edits.

## Not done (deliberately)
Phase B(b), builder throughput/margin changes, slice-window or
`SS_PLF_BUILD_SLICE_ROWS` changes, raster cutoff moves — all forbidden by §15.
