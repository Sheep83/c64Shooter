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
            "objects": list(self.objects),
            "metatileMetadata": dict(self.metatile_metadata),
        }


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
    if not isinstance(project.metatile_metadata, dict):
        errors.append("metatileMetadata must be an object/dictionary.")

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

    project = LevelProject(
        name=_require_key(data, "name"),
        metatile_rows=[row[:] if isinstance(row, list) else row for row in rows],
        palette=palette,
        scroll_frame_divider=scroll_divider,
        objects=_require_key(data, "objects"),
        metatile_metadata=_require_key(data, "metatileMetadata"),
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
