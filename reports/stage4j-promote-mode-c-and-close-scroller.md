# Stage 4J — Promote Mode C to the Default Scroller and Close Stage 4

## Verdict: **GREEN**

The ordinary default build now produces the already-accepted Mode-C binary
byte-for-byte, with no other source line touched. The full regression suite
passes against that ordinary build with no new correctness or timing issue.
Modes A and B remain reachable, unmodified, and byte-identical to their
established hashes. Documentation has been updated so future sessions treat
the double-buffered scroller as the normal architecture rather than an
experimental toggle. **Stage 4 double-buffered scrolling is CLOSED.**

---

## 1. Repository state (inspected, not assumed)

```
branch    experimental-border-hud
HEAD      e012f19  "Document dense per-flip investigation"
status    clean (before this task's edits)
tags      engine-pre-background-scroll, hud-updated-with-score,
          pre-terrain-workshop, stable-double-buffered-scroller,
          stable-double-buffered-scroller-v2, stable-single-screen-scroller,
          v1.0
```

`e012f19` is **one commit past** the accepted checkpoint `479bb32` — it adds
only the Stage 4I report and worklog (2 files, 558 insertions, no source
changes), confirming the Stage 4I investigation is fully committed and
pushed.

`stable-double-buffered-scroller-v2` is an **annotated** tag; its tag-object
hash is `2982010101cf93911f37d9b518ba65b4614d7c11...`, but resolving it via
`^{commit}` gives `479bb32afa6e066c0a59851a748c3cdfdeed9cdb` — an **exact
match** to the expected checkpoint commit. (A plain `git rev-parse` on an
annotated tag returns the tag object, not the commit, which is why the two
looked different on first read — resolved with `^{commit}` before concluding
anything.)

Toggle state in source at task start: all four Stage-4 sub-stage `#define`s
commented (tree built Mode A by default). Builder-scheduling constants
already at the Stage 4G/4H/4I values:
```
.const SS_PLF_BUILD_SLICE_ROWS     = 1
.const SS_PLF_SLICE_RASTER_CUTOFF  = 180
.const SS_PLF_FLIP_HOLDOFF_FRAMES  = 3
```

No pull, reset, stash, branch switch, commit, tag, push or stage was
performed. The working tree at the end of this task holds the reviewed,
uncommitted changes described below, left for the user.

---

## 2. Objective 1 — the exact proven Mode-C toggle set

Inspected directly from `src/main.asm` (not assumed from the prompt). The
four compile-time defines, all under `#if OPT_SECOND_SCREEN`:

| define | stage | effect |
|---|---|---|
| `OPT_SECOND_SCREEN` | 4A-4C | second 1 KB screen page in VIC bank 0; implies `OPT_SS_RELOCATE`/`OPT_SS_PAGE_B`/`OPT_SS_FLIP_PROOF` |
| `OPT_SS_INACTIVE_BUILD` | 4D | incremental inactive-page terrain construction |
| `OPT_SS_FLIP_COARSE` | 4E | publish a coarse step as a `$D018` flip instead of the legacy in-window matrix mutation |
| `OPT_SS_ALLOW_PENDING_LIVE_FLIP` | 4F | relax reason 1 (`COARSE_DEFER_LIVE`) for the proven flip path; also selects the Stage-4H-corrected page-aware pointer mirror and Stage-4G builder-scheduling overrides |

All four ON, exactly as described in Stage 4G/4H, is Mode C. This matches
the prompt's description and required no correction.

---

## 3. Objective 2 — make Mode C the normal/default build

`src/main.asm`'s toggle block was changed from commented to active for all
four defines, and the surrounding comments rewritten to describe the new
reality (Mode C is now the default; Modes A/B are documented fallbacks with
their hashes, not "experimental"/"not yet implemented" states). **No other
source line was touched** — confirmed by inspecting the full diff:

