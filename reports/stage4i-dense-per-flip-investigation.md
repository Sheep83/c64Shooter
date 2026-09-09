# Stage 4I — Mode-C `--dense` Per-Flip / Mux Cost Investigation

## Verdict: **GREEN — causal account complete, no fix justified**

The extra Mode-C `--dense` sprite-start misses are **not** a per-flip cost, not a
pointer-mirror cost, not a turret-reconcile cost, and not a `ssBatchPtrStore`
cost. They are a **VIC-II badline collision on one specific scroll phase**, and
Mode C's higher count is **exposure, not cost**: Mode C is the only mode that can
actually scroll under this fixture, so it visits the vulnerable phase 6× more
often. Per *exposed* frame the miss rate is statistically identical in all three
modes — and the **single-screen Stage-3 baseline (Mode A) is the worst of the
three**, which means the phenomenon predates the double-buffered scroller
entirely.

No source change was made. All three baseline hashes are unchanged and the
working tree is clean.

---

## 1. Repository state (inspected, not assumed)

```
branch          experimental-border-hud
HEAD            479bb32  "Bug fixes related to coarse transition"
tracking        origin/experimental-border-hud (in sync — HEAD is pushed)
status          clean (no modified, staged or untracked files)
tags            engine-pre-background-scroll, hud-updated-with-score,
                pre-terrain-workshop, stable-double-buffered-scroller,
                stable-single-screen-scroller, v1.0
```

**Stage 4G and 4H have now been committed and pushed**, in `479bb32`, which
carries `src/main.asm` (+105/−26), `tools/check_raster_capture.py`,
`tools/vice_scroll_test.py`, and the four 4G/4H report + worklog files. **No new
tag was created** — `stable-double-buffered-scroller` still points at the
original Stage 4D+4E commit (`931dca1`), as intended.

Toggle state in the committed source (all sub-stage toggles commented, i.e. the
tree builds Mode A by default):

```
147: //#define OPT_SECOND_SCREEN
159:     //#define OPT_SS_INACTIVE_BUILD
165:     //#define OPT_SS_FLIP_COARSE
173:     //#define OPT_SS_ALLOW_PENDING_LIVE_FLIP
```

Hashes rebuilt from this checkout and verified against the established baselines:

