# Bottom-Border Sprite HUD — Feasibility & Architecture Investigation

**19656 / c64Shooter — PAL C64 vertical shooter.**
Investigation only. Nothing implemented. No commit, no push. One read-only VICE
probe (RAM pokes only, background launch, no focus steal); no repo file changed.

Legend for every claim below:
**[OBS]** observed fact from source · **[MEAS]** measured this session ·
**[DOC]** measured previously and recorded in `docs/` · **[INF]** inference ·
**[REC]** recommendation.

---

## 0. Authority

| | |
| --- | --- |
| Branch | `terrain-asset-workshop` (checked out; not switched) |
| HEAD | `ff91d2d960c5a1f486d1f774238f823039996ab1` — *"Tile retention and additional editing tools added. Top HUD glitch still present"* |
| Working tree | clean |
| Build | KickAssembler 5.25 → `build/shooter.prg`, `build/main.vs` (559 symbols), clean |
| Emulator | `x64sc` (VICE 3.x), PAL, `-warp`, `-remotemonitor`, background `Popen`, no `open -a` |
| PAL frame | 312 lines × 63 cycles = **19,656 cycles** |

**Archaeology files not present locally.** `terra_cresta_border_hud_*` and
`slap_fight_border_hud_*` do not exist in the repo or session
(`find` returned nothing). The Terra Cresta / Slap Fight findings quoted in this
report are taken verbatim from the task brief and treated as **[DOC]-equivalent
external reference**, not re-derived here.

---

## 1. Current PAL frame map

### 1.1 Display geometry (RSEL=0, permanent) — [OBS] + [DOC] (Task 4 investigation)

| Raster | px | Content | Owner |
| ---: | ---: | --- | --- |
| 51–54 | 4 | RSEL=0 top crop → border | `init` clears `$D011` bit 3 once (`main.asm:414`) |
| 55–62 | 8 | Fixed HUD, matrix row 0, YSCROL 7 | `rasterDisplayHook` / `initFixedHud` |
| 63–70 | 8 | Forced-black separator (BMM+ECM invalid mode) — *the "top HUD glitch"* | `rasterDisplayHook` (`raster_scheduler.asm:258–303`) |
| 71–246 | 176 | Terrain, matrix rows 1–23, YSCROL = fine 0–7 (scrolls) | scroller |
| 247–250 | 4 | RSEL=0 bottom crop → border (masks the historical 7→0 bottom pop) | RSEL=0 |
| 251–~300 | ~50 | **Lower border (closed).** Nothing rendered here today. | — |

Gameplay area today: **176 px / 22 char rows.** The RSEL=0 lower-border compare
fires at **raster 247**; once the vertical border flip-flop is set there it stays
set until the top compare next frame (raster 55). **[OBS]** `raster_scheduler.asm`
+ `main.asm:404–416`.

### 1.2 Per-frame execution timeline — [OBS] source + [MEAS] this session

`x64sc` trace of `rasterFrameReset`, `rasterDisplayRestored`,
`rasterBadlineRestored`, `applyLiveRasterBatch`, `rasterAssignmentApplied`,
`bgUpperReady`, `waitForGameFrame`, plus `store d011/d012`, over 400 physical
frames of ordinary Level-1 play, then forced dense / lowest-Y loads.

| ~Raster | Phase | Routine / label | VIC touched | Hard real-time? |
| ---: | --- | --- | --- | --- |
| ~0–1 | Physical frame reset; `$D011 = $17` | `rasterFrameReset` (IRQ) | `$D011` | yes (compare 0) |
| ~2–15 | `waitForGameFrame` releases main; `capturePlayerCollision` reads/clears `$D01E`; `renderSprites` writes 8 initial hw sprites; `armFirstBatch` → `publishRasterPlan`; `finishBackgroundCoarse` lower copy (coarse frames only) | `gameLoop` main thread | `$D000-$D00F,$D010,$D015,$D027-$D02E,$07F8-$07FF` | soft (before first badline) |
| ~40–48 | Nothing scheduled | — | — | — |
| **55** | Fixed HUD badline (matrix row 0, YSCROL 7) | VIC | — | yes |
| **56** | `RASTER_EVENT_DISPLAY` fires | `dispatchRasterEvents` → `rasterDisplayHook` | `$D011` ×3–4 | **cycle-tight** (9-cycle poll slack in H-border; see `raster_scheduler.asm:307`) |
| 56–71 | HUD → separator → terrain transition writes (`$17→$11→$71→$70\|f→$10\|f`) | `rasterDisplayHook` | `$D011` | **yes** |
| **70–71** | `rasterDisplayRestored` / `rasterBadlineRestored` — last IRQ VIC write of the frame on a light frame | `rasterDisplayHook` | `$D011` | yes |
| 71 → ~233 | Terrain visible. Sprite batches (objects 9+) fire at `earliestY − 12`. **[MEAS]** latest batch raster observed: **233** (8 sprites forced to Y=245). Normal play: no batches at all on 375/400 frames. | `applyLiveRasterBatch` (IRQ) | `$D000-$D00F,$D010,$D027-$D02E,$07F8-$07FF` | yes (per batch compare) |
| ~152–184 | Coarse admission test + upper-row copy *start* (coarse frames only). Defers if a batch is pending, if `$D011` bit 7 set, or if `RASTER ≥ 184` (`BG_COARSE_LATEST_START`). | `prepareBackgroundCoarse` (`main.asm:5455`) | screen RAM only | raster-gated |
| ~160 → **271–272** | Coarse upper-row copy runs to completion. **[MEAS]** `bgUpperReady` at raster **271–272** on all 25/400 coarse frames. | `saveCrossingRow`+`shiftBackgroundUpper`+`renderStageRowToScreen` | screen RAM | must finish before raster ~159 next frame |
| ~200–233 → 311 | **Normal frames: CPU idle.** Main thread finished BUILD and is spinning in `waitForGameFrame` polling `$D011` bit 7. **[MEAS]** `waitForGameFrame` entered at raster 223–233; no traced engine event `≥ raster 200` on 375/400 frames; IRQ silent after raster 72. | `waitForGameFrame` spin | none | — |
| ~256 | `$D011` bit 7 set → `waitForGameFrame` releases → next frame | — | — | — |

**[MEAS] Cadence.** `rasterFrameReset` total-cycle deltas over 400 frames
cluster at **19,656 ± 3** (trace-sample jitter from IRQ-entry latency, not real
drift). The project's own cycle-exact `--physical` harness (raster-311 capture)
reports **exactly `[19656]`** on every documented run
(`docs/sort-and-free-baseline-worklog.md`, `docs/encounter-budget-worklog.md`,
`docs/scroll-hitch-worklog.md`). **[DOC]**

