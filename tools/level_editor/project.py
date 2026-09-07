"""Project model and JSON persistence for the 19656 level editor.

A level is a self-contained PACKAGE. It owns:
  * the terrain / metatile map        (metatile_rows)
  * palette + scroll config           (palette, scroll_frame_divider)
  * authored gameplay objects         (objects  -> turrets, 0..N)
  * its own terrain tileset           (tileset  -> glyph bitmaps + metatile defs)
  * enemy-wave timing                 (wave_definitions + wave_triggers)

formatVersion 3 adds `tileset`, `waveDefinitions` and `waveTriggers` and lifts
the artificial 3-turret cap. V1/V2 files still load (migrated on read).
"""
from dataclasses import dataclass, field
import json
from pathlib import Path

from engine_data import (
    ATTACK_COUNT,
    DEFAULT_PALETTE,
    DEFAULT_SCROLL_FRAME_DIVIDER,
    ENEMY_TYPE_COUNT,
    ENGINE_MAX_STAGE_ROWS,
    MAX_AUTHORED_TURRETS,
    METATILE_DEF_COUNT,
    METATILE_H,
    METATILE_W,
    METATILES_PER_ROW,
    TERRAIN_GLYPH_BASE,
    TERRAIN_GLYPH_NAMESPACE,
    TURRET_POOL,
    VIEWPORT_ROWS,
)

FORMAT_VERSION = 3
SUPPORTED_FORMAT_VERSIONS = (1, 2, 3)
MIN_STAGE_ROWS = 1
MAX_STAGE_ROWS = ENGINE_MAX_STAGE_ROWS
DEFAULT_STAGE_ROWS = 188

# --- Authored gameplay objects -------------------------------------------------
OBJECT_TYPE_TURRET = "turret"
SUPPORTED_OBJECT_TYPES = (OBJECT_TYPE_TURRET,)

# The engine streams authored turrets through a fixed pool of TURRET_POOL live
# slots. Every live turret shares one 4-code body glyph set, so concurrent
# capacity is not bounded by glyph codes and there is NO viewport-density limit
# to enforce here: a level with 4 (or up to ~7) turrets in one gameplay screen
# is valid. The authored count is bounded only by the 8-bit streaming cursor.
# See src/background_turrets.asm.
MAX_TURRETS = MAX_AUTHORED_TURRETS
TURRET_BODY_CHAR_OFFSET = 1          # 2x2 body offset inside the 4x4 metatile

WAVE_MAX_COMPOSITION_COUNT = 8       # attackEnemyCount ceiling in the engine


def turret_world_row(metatile_row):
    """Metatile-grid row -> world CHARACTER / logical row of the turret's top."""
    return metatile_row * METATILE_H + TURRET_BODY_CHAR_OFFSET


def turret_world_col(metatile_col):
    """Metatile-grid col -> world CHARACTER column of the turret's left cell."""
    return metatile_col * METATILE_W + TURRET_BODY_CHAR_OFFSET


def iter_turrets(project):
    """Yield the turret objects in deterministic (metatileRow, metatileCol) order."""
    turrets = [o for o in project.objects
               if isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET]
    turrets.sort(key=lambda o: (o.get("metatileRow", 0), o.get("metatileCol", 0)))
    return turrets


# --- Gameplay-viewport geometry (editor-only aid; never serialised) -----------

def stage_logical_rows(project_or_height):
    height = project_or_height.height if hasattr(project_or_height, "height") else int(project_or_height)
    return height * METATILE_H


def max_viewport_top(project):
    """Highest valid top logical row for the 23-row gameplay aperture."""
    return max(0, stage_logical_rows(project) - VIEWPORT_ROWS)


def clamp_viewport_top(top, project):
    return max(0, min(int(top), max_viewport_top(project)))


def default_viewport_top(project):
    """Bottom-origin boot view: matrix row 23 shows the authored last logical row."""
    return max_viewport_top(project)


