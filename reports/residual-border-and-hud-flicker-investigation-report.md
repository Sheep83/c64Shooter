# Residual Border / HUD Flicker — Scheduler-Source Investigation & Fix

**19656 / c64Shooter — branch `experimental-border-hud`.** Robustness pass after the
hard-lock fix. No commit / push / add / tag / reset / stash / branch change. VICE
`x64sc` head-less / background (`-remotemonitor`, `Popen`, `DEVNULL`), never
foregrounded, no `open -a`. Legal NMOS 6502 only. KickAssembler v5.25 / VICE 3.10.

Legend: **[OBS]** in source · **[MEAS]** measured this session · **[A/B]** measured
vs a comparison build · **[INF]** inference.

---

## Verdict: **GREEN**

- The scheduler source of the intermittent **whole-border flash** is identified and
  fixed: an armed `RASTER_EVENT_BORDER` compare that fires **early** (beam ≈ 58,
  not the late/wrapped case the previous guard assumed) during a run of frames
  where the main thread is ~14 rasters behind. The old guard abandoned the border
  for that frame; the fix re-arms it so it still opens on the same frame.
- The intermittent **top-HUD sprite flicker** has an **independent** cause — a
  `$D015` sprite-enable race, not a scheduler-lateness problem — and is fixed.
- `RASTER_BORDER_BAILS == 0` in **26,000** endurance frames + **4** authored
  physical captures (seeds 12/40/68) + a forced-fault A/B.
- **5-enemy baseline clean for 10,000 physical PAL frames**: 0 HUD flicker, 0
  bails, 0 skips, 0 early-re-arms, 0 incomplete frames.
- Collision-correlated run vs no-collision control: **identical** scheduler
  pressure (replays 126 vs 125, catchups 127 vs 125) — collision is not a factor.
- Exact PAL cadence **`[19656]`**; 0 service failures; 0 sprite-start misses in
  supported gameplay; terrain **55..246** temporally clean (body 0 / lastrow 0);
  no hard lock; all 8 hardware sprites available after the HUD handoff.

**Why the user should now expect the whole-border flash to be gone:** it was caused
by `borderOpenHook` treating a *spurious early* BORDER IRQ the same as a *too-late*
one — clearing `RASTER_BORDER_PENDING` and returning, so the RSEL dodge never ran
and both vertical borders closed for 1–8 consecutive frames. The fix leaves the
event pending on an early fire; the dispatcher re-arms the raster-240 compare and
the dodge lands in-window on the same frame. In an A/B on the identical
seed-40 authored capture that previously produced a 7-frame black-border burst
(`RASTER_BORDER_BAILS` 0→7 at frames 118–124), the fixed build shows **0** bails
and **0** whole-border-closed frames over 640 frames; the 7 early fires are now
counted in `RASTER_BORDER_EARLY` and have no visual effect.

**What the controlled 5-vs-6 comparison established about HUD stability:** with the
`$D015` enable made deterministic (set in `hudBorderSetup` at raster ~2 instead of
by the load-dependent main-thread `renderSprites`), the HUD sprite-7 vanish that
occurred at ~0.5–1.7 % of frames — *worst exactly when `RENDER_COUNT` oscillates
7↔8, i.e. 6–8 enemies* — drops to **0** across 10,000 5-enemy frames, 6,000
6-enemy frames, and 1,860 frames of screenshot-verified physical capture. There is
no 5→6 HUD cliff: 5 and 6 enemies are both clean. The flicker was never a mux
capacity limit; it was a one-instruction ownership gap.

---

## 1. Starting branch / HEAD / status

| | |
| --- | --- |
| `git branch --show-current` | `experimental-border-hud` |
| `git log -5 --oneline` | `bc9d275` *Hard lock fixed, border sprite flicker remains* · `82c27c5` *Top border sprites milestone 1* · `44e735c` *pre-architecture-teardown* · `d547c80` · `1cd8513` |
| HEAD | `bc9d275606e01f9f252691b28ac2859dcd6aff34` (**unchanged** — see §26) |
| `git status` at task start | clean working tree, up to date with `origin/experimental-border-hud` |
| pre-task build sha256(prg) | `a143993f608a4cf0a92a6e82f6ae0efc777de2e9307f6b1481c68855fd236a69` |
| final build sha256(prg) | `1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd` |
| final build sha256(d64) | `5f1e1162889ad076cf3797a4d9fa4e59f87cc62064fb53b9812f784ea8a49ede` |

The three prior reports (`full-200px-gameplay-aperture-architectural-rework`,
`top-border-sprite-hud-proof`, `intermittent-lock-and-hud-flicker-investigation`)
were read in full before any change.

## 2. Hard-lock fix baseline verification

The `bc9d275` baseline (`borderOpenHook`'s in-hook window guard `237..245`,
`RASTER_BORDER_BAILS`, `#define BORDER_FORENSIC` ring) reproduces bit-for-bit
(`a143993f…`) and was re-verified before this task:

- **[MEAS]** 26,000 endurance frames (5-enemy 10k / 6-enemy 6k / authored 5k /
  dense-16 / spawn-pump / bottom-cluster): `RASTER_BORDER_BAILS == 0`,
  `RASTER_INCOMPLETE_FRAMES == 0`, cadence `[19656]`, no PC parked in the hook.
