# 19656 fixed top HUD — active Codex worklog

## Status / exact next step

**Active continuation: Phase A/B prerequisites pass; beginning Phase C structural proof.**
The shared scheduler changes are uncommitted in main.asm/raster_scheduler.asm.
Normal, long and stress assignment/scroller checks pass as recorded in the
resumption sections below; lifecycle/explicit overdue checks are being completed.
All12 formation trajectories have been measured for the proposed viewport.
No production viewport or fixed-HUD display writes have been added yet.

The old Phase1 stop/handoff sections are historical. Continue from the latest
resumption entries at the end; do not repeat Phase1 or discard these source edits.

## Baseline / repository

- Initial checkout was clean on `background-scroll-first-working-prototype`
  at `f6e9620`. User explicitly requests main; switched cleanly to local main
  at `1145f65` (tracks `origin/main`). Their file trees compare identical.
- No AGENTS.md exists in either git tree, anywhere found within the checkout,
  or in the checked ancestors through `/`. No agent delegation instructions
  were found; no sub-agents started.
- No uncommitted plaque experiment or unrelated user work existed.
- The committed four-cell circle/X patch diagnostic remains in the baseline.
  Its calls/routines/data will be removed if a supported replacement is
  implemented; it is not protected production architecture.
- Fresh KickAssembler 5.25 build succeeded using `.vscode/tasks.json` paths.
- Baseline PRG SHA-256:
  `5e46c07eb3469cc1fd11c45ade795158611e3082c4f9e13730c5325e27eacb7c`.
- No commits or pushes authorized for the final proof; leave work for review.

## Verified source facts

`src/main.asm` and `src/variables.asm` inspected after switching to main.
Older `docs/fixed-hud-feasibility.md` predates the 24-row conversion and rejects
changes that this user now explicitly authorizes. It is historical evidence,
not the authority for this task. It also contains incorrect claims about
sprites being visible through the border and an overly loose earliest-batch
bound; use actual source/hardware instead.

### D011 / D018

- D011 writers: `init` clears RSEL; `applyFineScroll` preserves bits 3..7 and
  publishes fine at frame start; `armFirstBatch` clears compare high when it
  has gameplay batches; `endGame` restores fine 3 while preserving RSEL=0.
- RSEL=0, DEN=1. During gameplay lower seven bits normally `$10..$17`.
  D011 reads raster bit 8 but writes raster compare bit 8. A persistent HUD
  chain above line 255 would require deliberate compare-high ownership.
- `init` is the only explicit D018 writer: preserve screen nibble, set charset
  bits to `$0e`; actual setup is screen `$0400`, charset `$3800`, VIC bank 0.
  No second screen, matrix switching or background shadow exists.
- Ordinary 24-row visible aperture: rasters 55..246 inclusive, 192 pixels.
  Badlines remain 48+f+8r, r=0..24, for fine f=0..7. All fetched image pixels
  occupy 48+f..247+f. RSEL cropping hides both edge idle gaps.

### Coarse scrolling

- Prepare (fine 7): wait until >=152, reject starts >=200 or raster high set;
  restore patch HUD terrain, save physical old row 12; copy old rows 11..0
  into 12..1; decrement stage origin modulo 80; decode/install new row 0;
  set pending fine 0 and lower-finish flag.
- Row 12 fine-7 fetch =151; old upper rows are safe to overwrite afterwards.
- Next physical presentation: publish fine 0, swap BUILD/LIVE, initial sprites,
  arm gameplay IRQs, draw patch diagnostic, then finish lower copying.
- Finish: old rows 23..13 ->24..14; saved old row12 ->13. Row13 fine-0 fetch
  deadline is 152. Row24 fine-0 fetch is 240.
- Unrolled upper copy 480*8=3,840 CPU cycles; lower 440*8=3,520; physical
  crossing save/restore each 40*8=320 plus RTS/calls. Decoder/incoming row
  work is additional. No changes made to these bodies.
- BG_INCOMING_ROW and BG_CROSSING_ROW are separate 40-byte CPU buffers.

### Sprites and IRQ lifecycle

- 16 logical objects, object 0 permanently player; hardware slot assignment
  derives from sorted Y and is not permanently tied to logical object 0.
- Initial up-to-eight snapshot written near raster 0. Reassignment batch
  compare is min(Y-12) among its members; slot reuse is Y+24, saturated at
  255/unavailable. Legal enemy Y includes 0 and 255. Earliest reuse compare
  24 is possible; latest is 243. Player minimum Y=49 can need batch 37.
- `armFirstBatch` disables raster IRQs while publishing; with no batches it
  leaves them disabled. Otherwise vector `$0314` points to `multiplexIRQ`.
- IRQ captures collisions, applies a variable-length batch, acknowledges and
  chains next compare. Final batch disables raster IRQs in that same handler.
- KERNAL ROM saves registers before `$0314`; handler jumps to `$EA31`, which
  performs KERNAL service rather than only a short register/RTI epilogue.
- D015 writes currently occur in setup, initial snapshot rendering, and game
  teardown. Batch IRQs change pointer/colour/X/Y/X-high, not the enable mask.
- Under load main-loop presentation can skip physical frames. A fixed HUD
  needs its display state restored every *physical* frame, not merely when
  `applyFineScroll` happens. IRQ-visible fine must belong to presented LIVE
  state, not the pending main-thread SCROLL_FINE after coarse preparation.

## Candidate geometry analysis in progress (not yet approved)

Earliest fully visible stock 8-pixel HUD row in the current aperture is matrix
row0 fetched at fine7, raster55, visible55..62. First terrain fetch cannot
reset RC before that row finishes, or the stock text is truncated.

A naive switch after the HUD makes the first terrain fetch vary over an
eight-line interval. It reintroduces the very top-edge idle/reveal problem
that RSEL cropping solved. Merely reserving ordinary blank character rows or
painting those rows black does not produce a stationary crop of the scrolling
terrain: the colour/character row boundary itself moves with fine scroll.

Working hypothesis to probe: HUD55..62, a fixed masked separator63..70, then
terrain71..246 gives 16 status lines and a 176-pixel gameplay aperture. Terrain
row1 would first fetch64+f (64..71), so crop71 sees a continuous incoming edge.
Below it rows1..23 are fetched; row24 would be outside the badline interval.
This would preserve the beam-raced algorithm with incoming matrix row1,
upper copy1..11 ->2..12, physical crossing12->13, lower13..22 ->14..23;
row12 fine7 fetch159 (prepare >=160), row13 fine0 fetch160. CPU copies would
shrink to440 and400 bytes. This is a derivation, not measured implementation.

Open blockers before calling that candidate viable:

1. How to mask separator/fetched terrain until the fixed boundary without
   border opening, dynamic compositing, or truncating the HUD. Standard VIC
   invalid graphics modes could mask pixels with one D011 change, but this
   is only an idea: must verify counters/fetches, justify maintainability, and
   prove a safe write window under badlines. Do not silently adopt it.
2. D015 gating may discard starts for sprites crossing the band instead of
   clipping their visible tails. Verify actual NMOS-era VIC behaviour; do not
   repeat the historical assumption that D015 is an instantaneous pixel mask.
