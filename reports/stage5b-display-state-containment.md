# Stage 5B — Display-State Containment Fix

Branch `main`, HEAD `d60828a` (unchanged). Nothing committed, staged, tagged or
pushed. The Stage-5 comparison state is intact: the Fable prototype is still in
the working tree (now with this fix applied on top), and the original Stage-5A
candidate remains preserved in `reports/stage5a-candidate-as-tested.patch`.

## Verdict: **GREEN — ready for user visual acceptance**

The title/high-score starfield regression is fixed at its architectural root:
the gameplay edge-mask bit no longer lives in a constant that non-gameplay code
inherits. Gameplay masking is unchanged (aperture still fixed 58..247 on every
fixture), the mask-off build is still byte-identical to Stage 4J, and the whole
`TITLE → GAME → GAME OVER → starfield → GAME` cycle is proven clean.

| build | SHA-256 (16) | |
|---|---|---|
| `SCROLL_EDGE_MASK` off | `80d5b0461c070fe2` | accepted Stage 4J Mode C — **byte-identical**, re-verified after every edit |
| before this fix (Fable prototype) | `b719de4ca86c7f54` | starfield broken from power-on |
| **after this fix** | `69224428ddb05c8a` | starfield correct, mask intact |

---

## 1. The defect, reproduced before any change

Probed the broken build (`b719de4c…`) in VICE on the attract/title screen:

```
$D011 = $5B   ECM bit6 = 1   BMM = 0   DEN = 1   RSEL = 1   YSCROLL = 3
$D016 = $C8   MCM = 0        $D018 = $1F
IRQ vector $0314 = $EA31 (KERNAL)   GAME_STATE = 0 (MENU)
star-range codes (240..251) on screen: 16
   +162  code 244 ($F4)  -> ECM masks to glyph 52 ($34)  = screen code '4'
   +173  code 242 ($F2)  -> ECM masks to glyph 50 ($32)  = screen code '2'
   +342  code 246 ($F6)  -> ECM masks to glyph 54 ($36)  = screen code '6'
   +392  code 240 ($F0)  -> ECM masks to glyph 48 ($30)  = screen code '0'
```

**ECM was set on the attract screen straight out of power-on** — before gameplay
had ever been entered, with the KERNAL IRQ installed and no Stage-5 raster events
running. That single fact explains both reported symptoms.

### Why the stars became digit blocks
In ECM the VIC masks the character code to 6 bits. The starfield uses
`STAR_CHAR_BASE = 240`, codes 240..251, so `240..251 & 63 = 48..59` — the ROM
glyphs for `0123456789:;`. Every star cell fetched a digit instead of its star
glyph. The measured cells above show exactly that mapping.

