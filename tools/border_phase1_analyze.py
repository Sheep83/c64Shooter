#!/usr/bin/env python3
"""Analyse the Phase-1 border-proof screenshots (VICE 'screenshot ... 2', 384x272,
screenshot_y ~= raster - 16). Reports, per PNG:

  * the lowest raster with any non-border, non-$D021 content  (border-open depth)
  * the raster span of the diagnostic marker (solid white block near X=160)
  * whether the terrain region (raster 71..239) differs between two shots
  * the colour of the row-24 / seam band (raster ~240..250)

Run:  python3 tools/border_phase1_analyze.py build/border-phase1
"""
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

VICE16 = {  # x64sc -default PAL
    (0, 0, 0): "black", (255, 255, 255): "white", (104, 55, 43): "red",
    (112, 164, 178): "cyan", (111, 61, 134): "purple", (88, 141, 67): "green",
    (53, 40, 121): "blue", (184, 199, 111): "yellow", (111, 79, 37): "orange",
    (67, 57, 0): "brown", (154, 103, 89): "ltred", (68, 68, 68): "dkgrey",
    (108, 108, 108): "mdgrey", (154, 210, 132): "ltgreen",
    (108, 94, 181): "ltblue", (149, 149, 149): "ltgrey",
}


def nearest(rgb):
    return min(VICE16.items(), key=lambda kv: sum((a - b) ** 2 for a, b in zip(kv[0], rgb)))[1]


def row_dom(px, w, y):
    c = Counter(px[x, y] for x in range(0, w, 2))
    (rgb, n), = c.most_common(1)
    return nearest(rgb), n / (w // 2)


def white_run(px, w, y):
    """(x0, x1) of the longest near-white horizontal run on row y, else None."""
    best = cur = None
    for x in range(w):
        r, g, b = px[x, y][:3]
        if r > 200 and g > 200 and b > 200:
            cur = (cur[0], x) if cur else (x, x)
            if not best or (cur[1] - cur[0]) > (best[1] - best[0]):
                best = cur
        else:
            cur = None
    return best if best and best[1] - best[0] >= 8 else None


def analyse(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    marker_rows = []
    open_depth = None
    seam = []
    for y in range(h):
        raster = y + 16
        name, frac = row_dom(px, w, y)
        wr = white_run(px, w, y)
        if 240 <= raster <= 251:
            seam.append((raster, name, round(frac, 2)))
        if raster >= 247 and name != "black":
            open_depth = raster if open_depth is None else open_depth
        if raster >= 247 and wr:
            marker_rows.append((raster, wr))
    span = None
    if marker_rows:
        rs = [r for r, _ in marker_rows]
        xs0 = min(a for _, (a, b) in marker_rows)
        xs1 = max(b for _, (a, b) in marker_rows)
        span = dict(raster_first=rs[0], raster_last=rs[-1], n_rows=len(rs),
                    x_px=(xs0, xs1))
    last_content = None
    for y in range(h - 1, -1, -1):
        name, frac = row_dom(px, w, y)
        if name != "black":
            last_content = y + 16
            break
    return dict(name=path.name, size=(w, h),
                first_open_raster=open_depth, last_content_raster=last_content,
                marker=span, seam_240_251=seam)


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "build/border-phase1")
    for p in sorted(root.glob("*.png")):
        r = analyse(p)
        print(f"\n{r['name']}  {r['size']}")
        print(f"  first non-black raster >=247 : {r['first_open_raster']}")
        print(f"  last non-black raster (content depth): {r['last_content_raster']}")
        print(f"  marker white block          : {r['marker']}")
        print(f"  seam band raster 240..251   : "
              + " ".join(f"{rr}:{nm}" for rr, nm, _ in r['seam_240_251']))


if __name__ == "__main__":
    main()
