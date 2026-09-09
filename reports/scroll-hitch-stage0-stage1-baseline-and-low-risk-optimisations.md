# Scroll Hitch — Stage 0/1: Reproducible Baseline + Low-Risk CPU Wins

Task 11 follow-up to the Astra High architectural review
(`reports/astra-c64-engine-architecture-review.md`).
Branch `experimental-border-hud`. KickAssembler 5.25, VICE x64sc 3.10, PAL.

---

## 1. Verdict

**GREEN.**

All ten GREEN conditions are met:

| # | Condition | Result |
|---|---|---|
| 1 | Two coarse-deferral classes deterministically distinguished | ✅ reason 1 (pending-LIVE) vs reason 3 (CPU-late) separated by dedicated counters — Case B vs Phase 4 |
| 2 | 199/235 obstruction reproduced + documented, **not** fixed | ✅ 400/400 frames deferred, 0 admitted, 0 scroll progress, reason 1 only; left in place |
| 3 | Collision-confirmation spike reproduced / discrepancy explained | ✅ 974 clocks / **+823 clock (~13.1 line)** slip at 8 in-window objects — matches Astra's ~960 / ~821 / ~13 lines |
| 4 | No-reuse builder early exit — measured saving, identical render behaviour | ✅ **671–753 clocks** saved for SORTED_COUNT < 9; 9-object case correctly NOT shortcut; sort/snapshot output byte-identical |
| 5 | Unchanged turret-art publication eliminated — measured saving | ✅ **~433 clocks/frame**; 2499/2500 static-art re-copies removed; hit pulse / lifecycle unaffected |
| 6 | Exact `[19656]` | ✅ `frame_cycle_deltas: [19656]` for base, diag, o1, o2, all |
| 7 | Zero new sprite / HUD / border / scroll regressions | ✅ service failures 0, `RASTER_BORDER_BAILS` 0, `RASTER_INCOMPLETE_FRAMES` 0, terrain body temporally clean (0 diffs) |
| 8 | BUILD / LIVE architecturally intact | ✅ no plan-structure, batch-count, mask or slot-contract change |
| 9 | Coarse admission unchanged | ✅ same three gates, same order, same decisions; only `inc`-counters added on the request path (never in an IRQ) |
| 10 | Enough evidence to design the incoming-row-predecode task | ✅ Section 9 |

Both low-risk optimisations are proven safe and are shipped ON by default.
The structural 199/235 obstruction is reproduced and left unfixed, as required —
it is the baseline Stage 2 must clear.

---

## 2. Repository starting state

```
$ git branch --show-current
experimental-border-hud

$ git status --short
 M src/background_turrets.asm
 M src/main.asm
 M src/raster_scheduler.asm
?? reports/astra-c64-engine-architecture-review.md
?? reports/soft-edge-masking-and-astra-handoff-report.md

$ git log -5 --oneline
6a64130 Four top HUD sprites stable under managed mux load
bc9d275 Hard lock fixed, border sprite flicker remains
82c27c5 Top border sprites milestone 1
44e735c pre-architecture-teardown
d547c80 Establish RSEL1 border HUD experimental baseline

$ git diff --stat        (at task start)
 src/background_turrets.asm |   0
 src/main.asm               |   ~40 +-      (SOFT_EDGE_MASK, all guarded OFF)
 src/raster_scheduler.asm   |   80 +-       (SOFT_EDGE_MASK, all guarded OFF)
```

**Pre-existing uncommitted work (Task 10 — AMBER, preserved untouched):**
the `#define SOFT_EDGE_MASK` top/bottom ECM soft-edge-mask experiment in
`src/main.asm` (the `GAMEPLAY_D011_BASE` ECM variant, the `endGame` ECM restore,
the `initBackground` `!zeroEcmGlyphs` block) and **all** of the
`src/raster_scheduler.asm` diff (`softEdgeBodyRestore` / `softEdgeBandEnter`
blocks + the `borderOpenHook` `jmp`-routed guard). `SOFT_EDGE_MASK` is
**not `#define`d** — every one of those blocks compiles out. Report
`reports/soft-edge-masking-and-astra-handoff-report.md` is that task's
deliverable. None of it was modified, re-enabled, or removed in Task 11.

`reports/astra-c64-engine-architecture-review.md` is the review this task
follows.

---

## 3. Astra findings verified against source

| Astra claim | Source location | Verified |
|---|---|---|
| PAL frame = 19,656 cycles, hardware-fixed | — | ✅ `frame_cycle_deltas: [19656]` every build |
| `swapRenderPlans` ≈ 29 clocks, index exchange only | `main.asm:3625` | ✅ 6 instructions, `pha`/`pla`, no bulk copy |
| Coarse admission: defer if LIVE batch outstanding **OR** beam ≥ 256 **OR** raster ≥ `BG_COARSE_LATEST_START` (184) | `main.asm:5834-5865` (`prepareBackgroundCoarse`) | ✅ three gates, exact order: `RASTER_BATCH_OFFSET < RASTER_BATCH_END`, `VIC_CONTROL_1 bmi`, `RASTER >= 184` |
| `!defer` re-arms `SCROLL_FRAME_COUNT = SCROLL_FRAME_DIVIDER-1` → retries every frame | `main.asm:5924` | ✅ `lda #SCROLL_FRAME_DIVIDER-1 / sta SCROLL_FRAME_COUNT`; `SCROLL_FRAME_DIVIDER = 2` (`generated/level1/stage_config.asm:22`) |
| No SEI around the coarse copies | `main.asm` `!waitRead`..`bgUpperReady` | ✅ no `sei`/`cli` in the window |
| Single legacy counter `BG_COARSE_DEFERRED` (no reason classification) | `main.asm:6158` | ✅ one `.byte`; Task 11 adds the classification |
| 199/235 structural obstruction: 8 initial at Y=199 release slot at Y+24=223; player deadline 235−12=223; no earlier legal compare → one reuse batch stays LIVE to ~223 every frame | `main.asm` `buildBatchSpriteSchedule` `!initSlots` (`SLOT_FREE_RASTER = OBJECT_Y[sorted]+24`), `applyLiveRasterBatch` compare | ✅ reproduced — Section 4, Case B: 400/400 deferrals, reason 1 only |
| Collision-confirmation slip: `capturePlayerCollision` → first initial assignment ≈ 139 clocks healthy vs ≈ 960 pressured (≈ 821 clocks / ≈ 13 PAL lines) | `main.asm:3757` `capturePlayerCollision`, `main.asm:3708` `rasterInitialApplied` | ✅ measured 151 healthy / 974 at 8 in-window enemies / **+823 (13.1 lines)** — Section 4, Case C |
| `buildBatchSpriteSchedule` no-reuse early-exit worth ~650–750 clocks (dead `beginRasterPlanMasks` + slot init + HUD floor before the existing `SORTED_COUNT < 9 → rts`) | `main.asm:3061` | ✅ measured 671 / 720 / 753 clocks (SC 6 / 7 / 8) — Section 6 |
| `publishTurretGlyphs` unconditional 32-byte copy ≈ 449 clocks in the copy (≈ 558 whole routine with 8 empty slots) | `background_turrets.asm:481` | ✅ 558 whole routine / 125 with the copy gated → **433 clocks** removed — Section 7 |
| Incoming-row predecode ≈ 1,700 clocks moveable out of the raster-160→184 upper window | `main.asm:5555` `renderStageRowToScreen` → `decodeStageCharacterRow` + `copyIncomingRowToScreen` + `installTurretRow` | Not measured this task (predecode explicitly out of scope); infrastructure inspected — Section 9 |

