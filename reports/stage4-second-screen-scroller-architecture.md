# Scroll Hitch — Stage 4: Second Character-Screen Scroller Architecture

Experimental follow-up to Stages 0–3 (`stable-single-screen-scroller`). Branch
`experimental-border-hud`. KickAssembler 5.25, VICE x64sc 3.10, PAL.

---

## STAGE 4J UPDATE — ARCHITECTURE PROMOTED TO DEFAULT, STAGE 4 CLOSED

Everything below this notice is the original Stage 4A-4C investigation
report, kept as-is for historical/archaeological accuracy — including its
"experimental" framing and its (superseded) description of 4D-4F as "not
implemented". **It no longer describes the current state of the codebase.**

The work this report proposed was carried out and proved across Stages
4D-4I, and the resulting architecture was promoted to the **normal default
build** in Stage 4J:

- Stage 4D built the incremental inactive-page terrain construction this
  report designed in §9 — `/reports/stage4d-incremental-inactive-screen-build.md`
- Stage 4E published coarse steps as a `$D018` flip instead of the legacy
  in-window matrix mutation — `/reports/stage4e-d018-coarse-publication.md`
- Stage 4F relaxed reason 1 (pending-LIVE defer) for the proven flip path —
  `/reports/stage4f-pending-live-scroll-proof.md`
- Stage 4G made the raster test oracle page-aware and bounded the builder's
  load — `/reports/stage4g-pending-live-scroller-cleanup.md`
- Stage 4H found and repaired a real pointer-mirror defect discovered by that
  oracle in the reason-1-intact fallback configuration —
  `/reports/stage4h-mode-b-pointer-repair-and-rebaseline.md`
- Stage 4I gave a full causal, cycle-level account of the remaining
  synthetic-stress (`--dense`) sprite-start misses and accepted them as a
  pre-existing VIC badline/deadline-line coincidence, not a scroller defect
  — `/reports/stage4i-dense-per-flip-investigation.md`
- Stage 4J made the proven configuration (`OPT_SECOND_SCREEN` +
  `OPT_SS_INACTIVE_BUILD` + `OPT_SS_FLIP_COARSE` +
  `OPT_SS_ALLOW_PENDING_LIVE_FLIP`, all on) the source default, confirmed the
  ordinary build reproduces the accepted binary
  (`80d5b0461c070fe23d6e5dbcb2124eb9e4093dbbc4034464d9afe0596f08ce66`)
  byte-for-byte, and re-ran the full regression suite against it.

**Stage 4 double-buffered scrolling is CLOSED.** The double-buffered,
page-flip-published, pending-LIVE-tolerant, page-aware-pointer scroller is
now the normal production architecture — see `AGENTS.md`'s "Current
scrolling architecture" section for the current, maintained summary. The old
single-screen architecture this report's §2 baseline describes (and the
Stage 4D+4E-only, reason-1-intact configuration) remain available as
regression/reference/diagnostic fallbacks, not the normal build. Checkpoint
tags: `stable-single-screen-scroller` (pre-Stage-4),
`stable-double-buffered-scroller` (original Stage 4D+4E checkpoint —
archaeological, includes a since-repaired pointer defect),
`stable-double-buffered-scroller-v2` (the accepted, corrected architecture
this closure describes).

---

## 1. Executive verdict

**GREEN for sub-stages 4A, 4B and 4C. Sub-stages 4D–4F are designed but NOT
implemented** — the safely-proven boundary this pass, as the task sanctions.

* **4A — memory-map relocation:** GREEN. The CPU-only curated-attack / movement
  fragment tables (`$2700–$290E`) and the whole background-control code+state
  block (`$2920–$2EEE`) relocate cleanly to `$9000+`, freeing a contiguous
  `$2700–$2EFF` window in VIC bank 0. Byte-identical when the toggle is off;
  behaviourally transparent when on (`[19656]`, 0 service failures, 0 sprite
  misses, terrain temporally clean, 9k-frame natural run + stage wrap identical
  to Stage 3).
* **4B — allocate + initialise page B:** GREEN. Screen B occupies the freed
  `$2800–$2BFF`. Derived `$D018` = `$AE` (page A `$1E`), verified. `ssInitPageB`
  seeds page B with a full copy of the painted page A at `startGame`.
