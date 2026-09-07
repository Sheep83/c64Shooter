"""Tkinter dialogs for the Terrain Asset Workshop and the source-spritesheet
importer. Kept out of editor.py so that file stays navigable; these use only the
existing Tkinter stack (no new framework) and the shared C64 colour table.

  NativeMetatileEditor  - a reusable zoomed 16x32 multicolour paint canvas with
                          4 project-palette swatches, click/drag paint, visible
                          4x4-char boundaries and a live glyph-cost readout.
  WorkshopDialog        - source preview (optional) beside the native editor;
                          Save writes back a native pixel grid + name (+ repo).
  ImportDialog          - choose a PNG, set tile size, browse cached thumbnails,
                          pick one tile -> convert -> open the Workshop.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from engine_data import C64_PALETTE_HEX
from native_metatile import (
    CHAR_H, CHAR_W, CHARS_PER_SIDE, NATIVE_H, NATIVE_W, blank_pixels,
    pixels_to_glyphs, validate_pixels,
)
from spritesheet import slice_sheet
from terrain_convert import source_tile_to_native

LOGICAL_KEYS = ("background", "multicolour1", "multicolour2", "character")
LOGICAL_LABELS = ("0 bg", "1 mc1", "2 mc2", "3 char")


def _logical_hex(project_palette):
    return [C64_PALETTE_HEX[int(project_palette[k]) & 0x0F] for k in LOGICAL_KEYS]


class NativeMetatileEditor(ttk.Frame):
    """Zoomed paint canvas for one native 16x32 metatile (values 0..3)."""

    def __init__(self, master, project_palette, pixels=None, zoom=14,
                 on_change=None, cost_fn=None):
        super().__init__(master)
        self.palette = dict(project_palette)
        self.zoom = zoom
        self.pixels = validate_pixels(pixels) if pixels is not None else blank_pixels(0)
        self.on_change = on_change
        self.cost_fn = cost_fn                    # pixels -> dict(used,capacity,candidate_new,...)
        self.active = tk.IntVar(value=3)
        self._undo, self._redo = [], []

        swatches = ttk.Frame(self)
        swatches.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._swatch_widgets = []
        for i, label in enumerate(LOGICAL_LABELS):
            b = tk.Button(swatches, text=label, width=6,
                          command=lambda v=i: self.active.set(v))
            b.grid(row=0, column=i, padx=2)
            self._swatch_widgets.append(b)
        self._guides = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text="4x4 char guides", command=self._redraw,
                        variable=self._guides).grid(row=0, column=1, sticky="e")

        self.canvas = tk.Canvas(self, width=NATIVE_W * zoom, height=NATIVE_H * zoom,
                                highlightthickness=1, highlightbackground="#888",
                                background="#101010")
        self.canvas.grid(row=1, column=0, columnspan=2)
        self.canvas.bind("<Button-1>", self._paint_start)
        self.canvas.bind("<B1-Motion>", self._paint_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._commit())

        self.cost_label = ttk.Label(self, text="")
        self.cost_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self._before = None
        self._apply_palette_to_swatches()
        self._redraw()

    # -- palette / redraw --------------------------------------------------
    def set_palette(self, project_palette):
        self.palette = dict(project_palette)
        self._apply_palette_to_swatches()
        self._redraw()

    def _apply_palette_to_swatches(self):
        for i, hexc in enumerate(_logical_hex(self.palette)):
            fg = "#000" if i in (1, 3) else "#fff"
            self._swatch_widgets[i].configure(background=hexc, activebackground=hexc,
                                              foreground=fg)

    def _redraw(self):
        self.canvas.delete("all")
        z = self.zoom
        hexes = _logical_hex(self.palette)
        for y in range(NATIVE_H):
            for x in range(NATIVE_W):
                self.canvas.create_rectangle(
                    x * z, y * z, x * z + z, y * z + z,
                    fill=hexes[self.pixels[y][x]], outline="#333")
        if self._guides.get():
            for c in range(1, CHARS_PER_SIDE):
                self.canvas.create_line(c * CHAR_W * z, 0, c * CHAR_W * z, NATIVE_H * z,
                                        fill="#ffd000", width=2)
            for r in range(1, CHARS_PER_SIDE):
                self.canvas.create_line(0, r * CHAR_H * z, NATIVE_W * z, r * CHAR_H * z,
                                        fill="#ffd000", width=2)
        self._update_cost()

    def _update_cost(self):
        if not self.cost_fn:
            self.cost_label.configure(text="")
            return
        info = self.cost_fn(self.pixels)
        self.cost_label.configure(
            text=(f"Terrain glyphs: {info['used']} / {info['capacity']}   |   "
                  f"this metatile: 16 cells, {info['candidate_reuse']} existing reused, "
                  f"{info['candidate_new']} new unique required"))

    # -- painting -------------------------------------------------------
    def _cell(self, event):
        x = int(self.canvas.canvasx(event.x)) // self.zoom
        y = int(self.canvas.canvasy(event.y)) // self.zoom
        if 0 <= x < NATIVE_W and 0 <= y < NATIVE_H:
            return x, y
        return None

    def _paint_start(self, event):
        self._before = [row[:] for row in self.pixels]
        self._paint_drag(event)

    def _paint_drag(self, event):
        cell = self._cell(event)
        if not cell:
            return
        x, y = cell
        v = self.active.get()
        if self.pixels[y][x] != v:
            self.pixels[y][x] = v
            z = self.zoom
            self.canvas.create_rectangle(x * z, y * z, x * z + z, y * z + z,
                                         fill=_logical_hex(self.palette)[v], outline="#333")
            self._update_cost()

    def _commit(self):
        if self._before is not None and self._before != self.pixels:
            self._undo.append(self._before)
            self._redo.clear()
            if self.on_change:
                self.on_change()
        self._before = None

    def undo(self):
        if self._undo:
            self._redo.append([r[:] for r in self.pixels])
            self.pixels = self._undo.pop()
            self._redraw()

    def redo(self):
        if self._redo:
            self._undo.append([r[:] for r in self.pixels])
            self.pixels = self._redo.pop()
            self._redraw()

    def get_pixels(self):
        return [row[:] for row in self.pixels]


class WorkshopDialog(tk.Toplevel):
    """Turn a source tile (or a blank canvas) into an editable native C64
    multicolour metatile. `on_save(name, pixels)` is called when the user saves;
    it should update the project and return None or an error string."""

    def __init__(self, master, project_palette, *, title="Terrain Asset Workshop",
                 name="metatile", pixels=None, source_rgb=None, cost_fn=None,
                 on_save=None, allow_repo_save=None):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.on_save = on_save
        self.allow_repo_save = allow_repo_save          # callable(name, pixels) or None
        self.result = None

        top = ttk.Frame(self, padding=10)
        top.pack(fill="both", expand=True)

        if source_rgb is not None:
            src = ttk.LabelFrame(top, text="Source tile (image)", padding=6)
            src.grid(row=0, column=0, padx=(0, 12), sticky="n")
            h = len(source_rgb)
            w = len(source_rgb[0]) if h else 0
            zoom = max(1, 224 // max(w, 1))
            c = tk.Canvas(src, width=w * zoom, height=h * zoom, highlightthickness=0)
            c.pack()
            img = tk.PhotoImage(width=w * zoom, height=h * zoom)
            img.put(" ".join(
                "{" + " ".join("#%02x%02x%02x" % tuple(source_rgb[y][x]) for x in range(w)
                               for _ in range(zoom)) + "}"
                for y in range(h) for _ in range(zoom)))
            c.create_image(0, 0, anchor="nw", image=img)
            c._img = img                                # keep a ref

        edit = ttk.LabelFrame(top, text="Native C64 multicolour (16 x 32 logical pixels)", padding=6)
        edit.grid(row=0, column=1, sticky="n")
        namebar = ttk.Frame(edit)
        namebar.pack(fill="x", pady=(0, 6))
        ttk.Label(namebar, text="Name").pack(side="left")
        self.name_var = tk.StringVar(value=name)
        ttk.Entry(namebar, textvariable=self.name_var, width=26).pack(side="left", padx=6)

        self.editor = NativeMetatileEditor(edit, project_palette, pixels=pixels,
                                           cost_fn=cost_fn)
        self.editor.pack()
        self.bind("<Control-z>", lambda e: self.editor.undo())
        self.bind("<Control-Shift-Z>", lambda e: self.editor.redo())

        btns = ttk.Frame(top)
        btns.grid(row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        if allow_repo_save:
            ttk.Button(btns, text="Save to repository…", command=self._save_repo).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(btns, text="Save to level", command=self._save_level).pack(side="left", padx=4)

        self.grab_set()

    def _save_level(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Name required", "Give the metatile a name.", parent=self)
            return
        err = self.on_save(name, self.editor.get_pixels()) if self.on_save else None
        if err:
            messagebox.showerror("Cannot save", err, parent=self)
            return
        self.result = (name, self.editor.get_pixels())
        self.destroy()

    def _save_repo(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Name required", "Give the asset a name.", parent=self)
            return
        err = self.allow_repo_save(name, self.editor.get_pixels())
        if err:
            messagebox.showerror("Repository", err, parent=self)
        else:
            messagebox.showinfo("Repository", f"Saved '{name}' to the terrain repository.", parent=self)


class ImportDialog(tk.Toplevel):
    """Choose a source spritesheet, slice it, browse cached thumbnails, and pick
    one tile. `on_pick(rgb_rows, provenance)` is called with the chosen tile."""

    def __init__(self, master, *, on_pick=None, initial_dir=None):
        super().__init__(master)
        self.title("Import source spritesheet")
        self.transient(master)
        self.on_pick = on_pick
        self.sheet = None
        self._thumbs = []

        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="Choose PNG…", command=self._choose).pack(side="left")
        ttk.Label(bar, text="  Tile W").pack(side="left")
        self.tw = tk.IntVar(value=32)
        ttk.Spinbox(bar, from_=1, to=256, width=5, textvariable=self.tw,
                    command=self._reslice).pack(side="left")
        ttk.Label(bar, text=" H").pack(side="left")
        self.th = tk.IntVar(value=32)
        ttk.Spinbox(bar, from_=1, to=256, width=5, textvariable=self.th,
                    command=self._reslice).pack(side="left")
        self.info = ttk.Label(bar, text="no sheet loaded")
        self.info.pack(side="left", padx=10)

        body = ttk.Frame(self, padding=(8, 0, 8, 8))
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, width=560, height=420, background="#181818",
                                highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._initial_dir = initial_dir

    def _choose(self):
        path = filedialog.askopenfilename(
            title="Source spritesheet (PNG)", initialdir=self._initial_dir,
            filetypes=(("PNG image", "*.png"), ("All files", "*.*")), parent=self)
        if not path:
            return
        self._path = path
        self._reslice()

    def _reslice(self):
        if not getattr(self, "_path", None):
            return
        try:
            self.sheet = slice_sheet(self._path, self.tw.get(), self.th.get())
        except Exception as exc:                          # noqa: BLE001 - surface to user
            messagebox.showerror("Import", str(exc), parent=self)
            return
        warn = ("  ⚠ " + "; ".join(self.sheet.warnings)) if self.sheet.warnings else ""
        self.info.configure(
            text=f"{self.sheet.width}x{self.sheet.height}px → "
                 f"{self.sheet.cols_count}×{self.sheet.rows_count} tiles{warn}")
        self._render_thumbs()

    def _render_thumbs(self):
        self.canvas.delete("all")
        self._thumbs.clear()
        s = self.sheet
        pad, cell = 6, 40
        per_row = max(1, 560 // (cell + pad))
        for idx in range(s.tile_count):
            r, c = divmod(idx, per_row)
            x, y = pad + c * (cell + pad), pad + r * (cell + pad)
            tile = s.tile(idx)
            step = max(1, s.tile_w // cell)
            img = tk.PhotoImage(width=cell, height=cell)
            rowspec = []
            for ty in range(0, cell):
                sy = min(s.tile_h - 1, ty * step)
                rowspec.append("{" + " ".join(
                    "#%02x%02x%02x" % tuple(tile[sy][min(s.tile_w - 1, tx * step)])
                    for tx in range(cell)) + "}")
            img.put(" ".join(rowspec))
            self._thumbs.append(img)
            tag = f"t{idx}"
            self.canvas.create_image(x, y, anchor="nw", image=img, tags=tag)
            self.canvas.tag_bind(tag, "<Button-1>", lambda e, i=idx: self._pick(i))
        rows = (s.tile_count + per_row - 1) // per_row
        self.canvas.configure(scrollregion=(0, 0, 560, pad + rows * (cell + pad)))

    def _pick(self, idx):
        col, row = self.sheet.tile_coords(idx)
        prov = {
            "sourcePack": "",
            "sourceTileIndex": idx,
            "sourceCoords": [col, row],
            "sourceTileSize": [self.sheet.tile_w, self.sheet.tile_h],
            "localSourcePath": str(self.sheet.path),
        }
        if self.on_pick:
            self.on_pick(self.sheet.tile(idx), prov)
        self.destroy()
