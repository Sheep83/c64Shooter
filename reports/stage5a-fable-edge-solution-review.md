# Fable Review — Seamless Scroll Edges Without Reintroducing Hitching

Branch `main`, HEAD `d60828a` (unchanged). Nothing committed, staged, tagged or
pushed. Working tree: `M src/main.asm`, `M src/raster_scheduler.asm` (the
reviewed prototype, which supersedes the Stage 5A candidate in place); the Stage
5A candidate as tested is preserved verbatim in
`reports/stage5a-candidate-as-tested.patch` (builds to `d06724c6587e2f81…`).

| build | SHA-256 (16) | what |
|---|---|---|
| `SCROLL_EDGE_MASK` off | `80d5b0461c070fe2` | accepted Stage 4J Mode C — **byte-identical**, re-verified after every edit |
| Stage 5A candidate | `d06724c6587e2f81` | invalid-mode mask, busy-wait in the DISPLAY IRQ (patch above) |
| **this review, final** | `b719de4ca86c7f54` | invalid-mode mask as a scheduler event, HUD handoff at 43, aperture 58..247 |

## Ranked recommendation

1. **Recommended — scheduler-integrated invalid-mode mask (implemented, `b719de4c…`).** Same VIC mechanism as Stage 5A, but the aperture-open transition is a first-class raster event armed 5 lines ahead, the HUD handoff compare moves 46→43, `RASTER_DISPLAY_PENDING` becomes a 2-phase state so the batch catch-up chain pays nothing, and `publishRasterPlan` no longer forces ECM. Median display-phase IRQ occupancy drops from **755 → 424 cycles/frame**; aperture grows 188 → **190** lines; every fixture passes with **0 sprite-start misses including `--dense`**.
2. **Same, with `EDGE_MASK_BODY_RASTER` = 59** if the 0.2–0.3 % single-frame residual (one late/fallback frame per 320–500) is ever visible; costs one aperture line. Not measured, expected clean by margin analysis.
3. **Reject — Stage 5A as implemented.** Sound mechanism, wrong schedule: it holds the DISPLAY IRQ to raster 60 on *every* frame, denying the main thread a flat ~570 cycles/frame at the median in the frame's most contended window.
4. **Reject — intrinsic / full-192-line solutions** (numbers in §6). The border cannot do it while the HUD lives in the top border; every data-side approach either moves with fine or needs per-phase glyph variants that do not fit VIC bank 0 and cost ~9,000 cycles per fine step.

---

## 1. Is the Stage 5A idea sound? Yes.

The measured defect (both terrain boundaries sit at `48+fine` / `247+fine` and snap 7 rasters at each coarse wrap) is a finite-fetch quantisation; content at any fixed raster is exactly continuous across the coarse step (Stage 5A §2, re-confirmed here on every fixture). A fixed aperture is therefore the correct presentation, and the VIC's invalid text mode (ECM+MCM → black) is the only mask primitive that costs **one register write**: charset/palette untouched, sprites unaffected, no `$D01F` use anywhere in the engine. Nothing in this review changes that judgement. What was wrong is *when the CPU pays for the two writes*.

## 2. Is the busy-wait responsible for the returned hitching? Mechanistically yes; not reproduced as deferrals here.

Measured on the ordinary 6-enemy wave (seed 382, 320 frames) and `--stress` (500), three builds: OFF (4J), ON (5A), and STUB (5A with the top wait removed):

| | DISPLAY IRQ exit raster p50/p90/max | display-phase IRQ occupancy cycles p50/p90/max (wave) | reason-3 gate judged at raster p50/max (wave) | real coarse deferrals | replay |
|---|---|---|---|---|---|
| OFF (4J) | 51 / 56 / 57 | 187 / 508 / 553 | 122 / 177 | 0 | 2 |
| ON (5A) | **60 / 60 / 60** | **755 / 758 / 761** | 130 / 179 | 0 | 3 |
| STUB | 52 / 57 / 58 | ≈ OFF | 125 / 168 | 0 | 1 |
| **FINAL** | 48 / 53 / 54 | **424 / 677 / 680** | 131 / 181† | 0 | 2 |

† the gate raster is not a paired metric — gameplay diverges run-to-run with CIA jitter (page-B counts 142–179 across runs), so ±5 lines between runs is noise.

So the Stage 5A candidate removes a **flat ~570 cycles/frame (≈9 raster lines) from the main thread at the median**, ~210 at the heaviest frame, all of it between rasters ~49 and 60 — i.e. between `armFirstBatch` (≈19–37) and the main thread's gameplay pass. Every frame pays it regardless of load, because the hook polls from wherever the HUD handoff ended to raster 60.

