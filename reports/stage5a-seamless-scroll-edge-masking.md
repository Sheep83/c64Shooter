# Stage 5A — Eliminate Top/Bottom Scroll-Edge Pop

## Verdict: **GREEN — engineering candidate ready for visual acceptance**

The pop is gone in the measurement: the terrain field's outer boundary, which
previously walked one raster per fine step and jumped 7 rasters back at every
coarse wrap on **both** edges, is now a **fixed aperture at rasters 60..247 on
every frame of every fixture** (840 sampled frames across 7 fixtures, zero
variation). Automated regressions pass, exact PAL cadence holds, and the
mask-off build is byte-identical to the accepted Mode C binary. **Visual
acceptance has not happened yet** — §13 tells you exactly what to run and look
at.

---

## 1. Repository state (inspected, not assumed)

```
branch    main
HEAD      d60828a  "Promote double-buffered scroller to default"   (unchanged)
status    clean at start
tags      stable-single-screen-scroller -> 223a820
          stable-double-buffered-scroller -> 931dca1
          stable-double-buffered-scroller-v2 -> 479bb32
defaults  OPT_SECOND_SCREEN + OPT_SS_INACTIVE_BUILD + OPT_SS_FLIP_COARSE
          + OPT_SS_ALLOW_PENDING_LIVE_FLIP ; builder 1 / 180 / 3
binary    80d5b0461c070fe23d6e5dbcb2124eb9e4093dbbc4034464d9afe0596f08ce66  (reproduced)
```
Nothing had changed since Stage 4J. No pull/reset/stash/branch switch, and **no
commit, stage, tag or push** was performed. The candidate is left uncommitted:
`M src/main.asm`, `M src/raster_scheduler.asm` (+181/−1).

---

## 2. Objective 1 — what the defect actually is (measured)

PNG↔raster calibration: **raster = y + 16**, proved by the measured first-terrain
raster fitting `48 + fine` exactly at all eight phases.

Baseline capture (default Mode C build, idle, per frame):

| fine | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | then coarse |
|---|---|---|---|---|---|---|---|---|---|
| first terrain raster | 48 | 49 | 50 | 51 | 52 | 53 | 54 | 55 | **→ 48** |
| last terrain raster | 247 | 248 | 249 | 250 | 251 | 252 | 253 | 254 | **→ 247** |

So the **terrain field's outer boundary is at raster `48+fine` (top) and
`247+fine` (bottom)**. Both walk down one raster per fine step and **snap back up
7 rasters at each coarse 7→0 wrap** — an 8 px sawtooth on *both* edges at the
coarse cadence (~3.9 Hz). That moving high-contrast boundary is the visible pop.

Cause: the finite 25-row character fetch. Matrix row 0 is fetched at badline
`48+fine` and displayed at `48+fine..55+fine`; matrix row 24 at
`240+fine..247+fine`. Above and below, the VIC is in idle state (backdrop). The
*content* is not at fault — the body is temporally clean at every phase.

**Top and bottom are the same mechanism**, not two defects. It is visible on
every fine step (the 1 px walk) and jumps at every coarse publication (the 7 px
snap); it is not specific to page-flip frames.

### The key measurement that determines the fix
Content at a **fixed** raster is exactly continuous, *including across the coarse
step*. Checking "pixel row at raster R, frame N == pixel row at raster R−1, frame
N−2" (content descends 1 px per fine step; divider 2):

| raster | 55 | 56 | 120 | 200 | 246 | 247 | 248 | 249 |
|---|---|---|---|---|---|---|---|---|
| fine steps | OK | OK | OK | OK | OK | OK | OK | OK |
| **coarse steps** | (entry) | **OK** | **OK** | **OK** | **OK** | **OK** | DIFF | DIFF |

Rasters 248/249 differ because they alternate terrain/idle with the fine phase;
raster 55 is the entry line where new content necessarily appears. Everything
inside is continuous. **⇒ Presenting a fixed aperture and hiding everything
outside it is sufficient, and costs no continuity.** The ideal window is 55..247.

