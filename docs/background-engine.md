# Minimal scrolling-background prototype — design notes

## Why this branch exists

A previous attempt (`background-scrolling-works-but-glitches`) built a full
scrolling-background engine (starfield integration, turrets, dual shadow
buffers, per-cell colour, metatiles) and, along the way, replaced
`armFirstBatch` with a raster-split routine that unconditionally armed the
first sprite-multiplex batch at the HUD/playfield split line instead of its
own natural (often earlier) raster line. Automated `-exitscreenshot`
verification looked clean, but **human playtesting disagreed**: scrolling
still glitched, and a repeatable sprite-corruption regression had been
introduced. That branch was too broad and too entangled with the existing
raster/multiplexer architecture to safely keep patching.

This branch starts over from the last known-good revision **before any
background/stage-engine work** (`2d13fa2`) with a deliberately narrow goal:

> Prove that a vertically scrolling character background can coexist
> cleanly with the existing, fully-working game and sprite multiplexer.

Explicitly out of scope for this branch: starfield integration (disabled
outright during PLAYING instead), turrets, background entities, hitscan vs.
scenery, per-cell terrain colours, dual shadow buffers, stage completion,
CharPad pipeline, multiload prep, optimisation beyond what smoothness
needs.

## Two concrete lessons carried over from the previous attempt

1. **Off-by-one in the flip timing.** The previous branch set
   `SCREEN_FLIP_PENDING` when `SCROLL_FINE` became 7 (a chunk frame, not
   the wrap), so the very next raster split presented the new screen while
   `SCROLL_FINE` was still 7 (old fine phase, not yet wrapped to 0):
   `old/fine7 -> new/fine7 -> new/fine0` instead of `old/fine7 ->
   new/fine0`. Here, `SCREEN_FLIP_PENDING` is set **inside
   `beginNextCoarseState`**, which only runs at the actual fine 7→0 wrap,
   in the same pass that wraps `SCROLL_FINE` to 0 - so the next
   `hudSplitIRQ` always presents the new fine phase and the new screen
   together.
2. **Don't move the sprite multiplexer's first-batch raster line.** The
   previous branch's `armScrollSplit` armed the HUD-split IRQ unconditionally
   first, at a fixed line (58), which could be *later* than where the first
   sprite batch actually needed to fire (batches are scheduled by sorted
   object Y position and can legitimately be earlier than the HUD split).
   That delay is a plausible cause of the sprite corruption found in human
   playtesting. Here, `armFirstBatch` is otherwise unchanged - it still
   arms whatever the first batch's own `BATCH_RASTER` line is. The only
   addition is `armNextEvent`, a shared merge that decides whether the HUD
   split or the next sprite batch is next, by comparing raster lines, and
   arms whichever is actually earlier. See `armNextEvent`'s comment in
   `src/main.asm` for the full mechanism.

## Design

- **No shadow buffers at all.** The starfield is disabled during PLAYING
  (see `startGame`/`gameLoop`), and this prototype has no turrets/entities,
  so nothing ever mutates a screen while it's active. That makes the
  currently-ACTIVE screen itself a safe, direct read source for relocating
  rows into the inactive one - no separate "ground truth" copy is needed.
- **Two character screens**, Screen A (`$0400`) and Screen B (`$3400`, the
  same free 1K-aligned gap used before, between the health-sprite pool and
  the `$3800` charset RAM), selected by `ACTIVE_SCREEN` (0/1) and `$D018`'s
  screen-base nibble. `$D018`'s charset nibble (bits 1-3, `$3800`) is never
  touched.
- **One fixed terrain colour** (`TERRAIN_COLOUR`), `$D800` rows 1-24 filled
  once at game start and never touched again - no colour-RAM work at all,
  scrolling or otherwise.
