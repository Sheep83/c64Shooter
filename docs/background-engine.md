# Single-screen downward scrolling diagnostic

The implementation uses one matrix at `$0400`, the existing charset at `$3800`,
fixed colour RAM and the original sprite IRQ scheduler. There is no second
screen, screen shadow, temporary row buffer, `$D018` switching or background IRQ.

## Hardware reasoning

With a fixed YSCROL value, matrix row `r` begins at raster `48 + 8*r + YSCROL`.
Thus increasing YSCROL moves scenery down. On `7 -> 0`, old row `r` must become
row `r+1`: its new position is exactly one pixel below its previous position.
Copy rows downward, processing the highest destination row first. Discard old
row 24 and introduce one new row at row 0.

Character codes are fetched on badlines, then cached inside the VIC for that
character row. At fine 7, the last fetch is raster 247; at fine 0, the next
first fetch is raster 48. From completion of the old fetch to the beginning
of the new fetch there are about 7,100 PAL cycles. A fully unrolled 960-byte
`LDA abs / STA abs` copy alone takes 7,680 cycles. New-row rendering and the
existing raster-0 sprite presentation need additional time. A single blind
copy across that interval cannot meet all these deadlines.

These badline/cache rules follow [Christian Bauer's VIC-II reference,
sections 3.5 and 3.7.2](https://www.cebix.net/VIC-Article.txt). Calculations and
scheduling below are specific to this program, not a claim that all
single-screen scrollers require this particular split.

Starting the phase counter at 3 gives the normal initial 25-row alignment,
but does not change the physical `7 -> 0` wrap or make the copy cheaper.
The implementation retains 0–7 and the existing three-game-update pixel divider.
The normal 25-row border clips/exposes partial edge rows as fine scroll changes;
there is no HUD or border-opening trick.

## Exact in-place algorithm

The diagnostic row source is reproducible from an 8-bit row ID. Each row has
two hexadecimal digits, two vertical rails and a diagonal feature crossing
row boundaries. `SCROLL_ROW` is the ID at the top of the matrix; it decreases
once per coarse transition, modulo 256.

1. `updateBackgroundScroll` requests a wrap while keeping fine 7 pending.
2. After gameplay and BUILD preparation, `prepareBackgroundCoarse` waits until
   raster 152. At fine 7, row 12 was fetched on raster 151. The VIC no longer
   needs screen RAM rows 0–12 for this frame.
3. Copy old rows 11–0 to destinations 12–1, in descending row order. Decrement
   `SCROLL_ROW` and render the new top row. Mark fine 0 for presentation.
4. The original frame-start wait returns near raster 0. `applyFineScroll`
   writes fine 0; plan swapping, sprite rendering and `armFirstBatch` run in
   their existing order.
5. Immediately **after** `armFirstBatch`, copy old rows 23–13 to destinations
   24–14, in descending order. Reproduce old row 12 at destination 13 from
   `SCROLL_ROW + 13`. That is the existing crossing row, not a second new row.
   At fine 0, the VIC does not fetch row 13 until raster 152.

The crossing row's reproducible source is what avoids temporary storage.
This is deliberately a diagnostic source, not a general copier for arbitrary
screen edits: any future mutable scenery must preserve or reproduce that row.
No complete terrain/stage system has been added.

The upper part must commit in the frame immediately preceding fine 0. If
BUILD preparation arrives at raster 200 or later, or above 255, the routine
leaves the entire old matrix/phase unchanged and retries on the next game
update. `BG_COARSE_DEFERRED` counts these retries modulo 256. This can hold
fine 7 longer under overload; it avoids publishing half a coarse transition.

`$D011` bit 7 reads the current raster high bit but writes IRQ compare high.
The existing fine-scroll write remains safe because it runs at raster 0 and
the existing scheduler uses compare values below 256. It is not a generic
read/modify/write recipe for arbitrary raster positions.

## Cost and placement

| Work | CPU cycles, excluding VIC stalls and IRQs |
| --- | ---: |
| Upper copy: 480 absolute load/store pairs | 3,840 |
| Lower copy: 440 absolute load/store pairs | 3,520 |
| New top row render | 561 |
| Existing crossing row render | 561 |
| Total data work | 8,482 |

Copy RTS instructions, calls and control add roughly another hundred cycles;
polling depends on arrival time. Both row renders include their RTS. Copy code
uses legal NMOS 6502 instructions and no indexed page penalties. The two tiny
assembler loops emit straight-line instructions, not runtime row loops.

Control/source code occupies `$2920-$2a60`; unrolled copying occupies
`$4000-$5591`. This is code, not VIC screen memory. Compile-time guards protect
the health sprites and BASIC ROM boundary. Screen writes stop at `$07e7`, so
sprite pointers at `$07f8-$07ff` are untouched by background routines.

Measured in the physical-frame stress recording, including stalls/interrupts:

| Portion | Entry raster | Completion raster | Elapsed cycles |
| --- | --- | --- | --- |
| Upper copy through new-row render | 152–156 | 229–251 | 4,853–6,260 |
| Lower copy through crossing-row render | 15–19 | 84–123 | 4,313–6,734 |

## Changes outside background routines

- One `prepareBackgroundCoarse` call after BUILD/debug work.
- One `finishBackgroundCoarse` call after each existing `armFirstBatch` call.
- Score/lives screen writes suppressed during PLAYING; scoring, lives and
  combat still run. The cycle minimum remains in RAM but is no longer printed.
- Two unused charset glyphs installed at game start for the diagnostic.

`armFirstBatch`, `multiplexIRQ`, `swapRenderPlans`, `renderSprites`,
`buildInitialSpriteSnapshot` and `buildBatchSpriteSchedule` retain identical
source bodies compared with the starting revision. Code addresses relocate
because of the small additions earlier in the resident segment. No sprite
assignment, pointer, ordering or raster-comparison algorithm was changed.

## Runtime evidence and limits (2026-09-05)

KickAssembler 5.25 builds successfully. Tests use PAL `x64sc`, simulated real
joyport inputs for movement/fire, and extra player stock written by the test
monitor so deaths and respawns do not end the recording. Shipping lives remain
three. Stress tests accelerate the existing spawner by changing only its timer
state through the monitor; production spawning is unchanged.

- Normal gameplay: **1,600 consecutive physical/presented frames**, **66 wraps**,
  up to 9 objects and one reassignment batch. All frame intervals were 19,656
  cycles. Zero deferred wraps, matrix mismatches or background pixel mismatches.
- Accelerated spawning: **2,200 game-update captures**, **90 wraps**, up to
  **16 objects / six batches**, with zero matrix/background pixel mismatches.
  This run exposed skipped physical frames between game updates, so it was
  followed by the physical-frame test below, not treated as sufficient evidence.
- Physical-frame stress: **1,200 consecutive PAL frames**, **27 wraps**,
  **16 objects / six batches**, **68,356,964 checked background pixels**, zero
  mismatches. Every capture was separated by exactly 19,656 cycles. It includes
  all intervening frames when the game updates less often. A 120-frame GIF and
  the 5/6/7/0/1 contact sheet are retained beside the captures.

The pixel check compares the visible interior against the independently
constructed row IDs/glyphs and excludes LIVE sprite rectangles. It does not
claim exhaustive automated sprite-bitmap validation. Sprite presentation was
inspected across the boundary contact sheet; the unchanged renderer/scheduler
bodies provide the code-level regression check.

**Full-load limitation:** the aggressive spawner overloads the original game
as well. In its unchanged 1,000-update comparison, 776 update intervals took
39,312 cycles instead of 19,656. The scrolling stress run also showed this
existing slowdown. The physical stress recording logged 39 deferred scroll
attempts, so fine 7 sometimes holds longer. The background remains continuous
and free of tearing, but this is not a claim of constant-speed scrolling or
50 Hz sprite-plan presentation at artificially saturated load. That broader
acceptance condition remains unmet; the existing multiplexer was not modified
to disguise or repair the baseline overload.

## Reproduce

Build using the existing VS Code **C64: Build** task. Launch a fresh emulator:

```sh
x64sc -default -pal -warp +sound -remotemonitor \
  -remotemonitoraddress ip4://127.0.0.1:6510 \
  -autostartprgmode 1 -autostart build/shooter.prg
python3 tools/vice_scroll_test.py --port 6510 --physical --stress --trace \
  --frames 1200 --out build/scroll-test/repeat
python3 tools/check_scroll_capture.py build/scroll-test/repeat \
  --charset build/scroll-test/repeat/charset.bin
```

The checker requires Pillow; the capture tool uses the Python standard library.
Use a fresh emulator for each test if its remote monitor stops accepting
connections after a disconnected breakpoint session. Captures, JSON reports,
GIFs and monitor traces are under ignored `build/scroll-test/`.
