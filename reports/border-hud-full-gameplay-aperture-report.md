# Border-HUD Experiment — Reconcile the Full Gameplay Aperture

**19656 / c64Shooter — PAL C64 vertical shooter.** Branch `experimental-border-hud`.
No commit, no push. VICE (`x64sc`) launched head-less / background
(`-remotemonitor`, `Popen`, `DEVNULL`), never foregrounded, no `open -a`.

Legend: **[OBS]** source · **[MEAS]** measured this session · **[A/B]** measured
against a comparison build.

---

# TL;DR / verdict

| | |
| --- | --- |
| **Top sprite dead zone** (rasters ~55..71: terrain visible, sprites blanked) | **FIXED — GREEN.** It was a stale legacy of the removed fixed top HUD: `GAMEPLAY_SPRITE_MIN_Y = 71` drove the sprite top-clip, the player/enemy/hittable/fire clamps and the collision-confirm gate. Rebased to `51 + 4*(1 - GAMEPLAY_RSEL)` = **55** (the RSEL=0 aperture top). Sprites, collisions, player movement now reach the top of the visible terrain. `[19656]` exact, 0 new service failures / sprite-start misses. |
| **Bottom real-estate** | **PROVEN MAXIMUM — AMBER.** The RSEL=0 crop at raster 246 is the largest clean aperture this single-matrix 25-row-fetch scroller can present. Extending it (globally RSEL=1, or an asymmetric RSEL 0→1→0 dodge — both measured) re-exposes the overflow row-24's own uncroppable bottom edge and reintroduces a per-frame temporal discontinuity at raster 247+. |
| Overflow-row scroll fix | **NOT REGRESSED** — every temporal edge test still `body 0 / lastrow 0 / coarse_edge_median_jump [0,1]`. |
| Exact PAL cadence `[19656]` | preserved everywhere (trusted oracle). |

**Overall: GREEN on the reported gameplay regression (top dead zone); AMBER on
"make the screen bigger" (246 is the honest clean maximum).** The build is ready
for a top-border static sprite-HUD proof — with one geometry caveat (Q25).

---

# 1. Q1-Q2 — start state and the overflow-row changes present

| | |
| --- | --- |
| Branch | `experimental-border-hud` |
| HEAD | `d547c80` — *"Establish RSEL1 border HUD experimental baseline"* |
| Working tree at start | the **uncommitted overflow-row experiment** (`M src/main.asm`, `M src/raster_scheduler.asm`, `M tools/check_scroll_edges_rsel1.py`, `M tools/phase15_geometry_test.py`, `?? docs/rsel1-scroll-overflow-worklog.md`, `?? reports/rsel1-scroll-overflow-rows-experiment-report.md`) |
| Final build (this task) | `sha256(prg) = b67c89917025fe94…`, `sha256(d64) = b22398fbcb8f2bb7…` |

**Overflow-row changes present** (from the previous task, confirmed against source):
matrix rows 0 and 24 carry the incoming / outgoing terrain overflow
(`W(r) = SCROLL_ROW + r − 1`, r = 0..24); `shiftBackgroundUpper` `12..1`,
`shiftBackgroundLower` `24..14`, `prepareBackgroundCoarse` renders `BG_DEST_ROW = 0`,
`wrapBgLogicalRow` folds the `SCROLL_ROW = 0` underflow, `initBackground` renders
25 rows, `initFixedHud` emptied; `GAMEPLAY_RSEL = 0` (RSEL=0 24-row aperture,
raster 55..246). Both scroll edges temporally clean.

---

# 2. Q3-Q6 — the top sprite dead zone

## Q3 — the exact dead zone

**Rasters ~55..71.** With `GAMEPLAY_RSEL = 0` the visible terrain runs raster
55..246, but a gameplay sprite whose origin Y is 51..70 is placed at its true
`SPR_Y` with its VIC slot enabled **while its bitmap's top `71 − Y` scanlines are
forcibly blanked** — so it only becomes visible from raster ~71. Sprites with
Y < 51 get no VIC slot at all. Collisions are not confirmed for Y < 71 either.
Net: a ~16-scanline band of visible terrain where sprites do not draw and cannot
collide. Matches the manual playtest.

