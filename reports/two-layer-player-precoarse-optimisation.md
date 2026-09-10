# 19656 — Two-Layer Player Pre-Coarse Optimisation Pass

**Verdict: GREEN.** Two local, provable optimisations recover **228 of the 523
cycles** (**44%**) that the second player layer costs the pre-coarse path under
representative Level 1 — with **zero** behavioural change: 0 co-location
violations, 0 collision changes, 0 deferrals, longest scroll stop still 2 frames,
exact PAL and clean mux/scroller regressions throughout.

The most important result in this report is not a cycle count, though. It is
that **the first attribution baseline was measured on an empty scene**, and
would have led to the wrong conclusion (§2.1). That is now fixed in the tooling.

---

## 1. Starting branch / HEAD / worktree

Branch **`experimental-three-layer-player`**, HEAD **`e94ccf5`**, no commits.
`PLAYER_LAYER_COUNT = 2`, `$D01C` hardening from the previous pass present,
Level 1 (53 five-enemy waves, 8 turrets, canonical JSON, divider 2) untouched.

| build | SHA-256 |
|---|---|
| 2-layer **before** this pass | `67c5965de6e2e6cc6e02cd710044caaaa7464db2d550ff4273ffc4961de566cd` |
| **2-layer optimised (branch left here)** | `708165f33d84daed02b6974109f4196f18a1ce3caee2cf68dcfe3c3205d8a8c4` |
| 1-layer reference (before) | `a9346ca5d63c9cfa9c71761b1a94666a415f4ca887357317393cbadcb99c1942` |

`build/shooter.prg` hashes `708165f3…`, identical to the tested variant.

## 2. Fresh pre-change baseline

Reproduced on the exact current branch, **three runs per configuration**. The
attribution probe proved highly repeatable — identical medians across all three
runs.

| segment | 1-layer | 2-layer | delta |
|---|---:|---:|---:|
| `buildSortedObjectList` | 330 | 353 | +23 |
| `sortObjectsByY` | 41 | 127 | +86 |
| `buildInitialSpriteSnapshot` | 296 | 511 | +215 |
| `buildBatchSpriteSchedule` | 260 | 308 | +48 |
| **total** | | | **+372** |

Pre-coarse total 4624 → 5029. Gate raster median 96 → 104, p90 157 → 167.
Deadline probe (3 runs): 1-layer p90 160–163 / %late 5.2–5.5; 2-layer p90
163–171 / %late 4.8–7.2.

This matched the previous report almost exactly — which is precisely why it was
misleading.

### 2.1 The baseline was measured on an empty scene

After the first optimisation measured **zero** benefit, I dumped the actual
sorted list instead of trusting the model:

```
UNSORTED list at sortObjectsByY entry (packed entry : objectY):
  n=2  00:220  10:220
  n=2  00:220  10:220        <- SORTED_COUNT = 2, every frame
```

**`SORTED_COUNT = 2`: only the player's two layers. No enemies at all.** The
probe warmed up for 30 frames, but Level 1's first authored wave trigger is
~112 frames in. Every "representative" attribution number above — including the
`+372` carried forward from the previous report — describes a scene containing
nothing but the player.

That matters enormously for this pass: with no other objects in the list, there
is nothing for the sort to shift past, so the sort optimisation *cannot* help
and would have been wrongly rejected.

`tools/vice_precoarse_attribution.py` now takes `--warmup` (default 260) **and
records `sorted_count` in its output**, so a light scene can never again be
mistaken for a representative one.

| fixture | layer overhead | recovered |
|---|---|---|
| empty scene (`SORTED_COUNT` 2) | +372 | 73 (20%) |
| **busy scene (`SORTED_COUNT` 6, max 9)** | **+523** | **228 (44%)** |

Everything below uses the busy-scene fixture.

## 3. Exact redundant work identified

For a player layer > 0 the generic snapshot path performed, per entry:

* `jsr snapshotSpritePointer` — the straddler/clip decision. **Can never apply
  to the living player**: it triggers only below `GAMEPLAY_SPRITE_MIN_Y`, and
  the player's Y floor *is* `GAMEPLAY_SPRITE_MIN_Y`. Its one meaningful side
  effect is clearing the entry's clip shadow.
