#!/usr/bin/env python3
"""Generated native bas-relief terrain tiles + their install into Level 1
(objective 3).

Run:  python3 tools/level_editor/test_native_terrain_tiles.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import native_terrain_tiles as ntt                                  # noqa: E402
from engine_data import TERRAIN_GLYPH_NAMESPACE, load_engine_data   # noqa: E402
from ka_export import export_level                                  # noqa: E402
from native_metatile import (                                       # noqa: E402
    NATIVE_H, NATIVE_W, pack_metatiles, validate_pixels,
)
from project import (                                               # noqa: E402
    LevelProject, load_project, metatile_set_entry_from_native,
    metatile_set_glyph_cost, project_from_dict, repack_tileset_from_metatile_set,
    save_project, validate_project,
)

PASS = []


def ok(msg):
    PASS.append(msg)
    print(f"ok  - {msg}")


tiles = ntt.metatiles()

# 1. every generated metatile is a valid 16x32 grid of values 0..3
assert 20 <= len(tiles) <= 32, f"expected ~20..32 metatiles, got {len(tiles)}"
seen_names = set()
for name, px in tiles:
    assert isinstance(name, str) and name and name not in seen_names, name
    seen_names.add(name)
    grid = validate_pixels(px)
    assert len(grid) == NATIVE_H and all(len(r) == NATIVE_W for r in grid)
    assert {v for r in grid for v in r} <= {0, 1, 2, 3}
ok(f"{len(tiles)} generated metatiles: all valid {NATIVE_W}x{NATIVE_H}, values 0..3, unique names")

# 2. no ACCIDENTAL isolated single-logical-pixel noise: every non-background
#    pixel touches another pixel of the same value (4-neighbour), except where a
#    single stud/rivet is clearly intended (allow a small budget per tile).
def isolated_count(grid):
    n = 0
    for y in range(NATIVE_H):
        for x in range(NATIVE_W):
            v = grid[y][x]
            if v == 0:
                continue
            nb = []
            if x: nb.append(grid[y][x-1])
            if x < NATIVE_W-1: nb.append(grid[y][x+1])
            if y: nb.append(grid[y-1][x])
            if y < NATIVE_H-1: nb.append(grid[y+1][x])
            if v not in nb:
                n += 1
    return n
worst = max((isolated_count(validate_pixels(px)), name) for name, px in tiles)
# A small budget covers deliberate rivets/studs and the curved landmark tiles
# (CORE gradient); a checker/dither field would blow well past this.
assert worst[0] <= 10, f"tile {worst[1]} has {worst[0]} isolated logical pixels (visual noise)"
ok(f"no logical-pixel noise: worst tile has {worst[0]} isolated pixels (<= 10 budget)")

# 3. glyph packing / dedup succeeds and is materially efficient
grids = [px for _, px in tiles]
packed = pack_metatiles(grids)
assert packed["glyphCount"] <= TERRAIN_GLYPH_NAMESPACE
assert len(packed["metatileDefs"]) == len(tiles)
naive = len(tiles) * 16
assert packed["glyphCount"] < naive // 4, \
    f"{packed['glyphCount']} glyphs not materially better than naive {naive}"
ok(f"packer: {len(tiles)} metatiles -> {packed['glyphCount']} unique glyphs "
   f"(naive {naive}; {naive / packed['glyphCount']:.0f}x denser)")

# 4. deterministic
assert pack_metatiles(grids) == packed
assert [n for n, _ in ntt.metatiles()] == [n for n, _ in ntt.metatiles()]
ok("generated set + packing are deterministic")

# 5. loads into a project with NO migration hacks; repack + validate clean
p = LevelProject(
    name="ntt", metatile_rows=[[i % len(tiles) for i in range(10)] for _ in range(30)],
    palette={"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1},
    scroll_frame_divider=2,
    level_metatile_set=[metatile_set_entry_from_native(px, name=nm) for nm, px in tiles],
)
repack_tileset_from_metatile_set(p)
assert validate_project(p) == [], validate_project(p)
cost = metatile_set_glyph_cost(p)
assert cost["used"] == packed["glyphCount"] and cost["capacity"] == TERRAIN_GLYPH_NAMESPACE
ok(f"generated set loads + validates in a project; glyph cost {cost['used']}/{cost['capacity']}")

# 6. save/reload/export deterministic
eng = load_engine_data(REPO)
with tempfile.TemporaryDirectory() as d:
    a, b = Path(d) / "a.json", Path(d) / "b.json"
    save_project(p, a)
    p2 = project_from_dict(json.loads(a.read_text()))
    save_project(p2, b)
    assert a.read_text() == b.read_text()
    g1, g2 = Path(d) / "g1", Path(d) / "g2"
    export_level(p2, g1, engine_data=eng)
    export_level(project_from_dict(json.loads(b.read_text())), g2, engine_data=eng)
    for fn in ("stage_test.asm", "stage_charset.asm", "stage_config.asm"):
        assert (g1 / fn).read_text() == (g2 / fn).read_text(), fn
ok("save / reload / export of the generated set are deterministic")

# 7. the COMMITTED Level 1 now carries the generated set, turrets/waves intact
l1 = load_project(HERE / "levels" / "level1" / "level.json")
l1_names = {e["name"] for e in l1.level_metatile_set}
assert l1_names == seen_names, "Level 1 metatile set is not the generated native set"
assert len([o for o in l1.objects if o.get("type") == "turret"]) == 9
assert len(l1.wave_triggers) == 5
used = sorted({c for row in l1.metatile_rows for c in row})
assert used and used[-1] < len(l1.level_metatile_set)
assert used[-1] >= 15, "map should exercise the new higher metatile ids (demo patch)"
repack_tileset_from_metatile_set(l1)
assert l1.tileset["glyphCount"] <= TERRAIN_GLYPH_NAMESPACE
assert validate_project(l1) == []
ok(f"committed Level 1: {len(l1.level_metatile_set)} generated metatiles, "
   f"{l1.tileset['glyphCount']} glyphs, 9 turrets + 5 wave triggers preserved, "
   f"map uses ids {used[0]}..{used[-1]}")

# 8. Level 2 is unchanged (still its own planet tileset, not the sci-fi set)
l2 = load_project(HERE / "levels" / "level2" / "level.json")
assert {e["name"] for e in l2.level_metatile_set} != seen_names
ok("Level 2 metatile set untouched")

print(f"\nAll {len(PASS)} native-terrain-tiles checks passed.")