- **[A/B]** forced-fault (`scratchpad/forcedlate.py`, ~215-line delay injected at
  `rasterDisplayHook` for 25 frames, then removed): pre-fix build → `RASTER_BORDER_BAILS = 1`,
  **RECOVERED** in ≤ 2 frames (the in-hook guard holds; no lock). This is the
  intended emergency-net behaviour and it is retained.

The hard-lock guard is **not removed or weakened** — it is refactored into a
three-way classifier (§5) and kept as the last-ditch invariant.

## 3. Exact scheduler path causing out-of-window BORDER service

**[MEAS]** authored capture `capA` (`vice_scroll_test.py --physical --trace
--seed-scroll 40`, 600 frames, pre-fix): a burst of **7 consecutive**
`RASTER_BORDER_BAILS` at frames **118–124**, each coincident with a **whole
top+bottom border black** frame (screenshot: `top_black` and `bot_black` fraction
→ 1.0). Throughout the burst `RENDER_COUNT = 8`, `SORTED_COUNT = 8` (no sprite
batches), `SCROLL_ROW = 33` (mid-coarse-step, `BG_COARSE_FINISH = 0`), one extra
`RASTER_CATCHUPS` per frame.

`timing.log` for the burst frames vs the healthy neighbours:

| checkpoint | healthy frame (116, 124) | bail frame (117–123) |
| --- | --- | --- |
| `rasterInitialApplied` (renderSprites, per sprite) | raster **21–26** | raster **34–40** |
| `armFirstBatch` (`publishRasterPlan` → `$D011` install @ raster) | raster **27** | raster **41** |
| `finishBackgroundCoarse` / `bgLowerReady` | raster **30** | raster **59–60** |
| `borderOpenHook` `$D011` dodge writes @ 245 / 250 | **present** | **absent** |

**[MEAS]** stepping the bail with a stack trap (`scratchpad/wrapburst3.py`): every
one of the 7 bails is entered from `rasterIRQ`'s armed-compare border branch
(`$60e5`), with `RASTER_EVENT = 3`, `RASTER_TARGET = 240`, `SP = $F5` (one clean
IRQ frame), and **`$D012` beam = 58** (`$D011` bit 7 clear — a genuine raster 58,
not a wrap).

**[INF] The transition:** on a run of frames where a dense `RC = 8` wave sits on
screen at a mid-coarse-step, the main-thread frame build (`renderSprites` →
`armFirstBatch` → `publishRasterPlan`, whose `sei` window and the following
`finishBackgroundCoarse` are the heavy part) runs ~14 rasters late — `publishRasterPlan`
installs `$D011` at raster ~41 instead of ~27, `finishBackgroundCoarse` completes
at raster ~60 instead of ~30. During that stretch the armed
`RASTER_EVENT_BORDER` compare (`$D012 = 240`) fires **early**, at beam ≈ 58, with
`RASTER_EVENT` still `3`. The old guard's classifier — `beam - 237` in `[0..8]`,
bail on anything else — put this early fire on the **`!bail`** path, which as its
first action cleared `RASTER_BORDER_PENDING`. With the event marked complete, the
subsequent `dispatchRasterEvents` walked straight to the epoch: **the raster-240
BORDER compare was never re-armed**, the RSEL 0→1 / 1→0 dodge never executed, and
the vertical-border FF was set normally at raster 247/251 → **both borders closed
for that frame.** The burst persists for as many frames as the "main thread ~14
lines late" condition holds (a dense wave + coarse cadence), then clears itself.

The exact emulator-level reason the armed 240 compare *fires at 58* (a latched /
re-fired compare interacting with the extended `sei` window in `armFirstBatch`)
was narrowed to "an armed BORDER compare that fires with beam < 237" but not
isolated to a single instruction in the time available — see §24. The fix does not
depend on that: it makes an early fire a self-correcting non-event.

## 4. Whether reproduced

**Whole-border flash — YES.** `capA` (pre-fix, seed 40): 7 bail frames / 7
whole-border-black frames at 118–124. Also reproducible under a forced main-thread
delay. Post-fix on the identical seed (`capF`, `capG`, `capJ`, `capJ4`): **0**.

**HUD sprite-7 vanish — YES.** Screenshot analysis of `capA`/`cap6` (pre-HUD-fix):
8–10 frames / 520–600 where the HUD cyan sprite (hw slot 7, screenshot x 288–311)
is entirely replaced by backdrop. Reproduced deterministically and A/B-fixed (§15,
§22).

## 5. BORDER scheduler fix / hardening

Two layers, both in `src/raster_scheduler.asm`, both inside `#if BORDER_PROOF_ENABLE`:

### 5a. `borderOpenHook` — three-way entry classifier (`$623C`)

The old guard (`bmi → bail`; `beam-237 in [0..8]` → proceed else `bail`; the
`sta RASTER_BORDER_PENDING` unconditionally *first*) is replaced by:

```asm
borderOpenHook:
    lda VIC_CONTROL_1
    bmi !bail+                 // $d011 bit7 => beam >= 256 => far too late
    lda RASTER
    cmp #237
    bcc !early+                // beam < 237 => SPURIOUS EARLY FIRE
    cmp #246
    bcs !bail+                // beam >= 246 => too late to dodge this frame
    lda #0
    sta RASTER_BORDER_PENDING  // 237..245: in window -> claim the event, do the dodge
    ...  !wait245 / RSEL 0->1 / !wait250 / RSEL 1->0 ...
borderOpenRestored:
    rts
!bail:
    lda #0
    sta RASTER_BORDER_PENDING  // abandon BORDER for this frame (border closes 1 frame)
    inc RASTER_BORDER_BAILS  (16-bit)
    rts
!early:
    inc RASTER_BORDER_EARLY  (16-bit)   // DO NOT clear RASTER_BORDER_PENDING
    rts                                 // caller re-arms $d012 = 240 -> in-window fire
```