* `lda OBJECT_SPRITE,x / sta INITIAL_SPRITE,y` then
  `lda OBJECT_COLOUR,x / sta INITIAL_COLOUR,y` — **both immediately overwritten**
  by `playerLayerSnapshot`.
* `jsr playerLayerSnapshot` → `jsr playerLayerIndex` — **two nested jsr/rts
  pairs** (24 cycles of pure call overhead) plus a `PLAYER_STATE` test that is
  already guaranteed by `playerLayerEmit`.
* `ldx TEMP_OBJECT / ldy SNAPSHOT_INDEX` restores after the call.

Hand-counting one generic iteration gives ≈ 210 cycles, which matches the
measured +215 — confirming the model before any code was changed.

A second, separate redundancy was found in the sort (§6).

## 4. Snapshot specialisation (implemented)

The layer test is made **free** by restructuring the decode: for an ordinary
object the packed sorted byte *is* the object index (high nibble zero), so the
common path needs no masking at all.

```asm
!snapshotLoop:
    ldy SORTED_OBJECTS,x
    sty PLAYER_LAYER_TMP                    // keep the packed entry for the layer index
    tya
    and #SORTED_LAYER_MASK                  // layer nibble: 0 for every ordinary object
    bne !playerExtraLayer+                  // player layer > 0 -> specialised path
    // Layer 0: the packed byte IS the logical object index, so the common path
    // needs no masking and this test is free.
```

The specialised block is placed **out of line**, after the routine's `rts`, so
the common path pays nothing and the loop-back stays a short branch:

```asm
!playerExtraLayer:
    txa / clc / adc BUILD_PLAN / sta SNAPSHOT_INDEX / tay
    lda OBJECT_X                            // logical object 0 is permanently the player
    sta INITIAL_X,y
    lda OBJECT_X_MSB
    sta INITIAL_X_MSB,y
    lda OBJECT_Y
    sta INITIAL_Y,y
    lda #0
    sta CLIP_SHADOW_PTR,y                   // as snapshotSpritePointer's plain path would
    sta INITIAL_OBJECT,y                    // owner is logical object 0
    lda PLAYER_LAYER_TMP                    // layer index from the packed high nibble
    lsr / lsr / lsr / lsr
    tax
    lda playerLayerSprite,x
    sta INITIAL_SPRITE,y
    lda playerLayerColour,x
    sta INITIAL_COLOUR,y
    jmp !snapshotTail-
```

≈ 121 cycles against ≈ 210, with both nested `jsr`/`rts` pairs gone.

## 5. Invariants that make it safe

Each is either structurally guaranteed by existing code or explicitly enforced,
and each is documented in the source at the point it is relied on:

| invariant | why it holds |
|---|---|
| the entry is the player | the layer nibble is only ever non-zero for entries written by `playerLayerEmit`, which only ever writes object 0 |
| X / X-MSB / Y match layer 0 | **read from logical object 0 in the same frame** — co-location by construction, *not* by assuming plan adjacency |
| the clip/straddler decision cannot apply | the living player's Y floor *is* `GAMEPLAY_SPRITE_MIN_Y` (`updateObjects` refuses to move it higher); the clip path triggers only below that |
| the clip cache stays consistent | the specialised path reproduces `snapshotSpritePointer`'s plain-path shadow clear |
| the player is alive | `playerLayerEmit` emits extra layers only while `PLAYER_STATE == 0`, and nothing changes it between there and here — so the living-player test inside `playerLayerSnapshot` is not needed |
| `SORTED_OBJECTS` cannot overflow | sized `MAX_OBJECTS + PLAYER_LAYER_COUNT - 1`; unchanged |

### An assumption deliberately NOT relied on — and it would have been wrong

The brief suggested copying X/Y/MSB from the previous plan entry. I rejected it
on cost grounds (`lda INITIAL_X-1,y` is the same 9 cycles as `lda OBJECT_X`), and
the measurements then proved it would also have been **incorrect**: observed
player masks include **`10100000` — hardware slots 5 and 7, non-adjacent**. The
two layers do not always occupy adjacent plan entries, so a `y-1` shortcut would
have de-co-located the bundle. Reading object 0 directly is both free and safe.

## 6. Additional optimisation considered — and accepted

**Emit the extra player layers LAST in the unsorted list.**

