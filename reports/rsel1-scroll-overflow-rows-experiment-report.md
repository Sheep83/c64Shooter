# Border-HUD Experiment — Eliminate the RSEL=1 Coarse-Scroll Edge Pops

**19656 / c64Shooter — PAL C64 vertical shooter.** Branch `experimental-border-hud`.
No commit, no push. VICE (`x64sc`) launched head-less / background
(`-remotemonitor`, `Popen`, `DEVNULL`), never foregrounded, no `open -a`.

Legend: **[OBS]** source · **[MEAS]** measured this session · **[A/B]** measured
against a comparison build · **[INF]** inference.

---

# TL;DR / verdict

**GREEN** — the coarse-scroll edge pops are eliminated by giving matrix rows 0
and 24 the correct neighbouring terrain (an *incoming* and *outgoing overflow
row*) instead of leaving them blank, **and** letting the display aperture crop
those overflow rows' own outer edges. RSEL=0's border flip-flop crops at raster
55 / 246 exactly where those edges sit, so **`GAMEPLAY_RSEL = 0` + overflow rows
= both visible edges temporally continuous**, `[19656]` exact, scheduler clean,
colour RAM coherent, ~24 visible terrain rows.

The `GAMEPLAY_RSEL = 1` variant (kept behind a one-line toggle) is **AMBER**: the
overflow rows make the entire gameplay *body* (matrix rows 1..23, rasters
~56..246) temporally flawless, but the RSEL=1 aperture (51..250) does not crop
the overflow rows' own outer edges, leaving a ~4 px residual oscillation at
rasters 52-55 and 247-250.

| Success criterion | RSEL=0 + overflow (shipped) | RSEL=1 + overflow (toggle) |
| --- | --- | --- |
| 1. top-edge 7→0 pop gone | ✅ | ⚠ ~4 px residual at r 52-55 |
| 2. bottom-edge 7→0 pop gone | ✅ | ⚠ ~4 px residual at r 247-250 |
| 3. terrain body flawless | ✅ | ✅ |
| 4. exactly 1 px per presented scroll step | ✅ (`coarse_edge_median_jump [0,1]`) | ✅ in the body |
| 5. character identity coherent at both edges | ✅ | ✅ body |
| 6. colour RAM coherent at both edges | ✅ (uniform `TERRAIN_COLOUR_RAM`) | ✅ |
| 7. repeated coarse transitions clean | ✅ (13 / 19 / 24 tested) | body only |
| 8. `[19656]` exact | ✅ | ✅ |
| 9. no new service / sprite-start / incomplete | ✅ | ✅ |
| 10. wave5 scrolling visually stable | ✅ | body only |
| 11. no protected renderer/mux rewrite | ✅ | ✅ |
| 12. understandable / maintainable, not a mask | ✅ | ✅ |

---

# 1. Start state

| | |
| --- | --- |
| Branch | `experimental-border-hud` (already checked out) |
| HEAD | `d547c80415af5412bbdd92b014dbb75d79cbc5e4` — *"Establish RSEL1 border HUD experimental baseline"* (= the Phase-1.5 RSEL=1 conversion, committed) |
| Working tree at start | **clean** |
| Baseline build | `sha256(build/shooter.prg) = 6e9d30468522eb31…` |
| Final build (this experiment, `GAMEPLAY_RSEL = 0`) | `sha256(prg) = b8fdfe495a797d31…`, `sha256(d64) = 17ae896c770e3b1b…` |

Phase-1.5 state confirmed against source: legacy top char HUD removed
(`initFixedHud` reduced), invalid BMM+ECM separator removed (`rasterDisplayHook`
a no-op), gameplay RSEL=1 via `rasterFrameReset`/`publishRasterPlan` writing
`RASTER_DISPLAY_FINE | $18`, lower border opened by `borderOpenHook`'s RSEL 1→0
at raster 250, matrix rows 0 and 24 permanent blank `$20` spacers, scroller
writes matrix rows 1..23 only.

---

# 2. Experiment A — how the scroller behaves through fine 7→0 (before any change)

