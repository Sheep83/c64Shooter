# Astra C64 engine architecture review

Analysis and recommendation only · PAL C64 · 8 September 2026

## 1. Executive verdict

**Primary recommendation: Option 3 — optimise both incrementally, retaining BUILD/LIVE initially.** Recover avoidable CPU time in the current renderer/planner and move incoming-row preparation out of the coarse-scroll window. Then prove a bounded way for coarse copying to coexist with outstanding LIVE sprite work. Do not replace the multiplexer with JIT as the first intervention.

There are **two distinct causes of pressure**, and treating them as one publication problem leads to the wrong redesign:

1. **A structural scheduling conflict:** `prepareBackgroundCoarse` refuses to start while any LIVE batch remains outstanding. A perfectly serviceable nine-object sprite layout can therefore stop scrolling indefinitely. Faster sorting, faster publication, or a JIT implementation retaining that rule cannot solve it.
2. **Variable CPU work before narrow deadlines:** player collision confirmation, plan construction, clipping, projectile-suppression rebuilds, and coarse copying consume different windows. Fresh measurements identify the player collision scan as the cause of a reproduced approximately 14-line early-frame slip. That delay can then make publication encounter DISPLAY synchronously and produce additional latency.

The supplied handoff correctly identifies combined-load pressure, but several of its causal interpretations are not supported by the source. Publication is a **29-cycle plan-index exchange**, followed by hardware setup and scheduler arming—not a bulk BUILD-to-LIVE copy. BUILD usually happens in the preceding physical frame. `RENDER_COUNT = 8` does not mean eight objects in total. The approximately raster-30 versus raster-60 `finishBackgroundCoarse` comparison can describe a **seven-cycle no-op**, not a coarse copy. Actual lower copying takes thousands of cycles.

The new controlled nine-object run is decisive: eight enemies at Y=199, player at Y=235, one LIVE batch at raster 223. The batch continues to execute, the HUD/border scheduler remains complete, but scrolling holds fine 7 for **143 consecutive attempted advances**. Later attempts reach coarse preparation at approximately raster 163—early enough for the existing time cutoff—and still defer because the batch is pending. This is an interaction limit, not a five- or six-enemy hardware limit.

A second screen is a credible **fallback scroller architecture**, without replacing BUILD/LIVE. The current memory layout can plausibly accommodate it by moving 1,881 bytes of CPU-only tables/code out of VIC bank 0. However, neither a page flip nor blank outer character rows automatically preserves the clean 55..246 aperture and eliminates its exposed edges. That part needs a separate geometry proof.

Expected outcome: the first small changes should recover useful margins; the later scheduling proof must remove the demonstrated batch obstruction before claiming hitch-free combined gameplay. No defensible new maximum enemy count can be promised from this review alone.

## 2. Evidence and source basis

### Baseline identity and scope

The source of record was the supplied ZIP, extracted outside the repository. Every assembly file under its `src/` was compared with the repository's committed HEAD and matched byte for byte.

| Item | Identity |
|---|---|
| ZIP | `c64Shooter-experimental-border-hud.zip` |
| ZIP SHA-256 | `1499014c1c0a01d88f93974eb462be1104c7234d8096c23e30c78a7742b530de` |
| Matching commit | `6a64130220e87eea182f6b638d38da03524a2bc5` |
| Assembler | KickAssembler 5.25 |
| Fresh PRG SHA-256 | `1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd` |
| Emulator | VICE x64sc 3.10, PAL, fresh console-mode instances |

The rebuilt PRG exactly matches the handoff's mask-OFF baseline. The existing workspace's uncommitted masking experiment was inspected only to establish provenance and was left untouched. No repository files, commits, branches, tags, or index entries were changed. This report and all new diagnostics reside outside the repository.

The full 640-line handoff report was read. Instructions embedded in that report were treated as historical context and review questions, not authority to implement its suggested changes. Both commercial annotated files were read in full. They are selected excerpts with reconstructed labels and omitted code—not complete disassemblies from which whole-game performance can be established.

### Evidence labels

- **[S] Source:** directly established from the verified ZIP or its assembled instructions.
- **[M] Measured here:** fresh VICE measurements using the verified binary.
- **[H] Historical:** supplied report/worklog measurements, retaining their original build and test limitations.
- **[D] Derived:** cycle arithmetic, hardware-model reasoning, or a proposed design; not an accepted implementation.

Important baseline source anchors, with line numbers referring to the ZIP:

| Source | Relevant locations |
|---|---|
| `src/main.asm` | Main loop 626–689; collection/sort 2701/2725; initial snapshot 2777; clipping 2830 onward; batch builder 3012; swap 3525; render 3548; arming 3639; collision confirmation 3656 |
| `src/main.asm` | Row rendering 5423; decoder 5500; scroll update 5650; upper preparation 5675; lower finish 5739; suppression 5767 onward; unrolled copies 6217/6230/6243/6251; HUD setup/handoff 6365/6411 |
| `src/raster_scheduler.asm` | `waitForGameFrame`, `publishRasterPlan`, `startLiveRasterPlan`, `rasterFrameReset`, `dispatchRasterEvents`, `borderOpenHook`, `applyLiveRasterBatch`, mask builders |
| `src/background_turrets.asm` | Dead-cell restoration 352; incoming-row overlay 433; frame-top glyph publication 479 |
| Historical investigations | `docs/scroll-hitch-worklog.md`, `docs/scroll-hitch-investigation.md`, `docs/sort-and-free-baseline-worklog.md`; aperture, HUD, and residual-flicker reports |

Hardware cross-checks used Christian Bauer's primary VIC-II analysis: PAL dimensions, badline conditions, matrix addressing and bus arbitration. Its documented PAL timing is 312 lines × 63 clocks; screen bases are 1 KB aligned, character bases 2 KB aligned, and character/sprite accesses contend with CPU execution. These facts underlie the calculations below. [Bauer, VIC-II analysis](https://www.cebix.net/VIC-Article.txt)

