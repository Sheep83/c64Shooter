# C64 Display Geometry / HUD / Coloured-Background Investigation

**Investigation only. No implementation, no commit, no push.** This report
explains the top-edge artefact, accounts for every lost vertical pixel, traces
the history of the 24-row (RSEL=0) decision, evaluates alternatives, and
recommends an architecture. It does **not** change engine, editor, generated
assets, project JSON, raster scheduling, HUD code, RSEL config or tests.

---

## 1. Branch / HEAD authority

| Item | Value |
| --- | --- |
| Branch | `terrain-asset-workshop` |
| HEAD | `3a72c13ab50554b7e90ac591872dfa569a350bd0` — *"Tile editor and tileset import added to stage editor"* |
| Working tree | Dirty from Tasks 1–3 (terrain workshop / usability / native tiles). No file was modified by this investigation. |
| Emulator | PAL `x64sc` (`-default -pal -warp`), 312 lines × 63 cycles = 19,656 cycles/frame |
| Assembler | KickAssembler 5.25 |
| Fixed-HUD dispatcher | `src/raster_scheduler.asm` (`* = $6000`), introduced by commit `20eb3b5` *"Add fixed top HUD and deadline-aware raster scheduler"* |
| 24-row conversion | commit `f6e9620` *"Conversion to 24-row VIC mode"* (predates the HUD split) |

`git diff src/raster_scheduler.asm` = 0 lines. `git status` shows no
investigation-authored change to any tracked file (§19).

---

## 2. Investigation-only confirmation

- No implementation code, generated asset, project JSON, editor, engine, memory
  layout, raster schedule, HUD routine, RSEL setting or test was changed.
- All evidence was gathered from: reading tracked source and docs; `git log` /
  `git show`; and three **disposable** Python probes that launch the already-built
  `build/shooter.prg` in a background VICE, read the remote monitor, single-step
  the raster IRQ, and take screenshots. The probes' only writes are to **live
  emulator RAM** (`> d020 01`, `> d021 00` …), restored before the emulator is
  killed. They never patch the PRG or touch the repo.
- VICE was launched head-less/background with `-remotemonitor` only. No
  `open -a`, no focus steal.
- The recommendation in §13 is **not** implemented.

---

## 3. Artefact reproduction

**Symptom (as reported):** an ugly horizontal band across the top of the
gameplay area, immediately below the score line, that only became visible once a
level used a non-black `$D021`. With a black `$D021` the top edge looked clean.

**Reproduced.** With the current working-tree Level 1 config
(`src/generated/level1/stage_config.asm`: `TERRAIN_BACKGROUND_COLOUR = 12`,
medium grey) the running game shows a **solid dark stripe ≈ 8 pixels tall
(one character row)** spanning the full 320-pixel playfield width, wedged
between the score row and the first terrain row. Forcing `$D021` to a bright
value in live RAM (`> d021 01`, white) turns the same stripe into a **glaring
solid-black bar**. Forcing `$D021` back to 0 (black) makes it **vanish
completely** — black-on-black.

Screenshot pixel analysis (`analyze_png.py`, VICE 384×272 screenshot,
`screenshot_y + 16 = raster line`):

| Screenshot | `$D020` | `$D021` | raster 16–54 | raster 55–62 | raster 63–70 | raster 71–246 |
| --- | --- | --- | --- | --- | --- | --- |
| `01-as-is.png`      | 0 (black) | 12 (md grey) | black border | lt-grey/white (HUD) | **black 100 %** | grey terrain |
| `02-white-border.png` | 1 (white) | 12 | white border to r54 | lt-grey/white (HUD) | **black 83 %** | terrain |
| `03-d021-black.png` | 0 | 0 (black) | black | black (HUD unlit) | **black — invisible** | terrain from r71 |
| `04-d021-white.png` | 0 | 1 (white) | black | white (HUD) | **black 100 %** | white terrain |

The band's raster position (63–70) and height (8 lines) are **identical in
every screenshot and every fine-scroll phase** — it does not move, grow, shrink
or flicker. Only its visibility against `$D021` changes.

---

## 4. Exact root cause

The band is the **deliberate "masked separator" of the raster-split fixed HUD**
in `src/raster_scheduler.asm : rasterDisplayHook`. It is produced by writing
`$D011` values with **BMM (bit 5) and ECM (bit 6) both set at once**, which on
the VIC-II is an **invalid graphics mode that forces the entire display window
to black**, regardless of screen matrix, colour RAM, character data, `$D021`,
`$D022`, `$D023` or `$D018`.

Per-physical-frame `$D011` sequence inside the hook (probe `probe2.py`, single
stepped; raster from `$D012 | (($D011 & $80) << 1)`):

| ~raster | `$D011` write | bits | effect |
| ---: | --- | --- | --- |
| 55 (badline) | `$17` (set by `publishRasterPlan` / `rasterFrameReset`) | YSCROL 7, RSEL 0, DEN 1, **text** | fetch + show HUD matrix row 0 |
| ~59 | `$11` | YSCROL 1, text | prep write; YSCROL 1 chosen so no stray badline at 59–62 |
| ~62 (after `rasterHblankDelay`) | `$71` | YSCROL 1, **BMM+ECM → INVALID/BLACK** | blank everything from raster 63 |
| ~63 (fine 0–6) | `$70 \| fine` | YSCROL = fine, **BMM+ECM → INVALID/BLACK** | still black; first terrain fetch scheduled 64+fine |
| ~64 (fine 7 only) | `$77` | YSCROL 7, **BMM+ECM → INVALID/BLACK** | still black; fine-7 terrain badline is 71 |
| ~70 (after `rasterHblankDelay`; fine 6 uses a tighter `bit $01` path) | `$10 \| fine` = `RASTER_DISPLAY_NORMAL` | YSCROL = fine, RSEL 0, DEN 1, **text** | terrain resumes, visible from raster 71 |

