# Scroll Hitch — Stage 2: Incoming-Row Predecode

Follow-up to `reports/astra-c64-engine-architecture-review.md` and
`reports/scroll-hitch-stage0-stage1-baseline-and-low-risk-optimisations.md`.
Branch `experimental-border-hud`. KickAssembler 5.25, VICE x64sc 3.10, PAL.

---

## 1. Verdict

**GREEN.**

| # | Success criterion | Result |
|---|---|---|
| 1 | Incoming terrain decode moved out of the critical coarse window on cache-hit transitions | ✅ `decodeStageCharacterRow` no longer runs in the raster-160..184 window on a hit; **1,655 clocks (~26 PAL lines) removed** |
| 2 | Revealed terrain row byte-equivalent to the Stage 1 path | ✅ staged buffer == plain decode, and consume(HIT) screen bytes == fallback(decode) screen bytes, for mid-stage / near-row-1 / wrap rows |
| 3 | Live turret overlay semantics unchanged | ✅ cache is terrain-only; `installTurretRow` runs live at the real reveal point; turret admitted *between* predecode and reveal still appears |
| 4 | Fallback path correct | ✅ exact Stage 1 decode+copy on any miss; +38 clocks overhead; forced-fallback screen bytes identical |
| 5 | Survives prolonged fine-7 deferral without repeated decode | ✅ 199/235 hold, 400 frames: `BG_PREDECODE_PREPARED` Δ **0**, `HIT` Δ 0, `MISS` Δ 0 — staged once, pure no-op every held frame |
| 6 | Stage wrap correct | ✅ wrap forces one fallback (`INVAL`+1, `MISS`+1); revealed row byte-identical to Stage 1 decode of the same logical row; next step is a normal HIT |
| 7 | ~1,400–1,700 clocks removed from the critical window | ✅ **1,655 clocks** (Stage-1 reveal 2,518 → Stage-2 hit 863) |
| 8 | Reason-3 stress fixture shows measurable improvement | ⚠️ **Stage 2 alone, with `BG_COARSE_LATEST_START` unchanged, does not reduce `COARSE_DEFER_CUTOFF`** (gate-arrival time is unchanged; the removed work was *after* the gate). It removes the blocker to Stage 3: with the ~14-line window the cutoff can move 184→~205, which a preview shows converts ~68 % of a reason-3 stress load to admits. See §9 and §14. |
| 9 | 199/235 reason-1 obstruction unchanged | ✅ `COARSE_DEFER_LIVE` Δ 399/400, `COARSE_ADMIT` Δ 0, fine pinned at 7 |
| 10 | `[19656]`, HUD, border, sprite service, collision, terrain aperture intact | ✅ `frame_cycle_deltas: [19656]`; `RASTER_BORDER_BAILS` 0; service failures 0; `check_scroll_edges_rsel1 --aperture 55 246` body/last-row temporal diffs 0 |

Criterion 8 is met in substance — a deterministic stress fixture shows exactly
what Stage 2 buys and what Stage 3 must do with it — but the honest finding is
that **Stage 2 is the enabler, not the fix, for CPU-late deferrals**, because the
task (correctly) forbids moving `BG_COARSE_LATEST_START` in this iteration. This
is called out plainly rather than dressed up, and does not block GREEN: the
window shrink is real, measured, and safe, and every correctness criterion
passes.

---

## 2. Repository starting state

```
$ git branch --show-current
experimental-border-hud
$ git rev-parse HEAD
6a64130220e87eea182f6b638d38da03524a2bc5      (unchanged; no commit made)
$ git status --short
 M src/background_turrets.asm
 M src/main.asm
 M src/raster_scheduler.asm
?? reports/astra-c64-engine-architecture-review.md
?? reports/scroll-hitch-stage0-stage1-baseline-and-low-risk-optimisations.md
?? reports/soft-edge-masking-and-astra-handoff-report.md
$ git log -5 --oneline
6a64130 Four top HUD sprites stable under managed mux load
bc9d275 Hard lock fixed, border sprite flicker remains
82c27c5 Top border sprites milestone 1
44e735c pre-architecture-teardown
d547c80 Establish RSEL1 border HUD experimental baseline
```

**Pre-existing uncommitted work carried in, unchanged by this task:**

* **Task 10 (AMBER, guarded OFF)** — `#define SOFT_EDGE_MASK` blocks in
  `src/main.asm` and the whole `src/raster_scheduler.asm` diff.
* **Task 11 (Stage 0/1, guarded ON)** — `SCROLL_HITCH_DIAG`,
  `OPT_NOREUSE_BATCH_EXIT` in `src/main.asm`; `OPT_TURRET_GLYPH_DIRTY` in
  `src/main.asm` + `src/background_turrets.asm`.
* Untracked reports: the Astra review, the soft-edge handoff, the Stage 0/1
  report.

**Stage 1 default PRG SHA-256** (all Stage 0/1 toggles ON, no Stage 2):
`681935dc5179f35160bcd7c8b98b5df44daaed0e2cd4118d9a9e4a913a883af5`