**[MEAS]** `scratchpad/rowtrace.py` — col-0 screen code of every matrix row
0..24 each frame across a fine 0..7 → coarse cycle, with fine phase / `SCROLL_ROW`
/ `BG_COARSE_FINISH`.

## 2.1 Routine map (source) — [OBS]

| Stage | Routine | Matrix rows read → written | When |
| --- | --- | --- | --- |
| fine step | `updateBackgroundScroll` → `applyFineScroll` publishes `RASTER_DISPLAY_FINE = SCROLL_FINE` | none | frame start |
| coarse **upper** phase | `prepareBackgroundCoarse` (raster-gated, runs `saveCrossingRow` → `shiftBackgroundUpper` → `SCROLL_ROW--` (wrapping 0→SLR) → `renderStageRowToScreen`) | `saveCrossingRow`: row 12 → `BG_CROSSING_ROW`. `shiftBackgroundUpper`: **dst 2..12 ← src 1..11**. `renderStageRowToScreen`: **row 1** ← decoded stage. Rows 13..24 untouched. Sets `SCROLL_FINE = 0`, `BG_COARSE_FINISH = 1`. | raster ~160 → **271-272** (measured) |
| coarse **lower** phase | `finishBackgroundCoarse` (`shiftBackgroundLower` → `restoreCrossingRow`) | `shiftBackgroundLower`: **dst 14..23 ← src 13..22**. `restoreCrossingRow`: `BG_CROSSING_ROW` (old row 12) → **row 13**. | next frame start (beam in border) |

`renderStageRowToScreen`: `BG_LOGICAL_ROW = SCROLL_ROW + BG_DEST_ROW − 1`, reduced
mod `STAGE_LOGICAL_ROWS` (= 420) by `wrapBgLogicalRow`. Colour RAM is **one
stage-global value** (`TERRAIN_COLOUR_RAM`), written once by `initBackground`,
never scrolled. `copyIncomingRowToScreen` already supports `BG_DEST_ROW` 0..24
(`starRowLo/Hi` has 25 entries). **All 25 matrix rows are DMA-fetched by the VIC**
(DEN=1, badlines `48+fine+8k`, k=0..24, last = `240+fine` ≤ 247 at fine 7); the
blank rows 0/24 are *fetched but empty*.

## 2.2 Measured row-state, blank-spacer baseline — [MEAS]

```
fine 0..7  (SCROLL_ROW = 397, stable):
  row 0   = $20 (blank spacer)
  rows 1..23 = terrain, world 397..419      (W(r) = SCROLL_ROW + r - 1)
  row 24  = $20 (blank spacer)

coarse upper phase done (fine still presented 7, SCROLL_ROW 396, FINISH pending):
  row 0   = $20                               <- NOT touched
  row 1   = fresh render, world 396           <- renderStageRowToScreen
  rows 2..12 = old rows 1..11 (shifted down)
  rows 13..24 = unchanged (world 408..419, $20)

coarse lower phase done (fine 0, SCROLL_ROW 396):
  row 0   = $20                               <- STILL blank
  rows 1..23 = terrain, world 396..418
  row 24  = $20                               <- STILL blank; world 419 DISCARDED
```

---

# 3. Why each edge popped — [MEAS] + [INF]

**Q3 — top edge.** The scroll direction reveals *earlier* world rows at the top.
For continuity, world `SCROLL_ROW − 1` should be partially visible above matrix
row 1 during the fine phase. It is not — matrix row 0 is blank. At the coarse
step `prepareBackgroundCoarse` renders world `SCROLL_ROW − 1` freshly into matrix
row 1, where it lands at raster ~56-63 (fine 0) having been *nowhere* the
previous frame (fine 7). ⇒ the top terrain edge jumps ~7 px.

**Q4 — bottom edge.** For continuity, the outgoing bottom row (world
`old_SCROLL_ROW + 22`) should scroll one pixel further *down*, into matrix row
24's raster space. `shiftBackgroundLower` writes dst 14..23 only — **matrix row
24 is never written, so that row's content is discarded** and rasters ~240-246
snap from terrain to blank at the coarse step. ⇒ the bottom terrain edge jumps
~7 px.

