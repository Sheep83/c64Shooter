# 19656 — HUD Phase 1: Six-Digit Score

**Result: GREEN.**

Branch `main`, HEAD `f71ea24` (*Add stable scroller/pointer checkpoint report*),
tag `stable-scroller-and-sprite-pointers` = `c349fe2`. Nothing committed, staged,
tagged or pushed. Working tree carries exactly two changes: `src/main.asm` and a
new `docs/hud-phase1-six-digit-score-worklog.md`.

| build | SHA-256 |
|---|---|
| baseline (HEAD, pre-change) | `f1d08a0f5d2337eef0a75a28a68d4261e9166474e47d655f9c886aa4f2ec6652` |
| HUD Phase 1 (this work) | `3a8158152f9ef3f12a76cf9bd50bf15f1e0f5f49fb148aa0e83223ae051f80c4` |

The baseline was rebuilt out-of-tree from `git show HEAD:src/main.asm` for
side-by-side comparison, so every "baseline" number below is a real measurement
of the pristine build, not a recollection.

---

## 1. Phase A audit — what the score actually was

| item | finding |
|---|---|
| `SCORE_LO` / `SCORE_HI` | **16-bit**, hard ceiling 65,535 |
| `SCORE_VALUE_LO/HI` | conversion scratch |
| `SCORE_DIRTY` | set by `awardKillScore`, consumed once per frame |
| `SCORE_PER_KILL` | 100 |
| `setupScoreDisplay` | cleared the score **and drew "SCORE 00000" into `SCORE_SCREEN = $0400+29`** — a leftover from the retired character HUD that now writes into terrain row 0 |
| `awardKillScore` | 16-bit add. Callers: `main.asm:2542` (enemy death), `background_turrets.asm:813` (turret kill) |
| `refreshScoreIfDirty` | **a stub** — only cleared the flag; called once/frame from the main loop |
| `displayScore` | retained but **never called**; 16-bit → 5 digits into the retired `HUD_SCORE_CELL` |
| `debugDivisorLo/Hi` | 5-entry 16-bit divisors shared with `displayCycleMinimum` / `formatScore5` |
| high score | `HISCORE_LO/HI` ×8, **16-bit**; `HISCORE_ROW_WIDTH = 10` ("III  DDDDD") via `formatScore5` |
| top-border HUD | `HUD_SLOT_FIRST = 4`, `HUD_SPRITE_COUNT = 4` → hardware slots 4..7; `HUD_Y = 22`; `HUD_HANDOFF_RASTER = 43`; `HUD_HANDOFF_COMPLETE_RASTER = 56`; `HUD_SPRITE_BASE = $2f00` (4×64 B, pointers `$bc..$bf`); `hudBorderSetup` at the line-1 IRQ, `hudBorderHandoff` at the DISPLAY event; both write `$07F8` **and** `$2BF8` unconditionally (Stage 4H publication-race repair) |

Nothing was left in parallel. `displayScore`, `scoreLabel`, `SCORE_SCREEN`,
`SCORE_COLOUR`, `HUD_SCORE_CELL`, `SCORE_VALUE_LO/HI`, `HS_VAL_LO/HI` and
`formatScore5` are **deleted**, and the stray "SCORE 00000" write into terrain
row 0 is gone with them. There is exactly one score, one award path and one
binary→decimal conversion in the build.

## 2. Score representation

24-bit binary `SCORE_LO` / `SCORE_MID` / `SCORE_HI`, range 000000–999999,
**saturating** at `SCORE_MAX = 999999` (`$0F423F`). It never wraps.

All awards go through one routine:

```asm
addScore:            // input SCORE_ADD_LO/MID/HI, saturating, preserves X and Y
awardKillScore:      // thin wrapper: SCORE_PER_KILL -> addScore
```

`addScore` uses absolute addressing only, so X and Y survive it — it is called
from the middle of object loops. Gameplay code contains **no** bespoke 24-bit
arithmetic; `background_turrets.asm` was not touched at all.

`addScore` also returns early when the score is *already* exactly 999999. That
is not a micro-optimisation: without it, a player parked at the ceiling makes
the HUD re-run the most expensive conversion in the build on every single kill,
forever, for digits that cannot change.

## 3. Digit font and two-sprite composition

A 10 × 7-byte row table (`scoreFont`), 5 px wide, 1 px stroke, pattern held in
the top 5 bits of each byte. Ten legible glyphs in 70 bytes — not ten opaque
63-byte sprite blobs.

