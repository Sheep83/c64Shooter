# Scroll Hitch — Stage 4F: Remove the Structural Pending-LIVE Scroll Block

Branch `experimental-border-hub` … `experimental-border-hud`. KickAssembler 5.25,
VICE x64sc 3.10, PAL. Continues the Stage 4D+4E checkpoint.

---

## 1. Executive verdict — **AMBER**

**The decisive question is answered YES.** With the reason-1 relaxation enabled,
the 199/235 fixture — 8 enemies at Y=199 + player at Y=235, a LIVE reuse batch
outstanding on every frame — **scrolls through the pending-LIVE condition**:
`SCROLL_ROW` advances 33 rows over 700 frames, `SCROLL_FINE` crosses 7→0 33 times,
and it is no longer permanently pinned at fine 7. Every one of those coarse steps
is published as a `$D018` page flip while the LIVE batch is still armed
(`SS_PENDING_LIVE_FLIP_ADMIT` 32, `SS_FLIP_FALLBACK` 0,
`SS_LEGACY_COARSE_PATH_COUNT` 0). The batch is not delayed, lost, corrupted or
mis-scheduled: `RASTER_INCOMPLETE_FRAMES == 0` over 700 frames,
`RASTER_LAST_EXPECTED == RASTER_LAST_DONE`, `sprite_start_miss_count == 0`, and the
**active page's sprite-pointer table equals the expected final pointers
(render-plan initial + serviced assignments) on 200/200 sampled frames**, both A→B
and B→A. Exact PAL cadence `[19656]` holds everywhere. Reasons 2 and 3 are
untouched; the legacy in-window fallback keeps the original reason-1 protection;
the relaxation is isolated behind `OPT_SS_ALLOW_PENDING_LIVE_FLIP`; Modes A and B
are bit-identical to their baselines.

**Two bounded, clearly-identified issues keep this AMBER rather than GREEN:**

1. **`check_raster_capture` "final sprite pointers" oracle limitation.** On the
   199/235 scrolling capture the oracle reports 198/400 `final sprite pointers`
   "service failures" — it reads page A's `$07F8` unconditionally, but with a live
   `$D018` flip the *active* table alternates to `$2BF8`. Direct live measurement
   shows the active table is correct on 200/200 frames; the failures are the
   oracle reading the wrong page. A full fix needs the capture to dump
   `$2BF8`/`BG_ACTIVE_PAGE` and the oracle to become page-aware — deferred and
   documented, exactly like the Stage 4D `initial snapshot trace` and
   `check_scroll_edges` RSEL=1 caveats.

2. **Synthetic-worst-case builder load.** `--dense` (16 stationary objects) shows
   `sprite_start_miss_count` 17 vs the Mode-B baseline 3 (+14); the 199/235
   scrolling capture shows ~10 replay frames / 400 (~2.5 %, comparable to the
   stage-wrap baseline). Same root cause: 4F un-freezes the coarse scroll on
   scenes that were *permanently* reason-1-blocked, so the incremental
   inactive-page builder's ~16 000 cy / coarse-cycle now runs on them (in Stage 4E
   those scenes were frozen and the builder idled). Every such frame is still
   fully serviced — `[19656]`, 0 catchups, 0 incomplete frames, 0 border bails, 0
   service failures, 0 sprite-start misses **on supported gameplay**. Real
   workloads (idle / authored wave / stage wrap) show **no regression at all**.

**Reason 1 is architecturally obsolete for the prepared-page flip path** — the
flip is a ~4-cy `$D018` write plus a bounded frame-top reconcile, it touches no
sprite hardware and no batch state, and it needs neither the `RASTER ≥ 160`
window nor a clean 3 840-cy budget. Its *removal* is not zero-cost only because
the incremental builder load it was implicitly gating now lands on formerly-frozen
scenes.

## 2. Exact starting state

```
$ git branch --show-current   experimental-border-hud
$ git rev-parse HEAD          931dca1e577a57146c9a8edd029dbb2efe2d4136
$ git status --short          (clean)
$ git log -3 --oneline --decorate
931dca1 (HEAD -> experimental-border-hud, tag: stable-double-buffered-scroller, origin/experimental-border-hud) Implement double-buffered coarse scroll publication
f07b81f VIC Bank memory reclaim for screen 2 stage 1 complete
223a820 (tag: stable-single-screen-scroller) Stabilise single-screen scroller under mux load
```

