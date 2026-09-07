# Scroll hitch investigation — diagnosis and stop report

No production fix has been promoted. The investigation reproduced several causes,
proved useful bounded improvements, and found a legal render plan for which the
protected coarse-admission rule necessarily holds scrolling. The most developed
experimental candidate also retained a four-frame CPU-driven stall in real
scripted gameplay. It is not a completed hitch-free production solution.

## 1. Investigated revision

Branch `multicolour-with-turrets-experiment`, HEAD
`d96eb7cc60d681c9b703ac4c0fc776d7ef90ea6f`. The working tree started clean.
`AGENTS.md` was read. Current source, fresh assembly, and VICE traces were used;
older feasibility reports were not treated as current architecture.

## 2. Files changed

Only new diagnostics/reports:

- `docs/scroll-hitch-worklog.md`
- `docs/scroll-hitch-investigation.md`
- `tools/vice_scroll_hitch.py`
- `tools/check_scroll_hitch.py`
- `tools/make_scroll_hitch_ab.py`
- `tools/make_scroll_cpu_ab.py`
- `tools/vice_scroll_cpu_cases.py`

All tracked production source remains identical to HEAD. Disposable PRGs, code
overlays, full snapshots, traces, images and JSON results are under
`build/scroll-hitch/`, outside version control. No commits or pushes were made.

## 3. Exact current ordering

Initial presentation:

```
waitForGameFrame → publishTurretGlyphs → applyFineScroll
→ renderSprites(LIVE) → armFirstBatch → finishBackgroundCoarse
```

Each main iteration:

```
positionBackgroundTurrets
updateEnemyHitEffects             (including completed death/removal/score)
updatePlayerCombatEffects
updateObjects                    (movement, player HITSCAN, hostile projectiles)
updateEnemyFire
updateBackgroundTurrets          (aim, cadence, shared hostile allocation)
updatePlayerState                 (and game-over exit when required)
updateSpawner
updateBackgroundScroll
buildSortedObjectList → sortObjectsByY
buildInitialSpriteSnapshot(BUILD) → buildBatchSpriteSchedule(BUILD)
updateCycleDebug
prepareBackgroundCoarse
refreshScoreIfDirty
waitForGameFrame
publishTurretGlyphs → applyFineScroll → swapRenderPlans
renderSprites(LIVE) → armFirstBatch → finishBackgroundCoarse
```

`awardKillScore` updates binary score and marks `SCORE_DIRTY`. Decimal score
conversion runs **after coarse admission**, before the frame wait. Enemy score
is awarded when its death animation finishes; a destroyed turret awards
immediately. Player firing never allocates a player projectile.

IRQ frame zero establishes the physical epoch, resets the LIVE cursor and either
awaits main publication or replays LIVE. The unconditional display event and
sprite batches share that chain. `prepareBackgroundCoarse` sees the **current
physical frame's LIVE** `RASTER_BATCH_OFFSET/END`, while main has just built the
next plan. They are not next-BUILD cursors.

The pending flag is cleared, then admission tests outstanding LIVE work, raster
high, and raster `<184`. Admitted work waits until 160, saves physical row12,
copies upper rows and installs the incoming row. Fine0/lower finish publish at
the next presentation. A rejected transition retains fine7 and retries.

## 4–5. Proven causes and whether there is one cause

There are multiple causes:

1. **Late LIVE work at admission.** Latest-slot selection plus emitting the
   right edge of a reuse window recreates a late batch every frame. That batch
   can contain the player, not just an optional hostile projectile.
2. **Main CPU work misses admission even with no pending batch.** Measured
   contributors include redundant insertion-sort passes, repeated health-body
   clones, full clipping copies of mutable health art, and FREE decimal
   formatting. Sprite IRQ/collision work and DMA contribute elapsed time.
3. **Main misses a presentation boundary.** Baseline combined frame 3050 replays
   LIVE without incrementing `BG_COARSE_DEFERRED`. A deferral-only counter cannot
   account for every visible hold.

