# Historical Scroll Hitch — Forensic Investigation

**Phase A (diagnosis) COMPLETE. No source file was modified. No fix applied.**
Verdict: **root cause proven, and it contradicts the task premise.**

Branch `main`, HEAD `d60828a`. Working tree carries only the pre-existing
uncommitted Stage 5A/Fable/5B work (`src/main.asm`, `src/raster_scheduler.asm`
+ untracked stage-5 reports). Nothing committed, staged, tagged or pushed.

---

## 1. Headline

The hitch is **not** a fine-scroll pause and **not** a Stage-5 regression. It is a
**page-blindness defect in the legacy coarse-scroll fallback path**, and it was
introduced when Stage 4J made the double-buffered scroller the default build.

> `shiftBackgroundUpper`, `shiftBackgroundLower`, `saveCrossingRow`,
> `restoreCrossingRow` and `copyIncomingRowToScreen` all write **unconditionally
> to `BG_SCREEN_A` (`$0400`)**. They are pre-Stage-4 single-screen code and were
> never made page-aware. When the fallback runs while **page B (`$2800`) is the
> visible page**, the engine advances `SCROLL_ROW`, `SCROLL_FINE` and all logical
> bookkeeping while mutating a page the VIC is not displaying.

The visible result is a **7-pixel backward snap of the whole terrain**, followed
by a permanent one-row desynchronisation between the visible page and
`SCROLL_ROW` — which is what then produces the **duplicated turret** in your
screenshot.

**This does not predate Stage 4.** I tested that directly and the premise does not
hold; §7 has the evidence.

---

## 2. The causal chain (each link measured, not inferred)

1. Sprite/raster load rises — 6–7 live enemies with at least one at the very top
   of the playfield (`OBJECT_Y` 0–1).
2. The inactive-page builder is starved. It must lay down 25 rows in the 16
   physical frames between coarse steps (≥1.56 rows/frame); under this load it
   falls to as low as **6 of 24 rows** by the time the step is due.
3. `ssFlipPrereqOK` fails → `SS_FLIP_INVALID_PAGE` increments → control reaches
   `!legacyCoarsePath` (`src/main.asm:6308`).
4. The legacy path shifts **`$0400`** — regardless of which page is live — and
   decrements `SCROLL_ROW`, clears `SCROLL_FINE`.
5. If `BG_ACTIVE_PAGE == 1` the visible page is **not touched at all**. The
   terrain freezes while the fine scroll resets 7 → 0: a **−7px snap**.
6. The visible page is now one world row behind `SCROLL_ROW`, permanently.
7. On the *next* successful flip, the builder faithfully copies the stale turret
   (`INACTIVE[r] = ACTIVE[r-1]`) to row `rel`, while
   `ssReconcileTurretsOnNewPage` writes a fresh, correct body at row `rel+1`.
   `ssReconcileTurretRow` **only ever writes two cells and never erases**
   (`src/main.asm:7715`), so both survive → **top body rendered twice
   vertically**, persisting for as long as the turret is on screen (measured 129
   and 257 frames in two captures).

---

## 3. The invariant that is violated

> For every presented frame, the matrix on the page selected by `$D018` must
> represent world rows `[SCROLL_ROW-1 .. SCROLL_ROW+23]` at matrix rows `[0..24]`.

The legacy coarse path advances `SCROLL_ROW` while mutating a fixed page. The
invariant therefore holds **only when `BG_ACTIVE_PAGE == 0`**. Nothing in the
admission logic checks this.

---

## 4. Deterministic law found in the data

Across 8 double-buffered captures (7 seeds + the original `--seed-scroll 352`):

| legacy coarse event | active page | outcome |
|---|---|---|
| 10 events | page B | **10 visible freezes** |
| 9 events | page A | **0 visible freezes** |

**Correlation is 1:1 with no exceptions.** A legacy event on page A is fully
benign (it mutates the page it is displaying, exactly as it did pre-Stage-4).

Load conditions at *every* one of the 19 legacy events: **6 or 7 live enemies**,
and **minimum enemy `Y` of 0 or 1**. The one seed in the sweep whose enemy count
never sustained that load (`sw-c-224`, mean 1.27 enemies) produced **zero**
events, zero freezes and zero duplications.

---

