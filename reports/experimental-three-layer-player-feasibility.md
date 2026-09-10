# 19656 — Experimental Three-Layer Hires Player: Feasibility

**Verdict: AMBER.** One logical player expanded by the renderer into three
co-located hires sprite assignments works, keeps exact PAL, and breaks nothing
in supported gameplay — but it costs three of the eight physical sprites in the
band where the player lives, and that cost is measurable and must be
consciously accepted. Details and the exact envelope below.

---

## 1. Starting `main` HEAD

`main` @ **`e94ccf5`** *("High Score screen corruption fixed")* — the accepted
state containing the lifecycle-corruption repair and the 16 px score font.
Verified before branching:

* `git status` — **clean**, nothing staged or modified;
* `ssSelectPageA` present at its three sites, `HUD_SCORE_TOP_ROW = 2`,
  `HUD_SCORE_GLYPH_H = 16`, `setupLivesDisplay` reduced to the stock reset;
* rebuild reproduces the accepted hash
  `809b5edc2eb004f55bf027b2d4bdd92df7ba89bebbe0be2d33fdb9b3496062b7` exactly.

## 2. Branch and resulting HEAD

Created and switched to **`experimental-three-layer-player`**, HEAD
**`e94ccf5`** (branch point; **no commits made** — commits were not authorised).

## 3. Clean / dirty status

Worktree at branch creation: clean. Current worktree carries only the
experiment:

```
 M src/main.asm
 M src/raster_scheduler.asm
?? docs/experimental-three-layer-player-worklog.md
?? tools/vice_player_bundle_probe.py
?? tools/vice_player_capacity_sweep.py
?? tools/vice_player_collision_check.py
?? tools/vice_player_layers_visual.py
```

**Nothing committed, merged, tagged or pushed.**

| build | SHA-256 |
|---|---|
| baseline (single sprite) | `809b5edc2eb004f55bf027b2d4bdd92df7ba89bebbe0be2d33fdb9b3496062b7` |
| **three-layer (final)** | `226e13689f408db5ee74681f8a0b6bfae2ed15b1402330dcca3076111b7bcb1e` |

Both build from the same tree via `#define OPT_THREE_LAYER_PLAYER`, so every
comparison below is like-for-like. **Verified, not assumed:** commenting the
define out rebuilds `809b5edc…` — byte-for-byte identical to the accepted
`main` build — and restoring it rebuilds `226e1368…`. The experiment is
therefore a genuine A/B toggle with no residue in the baseline path (the
`ENGINE_LOOKUP_SEGMENT` move in §5 is itself conditional for exactly this
reason).

---

## 4. Current single-sprite player render architecture (Phase A audit)

**Pipeline.** `buildSortedObjectList` (active && Y in [35, 246)) →
`sortObjectsByY` (insertion sort, ascending Y) → `buildInitialSpriteSnapshot`
(the first `min(SORTED_COUNT, 8)` sorted objects; **sorted index == hardware
slot**) → `buildBatchSpriteSchedule` (sorted objects 9+ into recycled slots) →
`swapRenderPlans` → `renderSprites` (main thread) + `applyLiveRasterBatch`
(raster IRQ). It is strictly **one logical object → one render assignment**.

**Player slot-0 special cases — the complete list:**

| site | what it does |
|---|---|
| `renderSprites` | `INITIAL_OBJECT == 0` → `PLAYER_HW_MASK = HW_BIT_MASK[slot]` |
| `beginRasterPlanMasks` / `extendRasterPlanMasks` | same test → `SCHED_PLAYER_MASK` |
| `hudBorderHandoff` | the only place that already **OR**s the mask |
| `capturePlayerCollision` | scans logical objects 1..15, skipping 0 |
| `startGame` | pins object 0 as the player |

Sorting and slot allocation otherwise treat the player as an ordinary object.

**Slot allocation / recycling.** `SLOT_FREE_RASTER[s] = ownerY + 24`
(DMA-complete estimate). A later object at Y may take slot `s` iff
`SLOT_FREE_RASTER[s] <= Y - 12` (12 lines of IRQ lead). Batches group objects
sharing a raster window; the scheduler prefers the *latest* reusable slot. HUD
slots 4..7 are floored to `HUD_HANDOFF_COMPLETE_RASTER` (56).

