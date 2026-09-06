# Background turret prototype — active worklog

## Status / next step
Analysis completed; baseline freshly built, no production changes yet. Capture
baseline normal gameplay/FREE and raster timing, then implement the bounded
private-character model below. Leave bg-turret-test uncommitted for playtest.

## Baseline
- Read root AGENTS.md. No src/AGENTS.md exists on disk.
- Clean bg-turret-test tracking origin/bg-turret-test, HEAD a67d329.
- Current source, not earlier HUD-session edits, is authoritative. Accepted
  clipping/HUD/FREE/bas-relief terrain commits are protected.
- Fresh KickAssembler5.25 build passes all guards. Baseline copies:
  build/bg-turret-test/baseline.{prg,vs}. SHA256: b36264f1983ad1b1e55e7fe444f7111b0bbcdca934651bf9f7c64fa83ab07e94.
- Layout: main080e..1e35; state2000..23f6; data2400..290e;
  background control2920..2c3c; health3000..33ff; clipping3400..37ff;
  charset3800..3fff; copy/stage/HUD4000..5841; scheduler6000..634f.
- Screen0400, D018 unchanged, terrain160..199 at3d00..3e3f. Namespace200..223
  is free; HUD128..145/reserve146..159, diagnostic224/225, stars240..251.
- 16 metatiles,25x10 stage IDs,100 character rows. Do not change limits/decoder.
- RSEL aperture55..246; fixed HUD55..62, separator63..70, terrain71..246.
- Main SCROLL_ROW is stage row at matrixrow1; physical terrain pixel top is
  64+presentedFine+8*(matrixRow-1). Fine7->0 decrements stage origin modulo100.
  During pending coarse, upper physical rows already contain next origin,
  lower rows retain old origin; finish restores physical crossing row12->13.
- Coarse guard: no remaining LIVE batches, start before184, wait until160;
  upper old1..11->2..12; lower old13..22->14..23. No copy body changes allowed.
- Baseline includes accepted synthetic-overload raster71..73 straddler-DMA
  transients. Compare signatures, do not attribute them blindly to turrets.
- Enemy bullets: shared cap3, generic allocator starts1, TYPE_ENEMY_BULLET,
  velocityY+3, Xvelocity -2..+2, removes atY250/side exits. Player uses dual
  hitscan; nearest eligible enemy by greatest Y above player currently wins.
- FREE is rolling50-BUILD-frame minimum, not instantaneous remaining cycles;
  current WAVE_GAP=150. Preserve wave source/cadence; use same capture settings.

## Chosen model / safety derivation
Three explicit character-coordinate placements (column0..38,row0..99), each
2x2 characters/16x16 pixels. Separate per-game health, aim, hit/fire timers,
screen-position and desired/shown-glyph state. No logical/VIC slot for bodies.
Tables are editor-friendly placements, independent of metatile ID. A small
assembler-generated row lookup identifies a placement's two world rows.
Prototype placement guard: no two bodies share a world character row; wrap of
a body's bottom row is modulo100. Distribution keeps runtime updates modest.

Allocate four private glyphs per instance: codes200..211,3e40..3e9f. Six simple
aim templates (up/down x left/centre/right) plus a hit template live in CPU RAM,
not extra charset slots. Cache the underlying four glyph bitmaps/instance at
new-game initialization (96 bytes total, not a screen or terrain shadow).
Alive glyphs show a small solid mount; destroyed glyphs reproduce that cached
terrain exactly. Death is permanent until new-game reset, including stage wrap.

Keep decodeStageCharacterRow untouched and BG_INCOMING_ROW pure terrain. Add
an explicit tail hook after copyIncomingRowToScreen in renderStageRowToScreen:
only initial fill / safely hidden incomingrow1 receives the two private codes
for a world row. No ordinary runtime writes to turret screen cells. Existing
coarse copies move stable world codes exactly once, so no stale-art trail or
restoration race. BG_CROSSING_ROW intentionally preserves these physical world
codes just like any other character; it is never reinterpreted as raw terrain
or used as an underlay cache. Underlying stage data remains authoritative.

