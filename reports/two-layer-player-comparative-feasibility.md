# 19656 — Two-Layer Hires Player: Comparative Feasibility

**Verdict for two layers: GREEN.** Under the representative Level 1 workload, a
two-layer hires player is **indistinguishable from a single sprite**: ideal
coarse cadence (16.0 frames per row), longest visible scroll stop 2 frames, zero
coarse deferrals. The three-layer build on the *same* fixture stalls the terrain
for up to **61 consecutive frames**. **The third layer is the cliff.**

**Recommendation: adopt two hires layers as the production player sprite budget.**
The branch is left configured at `PLAYER_LAYER_COUNT = 2` for immediate manual
playtesting.

---

## 1. Starting branch / HEAD / worktree

Branch **`experimental-three-layer-player`**, HEAD **`e94ccf5`** — still no
commits on the branch. The worktree carried the three-layer player plus the
Level 1 five-enemy rebalance, both intact.

| build | SHA-256 |
|---|---|
| 1-layer variant | `9f0301300e68223420e0d40b85ea01ca262d6c45902516fe74946dbf2da9cf4d` |
| **2-layer variant (branch is left here)** | `29e46b78c33545d7356759038faacd7a80832332a0a073618e08971a89f42253` |
| 3-layer variant | `68ddd80be694727bcae276bde596a2df050fb7279302be78948a6dcfc2a80edc` |

`build/shooter.prg` now hashes `29e46b78…` — byte-identical to the tested
2-layer variant, so what you playtest is exactly what was measured.

## 2. Layer-count selection implementation

`PLAYER_LAYER_COUNT` (1–3) is now the **only** difference between the three
comparison builds — there is one implementation, not three.

* `playerLayerEmit` unrolls `.for (var layer = 1; layer < PLAYER_LAYER_COUNT; layer++)`,
  so the 1-layer build emits nothing extra and costs nothing;
* `playerLayerSprite` is `.fill PLAYER_LAYER_COUNT, PLAYER_LAYER_PTR + i` and the
  colour table is sized to match, with an assembler guard;
* a guard rejects any count outside 1–3.

Two deliberate controls:

1. **1 layer still goes through the experimental path** (a one-member bundle),
   so the comparison measures layer *count*, not the experimental renderer
   versus the original one.
2. **All three bitmaps stay assembled** at `$2c00` in every build, so the three
   configurations have an **identical memory footprint** and differ only in how
   many layers the renderer publishes.

The refactor was verified **byte-identical at 3 layers** against the
pre-refactor build (`1ad122ee…`), proving the parameterisation itself changed
nothing.

Everything the three-layer experiment proved is preserved at 2 layers: one
logical player object, renderer-expanded into an atomic co-located bundle,
independent hires pointers/colours, normal render-plan and scheduler ownership,
no direct VIC hack, no permanent hardware-sprite reservation.

## 3. Level 1 was not weakened

Confirmed unchanged and used for every measurement in this report:

| property | value |
|---|---|
| wave triggers | 53, **every one five-enemy** |
| wave definitions | 33 distinct (attack, enemyType) pairs |
| attacks used | 12 of 12; enemy types 4 of 4 |
| trigger spacing | alternating 8/7 rows = exactly 120 frames authored |
| turrets | 8 (`TURRET_TOTAL = 8`), cluster reduced to rows 345 / 337 |
| stage | 105 metatile rows (420 logical), divider 2, palette 12/15/11 |
| pipeline | canonical `level.json` → generated ASM |

`git diff` on `src/generated/level1/` shows only the two files the rebalance
changed, and no level file was touched in this pass.

## 4. How the manual three-layer symptom was reproduced

**The previous automation was not wrong — it was measuring the wrong thing.**

`frame_cycle_deltas [19656]` measures the **presented frame period**, and with a
per-physical-frame breakpoint it is exact *by construction*. A scroll stop is
**not a dropped frame**: the machine keeps presenting flawless PAL frames while
the **terrain stops moving**, because coarse-scroll admission is being deferred.
No existing metric looked at terrain motion over time.

The new probe (`tools/vice_scroll_stop_compare.py`) measures what the eye sees:
it samples `(SCROLL_FINE, SCROLL_ROW)` every physical frame and counts
**consecutive frames in which that pair does not change**. Input is a
deterministic, frame-indexed movement + burst-fire pattern, so all three
configurations are driven identically.