| mode | toggles | SHA-256 | expected |
|---|---|---|---|
| A | all off | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` | ✅ match |
| B | 4D+4E, PLF off | `e0c3141a7ee88f8f6216e94a0ee8f1a0f48c047f9de02f5c89da42106a74a6e4` | ✅ match |
| C | 4D+4E+4F+4G | `80d5b0461c070fe23d6e5dbcb2124eb9e4093dbbc4034464d9afe0596f08ce66` | ✅ match |

No commit, stage, tag, push, pull, reset, stash or branch switch was performed.
`build/shooter.prg` is left at Mode A, matching the Stage 4G/4H convention.

---

## 2. Objective 1 — where the misses actually occur

### 2.1 Every miss is the same event, in every mode

Extracting the untruncated deadline records from the existing captures (the
`sprite_start_misses` array in `raster-verification.json` is capped at 20 entries;
a scratchpad copy of the checker with the cap removed was used for the full data):

| capture | misses | event kind | affected batch |
|---|---|---|---|
| Mode A `--dense` 200f | 3 | `rasterBatchMasksApplied` (100%) | offsets 7/15 |
| Mode B `--dense` 200f | 2 | `rasterBatchMasksApplied` (100%) | offsets 7/15 |
| Mode C `--dense` 200f | 16 | `rasterBatchMasksApplied` (100%) | offsets 7/15 |
| Mode C `--dense` 600f | 53 | `rasterBatchMasksApplied` (100%) | offsets 7/15 |

Not one miss is a `rasterInitialApplied`, `hudSlotReclaimed`,
`rasterAssignmentApplied` or `rasterInitialMasksApplied` event. **Every miss, in
every mode, is the end-of-batch mask write for the final batch of the LIVE plan**
— batch-array offsets 7 and 15 are the last batch of each of the two plan
buffers. That batch services the dense fixture's bottom-most objects, whose
`ASSIGN_Y` minimum is **164** (the fixture seeds `OBJECT_Y` =
`range(100,129,4) + range(136,165,4)`, so 164 is the largest Y).

The oracle's deadline for that batch is the project's standing convention
`y*63 + 55` = raster **164, cycle 55** (= position 10387).

### 2.2 Misses are *anti*-correlated with flips

Publication frames were identified independently of the page dumps: a frame where
`gameplayPresented` traces but `bgLowerReady` does not is a frame where
`finishBackgroundCoarse` tail-jumped into `ssPublishCoarseFlip` and never reached
its normal exit. That set is **exactly identical** to the set of frames where the
captured `BG_ACTIVE_PAGE` byte changes (18 = 18 over 600 frames), confirming both
detectors.

Over the 600-frame Mode C dense capture (18 publications, 53 misses):

```
misses landing ON a publication frame ....... 0
misses within ±2 frames of a publication .... 0
misses within ±4 frames of a publication .... 0
offset of each miss after nearest publication:  +16 (×19), +17 (×19), +19 (×15)
```

The coarse cycle under this fixture is 32 physical frames (the main loop runs at
half rate — see §2.4 — so one 8-step fine cycle takes 32 frames). The misses land
at offset +16..+19, i.e. **the diametrically opposite phase of the cycle from the
flip**. If per-flip work were the cause, misses would cluster *on* publication
frames; they are maximally distant from them instead.

### 2.3 Every miss occurs at exactly one scroll phase

Correlating each miss frame against the `physical_fine` value the capture already
records ($D011 & 7 = YSCROLL = `SCROLL_FINE`):

| capture | miss frames by fine value | exposed frames at that phase | rate |
|---|---|---|---|
| Mode A 200f | **fine==4: 3** (no others) | 4 | 75% |
| Mode B 200f | **fine==4: 2** (no others) | 4 | 50% |
| Mode C 200f | **fine==4: 16** (no others) | 24 | 67% |
| Mode C 600f | **fine==4: 53** (no others) | 76 | 70% |

**100% of misses in every mode and every run occur at `SCROLL_FINE == 4`.**

And `164 & 7 == 4`. A VIC-II badline occurs on raster line R (inside the display
window) when `R & 7 == YSCROLL`. So **the deadline line 164 is itself a badline
exactly when YSCROLL is 4** — and only then.

### 2.4 How late, and where the write lands

Distribution of the last batch-mask write position (line·63+cycle; deadline
10387), Mode C 200f:

| fine | n | min | median | max | verdict |
|---|---|---|---|---|---|
| 0 | 26 | 10325 | 10343 | 10348 | safe |
| 1 | 28 | 10343 | 10348 | 10350 | safe |
| 2 | 25 | 10325 | 10348 | 10350 | safe |
| 3 | 24 | 10343 | 10348 | 10352 | safe |
| **4** | **24** | **10322** | **10388** | **10412** | **splits across the deadline** |
| 5 | 24 | 10326 | 10350 | 10354 | safe |
| 6 | 24 | 10326 | 10350 | 10355 | safe |
| 7 | 24 | 10325 | 10348 | 10354 | safe |

Seven of the eight phases are a tight band ending by 10355 — **30–32 cycles of
slack**. At fine==4 the distribution splits: the frames that finish on line 163
(≤10346) survive; everything else is thrown past the deadline.

Lateness distribution over the 600-frame run (n=53): **1 cycle ×35 (66%), 21
cycles ×17, 25 cycles ×1**. The landing positions are `164:56`, `165:13`,
`165:17`. Cycle 56 of line 164 is the *first cycle the CPU gets back* after a
badline's stolen cycles (~12–54) — the textbook signature of "resumed the instant
the badline released the bus".

(Aside: under `--dense` the main loop cannot complete inside one frame —
`gameplayPresented` traces 101 times per 200 frames — which is why `replay 99`
and the 32-frame coarse cycle. This is a property of the fixture's load, and is
identical in all three modes.)

---

## 3. Objective 4 — the falsifiable experiment

If the mechanism is "the deadline line is a badline when `deadline_line & 7 ==
YSCROLL`", then moving the bottom-most sprite from Y=164 to Y=165 must move the
vulnerable phase from 4 to 5, with an otherwise unchanged miss rate.

A scratchpad-only copy of `tools/vice_scroll_test.py` was patched with a
`--dense-yshift` diagnostic option (the repository tool was **not** modified) and
Mode C `--dense` re-run with `+1`:

```
Mode C dense, object Y +1 (bottom sprite Y = 165), 200 frames:
  sprite_start_miss_count 15   (was 16 at Y=164)
  fine value on MISS frames:  {5: 15}     <-- PREDICTED 5, since 165 & 7 == 5
  rate 15/24 exposed = 62%    (was 16/24 = 67%)
  records e.g. [19,'mask','rasterBatchMasksApplied',15, 165, 165,56]
