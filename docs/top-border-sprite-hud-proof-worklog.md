# Top-border sprite-HUD proof — worklog

Branch `experimental-border-hud`, HEAD `44e735c` ("pre-architecture-teardown").
Prior open-border task uncommitted (`M src/main.asm`, `M src/raster_scheduler.asm`,
+ docs/full-200px-*). No commit, no push.

Goal: static 4-sprite hires HUD in the opened TOP border, with those 4 physical
slots reclaimed by gameplay lower in the frame -- time-domain ownership, NO
permanent reservation. Keep clean terrain 55..246.

## Starting geometry (from the open-border task)
- RSEL=0; rasterFrameReset installs `$D011 = RASTER_DISPLAY_FINE | $10` @ line 1.
- borderOpenHook (@RASTER_BORDER_LINE 240): RSEL 0->1 @245, RSEL 1->0 @250 ->
  BOTH borders open every frame. `$3FFF/$39FF = $00` -> idle = solid $D021.
- Clean body r55..246. Soft edges r52-55 / r247-254 (~6px pop / coarse).
- Top border region r~16..51 = solid $D021 backdrop -> HUD canvas.
- multiplexIRQ dispatcher events: FRAME(line1), SPRITES(batches), DISPLAY(line
  56, a NO-OP since Phase 1.5), BORDER(line 240).
- renderSprites (main thread, ~raster 5-15): writes slots 0..RENDER_COUNT-1 from
  LIVE INITIAL_* (Y-sorted asc); `$D015 = SPRITE_ENABLE_MASK[RC]`; records
  PLAYER_HW_MASK. Batched objs 9-16 -> applyLiveRasterBatch, slots via
  SLOT_FREE_RASTER.
- Player = logical obj 0, NOT hw-slot-pinned; tends to a HIGH slot (Y~220 = last
  rank).

## Design

HUD owns hardware slots **4,5,6,7** (high 4). Reason: the deferred gameplay
sprites are then ranks 4..7 = the HIGHEST-Y initial objects (latest DMA, biggest
handoff margin); the topmost gameplay sprites (rank 0..3, earliest DMA) are NOT
deferred. The player (usually rank 4..7) is deferred -> handoff sets PLAYER_HW_MASK.

- **HUD bitmaps**: 4 x 64B hires at `$2f00` (gap $2e6a..$2fff in VIC bank 0),
  pointers `$bc..$bf`. Distinct patterns (digits / bars / diagonal / slot-number)
  so corruption or a HUD<->gameplay swap is obvious.
- **HUD Y = 22** (tune): body r22..42, DMA done ~r42, clear of r55 by 13px.
- **HUD X = 40, 120, 200, 280** (4 across the visible width).
- **hudBorderSetup** (every frame, from rasterFrameReset @ line 1): program
  slots 4-7 X/Y/ptr/colour; `$D01C &= $0F` (4-7 hires); `$D010 &= $0F`;
  `$D017=$D01D=$D01B=0`.
- **renderSprites**: cap the initial write at `min(RENDER_COUNT,4)` slots;
  `$D015 = SPRITE_ENABLE_MASK[capped] | $F0` (keep HUD on). Slots 4-7 untouched.
  `HUD_DEFERRED_COUNT = max(0, RC-4)` recorded for the handoff.
- **hudBorderHandoff** = repurpose the neutered DISPLAY event: `RASTER_DISPLAY_LINE`
  56 -> `HUD_HANDOFF_RASTER` (~46, tune); `rasterDisplayHook` -> re-apply
  INITIAL_*[LIVE_PLAN + s] for s=4..RC-1 into slots 4-7 (ptr/col/X/Y/X-MSB),
  `$D01C |= $F0` (restore MC), `$D015 = SPRITE_ENABLE_MASK[RC]` (drop HUD-leftover
  slots), set PLAYER_HW_MASK if a reclaimed slot owns object 0.
- **buildBatchSpriteSchedule**: after `!initSlots`, floor `SLOT_FREE_RASTER[4..7]`
  at `HUD_HANDOFF_RASTER` so no batch reuses a HUD slot before the handoff.

## Implemented
- `#define HUD_PROOF_ENABLE` (top of main.asm); HUD_* consts.
- `hudProofSprites` 4x64B hires @ $2f00 (ptr $bc..$bf); `hudProof{Ptr,X,XMsb,Colour}`
  tables in the $1f00 lookup segment. hudBorderSetup / hudBorderHandoff placed in
  the $4000 code segment tail ($5864 / $58a1; +177 B, ~213 B headroom to $5a00).
