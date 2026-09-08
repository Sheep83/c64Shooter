# Bottom-Border HUD — Phase 1.5: Remove Legacy Top HUD, Establish True RSEL=1 Gameplay, Prove Bottom-Border Geometry

**19656 / c64Shooter — PAL C64 vertical shooter.** Geometry / border proof only.
No commit, no push. VICE (`x64sc` + `x64`) launched head-less / background
(`-remotemonitor`, `Popen`, `DEVNULL`), never foregrounded, no `open -a`.

Legend: **[OBS]** observed in source · **[MEAS]** measured this session ·
**[A/B]** measured against a clean comparison build · **[INF]** inference.

---

# TL;DR / verdict

| Aspect | Result |
| --- | --- |
| Legacy top character HUD removed from gameplay | **GREEN** |
| Invalid BMM+ECM separator / top glitch removed | **GREEN** |
| Genuine RSEL=1 / 25-row geometry throughout the visible field | **GREEN** |
| No Phase-1-style RSEL 0→1 lower-edge setup | **GREEN** |
| Lower border opens reliably via the late RSEL 1→0 dodge | **GREEN** |
| RSEL=1 restored safely for the next frame | **GREEN** |
| Matrix row 24 (and row 0) remain blank $D021 spacers | **GREEN** |
| Exact PAL cadence `[19656]` + scheduler/mux diagnostics | **GREEN** (no new failures) |
| Dense / lowest-Y sprite gameplay correct | **GREEN** |
| No multiplexer rewrite / protected scroller redesign | **GREEN** |
| **Lowest visible terrain temporally stable while scrolling** | **RED** — a 7 px snap at *both* the top and bottom terrain edges on every fine-7→0 coarse transition (≈3×/s at divider 2), full width, visible against any non-black $D021. Fine phases 0↔7 themselves are flawless; the terrain *body* (~21 rows) is flawless. |
| Diagnostic lower-border sprite below raster ~256 | **RED** — the deep-border garble **persists**, byte-identical on `x64sc` and `x64`; the Phase-1 "RSEL history caused it" hypothesis is **disproven**. |

## Overall: **AMBER — task decision path C.**

The RSEL=1 conversion is a clean, fully-measured success and a real architectural
improvement (no invalid VIC mode, no fixed character HUD, no mid-frame $D011
split, exact `[19656]`, ~70 fewer bytes, one fewer scheduled hook body). **But it
un-masks a pre-existing scroll-edge defect that the retired RSEL=0 4-line edge
crops were hiding.** Per this task's own rule — *"If the bottom terrain still
visibly wobbles/tears, the pass is AMBER/RED regardless of static screenshot
analysis"* — and its decision tree, the result is **case C: do not build the
Phase-2 HUD hand-off. Root-cause the scroll/display geometry (the finite
25-row-fetch coarse-seam snap, at both edges) first.**

The diagnostic-sprite result is reported **separately** (as the brief instructs):
the *display geometry* conversion is otherwise GREEN; the *lower-border
sprite-HUD feasibility* is RED and now known to be a genuine VIC-II / VICE
deep-lower-border sprite limitation, not a Phase-1 artefact.

---

# 1. Start state — branch / HEAD / working tree