Dynamic art changes occur through ONE bounded glyph publication per presented
frame, immediately after waitForGameFrame, before initial sprites/terrain
fetches. Main computes complete desired-style bytes; IRQ reads no turret state.
An unrolled32-byte copy costs roughly400 CPU cycles, plus small selection/
pointer setup. Publish at most one dirty turret/frame; extra requests queue.
New-game init can publish all three before gameplay starts. Measure actual
entry/exit and initial-sprite deadlines (straddlers can startY51). No new IRQ,
D011/D018 change, scroller redesign or hardware sprite reservation.

The row-install hook must be O(1), ~40 cycles worst (one lookup and two stores),
not scan all placements inside coarse prepare. Re-measure pure coarse CPU cost
for ALL100 origins; preserve the existing6000-cycle copy budget/184 cutoff.
If it cannot fit, stop or reduce hook cost rather than alter protected timing.

Screen Y derives from (worldRow-SCROLL_ROW) modulo100 and presented fine;
relative99 represents the partially visible top-wrap body at56+fine. Graphics
enter/leave naturally through the existing crop. Combat/firing uses a fully
visible body and an additional top/bottom firing margin. Turrets point in six
coarse directions, but this first prototype fires only while the player is
below: existing projectiles deliberately remain downward-moving. No projectile
movement/cap changes. Reuse a common explicit-origin bullet initializer rather
than fake a turret enemy in a logical object slot.

Extend hitscan nearest-target selection with a turret tag, preserving enemy
selection and damage routines. Turret health/hit feedback/destruction uses the
same player volley. Do not make all rays damage both foreground enemy and
background turret: select the nearest eligible target.

## Validation plan
Fresh baseline normal capture + fixed-HUD/raster oracles and FREE distribution.
Then capture mutable private glyphs/state and adapt the independent oracle:
raw incoming buffer stays raw; matrix/crossing expectations include stable
placement codes; private glyphs independently match aim/hit/underlay data.
Check actual physical pixels and both edge-motion bands, excluding only the
changed turret glyph pixels from motion comparison when style changes (still
check them absolutely). Test hitscan ordering, cap/full-pool failures, firing,
damage/death near transitions, full stage wraps/dead persistence and new-game
reset. Run normal, long, scheduler cases, lifecycle and matched stress. Record
FREE separately for visibility/firing and correlate deferrals. Human VICE
acceptance remains required; no commit/push.

## Structural implementation v1
Implemented src/background_turrets.asm at8800..8edf (1760 allocated bytes,
including alignment): three placements (10,99),(28,32),(6,65), codes200..211;
96-byte original-glyph cache; six aim templates + hit template. Positions,
health3,100-update firing timer,4-update hit feedback, persistent death, nearest
hitscan target tags, existing kill reward. Existing bullet initializer now has
an explicit-origin entry and enforces the unchanged cap3. Turrets fire only
below-player shots with entry/exit margin, preserving projectile movement.

Main hooks: initialize after terrain charset load; position before hitscan;
update after existing enemy fire; publish at most one dirty32-byte glyph image
at frame start; tail-install codes after raw incoming-row copy. No IRQ/scheduler,
coarse body/cutoff, metatile decoder, stage data, health/clip pool changes.
The glyph staging-buffer idea was simplified: main publishes desired-style
bytes; the bounded frame-start routine copies directly from immutable templates
or the96-byte underlay cache. No second glyph-image buffer is needed.

Memory: main end1e5f (+42), background control end2c41 (+5), other protected
segments unchanged. New module8800..8edf avoids existing test scratch7000/7f00
and trajectory logs8000..87ff. Build guards pass, NMOS branches in range.
Pure coarse CPU test now enumerates actual stage size (100, previously hard80):
5881..5928 cycles including callerJSR, still below6000. Source copy bodies and
admission remain unchanged. Capture/oracle extended for stable world codes,
raw incoming buffer, private glyph bytes, preserved underlay and absolute pixels.

