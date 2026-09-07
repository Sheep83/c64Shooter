#!/usr/bin/env python3
"""Headless smoke of the editor's Terrain Asset Workshop wiring: metatile-set
selector 16 -> 64, native editor, import dialog slicing, undo of a metatile edit.
Constructs real Tk objects but never enters a main loop.

Run:  python3 tools/level_editor/test_editor_workshop_gui.py
Skips cleanly (exit 0) if Tk cannot initialise (no display).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.destroy()
except Exception as exc:                                            # noqa: BLE001
    print(f"SKIP - Tk unavailable ({exc})")
    sys.exit(0)

import editor as ed                                                 # noqa: E402
import workshop_ui as wu                                            # noqa: E402
import project as pj                                                # noqa: E402
from native_metatile import blank_pixels                            # noqa: E402

PASS = []


def ok(msg):
    PASS.append(msg)
    print(f"ok  - {msg}")


FIX = HERE / "testdata" / "synthetic_tileset.png"
if not FIX.exists():
    subprocess.run([sys.executable, str(HERE / "make_test_spritesheet.py")], check=True)

app = ed.LevelEditor(ed.find_repo_root())
try:
    # 1. starts with the historical 16-metatile set + a live glyph budget
    assert app._metatile_count() == 16
    assert "Terrain glyphs" in app.glyph_budget_text.get()
    ok(f"editor boots with 16 metatiles and a glyph budget readout ({app.glyph_budget_text.get()})")

    # 2. New blank metatile -> 17, selectable, undoable
    app._metatile_new_blank()
    assert app._metatile_count() == 17
    assert app.selected_tile == 16
    app._undo()
    assert app._metatile_count() == 16
    app._redo()
    assert app._metatile_count() == 17
    ok("New metatile grows the set to 17 and is undo/redo-safe")

    # 3. NativeMetatileEditor paints and reports cost
    nme = wu.NativeMetatileEditor(
        app, app.project.palette, pixels=blank_pixels(0),
        cost_fn=lambda px: pj.metatile_set_glyph_cost(app.project, candidate_pixels=px))
    nme.pixels[3][5] = 2
    nme._before = blank_pixels(0)
    nme._commit()
    assert nme.get_pixels()[3][5] == 2
    assert "cells" in nme.cost_label.cget("text")
    ok("native 16x32 editor paints a pixel and shows per-metatile glyph cost")

    # 4. Workshop save writes back into the level metatile set + repacks
    before_count = app._metatile_count()
    grid = blank_pixels(1)
    grid[0][0] = 3
    err = None

    def on_save(name, px):
        pj.ensure_level_metatile_set(app.project)
        app.project.level_metatile_set.append(pj.metatile_set_entry_from_native(px, name=name))
        return None if app._repack_after_metatile_edit() else "budget"

    wd = wu.WorkshopDialog(app, app.project.palette, name="ws", pixels=grid, on_save=on_save)
    wd._save_level()
    assert app._metatile_count() == before_count + 1
    # the packed tileset regenerated and stays within the namespace
    assert len(app.project.tileset["glyphs"]) % 8 == 0
    assert len(app.project.tileset["glyphs"]) <= 64
    ok("Workshop save appends to the level set and repacks a valid tileset")

    # 5. Import dialog slices a PNG grid and yields a 32x32 source tile
    picked = {}
    imp = wu.ImportDialog(app, on_pick=lambda rgb, prov: picked.update(rgb=rgb, prov=prov))
    imp._path = str(FIX)
    imp._reslice()
    assert imp.sheet.tile_count == 120
    imp._pick(7)
    assert len(picked["rgb"]) == 32 and len(picked["rgb"][0]) == 32
    assert picked["prov"]["sourceTileIndex"] == 7
    assert picked["prov"]["sourceTileSize"] == [32, 32]
    ok("import dialog slices 32x32 tiles and returns a chosen tile + provenance")

    # 6. capacity guard: cannot exceed 64 live metatiles
    pj.ensure_level_metatile_set(app.project)
    while app._metatile_count() < 64:
        app.project.level_metatile_set.append(
            pj.metatile_set_entry_from_native(blank_pixels(0), name=f"M{app._metatile_count()}"))
    app._repack_after_metatile_edit()
    n = app._metatile_count()
    app._metatile_new_blank()
    assert app._metatile_count() == n == 64
    ok("editor refuses to add a 65th live metatile")

    print(f"\nAll {len(PASS)} editor-workshop GUI smoke checks passed.")
finally:
    app.destroy()
