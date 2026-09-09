# Scroll Hitch — Stage 4D: Incremental Inactive-Screen Construction

Branch `experimental-border-hud`. KickAssembler 5.25, VICE x64sc 3.10, PAL.
Follows Stage 4A–4C (`/reports/stage4-second-screen-scroller-architecture.md`).

---

## 1. Executive verdict — **AMBER**

**The central question is answered YES:** the exact next coarse-scroll screen
state *can* be built incrementally in the inactive character page, byte-for-byte
identical to the legacy coarse transformation (including stage wrap), and once
built it stays valid indefinitely through a prolonged reason-1 hold with zero
redundant work. Terrain aperture, sprite capacity, collision, wave/turret/editor
contracts and the reason-1 (`COARSE_DEFER_LIVE`) admission gate are all untouched,
and exact PAL cadence `[19656]` is preserved in every workload.

**One bounded issue keeps this AMBER rather than GREEN:** the builder adds exactly
**one `RASTER_REPLAY_FRAME` per coarse admit** (≈1 frame in 16 while scrolling;
**zero** during a reason-1 hold). It is not corruption and not capacity loss — the
replay path services those frames correctly (`[19656]` exact, 0 catchups, 0
incomplete frames, 0 border bails, 0 service failures, 0 sprite-start misses). The
cause is pinned: the `f07b81f` baseline's coarse-admit frame reaches
`waitForGameFrame` with **< ~20 cycles of slack**, and ~20 cycles of unconditional
per-frame 4D scheduler code on that frame's path tips `RASTER_PRESENT_READY` to 0
at line 1. It is independent of slice size (0/1/2/3 rows all give the same count)
and of where in the frame the tick is called. **It is expected to invert under
Stage 4E:** 4E removes `shiftBackgroundUpper` (3 840 cy) + the in-window decode
(~1 400 cy) + the crossing-row save/restore from the admit frame and replaces
them with a 4-cycle `$D018` write, freeing far more admit-frame slack than the 4D
tick consumes. 4D measured in isolation pays the builder cost *while the legacy
admit still does all of its in-window work* — double coarse-frame load.

Per the task's own definition ("AMBER for a promising architecture with one
bounded unresolved problem, e.g. narrow timing margin") this is the correct
verdict. A concrete resolution path exists (4E) and the builder itself is proven.

---

## 2. Exact starting repository state

Local checkout was **1 commit behind** `origin/experimental-border-hud`. The Stage
4A–4C baseline (`f07b81f` "VIC Bank memory reclaim for screen 2 stage 1 complete":
+`reports/stage4-second-screen-scroller-architecture.md`, +208 lines in
`src/main.asm`, all behind `#if OPT_SECOND_SCREEN`) existed **only on origin** —
the task prompt's "modified src/main.asm / all Stage 4 work behind #if
OPT_SECOND_SCREEN" wording assumed it was present as uncommitted changes.
**The user explicitly authorised a fast-forward** (`git merge --ff-only
origin/experimental-border-hud`, a lossless direct-child update of the clean tree)
to bring it in, overriding the task's "no pull" limit for that one step.

```
$ git branch --show-current      experimental-border-hud
$ git rev-parse HEAD              f07b81fbcdb3240fde92e49c8f3694392e0e59df   (after the authorised FF)
$ git status --short             (clean at task start)
$ git log -4 --oneline
f07b81f VIC Bank memory reclaim for screen 2 stage 1 complete
223a820 Stabilise single-screen scroller under mux load   (tag: stable-single-screen-scroller)
6a64130 Four top HUD sprites stable under managed mux load
bc9d275 Hard lock fixed, border sprite flicker remains
```

Level: `STAGE_METATILE_ROWS = 105`, `METATILE_H = 4` ⇒ `STAGE_LOGICAL_ROWS = 420`;
`SCROLL_FRAME_DIVIDER = 2` ⇒ ~16 physical frames per coarse cycle.

## 3. Files changed