**Q5 — was "blank rows 0/24 are the cause" correct?** **Yes, exactly.** There is
no deeper 25-row / badline / beam-raced obstruction: all 25 rows are already
fetched; rows 0 and 24 simply need to carry `W(0) = SCROLL_ROW − 1` and
`W(24) = SCROLL_ROW + 23` and be maintained through the coarse transaction. The
one *secondary* fact discovered (§5) is that the overflow rows then have their
*own* uncroppable outer edges, which is why RSEL=0's border crop is part of the
solution.

## Before / after matrix-row diagram (fine 7 → coarse → fine 0)

```
BLANK-SPACER BASELINE                         OVERFLOW ROWS (this experiment)
--------------------------------------        --------------------------------------
fine 7 :  r0  = $20  (blank)                  fine 7 :  r0  = world S-1  (incoming overflow)
          r1  = world S                                 r1  = world S
          ...                                            ...
          r23 = world S+22                                r23 = world S+22
          r24 = $20  (blank)                              r24 = world S+23  (outgoing overflow)

coarse :  shiftUpper  dst 2..12 <- src 1..11             shiftUpper  dst 1..12 <- src 0..11
          render      r1 = world S-1                      render      r0 = world S-2
          shiftLower  dst 14..23 <- src 13..22            shiftLower  dst 14..24 <- src 13..23
          world S+22 (r24 space) -> DISCARDED             world S+22 -> r24  (kept, +1 px)
          world S-1 pops in at r1 (+7 px)                 world S-1 was already in r0 (+1 px)

fine 0 :  r0  = $20                                       r0  = world S-2
          r1  = world S-1   <- 7 px jump                  r1  = world S-1   <- +1 px, continuous
          ...                                             ...
          r23 = world S+21                                r23 = world S+21
          r24 = $20  (world S+22 gone) <- 7 px jump       r24 = world S+22  <- +1 px, continuous
```

Invariant preserved for all r = 0..24 through the coarse transaction and the
stage wrap: `W(r) = SCROLL_ROW + r − 1` (verified [MEAS] `rowtrace.py`).

---

# 4. Q6 — exact routines / constants changed (`src/main.asm` only for the engine)

| Routine / const | Change |
| --- | --- |
| `shiftBackgroundUpper` | `.for row = 12 … 2` → `.for row = 12 … 1` — also shift matrix **row 0 → row 1** (dst 1..12 ← src 0..11). +40 B. Beam-safe: row 0 is fetched at badline ≤ 55, this copy runs ≥ raster 160. |
| `shiftBackgroundLower` | `.for row = 23 … 14` → `.for row = 24 … 14` — also shift matrix **row 23 → row 24** (dst 14..24 ← src 13..23). +40 B. Beam-safe: runs at frame start, no row fetched yet. |
| `prepareBackgroundCoarse` | render the fresh stage row into `BG_DEST_ROW = 0` (was `1`) — the *incoming overflow* = world `SCROLL_ROW − 1` after the decrement. `shiftBackgroundUpper` has already moved the old row 0 down into row 1. |
| `wrapBgLogicalRow` | leading `bpl` branch: if `BG_LOGICAL_ROW` is negative (`$FFFF`, only reachable as `BG_DEST_ROW = 0` at `SCROLL_ROW = 0`), fold up by one `STAGE_LOGICAL_ROWS`. Every pre-existing caller passes a non-negative value → the branch is not taken → **zero behaviour change for `BG_DEST_ROW` 1..24**. |
| `initBackground` row loop | `ldx #1 … cpx #24` → `ldx #0 … cpx #25` — render all 25 matrix rows at game start (rows 0 and 24 included). |
| `initFixedHud` | Emptied to a bare `rts`. It previously blanked matrix rows 0 and 24 (`$20`) and forced matrix row 0's colour RAM to `1`. Rows 0/24 are no longer spacers; their colour RAM now stays at the stage-global `TERRAIN_COLOUR_RAM` from `initBackground`'s fill. |
| **`GAMEPLAY_RSEL`** (new `.const`, `main.asm`) + `GAMEPLAY_D011_BASE = $10 \| (GAMEPLAY_RSEL << 3)` | one-line toggle for the gameplay `$D011` RSEL bit. `GAMEPLAY_RSEL = 0` ships. Wired into `init` (`ora #GAMEPLAY_D011_BASE`), `raster_scheduler.asm : publishRasterPlan` and `rasterFrameReset` (`ora #GAMEPLAY_D011_BASE` replacing `ora #$18`). |

