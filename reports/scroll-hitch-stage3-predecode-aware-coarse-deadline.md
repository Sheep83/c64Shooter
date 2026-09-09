# Scroll Hitch — Stage 3: Predecode-Aware Coarse Admission Deadline

Follow-up to the Astra review and the Stage 0/1 + Stage 2 reports. Branch
`experimental-border-hud`. KickAssembler 5.25, VICE x64sc 3.10, PAL.

---

## 1. Verdict

**GREEN.**

| # | Success criterion | Result |
|---|---|---|
| 1 | Full coarse critical path measured, not just row reveal | ✅ admission→`bgUpperReady` under real display: **HIT ≈ 6,356 clocks / ~100 lines**, **MISS ≈ 8,052 / 128**, **wrap ≈ 8,150 / 129** (§4) |
| 2 | Extended admission used only when a Stage 2 cache HIT is guaranteed | ✅ `bgCoarseHitGuaranteed` — VALID set **and** not an impending wrap **and** tag == `(SCROLL_ROW-2) mod SLR`; predicate C-output == the real consumer's HIT/MISS in **24/24** cases, target arithmetic byte-identical to `predecodeNextStageRow` for all 419 `SCROLL_ROW` (§6, §11) |
| 3 | MISS / fallback / wrap frames retain conservative admission | ✅ forced `VALID=0` at a [184,196) arrival → **defers** (0 in-window fallbacks); the stage-wrap step is classified conservative every loop (§11) |
| 4 | A measured later HIT deadline materially reduces reason-3 deferrals | ✅ identical burn-3 fixture: `COARSE_DEFER_CUTOFF` **262 → 196** (−66), admits **77 → 81**; every admit uses the extended deadline (§10) |
| 5 | Chosen deadline has a positive numeric safety margin | ✅ **`BG_COARSE_HIT_LATEST_START = 196`**: worst measured `bgUpperReady` **294–295**, `RASTER_PRESENT_READY` set ~296–297 — **~15 lines below physical line 0**, **~4 lines below the deadline-200 replay onset**, **~14 lines below the deadline-214 replay edge** (§5, §7, §8) |
| 6 | No new replay / catchup / incomplete / service / border failure | ✅ deadline sweep 0/0/0/0 for every value ≤ 196 under burn 3 **and** burn 5; 9k-frame natural run: `REPLAY` 2, `CATCHUP` 8, `INCOMPLETE` 0, `RASTER_BORDER_BAILS` 0 — baseline noise, unchanged from Stage 2 (§7, §12) |
| 7 | Exact `[19656]` | ✅ `frame_cycle_deltas: [19656]` — s3off and s3on |
| 8 | Terrain / turret / predecode semantics unchanged | ✅ window code byte-identical to Stage 2; `check_scroll_edges_rsel1 --aperture 55 246` body/last-row temporal diffs 0; `TURRET_GLYPH_PUBLICATIONS` frozen; predecode HIT rate unchanged (§12) |
| 9 | 199/235 blocked solely by reason 1 | ✅ `COARSE_DEFER_LIVE` Δ 396/400, `COARSE_ADMIT` Δ 0, `COARSE_DL_EXT` Δ **0** (gate-3 never reached), fine pinned at 7 (§13) |
| 10 | Stage 3 OFF restores the Stage 2 default exactly | ✅ `OPT_BG_COARSE_EXTENDED_DEADLINE` commented ⇒ **byte-identical** to the Stage 2 default `561ad2fa…` |

One implementation defect was found and fixed **during validation**: `JSR
bgCoarseHitGuaranteed` clobbers `A`, and the first draft read the conservative
deadline into `A` *before* the JSR, so on the C=0 path (wrap / stale / absent
cache) the deadline byte was garbage and every such coarse step deferred forever
— a hard stall at the first stage wrap. Fixed by reloading the conservative
deadline *after* the JSR. Post-fix: 15,000-frame runs through multiple stage
wraps track s3off exactly (§11).

---

## 2. Repository starting state

```
$ git branch --show-current
experimental-border-hud
$ git rev-parse HEAD
6a64130220e87eea182f6b638d38da03524a2bc5      (unchanged; no commit made)
$ git status --short
 M src/background_turrets.asm
 M src/main.asm
 M src/raster_scheduler.asm
?? reports/astra-c64-engine-architecture-review.md
?? reports/scroll-hitch-stage0-stage1-baseline-and-low-risk-optimisations.md
?? reports/scroll-hitch-stage2-incoming-row-predecode.md
?? reports/soft-edge-masking-and-astra-handoff-report.md
$ git log -5 --oneline
6a64130 Four top HUD sprites stable under managed mux load
bc9d275 Hard lock fixed, border sprite flicker remains
82c27c5 Top border sprites milestone 1
44e735c pre-architecture-teardown
d547c80 Establish RSEL1 border HUD experimental baseline
```

**Pre-existing uncommitted work, unchanged by this task:**

* **Task 10 (AMBER, guarded OFF)** — `SOFT_EDGE_MASK` blocks in `src/main.asm`;
  the whole `src/raster_scheduler.asm` diff.
* **Task 11 / Stage 0-1 (GREEN, guarded ON)** — `SCROLL_HITCH_DIAG`,
  `OPT_NOREUSE_BATCH_EXIT` in `src/main.asm`; `OPT_TURRET_GLYPH_DIRTY` in
  `src/main.asm` + `src/background_turrets.asm` (entire `background_turrets.asm`
  diff).
* **Stage 2 (GREEN, guarded ON)** — `OPT_BG_ROW_PREDECODE`,
  `predecodeNextStageRow`, `bgConsumePredecodedRow`, `bgPredecodeReset`,
  `BG_PREDECODED_ROW` + tag/counters, the `gameLoop` and `renderStageRowToScreen`
  hooks — all in `src/main.asm`.