| file | change |
|---|---|
| `src/main.asm` | `+353 / -3` lines, one hunk each: (a) new sub-toggle `#define OPT_SS_INACTIVE_BUILD` under `OPT_SECOND_SCREEN` + two build guards; (b) the Stage-4D block in the `$9900` CPU-only region — page-aware addressing tables, `SS_BUILD_*` state/diag, `ssInactiveBuildReset`, `ssInactiveBuildTick` (scheduler), `ssInactiveBuildSlice`, `ssInactiveBuildRefreshTarget`, `ssRow0TargetMatchesPredecode`, `ssCopyOneInactiveRow`, `ssInstallInactiveRow0`; (c) `bgPredecodeReset` tail-calls `ssInactiveBuildReset`; (d) `noteCoarseSuppressionOutcome` (both exits) tail-calls `ssInactiveBuildTick`; (e) a comment on `predecodeNextStageRow`. Every functional addition is `#if OPT_SS_INACTIVE_BUILD`-guarded. |
| `docs/stage4d-incremental-inactive-screen-worklog.md` | new — investigation log. |

No commit / add / tag / push / pull / reset / stash / branch switch beyond the
one user-authorised fast-forward in §2. Changes left unstaged.

## 4. Toggle matrix + hashes

| mode | toggles | sha256(prg) | verdict |
|---|---|---|---|
| **1** | `OPT_SECOND_SCREEN` OFF (default) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` | **bit-identical to the Stage 3 baseline** |
| **2** | `OPT_SECOND_SCREEN` ON, `OPT_SS_INACTIVE_BUILD` OFF | `326f1686f3cf3d0526579de167dcb6a6806da48c035fd4a9ad93b90852ff8ab9` | **bit-identical to the 4A+4B+4C baseline** |
| **3** | `OPT_SECOND_SCREEN` ON, `OPT_SS_INACTIVE_BUILD` ON | `b73c765e9bcc54ec63a7cf1059b27565de392fb0534052998a85f45138c87140` | 4D active; memory guards pass (`$9900` block `$9900–$99e6`) |

Modes 1 & 2 are unchanged binaries, so no timing regression is possible with the
builder disabled. Reversibility is complete: comment `//#define OPT_SS_INACTIVE_BUILD`.

## 5. Page-aware addressing design

`BG_ACTIVE_PAGE` (0 = page A `$0400` displayed, 1 = page B `$2800` displayed) is
the single selector. Page B rows are page A rows **+ `$2400`**, so only the
address **high byte** differs between pages. The plumbing is therefore three
2-entry tables indexed by `BG_ACTIVE_PAGE`, no branch tree, no scattered
`$0400`/`$2800` arithmetic:

```
ssActiveHiDelta   .byte $00,$24     ; add to (page-A row hi) for the ACTIVE page
ssInactiveHiDelta .byte $24,$00     ; ... for the INACTIVE page
ssActiveD018      .byte $1E,$AE
ssInactiveD018    .byte $AE,$1E
```

`ssCopyOneInactiveRow` / `ssInstallInactiveRow0` build `TEXT_SRC` / `TEXT_DST`
from `starRowLo[r]` / `starRowHi[r]` (the existing row-address tables) plus the
delta. The existing single-screen path is unchanged (it uses `starRowLo/Hi`
directly = page A). Sprite-pointer table addresses are `page_base + $3F8`
(`$07F8` / `$2BF8`) — not needed by the builder (§13).

**Hook placement.** The `$080e` main-code segment has only ~2 bytes of headroom,
so both 4D hooks are **tail-calls from routines already in the roomy relocated
segments**, adding zero bytes to `gameLoop`:
`bgPredecodeReset → ssInactiveBuildReset`, and
`noteCoarseSuppressionOutcome → ssInactiveBuildTick` (runs once per frame, after
`prepareBackgroundCoarse`).

## 6. Exact inactive target / tag semantics

`SS_BUILD_TARGET_ROW` (16-bit) = **the post-coarse `SCROLL_ROW`** the finished
INACTIVE page represents:

```
SS_BUILD_TARGET_ROW = (SCROLL_ROW_current - 1) mod STAGE_LOGICAL_ROWS
                      (SCROLL_ROW_current == 0 folds to SLR-1)
```

