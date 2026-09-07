.filenamespace test
// World-owned background characters. No object or VIC slot belongs to a body.
// Screen codes enter only through the existing safe row-install path; dynamic
// pixels publish before terrain fetches at frame start. See the turret worklog.
* = $8800
// ---------------------------------------------------------------------------
// STREAMING TURRET POOL - shared body glyphs.
//
// The AUTHORED turret list (TURRET_TOTAL + turretCols / turretRows) is generated
// by the level editor and is bounded only by the 8-bit streaming cursor
// (0..255). The ENGINE keeps a fixed pool of TURRET_POOL live slots.
//
// Concurrent visible capacity is NOT set by glyph codes: every live turret's
// 2x2 body cells point at ONE shared 4-glyph body set (codes 226..229, from
// turretArt style TURRET_STATIC_STYLE), published once. Per-LOCATION state
// (health, screen position, fire/hit timers, and the cached terrain screen
// codes the body covers) is tracked per slot. The hit flash is a colour-RAM
// change (pulseTurretColour). A destroyed turret writes the cached terrain
// codes back into its 2x2 cells once, then it is just terrain again.
//
// TURRET_POOL is therefore bounded only by the per-slot state array staying
// under the 128-byte signed-X clear-loop convention (15 * TURRET_POOL <= 128 =>
// TURRET_POOL <= 8). 8 comfortably exceeds the ~7 turrets that can be on screen
// at once (23-row aperture / >=4-row turret spacing + stream margin) and the 5
// that can be combat-visible at once; if the pool were ever full updateTurret-
// Stream just defers the extra turret a frame, it never corrupts. So this is a
// code-simplicity choice, not a rendering or performance limit.
//
// This file owns turret BEHAVIOUR and validates the authored placement data.
// ---------------------------------------------------------------------------
.const TURRET_STREAM_MARGIN = 3             // Coarse rows of lead when admitting / trailing when evicting.
.const TURRET_STREAM_WIN_LOW = 22 + TURRET_STREAM_MARGIN
.label TURRET_POOL_CODE = TURRET_POOL       // Exported for the capture oracles.
.label TURRET_TOTAL_CODE = TURRET_TOTAL

// ONE shared 16x16 turret body: codes TURRET_GLYPH_BASE..+3 (TL,TR,BL,BR),
// bitmaps at STAR_CHARSET + 226*8. Codes 230..239 are free.
.const TURRET_GLYPH_BASE = 226
.label TURRET_GLYPH_BASE_CODE = TURRET_GLYPH_BASE
.const TURRET_GLYPH_SPAN = 4                // shared body = 4 char codes, independent of turret count
.const TURRET_START_HEALTH = 3
.const TURRET_FIRE_INTERVAL = 100
.const TURRET_STATIC_STYLE = 4              // turretArt index used for the shared body (down-facing)
.const TURRET_HIT_FRAMES = 4               // gameplay frames a hit flash lasts
.const TURRET_HIT_CRAM = 10 | 8            // colour-RAM value while hit-flashing (light red, not in the pulse)
.const TURRET_PULSE_LEN = 4
.const TURRET_PULSE_INTERVAL = 8            // Gameplay frames between pulse steps.

// ---- compile-time validation ----------------------------------------------
.if (TURRET_POOL < 1 || TURRET_POOL > 8) {
    .error "TURRET_POOL must be 1..8 (15 * TURRET_POOL <= 128, the signed-X state clear loop)"
}
.if (15 * TURRET_POOL > 128) {
    .error "Per-slot turret state array exceeds the 128-byte signed-X clear loop"
}
.if (turretCols.size() != TURRET_TOTAL || turretRows.size() != TURRET_TOTAL) {
    .error "Generated turret placement count does not match TURRET_TOTAL"
}
.if (TURRET_GLYPH_BASE < TERRAIN_GLYPH_BASE + TERRAIN_GLYPH_NAMESPACE + 2) {
    .error "Turret private glyphs overlap the terrain namespace (160..223) or the diagnostic glyphs (224/225)"
}
.if (TURRET_GLYPH_BASE + TURRET_GLYPH_SPAN > STAR_CHAR_BASE) {
    .error "Shared turret body glyphs overlap the starfield glyphs (240..251)"
}
.if (STAR_CHARSET + (TURRET_GLYPH_BASE + TURRET_GLYPH_SPAN)*8 > STAR_CHARSET + STAR_CHAR_BASE*8) {
    .error "Shared turret body bitmap runs into the starfield charset region"
}
.for (var t = 0; t < TURRET_TOTAL; t++) {
    .if (turretCols.get(t) < 0 || turretCols.get(t) > 38 || turretRows.get(t) < 0 || turretRows.get(t) >= STAGE_LOGICAL_ROWS) {
        .error "Authored turret placement lies outside the wrapping character map"
    }
    .if (t > 0) {
        .if (turretRows.get(t - 1) - turretRows.get(t) < 2) {
            .error "Authored turret world rows must be sorted DESCENDING and at least 2 rows apart"
        }
    }
}

