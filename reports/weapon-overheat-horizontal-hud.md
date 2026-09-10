# 19656 — Weapon Overheat + Horizontal HUD Gauge

**Verdict: GREEN**, with one quantified caveat recorded in §14 and §21.

All four design timings are **exact** at PAL 50 Hz (150 / 50 / 100 / 75 frames),
the horizontal gauge is a 48-pixel bar that tracks heat proportionally, and the
whole mechanic adds **+9 cycles** to the pre-coarse path — i.e. noise — because
everything except reading the lock runs in the HUD phase after coarse admission.

---

## 1. Starting branch / HEAD / worktree

Branch **`main`**, HEAD **`296ae6b`** (*"Two layer HiRes player sprite"*),
worktree **clean** at start — the accepted two-layer hires player work is merged.

| build | SHA-256 |
|---|---|
| pre-change baseline (HEAD, rebuilt out-of-tree) | `git show HEAD:src/main.asm` |
| **shipping (this work)** | `63bc46ed9ba5606f3f0f6c44fd0cc49503c9bf7260d5b6665cd825c8f634e3da` |

Every "before" number below is a real measurement of that baseline build, not a
recollection. Nothing committed or pushed.

## 2. Existing firing / HUD architecture found

**Firing.** `updatePlayerFire` gates on `PLAYER_STATE == ALIVE`, then on
`PLAYER_FIRE_COOLDOWN_TIMER == 0`, then on the joystick fire bit. A volley arms
`PLAYER_FIRE_COOLDOWN_TIMER = PLAYER_FIRE_COOLDOWN (8)` and
`PLAYER_MUZZLE_TIMER = 3`, swaps in the firing bitmap and the red muzzle colour,
then resolves two independent hitscan cannons. **Fire is LEVEL-triggered** — the
button is sampled every frame and re-fires on cadence; there is no edge detect.

**HUD.** Four sprites, hardware slots 4..7, set up at the line-1 IRQ by
`hudBorderSetup` and handed back to gameplay at raster 43 by `hudBorderHandoff`.
`hudBorderSetup` republishes **pointer, colour, X and Y** for all four slots
every frame from the `hudProofPtr / hudProofColour / hudProofX` tables, to both
pointer pages (`$07F8` and `$2BF8`).

The six-digit score owns HUD indices 0/1 (hardware 4/5), double buffered between
`$2f00/$2f40` and `$2f80/$2fc0`, published by rewriting `hudProofPtr` under SEI.