`stable-double-buffered-scroller` **exists** — annotated tag on commit
`931dca1e577a57146c9a8edd029dbb2efe2d4136` ("Implement double-buffered coarse
scroll publication"), which contains the Stage 4D + 4E `src/main.asm` changes and
the 4D/4E worklogs + reports. Tagger Brian Morrice, 2026-09-09.

## 3. Files changed

| file | change |
|---|---|
| `src/main.asm` | `+166` lines: `#define OPT_SS_ALLOW_PENDING_LIVE_FLIP` + guard; the reason-1 bypass in `prepareBackgroundCoarse`; the `!legacyCoarsePath` bypass-safety defer; the 4F state block + `SS_PLF_*` / `SS_PENDING_LIVE_*` / `SS_WOULD_DEFER_LIVE` / `SS_PAGEB_ACTIVE` counters; `ssFlipCoreReady`; `ssFlipNoteAdmit` / `ssPublishCoarseFlip` / `ssFlipCoarseReset` 4F hooks; `ssFlipMirrorPtrs` always `$07F8→$2BF8`; `ssPublishCoarseFlip` self-modifies `ssBatchPtrStore+2`; `hudBorderSetup` / `hudBorderHandoff` conditional page-B pointer write. |
| `src/raster_scheduler.asm` | `+7` lines: `applyLiveRasterBatch`'s pointer store is `ssBatchPtrStore: sta $07f8,x` with a self-modified hi byte (was `sta HW_SPRITE_POINTER,x`). |
| `tools/vice_scroll_test.py` | `+12` lines: `--y199` fixture (8 enemies Y=199 + player Y=235, real scrolling) for `check_raster_capture`. |

Every `main.asm` / `raster_scheduler.asm` functional addition is
`#if OPT_SS_ALLOW_PENDING_LIVE_FLIP`-guarded. **No commit / add / tag / push /
pull / reset / stash / branch switch.** Changes unstaged. `build/shooter.prg` is
Mode A.

## 4. Toggle matrix + hashes

| mode | toggles | sha256(prg) | note |
|---|---|---|---|
| **A** | `OPT_SECOND_SCREEN` off (default) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` | **bit-identical to the Stage 3 baseline** |
| **B** | 4D+4E, `OPT_SS_ALLOW_PENDING_LIVE_FLIP` off | `98eb5bbbc2fb385efeace6060e876c17c5d87ce9970303e7f2187b9bdc718cd2` | **bit-identical to `stable-double-buffered-scroller` (Stage 4E M4)** |
| **C** | 4D+4E+4F | `d3ba25a996c348dfe169d0bd2072acdf01de6faf2fadb0211d8c7d220eb9b2a8` | the reason-1 relaxation |

`$9900` block `$9900–$9de1`; `$9280` block `$9280–$98fa`; guards pass (~500 B free
to `$A000`). Mode B is unchanged from the tagged checkpoint, so Stage 4E is intact
with 4F OFF (criterion 2 ✓).

## 5. Exact old reason-1 condition

`prepareBackgroundCoarse` (SCROLL_HITCH_DIAG build), after `BG_COARSE_PENDING` is
latched and cleared:

```asm
    ldx RASTER_BATCH_OFFSET
    cpx RASTER_BATCH_END
    bcs !gateBeam+          ; OFFSET >= END  -> no pending LIVE batch, continue to reason 2
    inc COARSE_DEFER_LIVE   ; OFFSET <  END  -> a LIVE reuse batch is still outstanding
    lda #1
    sta COARSE_LAST_REASON  ; reason 1
    jmp !defer+             ; coarse step deferred; SCROLL_FRAME_COUNT := DIVIDER-1 -> retry next frame
```

`RASTER_BATCH_OFFSET < RASTER_BATCH_END` means the raster IRQ has not yet consumed
every scheduled sprite-reuse batch of the LIVE plan. Historically this protected
~7 700 cy of raster-sensitive visible-matrix mutation
(`shiftBackgroundUpper`/`shiftBackgroundLower` + crossing-row + in-window decode)
from colliding with the IRQ's mid-frame slot reassignments. On the Stage-4E flip
path that mutation does not run.

## 6. Exact new gated policy

```asm
    ldx RASTER_BATCH_OFFSET
    cpx RASTER_BATCH_END
    bcs !gateBeam+
    inc COARSE_DEFER_LIVE                     ; still counted (reason-1 fired == would-have-deferred)
#if OPT_SS_ALLOW_PENDING_LIVE_FLIP
    lda SS_BUILD_STATE     / cmp #2  / bne !reason1Defer+   ; the prepared page must be
    lda SS_INACTIVE_VALID           / beq !reason1Defer+    ; complete + valid + its
    lda SS_PTR_MIRROR_READY         / beq !reason1Defer+    ; pointer table mirrored
    inc SS_PENDING_LIVE_FLIP_ATTEMPT
    lda #1 / sta SS_PLF_BYPASSED                            ; legacy fallback must NOT run with a pending batch
    jmp !gateBeam+                                          ; skip reason 1; reasons 2 & 3 STILL apply
!reason1Defer:
    inc SS_WOULD_DEFER_LIVE                                 ; reason-1 fired AND flip not ready -> genuine defer
#endif
    lda #1 / sta COARSE_LAST_REASON / jmp !defer+
```

- The **legacy path** (`OPT_SS_ALLOW_PENDING_LIVE_FLIP` off, or the flip prereq
  fails) is byte-for-byte the old behaviour: reason 1 blocks. Criterion 17 ✓.
- Reasons 2 (`VIC_CONTROL_1` bit 7) and 3 (`bgCoarseReason3Defer` / raster cutoff)
  are unchanged and still run after the bypass. Criterion 16 ✓ — measured
  `COARSE_DEFER_BEAM` and `COARSE_DEFER_CUTOFF` still increment under 4F.
- `!admitDecided` still calls `ssFlipPrereqOK` (which additionally checks the
  16-bit tag). **If a reason-1-bypassed admit then fails the tag check
  (`SS_PLF_BYPASSED != 0`), `!legacyCoarsePath` defers instead of running the
  legacy in-window mutation** (`SS_PLF_TAG_DEFER++`) — a pending LIVE batch is
  never exposed to `shiftBackgroundUpper`. Measured `SS_PLF_TAG_DEFER == 0` on the
  199/235 run (the builder always re-tags in time).

Counters: `COARSE_DEFER_LIVE` (reason-1 fired, total), `SS_PENDING_LIVE_FLIP_ATTEMPT`
(bypassed), `SS_WOULD_DEFER_LIVE` (fired but flip not ready → deferred),
`SS_PENDING_LIVE_FLIP_ADMIT` (bypass → passed reasons 2/3 + tag → flip admitted),
`SS_PENDING_LIVE_FLIP_PUBLISH` (its `ssPublishCoarseFlip` ran the `$D018` write),
`SS_PLF_TAG_DEFER`.

## 7. A→B and B→A reuse-transition sprite-pointer proof

**The problem 4F exposes.** On the Stage-4E flip path, `renderSprites` and the
raster-IRQ batch write only page A's table (`$07F8`); page B's `$2BF8` is synced
by a frame-top mirror. That is adequate while a page is displayed with *stable*
pointers, but under 199/235 a reuse batch reassigns a slot *after* the frame-top
flip on *every* frame — the reassignment would land in `$07F8` while the VIC (now
on page B) reads `$2BF8`.

**The fix (three parts, all `#if OPT_SS_ALLOW_PENDING_LIVE_FLIP`):**

| write site | fix | cost |
|---|---|---|
| `applyLiveRasterBatch` (raster IRQ, hot) | pointer store is `ssBatchPtrStore: sta $07f8,x`; its **hi byte is self-modified** (main thread, in `ssPublishCoarseFlip`, from `ssActiveHiDelta[BG_ACTIVE_PAGE]` → `$07`/`$2B`) to the ACTIVE page's table. The IRQ that reads it is non-re-entrant and the patch happens at frame top before that frame's batches fire → no race. | **0 cy per assignment**; ~11 cy once per flip |
| `ssFlipMirrorPtrs` (present chain, per frame) | under 4F, ALWAYS mirrors `$07F8 → $2BF8` (not the `ssInactiveHiDelta` self-copy), so page B carries the frame's `renderSprites` initial pointers | ~50 cy/frame (unchanged from 4E's per-frame mirror) |
| `hudBorderSetup` (line-1 IRQ), `hudBorderHandoff` (DISPLAY-event IRQ) | `bit SS_PAGEB_ACTIVE / bpl / sta $2bf8+…,x` — also write page B only while it is displayed | +7 cy/slot page A, +12 cy/slot page B |