- `hudBorderSetup` (jsr from rasterFrameReset @ line 1): programs hw slots 4..7
  = HUD (ptr/col/X/Y=22), `$D01C &= $0f` (4..7 hires), `$D010` 4..7 = HUD_D010_KEEP
  ($80, sprite 3 @ X=280), `$D017=$D01D=$D01B=0`.
- `renderSprites`: initial write capped at HUD_SLOT_FIRST (4) slots;
  `$D015 = SPRITE_ENABLE_MASK[capped] | $f0`; final `$D010` ORs HUD_D010_KEEP.
- `hudBorderHandoff` = repurposed DISPLAY event (`RASTER_DISPLAY_LINE =
  HUD_HANDOFF_RASTER = 46`): re-applies INITIAL_*[LIVE+s] for s=4..RC-1 into
  slots 4..7 (ptr/col/X/Y/X-MSB), sets PLAYER_HW_MASK if a reclaimed slot owns
  obj 0, `$D01C |= $f0`, `$D015 = SPRITE_ENABLE_MASK[RC]`. IRQ scratch
  HUD_HO_RC / HUD_HO_MSB (raster-state block, NOT the TEMP_* main scratch).
- `buildBatchSpriteSchedule`: floor `SLOT_FREE_RASTER[4..7]` at HUD_HANDOFF_RASTER.
- Diagnostic bottom-border marker (`borderOpenHook`) guarded out under HUD_PROOF
  (it wanted slot 7).

## MEASURED — the proof works
- HUD: 4 distinct hires sprites render at rasters ~23..43 (Y=22), full width
  (X 40/120/200/280), on the clean $D021 top-border backdrop; clear of the
  clean terrain @55; `hud_top_full.png`.
- Slot reuse (8 enemies + player, RENDER_COUNT=8, player = rank 7 -> deferred):
  - raster 36: slots 0-3 = gameplay enemies, slots 4-7 = HUD (ptr bc..bf, Y=22),
    `$D01C = %00001111`.
  - raster 64 (post-handoff): slots 4-7 = GAMEPLAY -- enemies Y140/160/180 +
    **the player in slot 7** (ptr $60, Y=200, col 2); `$D01C = %11111111`.
  - Same physical slots, HUD early -> gameplay late. NO permanent reservation.
- `$D015`: renderSprites `$FF` (mask[4]|$f0); handoff `mask[RC]` (drops HUD-only
  bits when RC<8).

## Oracle updates (architecture-split awareness -- cf. prior task's check_scroll_edges RSEL=1)
- Added `hudSlotReclaimed:` trace label in `hudBorderHandoff` (`$5900`), X = the hw
  slot just re-applied.
- `check_raster_capture.py`: merges `rasterInitialApplied` + `hudSlotReclaimed`
  (sorted by clock) so a HUD frame still shows the full initial-slot set
  `0..RENDER_COUNT-1` in beam order, AND the handoff re-application of each deferred
  slot is deadline-checked (`line*63+cycle <= y*63+55`). Also a defensive
  `span==0` guard on the pre-existing `rasterBatchMasksApplied` deadline path
  (rare capture-start race, unrelated to the HUD).
- `vice_scroll_test.py` + `vice_raster_cases.py`: trace the new label.

## Handoff raster geometry (measured, build/hud-wave timing.log)
- HUD_Y = 22 -> HUD sprite DMA p-access ~raster 21, display rasters 22..42.
- DISPLAY event `RASTER_DISPLAY_LINE = HUD_HANDOFF_RASTER = 46`; `rasterDisplayHook`
  entry measured at raster **47** (cycle 18..27).
- `hudBorderHandoff` first `hudSlotReclaimed` at raster **49**; all deferred slots
  (up to 8) re-applied by raster **52..54** worst case.
- Deferred sprite = Y-rank 4..7 (the HIGHEST-Y quartile of the initial set). Its DMA
  p-access is line (Y-1). Handoff done by ~r54 => safe for any deferred sprite with
  Y >= 56. The topmost sprites (rank 0..3, nearest the r55 aperture floor) are NEVER
  deferred -- the capped frame-top `renderSprites` write keeps them in slots 0..3.
- Measured 0 sprite-start misses in every scenario, incl. 8 sprites at Y71
  (viewport_early95/viewport_top_dma) and Y51..70 (clip_eight: deferred rank-4 = Y63,
  DMA line 62, ~8-line margin), clip_boundary.

