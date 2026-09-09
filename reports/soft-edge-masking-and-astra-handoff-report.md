# Top/Bottom Soft-Edge Masking + Astra/Opus Architectural Handoff

**19656 / c64Shooter — PAL C64, branch `experimental-border-hud`.**
Presentation-cleanup task (mask the finite-fetch scroll-edge pop) **plus** a
self-contained technical hand-off to the next architectural review. No commit /
push / add / tag / reset / stash / branch change. VICE `x64sc` head-less /
background, never foregrounded, no `open -a`. Legal NMOS 6502 only.
KickAssembler v5.25 / VICE 3.10.

Legend: **[OBS]** in source · **[MEAS]** measured this session · **[A/B]** vs a
comparison build.

---

## 1. Verdict — **AMBER**

| GREEN criterion | status |
| --- | --- |
| top soft-edge pop visually eliminated | **NO** — reduced ~8 px → ~1 px, but a mid-scanline mode switch at the mask boundary is not cycle-exact from the variable-entry raster IRQs, so the boundary raster shows a ~1–8 px **per-frame shimmer** (trades a 3 Hz pop for a 50 Hz one) |
| bottom soft-edge pop visually eliminated | **NO** — same |
| clean terrain 55..246 remains temporally clean | **YES** — `check_scroll_edges_rsel1 --aperture 55 246`: `body_temporal_diffs 0`, `lastrow_temporal_diffs 0`, `coarse_edge_median_jump [0]`, with the mask on **and** off |
| top-border HUD remains stable | **YES** — 0 HUD-sprite-7 vanish in 595 sampled frames, mask on |
| whole-border flash does not return | **YES** — `RASTER_BORDER_BAILS == 0`, `RASTER_BORDER_SKIPS == 0`, mask on and off |
| no hard lock | **YES** — the Task-9 guard is untouched (see §2) |
| exact `[19656]` | **YES** — mask on and off |
| zero service failures / sprite-start misses in supported gameplay | **YES** (the 1 marginal `rasterInitialMasksApplied` trip at frame ~427 is the pre-existing, A/B-identical transient documented in the residual-flicker report §18) |
| all 8 hardware sprites available after HUD handoff / no permanent reservation | **YES** — unchanged |
| no BUILD/LIVE or scroller architectural rewrite performed | **YES** |
| Astra handoff complete enough to review the optimisation question | **YES** — §7 + §8 |

**The masking mechanism works** (an ECM band blanks the sacrificial outer
scanlines to `$D021`), the clean body / HUD / border / cadence are all
preserved, but the pop is **not visually eliminated** — the boundary raster
shimmers because the ECM↔text switch cannot be placed in the ~22-cycle gap
between two scanlines' g-accesses without a cycle-exact stable-raster prologue,
and the IRQs that would carry it (`borderOpenHook`, `hudBorderHandoff`) enter at
a load-dependent raster/cycle. Per the task's own off-ramp ("If masking cannot be
made reliable … report AMBER rather than forcing a risky architectural change"),
this is **AMBER**.

**The shipped engine is unchanged.** `#define SOFT_EDGE_MASK` is committed
**OFF**; with it off the build is **byte-identical** to the residual-flicker
report's baseline (`sha256(prg) = 1fadf2b4…`). Every added line is
`#if SOFT_EDGE_MASK`-guarded. The mask code stays in-tree so the architectural
review can measure it (`#define SOFT_EDGE_MASK` → `sha256 5d832000…`).

---

## 2. Starting repository state

```
$ git branch --show-current
experimental-border-hud
$ git status --short
        (clean)
$ git log -5 --oneline
6a64130 Four top HUD sprites stable under managed mux load
bc9d275 Hard lock fixed, border sprite flicker remains
82c27c5 Top border sprites milestone 1
44e735c pre-architecture-teardown
d547c80 Establish RSEL1 border HUD experimental baseline
```

- HEAD `6a64130220e87eea182f6b638d38da03524a2bc5` (**unchanged**).
- Compile-time toggles (`src/main.asm` top): `#define BORDER_PROOF_ENABLE`,
  `#define HUD_PROOF_ENABLE`, `#define BORDER_FORENSIC`, and **new**
  `//#define SOFT_EDGE_MASK` (commented — see §1).
- Accepted baseline (from the prior three reports, re-verified this session,
  mask off): PAL `[19656]`; clean terrain **raster 55..246 = 192 px**; both
  vertical borders opened via the `borderOpenHook` RSEL dodge; four top-border
  HUD sprites in physical slots 4..7, reclaimed for gameplay every frame at
  raster ~48–55 (`hudBorderHandoff`), no permanent reservation, all 8 hw sprites
  free after handoff; hard-lock guard + `RASTER_BORDER_BAILS/SKIPS/EARLY`
  counters intact; `HUD_HANDOFF_COMPLETE_RASTER = 56` floor.
- Hard-lock guard baseline verification: `borderOpenHook`'s three-way beam
  classifier (`beam >= 246` → bail; `beam < 237` → early re-arm; `237..245` →
  dodge) is **unchanged** when `SOFT_EDGE_MASK` is off — the shipped `.prg` is
  bit-for-bit the residual-flicker build. A/B: `RASTER_BORDER_BAILS 0`,
  `SKIPS 0`, `EARLY 7` on a 600-frame authored seed-40 capture, mask on and off.

