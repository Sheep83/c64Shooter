#!/usr/bin/env python3
"""Mixed hires / global-multicolour VIC-II character render model for the oracles.

The playfield runs global character multicolour mode ($D016 bit 4 set) during
PLAYING (main.asm initBackground); it is cleared again for the menu / GAME OVER
(endGame). Under global char MCM the *per cell* colour-RAM value decides the
rendering of that cell:

  colour-RAM bit 3 CLEAR  -> HIRES cell. The 8 bitmap bits are 8 physical
      pixels: 1 -> character colour (colour-RAM & 15), 0 -> $D021 background.

  colour-RAM bit 3 SET    -> MULTICOLOUR cell. The bitmap byte is four logical
      double-width pixels (bit pairs 7-6, 5-4, 3-2, 1-0):
        00 -> $D021        01 -> $D022        10 -> $D023
        11 -> low 3 bits of the colour-RAM value
      Each logical pixel occupies two physical horizontal pixels.

Terrain + turret cells carry one fixed multicolour colour-RAM value
(TERRAIN_COLOUR_RAM, main.asm) written once by initBackground and never
scrolled. Row 0 (the fixed HUD) is repainted hires by initFixedHud
(colour-RAM = 1) and stays hires even while global MCM is enabled.

Register / colour-RAM values are taken from the capture when
tools/vice_scroll_test.py dumped them (`vic.bin`, `NNNNN.colour`); otherwise
they are parsed from src/main.asm so the oracle still carries no literal
palette-register magic numbers.
"""
import re
from pathlib import Path

# VICE 3.10 x64sc `-default` internal palette, as emitted by `screenshot ... 2`
# (sampled directly from this project's captures). Only indices 0/1/12/15 are
# exercised by the terrain+HUD oracles - sprites are masked out - but the whole
# table is kept for completeness / future checks. This is a fixed property of
# the emulator render target, not a terrain assumption.
VICE_PALETTE = [
    (0, 0, 0),        # 0  black
    (255, 255, 255),  # 1  white
    (175, 60, 88),    # 2  red
    (126, 243, 214),  # 3  cyan
    (175, 96, 200),   # 4  purple      (estimated; unused by these oracles)
    (98, 213, 50),    # 5  green
    (44, 61, 236),    # 6  blue
    (255, 255, 70),   # 7  yellow
    (183, 99, 30),    # 8  orange
    (119, 83, 0),     # 9  brown       (the pre-multicolour terrain colour)
    (238, 123, 149),  # 10 light red
    (98, 98, 98),     # 11 dark grey
    (148, 148, 148),  # 12 grey
    (183, 255, 134),  # 13 light green
    (115, 133, 255),  # 14 light blue
    (205, 205, 205),  # 15 light grey
]

SOURCE_MAIN = Path(__file__).resolve().parent.parent / 'src' / 'main.asm'


def _parse_consts(path=SOURCE_MAIN):
    """Pull `.const NAME = <int expr>` values out of the assembler source."""
    values = {}
    if not Path(path).exists():
        return values
    for line in Path(path).read_text().splitlines():
        line = line.split('//', 1)[0]
        m = re.match(r'\s*\.const\s+(\w+)\s*=\s*([0-9A-Fa-fx$|&()\s+*-]+)$', line)
        if not m:
            continue
        expr = m.group(2).strip().replace('$', '0x')
        try:
            values[m.group(1)] = int(eval(expr, {'__builtins__': {}}, {}))
        except Exception:
            pass
    return values


class PaletteConfig:
    """Resolved playfield palette registers + colour-RAM model for one capture."""

    def __init__(self, palette, d021, d022, d023, mcm_on, terrain_cram, hud_cram, source):
        self.palette = palette
        self.d021 = d021 & 0x0f
        self.d022 = d022 & 0x0f
        self.d023 = d023 & 0x0f
        self.mcm_on = mcm_on
        self.terrain_cram = terrain_cram & 0x0f
        self.hud_cram = hud_cram & 0x0f
        self.source = source                       # 'capture' or 'source'

    def rgb(self, index):
        return self.palette[index & 0x0f]

    def mc_lut(self, cram):
        """[00, 01, 10, 11] -> RGB for a multicolour cell with this colour RAM."""
        return (self.palette[self.d021], self.palette[self.d022],
                self.palette[self.d023], self.palette[cram & 7])

    def scanline(self, bitmap_byte, cram):
        """8 RGB tuples for one character bitmap byte in this cell's mode."""
        if cram & 0x08:
            lut = self.mc_lut(cram)
            out = []
            for shift in (6, 4, 2, 0):
                rgb = lut[(bitmap_byte >> shift) & 3]
                out.append(rgb)
                out.append(rgb)
            return out
        fg = self.palette[cram & 0x0f]
        bg = self.palette[self.d021]
        return [fg if bitmap_byte & (1 << b) else bg for b in range(7, -1, -1)]

    def row_bytes(self, codes, gy, glyphs, cram):
        """Flat RGB bytes (len == 8*len(codes)*3) for one screen scanline.

        `cram` is one colour-RAM value for every cell, or a per-cell sequence.
        """
        if isinstance(cram, int):
            cram = [cram] * len(codes)
        out = bytearray()
        for code, cell_cram in zip(codes, cram):
            for rgb in self.scanline(glyphs[code][gy], cell_cram):
                out.extend(rgb)
        return bytes(out)


def load_palette_config(capture_root, source=SOURCE_MAIN):
    """PaletteConfig from a capture's vic.bin if present, else from source."""
    root = Path(capture_root)
    vic = root / 'vic.bin'
    if vic.exists():
        v = vic.read_bytes()                       # base $D000; index n == $D000+n
        return PaletteConfig(VICE_PALETTE, v[0x21], v[0x22], v[0x23],
                             bool(v[0x16] & 0x10),
                             _terrain_cram_from_source(source),
                             1, 'capture')
    c = _parse_consts(source)
    return PaletteConfig(
        VICE_PALETTE,
        d021=0,                                     # main.asm: lda #0 / sta BACKGROUND_COLOUR
        d022=c.get('TERRAIN_MC_COLOUR_1', 12),
        d023=c.get('TERRAIN_MC_COLOUR_2', 15),
        mcm_on=True,                               # PLAYING captures only
        terrain_cram=_terrain_cram_from_source(source),
        hud_cram=1,
        source='source')


def _terrain_cram_from_source(source=SOURCE_MAIN):
    return _parse_consts(source).get('TERRAIN_COLOUR_RAM', 8 | 1)


def load_colour_ram(capture_root, frame, cfg):
    """1000-byte visible colour-RAM image for a frame.

    Uses the per-frame `NNNNN.colour` dump ($D800..$DBFF) when present; the
    model otherwise is 'row 0 hires HUD, everything else the fixed terrain
    value' exactly as initBackground + initFixedHud leave it.
    """
    path = Path(capture_root) / f'{frame:05d}.colour'
    if path.exists():
        # Colour RAM is 4-bit; the upper nybble reads back as undefined bus noise.
        return bytes(b & 0x0f for b in path.read_bytes()[:1000])
    return bytes([cfg.hud_cram] * 40 + [cfg.terrain_cram] * 960)
