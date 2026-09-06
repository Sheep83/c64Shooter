# Isolated fixed-HUD investigation probes

These are disposable hardware experiments, **not an engine implementation**.
In particular `geometry.asm` deliberately retains the simple polling strategy
that fails under heavy sprite DMA. Do not copy it into `src/main.asm`.
The decision record is `docs/fixed-hud-codex-worklog.md`.

Run from the repository root. Python collectors import the existing VICE text
monitor helper from `tools/vice_scroll_test.py`; pixel collectors need Pillow.
Local tool paths below match this investigation's machine. Output is ignored
under `build/fixed-hud-codex/`. Use fresh VICE instances, not a user's running
game. Collectors mutate emulated RAM/registers; they do not edit engine source.

Build each isolated PRG, independently of the engine:

```sh
mkdir -p build/fixed-hud-codex/probes
java -jar /Users/brianmorrice/dev/tools/kickassembler/KickAss.jar tools/fixed_hud_probe/gating.asm -odir "$PWD/build/fixed-hud-codex/probes" -o "$PWD/build/fixed-hud-codex/probes/gating.prg" -vicesymbols
java -jar /Users/brianmorrice/dev/tools/kickassembler/KickAss.jar tools/fixed_hud_probe/geometry.asm -odir "$PWD/build/fixed-hud-codex/probes" -o "$PWD/build/fixed-hud-codex/probes/geometry.prg" -vicesymbols
```

Sprite gate: launch fresh VICE on6531, then collect its four D015/pointer modes:

```sh
/opt/homebrew/bin/x64sc -default -pal -warp +sound -remotemonitor -remotemonitoraddress ip4://127.0.0.1:6531 -autostartprgmode 1 -autostart build/fixed-hud-codex/probes/gating.prg
python3 tools/fixed_hud_probe/capture-gating.py
```

Geometry: launch fresh VICE on6532 for no-sprite mask-off/on captures, or6533
for the six DMA masks (including FF). Use `geometry.prg` in the same launch
command, with the appropriate port. Run respectively:

```sh
python3 tools/fixed_hud_probe/capture-geometry.py
python3 tools/fixed_hud_probe/capture-geometry-dma.py
```

The current geometry source has18 NOPs before restore. The first experiment
had16, and leaked8/16 right-edge pixels on raster70 at fine3/4. The worklog and
original `build/fixed-hud-codex/probes/geometry-results.json` describe that first
version. The18-NOP source fixes the no-sprite case but fails all phases for
DMA masks F8/FF. Expected known failures are reported as JSON; these exploratory
collectors do **not** implement a CI pass/fail contract. No sprite pixels are
excluded from the geometry oracle: DMA sprites are deliberately blank.

Schedule probes run the **freshly built engine**. Build `build/shooter.prg`
and `build/main.vs` using the normal project build first. The controller starts
and quits separate VICE processes at6535..6538 for all four cases:

```sh
python3 tools/fixed_hud_probe/measure-schedule.py
# Or one case: early24, player37, late243, overlap55
python3 tools/fixed_hud_probe/measure-schedule.py overlap55
```

Each case starts through the menu, seeds16 logical objects before the real
sort/snapshot/build, lets initial rendering and arming complete, and idles
the main CPU at a temporary RAM6000 loop. Sprites are blank, player remains
logical0, and D011fine7 gives the proposed HUD badline55. IRQ code is untouched.
Trace includes IRQ entry, full KERNAL service entry EA31, and RTI-tail entry
EA81. CIA interrupts still occur and must be distinguished from VIC batches.
The controller assumes the current symbols and real menu flow; it is not a
portable general VICE test runner. Fresh processes have different CIA phase,
so handler entry cycles may vary; compare the scheduling conflict, not one
historical exact stopwatch value.

After the ordinary `vice_scroll_test.py` and `check_hud_capture.py` baseline
captures at `build/fixed-hud-codex/{baseline,baseline-stress}`, run:

```sh
python3 tools/fixed_hud_probe/analyse-baseline.py
```

This extracts copy timings and compares final hardware pointers against the
LIVE plan. A mismatch is **not proof of memory corruption**: in the captured
baseline stress, all120 mismatching frames had unfinished batches. See the
worklog's frame90/91 evidence. Also, all these captures had PLAYER_STATE=0;
do not claim death/respawn or menu-return regression coverage from them.

On this machine Pillow was available via the temporary installation:
`PYTHONPATH=/private/tmp/hud-study/python-deps`. This is an environment detail,
not a new project dependency. Capture tools leave their manually launched
VICE running; close it normally after collection.