---

## 3. Objective 2 — what the previous experiments actually proved

`/reports/soft-edge-masking-and-astra-handoff-report.md` (AMBER) had the
**geometry right** (its constants were `SOFT_EDGE_BODY_RESTORE_RASTER = 55`,
`SOFT_EDGE_BAND_RASTER = 248` — the same boundaries derived above) and the clean
body, HUD, border and cadence all survived. It failed for one reason: to keep the
band *grey* it used ECM with MCM off, which forces **four** register writes
($D011 + $D016 + $D022 + $D023, ~20 cycles) plus a 50-cycle pad after a poll,
which cannot fit the ~22-cycle window between one line's last g-access and the
next line's first. The switch therefore landed mid-scanline at a load-dependent
cycle → ±1–8 px per-frame shimmer, i.e. it traded a 3.9 Hz pop for a 50 Hz one.
Its "fundamental 1 px coarse-step artifact" claim is **not** supported by this
session's measurements: a fixed-raster boundary is exactly continuous (§2).

Its recommendation was that a `$D018`-page scroller would give a clean edge "for
free". Stage 4 delivered the page flip, but that alone does **not** fix the edge:
this is a raster-versus-character-row quantisation problem, not a page problem.

**RSEL / border (task option A and C) is a genuine dead end with the current
HUD.** The normal RSEL=0 vertical border would mask exactly `<=54` and `>=247`
for free — precisely the required region. But the vertical border flip-flop can
only be *cleared* at raster 51 (RSEL=1) or 55 (RSEL=0), and the top-border HUD
sprites are displayed at rasters **23..43** (measured), so the FF must already be
clear from the previous frame — which is exactly what `borderOpenHook`'s dodge
achieves, and why both borders are open and the quantisation is exposed. There
is no way to close the border over rasters 44..54 only. Confirmed dead end; a
graphics-mode mask is required.

The blank-charset route stays blocked: every 2 KB `$D018` char-base slot in VIC
bank 0 is still occupied (`$0000` … `$3800`), Stage 4's relocation notwithstanding.

---

## 4. Objectives 3/4 — the candidate

`#define SCROLL_EDGE_MASK` (new, default ON, supersedes `SOFT_EDGE_MASK`, which
stays off; a `.error` guard forbids enabling both).

**Mechanism — the VIC's invalid text mode.** Outside the aperture the display is
put into **ECM=1 with MCM=1**, whose graphics sequencer outputs **black** for
both display *and* idle state regardless of matrix, charset or colour registers.
That reduces the mask to **one store of a pre-computed `$D011`** instead of the
prior four writes, which is what makes it fit the inter-g-access window with
margin to spare. Consequences:

- **No charset mutation** (`$3800..$39FF` untouched), so no menu/GAME-OVER
  charset restore is needed — a whole class of side effects removed.
- **No `$D016`/`$D022`/`$D023` juggling**; the terrain palette is untouched.
- Only `$D01E` (sprite/sprite) is read for collision — `$D01F` is never read
  anywhere in the engine — so the sequencer change **cannot** affect gameplay.
- Badlines, c/g-accesses and therefore the entire raster schedule are unchanged;
  the VIC still fetches normally, only the pixel output is forced black.
- Sprites are unaffected, so the top-border HUD keeps its band.

**Colour.** The band is black. The side border `$D020` is **already black** while
the top/bottom idle strips are currently grey (`$D021` = 12), so this makes the
surround a **uniform black letterbox** instead of grey strips inside a black
border. See §13 — this is the one deliberate look change and needs your eye.

**State.** `GAMEPLAY_D011_BASE |= $40`, so `rasterFrameReset` /
`publishRasterPlan` install the band state every frame; the body is opened by one
store at `EDGE_MASK_BODY_RASTER` and re-closed by one store at
`EDGE_MASK_BAND_RASTER`. `endGame` clears ECM (the existing SOFT_EDGE_MASK branch
condition was widened) so menu/GAME OVER/initials text is unaffected.
`borderOpenHook`'s `!wait250` write is a read-modify-write, so it preserves ECM
when it clears RSEL.