Baseline1800 normal frames: both oracles pass,74 coarse transitions, all8 phases,
19656 cadence, no deferrals, max8 active logical objects. FREE summary: {'hud_nonzero_min': 2394, 'hud_median': 5607, 'hud_max': 11466, 'sample_min': 2394, 'sample_median': 12348.0, 'sample_max': 17325}.
Current run build/bg-turret-test/normal-v1 is900 physical frames. Next: run its
oracles, inspect turret pixels, then exercise targeted hits/caps/death/wrap and
long/lifecycle/stress comparisons. Nothing committed; human review not ready.

Normal-v1 completed:900 physical frames, all8 phases,37 coarse transitions;
fixed-HUD/matrix/raw-incoming/crossing/private-glyph/pixel/edge oracle passes;
raster oracle passes, no service/start/mask failures,44 reassigned sprites.
Three real turret bullets fired, down-right then up-right aim observed. No
uncontrolled player hits occurred. Six coarse deferrals versus baseline zero;
RNG/load differs (max9 objects versus8), so this is not a matched cost claim.
Added optional --turret-playtest capture input: align real cannons at turret0
near fine7/Y112 and turret2 near bottomY224, then leave dead state untouched
through wrapping. Next run long physical capture, targeted function/cap tests,
lifecycle/new-game reset and scheduler regression cases.

Function probes passed45 checks including all100 origins x8 fine phases x3
positions, nearest hitscan/enemy ties, ninth-X-bit bounds/aim, health3->0,
one kill reward, exact destroyed underlay bytes, shared cap3/full pool rejection,
bullet despawn and new-game reset. No body allocation. CPU body timings:
position120..159; turret update126..522 including actual shot; glyph publish
469..503; aim59..74. Normal measured dirty publication entry raster4, exit11..12,
463..497cycles to pre-RTS label. Main presentation7..31, lower finish7..99.
Normal FREE: HUD min1575, median6835.5; visible sample median11844, offscreen12411,
three firing samples7623..11592. These include different background/wave work,
not isolated turret cost. Existing baseline HUD min2394/median5607.
All17 scheduler cases x16 frames/all8 phases passed assignment/start/mask oracle.
Lifecycle passed death/respawn/game-over/menu/restart, confirmed turret death
survives respawn and all3 health reset on new game, CIA/KERNAL lifecycle intact.
Long-v1 captured5400frames: turret0 killed using real cannons frame198/Y122 after
fine7 attack frame189; turret2 attack began too late(Y231), leaving before third
hit, then died on next entry. This exposes a TEST sequencing issue: begin turret2
attack atY224 without waiting until fine7, rerun to cover death just before exit.
Long-v1 pixel/raster oracles running; no production correction indicated yet.

Long-v1 raster oracle:5400frames, exact19656, zero service/start/mask failures,
max9 objects/1batch. Terrain oracle:224transitions/2.24circuits,5deferrals, one
failure confined to score digit pixels on a kill frame3273. Captured pixels show
previous score while screen RAM has the new score: existing awardKillScore
updates after row0's fetch. Oracle now permits exactly the complete previous
score ONLY on the score-change frame, still checks every HUD pixel, and reports
such frames explicitly. No score-area masking or production HUD changes.
Long-v2 repeats5400 with earlier bottom-exit attack. Matched synthetic1400frame
stress baseline/prototype starting; source WAVE_GAP remains150.

