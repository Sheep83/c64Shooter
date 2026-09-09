# Historical Scroll Hitch — Phase B(b): Page-Aware Legacy Fallback

**Verdict: GREEN**, with two pre-existing artifacts disclosed and separately
characterised (neither introduced by this change, neither fixed here).

Across 13 captures: **0 seven-pixel snaps, 0 duplicated turrets, 0 fallback
refusals, longest terrain stall back to the 2-frame baseline** (B(a) reached 36).
Exact PAL held on all seven regression fixtures; 0 sprite-start misses including
`--dense`; Stage-5 aperture unchanged.

Branch `main`, HEAD `d60828a`. Nothing committed, staged, tagged or pushed.

---

## 1. Correction to the Phase B(a) report

B(a) recommended B(b) and estimated the duplication at "~1 KB, cycle-neutral".
**That estimate was wrong.** The real unrolled routines are:

| routine | bytes | cycles |
|---|---|---|
| `shiftBackgroundUpper` | 2,881 | 3,840 |
| `shiftBackgroundLower` | 2,641 | 3,520 |
| `saveCrossingRow` | 241 | 320 |
| `restoreCrossingRow` | 241 | 320 |
| **total to mirror** | **6,004** | |

A mirrored copy does not fit. The only clean gap is `$6600..$87ff` (6,638 bytes)
and it must also hold the level's stage tables — a full-budget 10×400 stage needs
roughly 5 KB of that. `$a000..$bfff` is BASIC ROM and the program never writes
`$01`, so that RAM is unreachable without a banking change I judged out of scope.

So the mirror strategy was not viable and I used a different one (§2).

---

## 2. Implementation

The page-A routines are **untouched** — verified byte-identical between the B(a)
and B(b) binaries at `$4000`, `$4b41`, `$5592`, `$5683`. All historical page-A
timing and layout is preserved exactly.

Page B gets compact counterparts. Both shifts move a contiguous block down by one
row (`dst = src + 40`), so page B is expressed as an indexed block move rather
than 2,881 bytes of mirrored absolute pairs. Indexed addressing costs at minimum
9 cycles/byte (`lda abs,x` 4 + `sta abs,x` 5) against page A's 8, so the loops are
unrolled 8-deep to amortise the index arithmetic to ~10.4 cycles/byte.

```asm
.macro ssShiftChunkB(src, len) {
        ldx #len - 8
    !c: .for (var k = 7; k >= 0; k--) {
            lda BG_SCREEN_B + src + k, x
            sta BG_SCREEN_B + src + 40 + k, x
        }
        txa / sec / sbc #8 / tax
        bcs !c-
}
shiftBackgroundUpperB:  ssShiftChunkB(240, 240) ; ssShiftChunkB(0, 240)   ; rts
shiftBackgroundLowerB:  ssShiftChunkB(760, 200) ; ssShiftChunkB(520, 240) ; rts
```

Chunks are emitted **highest-first** and `X` descends within each, so the whole
traversal is strictly top-down — mandatory, since `dst` overlaps `src` by 200
bytes and an ascending pass would clobber unread source bytes.

Two further routines were page-blind and are now page-aware (2 instructions each,
`#if OPT_SECOND_SCREEN`): `copyIncomingRowToScreen` and the predecode hit path in
`bgConsumePredecodedRow`, which both built `TEXT_DST` from the page-A-only
`starRowLo/Hi` tables. Without this the legacy path's row-0 write still landed on
page A. `installTurretRow` already used the caller's `TEXT_DST` and needed no change.

**Placement:** `LEGACY_PAGEB_SEGMENT = $8640`, occupying `$8640..$873d` (254
bytes) at the **top** of the `$6600..$87ff` region so stage tables keep maximum
headroom (6,184 bytes remain). Two `.error` guards: stage data must not reach
`LEGACY_PAGEB_SEGMENT`, and the block must not reach `$8800`.

