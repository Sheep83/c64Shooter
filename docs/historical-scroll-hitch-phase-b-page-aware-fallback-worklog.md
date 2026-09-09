# Historical scroll hitch — Phase B(b) page-aware fallback — worklog

**STATUS: COMPLETE — GREEN, ready for user visual acceptance.**
Full report: `/reports/historical-scroll-hitch-phase-b-page-aware-fallback.md`.

Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed.

## What was done
Legacy in-window coarse fallback is now page-aware. `SS_LEGACY_PAGE` latches
`BG_ACTIVE_PAGE` at the gate; both the upper half and next frame's lower half
dispatch on that latch. Page-A routines UNTOUCHED (verified byte-identical).
New page-B routines `shiftBackgroundUpperB` / `shiftBackgroundLowerB` /
`saveCrossingRowB` / `restoreCrossingRowB` at `LEGACY_PAGEB_SEGMENT = $8640`
(`$8640..$873d`, 254 bytes). `copyIncomingRowToScreen` and the predecode hit path
in `bgConsumePredecodedRow` made page-aware (they built `TEXT_DST` from the
page-A-only `starRowLo/Hi`). Toggle `LEGACY_FALLBACK_PAGE_AWARE` (default ON);
off = exact B(a) refuse-and-defer. Refuse path retained as safety net.

## Result
13 captures: 32 attempts = 14 page-A + 18 page-B + **0 refusals**.
**0 snaps, 0 duplicated turrets, max stall back to 2 frames** (B(a): 36).
Regression: `[19656]` all 7 fixtures, 0 sprite-start misses incl. `--dense`,
dense catchups/replay 1386/100 identical to baseline, aperture 58..247 on 130/130.

## Key corrections / gotchas
- **B(a)'s "~1 KB duplication" estimate was wrong — it is 6,004 bytes.** Does not
  fit in `$6600..$87ff` alongside a full-budget level (~5 KB of stage tables);
  `$a000..$bfff` is BASIC ROM (no `$01` write anywhere in the program). Hence the
  compact indexed approach instead of a mirror.
- **First compact attempt (`dex/bpl`, 14 cy/byte) was TOO SLOW**: `bgUpperCopied`
  at raster 297–311, `bgUpperReady` often not inside the frame at all, causing a
  one-row turret misalignment (delta `+2`) on 5 of 9 page-B executions. Fixed by
  unrolling 8-deep (10.4 cy/byte) → `upperCopied` 272–291. **A late row-0 write is
  a corrupt top row — do not make this path slower.**
- Both shifts overlap `dst = src + 40`, so chunks MUST be emitted highest-first
  with `X` descending. An index of 239 is negative to `bpl`, so chunks are ≤ 240
  with the `txa/sec/sbc #8/tax/bcs` step.
- **Tightest number in the change:** page-B lower half finishes at raster 137–138
  against row 13's fetch at ~152 (comments say 160) → 14–22 lines of margin.
  Re-measure if this path ever slows down.
- Analysis trap: `BG_COARSE_DEFERRED` is outside the `.coarse` dump (see the B(a)
  worklog). Another: comparing the whole `$0400-$07ff` dump for "stall" includes
  the sprite-pointer table and hides everything — compare terrain rows 2..23 only.
- Turret-coherence analysis must exclude columns shared by two turrets and
  turrets not fully on screen, or dead-turret ghosts and row-0 entrants show up as
  false off-by-ones.

## Pre-existing defects found and DISCLOSED (not fixed)
1. **Dead turrets are never erased on page B.** `src/background_turrets.asm` has
   zero page awareness (`restoreDeadTurretRow` / `restoreDeadTurretCells` use the
   page-A-only `starRowLo/Hi`). Ghost counts identical before/after B(b)
   (22/31 on page B vs 2–6 on page A). Candidate for the user's visible artifact.
2. **Page-B sprite-pointer race.** All sprite anomalies in the suite are service
   failures on page B `$2BF8` at flip transitions (wrap frames 82, 88, 165) —
   the known `ssFlipMirrorPtrs`-after-LIVE-batch race. Baseline 3, B(b) 3.
   Matches the "single enemy sprite flicker" report. Next step: order the mirror
   so it cannot follow a LIVE pointer write on a late frame.
3. Residual row0→row1 mismatch, 1–2 per capture (unpatched 2–3), recurring on a
   ~128-frame period — points at turret install / predecode, not the coarse path.

## Not verified this session
GAME OVER → TITLE transition: could not drive the player's death through the
monitor (`PLAYER_LIVES`/`OBJECT_DEATH_TIMER` pokes did not take). Title and
gameplay states WERE verified live (title `$D011=$9b` ECM=0, 16 star glyphs;
gameplay ECM=1). The B(b) diff adds no `$D011` write and does not touch
`endGame`/`startGame`/`initRasterScheduler` — but that is reasoning, not a
measurement. Worth one manual pass.

## Binaries
- Mode A `f2abc225159e81bf` = **byte-identical** to `stable-single-screen-scroller`.
- B(b) default `234cdc065a2399ad`; B(b) mask-OFF `34afc81039af0510`.
- mask-OFF ↔ Stage-4J identity remains intentionally broken (engine bug fix).
