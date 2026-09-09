# Four-Turret Flicker — Frame-by-Frame Screen RAM Forensics

## 1. Verdict

**GREEN for the question this task asks — screen RAM is exonerated.**

Across 850 consecutive passive PAL frames covering the complete
`345 / 337 / 329 / 321` reproduction window, **the active screen matrix is a
perfect, coherent 25-row window of the authored stage on every frame the VIC
actually displays.** No incorrect character publication or content was found in
the user's reported interval.

**No production code was changed.** Harness-only changes are listed in §12.

This does not fix the user's symptom. It removes the scroller/turret matrix path
from suspicion and localises the remaining defect to the presentation layer.

Branch `main`, HEAD `d60828a`, working tree as found. Nothing committed, staged,
tagged or pushed.

---

## 2. The fixture was genuinely passive — verified, not assumed

FIRE is used once to leave the title screen and released immediately; the joystick
is neutral (`jpdb 1 ff`) on **every** captured frame. Verification over the whole
850-frame capture:

```
occupied-turret-slot samples:  alive = 1794    dead = 0
```

Zero turret damage, zero destruction, no movement, no shooting. Build is the
**mask-ON default** (`58e9d59131e4791b`), matching real gameplay.

For contrast, the standard `vst_hitch.py` runner holds FIRE every frame
(`jpdb 1 {255 ^ (16 | direction)}`, bit 4 = fire) and destroys turrets throughout
— which invalidated earlier investigations.

---

## 3. Capture interval and conditions

| | |
|---|---|
| build | `58e9d59131e4791b` (mask ON, default) |
| seed | `--seed-scroll 352` |
| frames | 850 consecutive physical PAL frames |
| sample point | raster `$137` (line 311), end of frame |
| per frame | `SCROLL_ROW`, `SCROLL_FINE`, `$D000-$D02F` (incl. `$D011`/`$D018`), `BG_ACTIVE_PAGE`, **full Screen A `$0400-$07FF`**, **full Screen B `$2800-$2BFF`**, colour RAM `$D800-$DBFF`, flip/fallback/builder counters, full turret state |

The window contains: clean 0-turret state, turret #1 entering (frame 111), #2
(239), **#3 (367)**, #4 (495), and the decline back to 2 (623) and 1 (751).

---

## 4. Methodology — ground truth, not a proxy

I decoded the stage tables **independently in Python** from the captured
`metatiledefs.bin` and `stagemetatilerows.bin`, replicating
`decodeStageCharacterRow` exactly (`METATILE_W/H = 4`, `METATILES_PER_ROW = 10`;
`metatileRow = world >> 2`, `tileRowOfs = (world & 3) * 4`,
`ids = stageMetatileRows[metatileRow*10 ..]`, `chars = metatileDefs[id*16 + ofs ..+3]`).
This yields the correct 40 characters for any world row with no reference to
engine state.

For every frame and both pages I then asked: **is this matrix a perfect 25-row
window of the stage at *some* offset?** Turret body glyphs (226–229) are accepted
as legitimate overlays. Searching the offset rather than asserting one avoids
assuming the mapping.

The mapping fell out of the data and is consistent across the whole capture:

- **active page: offset −1** — matrix row `r` holds world row `SCROLL_ROW + r − 1`
  (matches `BG_LOGICAL_ROW = SCROLL_ROW + BG_DEST_ROW − 1`)
- **inactive page**: offset `0` immediately after being displaced (stale), moving
  to offset `−2` once the builder completes it for the next coarse step
  (`INACTIVE[r] = ACTIVE[r−1]`)

---

## 5. Screen RAM verdict

```
frames whose ACTIVE matrix is a perfect 25-row stage window:
    offset -1, non-admit frame : 797 frames
    offset  0, admit frame     :  50 frames     <- pre-flip sampling transient
INCOHERENT (no offset gives 25/25):  3 frames   <- frames 95, 127, 831
```

The 50 offset-0 frames are the known sampling transient: on a coarse-admit frame
`SCROLL_ROW` is already decremented at raster 311 while the `$D018` flip happens at
the *next* frame top, so the still-displayed page legitimately matches the old
`SCROLL_ROW`. Not a defect.

### The 3 incoherent frames — and why they are not displayed