* **4C — `$D018` page-flip proof (identical contents):** GREEN. 6,000
  frame-boundary flips between page A and page B, both matrices held identical:
  `RASTER_BORDER_BAILS`, `RASTER_REPLAY_FRAMES`, `RASTER_INCOMPLETE_FRAMES`,
  `RASTER_CATCHUPS` all **+0**; physical-frame count exactly 1:1; per-frame
  sprite-batch service never short; screenshots on a page-A frame and a page-B
  frame **pixel-identical** when synced, and correctly different when page B is
  deliberately desynced. Flipping the screen base does not destabilise the
  raster chain, the mux, the top-border HUD or the exact PAL cadence.

**4D–4F not done.** The structural reason-1 (`COARSE_DEFER_LIVE`) obstruction is
therefore **unchanged** — the 199/235 fixture still pins fine phase at 7, exactly
as in Stage 3. That is the expected, correct state for the completed sub-stages:
4A–4C do not touch the coarse-admission path.

### The central question

> Does preparing the next coarse-scroll state in a second, inactive character
> screen matrix safely remove the structural pending-LIVE scroll obstruction
> without destabilising the HUD, multiplexer, terrain semantics or exact PAL
> cadence?

**Answer (partial, evidence-backed): the *mechanism* is safe. The relocation is
transparent (4A); a second 1 KB page fits VIC bank 0 (4B); and switching `$D018`
between the two pages at a frame boundary is provably stable for the HUD, mux,
border and cadence (4C). What is NOT yet proven is that the *next coarse state
can be built in the inactive page in time*: a full 1 KB matrix rebuild is
~11,000 cycles and does not fit any single PAL frame's non-visible window
(~3,000 cy before the first badline, ~6,000 cy in vertical blank). Removing the
reason-1 gate therefore requires spreading the inactive-page construction across
the ~8 fine-scroll frames between coarse steps (4D), which must be built and
cost-characterised before the gate can be changed. Sub-stages 4A–4C de-risk the
approach; 4D is the decisive next bounded step.**

---

## 2. Starting repository state

```
$ git branch --show-current
experimental-border-hud
$ git rev-parse HEAD
223a8201bbc55c5c751a9683e22e284143cc0644          (tag: stable-single-screen-scroller; unchanged)
$ git status --short
                                                   (clean)
$ git log -3 --oneline
223a820 Stabilise single-screen scroller under mux load
6a64130 Four top HUD sprites stable under managed mux load
bc9d275 Hard lock fixed, border sprite flicker remains
$ git diff --stat
                                                   (empty)
```

The Stage 0–3 scroll-hitch work and the Task 10/11 work are committed in
`223a820` and tagged `stable-single-screen-scroller`.

| build | SHA-256 |
|---|---|
| **Stage 3 baseline** (= current HEAD, all Stage 0–3 toggles ON) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` |
| **Stage 4 default** (`OPT_SECOND_SCREEN` commented) | `f2abc225159e81bf…` — **byte-identical to the Stage 3 baseline** |
| Stage 4 experimental (`OPT_SECOND_SCREEN` + 4A+4B+4C on) | `326f1686f3cf3d05…` |
| 4A only (relocation, no page B) | `3d7849ed99903f64…` |
| 4A + 4B (page B allocated, no flip) | `336a5c5a288e9f08…` |

`git status --short` at the end: `M src/main.asm` (all additions behind
`#if OPT_SECOND_SCREEN`). History not altered.

---

## 3. Sub-stages completed

| stage | status | what it proves |
|---|---|---|
| **4A** memory-map audit + relocation | **GREEN** | the `$2800–$2BFF` region can be freed with no behaviour change |
| **4B** allocate + init page B (never displayed) | **GREEN** | a second 1 KB VIC-visible page exists and holds a valid copy of page A; `$D018` values derived + verified |
| **4C** `$D018` A↔B flip with identical contents | **GREEN** | the flip mechanism is raster-safe: HUD, mux, border, cadence, sprite service all stable |
| **4D** build next coarse state in the inactive page | not done | — (design in §9) |
| **4E** flip on the coarse step instead of mutating the visible matrix | not done | — |
| **4F** structural reason-1 proof (199/235 scrolls) | not done | — |
| **4G** performance characterisation | partial (§8) | flip cost measured; inactive-page build cost is the open question |

---

## 4. Memory-map before / after

VIC bank 0 is `$0000–$3FFF`. Every 1 KB-aligned slot in the bank was occupied
before Stage 4; there was **no** free VIC-visible 1 KB page without relocation.