## 5. Measured directly from rendered VIC-II output

Frame-to-frame vertical displacement of the terrain, cross-correlated on a
sprite-free column strip of the actual captured PNGs (`dy` = pixels moved down):

```
Stage 4J default build, freeze at frame 96      Single-screen Mode A, identical seed
  frame 93: dy= +0px                              frame 93: dy= +0px
  frame 94: dy= -1px                              frame 94: dy= -1px
  frame 95: dy= +0px                              frame 95: dy= +0px
  frame 96: dy= +7px   <<< BACKWARD SNAP          frame 96: dy= -1px
  frame 97: dy= +0px                              frame 97: dy= +0px
  frame 98: dy= +0px      (scroll stalled)        frame 98: dy= -1px
  frame 99: dy= -1px                              frame 99: dy= +0px
```

Mode A steps a clean `-1px` every second frame. The shipping build jumps **+7px
in the wrong direction** and then stalls for two further frames. That is the
hitch, on real video output.

---

## 6. The duplicated turret — answered point by point

The six recorded questions:

1. **What exact matrix/turret state caused the duplicated upper half?**
   Capture `h-off4j`, slot 7, `TURRET_SLOT_COL=17`, `TURRET_SLOT_ROW=345`,
   `HEALTH=3`. A legacy coarse event at frame 145 with page B active left the
   visible turret at matrix row `rel+0` instead of the canonical `rel+1`. At the
   next real flip (frame 163→164, `SCROLL_ROW=342`, `rel=3`), page A received the
   builder's shifted copy at row 3 **and** the reconcile's correct copy at row 4.
2. **Was the active screen page internally inconsistent?** Yes — after the
   page-B legacy event the visible page represents world row `SCROLL_ROW+1` while
   every logical consumer (turret reconcile, wave triggers, terrain streaming)
   uses `SCROLL_ROW`.
3. **Were two different world rows presented?** Yes. The duplicated glyph pair is
   the same turret at two different world-row interpretations, one row apart.
4. **Was a page flipped before turret reconciliation completed?** No. Reconcile
   ran normally and wrote the *correct* position. The flip ordering in
   `ssPublishCoarseFlip` is sound.
5. **Was the turret drawn onto both old and new row positions?** Yes — but not by
   a double draw. The builder's row shift *carried* the stale copy forward while
   reconcile *added* the correct one. `ssReconcileTurretRow` writes two cells and
   never clears, so nothing removes the stale pair.
6. **Was a row copied twice / not advanced / stale?** Not advanced. The visible
   page missed exactly one coarse advance.

Statistical confirmation over all alive turrets and all frames: the top body sits
at `rel+1` (canonical) 281 times and at `rel+0` (stale) 146 times — two distinct
populations, and every transition into the `rel+0` population coincides with a
page-B legacy event.

Visual proof: `/tmp/turret_duplication_evidence.png` — a correct turret is two
rows tall (top, bottom); the defective one is **three** (top, top again, bottom),
matching your screenshot exactly.

---

## 7. "This hitch predates Stage 4" — tested, and it does not

This is the one place my findings contradict the brief, so I tested it as
directly as possible.

**The control is exact.** Building the current tree with `OPT_SECOND_SCREEN` and
`SCROLL_EDGE_MASK` commented out produces `f2abc225159e81bf` — **byte-identical
to a fresh build of the `stable-single-screen-scroller` tag** (`a544e90`). All
Stage 4 and Stage 5 work is perfectly contained behind its toggles, so the Mode A
control *is* the pre-Stage-4 game, bit for bit.

| build | seeds | visible freezes | duplicated turrets | coarse deferrals |
|---|---|---|---|---|
| pre-Stage-4 single-screen (`f2abc225`) | 8 captures | **0** | **0** | **0** |
| Stage 4J default, mask off (`80d5b046`) | 6 seeds | **5 of 6 seeds** | up to 256 frames | 0 |
| current working tree (`69224428`) | 1 seed | 2 | 121 frames | 0 |

Also relevant to the timeline: the `stable-double-buffered-scroller-v2` tag ships
with `OPT_SECOND_SCREEN` **commented out**. Double buffering only became the
default build at **Stage 4J**. Before that you were playing Mode A, which is clean.

