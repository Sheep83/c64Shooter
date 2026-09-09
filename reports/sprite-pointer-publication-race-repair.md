# Sprite Pointer Publication Race — Forensics and Bounded Repair

## 1. Verdict

**GREEN at the machine level. Visible-flicker confirmation is pending your manual test.**

**Two** distinct pointer-publication races were found — not one — both proven from
captured ordering, both repaired. Afterwards, across every fixture:

- **0 pointer-oracle failures** (was 3 on wrap, plus systematic staleness);
- **0 A/B divergence on any page-flip frame** (was 3–7 per capture);
- **0 player (slot 0) divergence** on 1,050 frames including combat;
- `svcFail = 0` on **all seven** regression fixtures — the wrap fixture's
  long-standing 3 service failures are now gone;
- exact PAL `[19656]`, **0 sprite-start misses**, `--dense` timing unchanged.

The mirror now provably runs before the first LIVE assignment on **every frame**
(0 violations; latest mirror raster 36, previously up to 66).

Branch `main`, HEAD `d60828a`. Nothing committed, staged, tagged or pushed.

---

## 2. Current pointer-publication architecture (reconstructed from source)

Per gameplay frame, in order:

| raster | actor | writes |
|---|---|---|
| ~2 | `hudBorderSetup` | HUD pointers → `$07F8` slots 4–7 (+ `$2BF8` **only if page B displayed**) |
| ~12 | `renderSprites` | this frame's entire initial plan → `$07F8` (always, both pages) |
| ~23 | `armFirstBatch` | arms the sprite raster IRQ |
| ~23 | `finishBackgroundCoarse` → tail `ssFlipMirrorPtrs` | `$07F8` → `$2BF8`, **unconditionally A→B** |
| ~45 | `hudBorderHandoff` | reclaimed gameplay pointers → `$07F8` (+ `$2BF8` **only if page B displayed**) |
| during frame | `ssBatchPtrStore` (LIVE batch) | **only the ACTIVE page's table** — the store's high byte is self-modified to `$07`/`$2B` once per `$D018` flip (zero per-assignment cost) |

Two consequences follow directly, and both are defects:

- `renderSprites` writes only `$07F8`, so the **A→B mirror is the mechanism that
  publishes the frame's initial plan to page B**. It cannot simply be reversed or
  removed.
- The mirror is a *sample* of `$07F8` at one instant. Anything that makes `$07F8`
  correct only *after* that instant never reaches page B while page A is displayed.

---

## 3. Phase A — race #1 proven: HUD reclaim never reaches page B

`hudBorderSetup` (raster 2) runs **before** the mirror (raster 23);
`hudBorderHandoff` (raster 45) runs **after** it. Both gated their page-B write on
`SS_PAGEB_ACTIVE` — "write page B only while it is displayed".

So while page A was displayed, `$2BF8` captured the **HUD-era** pointers from
setup and **never** the gameplay pointers from handoff. Page B sat stale until it
was flipped in.

### Exact failing chain — wrap fixture, seed 12

```
frm 80 page=0 | render@12 pres@23 mirror@24 hudSetup@2 hudHandoff@45 reclaim@47,48
        $07F8 = [152,152,151,153, 154,155,144, 191]      <- gameplay (handoff)
        $2BF8 = [152,152,151,153, 188,189,190, 191]      <- HUD-era  (stale)
frm 81 page=0 |  ... same divergence ...
frm 82 page=1 | flip@23  <-- page B becomes ACTIVE carrying the stale HUD pointers
        $07F8 = [152,152,151,153, 154,144,155, 191]
        $2BF8 = [152,152,151,153, 188,189,190, 191]      <- WHAT THE VIC READ
frm 83 page=1 | both tables agree again                  <- defect lasts ONE frame
```

Oracle record for that frame:

```
[82, 'final sprite pointers', 'page B $2BF8',
     hardware [152,193,151,153, 188,189,190],
     expected [152,193,151,153, 194,144,155]]
```

- **frame** 82 (and 147); **slots** 4, 5, 6; **expected** 154/144/155;
  **actual** 188/189/190; **source** HUD pointers installed at raster 2 and
  mirrored at raster 23; **page** B, becoming active at raster 23.
- Effect: for one frame after every A→B flip, each HUD-reclaimed hardware slot
  displays the **HUD sprite image** instead of its gameplay sprite — a one-frame
  wrong-sprite flash, i.e. a flicker.

Scale of the underlying staleness before repair (frames where `$07F8 != $2BF8`):

| fixture | frames A≠B | on a flip frame | slots affected |
|---|---|---|---|
| seed 12 | 75 / 400 | 4 | 4,5,6 (page A active) |
| seed 352 | 58 / 400 | 4 | 4,5,6,7 |
| y199 | **199 / 400** | 7 | 4,5,6,7 |
| dense | **127 / 250** | 3 | 4,5,6,7 |