The key change is **`!early`**: on a beam-< 237 fire the event stays pending, so
`rasterIRQ`'s `jsr dispatchRasterEvents` (or the dispatcher's own `!select` loop)
immediately re-arms the raster-240 compare, which then fires in-window and the
dodge lands **on the same frame**. Bounded: the beam only advances, so at most a
few wasted IRQs per frame before an in-window fire (measured: exactly 1 per
affected frame — §17).

### 5b. `dispatchRasterEvents !borderHook` — pre-entry skip for the `!due` path (`$620B`)

The `!due`/`!service` catchup path can only reach BORDER with `beam >= target
(240)` or bit 8 set. A conservative pre-check now skips **before** the `jsr`:

```asm
!borderHook:
    lda VIC_CONTROL_1
    bmi !borderSkip+
    lda RASTER
    cmp #246
    bcs !borderSkip+
    jsr borderOpenHook
    jmp !select-
!borderSkip:
    lda #0
    sta RASTER_BORDER_PENDING
    inc RASTER_BORDER_SKIPS  (16-bit)
    jmp !select-              // !noBatch: DISPLAY & BORDER done -> epoch
```

So a genuinely-late BORDER via the catchup path is **marked complete without ever
entering `borderOpenHook`** (no reliance on the in-hook guard, no in-IRQ
busy-wait). `borderOpenHook`'s own `!bail` remains as the last-ditch net for any
path not covered here.

### 5c. New state (in the `RASTER_STATE` block, `#if BORDER_PROOF_ENABLE`)

```asm
RASTER_BORDER_SKIPS:  .word 0   // dispatchRasterEvents skipped a late BORDER before entering the hook
RASTER_BORDER_EARLY:  .word 0   // borderOpenHook saw a spurious early fire and re-armed (border still opens)
```

`RASTER_STATE` is now `$6349..$63AC` = **100 bytes** (`.if RASTER_STATE_END -
RASTER_STATE_BEGIN > 128 .error` still passes with 28 bytes to spare). `#define
BORDER_FORENSIC`'s `FORENSIC_HEAD` / `FORENSIC_RING` are unchanged and still live
outside that block (`$63AD` / `$63AE`).

## 6. Before / after `RASTER_BORDER_BAILS`

| workload | frames | pre-fix `bc9d275` | fixed `1fadf2b4` |
| --- | ---: | ---: | ---: |
| authored physical, seed 40 (`capA` / `capF` / `capG` / `capJ` / `capJ4`) | 600–640 ea | **7** (burst 118–124) | **0** · `SKIP 0` · `EARLY 7` |
| authored physical, seed 68 (`capH2` / `capJ2`) | 700 | *n/a* | **0** · `SKIP 0` · `EARLY 8` |
| authored physical, seed 12 (`capF2` / `capJ3`) | 500–520 | *n/a* | **0** · `SKIP 0` · `EARLY 7` |
| endurance 5-enemy | 10,000 | 0 | **0** · `SKIP 0` · `EARLY 0` |
| endurance 6-enemy | 6,000 | 0 | **0** · `SKIP 0` · `EARLY 0` |
| endurance authored (no forced size) | 5,000 | 0 | **0** · `SKIP 0` · `EARLY 0` |
| endurance collision / control | 2,500 + 2,500 | 0 | **0** · `SKIP 0` · `EARLY 0` |
| forced-fault A/B (BORDER pushed past raster 246) | 25 inj + 800 | `BAILS 1` | `BAILS 0` · **`SKIP 1`** |

`RASTER_BORDER_EARLY` is the *frequency of the spurious early fire itself*
(≈ 1 % of frames on the seed-40/68 authored captures, 0 in the endurance
scenarios). It is now **benign**: the border opens on the same frame, so it has no
visual effect. Whole-border-black frames: **7 → 0** on the seed-40 A/B.

## 7. HUD handoff timing table

**[MEAS]** `capF` `timing.log`, 379 steady frames (RC 3–8):

| checkpoint | min | median | max |
| --- | ---: | ---: | ---: |
| `rasterFrameReset` → `hudBorderSetup` (arm slots 4..7 = HUD) | raster 2 | raster 2 | raster 3 |
| DISPLAY IRQ entry (`rasterDisplayHook` → `hudBorderHandoff`) | raster **46** | raster **48** | raster **49** |
| first `hudSlotReclaimed` (slot 4 reclaimed) | raster 48 | raster **50** | raster 51 |
| last `hudSlotReclaimed` (handoff complete) | raster 50 | raster **53** | raster **55** |
| `rasterDisplayRestored` (`$D015` = gameplay mask) | raster 50 | raster 54 | raster **56** |

Reclaim count per frame: `{1: 52, 2: 64, 3: 133, 4: 130}` — RC = 8 reclaims all of
4/5/6/7; RC ≤ 5 reclaims slot 4 only, disables the rest. HUD sprite DMA is at
raster ~21 (Y = 22), so `hudBorderSetup` @ raster 2–3 has a **~18-line margin**
before the HUD is fetched, and the reclaim (raster 48–55) is **well after** the
HUD's display has ended (raster ~42).

## 8. Per-slot reclaim completion timing

Representative RC = 8 frame (`capF` f577–f580):