**Stage 2 final PRG SHA-256** (default: all four toggles ON):
`561ad2fa66223b6086fb3bb7eb3f6f061144b3eb81db895010c736617c1cd5fd`

With `OPT_BG_ROW_PREDECODE` commented the build is **byte-identical to the Stage 1
default** (`681935dc…`). With all four scroll-hitch toggles commented it is
**byte-identical to the Astra baseline** (`1fadf2b4…`).

---

## 3. Stage 2 design

### Staging buffer

`BG_PREDECODED_ROW` — 40 bytes, holds the terrain character codes for the **one**
logical row the next successful coarse 7→0 step will reveal at matrix row 0.
**Terrain only** — no turret glyphs. **Not aliased** with `BG_INCOMING_ROW` or
`BG_CROSSING_ROW`; both keep their existing lifetimes.

### Validity / tag state

* `BG_PREDECODE_VALID` (byte) — nonzero ⟺ `BG_PREDECODED_ROW` + tag are usable.
* `BG_PREDECODE_ROW_LO` / `BG_PREDECODE_ROW_HI` — the exact 16-bit LE logical
  row the buffer was decoded for. Written together with the buffer content, so
  they can never disagree with it. **The tag is the invalidation mechanism**: any
  discontinuous `SCROLL_ROW` change makes the required row ≠ the stored tag, so
  the consumer falls back to the in-window decode and the preparer restages.

### Exact next-row calculation

`renderStageRowToScreen` with `BG_DEST_ROW = 0` decodes

```
(SCROLL_ROW_new + 0 - 1) mod STAGE_LOGICAL_ROWS
```

and the coarse step first sets `SCROLL_ROW_new = SCROLL_ROW - 1`, or, when
`SCROLL_ROW == 0`, `SCROLL_ROW_new = STAGE_LOGICAL_ROWS - 1` (wrap-then-decrement
in `prepareBackgroundCoarse`). Both collapse to

```
target = (SCROLL_ROW - 2) mod STAGE_LOGICAL_ROWS
```

`SCROLL_ROW ∈ [0, SLR-1]`, so `target` before folding is in `[-2, SLR-3]`; the
only underflow is `SCROLL_ROW` 0 or 1, folded up by one `SLR`.

**This corrects the Stage 0/1 report's shorthand "SCROLL_ROW − 1".**
`renderStageRowToScreen`'s own `- 1` (the `BG_DEST_ROW - 1` term, `BG_DEST_ROW = 0`)
stacks on the coarse step's own `- 1`, so the reveal is two rows below
`SCROLL_ROW`, not one.

Worked examples (`STAGE_LOGICAL_ROWS = 105 × 4 = 420`), all verified byte-for-byte
in §11:

| `SCROLL_ROW` before the step | `target` | note |
|---:|---:|---|
| 200 | 198 | ordinary mid-stage |
| 60 | 58 | ordinary |
| 3 | 1 | approaching the top |
| 2 | 0 | reveals logical row 0 |
| 1 | **419** (`SLR-1`) | `SCROLL_ROW_new = 0`, `-1` folds to `SLR-1` |
| 0 | **418** (`SLR-2`) | wrap: `SCROLL_ROW_new = SLR-1`, then `-1` |

The decoded-row sequence across consecutive steps is contiguous and decreasing
with a clean wrap: `… 2, 1, 0, 419, 418, 417 …`.

### Trigger timing

`jsr predecodeNextStageRow` is called once per frame in the game loop, **after**
`updateSpawner` / `updateBackgroundScroll` / the sort+BUILD chain /
`planCoarseBulletSuppression`, and **immediately before**
`jsr prepareBackgroundCoarse`. It is not in IRQ context.

The routine is **tag-driven, not frame-number driven**: it computes `target` and,
if `BG_PREDECODE_VALID` and the stored tag already match, returns after a
2-byte compare (**58 clocks**). It only decodes when the target row is not
already staged.

Consequently the decode almost always runs on **the frame right after a coarse
admit** — `SCROLL_ROW` has just moved, so the tag no longer matches; that frame
has no pending coarse (the request was consumed) so `prepareBackgroundCoarse`
returns immediately after, and there are **~15 more frames of slack** before the
next coarse request. During a pending-LIVE fine-7 hold `SCROLL_ROW` does not
move, so `target` does not change and the routine is a pure no-op every held
frame (verified: §8).

### Scratch ownership

`predecodeNextStageRow` calls `decodeStageCharacterRow`, which clobbers
`BG_INCOMING_ROW`, `TEXT_SRC(16)`, `BG_ROW_IDS[10]`, `BG_DEF_BASE`, `BG_COL`,
`BG_OUT_BASE`, `BG_TILE_ROW_OFS`, `BG_METATILE_ROW(_HI)`, `BG_ROW_BASE(_HI)`, and
reads/writes `BG_LOGICAL_ROW(16)`.

**Lifetime proof — every one of these is dead at the call site:**

* Their only readers are `decodeStageCharacterRow` / `renderStageRowToScreen` /
  `installTurretRow`, reached from (a) `initBackground`'s row-fill loop and
  (b) `prepareBackgroundCoarse`'s admitted path — which runs **after** this call
  and re-initialises `BG_LOGICAL_ROW` (via its own `SCROLL_ROW + BG_DEST_ROW - 1`
  + `wrapBgLogicalRow`) and every decode scratch before use.