**[OBS] Frame-loop order** (`main.asm:537–599`): `waitForGameFrame →
publishTurretGlyphs → applyFineScroll → swapRenderPlans → renderSprites →
armFirstBatch → finishBackgroundCoarse →` *(loop body)* `updateTurret* /
updateObjects / updateEnemyFire / updatePlayerState / updateSpawner /
updateBackgroundScroll / buildSortedObjectList / sortObjectsByY /
buildInitialSpriteSnapshot / buildBatchSpriteSchedule /
planCoarseBulletSuppression / prepareBackgroundCoarse / refreshScoreIfDirty →`
loop.

**[INF] The only two things that ever touch rasters 234–311 today are: (a) the
`waitForGameFrame` CPU spin (does nothing), and (b) `prepareBackgroundCoarse`'s
upper-row copy on 1-in-16 frames, ending at raster ~272.** The lower border is
dead space. There is a large, mostly-idle terminal window.

---

## 2. Lowest legal gameplay sprite usage

### 2.1 Render cull boundary — [OBS]

`main.asm:47` `.const GAMEPLAY_SPRITE_END_Y = 246   // Exclusive`.
`buildSortedObjectList` (`main.asm:2605–2625`): any active object with
`OBJECT_Y ≥ 246` is dropped from `SORTED_OBJECTS` and **owns no VIC slot**.
Objects with `Y < GAMEPLAY_SPRITE_CLIP_MIN_Y` (51) are also dropped;
`51 ≤ Y < 71` straddlers are kept and rendered top-clipped through raster 72.

⇒ **the lowest Y origin a gameplay sprite can be programmed with is 245.**
**[MEAS]** forcing `OBJECT_Y = 245` for 8 objects: they entered the plan
(`RENDER_COUNT 8/8`), were scheduled, and a batch serviced them at raster 233.

### 2.2 Final sprite DMA of a Y=245 sprite — [INF] from VIC-II timing

A 21-px sprite at Y=245 has its body on rasters 245–265; the VIC performs its
sprite pointer + data DMA on each of those lines (and the tail of line 244).
**Final sprite DMA for the lowest legal gameplay sprite ≈ raster 265–266.**
No `$D017` write exists anywhere in the engine (`grep` — only `$D01C` at init),
so **no sprite is Y-expanded**; every sprite is exactly 21 px. Y-expansion does
**not** change the answer anywhere.

### 2.3 Safety margin before slot reuse — [OBS]

The multiplexer's own bookkeeping is `SLOT_FREE_RASTER[slot] = OBJECT_Y + 24`
(`main.asm:2933` and `:3074`); if `Y + 24` overflows 8 bits the slot is marked
`$ff` = "not reusable this frame". **[MEAS]**:

| Load | `SLOT_FREE_RASTER[0..7]` after BUILD |
| --- | --- |
| normal (8 obj, max Y 220) | `117 126 126 135 139 144 186 244` |
| dense (16 obj, Y 100–164) | `160 164 168 172 176 180 184 188` |
| **lowest-Y (obj at Y 234–245)** | `255 255 255 255 255 255 255 255` |

⇒ **When any gameplay sprite sits at `Y ≥ 232` (`232+24 = 256`), the mux marks
its slot permanently unavailable for the rest of that frame.** In the worst legal
case *every* slot can be `$ff`. The conservative reuse point for a slot holding a
Y=245 sprite is **raster ~267** (body scanned out + one line of DMA settle).

### 2.4 Special cases — [OBS]

- **Explosions / death animation:** `OBJECT_DEATH_TIMER` gates them; they are the
  same logical objects, same `OBJECT_Y`, same cull at 246. No lower-Y path.
- **Player death / respawn / blink:** `PLAYER_STATE` drives a state machine;
  the player object keeps its `OBJECT_Y` and the same 71..245 clamp
  (`main.asm:1657`, `:1782`, `:2132` all `cmp #GAMEPLAY_SPRITE_MIN_Y`). No
  special low-Y sprite.
- **Enemy bullets:** `updateEnemyBullets` deactivates at `Y ≥ 250`
  (`main.asm:2326`) — but the render cull at 246 removes them from the plan
  first, so a bullet is *alive but unrendered* for Y 246–249. Rendered bound
  is still 245.
- **Turrets:** background turrets are drawn in the **character matrix**
  (`background_turrets.asm`, private glyph codes), **not hardware sprites**. They
  consume zero hw sprite slots and impose no low-Y sprite case.
- **Vertical wrap / bottom despawn:** no routine deliberately services a sprite
  "just below the edge". The 246 cull is a hard stop; nothing renders lower.
- **Player slot 0:** the player is logical object 0 but is **not pinned to
  hardware slot 0** — `renderSprites` places it wherever its Y-sort rank falls
  and records the slot in `PLAYER_HW_MASK` (`main.asm:3460–3463`). **[INF]** no
  hardware slot is permanently reserved; any of the 8 can be free after gameplay.

**Answer to §2:** lowest legal sprite Y = **245**; final DMA ≈ raster **265–266**;
safe reuse of that slot ≈ raster **267**; no expansion effect; no special state
goes lower; player imposes no slot pin.

---

## 3. Safe HUD handoff point

### 3.1 What the render plan already knows — [OBS]

`buildBatchSpriteSchedule` (`main.asm:2914–3118`) already computes, per hardware
slot, the raster at which the slot's current gameplay sprite is finished:
`SLOT_FREE_RASTER[slot]` (= `Y + 24`, or `$ff`). This array is **BUILD-plan
scratch in zero-ish RAM** and is fully populated by the time `swapRenderPlans`
runs. It is **not currently published to LIVE**.

The batch schedule also stores `BATCH_RASTER[b] = min(Y−12)` for each batch — the
IRQ compare line — so `max(BATCH_RASTER)` over the LIVE plan is the raster of the
*last scheduled mux event*.

### 3.2 Simplest robust derivation — [INF]/[REC]

A single global **`HUD_SAFE_RASTER`** is enough and is cheap to produce:

```
HUD_SAFE_RASTER = max over used slots of ( SLOT_FREE_RASTER[slot], treating $ff as 268 )
```

- On a normal frame this is ~244 **[MEAS]**; on a dense low frame ~188; on the
  worst legal low-Y frame it saturates at **268**.
- Producing it costs an 8-iteration `max` loop (~60–90 cycles) appended to
  `buildBatchSpriteSchedule`, writing one byte that `swapRenderPlans` copies
  into a LIVE-published `HUD_SAFE_RASTER_LIVE`. **No mux restructuring.** The mux
  loop, slot choice, batch payloads and order are untouched.
