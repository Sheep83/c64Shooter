# Historical Scroll Hitch — Phase B(a): Safe Legacy Fallback Gate

**Verdict: AMBER.** The corruption is completely gone — 0 visible snaps, 0
duplicated turrets, across 13 captures that previously produced 10 snaps and up
to 256 duplicated frames. But unbounded deferral replaces a **1-frame, 7-pixel
snap** with a terrain stall of up to **36 frames (0.72 s)**. Phase B(a) is
correct and it is not sufficient. **Do not ship it alone.**

Branch `main`, HEAD `d60828a`. Nothing committed, staged, tagged or pushed.
The repair and its instrumentation are left uncommitted for review.

---

## 1. What was changed

Three hunks in `src/main.asm`, nothing else. Verified: reversing exactly these
three hunks reproduces the pre-patch binary `69224428ddb05c8a` bit for bit.

**(a) The gate**, at the legacy fallback entry ([main.asm:6324](src/main.asm#L6324)),
after the existing Stage-4F pending-LIVE bypass check and before any mutation:

```asm
    inc SS_FLIP_FALLBACK                    // legacy fallback REACHED
    ...
    lda BG_ACTIVE_PAGE
    beq !lcpPageA+                          // 0 = page A displayed -> legacy path is valid
    inc SS_LEGACY_PAGEB_BLOCK               // page B live: refuse
    ...
    lda #4
    sta COARSE_LAST_REASON                  // new reason 4
    jmp !defer+                             // the EXISTING defer path
!lcpPageA:
    lda #0
    sta SS_LEGACY_BLOCK_STREAK
    inc SS_LEGACY_COARSE_PATH_COUNT         // executed (page A only)
```

**(b) Counters** appended to the `ssFlipStats` block (inside `#if OPT_SS_FLIP_COARSE`,
so they appear in every existing `.flip` capture dump automatically):
`SS_LEGACY_PAGEB_BLOCK` (word), `SS_LEGACY_BLOCK_STREAK`,
`SS_LEGACY_BLOCK_STREAK_MAX`. Streak is cleared by `ssFlipNoteAdmit` and by a
page-A execution, so it means "consecutive refusals since the last *completed*
coarse step".

**(c) A segment base move.** The gate pushed the relocated background-control
block from `$98fa` to `$9922`, past the Stage-4 second-screen block at `$9900`.
That block is CPU-only with no VIC alignment requirement, so its base moved
`$9900 → $9980` (`SS_STAGE4_BASE_ADDR`); it now occupies `$9980-$9e6f`, still far
below the BASIC ROM at `$a000`. A named `.error` assert was added so a future
collision fails with the real constraint rather than a bare overlap message.

### Disassembled from the built binary

```
$95a5: LDA $9980   BG_ACTIVE_PAGE
$95a8: BEQ $95c8               -> page-A path
$95aa: INC $9c05   SS_LEGACY_PAGEB_BLOCK
...
$95c0: LDA #$04
$95c2: STA $97d2   COARSE_LAST_REASON
$95c5: JMP $9630               -> !defer

$95c8: LDA #$00 / STA $9c07 / INC $9bfd (SS_LEGACY_COARSE_PATH_COUNT)
$95d5: LDA $d012               -> falls straight into !waitRead, unchanged

$9630: INC $97c6 BG_COARSE_DEFERRED ... LDA #$01 / STA $21c3 SCROLL_FRAME_COUNT / RTS
```

The `!defer` target is the **pre-existing** mechanism — no second defer path was
invented. It writes `SCROLL_FRAME_COUNT` only. `SCROLL_ROW` (`$21c5`) and
`SCROLL_FINE` (`$21c4`) are provably untouched, as is every matrix byte and every
VIC register.

---

## 2. Before / after on the known-bad seeds (420 frames each)

Mask-OFF builds both sides, so this is a like-for-like A/B.

| seed | BEFORE legacy A/B | BEFORE snaps | BEFORE dup frames | AFTER attempts | AFTER exec A | AFTER refused B | AFTER snaps | AFTER dup |
|---|---|---|---|---|---|---|---|---|
| 352 | 0 / 2 | 2 | 257 | 18 | 1 | 17 | **0** | **0** |
| 360 | 1 / 1 | 1 | 0 | 6 | 1 | 5 | **0** | **0** |
| 340 | 4 / 1 | 1 | 180 | 38 | 2 | 36 | **0** | **0** |
| 232 | 0 / 2 | 2 | 256 | 18 | 0 | 18 | **0** | **0** |
| 124 | 1 / 3 | 3 | 40 | 6 | 3 | 3 | **0** | **0** |
| 112 | 1 / 1 | 1 | 17 | 2 | 0 | 2 | **0** | **0** |
| 224 (control) | 0 / 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Plus a longer sweep (6 further seeds × 500 frames): before **7 snaps**, after
**0 snaps, 0 duplications**.

Attempt counts rise sharply (340: 5 → 38) because a refusal re-arms the retry
every frame, so one blocked *event* becomes many blocked *attempts*. The
instrumentation invariant holds exactly across all 13 captures:
`SS_FLIP_FALLBACK (118) == SS_LEGACY_COARSE_PATH_COUNT (13) + SS_LEGACY_PAGEB_BLOCK (105)`.

`SCROLL_ROW` remains aligned with the visible page on every frame of every
patched capture — the desync signature that produced the duplicated turret no
longer occurs at all.

---

## 3. The cost — this is why the verdict is AMBER

Longest run of frames in which the presented terrain does not move at all
(matrix rows 2..23 plus the live fine-scroll value; 2 frames is the normal
baseline, because fine advances every second frame):

| build | 352 | 360 | 340 | 232 | 124 | 112 | 224 |
|---|---|---|---|---|---|---|---|
| pre-Stage-4 Mode A | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| Stage 4J (unpatched) | 2 | 2 | 2 | 2 | 2 | 3 | 2 |
| **Phase B(a)** | **21** | **7** | **36** | **12** | **4** | **3** | 2 |

Confirmed independently on the rendered VIC-II output. Seed 340, the same window
in both builds (`dy` = pixels the terrain moved):

```
PATCHED   pb-340 : -1px, -1px, then 36 CONSECUTIVE FRAMES WITH NO MOTION, then -1px…
UNPATCHED sw-c-340: -1px every second frame throughout, 20 clean steps
```

Refusal streak distribution over all 13 patched captures (16 streaks):

```
  1 frame :  3  (18.8%)      builder ready on the very next frame
  3 frames:  1
  4 frames:  6
  5 frames:  2               75% cumulative
  8 frames:  1
 10 frames:  1
 16 frames:  1
 31 frames:  1  (worst; 36 presented frames of frozen terrain)
```

Only **18.8%** of refusals clear on the next frame. A quarter of them exceed five.

---

## 4. Why deferral does not clear quickly — and what that implies

The gate did not cause the stall; it exposed what the legacy path was papering
over. During the seed-340 stall the builder crawls:

```
SS_BUILD_NEXT_ROW : 7 → 7 → 9 → 15 → 18 → 18 → 18 → 18 → 24 → complete
```

Measured builder throughput (forward rows laid down per frame):

| condition | rows/frame |
|---|---|
| low-load control (seed 224) | 1.52 |
| healthy window under wave load | 1.28 |
| **during the seed-340 stall (patched)** | **0.50** |
| same window unpatched | 0.25 |

Throughput collapses roughly **3×** under 6–7 enemy load with an enemy at the top
of the playfield. Recovering that is not a margin tweak — it is a redesign of the
builder's slice budget. That materially changes the Phase B recommendation (§8).

---

## 5. Regression suite (patched default build, mask ON, `e966903477a03a91`)

| fixture | frame deltas | svc fail | sprite-start miss | catchups | replay | page A / B |
|---|---|---|---|---|---|---|
| idle 300 | `[19656]` | 0 | 0 | 0 | 0 | 156 / 144 |
| wave 320 (seed 382) | `[19656]` | 0 | 0 | 1 | 0 | 160 / 160 |
| wrap 340 (seed 12) | `[19656]` | 2 † | 0 | 3 | 5 | 197 / 143 |
| y199 400 | `[19656]` | 0 | 0 | 0 | 0 | 211 / 189 |
| dense 200 | `[19656]` | 0 | **0** | 1386 | 100 | 104 / 96 |
| turret 500 | `[19656]` | 0 | 0 | 0 | 0 | 260 / 240 |
| stress 500 | `[19656]` | 0 | 0 | 0 | 0 | 272 / 228 |

† pre-existing; the same fixture on the pre-patch build gives **3**. Baselined on
`69224428ddb05c8a`: dense `catchups 1386 / replay 100` — **identical**, no drift.

**Exact PAL 19,656 cycles/frame held on every fixture. Zero sprite-start misses
everywhere, `--dense` included. No new service failures.**

Stage-5 protections:
- Edge-mask aperture **58..247 on 130/130 frames** for wave, wrap, dense, turret
  and stress — unchanged from the accepted Stage 5B baseline.
- Title screen probed live: `$D011=$9b`, **ECM=0**, YSCROLL=3, `GAME_STATE=0`,
  12 starfield glyphs present. Matches the accepted Stage 5B checkpoint.
- The diff adds no `$D011` write and moves none.

---

## 6. Binary identity — intentional drift, disclosed

| build | hash | note |
|---|---|---|
| Mode A (single-screen), patched | `f2abc225159e81bf` | **byte-identical** to a fresh build of the `stable-single-screen-scroller` tag |
| mask-OFF double-buffered, pre-patch | `80d5b0461c070fe2` | accepted Stage 4J |
| mask-OFF double-buffered, patched | `00a25b367e0151ab` | **intentional drift** |
| default (mask ON), pre-patch | `69224428ddb05c8a` | |
| default (mask ON), patched | `e966903477a03a91` | |

The whole gate sits inside `#if OPT_SS_FLIP_COARSE`, so single-screen builds are
untouched — the Mode A identity with the historical tag still holds exactly.
The mask-OFF ↔ Stage-4J identity is **deliberately broken**: this is an engine
bug fix, not Stage-5 work, so it compiles unconditionally in double-buffered
builds. Per §14 I did not contort the repair to preserve that hash.

---

## 7. Answers to the final questions

1. **Where is the guard?** `src/main.asm`, at `!legacyCoarsePath` — after the 4F
   `SS_PLF_BYPASSED` check, before the first mutation and before `!waitRead`.
2. **Page A?** Unchanged. Streak cleared, `SS_LEGACY_COARSE_PATH_COUNT`
   incremented, then straight into `!waitRead` and the historical path.
3. **Page B?** Counters bumped, `COARSE_LAST_REASON = 4`, `jmp !defer`.
4. **`SCROLL_ROW` on a blocked fallback?** Unchanged — proven at machine-code
   level and in every capture.
5. **`SCROLL_FINE`?** Unchanged; `!defer` writes only `SCROLL_FRAME_COUNT = 1`.
6. **Page-B events blocked?** 105 refusals across 13 captures; all 10 of the
   originally-identified corrupting events are among them.
7. **7 px snaps remaining?** **0.**
8. **Duplicated-turret signatures remaining?** **0.**
9. **Safe coarse deferrals?** 105.
10. **Max consecutive streak?** 31 refusals → 36 presented frames of frozen terrain.
11. **Builder ready next frame?** **18.8%.**
12. **Any ordinary wave still showing a machine-detectable hitch?** No snap and no
    duplication anywhere. But a *new* detectable signature appears: terrain stalls
    of 3–36 frames against a 2-frame baseline, in 6 of 7 known-bad seeds.
13. **Exact PAL?** Yes — `[19656]` on all seven fixtures.
14. **Mux / HUD / Stage-5 clean?** Yes — 0 sprite-start misses, dense identical to
    baseline, aperture 58..247 on 130/130, title ECM=0 with starfield intact.
15. **Is Phase B(a) sufficient?** **No.** Necessary and correct, but the
    replacement artefact is worse in the worst case.
16. **Which next step?** **Phase B(b), the page-aware legacy fallback.** The
    evidence is in §4: eliminating the fallback through builder throughput would
    need roughly a 3× improvement under peak load, which is not a modest change.
    Making the fallback correct on either page is the bounded fix — it keeps the
    coarse step *always* completing (no stall, as today) while removing the
    corruption (as Phase B(a) does). Phase B(a) then becomes its safety net rather
    than the mechanism.
17. **Manual inspection?** See §9 — but I do not recommend acceptance testing this
    build as a candidate; test it only to confirm the snap and duplication are gone.

---

## 8. Recommendation

Keep the gate — it is correct, cheap, and it is the right safety net. Add
**Phase B(b)**: a page-aware legacy fallback (a `$2800` copy of the five unrolled
routines, dispatched on `BG_ACTIVE_PAGE`; ~1 KB, cycle-neutral). With B(b) in
place the coarse step always completes on whichever page is live, so neither the
snap nor the stall occurs, and the B(a) gate remains as the belt-and-braces guard
should the page-aware path ever be unavailable.

A cheaper interim exists — cap the refusal streak at N and then permit one legacy
execution — but it deliberately reintroduces the snap *and* the persistent turret
duplication on those events, so I do not recommend it.

I have not implemented B(b) (§15 forbids it in this task).

---

## 9. If you do want to look at this build

`build/shooter.prg` = `e966903477a03a91`. Expect: **no 7 px backward snap and no
duplicated turret top half** in repeated six-enemy waves with enemies climbing to
the top edge. Expect instead an occasional clean pause of the terrain — usually
brief, but up to about three-quarters of a second in the worst case. Stage-5 edge
masking, the HUD and the title/high-score starfield should all look exactly as
they do today.

---

## 10. Reproduction

```
scratchpad/run_hitch.sh <name> <port> <prg> <vs> --seed-scroll <S> --frames 420
```
Known-bad seeds: 352, 360, 340, 232, 124, 112 (clean control: 224). Longer sweep:
300, 280, 260, 200, 180, 150 at 500 frames.

Detectors used: visible-freeze (fine resets 7→0 while ≥24/25 rows of the *visible*
page are unchanged); duplicated-turret (adjacent row pair both matching glyphs
226,227 in a live turret's column); visual stall (terrain rows 2..23 plus fine
identical to the previous frame); and rendered-PNG vertical cross-correlation as
the independent check.
