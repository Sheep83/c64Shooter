# Stable Top-Border Sprite HUD Proof — report

**Task:** 19656 / c64Shooter — prove the reclaimed display architecture can carry a
stable sprite-based HUD in the opened top border **without giving back any of the
~192 px clean scrolling terrain (raster 55..246)**, using **time-domain**
hardware-sprite ownership (HUD early in the frame → the *same* physical slots
returned to the gameplay multiplexer lower in the frame; **no permanent
reservation**).

**Verdict: GREEN.**

---

## 1. Branch / HEAD / starting status

- Branch `experimental-border-hud`, HEAD `44e735c` ("pre-architecture-teardown").
- Working tree at task start already carried the **open-border task** uncommitted
  (`M src/main.asm`, `M src/raster_scheduler.asm`, `+docs/full-200px-aperture-worklog.md`,
  `+reports/full-200px-gameplay-aperture-architectural-rework-report.md`). That work
  is the baseline this task builds on and is **not** committed here.
- No commit / push / add / tag / branch change was made (see §27).

## 2. Files changed by this task

| File | Change |
| --- | --- |
| `src/main.asm` | `#define HUD_PROOF_ENABLE` + `HUD_*` consts; `hudProof{Ptr,X,XMsb,Colour}` tables ($1f4b–$1f5a); `hudProofSprites` 4×64 B hires bitmaps ($2f00–$2ffe); `renderSprites` initial-write cap (`#if` block); `buildBatchSpriteSchedule` SLOT_FREE_RASTER floor (`#if` block); `hudBorderSetup` / `hudBorderHandoff` routines ($5864 / $58a1) with a `hudSlotReclaimed:` trace label. Every added block is `#if HUD_PROOF_ENABLE`-guarded. |
| `src/raster_scheduler.asm` | `RASTER_DISPLAY_LINE` = `HUD_HANDOFF_RASTER` under the guard; `rasterFrameReset` → `jsr hudBorderSetup`; `rasterDisplayHook` → `jsr hudBorderHandoff`; `borderOpenHook` slot-7 diagnostic marker guarded out under HUD_PROOF; `HUD_HO_RC` / `HUD_HO_MSB` IRQ scratch in the raster-state block. |
| `tools/check_raster_capture.py` | Merge `rasterInitialApplied` + `hudSlotReclaimed` trace events (beam-ordered) so a HUD frame shows the full `0..RENDER_COUNT-1` initial-slot set **and** the handoff re-application of each deferred slot is deadline-checked; defensive `span==0` guard on the pre-existing `rasterBatchMasksApplied` deadline path. |
| `tools/vice_scroll_test.py` | trace the new `hudSlotReclaimed` label. |
| `tools/vice_raster_cases.py` | trace the new `hudSlotReclaimed` label. |
| `docs/top-border-sprite-hud-proof-worklog.md` | design + measured results. |

No canonical authored Level-1 content was modified. All emulator fixtures are
scratch (`/private/tmp/.../scratchpad/`), RAM pokes only.

## 3. Starting geometry (from the open-border task)

- RSEL=0 gameplay; `rasterFrameReset` installs `$D011 = RASTER_DISPLAY_FINE | $10`
  (DEN=1, RSEL=0, YSCROL = presented fine) at line 1.
- `borderOpenHook` (@ raster 240) flips RSEL 0→1 @ ~raster 245 and 1→0 @ ~raster 250,
  dodging **both** border-close compares → top **and** bottom vertical border open
  into overscan every frame. `init` forces the `$3FFF/$39FF` idle g-byte to `$00`
  → the opened border renders as **solid `$D021` backdrop** (no ROM-char stripes).
- Clean scrolling **terrain** body: raster **55..246**, temporally flawless.
- Soft edges: ~4–6 px pop at rasters ~52–55 (top) / ~247–254 (bottom), once per
  coarse 7→0 cycle, **outside** the 55..246 aperture.
- Top-border region ~raster 16..51 = solid `$D021` → HUD canvas.
- Multiplex dispatcher events: FRAME (line 1), SPRITES (batches), **DISPLAY (a
  no-op since Phase 1.5)**, BORDER (line 240).
- `renderSprites` (main thread, ~raster 8–20) writes hardware slots
  `0..RENDER_COUNT-1` from LIVE `INITIAL_*` (Y-sorted ascending); sets
  `$D015 = SPRITE_ENABLE_MASK[RENDER_COUNT]`; records `PLAYER_HW_MASK`.