### Relevant memory map (VIC bank 0, `$0000–$3FFF`)

| region | contents |
| --- | --- |
| `$0400–$07FF` | screen matrix (1000 cells) + sprite pointers `$07F8–$07FF` |
| `$0801–$1EF0` | engine code |
| `$1F00–$1F5A`, `$1FC0–$1FFF` | small tables, `BORDER_MARKER_SPRITE` |
| `$2000–$23FE` | `OBJECT_*` arrays + misc state |
| `$2400–$290E` | `attack*` tables (`$2400`), `randomAttackMap` |
| `$2920–$2E69` | background / coarse-scroll code |
| `$2F00–$2FFF` | 4 × 64 B HUD sprite bitmaps (`HUD_SPRITE_BASE`) |
| `$3000–$33FF` | `healthSpritePool` (`HEALTH_SPRITE_BASE`, 16 × 64 B) |
| `$3400–$37FF` | `clipSpritePool` (`CLIP_SPRITE_POOL`, 16 × 64 B) |
| `$3800–$3FFF` | terrain charset (`STAR_CHARSET`): 0–63 ROM font copy, 64–95 HUD glyphs, **96..167** level-1 terrain glyphs (`TERRAIN_GLYPH_BASE=96`, `TERRAIN_GLYPH_COUNT=72`), 224–225 diagnostic, 240–251 stars. `$3FFF`/`$39FF` forced `$00` in `init` (idle g-byte). |

**There is no free 2 KB-aligned region in bank 0** — every 2 KB `$D018`
character-base slot is occupied (code, live state, sprite pools, or the charset
itself). This is the constraint that forced the ECM route over a `$D018` blank-
charset swap (§4, §5).

---

## 3. Current display architecture (for Astra — assume no prior context)

**VIC bank / matrix / charset.** VIC bank 0. One screen matrix at `$0400`,
`$D018 = $1E` fixed (VM = `$0400`, CB = `$3800`) — never touched during
gameplay. Global multicolour text mode (`$D016` bit 4 = 1); every terrain /
turret cell has colour-RAM = `8 | TERRAIN_CHARACTER_COLOUR` (bit 3 set); the
2-bit multicolour pixels come from the glyph bitmap; palette `$D021 = 12`
(backdrop), `$D022 = 15`, `$D023 = 11`. Colour RAM is written once per game and
never scrolled.

**RSEL / border opening.** Gameplay runs RSEL = 0 (`GAMEPLAY_D011_BASE = $10`;
`rasterFrameReset` and `publishRasterPlan` install `$D011 = fine | $10` — DEN,
RSEL 0, YSCROL = presented fine — every frame). `borderOpenHook` (scheduled IRQ
at raster 240) polls to raster 245 and flips RSEL 0→1 (`$D011 |= $08`), then
polls to raster 250 and flips RSEL 1→0 (`$D011 &= ~$08`). Both border-close
compares (raster 247 for RSEL 0, raster 251 for RSEL 1) are missed → the single
vertical-border flip-flop is never set → **both** the top and bottom borders
stay open into overscan. The exposed idle region below the last badline fetches
`$3FFF` (`init`-forced `$00`) → solid `$D021`. `borderOpenHook` carries a
three-way beam guard (hard-lock fix, residual-flicker report): `beam >= 246` →
abandon BORDER for the frame (`RASTER_BORDER_BAILS`); `beam < 237` → leave BORDER
pending, re-arm (`RASTER_BORDER_EARLY`); `237..245` → do the dodge.

**Scroller.** Vertical only. 25 matrix rows fetched (badlines
`48+fine .. 240+fine`). `SCROLL_ROW` (16-bit) is the world logical row shown in
matrix row 1. Matrix row `d` shows world `SCROLL_ROW + d - 1`, so:

```
matrix row 0  = world SCROLL_ROW-1   (incoming overflow  -- rasters ~48..55+fine)
matrix row 1..23 = world SCROLL_ROW .. +22   (BODY -- rasters 55..246, temporally flawless)
matrix row 24 = world SCROLL_ROW+23  (outgoing overflow  -- rasters ~240..254+fine)
```

Fine scroll = `$D011` YSCROL (`applyFineScroll` publishes the phase;
`rasterFrameReset` installs it). Coarse step (`SCROLL_FRAME_DIVIDER = 2`, so
every 8 fine steps = every 16 frames, ≈ 3.9 Hz): `updateBackgroundScroll` flags
a pending wrap; `prepareBackgroundCoarse` (main thread, behind the beam) shifts
the upper matrix rows and decrements `SCROLL_ROW` at the wrap;
`finishBackgroundCoarse` (main thread, after `armFirstBatch`) shifts the lower
rows ahead of the beam; `renderStageRowToScreen` → `decodeStageCharacterRow`
expands the metatile stage (`metatileDefs` / `stageMetatileRows`) into the new
row, then `installTurretRow` overlays turret private glyphs. Rows 0 and 24 carry
**real** overflow terrain (not blank spacers) so the row0/row1 and row23/row24
**seams** are continuous through both fine and coarse motion.

