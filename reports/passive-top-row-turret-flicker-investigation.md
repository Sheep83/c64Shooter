# Passive Top-Row Turret Flicker — Forensic Investigation and Repair

**Verdict: GREEN.** Reproduced deterministically with no player input and no
turret destruction, root cause proven, bounded repair implemented. The row-0/row-1
turret oracle goes from **45–137 wrong cells per capture to exactly 0** on every
seed tested, including a 4-turret cluster and three stage wraps. Phase B(b) is
intact and every regression fixture is clean.

Branch `main`, HEAD `d60828a`. Nothing committed, staged, tagged or pushed.

---

## 1. Root cause — a one-row error in `ssReconcileTurretSlot`

The authoritative world-row mapping is set by `renderStageRowToScreen`:

```
BG_LOGICAL_ROW = SCROLL_ROW + BG_DEST_ROW - 1
```

so **matrix row `m` holds world row `SCROLL_ROW + m - 1`**, and a turret's top
body belongs at matrix row `rel + 1` where `rel = (T - SCROLL_ROW) mod SLR`.
`ssReconcileTurretSlot` uses exactly that for `rel` in 0..23.

But for a turret arriving at the top of the aperture it took a different branch:

```asm
!relHi:
    lda TURRET_REL_LO      // only rel == SLR-1 lands a body row on the new page
    cmp #<(STAGE_LOGICAL_ROWS - 1)
    ...
!aboveTop:
    lda #$ff               // top matrix row = -1 (above aperture); bottom = 0
    sta TURRET_CELL_ROW
```

`rel == SLR-1` is `rel == -1`, so by the routine's own formula the top body row is
`rel + 1 = 0` — **not** `-1`. The branch was one row too high, with two consequences:

1. **Matrix row 0 received the BOTTOM glyph pair (228,229) where the TOP pair
   (226,227) belongs.**
2. **Matrix row 1 — the first fully visible aperture row — was left as bare
   terrain**, because the bottom body was consumed by row 0.

Both persisted for a full coarse cycle (16 frames) as each turret scrolled in.

A second, related gap: `rel == SLR-2` (`rel == -2`, top genuinely above the
aperture, bottom legitimately at row 0) was **not handled at all**, so row 0 was
left as terrain in that case too.

### Why it looked like flicker at the top edge

The legacy/render path (`installTurretRow`) drives off `BG_LOGICAL_ROW` and always
got this right. The flip path (`ssReconcileTurretsOnNewPage`) did not. **The two
publication paths disagreed**, so the glyph at the top edge changed depending on
which path published that coarse step — a turret fragment appearing, changing and
snapping into place as it entered.

Row 0 spans rasters `48+YSCROLL .. 55+YSCROLL` and the Stage-5 aperture opens at
58, so the bottom sliver of row 0 is visible whenever `YSCROLL >= 3` — a thin band
at the very top. Row 1 is fully visible.

---

## 2. Why three turrets, and why ~128 frames

The authored turret rows are `345, 337, 329, 321, 225, 217, 117, 109, 25, 5`.
Consecutive gaps: `8, 8, 8, 96, 8, 100, 8, 84, 20`.

The dominant spacing is **8 world rows**, and one coarse step is 16 physical
frames (`SCROLL_FRAME_DIVIDER = 2`, 8 fine steps), so:

> **8 world rows × 16 frames = exactly 128 frames between turret entry events.**

That is the ~128-frame periodicity Phase B(b) observed and could not explain. The
rows also cluster — `345/337/329/321` is four turrets 8 rows apart — so while a
cluster scrolls through, three to four turrets are in view at once and an entry
event fires every 128 frames. That is precisely the user's "around three turrets"
observation, and it falls out of the stage authoring, not out of turret count
having any direct effect on the mechanism.

The defect is **per entry event**, at roughly **40 wrong cell-samples per entry**
(two rows × ~16 frames + transition). More turrets in view ⇒ more entries per unit
time ⇒ more frequent flicker.

---

## 3. Evidence

Oracle: from the authoritative mapping, matrix row `m` must contain the top pair
iff `world(m) == T` and the bottom pair iff `world(m) == T+1`. Checked for rows 0
and 1, every live turret, every frame. Pre-flip frames (`SS_FLIP_ADMIT` incremented
— `SCROLL_ROW` already decremented but `$D018` not yet flipped) are excluded as a
known sampling transient.

All captures are **passive**: the harness presses fire once to start and provides
no further input. No turret is destroyed.

| seed | turrets in view (max/mean) | entry events | coarse steps | cells checked | **wrong BEFORE** | **wrong AFTER** |
|---|---|---|---|---|---|---|
| 352 | 3 / 1.29 | 3 | 26 | 184 | **122** | **0** |
| 360 | 2 / 0.68 | 2 | 26 | 122 | **107** | **0** |
| 340 | 2 / 1.34 | 3 | 25 | 188 | **90** | **0** |
| 232 | 2 / 1.31 | 2 | 26 | 124 | **77** | **0** |
| 124 | 1 / 0.79 | 2 | 25 | 124 | **77** | **0** |
| 112 | 2 / 1.11 | 1 | 26 | 60 | **45** | **0** |
| 224 | 2 / 1.69 | 1 | 26 | 60 | **45** | **0** |
| cluster (seed 350, 700 frames, rows 345/337/329/321) | 2 / 1.04 | 4 | 43 | 245 | **137** | **0** |