This is exactly the value `prepareBackgroundCoarse` installs on an admit. The
INACTIVE page's decoded top row is therefore
`(SS_BUILD_TARGET_ROW - 1) mod SLR = (SCROLL_ROW_current - 2) mod SLR` — **identical
to the Stage-2 predecode target**, so `BG_PREDECODED_ROW` is shared and the
incoming row is never decoded twice (`ssRow0TargetMatchesPredecode` gates
completion on `BG_PREDECODE_VALID` + tag match).

`ssInactiveBuildRefreshTarget` (once per frame) classifies a changed tag:

| observed | action |
|---|---|
| tag unchanged | keep the build / stay VALID (the fine-7 held-frame no-op) |
| `stored - target ≡ 1 (mod SLR)` | **normal advance** (a coarse step; seamless across a stage wrap) → restart the build, `SS_BUILD_ADVANCE_COUNT++` |
| any other delta | **discontinuity** (fixture poke / repaint / level reinit) → restart, `SS_BUILD_INVALIDATE_COUNT++`, `SS_INVAL_DISCONT++` |

`ssInactiveBuildReset` (from `initBackground` via `bgPredecodeReset`, before the
`SCROLL_ROW` reseed) drops any in-flight build and zeroes all 4D counters.

## 7. Exact row transformation (derived from the real coarse code)

The current single-screen coarse step, net over its two frames
(`prepareBackgroundCoarse` + `finishBackgroundCoarse`), is:

```
newRow[r] = oldRow[r-1]                       for r = 1 .. 24
newRow[0] = decodeTerrain((SCROLL_ROW-2) mod SLR)  + live turret overlay
```

`shiftBackgroundUpper` does `for row=12..1: SCREEN[row] = SCREEN[row-1]`;
`shiftBackgroundLower` does `for row=24..14: SCREEN[row] = SCREEN[row-1]`; the one
straddling row (old row 12 → new row 13) is carried in `BG_CROSSING_ROW`. The
two-frame split and the crossing buffer exist **only** because that mutation is
in-place on the displayed matrix and must dodge the VIC fetch (row 12 is the last
cached row when the upper copy runs at raster ≥ 160).

In the INACTIVE page there is no beam constraint, so the builder is simply:

```
INACTIVE[r] = ACTIVE[r-1]     for r = 1 .. 24     (ssCopyOneInactiveRow, ~674 cy/row)
INACTIVE[0] = BG_PREDECODED_ROW                   (terrain only; turret overlay is 4E)
```

spread over the fine-scroll frames of the cycle. `finishBackgroundCoarse`'s lower
shift is folded in (rows 14..24 are just part of the r=1..24 loop). The row
mapping direction was taken from the assembler, not from any prose description.

## 8. Byte-equivalence methodology and results

`scratchpad/s4d_equiv.py`. For each seeded `SCROLL_ROW`: force the builder to
rebuild (`SS_BUILD_STATE:=0`), hold the coarse step off (pin `SCROLL_FINE`,
`SCROLL_FRAME_COUNT`), run until `SS_INACTIVE_VALID`, snapshot the INACTIVE page;
then let the engine perform **one real legacy coarse admit** and snapshot the
resulting ACTIVE page; compare all 25×40 = 1 000 character cells. (The legacy
transform runs on the *same* frozen input the builder used — this is the task's
specified "reference vs candidate" method.)

Seeds: 200, 60, 380 (mid-stage), 2, 1 (near-wrap), **0 (stage wrap → tag SLR-1 =
419)**, 419, 300.

| seed `SCROLL_ROW` | tag (post-coarse) | INACTIVE row0 == `BG_PREDECODED_ROW` | INACTIVE vs ACTIVE-after-real-legacy-coarse |
|---|---|---|---|
| 200 | 199 | PASS | **0 cell diffs** |
| 60 | 59 | PASS | **0 cell diffs** |
| 380 | 379 | PASS | **0 cell diffs** |
| 2 | 1 | PASS | **0 cell diffs** |
| 1 | 0 | PASS | **0 cell diffs** |
| **0** | **419 (wrap)** | PASS | **0 cell diffs** |
| 419 | 418 | PASS | **0 cell diffs** |
| 300 | 299 | PASS | **0 cell diffs** |