`buildSortedObjectList` scans objects 0..15 and the player is object 0, so the
extra layer used to be written at index 1 — the **front** of the list. But the
list is unsorted and `sortObjectsByY` is an insertion sort, and the player has
the **highest Y** on screen, so entries belonging at the *end* of the sorted
order sat at the *front* of the input. Every subsequent enemy insertion then had
to shift past them: one extra shift per enemy per extra layer.

The extra layers are now appended after the whole scan, gated on a
`PLAYER_IN_SORTED` flag so they are only added when the player itself was
collected.

**The sorted result is provably identical.** The inner loop inserts an equal key
*after* existing equals (`beq !insert+`), so layer 0 still precedes layer 1, and
an enemy sharing the player's Y still lands after both. Only the amount of
shifting changes. Worked example:

```
old input [L0(220), L1(220), E1(100), E2(150)] -> 5 shifts -> [E1, E2, L0, L1]
new input [L0(220), E1(100), E2(150), L1(220)] -> 3 shifts -> [E1, E2, L0, L1]
```

## 7. Optimisations accepted / rejected

| optimisation | verdict | reason |
|---|---|---|
| specialised layer>0 snapshot | **accepted** | −96 cycles, invariants provable, 0 behavioural change |
| emit extra layers last | **accepted** | −156 in the sort for +24 in the list build = **net −132**; sorted output provably identical |
| copy X/Y/MSB from plan entry `y-1` | **rejected** | zero saving *and* incorrect — layers are not always plan-adjacent (`10100000`) |
| specialise layer 0's snapshot too | **rejected** | its redundancy exists in the 1-layer build too, so it is inside the baseline and does not close the 1→2 gap; out of this pass's scope |
| `buildBatchSpriteSchedule` (+48) | **not attempted** | the extra entry genuinely needs a `SLOT_FREE_RASTER` slot computed; no redundancy found, and the brief says not to chase all three |
| `PLAYER_LAYER_COUNT == 2` special-casing | **rejected** | would break 1/2/3 configurability for a few cycles; exactly the fragile cleverness the brief warns against |

## 8. Old / new per-routine cycle table (busy scene, 3 runs each)

| segment | 1L base | 2L base | **2L optimised** | Δ base | Δ opt | **saved** |
|---|---:|---:|---:|---:|---:|---:|
| `buildSortedObjectList` | 514 | 542 | 566 | +28 | +52 | **−24** |
| `sortObjectsByY` | 625 | 862 | **706** | +237 | +81 | **+156** |
| `buildInitialSpriteSnapshot` | 983 | 1193 | **1097** | +210 | +114 | **+96** |
| `buildBatchSpriteSchedule` | 404 | 452 | 452 | +48 | +48 | 0 |
| **layer-attributable total** | | | | **+523** | **+295** | **+228** |

**Controls** (layer-independent segments — if these moved, the scenes would not
be comparable): `planCoarseBulletSuppression` **32** and
`predecodeNextStageRow` **64** are *identical* across all three builds;
`updateTurretStream` 4024 / 4004 / 4059 (within 1%). Scene size: 1-layer median
5, 2-layer median 6 — exactly one more entry, as expected.

**Per-run variance is negligible**: `buildInitialSpriteSnapshot` gave the same
median in all three runs of every configuration; `sortObjectsByY` varied by at
most 12 cycles.

## 9. Total cycles recovered

**228 cycles** per frame, ≈ **3.6 raster lines** at 63 cycles/line.

## 10. Percentage of the 1→2-layer overhead recovered

**44%** (228 of 523). The 2-layer pre-coarse penalty drops from **+523 to +295**
cycles over the 1-layer reference.

## 11. 1-layer vs old-2-layer vs optimised-2-layer

| | 1-layer | 2-layer before | **2-layer optimised** |
|---|---:|---:|---:|
| layer-attributable pre-coarse cost | 0 (reference) | +523 | **+295** |
| `sortObjectsByY` | 625 | 862 | **706** |
| `buildInitialSpriteSnapshot` | 983 | 1193 | **1097** |
| whole pre-coarse median | 6921 | 7349 | **7217** |

The 1-layer implementation was **not** altered.

## 12. Coarse-admission p50 / p90 / p99

Empty-scene deadline probe, median of 3 runs, deadline 184:

| build | p50 | p90 | p99 | % past deadline |
|---|---:|---:|---:|---:|
| 1-layer | 128 | 162 | 224 | 5.5 |
| 2-layer before | 132 | 163 | 251 | 5.0 |
| **2-layer optimised** | **132** | **158** | **235** | **4.2** |

Busy-scene gate raster (from the attribution probe): 1-layer median 139 / p90
160; 2-layer before 149 / 170; optimised 147 / 175.

**Honest caveat:** these aggregate distributions are noisy — they are dominated
by `updateTurretStream` and by run-to-run variation in enemy population, both far
larger than 228 cycles. The p90 numbers move in *both* directions between runs
and should not be read as a precise gain. The per-segment measurement in §8 is
the high-confidence result; it is repeatable to within 12 cycles and has clean
controls. I am not claiming a coarse-admission improvement beyond "not worse".

## 13. Coarse deferrals and scroll stops

Representative Level 1, 2400 frames, same input fixture:

| metric | result |
|---|---|
| coarse advances | 150 |
| **frames per coarse** | **16.0** (the theoretical ideal) |
| **longest visible scroll stop** | **2 frames** (normal divider-2 cadence) |
| **stop runs ≥ 4 frames** | **0** |
| stop runs ≥ 8 frames | 0 |
| coarse deferrals — BEAM / CUTOFF | **0 / 0** |
| `COARSE_HOLD_MAX` | 1 |
| stop-run histogram | `{1: 1196, 2: 2}` |

Every requirement in the brief's "required visible-motion metrics" is met.

## 14. Player bundle / co-location proof

`tools/vice_player_colocation_check.py` (new) reads the **hardware** sprite
registers for every slot in `PLAYER_HW_MASK` and asserts they share X, Y and
X-MSB, while driving the player through fast movement in all directions:

| check | result |
|---|---|
| **co-location violations** | **0** over 322 alive frames |
| frames with distinct pointers per layer | **322 / 322** (`same_pointer_frames: 0`) |
| frames with distinct colours per layer | **322 / 322** |
| layers per frame | **min 2, max 2** |
| partial bundle while alive | **0** |
| `PLAYER_BUNDLE_SHORT` | **0** |
| masks observed | `00000011`, `00000110`, `00001100`, `00011000`, `00110000`, `01100000`, **`10100000`**, `11000000` |

No one-frame lag, no stale previous-owner data, no partial bundle. Death and
explosion retain the existing single-sprite presentation unchanged.

## 15. Collision

Unchanged; full suite re-run on the optimised build:

| test | result |
|---|---|
| player hardware mask | `00000011` — one logical entity |
| isolated player false hits (200 frames) | **0** |
| `$D01E` gate open, disjoint layer art | **0 / 120** |
| real enemy overlap → hit | yes |
| real projectile overlap → hit | yes |
| distant enemy → false hit | **0 / 120** |
| lives lost for ONE hit | **exactly 1** |
| death → respawn states | 0 → 1 → 2 → 0 |
| layers forced to share every pixel | **0 false hits**, real hit still detected |

## 16. HUD / `$D01C` / pointer publication

| check | result |
|---|---|
| `$D01C` register check | **0 violations / 120 samples** |
| `$D01C` hardening from the previous pass | retained unchanged |
| `$07F8` / `$2BF8` per-frame validation | **0 mismatches** across 4700 captured frames |
| HUD borrow / handoff | intact |
| score sprite stability | lifecycle loop clean |

## 17. Exact PAL and mux / scroller regression

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | catchups | replay | page A/B | coarse steps |
|---|---|---|---|---|---|---|---|---|---|---|
| ordinary | 1400 | **`[19656]`** | 0 | 0 | 8 | 1 | 2 | 1 | 772/628 | **87** (ideal 87.5) |
| dense *(ref)* | 900 | **`[19656]`** | 0 | 0 | 16 | 4 | 2694 | 450 | 452/448 | — |
| y199 *(ref)* | 400 | **`[19656]`** | 0 | 0 | 9 | 1 | 0 | 0 | 400/0 | — |
| stage wrap | 1200 | **`[19656]`** | 0 | 0 | 8 | 0 | 0 | 4 | 627/573 | 74, **1 wrap** |
| aperture passive | 400 | **`[19656]`** | 0 | 0 | 8 | 1 | 1 | 0 | 208/192 | — |
| aperture dense | 400 | **`[19656]`** | 0 | 0 | 16 | 4 | 1194 | 200 | 208/192 | — |