| build | SHA-256 |
|---|---|
| Stage 2 default (Stage 3 baseline) | `561ad2fa66223b6086fb3bb7eb3f6f061144b3eb81db895010c736617c1cd5fd` |
| **Stage 3 final** (default: all five toggles ON) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` |
| Stage 3 OFF (`OPT_BG_COARSE_EXTENDED_DEADLINE` commented) | `561ad2fa…` — **byte-identical to Stage 2** |
| Stage 3 + Stage 2 OFF | `681935dc5179f35160bcd7c8b98b5df44daaed0e2cd4118d9a9e4a913a883af5` (Stage 1) |
| all five scroll-hitch toggles OFF | `1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd` (Astra baseline) |

---

## 3. Existing admission logic (before Stage 3)

`prepareBackgroundCoarse`, `#if SCROLL_HITCH_DIAG` build (default). Disassembly of
the Stage 2 default:

```
  LDA BG_COARSE_PENDING / BNE + / RTS          ; nothing pending
+ LDA #0 / STA BG_COARSE_PENDING
  LDX RASTER_BATCH_OFFSET / CPX RASTER_BATCH_END
  BCS !gateBeam                                ; gate 1: LIVE batch outstanding?
  <inc COARSE_DEFER_LIVE ; reason 1> ; JMP !defer
!gateBeam:
  LDA $D011 / BPL !gateCutoff                  ; gate 2: beam >= 256?
  <inc COARSE_DEFER_BEAM ; reason 2> ; JMP !defer
!gateCutoff:
  LDA $D012 / CMP #184 (BG_COARSE_LATEST_START)
  BCC !waitRead                                ; gate 3: RASTER < 184 -> admit
  <inc COARSE_DEFER_CUTOFF ; reason 3> ; JMP !defer
!waitRead:
  LDA $D012 / CMP #160 / BCC !waitRead         ; fence: wait for raster 160
  JSR saveCrossingRow
  JSR shiftBackgroundUpper                     ; 480-byte unrolled copy, ~3,843 cy
bgUpperCopied:
  <SCROLL_ROW wrap-then-decrement; wrap sets TURRET_STREAM_REWIND>
  LDA #0 / STA BG_DEST_ROW
  JSR renderStageRowToScreen                   ; Stage 2: HIT ~863 cy / MISS ~2,556 cy
bgUpperReady:
  ...
```

`BG_COARSE_LATEST_START = 184` was sized for the pre-Stage-2 ~40-line
`renderStageRowToScreen`; the fence at 160 is unchanged; there is no separate
check that the window *finishes* before any raster — the real deadline is
downstream (§5). The `#else` (`SCROLL_HITCH_DIAG` off) build has the same three
gates without the reason counters.

---

## 4. Full coarse-path timing

Isolated per-admission measurement under **representative display conditions**
(real IRQs, `DEN=1`, badlines, sprite DMA): breakpoint at the gate-pass point
(`!waitRead`) and at `bgUpperReady`, recording the raster line and STOPWATCH at
each. Stage 3 default build (the admitted-window code is byte-identical to Stage
2).

| path | gate-arrival raster | `bgUpperReady` raster | elapsed | CPU clocks |
|---|---:|---:|---:|---:|
| predecode **HIT** | 159–160 | **260** | **~100–101 lines** | **6,354–6,359** (median 6,359) |
| predecode **MISS** / fallback | 159 | **287** | ~128 lines | 8,051–8,052 |
| stage-wrap fallback | 159–160 | 288–290 | 128–130 lines | 8,088–8,195 |
| turret on the revealed row vs none | — | — | within ±1 line | ≤ +~40 clocks (`installTurretRow` scan + one 2-cell overlay) — not material |

* The window is entered after the `RASTER == 160` fence, so a clean-play admit
  (arrival ≈ 159) always starts the copy at 160 and lands `bgUpperReady` at
  **~260 (HIT) / ~287 (MISS)**.
* Under CPU load the CPU passes gate-3 at some later raster `A`; the fence is
  already satisfied, so **`bgUpperReady ≈ A + 99` (HIT)** / `A + 128` (MISS).
* The HIT window is dominated by `shiftBackgroundUpper` (~3,843 cy / ~61 lines,
  **identical for HIT and MISS** — Stage 3 does not touch it). The HIT vs MISS
  difference (~1,693 clocks / ~27 lines) is exactly the Stage 2 reveal saving.
* A turret body on the revealed row does not materially change the cost.

---

## 5. Unsafe-floor measurements