def viewport_logical_range(top):
    """(first, last) logical row visible for a given top. No wrap in the editor."""
    return int(top), int(top) + VIEWPORT_ROWS - 1


def viewport_metatile_range(top):
    first, last = viewport_logical_range(top)
    return first // METATILE_H, last // METATILE_H


class ProjectValidationError(ValueError):
    """Raised when a project does not satisfy the level-editor project contract."""


@dataclass
class LevelProject:
    name: str
    metatile_rows: list
    palette: dict = field(default_factory=lambda: dict(DEFAULT_PALETTE))
    scroll_frame_divider: int = DEFAULT_SCROLL_FRAME_DIVIDER
    objects: list = field(default_factory=list)
    metatile_metadata: dict = field(default_factory=dict)
    # Per-level terrain tileset: {"glyphCount": N, "glyphs": [[8]...],
    # "metatileDefs": [[16]...16]}. None on a bare test project; the editor and
    # the migration path always populate it. Codes run 160..160+glyphCount-1.
    tileset: dict = None
    # Authored enemy-wave timing. wave_definitions are reusable ("what");
    # wave_triggers anchor them to world/logical rows ("when").
    wave_definitions: list = field(default_factory=list)
    wave_triggers: list = field(default_factory=list)

    @property
    def width(self):
        return METATILES_PER_ROW

    @property
    def height(self):
        return len(self.metatile_rows)

    def clone_rows(self):
        return [row[:] for row in self.metatile_rows]

    def to_dict(self):
        data = {
            "formatVersion": FORMAT_VERSION,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "scrollFrameDivider": self.scroll_frame_divider,
            "palette": {
                "background": self.palette["background"],
                "multicolour1": self.palette["multicolour1"],
                "multicolour2": self.palette["multicolour2"],
                "character": self.palette["character"],
            },
            "metatileRows": self.clone_rows(),
            "metatileMetadata": dict(self.metatile_metadata),
            "objects": self.canonical_objects(),
            "tileset": self.canonical_tileset(),
            "waveDefinitions": self.canonical_wave_definitions(),
            "waveTriggers": self.canonical_wave_triggers(),
        }
        return data

    def canonical_objects(self):
        turrets = [
            {"type": OBJECT_TYPE_TURRET,
             "metatileRow": int(o["metatileRow"]),
             "metatileCol": int(o["metatileCol"])}
            for o in iter_turrets(self)
        ]
        others = [o for o in self.objects
                  if not (isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET)]
        return turrets + others

    def canonical_tileset(self):
        if not self.tileset:
            return None
        glyphs = [list(int(b) & 0xFF for b in g) for g in self.tileset["glyphs"]]
        defs = [list(int(c) for c in d) for d in self.tileset["metatileDefs"]]
        return {
            "glyphCount": int(self.tileset.get("glyphCount", len(glyphs))),
            "glyphs": glyphs,
            "metatileDefs": defs,
        }

    def canonical_wave_definitions(self):
        out = []
        for wd in sorted(self.wave_definitions, key=lambda d: str(d.get("id", ""))):
            comp = [
                {"enemyType": int(c.get("enemyType", 0)), "count": int(c.get("count", 1))}
                for c in wd.get("composition", [])
            ]
            interval = wd.get("spawnInterval", None)
            out.append({
                "id": str(wd["id"]),
                "name": str(wd.get("name", wd["id"])),
                "attackId": int(wd.get("attackId", 0)),
                "composition": comp,
                "spawnInterval": None if interval in (None, "") else int(interval),
            })
        return out

    def canonical_wave_triggers(self):
        out = []
        for wt in sorted(self.wave_triggers, key=lambda t: (-int(t.get("worldRow", 0)), str(t.get("id", "")))):
            out.append({
                "id": str(wt["id"]),
                "worldRow": int(wt["worldRow"]),
                "waveDef": str(wt["waveDef"]),
            })
        return out

    # -- convenience --------------------------------------------------------
    def wave_definition(self, def_id):
        for wd in self.wave_definitions:
            if str(wd.get("id")) == str(def_id):
                return wd
        return None