So rasters **63–70 inclusive (8 lines) are forced black by invalid mode** on
every frame and every fine phase. That 8-line black band is the artefact.

**Why invalid-mode black and not just `$D021`:** between the HUD row (YSCROL 7)
and the terrain rows (YSCROL 0–7) the VIC's badline/​video-matrix pointer has to
be walked from row 0's fetch at raster 55 to terrain matrix row 1's first fetch
at raster 64+fine. During that walk the display window would otherwise show
fragments of a half-fetched row and mode-transition glitch pixels. Invalid mode
is the *strongest possible* mask: it blacks out **foreground pixels too**, which
a plain `$D021` write, an ECM write, or a blank-background write cannot do
(their character foreground bits would still paint). The design (see
`docs/fixed-hud-codex-worklog.md` lines 105–118, 203–214, 264–266, 654–656)
consciously chose invalid-mode masking for that reason and validated it against a
pixel oracle — but **only ever with a near-black `$D021`**, so the band's own
colour was never a visible variable.

Answering the brief's checklist explicitly:

| Candidate cause | Verdict |
| --- | --- |
| Border colour (`$D020`) | **No.** `$D020` = 0, written once in `init` (`src/main.asm:419`), never changed. The band is inside the display window, not border. |
| Background colour (`$D021`) | **Indirect.** `$D021` does not *create* the band; it only stops *concealing* it. The band is colour-independent (invalid mode). |
| Hidden / incoming matrix row | **No.** Matrix row 1 *is* behind the band, but the band is drawn by the mode write, not by row-1 data. |
| Bad character data | **No.** Charset and matrix are correct; invalid mode ignores them. |
| Vertical fine-scroll exposure (idle strip) | **Not directly.** The band happens to sit exactly where the top idle strip used to be and masks the same class of seam — but it is an explicit mode write, not exposed idle output. |
| RSEL opening/closing the display | **No.** RSEL stays 0 throughout; the hook never touches bit 3. |
| Raster split at an awkward line | **Yes — this is it.** The HUD↔terrain raster split masks its transition (rasters 63–70) with invalid-mode black. |
| Combination | The visible result = *invalid-mode masked separator* (mechanism) + *non-black `$D021`* (what makes it show). |

---

## 5. Register / raster / memory evidence

Live PLAYING registers (probe `probe2.py`, VICE monitor; colour registers
read back with high nibble `$F`, masked `& $0F`):

```
$D011 cycles 55.. : $17 → $11 → $71 → $70|fine → $10|fine   (per frame, in rasterDisplayHook)
$D016 = $D8   MCM = 1 (multicolour text), CSEL/XSCROLL untouched
$D018 = $1F   screen matrix $0400, charset $3800, VIC bank 0 — never flipped
$D020 = $0    border black (init only, never rewritten)
$D021 = $C    TERRAIN_BACKGROUND_COLOUR = 12 (working-tree Level 1)
$D022 = $F    TERRAIN_MC_COLOUR_1 = 15
$D023 = $B    TERRAIN_MC_COLOUR_2 = 11
```

Memory / addressing:

- One screen matrix `BG_SCREEN_A` = `$0400`. `initFixedHud` (`src/main.asm:6130`)
  writes matrix **row 0** with private HUD glyphs (`HUD_GLYPH_BASE = 64`) and
  colour RAM `$D800..$D827` = 1 (white). `initBackground`'s fill loop
  (`src/main.asm:5198` `ldx #1 … cpx #24`) writes terrain into matrix **rows
  1..23**. Matrix **row 24** is set to blank `$20` and never enters the RSEL=0
  aperture.
- Colour RAM is one fixed value `TERRAIN_COLOUR_RAM` for the whole playfield,
  written once, never scrolled.
- `applyFineScroll` (`src/main.asm:5088`) only stores `SCROLL_FINE` into
  `RASTER_DISPLAY_FINE`; it does **not** write `$D011`. Every gameplay `$D011`
  write is owned by the physical-frame dispatcher / `rasterDisplayHook`.
- `rasterFrameReset` / `publishRasterPlan` write `$D011 = $17` at the top of
  every physical frame; the hook then performs the split.

Screenshot geometry (all four PNGs agree):

```
raster 16..50 : border            (RSEL=1 would still be border here)
raster 51..54 : border            (RSEL=0 crops what RSEL=1 would open)
raster 55..62 : HUD row 0          8 px — YSCROL 7 fixed, MC text, bg = $D021
raster 63..70 : SEPARATOR (BLACK)  8 px — BMM+ECM invalid mode — THE ARTEFACT
raster 71..246: terrain rows 1..23 176 px — YSCROL = fine, scrolls
raster 247..250: border           (RSEL=0 crops the bottom scroll-edge pop)
```

---

## 6. Did black conceal it? — proven yes, it always existed

- **Mechanism proof:** the band is `BMM+ECM` invalid mode. That output is black
  by hardware definition and cannot be any other colour. It has been emitted by
  `rasterDisplayHook` on every frame since commit `20eb3b5` (fixed HUD).
