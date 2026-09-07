#!/usr/bin/env python3
"""Regression tests for authored wave definitions + world-row wave triggers.

  * wave definitions + triggers round-trip save/load and export deterministically;
  * composition size is authoritative for wave size (no contradictory `size`);
  * a trigger world row > 255 works;
  * changing SCROLL_FRAME_DIVIDER does NOT move an exported trigger row
    (triggers are anchored to world position, not elapsed frames);
  * catalogue attack names resolve to ids; invalid schema is rejected.

Run:  python3 tools/level_editor/test_wave_schema.py
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from engine_data import ATTACK_COUNT, TERRAIN_GLYPH_BASE, load_engine_data  # noqa: E402
from ka_export import export_level, render_stage_waves                     # noqa: E402
from project import (                                                      # noqa: E402
    LevelProject, composition_size, load_project, save_project, validate_project,
)

PASS = []
D = load_engine_data(REPO)
TILESET = {"glyphCount": D.glyph_count,
           "glyphs": [list(D.glyphs[TERRAIN_GLYPH_BASE + i]) for i in range(D.glyph_count)],
           "metatileDefs": [list(m) for m in D.metatiles]}


def ok(m):
    PASS.append(m)
    print(f"ok  - {m}")


def prj(rows=100, divider=2, defs=None, triggers=None):
    return LevelProject(
        name="w", metatile_rows=[[0] * 10 for _ in range(rows)],
        palette={"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1},
        scroll_frame_divider=divider, tileset=TILESET,
        wave_definitions=defs or [], wave_triggers=triggers or [],
    )


DEFS = [
    {"id": "wd_a", "name": "Alpha", "attackId": 0,
     "composition": [{"enemyType": 0, "count": 5}], "spawnInterval": None},
    {"id": "wd_b", "name": "Bravo", "attackId": 7,
     "composition": [{"enemyType": 3, "count": 6}], "spawnInterval": 12},
]
TRIGGERS = [
    {"id": "t1", "worldRow": 372, "waveDef": "wd_a"},     # > 255
    {"id": "t2", "worldRow": 300, "waveDef": "wd_b"},
    {"id": "t3", "worldRow": 90, "waveDef": "wd_a"},
]

# 1. catalogue exists and covers ATTACK_COUNT ids
names = [n for n, _ in D.attack_catalogue]
ids = sorted(i for _, i in D.attack_catalogue)
assert ids == list(range(ATTACK_COUNT)), ids
assert all(n.startswith("ATTACK_") for n in names)
ok(f"engine attack catalogue parsed: {ATTACK_COUNT} ids, names {names[:2]}..")

# 2. round-trip + deterministic export
p = prj(defs=DEFS, triggers=TRIGGERS)
assert validate_project(p) == [], validate_project(p)
with tempfile.TemporaryDirectory() as td:
    j = Path(td) / "l.json"
    save_project(p, j)
    r = load_project(j, default_tileset=TILESET)
    save_project(r, Path(td) / "b.json")
    assert j.read_text() == (Path(td) / "b.json").read_text(), "wave JSON not deterministic"
    a = export_level(p, Path(td) / "g1", engine_data=D)
    b = export_level(r, Path(td) / "g2", engine_data=D)
    assert all(x.read_text() == y.read_text() for x, y in zip(a, b)), "wave export not deterministic"
    waves = (Path(td) / "g1" / "stage_waves.asm").read_text()
ok("wave definitions + triggers round-trip; stage_waves.asm export deterministic")

# 3. triggers sorted DESCENDING by worldRow; 16-bit split; > 255 handled
assert ".const WAVE_TRIGGER_COUNT = 3" in waves
assert "waveTriggerRowLo = List().add(116, 44, 90)" in waves, waves       # 372,300,90 low bytes
assert "waveTriggerRowHi = List().add(1, 1, 0)" in waves, waves
ok("trigger rows exported 16-bit, descending; world row > 255 handled")

# 4. composition size is authoritative for wave size
assert composition_size(DEFS[1]) == 6
assert "waveTriggerCount = List().add(5, 6, 5)" in waves, waves            # per resolved trigger
assert "size" not in "".join(k for d in DEFS for k in d)                   # no contradictory 'size' key
ok("composition size is the wave size (waveTriggerCount); no separate 'size' stored")

# 5. SCROLL_FRAME_DIVIDER does not move a trigger's terrain-relative position
w_div2 = render_stage_waves(prj(divider=2, defs=DEFS, triggers=TRIGGERS), D)
w_div5 = render_stage_waves(prj(divider=5, defs=DEFS, triggers=TRIGGERS), D)
lo2 = [l for l in w_div2.splitlines() if "waveTriggerRow" in l]
lo5 = [l for l in w_div5.splitlines() if "waveTriggerRow" in l]
assert lo2 == lo5, (lo2, lo5)
ok("changing SCROLL_FRAME_DIVIDER leaves every exported trigger row byte identical")

# 6. schema validation rejects bad input
bad = prj(defs=[{"id": "x", "name": "x", "attackId": 99,
                 "composition": [{"enemyType": 0, "count": 5}]}],
          triggers=[{"id": "t", "worldRow": 10, "waveDef": "x"}])
assert any("attackId" in e for e in validate_project(bad))
bad2 = prj(defs=DEFS, triggers=[{"id": "t", "worldRow": 99999, "waveDef": "wd_a"}])
assert any("worldRow" in e for e in validate_project(bad2))
bad3 = prj(defs=DEFS, triggers=[{"id": "t", "worldRow": 10, "waveDef": "nope"}])
assert any("waveDef" in e for e in validate_project(bad3))
ok("wave schema rejects bad attackId / out-of-range worldRow / dangling waveDef ref")

print(f"\nAll {len(PASS)} wave-schema checks passed.")