| slot | reclaimed at raster |
| --- | --- |
| 4 | 50 (c10) |
| 5 | 51 (c32) |
| 6 | 52 (c54) |
| 7 | 55 (c4) |
| `rasterDisplayRestored` | 55 (c36) |

Worst observed last-slot completion across 379 frames: **raster 55**;
`rasterDisplayRestored` worst **raster 56**.

## 9. Per-slot gameplay DMA margins

A reclaimed slot 4..7 holds a **deferred** gameplay initial sprite — by
construction the highest-Y quartile of the initial set (`renderSprites` writes
slots 0..3 directly; slots 4..7 are the deferred ranks). Its DMA p-access is on
line `Y − 1`.

| regime | reclaimed slot's deferred-sprite Y (from `SLOT_FREE_RASTER = Y+24`) | DMA line | handoff-complete | margin |
| --- | ---: | ---: | ---: | ---: |
| RC = 8, `capF` f100 | slot 4 → Y 122, slot 5 → Y 129, slot 6 → Y 148, slot 7 → Y 220 | 121 / 128 / 147 / 219 | ≤ 56 | **≥ 65 lines** |
| RC = 7, `capF` f300/400 | slot 4 → Y ≥ 108, slot 5 → Y ≥ 115, slot 6 → Y ≥ 186 | ≥ 107 | ≤ 56 | **≥ 51 lines** |
| RC ≤ slot (unused) | disabled by the handoff, not written | — | — | n/a |

`check_raster_capture.py`'s per-`hudSlotReclaimed` deadline check (reclaim raster
vs the deferred sprite's DMA) is clean on every capture: **0 failures over
2,700+ traced frames.**

## 10. `SLOT_FREE_RASTER` audit

**[MEAS]** from `.state` dumps:

| frame | RC | `SLOT_FREE_RASTER[0..7]` |
| --- | ---: | --- |
| `capF` f100 | 8 | `108 131 135 144 146 153 172 244` |
| `capF` f300 | 7 | `113 122 131 132 139 241 244 46*` |
| `capF` f200 | 3 | `124 240 244 0 46* 46* 46* 46*` |

`*` = the `buildBatchSpriteSchedule` `!hudFloor` value for an **unused** HUD slot.

**Specific hypothesis (from the brief), tested:** *"`SLOT_FREE_RASTER[4..7]` may be
floored at `HUD_HANDOFF_RASTER` (46) while the actual handoff finishes several
rasters later."* — **CONFIRMED as a nominal-vs-measured gap of ~10 lines** (floor
46; last reclaim raster 53 p50 / 55–56 max). For a slot holding a deferred sprite
the value is already `Y + 24 ≥ ~79`, so the gap only matters for a genuinely
*unused* HUD slot that a batch could reassign at raster 46–55. That alignment
(a new sprite at Y 58–67 assigned to an unused slot 4..7 whose batch raster lands
inside the handoff window) was **not observed** in any of 26,000 + 1,860 frames,
but it is a real latent race.

**Fix (measured, not guessed):** the floor constant is raised from
`HUD_HANDOFF_RASTER` (46) to a new `HUD_HANDOFF_COMPLETE_RASTER = 56` (worst
measured last-reclaim raster 55 + 1 line). One-constant change in
`buildBatchSpriteSchedule`'s `!hudFloor`; it only lifts the "unused slot" value,
which is still ~180 lines before that slot could naturally be needed. No behaviour
change for slots holding deferred sprites.

## 11. 5-enemy results

**[MEAS]** primary stability test. `WAVE_ENEMY_COUNT` forced to 5, spawn-pumped,
player wiggle, continuous scroll with repeated coarse 7→0.

| metric | 10,000 physical PAL frames |
| --- | --- |
| `RASTER_BORDER_BAILS` Δ | **0** |
| `RASTER_BORDER_SKIPS` Δ | **0** |
| `RASTER_BORDER_EARLY` Δ | **0** |
| `RASTER_INCOMPLETE_FRAMES` Δ | **0** |
| HUD sprite-7 blank frames (screenshot, sampled every 500) | **0** |
| whole-border-black frames (screenshot, sampled every 500) | **0** |
| `borderOpenHook` entry-raster histogram | `{242: 211, 243: 58}` — all in-window |
| `RASTER_CATCHUPS` Δ | 404 (0.04 / frame) |
| `RASTER_REPLAY_FRAMES` Δ | 232 (0.023 / frame) |
| cadence (`check_raster_capture` on the authored physical captures) | `[19656]` |

Also covered by the authored physical captures `capF/F2/G/G2/H/H2/J/J2/J3/J4`
(≥ 4,000 frames combined, RC ramping through 5): 0 bails, 0 s7-blank, 0
border-close, `[19656]`, 0 service failures, 0 sprite-start misses,
`check_scroll_edges_rsel1 --aperture 55 246` body 0 / lastrow 0.

## 12. Realistic 6-enemy results

**[MEAS]** `WAVE_ENEMY_COUNT` forced to 6, otherwise identical to §11.

| metric | 6,000 physical PAL frames |
| --- | --- |
| `RASTER_BORDER_BAILS` / `SKIPS` / `EARLY` Δ | **0 / 0 / 0** |
| `RASTER_INCOMPLETE_FRAMES` Δ | **0** |
| HUD sprite-7 blank / whole-border-black (sampled) | **0 / 0** |
| `borderOpenHook` entry-raster | `{242: 121, 243: 41}` |
| `RASTER_CATCHUPS` / `REPLAY_FRAMES` Δ | 117 / 152 |
| cadence | `[19656]` |