One refinement to Astra's numbers: the collision spike is **linear in the
number of objects that survive the broad-phase filters**, at ≈ 69 clocks each.
Astra's "~821" corresponds to ≈ 8 such objects; the absolute 15-slot maximum is
**+1,306 clocks (~20.7 lines)** (Section 4, Case C).

---

## 4. Stage 0 diagnostics

### 4.1 Instrumentation added (`#if SCROLL_HITCH_DIAG`, default ON)

`prepareBackgroundCoarse` keeps its three gates, their order, and every
decision. Each **failing** gate now first bumps a reason-specific counter and
sets `COARSE_LAST_REASON`, then joins the unchanged `!defer` path. On admission
`bgUpperReady` bumps `COARSE_ADMIT` and clears the run counter. `!defer` also
advances `COARSE_HOLD_RUN` and, on a new maximum, latches
`COARSE_HOLD_MAX` / `COARSE_HOLD_MAX_REASON`.

New state (`main.asm`, after `BG_COARSE_DEFERRED`):

| symbol | width | meaning |
|---|---|---|
| `COARSE_DEFER_LIVE` | word | reason 1 — a LIVE sprite batch is still outstanding (`RASTER_BATCH_OFFSET < RASTER_BATCH_END`) |
| `COARSE_DEFER_BEAM` | word | reason 2 — `VIC_CONTROL_1` bit 7 set (beam ≥ 256) at the admission attempt |
| `COARSE_DEFER_CUTOFF` | word | reason 3 — `RASTER >= BG_COARSE_LATEST_START` (CPU-late) |
| `COARSE_ADMIT` | word | coarse 7→0 transitions actually admitted |
| `COARSE_HOLD_RUN` | byte | current consecutive-deferral run (0 while scrolling normally) |
| `COARSE_HOLD_MAX` | byte | longest consecutive-deferral run this game (saturates at 255) |
| `COARSE_HOLD_MAX_REASON` | byte | reason code of the frame that set `COARSE_HOLD_MAX` |
| `COARSE_LAST_REASON` | byte | reason code of the most recent deferral |

All cleared per game in `initBackground`. `BG_COARSE_DEFERRED` (the legacy
single counter) is unchanged.

### 4.2 Proof the instrumentation changes nothing

* **Byte-identical baseline** — with `SCROLL_HITCH_DIAG`, `OPT_NOREUSE_BATCH_EXIT`
  and `OPT_TURRET_GLYPH_DIRTY` all commented out the PRG SHA-256 is
  `1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd`
  — identical to the Astra review baseline.
* **Cadence** — `diag` build (only `SCROLL_HITCH_DIAG` on):
  `check_raster_capture` → `frame_cycle_deltas: [19656]`, `service_failure_count: 0`.
* **Cost** — the added code is `inc abs` (+ carry) only, on the coarse-**request**
  path, which runs at most once every `SCROLL_FRAME_DIVIDER = 2` frames and is
  never inside a raster IRQ. Worst case ~25 cycles on a deferral frame, ~15 on
  an admission frame. Bounded, and outside every deadline window.
* **Decision equivalence** — the `#else` (OPT-off) arm of
  `prepareBackgroundCoarse` is the verbatim original
  `beq / bcc !defer / bmi !defer / bcs !defer` sequence. The `#if` arm reaches
  `!waitRead` / `!defer` on exactly the same conditions (it only needed the
  early-`rts` form for the `BG_COARSE_PENDING == 0` case because the added bytes
  pushed the original `beq !done+` past 8-bit branch range).

### 4.3 Case A — deterministic 6 enemies + 2 enemy bullets + player, scroll running

Fixture: object 0 = player (`TYPE_PLAYER`) at Y=120; objects 1–6 = enemies
(`TYPE_ENEMY`) at Y = 60/84/150/168/188/205; objects 7–8 = enemy bullets
(`TYPE_ENEMY_BULLET`) at Y = 96/132. Spawner frozen, layout re-posed every
frame, coarse scroll left running. `all` build. Per-frame anchor =
`updateObjects` (once/frame). 400 measured frames.

| quantity | value |
|---|---|
| `SORTED_COUNT` / `RENDER_COUNT` | 9 / 8 |
| `COARSE_DEFER_LIVE` Δ | **400** |
| `COARSE_DEFER_BEAM` / `COARSE_DEFER_CUTOFF` / `COARSE_ADMIT` Δ | 0 / 0 / **0** |
| `COARSE_HOLD_MAX` / reason | 255 (saturated; true run ≥ 400) / **1** |
| `SCROLL_ROW` Δ (progress) | **0** |
| `SCROLL_FINE` | pinned at 7 |
| `RASTER_CATCHUPS` / `REPLAY` / `INCOMPLETE` / `RASTER_BORDER_BAILS` Δ | 0 / 0 / 0 / 0 |

**The exact intermittent manual hitch is not deterministically reproducible from
a frozen fixture** — it is a real-play phenomenon driven by collision load and
CIA-derived encounter timing. What *is* deterministic: with **9 rendered
objects there is always one HW-sprite reuse batch**, and whenever any sorted
object sits low enough that its slot-release raster (`OBJECT_Y + 24`) lands past
the point `prepareBackgroundCoarse` runs (≈ raster 150), that batch is still
LIVE at the gate and coarse defers with reason 1 — every frame, forever. The
Y=205 enemy in this Case-A layout (release raster 229) is enough to hold it.
Remove the low objects (all non-player objects at Y ≤ ~150) and the same
9-object + 2-bullet load scrolls normally (see Case A-healthy / Phase 1 below).
So Case A resolves to one of two deterministic terminal states — **structural
hold** or **healthy progress** — selected by the lowest sorted Y, not by chance.

**Case A-healthy / Phase 1** (natural light play, no pose, `all` build, 500
frames): `COARSE_ADMIT` Δ **31** (one coarse request per 16 frames, all
admitted), every `COARSE_DEFER_*` Δ **0**, `SCROLL_ROW` Δ **−31** (31 rows
scrolled), no catchup / replay / incomplete / border bail.
`check_raster_capture` on the same build reports `max_objects: 9` — 9-object
frames scroll fine when their batches release early.

### 4.4 Case B — Astra's 199/235 layout

Fixture: object 0 = player at **Y=235**; objects 1–8 = enemies at **Y=199**.
Spawner frozen, re-posed every frame, coarse scroll running. `all` build.
400 measured frames.