Every captured baseline deferral is accounted for by an actual taken guard
branch:45 outstanding-batch,14 raster-deadline,5 high-raster. This classifies all
reproduced deferrals; it does not assert that every possible human scenario has
been exercised.

## 6. A complete real-combat stall timeline

Baseline `hits-kills`, physical frames1943–1956. Each row is a coarse deferral.
The LIVE halves alternate, and their assignments finish in their own frames.

| Frame | Admission | LIVE | Cause | Outstanding compare / assignment |
|---:|---:|---:|---|---|
|1943|172:55|0|batch|208 / player 0, Y220|
|1944|174:45|8|batch|208 / player 0, Y220|
|1945|234:10|0|deadline|none; nonfatal enemy 2 hit|
|1946|173:28|8|batch|208 / player 0, Y220|
|1947|172:32|0|batch|208 / player 0, Y220|
|1948|170:49|8|batch|209 / hostile7, Y221|
|1949|193:08|0|batch|212 / hostile7, Y224; FREE refresh also runs|
|1950|173:41|8|batch|215 / hostile7, Y227|
|1951|172:27|0|batch|218 / hostile7, Y230|
|1952|171:31|8|batch|221 / hostile7, Y233|
|1953|258:25|0|high raster|none; hits on enemies 8 and 3|
|1954|172:27|8|batch|227 / hostile7, Y239|
|1955|171:11|0|batch|230 / hostile7, Y242|
|1956|156:11|8|batch|233 / hostile7, Y245|

Fourteen extra physical frames are approximately 280 ms of additional holding.
A single run can change cause while the scenery remains held.

## 7–8. Responsible objects and why the obstruction repeats

Hostile 7 in that timeline is allocation generation 8, created on frame 1934 by
**enemy 2**. The first blocking assignments are **logical player 0**. Full LIVE
payloads, selected slots, predecessor Y/release, object generations, current
logical states and allocation provenance are in each capture's `deferrals.json`.
Provenance is associated with BUILD/swap, so later reuse of a logical slot cannot
mislabel an older LIVE assignment.

These are new equivalent plans, not a batch accidentally carried through frame
zero. The projectile continues moving down while fine7 is held. Rebuilding and
swapping the next plan recreates the same ordering obstruction until slot
availability or object membership changes. The baseline real-combat stall has
zero unfinished-frame service failures.

## 9–11. Baseline stress results and distributions

Each case covers 6,000 consecutive physical frames and crosses at least 248 coarse
steps, or 2.48 complete 100-row stage circuits. Inputs use the real hitscan system.
Controlled interventions are described in the harness: no-kills restores health;
bullet-heavy accelerates enemy fire attempts without raising the cap; movement
and turret-heavy suppress subsequent wave spawning. Initial seeded objects are
allowed to leave. These are explicit tests, not claims of untouched human input.

| Case | Deferrals | Consecutive run lengths | Cause split B/D/H | Turret shots/opportunities |
|---|---:|---|---|---|
|Movement|0|—|0/0/0|0/1|
|Enemies, no player fire|1|1|0/1/0|0/1|
|Moving hitscan, no kills|37|19,9,4,3,2|27/6/4|14/27|
|Aimed hits and kills|17|14,2,1|14/2/1|9/13|
|Burst hits/explosions|6|3,2,1|4/2/0|5/7|
|Turret-heavy|0|—|0/0/0|19/27|
|Enemy-bullet-heavy|0|—|0/0/0|0/1|
|Combined movement/hitscan|3|2,1|0/3/0|12/18|

B=batch-not-consumed, D=raster deadline, H=high raster. Total 64 deferrals in 14
stall runs. Startup timer-expiry entries explain the single opportunity in cases
whose subsequent turret timers are pinned. Shots count increments after frame0.

