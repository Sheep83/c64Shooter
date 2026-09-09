# Stage 4G — Finish Pending-LIVE Double-Buffered Scroller

Branch `experimental-border-hud`. HEAD at start `cd24b8c` ("Allow coarse scroll
during pending LIVE batches" = Stage 4F, on top of tag
`stable-double-buffered-scroller` = Stage 4D+4E, `931dca1`). Clean tree at
start. **No commit / stage / tag / push performed.** Working tree left with
`git diff --stat`:

```
 src/main.asm                  | 31 +++++++++++++++++++++++++++----
 tools/check_raster_capture.py | 40 +++++++++++++++++++++++++++++++++++++---
 tools/vice_scroll_test.py     |  5 +++++
```

`src/main.asm`'s toggle block is left **commented (Mode A / OFF)**, matching
the Stage 4D/4E/4F convention — the four `OPT_SS_*` sub-stage `#define`s at
lines 147/159/165/173 are untouched text (all the new code lives inside
`#if OPT_SS_ALLOW_PENDING_LIVE_FLIP` blocks, invisible unless a build turns
that toggle on). `build/shooter.prg` is left at Mode A
(`f2abc225159e81bf…`).

## Verdict: **AMBER**

Objective A's mechanism is complete and correct, and along the way surfaced a
genuine, previously-undetected defect in the **already-tagged** Stage 4E
architecture (Mode B) — reported below, not fixed (out of Stage 4G's scope:
Mode B must stay bit-identical). Objective B's decisive 199/235 target is met
(and exceeded); its `--dense` target is not, and the investigation shows
*why* it can't be reached through builder scheduling alone without risking a
correctness regression — that regression was actually triggered and caught
during tuning, then reverted. Per the task's explicit instruction, GREEN is
not forced by weakening the target.

---

## Objective A — page-aware raster oracle

### Mechanism
- `tools/vice_scroll_test.py`: one new per-frame capture, `.actpage`
  — a 1-byte `bsave` of `BG_ACTIVE_PAGE` ($9900), gated on the symbol
  existing (so single-screen/Mode-A captures are unaffected and produce no
  new files). Page B's hardware sprite-pointer table ($2BF8-$2BFF) was
  *already* inside the existing `.bg` dump (`bsave 2920 2fff`); only the
  one selector byte was missing.
- `tools/check_raster_capture.py`: `page_aware = 'BG_ACTIVE_PAGE' in symbols`.
  When true and `.actpage`/`.bg` exist for a frame, the "final sprite
  pointers" check reads whichever table `BG_ACTIVE_PAGE` says is *actually
  live* that frame (page A `$07F8`, inside `.ram`, or page B `$2BF8`, inside
  `.bg`) instead of always reading page A. Failure records now also carry
  `table_name` + the actual/expected bytes for diagnosis. The result dict
  gains `page_aware`, `page_a_frames`, `page_b_frames`.
- No fixture-specific override, no bespoke manual step: a capture from any
  existing build (page-aware or not) runs through exactly the same script
  and check.

### Decisive proof (199/235, Mode C, 400 frames)
```
frames 400, replay 10→0*, service_failure_count 0, sprite_start_miss 0,
frame_cycle_deltas [19656], page_aware true, page_a_frames 212/216, page_b_frames 184/188
```
(*before/after Objective B's scheduling change — see below.) Old oracle on
this same fixture reported 198/400 false "final sprite pointers" failures
(Stage 4F report); the page-aware oracle reports **0**, in agreement with
Stage 4F's dedicated live probe (`s4f_ptr2.py`, 200/200 match at raster 300).
This is the fixture Objective A's decisive criterion targets, and it is met.

### Mode A regression check
200-frame idle capture on the Mode-A (`OPT_SECOND_SCREEN` off) build:
`page_aware: false` (no `BG_ACTIVE_PAGE` symbol — correct fallback to the
original page-A-only behaviour), `service_failure_count: 0`. No regression.

### Finding 1 — a real, pre-existing Mode B defect, newly exposed
Running the page-aware oracle against **Mode B** (Stage 4D+4E only,
`OPT_SS_ALLOW_PENDING_LIVE_FLIP` off — the code the tag
`stable-double-buffered-scroller` points at) on two baseline fixtures that
were previously reported "0 failures" under the old (page-A-only) oracle:

| fixture | frames | old oracle | new (page-aware) oracle |
|---|---|---|---|
| idle | 300 | 0 | **144** (= every page-B-active frame) |
| authored wave (seed 382) | 320 | 0 | **159** (= every page-B-active frame) |

Every failure is `final sprite pointers` against `page B $2BF8`, and in both
captures the failure count exactly equals `page_b_frames` — i.e. **100% of
Mode B's page-B-active frames fail**, not a handful. Sample record (frame 16,
idle): `actual=[0], expected=[144]`. This is not staleness (an old-but-once-
valid value) — the byte is a fixed `0`.