VICE was launched directly with `-console`, never through `open -a`, never activated, and controlled through its localhost monitor. Console mode is documented by VICE. [VICE invocation manual](https://vice-emu.sourceforge.io/vice_2.html)

### New experiments and limitations

1. **Isolated CPU routine calls:** display, sprites and IRQs disabled, except controlled hardware-writing routines aligned away from sprite starts. Reported costs include the routine's RTS and exclude the probe's eight-cycle SEI/JSR wrapper. No replacement engine routines were injected.
2. **600-frame authored baseline:** normal game code, scroll origin seeded to 40, passive execution/store traces and end-of-frame state captures. It exercised counts through nine objects, all fine phases, 37 upper coarse preparations and a stage wrap. It reproduced the early-frame delay and four consecutive deferrals.
3. **160-frame controlled late-nine layout:** player Y=235, eight enemies Y=199, stationary path state; spawning and firing held off through emulator data. The initial one-object plan settled into nine objects. The final run recorded 143 consecutive deferrals and no upper coarse copy. An earlier trial admitted extra spawns and was rejected as a nine-object experiment.

Physical frame epochs were calculated from the monitor's absolute clock minus `63 × raster + cycle`. All 599 authored intervals were **19,656**, as were the controlled run's intervals. Raw breakpoint timestamps differ by a few clocks because the CPU stops on instruction boundaries; they must not be mistaken for variable PAL frame lengths. IRQ checkpoint spacing is a separate metric.

These were timing/state experiments, **not a new full pixel/HUD acceptance campaign**. Visual-cleanliness claims remain the supplied evidence. No newly proposed optimisation or redesign was implemented or benchmarked against the baseline.

Reproduction files accompany this report in its directory: `cpu_probe.py`, `cpu-results.json`, `frame_probe.py`, `analyze.py`, and the `authored/` and `late9/` captures. The scripts use only the extracted source/build and temporary emulator state. They are review probes, not proposed production tooling. Commands used, with output confined to the temporary review directory:

```sh
java -jar /Users/brianmorrice/dev/tools/kickassembler/KickAss.jar /private/tmp/astra-c64-review/c64Shooter-experimental-border-hud/src/main.asm -odir /private/tmp/astra-c64-review/build -o /private/tmp/astra-c64-review/build/shooter.prg -vicesymbols
python3 /private/tmp/astra-c64-review/cpu_probe.py
python3 /private/tmp/astra-c64-review/frame_probe.py authored
python3 /private/tmp/astra-c64-review/frame_probe.py late9
python3 /private/tmp/astra-c64-review/analyze.py authored
python3 /private/tmp/astra-c64-review/analyze.py late9
```

The accompanying evidence archive contains the original ZIP, verified PRG/symbols, probe scripts, raw timing/state captures and this report. It can be unpacked at the paths above to reproduce the probe setup. Random encounter choices are not frozen by these particular baseline probes; future optimisation A/B tests require a common emulator snapshot/input tape.

## 3. Current architecture

### Presentation and simulation pipeline

The steady loop is:

```text
Physical frame N begins
  frame IRQ: install previously presented fine state, set up HUD, ready/replay decision
  main: publish turret glyphs/dead-cell restoration
        publish fine state; exchange LIVE/BUILD indices
        write initial gameplay slots 0..3
        arm LIVE scheduler
        finish lower coarse copy, if pending
  main: turret/world updates, movement, combat, spawner
        advance requested scroll phase
        collect + stable Y sort
        build initial snapshots + batched assignments + masks
        optional projectile suppression and second batch build
        try upper coarse preparation
        deferred score refresh; wait for next physical frame
  IRQs throughout: HUD handoff, LIVE sprite batches, BORDER, next FRAME
```

BUILD and LIVE are two eight-entry halves addressed by bases 0 and 8. There are up to eight initial entries and eight additional assignments, with up to eight batch records per plan. The main thread changes BUILD; sprite assignment IRQs consume LIVE. Pointer exchange publishes ownership cheaply. Logical object 0 is permanently the player; hardware slot ownership is transient. [S]

The IRQ does **not** consume BUILD payloads. However, collision confirmation reads the mutable logical object arrays. Therefore “IRQ reads LIVE only” is correct for rendering payloads, not a claim that every datum read by the IRQ is immutable. Any JIT or deferred-collision proposal must account for that existing distinction. [S]

### Display, HUD and scrolling

Bank 0, screen `$0400`, charset `$3800`, `$D018=$1E`, global multicolour character mode. Gameplay base `$D011` is DEN plus fine phase, **RSEL=0**. Several comments still describe earlier RSEL=1 and fixed-character-HUD versions; the actual constants and instructions override those comments. [S]

All 25 matrix rows carry terrain. Row `d` corresponds to world `SCROLL_ROW+d−1`. Row 0 and row 24 are real incoming/outgoing overflow content; they are not spare blank rows. The clean fixed terrain aperture 55..246 is supported by the supplied pixel measurements. It includes phase-dependent fragments of outer matrix rows; it is not simply the 23 complete interior rows. [S,H]

HUD sprites occupy physical slots 4..7 at Y=22. FRAME enables them deterministically. Main writes at most four initial gameplay slots. DISPLAY at compare 46 reclaims 4..7 and installs the remaining LIVE initial entries. No hardware slots are permanently reserved. The handoff completion floor is 56, not merely compare 46. [S]

BORDER is a terminal event after DISPLAY and all sprite batches. It classifies early/in-window/late entry and performs the RSEL dodge around 245 and 250. It is not an independently competing IRQ chain. [S]

Terrain colour RAM is not shifted. It is initially filled uniformly, but turret pulse/death code does update selected cells; the handoff's stronger “written once and never changes” description is only true of ordinary terrain colour ownership. [S]

### The coarse-scroll contract

At requested 7→0:

- Clear the pending request.
- Reject if any **current LIVE** assignment batch remains.
- Reject if raster high is set or current raster is at least 184.
- Wait until raster 160 if necessary.
- Save old row 12; shift rows 0..11 into 1..12.
- Decrement/wrap the world origin; decode/install the fresh row 0.
- Set next fine phase to 0 and mark lower work pending.
- Next presentation: shift old rows 13..23 into 14..24; restore saved row 12 into row 13.

Deferral leaves fine 7 and matrix content intact and retries on the next main-loop iteration. This is an intentional safe presentation hold, visible as a hitch. There is **no SEI around these copies**. Outstanding sprite IRQ work is excluded by policy, but DISPLAY/BORDER IRQs and sprite DMA still matter. [S]

The gate is evaluated before the wait to 160 and is not rechecked afterwards. This both rejects batches that would finish during the wait and leaves a future gate improvement responsible for checking physical epoch and actual post-wait beam position. [S]

## 4. Frame/timing anatomy

### First separate the deadlines

| Deadline/window | What must be true |
|---|---|
| HUD start near Y=22 | HUD pointers, coordinates and enables installed by its DMA checks |
| Main ready at physical frame zero | `RASTER_PRESENT_READY` determines whether FRAME waits for main or replays old LIVE |
| Initial gameplay DMA | Slots 0..3 must be programmed before their actual sprite starts; slots 4..7 must survive HUD handoff |
| DISPLAY compare 46 | Handoff servicing and publication ownership must remain coherent, including synchronous catchup |
| Coarse admission | Current policy requires all LIVE batches done and sampled beam below 184 |
| Upper completion before next presentation | New upper matrix/incoming row and next fine state ready before frame boundary work |
| Lower row-13 fetch | Lower copies and crossing restore complete before the destination is fetched |
| BORDER dodge | Actual writes must precede the relevant close comparisons; compare 240 alone is not sufficient |

The handoff's approximately 200-line “publication margin” is not a generally useful deadline measure. Even with no gameplay batch, initial sprite starts and DISPLAY are early. Reaching `armFirstBatch` at 44 is quite different from merely being ahead of a batch at 223.

**Badline boundary correction [D]:** with this whole-frame fine state, normal matrix row `d` is fetched at `48 + fine + 8d`. Thus old row 12 at fine 7 is fetched at **151**, and new row 13 at fine 0 at **152**. The source comments saying 159 and 160 reflect an older display arrangement. The wait until 160 is conservative for row-12 release; the lower completion deadline must not casually be treated as 160. Verify VIC c-access timing before changing either fence. At a reported lower completion of 134, whole-line margin to 152 is only about 18 lines, not 26.

### A. Healthy scrolling/mux frame

Representative fresh authored coarse pair, physical epoch 1910 for preparation; timings are checkpoint positions, not exact routine boundaries unless specified. [M]

| Beam | Operation | Implication |
|---|---|---|
| N: ~2 | FRAME/HUD setup | Main resumes around 9 |
| N: ~9..18 | Turret publication/scan | Fixed work before renderer |
| N: ~19..27 | Initial sprites and arming | No long collision-confirmation path |
| N: 30 | Lower finish checkpoint | No-op if preceding presentation was not coarse |
| N: ~48..56 | DISPLAY/HUD handoff | Slots 4..7 returned to gameplay |
| N: 81:10 | Collect next objects | Main's simulation work has finished |
| N: 88:05 / 96:06 / 109:37 | Sort / initial snapshot / batch builder | BUILD prepared before admission |
| N: 123:32 | Coarse preparation entered | No outstanding LIVE batch; waits for 160 |
| N: 165:30 | Upper shift begins after crossing save | Copy runs behind fetched upper rows |
| N: 233:40 | Upper shift complete | Incoming row still needs decode/install |
| N: ~243..250 | BORDER hook | Can interrupt row-preparation work |
| N: 286:54 | Upper ready | Approximately 25 lines to physical frame boundary |
| N+1: ~27..31 | Arm and enter lower finish | Fine 0 is presented |
| N+1: ~110..118 under denser sampled conditions | Lower ready | Before row-13 fetch; steals much of early main budget |

A directly captured denser coarse pair, epochs 2006/2007, reached upper-ready at **294:01**, then lower finish ran from **31:20 to 117:20**: 5,418 elapsed clocks including interrupt/DMA/badline time. After that lower copy, collection did not start until 173:18. That frame was not requesting another coarse step; its risk was late BUILD/readiness, not a second immediate coarse admission.

### B. Pressured early-frame path and coarse request

The approximately 14-line slip was reproduced independently of a lower coarse copy. [M]

| Checkpoint | Healthy epoch 2203 | Pressured epoch 2200 | Cause/meaning |
|---|---:|---:|---|
| `renderSprites` entry | 18:57 | 18:62 | Almost identical entry |
| Collision latch passed to confirmation | `$00` | `$C0` | Expensive broad-phase-positive branch |
| First `rasterInitialApplied` | 21:13 | 34:20 | Extra work is before first VIC assignment |
| `armFirstBatch` | 26:50 | 40:16 | Roughly 13.5 lines later |
| Lower finish → lower-ready | 30:38→30:45 | 43:56→44:00 | **Seven elapsed clocks in both: no coarse copy** |

From `capturePlayerCollision` to the first initial assignment: **139 clocks healthy versus 960 pressured**, a difference of **821 clocks = 13.03 PAL lines**. No intervening traced raster service explains it; the source's variable path is collision confirmation. Hardware collision activity can occur without visible damage, and this baseline deliberately suppresses the final player-hit store while still performing the tests.

The following pressured epochs 2201/2202 entered arm at about 40:26 and encountered DISPLAY inside the publication path. DISPLAY completed at 54:03; an early BORDER entry followed at 58:31, and main reached lower finish at 60:56. The guard safely rearmed BORDER. This reproduces the handoff's raster-60 symptom without any lower-copy workload.

The actual authored hitch occurred at capture frames 561..564 (epochs 2422..2425):

| Work in first deferred frame | Beam |
|---|---:|
| Initial publication | 34:52 |
| Collect / sort | 116:40 / 126:53 |
| Initial snapshot / first batch build | 148:55 / 168:36 |
| Projectile-suppression policy | 194:06 |
| Second batch build | 200:12 |
| Coarse preparation / deferral store | 216:28 / 216:57 |
| Outstanding LIVE batch entry / assignment | 224:24 / 225:49 |

The first attempt still had a LIVE batch pending and was already late. On the next three attempts LIVE had no batches, but preparation arrived around 217, 209 and 209 after another suppression/rebuild path. These are CPU-deadline deferrals. There were no steady-state replay increments during this four-frame hold.

### C. Structural nine-object obstruction

The controlled layout has eight initial sprites at 199 and the ninth, logical player 0, at 235. Every initial slot's conservative release is `199+24=223`; the next sprite's planning deadline is `235−12=223`. There is no earlier legal compare under the existing planner's rules. [S,D]

Later in the run, main reached preparation at **163:39** and deferred at **164:05**, despite approximately 20 lines remaining to the admission cutoff. The batch was serviced around 225:58 and the assignment written around 227:15, before Y=235. Scrolling stayed at world row 40/fine 7. [M]

This demonstrates why correct sprite servicing, exact PAL cadence and a stable border can coexist with a severe scrolling hold.

## 5. Dominant pressure analysis

### Isolated CPU measurements

Costs below are executable CPU clocks, not guaranteed raster duration. [M]

| Routine/path | Clocks | Interpretation |
|---|---:|---|
| Upper shift, 480 bytes | 3,846 | 3,840 copy + RTS |
| Crossing save, 40 bytes | 326 | 320 copy + RTS |
| Lower shift, 440 bytes | 3,526 | 3,520 copy + RTS |
| Crossing restore, 40 bytes | 326 | 320 copy + RTS |
| Incoming metatile decode | 1,696–1,704 | Six sampled valid logical rows, not exhaustive WCET |
| Incoming 40-byte indirect screen copy | 625 | General destination-row path |
| Incoming turret overlay, eight empty slots | 103 | Occupied/matching paths vary |
| Turret publication, eight empty slots | 558 | Includes unconditional identical 32-byte glyph copy |
| `swapRenderPlans` | 29 | Index exchange, not data copy |
| `renderSprites`, four slots, no confirmation scan | 447 | HUD-enabled build; controlled zero X-MSB case |
| HUD setup / four-slot handoff | 219 / 398 | Excludes dispatcher/KERNAL and DMA stalls |
| Batch application: 1 / 4 / 8 assignments | 135 / 318 / 562 | No-hit path, excludes IRQ entry/dispatch |
| `startLiveRasterPlan`, zero batches | 49 | Cursor setup only |
| Sort reverse order, 8 / 16 objects | 1,177 / 4,365 | Existing corrected insertion sort |

The batch body's measured no-hit formula is **74 + 61 × assignments**. “100–150 cycles per batch” describes only a one-assignment body, not a multi-assignment batch or its entire IRQ. A full IRQ also pays hardware/KERNAL entry, the dispatcher, forensic logging, return, and possibly collision confirmation. The forensic breadcrumb itself is roughly 65 CPU clocks by instruction count, not the source comment's approximately 24. [S,D]

### Planning cost versus object count

These are controlled, uncomplicated snapshots without clipping. Equal-Y cases incur the stable-tie sort branch. [M]

| Layout | Collect | Sort | Initial snapshot | Batch builder including masks/setup | Total |
|---|---:|---:|---:|---:|---:|
| Six equal-Y objects | 405 | 310 | 839 | 696 | 2,250 |
| Eight equal-Y objects | 461 | 428 | 1,106 | 778 | 2,773 |
| Eight at 199, ninth at 235 | 489 | 485 | 1,106 | 1,506 | 3,586 |
| Sixteen, close-four-line batches | 685 | 870 | 1,106 | 7,427 | 10,088 |

The nine-object case adds **813 CPU clocks** over the eight-object example—already similar in scale to the reported 14-line slip, but occurring in the **previous-frame planning window**, not in frame-top rendering. Dense16's batch builder is substantial enough to justify later planner work. It does not prove a JIT rewrite is needed for nine-object gameplay.

The sorter progression defect has already been fixed. Historical 10,673-cycle numbers apply to the older defective sorter; current reverse16 measures 4,365 excluding the probe wrapper, consistent with the historical corrected 4,373 including it. Do not count that prior fix as an available new saving.

### Ranked causal pressure

1. **Outstanding-LIVE coarse gate:** most important for repeated holds. It is a logical incompatibility, not a large routine cost. The nine-object experiment proves it survives adequate CPU arrival time.
2. **Coarse transfer plus just-in-time row decode:** approximately 8,000 copy clocks per coarse transition before decoder, indirect row install, wrappers and turret work. Together, coarse preparation/finish are roughly 10.5–11 thousand CPU clocks distributed across two physical frames, plus contention. The critical upper segment is roughly 6.7 thousand before stalls, rather than an inexpensive row increment.
3. **BUILD planning and suppression:** scales with both object count and layout. Eight-slot searches, rejected candidates/retries, per-assignment snapshots and masks grow sharply beyond eight. Suppression can run the batch builder twice, on exactly the pending-coarse frame where spare time is least available. In the reproduced hitch its second build occupies about 16 raster lines; policy plus rebuild approximately 22.
4. **Collision confirmation before initial hardware writes:** experimentally accounts for the observed approximately 14-line slip. The scan can inspect all 15 non-player logical slots, filter type/viewport/death state, and perform overlap tests. Its cost occurs inside a publication-sensitive window, and also inside some batch/replay IRQ paths.
5. **Clipping and combat spikes:** initial snapshots can build up to eight full private clipped bitmaps. A full copy plus blanking costs of order a thousand clocks or more per straddler, depending on depth. Mutable health sprites bypass the immutable-source shortcut. Health-bar creation on nonfatal hits also copies 64 bytes and can run from both cannon hits. These are variable pre-admission costs; they must be profiled separately from sorting.
6. **HUD, badlines, sprite DMA and BORDER:** bounded but significant contributors to elapsed time. HUD handoff interrupts lower copying; sprite DMA persists after the last assignment has been programmed; BORDER occupies roughly the remaining interval to raster 250 when entered normally around 242–243. None disappears by replacing BUILD/LIVE.
7. **Publication/catchup/replay:** small on the healthy path, potentially large if it synchronously services due events. It amplifies poor phase alignment. It is not the fundamental byte-copy overhead implied by “BUILD→LIVE publication.”

### Placement matters more than averages

At divider 2, a coarse transition is due every 16 physical frames in uninterrupted operation. Approximately 10.5–11k coarse clocks amortise to about 660–690 CPU clocks per frame. That acceptable average conceals a large upper block that must fit before the next presentation and a large lower block that must finish before a specific fetch.

Likewise, a 449-cycle redundant static glyph copy is less than 3% of a PAL frame, but removing it from the first approximately 20 lines can matter more than saving the same cost after raster 270.

The actual lower copy example consumed 5,418 elapsed clocks against approximately 3,882 clocks for its no-contention instruction path. The difference is about 1,536 clocks of combined preemption/contention. It would be wrong to attribute all of that to badlines, or all to the HUD, without finer trace accounting.

## 6. BUILD/LIVE assessment

### What it buys

- Stable render payloads while the game updates logical state.
- Small and predictable assignment bodies: precomputed slot, pointer, colour, X/Y and masks.
- Explicit player hardware ownership for collision capture.
- A known full-frame schedule that can be examined before presentation.
- A complete previous frame available for safe replay.
- Existing integration with HUD time-domain reuse and clipping pools.

This is still a net advantage for the engine's current scale. Hardware writes already happen near the beam; BUILD/LIVE precomputes their payload and schedule rather than preventing timed reuse.

### Actual costs and liabilities

There is duplicated storage and preparation: initial snapshots, assignment snapshots, mask construction, and scanning all eight candidate slots per later object. However, there is no full-buffer publication copy. The 29-cycle swap is negligible beside a 1,696-cycle decode or 7,427-cycle dense batch build.

The current batch builder does masks, eight-slot setup and HUD-floor work **before discovering there are fewer than nine objects**. With no reuse batches, much of that work is unnecessary. A guarded early return after correctly zeroing BUILD's batch count is a promising low-risk path, potentially saving roughly 650–750 clocks in the eight-object case. This requires verifying downstream scratch contracts, not just deleting instructions.

Publication is not a fully general atomic transaction. `swapRenderPlans` and `renderSprites` precede the SEI in `armFirstBatch`; correctness depends on the established early-frame ownership protocol. The SEI covers `publishRasterPlan` and anything it services synchronously. HUD handoff consumes LIVE as well. A future change must not assume swapping two indices at any arbitrary raster is safe.

Replay is selected when `RASTER_PRESENT_READY` is zero at FRAME. It rerenders the **old LIVE initial snapshot**, saves/restores five scratch bytes, restarts LIVE batches and increments a counter. It does not rebuild/sort BUILD inside the IRQ. Missing a first batch's compare is handled by dispatch catchup; that is not the direct predicate for replay.

The two replay increments in each new capture were at startup. The four-frame authored scroll hold and long controlled late-nine hold did not require new steady-state replay increments. Consequently, “eliminate replay and the hitch disappears” is contradicted by the new evidence.

**Verdict:** retain BUILD/LIVE's isolation and existing scheduler. Optimise avoidable planning work, measure collision paths, and fix the coarse-admission contract. Reassess the planner architecture only if its measured cost remains dominant after those changes.

## 7. JIT mux assessment

A viable JIT alternative would retain logical objects and a stable sorted presentation list, program the first hardware occupants, and derive later reuse/IRQ work as each slot becomes available. It can fit within the current dispatcher: SPRITES becomes an incremental service step; FRAME, DISPLAY and BORDER retain explicit ownership.

| Concern | Likely JIT effect |
|---|---|
| Main workload | Removes some prebuilt batches/masks and candidate processing; substantial potential for dense16, modest for one reuse |
| Publication | Replaces full-plan readiness with stable-list/initial-state readiness; does not remove the need for a coherent frame snapshot |
| IRQ work | Adds next-object/slot/release decisions, mask changes and scheduling to hardware writes |
| Worst-case density | Closely spaced Y values can require long catchup runs or several serviced objects per IRQ; precomputed masks currently protect this window |
| Scroller | Helps pre-admission main CPU time only if the saving occurs there; outstanding late sprites and DMA remain |
| HUD | Can model HUD as an initial slot occupant, but must still enforce real release time and per-slot mode/enable ownership |
| Collisions | Must consume latches under the old physical ownership, then update ownership; mutable logical data and ID reuse remain hazards |
| Player/object pool | Logical player 0 and allocator starting at 1 need not change; cyclic hardware assignment must not silently drop the player |
| Recovery | Still needs explicit late/near/wrapped-event handling and a defined old-frame/partial-frame policy |

### Likely savings, with limits

At nine objects, the entire measured batch-build budget is 1,506 clocks. A JIT design cannot claim all of that as net saving: it must still snapshot or freeze relevant state, choose hardware ownership and update masks. An engineering estimate of several hundred to approximately 1,500 clocks removed from the **up-front** path is plausible; it is not a measured total-frame win.

At sixteen close-spaced objects, there are 7,427 clocks in the current batch builder to investigate. Several thousand clocks of up-front reduction could matter materially. But transferring decisions to the exact four-line reuse intervals can make sprite-start reliability worse despite improving main-thread completion. Benchmark both deadline tails and total executed clocks.

For eight or fewer objects, the cheaper existing-builder early exit obtains much of the obvious benefit without introducing a new IRQ workload.

### Does it fix the hitch?

**Not by itself.** A JIT scheduler preserving “no outstanding sprite work before coarse copy” still cannot admit the 199/235 layout by raster 184. If it allows sprite IRQ work during copying, it has changed the **scroller's scheduling contract** as well. That change can also be made with precomputed LIVE batches, whose exact future cost is easier to budget.

JIT does not remove initial sprite deadlines, DISPLAY handoff, the physical frame boundary, collision confirmation, BORDER writes or sprite DMA. It also does not solve finite-fetch terrain edges.

Do not implement JIT now. If later profiling warrants a comparison, retain the object model and snapshot isolation; add a compile-time alternative SPRITES producer inside the existing dispatcher, preserve an equivalent old-LIVE fallback, and require measured superiority before removing BUILD/LIVE. Do not transplant a second commercial IRQ chain.

## 8. Scroller optimisation assessment

### A. Predecode the incoming row

**Best first scroller intervention.** The current upper path derives and decodes the new incoming logical row after shifting. Decode the upcoming world row—current origin minus two, modulo stage length—on an earlier fine-phase frame and retain a validity tag containing origin/level information. On the eventual coarse step, consume the 40-byte result and apply current turret state at installation.

Expected critical-window reduction: approximately **1,700 CPU clocks, equivalent to 27 unstalled lines**. It moves work rather than eliminating it. Place the earlier decode after that frame's deadline-sensitive work, with a bounded completion/validity protocol. Do not force a whole-frame predecode cost immediately before another admission gate.

A 40-byte staging row plus a few validity bytes fits small CPU-accessible slack outside the packed `$2000` object block; it must have explicit guards. The existing incoming buffer is also used by row rendering and related terrain operations, so its exclusive lifetime must be proved or a separate buffer allocated. Never alias it with the physical crossing-row buffer. Keep turret overlays fresh rather than precommitting live/dead turret state many frames early.

The 16-frame coarse period gives ample opportunities to prepare immutable terrain, but a held fine 7 can last indefinitely. Cached data must remain correct through deferral, stage wrap, death restoration and level changes.

### B. Incoming-row copy and decode layout

The 40-byte generic indirect screen copy costs 625 clocks. A dedicated unrolled row-0 installation would be about 326 clocks including RTS: **approximately 300 clocks saved**, at the cost of about 240 bytes of instructions before bookkeeping. Current bank-0 code slack cannot simply absorb that expansion; place it in an explicitly allocated CPU-code region.

Lookup tables for metatile pointer low/high parts could reduce repeated `id*16` arithmetic. A transposed definition layout could also simplify fetching each four-character subrow. These are reasonable second-order changes, but once decode is outside the critical window, saving a few hundred decoder clocks may be less valuable than reducing admission lateness elsewhere. Do not combine an asset-format rewrite with the first predecode proof.

### C. Existing full-screen copy strategy

The large shifts are already unrolled absolute LDA/STA pairs: eight clocks per byte, no loop or indexed page-crossing overhead. An indexed/general memcpy is usually smaller, not faster. The two crossing-buffer transfers are necessary for this architecture's physical-content preservation and cannot simply be replaced by world-row regeneration when turret/death edits exist.

A scroll-offset pointer cannot make the VIC treat a 1 KB screen as an arbitrarily shifted row ring. Changing the software origin leaves the hardware's row-major matrix fetch unchanged.

Do not spread writes to the **active** matrix across arbitrary earlier fine-phase frames. That would present part of the next coarse state too soon. Only work independent of the current visible matrix—decode, immutable address lists, or an inactive screen—can freely move earlier.

### D. Replace blanket exclusion with a measured budget

After predecode, prove whether upper preparation can start in its safe post-fetch window while selected LIVE batches remain. The useful inputs already exist: batch rasters, assignment counts, release windows and ownership. Budget remaining copy CPU, badline/DMA stalls, complete IRQ paths including collision, BORDER occupancy, and the frame-zero readiness margin.

This is a timing-contract change, not “remove one branch.” Prove scratch noninterference, bound every admitted interruption, detect physical-epoch changes, and preserve deferral for unproved schedules. Use a finite admission table or conservative measured classes if a general analytical bound is too fragile.

Predecode removes the long TEXT_SRC/TEXT_DST decode work from the interrupted segment, making this proof smaller. An eight-assignment batch body is only 562 CPU clocks before entry/dispatch/collision—not free, but much easier to account for than an unbounded JIT service run.

Earlier service of a batch within its legal release/deadline interval can also remove avoidable obstructions. Preserve payload/slot choice first and derive the batch's maximum required release. Do not retime a compare before a previous occupant finishes. The 199/235 example has no slack under the current rules and must be handled by overlap/buffering or an explicit load restriction.

The nominal row-12 release may offer approximately eight additional raster lines compared with the current wait-160 convention, but this is a **derived opportunity requiring VIC measurement**, not permission to change the constant.

### E. Two screens and `$D018` switching

An inactive 1 KB matrix allows construction of the next coarse state across earlier frames. A normal next-screen construction copies 960 shifted cells plus installs 40 incoming cells; copying the 960 at eight clocks each costs 7,680 CPU clocks, and the incoming install still costs time. A page flip makes **publication** cheap; it does not make the coarse update computationally free.

Spread across 16 frames, the shift alone averages 480 CPU clocks per frame. Unlike the current split copy, it need not monopolise one post-raster-160 window and the next early frame. Rebuild from the active screen into the inactive screen after each flip, with explicit freshness/version tracking for mutable turret cells. The old inactive screen is two origins behind and cannot be treated as an already-current source without a defined update strategy.

Colour RAM is not double-buffered by `$D018`. Uniform terrain colours help, but turret pulses, vacated cells and deaths still require a consistent colour update plan. Both screens' sprite-pointer tables must contain the correct HUD/gameplay ownership at each phase. A screen switch affects those pointers too.

### Concrete memory feasibility

The freshly assembled layout corrects a significant handoff error:

| Region | Actual use |
|---|---|
| `$0400–$07FF` | Active screen, including pointer table |
| `$0801–$1EE3` plus small `$1Fxx` allocations | Main code/tables/marker |
| `$2000–$23FE` | Packed engine/object/render state |
| **`$2400–$26FF`** | **Twelve VIC-visible sprite bitmaps, not attack tables** |
| `$2700–$290E` | CPU-only attack/path tables: **527 bytes** |
| `$2920–$2E69` | Background code/state: **1,354 bytes** |
| `$2F00–$2FFF` | Four HUD bitmaps |
| `$3000–$33FF` / `$3400–$37FF` | Health / clipping pools |
| `$3800–$3FFF` | Runtime charset |
| `$4000–$5927` | Unrolled copies and other CPU code |
| `$5A00–$5C3F` | This level's terrain source glyphs |
| `$6000–$642D` | Scheduler/state/forensics |
| `$6600–$6C39`, guarded below `$8800` | Current metatile stage data; growth allowance must be respected |
| `$8800–$8FDF` | Background turrets |
| `$9000–$9FFF` | Not allocated by this baseline |

**Feasible design candidate [D]:** relocate the 527-byte CPU table block and 1,354-byte background block into a guarded allocation such as `$9000–$97FF` (2,048 bytes, leaving 167 bytes before alignment/expansion). This frees `$2800–$2BFF` for a second matrix. Keep original sprite bitmaps at `$2400–$26FF`; their bank-local pointers remain valid. Bank 0 and charset `$3800` can remain unchanged. Matrix selection becomes `$D018=$1E` or `$AE`, with alternate sprite pointers at `$2BF8–$2BFF`.

This is a source-level layout proposal, not an assembled relocation. Check all absolute addresses, tool assumptions, page-crossing timing, guards and level growth. It demonstrates that the lack of a free **2 KB charset** does not rule out a **1 KB screen**. Moving the whole `$2400` segment out of bank 0 would be wrong because it contains live sprite art.

### F. Can it also solve soft edges?

**It can facilitate a new edge presentation, but does not solve it automatically.** A page flip still has 25 fetched rows. If rows 0 and 24 are always blank, the remaining 23 terrain rows occupy `56+fine .. 239+fine`: 184 moving pixels. Their fixed all-phase intersection is only **63..239, 177 pixels**. This removes terrain currently present within the accepted 55..246 region.

Therefore the handoff's “blank outer row solves AMBER for free” is not valid under the unchanged-aperture requirement. The alternatives are an explicitly accepted smaller crop, phase-aware boundary glyph/content construction, or a separately proven display-mask/fetch design. Partial-glyph edges need character capacity and per-phase updates; they are not just two blank screen rows.

A two-screen scroller could address both objectives if its geometry is designed and accepted explicitly. It should first prove load stability with the existing terrain geometry, then prove its edge treatment independently. Do not revive the failed variable-entry ECM mask as a hidden dependency of the scrolling fix.

A bitmap approach makes pixel-level edge content more flexible but introduces an 8 KB bitmap and substantially different content/scroll work. In this bank layout that is a major asset/memory redesign, unjustified for the current evidence.

## 9. Slap Fight / Terra Cresta comparison

### Slap Fight

The supplied `slap_fight_border_hud_annotated.asm` shows:

- HUD setup at `$0F5F` uses all eight physical sprites at Y=12, with hires mode and pointers in `$FBF8`.
- Frame-top `$105F` restores ECM/RSEL state and schedules gameplay multiplexing from raster 32.
- `$1936` obtains a logical object through a sorted index, reads Y, tests a roughly Y−14 lead, writes colour/pointer/X/Y and updates the slot's X-MSB.
- Each gameplay pointer is written to both `$C3F8` and `$C7F8`: direct evidence of support for two screen-page pointer tables.
- `$1802` and `$187C` coordinate bottom/top display transitions involving RSEL, ECM and `$D018`.

Transferable: timed hardware ownership, narrow register-update paths, stable sorted input, keeping both screen pointer tables coherent, and treating HUD reuse as part of the frame schedule.

Not established: the sorting algorithm and its cost, complete slot-availability proof, full scrolling-copy implementation, exact page-flip cadence, collision rules, or worst-case late-service guarantees. Its instruction excerpt omits the next-slot traversal and parts of the IRQ chain. Do not assign it a measured capacity or cycle advantage on that basis.

### Terra Cresta

The supplied `terra_cresta_border_hud_annotated.asm` shows:

- Thirty logical list entries, initialised through index `$1D`; sorting occurs elsewhere and is not supplied.
- `$4A57` walks the indexed logical objects and cycles hardware slots 7..0, programming them shortly before the beam reaches their Y.
- Pointer writes again update `$C3F8` and `$C7F8`.
- `mux_reschedule` derives a following compare; its late path uses `inc $D012`; it stops near `$F0` and returns toward the border/frame chain.
- `$4549` programs top-border HUD sprites at Y=28/29, with mixed mode and CIA2 timer setup.
- `$483C`/`$4889` coordinate ECM/RSEL/`$D018` display transitions.

Transferable: the compact sequential service model and explicit screen/HUD phases. The cyclic slot model may avoid the present eight-candidate search, if this engine can prove equivalent admission for its own layouts.

Not transferable without proof: the assumptions that make cyclic reuse safe; its `$F0` endpoint; literal late-service code; CIA2/vector ownership; or a thirty-entry list as evidence that thirty arbitrary overlapping sprites fit. The excerpt does not show explicit previous-occupant release checks comparable to this engine's Y+24 policy.

### Shared differences and cautions

Both references use direct `$FFFE/$FFFF` chain setup and memory arrangements unlike the current KERNAL-vector dispatcher. Their phase-specific `$D018` values and pointer tables are evidence of display switching, not a complete demonstration of their scrolling algorithms.

The provided `SBC #$0E` fragments do not show all carry-state provenance. “Approximately fourteen lines ahead” is appropriate; do not build a precise timing proof from the annotation alone.

Likewise, `inc $D012` is an NMOS read-modify-write operation on a register whose read returns the beam low byte while writes program a compare. It is not a general wrap-safe “next physical scanline” scheduler. Preserve the current explicit epoch/overdue handling rather than copying that fragment.

The references validate the **possibility** of combined HUD reuse, dynamic multiplexing and display switching. They do not establish that replacing BUILD/LIVE is the best way to remove this engine's coarse gate.

## 10. Root-cause judgement for remaining scroll hitch

**High confidence:** safe coarse deferral is a real remaining hitch mechanism, caused by the interaction of the scroller's admission policy and LIVE reuse schedules. The source, historical counterexample and new controlled run agree.

**High confidence:** CPU lateness independently causes deferrals after the outstanding batch disappears. The authored capture records a four-frame sequence containing both classes, with suppression/rebuild overhead on the late CPU path.

**High confidence for the reproduced early-frame symptom:** collision confirmation accounts for the roughly 14-line renderer slip. It precedes the first assignment; BUILD sorting and row copying are not executing in that interval. A broad-phase-positive latch need not produce a confirmed hit, and development invulnerability does not eliminate the scan.

**Strong source-supported inference:** synchronous DISPLAY service inside SEI can leave a raster IRQ latch pending while the dispatcher selects BORDER next. On CLI the IRQ then sees the newer event classification and enters BORDER early. The new trace reproduces the sequence. Definitive attribution of the hardware latch should add `$D019` read/write tracing; do not remove the existing early guard based solely on this inference.

**Not demonstrated:** that replay is the cause of the user's remaining hitch; that a real lower-copy deadline is missed in supported gameplay; that the specific manual six-enemy/two-bullet case is identical to the seeded authored sequence; or that the 55..246 terrain corruption rate has changed. The new run supplies a reproducible causal class, not a recording of the user's exact play session.

A count alone is inadequate. Six enemies + two hostile bullets + player is nine logical objects and can involve reuse, but Y distribution, clipping, collision activity and the current LIVE plan determine pressure. `RENDER_COUNT` saturates at eight; `SORTED_COUNT` may be reduced by suppression even while an older LIVE plan still contains a ninth assignment. Log all three domains explicitly.

## 11. Primary recommendation

**Choose Option 3: optimise both incrementally.** Keep the object model, player invariant, BUILD/LIVE payload isolation, one raster dispatcher and HUD ownership scheme. Optimise the critical CPU paths first, then prove a less restrictive coarse scheduling contract.

| Proposed work | Expected benefit | Deadline helped | Cost/risk |
|---|---|---|---|
| Skip batch setup when no reuse is needed | Approximately 650–750 CPU clocks at eight objects | Before coarse admission and frame-ready | Small; preserve batch-count/scratch semantics |
| Stop rewriting unchanged static turret art | About 449 CPU clocks for the copy loop | Before initial sprites/DISPLAY and subsequent main work | Small; retain dead-cell restoration and lifecycle invalidation |
| Predecode incoming terrain | Moves approximately 1,700 CPU clocks out of upper preparation | Upper completion/frame-ready; supports a later admission proof | Small/medium; validity and scratch ownership |
| Dedicated row-0 copy, if memory cost justified | About 300 CPU clocks | Upper completion | Small logic change, explicit code allocation |
| Optimise collision confirmation without semantic loss | Measured opportunity: roughly 820 elapsed clocks on reproduced path, not all necessarily removable | Initial sprites, DISPLAY proximity and IRQ tails | Medium; latch/ownership and logical-state timing |
| Avoid unnecessary suppression rebuilds; retime flexible batches | Up to the reproduced approximately 16-line rebuild, or eliminate avoidable pending-work rejection | Pre-admission | Medium; presentation omission and release proof |
| Measured pending-batch-aware coarse admission | Removes the structural blocker for proved schedules | Coarse progress despite legal late sprites | Medium/high timing proof; retain safe fallback |

Do not add these savings mechanically: they occur in different frames/windows, may be absorbed by an intentional wait, and some are workload-specific. The first two together offer roughly **1.1–1.2k CPU clocks** on an eight-initial-object/no-batch frame. Predecode plus specialised row installation offer roughly **2k clocks** out of upper preparation. Neither result is an accepted new raster cutoff.

The target practical envelope is reliable five- and six-enemy gameplay, including the explicit six + two bullets + player case, without silent permanent slot reservation or a five-enemy cap. Higher synthetic loads determine the next envelope; do not announce a numeric capacity increase until placement and cadence tests pass.

Expected hitch effect: fewer CPU-deadline holds first; elimination of the proved late-batch holds only after the admission/buffering stage succeeds. Expected soft-edge effect of the initial stages: none. Address that geometry separately.

If bounded overlap cannot satisfy the supported gameplay matrix with margin, the fallback is **Option 1 with a staged two-screen scroller**, keeping BUILD/LIVE. This is more directly related to the demonstrated obstruction than JIT. Option 5 remains an honest temporary shipping policy if neither timing proof passes, but the envelope must describe schedules and latency, not just enemy count. A rewrite of both components is not justified.

## 12. Staged migration plan

Every stage preserves a runnable baseline configuration, is independently reversible, and ships only after its own acceptance criteria pass. The names below describe prospective toggles; none was added during this review.

| Stage | Work | Measurable acceptance | Reversal |
|---|---|---|---|
| 0. Reproducible diagnosis | Capture fixed-input/snapshot baseline, exact deferral reasons, collision paths, ready epochs, physical assignment timing | Reproduce both CPU and pending-LIVE holds; tracing does not alter emulated state/cadence | Remove probes only |
| 1. Low-risk CPU work | No-reuse batch early exit; static-glyph publication invalidation; evaluate redundant suppression work | Equivalent rendered plans/bitmaps; expected CPU savings observed; no new service/start errors; preserve dead-cell and lifecycle behaviour | Independent toggles/reverts |
| 2. Incoming-row predecode | Add row buffer/tag; prepare before demand; retain existing fallback decode | Byte equality for all level rows, all subrows, wraps and turret states; upper critical path shorter by approximately measured decode cost | Select original decoder path |
| 3. Small scheduler corrections | Audit pending-latch ownership; preserve BORDER guard; earlier legal batch service and post-wait admission checks | Explicit overdue/near/wrap injection passes; no early reuse; quantify minimum margins; baseline assignments preserved | Existing scheduler/admission mode |
| 4. Structural overlap proof | Keep game runnable; enable measured batch-aware coarse admission only for proved schedule classes | Controlled 199/235 layout scrolls continuously; no lower/upper fetch violations; no service/start failures; forced overload defers safely | Original blanket gate |
| 5. Gameplay integration | Apply proved classes to real six + two + player runs, combat/turrets/clipping and repeated wraps | Full matrix below; no unwanted fine-7 holds within stated envelope; collision equivalence | Disable new admission while retaining proven CPU improvements |
| 6. Optional edge/display proof | Investigate edge geometry independently; if overlap failed, evaluate second-screen design first | Existing aperture preserved unless user explicitly accepts a different one; zero new same-phase shimmer; publish quantitative pixel result | Original screen/mask-OFF display |

Stage 4 is the decision gate. Do not claim the objective is met after Stage 2 merely because traces finish earlier. Conversely, do not proceed automatically to a second-screen rewrite if Stage 4 passes comfortably.

If second-screen fallback is needed, subdivide it:

1. Relocate only CPU tables/background code, while still displaying `$0400`; prove unchanged gameplay and memory guards.
2. Add inactive `$2800` screen and dual pointer-table bookkeeping; build/compare it without displaying it.
3. Flip between identical matrices through the existing FRAME owner; verify HUD and all eight gameplay slots.
4. Populate next coarse content incrementally; retain existing edge geometry and compare matrix/world mapping.
5. Integrate turret death/colour updates and main presentation ownership.
6. Assess edge treatment as a separate acceptance decision.

Each substage must remain selectable against the single-screen baseline. Remove the old path only after the new design improves the relevant tail margins and scrolling progress without reducing the required gameplay envelope.

## 13. Acceptance/test matrix

### Required load and timing coverage

| Dimension | Required cases |
|---|---|
| Shipping-style loads | Five enemies; six enemies; six enemies + two bullets + player; actual authored waves |
| Separate synthetic capacity | 0..16 logical objects; 8 initial/no reuse; 9 with one reuse; sixteen spread-out and sixteen close batches |
| Distribution | Top straddlers, mid-screen, bottom cluster, mixed early/late; player at every sorted rank and hardware slot |
| Structural obstruction | Eight at 199 + player at 235; early-flexible batches; late compulsory release; residual sprite DMA after all assignments are done |
| Scrolling | Continuous input; all eight phases; divider-2 cadence; repeated 7→0; multiple stage wraps; prolonged deferral then release |
| CPU spikes | Broad-phase-negative/positive collisions, full confirmation scan, two cannon hits, health sprites, clipping cache misses, simultaneous turret deaths, suppression rebuild |
| Scheduler faults | Delayed publication; near compare; overdue compare; 255→256 and 311→0; intentional replay; queued IRQ while synchronous service changes next event; impossible late BORDER |
| HUD | Persistent four sprites; slot-7 enable race regression; handoff timing for each slot; all eight slots usable afterwards |
| Lifecycle | Menu → play → death/respawn → game over → initials/menu → restart; full collision build as well as development invulnerability |
| Memory | Matrix pointers, cross-row contents, immutable glyphs, private pools, buffer identities, logical-slot generations; both pointer tables if double-buffered |
| Presentation | Temporal terrain oracle over 55..246; incoming/outgoing seams; explicit outer-band/coarse-pop and same-phase shimmer checks |

### Metrics and passing criteria

- **Physical cadence:** exactly `[19656]` physical frame epochs. Independently report main-loop presentations, ready/replay rates and scrolling displacement. Constant PAL hardware cadence alone is not evidence of smooth game updates.
- **Scrolling progress:** for supported uninterrupted cases, requested phase advances every two physical frames and one world-row transition every sixteen, with zero additional fine-7 holds after startup. Record maximum consecutive hold, total holds and their exact reasons. Forced overload may defer, but must recover when load is removed.
- **Sprite correctness:** zero service failures, zero sprite-start misses and zero incomplete LIVE assignments in the supported matrix. Every assignment must be linked to its intended physical frame and logical-object generation, not only an address reused later.
- **Deadline margin:** record minimum and distributions of final pointer/X/Y/mask write margins to actual sprite DMA/start, upper completion to readiness, lower destination writes to VIC fetch, and handoff completion to each deferred sprite's start. Positive averages do not compensate for a negative minimum.
- **Catchups/replays:** report startup separately. Intentional parked-main replay and correctly handled near events are not automatic failures. Unexpected steady-state replay growth or repeated catchup bursts require explanation and must not hide lost simulation/scroll cadence.
- **HUD/border/locks:** zero unexplained HUD disappearances, border skips/bails in supported operation, or hard locks. Injected impossible deadlines must take the documented bounded recovery path. Preserve the early-event classifier until its replacement is proved.
- **Terrain/edges:** zero new body temporal differences or coarse jumps within 55..246. Measure outer-edge pop separately from body cleanliness; require no new per-frame shimmer. Any crop change must be explicitly recorded rather than silently narrowing the oracle.
- **CPU accounting:** report per-routine CPU clocks and elapsed physical clocks separately; correlate coarse, collision and assignment-count classes. Require demonstrated removal of the diagnosed bottleneck, not just a faster empty scene.
- **Functional equivalence:** no loss of player slot 0, no permanent hardware reservation, no new silent sprite drops, no changed collision outcome or hostile-projectile lifetime/count. Log existing suppression distinctly from render correctness.

Use fresh VICE instances, programmatic input and non-activating launches. Existing `vice_scroll_test --physical --trace`, `check_raster_capture`, `check_scroll_edges_rsel1 --aperture 55 246`, viewport/clipping/turret checks and lifecycle tools provide useful pieces. Their current assumptions must be inspected: legacy fixture names such as `early24` or `late243` can be culled by today's viewport and exercise no batches. Assert the generated schedule as well as the test's name.

For comparative acceptance, use fixed snapshots and recorded logical input/encounter choices. CIA-derived random choices diverge when execution time changes; fewer hitches in a different encounter sequence is not a valid causal A/B. A reasonable campaign is at least 10,000 physical frames per key gameplay case, plus short exhaustive schedule/phase fixtures and repeated complete stage wraps. Extend it when failures or rare timing tails justify doing so, not merely to accumulate a larger frame count.

A new architecture is better only if it improves scrolling progress and worst-case deadline margins at equivalent content/placement/collision correctness, with no unexplained loss of objects or aperture. Lower main-thread time accompanied by worse IRQ misses fails that test.

## 14. Risks and fallback

- **Overoptimistic copy budget:** sprite DMA can continue after assignments finish; collision confirmation changes IRQ duration. Retain conservative admission and exact fallback until measurements cover the admitted classes.
- **Moving work across ownership boundaries:** row caches, collision deferral and screen flips can introduce stale world state. Use explicit validity/version contracts; preserve current timing of logical damage unless a separately accepted change says otherwise.
- **Changing IRQ-latch handling:** acknowledging at the wrong point can erase a newly due event. Trace cause, prove ordering, keep early/late guards.
- **Active-screen partial progress:** once upper rows have changed, a simple “defer” is no longer equivalent to preserving the old frame. Admission must decide before mutation, or a new partial-work state machine must be proved explicitly.
- **Code placement:** unrolling an extra 40-byte copy or adding tables can exceed small bank-0 gaps. The current `$2000–$23FE` state has essentially no room. Relocations need new guards and a fresh build map.
- **Double-screen coherence:** pointer tables, turret mutations, colours and world origin must all refer to the displayed page. A second matrix does not buffer colour RAM or collision state.
- **Gameplay fairness:** hiding one bullet or dropping a player assignment is not a valid substitute for a scheduling fix. Existing suppression is a mitigation to measure and eventually reduce, not a proof of capacity.
- **Edge treatment:** preserving a fixed 192-pixel body while removing finite-fetch edges is a distinct display problem. Reject an apparent win obtained only by moving the oracle boundary.

Rollback should preserve independently verified improvements: return to the original gate if overlap fails; return to one screen if page ownership fails; leave masking off if edges shimmer. Keep the HUD fixes and player invariant throughout. If release must precede a satisfactory timing change, publish a measured load/schedule envelope and keep safe deferral, rather than promising a universal six-enemy limit or guarantee.

## 15. Questions / uncertainties requiring measurement

1. What exact LIVE schedule, collision latch and coarse-gate branch accompany the user's manual six + two + player hitch? The new capture proves relevant mechanisms, but is not that session.
2. How much of the collision-confirmation cost can be removed while preserving outcomes and the current logical-state sampling point? Latching only a mask is insufficient if confirmation is delayed across object motion/reallocation.
3. Does the pending DISPLAY latch fully explain early BORDER delivery? Add `$D019`/`$D012` tracing around synchronous dispatch and CLI, including cause classification.
4. What are the full WCET distributions for occupied/matching turret overlays, several dead-cell restorations, full clipping rebuilds, and collision-positive batch IRQs?
5. Can predecode plus a conservative remaining-batch budget safely admit the 199/235 layout and the real nine-object gameplay distribution? Measure actual write/fetch and DMA margins; do not extrapolate from blank sprites alone.
6. Can the current wait-160 fence move closer to the derived row-12 fetch release, and what cycle margin is required? The source's old fetch comments need correction before any implementation relies on them.
7. How much suppression work is unnecessary when it cannot affect the current LIVE blocker? Could avoiding it improve CPU timing without worsening the following presentation? Current and next plans must be analysed separately.
8. Are the shader-free boundary-glyph/crop alternatives acceptable within the exact desired aperture and character budget? No screen-buffer count answers that question by itself.
9. After low-risk savings, is dense16 planning still the dominant obstacle for desired gameplay, or only for a synthetic capacity benchmark? This decides whether a JIT experiment has enough value.
10. If a second screen is needed, does the proposed CPU relocation remain valid for maximum-size level packages and future code growth? The present map proves feasibility for this baseline, not unlimited headroom.

## 16. Concise implementation brief for the next engineering task

**Objective:** retain BUILD/LIVE and the fixed HUD; reproduce and reduce CPU-deadline scroll holds, then prove whether legal outstanding batches can coexist with coarse work. Do not start with a JIT rewrite.

Start from PRG hash `1fadf2b42cc30b333622014af1a1cf163afd8ea607150f76a89a22709aea22dd`. Preserve the existing masking experiment separately; use mask OFF. Preserve player logical slot 0, allocator starting at 1, all eight post-HUD hardware slots, one raster dispatcher and current terrain aperture.

First deliver a controlled baseline trace for the actual six + two + player case and the 199/235 nine-object counterexample. Record collision-confirmation cost, current LIVE versus next BUILD work, exact coarse-deferral reason, presentation readiness, sprite DMA margins and physical cadence.

Implement separately reversible changes for (a) no-reuse batch-builder early exit, (b) unchanged static turret-art publication, and (c) validated incoming-row predecode. Measure against identical input/state. Keep the original gate initially. Verify collision and mutable turret/clipping semantics.

Then present a concrete bounded-admission design using measured remaining LIVE work, including collision and DMA costs. Test it before promotion. If it cannot pass the required load matrix with positive margins, stop that path and undertake the staged two-screen scroller proof with BUILD/LIVE retained. Keep soft-edge geometry a separate measured acceptance item.

Success is uninterrupted requested scroll cadence under the defined gameplay loads, correct sprite service and collisions, stable HUD/borders, preserved 55..246 terrain, and an independently reversible implementation—not simply fewer replay counters or a different multiplexer architecture.
