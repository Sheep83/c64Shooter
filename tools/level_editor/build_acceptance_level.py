#!/usr/bin/env python3
"""Deterministically (re)generate the 100-metatile-row inspection acceptance level.

Chain proved end to end:
  Python level project -> editor exporter -> src/generated/{stage_config,
  stage_test, stage_turrets}.asm -> KickAssembler -> engine -> VICE.

The map is the committed 100-row bas-relief inspection stage with:
  * row 0 and row 99 forced to all-M0 (clean vertical wrap seam),
  * rows 1..5 forced to all-M13 GRILLE   -> the visually distinct FAR / top band
    (the END of the stage, reached last),
  * rows 94..97 forced to all-M1 R_FILL  -> the visually distinct START / bottom
    band (the BEGINNING of the stage, on screen at boot with bottom-origin init),
  * three M14 MACH housings under the three authored turrets.

Authored turrets (editor `objects`), one per requirement:
  * metatile (89, 4) -> world row 357  : near the BEGINNING (activates early)
  * metatile (70, 7) -> world row 281  : ABOVE logical row 255 (16-bit world row)
  * metatile (30, 3) -> world row 121  : later in the playthrough

Run from anywhere:  python3 tools/level_editor/build_acceptance_level.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from ka_export import export_project              # noqa: E402
from project import LevelProject, save_project    # noqa: E402

PROJECT_NAME = "inspection-100"
PALETTE = {"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1}
SCROLL_FRAME_DIVIDER = 2

M0, M1_RFILL, M13_GRILLE, M14_MACH = 0, 1, 13, 14
TOP_BAND = range(1, 6)          # rows 1..5   -> GRILLE (FAR / end)
BOTTOM_BAND = range(94, 98)     # rows 94..97 -> R_FILL (START / beginning)

# Authored turrets: (metatile_row, metatile_col). Distinct rows required.
TURRETS = [(89, 4), (70, 7), (30, 3)]


def _parse_byte_rows(text, start_label, end_label):
    rows, inside = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == f"{start_label}:":
            inside = True
            continue
        if inside and stripped == f"{end_label}:":
            break
        if not inside:
            continue
        payload = stripped.split("//", 1)[0]
        if ".byte" not in payload:
            continue
        rows.append([int(t) for t in payload.split(".byte", 1)[1].split(",") if t.strip()])
    if not inside:
        raise SystemExit(f"could not find {start_label}: in source")
    return rows


def main():
    src = subprocess.check_output(
        ["git", "-C", str(REPO), "show", "HEAD:src/generated/stage_test.asm"], text=True
    )
    metatiles = _parse_byte_rows(src, "metatileDefs", "METATILE_DEFS_END")
    if len(metatiles) != 16 or any(len(m) != 16 for m in metatiles):
        raise SystemExit(f"expected 16 x 16-byte metatile defs, got {[len(m) for m in metatiles]}")

    rows = [row[:] for row in _parse_byte_rows(src, "stageMetatileRows", "STAGE_METATILE_ROWS_END")]
    if len(rows) != 100 or any(len(r) != 10 for r in rows):
        raise SystemExit(f"expected a 100 x 10 committed map, got {len(rows)} rows")

    rows[0] = [M0] * 10
    rows[99] = [M0] * 10
    for r in TOP_BAND:
        rows[r] = [M13_GRILLE] * 10
    for r in BOTTOM_BAND:
        rows[r] = [M1_RFILL] * 10
    for mrow, mcol in TURRETS:
        rows[mrow][mcol] = M14_MACH

    project = LevelProject(
        name=PROJECT_NAME,
        metatile_rows=rows,
        palette=dict(PALETTE),
        scroll_frame_divider=SCROLL_FRAME_DIVIDER,
        objects=[{"type": "turret", "metatileRow": mr, "metatileCol": mc}
                 for mr, mc in TURRETS],
        metatile_metadata={},
    )

    projects_dir = HERE / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_path = projects_dir / f"{PROJECT_NAME}.json"
    save_project(project, project_path)

    generated_dir = REPO / "src" / "generated"
    config_path, stage_path, turrets_path = export_project(project, metatiles, generated_dir)

    print(f"project : {project_path.relative_to(REPO)}")
    for p in (config_path, stage_path, turrets_path):
        print(f"generated: {p.relative_to(REPO)}")
    print(f"height  : {project.height} metatile rows  ({project.height * 4} logical rows)")
    print(f"map     : {project.height * 10} bytes")
    print(f"palette : {project.palette}   divider {project.scroll_frame_divider}")
    for mr, mc in sorted(TURRETS):
        print(f"turret  : metatile ({mr:3d},{mc}) -> world char row {mr * 4 + 1}, col {mc * 4 + 1}")


if __name__ == "__main__":
    main()