**Root cause (confirmed live, not just from the capture).** Mode B's
`ssFlipMirrorPtrs` (`src/main.asm:7420`, the `#else` branch used when
`OPT_SS_ALLOW_PENDING_LIVE_FLIP` is off) computes the destination page
address into `SS_FLIP_TMP_LO`/`SS_FLIP_TMP_HI` and then does
`sta (SS_FLIP_TMP_LO),y` — 6502 indirect-indexed addressing. **That
addressing mode requires the pointer to live in zero page**, but
`SS_FLIP_TMP_LO`/`HI` are ordinary bytes in the Stage-4 `$9900` block
(`$9B6A`/`$9B6B`), not zero page. KickAssembler silently accepts this and
emits the indirect-Y opcode against the pointer's *low byte only*:

```
.C:9c1b  A0 07       LDY #$07
.C:9c1d  B9 F8 07    LDA $07F8,Y
.C:9c20  91 6A       STA ($6A),Y        ; NOT ($9B6A),Y -- reads zero page $6A/$6B
.C:9c22  88          DEY
.C:9c23  10 F8       BPL $9C1D
```

At runtime this indirects through **zero-page `$006A`/`$006B`** —
unrelated, arbitrary memory (a live probe on a fresh Mode B build found
`$6A/$6B = $80/$C0`, i.e. the "mirror" write silently lands at `$C080`,
nowhere near either sprite-pointer table). Direct memory peeks confirm the
consequence: `$2BF8-$2BFF` is **never written by anything at runtime** in
Mode B; it permanently holds its Stage-4B boot-time deterministic init
pattern `00 00 FF FF FF FF 00 00` for the entire game, on every page-B-active
frame, in every capture taken.

**Impact.** Whenever Mode B's `$D018` flip makes page B the displayed page,
the VIC-II reads its 8 live hardware sprite pointers from `$2BF8-$2BFF` —
which hold this fixed init pattern, not the frame's actual sprite-block
indices. Any sprite whose correct pointer differs from that pattern displays
the **wrong graphic** while page B is active. This is a real, user-visible
defect, present in Stage 4E's design since it was written, in the code the
annotated recovery tag `stable-double-buffered-scroller` points at.

**Why every previous proof missed it.**
1. The Stage 4E/4F oracle (`check_raster_capture.py`) only ever read page A's
   `$07F8` table — it never inspected `$2BF8` at all, in any mode.
2. Stage 4E's matrix/turret equivalence proofs check character-cell and
   colour-RAM content, not sprite-pointer tables.
3. The one live sprite-pointer proof that exists (Stage 4F's `s4f_ptr2.py`,
   200/200 match) was run specifically against the **new** 4F mirror
   (`OPT_SS_ALLOW_PENDING_LIVE_FLIP`'s plain `lda $07f8,x / sta $2bf8,x`
   loop — correct absolute,X addressing, no zero-page requirement, verified
   unaffected by this bug), not against Mode B's old `#else` branch. Nothing
   ever exercised Mode B's mirror with an instrumented check.

**Disposition.** Per Stage 4G's scope ("Mode A and Mode B must remain
bit-identical… do not replace the [pointer] mechanism unless you find a
concrete correctness defect — if you do, stop and report before broad
redesign"), **Mode B's source was not touched.** `git diff src/main.asm`
touches only code inside `#if OPT_SS_ALLOW_PENDING_LIVE_FLIP`; Mode A and
Mode B were rebuilt and reconfirmed byte-identical to their reported hashes
after every edit in this session (final check below). This is reported as a
newly-discovered latent defect in the committed/tagged Stage 4E code for the
user to decide on — see Recommendation.

### Finding 2 — a small, bounded, disclosed oracle/HUD-modeling gap (Mode C)
The page-aware oracle also surfaced 2 failures out of 340 frames on the
stage-wrap fixture (Mode C, i.e. *with* the Stage 4F fix):