That reproduced the symptom on the first calibration run: with 3 layers, a
**47-frame** freeze in 900 frames; over 2400 frames, **61 frames** — about 1.2
seconds of motionless terrain, which is exactly "heavy scroll stops".

## 5. Test conditions (identical for 1 / 2 / 3)

| | |
|---|---|
| level | representative Level 1, unmodified |
| duration | 2400 physical frames (~48 s, ~11 five-enemy waves) |
| input | deterministic frame-indexed: fire for 14 of every 24 frames; movement cycling LEFT/RIGHT/LEFT/UP/RIGHT/DOWN every 45 frames |
| lives | 255 (long run) — **combat, collision, death and respawn stay live** |
| start | normal new game from the level origin |
| sampling | every physical frame, one 3-byte read |

Burst fire rather than held fire is deliberate: held fire destroys turrets and
has invalidated "passive symptom" captures in this project before.

## 6. Side-by-side measurements

2400 frames, identical fixture:

| metric | 1-layer | **2-layer** | 3-layer |
|---|---|---|---|
| coarse-scroll advances | 150 | **150** | **132** |
| frames per coarse step | **16.0** | **16.0** | **18.18** |
| scroll state changes | 1199 | 1197 | 1082 |
| stopped frames (%) | 50.0 | **50.0** | **55.8** |
| **longest visible stop** | **2 f** | **2 f** | **61 f** |
| stop runs ≥ 4 frames | 0 | 0 | **9** |
| stop runs ≥ 8 frames | 0 | 0 | **7** |
| stop runs ≥ 16 frames | 0 | 0 | **5** |
| coarse admits | 151 | 151 | 133 |
| coarse defer — BEAM (reason 2) | **0** | **0** | **29** |
| coarse defer — CUTOFF (reason 3) | **0** | **0** | **91** |
| `COARSE_HOLD_MAX` | 0 | 1 | **60** |
| max sorted objects | 8 | 9 | 10 |
| max batches | 0 | 1 | 1 |
| catchups / replays | 1 / 1 | 1 / 3 | 1 / 3 |
| `PLAYER_BUNDLE_SHORT` | 0 | **0** | 0 |

**50% "stopped" is the correct baseline, not a fault**: with
`SCROLL_FRAME_DIVIDER = 2` the fine offset advances every second frame, so half
of all frames legitimately repeat the previous state.

### The distribution is the finding

```
1-layer  stop-run histogram : {1: 1198, 2: 1}
2-layer  stop-run histogram : {1: 1193, 2: 4}
3-layer  stop-run histogram : {1: ..., 3:1, 4:1, 6:1, 7:3, 8:1, 12:1, 36:1, 44:1, 48:1, 50:1, 61:1}
```

1-layer and 2-layer are **pure divider-2 cadence with no stalls at all**. Their
histograms are **disjoint** from the 3-layer one, which contains runs of 36, 44,
48, 50 and 61 frames. This is not a gradual degradation across layer counts —
it is a cliff between 2 and 3.

## 7. Longest scroll stop

| configuration | longest visible stop |
|---|---|
| 1 layer | **2 frames** (normal cadence) |
| **2 layers** | **2 frames** (normal cadence) |
| 3 layers | **61 frames ≈ 1.2 seconds** |

## 8. Coarse-scroll cadence

Ideal is 16.0 frames per logical row (8 fine steps × divider 2).

| configuration | frames/coarse, play fixture | coarse steps, 1400-frame `ordinary` capture |
|---|---|---|
| 1 layer | 16.0 | — |
| **2 layers** | **16.0** | **87** (ideal is 87.5) |
| 3 layers | 18.18 | **80** |

Two layers restores the cadence to the theoretical ideal.

## 9. Sprite / batch pressure — and why this is *not* a capacity problem

The stalls happen at **low** sprite load. Worst 3-layer events:

| frame | stall | sorted | batches | active objects | turret pressure | player layers |
|---|---|---|---|---|---|---|
| 2212 | **61** | 8 | 0 | 7 | 0 | 3 |
| 817 | **50** | 8 | 0 | 7 | 0 | 3 |
| 2017 | **48** | 8 | 0 | 7 | 0 | 3 |
| 1773 | **44** | 8 | 0 | 7 | 0 | 3 |