## Q4 — the source-level gates that caused it (Part A audit, full list)

All are in `src/main.asm`. Every top gate keys off **one** constant,
`GAMEPLAY_SPRITE_MIN_Y` (was `71`).

| Subsystem | Current Y rule (before) | Historical reason | Still valid? | New rule |
| --- | --- | --- | --- | --- |
| `GAMEPLAY_SPRITE_MIN_Y` const | `71` | old fixed HUD row 0 (r55-62) + BMM+ECM separator (r63-70); "no sprite DMA in the HUD transition" | **NO** — HUD + separator removed in Phase 1.5; `rasterDisplayHook` is a no-op, no mid-frame `$D011` writes | `51 + 4*(1 − GAMEPLAY_RSEL)` → **55** |
| `GAMEPLAY_SPRITE_CLIP_MIN_Y` = `MIN_Y − 20` | `51` (drop floor) | coupled to MIN_Y (clip pool blanks ≤ 20 rows) | follows | **35** |
| `buildSortedObjectList` (`cmp #CLIP_MIN` / `cmp #END_Y`, ~2637) | keep `51 ≤ Y < 246`, else no VIC slot | HUD | follows the consts | `35 ≤ Y < 246` |
| `snapshotSpritePointer` (`cmp #MIN_Y`, ~2776) | `Y < 71` → top-clipped bitmap | HUD | belt-and-braces now — the RSEL=0 border FF also masks the sprite top above r55 | follows MIN_Y |
| `buildClippedInitialSprite` (`d = 71 − Y`, ~2779/2788) | blank top `71 − Y` rows | HUD | follows | `d = MIN_Y − Y` |
| player move-**up** clamp (`cmp #GAMEPLAY_SPRITE_MIN_Y`, ~1681) | player Y ≥ 71 | "same viewport as every rendered object" | follows | player Y ≥ 55 |
| hitscan target eligibility (`cmp #MIN_Y`, ~1806) | enemy Y ≥ 71 hittable | "off-screen ingress not a target" | follows — top-band enemies are visible now | Y ≥ 55 |
| enemy-fire eligibility (`cmp #MIN_Y` … `cmp #190`, ~2156) | shooter Y in `71..190` | HUD floor + readability ceiling | floor follows; `190` ceiling unchanged | `55..190` |
| `checkCapturedPlayerCollision` (`cmp #MIN_Y` / `cmp #END_Y`, ~3563) | confirm only `71 ≤ Y < 246` | "culled ingress cannot cause an invisible software collision" | follows — a top-band overlap is now a fair, visible hit | `55 ≤ Y < 246` |
| `buildBatchSpriteSchedule` (`cmp #12`, ~3004) | batched obj needs `Y ≥ 12` (compute the `Y−12` IRQ compare) | **real** "compare raster can't be negative" limit — **not** a HUD gate | **YES** | unchanged; irrelevant (see Q9) |
| player move-**down** clamp (`cmp #230`, ~1700) | player Y ≤ 230 | bottom margin (independent magic number) | see Part D | **unchanged** (documented) |
| `PLAYER_START_Y = 220`, respawn | fine | | yes | unchanged |
| `GAMEPLAY_SPRITE_END_Y = 246` | enemy cull / collision ceiling | RSEL=0 aperture bottom | **YES** — still the clean crop (Part D) | unchanged |
| Tests encoding the old boundary | `tools/sprite_y_sweep.py` prints a `collision_eligible` column from a hard-coded `71` (cosmetic; the engine gate moved) | — | — | note only |

## Q5 — every gameplay Y-boundary found

See the Q4 table. Independent constants after this task:
`GAMEPLAY_SPRITE_MIN_Y` (55, derived), `GAMEPLAY_SPRITE_CLIP_MIN_Y` (35,
derived), `GAMEPLAY_SPRITE_END_Y` (246), player-down `#230`, enemy-fire ceiling
`#190`, `PLAYER_START_Y` (220), `buildBatchSpriteSchedule`'s `#12` (structural).

## Q6 — which were historical HUD assumptions