```diff
-//#define OPT_SECOND_SCREEN
+#define OPT_SECOND_SCREEN
...
-    //#define OPT_SS_INACTIVE_BUILD
+    #define OPT_SS_INACTIVE_BUILD
...
-    //#define OPT_SS_FLIP_COARSE
+    #define OPT_SS_FLIP_COARSE
...
-    //#define OPT_SS_ALLOW_PENDING_LIVE_FLIP
+    #define OPT_SS_ALLOW_PENDING_LIVE_FLIP
```
(plus comment text around each, and the block header). The old code paths
for Modes A and B were **not deleted** — they remain the `#else`/commented
branches throughout `main.asm` and `raster_scheduler.asm`, reachable exactly
as before by commenting the relevant define(s).

---

## 4. Objective 3 — the default build reproduces the accepted binary

Built normally (`java -jar KickAss.jar src/main.asm -odir build -o
build/shooter.prg -vicesymbols`), with no manual toggle editing before or
during this build:

```
80d5b0461c070fe23d6e5dbcb2124eb9e4093dbbc4034464d9afe0596f08ce66  build/shooter.prg
```

**Exact match** to the accepted Stage 4G/4H/4I Mode-C baseline
`80d5b0461c070fe23d6e5dbcb2124eb9e4093dbbc4034464d9afe0596f08ce66`. Since the
only change affecting the toggle state is a `#define`/comment edit (verified
above to be the entire diff), and the resulting bytes are identical to the
independently-built Mode-C binary from three prior stages, this is exactly
the expected and required outcome — no code-generation difference, no
assembler-layout difference, nothing to account for.

**Fallback paths reconfirmed reachable and unchanged**, by manually
commenting one define at a time from the new default and rebuilding to a
scratch path (not left in the tree):

| check | result |
|---|---|
| comment `OPT_SECOND_SCREEN` → Mode A | `f2abc225159e81bf...` — exact match |
| comment `OPT_SS_ALLOW_PENDING_LIVE_FLIP` → Mode B | `e0c3141a7ee88f8f...` — exact match |

`build/shooter.prg` is left at the ordinary default build (Mode C) — this is
now the correct resting state, superseding the earlier-stage convention of
leaving `build/` at Mode A.

---

## 5. Objective 4 — final default-configuration regression

Run against the **ordinary default build** (`build/shooter.prg` as produced
above), using the existing capture tooling with no manual source edits
during testing.

| fixture | frames | replay | catchup | `[19656]` | service fail | incomplete | sprite-start miss | page A | page B |
|---|---|---|---|---|---|---|---|---|---|
| idle | 300 | 0 | 0 | ✅ | 0 | 0 | 0 | 156 | 144 |
| authored wave (seed 382) | 320 | 1 | 1 | ✅ | 0 | 0 | 0 | 177 | 143 |
| stage wrap (seed 12) | 340 | 5 | 1 | ✅ | 2 † | 0 | 0 | 161 | 179 |
| `--y199` | 400 | 0 | 0 | ✅ | 0 | 0 | 0 | 212 | 188 |
| `--dense` | 200 | 99 | 1393 | ✅ | 0 | 0 | 16 ‡ | 104 | 96 |
| turret-playtest | 500 | 0 | 1 | ✅ | 0 | 0 | 0 | 256 | 244 |
| accelerated stress | 500 | 0 | 0 | ✅ | 0 | 0 | 0 | 272 | 228 |

† Both wrap failures were checked individually against the `.actpage`
capture: frame 82 and frame 131 are each the exact first page-B frame after
a flip, confined to slots 4-7 with the HUD-placeholder values 188-191 — the
same signature documented and disclosed since Stage 4G ("Finding 2": the
oracle models `INITIAL_SPRITE + ASSIGN_SPRITE` but not HUD's separate
pointer-write path). Not a raster-service defect — `sprite_start_miss_count`
is 0 and `RASTER_INCOMPLETE_FRAMES` is 0 throughout. Reported as-is, per the
task's instruction not to weaken the oracle; the frame numbers differ
slightly from prior runs (82/147 in Stage 4H, 131 in Stage 4I) only because
of the CIA-timing jitter these reports already document between independent
VICE runs — the failure mechanism and slot signature are identical.