Eight sorted objects, **zero** reuse batches, no turret pressure. There is no
sprite-capacity failure: `PLAYER_BUNDLE_SHORT` is **0** and the player holds all
3 layers throughout the stalls. Max batches never exceeds 1 in any configuration.

**The cost is CPU time in the main loop, not hardware sprites.** Note also that
`RENDER_COUNT` saturates at 8 in all the stall samples: three player layers plus
a five-enemy wave plus a projectile fills the initial snapshot.

## 10. Deadline margins — the direct causal measurement

Coarse admission requires `RASTER < BG_COARSE_LATEST_START (184)` at the
`prepareBackgroundCoarse` gate. Raster line at that call, 400 samples each:

| configuration | min | median | mean | **p90** | p99 | max | % past 184 |
|---|---|---|---|---|---|---|---|
| 1 layer | 82 | 128 | 123.4 | **155** | 201 | 275 | **3.5%** |
| **2 layers** | 90 | 138 | 136.3 | **172** | 281 | 290 | **7.2%** |
| 3 layers | 19 | 133 | 137.7 | **191** | 275 | 294 | **16.0%** |

The p90 walks **155 → 172 → 191**, and only at three layers does it cross the
184 deadline. Each layer adds main-loop work *ahead of* that call — one more
entry for the insertion sort, one more plan entry to snapshot, one more slot to
mask — pushing the coarse decision later in the frame until it routinely misses.
That is the whole mechanism, and it matches the deferral split exactly (reason 3
`CUTOFF` = 91 of 120 deferrals).

Player-bundle deadline margin itself is unchanged and healthy: the previous pass
measured **6 raster lines** at both 1 and 3 layers, with all layers installed by
a single batch. The bundle was never the problem.

## 11. Collision results (2 layers)

Full collision suite on the 2-layer build:

| test | result |
|---|---|
| player hardware mask | `00000011` — 2 slots, one logical entity |
| isolated player, false hits over 200 frames | **0** |
| lives lost while isolated | **0** |
| `$D01E` gate open (disjoint layer art) | **0 / 120** — layers never self-collide |
| real enemy overlap → hit | **yes** |
| real projectile overlap → hit | **yes** |
| distant enemy → false hit | **0 / 120** |
| lives lost for ONE hit | **exactly 1** — no duplicated damage |
| death states seen | 0 → 1 → 2 → 0 |
| worst case: layers forced to share every pixel | gate open 38/150, **0 false hits**, real hit still detected |

The three-layer collision solution carries over unchanged: `PLAYER_HW_MASK` is a
mask rather than a slot index, so accumulating its bits is all that is needed,
and the authoritative decision remains the software overlap scan. Nothing was
redesigned.

## 12. HUD / pointer / scroller regression (2 layers)

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | catchups | replay | page A/B | coarse steps |
|---|---|---|---|---|---|---|---|---|---|---|
| ordinary | 1400 | **`[19656]`** | 0 | 0 | 8 | 1 | 2 | 1 | 760/640 | **87** |
| dense *(ref)* | 900 | **`[19656]`** | 0 | 0 | 16 | 4 | 2694 | 450 | 452/448 | — |
| y199 *(ref)* | 400 | **`[19656]`** | 0 | 0 | 9 | 1 | 0 | 12 | 400/0 | 6 |
| stage wrap | 1200 | **`[19656]`** | 0 | 0 | 8 | 0 | 0 | 7 | 605/595 | 74, **1 wrap** |
| aperture passive | 400 | **`[19656]`** | 0 | 0 | 8 | 1 | 1 | 0 | 208/192 | — |
| aperture dense | 400 | **`[19656]`** | 0 | 0 | 16 | 4 | 1194 | 200 | 208/192 | — |

* exact PAL `[19656]`, **0 service failures, 0 sprite-start misses everywhere**;
* Stage 5 edge masking: **0 body / 0 lastrow temporal diffs**, passive *and* dense;
* page-aware fallback active, both pages exercised, stage wrap exercised;
* `$07F8`/`$2BF8` publication validated per frame by `check_raster_capture`
  across 4700 frames with 0 mismatches;