- **A trivial raw row source**: `rawRowGlyph(rowIndex)` returns a single
  digit-glyph screen code (`rowIndex mod 10`), repeated across all 40
  columns - no table, no metatiles. Chosen specifically so a coarse advance
  is trivially verifiable by eye (rows read 0,1,2,...,9,0,1,... continuously
  - any skip or repeat is immediately visible). Milestone 11 (a larger
  deterministic raw row *map*, still no metatiles) can replace just
  `rawRowGlyph`'s body later.
- **Work spread across the 8 fine-scroll frames**: `relocateNextChunk`
  relocates up to `CHUNK_ROWS` (4) rows/frame from the active screen into
  the inactive one; `beginNextCoarseState` (at the 7→0 wrap) renders the one
  genuinely new row, finishes any remaining relocation, and only then sets
  `SCREEN_FLIP_PENDING`.
- **The flip is committed inside `hudSplitIRQ`**, at the same instant it
  already writes the real `SCROLL_FINE` value into `VIC_CONTROL_1` - both
  take effect for the same playfield scan, every time.
- **Resident code placement**: the new background/state code didn't fit in
  the `$0801-$1fxx` segment's remaining headroom, so it's placed at `$2920`
  - an already-unused gap (confirmed free in the pre-background baseline's
  own memory map) between the `$2400` block and the health-sprite pool at
  `$3000`. (A `$6000` placement was tried first and works, but pads the
  `.prg` with ~10KB of dead space that made every VICE test run dramatically
  slower for no runtime benefit - reverted in favour of the closer gap.)

## Milestones (status)

1. Restore the exact known-good game/multiplexer baseline (commit
   `2d13fa2`). **Done.**
2. Confirm it still runs cleanly in VICE with enemies and full gameplay.
   **Done** - `-exitscreenshot` at ~35M cycles into an unpiloted playthrough
   shows clean sprites, HUD, no starfield interference.
3. Disable the starfield during PLAYING only (menus/game-over unchanged).
   **Done.**
4. Add a completely static background to rows 1-24 (single fixed colour,
   crude placeholder glyphs, no metatiles). **Done** (`initBackground`).
5. Confirm zero sprite regression. **Done** in the same pass as 4/6-9 below
   (see verification note).
6. Add fine-Y scrolling only (`$D011` bits 0-2, all other bits preserved).
   **Done.**
7. Confirm the static matrix moves smoothly through the 8 fine positions.
   **Partially verified** - see verification note below.
8. Add exactly one coarse-row transition mechanism. **Done**
   (`beginNextCoarseState`/`relocateNextChunk`).
9. Coarse transition occurs only on the fine 7→0 wrap, with the off-by-one
   from the previous branch fixed. **Done**, reasoned through carefully;
   needs the same seam-by-seam visual confirmation as milestone 7.
10. Run the full game with enemies/multiplexer and watch continuously.
    **Partially verified** - see below; VICE screenshot sampling is not a
    substitute for the human-playtesting acceptance test the user
    specified, and that has not happened yet on this branch.
11. Feed the new row from a larger deterministic raw row map. **Not
    started** - deliberately deferred until 7/9/10 are confirmed stable by
    a human.
12. Stop. **Not reached.**

### Verification note (honesty about method limits)

Implemented milestones 3-9 together (they're one coherent pipeline) rather
than as fully separate builds, then verified via `-exitscreenshot` at
several points across ~5M cycles (~10 coarse transitions) of an unpiloted
PLAYING session with full enemy spawning/combat/multiplexer active from the
start (per the user's instruction not to validate the background in an
artificially empty game): HUD row 0 stays fixed and readable, the digit-row
background pattern is present and un-corrupted, enemy/player sprites render
correctly with no visible garbling, across multiple samples spanning
several coarse steps. This is consistent with - but does **not** prove -
milestones 7/9/10's specific "no periodic 8-pixel snap/glitch, no raster
seam" requirement, which the user has explicitly and correctly flagged as
something only continuous human-visible video can really confirm. **This
branch should not be considered to have passed milestones 7/9/10 until a
human has actually watched it run.**