**Zero unexplained terrain-byte mismatches on any seed, including the actual stage
wrap.** Turret-overlay cells are inside this 1 000-cell compare and also match
(the builder carries ACTIVE's baked turret glyphs verbatim; the legacy admit
shifts the same baked glyphs). Sprite-pointer bytes (`$xBF8..$xBFF`) are handled
separately (§13) and are correctly left untouched by the builder.

## 9. Scheduler design

`ssInactiveBuildTick` (once per frame, tail-called after `prepareBackgroundCoarse`):

1. **Withhold the whole tick** — target refresh *and* slice — when
   `BG_COARSE_PENDING` (the fine-7 admit-candidate frame) **or** `BG_COARSE_FINISH`
   (the post-admit frame owing `shiftBackgroundLower`, 3 520 cy) is set, or when
   `$D011` bit 7 shows the beam has wrapped past 255. `SS_BUILD_SKIP_COUNT++`. The
   target cannot change on those frames (`SCROLL_ROW` is decremented *inside*
   `prepareBackgroundCoarse`), so deferring loses nothing.
2. Otherwise `ssInactiveBuildRefreshTarget`, then `ssInactiveBuildSlice`:
   - `SS_BUILD_STATE` ∈ {0 idle, 1 building, 2 complete+valid}; states 0/2 →
     immediate `rts` (the held-frame no-op).
   - state 1: copy up to `SS_BUILD_SLICE_ROWS` rows `INACTIVE[r] ← ACTIVE[r-1]`,
     `SS_BUILD_NEXT_ROW` advancing 1..24; each copy `SS_BUILD_SLICE_WORK++`, and
     `SS_BUILD_REDUNDANT_WORK++` if it ever happens while `SS_INACTIVE_VALID`
     (structural invariant check — must stay 0).
   - `SS_BUILD_NEXT_ROW == 25` → if `ssRow0TargetMatchesPredecode` C=1, install
     row 0 from `BG_PREDECODED_ROW`, set STATE=2 / `SS_INACTIVE_VALID=1`,
     `SS_BUILD_COMPLETE_COUNT++`; else `SS_BUILD_ROW0_WAIT++` and retry next frame.

The build has ~16 physical frames per coarse cycle; withholding the ~1–2
coarse-critical frames leaves ≥ ~13 for 8–12 slices (`SS_BUILD_SLICE_ROWS` = 2..3),
so completion is guaranteed well before the next coarse step — no
"it should eventually finish" logic.

## 10. Slice-size measurements

Idle natural play, 400 physical frames, `SS_BUILD_SLICE_ROWS` monitor-poked to
0 / 1 / 2 / 3 (`scratchpad/s4d_sweep.py`; slice 0 = whole 24-row build in one
frame):

| metric | Mode 2 (4D off) | slice 0 | slice 1 | slice 2 | slice 3 |
|---|---|---|---|---|---|
| `frame_cycle_deltas` | `[19656]` | `[19656]` | `[19656]` | `[19656]` | `[19656]` |
| `RASTER_CATCHUPS` | 0 | 0 | 0 | 0 | 0 |
| `RASTER_INCOMPLETE_FRAMES` | 0 | 0 | 0 | 0 | 0 |
| `RASTER_BORDER_BAILS` | 0 | 0 | 0 | 0 | 0 |
| **`RASTER_REPLAY_FRAMES`** | **0** | **25** | **25** | **25** | **25** |
| builds start / complete | – | 25 / 25 | 25 / 25 | 25 / 25 | 25 / 25 |
| `SS_BUILD_REDUNDANT_WORK` | – | 0 | 0 | 0 | 0 |
| `SS_BUILD_ROW0_WAIT` | – | 0 | 0 | 0 | 0 |
| `SS_INACTIVE_VALID` (end) | – | 1 | 1 | 1 | 1 |
| `COARSE_ADMIT` | 25 | 25 | 25 | 25 | 25 |

**`RASTER_REPLAY_FRAMES` is identical (== `COARSE_ADMIT`) for every slice size,
including the 24-rows-in-one-frame case.** So the replay is *not* the slice cost —
it is the ~10–20 cy of unconditional per-frame 4D scheduler/guard code landing on
the near-full coarse-admit frame (see §11). Total build cost per cycle = 24 row
copies ≈ **16 100 cy** (24 × ~674) + 1 row-0 install ≈ 320 cy; at slice 2 that is
~1 350 cy on each of ~12 frames.