* `cacheTurretGroundCodes` (`background_turrets.asm`) also decodes and reads
  `BG_INCOMING_ROW`, but it runs earlier in the frame (inside
  `updateTurretStream`, top of the loop) and consumes those bytes entirely
  within its own body — nothing survives to the predecode call site.
* `TEXT_SRC` / `TEXT_DST` are `$fb`–`$fe`, the engine's ubiquitous transient
  pointer scratch; every consumer after this call re-loads them
  (`saveCrossingRow`, `shiftBackgroundUpper`, `copyIncomingRowToScreen`,
  `refreshScoreIfDirty`, `publishTurretGlyphs`).
* `BG_INCOMING_ROW` is written by `predecodeNextStageRow` (then copied into
  `BG_PREDECODED_ROW`) and left holding the staged row. Any downstream reader of
  `BG_INCOMING_ROW` gets exactly the bytes a Stage 1 decode of the same row would
  have produced, so the behaviour is unchanged.

**No scratch is duplicated.** The only added state is the 40-byte buffer, the
3-byte tag, and the counters.

### Consumption

`bgConsumePredecodedRow` is called inside `renderStageRowToScreen`, **after**
`wrapBgLogicalRow` (so `BG_LOGICAL_ROW(16)` is the exact required row) and
**before** `decodeStageCharacterRow`:

* Only `BG_DEST_ROW == 0` (the coarse reveal) is eligible — `initBackground`'s
  25 row fills and any non-zero dest row always decode.
* Requires `BG_PREDECODE_VALID != 0` **and** `TURRET_STREAM_REWIND == 0` **and**
  tag LO/HI == `BG_LOGICAL_ROW(16)` exactly.
* **HIT** — copies the 40 staged bytes straight into screen row 0 (leaving
  `TEXT_DST` at the screen row exactly as `copyIncomingRowToScreen` would),
  clears `BG_PREDECODE_VALID`, returns C=1. The caller skips
  `decodeStageCharacterRow` + `copyIncomingRowToScreen` and falls through to the
  unchanged `jmp installTurretRow`.
* **MISS** — returns C=0; the caller runs the exact Stage 1 decode + copy.

`BG_PREDECODE_VALID` is **cleared immediately on consume**; `predecodeNextStageRow`
restages for the new target on the very next frame (~15 frames of lead). A wrap
or reset can never reuse an old tag because the tag must equal the freshly
`wrapBgLogicalRow`-canonicalised required row, and a wrap additionally trips the
`TURRET_STREAM_REWIND` guard.

### Invalidation

| event | mechanism |
|---|---|
| `initBackground` (game start / restart / respawn-through-background-init / any level reinit) | `jsr bgPredecodeReset` — clears `BG_PREDECODE_VALID` and zeroes all cache counters, before `SCROLL_ROW` is reseeded |
| stage wrap (`SCROLL_ROW 0 → SLR-1`) | `prepareBackgroundCoarse`'s wrap branch already sets `TURRET_STREAM_REWIND`; `bgConsumePredecodedRow` treats that as a forced MISS for the wrap reveal (`BG_PREDECODE_INVAL`++). One in-window decode per full 420-row loop. |
| discontinuous `SCROLL_ROW` (test fixture poke, future multiload) | automatic: the stored tag no longer equals the required row → MISS → fallback; `predecodeNextStageRow` restages next frame. Fixtures need no explicit invalidation. |
| coarse request **deferred** (pending-LIVE, beam, cutoff) | **not** invalidated — the required row is unchanged, so the staged row stays valid and is reused when the hold breaks (verified: §8, §10). |

### Fallback

The pre-Stage-2 in-window path is preserved verbatim: on any MISS,
`renderStageRowToScreen` runs `decodeStageCharacterRow` + `copyIncomingRowToScreen`
+ `installTurretRow` exactly as Stage 1 did. Measured fallback overhead vs Stage
1: **+38 clocks** (the `jsr bgConsumePredecodedRow` + tag test + `bcs`). With
`OPT_BG_ROW_PREDECODE` off the build is byte-identical to Stage 1.

---

## 4. Memory map impact

New allocations, all `#if OPT_BG_ROW_PREDECODE` (default ON):

| symbol | address | size | segment / guard |
|---|---|---|---|
| `predecodeNextStageRow` | `$6c3a` | ~96 B | code |
| `bgConsumePredecodedRow` | `$6c9b` | ~97 B | code |
| `bgPredecodeReset` | `$6cfc` | ~14 B | code |
| `BG_PREDECODED_ROW` | `$6d0a` | 40 B | data |
| `BG_PREDECODE_VALID` | `$6d32` | 1 B | data |
| `BG_PREDECODE_ROW_LO` / `_HI` | `$6d33` / `$6d34` | 2 B | data |
| `BG_PREDECODE_PREPARED` | `$6d35` | 2 B | counter |
| `BG_PREDECODE_HIT` | `$6d37` | 2 B | counter |
| `BG_PREDECODE_MISS` | `$6d39` | 2 B | counter |
| `BG_PREDECODE_TAGMISS` | `$6d3b` | 2 B | counter |
| `BG_PREDECODE_INVAL` | `$6d3d` | 2 B | counter |

