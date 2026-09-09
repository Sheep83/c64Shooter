# Four-turret cluster flicker — forensics worklog

**STATUS: AMBER.** Real count-scaling defect found and fixed; user percept not
machine-captured; 2→3 threshold DISPROVEN.
Full report: `/reports/four-turret-cluster-flicker-forensics.md`.

Branch `main`, HEAD `d60828a`, nothing committed/staged/tagged/pushed.

## Two fixture errors that invalidated the previous investigation
1. **`vst_hitch.py` holds FIRE every frame** (`jpdb 1 {255 ^ (16|direction)}`,
   bit 4 = fire). All earlier "passive" captures were shooting turrets dead
   (health 3→2→1→0 in ~8-frame steps). New `run_passive.sh` / `vst_passive.py`
   hold `jpdb 1 ff` throughout: alive=1624, dead=0. **Use these for passive work.**
2. Earlier passive captures used the **mask-OFF** build; the user runs mask-ON.

## Defect found
`positionBackgroundTurrets` sets `TURRET_VISIBLE` only for `72 <= TURRET_Y < 232`
("combat only while the full 16px body is visible") — a COMBAT predicate.
`pulseTurretColour` gated on it as a PRESENTATION predicate, while the glyph
writers (`installTurretRow`, `ssReconcileTurretSlot`) gate only on AUTH+HEALTH.
So a turret straddling the top/bottom aperture edge is DRAWN but UNCOLOURED and
renders in flat terrain colour. Dropouts by (rel, VISIBLE): (0,0)×36 [top],
(21,0)×45 (22,0)×27 (23,0)×30 [bottom].

## Fix
New per-slot `TURRET_PAINT_ROW` = rel+1 (0 = no body row on the aperture), set in
`positionBackgroundTurrets` for rel 0..23; `pulseTurretColour` gates on it and
uses it directly instead of re-deriving from `TURRET_Y`. Colour now follows the
glyphs by construction. Slightly cheaper than before.
Dropout frames: 138 → 4 (all single-frame rel==0 publish-ordering transients).
Selective removal: 2-turret 96 → 2; 3-turret 129 → 3; 4-turret 138 → 4.

## Threshold DISPROVEN
Two cluster turrets already produce 24-frame dropout runs. Count scales the RATE
(96/129/138), not a threshold. No 3+ resource/scratch/loop limit exists — audited
pool size, per-slot arrays, `cramRow` bounds (max observed 14, 0 out-of-range),
shared scratch, charset.

## Rejected hypotheses (do not re-investigate)
`cramRowLo/Hi` overrun; colour-RAM incoherence; charset republished mid-frame
(0 byte changes in 700 frames); mask late (`EDGE_MASK_LATE/FALLBACK` = 0);
aperture shift (58..247 on all 580 frames); screen-matrix placement (rel oracle 0).

## The trap that hid this for two investigations
`TERRAIN_COLOUR_RAM = 8|1 = 9` and pulse phase 0 = `1|8 = 9` are **identical**.
A naive "cell == terrain colour ⇒ missing" oracle false-positives 8 frames in 32
on every turret; excluding phase 0 without further care then HIDES the real
dropouts, because unpainted cells are also 9. Correct method: read the live
`TURRET_PULSE_COLOUR` and only judge frames where it is 10 or 15.

## Also note
- `TURRET_PAINT_ROW` puts the per-slot state block at **exactly 128 bytes**, the
  `.if (TURRET_STATE_END - TURRET_STATE_BEGIN > 128)` limit. Next per-slot array
  will trip it.
- Reverting exactly the three `background_turrets.asm` edits reproduces
  `3f398975ba6a5ba7` — cheap containment proof, worth repeating.
- The rendered-pixel detector was defeated by sprite motion (residual 100–400 px
  baseline). Masking sprite boxes from the object table was too imprecise. If a
  future task needs true pixel capture, disable sprites at source instead.

## Regression
`[19656]` all 7 fixtures; 0 sprite-start misses incl. `--dense`; dense
catchups/replay 1386/100 unchanged; wrap svcFail 3 (pre-existing pointer race);
aperture 58..247 on 130/130. B(b) intact (19 attempts = 11 A + 8 B + 0 refusals,
0 snaps, 0 dups, 2-frame stall). rel==-1/-2 oracle 0.

## Binaries
default `58e9d59131e4791b` (was `3f398975ba6a5ba7`).