- The terminal HUD raster event then simply schedules itself at
  `max(HUD_SAFE_RASTER_LIVE, FIXED_HUD_FLOOR)` where `FIXED_HUD_FLOOR` is a
  proven constant (see §5) — the compare is set exactly like every other event
  in `dispatchRasterEvents`.

Per-slot release times are also available (the raw `SLOT_FREE_RASTER` array) if a
future HUD wants to hand slots over individually as the beam passes each — but
the single global line is the **simplest robust** option and is recommended for
a first implementation.

**[INF]** The information is already there. The handoff is a *read* of existing
BUILD output plus one published byte, not new plan machinery.

---

## 4. How many hardware sprites for the HUD

**[OBS]** After the last gameplay batch, every one of the 8 slots is reusable
(no permanent reservation, §2.4). The constraint is *time*, not *count*:

| HUD sprites | Available after gameplay? | Setup cost (X,Y,ptr,colour,`$D010`) | Fits before border visible? | Notes |
| ---: | --- | --- | --- | --- |
| **2** | Always. | ~2 × (5 stores) + 1 `$D010` + 1 `$D015` ≈ **34 cyc** | Easily (border at raster ~251; setup at ~245). | ~48 px HUD width. Trivial. |
| **4** | Always. | ~64 cyc | Yes. | ~96 px. Score + lives comfortably. |
| **6** | Always. | ~92 cyc | Yes. | ~144 px. Score + lives + weapon + bombs. |
| **8** | Yes, but on the **worst legal low-Y frame** the last gameplay sprite's slot is not safe until raster ~267 (§2.3). Using all 8 forces the HUD setup to raster ≥ 267 on those frames, or requires clamping gameplay sprites (§10). | ~120 cyc + restore | Border must already be open by then (RSEL flip at ~250, §5) so raster 267 is inside the open border — OK. | ~192 px, full-width, Slap-Fight-equivalent. |

**Width:** 8 sprites × 24 px = 192 px un-expanded; the playfield is 320 px, so a
full-width HUD needs `$D01D` X-expansion (48 px each → 384 px, clip to 320) —
one `$D01D` write in setup, one to clear in restore. `$D01D` is currently never
touched, so this is additive.

**[REC] Start with 4 sprites** (score digits + a lives group), un-expanded,
placed centred/low. It is unconditionally safe on every legal frame with margin,
costs < 70 cycles to arm, and proves the whole pipeline. Grow to 6–8 later once
the low-Y clamp question (§10) is settled.

**[OBS]** No slot must stay untouched for the player or the mux: `renderSprites`
rewrites all `RENDER_COUNT` slots from scratch at the top of every frame, so
whatever the HUD phase leaves in a slot is overwritten before the next gameplay
use — provided the HUD phase restores `$D015` / `$D010` / colours to a known
baseline (see §7).

---

## 5. Lower-border opening requirements

### 5.1 The blocking fact — [OBS] + VIC-II border FF rules

The vertical border flip-flop is **set** (border on) at cycle 0 of
raster **251** (RSEL=1) or raster **247** (RSEL=0), and **reset** at raster 51
(RSEL=1) / 55 (RSEL=0). Once set it stays set until the reset compare **next**
frame. The engine runs **permanent RSEL=0**, so **the lower border closes at
raster 247 every frame and cannot be re-opened later in the same frame by any
`$D011` write.**

⇒ **From permanent RSEL=0 you cannot get a deep open lower border.** The only
trick available from RSEL=0 is to flip to **RSEL=1 before raster 247**: RSEL=0's
"close at 247" is then missed and RSEL=1's "close at 251" applies, yielding a
**4-line strip (raster 247–250)** of extra open area. Not enough for a sprite
HUD (needs ~20–40 lines).

### 5.2 The Slap-Fight relationship, proven for our timing — [INF]

To open a *deep* lower border you must be in **RSEL=1** up to raster 250, then
force **RSEL=0 during raster 250** so the RSEL=1 "close at 251" compare misses
and the RSEL=0 "close at 247" is already long past:

```
; at raster 250, inside H-blank of our display-safe window
lda RASTER_DISPLAY_D011_RSEL1   ; = $1B | fine  (YSCROL=fine, RSEL=1, DEN=1)
...
lda #<value with RSEL=0>        ; $13 | fine
wait: cpx RASTER / cpx #250 / bcc wait
sta $d011                       ; RSEL 1 -> 0 at raster 250; 251 compare misses
; border now stays OPEN from 251 to vblank
```

then during vblank (raster ~260–300 or at raster 0) restore `$D011` to
`RSEL=1 | fine` for the next gameplay frame — exactly the Slap Fight "at raster 0
restore RSEL=1" step.

- **Which line/cycle forces RSEL:** raster **250**, in the horizontal-blank
  window our display hook already proves is write-safe (the hook's
  `rasterHblankDelay` + poll pattern at rasters 62/63/70 is the template —
  9 cycles of poll slack fit the H-border, `raster_scheduler.asm:307–315`).
- **What runs there today:** on a normal frame, **nothing** — the IRQ is silent
  after raster 71 and the main thread is spinning (§1.2). On a coarse frame the
  main thread is mid upper-row copy (screen-RAM writes only, no VIC, fully
  preemptible by a short IRQ). **[MEAS]** no traced engine VIC write occurs at
  raster 234–311 on any of 400 frames except the coarse copy (screen RAM).
- **Badline / DMA / IRQ collision at raster 250:** no badline (badlines are
  rasters 48–247 only; 250 is past the last one), no sprite DMA for a gameplay
  sprite whose Y ≤ 245 has already started its body — a Y=245 sprite is on body
  line 5 at raster 250, so its slot is mid-DMA. **This is why the RSEL write and
  the HUD *sprite* writes are different problems:** the `$D011` RSEL flip does
  not touch sprite state and is safe at raster 250 regardless; the *HUD sprite
  register* writes must wait for `HUD_SAFE_RASTER` (§3), which on a worst-case
  low-Y frame is ~267 — comfortably inside the now-open border.
- **When RSEL can return to 1:** any time after raster 251 and before raster 251
  next frame; the natural point is the terminal phase's own tail, or `$D011 =
  $17`-equivalent at `rasterFrameReset`. Our `rasterFrameReset` already writes
  `$D011 = $17` every frame (`raster_scheduler.asm:106`) — that constant would
  change to `$1F` (RSEL=1) and the display hook would re-assert RSEL per phase.
- **ECM masking:** Terra Cresta / Slap Fight `ora #$40` (ECM) during the flip is
  a *belt-and-braces* to blank any half-fetched matrix data in the transition
  line. **For us it is optional.** Our transition line (raster 250) is below the
  last badline (247) so no matrix fetch is pending there; a blank `$D021`
  spacer row (§6) already guarantees clean pixels. Recommend **not** using ECM
  (it is the exact mechanism behind the current top "HUD glitch"; keeping it out
  of the bottom path avoids repeating that class of bug). Optional fallback only.

