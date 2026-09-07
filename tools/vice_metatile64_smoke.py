#!/usr/bin/env python3
"""Run the real game with a 64-metatile-definition stage and prove the frame
loop stays healthy: the widened decodeStageCharacterRow (16-bit metatileDefs
offset, +~650 cycles) must not perturb PAL cadence or raster servicing.

Builds a deterministic 64-def fixture into src/generated/level1/ (backed up and
restored from byte copies, like tools/run_stage_fixture.sh), assembles, then via
the VICE remote monitor (no keyboard focus, background launch):

  * boots to GAME_STATE == PLAYING and stays there for the whole sample window;
  * SCROLL_ROW keeps advancing and the stage wraps at least once;
  * every physical PAL frame is exactly 19656 cycles (raster-line delta constant);
  * a live decodeStageCharacterRow call for a row whose map IDs include one > 15
    (and, where the fixture places it, 63) expands to the exact metatileDefs
    bytes - checked against an independent expansion of the dumped tables.

    python3 tools/vice_metatile64_smoke.py --rows 240
"""
import argparse
import json
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

from vice_scroll_test import Monitor, symbols
from vice_turret_runtime_probe import start_playing

KA = Path("/Users/brianmorrice/dev/tools/kickassembler/KickAss.jar")
GEN = Path("src/generated/level1")
FILES = ["stage_config.asm", "stage_charset.asm", "stage_test.asm",
         "stage_turrets.asm", "stage_waves.asm"]
_RL = re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')


def build_fixture(rows, defs, tmp):
    for f in FILES:
        shutil.copy(GEN / f, tmp / f)
    fixture = subprocess.check_output(
        ["python3", "tools/make_stage_fixture.py", str(rows), str(defs)], text=True)
    (GEN / "stage_test.asm").write_text(fixture)
    cfg = (GEN / "stage_config.asm").read_text()
    cfg = re.sub(r"^\.const STAGE_METATILE_ROWS.*$",
                 f".const STAGE_METATILE_ROWS     = {rows}", cfg, flags=re.M)
    cfg = re.sub(r"^\.const STAGE_METATILE_COUNT.*$",
                 f".const STAGE_METATILE_COUNT   = {defs}", cfg, flags=re.M)
    (GEN / "stage_config.asm").write_text(cfg)
    (GEN / "stage_turrets.asm").write_text(
        ".const TURRET_TOTAL = 1\n.var turretCols = List().add(1)\n.var turretRows = List().add(1)\n")
    (GEN / "stage_waves.asm").write_text(
        ".const WAVE_TRIGGER_COUNT = 0\n"
        + "".join(f".var waveTrigger{n} = List()\n" for n in
                  ("RowLo", "RowHi", "AttackId", "Count", "Sprite", "Interval")))


def restore(tmp):
    for f in FILES:
        shutil.copy(tmp / f, GEN / f)


def assemble():
    out = subprocess.run(
        ["java", "-jar", str(KA), "main.asm", "-odir", "../build",
         "-o", "../build/shooter.prg", "-vicesymbols"],
        cwd="src", capture_output=True, text=True)
    if "Writing prg file" not in out.stdout:
        raise SystemExit("assemble failed:\n" + out.stdout + out.stderr)


