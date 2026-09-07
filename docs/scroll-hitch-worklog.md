# Remaining scroll hitch investigation

Current branch: multicolour-with-turrets-experiment. Started clean at
HEAD d96eb7cc60d681c9b703ac4c0fc776d7ef90ea6f. AGENTS.md read; no src/AGENTS.md
on disk. No commits/pushes authorized for this task. Current mitigation stays
on by default; player weapon is HITSCAN and never allocates a projectile.

Fresh KickAssembler5.25 build passes. Baseline saved under build/scroll-hitch:
baseline.prg / baseline.vs. PRG SHA256
955708c0bdb5868c26415466d51f4fa6c2287cedbe553e8c4a518183ea9191ad.
Protected memory map still0801..1e79, state2000..23f7, background2920..2c99,
copy/stage/HUD4000..5841, scheduler6000..634f, turrets8800..8edf, pools unchanged.

## Current source ordering (verified, not old documentation)
Initial game presentation: waitForGameFrame -> publishTurretGlyphs ->
applyFineScroll -> renderSprites(LIVE) -> armFirstBatch -> finishBackgroundCoarse.
Each BUILD iteration: positionBackgroundTurrets -> updateEnemyHitEffects
(explosions/death/health graphics) -> updatePlayerCombatEffects -> updateObjects
(player movement/hitscan damage, enemies and hostile projectiles) -> updateEnemyFire
-> updateBackgroundTurrets -> updatePlayerState -> updateSpawner ->
updateBackgroundScroll -> buildSortedObjectList -> sortObjectsByY ->
buildInitialSpriteSnapshot(BUILD) -> buildBatchSpriteSchedule(BUILD) ->
updateCycleDebug -> prepareBackgroundCoarse -> refreshScoreIfDirty ->
waitForGameFrame -> publishTurretGlyphs -> applyFineScroll -> swapRenderPlans ->
renderSprites(LIVE) -> armFirstBatch -> finishBackgroundCoarse -> next iteration.

awardKillScore updates binary score and SCORE_DIRTY only. refreshScoreIfDirty
renders after coarse admission and before wait. Some nearby source comments
still say 'frame start/next frame'; the CALL SITE above is authoritative.
FREE is sampled BEFORE both coarse work and deferred score conversion.

prepare checks pending, clears it, then tests RASTER_BATCH_OFFSET vs END.
Those are IRQ cursors for the CURRENT physical frame's LIVE plan (base0 or8).
They are not the just-completed next BUILD plan. BATCH_COUNT/RASTER are double
buffered by those same bases. startLiveRasterPlan initializes the cursor/end;
applyLiveRasterBatch increments it; frame0 either clears awaiting main publication
or replays LIVE and resets cursors. buildBatchSpriteSchedule changes BUILD only.
After outstanding-LIVE guard, high raster / line>=184 reject; admitted work
waits until160, saves crossingrow12, upper copy, incoming row install, fine0
pending lower finish. Deferral sets SCROLL_FRAME_COUNT=2; next BUILD retries
fine7, and following presentation may contain an equivalent newly built batch.

## Diagnostic weaknesses to replace
Existing vice_turret_stall_ab.py observes AFTER the frame, labels ANY batch_count>0
as 'batch-not-consumed', and sums total deferrals modulo256. It does not identify
the actual taken branch or LIVE assignment IDs at admission. It also samples
presentation iterations rather than explicitly every physical frame. Its counts
are useful evidence, not an exact cause oracle. Prior report claims observer
perturbation from admission breakpoints; validate a passive trace against an
identical initial emulator snapshot/control before drawing conclusions.

