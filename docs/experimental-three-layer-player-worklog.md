# Experimental three-layer hires player — feasibility worklog

## Branch
`experimental-three-layer-player`, created from `main` @ `e94ccf5`
("High Score screen corruption fixed"), working tree CLEAN, build reproduces
`809b5edc2eb004f55bf027b2d4bdd92df7ba89bebbe0be2d33fdb9b3496062b7`.

## Phase A audit — how one logical object becomes a render assignment

1. **Pipeline.** `buildSortedObjectList` (active && Y in
   [GAMEPLAY_SPRITE_CLIP_MIN_Y=35, GAMEPLAY_SPRITE_END_Y=246)) ->
   `sortObjectsByY` (insertion sort, ascending Y) -> `buildInitialSpriteSnapshot`
   (first `min(SORTED_COUNT,8)` sorted objects; **sorted index == hardware slot**)
   -> `buildBatchSpriteSchedule` (sorted objects 9+ into recycled slots) ->
   `swapRenderPlans` -> `renderSprites` (main thread) + `applyLiveRasterBatch` (IRQ).
   Strictly **1 logical object -> 1 render assignment** everywhere.

2. **Player slot-0 special cases** (the complete list):
   - `renderSprites:4101` `lda INITIAL_OBJECT,y / bne / sta PLAYER_HW_MASK`
   - `beginRasterPlanMasks` + `extendRasterPlanMasks` -> `SCHED_PLAYER_MASK`
   - `hudBorderHandoff:8381` (the ONLY place that ORs the mask today)
   - `capturePlayerCollision` scans logical objects 1..15 (skips 0)
   - `startGame` pins object 0 = player. Sorting/allocation treat it as ordinary.

3. **Slot allocation / recycling.** `SLOT_FREE_RASTER[s] = OBJECT_Y + 24`
   (DMA-complete estimate). A later object at Y may take slot s iff
   `SLOT_FREE_RASTER[s] <= Y - 12` (12 lines of IRQ lead). Batches group objects
   sharing a raster window; the scheduler prefers the **latest** reusable slot.
   HUD floor: slots 4..7 unusable before `HUD_HANDOFF_COMPLETE_RASTER` (56).

4. **Publication.** Initial: pointer `$07F8,x`, colour `$D027,x`, X/Y
   `$D000+2x`, accumulated `$D010`, `$D015`. LIVE batch: pointer via the
   self-modified page-aware `ssBatchPtrStore` (`$07F8`/`$2BF8`), colour, X, Y per
   assignment, then **one** `$D010` and one `PLAYER_HW_MASK` store per batch from
   BUILD-precomputed `BATCH_X_MSB_MASK` / `BATCH_PLAYER_MASK`.

5. **Initial vs LIVE.** `renderSprites` caps its writes at `HUD_SLOT_FIRST`(4)
   slots; entries 4..RC-1 are "deferred" and re-applied by `hudBorderHandoff` at
   raster 43. LIVE batches run from the raster IRQ.

6. **Worst-case player geometry.** Player Y range `GAMEPLAY_SPRITE_MIN_Y`(55)
   .. `PLAYER_MAX_Y`(237); start 220. Sorted ascending by Y, so the player is
   normally the LAST sorted object and lands in the LAST batch — the user's
   hypothesis is correct by construction.

7. **Projectiles EXIST in the shipping build.** `TYPE_ENEMY_BULLET = 3`,
   `MAX_ENEMY_BULLETS = 3`, speed 3 down, colour 7. Ordinary pool objects.

8. **RENDER_COUNT** is always `min(SORTED_COUNT, 8)`; `SPRITE_ENABLE_MASK,x` is
   indexed by it.

9. **Capacities that assume 1 object -> 1 assignment:**
   `SORTED_OBJECTS .fill MAX_OBJECTS(16)`; `INITIAL_* .fill 16` (8/plan);
   `ASSIGN_* .fill 16` (8/plan); `BATCH_* .fill 16`; `CLIP_SHADOW_* .fill 16`.

### Two findings that shape the whole experiment