**BUILD / LIVE render plan.** Two plan buffers. Each frame the main thread runs
`buildSortedObjectList` → `sortObjectsByY` → `buildInitialSpriteSnapshot`
(the first ≤ 8 hw sprites, Y-sorted) → `buildBatchSpriteSchedule` (raster batches
for objects 9..16, each `minY − 12`, plus per-batch masks) → `swapRenderPlans`
→ `armFirstBatch` → `publishRasterPlan` (installs the IRQ vector, arms the first
compare, `jmp dispatchRasterEvents`). The publication **deadline** is "before the
first gameplay sprite compare". If the main thread misses it,
`rasterFrameReset`'s `!replay` path re-runs `renderSprites` inside the IRQ at the
frame boundary (`RASTER_REPLAY_FRAMES`), and any event whose compare is already
past is serviced immediately (`RASTER_CATCHUPS`).

**Raster event scheduler** (`src/raster_scheduler.asm`, single re-entrant
dispatcher `dispatchRasterEvents`, one `$D012` compare at a time). Events, in
beam order: `FRAME` (compare 0 → `rasterFrameReset`: install whole-frame `$D011`,
`hudBorderSetup`, ready-or-`!replay`), `DISPLAY` (compare `HUD_HANDOFF_RASTER =
46` → `rasterDisplayHook` → `hudBorderHandoff`), `SPRITES` (batch compares
~raster 120..234 → `applyLiveRasterBatch`), `BORDER` (compare
`RASTER_BORDER_LINE = 240` → `borderOpenHook`), epoch (compare 0). Forensic ring
`FORENSIC_RING` (`#define BORDER_FORENSIC`) logs `(event, $d012, SP, frame)` per
VIC dispatch.

**HUD early-frame ownership / handoff.** `hudBorderSetup` (line-1 IRQ, raster
~2) programs hw slots 4..7 = 4 static hires HUD sprites at Y = 22 (body raster
22..42), sets `$D015 |= $F0` (deterministic enable — residual-flicker fix), and
`$D01C`/`$D010` for the HUD. `renderSprites` writes only slots `0..min(RC,4)`
(caps at 4) and `ORs $F0` into `$D015` to hold the HUD through its DMA.
`hudBorderHandoff` (DISPLAY event, entry raster **46–49**, per-slot reclaim done
by raster **50–55**, `rasterDisplayRestored` by raster **56**) re-applies the
deferred gameplay initial sprites into slots 4..7, restores `$D01C`/`$D010`, and
writes the final `$D015`. `buildBatchSpriteSchedule` floors an **unused** HUD
slot's reuse raster at `HUD_HANDOFF_COMPLETE_RASTER = 56`.

**Sprite-slot reuse.** No permanent reservation. HUD owns 4..7 only for rasters
~2..~50; from the handoff on, all 8 hw sprites are gameplay-owned; a deferred
gameplay sprite in a reclaimed slot has ≥ 51 rasters of DMA margin.

**Object / render limits relevant to the review.** Up to 16 logical objects →
8 initial hw sprites + up to 8 batched. Normal scrolling waves are forced to
`NORMAL_WAVE_SIZE = 5`; authored triggers can request more. The multiplexer is
known to carry substantially more than 6 enemies when the scrolling-background
workload is absent; the practical ceiling under combined scroll + mux load is a
property of the **combination**, not the mux (residual-flicker report §12).

---

## 4. Exact pre-fix soft-edge mechanism

**[MEAS]** `check_scroll_edges_rsel1` + frame-diff, mask off, seed-40 capture,
36 coarse steps:

- The clean body (matrix rows 1..23, raster 55..246) is temporally flawless
  every fine phase and every coarse step (`body_temporal_diffs 0`).
- A **once-per-coarse-cycle** discontinuity occurs in an **8-scanline** band at
  each end — screenshot rows y32..39 (top, ≈ C64 raster 50..57) and y232..239
  (bottom, ≈ C64 raster 248..255) — **~70 px wide, at the 7→0 step only, 0 at
  every non-coarse step** (a pure coarse-cadence pop, not a shimmer).

**Which fetched row / why.** `W(r) = SCROLL_ROW + r − 1`. Matrix row 24 = world
`S+23`, fetched at badline `240+fine`, showing glyph rows 0..7 at rasters
`240+fine .. 247+fine`. As `fine` goes 0→7 the whole field scrolls down 1 px;
the body stays continuous because rows 1..23 hand each world row to the next row
down, and row 24 catches row 23's fall-off. **But world `S+23` (the current row
24) has nowhere to go** — its next position (rasters `248+fine .. 254+fine`)
would need a matrix row 25 that the finite 25-row fetch cannot produce. At the
`7→0` step `SCROLL_ROW` decrements, matrix row 23 shifts into row 24, and the old
world `S+23`'s 8-px band at rasters `247+fine .. 254+fine` **simply vanishes**,
replaced by idle → `$D021` backdrop. That vanishing = the ~6–8 px bottom pop.
The top is the mirror: world `S−2` is only ever partially visible (its bottom
few pixels, in row 0, at rasters ~51..55); at the coarse step it **jumps in**
~4 px rather than scrolling in gradually.

