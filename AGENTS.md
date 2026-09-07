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

The production scrolling engine is a proven single-screen beam-raced vertical
scroller.

Important characteristics:

- screen matrix at $0400
- charset at $3800
- VIC bank 0
- RSEL=0 / 24-row display mode
- no second screen matrix
- no terrain shadow matrix
- no $D018 screen flipping
- no background raster IRQ
- coarse scrolling is split around VIC fetch timing
- a physical crossing-row buffer preserves the row spanning the split
- fine7 may be safely held/deferred when coarse work cannot begin in time

Do not replace this architecture casually.

Any change to its raster timing, row-copy boundaries, crossing-row handling,
badline assumptions or D011 behaviour must be derived and tested.

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