def composition_size(wave_def):
    return sum(int(c.get("count", 0)) for c in wave_def.get("composition", []))


# --- validation -------------------------------------------------------------

def _validate_palette(palette, errors):
    required = ("background", "multicolour1", "multicolour2", "character")
    if not isinstance(palette, dict):
        errors.append("palette must be an object/dictionary.")
        return
    for key in required:
        if key not in palette:
            errors.append(f"palette is missing {key!r}.")
            continue
        value = palette[key]
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"palette.{key} must be an integer C64 colour index.")
            continue
        maximum = 7 if key == "character" else 15
        if not 0 <= value <= maximum:
            errors.append(f"palette.{key} must be 0..{maximum}; got {value}.")


def validate_project(project):
    errors = []

    if not isinstance(project.name, str) or not project.name.strip():
        errors.append("Project name must be a non-empty string.")

    if isinstance(project.scroll_frame_divider, bool) or not isinstance(project.scroll_frame_divider, int):
        errors.append("scrollFrameDivider must be an integer.")
    elif not 1 <= project.scroll_frame_divider <= 255:
        errors.append("scrollFrameDivider must be 1..255.")

    _validate_palette(project.palette, errors)

    if not isinstance(project.metatile_rows, list):
        errors.append("metatileRows must be a list.")
        return errors

    if not MIN_STAGE_ROWS <= len(project.metatile_rows) <= MAX_STAGE_ROWS:
        errors.append(
            f"Stage height must be {MIN_STAGE_ROWS}..{MAX_STAGE_ROWS} metatile rows; "
            f"got {len(project.metatile_rows)}."
        )

    for row_index, row in enumerate(project.metatile_rows):
        if not isinstance(row, list):
            errors.append(f"Row {row_index} is not a list.")
            continue
        if len(row) != METATILES_PER_ROW:
            errors.append(
                f"Row {row_index} must contain exactly {METATILES_PER_ROW} metatile IDs; got {len(row)}."
            )
            continue
        for col_index, tile_id in enumerate(row):
            if isinstance(tile_id, bool) or not isinstance(tile_id, int):
                errors.append(f"Cell ({row_index}, {col_index}) is not an integer metatile ID.")
            elif not 0 <= tile_id < METATILE_DEF_COUNT:
                errors.append(
                    f"Cell ({row_index}, {col_index}) has metatile ID {tile_id}; "
                    f"valid IDs are 0..{METATILE_DEF_COUNT - 1}."
                )

    if not isinstance(project.objects, list):
        errors.append("objects must be a list.")
    else:
        _validate_objects(project, errors)
    if not isinstance(project.metatile_metadata, dict):
        errors.append("metatileMetadata must be an object/dictionary.")

    if project.tileset is not None:
        _validate_tileset(project.tileset, errors)

    _validate_waves(project, errors)

    return errors