- **A/B proof:** `03-d021-black.png` (`$D021` forced 0) — the raster 63–70 band
  is byte-for-byte identical to the border/​unlit-HUD black around it and is
  invisible. `04-d021-white.png` (`$D021` forced 1) — the *same 8 lines* are a
  solid black bar with 100 % coverage. Nothing about the band changed between the
  two shots except the register that everything *else* on those lines is drawn
  in.
- **History proof:** every shipped/tested level used `$D021` at or near black
  (`build_levels.py` `L1_PALETTE["background"] = 0`; `level.json` `background:
  0`; HEAD `stage_config.asm` `TERRAIN_BACKGROUND_COLOUR = 0`). The fixed-HUD
  pixel oracle (`tools/check_fixed_hud_capture.py`,
  `docs/fixed-hud-codex-worklog.md`) validated the separator's *position* and
  that terrain resumes cleanly at raster 71 — never its *colour*, because with a
  black backdrop there was no colour to validate.

The artefact is **not new**. The working-tree change of
`TERRAIN_BACKGROUND_COLOUR` from 0 to 12 (a Task-3-era edit;
`level.json`/HEAD still say 0) is simply the first time a non-black `$D021` has
been in front of it. It is a broken `$D020 == $D021 == black` assumption — the
same class of assumption noted in `docs/scroll-edge-investigation.md` line 58
("They are black in this engine").

---

## 7. Exact current vertical display geometry

PAL, RSEL=0, DEN=1, one matrix `$0400`, charset `$3800`. Reference aperture is
the RSEL=1 window raster **51..250** (200 px = 25 char rows). All ranges
inclusive; "px" = raster lines.

```
 raster   px  rows  what is there                       owner / necessity
 ─────────────────────────────────────────────────────────────────────────────
 51..54    4   ½    RSEL=0 top crop → BLACK BORDER        RSEL arrangement.
                    (RSEL=1 would open idle black here,        Now REDUNDANT: the
                     above the HUD)                            HUD+separator already
                                                               mask the top scroll seam.
 55..62    8   1    FIXED HUD  (matrix row 0)             HUD-REQUIRED.
                    YSCROL 7 fixed · MC text · bg = $D021      Score / FREE line.
                    · fg colour RAM = 1 (white)
 63..70    8   1    MASKED SEPARATOR — forced black       RSEL/​split consequence.
                    (BMM+ECM invalid mode)                     Masks matrix row 1's
                    THE ARTEFACT with non-black $D021          7-scanline partial fetch
                                                               (64..70) + the YSCROL 7→fine
                                                               transition.
 71..246 176  22    TERRAIN  (matrix rows 1..23)          GAMEPLAY.
                    YSCROL = fine (0..7) · scrolls             Row 1 grows from 1 px at
                    MC text · bg $D021 / $D022 / $D023         raster 71; rows ~2..22 full;
                                                               row 23 partial at bottom.
 247..250  4   ½    RSEL=0 bottom crop → BLACK BORDER     ANTI-POP — still doing
                    (RSEL=1 would expose outgoing row 24      original work: hides the
                     + the 7→0 bottom scroll pop)             bottom scroll-edge pop.
 ─────────────────────────────────────────────────────────────────────────────
 total   200  25    of which GAMEPLAY = 176 px / 22 rows
```

Distinctions the brief asks for:

| Class | Lines | Notes |
| --- | ---: | --- |
| Border (VIC, unavoidable at these `$D011` settings) | 51..54, 247..250 (8) | Only because RSEL=0. |
| HUD-reserved (product requirement) | 55..62 (8) | The score line. A HUD of some size is wanted. |
| Masked-but-existing / transition | 63..70 (8) | Matrix row 1 is *addressed* and *scrolled* here but only 1 px of it is ever visible (at raster 71). Effectively a spacer. |
| Usable terrain | 71..246 (176) | 22 comfortably visible rows + slivers of rows 1 and 23. |
| Gameplay exclusion zone for readability (not VIC) | none | The engine imposes no extra "keep clear" strip beyond the above. |

---

## 8. Exact gameplay area lost

Against the 200 px / 25-row RSEL=1 aperture:

| Lost region | px | rows | Category | Recoverable as gameplay? |
| --- | ---: | ---: | --- | --- |
| RSEL=0 top crop (51..54) | 4 | ½ | RSEL arrangement — now redundant | **No net gain.** Recovered pixels land *above the HUD*, outside the play area. |
| Fixed HUD (55..62) | 8 | 1 | HUD requirement | No — this is the HUD. |
| Masked separator (63..70) | 8 | 1 | Raster-split consequence | **Partially** — see §11/§13. Only via a design change (blank spacer row or different HUD scheme); not free. |
| RSEL=0 bottom crop (247..250) | 4 | ½ | Anti-pop, still needed | Only by masking the bottom pop another way (bottom separator / accept pop). 4 px, high risk-to-reward. |
| **Total lost** | **24** | **3** | | **Realistically reclaimable ≈ 8 px (1 row).** |

- **Top loss:** 20 px (rasters 51..70) = 4 (RSEL crop) + 8 (HUD) + 8 (separator).
- **Bottom loss:** 4 px (rasters 247..250) = RSEL crop.
- **HUD-*required*:** 8 px. Everything else is arrangement/anti-pop overhead.
- The playtest complaint ("too much lost top *and* bottom") is mostly the **top
  16 px of arrangement overhead** (redundant RSEL crop + separator) plus the
  8 px HUD; the bottom is only 4 px and is genuinely earning its keep.