// ---------------------------------------------------------------------------
// initBackgroundTurrets - once per game, from initBackground before the initial
// matrix fill. Clears the pool + scratch, marks every authored turret alive,
// publishes the shared body glyph set, then admits any turret already inside the
// boot aperture so the initial row fill draws it.
// ---------------------------------------------------------------------------
initBackgroundTurrets:
    lda #0
    ldx #TURRET_STATE_END - TURRET_STATE_BEGIN - 1
!clearState:
    sta TURRET_STATE_BEGIN,x
    dex
    bpl !clearState-
    ldx #TURRET_SCRATCH_END - TURRET_SCRATCH_BEGIN - 1
!clearScratch:
    sta TURRET_SCRATCH_BEGIN,x
    dex
    bpl !clearScratch-
    lda #$ff
    ldx #TURRET_POOL - 1
!free:
    sta TURRET_SLOT_AUTH,x
    dex
    bpl !free-
.if (TURRET_TOTAL > 0) {
    lda #0
    ldx #((TURRET_TOTAL + 7) / 8) - 1
!clearBits:
    sta turretDestroyedBits,x
    dex
    bpl !clearBits-
}
    lda #1
    sta TURRET_PULSE_TIMER                  // Step the pulse on the first gameplay frame.
    jsr publishTurretGlyphs                 // Publish the ONE shared body glyph set.
    jmp updateTurretStream                  // Admit turrets already inside the boot aperture.

// ---------------------------------------------------------------------------
// updateTurretStream - once per gameplay frame, before positionBackgroundTurrets
// and before prepareBackgroundCoarse renders the newly-entering top row.
// ---------------------------------------------------------------------------
updateTurretStream:
.if (TURRET_TOTAL == 0) {
    rts
}
.if (TURRET_TOTAL > 0) {
    lda TURRET_STREAM_REWIND
    beq !afterRewind+
    lda #0
    sta TURRET_STREAM_REWIND
    sta TURRET_STREAM_CURSOR                // Stage wrapped: re-stream every authored turret this loop.
!afterRewind:
    // --- evict pass: free any slot whose body has left the aperture + margin
    ldx #TURRET_POOL - 1
!evict:
    lda TURRET_SLOT_AUTH,x
    bmi !evictNext+
    stx TURRET_INDEX
    lda TURRET_SLOT_ROW_LO,x                // rel(16) = (slotRow(16) - SCROLL_ROW(16)) mod SLR
    sec
    sbc SCROLL_ROW
    sta TURRET_REL_LO
    lda TURRET_SLOT_ROW_HI,x
    sbc SCROLL_ROW_HI
    sta TURRET_REL_HI
    bcs !evictRel+
    lda TURRET_REL_LO
    clc
    adc #<STAGE_LOGICAL_ROWS
    sta TURRET_REL_LO
    lda TURRET_REL_HI
    adc #>STAGE_LOGICAL_ROWS
    sta TURRET_REL_HI
!evictRel:
    jsr turretRelInWindow                   // carry set => still near the aperture
    ldx TURRET_INDEX
    bcs !evictNext+
    lda TURRET_HEALTH,x                     // leaving: if it died on screen, remember that
    bne !evictFree+
    lda TURRET_SLOT_AUTH,x
    jsr markTurretDestroyed
    ldx TURRET_INDEX
!evictFree:
    lda #$ff
    sta TURRET_SLOT_AUTH,x
!evictNext:
    dex
    bpl !evict-
    // --- admit pass: fill free slots from the sorted authored list
!admit:
    lda TURRET_STREAM_CURSOR
    cmp #TURRET_TOTAL
    bcs !streamDone+                        // cursor past the last authored turret this loop
    tay
    clc                                     // reached(16) = turretAuthRow[cursor] + MARGIN
    lda turretAuthRowLo,y
    adc #TURRET_STREAM_MARGIN
    sta TURRET_REL_LO
    lda turretAuthRowHi,y
    adc #0
    sta TURRET_REL_HI
    lda TURRET_REL_LO                       // carry set => SCROLL_ROW <= turretAuthRow[cursor] + MARGIN
    cmp SCROLL_ROW
    lda TURRET_REL_HI
    sbc SCROLL_ROW_HI
    bcc !streamDone+                        // not descended to this turret yet - wait
    ldx #TURRET_POOL - 1
!findFree:
    lda TURRET_SLOT_AUTH,x
    bmi !gotFree+
    dex
    bpl !findFree-
    jmp !streamDone+                        // pool full - retry next frame (never corrupts)
!gotFree:
    ldy TURRET_STREAM_CURSOR
    jsr admitTurretSlot                     // x = free slot, y = authored index
    inc TURRET_STREAM_CURSOR
    jmp !admit-
!streamDone:
    rts
}

