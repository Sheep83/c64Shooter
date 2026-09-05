# PAL HUD architecture study

Source authority: `9d868b4`, independently rebuilt with KickAssembler 5.25.
The pre-existing `build/shooter.prg` and symbols were stale and differed from
that source. All measurements below use the fresh build. Working tree remains
uncommitted. This study assumes that gameplay sprites may briefly cover text
inside the playfield; it does not promise an always-foreground HUD.

## Timing model established before the diagnostic implementation

PAL has 312 lines of 63 cycles. The engine presents an initial snapshot near
line 0; only subsequent hardware-slot reassignments use raster IRQs. Logical
player object 0 has no permanent hardware slot. `renderSprites` owns the
initial pointer, colour, X, Y, enable and X-high writes; `armFirstBatch` and
`multiplexIRQ` own the single raster compare and soft IRQ vector.

The schedule chooses **min(Y - 12)** within a batch, despite the variable
name `SCHED_BATCH_LATEST`. A slot becomes reusable at Y + 24, saturated to
255, which is also the unavailable sentinel. Enemy motion permits **0..255**;
only arithmetic underflow/overflow deactivates it. Thus the analytical latest
compare is **243**, not 242. The earliest possible reassignment is **24**:
initial Y=0 frees a slot at 24 for a later object at Y=36. The initial snapshot
itself has earlier ownership, including Y=0; an IRQ-free interval is not a
sprite-free interval. Player Y is bounded to **49..230**, so a player assigned
after eight early enemies can require a first IRQ at **37**, not 208.

Controlled inputs passed through the actual assembled sort/snapshot/scheduler:

| Input, with player listed first | Result |
| --- | --- |
| 49, eight enemies at 0 | Eight initial enemies; player batch at 37 |
| 49, eight at 0, one at 36 | First batch at 24, two assignments |
| 49, eight at 38 | All eight hardware slots initially occupied; player unschedulable in this baseline state |
| 230, seven at 100, eight at 255 | Seven assignments at 243; one late object unschedulable |

These are boundary-state tests, not claims that those exact formations were
observed during ordinary spawning. The last case executed the actual IRQ via
the KERNAL entry: handler entry **244:26**, exit to `$EA31` **262:11**,
**1,119 cycles inside the handler**, with collision scanning bypassed through
the existing exploding-player state. KERNAL entry/exit costs are additional.
`$EA31` runs the normal KERNAL IRQ service, not merely an RTI epilogue.
The raster chain disables itself within the final batch, not on an additional
cleanup interrupt. Main-loop presentation may skip physical frames at load;
a border event must recur on every physical frame, including those skips.

## Border hardware correction

DEN-low was the wrong experiment. DEN gates display/badline enabling and the
opening of the vertical border; it does not inhibit its bottom closing test.
The appropriate technique is to keep RSEL=1 through line 247, clear it during
248..250, then restore it after 251. Preserve DEN and YSCROLL throughout.
This avoids both bottom comparisons and leaves the border open across frame
wrap, making the following top border available too. It needs a bounded
several-line deadline, not a single-cycle DEN pulse. Ordinary side borders
remain. There is an initialization frame before the first open top border.

The isolated PAL test used solid sprites at Y=26 and Y=252: baseline and DEN
toggle hid them; RSEL switching displayed both, plus the Y=26 sprite's second
trigger at raster 282. Sprite Y comparisons use the low eight raster bits.
The default 384x272 capture starts at raster 16; screenshot row numbers and
transparent sprite margins must not be mistaken for the border comparator.