The composition trick is an **8-pixel digit pitch**. Each digit therefore lands
byte-aligned on sprite column 0/1/2, so:

* composition is a plain `sta` per row per digit — no shifting;
* a rebuild **fully overwrites every byte it owns**, so a wide glyph can never
  leave stale pixels behind a narrow one, and no clear pass is needed;
* the 3 px gap is identical *inside* a sprite and *across* the sprite join
  (sprite R sits at sprite L's X + 24), so the six digits read as one number.

Bytes outside the seven digit rows are zeroed at assembly time and never
written, so the rest of each sprite stays permanently transparent.

Geometry: 6 digits × 8 px − 3 px = **45 px**, X 162..206, centre **184** — the
exact 40-column display centre. Both X values are < 256, so `HUD_D010_KEEP`
drops from `$80` to `$00`. Colour 13 (light green) on the grey terrain backdrop.
Digits occupy sprite rows 7..13 = rasters 29..35, inside the opened top border
and clear of the handoff.

## 4. Sprite ownership — the part that mattered most

The score uses HUD indices 0 and 1 → **hardware slots 4 and 5**. Indices 2 and 3
point at the all-zero `blankSprite`. That keeps the proven 4-slot setup/handoff
geometry **completely unchanged**, and it uses the repaired publication
architecture rather than bypassing it: `hudBorderSetup` and `hudBorderHandoff`
were not modified at all, only the data tables they read.

Measured on live gameplay (real raster IRQ, real multiplexer, 60 frames each):

| check | result |
|---|---|
| at `hudBorderHandoff` entry (raster 44..45), `$07F8+4/+5` | `$bc` / `$bd` — the score bitmaps |
| at `hudBorderHandoff` entry, `$2BF8+4/+5` | `$bc` / `$bd` — **both pointer pages agree** |
| at raster 80 (post-handoff), both pages | match the gameplay `INITIAL_SPRITE` plan exactly, on 60/60 frames |
| frames where slot 4+ was actually reclaimed for gameplay | 60/60 |
| `RENDER_COUNT` observed | 7–8 |

So the HUD owns 4/5 through their DMA, and gameplay takes them back every frame.
**No permanent gameplay sprite reservation, and no capacity loss** — the dense
fixture still reports `max_objects: 16`, `max_batches: 8`, identical to baseline.

## 5. Deferred refresh, and a timing bug that measurement caught

This is the one place the first implementation was wrong, so it is worth stating
plainly rather than burying.

The initial version did the whole rebuild (convert + compose) in one call from
the main loop. In isolation that looked fine. **In situ it is up to ~7,000
cycles — 111 raster lines — at score 999999.** The main loop can reach that call
site as late as raster ~299, so on a busy frame it overran `waitForGameFrame`
and **dropped a presented frame**: `applyFineScroll` period 39320 instead of
19656, a period the baseline never produces. That is precisely the scroll hitch
Stages 0–4 were spent removing.

The fix was to make every per-frame chunk small and bounded:

```
SCORE_PHASE 0      idle (~19 cycles)
0 -> 2             snapshot the score into CONV_*, convert place 0
2..6               convert one further decimal place (place = phase - 1)
7                  composeScoreSprites, back to idle
```

`convert24to6` was split into `convertScorePlace` (one place, ≤ 9 subtractions)
plus a thin six-place wrapper. The whole-value form survives for initial setup
and the high-score page, where a spike cannot matter.

The **snapshot** at phase 0 → 2 is what makes spreading the work safe: the six
places are converted from a frozen copy, so a kill landing mid-rebuild cannot
put a half-old, half-new number on screen. It simply re-dirties the score and is
picked up by the next rebuild. Verified directly.

Only phase 7 writes a sprite bitmap. It is bounded at ~510 cycles (~8 raster
lines) with **no data-dependent path** (measured spread across values: 4
cycles), so even from the latest reachable entry raster (311) it finishes by
line ~8 — well clear of the HUD sprites' DMA window at rasters 21..43. The score
bitmap therefore cannot be rewritten while the VIC is fetching it, from any
entry raster.

Cost of the split: worst-case visible latency is 7 frames (~140 ms). The score
**value** is always exact immediately; only the drawn digits trail.

## 6. Timing measurements

Live gameplay, 200 sampled frames per regime, entry raster observed 78..299.

| path | cost | raster lines |
|---|---|---|
| ordinary frame, score unchanged | **19–72 cycles** | < 1.2 |
| convert chunk, realistic score | 72–232 cycles | ≤ 4 |
| convert chunk, worst case (999999) | 127–946 cycles | ≤ 15 |
| compose (the only VIC-visible write) | 411–515 cycles | ≤ 8.2 |
| `renderScoreHud`, synchronous, setup only | ~4,558 cycles | one-time, nothing on screen |

Presented-frame period (`applyFineScroll`, once per presented frame, 300 frames
per regime):

| regime | dropped frames |
|---|---|
| baseline HEAD, score idle | **0 / 300** |
| score changes every frame (realistic) | **0 / 300** |
| ceiling 999999 rebuild every frame (pathological) | **0 / 300** |

Before the split, that last row dropped frames. It no longer does.

## 7. Regression suite

| check | baseline | HUD Phase 1 |
|---|---|---|
| build | clean | clean, no warnings |
| `HUD_PROOF_PATTERN` diagnostic toggle | — | still assembles |
| alignment guards (`blankSprite`, both score bitmaps 64-byte aligned) | — | pass |
| 1400-frame `--physical --trace`: `frame_cycle_deltas` | — | **`[19656]`** exact |
| ” `service_failure_count` / `sprite_start_miss_count` | — | **0 / 0** |
| ” `page_aware`, page A / page B frames | — | true, 722 / 678 |
| stage-wrap capture (1200 frames, `--seed-scroll 30`) | — | `[19656]`, 0 / 0, wrap exercised |
| **dense mux** (900 frames, trace) | frames 900, maxobj 16, maxbatch 8, catchups 6286, replay 450, `[19656]`, svcfail 0, spritemiss 0 | **byte-identical** |
| **y199 / 199-235** (400 frames, trace) | maxobj 9, maxbatch 1, catchups 0, replay 0, `[19656]`, 0 / 0 | **byte-identical** |
| Stage 5 aperture, `check_scroll_edges_rsel1 --aperture 55 246`, dense | 0 body / 0 lastrow diffs | 0 / 0 |
| ” passive | 32 body / 0 lastrow diffs | **32 / 0 — identical to baseline** |
| encounter fixtures A–R | J and L FAIL | **J and L FAIL — identical to baseline** |

Two pre-existing failures are reported rather than hidden: passive
`body_temporal_diffs: 32`, and encounter fixtures `J_wave_start_deferred_then_starts`
/ `L_pressure_clear_wave_eligible`. Both reproduce exactly on the pristine
baseline build, so neither is caused by this work — but neither is clean, and
they are outside this task's scope.

## 8. Score correctness

`addScore`, 14 boundary cases, all pass — 0+1; 255+1 (lo→mid carry); **65535+1
(mid→hi carry)**; 65535+100; 999998+1; 999900+100 → exact ceiling; 999900+200
(saturate); 65280+256 (multi-byte); 0+999999; 500000+499999 → exact ceiling;
500000+500000 (saturate); and two at-ceiling no-ops that correctly queue no
rebuild.

Conversion and rendering verified for **20 values** — all 16 required
(000000, 000001, 000009, 000010, 000099, 000100, 000999, 001000, 009999, 010000,
065535, **065536**, 099999, 100000, 999998, 999999) plus 123456, 500000, 700007,
909090. For each, the six digits **and both 64-byte sprite bitmaps** were
compared against an **independent Python model** — the font re-derived from
ASCII art, not read back from the assembled table. All exact.

Also verified: every byte outside the seven digit rows stays zero; rendering
888888 then 111111 leaves no stale pixels; a value change mid-rebuild renders
the frozen snapshot rather than a torn number.

Acceptance, end to end on the real game:

| criterion | result |
|---|---|
| new game starts showing a **rendered** 000000, nothing pending | pass |
| 65535 + 1 → value 65536, displays **065536** | pass |
| 65436 + 100 crosses the old ceiling | pass |
| 999998 + 1 → exactly 999999 (no early clamp) | pass |
| 999999 + five kills → still 999999, still displays 999999, never wraps | pass |
| high-score table stores and renders values > 65,535 | pass |
| every high-score row renders exactly 6 digits with leading zeroes | pass — `999999 / 123456 / 100000 / 065536 / 000100 …` |
| stored 24-bit high scores match the rendered digits, descending | pass |

High score was widened consistently: `HISCORE_LO/MID/HI`, 3-byte compare in
`scoreQualifies`, 3-byte shift/insert in `insertHiscore`, 3-byte seed,
`HISCORE_ROW_WIDTH` 10 → 11 ("III  DDDDDD"), and `formatScore5` replaced by
`formatScore6` calling the **same** `convert24to6` the HUD uses — so the attract
page and the in-game HUD can never disagree about a value. No disk persistence
was invented.

## 9. Visual verification

Captured from the running game and measured in pixels:

| value | rows | span | centre | colours |
|---|---|---|---|---|
| 000000 | 14..20 (7 px) | 45 px | 192 | one: `(183,255,134)` |
| 065536 | 14..20 | 45 px | **192** | one |
| 999999 | 14..20 | 45 px | **192** | one |
| 123456 | 14..20 | 44 px | **192** | one |

Centre is stable at 192 — the exact display centre of the 384 px frame — for
every value, so **the score does not shift horizontally as it changes**. Single
colour throughout confirms light green with no fringing. The 44 px span for
123456 is simply the `1` glyph's blank leading column; the digit *cells* do not
move.

The rendered strip shows slim 1 px-stroke digits, even spacing, **no visible
join** between the two sprites, leading zeroes present, no label, no frame.

## 10. Testability

No cheat ships. The probes poke `SCORE_LO/MID/HI` and `SCORE_ADD_*` and `JSR`
the shipping routines through an RTS sentinel; there is no diagnostic code in
the default build. The only debug affordance is the pre-existing
`HUD_PROOF_PATTERN` toggle, which is **off** by default and restores the old
four-pattern proof sprites when on.

## 11. Memory map

| region | contents |
|---|---|
| `$2000-$23ab` | engine state (was overflowing; see below) |
| `$235b` / `$235f` | `SCORE_LO/MID/HI` / `SCORE_PHASE` |
| `$2480` | `blankSprite`, 64-byte aligned (guarded) |
| `$2f00` / `$2f40` | score sprite bitmaps L / R, pointers `$bc` / `$bd` (guarded aligned) |
| `$8000-$8299` | new score module: state, font, divisor tables, `convert24to6`, `convertScorePlace`, `composeScoreSprites`, `refreshScoreIfDirty`, `renderScoreHud` |

Three overflow errors were hit and fixed during implementation: the tight
`$2000-$23FF` engine-state block twice (score scratch, then `HISCORE_PAGE_BUF`
growing with the 11-char rows — both re-homed into the `$8000` module), and the
main code segment once when `refreshScoreIfDirty` grew into the state machine
(also re-homed). All are structural placements, not workarounds.

## 12. Scope

Score only, as instructed. **Not** touched: overheat mechanic or its HUD, lives
display, weapon/upgrade indicators, decorative framing, the complete HUD layout,
raster laser, player art, scrolling and turret behaviour. No complete HUD was
designed. `src/background_turrets.asm` is unmodified.

## 13. Manual review checklist

1. Build and run: `java -jar KickAss.jar src/main.asm -odir build -o build/shooter.prg -vicesymbols`, then start a game.
2. **Start state** — the top border shows a green `000000`, centred, no "SCORE" label, no box.
3. **Slimness** — digits are 1 px stroke, 5 px wide, 7 px tall. Confirm this reads as instrumentation, not chunky bitmap text.
4. **Join** — kill a few enemies and watch the gap between digit 3 and digit 4. It should be indistinguishable from the other gaps.
5. **Stability** — let the score climb past 001000 and 010000. The number must not shift horizontally; only glyphs change.
6. **Leading zeroes** — always six digits.
7. **Latency** — digits trail a kill by up to 7 frames. That is deliberate; confirm it looks acceptable rather than laggy.
8. **Handoff** — watch for flicker in the top border during dense waves. There should be none, and gameplay sprite capacity should look unchanged.
9. **High-score page** — die, let the attract page appear, and confirm six digits per row with leading zeroes.

Font appearance and exact position are tunable presentation. If a glyph reads
poorly, it is a row edit in `scoreFont`; if the number wants moving, it is
`HUD_SCORE_X_L`. Neither implies architectural change.

## 14. Files changed

* `src/main.asm` — the only source file modified.
* `docs/hud-phase1-six-digit-score-worklog.md` — new, per AGENTS.md session continuity.
* `reports/hud-phase1-six-digit-score.md` — this report.

Nothing committed, staged, tagged or pushed.