// carry set = rel is inside the keep window (visible + margin, or approaching
// within margin). rel in TURRET_REL_LO/HI (0 .. STAGE_LOGICAL_ROWS-1).
turretRelInWindow:
    lda TURRET_REL_HI
    bne !approaching+
    lda TURRET_REL_LO
    cmp #TURRET_STREAM_WIN_LOW + 1
    bcc !keep+                              // rel <= visible+margin
!approaching:
    lda TURRET_REL_LO                       // rel >= STAGE_LOGICAL_ROWS - MARGIN ? (16-bit)
    cmp #<(STAGE_LOGICAL_ROWS - TURRET_STREAM_MARGIN)
    lda TURRET_REL_HI
    sbc #>(STAGE_LOGICAL_ROWS - TURRET_STREAM_MARGIN)
    bcs !keep+
    clc
    rts
!keep:
    sec
    rts

// a = authored turret index. set its destroyed bit. clobbers a, x.
markTurretDestroyed:
    pha
    and #7
    tax
    lda HW_BIT_MASK,x
    sta TURRET_BIT_SCRATCH
    pla
    lsr
    lsr
    lsr
    tax
    lda turretDestroyedBits,x
    ora TURRET_BIT_SCRATCH
    sta turretDestroyedBits,x
    rts

// a = authored turret index. carry set if that turret is marked destroyed.
// clobbers a, x.
turretIsDestroyed:
    pha
    and #7
    tax
    lda HW_BIT_MASK,x
    sta TURRET_BIT_SCRATCH
    pla
    lsr
    lsr
    lsr
    tax
    lda turretDestroyedBits,x
    and TURRET_BIT_SCRATCH
    bne !yes+
    clc
    rts
!yes:
    sec
    rts

// x = free slot, y = authored turret index. Copy geometry + seed per-slot state.
// A live turret also caches the terrain screen codes its body covers.
admitTurretSlot:
    lda turretAuthRowLo,y
    sta TURRET_SLOT_ROW_LO,x
    lda turretAuthRowHi,y
    sta TURRET_SLOT_ROW_HI,x
    lda turretAuthRow2Lo,y
    sta TURRET_SLOT_ROW2_LO,x
    lda turretAuthRow2Hi,y
    sta TURRET_SLOT_ROW2_HI,x
    lda turretAuthCol,y
    sta TURRET_SLOT_COL,x
    lda turretAuthXLo,y
    sta TURRET_X_LO,x
    lda turretAuthXHi,y
    sta TURRET_X_HI,x
    tya
    sta TURRET_SLOT_AUTH,x
    lda #0
    sta TURRET_VISIBLE,x
    sta TURRET_FIRE_TIMER,x
    sta TURRET_HIT_TIMER,x
    sta TURRET_CRAM_ROW,x
    sta TURRET_Y,x
    stx TURRET_INDEX
    lda TURRET_SLOT_AUTH,x
    jsr turretIsDestroyed                   // carry set => this authored turret is already dead
    ldx TURRET_INDEX
    bcs !admitDead+
    lda #TURRET_START_HEALTH
    sta TURRET_HEALTH,x
    lda #0
    sta TURRET_DEAD_RESTORED,x
    stx TURRET_INDEX
    jsr cacheTurretGroundCodes             // for the restore-terrain-on-death poke
    ldx TURRET_INDEX
    rts
!admitDead:
    lda #0
    sta TURRET_HEALTH,x                     // installTurretRow leaves the freshly-decoded terrain
    lda #1
    sta TURRET_DEAD_RESTORED,x              // nothing to poke: the row re-render shows terrain
    rts

// x = slot. Decode the two logical rows the 2x2 body covers and cache the 4
// terrain SCREEN CODES (not bitmaps) into turretGroundCodes + slot*4, so a
// destroyed turret can put back exactly the terrain it replaced.
cacheTurretGroundCodes:
    stx TURRET_INDEX
    lda TURRET_SLOT_ROW_LO,x
    sta BG_LOGICAL_ROW
    lda TURRET_SLOT_ROW_HI,x
    sta BG_LOGICAL_ROW_HI
    jsr decodeStageCharacterRow            // Raw terrain only; the decoder knows nothing about turrets.
    lda TURRET_INDEX
    asl
    asl
    sta TURRET_GROUND_OFFSET               // slot * 4
    ldx TURRET_INDEX
    ldy TURRET_SLOT_COL,x
    ldx TURRET_GROUND_OFFSET
    lda BG_INCOMING_ROW,y
    sta turretGroundCodes,x
    iny
    lda BG_INCOMING_ROW,y
    sta turretGroundCodes+1,x
    ldx TURRET_INDEX
    lda TURRET_SLOT_ROW2_LO,x
    sta BG_LOGICAL_ROW
    lda TURRET_SLOT_ROW2_HI,x
    sta BG_LOGICAL_ROW_HI
    jsr decodeStageCharacterRow
    ldx TURRET_INDEX
    ldy TURRET_SLOT_COL,x
    ldx TURRET_GROUND_OFFSET
    lda BG_INCOMING_ROW,y
    sta turretGroundCodes+2,x
    iny
    lda BG_INCOMING_ROW,y
    sta turretGroundCodes+3,x
    ldx TURRET_INDEX
    rts