**Proof (`s4f_ptr2.py`, Mode C, 199/235, 200 frames sampled at raster 300 — after
all batches).** For each frame: expected final table = `INITIAL_SPRITE[LIVE+0..7]`
with `ASSIGN_SPRITE` overlaid at each serviced `ASSIGN_SLOT`; actual table read
from `$2BF8` when `BG_ACTIVE_PAGE == 1`, `$07F8` when `== 0`; compare slots
`0..RENDER_COUNT-1`.

```
active-page pointer table vs expected-final over 200 frames @ raster 300:
    MATCH = 200   MISMATCH = 0            (both A active and B active)
```

**Zero flip-frame pointer lag or corruption. Criterion 8 ✓.** (`check_raster_capture`'s
198 "final sprite pointers" hits are the oracle reading `$07F8` while page B is
active — §12.)

## 8. Single controlled 199/235 transition

`s4f_single.py`, Mode C. One coarse step during the fixture:

| point | state |
|---|---|
| **before admit** | `SCROLL_FINE = 7`, a LIVE reuse batch outstanding (`RASTER_BATCH_OFFSET != RASTER_BATCH_END`) — the old reason 1 **would block** |
| **at admit** | `prepareBackgroundCoarse` bypassed reason 1 (`SS_PENDING_LIVE_FLIP_ATTEMPT` ++), passed reasons 2/3 + tag, decremented `SCROLL_ROW`, set `SCROLL_FINE = 0` and `SS_FLIP_PENDING = 1`, `COARSE_ADMIT` ++; **the LIVE batch chain is untouched** (`RASTER_BATCH_*` unchanged, IRQ still armed) |
| **at LIVE service** | the frame's batches run; `RASTER_LAST_EXPECTED == RASTER_LAST_DONE`, `RASTER_INCOMPLETE_FRAMES` stays 0 — the exact batch is serviced, no skip, no double service |
| **at publication** | `finishBackgroundCoarse → ssPublishCoarseFlip`: `ssFlipMirrorPtrs`; turret reconcile; **`ssBatchPtrStore+2` patched to the new active page**; `$D018` written at frame top (raster ~26, before the first badline — 4C-safe); `BG_ACTIVE_PAGE` swapped; `SS_PENDING_LIVE_FLIP_PUBLISH` ++; `SS_LEGACY_COARSE_PATH_COUNT` 0, `SS_FLIP_FALLBACK` 0 |
| **after** | `SCROLL_FINE` resumes 1→2→…; builder restarts for the new `(SCROLL_ROW-1)` target; displayed page agrees with the decremented `SCROLL_ROW` |

