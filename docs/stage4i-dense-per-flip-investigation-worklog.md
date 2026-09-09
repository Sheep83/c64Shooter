# Stage 4I — Mode-C dense per-flip / mux cost investigation — worklog

Branch `experimental-border-hud`. HEAD `479bb32` ("Bug fixes related to coarse
transition") — Stage 4G+4H now committed **and pushed**; tree clean at start and
finish. No new tag exists; `stable-double-buffered-scroller` untouched. No
commit/stage/tag/push performed. **No source change made** — all three baseline
hashes rebuilt and verified: A `f2abc225159e81bf…`, B `e0c3141a7ee88f8f…`,
C `80d5b0461c070fe2…`. `build/shooter.prg` left at Mode A.

## Method
No C64 instrumentation added. Everything came from data the captures already
carry: the existing trace labels, the Stage-4G `.actpage` byte, and the
`physical_fine` ($D011 & 7) value in `frames.json`. Two tool-side additions were
made in **scratchpad copies only** (repo `tools/` untouched): a `--dense-yshift`
option for the falsification experiment, and `trace store d018 d018` to measure
the publication raster. Neutrality checked — the traced run reproduced the
untraced miss count/cadence exactly.

## Findings, in the order they fell out
1. **Every** miss in every mode is the same event: `rasterBatchMasksApplied` for
   the final batch of the LIVE plan (batch-array offsets 7/15), whose min
   `ASSIGN_Y` is 164 — the dense fixture's bottom-most objects. Deadline is
   raster 164 cycle 55.
2. Publication frames were identified independently (`gameplayPresented` present,
   `bgLowerReady` absent) and matched the `.actpage` flips exactly: 18 flips /
   600 frames. **0 of 53 misses land on a publication frame, or within ±4 of
   one**; they cluster at +16/+17/+19 — the opposite phase of the 32-frame coarse
   cycle. That kills the per-flip hypothesis outright.
3. **100% of misses, every mode, every run, occur at `SCROLL_FINE == 4`.** And
   `164 & 7 == 4` — line 164 is a badline exactly at that YSCROLL.
4. Timing distribution: 7 of 8 phases finish by 10355 (30–32 cy of slack vs the
   10387 deadline); fine==4 splits across it (median 10388, max 10412). Landing
   positions are 164:56 / 165:13 / 165:17 — cycle 56 being the first cycle back
   after the badline's ~40–43 stolen cycles. 66% of misses are **1 cycle** late.
5. **Falsification test passed**: shifting the fixture's object Y by +1 (deadline
   line → 165) moved the vulnerable phase from fine 4 → **fine 5** (165&7==5),
   miss rate unchanged (15/24 vs 16/24). Mechanism confirmed.
6. **No Mode-C code cost exists.** `applyLiveRasterBatch` assembles byte-identical
   in B and C (same $6287, same 86 bytes); `ssBatchPtrStore` is `9D F8 07`, the
   same 5-cycle `sta abs,X` as Mode B's `sta HW_SPRITE_POINTER,x` ($07f8) →
   **0 cycles**. `ssFlipMirrorPtrs` (125 cy static) is shared by both modes since
   the 4H repair. `$D018` publication **measured at raster 32** — 132 lines
   (~8,300 cy) before the deadline, on 3% of frames. No `sei`/`cli` in any
   Stage-4 path, so main-thread interference is bounded by ≤7 cy interrupt
   latency — cannot consume 30–32 cy of slack; only the 40–43 cy badline can.
7. Batch-chain completion median is **10348 in Modes A, B and C alike** — Mode C
   adds no delay even versus a build with no second screen at all.
8. **It's exposure, not cost.** Reason 1 pins Mode A *and* Mode B at fine==7 for
   173/200 dense frames, so they see fine==4 only 4× (startup transient). Mode C
   scrolls, so it sees it 24×/200 (76×/600). Per-exposed-frame rates: A 3/4 (75%),
   B 2/4 (50%), C 16/24 (67%), C-600 53/76 (70%) — Mode A, the shipped
   single-screen baseline, is the worst.

## Regression status (committed Mode C, unchanged build)
idle 300 / wave 320 / wrap 340 / y199 400 / turret 500 / stress 500 — all
`[19656]`, 0 incomplete, **0 sprite-start misses**. Dense 200/600 — 16/53 misses,
all fine==4, on blank sprites. Wrap's single service failure is the known Stage-4G
HUD-modeling caveat, re-confirmed at frame 131 = the exact flip-transition frame,
slots 4–7 only. Page-aware oracle active and passing throughout.

## Verdict: GREEN — causal account complete, no fix justified
The gap is a VIC-II badline colliding with one deadline at one scroll phase, is
present in the single-screen baseline at an equal-or-worse per-exposure rate, and
is confined to a synthetic 16-object fixture with blank sprites. Closing the ~10
cycle deficit would need mux-scheduling changes — a do-not-reopen area with two
recent measured regressions — for no benefit in supported gameplay. Recommend
tagging a new checkpoint on `479bb32` (user action; `stable-double-buffered-
scroller` stays put), then a small bounded task to make Mode C the default build.