// x = slot. Put the cached terrain codes AND the fixed terrain colour RAM back
// into the turret's 2x2 body cells, atomically. Called from publishTurretGlyphs
// (frame start, beam still in the border) the frame AFTER a live turret dies, so
// the write never tears a partly-fetched row. The matrix row is derived from
// SCROLL_ROW (stable at that point), not the possibly-stale TURRET_Y. The cells
// then scroll with the terrain; any later row re-render leaves the freshly-
// decoded terrain (installTurretRow skips dead slots). Zeros TURRET_CRAM_ROW so
// pulseTurretColour will not touch these cells again.
restoreDeadTurretCells:
    stx TURRET_INDEX
    lda #0
    sta TURRET_CRAM_ROW,x
    lda TURRET_SLOT_ROW_LO,x                // rel(16) = (slotRow - SCROLL_ROW) mod SLR
    sec
    sbc SCROLL_ROW
    sta TURRET_REL_LO
    lda TURRET_SLOT_ROW_HI,x
    sbc SCROLL_ROW_HI
    sta TURRET_REL_HI
    bcs !rdRel+
    lda TURRET_REL_LO
    clc
    adc #<STAGE_LOGICAL_ROWS
    sta TURRET_REL_LO
    lda TURRET_REL_HI
    adc #>STAGE_LOGICAL_ROWS
    sta TURRET_REL_HI
!rdRel:
    lda TURRET_REL_HI
    bne !rdDone+                            // rel >= 256 -> body not on screen
    lda TURRET_REL_LO
    cmp #23
    bcs !rdDone+                            // body below the aperture
    clc
    adc #1                                  // top body matrix row = rel + 1  (1..23)
    sta TURRET_CELL_ROW
    lda TURRET_INDEX
    asl
    asl
    sta TURRET_GROUND_OFFSET               // slot * 4
    lda #0
    jsr restoreDeadTurretRow               // top body row: ground codes [0][1]
    inc TURRET_CELL_ROW
    lda TURRET_CELL_ROW
    cmp #25
    bcs !rdDone+
    lda #2
    jsr restoreDeadTurretRow               // bottom body row: ground codes [2][3]
!rdDone:
    ldx TURRET_INDEX
    rts

// a = ground-code pair offset (0 or 2). TURRET_INDEX = slot, TURRET_CELL_ROW =
// matrix row, TURRET_GROUND_OFFSET = slot*4. Writes the two cached terrain codes
// to screen RAM and TERRAIN_COLOUR_RAM to the two colour-RAM cells at that row,
// turret columns COL / COL+1.
restoreDeadTurretRow:
    clc
    adc TURRET_GROUND_OFFSET
    sta TURRET_PULSE_WRITE                 // TURRET_PULSE_WRITE = turretGroundCodes index
    ldx TURRET_CELL_ROW
    lda starRowLo,x
    sta TEXT_SRC
    lda starRowHi,x
    sta TEXT_SRC + 1
    lda cramRowLo,x
    sta TEXT_DST
    lda cramRowHi,x
    sta TEXT_DST + 1
    ldx TURRET_INDEX
    ldy TURRET_SLOT_COL,x                  // Y = left column
    ldx TURRET_PULSE_WRITE                 // X = turretGroundCodes index
    lda turretGroundCodes,x
    sta (TEXT_SRC),y
    lda #TERRAIN_COLOUR_RAM
    sta (TEXT_DST),y
    iny
    inx
    lda turretGroundCodes,x
    sta (TEXT_SRC),y
    lda #TERRAIN_COLOUR_RAM
    sta (TEXT_DST),y
    rts

// Tail of renderStageRowToScreen: TEXT_DST still addresses the installed row.
// BG_LOGICAL_ROW(16) is the world character row just installed. Match it against
// each occupied ALIVE pool slot's two body rows and write the SHARED body codes
// (226..229). Dead slots are skipped - the decoded terrain stands. At most one
// slot matches per row (authored rows are >= 2 apart).
installTurretRow:
    ldx #TURRET_POOL - 1
