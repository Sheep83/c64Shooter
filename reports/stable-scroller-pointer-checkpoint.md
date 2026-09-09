# Stable Scroller / Sprite Pointer Checkpoint

Consolidation, regression, commit, annotated tag and push of the scrolling and
sprite-pointer work accumulated on top of `d60828a`.

**Result: committed, tagged and pushed successfully. Working tree clean.**

---

## 1. Starting repository state

| | |
|---|---|
| repo | `Sheep83/c64Shooter` (SSH: `git@github.com:Sheep83/c64Shooter.git`) |
| branch | `main`, tracking `origin/main` |
| HEAD before | `d60828a` — *Promote double-buffered scroller to default* |
| divergence from origin | none (`0 0`) |
| target tag pre-existing? | **no** — `stable-scroller-and-sprite-pointers` was absent, so nothing was overwritten |

Working tree carried 3 modified sources and 22 untracked docs/reports. `.gitignore`
already excludes `build/`, `*.prg`, `*.sym`, `*.vs`, `*.log`, `*.tmp` and
`__pycache__`, so every capture directory, monitor trace, emulator dump and
assembled binary produced during the investigations was **automatically excluded**
— no manual pruning was required and nothing was deleted.

---

## 2. Working-tree classification

### A. Production changes — committed

| file | contents |
|---|---|
| `src/main.asm` | Stage 5 edge-mask constants and display-state ownership; Phase B(b) page-aware legacy coarse fallback (`SS_LEGACY_PAGE` latch, page-B shift/crossing-row routines at `LEGACY_PAGEB_SEGMENT = $8640`, `LEGACY_FALLBACK_PAGE_AWARE` toggle); `ssReconcileTurretSlot` `rel == -1/-2` correction; page-aware row-0 writes (`copyIncomingRowToScreen`, `bgConsumePredecodedRow`); sprite-pointer repair (unconditional `$2BF8` HUD writes, `ssFlipMirrorPtrs` moved to `armFirstBatch`'s entry); segment relocations `SS_STAGE4_BASE_ADDR = $9980` and `ENGINE_LOOKUP_SEGMENT = $1f20` with `.error` guards |
| `src/raster_scheduler.asm` | Fable's scheduler-integrated mask (`RASTER_EVENT_MASK`, 2-phase `RASTER_DISPLAY_PENDING`, arm/serve hooks, `EDGE_MASK_LATE`/`FALLBACK` counters) replacing the Stage-5A busy-wait |
| `src/background_turrets.asm` | `TURRET_PAINT_ROW` presentation row; `pulseTurretColour` follows the glyphs instead of the `TURRET_VISIBLE` combat gate |

### B. Tooling — committed

| file | contents |
|---|---|
| `tools/vice_scroll_test.py` | new `--passive` flag. The default holds FIRE on **every frame** (`jpdb 1 {255 ^ (16 \| direction)}`), which shoots and destroys turrets — that silently invalidated two passive-symptom investigations. `--passive` keeps the joystick neutral after the title screen. **Default behaviour is unchanged**, so every existing fixture is unaffected. |

### C. Reports and worklogs — committed

11 reports under `reports/` and 10 worklogs under `docs/`, consistent with the
repo's established practice (31 reports and 27 worklogs already tracked). Includes
`historical-scroll-hitch-turret-duplication.png` (the machine-captured evidence
image for the duplicated-turret defect) and `stage5a-candidate-as-tested.patch`
(the superseded Stage-5A candidate, retained deliberately for archaeology).

### D. Scratch / ephemeral — excluded

All capture directories (`build/*`), per-frame RAM/colour/charset/VIC dumps, PNG
frame grabs, VICE monitor traces, `timing.log` files, assembled `.prg`/`.vs`/`.sym`
artefacts, and the session scratchpad harnesses under `/private/tmp/...`. These are
covered by `.gitignore` and were never staged. Nothing was deleted.

`git add -A` was **not** used; files were staged explicitly by path.

---

## 3. Final regression — run against the exact committed tree

### Builds (all three supported configurations)

| configuration | hash | result |
|---|---|---|
| mask-ON (default) | `f1d08a0f5d2337ee` | clean |
| mask-OFF | `66d2fa9295e858ac` | clean |
| Mode A (single-screen, `OPT_SECOND_SCREEN` off) | `2591ca3da434cf1a` | clean |

### Suite

| fixture | frame deltas | incomplete | svc fail | pointer fail | sprite-start miss | catchups | replay | page A/B |
|---|---|---|---|---|---|---|---|---|
| idle 300 | `[19656]` | 0 | 0 | 0 | 0 | 0 | 0 | 156/144 |
| wave 320 (seed 382) | `[19656]` | 0 | 0 | 0 | 0 | 1 | 4 | 179/141 |
| wrap 340 (seed 12) | `[19656]` | 0 | **0** | 0 | 0 | 2 | 5 | 180/160 |
| y199 400 | `[19656]` | 0 | 0 | 0 | 0 | 0 | 0 | 211/189 |
| dense 200 | `[19656]` | 0 | 0 | 0 | **0** | 1386 | 100 | 104/96 |
| turret 500 | `[19656]` | 0 | 0 | 0 | 0 | 1 | 0 | 260/240 |
| stress 500 | `[19656]` | 0 | 0 | 0 | 0 | 1 | 0 | 272/228 |

**Exact PAL 19,656 cycles/frame on every fixture. Zero sprite-start misses,
`--dense` included. Zero pointer-oracle failures. Zero service failures** — the
wrap fixture's long-standing 3 failures were the sprite-pointer race and are gone.

### Invariants

- **Phase B(b) scrolling**, hitch seeds 352/340/232: 13 fallback attempts =
  8 page-A + 5 page-B + **0 refusals**; **0 seven-pixel snaps, 0 duplicated
  turrets**, max visual stall 2 frames (baseline). Counter invariant
  `attempts == execA + execB + refuse` holds.
- **Turret `rel == -1/-2` reconciliation oracle**: **0** wrong cells on all three seeds.
- **Stage 5 aperture**: fixed **58..247 on 130/130 frames** for wave, wrap, dense,
  turret and stress.
- **Title / high-score containment**: `$D011=$9b`, ECM=0, YSCROLL=3, `GAME_STATE=0`,
  15 starfield glyphs; gameplay ECM=1 (mask band).
- **Passive fixture via the new `--passive` flag**: `[19656]`, 0 service failures,
  0 sprite-start misses, and a passivity proof of **720 alive turret-slot samples,
  0 dead** — confirming the flag genuinely suppresses combat.

### Residual known failures

**None** in the automated suite. Every fixture is clean.

---

## 4. Known accepted residual issue

**Authored turret visual flicker / shimmer in the four-turret cluster
(`345 / 337 / 329 / 321`) is accepted as a level-design constraint and was not
investigated in this task.**

Recorded for future reference from the preceding investigations:

- Screen RAM was independently exonerated across the reproduction window: the
  active matrix is a perfect 25-row window of the authored stage on every
  displayed frame, verified against a standalone Python decode of the stage tables.
- Colour RAM is coherent; the turret glyph charset is stable; the mask never runs
  late and the aperture never moves.
- The cluster is spaced 8 world rows against a 24-row aperture, so at most **three**
  of the four turrets are ever on screen together.
- The strongest remaining hypothesis is presentational rather than a defect:
  `turretPulseTable = 1, 2, 7, 2` has phase 0 (`1|8 = 9`) **identical to
  `TERRAIN_COLOUR_RAM`**, and all turrets share one global pulse index, so every
  turret flattens into the terrain colour for 8 frames in every 32, in unison.

Workaround if wanted later: space one cluster turret more than 12 world rows from
its neighbours, or change pulse phase 0 away from `TERRAIN_CHARACTER_COLOUR`.
Neither was applied here.

---

## 5. Manual sprite-flicker test result

After the sprite-pointer publication repair the user played the game manually and
reported:

> **nothing detected**

This is manual confirmation that the previously observed player/enemy sprite
flicker is no longer reproducible in ordinary play. It is corroboration, not proof
— the primary evidence remains the machine-level pointer correctness: 0
pointer-oracle failures, 0 A/B divergence on any flip frame, 0 player (slot 0)
divergence across 1,050 frames of passive, combat and dense fixtures, and a
structural guarantee that the mirror now precedes the first LIVE assignment on
every frame (0 violations).

---

## 6. Commit

```
c349fe216c362dcd7d8defaf939b491e17a7e783
Stabilize scrolling and sprite pointer publication
```

26 files changed: 4 source/tooling files (`+629 / -47` lines) plus 22 reports and
worklogs.

## 7. Annotated tag

```
tag    stable-scroller-and-sprite-pointers   (annotated, object c9794f08632f)
target c349fe216c362dcd7d8defaf939b491e17a7e783
msg    Stable double-buffered scroller, edge masking, page-aware fallback and
       sprite pointer publication
```

The tag did not previously exist; nothing was overwritten or force-moved.

## 8. Push results

```
To github.com:Sheep83/c64Shooter.git
   d60828a..c349fe2  main -> main
 * [new tag]         stable-scroller-and-sprite-pointers -> ...
```

Verified against the remote:

```
c349fe216c362dcd7d8defaf939b491e17a7e783  refs/heads/main
c9794f08632fb2fb20a3f05e8f1ea850c96ddf2b  refs/tags/stable-scroller-and-sprite-pointers
```

`main` and `origin/main` are in sync (`0 0`); the annotated tag resolves to the
same commit as `HEAD`. No history was rewritten and no force-push was used.

## 9. Final working-tree status

Clean at the point of tagging and pushing. This checkpoint report and its worklog
were written afterwards and committed as a separate documentation commit, so the
tag continues to mark the code checkpoint exactly. No untracked files are
intentionally retained — all remaining artefacts are covered by `.gitignore`.

## 10. Ready for the next phase

The scroller, edge masking, page-aware coarse fallback, turret reconciliation and
colour presentation, and sprite-pointer publication are all stable, machine-verified
and tagged. **This checkpoint is ready for the next feature phase: HUD.**
