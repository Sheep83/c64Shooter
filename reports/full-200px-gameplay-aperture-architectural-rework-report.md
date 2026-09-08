# 19656 / c64Shooter — Full ~200px Gameplay Aperture: Architectural Rework

**PAL C64. Branch `experimental-border-hud`.** No commit, no push. VICE `x64sc`
head-less / background (`-remotemonitor`, `Popen`, `DEVNULL`), never foregrounded,
no `open -a`.

Legend: **[OBS]** source · **[MEAS]** measured this session · **[A/B]** measured
vs a comparison build · **[DOC]** from a supplied commercial decompilation.

---

# 0. Verdict — **AMBER**

The reported bug is **fixed** and a real, commercial-aligned aperture recovery
is shipped, but the *clean scrolling-terrain* aperture does not grow past
~192 px — that is an architectural property of a finite 25-row character fetch,
shared by the Slap Fight / Terra Cresta reference engines, and removing it needs
a change disproportionate to this task.

| Target (Part H GREEN) | Result |
| --- | --- |
| clean aperture ~200 px / raster 51..250 | **partial** — clean scrolling *terrain* = raster **55..246 (192 px)**, unchanged; the *displayed* field is now ~raster 16..260 (borders open), of which 55..246 is temporally-flawless terrain and 247..258 is a solid-$D021 "soft edge" sprite zone |
| bottom no longer clips the player | **YES** — `borderOpenHook` opens the lower vertical border; `PLAYER_MAX_Y` 230→237; the ship's full 21-line body renders against backdrop, not a black crop |
| top fully usable by terrain + sprites + collisions | **YES** — unchanged from the prior task (`GAMEPLAY_SPRITE_MIN_Y = 55`); the opened top border is now clean backdrop, HUD-ready |
| fine scrolling clean | **YES** — 0 temporal diffs, all 8 phases |
| repeated coarse 7→0 clean *in the claimed clean aperture (55..246)* | **YES** — 0 diffs, 24+ transitions incl. stage wrap |
| exact `[19656]` | **YES** |
| stable real gameplay, no new dead zones | **YES** |
| architecture compatible with a later top-border sprite HUD | **YES — improved** (top border now open + backdrop-clean) |
| **one bounded limitation remains** | the soft-edge band (raster 247..254 bottom, 52..55 top) shows overflow-row terrain that pops ~6 px **once per coarse cycle** (~3×/s at divider 2), below the claimed clean body. **Removal:** a `$D018` mid-frame swap to a reserved 2 KB zeroed charset region masks it to solid backdrop — bounded memory-map work, folded into the top-HUD task (§Part C cand. 2 / §12). Deeper still: a bitmap/hybrid playfield (disproportionate). |

---

# 1. Q1 — starting branch / HEAD / status