def _validate_tileset(tileset, errors):
    if not isinstance(tileset, dict):
        errors.append("tileset must be an object/dictionary.")
        return
    glyphs = tileset.get("glyphs")
    defs = tileset.get("metatileDefs")
    count = tileset.get("glyphCount")
    if not isinstance(glyphs, list) or not glyphs:
        errors.append("tileset.glyphs must be a non-empty list of 8-byte rows.")
        return
    if isinstance(count, int) and count != len(glyphs):
        errors.append(f"tileset.glyphCount {count} != len(glyphs) {len(glyphs)}.")
    if not 1 <= len(glyphs) <= TERRAIN_GLYPH_NAMESPACE or len(glyphs) % 8:
        errors.append(
            f"tileset must hold 8..{TERRAIN_GLYPH_NAMESPACE} glyphs in multiples of 8; got {len(glyphs)}."
        )
    for i, g in enumerate(glyphs):
        if not isinstance(g, list) or len(g) != 8 or any(
            isinstance(b, bool) or not isinstance(b, int) or not 0 <= b <= 255 for b in g
        ):
            errors.append(f"tileset.glyphs[{i}] must be 8 bytes 0..255.")
    if not isinstance(defs, list) or len(defs) != METATILE_DEF_COUNT:
        errors.append(f"tileset.metatileDefs must be exactly {METATILE_DEF_COUNT} entries.")
        return
    valid_codes = set(range(TERRAIN_GLYPH_BASE, TERRAIN_GLYPH_BASE + len(glyphs)))
    for i, d in enumerate(defs):
        if not isinstance(d, list) or len(d) != METATILE_W * METATILE_H:
            errors.append(f"tileset.metatileDefs[{i}] must be {METATILE_W * METATILE_H} glyph codes.")
            continue
        bad = sorted({c for c in d if c not in valid_codes})
        if bad:
            errors.append(f"tileset.metatileDefs[{i}] references undefined glyph codes {bad}.")


def turret_screen_peak(project):
    """Highest number of turret bodies that fall within any single
    VIEWPORT_ROWS-logical-row gameplay screen. INFORMATIONAL only - the engine
    shares one body glyph set across all live turrets, so this is never a
    rejection reason; the editor shows it as a status hint. The metatile grid +
    distinct-row rule already bound it to ~6."""
    rows = sorted(turret_world_row(t["metatileRow"]) for t in iter_turrets(project)
                  if isinstance(t.get("metatileRow"), int))
    peak = 0
    for i, r in enumerate(rows):
        peak = max(peak, sum(1 for x in rows[i:] if x <= r + VIEWPORT_ROWS - 1))
    return peak


def _validate_objects(project, errors):
    height = len(project.metatile_rows) if isinstance(project.metatile_rows, list) else 0
    turret_rows = []
    turret_count = 0
    for index, obj in enumerate(project.objects):
        if not isinstance(obj, dict):
            errors.append(f"objects[{index}] must be an object/dictionary.")
            continue
        obj_type = obj.get("type")
        if obj_type not in SUPPORTED_OBJECT_TYPES:
            errors.append(
                f"objects[{index}].type {obj_type!r} is not supported; "
                f"expected one of {list(SUPPORTED_OBJECT_TYPES)}."
            )
            continue
        if obj_type == OBJECT_TYPE_TURRET:
            turret_count += 1
            mrow = obj.get("metatileRow")
            mcol = obj.get("metatileCol")
            if isinstance(mrow, bool) or not isinstance(mrow, int) or not 0 <= mrow < max(height, 1):
                errors.append(
                    f"objects[{index}].metatileRow must be an integer 0..{max(height - 1, 0)}; got {mrow!r}."
                )
            else:
                turret_rows.append(mrow)
            if isinstance(mcol, bool) or not isinstance(mcol, int) or not 0 <= mcol < METATILES_PER_ROW:
                errors.append(
                    f"objects[{index}].metatileCol must be an integer 0..{METATILES_PER_ROW - 1}; got {mcol!r}."
                )
    if turret_count > MAX_TURRETS:
        errors.append(
            f"At most {MAX_TURRETS} authored turrets are supported (8-bit streaming cursor); "
            f"got {turret_count}."
        )
    if len(turret_rows) != len(set(turret_rows)):
        errors.append("Each turret must occupy a distinct metatile row (distinct world character row).")