**This is a finite-fetch presentation edge, not corruption of the clean body.**
Any N-row character scroller that displays its last fetched row has it; the
Slap Fight / Terra Cresta reference engines crop/mask at the same boundary — the
extra visible height there is *sprites + border HUD*, not scrolling terrain past
the crop. The clean scrolling terrain is, and remains, 55..246 = 192 px.

---

## 5. Masking implementation (investigated; shipped OFF)

Chosen mechanism: a **mid-frame Extended Color Mode (ECM) band** over the
sacrificial outer scanlines — the mechanism both commercial reference engines
use for their edge transitions (`$D011 |= $40`). It needs **no memory move**
(the `$D018` blank-charset alternative needs a free 2 KB CB region that bank 0
does not have — §2).

**How ECM blanks.** In ECM the character code is masked to 6 bits, so **every**
on-screen code (terrain 96..167, turret private 226..239) indexes glyph 0..63 at
`$3800..$39FF`. `initBackground` zeroes that 512-byte window during PLAYING
(nothing on the PLAYING matrix references codes 0..63 — `metatileDefs` emit 96+,
code 32's ROM glyph is already all-zero); `endGame` calls `setupStarfieldCharset`
to re-copy the full ROM font for the menu / GAME OVER text. An ECM cell then
renders as pure background; MCM is cleared first (ECM + MCM is the invalid all-
black mode) and `$D022`/`$D023` are set to the backdrop colour so mixed code
bits 6–7 do not stripe.

### Raster timeline (mask ON)

```
raster 1-2   rasterFrameReset : $D011 = fine | $50   (DEN, RSEL 0, ECM=1)   -- top band armed
raster ~2    hudBorderSetup   : HUD slots 4..7, $D015 |= $F0                  (ECM does not affect sprites)
raster ~15   publishRasterPlan: $D011 = fine | $50   (ECM=1 kept)
raster 16-47 IDLE strip       : ECM idle g-fetch $39FF ($00) -> $D021        (unchanged look)
raster 22-42 HUD sprites      : displayed normally
raster 48-55 matrix row 0     : ECM, glyphs from zeroed $3800..$39FF -> $D021 (TOP MASK -- pop hidden)
raster ~55   DISPLAY event    : hudBorderHandoff (reclaim 4..7), then softEdgeBodyRestore:
                                 poll $d012 to 55, pad, then  $D011 &= ~$40 (ECM off) /
                                 $D016 |= $10 (MCM on) / $D022=15 / $D023=11
raster 56-246 BODY            : ECM off, MCM on -> normal multicolour terrain  (UNCHANGED, clean)
raster 240   BORDER event     : borderOpenHook -- 3-way guard, then:
   poll to 245 : $D011 |= $08                 (RSEL 0->1, dodge raster-247 close)
   poll to 247 : pad, then $D016 &= ~$10 (MCM off) / $D011 |= $40 (ECM on) /
                 $D022=12 / $D023=12          (BOTTOM MASK armed for raster ~249+)
   poll to 250 : $D011 &= ~$08                (RSEL 1->0, dodge raster-251 close)
raster 249-311 bottom band + border + overscan : ECM -> $D021                 (BOTTOM MASK -- pop hidden)
raster 311   frame wrap -> rasterFrameReset re-arms ECM for the next top band
```

**Files touched** (all `#if SOFT_EDGE_MASK`): `src/main.asm` — `#define
SOFT_EDGE_MASK` (OFF); `GAMEPLAY_D011_BASE` gains bit 6 (ECM);
`SOFT_EDGE_BODY_RESTORE_RASTER = 55`, `SOFT_EDGE_BAND_RASTER = 248`;
`initBackground` zeroes `$3800..$39FF`; `endGame` clears `$D011` bit 6, restores
`$D022`/`$D023`, calls `setupStarfieldCharset`. `src/raster_scheduler.asm` —
`rasterDisplayHook` gains `softEdgeBodyRestore` (bounded guarded poll + mode
clear); `borderOpenHook` gains the `!wait247` band-enter block, and its 3-way
guard's three short branches are routed through `jmp` (only when `SOFT_EDGE_MASK`,
so branch range holds with the extra block). `git diff --stat`:
`2 files changed, 147 insertions(+), 2 deletions(-)`, **0 bytes** in the shipped
(mask-off) binary.

### Why it is not GREEN

**[MEAS]** mask-on seed-40 capture vs mask-off, same-phase consecutive frame
pairs (which must be pixel-identical in the bands — a true per-frame shimmer):

| band row | mask OFF shimmer | mask ON shimmer | mask OFF coarse pop | mask ON coarse pop |
| --- | ---: | ---: | ---: | ---: |
| top boundary (y40) | 0 px/frame | **~4 px/frame** | ~70 px/step ×8 rows | ~20 px/step ×1 row |
| bottom boundary (y232) | 0 px/frame | **~8 px/frame** | ~76 px/step ×8 rows | ~76 px/step ×1 row |