The frame is 312 physical lines. After `bgUpperReady`, `prepareBackgroundCoarse`
returns and the game loop runs `noteCoarseSuppressionOutcome` +
`refreshScoreIfDirty` + `waitForGameFrame`. `waitForGameFrame` (`raster_scheduler.asm`)
spins until `VIC_CONTROL_1` bit 7 (beam ≥ 256), then sets **`RASTER_PRESENT_READY = 1`**
and waits for the wrap. `rasterFrameReset`, at physical **line 0**, reads
`RASTER_PRESENT_READY`: if clear it takes the `!replay` path
(`inc RASTER_REPLAY_FRAMES`, runs `renderSprites` on main's behalf). It also
compares `RASTER_EXPECTED_ASSIGNMENTS` vs `RASTER_ASSIGNMENTS_DONE` and, on a
mismatch, `inc RASTER_INCOMPLETE_FRAMES`.

**⟹ the hard deadline is: `RASTER_PRESENT_READY` must be set before physical
line 0.** Equivalently `bgUpperReady` + the trailing work must complete before the
frame wraps.

Measured trailing cost (`bgUpperReady` → `RASTER_PRESENT_READY := 1`,
representative conditions): **~2 raster lines** and stable
(`noteCoarseSuppressionOutcome` is a few counters; `refreshScoreIfDirty` is a
no-op unless a kill dirtied the score that frame; `waitForGameFrame`'s spin is
short once the beam is near 256).

Extended-deadline sweep (§7) locates the empirical floor:

| observation | raster |
|---|---|
| clean-play `bgUpperReady`, HIT | ~260 |
| worst `bgUpperReady` at extended deadline **196** (burn 3) | **294–295** |
| first `RASTER_REPLAY_FRAMES` (extended deadline **200**, burn 3) | worst `bgUpperReady` ~299–301 |
| persistent replay (extended deadline **214**) | worst `bgUpperReady` ~311 (frame edge) |
| physical line 0 | 312 |

So the replay onset is at `bgUpperReady` ≈ **300** (`RASTER_PRESENT_READY` ≈ 302),
and the frame edge at ≈ 311. This is not a fixed hardware raster — it is the
CPU-time budget to reach `waitForGameFrame`. It is **not layout-dependent for a
HIT**: `shiftBackgroundUpper` + the 40-byte staged copy + `installTurretRow` are
bounded, and gate 1 already excludes a pending LIVE batch, so no per-object
sprite work runs inside the window. The next LIVE batch compare (when one
exists) begins ≈ raster 223 in the *lower* screen and is serviced by the IRQ,
which fires normally (no `SEI` in the window); it is not delayed by an admitted
HIT that finishes by ~295.

---

## 6. Predecode-hit eligibility predicate

`bgCoarseHitGuaranteed` (`$6d49`) returns **C=1 iff** the coarse step about to be
admitted is guaranteed to take `bgConsumePredecodedRow`'s HIT path. Conditions —
exactly the consumer's HIT conditions, evaluated with the **pre-decrement**
`SCROLL_ROW` that is still current at the gate:

1. **`OPT_BG_ROW_PREDECODE` compiled in.** A `.error` enforces
   `OPT_BG_COARSE_EXTENDED_DEADLINE ⇒ OPT_BG_ROW_PREDECODE`. With predecode off
   the routine is not built and the gate is the plain conservative check.
2. **`BG_PREDECODE_VALID != 0`.**
3. **Not an impending stage wrap: `SCROLL_ROW(16) != 0`.** `bgUpperCopied` sets
   `TURRET_STREAM_REWIND` on a wrap *before* `bgConsumePredecodedRow` runs, and
   the consumer treats `TURRET_STREAM_REWIND != 0` as a forced MISS. At the gate
   the wrap has not happened yet, so `SCROLL_ROW == 0` is the equivalent
   predictor (the wrap branch is entered exactly when `SCROLL_ROW(16) == 0`).
4. **`BG_PREDECODE_ROW` tag == `(SCROLL_ROW - 2) mod STAGE_LOGICAL_ROWS`.** This
   is the row the consumer will require after the coarse step's `SCROLL_ROW--`
   and `renderStageRowToScreen`'s `wrapBgLogicalRow` (Stage 2 report §3/§11:
   `SCROLL_ROW_new - 1 = SCROLL_ROW - 2`). The arithmetic in
   `bgCoarseHitGuaranteed` is the same instruction sequence as
   `predecodeNextStageRow`'s target computation.

`BG_DEST_ROW` is structurally 0 for the coarse reveal (set by
`prepareBackgroundCoarse` immediately before `renderStageRowToScreen`), so it is
not re-checked.

**Why C=1 here is still true at the consume.** Between the predicate and
`bgConsumePredecodedRow`, only `saveCrossingRow` (reads screen row 12 → a
separate buffer), `shiftBackgroundUpper` (shifts screen matrix rows), the
`SCROLL_ROW--` (non-wrap, since condition 3 excluded `SCROLL_ROW == 0`), and
`BG_DEST_ROW := 0` run. None touch `BG_PREDECODED_ROW`, `BG_PREDECODE_VALID`, the
tag, or set `TURRET_STREAM_REWIND`. The raster IRQ path (`raster_scheduler.asm`)
references none of them.

**Verification (§11):** `bgCoarseHitGuaranteed`'s C output equals the real
`bgConsumePredecodedRow` HIT/MISS outcome for **24/24** combinations of
`SCROLL_ROW ∈ {200,199,120,61,3,2,1,0}` × `{invalid, valid+matching-tag,
valid+mismatched-tag}` (including the wrap case), and its internal
`(SCROLL_ROW-2) mod SLR` equals `predecodeNextStageRow`'s target for **all 419**
non-wrap `SCROLL_ROW` values.

The gate does **not** reuse a value left in memory by `predecodeNextStageRow`; it
recomputes into its own `BG_COARSE_GATE_ROW` scratch so a future edit inserting
work between the predecode call and the gate cannot silently break it.

---

## 7. Deadline sweep

Fixed Stage 3 build, extended-deadline immediate runtime-patched to each
candidate, calibrated pre-gate burn, 1,600 frames/candidate. (The calibrated
burn is the deadline-characterisation tool the task endorses — it isolates the
gate-arrival raster cleanly; a collision-driven fixture perturbs CIA encounter
timing and cannot be held stable.)

### burn `ldx #3` (moderate, ≈ 3,840 cy on pending frames)