### Why smooth motion became character-step motion
This is the same cause, not a second bug. **The starfield never used `$D011`
fine scroll.** Its sub-row motion is *glyph phase*: `drawOneStar` computes the
code as `STAR_CHAR_BASE + size*4 + STAR_PHASE`, and `updateStarfield` advances
`STAR_PHASE` 0→3 ("Advance by two pixels inside its current character cell"),
only incrementing `STAR_Y` when the phase wraps. Under ECM the four phase glyphs
240,241,242,243 collapse to 48,49,50,51 = `'0','1','2','3'` — four *different
digits* at the same position. So the 2-pixel sub-row steps rendered as a cycling
digit (the user's "cycling 1,2,3,0"), and the only motion left that changed the
cell's screen position was the whole-character-row `STAR_Y` increment.

### The fine-scroll bits were **not** being corrupted
Measured `YSCROLL = 3` on the title screen, which is exactly what `endGame`/`init`
intend for the non-scrolling text screens. No fine-scroll damage occurred; the
"row-step motion" symptom was entirely the glyph-phase collapse above.

---

## 2. Root cause — a gameplay constant used as global boot state

Stage 5A put the mask bit into the shared display constant:

```asm
.const GAMEPLAY_D011_BASE = $10 | (GAMEPLAY_RSEL << 3) | $40   // ECM=1
```

and that constant has **four** consumers — three gameplay, one *not*:

| site | context | inheriting ECM correct? |
|---|---|---|
| `raster_scheduler.asm` `rasterFrameReset` | gameplay IRQ, line 1 | yes |
| `raster_scheduler.asm` `publishRasterPlan` | gameplay, ~raster 19 | yes |
| **`main.asm:848` `init`** | **BOOT — builds the global display state** | **no** |

`init` does `lda VIC_CONTROL_1 / ora #GAMEPLAY_D011_BASE / sta VIC_CONTROL_1`
to establish the machine-wide display state before the attract screen. Once ECM
joined that constant, boot itself set the gameplay mask bit, and the attract and
high-score screens rendered under it. No state transition was needed — the
regression was present on the very first frame after power-on.

`endGame` did clear ECM (`and #%00111000`), which is why the screens could look
correct *after* a game had been played and lost — but that was a downstream
patch compensating for state that should never have been global in the first
place. It could not help the boot path at all.

**Were Stage-5 raster events running outside gameplay?** No. `endGame` disables
the VIC raster IRQ and restores the KERNAL vector ($EA31, confirmed in the probe
above), so `rasterFrameReset` / the mask event / `borderOpenHook` do not run in
menu states. The leak was purely the constant, not live events.

---

## 3. The fix — ownership, not more clearing

The band bit is removed from the shared constant and given a name of its own, and
is applied **only inside the gameplay raster chain**:

```asm
// main.asm
.const GAMEPLAY_D011_BASE  = $10 | (GAMEPLAY_RSEL << 3)   // DEN, RSEL. NO ECM.
.const EDGE_MASK_D011_BAND = $40                          // ECM; with MCM=1 -> invalid mode -> black
```

| site | change |
|---|---|
| `initRasterScheduler` (called only from `startGame`) | **establishes** the band once at gameplay entry, so frame 1 of every game is already masked |
| `rasterFrameReset` (line 1, gameplay IRQ only) | `ora #GAMEPLAY_D011_BASE` **+ `ora #EDGE_MASK_D011_BAND`** — the band is (re-)established here every frame |
| `publishRasterPlan` | **preserves** the live band/body bit (`and #EDGE_MASK_D011_BAND`) — it must neither force the band (would black the frame if it ran after the aperture opened) nor force the body (would unmask the top band) |
| mask raster event / `borderOpenHook` | unchanged — clear at `EDGE_MASK_BODY_RASTER`, set at `EDGE_MASK_BAND_RASTER` |
| `init` (boot) | unchanged instruction; it now simply cannot inherit ECM |
| `endGame` | unchanged; its ECM clear remains as the teardown safety net for ending mid-band |

The ownership rule this establishes: **the mask bit is set only by code that runs
while the gameplay raster chain is installed, and cleared when that chain is torn
down.** Every non-gameplay state therefore inherits a mask-free `$D011` by
construction rather than by remembering to clear a bit.

This also removed a latent hazard: with ECM in the base constant, the boot path
was the *only* reason the menu ever worked after a game — any future non-gameplay
screen added without an ECM clear would have been broken too.

---

## 4. Evidence — full lifecycle, final build `69224428…`

Sampled at breakpoints so the machine is halted at a known point each time:

```
  OK 1. attract/title              $D011=$1B ECM=0(want 0) YSCROLL=3 state=0(MENU)      stars=16
  OK 2. FIRST gameplay frame       $D011=$50 ECM=1(want 1) YSCROLL=0 state=1(PLAYING)   stars=0
  OK 3. steady gameplay @frame top $D011=$54 ECM=1(want 1) YSCROLL=4 state=1(PLAYING)   stars=0
  OK 4. GAME OVER                  $D011=$13 ECM=0(want 0) YSCROLL=3 state=2(GAME_OVER) stars=15
  OK 5. starfield after game       $D011=$13 ECM=0(want 0) YSCROLL=3 state=2(GAME_OVER) stars=15
  OK 6. 2nd game, FIRST frame      $D011=$50 ECM=1(want 1) YSCROLL=0 state=1(PLAYING)   stars=0
  OK 7. 2nd game steady            $D011=$52 ECM=1(want 1) YSCROLL=2 state=1(PLAYING)   stars=0
```

Plus, sampled 12 consecutive frames at `gameplayPresented` (raster 19, ahead of
the aperture) well into a game: **band (ECM=1) 12/12**, with YSCROLL cycling
6,7,0 — the fine scroll and the mask both alive and independent. No state
accumulates across the two full game cycles.

**First-frame note.** During the fix I found (and closed) a real one-frame gap:
because `publishRasterPlan` only *preserves* the band, and on the first frame of
a game it can run before the first `rasterFrameReset`, that frame would have
rendered unmasked — a single-frame edge flash at game start. The
`initRasterScheduler` establish removes it; checkpoints 2 and 6 above are the
proof (`$D011 = $50`, band set, on the very first `gameplayPresented` of both
games).

---

## 5. Gameplay mask and Stage-4 invariants — unchanged

Terrain aperture measured per frame (sprite-tolerant classifier, 130 frames each):

| fixture | aperture | frames |
|---|---|---|
| wave 382 / wrap 12 / dense / turret / stress | **58..247** | 130/130 each |

Full regression on `69224428…`:

| fixture | frames | replay | catchup | `[19656]` | svc fail | incomplete | sprite-start miss | page A/B | LATE / FALLBACK |
|---|---|---|---|---|---|---|---|---|---|
| idle | 300 | 0 | 0 | ✅ | 0 | 0 | 0 | 156/144 | 0 / 0 |
| authored wave 382 | 320 | 2 | 1 | ✅ | 0 | 0 | 0 | 158/162 | 0 / 1 |
| stage wrap 12 | 340 | 5 | 2 | ✅ | 3 † | 0 | 0 | 180/160 | 0 / 0 |
| `--y199` | 400 | 0 | 0 | ✅ | 0 | 0 | 0 | 211/189 | 0 / 0 |
| `--dense` | 200 | 100 | 1386 | ✅ | 0 | 0 | **0** | 104/96 | 0 / 0 |
| turret-playtest | 500 | 0 | 0 | ✅ | 0 | 0 | 0 | 260/240 | 0 / 0 |
| accelerated stress | 500 | 0 | 0 | ✅ | 0 | 0 | 0 | 272/228 | 3 / 0 |

† the three known pre-existing wrap items documented in the Fable review (two
HUD flip-transition oracle caveats at the first page-B frame, plus the Stage-4F
`ssFlipMirrorPtrs`-after-batch race at frame 88). Not introduced here.

Exact PAL `[19656]` everywhere, zero incomplete frames, zero sprite-start misses
on every fixture including `--dense`, `--y199` still scrolling, page-aware
pointer oracle active. Mode-C scroller, `$D018` publication, pending-LIVE
progression, builder, BUILD/LIVE separation, sprite mux, HUD handoff, collision,
turrets and stage data all untouched.

---

## 6. Manual visual validation — what to check

Build and run `build/shooter.prg` (`69224428…`). To A/B, comment
`#define SCROLL_EDGE_MASK` in `src/main.asm` and rebuild — that is the accepted
Stage 4J binary.

1. **Title screen, from power-on.** Stars must be small star shapes, not digits.
2. **Star motion.** Stars must drift smoothly in ~2-pixel steps, not jump a whole
   character row at a time.
3. **High-score page.** Same stars, correct text, correct colours.
4. **Into gameplay.** No flash of unmasked terrain edges on the first frame.
5. **Gameplay edges.** Top and bottom terrain boundaries still rock-steady — no
   ~8 px pop, no 50 Hz shimmer; HUD sprites stable.
6. **Out of gameplay.** GAME OVER and initials text correct; back on the attract
   screen the stars are correct again.
7. **Repeat the whole cycle at least twice** — nothing should degrade.

---

## 7. Answers

1. **What broke it?** Stage 5A added ECM (`$40`) to `GAMEPLAY_D011_BASE`, which
   `init` ORs into `$D011` to build the *global* boot display state.
2. **Why digit blocks?** ECM masks char codes to 6 bits; star codes 240..251
   became glyphs 48..59, the ROM digits.
3. **Why character-step motion?** The starfield's smooth motion is glyph phase
   (`STAR_CHAR_BASE + size*4 + phase`), not `$D011` fine scroll; the four phase
   glyphs collapsed to `'0','1','2','3'`, leaving only the whole-row `STAR_Y`
   step as visible movement.
4. **Who wrongly owned `$D011`?** `init` (`main.asm:848`), via the shared
   constant. `endGame` was compensating downstream and could not cover boot.
5. **Was ECM leaking across transitions?** It leaked at *boot*; after a game,
   `endGame` did clear it. So the menu was broken from power-on and correct only
   after a completed game — an inconsistency the ownership model now removes.
6. **Fine-scroll bits overwritten?** No — measured `YSCROLL = 3` on the title
   screen as intended. That symptom had the same ECM cause.
7. **Stage-5 raster events active outside gameplay?** No; `endGame` disables the
   raster IRQ and restores `$EA31` (verified).
8. **Ownership model implemented?** Band bit removed from the shared constant into
   `EDGE_MASK_D011_BAND`; established at gameplay entry (`initRasterScheduler`)
   and per frame in `rasterFrameReset`; preserved by `publishRasterPlan`; cleared
   by `endGame`. Non-gameplay states cannot inherit it.
9. **Gameplay masking intact?** Yes — aperture fixed 58..247 on 650 sampled
   frames across five fixtures; all regressions clean.
10. **Starfield restored?** Register-level yes (ECM=0, 16 star codes, YSCROLL=3
    on title/GAME OVER/attract); pixels are for your eyes (§6).
11. **Mask-OFF byte-identical?** Yes — `80d5b0461c070fe2…`, re-verified after
    each edit.
12. **Gameplay regressions safe?** Yes (§5).
13. **What to inspect manually?** §6.
14. **Ready for the historical-hitch investigation?** Yes. The display-state leak
    is contained, so that work will not sit on top of it. It remains untouched
    here, as required.

---

## 8. Files changed (uncommitted)

`src/main.asm` — `GAMEPLAY_D011_BASE` loses ECM; new `EDGE_MASK_D011_BAND`
constant plus the ownership rationale.
`src/raster_scheduler.asm` — band established in `initRasterScheduler` and
`rasterFrameReset`; `publishRasterPlan` preserve rewritten against the new
constant.

No other file touched; the historical six-enemy hitch, the Stage-4F pointer race
and the dense signature were all left alone.
