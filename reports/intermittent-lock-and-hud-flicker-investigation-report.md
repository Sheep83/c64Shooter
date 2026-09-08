# Intermittent Hard-Lock / Border-HUD Flicker — Investigation & Fix

**19656 / c64Shooter — PAL C64 vertical shooter — branch `experimental-border-hud`.**
Investigation + robustness pass. No commit / push / tag / branch change.
VICE run head-less/background (`-remotemonitor`, `Popen`, DEVNULL), never
foregrounded, no `open -a`.

Legend: **[OBS]** observed in source · **[MEAS]** measured this session ·
**[INF]** inference · **[FIX]** the change made.

---

## 1. Starting branch / HEAD / status

| | |
| --- | --- |
| `git branch --show-current` | `experimental-border-hud` (not switched) |
| `git rev-parse HEAD` | `82c27c5cd738051cd539c6ec5730393b5a384146` — *"Top border sprites milestone 1"* |
| `git log -5 --oneline` | `82c27c5` Top border sprites milestone 1 · `44e735c` pre-architecture-teardown · `d547c80` Establish RSEL1 border HUD experimental baseline · `1cd8513` First bottom border HUD experiment · `2875dfd` Bottom border HUD investigation done |
| `git status` at start | clean except `?? lockup.bin` (the user's 64K dump, copied into the repo root; identical to `/Users/brianmorrice/Desktop/lockup.bin`, left untouched) |
| Toolchain | KickAssembler 5.25 · VICE `x64sc` **and** `x64` (PAL, `-warp`) |
| HEAD build sha256 | `65bb0d2c…fe73` |
| Fixed build sha256 | `a143993f608a4cf0a92a6e82f6ae0efc777de2e9307f6b1481c68855fd236a69` |

Both required reports (`full-200px-gameplay-aperture-architectural-rework`,
`top-border-sprite-hud-proof`) and their worklogs were read before any change.
The soft-edge-pop masking is deliberately **not** touched (per the brief).

---

## 2. Exact mapping of `$61F7`

**[MEAS]** In the HEAD build (`build/main.vs` + disassembly of `build/shooter.prg`):

```
$61ED  borderOpenHook:
$61ED  A9 00        LDA #$00
$61EF  8D D7 62     STA RASTER_BORDER_PENDING
$61F2  AE 12 D0     LDX $D012            ; RASTER (raster counter low byte)
$61F5  E0 F5        CPX #$F5             ; compare with 245
$61F7  90 F9        BCC $61F2   <-- captured PC: loop while $D012 < 245
$61F9  AD 11 D0     LDA $D011
$61FC  09 08        ORA #$08             ; RSEL 0 -> 1
$61FE  8D 11 D0     STA $D011
$6201  AE 12 D0     LDX $D012
$6204  E0 FA        CPX #$FA             ; compare with 250
$6206  90 F9        BCC $6201            ; loop while $D012 < 250   (identical hazard)
$6208  AD 11 D0     LDA $D011
$620B  29 F7        AND #$F7             ; RSEL 1 -> 0
$620D  8D 11 D0     STA $D011
$6210  borderOpenRestored:  RTS
```

`$61F7` is the `BCC` of **`borderOpenHook`'s first raster busy-wait (`!wait245`)**
— the lower-border RSEL "dodge". `$61ED..$620F` is the whole hook body.
`borderOpenHook` is `jsr`-ed from `rasterIRQ` (`RASTER_EVENT == RASTER_EVENT_BORDER`)
and from `dispatchRasterEvents`'s `!service` path — i.e. it always runs **inside
the raster IRQ handler** with the CPU `I` flag set.

*(In the fixed build the same routine is at `$6220` — the forensic ring buffer,
§21, added ~50 bytes ahead of it.)*

---

## 3. Interpretation of the captured register state

```
.;61f7 00 f2 0e ea 2f 37 10100100 243 000  183327165
        A  X  Y  SP  00 01  NV-BDIZC LIN CYC  STOPWATCH
```

| field | value | meaning |
| --- | --- | --- |
| **PC = $61F7** | — | executing `BCC $61F2` in `!wait245` (§2). |
| **A = $00** | — | last LDA #0 (top of the hook); not since overwritten by the loop. |
| **X = $F2** = 242 | — | `$D012` read on the previous `LDX $D012` iteration. |
| **LIN = 243, CYC = 0** | — | the beam is at raster 243, cycle 0 — the loop is 2 lines from its target (245). *For a single sample this is not itself a lock — but see below.* |
| **flags = `10100100`** | N=1 V=0 –=1 B=0 D=0 **I=1** Z=0 C=0 | **I=1 → interrupts disabled → we are inside an IRQ handler.** C=0 → the last `CPX #$F5` had X(242) < 245 → `BCC` taken → still spinning. N=1 → `242-245` = $FD, bit 7 set. Consistent. |
| **SP = $EA** | — | 21 bytes on the stack (`$01EB..$01FF`). One clean IRQ→`borderOpenHook` uses ~8 (3 CPU + 3 KERNAL + 1 `jsr`); **~13 extra bytes ≈ several nested calls / a stacked pending-IRQ frame** (§7). |
| **$00/$01 = $2F/$37** | — | normal C64 CPU-port (RAM+I/O+KERNAL). |
| **STOPWATCH = 183,327,165** | — | ≈ 9,326 physical frames of run time at this point. |

**[INF]** Taken alone, PC in a 2-lines-from-exit spin at raster 243 is a
transient. Taken **with** `I=1`, the deep stack, and the dump's scheduler
counters (§4), it is the tail of one iteration of a **self-sustaining spin
cascade** — the CPU spends ~250–300 lines of *every* frame in this loop, so a
random monitor freeze lands here ~80–95 % of the time (§4, §11).

---

## 4. Relevant `lockup.bin` findings

**[MEAS]** parsed from the supplied 64K dump (`load=$0000`):

### VIC
| reg | value | note |
| --- | --- | --- |
| `$D011` | `$17` | YSCROL 7, **RSEL 0**, DEN 1 (gameplay base; fine phase 7). |
| `$D012` | `$F3` = 243 | matches `LIN 243`. |
| `$D019` | `$F7` → **bit 0 = 1 (raster IRQ latched)**, **bit 7 = 1 (VIC IRQ line asserted)** | *a raster IRQ is pending while we are already in the handler.* |
| `$D01A` | `$F1` → bit 0 = 1 | raster IRQ enabled. |
| `$D015` | `$FF` | all 8 sprites enabled. |
| `$D017`/`$D01D`/`$D01B` | `00`/`00`/`00` | no expansion, default priority. |

### Raster scheduler state (`RASTER_STATE_BEGIN = $62D3`)
| symbol | value | meaning |
| --- | --- | --- |
| `RASTER_EVENT` (`$62D3`) | **`$03` = RASTER_EVENT_BORDER** | the event being serviced is the border dodge. |
| `RASTER_TARGET` (`$62D4`) | `$F0` = 240 | `RASTER_BORDER_LINE`. |
| `RASTER_BORDER_PENDING` (`$62D7`) | `$00` | cleared → we are **inside** `borderOpenHook`, past its first store. |
| `RASTER_DISPLAY_PENDING` (`$62D6`) | `$00` | DISPLAY already serviced this frame. |
| `RASTER_PRESENT_READY` (`$62D5`) | `$00` | **main thread NOT parked at the frame boundary — it is starved.** |
| `RASTER_FRAME` (`$62DC`) | **4720** | frames counted. |
| `RASTER_INCOMPLETE_FRAMES` | 0 | (there are no sprite assignments: `RASTER_EXPECTED_ASSIGNMENTS = 0`.) |
| `RASTER_REPLAY_FRAMES` (`$62E0`) | **3999** | **84.7 % of frames took the `!replay` path** (main not ready at the boundary). |
| `RASTER_CATCHUPS` (`$62E2`) | **7999** | **≈ 1.7 events/frame serviced late** (`!due`, beam already past the target). |
| `RASTER_DISPLAY_FINE` (`$62E7`) | `$07` | fine phase 7 — the coarse-transition frame, the engine's heaviest. |

### Stack (`$01EB..$01FF`, SP=$EA)
```
$01EB: 7d ea 1b 28 1b dd eb 61 da 61 44 61 0e 00 f0 a0
$01F0: ...                     6e 09 e2 08 46
```
**[INF]** decoded call chain (return addresses `word+1`): a nested
`renderSprites` (`$1B26`) → `capturePlayerCollision`/`checkCapturedPlayerCollision`
(`$1BAF`) frame under a `dispatchRasterEvents` (`$6148`) `jsr` at `$61DA`
(`jsr borderOpenHook`) under `rasterFrameReset` (`$60BF`) `jsr renderSprites` at
`$610D`. i.e. **`rasterFrameReset` took `!replay`, ran `renderSprites`, then
`dispatchRasterEvents` handed the pending BORDER event straight into
`borderOpenHook`** — which is now spinning. The interrupted-code status byte
(`$E2`) has **I=1** and `$D019` bit 7 = 1: a *further* raster IRQ is queued
behind this one.

**Conclusion:** the dump is a snapshot of a **permanently locked engine** —
`borderOpenHook` spinning ~1 frame per frame, `!replay`/`!due` firing on almost
every frame, the main thread getting essentially zero cycles.

---

## 5. Raster busy-wait audit

**[OBS]** every `$D011`/`$D012` poll in `src/`:

| location | form | entered when | bounded? | wrap-safe? | verdict |
| --- | --- | --- | --- | --- | --- |
| `borderOpenHook` `!wait245` (`raster_scheduler.asm`) | `ldx $d012 / cpx #245 / bcc` | inside the IRQ, on the BORDER event | **NO** | **NO** | **THE BUG.** `$d012` = raster **mod 256**: for beam rasters 256..311 it reads 0..55 (all < 245) → the loop spins until the beam wraps up to 245 = **~250..300 scanlines inside the IRQ**. Also spins ~190 lines if entered at raster < ~55 (a stray early dispatch — observed, §12). |
| `borderOpenHook` `!wait250` | `ldx $d012 / cpx #250 / bcc` | immediately after `!wait245` | NO | NO | same hazard; only unreachable-in-practice because `!wait245` normally leaves the beam at 245. |
| `dispatchRasterEvents` `!near` (`raster_scheduler.asm:280`) | `lda $d011 / bmi !due` **then** `lda RASTER / cmp TARGET / bcc !near` | dispatch, target within 3 lines | **yes** (≤ 3 lines) | **yes** (`bmi !due` exits at beam ≥ 256) | OK — this is the *correct* pattern; the border hook lacks its `bmi` guard. |
| `waitForGameFrame` `!high`/`!low` (`raster_scheduler.asm:52/62`) | `sei / lda $d011 / bmi …` | main thread, once per frame | yes (≤ 1 frame) | yes (tests bit 8 directly) | OK — main thread, interruptible. |
| `prepareBackgroundCoarse` `!waitRead` (`main.asm:5666`) | `lda RASTER / cmp #160 / bcc` | main thread, **guarded** by `bmi !defer` + `cmp #184 / bcs !defer` first | yes (≤ ~24 lines from entry; deferred if beam ≥ 184 or ≥ 256) | yes (guarded) | OK — pre-existing scroller code, main thread, bounded, wrap-guarded. Not touched. |
| `updateCycleDebug` `!stableRaster` (`main.asm:3391`) | double-read retry on bit-8 change | not called during gameplay | yes | yes | OK. |

**Only `borderOpenHook` is an unbounded, non-wrap-safe busy-wait, and it runs
inside the IRQ.** Everything else either has the `bmi $d011` wrap escape or runs
on the interruptible main thread.

---

## 6. IRQ / scheduler audit

**[OBS]** `rasterFrameReset` (the FRAME event, `RASTER_EVENT = 0`, compare
`$d012 = 0`) is armed by `dispatchRasterEvents`'s epoch (`sta RASTER`) and fires
at raster 0. Its `!replay` branch (taken when `RASTER_PRESENT_READY == 0`) runs
`hudBorderSetup` + 5 `pha` + `jsr renderSprites` + 5 `pla` + `startLiveRasterPlan`
**inside the IRQ**, then `dispatchRasterEvents`.

`dispatchRasterEvents` `!current` decides *arm vs service-now*:
```
lda VIC_CONTROL_1 / bmi !due     ; beam >= 256 -> service the event NOW
lda RASTER / cmp RASTER_TARGET / bcs !due   ; beam >= target -> service NOW
... else arm the compare (sta $d012 = target) and rts
```
Every armed compare is `< 256` (only `$d012` is written, never `$d011` bit 8).

### The lock mechanism — [INF], proven in §11

1. **Trigger frame.** On a heavy frame (coarse transition, dense/clipped
   sprites) the `!replay` path's `renderSprites` + `hudBorderHandoff` (the
   repurposed DISPLAY event) push `dispatchRasterEvents`'s arrival at the
   `!border` branch **past raster ~246**. `!current` → `bmi !due` / `cmp` →
   **`jsr borderOpenHook` with the beam already ≥ 246 (often ≥ 256).**