```

**Prediction confirmed exactly.** The vulnerable phase followed the deadline line,
the landing position followed it too (`165:56` — again the first cycle after that
line's badline), and the rate was unchanged. This isolates the cause to the
badline/deadline-line coincidence and to nothing else.

---

## 4. Objective 2 + 3 — attribution and measured cycle costs

### 4.1 The IRQ hot path is byte-identical between Mode B and Mode C

`applyLiveRasterBatch` assembles to the **same address and the same 86 bytes** in
both builds:

```
Mode B  applyLiveRasterBatch=$6287 .. $62dd  ad1ed02d8223f00320d51bae6163bdfa21186d3222a8187d0a228dab23be1a22b9c5229df807b9d5229d27d08a0aaab995229d00d0b9a5229d01d0ee5563c8ccab23d0d9ae6163bd79638d10d0bd69638d8223eeb221
Mode C  applyLiveRasterBatch=$6287 .. $62dd  ad1ed02d8223f00320d51bae6163bdfa21186d3222a8187d0a228dab23be1a22b9c5229df807b9d5229d27d08a0aaab995229d00d0b9a5229d01d0ee5563c8ccab23d0d9ae6163bd79638d10d0bd69638d8223eeb221
```

`HW_SPRITE_POINTER` is `$07f8` (`src/variables.asm:19`), so Mode B's
`sta HW_SPRITE_POINTER,x` and Mode C's self-modified `ssBatchPtrStore:
sta $07f8,x` are literally the same encoding `9D F8 07`. `STA abs,X` is 5 cycles
regardless of the operand and has no page-crossing penalty, so patching the high
byte to `$2B` at flip time costs nothing at run time either.

> **Measured cost of `ssBatchPtrStore` versus Mode B: 0 cycles.** The Stage 4F
> design goal holds exactly.

Per-assignment loop body = 61 cycles; the post-loop tail before the traced label
(`ldx`, `lda BATCH_X_MSB_MASK,x`, `sta $D010`, `lda BATCH_PLAYER_MASK,x`,
`sta PLAYER_HW_MASK`) = 20 cycles. Identical in both modes.

### 4.2 The chain has identical timing in all three modes

Last batch-mask write position at non-vulnerable phases:

| mode | n | median | max | slack to deadline |
|---|---|---|---|---|
| A (single screen, no Stage 4 at all) | 195 | **10348** | 10357 | 30 cy |
| B (double-buffered, reason 1 intact) | 195 | **10348** | 10355 | 32 cy |
| C (reason 1 relaxed) | 175 | **10348** | 10355 | 32 cy |

Identical medians to the cycle. **Mode C adds no measurable delay to the batch
service chain**, including relative to a build that has no second screen at all.

At fine==4: Mode A median **+22 cy late** (4/4 samples late), Mode B **+1 cy**,
Mode C **+1 cy**. Mode A — the shipped Stage-3 single-screen architecture — is
the worst affected of the three.

### 4.3 Mode-C-only work, measured, and why it cannot reach the deadline

| path | when it runs | cost | distance from the raster-164 deadline |
|---|---|---|---|
| `ssFlipMirrorPtrs` | every frame | **125 cy** (static count: `ldx#7` + 8×(`lda abs,x`+`sta abs,x`+`dex`+`bpl`) + `lda#1`+`sta`+`rts`) | — **shared with Mode B** since the Stage 4H repair made both modes use the one routine, so it contributes **nothing** to the B-vs-C delta |
| `$D018` publication | 18 of 600 frames | ~30 cy core | **measured at raster 32** (see below) — 132 lines ≈ 8,300 cy earlier |
| `ssBatchPtrStore` hi-byte patch | once per flip | 24 cy | same frame-top window |
| turret reconcile | once per flip | data-dependent, bounded by `TURRET_POOL` | completes before the `$D018` write, i.e. before raster 32 |
| incremental builder slice | main thread, cut off at raster 180 | ≤1 row/frame | main thread only — see below |