* HUD borrow/handoff intact — no permanent sprite reservation;
* lifecycle + high-score fix: **5/5 loops, 80/80 checks, 0 failures**, including
  death/respawn, GAME OVER → initials → menu → new game, correct stage origin
  and 24-bit high-score rendering;
* `$D01C` hires correctness: **0 violations / 120 samples**;
* two clearly distinguishable hires colours confirmed in pixels — light blue
  hull (28 px) and yellow spine.

The `dense` and `y199` synthetic fixtures are **reference only**. `y199` still
publishes no page-B frames at 2 layers (6 coarse steps vs 12 on the single-layer
baseline); it parks 8 enemies inside the player's non-recyclable band and is
over the capacity envelope by construction. It does **not** override the
representative Level 1 result. The accepted turret cosmetic flicker was not
reopened.

## 13. Why previous automation understated the manual problem

Determined, and demonstrated on the *same* build and *same* level in this
session. Old-style `ordinary` capture, three-layer build:

```
frame_cycle_deltas   [19656]      <- exact PAL
service_failure_count      0
sprite_start_miss_count    0
catchups 2   replay_frames 11
coarse_steps 80 / 1400 frames
```

**Every old metric is green.** The identical build, under representative play,
freezes the terrain for 61 consecutive frames.

Three reasons, in order of importance:

1. **The metrics measured frame *presentation*, not terrain *motion*.** With a
   per-physical-frame breakpoint, `frame_cycle_deltas [19656]` is exact by
   construction and can never report a scroll stop. Service failures and
   sprite-start misses are raster-servicing health, which stays perfect while
   the scroll is deferred — deferral is the scroller working *as designed*, just
   not advancing.
2. **The one number that could have shown it was an aggregate.**
   `coarse_steps 80` against an ideal 87.5 is a 9% shortfall that reads as minor
   — but those 7 missing steps are not spread evenly, they are **concentrated
   into five freezes of 36–61 frames**. The aggregate hid the distribution.
   Only a run-length measurement separates "slightly slow" from "visibly
   stopping", and nothing measured run length.
3. **Fixture realism was a secondary factor, not the main one.** The synthetic
   `dense`/`y199` fixtures move the player to unrepresentative positions, and
   the old `ordinary` capture holds fire continuously. But the decisive gap is
   (1) and (2): the *same* `ordinary` capture on the 3-layer build was already
   sitting at 80 coarse steps and reported green anyway.

A fourth, smaller point found along the way: my own `PLAYER_BUNDLE_SHORT`
counter was over-reporting. It counted the deliberate single-sprite
death/respawn presentation as a bundle shortfall (897 "failures" at 2 layers).
`playerLayerAudit` now returns early when `PLAYER_STATE != 0`; the true count is
**0** in every configuration.

## 14. Assessment for two layers — GREEN

Two hires layers restore representative Level 1 scrolling completely:

* coarse cadence **16.0 frames/row — the theoretical ideal**, matching 1 layer;
* longest visible scroll stop **2 frames**, i.e. the normal divider-2 cadence;
* **zero** coarse deferrals of any reason;
* stop-run histogram statistically indistinguishable from a single sprite;
* exact PAL, 0 service failures, 0 sprite-start misses across six captures;
* collision, HUD, pointer publication, edge masking, lifecycle all intact;
* no permanent sprite reservation, no bundle allocation failures;
* p90 coarse-admission raster 172, comfortably inside the 184 deadline.

The one honest caveat: 2 layers sits at **7.2%** of coarse calls past the
deadline versus 3.5% for a single sprite, and its p90 margin is 12 lines rather
than 29. That headroom reduction never produced a stall in 2400 frames of
representative play, but it means a future feature that adds comparable
main-loop work before `prepareBackgroundCoarse` would eat into it.

## 15. Comparison with one and three layers

| | 1 layer | **2 layers** | 3 layers |
|---|---|---|---|
| visible scrolling | clean | **clean** | **heavy stops** |
| longest stop | 2 f | **2 f** | 61 f |
| frames/coarse | 16.0 | **16.0** | 18.18 |
| coarse deferrals | 0 | **0** | 120 |
| p90 admission raster (deadline 184) | 155 | **172** | 191 |
| independent hires colours | 1 | **2** | 3 |
| verdict | baseline | **GREEN** | **RED for production** |