Wrong-cell count tracks **entry events**, not raw turret count: 1 entry → 45,
2 entries → 77–107, 3 entries → 90–122, 4 entries → 137.

### Ground truth that proved the disagreement

Slot 6, col 25, `T = 337`, passive, seed 352 — glyph rows on each page:

```
frm pg    S  rel | pageA rows | pageB rows
226  1  338  419 |     -      |     -
227  0  338  419 |    0:b     |     -        <- flip published page A: BOTTOM at row 0
...                                             row 1 left as bare terrain
243  1  337    0 |    0:b     |  1:T,2:b     <- next step is correct (rel+1 path)
```

versus the same condition published by the legacy path (slot 7, frames 95–111):
row 0 held **(226,227) — the top pair** — because `installTurretRow` computed it
from `BG_LOGICAL_ROW`. Two paths, two answers.

### Data wrong, not written late

A VICE store watchpoint on the row-0 turret cell (`$0419`) showed the only writer
in the window was `ssInstallInactiveRow0+22`, always with terrain codes and always
early. The turret glyph arrives from `ssReconcileTurretsOnNewPage` at flip publish
time, well before the fetch. **This is a wrong-data defect, not a late-write
defect** — the opposite of the mechanism Phase B(b) fixed.

### Stage wrap

Three separate wrap crossings (seeds 12, 8, 4; `SCROLL_ROW` reaches 0 and wraps to
419 in each): **32 / 45 / 0 wrong before → 0 / 0 / 0 after.** The wrap itself is
not implicated; turret entries near it were failing for the ordinary reason.

### Stage-5 mask is incidental, not causal

Same seed, mask ON vs OFF, identical defect counts **122 before / 0 after in both**.
The mask changes only how much of the row-0 sliver is visible; it neither causes
nor hides the underlying matrix error.

---

## 4. The fix

`ssReconcileTurretSlot`, the `!relHi` branch only. Nine lines of logic, no new
state, no timing change, nothing in any hot path:

```asm
    // rel == SLR-1 (rel == -1): top matrix row 0,  bottom row 1
    // rel == SLR-2 (rel == -2): top above aperture, bottom row 0
    lda TURRET_REL_HI
    cmp #>(STAGE_LOGICAL_ROWS - 1)
    bne !noBodyRow+
    lda TURRET_REL_LO
    cmp #<(STAGE_LOGICAL_ROWS - 1)
    bne !tryAboveTop+
    lda #0                      // rel == -1: top body IS matrix row 0
    sta TURRET_CELL_ROW
    jmp !haveTop+
!tryAboveTop:
    cmp #<(STAGE_LOGICAL_ROWS - 2)
    bne !noBodyRow+
    lda #$ff                    // rel == -2: top above aperture; bottom = row 0
    sta TURRET_CELL_ROW
    jmp !haveTop+
!noBodyRow:
    rts
```

`SLR = 420 = $01A4`, so `SLR-1` and `SLR-2` share a high byte of 1 and the low
compare separates them. The existing `$ff` handling downstream (`$ff + 1 = 0`)
still serves the `rel == -2` case unchanged.

---

## 5. Regression

Fixed default build `3f398975ba6a5ba7`, mask-OFF `defbfdcbfe4d48e2`.

| fixture | frame deltas | svc fail | sprite-start miss | catchups | replay | page A / B |
|---|---|---|---|---|---|---|
| idle 300 | `[19656]` | 0 | 0 | 0 | 0 | 156 / 144 |
| wave 320 (seed 382) | `[19656]` | 0 | 0 | 1 | 4 | 140 / 180 |
| wrap 340 (seed 12) | `[19656]` | 2 † | 0 | 2 | 5 | 180 / 160 |
| y199 400 | `[19656]` | 0 | 0 | 0 | 0 | 211 / 189 |
| dense 200 | `[19656]` | 0 | **0** | 1386 | 100 | 104 / 96 |
| turret 500 | `[19656]` | 0 | 0 | 0 | 0 | 260 / 240 |
| stress 500 | `[19656]` | 0 | 0 | 1 | 0 | 272 / 228 |

† the pre-existing page-B `$2BF8` pointer race; B(b) measured 3, this build 2 —
run-to-run variance around an untouched defect.

**Phase B(b) intact** across all fixed-build captures: 19 fallback attempts =
10 page-A + 9 page-B + **0 refusals**; **0 seven-pixel snaps, 0 duplicated
turrets, max visual stall 2 frames** (3 on seed 112, the baseline).

**The Phase B(b) row0→row1 detector — the previously undiagnosed signature — is
now exactly 0** on all six seeds (was 1–2 each).

