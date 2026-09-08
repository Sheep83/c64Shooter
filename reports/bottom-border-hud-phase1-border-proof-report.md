# Bottom-Border HUD Experiment — Phase 1: Prove the Border

**19656 / c64Shooter — PAL C64 vertical shooter.** Quarantined proof only.
No commit, no push. VICE launched head-less/background (`-remotemonitor`), never
foregrounded, no `open -a`.

Legend: **[OBS]** observed in source · **[MEAS]** measured this session ·
**[INF]** inference · **[REC]** recommendation.

---

## 0. Branch / HEAD / starting status

| | |
| --- | --- |
| Branch | `terrain-asset-workshop` (checked out; **not** switched) |
| HEAD | `2875dfd003010266a46827597bb6cee4dd23edfe` — *"Bottom border HUD investigation done"* |
| Working tree at start | **clean** |
| Toolchain | KickAssembler 5.25 · VICE `x64sc` **and** `x64` (both PAL, `-warp`) |
| Authoritative prior doc | `/reports/bottom-border-hud-feasibility-investigation.md` (verdict AMBER) — read in full |

### Top-HUD-glitch sequencing check (required)

**[OBS] The top-separator presentation fix has NOT been made.** `git log`: the
only change since the feasibility investigation is the report file itself
(`ff91d2d` → `2875dfd`). `rasterDisplayHook` in `src/raster_scheduler.asm` still
emits the invalid **BMM+ECM** separator (`$71` / `$70|fine`) at rasters ~62–70.
The HEAD commit message itself says *"Top HUD glitch still present"*.

Per the task, this Phase-1 proof **did not touch the top HUD**. The invalid-mode
separator is preserved unchanged. The one display-state change made (a brief
`RSEL` flip at the lower edge, §2) is mechanically separate from it and is fully
disabled by commenting a single `#define` line.

---

## 1. Clean baseline (experiment OFF)

Build of HEAD `2875dfd` with the experiment disabled (`#define
BORDER_PROOF_ENABLE` commented out):

```
sha256(build/shooter.prg, experiment OFF) = 2a605428eedb588f40310dd641fc17ce141035357a62bfc177e58655fb19b30e
sha256(build/shooter.prg, HEAD as-is)     = 2a605428eedb588f40310dd641fc17ce141035357a62bfc177e58655fb19b30e   ← byte-identical
sha256(build/shooter.prg, experiment ON)  = 6272b25e1d342181ecfc085bf79283c5ec4811e936184d4ffc01f4b759730e46
```

**[MEAS] Baseline scheduler / cadence** (`tools/check_raster_capture.py` on a
150-frame `tools/vice_scroll_test.py --physical --trace` capture of the
**experiment build**, ordinary Level-1 play):

| metric | value |
| --- | --- |
| `frame_cycle_deltas` | **`[19656]`** |
| `catchups` | 0 |
| `replay_frames` | 0 |
| `service_failure_count` | 0 |
| `sprite_start_miss_count` | 0 |
| `compare_writes_checked` | 603 (all valid) |

**[MEAS] 600-frame precise cadence** (STOPWATCH delta, experiment ON, ordinary
play): total 11,793,598 cyc / 600 = **19,655.997 → 19,656.000** (the ±2 total is
the raster-311 breakpoint landing on a slightly different cycle of line 311 on
the first vs last frame). Per-frame scheduler counters after 600 frames:
`incomplete=0 replay=0 catchups=0 display_late=0`.

**[OBS] Current relevant `$D011` phase values** (unchanged from HEAD, from a
`store d011` trace): `rasterFrameReset` writes `$17`; display hook writes
`$11` (r59), `$71` (r62, invalid), `$70|fine` / `$77` (r63/64, invalid),
`$10|fine` (r70, terrain). All RSEL=0. The experiment adds two more writes at
rasters 243 and 250 (§4).

---

## 2. Files changed