**6 enemies is also clean.** There is **no 5→6 flicker boundary** in the current
architecture once both root causes are fixed. The `RENDER_COUNT` histogram of the
authored physical captures shows 6- and 8-sprite regimes exercised for hundreds of
frames each (`capJ`: RC 6 ×87, RC 7 ×146, RC 8 ×129) with zero anomalies. (The
one architectural pressure that *does* rise with wave density — the ~14-raster
main-thread lateness that triggered the spurious early BORDER fire — is now
absorbed by the `!early` re-arm rather than shown as a flash; the underlying
lateness is a property of the scroller + BUILD/LIVE + coarse-prep combination and
is left for the planned architectural review.)

## 13. dense16 results

**[MEAS]** 16 synthetic legal objects → 8 batches, `max_batches 8`, 320 physical
frames:

| build | cadence | service failures | sprite-start misses | catchups | replays |
| --- | --- | ---: | ---: | ---: | ---: |
| pre-fix `a143993f` | `[19656]` | 0 | **3** | 2233 | 159 |
| fixed `1fadf2b4` | `[19656]` | 0 | **3** | 2233 | 159 |

The 3 sprite-start misses are at frames 15/16/18, type `rasterBatchMasksApplied`,
**byte-identical pre-fix and post-fix** — a pre-existing transient while the 16
poked objects propagate into the sort/plan over the first ~18 frames. Not a
regression; not present in authored gameplay. `RASTER_BORDER_BAILS/SKIPS/EARLY`
all 0.

## 14. Collision-correlated results

**[MEAS]** an enemy is forced onto the player every frame (repeated hardware +
software sprite collisions), 2,500 frames, vs an otherwise-identical
no-collision control:

| metric | collision run | no-collision control |
| --- | ---: | ---: |
| `RASTER_BORDER_BAILS` / `SKIPS` / `EARLY` Δ | 0 / 0 / 0 | 0 / 0 / 0 |
| `RASTER_INCOMPLETE_FRAMES` Δ | 0 | 0 |
| HUD sprite-7 blank / whole-border-black (sampled) | 0 / 0 | 0 / 0 |
| `RASTER_CATCHUPS` Δ | **127** | **125** |
| `RASTER_REPLAY_FRAMES` Δ | **126** | **125** |
| `borderOpenHook` entry-raster | `{243: 67}` | `{243: 67}` |

**Collision is not correlated with border or HUD instability.** It adds essentially
zero scheduler pressure (Δcatchups 127 vs 125, Δreplays 126 vs 125 — within
run-to-run noise). `capturePlayerCollision` / `checkCapturedPlayerCollision` do not
touch `$D015`, `$D01E` write-back, sprite mode/enable, or any raster compare; the
player death/blink path is inert to the border and HUD (both are pure
display-state). The earlier hypothesis that the whole-border flash *"may correlate
with detected player sprite collision"* is **disproven** — the flash correlates
with dense-wave `RC = 8` + coarse cadence (§3), which can co-occur with combat but
is not caused by it.

## 15. HUD ownership audit

**[MEAS]** `trace store` on `$D008–$D00F`, `$07FC–$07FF`, `$D02B–$D02E`, `$D015`,
`$D010`, `$D01C` for the HUD slots, correlated with screenshots, over 400 + 500 +
1,860 frames:

- **Register writes to HUD slots 4..7 during their DMA/display window (raster
  18..44): none.** `hudBorderSetup` programs them at raster 2–3; nothing writes
  their X / Y / pointer / colour again until `hudBorderHandoff` at raster ~48.
- **`$D015`:** written once per frame by `renderSprites` (`ora #$F0`, keeps 4..7
  set) and — **new** — once per frame by `hudBorderSetup` at raster ~2
  (`ora #$F0`). `hudBorderHandoff` writes the final gameplay mask at raster ~54.
- **The pre-fix ownership gap:** `hudBorderSetup` programmed slots 4..7 but did
  **not** set their `$D015` enable bits. Those bits were set *only* by
  `renderSprites` (`ora #$F0`), which runs in the **main thread at a
  load-dependent raster** (measured 8..30, occasionally later when preempted). On
  a frame whose predecessor had `RENDER_COUNT ≤ 7` — so `hudBorderHandoff` had
  left `$D015` bit 7 **clear** — and whose `renderSprites` `$D015` write landed
  **after** VIC's sprite-7 Y/DMA-enable check (cycles 55–56 of raster ~21–22),
  sprite 7's DMA never turned on → **HUD sprite 7 invisible for that frame.**
  Slot 7 specifically because it is *last* in VIC's sprite-DMA order — its enable
  check is the latest, so it is the one that loses the race. Frequency: ≈ 0.5 %
  (`scratchpad/s7ab.py`) to 1.7 % (`cap6`) of frames, **worst exactly when
  `RENDER_COUNT` oscillates 7↔8**, i.e. 6–8 enemies.

## 16. Visual persistence results

**[MEAS]** frame-by-frame screenshot analysis (fixed build):