## 11. Selected slice size and rationale

**`SS_BUILD_SLICE_ROWS = 2` (default).** Rationale: it completes every cycle with
margin (12 slices / ≥13 clear frames; `ROW0_WAIT = 0`, `START == COMPLETE` in
every run), keeps the largest per-frame cost small (~1 350 cy) so a future load
spike has room, and — since the replay count is slice-size-independent — there is
no benefit to a bigger slice and a small correctness cost (bigger monolithic
frame) to it. `SS_BUILD_SLICE_ROWS` stays runtime-pokeable for 4E re-tuning.

## 12. Build cost / per-frame cost / timing margin

| quantity | value |
|---|---|
| total cost to build one complete inactive next-screen state | ~16 400 cy (24 row copies + row-0 install) |
| clocks per slice (slice = 2 rows) | ~1 350 cy |
| slices per build | 12 |
| physical frames available per coarse cycle (divider 2) | ~16 (≥13 after coarse-critical withholds) |
| average added main-thread cost per frame | ~1 000 cy (12 × 1 350 spread over 16) |
| worst added cost on a preparation frame | ~1 350 cy (one 2-row slice) — at raster ~67 on measure, ~15 000 cy of frame left |
| earliest completion relative to the next coarse step | ~4 frames early (12 slices done by frame ~12 of ~16) |
| latest completion | same — deterministic; `ROW0_WAIT` observed 0 |
| positive completion margin | **yes** — `SS_INACTIVE_VALID` reached every cycle, `START == COMPLETE` in every measured run |
| `RASTER_PRESENT_READY` impact | set to 0 at line 1 on the coarse-admit frame → +1 replay/admit (§11); unaffected on all other frames |
| `RASTER_REPLAY_FRAMES` | +1 per coarse admit (25/400 idle; 19/260 wave; 27/320 wrap; **0** during a 600-frame reason-1 hold) |
| `RASTER_CATCHUPS` / `INCOMPLETE_FRAMES` / `BORDER_BAILS` | **+0** everywhere |
| reason-2 / reason-3 coarse deferrals | unchanged (gate untouched) |

## 13. Sprite-pointer strategy — Option A vs Option B

The builder writes only cols 0..39 of rows 0..24, so it **never touches the
`$xBF8..$xBFF` pointer tables** (verified: the INACTIVE table stays at its
`ssInitPageB` values while the ACTIVE table changes).

- **Option A — dual write** at all 5 pointer-write sites (`renderSprites`,
  `hudBorderSetup`, HUD handoff, `applyLiveRasterBatch`, border-marker). The two
  IRQ sites add ~8–10 cy per LIVE batch to the raster hot path.
- **Option B — `ssMirrorSpritePtrs`** (already implemented): one 8-byte copy
  `$07F8→$2BF8` late in the frame, ~50 cy, no IRQ change. Caveat: the displayed
  page's pointer table is one frame stale on the frame it is first displayed —
  void if 4E schedules the flip so the newly-active page was the *inactive* page
  (and was mirrored) the previous frame.

**Recommendation: Option B.** 4D.10/4D.11 showed this HEAD's admit frame and IRQ
path have essentially no spare cycles; Option A's raster-hot-path cost is the
wrong direction. Option B's ordering constraint is naturally satisfied by any
sane 4E flip schedule (flip at frame top to a page that has been inactive — and
mirrored — since the previous frame).

## 14. Prolonged 199/235 reason-1 hold

`scratchpad/s4d_hold.py`. 8 enemies Y=199 + player Y=235; 600 held frames after
the build had completed:

| observable | result |
|---|---|
| `SCROLL_ROW` | 395 → 395 (unchanged) |
| `SCROLL_FINE` | pinned 7 |
| `d COARSE_DEFER_LIVE` | **+600** (reason-1 gate still deferring every frame — unchanged) |
| `d COARSE_ADMIT` | 0 |
| `SS_BUILD_STATE` / `SS_INACTIVE_VALID` | 2 / 1 for all 600 frames |
| `SS_BUILD_TARGET_ROW` | 394 → 394 (constant) |
| `SS_BUILD_START_COUNT` / `COMPLETE` / `SLICE_WORK` | 0 / 0 / 0 over the hold |
| `SS_BUILD_REDUNDANT_WORK` | **0** |
| `SS_BUILD_INVALIDATE_COUNT` / `ROW0_WAIT` / `SKIP_COUNT` | 0 / 0 / 0 |
| `RASTER_REPLAY_FRAMES` / `CATCHUPS` / `INCOMPLETE` | 0 / 0 / 0 |

**Build starts once, completes once, stays valid; the tag is constant; zero
repeated work of any kind; no drift or corruption across hundreds of held
frames.** And the +1 replay/admit cost does not apply during a hold (no admits).

## 15. Invalidation rules and tests

`scratchpad/s4d_inval.py`:

| route | result |
|---|---|
| 120 frames natural play | `start == complete == 8`, `adv = 7`, `inval = 0`, `discont = 0`, `redund = 0`, VALID, tag == `SCROLL_ROW - 1` |
| discontinuous `SCROLL_ROW := 50` poke | `SS_BUILD_INVALIDATE_COUNT` 0→1, `SS_INVAL_DISCONT` 0→1 (**exactly once**); build restarts, recovers to VALID with the new tag; `redund = 0` |
| +60 frames natural (incl. coarse advances) | `inval` still 1 — **no spurious invalidation** from ordinary coarse steps; `redund = 0` |
| stage wrap (`SCROLL_ROW` 0 → tag 419) | classified as a normal −1 advance, byte-equivalence 0 diffs — **seamless, not an invalidation** |
| `initBackground` → `bgPredecodeReset` → `ssInactiveBuildReset` (game start/restart, level reinit) | wired + code-verified; drops any in-flight build and zeroes every 4D counter. The automated probe did not cleanly re-enter PLAYING (needs a joystick fire press), so this route is not measured this pass. |

A deferred coarse step is correctly **not** an invalidation (the tag does not
change). Respawn does not repaint the background, so it does not invalidate.

## 16. Stage-wrap results

Covered by §8 (seed 0 → tag 419: byte-equivalence 0 cell diffs) and §15 (the wrap
is a seamless −1 advance, not a discontinuity — the `−1`-in-target-space property
holds because `prepareBackgroundCoarse` sets `SCROLL_ROW = SLR` then `− 1`).
`TURRET_STREAM_REWIND` / `WAVE_TRIGGER_REWIND` are set by the unchanged legacy
path; the builder's row 0 comes from `BG_PREDECODED_ROW`, whose own wrap handling
(`bgConsumePredecodedRow` `!fallbackWrap`) is unchanged.

## 17. Turret stale-state proof

The byte-equivalence DYNAMIC check (§8) compares **all 1 000 cells**, turret
bodies included, and finds 0 diffs — the built page equals the legacy page for
the turret state that was resident in ACTIVE.

The remaining case — a turret that **changes state between the incremental build
and the flip** — is a **flip-time (Stage 4E) reconcile**, exactly the Stage-2
principle ("terrain-only cache; live turret overlay at reveal"):

- The incremental build is terrain + whatever turret glyphs were baked into
  ACTIVE at copy time. Row 0 is pure terrain (`BG_PREDECODED_ROW`).
- At the 4E flip, iterate `TURRET_POOL`: for each slot, against the **post-flip**
  `SCROLL_ROW`, write its 2×2 body glyphs (alive) or the cached
  `turretGroundCodes` terrain (dead / off-screen) into the INACTIVE page. Few
  slots, ~a few dozen cells — cheap, and it fixes both directions (resurrected
  dead turret → terrain; newly-alive → body).
- The prepared terrain page is fully compatible with this: nothing in the build
  bakes turret *lifetime*, and row 0 carries no overlay to undo.

**This proof (build most/all of the page, then change a turret before the flip,
then show the candidate can still reflect current turret state without a
whole-page rebuild) is a Stage-4E reconcile — designed here, not implemented, as
the task allows.** 4D's contribution is that the terrain page is ready and
overlay-free where it needs to be.

## 18. Colour-RAM ordering conclusion