### 5.3 Can gameplay stay RSEL=1 / 25 rows without the bottom pop coming back?

**[INF] Yes — but only with a blank `$D021` spacer row masking the seam**, not by
RSEL timing alone. Reasoning:

- In RSEL=1 the aperture is 51–250. The historical 7→0 bottom pop is the
  outgoing matrix row snapping height 4→0 at rasters **248–250**
  (`docs/scroll-edge-investigation.md`). Those pixels are *rendered* in RSEL=1.
- Flipping to RSEL=0 *before* raster 247 would border-mask 247–250 (killing the
  pop) **but also closes the border** — you cannot then have a HUD below. The
  border FF cannot be closed at 247 and re-opened at 251 in one frame (§5.1).
- Therefore, to keep the border open for the HUD, rasters 248–250 must be
  displayed, so the pop must be removed **at the source**: reserve **matrix row
  24** as a permanent **blank `$D021` character row** (an all-background glyph).
  A blank row has no foreground bits, so there is no height-4→0 foreground snap —
  rasters ~243–250 show solid `$D021`, pop gone, for *any* palette. This is the
  identical fix already planned for the top separator, applied symmetrically.
- Symmetrically, the RSEL=1 **top** idle strip (rasters 51–55) re-appears once
  the RSEL=0 top crop is gone; **matrix row 0** as a blank `$D021` spacer masks
  it the same way (and is where the current fixed HUD glyphs live — see §6/§13).

**[INF] Net:** RSEL=1 gameplay with row-0 and row-24 blank `$D021` spacers gives
**23 clean terrain rows (1–23) with no top or bottom scroll pop and no
invalid-mode band**, and the Slap-Fight RSEL flip at raster 250 keeps the lower
border open for the sprite HUD. This is the "option C" architecture.

---

## 6. Recoverable gameplay area

RSEL=1 aperture = raster 51–250 = **200 px / 25 char rows** of *fetched* image.
Char rows and their raster spans (fine 3 canonical): row *r* ≈ raster `51 + 8r`
… `58 + 8r`.

| Arch | Matrix use | Visible gameplay | Rows | HUD px | Top crop | Bottom crop | Scroll-seam tradeoff |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| **A. Current fixed-HUD baseline** | r0 HUD, r1–23 terrain, r24 unused; RSEL=0 | **176 px** | **22** | 8 (char HUD) | 4 (RSEL=0) | 4 (RSEL=0) | pop masked by RSEL=0 bottom crop; top has the invalid-mode band |
| **A′. Planned separator fix** (independent baseline) | r0 HUD, r1 blank `$D021`, r2–23 terrain; RSEL=0 | ~168 px | ~21 | 8 | 4 | 4 | band replaced by clean `$D021`; still RSEL=0 |
| **B. Bottom-border sprite HUD, keep permanent RSEL=0** | r0 free, r1–23 terrain, r24 unused; RSEL=0; only the 4-line 247–250 strip openable | **~184 px** (r0..r23 minus top/bottom cushions) | **~23** | ~4–12 (thin sprite strip in raster 247–~258 only) | 4 | 0–4 | pop must be masked by a blank r24 or a residual RSEL=0 crop; HUD is *shallow* — cramped |
| **C. Bottom-border sprite HUD, Slap-Fight RSEL flip** | r0 blank `$D021` spacer, r1–23 terrain, r24 blank `$D021` spacer; RSEL=1 → RSEL=0 at raster 250 | **184 px** (rows 1–23) | **23** | **~30–40** px sprite HUD in raster ~255–292 | 0 (row 0 spacer) | 0 (row 24 spacer) | **no pop, no band, any palette** |
| **C′. As C, but no top HUD/spacer needed → row 0 becomes terrain** | r0–23 terrain, r24 blank `$D021` spacer; RSEL=1 → RSEL=0 at 250 | **~192 px** | **24** | ~30–40 | tiny residual top idle strip (~4 px, `$D021`-ish) or accept | 0 | top idle strip returns unless a 4-px top cushion is kept |

**[INF]** The task's **~192–200 px** target is reachable via **C′** (192 px / 24
rows) if a ~4-px top idle strip is tolerated or cheaply cushioned; **C** delivers
a rock-solid **184 px / 23 rows** (+8 px / +1 row over today) with *both* seams
clean and the top band gone. **B** (staying permanent RSEL=0) yields only a
cramped ~4–12 px HUD strip and is not worth the complexity.

---

## 7. Multiplexer interaction

**[OBS] The "multiplexer" and the "raster scheduler" are the same code.**
`multiplexIRQ` is `jmp rasterIRQ` (`main.asm:3508`); `rasterIRQ` dispatches
`RASTER_EVENT_FRAME` / `RASTER_EVENT_SPRITES` / `RASTER_EVENT_DISPLAY`
(`raster_scheduler.asm:81–103`). Sprite batches ARE
`applyLiveRasterBatch`. A bottom HUD is therefore literally **one more
`RASTER_EVENT` value dispatched after the last `RASTER_EVENT_SPRITES`** — the
`dispatchRasterEvents` "merge the fixed display hook with the next ordinary
batch" pattern (`raster_scheduler.asm:171–237`) is the exact template.

### 7.1 State that must be preserved / restored — [OBS] + [INF]

