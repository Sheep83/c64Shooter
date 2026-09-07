"""Read current 19656 terrain glyph, metatile, palette, and stage data from assembly."""
from dataclasses import dataclass
from pathlib import Path
import re

METATILE_NAMES = (
    "PLATE", "R_FILL", "R_T", "R_B", "R_L", "R_R", "R_TL", "R_TR",
    "R_BL", "R_BR", "CHAN_V", "CHAN_H", "RECESS", "GRILLE", "MACH", "STEP",
)

METATILE_W = 4
METATILE_H = 4
METATILES_PER_ROW = 10
METATILE_DEF_COUNT = 16
TERRAIN_GLYPH_BASE = 160
TERRAIN_GLYPH_NAMESPACE = 64
ENGINE_MAX_STAGE_ROWS = 844

# Project defaults are design choices, not immutable engine truths.
DEFAULT_PALETTE = {
    "background": 0,
    "multicolour1": 12,
    "multicolour2": 15,
    "character": 1,
}
DEFAULT_SCROLL_FRAME_DIVIDER = 2


# Generated build inputs owned by the level editor (see tools/level_editor/
# ka_export.py). After the engine integration these are the single source of
# truth for stage height / terrain palette / scroll speed and the stage map;
# main.asm no longer defines them.
GENERATED_CONFIG_REL = "src/generated/stage_config.asm"
GENERATED_STAGE_REL = "src/generated/stage_test.asm"


@dataclass
class EngineData:
    glyphs: dict[int, list[int]]
    metatiles: list[list[int]]
    stage_rows: list[list[int]]
    glyph_count: int
    source_stage_rows: int
    source_palette: dict[str, int]
    source_scroll_frame_divider: int
    source_colour_ram: int


def _strip_comment(line):
    return line.split("//", 1)[0].strip()


def _parse_byte_values(line):
    line = _strip_comment(line)
    if ".byte" not in line:
        return []
    payload = line.split(".byte", 1)[1]
    values = []
    for token in payload.split(","):
        token = token.strip()
        if not token:
            continue
        base = 16 if token.startswith("$") else 10
        values.append(int(token[1:] if base == 16 else token, base))
    return values


def _read_table(path, start_label, end_label):
    values = []
    inside = False
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped == f"{start_label}:":
            inside = True
            continue
        if inside and stripped == f"{end_label}:":
            break
        if inside:
            values.extend(_parse_byte_values(raw_line))
    if not inside:
        raise ValueError(f"Could not find {start_label}: in {path}")
    return values


def _parse_const_int(text, name):
    pattern = rf"^\s*\.const\s+{re.escape(name)}\s*=\s*([^/\r\n]+)"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find .const {name}")
    expression = match.group(1).strip()
    if expression.startswith("$"):
        return int(expression[1:], 16)
    if re.fullmatch(r"\d+", expression):
        return int(expression)
    # Handle the current colour-RAM form: 8 | 1.
    parts = [part.strip() for part in expression.split("|")]
    if len(parts) > 1 and all(re.fullmatch(r"\d+", part) for part in parts):
        value = 0
        for part in parts:
            value |= int(part)
        return value
    raise ValueError(f"Unsupported numeric expression for {name}: {expression}")


def _parse_generated_config(path):
    """Parse the constants-only generated stage_config.asm.

    Ownership after the engine integration: stage height, terrain palette and
    scroll speed live here, NOT in main.asm. TERRAIN_COLOUR_RAM must derive from
    TERRAIN_CHARACTER_COLOUR (the fourth palette value is a named constant, not a
    hidden literal); this validates that.
    """
    text = Path(path).read_text(encoding="utf-8")
    rows = _parse_const_int(text, "STAGE_METATILE_ROWS")
    divider = _parse_const_int(text, "SCROLL_FRAME_DIVIDER")
    background = _parse_const_int(text, "TERRAIN_BACKGROUND_COLOUR")
    mc1 = _parse_const_int(text, "TERRAIN_MC_COLOUR_1")
    mc2 = _parse_const_int(text, "TERRAIN_MC_COLOUR_2")
    character = _parse_const_int(text, "TERRAIN_CHARACTER_COLOUR")

    cram_match = re.search(
        r"^\s*\.const\s+TERRAIN_COLOUR_RAM\s*=\s*([^/\r\n]+)", text, flags=re.MULTILINE
    )
    if not cram_match:
        raise ValueError(f"{path}: missing .const TERRAIN_COLOUR_RAM")
    cram_expr = cram_match.group(1).strip()
    expected_expr = "8 | TERRAIN_CHARACTER_COLOUR"
    if cram_expr != expected_expr:
        # Also accept the fully-resolved literal form, but require it to agree.
        try:
            cram_value = _parse_const_int(text, "TERRAIN_COLOUR_RAM")
        except ValueError:
            cram_value = None
        if cram_value != (8 | character):
            raise ValueError(
                f"{path}: TERRAIN_COLOUR_RAM must be '{expected_expr}' "
                f"(8 | TERRAIN_CHARACTER_COLOUR); got '{cram_expr}'"
            )
    colour_ram = 8 | character

    if not 0 <= character <= 7:
        raise ValueError(f"{path}: TERRAIN_CHARACTER_COLOUR must be 0..7; got {character}")
    for name, value in (("TERRAIN_BACKGROUND_COLOUR", background),
                        ("TERRAIN_MC_COLOUR_1", mc1),
                        ("TERRAIN_MC_COLOUR_2", mc2)):
        if not 0 <= value <= 15:
            raise ValueError(f"{path}: {name} must be 0..15; got {value}")

    palette = {
        "background": background,
        "multicolour1": mc1,
        "multicolour2": mc2,
        "character": character,
    }
    return rows, divider, palette, colour_ram