The `$D018` write position was **measured, not assumed**, by adding
`trace store d018 d018` to the scratchpad capture tool:

```
D018 writes traced (6 over 200 frames):
   raster 32:25  A=$AE      (page B)
   raster 32:40  A=$1E      (page A)
   ... alternating, all at raster 32
```

So the entire flip publication — mirror, turret reconcile, `$D018`, page toggle,
`ssBatchPtrStore` patch and counters — is complete by **raster 32**, comfortably
before the first badline at raster 48 (the Stage 4E design requirement) and
**132 raster lines (~8,300 CPU cycles) before the deadline it is accused of
missing**.

**Instrumentation neutrality check:** the run carrying the extra `$D018` trace
reported `sprite_start_miss_count: 16`, `service_failure_count: 0`,
`frame_cycle_deltas [19656]` — identical to the untraced run. The added
instrumentation did not perturb the measured timing.

### 4.4 Main-thread work cannot displace an IRQ by 40 cycles

`grep` over `src/main.asm` finds `sei`/`cli` only in `endGame` (interrupt
hardware teardown), a VIC-I/O banking window, and a two-instruction guard in
`swapRenderPlans`. **No Stage-4 path — publication, mirror, turret reconcile or
builder — masks interrupts.** The main thread can therefore delay a raster IRQ
only by ordinary interrupt latency, bounded by the longest legal NMOS instruction
(≤7 cycles).

That bound is decisive: the normal-case slack is **30–32 cycles**, so no
main-thread effect available to Mode C can consume it. Only the badline, which
steals **40–43 cycles**, exceeds the margin — and it does so by 8–13 cycles,
matching the observed 1–25 cycle lateness once the chain's own position within
line 164 is accounted for.

---

## 5. Complete causal chain

1. The `--dense` fixture places its bottom-most objects at **Y = 164**, so the
   final batch of the LIVE plan must be fully applied before raster **164, cycle
   55** (project deadline convention `y*63+55`).
2. In the normal case the chain completes at raster 163:56–164:23 — **30–32
   cycles of slack**. This is identical in Modes A, B and C (median 10348 in all
   three).
3. A VIC-II badline occurs on line R when `R & 7 == YSCROLL`. Since `164 & 7 ==
   4`, **line 164 is itself a badline exactly when `SCROLL_FINE == 4`**, and the
   VIC steals ~40–43 cycles of it (roughly cycles 12–54).
4. 40–43 stolen cycles exceed the 30–32 cycles of slack, so any part of the batch
   service not already finished cannot resume until cycle ~55 — landing at
   **164:56** (1 cycle late, 66% of cases) or slipping into **165:13/165:17**
   (21/25 cycles late).
5. Under `--dense`, reason 1 (`COARSE_DEFER_LIVE`) pins **both Mode A and Mode B**
   at `SCROLL_FINE == 7` for 173 of 200 frames — they reach the vulnerable
   fine==4 phase only 4 times, during the pre-pin startup transient. Mode C's
   Stage-4F reason-1 relaxation lets it **actually scroll**, so it cycles through
   all eight fine phases and visits fine==4 **24 times per 200 frames** (76 per
   600).