3. Early variable-length gameplay IRQs may overlap the HUD deadline. An
   unconditional event alone is insufficient: event ordering and non-preemptive
   handler duration must be bounded. No changes to sprite scheduling yet.
4. Main-loop frame skips, CIA/KERNAL IRQ service, and raster-high compare state
   require an explicit lifecycle for any permanent raster chain.

8/10/11/12-line candidates must be tested against the first-fetch/continuity
constraint, not selected by aesthetics. A 16-line hypothesis is not yet a
winner. If no complete timing/ownership model survives these probes, stop
with exact blockers rather than producing an unvalidated partial engine.

## Tests / artifacts

Fresh baseline capture completed; see continuation results below. Existing
capture and HUD/matrix/pixel checker source
inspected; ordinary HUD checker covers raster55..246, models four patched
cells, and is not a checker for a future genuine fixed region. Future oracles
must explicitly check the entire fixed region without sprite exclusions.

Use fresh VICE instances for authoritative tests. Do not rely on old ignored
plaque captures or old binaries under build/hud-study. Store this task's
new evidence under build/fixed-hud-codex/ and retain baseline PRG/symbol hashes.

## Continuation measurements — fresh baseline and sprite gate

Fresh baseline physical capture completed:

```sh
python3 tools/vice_scroll_test.py --port 6530 --physical --trace --frames 600 --out build/fixed-hud-codex/baseline
PYTHONPATH=/private/tmp/hud-study/python-deps python3 tools/check_hud_capture.py build/fixed-hud-codex/baseline
```

Result: 600 frames, all eight fine phases, 24 **coarse transitions** (the
checker labels these `wraps`; they are not complete 80-row stage wraps),
max active9/batches1, deferred0, physical delta19656 only,
35,226,402 terrain pixel checks +152,402 HUD pixel checks, zero failures.
Baseline build/symbol copies: `build/fixed-hud-codex/baseline.{prg,vs}`.

Isolated PAL gating probe in a separate fresh VICE (port6531), source and
capture controller/results under `build/fixed-hud-codex/probes/gating*` and
`capture-gating.py`. Sprite0 is solid white, X100 Y50; visible body ends71.
Four measured cases, each settled for two complete physical frames:

| Mode | Change | Captured white sprite pixels |
| --- | --- | --- |
| 0 | Enabled throughout | 24 pixels on every raster55..71 |
| 1 | D015 cleared near54, restored70 | Identical:55..71 |
| 2 | D015 cleared near0, restored70 | None, including the tail at71 |
| 3 | Enabled with blank pointer, restore solid pointer70 | 24 pixels at71 only |