`raster_scheduler.asm`: 3 tokens (`$18` → `GAMEPLAY_D011_BASE`). `borderOpenHook`
is unchanged — with `GAMEPLAY_RSEL = 0` its RSEL 1→0 write at raster 250 is a
no-op (bit already clear) and the bottom border closes normally at raster 247.

**Nothing else.** No change to: `renderStageRowToScreen` decode/colour model,
`decodeStageCharacterRow`, `copyIncomingRowToScreen`, `saveCrossingRow` /
`restoreCrossingRow` boundaries (still row 12 → 13), the crossing-row buffer,
the beam-raced two-phase split, `applyLiveRasterBatch`, the mux, BUILD/LIVE plan,
`sortObjectsByY`, collision plumbing, `installTurretRow` / turret pool,
`$D016`/`$D018`/VIC bank, the stage decoder, the level/editor contract, or the
raster scheduler architecture (the 3 `$D011`-base tokens are a constant swap, not
a timing change).

Editor viewport: **not modified.** See Q20.

---

# 5. The mechanism discovered — why RSEL matters

The overflow rows themselves have no further overflow (`W(-1)` / `W(25)` do not
exist), so **row 0's own top edge and row 24's own bottom edge are still
discontinuous** at the coarse step. Those edges sit at:

- row 0: rasters `48+fine … 55+fine` (its imperfect top ~48-54)
- row 24: rasters `240+fine … 247+fine` (its imperfect bottom ~247-254)

Whether that residual is *visible* depends entirely on the display aperture:

| Aperture | crops row 0 top at | crops row 24 bottom at | residual visible? |
| --- | --- | --- | --- |
| **RSEL=0** (border FF: reset r55, set r247) | **raster 55** | **raster 246** | **No** — the border FF crops exactly the overflow rows' bad edges. The visible field is row 0 (bottom sliver) + rows 1..23 (full) + row 24 (top sliver), all continuous. |
| **RSEL=1** (border FF: reset r51, set r251; bottom dodged open in the baseline) | raster 51 | raster 250 (or open) | **Yes** — ~4 px at r 52-55 and r 247-250; the aperture is 4 px wider than the clean content at each end. |

**[INF] RSEL does not gate the video-matrix DMA** — the badline condition is
`DEN ∧ 0x30 ≤ RASTER ≤ 0xf7 ∧ (RASTER & 7) == YSCROL`, with no RSEL term. So
RSEL=0 fetches the same 25 rows as RSEL=1; it only moves the vertical-border
comparison lines. RSEL=1's *only* effect here is a 4-px-wider aperture at each
end — which is precisely what exposes the overflow rows' bad edges. **For this
scroller, RSEL=0 is strictly better.**

---

# 6. Q7-Q12 — the resulting scroller

**Q7 — rows in the coarse transaction now:** upper phase touches matrix rows
**0..12** (`saveCrossingRow` 12; `shiftBackgroundUpper` dst 1..12 ← src 0..11;
render row 0). Lower phase touches matrix rows **13..24** (`shiftBackgroundLower`
dst 14..24 ← src 13..23; `restoreCrossingRow` → row 13). Split point unchanged
(row 12 → 13).

**Q8 — matrix row 0 during scrolling:** the **incoming overflow row**, world
`SCROLL_ROW − 1` (one row *earlier* than the top body row). Fully re-rendered by
`prepareBackgroundCoarse` each coarse step; shifted into row 1 on the next.
Under RSEL=0 only its bottom 0-8 px is visible (a growing sliver at rasters
~55-62 as fine goes 0→7).