| region | before (Stage 3) | after (`OPT_SECOND_SCREEN` on) | note |
|---|---|---|---|
| `$0400–$07FF` | Screen A + sprite-ptr table `$07F8` | **unchanged** — Screen A stays displayed | |
| `$080E–$1EFB` | main code | `$080E–$1EFE` (+3 B: `jsr ssInitPageB` in `startGame`) | fits below `$1F00` |
| `$1F00–$1FFF` | lookup tables + border-marker sprite | unchanged | |
| `$2000–$23FE` | protected engine-state block (`OBJECT_*`, `BATCH_*`, `INITIAL_*` …) | **unchanged** — deliberately not relocated | `raster_scheduler.asm:705` notes this layout is protected |
| `$2400–$26FF` | sprite bitmaps (`playerSprite` … `enemyBulletSprite`, 12 × 64 B) | **unchanged** — these are VIC-visible, cannot leave bank 0 | |
| `$2700–$290E` | curated-attack + ingress/manoeuvre/egress fragment tables | **FREED** (relocated to `$9000`) | CPU-only movement/timing data |
| `$290F–$291F` | (17-byte gap) | free | |
| `$2920–$2EEE` | background-control code + coarse state (`applyFineScroll`, `initBackground`, `renderStageRowToScreen`, `decodeStageCharacterRow`, `updateBackgroundScroll`, `prepareBackgroundCoarse`, `finishBackgroundCoarse`, `planCoarseBulletSuppression`, `BG_COARSE_*`, `COARSE_DEFER_*`, `SUPPRESS_*`, `ENCOUNTER_POLICY_*`, `updateTurretPressure` …) | **FREED** (relocated to `$9280`) | CPU-only code + state, never VIC-fetched |
| **`$2800–$2BFF`** | (was fragment data + bg code) | **`bgScreenB` — the second 1 KB screen page** (sprite-ptr table at `$2BF8`) | |
| `$2700–$27FF`, `$2C00–$2EFF` | | now free / unclaimed | ~768 B recoverable later |
| `$2F00–$2FFF` | HUD sprite bitmaps | unchanged | |
| `$3000–$33FF` | health sprite pool | unchanged | |
| `$3400–$37FF` | clip sprite pool | unchanged | |
| `$3800–$3FFF` | charset (`STAR_CHARSET`) | unchanged — **both pages use this charset** | |
| `$8800–$8FDF` | `background_turrets.asm` | unchanged | |
| `$9000–$920E` | — | **relocated attack/fragment tables** (527 B) | outside VIC bank 0; `$8000–$9FFF` is always RAM on a stock C64 |
| `$9280–$984E` | — | **relocated background-control code + state** (1,487 B) | |
| `$9900–$995D` | — | Stage 4 support routines (`ssInitPageB`, `ssMirrorSpritePtrs`, `ssFlipPage`) + diag bytes | |

Compile-time guards added: attack data must not overrun the relocated bg segment
or `$A000`; bg-control end must not overrun `$A000`; page B must be 1 KB-aligned,
inside VIC bank 0, and inside the freed `$2700–$2EFF` window; Stage 4 code must
not overrun `$A000`.

---

## 5. Exact relocated regions and why

### What moved

| block | from | to | size | reason it is safe to move |
|---|---|---|---|---|
| curated-attack tables + movement fragments (`attackEnemyCount` … `egressFragmentsEnd`) | `$2700–$290E` | `$9000` | 527 B | CPU-only. Read by `updateSpawner` / the path-fragment interpreter as absolute or absolute-indexed loads. Never a sprite bitmap, screen cell or charset byte — the VIC never fetches from here. Every reference is a symbolic label, so the address is transparent. |
| background-control code + coarse state (`applyFineScroll` … `countActiveEnemies`, `BG_COARSE_*`, `COARSE_DEFER_*`, `SUPPRESS_*`, `ENCOUNTER_POLICY_*`) | `$2920–$2EEE` | `$9280` | 1,487 B | CPU-only executable code + engine state. `jmp`/`jsr` reach anywhere in the 64 KB space; absolute `lda/sta` on the state is address-transparent. Audited: **no** self-modifying code, **no** indirect jump with a hard-coded target, **no** `.const X = $29xx` besides the segment directive itself, **no** cross-file (`raster_scheduler.asm`, `background_turrets.asm`, generated level files) hard-coded `$29xx`/`$2Axx`/`$2Bxx` reference. All 17 call sites are `jsr <name>`. |

### What did NOT move, and why

* `$2400–$26FF` sprite bitmaps — VIC-visible, referenced by sprite pointers
  (`playerSprite / 64` …). Cannot leave VIC bank 0.
* `$2000–$23FE` engine-state block — a protected layout; the object arrays are
  heavily absolute-indexed and page-adjacency-sensitive; moving it is higher
  risk than moving the background block and is unnecessary (it does not overlap
  `$2800–$2BFF`).