The mask **eliminates 7 of the 8 pop rows** and drops the surviving row's
*coarse* contribution, but the ECM↔text switch write lands at a load-dependent
cycle inside the boundary raster's g-access window (the safe gap between one
scanline's last g-access at cycle ~55 and the next's first at cycle ~16 is only
~22 cycles; two mode writes are ~20 cycles; the IRQ entry jitter is ±9 cycles),
so the "terrain | blank" split point on that one scanline **wobbles ±few chars
every frame**. The result trades a 3.9 Hz 8-px pop for a ~50 Hz 1–8 px edge
shimmer — not "visually eliminated", arguably worse. Landing the write cleanly
before/after the g-access instead leaves the **fundamental 1-px coarse-step
boundary artifact**: at the coarse step the pre-step frame has real terrain one
scanline past where the post-step frame has it, and a static mask boundary
cannot hide that last scanline without blanking a *body* row (which regresses
the clean-body oracle). Both were tried; neither reaches zero.

**What would make it clean:** a **cycle-exact stable-raster prologue** for each
switch (double-IRQ or `$D012`-sync + NOP alignment) so the boundary scanline is
consistently fully-one-thing, then only the 1-px coarse artifact remains — which
is a strict improvement over the 8-px pop and is plausibly "eliminated" for
practical purposes. That adds cycle-counted code to two time-critical IRQ paths
for a cosmetic edge, so it is deferred to the review rather than forced here.

---

## 6. Validation results (shipped build = mask OFF = `1fadf2b4…`; mask ON = `5d832000…`)

### Fine phases / coarse / stage wrap — `check_scroll_edges_rsel1 --aperture 55 246`

| capture | frames | phases | coarse steps | `body_temporal_diffs` | `lastrow_temporal_diffs` | `coarse_edge_median_jump` |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| shipped, seed 40 (coarse + stage wrap) | 600 | all 8 | 36 | **0** | **0** | `[0]` |
| mask ON, seed 40 | 400 | all 8 | 23 | **0** | **0** | `[0]` |