## 9. Repeated 199/235 proof (700 frames, Mode C)

| observable | value |
|---|---|
| `SCROLL_ROW` | 392 → 359 (**33 rows advanced**) |
| `SCROLL_ROW_moves` / `SCROLL_FINE` 7→0 crossings | 33 / 33 |
| `SCROLL_FINE` (end) | mid-cycle (3) — **not pinned at 7** |
| `COARSE_ADMIT` / `SS_FLIP_ADMIT` | 33 / 33 |
| `SS_PENDING_LIVE_FLIP_ADMIT` / `_PUBLISH` | 32 / 33 |
| `SS_WOULD_DEFER_LIVE` (fired, flip not ready) | 56 |
| `SS_PLF_TAG_DEFER` | 0 |
| `SS_FLIP_FALLBACK` / `SS_LEGACY_COARSE_PATH_COUNT` | 0 / 0 |
| `SS_PAGE_SWAP_COUNT` | 34 (= flips; the +1 vs `SS_FLIP_ADMIT` is one flip that straddled the counter zero) |
| `COARSE_DEFER_BEAM` / `COARSE_DEFER_CUTOFF` | 112 / 32 — reasons 2/3 **still enforced** |
| `RASTER_INCOMPLETE_FRAMES` / `RASTER_CATCHUPS` / `RASTER_BORDER_BAILS` | **0 / 0 / 0** |
| `SS_BUILD_REDUNDANT_WORK` | 0 |
| `frame_cycle_deltas` (via `check_raster_capture`, 400-frame `--y199` capture) | `[19656]` |
| `sprite_start_miss_count` (same capture) | **0** |
| `replay_frames` (same capture) | 10 / 400 (~2.5 %) |

