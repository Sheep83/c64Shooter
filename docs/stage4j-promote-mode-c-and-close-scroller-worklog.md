# Stage 4J — Promote Mode C to default and close the Stage 4 scroller — worklog

Branch `experimental-border-hud`. HEAD at start `e012f19` ("Document dense
per-flip investigation"), one commit past the accepted checkpoint `479bb32`,
containing only the Stage 4I report+worklog (no source changes). Tree clean.
Tag `stable-double-buffered-scroller-v2` verified: annotated tag object
`2982010101cf...`, resolves via `^{commit}` to `479bb32afa6e066c0a59851a748c3cdfdeed9cdb`
exactly. No commit/stage/tag/push performed.

## Change
`src/main.asm`'s Stage-4 toggle block: flipped the four `#define`s
(`OPT_SECOND_SCREEN`, `OPT_SS_INACTIVE_BUILD`, `OPT_SS_FLIP_COARSE`,
`OPT_SS_ALLOW_PENDING_LIVE_FLIP`) from commented to active, and rewrote the
surrounding comments to describe Mode C as the normal architecture and
Modes A/B as regression/reference fallbacks (with their hashes). No other
line touched — confirmed via `git diff`, a pure comment+`#define` change.
Builder-scheduling constants (`SS_PLF_BUILD_SLICE_ROWS=1`,
`SS_PLF_SLICE_RASTER_CUTOFF=180`, `SS_PLF_FLIP_HOLDOFF_FRAMES=3`) were
already at the Stage 4G/4H/4I values and were not touched.

## Hash verification
Ordinary build (no manual toggle editing): `80d5b0461c070fe2...` — **exact
match** to the accepted Mode-C baseline. Manually re-commenting
`OPT_SECOND_SCREEN` alone reproduces Mode A (`f2abc225159e81bf...`);
re-commenting `OPT_SS_ALLOW_PENDING_LIVE_FLIP` alone reproduces Mode B
(`e0c3141a7ee88f8f...`) — both fallback paths confirmed still reachable and
byte-identical to their established hashes.

## Regression (ordinary default build, `run_capture.sh`, no edits during
testing)
idle 300f, wave 320f (seed 382), wrap 340f (seed 12), y199 400f, dense 200f,
turret-playtest 500f, stress 500f — all `[19656]`, all `RASTER_INCOMPLETE_
FRAMES == 0`. service_failure_count 0 everywhere except wrap (2, both
confirmed flip-transition frames with the known HUD-slot-placeholder
signature 188-191, self-correcting, non-service). dense: 16 sprite-start
misses, all `mask` kind, all at `SCROLL_FINE==4` — exact match to the
Stage 4I-accepted signature, not a new issue. Page-aware oracle active
throughout. No regression versus Stage 4G/4H/4I numbers beyond normal
CIA-jitter frame-offset variance already documented in those reports.

## Documentation
- `AGENTS.md`'s "Current scrolling architecture" section rewritten: was
  describing the old single-screen engine as "the production scrolling
  engine" (stale). Now describes the double-buffered architecture as
  current, lists Modes A/B as reachable fallbacks, and names all three
  checkpoint tags.
- `reports/stage4-second-screen-scroller-architecture.md`: added a closure
  banner immediately after the title, before the original body (left
  untouched for historical accuracy), summarising Stages 4D-4J and pointing
  to `AGENTS.md` for the maintained current-state summary.
- No other doc changed (README.md is a one-line placeholder;
  docs/hud-architecture.md has no scroller-default dependency).

## Verdict: GREEN
Ordinary build now produces the accepted Mode-C binary exactly; full
regression suite passes with no new correctness/timing issue; Modes A/B
remain available and verified; docs updated. No behavioural change beyond
the toggle promotion. **Stage 4 double-buffered scrolling is CLOSED.** No
Stage 4K recommended.