Hardware source: [Christian Bauer, VIC-II reference, sections 3.8–3.10 and
3.14.1](https://www.cebix.net/VIC-Article.txt). The reference specifies bottom
comparisons at 247/251, top comparisons at 55/51, and sprite DMA checks in
cycles 55/56. All engine scheduling conclusions above are from local source
and local emulator measurements.

## Options

| Option | Raster and D011 requirements | Ownership and worst conflict | Complexity, maintenance, score/lives scaling |
| --- | --- | --- | --- |
| A. True top-border sprites | Open the preceding bottom border in 248..250; restore RSEL after 251, preserve fine scroll. Program HUD before its Y DMA check; release after its 21-line DMA lifetime, then restore gameplay before its Y checks. | No guarantee of one or two free initial slots. Eight early enemies may occupy all slots; first reuse can be 24 and the player can need 37. Snapshot writes near 0 would overwrite a HUD installed in the preceding frame. Very early Y also has a second trigger above 255 and lies partly outside the normal crop. | Better handover opportunity than bottom in common scenes, but no guaranteed pre-gameplay window. Needs merged recurring event chain, conditional slot lending, snapshot changes and collision/mode restoration. Two fields increase simultaneous demand. Rejected as a permanent guaranteed HUD under current bounds. |
| B. True bottom-border sprites | Same RSEL window. HUD at Y=252 needs registers ready by cycle 55/56 there. | Gameplay Y=255 retains DMA through approximately 276; scheduler's conservative reuse would be 279 in a wider representation. Last compare 243 does not mean slots or CPU are free. Measured handler ran through 262, missing the RSEL window altogether. | A terminal special batch alone is insufficient. Interleave/preempt gameplay work to meet the border deadline, plus establish per-slot handovers and repeat on skipped frames. Two fields need two proven free slots. Rejected. |
| C. Sprite overlay inside playfield | No D011 change. For HUD Y=H, install before H:55 and retain through the 21-line DMA; current scheduler would reserve through H+24. | Eight overlapping gameplay sprites can consume every slot at any proposed visible HUD band. A main-thread write after `armFirstBatch` is still before most gameplay DMA/IRQs and does not transfer ownership. | Conditional lending can flicker or reduce capacity. Permanent reservation violates the capacity constraint. One or two fields do not remove the conflict. Rejected as a guaranteed display. |
| D1. Reserve ordinary character rows | No sprite use, but each row still follows global fine scroll and the in-place coarse copy. | Simply omitting those rows from copying leaves the text moving by 0..7 pixels and changes the terrain transport/crossing contract. | A truly fixed character band normally needs a local scrolling-region redesign; easy score/lives formatting afterwards. Rejected in that form. |
| D2. Character raster split in this same matrix | Fixed YSCROLL for the band; restore scrolling YSCROLL before the first terrain badline. Badlines are 48+8r+fine, with matrix fetches starting at cycle 15. Changing fine near the split can insert/suppress fetches and alter row-counter progression. | Must share the one IRQ chain, including early player/reuse events. Requires a new proof of matrix row mapping, coarse seam, and split service latency under sprite DMA. | Familiar long-term architecture if a playfield redesign is allowed, but conflicts with this task's preserved scroller and timing constraints. Two character fields scale easily. Rejected here. |
| E. Phase-compensated character patches | Leave global fine scroll, D011, D018 and badlines unchanged. Select pre-shifted glyph codes after arming sprites and before the HUD rows' first fetch. Restore underlying cells after their old fetches, before coarse copying. | Zero hardware slots. Screen-cell ownership must be explicit so HUD codes never propagate into terrain. Gameplay sprites retain their normal foreground priority and may cover text. | Small localized data overlay with ordinary frame-level deadlines; no second scrolling architecture. Best fit if occasional occlusion is acceptable. Score digits can share phase-glyph tables; lives can use a digit/icon. Only two static markers are authorized in this proof. |

A later bottom sprite using Y=24 at raster 280 could avoid Y=255 DMA, but
still requires the missed 248..250 opening event; most of its height also lies
below the default capture's raster-287 edge. Side-border sprites require
horizontal CSEL changes on individual lines and still occupy hardware slots.
Idle-pattern tricks outside the character display do not supply independent
readable score/lives fields without substantial raster work. None improves
on E for this engine's constraints.

## Selected diagnostic contract

Two 8x8 markers occupy columns 2 and 31, at fixed raster Y=80..87. Each uses
matrix rows 3 and 4: their fetched row origins are 72+fine and 80+fine. With
phase f, put the first f bitmap rows at the end of the upper glyph and the
remaining 8-f rows at the beginning of the lower glyph. Their visible pixels
then stay at 80..87 for all eight phases. The surrounding blank footprint
is two character cells tall and follows fine scroll; this is diagnostic art.

Glyphs are immutable after initialization. Four underlying terrain bytes are
saved the first time patches are installed. Subsequent fine phases only
change their four glyph codes. Before `shiftBackgroundUpper`, at raster 152
or later, restore those bytes and relinquish patch ownership. Their old
fetches finished by raster 87. The unchanged copy and metatile decoder then
transport pure terrain. Next presentation saves the new underlying terrain
and reinstalls the patches. No cell in crossing row 12/13 is borrowed.

Draw after `armFirstBatch`, before `finishBackgroundCoarse`: no gameplay IRQ
is armed later, and no hardware sprite register changes. HUD writes must
finish before row 3's earliest fetch at 72:15; lower copying must still finish
before 152:15. Existing late-start coarse deferral stays intact. The baseline
500-frame physical stress test reached arm entry 21:12 and lower completion
100:45, with 13 wraps and no pixel errors. These are measured margins, not
claims of unlimited future CPU headroom. Expanded fields require budgeting
their cell writes against the same two deadlines.

The main-thread `$D011` writes preserve the other display bits; the compare
high bit is currently cleared near frame start. A future border event above
255 would also need explicit compare-high ownership rather than arbitrary
read/modify/write of a register whose read bit 7 is the current raster high.
Neither DEN nor RSEL is changed by this proof. Actual PLAYING values cycle
through `$18..$1f` (plus the read raster-high bit), rather than staying `$1b`.

For D2, even a one-row fixed band illustrates the mapping problem: a fixed
fine-3 row occupies 51..58, while the existing next terrain row's fetch would
be 56+f, i.e. 56..63. A simple register toggle cannot keep that first row
fixed and retain every original following-row fetch for all eight phases.

## Implementation and verification

Implemented only the circle and X. `drawHudDiagnostic` costs **51 CPU cycles**
including its call on an already-patched frame, **88** when saving four new
terrain bytes. Restoring terrain before a coarse copy costs **56** including
the call. These counts exclude VIC stalls/interrupts. State is five bytes;
the 32 immutable phase glyphs take 256 bytes. No score formatting, lives
logic, final artwork or gameplay behaviour was added.

The existing renderer, batch scheduler, plan swapping, multiplexer IRQ,
fine-scroll writer, metatile decoder and all four copy/save/restore routine
bodies compare unchanged against HEAD. Only four hooks were added: initialize
glyphs, draw at the two existing presentation sites, and restore terrain
before upper copying. Code still fits below the existing memory guards.

| Verification | Normal proof | Stress proof |
| --- | ---: | ---: |
| Consecutive physical PAL frames | 1,600 | 1,200 |
| Fine 7→0 wraps | 66 | 27 |
| Maximum active logical objects | 9 | 16 |
| Maximum LIVE gameplay batches | 1 | 6 |
| Observed coarse deferrals | 0 | 1 |
| Latest HUD-ready trace | 28:58 | 40:10 |
| Latest lower-copy completion | 93:14 | 124:41 |
| Checked background/HUD pixels | 94,340,103 | 68,292,556 |
| Uncovered HUD-footprint pixels checked | 403,076 | 292,262 |
| Matrix, saved-terrain or pixel failures | 0 | 0 |

All eight fine phases occurred. Every physical frame interval was 19,656
cycles. Each checked frame after initialization had uncovered marker pixels;
occluded pixels are explicitly excluded, not treated as successful visibility
checks. The checker compares the **entire matrix** against independently
decoded terrain plus the four owned patches, checks the saved bytes, and
checks visible pixels against fixed marker coordinates instead of merely
mirroring the phase lookup. It includes coarse-copy frames where the VIC's
cached display still shows the markers but screen RAM has already been
restored to terrain. Visual inspection confirms the circle and X in play.

Additional boundary tests on the proof build retained the first batch at 24
(HUD ready 19:34; VIC IRQ entry 24:38) and the seven-assignment batch at 243
(HUD ready 25:12; VIC IRQ entry 243:41). The player was Y=49 in the early case.
These demonstrate that HUD work after arming does not replace either event.
They do not claim to repair baseline unschedulable objects or late assignment
execution. The test distinguishes VIC events from intervening CIA IRQs.

Independent **unmodified-source** measurements: 1,600 normal physical frames
with Y=0..255, player 49..230, up to eight active objects and no reassignment
batches in that particular firing run; 1,200 accelerated frames with Y=0..255,
16 objects, seven batches and compares 66..243. Player movement slowed with
game updates under stress (observed 61..220). Eight initial sprites overlapped
the candidate top HUD band in stress, and the player was absent from the
initial eight in 937 captures. These observations replace the prior report's
numerical claims rather than attempting to reproduce its random sequence.

The separate 500-frame baseline scrolling check passed 28,999,110 pixel
comparisons with one deferral. Workloads are not cycle-identical: the spawner
uses a CIA timer as its random seed, so these deferral counts do **not** prove
zero performance cost. Stress still repeats old presented plans on some
physical frames, as the baseline does. The static HUD remains valid in those
frames because both its cells and physical fine phase remain unchanged.

## Permanent direction and limits

**Choose E**, with explicit HUD character/cell ownership. One five-digit score
and one lives digit need twelve patched cells and twelve saved terrain bytes.
They can share ten sets of 16 phase glyphs: 160 character codes. The current
stage uses only 32, 35, 42, 224 and 225, so reserving playfield codes 64..223
would fit that future digit table without another matrix, a charset switch or
runtime glyph animation. That reservation and formatting are not implemented
by the diagnostic. Additional icons/labels need their own allocation budget.
Extend the same bounded cell writes and remeasure before expanding the HUD.

This proof preserves scrolling transport, its row-12 crossing buffer,
fixed colour RAM, all eight hardware sprites and the single IRQ chain. It
does replace four displayed character cells, so it is an opaque character
patch, not transparent text composited over terrain. It never enters logical
object allocation or sprite collision ownership. Gameplay can cover it.

If the requirement is instead **unobscured HUD text in every frame**, this
implementation is not that architecture. A foreground-priority split would
restore the IRQ scheduling problem; globally placing sprites behind terrain
would change gameplay rendering. Under that stronger requirement, stop with
no approved permanent architecture: the next options require relaxing either
the scroller-region constraint (a fixed character band) or the sprite/raster
scheduling constraints (top-border lending plus a bounded recurring chain).

Within the present constraints the ranking is E, then D with a deliberate
playfield adaptation, then A with a scheduler adaptation. B and C cannot
guarantee available slots; late-bottom aliasing and side-border tricks do not
remove their timing/ownership blockers. Ordinary raster scheduling is retained
for E, but timing headroom is finite: no claim covers arbitrary future IRQ
work, new glyph sizes or larger HUD regions without revalidation.

## Reproduce and inspect

Build with the VS Code build task. Launch a fresh PAL emulator and use:

```sh
x64sc -default -pal -warp +sound -remotemonitor \
  -remotemonitoraddress ip4://127.0.0.1:6510 \
  -autostartprgmode 1 -autostart build/shooter.prg
python3 tools/vice_scroll_test.py --port 6510 --physical --stress --trace \
  --frames 1200 --out build/hud-study/repeat
python3 tools/check_hud_capture.py build/hud-study/repeat
```

The checker needs Pillow. Its dedicated HUD model supplements the existing
terrain-only checker, whose assumption of no patches is intentionally retained.
Remove `--stress` for normal play. Fresh emulators avoid VICE's occasional
failure to accept a new monitor connection after a disconnected breakpoint.

Ignored local evidence is in `build/hud-study/`: `proof-normal/` and
`proof-stress/` contain captures, timing logs and `hud-verification.json`.
`evidence/` retains the original fresh baseline binary/symbols, scheduler
boundary inputs/results, baseline frame measurements, and the isolated
RSEL/DEN test source, screenshots and monitor log. Scratch scripts retain
their original `/private/tmp/hud-study` paths/ports; adapt those before reuse.
No commit was made.
