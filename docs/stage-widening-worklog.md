# Stage / world-row addressing widening worklog

## Objective

Widen the metatile stage addressing from the current 8-bit / 25-metatile-row
model to safely support **>= 400 metatile rows** (10 wide, 4x4 char metatiles):

- 400 metatile rows, 10 wide  -> 4,000-byte flat `stageMetatileRows` map
- 1,600 logical character rows
- correct scrolling + full-stage vertical wrap
- metatile IDs stay 8-bit; 16 definitions unchanged
- multicolour terrain rendering, static turrets, all proven timing/gameplay
  fixes preserved

Minimum-safe widening only. No redesign of scroller / raster / multiplexer /
BUILD-LIVE ownership. No commit / push.

## Baseline (verified)

- branch `multicolour-with-turrets-experiment`, HEAD `fff83be` "bg-gfx hitching fixed"
- working tree clean at task start
- builds clean: `cd src && java -jar ~/dev/tools/kickassembler/KickAss.jar main.asm -odir ../build -o ../build/shooter.prg -vicesymbols`
- Proven changes present (grep-verified): `TEMP_SORT_I` sorter fix; `//jsr updateCycleDebug`
  FREE disabled; `SCORE_DIRTY`/`refreshScoreIfDirty`; `planCoarseBulletSuppression`/
  `noteCoarseSuppressionOutcome` presentation suppression; `TURRET_STATIC_STYLE=4`;
  `pulseTurretColour`; `MAX_ENEMY_BULLETS=3`; `MAX_OBJECTS=16`; `SORTED_COUNT>=8`
  turret-fire mitigation.

## Old 8-bit blockers (audited in current source)

| symbol / site | file:line | old repr | role |
|---|---|---|---|
| `SCROLL_ROW` | main.asm 4009 | `.byte` | persistent world row shown at matrix row 1; decremented by coarse, wraps 0->SLR-1 |
| `BG_LOGICAL_ROW` | main.asm 4019 | `.byte` | decoder input row |
| `BG_METATILE_ROW` | main.asm 4022 | `.byte` | logicalRow>>2 |
| `BG_ROW_BASE` | main.asm 4023 | `.byte` | metatileRow*10, stageMetatileRows byte offset |
| decode `lsr lsr` | main.asm 5036-5038 | 8-bit | logicalRow/4 caps metatile row at 63 |
| decode `metatileRow*10` | main.asm 5039-5047 | 8-bit asl/adc | overflows above row 25 |
| decode `lda stageMetatileRows,x` | main.asm 5052-5056 | 8-bit abs,X (max 249) | stage-map lookup |
| `renderStageRowToScreen` wrap | main.asm 4996-5004 | 8-bit cmp/sbc `#STAGE_LOGICAL_ROWS` | incoming logical row = SCROLL_ROW+BG_DEST_ROW-1 mod SLR |
| `prepareBackgroundCoarse` advance | main.asm 5223-5229 | 8-bit `lda#0? / #SLR / sbc#1` | world-row step + wrap |
| guard `SLR*MPR > 256` | main.asm 111 | compile-time `.error` | hard cap at 25 rows |
| `initBackgroundTurrets` `!row` | background_turrets.asm 91-100 | 8-bit add + `cmp #SLR` | turret underlay capture row |
| `positionBackgroundTurrets` | background_turrets.asm 246-283 | 8-bit `turretWorldRow - SCROLL_ROW` | turret screen row / visibility |
| `installTurretRow` | background_turrets.asm 174-185 | `ldx BG_LOGICAL_ROW` into `turretRowGlyph`/`turretRowColumn` (SLR-byte LUTs, .align $100) | per-row turret glyph install |
| `turretWorldRow` | background_turrets.asm 602 | `.fill TURRET_COUNT, row` (1 byte) | turret world char row |

Classification: A metatile ID width = 8-bit (unchanged). B logical char row =
16-bit LE. C metatile row = 16-bit LE. D stage-map byte offset / pointer = 16-bit.

## Memory

Segments in build: `$2920-$2e13` (scroll routines incl. decode), `$4000-$5841`
(unrolled shift copy code + stage_test data + initFixedHud, guard `*>$6000`),
`$6000-$634f` raster_scheduler (guard `*>$8000`), `$8800-$8fdf` background_turrets
(guard `*>$a000`).

Stage data is currently `metatileDefs` (256 B) + `stageMetatileRows` (250 B) at
$5594 inside the $4000 segment. A 4,000-byte map there would run to ~$6634 and
collide with raster_scheduler at $6000.