!scan:
    lda TURRET_SLOT_AUTH,x
    bmi !nextT+
    lda TURRET_HEALTH,x
    beq !nextT+                             // dead: leave the freshly-decoded terrain
    lda BG_LOGICAL_ROW
    cmp TURRET_SLOT_ROW_LO,x
    bne !notTop+
    lda BG_LOGICAL_ROW_HI
    cmp TURRET_SLOT_ROW_HI,x
    bne !notTop+
    lda #TURRET_GLYPH_BASE                  // top body -> shared TL / TR
    jmp !install+
!notTop:
    lda BG_LOGICAL_ROW
    cmp TURRET_SLOT_ROW2_LO,x
    bne !nextT+
    lda BG_LOGICAL_ROW_HI
    cmp TURRET_SLOT_ROW2_HI,x
    bne !nextT+
    lda #TURRET_GLYPH_BASE + 2              // bottom body -> shared BL / BR
!install:
    pha
    lda TURRET_SLOT_COL,x
    tay
    pla
    sta (TEXT_DST),y
    clc
    adc #1
    iny
    sta (TEXT_DST),y
    rts
!nextT:
    dex
    bpl !scan-
    rts

// Publish the ONE shared turret body glyph set (codes TURRET_GLYPH_BASE..+3)
// from turretArt style TURRET_STATIC_STYLE. Static bitmaps: every live turret
// points here regardless of count. The hit flash is colour-RAM only. Called at
// frame start (beam still in the border) from gameLoop, and once from init.
// This is also the SAFE window to revert a just-killed turret's 2x2 cells back
// to terrain (updateBackgroundTurrets only flags the kill; poking screen RAM
// mid-frame would tear a partly-fetched row).
publishTurretGlyphs:
    ldx #31
!copy:
    lda turretArt + TURRET_STATIC_STYLE*32,x
    sta STAR_CHARSET + TURRET_GLYPH_BASE*8,x
    dex
    bpl !copy-
    inc TURRET_GLYPH_PUBLICATIONS
    ldx #TURRET_POOL - 1
!deadScan:
    lda TURRET_SLOT_AUTH,x
    bmi !deadNext+
    lda TURRET_HEALTH,x
    bne !deadNext+
    lda TURRET_DEAD_RESTORED,x
    bne !deadNext+
    stx TURRET_INDEX
    jsr restoreDeadTurretCells
    ldx TURRET_INDEX
    lda #1
    sta TURRET_DEAD_RESTORED,x
!deadNext:
    dex
    bpl !deadScan-
backgroundTurretGlyphsPublished:
    rts

// Derive positions from the PRESENTED origin/phase, after coarse finish and
// before the player's hitscan. No logical lifetime is tied to screen presence.
positionBackgroundTurrets:
    ldx #TURRET_POOL - 1
!turret:
    lda #0
    sta TURRET_VISIBLE,x
    lda TURRET_SLOT_AUTH,x
    bmi !next+
    lda TURRET_SLOT_ROW_LO,x                // rel(16) = (slotRow(16) - SCROLL_ROW(16)) mod SLR
    sec
    sbc SCROLL_ROW
    sta TURRET_REL_LO
    lda TURRET_SLOT_ROW_HI,x
    sbc SCROLL_ROW_HI
    sta TURRET_REL_HI
    bcs !relative+
    lda TURRET_REL_LO
    clc
    adc #<STAGE_LOGICAL_ROWS
    sta TURRET_REL_LO
    lda TURRET_REL_HI
    adc #>STAGE_LOGICAL_ROWS
    sta TURRET_REL_HI
!relative:
    lda TURRET_REL_HI                       // rel == STAGE_LOGICAL_ROWS - 1: body's bottom row is the
    cmp #>(STAGE_LOGICAL_ROWS - 1)          // incoming row, so its top is one row above the aperture.
    bne !notAbove+
    lda TURRET_REL_LO
    cmp #<(STAGE_LOGICAL_ROWS - 1)
    bne !notAbove+
    lda #56
    jmp !fine+
!notAbove:
    lda TURRET_REL_HI
    bne !next+                              // rel >= 256 -> far below the aperture; not visible.
    lda TURRET_REL_LO
    cmp #23
    bcs !next+
    asl
    asl
    asl
    clc
    adc #64
!fine:
    clc
    adc RASTER_DISPLAY_FINE
    sta TURRET_Y,x
    cmp #72
    bcc !next+
    cmp #232
    bcs !next+
    lda #1                                  // Combat only while the full 16-pixel body is visible.
    sta TURRET_VISIBLE,x
!next:
    dex
    bpl !turret-
    rts

updateBackgroundTurrets:
    ldx #0
!turret:
    stx TURRET_INDEX
    lda TURRET_SLOT_AUTH,x
    bmi !next+
    lda TURRET_HEALTH,x
    bne !alive+
    jmp !next+                              // dead: publishTurretGlyphs reverts the cells at frame start