The clean body 55..246 is temporally flawless with the mask **on or off**. (The
mask's residual shimmer is at the boundary scanline just **outside** this
oracle's `y = raster − 16` window — see §5 for the direct frame-diff numbers.)

### HUD stability — screenshot analysis, mask ON, seed-40 640-frame capture

| check | result |
| --- | --- |
| HUD sprite-7 vanish frames | **0 / 595** |
| whole-border-black frames | **0 / 595** |
| `RENDER_COUNT` regimes exercised | 5 (×46 f), 6 (×72 f), 7 (×131 f), 8 (×151 f) |
| deferred-slot reclaim window | raster 46–49 entry, 50–55 complete (unchanged by the mask) |

### Scheduler / cadence

| metric | shipped (seed 40, 600 f) | mask ON (seed 40, 400 f) |
| --- | ---: | ---: |
| `frame_cycle_deltas` | **`[19656]`** | **`[19656]`** |
| `service_failure_count` | 0 | 0 |
| `sprite_start_miss_count` | 1 (frame ~427 `rasterInitialMasksApplied`, pre-existing / A/B-identical) | 0 |
| `RASTER_BORDER_BAILS` Δ | **0** | **0** |
| `RASTER_BORDER_SKIPS` Δ | **0** | **0** |
| `RASTER_BORDER_EARLY` Δ | 7 (benign — border still opens same frame) | 7 |
| `RASTER_INCOMPLETE_FRAMES` Δ | 0 | 0 |
| `RASTER_CATCHUPS` / `RASTER_REPLAY_FRAMES` Δ | 11 / 3 | ~10 / 3 |

### Long-running

The shipped `.prg` is bit-identical to the residual-flicker report's
`1fadf2b4…`, whose §11/§17 endurance (10,000 physical PAL 5-enemy frames + 6,000
6-enemy + 5,000 authored + 2,500 collision + 2,500 control = 26,000) recorded
`BAIL 0 / SKIP 0 / EARLY 0 / INCOMPLETE 0`, `[19656]`, 0 service failures, 0
sprite-start misses, 0 HUD-sprite vanish. This session re-confirmed the same
binary on a fresh 600-frame authored seed-40 capture (table above). The mask-ON
build was validated to 400–640 frames (fine-phase/coarse/wrap/HUD/cadence
tables above); it is not shipped, so a multi-thousand-frame endurance run on it
was not the priority — the failing criterion (visual shimmer) is already
established.

### dense16

Not the primary criterion. `check_raster_capture --dense` (320 f) on the shipped
build: `[19656]`, 0 service failures, 3 `rasterBatchMasksApplied` misses at
frames 15/16/18 — the pre-existing poke-settle transient, byte-identical to the
prior baseline.

### Regressions checked and clear

HUD `$D015` enable race — no (deterministic enable untouched). Whole-border flash
— no (`BAILS/SKIPS 0`). Hard lock — no (Task-9 guard byte-identical when mask
off; when on, the guard's logic is unchanged, only its short branches are routed
via `jmp`). Out-of-window unbounded busy-wait — no (all mask polls are bounded:
`softEdgeBodyRestore` ≤ ~9 lines with a `bmi`/`cmp` pre-guard, `borderOpenHook`'s
`!wait247` is inside the already-`[237..245]`-guarded region). HUD handoff timing
race — no (`HUD_HANDOFF_COMPLETE_RASTER = 56` floor unchanged; the mask's
`softEdgeBodyRestore` runs *after* the reclaim loop and touches no sprite
register). Permanent slot 4..7 reservation — no.

---

## 7. Remaining manual issue: scroll hitching under mux load (for Astra)

Written for the architectural review; **not** in scope for this task and
deliberately not addressed here.

- **The user considers the HUD fixed** (manual confirmation: four top HUD
  sprites stable under 6 enemies + 2 bullets + player).
- The whole-border flash is fixed (residual-flicker report — spurious early
  BORDER-compare fire, `!early` re-arm).
- Soft-edge masking is *investigated* (this report) — reduces the coarse pop but
  is not shipped (§1, §5).
- **The remaining visible issue is occasional scroll hitching** under combined
  multiplexer + scrolling-background load. A known manual reproduction regime is
  **6 enemies + 2 bullets + player + active scrolling**.
- The multiplexer alone handles substantially higher object counts when the
  scrolling-background workload is absent (residual-flicker report §12). **Do
  not frame this as a fundamental 5/6-enemy mux limit** — it is a property of the
  current *scroller + BUILD/LIVE plan + HUD handoff + mux* combination.

### Best measured evidence of main-thread / raster lateness

**[MEAS]** per-frame trace, shipped build, 530 steady authored frames (seed 40,
RC ramping 5→8, real coarse transitions incl. stage wrap). Entry raster of each
main-thread checkpoint:

| checkpoint | min | p50 | p90 | max |
| --- | ---: | ---: | ---: | ---: |
| `renderSprites` first sprite applied (`rasterInitialApplied`) | 10 | **21** | 22 | **37** |
| `armFirstBatch` / `publishRasterPlan` (`$D011` install, plan published) | 21 | **26** | 28 | **44** |
| `finishBackgroundCoarse` / `bgLowerReady` (lower-row shift) | 25 | **30** | 33 | **63 / 134** |
| `bgUpperReady` (coarse-frame upper-row prep) | 286 | **288** | 295 | 307 |
| `rasterDisplayHook` (DISPLAY event / HUD handoff) | 46 | 48 | 48 | 49 |

On the ~5 % of frames that combine dense `RENDER_COUNT = 8` + a coarse step, the
main thread runs **~14–33 rasters later** than the healthy case:
`armFirstBatch` 26→44, `finishBackgroundCoarse` 30→63 (worst observed
`bgLowerReady` 134). The BUILD-publish deadline is met with a ~200-raster margin
on a healthy frame and a shrinking margin on those heavy frames; when it is
missed, `rasterFrameReset`'s `!replay` re-runs `renderSprites` in the IRQ
(observed `RASTER_REPLAY_FRAMES` ≈ 0.5 %/frame authored, ~50 %/frame synthetic
dense16). The residual-flicker `!early` re-arm absorbs the *border* consequence
of this lateness, but the underlying timing pressure — and its visible
consequence, the scroll hitch — remains.

---

# ASTRA / OPUS ARCHITECTURAL REVIEW BRIEF

Review the current architecture **without modifying code initially** and answer
the following. Source of record: this repository at HEAD `6a64130`, branch
`experimental-border-hud`; the three prior reports
(`full-200px-gameplay-aperture-architectural-rework`,
`top-border-sprite-hud-proof`,
`intermittent-lock-and-hud-flicker-investigation`) plus this one; the commercial
decompilations `slap_fight_border_hud_annotated.asm` /
`terra_cresta_border_hud_annotated.asm`.

## A. Where is the dominant timing pressure?

Quantify, from code and from the measurements in §7 and the prior reports, the
per-frame cost and the deadline pressure of each of:

- `prepareBackgroundCoarse` — upper-row char-RAM shift + `SCROLL_ROW` wrap +
  1-row crossing buffer; runs behind the beam; coarse frames only. Measured
  `bgUpperReady` ≈ raster 288.
- `finishBackgroundCoarse` — lower-row shift (`shiftBackgroundLower`
  rows 14..24) + `restoreCrossingRow`; runs *after* `armFirstBatch`; measured
  `bgLowerReady` p50 30, max 134.
- `renderSprites` — `capturePlayerCollision`; rebuild `PLAYER_HW_MASK`; write
  the first `min(RC, 4)` hw sprites from the Y-sorted `INITIAL_*`; `$D015 |= $F0`.
  Runs in the main thread (~raster 10..37) **and** in the IRQ on a `!replay`
  frame.
- `sortObjectsByY` — insertion sort of up to 16 objects (worst case ~4.4 k
  cycles per the aperture report §Q22).
- BUILD plan construction — `buildSortedObjectList` + `buildInitialSpriteSnapshot`
  + `buildBatchSpriteSchedule` (per-slot `SLOT_FREE_RASTER`, batch `minY − 12`,
  `beginRasterPlanMasks`/`extendRasterPlanMasks`).
- LIVE plan publication — `swapRenderPlans` + `armFirstBatch` +
  `publishRasterPlan` (`sei` window; installs `$D012` compare; `jmp
  dispatchRasterEvents`). Measured entry raster p50 26, max 44.
- raster batch application — `applyLiveRasterBatch` (~100–150 IRQ cycles per
  batch; collision broad-phase; per-assignment `ASSIGN_*` writes; batch masks).
- catchup / replay machinery — `dispatchRasterEvents` `!due`/`!near`/`!service`;
  `rasterFrameReset` `!replay` (pushes 5 TEMP, `jsr renderSprites`, pops,
  `jsr startLiveRasterPlan`, `inc RASTER_REPLAY_FRAMES`).
- HUD handoff — `hudBorderSetup` (line 1) + `hudBorderHandoff` (DISPLAY event,
  raster 46–55) + the `buildBatchSpriteSchedule` slot-4..7 floor.
- BORDER handling — `borderOpenHook` (3-way guard + two polled `$D011` writes) +
  the `dispatchRasterEvents !borderHook` skip path.

Deliver a ranked list: which of these is on the critical path to the
publish deadline on a heavy (`RC = 8` + coarse) frame, and by how many cycles /
rasters each contributes to the ~14–33-raster slip.

## B. Is BUILD/LIVE still the right architecture?

Evaluate the full-frame double-buffered render-plan approach now that:

- the scroller is beam-raced (upper rows behind the beam at raster ~288, lower
  rows ahead of the beam after `armFirstBatch`);
- border-HUD time-domain slot ownership + reclaim exists (slots 4..7 handed
  back at raster 46–55);
- the project wants higher practical mux density than 5–6 while scrolling;
- late publication genuinely occurs during coarse-scroll load, exercising the
  `!replay` path and the `!early` BORDER re-arm.

Specifically: does pre-computing the *entire* frame's sprite program (initial 8 +
all batches + all masks) before a hard publish deadline help or hurt, versus
computing each hardware-sprite program just before it is needed?