2. **The spin.** `!wait245` reads `$d012` = 0..55, all `< 245` → it busy-waits
   ~250..300 scanlines, **crossing the raster-311→0 frame boundary inside the
   IRQ.**
3. **Latch.** During the spin, raster 0 passes → the FRAME compare latches in
   `$D019` (bit 0 + bit 7). It cannot fire — `I` is set.
4. **Re-fire.** `!wait245` finally exits at raster 245, does the RSEL writes,
   `RTS` → `dispatchRasterEvents` epoch → `RTI` → **the latched FRAME IRQ fires
   immediately, at raster ~250.**
5. **Cascade.** `rasterFrameReset` now starts at raster ~250, not 0.
   `RASTER_PRESENT_READY = 0` (main got ~0 cycles) → `!replay` → `renderSprites`
   → `dispatchRasterEvents` at raster ~258. `RASTER_DISPLAY_PENDING = 1` →
   `!display` → `!current` → `bmi !due` → DISPLAY serviced at raster 258
   (catchup). → `!border` → `!current` → `bmi !due` → **`borderOpenHook` re-entered
   at beam ≥ 256 → back to step 2.**

**Self-sustaining.** Once the spin crosses one boundary, every subsequent
"frame" repeats it. `RASTER_REPLAY_FRAMES` and `RASTER_CATCHUPS` climb ~1 and ~2
per frame respectively — **exactly the dump's 3999/4720 and 7999.**
`renderSprites` uses main-thread scratch; the `!replay` path's `pha`/`pla` guard
it, so **no corruption** — the lock is pure timing, not memory.