**Dispatch:** the gate latches `BG_ACTIVE_PAGE` into `SS_LEGACY_PAGE`; both the
upper half and the next frame's lower half branch on that latch, so the two halves
can never disagree about which page they are shifting.

---

## 3. Cycle cost, page A vs page B

| phase | page A | page B | delta |
|---|---|---|---|
| upper (`saveCrossingRow*` + `shiftBackgroundUpper*`) | 4,160 | ~5,550 | +1,390 (+33%) |
| lower (`shiftBackgroundLower*` + `restoreCrossingRow*`) | 3,840 | ~5,130 | +1,290 (+34%) |
| dispatch | — | ~5 cycles per half | negligible |

Nothing was added to the sprite-batch hot path. Measured rasters:

| | shift start | upperCopied | upperReady | next frame: lower start | lowerReady |
|---|---|---|---|---|---|
| page A | 165–192 | 233–270 | 262–289 | 23–25 | 106–110 |
| page B | 170–189 | 272–291 | 286–307 | 23–24 | **137–138** |

The operative deadlines are (a) row 0 must be written before the *next* frame's
row-0 fetch at raster ~48 — worst observed 307, so ~53 lines of margin; and (b)
the lower half must finish before row 13 is fetched at raster ~152 (the code
comments say 160) — worst observed 138, so **14–22 lines of margin**. Positive on
every event, but this is the tightest number in the change and is the thing to
re-measure if the fallback ever gets slower.

---

## 4. Results on the known-bad seeds (420 frames, mask-OFF, like-for-like)

| seed | attempts | exec A | exec B | refused | max refusal streak | 7px snaps | max stall | dup turrets |
|---|---|---|---|---|---|---|---|---|
| 352 | 2 | 0 | 2 | 0 | 0 | **0** | 2 | **0** |
| 360 | 3 | 2 | 1 | 0 | 0 | **0** | 2 | **0** |
| 340 | 5 | 4 | 1 | 0 | 0 | **0** | 2 | **0** |
| 232 | 2 | 0 | 2 | 0 | 0 | **0** | 2 | **0** |
| 124 | 4 | 1 | 3 | 0 | 0 | **0** | 2 | **0** |
| 112 | 2 | 1 | 1 | 0 | 0 | **0** | 3 | **0** |
| 224 (control) | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |

Long sweep (seeds 300/280/260/200/180/150, 500 frames): 14 attempts, 6 page-A,
8 page-B, **0 refused, 0 snaps, 0 duplications, max stall 2**.

**Aggregate over 13 captures: 32 attempts = 14 page-A + 18 page-B + 0 refusals.**
The counter invariant `SS_FLIP_FALLBACK == COARSE_PATH_COUNT + PAGEB_EXEC +
PAGEB_BLOCK` holds exactly in every capture.

Attempt counts collapse from B(a)'s 88 to 32 because a completed coarse step ends
the retry storm that unbounded deferral created.

### Stall comparison (longest run of frames with no terrain motion; 2 = baseline)

| build | 352 | 360 | 340 | 232 | 124 | 112 |
|---|---|---|---|---|---|---|
| pre-Stage-4 Mode A | 2 | 2 | 2 | 2 | 2 | 2 |
| Stage 4J (unpatched) | 2 | 2 | 2 | 2 | 2 | 3 |
| Phase B(a) | 21 | 7 | **36** | 12 | 4 | 3 |
| **Phase B(b)** | **2** | **2** | **2** | **2** | **2** | **3** |

### Page coherence

Turret body row versus the `rel+1` mapping implied by `SCROLL_ROW`, restricted to
unambiguous fully-on-screen turrets:

| build | canonical `rel+1` | `rel+0` | out of range |
|---|---|---|---|
| Stage 4J unpatched | 190–406 | **83–285** (sustained desync) | 3–28 |
| Phase B(a) | 207–395 | 12–26 (one per coarse step: the pre-flip transient) | 0 |
| **Phase B(b)** | 180–423 | 9–29 (same transient) | 0 † |

† after the fix in §5. `SCROLL_ROW` stays aligned with the visible matrix on every
frame of every B(b) capture.