## C. Would JIT / beam-driven muxing materially help?

Compare the current model against:

```
sort logical objects by Y
-> program the initial hardware sprites (as they are reached, not all up front)
-> at each slot-reuse point, program the freed slot(s) from the next object
-> schedule the next IRQ from the next object's Y - lead
```

(the Slap Fight `$1936` / Terra Cresta `$4a57` pattern: `lda $5a,x / sbc #$0e`
schedule ~14 lines ahead; `late_case: inc $d012 / rti`.)

Assess: likely cycle savings on a heavy frame; elimination of the BUILD→publish
deadline and therefore of the `!replay` path and its IRQ-time `renderSprites`;
effect on scroll stability (does removing the deadline free the ~14–33 rasters
the coarse shift needs?); complexity / regression risk; collision implications
(`capturePlayerCollision` currently runs at the top of `renderSprites` and in
`applyLiveRasterBatch`); compatibility with the HUD time-domain slot reuse
(slots 4..7 are already "reprogram at a reuse point" — is the HUD handoff just a
special case of a JIT reuse point?); whether `dispatchRasterEvents` /
`applyLiveRasterBatch` can evolve into JIT incrementally (they already program
"the next batch's slots at the next batch's raster").

## D. Could the scroller be optimised instead?

Identify whether equal or larger gains come from optimising:

- coarse upper-row prep (`prepareBackgroundCoarse` / `shiftBackgroundUpper`) —
  char-RAM `sta`-loop vs a `$D018`/`$0400`-page swap vs a scroll-offset pointer;
- coarse lower-row finish (`finishBackgroundCoarse` / `shiftBackgroundLower`) —
  same, plus whether it must run after `armFirstBatch` at all;
- the memory-copy strategy (currently full 40-byte per-row `sta`; a 2-screen
  `$D018` page flip would make coarse "free" **and** give the soft-edge mask a
  clean blank row for nothing);
- row decode (`decodeStageCharacterRow` — metatile expansion cost per row);
- splitting the coarse work across two frames (it is a divider-2 event — there
  are 15 idle frames between coarse steps);
- badline-aware scheduling of the shift (avoid the cycles the VIC steals);
- precomputation / buffering of the next incoming row during the idle frames.

## E. Recommend one of these outcomes

Make an explicit choice and defend it:

1. **Keep BUILD/LIVE; optimise the scroller.**
2. **Keep the scroller; replace BUILD/LIVE with a JIT / beam-driven mux.**
3. **Optimise both incrementally.**
4. **Architectural rewrite of both.**
5. **Current architecture is already near-optimal; accept a defined gameplay
   load envelope** (state the envelope: e.g. ≤ 6 enemies + 2 bullets + player
   while scrolling, more when static).

For the recommendation, give: expected benefit (rasters of slack recovered,
frames of `!replay` eliminated); implementation cost; regression risk (name the
specific invariants at risk — `[19656]`, the clean 55..246 body, the HUD
handoff, the border dodge, collision); the likely new supported sprite / enemy
envelope while scrolling; a migration strategy (what ships first, behind which
toggle); a test strategy (which existing oracles cover it —
`check_raster_capture`, `check_scroll_edges_rsel1`, `check_fixed_hud_capture`,
`vice_scroll_test --physical` — and what new coverage is needed); a fallback
plan if the change regresses.