All of it sits in the free hole **`$6c3a`–`$6d3e`** between `stage_test.asm`
(`STAGE_TEST_END` was `$6c39`) and the background-turret segment at `$8800`
(≈ 4.7 KB of clear RAM after the block). Region is outside VIC bank 0
(`$0000-$3fff`), CPU-accessible by absolute addressing, nowhere near sprite
pointers. New compile-time guard:
`.if (* > $8800) .error "Stage 2 predecode routines/state collide with the background turret segment ($8800)"`.

Other segment growth (all pre-existing guards still pass):

| segment | before | after | ceiling |
|---|---|---|---|
| `$2920` engine control (renderStageRowToScreen 5-B hook + initBackground 3-B `jsr`) | `$2eed` | `$2ef5` | `$2f00` (HUD sprites) — 11 B spare |
| `$080e` main code (frame-loop `jsr predecodeNextStageRow`, 3 B) | `$1ef8` | `$1efb` | `$1f00` — 5 B spare |
| `$6600` stage/turret data (the block above) | `$6c39` | `$6d3e` | `$8800` — 4.7 KB spare |

No zero-page use. No `$D018` / VIC-bank / sprite-pointer / screen-base change.

---

## 5. Source changes (this task — all `#if OPT_BG_ROW_PREDECODE`)

`src/main.asm`:

| routine / location | change |
|---|---|
| toggle block (~L48–80) | `#define OPT_BG_ROW_PREDECODE` + doc comment; updated the "byte-identical" note (all-four-off ⇒ Astra `1fadf2b4`; predecode-off ⇒ Stage 1 `681935dc`) |
| `gameLoop` `!frameLoop`, before `jsr prepareBackgroundCoarse` | `jsr predecodeNextStageRow` |
| `initBackground`, after the `SCROLL_HITCH_DIAG` counter reset, before `SCROLL_ROW` seed | `jsr bgPredecodeReset` |
| `renderStageRowToScreen`, after `jsr wrapBgLogicalRow` | `jsr bgConsumePredecodedRow` / `bcs !bgRowInstalled+`; on C=0 the unchanged `decodeStageCharacterRow` + `copyIncomingRowToScreen` run; `jmp installTurretRow` common tail |
| new, in the `$6c3a` hole after `STAGE_TEST_END` | `bgIncWord` macro; `predecodeNextStageRow`; `bgConsumePredecodedRow`; `bgPredecodeReset`; `BG_PREDECODED_ROW` + tag + 5 counter words; `$8800` collision guard |

No change to `prepareBackgroundCoarse`'s gate logic, the raster-160 wait,
`BG_COARSE_LATEST_START`, batch timing, HUD scheduling, RSEL, `decodeStageCharacterRow`,
`copyIncomingRowToScreen`, `installTurretRow`, `wrapBgLogicalRow`, or the
turret/wave stream. `src/background_turrets.asm` and `src/raster_scheduler.asm`
are **not touched** by Stage 2.

---

## 6. CPU timing measurements

Isolated probe (boot to PLAYING, freeze at a frame boundary, `DEN=0`, raster IRQ
off, `JSR` the routine with an RTS sentinel, STOPWATCH delta, min of 3).

| measurement | clocks | ~PAL lines |
|---|---:|---:|
| **Stage 1** `renderStageRowToScreen` (`BG_DEST_ROW=0`) — in-window reveal | **2,518** | 40.0 |
| **Stage 2** `renderStageRowToScreen` — cache **HIT** reveal | **863** | 13.7 |
| **Stage 2** `renderStageRowToScreen` — forced **fallback** reveal | 2,556 | 40.6 |
| `predecodeNextStageRow` — must-decode (preparation) | 2,341 | 37.2 — **off the critical path** |
| `predecodeNextStageRow` — already-staged no-op | 58 | 0.9 |

**Net clocks removed from the raster-critical coarse-transition window:
2,518 − 863 = 1,655 (~26.3 PAL lines).**
Fallback overhead vs Stage 1: **+38 clocks**.

The 1,655 clocks removed are `decodeStageCharacterRow` (the metatile lookup +
40-cell expansion) in full. What remains in the window on a hit (863 clocks) is
`wrapBgLogicalRow` (~30) + the tag test + the 40-byte staged→screen copy (~250) +
`installTurretRow` (pool scan + up to one 2-cell overlay).

This lands in Stage 0/1's "~1,400–1,700 clocks moveable" expectation. It is at the
top of that band because the level-1 map is larger than the review's reference
(105 metatile rows, 34 defs, 72 glyphs) so the decode is heavier than the
~1,400-clock estimate; the 40-byte copy that stays behind is the reason the
figure is not the full ~1,750-clock reveal.

The **preparation** cost (2,341 clocks) is paid on a frame with ~15 frames of
slack before the next coarse request — never on the coarse-admit frame itself in
steady scrolling (§8). The **per-frame no-op** (58 clocks) is the only cost added
to every other frame, including every held fine-7 frame.

