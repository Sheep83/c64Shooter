# 19656 — HUD Phase 1.1: Presentation Pass + Restore Collision

**Result: GREEN.**

---

## 1. Starting git / worktree state

Branch `main`, HEAD `f71ea24` (*Add stable scroller/pointer checkpoint report*),
continuing the uncommitted Phase 1 tree exactly as it was left:

```
 M src/main.asm
?? docs/hud-phase1-six-digit-score-worklog.md
?? reports/hud-phase1-six-digit-score.md
```

Nothing committed, staged, tagged or pushed.

| build | SHA-256 |
|---|---|
| pristine HEAD baseline (rebuilt out-of-tree for comparison) | `f1d08a0f5d2337eef0a75a28a68d4261e9166474e47d655f9c886aa4f2ec6652` |
| Phase 1 (start of this pass) | `3a8158152f9ef3f12a76cf9bd50bf15f1e0f5f49fb148aa0e83223ae051f80c4` |
| **Phase 1.1 (shipping)** | `fd42763699bf51c2edf463249d785470eaf499faef4f457dac7f17fe517f8f8c` |
| Phase 1.1 with `DEBUG_PLAYER_INVULNERABLE = 1` (comparison only) | `c7cdd099933deacf…` |

All Phase 1 invariants are preserved: 24-bit score and high score, saturation at
999999, two hires HUD score sprites on physical slots 4/5, deferred refresh with
frozen-snapshot semantics, repaired A/B pointer publication, exact PAL.

## 2. Font design and exact dimensions

**6 px wide × 21 px tall**, inside the existing 8 px byte-aligned digit cell
(2 px gap). Six digits span `6×8 − 2 = 46 px`.

Drawn from scratch on the grid in `font_design.py` and generated into
`scoreFont`. Not traced from, or byte-copied from, any commercial face.

Structural grid: bar rows at 0 / 10 / 20, stems at columns 0 and 5. Stroke is a
single pixel everywhere — the horizontal-run audit shows only runs of 1 (stems)
and the deliberate bar lengths, with no modulation anywhere.

## 3. How it captures the requested character

Brief was Berthold City / the MU-TH-UR terminal typography in *Alien*.

* **Tall and condensed** — 21:6 proportion, about 3.5:1. This is the dominant
  cue; it is what makes the row read as instrumentation rather than arcade text.
* **Geometric and squared** — flat horizontal terminals, chamfered (not rounded)
  bowl corners, no curves anywhere. `0` is a chamfered rectangle, `8` the same
  with a middle bar.
* **Thin, consistent stroke** — one pixel, unmodulated, which at this height
  reads as the fine hairline of a technical face rather than a chunky numeral.
* **Systematic, not decorative** — `6` and `9` are exact 180° rotations of each
  other; `4`'s crossbar sits on the same structural row as `3`'s and `8`'s
  middle. `2` and `7` use straight stepped diagonals.
* **Restrained** — no serifs, no flourish; the only concession to legibility at
  this width is the base bar on `1`, which is itself a technical-face idiom.

## 4. Exact sprite rows / pixels and raster geometry

**Measured before designing**, not assumed. Both score bitmaps were filled with
solid rows and the running game screenshotted:

```
lit screen rows: 7..27  (21 rows), 48 lit px on every row
```

All 21 sprite rows are presented, with no clipping at either end. So:

| item | value |
|---|---|
| `HUD_Y` | 22 → sprite body rasters **22..42** |
| `HUD_HANDOFF_RASTER` | 43 (after the body ends) |
| `HUD_HANDOFF_COMPLETE_RASTER` | 56 |
| glyph rows used | **0..20 — the full 21** (`HUD_SCORE_TOP_ROW` 7 → 0, `HUD_SCORE_GLYPH_H` 7 → 21) |
| `HUD_SCORE_X_L` / `X_R` | 161 / 185 |
| span | 46 px |

The full height was available without touching the raster architecture. Measured
on screen: **rows 7..27 (21 px tall), span 46 px, centre 191** for every value
tested. The one-pixel span variation on values starting with `1` is that glyph's
blank leading column — the digit *cells* are fixed, so there is no
value-dependent horizontal movement.

## 5. Font / compositor changes

`scoreFont` is now 10 × 21 bytes; `scoreFontOffset` is `i × 21` (max 209, still
one byte). The compositor was already parameterised by `HUD_SCORE_GLYPH_H` and
`HUD_SCORE_TOP_ROW`, so it adapted without restructuring.

Two real changes:

1. The digit index moved from X to Y (`ldy CONV_DIGITS+col / lda scoreFontOffset,y / tay`)
   because **X now selects the buffer**.
2. Every store became `sta ADDR,x` where X is 0 or `$80` — see §6.