Long-v2 is authoritative normal/destruction run:5400frames,224 coarse transitions,
2.24 full stage circuits, all8 fine phases, exact19656 cycles,3 total safe coarse
holds, no replay frames. Both fixed-HUD/pixel and raster oracles PASS:318,931,753
pixel checks,27,642,880 HUD/separator checks,7,633,693 edge-motion checks; zero
matrix/incoming/crossing/charset errors, zero assignment/start/mask failures.
Real turret0 cannon death frame198/Y122, turret2 death frame1332/Y227 before
bottom exit. Captured hit flash for both; dead reentries[2,0,1], no resurrection.
Dedicated turret capture oracle checks all captured positions, persistent health,
slot0 identity and exact shared bullet count/cap. PASS;10 turret shots observed.
Long-v2 FREE: HUD min4473/median7308/max11907; live visible samples min4473,
median11466; firing samples min9324/median10867.5/max16254; offscreen-or-dead
median11970. Different waves/input make these representative, not matched deltas.
Worst normal FREE across900+5400 runs1575. No sustained normal scroll holds.

Worst-index dirty glyph + eight early clipped sprites probe PASS:497cycles to
pre-RTS label, real presentation completes raster29, before earliest Y51 DMA.
No main/IRQ ordering changes required. Synthetic stress comparison and physical
clip-sweep are the remaining checks before final build/source review.

## Final automated handoff — ready for human VICE playtest

Production source is the same binary tested above; final fresh KickAssembler5.25
build and Python compilation pass. `git diff --check` passes. Branch remains
`bg-turret-test`, HEAD a67d329; nothing staged, committed or pushed. The original
baseline was clean and no unrelated user edits were removed. All six owned
capture VICE instances have been closed. Human acceptance is still pending.

### Architecture and data
- Three software turrets, each a16x16 background body; no logical/VIC body slot.
- Explicit placement lists in background_turrets.asm: character columns
  [10,28,6], world character rows[99,32,65]. Map width40/height100; the bottom
  half of the row99 placement wraps into row0. Sprite-space X=24+column*8.
- Runtime44 bytes: per-instance health, visibility,9-bit X/Y, aim, fire/hit
  timers, desired/shown style, plus scratch/counters/shared bullet origin.
- Six aim orientations use9-bit dx and24px horizontal deadband; dy selects
  up/down. Upward aiming is visible, but this prototype holds fire when the
  player is above: existing bullets intentionally retain +3 vertical speed.
- About100 eligible updates between attempts; only fire at turretY88..200 with
  player more than24px below, alive. Cap3 and slot1..15 allocation unchanged;
  failure consumes the attempted cadence and causes no allocation/state leak.
- Body combat eligibility Y72..231 (fully visible). Partial entry/exit graphics
  follow normal terrain crop. Nearest upward cannon ray selects either original
  enemy or turret; enemy wins equal-origin Y. Turret bounds16px, health3, brief
  hit glyph, single existing100-point kill reward. Dead state persists until
  next new game; respawn does not resurrect it.

### Repaint / scrolling ownership
Private codes200..211 are stable world content installed only during initial
fill and the existing safe incoming-row install. Dynamic updates never patch
screen RAM. One desired body style is copied to its private32-byte charset
allocation per presented frame, after frame synchronization and before sprite
presentation/terrain fetches. Screen codes remain unchanged on destruction;
private pixels become the exact cached underlying terrain glyphs.

BG_INCOMING_ROW stays raw terrain. BG_CROSSING_ROW remains a physical row and
therefore intentionally contains private world codes when applicable. Copying
those codes moves the same world footprint; it cannot leave old orientation
bytes behind in a neighbouring row. Underlay is decoded only at game init from
raw stage data, never from patched screen/crossing bytes. The glyph cache is
only12 cells/96bytes, not a terrain matrix. No scroller copy body, fetch split,
admission cutoff, D011/D018 owner, scheduler, IRQ, BUILD/LIVE or clipping-pool
architecture was changed.

### Memory and measured timing
- New module8800..8edf:1760bytes including alignment. Code8800..8b56 (855bytes),
  runtime state8b57..8b82 (44), placement/derived-X arrays12bytes,
  row lookup8c00..8cc7 (200), original glyph cache8d00..8d5f (96),
  seven art templates8e00..8edf (224). Remaining bytes are alignment padding.
