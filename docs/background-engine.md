# Minimal scrolling-background prototype — design notes

## Why this branch exists

A previous attempt (`background-scrolling-works-but-glitches`) built a full
scrolling-background engine (starfield integration, turrets, dual shadow
buffers, per-cell colour, metatiles) and, along the way, replaced
`armFirstBatch` with a raster-split routine that unconditionally armed the
first sprite-multiplex batch at the HUD/playfield split line instead of its
own natural (often earlier) raster line. Automated `-exitscreenshot`
verification looked clean, but human playtesting disagreed: scrolling still
glitched, and a repeatable sprite-corruption regression had been
introduced. That branch was too broad and too entangled with the existing
raster/multiplexer architecture to safely keep patching.

This branch (`background-scroll-minimal`) starts over from the last
known-good revision before any background/stage-engine work (`2d13fa2`)
with a deliberately narrow goal:

> Prove that a vertically scrolling character background can coexist
> cleanly with the existing, fully-working game and sprite multiplexer.

## History on this branch: a fixed HUD is not a "day one" feature

The first version of this prototype kept `FREE`/`LIVES`/`SCORE` fixed on
row 0 while rows 1-24 scrolled. That required a mid-frame `$D011`/`$D018`
raster split, which in turn required merging a second raster event
(`hudSplitIRQ`) into the sprite multiplexer's own schedule
(`armNextEvent`), and a second character screen (`$0400`/`$3400`) so the
flip could be atomic. Human playtesting found real bugs in that approach
twice in a row (`HUD_SPLIT_PENDING` never re-armed, so nothing scrolled at
all; then Screen B's row 0 was never given HUD content, so it briefly
showed placeholder garbage) - each screenshot-verified fix uncovered
something screenshot sampling had missed, and the underlying complexity
(raster split + merged IRQ schedule + double buffer, all to protect one
HUD row) was exactly the kind of entanglement with the raster/multiplexer
architecture that sank the previous branch.

**The fixed HUD requirement has been dropped for this diagnostic.** Per
explicit instruction: get one character screen scrolling vertically and
smoothly while the original sprite multiplexer and full enemy gameplay
remain completely stable - first. A fixed HUD is a real, legitimate raster
effect, but it is its own feature, to be added later, on top of scrolling
that is already proven stable - not something to solve at the same time as
first getting scrolling itself working.

All of that HUD-split machinery has been reverted:

- `armFirstBatch` and `multiplexIRQ` are restored **byte-for-byte
  identical** to the pre-background baseline (`2d13fa2`) - diffed
  mechanically to confirm, not just eyeballed.
- `HUD_SPLIT_PENDING`, `armNextEvent`, `hudSplitIRQ`, `resetHudScroll` are
  all gone.
- No raster IRQ of any kind is armed for the background. `$D011` bits 0-2
  (YSCROL) are written exactly once per frame, from the main loop
  (`applyFineScroll`), not from an interrupt.
- There is only one character screen (`$0400`). No second screen, no
  `$D018` writes, no flip, no shadow buffers.
- The whole 25-row screen scrolls, including where the HUD used to be.
  `FREE`/`LIVES`/`SCORE` are not kept fixed and are not specially
  protected - `initBackground` overwrites all 25 rows with the test
  pattern at game start, same as the previous background-1000 line
  ownership problem this avoids entirely by not existing.

## Design (current)

- **Single screen, single buffer.** `$0400`/`$D800` only. Nothing else
  touches VIC memory-setup (`$D018`) at all in this prototype.
- **One fixed terrain colour** (`TERRAIN_COLOUR`), all 1000 bytes of
  `$D800` filled once at game start and never touched again.
- **A trivial raw row source**: `rawRowGlyph(rowIndex)` returns a single
  digit-glyph screen code (`rowIndex mod 10`), repeated across all 40
  columns - no table, no metatiles. Chosen so a coarse advance (once
  added) is trivially verifiable by eye: rows read 0,1,2,...,9,0,1,...
  continuously, and any skip or repeat is immediately visible. A larger
  deterministic raw row *map* (milestone 3) can replace just this
  routine's body later.