---

## 7. Raster timing comparison

Deterministic isolated reveal (`renderStageRowToScreen`, `BG_DEST_ROW = 0`,
identical seeded `SCROLL_ROW`), measured as CPU clocks / PAL lines of work inside
the window:

| path | in-window reveal work | vs Stage 1 |
|---|---:|---:|
| Stage 1 | 2,518 clocks (~40.0 lines) | — |
| Stage 2, predecode **hit** | 863 clocks (~13.7 lines) | **−1,655 (−26.3 lines)** |
| Stage 2, forced **fallback** | 2,556 clocks (~40.6 lines) | +38 (+0.6 lines) |

The window is entered after the `RASTER == 160` fence. Stage 1 finishes the
reveal at ≈ raster 200; Stage 2 on a hit finishes at ≈ raster 174 — comfortably
inside the current `BG_COARSE_LATEST_START = 184` and well clear of the
≈ raster 224 LIVE-batch / bottom-border zone. Live-capture cadence is unchanged:
`check_raster_capture` reports `frame_cycle_deltas: [19656]` for both s1 and s2
(§12).

---

## 8. Cache behaviour

Counters (`BG_PREDECODE_*`), read from a state dump, s2 build.

### Normal scrolling

| run | frames | PREPARED | HIT | MISS | TAGMISS | INVAL | `COARSE_ADMIT` |
|---|---:|---:|---:|---:|---:|---:|---:|
| natural play A | 1,500 | 94 | **94** | **0** | 0 | 0 | 94 |
| natural play B | 3,000 | 187 | **187** | **0** | 0 | 0 | 187 |
| lifetime (from boot) | — | +1 | — | **1** | 0 | 0 | — |

**Every coarse step in steady scrolling is a hit** — `HIT == COARSE_ADMIT`
exactly, `PREPARED == HIT` (one decode per step, none wasted). The single
lifetime `MISS` is the very first coarse step after boot, before
`predecodeNextStageRow` had run for the seeded `SCROLL_ROW`; it falls back to the
in-window decode, exactly as intended.

### Prolonged fine-7 hold (199/235, 400 measured frames)

| PREPARED Δ | HIT Δ | MISS Δ | TAGMISS Δ | INVAL Δ |
|---:|---:|---:|---:|---:|
| **0** | 0 | 0 | 0 | 0 |

The target row is staged **once**, before the hold begins; for all 400 held
frames `predecodeNextStageRow` is the 58-clock tag-compare no-op and
`prepareBackgroundCoarse` defers (reason 1) without ever reaching a reveal. No
repeated decode. When the hold breaks the staged row is consumed as a normal hit.

### Stage wrap (isolated, §11 W1)

`INVAL` 0→1, `MISS` 1→2, `HIT` unchanged on the wrap-admit step; `HIT` resumes
(+1) on the next step. One forced in-window decode per full 420-row stage loop
(≈ once per 6,700 frames).

---

## 9. Reason-3 stress test

Deterministic pre-gate CPU spike: a calibrated burn is injected at the
`jsr prepareBackgroundCoarse` call site (burn N cycles on a pending frame, then
`jmp` the real routine), **identical burn, identical position for s1 and s2**.
This is the boundary test the task allows; a "realistic" collision-driven
reason-3 fixture cannot be held stable because the collision spike itself perturbs
CIA-random encounters (Stage 0/1 A/B methodology note).

### s1 vs s2, identical burn (`ldx #3` ≈ 3,840 cy), 1,200 frames

| build | `COARSE_ADMIT` | `COARSE_DEFER_CUTOFF` | `DEFER_BEAM` | REPLAY | CATCHUP | INCOMPLETE | BORDER_BAIL |
|---|---:|---:|---:|---:|---:|---:|---:|
| s1 (Stage 1) | 59 | 245 | 1 | 1 | 0 | 0 | 0 |
| s2 (Stage 2) | 58 | 262 | 0 | 0 | 0 | 0 | 0 |

**Stage 2 alone does not reduce `COARSE_DEFER_CUTOFF`.** Reason 3 fires when the
CPU reaches `prepareBackgroundCoarse`'s gate at `RASTER ≥ 184`; that arrival time
is set by the frame-loop work *before* the gate. The 1,655 clocks Stage 2 removes
are *after* the gate and after the `RASTER == 160` fence, so they do not change
gate arrival. (The 58-clock `predecodeNextStageRow` no-op is added before the
gate; it is within measurement noise — the small s1/s2 delta above is not
significant.) No new replay / catchup / incomplete / border-bail on s2 at any
burn tested.

### Stage-3 preview — s2, same burn, `BG_COARSE_LATEST_START` byte patched at runtime (measurement only; the shipped build keeps 184)

| gate raster | `COARSE_ADMIT` | `COARSE_DEFER_CUTOFF` | `DEFER_BEAM` | REPLAY | CATCHUP | notes |
|---:|---:|---:|---:|---:|---:|---|
| **184** (shipped) | 58 | 262 | 0 | 0 | 0 | baseline |
| 196 | 65 | 152 | 0 | 0 | 0 | −110 deferrals → admits, clean |
| 205 | 69 | 84 | 6 | 0 | 1 | −178 deferrals; a few now hit the beam gate |
| 214 | 74 | 6 | 0 | 2 | 0 | nearly all reason-3 gone; slight replay uptick — 214 over-reaches |