Plan: relocate the `#import "stage_test.asm"` block to its own origin `* = $6600`
(after raster_scheduler's real end $634f), tighten raster_scheduler's build guard
from `*>$8000` to `*>$6600`, add `STAGE_TEST_END > $8800` collision guard. Region
$6600-$87FF is otherwise unused. No code moves; no VIC asset moves.
`turretRowGlyph`/`turretRowColumn` (2 x SLR bytes) are removed, shrinking
background_turrets.

## Implementation state — COMPLETE

- [x] engine changes (src/main.asm, src/background_turrets.asm, src/raster_scheduler.asm)
- [x] build clean (25-row stage): `$6600-$67f9` stage data, all guards pass
- [x] host arithmetic oracle: tools/check_stage_addressing.py PASS (every logical
      row 0..1599 + headroom to 6553 metatile rows + all task offset/wrap points)
- [x] fixture generator tools/make_stage_fixture.py + tools/run_stage_fixture.sh
- [x] real-6502 decode probe tools/vice_stage_widen_probe.py: 25/64/256/400-row
      builds, BG_INCOMING_ROW / BG_METATILE_ROW / BG_ROW_BASE / BG_TILE_ROW_OFS
      byte-exact vs model for max rows 99/255/1023/1599; wrapBgLogicalRow OK
- [x] 25-row equivalence: check_scroll_capture / check_fixed_hud_capture /
      check_turret_capture / check_raster_capture all PASS, frame_cycle_deltas
      [19656], 0 failures, 0 sprite-start misses. Dense (8 batches): deferred 227
      == HEAD 227, cadence [19656], 0 failures.
- [x] 400-row wrap capture (seed SCROLL_ROW=30, 1100 frames): 0 failures, 58.8M
      pixel checks, stage_loops 1, first_transition_ok, stage_step_errors [],
      frame_cycle_deltas [19656].
- [x] turret large-row fixture (turretRows 255/260/1024 on 400-row stage):
      tools/vice_turret_large_row.py PASS (position/visibility, glyph install,
      colour pulse + restore, hit/destroy).

## Timing (cycles, IRQ/DMA off, measured via $7000 trampoline)

| routine | HEAD | widened | delta |
|---|---|---|---|
| decodeStageCharacterRow | 1242 | 1246 | +4 |
| renderStageRowToScreen (decode+copy+installTurret) | 1924 | 2056 | +132 |
| installTurretRow (no match) | 18 | 94 | +76 |
| positionBackgroundTurrets (3 turrets) | 160 | 310 | +150 |
| wrapBgLogicalRow | - | 26 | new (folded into render) |

renderStageRowToScreen runs once per coarse step (+ 23x one-time at init).
positionBackgroundTurrets runs once/frame before prepareBackgroundCoarse.
Net effect on the protected coarse window: none measurable - dense-mode
deferral count is identical to HEAD (227 == 227 over 500 frames), cadence stays
exactly 19656, no sprite-start or raster-service misses.

## Files changed

- src/main.asm: 16-bit SCROLL_ROW / BG_LOGICAL_ROW / BG_METATILE_ROW /
  BG_ROW_BASE; wrapBgLogicalRow; 16-bit decode arithmetic + (zp),Y stage-map
  pointer; 16-bit renderStageRowToScreen + prepareBackgroundCoarse; obsolete
  >256 guard replaced; stage_test.asm #import relocated to `* = $6600`.
- src/background_turrets.asm: turretWorldRow 16-bit + turretWorldRowHi /
  turretWorldRow2 / turretWorldRow2Hi; turretRowGlyph/turretRowColumn LUTs
  removed; installTurretRow -> 3-turret 16-bit compare; positionBackgroundTurrets
  + initBackgroundTurrets row math 16-bit; TURRET_REL_LO/HI scratch.
- src/raster_scheduler.asm: build guard `* > $8000` -> `* > $6600`.
- tools/check_scroll_capture.py: read SCROLL_ROW as 16-bit when SCROLL_ROW_HI exists.
- tools/vice_scroll_test.py: `--seed-scroll` to reach a large stage's wrap in-window.
- new: tools/check_stage_addressing.py, tools/make_stage_fixture.py,
  tools/run_stage_fixture.sh, tools/vice_stage_widen_probe.py,
  tools/vice_turret_large_row.py.

## Max safe stage height

- by 16-bit arithmetic: metatileRow*10 < 65536 -> STAGE_METATILE_ROWS <= 6553
  (65530 map bytes); STAGE_LOGICAL_ROWS <= 65535 -> <= 16383 metatile rows.
  Combined arithmetic ceiling: 6553 metatile rows.
- by current memory map: stage data at $6600, must end <= $8800 (turret
  segment). metatileDefs 256 B + N*10. $8800-$6600-256 = 8448 -> N <= 844
  metatile rows (8,440-byte map, 3,376 logical rows). Guarded by
  `STAGE_TEST_END > $8800`.
- effective safe maximum for the editor: 844 metatile rows (>= the 400 required).
  400 rows uses $6600-$769f, ~4.3 KB of the ~8.4 KB region.

Nothing left to do. Working tree holds the widening; nothing committed.