`GAMEPLAY_SPRITE_MIN_Y = 71` and everything derived from it — the sprite
top-clip, the player-up clamp, the hittable floor, the enemy-fire floor, and the
collision-confirm floor. All existed to keep gameplay sprites clear of the
raster 55-70 fixed HUD row + invalid-mode separator. Those are gone. `#230`,
`#190`, `PLAYER_START_Y`, `GAMEPLAY_SPRITE_END_Y` are bottom-side / policy and
are **not** HUD artefacts.

## Q7 — what changed

`src/main.asm`, two lines + comments:

```
.const GAMEPLAY_SPRITE_MIN_Y      = 51 + 4 * (1 - GAMEPLAY_RSEL)   // 55 (RSEL=0) / 51 (RSEL=1)   (was 71)
.const GAMEPLAY_SPRITE_CLIP_MIN_Y = GAMEPLAY_SPRITE_MIN_Y - 20     // 35 (RSEL=0)                  (was 51)
```

Stale comments on `GAMEPLAY_SPRITE_MIN_Y`, `snapshotSpritePointer` and
`buildClippedInitialSprite` updated ("raster 72 / HUD transition" → "aperture
top"). **No other engine code** — every gate already referenced the constant.
`src/raster_scheduler.asm` gained only a guarded `GAMEPLAY_BOTTOM_EXTEND` branch
in `borderOpenHook` (Part D investigation, ships as 0).

---

# 3. Q8-Q11 — the new sprite/gameplay top

## Q8 — first legal / visible sprite Y

**55** (= the RSEL=0 aperture top, and `= GAMEPLAY_SPRITE_MIN_Y`). A sprite with
origin Y ≥ 55 renders its full bitmap; its topmost scanline is the first visible
terrain scanline. Y 35..54 are kept and top-clipped (and are border-masked by
the RSEL=0 vertical-border FF regardless). Y < 35 are dropped.

**[MEAS]** `tools/sprite_y_sweep.py` (new): baseline (MIN_Y=71) — objects Y 51..70
get a slot + `$D015` bit + true `SPR_Y` but **zero visible pixels** (bitmap
top-blanked). After (MIN_Y=55) — objects Y ≥ 55 render fully.
`scratchpad/topzone_beforeafter.png`: the player ship forced to Y=60 shows only
its wings (before) vs the whole ship from its true top (after).
`build/p15-wave5` real combat, frame 211: an authored enemy at **Y = 51** renders
as a clean recognisable sprite at the very top of the terrain
(`scratchpad/wave5_top.png`).

## Q9 — can the mux safely service sprites there?

**Yes, by construction.** `sortObjectsByY` orders ascending; `buildInitialSpriteSnapshot`
takes the first ≤ 8 = the **lowest-Y (topmost)** objects → they go in the
**initial snapshot**, which `renderSprites` writes at frame top (~raster 10),
with **no raster scheduling and no batch**. `buildBatchSpriteSchedule` only ever
handles objects 9-16 = the **higher-Y (lower-on-screen)** ones. So the topmost
sprite is never scheduled — lowering `GAMEPLAY_SPRITE_MIN_Y` adds **zero** mux
scheduling pressure.

**[MEAS]** `--case highy` (15 enemies packed into Y 56..84 + player):
`frame_cycle_deltas [19656]`, `sprite_start_miss_count 0`, `max_objects 16`.
Regression battery (trusted `vice_scroll_test.py --physical --trace` +
`check_raster_capture.py`): ordinary / dense(16) / stage-wrap all `[19656]`,
**0 service failures, 0 sprite-start misses**.

## Q10 — earliest measured sprite batch raster

**Raster 127** (`rasterAssignmentApplied`, dense load — batched sprites are the
lower-on-screen objects). No batch fires above raster 127; the topmost sprites
are the unscheduled initial-8. `bgLowerReady` (coarse lower phase) completes by
raster ~31, far above any top-band sprite DMA (~raster 54).

## Q11 — are collision / player / enemy / bullet bounds coherent with the new top?

Yes — all follow `GAMEPLAY_SPRITE_MIN_Y` in lock-step:

| bound | before | after |
| --- | --- | --- |
| player movement top | Y ≥ 71 | **Y ≥ 55** |
| enemy hittable (hitscan) | Y ≥ 71 | **Y ≥ 55** |
| enemy-fire eligible | Y ∈ 71..190 | **Y ∈ 55..190** |
| software collision confirm | Y ∈ 71..246 | **Y ∈ 55..246** |
| render cull / VIC-slot | Y ∈ 51..246 | **Y ∈ 35..246** |
| enemy bullets / explosions | share `OBJECT_Y`, same cull at 246; no independent top gate | unchanged, follow the cull |
| player death / respawn | `PLAYER_START_Y = 220`; state machine keeps `OBJECT_Y`, re-clamps via the move clamps | now re-clamps to Y ≥ 55 |

A collision in the (previously invisible, now visible) raster 55-70 band is now a
fair, on-screen hit rather than a suppressed "invisible" one.

---

# 4. Q12-Q17 — the bottom real-estate loss (Part D)

## Q12 — why did the build appear to lose bottom real estate?

Three contributors, in order of size:

1. **The RSEL=0 crop is a hard raster-246 border.** The overflow-row fix made
   matrix row 24 an *outgoing overflow row*; RSEL=0's vertical-border FF sets at
   raster 247, so everything below 246 is solid `$D020` black border. The full
   RSEL=1 aperture would reach raster 250 (+4 px) but the previous task proved
   that re-exposes row 24's own bottom edge as a ~4 px pop.
2. **The player-down clamp `#230`.** A player sprite at Y=230 has its body on
   rasters 230-250 → its **bottom 4 px are inside the r246 crop**. The player
   cannot fly into the lowest ~16 px of the visible field the way enemies (culled
   at Y=246) can; it "hits a wall" ~16 px above the visible bottom.
3. **Cosmetic:** the crop is a hard black line (`$D020` = 0), which reads as
   "screen ends here" more starkly than a border that matched the terrain
   backdrop.

## Q13-Q14 — display geometries tested, with exact D011 / RSEL timing

### Candidate 0 — shipped: `GAMEPLAY_RSEL = 0`

```
line 1  (rasterFrameReset)      $D011 = RASTER_DISPLAY_FINE | $10   ; DEN=1, RSEL=0, YSCROL=fine
line 17 (publishRasterPlan)     $D011 = same
borderOpenHook (r250)          $D011 &= $F7                        ; no-op (RSEL already 0)
```
Vertical-border FF: **reset** at raster 55 cycle 63 (RSEL=0, DEN=1), **set** at
raster 247 cycle 63 (RSEL=0). Aperture **55..246**. Overflow row 0's top edge
(r ~48-54) and row 24's bottom edge (r ~247-254) are **both cropped by the FF**
→ both visible edges temporally clean.

### Candidate 1 — global `GAMEPLAY_RSEL = 1` (measured, previous task)

`$D011` base `$18`; `borderOpenHook` RSEL 1→0 at raster 250 (before the raster-251
set). FF never set → top and bottom both open. Aperture 51..250 (**+8 px**), but
the overflow rows' own outer edges are **not** cropped → **~4 px residual pop at
rasters 52-55 and 247-250** on the 7→0 coarse step. Rejected there.

### Candidate 2 — asymmetric `GAMEPLAY_BOTTOM_EXTEND = 1` (measured this task)

`GAMEPLAY_RSEL = 0` for the frame, `borderOpenHook` does:
```
poll to raster 242 ; $D011 |= $08   ; RSEL 0 -> 1  (RSEL=0 set-@247 compare now misses)
poll to raster 252 ; $D011 &= $F7   ; RSEL 1 -> 0  (AFTER the RSEL=1 set-@251 -> FF IS set at 251)
```
FF: reset @ raster 55 (next frame, still RSEL=0), **set @ raster 251** (RSEL=1).
Aperture **55..250** — top crop unchanged at 55, **+4 px at the bottom**.
**[MEAS]** temporal oracle at aperture 55..250: `body 0`, but the newly-exposed
band shows **`lastrow` diffs at raster 247 on EVERY fine step** (≈ 4160 px/step,
not only 7→0). The +4 px are **not** temporally clean — raster 247+ is exactly
where the overflow row-24's own uncroppable bottom edge lives, and it does not
scroll-match frame to frame.

## Q15-Q17 — can the bottom aperture be enlarged without exposing the overflow discontinuity?

**No.** The vertical-border flip-flop is a **single** FF: opening the bottom past
raster 246 (Candidate 1) also opens the top; the asymmetric dodge (Candidate 2)
keeps the top crop but the exposed bottom band is still row 24's discontinuous
outer edge. There is no 26th matrix row to feed row 24 (RSEL=1 badlines stop at
raster 247; RSEL=0 fetches the same 25 rows). **The RSEL=0 crop at raster 246 is
the clean maximum for this single-matrix beam-raced 25-row scroller.** This
re-confirms, by direct measurement of two candidates, the previous task's
finding.

**New clean visible raster range: unchanged — 55..246 (192 px).** Shipped
`GAMEPLAY_BOTTOM_EXTEND = 0`.

**Bounded improvements that do NOT touch the aperture** (offered, not applied
without direction):
- Set `$D020 = TERRAIN_BACKGROUND_COLOUR` in `init` so the crop border blends
  with the terrain backdrop instead of a hard black line — removes the "screen
  ends here" read for zero gameplay/timing cost.
- Relax the player-down clamp from `#230` toward `#236` (ship centre at the crop
  edge — a standard bottom-hug) or tie it to `GAMEPLAY_SPRITE_END_Y`. Gains the
  player ~6 px of usable field; the ship's lower rows clip like enemies already
  do. Left as-is here because it is a feel decision, not a geometry bug.

---

# 5. Q18-Q22 — no regressions

## Q18 — repeated 7→0 coarse transitions still temporally clean

**Yes.** `tools/check_scroll_edges_rsel1.py` (RSEL=0 aperture, turret columns
excluded), shipped build:

| workload | coarse steps | body diffs | edge diffs | `coarse_edge_median_jump` |
| --- | ---: | ---: | ---: | --- |
| ordinary (canonical, 240f) | 13 | **0** | **0** | `[0, 1]` |
| wave5 (≤5-enemy authored) | 13 | **0** | **0** | `[0, 1]` |
| contrast (`$D021` = 7, yellow) | 11 | **0** | **0** | `[0, 1]` |
| divider-1-like | **22** | **0** | **0** | `[0, 1]` |
| stage wrap (`SCROLL_ROW` 0→420, 320f) | 19 | **0** | **0** | `[0, 1]` |

The `GAMEPLAY_SPRITE_MIN_Y` change is orthogonal to the scroller and does not
touch it.

## Q19 — colour continuity

**Clean.** Colour RAM is the single stage-global `TERRAIN_COLOUR_RAM` for every
terrain cell including matrix rows 0 and 24 (**[MEAS]** runtime dump: rows 0 / 1 /
12 / 24 colour RAM all `$F9`). No colour row is scrolled; no 8-px colour flash.
Unchanged from the overflow-row task.

## Q20 — `[19656]` exact

**Yes.** Trusted `vice_scroll_test.py --physical --trace` +
`check_raster_capture.py`, shipped build:

| run | frames | `frame_cycle_deltas` |
| --- | ---: | --- |
| ordinary | 240 | **`[19656]`** |
| dense (16) | 200 | **`[19656]`** |
| stage wrap | 320 | **`[19656]`** |

## Q21 — service failures / sprite-start misses zero

**Yes** — 0 / 0 on all three trusted runs. `catchups 1393 / replay 99` on the
`--dense` synthetic stress are pre-existing (**[A/B]** identical on the baseline
`d547c80`), absorbed by the scheduler, cadence still exact. (`tools/phase15_geometry_test.py`'s
own `check_raster_capture` output remains an unreliable trace-parse artifact —
it reports spurious `service_failure` on the baseline too — so only the
`vice_scroll_test.py` pairing above is trusted for this oracle.)

## Q22 — supported wave5 stable

**Yes.** `--case wave5` (RAM-only `waveTrigCount ≤ 5` fixture, canonical Level-1
assets untouched, `SCROLL_ROW` seeded so authored waves fire): scroll-edge
oracle `body 0 / edge 0`, 13 coarse steps, all `[0, 1]`; cadence `[19656]`; and
`wave5_top.png` shows an authored enemy rendering cleanly at Y = 51 at the
aperture top. Known 6-enemy overload flicker is a separate, pre-existing mux-load
constraint and not a result here.

---

# 6. Q23-Q24 — the final coherent aperture

## Q23 — the final terrain / sprite / collision gameplay aperture

```
terrain visible raster range        : 55 .. 246        (RSEL=0 border FF; hard crop both ends)
terrain clean / useful raster range : 55 .. 246        (== visible; overflow rows 0/24 keep it
                                                         temporally continuous, their own outer
                                                         edges cropped by the FF)
topmost legal gameplay sprite origin Y : 55             (= GAMEPLAY_SPRITE_MIN_Y = aperture top)
lowest legal gameplay sprite origin Y  : 245            (GAMEPLAY_SPRITE_END_Y = 246, exclusive)
sprite pixel-visible raster range      : 55 .. 246      (a sprite's rows outside this are border-masked;
                                                         Y 35..54 additionally clip-blanked)
collision-confirmation Y range         : 55 .. 245      (checkCapturedPlayerCollision)
player movement Y range                : 55 .. 230      (up = GAMEPLAY_SPRITE_MIN_Y; down = #230,
                                                         ship bottom then clips 4 px into the crop)
enemy spawn/despawn Y range            : spawn per wave;  render/cull at Y ∈ 35 .. 246;
                                                         enemy-fire only in Y ∈ 55 .. 190
```

Related on purpose: the sprite/collision/player-up top (55) **equals** the
terrain aperture top. The one deliberate mismatch is player-down (230) vs
terrain/enemy bottom (246) — a 16-px bottom margin so the player ship stays
mostly on-screen; documented, not a bug. There is **no** remaining "terrain
exists here but sprites are not allowed here" band.

## Q24 — editor viewport change eventually required

`tools/level_editor/engine_data.py : VIEWPORT_ROWS` currently models a 23-row
aperture. The engine now presents a continuous **24-row-equivalent** field
(matrix row 0 sliver + rows 1..23 + row 24 sliver, RSEL=0 crop). A follow-up
editor pass should set `VIEWPORT_ROWS = 24` (display constant only — the
bottom-origin anchor `SCROLL_ROW = STAGE_LOGICAL_ROWS − VIEWPORT_ROWS` is already
parameterised; do **not** change it here, it would move authored bottom-origin).
Cosmetic overlay change, no world-coordinate impact. Not done in this task.

## Q25 — ready for the top-border static sprite-HUD proof?

**Yes, with one geometry caveat to carry into that task.** The gameplay aperture
is now coherent and the top dead zone is gone. But opening the **top** border for
a HUD canvas needs the Slap-Fight dodge (RSEL 0→1 before the raster-247 bottom
SET, RSEL 1→0 before raster 251), which — being single-FF — also opens the
**bottom** border and re-widens the bottom aperture toward the Candidate-1
residual (§Q13). So the top-HUD proof must:
1. re-run **this report's temporal edge battery** with the border open, and
2. either accept a ~4 px bottom overflow residual while the border is open, add a
   narrow beam-raced bottom re-close, or hold the HUD canvas only in a phase
   where the bottom is still cropped.

Prove the sprite canvas renders cleanly at Y ≈ `$0c` (raster ~12-33, inside the
normal sprite window) first; defer `HUD_SAFE_RASTER`, dynamic content and the
gameplay→HUD slot hand-off.

---

# 7. Before / after gameplay aperture diagram

```
BEFORE (this task's start)                     AFTER
------------------------------------------     ------------------------------------------
r16-54  RSEL=0 top border ($D020 black)        r16-54  RSEL=0 top border ($D020 black)      (unchanged)
r55-70  TERRAIN visible                        r55-70  TERRAIN visible
        · sprites BLANKED (top-clip to r71)            · sprites RENDER at true Y (>=55)
        · player cannot fly here (>=71)                · player may fly here (>=55)
        · enemies not hittable / no collision          · enemies hittable, collisions confirmed
r71-246 TERRAIN + full sprites + collision     r55-246 TERRAIN + full sprites + collision
r230    player-down clamp                      r230    player-down clamp                    (unchanged; Part D)
r246    RSEL=0 bottom crop (hard black)        r246    RSEL=0 bottom crop (hard black)      (proven max)
r247+   border ($D020 black)                   r247+   border  (+4 px reachable only with a
                                                        re-exposed overflow-edge pop -> not taken)

top sprite dead zone: rasters ~55..71  ---->   ELIMINATED
clean visible aperture: 192 px (r55..246) ->   192 px (r55..246)  -- unchanged, proven maximum
```

## Candidate border/RSEL raster diagrams (Part D)

```
Candidate 0  RSEL=0 (SHIPPED)         Candidate 1  RSEL=1 global         Candidate 2  asymmetric (BOTTOM_EXTEND)
FF reset @ r55  (RSEL=0, DEN=1)       FF reset @ r51  (RSEL=1)           FF reset @ r55  (RSEL=0 next frame)
FF set   @ r247 (RSEL=0)              FF never set (dodge r250)          FF set   @ r251 (RSEL=1; RSEL 0->1 @r242,
aperture 55..246  -> BOTH edges      aperture 51..250  -> +8px but        RSEL 1->0 @r252)
       clean (overflow edges              overflow edges NOT cropped      aperture 55..250  -> top clean, but
       cropped by the FF)                 -> ~4px pop r52-55 & r247-250    r247+ not temporally clean (MEAS)
```

---

# 8. Y-boundary audit table (compact)

| # | subsystem | before | after | class |
| --- | --- | --- | --- | --- |
| 1 | `GAMEPLAY_SPRITE_MIN_Y` | 71 | **55** (derived) | HUD legacy — FIXED |
| 2 | `GAMEPLAY_SPRITE_CLIP_MIN_Y` | 51 | **35** (derived) | HUD legacy — FIXED |
| 3 | render cull / VIC slot | 51..246 | 35..246 | follows 1,2 |
| 4 | sprite top-clip / clip-pool depth | `71−Y` | `MIN_Y−Y` | follows 1 |
| 5 | player move up | ≥71 | ≥55 | follows 1 |
| 6 | hitscan hittable | ≥71 | ≥55 | follows 1 |
| 7 | enemy-fire eligible | 71..190 | 55..190 | follows 1 (190 kept) |
| 8 | collision confirm | 71..246 | 55..246 | follows 1 |
| 9 | batch schedule `Y≥12` | 12 | 12 | structural — kept |
| 10 | player move down | ≤230 | ≤230 | policy — kept (Part D) |
| 11 | enemy cull ceiling `END_Y` | 246 | 246 | proven clean crop — kept |
| 12 | `PLAYER_START_Y` | 220 | 220 | kept |

---

# 9. Exact test commands / harnesses

```
# build (GAMEPLAY_RSEL=0, GAMEPLAY_BOTTOM_EXTEND=0 in src/main.asm)
java -jar …/KickAss.jar src/main.asm -odir build -o build/shooter.prg -vicesymbols
c1541 -format "19656,01" d64 build/shooter.d64 ; c1541 build/shooter.d64 -write build/shooter.prg 19656

# Part B — sprite-Y sweep (self-launching)
python3 tools/sprite_y_sweep.py --lo 40 --hi 92            # initial-8 path
python3 tools/sprite_y_sweep.py --lo 40 --hi 84 --batched  # + 8 fillers

# top-band mux stress
python3 tools/phase15_geometry_test.py --case highy --frames 180   # 15 enemies Y 56..84

# trusted cadence / scheduler (background x64sc on -remotemonitor :6510)
python3 tools/vice_scroll_test.py --physical --trace --frames 240 --out build/apF-ord
python3 tools/vice_scroll_test.py --physical --trace --dense --frames 200 --out build/apF-dense
python3 tools/vice_scroll_test.py --physical --trace --seed-scroll 12 --frames 320 --out build/apF-wrap
python3 tools/check_raster_capture.py build/apF-<run>

# temporal scroll-edge (RSEL=0, turret cols excluded)
python3 tools/check_scroll_edges_rsel1.py build/<capture> --aperture 55 246 --body-top 56 --last-row-top 246

# Part D candidate (revert after): src/main.asm  GAMEPLAY_BOTTOM_EXTEND = 1, rebuild,
python3 tools/check_scroll_edges_rsel1.py build/<capture> --aperture 55 250 --body-top 56 --last-row-top 247
```

New / changed this task:
- `src/main.asm` — `GAMEPLAY_SPRITE_MIN_Y` rebased (+ `GAMEPLAY_BOTTOM_EXTEND` toggle, ships 0); stale comments.
- `src/raster_scheduler.asm` — guarded `GAMEPLAY_BOTTOM_EXTEND` branch in `borderOpenHook`.
- `tools/sprite_y_sweep.py` — **new** Part-B fixture.
- `tools/phase15_geometry_test.py` — `--case highy` (15 enemies in the top band).
- `tools/check_scroll_edges_rsel1.py` — `--aperture` override already added last task; used here at 55 246 / 55 250.
- `docs/full-gameplay-aperture-worklog.md` — worklog.

Evidence: `scratchpad/topzone_beforeafter.png` (player Y=60, MIN_Y 71 vs 55),
`scratchpad/wave5_top.png` (authored enemy at Y=51), `build/sprite-y-sweep/sweep.json`.

---

# 10. Manual-test build

`build/shooter.d64` / `build/shooter.prg` (`sha256(prg) = b67c89917025fe94…`),
Level 1 straight into PLAYING. No diagnostic build mode was added — the fix is a
constant change and the effect (sprites and the player reaching the top of the
visible terrain) is directly playable. To make the aperture obvious for a
playtest: fly the player straight up (it now reaches raster 55, the top of the
terrain), and note enemies now spawn/fight fully-visible in the previously-blank
top band. To see the Part-D candidate: set `GAMEPLAY_BOTTOM_EXTEND = 1` in
`src/main.asm`, rebuild — the bottom gains 4 px but pulses at the coarse step.

---

# 11. Decision & caveats

**GREEN** on the reported gameplay regression: the top sprite dead zone is
eliminated at the source, sprite/terrain/collision/player geometry now agree at
the top (raster 55), no timing / mux regression, overflow-row scroll fix intact,
`[19656]` exact.

**AMBER** on "recover bottom real estate": raster 246 is the proven clean
maximum; two extension candidates were measured and both reintroduce a temporal
discontinuity at raster 247+.

Caveats:
1. `GAMEPLAY_BOTTOM_EXTEND = 1` is an investigation toggle, not shipped.
2. `tools/phase15_geometry_test.py`'s `check_raster_capture` numbers are an
   unreliable trace-parse artifact — use `vice_scroll_test.py`.
3. Player death/respawn not re-run (`DEBUG_PLAYER_INVULNERABLE = 1`); the coarse
   routines and the Y clamps are inert to `PLAYER_STATE` beyond the clamp values.
4. NTSC untested — PAL authoritative.
5. Editor overlay still shows 23 rows (Q24) — cosmetic, deferred.
6. `#230` player-down and `#190` enemy-fire-ceiling are independent magic numbers
   left as-is; both bottom-side, neither a HUD artefact.

## Housekeeping

**No commit, no push.** `HEAD` still `d547c80`. Working tree: `M src/main.asm`,
`M src/raster_scheduler.asm`, `M tools/check_scroll_edges_rsel1.py`,
`M tools/phase15_geometry_test.py`; `?? tools/sprite_y_sweep.py`,
`?? docs/full-gameplay-aperture-worklog.md`, `?? reports/border-hud-full-gameplay-aperture-report.md`
(plus the previous task's uncommitted `docs/rsel1-scroll-overflow-worklog.md` and
`reports/rsel1-scroll-overflow-rows-experiment-report.md`). `build/` is gitignored.
VICE launched head-less/background, killed on exit, never foregrounded, no
`open -a`. Canonical Level-1 assets not modified.