```asm
.const EDGE_MASK_BODY_RASTER = 60      // first raster of the fixed aperture
.const EDGE_MASK_BAND_RASTER = 248     // first masked raster at the bottom
```

### Why 60 and 248
- **248**: raster 247 is row 24's last continuity-relevant g-access; 248 is the
  first raster that alternates terrain/idle with the fine phase. It is also
  **never a badline** (the badline range ends at 247), which makes the bottom
  switch inherently robust.
- **60**: the switch must land after `hudBorderHandoff`, whose completion cannot
  be moved (§14 protects it). Measured entry raster of the mask block: 49..50
  (`--stress`), **49..56** (authored wave). The badline path (below) needs to
  arrive two lines earlier still, so 60 leaves it ≥1 line and the normal path ≥3
  lines of margin. Two diagnostic counters prove the margin is real.

### Raster/cycle proof (measured on the final build, authored wave, 320 frames)

| switch | where | when | measured |
|---|---|---|---|
| body open, normal path (7 of 8 phases) | `rasterDisplayHook`, after the HUD handoff | poll to raster 60, single `stx $d011` | **raster 60, cycles 3..9** (n=280) — store completes by cycle 13, first g-access is cycle 16 ⇒ **3–9 cycles of margin** |
| body open, badline path (`fine == 60&7 == 4`) | same | poll to raster 59 + 51-cycle pad, single `stx $d011` | **raster 59:54..62 / 60:0..2** (n=40) — i.e. inside the inter-line gap, after line 59's last g-access (cycle 55) and before line 60's first (cycle 16) |
| band close | `borderOpenHook`, between its two RSEL dodge writes | poll to raster 248, single `stx $d011` | **raster 248, cycles 3..13** (n=320); line 248 is never a badline |

**Badline interaction — this is what defeated the earlier attempt and what the
badline path exists for.** Raster 60 is itself a badline exactly when
`fine == 4`; a badline steals cycles ~12..54, and combined with sprite DMA
(cycles 0..10) it can starve a poll so the store lands at cycle ~55, i.e. *after*
that line's g-accesses — which blacks the first body line for that phase. This
was observed directly at the earlier target of 58 (store at `58:55` on `fine==2`,
aperture 59 instead of 58 on those frames). The fix is a one-compare branch: two
badlines can never be adjacent, so when the body raster is a badline the previous
line provably is not, and a poll + fixed 51-cycle pad lands the store
deterministically in that line's tail. Both paths measured above; the defect is
gone.

**Poll bounds and safety.** Every poll is bounded and can never wrap: the body
polls run at most from the mask block's entry (raster 49..56) to raster 60; the
band poll runs from the beam's guarded `[237..245]` window to 248. Both are
inside an IRQ with the beam only advancing. `borderOpenHook`'s three-way
hard-lock guard is untouched. `EDGE_MASK_LATE` counts frames that reached the
poll already past the target (store immediately, aperture opens a line or two
low); `EDGE_MASK_FALLBACK` counts badline-phase frames that arrived too late to
place the early store and degraded to the in-line path. Both live inside
`RASTER_STATE`, so every capture dumps them.

**Cost.** One `stx $d011` (4 cycles) per switch; the surrounding poll burns IRQ
time between the mask block's entry (49..56) and raster 60 — at most ~11 rasters
inside the DISPLAY IRQ, which is idle time in any case (the earliest sprite batch
compare under `--dense` is ~raster 88). Nothing was added to
`applyLiveRasterBatch`; the IRQ hot path is untouched.

---

## 5. Result — the aperture is fixed

Terrain-aperture boundaries measured per frame across all seven fixtures (120
frames each, 840 total). The measurement ignores sprites in the band by requiring
≥90 % of a row to be masked (a 24 px sprite is ~8 % of the sample window):