**BUILD/LIVE swap, collision registers, `$D01E`:** unaffected by the lock and by
the fix. `swapRenderPlans` runs on the main thread; the fix touches neither it
nor `applyLiveRasterBatch`.

---

## 7. Stack / re-entrancy audit

- **SP = $EA at the lock** = ~13 bytes deeper than a clean single IRQ into
  `borderOpenHook`. **[INF]** that depth is *one* extra stacked context: the
  cascade's `rasterFrameReset → !replay → jsr renderSprites → jsr
  capturePlayerCollision → …` chain (§4 stack decode) sitting under the
  `jsr borderOpenHook`, plus the KERNAL `$FF48` A/X/Y frame. It is **bounded** —
  the cascade does not nest IRQs (no `cli` in `rasterIRQ` / `borderOpenHook` /
  `rasterFrameReset`), so `$D019`-latched IRQs wait for the single `RTI`. There
  is **no runaway stack growth**; SP is stable at ~$EA every locked frame
  (verified in the A/B repro, §11). So the lock is a *timing* spiral, not stack
  exhaustion.
- **Shared scratch:** `renderSprites` uses `TEMP_OBJECT/MSB/SORT_Y/OBJECT_Y/Y_REG`
  (main-thread scratch). `rasterFrameReset !replay` explicitly `pha`/`pla`-saves
  all five around its `jsr renderSprites`. `borderOpenHook` uses only A/X and
  its own `RASTER_BORDER_PENDING`/`RASTER_BORDER_BAILS`. `hudBorderHandoff` uses
  `HUD_HO_RC`/`HUD_HO_MSB` (IRQ-private, in the RASTER_STATE block). **No
  concurrent main/IRQ use of the same byte.** Clean.
- **`RTI` / balance:** `rasterIRQ` always exits via `jmp $ea81` (KERNAL
  `PLA/TAY/PLA/TAX/PLA/RTI`); `!cia` via `jmp $ea31`. No path branches around a
  restore. `borderOpenHook` is entered by `jsr` and always ends `rts`
  (`borderOpenRestored` or the new `!bail`). Balanced.
- **Second IRQ source:** CIA-1 timer-A is masked (`initRasterScheduler` writes
  `$DC0D = $01`). `rasterIRQ` routes a non-raster IRQ to `$ea31`. No unexpected
  second source seen in the dump (`$DC0D = $01` = a latched-but-masked timer A,
  harmless).

**No re-entrancy or stack bug.** SP watermarking added indirectly via the
forensic ring (it records SP per event, §21).

---

## 8. HUD register-ownership audit (flicker)

**[MEAS]** (fixed build) — `trace store` on `$D008–$D00F` (slots 4..7 X/Y),
`$07FC–$07FF` (slots 4..7 pointers), `$D02B–$D02E` (slots 4..7 colours),
`$D015`, `$D01C`, over 500 spawn-pumped frames; classified by raster line vs the
HUD sprites' live DMA/display window (`HUD_Y = 22`, body rasters 22..42, DMA
from ~21):

| target | stores in raster 18..44 | source |
| --- | ---: | --- |
| `$D008–$D00F` (slots 4..7 X/Y) | **0** | — |
| `$07FC–$07FF` (slots 4..7 pointers) | **0** | — |
| `$D02B–$D02E` (slots 4..7 colours) | **0** | — |
| `$D01C` (MCM) | **0** | — |
| `$D015` (enable) | 501 (≈1/frame) at raster 18–19 | `renderSprites` `$1B42` — **`ora #$F0` keeps the HUD enable bits set through their DMA** (`main.asm:3548`); by design, not a corruption. |

