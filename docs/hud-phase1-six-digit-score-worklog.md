# HUD Phase 1 — six-digit score : worklog

## Objective

Replace the 16-bit score with a 24-bit (000000..999999, saturating) score and
display it as a minimal slim green six-digit number using **two hires sprites**
in the already-proven top-border HUD, without reducing gameplay sprite capacity.

Score only. No overheat / lives / weapons / HUD framing.

## Starting state (audited 2026-09-10)

- branch `main`, HEAD `f71ea24` (`Add stable scroller/pointer checkpoint report`),
  clean tree. Tag `stable-scroller-and-sprite-pointers` = `c349fe2`.
- Production scroller = double-buffered (Stage 4J default): page A `$0400`,
  page B `$2800`, charset `$3800`, `$D018` flip publication, page-aware sprite
  pointer tables `$07F8` / `$2BF8`.

### Score (old)

| item | location | notes |
|---|---|---|
| `SCORE_LO` / `SCORE_HI` | main.asm ~4921 | **16-bit**, ceiling 65535 |
| `SCORE_VALUE_LO/HI` | ~4923 | conversion scratch |
| `SCORE_DIRTY` | ~4925 | set by `awardKillScore` |
| `SCORE_PER_KILL` | 495 | 100 |
| `setupScoreDisplay` | 3695 | clears score; **also draws "SCORE 00000" into `SCORE_SCREEN = $0400+29`** — leftover from the retired character HUD, now writes into terrain row 0 |
| `awardKillScore` | 3722 | 16-bit add, sets dirty. Callers: main.asm:2542 (enemy death), background_turrets.asm:813 (turret kill) |
| `refreshScoreIfDirty` | 3739 | **stub** — only clears the dirty flag; called once/frame at main.asm:1059 |
| `displayScore` | 3756 | retained but **never called**; 16-bit -> 5 digits into retired `HUD_SCORE_CELL` |
| `debugDivisorLo/Hi` | 3935 | 5-entry 16-bit divisors (10000..1) shared by `displayScore`, `displayCycleMinimum`, `formatScore5` |

### High score (old)

`HISCORE_LO` / `HISCORE_HI` `.fill HISCORE_COUNT(8)` — 16-bit per entry.
`HISCORE_START_SCORE = 100`. `checkHiscore` (1168) 16-bit compare,
`insertHiscore` (1361) 16-bit, `seedHiscoreTable` (1557), `renderHiscorePage`
(~1614) with `HISCORE_ROW_WIDTH = 10` ("III  DDDDD") via `formatScore5`.

### Top-border HUD (proven, must be preserved)

- `HUD_SLOT_FIRST = 4`, `HUD_SPRITE_COUNT = 4` -> hardware slots **4..7**.
- `HUD_Y = 22` (body rasters 22..42), `HUD_HANDOFF_RASTER = 43`
  (`SCROLL_EDGE_MASK` on), `HUD_HANDOFF_COMPLETE_RASTER = 56`.
- `HUD_SPRITE_BASE = $2f00`, 4 x 64 B (`$2f00-$2fff`), pointers `$bc..$bf`.
- data tables `hudProofPtr` / `hudProofX` / `hudProofXMsb` / `hudProofColour`
  (X = 40/120/200/280, colours 1/7/13/3), `HUD_D010_KEEP = $80` (slot 7 X=280).
- `hudBorderSetup` (line-1 IRQ) programs slots + `$D015 |= $F0` + `$D01C` HUD
  bits cleared (hires) + `$D010`. `hudBorderHandoff` (DISPLAY event at
  `HUD_HANDOFF_RASTER`) reclaims 4..7 for gameplay.
- Both write page A `$07F8` **and** page B `$2bf8` unconditionally
  (Stage 4H publication-race repair) — must be preserved for the score too.

## Design decisions

- **24-bit score** `SCORE_LO/MID/HI`, **saturate at 999999** (`$0F423F`).
- Central `addScore` (input `SCORE_ADD_LO/MID/HI`), `awardKillScore` becomes a
  thin wrapper. X/Y preserved (absolute addressing only).
- **High score 24-bit** `HISCORE_LO/MID/HI`; `formatScore6`;
  `HISCORE_ROW_WIDTH` 10 -> 11.
- **Decimal conversion** `convertScore6`: repeated subtraction against a 6-entry
  24-bit divisor table (100000/10000/1000/100/10/1). Simple + obviously correct.
- **Digit font** 5x7, 1px stroke, row-table (10 x 7 bytes), pattern in the top
  5 bits of each byte.
- **8-pixel digit pitch** => each digit is **byte-aligned** inside the sprite
  (columns 0/1/2), so composition is `sta` with no shifting, and the 3px gap is
  identical inside a sprite and across the sprite join.
  Number spans 45 px. Sprite1 X = 162, sprite2 X = 186 => span 162..206,
  centre 184 = exact display centre. Both X < 256 => no `$D010` MSB needed.
- **HUD slot use:** score = slots **4 and 5** (bitmaps `$2f00` / `$2f40`,
  pointers `$bc`/`$bd`). Slots **6, 7** become transparent (`blankSprite`)
  so the proven 4-slot setup/handoff geometry is untouched and **no gameplay
  sprite capacity changes**. Old diagnostic proof sprites retained behind
  `HUD_PROOF_PATTERN`.
- Digits at sprite rows **7..13** (rasters 29..35) — inside the opened top
  border, clear of the handoff.
- Colour: **13 (light green)** on the `$D021` terrain backdrop (12, med grey).
- `refreshScoreIfDirty` becomes the real rebuild, split into a SEVEN-FRAME
  state machine (`SCORE_PHASE`). See "Timing correction" below.

