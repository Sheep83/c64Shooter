# Four-Turret Cluster Flicker — Visual-Symptom Forensics

**Verdict: AMBER.**

A real, count-scaling, top-and-bottom-edge presentation defect was found and
repaired: **turrets whose body is drawn but whose 16-pixel sprite box straddles
the aperture edge received no colour at all and rendered in flat terrain colour.**
Machine-detected dropouts fall from **138 frames to 4** on the passive cluster,
and from 96 → 2 on a two-turret variant.

It is AMBER and not GREEN for two honest reasons:

1. I could **not** capture the user's percept in rendered pixels. My background
   pixel detector was defeated by sprite motion, so the correlation to the visible
   symptom is by mechanism and timing, not by a captured image.
2. The **2→3 turret threshold is disproven, not explained.** Two cluster turrets
   already produce 24-frame dropout runs. Turret count scales the *rate*, not a
   threshold — so "starts at the third turret" is a density/noticeability effect,
   not a resource limit.

The user's retest is the decisive evidence.

Branch `main`, HEAD `d60828a`. Nothing committed, staged, tagged or pushed.

---

## 1. The previous GREEN was wrong, and so was my fixture

Two fixture errors invalidated the earlier investigation, both mine:

**(a) My "passive" captures were firing continuously.** `vst_hitch.py` holds the
joystick fire bit down every frame (`jpdb 1 {255 ^ (16 | direction)}`, bit 4 =
fire). Turrets were being shot and destroyed throughout — health 3→2→1→0 in ~8
frame steps — so every earlier capture was contaminated by dead turrets and by
the page-blind dead-turret restore path. That is the opposite of the user's
scenario. A genuinely passive runner (`run_passive.sh` / `vst_passive.py`) now
holds `jpdb 1 ff` for the whole run: **alive=1624, dead=0**.

**(b) My passive captures used the mask-OFF build.** The user runs the mask-ON
default. Re-run with the real default build.

Both had to be fixed before any measurement meant anything.

---

## 2. What the defect is

`positionBackgroundTurrets` sets `TURRET_VISIBLE` only when
`72 <= TURRET_Y < 232` — and says so: *"Combat only while the full 16-pixel body
is visible."* It is a **combat** predicate.

`pulseTurretColour` used it as a **presentation** predicate:

```asm
    lda TURRET_VISIBLE,x
    beq !restoreOnly+        // -> paint row 0 -> colour cells restored to terrain
```

But the glyph writers — `installTurretRow` and `ssReconcileTurretSlot` — gate only
on `TURRET_SLOT_AUTH` and `TURRET_HEALTH`. So a turret straddling the top or
bottom aperture edge **is drawn but not coloured**, and renders in flat terrain
colour until its whole 16-pixel body is inside.

Measured dropouts by `(rel, TURRET_VISIBLE)` on the passive cluster:

```
 (0, 0): 36    turret entering at the TOP  (matrix rows 1-2)
(21, 0): 45    turret leaving at the BOTTOM
(22, 0): 27
(23, 0): 30
```

`rel == 0` is precisely the top of the aperture — matching "top-row flicker".

### Why it looks worse with more turrets

Each turret contributes a dropout at entry and again at exit. With more turrets in
the aperture the events overlap, so *something* is uncoloured for a much larger
fraction of the time:

| turrets in aperture | dropout runs observed |
|---|---|
| 1 | isolated 9-frame runs |
| 2 | isolated 9-frame runs, plus 24-frame runs |
| 3 | repeated 24-frame runs (416–439, 448–471, 544–567, 576–590) |

That is a density effect. **There is no 3-turret resource, scratch or loop
threshold** — see §4.

---

## 3. Hypotheses tested and rejected

I checked and discarded several before landing on the above. Recording them so
they are not re-investigated:

| hypothesis | result |
|---|---|
| `cramRowLo/Hi` (26 entries) indexed out of range | **rejected** — max `TURRET_CRAM_ROW` observed 14; 0 out-of-range samples |
| Colour RAM incoherent with the glyphs (not double-buffered) | **rejected** — 0 incoherent frames once the live pulse colour is used |
| Shared turret charset republished mid-frame | **rejected** — 0 charset byte changes across 700 frames |
| Stage-5 mask arriving late under turret load | **rejected** — `EDGE_MASK_LATE = 0`, `EDGE_MASK_FALLBACK = 0` |
| Aperture shifting during the cluster | **rejected** — 58..247 on all 580 frames sampled |
| Screen-matrix turret placement wrong | **rejected** — the rel==-1/-2 oracle stays 0 |