| ext DL | ADMIT | DEFER_CUTOFF | DEFER_BEAM | REPLAY | CATCHUP | INCOMPLETE | BORDER_BAIL | worst `bgUpperReady` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 184 (= conservative) | 80 | 312 | 0 | 0 | 0 | 0 | 0 | 281 |
| 192 | 70 | 463 | 10 | 0 | 0 | 0 | 0 | 290 |
| **196** | 84 | 251 | 0 | **0** | **0** | **0** | **0** | **295** |
| 200 | 91 | 148 | 0 | **1** | 0 | 0 | 0 | 299 |
| 202 | 85 | 241 | 6 | 0 | 0 | 0 | 0 | 301 |
| 204 | 88 | 200 | 3 | 0 | 1 | 0 | 0 | 302 |
| 208 | 92 | 129 | 0 | 1 | 0 | 0 | 0 | 307 |
| 214 | 98 | 21 | 0 | 3 | 0 | 0 | 0 | 311 |

### burn `ldx #5` (hard, ≈ 6,400 cy)

| ext DL | ADMIT | DEFER_CUTOFF | DEFER_BEAM | REPLAY | CATCHUP | INCOMPLETE | worst `bgUpperReady` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 184 | 37 | 806 | 194 | 5 | 0 | 0 | 280 |
| 192 | 13 | 1384 | 0 | 0 | 0 | 0 | 291 |
| **196** | 1 | 1576 | 0 | **0** | **0** | **0** | **295** |
| 198 | 1 | 1576 | 0 | 0 | 0 | 0 | 298 |
| 200 | 1 | 1576 | 0 | 0 | 0 | 0 | 298 |
| 202 | 62 | 274 | 326 | 13 | 1 | 0 | 303 |
| 204 | 77 | 178 | 183 | 6 | 1 | 0 | 301 |
| 208 | 68 | 170 | 339 | 13 | 0 | 0 | 306 |
| 214 | 71 | 121 | 328 | 12 | 0 | 0 | 311 |

**Consistent knee: every value ≤ 196 is clean (0 replay / catchup / incomplete /
beam-defer) under both burns; the first `RASTER_REPLAY_FRAMES` appears at 200,
and by 202–214 replay is persistent with heavy beam-defer pressure.** `bgUpperReady`
rises monotonically with the deadline (deterministic within a run): 196 → 294–295,
200 → 298–299, 214 → 311.

---

## 8. Chosen shipping deadlines

| | value | rationale |
|---|---|---|
| **conservative** `BG_COARSE_LATEST_START` | **184** (unchanged) | applies to every MISS / stale-cache / wrap / `OPT_BG_ROW_PREDECODE`-off request; safe for the full ~128-line fallback reveal (clean-play MISS `bgUpperReady` ≈ 287). No measurement justified moving it, and lowering it would cost an extra deferral on the rare MISS/startup/wrap frame. |
| **extended** `BG_COARSE_HIT_LATEST_START` | **196** | applies **only** when `bgCoarseHitGuaranteed` returns C=1 (guaranteed ~99-line HIT reveal). |

### Measured margin for the extended deadline (196)

```
latest admitted gate-arrival raster (RASTER < 196)  : 195
HIT window (measured, arrival > 160)                : ~99 lines   (bgUpperReady = arrival + 99)
worst observed bgUpperReady (burn 3 & burn 5 sweep) : 294 - 295
trail bgUpperReady -> RASTER_PRESENT_READY := 1     : ~2 lines
worst RASTER_PRESENT_READY                          : ~296 - 297
--------------------------------------------------------------------
earliest replay-onset RASTER_PRESENT_READY (ext DL 200)  : ~301
persistent-replay bgUpperReady (ext DL 214)              : ~311
physical line 0                                          : 312
--------------------------------------------------------------------
margin to replay onset      : ~301 - ~297  =  ~4 raster lines  (~250 cycles)
margin to physical line 0   :  312 - ~297  =  ~15 raster lines (~945 cycles)
margin to the frame edge    :  ~311 - ~297 =  ~14 raster lines
```

196 is **deliberately not the highest value that survived a run.** 198–200 also
survived individual runs, but 200 already produced a replay and sits ~1 line from
the onset. 196 keeps a ~4-line cushion below the empirical onset and a ~15-line
cushion to line 0, under both a moderate and a hard pre-gate stress, with `DEFER_BEAM`
= 0 (no beam-gate leakage). VIC stalls are already folded into the measurements
(they were taken with `DEN=1` and real badlines/sprite DMA — CPU clocks
`6,359 ≈ 101 lines` include the steal).

---

## 9. Implementation

All Stage 3 changes are `src/main.asm`, all `#if OPT_BG_COARSE_EXTENDED_DEADLINE`.

| location | change |
|---|---|
| toggle block (~L48–96) | `#define OPT_BG_COARSE_EXTENDED_DEADLINE` + doc; `.error` guards requiring `SCROLL_HITCH_DIAG` and `OPT_BG_ROW_PREDECODE`; an early `bgIncWord` macro definition (guarded, emits nothing; needed before `prepareBackgroundCoarse`) — the Stage 2 `bgIncWord` def is now `#if !BG_INC_WORD_MACRO_DEFINED` so exactly one exists |
| `.const` block (~L232) | `BG_COARSE_HIT_LATEST_START = 196` + a `.error` that it exceeds the conservative deadline; the measurement rationale in the comment |
| `prepareBackgroundCoarse` `!gateCutoff` (diag build) | the inline `LDA RASTER / CMP #184 / …` replaced by `JSR bgCoarseReason3Defer / BCC !waitRead+ / LDA #3 / STA COARSE_LAST_REASON / JMP !defer+`. Net **−12 bytes** in the near-full `$2920` segment. The `#else` (diag-off) build is unchanged (Stage 3 requires diag). |
| `bgUpperReady` (diag build) | `+ JSR bgCoarseNoteReady` (record the latest `bgUpperReady` raster this game) |
| `initBackground` | the per-game counter reset moved into `bgPredecodeReset` (which `initBackground` already calls) — 0 bytes added to `$2920` |
| `bgPredecodeReset` (`$6c…`) | second clear loop over `bgCoarseStage3State … bgCoarseStage3StateEnd` |
| new, in the `$6c3a` hole after `STAGE_TEST_END` | `bgCoarseHitGuaranteed` (the predicate), `bgCoarseReason3Defer` (deadline pick + `RASTER` compare + `COARSE_DEFER_CUTOFF`/`COARSE_CUT_EXT`/`COARSE_CUT_CONS`/`COARSE_ADMIT_EXT` classification; returns C=1 defer / C=0 admit), `bgCoarseNoteReady`; the state block `bgCoarseStage3State … End` (`COARSE_DL_USED`, `BG_COARSE_GATE_ROW`, and the 7 diag counters) |