Mode B on the same fixture: `SCROLL_ROW_moves 0`, `COARSE_DEFER_LIVE 300/300`, 0
flips — **permanently pinned**, reproducing the Stage 4E baseline. Criteria 3, 4,
5 ✓.

## 10. LIVE service, not merely visible scrolling

- `RASTER_INCOMPLETE_FRAMES == 0` over 700 frames → every expected assignment
  completed in its physical frame. Criterion 7 ✓.
- `sprite_start_miss_count == 0` on the `--y199` scrolling capture and on
  `vice_raster_cases coarse_late_dma` (16 Y=199/235 objects, parked-main raster
  stress: `service_failure_count 0`, `sprite_start_miss_count 0`). Criterion 6 ✓.
- Active-page table == expected final pointers, 200/200 (§7): no missing enemy, no
  transient stale sprite, no duplicate, no wrong pointer, **no wrong-page pointer
  table** (the whole point of the self-mod + mirror), no skipped final batch.
  Criterion 4F.4 ✓ (subject to the §12 oracle caveat, disproven live).

## 11. Regression suite (`check_raster_capture`, Mode C vs Mode B)

| # | fixture | replay | catchup | `[19656]` | service fail | sprite-start miss | vs Mode B |
|---|---|---|---|---|---|---|---|
| 1 | idle / player, 300 | 0 | 0 | yes | 0 | 0 | identical |
| 2/3 | authored wave (seed 382, ramps 5→6 enemies), 320 | 0 | 0 | yes | 0 | 0 | **better** (4E wave had 1 replay) |
| 7 | stage wrap (seed 12), 340 | 4 | 1 | yes | 0 | 0 | = 4E (≤ pre-4D baseline 8) |
| — | 199/235 scrolling (`--y199`), 400 | 10 | 0 | yes | 198 *(oracle, §12)* | 0 | new (was: no scroll) |
| 8 | `--dense` 16-obj synthetic stress, 200 | 99 *(--dense baseline)* | 1393 *(baseline)* | yes | 0 | **17** | Mode B baseline **3** |
| 9 | repeated A↔B flips | — | — | — | — | — | covered by wave/199/235 (33+ swaps, 1:1) |
| 10 | turret alive/destroyed around transitions | — | — | — | — | — | Stage 4E-proven; 4F does not touch the turret reconcile |

6-enemy + 2-bullet, 8-no-reuse and 9-reuse cases (items 3/4/5) are inside the
authored wave (`max_objects 9`, `max_batches 1`, real reuse batches + flips) — 0
service failures, 0 sprite-start misses, 0 replay.

**Supported gameplay: no regression.** The only deltas are the `--dense` synthetic
stress (+14 sprite-start misses) and the 199/235 synthetic worst-case (~10 replays
/ 400) — §13.

## 12. The `check_raster_capture` "final sprite pointers" oracle limitation

`check_raster_capture.py` verifies `matrix[1016:1016+count] == expected pointers`,
where `matrix` is the `$0400` page dump so offset 1016 = `$07F8` — **page A's**
table, hard-coded. Under a live `$D018` flip the *active* table alternates to
`$2BF8` for a whole coarse cycle. On the `--y199` capture the failures are exactly
the page-B runs (frames 16–31, 48–51, …). Direct live measurement of the *active*
table (`s4f_ptr2.py`, §7) shows 200/200 correct. So the 198 hits are the oracle
inspecting the inactive page, not real corruption.