* the charset (`$3800`), the sprite pools (`$2F00`, `$3000`, `$3400`) — VIC-visible.

### Why `$9000`

`$8000–$9FFF` is unconditionally RAM on a stock C64 (no cartridge; the game never
touches the `$01` processor port, so `$A000`/`$E000` stay ROM but `$8000–$9FFF`
is RAM regardless). It is outside VIC bank 0, so the VIC in bank 0 never fetches
from it — perfect for CPU-only code/data. `background_turrets.asm` already lives
at `$8800`; the relocation slots in above it with room to `$A000` (~5.5 KB used
of the ~8 KB `$8000–$9FFF` window).

### Regression evidence (4A)

| check | Stage 3 baseline (off) | 4A+4B+4C (on) |
|---|---|---|
| build SHA-256, toggle off | `f2abc225159e81bf…` | `f2abc225159e81bf…` (identical) |
| `frame_cycle_deltas` (trace, 1,400 frames) | `[19656]` | `[19656]` |
| `service_failure_count` / `sprite_start_miss_count` | 0 / 0 | 0 / 0 |
| `check_scroll_edges_rsel1 --aperture 55 246` | `body 0 / lastrow 0` | `body 0 / lastrow 0` |
| 9,000-frame natural run (crosses a stage wrap) | ADMIT 562, CUT 2, LIVE 1, HIT 561, MISS 1, REP 2, INC 0, BAIL 0 | ADMIT 563, CUT 1, LIVE 3, HIT 562, MISS 1, REP 2, INC 0, BAIL 0 |
| 199/235 control | `dLIVE 396, dADMIT 0, fine pinned 7` | `dLIVE 396, dADMIT 0, fine pinned 7` |

The small A/B differences (ADMIT 562↔563, LIVE 1↔3, CUT 2↔1) are CIA-derived
encounter-timing jitter between otherwise-equivalent runs — the same "different
gameplay sequence" effect noted in the Stage 0–3 reports. The deterministic
signals (cadence, service, terrain cleanliness, reason-1) are identical.

---

## 6. Chosen screen B address and derived `$D018`

* **Screen B base: `$2800`** (1 KB-aligned; inside VIC bank 0; inside the
  `$2700–$2EFF` window freed by 4A).
* **`$D018` derivation** — `$D018` bits 7–4 select the screen base as
  `n × $400` within the VIC bank; bits 3–1 select the char base as
  `m × $800` (charset stays at `$3800` ⇒ `m = 7` ⇒ bits `1110`); bit 0 is
  unused by the VIC and **reads back as 1** on real hardware.
  * Page A: screen `$0400` ⇒ `n = 1` ⇒ `0001` ⇒ `$D018 = $1E` (matches the
    value `init` already writes: `and #%11110000 / ora #%00001110`).
  * Page B: screen `$2800` ⇒ `n = $0A` ⇒ `1010` ⇒ **`$D018 = $AE`**.
* **Verified in emulation:** writing `$1E` reads back `$1F`; writing `$AE` reads
  back `$AF` (bit 0 forced to 1). Masked (`& $FE`) the values are exactly
  `$1E` / `$AE`. The VIC ignores bit 0, so `$1E`/`$1F` and `$AE`/`$AF` are
  equivalent. Astra's earlier `$1E` / `$AE` guess is therefore confirmed for
  this charset layout and VIC bank.

Both pages share the one charset at `$3800` — no `$D018` char-base change on a
flip, only the screen nibble.

---

## 7. Sprite-pointer-table handling

Each screen page owns its own 8-byte hardware sprite-pointer table at
`page_base + $3F8`:

* page A: `$07F8` (this is exactly the existing `HW_SPRITE_POINTER` `.var`).
* page B: `$2BF8` (`BG_SPRITE_PTRS_B`).

The five sites that write sprite pointers were audited:

| site | context | frequency |
|---|---|---|
| `renderSprites` (`main.asm`) | main thread, frame top | every frame |
| `hudBorderSetup` (`main.asm`, from `rasterFrameReset`) | frame top / IRQ-adjacent | every frame |
| `hudBorderHandoff` region (`main.asm`) | main thread | every frame (HUD slots reclaimed) |
| `applyLiveRasterBatch` (`raster_scheduler.asm`) | **raster IRQ**, mid-frame | per LIVE reuse batch |
| border-marker install (`raster_scheduler.asm`) | **raster IRQ** | per frame (`BORDER_PROOF_ENABLE`) |

