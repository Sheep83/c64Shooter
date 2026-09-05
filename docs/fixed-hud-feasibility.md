# Fixed top HUD over the beam-raced scroller: feasibility analysis

**Status: ANALYSIS ONLY. No engine source changed. No raster split implemented.**
Fresh KickAssembler 5.25 build, PRG SHA-256
`8a5873dfb8faa7564c4eff62b01d7cdac47abc613aaa0ed80eddacdaf6873a9d`
(identical to the tree state in `docs/scroll-edge-investigation.md`; working
tree clean apart from this file).

The task asked for the smallest clean VIC-II technique that yields a genuinely
fixed top HUD region above a smoothly scrolling cropped gameplay viewport,
without redesigning the proven scroller. After source inspection the answer is:

> **No such technique exists on this engine without changes that the task's own
> STOP conditions forbid.** The blocking facts are structural, not budgetary.
> Recommended path is a *deliberate, separately reviewed* narrowing of the
> scroller's row window (25 -> ~21 rows), after which option C becomes clean.
> A zero-risk partial win (RSEL=0 crop) is available immediately and fixes the
> top/bottom pop but provides no HUD.

---

## 1. What the current source actually does (verified, not assumed)

| Fact | Source | Consequence for a HUD |
| --- | --- | --- |
| One matrix `$0400`, 25 rows, global `YSCROL = SCROLL_FINE` written once per presented frame in `applyFineScroll` (`$d011 & %11111000 | SCROLL_FINE`). | `main.asm:4684`, `main.asm:342/374` | Every one of the 25 rows moves together 0..7 px. There is no second geometry, no mid-frame `$d011` write of any kind. |
| Coarse copy is hard-wired to a 25-row matrix split at row 12/13. `shiftBackgroundUpper` copies rows 0->1 .. 11->12; `shiftBackgroundLower` copies 13->14 .. 23->24; `saveCrossingRow`/`restoreCrossingRow` carry old row 12 into new row 13; new scenery always enters **row 0**. | `main.asm:5027-5060`, `main.asm:4910-4921` | The numbers 0, 12/13, 24 and "enter at row 0" are literals in unrolled code, tied to fetch rasters 151/152 and 240. Any region that is *not* scrolled has to be carved out of that hard-wired range. |
| Beam timing: `prepareBackgroundCoarse` busy-waits `RASTER >= 152`, defers if `$d011` bit7 set or `RASTER >= 200`. `finishBackgroundCoarse` runs just after `armFirstBatch` (raster ~0) and must beat row 13's fetch at line 152. | `main.asm:4892-4933`, `main.asm:4941-4950`, `docs/background-engine.md` | Derived from "row 12 fetched at line 151 when YSCROL=7". Valid **only while YSCROL is uniform for the whole frame.** Move the gameplay region and these constants all move, and 152 vs the 200 deferral wall is already only 48 lines apart. |
| The raster IRQ chain is a **sprite multiplexer only**. `armFirstBatch`: if `BATCH_COUNT == 0` it clears the latch and **leaves the VIC raster-IRQ enable bit cleared** -- i.e. frames with <=8 sprites run with **no raster IRQ at all**. `multiplexIRQ` only ever reassigns hardware sprite slots and chains `RASTER` to the next batch, then `jmp $ea31`. | `main.asm:3032-3071`, `main.asm:3075-3177` | There is no always-present raster event to "just add a compare to". In the common case a HUD split would be the *only* raster IRQ that frame, armed unconditionally every frame -- functionally a new competing raster IRQ. |
| Batch compare = `min(objectY - 12)` in the batch, `objectY < 12` skipped. Enemy Y 0..255 -> compares **0..243**; player Y 49..230 -> **37..218**; eight early enemies can force the first compare down toward **24**. Late legal activity keeps the handler busy to ~raster **262** (`docs/hud-architecture.md`, independently consistent with `buildBatchSpriteSchedule` at `main.asm:2523-2591`). | `main.asm:2530-2538` | A top-HUD split at raster ~50-70 lands **inside the early-batch window**. A bottom-HUD split at raster ~220 lands **inside the late-batch window** that already runs to 262. Either way the split shares the chain with the worst-case sprite pressure. |
| `$d011` bit 7 reads raster bit 8 but writes the IRQ compare high bit. `applyFineScroll` is only safe because it runs at raster 0. | `main.asm:4677-4690` | Any mid-frame `$d011` write above raster 255, or any read/modify/write of `$d011` at an arbitrary raster, has to take explicit ownership of the compare-high bit. A HUD split at raster 50-70 or ~220 is below 256, so this is manageable, but it is one more thing the split must get right every frame. |
| Sprites are independent of `YSCROL`, `RSEL` and the character sequencer. A sprite at Y=40 displays at raster ~40 regardless of any raster split, and sprites display in the border. | VIC-II reference 3.8 | **A YSCROLL raster split does NOT clip gameplay sprites at the HUD boundary and does NOT stop enemies (Y 0..255) from flying through a top HUD.** Requirement 6 ("no sprite occlusion of score") needs `$d015` gating in the HUD band *in addition to* the split, or enemy Y-exclusion (explicitly deferred by the task). |
| Proven character-patch HUD (`drawHudDiagnostic`, `initHudDiagnostic`, `restoreHudTerrain`) keeps 4 cells pixel-fixed across all 8 fine phases using pre-shifted glyphs, terrain save/restore around the coarse copy, no sprite, no IRQ, no `$d011` change. | `main.asm:4952-5008` | This already delivers *pixel-fixed* HUD content. Its limitations are exactly requirements 5 and 6: it needs phase-compensated glyph tables for a dynamic score, and gameplay sprites can cover it. |

