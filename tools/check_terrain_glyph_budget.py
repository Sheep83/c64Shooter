#!/usr/bin/env python3
"""Regression for the terrain-glyph memory-layout / capacity guards.

A level that uses the FULL supported terrain-glyph budget
(TERRAIN_GLYPH_COUNT == TERRAIN_GLYPH_NAMESPACE == 128, a 1024-byte terrainGlyphs
block) must assemble without pushing timing/control code into reserved sprite
RAM. The block lives in its own fixed $5a00 segment (not the $2920
background-control code segment) and the initBackground copy is a fixed-size
runtime loop, so no generated glyph-data size can relocate timing code.

Backs up src/generated/level1/{stage_charset,stage_config}.asm, substitutes a
deterministic 128-glyph charset, assembles and asserts:
  * the build succeeds;
  * terrainGlyphs sits at $5a00 (its own segment);
  * every reserved-region guard holds with room to spare -
      BACKGROUND_CONTROL_END  <  HEALTH_SPRITE_BASE  ($3000)
      TERRAIN_CHARSET_END      <= $6000              (raster scheduler)
      BACKGROUND_CODE_END      <  $5a00              (terrain glyph block)
  * $5a00 + 128*8 == $5e00 <= $6000 (the reserved window fits a full block);
  * the committed Level 1 still builds.
Then restores the originals. Never commits.

    python3 tools/check_terrain_glyph_budget.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KA = Path("/Users/brianmorrice/dev/tools/kickassembler/KickAss.jar")
GEN = ROOT / "src" / "generated" / "level1"
CS = GEN / "stage_charset.asm"
CFG = GEN / "stage_config.asm"
SEGMENT = 0x5A00
NAMESPACE = 128


def assemble(tag):
    r = subprocess.run(
        ["java", "-jar", str(KA), "main.asm", "-odir", "../build",
         "-o", f"../build/{tag}.prg", "-vicesymbols"],
        cwd=ROOT / "src", capture_output=True, text=True)
    return r.stdout + r.stderr


def sym(name):
    text = (ROOT / "build" / "main.vs").read_text()
    m = re.search(rf"^al C:([0-9a-fA-F]+) \.{re.escape(name)}$", text, re.M)
    if not m:
        raise AssertionError(f"symbol {name} not found in build/main.vs")
    return int(m.group(1), 16)


def make_full_charset(cfg_bak):
    """Deterministic NAMESPACE-glyph stage_charset.asm from the committed set + pad."""
    lines = CS.read_text().splitlines()
    idx = [i for i, l in enumerate(lines)
           if l.strip().startswith(".byte") and "// code" in l]
    have = len(idx)
    last = idx[-1]
    base = int(re.search(r"// code (\d+)", lines[last]).group(1)) + 1
    pad = [f"    .byte 170, 85,170, 85,170, 85,170, 85   // code {base + i}"
           for i in range(NAMESPACE - have)]
    lines[last + 1:last + 1] = pad
    return "\n".join(lines) + "\n"


def main():
    fails = []
    cs_bak, cfg_bak = CS.read_text(), CFG.read_text()
    try:
        out_c = assemble("shooter")
        if "Writing prg file" not in out_c:
            fails.append("committed Level 1 no longer assembles:\n" + out_c[-800:])

        CS.write_text(make_full_charset(cfg_bak))
        CFG.write_text(re.sub(r"(TERRAIN_GLYPH_COUNT\s*=\s*)\d+", rf"\g<1>{NAMESPACE}", cfg_bak))
        out_f = assemble("shooter-glyphmax")
        if "Writing prg file" not in out_f:
            fails.append(f"{NAMESPACE}-glyph (full budget) level FAILS to assemble:\n" + out_f[-1000:])
        else:
            g = {n: sym(n) for n in (
                "terrainGlyphs", "terrainGlyphsEnd", "TERRAIN_CHARSET_END",
                "BACKGROUND_CONTROL_END", "BACKGROUND_CODE_END")}
            HEALTH_SPRITE_BASE = 0x3000
            block = g["terrainGlyphsEnd"] - g["terrainGlyphs"]
            for good, msg in [
                (g["terrainGlyphs"] == SEGMENT,
                 f"terrainGlyphs at ${g['terrainGlyphs']:04x}, want ${SEGMENT:04x} (own segment)"),
                (block == NAMESPACE * 8, f"{NAMESPACE}-glyph block is {block} bytes, want {NAMESPACE*8}"),
                (g["BACKGROUND_CONTROL_END"] < HEALTH_SPRITE_BASE,
                 f"BACKGROUND_CONTROL_END ${g['BACKGROUND_CONTROL_END']:04x} >= HEALTH_SPRITE_BASE $3000"),
                (g["TERRAIN_CHARSET_END"] <= 0x6000,
                 f"TERRAIN_CHARSET_END ${g['TERRAIN_CHARSET_END']:04x} > $6000 (raster scheduler)"),
                (g["BACKGROUND_CODE_END"] < SEGMENT,
                 f"BACKGROUND_CODE_END ${g['BACKGROUND_CODE_END']:04x} >= ${SEGMENT:04x} (terrain glyph block)"),
                (SEGMENT + NAMESPACE * 8 <= 0x6000,
                 f"reserved window ${SEGMENT:04x}+{NAMESPACE*8} overruns $6000"),
            ]:
                if not good:
                    fails.append(msg)
            print(f"{NAMESPACE}-glyph build: terrainGlyphs ${g['terrainGlyphs']:04x}..${g['terrainGlyphsEnd']:04x} "
                  f"({block}B) | BACKGROUND_CONTROL_END ${g['BACKGROUND_CONTROL_END']:04x} "
                  f"(headroom {HEALTH_SPRITE_BASE - g['BACKGROUND_CONTROL_END']}B to $3000) | "
                  f"TERRAIN_CHARSET_END ${g['TERRAIN_CHARSET_END']:04x} "
                  f"(headroom {0x6000 - g['TERRAIN_CHARSET_END']}B to $6000) | "
                  f"BACKGROUND_CODE_END ${g['BACKGROUND_CODE_END']:04x} "
                  f"(headroom {SEGMENT - g['BACKGROUND_CODE_END']}B to ${SEGMENT:04x})")
    finally:
        CS.write_text(cs_bak)
        CFG.write_text(cfg_bak)
        assemble("shooter")

    if fails:
        print(f"\nFAIL ({len(fails)}):")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print(f"\nPASS: full {NAMESPACE}-glyph terrain budget assembles; all reserved-region "
          f"guards hold; committed Level 1 unaffected.")


if __name__ == "__main__":
    main()
