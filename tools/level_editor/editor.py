#!/usr/bin/env python3
"""19656 standalone Tkinter level editor.

A level is a PACKAGE: terrain map + palette/config + authored turrets + its own
terrain tileset + enemy-wave timing, saved as levels/<name>/level.json. The
editor also shows an editor-only overlay of the real C64 gameplay terrain
aperture (40 chars x 23 logical rows, bottom-origin) so turret density and wave
timing can be authored against true world coordinates.
"""
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from engine_data import (
    DEFAULT_PALETTE,
    DEFAULT_SCROLL_FRAME_DIVIDER,
    ENEMY_TYPE_COUNT,
    METATILE_H,
    METATILE_NAMES,
    METATILE_W,
    METATILES_PER_ROW,
    VIEWPORT_ROWS,
    load_engine_data,
)
from ka_export import export_level
from project import (
    DEFAULT_STAGE_ROWS,
    LevelProject,
    MAX_STAGE_ROWS,
    MAX_TURRETS,
    MIN_STAGE_ROWS,
    OBJECT_TYPE_TURRET,
    ProjectValidationError,
    TURRET_POOL,
    WAVE_MAX_COMPOSITION_COUNT,
    clamp_viewport_top,
    composition_size,
    default_viewport_top,
    export_readiness_errors,
    iter_turrets,
    load_project,
    max_viewport_top,
    save_project,
    stage_logical_rows,
    turret_world_col,
    turret_world_row,
    validate_project,
    wrap_seam_warning,
    turret_screen_peak,
)

CHAR_SIZE = 8
METATILE_PIXELS = METATILE_W * CHAR_SIZE
LEVEL_WIDTH = METATILES_PER_ROW * METATILE_PIXELS
PAL_FRAMES_PER_SECOND = 50
# Approximate C64 palette for editor preview. Project data stores indices, not RGB.
C64_COLOURS = (
    "#000000", "#ffffff", "#813338", "#75cec8",
    "#8e3c97", "#56ac4d", "#2e2c9b", "#edf171",
    "#8e5029", "#553800", "#c46c71", "#4a4a4a",
    "#7b7b7b", "#a9ff9f", "#706deb", "#b2b2b2",
)
GRID = "#555555"
SELECTED = "#ffffff"
VIEWPORT_EDGE = "#38d0ff"
VIEWPORT_ACTIVATION = "#ffd000"
TRIGGER_COLOUR = "#ff40c0"
TRIGGER_HIT = 6            # px tolerance when clicking a trigger flag


def _next_id(prefix, existing):
    n = 1
    used = {str(x.get("id")) for x in existing}
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