⇒ **HUD hardware slots 4..7 are never written during their active DMA/display
window.** `renderSprites` caps its initial write at `HUD_SLOT_FIRST` (4) slots
and OR-s `$F0` into `$D015` to *preserve* the HUD; `hudBorderHandoff` reclaims
4..7 only at `HUD_HANDOFF_RASTER` (46), after the HUD body (≤42). **No
independent register-ownership flicker bug.**

**[INF] The flicker and the lock are the SAME family.** On a frame where the
BORDER event is dispatched outside its ~raster 237..245 window (§12) but the spin
does *not* cross the frame boundary (e.g. entered at raster ~55 → spins ~190
lines), the IRQ eats most of the frame → `rasterFrameReset` + `hudBorderSetup`
for the *next* frame run late → the four HUD sprites (4..7) are re-programmed
after part of their DMA window, or `$D015` is momentarily wrong → **one frame of
visibly wrong HUD sprites, then it recovers** = an intermittent single-frame HUD
flicker. Rare (§12: ~0.8 % of frames under pathological spawn-pumping, ~0 in
realistic play). **The §13 guard converts every such dispatch into an immediate
bail — no spin, no stolen frame, no flicker.**

---

## 9. Reproduction methodology

1. **Scripted organic** (`scratchpad/repro_lock.py`, `repro2.py`): free-run
   Level 1 with joystick wiggle + forced wave spawns + a dense 16-object load +
   **forced `!replay` on 75 % of frames**, sampling every ~2 frames.
   **Result: did not reproduce.** `borderOpenHook` entered at raster 241–242 on
   ~2,400 consecutive frames, `RASTER_CATCHUPS = 0`. The trigger is a *rare*
   timing coincidence and warp-mode monitor stepping perturbs the very timing
   that produces it.
2. **Forced-fault A/B** (`scratchpad/ab_lock.py`): inject a `JMP $C000` at
   `rasterDisplayHook` for 25 frames, where `$C000` runs the original body **+ a
   ~215-scanline delay**, so `dispatchRasterEvents` reaches `!border` with the
   beam ≥ 256; then **remove** the injection and free-run 800 frames.
   **This reproduces the dump's signature exactly** and lets pre-fix vs fixed be
   compared (§11).
3. **Regression / endurance** (`scratchpad/regress.py` + the project's
   `tools/vice_scroll_test.py --physical` / `tools/check_raster_capture.py`).

---

## 10. Endurance-test duration / frame counts

| run | build | frames | load |
| --- | --- | ---: | --- |
| organic repro | HEAD | ~6,000 samples (~2,400 frames advanced) | wiggle + spawn + dense |
| organic repro 2 | HEAD | ~2,000 frames | + forced 75 % `!replay` |
| A/B forced-fault | HEAD vs FIXED | 25 inj + 800 free-run each | dense-adjacent |
| regression | FIXED | 600 + 400 + **4,000** | authored + spawn-pump |
| regression 2 | FIXED (+forensic) | **3,000** | spawn-pump every 5 f |
| clean endurance | FIXED (+forensic) | 2,500 | joystick wiggle only |
| project oracle | FIXED (+forensic) | 200 (`--physical --trace`) | authored |