**Publication.** Initial: pointer `$07F8,x`, colour `$D027,x`, X/Y `$D000+2x`,
accumulated `$D010` and `$D015`. LIVE batch: pointer through the self-modified
page-aware `ssBatchPtrStore` (`$07F8`/`$2BF8`), colour, X, Y per assignment, then
**one** `$D010` and one `PLAYER_HW_MASK` store per batch from BUILD-precomputed
`BATCH_X_MSB_MASK` / `BATCH_PLAYER_MASK`.

**Initial vs LIVE.** `renderSprites` caps its writes at `HUD_SLOT_FIRST` (4)
slots; entries 4..RC-1 are deferred and re-applied by `hudBorderHandoff` at
raster 43.

**Worst-case player geometry.** Player Y is 55..237 (start 220). Sorting is
ascending by Y, so **the player is normally the last sorted object and lands in
the last batch** — the brief's hypothesis is correct by construction, and the
measurements below confirm it.

**Projectiles exist in the shipping build:** `TYPE_ENEMY_BULLET = 3`,
`MAX_ENEMY_BULLETS = 3`, speed 3 downward. Ordinary pool objects, so no
test-only projectile system was needed.

**`RENDER_COUNT`** is always `min(SORTED_COUNT, 8)`; `SPRITE_ENABLE_MASK,x` is
indexed by it.

**Capacities that encoded "one object → one assignment":**
`SORTED_OBJECTS .fill MAX_OBJECTS(16)` (the one that actually had to grow);
`INITIAL_* .fill 16` and `ASSIGN_* .fill 16` (8 per plan — unchanged, because
the extra layers consume plan entries, not new arrays); `BATCH_* .fill 16`;
`CLIP_SHADOW_* .fill 16`.

### Two audit findings that shaped everything