class LevelEditor(tk.Tk):
    def __init__(self, repo_root):
        super().__init__()
        self.repo_root = Path(repo_root)
        self.data = load_engine_data(self.repo_root)
        self.levels_dir = self.repo_root / "tools" / "level_editor" / "levels"
        self.legacy_dir = self.repo_root / "tools" / "level_editor" / "projects"
        self.levels_dir.mkdir(parents=True, exist_ok=True)

        self.attack_names = [n for n, _ in self.data.attack_catalogue]
        self.attack_id_by_name = {n: i for n, i in self.data.attack_catalogue}
        self.attack_name_by_id = {i: n for n, i in self.data.attack_catalogue}

        self.project = self._seed_project("level1", [row[:] for row in self.data.stage_rows],
                                          dict(self.data.source_palette),
                                          self.data.source_scroll_frame_divider,
                                          objects=[dict(t) for t in self.data.source_turrets])
        self.project_path = None
        self.viewport_top = default_viewport_top(self.project)

        self.selected_tile = 0
        self.metatile_image_cache = {}
        self.last_painted_cell = None
        self.edit_mode = tk.StringVar(value="terrain")   # terrain | turret | wave
        self.selected_turret = None
        self.selected_trigger = None                      # index into project.wave_triggers
        self.selected_wave_def = None                     # index into project.wave_definitions
        self._dragging_trigger = False
        self.show_grid = tk.BooleanVar(value=True)
        self.stage_row_count = tk.IntVar(value=self.project.height)
        self.viewport_var = tk.IntVar(value=self.viewport_top)
        self.duration_text = tk.StringVar()
        self.viewport_text = tk.StringVar()
        self.status_text = tk.StringVar()
        self.scroll_divider_var = tk.IntVar(value=self.project.scroll_frame_divider)
        self.palette_vars = {
            key: tk.IntVar(value=self.project.palette[key])
            for key in ("background", "multicolour1", "multicolour2", "character")
        }
        # wave-definition editor vars
        self.wd_name_var = tk.StringVar()
        self.wd_attack_var = tk.StringVar()
        self.wd_enemy_var = tk.IntVar(value=0)
        self.wd_count_var = tk.IntVar(value=5)
        self.wd_interval_var = tk.StringVar()
        self.wt_row_var = tk.IntVar(value=0)
        self.wt_def_var = tk.StringVar()

        self.saved_state = self._project_state()
        self.undo_stack = []
        self.redo_stack = []
        self.paint_gesture_before = None

        self.geometry("1120x920")
        self.minsize(900, 640)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menu()
        self._build_ui()
        self._refresh_all()

    # ---- project construction ------------------------------------------
    def _baseline_tileset(self):
        return {
            "glyphCount": self.data.glyph_count,
            "glyphs": [list(self.data.glyphs[160 + i]) for i in range(self.data.glyph_count)],
            "metatileDefs": [list(m) for m in self.data.metatiles],
        }

    def _seed_project(self, name, rows, palette, divider, objects=None,
                      wave_definitions=None, wave_triggers=None, tileset=None):
        return LevelProject(
            name=name, metatile_rows=rows, palette=palette, scroll_frame_divider=divider,
            objects=objects or [], tileset=tileset or self._baseline_tileset(),
            wave_definitions=wave_definitions or [], wave_triggers=wave_triggers or [],
        )

    @property
    def stage_rows(self):
        return self.project.metatile_rows

    @property
    def level_height(self):
        return self.project.height * METATILE_PIXELS

    # ---- undo/dirty state --------------------------------------------------
    def _project_state(self):
        return (
            self.project.name,
            tuple(tuple(row) for row in self.project.metatile_rows),
            tuple(sorted(self.project.palette.items())),
            self.project.scroll_frame_divider,
            tuple(self._obj_key(o) for o in self.project.objects),
            tuple(sorted(self.project.metatile_metadata.items())),
            json.dumps(self.project.canonical_wave_definitions(), sort_keys=True),
            json.dumps(self.project.canonical_wave_triggers(), sort_keys=True),
            json.dumps(self.project.tileset, sort_keys=True) if self.project.tileset else None,
        )

    @staticmethod
    def _obj_key(obj):
        if isinstance(obj, dict):
            return tuple(sorted((k, v) for k, v in obj.items()
                                if not isinstance(v, (list, dict))))
        return ("_opaque", repr(obj))

    @staticmethod
    def _obj_from_key(key):
        if key and key[0] == "_opaque":
            return None
        return {k: v for k, v in key}

    def _is_dirty(self):
        return self._project_state() != self.saved_state

    # ---- menu -----------------------------------------------------------
    def _build_menu(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="New Level…", accelerator="Ctrl+N", command=self._new_level)
        file_menu.add_command(label="Open Level…", accelerator="Ctrl+O", command=self._open_level)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self._save_project)
        file_menu.add_command(label="Save As…", accelerator="Ctrl+Shift+S", command=self._save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export level package…", command=self._export_kickassembler)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", accelerator="Ctrl+Q", command=self._on_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        self.edit_menu = tk.Menu(menu_bar, tearoff=False)
        self.edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self._undo)
        self.edit_menu.add_command(label="Redo", accelerator="Ctrl+Shift+Z", command=self._redo)
        menu_bar.add_cascade(label="Edit", menu=self.edit_menu)
        self.config(menu=menu_bar)

        for seq, fn in (("<Control-n>", self._new_level), ("<Control-o>", self._open_level),
                        ("<Control-s>", self._save_project), ("<Control-Shift-S>", self._save_project_as),
                        ("<Control-z>", self._undo), ("<Control-Shift-Z>", self._redo),
                        ("<Control-q>", self._on_close)):
            self.bind_all(seq, lambda e, f=fn: f())
            if sys.platform == "darwin":
                self.bind_all(seq.replace("Control", "Command"), lambda e, f=fn: f())

    # ---- UI -----------------------------------------------------------
    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="19656 Level Editor", font=("TkDefaultFont", 12, "bold")).pack(side="left")
        ttk.Checkbutton(toolbar, text="Metatile grid", variable=self.show_grid,
                        command=self._draw_level).pack(side="right")
        ttk.Label(toolbar, text="   Mode:").pack(side="left", padx=(16, 2))
        for text, value in (("Terrain", "terrain"), ("Turrets", "turret"), ("Waves", "wave")):
            ttk.Radiobutton(toolbar, text=text, value=value, variable=self.edit_mode,
                            command=self._on_mode_change).pack(side="left")
        self.delete_turret_button = ttk.Button(toolbar, text="Delete turret",
                                               command=self._delete_selected_turret, state="disabled")
        self.delete_turret_button.pack(side="left", padx=(8, 0))

        stage_controls = ttk.Frame(self, padding=(8, 0, 8, 4))
        stage_controls.pack(fill="x")
        ttk.Label(stage_controls, text="Stage rows:").pack(side="left")
        self.stage_rows_spinbox = ttk.Spinbox(stage_controls, from_=MIN_STAGE_ROWS, to=MAX_STAGE_ROWS,
                                              width=6, textvariable=self.stage_row_count,
                                              command=self._apply_stage_row_count)
        self.stage_rows_spinbox.pack(side="left", padx=(5, 8))
        self.stage_rows_spinbox.bind("<Return>", self._apply_stage_row_count)
        self.stage_rows_spinbox.bind("<FocusOut>", self._apply_stage_row_count)
        ttk.Label(stage_controls, textvariable=self.duration_text).pack(side="left")

        # Gameplay viewport overlay controls (editor-only; never saved/exported).
        vp = ttk.Frame(self, padding=(8, 0, 8, 4))
        vp.pack(fill="x")
        ttk.Label(vp, text="Gameplay view:").pack(side="left")
        self.viewport_scale = ttk.Scale(vp, from_=0, to=max(1, max_viewport_top(self.project)),
                                        orient="horizontal", command=self._on_viewport_scrub)
        self.viewport_scale.pack(side="left", fill="x", expand=True, padx=(6, 8))
        ttk.Label(vp, textvariable=self.viewport_text).pack(side="left")

        level_settings = ttk.Frame(self, padding=(8, 0, 8, 4))
        level_settings.pack(fill="x")
        ttk.Label(level_settings, text="Palette:").pack(side="left")
        for label, key, maximum in (("BG", "background", 15), ("MC1", "multicolour1", 15),
                                    ("MC2", "multicolour2", 15), ("CHAR", "character", 7)):
            ttk.Label(level_settings, text=label).pack(side="left", padx=(8, 2))
            spin = ttk.Spinbox(level_settings, from_=0, to=maximum, width=3,
                               textvariable=self.palette_vars[key], command=self._apply_level_settings)
            spin.pack(side="left")
            spin.bind("<Return>", self._apply_level_settings)
            spin.bind("<FocusOut>", self._apply_level_settings)
        ttk.Label(level_settings, text="Scroll divider").pack(side="left", padx=(14, 2))
        divider_spin = ttk.Spinbox(level_settings, from_=1, to=255, width=4,
                                   textvariable=self.scroll_divider_var, command=self._apply_level_settings)
        divider_spin.pack(side="left")
        divider_spin.bind("<Return>", self._apply_level_settings)
        divider_spin.bind("<FocusOut>", self._apply_level_settings)

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        palette_frame = ttk.LabelFrame(body, text="Metatiles", padding=6)
        palette_frame.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        palette_frame.rowconfigure(0, weight=1)
        self.palette_canvas = tk.Canvas(palette_frame, width=210, highlightthickness=0,
                                        background=self.cget("background"))
        pscroll = ttk.Scrollbar(palette_frame, orient="vertical", command=self.palette_canvas.yview)
        self.palette_canvas.configure(yscrollcommand=pscroll.set)
        self.palette_canvas.grid(row=0, column=0, sticky="nsew")
        pscroll.grid(row=0, column=1, sticky="ns")
        self.palette_canvas.bind("<Button-1>", self._palette_click)
        self._bind_mousewheel(self.palette_canvas)

        self.level_frame = ttk.LabelFrame(body, text="Working stage", padding=6)
        self.level_frame.grid(row=0, column=1, sticky="nsew")
        self.level_frame.columnconfigure(0, weight=1)
        self.level_frame.rowconfigure(0, weight=1)
        self.level_canvas = tk.Canvas(self.level_frame, width=LEVEL_WIDTH, height=700,
                                      background=C64_COLOURS[self.project.palette["background"]],
                                      scrollregion=(0, 0, LEVEL_WIDTH, self.level_height),
                                      highlightthickness=0)
        yscroll = ttk.Scrollbar(self.level_frame, orient="vertical", command=self.level_canvas.yview)
        self.level_canvas.configure(yscrollcommand=yscroll.set)
        self.level_canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self.level_canvas.bind("<Button-1>", self._level_click_start)
        self.level_canvas.bind("<B1-Motion>", self._level_drag)
        self.level_canvas.bind("<ButtonRelease-1>", self._level_click_end)
        self.level_canvas.bind("<Button-3>", self._level_right_click)
        self.level_canvas.bind("<Control-Button-1>", self._level_right_click)
        self.level_canvas.bind("<Shift-MouseWheel>", self._viewport_wheel)
        self.level_canvas.bind("<Up>", lambda e: self._nudge_viewport(-1))
        self.level_canvas.bind("<Down>", lambda e: self._nudge_viewport(1))
        self.bind_all("<Delete>", self._delete_selected)
        self.bind_all("<BackSpace>", self._delete_selected)
        self._bind_mousewheel(self.level_canvas)

        self._build_wave_panel(body)

        status = ttk.Frame(self, padding=(8, 2, 8, 8))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_text).pack(side="left")

    def _build_wave_panel(self, body):
        self.wave_frame = ttk.LabelFrame(body, text="Waves", padding=6)
        self.wave_frame.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        ttk.Label(self.wave_frame, text="Wave definitions (reusable)").pack(anchor="w")
        self.wd_list = tk.Listbox(self.wave_frame, height=6, width=30, exportselection=False)
        self.wd_list.pack(fill="x")
        self.wd_list.bind("<<ListboxSelect>>", self._on_wave_def_select)
        wd_btns = ttk.Frame(self.wave_frame)
        wd_btns.pack(fill="x", pady=(2, 6))
        ttk.Button(wd_btns, text="Add def", command=self._add_wave_def).pack(side="left")
        ttk.Button(wd_btns, text="Delete def", command=self._delete_wave_def).pack(side="left", padx=(4, 0))

        form = ttk.Frame(self.wave_frame)
        form.pack(fill="x")
        ttk.Label(form, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.wd_name_var, width=20).grid(row=0, column=1, sticky="ew")
        ttk.Label(form, text="Formation").grid(row=1, column=0, sticky="w")
        self.wd_attack_combo = ttk.Combobox(form, textvariable=self.wd_attack_var, width=24,
                                            values=self.attack_names, state="readonly")
        self.wd_attack_combo.grid(row=1, column=1, sticky="ew")
        ttk.Label(form, text="Enemy type").grid(row=2, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.wd_enemy_var, width=6, state="readonly",
                     values=list(range(ENEMY_TYPE_COUNT))).grid(row=2, column=1, sticky="w")
        ttk.Label(form, text="Count (size)").grid(row=3, column=0, sticky="w")
        ttk.Spinbox(form, from_=1, to=WAVE_MAX_COMPOSITION_COUNT, width=6,
                    textvariable=self.wd_count_var).grid(row=3, column=1, sticky="w")
        ttk.Label(form, text="Spawn interval").grid(row=4, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.wd_interval_var, width=8).grid(row=4, column=1, sticky="w")
        ttk.Button(form, text="Apply to def", command=self._apply_wave_def_form).grid(
            row=5, column=1, sticky="e", pady=(4, 0))
        form.columnconfigure(1, weight=1)

        ttk.Separator(self.wave_frame, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(self.wave_frame, text="Trigger inspector (Waves mode:\nclick the stage to place)").pack(anchor="w")
        tf = ttk.Frame(self.wave_frame)
        tf.pack(fill="x", pady=(2, 0))
        ttk.Label(tf, text="World row").grid(row=0, column=0, sticky="w")
        self.wt_row_spin = ttk.Spinbox(tf, from_=0, to=10 ** 6, width=8, textvariable=self.wt_row_var,
                                       command=self._apply_trigger_form)
        self.wt_row_spin.grid(row=0, column=1, sticky="w")
        self.wt_row_spin.bind("<Return>", self._apply_trigger_form)
        ttk.Label(tf, text="Wave def").grid(row=1, column=0, sticky="w")
        self.wt_def_combo = ttk.Combobox(tf, textvariable=self.wt_def_var, width=20, state="readonly")
        self.wt_def_combo.grid(row=1, column=1, sticky="ew")
        self.wt_def_combo.bind("<<ComboboxSelected>>", self._apply_trigger_form)
        ttk.Button(tf, text="Delete trigger", command=self._delete_selected_trigger).grid(
            row=2, column=1, sticky="e", pady=(4, 0))
        tf.columnconfigure(1, weight=1)

    # ---- mousewheel -----------------------------------------------------
    def _bind_mousewheel(self, canvas):
        canvas.bind("<MouseWheel>", lambda e, t=canvas: self._mousewheel(e, t))
        canvas.bind("<Button-4>", lambda e, t=canvas: (t.yview_scroll(-1, "units"), "break")[1])
        canvas.bind("<Button-5>", lambda e, t=canvas: (t.yview_scroll(1, "units"), "break")[1])

    def _mousewheel(self, event, canvas):
        units = -int(event.delta) if sys.platform == "darwin" else -int(event.delta / 120) if event.delta else 0
        if units:
            canvas.yview_scroll(units, "units")
        return "break"

    def _viewport_wheel(self, event):
        step = -1 if (event.delta > 0 if sys.platform != "darwin" else event.delta < 0) else 1
        self._nudge_viewport(step)
        return "break"

    # ---- gameplay viewport overlay -----------------------------------
    def _clamp_viewport(self):
        self.viewport_top = clamp_viewport_top(self.viewport_top, self.project)
        try:
            self.viewport_scale.configure(to=max(1, max_viewport_top(self.project)))
            self.viewport_var.set(self.viewport_top)
            self.viewport_scale.set(self.viewport_top)
        except AttributeError:
            pass

    def _set_viewport(self, top, push_undo=False):
        self.viewport_top = clamp_viewport_top(top, self.project)
        self.viewport_var.set(self.viewport_top)
        try:
            if abs(self.viewport_scale.get() - self.viewport_top) > 0.5:
                self.viewport_scale.set(self.viewport_top)
        except (AttributeError, tk.TclError):
            pass
        self._draw_viewport_overlay()
        self._update_viewport_text()

    def _on_viewport_scrub(self, value):
        top = int(round(float(value)))
        if top != self.viewport_top:
            self.viewport_top = clamp_viewport_top(top, self.project)
            self.viewport_var.set(self.viewport_top)
            self._draw_viewport_overlay()
            self._update_viewport_text()

    def _nudge_viewport(self, delta):
        self._set_viewport(self.viewport_top + delta)
        return "break"

    def _update_viewport_text(self):
        lo = self.viewport_top
        hi = lo + VIEWPORT_ROWS - 1
        slr = stage_logical_rows(self.project)
        self.viewport_text.set(f"logical rows {lo}–{hi}  (start row {slr - 1}; {VIEWPORT_ROWS}×40)")

    def _draw_viewport_overlay(self):
        c = self.level_canvas
        c.delete("viewport")
        y0 = self.viewport_top * CHAR_SIZE
        y1 = (self.viewport_top + VIEWPORT_ROWS) * CHAR_SIZE
        # faint fill band
        c.create_rectangle(0, y0, LEVEL_WIDTH, y1, outline="", fill=VIEWPORT_EDGE,
                           stipple="gray12", tags="viewport")
        for yy in (y0, y1):
            c.create_line(0, yy, LEVEL_WIDTH, yy, fill=VIEWPORT_EDGE, width=1, tags="viewport")
        # top edge = the wave activation line (SCROLL_ROW == worldRow)
        c.create_line(0, y0, LEVEL_WIDTH, y0, fill=VIEWPORT_ACTIVATION, width=2, tags="viewport")
        c.create_text(3, y0 + 2, anchor="nw", fill=VIEWPORT_ACTIVATION,
                      font=("TkDefaultFont", 7),
                      text=f"gameplay view  rows {self.viewport_top}–"
                           f"{self.viewport_top + VIEWPORT_ROWS - 1}", tags="viewport")

    def _viewport_range(self):
        return self.viewport_top, self.viewport_top + VIEWPORT_ROWS - 1

    # ---- rendering ---------------------------------------------------
    def _pixel_colour(self, pair):
        p = self.project.palette
        return C64_COLOURS[(p["background"], p["multicolour1"], p["multicolour2"], p["character"])[pair]]

    def _glyph_bitmap(self, code):
        base = 160
        glyphs = self.project.tileset["glyphs"]
        idx = code - base
        if 0 <= idx < len(glyphs):
            return glyphs[idx]
        raise ValueError(f"No terrain glyph bitmap for character {code} in this level's tileset")

    def _get_metatile_image(self, tile_id):
        palette_key = tuple(self.project.palette[k] for k in
                            ("background", "multicolour1", "multicolour2", "character"))
        cache_key = (tile_id, palette_key, id(self.project.tileset))
        image = self.metatile_image_cache.get(cache_key)
        if image is not None:
            return image
        tile = self.project.tileset["metatileDefs"][tile_id]
        pixel_rows = []
        for char_row in range(METATILE_H):
            for glyph_y in range(CHAR_SIZE):
                row_colours = []
                for char_col in range(METATILE_W):
                    byte = self._glyph_bitmap(tile[char_row * METATILE_W + char_col])[glyph_y]
                    for shift in (6, 4, 2, 0):
                        colour = self._pixel_colour((byte >> shift) & 0x03)
                        row_colours.extend((colour, colour))
                pixel_rows.append(row_colours)
        image = tk.PhotoImage(width=METATILE_PIXELS, height=METATILE_PIXELS)
        image.put(" ".join("{" + " ".join(row) + "}" for row in pixel_rows))
        self.metatile_image_cache[cache_key] = image
        return image

    def _draw_metatile(self, canvas, tile_id, x, y, tags=()):
        canvas.create_image(x, y, anchor="nw", image=self._get_metatile_image(tile_id), tags=tags)

    def _draw_palette(self):
        self.palette_canvas.delete("all")
        item_height = 46
        for tile_id, name in enumerate(METATILE_NAMES):
            y = tile_id * item_height + 4
            tags = (f"tile_{tile_id}",)
            self.palette_canvas.create_rectangle(4, y, 39, y + 35,
                                                 fill=C64_COLOURS[self.project.palette["background"]],
                                                 outline="#888888", tags=tags)
            self._draw_metatile(self.palette_canvas, tile_id, 6, y + 2, tags=tags)
            self.palette_canvas.create_text(48, y + 17, anchor="w", text=f"{tile_id:2d}  {name}", tags=tags)
            if tile_id == self.selected_tile:
                self.palette_canvas.create_rectangle(1, y - 2, 205, y + 38, outline=SELECTED, width=2, tags=tags)
        self.palette_canvas.configure(scrollregion=(0, 0, 210, len(METATILE_NAMES) * item_height + 4))

    def _draw_level(self):
        self.level_canvas.delete("all")
        self.level_canvas.configure(scrollregion=(0, 0, LEVEL_WIDTH, self.level_height))
        for row, tiles in enumerate(self.stage_rows):
            for col, tile_id in enumerate(tiles):
                self._draw_metatile(self.level_canvas, tile_id, col * METATILE_PIXELS, row * METATILE_PIXELS)
        if self.show_grid.get():
            for x in range(0, LEVEL_WIDTH + 1, METATILE_PIXELS):
                self.level_canvas.create_line(x, 0, x, self.level_height, fill=GRID, tags="grid")
            for y in range(0, self.level_height + 1, METATILE_PIXELS):
                self.level_canvas.create_line(0, y, LEVEL_WIDTH, y, fill=GRID, tags="grid")
        self._draw_turret_markers()
        self._draw_wave_triggers()
        self._draw_viewport_overlay()

    def _draw_turret_markers(self):
        self.level_canvas.delete("turret_marker")
        lo, hi = self._viewport_range()
        active = self.edit_mode.get() == "turret"
        for index, obj in enumerate(self.project.objects):
            if not (isinstance(obj, dict) and obj.get("type") == OBJECT_TYPE_TURRET):
                continue
            row, col = obj.get("metatileRow", 0), obj.get("metatileCol", 0)
            x0, y0 = col * METATILE_PIXELS, row * METATILE_PIXELS
            x1, y1 = x0 + METATILE_PIXELS, y0 + METATILE_PIXELS
            wr = turret_world_row(row)
            in_view = lo <= wr <= hi
            selected = active and index == self.selected_turret
            outline = SELECTED if selected else ("#ff5030" if in_view else "#7a4a44")
            width = 3 if selected else (2 if in_view else 1)
            self.level_canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=outline,
                                               width=width, tags="turret_marker")
            bx, by = x0 + CHAR_SIZE, y0 + CHAR_SIZE
            self.level_canvas.create_rectangle(bx, by, bx + 2 * CHAR_SIZE, by + 2 * CHAR_SIZE,
                                               outline=outline, fill="", width=1, tags="turret_marker")
            self.level_canvas.create_text(x0 + METATILE_PIXELS / 2, y0 + METATILE_PIXELS / 2,
                                          text="T", fill=outline,
                                          font=("TkDefaultFont", 10, "bold"), tags="turret_marker")

    def _draw_wave_triggers(self):
        self.level_canvas.delete("wave_trigger")
        active = self.edit_mode.get() == "wave"
        for index, wt in enumerate(self.project.wave_triggers):
            y = int(wt.get("worldRow", 0)) * CHAR_SIZE
            selected = active and index == self.selected_trigger
            colour = SELECTED if selected else TRIGGER_COLOUR
            self.level_canvas.create_line(0, y, LEVEL_WIDTH, y, fill=colour,
                                          width=3 if selected else 2, tags="wave_trigger")
            wd = self.project.wave_definition(wt.get("waveDef"))
            label = (wd.get("name") if wd else wt.get("waveDef")) or "?"
            self.level_canvas.create_text(4, y - 2, anchor="sw", fill=colour,
                                          font=("TkDefaultFont", 8, "bold" if selected else "normal"),
                                          text=f"▶ {label}  (row {wt.get('worldRow', 0)})",
                                          tags="wave_trigger")

    def _palette_click(self, event):
        tile_id = int((self.palette_canvas.canvasy(event.y) - 4) // 46)
        if 0 <= tile_id < len(METATILE_NAMES):
            self.selected_tile = tile_id
            self._draw_palette()
            self._update_status()

    # ---- canvas input dispatch -----------------------------------------
    def _cell_from_event(self, event):
        x = int(self.level_canvas.canvasx(event.x))
        y = int(self.level_canvas.canvasy(event.y))
        col, row = x // METATILE_PIXELS, y // METATILE_PIXELS
        if 0 <= row < self.project.height and 0 <= col < METATILES_PER_ROW:
            return row, col
        return None

    def _logical_row_from_event(self, event):
        y = int(self.level_canvas.canvasy(event.y))
        return max(0, min(stage_logical_rows(self.project) - 1, round(y / CHAR_SIZE)))

    def _on_mode_change(self):
        self.selected_turret = None
        self.selected_trigger = None
        self._draw_level()
        self._update_turret_ui()
        self._update_status()

    def _level_click_start(self, event):
        self.level_canvas.focus_set()
        mode = self.edit_mode.get()
        if mode == "turret":
            self._turret_click(event)
            return "break"
        if mode == "wave":
            self._wave_click(event)
            return "break"
        self._paint_start(event)

    def _level_drag(self, event):
        mode = self.edit_mode.get()
        if mode == "wave" and self._dragging_trigger and self.selected_trigger is not None:
            before = self._trigger_drag_before
            self.project.wave_triggers[self.selected_trigger]["worldRow"] = self._logical_row_from_event(event)
            self._draw_wave_triggers()
            self._sync_trigger_form()
            return "break"
        if mode in ("turret", "wave"):
            return "break"
        self._paint_event(event)

    def _level_click_end(self, event=None):
        mode = self.edit_mode.get()
        if mode == "wave" and self._dragging_trigger:
            self._dragging_trigger = False
            if self._trigger_drag_before != self._project_state():
                self._push_undo(self._trigger_drag_before)
            self._set_viewport(self.project.wave_triggers[self.selected_trigger]["worldRow"])
            self._update_document_ui()
            return "break"
        if mode in ("turret", "wave"):
            return "break"
        self._paint_end(event)

    def _level_right_click(self, event):
        if self.edit_mode.get() == "turret":
            cell = self._cell_from_event(event)
            if cell:
                self._remove_turret_at(*cell)
            return "break"
        if self.edit_mode.get() == "wave":
            idx = self._trigger_at(event)
            if idx is not None:
                self._remove_trigger(idx)
            return "break"

    def _delete_selected(self, event=None):
        if self.edit_mode.get() == "turret":
            return self._delete_selected_turret()
        if self.edit_mode.get() == "wave":
            return self._delete_selected_trigger()
        return "break"

    # ---- turret placement -------------------------------------------------
    def _turret_index_at(self, row, col):
        for i, o in enumerate(self.project.objects):
            if (isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET
                    and o.get("metatileRow") == row and o.get("metatileCol") == col):
                return i
        return None

    def _turret_index_in_row(self, row):
        for i, o in enumerate(self.project.objects):
            if (isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET and o.get("metatileRow") == row):
                return i
        return None

    def _turret_count(self):
        return sum(1 for o in self.project.objects
                   if isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET)

    def _turret_click(self, event):
        cell = self._cell_from_event(event)
        if cell is None:
            return
        row, col = cell
        existing = self._turret_index_at(row, col)
        if existing is not None:
            self.selected_turret = existing
            self._draw_level()
            self._update_turret_ui()
            return
        if self._turret_index_in_row(row) is not None:
            self.bell()
            self.status_text.set(f"Metatile row {row} already has a turret (one per world row).")
            return
        before = self._project_state()
        self.project.objects.append({"type": OBJECT_TYPE_TURRET, "metatileRow": row, "metatileCol": col})
        self.selected_turret = len(self.project.objects) - 1
        self._push_undo(before)
        self._draw_level()
        self._update_turret_ui()
        self._update_document_ui()

    def _remove_turret_at(self, row, col):
        idx = self._turret_index_at(row, col)
        if idx is None:
            return
        before = self._project_state()
        del self.project.objects[idx]
        self.selected_turret = None
        self._push_undo(before)
        self._draw_level()
        self._update_turret_ui()
        self._update_document_ui()

    def _delete_selected_turret(self):
        if self.edit_mode.get() != "turret" or self.selected_turret is None:
            return "break"
        if not 0 <= self.selected_turret < len(self.project.objects):
            self.selected_turret = None
            return "break"
        before = self._project_state()
        del self.project.objects[self.selected_turret]
        self.selected_turret = None
        self._push_undo(before)
        self._draw_level()
        self._update_turret_ui()
        self._update_document_ui()
        return "break"

    def _update_turret_ui(self):
        has = (self.edit_mode.get() == "turret" and self.selected_turret is not None
               and 0 <= (self.selected_turret or -1) < len(self.project.objects))
        self.delete_turret_button.configure(state="normal" if has else "disabled")

    # ---- wave definitions ------------------------------------------------
    def _refresh_wave_panel(self):
        self.wd_list.delete(0, "end")
        for wd in self.project.wave_definitions:
            self.wd_list.insert("end", f"{wd.get('id')}  {wd.get('name', '')}  "
                                       f"[{self.attack_name_by_id.get(int(wd.get('attackId', 0)), '?')}]"
                                       f"  x{composition_size(wd)}")
        ids = [wd["id"] for wd in self.project.wave_definitions]
        self.wt_def_combo.configure(values=ids)
        if self.selected_wave_def is not None and 0 <= self.selected_wave_def < len(self.project.wave_definitions):
            self.wd_list.selection_clear(0, "end")
            self.wd_list.selection_set(self.selected_wave_def)
            self._sync_wave_def_form()
        self._sync_trigger_form()

    def _sync_wave_def_form(self):
        if self.selected_wave_def is None or not 0 <= self.selected_wave_def < len(self.project.wave_definitions):
            return
        wd = self.project.wave_definitions[self.selected_wave_def]
        self.wd_name_var.set(wd.get("name", ""))
        self.wd_attack_var.set(self.attack_name_by_id.get(int(wd.get("attackId", 0)), ""))
        comp = wd.get("composition") or [{"enemyType": 0, "count": 5}]
        self.wd_enemy_var.set(int(comp[0].get("enemyType", 0)))
        self.wd_count_var.set(int(comp[0].get("count", 5)))
        self.wd_interval_var.set("" if wd.get("spawnInterval") in (None, "") else str(wd["spawnInterval"]))

    def _on_wave_def_select(self, event=None):
        sel = self.wd_list.curselection()
        self.selected_wave_def = sel[0] if sel else None
        self._sync_wave_def_form()
        self._update_status()

    def _add_wave_def(self):
        before = self._project_state()
        wd = {"id": _next_id("wd", self.project.wave_definitions),
              "name": "New wave",
              "attackId": self.attack_id_by_name.get(self.attack_names[0], 0) if self.attack_names else 0,
              "composition": [{"enemyType": 0, "count": 5}], "spawnInterval": None}
        self.project.wave_definitions.append(wd)
        self.selected_wave_def = len(self.project.wave_definitions) - 1
        self._push_undo(before)
        self._refresh_wave_panel()
        self._update_document_ui()

    def _delete_wave_def(self):
        if self.selected_wave_def is None or not 0 <= self.selected_wave_def < len(self.project.wave_definitions):
            return
        wd_id = self.project.wave_definitions[self.selected_wave_def]["id"]
        if any(wt.get("waveDef") == wd_id for wt in self.project.wave_triggers):
            self.bell()
            self.status_text.set(f"Wave def {wd_id} is still referenced by a trigger.")
            return
        before = self._project_state()
        del self.project.wave_definitions[self.selected_wave_def]
        self.selected_wave_def = None
        self._push_undo(before)
        self._refresh_wave_panel()
        self._update_document_ui()

    def _apply_wave_def_form(self):
        if self.selected_wave_def is None or not 0 <= self.selected_wave_def < len(self.project.wave_definitions):
            return
        before = self._project_state()
        wd = self.project.wave_definitions[self.selected_wave_def]
        wd["name"] = self.wd_name_var.get().strip() or wd["id"]
        wd["attackId"] = self.attack_id_by_name.get(self.wd_attack_var.get(), wd.get("attackId", 0))
        try:
            et = max(0, min(ENEMY_TYPE_COUNT - 1, int(self.wd_enemy_var.get())))
            cn = max(1, min(WAVE_MAX_COMPOSITION_COUNT, int(self.wd_count_var.get())))
        except (tk.TclError, ValueError):
            return
        wd["composition"] = [{"enemyType": et, "count": cn}]
        iv = self.wd_interval_var.get().strip()
        wd["spawnInterval"] = int(iv) if iv.isdigit() and 1 <= int(iv) <= 255 else None
        errs = validate_project(self.project)
        if errs:
            messagebox.showerror("Wave definition invalid", "\n".join(errs), parent=self)
            self._restore_state(before)
            return
        self._push_undo(before)
        self._refresh_wave_panel()
        self._draw_wave_triggers()
        self._update_document_ui()

    # ---- wave triggers -------------------------------------------------
    def _trigger_at(self, event):
        y = int(self.level_canvas.canvasy(event.y))
        best, bestd = None, TRIGGER_HIT
        for i, wt in enumerate(self.project.wave_triggers):
            d = abs(int(wt.get("worldRow", 0)) * CHAR_SIZE - y)
            if d <= bestd:
                best, bestd = i, d
        return best

    def _wave_click(self, event):
        idx = self._trigger_at(event)
        if idx is not None:
            self.selected_trigger = idx
            self._dragging_trigger = True
            self._trigger_drag_before = self._project_state()
            self._draw_wave_triggers()
            self._sync_trigger_form()
            self._set_viewport(self.project.wave_triggers[idx]["worldRow"])
            return
        if not self.project.wave_definitions:
            self.bell()
            self.status_text.set("Add a wave definition first, then click the stage to place a trigger.")
            return
        wd_id = (self.project.wave_definitions[self.selected_wave_def]["id"]
                 if self.selected_wave_def is not None
                 and 0 <= self.selected_wave_def < len(self.project.wave_definitions)
                 else self.project.wave_definitions[0]["id"])
        before = self._project_state()
        wt = {"id": _next_id("wt", self.project.wave_triggers),
              "worldRow": self._logical_row_from_event(event), "waveDef": wd_id}
        self.project.wave_triggers.append(wt)
        self.selected_trigger = len(self.project.wave_triggers) - 1
        self._push_undo(before)
        self._draw_wave_triggers()
        self._sync_trigger_form()
        self._set_viewport(wt["worldRow"])
        self._update_document_ui()

    def _sync_trigger_form(self):
        if self.selected_trigger is not None and 0 <= self.selected_trigger < len(self.project.wave_triggers):
            wt = self.project.wave_triggers[self.selected_trigger]
            self.wt_row_var.set(int(wt.get("worldRow", 0)))
            self.wt_def_var.set(wt.get("waveDef", ""))

    def _apply_trigger_form(self, event=None):
        if self.selected_trigger is None or not 0 <= self.selected_trigger < len(self.project.wave_triggers):
            return
        before = self._project_state()
        wt = self.project.wave_triggers[self.selected_trigger]
        try:
            wt["worldRow"] = max(0, min(stage_logical_rows(self.project) - 1, int(self.wt_row_var.get())))
        except (tk.TclError, ValueError):
            pass
        if self.wt_def_var.get():
            wt["waveDef"] = self.wt_def_var.get()
        errs = validate_project(self.project)
        if errs:
            messagebox.showerror("Trigger invalid", "\n".join(errs), parent=self)
            self._restore_state(before)
            return
        self._push_undo(before)
        self._draw_wave_triggers()
        self._set_viewport(wt["worldRow"])
        self._update_document_ui()

    def _remove_trigger(self, idx):
        before = self._project_state()
        del self.project.wave_triggers[idx]
        self.selected_trigger = None
        self._push_undo(before)
        self._draw_wave_triggers()
        self._sync_trigger_form()
        self._update_document_ui()

    def _delete_selected_trigger(self):
        if self.edit_mode.get() != "wave" or self.selected_trigger is None:
            return "break"
        if 0 <= self.selected_trigger < len(self.project.wave_triggers):
            self._remove_trigger(self.selected_trigger)
        return "break"

    # ---- terrain paint -------------------------------------------------
    def _paint_start(self, event):
        self.paint_gesture_before = self._project_state()
        self.last_painted_cell = None
        self._paint_event(event)

    def _paint_event(self, event):
        x = int(self.level_canvas.canvasx(event.x))
        y = int(self.level_canvas.canvasy(event.y))
        col, row = x // METATILE_PIXELS, y // METATILE_PIXELS
        if not (0 <= row < self.project.height and 0 <= col < METATILES_PER_ROW):
            return
        if (row, col) == self.last_painted_cell:
            return
        self.last_painted_cell = (row, col)
        if self.stage_rows[row][col] == self.selected_tile:
            return
        self.stage_rows[row][col] = self.selected_tile
        self._redraw_cell(row, col)
        self._update_document_ui()

    def _paint_end(self, event=None):
        self.last_painted_cell = None
        if self.paint_gesture_before is not None and self.paint_gesture_before != self._project_state():
            self._push_undo(self.paint_gesture_before)
        self.paint_gesture_before = None
        self._update_document_ui()

    def _redraw_cell(self, row, col):
        x0, y0 = col * METATILE_PIXELS, row * METATILE_PIXELS
        x1, y1 = x0 + METATILE_PIXELS, y0 + METATILE_PIXELS
        self.level_canvas.delete(f"cell_{row}_{col}")
        tag = (f"cell_{row}_{col}",)
        self.level_canvas.create_rectangle(x0, y0, x1, y1,
                                           fill=C64_COLOURS[self.project.palette["background"]],
                                           outline="", tags=tag)
        self._draw_metatile(self.level_canvas, self.stage_rows[row][col], x0, y0, tags=tag)
        if self.show_grid.get():
            self.level_canvas.create_rectangle(x0, y0, x1, y1, outline=GRID, tags=tag)
        self._draw_turret_markers()
        self._draw_wave_triggers()
        self._draw_viewport_overlay()

    # ---- stage/level settings ---------------------------------------
    def _apply_stage_row_count(self, event=None):
        try:
            requested = int(self.stage_row_count.get())
        except (tk.TclError, ValueError):
            self.stage_row_count.set(self.project.height)
            return "break" if event else None
        requested = max(MIN_STAGE_ROWS, min(MAX_STAGE_ROWS, requested))
        current = self.project.height
        if requested == current:
            self.stage_row_count.set(current)
            return "break" if event else None
        before = self._project_state()
        if requested < current:
            removed = self.stage_rows[requested:]
            slr_new = requested * METATILE_H
            lost_t = [t for t in iter_turrets(self.project) if t["metatileRow"] >= requested]
            lost_w = [w for w in self.project.wave_triggers if int(w.get("worldRow", 0)) >= slr_new]
            has_terrain = any(t != 0 for r in removed for t in r)
            if (has_terrain or lost_t or lost_w) and not messagebox.askyesno(
                "Reduce stage height?",
                f"Rows {requested}..{current - 1} will be discarded"
                + (f", along with {len(lost_t)} turret(s)" if lost_t else "")
                + (f" and {len(lost_w)} wave trigger(s)" if lost_w else "")
                + ".\n\nReduce the stage height anyway?", parent=self):
                self.stage_row_count.set(current)
                return "break" if event else None
            del self.stage_rows[requested:]
            self.project.objects = [o for o in self.project.objects
                                    if not (isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET
                                            and o.get("metatileRow", 0) >= requested)]
            self.project.wave_triggers = [w for w in self.project.wave_triggers
                                          if int(w.get("worldRow", 0)) < slr_new]
        else:
            self.stage_rows.extend([[0] * METATILES_PER_ROW for _ in range(requested - current)])
        self.selected_turret = self.selected_trigger = None
        self._push_undo(before)
        self.stage_row_count.set(self.project.height)
        self._clamp_viewport()
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()
        return "break" if event else None

    def _apply_level_settings(self, event=None):
        try:
            new_palette = {k: int(v.get()) for k, v in self.palette_vars.items()}
            new_divider = int(self.scroll_divider_var.get())
        except (tk.TclError, ValueError):
            self._sync_level_settings_controls()
            return "break" if event else None
        ranges = {"background": 15, "multicolour1": 15, "multicolour2": 15, "character": 7}
        if any(not 0 <= new_palette[k] <= m for k, m in ranges.items()) or not 1 <= new_divider <= 255:
            self._sync_level_settings_controls()
            return "break" if event else None
        if new_palette == self.project.palette and new_divider == self.project.scroll_frame_divider:
            return "break" if event else None
        before = self._project_state()
        self.project.palette = new_palette
        self.project.scroll_frame_divider = new_divider
        self.metatile_image_cache.clear()
        self._push_undo(before)
        self.level_canvas.configure(background=C64_COLOURS[self.project.palette["background"]])
        self._draw_palette()
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()
        return "break" if event else None

    def _sync_level_settings_controls(self):
        self.scroll_divider_var.set(self.project.scroll_frame_divider)
        for k, v in self.palette_vars.items():
            v.set(self.project.palette[k])

    def _update_stage_info(self):
        total_pixels = self.level_height
        seconds = total_pixels * self.project.scroll_frame_divider / PAL_FRAMES_PER_SECOND
        minutes = int(seconds // 60)
        rem = int(round(seconds - minutes * 60))
        if rem == 60:
            minutes, rem = minutes + 1, 0
        plural = "s" if self.project.scroll_frame_divider != 1 else ""
        self.duration_text.set(
            f"≈ {minutes}:{rem:02d} at 1 px/{self.project.scroll_frame_divider} frame{plural} PAL  "
            f"({LEVEL_WIDTH} x {total_pixels}px, {stage_logical_rows(self.project)} logical rows)")
        self._update_viewport_text()
        self._update_status()

    def _screen_peak_turrets(self):
        return turret_screen_peak(self.project)

    def _update_status(self):
        mode = self.edit_mode.get()
        if mode == "turret":
            self.status_text.set(
                f"Turret mode: {self._turret_count()} authored, up to {self._screen_peak_turrets()} on "
                f"one gameplay screen (pool {TURRET_POOL})  |  click to place/select, right-click/Delete to remove")
            return
        if mode == "wave":
            self.status_text.set(
                f"Wave mode: {len(self.project.wave_triggers)} trigger(s), "
                f"{len(self.project.wave_definitions)} definition(s)  |  "
                f"click the stage to place a trigger; drag to move; Delete to remove")
            return
        self.status_text.set(
            f"Selected: {self.selected_tile} {METATILE_NAMES[self.selected_tile]}  |  "
            f"Level: {self.project.name}  {METATILES_PER_ROW} x {self.project.height} metatiles  |  "
            f"Palette {self.project.palette['background']}/{self.project.palette['multicolour1']}/"
            f"{self.project.palette['multicolour2']}/{self.project.palette['character']}  |  "
            f"Divider {self.project.scroll_frame_divider}")

    def _update_document_ui(self):
        mark = " *" if self._is_dirty() else ""
        self.title(f"19656 Level Editor - {self.project.name}{mark}")
        path_text = self.project_path.name if self.project_path else "unsaved"
        parent = self.project_path.parent.name if self.project_path else "-"
        self.level_frame.configure(text=f"Working stage: {self.project.name}  ({parent}/{path_text})")
        self.edit_menu.entryconfigure("Undo", state="normal" if self.undo_stack else "disabled")
        self.edit_menu.entryconfigure("Redo", state="normal" if self.redo_stack else "disabled")
        self._update_turret_ui()
        self._update_status()

    def _refresh_all(self):
        self.metatile_image_cache.clear()
        self._clamp_viewport()
        self.level_canvas.configure(background=C64_COLOURS[self.project.palette["background"]])
        self._sync_level_settings_controls()
        self.stage_row_count.set(self.project.height)
        self._draw_palette()
        self._draw_level()
        self._refresh_wave_panel()
        self._update_stage_info()
        self._update_document_ui()

    # ---- undo/redo --------------------------------------------------
    def _push_undo(self, state):
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def _restore_state(self, state):
        (name, rows, palette_items, divider, obj_keys, meta_items, defs_json, trig_json, tileset_json) = state
        self.project.name = name
        self.project.metatile_rows = [list(r) for r in rows]
        self.project.palette = dict(palette_items)
        self.project.scroll_frame_divider = divider
        self.project.objects = [o for o in (self._obj_from_key(k) for k in obj_keys) if o is not None]
        self.project.metatile_metadata = dict(meta_items)
        self.project.wave_definitions = json.loads(defs_json)
        self.project.wave_triggers = json.loads(trig_json)
        self.project.tileset = json.loads(tileset_json) if tileset_json else None
        self.selected_turret = self.selected_trigger = None
        self._refresh_all()

    def _undo(self):
        if not self.undo_stack:
            return "break"
        self.redo_stack.append(self._project_state())
        self._restore_state(self.undo_stack.pop())
        return "break"

    def _redo(self):
        if not self.redo_stack:
            return "break"
        self.undo_stack.append(self._project_state())
        self._restore_state(self.redo_stack.pop())
        return "break"

    # ---- file ops -------------------------------------------------
    def _confirm_discard(self):
        if not self._is_dirty():
            return True
        answer = messagebox.askyesnocancel("Unsaved changes",
                                           f"Save changes to {self.project.name} first?", parent=self)
        if answer is None:
            return False
        return self._save_project() if answer else True

    def _adopt_project(self, project, path):
        """Switch to a level package, resetting ALL editor state (no stale data)."""
        self.project = project
        self.project_path = Path(path) if path else None
        self.metatile_image_cache.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.selected_turret = self.selected_trigger = self.selected_wave_def = None
        self.paint_gesture_before = None
        self._dragging_trigger = False
        self.edit_mode.set("terrain")
        self.viewport_top = default_viewport_top(self.project)
        self.saved_state = None if path is None else self._project_state()
        self.level_canvas.yview_moveto(0)
        self._refresh_all()

    def _new_level(self):
        if not self._confirm_discard():
            return "break"
        name = simpledialog.askstring("New Level", "Level name:", initialvalue="new_level", parent=self)
        if not name or not name.strip():
            return "break"
        name = name.strip()
        rows = simpledialog.askinteger("New Level", "Stage rows:", initialvalue=DEFAULT_STAGE_ROWS,
                                       minvalue=MIN_STAGE_ROWS, maxvalue=MAX_STAGE_ROWS, parent=self)
        if rows is None:
            return "break"
        project = self._seed_project(name, [[0] * METATILES_PER_ROW for _ in range(rows)],
                                     dict(DEFAULT_PALETTE), DEFAULT_SCROLL_FRAME_DIVIDER)
        self._adopt_project(project, None)   # unsaved; Save writes levels/<name>/level.json
        return "break"

    def _open_level(self):
        if not self._confirm_discard():
            return "break"
        initial = self.levels_dir if any(self.levels_dir.glob("*/level.json")) else self.legacy_dir
        path = filedialog.askopenfilename(
            title="Open level package (levels/<name>/level.json) or legacy project",
            initialdir=initial,
            filetypes=(("Level packages", "level.json"), ("Level JSON", "*.json"), ("All files", "*.*")),
            parent=self)
        if not path:
            return "break"
        try:
            project = load_project(path, default_tileset=self._baseline_tileset())
        except (OSError, ProjectValidationError) as exc:
            messagebox.showerror("Open Level", str(exc), parent=self)
            return "break"
        self._adopt_project(project, path)
        return "break"

    def _validate_before_write(self):
        errors = validate_project(self.project)
        if errors:
            messagebox.showerror("Project validation failed", "\n".join(errors), parent=self)
            return False
        seam = wrap_seam_warning(self.project)
        if seam and not messagebox.askyesno("Possible wrap seam", seam + "\n\nSave anyway?", parent=self):
            return False
        return True

    def _default_level_path(self):
        return self.levels_dir / self.project.name / "level.json"

    def _save_project(self):
        if self.project_path is None:
            target = self._default_level_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            if not self._validate_before_write():
                return False
            return self._write_project(target, already_validated=True)
        return self._write_project(self.project_path)

    def _save_project_as(self):
        if not self._validate_before_write():
            return False
        path = filedialog.asksaveasfilename(
            title="Save level package", initialdir=self._default_level_path().parent,
            initialfile="level.json", defaultextension=".json",
            filetypes=(("Level JSON", "*.json"), ("All files", "*.*")), parent=self)
        if not path:
            return False
        return self._write_project(Path(path), already_validated=True)

    def _write_project(self, path, already_validated=False):
        if not already_validated and not self._validate_before_write():
            return False
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            save_project(self.project, path)
        except (OSError, ProjectValidationError) as exc:
            messagebox.showerror("Save Project", str(exc), parent=self)
            return False
        self.project_path = Path(path)
        self.saved_state = self._project_state()
        self._update_document_ui()
        return True

    def _export_kickassembler(self):
        readiness = export_readiness_errors(self.project)
        if readiness:
            messagebox.showerror("Cannot export", "\n".join(readiness), parent=self)
            return "break"
        if not self._validate_before_write():
            return "break"
        default_dir = self.repo_root / "src" / "generated" / self.project.name
        out = filedialog.askdirectory(title=f"Export level '{self.project.name}' package (5 .asm files)",
                                      initialdir=default_dir if default_dir.parent.exists() else self.repo_root,
                                      parent=self)
        if not out:
            return "break"
        try:
            paths = export_level(self.project, out, engine_data=self.data)
        except (OSError, ProjectValidationError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return "break"
        gameplay = "  (imported by main.asm; rebuild to play)" if self.project.name == "level1" else \
                   "  (coexists on disk; not imported by gameplay)"
        messagebox.showinfo("Level package exported",
                            "Generated:\n" + "\n".join(str(p) for p in paths) + "\n" + gameplay, parent=self)
        return "break"

    def _on_close(self):
        if self._confirm_discard():
            self.destroy()
        return "break"


def find_repo_root():
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        if (parent / "src" / "main.asm").is_file() and (
            (parent / "src" / "generated" / "level1" / "stage_test.asm").is_file()
            or (parent / "src" / "generated" / "stage_test.asm").is_file()
        ):
            return parent
    raise FileNotFoundError(
        "Could not find repo root containing src/main.asm and src/generated/level1/stage_test.asm")


def main():
    try:
        editor = LevelEditor(find_repo_root())
    except Exception as exc:  # noqa: BLE001
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("19656 Level Editor", str(exc))
        root.destroy()
        return 1
    editor.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
