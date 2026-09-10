# 19656 — High-Score Lifecycle Corruption Fix + Score Font Height

**Result: GREEN.** Root cause found, demonstrated, and fixed; score font reduced
21 px -> 16 px; all Phase 1 / 1.1 work preserved.

---

## 1. Starting HEAD / worktree

Branch `main`, HEAD **`308f430`** *("high score hud working. high score
corruption to fix")*. The git snapshot supplied with the task was one commit
stale (`f71ea24`); `308f430` is the real HEAD and is what everything below is
measured against.

Working tree **clean** at start. Building HEAD's `src/main.asm` reproduces the
Phase 1.1 shipping hash exactly, confirming HEAD == the accepted Phase 1.1 build:

| build | SHA-256 |
|---|---|
| HEAD `308f430` (pre-fix baseline) | `fd42763699bf51c2edf463249d785470eaf499faef4f457dac7f17fe517f8f8c` |
| Priority 1 only (page-ownership fix) | `c73c82900330fab8371d028517b217e43bd08478f9b31aa2ca771221629772e3` |
| **shipping (P1 + 16 px font)** | `809b5edc2eb004f55bf027b2d4bdd92df7ba89bebbe0be2d33fdb9b3496062b7` |

The baseline was rebuilt out-of-tree from `git show HEAD:src/main.asm`, so every
"baseline" number below is a real measurement, not a recollection.

**Nothing committed, staged, tagged or pushed.**

---

## 2. Pre-fix reproduction rate

`tools/vice_lifecycle_rate.py` (new) starts a game, plays a chosen number of
frames, applies one fatal hit through `PLAYER_HIT`, and samples `$D018` once
`GAME_STATE` reaches GAME_OVER — i.e. the first sample after `endGame`.

15 lifecycles at 15 different fatal-hit frames:

| build | ended with `$D018` selecting page B |
|---|---|
| **pre-fix (HEAD)** | **7 / 15 (47%)** |
| post-fix | **0 / 15** |

47% is effectively a coin flip, because the deciding factor is the coarse-flip
parity at the instant `endGame` runs. From a player's seat that reads as
"occasionally", exactly as reported.

`tools/vice_lifecycle_loop.py` (new) against the pre-fix build shows the causal
chain directly — **every** loop that ends on page B is followed by a corrupted
new game, with no exceptions:

```
loop 0: ... game_over_page_A=FAIL initials_visible=FAIL hiscore_page_visible=FAIL
loop 1: new_game_page_A=FAIL new_game_matrix_clean=FAIL no_lives_label=FAIL  game_over_page_A=FAIL ...
loop 2: new_game_page_A=FAIL new_game_matrix_clean=FAIL no_lives_label=FAIL  game_over_page_A=ok   ...
loop 3: (all ok)
loop 4: (all ok)
loop 5: ... game_over_page_A=FAIL initials_visible=FAIL hiscore_page_visible=FAIL
loop 6: new_game_page_A=FAIL new_game_matrix_clean=FAIL no_lives_label=FAIL  game_over_page_A=FAIL ...
loop 7: new_game_page_A=FAIL new_game_matrix_clean=FAIL no_lives_label=FAIL  game_over_page_A=FAIL ...
```

0->1, 1->2, 5->6, 6->7. A 1:1 correspondence between "the previous game ended on
page B" and "this new game is wrong". That is the evidence that the two visible
symptoms are one defect.

---

## 3. First good-vs-bad divergence

The runs are identical through the fatal hit, the explosion animation and the
lives decrement. **The first divergent byte is `$D018`, and it diverges at
`endGame`** — not at the death, and not on the high-score screen where the
symptom first becomes visible.

| sample point | good run | bad run |
|---|---|---|
| fatal hit armed | identical | identical |
| `endGame` -> `GAME_STATE = 2`, `$D018` | `$1F` (page A) | **`$AF` (page B)** |
| `BG_ACTIVE_PAGE` at that point | 0 | 1 |
| initials screen: prompt on the **visible** page | yes | **no** |
| initials screen: prompt present in `$0400` | yes | yes |
| initials screen: non-space cells on the visible page | 35 | **1000** (every cell = stale terrain) |
| menu/high-score page: heading on the visible page | yes | **no** |
| next new game: `$D018` / `BG_ACTIVE_PAGE` | `$1F` / 0 | **`$AF` / 0 — hardware B, software A** |
| next new game: non-terrain cells on the visible page | 0 | **1000 (all `$20`, spaces)** |
| next new game: "LIVES 3" on the visible page | 0 | **1, at row 1 col 17** |
| next new game: `SCROLL_ROW` | 397 | **397 — correct in BOTH** |

Two findings worth stating plainly because they correct the framing in the task:

* **`SCROLL_ROW` is never wrong.** `initBackground` resets it to
  `STAGE_START_ROW` (397) on every single run, good or bad. The next game does
  not literally start partway through the level.
* The bad new game's visible matrix is **1000 space characters**, not terrain.

---

## 4. Root cause

`$D018` is written in exactly three places in the whole program
(`grep 'sta VIC_MEMORY_SETUP'`):

| site | when |
|---|---|
| `src/main.asm:926` | one-time boot init (selects page A) |
| `src/main.asm:7198` | `ssFlipPage`, inside the **disabled** `OPT_SS_FLIP_PROOF` |
| `src/main.asm:8011` | `ssPublishCoarseFlip` — the coarse-scroll page flip |

So after boot, **the only thing that ever moves `$D018` is the gameplay coarse
scroll**, and nothing on the game-over / menu / new-game path moves it back.

Meanwhile every piece of *software* page state already asserts that a fresh game
is on page A:

* `ssFlipCoarseReset` zeroes `SS_PAGEB_ACTIVE` and sets `ssBatchPtrStore+2 = $07`,
  commented *"a fresh game boots on page A"*;
* `ssInitPageB` sets `BG_ACTIVE_PAGE = 0`, commented *"boot displaying page A"*.

**The software asserted page A; the hardware was never told.** That is the bug.

### 4.1 Why the high-score screen is corrupt

`endGame` carefully restores `$D011`, `$D016`, `$D021`, `$D022/$D023` and the
character ROM for the menu — but not `$D018`. If the last life ended while page B
was displayed, the VIC keeps fetching `$2800` while `enterGameOver`,
`enterInitials`, `drawInitialsScreen`, `insertHiscore`, `drawHiscorePage` and
`enterMenu` all draw into `$0400`.

The result is exactly the reported symptom set: the screen shows the frozen
gameplay terrain instead of the initials page (hence "badly corrupted", and
measured as 1000 non-space cells); nothing crashes, because only the *display
base* is wrong; and Fire still works, because input never touches screen RAM.

### 4.2 Why the next new game is wrong, and why "LIVES 3" lands in the terrain

`startGame` runs in this order:

```
147 chrout            -> clears $0400
setupDebugDisplay
setupScoreDisplay
setupLivesDisplay     -> stamps "LIVES 3" at LIVES_SCREEN ($0400 + 17), matrix row 0
...
initBackground        -> paints all 25 rows PAGE-AWARE
ssInitPageB           -> copies A -> B, sets BG_ACTIVE_PAGE = 0
```

`initBackground`'s row loop reaches screen RAM through `copyIncomingRowToScreen`,
which is page-aware:

```asm
copyIncomingRowToScreen:
    ldy BG_DEST_ROW
    lda starRowLo,y
    sta TEXT_DST
    lda starRowHi,y
#if OPT_SECOND_SCREEN
    ldy BG_ACTIVE_PAGE                      // <-- still the PREVIOUS game's value
    clc
    adc ssActiveHiDelta,y
#endif
```

`BG_ACTIVE_PAGE` is not reset until `ssInitPageB`, which runs **after** the
paint. So in the bad case:

1. the fresh terrain is painted into page B (`$2800`);
2. `ssInitPageB` then copies **A -> B**, overwriting that terrain with the
   contents of `$0400` — a freshly cleared screen plus `setupLivesDisplay`'s
   seven "LIVES 3" cells;
3. `$D018` still selects B, so the player sees the blank copy with "LIVES 3" in
   it, while the correctly painted origin viewport is discarded.

"LIVES 3" is written at matrix row 0. The scroller shifts content **downward**,
so successive coarse steps carry those seven cells down the screen — which is
why it is seen "near the bottom of gameplay terrain" rather than at the top.

### 4.3 Why the run then looks like it "starts partway through the level"

After the copy, `BG_ACTIVE_PAGE = 0` claims page A is displayed while `$D018`
actually shows B. The inactive-page builder therefore writes the next coarse
state into the page the VIC is *really* fetching, so the player watches terrain
rows appear one at a time over a blank matrix. The proper start-of-level
viewport is never presented at all. On the first flip, `ssPublishCoarseFlip`
writes `ssInactiveD018[0]` = page B — a no-op on the hardware — and toggles
`BG_ACTIVE_PAGE` to 1, at which point hardware and software silently agree again
and the game continues normally. That self-healing is why it never crashes and
why the damage is confined to the opening seconds.

---

## 5. Affected memory / state ownership

| item | owner | reset per game? |
|---|---|---|
| `$D018` screen nibble | `ssPublishCoarseFlip` only | **NO — the defect** |
| `BG_ACTIVE_PAGE` | `ssInitPageB` | yes, but **after** `initBackground` paints — **the second half of the defect** |
| `SS_PAGEB_ACTIVE`, `ssBatchPtrStore+2` | `ssFlipCoarseReset` | yes (via `initBackground`) |
| `SS_FLIP_PENDING/HOLDOFF`, `SS_PTR_MIRROR_READY`, `ssFlipStats` | `ssFlipCoarseReset` | yes |
| `SS_BUILD_STATE`, `SS_INACTIVE_VALID`, build target row | `ssInactiveBuildReset` | yes |
| `SCROLL_ROW/_HI`, `SCROLL_FINE`, `BG_COARSE_*` | `initBackground` | yes |
| screen page A `$0400` / page B `$2800` | shared: KERNAL + text routines write A; scroller writes both | — |

Exactly two things were unreset, and both are page ownership.

### 5.1 Memory/layout audit (the Phase 1 widening)

Checked specifically for the failure modes named in the brief. **No overlap and
no off-by-one was found** — the boundaries are exact, and here they are:

| block | span | next symbol | verdict |
|---|---|---|---|
| `HISCORE_PAGE_BUF` | `$8014..$806b` (88 = 8 x 11) | `scoreFont` at `$806c` | exact, adjacent, **no overlap** |
| `HISCORE_NAME` | `$2318..$232f` (24 = 8 x 3) | `PLAYER_HIT` at `$2331` | 1 byte slack |
| `scoreFont` | `$806c..$810b` (160 = 10 x 16) | `scoreFontOffset` at `$810c` | exact |
| `SCORE_LO/MID/HI` | `$235b..$235d` | `SCORE_DIRTY $235e` | fine |

* `HISCORE_ROW_WIDTH = 11` is honoured everywhere: the buffer is
  `HISCORE_COUNT * HISCORE_ROW_WIDTH`, offsets are computed as `entry * 11`,
  `drawHiscorePage` draws `HISCORE_ROW_WIDTH` chars, and rows start at column 15
  (15 + 11 = 26 < 40). **No stale 10-char assumption survives.**
* `formatScore6` writes 6 digits at `base + HISCORE_DIGIT_OFFSET`; the worst-case
  index is `7*11 + 5 + 5 = 87`, inside the 88-byte buffer. No formatter overrun.
* `HISCORE_MID` is at `$800c`, split from `HISCORE_LO`/`HISCORE_HI` at
  `$2308`/`$2310` (the middle byte was re-homed into the `$8000` module when the
  `$2000` state block overflowed). Functionally correct, worth knowing.
* The one thing worth flagging for the future: `HISCORE_PAGE_BUF` ends exactly
  where `scoreFont` begins, and `HISCORE_NAME` ends one byte before `PLAYER_HIT`.
  Both have essentially zero slack, so any further widening of a row or of the
  table needs a deliberate re-home rather than a constant bump.

**Answering the brief's question 5 directly: no, the widening did not create the
corruption.** It is unrelated; the defect predates it and is purely `$D018`
ownership.

---

## 6. Why the two symptoms were linked

They are the same missing write, observed one game apart:

* **Same game:** `$D018` left on page B -> GAME OVER / initials / high-score
  drawn into the invisible `$0400` -> "corrupt high-score screen".
* **Next game:** the same stale `BG_ACTIVE_PAGE`/`$D018` pair makes
  `initBackground` paint the wrong page and `ssInitPageB` clobber it -> blank
  matrix + "LIVES 3" + terrain appearing progressively.

The loop harness proves the link empirically: 4 bad game-overs, 4 corrupted
following games, 0 corrupted games after a clean game-over. That is why the bad
new-game state "has only been observed after a corrupt high-score ending".

---

## 7. The exact fix

Three changes to `src/main.asm`; no architecture touched.

### 7.1 New routine `ssSelectPageA`

```asm
ssSelectPageA:
    lda VIC_MEMORY_SETUP
    and #%00001111                          // Preserve the char base ($3800) + unused bits.
    ora #(BG_SCREEN_A_D018 & %11110000)     // Screen base -> page A ($0400).
    sta VIC_MEMORY_SETUP
    lda #0
    sta BG_ACTIVE_PAGE
    rts
```

Read-modify-write rather than a flat store, so it can never disturb the
character base — mirroring how boot init writes the same register.

### 7.2 Called from `endGame`

Placed in the existing "restore display state for the menu" cluster, right after
the `$D016` multicolour restore. Every non-gameplay screen is now drawn on the
page the VIC is fetching. No IRQ interaction: `endGame` has already torn the
raster chain down and restored the KERNAL vector.

### 7.3 Called from `startGame`, **before** `initBackground`

So the page-aware terrain paint targets the displayed page, and `ssInitPageB`'s
A -> B copy propagates real terrain instead of clobbering it.

Either call alone would fix the observed failures, because after `endGame`
nothing moves `$D018` until the next game's first coarse flip. Both are present
deliberately: `startGame` should not silently depend on a value another routine
happened to leave behind, and the two call sites are what make the existing
`ssFlipCoarseReset` / `ssInitPageB` "boots on page A" comments actually true.

### 7.4 Secondary: the vestigial "LIVES 3" write

`setupLivesDisplay` stamped "LIVES 3" into `LIVES_SCREEN` (`$0400 + 17`) — matrix
row 0, which since Phase 1.5 carries scrolling terrain. This is the identical
retired-character-HUD scribble that Phase 1 already removed for
`setupScoreDisplay`'s "SCORE 00000". It survived only because `initBackground`
repaints immediately afterwards — on whichever page `BG_ACTIVE_PAGE` names — so
it became visible precisely when page ownership was wrong.

The screen/colour writes are removed; the `PLAYER_LIVES = PLAYER_START_LIVES`
stock reset, which is the routine's real job, is kept. This is defence in depth,
not the root-cause fix, and is reported as such. (`displayLives` is left alone:
it is guarded to draw only when *not* PLAYING and is only ever called during
PLAYING, so it never writes.)

---

## 8. Repeated post-fix lifecycle results

`tools/vice_lifecycle_loop.py`, one VICE instance, consecutive full lifecycles,
fatal-hit delay swept per iteration so both coarse-flip parities are exercised.
Joystick neutral except the taps the lifecycle requires.

| run | loops | checks | failures |
|---|---|---|---|
| lifecycle + high-score verification | 16 | 12/loop = **192** | **0** |
| lifecycle + high-score + death/respawn | 10 | 16/loop = **160** | **0** |

Per-loop checks, all green in every loop:

| check | what it proves |
|---|---|
| `new_game_origin` | `SCROLL_ROW == STAGE_START_ROW` (397) on the first PLAYING frame |
| `new_game_page_A` | `$D018` selects A **and** `BG_ACTIVE_PAGE == 0` (hardware and software agree) |
| `new_game_matrix_clean` | **0** of 1000 visible cells hold a code below the terrain range (96) |
| `no_lives_label` | the "LIVES 3" screen-code sequence appears **0** times |
| `death_anim_ran` / `respawned` / `life_consumed` | `PLAYER_STATE` 0->1->2->0, lives 3->2 |
| `respawn_colour_blue` | `OBJECT_COLOUR == 14` after respawn |
| `game_over_page_A` | the game ends with `$D018` on page A |
| `initials_reached` / `initials_visible` | ENTER_INITIALS entered, and the exact 19 prompt screen codes are on the **visible** page |
| `menu_reached` / `hiscore_page_visible` | Fire returns to menu; "HIGH SCORES" heading on the visible page |
| `hiscore_digits_match_stored` | every rendered row equals its stored 24-bit value |
| `hiscore_sorted_desc` / `hiscore_inserted_present` | table ordering and real insertion |

Post-fix `vice_lifecycle_rate.py`: **0 / 15** ended on page B; the prompt was on
the visible page 15/15; visible non-space 34–36 (text only, never 1000).

---

## 9. Score font: old vs new dimensions

| | old (Phase 1.1) | **new (this work)** |
|---|---|---|
| glyph | 6 px wide x **21 px** tall | 6 px wide x **16 px** tall |
| digit cell / pitch | 8 px byte-aligned | **unchanged** |
| six-digit span | 46 px | **46 px — unchanged** |
| sprite X (L / R) | 161 / 185 | **unchanged** |
| `HUD_SCORE_GLYPH_H` | 21 | 16 |
| `HUD_SCORE_TOP_ROW` | 0 | 2 |
| `HUD_Y`, handoff rasters 43 / 56 | — | **unchanged** |
| font table | 210 bytes | 160 bytes |

**Measured on the running game** (VICE 384x272 screenshot, six values):

| value | lit rows | height | x range | span | colours |
|---|---|---|---|---|---|
| 000000 | 9..24 | **16** | 169..214 | 46 | 1 — `(183,255,134)` |
| 123456 | 9..24 | 16 | 170..214 | 45 | 1 |
| 999999 | 9..24 | 16 | 169..214 | 46 | 1 |
| 065536 | 9..24 | 16 | 169..214 | 46 | 1 |
| 111111 | 9..24 | 16 | 170..214 | 45 | 1 |
| 888888 | 9..24 | 16 | 169..214 | 46 | 1 |

Height is identical for every value. The right edge is **214 in every case**;
the left edge is 169 except for values beginning with `1`, where it is 170 —
that glyph's blank leading column, exactly as in the 21 px font. The six digit
*cells* are fixed on the 8 px grid (169, 177, 185, 193, 201, 209), so **the
number does not move horizontally as it changes.** Single colour throughout
confirms light green with no fringing.

Retained as required: six digits, green (`HUD_SCORE_COLOUR = 13`), thin 1 px
stroke, narrow geometric City/MU-TH-UR character, no visible join. Horizontal
geometry deliberately untouched — only vertical proportion was tuned.

The design moved into **`tools/score_font_design.py`**, which holds the glyphs as
ASCII art and is both the generator (`--emit`) and an *independent* oracle
(`--verify`): it re-derives the bytes from the drawing and compares them against
what KickAssembler actually put in the PRG. Result: **160 bytes MATCH**.
Structural properties it asserts, all true: `9 == rot180(6)`; a single 1 px
stroke outside the deliberate bars; inter-digit gap bits always clear; every
glyph uses row 0 and row 15. The structural grid is bar rows 0 / 7 / 15, with
row 7 the shared middle (3's waist, 4's crossbar, 5's and 6's shoulder, 8's bar)
— the role rows 0 / 10 / 20 played at 21 rows.

---

## 10. Font / compositor timing

`tools/vice_score_compose_timing.py` (new): CPU-cycle delta from
`composeScoreSprites` to `publishScoreBuffer`, measured **in situ** on the real
game with the real raster IRQ and multiplexer running, so ambient badline and
sprite-DMA inflation is included. 40 samples each, values cycled 999999 /
123456 / 808080, entry raster 79..199 in both.

| build | min | max | median | raster lines |
|---|---|---|---|---|
| 21 px (HEAD baseline) | 1282 | 1453 | 1389 | 20.3 – 23.1 |
| **16 px (shipping)** | **1012** | **1129** | **1014** | **16.1 – 17.9** |

About 27% cheaper, tracking the 16/21 row ratio. The compositor was already
parameterised by `HUD_SCORE_GLYPH_H` / `HUD_SCORE_TOP_ROW`, so no restructuring
was needed.

---

## 11. Double buffering is intact

Unchanged and re-proven on the shipping build:

| check | result |
|---|---|
| composes that drew into the **published** pair | **0 / 40** |
| published pointer pairs observed | `$bc/$bd` and `$be/$bf`, alternating |
| `HUD_SCORE_BITMAP_B` (back-pair offset) | `$80`, unchanged |
| publish still via `hudProofPtr` under `SEI` | unchanged |
| `refreshScoreIfDirty` 7-phase deferred rebuild | unchanged |
| presented frames dropped under score churn | **0 / 300** (§13) |

The architecture was not undone, reduced or bypassed. The only change inside the
score module is the font table and two constants.

Note: with `TOP_ROW = 2` / `H = 16` the compositor writes rows 2..17 and no
longer rewrites all 21 rows. Rows 0–1 and 18–20 are zero-filled at assembly time
(`.fill HUD_SPRITE_COUNT * 64, $00`) and are never written by anything, so they
remain permanently transparent — the Phase 1 situation, and confirmed by the
measured 16-row height with no stray pixels.

---

## 12. Colour / collision preservation (Priority 3)

Verified against the source and, where observable, live:

| item | state |
|---|---|
| `PLAYER_COLOUR_NORMAL` | **14** (light blue) — unchanged |
| `PLAYER_COLOUR_MUZZLE` | **2** (red) — unchanged |
| respawned player colour, measured live | `OBJECT_COLOUR == 14` in 10/10 loops |
| `DEBUG_PLAYER_INVULNERABLE` | **0** — collisions can kill the player |
| death / respawn / invulnerability | exercised 10/10 loops: `PLAYER_STATE` 0->1->2->0, lives 3->2 |
| 24-bit six-digit high score | verified end to end, §13 |
| HUD double-buffering | §11 |
| `$07F8` / `$2BF8` publication | §13, page-aware, 0 failures over 5600 captured frames |
| gameplay sprite capacity | `max_objects 16` / `max_batches 8` — identical to baseline |
| `HUD_SLOT_FIRST` 4, `HUD_SPRITE_COUNT` 4, `HUD_Y` 22, handoff 43 / 56 | all unchanged |

The diff touches none of the collision, colour, sprite-pointer or handoff code.

---

## 13. Full regression

All captures on the shipping build `809b5edc…`; `frame_cycle_deltas` is the
presented-frame period, exact PAL = 19656.

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | catchups | replay | page A / B |
|---|---|---|---|---|---|---|---|---|---|
| ordinary | 1400 | `[19656]` | 0 | 0 | 9 | 0 | 0 | 1 | 728 / 672 |
| **dense** | 900 | `[19656]` | 0 | 0 | 16 | 8 | 6286 | 450 | 452 / 448 |
| **y199 / 199-235** | 400 | `[19656]` | 0 | 0 | 9 | 1 | 0 | 0 | 211 / 189 |
| stage wrap (`--seed-scroll 30`) | 1200 | `[19656]` | 0 | 0 | 9 | 1 | 2 | 7 | 655 / 545 |
| stage wrap (`--seed-scroll 352`) | 900 | `[19656]` | 0 | 0 | 9 | 1 | 2 | 9 | 369 / 531 |
| aperture, passive | 400 | `[19656]` | 0 | 0 | 8 | 0 | 0 | 0 | 208 / 192 |
| aperture, dense | 400 | `[19656]` | 0 | 0 | 16 | 8 | 2786 | 200 | 208 / 192 |
| **baseline HEAD, dense** | 900 | `[19656]` | 0 | 0 | 16 | 8 | **6286** | **450** | **452 / 448** |
| **baseline HEAD, y199** | 400 | `[19656]` | 0 | 0 | 9 | 1 | 0 | 0 | **211 / 189** |

Dense and y199 are **byte-identical between the shipping build and the pristine
HEAD baseline** — every metric, including `catchups 6286` and `replay 450`. That
is what isolates this work from the scroller/mux.

| other check | result |
|---|---|
| clean build | **pass** — 0 errors, 0 warnings |
| exact `[19656]` | **pass** in all seven captures |
| service failures | **0** across 5600 captured frames |
| sprite-start misses | **0** across 5600 captured frames |
| ordinary gameplay | pass (1400 frames) |
| death / respawn | pass, 10/10 loops, real collision path |
| GAME OVER -> HIGH SCORE -> MENU -> NEW GAME loops | **26 loops, 352 checks, 0 failures** (§8) |
| correct new-game stage origin every time | **pass** — `SCROLL_ROW == 397`, 26/26 |
| no stale `LIVES 3` | **pass** — 0 hits, 26/26 |
| high-score insertion / rendering above 65535 | **pass** — e.g. stored `[500000, 480000, 460000, 440000, 420000, 400000, 380000, 360000]` renders `['500000','480000','460000','440000','420000','400000','380000','360000']`; leading zeroes present (`000100`); sorted descending; six digits every row |
| stage wrap | **pass** — 74 coarse steps, 1 end->start wrap (row 0 -> 419), every step a single decrement, 0 bad steps |
| dense mux | **pass**, identical to baseline |
| y199 / 199-235 | **pass**, identical to baseline |
| seed 352 | **pass** |
| Stage 5 aperture (`--aperture 55 246`) | **0 body / 0 lastrow diffs**, passive **and** dense; all eight fine phases exercised |
| page-aware fallback | `page_aware: true`, both pages exercised in every capture |
| A/B pointer publication | validated per frame by `check_raster_capture` against the live page's table (`$07F8` or `$2BF8`) — 0 mismatches |
| HUD handoff | 0 service failures / 0 sprite-start misses under dense load |
| no gameplay sprite-capacity loss | `max_objects 16`, `max_batches 8` — identical to baseline |
| score updates drop presented frames | **0 / 300** in all three regimes: idle, +100 every frame, and the pathological 999999 rebuild every frame — all exact `[19656]` |
| encounter fixtures A–R | 16/18 PASS; **J and L FAIL — identical on the pristine baseline** |

---

## 14. Known pre-existing failures and tool breakage

Reported honestly; none is caused by this work, and all reproduce on the
pristine HEAD baseline.

1. **Encounter fixtures `J_wave_start_deferred_then_starts` and
   `L_pressure_clear_wave_eligible` FAIL.** Verified by running the fixture
   suite against the pristine baseline build in this session: identical two
   failures, identical 16 passes. Outside this task's scope.

2. **`tools/check_scroll_capture.py` is broken against the current memory map.**
   It reads `BG_COARSE_*` from a `$2920..$2fff` dump, but Stage 4A's
   `OPT_SS_RELOCATE` moved that block to `$9000+` (`BG_COARSE_DEFERRED` is at
   `$97fe` in **both** builds). It raises `IndexError` on every current capture.
   Its terrain-matrix oracle has therefore been non-functional since Stage 4A —
   which is consistent with the Phase 1 / 1.1 reports, neither of which quotes
   it. I did not repair it (out of scope); I added
   `tools/check_stage_wrap.py`, which covers the scroll-position half from the
   `$2000` state dump, and relied on `check_scroll_edges_rsel1` for pixel-level
   terrain continuity.

3. **`tools/vice_raster_lifecycle.py` is broken.** It references
   `TURRET_DESIRED_STYLE`, which exists in neither build's symbol table, and
   dies with `KeyError` before capturing anything. Death/respawn coverage was
   therefore implemented inside `tools/vice_lifecycle_loop.py` instead.

4. **Passive `body_temporal_diffs`.** Measured **0** here on both passive and
   dense aperture captures. Phase 1.1 already established that this metric is
   run-to-run variance driven by CIA-random wave timing, not a fixed property of
   a build, so 0 is not evidence of an improvement any more than 32 would have
   been evidence of a regression.

5. **The accepted authored multi-turret cosmetic flicker** was not touched or
   reopened, per the brief.

### A measurement error I made and corrected

My first dense/y199 captures reported `frame_cycle_deltas [39312]`, ~3599
"service failures" and 15 sprite-start misses — alarming numbers that reproduced
**identically on the pristine baseline**, which is what told me they were not a
regression. Cause: I omitted `--physical`. Without it the capture breakpoint is
once per *presented* frame, which under dense load is every *other* physical
frame, and `check_raster_capture` then windows its trace events over 19656
cycles of a 39312-cycle interval, so every frame reports spurious mask-count
mismatches. With `--physical` the documented baseline reproduces exactly
(`catchups 6286`, `replay 450`, 0/0). The table in §13 is the corrected run.

---

## 15. Build / test artifact cleanup

The previous multi-GB `build/` accumulation was specifically avoided.

* **Every** emulator capture went to a scratch root **outside the repository**
  (the session scratchpad under `/private/tmp/...`), never to `build/`.
* `tools/run_regression_suite.sh` (new) deletes each capture directory
  **immediately after analysing it** and keeps only the small JSON summaries; it
  also prints each capture's size. Peak transient usage was ~70 MB for one
  capture at a time; the seven captures would have been ~270 MB had they
  accumulated.
* Fixed output locations are reused (`build/shooter.prg`, `build/main.vs`); the
  out-of-tree baseline build went to scratch, and the temporary
  `src/.baseline_main.asm` used to produce it was deleted in the same command.
* Scratch after cleanup: **296 KB** (JSON summaries only).
* Repository `build/` after this work: **300 KB**, 4 files
  (`shooter.prg`, `shooter.d64`, `main.vs`, `main.sym`) — the same shape as
  before the task. **No per-run, per-seed or timestamped files were left.**
* Transient PNGs from the font measurement are deleted unless `--keep` is passed.
* `/tmp/shooter-charset.bin` and the `/tmp/c64-*` scratch dirs were removed.
* One orphaned `x64sc` (port 6547, left spinning at 99.7% CPU by the crash of the
  pre-existing `vice_raster_lifecycle.py`) was identified by pid and terminated.
  No unrelated, user-launched VICE instance was touched.

**VICE focus discipline:** every instance is launched directly via
`subprocess.Popen` / background `&` on the binary path — never `open -a` — so no
automated run activates or focuses the VICE application. All driving is through
the remote monitor; the only emulated input is `jpdb` joystick state, which is
required to start a game and enter initials.

---

## 16. Manual test checklist

1. **Build and run.** `java -jar KickAss.jar src/main.asm -odir build -o build/shooter.prg -vicesymbols`, then start a game.
2. **Score height.** The number should be noticeably shorter than before — about three-quarters the previous height — sitting centred in the top border band with a little clearance above and below. It should still read as a terminal readout: narrow, squared, hairline strokes.
3. **All ten digits.** Score past each: `0`/`8` differ by the middle bar, `6`/`9` are 180° rotations, `1` has a base bar, `4`'s crossbar sits on the same row as `3`'s and `8`'s middle.
4. **Join and stability.** The gap between digits 3 and 4 (the sprite join) should be indistinguishable from the others; as the score climbs past `001000` and `010000` the number must not shift sideways.
5. **The lifecycle, several times over.** Play, lose all lives, and go GAME OVER -> initials -> menu -> new game **at least six times**, deliberately dying at different moments. Every time:
   * the initials screen must be clean text over stars — **never** frozen terrain;
   * Fire must return to the menu;
   * the high-score page must show six digits per row with leading zeroes;
   * the next game must start at the **top of the level** with full terrain from the first frame;
   * there must be **no "LIVES 3"** anywhere in the playfield, at any height.
6. **The old failure specifically.** The bug depended on where the coarse scroll happened to be when the last life went. Vary it: die immediately after a coarse step and again just before one. Both must behave identically now.
7. **Blue player, red muzzle.** The ship is light blue with a light-grey highlight; holding fire flashes it red for ~3 frames per volley. Enemies and turrets are unchanged.
8. **Damage and death.** Take a hit: explosion plays, a life is lost, the ship respawns blue and blinks briefly invulnerable.
9. **High scores above 65,535.** Score past 65535 and qualify; the table must store and render it correctly (e.g. `065536`, `123456`).
10. **Dense waves.** Watch the top border during heavy waves — no HUD flicker, and gameplay sprite capacity should look unchanged.

---

## 17. Files changed

* `src/main.asm` — the only source file modified (`ssSelectPageA` + two call
  sites; `setupLivesDisplay` screen write removed; font table and two constants).
* `docs/high-score-lifecycle-corruption-worklog.md` — new, per AGENTS.md.
* `reports/high-score-lifecycle-corruption-fix.md` — this report.
* New tooling: `tools/score_font_design.py`, `tools/vice_lifecycle_pages.py`,
  `tools/vice_lifecycle_rate.py`, `tools/vice_lifecycle_loop.py`,
  `tools/vice_score_compose_timing.py`, `tools/vice_score_font_measure.py`,
  `tools/vice_score_acceptance.py`, `tools/check_stage_wrap.py`,
  `tools/run_regression_suite.sh`.

`src/background_turrets.asm` and `src/raster_scheduler.asm` are unmodified.

**Nothing committed, staged, tagged or pushed.**