| | |
| --- | --- |
| Branch | `terrain-asset-workshop` (checked out; **not** switched) |
| HEAD | `1cd8513f3327d9775b024ac3d2cb4e85926e6553` — *"First bottom border HUD experiment"* |
| Working tree at start | **clean** |
| HEAD build | `sha256(build/shooter.prg) = 6272b25e1d342181ecfc085bf79283c5ec4811e936184d4ffc01f4b759730e46` — builds with `#define BORDER_PROOF_ENABLE` active (matches the Phase-1 report's "experiment ON" hash). |
| Toolchain | KickAssembler 5.25 (`/Users/brianmorrice/Dev/Tools/KickAssembler/KickAss.jar`) · VICE `x64sc` **and** `x64`, PAL, `-warp` · `c1541` for the `.d64`. |
| Prior docs read in full | `/reports/bottom-border-hud-phase1-border-proof-report.md`, `/reports/bottom-border-hud-feasibility-investigation.md`, `/reports/hud-rsel-display-geometry-investigation.md`, `docs/scroll-edge-investigation.md` (via cross-reference). |

## Phase-1 changes present at HEAD (commit `1cd8513`)

- **`src/main.asm`** — `#define BORDER_PROOF_ENABLE` toggle (line 10); guarded
  `BORDER_MARKER_SPRITE` (64 B all-`$ff` solid marker, `$1fc0`, pointer `$7f`).
- **`src/raster_scheduler.asm`** — guarded `RASTER_EVENT_BORDER = 3`,
  `RASTER_BORDER_LINE = 240`, marker consts, `RASTER_BORDER_PENDING`, dispatch of
  the terminal border event through `rasterIRQ` / `dispatchRasterEvents`, and
  `borderOpenHook` performing the **hybrid** dodge: marker arm + **RSEL 0→1 at
  raster 243** + **RSEL 1→0 at raster 250**, with the playfield left permanent
  RSEL=0.
- **`tools/vice_border_phase1.py`, `tools/border_phase1_analyze.py`** — new
  Phase-1 harnesses.

Everything else (mux, BUILD/LIVE plan, `applyLiveRasterBatch`, sort, collision,
coarse routines, stage decoder, level data) was unchanged from the pre-experiment
engine.

---

# 2. What was removed / disabled, and what was deliberately kept

Source diff: **`src/main.asm` +72 / −? , `src/raster_scheduler.asm` −143 net** —
a net code *reduction*; `raster_scheduler.asm` footprint `$6000–$63cb` →
`$6000–$6341`.

## 2.1 Retired display / HUD presentation machinery — [OBS]

| Location | Removed / changed |
| --- | --- |
| `src/main.asm : init` (`~423`) | Stopped clearing $D011 bit 3. Now `lda $D011 / ora #%00011000 / sta $D011` — asserts **RSEL=1, DEN=1**, preserves YSCROL / raster-compare MSB. |
| `src/raster_scheduler.asm : rasterDisplayHook` | The entire HUD/terrain **$D011 write chain** deleted: `$11` (r59), `$71` (r62, **invalid BMM+ECM band — the "top glitch"**), `$70\|fine` / `$77` (r63/64, invalid), `$10\|fine` (r70/71). Also deleted: `rasterHblankDelay`, the `rasterWaitHudEnd` / `rasterWaitPlayfield` / `rasterWaitBadline` poll loops, the `!fine7` / `!badline70` special cases, the two page-cross `.error` guards. The hook body is now `lda #0 / sta RASTER_DISPLAY_PENDING / rts` — a scheduled **no-op** at ~raster 56 (the dispatcher's "merge with the next sprite batch" plumbing is deliberately left intact so the sprite scheduler is not touched). |
| `src/raster_scheduler.asm : rasterFrameReset` (`~136`) | `lda #$17 / sta $D011` → `lda RASTER_DISPLAY_FINE / ora #$18 / sta $D011`. Installs the whole-frame display state (RSEL=1, DEN=1, YSCROL = presented fine phase) at **line 0/1**. |
| `src/raster_scheduler.asm : publishRasterPlan` (`~70`) | Same `$17` → `RASTER_DISPLAY_FINE \| $18` change. **Required:** `publishRasterPlan` runs *every frame* via `armFirstBatch` (`main.asm:3515`) at ~line 17; its old `$17` seed was clobbering the fine phase to a constant once the display hook stopped correcting it. |
| `src/main.asm : initFixedHud` | Rewritten. Was: build 18 private HUD glyphs, paint matrix row 0 with `HUD_GLYPH_BASE`, stamp `"SCORE ....."` + `"FREE ....."`, call `displayScore`. Now: fill matrix **row 0 and row 24** with screen code `$20` (ROM-charset space, all-zero bitmap → solid $D021 for any palette). Nothing else. |
| `src/main.asm : refreshScoreIfDirty` | Was: `if SCORE_DIRTY: displayScore` (writes `HUD_SCORE_CELL` = matrix row 0). Now: just clears `SCORE_DIRTY`. |
| `src/raster_scheduler.asm : borderOpenHook` | The **RSEL 0→1 poll-to-243 write is deleted.** Marker-arm block unchanged; then poll to raster 250 and `$D011 &= ~$08` (RSEL 1→0). |

## 2.2 Kept intentionally (score / state bookkeeping)

- `SCORE_LO/HI`, `awardKillScore`, `SCORE_DIRTY`, `PLAYER_LIVES`,
  `setupScoreDisplay` / `setupLivesDisplay` (their row-0 label writes are
  overwritten by `initFixedHud`'s spacer fill, which runs last in
  `initBackground`), `displayLives` (already early-outs during PLAYING).
- `updateCycleDebug` / `displayCycleMinimum` (already not called).

## 2.3 Now-dead presentation-only code (retained, not deleted — kept bounded)

| Symbol | Status |
| --- | --- |
| `displayScore` | **Unreachable during gameplay** — its only two callers (`initFixedHud`, `refreshScoreIfDirty`) no longer call it. Retained (a future HUD will want the binary→decimal digit routine). |
| `hudStockCodes`, `fixedHudText`, `fixedHudFreeLabel`, `HUD_G_*` consts, the `HUD_GLYPH_BASE`/`HUD_DIGIT_GLYPH` `.if` guards | Unreferenced data / compile-time asserts. Harmless; retained to keep the diff bounded. |
| `RASTER_DISPLAY_NORMAL`, `RASTER_DISPLAY_LATE` (state bytes) | Now always 0. Retained for capture-tool symbol parity (`vice_border_phase1.py` reads `RASTER_DISPLAY_LATE`). |
| `RASTER_EVENT_DISPLAY`, `RASTER_DISPLAY_LINE`, `RASTER_DISPLAY_PENDING`, `rasterDisplayHook` | The DISPLAY event still fires once per frame at raster 56 and does ~10 cycles of nothing. A tidy follow-up could excise it from `dispatchRasterEvents`; left in place here to avoid editing the sprite dispatcher (criterion 13). |

**No protected architecture was touched** (see §17).

---

# 3. New display state — exact $D011 values and timing

## 3.1 Whole-frame gameplay state — [MEAS] (`store d011` trace, `x64sc`)

`$D011 = RASTER_DISPLAY_FINE | $18` — DEN=1 (bit 4), RSEL=1 (bit 3), YSCROL =
presented fine phase (bits 0-2), raster-compare MSB (bit 7) = 0. Concrete values
seen: `$18` (fine 0) … `$1B` (fine 3) … `$1F` (fine 7).

Written **twice per physical frame**, both before the first badline (`48+fine`):

| Writer | Raster : cycle | Purpose |
| --- | --- | --- |
| `rasterFrameReset` (`$60c1`) | **line 1 : cyc ~9–22** | frame-0 IRQ compare; this is the **RSEL 0→1 restore** after the previous frame's lower-border dodge, well before the line-51 top compare. |
| `publishRasterPlan` (`$603f`) | **line ~17 : cyc ~46** | re-armed every frame by `armFirstBatch`; installs the identical value so it cannot clobber the fine phase. |

No further $D011 write occurs until `borderOpenHook`. **There is no mid-frame
HUD/terrain split write.**

## 3.2 Lower-border open — the single late RSEL 1→0 dodge — [MEAS]

`borderOpenHook` (`$61e4`), fired from an IRQ compare at `RASTER_BORDER_LINE = 240`:

```
$61e4  LDA #$00 / STA RASTER_BORDER_PENDING          ; consume the event
$61e?  LDA $D015 / AND #$80 / BNE (skip)             ; slot 7 in gameplay use? -> skip the marker
       ... (marker slot-7 ptr/colour/X/Y/$D010/$D015 arm, only if slot 7 idle) ...
!wait250:
       LDX $D012 / CPX #250 / BCC !wait250-          ; poll to raster 250
       LDA $D011 / AND #%11110111 / STA $D011        ; ** RSEL 1 -> 0 **
$6223  RTS  (borderOpenRestored)
```

| Event | Raster : cycle | `$D011` | Decode |
| --- | --- | --- | --- |
| IRQ entry (`borderOpenHook`) | 241–242 | — | (`RASTER_BORDER_LINE 240` + latency) |
| **RSEL 1 → 0** | **250 : cyc ~18–23** | `$1B → $13` | RSEL cleared; **YSCROL / DEN / BMM / ECM preserved** (read-modify-write `AND #$F7`). No ECM. |
| `borderOpenRestored` (RTS) | ~250 | — | whole hook lives in raster ~241–250, in the blank-row-24 / border region. |

Across all 8 fine phases the RSEL 1→0 write always lands at raster 250 (`x64sc`
`border_trace`: `done_raster = [250]×15`). Moving the poll target is not
cycle-fragile in this window (Phase-1 established the same).

## 3.3 Border flip-flop outcome — [INF] from VIC-II rules + [MEAS]

- Gameplay is RSEL=1 the entire frame, so the **RSEL=0 bottom close compare at
  raster 247 never applies.**
- The RSEL 1→0 write at raster 250 is latched **before cycle 63 of raster 251**,
  so the **RSEL=1 bottom close compare at raster 251 is missed.**
- ⇒ the vertical-border flip-flop is **never set** this frame → it stays reset
  from the previous frame's line-51 top compare → **both the lower AND the upper
  border stay open** (single-FF VIC-II; expected — see §8).
- `rasterFrameReset` re-asserts RSEL=1 at line 1, and the line-51 top compare
  (DEN=1) keeps the FF reset. **[MEAS]** no RSEL=0 lingers past raster 250 into
  the next frame.

---

# 4. Resulting visible raster ranges — [MEAS] (`x64sc`, fine-5 example; ±7 with fine phase)

```
raster ~16 .. ~52   OPEN TOP BORDER  (single-FF consequence)
                    - above the first badline: flat $D021
                    - then idle-graphics stripes ($D020/$D021 alternating, $3fff)
raster ~53 .. ~60   MATRIX ROW 0  = blank $D021 spacer  (solid backdrop, no fg)
raster ~61 .. ~239  TERRAIN  (matrix rows 1..23), scrolls with YSCROL = fine
raster ~240 .. ~252 MATRIX ROW 24 = blank $D021 spacer  (solid backdrop, full width)
raster ~253 ..      OPEN LOWER BORDER  - idle-graphics stripes
raster ~254 .. ~273   diagnostic marker sprite region  (GARBLED - §14/§15)
```

The RSEL=1 aperture proper is raster 51..250; the lower border is held open
below it. First non-$D021 / idle raster below the terrain: **~253** every frame,
every phase, every load — the border open is rock-solid (§13).

---

# 5. Before / after raster diagram

```
BEFORE — HEAD (permanent RSEL=0 + Phase-1 hybrid dodge)   AFTER — Phase 1.5 (genuine RSEL=1)
---------------------------------------------------------  --------------------------------------------------
r16-50   BLACK BORDER (RSEL=0 top crop)                    r16-~52  OPEN TOP BORDER (idle stripes)  <- single-FF
r51-54   BLACK BORDER (RSEL=0 top crop, redundant)                  consequence of the deep bottom open
r55-62   FIXED CHAR HUD  (matrix row 0, YSCROL 7)          r53-60   matrix row 0 = BLANK $D021 spacer
r63-70   INVALID BMM+ECM SEPARATOR (forced black) <-glitch (removed entirely)
r71-246  terrain rows 1..23 (RSEL=0, YSCROL=fine)          r61-239  terrain rows 1..23 (RSEL=1, YSCROL=fine)
r243     hybrid RSEL 0->1  (Phase-1 only)                  (no 0->1 write)
r244-250 matrix row 24 briefly visible (Phase-1 only)      r240-252 matrix row 24 = BLANK $D021 spacer
r247-250 BLACK BORDER (RSEL=0 bottom crop)                          (visible; absorbs idle strip, NOT the
                                                                     coarse-step content snap -- §11)
r250     hybrid RSEL 1->0                                  r250     RSEL 1 -> 0  (dodge the r251 close)
r251+    LOWER BORDER (open, Phase-1) + garbled marker     r253+    LOWER BORDER (open) + garbled marker
r0-1     $D011 = $17 (RSEL 0)                              r1       $D011 = $18|fine (RSEL 1 restored)
```

---

# 6. Terrain geometry / usable rows — [OBS] + [MEAS]

- The scroller fetches **25 matrix rows (0..24)** with no 26th fetch (unchanged).
  Matrix **rows 1..23 = terrain** (23 rows), written by `renderStageRowToScreen`
  / `prepareBackgroundCoarse`; `shiftBackgroundUpper` writes dst rows 2..12,
  `shiftBackgroundLower` dst rows 14..23. **Rows 0 and 24 are never written by
  the scroller** — only `initFixedHud` — so the one-time blank fill is permanent.
- **Temporal cleanliness (§11):** matrix rows ~2..22 (rasters ~64..231) —
  **≈ 21 rows — are temporally flawless** through every fine phase and every
  coarse transition. Matrix row 1 (top) and matrix row 23 (bottom) each carry a
  ~7 px edge that snaps once per coarse cycle.
- **Reclaiming matrix row 0 as a 24th terrain row** (the "C′" target) requires a
  scroller row-range change (`shiftBackgroundUpper` 12..2 → 12..1,
  `renderStageRowToScreen` / coarse constants, `STAGE_START_ROW`, editor
  `VIEWPORT_ROWS`). It is **out of scope** here (criterion 13; "do not redesign
  the background scroller merely to gain one row") and — crucially — **would not
  fix the bottom pop**, which is about row 23→24, independent of row 0.

**Answer: 23 terrain rows are fetched and displayed; ~21 of them (the body) are
genuinely temporally stable; rows 1 and 23 each have a coarse-step edge pop.**

---

# 7. Matrix-row-24 invariant — re-verified [MEAS]

- `initFixedHud` writes `BG_SCREEN_A + 24*40 .. +39 = $20`. Runtime dump of
  matrix row 24: **all `$20`**, every frame. Colour RAM for row 24 is left at the
  stage-global `TERRAIN_COLOUR_RAM` (not written).
- No scroller routine addresses row 24 (`shiftBackgroundLower` stops at dst 23;
  `restoreCrossingRow` writes row 13; `renderStageRowToScreen` range is 1..23).
- Tested with a **strongly contrasting non-black `$D021` = 7 (yellow)**: the row-24
  band renders as **solid yellow, full 320 px width**, with no foreground pixels
  and no per-fine-phase artefact *within* a fine phase — confirming it is a true
  blank spacer and not black-on-black concealment. (It still *breathes* at the
  coarse step — §11.)

Matrix **row 0** is now the same: permanent blank `$20`, verified all-`$20` at
runtime.

---

# 8. The open top border — expected single-FF consequence

Dodging the bottom border-set compare leaves the vertical-border flip-flop reset
through the top of the next frame as well (the VIC-II has one vertical border FF;
it is *set* only at a bottom compare, *reset* at a top compare). So rasters
~16..~52 show display/idle output rather than `$D020` border:

- above the first badline (`48+fine`): flat `$D021`;
- once the sequencer has run and gone idle: `$3fff` idle-graphics stripes
  (`$D020`/`$D021` alternating in MC).

This is **unavoidable** with the RSEL-dodge technique and matches the Phase-1
finding. It is cosmetic (no gameplay pixel depends on it) but **not pretty** with
a non-black palette — a Phase-2 concern (a top sprite-HUD canvas, or a top
re-close, would cover it; see §18).

---

# 9. Cadence & scheduler diagnostics — [MEAS] (trusted oracle)

`tools/check_raster_capture.py` on `tools/phase15_geometry_test.py` captures
(≥200 physical PAL frames each), border proof **ON**:

| Case | `frame_cycle_deltas` | catchups | replay | service_failure | sprite_start_miss |
| --- | --- | --- | --- | --- | --- |
| ordinary (player only) | **`[19656]`** | 0 | 0 | **0** | **0** |
| **wave5** (≤5-enemy authored waves, seeded scroll) | **`[19656]`** | 0 | 0 | **0** | **0** |
| dense (16 stationary legal objects) | **`[19656]`** | 0 | 0 | **0** | **0** |
| lowy (8 gameplay sprites @ Y=245, synthetic) | **`[19656]`** | **8** | 0 | **0** | **0** |
| contrast (`$D021` = 7) | **`[19656]`** | 0 | 0 | **0** | **0** |
| div1 (SCROLL_FRAME_COUNT pumped) | **`[19656]`** | 0 | 0 | **0** | **0** |
| wave6 (authored waves as exported — overload demo) | **`[19656]`** | 0 | 0 | **0** | **0** |

Plus a 1112-frame `vice_border_phase1.py` run: `incomplete / replay / catchups /
display_late = 0 / 0 / 0 / 0`.

- **Exact PAL cadence `[19656]` is preserved everywhere.** (The
  `vice_border_phase1.py` per-frame `cadence_run` shows ±3 spread — that is its
  known monitor-poke sampling jitter, documented in the Phase-1 report; the
  trusted `--physical` oracle above is exact.)
- **lowy** (a deliberately pathological synthetic load — 8 sprites at the lowest
  legal Y, every mux slot marked unavailable): **8 dispatcher catchups over 200
  frames, 0 sprite-start misses, cadence exact.** This is the dispatcher's
  overdue-event handling (`!due` → `inc RASTER_CATCHUPS`) working as designed
  (AGENTS.md: "explicitly handle overdue raster events"); the assignments still
  land in the correct physical frame. It is a *synthetic* stress case outside the
  supported scrolling-gameplay envelope and is **not a Phase-1.5 regression** —
  `rasterDisplayHook` is now a ~10-cycle no-op at raster 56, far from the
  raster-233 low-Y batch.

---

# 10. Workload / fixture used for each test class

| Test class | Workload |
| --- | --- |
| **Normal pass/fail scrolling / temporal edge tests** | `tools/phase15_geometry_test.py --case ordinary` (authored Level 1, player only) **and** `--case wave5`. |
| **`wave5` (≤5-enemy scrolling combat)** | **Non-destructive runtime fixture**: after load, the 16-entry `waveTrigCount` **RAM table** is clamped `min(v, 5)` (measured before `[6,6,6,5,6,6,6,5,5,6,6,6,5,5,5,6]` → after all ≤5). `SCROLL_ROW` seeded to 382 so authored triggers fire inside the capture window (`max_objects` reached 7–8). **The generated level assets on disk are never touched.** The fixture lives only in `tools/phase15_geometry_test.py` and applies only when `--case wave5` is passed. |
| **Low-Y sprite pressure** | `--case lowy`: `OBJECT_Y = [150] + [245]×7 + [244..234]`, 16 active objects. Synthetic. |
| **Dense synthetic** | `--case dense`: 16 stationary legal objects, 8 tight batches. Synthetic. |
| **Known 6-enemy overload demo** | `--case wave6`: authored waves **as exported**. In the 200-frame window it did not stack two 6-waves (`max_objects` 8–9); cadence stayed `[19656]`. Any resulting sprite/border flicker under a genuine 6-wave stack is **expected overload behaviour** and is **not** counted against this verdict, per the brief. |
| **Contrasting backdrop** | `--case contrast`: `$D021` forced to 7 (yellow) every frame. |
| **divider-1-like** | `--case div1`: `SCROLL_FRAME_COUNT` pumped to 0 every frame. |

The bottom-edge pop (§11) appears **identically** under `ordinary` and `wave5`,
so it is a pure display-geometry property, **not** a sprite-load overload. Per
the brief that makes it a genuine failure to investigate, not "expected overload".

---

# 11. THE MOST IMPORTANT RESULT — lowest visible terrain edge while scrolling

## 11.1 Method (temporal, not static)

Three independent temporal instruments on `tools/phase15_geometry_test.py`
`--physical` captures (200 consecutive PAL frames each, all 8 fine phases,
12 coarse 7→0 transitions per capture):

1. **`tools/check_scroll_edges_rsel1.py` (new)** — model-free: every observed
   pixel must equal the pixel one line above it in the previous frame (1 px
   scroll), excluding sprite-covered samples and the one genuinely-new entering
   line. Diffs are bucketed by raster band so the *body* and the *last terrain
   row* are judged separately.
2. **Per-frame lowest-terrain-edge raster series** — for six columns, the lowest
   raster that is neither `$D021` nor near-black; printed with fine phase and
   `SCROLL_ROW`.
3. **Magnified consecutive-frame seam strips** across a 7→0 step (rasters 48..74
   top, 226..258 bottom, 3× zoom, 12 frames) — saved under
   `build/p15-*/phase15-evidence/`.

A/B against a **clean RSEL=0 HEAD** build (`#define BORDER_PROOF_ENABLE`
commented, `sha256 2a605428…`, byte-identical to the pre-experiment engine).

## 11.2 Result — [MEAS]

**Instrument 1 (`check_scroll_edges_rsel1.py`), ordinary + wave5 + contrast:**

| Transition | body band (r ~64..231) | last-row band (r ~232..250) |
| --- | --- | --- |
| every fine step `0↔7` (`0→0`, `0→1`, … `6→7`) | **0 diffs** | **0 diffs** |
| **`7→0` (coarse)** | diffs **only at rasters ~60..63** (top seam) | diffs at rasters **~240..247** (bottom seam) |

`coarse_edge_median_jump = -7` on every coarse step.

**Instrument 2 (per-frame lowest-edge series), ordinary:**

```
fine 0 -> edge raster 239
fine 1 -> 240   ... +1 per fine step ...
fine 7 -> 246
[coarse 7->0]   edge SNAPS 246 -> 239   (a 7 px jump UP; exposes the blank spacer)
fine 0 -> 239 ...
```

Identical under `wave5` (edge 246→239 at every 7→0). Under contrast (`$D021`=7)
the same, and the yellow row-24 band visibly **grows ~7 px taller for one coarse
cycle then shrinks** — a pulsing band at the bottom of the play area.

**Instrument 3 (seam strips):** the light-grey terrain band's lower edge
descends over fine 0→7, then at frame N→N+1 (fine 7→0) **abruptly retreats ~7 px**
and the $D021 spacer band jumps up to fill it; then it descends again. The **top**
seam does the mirror image (the terrain's *top* edge and the open-top-border
idle-stripe band snap ~7 px at the same coarse step).

**A/B — clean RSEL=0 HEAD:** the lowest-edge series is **rock stable at raster
246 for every fine phase and every coarse transition — zero jump.**

## 11.3 Why

- In RSEL=0 the aperture bottom (raster 246) sits **inside** the 25-row fetch
  stack — matrix rows ~21..24 fall below the crop — so terrain always fills to
  the crop and the outgoing-row snap happens in the border, invisibly. This is
  exactly what `f6e9620` ("Conversion to 24-row VIC mode") and
  `docs/scroll-edge-investigation.md` describe.
- In RSEL=1 the aperture (raster 51..250, border open below) extends **past the
  true bottom of the fetch stack**. Matrix row 23 (the last terrain row) has its
  bottom edge at raster `239+fine`; matrix row 24 (blank) is `240+fine`. At the
  coarse step the copy shifts row 22→23 and **discards row 23's outgoing
  content** — it has nowhere to go, because row 24 is a fixed blank spacer and
  there is no 26th fetch. So the terrain's real bottom edge is now *visible* and
  it snaps.
- **The blank spacer rows absorb the fine-phase *idle strip* and the old
  mode-transition — they do NOT absorb the coarse-step outgoing-row *content*
  snap.** That snap is a property of the finite 25-row fetch, present at *both*
  edges, and with matrix row 24 required blank + RSEL=1 + border open + no hybrid
  dodge, the visible aperture necessarily shows past the last terrain row, so it
  is unavoidable without a scroller change.

## 11.4 Verdict on criterion 8

> *Does the lowest visible terrain edge move continuously and correctly through
> the fine 7→0/coarse transition, or does it visibly jump/wobble/expose the
> spacer?*

**It visibly jumps 7 px and exposes the spacer, on every coarse 7→0 transition
(≈3×/second at divider 2), full screen width, against any non-black `$D021`.**
The top terrain edge does the mirror-image jump. **Criterion 8 = FAIL.** This
matches the user's manual VICE + MiSTer observation and supersedes the Phase-1
static-frame "no pop" conclusion.

Fine scrolling itself (phases 0↔7) and the terrain body (~21 rows) are
**temporally flawless.**

---

# 12. Regression / timing battery — summary

| Test | Result |
| --- | --- |
| Exact physical PAL cadence `[19656]` | **PASS** — every case (§9). |
| All 8 fine-scroll phases | **PASS** — 0 temporal diffs within/between fine phases (§11). |
| Repeated coarse 7→0 transitions (12–13 per 200-frame capture) | body PASS; **edge FAIL** (7 px snap, §11). |
| Normal authored scroll divider 2 | as above. |
| divider-1-like stress (`SCROLL_FRAME_COUNT` pumped) | cadence `[19656]`, 0 counters. (Pump also pins fine at 0, so the 8-phase temporal coverage comes from `ordinary`/`wave5`.) |
| Ordinary authored gameplay | cadence `[19656]`, scheduler clean. |
| Dense sprite load (16 legal objects) | cadence `[19656]`, `service_failure 0`, `sprite_start_miss 0`; marker correctly **skipped** (slot 7 = gameplay). |
| Lowest-Y sprite pressure (8 @ Y=245, synthetic) | cadence `[19656]`, `sprite_start_miss 0`; **8 dispatcher catchups** (overdue-handling, not a miss, not a regression — §9); marker skipped. |
| Contrasting non-black `$D021` (7 = yellow) | cadence `[19656]`; confirms the edge pop is real, not "black hiding it" (§11). |
| Stage wrap | not driven to a full ~420-logical-row circuit this session (the hook + the pop are stage-position-independent; the pop reproduces on every one of dozens of coarse steps regardless of `SCROLL_ROW`). |
| Player death / respawn | not re-run (build has `DEBUG_PLAYER_INVULNERABLE = 1`, as Phase-1 noted); `borderOpenHook` and `rasterFrameReset` are inert to `PLAYER_STATE`. Phase-2 check. |

**Scheduler diagnostics show no new failures** relative to the clean RSEL=0
baseline (0 service failures, 0 sprite-start misses, 0 replay, 0 incomplete,
exact `[19656]`).

---

# 13. Does the lower border remain reliably open? — [MEAS] YES

- First non-`$D021` / idle-graphics raster below the terrain: **~253**, in
  **every** screenshot — all 8 fine phases, 12+ coarse transitions per capture,
  ordinary / wave5 / dense / lowy / contrast.
- The RSEL 1→0 write at raster 250 (§3.2) dodges the raster-251 close every
  frame (`border_trace done_raster = [250]×15`). The RSEL=0 raster-247 close is
  irrelevant (RSEL=1 all frame). No frame was observed with the lower border
  closed.
- The top border is also open (§8).

---

# 14 & 15. Diagnostic lower-border sprite — [MEAS]

Same conditions as Phase-1: one static hardware sprite (slot 7), pointer `$7f` →
`$1fc0` (verified all-`$ff` at runtime), multicolour (`$D01C` bit 7 = 1), colour
`$D02E` = 1 (white) → an all-`%11` bitmap should be a **solid 24×21 white block**,
armed by `borderOpenHook` at Y = 252 only when `$D015` bit 7 is clear.

## 14.1 Arming / safety — unchanged from Phase-1 (verified)

- Armed on every frame slot 7 is free (`$D015` bit 7 clear); `fine_phase_marker`
  shows Y=252, X=160, ptr `$7f`, colour `$F1`, `$D015`=`$81`, `$D010`=0 across
  all 8 fine phases.
- **Skipped** when slot 7 is in gameplay use: `dense` (`$D015`=`$FF`, slot-7 Y≠252),
  `lowy` (`$D015`=`$FF`, slot-7 Y=243). Correct.
- `player_hit_seen = [0]` over 120 frames; no register leak into gameplay
  (`renderSprites` re-defines `$D000-$D00F`/`$D010`/`$D015` every frame top).

## 14.2 What happens below raster ~256 — [MEAS]

**The deep-lower-border corruption PERSISTS.** In the opened lower border the
marker renders a **byte-stable garble** — a fixed per-frame mixture of white
(255) / terrain-shade (205) / `$D021` (148) / dark-shade (98) / black (0) pixels —
across rasters **~254 … ~273**, then ends (MCBASE = 63). ASCII of the marker
column band (`x64sc`, marker Y=252, `.`=black `g`=$D021 `x`=205 `W`=white
`?`=other):

```
r250-252  gggggggggggg     <- blank row-24 spacer / open border top ($D021)
r253      gg..gg..gg..      <- open-border idle-graphics stripes (NOT the marker)
r254-256  ggxxxxxxxxxxxx..  <- marker body rows 0-2: rendered as SHADE-205, not white
r257      ggxxxx..gg..gg..  <- garble begins
r258-273  gg..ggxxxWxxxg.. / ggxxW?W?gxW.?x.. / ...  (byte-stable striped mixture)
r274+     gg..gg..gg..      <- marker ended; idle stripes resume
```

- **Independent of RSEL history.** Phase-1's onset was ~raster 257 with 3 clean
  white rows first; under the *corrected genuine RSEL=1* gameplay history the
  marker is wrong from its **first body raster (~254)** — the corruption did
  **not disappear, did not improve; if anything it is slightly worse** (no clean
  rows). The Phase-1 hypothesis that "the strange sprite behaviour may be related
  to the Phase-1 hybrid RSEL history" is **disproven.**
- **Reproduced byte-identically on `x64sc` AND `x64`** (two VICE cores) — rasters
  263-273 pixel-for-pixel identical between cores.
- Region-locked (Phase-1 established the identical sprite is pixel-perfect in the
  normal playfield; not independently re-confirmed here because `borderOpenHook`
  re-pokes Y=252 every frame, contaminating a naive playfield Y-poke).

## 14.3 Interpretation

This is a genuine **VIC-II deep-lower-border sprite-fetch / MCBASE behaviour**
(both cores agree), not an artefact of the Phase-1 experiment. A bottom-border
sprite HUD needs ~24–40 clean px of sprite depth at Y ≈ 252; **~0 clean px are
available.** Confirmation on real PAL hardware remains the single decisive test,
but two independent emulator cores agreeing, and the corruption surviving the
RSEL-history fix, strongly indicate it is real.

---

# 16. Exact PAL cadence & mux diagnostics — clean

`[19656]` exact on the trusted oracle for all seven cases (§9). No new service
failures, sprite-start misses, replay frames or incomplete frames vs the clean
RSEL=0 baseline. The only non-zero counter anywhere is 8 catchups under the
synthetic lowest-Y load (overdue-handling, 0 misses — §9).

---

# 17. Protected architecture — nothing changed

| Protected item | Touched? |
| --- | --- |
| logical object pool (`MAX_OBJECTS=16`), slot-0 player convention | **No** |
| BUILD/LIVE render-plan separation, `swapRenderPlans`, `applyLiveRasterBatch`, object sort / render-plan, `buildBatchSpriteSchedule` | **No** |
| sprite multiplexer architecture, `dispatchRasterEvents` sprite-batch merge logic | **No** — the DISPLAY event's *plumbing* is untouched; only its hook *body* is now a no-op |
| collision plumbing (`checkCapturedPlayerCollision`, `$D01E`) | **No** |
| player / enemy gameplay, wave / turret systems, level / editor data contract, generated level package | **No** — the ≤5-enemy fixture is a RAM-only runtime patch |
| `prepareBackgroundCoarse` / `finishBackgroundCoarse` / `shiftBackground*` / `save/restoreCrossingRow` / crossing-row buffer | **No** |
| stage decoder / metatile system, `$D016` / `$D018` / VIC bank / `$0400` / `$3800`, palette/config ownership | **No** |
| **RSEL=0** | **Replaced by RSEL=1** — explicitly *not* protected per the brief; this is the point of the task. |

Changes are confined to: `$D011` ownership (`init`, `publishRasterPlan`,
`rasterFrameReset`, `borderOpenHook`), the neutered `rasterDisplayHook`, and the
row-0/row-24 spacer fill + score-presentation stubs in `main.asm`.

---

# 18. What Phase 2 should be

Per the task's decision tree:

- **Gameplay geometry is NOT yet temporally stable** (criterion 8 fails: the
  7→0 coarse-seam 7 px snap at both terrain edges). → **Case C.** **Do not build
  the HUD hand-off.** Root-cause the scroll/display geometry first.
- **Deep-lower-border sprites still corrupt** (§14). → also **Case B** for the
  sprite question specifically: even once the geometry is fixed, a *bottom*
  sprite HUD at Y ≈ 252 is not viable at the required depth.

### Phase-2A (blocking) — fix the coarse-seam edge snap

The RSEL=1 aperture shows past the bottom (and top) of the finite 25-row fetch
stack, so the outgoing/incoming row's fine-scroll overflow is visible and snaps
7 px at each coarse step. Bounded options, in rough order of preference:

1. **Scrolled row 24 with the seam pushed into the open border.** Let the
   scroller write matrix row 24 (terrain, 24 content rows: matrix 0..23 terrain +
   a scrolled row 24), and treat rasters ≳ 247 as "border HUD / overscan" not
   "gameplay". The outgoing-row snap then happens at raster ~247–254, below the
   gameplay field. Cost: `shiftBackgroundLower` 14..23 → 14..24,
   `renderStageRowToScreen` range, `initBackground` fill, one editor constant.
   (Contradicts *this experiment's* "row 24 blank" requirement — which is why it
   is Phase 2, not Phase 1.5.)
2. **Beam-raced bottom crop that still leaves the border open.** Not possible
   with the vertical border FF alone (opening the bottom opens the top; setting
   it closes the HUD region). Would need a per-line left/right-border trick or an
   ECM/blank band precisely over rasters ~239..250 — i.e. re-introducing a
   mid-frame $D011 write, the thing Phase 1.5 removed. Not recommended.
3. **Accept a ~7 px "keep-clear" strip** at the very bottom (and top) of the
   gameplay field as an authoring guideline, and position the HUD sprites to
   cover the bottom strip. Cheapest; leaves the top strip visible.

Whichever is chosen, re-run the §11 temporal battery until `check_scroll_edges_rsel1`
reports **0 diffs at the 7→0 step in every band**, including a full stage-wrap.

### Phase-2B — the border sprite HUD (only after 2A is GREEN)

Given §14, **do not target the deep lower border.** Re-target the *opened top
border* (Slap-Fight-exact: HUD sprites at Y ≈ `$0c`, raster ~12–33, inside the
normal sprite window, reused by gameplay from ~raster `$20`). The top border is
already open as a side-effect (§8), so this also *covers* the ugly open-top-border
idle stripes. Re-run the full Phase-1 border battery for the top border; if a
≥ ~24 px clean opened-border sprite depth is demonstrated there, then proceed to
`HUD_SAFE_RASTER` / the terminal gameplay→HUD hardware-sprite hand-off / borrow
4 sprites / static canvas first / dynamic content later — as the feasibility
report lays out, but **top**, not bottom.

---

# 19. Answers to the brief's explicit questions

1. **Branch/HEAD, tree clean?** `terrain-asset-workshop` @ `1cd8513`; working
   tree **clean** at start.
2. **Which Phase-1 changes were present?** §1 — the `BORDER_PROOF_ENABLE` toggle,
   `BORDER_MARKER_SPRITE`, the guarded `RASTER_EVENT_BORDER` / `borderOpenHook`
   hybrid (RSEL 0→1 @ r243 + RSEL 1→0 @ r250, playfield permanent RSEL=0), and
   two Phase-1 harnesses.
3. **What old top-HUD/display-split code was removed/disabled?** §2.1 — `init`
   now sets RSEL=1; `rasterDisplayHook`'s entire `$11/$71/$70|f/$77/$10|f` chain
   (incl. the invalid BMM+ECM band) + `rasterHblankDelay` + poll loops + guards
   deleted (hook is a scheduled no-op); `rasterFrameReset` + `publishRasterPlan`
   `$17` → `RASTER_DISPLAY_FINE|$18`; `initFixedHud` reduced to the two blank
   spacer rows; `refreshScoreIfDirty` no longer writes screen RAM.
4. **Any old HUD routines now dead/unreachable?** Yes — `displayScore` (no
   callers), and the `hudStockCodes` / `fixedHudText` / `fixedHudFreeLabel` data
   + `displayCycleMinimum`. All **retained** (bounded), listed in §2.3.
5. **New normal `$D011` state during gameplay?** `RASTER_DISPLAY_FINE | $18` =
   `$18`…`$1F` (DEN=1, RSEL=1, YSCROL = presented fine, compare-MSB 0). §3.1.
6. **Exact raster/cycle RSEL is changed 1→0?** `borderOpenHook`, poll to raster
   250 → `$D011 AND #$F7` executes at **raster 250, cycle ~18–23**, `$1B → $13`.
   IRQ entry raster 241–242. §3.2.
7. **Exact raster/cycle RSEL is restored to 1?** `rasterFrameReset` at **raster 1,
   cycle ~9–22** (`$D011 = fine|$18`); re-asserted by `publishRasterPlan` at
   raster ~17. Both before the line-51 top compare. §3.1.
8. **Resulting visible raster ranges?** §4 / §5. Open top border ~16–52; blank
   row-0 spacer ~53–60; terrain ~61–239; blank row-24 spacer ~240–252; open
   lower border ~253+ (marker region ~254–273). All ±7 with fine phase.
9. **How many complete terrain character rows are genuinely usable?** 23 rows are
   fetched/displayed; **~21 (matrix rows ~2..22) are temporally flawless**; rows
   1 and 23 each carry a coarse-step 7 px edge pop (§6, §11). Reclaiming a 24th
   (matrix row 0) needs a scroller change and would not fix the pop.
10. **Is row 24 still permanently blank?** Yes — verified all-`$20` at runtime,
    scroller never addresses it; row 0 now likewise (§7).
11. **Is the lowest terrain edge visually/temporally stable through fine 7→0?**
    **No** — 7 px snap every coarse transition, full width, any `$D021` (§11).
12. **What temporal test proves that?** `tools/check_scroll_edges_rsel1.py`
    (model-free pixel-vs-line-above-previous-frame), a per-frame lowest-edge
    raster series, and magnified 12-frame seam strips — cross-checked A/B against
    a clean RSEL=0 build. §11.1–11.2. Evidence in `build/p15-*/phase15-evidence/`
    and `build/p15-*/rsel1-edge-verification.json`.
13. **Does the lower border remain reliably open?** Yes — first idle raster ~253
    every frame/phase/load; the r251 close is dodged every frame. §13.
14. **What happens to the diagnostic sprite below raster 256 under the new RSEL
    history?** Byte-stable garble across rasters ~254–273 (mixed white / 205 /
    $D021 / 98 / black), from the marker's first body raster. §14.2.
15. **Does the corruption disappear, move, change, or remain?** **Remains** —
    and starts *earlier* than Phase-1 (no clean leading rows). Byte-identical on
    `x64sc` and `x64`. The RSEL-history hypothesis is disproven. §14.2–14.3.
16. **Are `[19656]` and all scheduler/mux diagnostics still clean?** Yes —
    `[19656]` exact, 0 service failures, 0 sprite-start misses, 0 replay/incomplete
    across all cases; 8 catchups only under the synthetic lowest-Y load (0 misses,
    not a regression). §9, §16.
17. **Did any protected architecture need changing?** No — §17. Only `$D011`
    ownership + the neutered display hook + the spacer/score-presentation stubs.
18. **What should Phase 2 be?** §18 — **Case C**: root-cause the coarse-seam edge
    snap (Phase-2A) before any HUD hand-off; and re-target the sprite HUD to the
    *opened top* border, not the deep lower border (Phase-2B).

---

# 20. Success-criteria scorecard

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Legacy top character HUD gone from gameplay | ✅ |
| 2 | Invalid BMM+ECM separator / top glitch gone | ✅ |
| 3 | Gameplay runs in genuine RSEL=1 geometry throughout its visible field | ✅ |
| 4 | No temporary RSEL 0→1 lower-edge setup remains | ✅ |
| 5 | Lower border opens reliably via the late RSEL 1→0 transition | ✅ |
| 6 | RSEL=1 restored safely for the next frame | ✅ |
| 7 | Matrix row 24 remains blank/spacer | ✅ (row 0 too) |
| 8 | **Lowest visible gameplay terrain temporally stable while scrolling** | ❌ **7 px coarse-seam snap, both edges** |
| 9 | Exact PAL cadence `[19656]` | ✅ |
| 10 | Existing raster/mux/coarse diagnostics show no new failures | ✅ |
| 11 | Dense and lowest-Y sprite gameplay remain correct | ✅ (synthetic low-Y: 8 catchups, 0 misses) |
| 12 | Diagnostic lower-border sprite result measured and documented | ✅ (still corrupt) |
| 13 | No multiplexer rewrite / protected scroller redesign required | ✅ |

**GREEN requires all 13.** Criterion 8 fails → **not GREEN.**
Per the brief: *"If the bottom terrain still visibly wobbles/tears, the pass is
AMBER/RED regardless of static screenshot analysis."* → **AMBER, decision C.**

Split, as the brief allows:
- **RSEL=1 display-geometry conversion (HUD removal, separator removal, border
  open, RSEL restore, cadence, scheduler): GREEN.**
- **Scroll temporal stability: RED** (criterion 8).
- **Lower-border sprite-HUD feasibility: RED** (deep-border corruption confirmed
  independent of RSEL history).

---

# 21. Artefacts

Source (working tree, **not committed**):

- `src/main.asm`, `src/raster_scheduler.asm` — the Phase-1.5 changes (§2).
- `docs/bottom-border-hud-phase1-5-worklog.md` — session worklog.
- `tools/check_scroll_edges_rsel1.py` — **new** RSEL=1 temporal edge oracle.
- `tools/phase15_geometry_test.py` — **new** capture harness + non-destructive
  ≤5-enemy runtime fixture.

Build (gitignored) — **MiSTer / real-hardware ready:**

- `build/shooter.prg` / `build/shooter.d64` — `sha256(prg) =
  6e9d30468522eb31faf39dc17ba80bf8968198d45d2934a3f2c7ad1899f355e5`. Runs Level 1
  straight into PLAYING. The bottom-edge pop and the open-top-border idle stripes
  are visible on any non-black backdrop; the current Level-1 `$D021` is 12
  (medium grey). To make the pop unmistakable, run with `$D021` forced bright.
- `build/p15-{ordinary,wave5,dense,lowy,contrast,div1,wave6}/` — 200-frame
  physical captures + `raster-verification.json` + `rsel1-edge-verification.json`
  + `phase15-evidence/{top,bottom}_seam_7to0.png` (magnified consecutive-frame
  seam strips).
- `build/p15-border/` — `vice_border_phase1.py` run (fine-phase / dense / low-Y /
  contrast / Y-sweep screenshots + `report.json`).
- `build/p15-cap/`, `build/rsel0clean-cap/` — the RSEL=1 vs clean-RSEL=0 A/B
  captures.

Housekeeping: **no commit, no push.** `HEAD` still `1cd8513`. VICE was launched
head-less/background and killed on exit; never foregrounded; no `open -a`. The
generated Level-1 assets on disk were **not** modified (the ≤5-enemy fixture is a
RAM-only runtime patch inside `tools/phase15_geometry_test.py`).
