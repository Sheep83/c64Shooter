# Scroll Hitch — Stage 4E: Publish Coarse Scroll by `$D018` Page Flip

Branch `experimental-border-hud`. KickAssembler 5.25, VICE x64sc 3.10, PAL.
Continues the Stage 4D dirty working tree.

---

## 1. Executive verdict — **GREEN**

**An admitted coarse scroll is now published as a cheap, coherent `$D018` page
flip.** The legacy visible-matrix mutation (`saveCrossingRow` /
`shiftBackgroundUpper` / in-window `renderStageRowToScreen` / `shiftBackgroundLower`
/ `restoreCrossingRow`) is **skipped entirely** on the flip path
(`SS_LEGACY_COARSE_PATH_COUNT == 0`, `SS_FLIP_FALLBACK == 0` — 100 % of admits
flip). The newly-active matrix is byte-exact to the legacy coarse output (it *is*
the Stage-4D builder's page, whose byte-equivalence — including stage wrap — was
proven in 4D and re-verified here). Turret live-state is reconciled at the flip
(proven both directions, including a turret destroyed between the incremental
build and the flip → **no resurrection**). Sprite pointers use Option B
(late 8-byte mirror, gated by `SS_PTR_MIRROR_READY`). Page roles alternate 1:1
with admits; the 4D builder retargets the new inactive page automatically.

**The decisive criterion is met: the Stage-4D `+1 RASTER_REPLAY_FRAME` per coarse
admit is eliminated.** Idle play (which isolates coarse admits) shows **0 replay
frames over 500 frames**; on loaded fixtures Stage 4E's replay count is **≤ the
Stage-4A–4C baseline's** (wave 1 vs 4, wrap 4 vs 8), so 4E introduces none.

`[19656]` PAL cadence holds in every workload; 0 catchups / incomplete frames /
border bails / service failures / sprite-start misses everywhere except the
pre-existing `--dense` synthetic-stress `sprite_start_miss` (3, identical to the
no-4D/4E baseline). The reason-1 (`COARSE_DEFER_LIVE`) gate is byte-for-byte
unchanged and the 199/235 fixture still defers every frame with no flip. Soft-edge
work was not touched. Modes 1 & 2 are bit-identical to their baselines.

## 2. Exact starting repository / dirty-tree state

```
$ git branch --show-current   experimental-border-hud
$ git rev-parse HEAD          f07b81fbcdb3240fde92e49c8f3694392e0e59df   (unchanged)
$ git status --short
 M src/main.asm
?? docs/stage4d-incremental-inactive-screen-worklog.md
?? reports/stage4d-incremental-inactive-screen-build.md
$ git diff --stat            src/main.asm | 356 (+353 -3)   [before 4E]
```

The Stage-4D changes were kept and built upon (not reset / stashed / replaced).
Stage 4E adds to the same working tree.

## 3. Files changed (4E, on top of 4D)

`src/main.asm` only. `git diff --stat` after 4E: `src/main.asm | 795 (+790 -5)`.
4E hunks:

| area | change |
|---|---|
| toggle block | `#define OPT_SS_FLIP_COARSE` under `OPT_SS_INACTIVE_BUILD` + a needs-4D guard |
| `.const` | `SS_SLICE_RASTER_CUTOFF = 220` |
| `ssInactiveBuildSlice` | **raster-budget guard** (`#if OPT_SS_INACTIVE_BUILD`): stop the slice before a row copy if the beam is past `SS_SLICE_RASTER_CUTOFF` / wrapped; unbuilt rows resume next frame (`SS_BUILD_SLICE_DEFER_COUNT`) |
| `ssInactiveBuildTick` | withhold also on `SS_FLIP_PENDING` / `SS_FLIP_HOLDOFF` (`#if OPT_SS_FLIP_COARSE`) |
| `ssInactiveBuildReset` | tail-call `ssFlipCoarseReset` |
| `prepareBackgroundCoarse` | new `!admitDecided` block: on flip-prereq pass, decrement `SCROLL_ROW` (legacy code, incl. wrap), `SCROLL_FINE=0`, `SS_FLIP_PENDING=1`, `COARSE_ADMIT++`, **return** (legacy path skipped); on fail, legacy fallback + counters |
| `finishBackgroundCoarse` | if `SS_FLIP_PENDING` → `jmp ssPublishCoarseFlip`; the `!done` path tail-calls the every-frame `ssFlipMirrorPtrs` |
| `$9900` Stage-4 block | 4E state + `ssFlipCoarseReset` / `ssFlipPrereqOK` / `ssFlipNoteAdmit` / `ssFlipMirrorPtrs` / `ssReconcileTurretsOnNewPage` / `ssReconcileTurretSlot` / `ssReconcileTurretRow` / `ssPublishCoarseFlip` |