!alive:
    lda TURRET_VISIBLE,x
    bne !visible+
    lda #TURRET_FIRE_INTERVAL
    sta TURRET_FIRE_TIMER,x
    jmp !next+
!visible:
    lda TURRET_HIT_TIMER,x                  // hit flash is decayed here; the colour is applied in pulseTurretColour
    beq !fireCheck+
    dec TURRET_HIT_TIMER,x
!fireCheck:
    lda TURRET_FIRE_TIMER,x
    beq !fire+
    dec TURRET_FIRE_TIMER,x
    jmp !next+
!fire:
    lda #TURRET_FIRE_INTERVAL
    sta TURRET_FIRE_TIMER,x
    lda TURRET_Y,x
    cmp #88                                 // Give the HUD boundary a clear entry margin.
    bcc !next+
    cmp #201
    bcs !next+
    clc
    adc #24
    cmp OBJECT_Y
    bcs !next+                              // Existing bullets fly downward: hold fire when player is above/near.
    lda PLAYER_STATE
    bne !next+
#if !TURRET_FIRE_NO_MITIGATION
    lda SORTED_COUNT
    cmp #8
    bcs !next+
#endif
    lda TURRET_X_LO,x
    clc
    adc #4                                  // Centre the existing 8-pixel projectile on the 16-pixel mount.
    sta BULLET_SPAWN_X_LO
    lda TURRET_X_HI,x
    adc #0
    sta BULLET_SPAWN_X_HI
    lda TURRET_Y,x
    clc
    adc #12
    sta BULLET_SPAWN_Y
    jsr spawnEnemyBulletAt                  // Same cap, allocator, aim quantisation and projectile lifecycle.
    bcs !next+
    inc TURRET_SHOTS_FIRED
!next:
    ldx TURRET_INDEX
    inx
    cpx #TURRET_POOL
    beq !done+
    jmp !turret-
!done:
    rts

// --- Routine: pulseTurretColour ------------------------------------------
// Cheap continuous pulse on the fourth multicolour colour of the cells occupied
// by visible, alive turrets. A hit-flashing turret uses TURRET_HIT_CRAM instead
// of the pulse colour for TURRET_HIT_FRAMES frames. Only the four colour-RAM
// cells per visible turret are written; $D021/$D022/$D023 and every other colour
// RAM cell are untouched.
pulseTurretColour:
    dec TURRET_PULSE_TIMER
    bne !phaseReady+
    lda #TURRET_PULSE_INTERVAL
    sta TURRET_PULSE_TIMER
    ldx TURRET_PULSE_INDEX
    inx
    cpx #TURRET_PULSE_LEN
    bcc !storeIdx+
    ldx #0
!storeIdx:
    stx TURRET_PULSE_INDEX
!phaseReady:
    ldx TURRET_PULSE_INDEX
    lda turretPulseTable,x
    ora #$08                               // Keep the multicolour selector bit set.
    sta TURRET_PULSE_COLOUR

    ldx #0
!turret:
    stx TURRET_INDEX
    lda TURRET_SLOT_AUTH,x
    bmi !next+
    lda TURRET_VISIBLE,x
    beq !restoreOnly+
    lda TURRET_HEALTH,x
    beq !restoreOnly+
    lda TURRET_Y,x                          // matrix row of the turret's top-left cell:
    sec
    sbc RASTER_DISPLAY_FINE                 //   (TURRET_Y - fine - 64) / 8 + 1  == relative row + 1
    sbc #63                                 // carry still set from the previous sbc.
    lsr
    lsr
    lsr
    clc
    adc #1
    bne !haveRow+                           // (a visible turret is always matrix row >= 2)
!restoreOnly:
    lda #0                                  // Nothing to paint this frame: only restore the old cells.
!haveRow:
    cmp TURRET_CRAM_ROW,x
    beq !samePaint+
    pha                                    // New target matrix row (0 = none).
    ldy TURRET_CRAM_ROW,x
    beq !noOldRow+
    lda #TERRAIN_COLOUR_RAM                // Return the vacated cells to the fixed terrain colour.
    jsr paintTurretCells
!noOldRow:
    pla
    sta TURRET_CRAM_ROW,x
!samePaint:
    ldy TURRET_CRAM_ROW,x
    beq !next+
    ldy TURRET_HIT_TIMER,x
    beq !usePulse+
    lda #TURRET_HIT_CRAM                   // hit flash: colour-RAM only, no glyph swap
    bne !doPaint+
!usePulse:
    lda TURRET_PULSE_COLOUR
!doPaint:
    ldy TURRET_CRAM_ROW,x
    jsr paintTurretCells
!next:
    ldx TURRET_INDEX
    inx
    cpx #TURRET_POOL
    bne !turret-
    rts