**The opening this work used:** HUD indices **2 and 3** (hardware sprites 6 and
7) were already enabled and handed off every frame but had only ever pointed at
`blankSprite`. That is proven-free display capacity, so the gauge costs **no new
sprite reservation**, no change to the handoff geometry and no gameplay sprite
capacity. Their 64-byte blocks inside `HUD_SPRITE_BASE` are *not* free (the
score's back buffers live there), so the gauge bitmaps took their own space.

**Where HUD work belongs:** `refreshScoreIfDirty` is called from the main loop
**immediately after `prepareBackgroundCoarse`**. That is the established HUD-side
phase, and it is where the gauge went.

## 3. Heat state representation and constants

A single deterministic accumulator, no separate cooldown timers. `HEAT_MAX` is
300, so the accumulator is **16-bit** (`WEAPON_HEAT_LO/HI`); the high byte is
only ever 0 or 1, which the ceiling test exploits.

```asm
.const HEAT_MAX             = 300       // overheat threshold
.const HEAT_REENABLE        = 150       // firing permitted again at/below this
.const HEAT_RISE_PER_FRAME  = 2
.const HEAT_FALL_PER_FRAME  = 3
.const HEAT_FLASH_PERIOD    = 8         // frames per flash half-cycle while locked
```

State: `WEAPON_HEAT_LO/HI`, `WEAPON_OVERHEATED` (the latch),
`HEAT_GAUGE_WIDTH` / `HEAT_GAUGE_SHOWN` (requested vs drawn, the dirty test),
`HEAT_BACKBUF`, `HEAT_FLASH_TIMER`, `HEAT_FLASH_ON`.

All named and centralised in one block so a later upgrade screen can change
capacity, cooling rate or sustained-fire duration without touching the fire code.
**No upgrade machinery was built** — no tables, no indirection, no abstraction
for upgrades that do not exist.

## 4. Exact fire / cooling state machine

```
per frame, in the HUD phase (after prepareBackgroundCoarse):

    if fully cold and not firing:            -> nothing to do (cheap exit)
    else if WEAPON_OVERHEATED:               -> heat -= 3   (locked: always cooling)
    else if PLAYER_FIRE_COOLDOWN_TIMER != 0: -> heat += 2   (the weapon is firing)
    else:                                    -> heat -= 3

    heat saturates at HEAT_MAX -> set WEAPON_OVERHEATED
    heat clamps at 0
    while latched, heat <= HEAT_REENABLE     -> clear WEAPON_OVERHEATED

per frame, pre-coarse, inside updatePlayerFire:

    if WEAPON_OVERHEATED: return             (no fire, no cadence armed, no heat)
```

**"The weapon is firing" is defined as `PLAYER_FIRE_COOLDOWN_TIMER != 0`.** That
timer is only ever armed by a *successful* volley, so heat tracks actual firing
rather than the button: a shot suppressed for any other reason (dead player,
locked weapon) never arms it and therefore never generates heat. This is what the
brief asked for — heat from real weapon use, not from holding the button.

While the lock is latched the cadence branch is skipped entirely, so heat falls
from the *first* locked frame. That is what makes the 1.0 s re-enable and 2.0 s
full-cool exact rather than trailing the last volley's 8-frame cadence.

The unlock compares against `HEAT_REENABLE + 1`, so it fires on the frame heat
**reaches** 150 rather than the frame after — worth one frame of the cooldown.

## 5. Measured timings (VICE, PAL 50 Hz)

Measured, not inferred. `tools/vice_weapon_heat_timing.py` drives the FIRE line
frame by frame and counts physical frames between transitions. Confirmed against
the **shipped binary**:

| # | transition | target | **measured** | |
|---|---|---|---|---|
| 1 | cold → overheat, firing continuously | 150 frames / 3.0 s | **150 / 3.00 s** | ✓ exact |
| 2 | overheat → firing re-enabled | 50 frames / 1.0 s | **50 / 1.00 s** | ✓ exact |
| 3 | overheat → fully cold | 100 frames / 2.0 s | **100 / 2.00 s** | ✓ exact |
| 4 | re-fire from the threshold → overheat | ~75 frames / 1.5 s | **75 / 1.50 s** | ✓ exact |

Supporting values: heat at the lock **300**, gauge width **48/48**; heat at
re-enable **exactly 150**, gauge width **23/48** (still about half full, as
designed); gauge width **0** when fully cold.

**There is no off-by-one to document.** An earlier revision had t1 = 151 because
the accumulator ran before the first volley armed the cadence; moving it into the
HUD phase (§11) removed that, and all four numbers are now the design values
exactly.

Measurement note: player death calls `resetWeaponHeat`, which would silently
restart a measurement. The probe therefore clears the enemy pool each frame (one
fill command) rather than trying to suppress `PLAYER_HIT` at a frame boundary,
which cannot work — capture and consumption both happen inside the frame.
Timings 3 and 4 are also positive proof that **no firing occurs while locked**:
any volley would have added heat and lengthened them beyond 100 and 75.

## 6. Behaviour when FIRE is held through the lockout

**Firing resumes automatically once the lock clears, with FIRE still held.**

That is the behaviour most consistent with the current game: the existing fire
path samples the button level every frame and re-fires on cadence — there is no
edge detection anywhere in `updatePlayerFire`. Requiring a release would have
been a new input semantic.

Proven by `tools/vice_weapon_lockout_check.py`, FIRE held throughout:

| phase | volleys | damage | muzzle frames | heat rise frames |
|---|---|---|---|---|
| **cold**, 60 frames | 7 (60/8 ✓ cadence intact) | **14** (7 × 2 cannons ✓) | 22 (7 × 3 ✓) | rose to 122 |
| **locked**, 40 frames | **0** | **0** | **0** | **0** |
| **after unlock**, 40 frames | 5 | **10** | — | — |

So while locked: no fire, no cadence, no muzzle flash, no damage, no heat — and
the moment the lock clears, firing resumes without touching the stick.

## 7. Horizontal gauge design and pixel dimensions

Two hires sprites side by side on HUD indices 2/3 = **48 pixels** of gauge.

```
cold        [                                                ]
heating     [########################                        ]
maximum     [################################################]   flashing
```

Measured on screen from a live screenshot:

| property | value |
|---|---|
| span | **x 224 … 271 = 48 px** (sprite X 216 and 240) |
| rows | **6** — a hairline rule, 4 fill rows, a hairline rule |
| colour | **one** — light green `(183,255,134)`, the same as the score |
| fill direction | left → right, retreating right → left on cooling |

The two 1-pixel rules bracket the bar so the empty part of the track is clearly
visible without any text. They are **assembled into the bitmaps and never
rewritten**, so a compose only touches the four fill rows. No `OVERHEAT` word was
added — the flash carries that meaning, and the HUD has no label text elsewhere.

**Layout.** The score is left exactly where it was (161..208, centred): its 16 px
font and double buffering are accepted production behaviour and were not
touched. The gauge sits to its right, matching the brief's `000000   [====----]`
sketch:

```
            000000          [========--------]
            ^161..208        ^216..263 (sprite X)
```

Both gauge X values stay below 256, so `HUD_D010_KEEP` remains `$00` and no
`$D010` MSB bit is needed. Note the assembler guard tests the sprite X
**coordinate**, not its right edge — only the coordinate reaches `SPR_X`; the
score's stricter "+24" guard is conservative and the gauge would have failed it
spuriously.

## 8. Heat → width mapping

`width = heatGaugeWidth[heat >> 2]`, a **76-byte table** — a lookup rather than a
divide, because the mapping is `heat × 48 / 300`, which is not a shift. The fill
bytes then come from three **25-byte** tables indexed by the per-sprite width, so
there is no branching and no mask arithmetic per row. **151 bytes of table in
total**, in the CPU-only heat module.

That gives **48 distinct steps** across a three-second burst — about one pixel
every three frames, so the bar visibly creeps rather than jumping in chunks.

Measured, live:

| heat | 0 | 60 | 150 | 240 | 299 | 300 |
|---|---|---|---|---|---|---|
| gauge width | **0** | **8** | **23** | **37** | **47** | **48** |
| lit gauge pixels | 96 | 128 | 188 | 244 | 284 | — |

The lit-pixel deltas above the empty track (96 px of rules) are 32 / 92 / 148 /
188 — exactly `4 rows × width` in every case.

## 9. Flashing

While `WEAPON_OVERHEATED` is latched the gauge colour alternates
**red (2) ↔ black (0)** every `HEAT_FLASH_PERIOD` = 8 frames, i.e. about 3 Hz.
Black is the border colour, so the gauge visibly blinks out — unmistakable, and
it costs **two byte writes**, because `hudBorderSetup` already republishes
`hudProofColour` for every HUD slot each frame. Nothing in the raster
architecture was complicated for colour.

`HEAT_FLASH_ON` is a three-state phase (0 = not flashing, 1 = bright, 2 = dark)
rather than a bare toggle, so "is the flash running at all?" cannot be confused
with "which half are we in". That confusion is not hypothetical: an intermediate
revision used a two-state toggle, `dec` ran on a zero timer, wrapped it to 255
and stalled the flash for five seconds. The three-state form makes it impossible.

Measured while locked: colours seen `{0, 2}` only, run lengths **8, 8, 8, 8**
frames. On re-enable the flash stops and the colour returns to solid **13** —
measured `colours_after_reenable = [13]` — while the gauge stays about half full
and the weapon is usable.

## 10. HUD sprite / layout changes

| | before | after |
|---|---|---|
| `hudProofPtr[2..3]` | `blankSprite`, `blankSprite` | gauge L, gauge R |
| `hudProofX[2..3]` | 0, 0 (parked) | 216, 240 |
| `hudProofColour[2..3]` | 0, 0 | 13, 13 (flash-driven while locked) |
| gauge bitmaps | — | `$2cc0/$2d00` front, `$2d40/$2d80` back |
| score | unchanged | **unchanged** |

The gauge bitmaps are **double buffered on the score's proven publication path**:
compose into the pair the VIC is not fetching, then publish by rewriting
`hudProofPtr` under SEI, which `hudBorderSetup` republishes to both pointer
pages. Buffers are `$80` apart so one index register selects a pair. Nothing new
was invented; the same mechanism, with its own memory.

Score untouched, and proven so: in every gauge screenshot the score measured
**194 lit pixels at x 169..209**, identical at every heat value.

## 11. Composition cost, and where it executes

**This is the part that took three attempts, and the journey is the useful part.**

| revision | where the work ran | pre-coarse cost | representative scroll |
|---|---|---|---|
| v1 | accumulator + width + flash pre-coarse (in `updatePlayerCombatEffects`) | **+130 cycles** | longest 3, 2 deferrals |
| v2 | accumulator pre-coarse, width + flash + compose post-coarse | **+86 cycles** | longest 3–4, 2 deferrals |
| **v3 (shipping)** | **everything post-coarse** | **+9 cycles (noise)** | longest 2, 0–1 deferrals |

v1 and v2 kept the accumulator ahead of `prepareBackgroundCoarse` on the
assumption that the latch had to be set before `updatePlayerFire` in the same
frame, or a ghost volley would escape. **That assumption was wrong**, and seeing
it is what fixed the cost:

```
frame N  pre-coarse : updatePlayerFire fires and arms the cadence
frame N  post-coarse: the accumulator adds the heat and, at the ceiling,
                      sets WEAPON_OVERHEATED
frame N+1 pre-coarse: updatePlayerFire sees the latch and refuses
```

The only thing that must be pre-coarse is **reading** the latch, which is a load
and a branch already inside `updatePlayerFire`. Moving the accumulator into the
HUD phase removed the entire cost *and* removed the one-frame off-by-one from
timing 1 (§5).

Measured, three runs per build, on the representative Level 1 fixture:

| segment | pre | **post** | delta |
|---|---:|---:|---:|
| `updateTurretStream` (contains `updatePlayerCombatEffects`) | 4031 | 4040 | **+9** |
| `buildSortedObjectList` | 566 | 566 | 0 |
| `sortObjectsByY` | 706 | 689 | −17 |
| `buildInitialSpriteSnapshot` | 1097 | 1094 | −3 |
| `buildBatchSpriteSchedule` | 452 | 452 | 0 |
| **whole pre-coarse path** | **7217** | **7226** | **+9** |

Per-frame HUD-phase cost: the accumulator (~60 cycles, with a cheap exit when
fully cold and not firing), the width lookup and flash check (~30), and a compose
+ publish (~180) only on the ~1-frame-in-3 where the drawn width actually
changes — `HEAT_GAUGE_SHOWN` is the dirty test.

## 12. Firing / hitscan integration

The lock check sits at the top of `updatePlayerFire`, after the `PLAYER_STATE`
test and before the cadence test, so a locked weapon arms nothing. Everything
below it — cadence, muzzle timer, firing bitmap, red muzzle colour, both hitscan
cannons — is **completely unmodified**. §6 shows cadence, damage and muzzle
frames all intact when cold, and all zero when locked. Enemy firing was not
touched.

## 13. Death / respawn / lifecycle reset

`resetWeaponHeat` zeroes the accumulator and the latch, stops the flash, restores
the solid colour, draws the cold gauge into **both** buffers and publishes the
front pair. It is called from:

* **`startGame`** — every new game begins cold and unlocked, so no heat or gauge
  pixels can survive GAME OVER → initials → menu → new game;
* **`!beginExplosion`** — player death clears heat and the latch, so the ship
  respawns with a fully cooled weapon and the gauge does not sit hot, or
  flashing, through the explosion.

This is the behaviour the brief preferred. Verified by the lifecycle loop: **5
loops, 80 / 80 checks, 0 failures**, covering death/respawn, GAME OVER →
initials → menu → new game, correct stage origin and 24-bit high-score rendering.

## 14. Representative Level 1 scroll metrics

Same fixture, same input, 2400 frames, **three runs of each build**:

| run | frames/coarse | longest stop | runs ≥ 4 | defer BEAM | defer CUT | histogram |
|---|---|---|---|---|---|---|
| PRE 1 | 16.0 | 2 | 0 | 0 | **0** | `{1:1196, 2:2}` |
| PRE 2 | 16.0 | 2 | 0 | 0 | **0** | `{1:1196, 2:2}` |
| PRE 3 | 16.0 | 2 | 0 | 0 | **0** | `{1:1196, 2:2}` |
| POST 1 | 16.0 | **2** | 0 | 0 | 1 | `{1:1195, 2:3}` |
| POST 2 | 16.0 | **2** | 0 | 0 | **0** | `{1:1196, 2:2}` |
| POST 3 | 16.0 | **3** | 0 | 0 | 1 | `{1:1188, 2:6, 3:1}` |

* **16.0 frames/coarse — the theoretical ideal — in every run.** ✓
* **No stop run ≥ 4 frames in any run.** ✓
* **No coarse-admission cliff** — see §15. ✓

**The caveat, stated plainly:** the baseline is bit-deterministic across runs
(identical histogram three times, zero deferrals). The overheat build is not: two
of three runs match the baseline exactly, one produced a single 3-frame stop, and
1–2 coarse deferrals appear per 2400 frames (≈0.05 %). Since pre-coarse pressure
is now +9 cycles, this is residual *post-coarse frame budget* — the unavoidable
cost of any new per-frame mechanic — not a scheduling regression. A 3-frame stop
is 60 ms against the normal 40 ms cadence; for scale, the problem that started
this whole line of work was a **61-frame** freeze. If bit-exact determinism ever
matters more than gauge resolution, the lever is the ~180-cycle compose: dropping
the fill from four rows to two roughly halves it.

## 15. Coarse-admission timing before / after

| | pre | **post** |
|---|---:|---:|
| gate raster, median | 147 | **147** |
| gate raster, p90 | 175 | **165** |
| whole pre-coarse path, median | 7217 | **7226** |

Median identical, p90 slightly better (within this probe's known variance), and
the deadline is 184. There is no new cliff.

## 16. Score HUD / `$D01C` / pointer publication

| check | result |
|---|---|
| score pixels, every gauge frame | **194 lit px at x 169..209 — identical at every heat value** |
| `$D01C` register check | **0 violations / 120 samples** |
| `$07F8` / `$2BF8` per-frame validation | **0 mismatches** across 4700 captured frames |
| HUD borrow / handoff | intact, unmodified |
| score double buffering | unmodified |

## 17. Player collision and two-layer presentation

| check | result |
|---|---|
| **co-location violations** | **0** over 323 alive frames of fast movement |
| distinct pointer per layer | **323 / 323** (`same_pointer_frames: 0`) |
| layers presented | 2 on 323 / 324 frames (the one is a death frame) |
| `PLAYER_BUNDLE_SHORT` | **0** |
| isolated player false hits | **0 / 200** |
| real enemy / projectile hit | yes / yes |
| lives lost for ONE hit | **exactly 1** |
| death → respawn states | 0 → 1 → 2 → 0 |
| layers forced to share every pixel | **0 false hits**, real hit still detected |

## 18. Stage wrap and aperture

| capture | result |
|---|---|
| stage wrap, 1200 frames | 74 coarse steps, **1 wrap**, all steps single decrements |
| aperture passive | **0 body / 0 lastrow** temporal diffs |
| aperture dense | **0 body / 0 lastrow** temporal diffs |

## 19. Exact PAL / service / sprite-start

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | page A/B | coarse steps |
|---|---|---|---|---|---|---|---|---|
| ordinary | 1400 | **`[19656]`** | **0** | **0** | 8 | 1 | 754/646 | **87** (ideal 87.5) |
| dense *(ref)* | 900 | **`[19656]`** | **0** | **0** | 16 | 4 | 452/448 | — |
| y199 *(ref)* | 400 | **`[19656]`** | **0** | **0** | 9 | 1 | 400/0 | — |
| stage wrap | 1200 | **`[19656]`** | **0** | **0** | 8 | 0 | 605/595 | 74, 1 wrap |
| aperture passive | 400 | **`[19656]`** | **0** | **0** | 8 | 1 | 208/192 | — |
| aperture dense | 400 | **`[19656]`** | **0** | **0** | 16 | 4 | 208/192 | — |

Exact PAL, zero service failures and zero sprite-start misses across all 4700
captured frames. `dense` and `y199` are unchanged from baseline and remain
reference-only. The accepted dense-turret presentation issue was not reopened.

## 20. Build / test artifact cleanup and final disk usage

* **`build/`: 304 KB, 4 files** (`shooter.prg`, `shooter.d64`, `main.vs`,
  `main.sym`) — unchanged in shape, no per-run or per-configuration files.
* **Scratch: 944 KB**, entirely outside the repository.
* **Cleaned**: every emulator capture directory (peak ~70 MB each, deleted
  immediately after analysis by `run_regression_suite.sh`), the out-of-tree
  baseline build, screenshot/lifecycle/visual scratch, the temporary driver
  scripts and `/tmp/shooter-charset.bin`.
* **Retained**: the JSON summaries behind this report's tables — heat timings,
  lockout behaviour, gauge pixels, co-location, the three PRE and three POST
  scroll-stop runs, and the pre/post attribution.
* **No VICE instances left running.** All launched directly via
  `subprocess.Popen` — **never `open -a`** — so nothing stole keyboard focus.

New tools: `tools/vice_weapon_heat_timing.py`,
`tools/vice_weapon_lockout_check.py`, `tools/vice_heat_gauge_visual.py`.
`src/main.asm` is the only source file modified.

## 21. Verdict — GREEN

* mechanic works exactly as designed, all four timings **exact**;
* horizontal gauge fills left→right, 48 px, 48 steps, proportional to heat;
* flashes visibly while locked, stops at the re-enable threshold with the gauge
  still half full and the weapon usable;
* heat comes from **actual firing**, not the button; locked FIRE does nothing at
  all;
* death, respawn and the whole GAME OVER → menu → new game lifecycle reset it;
* score HUD, `$D01C`, pointer publication, collision, two-layer player,
  stage wrap, apertures, exact PAL, service failures and sprite-start misses all
  clean;
* **+9 cycles pre-coarse** — the recovered margin was not spent.

The single deviation from the baseline is in §14: 1–2 coarse deferrals per 2400
frames and, in one run of three, a 3-frame stop instead of 2, where the baseline
is deterministic at zero. Every hard invariant holds and no run produced a stop
≥ 4 frames, so this is GREEN rather than AMBER — but it is a real difference, it
is not hidden, and §14 names the lever if you want it closed.

## 22. Manual playtest checklist

1. **Fire from cold.** Hold FIRE. The gauge should creep steadily left→right and
   fill completely after about **three seconds**.
2. **Overheat.** At full, firing stops dead and the gauge **flashes red/black**
   at about 3 Hz. Confirm no stray shot escapes at the moment it locks.
3. **Keep holding FIRE.** Nothing should fire, and the gauge should keep draining.
4. **Re-enable.** After about **one second** the flashing stops, the gauge is
   about half full — and because FIRE is still held, **firing resumes by itself**.
5. **Short second burst.** That burst should last roughly **1.5 seconds** before
   overheating again — visibly shorter than the first.
6. **Full cool.** Release FIRE at maximum and wait: about **two seconds** to
   empty, and the next burst is a full three seconds again.
7. **Score is untouched.** The six digits should stay rock-steady green
   throughout, including while the gauge flashes.
8. **Death.** Take a hit while hot: the gauge should clear immediately and the
   ship respawn with a cold weapon.
9. **New game.** Lose all lives, go through initials/menu, start again — the
   gauge must start empty with no leftover pixels.
10. **Scrolling.** Play through several five-enemy waves while firing hard; the
    terrain should scroll as smoothly as before.

**Left built and ready on `main`. Not committed, not pushed.**
