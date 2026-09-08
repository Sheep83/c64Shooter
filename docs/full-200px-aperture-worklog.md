# Full ~200px gameplay aperture — architectural rework worklog

Branch `experimental-border-hud`, HEAD `d547c80`. Uncommitted Phase-1.5 +
overflow-row + full-aperture work present. No commit, no push.

Goal: recover the maximum clean vertical gameplay aperture, target ~raster
51..250 (200 px). Previous checkpoint: RSEL=0 crop, 192 px clean terrain (r55..246),
player clipped ~4 px at the bottom.

## Part A — measured mechanism (RSEL=1 build, `/tmp/rsel1.prg`, all 8 fine phases)

- RSEL=1 gameplay displays terrain cleanly down to raster **247 + fine** (the
  last badline = matrix row 24 at `48+fine+8*24 = 240+fine`, displayed to
  `247+fine`). Below that = **VIC idle graphics** (black/$D021 4-px stripes,
  $3fff pattern). RSEL=1 aperture bottom compare @ 251; borderOpenHook dodges it.
- **Temporal oracle, RSEL=1, aperture 51..250** (`check_scroll_edges_rsel1`):
  - `body_temporal_diffs = 0` across rasters 56..244 — the terrain BODY is
    temporally FLAWLESS, every fine phase AND every coarse transition.
  - `lastrow_temporal_diffs` non-zero **ONLY at the 7->0 coarse step**, at
    rasters **248, 249, 250** (~3 px).
  - Symmetric top run (aperture 51..246): `body` diffs ONLY at 7->0, rasters
    **52, 53, 54, 55** (~4 px). `lastrow` (245-246) = 0.
  - Every non-coarse fine step (`0->1` .. `6->7`): **zero diffs everywhere.**
- => the earlier "diffs at raster 247 every fine step" reading was an artefact of
  the botched `GAMEPLAY_BOTTOM_EXTEND` borderOpenHook timing (RSEL 0->1@242 /
  1->0@252). The CLEAN RSEL=1 build pops only **~3-4 px at rasters 52-55 (top)
  and 248-250 (bottom), once per coarse 7->0 cycle** (~3x/s at divider 2).

## Part A — why the overflow rows' OUTER edges pop (root cause)

`W(r) = SCROLL_ROW + r - 1`. Matrix row 0 = world `S-1` (incoming overflow),
row 24 = world `S+23` (outgoing overflow).
- RSEL=1 shows row 0 from raster 51. Row 0 badline `48+fine`; only its glyph
  rows `3-7` (rasters 51-55) are ever visible at fine 0 — its top rows are above
  raster 51, in the border, never fetched-and-shown.
- So world `S-2` is only ever *partially* visible (bottom 5 px, in row 0) until
  it becomes row 1. At the 7->0 coarse step the new row 0 = world `S-2` appears
  with its bottom 5 px where world `S-1`'s were => a ~4 px jump. There is no
  matrix row -1 (rasters 43-50) to show world `S-2`'s top gradually.
- Mirror at the bottom: world `S+23` (row 24) only ever shows its top 0-7 px
  (rasters 247+); its bottom falls off with no matrix row 25 to receive it.
- **The last presented content row on EITHER edge always pops ~one glyph-row's
  worth at the coarse step. RSEL=0's crop at 55/246 hides both. RSEL=1 exposes
  ~4 px of each.** This is a property of a finite N-row character fetch, not of
  our specific implementation. No 26th badline is reachable (badlines stop at
  raster 247).

## Part A — ECM masking probe

Poking `$D011 |= $40` (ECM=1) at raster 246 did NOT convert the idle stripes to
a solid colour — idle graphics below the last badline still show the $3fff
stripe pattern. Slap Fight / Terra Cresta pair the RSEL flip with `$D018 = $e3`
(swap to a zeroed screen+charset) so the idle fetch byte is $00 -> solid
backdrop. ECM alone is insufficient for our config; a `$D018` swap is the
commercial mechanism. To be tested.

## Reframe of the user's actual problem

"Player body clipped ~4 px at the bottom" is a **SPRITE** problem, not a terrain
one. Sprites are not subject to the char-fetch limit. With the vertical border
open (RSEL 1->0 dodge, commercial style) a sprite renders through rasters
~247..258. => opening the borders fixes the player clip regardless of the
terrain edge question.

## Direction