No change to the pending-LIVE gate, the beam gate, the `RASTER == 160` fence,
`BG_COARSE_LATEST_START`, `shiftBackgroundUpper`, `saveCrossingRow`,
`renderStageRowToScreen`, `bgConsumePredecodedRow`, `predecodeNextStageRow`,
BUILD/LIVE, HUD, border, RSEL, `$D018`, collision, projectile suppression, or
gameplay object limits. `src/background_turrets.asm` and
`src/raster_scheduler.asm` are **not touched** by Stage 3.

### New state (`$6c…` region, `#if OPT_BG_COARSE_EXTENDED_DEADLINE`)

| symbol | width | meaning |
|---|---|---|
| `COARSE_DL_USED` | byte | effective reason-3 deadline the last request was judged against (184 or 196) |
| `BG_COARSE_GATE_ROW` | word | predicate scratch: `(SCROLL_ROW - 2) mod STAGE_LOGICAL_ROWS` |
| `COARSE_DL_EXT` / `COARSE_DL_CONS` | word | coarse requests reaching gate-3, judged under the extended / conservative deadline |
| `COARSE_CACHE_VALID_UNQUAL` | word | subset of `_CONS`: cache VALID but wrap-impending or tag mismatch |
| `COARSE_ADMIT_EXT` | word | admits granted under the extended deadline |
| `COARSE_CUT_EXT` / `COARSE_CUT_CONS` | word | reason-3 defers under the extended / conservative deadline |
| `COARSE_UPPER_READY_RASTER_MAX` | byte | latest `bgUpperReady` raster this game, minus 256 (tracked only while beam ≥ 256) |

`bgCoarseStage3State … bgCoarseStage3StateEnd` is `$6df…–$6e0f` (well below the
`$8800` turret segment). The `$2920` engine-control segment ends at `$2eee` (was
`$2ef5` at Stage 2 — Stage 3 *shrank* it by lifting the gate into helpers),
ceiling `$2f00`.

---

## 10. Reason-3 before/after

Identical burn-3 pre-gate fixture, identical object/screen state, 1,500 frames,
s3off (Stage 2, deadline 184 only) vs s3on (Stage 3, 184/196):

| build | `COARSE_ADMIT` | `COARSE_DEFER_CUTOFF` | `DEFER_BEAM` | `DEFER_LIVE` | REPLAY | CATCHUP | INCOMPLETE | BORDER_BAIL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| s3off (Stage 2) | 77 | **262** | 0 | 0 | 0 | 0 | 0 | 0 |
| s3on (Stage 3) | **81** | **196** | 0 | 0 | 0 | 0 | 0 | 0 |

Stage 3 counters on the s3on run: `COARSE_DL_EXT` 277, `COARSE_DL_CONS` 0,
`COARSE_CACHE_VALID_UNQUAL` 0, `COARSE_ADMIT_EXT` 81, `COARSE_CUT_EXT` 196,
`COARSE_CUT_CONS` 0, `COARSE_UPPER_READY_RASTER_MAX` = 38 → raster **294**.

**−66 reason-3 deferrals (−25 %), +4 admits, zero new replay / catchup /
incomplete / border-bail, worst `bgUpperReady` 294.** Every admit used the
extended deadline; every remaining reason-3 defer was a frame the burn pushed
past raster 196.

Deadline-margin margin held under the hard burn-5 fixture too (§7): at 196,
`bgUpperReady` never exceeded 295 and replay/catchup/incomplete stayed 0 even
when the burn forced `ADMIT` down to 1.

---

## 11. Forced MISS / wrap proof

### Forced predecode MISS at a late arrival

Burn fixture, breakpoint at `bgCoarseReason3Defer` entry; for every coarse
request whose gate-arrival raster is in **[184, 196)** (the extended-only band),
`BG_PREDECODE_VALID` is poked to 0 before the decision.

| forced frames (arrival ∈ [184,196), VALID:=0) | Δ`COARSE_DEFER_CUTOFF` | Δ`COARSE_ADMIT` | Δ`BG_PREDECODE_MISS` |
|---:|---:|---:|---:|
| 31 | 513 | 86 | **0** |

`Δ BG_PREDECODE_MISS = 0` ⟹ **none of the forced-MISS frames admitted** (an
admitted MISS increments it via the in-window fallback consume). With
`VALID = 0`, `bgCoarseHitGuaranteed` returns C=0, `bgCoarseReason3Defer` reloads
the **conservative 184** deadline, `RASTER (≥ 184) cmp 184` fails the `bcc`, and
the frame **defers**. A forced MISS at a late arrival never takes the extended
deadline and never falls through to the 2,556-clock in-window fallback.