**Q9 — matrix row 24 during scrolling:** the **outgoing overflow row**, world
`SCROLL_ROW + 23` (one row *later* than the bottom body row). Populated by
`shiftBackgroundLower` from old row 23 each coarse step. Under RSEL=0 only its
top 7-0 px is visible (a shrinking sliver at rasters ~240-246 as fine goes 0→7).

**Q10 — colour RAM at the edges:** **uniform.** `initBackground` fills all 1000
colour-RAM cells with `TERRAIN_COLOUR_RAM`; `initFixedHud` no longer overrides
row 0. **[MEAS]** runtime dump: rows 0 / 1 / 12 / 24 colour RAM all `$F9`
(colour 9). No colour row is scrolled, so there is no colour-vs-character skew
and **no 8-px colour flash** at either edge. (Turret hit-flash still writes
turret-cell colour RAM — unchanged, covered by `check_turret_capture.py`.)

**Q11 — visible terrain aperture:** RSEL=0, raster **55..246 = 192 px = 24 char
rows** of visible terrain (row 0 bottom sliver + rows 1..23 full + row 24 top
sliver; the "24 rows" counts the two edge slivers that together make one row's
worth). `STAGE_START_ROW` is unchanged (`STAGE_LOGICAL_ROWS − 23`), so matrix
row 1 still anchors `SCROLL_ROW` and the bottom-origin semantics are preserved.