| Register | Written per frame by | HUD phase must… |
| --- | --- | --- |
| `$D000–$D00F` X/Y | `renderSprites` (top of frame), `applyLiveRasterBatch` | overwrite for HUD, then **restore is free**: `renderSprites` rewrites all of it next frame before any gameplay use. No save needed if HUD phase is the last event. |
| `$D010` X-MSB | `renderSprites`, `applyLiveRasterBatch` (`BATCH_X_MSB_MASK`) | set for HUD; next `renderSprites` writes `SPRITE_OVERFLOW_REGISTER` from `TEMP_MSB` — restored automatically. |
| `$D015` enable | `renderSprites` (`SPRITE_ENABLE_MASK,x` for `RENDER_COUNT`), `endGame` | HUD may widen the enable mask; next `renderSprites` reasserts it. **But** if HUD enables slots the next frame's `RENDER_COUNT` is `< 8`, those extra slots stay enabled showing stale HUD until `renderSprites` — so **HUD phase should restore `$D015` to the LIVE `RENDER_COUNT` mask in its own tail**, OR always leave `$D015 = $FF` and rely on off-screen Y. Cheapest: restore in tail (~6 cyc). |
| `$D027–$D02E` colour | `renderSprites`, `applyLiveRasterBatch` | overwrite for HUD; auto-restored next `renderSprites`. |
| `$07F8–$07FF` pointers | `renderSprites`, `applyLiveRasterBatch` | overwrite for HUD; auto-restored. |
| `$D01C` MC mode | init only (`$FF`) | **leave alone** — HUD sprites are MC too, or set per-sprite in setup if a hires HUD sprite is wanted (one write, restore in tail). |
| `$D025/$D026` shared MC colours | init only | leave alone, or save/restore the pair if the HUD needs different shades (2 + 2 writes). |
| `$D01D` X-expand | **never** | if HUD wants full width: set in setup, **clear in tail** (else next gameplay sprites are 48 px wide — visible artefact). Mandatory restore. |
| `$D01B` priority | **never** | leave 0. |
| `$D011` RSEL bit | `init`, `rasterFrameReset` (`$17`), `rasterDisplayHook` per phase | the RSEL-flip design (§5) changes `rasterFrameReset`'s constant to `$1F` and adds one RSEL-0 write at raster 250 + implicit RSEL-1 restore at frame reset. Bounded. |
| `$D01E` collision latch | read+cleared by `capturePlayerCollision` at frame top | HUD sprites overlapping in the border **will latch bits**. Defended: the software confirm (`checkCapturedPlayerCollision`) gates on `71 ≤ OBJECT_Y < 246`, so a border-only overlap cannot raise `PLAYER_HIT` (it wastes one scan). **Clean fix: `lda $D01E` (dummy read to clear) at the end of the HUD phase.** 1 instruction. |

### 7.2 Does the HUD corrupt next-frame assumptions? — [INF]

**No, provided the HUD phase is the terminal event and restores `$D015` (+
`$D01D` if used) in its tail.** `renderSprites` is a full rewrite of `$D000–$D00F,
$D010, $D027–$D02E, $07F8–$07FF, $D015` from `LIVE_PLAN` at the top of every
frame, *before* `armFirstBatch` and before any gameplay compare. The BUILD/LIVE
swap (`swapRenderPlans`, `main.asm:3408`) is untouched — the HUD reads no plan
data, only `HUD_SAFE_RASTER_LIVE`. Collision plumbing is untouched (`$D01E` dummy
read closes the one hole). Enable/disable sequencing artefact: only if `$D015`
is left wide — hence the mandatory tail restore.

**[REC] Preferred result achieved:** the HUD is **an extra terminal raster phase
appended to the existing scheduler**, ~8–12 new instructions in
`dispatchRasterEvents` + a small `hudBorderHook` routine. **No multiplexer
rewrite.**

---

## 8. Terra Cresta / Slap Fight multiplexer techniques vs ours

| Technique | Our engine | Classification |
| --- | --- | --- |
| Y-sorted just-in-time IRQ scheduling | `sortObjectsByY` + `buildBatchSpriteSchedule` batches at `min(Y−12)` | **already equivalent** |
| `≈ Y − 14` service lead | Ours is `Y − 12` (`main.asm:2987`), plus the `dispatchRasterEvents` "≥3 lines / DMA lead" guard | **already equivalent** (2 lines tighter; leaves it) |
| Late-service fallback | `dispatchRasterEvents` `!near`/`!due` path spins to target then services + `inc RASTER_CATCHUPS`; `rasterFrameReset` replay path | **already equivalent** (arguably more robust — full replay) |
| Mask tables for `$D010` | `BATCH_X_MSB_MASK` prepared in BUILD (`beginRasterPlanMasks`/`extendRasterPlanMasks`), applied as one `sta SPRITE_OVERFLOW_REGISTER` per batch | **already equivalent** (BUILD-time, better) |
| Hardware-slot → VIC register-offset table | `HW_SPRITE_OFFSET,x` (`main.asm:3470`), `HW_BIT_MASK` / `HW_CLEAR_MASK` | **already equivalent** |
| Compact state representation | parallel `ASSIGN_*` arrays + `BATCH_*` arrays; 16-entry pools | **already equivalent** |
| HUD = time-domain slot reuse, no reservation | not present yet — **this is exactly what the bottom HUD would add** | **the technique to adopt** |
| Terminal border phase integrated into the raster state machine | not present — **add as one `RASTER_EVENT`** | **potentially useful — recommended** |
| ECM blank during the flip | present as the *top* separator (the current glitch) | **unsuitable for the bottom path** — avoid |

**[INF] No multiplexer optimisation is warranted.** Our hot path already
implements every cheap trick the two commercial engines use, and BUILD-time mask
precomputation puts us slightly ahead. The only thing worth taking is the
*architectural* idea of a terminal border phase reusing slots — which this
investigation already recommends as an additive event, not a rewrite. Estimated
benefit of any mux micro-opt: **negligible** (< 50 cyc/frame) and not worth the
regression risk against `[19656]` + 0-miss invariants.

---

## 9. Cycle-budget analysis

### 9.1 Measured free budget — [MEAS] + [DOC]

- **Frame cadence:** exactly **19,656 cyc** (`--physical` harness, all documented
  runs). My 400-frame trace: 19,656 ± 3 (sampling jitter).
- **Main-thread BUILD worst case:** `docs/sort-and-free-baseline-worklog.md`
  Task D — sort worst case **4,373 cyc** (was 10,673); full BUILD path
  historically measured with headroom to spare (FREE-cycle diagnostic disabled
  precisely because it *itself* cost enough to perturb coarse admission —
  `main.asm:575–583`).
- **Terminal idle window (normal frame):** **[MEAS]** `waitForGameFrame` entered
  at raster **223–233**; no engine event after raster 72; frame boundary
  ~raster 311. ⇒ **≈ (311 − 230) × 63 ≈ 5,100 free CPU cycles** in the tail,
  every normal frame, doing nothing but polling `$D011`.
- **Terminal window (coarse frame, 1-in-16 at divider 2):** the upper-row copy
  runs raster ~160 → **271–272** **[MEAS]**, then ~(311 − 272) × 63 ≈ **2,450
  free cyc** after it.
- **Latest mux activity:** raster **233** in the worst forced low-Y load
  **[MEAS]**; raster 71 on 375/400 normal frames.

### 9.2 Expected added cost of a bottom-border HUD — [INF]