**A false positive I nearly reported:** `TERRAIN_COLOUR_RAM = 8|1 = 9` and pulse
phase 0 is `1|8 = 9` — *identical*. One of the four pulse phases legitimately
renders the turret in exactly the terrain colour, so a naive "cell is terrain
colour ⇒ missing" oracle flags 8 frames out of every 32 on every turret. The
working oracle reads the live `TURRET_PULSE_COLOUR` and only judges frames where
the pulse is 10 or 15. Excluding phase 0 *without* that refinement then hides the
genuine dropouts, because an unpainted cell is also colour 9 — the blind spot that
let this defect survive the previous investigation.

---

## 4. Selective-removal A/B (§9)

Diagnostic builds with the cluster trimmed (stage authoring untouched; variant
trees only), same seed, same passive fixture, 700 frames:

| cluster | before fix | after fix |
|---|---|---|
| 345 + 337 (2 turrets) | **96** dropout frames, runs up to 24f | **2** (single-frame) |
| 345 + 337 + 329 (3) | **129** dropout frames, runs up to 24f | **3** (single-frame) |
| all four (4) | **138** dropout frames, runs up to 24f | **4** (single-frame) |

**Two turrets already produce the long runs.** No specific turret or world row is
necessary. This disproves a 2→3 threshold: the count scales the event rate
(96 → 129 → 138), and perception of "it starts at the third" follows from
overlap density, not from a mechanism that engages at three.

---

## 5. The fix

`src/background_turrets.asm`, three small edits. Reverting exactly these
reproduces the pre-fix binary `3f398975ba6a5ba7` bit for bit.

1. New per-slot array `TURRET_PAINT_ROW` — the **presentation** row (`rel + 1`,
   the matrix row the glyph writers use), or 0 when no body row is on the aperture.
2. `positionBackgroundTurrets` sets it for `rel` 0..23 (it already has `rel`), and
   keeps the combat/sprite-Y projection gated at `rel` 0..22 as before.
3. `pulseTurretColour` gates on `TURRET_PAINT_ROW` instead of `TURRET_VISIBLE`,
   and uses it directly rather than re-deriving the row from `TURRET_Y` — so
   colour follows the glyphs by construction.

Net effect on cycles is slightly negative (the `TURRET_Y` shift/add chain is
replaced by one load); nothing was added to any raster-critical path.

**Residual:** 2–4 single-frame dropouts remain, all at `rel == 0`, one per turret
entry. That is a one-frame ordering transient — the glyph is published at the
coarse flip while the colour is painted at the next frame top. 1 frame in 700 per
entry (20 ms); not chased.

**Build-guard note:** `TURRET_PAINT_ROW` brings the per-slot state block to
**exactly 128 bytes**, the limit enforced by `.if (TURRET_STATE_END -
TURRET_STATE_BEGIN > 128)`. Any further per-slot array will trip that guard and
require the signed-X clear loop to be revisited.

---

## 6. Regression

Fixed default build `58e9d59131e4791b`.

| fixture | frame deltas | svc fail | sprite-start miss | catchups | replay |
|---|---|---|---|---|---|
| idle 300 | `[19656]` | 0 | 0 | 0 | 0 |
| wave 320 (seed 382) | `[19656]` | 0 | 0 | 1 | 4 |
| wrap 340 (seed 12) | `[19656]` | 3 † | 0 | 2 | 5 |
| y199 400 | `[19656]` | 0 | 0 | 0 | 0 |
| dense 200 | `[19656]` | 0 | **0** | 1386 | 100 |
| turret 500 | `[19656]` | 0 | 0 | 0 | 0 |
| stress 500 | `[19656]` | 0 | 0 | 0 | 0 |

† the pre-existing page-B `$2BF8` pointer race, untouched.

- **Phase B(b) intact**: 19 fallback attempts = 11 page-A + 8 page-B + **0
  refusals**; 0 seven-pixel snaps, 0 duplicated turrets, max visual stall 2 frames.
- **rel==-1/-2 correction intact**: row-0/row-1 turret oracle **0** on all seeds.
- Stage-5: aperture **58..247 on 130/130** for wave, wrap, dense, turret, stress;
  `EDGE_MASK_LATE = 0`, `EDGE_MASK_FALLBACK = 0`.

---

## 7. Answers to the final questions

1. **Reproduced the four-turret cluster window?** Yes — seed 350, 700 frames,
   truly passive, reaching 3 turrets in the aperture from frame ~350 and 4
   occupied slots by ~475.