| | |
| --- | --- |
| Branch | `experimental-border-hud` |
| HEAD at task start | `d547c80` — *"Establish RSEL1 border HUD experimental baseline"*; the Phase-1.5 + overflow-row + full-gameplay-aperture work uncommitted |
| HEAD now | `44e735c` — *"pre-architecture-teardown"* (the user committed the three prior tasks' work as a checkpoint during this task; author Brian Morrice, Sep 8) |
| Working tree at task start | `M src/main.asm`, `M src/raster_scheduler.asm`, `M tools/check_scroll_edges_rsel1.py`, `M tools/phase15_geometry_test.py`, `?? tools/sprite_y_sweep.py`, `?? docs/*worklog.md`, `?? reports/*.md` — all now in `44e735c` |
| Confirmed present | the overflow-row model (`W(r)=SCROLL_ROW+r-1`, r=0..24), `GAMEPLAY_RSEL=0`, `GAMEPLAY_SPRITE_MIN_Y=55`, `GAMEPLAY_SPRITE_END_Y=246` — all verified in source |
| Final build (this task) | `sha256(prg) = c59f975a7a08cdf6…`, `sha256(d64) = e135aa93a5288427…` |

---

# 2. Q2 — exact files changed this task

| File | Change |
| --- | --- |
| `src/raster_scheduler.asm` | `borderOpenHook`: replaced the `#if GAMEPLAY_BOTTOM_EXTEND` toggle with a single clean **open-both-borders dodge** — poll to raster 245, `$D011 \|= $08` (RSEL 0→1, misses the RSEL=0 close @247); poll to raster 250, `$D011 &= ~$08` (RSEL 1→0, misses the RSEL=1 close @251). The vertical-border FF is never set → both borders open every frame. `rasterFrameReset` re-installs `RASTER_DISPLAY_FINE \| GAMEPLAY_D011_BASE` (RSEL=0, DEN=1, YSCROL=fine) at line 1. |
| `src/main.asm : init` | after `setupStarfieldCharset`: `sta STAR_CHARSET+$7ff` / `sta STAR_CHARSET+$1ff` (= `$3FFF` / `$39FF`, the text / ECM idle-graphics g-fetch bytes) `= $00` → the idle region renders solid `$D021` backdrop, not the `$3FFF` ROM-char stripe pattern. Char codes 224..255 are outside the terrain (96..223) / HUD (64..145) / star (224..225) allocation. |
| `src/main.asm` | `+ .const PLAYER_MAX_Y = 237` (near `PLAYER_START_Y`); removed `.const GAMEPLAY_BOTTOM_EXTEND`; updated the `GAMEPLAY_RSEL` doc block. |
| `src/main.asm : updateObjects` player-down clamp | `cmp #230 / beq !left+` → `cmp #PLAYER_MAX_Y / bcs !left+` — raises the limit and fixes a latent bug (the old `beq`-only path let a player already past 230 keep descending). |
| `docs/full-200px-aperture-worklog.md` | new worklog. |
| `reports/full-200px-gameplay-aperture-architectural-rework-report.md` | this report. |

Net: `src/main.asm` +58/−48-ish, `src/raster_scheduler.asm` +? small. No new
half-active scrollers; the superseded `GAMEPLAY_BOTTOM_EXTEND` toggle removed.

---

# 3. Q3 — architecture diagram (before)

```
BEFORE (44e735c) — RSEL=0, bottom border CLOSED
--------------------------------------------------
line 0/1  rasterFrameReset : $D011 = RASTER_DISPLAY_FINE | $10   (DEN, RSEL=0, YSCROL=fine)
line ~15  armFirstBatch -> publishRasterPlan : same $D011 ; IRQ armed ; BUILD published
line ~15-89  finishBackgroundCoarse (shiftBackgroundLower 14..24 + restoreCrossingRow)
raster 55  border FF RESET (RSEL=0, DEN=1)                        <- top crop
raster 55..246  25 fetched matrix rows displayed:
     r0  = world SCROLL_ROW-1   (incoming overflow; only glyph rows 3-7 ever visible)
     r1..r23 = world SCROLL_ROW .. +22   (BODY — temporally flawless)
     r24 = world SCROLL_ROW+23  (outgoing overflow; only glyph rows 0-7 ever visible)
raster 247  border FF SET (RSEL=0)                                <- BOTTOM CROP: r247+ = $D020 black
             ... row-24 terrain (fetched, displayed r240..254) is painted over by the border
             ... SPRITES in r247+ are painted over by the border   <- PLAYER BODY CLIPPED
raster ~160-272  prepareBackgroundCoarse (coarse frames only)
raster 240  RASTER_EVENT_BORDER -> borderOpenHook : $D011 &= ~$08  (no-op, RSEL already 0)
raster 311  frame wrap
```

Player at `Y=230` → sprite body rasters 230..250 → **bottom 4 px (247..250) hidden
by the closed border.** This is the reported bug.

---

# 4. Q4 — Part B: commercial-vs-current comparison

Verified directly from the supplied `slap_fight_border_hud_annotated.asm` and
`terra_cresta_border_hud_annotated.asm`.

| Concern | Our engine (44e735c → this task) | Slap Fight [DOC] | Terra Cresta [DOC] | Implication |
| --- | --- | --- | --- | --- |
| RSEL during gameplay | RSEL=0 (this task keeps RSEL=0, dodges both closes) | **RSEL=1** (`$D011 \|= $48` @ raster 0) | **RSEL=1** (`$D011 & $3f` keeps RSEL=1) | commercial runs 25-row; we run 24-row + dodge. Equivalent *displayed* height once borders open. |
| Bottom-edge transition | poll to raster 245, RSEL 0→1; poll 250, RSEL 1→0 → both closes missed → FF never set | `BORDER_OPEN_PHASE $1802`: wait raster > `$f7` (247), `$D011 = ($D011 & $17) \| $40` → **RSEL=0 + ECM=1**; `$D018 = $e3` | `bottom_border_phase $483c`: wait raster ≥ `$f7`, `$D011 = ($D011 & $17) \| $40` → RSEL=0 + ECM=1; `$D018 = $e3` | Both commercial engines: **RSEL flip + ECM + `$D018` swap** at the bottom. We do the RSEL flip; we mask idle via a zeroed `$3FFF` instead of ECM+`$D018`. Their `$D018 = $e3` swaps screen+charset for the border strip — the mechanism our §12 GREEN path would adopt. |
| Top restoration | `rasterFrameReset` @ line 1 restores RSEL=0\|fine; idle above the first badline = zeroed → backdrop | `FRAME_TOP_IRQ $105f` @ raster 0: `$D011 \|= $48` (ECM=1, RSEL=1); `DISPLAY_RESTORE_PHASE $187c` @ raster ≥ `$39` (57): `$D011 & $3f` (ECM=0) | `top_restore_phase $4889` @ raster ≥ `$39`: `$D011 & $3f` (clear ECM) | Commercial keeps **ECM=1 for rasters 0..57** to mask the top transition; we mask the top idle with the zeroed g-byte and accept a ~4 px overflow-row soft edge at r52-55. |
| IRQ phases per frame | 3 kinds: FRAME(0), SPRITES(n batches), BORDER(1) — one merged dispatcher | ≥4 phases: HUD_IRQ(`$0f5f` ~raster 247), FRAME_TOP(`$105f` raster 0), BORDER_OPEN(`$1802`), DISPLAY_RESTORE(`$187c`), SPRITE_MUX(`$1936` from raster 32) | ≥4: score/HUD (`$4549`), bottom (`$483c`), top-restore (`$4889`), sprite mux (`$4a57`) | Similar phase count. Ours is a single re-entrant dispatcher; theirs is a self-modifying `$FFFE/$FFFF` chain. |
| Fine-scroll write timing | once, at line 1 (`rasterFrameReset`), no mid-frame split | not shown in the excerpt | not shown | ours is simpler (single write); theirs not decompiled here — **unclear**, stated so. |
| Coarse-scroll method | beam-raced 2-phase char-RAM shift (upper behind beam, lower at frame top) + 1-row crossing buffer + 2 overflow rows | `$D018` values swapped per frame (`$e3` ↔ `$02\|var`) — **suggests `$D018`/page-based scroll or at least a separate border screen**; char-shift not shown | `$D018` swapped (`$e3` ↔ `$02\|$062d`) — same | Commercial may use a second screen page / `$D018` for the scroll or border; our char-RAM shift is confirmed and works. The `$D018` swap is the missing piece for masking our soft edge (§12). |
| Sprite list representation | logical pool → `sortObjectsByY` → BUILD render plan (per-slot payloads + batch schedule) → publish → LIVE | sorted logical list, `ldy $0a / ldx $28,y` walks it; **no pre-built frame plan** | sorted list, `ldy $0a / ldx $2b,y`; **no pre-built plan** | We pre-compute a whole frame; they compute just-in-time. §Part E. |
| HW slot reuse | mux recycles slots for objects 9-16 in batches; initial 8 written by `renderSprites` | HUD sprites (raster 12) reused as gameplay sprites from raster 32 — **time-domain ownership, no reservation** | score sprites (Y 28-29) reused by the gameplay mux — same | Both commercial engines time-slice the *same* 8 physical sprites HUD↔gameplay. Our future top-HUD should do likewise (this task keeps the door open). |
| Next-raster scheduling | dispatcher sets `$D012` to the next batch's `min(Y)-12`; late → spin to target + `inc RASTER_CATCHUPS` | `lda $5a,x / sbc #$0e` → schedule ~14 lines before the sprite; `.schedule_next` bumps `$D012`; `late_case` → `inc $D012` | `lda $67,x / sbc #$0e` → ~14 lines ahead; `mux_reschedule` / `late_case` identical | **Already equivalent** — same `Y−14`-ish lead, same late-recovery idea. |
| Late-raster recovery | spin-to-target + catchup counter; `rasterFrameReset` replay path re-runs `renderSprites` if BUILD unfinished | `late_case: inc $d012 / rti` (advance one line, try again) | `late_case: inc $d012 / rti` | Ours is arguably heavier (full-frame replay) but also more deterministic. |
| Frame reset | explicit FRAME event at compare 0; unconditional `$D011` + plan re-arm | `FRAME_TOP_IRQ` at raster 0 restores RSEL, sets next `$D012=$20` | `score_border_irq` chains toward raster 0 | equivalent intent. |
| HUD / gameplay sprite handoff | none yet (this task keeps it possible) | HUD_IRQ programs all 8 as the status strip at Y=12; SPRITE_MUX reclaims them from raster 32 | score_border_irq at Y 28-29; mux reclaims | the model our top-HUD task should copy. |
| Dependence on a pre-built schedule | **high** — BUILD must finish + publish before the first gameplay compare; replay path exists for when it doesn't | **none** | **none** | the one place the commercial architecture is structurally lighter (§Part E). |
| Behaviour near bottom of frame | terrain to raster 247+fine, then idle (now zeroed → backdrop); borderOpenHook opens the border; sprites usable to ~258 | RSEL→0 + ECM + `$D018` swap at raster 248; HUD/sprites in the opened region | same | We reach the same place (open border, masked strip) by a slightly different mechanism. |

Where the commercial excerpts are silent (fine-scroll write timing; whether the
scroll itself is `$D018`-page-based) this report says so rather than inventing.

---

# 5. Q5 — precise cause of the raster-247+ discontinuity

**[MEAS]** RSEL=1 build (`/tmp/rsel1.prg`), all 8 fine phases, `check_scroll_edges_rsel1`:

- Terrain displays cleanly to raster **`247 + fine`** — matrix row 24's badline
  is `48 + fine + 8*24 = 240 + fine`; row 24 shows for 8 lines. Below that the
  VIC is **idle** (no 26th badline — badlines stop at raster 247), fetching
  `$3FFF` → stripe pattern.
- Aperture 51..250: **`body_temporal_diffs = 0`** (rasters 56..244) — the body is
  temporally flawless every phase and every coarse step.
- Non-zero diffs occur **only at the `7→0` coarse step**, at rasters **248-250**
  (bottom) and, symmetrically, **52-55** (top). Every non-coarse fine step
  (`0→1`…`6→7`) = **zero diffs**.

**Root cause (not "there is no 26th row" — the mechanism):**

`W(r) = SCROLL_ROW + r − 1`. Matrix row 24 = world `S+23` (outgoing overflow),
row 0 = world `S−1` (incoming overflow).

- Row 24 is fetched at badline `240+fine` and shows glyph rows 0..7 at rasters
  `240+fine … 247+fine`. As `fine` goes 0→7 the whole image scrolls down 1 px per
  frame — the *body* stays continuous because rows 1..23 hand each world row to
  the next row down, and row 24 catches row 23's fall-off.
- At the `7→0` coarse step `SCROLL_ROW` decrements and `shiftBackgroundLower`
  moves matrix row 23→24, so the new row 24 = old row 23 = world `S+22` (= new
  `S+23`) → world `S+22` continues at +1 px (rasters 239-246 → 240-247). **The
  body is fine.**
- But world `S+23` (the *old* row 24) has **nowhere to go**: its next position
  (rasters 248-255) needs a matrix row 25 that cannot be fetched. Its 8-px band
  at rasters `247+fine…254+fine` simply **vanishes** and is replaced by idle
  (now backdrop). That vanishing = the ~6-8 px pop, once per coarse cycle.
- Mirror at the top: world `S−2` is only ever *partially* visible (its bottom
  5 px, in row 0, at rasters 51-55) — its top rows are above raster 51, never
  fetched-and-shown — so at the coarse step it "jumps in" ~4 px rather than
  scrolling in gradually.

**This is a property of any finite N-row character fetch that presents its last
fetched row.** The RSEL=0 crop at raster 55/246 hides both overflow rows'
imperfect outer edges. RSEL=1 (or an open border) exposes ~4-8 px of each. The
Slap Fight / Terra Cresta engines crop/mask at the *same* boundary — their extra
visible height is **sprites + border HUD**, not scrolling terrain past the crop.

---

# 6. Q6 — Part C: candidate architectures

| # | Candidate | Mechanism | Mem | Cyc/frame | Scroller impact | Mux impact | Editor/world | Risk | Aperture | Top-HUD later |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **1 (chosen)** | **Open both borders + zeroed idle byte** (commercial dodge, our masking) | RSEL 0→1@245 / 1→0@250 → FF never set; `$3FFF/$39FF = $00` → idle = solid `$D021` | +2 B (init) + ~20 B (hook) | ~30 (2 polled `$D011` writes) | **none** — RSEL=0 scroll unchanged | **none** | none | **Low** | terrain 55..246 clean; displayed ~16..260; sprites usable ~16..258 | **yes — top border now open + backdrop-clean = the HUD strip** |
| 2 | Cand. 1 **+ `$D018` mid-frame swap** to a reserved zeroed 2 KB charset for r247+ (and r16-54) | at raster ~246 point CB at a zeroed charset → r247+ glyph fetch = blank; restore CB at line 1 | **+2 KB charset** (reserved zeroed page) + ~15 B | ~40 (extra `$D018` write + restore) | none | none | possibly a VIC-bank memory-map shuffle | **Med** (memory map) | terrain 55..246 clean; r247-254 = solid backdrop (**pop masked**) → full GREEN for "no periodic pop" | yes |
| 3 | Deeper beam-raced row-24 prep (blend two source rows into row 24 each frame at the fine offset) | re-render row 24 from world `S+22`/`S+23` blended per fine → its bottom edge always continuous | +40 B buf | **+~1200** (re-decode + 8-byte shift ×40 glyphs, main thread) | **significant** — new per-frame row build, new blend path | none | none | **Med-High** | still 192 px *clean gameplay rows* (row 24 becomes the sacrificial blend row) — **no net terrain gain**, only a smoother sacrificial edge | yes |
| 4 | Full commercial raster state machine + `$D018`-page scroll | adopt Slap Fight's phase chain + ECM edges + a 2-page `$D018` scroll | **+8 KB** (screen pages) or +2 KB | rework | **replace the scroller** | rework the IRQ chain | likely | **High** | ~200 px *displayed*; the terrain still can't scroll cleanly past its last fetched row → same soft edge, just relocated | yes |

**Why Candidate 1 won:** it is the only option that fixes the reported bug
(player clip), removes the black border, and is forward-compatible with the
top-HUD, at **zero scroller / mux risk and near-zero cost**, with `[19656]`
untouched. Candidate 2 is the small, well-scoped follow-up that converts the
remaining soft-edge pop to a clean fixed strip — deferred because it wants a
VIC-bank memory reshuffle that the top-HUD task will do anyway. Candidates 3-4
spend a large amount of code/cycles/risk **without recovering any clean
scrolling terrain** — the finite-fetch edge is not a bug our engine can
out-engineer with a bigger scroller; it is where every C64 char scroller stops.

---

# 7. Q7-Q10 — Part D: what was implemented, after-state

## Q7 — architecture diagram (after)

```
AFTER (this task) — RSEL=0, BOTH vertical borders OPEN, idle byte = $00
---------------------------------------------------------------------------
line 1    rasterFrameReset : $D011 = RASTER_DISPLAY_FINE | $10   (DEN, RSEL=0, YSCROL=fine)
line ~15  armFirstBatch -> publishRasterPlan : same ; BUILD published (unchanged)
raster ~16..~51  IDLE (above first badline) -> g-fetch $3FFF = $00 -> SOLID $D021 backdrop
                 (border FF is open all frame -> top border shows display/idle, not $D020)
raster ~48..~55  matrix row 0 (world S-1) overflow terrain  <- ~4 px "soft edge", pops at 7->0
raster 55..246   BODY (matrix rows 1..23) -> TEMPORALLY FLAWLESS, every phase, every coarse step
raster 245       borderOpenHook : $D011 |= $08   (RSEL 0->1 ; RSEL=0 close @247 now misses)
raster 247..~254 matrix row 24 (world S+23) overflow terrain  <- ~6 px "soft edge", pops at 7->0
raster 250       borderOpenHook : $D011 &= ~$08  (RSEL 1->0 ; RSEL=1 close @251 now misses)
raster ~252..~260 IDLE -> SOLID $D021 backdrop ; SPRITES render here (player body, low enemies)
raster ~260+     overscan / vblank
raster 311       frame wrap -> rasterFrameReset re-establishes RSEL=0
```

Player at `Y=237` → body rasters 237..258 → **fully inside the open display →
NOT clipped.** [MEAS] `player_bottom_beforeafter.png`.

## Q8 — exact `$D011` / RSEL raster sequence (after) — [MEAS] `store d011` trace

| Event | Raster : cycle | `$D011` | Decode |
| --- | --- | --- | --- |
| `rasterFrameReset` | **line 1 : ~10-22** | `RASTER_DISPLAY_FINE \| $10` = `$10..$17` | DEN=1, RSEL=0, YSCROL=fine, compare-MSB 0 |
| `publishRasterPlan` (every frame via `armFirstBatch`) | line ~15 : ~46 | same | idempotent re-install before the first badline |
| `borderOpenHook` RSEL 0→1 | **raster 245 : ~15-25** | `$18..$1F` | bit 3 set; RSEL=0 border-close compare @247 now misses |
| `borderOpenHook` RSEL 1→0 | **raster 250 : ~15-25** | `$10..$17` | bit 3 clear; RSEL=1 border-close compare @251 now misses → FF never set this frame |

Vertical-border FF: **reset** at raster 55 cycle 63 (RSEL=0, DEN=1) — but it was
already reset (never set) → both borders open. No ECM, no BMM (unlike the retired
separator). Read-modify-write preserves DEN/YSCROL/BMM/ECM; only bit 3 moves.

## Q9 — screen-matrix / fetch strategy (after)

**Unchanged.** One screen matrix `$0400`, charset `$3800`, VIC bank 0, `$D018 =
$1F` fixed. 25 matrix rows fetched (badlines `48+fine .. 240+fine`). The only
new memory fact: charset bytes `$3FFF` and `$39FF` are forced to `$00` so idle
graphics = solid `$D021`. No second matrix, no `$D018` swap (that is Candidate 2).

## Q10 — memory changes

- `+2` bytes written in `init` (`$3FFF`, `$39FF` ← `$00`).
- `borderOpenHook` net roughly unchanged (toggle removed, one poll block).
- `+1` const (`PLAYER_MAX_Y`), `−1` const (`GAMEPLAY_BOTTOM_EXTEND`).
- Segment sizes essentially unchanged: `$6000-$6353` (raster scheduler) vs
  `$6000-$6344` before; `$2920-$2e69` unchanged; ~390 B headroom in the `$4000`
  segment as before. No memory-map move.

---

# 8. Q11-Q12 — timing / cycle changes

- **Q12 cycle/raster:** `borderOpenHook` adds two polled `$D011` writes (~30 cyc
  total) inside the already-scheduled `RASTER_EVENT_BORDER` at raster 240 — no
  new IRQ. `init` adds 4 cyc once. **No change to the per-frame budget on the
  gameplay path.** `bgUpperReady` still raster 288 (coarse frames), `bgLowerReady`
  median 20 — unchanged from the overflow-row task. BUILD published by raster
  ~15-20 (`gameplayPresented`). `[19656]` untouched (nothing moves
  `rasterFrameReset`).

---

# 9. Q13 — final gameplay aperture (Part F audit)

```
terrain visible raster range          : ~16 .. ~260   (both borders open; idle = $D021 backdrop)
terrain temporally CLEAN raster range  : 55 .. 246     (the claimed clean gameplay body — 192 px)
fine-scroll range                      : 55 .. 246 clean ; 247..254 soft edge follows fine 1:1
coarse-transition clean range          : 55 .. 246     (0 temporal diffs, 24+ transitions + wrap)
topmost FULL sprite origin Y           : 55            (GAMEPLAY_SPRITE_MIN_Y ; prior task)
lowest FULL / partially-clipped sprite : 245 exclusive cull (GAMEPLAY_SPRITE_END_Y) ; a sprite
                                          origin renders through raster ~258 (open border)
sprite pixel-visible raster range      : ~16 .. ~258   (border open ; rows outside are overscan)
player movement Y range                : 55 .. 237     (up = GAMEPLAY_SPRITE_MIN_Y ; down = PLAYER_MAX_Y)
collision-confirmation Y range          : 55 .. 245     (checkCapturedPlayerCollision)
hitscan eligibility Y range             : 55 .. player Y (unchanged)
enemy fire Y range                     : 55 .. 190     (unchanged)
enemy spawn/despawn/render Y range      : render/cull 35 .. 246 ; fire 55 .. 190
```

Coherent: the sprite / collision / player-up top (55) **equals** the clean
terrain top. The one deliberate mismatch — player-down 237 vs clean terrain
246 — is intentional: the player may now descend into the opened-border backdrop
zone (its body stays fully visible), which was the reported bug. No band exists
where terrain is presented as gameplay but sprites are disallowed.

---

# 10. Q14 — full gameplay Y-boundary table

| # | subsystem | before this task | after | class |
| --- | --- | --- | --- | --- |
| 1 | `GAMEPLAY_SPRITE_MIN_Y` | 55 (prior task) | 55 | unchanged |
| 2 | `GAMEPLAY_SPRITE_CLIP_MIN_Y` | 35 | 35 | unchanged |
| 3 | render cull / VIC slot | 35..246 | 35..246 | unchanged |
| 4 | sprite top-clip depth | `MIN_Y − Y` | same | unchanged |
| 5 | player move up | ≥ 55 | ≥ 55 | unchanged |
| 6 | hitscan hittable | ≥ 55 | ≥ 55 | unchanged |
| 7 | enemy-fire eligible | 55..190 | 55..190 | unchanged |
| 8 | collision confirm | 55..246 | 55..246 | unchanged |
| 9 | batch schedule `Y ≥ 12` | 12 | 12 | structural — unchanged |
| 10 | **player move down** | **`#230`** | **`#PLAYER_MAX_Y` = 237** | **raised** (opened border) + latent-bug fix |
| 11 | enemy cull ceiling `END_Y` | 246 | 246 | unchanged (clean-terrain bottom) |
| 12 | `PLAYER_START_Y` | 220 | 220 | unchanged |

---

# 11. Q15-Q22 — test results

## Q16 — cadence (trusted `vice_scroll_test.py --physical --trace` + `check_raster_capture.py`)

| run | frames | `frame_cycle_deltas` | service_failure | sprite_start_miss |
| --- | ---: | --- | ---: | ---: |
| ordinary | 220 | **`[19656]`** | 0 | 0 |
| dense (16 obj / 8 batches) | 200 | **`[19656]`** | 0 | 0 |
| seeded real waves (authored, incl. 6-enemy) | 260 | **`[19656]`** | 0 | 0 |
| stage wrap (`SCROLL_ROW` 0→420) | 320 | **`[19656]`** | 0 | 0 |

`--dense` catchups 1393 / replays 99 — **[A/B]** identical on baseline `d547c80`;
pre-existing synthetic-stress behaviour of the BUILD/LIVE architecture, absorbed,
cadence exact.

## Q15 — scroll temporal (Part G.3), `check_scroll_edges_rsel1 --aperture 55 246`

| workload | coarse 7→0 | body diffs (r56-245) | edge diffs (r246) | `coarse_edge_median_jump` |
| --- | ---: | ---: | ---: | --- |
| ordinary | 12 | **0** | **0** | `[0]` |
| **wave5** (≤5-enemy authored) | 12 | **0** | **0** | `[0]` |
| contrast (`$D021` = 7, yellow) | 12 | **0** | **0** | `[0]` |
| divider-1-like | **24** | **0** | **0** | `[0]` |
| stage wrap (320 f) | 19 | **0** | **0** | `[0]` |

The claimed clean aperture 55..246 is temporally flawless across all 8 fine
phases and every coarse transition including the stage wrap. Fine scrolling: 0
diffs. **The soft-edge band (247..254)** shows, at the `7→0` coarse step only,
~29 000 pixel-diffs across rasters 248-253 (a ~6 px terrain-edge snap against
backdrop); every non-coarse fine step there is ≤ 312 diffs at a single raster
(the edge advancing 1 px/frame — expected).

## Q17-Q18-Q20 — sprite / mux stress (Part G.7)

| case | `[19656]` | service_failure | sprite_start_miss | max_objects |
| --- | --- | ---: | ---: | ---: |
| top cluster — 15 enemies @ Y 56..84 (`highy`) | ✅ | 0 | 0 | 16 |
| mid cluster — 16 stationary @ Y 96..188 (`dense`) | ✅ | 0 | 0 | 16 |
| bottom cluster — 8 @ Y ~245 (`lowy`) | ✅ | 0 | 0 | 16 |
| **5-enemy** authored (`wave5`) | ✅ | 0 | 0 | ~8 |
| **6-enemy** authored (`wave6`, seeded real) | ✅ | 0 | 0 | 9 |
| **8-enemy** — covered by `dense`/`highy` (16 obj, 8 batches) | ✅ | 0 | 0 | 16 |
| Y-distribution spread (sweep 40..244, single obj) | every Y gets a slot; topmost = always the initial-8 (unscheduled) | — | — | — |

`sprite_y_sweep 40..244`: no active object is denied a slot; the **topmost
sprites are always the Y-sorted initial-8**, written by `renderSprites` at frame
top with **no raster scheduling** — so the sprite top limit is *display-bound*
(the aperture), never *mux-bound*. The earliest *batched* service raster stays
~127 (mid-screen). The "5 enemies while scrolling" observation is confirmed
conservative — 6-enemy and 16-object loads pass the trusted oracle here.

## Q19 — dense 16-object

`[19656]`, 0 service failures, 0 sprite-start misses, `max_batches 8`. Replay
path exercised (pre-existing).

## Q21 — BUILD/LIVE retained / modified / replaced, and why

**Retained, unmodified.** The aperture solution is entirely a display-state
change (`borderOpenHook` + one init write + one clamp const) — it needs nothing
from the render plan. Touching the mux would add risk to the primary work for no
benefit. See Q22.

## Q22 — measured current-vs-JIT mux evidence (Part E)

**[MEAS]** on the shipped build:

- **BUILD cost / publication deadline:** the render plan is built and published
  by raster **~15-20** every normal frame (`gameplayPresented` r15-20,
  `armFirstBatch` r12-17). The deadline is "before the first gameplay sprite
  compare" — met with a ~200-raster margin on normal frames.
- **Main-loop work consumed by planning:** `sortObjectsByY` worst case ~4.4 k
  cyc [DOC]; full BUILD historically leaves a large idle tail (the FREE-cycle
  diagnostic is *disabled* precisely because it perturbed coarse admission —
  i.e. there is spare budget).
- **LIVE dispatch cost:** `applyLiveRasterBatch` ~100-150 cyc IRQ per batch.
- **Catchups / replays in realistic loads:** **zero** on ordinary / wave5 /
  wave6 / seeded real waves. The synthetic `--dense` (16 stationary objects, 8
  tight batches) triggers the **replay path** ~99/200 frames (main didn't finish
  BUILD before frame 0) — cadence still exact, 0 misses.
- **Failure onset:** none observed in the supported scrolling envelope; the
  synthetic dense load is the first thing to exercise replay, and it still does
  not *fail* (no service failure, no sprite-start miss).
- **Does JIT help?** The commercial JIT mux (Slap Fight `$1936`, Terra Cresta
  `$4a57`) has **no BUILD phase, no publication deadline, no replay/catchup
  machinery** — a short IRQ programs the next 1-2 hardware sprites scheduled
  `Y−14` lines ahead off a pre-sorted list. It would **remove our
  replay/catchup path and the BUILD deadline**, and it maps cleanly onto the
  commercial HUD↔gameplay slot handoff our top-HUD task wants. It would **not**
  change the sprite *count* limit materially (both are 8 hardware sprites) and
  it is a **substantial rewrite** of the IRQ chain and every render-plan
  consumer.
- **Recommendation:** **the JIT mux is the immediate next architectural task**,
  after (or alongside) the top-border HUD — not this task. It is not required
  for the aperture and adopting it here would jeopardise the primary work.

---

# 12. Path to full GREEN (the one remaining bounded limitation)

The soft-edge pop (raster 247-254 bottom, 52-55 top; ~6 px; once per coarse
cycle; against `$D021` backdrop; below the clean body): **Candidate 2** removes
it. At raster ~246 write `$D018` so the character-generator (CB) points at a
**reserved 2 KB zeroed charset region**; the per-scanline glyph fetch for
rasters 247+ then returns `$00` → the overflow row-24 terrain there renders as
solid `$D021`, identical frame to frame → **no visible pop**, sprites still
composite on top. Restore `$D018` in `rasterFrameReset`. This is exactly the
`$D018 = $e3` mechanism both commercial engines use at the bottom edge [DOC].
Cost: one reserved zeroed page (a VIC-bank memory reshuffle) + one extra
`$D018` write/restore. **Deferred to the top-border-HUD task**, which reorganises
VIC-bank memory for the HUD sprite frames anyway.

Deeper still — a bitmap or hybrid text/bitmap playfield for the last row — would
let the terrain scroll cleanly to the true bottom, but is disproportionate to a
few pixels.

---

# 13. Q23 — implications for the eventual top-border HUD

Improved, not blocked:
- The **top border is now open and renders as clean `$D021` backdrop** (zeroed
  idle byte) — that is precisely the canvas a Slap-Fight-style top sprite HUD
  draws into (HUD sprites at Y ≈ `$0c`, raster ~12-33).
- The both-borders-open dodge is already in place; the HUD IRQ would program 4-8
  hardware sprites in the open top border and the existing mux reclaims them for
  gameplay from ~raster 32 (time-domain ownership, no reservation) — the
  commercial pattern.
- Candidate 2's `$D018` swap (for the soft-edge mask) and the HUD's charset
  frames want the same VIC-bank memory work → do them together.
- The JIT mux (Part E) would make the HUD↔gameplay slot handoff simpler; sequence
  it right after the HUD proof.

---

# 14. Q24 — remaining caveats

1. Clean *scrolling terrain* is 192 px (r55..246), unchanged — architectural, not
   a defect (§5, matches commercial practice).
2. Soft-edge pop r247-254 / r52-55 — §12 has the fix.
3. `tools/phase15_geometry_test.py`'s own `check_raster_capture` output is an
   unreliable trace-parse artefact (documented in the prior report) — trusted
   numbers here are all from `tools/vice_scroll_test.py --physical --trace`.
4. Player death / respawn not re-run (`DEBUG_PLAYER_INVULNERABLE = 1`); the
   clamp change and `borderOpenHook` are inert to `PLAYER_STATE` beyond
   `PLAYER_MAX_Y`.
5. NTSC untested — PAL authoritative; NTSC border compares differ.
6. `#190` enemy-fire ceiling left as-is (readability policy, not geometry).
7. Editor `VIEWPORT_ROWS` still models 23 rows — cosmetic overlay, deferred
   (noted in the prior report).

---

# 15. Q25 — manual playtest instructions

1. `build/shooter.d64` (or `.prg`) — `sha256(prg) = c59f975a7a08cdf6…`. Level 1
   boots straight into PLAYING.
2. **Fly the player straight down.** The ship now descends further (`PLAYER_MAX_Y
   = 237`) and its **whole body stays visible** against a grey `$D021` backdrop
   at the bottom — no black bar clipping the nose/wings. Compare with the prior
   build where the bottom ~4 px were eaten by the border.
3. **Fly the player straight up.** It reaches the top of the visible terrain
   (raster 55) — sprites and terrain now agree there (prior task).
4. The screen no longer has a hard black border top or bottom — the edges fade
   to the terrain backdrop colour.
5. During a wave, watch the extreme bottom edge (below where the player sits):
   at the coarse scroll cadence (~3×/s) the terrain's very bottom edge shifts
   ~6 px against the backdrop — the documented "soft edge". It is below the
   clean gameplay field and is masked to invisibility by the §12 follow-up.
6. No hidden monitor ritual is needed for the verdict.
7. To A/B the soft edge vs a hard crop: set `borderOpenHook`'s two `$D011`
   writes to no-ops (or `GAMEPLAY_RSEL` experiments) and rebuild.

---

# 16. Q26-Q27 — git status; no commit

**Q27: no `git commit`, `git push`, `git add`, tag or branch operation was
performed by this task.**

**Q26 — final `git status`:**
```
On branch experimental-border-hud
Changes not staged for commit:
    modified:   src/main.asm
    modified:   src/raster_scheduler.asm
Untracked files:
    docs/full-200px-aperture-worklog.md
    reports/full-200px-gameplay-aperture-architectural-rework-report.md
```
`HEAD` = `44e735c` (the user committed the three prior tasks as
*"pre-architecture-teardown"* during this task; not by this task). `build/` is
gitignored. Canonical Level-1 assets unmodified. VICE was launched
head-less/background and killed on exit, never foregrounded, no `open -a`.

---

# 17. Before / after summary diagram

```
                         BEFORE (44e735c)                 AFTER (this task)
top border (r16-54)      $D020 black                      OPEN -> $D021 backdrop (HUD-ready)
top soft edge (r52-55)   cropped (row 0 in border)        row-0 overflow terrain, ~4px pop @coarse
gameplay body (r55-246)  clean, 192 px                    clean, 192 px  (UNCHANGED, flawless)
bottom soft edge         cropped @246 (row 24 in border)  row-24 overflow terrain r247-254,
                                                          ~6px pop @coarse, on $D021 backdrop
below (r252-260)         $D020 black border               $D021 backdrop ; SPRITES render here
player max Y             230  (body clipped 4px @246)     237  (body fully visible to ~r258)
[19656] / scheduler      exact / clean                    exact / clean  (UNCHANGED)
next: top-border HUD      top border was black             top border open + clean = the canvas
```
