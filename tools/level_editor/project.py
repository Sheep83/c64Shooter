"""Project model and JSON persistence for the 19656 level editor."""
from dataclasses import dataclass, field
import json
from pathlib import Path

from engine_data import (
    DEFAULT_PALETTE,
    DEFAULT_SCROLL_FRAME_DIVIDER,
    ENGINE_MAX_STAGE_ROWS,
    METATILE_DEF_COUNT,
    METATILES_PER_ROW,
)

FORMAT_VERSION = 2
LEGACY_FORMAT_VERSION = 1
MIN_STAGE_ROWS = 1
MAX_STAGE_ROWS = ENGINE_MAX_STAGE_ROWS
DEFAULT_STAGE_ROWS = 188

# --- Authored gameplay objects -------------------------------------------------
# The editor owns authored PLACEMENT only. AI / firing cadence / runtime state /
# sprite allocation / activation / collision internals stay engine-owned.
#
# The first (and, this iteration, only) authored object type is the existing
# background turret. It is placed on the metatile grid; the engine derives its
# world CHARACTER coordinates as metatile_index * METATILE_H + 1 (row) and
# metatile_index * METATILE_W + 1 (col) - i.e. the 2x2 body sits centred in the
# metatile, which is exactly where the previous hand-authored turrets sat
# (turretCols 17/29/13 == col*4+1, turretRows 13/29/57 == row*4+1).
OBJECT_TYPE_TURRET = "turret"
SUPPORTED_OBJECT_TYPES = (OBJECT_TYPE_TURRET,)

# Engine limit: the private turret glyph namespace is codes 226..239 (4 glyphs
# per turret), so at most 3 turrets. See src/background_turrets.asm.
MAX_TURRETS = 3
TURRET_BODY_CHAR_OFFSET = 1          # 2x2 body offset inside the 4x4 metatile


def turret_world_row(metatile_row):
    """Metatile-grid row -> world CHARACTER / logical row of the turret's top."""
    return metatile_row * 4 + TURRET_BODY_CHAR_OFFSET


def turret_world_col(metatile_col):
    """Metatile-grid col -> world CHARACTER column of the turret's left cell."""
    return metatile_col * 4 + TURRET_BODY_CHAR_OFFSET


def iter_turrets(project):
    """Yield the turret objects in deterministic (metatileRow, metatileCol) order."""
    turrets = [o for o in project.objects
               if isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET]
    turrets.sort(key=lambda o: (o.get("metatileRow", 0), o.get("metatileCol", 0)))
    return turrets


class ProjectValidationError(ValueError):
    """Raised when a project does not satisfy the level-editor project contract."""


@dataclass
class LevelProject:
    name: str
    metatile_rows: list[list[int]]
    palette: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_PALETTE))
    scroll_frame_divider: int = DEFAULT_SCROLL_FRAME_DIVIDER
    objects: list = field(default_factory=list)
    metatile_metadata: dict = field(default_factory=dict)

    @property
    def width(self):
        return METATILES_PER_ROW

    @property
    def height(self):
        return len(self.metatile_rows)

    def clone_rows(self):
        return [row[:] for row in self.metatile_rows]

    def to_dict(self):
        return {
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
            "objects": self.canonical_objects(),
            "metatileMetadata": dict(self.metatile_metadata),
        }

    def canonical_objects(self):
        """Deterministic object list: turrets first, sorted by (row, col), with a
        fixed key order. Any non-turret objects keep their original order after."""
        turrets = [
            {"type": OBJECT_TYPE_TURRET,
             "metatileRow": int(o["metatileRow"]),
             "metatileCol": int(o["metatileCol"])}
            for o in iter_turrets(self)
        ]
        others = [o for o in self.objects
                  if not (isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET)]
        return turrets + others


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

    return errors


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
            f"At most {MAX_TURRETS} turrets are supported (private glyph namespace 226..239); "
            f"got {turret_count}."
        )
    if len(turret_rows) != len(set(turret_rows)):
        errors.append("Each turret must occupy a distinct metatile row (distinct world character row).")


def export_readiness_errors(project):
    """Extra checks required before generating engine-facing ASM (but not for a
    plain in-progress editor document). The engine's turret loop / glyph
    namespace need exactly 1..MAX_TURRETS turrets."""
    errors = validate_project(project)
    turrets = [o for o in project.objects
               if isinstance(o, dict) and o.get("type") == OBJECT_TYPE_TURRET]
    if not 1 <= len(turrets) <= MAX_TURRETS:
        errors.append(
            f"The current engine requires 1..{MAX_TURRETS} placed turrets before export; "
            f"got {len(turrets)}."
        )
    return errors


def _require_key(data, key):
    if key not in data:
        raise ProjectValidationError(f"Missing required project field: {key}")
    return data[key]


def project_from_dict(data):
    if not isinstance(data, dict):
        raise ProjectValidationError("Project JSON root must be an object.")

    format_version = _require_key(data, "formatVersion")
    if format_version not in (LEGACY_FORMAT_VERSION, FORMAT_VERSION):
        raise ProjectValidationError(
            f"Unsupported formatVersion {format_version!r}; expected {LEGACY_FORMAT_VERSION} or {FORMAT_VERSION}."
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

    # V1 migration: add the now-level-owned palette and scroll speed using the
    # current design defaults. Saving writes V2 deterministically.
    if format_version == LEGACY_FORMAT_VERSION:
        palette = dict(DEFAULT_PALETTE)
        scroll_divider = DEFAULT_SCROLL_FRAME_DIVIDER
    else:
        palette = dict(_require_key(data, "palette")) if isinstance(data.get("palette"), dict) else data.get("palette")
        scroll_divider = _require_key(data, "scrollFrameDivider")

    # objects / metatileMetadata are optional for backward compatibility with
    # early V1/V2 files that omitted them or left objects empty.
    raw_objects = data.get("objects", [])
    if not isinstance(raw_objects, list):
        raise ProjectValidationError("objects must be a list.")

    project = LevelProject(
        name=_require_key(data, "name"),
        metatile_rows=[row[:] if isinstance(row, list) else row for row in rows],
        palette=palette,
        scroll_frame_divider=scroll_divider,
        objects=[dict(o) if isinstance(o, dict) else o for o in raw_objects],
        metatile_metadata=data.get("metatileMetadata", {}),
    )
    errors = validate_project(project)
    if errors:
        raise ProjectValidationError("\n".join(errors))
    return project


def load_project(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectValidationError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return project_from_dict(data)


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
