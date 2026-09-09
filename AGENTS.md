# AGENTS.md — 19656 C64 project

This repository is a PAL Commodore 64 game/engine project written in 6502
assembly and built with KickAssembler.

Read this file before making changes.

## General working rules

- Target PAL C64 unless explicitly told otherwise.
- Use legal NMOS 6502 instructions/addressing modes only.
- Respect 6502 relative branch range limits (±128 bytes).
- Preserve the existing coding style and comments.
- Prefer small, reviewable changes over broad rewrites.
- Do not silently replace working architecture with a different design.
- Measure VIC/raster behaviour in VICE where timing matters; do not rely only
  on theoretical assumptions.
- Use fresh VICE instances for authoritative capture/testing where practical.
- Do not commit or push unless explicitly requested.
- One agent modifies the source tree at a time.

## Protected engine invariants

### Logical object slot 0

Logical object slot 0 is permanently reserved for the player.

Generic allocation must always begin at logical slot 1.

The player may move between VIC hardware sprite slots as part of the sprite
multiplexer, but its logical object ID remains 0 for the lifetime of the game.

Do not change this invariant.

### Render architecture

Preserve the logical-object -> sorted active list -> BUILD render plan ->
LIVE render plan architecture.

The raster IRQ reads LIVE state only.

Do not make the IRQ consume partially built/main-thread render state.

### Current scrolling architecture

The production scrolling engine is a proven **double-buffered** vertical
scroller (promoted to the default build in Stage 4J, `src/main.asm`'s
`OPT_SECOND_SCREEN` block; see
`/reports/stage4-second-screen-scroller-architecture.md` and the Stage
4D-4I reports/worklogs under `/reports` and `/docs` for the full derivation).

Important characteristics:

- two 1 KB screen matrices in VIC bank 0: page A at $0400, page B at $2800
- charset at $3800, shared by both pages
- RSEL=0 / 24-row display mode
- the next coarse-scroll state is built incrementally into the currently
  INACTIVE page across the fine-scroll frames leading up to the next coarse
  step, then published by flipping `$D018` -- no legacy in-window
  visible-matrix mutation on that path
- coarse admission may proceed while a LIVE sprite-reuse batch is still
  outstanding (the flip touches no sprite hardware/batch state); reasons 2
  and 3 (badline defer / beam-position deadline) are unchanged
- page-aware sprite-pointer handling keeps the ACTIVE page's hardware
  pointer table ($07F8 or $2BF8) correct every frame, including mid-frame
  LIVE batch reassignments (a self-modified store target) and HUD
  slot-reclaim writes
- a fixed, understood VIC badline/deadline-line coincidence remains, visible
  only under deliberately pathological synthetic sprite-reuse stress
  (`--dense`); it is present (at an equal-or-worse per-exposure rate) in the
  old single-screen baseline too, is not a double-buffering cost, and is not
  an open task (Stage 4I)

Two older/reference configurations remain reachable by commenting toggles in
`src/main.asm`, kept for regression, archaeology and diagnosis -- **not** the
normal build:
- **Mode A** (`OPT_SECOND_SCREEN` commented): the old single-screen Stage-3
  regression baseline (beam-raced, `$0400` only, no second screen, no
  `$D018` flipping, coarse scrolling split around VIC fetch timing with a
  physical crossing-row buffer -- this used to be the default; it is not
  anymore).
- **Mode B** (`OPT_SS_ALLOW_PENDING_LIVE_FLIP` commented): the double-buffered
  architecture with reason 1 (pending-LIVE defer) still intact, so it cannot
  advance the coarse scroll while a LIVE batch is outstanding.

Checkpoint tags: `stable-single-screen-scroller` (pre-Stage-4), `stable-
double-buffered-scroller` (original Stage 4D+4E checkpoint -- archaeological,
includes a since-repaired pointer defect), `stable-double-buffered-
scroller-v2` (this accepted, corrected architecture).

Do not replace this architecture casually.

Any change to its raster timing, page-flip publication, inactive-page build
scheduling, sprite-pointer mirroring, crossing-row handling, badline
assumptions or D011/D018 behaviour must be derived and tested.

### Memory

Respect existing memory guards and documented allocations.

Do not grow code/data into protected regions without first inspecting the
current memory map and assembler guards.

## Raster / sprite work

The sprite multiplexer and display code share time-critical VIC-II resources.

When modifying raster scheduling:

- analyse actual raster deadlines rather than only compare values
- account for sprite DMA stealing cycles
- account for CIA/KERNAL IRQ latency
- account for variable-length handlers
- do not assume a D012 compare written after its raster line has passed will
  execute in the intended physical frame
