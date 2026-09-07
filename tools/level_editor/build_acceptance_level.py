#!/usr/bin/env python3
"""Deterministically (re)generate the 100-metatile-row inspection acceptance level.

This is the first end-to-end level-editor -> generated-assembler -> engine
integration artefact. It:

  1. reads the 16 hand-authored metatile definitions from git HEAD's
     src/stage_test.asm (the tileset ownership does NOT move in this milestone),
  2. builds a V2 LevelProject: 100 metatile rows, palette bg=0 / mc1=11 /
     mc2=14 / character=1, scroll divider 2,
  3. saves the deterministic V2 project JSON under tools/level_editor/projects/,
  4. exports src/generated/stage_config.asm + src/generated/stage_test.asm via
     the real editor exporter.

The 100-row map is the committed 25-row bas-relief inspection stage tiled x4
(rows 0 and 99 are all-M0 so the vertical wrap seam stays clean, and the M14
MACH turret housings still land under turretCols/turretRows 17/29/13 @ 13/29/57).

Run from anywhere:  python3 tools/level_editor/build_acceptance_level.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from ka_export import export_project          # noqa: E402
from project import LevelProject, save_project  # noqa: E402

PROJECT_NAME = "inspection-100"
TARGET_ROWS = 100
PALETTE = {"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1}
SCROLL_FRAME_DIVIDER = 2


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
        vals = [int(tok) for tok in payload.split(".byte", 1)[1].split(",") if tok.strip()]
        rows.append(vals)
    if not inside:
        raise SystemExit(f"could not find {start_label}: in source")
    return rows


def main():
    src = subprocess.check_output(
        ["git", "-C", str(REPO), "show", "HEAD:src/stage_test.asm"], text=True
    )
    metatiles = _parse_byte_rows(src, "metatileDefs", "METATILE_DEFS_END")
    if len(metatiles) != 16 or any(len(m) != 16 for m in metatiles):
        raise SystemExit(f"expected 16 x 16-byte metatile defs, got {[len(m) for m in metatiles]}")

    base_rows = _parse_byte_rows(src, "stageMetatileRows", "STAGE_METATILE_ROWS_END")
    tiled = (base_rows * ((TARGET_ROWS // len(base_rows)) + 1))[:TARGET_ROWS]
    assert len(tiled) == TARGET_ROWS
    assert tiled[0] == [0] * 10 and tiled[-1] == [0] * 10, "wrap-seam rows must be all-M0"

    project = LevelProject(
        name=PROJECT_NAME,
        metatile_rows=[row[:] for row in tiled],
        palette=dict(PALETTE),
        scroll_frame_divider=SCROLL_FRAME_DIVIDER,
        objects=[],
        metatile_metadata={},
    )

    projects_dir = HERE / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_path = projects_dir / f"{PROJECT_NAME}.json"
    save_project(project, project_path)

    generated_dir = REPO / "src" / "generated"
    config_path, stage_path = export_project(project, metatiles, generated_dir)

    print(f"project : {project_path.relative_to(REPO)}")
    print(f"config  : {config_path.relative_to(REPO)}")
    print(f"stage   : {stage_path.relative_to(REPO)}")
    print(f"height  : {project.height} metatile rows")
    print(f"map     : {project.height * 10} bytes")
    print(f"palette : {project.palette}")
    print(f"divider : {project.scroll_frame_divider}")


if __name__ == "__main__":
    main()
