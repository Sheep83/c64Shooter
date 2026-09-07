#!/usr/bin/env python3
"""Headless regression tests for editor turret placement + bottom-origin data.

Plain assert script (no pytest dependency), matching the repo's tools/check_*.py
style. Run:  python3 tools/level_editor/test_turret_integration.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from engine_data import load_engine_data                       # noqa: E402
from ka_export import render_stage_turrets, export_project      # noqa: E402
from project import (                                           # noqa: E402
    MAX_TURRETS, LevelProject, export_readiness_errors, iter_turrets,
    load_project, project_from_dict, save_project,
    turret_world_col, turret_world_row, validate_project,
)

PASS = []


def ok(msg):
    PASS.append(msg)
    print(f"ok  - {msg}")


def fail(msg):
    print(f"FAIL - {msg}")
    sys.exit(1)


def _project(rows=100, turrets=((30, 3), (70, 7), (89, 4)), **kw):
    return LevelProject(
        name=kw.get("name", "t"),
        metatile_rows=[[0] * 10 for _ in range(rows)],
        palette={"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1},
        scroll_frame_divider=2,
        objects=[{"type": "turret", "metatileRow": r, "metatileCol": c} for r, c in turrets],
    )


# 1. coordinate model: metatile grid -> world char row/col = idx*4 + 1
assert turret_world_row(0) == 1 and turret_world_row(89) == 357
assert turret_world_col(0) == 1 and turret_world_col(7) == 29
ok("coordinate model: world = metatile_index * 4 + 1")

# 2. widened vertical coordinate - no 8-bit limit
big = _project(rows=844, turrets=((0, 0), (200, 5), (700, 9)))
assert validate_project(big) == [], validate_project(big)
rows = [turret_world_row(t["metatileRow"]) for t in iter_turrets(big)]
assert rows == [1, 801, 2801] and max(rows) > 255
asm = render_stage_turrets(big)
assert "turretRows = List().add(1, 801, 2801)" in asm, asm
ok("widened turret vertical coordinate: world rows up to 2801 (>255), 16-bit clean")

# 3. JSON persistence: save -> reload -> identical, and deterministic bytes
p = _project()
with tempfile.TemporaryDirectory() as d:
    a, b = Path(d) / "a.json", Path(d) / "b.json"
    save_project(p, a)
    p2 = load_project(a)
    assert p.canonical_objects() == p2.canonical_objects()
    save_project(p2, b)
    assert a.read_text() == b.read_text(), "save is not deterministic"
    data = json.loads(a.read_text())
    assert data["objects"] == [
        {"type": "turret", "metatileRow": 30, "metatileCol": 3},
        {"type": "turret", "metatileRow": 70, "metatileCol": 7},
        {"type": "turret", "metatileRow": 89, "metatileCol": 4},
    ], data["objects"]
ok("turret JSON persistence: save/reload exact + byte-deterministic")

# 4. export is deterministic and INDEPENDENT of authoring order
p_shuffled = _project(turrets=((89, 4), (30, 3), (70, 7)))
assert render_stage_turrets(p) == render_stage_turrets(p_shuffled), "export depends on order"
assert render_stage_turrets(p).splitlines()[-3:] == [
    ".const TURRET_COUNT = 3",
    ".var turretCols = List().add(13, 29, 17)",
    ".var turretRows = List().add(121, 281, 357)",
]
ok("turret ASM export: deterministic + authoring-order-independent")

# 5. backward compat: V2 file with no/empty 'objects' still loads
legacy = {
    "formatVersion": 2, "name": "legacy", "width": 10, "height": 30,
    "scrollFrameDivider": 2,
    "palette": {"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1},
    "metatileRows": [[0] * 10 for _ in range(30)],
}
lp = project_from_dict(legacy)
assert lp.objects == []
assert validate_project(lp) == []                     # structurally fine
assert export_readiness_errors(lp)                    # ... but not export-ready (needs >=1 turret)
legacy_v1 = dict(legacy, formatVersion=1)
legacy_v1.pop("palette"); legacy_v1.pop("scrollFrameDivider")
assert project_from_dict(legacy_v1).objects == []
ok("backward compat: V1/V2 levels with absent/empty 'objects' load")

# 6. impossible placements rejected
dup = _project(turrets=((5, 3), (5, 7)))
assert any("distinct metatile row" in e for e in validate_project(dup))
too_many = _project(turrets=tuple((i, 0) for i in range(MAX_TURRETS + 1)))
assert any("At most" in e for e in validate_project(too_many))
bad_type = _project()
bad_type.objects.append({"type": "boss", "metatileRow": 1, "metatileCol": 1})
assert any("not supported" in e for e in validate_project(bad_type))
oob = _project(turrets=((30, 3), (70, 7), (500, 4)))   # row 500 > height 100
assert any("metatileRow" in e for e in validate_project(oob))
ok("impossible placements rejected (dup row / >MAX / bad type / out of range)")

# 7. round-trip through the real generated file the engine consumes
d = load_engine_data(REPO)
gen_project = LevelProject(
    name="from-generated", metatile_rows=[r[:] for r in d.stage_rows],
    palette=dict(d.source_palette), scroll_frame_divider=d.source_scroll_frame_divider,
    objects=[dict(t) for t in d.source_turrets],
)
assert validate_project(gen_project) == [], validate_project(gen_project)
assert export_readiness_errors(gen_project) == []
turret_rows = [turret_world_row(t["metatileRow"]) for t in iter_turrets(gen_project)]
assert any(r > 255 for r in turret_rows), turret_rows
ok(f"engine_data reads generated placement: {len(d.source_turrets)} turrets, "
   f"world rows {sorted(turret_rows)} (has >255)")

# 8. export_project writes exactly the 3 engine files
with tempfile.TemporaryDirectory() as td:
    paths = export_project(_project(), d.metatiles, td)
    names = sorted(p.name for p in paths)
    assert names == ["stage_config.asm", "stage_test.asm", "stage_turrets.asm"], names
ok("export_project writes stage_config.asm + stage_test.asm + stage_turrets.asm")

print(f"\nAll {len(PASS)} turret-integration checks passed.")
