# Physical top/bottom scroll edges: investigation and handoff

## Decision

**Keep the engine unchanged.** The observed edge pop is real in captured
pixels, but is the expected consequence of scrolling a 200-pixel character
image behind the fixed standard 25-row border. It is not a late incoming-row
write, faulty metatile expansion, broken crossing row, or coarse-copy tear.
Earlier preparation of `BG_INCOMING_ROW` cannot make the VIC display terrain
while its character sequencer is idle.

There is a simple geometry alternative: standard **24-row border cropping**
hides the affected strips. This was measured in a disposable emulator only.
It sacrifices four visible scanlines at each edge, also cropping sprites there.
It is not implemented or silently selected as a fix. Retain the current minor
edge artefact unless that visible-area tradeoff is explicitly wanted.

## Starting authority and reproducibility

- HEAD: `8a2c841`, `proved fixed character HUD over scrolling playfield`.
- Branch: `background-scroll-first-working-prototype`.
- Working tree verified clean before investigation and after rebuilding.
- Fresh KickAssembler 5.25 build using the repository's configured assembler.
- Fresh PRG SHA-256:
  `8a5873dfb8faa7564c4eff62b01d7cdac47abc613aaa0ed80eddacdaf6873a9d`.
- All captures in this investigation used this fresh PRG and matching symbols.
- PAL `x64sc`, 312 lines × 63 cycles = 19,656 cycles per physical frame.

No engine source, sprite plan, HUD routine, metatile data, matrix address,
coarse-copy body, colour RAM policy, or raster scheduling was changed.
Only two investigation/test tools and this report are new, left uncommitted.
The probe explicitly changes **disposable emulator RAM**, not the repository
or the shipping PRG.

## What the VIC displays, measured for every fine phase

All raster ranges below are inclusive. They are VIC raster numbers, not image
rows. VICE's default 384×272 screenshot starts at raster 16; the character
area starts at image X=32. Standard RSEL=1 exposes rasters **51..250**.

With fine phase `f`, ordinary first and last matrix fetches occur at `48+f`
and `240+f`. Matrix row `r` supplies pixels at `48+f+8*r .. 55+f+8*r`.
Thus the complete fetched 25-row image occupies `48+f .. 247+f`.
The visible border aperture does not move with it.

| Fine | First / last matrix fetch | Visible matrix row 0: raster, glyph scanlines | Visible matrix row 24: raster, glyph scanlines | Top idle strip | Bottom idle strip |
| ---: | --- | --- | --- | --- | --- |
| 0 | 48 / 240 | 51..55, 3..7 (5 pixels high) | 240..247, 0..7 (8) | none | 248..250 (3) |
| 1 | 49 / 241 | 51..56, 2..7 (6) | 241..248, 0..7 (8) | none | 249..250 (2) |
| 2 | 50 / 242 | 51..57, 1..7 (7) | 242..249, 0..7 (8) | none | 250 (1) |
| 3 | 51 / 243 | 51..58, 0..7 (8) | 243..250, 0..7 (8) | none | none |
| 4 | 52 / 244 | 52..59, 0..7 (8) | 244..250, 0..6 (7) | 51 (1) | none |
| 5 | 53 / 245 | 53..60, 0..7 (8) | 245..250, 0..5 (6) | 51..52 (2) | none |
| 6 | 54 / 246 | 54..61, 0..7 (8) | 246..250, 0..4 (5) | 51..53 (3) | none |
| 7 | 55 / 247 | 55..62, 0..7 (8) | 247..250, 0..3 (4) | 51..54 (4) | none |

“Idle” is distinct from the border: these lines are **inside** the open border
aperture but have no fetched terrain data. They are black in this engine.
Changing the border colour to blue in the isolated probe made that distinction
directly visible. The probe filled all 1,000 screen cells with a solid vertical
rail glyph, disabled sprites, and ran only `SEI; JMP *` in CPU RAM. All 40 rails
showed the boundaries in the table with no scrolling code executing.