With `TOP_ROW = 0` and 21 rows, the compose writes all 63 meaningful bytes of
each sprite, so the "stale pixel" and "transparency outside the digit rows"
questions are now structurally closed: every owned byte is rewritten every time.

The independent oracle was repointed at the *design* source (`font_design.py`,
re-derived from the ASCII art) rather than the assembled table, so the test still
proves the build against something independent of it.

## 6. Composition timing — and why it became double buffered

The taller font tripled the compose: **1,169–2,152 cycles, up to ~34 raster
lines** in situ, against ~400 cycles in Phase 1.

Phase 1's guarantee was that the bitmap write is safe *from any entry raster*.
At 34 lines that is no longer true — from a late entry it would still be writing
during the HUD sprites' DMA at rasters 21..43 of the following frame. The
measurement made this explicit: the probe's own headroom line printed
"finish by line 22 < 21", which is false.

A raster gate was implemented first and then **rejected**: the compose cost
varies with ambient badline and sprite DMA, so any fixed "latest safe start"
constant is tuned against a number that moves between runs. That is a fragile
guarantee.

**The score sprites are now double buffered.** The compositor draws into the
pair the VIC is *not* fetching, then publishes it by rewriting `hudProofPtr` —
which the existing `hudBorderSetup` republishes to **both** `$07F8` and `$2BF8`
at the line-1 IRQ, i.e. through the repaired publication path rather than around
it. The compose therefore has **no raster deadline at all**; its duration
stopped being a correctness question.

* The back pair reuses HUD slots 2/3 (`$2f80` / `$2fc0`), which were already
  allocated in the 4 × 64 B HUD block but pointed at `blankSprite` and never
  displayed — **no new memory**.
* The buffers are exactly `$80` apart, so one index register selects a pair and
  the compositor is not duplicated (+1 cycle per store, no code duplication).
* The two-byte publish is held under `SEI` so `hudBorderSetup` cannot observe a
  half-updated pair (which would show digits 1–3 from one buffer and 4–6 from
  the other for a frame). ~12 cycles of added IRQ latency, on compose frames
  only; `sprite_start_miss_count` remains 0.
* Game start renders into **both** pairs, so the first publish can never swap in
  a buffer that was never written.

Proven in a live game over 140 frames of continuous scoring:

| check | result |
|---|---|
| published pair alternates A↔B | 20 flips, pairs `$bc/$bd` ↔ `$be/$bf` |
| published pair was ever the pair being composed | **0 / 140** |

Per-frame costs (unchanged structure, seven-frame rebuild):

| path | cost |
|---|---|
| idle frame, nothing to do | **19–72 cycles** |
| convert chunk (one decimal place) | 71–937 cycles |
| compose (now off-screen, no deadline) | 1,169–2,152 cycles |
| synchronous setup render | ~5,466 cycles |

## 7. Player colour

**`PLAYER_COLOUR_NORMAL = 14`** (VIC-II light blue).

The audit found the real problem: the hull was **110 pixels of `$D026`** — the
*shared* light grey that every enemy and turret also uses — while only 16 pixels
(the spine and exhaust) used the per-sprite `OBJECT_COLOUR`. So setting
`OBJECT_COLOUR` alone would have recoloured a thin stripe and left the ship grey,
and changing `$D025`/`$D026` would have recoloured every enemy and turret, which
the brief forbids.

The fix keeps both constraints: multicolour bit pairs `10` and `11` were swapped
in `playerSprite` and `playerFireSprite`, so the hull now indexes the
**per-sprite** colour register and the old spine becomes a light-grey highlight.
The silhouette is byte-for-byte identical — this is a palette-slot remap, not new
artwork. Dark-grey shading is untouched.

`$D025` / `$D026` verified still 11 / 15 — **no enemy or turret colour changed.**
Explosion sprites already used the per-sprite slot and were left alone.

## 8. Muzzle colour

**`PLAYER_COLOUR_MUZZLE = 2`** (VIC-II red). Driven by the existing muzzle timer
in the existing colour-state machinery: the fire path sets red alongside the
firing bitmap, and `updatePlayerCombatEffects` restores blue when
`PLAYER_MUZZLE_TIMER` expires — the same place that already restored the bitmap.

Verified in pixels over 24 consecutive frames of held fire: a clean **3 red
frames per volley** (`PLAYER_MUZZLE_TIME = 3`) then back to blue, repeating on
the fire cadence — 232 red px / 220 blue px, never mixed.

## 9. Collision-disabled audit

```
.const DEBUG_PLAYER_INVULNERABLE = 1   // 0 = normal: collisions can kill the player.
                                       // 1 = development: capturePlayerCollision still reads/clears
                                       // $D01E and runs every overlap test, but never sets PLAYER_HIT,
                                       // so unattended scrolling tests can run indefinitely.
```