```
[82,  'final sprite pointers', 'page B $2BF8', actual=[152,193,151,153,188,189,190], expected=[152,193,151,153,194,144,155]]
[147, 'final sprite pointers', 'page B $2BF8', actual=[216,153,194,197,188,189,190], expected=[216,153,194,197,198,153,144]]
```
Both are confirmed (via `.actpage` across neighbouring frames) to be the
**exact first frame** a `$D018` flip makes page B active. Both mismatches
are confined to sprite slots 4-6 — exactly `HUD_SLOT_FIRST..+2`
(`HUD_SLOT_FIRST = 4`, HUD owns slots 4-7); slots 0-3 (gameplay-owned) match
every time. `sprite_start_miss_count = 0` and the assignment-service check
passes on both frames — this is **not** a raster-service defect (every
scheduled assignment still completes in its physical frame at exact `[19656]`
cadence). It is a gap in what the oracle's "expected pointers" formula
models: `INITIAL_SPRITE` (render plan) + `ASSIGN_SPRITE` (LIVE batch
reassignment) — it has no visibility into HUD's separate pointer-write path
(`hudBorderSetup`/`hudBorderHandoff`), which is explicit non-scope for Stage
4G (HUD architecture). It self-corrects by the very next frame in every case
observed, and did not appear on the 199/235 fixture (the one Objective A's
decisive criterion targets) or on idle/wave. Documented here in the same
spirit as the pre-existing "initial snapshot trace" / RSEL=1 oracle caveats
from Stage 4D/4E, rather than pursued further (would require reasoning about
HUD slot-ownership timing, out of scope).

### Objective A verdict: **substantially GREEN**, two disclosed findings
The mechanism itself does exactly what was asked — general, non-fixture-
specific, agrees with the 4F 200/200 proof, correct fallback on Mode A — and
paid for itself by finding a real bug. Neither finding blocks Objective A's
own goal; both are reported per scope rather than fixed/chased further.

---

## Objective B — bound the incremental inactive-page builder's load

### Baseline (this session, Mode C `d3ba25a9…`, before any Objective B change)
| fixture | frames | replay | catchup | `[19656]` | service_fail | sprite_start_miss |
|---|---|---|---|---|---|---|
| stage wrap (seed 12) | 340 | 4 | 1 | yes | 2 (Finding 2, HUD-slot) | 0 |
| 199/235 (`--y199`) | 400 | 10 | 0 | yes | 0 | 0 |
| `--dense` | 200 | 99 | 1393 | yes | 0 | **17** |

Targets (Section 8): 199/235 replay ≤ stage-wrap baseline (4/340, ~1.2%);
`--dense` sprite-start-miss ≤ 3 (Mode B baseline).

### Experiments (smallest-change-first, all `#if OPT_SS_ALLOW_PENDING_LIVE_FLIP`-gated, Mode C exclusive)
Three scheduling-only knobs were added, each shadowing the existing Stage
4D/4E value only under the PLF toggle (Mode A/B keep the original values and
are bit-identical throughout): `SS_PLF_BUILD_SLICE_ROWS` (rows/slice, base
2), `SS_PLF_SLICE_RASTER_CUTOFF` (raster budget guard, base 220),
`SS_PLF_FLIP_HOLDOFF_FRAMES` (post-flip settle frames, base 1).

| trial | rows | cutoff | holdoff | dense miss | dense replay/catchup | 199/235 replay | 199/235 page_b_frames |
|---|---|---|---|---|---|---|---|
| baseline | 2 | 220 | 1 | 17 | 99 / 1393 | 10 | 184/400 |
| v1 (conservative) | 1 | 200 | 2 | 17 (no change) | 99 / 1393 | 10 | 184/400 |
| v2 (aggressive) | 1 | 140 | 4 | 15 | 99 / 1393 | **0/400 — stalled** | **0** |
| v3 (extreme, ceiling probe) | 1 | 100 | 8 | 18 (worse) | 99 / 1393 | — | — |
| v4 (kept) | 1 | 180 | 3 | **16** | 99 / 1393 | 0 (better) | 188/400 |
| v5 (boundary probe) | 1 | 160 | 3 | 16 | 99 / 1393 | **0/400 — stalled** | **0** |

Three things this table establishes:
1. **`replay_frames`/`catchups` on `--dense` (99/1393) never moved, across
   every trial from the mildest to the most extreme.** This is strong
   evidence the incremental builder's per-frame slice cost is *not* the
   dominant contributor to `--dense`'s replay/catchup pressure — something
   else (raw 16-object/8-batch sprite-mux contention, or the reason-1-bypass
   path's own fixed per-flip cost — turret reconcile, the `ssBatchPtrStore`
   self-modify, the mandatory every-frame `ssFlipMirrorPtrs` mirror) is.
   `sprite_start_miss_count` shows only small, **non-monotonic** movement
   (17→15→18 across increasing aggressiveness) — consistent with a metric
   dominated by something the builder throttle only touches at the margin.