- **`applyFineScroll`**: writes `SCROLL_FINE` into `$D011` bits 0-2 once
  per presented frame, preserving every other bit (including bit 7, which
  the sprite multiplexer manages itself for its own raster compares). No
  split, no second value, no IRQ.
- **`updateBackgroundScroll`** (milestone 1): advances `SCROLL_FINE`
  through 0-7 and wraps straight back to 0. There is deliberately no
  coarse-row transition yet, so the static test pattern will visibly snap
  back by 8 pixels on every wrap - that is the expected, correct look of
  pure YSCROL cycling on unchanging content, not a bug. Making the motion
  continuous is milestone 2's job, and it is not implemented until
  milestone 1 is confirmed clean by actually watching it run.
- `endGame` restores `$D011`'s YSCROL to 3 (the normal, non-scrolling
  25-row position) when PLAYING ends, since `applyFineScroll` may have
  left it anywhere in 0-7 - menus/GAME OVER are otherwise completely
  unaffected by any of this.
- **Resident code placement**: the new code didn't fit in the
  `$0801-$1fxx` segment's remaining headroom, so it's placed at `$2920` -
  an already-unused gap (confirmed free in the pre-background baseline's
  own memory map) between the `$2400` block and the health-sprite pool at
  `$3000`.

## Milestones (status)

1. Restore the exact known-good game/multiplexer baseline (commit
   `2d13fa2`). **Done**, and re-confirmed byte-for-byte after the HUD-split
   revert.
2. Confirm it still runs cleanly in VICE with enemies and full gameplay.
   **Done.**
3. Disable the starfield during PLAYING only (menus/game-over unchanged).
   **Done**, unaffected by the HUD-split revert.
4. Put a static repeating test pattern across the **whole** text screen
   (no fixed HUD - see above). **Done** (`initBackground`).
5. Change only `$D011` YSCROL once per frame; no double-buffering, no
   raster IRQ for it. **Done** (`applyFineScroll`).
6. Watch it continuously in VICE with full enemy gameplay: confirm the
   complete screen moves smoothly through all eight fine positions, no
   tearing, no sprite corruption, no change to sprite-multiplex timing.
   **Verified as far as `-exitscreenshot` sampling can show** (dense
   frame-by-frame sweeps, full enemy spawning/combat/multiplexer active
   throughout, sampled at several points across multiple 0-7 cycles): no
   corruption, no clipping, sprites render correctly, `armFirstBatch`/
   `multiplexIRQ` untouched. **This is not the acceptance test** - only
   continuous human observation can confirm there's no glitch between
   sampled frames. Not yet confirmed by a human.

Not started (deliberately, per the instruction to stop and report if
milestone 1 fails, or wait for confirmation it's clean before proceeding):

7. The simplest coarse character-row transition needed to make scrolling
   continuous (whole screen, HUD area included, may scroll).
8. Feed newly exposed rows from the deterministic raw row source (a real
   table, not just `rawRowGlyph`'s formula).
9. Stop.

A fixed HUD is not on this list. It comes later, as its own raster-effect
feature, once coarse+fine scrolling together are confirmed stable by a
human.

## If milestone 1 glitches

Per instruction: stop immediately, do not proceed to another
architecture, and report the exact `$D011` values being written each
frame. The entire write path is `applyFineScroll` (one routine, four
instructions of substance: `lda`/`and #%11111000`/`ora SCROLL_FINE`/
`sta`) called twice per frame from `gameLoop`, and `SCROLL_FINE` is
advanced only by `updateBackgroundScroll`, which is about ten instructions
total. If something glitches here, the investigation is confined to those
two routines and nothing else - no IRQ, no second screen, no split - so
the visible symptom and the $D011 value at that moment should be reportable
precisely.
