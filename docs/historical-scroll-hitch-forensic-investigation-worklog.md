# Historical scroll hitch — forensic investigation — worklog

**STATUS: Phase A COMPLETE (diagnosis proven). No fix applied, no source touched.**
Full report: `/reports/historical-scroll-hitch-forensic-investigation.md`.

Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed. Only
pre-existing Stage 5A/Fable/5B modifications in the tree.

## Root cause (proven)
`shiftBackgroundUpper` / `shiftBackgroundLower` / `saveCrossingRow` /
`restoreCrossingRow` / `copyIncomingRowToScreen` hard-code `BG_SCREEN_A`. The
legacy coarse fallback (`main.asm:6308`) therefore mutates `$0400` regardless of
`BG_ACTIVE_PAGE`, while still advancing `SCROLL_ROW` / clearing `SCROLL_FINE`.
Page B live ⇒ visible terrain does not advance ⇒ **−7px backward snap**, then a
permanent 1-row desync ⇒ on the next flip the builder's stale copy (row `rel`)
and the reconcile's correct copy (row `rel+1`) coexist because
`ssReconcileTurretRow` never erases ⇒ **duplicated turret top body**.

## Deterministic law
19 legacy events across 8 captures: **10 on page B ⇒ 10 freezes; 9 on page A ⇒ 0
freezes.** 1:1, no exceptions. Every event occurred at 6–7 live enemies with min
`OBJECT_Y` 0–1. Seed with low enemy load (224): zero events.

## Timeline finding — contradicts the task premise
Current tree with `OPT_SECOND_SCREEN` + `SCROLL_EDGE_MASK` off builds
`f2abc225159e81bf` = **byte-identical to the `stable-single-screen-scroller` tag
build**. That control shows 0 freezes / 0 duplications on 8 captures.
`stable-double-buffered-scroller-v2` ships with `OPT_SECOND_SCREEN` commented
out — double buffering became default only at **Stage 4J**. So the defect does
NOT predate Stage 4.
A *different*, genuinely older mechanism exists: pre-Stage-4 `--dense` gives
47,361 coarse deferrals and the scroll stalls — but 0 deferrals in ordinary
6-enemy waves.

## Binaries
- `80d5b0461c070fe2` mask-OFF = accepted Stage 4J (reproduces the defect).
- `f2abc225159e81bf` Mode A = `stable-single-screen-scroller` tag (clean).
- `69224428ddb05c8a` current working tree (reproduces the defect).

## Gotchas / corrections
- **My earlier "3-frame fine hold" signature was invalid** — the clean baseline
  shows the same holds. Aliasing between the raster-311 sample point and
  `SCROLL_FRAME_COUNT`. Use the content-based visible-page oracle instead.
- Capture breakpoint is raster `$137` (line 311, end of frame). Dump N =
  (matrix at end of frame N, fine displayed during frame N).
  `shiftBackgroundLower` runs at the *next* frame's top, so an apparent
  upper/lower "tear" at a page-A legacy event is a sampling artefact, not a
  defect.
- Naive "two 226,227 pairs in a column" over-counts when two turrets share a
  column; require an *adjacent* row pair.
- PNG calibration for this capture: col `c` → `x = 32 + c*8`, row `r` →
  `y = 26 + r*8` (384×272 frame).
- numpy is not installed; PIL is.

## Not done (Phase B)
No repair implemented — awaiting a decision between (a) refuse the legacy path
when `BG_ACTIVE_PAGE != 0` and defer instead (~6 instructions), and (b) make the
legacy path page-aware (~1 KB duplicated unrolled code, cycle-neutral). Plus the
optional builder-margin increase that would stop the fallback being reached.

## Untouched
Stage-4F `ssFlipMirrorPtrs`-after-batch race (wrap frame 88), dense signature,
Stage 5A/5B work.