- Player = logical object 0, **not** hw-slot-pinned; by Y-sort rank it tends to a
  high slot.

## 4. HUD design and physical slots

**HUD owns hardware sprite slots 4, 5, 6, 7** (the high four).

Rationale — audited against the renderer: `renderSprites` writes initial slots in
**ascending Y-sort order**, so slot *k* holds the (k+1)-th sprite from the top of
the field, and its DMA is the (k+1)-th earliest. Choosing the **high** four slots
for the HUD means the *deferred* gameplay sprites are exactly ranks 4..7 — the
**highest-Y / latest-DMA** quartile, giving the largest possible margin between the
HUD→gameplay handoff and the first deferred sprite's DMA. The **topmost** gameplay
sprites (ranks 0..3, nearest the raster-55 aperture floor, earliest DMA) are
**never deferred** — the frame-top `renderSprites` write still programs them
directly into slots 0..3. Logical object 0 (the player) is usually a high rank, so
it is normally one of the deferred slots; `hudBorderHandoff` detects
`INITIAL_OBJECT == 0` on a reclaimed slot and rebuilds `PLAYER_HW_MASK` accordingly.

Lifecycle:

| phase | routine | when | effect on slots 4..7 |
| --- | --- | --- | --- |
| arm | `hudBorderSetup` | line-1 IRQ (`rasterFrameReset`), before HUD DMA @ ~raster 21 | slots 4..7 = HUD (ptr/colour/X/Y), `$D01C &= $0F` (hires), `$D010` bit7 = HUD sprite 3 @ X=280, `$D017=$D01D=$D01B=0` |
| protect | `renderSprites` | main thread ~raster 8–20 | initial write **capped at `HUD_SLOT_FIRST` (4) slots**; `$D015 |= $F0` keeps the HUD enabled through its DMA; `$D010 |= $80` |
| hand off | `hudBorderHandoff` | DISPLAY event @ `HUD_HANDOFF_RASTER` (measured entry raster 47) | re-applies deferred `INITIAL_*[LIVE+s]` for `s = 4..RENDER_COUNT-1` into slots 4..7 (ptr/colour/X/Y/X-MSB), `$D01C |= $F0` (multicolour restored), `$D015 = SPRITE_ENABLE_MASK[RENDER_COUNT]` (drops HUD-only bits), `$D010` bit7 dropped, `PLAYER_HW_MASK` updated if a reclaimed slot owns object 0 |
| schedule | `buildBatchSpriteSchedule` | main thread | floors `SLOT_FREE_RASTER[4..7]` at `HUD_HANDOFF_RASTER` so no batch reuses a HUD slot before the handoff |

## 5. HUD X / Y

- **Y = 22** (SPR_Y register) → sprite body rasters **22..42**. Determined
  experimentally: clear of the raster-55 clean-terrain floor by 13 px; entirely
  inside the solid-`$D021` opened-border zone; DMA (p-access ~raster 21) sits well
  after the line-1 `hudBorderSetup`.
- **X = 40, 120, 200, 280** (`$D010` bit 7 set for sprite 3 only). Four sprites
  spread across the normal visible width; **no horizontal-border tricks**.

## 6. Bitmap / pointer allocation

- 4 × 64 B hires sprite bitmaps at **`$2f00`..`$2ffe`** (`HUD_SPRITE_BASE`), inside
  the free VIC-bank-0 gap `$2e6a..$2fff`. Pointers **`$bc..$bf`**
  (`HUD_SPRITE_BASE_PTR = $2f00/64`). Guards assert
  `hudProofSprites == $2f00`, `hudProofSpritesEnd == $2f00 + 4*64`,
  `hudProofSpritesEnd <= HEALTH_SPRITE_BASE ($3000)` — all pass.
- Geometry tables `hudProof{Ptr,X,XMsb,Colour}` at **`$1f4b..$1f5a`** in the
  `$1f00` lookup segment.
- Deliberately-distinct diagnostic patterns so any corruption / HUD↔gameplay swap
  is obvious: **s4** white dither/checkerboard, **s5** yellow horizontal bars,
  **s6** light-green chevron, **s7** cyan box framing a digit "4". Colours
  `$D02B..$D02E` = 1 / 7 / 13 / 3.