| Item | Where | Cycles/frame |
| --- | --- | --- |
| `HUD_SAFE_RASTER` max-loop | append to `buildBatchSpriteSchedule` (BUILD, main thread) | ~70 |
| publish `HUD_SAFE_RASTER_LIVE` | `swapRenderPlans` | ~6 |
| extra `RASTER_EVENT` dispatch overhead | `dispatchRasterEvents` per frame | ~20 |
| RSEL flip write @ raster 250 (`hudBorderHook`) | IRQ | ~15 (poll) + `sta` |
| HUD sprite setup: 4 sprites × (ptr,colour,X,Y) + `$D010` + `$D015` | IRQ, once armed | **~70** (4 sprites); ~120 (8) |
| tail restore: `$D015`, (`$D01D`), dummy `lda $D01E` | IRQ | ~12 |
| RSEL-1 restore | folded into `rasterFrameReset` constant change | ~0 |
| **Total (4-sprite HUD)** | | **≈ 190 cyc/frame** |
| **Total (8-sprite full-width HUD)** | | **≈ 270 cyc/frame** |

### 9.3 Margin remaining — [INF]

- **Normal frame:** ~5,100 free tail cycles − ~190 = **~4,900 spare.** Trivial.
- **Coarse frame:** the HUD IRQ (~110 cyc of IRQ-side work) *preempts* the
  upper-row copy; the copy still has ~2,450 spare after raster 272 and the HUD
  IRQ pushes its completion by ~110 cyc → **~2,340 spare.** Comfortable, but this
  is the tightest case and must be in the timing tests.
- **`[19656]` invariant:** unaffected — all added work is inside the existing
  frame, none of it moves `rasterFrameReset`.

---

## 10. Failure modes

