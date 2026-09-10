# High-score lifecycle corruption + score font height — worklog

## Objective
1. Fix intermittent GAME OVER -> HIGH SCORE corruption and the bad next-game
   start that follows it.
2. Reduce the score font from 21 px to ~16 px tall.
3. Preserve all accepted Phase 1 / 1.1 work.

## Starting state
- Branch `main`, HEAD `308f430` ("high score hud working. high score corruption to fix").
- Working tree clean at start.
- Build from HEAD reproduces the Phase 1.1 shipping hash exactly:
  `fd42763699bf51c2edf463249d785470eaf499faef4f457dac7f17fe517f8f8c`.

## Priority 1 — leading hypothesis (from source audit, pre-measurement)

`$D018` is written in exactly three places (`grep 'sta VIC_MEMORY_SETUP'`):
- `src/main.asm:926` — one-time boot init (page A).
- `src/main.asm:7198` — `ssFlipPage`, inside the disabled `OPT_SS_FLIP_PROOF`.
- `src/main.asm:8011` — `ssPublishCoarseFlip`, the coarse page flip.

So after boot, the ONLY thing that moves `$D018` is the coarse scroll flip.
Neither `endGame` nor `startGame` ever restores it to page A.

Meanwhile every piece of *software* page state asserts "fresh game boots on
page A":
- `ssFlipCoarseReset` (`src/main.asm:7690`) zeroes `SS_PAGEB_ACTIVE` and sets
  `ssBatchPtrStore+2 = $07`, commented "a fresh game boots on page A".
- `ssInitPageB` (`src/main.asm:7159`) sets `BG_ACTIVE_PAGE = 0`,
  commented "boot displaying page A".

Predicted consequences when the last life is lost while `BG_ACTIVE_PAGE == 1`
(i.e. `$D018 == $AE`, VIC showing page B at `$2800`):

(a) `endGame` / `enterGameOver` / `enterInitials` / `enterMenu` draw text into
    `$0400` (KERNAL `chrout #147` + direct stores), but the VIC is still
    fetching `$2800` -> the GAME OVER / initials / high-score pages are
    invisible under stale terrain. No crash; input still works.

(b) `startGame` -> `initBackground` paints terrain page-aware through
    `copyIncomingRowToScreen` (`src/main.asm:6259`, `ldy BG_ACTIVE_PAGE`), and
    `BG_ACTIVE_PAGE` is STILL 1 at that point, so the fresh terrain is painted
    into page B.

(c) `ssInitPageB` then unconditionally copies A -> B, overwriting that fresh
    terrain with the contents of `$0400` — which is the just-drawn new-game
    `$0400`: cleared screen + `setupLivesDisplay`'s "LIVES 3". `$D018` is still
    `$AE`, so page B is what the player sees.

That predicts all four observed symptoms including "LIVES 3 in the terrain".

## Next step
Prove (a)-(c) in VICE with a controlled good/bad pair, by choosing the death
frame on `BG_ACTIVE_PAGE == 0` vs `== 1`.

## Priority 1 — PROVEN AND FIXED

### Reproduction (pre-fix, HEAD build `fd427636…`)
`tools/vice_lifecycle_rate.py` — 15 lifecycles, fatal hit at 15 different
frame offsets: **7 / 15 ended with `$D018` selecting page B**. Effectively a
coin flip on coarse-flip parity at the moment `endGame` runs.

### First divergence
Not at the fatal hit — at `endGame`. Good and bad runs are identical up to it.
The first divergent byte is `$D018`:

| sample | good | bad |
|---|---|---|
| `game_over_entry` `$D018` | `$1F` (page A) | `$AF` (page B) |
| initials screen: prompt on the VISIBLE page | yes | **no** — prompt is in `$0400`, VIC fetches `$2800` |
| initials screen: visible-page non-space cells | 35 | **1000** (stale terrain, every cell) |
| next new game: `$D018` / `BG_ACTIVE_PAGE` | `$1F` / 0 | **`$AF` / 0 — hardware B, software A** |
| next new game: visible matrix | 0 non-terrain cells | **1000 non-terrain cells (all spaces)** |
| next new game: "LIVES 3" in visible matrix | 0 | **1** |
| next new game: `SCROLL_ROW` | 397 | **397 — correctly reset in BOTH cases** |

`tools/vice_lifecycle_loop.py` against the pre-fix build shows a **1:1 causal
chain**: every loop with `game_over_page_A=FAIL` is followed by a loop with
`new_game_page_A` / `new_game_matrix_clean` / `no_lives_label` all FAIL
(0->1, 1->2, 5->6, 6->7). Same defect, two visible symptoms.