Real damage was exercised: hits-kills628 health decrements/37 score awards,
explosions446/26, combined564/31. The no-kills case has 641 decrements and no awards.

## 12. Off-ramps evaluated

| Approach | Evidence / blocker |
|---|---|
|Retiming the same selected slots|Insufficient. Explosions1943/1944 selects slots unavailable until196/199, already beyond184.|
|Earliest reusable slot + earliest legal compare|Promising. Preserves assignments, masks, objects and collision visibility; controlled data below. Cannot advance a slot before its predecessor has finished.|
|Wait until the existing160 fetch window before admission|Matched test removes a reject at153 when the batch is serviced at156. All original guards still apply afterward. Production would also need an epoch-change rejection across the wait.|
|Correct insertion-sort outer-index progression|Stable output proved; substantial CPU saving. Does not remove every heavy-frame deadline failure.|
|Reuse health bodies / immutable clipped bodies / avoid copying hidden rows|Byte-exact in direct VICE tests; reduces CPU. The plain-sprite fast path must remain cheap.|
|Queue FREE conversion while coarse is pending|Removes a proven optional critical-path cost. Moving unbounded formatting after upper copy could instead cause a presentation overrun.|
|Coarse reservation in BUILD|Cannot create a free hardware slot where none exists; cannot by itself eliminate mandatory main CPU work.|
|Omit/delay a hostile render item|Not adopted. Invisible damaging projectiles, recurring flicker and visible/logical disagreement require a separate gameplay/presentation contract. The last item is sometimes the player.|
|Retire a batch without presenting it|Violates assignment-service requirements.|
|Early projectile despawn or tighter bullet/turret rules|Not adopted. Gameplay/visual change; current cap and firing rules retained.|
|Permit late IRQ work during upper copying|Requires a new proved IRQ/collision/copy budget and changing the protected gate. Not attempted.|

**A hard scheduling counterexample:** eight resident sprites at Y199 and a ninth
at Y235 are legal viewport positions. Every hardware slot is unavailable until
`199+24=223`. The ninth object's compare deadline is also `235−12=223`.
Coarse admission requires no outstanding batch **before 184**. No slot selection,
compare retiming or BUILD ordering can meet both requirements in that frame.

A fresh nine-object fixture measured compare 223, all assignments serviced, and
real coarse prepare at 160:00 returning at 160:47 with deferred incremented and
no finish pending. This is a legal synthetic counterexample, not a claim that
normal gameplay generated exactly that stationary layout. It establishes why a
scheduler-only guarantee for every allowed plan is impossible under the stated
guard. Changing the scroller, omitting presentation, or changing object lifetime
would exceed this investigation's safe production off-ramp.

## 13. Permanent fix decision

None. Production source and the normal PRG remain unchanged.

The final diagnostic candidate combines earlier slot/compare selection, stable
insertion-sort progression, health-body reuse, immutable-source clipping when
both health rows are hidden, copying only visible sprite rows, preserving the
plain-sprite fast path, and deferring optional FREE conversion on coarse frames.
It preserves the original admission gate/deadline, object limit 16, player 0,
hostile cap 3, BUILD/LIVE and all screen/charset architecture.

It still produced a real four-frame CPU stall at lean combined5975–5978:
admission185:15,203:46,251:23,199:02. Every batch was already serviced; active load
reached 10. Frame5977 includes a nonfatal enemy 2 hit. This has not met the requested
removal of the remaining visible hitch, so promoting it as the definitive fix
would overstate the evidence. Further bounded CPU improvements may exist; a
fundamental rewrite has not been proved necessary for ordinary gameplay.

## 14. Before/after evidence

Uncontrolled CPU changes alter CIA-driven wave and shooter choices. Their raw
counts describe different reachable histories and must not be presented as
matched gameplay. Separate deterministic choice tapes were therefore added to
both sides for controlled A/B runs; production randomness is untouched.