This independently matches the hardware description: badline conditions are
limited to rasters 48..247; RSEL chooses border comparisons independently of
YSCROLL; the graphics sequencer uses idle data outside its fetched rows.
Reference: [Christian Bauer's VIC-II article, sections 3.5, 3.7.1, 3.7.2 and
3.9](https://www.cebix.net/VIC-Article.txt). The tables, screenshots, and temporal
pixel counts here are local measurements/derivations, not copied conclusions
from the earlier HUD or scrolling studies.

## Why both edges pop at 7→0

### Top: four lines of missed progressive reveal, then a five-line arrival

During fine 4, 5, 6, 7, an ideal infinite scrolling image would show the next
incoming row's last 1, 2, 3, 4 pixel rows at the top. The current VIC display
instead shows idle output there. Its first fetched row is still the existing
matrix row 0, beginning at raster 52, 53, 54, 55 respectively.

At the coarse transition, old row 0 correctly becomes row 1. The newly
installed row 0 is fetched at raster 48. Its first three scanlines are behind
the border, and its last **five** appear together at rasters **51..55**.
One is a legitimately new entering scanline; four should already have been
progressively visible under an ideal infinite-image model. Therefore a direct
one-pixel translation comparison fails at **52..55**, not just 51..54.

After arrival, fine 0→1→2→3 reveals that row at heights 5→6→7→8, one pixel
at a time. Fine 4→7 then moves it down intact while another idle gap grows
above it. The cycle repeats at each coarse transition.

### Bottom: four lines visible, then zero instead of three

At fine 7 the outgoing matrix row 24 still contributes four scanlines at
247..250. After one more pixel of downward movement it should retain three
at 248..250. However, the coarse copy correctly discards old row 24; old row
23 becomes new row 24. The VIC finishes that new last row at 247 and enters
idle output at 248..250. There is no ordinary 26th row fetch to continue the
old outgoing row.

Thus the old outgoing row disappears from height **4 to 0**, rather than
4 to 3. Fine 0→1→2→3 then shrinks the bottom idle gap from 3→2→1→0 as the
last fetched row advances normally. Later phases clip the outgoing row from
height 8→7→6→5→4, one scanline per step, before the next coarse drop.

The two effects are related but not numerically symmetric: canonical fine 3
aligns the fetched image exactly with the aperture. Fine 0 is three pixels
above it; fine 7 is four below it. Maximum missing bands span 1,280 possible
pixel positions at the top and 960 at the bottom across the 320-pixel width.
Only actual foreground terrain bits produce a visible contrast, so sparse
scenery can make the artefact appear intermittent or more prominent at one end.

## Data ownership and timing audit

| Component | Current behaviour | Relevance to the edge observation |
| --- | --- | --- |
| `SCROLL_FINE` | Main-thread pending phase, not necessarily the currently displayed phase. | Captures use actual `$D011 & 7` at raster 311. Reading only this RAM variable can mislabel a frame. |
| `updateBackgroundScroll` | Advances after the three-update divider; at 7 requests coarse work without immediately publishing 0. | Correctly protects the 7→0 transition. Under overload, game updates and thus scrolling may hold for physical frames. |
| `applyFineScroll` | Publishes fine bits near frame start, keeping the existing display mode and compare convention. | No mid-frame YSCROLL split or hidden second display geometry. RSEL remains 1. |
| `prepareBackgroundCoarse` | On a safe pending wrap, waits until ≥152; restores HUD terrain; saves crossing row; shifts upper rows; decodes and installs new row 0; then marks phase 0 and lower work pending. Defers starts at ≥200 or with raster high set. | New row is installed in the **preceding** physical frame. The old upper rows were already fetched. |
| `BG_INCOMING_ROW` | A 40-byte decoded staging buffer used by initialization and each newly introduced stage row. | CPU workspace, not VIC-visible screen storage. Pre-decoding it sooner cannot supply an idle VIC scanline. |
| `finishBackgroundCoarse` | After presentation/HUD, shifts lower rows and restores the physical crossing row before row 13's fine-0 fetch at 152. | Bottom matrix row 24 is ready long before its fetch at 240. |
| `BG_CROSSING_ROW` | Saves actual old row 12 bytes, restoring them to new row 13. | Preserves the interior seam. It is not an incoming/outgoing edge buffer and is not implicated in either pop. |
| Badlines / cached characters | Fetch rows on their phase-dependent lines; screen writes behind those fetches do not alter the cached old display. | Explains why upper RAM can already contain next-frame data while current-frame pixels remain correct. |
| Fixed 25-row border | Aperture is 51..250 at every phase. | Exposes the idle gaps listed above. This alone reproduces the symptom. |

Measured latest routine trace positions:

| Capture | New top row ready | Lower work ready | HUD ready |
| --- | --- | --- | --- |
| 600 normal frames | 270:23 | 83:38 | 27:29 |
| 2,400 long frames | 271:23 | 92:36 | 29:18 |
| 1,200 stress frames | 295:21 | 118:48 | 30:13 |

`line:cycle` uses VICE's register/trace convention. The latest observed new
top row was still ready about **4,089 PAL cycles before** the following
frame's first fine-0 matrix fetch at 48:15. The stress lower completion was
**2,109 cycles before** the crossing-row fetch deadline at 152:15, and much
earlier than row 24's fetch. These are observed margins, not an expansion of
the engine's existing safety guarantees.

Copy source bodies and all IRQ/HUD code are unchanged. No cycles were added
to engine execution. Existing early compare-24 and late compare-243 legality
and their baseline limitations are preserved by identical engine source and
PRG hash; the synthetic HUD boundary tests were not repeated in this task.

## What the old tests did and did not establish

Both existing pixel checkers iterate image Y=39..230, i.e. raster **55..246**.
They omit top rasters 51..54 and bottom 247..250. Even at raster 55, checking
the correct character for each isolated phase does not prove continuity with
the previous frame's raster 54. A correct spatial matrix oracle can therefore
pass while the observed edge still pops.

The current HUD checker also verifies the complete screen matrix, saved HUD
terrain bytes, phase-compensated marker pixels and physical frame intervals.
The older terrain-only checker intentionally does not model HUD patches and
skips its matrix comparison for physical captures. It was inspected, not used
as the acceptance oracle for this HUD-bearing checkpoint.

New `tools/check_scroll_edges.py` adds three complementary checks:

1. **Temporal:** compare actual image pixels to the same X, previous Y−1 on
   one-pixel steps, or previous Y on held phases. It does not read charset
   bytes or decode terrain for this comparison. It examines top 51..70 and
   bottom 231..250, excluding actual planned sprite rectangles in both frames
   and the single newly entering scanline at 51. Measured differences are
   retained by phase and physical raster number. Expected 25-row geometry
   losses are reported, not falsely called continuity passes.
2. **Spatial:** check border, idle output, and decoded terrain pixels over
   top 44..70 and bottom 231..259. This tests the newly arriving/clipped rows
   and the gaps themselves against the independently established geometry.
3. **Isolated geometry:** verify all 40 diagnostic rails over rasters 44..259
   in 16 screenshots: all phases in standard 25- and 24-row modes.

It emits `edge-verification.json` and an enlarged `edge-phases.png` from real
VICE output, ordered 4,5,6,7,0,1,2,3. Images were visually inspected in addition
to numerical checks. These static captures are supplied for human review;
this is not a claim of a new human acceptance of changed gameplay.

## Results

| Run | Physical frames | Displayed coarse transitions | Max objects / LIVE batches | Deferred counter | Existing matrix/HUD/interior oracle |
| --- | ---: | ---: | --- | ---: | --- |
| Normal | 600 | 24 | 9 / 1 | 0 | 35,124,204 pixel checks, no failures |
| Long | 2,400 | 99 | 9 / 1 | 0 | 140,371,306 pixel checks, no failures |
| Stress | 1,200 | 28 | 16 / 7 | 1 | 69,076,754 pixel checks, no failures |

All eight fine phases occurred in every run. All captured physical intervals
were exactly **19,656 cycles**. The long test made 100 RAM coarse steps and
crossed the stage table's 0→79 boundary twice; the last prepared RAM step
need not yet have been displayed at the final raster-311 capture. This accounts
for its 99 displayed 7→0 transitions. Stress includes six-batch frames as well
as a seven-batch maximum; the one deferred attempt held the old display safely.

The direct temporal comparison found differences **only at 7→0**, restricted
to top rasters 52..55 and bottom 248..250. Every other measured shift/hold
matched at the uncovered edge pixels. No unexpected temporal differences were
found in any run. Exact per-raster changed-pixel counts are in each report.
The solid-rail geometry test passed all 16 cases without discrepancies.

Extended spatial edge checks covered **10,486,720 / 41,948,014 / 20,858,691**
pixels in normal / long / stress respectively, **73,293,425 total**, with no
failures. These include the bands the original checker omitted. Stress
included three captured six-batch plans and two seven-batch plans, with
actual batch compares spanning 61..243. Exact results are retained in each
run's `edge-verification.json`.
An exit status of zero means “no deviation from the measured standard geometry,”
**not** “the full 25-row aperture is temporally continuous.”

## Candidate changes and cycle implications

| Candidate | Result / blocker | Timing consequence | Recommendation |
| --- | --- | --- | --- |
| Retain current 25-row geometry | Keeps the quantified 4-line top / 3-line bottom missing reveal. | Zero new work; all proven scheduling remains intact. | **Default: retain.** |
| Predecode incoming row sooner | Does not create a first fetch for the preceding row above `48+fine`. Installing into row 0 too early instead replaces still-needed terrain. | Adds/moves decoder work without addressing idle output. | Reject as a fix for this cause. |
| Preserve old row 24 in another 40-byte CPU buffer | Still no ordinary 26th character fetch after 247. | Additional copy/storage, no visible benefit by itself. | Reject. |
| Start at fine 3 or alter the divider | Merely changes when/how often the same eight geometries occur. | Small bookkeeping change, no continuity correction. | Reject as a fix. |
| Standard fixed 24-row border (RSEL=0) | Aperture 55..246 lies wholly inside fetched data for **all** phases; the probe confirms no exposed idle strips. A new row would grow from one visible scanline; outgoing data would reach zero progressively. Crops four scanlines at each edge, including sprite pixels. | RSEL does not change ordinary badline positions. Could reuse existing D011 writes with different masks/immediates and restore 25-row mode for menus, without extra IRQs or changing copies. Runtime scroller remains 25 matrix rows. | Best optional cosmetic change **if the 192-pixel aperture is acceptable**. Not implemented; dynamic/HUD/stress acceptance would still be required. |
| Fill the entire 25-row aperture through raster tricks / alternate fetching | Needs data outside the ordinary 25-row fetched image. Extra row-counter/graphics manipulation, screen switching or a new compositing model would be required. | New timing/ownership proof, potential DMA/IRQ conflicts; violates this task's preferred scope. | Stop rather than redesign for a cosmetic edge. |
| Border opening or sprite masks | Opening reveals more rather than supplying missing character data; sprite masks consume ownership or demand reuse scheduling. | Adds complexity and possible capacity/timing conflicts. | Reject as first-choice workarounds. |

## Files, commands and continuation

New uncommitted files:

- `tools/vice_edge_probe.py`: destructive **only to a disposable emulator's**
  live state; isolates VIC geometry after a fresh game initialization.
- `tools/check_scroll_edges.py`: independent temporal edge comparison,
  extended spatial checks, geometry verifier and contact sheets.
- `docs/scroll-edge-investigation.md`: this handoff.

Ignored capture artifacts live under `build/edge-study/`:

- `baseline-normal/`, `baseline-long/`, `baseline-stress/`: source-state dumps,
  screenshots, physical registers, matrix/HUD reports, edge reports and traces.
- `geometry/`: raw 25-/24-row probe images, register samples, full monitor
  commands and `geometry-verification.json`.

Build fresh with the VS Code task, then for each normal/stress run launch a
fresh emulator (choose an unused port):

```sh
x64sc -default -pal -warp +sound -remotemonitor \
  -remotemonitoraddress ip4://127.0.0.1:6520 \
  -autostartprgmode 1 -autostart build/shooter.prg
python3 tools/vice_scroll_test.py --port 6520 --physical --trace \
  --frames 600 --out build/edge-study/repeat
python3 tools/check_hud_capture.py build/edge-study/repeat
python3 tools/check_scroll_edges.py build/edge-study/repeat
```

Use 2,400 frames for the long run; add `--stress` and use 1,200 frames for
stress. The Python checkers require Pillow. This session reused the temporary
Pillow installation at `/private/tmp/hud-study/python-deps` through PYTHONPATH;
that temporary path is not a repository dependency or guaranteed to persist.

After capturing normal gameplay, its **disposable** emulator can be reused
for the isolated test:

```sh
python3 tools/vice_edge_probe.py --port 6520 --out build/edge-study/geometry-repeat
python3 tools/check_scroll_edges.py --geometry build/edge-study/geometry-repeat
```

The probe deliberately stops gameplay, replaces matrix/colour data with
diagnostics, and tests RSEL=1 then 0; close/restart that emulator afterwards.
It never patches the PRG. VICE may need a fresh instance if its remote monitor
stops accepting reconnections following a disconnected breakpoint session.

No unresolved implementation defect was found and no engine fix is pending.
The remaining product choice is whether to keep the full 200-pixel aperture
or explicitly accept the standard 192-pixel crop. If retaining 25-row geometry,
this investigation is complete. If selecting 24-row geometry later, implement
only that display-policy change and rerun dynamic edge, matrix, HUD, cadence,
boundary-schedule and stress checks; do not treat the static probe as those
tests. Physical-hardware testing was not performed here.