- Charset3e40..3e9f:12 private glyphs/96bytes. No existing art/HUD/star glyph
  overwritten; allocation/range/placement guards included. No sprite-pool growth.
- Main code +42bytes, background-control code +5. Other protected segment
  boundaries unchanged. PRG extends through8edf (loader fills the address gap).
- Pure prepare cost5881..5928 including callerJSR over all100 origins, within
  existing6000 budget. Cutoff184 remains unchanged.
- Measured CPU routine bodies: position120..159; update126..522 (including
  actual firing); dirty glyph469..503; aim59..74. Normal captured dirty glyph
  wall time463..542 to pre-RTS label, exit raster11..13. Wall time includes VIC
  contention; the normal900 subset alone had463..497. Worst-index/eight-early-
  sprite probe497 to pre-RTS, presentation raster29 < earliest legalY51.
- Long normal: upper copy begins165..180, ready261..278; lower begins12..27,
  completes no later105 (< row13 fetch160). Synthetic stress: upper ready<=283,
  lower ready<=130. These include IRQ/DMA time; no copy timing assumption moved.

### Test results
| Test | Result |
| --- | --- |
| Baseline1800 normal | Pixel/matrix/HUD/raster pass;74coarse transitions; no deferrals |
| Prototype900 normal | All oracles pass;37coarse;6safe deferrals;3turret shots |
| Prototype5400 long-v2 | All oracles pass;224coarse,2.24circuits;3safe deferrals;10turret shots |
| Turret functional probes |45checks pass; includes2400 position/phase combinations, hit ordering, health/death,9-bit X, caps/fullpool/despawn/reset |
| Long turret lifetime oracle | Pass; real cannon deaths198/Y122 and1332/Y227; dead reentries2and1; hit flashes captured |
| Scheduler regression |17cases x16frames/all8phases pass; early24/37/55, late243,16objects, replay and DMA cases |
| Dirty glyph + early sprites | Pass;497cycles, presentation29 beforeY51 |
| Lifecycle | Real death/respawn/game-over/menu/restart pass; CIA/KERNAL restored; turret death persists through respawn and resets on new game |
| Physical top-clip sweep |54samples,Y48..74 both directions;10,962raster checks; zero failures |
| Pure coarse CPU | All100 origins below6000cycles |
| Synthetic1400 stress, both builds |16objects/6batches, exact19656; zero service/start failures; baseline top-edge signature remains |

Synthetic stress is deliberately NOT reported as pixel-clean. Baseline has
33physical pixel failures +5edge-motion failures; prototype51+3. Every mismatch
in both is confined to physical raster71..72 (within the already-known71..73
straddler-DMA band). Full lists are in fixed-hud-failures.json. Neither run has
matrix, incoming, crossing, charset, HUD, display-event or cadence failures.
Baseline has665 replay frames/409coarse deferrals; prototype667/397. Both make
13coarse transitions. Random/wave timing differs, so counts are not a matched
seed performance delta. No new failure class observed; scheduler remains intact.

FREE is a rolling50-BUILD minimum, not an instantaneous cost meter:
| Run | HUD min / median | Notes |
| --- | --- | --- |
| Baseline normal1800 |2394 /5607 | No turret cost |
| Prototype normal900 |1575 /6835.5 | Worst observed ordinary FREE1575 |
| Prototype long5400 |4473 /7308 | Alive/visible sample median11466; firing median10867.5; offscreen/dead median11970 |
| Baseline synthetic stress |0 /1197 | Expected heavy overload |
| Prototype synthetic stress |0 /945 | Expected heavy overload |
Normal holds are occasional (3/5400 in the long run), not sustained. Timing
costs above isolate routines more reliably than comparing different wave RNG.

### Exact changed files
1. src/main.asm — small lifecycle/row-install/frame-publication/combat hooks and
   shared explicit-origin projectile entry.
2. src/background_turrets.asm — new guarded turret data/runtime/art module.
3. tools/vice_scroll_test.py — private-glyph/state captures and optional real
   cannon playtest inputs.