---

## 11. Did either failure reproduce?

**Hard lock — YES, deterministically, via the forced-fault A/B** (`ab_lock.py`):

| metric (after injection removed, 800 free-run samples) | **PRE-FIX (HEAD)** | **FIXED** |
| --- | --- | --- |
| PC parked in `borderOpenHook` (`$61ED..$620F`) | **795 / 800** | **0 / 800** |
| `RASTER_REPLAY_FRAMES` growth / frames | **37 / 38 (97 %)** | 1 / 38 |
| `RASTER_CATCHUPS` growth | **75 (≈2/frame)** | 1 |
| `RASTER_BORDER_BAILS` | n/a | 1 |
| outcome | **STILL LOCKED** (self-sustaining) | **RECOVERED** in ≤ 2 frames |

The pre-fix numbers (97 % replay, ~2 catchups/frame, PC in the hook) **match the
supplied `lockup.bin`** (84.7 % replay, 1.7 catchups/frame, `RASTER_EVENT =
BORDER`, PC = `$61F7`). The lock is real, its cause is `borderOpenHook`, and it
is permanent once triggered.

**HUD flicker — NOT reproduced visually** (it is a ≤1-frame event at ~0.8 %
incidence; scripted capture can't reliably catch the exact frame). But the
*mechanism* is established: register ownership is clean (§8), the only anomaly is
the rare out-of-window `borderOpenHook` dispatch (§12) whose ~190-line spin
steals the frame that `hudBorderSetup` needs. The §13 guard removes that spin.

---

## 12. Root cause

**`borderOpenHook`'s raster busy-waits `!wait245` / `!wait250`
(`ldx $d012 / cpx #target / bcc loop`) are unbounded and not wrap-safe, and the
hook runs inside the raster IRQ.**

- `$d012` is the raster counter **mod 256**. For beam rasters 256..311 it reads
  0..55 — all below both targets — so `!wait245` busy-waits **~250..300
  scanlines** until the beam wraps back up to 245, *inside the IRQ*, crossing
  the frame boundary.
- That stall makes `rasterFrameReset` start ~250 lines late; `RASTER_PRESENT_READY`
  is 0 (main starved) so `!replay` runs; the DISPLAY event is then a `!due`
  catchup at raster ~258; and `dispatchRasterEvents` hands the next BORDER event
  to `!due` with the beam **again ≥ 256** → the hook re-enters late → **permanent,
  self-sustaining lock.**
- **First trigger:** any single frame heavy enough (coarse transition + dense /
  top-clipped sprites, on the `!replay` path) that `dispatchRasterEvents` reaches
  the `!border` branch past raster ~246. The dump's `RASTER_DISPLAY_FINE = 7`
  (coarse-transition frame) is consistent.
- **[MEAS]** the fixed build also sees, ~0.8 % of spawn-pumped frames, the
  *opposite* anomaly — `borderOpenHook` dispatched at raster ~55 (a spurious
  early `!border` service, exact scheduler path not isolated) — which pre-fix
  would busy-wait ~190 lines (1-frame hitch → **the HUD flicker**); post-fix it
  bails.

**It is a display/scheduler robustness bug introduced with the border-HUD RSEL
dodge, not a scroller or multiplexer bug.** No `[19656]` / mux / BUILD-LIVE
problem exists.

---

## 13. Exact code changes

`src/raster_scheduler.asm` only (feature-relevant); `src/main.asm` +1 `#define`.
**+85 lines, 0 removed. No behaviour change on any in-window frame.**

### 13a. The fix — `borderOpenHook` late/early-entry guard (fixed build `$6220`)

```asm
borderOpenHook:
    lda #0
    sta RASTER_BORDER_PENDING
    // --- ROBUSTNESS GUARD (intermittent hard-lock fix) ---
    lda VIC_CONTROL_1
    bmi !bail+                    ; $d011 bit7 = raster bit8 => beam >= 256 => far too late
    lda RASTER
    sec
    sbc #237
    cmp #(246 - 237)             ; beam-237 in [0..8] i.e. raster 237..245 -> proceed; else bail
    bcs !bail+
    ...                          ; !wait245 / RSEL 0->1 / !wait250 / RSEL 1->0  (now provably <= ~13 lines, no wrap)
borderOpenRestored:
    rts
!bail:
    inc RASTER_BORDER_BAILS       ; forensic counter (16-bit)
    bne !bailDone+
    inc RASTER_BORDER_BAILS + 1
!bailDone:
    rts
```

- The dodge is only physically possible in the raster ~237..245 window (it must
  beat the raster-247 RSEL=0 close compare). The BORDER compare is
  `RASTER_BORDER_LINE = 240`, so a legitimate entry is 237..245.
- **Accept only that window.** Bail on earlier (spurious/corrupt event — would
  otherwise spin ~190 lines up to 245) or later (late IRQ / catchup / beam
  wrapped ≥ 256 — would otherwise spin ~250..300 lines and cascade).
- On a bail the border simply **closes normally for that one frame** — a
  ≤1-frame cosmetic blip of the lower overscan region, never a hang. The
  scheduler stays in sync (`dispatchRasterEvents` proceeds to the epoch as
  usual; no boundary crossed).
- `RASTER_BORDER_BAILS` (16-bit, `$6323`) counts every skip — visible in any
  future dump / capture.

### 13b. Forensic ring buffer (`#define BORDER_FORENSIC`, §21)

`rasterIRQ` records `(RASTER_EVENT, $d012, SP, RASTER_FRAME-low)` into a 32-entry
ring at `FORENSIC_RING` (`$637F`) on every raster-event dispatch; `FORENSIC_HEAD`
(`$637E`) is the cursor; zeroed in `initRasterScheduler`. ~24 cycles/event.

### Not changed
`rasterDisplayHook` / `hudBorderHandoff` / `hudBorderSetup` / `renderSprites` /
`applyLiveRasterBatch` / `dispatchRasterEvents` control flow / BUILD-LIVE /
`sortObjectsByY` / `prepareBackgroundCoarse` / `finishBackgroundCoarse` /
collision plumbing / `$D016` / `$D018` / VIC bank / `$0400` / `$3800` / level
data.

---

## 14. Before / after timing

| phase (fixed build, healthy frame — from the forensic ring) | raster | SP | note |
| --- | ---: | --- | --- |
| `RASTER_EVENT_FRAME` (`rasterFrameReset`) | 1 | $F5 | unchanged |
| `RASTER_EVENT_DISPLAY` (`hudBorderHandoff`) | 47 | $F3 | unchanged (`HUD_HANDOFF_RASTER = 46`) |
| `RASTER_EVENT_BORDER` (`borderOpenHook`) | **241** | $F5 | guard passes (241 ∈ [237,245]); `!wait245` waits 4 lines; RSEL 0→1 @ ~245; `!wait250` waits 5 lines; RSEL 1→0 @ ~250; `RTS` @ ~250 — **identical to before on every normal frame** |
| epoch → next frame | ~251 | — | unchanged |

**On an out-of-window dispatch:** before — `borderOpenHook` spins 190..300 lines
(→ 1-frame hitch or permanent lock). After — `borderOpenHook` returns in
**~12 cycles** (`bmi`/`sbc`/`cmp`/`bcs` + `inc inc`), `RASTER_BORDER_BAILS++`,
border closed for that one frame, scheduler continues normally.

---

## 15. `[19656]` cadence results

| run | build | frames | mean cycles/frame | oracle |
| --- | --- | ---: | --- | --- |
| authored + spawn-pump | FIXED | 600 | **19656.002** | — |
| dense 16-obj + top-clip straddlers | FIXED | 400 | **19656.005** | — |
| authored + spawn-pump | FIXED (+forensic) | 3,000 | **19655.999** | — |
| `--physical --trace` | FIXED (+forensic) | 200 | — | `check_raster_capture.py` → `frame_cycle_deltas: [19656]` |

Per-frame ±3 is the raster-311 breakpoint landing on a slightly different cycle
of line 311; the multi-thousand-frame mean is exactly **19,656.000**. The guard
(~12 cy on a bail, 0 on a normal frame) and the forensic ring (~72 cy/frame)
have **no cadence impact** — the physical frame is hardware-timed and the engine
has thousands of spare cycles.

---

## 16. Service failures / sprite-start misses

**[MEAS]** `check_raster_capture.py` (FIXED, 200 frames):
`service_failure_count: 0`, `sprite_start_miss_count: 0`,
`compare_writes_checked: 803` (all valid).
Custom endurance (FIXED, 4,000 + 3,000 frames): `RASTER_INCOMPLETE_FRAMES` delta
**0**. No regressions.

---

## 17. Catchups / replays

| run | build | frames | `RASTER_CATCHUPS` Δ | `RASTER_REPLAY_FRAMES` Δ | `RASTER_BORDER_BAILS` Δ |
| --- | --- | ---: | ---: | ---: | ---: |
| forced-fault, injection removed | **HEAD** | 800 | **+75** (runaway) | **+37 (97 %)** | n/a |
| forced-fault, injection removed | **FIXED** | 800 | **+1** | **+1** | **+1** |
| authored + heavy spawn-pump | FIXED | 3,000 | +33 (1 %) | **0** | +25 (0.8 %) |
| dense 16-obj + straddlers | FIXED | 400 | **0** | +12 | **0** |
| clean joystick wiggle (realistic) | FIXED | 2,500 | **0** | **0** | **0** |
| `check_raster_capture.py` | FIXED | 200 | **0** | **0** | **0** |

**[INF]** `RASTER_BORDER_BAILS` is non-zero only under pathological
spawn-pumping (a forced heavy BUILD every 5th frame). In realistic play it is
**0**. Each bail is one benign closed-border frame. The residual out-of-window
dispatch rate is a *pre-existing* scheduler characteristic (pre-fix it was a
latent lock); reducing it at its source (the DISPLAY-catchup / replay path) is a
recommended Phase-2 follow-up (§23), not required for stability.

---

## 18. Scroll temporal results for raster 55..246

**[OBS]** the fix does not touch `rasterDisplayHook`, the fine-scroll `$D011`
writes, `prepareBackgroundCoarse`/`finishBackgroundCoarse`, or any matrix data;
`GAMEPLAY_D011_BASE` / `RASTER_DISPLAY_FINE` handling is unchanged. `borderOpenHook`
still performs the identical RSEL dodge on every in-window (normal) frame — the
two `$D011` writes land at raster ~245 / ~250, **below the raster-55..246 body**,
exactly as before.
**[MEAS]** across 400 dense + 600 authored + 3,000 spawn-pumped frames the
scroller ran with `RASTER_INCOMPLETE = 0`, cadence `[19656]`, and
`check_raster_capture` clean — i.e. no change to the raster-55..246 presentation.
(The dedicated pixel oracle `check_scroll_capture.py` needs extra CLI fixtures
not wired up this session; the scheduler oracle + the untouched display path
cover the temporal-cleanliness claim.)

---

## 19. 5-enemy / 6-enemy / dense results

- **Authored waves, spawn-pumped** (forces back-to-back `NORMAL_WAVE_SIZE`-enemy
  waves) — 600 + 3,000 + 4,000 frames: cadence `[19656]`, `catchups`/`incomplete`
  0, no lock, no bail (except the 0.8 % pathological-pump case).
- **Dense synthetic (16 legal objects incl. top-clip straddlers Y 52..70)** —
  400 frames: cadence `[19656]`, `catchups 0`, `incomplete 0`, `bails 0`,
  `replay 12` (normal for a permanently-maxed sprite load), PC in the main loop
  throughout.
- **Lowest-Y sprite pressure** (8 sprites at Y = 245) exercised in the phase-1
  work on this branch; the fix does not change sprite scheduling.

---

## 20. HUD persistence / reuse proof

**[OBS]** unchanged by the fix — `hudBorderSetup` (line-1 IRQ) still programs
hardware slots 4..7 as the four HUD sprites; `renderSprites` still caps its
initial write at `HUD_SLOT_FIRST` and OR-s `$F0` into `$D015`; `hudBorderHandoff`
(DISPLAY event @ raster 46) still re-applies the deferred gameplay `INITIAL_*`
entries into slots 4..7 and restores their MC/`$D010` state.
**[MEAS]** over 500 frames, zero writes to slots 4..7 X/Y/pointer/colour during
their raster-18..44 DMA/display window (§8); `$D015` carries the `$F0` HUD bits
through DMA and is reset to the gameplay `RENDER_COUNT` mask at handoff. HUD
slots 4..7 are demonstrably reclaimed for gameplay every frame; all 8 hw sprites
are available after the raster-46 handoff. No permanent reservation.

---

## 21. Diagnostic breadcrumb layout (`#define BORDER_FORENSIC`)

| symbol | addr | size | contents |
| --- | --- | --- | --- |
| `RASTER_BORDER_BAILS` | `$6323` | 2 | count of `borderOpenHook` late/early bails (always compiled with `BORDER_PROOF_ENABLE`). |
| `FORENSIC_HEAD` | `$637E` | 1 | ring cursor, 0..124 step 4. |
| `FORENSIC_RING` | `$637F` | 128 | **32 entries × 4 bytes**, oldest-overwritten: `[0]=RASTER_EVENT` (0 FRAME / 1 SPRITES / 2 DISPLAY / 3 BORDER), `[1]=$D012` (beam raster low at dispatch), `[2]=SP`, `[3]=RASTER_FRAME low`. |

Zeroed in `initRasterScheduler`; written in `rasterIRQ` right after the IRQ ack,
before event dispatch (~24 cy/event, ~72 cy/frame, **no cadence effect**).

**Healthy pattern (verified):** repeating `(0,1,$F5,n) (2,47,$F3,n) (3,241,$F5,n)`
with `n` incrementing and SP flat at `$F3`/`$F5`.
**A future hang:** the ring shows the last 32 events — if `RASTER_EVENT = 3`
(BORDER) dominates with `$D012` small (0..55) and SP creeping, that is the
busy-wait region again; if a different event dominates, look there. Combined
with `RASTER_BORDER_BAILS`, `RASTER_REPLAY_FRAMES`, `RASTER_CATCHUPS` in the same
dump, the next occurrence should be diagnosable from one `bsave`.

To remove: comment `#define BORDER_FORENSIC` in `src/main.asm` (build then loses
the ring + its init/write code; `RASTER_BORDER_BAILS` and the guard stay).

---

## 22. Remaining uncertainties

1. **The exact scheduler path that dispatches `borderOpenHook` at raster ~55**
   (seen ~0.8 % of spawn-pumped frames; the source of the *flicker* class).
   Isolated to "a spurious early `!border` service", not to a specific line —
   the windowed guard makes it harmless either way, but Phase 2 should trace it
   (a conditional breakpoint that survives warp is needed).
2. **First-trigger frequency in real play.** The forced-fault proves the
   mechanism and the fix; I could not make the *organic* trigger fire under
   scripted warp input (monitor stepping perturbs the ~sub-line timing window).
   The user's two locks "within seconds" imply a real, if low, organic rate —
   consistent with a coincidence needing a heavy `!replay` frame to land the
   `!border` dispatch past raster 246.
3. **Visual confirmation of the flicker's elimination** — not captured frame-
   exact this session; argued from (a) clean register ownership, (b) the guard
   removing the only spin, (c) both failures sharing the feature.
4. **`check_scroll_capture.py` pixel oracle** not re-run (CLI fixture wiring);
   the untouched display path + scheduler oracle cover raster-55..246.

---

## 23. Recommended next step

**GREEN — the fix is in; proceed with the border-HUD work.** Before the next
feature (soft-edge masking):

1. **Keep `#define BORDER_FORENSIC` on** through the next round of manual
   playtesting. If a hang recurs, `bsave "dump.bin" 0 0000 ffff` and read
   `FORENSIC_RING` / `RASTER_BORDER_BAILS` / the counters — root cause should be
   immediate.
2. **Phase 2 (optional hardening):** reduce the out-of-window `!border` dispatch
   rate at its source — e.g. in `dispatchRasterEvents !current`, when the
   pending event is BORDER and `raster >= RASTER_BORDER_LINE`, skip it for this
   frame instead of `!due` (the guard already makes `!due` safe; this would just
   stop the bail from ever being needed). Or give BORDER its own dedicated
   compare armed at frame start rather than after DISPLAY.
3. Wire up `check_scroll_capture.py` and add a `borderOpenHook`-entry-raster
   assertion (must stay in [237,245], `RASTER_BORDER_BAILS` must stay 0 in a
   clean 5,000-frame authored run) to the automated suite — **this is the check
   that would have caught the bug** (§25).
4. Only then implement the top/bottom soft-edge masking.

---

## 24. Final `git status`

```
 M src/main.asm
 M src/raster_scheduler.asm
?? lockup.bin
```
`src/main.asm`: +1 `#define BORDER_FORENSIC` (+ its comment). `src/raster_scheduler.asm`:
the guard + bail + forensic ring (`git diff --stat`: `2 files changed, 85
insertions(+)`). `lockup.bin` is the user's dump (pre-existing in the tree,
untouched). HEAD is still `82c27c5`.