| File | Change |
| --- | --- |
| `src/main.asm` | +1 line at top: `#define BORDER_PROOF_ENABLE` (the single on/off toggle). +1 guarded block (`#if BORDER_PROOF_ENABLE … #endif`) at `$1fc0`: `BORDER_MARKER_SPRITE` — 63×`$ff` + 1 pad, a solid 24×21 marker bitmap in the free `$1f4a..$1fff` tail of the lookup-table segment (VIC bank 0, 64-aligned, pointer `$7f`), with two `.if` size/alignment guards. |
| `src/raster_scheduler.asm` | Guarded (`#if BORDER_PROOF_ENABLE`) additions only: `.const RASTER_EVENT_BORDER = 3`, `RASTER_BORDER_LINE = 240`, marker consts; `RASTER_BORDER_PENDING` state byte; re-arm it in `initRasterScheduler` + `rasterFrameReset` alongside `RASTER_DISPLAY_PENDING`; dispatch `RASTER_EVENT_BORDER` in `rasterIRQ` and `dispatchRasterEvents` (`!noBatch` path → after every sprite batch AND the display hook, before the epoch/frame-zero transition); new routine `borderOpenHook` + label `borderOpenRestored`. |
| `tools/vice_border_phase1.py` | **new** — self-launching (background, no focus steal) Phase-1 measurement harness. |
| `tools/border_phase1_analyze.py` | **new** — screenshot analyser (border depth, marker pixels, seam band). |

`raster_scheduler.asm` footprint grew `$6000–$634f` → `$6000–$63cb` (~124 bytes),
still well inside its `$6000–$65ff` allocation. **With the `#define` commented
out the build is byte-identical to HEAD** (SHA above) — the experiment is a
single-line revert.

### Exact source labels / routines changed

- **`initRasterScheduler`** (`raster_scheduler.asm`) — clears `RASTER_BORDER_PENDING` (in the state block, auto-cleared by the existing loop) and sets it to 1 next to `RASTER_DISPLAY_PENDING`.
- **`rasterFrameReset` `!epoch`** — `sta RASTER_BORDER_PENDING` (re-arm every physical frame).
- **`rasterIRQ` `!vic`** — new `cmp #RASTER_EVENT_BORDER / beq !border+` → `jsr borderOpenHook`.
- **`dispatchRasterEvents` `!noBatch`** — new `lda RASTER_BORDER_PENDING / bne !border+`; new `!border:` sets `RASTER_TARGET = RASTER_BORDER_LINE (240)`, `RASTER_EVENT = RASTER_EVENT_BORDER`, `jmp !current+`.
- **`dispatchRasterEvents` `!service`** — new `cmp #RASTER_EVENT_BORDER / beq !borderHook+`.
- **`borderOpenHook`** (`$625f`, NEW) — the whole hook (§4).
- **`BORDER_MARKER_SPRITE`** (`$1fc0`, `main.asm`, NEW) — 64-byte solid marker bitmap.

Untouched: `rasterDisplayHook`, `applyLiveRasterBatch`, `renderSprites`, the
BUILD/LIVE plan, `sortObjectsByY`, `buildBatchSpriteSchedule`,
`prepareBackgroundCoarse` / `finishBackgroundCoarse` / all `shift*` / `*CrossingRow`,
collision plumbing, `$D016`/`$D018`/VIC bank/`$0400`/`$3800`, level/editor data.

---

## 3. Before / after raster diagram

