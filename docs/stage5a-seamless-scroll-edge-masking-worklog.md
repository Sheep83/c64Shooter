# Stage 5A — Seamless scroll-edge masking — worklog

**STATUS: COMPLETE — GREEN, candidate ready for manual visual acceptance.**
Full report: `/reports/stage5a-seamless-scroll-edge-masking.md`.

Branch `main`, HEAD `d60828a` ("Promote double-buffered scroller to default"),
unchanged. Working tree has the in-progress candidate, uncommitted:
`M src/main.asm`, `M src/raster_scheduler.asm`. No commit/stage/tag/push done.
Tags untouched (`stable-double-buffered-scroller-v2` -> `479bb32` verified).

## Verified starting state
- Mode C defaults on (`OPT_SECOND_SCREEN`, `OPT_SS_INACTIVE_BUILD`,
  `OPT_SS_FLIP_COARSE`, `OPT_SS_ALLOW_PENDING_LIVE_FLIP`), builder values
  1/180/3 unchanged, accepted hash `80d5b0461c070fe2…` reproduced.
- **Candidate OFF (`//#define SCROLL_EDGE_MASK`) rebuilds `80d5b0461c070fe2…`
  byte-identical** — the change is fully guarded.

## Objective 1 — defect characterised (DONE, measured)
Calibration: PNG `y` -> C64 raster is **raster = y + 16** (proved: the measured
first-terrain raster fits `48+fine` exactly at all 8 phases).

- Terrain field **top edge = raster 48+fine**, **bottom edge = raster 247+fine**.
  Both walk down 1 raster per fine step and **snap back up 7 rasters at each
  coarse 7->0 wrap** — an 8 px sawtooth on BOTH edges at ~3.9 Hz. That moving
  boundary is the visible pop; the body content is temporally clean.
- Top and bottom are the **same** mechanism: the finite 25-row fetch. Matrix row
  0 occupies 48+fine..55+fine, row 24 occupies 240+fine..247+fine.
- Content at any **fixed** raster is exactly continuous, including across the
  coarse step (verified rasters 56/120/200/246/247 = OK; 55 and 248/249 differ
  only because they are the entry/exit lines). **=> masking outside a fixed
  window is sufficient and loses no continuity.** Ideal window: **55..247**.

## Objective 2 — prior work reassessed (DONE)
`/reports/soft-edge-masking-and-astra-handoff-report.md` (AMBER) used an ECM
band with the same geometry (55 / 248) but needed **4 register writes**
($D011+$D016+$D022+$D023) to keep the band grey, applied after a `poll + 50-cycle
pad`, so the switch landed mid-scanline at a load-dependent cycle -> ±1-8 px
per-frame shimmer. Its own recommendation was that a `$D018`-page scroller would
give a clean edge "for free"; Stage 4 delivered that page flip, but the flip
alone does **not** fix the edge — the boundary is a raster-vs-character-row
problem, not a page problem.

Border option (§8C) is **impossible with the current HUD**: RSEL=0's border
would mask exactly <=54 / >=247 for free, but the vertical border FF can only be
cleared at raster 51/55, so keeping the top-border HUD sprites (measured at
rasters 23..43) visible forces the FF clear from the previous frame — both
borders open. Confirmed dead end; a graphics-mode mask is required.

## Candidate implemented (NEW, better than the 4-write ECM)
`#define SCROLL_EDGE_MASK` (default ON) in `src/main.asm`:
- Band = the VIC **invalid text mode (ECM=1 with MCM=1)** -> sequencer outputs
  **black** for display *and* idle state, regardless of charset/colour
  registers. So the mask is **ONE store of a pre-computed $D011** per switch,
  not four writes. No charset mutation, no $D022/$D023 juggling, no
  `setupStarfieldCharset` restore.
- Black is the right colour: the side border ($D020) is already black, the
  top/bottom strips are currently grey (12) — so the surround becomes a
  **uniform black letterbox**.
- `GAMEPLAY_D011_BASE |= $40` so rasterFrameReset/publishRasterPlan install the
  band state every frame; `endGame` clears ECM (shares the existing
  SOFT_EDGE_MASK branch, condition widened).
- Only `$D01E` (sprite/sprite) is used for collision — `$D01F` is never read —
  so the sequencer change cannot affect gameplay.
- `EDGE_MASK_BODY_RASTER = 58` (must clear the HUD handoff; measured
  `rasterDisplayRestored` max **56**, `--stress` max **57**).
  `EDGE_MASK_BAND_RASTER = 248` (raster 248 is never a badline — the badline
  range ends at 247 — and is the first raster that alternates terrain/idle).
- Switches: top at the end of `rasterDisplayHook`; bottom inside
  `borderOpenHook` between its two RSEL dodge writes (`!wait250` is a
  read-modify-write so it preserves ECM).
- `EDGE_MASK_LATE` (word, inside RASTER_STATE so captures dump it) counts frames
  that reached the poll already past the target. Measured **0**.

## Measured results so far
Aperture became **fixed at 58..247** on every frame — no oscillation, no
coarse-step jump (vs 48+fine..247+fine before). **The pop is gone at 7 of 8 fine
phases.**

**Remaining defect: fine == 2.** Raster 58 is a badline exactly when fine == 2
(58 & 7 == 2). Trace of the store instruction (`edgeMaskBodyApplied`) shows:
```
fine=0 58:6/58:12   fine=1 58:6..9    fine=2 58:55 (x8), 58:6/11 (x2)   fine=3 58:6/12
fine=4 58:6/7/12    fine=5 58:6..8    fine=6 58:6/11/12                 fine=7 58:11/12
edgeMaskBandApplied: 248:3..9 on ALL phases  (bottom switch is robust)
```
At fine==2 the badline stall (cycles 12..54) plus sprite DMA (0..10) starves the
poll, so the store lands at cycle 55 — after line 58's g-accesses — and line 58
renders black => aperture 59 on that phase (a 1 px flicker at ~3.9 Hz).
Confirmed visually: frames 20/21 of `build/s5a-idle` show 59..247, all others
58..247.