2. **v2 caused a real correctness regression, caught by re-running the
   decisive 199/235 fixture, not assumed safe.** With cutoff tightened to
   140 (holdoff 4), 199/235's `page_b_frames` fell from 184/400 to **0/400**
   — the coarse scroll stopped progressing entirely, the same permanently-
   pinned symptom Stage 4F was written to fix. Cause: the builder no longer
   finishes a 24-row rebuild within a coarse cycle under 199/235's
   back-to-back admission cadence, so `ssFlipPrereqOK` never finds
   `SS_BUILD_STATE==2`/`SS_INACTIVE_VALID`; every admission takes
   `SS_PLF_TAG_DEFER` (4F's deliberate "never run the legacy in-window
   mutation with a pending batch" safety) instead of publishing. **This was
   reverted before being kept** — v2/v3 were never left as the final state.
3. **The safe margin is narrow.** v4 (cutoff 180) preserves 199/235
   advancement with a small dense improvement; v5 (cutoff 160 — 20 less)
   already reproduces the v2 stall (`page_b_frames: 0`). This is a sharp
   cliff, not a smooth trade-off curve — consistent with (1): there isn't
   much genuine slack to trade away in the builder's own budget before it
   stops finishing on time, and what slack exists barely moves the target
   metric.

### Kept change
```asm
#if OPT_SS_ALLOW_PENDING_LIVE_FLIP
.const SS_PLF_BUILD_SLICE_ROWS     = 1
.const SS_PLF_SLICE_RASTER_CUTOFF  = 180
.const SS_PLF_FLIP_HOLDOFF_FRAMES  = 3
#endif
```
applied at the three sites that read the base constants/init values
(`ssInactiveBuildReset`'s `SS_BUILD_SLICE_ROWS` init, `ssInactiveBuildSlice`'s
raster-budget compare, `ssPublishCoarseFlip`'s `SS_FLIP_HOLDOFF` store) —
each shadowed only inside the PLF `#if`, base branch text unchanged.
Mode C hash: `80d5b0461c070fe2…` (changed from 4F's `d3ba25a9…`, as expected
— the schedule differs). **Mode A (`f2abc225159e81bf…`) and Mode B
(`98eb5bbbc2fb385e…`) reconfirmed byte-identical** after this and every
intermediate edit in this session.

### Target evaluation
- **199/235 replay ≤ stage-wrap baseline: MET (exceeded).** Final: 0/400
  replay frames, `page_b_frames` 188/400 (full, healthy advancement — even
  better than the pre-tuning 10/400). Stage-wrap baseline for comparison:
  4/340.
- **`--dense` sprite-start-miss ≤ 3: NOT MET.** Final: **16** (from a
  baseline of 17 — a genuine but small, 1-miss improvement). The evidence in
  the experiment table above indicates the remaining gap is not addressable
  through incremental-builder scheduling changes without reproducing the
  v2/v5 correctness regression; closing it further would mean touching the
  per-flip fixed-cost mechanism itself (turret reconcile, the pointer
  mirror/self-modify, or raw batch/reuse contention) — outside "scheduling
  changes to the builder" and squarely the kind of broad redesign Stage 4G's
  Section 4 says to stop and report on rather than pursue unilaterally.

### Objective B verdict: **partial — one target met, one not, root cause identified**
Per the task's explicit instruction ("if this cannot be achieved with
bounded scheduling changes, report the best measured result and stop before
architectural redesign"), this is where Objective B stops.

---

## Full regression suite (final build, Mode C `80d5b0461c070fe2…`)

| fixture | frames | replay | catchup | `[19656]` | service_fail | sprite_start_miss | page_a | page_b |
|---|---|---|---|---|---|---|---|---|
| idle | 300 | 0 | 0 | yes | 0 | 0 | 156 | 144 |
| authored wave (seed 382) | 320 | 2 | 0 | yes | 0 | 0 | 144 | 176 |
| stage wrap (seed 12) | 340 | 5 | 1 | yes | 1 (Finding 2, same frame 82 signature) | 0 | 161 | 179 |
| 199/235 (`--y199`) | 400 | 0 | 0 | yes | 0 | 0 | 212 | 188 |
| `--dense` | 200 | 99 | 1393 | yes | 0 | 16 | 104 | 96 |
| turret-playtest (repeated A↔B flips incl. alive/destroyed-before-publish) | 500 | 0 | 0 | yes | 0 | 0 | 256 | 244 |
| accelerated natural gameplay (`--stress`) | 500 | 0 | 0 | yes | 0 | 0 | 272 | 228 |

Every capture holds the exact PAL cadence `frame_cycle_deltas == [19656]`.
Assignment-service (`RASTER_EXPECTED_ASSIGNMENTS == done`,
`RASTER_INCOMPLETE_FRAMES == 0`) and physical epoch/trace checks pass on
every frame of every capture. The sole remaining `service_failure` (stage
wrap, 1 vs the pre-tuning session's 2 — same frame-82 HUD-slot signature) is
Finding 2 above, unrelated to Objective B's scheduling change.

## Toggle / baseline preservation (final)
| mode | toggles | hash | status |
|---|---|---|---|
| A | `OPT_SECOND_SCREEN` off | `f2abc225159e81bf…` | **bit-identical**, reconfirmed after every edit |
| B | 4D+4E only, PLF off | `98eb5bbbc2fb385e…` | **bit-identical**, reconfirmed after every edit (= tag `stable-double-buffered-scroller`) |
| C | 4D+4E+4F+4G | `80d5b0461c070fe2…` | changed from 4F's `d3ba25a996c348df…` — expected, scheduling-only change under `OPT_SS_ALLOW_PENDING_LIVE_FLIP` |

Reasons 2/3 (`VIC_CONTROL_1` bit7 badline defer; `bgCoarseReason3Defer` /
`RASTER >= BG_COARSE_LATEST_START`) were not touched at all this stage — no
source line inside either gate was read or edited.

## Areas explicitly not touched
Soft-edge masking, RSEL1 experiment, HUD architecture/art (Finding 2 is
diagnosed, not fixed, and does not touch HUD code), player artwork/movement,
weapons/overheat/laser experiments, collision architecture, object limit,
wave/editor contract, stage-package ABI, sprite asset map, `$2000-$23FF`
reclamation, VIC-bank art layout, gameplay state machine, docking/upgrade
screen, multiload/stage loader.

## Memory
`$9900` Stage-4 block now `$9900-$9de1` region unchanged in size (only
`.const` and immediate-operand additions, no new runtime bytes beyond the
constants already accounted for by KickAssembler as immediates — no new
`.byte`/`.word` storage was added). No new C64-side diagnostics were added;
all Objective A/B investigation used tool-side (Python) capture/analysis and
targeted live VICE-monitor probes (disassembly + direct memory peeks),
consistent with the ~500-byte headroom constraint below `$A000`.

## Recommendation
1. **Do not tag this session's work.** Objective B's target is not fully met,
   and Finding 1 (the Mode B `$2BF8` zero-page-addressing bug) is a real
   defect in the **already-tagged** `stable-double-buffered-scroller`
   checkpoint that the user should be aware of before relying on Mode B
   (4D+4E without 4F) in any context where page B is actually displayed —
   whether or not this session's changes are kept.
2. Should the double-buffered scroller become the normal architecture with
   legacy reason-1 as compile-time fallback? **Not yet, as Mode B stands.**
   Mode C (4D+4E+4F+4G) is the only variant proven end-to-end (matrix
   equivalence, turret reconcile, sprite-pointer coherence including the
   4F self-modified-store fix, exact PAL cadence, bounded builder load on
   the previously-frozen scenes) — it is a reasonable candidate. Mode B
   specifically should not be treated as safe to ship or fall back to
   as-is because of Finding 1.
3. Suggested next-smallest step, if this work continues: fix Finding 1
   (move `SS_FLIP_TMP_LO`/`HI` to true zero page, or replace the
   indirect-indexed store in Mode B's `ssFlipMirrorPtrs` `#else` branch with
   the same absolute,X-indexed loop the 4F branch already uses — cheap,
   mechanical, and would very likely change Mode B's hash, which is why it
   was not done unilaterally here) as its own small, explicit task, then
   revisit whether Mode B's now-corrected baseline changes any Objective B
   conclusions.
4. Investigate `--dense`'s fixed per-flip cost as a separate, explicitly
   scoped follow-up if closing the sprite-start-miss gap further is a
   priority — the evidence here points at the pointer-mirror/self-modify
   and turret-reconcile machinery (or raw batch/reuse contention), not the
   builder, as the next place to look.