### Root cause
`$D018` is written in only two live places (boot init; `ssPublishCoarseFlip`).
Neither `endGame` nor `startGame` restored it, while `ssFlipCoarseReset` and
`ssInitPageB` both already asserted page A **in software**. So:

1. A game ending on page B leaves the VIC fetching `$2800` while GAME OVER /
   initials / high-score / menu all draw into `$0400` -> invisible screens
   under stale terrain (no crash; input unaffected -> Fire still works).
2. `startGame` -> `initBackground` paints page-aware
   (`copyIncomingRowToScreen`, `ldy BG_ACTIVE_PAGE`) and `BG_ACTIVE_PAGE` is
   still 1, so the fresh terrain goes to `$2800`.
3. `ssInitPageB` then copies A -> B, overwriting that terrain with `$0400` —
   which holds the cleared menu screen plus `setupLivesDisplay`'s "LIVES 3".
   `$D018` still selects B, so THAT is what the player sees.

`SCROLL_ROW` was never wrong. "Starts partway through the level" is the
*presentation*: the origin viewport is never presented; the player sees a blank
matrix that fills in as the inactive-page builder writes into the page the VIC
is actually showing, with "LIVES 3" carried down by successive coarse steps.

### Fix
- New `ssSelectPageA` (after `ssInitPageB`): forces `$D018`'s screen nibble to
  page A (preserving the char base) and `BG_ACTIVE_PAGE = 0`.
- Called from `endGame` (non-gameplay screens draw on the displayed page) and
  from `startGame` **before** `initBackground` (fresh paint targets it).
- Secondary: `setupLivesDisplay` no longer stamps "LIVES 3" into the terrain
  matrix — the same retired-character-HUD scribble Phase 1 removed for
  "SCORE 00000". It keeps the `PLAYER_LIVES` stock reset.

### Post-fix
- `vice_lifecycle_rate.py`: **0 / 15** ended on page B; prompt on the visible
  page in 15/15; visible non-space 34-36 (text only).
- `vice_lifecycle_loop.py`: **14 / 14 loops, 126 / 126 checks, 0 failures.**

Build after fix: `c73c82900330fab8371d028517b217e43bd08478f9b31aa2ca771221629772e3`.

## Next step
Priority 2: score font 21 px -> 16 px.

## Priority 2 — score font 21 px -> 16 px: DONE

- `tools/score_font_design.py` is the new design source of truth (ASCII art) and
  an independent oracle: it re-derives the byte table from the drawing and
  verifies it back out of the PRG (`--verify build/shooter.prg --font-addr`).
  160 bytes MATCH.
- `HUD_SCORE_GLYPH_H` 21 -> 16, `HUD_SCORE_TOP_ROW` 0 -> 2 (centred in the SAME
  21-row sprite body). `HUD_Y`, the DMA window and both handoff rasters are
  untouched -> no raster geometry change.
- Measured on screen: rows 9..24 (16 px), x 169..214, span 46 px, one colour
  (183,255,134). Right edge fixed at 214 for every value.
- Compose cost, same method, same probe:
  21 px 1282-1453 cy (20.3-23.1 lines, median 1389);
  16 px 1012-1129 cy (16.1-17.9 lines, median 1014).
- Double buffering intact: 0/40 composes into the published pair; both pairs
  `$bc/$bd` and `$be/$bf` alternate.

## Tooling notes (matter for anyone repeating this)

- `tools/vice_scroll_test.py` does NOT quit VICE when it finishes; a driver must
  kill the pid it launched or it will hang in `wait`.
- dense / y199 must be captured with `--physical`. Without it the breakpoint is
  once per PRESENTED frame, which under dense load is every OTHER physical
  frame; `check_raster_capture` then windows events over 19656 cycles of a 39312
  cycle interval and reports ~4 spurious "service failures" per frame.
- VICE's `m` output groups hex in fours (`64 64 64 64  64 64 64 64`), so a
  `[0-9a-f]{2}\s` repeat regex silently stops after 4 bytes.
- `tools/check_scroll_capture.py` is BROKEN against the current memory map: it
  reads `BG_COARSE_*` from a `$2920` dump, but OPT_SS_RELOCATE moved that block
  to `$9000+`. Fails identically on the pristine baseline.
  `tools/check_stage_wrap.py` (new) covers the scroll-position half.
- `tools/vice_raster_lifecycle.py` is BROKEN: it references
  `TURRET_DESIRED_STYLE`, which exists in neither build's symbol table.
  Death/respawn coverage moved into `tools/vice_lifecycle_loop.py`.

## Final state
Build `809b5edc2eb004f55bf027b2d4bdd92df7ba89bebbe0be2d33fdb9b3496062b7`.
Nothing committed, staged, tagged or pushed. Report at
`reports/high-score-lifecycle-corruption-fix.md`.