| Controlled6,000-frame case | Baseline | Candidate | Turret shots/opportunities, both |
|---|---|---|---|
|Combined|14 deferrals, runs8/6|0|12/18|
|Protected nonfatal combat|27, runs9/8/6/4|1 isolated batch reject|16/27|

Combined has identical 533 hits,32 awards,100 hostile spawn attempts and 249
allocations on both sides. Nonfatal combat has 104 hostile spawn attempts and 253
allocations on both sides. Its residual rejection is at 146 with compare 151,
before the mandatory160 window.

Matched single-frame interventions also isolate causes without changing earlier
wave history:

- FREE conversion removed only after combined 598: admission184:36 →157:31.
- Health-art routine removed only after 3505:253:12 →205:59; **still late**.
- Wait-before-guards after earliest-case 3958: batch serviced156:23, upper done271:22;
  the otherwise rejected transition succeeds.
- Corrected sort after trim-case 1942:203:50 →182:27; upper done285:33.
- Plain fast path after FREE-case 1270: admission moves below184; upper done286:46.

These removed-function tests are causal probes, not proposed feature removals.

## 15–17. Turret mitigation and projectile behaviour

The existing `SORTED_COUNT>=8` turret suppression remained enabled in all tested
runtime candidates. Its necessity after a future complete fix is **not proved**;
it must not be removed on this evidence. No extra projectile-count or wave-phase
rule was added, and the hostile cap remains 3.

In the controlled combined comparison,87 enemy projectile allocations occurred
on each side. Turret allocations also match (13 including startup, versus12
post-frame0 counter increments). Controlled nonfatal combat likewise has87 enemy
projectile allocations on each side. No candidate deliberately delays, hides,
despawns or changes the velocity/collision semantics of a projectile.

## 18–19. Cadence, raster service, sprite starts and replay

All completed6,000-frame captures have `frame_cycle_deltas == [19656]`.
This is physical cadence, not proof that main presents fresh state every frame.
Baseline combined has one replay at3050. Baseline controlled no-kills has 10
sprite-start assignment/mask misses: variable collision work inside
`applyLiveRasterBatch` delays writes past the12-line lead. Those are baseline
findings, not dismissed as terrain-oracle noise.

The candidate raster fixtures passed 17 maintained cases plus actual earliest75
and the nine-object residency case: zero service failures and sprite-start misses.
`close4` exercises eight batches. Parked-main fixtures intentionally replay LIVE.
Legacy fixture names early24/player37/overlap55/late243 now produce zero batches
because current viewport filtering excludes their objects; they do not validate
those numerical compares. Current generated reuse compares can begin at75 and
end at233 (`OBJECT_Y<=245`). Explicit out-of-viewport243 injection has not been
performed in this investigation.

Completed gameplay candidate raster checks and final pixel totals are summarized
in the validation appendix below. No missed service is excused by a terrain pass.

## 20. Validation scope

Fresh KickAssembler5.25 build passed at the investigated HEAD. All emulator
captures used fresh VICE processes; A/B gameplay restores the same complete
CPU/VIC/CIA snapshot. A 600-frame traced/plain comparison was byte-identical in
registers/clocks, matrix, engine state, background, raster state and turret state.

The final direct-routine audit passes 1,008 health/clip cases, including depth0,
source/HP/slot changes, and 340 stable-sort cases over0..16 objects and ties.
Measured CPU-only sort maxima: 7,396 baseline vs 3,302 optimized; maximum saving 4,094.
Health routine276..1300 cycles; clipping/plain42..1364. These direct-call costs
exclude VIC stealing and are not physical frame headroom claims.

Physical oracles cover full matrix, incoming/crossing buffers, all eight fine phases,
repeated coarse transitions, multiple stage circuits, fixed HUD/stock glyphs,
mixed hires/multicolour terrain, colour RAM and captured top/bottom edge motion.
Sprite rectangles are masked in the terrain oracle; direct sprite-byte tests and
raster deadline checks are separate. The changing FREE digits are structurally
validated rather than used as an exact same-frame pixel oracle.