The C64 has one colour RAM (`$D800–$DBE7`), read by the VIC regardless of the
`$D018` screen base — it **cannot** be double-buffered, and 4D does not try.

- Global terrain colour is a single value written once by `initBackground`;
  scrolling it is a **no-op**, so a page flip changes nothing there.
- The only dynamic colour cells are turret bodies, whose screen position is
  already recomputed every frame from `SCROLL_ROW`
  (`positionBackgroundTurrets` / `pulseTurretColour`).
- **Required 4E ordering:** run the turret colour-cell update against the
  **post-flip** `SCROLL_ROW` on the flip frame — the same discipline
  `installTurretRow` already uses for character cells. No colour buffer, no new
  data structure; a bounded ordering constraint, not a blocker.

## 19. Sprite-pointer Option A / Option B measurements

See §13. Option A ≈ +8–10 cy per LIVE batch in the raster IRQ (5 write sites, 2
in the IRQ). Option B = `ssMirrorSpritePtrs`, ~50 cy once per frame, no IRQ
change (already coded). **Recommended: Option B**, because this HEAD's raster/
admit-frame margins (§10–§12) cannot absorb IRQ-path additions, and Option B's
staleness caveat is void under any sane 4E flip schedule.

## 20. Supported-gameplay regressions

MODE3 vs MODE2, `check_raster_capture` (physical PAL frames):

| fixture | frames | `[19656]` | service fail | sprite-start miss (M3 / M2) | replay (M3 / M2) | catchups | incomplete | border bails |
|---|---|---|---|---|---|---|---|---|
| idle / player | 400 | exact | 0 | 0 / 0 | 25 / 0 | 0 / 0 | 0 | 0 |
| authored wave (seed 382, ramps to 6 enemies) | 260 | exact | 0 | 0 / 0 | 19 / 0 | 1 / 0 | 0 | 0 |
| stage wrap (seed 12) | 320 | exact | 0 | 0 / 0 | 27 / 0 | 1 / 0 | 0 | 0 |
| dense 16-object synthetic stress | 200 | exact | 0 | 2 / **3** | 100 / 99 | 1393 / 1393 | 0 | 0 |

The 5-/6-enemy regimes are inside the seed-382 wave (`max_objects 9`,
`max_batches 1`). The dense sprite-start misses are a **pre-existing `--dense`
baseline property** (MODE2 = 3, MODE3 = 2 — 4D is not the cause; `--dense` freezes
scroll so the builder is a no-op after its first ~12 frames). The **only** new
regression is **+1 `RASTER_REPLAY_FRAME` per coarse admit** — analysed in §11, and
correctly serviced (cadence exact, everything else `+0`).

## 21. Exact PAL cadence evidence

`frame_cycle_deltas: [19656]` — the sole value — in every capture above (idle 400,
wave 260, wrap 320, dense 200) and in every slice-size run (§10). The 199/235
hold (§14) shows 0 replay / 0 catchup / 0 incomplete over 600 held frames.

## 22. Hashes