| fixture | aperture | frames |
|---|---|---|
| idle | **60..247** | 120/120 |
| authored wave (seed 382) | **60..247** | 120/120 |
| stage wrap (seed 12) | **60..247** | 120/120 |
| `--y199` | **60..247** | 120/120 |
| `--dense` | **60..247** | 120/120 |
| turret-playtest | **60..247** | 120/120 |
| accelerated stress | **60..247** | 120/120 |

**Zero variation, all eight fine phases, across coarse steps and page flips** —
versus a boundary that previously swept 48→55 and 247→254 every coarse cycle.

---

## 6. Regression suite (candidate build `d06724c6587e2f81…`)

| fixture | frames | replay | catchup | `[19656]` | service fail | incomplete | sprite-start miss | page A | page B | MASK_LATE | FALLBACK |
|---|---|---|---|---|---|---|---|---|---|---|---|
| idle | 300 | 0 | 0 | ✅ | 0 | 0 | 0 | 156 | 144 | 0 | 0 |
| authored wave 382 | 320 | 3 | 1 | ✅ | 0 | 0 | 0 | 141 | 179 | 0 | 0 |
| stage wrap 12 | 340 | 5 | 1 | ✅ | 1 † | 0 | 0 | 180 | 160 | 0 | 0 |
| `--y199` | 400 | 0 | 0 | ✅ | 0 | 0 | 0 | 190 | 210 | 0 | 0 |
| `--dense` | 200 | 100 | 1386 | ✅ | 0 | 0 | 13 ‡ | 104 | 96 | 0 | 0 |
| turret-playtest | 500 | 0 | 0 | ✅ | 0 | 0 | 0 | 260 | 240 | 0 | 0 |
| accelerated stress | 500 | 0 | 0 | ✅ | 0 | 0 | 0 | 272 | 228 | **2** | 0 |

† The single stage-wrap service failure is the **known Stage-4G "Finding 2"
HUD-modelling oracle caveat**, re-confirmed byte-for-byte: frame 82, slots 4–6,
HUD placeholder values 188/189/190 — the exact signature reported in Stage 4G/4H
and unrelated to this mask. The page-aware sprite-pointer oracle is active
(`page_aware: true`) and reports **no** genuine gameplay-pointer failure anywhere.

‡ `--dense` sprite-start misses are **13**, i.e. no worse than (in fact slightly
under) the accepted Stage-4I/4J Mode-C signature of 16, and still the same
`rasterBatchMasksApplied`/badline-coincidence phenomenon Stage 4I attributed to a
pre-existing multiplexer boundary. Not a new defect and explicitly not touched.

`--y199` still progresses (210 of 400 frames on page B) — the pending-LIVE coarse
relaxation is intact.

**Residual:** `EDGE_MASK_LATE = 2` on `--stress` only (2 frames in 500 = 0.4 %),
zero on every other fixture including all supported gameplay. On such a frame the
mask block entered past raster 60 and the store happened immediately, so the
aperture opens one or two lines low for that single frame (a 1–2 px black line at
the top edge, self-correcting). `--stress` is the synthetic accelerated-spawner
fixture. Raising `EDGE_MASK_BODY_RASTER` from 60 to 62 would remove it at a cost
of two further aperture lines — a one-constant decision left open for after
visual inspection.

---

## 7. Aperture cost (quantified)

| | rasters | lines |
|---|---|---|
| before, *maximum* visible terrain extent (fine=7) | 48..254 | 207 |
| before, *minimum* (fine=0) | 48..247 | 200 |
| before, temporally-clean body (as documented since Stage 3) | 55..246 | 192 |
| **after, fixed aperture** | **60..247** | **188** |

So the steady playfield loses **4 raster lines (2.1 %)** against the previously
documented clean body — 5 lines at the top, +1 recovered at the bottom. Against
the *jittering* extent the eye currently sees, the terrain rectangle becomes
about 12–19 px shorter, in exchange for edges that no longer move at all.
Gameplay implication: the terrain window is ~2 % shorter vertically; object
spawn/despawn and turret placement all work in world rows and are unaffected.