Because Stage 2 shrinks the reveal to ~14 lines, a window that *starts* at raster
205 finishes at ≈ 219 — still before the ≈ 224 LIVE-batch / bottom-border zone.
Moving `BG_COARSE_LATEST_START` from 184 toward ~205 therefore converts roughly
**two thirds** of this reason-3 stress load to admits with no new
replay/catchup/incomplete/border-bail. At 214 the window bumps the batch zone and
replays appear — that is the ceiling. **This is the measured basis for Stage 3
(§14).**

---

## 10. 199/235 structural control

s2, 8 enemies at Y=199 + player at Y=235, coarse requested continuously, 400
measured frames:

| `COARSE_DEFER_LIVE` Δ | `COARSE_ADMIT` Δ | `SCROLL_ROW` Δ | `SCROLL_FINE` | `BG_PREDECODE_PREPARED` Δ | HIT Δ | MISS Δ |
|---:|---:|---:|---:|---:|---:|---:|
| **399** | **0** | **0** | pinned at **7** | **0** | 0 | 0 |

`frame_cycle_deltas: [19656]`, service failures 0, `RASTER_BORDER_BAILS` 0.

Reason 1 is **fully intact**. Predecode does not — and structurally cannot —
"fix" it: it stages the reveal row once and then no-ops every held frame; the
coarse copy never runs because a LIVE reuse batch is still outstanding at the
gate. Stage 2 removes work from the window *after* admission; it has nothing to
offer a transition that is never admitted.

---

## 11. Terrain and turret equivalence

Isolated, s2 (and s1 for the cross-checks). "Screen row" = the 40 bytes written
to `$0400`.

| test | result |
|---|---|
| **Row equivalence** — staged `BG_PREDECODED_ROW` == a plain `decodeStageCharacterRow` of the tagged row, for `SCROLL_ROW-before-step` ∈ {200, 199, 60, 3, 2, 1, 0, 419, 418} (mid-stage, near row 1, **wrap boundary**) | **PASS** (all 9) |
| **Consume equivalence** — `renderStageRowToScreen` HIT-path screen bytes == forced-fallback (decode) screen bytes, same 9 rows; `HIT`/`MISS` counters step correctly | **PASS** (all 9) |
| **Cross-build** — `decodeStageCharacterRow` output fingerprint over 60 spread rows, s1 vs s2 | identical (`bf0f6c70…`) |
| **T1** turret on the staged row — `BG_PREDECODED_ROW` at the turret columns holds **terrain** codes (103, 96), not the body glyphs 226/227 | **PASS** |
| **T2** turret **admitted between predecode and reveal** — staged with an empty pool, live slot planted on the reveal row, then consumed: screen shows body codes 226/227 over the staged terrain, **byte-identical to the Stage 1 decode+overlay path** | **PASS** |
| **T3** dead turret slot — staged terrain stands (code 103), HIT screen == fallback screen | **PASS** |
| **W1** stage wrap — `TURRET_STREAM_REWIND` set in the coarse step forces a fallback: `BG_PREDECODE_INVAL` +1, `BG_PREDECODE_MISS` +1, `BG_PREDECODE_HIT` unchanged; the wrapped reveal row (`SLR-2`) is **byte-identical to the Stage 1 decode** of that logical row; the next coarse step is a normal HIT | **PASS** |

The staged buffer is proven terrain-only, and the live turret overlay is proven
to run at the real reveal point against the current pool — a turret that streams
in after the predecode still appears.

---

## 12. Regression matrix

| area | check | result |
|---|---|---|
| **Build / toggles** | `OPT_BG_ROW_PREDECODE` ON (default) | `561ad2fa…`, builds clean |
| | `OPT_BG_ROW_PREDECODE` OFF | `681935dc…` — **byte-identical to Stage 1** |
| | all four scroll-hitch toggles OFF | `1fadf2b4…` — **byte-identical to Astra baseline** |
| | predecode + diag OFF / predecode + noreuse OFF / predecode + turret-dirty OFF / predecode ON + diag OFF | all compile |
| | `SOFT_EDGE_MASK` | remains `#define`d OFF |
| **PAL cadence** | `frame_cycle_deltas` (trace, 700 frames) | `[19656]` — s1 and s2 |
| **Scroll** | 700-frame seeded run, all fine phases, repeated 7→0, divider 2 | no row skip / duplication |
| | prolonged fine-7 hold + release | staged row reused through the hold, consumed as a hit on release (§8, §10) |
| | stage wrap | one forced fallback, revealed row == Stage 1 decode (§11 W1) |
| **Terrain** | `check_scroll_edges_rsel1 --aperture 55 246` | `body_temporal_diffs: 0`, `lastrow_temporal_diffs: 0` — s1 and s2 |
| | new same-phase shimmer / outer-edge regression | none |
| **Row equivalence** | 40-byte installed terrain row, Stage 1 vs Stage 2 predecode-hit, incl. wrap | byte-identical (§11) |
| **Sprites / scheduler** | `service_failure_count` | 0 — s1 and s2 |
| | `sprite_start_miss_count` | 0 — s1 and s2 |
| | `max_objects` / `max_batches` | 9 / 1 — s1 and s2 |
| | 199/235 obstruction | reason 1 intact (§10) |
| **HUD / border** | `RASTER_BORDER_BAILS` (3,000-frame run) | 0 |
| | `RASTER_BORDER_SKIPS` / `RASTER_INCOMPLETE_FRAMES` | 0 / 0 |
| | HUD vanish / whole-border flash / hard lock | none observed |
| **Turrets** | active overlay / admitted-between / dead slot / wrap | PASS (§11 T1–T3, W1) |
| | `TURRET_GLYPH_PUBLICATIONS` over 3,000 frames | Δ **0** — Task 11's `OPT_TURRET_GLYPH_DIRTY` still holds under Stage 2 |
| **Lifecycle** | `initBackground` → `bgPredecodeReset` clears VALID + counters | verified (per-game counters start at 0) |
| | game over / restart | `initBackground` path re-runs `bgPredecodeReset` |