## Timing correction (found during measurement, not design)

The first implementation did the whole rebuild (convert + compose) in one call
from the main loop. Measured in situ that is **up to ~7,000 cycles (111 raster
lines)** at score 999999. The main loop can reach this call site as late as
raster ~299, so on a busy frame it overran `waitForGameFrame` and **dropped a
presented frame** (`applyFineScroll` period 39320 instead of 19656) - i.e. it
re-introduced exactly the scroll hitch Stages 0-4 removed. Baseline never shows
that period.

Two changes fixed it, both measured:

1. **Per-place conversion.** `convert24to6` was split into `convertScorePlace`
   (one decimal place, <= 9 subtractions, bounded ~800 cycles) and a thin
   six-place wrapper. `refreshScoreIfDirty` now runs one place per frame:
   phase 0 -> 2 snapshots the score and does place 0, phases 2..6 do places
   1..5, phase 7 composes. Every per-frame chunk is now the same order as the
   compose (~400-950 cycles), and zero frames are dropped in any regime.
   The whole-value `convert24to6` survives for setup and the high-score page,
   where a spike cannot matter.
2. **Ceiling early-out in `addScore`.** An award onto an already-saturated
   999999 no longer sets `SCORE_DIRTY`, so a player parked at the ceiling
   cannot make the HUD re-run the most expensive conversion there is, every
   kill, for digits that cannot change.

The snapshot at phase 0 -> 2 is what makes the spread safe: the six places are
converted from a frozen copy, so a kill landing mid-rebuild cannot produce a
half-old/half-new number. Cost: visible latency is <= 7 frames (~140 ms); the
score VALUE is exact immediately.

Only phase 7 touches a sprite bitmap, it is bounded at ~510 cycles (~8 raster
lines) with no data-dependent path, and it could enter as late as raster 311 and
still finish by line ~8 - well clear of the HUD sprite DMA window (21..43).

## Status

- [x] Phase A audit
- [x] implementation
- [x] tests (score correctness, sprite ownership/handoff, timing, regression)
- [x] report -> `reports/hud-phase1-six-digit-score.md`

Build: `3a8158152f9ef3f12a76cf9bd50bf15f1e0f5f49fb148aa0e83223ae051f80c4`
(baseline HEAD f71ea24 = `f1d08a0f5d2337eef0a75a28a68d4261e9166474e47d655f9c886aa4f2ec6652`).

---

# Phase 1.1 — presentation pass + restore collision

## Font

Measured first: filled all 21 HUD sprite rows solid and screenshotted. Screen
rows 7..27 all lit, 48 px wide, no clipping at either end — so the **full 21-row
sprite height is presentable** in the opened top border at `HUD_Y = 22`
(body rasters 22..42, handoff at 43). No raster change was needed to use it.

New font is 6 px wide x 21 px tall in the same 8 px byte-aligned cell:
`HUD_SCORE_GLYPH_H` 7 -> 21, `HUD_SCORE_TOP_ROW` 7 -> 0, `HUD_SCORE_X_L`
162 -> 161 (span 6*8-2 = 46 px). Compositor is parameterised by those constants
and adapted unchanged.

## Timing — why the compose became double buffered

The 21-row font tripled the composition: measured **1,169–2,152 cycles
(up to ~34 raster lines)** in situ, against ~400 in Phase 1. Phase 1's guarantee
was "the bitmap write is safe from ANY entry raster"; at 34 lines that is simply
no longer true — from a late entry it would still be writing during the HUD
sprites' DMA at rasters 21..43 of the next frame.

A raster gate was tried first and rejected: the compose cost varies with ambient
badline/sprite DMA, so any fixed "latest safe start" constant is tuned against a
measurement that moves between runs.

Instead the score sprites are now **double buffered**. The compositor draws into
the pair the VIC is not fetching, then publishes it by rewriting `hudProofPtr`,
which the existing `hudBorderSetup` republishes to BOTH `$07F8` and `$2BF8` at
the line-1 IRQ. The compose therefore has **no raster deadline at all** — its
duration stopped being a correctness question. The back pair reuses HUD slots
2/3 (`$2f80`/`$2fc0`), which were allocated but pointed at `blankSprite` and
never displayed, so this costs no new memory. The two-byte publish is held under
SEI so `hudBorderSetup` cannot observe a half-updated pair.

## Collision

`DEBUG_PLAYER_INVULNERABLE` 1 -> 0. It is a documented development toggle, not a
workaround for a defect: both guarded sites suppress only the final `PLAYER_HIT`
store, and every overlap test ran regardless. One character changed.

## Player colour

The hull was 110 px of `$D026` — the SHARED light grey that every enemy and
turret also uses — so `OBJECT_COLOUR` alone could not recolour the ship.
Multicolour bit pairs `10` and `11` were swapped in `playerSprite` /
`playerFireSprite`: the hull now indexes the PER-SPRITE colour register and the
old spine becomes a light-grey highlight. Silhouette is byte-for-byte identical;
`$D025`/`$D026` are untouched, so no enemy or turret changed colour.

`PLAYER_COLOUR_NORMAL = 14` (light blue), `PLAYER_COLOUR_MUZZLE = 2` (red).

## Correction to a Phase 1 finding

Phase 1 reported passive `body_temporal_diffs: 32` as a stable pre-existing
artifact. It is **not stable**: re-running the pristine baseline gives 32 on one
run and 0 on another. The diffs sit at rasters 61–62 (8 px), just inside the top
of the body band where reclaimed gameplay sprites appear, so the metric tracks
CIA-random wave timing. It is run variance, not a build property.

Build: `fd42763699bf51c2edf463249d785470eaf499faef4f457dac7f17fe517f8f8c`