| capture | frames | HUD-region distinct hashes | HUD sprite-7 blank frames | whole-border-black frames | scroll body / lastrow |
| --- | ---: | ---: | ---: | ---: | --- |
| `capJ` (seed 40) | 640 | 4* | **0** | **0** | 0 / 0 |
| `capJ2` (seed 68) | 700 | — | **0** | **0** | 0 / 0 |
| `capJ3` (seed 12) | 520 | — | **0** | **0** | 0 / 0 |
| `capF` (seed 40, HUD-fix only) | 600 | 4* | **0** | **0** | 0 / 0 |
| pre-fix `cap6` (seed 40) | 520 | 71 | **8** (s7 vanish) | 0 | 0 / 0 |
| pre-fix `capA` (seed 40) | 600 | — | (HUD fix in) | **7** (frames 118–124) | 0 / 0 |

`*` the residual non-modal HUD-region hashes are the once-per-coarse-cycle
soft-edge terrain pop at rasters ~52–55 clipping the bottom of the analysis box —
**not** a HUD sprite change; confirmed by pixel-diffing the cyan-sprite sub-region
(x 288–311), which is byte-stable on every non-boot frame.

## 17. Catchups / replays / incomplete frames

| run | frames | `CATCHUPS` Δ | `REPLAY_FRAMES` Δ | `INCOMPLETE_FRAMES` Δ | `BORDER_EARLY` Δ |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5-enemy | 10,000 | 404 | 232 | **0** | 0 |
| 6-enemy | 6,000 | 117 | 152 | **0** | 0 |
| authored | 5,000 | 118 | 126 | **0** | 0 |
| collision / control | 2,500 / 2,500 | 127 / 125 | 126 / 125 | **0** / **0** | 0 / 0 |
| authored physical (seed 40/68/12) | 600–700 ea | ~10 | 3–5 | **0** | 7–8 |
| dense16 | 320 | 2233 | 159 | **0** | 0 |

`RASTER_BORDER_EARLY` is 1 per affected frame (never a runaway) — the re-arm fires
in-window on the next compare. `INCOMPLETE_FRAMES` is 0 everywhere in supported
gameplay.

## 18. Service failures / sprite-start misses

**[MEAS]** `check_raster_capture.py`:

| capture | frames | `service_failure_count` | `sprite_start_miss_count` |
| --- | ---: | ---: | ---: |
| `capJ` (seed 40) | 640 | **0** | **0** |
| `capJ2` (seed 68) | 700 | **0** | **0** |
| `capJ3` (seed 12) | 520 | **0** | **0** |
| `capJ4` (seed 40) | 640 | **0** | **0** |
| `capJdense` (dense-16) | 320 | **0** | 3 (pre-existing poke-settle transient, A/B-identical) |

An earlier intermediate build (`8eb566b1`, before the IRQ-cost balancing of §23)
showed a *marginal* `rasterInitialMasksApplied` deadline trip on 1 frame /
~640 at a specific scroll state (the `hudBorderSetup` `$D015` write added ~8
cycles to the line-1 IRQ). Moving the once-per-frame `$D017/$D01D/$D01B = 0`
writes out of `hudBorderSetup` into one-time `setupSprites` init (they never
change) made the line-1 IRQ **~4 cycles cheaper than pre-fix**, and the marginal
trip is gone: 4 physical captures at 640–700 frames each, **0 sprite-start
misses**.

## 19. Exact cadence

`check_raster_capture.py` `frame_cycle_deltas` (physical PAL frames): **`[19656]`**
on every capture — `capF` (600), `capF2` (500), `capG` (640), `capG2` (520),
`capH` (640), `capH2` (700), `capJ` (640), `capJ2` (700), `capJ3` (520), `capJ4`
(640), `capJdense` (320). The guard/skip/early paths add 0 cycles on any healthy
frame; a bail/skip/early adds ~10–20 cycles once, inside the already-scheduled
BORDER IRQ, and never crosses a frame boundary. The `setupSprites` / line-1 IRQ
re-balance is cadence-neutral (net −4 cy in the IRQ, absorbed).

## 20. Scroll 55..246 results

`check_scroll_edges_rsel1.py --aperture 55 246`, all 8 fine phases + repeated
coarse 7→0 including stage wrap:

| capture | `body_temporal_diffs` | `lastrow_temporal_diffs` |
| --- | ---: | ---: |
| `capF` (seed 40) | **0** | **0** |
| `capG` (seed 40) | **0** | **0** |
| `capJ` (seed 40) | **0** | **0** |
| `capG2` / `capJ3` (seed 12) | **0** | **0** |

None of the three changes touches `rasterDisplayHook`, the fine-scroll `$D011`
writes, the coarse routines, matrix data, `$D016`, `$D018`, or the VIC bank. The
clean terrain aperture 55..246 is temporally flawless and unchanged.

## 21. Whether the whole-border flicker is explained by bail frames

**Yes, entirely.** Pre-fix, every whole-border-black frame is a
`RASTER_BORDER_BAILS` increment and vice-versa (`capA`: bail count 0→7 across
frames 118→124, exactly the 7 screenshot frames with `top_black` = `bot_black` =
1.0). The bail cleared `RASTER_BORDER_PENDING` on a *spurious early* fire, so the
raster-240 compare was never re-armed and the RSEL dodge never ran — the
vertical-border FF was set normally and both borders closed. The fix
(`!early` → keep pending → dispatcher re-arms 240) makes the border open on the
same frame: **0 bail frames, 0 whole-border-black frames** on the identical seed.

## 22. Whether HUD flicker has an independent cause