## Candidate to investigate, not yet implemented
Batch construction currently picks the latest reusable eligible slot, and emits
BATCH_RASTER = min(new object's Y-12), i.e. the right edge of a feasible window.
A slot may actually be free substantially earlier (old Y+24). Investigate earlier
publication inside the SAME proven reuse/deadline interval, preserving every
payload/slot first, before considering changes to slot selection. This can
potentially finish late OPTIONAL compares earlier without dropping sprites,
changing logical objects/collision semantics, or touching coarse guards/IRQ.
Need exact per-batch max release and full LOAD/CPU evidence; do not assume it
solves intervals whose earliest safe release itself exceeds coarse admission.

Next: develop passive exact-branch trace and per-deferral memory/ID capture;
prove repeatability/observer neutrality; run realistic cases from common snapshot.
No production changes yet. Owned initial VICE test port6580/session45301.

Passive observer validated:600 physical frames from identical start.vsf, with
tracepoints vs --plain, produced IDENTICAL registers/clocks,0400 matrix,2000
object/plan state, background, raster and turret snapshots on every frame.
Both recorded1deferral. The old stop-at-admission probe is not needed. VICE
trace checkpoint commands can dump RAM using semicolon-separated m commands
without stopping/advancing emulated time. New tools/vice_scroll_hitch.py traces
actual three branch PCs (asserted against baseline machine bytes), pending
context and defer context, main phase entries, assignments/masks, state writes,
hitscan, score, allocation, hostile fire and turret opportunities. Source remains
unchanged. Common snapshot contains CIA/VIC/CPU state; fresh process each case.

Eight6000-frame cases started: movement-only (spawn/turret fire suppressed),
enemy/no-player-fire (turret fire suppressed), fire-no-kills (restore legal6HP
between physical frames), aimed real hits/kills, burst-fire explosions/despawns,
turret-heavy (spawns suppressed), bullet-heavy (enemy fire timer1; cap unchanged),
combined moving+hitscan. Baseline movement/input timing is physical-frame-based.
Interventions are explicit in harness; do not describe controlled cases as
unmodified gameplay. Aimed cases steer with joystick, no player teleport.

First measured additional cause: observer combined frame599 has NO pending LIVE
batch, no hit, no kill, no allocation; prepare enters184:36 and takes deadline
branch. updateCycleDebug entered152:39. Its every50-frame displayCycleMinimum
repeated-subtraction conversion sits BEFORE coarse admission. This is separate
from the already-relocated score conversion. Need isolate this CPU contributor,
not attribute the frame to hitscan merely because fire is held.

Completed movement6000: zero deferrals,250coarse steps. Initial seeded enemies
were allowed to leave; 'movement' suppresses further spawning/turret shots, not
that startup population (3 allocations/3 despawns captured). Explosions6000:
6deferrals [3,2,1],4batch +2deadline,249coarse steps,446real health decrements,
26score awards,5turret shots/7timer-expiry entries. Longest stall:
1943 LIVE0, pendingcompare229; hostile ID4 generation14 born1891 from enemy2,
LIVEY241; reuses slot6 previously hostile ID8/Y172, release196. Admission201.
1944 LIVE8, NEW equivalent compare232; same ID4 LIVEY244, ID8 release199;
admission183.1945 no pending batch, deadline229 after a real hit on enemy6.
Thus even a single stall can change cause; the late enemy projectile is NOT
created by the hitscan weapon, and the IRQ did not carry an unfinished batch.
Retiming SAME selected slot cannot put release196/199 before184. Earliest-slot
selection may use earlier departed enemies instead; must measure it.

Diagnostic A/B overlays only (tools/make_scroll_hitch_ab.py, guarded scratch7000,
7100,7e10; src unchanged): (1) same-slot earliest legal compare=max slot release;
(2) earliest reusable slot + earliest compare. Both preserve +24 release,
Y-12 deadline, all payloads/masks and every coarse/IRQ guard. Address-preserving
helpers add conservative CPU overhead (~16 per batch + ~30 per assignment).
Experiments6000frames combined/explosions launched for both variants. Common
snapshot identical, but changed CPU timing can change CIA-driven wave selection;
report this limitation rather than claiming identical later wave histories.

All eight baseline6000-frame captures completed. Exact branch counts:
movement0; enemy-nofire1(deadline); turret-heavy0(19shots); bullet-heavy0;
combined3(deadline, runs2/1); explosions6(batch4/deadline2, runs3/2/1);
hits-kills17(batch14/deadline2/high1, runs14/2/1);
fire-no-kills37(batch27/deadline6/high4, runs19/9/4/3/2).
All>=248 coarse steps (>=2.48 stage circuits). Player fire remains hitscan.
Aimed real hits-kills longest1943..1956 starts with reassigned PLAYER ID0/Y220
(compare208) then switches to enemy-fired hostile ID7/Y221..245, not a player
projectile. All14 deferrals have alternating LIVE base0/8 and physically
serviced batches each epoch. Two intervening frames are CPU lateness, not batch.

Additional CPU evidence: combined3506 has two non-fatal hits on enemy7, admission
253, no outstanding batch. Hits-kills1953 has hits on two enemies and admission
258. updateEnemyHealthSprite copies64bytes from base sprite on EVERY nonfatal
hit, including the second cannon hitting the same already-private sprite. This
cost coexists with sorting, full straddler bitmap builds and IRQ/DMA. Do not
assume all deadline frames are health work: some have no hits, and FREE formatting
is separately proven by phase timing. Combined3505 enters183 but crosses the
actual compare deadline by the time its safety check executes.

Diagnostic correction: first capture harness incorrectly supplied a placeholder
physical_x_msb=0. Removed this UNMEASURED field from completed frames.json files,
so existing raster oracle skips only that unavailable hardware-register check;
it still verifies LIVE masks and actual assignment/mask timings. Future captures
read real D010. Do not claim old captures measured final D010. Baseline protected
fire-no-kills also exposes actual late sprite assignments/masks (e.g1468..1471),
not just the old placeholder errors: IRQ applyLiveRasterBatch starts225..233,
then collision narrow-phase work delays Y writes to244..250. Current IRQ's
checkCapturedPlayerCollision reads logical OBJECT arrays (historical exception
to the desired LIVE-only rule); payload writes remain LIVE. Record this current
source fact rather than silently rewriting collision ownership.

Exact FREE isolation running: restore same start snapshot, identical inputs
through frame598; only then replace displayCycleMinimum entry with RTS in the
emulator for frame599. Production source untouched. This tests cause without
letting earlier format changes alter CIA-derived wave choices.

## Completed A/B and causal isolations (continuation)
All eight baseline 6000-frame traces complete, totals64 deferrals:45 batch,
14 deadline,5 high. Real hits-kills has37 awards/628 hits; combined31/564;
explosions26/446. These are actual hitscan damage/awards, not projectile guesses.
All captures have19656-cycle physical cadence and >=2.48 stage circuits.

Matched FREE isolation: byte-identical state through combined598; replace ONLY
entry displayCycleMinimum with RTS after598. At599 prepare changes184:36 ->
157:31 and the defer disappears (1 ->0 over601frames). This proves optional
FREE decimal formatting itself can cause a hitch. Not a production change.
Matched health isolation: identical through3505; replace updateEnemyHealthSprite
with RTS after3505. Two nonfatal enemy7 hits still occur; prepare3506 changes
253:12 ->205:59, STILL late. Bitmap work contributes ~47 lines but is not the
sole cause. Simply skipping redundant clones cannot alone guarantee admission.

Another holding path: combined3049 lower finish99:30, updateObjects110:22,
two hits125:15/162:30, enemy fire210:8, initial snapshot239:30, batch build279:34,
updateCycleDebug290:32 (50-frame FREE conversion). Main crosses frame0; IRQ
replays LIVE on3050. Prepare18:24 has no coarse pending, wait18:56 misses that
frame's presentation. No coarse-deferred increment accompanies this visible hold.
FREE alone is therefore insufficient; total main-work and replay matter.

Trace parser corrected: VICE sometimes prints disassembly stopwatch after monitor
resume, although trace-header raster/cycle is from the event. Retain raw_clock
and anchor header beam to the most recent matching physical epoch. Report
trace_clock_adjustments. Counter totals unchanged. Reparse other completed
captures with current checker before final timing reports (combined reparsed).

A/B6000 results (disposable7000/7100 helpers only):
- Same-slot ASAP: combined3 [2,1], explosions6 [3,2,1]; insufficient.
- Earliest-slot ASAP: combined3 [2,1], explosions5 [3,1,1], all deadline;
  hits-kills17 ->1 [1], only batch; fire-no-kills37 ->20 [8,5,4,3],
  deadline18/high2. Turret shots hits-kills9 ->10 (13opps both), no-kills14 ->17
  (27opps both). Enemy kills may diverge because CPU timing changes CIA randomness.
  No objects or assignment payloads deliberately omitted; existing turret guard on.
Remaining earliest hits-kills3959: admission153, compare155, hostile8/Y244,
reuses slot0 after enemy1/Y131 (release155). Original guard checks BEFORE its
mandatory wait-until160 and rejects a batch that may complete during that wait.
Next diagnostic: wait until160 before unchanged batch/high/184 guards; prove
it helps without starting copy while any IRQ work remains or after184.

Existing raster checker on baseline8 / ASAP2 / earliest4 captures:
all service failures0. Sprite-start misses0 except baseline protected no-kills10
(actual variable collision work in IRQ). Earliest no-kills removes those misses.
Combined has1 replay in all3variants; all other tested cases0replay. Old captures
skip UNMEASURED final D010 only (placeholder removed); future captures read it.
No full pixel regression for overlays yet; no production source changed.

Continuation: wait-until160 before the unchanged gates removes batch causes in
long runs, but does NOT establish a complete fix. earliest-asap-wait6000:
hits-kills14 defers [7,5,1,1] (deadline13/high1), combined9 [9] (deadline8/high1).
Wave/kill sequences differ (CIA timing), so do not interpret this as a matched
regression/improvement. Matched wait-only3958 intervention on earliest-asap is
running. Production unchanged. A precise parser bug was found and fixed:
multiple .C disassembly lines after the last trace were overwriting that trace's
CPU/clock (monitor stop entries). Keep ONLY the first .C after each trace header.
Do NOT normalize timestamps. Header beam/CPU stopwatch now agree exactly;
nonzero disagreement fails the checker. Reparse all captures again. Previous
phase timings and deferral counts confirmed in combined/wait cases.

Next bounded CPU experiment: health sprite's only mutable bytes are rows0/1.
For a top-straddler clipping >=2 rows, those bytes are entirely hidden. Using
OBJECT_BASE_SPRITE as its clipping source/cache key is pixel-equivalent and
permits the existing immutable-source incremental clipping cache. At depth1 keep
the actual mutable private source/full rebuild. No new cache arrays necessary;
original base pointer distinguishes allocation/art changes. Also test avoiding
redundant base64byte clone when OBJECT_SPRITE already points to that object's
private health slot. All base-pointer writers inspected: spawn initializes it;
it is immutable for an enemy lifetime. Prototype only in diagnostic scratch,
then matched bitmap checks and long VICE comparison before any source promotion.

Matched wait result complete: earliest-asap vs wait-isolation state byte-identical
through3958. On3959 prepare enters153:56, IRQ batch begins156:23, guarded upper
work finishes271:22. Deferral1 ->0 for that matched segment (3962frames). The
ordering improvement is causally valid; long-run timing changes still expose
other workloads and are not a universal cure.

CPU diagnostics added (src STILL unchanged): tools/make_scroll_cpu_ab.py builds
relocated routine copies at7300/7500 (scratch7e12). Health-cache uses CMP/PHP before
existing destination setup to skip a clone only if already using that logical
slot's private bitmap. Clip-source normalizes health art to immutable base only
at depth>=2; mutable depth1 retains original behaviour. Actual constant MIN_Y=71,
not72 (some source comments stale); body pixels start Y+1. No logical pointer is
changed by normalization. Preserve clip budget8, BUILD half and pool addresses.
New tools/vice_scroll_cpu_cases.py verified960 cases (logical1/7/15, pool0/7/8/15,
two base artworks, depths20..1..20, HP changes/source changes). Exact health64bytes,
clip63bytes, published pointer, and logical pointer all pass. No display/IRQs
in that direct-call test; physical pixel tests remain mandatory.

schedule-cpu (earliest-asap + two CPU changes),6000 each:
combined1[1] deadline,12shots/18opps,47awards; hits-kills3[3] deadline,
5shots/8opps,51awards; explosions1[1] deadline,6shots/10opps,37awards;
controlled no-kills13[5,4,2,1,1] deadline,17shots/27opps. Main residuals include
brand-new straddlers (Y51/53): full copy63 followed by blank60 wastes most copy.
--trim variant blanks hidden prefix then copies only visible suffix, no changed
pixels or budget;960 additional direct cases pass. Measured helper CPU health
276..1300, clip326..1368 (prior clip max1938). These include JSR/SEI/direct-call
harness timing, exclude VIC stealing. New long --pixels cases running combined,
no-kills, hits-kills, explosions; captures also dump actual charset/CRAM/pools.
No runtime promotion until their acceptance evidence supports it.

All older exact-branch logs reparsed with first-CPU-line fix. Clock/header
mismatches zero, counters agree; no normalization used. Earlier incorrect
normalization explanation is superseded by the parser fix above. Larger overlay
writes now chunk64bytes to respect VICE monitor input-line limit.

Important additional root of CPU lateness: sortObjectsByY inserts correctly but
!next increments the INSERTION index twice, rather than resuming from the original
outer input index. It repeatedly visits the already sorted prefix. For trim
combined1943, current49 vs ordinary27 comparisons produce the SAME stable list.
Matched intervention after1942 (all state identical before): only corrected sort
at7800; prepare203:50 ->182:27; safe upper completes285:33, no defer. Direct VICE
340 shuffled/tied lists covering0..16 entries verify stable Python-sorted output
for old/new routines; maximum measured cost7396 ->3302 CPUcycles, max saving4094.
No sorter architecture change: preserve the outer index in one byte, restore it
at !next, increment once. This is a bounded insertion-sort correction.

Long schedule-cpu-trim-sort runs so far: combined6000 has1 isolated deadline
(frame3599), hits-kills6000 has0. Combined3599 has no hits, batch89 already fully
served; updateCycleDebug169:30 ->prepare193:29 on its50-frame FREE refresh.
Next bounded test queues the optional FREE refresh across a pending coarse
transition, preserving its rolling minimum/counter until it can display. Do not
blindly move formatting after upper copy (that could create frame overrun).

Previous trim-without-sort combined6000 had20 deferrals [19,1], all CPU lateness;
all batches were already serviced. This is a useful alternate real-gameplay
history, NOT evidence trimming costs more. CIA random choices change with CPU
timing. Its full matrix/pixel/HUD/MC/edge oracle passed:353108173 background
pixel checks,30714880 HUD/separator,8690010 edge-motion,0 mismatches. Preserved
coarse guards turn overload into a clean hold as intended. No source promotion.

Controlled random-tape A/B now isolates CPU changes from CIA sampling. Separate
wave and enemy-shooter counters index one shuffled256byte tape (seed19656),
helpers7b00/7b40,tape7c00,counters7e14/15,scratch7e17. ONLY diagnostic builds use
this; production random selection unchanged. Every original gate/cap retained.
6000 combined: baseline14 [8,6] (batch12/deadline1/high1) -> candidate0;
BOTH533hits/32awards/12turretshots/18opps/100hostile attempts/249allocations.
6000 protected no-kills:27 [9,8,6,4] ->1 [1], shots16/opps27/hostile attempts104
identical. Remaining no-kills4271 enters146, compare151 (hostile7/Y243, release151)
not yet served: same pre160 admission issue already proven by matched wait test.

Uncontrolled full CPU+sort+FREE variant still finds an8-frame pure-CPU hold with
a different wave history. Do not call that final. The clipping prototype paid
source-normalization overhead even for wholly visible sprites. --lean retains
the ORIGINAL Y>=71 plain fast path and normalizes only actual straddlers.
This removes unnecessary per-object overhead without changing a byte of sprite
output. New eight6000-frame --pixels cases running (ports6582/6583), plus a matched
lean-only intervention after1270 and a depth0-inclusive direct bitmap/sort audit.

All17 existing parked-main raster fixtures passed candidate PRG,16physical
frames/all8phases each:0service failures/0sprite-start misses/exact19656. close4
really produced8batches; clip_boundary2. CAUTION: legacy names early24/player37/
overlap55/late243 currently produce ZERO batches due current viewport filtering.
They do not prove those numerical compares anymore. Valid viewport95/233 cases
and explicit injected overdue/replay testing still needed for full acceptance.
Candidate routine overlays only; src remains identical to HEAD. All trim and
sort pixel captures completed so far pass matrix/incoming/crossing/HUD/MC/edge
oracle. Full runtime/lifecycle/turret acceptance not yet run for a source fix.

Potential source promotion must keep all runtime safety guards. Waiting for the
existing160 fetch window before checking outstanding work is supported by matched
data, but a production implementation should also detect a physical epoch change
across the wait instead of assuming interrupt latency cannot span frame0. One
main-owned byte can remember RASTER_FRAME low; changed epoch defers. No copy
starts while any LIVE batch remains, with high raster set, or at/after184.

## Stop / handoff status — 2026-09-07

Full report: docs/scroll-hitch-investigation.md (requested22-point report plus
validation appendix). NO production source changes, commits or pushes. Normal
build/shooter.prg still baseline SHA955708c0...9191ad. Seven new untracked files:
two reports and five diagnostic tools. All completed authoritative captures used
fresh VICE. Diagnostic helpers are not a final production implementation.

Final lean diagnostic completed all eight6000-frame cases (48000physicalframes):
combined4 deferrals [4], all deadline; other seven0. All eight raster oracles:
0 service failures,0 sprite-start misses,0 replay frames; cadence[19656]. All eight
fixed-HUD/MC/matrix/incoming/crossing/edge oracles pass, with2,844,216,500 aggregate
pixel checks,245,719,040 HUD/separator assertions,69,830,558 edge-motion assertions
(overlapping assertion counts). Direct tests1008 health/clip including depth0 +
340 stable sorts pass. Latest plain fast path matched-only isolation was byte-
identical through1270 and admits1271 at182:51, upper finishes286:46.

Unresolved actual normal-play case: lean-candidate/combined5975..5978, ten active
objects, all batches DONE, admission185:15,203:46,251:23,199:02. One nonfatal enemy2
hit on5977. This fails the complete hitch-removal objective; do not promote the
candidate merely because most counters/tests improved.

Hard scheduler-only counterexample measured in fresh VICE:
8initial objectsY199, ninthY235 => every slot release223, deadline223; all positions
are legal. Candidate correctly emits223 and services every assignment. Real
prepare at160:00 exits160:47, increments deferred, finish_pending0. No slot choice
or compare retiming can make223 occur before the protected184 cutoff. Holding
such a layout recreates the obstruction. It is a synthetic legal counterexample,
not an assertion this precise stationary layout occurred in human gameplay.
Without relaxing that gate/allowing IRQ work during copy or changing presentation/
object lifetime, an unconditional no-stall guarantee for all legal plans is not
possible. Preserve the proven scroller and stop short of that architectural change.

Candidate synthetic tests:17 existing fixtures + earliest75 + nine_late_residency,
16physicalframes/allphases each, all0service/start failures. Parked-main replay is
intentional. earliest75 used[51]*8+[87]*8; nine residency used[199]*8+[235], with
--prepare-at160. Both injected by replacing vice_raster_cases.CASES in an imported
Python module before main; no maintained source/test fixture silently changed.
Current legacy early24/player37/overlap55/late243 fixtures yield0batches due current
viewport. Do not claim they cover those compares. Explicit243/overdue255->256 and
full lifecycle/turret/viewport acceptance remain future promotion work.

Last diagnostic fixes: first CPU line only per trace; no timestamp normalization.
Allocation provenance snapshots at BUILD/swap prevent later logical reuse from
mislabeling LIVE assignments. Exact fatal-enemy store PC and turret-award phase
track kills separately from later score awards; SCORE_DIRTY writes recorded.
Each final hitch audit also checks player0/type/active, distinctLIVE/BUILD{0,8},
shared hostile count/cap3. Baseline8, controlled tape4 and final lean8 all rechecked.

Generators now refuse wrong baseline PRG hash; CPU generator also requires the
investigated HEAD and unchanged src/main.asm/variables.asm. Rebuild commands:
  python3 tools/make_scroll_hitch_ab.py
  python3 tools/make_scroll_cpu_ab.py --trim --sort --free-defer --lean
Normal runtime remains unchanged unless --overlay is explicitly supplied to the
capture harness. --pixels captures PNG, glyphs, CRAM, sprite pools and static stage
assets; use check_fixed_hud_capture.py with Pillow available through
PYTHONPATH=/private/tmp/hud-study/python-deps. See case.json in every capture for
snapshot/overlay inputs. All artifacts remain under build/scroll-hitch.

Exact next step if this task resumes: do NOT redo Phase1 or generic no-fire probes.
Read the report, inspect lean combined5975..5978 deferrals/frame-activity and full
captured state; profile its remaining pre184 main CPU cost. Keep choices fixed
with random-tape.json for A/B, or use --initial-overlay plus delayed --overlay-at-
frame for a matched intervention. Do not add turret suppression or claim a
scheduler-only cure. The small sort progression correction is independently
valuable but any production promotion must first run the complete requested
acceptance suite; it does not establish universal uninterrupted scrolling.