What I could **not** reproduce is a coarse deferral or a replay-rate change: all three builds show 0 real deferrals and 0–3 replays on both fixtures, and the main-thread tail (`prepareBackgroundCoarse` up to raster 294–309) is dominated by run-to-run variance. The honest statement is: the 6-enemy wave already runs its heaviest frames within a few lines of the 312 boundary and within 5–7 lines of the conservative 184 gate; Stage 5A erodes 3–9 lines of that margin on every frame; the user's real waves (more bullets/turret fire than seed 382) plausibly cross where the fixture does not. The design response is the same either way — the wait is pure waste and it sits in the worst possible window.

**Cycles per frame denied to the main thread (Q3):** Stage 5A ≈ 755 − 187 = **~570 at p50, ~250 at p90, ~210 at max**; final ≈ **~240 / ~170 / ~130**. The remaining ~130–170 at the tail is the structural floor: an exact-line VIC write from this scheduler needs the CPU spinning for ≥2 lines before the line (§3), and on the heaviest frames the handoff ends only 2–4 lines before the mask line.

## 3. Can the transitions be scheduler events? Yes — with three facts you must respect.

**Fact 1 — compare→hook latency is 2–3 raster lines, not "an IRQ".** Measured with the prototype armed at T−2: hook entry landed at arm+2 (fine phases with no badline in the way) and arm+3 (a badline between arm line and target). The path is 7 cycles entry + the KERNAL `$FF48` stub (~30) + `rasterIRQ` + `dispatchRasterEvents` + hook preamble ≈ 115 cycles, +43 when a badline sits in the way — which it does on half the phases. Hence **arm at T−5 (T−6 on the badline phase)**; the hook's existing prime/poll then lands the store exactly as before. (Measured after the fix: `EDGE_MASK_LATE` 239→0.)

**Fact 2 — the dispatcher's hot path is per-batch and has ~30 cycles of slack under `--dense`.** My first integration added a 6-cycle pending check in `!select` and a 5-cycle `cmp #MASK` in `!service`; both run once *per batch*, and `--dense` serves 8 batches in one catch-up IRQ: **508 sprite-start misses** (accepted signature 13–16). Fix: encode the mask as phase 2 of `RASTER_DISPLAY_PENDING` (2 = handoff due, 1 = aperture-open due, 0 = done — the load+branch the baseline already pays decides both) and test `RASTER_EVENT_SPRITES` first in both dispatch chains. Batch dispatch now costs ~3 cycles *less* than baseline, and `--dense` drops to **0 misses** — the ~24 cycles recovered over 8 batches exceed the ~10-cycle deficit Stage 4I measured behind the badline coincidence. Both reorderings are gated; OFF is byte-identical.

**Fact 3 — a near/past mask target must not count as a `RASTER_CATCHUPS` event.** Routing it through the generic `!due` path inflated that health metric ~100× (1 → 107). The `!mask` arm block now makes its own arm/serve decision and jumps to `!service` directly.

Everything else stayed inside the existing machinery: one new event id, one `.byte` fewer than the first prototype (no separate pending flag), the same `!current` arm/near/due logic, the same `borderOpenHook` band-close poll (free — that hook already waits to raster 250 for the RSEL dodge).

### Where it sits and how it behaves (measured, final binary, wave)

| point | raster : cycle | n |
|---|---|---|
| DISPLAY hook entry (`HUD_HANDOFF_RASTER` 43) | 45:18..40 | 320 |
| DISPLAY hook exit (`rasterDisplayRestored`) | 46..54 (p50 46, p90 53) | 320 |
| mask event arm | 53 (52 on the `fine==2` badline phase) | — |
| mask hook entry | 50..57 (inline-served when DISPLAY ends ≥51) | 320 |
| aperture open, normal path (`stx $d011`) | **58:3..9** | 280 |
| aperture open, badline-phase early store | **57:54..62 / 58:0..2** | 39 |
| band close (`borderOpenHook`) | **248:3..14** | 320 |
| `EDGE_MASK_LATE` / `EDGE_MASK_FALLBACK` | 0 / 1 (wave), 1 / 0 (stress), 0 / 0 elsewhere | — |

