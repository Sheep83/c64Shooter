#!/usr/bin/env python3
"""19656 standalone Tkinter level editor."""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from engine_data import (
    DEFAULT_PALETTE,
    DEFAULT_SCROLL_FRAME_DIVIDER,
    METATILE_H,
    METATILE_NAMES,
    METATILE_W,
    METATILES_PER_ROW,
    load_engine_data,
)
from ka_export import export_project
from project import (
    DEFAULT_STAGE_ROWS,
    LevelProject,
    MAX_STAGE_ROWS,
    MAX_TURRETS,
    MIN_STAGE_ROWS,
    OBJECT_TYPE_TURRET,
    ProjectValidationError,
    export_readiness_errors,
    iter_turrets,
    load_project,
    save_project,
    turret_world_col,
    turret_world_row,
    validate_project,
    wrap_seam_warning,
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


class LevelEditor(tk.Tk):
    def __init__(self, repo_root):
        super().__init__()
        self.repo_root = Path(repo_root)
        self.data = load_engine_data(self.repo_root)
        self.project_dir = self.repo_root / "tools" / "level_editor" / "projects"
        self.project_dir.mkdir(parents=True, exist_ok=True)

        self.project = LevelProject(
            name="stage_test",
            metatile_rows=[row[:] for row in self.data.stage_rows],
            palette=dict(self.data.source_palette),
            scroll_frame_divider=self.data.source_scroll_frame_divider,
            objects=[dict(t) for t in self.data.source_turrets],
        )
        self.project_path = None
        self.saved_state = self._project_state()
        self.undo_stack = []
        self.redo_stack = []
        self.paint_gesture_before = None

        self.selected_tile = 0
        self.metatile_image_cache = {}
        self.last_painted_cell = None
        self.edit_mode = tk.StringVar(value="terrain")   # "terrain" | "turret"
        self.selected_turret = None                      # index into project.objects
        self.show_grid = tk.BooleanVar(value=True)
        self.stage_row_count = tk.IntVar(value=self.project.height)
        self.duration_text = tk.StringVar()
        self.status_text = tk.StringVar()
        self.scroll_divider_var = tk.IntVar(value=self.project.scroll_frame_divider)
        self.palette_vars = {
            key: tk.IntVar(value=self.project.palette[key])
            for key in ("background", "multicolour1", "multicolour2", "character")
        }

        self.geometry("780x900")
        self.minsize(640, 640)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menu()
        self._build_ui()
        self._draw_palette()
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()

    @property
    def stage_rows(self):
        return self.project.metatile_rows

    @property
    def level_height(self):
        return self.project.height * METATILE_PIXELS

    def _project_state(self):
        return (
            self.project.name,
            tuple(tuple(row) for row in self.project.metatile_rows),
            tuple(sorted(self.project.palette.items())),
            self.project.scroll_frame_divider,
            tuple(self._object_key(o) for o in self.project.objects),
            tuple(sorted(self.project.metatile_metadata.items())),
        )

    @staticmethod
    def _object_key(obj):
        if isinstance(obj, dict):
            return tuple(sorted((k, v) for k, v in obj.items()
                                if not isinstance(v, (list, dict))))
        return ("_opaque", repr(obj))

    @staticmethod
    def _object_from_key(key):
        if key and key[0] == "_opaque":
            return None
        return {k: v for k, v in key}

    def _is_dirty(self):
        return self._project_state() != self.saved_state

    def _build_menu(self):
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="New Project…", accelerator="Ctrl+N", command=self._new_project)
        file_menu.add_command(label="Open JSON…", accelerator="Ctrl+O", command=self._open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self._save_project)
        file_menu.add_command(label="Save As…", accelerator="Ctrl+Shift+S", command=self._save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export KickAssembler…", command=self._export_kickassembler)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", accelerator="Ctrl+Q", command=self._on_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        self.edit_menu = tk.Menu(menu_bar, tearoff=False)
        self.edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self._undo)
        self.edit_menu.add_command(label="Redo", accelerator="Ctrl+Shift+Z", command=self._redo)
        menu_bar.add_cascade(label="Edit", menu=self.edit_menu)

        self.config(menu=menu_bar)

        self.bind_all("<Control-n>", lambda event: self._new_project())
        self.bind_all("<Control-o>", lambda event: self._open_project())
        self.bind_all("<Control-s>", lambda event: self._save_project())
        self.bind_all("<Control-Shift-S>", lambda event: self._save_project_as())
        self.bind_all("<Control-z>", lambda event: self._undo())
        self.bind_all("<Control-Shift-Z>", lambda event: self._redo())
        self.bind_all("<Control-q>", lambda event: self._on_close())

        if sys.platform == "darwin":
            self.bind_all("<Command-n>", lambda event: self._new_project())
            self.bind_all("<Command-o>", lambda event: self._open_project())
            self.bind_all("<Command-s>", lambda event: self._save_project())
            self.bind_all("<Command-Shift-S>", lambda event: self._save_project_as())
            self.bind_all("<Command-z>", lambda event: self._undo())
            self.bind_all("<Command-Shift-Z>", lambda event: self._redo())
            self.bind_all("<Command-q>", lambda event: self._on_close())

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="19656 Level Editor", font=("TkDefaultFont", 12, "bold")).pack(side="left")

        ttk.Checkbutton(
            toolbar, text="Metatile grid", variable=self.show_grid, command=self._draw_level
        ).pack(side="right")

        ttk.Label(toolbar, text="   Mode:").pack(side="left", padx=(16, 2))
        ttk.Radiobutton(
            toolbar, text="Terrain", value="terrain",
            variable=self.edit_mode, command=self._on_mode_change,
        ).pack(side="left")
        ttk.Radiobutton(
            toolbar, text="Turrets", value="turret",
            variable=self.edit_mode, command=self._on_mode_change,
        ).pack(side="left")
        self.delete_turret_button = ttk.Button(
            toolbar, text="Delete turret", command=self._delete_selected_turret, state="disabled",
        )
        self.delete_turret_button.pack(side="left", padx=(8, 0))

        stage_controls = ttk.Frame(self, padding=(8, 0, 8, 4))
        stage_controls.pack(fill="x")
        ttk.Label(stage_controls, text="Stage rows:").pack(side="left")
        self.stage_rows_spinbox = ttk.Spinbox(
            stage_controls,
            from_=MIN_STAGE_ROWS,
            to=MAX_STAGE_ROWS,
            width=6,
            textvariable=self.stage_row_count,
            command=self._apply_stage_row_count,
        )
        self.stage_rows_spinbox.pack(side="left", padx=(5, 8))
        self.stage_rows_spinbox.bind("<Return>", self._apply_stage_row_count)
        self.stage_rows_spinbox.bind("<FocusOut>", self._apply_stage_row_count)
        ttk.Label(stage_controls, textvariable=self.duration_text).pack(side="left")

        level_settings = ttk.Frame(self, padding=(8, 0, 8, 4))
        level_settings.pack(fill="x")
        ttk.Label(level_settings, text="Palette:").pack(side="left")
        palette_specs = (
            ("BG", "background", 15),
            ("MC1", "multicolour1", 15),
            ("MC2", "multicolour2", 15),
            ("CHAR", "character", 7),
        )
        for label, key, maximum in palette_specs:
            ttk.Label(level_settings, text=label).pack(side="left", padx=(8, 2))
            spin = ttk.Spinbox(
                level_settings, from_=0, to=maximum, width=3,
                textvariable=self.palette_vars[key], command=self._apply_level_settings,
            )
            spin.pack(side="left")
            spin.bind("<Return>", self._apply_level_settings)
            spin.bind("<FocusOut>", self._apply_level_settings)

        ttk.Label(level_settings, text="Scroll divider").pack(side="left", padx=(14, 2))
        divider_spin = ttk.Spinbox(
            level_settings, from_=1, to=255, width=4,
            textvariable=self.scroll_divider_var, command=self._apply_level_settings,
        )
        divider_spin.pack(side="left")
        divider_spin.bind("<Return>", self._apply_level_settings)
        divider_spin.bind("<FocusOut>", self._apply_level_settings)

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        palette_frame = ttk.LabelFrame(body, text="Metatiles", padding=6)
        palette_frame.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        palette_frame.columnconfigure(0, weight=1)
        palette_frame.rowconfigure(0, weight=1)

        self.palette_canvas = tk.Canvas(
            palette_frame, width=210, highlightthickness=0, background=self.cget("background")
        )
        palette_scroll = ttk.Scrollbar(palette_frame, orient="vertical", command=self.palette_canvas.yview)
        self.palette_canvas.configure(yscrollcommand=palette_scroll.set)
        self.palette_canvas.grid(row=0, column=0, sticky="nsew")
        palette_scroll.grid(row=0, column=1, sticky="ns")
        self.palette_canvas.bind("<Button-1>", self._palette_click)
        self._bind_mousewheel(self.palette_canvas)

        self.level_frame = ttk.LabelFrame(body, text="Working stage", padding=6)
        self.level_frame.grid(row=0, column=1, sticky="nsew")
        self.level_frame.columnconfigure(0, weight=1)
        self.level_frame.rowconfigure(0, weight=1)

        self.level_canvas = tk.Canvas(
            self.level_frame,
            width=LEVEL_WIDTH,
            height=700,
            background=C64_COLOURS[self.project.palette["background"]],
            scrollregion=(0, 0, LEVEL_WIDTH, self.level_height),
            highlightthickness=0,
        )
        yscroll = ttk.Scrollbar(self.level_frame, orient="vertical", command=self.level_canvas.yview)
        self.level_canvas.configure(yscrollcommand=yscroll.set)
        self.level_canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        self.level_canvas.bind("<Button-1>", self._level_click_start)
        self.level_canvas.bind("<B1-Motion>", self._level_drag)
        self.level_canvas.bind("<ButtonRelease-1>", self._level_click_end)
        self.level_canvas.bind("<Button-3>", self._level_right_click)
        self.level_canvas.bind("<Control-Button-1>", self._level_right_click)
        self.bind_all("<Delete>", lambda event: self._delete_selected_turret())
        self.bind_all("<BackSpace>", lambda event: self._delete_selected_turret())
        self._bind_mousewheel(self.level_canvas)

        status = ttk.Frame(self, padding=(8, 2, 8, 8))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_text).pack(side="left")
        self._update_status()

    def _bind_mousewheel(self, canvas):
        canvas.bind("<MouseWheel>", lambda event, target=canvas: self._mousewheel(event, target))
        canvas.bind("<Button-4>", lambda event, target=canvas: self._mousewheel_linux(-1, target))
        canvas.bind("<Button-5>", lambda event, target=canvas: self._mousewheel_linux(1, target))

    def _mousewheel(self, event, canvas):
        if sys.platform == "darwin":
            units = -int(event.delta)
        else:
            units = -int(event.delta / 120) if event.delta else 0
        if units:
            canvas.yview_scroll(units, "units")
        return "break"

    def _mousewheel_linux(self, units, canvas):
        canvas.yview_scroll(units, "units")
        return "break"

    def _pixel_colour(self, pair):
        palette = self.project.palette
        if pair == 0:
            index = palette["background"]
        elif pair == 1:
            index = palette["multicolour1"]
        elif pair == 2:
            index = palette["multicolour2"]
        else:
            index = palette["character"]
        return C64_COLOURS[index]

    def _get_metatile_image(self, tile_id):
        palette_key = tuple(self.project.palette[key] for key in (
            "background", "multicolour1", "multicolour2", "character"
        ))
        cache_key = (tile_id, palette_key)
        image = self.metatile_image_cache.get(cache_key)
        if image is not None:
            return image

        tile = self.data.metatiles[tile_id]
        pixel_rows = []
        for char_row in range(METATILE_H):
            for glyph_y in range(CHAR_SIZE):
                row_colours = []
                for char_col in range(METATILE_W):
                    code = tile[char_row * METATILE_W + char_col]
                    bitmap = self.data.glyphs.get(code)
                    if bitmap is None:
                        raise ValueError(f"No terrain glyph bitmap for character {code}")
                    byte = bitmap[glyph_y]
                    for shift in (6, 4, 2, 0):
                        colour = self._pixel_colour((byte >> shift) & 0x03)
                        row_colours.extend((colour, colour))
                pixel_rows.append(row_colours)

        image = tk.PhotoImage(width=METATILE_PIXELS, height=METATILE_PIXELS)
        image.put(" ".join("{" + " ".join(row) + "}" for row in pixel_rows))
        self.metatile_image_cache[cache_key] = image
        return image

    def _draw_metatile(self, canvas, tile_id, x, y, scale=1, tags=()):
        if scale != 1:
            raise ValueError("Metatile preview scaling other than 1 is not supported")
        canvas.create_image(
            x, y, anchor="nw", image=self._get_metatile_image(tile_id), tags=tags
        )

    def _draw_palette(self):
        self.palette_canvas.delete("all")
        item_height = 46
        for tile_id, name in enumerate(METATILE_NAMES):
            y = tile_id * item_height + 4
            tags = (f"tile_{tile_id}",)
            self.palette_canvas.create_rectangle(4, y, 39, y + 35, fill=C64_COLOURS[self.project.palette["background"]], outline="#888888", tags=tags)
            self._draw_metatile(self.palette_canvas, tile_id, 6, y + 2, tags=tags)
            self.palette_canvas.create_text(
                48, y + 17, anchor="w", text=f"{tile_id:2d}  {name}", tags=tags
            )
            if tile_id == self.selected_tile:
                self.palette_canvas.create_rectangle(
                    1, y - 2, 205, y + 38, outline=SELECTED, width=2, tags=tags
                )
        self.palette_canvas.configure(scrollregion=(0, 0, 210, len(METATILE_NAMES) * item_height + 4))

    def _draw_level(self):
        self.level_canvas.delete("all")
        self.level_canvas.configure(scrollregion=(0, 0, LEVEL_WIDTH, self.level_height))
        for row, tiles in enumerate(self.stage_rows):
            for col, tile_id in enumerate(tiles):
                x = col * METATILE_PIXELS
                y = row * METATILE_PIXELS
                self._draw_metatile(self.level_canvas, tile_id, x, y)
        if self.show_grid.get():
            for x in range(0, LEVEL_WIDTH + 1, METATILE_PIXELS):
                self.level_canvas.create_line(x, 0, x, self.level_height, fill=GRID, tags="grid")
            for y in range(0, self.level_height + 1, METATILE_PIXELS):
                self.level_canvas.create_line(0, y, LEVEL_WIDTH, y, fill=GRID, tags="grid")
        self._draw_turret_markers()

    def _palette_click(self, event):
        y = self.palette_canvas.canvasy(event.y)
        tile_id = int((y - 4) // 46)
        if 0 <= tile_id < len(METATILE_NAMES):
            self.selected_tile = tile_id
            self._draw_palette()
            self._update_status()

    # ---- level-canvas input dispatch (terrain paint vs turret placement) ----
    def _cell_from_event(self, event):
        x = int(self.level_canvas.canvasx(event.x))
        y = int(self.level_canvas.canvasy(event.y))
        col = x // METATILE_PIXELS
        row = y // METATILE_PIXELS
        if 0 <= row < self.project.height and 0 <= col < METATILES_PER_ROW:
            return row, col
        return None

    def _on_mode_change(self):
        self.selected_turret = None
        self._draw_level()
        self._update_turret_ui()
        self._update_status()

    def _level_click_start(self, event):
        if self.edit_mode.get() == "turret":
            self._turret_click(event)
            return "break"
        self._paint_start(event)

    def _level_drag(self, event):
        if self.edit_mode.get() == "turret":
            return "break"
        self._paint_event(event)

    def _level_click_end(self, event=None):
        if self.edit_mode.get() == "turret":
            return "break"
        self._paint_end(event)

    def _level_right_click(self, event):
        if self.edit_mode.get() != "turret":
            return
        cell = self._cell_from_event(event)
        if cell is None:
            return "break"
        self._remove_turret_at(*cell)
        return "break"

    # ---- turret placement -------------------------------------------------
    def _turret_index_at(self, row, col):
        for index, obj in enumerate(self.project.objects):
            if (isinstance(obj, dict) and obj.get("type") == OBJECT_TYPE_TURRET
                    and obj.get("metatileRow") == row and obj.get("metatileCol") == col):
                return index
        return None

    def _turret_index_in_row(self, row):
        for index, obj in enumerate(self.project.objects):
            if (isinstance(obj, dict) and obj.get("type") == OBJECT_TYPE_TURRET
                    and obj.get("metatileRow") == row):
                return index
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
        row_conflict = self._turret_index_in_row(row)
        if row_conflict is not None:
            self.bell()
            self.status_text.set(
                f"Metatile row {row} already has a turret (one turret per world row)."
            )
            return
        if self._turret_count() >= MAX_TURRETS:
            self.bell()
            self.status_text.set(
                f"Maximum {MAX_TURRETS} turrets (engine private glyph namespace)."
            )
            return
        before = self._project_state()
        self.project.objects.append(
            {"type": OBJECT_TYPE_TURRET, "metatileRow": row, "metatileCol": col}
        )
        self.selected_turret = len(self.project.objects) - 1
        self._push_undo_state(before)
        self._draw_level()
        self._update_turret_ui()
        self._update_document_ui()

    def _remove_turret_at(self, row, col):
        index = self._turret_index_at(row, col)
        if index is None:
            return
        before = self._project_state()
        del self.project.objects[index]
        self.selected_turret = None
        self._push_undo_state(before)
        self._draw_level()
        self._update_turret_ui()
        self._update_document_ui()

    def _delete_selected_turret(self):
        if self.edit_mode.get() != "turret" or self.selected_turret is None:
            return "break"
        if not (0 <= self.selected_turret < len(self.project.objects)):
            self.selected_turret = None
            return "break"
        before = self._project_state()
        del self.project.objects[self.selected_turret]
        self.selected_turret = None
        self._push_undo_state(before)
        self._draw_level()
        self._update_turret_ui()
        self._update_document_ui()
        return "break"

    def _update_turret_ui(self):
        has_selection = (
            self.edit_mode.get() == "turret"
            and self.selected_turret is not None
            and 0 <= (self.selected_turret or -1) < len(self.project.objects)
        )
        self.delete_turret_button.configure(state="normal" if has_selection else "disabled")

    def _draw_turret_markers(self):
        self.level_canvas.delete("turret_marker")
        for index, obj in enumerate(self.project.objects):
            if not (isinstance(obj, dict) and obj.get("type") == OBJECT_TYPE_TURRET):
                continue
            row, col = obj.get("metatileRow", 0), obj.get("metatileCol", 0)
            x0 = col * METATILE_PIXELS
            y0 = row * METATILE_PIXELS
            x1 = x0 + METATILE_PIXELS
            y1 = y0 + METATILE_PIXELS
            active = self.edit_mode.get() == "turret"
            outline = SELECTED if (active and index == self.selected_turret) else "#ff5030"
            width = 3 if (active and index == self.selected_turret) else 2
            self.level_canvas.create_rectangle(
                x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=outline, width=width,
                tags="turret_marker",
            )
            # 2x2 body footprint (chars col*4+1..+2, row*4+1..+2)
            bx = x0 + CHAR_SIZE
            by = y0 + CHAR_SIZE
            self.level_canvas.create_rectangle(
                bx, by, bx + 2 * CHAR_SIZE, by + 2 * CHAR_SIZE,
                outline=outline, fill="", width=1, tags="turret_marker",
            )
            self.level_canvas.create_text(
                x0 + METATILE_PIXELS / 2, y0 + METATILE_PIXELS / 2,
                text="T", fill=outline, font=("TkDefaultFont", 10, "bold"),
                tags="turret_marker",
            )

    def _paint_start(self, event):
        self.paint_gesture_before = self._project_state()
        self.last_painted_cell = None
        self._paint_event(event)

    def _paint_event(self, event):
        x = int(self.level_canvas.canvasx(event.x))
        y = int(self.level_canvas.canvasy(event.y))
        col = x // METATILE_PIXELS
        row = y // METATILE_PIXELS
        cell = (row, col)
        if not (0 <= row < self.project.height and 0 <= col < METATILES_PER_ROW):
            return
        if cell == self.last_painted_cell:
            return
        self.last_painted_cell = cell
        if self.stage_rows[row][col] == self.selected_tile:
            return
        self.stage_rows[row][col] = self.selected_tile
        self._redraw_cell(row, col)
        self._update_document_ui()

    def _paint_end(self, event=None):
        self.last_painted_cell = None
        if self.paint_gesture_before is not None and self.paint_gesture_before != self._project_state():
            self._push_undo_state(self.paint_gesture_before)
        self.paint_gesture_before = None
        self._update_document_ui()

    def _redraw_cell(self, row, col):
        x0 = col * METATILE_PIXELS
        y0 = row * METATILE_PIXELS
        x1 = x0 + METATILE_PIXELS
        y1 = y0 + METATILE_PIXELS
        self.level_canvas.delete(f"cell_{row}_{col}")
        tag = (f"cell_{row}_{col}",)
        self.level_canvas.create_rectangle(x0, y0, x1, y1, fill=C64_COLOURS[self.project.palette["background"]], outline="", tags=tag)
        self._draw_metatile(self.level_canvas, self.stage_rows[row][col], x0, y0, tags=tag)
        if self.show_grid.get():
            self.level_canvas.create_rectangle(x0, y0, x1, y1, outline=GRID, tags=tag)
        if self._turret_index_at(row, col) is not None:
            self._draw_turret_markers()

    def _apply_stage_row_count(self, event=None):
        try:
            requested_rows = int(self.stage_row_count.get())
        except (tk.TclError, ValueError):
            self.stage_row_count.set(self.project.height)
            return "break" if event else None

        requested_rows = max(MIN_STAGE_ROWS, min(MAX_STAGE_ROWS, requested_rows))
        current_rows = self.project.height
        if requested_rows == current_rows:
            self.stage_row_count.set(current_rows)
            return "break" if event else None

        before = self._project_state()

        if requested_rows < current_rows:
            removed_rows = self.stage_rows[requested_rows:]
            has_terrain = any(tile_id != 0 for row in removed_rows for tile_id in row)
            if has_terrain and not messagebox.askyesno(
                "Reduce stage height?",
                f"Rows {requested_rows}..{current_rows - 1} contain terrain and will be discarded.\n\n"
                "Reduce the stage height anyway?",
                parent=self,
            ):
                self.stage_row_count.set(current_rows)
                return "break" if event else None
            del self.stage_rows[requested_rows:]
        else:
            self.stage_rows.extend(
                [[0] * METATILES_PER_ROW for _ in range(requested_rows - current_rows)]
            )

        self._push_undo_state(before)
        self.stage_row_count.set(self.project.height)
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()
        return "break" if event else None

    def _apply_level_settings(self, event=None):
        try:
            new_palette = {key: int(variable.get()) for key, variable in self.palette_vars.items()}
            new_divider = int(self.scroll_divider_var.get())
        except (tk.TclError, ValueError):
            self._sync_level_settings_controls()
            return "break" if event else None

        ranges = {"background": 15, "multicolour1": 15, "multicolour2": 15, "character": 7}
        for key, maximum in ranges.items():
            if not 0 <= new_palette[key] <= maximum:
                self._sync_level_settings_controls()
                return "break" if event else None
        if not 1 <= new_divider <= 255:
            self._sync_level_settings_controls()
            return "break" if event else None

        if new_palette == self.project.palette and new_divider == self.project.scroll_frame_divider:
            return "break" if event else None

        before = self._project_state()
        self.project.palette = new_palette
        self.project.scroll_frame_divider = new_divider
        self.metatile_image_cache.clear()
        self._push_undo_state(before)
        self.level_canvas.configure(background=C64_COLOURS[self.project.palette["background"]])
        self._draw_palette()
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()
        return "break" if event else None

    def _sync_level_settings_controls(self):
        self.scroll_divider_var.set(self.project.scroll_frame_divider)
        for key, variable in self.palette_vars.items():
            variable.set(self.project.palette[key])

    def _update_stage_info(self):
        total_pixels = self.level_height
        seconds = total_pixels * self.project.scroll_frame_divider / PAL_FRAMES_PER_SECOND
        minutes = int(seconds // 60)
        remaining_seconds = int(round(seconds - minutes * 60))
        if remaining_seconds == 60:
            minutes += 1
            remaining_seconds = 0
        self.duration_text.set(
            f"≈ {minutes}:{remaining_seconds:02d} at 1 px/{self.project.scroll_frame_divider} frame"
            f"{"s" if self.project.scroll_frame_divider != 1 else ""} PAL  "
            f"({LEVEL_WIDTH} x {total_pixels}px)"
        )
        self._update_status()

    def _update_status(self):
        if self.edit_mode.get() == "turret":
            self.status_text.set(
                f"Turret mode: {self._turret_count()}/{MAX_TURRETS} placed  |  "
                "click a metatile to place/select, right-click or Delete to remove  |  "
                f"Level: {METATILES_PER_ROW} x {self.project.height} metatiles"
            )
            return
        self.status_text.set(
            f"Selected: {self.selected_tile} {METATILE_NAMES[self.selected_tile]}  |  "
            f"Level: {METATILES_PER_ROW} x {self.project.height} metatiles  |  "
            f"Palette {self.project.palette['background']}/{self.project.palette['multicolour1']}/"
            f"{self.project.palette['multicolour2']}/{self.project.palette['character']}  |  "
            f"Divider {self.project.scroll_frame_divider}"
        )

    def _update_document_ui(self):
        dirty_mark = " *" if self._is_dirty() else ""
        self.title(f"19656 Level Editor - {self.project.name}{dirty_mark}")
        path_text = self.project_path.name if self.project_path else "not saved as JSON"
        self.level_frame.configure(text=f"Working stage: {self.project.name} ({path_text})")
        self.edit_menu.entryconfigure("Undo", state="normal" if self.undo_stack else "disabled")
        self.edit_menu.entryconfigure("Redo", state="normal" if self.redo_stack else "disabled")
        self._update_turret_ui()
        self._update_status()

    def _push_undo_state(self, state):
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def _restore_state(self, state):
        name, rows, palette_items, scroll_divider, object_keys, metadata_items = state
        self.project.name = name
        self.project.metatile_rows = [list(row) for row in rows]
        self.project.palette = dict(palette_items)
        self.project.scroll_frame_divider = scroll_divider
        self.metatile_image_cache.clear()
        self.project.objects = [o for o in (self._object_from_key(k) for k in object_keys)
                                if o is not None]
        self.selected_turret = None
        self.project.metatile_metadata = dict(metadata_items)
        self.stage_row_count.set(self.project.height)
        self.scroll_divider_var.set(self.project.scroll_frame_divider)
        for key, variable in self.palette_vars.items():
            variable.set(self.project.palette[key])
        self.level_canvas.configure(background=C64_COLOURS[self.project.palette["background"]])
        self._draw_palette()
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()

    def _undo(self):
        if not self.undo_stack:
            return "break"
        current = self._project_state()
        state = self.undo_stack.pop()
        self.redo_stack.append(current)
        self._restore_state(state)
        return "break"

    def _redo(self):
        if not self.redo_stack:
            return "break"
        current = self._project_state()
        state = self.redo_stack.pop()
        self.undo_stack.append(current)
        self._restore_state(state)
        return "break"

    def _confirm_discard_changes(self):
        if not self._is_dirty():
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save changes to {self.project.name} before continuing?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return self._save_project()
        return True

    def _new_project(self):
        if not self._confirm_discard_changes():
            return "break"

        name = simpledialog.askstring(
            "New Project",
            "Project name:",
            initialvalue="new_level",
            parent=self,
        )
        if name is None:
            return "break"
        name = name.strip()
        if not name:
            messagebox.showerror("New Project", "Project name cannot be empty.", parent=self)
            return "break"

        rows = simpledialog.askinteger(
            "New Project",
            "Stage rows:",
            initialvalue=DEFAULT_STAGE_ROWS,
            minvalue=MIN_STAGE_ROWS,
            maxvalue=MAX_STAGE_ROWS,
            parent=self,
        )
        if rows is None:
            return "break"

        self.metatile_image_cache.clear()
        # Seed one turret near the START (bottom) so a new project is
        # export-ready; the engine currently needs 1..MAX_TURRETS.
        seed_row = max(0, rows - 3)
        self.project = LevelProject(
            name=name,
            metatile_rows=[[0] * METATILES_PER_ROW for _ in range(rows)],
            palette=dict(DEFAULT_PALETTE),
            scroll_frame_divider=DEFAULT_SCROLL_FRAME_DIVIDER,
            objects=[{"type": OBJECT_TYPE_TURRET, "metatileRow": seed_row, "metatileCol": 4}],
        )
        self.project_path = None
        # A newly created project has not been persisted yet, so treat it as dirty.
        self.saved_state = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.stage_row_count.set(rows)
        self.scroll_divider_var.set(self.project.scroll_frame_divider)
        for key, variable in self.palette_vars.items():
            variable.set(self.project.palette[key])
        self.level_canvas.yview_moveto(0)
        self.level_canvas.configure(background=C64_COLOURS[self.project.palette["background"]])
        self._draw_palette()
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()
        return "break"

    def _open_project(self):
        if not self._confirm_discard_changes():
            return "break"

        path = filedialog.askopenfilename(
            title="Open 19656 Level Project",
            initialdir=self.project_dir,
            filetypes=(("19656 level projects", "*.json"), ("JSON files", "*.json"), ("All files", "*.*")),
            parent=self,
        )
        if not path:
            return "break"

        try:
            project = load_project(path)
        except (OSError, ProjectValidationError) as exc:
            messagebox.showerror("Open Project", str(exc), parent=self)
            return "break"

        self.project = project
        self.metatile_image_cache.clear()
        self.project_path = Path(path)
        self.saved_state = self._project_state()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.stage_row_count.set(self.project.height)
        self.scroll_divider_var.set(self.project.scroll_frame_divider)
        for key, variable in self.palette_vars.items():
            variable.set(self.project.palette[key])
        self.level_canvas.yview_moveto(0)
        self.level_canvas.configure(background=C64_COLOURS[self.project.palette["background"]])
        self._draw_palette()
        self._draw_level()
        self._update_stage_info()
        self._update_document_ui()
        return "break"

    def _validate_before_write(self):
        errors = validate_project(self.project)
        if errors:
            messagebox.showerror(
                "Project validation failed",
                "\n".join(errors),
                parent=self,
            )
            return False

        seam_warning = wrap_seam_warning(self.project)
        if seam_warning and not messagebox.askyesno(
            "Possible wrap seam",
            seam_warning + "\n\nSave anyway?",
            parent=self,
        ):
            return False
        return True

    def _save_project(self):
        if self.project_path is None:
            return self._save_project_as()
        return self._write_project(self.project_path)

    def _save_project_as(self):
        if not self._validate_before_write():
            return False

        initial_name = f"{self.project.name}.json"
        path = filedialog.asksaveasfilename(
            title="Save 19656 Level Project",
            initialdir=self.project_dir,
            initialfile=initial_name,
            defaultextension=".json",
            filetypes=(("19656 level projects", "*.json"), ("JSON files", "*.json"), ("All files", "*.*")),
            parent=self,
        )
        if not path:
            return False
        return self._write_project(Path(path), already_validated=True)

    def _write_project(self, path, already_validated=False):
        if not already_validated and not self._validate_before_write():
            return False
        try:
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
        output_dir = filedialog.askdirectory(
            title="Export KickAssembler stage files",
            initialdir=self.repo_root / "src" / "generated",
            parent=self,
        )
        if not output_dir:
            return "break"
        try:
            paths = export_project(self.project, self.data.metatiles, output_dir)
        except (OSError, ProjectValidationError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return "break"
        messagebox.showinfo(
            "KickAssembler export complete",
            "Generated:\n" + "\n".join(p.name for p in paths) + "\n\n"
            "stage_config.asm / stage_turrets.asm are imported early by main.asm; "
            "stage_test.asm assembles at $6600. Rebuild to play the authored level.",
            parent=self,
        )
        return "break"

    def _on_close(self):
        if self._confirm_discard_changes():
            self.destroy()
        return "break"


def find_repo_root():
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        if (parent / "src" / "main.asm").is_file() and \
                (parent / "src" / "generated" / "stage_test.asm").is_file():
            return parent
    raise FileNotFoundError(
        "Could not find repo root containing src/main.asm and src/generated/stage_test.asm"
    )


def main():
    try:
        editor = LevelEditor(find_repo_root())
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("19656 Level Editor", str(exc))
        root.destroy()
        return 1
    editor.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