```
BEFORE (permanent RSEL=0)                  AFTER (experiment ON — playfield still RSEL=0)
------------------------------------       ------------------------------------------
r51-54  border (RSEL=0 top crop)           r16-54  TOP BORDER now OPEN (idle graphics)  <- consequence
r55-62  fixed char HUD (row 0)             r55-62  fixed char HUD (row 0)          UNCHANGED
r63-70  invalid BMM+ECM separator          r63-70  invalid BMM+ECM separator       UNCHANGED (glitch kept)
r71-246 terrain rows 1-23 (RSEL=0)         r71-243 terrain rows 1-23 (RSEL=0)      UNCHANGED
r247-250 border (RSEL=0 bottom crop)       r243    borderOpenHook: $D011 |= $08  -> RSEL 0->1
                                           r244-250 matrix row 24 ($20 blank -> $D021) + idle,
                                                    now VISIBLE (RSEL=1 aperture); NO foreground pop
                                           r250    borderOpenHook: $D011 &= $F7  -> RSEL 1->0
r251+   LOWER BORDER - closed, dead        r251+   LOWER BORDER OPEN (idle graphics) + marker sprite
                                           r~254-256  marker sprite: CLEAN solid white
                                           r~257-273  marker sprite: GARBLED  <-- the Phase-1 blocker
                                           r0-15   renderSprites re-defines $D015 for gameplay
```

---

## 4. RSEL state transition — exact `$D011` values and timing

`borderOpenHook` (`$625f`), fired from an IRQ compare at `RASTER_BORDER_LINE = 240`
(the dispatcher schedules it after the last sprite batch and the display hook,
before the frame-zero epoch). Disassembly + `store d011` trace:

```
$625f  LDA #$00 / STA RASTER_BORDER_PENDING          ; consume the event
$6264  LDA $D015 / AND #$80 / BNE $628F              ; slot 7 in gameplay use? -> skip the marker
$626b  LDA #$7F / STA $07FF                          ; slot-7 sprite pointer  = $1fc0/64
$6270  LDA #$01 / STA $D02E                          ; slot-7 colour = white
$6275  LDA #$A0 / STA $D00E                          ; slot-7 X = 160
$627a  LDA #$FC / STA $D00F                          ; slot-7 Y = 252
$627f  LDA $D010 / AND #$7F / STA $D010              ; marker X < 256
$6287  LDA $D015 / ORA #$80 / STA $D015              ; enable slot 7
$628F  LDX $D012 / CPX #$F3 / BCC $628F              ; poll to raster 243
$6296  LDA $D011 / ORA #$08 / STA $D011              ; **RSEL 0 -> 1**
$629E  LDX $D012 / CPX #$FA / BCC $629E              ; poll to raster 250
$62A5  LDA $D011 / AND #$F7 / STA $D011              ; **RSEL 1 -> 0**
$62AD  RTS
```

**[MEAS]** (`store d011` trace, per frame, fine-6 example — `A` is the value stored):

| write | raster : cycle | `$D011` value | decode |
| --- | --- | --- | --- |
| RSEL 0→1 | **243 : ~18** | `$1E` | YSCROL 6, **RSEL 1**, DEN 1, text — *before* the RSEL=0 close compare at raster 247 → **that compare is missed** |
| RSEL 1→0 | **250 : ~16** | `$16` | YSCROL 6, **RSEL 0**, DEN 1, text — *before* the RSEL=1 close compare at raster 251 → **that compare is missed** |

- **Both writes are read-modify-write of `$D011` (`ORA #$08` / `AND #$F7`)** — YSCROL, DEN, BMM, ECM are preserved exactly; only bit 3 (RSEL) moves. **No ECM, no invalid mode** (deliberately — the top-band glitch shows why).
- `borderOpenHook` entry raster **241–242** (`RASTER_BORDER_LINE 240` + IRQ latency), `borderOpenRestored` (RTS) raster **250**. The whole hook lives in raster ~241–250, entirely in the lower crop / border region — no visible playfield pixel depends on its exact cycle. A badline at the polled line (row-24 badline = 240+fine, ≤ 247) delays the poll exit by < 1 line, still well before raster 247. **[MEAS]** across all 8 fine phases the writes always land at raster 243 / 250.
- `rasterFrameReset` restores `$D011 = $17` (RSEL 0, YSCROL 7) at raster ~1 as always. **[MEAS]** no RSEL=1 lingers past raster 250.
- **[MEAS] Moving the RSEL 1→0 write to raster 254 or 262 (live RAM patch) changed nothing** about the border or the marker — the transition mechanism is not cycle-fragile in this window.