## F. Do not assume the commercial code should simply be copied

The Slap Fight / Terra Cresta patterns (self-modifying `$FFFE` IRQ chain,
`$D018`-page scroll, ECM + `$D018` edge masking, HUD-sprite time-slice,
`Y − 14`-lead JIT mux, `inc $d012` late recovery) are *useful references*. Judge
each against this engine's actual constraints and measurements — the exact PAL
`[19656]` requirement, the packed VIC bank 0 (no free 2 KB), the RSEL-dodge
open-border geometry, the existing re-entrant single-dispatcher scheduler, the
`!replay`/`!early` safety machinery, and the timing numbers in §7 — rather than
recommending JIT (or a `$D018` scroller) merely because commercial games used it.

### Direct pointer for the soft-edge question

If the review lands on a `$D018`-page or bitmap-edge-row scroller (D / E), note
that it **also solves this report's AMBER for free**: a second screen page whose
outer row is blank, or a bitmap row that can be cleared, gives a clean stable
edge mask with no mid-scanline mode switch, no ECM, and no cycle-exact
stable-raster prologue. That is the strongest reason to weigh the scroller
option over pure BUILD/LIVE-side optimisation.

---

## 8. Exact code changes / remaining uncertainties / next task

### Code changes (all `#if SOFT_EDGE_MASK`, shipped OFF)

`src/main.asm`: `#define SOFT_EDGE_MASK` (commented); `GAMEPLAY_D011_BASE |= $40`
and `SOFT_EDGE_*` rasters (guarded); `initBackground` zeroes `$3800..$39FF`;
`endGame` clears `$D011` bit 6 + restores `$D022`/`$D023` + `jsr
setupStarfieldCharset`. `src/raster_scheduler.asm`: `rasterDisplayHook`
`softEdgeBodyRestore` (guarded poll + `$D011`/`$D016`/`$D022`/`$D023`);
`borderOpenHook` `!wait247` band-enter (guarded); the 3-way guard's short
branches routed via `jmp` **only** under `SOFT_EDGE_MASK`. `git diff --stat`:
`2 files changed, 147 insertions(+), 2 deletions(-)`. Shipped (mask off) binary:
byte-identical to `1fadf2b4…`.

### Remaining uncertainties

1. A cycle-exact stable-raster switch (double-IRQ or `$D012`-sync + NOP align)
   was **not** attempted end-to-end — the estimate that it reduces the residual
   to a 1-px coarse artifact is analytical, not measured.
2. The `$D022`/`$D023`-per-column-stripe path (drop the palette juggle, accept
   faint greyscale stripes in the band) was identified but not tried — it needs
   only one clean `$D011` write and might fit the 22-cycle gap.
3. `enterInitialsScreen` / hi-score text screens were not round-trip tested with
   the mask **on** (only the `endGame` → GAME OVER path); the charset restore is
   in `endGame` so they should be covered, but it is unverified.
4. NTSC untested (PAL authoritative; NTSC border compares differ).

### Recommended next task

1. **The architectural review above (A–F).** Its outcome decides whether the
   soft-edge mask is finished cleanly (a `$D018`-page scroller makes it trivial)
   or via a stable-raster prologue (if the scroller is kept).
2. If the review keeps the current scroller and still wants the mask shipped:
   a focused stable-raster-prologue pass on `softEdgeBodyRestore` /
   `borderOpenHook`'s `!wait247` (cycle-count both switch points to land the
   mode writes at a fixed cycle), then re-run this report's §6 tables.
3. Manual torture test (6 enemies + 2 bullets + player + scrolling) with
   `#define BORDER_FORENSIC` on, to characterise the scroll hitch for the review.

---

## 9. Final `git status --short`

```
 M src/main.asm
 M src/raster_scheduler.asm
?? reports/soft-edge-masking-and-astra-handoff-report.md
```

`git diff --stat`: `src/main.asm | 69 ++-`, `src/raster_scheduler.asm | 80 ++-`.
HEAD unchanged `6a64130220e87eea182f6b638d38da03524a2bc5`. Shipped build
(`SOFT_EDGE_MASK` off) `sha256(prg) = 1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd`
— **byte-identical to the residual-flicker report's baseline**. Mask-on build
`sha256(prg) = 5d8320001596e6dfecc1b6979b76dac3f5a69f251dae63027fd29a9c9cff567b`.
Toggle builds verified: `SOFT_EDGE_MASK` on, `HUD_PROOF_ENABLE` off,
`BORDER_PROOF_ENABLE` off, `BORDER_FORENSIC` off each compile.

## 10. No repository history was altered

**No `git commit`, `git push`, `git add`, `git tag`, `git reset`, `git stash`,
or branch switch was performed.** All prior uncommitted work is preserved (there
was none at task start beyond the tracked baseline). VICE was launched
head-less / background via `Popen` with output to `DEVNULL` and killed on exit;
never foregrounded; no `open -a`.
