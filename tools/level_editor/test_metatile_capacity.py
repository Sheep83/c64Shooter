#!/usr/bin/env python3
"""64-metatile per-level capacity + V1-V3 -> V4 project migration
(task section 7 / 24 / 25 / 29 / 31).

Run:  python3 tools/level_editor/test_metatile_capacity.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from engine_data import (                                           # noqa: E402
    ENGINE_MAX_STAGE_ROWS, METATILE_CAPACITY, METATILE_NAMES, load_engine_data,
)
from native_metatile import blank_pixels                            # noqa: E402
from ka_export import export_level, render_stage_config             # noqa: E402
from project import (                                               # noqa: E402
    FORMAT_VERSION, MAX_STAGE_ROWS, LevelProject, ProjectValidationError,
    derive_metatile_set_from_tileset, ensure_level_metatile_set,
    metatile_set_entry_from_native, project_from_dict,
    repack_tileset_from_metatile_set, save_project, validate_project,
)

PASS = []


def ok(msg):
    PASS.append(msg)
    print(f"ok  - {msg}")


ENGINE = load_engine_data(REPO)
BASE_TILESET = {
    "glyphCount": ENGINE.glyph_count,
    "glyphs": [list(ENGINE.glyphs[160 + i]) for i in range(ENGINE.glyph_count)],
    "metatileDefs": [list(m) for m in ENGINE.metatiles],
}


# A small shared glyph vocabulary: cell -> one of GLYPH_POOL 8-byte bitmaps,
# encoded via the top row's 4 pixels. 64 metatiles built from different
# arrangements of these still need only <= len(GLYPH_POOL) unique glyphs, which
# is the realistic case ("metatiles are cheap; glyphs are precious").
GLYPH_POOL = 40


def _cell_glyph_pixels(g, cr, cc, glyph_id):
    code = glyph_id & 0xFF
    for i in range(4):
        g[cr * 8][cc * 4 + i] = (code >> (2 * (3 - i))) & 3


def _shared_native(seed):
    g = blank_pixels(0)
    for cell in range(16):
        cr, cc = divmod(cell, 4)
        _cell_glyph_pixels(g, cr, cc, (seed * 3 + cr * 4 + cc) % GLYPH_POOL)
    return g


def _level(n_metatiles, rows=40):
    entries = [metatile_set_entry_from_native(_shared_native(k), name=f"M{k}")
               for k in range(n_metatiles)]
    p = LevelProject(
        name="cap", metatile_rows=[[k % n_metatiles for k in range(10)] for _ in range(rows)],
        palette={"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1},
        scroll_frame_divider=2, level_metatile_set=entries,
    )
    repack_tileset_from_metatile_set(p)
    return p


# 1. IDs 0..63 are accepted; a map ID == metatile count is rejected
p64 = _level(64)
assert validate_project(p64) == [], validate_project(p64)
assert len(p64.tileset["metatileDefs"]) == 64
p64.metatile_rows[0][0] = 63
assert validate_project(p64) == []
p64.metatile_rows[0][0] = 64                         # one past the set
errs = validate_project(p64)
assert any("metatile ID 64" in e for e in errs), errs
p64.metatile_rows[0][0] = 0                          # restore for later export checks
assert validate_project(p64) == []
ok("map cells 0..63 accepted; ID == metatile count rejected")

# 2. capacity ceiling: 65 native metatiles rejected
entries65 = [metatile_set_entry_from_native(_shared_native(k), name=f"M{k}") for k in range(65)]
p65 = LevelProject(name="x", metatile_rows=[[0] * 10 for _ in range(20)],
                   palette=p64.palette, scroll_frame_divider=2, level_metatile_set=entries65)
errs = validate_project(p65)
assert any(f"1..{METATILE_CAPACITY}" in e for e in errs), errs
ok(f"levelMetatileSet capped at {METATILE_CAPACITY}; 65 entries rejected")

# 3. stage map stays ONE byte per cell in the exported ASM
with tempfile.TemporaryDirectory() as d:
    paths = export_level(p64, d, engine_data=ENGINE)
    stage_asm = (Path(d) / "stage_test.asm").read_text()
    config_asm = (Path(d) / "stage_config.asm").read_text()
    assert ".const STAGE_METATILE_COUNT   = 64" in config_asm, config_asm
    # every stageMetatileRows .byte line has exactly 10 comma-separated values
    inside = False
    for line in stage_asm.splitlines():
        s = line.strip()
        if s == "stageMetatileRows:":
            inside = True
            continue
        if s == "STAGE_METATILE_ROWS_END:":
            break
        if inside and s.startswith(".byte"):
            vals = [v for v in s.split(".byte", 1)[1].split("//", 1)[0].split(",") if v.strip()]
            assert len(vals) == 10, s
            assert all(0 <= int(v) <= 255 for v in vals)
ok("export: STAGE_METATILE_COUNT=64, stage map is 10 one-byte IDs per row")

# 4. STAGE_METATILE_COUNT tracks the actual set size (not a fixed 64)
with tempfile.TemporaryDirectory() as d:
    export_level(_level(20), d, engine_data=ENGINE)
    assert ".const STAGE_METATILE_COUNT   = 20" in (Path(d) / "stage_config.asm").read_text()
ok("STAGE_METATILE_COUNT is the level's real metatile count (20), no magic 16/64")

# 5. legacy 0..15 metatiles migrate: a V2 file (16 defs) -> V4 with a 16-entry
#    native set, and the packed tileset is preserved so visuals are unchanged
v2 = {
    "formatVersion": 2, "name": "legacy16", "width": 10, "height": 30,
    "scrollFrameDivider": 2,
    "palette": {"background": 0, "multicolour1": 11, "multicolour2": 14, "character": 1},
    "metatileRows": [[i % 16 for i in range(10)] for _ in range(30)],
    "tileset": {"glyphCount": BASE_TILESET["glyphCount"],
                "glyphs": [list(g) for g in BASE_TILESET["glyphs"]],
                "metatileDefs": [list(m) for m in BASE_TILESET["metatileDefs"]]},
}
mp = project_from_dict(v2)
assert validate_project(mp) == []
assert mp.level_metatile_set is not None and len(mp.level_metatile_set) == 16
# names default to the historical METATILE_NAMES
assert [e["name"] for e in mp.level_metatile_set] == list(METATILE_NAMES)
# the packed tileset is UNCHANGED (byte-identical) -> identical visuals
assert mp.tileset["metatileDefs"] == v2["tileset"]["metatileDefs"]
assert mp.tileset["glyphs"] == v2["tileset"]["glyphs"]
# and the derived native set re-packs to an equivalent render of the same tiles
re_derived = derive_metatile_set_from_tileset(mp.tileset)
assert len(re_derived) == 16
ok("legacy 16-metatile V2 migrates to V4: native set derived, packed tileset byte-identical")

# 6. round-trip: save a migrated project (now V4) and reload deterministically
with tempfile.TemporaryDirectory() as d:
    a, b = Path(d) / "a.json", Path(d) / "b.json"
    save_project(mp, a)
    reloaded = json.loads(a.read_text())
    assert reloaded["formatVersion"] == FORMAT_VERSION == 4
    assert "levelMetatileSet" in reloaded and len(reloaded["levelMetatileSet"]) == 16
    mp2 = project_from_dict(reloaded)
    save_project(mp2, b)
    assert a.read_text() == b.read_text(), "migrated project save is not deterministic"
ok("migrated project saves as V4 and re-saves byte-identically (deterministic)")

# 7. editor MAX_STAGE_ROWS is the recalculated 768 (64-metatile worst case)
assert ENGINE_MAX_STAGE_ROWS == 768 == MAX_STAGE_ROWS
tall_ok = LevelProject(name="t", metatile_rows=[[0] * 10 for _ in range(768)],
                       palette=mp.palette, scroll_frame_divider=2, tileset=BASE_TILESET)
assert validate_project(tall_ok) == []
tall_bad = LevelProject(name="t", metatile_rows=[[0] * 10 for _ in range(769)],
                        palette=mp.palette, scroll_frame_divider=2, tileset=BASE_TILESET)
assert any("Stage height" in e for e in validate_project(tall_bad))
ok("stage-row maximum recalculated to 768; 769 rejected by the editor")

print(f"\nAll {len(PASS)} metatile-capacity / migration checks passed.")