**(a) `$D01C` is effectively static and gameplay is ALL multicolour.**
`setupSprites` sets `$D01C = %11111111`; `hudBorderSetup` clears the HUD slots to
hires each frame and `hudBorderHandoff` ORs them back to MC ("gameplay sprites
are MC"). A hires player therefore needs **per-slot** `$D01C` state that follows
the player through the multiplexer — a hardware axis the render plan does not
currently carry. Cheap fix available: the plan already precomputes
`BATCH_X_MSB_MASK` and applies it with ONE store per batch; a `BATCH_MODE_MASK`
alongside it costs ~8 cycles per batch, not per assignment.

**(b) `$D01E` is only a fast-path GATE, not the collision decision.**
```
capturePlayerCollision:
    lda VIC_SPRITE_COLLISION        // read+clear
    and PLAYER_HW_MASK
    bne !playerCollision+           // -> full SOFTWARE overlap scan of objects 1..15
```
Three co-located player sprites will set each other's bits every frame, so the
gate opens every frame. That **cannot** cause a false hit, because
`checkEnemyPlayerOverlap` / `checkBulletPlayerOverlap` are authoritative and only
test logical objects 1..15. The cost is that the filter stops filtering: the
15-object software scan runs every frame instead of rarely. That is a
measurable CPU cost on the frame-critical path, not a correctness break.
`$D01F` (sprite/background) is **not used anywhere** — terrain is unaffected.

## Implementation plan
Expand at the SORTED-LIST level: `buildSortedObjectList` emits the player three
times with a parallel `SORTED_LAYER` tag, so the existing snapshot/schedule/
publication machinery allocates, sorts, batches and publishes all three exactly
like any other sprite. Layer tag selects bitmap pointer + colour only.

## Implementation (as built)

Builds, from one tree via `#define OPT_THREE_LAYER_PLAYER`:

| build | SHA-256 |
|---|---|
| baseline `main` @ e94ccf5 | `809b5edc2eb004f55bf027b2d4bdd92df7ba89bebbe0be2d33fdb9b3496062b7` |
| three-layer (final) | `226e13689f408db5ee74681f8a0b6bfae2ed15b1402330dcca3076111b7bcb1e` |

- `buildSortedObjectList` emits the player once per layer; the layer index is
  packed into the HIGH NIBBLE of the sorted entry, so the insertion sort moves
  whole bytes and the tag travels with its object (no parallel array, no change
  to the sort's shift logic). Consumers mask with `#SORTED_OBJ_MASK`.
- `playerLayerSnapshot` / `playerLayerAssign` override ONLY bitmap pointer and
  colour. Position, X-MSB, visibility and ownership are the shared logical
  player's, so the layers are co-located by construction.
- `PLAYER_HW_MASK` / `SCHED_PLAYER_MASK` now ACCUMULATE (were single-bit stores).
- **$D01C is derived, not tabulated**: every gameplay sprite is multicolour
  except the player's layers, so the register is exactly `~PLAYER_HW_MASK`.
  In the IRQ that is `eor #$ff / sta SPRITE_MODE` right after the existing
  `sta PLAYER_HW_MASK` -- 4 cycles per BATCH, none per assignment.
- Layers are gated on `PLAYER_STATE == 0`: during explosion / respawn blink the
  player reverts to the existing single-sprite presentation (permitted by the
  brief, and it keeps the explosion frames and blink working unchanged).
- Layer 0 is the hull and keeps `OBJECT_COLOUR`, so the existing colour state
  machine (normal blue / red muzzle flash) still drives it. Layers 1 and 2 take
  fixed accent colours.
- `playerLayerAudit` records `PLAYER_LAYERS_LIVE` and `PLAYER_BUNDLE_SHORT`.

Placement: helper/tables in their own `$7000` segment, bitmaps 64-byte aligned
at `$2c00` (free VIC-bank-0 gap). `ENGINE_LOOKUP_SEGMENT` moved `$1f20 -> $1f60`
because the call sites grew the main code block to `$1f40` (the same "origin
simply moves up" precedent its own comment records); a new guard checks it stays
clear of the `$1fc0` border-marker sprite.

## Results so far
- Hires: 0 register violations / 120 samples; three colours on screen.
- Capacity: 3 layers always, until >=6 objects sit in the non-recyclable band.
- Collision: 0 false hits in every configuration, including forced pixel-overlap.
- Lifecycle: 6/6 loops, 96/96 checks.

## A/B toggle proof
`ENGINE_LOOKUP_SEGMENT`'s $1f20 -> $1f60 move is CONDITIONAL on
OPT_THREE_LAYER_PLAYER, so the toggle is exact in both directions:

    #define  OPT_THREE_LAYER_PLAYER  -> 226e13689f408db5ee74681f8a0b6bfae2ed15b1402330dcca3076111b7bcb1e
    //#define OPT_THREE_LAYER_PLAYER -> 809b5edc2eb004f55bf027b2d4bdd92df7ba89bebbe0be2d33fdb9b3496062b7
                                        (byte-identical to accepted main @ e94ccf5)

## Verdict
AMBER. Works, no architectural compromise, no deadline-margin loss, collision
safe, no permanent sprite reservation -- but costs 3 of 8 physical sprites in
the player's band: at most 5 other objects may sit within ~36 raster lines of
the player before the bundle degrades, ordinary scroll cadence drops ~9%, and
the `dense` / `y199` synthetic torture fixtures change materially (they exceed
the capacity envelope by construction). See
reports/experimental-three-layer-player-feasibility.md.

---

# Two-layer comparative pass

## Layer-count selector
`PLAYER_LAYER_COUNT` (1..3) is now the only difference between comparison
builds: `playerLayerEmit` unrolls `.for layer = 1 .. COUNT-1`, and the sprite /
colour tables are sized by it. All three bitmaps stay assembled at `$2c00` in
every build, so the 1/2/3 comparison has an IDENTICAL memory footprint and
differs only in how many layers the renderer publishes. Refactor verified
byte-identical at 3 layers.

## THE INSTRUMENTATION GAP (this is the whole story)
`frame_cycle_deltas [19656]` measures the PRESENTED FRAME PERIOD, and with a
per-physical-frame breakpoint it is exact BY CONSTRUCTION. A scroll stop is not
a dropped frame: the machine keeps presenting perfect PAL frames while the
TERRAIN STOPS, because coarse admission is deferred. Nothing measured that.

Same 3-layer build, same Level 1, old metrics: `[19656]`, service failures 0,
sprite-start misses 0, catchups 2 — all GREEN. New metric on that same build:
**61-frame terrain freeze**.

The only old number that even hinted was `coarse_steps 80 / 1400` vs the ideal
87.5 — a 9% aggregate shortfall that is actually CONCENTRATED into a handful of
~1-second freezes. The aggregate hid the distribution.

## Result (2400 frames, identical frame-indexed play input)
|                | 1-layer | 2-layer | 3-layer |
|---|---|---|---|
| frames per coarse | 16.0 | 16.0 | 18.18 |
| longest visible stop | 2 f | 2 f | **61 f** |
| stop runs >= 16 f | 0 | 0 | **5** |
| coarse defer BEAM / CUTOFF | 0 / 0 | 0 / 0 | **29 / 91** |
| stop-run histogram | {1:1198, 2:1} | {1:1193, 2:4} | {..36,44,48,50,61} |

Stop-run histograms for 1 and 2 layers are DISJOINT from 3-layer. The third
layer is the cliff.

## Mechanism (direct causal measurement)
Coarse admission needs `RASTER < BG_COARSE_LATEST_START (184)`. Raster at
`prepareBackgroundCoarse` entry:

    config    median   p90   %>=184
    1-layer     128    155     3.5
    2-layer     138    172     7.2
    3-layer     133    191    16.0

Each layer adds main-loop work AHEAD of that call (one more sorted entry to
insert-sort, one more plan entry to snapshot, one more slot to mask). At 3
layers the p90 crosses the deadline. Stalls occur at LOW sprite load
(sorted 8, batches 0) — it is CPU time, not sprite capacity.

## Instrumentation fix
`playerLayerAudit` now returns early when `PLAYER_STATE != 0`. It was counting
the deliberate single-sprite death/respawn presentation as a bundle shortfall,
which made `PLAYER_BUNDLE_SHORT` read as capacity failure (897 at 2 layers).
After the fix: **0**.

## Branch left at PLAYER_LAYER_COUNT = 2 for manual playtest.

---

# Late-frame reservation experiment

## Phase A — measured pre-coarse cost attribution (median cycles, 150 frames)

| segment                     | 1-layer | 2-layer | delta |
|---|---|---|---|
| updateTurretStream (loop head, layer-independent) | 3150 | 3139 | -11 |
| buildSortedObjectList       |  330 |  353 | **+23** |
| sortObjectsByY              |   42 |  127 | **+85** |
| **buildInitialSpriteSnapshot** | **296** | **511** | **+215** |
| buildBatchSpriteSchedule    |  260 |  308 | **+48** |
| planCoarseBulletSuppression |   32 |   32 | 0 |
| predecodeNextStageRow       |   64 |   64 | 0 |
| **layer-attributable total** | | | **+371** |

pre-coarse total median 4625 -> 5028 (+403, matches the segment sum + noise).
Gate raster median 96 -> 104, p90 157 -> 167. 403 cycles ~= 6.4 raster lines.

**buildInitialSpriteSnapshot is 58% of the whole regression, more than the other
three combined.** And most of that per-entry work is REDUNDANT for a player
layer: the generic path writes X, X_MSB, Y, calls snapshotSpritePointer (the
straddler/clip test, which the player can never need because its Y floor is
GAMEPLAY_SPRITE_MIN_Y), writes colour and owner -- and then playerLayerSnapshot
immediately OVERWRITES pointer and colour. A layer is co-located with layer 0 by
construction, so X / X_MSB / Y are known-identical to the previous plan entry.

## Phase B — the late-frame reservation ALREADY EXISTS

The requested architecture is: all 8 physical sprites usable earlier in the
frame, a pair reclaimed for the player as the raster approaches the player band,
scheduler-owned, previous owner's DMA provably complete. That is a precise
description of the engine's existing LIVE REUSE BATCH:

  SLOT_FREE_RASTER[s] = ownerY + 24; a later object may take slot s iff
  SLOT_FREE_RASTER[s] <= Y - 12. Batch fires at objectY - 12; applyLiveRasterBatch
  republishes pointer (page-aware $07F8/$2BF8), colour, X, Y, $D010, $D01C and
  PLAYER_HW_MASK.

Measured, representative Level 1, 2-layer, 600 frames:

    batch_count_hist        {0: 355, 1: 1}
    player_any_batch        0
    early_reuse_of_player_slot  0
    render_count_hist       {2:85, 3:44, 4:25, 5:39, 6:51, 7:14, 8:98}

-> the reuse mux essentially NEVER engages: the sorted list rarely exceeds 8, so
nothing is ever denied a slot by the player holding one. There is no early-frame
contention for a late reservation to relieve.

Measured with 9 enemies forced ABOVE the player (sorted 11 > 8), 250 frames:

    player_any_batch            235 / 236
    early_reuse_of_player_slot  468  (= both player slots, every frame)
    render_count_hist           {8: 235}      <- all 8 slots enemy-owned up top
    player_slots_hist           {2: 234}      <- player still gets both layers
    handoff_margin_min          63 raster lines

-> when contention DOES exist the engine already does exactly the requested
thing: 8 sprites for enemies in the upper/middle playfield, two of them
reclaimed for the player near the player band, 63 lines of margin.

Building a SEPARATE late-reservation subsystem would therefore add no capacity
(already achieved adaptively), and no timing (the batch path is the CHEAP path:
+48 cycles vs +215 for the initial-snapshot path). It would only change the
<=8-object case, where there is provably nothing to relieve -- and there it would
need new $D015 publication in the raster IRQ, because applyLiveRasterBatch does
not write the enable register (batched slots rely on being < RENDER_COUNT).

## $D01C hardening (implemented)
Previously the batch published $D01C as `eor #$ff` of the whole register. A batch
scheduled BEFORE hudBorderHandoff would have flipped the HUD score sprites to
multicolour mid-DMA. Now resolved in BUILD into BATCH_MODE_MASK: a batch whose
raster is < HUD_HANDOFF_COMPLETE_RASTER masks the HUD block to hires, so the
corruption is structurally impossible rather than merely unreachable. IRQ cost
+3 cycles per batch; measured scroll behaviour byte-for-byte unchanged.

## Verdict
Late-frame reservation as a CAPABILITY: already present and GREEN.
Building a NEW dedicated subsystem: not recommended (no measurable benefit).
Branch left at PLAYER_LAYER_COUNT = 2 (dynamic) + $D01C hardening.

---

# Pre-coarse optimisation pass (2-layer)

## METHODOLOGY TRAP -- read this before trusting any attribution number
The first attribution baseline was measured on a scene with **SORTED_COUNT = 2**:
only the player's two layers, NO ENEMIES. `vice_precoarse_attribution.py` had a
30-frame warm-up, but Level 1's first authored wave trigger is ~112 frames in.
On an empty scene the sort optimisation below measures ZERO benefit, because
there is nothing to shift past. The probe now takes `--warmup` (default 260) and
records `sorted_count` in its output so a light scene can never again be
mistaken for a representative one.

Empty scene (SORTED_COUNT 2):   layer overhead +372, optimisation recovers  73 (20%)
Busy scene  (SORTED_COUNT 6):   layer overhead +523, optimisation recovers 228 (44%)

The busy-scene numbers are the representative ones. Controls confirm the scenes
are comparable: `planCoarseBulletSuppression` 32 and `predecodeNextStageRow` 64
are IDENTICAL across all three builds, and `updateTurretStream` is within 1%.

## Two optimisations, both kept

**1. Emit the extra player layers LAST in the unsorted list** (was: immediately
after layer 0, at the head). The list is unsorted and `sortObjectsByY` is an
insertion sort; the player has the highest Y on screen, so entries belonging at
the END of the sorted order sat at the FRONT of the input, and every subsequent
enemy insertion had to shift past them. The sorted RESULT is identical either
way (`beq !insert+` puts an equal key after existing equals).
    sortObjectsByY  862 -> 706   (-156)
Costs +24 in buildSortedObjectList for the PLAYER_IN_SORTED flag. Net +132.

**2. Specialised snapshot path for player layer > 0.**
    buildInitialSpriteSnapshot  1193 -> 1097   (-96)
Skips: `jsr snapshotSpritePointer` (the straddler/clip decision, which the living
player can never need -- its Y floor IS GAMEPLAY_SPRITE_MIN_Y), the generic
OBJECT_SPRITE/OBJECT_COLOUR pair that was immediately overwritten, and two nested
jsr/rts pairs. Reproduces the one side effect that matters (clearing the entry's
clip shadow). X / X-MSB / Y are read from logical object 0, so co-location stays
guaranteed BY CONSTRUCTION.

### Rejected: copying X/Y/MSB from plan entry y-1
Would have saved nothing (same 9 cycles per field as reading the object arrays)
AND would have been WRONG. Measured player masks include `10100000` -- hardware
slots 5 and 7, NON-ADJACENT. The two layers do not always occupy adjacent plan
entries, so a `y-1` shortcut would have de-co-located the bundle.

## Result
228 of 523 cycles recovered = **44%** of the 1->2 layer overhead.
Co-location: **0 violations** over 322 frames of fast movement; distinct
pointers and colours every frame; layers per frame min 2 max 2;
PLAYER_BUNDLE_SHORT 0.
Scroll: 16.0 frames/coarse, longest stop 2 frames, **0 runs >= 4**, 0 deferrals.

## Memory
`ENGINE_LOOKUP_SEGMENT` moved $1f60 -> $7300: the main code block grew past the
$1fc0 border-marker cap. The block is plain CPU-side lookup data (bit masks, star
row addresses, HUD proof tables), absolute-indexed, no alignment constraint.