Stage 5 edge mask: **0 body / 0 lastrow temporal diffs**, passive *and* dense.
All scroll steps single decrements. Lifecycle / high-score loop: **5 / 5 loops,
80 / 80 checks, 0 failures**. `dense` and `y199` are unchanged from the 2-layer
baseline and remain reference-only.

### Memory-map change

The main code block grew past the `$1fc0` border-marker cap, so
`ENGINE_LOOKUP_SEGMENT` moved **`$1f60` → `$7300`** (the free hole above the
authored wave-trigger tables). That block is plain CPU-side lookup data — bit
masks, star row addresses, HUD proof tables — read only through absolute or
absolute-indexed addressing, with no alignment or VIC-bank constraint; it is
placed on a page boundary so no table straddles one. Resulting map has no
overlaps:

```
$080e-$1f9f  main code        (cap $1fc0)
$7100-$723d  wave-trigger tables
$7300-$735a  engine lookup tables
```

## 18. Verdict — GREEN

228 cycles (44% of the 1→2-layer overhead) recovered by two local, provable
changes, with **no behavioural regression of any kind**: co-location, collision,
HUD, pointer publication, `$D01C`, exact PAL, edge masking, lifecycle and visible
scroll motion are all unchanged or clean. Both changes make the intent clearer —
one removes work that was provably redundant, the other stops feeding an
insertion sort its worst-case input.

I am *not* claiming a measurable coarse-admission improvement (§12); the honest
claim is a repeatable 228-cycle reduction with clean controls, and no regression.

## 19. Branch configuration left for manual testing

```asm
.const PLAYER_LAYER_COUNT = 2      // dynamic 2-layer, optimised
```

`build/shooter.prg` hashes `708165f33d84daed02b6974109f4196f18a1ce3caee2cf68dcfe3c3205d8a8c4`,
identical to the tested variant; `build/shooter.d64` rebuilt to match. Level 1
untouched, `$D01C` hardening retained. Layer count remains a one-line change
(1, 2 or 3); commenting out `OPT_THREE_LAYER_PLAYER` still restores the original
single-sprite baseline. **No known-bad optimisation is left in the worktree** —
both changes measured positive on the representative fixture and were kept; the
two rejected ideas were never committed to the tree.

## 20. Build / test artifact cleanup and final disk usage

* **`build/`: 304 KB, 4 files** — unchanged in shape, no per-run files.
* **Scratch: 784 KB**, outside the repository.
* **Cleaned**: every emulator capture directory (peak ~70 MB each, deleted
  immediately after analysis), both layer-variant build directories, screenshot
  and lifecycle scratch, the temporary comparison shell scripts, the throwaway
  sorted-list dump script, `/tmp/shooter-charset.bin` and the layer-variant
  source backup.
* **Deliberately retained**: the JSON summaries behind this report's tables —
  `base-battr-*` / `opt-battr-*` (busy-scene attribution), `base-attr-*` /
  `opt-attr-*` (the empty-scene runs, kept as the evidence for §2.1),
  `base-dl-*` / `opt-dl-*` (deadline), `opt-stop.json`, `coloc-opt.json`.
* No VICE processes left running. All instances launched via direct
  `subprocess.Popen` — **never `open -a`** — so nothing stole keyboard focus.

## 21. Manual playtest checklist

1. Build and run: light-blue hull, yellow spine, two hires colours.
2. **Co-location under hard movement.** Waggle the stick fast in all directions
   and along every screen edge. The two layers must stay welded together — this
   is the specific thing the specialised snapshot path could have broken, and the
   automated check found 0 violations, but it is worth eyeballing.
3. **Scrolling.** Play through several five-enemy waves: smooth and continuous,
   no half-second freezes. Should be indistinguishable from your last playtest.
4. **Muzzle flash.** Hold fire — the hull flashes red, the yellow spine stays.
5. **Score HUD.** Steady green hires digits during busy waves.
6. **Death and respawn.** Single-sprite explosion, blink, both layers return.
7. **One hit, one life.**
8. **Enemies unchanged** — still multicolour; only the player is hires.
9. **Stage wrap.** Play until the level wraps; scrolling stays clean.

**Branch `experimental-three-layer-player`, left at 2 layers optimised. Not
committed, merged, tagged or pushed.**