- Pointer handling is table-driven (`hudProofPtr`), not immediates: a future
  `$D018` bank/screen swap only needs the pointer table (and `HUD_SPRITE_BASE`)
  revisited in one place; `hudBorderSetup` and `hudBorderHandoff` both index it.

## 7. HUD raster phase

An explicit phase, not writes buried in scrolling code:

1. **line 1** — `rasterFrameReset` → `jsr hudBorderSetup` (arm slots 4..7 = HUD).
2. **main thread** — `renderSprites` runs with its initial write capped at 4 slots
   (HUD untouched); `buildBatchSpriteSchedule` floors the HUD slots' free-raster.
3. **DISPLAY compare `$2E` (= 46)** — `rasterDisplayHook` → `jsr hudBorderHandoff`
   (slots 4..7 → deferred gameplay sprites).
4. **BORDER compare `$F0` (= 240)** — `borderOpenHook` (RSEL dodge, unchanged).
5. **compare `$00`** — epoch / next physical frame.

The previously-neutered DISPLAY event (a no-op at raster 56 since Phase 1.5) is
**repurposed** as the handoff hook; the event-merge plumbing in
`dispatchRasterEvents` is unchanged.

## 8. `$D011` / `$D012` write sequence per frame (measured, `build/hud-wave`)

- `$D011`: `$10|fine` @ line 1 (`rasterFrameReset`); `$18|fine` (RSEL 0→1) @ ~raster
  245; `$10|fine` (RSEL 1→0) @ ~raster 250. Unchanged by the HUD.
- `$D012` compares written: `$2E` (46 — **HUD handoff / DISPLAY event**, armed once,
  re-armed on replay), `$F0` (240 — BORDER), `$00` (epoch). The `$2E` compare is
  the only new raster compare this task introduces.

## 9. HUD DMA / display lifetime

- `hudBorderSetup` completes at line 1 (well before the HUD p-access at ~raster 21).
- HUD sprite DMA/display: rasters **~21..42**.
- HUD registers must not be disturbed rasters 1..≈46; verified: nothing between
  `hudBorderSetup` and `hudBorderHandoff` writes `$D02B..$D02E`, and `renderSprites`
  is explicitly capped so it never touches slots 4..7 or clears their `$D015` bits.

## 10. Calculated + measured safe handoff raster

- **Calculated:** a deferred sprite is Y-rank 4..7 (highest-Y quartile of the
  initial set); its DMA p-access is on line `Y-1`. The handoff must finish before
  that line. The topmost sprites (rank 0..3, the ones that could sit at the
  raster-55 floor) are **not** deferred, so the binding constraint is
  `Y(rank 4) - 1`.
- **Measured (`build/hud-wave/timing.log`):** `rasterDisplayHook` entry = raster
  **47** (cycle 18–27). First `hudSlotReclaimed` = raster **49**. All deferred
  slots (up to 8) re-applied by raster **52..54** worst case.
- **Margin:** safe for any deferred sprite with `Y ≥ 56`. Stress-verified with 8
  sprites clustered at Y71 (`viewport_early95`, `viewport_top_dma`) and Y51..70
  (`clip_eight`: deferred rank-4 = Y63 → DMA line 62 → ~8-line margin) and
  `clip_boundary` — **0 sprite-start misses** in every case (§20).

## 11. Gameplay reuse of each HUD slot (register/pointer trace, not screenshot)

`hud_proof.py` stops at an **early** raster (36, mid-HUD-band) and a **late** raster
(80, past the handoff) every frame and reads the full sprite register block +
`$07F8..$07FF` + LIVE `INITIAL_*`.

**Dense (RENDER_COUNT = 8), 48/48 sampled frames:**

| slot | early raster 36 | late raster 80 |
| --- | --- | --- |
| 4 | ptr `$bc`, X 40, Y 22, col 1, `$D01C` bit4 = 0 (hires) | ptr = `INITIAL_SPRITE[LIVE+4]`, col = `INITIAL_COLOUR[LIVE+4]`, Y = `INITIAL_Y[LIVE+4]`, `$D01C` bit4 = 1 (MC) |
| 5 | ptr `$bd`, X 120, Y 22, col 7, hires | = `INITIAL_*[LIVE+5]`, MC |
| 6 | ptr `$be`, X 200, Y 22, col 13, hires | = `INITIAL_*[LIVE+6]`, MC |
| 7 | ptr `$bf`, X 280 (`$D010` bit7), Y 22, col 3, hires | = `INITIAL_*[LIVE+7]`, MC, `$D010` bit7 cleared |