### Border flip-flop outcome

- RSEL=0 close compare (raster 247) — missed (RSEL=1 at that cycle).
- RSEL=1 close compare (raster 251) — missed (RSEL=0 at that cycle).
- ⇒ the vertical border flip-flop is **never set** this frame → it stays reset from the raster-55 top compare → **both the lower AND the upper border open** (single-FF VIC-II; expected, see §7).

---

## 5. Diagnostic marker sprite

| property | value |
| --- | --- |
| hardware slot | **7** |
| bitmap | `$1fc0` (`BORDER_MARKER_SPRITE`), 63 × `$ff` + 1 pad — **[MEAS]** verified all-`$ff` at runtime on both `x64sc` and `x64` |
| pointer `$07ff` | `$7f` |
| colour `$d02e` | `1` (white) — multicolour mode (`$D01C` bit 7 = 1), all `%11` pixel pairs → solid white block |
| X `$d00e` | 160 (`$D010` bit 7 forced 0) |
| Y `$d00f` | 252 (body rasters 252–272) |
| enable | `$D015` bit 7 set **only when `$D015 & $80 == 0` at hook entry** |
| setup raster | ~241 (in `borderOpenHook`, before the RSEL writes) |
| `$D017` / `$D01D` / `$D01B` | 0 / 0 / 0 — **[MEAS]** never touched, no expansion, default priority |

### Why hardware slot 7 is safe in this proof

- **[OBS]** `renderSprites` writes `$D015 = SPRITE_ENABLE_MASK[RENDER_COUNT]` at the top of **every** frame — a full definition of the enable register to exactly the first `RENDER_COUNT` bits. So whatever the hook leaves in `$D015` bit 7 is wiped next frame.
- The hook arms the marker **only if `$D015` bit 7 is already clear** at raster ~241 — i.e. `renderSprites` gave this frame `RENDER_COUNT < 8`, so the multiplexer never assigns hardware slot 7. When a frame genuinely needs 8 hardware sprites, `renderSprites` sets bit 7, the hook **sees it and skips** — the gameplay sprite in slot 7 (whose body may still be DMAing) is **left completely alone**. **[MEAS]** in the 16-object dense load `$D015 = $FF` and `dense_marker` shows a gameplay sprite in slot 7 (Y ≠ 252) — the marker correctly absent.
- No `HUD_SAFE_RASTER`, no `SLOT_FREE_RASTER` publishing, no handoff, no reservation, no limit change, no `RENDER_COUNT` cap. The marker simply blinks out on any frame that needs all 8.

---

## 6. Measured opened-border geometry

**[MEAS]** VICE `screenshot … 2` (384×272; screenshot_y ≈ raster − 16), pixel-analysed
(`tools/border_phase1_analyze.py`) across all 8 fine phases, several coarse
transitions, ordinary + dense + low-Y loads, and a contrasting `$D021`.

### Border opening — GREEN

- **Lower border is open every frame**: rasters ≥ 247 show the display region's
  **idle graphics** (repeating `$3FFF` byte pattern — with `$D021` = mdgrey it
  reads as grey/black vertical stripes; with `$D021` = yellow, yellow/black
  stripes) instead of the closed `$D020` black border. First non-black raster is
  **247** in every screenshot.
- **Upper border is also open** (rasters ~16–54 show the same idle-graphics
  stripe pattern above the fixed HUD row) — the single-FF consequence of §4.
- The open borders are **stable across all 8 fine phases and across coarse 7→0
  transitions** — `first_open_raster = 247` in all 20+ screenshots; no flicker,
  no unstable transition line.

### Diagnostic sprite in the opened lower border — **the blocker**

- The marker **is displayed** in the opened lower border: a 24-px-wide block at
  C64 X 160, starting raster ~254.