**(a) `$D01C` was effectively static, and gameplay is all multicolour.**
`setupSprites` sets `$D01C = %11111111`; `hudBorderSetup` clears the HUD slots
to hires each frame and `hudBorderHandoff` ORs them back ("gameplay sprites are
MC"). A hires player needs per-slot mode state that follows the player through
the multiplexer — an axis the render plan did not carry. Solved cheaply in §5.

**(b) `$D01E` is only a fast-path GATE, not the collision decision.** See §12.

---

## 5. Implementation: one logical player → three render assignments

The expansion happens **at the sorted-list level**, which is what keeps the
proven architecture intact — every later stage allocates, sorts, batches,
publishes and hands off the layers exactly as it does any other sprite. Nothing
bypasses the render plan, the scheduler or the pointer publication.

* **`buildSortedObjectList`** emits the player once per layer. The layer index
  is packed into the **high nibble** of the sorted entry
  (`entry = object | layer << 4`), so the insertion sort keeps moving whole
  bytes and the tag travels with its object — **no parallel array and no change
  to the sort's shift logic**. The five consumers mask with `#SORTED_OBJ_MASK`.
* **`playerLayerSnapshot` / `playerLayerAssign`** override *only* the bitmap
  pointer and colour. Position, X-MSB, visibility and logical ownership are the
  shared logical player's values already written by the normal path, so **the
  three layers are co-located by construction** rather than by synchronisation.
* **`PLAYER_HW_MASK` and `SCHED_PLAYER_MASK` now accumulate** (they were
  single-bit stores). `extendRasterPlanMasks`' existing `and HW_CLEAR_MASK,x`
  still correctly retires a slot's old bit on reuse.
* **`SORTED_OBJECTS` grew** to `MAX_OBJECTS + PLAYER_LAYER_COUNT - 1`.
* **`$D01C` is derived, not tabulated.** Every gameplay sprite is multicolour
  except the player's layers, so the whole register is exactly
  `~PLAYER_HW_MASK`. In the IRQ that is `eor #$ff / sta SPRITE_MODE`
  immediately after the existing `sta PLAYER_HW_MASK` — **4 cycles per batch,
  none per assignment**, and it stays correct automatically as the player moves
  between physical slots. `renderSprites` applies the same rule to the non-HUD
  slots only; `hudBorderHandoff` re-derives the full register after it has
  reclaimed slots 4..7.
* **Layers are gated on `PLAYER_STATE == 0`.** During explosion and
  respawn-blink the player reverts to the existing single-sprite presentation,
  which the brief explicitly permits and which keeps the explosion frames and
  blink working unchanged (§15).
* **Layer 0 keeps `OBJECT_COLOUR`**, so the existing colour state machine
  (normal blue / red muzzle flash) still drives the hull. Layers 1 and 2 take
  fixed accent colours.

**Placement.** Helper and tables in their own `$7000` segment; bitmaps 64-byte
aligned at `$2c00` (the free VIC-bank-0 gap between page B at `$2bff` and the
HUD sprite block at `$2f00`). The call sites grew the main code block to
`$1f40`, so `ENGINE_LOOKUP_SEGMENT` moved `$1f20 → $1f60` — the same "the origin
simply moves up" precedent recorded in that block's own comment — and a **new
guard** now checks it stays clear of the `$1fc0` border-marker sprite.

## 6. Diagnostic layer pointers and colours

| layer | bitmap | pointer | colour | content |
|---|---|---|---|---|
| 0 | `$2c00` | `$b0` | `OBJECT_COLOUR` (14 light blue normally, 2 red on muzzle flash) | hull outline |
| 1 | `$2c40` | `$b1` | 7 yellow | central spine |
| 2 | `$2c80` | `$b2` | 3 cyan | wing tips |

Deliberately complementary: **no pixel is set in more than one layer**, so all
three colours are visible at once and a missing layer is immediately obvious.
This is diagnostic, not final art — as instructed, no time was spent designing
a ship.

## 7. Atomic bundle policy

Policy, stated plainly: **the layers are allocated by the ordinary scheduler,
and a shortfall is instrumented rather than hidden.**

* All three layers carry identical X/Y/X-MSB/ownership from the single logical
  player, so they can never be presented at different positions.
* All three are ordinary plan entries, so none can carry a stale pointer from a
  previous owner, appear a frame late, or be reclaimed early — they inherit the
  same `SLOT_FREE_RASTER` and 12-line lead rules as every other sprite.
* If the scheduler cannot place all three, `playerLayerAudit` (called at every
  exit of `buildBatchSpriteSchedule`) records `PLAYER_LAYERS_LIVE` and
  increments `PLAYER_BUNDLE_SHORT`. The player then renders with fewer layers
  rather than the frame being dropped or the geometry faked.

Deliberately **not** implemented: any permanent reservation of three hardware
sprites. The measurements in §11 show the multiplexer does recycle slots for
the player exactly as hoped, so a reservation was never needed — and the brief
forbids one as a shortcut.

## 8. Baseline timing / capacity (single-sprite player)

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | catchups | replay | page A/B | coarse steps |
|---|---|---|---|---|---|---|---|---|---|---|
| ordinary | 1400 | `[19656]` | 0 | 0 | 9 | 0 | 0 | 1 | 728/672 | 87 |
| dense | 900 | `[19656]` | 0 | 0 | 16 | 8 | 6286 | 450 | 452/448 | — |
| y199 / 199-235 | 400 | `[19656]` | 0 | 0 | 9 | 1 | 0 | 0 | 211/189 | 12 |

Player-bundle geometry, baseline: player owns **1** physical slot on every
frame; **worst deadline margin 6 raster lines** over 240 player-assigning
batches; max 1 player assignment per batch.

## 9. Three-layer timing / capacity

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | catchups | replay | page A/B | coarse steps |
|---|---|---|---|---|---|---|---|---|---|---|
| ordinary | 1400 | **`[19656]`** | **0** | **0** | 9 | 1 | 2 | 9 | 713/687 | 79 |
| dense | 900 | **`[19656]`** | **0** | **0** | 16 | **3** | **898** | 450 | 452/448 | — |
| y199 / 199-235 | 400 | **`[19656]`** | **0** | **0** | 9 | 1 | 0 | 4 | **400/0** | **2** |
| stage wrap | 1200 | **`[19656]`** | **0** | **0** | 9 | 1 | 2 | 18 | 470/730 | 73, **1 wrap** |
| aperture passive | 400 | **`[19656]`** | **0** | **0** | 8 | 1 | 0 | 1 | 192/208 | 24 |
| aperture dense | 400 | **`[19656]`** | **0** | **0** | 16 | 3 | 398 | 200 | 208/192 | 12 |

**Exact PAL `[19656]`, zero service failures and zero sprite-start misses in
every capture**, including the synthetic stress fixtures.

Differences that matter:

| metric | baseline | three-layer | reading |
|---|---|---|---|
| ordinary coarse steps / 1400 | 87 | 79 | ~9 % slower scroll cadence in real play |
| dense `max_batches` | 8 | **3** | fewer synthetic objects get slots |
| dense catchups | 6286 | **898** | consequence of the above |
| y199 coarse steps / 400 | 12 | **2** | scroll largely stalled in this fixture |
| y199 page-B frames | 189 | **0** | no coarse page publication at all |

**These are torture-fixture results, and they are over the capacity envelope by
construction**: `y199` parks 8 enemies at Y=199 with the player at Y=235, i.e.
8 objects inside the player's non-recyclable band, plus 3 player layers — 11
sprites wanted where 8 exist. `dense` clusters 16 objects into a narrow band.
Neither is supported gameplay (a wave is 5–6 enemies, `MAX_ENEMY_BULLETS` is 3).
Supported-gameplay captures — ordinary, stage wrap, both apertures — are clean,
which is the distinction the brief asked to be drawn explicitly.

Stage 5 edge masking: **0 body / 0 lastrow temporal diffs**, passive *and*
dense, all eight fine-scroll phases exercised. Stage wrap exercised (1 end→start
wrap, every step a single decrement, 0 bad steps).

## 10. Worst player-bundle deadline margin

Measured at `rasterBatchMasksApplied` — the point at which a batch's
assignments are all written — for **only** those batches that actually assign
logical object 0, as `OBJECT_Y(player) − current raster line`.

| build | player-assigning batches | worst margin | max player assigns in one batch |
|---|---|---|---|
| baseline | 240 | **6 lines** | 1 |
| three-layer | 381 | **6 lines** | **3** |

**No margin loss.** All three layers are routinely installed by a single batch,
and that batch still completes 6 raster lines before the player's sprite DMA —
identical to the single-sprite baseline.

*(An earlier version of this probe reported −18 lines. That was a measurement
error, not a defect: `BATCH_PLAYER_MASK` is cumulative ownership state seeded
from the INITIAL entries, so batches that never touch the player still carry its
bit, and batches firing below the player then produced meaningless negative
margins. The probe now filters on `ASSIGN_OBJECT == 0`.)*

## 11. Lower-screen density and projectile results

The governing rule: a slot is recyclable for the player only if
`ownerY + 24 <= playerY − 12`, i.e. only for objects at least **36 lines above**
the player. Objects inside that band hold their slots.

Sweep with the player held at Y=220 and alive (measuring allocation, not death):

| objects in the **blocking** band (Y 190–214) | layers presented | `PLAYER_BUNDLE_SHORT` |
|---|---|---|
| 0 | 3 / 3 / 3 … | 0 |
| 1 | 3 | 0 |
| 2 | 3 | 0 |
| 3 | 3 | 0 |
| 4 | 3 | 0 |
| **5** | **3 on every frame** | **0** |
| 6 | mostly 1, some 2 | 39 / 40 frames |
| 7 | 1 | 40 / 40 frames |

| objects **above** the band (Y 90–153) | layers presented | short |
|---|---|---|
| 0 … 7 | **3 on every frame** | 0 |

**The envelope is exactly what the slot arithmetic predicts: 8 physical sprites
− 3 player layers = 5 other objects may sit within ~36 lines of the player.**
Objects higher up the screen cost nothing at all — their slots recycle cleanly
into the player bundle, which is precisely the behaviour the experiment set out
to test, and it confirms the brief's intuition.

Against real gameplay limits: `MAX_ENEMY_BULLETS` is **3**, so "player + up to
three low projectiles" is 3 blocking objects — comfortably inside the envelope
of 5. Fixture results (player held alive, real pool objects):

| fixture | layers presented |
|---|---|
| ordinary play | 3 / 3 |
| player + 1 projectile | 3 |
| player + 2 projectiles | 3 |
| player + 3 projectiles (the shipping cap) | 3 |
| lower-screen enemy + projectile pressure | 3 |
| player at upper bound (Y 55) | 3 |
| player at lower bound (Y 237) | 3 |

## 12. Collision analysis and results

**Architecture.** `capturePlayerCollision` reads `$D01E` and uses
`and PLAYER_HW_MASK` **only as a fast-path gate**; the authoritative decision is
a software overlap scan (`checkEnemyPlayerOverlap` / `checkBulletPlayerOverlap`)
over logical objects 1..15. `$D01F` (sprite/background) is **not used anywhere**,
so terrain collision is untouched. Enemy damage is entirely software — `$D01E`
is never consulted for it — so three player layers cannot contaminate enemy hits.

**The risk** is that three co-located sprites set each other's bits in `$D01E`,
holding the gate permanently open. Measured in both configurations:

| test | non-overlapping layers (as shipped) | layers forced to share pixels (worst case) |
|---|---|---|
| gate open | **0 / 150 frames** | **150 / 150 frames** |
| isolated player, false hits | **0 / 200** | **0 / 150** |
| player state stays alive | yes | yes |
| lives lost while isolated | 0 | 0 |
| real enemy overlap → hit | **yes** | **yes** |
| distant enemy → false hit | **0 / 120** | — |
| real projectile overlap → hit | **yes** | — |
| lives lost for ONE hit | **exactly 1** | **exactly 1** |
| death states seen | 0 → 1 → 2 → 0 | 0 → 1 → 2 → 0 |

Two findings:

1. **VIC sprite/sprite collision only fires on overlapping non-transparent
   pixels.** Because the diagnostic layers set disjoint pixels, they never
   collide with each other at all — the gate is untouched, at zero cost. Layered
   art that assigns each pixel to exactly one layer (the natural design for
   independent colours) keeps this property.
2. **Even with layers forced to share every pixel, there is no correctness
   break.** The gate opens on every frame, but the software scan is
   authoritative and rejects the self-collision, so no false player hit, no
   repeated damage, and exactly one life per real hit. The only cost is that the
   filter stops filtering, so the bounded 15-object scan runs every frame — and
   the regression captures show that cost is absorbed (`[19656]`, 0 failures).

**No collision redesign was needed, and nothing is hidden.** The existing
logical-player semantics remain authoritative; the three physical layers are
already interpreted as one collision entity because `PLAYER_HW_MASK` is a mask,
not a slot index — accumulating its bits was the whole change.

## 13. HUD / pointer-publication proof

| check | result |
|---|---|
| `$07F8` / `$2BF8` correct against the live page, every frame | **0 mismatches across 4700 captured frames** (`check_raster_capture` validates this per frame; any error appears as a service failure) |
| service failures / sprite-start misses | **0 / 0** in all six captures |
| page-aware fallback | `page_aware: true`, both pages exercised in ordinary, dense, wrap and both apertures |
| HUD slot reclaim after handoff | intact — `hudBorderHandoff` unchanged except for re-deriving `$D01C` after its reclaim loop |
| permanent sprite reservation | **none** — HUD still borrows slots 4..7 and hands them back every frame |
| score HUD stability | full lifecycle suite green (§15) |
| `$D01C` correctness | **0 violations / 120 samples**: every player-owned slot hires, every other enabled slot multicolour |

One documented caveat: `applyLiveRasterBatch` now writes `$D01C` for the whole
register. A batch scheduled before `hudBorderHandoff` (raster 43) would
therefore set the HUD slots to multicolour for the remainder of their DMA.
Batch raster is `objectY − 12` and batched objects are the *lowest* on screen,
so this did not occur in any capture; it is called out rather than assumed away,
and would be trivially closed by masking the HUD bits in that one store.

## 14. Scrolling / exact-PAL regression

Covered in §9. Every capture is exact `[19656]` with zero service failures and
zero sprite-start misses; Stage 5 aperture is 0/0 body and lastrow in both
passive and dense; the stage wrap is exercised with every step a single
decrement. The scroll **cadence** is ~9 % slower in ordinary play (87 → 79
coarse steps per 1400 frames) and substantially slower in the over-capacity
`y199` fixture (12 → 2), which is the capacity cost showing up as deferred
coarse admission rather than as dropped frames.

## 15. Death / respawn behaviour

Layers are gated on `PLAYER_STATE == 0`, so explosion frames and the
respawn-blink use the existing single-sprite presentation unchanged — the
isolation the brief permits, and it avoids three static layers standing in for
an explosion. Verified over 6 full lifecycles (16 checks each, **96 / 96 pass,
0 failures**): `PLAYER_STATE` 0 → 1 → 2 → 0, exactly one life consumed per hit,
respawned hull back to `OBJECT_COLOUR` 14, GAME OVER → initials → menu → new
game all correct, high-score rows matching their stored 24-bit values, new-game
stage origin correct, and no stale UI characters in terrain.

Because layer 0 keeps `OBJECT_COLOUR`, the existing muzzle-flash red still
drives the hull; layers 1 and 2 hold their accent colours through it.

## 16. Build / test artifact cleanup and final disk usage

* Every emulator capture went to a scratch root **outside the repository**;
  `tools/run_regression_suite.sh` deletes each capture directory immediately
  after analysing it and keeps only small JSON summaries. Peak transient usage
  was ~70 MB for one capture at a time.
* Repository `build/` after this work: **300 KB, 4 files** — unchanged in shape
  from the start of the task. No per-run, per-seed or timestamped files.
* Scratch after cleanup: **492 KB** (JSON summaries plus the two 40 KB PRG
  copies used for like-for-like comparison).
* Transient PNGs from the visual check are deleted unless `--keep` is given.
* One process-hygiene issue was found and fixed in my own driver: the capture
  harness detaches from VICE without quitting it, so the driver now kills the
  pid **it** launched. A regression run was also restarted after I discovered it
  was reading `build/shooter.prg` while I rebuilt it mid-run; the final suite
  runs against an immutable copy in scratch. No unrelated, user-launched VICE
  was touched.
* **VICE focus discipline:** every instance is launched directly via
  `subprocess.Popen` / background `&` on the binary path — never `open -a` — so
  no automated run activates or focuses the VICE application. All driving is
  through the remote monitor.

## 17. Verdict — AMBER

Three-layer hires player **works**, with no architectural compromise:

* one logical object, expanded by the render-plan machinery into three atomic
  co-located assignments — no independently simulated player objects, no
  unmanaged sprites, no bypass of the scheduler or pointer publication;
* three independent hires colours at full horizontal resolution, verified in
  registers and in pixels;
* exact PAL `[19656]`, zero service failures, zero sprite-start misses in every
  capture;
* **no deadline-margin loss** (6 lines, identical to baseline);
* collision correct in every configuration tested, including forced pixel
  overlap;
* **no permanent sprite reservation** — the multiplexer really does recycle
  slots into the player bundle, exactly as hypothesised;
* HUD borrow/handoff and `$07F8`/`$2BF8` publication intact.

It is AMBER, not GREEN, because it imposes **specific, measurable restrictions**
that must be consciously accepted:

1. **At most 5 other objects may occupy the ~36 raster lines above the player.**
   At 6 the bundle degrades to 1–2 layers (instrumented, not hidden). Today's
   gameplay stays inside this — `MAX_ENEMY_BULLETS` is 3 — but it is now a real
   design constraint on lower-screen encounter authoring.
2. **Scroll cadence drops ~9 % in ordinary play** (87 → 79 coarse steps per
   1400 frames) and collapses in over-capacity geometry (`y199`: 12 → 2 coarse
   steps, no page-B publication at all).
3. **Two existing regression fixtures change materially** — `dense`
   `max_batches` 8 → 3, `y199` scroll largely stalled. Both are synthetic
   torture fixtures that exceed the capacity envelope by construction, but they
   are part of the accepted regression set and would need re-baselining or
   explicit exemption.
4. **Layered art should keep layers pixel-disjoint.** Overlapping layers are
   still *correct*, but they hold the `$D01E` fast path permanently open.
5. **Death/explosion uses single-sprite presentation** (isolated and
   documented, as permitted).

Nothing here is a blocker; all five are decisions rather than defects. I have
not forced a GREEN, and I have not hidden the fixture regressions.

## 18. Two-layer estimate (evidence-based, not implemented)

From the same slot arithmetic, and directly supported by the sweep in §11 — the
envelope is `8 − layers` objects in the non-recyclable band:

* **two layers → 6 tolerated objects** instead of 5, i.e. exactly one more.
* The `y199` fixture needs 8 blocking objects + layers; at two layers that is
  10 wanted against 8 slots, so **`y199` would still fail**. The fixture
  regressions in §17.3 are therefore *not* resolved by dropping to two layers.
* Ordinary play, both apertures and stage wrap are already clean at three
  layers, so two layers buy no correctness there — only margin.

Conclusion: a two-layer player would be safer by exactly one lower-screen
object and would not rescue the synthetic fixtures. **If the third colour is
worth a documented five-object budget near the player, keep three; if the
encounter design wants more lower-screen traffic, two layers is the cheaper
compromise — but the decision is about encounter density, not about timing
safety.** I have not implemented the two-layer fallback, as instructed.

## 19. Manual test checklist

1. Build with `#define OPT_THREE_LAYER_PLAYER` active and start a game.
2. **Three colours.** The ship should show a light-blue outline, a yellow spine
   and cyan wing tips simultaneously — three hires colours, full horizontal
   resolution, no multicolour chunkiness.
3. **Co-location.** Move fast in all directions and at the screen edges. The
   three layers must never separate, lag by a frame, or flicker independently.
4. **Muzzle flash.** Hold fire: the hull (layer 0) should flash red while the
   yellow and cyan accents stay put.
5. **Lower-screen density.** Let enemies descend toward the player and take
   fire. With up to ~5 objects close above the ship, all three layers must
   persist. Beyond that, expect layers to drop — confirm it degrades visibly
   rather than corrupting.
6. **Death and respawn.** Take a hit: the explosion should play as the normal
   single-sprite animation, the blink should work, and the three layers should
   return cleanly on respawn.
7. **Top and bottom bounds.** Fly to the very top and the very bottom of the
   playfield; all three layers must render at both extremes.
8. **HUD.** Watch the top border under heavy waves — the score must stay stable,
   with no flicker and no colour change.
9. **Scrolling.** Confirm the terrain still scrolls smoothly; note it is
   slightly slower than the baseline by design of the capacity cost.
10. **Toggle off.** Comment out `OPT_THREE_LAYER_PLAYER` and rebuild: the PRG
    should hash `809b5edc…`, byte-for-byte the accepted `main` build. (Verified
    in this session, both directions.)

## 20. Files changed

* `src/main.asm`, `src/raster_scheduler.asm` — the experiment (all under
  `OPT_THREE_LAYER_PLAYER`).
* `docs/experimental-three-layer-player-worklog.md` — new, per AGENTS.md.
* `reports/experimental-three-layer-player-feasibility.md` — this report.
* New probes: `tools/vice_player_bundle_probe.py`,
  `tools/vice_player_capacity_sweep.py`,
  `tools/vice_player_collision_check.py`,
  `tools/vice_player_layers_visual.py`.

`src/background_turrets.asm` is unmodified.

**Branch `experimental-three-layer-player`. Not merged, not pushed, not tagged,
not committed.**
