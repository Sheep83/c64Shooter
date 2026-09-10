# 19656 — Late-Frame Player Sprite Reservation Experiment

**Verdict: the requested architecture already exists in the engine, is already
GREEN, and engages automatically exactly when it is needed. Building a separate
late-reservation subsystem is AMBER→not recommended: it would add no capacity,
no timing benefit, and new risk.**

The engine's LIVE reuse batch *is* a late-frame reservation. Measured under
forced contention it delivers precisely the stated goal — **8 physical sprites
for enemies in the upper/middle playfield, two of them reclaimed for the player
near the player band, with a 63-raster-line handoff margin** — while under
representative Level 1 it correctly stays out of the way (0 batches on 355 of
356 frames, because nothing is ever denied a slot).

One real improvement did come out of this pass and **is implemented**: the
`$D01C` publication is now structurally safe rather than merely unreachable.

Branch left on the known-good **dynamic 2-layer** player.

---

## 1. Starting branch / HEAD / worktree

Branch **`experimental-three-layer-player`**, HEAD **`e94ccf5`**, no commits.
Worktree carried the 2-layer player, the Level 1 five-enemy rebalance and the
canonical JSON pipeline, all intact and unmodified by this pass except the
`$D01C` change in §9.

| build | SHA-256 |
|---|---|
| 2-layer **before** this pass | `29e46b78c33545d7356759038faacd7a80832332a0a073618e08971a89f42253` |
| **2-layer + `$D01C` hardening (branch left here)** | `67c5965de6e2e6cc6e02cd710044caaaa7464db2d550ff4273ffc4961de566cd` |
| 1-layer reference | `17b1f0a2637cca185c90111d001e4cd5d681660d3a61cd19ba2c12f6fb7cc4a8` |
| 3-layer reference | `1d1397064700cfdffbffa8cafe918eb932b974ab2c31ca9740add78069836022` |

`build/shooter.prg` hashes `67c5965d…`, identical to the tested variant.

## 2. Current dynamic 2-layer cost breakdown

Measured with VICE's free-running cycle counter, breaking on each routine in
the pre-coarse chain — **cycles, not source-level guesses**. 150 frames,
representative Level 1, identical burst-fire input.

| segment | 1-layer median | 2-layer median | **delta** | 1L p90 | 2L p90 |
|---|---|---|---|---|---|
| `updateTurretStream` (loop head, layer-independent) | 3150 | 3139 | −11 | 4198 | 4205 |
| `buildSortedObjectList` | 330 | 353 | **+23** | 502 | 524 |
| `sortObjectsByY` | 42 | 127 | **+85** | 612 | 857 |
| **`buildInitialSpriteSnapshot`** | **296** | **511** | **+215** | 1526 | 1807 |
| `buildBatchSpriteSchedule` | 260 | 308 | **+48** | 439 | 490 |
| `planCoarseBulletSuppression` | 32 | 32 | 0 | 43 | 75 |
| `predecodeNextStageRow` | 64 | 64 | 0 | 107 | 117 |
| **layer-attributable total** | | | **+371** | | |

Whole pre-coarse path: median **4625 → 5028 cycles (+403)**, consistent with the
segment sum plus noise. Gate raster median **96 → 104**, p90 **157 → 167**.
403 cycles ≈ **6.4 raster lines** at 63 cycles/line, which matches the observed
+8 median lines once badline inflation is included.

## 3. Exact cause of the 1→2 layer pre-coarse increase

**`buildInitialSpriteSnapshot` is 58% of it (+215 of +371) — more than the other
three routines combined.** The remainder splits +85 sort, +48 batch scheduling,
+23 list building.