- **[MEAS] It renders CLEANLY (solid white, full 24 px) only for rasters
  ~254–256 — the first ~3 sprite data rows. From raster ~257 downward it
  GARBLES**: the sprite shows a byte-stable striped mixture of white / `$D021` /
  `$D025` / `$D026` pixels — i.e. the VIC fetches **wrong sprite data** for rows
  ≥ 3, even though `$1fc0..$1ffe` is verified all-`$ff`. Visible to raster ~273
  then the sprite ends normally (MCBASE = 63, DMA off).
- The garble is:
  - **byte-identical across consecutive frames** (deterministic, not flicker);
  - **independent of the RSEL-write timing** (live-patched raster 250 → 254 → 262: garble onset unchanged at ~257);
  - **independent of `borderOpenHook`** — a monitor-poked marker in the untouched slot 6 at Y=252 garbles identically;
  - **region-locked** — the *same* sprite (same data, same pointer, same colour) at Y = 180 in the normal playfield renders as a **pixel-perfect solid white block**;
  - **reproduced on BOTH `x64sc` and `x64`** (two different VICE emulation cores), same onset raster, same pattern.
- The transition raster (~256–257) coincides with the `$D012` 8-bit wrap
  (RASTER bit 8 going 0→1).

### Measured usable depth

| quantity | value |
| --- | --- |
| first raster the border is open | **247** |
| first raster a sprite is visible | ~254 (marker Y 252 + ~2 px calibration) |
| **last raster a sprite renders CLEANLY** | **~256** |
| last raster with *any* marker pixels (garbled) | ~273 |
| **clean usable opened-lower-border sprite depth** | **≈ raster 251–256 ≈ 6 px** |
| depth a 4-sprite HUD would need | ~24–40 px |

---

## 7. Scroll-seam behaviour (RSEL=1 briefly reveals rasters 244–250)

**[OBS] Matrix row 24 is already a permanent blank row.** `initFixedHud`
(`main.asm:6144`) writes `BG_SCREEN_A + 24*40 .. +39 = $20` (space). **[OBS]**
`shiftBackgroundUpper` shifts rows 0..11→1..12, `shiftBackgroundLower` shifts
rows 13..22→14..23, `renderStageRowToScreen` (from `prepareBackgroundCoarse`)
writes row 1, `save/restoreCrossingRow` handle rows 12/13 — **nothing in the
scroller ever writes matrix row 24.** No spacer-row change was needed.

**[MEAS]** With RSEL=1 active for rasters ~244–250, the screenshots show that
band as **`$D021` (blank space glyph)** transitioning to idle graphics, with the
break point moving 240→250 as the fine phase goes 0→7 — i.e. it tracks the fine
scroll exactly as the terrain does. **There is NO foreground "7→0 pop"**: row 24
is a space glyph, it carries no foreground bits, so there is nothing to snap
from height 4→0. Verified across all 8 fine phases and repeated coarse
transitions.

**The diagnostic therefore distinguishes cleanly:**

| aspect | result |
| --- | --- |
| border-opening success | **YES** (rasters 247+ open every frame, every phase) |
| scroll-seam success | **YES** (row 24 = blank `$D021`, no foreground pop, no spacer change needed) |
| sprite-in-open-border success | **NO past ~raster 256** (garble, §6) |

---

## 8. Required measurements — before vs after