A complete production acceptance run has **not** been claimed: no source fix was
promoted. Standalone lifecycle, viewport sweep, turret functional/kill timing,
and explicit overdue255→256 injection remain required before any future runtime
promotion. Existing scripts that hard-code the normal PRG were not pointed at a
scratch candidate by silently replacing `build/shooter.prg`.

## 21. Risks, limits, and exact continuation point

The strongest unresolved real case is `lean-candidate/combined`5975–5978.
All LIVE batches finish; main CPU still misses184. Investigate that budget before
combining more optimizations or claiming the scheduler solves every hitch.
Preserve the demonstrated hard counterexample and the original coarse guards.
The tested sort correction is a particularly small, independently useful result;
its eventual production version still needs the full acceptance suite.

Current `DEBUG_PLAYER_INVULNERABLE=1` prevents natural player death, although
collision capture/narrow phase still runs. The IRQ collision routine reads
logical object arrays, a historical exception to the desired LIVE-only rule;
this investigation did not silently change it. Gameplay disables CIA timer-A
IRQs while keeping the timer running for randomness. Artificial CIA re-enabling
was not part of these ordinary gameplay comparisons.

Historical early captures lacked measured final D010: the mistaken zero
placeholder was removed, so the raster oracle skips only that unavailable
hardware-register check. Later captures read real D010. Trace parsing was fixed
to keep the first CPU line following each trace header; monitor-stop disassembly
must not overwrite it. Header beam/stopwatch disagreement now fails instead of
being normalized. Refer to the worklog for full provenance and commands.

## 22. Human VICE/MiSTer review and repository state

No candidate is labeled ready for final human acceptance. After a bounded source
fix passes full regression, specifically exercise continuous movement/hitscan,
nonfatal hits, overlapping slow egress formations, a ninth/tenth hostile render
item, turret entry/exit, kills near coarse transitions, and the 50-frame FREE
refresh. Watch both fine7 holds and full presentation replays; verify sprite
visibility/collision consistency, health/clipping art, HUD and screen edges.

Working branch remains `multicolour-with-turrets-experiment`; tracked source is
unchanged, reports/tools are untracked, nothing committed or pushed. The normal
fresh-build PRG remains SHA-256:

```
955708c0bdb5868c26415466d51f4fa6c2287cedbe553e8c4a518183ea9191ad
```

See `scroll-hitch-worklog.md` for exact diagnostic variants and continuation.

## Validation appendix — final lean diagnostic, not production

Eight 6,000-frame cases,48,000 physical frames total. All have19,656-cycle cadence,
all eight fine phases, at least 249 coarse steps and at least 2.49 stage circuits.
B/D/H classification for the only four deferrals is 0/4/0. Baseline comparison
numbers are in section 9; these untaped runs may choose different CIA-driven waves.

| Case | Deferrals | Runs | Turret shots/opportunities | Coarse steps | Service/start/replay failures* | Matrix/pixel/HUD/MC/edge failures |
|---|---:|---|---|---:|---|---:|
|bullet-heavy|0|—|0/1|250|0/0/0|0|
|combined|4|4|12/18|249|0/0/0|0|
|enemy-nofire|0|—|0/1|250|0/0/0|0|
|explosions|0|—|7/12|250|0/0/0|0|
|fire-no-kills|0|—|17/27|250|0/0/0|0|
|hits-kills|0|—|7/12|250|0/0/0|0|
|movement|0|—|0/1|250|0/0/0|0|
|turret-heavy|0|—|19/27|250|0/0/0|0|

*Replay column counts actual replay frames, not a terrain-derived estimate.

Aggregate physical oracle checks: 2,844,216,500 background/HUD pixels, 245,719,040 HUD/separator positions, 69,830,558 edge-motion positions; 0 failures. These overlapping counts are different assertions, not distinct pixels.