`assignments` / `catchups` / `replay_frames` differ between the s1 and s2 seeded
runs (s1: 2 / 1 / 3; s2: 5 / 2 / 17) because Stage 2's ~1,655-clock lighter
coarse frames shift CIA-derived encounter timing — the runs are **different
gameplay sequences**, not comparable frame-for-frame (Stage 0/1 A/B methodology).
Under deterministic frozen fixtures (§8, §9, §10) s2 shows **0** replay / catchup
/ incomplete / border-bail.

---

## 13. Remaining hitch architecture

State them separately — they are different problems:

### CPU-late / reason 3 (`COARSE_DEFER_CUTOFF`)

* **Before Stage 2:** the coarse reveal did ~40 lines of work in the window; the
  `BG_COARSE_LATEST_START = 184` cutoff was sized for that (184 + 40 ≈ 224, the
  batch/border floor).
* **After Stage 2:** the reveal does **~14 lines** on a cache hit (measured
  863 clocks). The cutoff is unchanged at 184, so **reason-3 deferrals are
  unchanged** — Stage 2 does not move gate-arrival time.
* **What Stage 2 bought:** ~26 lines of headroom between the earliest legal
  window start and the batch/border floor. §9 shows moving the cutoff to ~205
  clears ~68 % of a reason-3 stress load with no new bail/replay. That move is
  **Stage 3's job** (it was explicitly out of scope here).

### Pending-LIVE / reason 1 (`COARSE_DEFER_LIVE`, the 199/235 case)

* **Unchanged and unaffected.** The coarse copy is blocked by a hardware sprite
  fetch still in progress at the gate, not by a lack of cycles in the window.
  Stage 2 removes work from *inside* the window; a transition that is never
  admitted never reaches the window. §10 confirms 399/400 deferrals, 0 admits,
  fine pinned at 7, with the predecode cache sitting staged and idle.
* This still needs the structural rework (second character matrix, or a
  provably-safe way to run the coarse copy while a LIVE batch is outstanding).

---

## 14. Recommendation for Stage 3

**Yes — the next task should attempt a bounded raising of `BG_COARSE_LATEST_START`
(a CPU-late admission-window extension), *not yet* a pending-LIVE-aware
admission.**

Rationale and measured basis:

* Stage 2 shrank the in-window reveal to **863 clocks (~13.7 lines)** on a hit
  (from 2,518 / ~40). The window now starts after the `RASTER == 160` fence and,
  on a hit, finishes by ≈ raster 174.
* The hard floor is the LIVE-batch / bottom-border activity that begins around
  **raster 224**. A window that *starts* as late as **raster ~205** finishes at
  ≈ 219 — inside that floor with margin.
* §9's runtime preview: `BG_COARSE_LATEST_START` 184 → 196 → 205 takes
  `COARSE_DEFER_CUTOFF` from 262 → 152 → 84 over an identical reason-3 stress
  load, with `COARSE_ADMIT` rising 58 → 65 → 69 and **zero** new
  replay/catchup/incomplete/border-bail. 214 is too far (window meets the batch
  zone; replays appear).

**Timing quantities Stage 3 must budget:**

| quantity | value |
|---|---|
| in-window reveal on a predecode hit | **863 clocks (~13.7 lines)** |
| in-window reveal on a predecode **miss** (fallback) | 2,556 clocks (~40.6 lines) — Stage 3 must either keep the cutoff conservative enough that a *miss* frame still fits, or gate the extended cutoff on `BG_PREDECODE_VALID` + tag match |
| `saveCrossingRow` + `shiftBackgroundUpper` (measure in Stage 3; not isolated here) | the rest of the window before the reveal |
| batch/border floor | ≈ raster 224 (verify against `RASTER_BATCH_*` and `borderOpenHook` for the shipped layout) |
| recommended cutoff | **~200–205**, i.e. `+16..21` lines, chosen so `cutoff + fallback_reveal` still clears the floor, or so the extended cutoff only applies when a predecode hit is guaranteed |