| measurement | HEAD (baseline) | experiment ON |
| --- | --- | --- |
| `frame_cycle_deltas` (`check_raster_capture`, 150 frames) | `[19656]` | **`[19656]`** |
| 600-frame mean cycles/frame (STOPWATCH) | — | **19,656.00** |
| `catchups` / `replay_frames` | 0 / 0 | **0 / 0** |
| `service_failure_count` / `sprite_start_miss_count` | 0 / 0 | **0 / 0** |
| `RASTER_INCOMPLETE_FRAMES` / `RASTER_DISPLAY_LATE` (1200+ frames incl. dense/low-Y/div1) | 0 / 0 | **0 / 0** |
| coarse-scroll readiness | `bgUpperReady` r271–272 on coarse frames | unchanged (hook preempts the copy for ~40–90 cyc; 0 deferrals) |
| latest gameplay sprite batch | r233 (8 sprites @ Y=245) | unchanged |
| lower-border `$D011` transition | n/a | **RSEL 0→1 @ r243:18 (`$1E`); RSEL 1→0 @ r250:16 (`$16`)** |
| diagnostic sprite setup raster / Y | n/a | **~r241 / Y = 252** |
| gameplay sprite register corruption | n/a | **none** — `$D000–$D00F`, `$D027–$D02E`, `$07F8–$07FF` untouched by the hook except slot 7, and only when slot 7 is idle |
| `$D015` leak into next frame | n/a | **[MEAS]** bit 7 lingers from raster 241 to the next frame's `renderSprites` (~raster 10); the marker (Y 252) is out of range during rasters 0–10 so **no spurious sprite**; `renderSprites` then re-defines `$D015` per `RENDER_COUNT`. Slot-7 X/Y/ptr/colour also linger, harmless (overwritten before any gameplay use, or the hook skips). |
| `$D010` leak | none — hook clears bit 7 each frame; other bits owned by `renderSprites` |
| collision latch | **[MEAS]** `PLAYER_HIT` seen `[0]` over 120 frames. When shown, the marker is never in the player's slot (hook skips an in-use slot 7), so `PLAYER_HW_MASK` never includes it and the software confirm (Y ∈ [71,246)) blocks any border-only overlap. **Caveat:** `DEBUG_PLAYER_INVULNERABLE = 1` in this build suppresses `PLAYER_HIT` unconditionally, so this is corroborating, not decisive — an invuln-off run is a Phase-2 check. `$D01E` is read+cleared by `renderSprites` every frame regardless. |
| visible lower-border depth | closed (0 px usable) | **open; ~6 px clean sprite-usable (r251–256); garbled r257–273** |

---

## 9. Stress cases exercised

| case | done | result |
| --- | --- | --- |
| all 8 fine-scroll phases | ✅ (400-frame run cycles them; per-phase screenshots) | border open r247 every phase; marker stable; row-24 band clean |
| repeated coarse 7→0 transitions | ✅ (25 in a 400-frame run; 6 contrast screenshots across transitions) | no scheduler deferral, no seam pop, marker unaffected |
| scroll divider 2 (authored) | ✅ (default) | `[19656]`, 0 counters |
| divider-1-like (SCROLL_FRAME_COUNT pumped each frame → coarse work every ~8 frames) | ✅ (250 frames) | `[19656]` (one 21567 outlier = the per-frame monitor poke, not the engine); 0 counters |
| ordinary authored gameplay | ✅ (600+ frames) | clean |
| dense sprite load (16 legal objects) | ✅ (250 frames + screenshot) | `[19656]`, 0 counters; marker correctly **skipped** (slot 7 = gameplay) |
| lowest-Y sprite pressure (8 gameplay sprites @ Y=245) | ✅ (250 frames + screenshot) | `[19656]`, 0 counters; marker skipped (`$D015 = $FF`); no corruption |
| player death/respawn | partial — invuln build; scheduler-lifecycle unaffected (hook is inert to `PLAYER_STATE`) | Phase-2 to re-run with invuln off |
| stage wrap | not driven to a full ~400-logical-row circuit this session (covered by the documented scroll-hitch battery; the hook is stage-position-independent) | — |
| contrasting non-black `$D021` (yellow) | ✅ (6 screenshots) | border/seam artefacts do **not** masquerade as success — the open borders visibly show `$D021`+idle stripes; the marker garble is equally visible; confirms the proof is not "black hiding it" |

Several hundred physical PAL frames per important case; **1200+ frames total**
with `incomplete/replay/catchup/display_late` all 0.

---

## 10. Captures