## Trusted battery -- ALL GREEN
- check_raster_capture (physical PAL frames):
  | capture | frames | peak obj | batch | catchup | replay | dcyc | svc | miss |
  | hud-ord idle       | 200 |  1 | 0 |    0 |  0 | [19656] | 0 | 0 |
  | hud-wave seed382   | 260 |  9 | 0 |    0 |  3 | [19656] | 0 | 0 |  (ramps 1..8, incl 5- & 6-enemy)
  | hud-wrap seed12    | 320 |  9 | 1 |    2 |  5 | [19656] | 0 | 0 |  (stage wrap + coarse)
  | hud-dense 16obj    | 200 | 16 | 8 | 1393 | 99 | [19656] | 0 | 0 |  (== baseline ob-dense exactly)
  dense catchup/replay per-frame rate identical to HUD-off baseline.
- vice_raster_cases top-cluster handoff stress (40f, 16obj, +hudSlotReclaimed trace):
  viewport_early95 / viewport_top_dma / clip_eight / clip_boundary -> all [19656], 0 svc, 0 miss.
- check_scroll_edges_rsel1 --aperture 55 246: hud-ord/wave/wrap/dense ->
  body_temporal_diffs 0, lastrow_temporal_diffs 0, median edge jump 0, all 8 fine
  phases + repeated 7->0 coarse. Matches open-border baseline (0/0).
- hud_proof.py register EARLY(r36)/LATE(r80) proof:
  dense RC=8  -> 48/48 EARLY slots4-7 = HUD (byte-identical to frame0 ref), 48/48 LATE
                slots4-7 = gameplay (ptr/col/Y = LIVE INITIAL_*, $D01C MC restored,
                no HUD-leftover $D015 bits); slots 4..7 ALL reused late -> no reservation.
  wave seed382 -> 57/57 sampled pass (3 main-behind catchup frames skipped; covered
                by the beam-truth persistence test).
- hud_persist.py beam-truth (screenshot every frame, read $D015 at HUD raster):
  wave peak-7  -> 120/120 frames all 4 HUD sprites visible + $D015 HUD bits set.  {4:120}
  dense 16obj  ->  90/90 frames.  {4:90}   NO flicker / drop / colour corruption.
- vic_audit.py (7 active): r28 s4-7 = HUD (X40/120/200/280 Y22 ptr bc-bf,
  $D015=%11111111, $D01C=%00001111 hires, $D010 bit7, $D017=$D01D=$D01B=0,
  col 1/7/13/3). r82 post-handoff: s4-6 = reclaimed gameplay, s7 disabled (RC=7,
  $D015=%01111111), $D01C=%11111111 MC restored, $D010 bit7 cleared.
- sprite_y_sweep.py Y50..82: in_live_plan / d015_bit / first_visible_raster /
  collision_eligible IDENTICAL to the pre-HUD baseline sweep. No dead zone.
- Build: `#define HUD_PROOF_ENABLE` (main.asm:17) commented out -> clean build,
  reverts to the open-border engine (diff = only $2f00 bitmaps, $5864-$592a routines,
  $1f4b-$1f5a tables + downstream position shift).

## Top soft-edge pop
- Pop is at rasters ~52..55 (once per coarse cycle), BELOW the r55 aperture and
  9+ rasters below the HUD band (22..42). No interference; no masking required or
  claimed. HUD backdrop = the same solid $D021 the open-border task delivered.

## Verdict: GREEN
- HUD stable in the opened top border; uses border not terrain; terrain stays
  55..246 (scroll-edge 0/0); same physical slots 4..7 reused by gameplay lower in
  the frame; all 8 slots available after handoff (dense RC=8); NO permanent
  reservation (RC<8 -> slots disabled, not reserved; dense proves instant reuse);
  no top dead zone; no scroll/cadence/capacity regression; [19656] exact; normal +
  6-enemy + dense-16 + wrap all clean.
- Harness note (not AMBER): vice_level1_smoke.py sustained free-run flaked with VICE
  monitor socket timeouts at non-deterministic points (reproduced on retry, pattern
  is HUD-independent); end-to-end real-gameplay coverage is carried by hud-wave
  (260f authored waves + turret pool) and hud-wrap (320f wrap+coarse), both clean.
- Final sha256(build/shooter.prg) 65bb0d2c3c116e93.  No commit/push/branch/tag.

## Progress
- [done] implement + measurement (HUD visible, slots reclaimed incl. player).
- [done] oracle split-awareness; handoff geometry measured.
- [done] full trusted battery -> GREEN.
- [done] report: /reports/top-border-sprite-hud-proof-report.md.