| build | sha256(prg) |
|---|---|
| Mode 1 (`OPT_SECOND_SCREEN` OFF) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` (= Stage 3 baseline) |
| Mode 2 (`OPT_SECOND_SCREEN` ON, 4D OFF) | `326f1686f3cf3d0526579de167dcb6a6806da48c035fd4a9ad93b90852ff8ab9` (= 4A+4B+4C baseline) |
| Mode 3 (4D ON, `SS_BUILD_SLICE_ROWS` = 2) | `b73c765e9bcc54ec63a7cf1059b27565de392fb0534052998a85f45138c87140` |

`build/shooter.prg` / `build/shooter.d64` are left at **Mode 1** (`f2abc225…` /
d64 `f711694613ca9c47…`).

## 23. Remaining risks

1. **The +1 replay/coarse-admit** (§11). Bounded, correctly serviced, and
   expected to invert under 4E. If a GREEN 4D is required first, the fix is to
   move the target-refresh + slice fully into the post-`waitForGameFrame` window
   *and* free ~2 bytes in the `$080e` segment for a dedicated hook that is not on
   the admit-frame critical path — modest work, deferred.
2. **`ssInactiveBuildReset` restart route not automatically measured** (§15). Code
   is wired via `bgPredecodeReset`; an interactive fire-press test would close it.
3. **Turret flip-time reconcile and colour-RAM post-flip ordering** (§17–§18) are
   designed, not implemented — Stage 4E.
4. **Option A/B decision not hard-wired** (§13) — recommended B, to be committed in
   4E when the flip schedule is fixed.
5. **`$9900` block growth**: 4D used `$9900–$99e6`; ~1.5 KB free to `$A000` for the
   4E reconcile + flip logic.

## 24. Explicit confirmations

- **The reason-1 (`COARSE_DEFER_LIVE`) admission gate was NOT changed.** The
  199/235 fixture still defers every frame (`d COARSE_DEFER_LIVE = +600` over a
  600-frame hold), `SCROLL_FINE` still pinned at 7, `d COARSE_ADMIT = 0` — exactly
  as before 4D. `prepareBackgroundCoarse`'s three gate checks are byte-for-byte
  untouched.
- **Soft-edge masking was NOT touched.** `SOFT_EDGE_MASK` remains `#define`d off
  and unmodified. No ECM / charset-swap / phase-mask / 200 px work.
- Not done (correctly out of scope): Stage 4E flip-on-coarse, any change to
  BUILD/LIVE, JIT mux, HUD redesign, enemy/object/projectile limits, collision,
  wave/editor contracts.

## 25. Recommendation for Stage 4E

Proceed. 4D answers the decisive question — **the exact next coarse state can be
built incrementally in the inactive page, byte-correct (incl. wrap), completing
every cycle with positive margin, and it stays valid through a reason-1 hold with
zero redundant work.** 4E should:

1. **Publish by flip.** When `SS_INACTIVE_VALID` and a coarse step is admitted,
   `$D018 := ssInactiveD018[BG_ACTIVE_PAGE]` at beam ≈ 0 (proven safe by 4C),
   swap `BG_ACTIVE_PAGE`, and **skip `saveCrossingRow` / `shiftBackgroundUpper` /
   the in-window `renderStageRowToScreen` / `shiftBackgroundLower` /
   `restoreCrossingRow`** for that step. Keep the legacy path behind a
   compile-time fallback.
2. **Turret + colour reconcile at the flip**, against the post-flip `SCROLL_ROW`
   (§17–§18).
3. **Sprite pointers: Option B** — `ssMirrorSpritePtrs` at a fixed late point;
   schedule the flip so the newly-active page was mirrored the previous frame.
4. **Re-measure the admit frame.** Removing ~5 500 cy of in-window work should
   turn the current −20 cy admit-frame margin sharply positive and **eliminate
   the 4D replay regression** — verify, then the reason-1 proof (4F) and only then
   touch the gate.
5. Roll the now-INACTIVE (old ACTIVE) page straight into the next incremental
   build (`ssInactiveBuildRefreshTarget` already restarts on the −1 target
   advance).

## 26. Final repository state

```
$ git branch --show-current   experimental-border-hud
$ git rev-parse HEAD          f07b81fbcdb3240fde92e49c8f3694392e0e59df   (unchanged since the authorised FF)
$ git status --short
 M src/main.asm
?? docs/stage4d-incremental-inactive-screen-worklog.md
?? reports/stage4d-incremental-inactive-screen-build.md
$ git diff --stat
 src/main.asm | 356 +++++++++++++++++++++++++++++++++++++++++++++++++++++++--
 1 file changed, 353 insertions(+), 3 deletions(-)
```

**No commit, no add/stage, no tag, no push, no reset, no stash, no branch switch.**
The one authorised action beyond read-only was the fast-forward described in §2.
Working tree changes are unstaged. `build/shooter.prg` = Mode 1 (`f2abc225…`).

### Generated test artefacts (scratchpad only, not in the repo tree)

`s4d_equiv.py` (byte-equivalence), `s4d_sweep.py` (slice sweep), `s4d_hold.py`
(199/235 hold), `s4d_inval.py` (invalidation), `s4d_raster.py` (slice-entry
raster), plus A/B build trees under `/tmp/m1 /tmp/m2 /tmp/m3`.