**There *is* a genuinely older mechanism, but it is a different one.** Under
extreme synthetic load (`--dense`, 16 objects) the pre-Stage-4 build defers the
coarse step **185 times with `COARSE_ADMIT = 0`** — the scroll is blocked for the
entire capture (longest consecutive-deferral run: 185, reason 1). That is a real
historical hitch — but it did not fire once in any ordinary 6-enemy wave I
captured (**0 deferrals of any reason** across 4 seeds and `--stress`). So the
mechanism you remember is load-induced *deferral*; the one you are seeing now,
and which produced the duplicated turret, is the newer page-blindness defect.

> **Correction (Phase B).** An earlier revision of this section quoted 47,361
> deferrals. That figure was wrong: `BG_COARSE_DEFERRED` (`$979e`) lies *outside*
> the `.coarse` dump, which begins at `COARSE_DEFER_LIVE` (`$979f`), so reading it
> by offset silently returned unrelated bytes. The corrected numbers above come
> from the reason counters, which are inside the dump. The conclusions are
> unaffected — they rest on the content oracle and the rendered-output
> cross-correlation, not on this counter.

I'd rather flag the contradiction than quietly fold the evidence into the stated
premise. If you have a pre-4J recording of the hitch, that would settle it.

---

## 8. A correction to my own earlier finding

Before compaction I reported a signature of "fine-phase holds of 3 frames instead
of 2" coinciding with legacy frames. **That signature is invalid.** The clean
pre-Stage-4 baseline shows the same 3-frame holds (6–12 per 420-frame capture)
with zero freezes. It is an aliasing artefact between the raster-311 sample point
and `SCROLL_FRAME_COUNT`, not a defect. The content-based oracle in §4/§5
(comparing the *visible page's* matrix across frames, and cross-correlating the
rendered PNGs) is the correct instrument, and it is what the conclusions rest on.

Similarly, an apparent "intra-frame tear" at the frame-404 legacy event is a
**sampling artefact**: the capture breakpoint is at raster $137 (line 311), and
`shiftBackgroundLower` legitimately runs at the following frame's top, before the
beam reaches row 13. On page A the legacy path is correct. I discarded that
finding rather than report it.

---

## 9. Recommended repair (Phase B — not implemented)

Two options, smallest first.

**(a) Refuse the legacy path when it would corrupt — ~6 instructions.**
At `!legacyCoarsePath`, if `BG_ACTIVE_PAGE != 0`, `jmp !defer` instead of
shifting. This converts a corrupting freeze into the clean, pre-Stage-4 one-frame
coarse deferral, and gives the builder another frame to finish — which it usually
will. Removes both the −7px snap and the turret duplication at their source,
because the visible page can never desynchronise from `SCROLL_ROW`.
*Risk:* repeated deferral if the builder is persistently starved; wants a bounded
retry count.

**(b) Make the legacy path page-aware — the complete fix.**
The five routines are unrolled absolute-addressed code (480 + 440 + 40 + 40
bytes). The cycle-neutral way is a second copy targeting `$2800`, dispatched on
`BG_ACTIVE_PAGE`; roughly 1 KB of extra code for zero added cycles. Larger
change, in the most timing-sensitive part of the engine.

**Worth doing alongside either:** raise the builder's completion margin
(`SS_PLF_BUILD_SLICE_ROWS`, or widen the slice window past
`SS_PLF_SLICE_RASTER_CUTOFF=180`) so the fallback is rarely reached at all. That
attacks step 2 of the chain rather than its consequence.

My recommendation is **(a) now**, then measure how often the deferral actually
bites, then decide whether (b) is needed. I have not touched any source file —
say the word and I'll implement and run the full regression suite.

---

## 10. Reproduction

```
scratchpad/run_hitch.sh <name> <port> <prg> <vs> --seed-scroll <S> --frames 420
```
Seeds that reproduce on the Stage 4J default build: 352, 360, 340, 232, 124, 112
(clean: 224). Captures retained under `build/`: `h-t350`, `h-off4j`, `h-modea`,
`sw-c-*`, `sw-a-*`, `base1-*`, `st-*`, `dn-*`.

Detector: for each frame where fine resets 7→0, compare the **visible** page's
matrix with the previous frame's; ≥24 of 25 rows identical ⇒ visible freeze.