**Q12 — clean 24th terrain row?** Effectively yes: the visible field is now a
continuous 192 px / 24-row-equivalent aperture (up from the blank-spacer
baseline's 176 px of clean body + two popping edges). The engine still fetches
exactly 25 rows and still anchors on matrix row 1; rows 0 and 24 are now *useful
overflow* rather than wasted blanks. No re-anchor, no `STAGE_START_ROW` change,
no editor change was required to get there.

---

# 7. Q13-Q14 — temporal proof

**Instrument:** `tools/check_scroll_edges_rsel1.py` (extended this session) —
model-free: every observed pixel must equal the pixel one line above it in the
previous frame (1 px scroll), excluding sprite-covered samples, the one
genuinely-new entering scanline, and authored turret columns (turret 2×2 cells
are republished on stream-in / hit / stage wrap — a content change owned by
`check_turret_capture.py`). Bands reported separately: **top overflow / body /
bottom overflow**. Plus a per-frame lowest-terrain-edge raster series
(`scratchpad/edgeseries.py`) and magnified 12-frame seam strips
(`scratchpad/evidence.py`).

## 7.1 `GAMEPLAY_RSEL = 0` + overflow rows — [MEAS]

| Workload | frames | coarse 7→0 steps | body diffs | edge (r 55 / 246) diffs | `coarse_edge_median_jump` |
| --- | ---: | ---: | ---: | ---: | --- |
| ordinary, player-only (canonical) | 220 | **13** | **0** | **0** | `[0, 1]` |
| ordinary (phase15) | 200 | 12 | **0** | **0** | `[0, 1]` |
| **wave5** (≤5-enemy authored waves) | 200 | 12 | **0** | **0** | `[0, 1]` |
| contrasting `$D021` = 7 (yellow) | 200 | 12 | **0** | **0** | `[0, 1]` |
| dense (16 synthetic objects) | 200 | — | **0** | **0** | — |
| lowest-Y (8 sprites @ Y=245) | 200 | — | **0** | **0** | — |
| **divider-1-like** (fine advances every frame) | 200 | **24** | **0** | **0** | `[0, 1]` |
| **stage wrap** (`SCROLL_ROW` 12 → 0 → 419, seeded) | 320 | **19** | **0** | **0** | `[0, 1]` |

Per-frame edge series (ordinary): the lowest terrain edge stays **rock-steady at
raster 246** for every fine phase and every coarse transition — no jump. A/B:
the blank-spacer baseline oscillated 239↔246 with a 7-px snap; the RSEL=1 +
overflow variant oscillates 247↔254 with a 7-px snap (§7.2).

Seam strips (`build/rsel0of-canon/phase15-evidence/`): the terrain scrolls
continuously into a steady raster-246 border crop at the bottom and a steady
raster-55 border crop at the top; the feature bands descend 1 px/frame through
the fine 7→0 step with no discontinuity. The RSEL=0 top border shows **solid
`$D020` black** (no open-top-border idle stripes — a cosmetic bonus over the
baseline).

**Q14 — top / body / bottom temporal diffs all zero where expected: YES**, on
every workload above, across 13 / 19 / 24 coarse transitions and a full stage
wrap.

## 7.2 `GAMEPLAY_RSEL = 1` + overflow rows — [MEAS] (the AMBER toggle)

| band | 7→0 diffs |
| --- | --- |
| body (rasters ~56-246) | **0** — the 7-px body pop is eliminated |
| top overflow edge (rasters 52-55) | non-zero — ~4 px residual oscillation |
| bottom overflow edge (rasters 247-250) | non-zero — ~4 px residual oscillation |

Edge series: 247↔254 with a 7-px snap of *row 24's own bottom edge*, straddling
the aperture bottom (250) / open-border zone. Mirror residual at row 0's top.
This is the "one edge fixed, the other needs a bigger change" shape — except here
*both* extreme edges have the residual and the fix for both is the same: crop
them, i.e. RSEL=0.

---

# 8. Q15-Q18 — timing / cadence / scheduler

**Q17 — `[19656]` exact:** **YES.** `tools/vice_scroll_test.py --physical
--trace` + `tools/check_raster_capture.py` (the trusted oracle), `GAMEPLAY_RSEL
= 0`:

| Run | frames | `frame_cycle_deltas` | catchups | replay | service_failure | sprite_start_miss |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| ordinary | 220 | **`[19656]`** | 0 | 0 | **0** | **0** |
| seeded-scroll (waves firing) | 260 | **`[19656]`** | 0 | 0 | **0** | **0** |
| through the `SCROLL_ROW` 0 wrap | 320 | **`[19656]`** | 1 | 4 | **0** | **0** |

**Q18 — scheduler / mux diagnostics clean: YES.** 0 service failures, 0
sprite-start misses on every run. The 1 catchup / 4 replays on the 320-frame
seeded-wrap run are the scheduler's normal overdue-event handling under the
`--seed-scroll` transient (the harness force-jumps `SCROLL_ROW`, so turret
streaming and a couple of BUILD frames run long) — **[A/B]** the same
`--dense` synthetic stress produces **identical** `catchups 1253 / replay 89`
on the *baseline* build `d547c80` (`sha 6e9d3046`), so this is pre-existing
load behaviour, not a regression.

> Caveat: `tools/phase15_geometry_test.py`'s own `check_raster_capture` numbers
> are an unreliable trace-parse artifact (its trace-label + `store d011/d012`
> interleaving confuses `check_raster_capture`'s line-anchored regexes) — it
> reports spurious `service_failure` on the **baseline** build too. Only the
> `vice_scroll_test.py --physical --trace` pairing above is trusted for the
> raster oracle. `phase15_geometry_test.py` is used only for screenshots + the
> edge oracle, which read pixels, not the trace log.

**Q15 — added coarse-frame cycle cost:** `shiftBackgroundUpper` +40 B (one row
of 40 abs LDA/STA pairs ≈ +320 cyc). `shiftBackgroundLower` +40 B (≈ +320 cyc).
`renderStageRowToScreen(0)` costs the same as `(1)`. **[MEAS]** measured net on
the upper phase: `bgUpperCopied` raster 233 (unchanged), `bgUpperReady` raster
**288** (blank-spacer baseline / feasibility report: ~271-272) → **≈ +16 rasters
≈ +1000 cyc** on the coarse-upper phase (the byte-copy plus a little more from
`renderStageRowToScreen(0)` taking the `wrapBgLogicalRow` fold path near the
stage wrap). `bgLowerReady` median raster **20** (unchanged), max 89.

**Q16 — worst measured coarse completion raster:** `bgUpperReady` = **raster
288** (constant across 13 coarse frames), i.e. ~23 rasters before frame end and
~180 rasters (≈ +311 wrap) before the beam re-fetches matrix rows 1..12 next
frame (badline ~144-151). `bgLowerReady` worst = raster **89**, well before the
row-14 badline (~152-159). Both deadlines are met with large margin, and
`check_raster_capture` confirms 0 misses / `[19656]`.

Memory: `$4000` segment `$4000-$56ab` → `$4000-$5879` (**+462 B**; ~391 B
headroom to the `$5a00` terrain-charset segment). `$2920` background segment
`+20 B`. `raster_scheduler.asm` `+3 B`. All within the assembler guards (build
clean).

---

# 9. Q19 — wave5 gameplay

**[MEAS]** `wave5` (the non-destructive RAM-only fixture in
`tools/phase15_geometry_test.py` — clamps the 16-entry `waveTrigCount` table to
`min(v, 5)`; the generated Level-1 assets on disk are untouched;
`SCROLL_ROW` seeded to 382 so authored waves fire in-window, `max_objects`
reached 7-8): edge oracle **body 0 / edge 0**, 12 coarse transitions, all
`coarse_edge_median_jump [0,1]`. Cadence `[19656]`, scheduler clean (seeded-wave
canonical run, §8). The scroll edge behaves identically with ≤5 combat sprites
present as with player-only — the fix is object-independent. Known 6-enemy
overload flicker is a separate, pre-existing mux-load constraint and is not a
scroller-experiment result.

---

# 10. Q20 — editor viewport / contract change needed later

**None required for this task**, and none made. `STAGE_START_ROW` is unchanged;
matrix row 1 still anchors `SCROLL_ROW`; world/logical turret and wave-trigger
rows are unchanged; the bottom-origin semantics are preserved.

For a follow-up: the editor (`tools/level_editor/engine_data.py`,
`VIEWPORT_ROWS`) currently models a 23-row aperture. The engine now presents a
continuous **24-row-equivalent** field (row 0 + rows 1..23 + row 24 slivers).
If the editor overlay should reflect that, bump `VIEWPORT_ROWS` 23→24 (a display
constant only — the bottom-origin anchor formula
`SCROLL_ROW = STAGE_LOGICAL_ROWS − VIEWPORT_ROWS` is already parameterised, but
**do not** change it here as it would move authored bottom-origin). This is a
cosmetic editor-overlay change with no world-coordinate impact; defer to a
dedicated editor pass.

---

# 11. Q21 — is the RSEL=1 architecture safe to retain?

**Not as the gameplay display mode, for this scroller.** RSEL=1's 25-row
aperture is 4 px wider at each end than the content the finite 25-row fetch can
keep continuous (rows 0..24 with rows 0/24 as overflow). Those 4 px at each end
can only ever show the overflow rows' *own* discontinuous outer edges, and RSEL=1
provides no crop for them. RSEL=1 offered no fetch benefit over RSEL=0 (RSEL does
not gate DMA) — its only purpose in Phase 1.5 was to open the lower border for a
bottom sprite HUD, which Phase 1.5 itself found unviable (deep-lower-border
sprite corruption). **Recommendation: retain `GAMEPLAY_RSEL = 0`.** The Phase-1.5
wins that matter — no legacy character HUD, no invalid BMM+ECM separator, a
single uniform-YSCROL display with no mid-frame `$D011` split — are all kept.
The `GAMEPLAY_RSEL = 1` path stays in the tree (one constant) for any future
work that needs the wider aperture and can tolerate / re-mask the 4-px edges.

---

# 12. Q22 — next border-HUD experiment

The scroller edge is now genuinely clean, so HUD work can resume. Per the brief's
own steer and the Phase-1.5 findings:

**Next: a top-border static sprite-HUD canvas proof.**

- The deep *lower* border sprite path is corrupt below raster ~256 on both VICE
  cores (Phase-1.5) — do not target it.
- With `GAMEPLAY_RSEL = 0` the top border is *closed* (solid `$D020`). Opening it
  for HUD sprites needs the Slap-Fight dodge (RSEL 0→1 before the raster-247
  bottom SET, RSEL 1→0 before raster 251) — which, being single-FF, will also
  open the *bottom* border and re-widen the bottom aperture toward the RSEL=1
  residual. So the top-HUD experiment must **re-run this report's temporal edge
  battery** with the border open, and either (a) accept a ~4 px bottom overflow
  residual while the border is open, (b) add a narrow beam-raced bottom re-close,
  or (c) keep the HUD canvas in the top border only during a phase where the
  bottom is still cropped. Prove the sprite canvas renders cleanly at Y ≈ `$0c`
  (raster ~12-33, inside the normal sprite window) first; defer dynamic content,
  `HUD_SAFE_RASTER`, and the gameplay→HUD slot hand-off.

---

# 13. Exact test commands / harnesses

```
# build (GAMEPLAY_RSEL = 0 in src/main.asm)
java -jar …/KickAss.jar src/main.asm -odir build -o build/shooter.prg -vicesymbols
c1541 -format "19656,01" d64 build/shooter.d64 ; c1541 build/shooter.d64 -write build/shooter.prg 19656

# trusted cadence / scheduler oracle (needs a background x64sc on -remotemonitor :6510)
python3 tools/vice_scroll_test.py --physical --trace --frames 220 --out build/rsel0of-canon
python3 tools/vice_scroll_test.py --physical --trace --seed-scroll 12 --frames 320 --out build/rsel0of-wrap0   # stage wrap
python3 tools/check_raster_capture.py build/rsel0of-canon
python3 tools/check_raster_capture.py build/rsel0of-wrap0

# temporal edge oracle (RSEL=0 aperture, turret columns excluded)
python3 tools/phase15_geometry_test.py --case ordinary|wave5|contrast|dense|lowy|div1 --frames 200 --out build/p15-<case>
python3 tools/check_scroll_edges_rsel1.py build/<capture> --aperture 55 246 --body-top 56 --last-row-top 246

# scratchpad instruments (non-repo): rowtrace.py (row-state), edgeseries.py (edge series), evidence.py (seam strips)
```

New / changed this session:
- `src/main.asm`, `src/raster_scheduler.asm` — the overflow-row engine change + `GAMEPLAY_RSEL` toggle.
- `tools/check_scroll_edges_rsel1.py` — `--aperture TOP BOTTOM` override; authored-turret-column exclusion.
- `tools/phase15_geometry_test.py` — `--case div1` now advances the fine phase every frame (was freezing it).
- `docs/rsel1-scroll-overflow-worklog.md` — session worklog.

---

# 14. Caveats

1. The `GAMEPLAY_RSEL = 1` toggle is AMBER (§7.2) and is not the shipped config;
   it is retained for future aperture-flexible work only.
2. `tools/phase15_geometry_test.py`'s `check_raster_capture` output is unreliable
   (§8 caveat) — always use `vice_scroll_test.py` for that oracle.
3. Player death/respawn not re-run (build carries `DEBUG_PLAYER_INVULNERABLE = 1`,
   as noted in prior reports); the coarse routines are inert to `PLAYER_STATE`.
4. NTSC untested — PAL authoritative; NTSC border compares and badline limits
   differ and would need their own derivation.
5. The diagnostic lower-border marker sprite (`borderOpenHook`) remains in the
   tree but under `GAMEPLAY_RSEL = 0` it sits in the closed bottom border and is
   clipped/invisible — expected, and explicitly out of scope for this task.
6. Editor overlay still shows 23 rows (Q20) — cosmetic, deferred.

---

# 15. Housekeeping

**No commit, no push.** `HEAD` still `d547c80`. Working tree:
`src/main.asm`, `src/raster_scheduler.asm`, `tools/check_scroll_edges_rsel1.py`,
`tools/phase15_geometry_test.py` (all `M`) + `docs/rsel1-scroll-overflow-worklog.md`
+ this report (`??`). `build/` is gitignored. The MiSTer / real-hardware build is
`build/shooter.d64` / `build/shooter.prg` (`sha256(prg) = b8fdfe495a797d31…`),
Level 1 straight into PLAYING. VICE was launched head-less/background and killed
on exit; never foregrounded; no `open -a`. The generated Level-1 assets on disk
were not modified.