Badline phases are handled exactly as in Stage 5A (the store goes into the previous line's tail when the mask line itself is a badline); the event's arm line is phase-aware for the same reason. HUD handoff: `hudSlotReclaimed` for slots 4..7 now lands at rasters 46–52 (was 50–56); the HUD sprites' last displayed line is 43, fetched at the end of line 42, so reclaiming from 45 is safe by two lines — HUD band present on **450/450** sampled frames. `HUD_HANDOFF_COMPLETE_RASTER` (56) is left in place (now conservative). No sprite slot is stolen; no batch timing moves; `applyLiveRasterBatch` untouched.

### Can the top boundary go back to 55? Not with the HUD handoff in the frame.

The badline-phase path must arrive by T−2 after the handoff, whose exit is measured at 46..54. With T=57 the margin is zero and 3 badline-phase frames per run fell back (1-px-low top edge for that frame); **T=58 gives one line of margin** and is what ships here (aperture **58..247 = 190 lines**, +2 over Stage 5A). 55..247 would need the reclaim to finish by 52 — a faster `hudBorderHandoff`, i.e. HUD work, out of scope.

## 4. Full 192-line playfield — is it achievable? Only by moving the HUD.

The RSEL=0 vertical border masks exactly `<=54` / `>=247` for free (55..246 = 192 lines, the documented clean body) with zero CPU and zero shimmer. It is unavailable because the vertical border flip-flop can only be *cleared* at raster 51 or 55, and the HUD sprites are displayed at 23..43 — so the flip-flop must already be clear from the previous frame, which opens both borders and exposes the quantisation. **That is the true technical reason**, not masking convenience. The two ways to 192 lines are (a) reclaim the HUD slots faster (handoff end ≤52 → T=55/56) or (b) take the HUD out of the top border and let the hardware border mask. Both are HUD architecture.

## 5. Options compared

| | A — Stage 5A as implemented | B — scheduler-integrated (final) | C — intrinsic full-aperture |
|---|---|---|---|
| visual | fixed 60..247, black surround | fixed 58..247, black surround | 55..247 in theory |
| aperture (lines) | 188 | **190** | 192 |
| IRQ occupancy cycles p50/max | 755 / 761 | **424 / 680** | 0 (border) — HUD relocation required |
| main-thread cost vs 4J | −570 / −210 | −240 / −130 | 0 |
| badline handling | phase branch | phase branch + phase-aware arm | n/a |
| `--dense` misses | 13–16 | **0** | — |
| HUD / mux | unchanged | handoff 46→43, measured safe | HUD moves |
| complexity | 2 hooks | + 1 event id, 2-phase pending, ~120 lines | charset/data or HUD redesign |
| risk | main-thread starvation (measured) | low; all gated; OFF byte-identical | high |

## 6. Intrinsic (non-masking) candidates — evaluated and rejected

- **Guard / sacrificial / blank rows, colour-RAM blanking, pre-rendered rows, matrix duplication:** every boundary tied to a matrix row sits at `48+8k+fine` and therefore *moves with fine*; blanking row 0 just relocates the sawtooth to 56..63. Verified by the same fixed-raster continuity measurement — only raster-defined boundaries are still.
- **Per-phase glyph variants (the only correct data-side approach):** rows 0 and 24 must show world rows whose top/bottom `8−fine` pixel rows are blanked *per phase*. Either 8 masked copies of the 72-glyph terrain set (4.6 KB; VIC bank 0 has no free 2 KB CB slot — every one is occupied) or 80 private glyphs re-masked every fine step (only 60 codes free; ~9,000 cycles per fine step, every 2 frames — ~4,500/frame, an order of magnitude above the mask's cost, plus builder/turret-overlay coupling). Reject.
- **FLD / DEN tricks:** row-granular (idle starts at a row boundary), so the boundary still moves; FLD also inserts a visible gap. Reject.
- **Sprites:** 8 X-expanded sprites cover 320 px, but slots 4..7 are being handed off and gameplay needs the rest at exactly those rasters. Reject.
- **Border:** the right answer, blocked by the top-border HUD (§4).

## 7. Regression — final binary `b719de4c…`

| fixture | frames | replay | catchup | `[19656]` | svc fail | incomplete | sprite-start miss | page A/B | LATE / FALLBACK | real defer / admit |
|---|---|---|---|---|---|---|---|---|---|---|
| idle | 300 | 0 | 0 | ✅ | 0 | 0 | 0 | 156/144 | 0 / 0 | 0 / 18 |
| **6-enemy wave 382** | 320 | 2 | 1 | ✅ | 0 | 0 | 0 | 158/162 | 0 / 1 | 0 / 19 |
| stage wrap 12 | 340 | 5 | 2 | ✅ | 3 † | 0 | 0 | 180/160 | 0 / 0 | 0 / 20 |
| `--y199` | 400 | 0 | 0 | ✅ | 0 | 0 | 0 | 211/189 | 0 / 0 | 0 / 12 (scrolls) |
| `--dense` | 200 | 100 | 1386 | ✅ | 0 | 0 | **0** | 104/96 | 0 / 0 | 0 / 6 |
| turret-playtest | 500 | 0 | 0 | ✅ | 0 | 0 | 0 | 260/240 | 0 / 0 | 0 / 31 |
| `--stress` | 500 | 0 | 0 | ✅ | 0 | 0 | 0 | 244/256 | 1 / 0 | 0 / 31 |

Aperture **58..247 on 750/750** sampled frames (wave, stress, dense, wrap, turret). Page-aware pointer oracle active. `RASTER_CATCHUPS` honest (1/0, vs 107 in the first integration).

† Frames 82 and 165 are the disclosed Stage 4G HUD-slot flip-transition oracle caveat (both are the first page-B frame, slots 4–6, placeholders 188–190). **Frame 88 is a real, pre-existing Stage 4F ordering race, not this review's doing:** both hardware tables agree (`$07F8 == $2BF8`, slot 6 = 194); the LIVE batch at raster 63 correctly wrote 155 to the active page, but the main thread was late that frame (`gameplayPresented` at raster 66, normally 24–31) so `ssFlipMirrorPtrs`'s every-frame `$07F8→$2BF8` copy ran *after* the batch and clobbered it with the handoff's 194 — a one-frame wrong sprite pointer on one slot. It is the same fixture frame Stage 4H recorded in Mode B. Bounded fix: skip the mirror for slots already reassigned, or run it only while `RASTER` precedes the first batch. Recommended as a small follow-up.

## 8. Other findings

- **Latent black-frame hazard, now guarded:** `publishRasterPlan` used to re-install `$D011` with ECM forced; had it ever run after the aperture opened (measured max raster 37, so never observed) the rest of the frame would have gone black. It now preserves the current ECM state.
- **The dispatcher's per-batch paths are a hard no-go zone**: 11 cycles there turned into 508 dense misses. Worth a comment in `AGENTS.md`.
- **Byte-identity discipline paid off twice**: the OFF hash moved once during the review (an unconditional `lda #1` leaked into the OFF path) and was caught immediately.
- The four zero-byte trace labels (`edgeMaskEntry`, `edgeMaskBodyApplied`, `edgeMaskBodyAppliedEarly`, `edgeMaskBandApplied`) remain; they cost nothing and made every measurement here possible.

## 9. Answers

1. **Sound?** Yes — invalid text mode is the right one-write mask; the geometry (58/248) is right.
2. **Busy-wait responsible for the hitching?** It removes a flat ~570 cycles/frame (median) from the main thread in the early frame; deferrals/replays did not increase in the two fixtures, so the link to the user's real waves is mechanistic, not reproduced. Either way the wait is removed.
3. **Cycles denied:** Stage 5A ≈ 570 p50 / 210 max per frame; final ≈ 240 / 130. Floor ≈ 2 lines on the heaviest frames (§2, §3).
4. **Tiny deterministic events?** Yes — implemented; latency 2–3 lines dictates a 5/6-line arm lead.
5. **Architecture:** mask-open as `RASTER_EVENT_MASK` armed from `dispatchRasterEvents` via a 2-phase `RASTER_DISPLAY_PENDING`, sprites-first dispatch, own arm/serve decision, hook unchanged from Stage 5A; band-close stays inside `borderOpenHook`'s existing wait; HUD handoff compare 43; `publishRasterPlan` ECM-preserving.
6. **Top boundary toward 55?** 60 → **58**; 57 measured zero-margin (3 fallbacks/run); 55 needs the handoff to end by 52.
7. **Full 192 lines?** Only by moving the HUD out of the top border (then the hardware border does it for free) or a faster reclaim. Not with masking as the HUD stands.
8. **Better non-masking solution?** No (§6).
9. **Measured costs:** §5 table.
10. **Best visual:** A and B are identical except B has +2 aperture lines.
11. **Best smoothness:** B (final).
12. **Lowest risk:** B — fully gated, OFF byte-identical, full suite clean, dense improved.
13. **Prototype implemented:** B, in the working tree (`b719de4c…`).
14. **Did the 6-enemy wave return to smooth?** In measurement, IRQ occupancy is back near baseline and there are 0 deferrals/holds; **visual confirmation is the user's** — the fixtures never showed the hitch in the first place.
15. **Regressions safe?** Yes (§7), with the two disclosed pre-existing wrap caveats.
16. **Next for Opus/Sonnet:** (a) user visual acceptance of `b719de4c…` (top/bottom edges still; no hitch in 6-enemy waves; black surround; sprites visible in the letterbox); (b) if any residual edge flicker is seen, `EDGE_MASK_BODY_RASTER` 58→59; (c) a bounded fix for the `ssFlipMirrorPtrs`-after-batch race (§7); (d) note the dispatcher hot-path rule in `AGENTS.md`; then commit.