**For the 4C proof** the eight bytes `$07F8–$07FF` are copied to `$2BF8–$2BFF`
once per frame (monitor block copy; `ssMirrorSpritePtrs` in the engine does the
same in ~50 cy). With the game frozen and the two matrices held identical this
is exact; with the game running it leaves page B's pointer table one frame
stale, which is coherent (not corrupt) for a static-content proof.

**For 4D–4F (running double-buffer)** two options, to be measured in 4G:

1. **Dual write** at all five sites (`sta HW_SPRITE_POINTER,x` → also
   `sta BG_SPRITE_PTRS_B + <same offset>,x`). +1 instruction each; the two IRQ
   sites add ~8–10 cy to the raster hot path per batch — needs a measured
   verdict against the frame budget.
2. **8-byte mirror** after every write is known-complete for the frame (late in
   the game loop, ~50 cy, no IRQ change) — but then the *displayed* page's
   pointer table is a frame behind on the frame it is first displayed, which is
   only acceptable if the flip is scheduled so the newly-active page was the
   *inactive* page last frame and its pointers were mirrored then.

The 4C evidence (below) shows both tables staying correct under constant
flipping; the open question is purely the running-cost trade-off.

---

## 8. Colour RAM strategy

The C64 has **one** colour RAM at `$D800–$DBE7`, read by the VIC regardless of
which screen base `$D018` selects. It is **not** double-buffered and cannot be.

Current engine usage:
* `initBackground` fills all of `$D800–$DBE7` with the single global
  `TERRAIN_COLOUR_RAM` value once per game.
* The scroller **never** touches colour RAM (terrain colour is one global value;
  the fine/coarse shift moves only character codes).
* `initFixedHud` overwrites row 0 (the HUD) once.
* Turret hit flash (`pulseTurretColour`) and dead-cell restoration write the
  specific colour-RAM cells covering a turret's 2×2 body **at its current screen
  position**.

**For 4C (identical content):** colour RAM is inherently shared and position-
stable, so a flip between two matrices holding the same codes renders identically
— confirmed: the page-A-frame and page-B-frame screenshots are **pixel-identical**
(colour included) when the matrices are synced.

**For 4D–4F:** when the coarse step is published by a page flip instead of a
matrix mutation, colour RAM must already reflect the *new* view. Two facts help:
(a) terrain colour is a single global value, so scrolling it is a no-op; (b) the
only *dynamic* colour cells are the turret bodies, whose screen position the
turret code already recomputes each frame from `SCROLL_ROW`
(`positionBackgroundTurrets` / `pulseTurretColour`). The design requirement
(§9) is that the turret colour-cell writes for frame N target the row offsets
that will be correct *after* frame N's flip — i.e. the turret colour update must
run against the post-flip `SCROLL_ROW`, exactly as `installTurretRow` already
does for the character cells. No colour double-buffer is needed; the turret
colour update simply has to be ordered correctly relative to the flip. This is a
known, bounded ordering constraint, not an architectural blocker.

---

## 9. Inactive-page preparation design (4D — not implemented)

**The core finding that shapes 4D:** a full 1 KB matrix rebuild is ~11,000
CPU cycles (`shiftBackgroundUpper` alone is 3,843 cy for 12 rows; a full 25-row
rebuild plus the incoming decoded row is ~4×). PAL non-visible windows are
~3,000 cy before the first badline and ~6,000 cy in vertical blank. **The whole
next-page matrix cannot be built in one frame's slack.** Therefore 4D must
spread the build across the ~8 fine-scroll frames between coarse steps
(divider 2 ⇒ ~16 physical frames), ≈ 120–150 cells/frame, well within budget.

Proposed 4D design:

1. **Two page roles**, tracked by `BG_ACTIVE_PAGE`: `ACTIVE` (displayed) and
   `INACTIVE` (CPU-writable). Symbolic `ssActiveBase` / `ssInactiveBase` and
   `ssActiveD018` / `ssInactiveD018` resolved from `BG_ACTIVE_PAGE` (a 3-byte
   table lookup, not a branch tree).
2. **Incremental construction.** Over the fine-scroll frames leading to the next
   coarse step, copy the ACTIVE matrix into the INACTIVE matrix *shifted up one
   row* (rows 1..24 ← rows 0..23), a bounded slice (e.g. 2 matrix rows = 80
   cells ≈ 800 cy) per frame, and decode the one incoming top row (row 0) into
   the INACTIVE matrix. Reuse `decodeStageCharacterRow` + a page-parameterised
   `copyIncomingRowToScreen`.