They correlate **1:1, with no exceptions**, with the only three legacy in-window
fallback executions in the capture:

```
frame  95 : SS_LEGACY_PAGEB_EXEC        0 -> 1     torn rows 1..11
frame 127 : SS_LEGACY_COARSE_PATH_COUNT 0 -> 1     torn rows 13..24
frame 831 : SS_LEGACY_PAGEB_EXEC        1 -> 2     torn rows 0..12
totals: SS_FLIP_ADMIT 50, SS_FLIP_FALLBACK 3, PAGEB_BLOCK 0
```

That is the legacy path's two-phase shape: rows 1–12 shift in frame *N* (at
raster ≥ 160, after those rows have been fetched), rows 14–24 plus the crossing
row at the top of frame *N+1* (before row 13 is fetched). The matrix is
half-shifted **in RAM** between the two — exactly where my raster-311 sample
lands — but never on screen. Measured:

| frame | path | upper shift start | upperCopied | next frame lowerReady | row-13 fetch | margin |
|---|---|---|---|---|---|---|
| 95 | page B | 170 | 272 | **143** | 152 | 9 lines |
| 127 | page A | 165 | 233 | **114** | 152 | 38 lines |
| 831 | page B | 170 | 273 | **142** | 152 | 10 lines |

Row 12 is fetched by raster 151 and the upper shift starts at 165–170, so the
frame *N* display is fully old and coherent; the lower half completes at 114–143
against a row-13 fetch at 152, so frame *N+1* is fully new and coherent.

**Across both fixtures (10 legacy events) the deadline was met every time, worst
margin 9 rasterlines on the page-B path.** Flagging that as the tightest number in
the pipeline: if it were ever missed, rows 13–24 *would* tear visibly. It is not
being missed today.

### Active/inactive page findings

No incoherent active frame exists outside those three, which means **the inactive
page is never published while incomplete** — an incomplete page becoming active
would show up immediately as an incoherent active matrix. Inactive-page states
observed are the expected build progression (stale offset 0 → partial → complete
offset −2).

---

## 6. Exact cluster timeline

"In aperture" = authored world row with `rel = (row − SCROLL_ROW) mod 420` in
`0..23`, i.e. a body row on the visible matrix. This is the machine predicate; it
is not claimed to match the user's perception.

| frame | `SCROLL_ROW` | active page | cluster turrets in aperture | n | active matrix |
|---|---|---|---|---|---|
| 0 | 352 | A | — | 0 | OK |
| 111 | 345 | — | 345(rel0) | 1 | OK |
| 239 | 337 | A | 337(rel0), 345(rel8) | 2 | OK |
| **367** | **329** | **A** | **329(rel0), 337(rel8), 345(rel16)** | **3** | **OK** |
| 495 | 321 | — | 321(rel0), 329(rel8), 337(rel16) | 3 | OK |
| 623 | 313 | A | 321(rel8), 329(rel16) | 2 | OK |
| 751 | 305 | A | 321(rel16) | 1 | OK |

**The 2→3 transition is frame 367. Frames 367–622 — the user's entire reported
window — contain zero matrix anomalies.** The three incoherent frames (95, 127,
831) all lie outside it.

A geometric note worth recording: the cluster is spaced 8 world rows apart and the
aperture is 24 rows, so **at most three of the four turrets can be on screen at
once** (3 × 8 = 24). Turret #4 entering coincides exactly with turret #1 leaving.
What the user describes as "the fourth appears" is that crossover, not a
four-turret overlap.

---

## 7. Colour RAM verdict (secondary)

Reported separately, as required. The previous turret colour-presentation fix is
**holding**: using the live `TURRET_PULSE_COLOUR` to avoid the phase-0/terrain
colour ambiguity, only **4 single-frame** dropouts remain in 850 frames, all at
`rel == 0`, one per turret entry (frames 111, 239, 367, 495).

Those are the known one-frame publish-ordering residual — the glyph is published
at the coarse flip while colour is painted at the next frame top. 20 ms each.

**A clean screen-matrix trace is not being reinterpreted as a screen-RAM failure
because colour changes.** Screen RAM: clean. Colour RAM: clean apart from that
4-frame residual.

---

## 8. Control fixture

Diagnostic tree only; authored production stage data untouched. Turret `329`
removed, so the 2→3 transition no longer occurs at that point.