Candidate: **RSEL=1 gameplay + open both borders (commercial dodge)** so:
1. sprites usable across the full 51..~258 range (player unclipped) -- fixes the bug;
2. terrain body rasters ~56..247 temporally flawless;
3. extreme edges (r51-55 / r248-250) = overflow-row terrain, ~3-4 px pop once per
   coarse cycle -- either documented as a "soft edge" (commercial precedent) or
   masked with a `$D018` swap to a zero region (test if worth it).

## Part C/D — chosen candidate: commercial open-both-borders + zeroed idle byte

Implemented (`src/main.asm`, `src/raster_scheduler.asm`):
- `borderOpenHook`: RSEL 0->1 @ raster 245, RSEL 1->0 @ raster 250 -> BOTH border
  close compares (RSEL=0 @247, RSEL=1 @251) missed -> vertical border FF never
  set -> top AND bottom border open into overscan every frame. rasterFrameReset
  re-installs RSEL=0|fine @ line 1. Removed the `GAMEPLAY_BOTTOM_EXTEND` toggle.
- `init`: `$3FFF = $00`, `$39FF = $00` (idle g-fetch bytes; char codes 224..255
  are outside the terrain/HUD/star allocation) -> the idle region below/above
  the terrain renders as **solid $D021 backdrop** instead of $3FFF stripes.
- `PLAYER_MAX_Y = 237` (was hard `#230`): the ship's 21-line body now reaches
  the open-border backdrop edge (~raster 258) fully visible -- **player clip
  FIXED**. Also fixed a latent bug (old `beq` let Y run past the clamp).

## Results (measured)

| aspect | result |
| --- | --- |
| clean gameplay TERRAIN body raster 55..246 | temporally **FLAWLESS** -- `check_scroll_edges_rsel1 --aperture 55 246`: `body 0 / lastrow 0` on ordinary / wave5 / contrast($D021=7) / div1 (24 coarse). No regression. |
| player at Y=237 | fully visible against $D021 backdrop, NOT clipped (`player_bottom_beforeafter.png`) |
| idle regions (r~16-51, r~252-260) | solid $D021 backdrop (zeroed idle byte), no stripes, no black border |
| soft edge r247-254 (bottom) / r52-55 (top) | overflow-row terrain; `7->0` coarse pop ~6 px once per coarse cycle (r248-253), BELOW the claimed clean body; every non-coarse fine step ~0 |
| cadence `[19656]` | exact -- ordinary / dense / wrap / seeded-wave (trusted `vice_scroll_test` + `check_raster_capture`) |
| scheduler | 0 service failures, 0 sprite-start misses everywhere; dense catchups/replays = pre-existing --dense synthetic stress (identical on baseline) |
| sprite Y-clusters | highy (15 @ Y56-84) / lowy (8 @ Y245) / dense (16) / wave6 (authored 6-enemy) / seeded real waves -> all `[19656]`, 0/0 |
| sprite-Y sweep 40..244 | every Y gets a slot; topmost sprites are always the initial-8 (unscheduled) -> MIN_Y is display-bound, not mux-bound |

## Part E (mux) -- measured, NOT rewritten

- BUILD render plan built + published by raster ~15-20 every normal frame
  (`gameplayPresented` r15-20, `armFirstBatch` r12-17). Big idle tail.
- Failure onset: none in the supported envelope; `--dense` (16 obj / 8 batches)
  triggers the replay path (main didn't finish BUILD) ~99/200 frames but
  cadence stays exact and 0 misses.
- JIT (Slap Fight $1936 / Terra Cresta $4a57): no BUILD phase, no publication
  deadline, no replay/catchup; short IRQ per 1-2 sprites scheduled `Y-14` ahead.
  Would remove our replay/catchup machinery. **Recommended as the next
  architectural task** -- not required for and not done in this aperture work.

## Verdict: AMBER

Clean scrolling TERRAIN stays 192 px (r55..246) -- architectural limit of a
finite 25-row char fetch, matches Slap Fight / Terra Cresta (their tallness is
sprites + border HUD, not terrain past their crop). RECOVERED: player unclipped,
no black border (backdrop soft edge), sprite/player usable r~16..258, top border
open & ready for the HUD, body flawless, `[19656]`.
Path to full GREEN (zero visible edge pop): a `$D018` mid-frame swap to a
reserved 2 KB zeroed charset region masks r247-254 & r52-55 to solid backdrop --
bounded memory-map work, fold into the top-HUD task.

Final build sha256(prg) c59f975a7a08cdf6. HEAD 44e735c (user committed prior
tasks). No commit this task.