def _validate_waves(project, errors):
    if not isinstance(project.wave_definitions, list):
        errors.append("waveDefinitions must be a list.")
        return
    if not isinstance(project.wave_triggers, list):
        errors.append("waveTriggers must be a list.")
        return
    slr = stage_logical_rows(project)
    seen_def_ids = set()
    def_ids = set()
    for i, wd in enumerate(project.wave_definitions):
        if not isinstance(wd, dict):
            errors.append(f"waveDefinitions[{i}] must be an object.")
            continue
        wid = wd.get("id")
        if not isinstance(wid, str) or not wid.strip():
            errors.append(f"waveDefinitions[{i}].id must be a non-empty string.")
        elif wid in seen_def_ids:
            errors.append(f"waveDefinitions[{i}].id {wid!r} is duplicated.")
        else:
            seen_def_ids.add(wid)
            def_ids.add(wid)
        aid = wd.get("attackId")
        if isinstance(aid, bool) or not isinstance(aid, int) or not 0 <= aid < ATTACK_COUNT:
            errors.append(f"waveDefinitions[{i}].attackId must be 0..{ATTACK_COUNT - 1}; got {aid!r}.")
        comp = wd.get("composition")
        if not isinstance(comp, list) or not comp:
            errors.append(f"waveDefinitions[{i}].composition must be a non-empty list.")
        else:
            for j, c in enumerate(comp):
                if not isinstance(c, dict):
                    errors.append(f"waveDefinitions[{i}].composition[{j}] must be an object.")
                    continue
                et = c.get("enemyType")
                cn = c.get("count")
                if isinstance(et, bool) or not isinstance(et, int) or not 0 <= et < ENEMY_TYPE_COUNT:
                    errors.append(
                        f"waveDefinitions[{i}].composition[{j}].enemyType must be 0..{ENEMY_TYPE_COUNT - 1}."
                    )
                if isinstance(cn, bool) or not isinstance(cn, int) or not 1 <= cn <= WAVE_MAX_COMPOSITION_COUNT:
                    errors.append(
                        f"waveDefinitions[{i}].composition[{j}].count must be 1..{WAVE_MAX_COMPOSITION_COUNT}."
                    )
        si = wd.get("spawnInterval")
        if si not in (None, "") and (isinstance(si, bool) or not isinstance(si, int) or not 1 <= si <= 255):
            errors.append(f"waveDefinitions[{i}].spawnInterval must be null or 1..255.")

    seen_trigger_ids = set()
    for i, wt in enumerate(project.wave_triggers):
        if not isinstance(wt, dict):
            errors.append(f"waveTriggers[{i}] must be an object.")
            continue
        tid = wt.get("id")
        if not isinstance(tid, str) or not tid.strip():
            errors.append(f"waveTriggers[{i}].id must be a non-empty string.")
        elif tid in seen_trigger_ids:
            errors.append(f"waveTriggers[{i}].id {tid!r} is duplicated.")
        else:
            seen_trigger_ids.add(tid)
        wr = wt.get("worldRow")
        if isinstance(wr, bool) or not isinstance(wr, int) or not 0 <= wr < max(slr, 1):
            errors.append(f"waveTriggers[{i}].worldRow must be 0..{max(slr - 1, 0)}; got {wr!r}.")
        wd_ref = wt.get("waveDef")
        if wd_ref not in def_ids:
            errors.append(f"waveTriggers[{i}].waveDef {wd_ref!r} does not match any waveDefinition id.")


def export_readiness_errors(project):
    """Extra checks required before generating engine-facing ASM. 0 turrets is
    fine now; a per-level tileset is required (the charset export needs it)."""
    errors = validate_project(project)
    if project.tileset is None:
        errors.append("A per-level tileset is required before export (open/save via the editor).")
    return errors


# --- persistence -----------------------------------------------------------

def _require_key(data, key):
    if key not in data:
        raise ProjectValidationError(f"Missing required project field: {key}")
    return data[key]


def _migrate_tileset(raw, default_tileset):
    if isinstance(raw, dict) and raw.get("glyphs") and raw.get("metatileDefs"):
        glyphs = [list(int(b) & 0xFF for b in g) for g in raw["glyphs"]]
        defs = [list(int(c) for c in d) for d in raw["metatileDefs"]]
        return {"glyphCount": int(raw.get("glyphCount", len(glyphs))),
                "glyphs": glyphs, "metatileDefs": defs}
    if default_tileset is not None:
        return {
            "glyphCount": int(default_tileset["glyphCount"]),
            "glyphs": [list(g) for g in default_tileset["glyphs"]],
            "metatileDefs": [list(d) for d in default_tileset["metatileDefs"]],
        }
    return None


