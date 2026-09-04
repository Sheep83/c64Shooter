# Background / stage engine — design notes

Status: first working prototype ("v1"). Placeholder art and a placeholder
test map throughout; the *mechanism* is intended to be final.

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
