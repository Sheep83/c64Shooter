# Sprite pointer publication race — worklog

**STATUS: GREEN at machine level. Visible-flicker confirmation pending user test.**
Full report: `/reports/sprite-pointer-publication-race-repair.md`.

Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed.
Final build `f1d08a0f5d2337ee` (mask ON); mask-OFF `66d2fa9295e858ac`.

## TWO races found, not one

**Race 1 — HUD reclaim never reached page B.**
`hudBorderSetup` (raster ~2) runs BEFORE the once-per-frame mirror (~23);
`hudBorderHandoff` (~45) runs AFTER it. Both gated their `$2BF8` write on
`SS_PAGEB_ACTIVE` ("only while B is displayed"). So while page A was displayed,
`$2BF8` captured HUD-era pointers from setup and never the gameplay pointers from
handoff. First frame after every A->B flip therefore showed HUD sprite images in
every reclaimed slot. Proof: wrap seed 12 frame 82, slots 4/5/6 expected
154/144/155, actual 188/189/190. Before-fix staleness was large: y199 199/400
frames A!=B, dense 127/250.
FIX: write `$2BF8` unconditionally in both routines. CHEAPER than the gate it
replaces (-7 cy/slot page B, -1 cy/slot page A). Page B isn't VIC-fetched while
inactive, so the store is always safe.

**Race 2 — the original 4F mirror-after-batch race.**
`ssBatchPtrStore` self-modifies to write ONLY the active page, so with page B live
`$07F8` keeps the frame-top plan. The mirror ran at `finishBackgroundCoarse`'s
tail — AFTER `armFirstBatch` — so on a late main-thread frame the IRQ published
`$2BF8` first and the mirror stamped the stale plan back. Proof: wrap frame 88,
slot 6 expected 155 (batch), actual 194 (plan); mirror@66 that frame vs @24-31
neighbours.
FIX: move `jsr ssFlipMirrorPtrs` to `armFirstBatch`'s ENTRY. `renderSprites` is
the immediately preceding call (source complete) and the IRQ is not yet armed (no
batch can precede it). Row shifts never touch `$07e8-$07ff`, so nothing lost.
Structural proof after: 0/400 frames with mirror after first LIVE assignment;
latest mirror raster 36 (was 66).

## Result
All 7 regression fixtures: `[19656]`, **svcFail 0**, ptrFail 0, spriteMiss 0.
The wrap fixture's long-standing "pre-existing" 3 service failures WERE this race
and are gone. `--dense` catchups/replay 1386/100 unchanged. Slot 0 (player)
divergence 0/400, 0/400, 0/250 (passive, combat, dense). Zero divergence on any
flip frame. B(b), rel==-1/-2 oracle, turret colour fix, aperture 58..247 all intact.

## Gotchas
- Main code block had only ~1 byte of headroom; the added `jsr` overflowed into
  the `$1f00` lookup tables. Moved those to `ENGINE_LOOKUP_SEGMENT = $1f20`
  (alignment-free read-only, 101 bytes of slack, still below `$1fc0`).
- A python edit script asserted mid-way AFTER a successful replace, leaving the
  tree with the mirror removed and never re-added — a silently broken build that
  still assembled. Re-check `grep -n ssFlipMirrorPtrs` after any such edit.
- `$07F8` legitimately lags while page B is active (batch writes only the active
  table). Do NOT treat `$07F8 != $2BF8` as a failure per se — direction matters.
  Residual 2 frames of `slot6@pageB` divergence are correct.
- Do not use `vst_hitch.py` for passive symptom work: it holds FIRE every frame.

## Not fixed (bounded scope)
- `ssPublishCoarseFlip`'s own mirror still runs after `armFirstBatch`; needed
  there (must precede `$D018`), harmless for A->B, ~700 cy exposure on B->A.
  No oracle failure observed from it.
- Mode B (`!OPT_SS_ALLOW_PENDING_LIVE_FLIP`) has the equivalent HUD gate keyed on
  `BG_ACTIVE_PAGE` — same latent flaw, not compiled in the default build.