- preserve deterministic ownership of D011 raster compare-high state
- explicitly handle overdue raster events
- test early and late legal sprite schedules
- verify that all intended LIVE assignments complete in the correct physical
  frame

Do not introduce an independent competing raster IRQ chain without proving
ownership and ordering.

## Session continuity and interrupted work

Long-running tasks may outlive an agent's context window, token allowance,
usage window or individual session.

Treat session expiry as an interruption, not as a reason to restart work.

For any substantial investigation or implementation likely to span sessions,
maintain a task-specific worklog under `docs/`, for example:

    docs/<task-name>-worklog.md

Create/update the worklog early enough that useful work is not lost if the
session ends unexpectedly.

Keep the worklog concise but sufficient for another agent/session to resume
without repeating completed investigation.

Record, as applicable:

- task objective and current scope
- important architecture/source facts discovered
- hypotheses tested
- approaches rejected and why
- timing/performance measurements
- test commands and significant results
- files intentionally modified
- current implementation state
- unresolved questions
- exact next recommended step

Update the worklog periodically during substantial work, especially:

- after completing an investigation phase
- before lengthy builds/tests/emulator runs
- before a significant architectural change
- when remaining session/context budget appears low

## Resuming interrupted work

At the start of a substantial task, inspect the repository and relevant
`docs/*-worklog.md` files before repeating investigation.

If a relevant unfinished worklog exists:

1. Read it.
2. Inspect `git status`, `git diff`, and current source.
3. Verify that repository state is consistent with the worklog.
4. Continue from the recorded next step where appropriate.
5. Do not repeat completed investigation merely because this is a new agent,
   model, context or usage window.
6. Re-test earlier conclusions only when source state has changed, evidence is
   incomplete, or there is a concrete technical reason to doubt them.

Never discard, revert, overwrite or "clean up" uncommitted work from an
interrupted session merely because its origin is unclear.

Determine what the changes are first.

Do not create commits solely as session checkpoints unless explicitly
requested.

The working tree plus task worklog are the normal handoff mechanism.

## Cross-agent continuity

Work produced by another agent is not disposable or provisional merely because
the current agent did not produce it.

Claude, Codex, ChatGPT-assisted work and human-written changes must all be
treated as existing repository state.

Before replacing another agent's implementation or repeating its investigation:

- inspect its source changes
- read any associated worklog/report
- verify its recorded evidence
- identify a specific technical reason for replacement or re-investigation

Prefer continuing proven work over independently recreating it.

## Testing discipline

Do not describe a change as proven merely because it assembles or looks correct
for a few seconds in VICE.

For timing-sensitive engine changes, test the relevant combination of:

- all eight fine-scroll phases
- coarse transitions
- repeated stage wraps where applicable
- normal sprite load
- maximum/stress sprite load
- early and late raster batches
- frame cadence
- deferred scrolling paths
- menu/gameplay/game-over lifecycle where relevant
- memory/sprite-pointer integrity

Keep experimental probes separate from production source where possible.

An experiment demonstrating hardware behaviour is not automatically a valid
production implementation.

## Stop conditions

Stop and report rather than forcing an implementation through if a requested
change appears to require an unapproved:

- wholesale sprite-multiplexer rewrite
- replacement scrolling engine
- second screen buffer
- terrain shadow matrix
- hardware sprite reservation that reduces game capacity
- change to logical player slot 0
- unsafe memory overlap
- undocumented/illegal NMOS 6502 behaviour
- timing assumption that only survives a light-load test

A technically honest stop with measured blockers is preferable to an
unvalidated implementation.

## VICE launch / focus discipline

Automated VICE testing must not steal macOS keyboard focus from the user.

When launching VICE/x64sc for automated tests on macOS:

- launch it without intentionally activating, foregrounding or focusing the
  VICE application/window
- avoid launch methods such as `open -a` that normally activate the GUI
- prefer direct/background process launch methods that leave the user's
  currently active application focused
- automated tests must not depend on VICE having keyboard focus
- use the VICE remote monitor, test harness, process control or other
  programmatic interfaces rather than simulated keyboard input
- do not send arbitrary user keyboard input to the emulated C64
- where practical, centralise VICE process launching in the test tooling so
  all automated tests inherit the non-focus-stealing behaviour
- do not hide, minimise, terminate or otherwise manipulate an unrelated
  user-launched VICE instance in order to achieve this

A VICE window may remain visible during testing; the requirement is that an
automatically launched instance must not deliberately take keyboard focus.

If reliable non-activating launch is not possible for a particular test,
stop and report the limitation rather than introducing fragile focus-stealing
automation.