// Y = matrix row (2..24), X = slot, A = colour byte. Writes the turret's four
// 2x2 colour-RAM cells. Clobbers A, X, Y, TEXT_SRC/DST.
paintTurretCells:
    sta TURRET_PULSE_WRITE
    lda cramRowLo,y
    sta TEXT_SRC
    lda cramRowHi,y
    sta TEXT_SRC + 1
    iny
    lda cramRowLo,y
    sta TEXT_DST
    lda cramRowHi,y
    sta TEXT_DST + 1
    ldx TURRET_INDEX
    ldy TURRET_SLOT_COL,x
    lda TURRET_PULSE_WRITE
    sta (TEXT_SRC),y
    sta (TEXT_DST),y
    iny
    sta (TEXT_SRC),y
    sta (TEXT_DST),y
    rts

turretPulseTable:
    .byte 1, 2, 7, 2                        // white, red, yellow, red  (TURRET_PULSE_LEN entries)

// $D800 + row*40 for matrix rows 0..25 (25 is one past the last visible row,
// referenced only as the "row+1" bottom half of a turret at the aperture edge).
cramRowLo: .fill 26, <($d800 + i*40)
cramRowHi: .fill 26, >($d800 + i*40)

// Extend the existing nearest-Y hitscan result; high-bit tags are pool slot
// IDs. An enemy wins an exact-origin tie.
traceTurretCannon:
    ldx #0
!turret:
    lda TURRET_SLOT_AUTH,x
    bmi !next+
    lda TURRET_HEALTH,x
    beq !next+
    lda TURRET_VISIBLE,x
    beq !next+
    lda TURRET_Y,x
    cmp OBJECT_Y
    bcs !next+
    cmp HITSCAN_TARGET_Y
    bcc !next+
    beq !next+
    lda HITSCAN_X_LO
    sec
    sbc TURRET_X_LO,x
    sta HITSCAN_DELTA_LO
    lda HITSCAN_X_MSB
    sbc TURRET_X_HI,x
    bne !next+
    lda HITSCAN_DELTA_LO
    cmp #16
    bcs !next+
    lda TURRET_Y,x
    sta HITSCAN_TARGET_Y
    txa
    ora #$80
    sta HITSCAN_TARGET
!next:
    inx
    cpx #TURRET_POOL
    bne !turret-
    rts

hitCannonTarget:
    txa
    bmi !turret+
    jmp damageEnemy                         // Preserve the existing enemy damage/health-sprite path.
!turret:
    and #$7f
    tax
    lda TURRET_HEALTH,x
    beq !done+
    dec TURRET_HEALTH,x
    beq !destroy+
    lda #TURRET_HIT_FRAMES
    sta TURRET_HIT_TIMER,x                  // colour-RAM flash starts next pulseTurretColour
!done:
    rts
!destroy:
    inc TURRET_DESTROYED
.if (TURRET_TOTAL > 0) {
    lda TURRET_SLOT_AUTH,x                  // keep this authored turret dead across evict / re-admit / loop
    jsr markTurretDestroyed
}
    jmp awardKillScore                       // Existing single kill reward, once per destroyed placement.
                                            // updateBackgroundTurrets restores the covered terrain next frame.

// --- per-slot state (one signed-X clear block) ----------------------------
TURRET_STATE_BEGIN:
TURRET_HEALTH:          .fill TURRET_POOL,0
TURRET_VISIBLE:         .fill TURRET_POOL,0
TURRET_X_LO:            .fill TURRET_POOL,0
TURRET_X_HI:            .fill TURRET_POOL,0
TURRET_Y:               .fill TURRET_POOL,0
TURRET_FIRE_TIMER:      .fill TURRET_POOL,0
TURRET_HIT_TIMER:       .fill TURRET_POOL,0
TURRET_DEAD_RESTORED:   .fill TURRET_POOL,0    // 1 once the covered terrain codes are poked back
TURRET_CRAM_ROW:        .fill TURRET_POOL,0
TURRET_SLOT_AUTH:       .fill TURRET_POOL,0    // authored index in this slot; $ff = free
TURRET_SLOT_ROW_LO:     .fill TURRET_POOL,0
TURRET_SLOT_ROW_HI:     .fill TURRET_POOL,0
TURRET_SLOT_ROW2_LO:    .fill TURRET_POOL,0
TURRET_SLOT_ROW2_HI:    .fill TURRET_POOL,0
TURRET_SLOT_COL:        .fill TURRET_POOL,0
TURRET_STATE_END:
.if (TURRET_STATE_END - TURRET_STATE_BEGIN > 128) {
    .error "Turret per-slot state array exceeds the signed-X clear loop"
}