Stage-5: aperture fixed **58..247 on 130/130 frames** for wave, wrap, dense,
turret and stress. Title probe: `$D011=$9b`, ECM=0, YSCROLL=3, `GAME_STATE=0`,
16 starfield glyphs. Gameplay: ECM=1 band.

---

## 6. Answers to the final questions

1. **Reproduce without player input?** Yes — every capture is passive.
2. **Without destroying a turret?** Yes — all turrets at full health throughout.
3. **Correlates with turret count?** Indirectly. It correlates with turret *entry
   events*; more turrets in view means more entries per unit time.
4. **Rate by turret count?** ~40 wrong cell-samples per entry event: 1 entry → 45,
   2 → 77–107, 3 → 90–122, 4 → 137. Zero after the fix in every case. Seeds with
   no entry events (L3 sweep) show zero before and after.
5. **Page A or B?** Both equally — it is a row-computation error, not page-dependent.
6. **Coarse transition or stage wrap?** Coarse transition (each turret entry).
   Wraps were clean once entries were fixed.
7. **Specific fine phase?** No. It persists across a whole coarse cycle; the
   *visibility* of the row-0 sliver depends on `YSCROLL >= 3`.
8. **Turret install / predecode?** Turret **reconcile** on the flip path.
   Predecode was innocent — it correctly writes terrain only.
9. **~128-frame periodicity?** 8 world rows between authored turrets × 16 frames
   per coarse step = 128 frames between entry events.
10. **Wrong before fetch, or written too late?** **Wrong data, written early.**
    Proven with a store watchpoint on the cell.
11. **Which cells?** The two body cells at `TURRET_SLOT_COL`/`+1` in matrix rows 0
    and 1 — row 0 got (228,229) instead of (226,227); row 1 got terrain instead of
    (228,229).
12. **First incorrect operation?** `ssReconcileTurretSlot` `!aboveTop` setting
    `TURRET_CELL_ROW = $ff` for `rel == SLR-1`.
13. **Pages prepared equivalently?** Yes — the error was identical on both.
14. **Multi-turret ordering/scratch bug?** No. Each slot is processed
    independently and correctly; there is no shared-scratch defect. The
    three-turret correlation is purely entry-event frequency.
15. **Stage-5 masking causal?** **Incidental.** Identical counts mask ON and OFF.
16. **Fix?** Nine lines in the `!relHi` branch (§4).
17. **Row0→row1 mismatches now zero?** Yes, 0 on all six seeds.
18. **Three passive wraps clean?** Yes — three wrap crossings, 0 wrong cells.
19. **Phase B(b) intact?** Yes — 0 snaps, 0 dups, 0 refusals, 2-frame stall baseline.
20. **PAL/mux/HUD/mask/starfield safe?** Yes — `[19656]` everywhere, 0 sprite-start
    misses, aperture 58..247 on 130/130, title ECM=0 with 16 star glyphs.
21. **Sprite-pointer flicker changed?** No — still the page-B `$2BF8` race,
    count 3 → 2 (variance). Untouched, and still the recommended next task.
22. **Manual inspection?** §7.
23. **Ready to close after visual acceptance?** Yes for this defect.

---

## 7. What to test manually

Exactly the scenario that reproduced it:

- start the game, **touch no controls**
- let the stage scroll through several turret clusters (rows 345/337/329/321 and
  225/217 are groups 8 rows apart — three to four turrets in view at once)
- allow at least one, ideally three, stage wraps

Expect: turrets should **scroll in from the top edge cleanly**, with the correct
half of the body appearing in the top sliver and the body complete as it enters
the aperture — no fragment appearing, changing shape, or snapping into place.

Also confirm still-good: no 7 px backward hitch, no duplicated turret top, smooth
scroll cadence, Stage-5 top/bottom aperture steady, HUD stable, title/high-score
starfield correct.

**Still expected to be present** (separate, disclosed, not fixed here):

- a **destroyed** turret can leave its body on page B — `background_turrets.asm`
  is page-blind (`restoreDeadTurretRow` / `restoreDeadTurretCells` use page-A-only
  row tables). Requires shooting a turret, so it is out of the passive scenario.
- one enemy sprite occasionally drawing the wrong shape near a page flip — the
  known `ssFlipMirrorPtrs` race.

---

## 8. Reproduction

```
scratchpad/run_hitch.sh <name> <port> <prg> <vs> --seed-scroll <S> --frames 420
```

Seeds with turret entry events: 352, 360, 340, 232, 124, 112, 224; 4-turret
cluster: `--seed-scroll 350 --frames 700`; wrap crossings: 12, 8, 4.

Oracle (`/tmp/oracle2.py` pattern): for each live turret and each of matrix rows
0 and 1, expected content is the top pair iff `world(row) == T`, the bottom pair
iff `world(row) == T+1`, where `world(row) = SCROLL_ROW + row - 1`; frames on
which `SS_FLIP_ADMIT` increments are excluded as the pre-flip sampling transient.