Per the decision criteria: this is the "**2 layers is clean**" outcome. Three
layers should **not** be optimised further in this pass — and the evidence says
the third layer genuinely was the root cause, not the Level 1 workload: the same
level at 1 and 2 layers scrolls at the ideal cadence with zero deferrals.

## 16. Recommendation for production player layer count

**Two hires layers.** It delivers the actual goal of the experiment — independent
hires colours at full horizontal resolution — at zero measured scrolling cost,
and it keeps a documented capacity margin (one more object tolerated in the
player's band than three layers allowed: 6 rather than 5).

If a third colour later becomes important, the target would be the
**coarse-admission deadline**, not the sprite budget: the fix is to move work
out from in front of `prepareBackgroundCoarse` (or raise
`BG_COARSE_LATEST_START` where the predecode HIT guarantee already permits it),
because the failure is CPU scheduling and not sprite capacity. That is a
separate, deliberate investigation and is explicitly **not** started here.

## 17. Branch left configured for manual test

`src/main.asm` is left at:

```asm
// LEFT AT 2 for manual playtesting: the 1/2/3 comparison showed the third layer
// is the cliff. ...
.const PLAYER_LAYER_COUNT = 2
```

`build/shooter.prg` hashes `29e46b78c33545d7356759038faacd7a80832332a0a073618e08971a89f42253`
— identical to the measured 2-layer variant. `build/shooter.d64` was rebuilt to
match. Switching configurations is a one-line edit of that constant (1, 2 or 3);
commenting out `OPT_THREE_LAYER_PLAYER` still returns the original single-sprite
baseline byte-for-byte.

## 18. Build / test artifact cleanup and final disk usage

* **`build/`: 304 KB, 4 files** (`shooter.prg`, `shooter.d64`, `main.vs`,
  `main.sym`) — unchanged in shape, no per-run or per-configuration files.
* **Scratch: 552 KB**, outside the repository.
* **Cleaned automatically**: every emulator capture directory (peak ~70 MB per
  capture; `run_regression_suite.sh` deletes each immediately after analysing
  it), the three-variant build directory (192 KB), screenshot scratch, lifecycle
  scratch, `/tmp/shooter-charset.bin` and the layer-variant source backup.
* **Deliberately retained**: the small JSON summaries for the 1/2/3 comparison
  (`cmp-play-*.json`, `deadline-*.json`) and a couple of 40 KB PRG copies — these
  are the evidence behind this report's tables and are the only things worth
  keeping.
* `tools/build_layer_variant.sh` builds each variant into a **fixed** scratch
  directory and always restores `src/main.asm` via a shell trap, so a failed run
  cannot leave the tree on the wrong layer count.
* No VICE processes left running. All instances launched directly via
  `subprocess.Popen` / background `&` — **never `open -a`** — so nothing stole
  keyboard focus.

## 19. Manual playtest checklist

1. Build and run. The ship should show **two** hires colours: a light-blue hull
   outline and a yellow spine.
2. **The headline check — scrolling.** Play a normal Level 1 run for a minute or
   two through several five-enemy waves. The terrain should scroll **smoothly and
   continuously**. There should be **no** moments where it visibly freezes for
   half a second or more. That is the whole question this pass exists to answer.
3. Compare directly if you want the contrast: set `PLAYER_LAYER_COUNT = 3`,
   rebuild, and play the same stretch — the freezes should be obvious. Then set
   it back to 2.
4. **Co-location.** Move fast in all directions and at the screen edges; the two
   layers must never separate or lag by a frame.
5. **Muzzle flash.** Hold fire — the hull should flash red while the yellow
   spine stays put.
6. **Death and respawn.** Take a hit: the explosion plays as the normal
   single-sprite animation, the blink works, and both layers return on respawn.
7. **One hit, one life.** Confirm a single collision costs exactly one life.
8. **HUD.** The six-digit score in the top border should stay rock-steady under
   heavy waves, with no flicker.
9. **Turret cluster.** Only the lower two turrets at the cluster.
10. **Longer session.** Play until the stage wraps to confirm scrolling stays
    clean across the wrap.

**Branch `experimental-three-layer-player`, left at 2 layers. Not committed,
merged, tagged or pushed.**
