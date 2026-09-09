# Passive top-row turret flicker — worklog

**STATUS: COMPLETE — GREEN, ready for user visual acceptance.**
Full report: `/reports/passive-top-row-turret-flicker-investigation.md`.

Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed.

## Root cause
`ssReconcileTurretSlot`, `!relHi` branch. Matrix row `m` holds world row
`SCROLL_ROW + m - 1`, so the top body row is **always** `rel + 1`. For
`rel == SLR-1` (i.e. `rel == -1`) that is row **0**, but the code set
`TURRET_CELL_ROW = $ff` (row -1) and put the BOTTOM pair in row 0, leaving row 1 —
the first fully visible aperture row — as bare terrain for a whole coarse cycle.
`rel == SLR-2` was not handled at all. `installTurretRow` (legacy/render path)
drives off `BG_LOGICAL_ROW` and was always correct, so the two publication paths
disagreed and the top-edge glyph changed depending on which one published.

## Fix
Nine lines in that branch: `rel == SLR-1` → top row 0 (bottom 1);
`rel == SLR-2` → top `$ff` (bottom row 0). No new state, no timing change.

## Result
Row-0/row-1 turret oracle: **45–137 wrong cells per capture → 0** on all 7 seeds,
the 4-turret cluster (700 frames) and 3 stage-wrap crossings. Phase B(b)'s
previously-undiagnosed row0→row1 signature is now **0** (was 1–2 per capture).

## Why "three turrets" and "~128 frames"
Authored turret rows `345,337,329,321,225,217,117,109,25,5` — dominant gap is
**8 world rows**; one coarse step is 16 frames, so **8 × 16 = 128 frames** between
entry events. Rows cluster in groups of 8 apart, so 3–4 turrets are in view during
a cluster. The defect is per ENTRY EVENT (~40 wrong cell-samples each), not per
turret, so turret count only sets the event rate.

## Method notes / gotchas
- The oracle must be built from the authoritative mapping
  (`BG_LOGICAL_ROW = SCROLL_ROW + BG_DEST_ROW - 1`), **not** from
  `ssReconcileTurretSlot` — the routine under test was the thing that was wrong.
  My first oracle assumed reconcile's convention and produced nonsense.
- **Exclude frames where `SS_FLIP_ADMIT` increments**: `SCROLL_ROW` is already
  decremented at the raster-311 dump while `$D018` flips next frame top, so the
  displayed page is legitimately one row behind. Every residual after the fix was
  exactly this transient — 100% of them.
- A VICE store watchpoint (`watch store <addr>`) on the single row-0 turret cell
  settled "wrong data vs late write" instantly: only `ssInstallInactiveRow0` wrote
  it, always terrain, always early ⇒ wrong data.
- Row 0 spans rasters `48+YSCROLL .. 55+YSCROLL`; the Stage-5 aperture opens at 58,
  so the row-0 sliver is visible only at `YSCROLL >= 3`. Row 1 is fully visible —
  which is why the row-1 half of this bug mattered most.
- Mask ON/OFF gives identical oracle counts ⇒ the mask is incidental, not causal.

## Regression
`[19656]` on all 7 fixtures; 0 sprite-start misses incl. `--dense`; dense
catchups/replay 1386/100 unchanged; aperture 58..247 on 130/130; title `$D011=$9b`
ECM=0 with 16 star glyphs. B(b) intact: 19 attempts = 10 page-A + 9 page-B + 0
refusals, 0 snaps, 0 dups, 2-frame stall baseline.

## Binaries
default `3f398975ba6a5ba7`, mask-OFF `defbfdcbfe4d48e2`.

## Untouched / still open
- Dead-turret bodies not erased on page B (`background_turrets.asm` page-blind).
  Needs turret destruction, so outside the passive scenario.
- Page-B `$2BF8` sprite-pointer race (`ssFlipMirrorPtrs` after a LIVE write);
  wrap service failures 3 → 2, variance only. Recommended next bounded task.