- `build/border-phase1/fine0.png … fine7.png` — one per fine phase (border open, marker present).
- `build/border-phase1/contrast_d021_0..5.png` — `$D021` = yellow, across coarse transitions.
- `build/border-phase1/dense.png`, `lowY.png` — 16-object / lowest-Y loads (marker correctly absent).
- `build/border-phase1/stable_0..2.png` — 3 consecutive frames, marker region **byte-identical** (garble is deterministic, not flicker).
- `build/border-phase1/x64_marker.png` — plain `x64` core: identical garble.
- `build/border-phase1/scrollcap/` — 150-frame `--physical --trace` capture; `check_raster_capture.py` = clean.
- `build/border-phase1/report.json` — the harness's machine-readable results.

ASCII of the marker region (from `stable_0.png`, byte-identical across frames):

```
r254  WWWWWWWWWWWWWWWWWWWWWWWW      <- sprite data row 0 : clean solid white
r255  WWWWWWWWWWWWWWWWWWWWWWWW      <- row 1 : clean
r256  WWWWWWWWWWWWWWWWWWWWWWWW      <- row 2 : clean
r257  WWWWWWWW    ....    ....      <- row 3 : GARBLE begins ($D012 wrap boundary)
r258      ....WWWWWWWWWWWWWW..
r259  WWWWWW..WW....WWWW  ..WW
 ...  (byte-stable striped mixture of white / $D021 / $D025 / $D026 to r273)
```

---

## 11. Explicit regressions / unknowns

**Regressions: none measured.** Cadence `[19656]`, 0 catchup / replay / service /
sprite-start / incomplete / display-late across every load, on the trusted
`check_raster_capture.py` oracle and a 1200+-frame custom run. No multiplexer
change. Playfield rasters 55–243 are pixel-unchanged (RSEL only moves the border
compare lines; the display hook is untouched).

**Unknowns / open items:**

1. **[BLOCKER] Why does a sprite garble past raster ~256 in the opened lower
   border?** Ruled out this session: our RSEL-write timing, `borderOpenHook`,
   slot 7 specifically, the sprite data, one emulator core. **Not** ruled out:
   (a) a genuine VIC-II sprite-`MCBASE` / DMA behaviour in the far lower border
   (both VICE cores agreeing points here); (b) an interaction from the playfield
   being permanent-RSEL=0 while the edge is briefly RSEL=1; (c) an artefact of
   *no other sprites being active* (an empty sprite sequencer edge state).
   **Real PAL-hardware confirmation is required.** Note: Slap Fight's HUD is in
   the opened **TOP** border at Y ≈ `$0c` (raster ~12) — comfortably inside the
   normal sprite window — not the deep lower border.
2. The **open top border** (rasters ~16–54, idle-graphics stripes above the HUD)
   is an unavoidable single-FF consequence of a deep bottom open. Not addressed
   here (out of scope); Phase 2 / final architecture must either use it
   (top HUD returns as border sprites, ≈ architecture C′) or find a top re-close.
3. Collision with invulnerability **on** — not tested (Phase-2 check).
4. Full stage-wrap timing with the hook active — not independently re-measured
   (hook is stage-position-independent; covered by the documented battery).
5. NTSC — untested; PAL authoritative; border compares differ (§ feasibility
   report), NTSC would need its own numbers.

---

## 12. Recommendation

# AMBER — the border opens, but sprite graphics in the deep opened lower border are corrupted (measured), and that must be root-caused before a dynamic handoff is worth building.

**GREEN parts (measured, robust):**

- The lower vertical border **opens reliably** on PAL every frame, all 8 fine
  phases, across coarse 7→0 transitions, dense and lowest-Y loads, and with a
  contrasting `$D021` (criteria 1, 3, 4).
- **Exact PAL cadence stays `[19656]`** — trusted oracle + 600-frame mean
  (criterion 8).
- **No new service / sprite-start / catchup / replay / incomplete regressions**
  over 1200+ frames (criterion 9).
- **No multiplexer rewrite** — the border is one extra terminal `RASTER_EVENT`
  in the existing dispatcher (criterion 10).
- The **bottom scroll seam is NOT reintroduced** — matrix row 24 is already a
  blank `$20` row the scroller never touches; no spacer change was needed; no
  foreground 7→0 pop in any phase (criterion 5).