2. **First anomalous frame relative to turret #3?** Turret #3 (row 329) enters at
   frame ~350; the first long (24-frame) dropout run in that window starts at
   frame 416. Isolated 9-frame runs occur earlier, from frame 79, with one turret.
3. **Last anomalous frame?** 590 in the 3-turret window; further isolated runs at
   672–695 once the count falls back to 2.
4. **Requires three turrets?** **No** — disproven. Two produce 24-frame runs.
5. **Which removal fixtures reproduce it?** All of them (2, 3 and 4 turret
   variants). No specific turret is necessary.
6. **A specific world row necessary?** No.
7. **Which "turret count" correlates?** None as a threshold. The number of
   *drawn* turrets scales the dropout **rate** (96 → 129 → 138 frames for 2 → 3 → 4).
8. **What does the rendered top strip do on bad frames?** Not captured — see the
   AMBER caveat. The matrix and colour dumps say the turret is drawn in flat
   terrain colour instead of its pulse colour.
9. **Screen RAM bytes wrong?** No — glyphs are correct.
10. **Colour RAM bytes wrong?** Yes — the turret's four cells hold
    `TERRAIN_COLOUR_RAM` while the pulse is 10 or 15.
11. **`$D011/$D018`/mask wrong?** No — aperture fixed, mask never late.
12. **Alternates with page A/B?** No — colour RAM is single-buffered and the
    defect is page-independent.
13. **Badline / raster deadline?** No — no timing threshold found.
14. **First incorrect operation?** `pulseTurretColour`'s `lda TURRET_VISIBLE,x /
    beq !restoreOnly+` — a combat predicate used as a presentation predicate.
15. **Last writer of the bad cells?** `paintTurretCells` writing
    `TERRAIN_COLOUR_RAM` via the `!restoreOnly` path.
16. **Was the rel==-1/-2 fix still correct?** Yes — kept, and its oracle stays 0.
17. **Why did the previous oracle miss it?** It checked *character codes* only,
    never colour; and my captures were firing, so turrets were dying.
18. **A genuine 3+ turret resource/scratch/loop threshold?** **No.** Audited pool
    size, per-slot arrays, `cramRow` bounds, shared scratch and the charset — all
    clean.
19. **Repair?** §5.
20. **Cluster now produces zero anomalies?** Near-zero: 138 → 4 single frames.
21. **Removal fixtures consistent?** Yes — 96 → 2 and 129 → 3.
22. **Three passive wraps clean?** Wrap fixture clean; the earlier three
    wrap-crossing captures remain clean under the rel oracle.
23. **Phase B(b) intact?** Yes.
24. **Stage-5 / HUD / starfield intact?** Yes.
25. **PAL and mux safe?** Yes — `[19656]` everywhere, 0 sprite-start misses,
    `--dense` catchups/replay identical to baseline.
26. **Manual inspection?** §8.
27. **Ready to close?** **Not yet** — pending the user's retest.

---

## 8. What to test manually

Exactly the known reproduction:

1. start the game, **touch no controls**
2. watch the 345 / 337 / 329 / 321 cluster
3. watch the moment turret #3 appears
4. continue through turret #4 and for several seconds after
5. repeat over at least three passes

What should now be different: **turrets should carry their pulsing colour the
whole time they are on screen**, including while entering at the top edge and
leaving at the bottom. Previously they rendered in flat terrain colour until the
full body was inside, and again as they left.

Note the turret pulse legitimately cycles white → red → yellow → red every 8
frames, and its white phase is the same colour as the terrain highlight, so a
turret does momentarily flatten in colour by design. If what you are seeing is
that pulse, it is intended behaviour and we should change the pulse table rather
than the scroller.

If flicker persists, the most useful thing you can give me is *which* of these it
looks like: (a) the turret briefly losing its colour, (b) terrain characters
changing shape, (c) the whole top band jumping or blanking. Those point at three
different subsystems and would let me target the next capture.

---

## 9. Reproduction

```
scratchpad/run_passive.sh <name> <port> <prg> <vs> --seed-scroll 350 --frames 700
```

`run_passive.sh` / `vst_passive.py` differ from the hitch runner only in holding
`jpdb 1 ff` (no fire, no movement) for the whole capture — **use these for any
passive-symptom work**; the standard runner fires continuously.

Oracle (`/tmp/cram4.py` pattern): for each alive turret with `rel` in 0..23, find
the matrix rows carrying its body glyphs on the active page; if every one of those
cells holds `TERRAIN_COLOUR_RAM` while `TURRET_PULSE_COLOUR` is 10 or 15, the
turret is drawn but uncoloured. Frames where the pulse itself is colour 9 are
skipped as indistinguishable.
