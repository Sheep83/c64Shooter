#!/usr/bin/env python3
"""Verify stage scrolling / wrap from a vice_scroll_test capture.

Reads SCROLL_ROW / SCROLL_ROW_HI out of the per-frame $2000-$23FF state dumps.
Reports the row range covered, how many coarse steps ran, how many stage
end->start wraps were exercised, and whether every step is the expected single
decrement (modulo STAGE_LOGICAL_ROWS).

This exists because tools/check_scroll_capture.py still assumes the PRE-Stage-4A
memory map: it reads BG_COARSE_* out of a $2920 dump, but OPT_SS_RELOCATE moved
that block to $9000+, so it raises IndexError on any current capture (baseline
and modified builds alike).
"""
import argparse, json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture', type=Path)
    ap.add_argument('--logical-rows', type=int, default=None,
                    help='STAGE_LOGICAL_ROWS; inferred from the observed max when omitted')
    a = ap.parse_args()
    root = a.capture
    sym = json.loads((root / 'symbols.json').read_text())
    records = json.loads((root / 'frames.json').read_text())
    lo, hi = sym['SCROLL_ROW'] - 0x2000, sym['SCROLL_ROW_HI'] - 0x2000
    rows = []
    for r in records:
        st = (root / f"{r['frame']:05d}.state").read_bytes()
        rows.append(st[lo] | (st[hi] << 8))
    slr = a.logical_rows or (max(rows) + 1)
    steps = [(rows[i - 1] - rows[i]) % slr for i in range(1, len(rows))]
    coarse = [s for s in steps if s]
    wraps = sum(1 for i in range(1, len(rows)) if rows[i] > rows[i - 1])
    bad = [(i, rows[i - 1], rows[i]) for i in range(1, len(rows)) if steps[i - 1] > 1]
    print(json.dumps(dict(
        frames=len(rows), stage_logical_rows_assumed=slr,
        scroll_row_first=rows[0], scroll_row_last=rows[-1],
        scroll_row_min=min(rows), scroll_row_max=max(rows),
        coarse_steps=len(coarse), wraps=wraps,
        all_steps_single_decrement=not bad,
        bad_steps=bad[:10]), indent=2))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