---

## 2. Options evaluated

### A. Static 24-row RSEL geometry + HUD in the freed area

`RSEL=0` (clear `$d011` bit 3) once per frame. Visible aperture becomes
raster **55..246** (from 51..250). Per `docs/scroll-edge-investigation.md`
this aperture lies wholly inside fetched terrain for **all 8 fine phases**, so
it hides **both** the top and bottom scroll pop with zero timing risk.

**But it does not create a HUD region.** The 4 cropped lines at each edge are
*border*, not display -- the character sequencer is idle there. Putting score
characters into that strip requires opening the border (a fragile cycle-timed
trick, explicitly a STOP condition). So A on its own answers requirements 3
and 4 and nothing else.

- Cost: ~6 cycles/frame (one extra `and` immediate in `applyFineScroll`), plus
  restoring `RSEL=1` in `endGame` for the menu.
- Scroller, IRQ chain, sprites, metatile decoder, `BG_CROSSING_ROW`: untouched.
- **Verdict: keep as an immediate, safe, reversible partial win. Not a HUD.**

### B. Raster-controlled RSEL switching to build a top HUD region

`RSEL` only moves the vertical-border comparison lines (51/251 <-> 55/247). It
**cannot freeze a region's scroll** and it cannot make the character sequencer
emit rows outside the badline window (48..247). Toggling `RSEL` mid-frame
opens/closes the border; it does not give you fixed score digits. To get
characters above raster 51 you are back to border-opening.

- **Verdict: rejected. `RSEL` is the wrong mechanism for a fixed HUD; it is
  only useful for edge cropping (option A) or bottom-border sprite work
  (rejected in `docs/hud-architecture.md`).**

### C. Small raster display split: fixed YSCROLL for the HUD band, scrolling YSCROLL below

This is the only technique that produces a genuinely fixed, phase-glyph-free
HUD region. Mechanics:

- Frame start (raster ~0): write `YSCROL = HUD_FIXED` (a constant, e.g. 3).
  VIC auto-badlines the HUD rows at rasters 51 and 59 -> HUD occupies
  **raster 51..66**, permanently fixed, ordinary screen codes. Good.
- One raster IRQ at ~raster 67-79 writes `YSCROL = SCROLL_FINE`. Badlines
  resume at `(raster & 7) == SCROLL_FINE`.
- Everything below is the scrolling gameplay region.

Four structural problems, each independently fatal under the task's constraints:

1. **Badline-phase reconciliation at the boundary is fine-dependent.** The
   fixed band uses phase `HUD_FIXED`; the gameplay region uses phase `f`. The
   first gameplay badline after the split write lands at a raster that depends
   on `f`, and for `f = 7` it wraps 7 lines above the `f = 6` position. To
   keep the gameplay region's fine scroll smooth *and* the HUD boundary
   stationary you must insert a **fixed-height idle/FLD dead band** wide enough
   to absorb the full 0..7 phase difference plus IRQ jitter -- ~8-16 lost
   lines. (This is the natural home for the requested separator line, so the
   pixel loss is acceptable; the *mechanism* is the problem, see 2-4.)