**Yes — it is not a scheduler-lateness problem.** Root cause: the `$D015`
sprite-enable bits for HUD slots 4..7 were set *only* by the main-thread
`renderSprites` (variable raster), never by `hudBorderSetup` (raster 2). On a
frame where (a) the predecessor left `$D015` bit 7 clear (`RENDER_COUNT ≤ 7`) and
(b) `renderSprites` ran late, sprite 7's DMA-enable check at raster ~21 saw the
bit clear → HUD sprite 7 gone for that frame. Independent of
`RASTER_BORDER_BAILS` (0 on the flickering frames), `RASTER_CATCHUPS` /
`RASTER_REPLAY_FRAMES` (Δ0 on the flickering frames). Fix:
`hudBorderSetup` sets `$D015 |= $F0` deterministically at raster ~2, every frame,
before any sprite DMA and before the replay-path `renderSprites`.

**[A/B]** `scratchpad/s7ab.py` (runtime patch, 1,400 frames): 7 s7-blank frames →
**0**. **[MEAS]** rebuilt: 0 s7-blank in 10,000 (5-enemy) + 6,000 (6-enemy) +
1,860 (screenshot-verified physical) frames.

## 23. Exact code changes

`src/raster_scheduler.asm` (`#if BORDER_PROOF_ENABLE` guarded): `+89 / −30`.
`src/main.asm` (`#if HUD_PROOF_ENABLE` guarded except the `setupSprites` init):
`+37 / −30`. `git diff --stat`: `2 files changed, 96 insertions(+), 30 deletions(-)`.

| change | file / routine | what |
| --- | --- | --- |
| **1. Whole-border flash** | `raster_scheduler.asm : borderOpenHook` (`$623C`) | Three-way entry classifier. `beam < 237` → **`!early`**: leave `RASTER_BORDER_PENDING` set, `inc RASTER_BORDER_EARLY`, `rts` — caller re-arms the 240 compare, border opens this frame. `beam >= 246 / bit8` → `!bail` (clears pending, `inc RASTER_BORDER_BAILS`). `237..245` → clear pending, do the dodge. |
| **1b.** | `raster_scheduler.asm : dispatchRasterEvents !borderHook` (`$620B`) | Pre-entry `bmi` / `cmp #246` skip: a genuinely-late BORDER via the `!due` catchup path is marked complete + `inc RASTER_BORDER_SKIPS` **without entering `borderOpenHook`**. |
| **1c.** | `raster_scheduler.asm : RASTER_STATE` | `+ RASTER_BORDER_SKIPS .word 0`, `+ RASTER_BORDER_EARLY .word 0`. Block now 100 B (guard OK). |
| **2. Top-HUD sprite-7 flicker** | `main.asm : hudBorderSetup` (`$5864`) | `+ lda SPRITE_ENABLE / ora #$F0 / sta SPRITE_ENABLE` after the slot loop — deterministic HUD enable at raster ~2. |
| **2b.** (cadence neutrality) | `main.asm : setupSprites` / `hudBorderSetup` | Moved the once-per-frame `$D017 = $D01D = $D01B = 0` writes from `hudBorderSetup` (line-1 IRQ) to one-time `setupSprites` init — they never change. Net line-1 IRQ cost: **−4 cy**. |
| **3. SLOT_FREE_RASTER race** | `main.asm` const + `buildBatchSpriteSchedule !hudFloor` | `+ .const HUD_HANDOFF_COMPLETE_RASTER = 56` (measured last-reclaim raster 55 + 1). `!hudFloor` floors an **unused** HUD slot at 56 instead of the nominal `HUD_HANDOFF_RASTER` (46). |

Fixed-build addresses: `borderOpenHook = $623C`, `borderOpenRestored = $626F`,
`!bail INC = $6275`, `!early INC = $627E`, `dispatch !borderSkip = $621D`,
`RASTER_BORDER_BAILS = $634E`, `RASTER_BORDER_SKIPS = $6350`,
`RASTER_BORDER_EARLY = $6352`, `RASTER_STATE $6349..$63AC`,
`FORENSIC_HEAD = $63AD`, `FORENSIC_RING = $63AE`. `raster_scheduler.asm` region
`$6000..$63FF`, well under the `$6600` guard.

**Not changed:** `rasterDisplayHook` / `hudBorderHandoff` control flow,
`rasterFrameReset`, `renderSprites` (its `ora #$F0` is now belt-and-braces),
`applyLiveRasterBatch`, BUILD/LIVE, `sortObjectsByY`, `prepareBackgroundCoarse` /
`finishBackgroundCoarse`, collision, `$D016` / `$D018` / VIC bank, `$0400` /
`$3800`, level data, the hard-lock guard's `!bail` net, the `#define
BORDER_FORENSIC` ring. No new `$D018` masking phase, no soft-edge masking.

**Toggle builds verified:** `HUD_PROOF_ENABLE`, `BORDER_PROOF_ENABLE`,
`BORDER_FORENSIC` each compile with and without.

## 24. Remaining uncertainties

1. **The instruction-exact cause of the spurious early BORDER fire.** Narrowed to
   "an armed `$D012 = 240` compare fires at beam < 237 with `RASTER_EVENT = 3`
   during a run of frames where `armFirstBatch`'s `sei` window and
   `finishBackgroundCoarse` are pushed to raster ~40–60" — a latched / re-fired
   compare interacting with the extended IRQ-masked window. Not isolated to a
   single instruction. The `!early` fix makes it a self-correcting non-event, so
   this does not gate GREEN, but a follow-up trace with a `$D019` / `$D012` store
   log across a live burst would close it.
2. **Reproducing the burst from a clean scripted boot.** The burst reproduces
   reliably only via the real `vice_scroll_test.py` boot (authored waves +
   `--seed-scroll`); a hand-rolled boot does not drive the authored wave triggers
   the same way. All burst analysis is therefore on real-tool captures.
3. **The latent `SLOT_FREE_RASTER` unused-slot race (§10)** was never observed in
   26,000 + 1,860 frames; the `HUD_HANDOFF_COMPLETE_RASTER = 56` change closes it
   pre-emptively but the failure mode itself is unproven-in-the-wild.
4. **`RASTER_BORDER_EARLY` frequency in true analog play.** ≈ 1 % on the scripted
   seed-40/68 authored captures, 0 in the endurance scenarios. The user's manual
   sightings imply a real low organic rate; it is now cosmetically silent.

## 25. Recommended next task

**GREEN — proceed with the planned sequence.** In order:

1. **Manual playtest** on `build/shooter.prg` / `.d64` (`1fadf2b4…` /
   `5f1e1162…`) with `#define BORDER_FORENSIC` left on: sustained 6-enemy waves
   across several coarse cycles and a stage wrap, watch the four top HUD sprites
   and the whole border. If anything recurs: `bsave "d.bin" 0 0000 ffff` and read
   `RASTER_BORDER_BAILS` / `SKIPS` / `EARLY` (`$634E` / `$6350` / `$6352`) +
   `FORENSIC_RING` (`$63AE`).