// --- scratch / counters (second clear block) -----------------------------
TURRET_SCRATCH_BEGIN:
TURRET_INDEX:           .byte 0
TURRET_CELL_ROW:        .byte 0
TURRET_GROUND_OFFSET:   .byte 0
TURRET_SHOTS_FIRED:     .byte 0
TURRET_DESTROYED:       .byte 0
TURRET_GLYPH_PUBLICATIONS: .byte 0
BULLET_SPAWN_X_LO:     .byte 0
BULLET_SPAWN_X_HI:     .byte 0
BULLET_SPAWN_Y:        .byte 0
TURRET_PULSE_TIMER:   .byte 0
TURRET_PULSE_INDEX:   .byte 0
TURRET_PULSE_COLOUR:  .byte 0
TURRET_PULSE_WRITE:   .byte 0
TURRET_REL_LO:        .byte 0
TURRET_REL_HI:        .byte 0
TURRET_STREAM_CURSOR: .byte 0
TURRET_STREAM_REWIND: .byte 0
TURRET_BIT_SCRATCH:   .byte 0
TURRET_SCRATCH_END:
.if (TURRET_SCRATCH_END - TURRET_SCRATCH_BEGIN > 128) {
    .error "Turret scratch block exceeds the signed-X clear loop"
}

// Authored placement LUTs, materialised at assembly time from the generated
// list (sorted DESCENDING by world row - streaming-cursor order). World rows are
// 16-bit. turretAuthRow2* is the body's second (bottom) character row =
// (row+1) mod STAGE_LOGICAL_ROWS, precomputed so no runtime modulo is needed.
// turretAuthCol / turretAuthRowLo / turretAuthRowHi are kept contiguous and one
// byte each so the capture oracle can dump [cols(N), rowsLo(N)] + [rowsHi(N)].
turretAuthCol:     .fill TURRET_TOTAL, turretCols.get(i)
turretAuthRowLo:   .fill TURRET_TOTAL, <turretRows.get(i)
turretAuthRowHi:   .fill TURRET_TOTAL, >turretRows.get(i)
turretAuthRow2Lo:  .fill TURRET_TOTAL, <mod(turretRows.get(i) + 1, STAGE_LOGICAL_ROWS)
turretAuthRow2Hi:  .fill TURRET_TOTAL, >mod(turretRows.get(i) + 1, STAGE_LOGICAL_ROWS)
turretAuthXLo:     .fill TURRET_TOTAL, <(24 + turretCols.get(i)*8)
turretAuthXHi:     .fill TURRET_TOTAL, >(24 + turretCols.get(i)*8)

turretDestroyedBits:
.if (TURRET_TOTAL > 0) { .fill (TURRET_TOTAL + 7) / 8, 0 }

// Per-slot cached terrain SCREEN CODES for the 2x2 body (TL,TR,BL,BR), used by
// restoreDeadTurretCells. slot*4 addressing, no page alignment needed.
turretGroundCodes: .fill TURRET_POOL * 4, 0

.align $100
// Seven 16x16 turret-body bitmaps, 4 glyphs each (TL,TR then BL,BR). 2-bit
// multicolour bitmaps against the stage palette. Only style TURRET_STATIC_STYLE
// (4, down-facing) is used by the shared-glyph renderer; the rest are retained
// for the functional tests and possible future use. The hit flash is colour-RAM
// only, and a destroyed turret shows the cached terrain codes.
turretArt:
    // Style0: up-left
    .byte $20,$20,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $00,$00,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$00,$00
    .byte $ff,$ff,$ff,$55,$55,$54,$00,$00
    // Style1: up
    .byte $02,$02,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $80,$80,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$00,$00
    .byte $ff,$ff,$ff,$55,$55,$54,$00,$00
    // Style2: up-right
    .byte $00,$00,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $08,$08,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$00,$00
    .byte $ff,$ff,$ff,$55,$55,$54,$00,$00
    // Style3: down-left
    .byte $00,$00,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $00,$00,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$20,$20
    .byte $ff,$ff,$ff,$55,$55,$54,$00,$00
    // Style4: down  (TURRET_STATIC_STYLE - the shared body)
    .byte $00,$00,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $00,$00,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$02,$02
    .byte $ff,$ff,$ff,$55,$55,$54,$80,$80
    // Style5: down-right
    .byte $00,$00,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $00,$00,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$00,$00
    .byte $ff,$ff,$ff,$55,$55,$54,$08,$08
    // Style6: hit (retained; unused by the shared-glyph renderer)
    .byte $3c,$7e,$ff,$ff,$ff,$ff,$ff,$ff
    .byte $3c,$7e,$ff,$ff,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$ff,$ff,$ff,$7e,$3c
    .byte $ff,$ff,$ff,$ff,$ff,$ff,$7e,$3c
turretArtEnd:
.if (turretArtEnd - turretArt != 7*32) {
    .error "Turret templates must contain seven 16x16 bitmaps"
}
BACKGROUND_TURRETS_END:
.if (BACKGROUND_TURRETS_END > $a000) {
    .error "Background turret code/data overlaps BASIC ROM"
}