All four HUD slots observed holding a **non-HUD (gameplay) pointer** at the late
sample in **every** frame → time-domain reuse, no reservation. HUD block at the
early sample is **byte-identical to the frame-0 reference** across all 48 frames.

**Authored 6-enemy wave (seed 382, RENDER_COUNT up to 8):** 57/57 sampled frames
pass; 3 additional frames where the main thread was a whole frame behind (catchup)
were skipped by the fixed-raster sampler and are instead covered by the beam-truth
persistence test (§13), which never drops the HUD.

When `RENDER_COUNT < 8`, the HUD slots above `RENDER_COUNT` are **disabled**
(`$D015` bit clear) by the handoff rather than rewritten — released and instantly
re-claimable (dense proves the moment gameplay needs 8, it gets 8), **not**
reserved.

## 12. All-8-slot availability proof

`build/hud-dense` (16 synthetic objects → 8 batches, `max_batches = 8`,
`RENDER_COUNT = 8`): `check_raster_capture` `final sprite pointers` check
(`matrix[1016:1016+8] == expected LIVE+ASSIGN pointers`) passes on all 200 frames,
`player hardware ownership` passes, `X high hardware mask` passes. `hud_proof.py`
dense run: slots **0..7** all observed carrying gameplay pointers post-handoff.
No slot is withheld from the multiplexer after the HUD hand-off.

## 13. HUD persistence across many frames (beam truth)

`hud_persist.py` — screenshot **every** frame + read `$D015` at the HUD raster:

| scenario | frames | HUD sprites visible / frame | `$D015` HUD bits set @ HUD raster |
| --- | --- | --- | --- |
| authored wave, peak 7 objects | 120 / 120 | 4 (histogram `{4: 120}`) | every frame |
| dense, 16 objects | 90 / 90 | 4 (histogram `{4: 90}`) | every frame |

No flicker, no dropped frame, no pointer/colour corruption.

## 14. VIC mode/state handling (audit, `vic_audit.py`, 7 active objects)

| register | HUD raster (28) | post-handoff raster (82) |
| --- | --- | --- |
| `$D015` enable | `%11111111` (s0–3 gameplay + s4–7 HUD) | `%01111111` (RENDER_COUNT = 7; s7 released) |
| `$D01C` multicolour | `%00001111` (**s4–7 hires**) | `%11111111` (**s4–7 MC restored**) |
| `$D010` X-MSB | `%1xxxxxxx` (**bit7 = HUD s7 @ X280**) | `%0xxxxxxx` (**bit7 cleared**) |
| `$D017` Y-expand | `%00000000` | `%00000000` |
| `$D01D` X-expand | `%00000000` | `%00000000` |
| `$D01B` priority | `%00000000` | `%00000000` |
| `$D025/$D026` MC pair | unchanged | unchanged |
| `$D027–$D02E` | s4–7 = 1/7/13/3 (HUD) | s4–6 = reclaimed enemy colours; s7 stale (disabled) |
| `$D000–$D00F` X/Y | s4–7 = 40/120/200/280, Y 22 | s4–6 = reclaimed enemy X/Y; s7 stale (disabled) |
| pointers `$07F8–$07FF` | s4–7 = `bc bd be bf` | s4–6 = gameplay ptrs; s7 = stale `bf` (disabled) |

Gameplay never inherits stale HUD mode: `hudBorderHandoff` explicitly restores
`$D01C` bits 4..7 to multicolour and rewrites every reclaimed slot's
ptr/colour/X/Y/X-MSB from LIVE. HUD does not depend on previous-frame VIC state:
`hudBorderSetup` writes `$D01C`/`$D010` with `AND` masks + fixed `OR`, and forces
`$D017 = $D01D = $D01B = 0` every frame.

## 15. Pointer-table handling / future `$D018`

