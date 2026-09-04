# Background / stage engine — design notes

Status: scrolling is logically correct (confirmed both by memory-level
diagnostic and by human playtesting - it genuinely scrolls now, no more
snap-back). **Confirmed by human playtesting: heavy glitching every few
frames.** This is "problem B" below - the unoptimised brute-force
coarse-step cost - manifesting exactly as predicted once played for real
rather than sampled via cycle-limited screenshots. This is the open
problem on this branch: making the coarse transition raster-safe/cheap
enough not to glitch, without redesigning the HUD split, sprite
multiplexer, or LIVE/BUILD render-plan architecture. Placeholder art and
a placeholder test map throughout; the *mechanism* is intended to be
final once this is resolved.

## RESOLVED — the "snap back" scrolling bug was a live/shadow sync bug, not a raster-timing bug

The original hypothesis in this section (raster-timing/scheduling) was
**wrong** and was superseded before any raster work was attempted, per an
independent review that correctly diagnosed the actual defect from the
code alone: `advanceCoarseRow` called `shiftShadowRowsDown` (which only
ever touches the two shadow buffers) and then `blitShadowRowToLive` for
**row 1 only**. Live screen RAM (`$0400`) and colour RAM (`$D800`) rows
2-24 were therefore never updated after the initial static build - a
plain logical-ownership bug with nothing to do with raster timing.

Confirmed empirically before changing anything (as instructed - see
`git log` for the exact protocol): a disposable diagnostic build dumped
shadow vs. live screen-RAM bytes at several rows immediately after the
first coarse transition. Row 1 matched (it *was* blitted); row 10 showed
shadow=`$20` (sky) vs. live=`$e9` (233, a stale pre-shift turret-head
glyph left over from the initial build); row 20 showed shadow=`$e0` vs.
live=`$e1` (a different rock-tile byte). That divergence is exactly what
produces "advances one row then snaps back, only some cells move": row 1
alone changing, the rest reverting to old content, on every coarse step.
It also explains the reported "random" corruption - once shadow and live
diverge, `eraseOneStar` (which is intentionally shadow-authoritative)
copies now-mismatched shadow content into individual live cells wherever
a star happens to move, scattering fragments of the "true" (shadow)
background across the still-stale live screen.

**Fix applied** (`advanceCoarseRow`): blit *every* row (1-24) from shadow
to live on every coarse step, not just row 1 - reusing the existing,
already-correct `blitShadowRowToLive` in a loop. Deliberately the
simplest possible correct fix, chosen over any raster-safety work per the
instruction to prove logical correctness first. Re-verified via the same
shadow-vs-live byte comparison after six repeated coarse transitions
(all rows checked matched); watched a close-spaced sequence of screenshots
(~1-2M cycles apart) show continuous, correct terrain progression with no
snap-back, including the background-attached turret scrolling correctly
with it.

**Known follow-up (not yet addressed - this is "problem B", deliberately
separated from the correctness fix above):** blitting all 24 rows costs
roughly 23,000 extra cycles on top of the existing ~24,000-cycle shadow
shift, i.e. a coarse-step frame now costs on the order of 50-55k cycles -
about 2.5-3x a normal 19,656-cycle PAL frame. No visual tearing was
observed in cycle-limited screenshot testing (the existing LIVE/BUILD
double-buffered render-plan swap means this heavy work happens during
background-plan construction, before the next presented frame, so the
effect was expected to be a pacing stutter rather than a mid-scan
corruption), and the FREE-cycle debug HUD stayed positive throughout -
but that testing never watched sustained real-time play, only sampled
single frames far apart. Human playtesting has since confirmed **heavy
glitching every few frames**, i.e. this cost is real and visible in
practice, not just a theoretical rolling-minimum concern.

## OPEN — coarse-step cost needs to come down (or be scheduled safely)

Next steps for whoever picks this up, roughly in order of how cheap they
are to try:

- Profile properly first: use the existing FREE-cycle HUD specifically on
  coarse-step frames (it currently reports a 50-frame rolling minimum,
  which blends heavy and light frames together - instrument it, or add a
  one-off counter, to isolate the coarse-step frame's own cost rather than
  inferring it from the blended minimum).