| | full cluster | control (329 removed) |
|---|---|---|
| coherent active frames | 847/850 | 843/850 |
| incoherent active frames | 3 | **7** |
| legacy fallback executions | 3 | 7 |
| all lowerReady vs 152 deadline | 114–143 ✓ | 111–143 ✓ |

Removing a turret produced **more** tears, not fewer — and each remains a
never-displayed RAM artefact. This is informative: the legacy-fallback tears are
driven by CPU/raster load and which coarse steps miss the builder deadline, **not
by turret 329 or by the 2→3 transition**. It further exonerates the cluster
geometry as a matrix-level cause.

---

## 9. First incorrect byte / writer

None in the displayed output. The only incorrect *RAM* states are the three
mid-legacy-shift samples, whose writer is by construction
`shiftBackgroundUpper` / `shiftBackgroundUpperB` (frame *N*) with
`shiftBackgroundLower*` / `restoreCrossingRow*` completing at frame *N+1* top —
a designed two-phase update whose intermediate state the VIC never fetches.

---

## 10. Repair

**None made**, per the decision tree: screen RAM is clean, so no production fix is
justified from this evidence.

---

## 11. Regression

Not applicable — no production code changed. The build under test is the existing
`58e9d59131e4791b`, unmodified.

---

## 12. Harness changes (separate from production)

In the passive diagnostic runner only (`scratchpad/vst_passive.py` /
`run_passive.sh`):

1. per-frame VIC register dump (`$D000-$D02F`) so `$D011`/`$D018` are recorded
   with every frame;
2. **`--hold-fire` is now an explicit opt-in.** The default is genuinely passive.
   Combat/turret-destruction tests must ask for FIRE deliberately.

Recommendation: make this the standard path for scrolling, sprite-capacity,
background-turret and passive-presentation diagnostics. Do not use a runner that
silently holds FIRE.

---

## 13. Recommendation

**Screen RAM is exonerated for this reproduction. Moving the authored turret is a
reasonable temporary workaround, and further presentation-layer investigation is
justified if you want the root cause.**

Concretely:

- The character matrix the VIC displays is provably correct on every frame of the
  window, verified against an independent decode of the stage tables. The
  scroller, the page-aware fallback, the builder, turret install and turret
  reconcile are all clean here. **Stop chasing them for this symptom.**
- What remains plausible, from the captured evidence: colour RAM behaviour that is
  *correct* but visually undesirable — in particular the turret pulse table
  `1, 2, 7, 2` whose phase 0 (`1|8 = 9`) is **identical to `TERRAIN_COLOUR_RAM`**,
  so every turret flattens into the terrain colour for 8 frames in every 32, and
  all turrets pulse in unison from a single global `TURRET_PULSE_INDEX`. With
  three turrets on screen that is a synchronised, repeating brightness change in
  the upper playfield. It is *by design*, which is exactly why no correctness
  oracle flags it — and it is the best remaining candidate for what is being
  perceived as flicker.
- The cheapest experiment to confirm or kill that: change `turretPulseTable`
  phase 0 from `1` to something not equal to `TERRAIN_CHARACTER_COLOUR`, or
  lengthen `TURRET_PULSE_INTERVAL`, and ask whether the symptom changes character.
  That is a one-byte diagnostic, not a scroller change — but it is a *presentation*
  question and I have not made that change.
- As a workaround, moving one cluster turret so that no more than two are in the
  24-row aperture at once (spacing > 12 world rows) is safe and touches only
  authored stage data.

If the flicker persists after the pulse experiment, the next capture should target
VIC-level presentation rather than RAM: per-raster `$D011`/`$D016`/`$D018` sampling
inside the visible window rather than one sample at line 311.

---

## 14. Reproduction

```
scratchpad/run_passive.sh <name> <port> <prg> <vs> --seed-scroll 352 --frames 850
```

Analysis: decode the stage from `metatiledefs.bin` + `stagemetatilerows.bin`
(`/tmp/terrain.py` pattern), then for each frame test whether the active matrix is
a perfect 25-row window at any offset in −4..+4, accepting 226–229 as turret
overlays. Offset −1 = normal, offset 0 on an admit frame = pre-flip transient,
anything else = genuine incoherence.
