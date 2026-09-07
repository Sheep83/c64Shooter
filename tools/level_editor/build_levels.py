#!/usr/bin/env python3
"""Deterministically (re)build the two authored level packages and their
generated engine includes.

    tools/level_editor/levels/level1/level.json  -> src/generated/level1/*.asm
    tools/level_editor/levels/level2/level.json  -> src/generated/level2/*.asm

Gameplay imports src/generated/level1/ only. Level 2 is an editor/export proof:
its includes are generated and committed but never #import-ed by main.asm.

Run from anywhere:  python3 tools/level_editor/build_levels.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from engine_data import load_engine_data                       # noqa: E402
from ka_export import export_level                             # noqa: E402
from project import LevelProject, save_project                 # noqa: E402
import level2_tileset                                          # noqa: E402

LEVELS_DIR = HERE / "levels"
GENERATED = REPO / "src" / "generated"

M0, M1_RFILL, M13_GRILLE, M14_MACH = 0, 1, 13, 14


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


# ---------------------------------------------------------------------------
# Level 1 - the level gameplay consumes. Current riveted-hull tileset & style,
# bottom-origin, 100 metatile rows. Uses the committed inspection map as its
# basis; spreads 9 turrets through the level - including a cluster of FIVE that
# are all simultaneously on one gameplay screen, well past the old 3-visible cap
# and proving the shared-body-glyph rendering - plus authored wave triggers.
# ---------------------------------------------------------------------------
L1_NAME = "level1"
L1_PALETTE = {"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1}
L1_DIVIDER = 2
L1_TOP_BAND = range(1, 6)          # M13 GRILLE - FAR / end band
L1_BOTTOM_BAND = range(94, 98)     # M1 R_FILL  - START / beginning band

# (metatile_row, metatile_col). Distinct rows. Metatile rows 92/91/90/89/88 sit
# inside one 23-logical-row gameplay screen (world rows 369/365/361/357/353,
# span 16) - FIVE turrets visible at once, all > 255 (16-bit rows). The rest are
# solo, one per screen.
L1_TURRETS = [(92, 6), (91, 3), (90, 8), (89, 1), (88, 5),
              (60, 4), (40, 2), (20, 8), (8, 1)]

L1_WAVE_DEFS = [
    {"id": "wd_top_sweep", "name": "Top sweep",
     "attackId": 0,  # ATTACK_TOP_TURN_LEFT
     "composition": [{"enemyType": 0, "count": 5}], "spawnInterval": None},
    {"id": "wd_flank_up", "name": "Left flank U-turn",
     "attackId": 5,  # ATTACK_LEFT_U_TURN_UP
     "composition": [{"enemyType": 2, "count": 5}], "spawnInterval": 14},
]
# worldRow < STAGE_LOGICAL_ROWS (= 400). 372 & 340 are > 255 (16-bit rows).
L1_WAVE_TRIGGERS = [
    {"id": "wt_intro", "worldRow": 372, "waveDef": "wd_top_sweep"},
    {"id": "wt_ridge", "worldRow": 340, "waveDef": "wd_flank_up"},
    {"id": "wt_mid", "worldRow": 300, "waveDef": "wd_top_sweep"},
    {"id": "wt_deep", "worldRow": 200, "waveDef": "wd_flank_up"},
    {"id": "wt_far", "worldRow": 90, "waveDef": "wd_top_sweep"},
]


def _committed_stage_test():
    for ref in ("HEAD:src/generated/level1/stage_test.asm",
                "HEAD:src/generated/stage_test.asm"):
        try:
            return subprocess.check_output(["git", "-C", str(REPO), "show", ref], text=True,
                                           stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue
    # Not committed anywhere yet - fall back to the working copy.
    p = REPO / "src" / "generated" / "level1" / "stage_test.asm"
    return p.read_text(encoding="utf-8")


def build_level1(engine):
    src = _committed_stage_test()
    rows = [r[:] for r in _parse_byte_rows(src, "stageMetatileRows", "STAGE_METATILE_ROWS_END")]
    if len(rows) != 100 or any(len(r) != 10 for r in rows):
        raise SystemExit(f"expected a 100 x 10 committed map, got {len(rows)} rows")

    rows[0] = [M0] * 10
    rows[99] = [M0] * 10
    for r in L1_TOP_BAND:
        rows[r] = [M13_GRILLE] * 10
    for r in L1_BOTTOM_BAND:
        rows[r] = [M1_RFILL] * 10
    for mrow, mcol in L1_TURRETS:
        rows[mrow][mcol] = M14_MACH

    tileset = {
        "glyphCount": engine.glyph_count,
        "glyphs": [list(engine.glyphs[160 + i]) for i in range(engine.glyph_count)],
        "metatileDefs": [list(m) for m in engine.metatiles],
    }
    return LevelProject(
        name=L1_NAME,
        metatile_rows=rows,
        palette=dict(L1_PALETTE),
        scroll_frame_divider=L1_DIVIDER,
        objects=[{"type": "turret", "metatileRow": mr, "metatileCol": mc}
                 for mr, mc in L1_TURRETS],
        metatile_metadata={},
        tileset=tileset,
        wave_definitions=[dict(d) for d in L1_WAVE_DEFS],
        wave_triggers=[dict(t) for t in L1_WAVE_TRIGGERS],
    )


# ---------------------------------------------------------------------------
# Level 2 - planet surface. Editor/export proof only; never imported by
# gameplay. Crude, visibly distinct tileset (level2_tileset.py) + a hand-shaped
# 64-row planet map.
# ---------------------------------------------------------------------------
L2_NAME = "level2"
L2_PALETTE = {"background": 0, "multicolour1": 9, "multicolour2": 8, "character": 1}
L2_DIVIDER = 2
L2_ROWS = 64
L2_TURRETS = [(50, 2), (18, 7)]     # world rows 201 / 73
L2_WAVE_DEFS = [
    {"id": "wd_crater_rush", "name": "Crater rush", "attackId": 2,
     "composition": [{"enemyType": 1, "count": 6}], "spawnInterval": None},
    {"id": "wd_ridge_dive", "name": "Ridge dive", "attackId": 8,
     "composition": [{"enemyType": 3, "count": 5}], "spawnInterval": 16},
]
L2_WAVE_TRIGGERS = [
    {"id": "wt_p_top", "worldRow": 236, "waveDef": "wd_crater_rush"},
    {"id": "wt_p_low", "worldRow": 120, "waveDef": "wd_ridge_dive"},
]


def build_level2():
    # A deterministic planet profile: mostly plain rocky ground with recognisable
    # feature bands. Rows 0 and last kept plain for a clean vertical wrap seam.
    P, GRAVEL, DUST = 0, 1, 13
    CLIFF_TOP, CLIFF_FACE, CLIFF_BASE = 2, 3, 15
    CRATER, CRATER_FLOOR, CRATER_RIM = 4, 5, 14
    STRATA, PIT, PODS, RIDGE, VENTS, CRACKS, SCREE = 6, 7, 8, 9, 10, 11, 12

    feature_rows = {
        3: STRATA, 4: STRATA, 5: STRATA,
        9: CLIFF_TOP, 10: CLIFF_FACE, 11: CLIFF_FACE, 12: CLIFF_BASE,
        16: CRATER_RIM, 17: CRATER, 18: CRATER, 19: CRATER_FLOOR, 20: CRATER_RIM,
        25: RIDGE, 26: RIDGE,
        30: PODS, 31: PODS,
        35: VENTS, 36: VENTS,
        40: PIT, 41: PIT, 42: PIT,
        46: STRATA, 47: STRATA,
        51: CLIFF_TOP, 52: CLIFF_FACE, 53: CLIFF_BASE,
        56: CRACKS, 57: SCREE,
        60: DUST, 61: GRAVEL,
    }
    rows = []
    for i in range(L2_ROWS):
        if i in (0, L2_ROWS - 1):
            rows.append([P] * 10)
            continue
        base = feature_rows.get(i, P)
        row = [base] * 10
        # scatter a couple of contrast tiles so bands are not perfectly flat
        if base == P:
            row[(i * 3) % 10] = GRAVEL
            row[(i * 7) % 10] = DUST
        rows.append(row)
    for mrow, mcol in L2_TURRETS:
        rows[mrow][mcol] = CLIFF_BASE

    return LevelProject(
        name=L2_NAME,
        metatile_rows=rows,
        palette=dict(L2_PALETTE),
        scroll_frame_divider=L2_DIVIDER,
        objects=[{"type": "turret", "metatileRow": mr, "metatileCol": mc}
                 for mr, mc in L2_TURRETS],
        metatile_metadata={},
        tileset=level2_tileset.tileset(),
        wave_definitions=[dict(d) for d in L2_WAVE_DEFS],
        wave_triggers=[dict(t) for t in L2_WAVE_TRIGGERS],
    )


def _emit(project, engine):
    pkg_dir = LEVELS_DIR / project.name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    json_path = pkg_dir / "level.json"
    save_project(project, json_path)
    out_dir = GENERATED / project.name
    paths = export_level(project, out_dir, engine_data=engine)
    print(f"{project.name}: {json_path.relative_to(REPO)}")
    for p in paths:
        print(f"          {p.relative_to(REPO)}")
    print(f"          {project.height} metatile rows ({project.height * 4} logical), "
          f"{len(project.objects)} turrets, {len(project.wave_triggers)} wave triggers")


def main():
    engine = load_engine_data(REPO)
    _emit(build_level1(engine), engine)
    _emit(build_level2(), engine)


if __name__ == "__main__":
    main()