Every functional addition is `#if OPT_SS_FLIP_COARSE`-guarded except the
`ssInactiveBuildSlice` raster-budget guard (`#if OPT_SS_INACTIVE_BUILD` — it is a
strict scheduler improvement and also removes Stage 4D's own replay AMBER; see §15).

No commit / add / tag / push / pull / reset / stash / branch switch. Changes unstaged.

## 4. Toggle matrix + hashes

| mode | toggles | sha256(prg) | note |
|---|---|---|---|
| **1** | `OPT_SECOND_SCREEN` off (default) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` | **bit-identical to the Stage 3 baseline** |
| **2** | SS on, `OPT_SS_INACTIVE_BUILD` off | `326f1686f3cf3d0526579de167dcb6a6806da48c035fd4a9ad93b90852ff8ab9` | **bit-identical to the 4A+4B+4C baseline** |
| **3** | 4D builder on, `OPT_SS_FLIP_COARSE` off | `95f03ff2110721a85fb9aa5b8abbcf49d2c0944814868d225fb2f504099cc6fb` | hash **changed** from `b73c765e…` — the `ssInactiveBuildSlice` raster-budget guard. Strict improvement: also eliminates 4D's replay (§15). 4D builder re-verified byte-exact. |
| **4** | 4D + 4E flip | `98eb5bbbc2fb385efeace6060e876c17c5d87ce9970303e7f2187b9bdc718cd2` | the new production coarse path |

`$9900` block `$9900–$9d7d`; `$9280` block `$9280–$98b4`; all compile-time guards
pass (~600 B free below `$A000`). `build/shooter.prg` is left at **Mode 1**
(`f2abc225…` / d64 rebuilt).

## 5. Legacy coarse control flow before 4E

gameLoop `!frameLoop`: … `updateBackgroundScroll` (sets `BG_COARSE_PENDING` at
fine 7) → BUILD (`sort`/`snapshot`/`batch`/`suppression`) → `predecodeNextStageRow`
→ **`prepareBackgroundCoarse`** → `noteCoarseSuppressionOutcome` (4D tick tail) →
`refreshScoreIfDirty` → `waitForGameFrame` → present chain
(`publishTurretGlyphs` → `applyFineScroll` → `swapRenderPlans` → `renderSprites` →
`armFirstBatch` → **`finishBackgroundCoarse`**) → loop.

`prepareBackgroundCoarse` admit path: gate (reason 1/2/3, unchanged) → spin
`RASTER ≥ 160` → `saveCrossingRow` (320 cy) → `shiftBackgroundUpper` (3 840 cy) →
`SCROLL_ROW -= 1` (16-bit; `0 → SLR` then `-1`, sets `TURRET_STREAM_REWIND` +
`WAVE_TRIGGER_REWIND` on the wrap) → `renderStageRowToScreen` (row 0, ~1 400 cy)
→ `SCROLL_FINE = 0`, `BG_COARSE_FINISH = 1`, `COARSE_ADMIT++`.
`finishBackgroundCoarse` (next frame top): `shiftBackgroundLower` (3 520 cy) +
`restoreCrossingRow` (320 cy). Turret positions/colour are recomputed at the top
of the *next* `!frameLoop` from the already-decremented `SCROLL_ROW`. Colour RAM
(`$D800`) is one shared bank, never scrolled.

## 6. Exact 4E coarse-admit prerequisites

`ssFlipPrereqOK` (called after the unchanged gate, before `SCROLL_ROW` is
decremented). A flip admit requires **all** of:

1. `SS_BUILD_STATE == 2` **and** `SS_INACTIVE_VALID != 0` — the inactive page is a
   complete build. (fail → `SS_FLIP_INVALID_PAGE++`)
2. `SS_PTR_MIRROR_READY != 0` — the inactive page's `+$3F8` pointer table has been
   mirrored. (fail → `SS_FLIP_POINTER_NOT_READY++`)
3. `SS_BUILD_TARGET_ROW == (SCROLL_ROW - 1) mod SLR` — the built page represents
   the *exact* post-coarse row about to be published. (fail →
   `SS_FLIP_TAG_MISMATCH++`)

On any fail the caller takes the compile-time legacy in-window path
(`SS_FLIP_FALLBACK++`, `SS_LEGACY_COARSE_PATH_COUNT++`). Measured over 400 idle
frames + wave + wrap: **all fail counters 0, `SS_FLIP_FALLBACK 0`,
`SS_LEGACY_COARSE_PATH_COUNT 0`** — every admit flips.

## 7. Exact flip-frame ordering

On the admit frame N (`prepareBackgroundCoarse`, build phase):
`ssFlipPrereqOK` → decrement `SCROLL_ROW` (wrap-aware, identical to legacy) →
`SCROLL_FINE = 0` → `ssFlipNoteAdmit` (`SS_FLIP_PENDING = 1`, `SS_FLIP_ADMIT++`,
`SS_FLIP_PATH_COUNT++`) → `COARSE_ADMIT++` → return. No visible-matrix or VIC write.

On frame N+1 top (present chain, `finishBackgroundCoarse` → `ssPublishCoarseFlip`,
**after** `renderSprites` + `armFirstBatch`, so it cannot delay the beam-critical
sprite writes):

1. `ssFlipMirrorPtrs` — copy `$07F8..$07FF` → `(inactive page base + $3F8)`; set
   `SS_PTR_MIRROR_READY`.
2. `ssReconcileTurretsOnNewPage` — per `TURRET_POOL` slot, the 2×2 body CHAR cells
   on the inactive (about-to-be-active) page, against the **post-coarse**
   `SCROLL_ROW`: alive → shared body glyphs 226..229; dead / off-screen → the
   cached `turretGroundCodes` terrain.
3. record `SS_D018_RASTER` ← `$D012`.
4. `$D018 := ssInactiveD018[BG_ACTIVE_PAGE]` — **the publication**.
5. `BG_ACTIVE_PAGE ^= 1`; `SS_PAGE_SWAP_COUNT++`; `SS_FLIP_PENDING = 0`;
   `SS_FLIP_HOLDOFF = 1` (keeps the 4D build tick clear for this frame's build
   phase too).

The 4D build tick (`ssInactiveBuildRefreshTarget` + slice) is withheld on frame N
(`SS_FLIP_PENDING`) and frame N+1 (`SS_FLIP_HOLDOFF`); it restarts the build for
the new `(SCROLL_ROW-1)` target on frame N+2, into the page that is now inactive
(the old active page — the delta tables key on `BG_ACTIVE_PAGE`).

Turret positions/colour: `positionBackgroundTurrets` + `pulseTurretColour` run at
the top of frame N+1's `!frameLoop`, i.e. **before** `ssPublishCoarseFlip`, with
the post-coarse `SCROLL_ROW`. `pulseTurretColour` reverts vacated / dead turret
colour cells to `TERRAIN_COLOUR_RAM`. Since `$D800` is page-independent, the
colour RAM shown on the flipped page is already correct — no 4E colour work, no
second buffer (§10).

## 8. `$D018` write point

Measured `SS_D018_RASTER = 26` (idle) / 31 (wave). The write is well **before the
first badline** (raster 48 at YSCROL = 0), so the VIC latches the new screen base
for the whole visible frame — no mid-frame matrix split. This is the frame-top
window Stage 4C proved raster-safe for A↔B flips (0 border bails / replays /
incomplete frames over 6 000 flips). The write is a single `sta $D018` (4 cy); no
IRQ can pre-empt between prereq validation (frame N) and the write (frame N+1),
because the flip publication runs entirely on the main thread with the frame's
sprite IRQ already armed and idle.

## 9. Proof the legacy matrix mutation is skipped

`prepareBackgroundCoarse`'s flip path `return`s before `!waitRead`, so
`saveCrossingRow` / `shiftBackgroundUpper` / `renderStageRowToScreen` never run
for a flip admit; `BG_COARSE_FINISH` is never set, so `finishBackgroundCoarse`'s
`shiftBackgroundLower` / `restoreCrossingRow` never run. Instrumented:
`SS_FLIP_PATH_COUNT == SS_FLIP_ADMIT == COARSE_ADMIT` and
**`SS_LEGACY_COARSE_PATH_COUNT == 0`** over every measured run (idle 400/500, wave
300, wrap 340). The flip publication removes ~7 700 cy of coarse-frame work
(`shiftBackgroundUpper` 3 840 + `shiftBackgroundLower` 3 520 + crossing-row 640 +
the in-window decode) and replaces it with the ~4-cy `$D018` write plus the
mirror (~60 cy) and turret reconcile (§12).

## 10. Logical `SCROLL_ROW` ordering / colour RAM

The newly-active matrix represents the **post-coarse `SCROLL_ROW`**
(`SCROLL_ROW - 1`, wrap `0 → SLR-1`). Ordering per §7: `SCROLL_ROW` is decremented
on frame N; on frame N+1 the turret position/colour update, then the turret CHAR
reconcile, then `$D018`, then the page-role swap all use that same post-coarse
`SCROLL_ROW`. The displayed page and the logical world state never disagree for a
frame (verified: seeds 0/1/2/200/419/… — `flipped`, `page` toggles,
`SCROLL_ROW n→n-1`, wrap `0→419`, `SS_INACTIVE_VALID == 1` at each flip).

**Colour RAM conclusion:** single bank, not double-buffered, and not needed to be.
Global terrain colour is one value (scrolling it is a no-op). The only dynamic
cells are turret bodies, already recomputed every frame from `SCROLL_ROW` by
`pulseTurretColour`, which runs against the post-coarse `SCROLL_ROW` *before* the
flip and reverts vacated/dead cells. Verified in CASE B (§11): a killed turret's
colour cells read `$09` (`TERRAIN_COLOUR_RAM`) on the flipped page. No colour
ghost, no second colour abstraction.

## 11. Turret live-state reconcile — implementation + results

`ssReconcileTurretsOnNewPage` iterates `TURRET_POOL` (8 slots) via
`ssReconcileTurretSlot`; for each occupied slot it derives the 2×2 body matrix
rows from `rel = (TURRET_SLOT_ROW - SCROLL_ROW) mod SLR` (`rel 0..23` → matrix
row `rel+1`; `rel == SLR-1` → the body's bottom row is matrix 0), then
`ssReconcileTurretRow` writes the two CHAR cells at `TURRET_SLOT_COL`:
`TURRET_HEALTH == 0` → cached `turretGroundCodes` terrain, else body glyphs
`226..229`. Colour RAM is not touched (§10). Diagnostics
`SS_TURRET_RECONCILE_COUNT` (slots touched, running) / `SS_TURRET_RECONCILE_MAX`.

**Mandatory stale-state tests** (M4, seed 355, authored turret slot 7 @ world
row 345, col 17):

| case | result |
|---|---|
| **A — alive across a flip** | flipped page (page 0), matrix row 3, cells `[226,227,228,229]` = **body glyphs present — OK** |
| **B — destroyed between the incremental build and the flip** (`TURRET_HEALTH := 0`, then flip) | flipped page (page 1), matrix row 4, cells `[112,112,112,112]` = terrain, colour RAM `$09` = **no resurrection — OK** |
| **hit-flash around the flip** | colour-RAM only (`pulseTurretColour` / `TURRET_HIT_CRAM`), page-independent; the char reconcile is state-driven (alive→body) so a flashing (alive) turret keeps its body glyphs. No separate failure surface. |

**Reconcile cost:** `SS_TURRET_RECONCILE_MAX` observed 1 (one slot on screen at a
time in the authored stretch); each touched slot is ~2 × 2-cell writes ≈ 40–60 cy;
empty / off-screen slots are the fast `bpl`/`rts` path ≈ 10 cy. Worst realistic
case (all 8 pool slots on screen) ≈ 8 × ~120 cy ≈ 1 000 cy — bounded, at frame
top in the border, and it *replaces* part of the ~7 700 cy the legacy path spent
on that frame, so admit-frame margin is far healthier, not worse (§9, §15). No
whole-matrix rebuild.

## 12. Sprite-pointer strategy — Option B implemented

`ssFlipMirrorPtrs` (~60 cy) mirrors `$07F8..$07FF` → the inactive page's
`+$3F8` table, called (a) every frame from `finishBackgroundCoarse`'s `!done`
(after `renderSprites`), keeping the inactive table current and `SS_PTR_MIRROR_READY`
set, and (b) at the flip itself (first step of `ssPublishCoarseFlip`), so the page
being published carries the frame's initial pointer table. No raster-IRQ
dual-write. For normal gameplay (`max_batches == 0`) the initial table is the
complete table, so the flipped page is fully current; for the reuse case
(`max_batches ≥ 1`) mid-frame `applyLiveRasterBatch` pointer writes land only in
`$07F8` and would be one frame late on the single transition frame — the accepted
Option-B trade (the flip is scheduled so the newly-active page was the inactive
page, and was mirrored, the previous frame). `SS_PTR_MIRROR_READY` gates the flip:
a flip cannot occur with an un-mirrored table (fallback + `SS_FLIP_POINTER_NOT_READY`).

Pointer coherence checks: HUD sprites, player and non-reuse enemy loads render
correctly across A→B and B→A (idle 500 + wave 300 captures: 0 service failures,
0 sprite-start misses, `[19656]`). The reuse / border-marker / HUD-handoff cases
are covered indirectly by the wave and dense captures (0 service failures); a
dedicated per-slot A/B pointer-lag probe for the `max_batches ≥ 1` transition
frame is the one remaining bounded verification (§17).

## 13. Reference / oracle — matrix equivalence

The Stage-4D builder's INACTIVE page was proven **byte-exact to a real legacy
coarse admit** (`s4d_equiv.py` DYNAMIC: 0 of 1 000 character cells differ, seeds
200/60/380/2/1/**0 (wrap → 419)**/419/300). Stage 4E **displays that exact page**
via `$D018`; the only 4E modification to it is the turret CHAR reconcile, proven
correct in §11. Re-run here against the raster-capped M3 (`95f03ff2…`): still
0/1 000 on all 8 seeds including the wrap — the raster-budget guard does not
corrupt the incremental build (partial slices resume correctly). Stage wrap
(`SCROLL_ROW 0`): flip taken, `SCROLL_ROW 0 → 419`, page toggled, builder page
byte-exact.

(A direct M4-vs-M3 full-frame screenshot diff over a turret stretch shows the
terrain in lock-step — many frames pixel-identical, `SCROLL_ROW` matched every
frame — with residual diffs confined to sprite regions from CIA-jitter gameplay
divergence between the two independent emulator runs, not terrain.)

## 14. Page-role swap / target progression

`BG_ACTIVE_PAGE ^= 1` exactly once per flip. Measured (M4, 400 idle frames):
`SS_PAGE_SWAP_COUNT == SS_FLIP_ADMIT == COARSE_ADMIT == 25`;
`SS_BUILD_START_COUNT == SS_BUILD_COMPLETE_COUNT == SS_BUILD_ADVANCE_COUNT == 25`;
`SS_BUILD_INVALIDATE_COUNT == 0`, `SS_BUILD_REDUNDANT_WORK == 0`. The target
advances by −1 (mod SLR) each admit (seamless across the wrap); the builder
restarts once per admit and copies from the newly-active page into the newly-
inactive one; `SS_INACTIVE_VALID` returns to 1 well before the next admit.

## 15. Stage 4D `+1 replay / admit` — eliminated

Traced (interrupted-PC on the stack at `inc RASTER_REPLAY_FRAMES`): the main
thread was inside `ssCopyOneInactiveRow` — a **4D build slice** — when the line-1
IRQ fired, on one frame per coarse cycle where the build phase ran late. **Not**
the legacy shift (`SS_LEGACY_COARSE_PATH_COUNT == 0` confirms it never runs under
4E). Fix: a raster-budget guard in `ssInactiveBuildSlice` — stop before a row copy
if `RASTER ≥ SS_SLICE_RASTER_CUTOFF (220)` or the beam has wrapped; the unbuilt
rows resume next frame (`SS_BUILD_SLICE_DEFER_COUNT`), and the build still
completes every cycle with margin (`ROW0_WAIT == 0`, `START == COMPLETE`).

| fixture | Stage 4D (`b73c765e`) replay | **Stage 4D raster-cap (`95f03ff2`)** | **Stage 4E (`98eb5bbb`)** | Stage 4A–4C (`326f1686`) |
|---|---|---|---|---|
| idle 400 / 500 | +1 per admit (25 / 400) | **0** | **0** | 0 |
| authored wave (seed 382) 300 | 19 | — | **1** | 4 |
| stage wrap (seed 12) 340 | 27 | — | **4** | 8 |
| 199/235 hold 600 | 0 (holds) | 0 | **0** | 0 |
| dense 16-obj 200 | 100 (`--dense` baseline) | — | 99 (`--dense` baseline) | 99 |

Stage 4E replay ≤ the Stage-4A–4C baseline on every fixture; idle (coarse admits
isolated) = 0. **The regression is gone.**

## 16. Full metrics (Stage 4E, M4)

| check | idle 500 | authored wave 300 | stage wrap 340 | dense 200 | 199/235 hold 600 |
|---|---|---|---|---|---|
| `frame_cycle_deltas` | `[19656]` | `[19656]` | `[19656]` | `[19656]` | `[19656]` |
| `RASTER_REPLAY_FRAMES` | 0 | 1 (≤ baseline 4) | 4 (≤ baseline 8) | 99 (`--dense` baseline) | 0 |
| `RASTER_CATCHUPS` | 0 | 1 | 1 | 1393 (`--dense`) | 0 |
| `RASTER_INCOMPLETE_FRAMES` | 0 | 0 | 0 | 0 | 0 |
| `RASTER_BORDER_BAILS` | 0 | 0 | 0 | 0 | 0 |
| `service_failure_count` | 0 | 0 | 0 | 0 | 0 |
| `sprite_start_miss_count` | 0 | 0 | 0 | 3 (`--dense` baseline) | 0 |
| `SS_FLIP_ADMIT` / `COARSE_ADMIT` | 25 / 25 | 16 / 16 | — | — | 0 / 0 |
| `SS_FLIP_FALLBACK` / `SS_LEGACY_COARSE_PATH_COUNT` | 0 / 0 | 0 / 0 | 0 / 0 | — | 0 / 0 |
| `SS_PAGE_SWAP_COUNT` | 25 | 16 | — | — | 0 |
| `SS_BUILD_REDUNDANT_WORK` | 0 | 0 | 0 | 0 | 0 |
| `check_scroll_edges_rsel1 --aperture 55 246` | body 0 / lastrow 0 | — | — | — | — |
| `RASTER_PRESENT_READY` at line 1 | ready every frame (0 replays) | — | — | — | — |

`SS_D018_RASTER` 26 (idle) / 31 (wave) — before the first badline.

## 17. Remaining risks

1. **Reuse-case (`max_batches ≥ 1`) pointer lag on the single transition frame**
   (§12). Bounded by design (Option B); the wave/dense captures show no service
   failure or sprite-start miss, but a dedicated per-slot A/B pointer-value probe
   on that exact frame was not run this pass.
2. **Wave/wrap residual replays** (1 / 300, 4 / 340) are **≤** the Stage-4A–4C
   baseline (4, 8) — pre-existing load-jitter, not 4E — but not literally 0 on
   loaded scenes.
3. **Turret hit-flash exactly on the flip frame** — argued safe (colour-only,
   state-driven char reconcile) but not screenshot-captured.
4. **`SS_SLICE_RASTER_CUTOFF = 220`** is a measured constant, not derived; a very
   different per-frame load profile could want re-tuning (the deferred rows always
   resume, so a wrong value degrades gracefully, never corrupts).
5. **`$9900` block** now `$9900–$9d7d` (~600 B free to `$A000`).

## 18. Explicit confirmations

- **The reason-1 (`COARSE_DEFER_LIVE`) gate was NOT altered.** `prepareBackgroundCoarse`'s
  three gate checks are byte-for-byte unchanged; the flip decision is taken
  *after* the gate has said "admit". The 199/235 fixture still defers every frame
  (`dCOARSE_DEFER_LIVE +600` over a 600-frame hold, `SCROLL_FINE` pinned 7,
  `dCOARSE_ADMIT 0`, **no page flip while blocked** — `SS_INACTIVE_VALID` stays 1,
  every `SS_BUILD_*` counter 0).
- **Soft-edge masking was NOT touched.** `SOFT_EDGE_MASK` remains off/unmodified;
  the 55..246 terrain aperture is temporally clean (`check_scroll_edges_rsel1`
  body 0 / lastrow 0).
- Not done (correctly out of scope): reason-1 gate removal (Stage 4F), BUILD/LIVE
  redesign, JIT mux, object-limit / HUD / collision / wave-editor changes, stage
  multiload, `$2000–$23FF` reclamation, sprite-asset reorg, permanent HUD/player
  sprite work.

## 19. Recommendation for Stage 4F

**Proceed.** Stage 4E answers its decisive question: an admitted coarse scroll is
published as a cheap, coherent `$D018` flip with current turret state and valid
sprite pointers, the legacy visible-matrix mutation is gone from that path, and
the Stage-4D replay regression is eliminated.

Stage 4F: **prove the 199/235 case can scroll *through* the pending-LIVE condition
before any reason-1 gate removal becomes permanent.** With 4E, a coarse step is
now a ~4-cy `$D018` write plus a bounded frame-top reconcile — it no longer needs
the `RASTER ≥ 160` window or a clean 3 840-cy budget, which is the entire reason
the reason-1 gate exists. 4F should: (a) allow a flip admit while a LIVE sprite
batch is still outstanding (the flip does not touch sprite hardware or the batch
chain); (b) prove the pending batch is still serviced correctly on the flip frame
(`RASTER_LAST_EXPECTED == RASTER_LAST_DONE`, 0 sprite-start misses); (c) re-run
199/235 and show `SCROLL_ROW` advancing through repeated coarse steps,
`COARSE_DEFER_LIVE` no longer the structural blocker — *measured*; (d) only then
relax the gate, behind its own toggle, with the legacy path retained.

## 20. Final repository state

```
$ git branch --show-current   experimental-border-hud
$ git rev-parse HEAD          f07b81fbcdb3240fde92e49c8f3694392e0e59df   (unchanged)
$ git status --short
 M src/main.asm
?? docs/stage4d-incremental-inactive-screen-worklog.md
?? docs/stage4e-d018-coarse-publication-worklog.md
?? reports/stage4d-incremental-inactive-screen-build.md
?? reports/stage4e-d018-coarse-publication.md
$ git diff --stat
 src/main.asm | 795 +++++++++++++++++++++++++++++++++++++++++++++++++++++++--
 1 file changed, 790 insertions(+), 5 deletions(-)
```

**No commit, no add/stage, no tag, no push, no pull, no reset, no stash, no branch
switch.** The Stage 4D dirty tree was preserved and extended. `build/shooter.prg`
is Mode 1 (`f2abc225…`).

### Generated test artefacts (scratchpad / /tmp only, not in the repo tree)

`s4e_probe.py`, `s4e_trace.py`, `s4e_pc2.py`, `s4e_ras2.py`, `s4e_equiv.py`,
`s4e_t3.py`, `s4e_shots.py`, `s4d_hold.py`, `s4d_equiv.py`; A/B build trees under
`/tmp/f1../f4`, `/tmp/m3b`; screenshots under `…/scratchpad/s4e/`.