A proper oracle fix requires (a) `vice_scroll_test.py` to also `bsave` `$2BF8` and
`BG_ACTIVE_PAGE`, (b) `check_raster_capture.py` to select the table by
`BG_ACTIVE_PAGE`. That is a bounded tooling change, deferred; it is the same class
of oracle-vs-architecture gap that Stages 4D/4E already documented and handled by
teaching the oracle (`hudSlotReclaimed`) or annotating the caveat
(`check_scroll_edges` RSEL=1).

## 13. Why `--dense` / 199/235 cost more under 4F

In Stage 4E these scenes are **permanently reason-1-blocked** — no coarse admit,
no flip, and the incremental inactive-page builder builds once then idles forever
(`SS_BUILD_REDUNDANT_WORK 0`). With 4F they **scroll**, so the builder does a full
~16 000-cy incremental rebuild every coarse cycle, on frames that already carry 9
(199/235) or 16 (`--dense`) objects + a reuse batch. The `SS_SLICE_RASTER_CUTOFF`
guard keeps the build slices from being caught by the line-1 IRQ, but the added
per-cycle load pushes ~2.5 % of 199/235 frames and +14 `--dense` frames past the
frame-top deadline into the (correctly-serviced) replay path / a sprite-start
miss. `[19656]`, 0 catchups, 0 incomplete frames, 0 service failures, and 0
sprite-start misses on all *supported* workloads (§11). This is a load property of
un-freezing the scroll, not a defect in the flip or the batch service.

## 14. Page-role swap / builder validity

`SS_PAGE_SWAP_COUNT` tracks `SS_FLIP_ADMIT` 1:1 (34 vs 33 over the counted window,
one flip straddling the zero). `SS_BUILD_REDUNDANT_WORK == 0`,
`SS_BUILD_INVALIDATE_COUNT == 0`; the builder restarts once per admit for the
`(SCROLL_ROW-1)` target into the newly-inactive page. Criteria 9, 10 ✓. Wrap
(criterion 11): 4F does not touch the wrap arithmetic (Stage 4D byte-exact, 4E
flip verified `SCROLL_ROW 0 → 419`); the stage-wrap regression capture is clean.

## 15. Cadence / raster metrics (Mode C)

`frame_cycle_deltas == [19656]` — the only value — on every capture (idle 300,
wave 320, wrap 340, `--y199` 400, `--dense` 200). `RASTER_INCOMPLETE_FRAMES 0`,
`RASTER_BORDER_BAILS 0`, `RASTER_CATCHUPS 0` on supported gameplay and 199/235.
Replay: 0 (idle, wave), 4 (wrap, = baseline), 10/400 (199/235 synthetic), 99
(`--dense`, = baseline). Sprite-start misses: 0 (idle, wave, wrap, 199/235), 17
(`--dense`, baseline 3).

## 16. Confirmations

- **Reasons 2 and 3 retained** — unchanged code; `COARSE_DEFER_BEAM` /
  `COARSE_DEFER_CUTOFF` still increment under 4F (112 / 32 on the 199/235 run).
- **Legacy fallback retains reason 1** — the non-relaxed path is byte-for-byte the
  old gate; a reason-1-bypassed admit that then fails the tag defers rather than
  running the legacy in-window mutation with a pending batch (`SS_PLF_TAG_DEFER`).
- **Relaxation isolated** behind `OPT_SS_ALLOW_PENDING_LIVE_FLIP` (requires
  `OPT_SS_FLIP_COARSE`); Mode B unchanged from the tag.
- **Soft-edge masking untouched** — `SOFT_EDGE_MASK` off/unmodified; terrain
  aperture 55..246 unchanged; `check_scroll_edges_rsel1` clean under 4E and 4F
  (idle capture).
- **No BUILD/LIVE redesign, no JIT mux, no object-limit / HUD / collision /
  wave-editor / stage-package changes, no `$2000-$23FF` reclaim, no sprite-asset
  reorg, no new art.**

## 17. Remaining risks

1. **Oracle** (§12): `check_raster_capture` needs page-awareness + a `$2BF8`
   capture. Live proof (200/200) stands in for it meanwhile.
2. **Builder load on formerly-frozen scenes** (§13): `--dense` +14 sprite-start
   misses; 199/235 ~2.5 % replay. Bounded, correctly serviced, real gameplay
   unaffected. Mitigations if needed: a shorter `SS_SLICE_RASTER_CUTOFF`, or
   spreading the flip-frame builder restart over more frames, or a lighter
   incremental transform for the pending-LIVE case.