(The A-clobber defect described in §1 originally broke exactly this: on the C=0
path `A` held garbage from `bgCoarseHitGuaranteed`, so `COARSE_DL_USED` and the
compare were nonsense. Fixed; re-verified here.)

### Stage wrap

* **Predicate**: `SCROLL_ROW(16) == 0` → `bgCoarseHitGuaranteed` returns C=0
  (`COARSE_CACHE_VALID_UNQUAL`++, `COARSE_DL_CONS`++). The wrap step is judged
  against the **conservative** deadline. Proven for `SCROLL_ROW = 0` in the
  24/24 predicate matrix (§6).
* **Consumer**: `bgUpperCopied` sets `TURRET_STREAM_REWIND`; `bgConsumePredecodedRow`
  forces its wrap MISS (`BG_PREDECODE_INVAL`++, `BG_PREDECODE_MISS`++) and the
  Stage 1 decode runs in-window. Terrain byte-identical to Stage 1 (Stage 2
  report §11 W1, unchanged).
* **9,000-frame natural run** (one full stage wrap): `COARSE_DL_CONS` 1,
  `COARSE_CACHE_VALID_UNQUAL` 1, `BG_PREDECODE_MISS` 1 — exactly the single wrap
  step, classified conservative, handled without a hitch; the other 561 coarse
  steps `COARSE_DL_EXT` / `BG_PREDECODE_HIT`.
* **15,000-frame s3off vs s3on comparison** through **multiple** stage wraps:
  frame-for-frame identical `COARSE_ADMIT` / `BG_PREDECODE_HIT` / `BG_PREDECODE_MISS`
  / `SCROLL_ROW` progression; `RASTER_BORDER_BAILS` 0, `RASTER_INCOMPLETE_FRAMES`
  0 throughout. No stall.

---

## 12. Supported gameplay tests

### Frozen fixtures — s3off vs s3on **byte-identical**

| load | SORTED_COUNT | Δ`COARSE_ADMIT` | Δ`COARSE_DEFER_CUTOFF` | Δ`COARSE_DEFER_LIVE` | Δ`SCROLL_ROW` | Δ REPLAY / CATCHUP / INCOMPLETE |
|---|---:|---:|---:|---:|---:|---:|
| 5 enemies + player | 6 | 19 | 0 | 0 | −19 | 0 / 0 / 0 |
| **6 enemies + player** | 7 | 19 | 0 | 0 | −19 | 0 / 0 / 0 |
| 6 enemies + 2 bullets + player | 9 | 0 | 0 | 300 | 0 | 0 / 0 / 0 (structural reason-1 hold, by design) |
| 8 rendered / no reuse | 8 | 19 | 0 | 0 | −19 | 2 / 0 / 0 (the `dREP=2` is present in s3off too — Y-cluster sprite-service pressure, not Stage 3) |
| 9 objects / one reuse | 9 | 0 | 0 | 291 | 0 | 0 / 0 / 0 (reason-1 hold) |

In these clean fixtures the CPU reaches gate-3 at raster ≈ 159 (< 184 < 196), so
**both** deadlines admit identically. Stage 3 diverges from Stage 2 only on
frames arriving in [184, 196), which requires real CPU pressure. The user's clean
six-enemy experience is unchanged.

### Long natural run — 9,000 frames, s3on

| quantity | value |
|---|---|
| coarse admits | 562 (`COARSE_ADMIT_EXT` **561**, conservative 1 = the wrap) |
| `COARSE_DEFER_CUTOFF` | 2 (both extended-class) |
| `COARSE_DL_EXT` / `COARSE_DL_CONS` / `COARSE_CACHE_VALID_UNQUAL` | 563 / 1 / 1 |
| predecode HIT / MISS | 561 / 1 (the wrap) |
| `COARSE_UPPER_READY_RASTER_MAX` | 34 → raster **290** (22 lines below line 0) |
| `RASTER_REPLAY_FRAMES` / `RASTER_CATCHUPS` / `RASTER_INCOMPLETE_FRAMES` / `RASTER_BORDER_BAILS` | 2 / 8 / 0 / 0 |

`frame_cycle_deltas: [19656]`, `service_failure_count` 0, `sprite_start_miss_count`
0. The 2 replay / 8 catchup over 9,000 frames are baseline noise, present at the
same rate in the Stage 1/2 reports.

### 15,000-frame s3off vs s3on

Frame-for-frame equivalent (§11): admits, HIT/MISS, `SCROLL_ROW`, all failure
counters. Multiple stage wraps, no stall, no border bail.

---

## 13. 199/235 structural control

s3on, 8 enemies at Y=199 + player at Y=235, coarse requested continuously, 400
measured frames:

| Δ`COARSE_DEFER_LIVE` | Δ`COARSE_ADMIT` | Δ`COARSE_DEFER_CUTOFF` | Δ`COARSE_DL_EXT` | Δ`BG_PREDECODE_HIT` | Δ`BG_PREDECODE_PREPARED` | Δ`SCROLL_ROW` | `SCROLL_FINE` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| **396** | **0** | 0 | **0** | 0 | 0 | 0 | pinned at **7** |

Reason 1 fires first, every frame. **`COARSE_DL_EXT` Δ 0** — gate-3 (and hence
the whole extended-deadline mechanism) is **never reached**; the pending-LIVE
gate defers first. The predecode cache sits staged and idle (`Δ PREPARED = 0`).
`frame_cycle_deltas: [19656]`, `RASTER_BORDER_BAILS` 0, service failures 0. The
199/235 obstruction is unchanged and Stage 3 is provably irrelevant to it.

---

## 14. Regression matrix