3. **Validity tag.** `SS_INACTIVE_ROW_LO/HI` = the `SCROLL_ROW` this INACTIVE
   page was built for; `SS_INACTIVE_VALID` set only when the whole slice
   sequence has completed. The tag semantics are identical to Stage 2's
   `BG_PREDECODE_ROW` tag — this dovetails with the existing predecode
   (`BG_PREDECODED_ROW` already holds the decoded incoming row a frame early).
4. **Invalidation** (`SS_INACTIVE_VALID := 0` + restart the slice sequence):
   `initBackground` (game start / restart), stage wrap (`SCROLL_ROW 0 → SLR-1`),
   any level-reinit path, any discontinuous `SCROLL_ROW` change (test fixtures
   must poke `SS_INACTIVE_VALID = 0` after seeding `SCROLL_ROW`), respawn if it
   repaints. The predecode already has all these invalidation hooks — 4D extends
   them.
5. **Turret / colour ordering** (§8): the INACTIVE-page turret-glyph overlay and
   the turret colour-cell writes run against the *post-flip* `SCROLL_ROW` on the
   frame the flip happens, so a turret that changes state (destroyed, hit flash)
   between the incremental build and the flip is still shown correctly — the
   overlay is applied at flip time, not build time (same principle as Stage 2's
   "terrain-only cache, live turret overlay at reveal").

## 10. Page-flip timing (4C measured; 4E design)

**4C (measured):** the flip is a single `sta VIC_MEMORY_SETUP` (4 cy) performed
at beam ≈ 0, right after `waitForGameFrame` returns and before the frame's first
badline (~raster 48). The VIC latches the screen base per badline, so a flip in
that window applies cleanly to the whole visible frame. 6,000 such flips: zero
border bails / replays / incomplete frames / catchups (§11).

**4E (design):** publish the coarse step by flipping to the freshly-built
INACTIVE page instead of running the in-window matrix mutation. The flip still
happens at beam ≈ 0 of the frame that would have admitted the coarse step; the
`RASTER == 160` fence and `saveCrossingRow` / `shiftBackgroundUpper` /
`renderStageRowToScreen` in-window work are **removed from that frame** (they
were done incrementally on earlier frames into the INACTIVE page). Roles swap;
the now-INACTIVE (old ACTIVE) page begins its incremental build for the next
step. `finishBackgroundCoarse`'s lower-row copy is folded into the incremental
build.

---

## 11. Reason-1 before / after evidence

**4A–4C do not change the coarse-admission path, so reason 1 is unchanged — by
design.**

| fixture | Stage 3 baseline | Stage 4 (4A+4B+4C on, no flip) | Stage 4 (4C, flipping every frame) |
|---|---|---|---|
| 199/235 (8 en Y=199 + player Y=235), 400 frames | `COARSE_DEFER_LIVE` +396, `COARSE_ADMIT` +0, fine pinned 7 | `COARSE_DEFER_LIVE` +396, `COARSE_ADMIT` +0, fine pinned 7 | n/a (frozen fixture) — the flip path does not reach the coarse gate |
| 9,000-frame natural run | ADMIT 562 / LIVE 1 / HIT 561 | ADMIT 563 / LIVE 3 / HIT 562 | n/a |

The 199/235 case **still fails to make scroll progress for reason 1**, exactly as
required for this pass. Removing that obstruction is 4D–4F.

## 12. 199/235 results

Run on the 4A+4B build (screen B allocated, `$D018` at page A, no flip):

```
199/235, 400 measured frames:  dCOARSE_DEFER_LIVE = 396   dCOARSE_ADMIT = 0
                               dSCROLL_ROW = 0             SCROLL_FINE = 7 (pinned)
```

Identical to Stage 3. The relocation and the inert second page have zero effect
on the structural stall.

## 13. Supported gameplay results

4A+4B build, natural play:

| workload | result |
|---|---|
| clean boot + normal play | plays identically to Stage 3 (screen B inert at `$0400`) |
| 9,000 frames incl. a stage wrap | `[19656]`, service 0, sprite-miss 0, `body/lastrow temporal diffs 0`, coarse-admit / predecode-HIT / reason counters within CIA-jitter of Stage 3 |
| 1,400-frame `--physical --trace` capture | `frame_cycle_deltas: [19656]`, `service_failure_count: 0`, `sprite_start_miss_count: 0`, `max_objects: 9`, `max_batches: 1` |

Fixtures (5 en / 6 en / 6 en + 2 bullets / 8-no-reuse / 9-reuse) were validated
against Stage 3 during the Stage 2/3 passes; 4A–4C add no code to the object,
sort, BUILD/LIVE, collision or wave paths, so those results carry forward. The
one behavioural surface 4A touches — the *location* of the attack/fragment
tables and the background code — is proven transparent by the 9k natural run and
the `--trace` capture above.

