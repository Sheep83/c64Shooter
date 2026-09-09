# Four-turret screen-RAM frame forensics — worklog

**STATUS: GREEN for scope — screen RAM EXONERATED. No production change.**
Full report: `/reports/four-turret-screen-ram-frame-forensics.md`.

Branch `main`, HEAD `d60828a`, working tree as found. Nothing committed/staged/
tagged/pushed. Build under test: existing `58e9d59131e4791b` (mask ON, default).

## Result
850 passive frames, seed 352, covering the whole `345/337/329/321` window.
Active matrix is a perfect 25-row stage window on **847/850** frames
(797 at offset −1 normal, 50 at offset 0 = pre-flip admit transient).
**The user's window (frames 367–622, three cluster turrets) has ZERO anomalies.**

The 3 incoherent frames (95, 127, 831) correlate **1:1** with the only 3 legacy
fallback executions and are the two-phase shift caught mid-update in RAM at the
raster-311 sample point. Never displayed: lowerReady 114–143 vs the row-13 fetch
at 152. Worst margin **9 rasterlines** (page B) — tightest number in the pipeline;
if ever missed, rows 13–24 would tear visibly.

## Method that finally settled it
Decoded the stage INDEPENDENTLY in Python from `metatiledefs.bin` +
`stagemetatilerows.bin`, replicating `decodeStageCharacterRow`
(metatileRow = world>>2, ofs = (world&3)*4, 10 ids/row, 4 chars/id). Then asked
"is this matrix a perfect 25-row window at ANY offset −4..+4?" rather than
asserting a mapping. The mapping fell out of the data:
- active page = offset −1 (row r ↔ SCROLL_ROW + r − 1)
- inactive page = offset 0 when just displaced (stale) → −2 once rebuilt
Searching the offset is what makes admit-frame transients self-identifying.

## Control
Turret 329 removed (diagnostic tree only): **7** tears instead of 3, all still
inside the deadline. Removing a turret produced MORE tears — they are load-driven,
not caused by 329 or by the 2→3 transition.

## Geometry note
Cluster spacing is 8 world rows, aperture is 24 rows, so **at most THREE of the
four turrets are ever on screen together**. "The fourth appears" is really the
fourth entering as the first leaves.

## Colour RAM
Previous presentation fix holding: only 4 single-frame `rel==0` dropouts in 850
frames (one per turret entry) — the known publish-ordering residual.

## Harness changes (NOT production)
`scratchpad/vst_passive.py` / `run_passive.sh`:
- per-frame VIC register dump `$D000-$D02F` (`.vic`) so `$D011`/`$D018` are recorded;
- **`--hold-fire` is now explicit opt-in**; default is genuinely passive.
Use this runner for scrolling / sprite-capacity / turret-render / passive work.
`vst_hitch.py` still holds FIRE every frame — do not use it for passive symptoms.

## Best remaining candidate (NOT investigated, no change made)
`turretPulseTable = 1, 2, 7, 2`; phase 0 is `1|8 = 9` = **identical to
`TERRAIN_COLOUR_RAM`**, and all turrets share one global `TURRET_PULSE_INDEX`.
So every turret flattens into the terrain colour for 8 frames in every 32, in
unison. By design, so no correctness oracle flags it. Cheapest experiment: change
phase 0 away from `TERRAIN_CHARACTER_COLOUR`, or lengthen `TURRET_PULSE_INTERVAL`,
and ask the user whether the symptom changes character.

## Recommendation
Stop chasing the scroller/turret matrix for this symptom. Moving one cluster
turret (spacing > 12 world rows) is a safe authored-data workaround. If root cause
is wanted, next capture should sample `$D011/$D016/$D018` per-raster INSIDE the
visible window rather than once at line 311.