def load_engine_data(repo_root):
    repo_root = Path(repo_root)
    main_asm = repo_root / "src" / "main.asm"
    config_asm = repo_root / GENERATED_CONFIG_REL
    stage_asm = repo_root / GENERATED_STAGE_REL
    main_text = main_asm.read_text(encoding="utf-8")

    # Glyph bitmap data + geometry stay hand-authored / engine-owned for now.
    glyph_count = _parse_const_int(main_text, "TERRAIN_GLYPH_COUNT")

    # Stage height / terrain palette / scroll speed are owned by the generated
    # level config. There is deliberately no fallback to stale main.asm values.
    if not config_asm.exists():
        raise ValueError(
            f"Generated level config not found: {config_asm}. "
            f"Export a project with tools/level_editor first."
        )
    (source_stage_rows, source_scroll_divider,
     source_palette, source_colour_ram) = _parse_generated_config(config_asm)

    if not 1 <= glyph_count <= TERRAIN_GLYPH_NAMESPACE or glyph_count % 8:
        raise ValueError(
            f"TERRAIN_GLYPH_COUNT must be 1..{TERRAIN_GLYPH_NAMESPACE} and a multiple of 8; got {glyph_count}"
        )

    glyph_bytes = _read_table(main_asm, "terrainGlyphs", "terrainGlyphsEnd")
    expected_glyph_bytes = glyph_count * 8
    if len(glyph_bytes) != expected_glyph_bytes:
        raise ValueError(f"Expected {expected_glyph_bytes} terrain glyph bytes, got {len(glyph_bytes)}")
    glyphs = {
        TERRAIN_GLYPH_BASE + i: glyph_bytes[i * 8:(i + 1) * 8]
        for i in range(glyph_count)
    }

    metatile_bytes = _read_table(stage_asm, "metatileDefs", "METATILE_DEFS_END")
    expected_metatile_bytes = METATILE_DEF_COUNT * METATILE_W * METATILE_H
    if len(metatile_bytes) != expected_metatile_bytes:
        raise ValueError(f"Expected {expected_metatile_bytes} metatile bytes, got {len(metatile_bytes)}")
    metatiles = [
        metatile_bytes[i * 16:(i + 1) * 16]
        for i in range(METATILE_DEF_COUNT)
    ]
    valid_codes = set(glyphs)
    invalid_codes = sorted({code for code in metatile_bytes if code not in valid_codes})
    if invalid_codes:
        raise ValueError(f"Metatile definitions reference unavailable terrain glyphs: {invalid_codes}")

    stage_bytes = _read_table(stage_asm, "stageMetatileRows", "STAGE_METATILE_ROWS_END")
    if len(stage_bytes) % METATILES_PER_ROW:
        raise ValueError(
            f"Stage table contains {len(stage_bytes)} bytes, not a whole number of {METATILES_PER_ROW}-byte rows"
        )
    parsed_stage_rows = len(stage_bytes) // METATILES_PER_ROW
    if parsed_stage_rows != source_stage_rows:
        raise ValueError(
            f"STAGE_METATILE_ROWS says {source_stage_rows}, but stage table contains {parsed_stage_rows} rows"
        )
    if any(tile_id >= METATILE_DEF_COUNT for tile_id in stage_bytes):
        raise ValueError(f"Stage contains a metatile ID outside 0..{METATILE_DEF_COUNT - 1}")
    stage_rows = [
        stage_bytes[i * METATILES_PER_ROW:(i + 1) * METATILES_PER_ROW]
        for i in range(parsed_stage_rows)
    ]

    return EngineData(
        glyphs=glyphs,
        metatiles=metatiles,
        stage_rows=stage_rows,
        glyph_count=glyph_count,
        source_stage_rows=source_stage_rows,
        source_palette=source_palette,
        source_scroll_frame_divider=source_scroll_divider,
        source_colour_ram=source_colour_ram,
    )
