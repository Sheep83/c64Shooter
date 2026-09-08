#!/usr/bin/env python3
"""Phase 1.5 temporal scroll-edge oracle for the RSEL=1 gameplay geometry.

Sibling of check_scroll_edges.py (which hard-codes the retired RSEL=0 aperture
55..246 and skips the old fixed-HUD band). This one:

  * uses the RSEL=1 aperture 51..250 (lower border opened below);
  * expects matrix row 0 (top) and matrix row 24 (bottom) to be blank $D021
    spacer rows that scroll with the field;
  * runs the model-free temporal test: on a 1 px scroll every observed pixel
    must equal the pixel one line above it in the previous frame, except the
    single genuinely-new entering line and sprite-covered samples;
  * classifies mismatches by raster band so the *lowest terrain row* can be
    judged on its own, and reports the per-coarse-step edge jump magnitude.

Consumes a `tools/vice_scroll_test.py --physical` capture directory.
Usage:  python3 tools/check_scroll_edges_rsel1.py build/<capture>
Exit 0 iff the terrain body (rows above the last one) is temporally clean.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_scroll_edges import sprite_mask  # reuse the LIVE-plan sprite rectangle mask

APERTURE_TOP, APERTURE_BOTTOM = 51, 250          # RSEL=1, border opened below 250
GREY_D021 = None                                 # filled from the first frame's own backdrop


def dominant_backdrop(im):
    from collections import Counter
    y = 120 - 16
    c = Counter(im.getpixel((x, y)) for x in range(300, 340))
    return c.most_common(1)[0][0]


def near(a, b, tol=10):
    return all(abs(p - q) <= tol for p, q in zip(a, b))


def terrain_edge(im, backdrop, columns, lo=200, hi=262):
    """Lowest raster in [lo,hi] whose pixel is neither backdrop ($D021) nor
    near-black (open border / idle). Averaged intent: the terrain/spacer boundary."""
    edges = []
    for cx in columns:
        low = None
        for raster in range(lo, hi):
            px = im.getpixel((cx, raster - 16))
            if not near(px, backdrop, 26) and not near(px, (0, 0, 0), 30):
                low = raster
        edges.append(low)
    return edges


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture", type=Path)
    ap.add_argument("--body-top", type=int, default=60,
                    help="first raster of the 'terrain body' band judged for cleanliness")
    ap.add_argument("--last-row-top", type=int, default=232,
                    help="first raster of the 'last terrain row' band reported separately")
    args = ap.parse_args()
    root = args.capture
    records = json.loads((root / "frames.json").read_text())
    sym = json.loads((root / "symbols.json").read_text())

    cols = list(range(40, 344, 8))
    stats = defaultdict(lambda: dict(pairs=0, checks=0, diffs=0, rows=defaultdict(int)))
    body_failures = []
    coarse_steps = []
    prev = None
    for rec in records:
        n = rec["frame"]
        phase = rec["physical_fine"]
        im = Image.open(root / f"{n:05d}.png").convert("RGB")
        if im.size != (384, 272):
            raise SystemExit("expected 384x272 PAL crop")
        backdrop = dominant_backdrop(im)
        mask = sprite_mask(root, sym, n, im.size)
        edges = terrain_edge(im, backdrop, cols)
        if prev is not None:
            oim, omask, ophase, oframe, oedges, obackdrop = prev
            if phase == ophase:
                dy = 0
            elif phase == (ophase + 1) % 8:
                dy = 1
            else:
                prev = (im, mask, phase, n, edges, backdrop)
                continue
            coarse = ophase == 7 and phase == 0
            key = f"{ophase}->{phase}"
            pix, opix = im.load(), oim.load()
            m, om = mask.load(), omask.load()
            for band, first, last in (("body", args.body_top, args.last_row_top - 1),
                                      ("lastrow", args.last_row_top, APERTURE_BOTTOM)):
                st = stats[f"{key}:{band}"]
                st["pairs"] += 1
                for raster in range(first, last + 1):
                    if not APERTURE_TOP <= raster <= APERTURE_BOTTOM:
                        continue
                    if raster - dy < APERTURE_TOP:
                        continue
                    y = raster - 16
                    for x in range(32, 352):
                        if m[x, y] or om[x, y - dy]:
                            continue
                        st["checks"] += 1
                        if pix[x, y] == opix[x, y - dy]:
                            continue
                        st["diffs"] += 1
                        st["rows"][raster] += 1
                        if band == "body" and len(body_failures) < 30:
                            body_failures.append(dict(frame_pair=[oframe, n], raster=raster,
                                                      x=x, got=list(pix[x, y]),
                                                      expected=list(opix[x, y - dy])))
            if coarse:
                jumps = [b - a for a, b in zip(oedges, edges) if a and b]
                coarse_steps.append(dict(frame_pair=[oframe, n],
                                         edge_before=oedges, edge_after=edges,
                                         median_jump=sorted(jumps)[len(jumps) // 2] if jumps else None))
        prev = (im, mask, phase, n, edges, backdrop)

    body_diff_total = sum(v["diffs"] for k, v in stats.items() if k.endswith(":body"))
    lastrow_diff_total = sum(v["diffs"] for k, v in stats.items() if k.endswith(":lastrow"))
    coarse_jumps = [s["median_jump"] for s in coarse_steps if s["median_jump"] is not None]
    result = dict(
        frames=len(records),
        phases=sorted({r["physical_fine"] for r in records}),
        aperture=[APERTURE_TOP, APERTURE_BOTTOM],
        body_band=[args.body_top, args.last_row_top - 1],
        lastrow_band=[args.last_row_top, APERTURE_BOTTOM],
        body_temporal_diffs=body_diff_total,
        lastrow_temporal_diffs=lastrow_diff_total,
        coarse_steps_seen=len(coarse_steps),
        coarse_edge_median_jump=sorted(set(coarse_jumps)),
        per_key={k: dict(pairs=v["pairs"], checks=v["checks"], diffs=v["diffs"],
                         worst_rasters=sorted(v["rows"].items(), key=lambda t: -t[1])[:6])
                 for k, v in sorted(stats.items())},
        body_failures=body_failures[:12],
        coarse_steps=coarse_steps[:8],
    )
    (root / "rsel1-edge-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("per_key", "body_failures", "coarse_steps")}, indent=2))
    print("per_key:", json.dumps(result["per_key"], indent=2))
    # verdict: terrain BODY must be temporally clean; last-row wobble is reported,
    # not fatal to this script (the report interprets it against the task).
    raise SystemExit(1 if body_diff_total else 0)


if __name__ == "__main__":
    main()