## Next step (resume here)
A "primed poll" fix was just installed and built but **not yet measured**: the
final poll is now preceded by a poll for `EDGE_MASK_BODY_RASTER - 2`, so the
7-cycle loop is already spinning when the beam crosses into line 58 and its
first read should land in cycles 0..6, ahead of both the sprite-DMA steal and
the badline stall. Candidate build `b025ab2512ec8266…`; capture `build/s5a-t3`
was taken but not analysed.

1. Analyse `build/s5a-t3` with the scratchpad tools (below) — check
   `edgeMaskBodyApplied` at fine==2 and the per-frame aperture.
2. If fine==2 still lands late, fall back to the **phase-conditional** variant:
   when `RASTER_DISPLAY_FINE == (EDGE_MASK_BODY_RASTER & 7)` line 58 is a
   badline but line 57 provably is not, so poll line 57 and use a fixed ~51-cycle
   delay (`ldy #10 / dey / bne`) to land the store in line 57's tail
   (cycles 56..62), which is after line 57's stall and before line 58's fetches.
   Otherwise keep poll-58 + immediate store. Both branches are then
   stall-free by construction.
3. Then run the full regression suite (idle / wave 382 / wrap 12 / --y199 /
   --dense / turret-playtest / --stress), the page-aware pointer oracle,
   `[19656]`, incomplete frames, sprite-start misses, and `EDGE_MASK_LATE == 0`.
4. Write `/reports/stage5a-seamless-scroll-edge-masking.md` and present it.

## Tooling (scratchpad, repo `tools/` untouched)
`/private/tmp/claude-501/-Users-brianmorrice-Dev-C64-ASM-shooter-test/2bada50f-f6bb-4365-b321-e56e1f493553/scratchpad/`
- `s5a_calibrate.py <cap> <frame>` — per-row colour profile / y<->raster calibration
- `s5a_edges.py <cap> <first> <count>` — first/last non-backdrop raster per frame
- `s5a_aperture.py <cap> <first> <count>` — classify each raster MASKED/IDLE/TERRAIN
- `s5a_continuity.py <cap> <first> <count> <rasters...>` — fixed-raster continuity proof
- `vst_edge.py` + `run_capture_edge.sh` — capture tool patched to trace
  `edgeMaskBodyApplied` / `edgeMaskBandApplied`
- `run_capture.sh` — the standard capture wrapper

Note: the two trace labels are currently present in `src/raster_scheduler.asm`;
they emit no bytes but should stay (harmless) or be removed before final review.


---

# COMPLETION (resumed session)

## What finished the job
1. **Primed poll** — the final `cmp RASTER / bcs` loop is now preceded by a poll
   one line earlier, so it is already spinning when the beam crosses into the
   target line and its first read lands in cycles 0..6. Moved the `fine==2` store
   from `58:55` to `58:3..9`, but line 58 still rendered black on that phase:
   on a badline line the effective deadline is earlier than cycle 12.
2. **Badline path** — one compare (`RASTER_DISPLAY_FINE == EDGE_MASK_BODY_RASTER
   & 7`) selects a separate path that polls the PREVIOUS line and pads 51 cycles
   to land the store in that line's tail. Two badlines cannot be adjacent, so
   that line is provably stall-free. Measured `59:54..60:02`, n=40, all in window.
3. **Target raised 58 -> 60** — the badline path must arrive two lines earlier
   than the normal one; measured mask-block entry is 49..56 (authored wave), so
   60 gives the badline path >=1 line and the normal path >=3 lines of margin.
   Added `EDGE_MASK_FALLBACK` so a late badline frame degrades into the in-line
   path rather than storing blind.

## Final measured state (build `d06724c6587e2f81...`)
- Terrain aperture **fixed at 60..247 on 840/840 sampled frames** across all
  seven fixtures (measurement must ignore sprites in the band: require >=90% of
  the row masked, since the mask blacks graphics, not sprites).
- Store timing: body normal path **60:3..9** (n=280), body badline path
  **59:54..60:02** (n=40), band close **248:3..13** (n=320).
- Regression: `[19656]` everywhere, 0 incomplete, 0 sprite-start misses except
  `--dense` 13 (better than the accepted 16), wrap's 1 service failure is the
  known Stage-4G HUD-oracle caveat (frame 82, slots 4-6, values 188/189/190).
  `EDGE_MASK_LATE` 0 everywhere except `--stress` 2/500; `EDGE_MASK_FALLBACK` 0
  everywhere.
- Mask OFF rebuilds `80d5b0461c070fe2...` byte-identically.

## Gotchas for a future session
- The aperture analyser MUST tolerate sprites in the letterbox, otherwise wrap /
  stress look like the aperture is unstable. Use `s5a_aperture2.py`.
- A trace label placed AFTER the store times the following instruction, which a
  badline can stall; put the label ON the store.
- KickAssembler multi-labels: a reference to a label defined earlier needs `-`,
  not `+` (`bcc !edgeBodyLate-`).

## Open decisions for the user (post visual inspection)
- Black vs grey surround (the band is black; side borders already are).
- Sprites remain visible in the letterbox — keep or hard-clip.
- `EDGE_MASK_BODY_RASTER` 60 -> 62 would remove the 0.4% `--stress` residual at a
  cost of two aperture lines.
- Optionally drop the four zero-byte trace labels before commit.