---

## 5. A real bug this work found and fixed mid-flight

The **first** B(b) implementation used a simple `dex/bpl` loop at 14 cycles/byte.
It was too slow: `bgUpperCopied` landed at raster **297–311** and `bgUpperReady`
frequently did not fire inside the frame at all — the coarse step's bookkeeping
spilled past the frame boundary. The capture caught it as a turret sitting one row
too low (delta `+2`) on 5 of 9 page-B executions, with `SCROLL_ROW` not yet
decremented at the raster-311 sample point.

Page-A executions never showed it; only page B did. The 8-deep unroll (10.4
cycles/byte) moved `upperCopied` back to 272–291 and the signature disappeared
completely. This is exactly the class of defect §12 predicted — a late row-0 write
is a top-of-background corruption — and it is worth recording that a naive compact
page-B implementation reintroduces it.

---

## 6. The two user-observed residual artifacts

Per §14 these are tracked as **separate** signatures, not folded into one counter.

### A. Top-of-background corruption / flicker — *partly explained, residual disclosed*

Two distinct findings:

1. **The B(b)-specific one is fixed** (§5). A late row-0 write is precisely a
   corrupt top row, and the first implementation produced it on most page-B
   fallbacks. The shipped implementation does not.
2. **A pre-existing signature remains.** Oracle: visible row 0 at frame *N* must
   become row 1 at the next coarse advance.

   | build | row0→row1 OK | mismatch |
   |---|---|---|
   | Stage 4J unpatched | 17–21 | 2–3 per capture |
   | **Phase B(b)** | 18–23 | **1–2 per capture** |

   B(b) is equal-or-better, never worse. The mismatches recur at a ~128-frame
   period (frames 48, 113/114, 176, 241–244, 371), which points at the turret
   install / predecode interaction on row 0 rather than at the coarse path. **Not
   diagnosed further and not fixed** — it is a separate reproducible issue.

3. **A third, clearly separate defect found by machine:** dead turrets are never
   erased from page B. `src/background_turrets.asm` has no page awareness at all —
   `restoreDeadTurretRow` / `restoreDeadTurretCells` resolve through the page-A-only
   `starRowLo/Hi` tables — so a destroyed turret's body survives on page B.

   | build | dead-turret samples | body still VISIBLE | ghost on A | ghost on B |
   |---|---|---|---|---|
   | Stage 4J unpatched | 90 / 556 | 22 / 31 | 6 / 3 | **22 / 31** |
   | **Phase B(b)** | 90 / 557 | 22 / 31 | 2 / 3 | **22 / 31** |

   Identical before and after: **pre-existing, untouched by B(b)**. This is a
   strong candidate for part of what the user sees, since the ghost is present on
   one page and absent on the other.

### B. Occasional single-enemy sprite flicker — *machine signature found, correlates with the known race*

The only sprite anomalies detected anywhere in the suite are sprite-pointer
service failures, and every one is on **page B `$2BF8` at a flip transition**:

```
wrap frame  82: page B $2BF8  expected [...,188,189,190]  hardware [...,194,144,155]
wrap frame  88: page B $2BF8  expected [...,194,144]      hardware [...,155,144]
wrap frame 165: page B $2BF8  expected [...,188]          hardware [...,144]
```

That is exactly the **`ssFlipMirrorPtrs`-after-a-LIVE-batch race** documented in
the Fable review (frame 88 is the known instance). Counts: pre-patch baseline 3,
B(a) 2, B(b) 3 — run-to-run variance around the same pre-existing defect, not a
B(b) regression. A wrong pointer on the page about to become active shows as one
sprite briefly drawing the wrong shape, which matches the report.

Per §13 I did **not** fix it. Precise next step: order `ssFlipMirrorPtrs` so it
cannot run after a LIVE pointer write on a late main-thread frame — either move
the mirror ahead of the batch or re-mirror the affected slot after it. Bounded,
but it belongs in its own task with its own before/after on the wrap fixture.