6. Per exposed frame the failure rate is the same everywhere — A 3/4 (75%),
   B 2/4 (50%), C 16/24 (67%), C-600 53/76 (70%). The totals differ **only**
   because the exposure counts differ by 6×.

> The "~14-miss gap" is therefore **the price of the scroller actually advancing**
> under sustained sprite-reuse pressure — not a cost the double-buffered
> architecture adds. The same misses appear in the single-screen Stage-3 build at
> the same or worse per-exposure rate during the brief window in which it, too,
> advances.

---

## 6. Objective 5 — is a bounded fix warranted?

The deficit is arithmetic: **40–43 cycles stolen vs 30–32 cycles of slack**, i.e.
about 10 cycles short, on one deadline, on one scroll phase.

| candidate | assessment |
|---|---|
| Schedule the final batch's compare raster earlier | This is sprite-multiplexer scheduling — an explicit do-not-reopen area, tuned across Stages 0–3, affecting **all** modes and fixtures. Under `--dense` the chain is already in catch-up mode (one IRQ entry at raster ~125 works through the backlog to ~164, `catchups 1393`), so moving compares earlier redistributes rather than removes contention. High risk, benefit only in synthetic stress. |
| Shorten the batch tail | The post-loop tail is only 20 cycles total. Even eliminating it entirely cannot cover a 40–43 cycle steal. |
| Suppress the badline (e.g. force a non-badline YSCROLL) | Would stop the scroller scrolling — that is the bug Stage 4F fixed. |
| Keep sprites off badline-aligned lines | A content property of a synthetic fixture, not an engine mechanism. |

None is both bounded and effective. More importantly, **this is not a Stage-4
regression to fix**: Mode A, the shipped single-screen baseline, exhibits the
identical phenomenon at an equal-or-worse per-exposure rate. Any "fix" would be a
re-tuning of the multiplexer's timing margin, in the one subsystem whose recent
history includes two measured regressions (Stage 4G's IRQ-hot-path dual-write
attempts at 139 and 368 misses, and its builder-tuning experiment that silently
stalled 199/235 before being caught).

Weighed against that: across **2,760 captured frames of supported gameplay in
this session alone** (idle, authored wave, stage wrap, 199/235, turret-playtest,
accelerated stress) Mode C records **zero** sprite-start misses. And in the dense
fixture itself, all 16 objects are assigned `blankSprite`
(`tools/vice_scroll_test.py:128`), so even a genuinely late register write has no
visible consequence there.

**Conclusion: no fix is justified.** The current behaviour should be accepted and
documented.

---

## 7. Mode C regression status (committed build `80d5b0461c070fe2`)

All fixtures re-run this session against the committed Mode C build:

| fixture | frames | replay | catchup | `[19656]` | service fail | incomplete | sprite-start miss | page A | page B |
|---|---|---|---|---|---|---|---|---|---|
| idle | 300 | 0 | 0 | ✅ | 0 | 0 | **0** | 156 | 144 |
| authored wave (seed 382) | 320 | 2 | 1 | ✅ | 0 | 0 | **0** | 144 | 176 |
| stage wrap (seed 12) | 340 | 5 | 1 | ✅ | 1 † | 0 | **0** | 161 | 179 |
| 199/235 (`--y199`) | 400 | 0 | 0 | ✅ | 0 | 0 | **0** | 212 | 188 |
| `--dense` | 200 | 99 | 1393 | ✅ | 0 | 0 | 16 ‡ | 104 | 96 |
| `--dense` (long) | 600 | 299 | 4193 | ✅ | 0 | 0 | 53 ‡ | 312 | 288 |
| turret-playtest | 500 | 0 | 0 | ✅ | 0 | 0 | **0** | 256 | 244 |
| accelerated stress | 500 | 0 | 0 | ✅ | 0 | 0 | **0** | 244 | 256 |