3. **Self-modified `ssBatchPtrStore`**: standard page-flip technique, patched from
   the main thread into a non-re-entrant IRQ before that frame's batches fire; no
   race path found, but it is the one self-modifying store in the engine.
4. **`SS_PAGE_SWAP_COUNT` vs `SS_FLIP_ADMIT` off-by-one** across a counter zero —
   cosmetic in the probe; the engine tracks them consistently frame-to-frame.
5. **`$9900` block** now `$9900–$9de1` (~500 B free to `$A000`).

## 18. Final repository state

```
$ git branch --show-current   experimental-border-hud
$ git rev-parse HEAD          931dca1e577a57146c9a8edd029dbb2efe2d4136   (unchanged; tag stable-double-buffered-scroller)
$ git status --short
 M src/main.asm
 M src/raster_scheduler.asm
 M tools/vice_scroll_test.py
?? docs/stage4f-pending-live-scroll-worklog.md
?? reports/stage4f-pending-live-scroll-proof.md
$ git diff --stat
 src/main.asm              | 166 ++++++++++++++++++++++++++++++++++++++++++++++-
 src/raster_scheduler.asm  |   7 ++
 tools/vice_scroll_test.py |  12 ++-
```

**No commit, no add/stage, no tag, no push, no pull, no reset, no stash, no branch
switch.** `build/shooter.prg` is Mode A (`f2abc225…`).

### Generated test artefacts (scratchpad / /tmp only)

`s4f_probe.py`, `s4f_single.py`, `s4f_ptr.py`, `s4f_ptr2.py`; A/B/C build trees
`/tmp/f? /tmp/g?`; `check_raster_capture` dirs `build/s4f-*`.

## 19. Answer to the decisive question

> **Can the double-buffered `$D018` scroller now progress through the
> previously-blocking pending-LIVE sprite-reuse condition without compromising
> raster service?**

**Yes.** The 199/235 fixture scrolls (33 coarse steps over 700 frames), every one
published as a page flip while the LIVE reuse batch is armed, and every batch is
serviced correctly — `RASTER_INCOMPLETE_FRAMES 0`, `sprite_start_miss_count 0`,
active-page pointer table correct 200/200, exact `[19656]`. Raster service is not
compromised.

**Is reason 1 architecturally obsolete for the prepared-page flip path?** **Yes,
in principle** — the flip is a `$D018` write plus a frame-top reconcile that
touches no sprite hardware and no batch chain, so a pending LIVE batch is
genuinely irrelevant to it. The AMBER is not about safety of the flip; it is about
(a) an oracle that still assumes a single fixed pointer table, and (b) the
incremental-builder load that reason 1 was implicitly gating now running on
scenes that were previously frozen. Neither breaks raster service.

## 20. Recommendation

**AMBER → proceed to a bounded Stage 4G cleanup, do not yet make the relaxation
the default:**

1. **Teach the oracle.** `vice_scroll_test.py`: `bsave $2BF8` + `BG_ACTIVE_PAGE`.
   `check_raster_capture.py`: pick the pointer table by `BG_ACTIVE_PAGE`. Re-run
   the `--y199` capture — expect `service_failure_count 0`.
2. **Bound the builder load on pending-LIVE scenes.** Measure a lower
   `SS_SLICE_RASTER_CUTOFF`, and/or defer the flip-frame builder restart by one
   frame, and/or a "pending-LIVE only" lighter incremental transform. Target:
   199/235 replay ≤ stage-wrap baseline and `--dense` sprite-start miss ≤ 3.
3. Once 1 + 2 are GREEN, keep the legacy reason-1 path as the compile-time
   fallback and consider making `OPT_SS_ALLOW_PENDING_LIVE_FLIP` imply-on with
   `OPT_SS_FLIP_COARSE`.
4. Reasons 2 and 3 remain out of scope — any future simplification needs its own
   independent proof (page flipping removes the `RASTER ≥ 160` dependency, which
   *suggests* reason 3's cutoff could relax for the flip path, but that is
   unproven).