And most of that +215 is **redundant work**. For a player layer the generic
per-entry path writes X, X_MSB and Y (values that are *identical to layer 0 by
construction* — co-location is the whole point of the bundle), calls
`snapshotSpritePointer` (whose straddler/clip test the player can never need,
because the player's Y floor *is* `GAMEPLAY_SPRITE_MIN_Y`), then writes colour
and owner — after which `playerLayerSnapshot` immediately **overwrites** the
pointer and colour it just computed. Two nested `jsr`/`rts` pairs sit on top of
that.

This matters for the experiment's premise: a late reservation is only worthwhile
if it *removes* meaningful pre-coarse work. It does not (§4–7) — but the
redundancy above is a genuine, cheap, contained saving if margin is ever needed
(§20).

## 4. Late-frame ownership design — and the finding that it already exists

The requested design is:

> all 8 physical sprites available to the normal mux earlier in the frame; two
> of them handed to the player through a small, deterministic, scheduler-owned
> operation near the player raster band; the previous owner's DMA provably
> complete.

That is a precise description of the engine's existing **LIVE reuse batch**:

```
SLOT_FREE_RASTER[s] = ownerY + 24            (owner's DMA-complete estimate)
slot s may be reused by a later object iff   SLOT_FREE_RASTER[s] <= newY - 12
batch fires at   objectY - 12
applyLiveRasterBatch republishes: pointer (page-aware $07F8 / $2BF8 via the
self-modified ssBatchPtrStore), colour, X, Y, then $D010, $D01C and
PLAYER_HW_MASK once per batch
```

Every requirement in the brief is already satisfied by that path: it is
scheduler-owned, not a mainline VIC seizure; it is atomic per batch; it proves
the previous owner's DMA has completed via the 24-line rule; and it reserves
nothing permanently.

The player is the lowest object on screen, so it sorts last and is *exactly* the
object this mechanism hands slots to.

## 5. Chosen physical pair and rationale

**No fixed pair should be chosen, and this is the substantive finding.**

The engine deliberately does not bind the player to fixed hardware slots — the
protected invariant is that the player is *logical* object 0, and
`PLAYER_HW_MASK` is a **bitmask** precisely so the player can live in any
physical slots. Measured player masks over a representative run include
`00010000`, `00100000`, `00110000`, `01100000`, `11000000` — the pair moves.

Pinning a pair (e.g. hardware 0 and 1) would:

* fight the sorted-index→slot mapping, which is 1:1 by construction;
* require the scheduler to reject that pair for any earlier object whose
  `ownerY + 24` overlaps a **dynamic** deadline (the player's Y moves 55..237),
  where every other slot constraint in the engine is static;
* gain nothing, because the measurement below shows nothing is ever denied a
  slot by the player.

The correct "pair" is therefore *whichever two slots the scheduler assigns*, and
the existing `SLOT_FREE_RASTER` rule is what makes them safe.

## 6. Derived player handoff deadline

Sprite DMA for a sprite at Y begins on the raster line before display, so the
programming deadline is `playerY − 1`; the engine's scheduler uses a
conservative `playerY − 12` as the batch raster, giving 11 lines of built-in
slack, and requires the previous owner to be finished by `ownerY + 24`.

**Measured worst case, forced contention (9 enemies above the player, 468
handoff samples): minimum margin 63 raster lines** between the batch completing
and the player's sprite DMA. That is not marginal — it is an order of magnitude
more slack than needed.

## 7. Earlier-owner reuse rules — measured, both ways

**Representative Level 1, 2-layer, 600 frames:**

| measure | value |
|---|---|
| batches per frame | **0 on 355 frames, 1 on 1 frame** |
| frames where the player came via a batch | **0** |
| **early reuses of a player slot** | **0** |
| `RENDER_COUNT` distribution | 2:85, 3:44, 4:25, 5:39, 6:51, 7:14, **8:98** |
| player layers presented | 2 on 354 frames |

The reuse mux **essentially never engages**: the sorted list rarely exceeds 8, so
no object is ever denied a slot by the player holding one. `RENDER_COUNT` does
reach 8 on 28% of frames — but those are eight *simultaneous* initial owners,
not a queue waiting for a slot. **There is no early-frame contention for a late
reservation to relieve.**

**Adversarial geometry — 9 enemies forced above the player (sorted 11 > 8), 250
frames:**

| measure | value |
|---|---|
| frames where the player came via a batch | **235 / 236** |
| **early reuses of a player slot** | **468** (= both slots, every frame) |
| `RENDER_COUNT` | **8 on 235 frames** — all 8 slots enemy-owned up top |
| player layers still presented | **2 on 234 frames** |
| worst handoff margin | **63 raster lines** |

When contention exists, the engine already does exactly the requested thing:
**8 sprites for enemies in the upper/middle playfield, two reclaimed for the
player near the player band, no object dropped, both layers guaranteed.**

That is the "effectively 8 above, then 6 general + 2 player at the bottom"
outcome the experiment set out to obtain — with no hidden cliff: no object was
dropped, `max_batches` never exceeded 1 in representative play and 4 under the
dense synthetic fixture.

### Reservation-induced rejections / deferrals

**Zero**, because there is no standing reservation to reject against. The only
constraint is the pre-existing `SLOT_FREE_RASTER` rule, which applies equally to
every object and is what makes the handoff safe in the first place.

## 8. Collision mapping

Unchanged and re-verified on the shipping build. The three-layer collision
solution carries over because `PLAYER_HW_MASK` is a *mask*, so a slot changing
hands mid-frame is already handled: `applyLiveRasterBatch` republishes the mask
from `BATCH_PLAYER_MASK` at the same instant it reprograms the slot, so
physical→logical mapping can never be stale.

| test (2-layer) | result |
|---|---|
| player hardware mask | `00000011` / moves with the scheduler — one logical entity |
| isolated player, false hits (200 frames) | **0** |
| `$D01E` gate open, disjoint layer art | **0 / 120** |
| real enemy overlap → hit | yes |
| real projectile overlap → hit | yes |
| distant enemy → false hit | **0 / 120** |
| lives lost for ONE hit | **exactly 1** |
| death → respawn states | 0 → 1 → 2 → 0 |
| worst case: layers forced to share every pixel | **0 false hits**, real hit still detected |

No stale previous-owner mapping was observed, and none is structurally possible:
the mask is republished with the slot.

## 9. `$D01C` ownership — hardened (the one code change this pass)

**Previously**: `applyLiveRasterBatch` published sprite mode as `eor #$ff` of the
whole register. A batch scheduled *before* `hudBorderHandoff` (raster 43) would
therefore have flipped the HUD score sprites to **multicolour mid-DMA**. I
flagged this as theoretical in the three-layer report; this pass makes it
structurally impossible.

**Now**: the value is resolved in **BUILD** into a new `BATCH_MODE_MASK` table,
alongside the existing `BATCH_PLAYER_MASK` / `BATCH_X_MSB_MASK`:

```asm
    lda SCHED_PLAYER_MASK
    eor #$ff                                // gameplay MC, player layers hires
    ldy SCHED_BATCH_LATEST                  // this batch's raster
    cpy #HUD_HANDOFF_COMPLETE_RASTER
    bcs !batchModeReady+                    // after the handoff: whole register is gameplay
    and #(($01 << HUD_SLOT_FIRST) - 1)      // before it: HUD block stays HIRES
!batchModeReady:
    sta BATCH_MODE_MASK,x
```

and the IRQ becomes a plain table read:

```asm
    lda BATCH_MODE_MASK,x
    sta SPRITE_MODE
```

Cost: BUILD-time only, plus **+3 cycles per batch** in the IRQ (not per
assignment). This is the "masked / per-slot ownership appropriate to the current
engine" the brief asked for: the IRQ no longer has to reason about who owns the
HUD slots, and no LIVE/handoff ordering can corrupt them.

Verified after the change: `$D01C` register check **0 violations / 120 samples**
(every player-owned slot hires, every other enabled slot multicolour), and the
measured scroll behaviour is unchanged (§10).

## 10. A/B measurements

**A = dynamic 2-layer (pre-pass). B = dynamic 2-layer + `$D01C` hardening
(shipping).** There is no third build because the late-reservation architecture
turned out to be the mechanism already under test (§4).

2400 frames, representative Level 1, identical frame-indexed input:

| metric | 1-layer ref | **A (before)** | **B (shipping)** | 3-layer ref |
|---|---|---|---|---|
| coarse advances | 150 | 150 | **150** | 132 |
| **frames per coarse** | **16.0** | **16.0** | **16.0** | 18.18 |
| stopped frames % | 50.0 | 50.0 | **50.1** | 55.8 |
| **longest scroll stop** | **2 f** | **2 f** | **2 f** | **61 f** |
| stop runs ≥ 8 frames | 0 | 0 | **0** | 7 |
| coarse admits | 151 | 151 | **151** | 133 |
| defer BEAM / CUTOFF | 0 / 0 | 0 / 0 | **0 / 0** | 29 / 91 |
| `COARSE_HOLD_MAX` | 0 | 1 | **1** | 60 |
| max sorted / batches | 8 / 0 | 9 / 1 | **9 / 1** | 10 / 1 |
| stop-run histogram | {1:1198, 2:1} | {1:1193, 2:4} | **{1:1192, 2:5}** | {…36,44,48,50,61} |

**The hardening changed nothing measurable** — B is statistically identical to A.
Both remain at the theoretical ideal (16.0 frames/row is 8 fine steps ×
`SCROLL_FRAME_DIVIDER` 2), with zero coarse deferrals of any reason.

50% "stopped" is the correct baseline, not a fault: with divider 2 the fine
offset advances every second frame.

## 11. Coarse-admission timing comparison

Raster line at `prepareBackgroundCoarse`, deadline **184**:

| build | median | **p90** | p99 | % past deadline |
|---|---|---|---|---|
| 1-layer | 128 | **155** | 201 | 3.5% |
| A — 2-layer before | 138 | **172** | 281 | 7.2% |
| **B — 2-layer shipping** | **132** | **163** | 251 | **4.8%** |
| 3-layer | 133 | **191** | 275 | 16.0% |

B sits comfortably inside the deadline with ~21 lines of p90 margin. The
A→B difference is within this probe's run-to-run variance (it samples every call,
including uncontended ones); the honest reading is that the hardening neither
helped nor hurt timing, which is what §10 independently confirms.

## 12. Scroll-stop comparison

Shipping 2-layer: **longest visible stop 2 frames** — the normal divider-2
cadence — with **zero** coarse deferrals over 2400 frames of representative play.
The 3-layer reference on the identical fixture stalls for **61 frames**. The
2-layer stop-run histogram remains **disjoint** from the 3-layer one.

## 13. Upper / middle sprite-capacity result

**Full 8-sprite capacity is preserved, and is demonstrably reclaimed for the
player when needed.** Under forced contention, `RENDER_COUNT` was **8** on 235
of 236 frames — all eight physical sprites owned by enemies in the upper/middle
playfield — while the player still received **both** layers via late batch
handoff, with no object dropped. `max_batches` stayed at 1 in representative
play and 4 under the dense synthetic fixture.

Nothing is permanently reserved, and no reservation-induced rejection exists.

## 14. Successful same-frame early reuses of player slots

| scenario | early reuses |
|---|---|
| representative Level 1 (600 frames) | **0** — no contention exists to reuse against |
| 9 enemies forced above the player (250 frames) | **468** = both player slots, every frame |

## 15. Reservation-induced rejections / deferrals

**Zero.** See §7 — there is no standing reservation, only the pre-existing
`SLOT_FREE_RASTER` rule that applies uniformly to all objects.

## 16. Player handoff worst margin

**63 raster lines** (minimum over 468 samples under forced contention). The
theoretical requirement is that programming completes before `playerY − 1`; the
scheduler targets `playerY − 12`.

## 17. HUD / pointer / scroller regression (shipping build B)

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | catchups | page A/B | coarse steps |
|---|---|---|---|---|---|---|---|---|---|
| ordinary | 1400 | **`[19656]`** | 0 | 0 | 8 | 1 | 2 | 760/640 | **87** (ideal 87.5) |
| aperture passive | 400 | **`[19656]`** | 0 | 0 | 8 | 1 | 1 | 224/176 | — |
| aperture dense | 400 | **`[19656]`** | 0 | 0 | 16 | 4 | 1194 | 208/192 | — |

* exact PAL `[19656]`, **0 service failures, 0 sprite-start misses**;
* Stage 5 edge mask: **0 body / 0 lastrow temporal diffs**, passive *and* dense;
* `$07F8`/`$2BF8` validated per frame by `check_raster_capture` — 0 mismatches,
  so no stale enemy pointer became a player layer and no player pointer leaked
  into an enemy; the Stage-4H pointer-race repair is untouched;
* page-aware fallback active, both screen pages exercised;
* HUD borrow/handoff intact; score sprites stable; `$D01C` 0 violations;
* double-buffered scroller, lifecycle/high-score repair and the canonical
  Level 1 JSON pipeline all untouched — no scroller code was modified;
* all scroll steps single decrements, `all_steps_single_decrement: true`.

## 18. Synthetic boundary results

| case | result |
|---|---|
| enemy occupying a future player slot shortly before handoff | **468 occurrences, all clean**, worst margin 63 lines |
| multiple enemies near player Y | player keeps 2 layers; `PLAYER_BUNDLE_SHORT` 0 |
| lower-screen projectile pressure | covered by representative play (bullets present in stall samples) |
| dense reference | `[19656]`, 0/0, max batches 4 — reference only |
| aperture dense/passive | 0/0 temporal diffs |
| player at upper / lower movement bound | previously verified: 2 layers at both bounds |
| death / respawn | lifecycle loop 5/5, 80/80 checks, 0 failures |

Distinguishing supported from impossible: the 9-enemies-above fixture is
deliberately beyond normal Level 1 (waves are five enemies) and is a *capability*
demonstration, not a supported-gameplay claim. The `dense` and `y199` fixtures
remain reference-only and do not override the representative result.

## 19. Verdict

**Late-frame reservation as a capability: GREEN — and already implemented.**
The LIVE reuse batch satisfies every requirement in the brief, engages
automatically under contention, guarantees both player layers, and does so with
63 lines of margin while keeping all 8 sprites available above.

**Building a separate dedicated late-reservation subsystem: AMBER → do not
build.** Evidence:

1. **No capacity benefit** — already achieved adaptively (§7, §13).
2. **No timing benefit** — the batch path is the *cheap* path (+48 cycles)
   versus the initial-snapshot path (+215). Routing the player through it more
   often would help only in the ≤8-object case, where…
3. **…there is provably nothing to relieve** — 0 batches and 0 early reuses on
   355 of 356 representative frames.
4. **It would add real risk** — forcing a late handoff at low object counts
   requires a slot that no initial object occupies, and `applyLiveRasterBatch`
   deliberately does **not** publish `$D015`; batched slots rely on being
   `< RENDER_COUNT`. Making that work means adding enable publication to the
   time-critical IRQ, in the code with a documented pointer-race history, for
   zero measured gain.

This matches the brief's own AMBER criterion: *"prefer the simpler current
dynamic 2-layer architecture unless the guarantee has another compelling
benefit."* It does not.

### Analytical estimate: permanent reservation of two slots (not implemented)

Asked for completeness. It would remove both player entries from the plan
entirely, saving roughly **580 cycles** pre-coarse (~9 raster lines) — more than
the late handoff could. But it would leave only **6** physical sprites for
everything else at all times, and the measurement shows all 8 are genuinely in
simultaneous use on **28%** of representative frames (`RENDER_COUNT = 8`). It
would therefore trade real upper-screen capacity for margin that is not
currently needed. **Not recommended, and not implemented** — consistent with the
brief's instruction not to pivot to it.

## 20. Recommended production architecture

**Keep the current dynamic 2-layer player**, now with the `$D01C` hardening.

If pre-coarse margin ever needs recovering, the evidence points somewhere much
cheaper and safer than a new ownership model: **specialise the initial-snapshot
path for layer > 0**. Because a layer is co-located with layer 0 by
construction, X / X_MSB / Y are known-identical to the previous plan entry, the
straddler/clip test can never apply to the player, and the pointer/colour are
overwritten immediately afterwards anyway. That targets the +215 that dominates
the regression, in one contained routine, with no change to ownership, enable,
pointer publication or collision. It is **not** implemented here — it is
unrelated to the reservation question and current margin is ample (§11) — but it
is the right first move if the budget is ever wanted back.

## 21. Branch configuration left for manual testing

```asm
.const PLAYER_LAYER_COUNT = 2      // dynamic 2-layer, the known-good architecture
```

`build/shooter.prg` hashes `67c5965de6e2e6cc6e02cd710044caaaa7464db2d550ff4273ffc4961de566cd`
— identical to the tested variant — and `build/shooter.d64` was rebuilt to match.
Layer count is a one-line change (1, 2 or 3); commenting out
`OPT_THREE_LAYER_PLAYER` still restores the original single-sprite baseline.

The branch is **not** left in a knowingly worse experimental state: the only
engine change retained is the `$D01C` hardening, which is strictly safer and
measurably free.

## 22. Build / test artifact cleanup and final disk usage

* **`build/`: 304 KB, 4 files** (`shooter.prg`, `shooter.d64`, `main.vs`,
  `main.sym`) — unchanged in shape; no per-run or per-configuration files.
* **Scratch: 584 KB**, entirely outside the repository.
* **Cleaned**: every emulator capture directory (peak ~70 MB each, deleted
  immediately after analysis by `run_regression_suite.sh`), the three-variant
  build directory (192 KB), screenshot and lifecycle scratch, the temporary
  comparison shell scripts, `/tmp/shooter-charset.bin` and the layer-variant
  source backup.
* **Deliberately retained**: the small JSON summaries that are the evidence
  behind this report's tables — `attr-{1,2}.json` (cycle attribution),
  `own-2*.json` (slot ownership), `final-stop-2.json`, `final-deadline-2.json`,
  `cmp-play-*.json` — plus a couple of 40 KB PRG copies for A/B reference.
* `tools/build_layer_variant.sh` builds into a fixed scratch dir and restores
  `src/main.asm` via a shell trap, so a failed run cannot strand the tree.
* No VICE processes left running. All instances launched directly via
  `subprocess.Popen` — **never `open -a`** — so nothing stole keyboard focus.

## 23. Manual playtest checklist

1. Build and run. The ship shows **two** hires colours — light-blue hull, yellow
   spine.
2. **Scrolling.** Play a normal Level 1 run through several five-enemy waves.
   Terrain should scroll smoothly and continuously, with no half-second freezes.
   This should be unchanged from your last 2-layer playtest — the goal of this
   pass was to find margin, not to fix behaviour.
3. **Score HUD.** Watch the top border closely during busy waves, especially as
   enemies reach the lower screen. The six digits must stay green hires and
   rock-steady — this is the specific thing the `$D01C` hardening protects.
4. **Heavy lower-screen pressure.** Let a wave descend to the player's level
   while firing. Both player layers must stay co-located; no colour or mode
   flicker on the ship.
5. **Death and respawn.** Take a hit: single-sprite explosion, blink, then both
   layers return.
6. **One hit, one life.**
7. **Enemies unchanged** — enemies and turrets stay multicolour; only the player
   is hires.
8. **Stage wrap.** Play until the level wraps and confirm scrolling stays clean.

**Branch `experimental-three-layer-player`, left at 2 layers. Not committed,
merged, tagged or pushed.**