† The single stage-wrap service failure is the **known Stage-4G "Finding 2"
HUD-modeling caveat**, re-confirmed here: frame 131 is exactly the first page-B
frame after a flip, and the mismatch is confined to slots 4–7 (`HUD_SLOT_FIRST`
= 4) with the HUD placeholder values 188/189/190/191. The oracle models
`INITIAL_SPRITE + ASSIGN_SPRITE` but not HUD's separate pointer-write path. Not a
raster-service defect; unchanged by this stage.

‡ Analysed above: all at `SCROLL_FINE == 4`, all the final batch, 66% of them
exactly one cycle past a deliberately conservative deadline, on blank sprites.

Page-aware pointer oracle: active (`page_aware: true`) and functioning on every
Mode C capture. 199/235 advancement remains healthy (188 of 400 frames on page B,
0 replays).

**No source change was made, so all three baseline hashes are unchanged.**

---

## 8. Final questions

**1. Exactly what causes the extra Mode-C `--dense` sprite-start misses?**
A VIC-II badline landing on the deadline line. The dense fixture's bottom-most
sprites sit at Y=164; the final batch of the LIVE plan must complete by raster
164 cycle 55 and normally does so with 30–32 cycles to spare. When
`SCROLL_FINE == 4`, raster 164 satisfies the badline condition (`164 & 7 == 4`)
and the VIC steals ~40–43 cycles of that line — more than the available slack —
so the mask write resumes at the first cycle the badline releases (164:56) or
slips into line 165. Mode C simply reaches that scroll phase 6× more often than
Modes A and B, which reason 1 pins at fine==7 under this fixture.

**2. Are they concentrated on flip/publication frames or elsewhere?**
Elsewhere, and provably so: **0 of 53 misses fall on a publication frame, or
within ±4 frames of one.** They cluster at offset +16/+17/+19 after a
publication — the opposite phase of the 32-frame coarse cycle, which is precisely
where fine==4 falls.

**3. Which specific code path(s) account for the timing delta versus corrected
Mode B?**
**None.** `applyLiveRasterBatch` is byte-identical in both builds (same address,
same 86 bytes); `ssFlipMirrorPtrs` is now shared by both modes after the Stage 4H
repair; the flip publication is measured to complete at raster 32. The measured
batch-chain completion median is 10348 in Modes A, B *and* C. The delta is in
**exposure count**, not in any code path's cost.

**4. What is the measured cycle cost of those path(s)?**
`ssBatchPtrStore` vs Mode B's store: **0 cycles** (same `9D F8 07`, 5 cycles
either way, no page-crossing penalty on `STA abs,X`). `ssFlipMirrorPtrs`: **125
cycles/frame**, but charged to Mode B equally since Stage 4H. Flip publication:
`$D018` write measured at **raster 32**, ~30 cycles of core work plus a 24-cycle
`ssBatchPtrStore` patch, on 3% of frames, ~8,300 cycles before the deadline.
Main-thread interference on the IRQ is bounded by interrupt latency ≤7 cycles (no
`sei`/`cli` in any Stage-4 path) — insufficient to consume 30–32 cycles of slack.
The badline steals 40–43, which is sufficient, and is the only candidate that is.

**5. Why do replay/catchup stay 99/1393 in both modes while sprite-start misses
differ?**
Because replay and catchup measure *quantity of work* — main-thread frame
overrun and IRQ backlog servicing — which is set by the fixture's 16-object,
8-batch load and is identical in every mode (indeed identical to the cycle:
99/1393 in A, B and C). The scroll phase changes nothing about how much work
there is; it changes only *where the badlines fall relative to one particular
deadline*. A 40-cycle displacement is far too small to move frame-level replay
or catchup counts, but is exactly enough to cross a 30-cycle margin on the one
deadline that happens to sit on a badline-aligned raster line.