‡ Checked directly: all 16 are `mask`-kind (`rasterBatchMasksApplied`)
misses, all at `physical_fine == 4` — an exact match to the Stage-4I-accepted
badline/deadline-line signature (raster 164 is a badline exactly when
`SCROLL_FINE == 4`; the dense fixture's bottom sprites sit at Y=164). This is
not a new or worse result — it is the same, already-investigated and
already-accepted phenomenon. **Not touched, not re-tuned**, per the explicit
instruction not to attempt to reduce it in this task.

`page_aware: true` on every capture; the page-aware sprite-pointer oracle is
active and passing (0 genuine gameplay-pointer failures anywhere in the
suite — both wrap failures are the disclosed HUD-modeling caveat, not
gameplay pointer corruption).

`--y199` **progresses** (188 of 400 frames on page B, 0 replay) rather than
remaining pinned — confirming the pending-LIVE relaxation is active in the
default build, not just theoretically selected by the toggles.

All numbers are within the normal run-to-run CIA-jitter variance already
documented across Stage 4F-4I (e.g. wave replay/catchup and page-B frame
counts shift by a few frames between independent captures of the same
fixture — this has never affected cadence, service correctness or pointer
correctness, and does not here either).

---

## 6. Objective 5 — documentation closure

### `AGENTS.md`
The "Current scrolling architecture" section previously described the *old*
single-screen engine as "the production scrolling engine" — stale, and
exactly the kind of thing that would mislead a future session into treating
the double-buffered architecture as an experiment to be cautious of, or
vice versa. Rewritten to:
- describe the double-buffered, page-flip-published, pending-LIVE-tolerant,
  page-aware-pointer architecture as current
- list Modes A and B as reachable regression/reference/diagnostic
  configurations (with a one-line description of each), explicitly not the
  normal build
- name all three checkpoint tags and what each represents
- note the disclosed, accepted `--dense` badline exposure as a known,
  understood, closed characteristic — not touched further
- keep the "do not replace this architecture casually" guidance, now
  pointed at the current architecture's actual load-bearing details (page
  flip publication, inactive-page build scheduling, sprite-pointer
  mirroring) instead of the old crossing-row-buffer description

### `reports/stage4-second-screen-scroller-architecture.md`
A closure banner was added immediately after the title, before the original
Stage 4A-4C body (left completely unmodified for historical accuracy,
including its now-superseded "4D-4F not implemented" framing). The banner:
- states plainly that everything below it is historical and no longer
  describes the current codebase
- summarises what Stages 4D through 4J each did, with links to each report
- states the checkpoint tags and their meaning
- points to `AGENTS.md` as the maintained, current-state summary

This satisfies "do not turn the main docs into a dump of the entire Stage-4I
report" — the dense-result summary here is two sentences with a link, not a
restatement of Stage 4I's causal analysis.

### Not touched
`README.md` is a one-line placeholder unrelated to the scroller.
`docs/hud-architecture.md` was checked and has no scroller-default
dependency (its one `$D018` mention is about the alternative HUD-approach
comparison table, not the toggle state). No other documentation file
references the scroller toggle state.

---

## 7. Areas explicitly not touched

Sprite multiplexer architecture, raster scheduling architecture, reasons 2/3,
builder scheduling values (`SS_PLF_BUILD_SLICE_ROWS`/`SS_PLF_SLICE_RASTER_
CUTOFF`/`SS_PLF_FLIP_HOLDOFF_FRAMES` — confirmed still 1/180/3, unedited),
HUD visual architecture/art, soft-edge/RSEL1 masking, player sprite art,
player movement, weapons, laser, overheat, editor/stage ABI, VIC-bank
relocation/reclaim, multiload/stage package architecture, gameplay state
machine, upgrade screen. `raster_scheduler.asm` was read but not edited.
This task stayed boring throughout — no unexpected finding required a stop.