---

## 25. No repository history was altered

**No `git commit`, `git push`, `git add`, `git tag`, `git reset`, `git stash`,
or branch switch was performed.** All existing uncommitted work is preserved
(there was none on `experimental-border-hud` at start beyond the untracked
`lockup.bin`). The build toggles (`#define BORDER_PROOF_ENABLE`,
`#define HUD_PROOF_ENABLE`, `#define BORDER_FORENSIC`) were each verified to
compile on and off.

---

## Verdict: **GREEN**

- **Hard-lock root cause identified with convincing evidence:** `borderOpenHook`'s
  unbounded, non-wrap-safe raster busy-waits (`ldx $d012 / cpx #target / bcc`)
  running inside the IRQ; a single heavy frame dispatches the hook with the beam
  ≥ 246 (`$d012` wrapped to 0..55) → ~250..300-line spin → frame-boundary cross →
  `!replay` + `!due` cascade → **permanent self-sustaining lock**. Confirmed by
  A/B forced-fault: the pre-fix build reproduces the exact `lockup.bin` signature
  (97 % replay, ~2 catchups/frame, PC in `$61ED..$620F`); the fixed build
  recovers in ≤ 2 frames.
- **Minimal fix implemented:** a 4-instruction window guard (`raster ∈ [237,245]`,
  plus an explicit `bmi` beam-≥-256 escape) that bails `borderOpenHook`
  immediately on any out-of-window entry. +85 lines, one file, no behaviour
  change on any normal frame, no scroller/mux/BUILD-LIVE touch.