---

## 9. Historical reason RSEL=0 was introduced

Source: `docs/scroll-edge-investigation.md` (the handoff that commit `f6e9620`
"lands the completed investigations this builds on") and the `f6e9620` commit
message.

The engine scrolls a **25-row (200 px) character image** vertically behind a
fixed border. It fetches exactly 25 matrix rows; there is **no 26th-row fetch**.
Consequences measured for every fine phase (`scroll-edge-investigation.md`
§"What the VIC displays"):

- **Top, fine 4–7:** an ideal infinite scroll would reveal 1–4 pixel rows of the
  *next incoming* row at the top of the aperture. The VIC instead emits **idle
  output** (black) there, because its first fetched row is still matrix row 0
  starting at raster 52/53/54/55. At the coarse 7→0 transition the freshly
  installed row 0 appears as a **5-line arrival at rasters 51..55** where an
  ideal model expected a 1-line arrival — a visible "pop".
- **Bottom, fine 7→0:** outgoing matrix row 24 contributes 4 scanlines at
  247..250, then the coarse copy discards it and the VIC finishes the new last
  row at 247 and emits idle at 248..250. The outgoing row snaps from height
  **4 → 0** instead of 4→3→2→1→0 — a second "pop".

Both pops occur **only at the 7→0 coarse transition** and only where foreground
terrain bits create contrast (so sparse scenery makes them intermittent).

`f6e9620`'s fix: clear RSEL once in `init`. The aperture becomes raster
**55..246** (192 px), which *"lies wholly inside fetched terrain for all eight
fine-scroll phases"* — the idle strips and the pop scanlines are pushed into the
border. Cost: ~6 cycles/frame (reuse existing `$D011` writes with different
masks), 4 cropped scanlines at each edge (also crops sprite pixels there). It is
a **cosmetic display-policy crop, explicitly "not a HUD"**
(`docs/fixed-hud-feasibility.md` Option A).

The chronology matters:

```
8a2c841  proved fixed character HUD over scrolling playfield   (patch-HUD era)
f6e9620  Conversion to 24-row VIC mode          ← RSEL=0 added here, to hide BOTH scroll pops
20eb3b5  Add fixed top HUD + deadline-aware raster scheduler   ← the raster split HUD arrives AFTER
3dfe4c4  Larger levels … up to 844 rows
3a72c13  (HEAD)
```

RSEL=0 was introduced to solve a **pure-scroller** problem, *before* the
raster-split HUD existed.

---

## 10. Does that reason still apply?

**Split verdict — top: no; bottom: yes.**

- The underlying VIC fact is unchanged: the engine still fetches 25 matrix rows
  with no 26th fetch, so the fine-scroll idle strips / 7→0 pops still exist as
  raw geometry. Nothing in the engine's evolution (raster scheduler, BUILD/LIVE
  plan, coarse-scroll deferral, score dirty-flag, charset/​memory reorg, sprite
  multiplexer, turret streaming, terrain decoder) changed the scroller's row
  count or added a 26th fetch.

- **Top edge:** the raster-split HUD now *owns* the top of the display. Matrix
  row 0 is the fixed HUD; the **invalid-mode separator (rasters 63–70) already
  masks matrix row 1's partial reveal and the entire top scroll seam** — it is
  doing exactly the job RSEL=0's top crop was added for, and more (it hides a
  whole row, not 4 lines). With the HUD + separator in place, RSEL=1 would only
  expose 4 lines of black idle *above the HUD* (raster 51–54), which is
  cosmetically border-equivalent. **RSEL=0's top crop is now redundant.**

- **Bottom edge:** unchanged. There is no HUD or separator at the bottom. RSEL=1
  would expose outgoing matrix row 24 and the 7→0 bottom pop at rasters 248–250.
  **RSEL=0's bottom crop still does its original job.**

**"We don't need that hack anymore" hunt — partial hit.** The *top half* of the
RSEL=0 crop is dead weight: it was superseded by the separator band that a later
commit added for a different reason. Removing RSEL=0 wholesale is **not** safe
(it re-exposes the bottom pop). Removing only the top crop is not possible —
RSEL is one bit affecting both edges symmetrically. So RSEL=0 stays, but its
*cost* at the top (4 px) is now paid for nothing, and the real top-edge cost is
the 8 px separator, which is a property of the HUD split, not of RSEL.

---

## 11. Serious alternatives considered (evaluated, not implemented)