- The 23k-cycle live-sync blit (`blitShadowRowToLive` x24 in
  `advanceCoarseRow`) is the part added by the brute-force fix and the
  most obviously wasteful: every coarse step re-copies 23 rows whose
  content didn't actually change relative to the *previous* frame's live
  screen, just moved down one row. A shift-in-place of the 23 unchanged
  live rows (mirroring what `shiftShadowRowsDown` already does for the
  shadow buffers, applied to `$0400`/`$D800` too) only needs a single
  extra full-row blit (the new row 1) rather than 24 - roughly the same
  saving `shiftShadowRowsDown` already gets over a naive full re-render.
- Only after that: consider whether the remaining cost needs to be spread
  across several frames (double-buffering the live screen via a second
  `$D018`-selected screen, as discussed and deliberately deferred earlier
  in this document) or scheduled around a raster-safe window. Do not reach
  for either without first re-measuring the cost of the simpler shift-in-
  place version above - it may already be enough on its own.

## Why fine-Y hardware scroll + a live coarse row-shift

The VIC-II has no per-row screen-memory remap: screen RAM is one fixed
1000-byte block, row *R* is always displayed at character-row *R*. Fine
vertical scroll (`$D011` bits 0-2, `YSCROL`) shifts the *whole* 25-row grid
uniformly by 0-7 pixels; it cannot exempt one row. So two problems had to be
solved beyond "just scroll":

1. **Row 0 (the HUD) must never move**, but YSCROL is global. Solved with a
   one-line raster split (see below) that forces `YSCROL=0` for row 0's 8
   scanlines and only reveals the real scroll value from row 1 down.
2. **Coarse row advance.** Every 8th fine-scroll step, the picture has to
   snap by exactly one character row to stay continuous. Shifting all 24
   playfield rows (960 bytes × screen + colour) costs roughly 20-25k cycles
   with a straightforward 6502 loop — more than a whole PAL frame's 19656-
   cycle budget on its own. True double-buffering (prepare a second screen
   off-screen, flip `$D018`) was evaluated and rejected for v1: colour RAM
   has no second bank to flip (`$D800` is the only physical colour matrix,
   whichever screen is "live"), so a swap still needs a live colour-RAM
   rewrite at the flip instant anyway, and the screen-buffer bookkeeping
   (two 1K-aligned blocks, a wasted row-0 slot in each, HUD duplication)
   adds real complexity for a placeholder milestone. Chosen instead: do the
   full 24-row shift **in place, live, once per coarse step**, timed to
   finish inside the dead window between the last visible raster line of one
   frame and row 1 being re-scanned next frame (so it is not a raster tear,
   just an occasionally-longer frame). This is deliberately the simpler of
   the two standard techniques the brief invited me to weigh, chosen for
   predictability over squeezing out the last few thousand cycles. It is
   profiled with the existing FREE-cycle HUD; see the performance section of
   the final report for measured numbers. If the occasional heavier frame
   ever proves visible in practice, the natural upgrade is exactly the
   double-buffered version sketched above — nothing here forecloses it.

Scroll speed is deliberately conservative (`SCROLL_FRAME_DIVIDER`) so a
coarse step, and its one heavier frame, is infrequent.

## Raster split (HUD exemption)

One additional, fixed-line raster IRQ (`scrollSplitIRQ`, armed by
`armScrollSplit`) fires once per frame at `HUD_SPLIT_RASTER` (the first
scanline of character row 1). It does exactly one thing: writes the current
`SCROLL_FINE` value into `$D011` bits 0-2, leaving every other bit (RSEL,
DEN, BMM, ECM, and the raster-compare high bit already in use by the sprite
multiplexer) untouched. The main thread forces `YSCROL=0` immediately after
`waitForFrameStart` each frame (`resetHudScroll`), before row 0 is scanned.

This IRQ then falls through into the *unmodified* `armFirstBatch` arming
sequence for the sprite multiplexer's first recycling batch (duplicated
inline rather than `jsr`'d, since calling a routine that ends in `cli` from
inside an IRQ would re-enable interrupts mid-handler). `armFirstBatch`,
`multiplexIRQ` and all batch data are untouched; `gameLoop`'s two former
`jsr armFirstBatch` call sites now call `jsr armScrollSplit` instead, which
arms the split line first. The sprite multiplexer's own raster IRQs, which
only ever target rows well below the split (object Y ≥ 12), are unaffected.