def project_from_dict(data, *, default_tileset=None):
    if not isinstance(data, dict):
        raise ProjectValidationError("Project JSON root must be an object.")

    format_version = _require_key(data, "formatVersion")
    if format_version not in SUPPORTED_FORMAT_VERSIONS:
        raise ProjectValidationError(
            f"Unsupported formatVersion {format_version!r}; expected one of {SUPPORTED_FORMAT_VERSIONS}."
        )

    width = _require_key(data, "width")
    if width != METATILES_PER_ROW:
        raise ProjectValidationError(f"Project width must be exactly {METATILES_PER_ROW}; got {width!r}.")

    height = _require_key(data, "height")
    rows = _require_key(data, "metatileRows")
    if isinstance(height, bool) or not isinstance(height, int):
        raise ProjectValidationError("Project height must be an integer.")
    if not isinstance(rows, list):
        raise ProjectValidationError("metatileRows must be a list.")
    if height != len(rows):
        raise ProjectValidationError(
            f"Project height says {height}, but metatileRows contains {len(rows)} rows."
        )

    if format_version == 1:
        palette = dict(DEFAULT_PALETTE)
        scroll_divider = DEFAULT_SCROLL_FRAME_DIVIDER
    else:
        palette = dict(_require_key(data, "palette")) if isinstance(data.get("palette"), dict) else data.get("palette")
        scroll_divider = _require_key(data, "scrollFrameDivider")

    raw_objects = data.get("objects", [])
    if not isinstance(raw_objects, list):
        raise ProjectValidationError("objects must be a list.")

    raw_defs = data.get("waveDefinitions", [])
    raw_triggers = data.get("waveTriggers", [])
    if not isinstance(raw_defs, list) or not isinstance(raw_triggers, list):
        raise ProjectValidationError("waveDefinitions / waveTriggers must be lists.")

    project = LevelProject(
        name=_require_key(data, "name"),
        metatile_rows=[row[:] if isinstance(row, list) else row for row in rows],
        palette=palette,
        scroll_frame_divider=scroll_divider,
        objects=[dict(o) if isinstance(o, dict) else o for o in raw_objects],
        metatile_metadata=data.get("metatileMetadata", {}),
        tileset=_migrate_tileset(data.get("tileset"), default_tileset),
        wave_definitions=[dict(d) if isinstance(d, dict) else d for d in raw_defs],
        wave_triggers=[dict(t) if isinstance(t, dict) else t for t in raw_triggers],
    )
    errors = validate_project(project)
    if errors:
        raise ProjectValidationError("\n".join(errors))
    return project


def load_project(path, *, default_tileset=None):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectValidationError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return project_from_dict(data, default_tileset=default_tileset)


def save_project(project, path):
    errors = validate_project(project)
    if errors:
        raise ProjectValidationError("\n".join(errors))

    path = Path(path)
    payload = json.dumps(project.to_dict(), indent=2, ensure_ascii=False)
    path.write_text(payload + "\n", encoding="utf-8")


def wrap_seam_warning(project):
    """Warn when the first and last metatile rows differ materially."""
    if project.height < 2:
        return None
    first = project.metatile_rows[0]
    last = project.metatile_rows[-1]
    differing_columns = [index for index, (a, b) in enumerate(zip(first, last)) if a != b]
    if len(differing_columns) < 3:
        return None
    return (
        f"The first and last stage rows differ in {len(differing_columns)} of "
        f"{METATILES_PER_ROW} columns. Because the stage wraps vertically, "
        "the wrap seam may be visually obvious."
    )