| Mode | Analysis | Severity | Mitigation |
| --- | --- | --- | --- |
| Gameplay sprite still active when HUD steals slot | Worst legal: Y=245 sprite, slot busy to raster ~267. If HUD arms at `HUD_SAFE_RASTER` (≥ that), **no collision**. If a fixed floor < 267 is used and a low-Y sprite exists → mid-sprite Y rewrite → **the sprite re-triggers at the new (HUD) Y**, a visible double / stretch. | **High if mishandled** | Use `HUD_SAFE_RASTER` (§3), not a blind floor. Optionally clamp gameplay `GAMEPLAY_SPRITE_END_Y` to ~228 so slots are always free by ~252 (costs ~1 row of enemy travel at the very bottom — enemies are already exiting there). |
| HUD sprite DMA starts too early | HUD sprite Y in the open border (≥ ~255). If armed before its Y is passed *and* Y > current raster, it displays this frame — desired. If Y < current raster when armed, it displays *next* frame (one-frame HUD delay on the very first frame only). | Low | Arm with HUD Y a few lines below `HUD_SAFE_RASTER`; steady-state is stable. |
| Border-open `$D011` write misses raster 250 | If late (raster ≥ 251) the RSEL=1 "close at 251" already fired → border closed → **no HUD this frame** (flicker). | Medium | Same H-blank poll pattern the display hook already uses reliably (`raster_scheduler.asm:307`); 9-cycle slack. Event compare set at raster ~246. |
| Badline interaction | Last badline is raster 247. The raster-250 flip and the ≥255 HUD writes are **past all badlines**. No stolen-cycle uncertainty. | None | — |
| Coarse-scroll wrap interaction | Upper-row copy runs to raster ~272 on coarse frames; the HUD IRQ preempts it (screen-RAM copy is fully interruptible). ~2,340 cyc spare after (§9.3). Stage wrap adds ~10 cyc to one coarse frame per full circuit (`prepareBackgroundCoarse` `!stageNoWrap`) — geometry unchanged. | Low | Include a divider-1 + forced-wrap run in the timing battery. |
| All 8 fine-scroll phases | The RSEL flip value is `RSEL0 \| fine`; fine only affects YSCROL (bits 0–2), RSEL is bit 3 — **orthogonal**. The blank `$D021` spacer rows (§5.3) make the seam phase-independent. | Low | Test all 8 (the harness cycles them naturally). |
| Lowest-Y enemy / projectile / explosion | Covered: render cull at Y 246 → lowest sprite Y 245 → `HUD_SAFE_RASTER` saturates at ~268 (§2, §3). Explosions/bullets impose nothing lower. | Handled by design | — |
| Player death / respawn / blink | Player is a normal object, same Y clamp, no low-Y special case, not slot-pinned (§2.4). | None | — |
| No enemies | `SORTED_COUNT` small, `HUD_SAFE_RASTER` ≈ player `Y+24` (often < 200). HUD arms early, displays full. | None | — |
| Maximum enemies | 16 objects, 8 batched. `HUD_SAFE_RASTER` = latest `SLOT_FREE_RASTER`. If several are low-Y, arms at ~268. Border already open. | Low | Dense + low-Y stress run. |
| Stage wrap | See coarse row above. | Low | — |
| Title / menu / GAME OVER | `endGame` clears the raster IRQ, restores KERNAL, `$D015 = 0` (`main.asm:607–623`). The HUD event only exists while `multiplexIRQ` is installed. Menu uses RSEL=1 already (`> d011 1b` in harness / KERNAL default). **Must** ensure the RSEL-flip design's `rasterFrameReset` change doesn't leak into menu (it can't — IRQ disabled). | Low | Lifecycle test (`tools/vice_raster_lifecycle.py` already exercises death→menu→restart). |
| Collision-register side effects | `$D01E` border overlap latched; software confirm gates on Y∈[71,246); add a dummy `lda $D01E` in the HUD tail. | Low | 1 instruction. |
| VIC state leaking to next frame | `$D015` / `$D01D` are the only ones not auto-rewritten by `renderSprites`. Tail restore both. | Medium | Mandatory tail restore; assert in a capture test. |
| HUD flicker from varying final gameplay batch | `HUD_SAFE_RASTER` varies frame-to-frame (188…268). HUD *arm raster* therefore varies, but HUD *sprite Y* is fixed → the HUD position is stable; only the arm line moves, invisibly. | None | — |
| NTSC | NTSC has 262/263 lines, border compares at 234/25 (RSEL=1) / 238/29 (RSEL=0), ~65 cyc/line. The raster-250 flip and ≥255 HUD would fall *below* the NTSC visible field. **NTSC would need its own flip raster (~232) and HUD band.** PAL is authoritative; NTSC is a separate port problem. | Out of scope | Note only. |

---

## 11. Isolated proof

**Not built.** Static analysis + the one read-only measurement probe resolved
every feasibility question:

- lowest sprite Y (245) and its slot-release raster (~267) — **[MEAS]** via
  `SLOT_FREE_RASTER` snapshots and a forced Y=245 batch firing at raster 233;
- the terminal window is idle on normal frames and coarse-copy-bound to
  raster ~272 on 1-in-16 frames — **[MEAS]** trace classification of 400 frames;
- cadence stays `[19656]` — **[MEAS]** + **[DOC]**;
- the border-FF "cannot reopen after RSEL=0 closes it at 247" rule — VIC-II
  reference, deterministic, no probe needed;
- the RSEL=1-gameplay + flip-at-250 + `$D021`-spacer path — geometric/timing
  derivation from the border-FF rules and the existing display hook.

The one remaining *empirical* unknown — **exact visible extent of the open lower
border on this PAL `x64sc` config, across all 8 fine phases** (how many rasters
below 251 are actually drawn before overscan / vblank) — should be measured by
the **first task of the implementation branch** (a static marker sprite in the
opened border), not now. It changes the HUD's pixel height, not its feasibility.

**Probe file:** `scratchpad/probe_bottomhud.py` (session scratchpad, **outside
the repo**, not committed). Reads-only via the VICE monitor; emulator killed on
exit. Nothing to revert in the repo.

---

## 12. VICE validation performed

Background `x64sc` (`-remotemonitor`, no focus steal), current
`build/shooter.prg`, Level 1, driven to PLAYING with one joystick fire press.

| Check | Result |
| --- | --- |
| Physical cadence, ~400 frames | `rasterFrameReset` deltas 19,656 ± 3 (trace jitter); `--physical` harness `[19656]` exact — **[DOC]** |
| Fine-scroll phases | 400 frames = 25 full 16-frame fine cycles → all 8 phases + 25 coarse 7→0 transitions exercised |
| Coarse 7→0 transition | 25/400 frames; `bgUpperReady` (upper copy done) at raster **271–272** every time |
| Latest raster IRQ / mux activity | raster **71** on 375/400 frames; raster **233** with 8 sprites forced to Y=245; **no** traced VIC write at raster 234–311 except the coarse screen-RAM copy |
| Idle-tail start | `waitForGameFrame` entered at raster **223–233** |
| Ordinary wave load | normal spawner: `SLOT_FREE_RASTER` ≤ 244, ≤ 8 objects, 0 batches |
| Dense load (16 stationary legal objects) | `SLOT_FREE_RASTER` 160–188; all slots free by raster 188 |
| Lowest legal sprite layout (Y=245 ×8) | `SLOT_FREE_RASTER` = `$ff` ×8; batch services them at raster 233; body/DMA to ~raster 266 |
| Service / sprite-start misses, catchups, replays | none observed; consistent with **[DOC]** 0-miss battery |
| Stage wrap | not driven to a full 400-logical-row circuit this session; geometry-independent per `prepareBackgroundCoarse` read; covered by **[DOC]** scroll-hitch battery |

No repo file was written. VICE was never foregrounded.

---

## 13. Current vs proposed frame diagram

```
CURRENT (permanent RSEL=0)                 PROPOSED "C" (RSEL=1 gameplay + flip@250)
------------------------------------       ------------------------------------------
r51-54  border (RSEL=0 top crop)           r51-58  matrix row 0 = BLANK $D021 spacer
r55-62  fixed char HUD (row 0)                     (masks top idle strip; today's
r63-70  BLACK invalid-mode band  <-glitch          HUD glyphs move to sprites)
r71-246 terrain rows 1-23 (176px/22)       r59-242 terrain rows 1-23 (184px/23)
r247-250 border (RSEL=0 bottom crop,       r243-250 matrix row 24 = BLANK $D021
         masks 7->0 pop)                            spacer (masks 7->0 bottom pop)
r251+   LOWER BORDER - closed, dead        r250    $D011: RSEL 1 -> 0  (251 compare
                                                    misses; border stays OPEN)
                                           r255-292 OPEN LOWER BORDER:
                                                    4-8 HUD sprites (score/lives/...)
                                                    armed at HUD_SAFE_RASTER (>=~235,
                                                    <=~268 worst legal case)
                                           r~300   vblank; rasterFrameReset writes
                                                    $D011 = $1F (RSEL back to 1)
                                           r0-15   renderSprites rewrites all 8 slots
                                                    for gameplay -> HUD auto-cleared
```

---

## 14. Recommendation

# AMBER

**A bottom-border sprite HUD is feasible with an additive terminal raster phase
and no scroller or multiplexer rewrite — but it requires changing one current
invariant: the permanent `RSEL=0` / 24-row display must become a per-frame
`RSEL=1`-gameplay / `RSEL=0`-at-raster-250 flip (Slap-Fight style).**

**Why that invariant must change (measured / derived, not hypothesised):**
the vertical border flip-flop, once set by the `RSEL=0` compare at **raster 247**,
cannot be re-opened for the rest of the frame by any `$D011` write (VIC-II border
rule). From permanent `RSEL=0` the only openable lower strip is **4 lines
(raster 247–250)** — far too shallow for a sprite HUD. A deep open lower border
*requires* being in `RSEL=1` up to raster 250 and flipping to `RSEL=0` there so
the `RSEL=1` "close at 251" compare misses.

**Why it is not RED:** everything else lines up. **[MEAS]** the terminal window
(raster ~233 → 311) carries **zero** scheduled VIC work on normal frames and only
a preemptible screen-RAM copy (to raster ~272) on 1-in-16 coarse frames, leaving
**~5,100 free tail cycles** normally and **~2,340** on the tightest coarse frame
against an expected HUD cost of **~190–270 cyc/frame**. **[OBS]** the render plan
already computes per-slot release rasters (`SLOT_FREE_RASTER`) so the handoff is a
read, not new machinery. **[OBS]** no hardware sprite is permanently reserved
(the player is not slot-pinned) and `renderSprites` fully re-arms all 8 slots at
the top of every frame, so a terminal HUD phase that restores `$D015` (+ `$D01D`
if used) and dummy-reads `$D01E` leaves no next-frame corruption. **[OBS]/[INF]**
`[19656]` is untouched — no added work moves `rasterFrameReset`.

**Why it is not GREEN:** `RSEL=0`-permanent is a protected display invariant, and
changing it re-exposes the top idle strip and the bottom 7→0 scroll pop that
`RSEL=0` currently border-masks. Those seams must be re-masked *at the source* —
by reserving **matrix row 0 and matrix row 24 as blank `$D021` spacer rows** (the
same fix already planned for the top separator, applied symmetrically). That is a
bounded, well-understood change to the display hook + one-time matrix setup, but
it *is* a real change to a protected area and to the RSEL constant in
`rasterFrameReset` / `rasterDisplayHook`.

### Proposed implementation plan (do NOT implement yet)

| Phase | Work | Files touched | Must NOT touch |
| --- | --- | --- | --- |
| **1. Final gameplay sprite release point** | Append an 8-slot `max` over `SLOT_FREE_RASTER` (`$ff` → 268) at the end of `buildBatchSpriteSchedule`; store `HUD_SAFE_RASTER`. Publish it in `swapRenderPlans` as `HUD_SAFE_RASTER_LIVE`. Add a BUILD guard that `GAMEPLAY_SPRITE_END_Y` bodies never require a release raster past a proven ceiling. | `main.asm` (`buildBatchSpriteSchedule`, `swapRenderPlans`), `raster_scheduler.asm` (state byte) | mux slot choice, batch payloads/order, `sortObjectsByY` |
| **2. Terminal handoff raster event** | New `RASTER_EVENT_HUD` after the last `RASTER_EVENT_SPRITES` in `dispatchRasterEvents`; compare = `max(HUD_SAFE_RASTER_LIVE, FIXED_HUD_FLOOR)`; new `hudBorderHook` routine. | `raster_scheduler.asm` (`dispatchRasterEvents`, `rasterIRQ`) | `applyLiveRasterBatch`, the DISPLAY hook body |
| **3. Lower-border RSEL transition** | `rasterFrameReset` constant `$17 → $1F`; `rasterDisplayHook` phase values gain RSEL=1 (`$1B\|fine` etc.); `hudBorderHook` writes `RSEL=0 \| fine` at raster 250 via the existing H-blank poll pattern. Reserve matrix row 0 + row 24 as blank `$D021` glyph rows in `initBackground` / `initFixedHud`; move the fixed HUD's score glyphs off the matrix. | `raster_scheduler.asm`, `main.asm` (`initBackground`, `initFixedHud`, `renderStageRowToScreen` row range) | the scroller's row 1–23 copy logic, coarse routines, `$D016`/`$D018`/VIC bank |
| **4. HUD sprite setup** | In `hudBorderHook` after `HUD_SAFE_RASTER`: write 4 sprites (ptr/colour/X/Y), `$D010`, widen `$D015`. Start with **4 sprites**, un-expanded, centred low. HUD content (score digits, lives) built in BUILD into a small `HUD_SPRITE_*` table like the fixed-HUD score digits are today. | `raster_scheduler.asm` (`hudBorderHook`), `main.asm` (HUD content build, ~`refreshScoreIfDirty` sibling) | `renderSprites`, BUILD/LIVE plan arrays |
| **5. Next-frame VIC restore** | `hudBorderHook` tail: restore `$D015` to the LIVE `RENDER_COUNT` mask, clear `$D01D` if used, dummy `lda $D01E`. RSEL→1 happens for free at `rasterFrameReset`. | `raster_scheduler.asm` | — |
| **6. Exhaustive timing tests** | All 8 fine phases; coarse 7→0 at divider 1 **and** 2; forced full stage wrap; ordinary wave; dense (16); lowest-Y (Y=245 ×8); player death/respawn/menu/restart lifecycle; ≥ 600 physical frames each. Assert `frame_cycle_deltas == [19656]`, 0 service/sprite-start misses, 0 replay/catchup regressions, `$D015`/`$D01D` clean at raster 0, no false `PLAYER_HIT` from border overlap, HUD stable across the varying `HUD_SAFE_RASTER`. Add `tools/check_border_hud_capture.py` + `tools/vice_border_hud_cases.py`; reuse `vice_scroll_test.py --physical/--dense/--stress`, `vice_raster_lifecycle.py`, `check_raster_capture.py`. | new `tools/*` | existing check scripts (extend, don't edit) |
| **7. Only then** reclaim top geometry | Once the bottom HUD is proven, drop the top fixed char HUD entirely (row 0 → terrain or a thin cushion), giving architecture **C′** (~192 px / 24 rows). Separate follow-up; not part of the HUD branch. | `main.asm`, `raster_scheduler.asm`, editor `VIEWPORT_ROWS` | — |

### Specifics

- **Start with 4 HUD sprites**, un-expanded (~96 px). Unconditionally safe on
  every legal frame; ~70 cyc to arm. Grow to 6–8 + `$D01D` after phase 6.
- **Expected gameplay-height gain:** **+8 px / +1 row** (176→184, arch C) with
  both scroll seams clean and the top invalid-mode band gone; **+16 px / +2 rows**
  (176→192, arch C′) once the top HUD is also removed (phase 7).
- **Expected cycle cost:** **~190 cyc/frame** (4-sprite HUD), **~270** (8-sprite
  full-width). Frame cadence `[19656]` unaffected.
- **Files that would be touched:** `src/raster_scheduler.asm` (dispatch + new
  `hudBorderHook` + `rasterFrameReset` constant + state bytes),
  `src/main.asm` (`buildBatchSpriteSchedule` max-loop, `swapRenderPlans` publish,
  `initBackground`/`initFixedHud` spacer rows + HUD-content build,
  `renderStageRowToScreen` row range), new `tools/check_border_hud_capture.py` +
  `tools/vice_border_hud_cases.py`, `docs/` worklog.
- **Files / routines that must remain untouched:** `sortObjectsByY`,
  `buildSortedObjectList` cull rule, `applyLiveRasterBatch` payload/order,
  `beginRasterPlanMasks`/`extendRasterPlanMasks`, `prepareBackgroundCoarse` /
  `finishBackgroundCoarse` / `shiftBackgroundUpper` / `shiftBackgroundLower` /
  `saveCrossingRow` / `restoreCrossingRow`, `swapRenderPlans` swap logic,
  the BUILD/LIVE arrays, `$D016` / `$D018` / VIC bank / screen matrix `$0400` /
  charset `$3800`, collision plumbing, `MAX_OBJECTS`, the encounter-budget
  policy, `build_levels.py`, all editor viewport geometry.

### Explicit unknowns carried forward

1. **Exact visible raster depth of the opened PAL lower border** on this
   `x64sc` config across all 8 fine phases → phase-6 marker-sprite measurement.
2. Whether `GAMEPLAY_SPRITE_END_Y` should be tightened (~228) to guarantee slots
   free by ~252 and permit an 8-sprite HUD without a late (~268) arm — a 1-row
   gameplay/robustness trade to decide in phase 1.
3. Interaction of the RSEL-flip with the **planned top-separator `$D021` fix**
   (they touch the same `rasterDisplayHook` phase constants) — sequence the two
   changes; do the separator fix first as its own baseline, as the brief directs.
4. NTSC (separate port; PAL authoritative).
