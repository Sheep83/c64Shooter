# Stage 5B — display-state containment — worklog

**STATUS: COMPLETE — GREEN, ready for user visual acceptance.**
Full report: `/reports/stage5b-display-state-containment.md`.

Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed. Stage-5
comparison state preserved (Fable prototype in the tree with this fix on top;
Stage-5A candidate still in `reports/stage5a-candidate-as-tested.patch`).

## Binaries
- mask OFF: `80d5b0461c070fe2…` = accepted Stage 4J, byte-identical (checked
  after every edit).
- before fix: `b719de4ca86c7f54…` (starfield broken from power-on).
- after fix: `69224428ddb05c8a…`.

## Root cause (proven, not assumed)
Stage 5A put ECM into `GAMEPLAY_D011_BASE`. That constant has four consumers —
`rasterFrameReset`, `publishRasterPlan` (both gameplay, correct) and
**`main.asm:848` `init`**, which ORs it into `$D011` to build the GLOBAL boot
display state. So ECM was set on the attract screen from power-on, before any
gameplay. Measured on the broken build: `$D011=$5B` (ECM=1), IRQ `$EA31`,
GAME_STATE=0, 16 star codes 240..251 on screen.

Both symptoms are that one cause:
- ECM masks codes to 6 bits → 240..251 & 63 = 48..59 = ROM digits (measured
  244→'4', 242→'2', 246→'6', 240→'0').
- The starfield's smooth motion is **glyph phase**, not `$D011` fine scroll
  (`drawOneStar`: `STAR_CHAR_BASE + size*4 + STAR_PHASE`; `updateStarfield`
  advances phase 0..3 = 2-pixel steps). Phases 240..243 collapse to '0','1','2','3',
  so only the whole-row `STAR_Y` step remained visible.
- Fine-scroll bits were NOT corrupted (YSCROLL=3 on title, as intended).
- Stage-5 raster events were NOT running outside gameplay (`endGame` disables the
  raster IRQ and restores `$EA31`) — the leak was purely the constant.

## Fix (ownership, not more clearing)
- `GAMEPLAY_D011_BASE` = DEN|RSEL only; new `.const EDGE_MASK_D011_BAND = $40`.
- `initRasterScheduler` (called only from `startGame`) establishes the band once
  at gameplay entry.
- `rasterFrameReset` ORs the band every frame (gameplay IRQ chain only).
- `publishRasterPlan` PRESERVES the live band/body bit (must not force either:
  forcing band would black a frame after the aperture opened, forcing body would
  unmask the top band).
- `endGame` ECM clear kept as teardown safety net. `init` instruction unchanged —
  it simply can no longer inherit ECM.

## Extra gap found and closed
`publishRasterPlan` only preserves, and on the first frame of a game it can run
before the first `rasterFrameReset` → that frame rendered unmasked (one-frame
edge flash at game start). Closed by the `initRasterScheduler` establish;
lifecycle checkpoints 2 and 6 (`$D011=$50` on the FIRST `gameplayPresented` of
both games) are the proof.

## Evidence
Lifecycle, all 7 checkpoints OK: title ECM=0/16 stars; first gameplay frame
ECM=1; steady gameplay ECM=1 (12/12 samples at raster 19, YSCROLL cycling 6,7,0);
GAME OVER ECM=0; attract after game ECM=0; second game first frame ECM=1; second
game steady ECM=1.

Regression (all `[19656]`, 0 incomplete, 0 sprite-start misses incl. `--dense`):
idle 300, wave 320, wrap 340 (3 known pre-existing failures), y199 400, dense 200,
turret 500, stress 500. Aperture fixed **58..247 on 130/130 frames** for wave,
wrap, dense, turret, stress — mask unchanged.

## Gotchas
- VICE monitor `m` only responds when the machine is halted — every sample needs
  a breakpoint; `x` alone leaves the monitor unable to read.
- Probing right after entering gameplay samples the FIRST frame; advance ~25
  frames with repeated `x` for steady state.
- The starfield does not use `$D011` fine scroll at all — do not "fix" YSCROLL
  when its motion looks wrong; check glyph codes first.

## Out of scope, untouched
Historical six-enemy hitch, duplicated-turret hitch, Stage-4F
`ssFlipMirrorPtrs`-after-batch race (wrap frame 88), dense signature.
Repo is now clean of the display-state leak, so the hitch investigation can start
from a sound base.