2. **The gameplay region shifts down, so the scroller's beam constants must be
   re-derived.** HUD (2 rows) + dead band (~1.5 rows) pushes matrix row "first
   gameplay row" down ~28-40 px. Row 12's fetch moves from line 151 to
   ~175-191; `prepareBackgroundCoarse`'s `cmp #152` and its `cmp #200`
   deferral wall move with it and compress toward the bottom of the frame.
   Row 24's fetch moves past the bottom border (loses rows). "New scenery
   enters row 0" must become "enters row N"; the crossing row moves; the
   unrolled `shiftBackgroundUpper/Lower` loop bounds change. That is
   *rewriting the coarse-copy bodies and their timing* -- a STOP condition
   ("casually change coarse-copy bodies", "significant changes to coarse-copy
   timing", "rewrite the physical coarse scrolling algorithm").

3. **The split IRQ is effectively a new always-on raster interrupt.** With
   <=8 sprites the engine currently arms **no** raster IRQ. A HUD split must be
   armed every frame regardless of sprite count. Even sharing `$0314` and the
   `jmp $ea31` tail, it is a new unconditional raster event -- a STOP
   condition ("add an independent competing raster IRQ").

4. **It still does not stop sprite occlusion.** A YSCROLL split does not clip
   sprites. Enemies (Y 0..255) still cross raster 51..66. Requirement 6 needs
   `$d015 = 0` for the HUD band and restore below it, inside that same IRQ,
   interacting with the multiplexer's own `$d015`/`$d010` writes
   (`renderSprites` `main.asm:2965-3026`, `armFirstBatch`). That is a
   meaningful change to sprite scheduling -- a STOP condition.

- **Verdict: the only technique that meets requirements 1/2/5, but on this
  engine it trips four STOP conditions. Do not implement as a "minimal proof".**

### D. Simpler VIC-II-native solutions found during inspection

- **D-i. Expand the proven phase-glyph patch HUD** to a 6-digit score string
  in rows 1-2. Zero risk, already validated (2,800 frames). Fails requirement
  5 (needs 10x8 = 80 phase-compensated digit glyphs, ~640 bytes -- the budget
  in `docs/hud-architecture.md`) and requirement 6 (sprites can cover it).
  This remains the safe fallback and must not be destroyed.

- **D-ii. A + D-i:** `RSEL=0` crop (hides both pops) plus the phase-glyph
  score at the top of the cropped view. Safe, and it is the closest *safe*
  approximation of the requested look. Still phase glyphs, still occludable.

- **D-iii. Bottom status panel instead of a top HUD (least-invasive split).**
  Many classic C64 shooters (Delta, IO, Sanxion) put the panel at the bottom.
  Gameplay = matrix rows 0..~21, panel = rows ~22..24 held at a fixed
  `YSCROL`. This is *materially* cheaper than option C because:
  - New scenery still enters **row 0**; `shiftBackgroundUpper` is **unchanged**;
    the crossing row stays at 12/13; the 152 wait is **unchanged**.
  - Only `shiftBackgroundLower`'s loop bound changes (24 -> ~21) -- a bounded,
    reviewable edit, not a re-derivation.
  - The outgoing bottom row is now *above* the panel, so the bottom-edge pop
    is hidden behind the separator for free (requirement 4).
  - Top-edge pop still needs `RSEL=0` (option A) on top.

  It still trips STOP conditions 3 (always-on split IRQ at raster ~220, inside
  the late-batch/262 window) and 4 (`$d015` gate for occlusion), and it is a
  bottom panel, not the requested top HUD. But if the product can accept a
  bottom panel it is the cheapest real path and worth a decision.

- **D-iv. Deliberate scroller-window narrowing (recommended real path, needs
  review before coding).** Reduce the scroller from 25 rows to ~21 rows as an
  *intentional, separately reviewed* change to `shiftBackgroundUpper/Lower`,
  the crossing-row index, "enter at row N", and the 152/200/240 constants --
  re-derived once, same algorithm. Reserve rows 0-1 (top) or 22-24 (bottom)
  for the HUD. *Then* option C's split is clean: the HUD band and gameplay
  band have stable, independently-derived badline rasters, and the dead band
  is a designed constant. This is exactly the "authorised experiment that
  changes the scroller -> STOP for review first" gate in the task.

---

## 3. The 13 critical questions, answered for the viable paths

Answers are given for **C / D-iii / D-iv** (the split family) unless noted;
**A** and **D-i/D-ii** are non-split and trivially safe but do not deliver a
fixed non-occludable region.

1. **Raster ownership (top-HUD split, `RSEL=1`, HUD_FIXED=3):**
   - HUD: raster **51..66** (matrix rows 0-1, fixed `YSCROL=3`).
   - Separator / dead band: raster **~67..~82** (idle output or a 1-2 px
     `$d021`/`$d020` bar; absorbs the 0..7 phase difference + IRQ jitter).
   - Scrolling gameplay: raster **~83..246** (`RSEL=0`) or **~83..250**
     (`RSEL=1`), matrix rows 2..~20, `YSCROL = SCROLL_FINE`.
   - Bottom-HUD split (D-iii): gameplay **51..~223**, dead band **~224..~230**,
     panel **~231..250**.
2. **Ordinary screen codes for a dynamic score:** **Yes** -- inside a fixed
   `YSCROL` band the HUD rows never move sub-pixel, so plain screen codes and a
   cheap `printScore`-style writer work (no phase glyphs). This is the whole
   point of the split. Non-split options (A, D-i, D-ii) **cannot** do this;
   they need phase-compensated glyphs.
3. **Shared `$0400` matrix:** Workable but requires **explicit cell
   ownership**. The HUD band cells must be excluded from the coarse copy's
   read/write range (D-iii: trivial, they are below row 21; C/top: they are
   rows 0-1 which `shiftBackgroundUpper` *reads as source*, so they need the
   same terrain save/restore dance the patch HUD already uses, scaled to 80
   cells). A second screen is **not** required and remains prohibited.
4. **`$d011` / `YSCROL` / `RSEL` writes and timing:**
   - `RSEL=0`: once, in `applyFineScroll`, raster ~0 (change the mask from
     `%11111000` to `%11110000`); restore bit 3 in `endGame`.
   - Split `YSCROL`: written twice per frame -- `HUD_FIXED` at raster ~0
     (fold into `applyFineScroll`), `SCROLL_FINE` at the split raster from the
     IRQ. Both are below raster 256 so the compare-high bit reads back as 0,
     matching the scheduler; still must be written deliberately, not blind RMW.
5. **Interaction with existing routines:**
   - `applyFineScroll`: gains the `HUD_FIXED` write / `RSEL` mask. Still at
     raster 0. Safe.
   - `armFirstBatch` / `multiplexIRQ`: the split IRQ must be **chained into
     this vector**, armed even when `BATCH_COUNT == 0`. `armFirstBatch`
     currently *disables* the raster IRQ in that case -- it would have to arm
     the split compare instead. This is the core intrusion.
   - Early batch ~24/37 (top split) or late batch ~243/262 (bottom split): the
     split compare and a sprite-batch compare coexist in one chain; ordering
     is by raster, but a late batch that overruns to 262 can delay a
     bottom-split write -> HUD boundary jitter unless the dead band covers it.
   - `prepareBackgroundCoarse` / `finishBackgroundCoarse`: unaffected by
     D-iii (constants unchanged) apart from `shiftBackgroundLower`'s bound;
     **materially affected by C/top** (152/200/240 re-derivation).
6. **Is a new raster event required?** For a **fixed** HUD (req 1) with the
   scroller intact: **yes**, a mid-frame `YSCROL` change is unavoidable, and
   in <=8-sprite frames it is the only raster IRQ. For **A / D-i / D-ii**: no.
7. **Can it live in the one existing chain?** Physically yes (same `$0314`
   vector, same `jmp $ea31` tail, raster-ordered compares). Semantically it is
   still an unconditional new raster interrupt, which the task lists as a STOP
   condition. Needs explicit human approval.
8. **Does the HUD steal a hardware sprite?** **No** for every option here. The
   HUD is character data. (Requirement 6 pushes toward `$d015` *gating* -- not
   reservation -- of sprites in the band, which is a scheduling interaction,
   not a sprite loss.)
9. **Are gameplay sprites clipped cleanly at the HUD boundary?** **No.** A
   YSCROLL split does not touch the sprite system. Without `$d015` gating or
   enemy Y-exclusion, sprites overlap the HUD exactly as they do today.
10. **Does the beam-raced coarse-copy timing stay valid?**
    - A / D-i / D-ii: **yes, unchanged.**
    - D-iii: yes except `shiftBackgroundLower`'s row bound.
    - C / top HUD: **no** -- 152/200/240 and the row-0 entry point move.
11. **Can the metatile decoder and `BG_CROSSING_ROW` stay unchanged?**
    - A / D-i / D-ii / D-iii: **yes** (decoder always; crossing row stays at
      12/13 for all but a full window narrowing).
    - C / D-iv: decoder yes; `BG_CROSSING_ROW` index moves with the window.
12. **Can the bottom-edge pop be hidden cheaply at the same time?** **Yes** --
    `RSEL=0` (option A) hides both edges for ~6 cycles/frame and no structural
    change. D-iii hides the bottom pop behind its panel for free.
13. **CPU / raster cost, worst case (16 objects / max batches):**
    - A: ~6 cycles/frame, no raster interaction.
    - D-i score expansion: ~80-160 cycles/frame for the digit writer +
      ~160 cycles on coarse frames for 80-cell terrain save/restore.
    - C / D-iii split: the `YSCROL` write itself is ~10 cycles, but it forces
      a raster IRQ every frame (KERNAL entry/exit ~ tens of cycles) that in
      the 16-object / 7-batch case is *interleaved* with the multiplexer's
      own worst-case chain running to raster ~262. Not measured; would need
      the full `tools/vice_scroll_test.py --stress --trace` battery, because
      the risk is jitter/ordering, not a cycle count.

---

## 4. Recommendation

**Do not implement a raster split now.** The clean version (C / D-iv) requires
narrowing the proven scroller's row window and re-deriving its beam constants,
plus arming an unconditional raster IRQ and gating `$d015` -- four of the
task's explicit STOP conditions. Forcing a "minimal proof" that skips those
steps would prove nothing about the real architecture and would risk the one
thing being protected.

Two honest ways forward, for a human decision:

1. **Immediate, zero-risk, partial:** ship the `RSEL=0` static crop (option A).
   It removes the top *and* bottom scroll pop (requirements 3, 4) for ~6
   cycles/frame with no scroller, IRQ, sprite or decoder change. Keep the
   phase-glyph patch HUD for score. This does **not** give a separated,
   non-occludable, ordinary-character HUD (requirements 1, 2, 5, 6, 7).

2. **Full classic HUD, as a separate reviewed task (recommended):** approve a
   deliberate narrowing of the scroller to ~21 rows (D-iv), constants
   re-derived once, same algorithm and same crossing-row mechanism. With that
   in place, option C's split is clean: stable independent badline rasters for
   both bands, a designed dead band for the separator, the split compare
   folded into the multiplexer chain as an unconditional "batch -1", and
   `$d015` gated in the HUD band. Then run the full validation battery
   (all 8 phases, repeated 7->0, 16 objects / max batches, early **and** late
   raster schedules, `check_hud_capture.py` + `check_scroll_edges.py`, human
   VICE observation). Expect ~19-21 gameplay rows (152-168 px) of viewport.

If option 2 is approved, the first concrete step is the scroller-window change
in isolation (no HUD), validated against the existing oracles, **then** the
split on top of it.

---

## 5. Files

- `docs/fixed-hud-feasibility.md` -- this analysis (new, uncommitted).
- No source, tool, build-task, symbol, capture-oracle or asset file changed.
- Fresh build verified: `build/shooter.prg` SHA-256
  `8a5873dfb8faa7564c4eff62b01d7cdac47abc613aaa0ed80eddacdaf6873a9d`.

## 6. Limitations of this analysis

Raster/badline positions are derived from the VIC-II reference and the
measurements already recorded in `docs/background-engine.md` and
`docs/scroll-edge-investigation.md`; they were **not** re-measured in VICE for
this pass because no code was run or changed. The four STOP-condition
collisions in section 2C are structural (they follow from the hard-wired
25-row copy, the conditionally-armed IRQ, and sprite independence from
`YSCROL`) and do not depend on exact cycle counts. Any implementation of
option 2 must replace these derivations with `--trace` measurements.