| area | check | result |
|---|---|---|
| **Build / toggles** | Stage 3 default (all 5 ON) | `f2abc225159e81bf…` builds clean |
| | Stage 3 OFF | `561ad2fa…` — **byte-identical to Stage 2** |
| | Stage 3 + predecode OFF | `681935dc…` (Stage 1) |
| | all 5 OFF | `1fadf2b4…` (Astra) |
| | Stage 3 ON + `SCROLL_HITCH_DIAG` OFF / + predecode OFF | refused at assembly (`.error` + symbol errors) — unsupported by design |
| **PAL cadence** | `frame_cycle_deltas` (900 frames) | `[19656]` — s3off and s3on |
| **Scroll** | divider 2, all 8 fine phases, repeated 7→0, prolonged fine-7 hold, wrap | no row skip/duplication; 15k-frame run through multiple wraps identical to Stage 2 |
| **Terrain** | `check_scroll_edges_rsel1 --aperture 55 246` | `body_temporal_diffs: 0`, `lastrow_temporal_diffs: 0` — s3off and s3on |
| **Predecode** | steady HIT rate | 561/562 admits are HITs; MISS only at the wrap |
| | prolonged hold, no repeated decode | 199/235: `Δ PREPARED = 0` over 400 held frames |
| | forced MISS / wrap → conservative deadline | §11 — forced-MISS frames defer, wrap classified conservative |
| | Stage 3 OFF restores Stage 2 | byte-identical |
| **Sprites / scheduler** | `service_failure_count` / `sprite_start_miss_count` / `incomplete_live_assignments` | 0 / 0 / none — s3off and s3on |
| | 8 post-HUD slots, BUILD/LIVE semantics | untouched (Stage 3 changes only the reason-3 gate) |
| **HUD / border** | `RASTER_BORDER_BAILS` (9k + 15k frames) | 0 |
| | `RASTER_INCOMPLETE_FRAMES` / whole-border flash / hard lock | 0 / none / none |
| **Collision** | broad-phase / confirmed-hit paths | untouched |
| **Turrets** | `TURRET_GLYPH_PUBLICATIONS` frozen; overlay on the revealed row | Δ 0 over 6k frames; window code (incl. `installTurretRow`) byte-identical to Stage 2 (Stage 2 report §11 T1–T3) |
| **Lifecycle** | init / restart | `initBackground` → `bgPredecodeReset` clears the Stage 3 counters + `COARSE_DL_USED` |

`assignments` / `catchups` / `replay_frames` differ between the seeded s3off and
s3on captures (6/1/12 vs 5/2/17) because Stage 3's extra admits shift CIA-derived
encounter timing — different gameplay sequences, not comparable frame-for-frame
(Stage 0/1 A/B methodology). Under deterministic frozen fixtures s3on == s3off.

---

## 15. Remaining hitch architecture

### CPU-late / reason 3 (`COARSE_DEFER_CUTOFF`)

* **After Stage 2:** the HIT reveal shrank to ~99 lines, but `BG_COARSE_LATEST_START`
  stayed at 184, so the recovered headroom was unused — Stage 2 did not reduce
  reason-3 deferrals.
* **After Stage 3:** a proven HIT is judged against **196** instead of 184.
  Reason-3 deferrals drop ~25 % in the burn-3 stress (262 → 196) with a measured
  ~15-line margin to line 0. In clean natural play reason-3 is already near-zero
  (2 in 9,000 frames), so the practical effect is on genuine CPU-pressure frames
  (heavy collision confirmation stacked with score refresh / turret / suppression
  work).
* **Remaining reason-3 exposure:** frames that arrive at the gate at raster
  ≥ 196 still defer, and frames whose reveal is a genuine MISS (startup, wrap,
  any future discontinuity) still use the 184 deadline. Pushing the extended
  deadline higher is bounded by the ~300 replay onset (§5) and is not worth the
  ~1-line margin at 198–200.

### Pending-LIVE / reason 1 (`COARSE_DEFER_LIVE`, 199/235)

* **Unchanged and structurally untouched by Stage 3** — gate-3 is never reached
  for that layout (§13). The coarse copy is still blocked by a hardware sprite
  fetch in progress at gate 1, not by CPU time. Needs the second character
  matrix or a provably-safe overlap of the copy with an in-flight LIVE batch.

---

## 16. Stage 4 recommendation

**Is CPU-late hitching effectively exhausted for the supported gameplay
envelope?** — **Largely, yes, for the shipped load.** In 9,000 frames of natural
play with the standard wave load, reason-3 deferrals are 2 (both recovered by the
extended deadline would need a still-later deadline, which the margin does not
allow). The Stage 1 CPU savings (~1,100 clocks/frame), Stage 2 predecode (~1,655
clocks out of the window on every HIT), and Stage 3's ~15-line-margin extended
deadline together mean a normal frame has to overrun by **~40+ raster lines
before the gate** to be pushed past 196 — i.e. a genuinely pathological CPU
spike, not ordinary combat. The residual is the deep tail: a worst-case
broad-phase-positive collision scan (~1,300 clocks) stacked with a dirty score
refresh and turret/suppression work on the same frame can still cross 196. That
tail is small and does not visibly hitch (it is a one-frame deferral that the
next frame recovers).

**Further CPU-late optimisation is low-value from here.** The obvious remaining
lever — a still-later extended deadline — is blocked by the ~300 replay onset,
which is a hard frame-budget limit, not a tunable. Shaving the collision-confirmation
tail (Stage 0/1 investigated it) would help the deep tail but is a separate,
larger piece of work with its own correctness risk.