---

## 4. Phase A — race #2 proven: the original 4F mirror-after-batch race

Repairing race #1 removed 2 of the wrap fixture's 3 pointer failures. Frame 88
survived — and it is the **separate** race documented (unfixed) in the Fable
review:

```
[88, 'final sprite pointers', 'page B $2BF8',
     hardware [193,153,152,155,153,151, 194, 144],
     expected [193,153,152,155,153,151, 155, 144]]
```

- **slot 6**, expected 155 (a LIVE batch value), actual 194 (the `renderSprites`
  plan value from `$07F8`).

Mechanism: with page B active, `ssBatchPtrStore` writes **only** `$2BF8`, so
`$07F8` keeps the frame-top plan. The mirror ran at the tail of
`finishBackgroundCoarse` — **after** `armFirstBatch`. On a late main-thread frame
the IRQ therefore fired first, published the correct pointer to `$2BF8`, and the
mirror then stamped the stale `$07F8` plan back over it.

Direct evidence of the late-frame condition, same fixture:

```
frm 86  mirror@31
frm 87  mirror@31
frm 88  mirror@66     <-- main thread late; mirror well past the first batch window
frm 89  mirror@24
```

---

## 5. Relationship to sprite 0 (player)

Both races are **slot-agnostic**. Race #1 hits whichever slots the HUD reclaims
(measured: 4–7). Race #2 hits whichever slot a LIVE batch reassigns (measured:
slot 6). The player occupies whatever hardware slot the multiplexer assigns it, so
**sprite 0 is exposed to both**, and `PLAYER_HW_MASK` confirms the player is
regularly a deferred/reclaimed slot. Nothing about either race excludes the player.

Post-fix, slot 0 divergence is **0/400, 0/400, 0/250** frames across passive,
combat and dense fixtures.

---

## 6. Relationship to player-hit frames — correlation only

You saw one flicker near an enemy-bullet hit. **I did not treat that as causal and
found no evidence that it is.**

I did not need a dedicated collision investigation: the combat fixture
(`--hold-fire`, seed 12, 400 frames) exercises player hits and shows **0 pointer
failures and 0 player divergence** after the repair, and showed the same class of
failures as the passive fixtures before it. The races are driven by *flip timing*
and *main-thread lateness*, not by hit state. A hit merely changes the player's
sprite image, which makes a wrong pointer easier to notice — a plausible reason
the flicker caught your eye there without the hit causing it.

No collision or bullet logic was inspected or changed.

---

## 7. Repairs chosen, and why

**Repair 1 — unconditional HUD page-B write** (`hudBorderSetup`, `hudBorderHandoff`).
Removed the `bit SS_PAGEB_ACTIVE / bpl` gate so both write `$2BF8` always. Page B
is not fetched by the VIC while inactive, so the store is always safe. Chosen over
re-mirroring because it fixes the value at its source and needs no new state.

**Repair 2 — move the per-frame mirror ahead of `armFirstBatch`.**
`ssFlipMirrorPtrs` moved from the tail of `finishBackgroundCoarse` to the entry of
`armFirstBatch`. The task asked for proof that all source values are valid at the
earlier point: `renderSprites` is the immediately preceding call in both present
chains and writes the frame's entire initial plan to `$07F8`, so the source is
complete; and because the IRQ is not yet armed, no LIVE batch can have written
`$2BF8` yet. The row shifts in `finishBackgroundCoarse` never reach
`$07E8-$07FF`, so nothing was lost by moving it.

Chosen over "re-mirror the affected slots afterwards" because it removes the race
by construction rather than repairing its damage, and costs nothing extra.

**Memory placement:** the repair pushed the main code block to `$1f01`, past the
`$1f00` lookup tables. Those are alignment-free read-only tables with 101 bytes of
slack above, so their origin moved to `ENGINE_LOOKUP_SEGMENT = $1f20`
(block now `$1f20-$1f7a`, still far below the `$1fc0` border-marker sprite).

---

## 8. Cycle / timing impact

| site | before | after | delta |
|---|---|---|---|
| `hudBorderSetup` / `hudBorderHandoff`, page B active | `bit`(4) + `bpl`(3) + `sta abs,x`(5) = 12 | `sta abs,x`(5) | **−7 per slot** |
| same, page A active | `bit`(4) + `bpl`(2) = 6 | `sta abs,x`(5) | **−1 per slot** |
| mirror relocation | ~50 cy at raster ~23 | ~50 cy at raster ~12–20 | **0** |

Both repairs are **cheaper than the code they replace**, and neither is in the
LIVE batch hot path — `ssBatchPtrStore` is untouched and still costs zero per
assignment. Measured effect on the tightest fixture: `--dense` catchups/replay
`1386/100`, **identical** to baseline.

---