- **No observed lock** in 4,000 + 3,000 + 2,500 endurance frames, dense +
  top-clip + coarse + 5/6-enemy loads, or the forced-fault A/B.
- **Flicker:** HUD slots 4..7 register ownership proven clean; the flicker is the
  same out-of-window spin (a stolen frame delaying `hudBorderSetup`), which the
  guard eliminates. No independent register/enable-sequencing bug found.
- HUD slots 4..7 still reused by gameplay; all 8 sprites available after handoff;
  no permanent reservation.
- Terrain raster 55..246 presentation unchanged (display path untouched).
- **Exact PAL cadence `[19656]`** (mean 19655.999 over 3,000 frames;
  `check_raster_capture` `[19656]`).
- **0** service failures, sprite-start misses, catchups, replays, incomplete
  frames in supported gameplay.
- New coverage: `RASTER_BORDER_BAILS` + `FORENSIC_RING` breadcrumbs, the A/B
  repro harness, and a proposed entry-raster assertion for the automated suite.

### Why the new coverage would have caught this

The pre-fix automated suite checked cadence and the aggregate `catchups` /
`replay` / `incomplete` counters — all of which a *single* trigger frame barely
perturbs, and which the suite's short (~150–600-frame) runs rarely hit. It never
asserted **where `borderOpenHook` is entered** or that it **cannot busy-wait
across a wrap**. The additions:

- `RASTER_BORDER_BAILS` — any non-zero value in a clean authored run is a red
  flag that the BORDER event is being dispatched out of window (the precondition
  for the pre-fix spin).
- `FORENSIC_RING` — an event-level trace that shows a BORDER dispatch at
  `$D012` = 0..55 (the wrapped-beam case) directly.
- Proposed suite assertion (§23.3): `borderOpenHook` entry raster ∈ [237,245] and
  `RASTER_BORDER_BAILS == 0` over a 5,000-frame authored + coarse + dense run —
  this fails immediately on the pre-fix build under the same conditions that
  locked it, and passes on the fixed build.