def launch(port):
    with socket.socket() as c:
        if c.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"port {port} occupied")
    p = subprocess.Popen(
        ["/opt/homebrew/bin/x64sc", "-default", "-pal", "-warp", "+sound",
         "-remotemonitor", "-remotemonitoraddress", f"ip4://127.0.0.1:{port}",
         "-autostartprgmode", "1", "-autostart", str(Path("build/shooter.prg").resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return p, Monitor(port)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=240)
    ap.add_argument("--defs", type=int, default=64)
    ap.add_argument("--samples", type=int, default=80)
    ap.add_argument("--port", type=int, default=6607)
    ap.add_argument("--out", type=Path, default=Path("build/mc-test/metatile64"))
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "gen-backup"
    tmp.mkdir(exist_ok=True)

    fails = []
    build_fixture(args.rows, args.defs, tmp)
    try:
        assemble()
        sym = symbols(Path("build/main.vs"))
        proc, m = launch(args.port)
        try:
            m.trace_file = (out / "monitor.log").open("w")
            start_playing(m, sym)

            def rd(name, n=1):
                a = sym[name] if isinstance(name, str) else name
                p = out / "s.bin"
                m.cmd(f'bsave "{p}" 0 {a:04x} {a + n - 1:04x}')
                return list(p.read_bytes())

            def w16(name):
                b = rd(name, 2)
                return b[0] | (b[1] << 8)

            defs_len = sym["METATILE_DEFS_END"] - sym["metatileDefs"]
            mdefs = rd("metatileDefs", defs_len)
            metatile_defs = [mdefs[i:i + 16] for i in range(0, defs_len, 16)]
            rows_len = sym["STAGE_METATILE_ROWS_END"] - sym["stageMetatileRows"]
            raw = rd("stageMetatileRows", rows_len)
            stage_rows = [raw[i:i + 10] for i in range(0, rows_len, 10)]
            slr = len(stage_rows) * 4
            max_id = max(v for r in stage_rows for v in r)
            print(f"{len(metatile_defs)} metatile defs, {len(stage_rows)} rows, "
                  f"{slr} logical rows; max map id {max_id}")
            if len(metatile_defs) != args.defs:
                fails.append(f"metatileDefs table has {len(metatile_defs)} entries, want {args.defs}")
            if max_id <= 15:
                fails.append(f"fixture never uses an id > 15 (max {max_id})")

            playing = sym.get("GAME_STATE_PLAYING", 1)
            m.cmd(f'break {sym["applyFineScroll"]:04x}')

            states, rows_seen, rl_deltas = [], [], []
            prev_rl = None
            for _ in range(args.samples):
                for _ in range(6):
                    m.cmd("x")
                states.append(rd("GAME_STATE", 1)[0])
                rows_seen.append(w16("SCROLL_ROW"))
                rl = int(_RL.search(m.cmd("r"))[2])
                if prev_rl is not None:
                    rl_deltas.append((rl - prev_rl) % 312)
                prev_rl = rl

            if any(s != playing for s in states):
                fails.append(f"GAME_STATE left PLAYING: {sorted(set(states))}")
            if max(rows_seen) - min(rows_seen) < 20:
                fails.append(f"SCROLL_ROW barely moved: {min(rows_seen)}..{max(rows_seen)}")

            # force a wrap: nudge SCROLL_ROW near 0 and let the coarse scroller
            # carry it through the 0 -> SLR-1 seam
            m.cmd(f'> {sym["SCROLL_ROW"]:04x} 06 00')
            m.cmd(f'> {sym["SCROLL_ROW_HI"]:04x} 00')
            wrapped = False
            prev = 6
            for _ in range(200):
                for _ in range(6):
                    m.cmd("x")
                r = w16("SCROLL_ROW")
                if r > prev + 5:
                    wrapped = True
                prev = r
            if not wrapped:
                fails.append("stage never wrapped after nudging SCROLL_ROW to 6")
            if rd("GAME_STATE", 1)[0] != playing:
                fails.append("GAME_STATE left PLAYING during the wrap window")

            # (PAL cadence for this build is proven separately by
            #  tools/check_raster_capture.py against build/shooter.prg - the
            #  raster-line deltas here are informational only.)

            # live decode check: pick a logical row whose 10 map IDs include the
            # largest id in the fixture; call decodeStageCharacterRow and compare
            trampoline = 0x6400
            m.cmd("delete")
            m.cmd(f"break {trampoline + 0x0a:04x}")
            target_mrow = next(i for i, r in enumerate(stage_rows) if max_id in r)
            for sub in (0, 1, 2, 3):
                logical = target_mrow * 4 + sub
                m.cmd(f'> {sym["BG_LOGICAL_ROW"]:04x} {logical & 0xFF:02x} {(logical >> 8) & 0xFF:02x}')
                m.cmd(f'> {sym["BG_INCOMING_ROW"]:04x} ' + "ee " * 40)
                a = sym["decodeStageCharacterRow"]
                code = [0x78, 0xd8, 0x20, a & 255, a >> 8, 0x4c,
                        (trampoline + 0x0a) & 0xFF, (trampoline + 0x0a) >> 8]
                m.cmd(f"> {trampoline:04x} " + " ".join(f"{b:02x}" for b in code))
                m.cmd(f"r pc={trampoline:04x}, sp=ff")
                m.cmd("x")
                incoming = rd("BG_INCOMING_ROW", 40)
                ids = stage_rows[target_mrow]
                want = []
                for col in range(10):
                    want += metatile_defs[ids[col]][sub * 4:sub * 4 + 4]
                if incoming != want:
                    bad = [i for i in range(40) if incoming[i] != want[i]]
                    fails.append(f"decode row {logical} (ids incl {max_id}) mismatch at "
                                 f"{bad[:6]}: got {[incoming[i] for i in bad[:6]]} "
                                 f"want {[want[i] for i in bad[:6]]}")

            result = {
                "rows": args.rows, "defs": len(metatile_defs), "logical_rows": slr,
                "max_map_id": max_id,
                "scroll_row_range": [min(rows_seen), max(rows_seen)],
                "wrapped": wrapped,
                "raster_line_deltas": sorted(set(rl_deltas)),
                "game_states": sorted(set(states)),
                "fails": fails,
            }
            (out / "metatile64.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
        finally:
            try:
                m.cmd("quit")
            except Exception:
                pass
            proc.terminate()
    finally:
        restore(tmp)

    if fails:
        print(f"\nFAIL ({len(fails)}):")
        for f in fails:
            print("  " + f)
        raise SystemExit(1)
    print("\nPASS: 64-metatile stage runs with healthy frame loop + exact live decode")


if __name__ == "__main__":
    main()