A **documented compile-time development toggle**, at `src/main.asm:528`, with
exactly two guarded sites (`capturePlayerCollision`'s `!hit` branch, and the
suppressed-frame collision-safety path). Both suppress **only** the final
`PLAYER_HIT` store — `$D01E` is still read and cleared, and every overlap test
still runs, in both settings.

It is **not** a workaround for a defect: there is no bypassed call, no stub, no
early return, no temporary invulnerability state, no fixture leakage, and no
recorded unresolved bug. It exists so unattended scrolling captures can run
without the player dying. The stop-condition in the brief does not apply.

## 10. Restoration change

One character: `= 1` → `= 0`. Nothing else in the collision path was touched.

The regression harness already anticipated this — `tools/vice_scroll_test.py:161`
sets a 255-life stock with the comment *"Long-run test stock; combat/death/respawn
stay active."*

## 11. Death / respawn / game-over tests

Driven by the **shipping collision path** — no forced `PLAYER_HIT` anywhere:

| check | result |
|---|---|
| collision kills the player | pass — `PLAYER_STATE` seen `[0, 1, 2]` (alive / exploding / respawning) |
| death animation runs | pass |
| respawn returns the player to alive | pass |
| lives decrement | pass — `[3, 2]` |
| respawned player is blue | pass — `OBJECT_COLOUR = 14` |
| last life lost → GAME OVER state | pass — `GAME_STATE = 2` |
| non-qualifying run → attract menu | pass — `GAME_STATE = 0` |
| fire from attract starts a new game | pass — `GAME_STATE = 1` |

Invulnerability after respawn is the existing `PLAYER_RESPAWN_TIME` blink window,
preserved unchanged; the probe observed the respawning state before the player
returned to alive.

## 12. 24-bit high-score lifecycle

Full end-to-end run, in order, on the real game:

| # | check | result |
|---|---|---|
| 1–2 | new game, score starts `000000` **and is rendered** | pass |
| 3 | kills award score in real play | pass |
| 4–5 | death by collision, then respawn | pass |
| 6 | game over → attract | pass |
| 11 | fire restarts | pass |
| 12 | new game resets live score to `000000`; high-score table intact | pass |
| 7 | a **123456** run qualifies via the live `checkHiscore` path and routes to `ENTER_INITIALS` | pass — `GAME_STATE = 3`, `NEW_SCORE_RANK = 0` |
| 8 | insert places it at the top | pass |
| 9 | every row renders exactly six digits with leading zeroes | pass |
| 10 | values above 65,535 correct | pass — `999999 / 250000 / 123456 / 065536 / 000100 …` |

`065536` renders with its leading zero; stored 24-bit values match the rendered
digits exactly; the table stays sorted descending.

Separately, the Phase 1 acceptance suite still passes in full: `65535 + 1` →
`065536`, `999998 + 1` → exactly `999999`, `999999 +` five kills saturates and
never wraps, and an award at the ceiling queues no needless rebuild.

## 13. Pointer / HUD handoff proof

Live gameplay, 60 frames per sample point:

| check | result |
|---|---|
| at `hudBorderHandoff` entry: `$07F8+4/5` == `$2BF8+4/5` == `hudProofPtr` | pass, 60/60 |
| the published pair is always a valid score pair | pass |
| the published pair is **never** the pair the compositor may write | pass, 0 violations |
| at raster 80 (post-handoff): both pointer pages match the gameplay plan | pass, 60/60 |
| frames where slot 4+ was actually reclaimed for gameplay | 60/60 |
| sprite capacity | `max_objects 16`, `max_batches 8` — identical to baseline |

No permanent sprite reservation; the HUD owns slots 4/5 through their DMA and
gameplay takes them back every frame, exactly as in Phase 1.

## 14. Full regression

`frame_cycle_deltas` is exact `[19656]` in every capture below.

| capture | frames | deltas | svc fail | sprite miss | max obj | max batch | catchups | replay |
|---|---|---|---|---|---|---|---|---|
| shipping, ordinary | 1400 | `[19656]` | 0 | 0 | 9 | 0 | 0 | 4 |
| shipping, **dense** | 900 | `[19656]` | 0 | 0 | 16 | 8 | 6286 | 450 |
| shipping, **y199 / 199-235** | 400 | `[19656]` | 0 | 0 | 9 | 1 | 0 | 0 |
| shipping, **stage wrap** | 1200 | `[19656]` | 0 | 0 | 9 | 1 | 3 | 9 |
| invuln variant, dense | 900 | `[19656]` | 0 | 0 | 16 | 8 | 6286 | 450 |
| invuln variant, y199 | 400 | `[19656]` | 0 | 0 | 9 | 1 | 0 | 0 |
| **baseline HEAD, dense** | 900 | `[19656]` | 0 | 0 | 16 | 8 | 6286 | 450 |
| **baseline HEAD, y199** | 400 | `[19656]` | 0 | 0 | 9 | 1 | 0 | 0 |