## 14. Regression matrix

| area | check | result |
|---|---|---|
| **Build / toggles** | `OPT_SECOND_SCREEN` off (default) | `f2abc225159e81bf…` — **byte-identical to Stage 3** |
| | 4A only / 4A+4B / 4A+4B+4C | all compile (`3d7849ed…` / `336a5c5a…` / `326f1686…`) |
| | guards | attack-data / bg-control / page-B / Stage-4-code overrun guards all pass |
| **PAL cadence** | `frame_cycle_deltas` (trace, 1,400 frames, 4A+4B on) | `[19656]` |
| | `RASTER_FRAME` 1:1 over 6,000 frame-boundary flips (4C) | exact — no dropped/doubled frames |
| **Scroll** | fine phases / repeated 7→0 / stage wrap (9k natural run) | identical progression to Stage 3 |
| **Terrain** | `check_scroll_edges_rsel1 --aperture 55 246` (4A+4B on) | `body_temporal_diffs 0`, `lastrow_temporal_diffs 0` |
| | soft-edge behaviour | **not addressed** (§16); `SOFT_EDGE_MASK` untouched / off |
| **Predecode** | HIT / MISS rate, stage-wrap MISS (9k run) | HIT 562 / MISS 1 — Stage 3 profile |
| **Sprites / scheduler** | `service_failure_count` / `sprite_start_miss_count` (trace) | 0 / 0 |
| | per-frame `RASTER_LAST_EXPECTED == RASTER_LAST_DONE` over 6,000 flips (4C) | never short |
| | `max_batches` / all 8 post-HUD slots | unchanged |
| **HUD / border** | `RASTER_BORDER_BAILS` over 6,000 flips (4C) | **+0** |
| | `RASTER_REPLAY_FRAMES` / `RASTER_INCOMPLETE_FRAMES` / `RASTER_CATCHUPS` over 6,000 flips | **+0 / +0 / +0** |
| | HUD digits visible on both pages | screenshots pixel-identical when synced |
| **Collision / waves / turrets** | code paths | untouched by 4A–4C |
| **Page-flip specifics (4C)** | screenshot page A frame vs page B frame, matrices synced | **pixel-identical** |
| | screenshot with page B deliberately desynced (extra band) | page B frame shows the band, page A frame does not — flip selects the intended matrix |
| | page A / page B content + sprite-ptr-table equality under flipping | 0 mismatches in 6,000 flips |
| | `$D018` readback | `$1E`→`$1F`, `$AE`→`$AF` (bit 0 reads 1; VIC ignores) |
| **Lifecycle** | `ssInitPageB` at `startGame` | `$2800–$2BFF == $0400–$07FF`, `SS_PAGE_B_INITED = 1`, `BG_ACTIVE_PAGE = 0`, `$D018 = $1E` |

## 15. Diagnostics added

All `#if OPT_SECOND_SCREEN`, in the CPU-only `$9900` block, no IRQ hot-path cost:

| symbol | meaning |
|---|---|
| `BG_ACTIVE_PAGE` | 0 = displaying page A (`$0400`), 1 = page B (`$2800`) |
| `SS_PAGE_B_INITED` | 1 once `ssInitPageB` has seeded page B from page A |
| `SS_FLIP_COUNT` (word) | `$D018` page flips performed by `ssFlipPage` |
| `SS_PTR_MIRROR_COUNT` (word) | `$07F8→$2BF8` sprite-pointer mirrors performed |

Routines: `ssInitPageB` (one-time full A→B copy), `ssMirrorSpritePtrs` (8-byte
ptr-table mirror, ~50 cy), `ssFlipPage` (toggle `$D018`, ~20 cy — used by the 4C
probe via `r pc=` / not wired into the game loop this pass to keep the byte-off
build identical and the near-full `$080E` code segment intact).

## 16. Hashes / build reproducibility

| build | SHA-256 |
|---|---|
| Stage 4 default (`OPT_SECOND_SCREEN` commented) | `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991` (= Stage 3 baseline, HEAD `223a820`) |
| 4A only | `3d7849ed99903f64…` |
| 4A + 4B | `336a5c5a288e9f08…` |
| 4A + 4B + 4C | `326f1686f3cf3d05…` |

## 17. Remaining risks

1. **Inactive-page build cost (the decisive unknown).** A full matrix rebuild
   does not fit one PAL frame's slack; 4D must spread it. If the incremental
   slice cost plus the existing per-frame load pushes any fine-scroll frame past
   its budget, the whole approach regresses. Must be measured before 4E.