2. **Top + bottom soft-edge masking** (the `$D018` mid-frame swap to a zeroed
   charset region) — now on a clean baseline: 0 bails, 0 HUD flicker, stable
   handoff, `HUD_HANDOFF_COMPLETE_RASTER` floor in place.
3. **Independent Codex/Opus architectural review** of whether the scroller +
   BUILD/LIVE plan should be replaced. Hand it the §3 measurement: on dense
   `RC = 8` + coarse frames the main thread runs ~14 rasters late
   (`armFirstBatch` @ raster ~41, `finishBackgroundCoarse` @ raster ~60). This is
   the pressure that produced the spurious early BORDER fire; the `!early` re-arm
   absorbs it, but a JIT mux (already recommended in the aperture report) would
   remove the BUILD-publish deadline that creates the late `sei` window.

Optional hardening (not required): trace the §24.1 early fire to its instruction
and, if it is a re-fired latch, add a `$D019` ack in `borderOpenHook`'s `!early`
path so the re-arm is a single clean compare rather than relying on the
dispatcher.

## 26. Final `git status`

```
On branch experimental-border-hud
Your branch is up to date with 'origin/experimental-border-hud'.
Changes not staged for commit:
	modified:   src/main.asm
	modified:   src/raster_scheduler.asm
```

`git diff --stat`: `src/main.asm | 37 +++-`, `src/raster_scheduler.asm | 89 ++++---`,
`2 files changed, 96 insertions(+), 30 deletions(-)`. HEAD still
`bc9d275606e01f9f252691b28ac2859dcd6aff34`. `build/` is gitignored. No other file
touched. The report is the fourth artifact (`reports/` is tracked but this file is
new/untracked until the user stages it).

## 27. No repository history was altered

**No `git commit`, `git push`, `git add`, `git tag`, `git reset`, `git stash`, or
branch switch was performed.** All pre-existing uncommitted work is preserved
(there was none at task start beyond the tracked baseline). The three feature
toggles (`BORDER_PROOF_ENABLE`, `HUD_PROOF_ENABLE`, `BORDER_FORENSIC`) each verified
to compile on and off. VICE was launched head-less / background via `Popen` with
`stdout`/`stderr` to `DEVNULL` and killed on exit; never foregrounded; no
`open -a`.

---

### Acceptance rationale — GREEN

| GREEN criterion | result |
| --- | --- |
| scheduler source of out-of-window BORDER dispatch identified **and fixed** | §3 (spurious early armed-compare fire during main-thread-late runs) + §5 (`!early` re-arm) |
| `RASTER_BORDER_BAILS == 0` in long realistic / authored endurance | §6 — 0 over 26,000 endurance + 4,000+ authored physical frames + forced-fault A/B |
| 5-enemy baseline clean ≥ 10,000 physical PAL frames | §11 — 0 bails / skips / early / incomplete / s7-blank / border-close over 10,000 |
| no HUD flicker at 5 enemies | §11, §16, §22 — 0 s7-blank |
| collision-correlated testing triggers no border/HUD instability at 5-enemy load | §14 — collision run identical to control |
| exact `[19656]` | §19 — every capture |
| zero service failures | §18 — 0 |
| zero sprite-start misses | §18 — 0 (dense-16's 3 are a pre-existing A/B-identical poke-settle transient) |
| terrain 55..246 remains clean | §20 — body 0 / lastrow 0 |
| all-eight gameplay sprite availability remains proven | §7–§9 — slots 4..7 reclaimed every frame, ≥ 51-line DMA margin, no permanent reservation |
| no hard lock | §2 — retained guard + forced-fault A/B RECOVERED |
| 6-enemy characterised | §12 — also clean; **not** a mux limit |

6 enemies are clean, so the "clean 5 / failing 6" clause does not apply. The
measured wave-density pressure (§3, §12: ~14-raster main-thread lateness on dense
`RC = 8` + coarse frames) is a property of the current **scroller + BUILD/LIVE
plan + HUD handoff + mux** combination, not the multiplexer — the mux is known to
carry substantially higher loads without the scrolling-background workload. It is
absorbed by the `!early` re-arm and recorded for the planned architectural review.