---

## 8. Final questions

**1. What exact compile-time toggles now define the default scroller?**
`OPT_SECOND_SCREEN`, `OPT_SS_INACTIVE_BUILD`, `OPT_SS_FLIP_COARSE`,
`OPT_SS_ALLOW_PENDING_LIVE_FLIP` — all now active by default in
`src/main.asm`, with the Stage 4G builder-scheduling constants
(`SS_PLF_BUILD_SLICE_ROWS=1`, `SS_PLF_SLICE_RASTER_CUTOFF=180`,
`SS_PLF_FLIP_HOLDOFF_FRAMES=3`) unchanged.

**2. Does an ordinary build now produce Mode C?**
Yes — verified by building with no manual toggle editing.

**3. What is the ordinary-build SHA-256?**
`80d5b0461c070fe23d6e5dbcb2124eb9e4093dbbc4034464d9afe0596f08ce66`

**4. Does it match the accepted Mode-C baseline?**
Yes, exactly.

**5. Did all core regression fixtures pass?**
Yes: idle, authored wave, stage wrap, `--y199`, `--dense`, turret-playtest,
and accelerated stress all hold exact `[19656]` cadence, zero incomplete
frames, and zero genuine (non-HUD-caveat) service failures. `--dense`
reproduces the exact accepted 16-miss/`fine==4` signature from Stage 4I — no
new or worse result.

**6. Is page-aware sprite-pointer correctness intact?**
Yes — the oracle is active (`page_aware: true`) on every capture and reports
zero gameplay-pointer failures. The two wrap-fixture failures are the
already-disclosed HUD-modeling oracle gap (Stage 4G Finding 2), not pointer
corruption, and were verified individually against the flip-transition frame
signature before being reported as such.

**7. Did you make any behavioural change beyond promoting the proven
configuration to default?**
No. The entire `src/main.asm` diff is the four `#define` lines plus their
surrounding explanatory comments — confirmed by inspecting the full diff
before building. No other line in `src/main.asm`, `raster_scheduler.asm`, or
any tool was touched.

**8. Are Modes A and B still available for regression/reference?**
Yes — both were rebuilt this session by commenting one toggle each from the
new default and reconfirmed byte-identical to their established hashes
(Mode A `f2abc225159e81bf...`, Mode B `e0c3141a7ee88f8f...`). Neither code
path was deleted or altered.

**9. Is `stable-double-buffered-scroller-v2` still untouched and correctly
positioned?**
Yes. It was not moved, deleted or rewritten this session (no tag operation
was performed at all), and resolves (via `^{commit}`) to exactly
`479bb32afa6e066c0a59851a748c3cdfdeed9cdb`, the expected checkpoint.

**10. Is Stage 4 double-buffered scrolling now formally CLOSED?**
**Yes.** The architecture is proven, promoted to the default build, the
default build reproduces the accepted binary exactly, and the full
regression suite passes against it with no new issue. There is no open
scroller-architecture question remaining.

**11. What should the next project task be?**
No Stage 4K. Per the task's own framing, the natural next steps are outside
the scroller (visually reassessing the remaining scroll-edge pop under the
now-completed architecture; top-border HUD artwork/layout; dynamic score
rendering; overheat mechanic; player movement tuning; end-of-level/upgrade
flow) — none of which this task implements or recommends starting now.

---

## 9. Summary for the user

Mode C is now what an ordinary build produces. Nothing about the engine's
behaviour changed — the exact same, already-proven binary is now the
default instead of something a developer had to opt into. Modes A and B are
still there if you need them for comparison or diagnosis. The two docs a
future session (or you) would read first — `AGENTS.md` and the Stage 4
architecture report — now say the double-buffered scroller is the normal
architecture instead of an experiment. Nothing has been committed; the
change is sitting in your working tree for review.