2. **IRQ sprite-pointer dual-write cost.** ~8–10 cy per LIVE batch in the raster
   hot path if option 1 (§7) is chosen. Needs a measured verdict vs the frame
   budget; option 2 (8-byte late mirror) avoids the IRQ but constrains flip
   scheduling.
3. **Turret colour-cell ordering** across a flip (§8). Bounded and understood,
   but a real ordering constraint that 4D must implement precisely (turret
   colour + glyph overlay against post-flip `SCROLL_ROW`).
4. **`finishBackgroundCoarse`'s lower-row copy** must be folded into the
   incremental build; it currently mutates the visible matrix at frame top.
5. **`$080E` code-segment headroom** is ~2 bytes. Wiring 4D–4F hooks into
   `gameLoop` will need either a small relocation of a self-contained routine
   out of that segment or moving hook bodies behind `jsr` into the roomy
   `$9280`/`$9900` region.
6. **Menu / GAME OVER / hi-score** all write `$0400`; 4E must guarantee the
   engine returns to `$D018 = $1E` on any transition out of PLAYING (a
   3-instruction `endGame` addition, deferred so the byte-off build stays
   identical this pass).
7. **Colour RAM stays single.** Any future per-cell dynamic colour beyond the
   turret bodies would need the same post-flip ordering discipline.

## 18. Explicit soft-edge statement

**Soft-edge masking was not addressed in this task.** The `SOFT_EDGE_MASK`
experiment remains `#define`d off and untouched. The accepted clean 192 px
terrain aperture (raster 55..246) is preserved unchanged. A second screen does
not, on its own, solve the top/bottom soft-edge pop, and no ECM / charset-swap /
phase-mask / 200 px work was attempted.

## 19. Recommendation for the next bounded step

**Proceed to 4D as its own task, in this order, stopping at the first failure:**

1. **Parameterise the row-install path by page.** Add `ssActiveBase` /
   `ssInactiveBase` lookups; make `copyIncomingRowToScreen` and a new
   `ssShiftInactiveSlice` take a destination page. Prove the ACTIVE-page path is
   byte-identical to Stage 3.
2. **Incremental inactive-page build.** Spread the 25-row shift + incoming-row
   decode across the fine-scroll frames before each coarse step (~2 rows/frame
   ≈ 800 cy). Instrument per-frame cost. **Acceptance:** worst preparation frame
   stays inside budget; `[19656]`; `RASTER_REPLAY_FRAMES` / `INCOMPLETE` / `BORDER_BAILS`
   unchanged over a long run + stage wrap.
3. **Sprite-pointer strategy decision.** Measure option 1 (IRQ dual-write) vs
   option 2 (late 8-byte mirror) against the frame budget; pick the cheaper that
   keeps the displayed page's table always correct.
4. **4E flip-on-coarse.** Replace the in-window matrix mutation with a flip to
   the prepared INACTIVE page. Keep the old path behind a compile-time fallback.
5. **4F reason-1 proof.** Re-run 199/235: scrolling must continue through
   repeated coarse transitions, the pending LIVE batch serviced correctly, no
   sprite/HUD/border/terrain regression, `[19656]`, and `COARSE_DEFER_LIVE` no
   longer the structural blocker — *proven*, not merely uncounted.
6. Only after 4F is GREEN: remove or relax the `pending-LIVE` gate.

Do **not** change the coarse-admission gate before 4D–4F are proven. The Stage 4A
relocation and the 4C flip proof have de-risked the approach; the inactive-page
build cost is the remaining gate, and it must be a measurement, not an
assumption.

---

## 20. Final repository state

```
$ git status --short
 M src/main.asm

$ git diff --stat
 src/main.asm | 208 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++-
 1 file changed, 207 insertions(+), 1 deletion(-)
```

**Repository history was not altered.** No commit, add/stage, tag, push, pull,
reset, stash, or branch switch. HEAD is still
`223a8201bbc55c5c751a9683e22e284143cc0644` (tag `stable-single-screen-scroller`).
All Stage 4 changes are in the working tree, behind `#if OPT_SECOND_SCREEN`
(default off). With the toggle off the build is byte-identical to the stable
baseline: `f2abc225159e81bfc6f911bea28558dbe55821eb9546bb8cab45b0893f027991`.

### Generated test artefacts

Scratchpad only (not in the repo tree): `s4c.py` / `s4c2.py` (flip proof),
`s4shots/*.png` (page-A / page-B screenshots, sync + desync), A/B build tree
`/tmp/ss4/{off,on}/`.