---

## 8. Invariants

Preserved and verified: exact PAL `[19656]` on every capture;
`RASTER_INCOMPLETE_FRAMES == 0`; assignment service correct; Mode C
double-buffered scroller, `$D018` publication, pending-LIVE progression,
inactive-page builder, page-aware sprite pointers, BUILD/LIVE separation, the
raster scheduler, the gameplay sprite mux, the top-border HUD handoff
(`HUD_HANDOFF_RASTER` 46 and `HUD_HANDOFF_COMPLETE_RASTER` 56 both untouched, and
the mask block runs strictly after it), collision, turret and stage-map
behaviour. Builder scheduling values unchanged (1 / 180 / 3).
`applyLiveRasterBatch` not touched. `borderOpenHook`'s hard-lock guard not
touched. **`SCROLL_EDGE_MASK` commented out rebuilds
`80d5b0461c070fe23d6e5dbcb2124eb9e4093dbbc4034464d9afe0596f08ce66` byte-identically**,
so the change is fully guarded.

---

## 9. Files changed (uncommitted, for review)

`src/main.asm` (+71): the `SCROLL_EDGE_MASK` toggle and its rationale;
`GAMEPLAY_D011_BASE |= $40` plus `EDGE_MASK_BODY_RASTER` / `EDGE_MASK_BAND_RASTER`
under the toggle; `endGame`'s ECM clear condition widened.

`src/raster_scheduler.asm` (+111): the aperture-open block at the end of
`rasterDisplayHook` (normal path, badline path, late/fallback paths); the
aperture-close block inside `borderOpenHook` between its two RSEL writes; the
`EDGE_MASK_LATE` / `EDGE_MASK_FALLBACK` counters inside `RASTER_STATE`; and four
zero-byte trace labels (`edgeMaskEntry`, `edgeMaskBodyApplied`,
`edgeMaskBodyAppliedEarly`, `edgeMaskBandApplied`) which cost nothing and let any
future session re-measure the switch timing directly.

No repository tool was modified; the extra tracing and the pixel analysers live
in the session scratchpad.

---

## 10. Manual visual validation (this is what remains)

Build and run:
```
cd "…/shooter_test"
java -jar …/KickAss.jar src/main.asm -odir build -o build/shooter.prg -vicesymbols
x64sc -pal build/shooter.prg
```
To A/B against today's behaviour, comment `#define SCROLL_EDGE_MASK` in
`src/main.asm` (line ~93) and rebuild — that is exactly the current shipped
binary.

**What to look for**
1. **Top edge.** Watch the boundary between the black surround and the terrain
   while scrolling. It should be perfectly still. Before, it stepped down a pixel
   at a time and jumped ~7 px up about four times a second.
2. **Bottom edge.** Same, at the bottom boundary.
3. **No new shimmer.** The boundary lines must not flicker or wobble at 50 Hz —
   that was the failure mode of the previous ECM attempt.
4. **The surround is now black rather than grey.** This is the one deliberate
   look change: the top/bottom strips now match the already-black side borders,
   making a uniform letterbox. Please judge whether you like it.
5. **Sprites still show in the letterbox.** The mask blacks the *terrain*, not
   sprites, so the player/enemies remain visible in the band above and below the
   aperture (previously they flew over popping terrain there). Worth deciding
   whether you want the playfield to read as a hard-edged window.
6. **HUD.** The four top-border HUD sprites must still be rock solid.
7. **Game over / menu.** Text screens must render normally (ECM is cleared in
   `endGame`).

**Expected residual artifacts:** none at any fine phase on supported gameplay. On
the synthetic `--stress` fixture only, roughly 1 frame in 250 may show a 1–2 px
black line at the very top edge for a single frame. The mask is active
continuously, not only at selected phases.

---

## 11. Final questions

