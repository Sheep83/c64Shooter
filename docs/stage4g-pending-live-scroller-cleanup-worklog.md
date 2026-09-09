# Stage 4G — Finish pending-LIVE double-buffered scroller — worklog

Branch `experimental-border-hud`. HEAD `cd24b8c` (Stage 4F, on tag
`stable-double-buffered-scroller` = Stage 4D+4E `931dca1`). Clean tree at
start. No commit/push/tag. Working tree left at Mode A (all toggles
commented); `build/shooter.prg` left at Mode A.

## Objective A — page-aware oracle
- `vice_scroll_test.py`: added `.actpage` (1-byte `bsave` of `BG_ACTIVE_PAGE`),
  gated on the symbol existing. Page B's `$2BF8` table was already inside the
  existing `.bg` dump (`2920-2fff`).
- `check_raster_capture.py`: `page_aware` flag; "final sprite pointers" now
  reads whichever table (`$07F8` in `.ram`, or `$2BF8` in `.bg`) matches the
  captured `BG_ACTIVE_PAGE` for that frame; falls back to the old page-A-only
  behaviour when the symbol/files are absent. Failure records now include
  `table_name` + actual/expected bytes.
- Verified: Mode C 199/235 (400f) `service_failure_count: 0` (was 198),
  matching Stage 4F's live 200/200 probe. Mode A 200f idle:
  `page_aware: false`, 0 failures (fallback intact, no regression).

### Finding 1 (Mode B, real defect, not fixed — see report)
Running the new oracle against Mode B (4D+4E only) on idle/wave showed
144/300 and 159/320 failures — *every* page-B-active frame. Root-caused live
(VICE monitor: `disass`, `m`) to `ssFlipMirrorPtrs`'s `#else` branch:
`sta (SS_FLIP_TMP_LO),y` where `SS_FLIP_TMP_LO/HI` are NOT zero page
($9B6A/$9B6B) — KickAssembler assembles `91 6A` (`STA ($6A),Y`), which
indirects through **zero-page $6A/$6B** (unrelated memory; probed as $80C0)
instead of the intended $9B6A/$9B6B. Confirmed live: `$2BF8-$2BFF` never
changes from its boot-time init pattern `00 00 FF FF FF FF 00 00` regardless
of gameplay. This is a real sprite-pointer-corruption bug in the *already
tagged* `stable-double-buffered-scroller` checkpoint, invisible to every
prior proof because none of them ever inspected `$2BF8` under Mode B. Not
fixed — out of Stage 4G scope (Mode B must stay bit-identical); fully written
up in the report with a recommended follow-up.

### Finding 2 (Mode C, bounded oracle/HUD-modeling gap)
2/340 stage-wrap failures, both the exact first frame of a flip, both
confined to HUD-owned slots (4-6). Not a raster-service defect
(`sprite_start_miss 0`, assignment-service passes, `[19656]` held). Oracle
models `INITIAL_SPRITE + ASSIGN_SPRITE` only, not HUD's separate pointer
writes — HUD architecture is out of scope, so documented as a caveat rather
than chased.

## Objective B — bound builder load
Added three `#if OPT_SS_ALLOW_PENDING_LIVE_FLIP`-gated tunables (Mode C
exclusive, Mode A/B keep the Stage 4D/4E base values, reconfirmed
byte-identical after every edit): `SS_PLF_BUILD_SLICE_ROWS`,
`SS_PLF_SLICE_RASTER_CUTOFF`, `SS_PLF_FLIP_HOLDOFF_FRAMES`, applied at
`ssInactiveBuildReset`'s slice-row init, `ssInactiveBuildSlice`'s raster
compare, and `ssPublishCoarseFlip`'s holdoff store.

Swept 5 trials (rows/cutoff/holdoff): conservative (1/200/2) moved nothing;
aggressive (1/140/4) improved `--dense` misses 17→15 but **broke 199/235
advancement entirely** (`page_b_frames` 184→0 — permanently pinned again,
same symptom Stage 4F fixed); extreme (1/100/8) made `--dense` worse (18).
`--dense`'s `replay_frames`/`catchups` (99/1393) never moved across any
trial — strong evidence the builder isn't `--dense`'s dominant cost. Found
the safe edge: 1/180/3 preserves 199/235 (`page_b_frames` 188/400, replay 0)
with a small `--dense` improvement (17→16); 1/160/3 (only 20 less on the
cutoff) already reproduces the stall. Kept 1/180/3.

Target check: 199/235 replay ≤ stage-wrap baseline — **met** (0/400 vs 4/340
baseline). `--dense` sprite-start-miss ≤ 3 — **not met** (16). Stopped here
per the task's explicit instruction rather than pursue architectural changes
to the per-flip mechanism.

## Final verification
Mode A `f2abc225159e81bf…`, Mode B `98eb5bbbc2fb385e…` — both bit-identical,
reconfirmed after every edit including the final kept state. Mode C
`80d5b0461c070fe2…` (changed from `d3ba25a9…`, expected). Full regression
suite (idle/wave/wrap/199-235/dense/turret-playtest/stress) run on the final
build: exact `[19656]` cadence and passing assignment-service checks in
every capture; only the disclosed Finding-2 signature remains (1/340 on
wrap, down from 2/340 pre-tuning).

## Verdict: AMBER
Objective A's mechanism works and is proven against the decisive fixture and
the Mode A fallback; it also found a real bug (Finding 1) outside this
stage's authority to fix. Objective B met one of its two targets and made a
genuine (if small) improvement on the other while proving — by triggering
and reverting a real regression — that the remaining gap is not reachable
through builder-scheduling changes alone. No commit/push/tag. Source and
`build/` left at Mode A.