4. tools/check_fixed_hud_capture.py — independent private-code/underlay/pixel
   expectations, full failure log and one-frame old-score handling on kills.
5. tools/vice_raster_cases.py — all100-origin CPU enumeration and dirty-publication probe.
6. tools/vice_raster_lifecycle.py — turret death/respawn/new-game assertions.
7. tools/vice_turret_cases.py — fresh-VICE functional/CPU probes.
8. tools/check_turret_capture.py — captured world/lifetime/cap/FREE audit.
9. docs/bg-turret-test-worklog.md — this investigation/handoff.

### Reproduction / artifacts
Build:
```
java -jar /Users/brianmorrice/dev/tools/kickassembler/KickAss.jar src/main.asm -odir /Volumes/SSD/dev/C64/shooter_test/build -o /Volumes/SSD/dev/C64/shooter_test/build/shooter.prg -vicesymbols
```
Fresh capture process (choose an unused port), then capture:
```
/opt/homebrew/bin/x64sc -default -pal -warp +sound -remotemonitor -remotemonitoraddress ip4://127.0.0.1:6571 -autostartprgmode 1 -autostart build/shooter.prg
python3 tools/vice_scroll_test.py --port 6571 --physical --trace --turret-playtest --frames 5400 --out build/bg-turret-test/long-v2
PYTHONPATH=/private/tmp/hud-study/python-deps python3 tools/check_fixed_hud_capture.py build/bg-turret-test/long-v2
python3 tools/check_raster_capture.py build/bg-turret-test/long-v2
python3 tools/check_turret_capture.py build/bg-turret-test/long-v2 --require-wrap-deaths
```
Other commands:
```
python3 tools/vice_turret_cases.py
python3 tools/vice_raster_cases.py --port 6569 --frames 16 --all-phases --out build/bg-turret-test/scheduler-v1
python3 tools/vice_raster_cases.py --case clip_eight --port 6574 --frames 16 --all-phases --publish-turret --out build/bg-turret-test/publication-v1
python3 tools/vice_raster_cases.py --case zero --port 6567 --frames 2 --copy-cpu --out build/bg-turret-test/copy-cpu-v1
python3 tools/vice_raster_lifecycle.py --out build/bg-turret-test/lifecycle-v1
PYTHONPATH=/private/tmp/hud-study/python-deps python3 tools/vice_clip_sweep.py --port 6575 --out build/bg-turret-test/clip-sweep-v1
```
Run check_raster_capture.py on each scheduler case subdirectory. Stress uses
vice_scroll_test.py --physical --trace --stress --frames1400 (space before1400)
on separate fresh ports; baseline additionally supplies --prg baseline.prg and
--symbols baseline.vs from build/bg-turret-test. Capture/checker JSON/logs and
screenshots reside below build/bg-turret-test (ignored build artifacts).

### Limitations / next step
Human VICE playtest is the next step, not more architectural implementation.
Review body visibility/aim, hits/flash/disappearance and natural movement against
terrain. Screenshots long-v2/00150.png and00210.png show alive and restored ground;
automated inspection is not a substitute for human motion acceptance.

Prototype uses one fixed3-placement table; editor should emit character col/row
coordinates, not metatile IDs. Placement origins col0..38,row0..99; bottom wraps.
Current O(1) installer requires all bodies' footprint world rows disjoint, even
at different columns. The assembler rejects violations. Future editor should
validate that prototype rule or a later task must deliberately generalize it.
Runtime/graphics are not a generic entity system. Colours inherit terrain;
solid small mount, six crude directions, downward bullets only, no new effects
or sounds. Glyph templates replace the four terrain glyphs while alive and
restore exact terrain on death; this is intentional background body rendering,
not dynamic terrain compositing. Destruction is per-game RAM state, not disk save.
The known overload-only raster71..73 issue remains outside this task's scope.

Final PRG SHA-256:
fd3d3a68099d2832ee71840c82bc51a6123424caa98d75745b43af6fc61acbb2