1. **What causes the top-edge pop?** The terrain field's top boundary is the
   first badline at raster `48+fine`, so it walks down 1 px per fine step and
   jumps 7 px up at each coarse wrap — an 8 px sawtooth at ~3.9 Hz.
2. **What causes the bottom-edge pop?** The mirror image: matrix row 24 ends at
   raster `247+fine`, so the bottom boundary sweeps 247→254 and snaps back.
3. **Same mechanism?** Yes — one defect, the finite 25-row character fetch
   presenting its outermost rows outside a fixed window.
4. **Which phases/rasters?** All of them: every fine step moves the boundary 1
   px (rasters 48..55 top, 247..254 bottom) and every coarse step snaps it back.
5. **What did the previous experiments prove?** The geometry (mask `<=54` /
   `>=248`) was right and the body/HUD/border/cadence survive a mid-frame band;
   the failure was purely that a grey ECM band needs four register writes, which
   cannot be placed inside the ~22-cycle inter-g-access window from a
   variable-entry IRQ, giving a 50 Hz shimmer. Its claim of an irreducible 1 px
   coarse artifact is disproved by §2.
6. **Which techniques were investigated now?** RSEL/display-height and border
   closing (dead end — proven, the vertical border FF cannot be cleared before
   raster 51, and the HUD sits at 23..43); blank-charset via `$D018` (still
   blocked, no free 2 KB CB slot); grey ECM band (the prior four-write approach);
   colour-RAM row blanking (rejected — row-granular, so the boundary still moves
   with fine); **invalid text mode** (chosen); phase-aware boundary treatment
   (used, but only for the badline phase of the switch line, not the aperture).
7. **Best technique and why?** Invalid text mode (ECM+MCM). It is the only
   variant that reduces the mask to a **single** register write, which is what
   makes the switch fit the timing window with margin instead of landing
   mid-scanline; it needs no charset or palette changes, and its black band
   matches the existing black side borders.
8. **Exact writes/timing?** One `stx $d011` per switch: ECM cleared at raster 60
   (cycles 3..9, or 59:54..60:02 on the badline phase) and set at raster 248
   (cycles 3..13). `$D011` is otherwise installed with ECM=1 every frame by
   `rasterFrameReset`/`publishRasterPlan`.
9. **Measured cycle cost?** 4 cycles per switch, 8 cycles per frame of actual
   register work, plus a bounded poll of at most ~11 rasters of otherwise-idle
   DISPLAY-IRQ time.
10. **Badline interaction?** Yes, and it is handled explicitly: raster 60 is a
    badline when `fine == 4`, so that phase takes a separate path that places the
    store in raster 59's tail. Raster 248 is never a badline.
11. **Top-border HUD handoff?** Unaffected — the mask block runs strictly after
    `hudBorderHandoff`, and neither `HUD_HANDOFF_RASTER` nor
    `HUD_HANDOFF_COMPLETE_RASTER` changed. HUD sprites remain visible (sprites
    are not masked).
12. **Gameplay sprite scheduling?** Unaffected; `applyLiveRasterBatch` untouched,
    no sprite deadline regressions in any fixture.
13. **Aperture reduction?** Yes: fixed 60..247 = 188 lines, i.e. **4 lines
    (2.1 %) less** than the previously documented clean body 55..246 = 192.
14. **Mode C otherwise unchanged?** Yes — mask off is byte-identical to
    `80d5b0461c070fe2…`.
15. **All automated regressions pass?** Yes (§6), with the two disclosed
    pre-existing items (wrap HUD-oracle caveat, `--dense` Stage-4I signature) and
    one 0.4 % residual on `--stress` only.
16. **Ready for manual inspection?** Yes.
17. **What to look for?** §10.
18. **If visual inspection passes, what remains?** Decide the black-vs-grey
    surround and whether sprites should remain visible in the letterbox; decide
    whether to spend two more aperture lines (`EDGE_MASK_BODY_RASTER` 60→62) to
    remove the 0.4 % `--stress` residual; optionally drop the four zero-byte
    trace labels; then commit. No further scroller work is implied.