| quantity | value |
|---|---|
| `SORTED_COUNT` / `RENDER_COUNT` | **9 / 8** → 8 initial HW sprites + **one LIVE reuse batch** (exactly Astra's scenario) |
| `COARSE_DEFER_LIVE` Δ | **400** |
| `COARSE_DEFER_BEAM` Δ | **0** |
| `COARSE_DEFER_CUTOFF` Δ | **0** |
| `COARSE_ADMIT` Δ | **0** |
| `COARSE_HOLD_MAX` / reason | 255 (saturated; true run = 400) / **1 = pending-LIVE** |
| `COARSE_LAST_REASON` | 1 |
| `SCROLL_ROW` Δ (progress) | **0** — zero rows in 400 frames |
| `SCROLL_FINE` | **0 → 7, then pinned at 7** |
| `RASTER_CATCHUPS` / `REPLAY` / `INCOMPLETE` Δ | 0 / 0 / 0 |
| `RASTER_BORDER_BAILS` Δ | **0** |
| `frame_cycle_deltas` (trace tool, same layout) | `[19656]` |

**Interpretation — matches Astra exactly:**

* The one reuse batch places the 9th sorted object (player, Y=235) into a
  recycled HW slot. `buildBatchSpriteSchedule`'s `!initSlots` sets every
  `SLOT_FREE_RASTER[y] = OBJECT_Y[sorted[y]] + 24 = 199 + 24 = 223`. The
  player's LIVE compare therefore cannot be scheduled earlier than raster 223
  (its own body deadline is `235 − 12 = 223` — there is no earlier legal
  compare). The batch stays LIVE (`RASTER_BATCH_OFFSET < RASTER_BATCH_END`)
  until ~223 every frame.
* `prepareBackgroundCoarse` runs at ≈ raster 150 — **well before** the beam gate
  (256) and **well before** the raster-184 cutoff. `COARSE_DEFER_BEAM` and
  `COARSE_DEFER_CUTOFF` stay at **0** for all 400 frames: gates 2 and 3 are
  never even reached. Gate 1 (LIVE outstanding) fires every single time.
* `!defer` re-arms `SCROLL_FRAME_COUNT = 1`, so the next frame requests coarse
  again → **400 consecutive deferrals** (Astra saw 143; a frozen fixture just
  never breaks the cycle). Fine scroll is pinned at 7; **the screen makes zero
  scroll progress** while sprite service, PAL cadence, the top-border HUD and
  the border stay perfectly stable.

This is the structural pending-LIVE obstruction, reproduced and left in place.
It is **not** a CPU-deadline problem — the CPU arrives early every time.

### 4.5 Deterministic CPU-late deferral (reason 3) — distinguishing the second class

To prove the counters separate the *other* class, a ~5,120-cycle delay was
injected at the `jsr prepareBackgroundCoarse` call site (only on frames with a
pending coarse request; removed afterwards), with **no object pose** (light
play, where Case A-healthy shows coarse always admits). `all` build, 500
anchor frames.

| quantity | value |
|---|---|
| `COARSE_DEFER_CUTOFF` Δ (reason 3) | **269** |
| `COARSE_DEFER_BEAM` Δ (reason 2) | **101** |
| `COARSE_DEFER_LIVE` Δ (reason 1) | 130 |
| `COARSE_ADMIT` Δ | 0 |
| `COARSE_HOLD_MAX_REASON` / `COARSE_LAST_REASON` | **3 / 3** |
| `RASTER_REPLAY_FRAMES` Δ | 131 (the injected burn genuinely overloads the frame) |
| `RASTER_INCOMPLETE_FRAMES` / `RASTER_BORDER_BAILS` Δ | **0 / 0** (no border/HUD damage even under artificial overload) |
| after injection removed (150 frames) | `COARSE_ADMIT` Δ **10**, every `COARSE_DEFER_*` Δ **0**, `SCROLL_ROW` Δ **−10** — full recovery, no lingering state |

**Case B (reason 1, CPU early, LIVE blocks) and this injection (reason 3, CPU
late, LIVE clear) are now deterministically distinguished by the counters.**

### 4.6 Case C — collision-confirmation A/B

`capturePlayerCollision` (`main.asm:3757`) structure:

1. `lda VIC_SPRITE_COLLISION` — always reads/clears `$D01E`.
2. `PLAYER_STATE != 0` → `rts` (dead/dying).
3. `and PLAYER_HW_MASK`:
   * **result 0 → `rts`. Broad-phase-NEGATIVE.** The hardware sprite-sprite
     latch does not contain the player's slot bit this frame → no scan at all.
   * **non-zero → `!playerCollision`. Broad-phase-POSITIVE.** Scan logical slots
     1..`MAX_OBJECTS-1`; per slot: `OBJECT_ACTIVE`, then `OBJECT_Y` in
     `[GAMEPLAY_SPRITE_MIN_Y (55), GAMEPLAY_SPRITE_END_Y (246))`, then
     `OBJECT_TYPE` (`TYPE_ENEMY` / `TYPE_ENEMY_BULLET`), then
     `OBJECT_DEATH_TIMER`, then `checkEnemyPlayerOverlap` /
     `checkBulletPlayerOverlap` (full 9-bit signed X delta with MSB, then a
     vertical box test). First `bcs` → `!hit`, latch `PLAYER_HIT`, `rts`.

Isolated CPU-clock probe (`all` build; boot to PLAYING, freeze, `DEN=0`,
`$D01A=0`; `JSR` in isolation with an RTS sentinel; STOPWATCH delta; min of 5):

| case | clocks | ~PAL lines |
|---|---:|---:|
| **A** — broad-phase-negative, whole `capturePlayerCollision` | **23** | 0.4 |
| scan, 15 inactive slots (bail at `OBJECT_ACTIVE`) | 276 | 4.4 |
| scan, 15 active, Y=10 outside the window (bail at Y filter) | 396 | 6.3 |
| **B2** — scan, 15 active enemies in-window, none overlapping (full `checkEnemyPlayerOverlap` ×15) | **1,311** | 20.8 |
| scan, 15 active bullets in-window (full `checkBulletPlayerOverlap` ×15) | 1,281 | 20.3 |
| **B3** — scan, confirmed hit on slot 1 (`!hit` early-out) | **106** | 1.7 |

Per fully-scanned in-window enemy ≈ **69 clocks**. The `OBJECT_ACTIVE` and
Y-window filters are cheap (~18 clocks/slot) and already exclude
culled/off-screen objects; `OBJECT_DEATH_TIMER` already excludes explosion
sprites; `OBJECT_TYPE` already excludes non-collidable objects. The cost is
dominated by the per-surviving-slot overlap arithmetic.

**Astra checkpoint** — `renderSprites` entry → first `rasterInitialApplied`
(`renderSprites` begins with `jsr capturePlayerCollision`; the positive path was
forced by patching `and PLAYER_HW_MASK` → `lda #$ff` for the measurement only):

| in-window enemies | clocks | ~lines | slip vs negative |
|---:|---:|---:|---:|
| negative (baseline) | **151** | 2.4 | — |
| 2 | 560 | 8.9 | +409 (~6.5 lines) |
| 4 | 698 | 11.1 | +547 (~8.7 lines) |
| 6 | 836 | 13.3 | +685 (~10.9 lines) |
| **8** | **974** | **15.5** | **+823 (~13.1 lines)** |
| 12 | 1,250 | 19.8 | +1,099 (~17.4 lines) |
| 15 | 1,457 | 23.1 | +1,306 (~20.7 lines) |

Astra: ≈ 139 healthy, ≈ 960 pressured, ≈ 821 clock / ≈ 13 line slip. **The
8-object row reproduces this within measurement noise.** The spike is real,
linear in surviving-slot count, and — when it lands on a frame whose coarse
request would otherwise have been admitted — pushes the CPU past the raster-184
cutoff (reason 3), which is the CPU-deadline hitch mechanism.

---

## 5. Baseline timing tables

Isolated CPU-clock probe (Astra method: freeze at a frame boundary, `DEN=0`,
raster IRQ off, poke object arrays, run
`buildSortedObjectList`/`sortObjectsByY`/`buildInitialSpriteSnapshot` to make
`SORTED_*`/`RENDER_COUNT` consistent, then `JSR` the routine in isolation with
an RTS sentinel; STOPWATCH delta; min of 3). `base` build =
`1fadf2b4…` = Astra baseline.

### 5.1 `buildBatchSpriteSchedule` (base)

| scenario | object Ys | SORTED_COUNT | clocks |
|---|---|---:|---:|
| 5 enemies + player | 70,90,110,130,150,180 | 6 | **696** |
| 6 enemies + player | 70,90,110,130,150,170,190 | 7 | **745** |
| 8 rendered / no reuse | 190..196, 235 | 8 | **778** |
| 6 enemies + 2 bullets + player | 60..200, 120 | 9 | **1,472** |
| 9 objects / one reuse | 188..195, 235 | 9 | **1,490** |
| 12 objects | 60..192 step 12 | 12 | **3,164** |
| 16 objects dense | 60..188 step 8 | 16 | **5,498** |

### 5.2 `publishTurretGlyphs` (base)

**558 clocks in every scenario** — it is layout-independent: an unconditional
32-byte charset copy (~449 clocks) + `inc TURRET_GLYPH_PUBLICATIONS` + the
`TURRET_POOL`-slot dead-cell scan.

### 5.3 `capturePlayerCollision` / `renderSprites` — Section 4.6.

### 5.4 Cadence (all builds, `check_raster_capture`, 600–700 frames)

| build | `frame_cycle_deltas` | service failures | sprite-start misses |
|---|---|---:|---:|
| base `1fadf2b4` | `[19656]` | 0 | 0–1¹ |
| diag `0c7199c4` | `[19656]` | 0 | 0–1¹ |
| o1 `7daad8ca` | `[19656]` | 0 | 0 |
| o2 `fc8bbd46` | `[19656]` | 0 | 0 |
| all `681935dc` | `[19656]` | 0 | 0 |

¹ An occasional single `sprite_start_miss` appears in **base** as well; it is
CIA-derived encounter-timing jitter between otherwise-equivalent runs (see the
A/B methodology note), not a regression.

---

## 6. Optimisation 1 — `buildBatchSpriteSchedule` no-reuse early exit

### 6.1 Change (`#if OPT_NOREUSE_BATCH_EXIT`, `main.asm:3095`)

```asm
buildBatchSpriteSchedule:
#if OPT_NOREUSE_BATCH_EXIT
    lda SORTED_COUNT
    cmp #9
    bcs !hasReuse+
    ldy BUILD_PLAN
    lda #0
    sta BATCH_COUNT,y          // only downstream contract for SC < 9
    rts
!hasReuse:
#endif
    jsr beginRasterPlanMasks
    ...
```

Placed **before** `jsr beginRasterPlanMasks`, so when `SORTED_COUNT < 9` it
also skips `beginRasterPlanMasks`, the 8-entry `!initSlots`
`SLOT_FREE_RASTER` fill, and the `#if HUD_PROOF_ENABLE` `!hudFloor` loop — all
of which the pre-existing `SORTED_COUNT < 9 → rts` (further down) already
proved to be dead work on sub-9 frames.

### 6.2 Why it is safe — what later code expects when `SORTED_COUNT < 9`

* **BUILD batch count** — the only state `applyLiveRasterBatch` and
  `swapRenderPlans` consume from BUILD on a sub-9 frame. Explicitly zeroed
  (`BATCH_COUNT[BUILD_PLAN] = 0`), identical to the original's
  `lda #0 / sta BATCH_COUNT,y` at the top of the batch path.
* **`SLOT_FREE_RASTER` (`$222a`)** — read only by `buildBatchSpriteSchedule`
  itself (`!hudFloor`, `!findSlot`). It is pure batch-path scratch, fully
  repopulated by `!initSlots` at the top of every `SORTED_COUNT ≥ 9` frame. No
  reader survives a sub-9 frame.
* **`SCHED_PLAYER_MASK` / `SCHED_X_MSB_MASK` / `BATCH_PLAYER_MASK[16]` /
  `BATCH_X_MSB_MASK[16]`** — `beginRasterPlanMasks` fully re-initialises the
  `SCHED_*` pair to 0 and rebuilds from INITIAL sprites at the top of the batch
  path; the `BATCH_*` arrays are written per completed batch and read by
  `applyLiveRasterBatch` only at `RASTER_BATCH_OFFSET ∈ [LIVE_PLAN ..
  LIVE_PLAN + BATCH_COUNT)`. With `BATCH_COUNT = 0` that range is empty. Pure
  batch-path scratch; no stale read.
* **HUD slot floors / ownership** — the `!hudFloor` loop only floors
  `SLOT_FREE_RASTER[4..7]` at `HUD_HANDOFF_COMPLETE_RASTER`; since
  `SLOT_FREE_RASTER` is not read on a sub-9 frame, skipping it is inert. Time-
  domain HUD ownership is enforced by `renderSprites`' `HUD_SLOT_FIRST` cap and
  `hudBorderHandoff`, neither of which this routine touches.
* **Initial snapshot** — `buildInitialSpriteSnapshot` runs *before*
  `buildBatchSpriteSchedule` and is untouched; all 8 post-HUD HW sprites remain
  available.
* **No object drop** — objects 9+ only ever reach hardware *through* a reuse
  batch; with `SORTED_COUNT < 9` there is no 9th object, so there is nothing to
  drop.
* **No collision-semantic change** — this routine does no collision work.

### 6.3 Measured (probe: base vs o1)

| scenario | SORTED_COUNT | base | o1 | saving |
|---|---:|---:|---:|---:|
| 5 enemies + player | 6 | 696 | **25** | **671** |
| 6 enemies + player | 7 | 745 | **25** | **720** |
| 8 rendered / no reuse | 8 | 778 | **25** | **753** |
| 6 enemies + 2 bullets + player | 9 | 1,472 | 1,474 | 0 (correctly **not** shortcut) |
| 9 objects / one reuse | 9 | 1,490 | 1,492 | 0 (correctly **not** shortcut) |
| 12 objects | 12 | 3,164 | 3,166 | 0 |
| 16 objects dense | 16 | 5,498 | 5,500 | 0 |

**671–753 clocks saved on every frame with ≤ 8 rendered objects** — the common
case. Frames with ≥ 9 sorted objects take the full path unchanged (the extra
~2 clocks is the `lda SORTED_COUNT / cmp #9 / bcs` that now precedes it).
`SORTED_COUNT` and `RENDER_COUNT` are byte-identical between base and o1 for
every scenario — render behaviour is unchanged.

### 6.4 Effect on the deadline

`buildBatchSpriteSchedule` is called at `main.asm:726`, in the second
sort/build pass, immediately before `prepareBackgroundCoarse` (`:739`). On a
≤ 8-object frame the CPU now reaches the coarse gate **671–753 clocks (≈ 11–12
PAL lines) earlier**. This does **not**, on its own, rescue a Case-B frame
(reason 1 is structural, not CPU-timing) but it widens the margin against
reason 3 on frames that also carry a collision-confirmation scan or other
transient load.

---

## 7. Optimisation 2 — turret static-glyph publication only when dirty

### 7.1 Change (`#if OPT_TURRET_GLYPH_DIRTY`)

* New flag `TURRET_GLYPH_DIRTY` (`background_turrets.asm:842`, inside
  `TURRET_SCRATCH_BEGIN..END`, cleared by `initBackgroundTurrets`).
* `setupStarfieldCharset` (`main.asm:1490`) sets it after the char-ROM copy —
  that copy overwrites glyph codes 226..229.
* `initBackgroundTurrets` (`background_turrets.asm:113`) sets it before its
  `jsr publishTurretGlyphs` — a fresh game re-publishes once.
* `publishTurretGlyphs` (`background_turrets.asm:481`) gates **only** the
  `ldx #31 … !copy` charset write and the `inc TURRET_GLYPH_PUBLICATIONS` on
  `TURRET_GLYPH_DIRTY != 0`, clears the flag after the copy, and falls through
  to `!glyphsClean`. **The per-frame `TURRET_POOL`-slot dead-cell scan below
  `!glyphsClean` still runs every frame, unchanged.**

### 7.2 Ownership / lifecycle — why the copy is safe to skip

* **Source** `turretArt + TURRET_STATIC_STYLE*32` is an assembled constant.
* **Destination** `STAR_CHARSET + TURRET_GLYPH_BASE*8` (`$3F10`, codes 226..229)
  is written **only** by `publishTurretGlyphs`. It is clobbered exactly once, by
  `setupStarfieldCharset` (the `$D000-$D7FF` ROM copy) — which now sets the flag.
* **Hit pulse** is colour-RAM only (`pulseTurretColour`) — never touches the
  charset.
* **Death / dead-cell terrain restoration** pokes *screen* RAM
  (`restoreDeadTurretCells` / the `!deadScan` loop), not the glyph bitmaps —
  and that loop still runs every frame.
* **Respawn / restart / level transition** all pass through
  `initBackground → initBackgroundTurrets`, which sets the flag.
* **`endGame`** (menu / GAME OVER) — when `SOFT_EDGE_MASK` is on it calls
  `setupStarfieldCharset` (which sets the flag); with the mask off (shipping)
  `endGame` does not disturb `$3F10`, and the next `initBackground` re-publishes
  anyway.

### 7.3 Measured

**Isolated probe (base vs o2):** `publishTurretGlyphs` **558 → 125 clocks**,
every scenario → **433 clocks/frame saved** (matches Astra's ~449 in the copy).

**Long natural run (2,500 frames, `all` vs `base`):**

| | base | all |
|---|---:|---:|
| `TURRET_GLYPH_PUBLICATIONS` increments over the run | ~2,500 (every frame) | **0** |
| `TURRET_GLYPH_DIRTY` after settle | — | **0** (latched clean) |
| publications across a forced turret hit | +120 over 120 frames (still every frame) | **0** (hit does not re-publish) |
| `RASTER_BORDER_BAILS` / `RASTER_INCOMPLETE_FRAMES` / `RASTER_BORDER_SKIPS` | 0 / 0 / 0 | 0 / 0 / 0 |

After the one post-init publish the static body art is resident and never
re-copied. Turret visuals, the hit pulse and the full respawn/destruction
lifecycle are unaffected.

### 7.4 Effect on the deadline

`publishTurretGlyphs` is called from `gameLoop` (`main.asm:664`, `:718`) every
frame, in the early-frame window before the coarse work. Removing it returns
**~433 clocks (≈ 6.9 PAL lines) to every frame** — an unconditional early-frame
saving, independent of object count, that widens the margin against reason-3
deferrals on **all** frames (it does nothing for reason 1).

---

## 8. Collision-confirmation investigation (investigate only — no rewrite)

Collision semantics are **unchanged**. Findings, per the task's questions:

* **How often does a positive broad-phase scan occur in real play?** Rarely.
  `capturePlayerCollision` only scans when the **hardware** sprite-sprite latch
  (`$D01E`) contains the player's current HW-slot bit. That requires two sprite
  DMAs to physically overlap on a scanline with the player as one of them —
  which happens on contact frames and near-misses, not routinely. In the
  natural-play captures the scan is not entered on the large majority of frames
  (broad-phase-negative = 23 clocks).
* **How many logical slots are examined?** Up to `MAX_OBJECTS − 1` (15). The
  loop has no early termination other than a confirmed `!hit`.
* **Which filters dominate?** Not the filters — the surviving-slot arithmetic.
  `OBJECT_ACTIVE` bail ≈ 18 clocks/slot; +Y-window bail ≈ 8 more; a full
  `checkEnemyPlayerOverlap` with no hit ≈ **69 clocks/slot**. 0 → 276, all-15
  in-window → 1,311.
* **Can stale / dead / off-screen / non-collidable objects be excluded
  earlier?** They already are: `OBJECT_ACTIVE` (stale), `OBJECT_DEATH_TIMER`
  (explosion sprites), `OBJECT_Y` window 55..246 (culled ingress / off-screen),
  `OBJECT_TYPE` (only `TYPE_ENEMY` / `TYPE_ENEMY_BULLET`). The remaining cost is
  genuine candidates.
* **Could rendering / sorting info narrow the scan?** Potentially. The scan
  walks *logical* slots; the sorted list (`SORTED_*`) and the initial snapshot
  already know which objects are on-screen and their Y order. A confirmation
  pass driven by the sorted on-screen set — or bounded to the sorted Y-band
  around the player — would examine only the handful of objects that can
  actually overlap. This is a **candidate for Stage 2+**, not this task.
* **Does moving / deferring confirmation change logical-state sampling?** Yes,
  and Astra's warning holds: `capturePlayerCollision` consumes the hardware
  ownership latched during *the previous raster interval* and resolves it
  against *current* `OBJECT_*`. If confirmation is delayed past subsequent
  `updateObjects` / spawn / free calls, objects may have moved or slots been
  reallocated, so the latched hardware mask no longer corresponds to the same
  logical objects — a false negative or a mis-attributed hit. Any relocation of
  this work must keep the confirmation in the same frame phase, between the
  hardware-ownership interval and the next `updateObjects`.

**Recommendation:** do **not** rewrite the scan for Stage 1. It is already
well-filtered; its worst case is bounded (~1,311 clocks) and only bites on the
rare positive-broad-phase frame. If Stage 2's predecode does not by itself
remove the reason-3 hitch on collision frames, the next cheapest move is to
drive confirmation from the sorted on-screen set (≈ 3–6 slots instead of 15),
staying in the current frame phase.

---

## 9. Incoming-row predecode preparation (document only — not implemented)

The Stage 2 target is `renderStageRowToScreen` (`main.asm:5555`), called from
`prepareBackgroundCoarse` **inside the raster-160 → 184 upper window**:

```
renderStageRowToScreen:
    ... compute BG_LOGICAL_ROW(16) = SCROLL_ROW(16) + BG_DEST_ROW - 1
    jsr wrapBgLogicalRow          // 16-bit mod STAGE_LOGICAL_ROWS
    jsr decodeStageCharacterRow   // metatile lookup + expand -> BG_INCOMING_ROW[40]
    jsr copyIncomingRowToScreen   // BG_INCOMING_ROW -> screen row BG_DEST_ROW
    jmp installTurretRow          // overlay any turret world-characters on that row
```

`decodeStageCharacterRow` + `copyIncomingRowToScreen` + `installTurretRow` are
the ≈ 1,700 clocks Astra wants moved out of the window: they depend only on
`SCROLL_ROW` (known one frame ahead — the next coarse step always reveals world
row `SCROLL_ROW − 1`) and the static level map, so they can run in the *previous*
frame into a staging buffer, leaving only a 40-byte buffer→screen copy in the
window.

### Lifetimes & invariants the predecode design must honour

| concern | current mechanism | predecode requirement |
|---|---|---|
| **Candidate staging buffer** | `BG_INCOMING_ROW[40]` (`main.asm`, near `BG_COARSE_PENDING`) is the live decode target; `BG_CROSSING_ROW[40]` (`main.asm:4490`) holds the one crossing row saved by `saveCrossingRow`. Both are 40-byte, in the `$29xx`/`$5axx` background area. | A **separate** `BG_PREDECODED_ROW[40]` (do **not** reuse `BG_INCOMING_ROW` — it is still the in-window decode target for the non-predecoded path and for `renderStageRowToScreen`'s other callers at `initBackground:5537`). ~40 bytes; the background segment at `$5a00` has room. |
| **Validity tag** | none — `BG_INCOMING_ROW` is always freshly decoded before use | 1-byte `BG_PREDECODE_VALID`. Set when the buffer is filled for a specific next-row; cleared by anything that can invalidate it (below). `prepareBackgroundCoarse` uses the buffer only if valid **and** its tagged row matches the row it is about to reveal; otherwise it falls back to the in-window `decodeStageCharacterRow`. |
| **World-origin / level identity** | `SCROLL_ROW(16)` + `stageMetatileRows` / `metatileDefs` (level-owned, imported once) | Tag the buffer with the 16-bit logical row it was decoded for (`BG_PREDECODE_ROW_LO/HI`). A single level is loaded (`generated/level1/`), so no level-id tag is needed *yet*; if multiload lands, add a level-generation byte. |
| **Stage-wrap handling** | `prepareBackgroundCoarse` wraps `SCROLL_ROW 0 → STAGE_LOGICAL_ROWS-1` and sets `TURRET_STREAM_REWIND` / `WAVE_TRIGGER_REWIND` | The predecode of "next row" must apply the **same** `wrapBgLogicalRow` reduction. If the predecode was computed before a wrap and the wrap then happens, the tagged row won't match → automatic fallback. Simplest correct rule: invalidate `BG_PREDECODE_VALID` in the wrap branch. |
| **Turret-overlay freshness** | `installTurretRow` overlays turret world-characters *after* the row hits the screen; the turret stream (`updateTurretStream`) admits/evicts pool slots each frame | The predecoded buffer must hold **terrain only**; `installTurretRow` (or an equivalent overlay) must still run in-window against the *current* turret pool state, because a turret can be admitted/evicted between the predecode frame and the reveal frame. Do not bake turret glyphs into the staging buffer. |
| **Scratch conflicts** | `decodeStageCharacterRow` clobbers `BG_INCOMING_ROW`, `TEXT_SRC`, `BG_ROW_IDS`, `BG_TILE_ROW_OFS`, `BG_METATILE_ROW(_HI)`, `BG_ROW_BASE(_HI)`, `BG_OUT_BASE`, `BG_LOGICAL_ROW(_HI)` | Running it a frame early means those scratch bytes are touched during normal frame code (currently they are only live during the coarse window). Audit that nothing else in the early-frame path reads them; if so, give the predecode pass its own scratch or save/restore. `BG_LOGICAL_ROW` in particular is an explicit entry param — the predecode pass sets it, and no other early-frame code may assume it survives. |
| **`SCROLL_FINE` / divider timing** | coarse is requested when `SCROLL_FINE` wraps 7→0 (`updateBackgroundScroll`); `SCROLL_FRAME_DIVIDER = 2` | The predecode should fire when `SCROLL_FINE` reaches ~6–7 (one step before the coarse request) so the buffer is ready when `prepareBackgroundCoarse` runs. If a coarse request is *deferred* (Case B), the predecoded row stays valid across the held frames — the revealed row does not change while fine is pinned at 7 — so the predecode is done once, not every held frame. |

### Expected saving

Astra's ≈ 1,700 clocks of `decodeStageCharacterRow` + `copyIncomingRowToScreen`
leave the raster-160→184 window; only a ~40-byte `BG_PREDECODED_ROW → screen`
copy (≈ 250–350 clocks) plus the unchanged `installTurretRow` remain. This
directly widens the upper window against **reason 3** (CPU-late). It does
**nothing for reason 1** — Case B still holds, because the blocker there is the
LIVE batch, not the copy budget.

---

## 10. Before / after comparison

| routine / path | base (clocks) | all (clocks) | delta | when it applies |
|---|---:|---:|---:|---|
| `buildBatchSpriteSchedule`, ≤ 8 rendered objects | 696–778 | 25 | **−671 … −753** | every frame with `SORTED_COUNT < 9` (the common case) |
| `buildBatchSpriteSchedule`, ≥ 9 rendered objects | 1,472–5,498 | +2 | +2 | frames with a reuse batch (incl. Case B / Case A-structural) |
| `publishTurretGlyphs` | 558 | 125 | **−433** | **every frame** |
| `capturePlayerCollision`, broad-phase-negative | 23 | 23 | 0 | most frames (unchanged) |
| `capturePlayerCollision`, broad-phase-positive | 276–1,457 | 276–1,457 | 0 | rare contact frames (unchanged — investigate only) |
| coarse-request instrumentation | 0 | +15 … +25 | +15 … +25 | ≤ once per 2 frames, never in an IRQ |

**Early-frame budget returned on a typical ≤ 8-object frame:** ~433 (turret) +
~671–753 (builder) ≈ **1,100–1,190 clocks (≈ 17–19 PAL lines)** before
`prepareBackgroundCoarse` runs.

**These savings are not additive across unrelated frames** and they do **not**
rescue the 199/235 obstruction — that is reason 1 (structural pending-LIVE),
which no amount of upstream CPU headroom addresses. They reduce the frequency of
**reason 3** (CPU-late) deferrals by widening the margin to the raster-184
cutoff on every frame, and by ~11–12 extra lines on frames that also carry a
collision-confirmation scan or other transient load.

---

## 11. Regression matrix (all three toggles ON, `all` build `681935dc`, vs baseline `1fadf2b4`)

| area | check | result |
|---|---|---|
| **Cadence** | `frame_cycle_deltas` (trace) | `[19656]` — base, diag, o1, o2, all |
| | all-toggles-OFF build SHA-256 | `1fadf2b42cc30b33…` — **byte-identical** to Astra baseline |
| | every individual toggle-off permutation | compiles |
| **Gameplay loads** | 5 en + player / 6 en + player / 8 rendered no-reuse | scroll normally; `SORTED_COUNT`/`RENDER_COUNT` identical base↔all |
| | 6 en + 2 bullets + player (SC 9) / 9 objects one-reuse | full batch path taken (early exit correctly not applied) |
| | 199 / 235 (8 en Y=199 + player Y=235) | **structural hold reproduced** — reason 1, 400/400 deferrals, 0 progress; cadence / HUD / border / sprite service all stable |
| **Scroll** | natural light play, 500 frames | 31 coarse steps, all admitted, `SCROLL_ROW` −31, 0 deferrals |
| | held-fine-7 max + reason | `COARSE_HOLD_MAX` 255 (saturated), `COARSE_HOLD_MAX_REASON` 1 in Case B; 0 in light play |
| | terrain body 55..246 temporal cleanliness (`check_scroll_edges_rsel1 --aperture 55 246`) | `body_temporal_diffs: 0`, `lastrow_temporal_diffs: 0` — base, diag, o2, all (controlled seed 40 / 600 frames) |
| **Sprites** | `service_failure_count` | 0 — every build |
| | `sprite_start_miss_count` | 0 (occasional 1 also present in base — encounter-timing jitter) |
| | 8 HW sprites after HUD handoff | unchanged — no batch/mask/slot contract touched |
| **HUD / border** | `RASTER_BORDER_BAILS` | 0 over 2,500 frames — base and all |
| | `RASTER_INCOMPLETE_FRAMES` / `RASTER_BORDER_SKIPS` | 0 / 0 — base and all |
| | whole-border flash / vanish / hard lock | none observed |
| **Collision** | broad-phase-negative / broad-phase-positive costs | unchanged (23 / 276–1,457) — semantics untouched |
| | confirmed-hit path (`!hit` early-out) | 106 clocks, unchanged |
| **Turrets** | `TURRET_GLYPH_PUBLICATIONS` over 2,500 frames | base ~2,500 → all **0** after the one post-init publish |
| | forced turret hit | pulse path runs; **no** static-art re-publication; `TURRET_GLYPH_DIRTY` stays 0 |
| | respawn / restart / level init | `initBackgroundTurrets` sets `TURRET_GLYPH_DIRTY` → one clean re-publish per game |
| **Terrain** | outer soft-edge pop | **not addressed** (out of scope); `SOFT_EDGE_MASK` stays OFF; no new shimmer/pop introduced |

No new regression in any row.

---

## 12. Remaining structural problem

The 199/235 obstruction is **unchanged and unfixable within Stage 1's remit**.
The mechanism, now instrumented and confirmed:

* 9 rendered objects ⇒ one HW-sprite reuse batch.
* Every initial slot at Y=199 releases at raster `199 + 24 = 223`; the player at
  Y=235 has body deadline `235 − 12 = 223`. There is no legal compare earlier
  than 223, so the reuse batch is LIVE until ~223 **every frame**.
* `prepareBackgroundCoarse` runs at ≈ raster 150 — before the beam gate and
  before the raster-184 cutoff — but gate 1 (`RASTER_BATCH_OFFSET <
  RASTER_BATCH_END`) is still true, so it defers with reason 1, re-arms, and
  repeats. `COARSE_DEFER_BEAM` and `COARSE_DEFER_CUTOFF` stay at 0: the CPU is
  never the problem here.

Neither Stage 1 optimisation touches this. More early-frame CPU headroom cannot
help — the coarse copy is blocked by a **hardware sprite fetch still in
progress**, not by a lack of cycles. The fix requires either a second character
matrix (so the upper rows can be prepared without disturbing the LIVE lower-half
fetch) or a fundamental change to how the reuse batch and the coarse copy share
the lower screen — both explicitly out of scope for this task and reserved for
the architectural rework.

---

## 13. Recommendation for Stage 2

**Proceed with incoming-row predecode**, with the following contract.

### Contract

1. Add `BG_PREDECODED_ROW[40]`, `BG_PREDECODE_VALID` (byte),
   `BG_PREDECODE_ROW_LO/HI` (the tagged 16-bit logical row) in the `$5a00`
   background segment. Do **not** reuse `BG_INCOMING_ROW` or `BG_CROSSING_ROW`.
2. A new `predecodeNextStageRow` runs in the early-frame path (triggered when
   `SCROLL_FINE ≥ 6`, i.e. one fine step before the coarse request): compute the
   next revealed logical row (`SCROLL_ROW − 1` folded by `wrapBgLogicalRow`),
   `decodeStageCharacterRow` into `BG_PREDECODED_ROW`, set `BG_PREDECODE_VALID`
   and the row tag. Terrain only — no turret overlay.
3. `prepareBackgroundCoarse`'s `renderStageRowToScreen` call uses
   `BG_PREDECODED_ROW` **iff** `BG_PREDECODE_VALID` is set and the tag matches
   the row being revealed; otherwise it falls back to the in-window
   `decodeStageCharacterRow` (bit-for-bit the current path). `installTurretRow`
   still runs in-window against the current turret pool.
4. Invalidate `BG_PREDECODE_VALID` in the stage-wrap branch (alongside
   `TURRET_STREAM_REWIND` / `WAVE_TRIGGER_REWIND`) and on any level (re)init.
5. `predecodeNextStageRow` must not clobber early-frame-live state — audit
   `TEXT_SRC`, `BG_ROW_IDS`, `BG_LOGICAL_ROW(_HI)`, `BG_METATILE_ROW(_HI)`,
   `BG_ROW_BASE(_HI)`, `BG_OUT_BASE`, `BG_TILE_ROW_OFS`; give the predecode pass
   private scratch if any of these is read elsewhere in that phase.

### Acceptance measurements

* Isolated CPU probe: `prepareBackgroundCoarse`'s raster-160→`bgUpperReady`
  span drops by ≈ 1,400–1,700 clocks on a predecode-hit frame; the in-window
  work is a 40-byte copy + `installTurretRow` only.
* `SCROLL_HITCH_DIAG`: with a moderate collision + object load that currently
  produces reason-3 deferrals, `COARSE_DEFER_CUTOFF` drops toward 0 while
  `COARSE_ADMIT` rises correspondingly.
* `COARSE_DEFER_LIVE` for the 199/235 layout is **unchanged** (predecode must
  not, and cannot, fix reason 1 — this is the control).
* `frame_cycle_deltas: [19656]` preserved; `check_scroll_edges_rsel1 --aperture
  55 246` still `body_temporal_diffs: 0`; `RASTER_BORDER_BAILS` still 0;
  turret overlay still correct on the revealed row across an admit **and**
  across a wrap.

### Where the evidence refines Astra

Astra frames predecode as *the* scroll-hitch fix. The Stage 0 data shows there
are **two** hitches and predecode only addresses one:

* **Reason 3 (CPU-late):** predecode is the right fix — it directly returns
  ≈ 1,700 clocks to the window.
* **Reason 1 (pending-LIVE / 199/235):** predecode does nothing. This needs the
  second-matrix / lower-screen rework. Stage 2 should ship predecode **and**
  keep the 199/235 case as a known, measured, still-failing baseline until the
  architectural rework lands.

---

## 14. Exact files changed

### Pre-existing before this task (Task 10 — SOFT_EDGE_MASK, AMBER, `#define` OFF, untouched)

* `src/raster_scheduler.asm` — **entire diff** (`+80`): `softEdgeBodyRestore` /
  `softEdgeBandEnter` blocks in `rasterDisplayHook` / `borderOpenHook`, plus the
  `borderOpenHook` `jmp`-routed window guard. All `#if SOFT_EDGE_MASK`.
* `src/main.asm` — the `SOFT_EDGE_MASK` comment block (~line 22), the
  `GAMEPLAY_D011_BASE` ECM `#if/#else` (~line 92), the `endGame` ECM restore
  (~line 779), the `initBackground` `!zeroEcmGlyphs` block (~line 5483). All
  `#if SOFT_EDGE_MASK`.
* `reports/soft-edge-masking-and-astra-handoff-report.md` — Task 10 deliverable.
* `reports/astra-c64-engine-architecture-review.md` — the review being followed.

### This task (Task 11)

* **`src/main.asm`**
  * toggle block (`main.asm:52-75`): comment + `#define SCROLL_HITCH_DIAG`,
    `#define OPT_NOREUSE_BATCH_EXIT`, `#define OPT_TURRET_GLYPH_DIRTY`.
  * `setupStarfieldCharset` (`:1490`): `#if OPT_TURRET_GLYPH_DIRTY` → set
    `TURRET_GLYPH_DIRTY` after the char-ROM copy.
  * `buildBatchSpriteSchedule` (`:3095`): `#if OPT_NOREUSE_BATCH_EXIT` early
    exit — `SORTED_COUNT < 9` ⇒ zero `BATCH_COUNT[BUILD_PLAN]`, `rts`.
  * `initBackground` (`:5418`): `#if SCROLL_HITCH_DIAG` — clear the eight new
    counters per game.
  * `prepareBackgroundCoarse` (`:5807`): `#if SCROLL_HITCH_DIAG` — reason-
    classifying gate (same three checks, same order, same decisions; each
    failing branch bumps its counter + `COARSE_LAST_REASON`); `#else` = verbatim
    original.
  * `bgUpperReady` (`:5898`): `#if SCROLL_HITCH_DIAG` — bump `COARSE_ADMIT`,
    clear `COARSE_HOLD_RUN`.
  * `!defer` (`:6160`): `#if SCROLL_HITCH_DIAG` — advance `COARSE_HOLD_RUN`,
    latch `COARSE_HOLD_MAX` / `COARSE_HOLD_MAX_REASON`.
  * counter storage (`:6160`, after `BG_COARSE_DEFERRED`): `#if
    SCROLL_HITCH_DIAG` — `COARSE_DEFER_LIVE/BEAM/CUTOFF` (`.word`),
    `COARSE_ADMIT` (`.word`), `COARSE_HOLD_RUN/MAX/MAX_REASON/LAST_REASON`
    (`.byte`).
* **`src/background_turrets.asm`**
  * `initBackgroundTurrets` (`:113`): `#if OPT_TURRET_GLYPH_DIRTY` → set
    `TURRET_GLYPH_DIRTY` before `jsr publishTurretGlyphs`.
  * `publishTurretGlyphs` (`:481`): `#if OPT_TURRET_GLYPH_DIRTY` → `beq
    !glyphsClean` on `TURRET_GLYPH_DIRTY == 0`; clear the flag after the copy;
    `!glyphsClean:` label before the (unchanged) per-frame dead-cell scan.
  * `TURRET_GLYPH_DIRTY: .byte 0` (`:842`, in `TURRET_SCRATCH_BEGIN..END`).

### Test / probe / report artefacts (not engine source)

* `reports/scroll-hitch-stage0-stage1-baseline-and-low-risk-optimisations.md` —
  this report.
* Scratchpad probes (not in the repo tree):
  `cpuprobe2.py` (isolated builder/turret CPU clocks),
  `stage0b.py` (Cases A/B + deterministic reason-3 injection + cadence),
  `casec.py` / `casec2.py` (collision-confirmation A/B),
  `turretreg.py` (turret-glyph + border-counter A/B).
* A/B build tree `/tmp/sh/{base,diag,o1,o2,all}/` — five toggle permutations.

No commits, no staging, no branch/tag/history changes.

---

## 15. Final repository state

```
$ git status --short
 M src/background_turrets.asm
 M src/main.asm
 M src/raster_scheduler.asm
?? reports/astra-c64-engine-architecture-review.md
?? reports/scroll-hitch-stage0-stage1-baseline-and-low-risk-optimisations.md
?? reports/soft-edge-masking-and-astra-handoff-report.md

$ git diff --stat
 src/background_turrets.asm |  22 +++++
 src/main.asm               | 215 +++++++++++++++++++++++++++++++++++++++++++-
 src/raster_scheduler.asm   |  80 ++++++++++++++++
 3 files changed, 314 insertions(+), 3 deletions(-)
```

* `src/raster_scheduler.asm` (`+80`) — **100 % pre-existing Task 10**
  (`SOFT_EDGE_MASK`, all guarded OFF). Not touched this task.
* `src/main.asm` (`+215 −3`) — mix: the `SOFT_EDGE_MASK` blocks (~40 lines) are
  pre-existing Task 10; the remainder (`SCROLL_HITCH_DIAG` /
  `OPT_NOREUSE_BATCH_EXIT` / `OPT_TURRET_GLYPH_DIRTY`) is this task, all behind
  those three guards.
* `src/background_turrets.asm` (`+22`) — **100 % this task**
  (`OPT_TURRET_GLYPH_DIRTY`).
* New untracked files: this report + the two carried-over reports.

**Git history was not altered** — no commit, add/stage, pull, push, tag, reset,
stash, or branch switch was performed. Working tree only.

Default build (`all`, three toggles ON): SHA-256
`681935dc5179f351…`.
All three toggles commented out: SHA-256
`1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd`
— byte-identical to the Astra review baseline.