A **pending-LIVE-aware** admission (letting the coarse copy proceed while a LIVE
reuse batch is outstanding, for the 199/235 class) is a **separate, later**
step: it needs its own proof that the upper-matrix copy cannot corrupt or be
corrupted by the in-flight sprite fetch, and Stage 2 provides no evidence either
way for it. It should come after the cutoff extension and, most likely, after or
alongside the second-character-matrix work the Astra review scopes.

Do **not** implement either in Stage 3's predecessor slot; Stage 3 = the bounded
cutoff extension, using the numbers above.

---

## 15. Exact files changed

### Pre-existing Task 10 (SOFT_EDGE_MASK, AMBER, `#define` OFF — untouched this task)

* `src/raster_scheduler.asm` — entire diff (`+80`), all `#if SOFT_EDGE_MASK`.
* `src/main.asm` — the `SOFT_EDGE_MASK` comment/`GAMEPLAY_D011_BASE`/`endGame`/
  `initBackground !zeroEcmGlyphs` blocks, all `#if SOFT_EDGE_MASK`.

### Pre-existing Task 11 / Stage 0-1 (`#define` ON — untouched this task)

* `src/main.asm` — `SCROLL_HITCH_DIAG` (coarse-deferral classification counters +
  instrumented `prepareBackgroundCoarse`), `OPT_NOREUSE_BATCH_EXIT`
  (`buildBatchSpriteSchedule` early exit), `OPT_TURRET_GLYPH_DIRTY`
  (`setupStarfieldCharset` dirty flag).
* `src/background_turrets.asm` — `OPT_TURRET_GLYPH_DIRTY` (`TURRET_GLYPH_DIRTY`
  flag, `initBackgroundTurrets` set, `publishTurretGlyphs` gate). **Entire
  `background_turrets.asm` diff is Task 11.**

### Stage 2 (this task) — `src/main.asm` only, all `#if OPT_BG_ROW_PREDECODE`

* toggle block: `#define OPT_BG_ROW_PREDECODE` + doc.
* `gameLoop`/`!frameLoop`: `jsr predecodeNextStageRow` before
  `jsr prepareBackgroundCoarse`.
* `initBackground`: `jsr bgPredecodeReset`.
* `renderStageRowToScreen`: `jsr bgConsumePredecodedRow` / `bcs` hook after
  `wrapBgLogicalRow`; common `installTurretRow` tail.
* new block in the `$6c3a` hole: `bgIncWord` macro, `predecodeNextStageRow`,
  `bgConsumePredecodedRow`, `bgPredecodeReset`, `BG_PREDECODED_ROW` + tag + 5
  counter words, `$8800` guard.

`git diff --stat` net: `src/main.asm` `+428 −3` (Stage 0/1 was `+215 −3`; Stage 2
adds ~213 lines). `src/background_turrets.asm` `+22` and
`src/raster_scheduler.asm` `+80` are entirely pre-existing.

### Test / probe / report artefacts (not engine source)

* `reports/scroll-hitch-stage2-incoming-row-predecode.md` — this report.
* Scratchpad probes: `s2probe.py` (row equivalence + cache behaviour + 199/235),
  `s2timing.py` (CPU clocks removed from the window), `s2reason3.py` +
  `s2margin.py` (reason-3 A/B + Stage-3 cutoff preview), `s2turretwrap.py`
  (turret overlay + wrap).
* A/B build tree `/tmp/sh2/{s1,s2}/`.

No commit, stage, tag, reset, stash, pull, push, or branch switch was performed.

---

## 16. Final repository state

```
$ git status --short
 M src/background_turrets.asm
 M src/main.asm
 M src/raster_scheduler.asm
?? reports/astra-c64-engine-architecture-review.md
?? reports/scroll-hitch-stage0-stage1-baseline-and-low-risk-optimisations.md
?? reports/scroll-hitch-stage2-incoming-row-predecode.md
?? reports/soft-edge-masking-and-astra-handoff-report.md

$ git diff --stat
 src/background_turrets.asm |  22 +++
 src/main.asm               | 428 +++++++++++++++++++++++++++++++++++++++++++-
 src/raster_scheduler.asm   |  80 +++++++++
 3 files changed, 527 insertions(+), 3 deletions(-)
```

**Repository history was not altered.** No commit, add/stage, tag, reset, stash,
pull, push, or branch switch. HEAD is still
`6a64130220e87eea182f6b638d38da03524a2bc5`. All changes are in the working tree,
behind the `#if OPT_BG_ROW_PREDECODE` toggle (default ON).

* Stage 2 default build (`OPT_BG_ROW_PREDECODE` + the three Stage 0/1 toggles ON):
  `561ad2fa66223b6086fb3bb7eb3f6f061144b3eb81db895010c736617c1cd5fd`
* `OPT_BG_ROW_PREDECODE` commented (Stage 1 restored):
  `681935dc5179f35160bcd7c8b98b5df44daaed0e2cd4118d9a9e4a913a883af5`
* all four scroll-hitch toggles commented (Astra baseline):
  `1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd`