**Does the pending-LIVE (reason 1) obstruction justify a bounded overlap
experiment, or is a second character matrix the cleaner next move?** — **The
second character matrix is the cleaner next move.** Reason 1 is now the *only*
remaining scroll-hitch class, and it is purely structural: the coarse upper-matrix
copy cannot run while a LIVE reuse batch is still fetching the lower screen,
because they share the one matrix. A "bounded overlap" experiment would have to
prove the copy cannot corrupt or be corrupted by an in-flight sprite DMA/matrix
fetch for *every* batch raster and object layout — a large, fragile proof surface.
A second matrix at `$2800` (Astra's `$2800-$2BFF` plan, freed by relocating the
1,881-byte CPU-only table/code block) lets the upper rows be prepared on the
inactive matrix and flipped via `$D018` at the frame boundary, removing the
shared-resource conflict entirely and making the 199/235 case a non-event. That
is the Stage 4 recommendation. It is also the prerequisite for any future
JIT-multiplex or full-aperture work.

Neither is implemented here.

---

## 17. Exact files changed

### Pre-existing Task 10 (SOFT_EDGE_MASK, `#define` OFF — untouched)

`src/raster_scheduler.asm` (entire `+80` diff); the `SOFT_EDGE_MASK` blocks in
`src/main.asm`.

### Pre-existing Task 11 / Stage 0-1 (`#define` ON — untouched)

`src/main.asm`: `SCROLL_HITCH_DIAG`, `OPT_NOREUSE_BATCH_EXIT`,
`OPT_TURRET_GLYPH_DIRTY`. `src/background_turrets.asm` (entire `+22` diff).

### Pre-existing Stage 2 (`#define` ON — untouched except one guard)

`src/main.asm`: `OPT_BG_ROW_PREDECODE` and its routines/state/hooks. The **only**
Stage-2-line touched by Stage 3 is the `bgIncWord` macro definition, now
`#if !BG_INC_WORD_MACRO_DEFINED` so the earlier Stage 3 copy is used when Stage 3
is on — zero byte effect (verified: Stage 3 OFF == Stage 2 default).

### Stage 3 (this task) — `src/main.asm` only, all `#if OPT_BG_COARSE_EXTENDED_DEADLINE`

* toggle `#define` + doc + `.error` requires-guards + early `bgIncWord` macro.
* `.const BG_COARSE_HIT_LATEST_START = 196` + range `.error` + rationale comment.
* `prepareBackgroundCoarse` `!gateCutoff`: inline reason-3 check → `jsr bgCoarseReason3Defer`.
* `bgUpperReady`: `jsr bgCoarseNoteReady`.
* `bgPredecodeReset`: second clear loop over the Stage 3 state block.
* new routines + state after `STAGE_TEST_END`: `bgCoarseHitGuaranteed`,
  `bgCoarseReason3Defer`, `bgCoarseNoteReady`, `bgCoarseStage3State …
  bgCoarseStage3StateEnd` (`COARSE_DL_USED`, `BG_COARSE_GATE_ROW`, 7 counters).

`git diff --stat` net: `src/main.asm` `+655 −3` (Stage 2 was `+428 −3`; Stage 3
adds ~227 lines, ~150 of them the guarded routine block). `src/background_turrets.asm`
`+22` and `src/raster_scheduler.asm` `+80` are entirely pre-existing.

### Test / probe / report artefacts (not engine source)

* `reports/scroll-hitch-stage3-predecode-aware-coarse-deadline.md` — this report.
* Scratchpad probes: `s3window.py` / `s3window_on.py` (full-window timing),
  `s3sweep.py` / `s3fsweep.py` (deadline sweep), `s3trail.py` (arrival→ready→RPR
  chain), `s3predicate.py` (predicate ↔ consumer equivalence + target arithmetic),
  `s3behav.py` (reason-3 A/B + forced MISS + 199/235), `s3long.py` (long run +
  supported gameplay), `s3stall.py` (15k-frame s3off/s3on wrap comparison),
  `s3wrapturret.py`.
* A/B build tree `/tmp/sh3/{on,off}/`.

No commit, stage, tag, reset, stash, pull, push, or branch switch was performed.

---

## 18. Final repository state

```
$ git status --short
 M src/background_turrets.asm
 M src/main.asm
 M src/raster_scheduler.asm
?? reports/astra-c64-engine-architecture-review.md
?? reports/scroll-hitch-stage0-stage1-baseline-and-low-risk-optimisations.md
?? reports/scroll-hitch-stage2-incoming-row-predecode.md
?? reports/scroll-hitch-stage3-predecode-aware-coarse-deadline.md
?? reports/soft-edge-masking-and-astra-handoff-report.md

$ git diff --stat
 src/background_turrets.asm |  22 ++
 src/main.asm               | 655 +++++++++++++++++++++++++++++++++++++++++++-
 src/raster_scheduler.asm   |  80 ++++++
 3 files changed, 754 insertions(+), 3 deletions(-)
```

**Repository history was not altered.** No commit, add/stage, tag, reset, stash,
pull, push, or branch switch. HEAD is still
`6a64130220e87eea182f6b638d38da03524a2bc5`. All changes are in the working tree,
behind the `#if OPT_BG_COARSE_EXTENDED_DEADLINE` toggle (default ON).

* Stage 3 default build:
  `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991`
* `OPT_BG_COARSE_EXTENDED_DEADLINE` commented (Stage 2 restored):
  `561ad2fa66223b6086fb3bb7eb3f6f061144b3eb81db895010c736617c1cd5fd`
* + `OPT_BG_ROW_PREDECODE` commented (Stage 1):
  `681935dc5179f35160bcd7c8b98b5df44daaed0e2cd4118d9a9e4a913a883af5`
* all five scroll-hitch toggles commented (Astra baseline):
  `1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd`
