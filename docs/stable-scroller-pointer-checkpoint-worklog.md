# Stable scroller / sprite pointer checkpoint — worklog

**STATUS: COMMITTED, TAGGED, PUSHED.**
Full report: `/reports/stable-scroller-pointer-checkpoint.md`.

- base `d60828a` -> commit `c349fe2` "Stabilize scrolling and sprite pointer publication"
- annotated tag `stable-scroller-and-sprite-pointers` (object `c9794f0`) -> `c349fe2`
- `main` and the tag pushed to `origin` (SSH); no force-push, no history rewrite.

## What went in
Production: `src/main.asm`, `src/raster_scheduler.asm`, `src/background_turrets.asm`
(Stage 5 scheduled edge mask + display-state containment; Phase B(b) page-aware
legacy coarse fallback; turret `rel == -1/-2` reconciliation; `TURRET_PAINT_ROW`
colour presentation; sprite-pointer publication repair; segment relocations
`SS_STAGE4_BASE_ADDR = $9980`, `LEGACY_PAGEB_SEGMENT = $8640`,
`ENGINE_LOOKUP_SEGMENT = $1f20`, each with `.error` guards).
Tooling: `tools/vice_scroll_test.py --passive` (default behaviour unchanged).
Docs: 11 reports + 10 worklogs, matching the repo's existing convention.

## What stayed out
Everything under `build/`, all `.prg`/`.vs`/`.sym`/`.log` artefacts, per-frame
capture dumps, monitor traces and the session scratchpad. All already covered by
`.gitignore`; nothing was deleted and `git add -A` was never used.

## Final regression (against the exact committed tree)
All 7 fixtures `[19656]`, 0 incomplete, **0 service failures**, 0 pointer failures,
0 sprite-start misses (`--dense` included), dense catchups/replay 1386/100.
B(b): 13 attempts = 8 A + 5 B + 0 refusals, 0 snaps, 0 dups, 2-frame stall.
rel==-1/-2 oracle 0. Aperture 58..247 on 130/130. Title ECM=0 + starfield.
Builds: mask-ON `f1d08a0f5d2337ee`, mask-OFF `66d2fa9295e858ac`,
Mode A `2591ca3da434cf1a`.
The wrap fixture's long-standing 3 service failures were the sprite-pointer race
and are now gone.

## Accepted, NOT fixed
Authored four-turret cluster (345/337/329/321) visual flicker — treated as a
level-design constraint. Screen RAM, colour RAM, charset, mask timing and aperture
were all independently exonerated. Best remaining hypothesis is presentational:
`turretPulseTable` phase 0 (`1|8 = 9`) equals `TERRAIN_COLOUR_RAM`, and all
turrets share one global pulse index.

## Manual
User played the latest build and reported "nothing detected" for player/enemy
sprite flicker. Recorded as corroboration; machine pointer correctness is the proof.

## Note for next session
Checkpoint is ready for the HUD feature phase. Use `--passive` for any
scrolling/background/turret presentation capture; the default still holds FIRE.