Dense and y199 are **byte-identical across all three builds** — every metric,
including `catchups 6286` and `replay 450`. An invulnerable-variant build was
made specifically so the scroller/mux comparison isolates the presentation work
from the collision restoration; both agree with baseline.

| other check | result |
|---|---|
| clean build, no warnings | pass |
| `HUD_SCORE_CODE_LIMIT` | `hudScoreCodeEnd = $8557` vs limit `$8600` |
| Stage 5 aperture `--aperture 55 246` (passive, shipping) | 0 body / 0 lastrow diffs |
| ” (passive, invuln variant) | 0 / 0 |
| ” (dense, shipping) | 0 / 0 |
| page-aware fallback | `page_aware: true`, both pages exercised in every capture |
| `$07F8` / `$2BF8` publication | §13 — pass |
| HUD slots reclaimed after handoff | §13 — 60/60 |
| no permanent sprite-capacity loss | `max_objects 16` / `max_batches 8`, unchanged |
| score changes under heavy gameplay drop presented frames | **0 / 300** in all three regimes (idle, realistic, pathological ceiling rebuild) |
| collision-enabled gameplay stability | 1400 + 900 + 400 + 1200 frames with collision live: 0 service failures, 0 sprite-start misses, exact PAL |
| encounter fixtures A–R (incl. six-enemy `B_authored6_presented_as_5`) | J and L FAIL, all others PASS — **identical to baseline** |

## 15. Known pre-existing artifacts

**Encounter fixtures J and L** (`J_wave_start_deferred_then_starts`,
`L_pressure_clear_wave_eligible`) fail on the Phase 1.1 build. They fail
**identically on the pristine HEAD baseline**. Not caused by this pass, and
outside its scope.

**Correction to a Phase 1 finding.** Phase 1 reported passive
`body_temporal_diffs: 32` as a stable pre-existing artifact. It is **not
stable**. Re-running the *pristine baseline* twice gives:

```
baseline passive run 2:  body_temporal_diffs: 32
baseline passive run 3:  body_temporal_diffs: 0
```

The diffs sit at rasters 61–62 (8 px wide), just inside the top of the body band
(60..231) where gameplay sprites reclaimed after the HUD handoff appear — so the
metric tracks CIA-random wave timing, not terrain correctness. It is run-to-run
variance in the passive fixture, and Phase 1's characterisation of it as a fixed
property of the build was wrong. Phase 1.1 measured 0 on both its builds, which
is likewise not evidence of an improvement.

The accepted authored multi-turret cosmetic flicker was not touched or reopened.

## 16. Manual checklist

1. **Tall score** — the score should fill essentially the whole top-border band, not a short strip. Roughly three times the previous height.
2. **Character** — tall, narrow, squared, hairline strokes; should read as a terminal readout, not arcade text.
3. **Readability** — check all ten digits: `0`/`8` differ by the middle bar, `6`/`9` are rotations, `1` has a base bar.
4. **Centring and join** — the number should sit centred; the gap between digits 3 and 4 (the sprite join) should be indistinguishable from the others.
5. **Update stability** — score past `001000` and `010000`: digits change, the number must not shift sideways.
6. **Blue player** — the ship should be clearly light blue with a light-grey highlight down the fuselage.
7. **Red muzzle** — holding fire flashes the ship red for ~3 frames per volley, returning to blue between shots.
8. **Visibility** — the ship should no longer disappear into the grey terrain.
9. **Enemies unchanged** — enemies and turrets should look exactly as before.
10. **Damage and death** — you can now be killed. Take a hit: explosion plays, a life is lost, the ship respawns blue and blinks briefly invulnerable.
11. **Game over** — lose all lives; GAME OVER holds, then either the initials screen (if you qualified) or the attract screen.
12. **High-score page** — six digits per row with leading zeroes; a score above 65,535 displays correctly.
13. **Another game** — fire from the attract screen: the live score resets to `000000` and the high-score table is intact.

Font shape and position remain tunable presentation: a glyph edit is a row in
`scoreFont`, a move is `HUD_SCORE_X_L`. Neither implies architectural change.

## 17. Files changed

* `src/main.asm` — the only source file modified.
* `docs/hud-phase1-six-digit-score-worklog.md` — Phase 1.1 section appended.
* `reports/hud-phase1-1-presentation-collision.md` — this report.

Nothing committed, staged, tagged or pushed.
