# Stage 4H — Repair Mode-B sprite pointer mirror and re-baseline — worklog

Branch `experimental-border-hud`. HEAD `cd24b8c` (Stage 4F, on tag
`stable-double-buffered-scroller` = Stage 4D+4E `931dca1`). Stage 4G's
uncommitted changes (page-aware oracle + v4 builder-load tuning) were present
at start and preserved throughout. No commit/push/tag; tag not moved. Source
and `build/` left at Mode A.

## Repair
`ssFlipMirrorPtrs`'s pre-4F (`#else`) branch used `sta (SS_FLIP_TMP_LO),y` —
indirect-indexed addressing on a non-zero-page pointer ($9B6A/$9B6B).
KickAssembler silently assembled `STA ($6A),Y`, truncating to the pointer's
low byte and dereferencing unrelated zero-page memory instead. `$2BF8` was
therefore never written in Mode B. Replaced the whole routine with the
proven absolute,X copy loop Stage 4F's branch already used (`lda $07f8,x /
sta $2bf8,x` × 8) — no `#if`/`#else` split remains; both modes share the one
implementation now. Confirmed via disassembly: `9D F8 2B` = `STA $2BF8,X`,
no `(zp),Y` anywhere in the path.

## Second gap found and fixed (same objective)
The first post-repair proof run showed wave/wrap/turret/stress still failing
heavily (idle was clean). Root cause: `hudBorderHandoff` reclaims a HUD slot
for gameplay via a raster IRQ event that fires *after* the once-per-frame
mirror, writing only `$07F8` in Mode B (the Mode-C dual-write there is gated
on the 4F-only `SS_PAGEB_ACTIVE` flag, absent in Mode B); `hudBorderSetup`
had the same gap at frame-top. Added a parallel Mode-B-only branch at each
site (`#if OPT_SS_FLIP_COARSE && !OPT_SS_ALLOW_PENDING_LIVE_FLIP`) using
`BG_ACTIVE_PAGE` (available in both modes) as the equivalent test, writing
the same `$2bf8[+HUD_SLOT_FIRST],x` target the 4F branch already uses.
Register care: `hudBorderSetup` uses free Y for the test (A holds the
pointer byte); `hudBorderHandoff` already uses Y, so A is held on the stack
across the test instead. Verified via disassembly: reclaimed pointer reaches
`$2BF8` in the same instruction sequence as `$07F8`, no lag. This closed
wave (144→0) and wrap (65→4) failures; turret-playtest and stress went to
0/500 clean.

## Byte-identity checks (after every edit, both fixes)
Mode A: `f2abc225159e81bf…` unchanged throughout. Mode C: `80d5b0461c070fe2…`
unchanged throughout (Stage 4G's hash, reconfirmed — none of the new code
compiles under `OPT_SS_ALLOW_PENDING_LIVE_FLIP`). Mode B (corrected):
`e0c3141a7ee88f8f…` (old broken hash was `98eb5bbbc2fb385e…`).

## Proof
Page-aware oracle, corrected Mode B: idle 300f/0 fail, wave 320f/0 fail,
`--dense` 200f/0 fail (page B never displayed, reason 1 unchanged),
`--y199` 400f/0 fail (same), turret-playtest 500f/0 fail, stress 500f/0
fail. Stage wrap 340f/4 fail: 2 are the already-disclosed Stage 4G Finding-2
HUD flip-transition-frame caveat (same signature/frames as Mode C); 2
(frames 88-89) are a new, small, self-correcting residual — direct `$07F8`
vs `$2BF8` byte comparison shows a genuine 2-frame disagreement at one slot,
matching a LIVE reuse-batch reassignment landing on an ordinary
(non-flip) frame while B is already displayed, which Mode B's simpler
once-per-frame mirror (deliberately not given Stage 4F's IRQ-hot-path
dual-write, per this task's scope) cannot instantly propagate. Not chased
further — Stage 4G's own history shows that IRQ-hot-path lever regresses
`--dense` badly (139/368 misses from two prior attempts) for a payoff far
smaller than this residual's size (2/340 frames, zero service impact).

## Crucial question
Corrected Mode B `--dense` sprite-start-miss: 2 (statistically same as the
pre-repair 3 — `page_b_frames = 0` in both, so the pointer bug was never a
factor in this fixture). Mode C `--dense`: 16 (unchanged, reconfirmed).
Confirms the Stage 4G dense gap is real, not an artifact of the old broken
Mode-B baseline.

## Verdict: GREEN, one small disclosed residual
Repair confirmed via disassembly and 1,860/1,860 clean frames across 5
fixtures. One fixture retains a fully-diagnosed, bounded, non-service-
affecting residual, explicitly not silently smoothed over. Mode A/C
unchanged. Recommend committing Stage 4G+4H together, tagging a *new*
checkpoint (leaving `stable-double-buffered-scroller` as the original
archaeological record), and handing a dedicated `--dense`/per-flip
investigation to Opus High as the next task.