Background scrolling — and therefore the split — is armed only while
`GAME_STATE_PLAYING`; menu/game-over/high-score screens use the plain
`armFirstBatch` path exactly as before.

## Metatile / stage format

```
metatile        16 bytes: 4x4 screen codes, row-major (top-left first)
metatile colour 16 bytes: 4x4 colour-RAM values, same order
stage map       1 byte per metatile, row-major, BG_MAP_COLS (10) per map row
stage entities  one record per turret placement (world row, column, type)
```

* Metatile = 4×4 characters = 32×32 px. The 40-column playfield is exactly
  10 metatiles wide (`BG_MAP_COLS = 10`), so a map row is 10 bytes.
* `BG_CHAR_SKY = 32` (space) is the sky/empty convention. `bgMetaSky` is an
  all-32 metatile.
* Colour is stored **per character cell**, not per metatile, so future
  CharPad exports (which usually carry per-cell colour) drop in directly and
  individual glyphs (e.g. a turret's head vs. base) can carry different
  colours within one metatile.
* The stage map (`stageMap`) is `BG_MAP_ROWS` (80) metatile-rows tall — 320
  character rows, about 13 screens of unique content — long enough that
  wrap/repeat bugs cannot hide in one 25-row demo, and short enough to stay
  fully deterministic hand-authored data.
* World position is tracked in **character rows** (`SCROLL_MAP_ROW`, 16-bit),
  not metatile rows, since fine/coarse scroll operates a row at a time; a
  metatile row is simply 4 consecutive character rows sharing one map byte.
* Reaching the last map row sets `STAGE_STATE = STAGE_STATE_COMPLETE` and
  freezes further scrolling (`updateBackgroundScroll` becomes a no-op). No
  stage-transition UI yet, per scope.

## Starfield / background compositing

A 1000-byte shadow copy of the *true* background exists for both screen
codes (`BG_CHAR`, `$4400`) and colour (`BG_COLOUR`, `$4800`) — this is the
"backing screen" the brief suggested. Row 0 of each is unused filler (the
HUD owns real row 0 and is never touched by the background system). Because
both shadow buffers are 256-byte-aligned at the same low-byte offset as
`$0400`/`$D800`, any screen address's shadow address is just "add a constant
to the high byte" — reusing the exact address-computation idiom the star
routines already use for colour RAM (`adc #$d4`).

The four star routines (`drawOneStar`, `eraseOneStar`,
`setOneStarTwinkleColour`, `setOneStarNormalColour`) gained one shadow-aware
change each:

* **`eraseOneStar`** no longer writes a blind space. It restores whatever
  `BG_CHAR`/`BG_COLOUR` says truly belongs in that cell (terrain or sky).
* **`drawOneStar`** first checks `BG_CHAR` at the target cell; if it is not
  `BG_CHAR_SKY`, the glyph/colour writes are skipped (the star's own
  position/phase state still advances normally — it simply isn't drawn
  while parked over solid ground, and will draw again the moment it moves
  back over sky).
* The twinkle-colour routines only ever touch a cell that a star is already
  legitimately occupying (i.e. one where `drawOneStar` most recently
  succeeded), so they need no additional check.

Star motion is completely unchanged (still screen-space, independent of
scroll rate) — this preserves "the cheap 16-star implementation" exactly as
asked, rather than turning it into a general compositor.

When the coarse row-shift runs, the *shadow* buffer is shifted and the new
row is rendered from the map into it; the live screen/colour rows are then
written straight from the freshly-shifted shadow (not copied from whatever
was previously on screen, since that could contain star glyphs). This is
what makes "terrain wins immediately" trivially true — a coarse step always
repaints the real background, and any star glyph is naturally re-established
by its own next move cycle (at most 4 frames later for the slowest star
layer) if the cell is still sky.

## Turret entity

Turrets are **not** logical objects (`OBJECT_*` arrays) — they never
consume one of the 16 sprite-object slots, per the hard constraint. Instead:

* `stageTurrets` (stage data) lists every turret's placement in world
  coordinates: character row, fixed screen column (0-39 — there is no
  horizontal scroll, so a turret's column never changes) and type.
* A small fixed pool, `ACTIVE_TURRET_*` (4 slots), holds the state of
  whichever turrets are currently near/on the viewport: health, state
  (alive/damaged/destroyed), fire timer, aim sector. `activateTurrets`
  scans the (short) stage turret list once per coarse step and
  activates/deactivates pool slots as their world row enters/leaves the
  visible window — "only entities reasonably near/on the visible screen
  need active updates".
* **Rendering** happens once, when a turret's row is first written into the
  shadow buffer as part of building a new map row (`renderTurretIntoRow`),
  stamping base/head characters (230-233) over the plain terrain. After
  that the turret scrolls for free — it is now just shadow-buffer content,
  carried along by the same coarse shift as everything else, exactly like
  the brief's "wreck remains attached to the scrolling landscape".
* **Aiming** re-stamps only the head character (231/232/233) directly into
  both the shadow and live buffers at the turret's *current* screen row
  (recomputed from `worldRow - SCROLL_MAP_ROW`), every 6 frames, comparing
  the player's X against the turret's fixed column in three coarse sectors.
* **Firing** reuses the existing enemy-bullet mechanism exactly:
  `spawnTurretBullet` duplicates only the small amount of
  `spawnEnemyBullet` that reads a *logical object's* X/Y (turrets have none)
  and otherwise calls the same `findFreeObject`, the same
  `chooseEnemyBulletSlope` aim quantiser, and honours the same
  `MAX_ENEMY_BULLETS` / `ENEMY_BULLET_COUNT` global cap. A turret whose fire
  request finds the bullet budget exhausted simply defers (retries next
  cadence) — no new budget, no new projectile type.
* **Damage** is a cheap character-cell rectangle test
  (`traceTurretHit`), called from `updatePlayerFire` alongside the existing
  `tracePlayerCannon` enemy trace (only when the enemy trace misses), using
  the same hitscan X/Y the player's twin cannon already computed. On hit:
  brief colour flash, HP-1, swap to the damaged base glyph (235) at low HP,
  and at 0 HP stop tracking/firing and permanently stamp the wreck glyph
  (236) into the shadow buffer (i.e. it becomes ordinary scrolling terrain
  from then on — ordinary hitscan against a shadow-only wreck is a no-op
  since it is no longer in the active pool).

This keeps turret-specific code in its own section, deliberately structured
so a future entity type (radar dish, generator, silo) can reuse
`ACTIVE_TURRET_*`-style pooling, activation-by-viewport, and the shared
fire/damage helpers without touching the scroll/compositor machinery.

## Memory map additions

See the final session report for the as-built address list; in summary:
resident background/turret code, state and the two shadow buffers live at
`$4000-$5FFF` (physically in upper free RAM because the original
`$0801-$1F00` code segment had only ~275 bytes of headroom left after the
movement-fragment work — this is *placement*, not a redesign of anything
existing). Stage-package data (placeholder charset additions, metatile
definitions, metatile colours, the test map, turret placements, stage
config) lives separately at `$6000-$9FFF`, guarded to stay clear of the
BASIC ROM shadow at `$A000`. This split is deliberate: a future multiload
would replace only the `$6000+` block and re-run the (unchanged) resident
install/activation routines — nothing resident depends on stage-package
addresses being fixed at compile time beyond simple labels a loader could
equally well re-point.

## CharPad / future asset pipeline

To replace the placeholder art with a CharPad export, the expected shape is:

* **Charset**: 128 bytes per 16 characters (8 bytes/char), same layout as
  `testStageGlyphData` — install with the same byte-copy loop already used
  for `starGlyphData`/`testStageGlyphData`, targeting `$3800 + code*8`.
* **Metatiles**: 16 bytes (char) + 16 bytes (colour) per metatile, 4×4
  row-major — same shape as `bgMetaRock` etc.
* **Map**: 1 byte per metatile, row-major, `BG_MAP_COLS` (10) bytes per row,
  any number of rows.
* **Entities**: fixed-size records (today: world row, column, type — see
  `stageTurrets`), one per placement.
* **Colours**: raw VIC colour-RAM nibbles (0-15), never PETSCII/ANSI codes.

All of the above are plain `.byte` tables today; swapping them for
`.import binary "stageN.bin"` blocks (KickAssembler) at the same labels,
built at each of the section boundaries above, is the entire migration —
no runtime code changes anticipated.