Sprite-start misses are **0** in every fixture including `--dense`, so this is a
pointer-content race, not a multiplexer timing failure.

---

## 7. Regression suite (patched default build, mask ON, `234cdc065a2399ad`)

| fixture | frame deltas | svc fail | sprite-start miss | catchups | replay | page A / B |
|---|---|---|---|---|---|---|
| idle 300 | `[19656]` | 0 | 0 | 0 | 0 | 156 / 144 |
| wave 320 (seed 382) | `[19656]` | 0 | 0 | 0 | 0 | 178 / 142 |
| wrap 340 (seed 12) | `[19656]` | 3 † | 0 | 2 | 5 | 180 / 160 |
| y199 400 | `[19656]` | 0 | 0 | 0 | 0 | 211 / 189 |
| dense 200 | `[19656]` | 0 | **0** | 1386 | 100 | 104 / 96 |
| turret 500 | `[19656]` | 0 | 0 | 0 | 0 | 260 / 240 |
| stress 500 | `[19656]` | 0 | 0 | 0 | 0 | 272 / 228 |

† the three page-B pointer-race failures of §6B; the pre-patch baseline for this
fixture is also 3. `--dense` catchups/replay 1386/100 are **identical** to the
pre-patch baseline — mux timing is unaffected.

**Exact PAL 19,656 cycles/frame on every fixture.**

Stage-5 protections: aperture fixed **58..247 on 130/130 frames** for wave, wrap,
dense, turret and stress — unchanged. Live probe of the title screen:
`$D011=$9b`, **ECM=0**, YSCROLL=3, `GAME_STATE=0`, 16 starfield glyphs — matches
the accepted Stage 5B checkpoint. Gameplay probe: `GAME_STATE=1`, **ECM=1** band.

**Honest gap:** I could not drive the player's death through the monitor, so the
GAME OVER → TITLE half of the lifecycle was **not** re-verified this session. The
B(b) diff adds no `$D011` write and does not touch `endGame`, `startGame` or
`initRasterScheduler`, so the Stage-5B proof for those transitions still applies
to unchanged code — but that is an argument, not a fresh measurement. Worth one
manual check.

---

## 8. Binary identity

| build | hash | note |
|---|---|---|
| Mode A (single screen) | `f2abc225159e81bf` | **byte-identical** to the `stable-single-screen-scroller` tag — the whole of B(b) is inside `#if OPT_SS_FLIP_COARSE` |
| B(b) default (mask ON) | `234cdc065a2399ad` | |
| B(b) mask-OFF | `34afc81039af0510` | |
| B(a) default (previous) | `e966903477a03a91` | |

The mask-OFF ↔ Stage-4J identity remains deliberately broken, as disclosed in the
B(a) report: this is an engine bug fix, compiled unconditionally in
double-buffered builds.

A build-time toggle `LEGACY_FALLBACK_PAGE_AWARE` (default ON) selects B(b);
switching it off restores exact B(a) refuse-and-defer behaviour for A/B testing.
The refuse-and-defer code stays compiled in either way as the out-of-range safety
net, so the engine can still never run a fallback against the wrong page.

---

## 9. Answers to the final questions

1. **How page-aware?** The gate latches `BG_ACTIVE_PAGE` into `SS_LEGACY_PAGE`;
   both halves of the coarse step branch on that latch to page-A or page-B routines.
2. **What was duplicated/altered?** Nothing duplicated. Four new compact page-B
   routines added; `copyIncomingRowToScreen` and `bgConsumePredecodedRow` made
   page-aware (2 instructions each); the B(a) gate reworked from refuse to dispatch.
3. **Page-A copy location?** Unchanged, `$4000` segment — verified byte-identical.
4. **Page-B copy location?** `$8640..$873d`, 254 bytes, `LEGACY_PAGEB_SEGMENT`.
5. **Cycles A vs B?** Upper 4,160 vs ~5,550 (+33%); lower 3,840 vs ~5,130 (+34%).
6. **Dispatch?** `lda SS_LEGACY_PAGE / beq` per half, ~5 cycles; nothing in the
   sprite hot path.