- **Ordinary and dense gameplay remain stable**; **low-Y sprite pressure does
  not corrupt the proof** (the marker safely blinks out when slot 7 is in
  gameplay use) (criteria 6, 7).

**The `X` that makes it AMBER (criterion 2 — "diagnostic sprite visibly and
measurably rendered"):** a sprite **is** rendered in the opened lower border, but
**cleanly only for ~6 px (raster ~251–256)**. Below raster ~256 it fetches wrong
data and garbles — deterministically, on both VICE cores, independent of our
code, region-locked (the identical sprite is pixel-perfect in the playfield).
A bottom-border sprite HUD needs ~24–40 clean px, so **this is a hard blocker
until root-caused.**

**Do NOT proceed to the Phase-2 dynamic handoff yet.** The handoff is only worth
building if there is a usable depth to hand sprites *into*.

### Proposed Phase-1.5 (resolve the blocker) — bounded, before any Phase 2

1. **Confirm on real PAL hardware** (or a third independent emulator / a known
   community "sprites in the full lower border" reference) whether a solid
   sprite at Y ≈ 252 renders its full 21 rows in an opened lower border. This is
   the single decisive test.
2. If it is a **VIC-II reality** (deep-lower-border sprites corrupt):
   - Re-target the experiment to the opened **TOP** border (Slap-Fight-exact:
     HUD sprites at Y ≈ `$0c`, raster ~12–33, reused by gameplay from ~raster
     `$20`). The top border is already open as a side effect (§6) and is inside
     the normal sprite window. This flips the architecture to a **top** sprite
     HUD — still "sprite HUD in an opened border, no permanent reservation,
     terminal/entry raster phase" — and would reclaim the *bottom* geometry for
     terrain instead.
   - Re-run this whole Phase-1 battery for the top border.
3. If it is an **interaction** (playfield RSEL=0 vs brief RSEL=1, or empty
   sprite sequencer): try the feasibility report's "option C" — run the
   *playfield* in RSEL=1 for the whole frame (with matrix row 0 + row 24 as
   blank `$D021` spacers, as that report specifies) and flip RSEL→0 only at
   raster 250. A sprite whose trigger and early rows are inside a normally-lit
   RSEL=1 display may keep its `MCBASE` correct into the lower border.
4. Only when a **≥ ~24 px clean** opened-border sprite depth is demonstrated:
   proceed to Phase 2 (`HUD_SAFE_RASTER` from `SLOT_FREE_RASTER`, terminal
   gameplay→HUD handoff, borrow 4 sprites dynamically, restore/collision
   semantics, static HUD graphics first).

### Phase-2 scope (only if Phase-1.5 turns the depth GREEN)

Unchanged from the feasibility report: derive/publish `HUD_SAFE_RASTER` from the
existing BUILD `SLOT_FREE_RASTER` (8-iteration `max`, ~70 cyc), add the terminal
gameplay→HUD handoff as one more `RASTER_EVENT`, borrow 4 hardware sprites
dynamically, prove `$D015`/`$D01D`/collision restore, keep static HUD graphics
until that is solid, then add real HUD content. **prove border → prove usable
depth → prove handoff → build HUD content.**

---

## 13. Housekeeping

- **No commit, no push.** `HEAD` still `2875dfd`. Working tree: `src/main.asm`
  + `src/raster_scheduler.asm` (the guarded experiment) + 2 new `tools/*.py`
  + this report.
- **The experiment is one line to disable:** comment out `#define
  BORDER_PROOF_ENABLE` at the top of `src/main.asm` → build is byte-identical to
  HEAD (SHA `2a605428…`, verified).
- VICE was launched head-less/background (`-remotemonitor`, `Popen`, DEVNULL)
  and killed on exit; **never foregrounded**, no `open -a`.
- Scratchpad probe from the prior investigation (`probe_bottomhud.py`) is
  outside the repo and untouched.