**6. Is the 16-vs-2/3 gap fixable with a bounded low-risk change?**
No. The deficit is ~10 cycles against a 40–43 cycle bus steal; the only lever
large enough is the sprite-multiplexer's batch scheduling, which is an explicit
do-not-reopen area, affects all modes and fixtures, and has a recent history of
regressions. The batch tail is only 20 cycles total, so micro-optimisation cannot
cover it.

**7. If yes, what change was proven?**
Not applicable — no change was made and none is recommended.

**8. If no, why should the current result be accepted?**
Because it is not a defect of the double-buffered scroller. The phenomenon is a
pre-existing property of the sprite multiplexer's timing margin under 16-object
load: Mode A, the shipped single-screen Stage-3 baseline with no second screen at
all, exhibits it at an equal-or-worse per-exposure rate (75% vs Mode C's 67–70%).
Mode C's higher total reflects only that it is the one mode able to scroll under
sustained pending-LIVE pressure — the capability Stage 4F was built to deliver.
The misses are confined to a deliberately pathological synthetic fixture whose
sprites are blank, 66% of them are a single cycle past a conservative deadline,
and supported gameplay records zero misses across 2,760 captured frames.

**9. Is Mode C now ready to become the normal scrolling architecture?**
Yes, on this evidence. Exact PAL cadence `[19656]` holds everywhere, incomplete
frames are zero everywhere, assignment service is correct everywhere, the
page-aware pointer oracle passes, 199/235 advances healthily, and every supported
fixture is clean. Two disclosed caveats remain, both documented and neither a
service defect: the HUD-modeling oracle gap on flip-transition frames (Stage 4G
Finding 2, reproduced here at wrap frame 131), and the Mode-B-only two-frame LIVE
batch pointer staleness from Stage 4H — which **Mode C does not have**, because
its self-modified batch store keeps the active page current mid-frame.

**10. Is it now appropriate to create a new final scrolling checkpoint/tag?**
Yes. `479bb32` contains the complete, pushed 4G+4H work; Stage 4I adds no source
change, so the current HEAD is a sound checkpoint. A new tag (e.g.
`stable-double-buffered-scroller-v2`) should be created on `479bb32` or on a
later commit that adds this report. `stable-double-buffered-scroller` must stay
where it is, as the archaeological record of the original defect-carrying Stage
4D+4E implementation. **I did not create any tag.**

**11. What should the project do next after this task?**
The scrolling investigation is complete; no further scroller analysis is
warranted. Suggested order:
1. Tag the checkpoint (user action).
2. A small, bounded task to make Mode C the **default build** — flip the four
   `#define`s on, re-verify the regression suite, and update the memory-map /
   architecture docs. This is the last step to "normal architecture" and is
   low-risk since the toggles are already proven.
3. Optionally, a tool-side-only task to teach `check_raster_capture.py` about the
   HUD pointer-write path so the wrap fixture reports a true zero (removes the
   last disclosed caveat; no C64 code involved).
4. Return to gameplay/UI work.

---

## 9. Method notes and instrumentation

- **No C64 source instrumentation was added.** All Objective 1–3 evidence came
  from the existing trace labels already emitted by `tools/vice_scroll_test.py`
  (`gameplayPresented`, `armFirstBatch`, `rasterBatchMasksApplied`,
  `rasterAssignmentApplied`, `multiplexIRQ`, …), the per-frame `.actpage` byte
  added in Stage 4G, and the `physical_fine` value the capture already records.
- Two tool-side additions were made **in scratchpad copies only**, leaving
  `tools/` untouched: a `--dense-yshift` diagnostic option (for the falsifiable
  §3 experiment) and a `trace store d018 d018` tracepoint (to measure the
  publication raster). The repository working tree is clean.
- Instrumentation neutrality was verified: the `$D018`-traced run reproduced the
  untraced run's miss count, service failures and cadence exactly.
- Analysis scripts (`s4i_timeline.py`, `s4i_correlate.py`, a cap-removed copy of
  `check_raster_capture.py`) live in the session scratchpad, not the repository.