| # | Architecture | Top-edge artefact | Gameplay height | Coordinate impact | Risk |
| --- | --- | --- | --- | --- | --- |
| 0 | **Status quo** — RSEL=0 + raster-split HUD + invalid-mode separator | Present with non-black `$D021` | 176 px / 22 rows | none | — |
| 1 | **Restore 25-row (RSEL=1)**, keep the HUD split | Separator unchanged (it's the split, not RSEL) → **still present**; *also* re-exposes both scroll pops | +8 px raw (4 top above HUD, 4 bottom) but the bottom 4 px now *pops* | none | Med — reintroduces a documented, deliberately-fixed defect for ~4 px of usable gain |
| 2 | **HUD = 1 row, terrain fills the rest of a 25-row window** | = alternative 1 (this is just "RSEL=1 + current split") | as #1 | none | Med |
| 3 | **Raster-split character HUD** | *This is the shipped design (alternative 0).* | 176 px | none | — |
| 4a | **Recolour the separator to `$D021` via a permanent blank spacer row** (matrix row 1 = blank `$20`, scroller uses rows 2..24, `VIEWPORT_ROWS` 23→22) | **Fixed for every palette** — the separator renders a blank char = solid `$D021` | 176 px (honest: row 1 was already only 1 px visible) | `VIEWPORT_ROWS` 23→22 and `STAGE_START_ROW` shift by 1; **world-anchored turret/​wave-trigger rows unchanged** | **Low** — no invalid-mode write, hook simplifies, ~a few cycles saved |
| 4b | **HUD occupies 2 char rows** (rows 0–1, both YSCROL 7); row 1 is a blank/​secondary HUD line at `$D021`; terrain from row 2 | **Fixed** — no invalid-mode band; the YSCROL 7→fine transition is masked by the blank/​known row-1 area | 176 px, and row 1 becomes a *usable* second HUD line (lives, weapon, etc.) | `VIEWPORT_ROWS` 23→22, `STAGE_START_ROW` shift by 1; world coords unchanged | Low–Med — needs a fresh badline proof at the row-1→row-2 boundary |
| 5 | **HUD over the playfield + top exclusion zone** — sprite-drawn score over the top 2 terrain rows, no `$D011` split at all | No separator → **no artefact**; RSEL=0 top crop alone masks the top scroll seam (original design) | ~184–192 px if the exclusion zone is "cosmetic keep-clear" not a real gap | none (exclusion zone is an editor/​authoring guideline) | Med — spends 4–8 sprites on the HUD; multiplexer already runs 9 sprites |
| 6 | **Border HUD** — open the top (and/or bottom) border, draw the score with sprites in the border | **No artefact**; frees the whole 25-row aperture | up to ~200 px | none | **High** — every-frame border opening, tight raster timing, sprite-in-border competes with the 9-sprite multiplexer, needs full stress re-proof |
| 7 | **Bottom HUD** — terrain in matrix rows 0..22 (top, scrolls), HUD in row 23; separator moved to the bottom | Top becomes pure terrain → **no top artefact**; bottom gets the separator/​pop instead | 176 px (unchanged; just relocated) | **Inverts bottom-origin semantics** — `SCROLL_ROW` now = matrix row 0; editor viewport origin flips | High — touches the exact thing the brief says to preserve |
| 8 | **Shorten the separator to 4 lines** (`fixed-hud-codex-worklog.md` "option 15") | Smaller band, still black, still shows | +4 px | none | Med–High — "rotates all logical phase/fetch deadlines; not probed" |

---

## 12. Quantified comparison of the serious candidates

Numbers derived from `src/raster_scheduler.asm`, `src/main.asm`, PAL badline
math (`48 + fine + 8·row`), and `docs/scroll-edge-investigation.md`.

| Metric | 0 Status quo | 1 RSEL=1 | 4a Blank spacer / `$D021` separator | 4b 2-row HUD | 5 Sprite HUD + exclusion | 6 Border HUD |
| --- | --- | --- | --- | --- | --- | --- |
| Usable gameplay height | 176 px / 22 rows | 184 px (+4 top *popping*, +4 bottom *popping*) | 176 px / 22 rows | 176 px / 22 rows (+1 usable HUD line) | ~184–192 px (2 rows shared with HUD sprites) | ~192–200 px |
| Rows/px regained vs status quo | 0 | +4..+8 px (with regressions) | 0 (accounting honesty) | 0 gameplay, +1 HUD row | +8..+16 px | +16..+24 px |
| Top-edge artefact fixed for any `$D021` | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ |
| HUD height | 8 px | 8 px | 8 px | 16 px | 0 (sprite overlay) | 0 (border) |
| Extra raster work / frame | baseline (`rasterDisplayHook`, ~1 IRQ) | ~same | **less** — drop the `$71`/`$70\|f`/`$77` invalid-mode writes; keep one `$10\|f` restore | +1 badline region to prove; similar write count | HUD sprite build + multiplexer slots | border open/close every line of the HUD region + sprite DMA in border |
| Cycle cost delta | 0 | ~0 | **−6..−12 cyc/frame** | +0..+10 cyc/frame | +sprite-build cost; −`$D011` split | +hundreds of cyc/frame (border racing) |
| Sprite multiplexer interaction | none | none | none | none | **competes** — 4–8 HUD sprites against the existing 9 | **competes hard** — sprites in border |
| Scroller interaction | none | none | none — row 1 stops being scrolled, rows 2..24 scroll | none — as 4a | none | none |
| Collision-coord implications | none | none | none (world rows unchanged) | none | none | none |
| Editor viewport implications | none | none | `VIEWPORT_ROWS` 23→22 constant only | 23→22 constant only | overlay a 2-row "HUD-shared" hint | overlay only |
| Memory implications | none | none | 1 reserved blank glyph (already have `HUD_G_SPACE`) | +1 HUD row of glyphs/​colour | HUD sprite frames (~64–128 B each) | HUD sprite frames + border-IRQ code |
| Complexity | shipped | trivial revert | small, local to `rasterDisplayHook` + fill loop bound + 2 constants | moderate (badline re-proof) | large (sprite HUD subsystem) | large (border engine) |
| Regression risk | — | **Med** (re-adds fixed defect) | **Low** | Low–Med | Med | **High** |

---

## 13. Recommended architecture

**Keep RSEL=0. Keep the raster-split fixed top HUD. Replace the invalid-mode
(forced-black) separator with a `$D021`-coloured blank spacer row — alternative
4a, with 4b as the upgrade path if a second HUD line is wanted.**

Rationale:

1. **It fixes the reported artefact for every valid palette** and is the *only*
   option that does so without spending sprites or a border engine. Invalid-mode
   output is black by hardware law; the sole way to make that 8-line band take
   `$D021` is to render a genuine all-zero-bitmap character there, i.e. a blank
   matrix row.
2. **Matrix row 1 is already, in practice, a spacer.** Only 1 pixel of it is
   ever visible (raster 71). Formally reserving it costs **zero real gameplay
   area** — `VIEWPORT_ROWS` goes 23→22 to match what the player has actually
   been seeing all along.
3. **The scroll-edge masking is preserved.** A blank row 1 at the top masks the
   incoming-row reveal exactly as the black band did; RSEL=0's bottom crop still
   masks the bottom pop. No scroll-pop regression.
4. **It removes work, not adds it.** The hook drops the `$71` / `$70|fine` /
   `$77` invalid-mode writes and keeps a single `$10|fine` text-mode restore;
   ~6–12 cycles/frame recovered, and the "fine 6 badline-70" and "fine 7"
   special cases get simpler to reason about (the transition is now text→text at
   a known-blank row).
5. **World-authored coordinates do not move.** Turret rows and wave-trigger rows
   are logical/​world rows (§15); only the boot viewport anchor shifts by one
   row.
6. **Low blast radius:** `src/raster_scheduler.asm` `rasterDisplayHook`, the
   `initBackground` fill-loop bound, `initFixedHud` (blank row 1), one engine
   constant, and the editor's `VIEWPORT_ROWS`. No memory-map move, no
   multiplexer change, no collision change.

If, separately, playtesting wants **more** vertical area rather than just the
artefact fixed, the ranked follow-ups are: **4b** (turn the freed spacer into a
useful second HUD line — same geometry, better HUD), then **5** (sprite HUD over
a cosmetic 2-row exclusion zone, ~+1 row of terrain), then **6** (border HUD,
biggest gain, highest risk — only if the multiplexer budget is re-proven). Do
**not** adopt alternative 1/7 — they trade a fixed defect back in for ≤4 px.

---

## 14. Simplest implementation path for the recommendation (4a) — description only

1. **`src/main.asm : initFixedHud`** — additionally write matrix **row 1**
   (`BG_SCREEN_A + 40 .. +79`) with the private blank glyph (`HUD_G_SPACE`,
   bitmap already all-zero) and colour RAM as today. Row 1 is now HUD-owned, not
   terrain-owned.
2. **`src/main.asm : initBackground`** — change the initial terrain fill loop
   (`src/main.asm:5198-5204`) from rows `1..23` to rows `2..23` (and the scroll
   destination base from matrix row 1 to matrix row 2). `renderStageRowToScreen`
   / `prepareBackgroundCoarse` / `finishBackgroundCoarse` matrix-row constants
   shift by +1 (matrix row 2 becomes "the newest revealed row").
3. **`src/main.asm`** — `STAGE_START_ROW = STAGE_LOGICAL_ROWS - 22` (was `- 23`);
   the `.if (STAGE_LOGICAL_ROWS < 24)` guard becomes `< 23` or stays (still safe).
4. **`src/raster_scheduler.asm : rasterDisplayHook`** — delete the `$11` prep
   write's role change is minor, but remove the `$71` write at raster 62 and the
   `$70|fine` / `$77` invalid-mode writes at 63/64; keep a single text-mode
   `$10|fine` restore in the horizontal blank before raster 71. Blank row 1
   (YSCROL still transitioning) renders solid `$D021` for rasters ~63–70. Re-run
   the badline derivation for the row-1(blank)→row-2(terrain) boundary and the
   fine-6/fine-7 edge cases; keep the page-cross `.error` guards.
5. **`src/raster_scheduler.asm`** — the `.if (* > $6600)` size guard is unaffected
   (code shrinks).
6. **`tools/level_editor/engine_data.py`** — `VIEWPORT_ROWS = 22`; comment update
   ("matrix row 0 HUD, row 1 blank `$D021` spacer, rows 2..23 terrain").
7. **`tools/level_editor/*`** — `STAGE_START_ROW` / bottom-origin helper uses
   `STAGE_LOGICAL_ROWS - VIEWPORT_ROWS`; already parameterised, so it follows the
   constant.
8. **Oracles** — `tools/check_fixed_hud_capture.py`,
   `tools/check_scroll_capture.py`, `tools/check_raster_capture.py`: the expected
   separator is now `$D021`-coloured, not black, at rasters ~63–70; terrain
   first-visible row index shifts by one. `tools/check_scroll_edges.py` aperture
   stays 55..246.
9. **Docs** — `docs/fixed-hud-codex-worklog.md` / `docs/hud-architecture.md`
   milestone: "invalid-mode separator retired; matrix row 1 is a permanent
   `$D021` blank spacer".

No change to: memory map, `$D018`, VIC bank, sprite multiplexer, collision
coordinates, turret pool, wave-trigger world rows, `$D020`, `$D016`.

---

## 15. Editor viewport consequences (editor not modified)

Current editor model (`tools/level_editor/engine_data.py`): `VIEWPORT_COLS = 40`,
`VIEWPORT_ROWS = 23`, bottom-origin `SCROLL_ROW = STAGE_LOGICAL_ROWS -
VIEWPORT_ROWS`; the overlay draws a 23-logical-row aperture; wave triggers are
anchored to **world/logical rows**; turrets to **metatile-cell world
coordinates**. The editor does **not** currently model the 8 px separator — its
top authored row maps to matrix row 1, which the player only sees 1 px of.

For the recommended architecture (4a):

| Question | Answer |
| --- | --- |
| New visible aperture | 40 × **22** logical rows (176 px). This is what the player *already* sees today; the editor's "23" was 1 row optimistic. |
| Viewport row count / pixel geometry change | `VIEWPORT_ROWS` constant 23 → 22. Pixel height per row unchanged (8 px logical / 16 px at the editor's 2:1 VIC aspect). The overlay band is drawn one row shorter. |
| Bottom-origin semantics change | **No.** Still `SCROLL_ROW = STAGE_LOGICAL_ROWS - VIEWPORT_ROWS`; the formula is already written in terms of the constant. The bottom of the aperture still shows the authored last logical row at boot. |
| Wave-trigger rows change | **No.** Triggers fire on `SCROLL_ROW == worldRow` (a logical row). The scenery under a given world row is unchanged; only which *matrix* row renders it moves by one. Authored trigger `worldRow` values stay valid. |
| Turret world coords change | **No.** Turret body world char col/row are absolute; `updateTurretStream` admits by `SCROLL_ROW` window. Unchanged. |
| Authored level / world coordinates need rewriting | **No.** This is the decisive property — the recommendation is a presentation change, not a world-geometry change. Only the editor's `VIEWPORT_ROWS` literal and the (already parameterised) boot anchor move. |

Alternative 4b is identical except the editor may want to *draw* row 1 of the
band as a "HUD" strip rather than "terrain". Alternatives 5/6 leave
`VIEWPORT_ROWS` at 22–24 and add only a cosmetic "HUD-shared / keep-clear"
hint overlay. Alternatives 1/7 would change viewport row count and (7) flip the
origin — rejected.

---

## 16. Coloured-background robustness

The recommended blank-spacer separator renders a real character cell, so it
takes `$D021` like any other background pixel and is correct for **any** valid
palette. Remaining places where display correctness still depends on colours
being chosen sensibly (true for the current engine *and* the recommendation):

| Location | Dependency | Palette that breaks it | Mitigation (not implemented) |
| --- | --- | --- | --- |
| **HUD text** (`initFixedHud` writes colour RAM = `1`, white; `src/main.asm:6145`) | HUD glyphs are white; background is `$D021` | `$D021 = 1` (white) → HUD text invisible | Make the HUD fg colour level-owned, or force it to a fixed high-contrast pair, or keep the HUD row background forced to a fixed colour independent of `$D021`. |
| **Separator band** (today: forced black) | Assumes `$D021 ≈ black` | any non-black `$D021` → **the reported artefact** | The recommendation fixes this. |
| **RSEL=0 border crops** (rasters 51–54, 247–250) show `$D020` | `$D020` = 0 (black), hard-coded in `init` | `$D020` ≠ `$D021` makes the 4-line crops read as a visible frame | `$D020` is not level-owned today; if it ever becomes so, the crop lines become a visible border stripe — acceptable, but should be a conscious choice. |
| **Score digits / `FREE` counter** | private glyphs, colour RAM = 1 | same as HUD text | as HUD text |
| **`$D022` / `$D023`** (terrain MC shades) | authored per level | `$D022`/`$D023` == `$D021` flattens terrain relief | authoring concern, already the artist's job |
| **Starfield / sprites** | own hardware colours | a `$D021` equal to a sprite colour reduces contrast | cosmetic, authoring concern |

Diagnostic recommendation for regression: run the fixed-HUD and scroll oracles
with a **strongly contrasting** probe palette (`$D020` = 6 blue, `$D021` = 1
white, `$D022`/`$D023` distinct) in addition to the black baseline, so any
future colour-matching assumption fails loudly.

---

## 17. Tests / probes performed

All against the already-built `build/shooter.prg`; no rebuild, no source change.

| Probe (scratchpad, disposable) | What it did | Result |
| --- | --- | --- |
| `probe2.py` | Background VICE (`-remotemonitor`, no focus steal); drove the menu into PLAYING; set a breakpoint on `rasterDisplayHook`; single-stepped the hook body dumping beam + `$D011` after every write; repeated for 6 more hook passes to see other fine phases; captured 4 screenshots (`01-as-is`, `02-white-border` via `> d020 01`, `03-d021-black` via `> d021 00`, `04-d021-white` via `> d021 01`); restored registers; killed the emulator. | Confirmed the per-frame `$D011` sequence `$17→$11→$71→$70\|f→$10\|f`, the invalid (BMM+ECM) mode at rasters ~62–70, and PLAYING registers `$D020=0 $D021=12 $D022=15 $D023=11 $D016=$D8 $D018=$1F`. |
| `analyze_png.py` | Row-by-row dominant-colour of each screenshot (`screenshot_y + 16 = raster`), nearest-match against the x64sc PAL palette. | Located border→HUD at raster 55, HUD→separator at raster 63, separator→terrain at raster 71, all four PNGs. Proved the raster 63–70 band is black in every PNG and invisible only when `$D021 = 0`. |
| `probe_topedge.py` | Earlier first attempt; superseded (used unsupported VICE `break … if` / `watch store` syntax). Left in scratchpad, not used for any conclusion. | n/a |

Reading-only evidence: `git log`/`git show` on `f6e9620`, `20eb3b5`;
`docs/scroll-edge-investigation.md`, `docs/fixed-hud-feasibility.md`,
`docs/fixed-hud-codex-worklog.md`, `docs/hud-architecture.md`;
`src/raster_scheduler.asm`, `src/main.asm` (`init`, `initBackground`,
`initFixedHud`, scroll constants), `tools/level_editor/engine_data.py`,
`src/generated/level1/stage_config.asm` vs `tools/level_editor/levels/level1/level.json`.

No engine timing/stress test was run (investigation only; the recommendation is
not implemented, so there is nothing new to stress-prove).

---

## 18. Temporary files created

All in the session scratchpad
`/private/tmp/claude-501/-Volumes-SSD-dev-C64-shooter-test/1ab2a81c-.../scratchpad/`
— **outside the repository**, not tracked, not committed:

| File | Purpose | Removed? |
| --- | --- | --- |
| `probe2.py` | working raster-split / screenshot probe | **Retained** as reusable instrumentation (non-repo). Harmless; can be deleted freely. |
| `analyze_png.py` | screenshot row/colour analyser | Retained (non-repo). |
| `probe_topedge.py` | superseded first attempt | Retained (non-repo); unused. |
| `topedge2/*.png`, `topedge2/monitor.log`, `topedge/*` | screenshots + monitor traces | Retained (non-repo) as evidence. |

No temporary file was created inside `/Volumes/SSD/dev/C64/shooter_test`. Nothing
needs restoring in the repo because nothing in the repo was touched.

---

## 19. Confirmation: no production changes remain

```
$ git diff --stat src/raster_scheduler.asm
 (no output — 0 lines)

$ git status --porcelain            # all pre-existing Task 1–3 work; none authored here
 M docs/level-editor-worklog.md
 M src/generated/level1/stage_charset.asm
 M src/generated/level1/stage_config.asm
 M src/generated/level1/stage_test.asm
 M src/generated/level1/stage_turrets.asm
 M src/generated/level1/stage_waves.asm
 M src/generated/level2/stage_charset.asm
 M src/generated/level2/stage_test.asm
 M src/main.asm
 M tools/check_fixed_hud_capture.py
 M tools/level_editor/…            (editor / tests from Tasks 1–3)
 M tools/make_stage_fixture.py
 M tools/vice_bottom_origin_probe.py
 ?? reports/terrain-authoring-blockers-and-native-tiles-report.md
 ?? reports/terrain-workshop-final-usability-pass.md
 ?? reports/hud-rsel-display-geometry-investigation.md   ← this report
 ?? tools/… (new test/tool files from Task 3)
```

- `src/raster_scheduler.asm` — **unmodified** (0 diff lines).
- No investigation instrumentation was added to any tracked file (no temporary
  probe writes, no `$D011`/`$D021` pokes in source — those were live-RAM-only).
- The only new file this task adds is this report.
- The `M` / `??` entries above are the uncommitted output of Tasks 1–3, present
  before this investigation began and unchanged by it. In particular
  `src/generated/level1/stage_config.asm`'s `TERRAIN_BACKGROUND_COLOUR = 12` is a
  **pre-existing** Task-3-era edit (`level.json` and HEAD still say `0`) — it is
  the reason a non-black `$D021` is now in front of the separator, and it was not
  made here.

---

## 20. Confirmation: no commit, no push

No `git commit`, `git push`, `git add`, tag, or branch operation was performed.
`HEAD` is still `3a72c13`. The working tree is exactly as handed over plus this
one report file.

---

## 21. The "a-ha"

**The artefact is a colour bug, not a geometry crisis, and the geometry is
already close to optimal for a top fixed-HUD design.**

- The top-edge band is the raster-split HUD's **invalid-mode (BMM+ECM) masked
  separator** at rasters 63–70. It has been emitted every frame since the fixed
  HUD landed (`20eb3b5`); it was invisible only because every level until now
  used `$D021 ≈ black`. Invalid-mode output is black by hardware definition, so
  the fix is to stop using invalid mode: render a **blank character row** there
  and it takes `$D021` automatically, for any palette.

- **RSEL=0's top crop is now dead weight.** It was added by `f6e9620` to hide the
  top scroll pop *before* the HUD split existed. The separator band that a later
  commit added for the HUD now masks that same seam. Only RSEL=0's **bottom**
  crop still earns its 4 pixels. You cannot drop RSEL=0 (bit affects both edges),
  but recognising this reframes the "too much lost top and bottom" complaint:
  the bottom costs a legitimate 4 px; the top's 20 px is 8 px real HUD + 12 px of
  arrangement overhead (4 redundant RSEL + 8 separator).

- **Matrix row 1 is already a spacer.** The player sees 1 pixel of it. Formally
  reserving it as a blank `$D021` row (a) fixes the artefact for every palette,
  (b) removes ~6–12 cycles/frame of invalid-mode writes, (c) costs **zero real
  gameplay area** (`VIEWPORT_ROWS` 23→22 just tells the truth), and (d) needs
  **no rewrite of any authored world coordinate** — turret and wave-trigger rows
  are world-anchored; only the boot viewport anchor moves one row, via a
  constant that is already parameterised.

Follow-up task: implement alternative **4a** (blank `$D021` spacer separator),
or **4b** if the freed row should become a second HUD line. Add a
strongly-contrasting probe palette to the fixed-HUD / scroll oracles so the next
colour-matching assumption fails loudly instead of silently. Separately fix the
`stage_config.asm` vs `level.json` background-colour drift (generated is ahead:
`12` vs `0`).