## 9. Post-fix pointer oracle, all eight slots and both pages

| fixture | exact PAL | svcFail | pointer failures | sprite-start misses | frames A≠B | on flip frame |
|---|---|---|---|---|---|---|
| seed 12 (passive) | `[19656]` | 0 | **0** | 0 | 2 | **0** |
| seed 352 (passive) | `[19656]` | 0 | **0** | 0 | 2 | **0** |
| seed 12 (**combat**, `--hold-fire`) | `[19656]` | 0 | **0** | 0 | 2 | **0** |
| dense | `[19656]` | 0 | **0** | 0 | **0** | **0** |
| y199 | `[19656]` | 0 | **0** | 0 | **0** | **0** |

The residual 2 frames are `slot6` while **page B is active** with `$07F8` lagging.
That direction is correct by design: the VIC reads `$2BF8`, which holds the live
batch value, and `$07F8` is the inactive table. The authoritative oracle — the
active page's final table versus the accumulated LIVE assignments — is **0
failures**.

Structural proof, combat fixture, 400 frames:

```
frames where ssFlipMirrorPtrs ran AFTER the first LIVE assignment : 0
latest mirror raster observed                                     : 36   (was 66)
```

---

## 10. Regression

Final build `f1d08a0f5d2337ee` (mask ON, default). Mask-OFF builds clean
(`66d2fa9295e858ac`).

| fixture | deltas | svcFail | ptrFail | sprite-start miss | catchups | replay |
|---|---|---|---|---|---|---|
| idle 300 | `[19656]` | 0 | 0 | 0 | 0 | 0 |
| wave 320 (seed 382) | `[19656]` | 0 | 0 | 0 | 1 | 3 |
| wrap 340 (seed 12) | `[19656]` | **0** | 0 | 0 | 2 | 5 |
| y199 400 | `[19656]` | 0 | 0 | 0 | 0 | 0 |
| dense 200 | `[19656]` | 0 | 0 | **0** | 1386 | 100 |
| turret 500 | `[19656]` | 0 | 0 | 0 | 0 | 0 |
| stress 500 | `[19656]` | 0 | 0 | 0 | 1 | 0 |

The wrap fixture previously carried **3** service failures — described in earlier
reports as "pre-existing, untouched". They were this race, and they are gone.

Everything else intact:

- **Phase B(b)**: 13 fallback attempts = 8 page-A + 5 page-B + **0 refusals**;
  0 seven-pixel snaps, 0 duplicated turrets, max visual stall 2 frames.
- **rel == −1/−2 turret correction**: row-0/row-1 oracle **0** on all three seeds.
- **Turret colour-presentation correction**: unchanged.
- **Stage 5**: aperture **58..247 on 130/130** for wave, wrap, dense, turret, stress.

---

## 11. Remaining known sprite/presentation risks

1. **`ssPublishCoarseFlip`'s own mirror still runs after `armFirstBatch`.** It is
   needed there (it must precede the `$D018` write), and it is harmless for an
   A→B flip because page B is not yet displayed. For a B→A flip it briefly
   overwrites the live page-B table in the ~700 cycles before `$D018` switches
   away from B. No oracle failure was observed from it in any fixture; recording
   it as the one remaining ordering asymmetry.
2. **Mode B (`OPT_SS_ALLOW_PENDING_LIVE_FLIP` off)** still has the equivalent
   HUD gate, keyed on `BG_ACTIVE_PAGE` instead of `SS_PAGEB_ACTIVE`. Same latent
   flaw, but that path is not compiled in the default build; left alone to keep
   this change bounded.
3. `$07F8` legitimately lags while page B is active. Anything new that reads
   `$07F8` as "the live pointer table" would be wrong — it is only live when
   page A is displayed.

---

## 12. Manual test plan

Please watch specifically:

1. **The player, continuously, during ordinary gameplay.** This is the primary
   check — the flash was one frame per flip, so watch for a brief wrong-shape
   blink rather than a sustained artefact.
2. **Around page flips / stage wrap.** Flips happen roughly every 16 frames; the
   wrap sequence was the fixture that reproduced this most strongly.
3. **Dense enemy waves**, where more slots are multiplexed and reclaimed.
4. **Player bullet-hit / invulnerability events** — the case where you first
   noticed it. Note whether a flicker still coincides with hits specifically.
5. **Enemy sprites during the same intervals**, since the race was never
   player-specific — slots 4–7 were the measured victims.

I am not claiming the visible flicker is solved. The machine-level races are
proven gone; whether that was what you saw is your call.

---

## 13. Harness note

`vst_passive.py` / `run_passive.sh` gained a per-frame VIC register dump
(`$D000-$D02F`) and now takes `--hold-fire` as an **explicit opt-in** for combat
fixtures; the default is genuinely passive. Both combat and passive variants of
the wrap fixture were used here and agree.