7. **Role of the B(a) guard?** Retained as the out-of-range safety net and as the
   whole behaviour when `LEGACY_FALLBACK_PAGE_AWARE` is off. It fired 0 times.
8. **Page-A legacy executions?** 14 across 13 captures.
9. **Page-B legacy executions?** 18.
10. **Fallback deferrals?** **0.**
11. **Max visual stall?** **2 frames** (3 on seed 112) — the baseline; B(a) reached 36.
12. **7 px snaps remaining?** **0.**
13. **Duplicated-turret signatures?** **0.**
14. **`SCROLL_ROW` aligned with the visible matrix?** Yes, every frame of every capture.
15. **Top-of-background corruption reproduce?** A B(b)-specific one did, from a
    too-slow first implementation, and is fixed (§5). A pre-existing row-0
    signature remains at 1–2 per capture (unpatched: 2–3).
16. **Correlates with?** The fixed one: page-B upper-shift duration pushing the
    row-0 write past the frame boundary. The residual: a ~128-frame periodic
    row-0 event, pointing at turret install / predecode, not the coarse path.
17. **Single-sprite flicker signature?** Yes — sprite-pointer service failures,
    all on page B `$2BF8` at flip transitions.
18. **Correlates with `ssFlipMirrorPtrs`?** Yes, cleanly, and it is pre-existing
    (baseline 3, B(b) 3). Not fixed; next step in §6B.
19. **Exact PAL?** Yes, `[19656]` on all seven fixtures.
20. **Dense/mux safe?** Yes — 0 sprite-start misses, catchups/replay identical to baseline.
21. **Stage-5 masking and starfield?** Aperture 58..247 on 130/130; title ECM=0
    with 16 star glyphs. GAME OVER → TITLE not re-measured (§7).
22. **Ready for visual acceptance?** Yes.
23. **What to inspect manually?** §10.
24. **Remaining blocker before committing?** None for the scrolling work itself.
    Two disclosed pre-existing defects (dead-turret ghost on page B; page-B
    sprite-pointer race) are independent of it and can be committed around.

---

## 10. Manual inspection checklist

Expected to be **gone**: the 7 px backward snap; the duplicated turret top half;
and B(a)'s occasional brief scroll stall — coarse steps now always complete, so
the fine-scroll cadence should be uniform.

Please look specifically for:

- repeated six-enemy waves, late-wave, with enemies climbing to the top edge —
  the terrain should scroll at a constant rate with no pause and no jump
- a turret near the lower edge during a coarse transition
- **a destroyed turret leaving its top half on screen** — a known page-B defect
  found here, expected to still be present
- **one enemy sprite briefly drawing the wrong shape** near a page flip — the
  known pointer race, expected to still be present
- Stage-5 top/bottom edge masking steady, no 8 px pop, no 50 Hz shimmer
- top-border HUD stable
- title / high-score starfield correct (smooth, no digit glyphs)
- one full TITLE → GAME → GAME OVER → TITLE cycle, since I could not
  automate the GAME OVER transition

---

## 11. Reproduction

```
scratchpad/run_hitch.sh <name> <port> <prg> <vs> --seed-scroll <S> --frames 420
```
Known-bad seeds 352, 360, 340, 232, 124, 112; control 224; long sweep 300, 280,
260, 200, 180, 150 at 500 frames.

Detectors: visible-freeze (fine 7→0 while ≥24/25 rows of the visible page are
unchanged); duplicated turret (adjacent row pair of 226,227 in a live turret's
column); visual stall (terrain rows 2..23 plus fine identical to previous frame);
page coherence (turret row vs `(T-SCROLL_ROW) mod SLR + 1`, unambiguous turrets
only); row0→row1 integrity; dead-turret ghost (body present at `rel+1` for a
health-0 slot); plus `tools/check_raster_capture.py` for PAL/mux/pointer oracles.