Thus D015 cannot directly clip an already running sprite. Pre-start disabling
loses legal straddling tails. A single blank-pointer swap can clip a sprite,
but that is not proof for eight pointers with distinct DMA fetch slots and
an overlapping reassignment IRQ. Source reference cross-check:
[Christian Bauer VIC-II article](https://www.cebix.net/VIC-Article.txt), section
3.8.1, agrees that enable participates in DMA-start decisions. Captured pixels
are the authority for the above measured result.

Possible alternatives still **unproved**, not implementation decisions:
- Cull any sprite whose origin is above the playfield: simplest gate, but
  changes the visible tails of legal early objects and must not be silently
  substituted for clipping.
- Blank pointer gating: individual proof works; eight pointer writes and
  early batches require a separate worst-case DMA/timing proof.
- BUILD/LIVE private clipped sprite bitmaps could retain tails without a
  raster pointer deadline, but add CPU/memory/ownership work. No buffers
  allocated; no source changes. Evaluate only if a small justified addition
  satisfies the protected architecture, otherwise stop.

Geometry probe `probes/geometry.asm` is now running on fresh VICE port6532.
It isolates matrix row0 fixed at55..62, terrain row1 first-fetch64+f, and an
optional black graphics-mode interval63..70. Its polled writes are a hardware
experiment, NOT an IRQ architecture or a stress-safe production proof.
Next step: capture all phases with mask off/on; verify row/scanline identity,
HUD pixels, and exact mask-end writes. Then assess early IRQ deadline overlap.

## Geometry probe results — not a production solution

`geometry.asm` uses stock ROM text copied to3800 and deterministic tagged
terrain glyphs. Row0 at55..62 is identical across all phases. With masking
off, the first terrain pixels appear at64+f: separator63..70 contains seven,
six, five, four, three, two, one, zero terrain scanlines for f0..7. Pixels
71..246 match the independent row/glyph oracle in all eight cases.

With ECM+BMM set only during the separator, all graphics become black while
fetches continue. The first no-sprite polling version restored D011 too early
at phases3/4: respectively8/16 pixels leaked at the right of raster70.
Measured STA entry positions were70:51/70:50 (VICE zero-based cycles).
Adding two NOPs fixes those no-sprite cases; this is NOT a general timing fix.

The adjusted version was tested with six DMA masks (00,01,07,80,F8,FF), all
sprites blank but actively fetching, Y50. All eight phases tested for each:
48 cases total. Masks00/01/07/80 passed the separator + terrain pixel oracle.
MasksF8 andFF failed every phase (16 failing cases): graphics restored late
into raster71. FF/fine0 also had extensive fetch corruption (4,677 pixel
mismatches), consistent with the first fine write arriving too late for its
badline; exact write/fetch trace still needed to isolate that mechanism.
`geometry-dma-results.json` contains counts and first mismatches for each case.

This establishes that the simple polled handler is **not stress safe**. It
must not be inserted into production. It does not prove that a stabilized,
first-class shared raster handler is impossible. Before selecting16 lines,
a follow-up must solve the deadline under all DMA masks/Y starts and early
sprite assignments, as well as sprite visibility clipping itself.

A fresh1,000-frame accelerated-spawner baseline capture completed at port6534;
checker running. Constructed legal early24/player37/late243 schedule probes
are now running against the original build in separate fresh VICE instances.
They use blank sprite pointers to isolate handler cost and D011fine7 to model
the fixed HUD's55 badline. No resident instructions are modified; main CPU
idles in a scratch6000 JMP loop after real initial render/arm. This isolates
IRQ duration and does not establish complete gameplay/split integration.

## Candidate comparison at the analysis gate

All ranges below are PAL raster lines inclusive, using the existing RSEL0
aperture55..246. Stock text needs all eight pixels55..62; the architecture
must not depend on the current font having a blank last scanline.

For an ordinary one-row text HUD followed by ordinary terrain row fetches,
the first terrain fetch cannot precede63 without resetting the HUD's RC
before its eighth scanline. Its scrolling start must range over eight
consecutive rasters. Even with a rotated fine-phase mapping the earliest
range is63..70. A fixed continuous crop must begin at or below the last start.
This is a lower bound for this **ordinary text-row split**, not a proof that
all VIC tricks for shorter regions are impossible.

| Status height | HUD/status range | Desired terrain range | Loss / remaining gameplay pixels | Assessment |
| --- | --- | --- | --- | --- |
| 8 | 55..62 | 63..246 | 8 /184 | Cannot fit a complete fixed text row plus the eight-phase incoming crop with ordinary row fetches. |
| 10 | 55..64 | 65..246 | 10 /182 | Same conflict; at least five-phase-start interval extends below boundary in the earliest63..70 mapping. |
| 11 | 55..65 | 66..246 | 11 /181 | Same conflict; four later first-fetch phases extend below boundary. |
| 12 | 55..66 | 67..246 | 12 /180 | Same conflict; three later first-fetch phases extend below boundary. |
| 15 (derived bound) | 55..69 | 70..246 | 15 /177 | First-fetch63+q, physical fine=(q+7)&7. Needs fixed black masking. Rotates all logical phase/fetch deadlines; not probed. |
| 16 | 55..70 | 71..246 | 16 /176 | First-fetch64+f, retains current fine mapping. Geometry independently pixel-checked. Fixed masking and sprite ownership/IRQ deadlines remain unresolved. |

For16, candidate state sequence (only the isolated probe exists):
- HUD row0 first badline55, D011=$17; DEN1/RSEL0 throughout.
- Change to interim fine1 after HUD badline and before63, avoiding a repeated
  fine7 badline63. The probe writes `$11` near60.
- Near63 enable black graphics output with ECM+BMM (`$70|f`), retaining DEN1
  and RSEL0. For fine7 retain interim1 until64 so63 does not become a badline.
- Terrain row1 begins64+f, then rowr begins56+f+8r (r1..23).
- Restore normal text `$10|f` between the last visible pixels of70 and the
  first pixels of71. This sub-line window is the failed DMA-stress deadline.
- D018 stays `$1e`, bank0/screen0400/charset3800. No screen switch or border
  opening. Invalid **VIC graphics mode** is distinct from an illegal NMOS
  CPU instruction; all probe CPU instructions are legal. It still needs
  justification and timing proof before being considered maintainable.

For16 the beam-raced concept need not be replaced: matrixrow0 becomes fixed;
terrain rows1..23 move downward. Upper1..11 ->2..12, crossing12 ->13,
lower13..22 ->14..23, incoming1. Row12 fine7 fetch159; prepare can begin160.
Row13 fine0 fetch160; finish must restore crossing before that fetch. Upper
copy shrinks3840 ->3520 CPU cycles, lower3520 ->3200; crossing save/restore
remain320 each, excluding call/RTS overhead. Decoder cost remains additional.
Row24 would first fetch248+f, outside the badline interval, so no live terrain
storage is needed there. No copy body or threshold has been changed.
The existing latest prepare threshold200 cannot simply be retained on faith:
new IRQ cost, decoder and next-frame setup must be included in its proof.

For15, rowr starts55+q+8r. Crossing row12 at q7 fetch158 and row13 at q0
fetch159, so prepare/finish boundary becomes159. At q0 an extra hidden row24
badline occurs247; this differs from16 and adds bus contention. This extra
phase remapping buys only one pixel. Thus16 is the leading geometry to research,
not an approved production architecture or a selected implementation.

All candidates share the earliest/late sprite conflicts below. None needs
D018 screen switching; none has a proven sprite gate. The short candidates
would additionally need row-counter/fetch tricks or a different representation
to meet the pixel continuity requirement. Do not introduce those casually.

## Exact legal sprite schedule probes

Fresh instances; blank sprite data eliminates collision hits but leaves DMA.
Objects0..15 Y values and generated LIVE plans are retained in
`probes/schedule-results.json` and `schedule-overlap55-results.json`.
All four produced one8-assignment batch, from the original builder:

| Case | Raster compare | Measured handler entry | Jump to EA31 | Entry to EA81 | Handler elapsed to EA31 |
| --- | --- | --- | --- | --- | --- |
| earliest enemy | 24 | 24:38 | 43:04 | 45:54 | 1163 cycles |
| player Y49 after eight Y0 objects | 37 | 38:00 | 57:18 | 59:62 | 1215 cycles |
| player Y67 after eight Y0 objects | 55 | 56:17 | 76:19 | 79:01 | 1262 cycles |
| late objects Y255 | 243 | 243:38 | 263:51 | 267:12 | 1273 cycles |

Cycles here are VICE's zero-based line positions. EA81 is **entry** to the
register-pop/RTI tail, not completion. These are measured no-hit cases,
not worst-case collision bounds. The player37 case's CIA service at34 ran
through37, delaying the VIC handler to38. This is an actual source of jitter.

The55 case decisively rejects adding a stand-alone boundary compare: the
existing non-preemptive handler is still executing across63..71. A new chain
must merge display operations *inside/between bounded gameplay work*, or
otherwise prove that assignments can move while respecting old-slot DMA and
new-object starts. A second independent IRQ cannot solve this. No dispatcher
change has been made, and no claim of a general impossibility is justified.

The latest243 batch still finishes before300 in this measured no-hit case;
that is not a worst-case frame-reset bound. The one-chain design would need
an unconditional physical-frame reset and HUD boundary event even at<=8
objects, when existing `armFirstBatch` disables raster IRQs. It must also own
D011 compare-high and keep displayed fine in LIVE state across main-loop
frame skips. The full KERNAL/CIA lifecycle must be included in that design.

## Baseline stress result and an independent schedule finding

The fresh1,000-frame stress checker passed: all8 phases,23 coarse transitions,
16 active objects,6 batches, deferred counter1, physical delta19656 only,
57,636,888 terrain pixel checks and248,115 diagnostic HUD checks, zero failures.
This is a **scroller/matrix/pixel-mask-oracle pass**, not proof every sprite
batch completed in its intended frame. Existing checker excludes the sprite
rectangles described by the plan, without checking whether sprites were drawn.

A separate final-pointer comparison found120/1000 frames where the hardware
pointers did not yet reflect all LIVE assignments. All120 had BATCH_INDEX>0:
51 at index1,57 at2,9 at3,3 at4. These are unfinished plans, not evidence of
random pointer-memory corruption. Concrete captured example:

- frame90 LIVE0: batches146(count1),150(count2); at raster311 BATCH_INDEX=1.
  Only the first assignment had affected hardware pointers.
- timing log: VIC handler starts146:43 in frame90; no150 handler that frame.
- frame91 keeps the same LIVE plan; handler occurs150:50 and completes it.
- The next raster compare was apparently installed after its line had passed,
  so it waited a physical frame. A direct watch on D012 writes is still needed
  to prove the exact late-arming instruction cycle; the observed one-frame
  delay and unfinished pointers are already established.

Do not repair this incidentally in HUD work or call the whole scroller broken.
It is relevant to the prerequisite shared-event design: a new mandatory HUD
cannot inherit this handling of deadlines. The existing batch builder considers
slot-free/Y-12 windows but does not itself budget execution time between compares.
An eventual display dispatcher needs an explicit policy for pending/past compares,
plus proof that it does not reassign before old sprite DMA is finished.

Coarse timing, measured elapsed wall cycles (includes DMA and IRQs):

| Trace span | Normal entry / exit raster ranges | Normal elapsed cycles | Stress entry / exit raster ranges | Stress elapsed cycles |
| --- | --- | --- | --- | --- |
| shiftBackgroundUpper to bgUpperCopied | 158..163 /225..233 | 4253..4722 | 158..161 /225..242 | 4223..5181 |
| shiftBackgroundUpper to bgUpperReady (includes decode/install) | 158..163 /259..266 | 6391..6822 | 158..161 /258..274 | 6294..7158 |
| shiftBackgroundLower to bgLowerReady (includes crossing restore) | 6..22 /71..92 | 3986..4359 | 17..37 /81..132 | 4071..6776 |

These spans begin at copy entry; they do not include upper crossing-save time
or every surrounding call. Normal traces contain25 copy spans, whereas24
7->0 transitions lie fully inside the600-frame observation interval.
At the latest observed stress finish132, the existing crossing fetch deadline152
still had about20 raster lines (1260 wall cycles) remaining. A16-line HUD would
move that deadline to160 and save320 copy CPU cycles, but a new HUD handler's
interrupt occupancy consumes part of this margin; it has not been bounded.

Deferral sample: frames223..224 fine7/row76/counter0;225 increments counter1,
226 still fine7/row76;227 prepares pendingfine0/row75/finish1 while physicalfine
remains7;228 publishesfine0 and completes finish. Matrix and pixels pass
throughout. This is measured hold-and-retry behaviour in the unchanged engine.

All1600 baseline captured frames had PLAYER_STATE=0. Real menu-to-game start
was exercised by the collector, but death/respawn, game-over/menu return and
multiple complete80-row stage wraps are **not** validated in this session.
Physical19656 cadence must not be confused with guaranteed main-loop presentation
on every physical frame; stress can skip presentations.

## Memory / charset assessment (no allocations made)

Fresh assembler guard checks pass. Current resident map:
080e..1e1c,1f00..1f4a,2000..23f6,2400..290e,2920..2b50,
3000..33ff health sprite pool,4000..59fb copies/stage/HUD data.
Screen0400; charset3800..3fff. Do not grow resident code across1f00.

Current stage's literal glyph codes are32,35,42,224,225; stars use240..251.
Committed phase-patch diagnostic uses128..159. Removing it would free that
range. A static score proof needs ten distinct glyphs (space,S,C,O,R,E,0,1,2,5),
so128..137 at3c00..3c4f is a plausible80-byte replacement allocation within
that already-owned range. Stock sources can be copied from the standard
charset set up by `setupStarfieldCharset`; no final font design is needed.
No production reservation or copy routine was added. A future implementation
must guard stage-code exclusion and check menu/init lifetime explicitly.

An offline HUD check on the48 geometry/DMA screenshots compares all320*8
pixels against stock glyph bytes from the fresh baseline charset dump:
122,880 checks, zero mismatches. No sprite-exclusion mask was used. These
sprites were blank, so this establishes stock text stability under DMA,
**not** visibility gating for real sprite pixels. The real solid-sprite
D015 probe establishes why that separate requirement remains unsolved.

Private sprite clipping buffers remain only a possible ownership solution.
Do not use the earlier rough '8 cycles/byte' copy estimate: dynamically selected
source/destination loops cost more, and concurrent BUILD/LIVE ownership must
be accounted for. No extra sprite RAM, hardware slot, logical slot, matrix,
charset or raster handler was allocated by this investigation.

## Stop / handoff decision

**Production architecture is not yet selected. Phases2–4 have not been performed.**
The16-line geometry is the strongest remaining candidate, but its simple
handler failed stress, D015 does not implement the required visibility clip,
and an unchanged gameplay handler can span the whole boundary window. It
would be unsafe to present the isolated screenshot as a production proof.
The protected scroller and multiplexer are left untouched.

This is not a proof that a compliant shared-event implementation is impossible.
The next session should continue from these measured blockers, not re-run the
initial feasibility study or implement the plaque overlay:

1. Choose a complete sprite visibility model for legal straddlers. If proposing
   pre-start culling, explicitly account for the lost tails/player movement;
   do not call it clipping. If proposing blank-pointer or clipped-bitmap
   ownership, bound all8 hardware sprites and BUILD/LIVE buffer/copy costs.
2. Derive a bounded shared-event dispatcher that services fixed display writes
   despite early24/37/55 batches, late243 batches and CIA/KERNAL latency.
   Include physical-frame reset on skipped main presentations and overdue
   compare handling. Stop if this requires a wholesale multiplexer rewrite.
3. Improve the isolated geometry probe only after that cycle model exists:
   precompute fine writes early enough for all-phase badlines; stabilize mask
   removal for every active DMA pattern and sprite start across the boundary.
   A few extra NOPs fixing zero-sprite screenshots is not an acceptable proof.
4. If the complete model is clean, implement the minimal16-line structural
   proof with the derived row1..23 copies/deadline160 and remove the old patch.
   Re-derive latest-safe prepare threshold from actual new execution cost.
5. Then run the user's entire acceptance suite, including long full stage wraps,
   dedicated physical top/bottom/HUD-boundary pixels, real sprite occlusion,
   overdue/early/late batches, deferral, lifecycle and human VICE observation.

Sources of reproducible probes are preserved in `tools/fixed_hud_probe/`, with
commands and limitations in its README. Original raw screenshots/RAM/traces and
JSON remain ignored under `build/fixed-hud-codex/`; do not delete that directory
before continuation. All task-owned VICE instances6530..6538 have been closed.
No user VICE process was touched.

Final fresh engine build still has SHA-256:
`5e46c07eb3469cc1fd11c45ade795158611e3082c4f9e13730c5325e27eacb7c`.
Main HEAD remains1145f65, tracking origin/main. No commits or pushes. No changes
to `src/`, existing tests, stage data, build configuration or protected code.
Only this worklog and the isolated probe directory are untracked additions.

Exact added files (all uncommitted):
- `docs/fixed-hud-codex-worklog.md`
- `tools/fixed_hud_probe/README.md`
- `tools/fixed_hud_probe/gating.asm`
- `tools/fixed_hud_probe/geometry.asm`
- `tools/fixed_hud_probe/capture-gating.py`
- `tools/fixed_hud_probe/capture-geometry.py`
- `tools/fixed_hud_probe/capture-geometry-dma.py`
- `tools/fixed_hud_probe/measure-schedule.py`
- `tools/fixed_hud_probe/analyse-baseline.py`

The preserved Python controllers were syntax checked. The assembly probe
bodies were assembled and executed as described above; their simple code is
experimental and intentionally records a failing approach. `git diff --check`
passes for tracked changes (there are none); new files were also inspected.

## Resumption — explicit Phase A/B/C task (2026-09-06)

HEAD is now ae452a9, one local commit ahead of origin/main. That user commit
adds root AGENTS.md only; engine source and baseline PRG are unchanged. Root
instructions read in full. src/AGENTS.md is open in the IDE but absent on disk.
The prior worklog/probes are preserved. Phase1 is not being repeated.

Phase A implementation model, before edits:
- Keep sorted objects, BUILD/LIVE plans and slot-selection algorithm.
- Replace the unsafe compare tail with one event dispatcher: frame-zero,
  sprite batch, reserved unconditional display hook (initially no VIC change).
- Requested batch compare is its release/service target, not proof the CPU
  finishes before every sprite start. An overdue target is serviced now;
  close future targets are waited for inside the handler without early slot
  reuse. Only compares with a conservative programming margin are armed.
- Explicit next-frame event0 is the sole intentional wrap; it audits/reset
  diagnostics each physical frame. If the main thread is waiting to present,
  it lets that thread install the new LIVE snapshot. Otherwise it replays
  the current LIVE snapshot/batches, preserving main scratch during replay.
- A dedicated game-frame wait publishes this handoff while IRQs are masked
  around the high-raster observation, so an interrupt cannot turn a next-frame
  wait into an ambiguous already-passed presentation boundary.
- Precompute each batch's final X-high/player hardware masks in BUILD. The
  IRQ consumes those LIVE fields, keeping the existing assignment operations
  but removing repeated ownership/mask calculations from its inner loop.
- VIC events use the short KERNAL exit. CIA IRQs still take the normal KERNAL
  path; lateness is handled by dispatch rather than hidden by a stale compare.
- Record per-frame expected/serviced assignments and incomplete-frame counts;
  trace actual assignment execution for an independent physical-frame oracle.

This is a proposed bounded change, not yet validated. No HUD register changes
or viewport changes belong in the first scheduler test build. New code/data
will live at6000+ with an explicit guard, avoiding existing resident/matrix/
charset/sprite allocations. Build and measure before proceeding to B or C.

### Phase A first implementation/test build

Production edits are now present, uncommitted: `src/raster_scheduler.asm`
($6000..$62ad, guarded below8000), small main-loop/builder hooks in main.asm,
and assignment capture/check diagnostics. The old slot-selection/build grouping
is intact. The IRQ loop installs the same pointer/colour/X/Y payloads, with final
X-high/player masks prepared per batch in BUILD. Frame-zero replays initial LIVE
sprites only when main has not announced a presentation; it saves all five
main-thread scratch bytes used by the reused initial renderer. VIC IRQs use EA81;
CIA IRQs continue through EA31. Display event58 is currently a no-op.

Normal fresh600-frame assignment audit passed: all service counts, pointer
end states and physical assignment traces match, reset epoch advances once per
physical frame, no sprite-Y start deadlines missed. Only6 recycled assignments
occurred at this normal load; this is not a stress proof. Terrain checker still
running. Fresh1200-frame stress capture started at port6541. Do not proceed to
viewport/HUD until these and explicit early/late/replay cases are assessed.

### Direct cause and refined scheduler results

The old-binary D012 watch now proves the missing instruction-level detail:
on a valid batch146/150/... plan, old IRQ starts146:43 and writes compare150
at raster152:29. It next writes154 at156:30 in the following physical frame.
Evidence: `build/raster-scheduler/old-compare/{monitor,timing}.log`; baseline
PRG/symbols are saved under `build/raster-scheduler/baseline.{prg,vs}`.

First scheduler build: normal600 terrain check passed; stress1200 reached16
objects/5 batches,7637 assignments,365 catchups,564 replay frames. All service,
final-pointer and physical trace checks passed, with no sprite-start misses.
Terrain/matrix check passed (26 coarse transitions, deferred2,19656 only).
An explicit8-batch case with compares4 lines apart exposed start misses despite
all assignments being serviced in-frame. This is exactly why both diagnostics
are retained; counting completed batches alone is insufficient.

Refinement: remove redundant temporary batch masks and shorten the no-hit
collision path, keeping the original software hit tests on a latched hit.
Cache the selected LIVE batch offset and shorten event selection. The same
close4 case now passes96 assignments over12 frames, all8 batches/11 replay
frames,84 catchups, zero start misses. New code/data ends62a7 (unchanged protected
allocations). No viewport or HUD display-state edits yet.

Fresh6200-frame normal run and64-frame repetitions of all explicit scheduler
cases are running for v2. Next: finish these checks, inspect sprite-start timing
and CIA variation, then complete the viewport measurements before any HUD code.

### Phase A v2 regression / Phase B measured consequences

V2 passed64-frame runs of early24/player37/overlap55/late243/close4 plus0/1/8
objects. The close4 fixture reaches8 batches (more than the usual6),512
assignments,448 catchups,63 replay frames, with no missed sprite starts.
Fresh6200-frame normal run passed both oracles:258 coarse transitions (>3 full
80-row stage circuits),365,269,691 terrain pixels, zero failures,19656 cadence.
Fresh1600-frame stress v2 assignment audit passed9974 assignments,517 catchups,
763 replays,16 objects/5 natural batches, including hardware X-high/player mask
checks. Its terrain checker is finishing. VICE's own log may contain raw PETSCII
bytes from memory display; the trace parser now replaces undecodable characters,
while matching only ASCII event lines. Compare-store auditing is also added:
only explicitly next-frame0 may be behind the beam; sprite/display compares may not.

Phase B: actual unchanged spawn/path routines were run in NMOS VICE for every
member of all12 curated attacks. `tools/vice_viewport_paths.py` logs512 logical
update ticks/member at8000..87ff from a disposable caller7000; IRQs are disabled
for this **logic** measurement, so these are not physical-frame timing claims.
Results: `build/raster-scheduler/viewport-paths/results.json` and per-member logs.

With proposed eligibility71<=VIC Y<=245:
- Top-entry attacks0..4 and9 spawn atY38, become eligible after16 update ticks.
- Side entries5/6/10/11 start58,65,72,79,86[,93]; first eligibility at13,6,0,0,0[,0].
- Side entries7/8 start58,67,76,85,94; first eligibility at13,4,0,0,0.
- Every measured member eventually becomes eligible. Formation timing/spacing
  and object allocation can stay unchanged; the viewport changes presentation,
  not logical lifetime. Absolute formation appearance adds each member's normal
  spawn interval to its relative tick count; do not reschedule the formations.
- Existing enemy fire eligibility starts atY64. Measured members spend3..14
  ticks (including later upward passages) in64..70. A coherent viewport rule
  should also prevent a culled source from firing there. Bullets start at
  enemyY+12, travel+3/tick and are removed at250; changing the firing lower bound
  to the render lower bound is a local consistency change, not a general retune.
- Player starts/respawns220; current upper bound49 would allow an invisible
  player under the new rule. It must move to the chosen render minimum. Keep
  existing lower bound230 for now; its existing border clipping is separate.

Geometric minimum sprite Y is70 for a first body scanline at71 (VIC body starts
one line after its Y compare). A production minimum of71 would leave raster71
terrain-only, and guarantee no sprite DMA before71:55. That one-line guard
removes sprite DMA from the entire proposed D011 transition write window; it
must be stated explicitly, not mislabelled as sprite clipping. No viewport
source changes have been made yet. Next: finish A lifecycle/overdue checks,
then prove this rule and its boundary pixels before C.

### All-phase edge case / current v3

The first all-phase sweep found one sprite-start miss in close4 (phase1,
last assignment Y164 written165:40). Service counts still passed. Therefore
v2 is retained as `phase-a-v2.{prg,vs}`, **not** called the final scheduler.
V3 maintains a buffered batch cursor/end instead of recalculating LIVE+index
on every catchup; net saving about10 CPU cycles per batch without new zero-page
allocation or changes to assignment grouping. Current code/data ends62b3.
The exact failing fixture is being rerun for128 frames across all phases.

Lifecycle test now passes through explosion, respawn, second death, game over,
menu, and a restarted game with the raster vector/enable actually rearmed.
`tools/vice_raster_lifecycle.py` injects PLAYER_HIT because production's current
DEBUG_PLAYER_INVULNERABLE=1 suppresses real lethal hits; it uses the real state
machine and timers. It does not claim collision-detection acceptance from
injected hits. All protected identity/allocation rules remain unchanged.

### Phase A v3 accepted prerequisite / next Phase B

Fresh v3 normal600: all8 phases,24 coarse transitions,35,350,384 terrain
pixels and149,786 old diagnostic HUD pixels; zero failures,19656 cadence.
Fresh v3 stress1600:16 logical objects/6 natural batches,10,879 recycled LIVE
assignments,443 catchups,780 replay frames,7459 compare stores audited;
zero service/start/pointer/player-mask/X-high failures. Terrain checker:
33 coarse transitions, deferred10,91,488,021 terrain pixels,388,019 old HUD
pixels, zero failures and19656 cadence. This exercises hold/retry safety.
All8 synthetic cases repeated64 frames across all8 phases passed v3, including
24/37/55/243 compares and8 batches spaced4 lines apart. Separate close4 run:
128 frames/1024 assignments/896 catchups/127 replays, all phases, zero misses.
Current PRG/symbols saved as build/raster-scheduler/phase-a-v3.{prg,vs}.
SHA-256: e67604e9312f2d1d6dcc3331a11324e6908a1cee674c870ccb98c05f0db7919b.

Deadline model: desired batch raster is release time, not permission to reuse
hardware earlier. Dispatcher waits for a near release, immediately services
an overdue release, and only installs a nonzero compare at least4 lines ahead.
The actual sprite-start deadline is additionally checked against Y:55; catchup
cannot retroactively repair a missed sprite start. Frame0 is the explicit epoch
wrap, restores initial LIVE on skipped presentations, and audits completion.
Display58 is an unconditional no-op event pending Phase C. No source D011
geometry/coarse-body changes yet. These checks audit recycled assignments;
initial-snapshot trace/deadline coverage will be added with the viewport proof
(the old Y0 fixtures cannot have their initial snapshot ready before0:55).

Phase B implementation decision: eligibility71<=OBJECT_Y<=245, player upper
bound71, and suppress enemy shots/hitscan/collision eligibility outside the
viewport. Logical updates/lifetime/formation tables/allocation remain unchanged.
This avoids invisible combat sources/targets as well as HUD overlap. Y71's
first body pixels are72; raster71 is deliberately terrain-only. No D015 clipping.

### Phase C working timing derivation — NOT IMPLEMENTED / NOT PROVEN

Preserve this reasoning for continuation; do not copy the old polling/NOP probe.
With viewport minimum71 there is no sprite DMA until71:55. Proposed event56,
normal HUD D011=$17, HUD badline55/text55..62. Change tofine1 only AFTER57
(e.g59) to suppress unwanted63 badline. At63 mask graphics using documented
invalid ECM+BMM mode ($70|f), DEN1/RSEL0/D018unchanged; forf7 use$71 until64,
then$77. Terrain row1 firstbadline64+f. Restore $10|f in horizontal gap after
raster70's visible pixels but before71's. Need derive/measure instruction-phase
bounds under all entry alignments, not just run a geometric probe once.
Potential bounded tail: preload normalA, poll70 with LDX D012/CPX#70/BCC;
nonbadline70 use a derived45 CPU-cycle delay (JSR/LDY#6/DEY-BNE/RTS=43 +2);
f6 has a70badline and requires a separate short path forcing any early arrival
through its RDY stall. Formal earliest/latest store bounds remain to prove.

CIA1 timerA IRQ may need suspension during gameplay to bound HUD entry latency;
change interrupt mask bit0 only, keep timer running (random seed reads depend
on it), restore bit0 and KERNAL vector on teardown. Verify dependencies/lifecycle.
IRQ display fine must be a presented shadow, never SCROLL_FINE pending coarse0.
Frame0 owns D011=$17 each physical frame; display handler owns transition/fine;
applyFineScroll publishes only shadow. No D018 switch or border opening.

Coarse derivation: fixedrow0, terrainrows1..23; upperold1..11->2..12 (3520CPU),
crossingold12->13 unchanged; lowerold13..22->14..23 (3200CPU). Fine7 row12fetch159
means prepare>=160; nextfine0 row13fetch160 is finish deadline. Incomingdest1,
logicalsource=(SCROLL_ROW+BG_DEST_ROW-1)mod80. Row24 unused/blank. Re-derive latest
prepare threshold and measure both halves with new event before acceptance.
Potential charset slots128..137 at3c00..3c4f, copied stock source codes
[32,19,3,15,18,5,48,49,50,53]; remove rejected old128..159 patch glyphs/calls.
Static row0 white text SCORE 012500 atcols2..13, black/privateblank elsewhere.
No terrain cells repurposed as overlay. Full new HUD/matrix/boundary oracle
still required; old diagnostic checker cannot establish fixed-region acceptance.

### Phase B prerequisite accepted / Phase C implementation entry

Production viewport filter added before SORTED collection (logical objects
remain allocated/updated), player upper bound71, enemy firing lower bound71,
and off-screen hitscan/collision exclusion. Formation/path/lifetime/bullet
velocity tables untouched. Initial snapshot trace added, with physical-frame
and sprite-start checks alongside recycled assignments.

Fresh viewport_edges32 and viewport_top_dma64 captures pass both assignment
and independent solid-sprite pixel checks in all8 phases:1,904,640+3,870,720
physical pixels checked. No pixels above72; Y245 has exactly its last visible
line246. Top-DMA fixture retains16 logical objects and renders all16 across
initial8 and later8, with512 initial and512 recycled writes traced. Fixturev1
incorrectly used multicolour11 (shared grey), caught by the white-pixel test;
v2 uses pair10/$aa for per-sprite white, no engine correction needed.
Real held-UP360-frame test reaches71 after148 captured frames and holds it;
logical0 remains active TYPE_PLAYER. Saved phase-b-v1.{prg,vs} before C.

Refined HUD tail derivation: LDX D012/CPX immediate/BCC has9-cycle polling
period. First successful raster read is0..8 cycles into target; exit is5..13.
A48-cycle subroutine delay (JSR,LDY#7,7xDEY/BNE,RTS) puts STA entry53..61,
write56..64: entirely after visible pixels, before next line's display/fetch.
Use this at end62 to mask63 cleanly and at end70 to restore71, with A preloaded.
No NOP padding or copied geometry probe. Fine6 has a70badline; a separate6-cycle
read delay forces early arrivals through BA/RDY and keeps late arrivals before
71's visible pixels. These bounds must now be checked by actual store traces
and the all-phase physical oracle, including maximum first-sprite DMA at71.

The only gameplay SEI regions are short near-frame0 publication; charset ROM
banking runs in initial setup only. CIA timerA IRQ is the remaining unbounded
HUD-entry interference. C will mask bit0 during gameplay and restore it at
teardown; timer keeps running, preserving random-seed inputs. No sound or
keyboard gameplay dependency found. Menus retain KERNAL service.

### Phase C structural v1 / measured fine6 correction

C now exists uncommitted: display event56 owns fixed/mask/playfield D011;
frame0 restores17, applyFineScroll publishes a separate presented fine byte;
CIA1 timerA interrupt bit0 is masked in gameplay and restored on teardown.
Old patch calls/routines/glyphdata removed. Fixed stock SCORE 012500 uses
row0/codes128..137, row24blank. Terrainrows1..23; upper440bytes/lower400bytes;
prepare>=160 (latest200 unchanged pending stress evidence), physical crossing
buffer unchanged. D018 unchanged. New memory ends632b; protected slots unchanged.

First normal600: sprite assignments/initial snapshots/pointers/cadence passed.
Independent fixed-HUD oracle found49 failures (pixel/edge records), all underlying
pixel defects in phase6. Matrix, HUD and separator remained correct. Traces:
mask write62:57 could pass,62:58..61 could fail. Reason: installingfine6 on62,
even at its end, can assert a late badline and disturb row-counter/fetch state.
Corrected architecture uses$71 for masking at end62 in EVERY phase; installs
$70|fine on63 forfine0..6, on64 forfine7. This avoids both latebadline62 and
accidentalbadline63. Fresh normal/stress v2 captures are next; do not acceptv1.
New tools/check_fixed_hud_capture.py checks fixed stock glyph copies, matrix,
incoming/crossing buffers, every unmasked HUD/separator pixel, full terrain,
and captured-to-captured one-pixel motion at72..78 and240..246. It found the
real defect independently of the screen-RAM oracle.

### Phase C v2 acceptance runs / newly exposed coarse deadline blocker

C v2 full oracles passed: normal600 (24 transitions), long6200 (258 transitions,
3.225 stage circuits,366,949,563 pixel checks/31,738,880 unmasked HUD+separator/
9,028,174 actual edge-motion checks), stress1600 (16 objects/5 batches,40
transitions,deferred49), and sustained dense1200 (16 objects/8 batches,45
transitions,9592 recycled assignments,8393 catchups,116 replay frames).
Every run has19656 physical cadence and zero pixel/matrix/assignment errors.
Dense legal stationary egress-coast objects exercise the real main/scroller,
not parked main. Eight all-phase synthetic cases128 frames each also pass;
four solid viewport cases check31,211,520 pixels, including early95/late233.
Lifecycle passes actual respawn/game-over/menu/restart:0 KERNAL jiffy changes
in gameplay and185 outside it, so CIA interrupt suspension/restoration works.

Measured display-hook entry57:18..28, restoration70:57..71:3, elapsed853..866
wall cycles to restore (plus return/dispatcher/IRQ prologue/epilogue). Poll/delay
branches now have assembler page-cross guards; those guards/labels add no bytes.
Normal/stress/dense/long timing-summary.json files record copy windows. Natural
stress upper body ends as late301:23; lower complete by114:40, before160.

IMPORTANT: acceptance is NOT complete. A new forced late-copy diagnostic calls
real prepare with8 sprites at199 and8 at235 (batch223), main parked. Entry198:2
is accepted by the inherited cutoff200 but returns next physical frame27:39!
The8920 wall cycles include frame0 replay after the copy already missed its
publication boundary. Entry199 happens to defer because its initial badline
moves the cutoff sample into200. This is a real unsafe path, despite all natural
oracles passing; do not approve the current build until corrected.

Likely small correction: admit coarse preparation only once all LIVE sprite
batches have finished, and use a conservative earlier cutoff derived from the
remaining pure-copy+VIC DMA budget. With no remaining batches, no variable IRQ
body/collision scan can interrupt the copy before frame0. Existing physical
crossing/copy bodies remain intact. Need measure pure CPU cost, bound at most8
remaining sprite DMA streams and remaining badlines, choose cutoff with margin,
then rerun the forced case for safe deferral and final acceptance runs.
Current next step: finish this deadline proof; do not stop with v2 marked safe.

### Bounded coarse-admission correction (C v3)

Pure NMOS CPU benchmark (DEN/sprites/IRQs off, all80 actual stage origins):
prepare including callerJSR takes5848..5867 cycles before the new guard.
The new10-cycle cursor/end check keeps this below6000 CPU cycles.
Coarse prepare now requires all LIVE batches completed and raster<184.
This prevents variable IRQ payload/collision scans during the copy; next event
is explicitly frame0, because display56 already finished before160.

Bound: after the final batch, at most8 current/future sprite DMA streams remain
(one per physical slot, no further reassignments). Conservatively budget22
lines*6 CPU-denial cycles*8=1056 (actual unexpanded sprite data needs21 lines,
2 CPU bus cycles plus BA lead; this deliberately overcounts). Budget10 remaining
badlines*43=430 (at cutoff there are actually9 from183..247). Total with6000
CPU =7486 cycles. From184 to312 there are8064 cycles, giving578 cycles margin
even after rounding the raster sample up to184. The physical crossing/copy
bodies and stage representation are unchanged. If a late batch remains or
admission is late, preserve fine7 and retry with no matrix writes.
This may pause terrain under sustained late16-object plans; gameplay sprite
service is preserved. Dense8-batch plans completing near160 can still scroll.

Evidence: pre-correction forced198 entry crossed frame0; forced180 returned303:9.
New tests must show these pending-batch cases defer, and no-pending but residual
full/sparse DMA cases admitted at183 finish before0. Rerun normal,long,stress,
dense and both oracles after this guard change; earlier v2 passes alone are
insufficient for final acceptance.

## Resumption — progressive top-edge sprite clipping (Claude, 2026-09-06)

### Task
Human accepted the fixed HUD visually. Only defect: sprites POP in/out at the top
gameplay boundary (raster ~72) instead of emerging pixel-by-pixel.

Implement progressive top clipping. Do NOT touch the HUD raster scheduler, the
scroller, the viewport `71` semantics for combat, or BUILD/LIVE. Three states:
(1) fully above -> active but not rendered; (2) partial -> rendered at TRUE VIC Y
with a top-clipped bitmap; (3) fully inside -> original pointer. No move-down, no
D015 clip, no bitmap generation in the IRQ. BUILD-time gen into a fixed private
clipped-sprite pool; pointer stored in the plan before LIVE.

### Confirmed root cause (verified in source)
`buildSortedObjectList` (main.asm ~2364) drops every object with
`OBJECT_Y < GAMEPLAY_SPRITE_MIN_Y (71)` from SORTED entirely, so no plan entry,
no sprite. Eligibility is whole-sprite -> instant appearance at Y=71.

### Verified architecture facts for this change
- Sprite geometry (Codex's own `check_viewport_capture.py` contract, passes on
  HEAD): OBJECT_Y is written straight to $D001; body occupies raster
  `OBJECT_Y+1 .. OBJECT_Y+21` (21 rows, 3 bytes/row, 63-byte bitmap). Sprites are
  unexpanded (no $D017/$D01D writes); multicolour ($D01C=$ff) - irrelevant to
  whole-row blanking.
- Clip depth (bitmap rows blanked from the top) `d = max(0, 72 - (Y+1)) = 71 - Y`.
  Straddler band: Y in [51,70] -> d in [1,20]. Y<=50 -> d>=21 -> cull. Y>=71 -> d=0.
- Plan: `INITIAL_SPRITE[LIVE+hwslot]` (renderSprites) and `ASSIGN_SPRITE` (IRQ
  `applyLiveRasterBatch`) are the only sprite-pointer sources written to
  `$07F8+hwslot`. `INITIAL_Y`/`ASSIGN_Y` -> `$D001` unchanged (true Y).
- Initial snapshot: sorted position x -> hw slot x directly (renderSprites loop).
- **Batches never carry straddlers.** A batch reuses hw slot S only when
  `SLOT_FREE_RASTER[S] = OBJECT_Y[initial S] + 24 <= OBJECT_Y[batch obj] - 12`.
  With the new SORTED floor 51, an initial straddler frees its slot at >=75,
  while any batch-straddler deadline is <=58 -> no slot -> `!cannotSchedule`
  skips it. So clipping is needed **only in `buildInitialSpriteSnapshot`**,
  keyed by hw slot 0..7. `buildBatchSpriteSchedule`/`applyLiveRasterBatch`/
  `multiplexIRQ` need no change.
- Memory: `$3400-$37FF` (1024 B) is unallocated in VIC bank 0 (map:
  health pool $3000-$33FF, charset $3800). Use it for a double-buffered clip
  pool: 2 plan halves x 8 hw slots x 64 B. Pointer base `$3400/64 = $D0`;
  pool-slot pointer = `$D0 + plan_base(0/8) + hwslot`. Double-buffering by plan
  makes BUILD writes race-free vs LIVE display and vs `rasterFrameReset` replay.
- Shadow state (avoid full 63-byte copy every frame): per plan slot (16)
  `CLIP_SHADOW_PTR` + `CLIP_SHADOW_D`. Same-art slots only diff the changed mask
  rows. New/changed slots do a full copy+mask. Unused/non-straddler slots get
  `CLIP_SHADOW_PTR=0` so they force a rebuild when reused.

### Decisions
- New const `GAMEPLAY_SPRITE_CLIP_MIN_Y = 51`; only the `buildSortedObjectList`
  floor moves from 71 to 51. Player clamp, enemy-fire, hitscan and software
  collision stay gated at 71 (combat semantics preserved; a half-visible enemy
  is drawn but not yet a combat participant - matches "viewport changes
  presentation, not logical lifetime").
- Clip pool double-buffered, 1024 B at $3400 (guarded `< $3800`).
- Shadow (32 B) appended to the raster scheduler state block (stays < 128 for
  its clear loop).
- Overflow: at most 8 straddlers get clipping (8 initial slots). A theoretical
  9th+ simultaneous straddler (needs >=9 enemies inside a 20px Y band, extras
  in batches) is culled as today - no HUD contamination, degrades to old pop.

### Status: implementing. Files to touch:
- src/main.asm: `GAMEPLAY_SPRITE_CLIP_MIN_Y`; `buildSortedObjectList` floor;
  `buildInitialSpriteSnapshot` clip hook + `buildClippedInitialSprite`;
  `$3400` pool block + guard; shadow init in startGame.
- src/raster_scheduler.asm: 32 B shadow state.
- tools/check_viewport_capture.py: expect straddlers in plan; clip white-pixel
  rectangles to `max(y+1,72)..y+21`.
- New: tools/vice_clip_cases.py or reuse vice_raster_cases viewport_* + a
  dedicated depth/entry test.

### Next step
Implement main.asm clip pool + hook, build, then a fresh single-straddler
capture to prove d = 71 - Y against raster pixels before scaling to 8.

### Progressive top-clip — implementation complete, one stress interaction found

**Implementation (uncommitted):**
- `buildSortedObjectList` floor 71 -> `GAMEPLAY_SPRITE_CLIP_MIN_Y` (51). Combat
  gates (player clamp, enemy fire, hitscan, software collision) stay at 71.
- `snapshotSpritePointer` / `buildClippedInitialSprite` (new, main.asm): for a
  straddler (Y 51..70) copies OBJECT_SPRITE's 63 bytes into
  `CLIP_SPRITE_POOL[BUILD_PLAN + hw slot]` and zeros the top (71-Y)*3 bytes,
  then stores pointer `$d0 + plan + slot` in `INITIAL_SPRITE`. True VIC Y
  unchanged. Batches provably never carry straddlers (a straddler frees its slot
  at >=75; any batch-straddler deadline is <=58), so only the initial snapshot
  needs the hook - `buildBatchSpriteSchedule`, `applyLiveRasterBatch`,
  `multiplexIRQ`, `renderSprites` are untouched.
- Pool: 1024 B at $3400-$37FF (VIC bank0, free per memory map), double-buffered
  by plan half so BUILD writes never race the LIVE bitmap the VIC / IRQ replay
  fetches.
- Cost control: per plan-slot shadow (`CLIP_SHADOW_PTR/_D`); an unchanged
  straddler with immutable formation art (ptr <$c0) skips the copy entirely;
  a moved straddler only rewrites the changed mask rows; only a genuinely new
  bitmap does the full 63-byte copy. `CLIP_FULL_REBUILD_BUDGET` (=8) bounds
  full rebuilds per BUILD (inert at 8 for the 8-slot engine; a knob).
- State added to raster_scheduler.asm block: 4 scratch + 32 shadow bytes
  (block still < 128 for its clear loop; zeroed by initRasterScheduler).

**Geometry proven:** VIC body = OBJECT_Y+1 .. +21; clip depth d = 71-Y;
straddler Y 51..70 -> visible rows 1..20 starting at raster 72, nothing above.
`tools/vice_clip_sweep.py`: Y swept 48<->74 in the live game loop, solid /
player / enemyA art, 54 frames each, byte-exact pool check + pixel check =
0 failures. Smooth 1px entry and 1px upward exit; clean clipped->original
handover at Y=71.

**Regression results (fresh VICE):**
- Normal 1500 frames, 457 with a live clipped straddler, 62 coarse transitions:
  check_fixed_hud_capture 0 failures (89M px), check_raster_capture 0 service /
  0 sprite-start misses, 19656 cadence, 0 replays.
- Parked scheduler cases early24/player37/overlap55/late243/close4/zero/one/
  eight/viewport_* + new clip_eight/clip_boundary, all 8 phases:
  0 service / 0 sprite-start misses; viewport pixel oracle 0 (incl. 8
  simultaneous straddlers in clip_eight).
- Lifecycle (death/respawn/game-over/menu/restart): 0 failures; CIA jiffy
  suspend/restore intact.

**Open stress interaction (NOT resolved, needs human judgement):**
Under `--stress` (accelerated spawner; baseline already saturates deferred=255)
check_fixed_hud_capture reports ~20-85 `physical pixels` failures / 500-1200
frames, 100% on frames with a straddler live, **all at raster 71..73**, <=19
mismatched pixels, 1-frame transient, clustered in the opening spawn wave.
NO matrix / incoming / crossing / late-display / cadence / service failures;
2/6757 `rasterBatchMasksApplied` deadline flags at frames 488-489.
The pixels are **terrain**, not sprite (a lag-tolerant sprite mask changed
nothing). Cause: straddler sprite DMA in raster ~50..71 perturbs the fixed-HUD
raster hook's cycle-timed $D011 writes - Phase C explicitly assumed "no sprite
DMA before 71:55". The protected hook cannot be modified, and the task
requires straddlers at true VIC Y (which necessarily puts DMA there). Options:
(a) accept the transient top-edge flicker under synthetic overload; (b) keep
straddler rendering out of the hook's DMA window (reduces but does not remove
the entry pop). Left for human VICE acceptance.

**Files:** src/main.asm, src/raster_scheduler.asm, tools/check_viewport_capture.py,
tools/vice_raster_cases.py (+clip_eight/clip_boundary), tools/vice_clip_sweep.py (new).