HUD pointers live only in `hudProofPtr` ($1f4b) and are resolved from
`HUD_SPRITE_BASE`. `hudBorderSetup` writes `HW_SPRITE_POINTER + HUD_SLOT_FIRST,x`
from that table; `hudBorderHandoff` restores gameplay pointers from
`INITIAL_SPRITE` (the renderer's own source). A future `$D018` screen/bank swap
touches exactly one table + one const; nothing in the HUD path hard-codes a
pointer value.

## 16. BUILD / LIVE interaction (measured — not rewritten)

Interaction is **modest and localized**:

- **Does BUILD / `renderSprites` write HUD-owned regs before the handoff?** No.
  `renderSprites`' initial write is explicitly capped at `HUD_SLOT_FIRST`; it never
  writes slots 4..7 registers/pointers and never clears their `$D015` bits (it
  `OR`s `$F0` in).
- **Does LIVE assume all 8 slots from frame top?** No longer, under the guard — the
  capped write + `hudBorderHandoff` split is two small `#if` blocks. Undeferred
  ranks 0..3 are still written at frame top exactly as before.
- **Does batch scheduling assume HUD slots free?** No — `buildBatchSpriteSchedule`
  floors `SLOT_FREE_RASTER[4..7]` at `HUD_HANDOFF_RASTER`; batches simply schedule
  after the handoff for those slots.
- **How much special-case machinery?** Six small items (§17). No exceptions are
  threaded through the body of BUILD/LIVE.

**Conclusion: retain BUILD/LIVE.** A modest, well-contained handoff solves it; the
HUD is **not** evidence for a forced JIT-mux rewrite. (The open-border report's
separate JIT recommendation stands on its own merits, unaffected.)

## 17. Special cases required

1. `renderSprites` initial-write cap at `HUD_SLOT_FIRST` + `$D015 |= $F0` +
   `$D010 |= $80` (one `#if` block).
2. `buildBatchSpriteSchedule` `SLOT_FREE_RASTER[4..7]` floor (one `#if` block).
3. Dedicated IRQ scratch `HUD_HO_RC` / `HUD_HO_MSB` in the raster-state block
   (deliberately **not** the `TEMP_*` bytes shared with the main thread's
   `renderSprites`).
4. DISPLAY dispatcher event repurposed as the handoff (was a Phase-1.5 no-op).
5. `borderOpenHook`'s diagnostic slot-7 bottom-border marker guarded out under
   `HUD_PROOF_ENABLE` (the HUD owns slot 7).
6. Test-oracle only: `$D027–$D02E` read-back upper-nibble masking; merge of the new
   `hudSlotReclaimed` trace with `rasterInitialApplied`.

## 18. Cadence `[19656]`

`check_raster_capture` (physical PAL frames, `frame_cycle_deltas`):

| capture | frames | peak obj | batches | catchups | replays | Δcycles | service failures | sprite-start misses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hud-ord` (player idle) | 200 | 1 | 0 | 0 | 0 | **[19656]** | 0 | 0 |
| `hud-wave` (authored, seed 382; ramps 1→8, incl. 5- and 6-enemy) | 260 | 9 | 0 | 0 | 3 | **[19656]** | 0 | 0 |
| `hud-wrap` (seed 12; stage wrap + coarse transitions) | 320 | 9 | 1 | 2 | 5 | **[19656]** | 0 | 0 |
| `hud-dense` (16-object synthetic stress) | 200 | 16 | 8 | 1393 | 99 | **[19656]** | 0 | 0 |
| baseline `ob-dense` (HUD off) | 200 | 16 | 8 | 1393 | 99 | **[19656]** | 0 | 0 |

## 19. Scroll (temporal, RSEL=0 aperture 55..246)

`check_scroll_edges_rsel1.py --aperture 55 246` — model-free per-pixel temporal
test, all 8 fine phases + repeated 7→0 coarse:

| capture | `body_temporal_diffs` | `lastrow_temporal_diffs` | coarse steps | median edge jump |
| --- | --- | --- | --- | --- |
| `hud-ord` | **0** | **0** | 12 | 0 |
| `hud-wave` | **0** | **0** | 16 | 0 |
| `hud-wrap` | **0** | **0** | 19 | 0 |
| `hud-dense` | **0** | **0** | 0 (scroll frozen) | — |

Identical to the open-border baseline (`body 0 / lastrow 0`). The top-border HUD
does not disturb scrolling.

## 20. Top-Y gameplay sprites

- `sprite_y_sweep.py` Y = 50..82, HUD build vs the pre-HUD baseline sweep:
  `in_live_plan`, `d015_bit`, `first_visible_raster` (56→r63, 58→r65, …), and
  `collision_eligible` are **byte-identical** at every Y. Objects are render-plan-
  and `$D015`-eligible from Y ≤ 50; first pixel visibility begins ~Y56 — a
  **display-boundary** property, unchanged, **not** a HUD-induced dead zone.
- Handoff-margin stress (`vice_raster_cases` + `check_raster_capture`, 40 frames,
  16 objects, `hudSlotReclaimed` traced):

| case | sprite Ys | Δcycles | service failures | sprite-start misses |
| --- | --- | --- | --- | --- |
| `viewport_early95` | 8×Y71 + 8×Y107 | [19656] | 0 | 0 |
| `viewport_top_dma` | 8×Y71 + Y107..245 | [19656] | 0 | 0 |
| `clip_eight` | Y220 + Y51,54,57,60,63,66,69,70 + 7×Y150 | [19656] | 0 | 0 |
| `clip_boundary` | Y50,51,70,71,72,90,105,120,…,240 | [19656] | 0 | 0 |

## 21. 5-enemy and 6-enemy results

`hud-wave` (seed 382) ramps the authored wave 1→8 active objects. `RENDER_COUNT`
histogram over the 260-frame capture: `{1:81, 2:5, 3:11, 4:16, 5:21, 6:26, 7:50,
8:50}` — the **5-** and **6-**sprite regimes are exercised for 47 frames combined,
all `[19656]`, 0 service failures, 0 sprite-start misses, scroll body 0/0,
persistence 120/120. Player reclaimed into a deferred slot (`PLAYER_HW_MASK`
verified within the enabled set on every sampled frame).

## 22. Dense 16-object result

`hud-dense`: `max_objects 16`, `max_batches 8`, `[19656]`, 0 service failures, 0
sprite-start misses. `catchups 1393 / replay_frames 99` over 200 frames — the
**pre-existing** `--dense` synthetic-stress behaviour, **identical** to the HUD-off
baseline (`ob-dense`), and the per-frame rate matches across 180/200/220-frame runs
(≈6.97 catchups, ≈0.495 replays per frame). No regression.

## 23. Catchup / replay comparison vs baseline

| build | frames | catchups | replays | catch/frame | replay/frame |
| --- | --- | --- | --- | --- | --- |
| baseline `base-dense` (HUD off) | 180 | 1253 | 89 | 6.96 | 0.494 |
| baseline `ob-dense` (HUD off) | 200 | 1393 | 99 | 6.97 | 0.495 |
| **`hud-dense` (HUD on)** | 200 | 1393 | 99 | **6.97** | **0.495** |
| **`hud-dense` (HUD on)** | 220 | 1533 | 109 | **6.97** | **0.495** |

The HUD adds **zero** catchup/replay pressure. On a replay frame the line-1 IRQ
runs `hudBorderSetup` then the replay `renderSprites`, and the DISPLAY compare
still fires `hudBorderHandoff` at raster 47 with the (stale but valid) LIVE plan —
`check_raster_capture` is replay/epoch-accurate and reports 0 failures.

## 24. Top soft-edge masking

**None applied, none required.** The top soft-edge pop is at rasters ~52–55 (once
per coarse cycle), **below** the 55..246 aperture and **≥ 9 rasters below the HUD
body (22..42)**. The HUD sits entirely within the solid-`$D021` opened-border zone;
the pop does not reach it. `check_scroll_edges_rsel1 --aperture 55 246` = 0/0 on
every HUD capture (the pop band is outside the tested aperture, unchanged from the
open-border baseline).

## 25. Remaining bottom soft-edge state

Unchanged from the open-border task: ~4–6 px pop at rasters ~247–254 once per
coarse 7→0 cycle, below the claimed clean body (55..246). Left for a later task
(a `$D018` mid-frame swap to a zeroed charset region would mask both edges); the
HUD proof neither improves nor worsens it.

## 26. Manual verification instructions

```
# Build (KickAssembler v5.25, VICE 3.10):
cd src && java -jar <KickAss.jar> ../src/main.asm -odir ../build \
    -o ../build/shooter.prg -vicesymbols
cd .. && rm -f build/shooter.d64 \
  && c1541 -format "19656,01" d64 build/shooter.d64 \
  && c1541 build/shooter.d64 -write build/shooter.prg 19656

# Run (x64sc). The four HUD sprites (white dither / yellow bars / green chevron /
# cyan "4" box) sit in the opened top border, above the scrolling terrain.

# Automated (headless / background x64sc, no focus steal, no `open -a`):
python3 tools/vice_scroll_test.py --physical --trace --out build/hud-ord  --frames 200          # then:
python3 tools/check_raster_capture.py     build/hud-ord
python3 tools/check_scroll_edges_rsel1.py build/hud-ord --aperture 55 246
python3 tools/vice_scroll_test.py --physical --trace --out build/hud-wave --seed-scroll 382 --frames 260
python3 tools/vice_scroll_test.py --physical --trace --out build/hud-dense --dense --frames 200
python3 tools/vice_raster_cases.py --case viewport_early95 --frames 40 --out <scratch>
python3 tools/sprite_y_sweep.py --lo 50 --hi 82 --out <scratch>
# scratchpad fixtures used for the register/persistence proofs:
#   hud_proof.py <port> --dense            (EARLY vs LATE slot-ownership register proof)
#   hud_proof.py <port> --seed 382 --settle 100 --frames 60
#   hud_persist.py <port> --seed 382       (beam-truth screenshot persistence)
#   hud_persist.py <port> --dense
#   vic_audit.py <port>                    (full VIC register audit)

# Build the engine exactly as the open-border task left it:
#   comment out `#define HUD_PROOF_ENABLE` at src/main.asm:17 and rebuild
#   (verified: clean build, all HUD additions are behind the guard).
```

Harness note: `tools/vice_level1_smoke.py` sustained free-run flaked with VICE
remote-monitor socket timeouts at non-deterministic points (reproduced on retry;
the pattern is HUD-independent — long uninterrupted `x` loops under warp). It is
**not** a blocker: end-to-end real-gameplay coverage is carried by `hud-wave`
(260 frames, authored waves + streaming turret pool) and `hud-wrap` (320 frames,
stage wrap + coarse transitions), both fully clean.

## 27. Final git status / no-commit statement

```
Branch experimental-border-hud, HEAD 44e735c (unchanged).
 M src/main.asm
 M src/raster_scheduler.asm
 M tools/check_raster_capture.py
 M tools/vice_raster_cases.py
 M tools/vice_scroll_test.py
?? docs/full-200px-aperture-worklog.md            (prior open-border task)
?? docs/top-border-sprite-hud-proof-worklog.md    (this task)
?? reports/full-200px-gameplay-aperture-architectural-rework-report.md   (prior task)
?? reports/top-border-sprite-hud-proof-report.md  (this file)
```

Final artifacts:
- `build/shooter.prg`  sha256 `65bb0d2c3c116e935de5a788400cfe2dca9cdf135acbbee5db9533b96749fe73`
- `build/shooter.d64`  sha256 `c77a7f2aa295f944f2dde9dcac33ccc2a392ad9aa9ee3515dadd784a4732c6a6`

**No commit, push, add, tag or branch change was made, and none is requested.**
The working tree + worklog are the handoff.

---

## Acceptance rationale — GREEN

| criterion | result |
| --- | --- |
| HUD stable in the opened top border | 120/120 + 90/90 beam-truth frames, 48/48 register frames; byte-identical HUD block every frame |
| Uses the border, not terrain | HUD Y 22..42; clean terrain floor at raster 55 untouched |
| Terrain stays 55..246 | `check_scroll_edges_rsel1 --aperture 55 246` body 0 / lastrow 0 on every capture |
| Same physical slots reused by gameplay | slots 4..7 = HUD at raster 36, = gameplay (LIVE `INITIAL_*`) at raster 80, every frame |
| All 8 slots available after handoff | dense `max_batches 8`, `RENDER_COUNT 8`, slots 0..7 all gameplay-owned post-handoff; `final sprite pointers` check passes |
| No permanent reservation | `RENDER_COUNT < 8` → HUD slots disabled (not reserved); dense proves instant reuse of all 4 |
| No top dead zone | `sprite_y_sweep` Y50..82 identical to pre-HUD baseline |
| No new scroll corruption | 0/0 temporal diffs, all phases + coarse |
| No new sprite-start / service failures | `[19656]`, 0/0 across idle / 5- & 6-enemy / dense-16 / wrap / top-cluster stress |
| Cadence `[19656]` exact | every capture |
| Normal + 6-enemy clean | `hud-wave` 260 frames, `RENDER_COUNT` 5/6 for 47 frames, all clean |

No permanent 4-slot reservation exists, so the AMBER-forbidding condition is not
triggered; every GREEN criterion is met.
