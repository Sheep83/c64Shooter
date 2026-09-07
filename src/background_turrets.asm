.filenamespace test
// World-owned background characters. No object or VIC slot belongs to a body.
// Screen codes enter only through the existing safe row-install path; dynamic
// pixels publish before terrain fetches at frame start. See the turret worklog.
* = $8800
.const TURRET_COUNT = 3
// Private, runtime-modified glyphs. Relocated out of the editor-owned terrain
// namespace (160..223): they now sit between the diagnostic glyphs (224/225)
// and the starfield (240..251). Codes 226..237, bitmaps $3F10..$3F6F.
.const TURRET_GLYPH_BASE = 226
// Exported so the capture oracles locate the private glyph code/charset region
// without a hard-coded literal (KickAssembler exports labels, not .const).
.label TURRET_GLYPH_BASE_CODE = TURRET_GLYPH_BASE
.const TURRET_START_HEALTH = 3
.const TURRET_FIRE_INTERVAL = 100
.const TURRET_HIT_STYLE = 6
.const TURRET_DEAD_STYLE = 7
// Turrets are now STATIC emplacements: no per-frame player-relative aim glyph.
// One fixed body orientation is shown while alive/visible (style 6 = hit flash,
// style 7 = destroyed underlay still apply). turretArt style 4 = down-facing,
// the natural look for a background gun firing down the playfield. The genuine
// projectile aim is still computed at fire time inside spawnEnemyBulletAt.
.const TURRET_STATIC_STYLE = 4
// Static-turret fourth-colour pulse (see pulseTurretColour). Restrained
// white / red / yellow / red cycle; legal low-3 colours only, bit 3 ORed in at
// use so the cell stays multicolour. Easy to retune.
.const TURRET_PULSE_LEN = 4
.const TURRET_PULSE_INTERVAL = 8            // Gameplay frames between pulse steps.

// Editor-facing placement layer: character column and world character row.
// A body covers2x2 cells; its second row wraps modulo STAGE_LOGICAL_ROWS.
// Each placement sits on the interior of a M14 MACH housing in the redesigned
// bas-relief stage (stage_test.asm), so a turret reads as machinery emerging
// from the same hull surface: turret 0 in platform A, turret 1 in the section-B
// platform, turret 2 in the large section-D massif.
.var turretCols = List().add(17,29,13)
.var turretRows = List().add(13,29,57)
.if (turretCols.size() != TURRET_COUNT || turretRows.size() != TURRET_COUNT) {
    .error "Turret placement count does not match TURRET_COUNT"
}
.if (TURRET_GLYPH_BASE < TERRAIN_GLYPH_BASE + TERRAIN_GLYPH_NAMESPACE + 2) {
    .error "Turret private glyphs overlap the terrain namespace (160..223) or the diagnostic glyphs (224/225)"
}
.if (TURRET_GLYPH_BASE + TURRET_COUNT*4 > STAR_CHAR_BASE) {
    .error "Turret private glyphs overlap the starfield glyphs (240..251)"
}
.if (STAR_CHARSET + (TURRET_GLYPH_BASE + TURRET_COUNT*4)*8 > STAR_CHARSET + STAR_CHAR_BASE*8) {
    .error "Turret glyph bitmaps run into the starfield charset region"
}
.for (var t = 0; t < TURRET_COUNT; t++) {
    .if (turretCols.get(t) < 0 || turretCols.get(t) > 38 || turretRows.get(t) < 0 || turretRows.get(t) >= STAGE_LOGICAL_ROWS) {
        .error "Turret placement lies outside the wrapping character map"
    }
    .for (var other = 0; other < t; other++) {
        .for (var a = 0; a < 2; a++) {
            .for (var b = 0; b < 2; b++) {
                .if (mod(turretRows.get(t)+a, STAGE_LOGICAL_ROWS) == mod(turretRows.get(other)+b, STAGE_LOGICAL_ROWS)) {
                    .error "Prototype turrets must occupy different world character rows"
                }
            }
        }
    }
}

// Called after terrain charset initialization, before the initial matrix fill.
initBackgroundTurrets:
    lda #0
    ldx #TURRET_STATE_END - TURRET_STATE_BEGIN - 1
!clear:
    sta TURRET_STATE_BEGIN,x
    dex
    bpl !clear-
    lda #1
    sta TURRET_PULSE_TIMER                  // Step the pulse on the first gameplay frame.
    ldx #0
!turret:
    stx TURRET_INDEX
    lda #TURRET_START_HEALTH
    sta TURRET_HEALTH,x
    lda #4                                  // Start with a downward-facing barrel.
    sta TURRET_AIM,x
    sta TURRET_DESIRED_STYLE,x
    lda #$ff
    sta TURRET_SHOWN_STYLE,x
    lda turretWorldXLo,x
    sta TURRET_X_LO,x
    lda turretWorldXHi,x
    sta TURRET_X_HI,x
    lda #0
    sta TURRET_CELL_ROW
!row:
    ldx TURRET_INDEX
    lda turretWorldRow,x
    clc
    adc TURRET_CELL_ROW
    cmp #STAGE_LOGICAL_ROWS
    bcc !rowReady+
    sbc #STAGE_LOGICAL_ROWS
!rowReady:
    sta BG_LOGICAL_ROW
    jsr decodeStageCharacterRow             // Raw terrain only; the decoder knows nothing about turrets.
    ldx TURRET_INDEX
    lda turretWorldCol,x
    sta TURRET_COLUMN
    txa
    asl
    asl
    asl
    asl
    asl
    sta TURRET_GROUND_OFFSET
    lda TURRET_CELL_ROW
    asl
    asl
    asl
    asl
    clc
    adc TURRET_GROUND_OFFSET
    sta TURRET_GROUND_OFFSET
    lda #2
    sta TURRET_CELLS_LEFT
!cell:
    ldy TURRET_COLUMN
    lda BG_INCOMING_ROW,y
    pha
    and #31
    asl
    asl
    asl
    sta TEXT_SRC
    pla
    lsr
    lsr
    lsr
    lsr
    lsr
    clc
    adc #>STAR_CHARSET
    sta TEXT_SRC + 1
    ldx TURRET_GROUND_OFFSET
    ldy #0
!glyph:
    lda (TEXT_SRC),y
    sta turretGroundGlyphs,x
    inx
    iny
    cpy #8
    bne !glyph-
    stx TURRET_GROUND_OFFSET
    inc TURRET_COLUMN
    dec TURRET_CELLS_LEFT
    bne !cell-
    inc TURRET_CELL_ROW
    lda TURRET_CELL_ROW
    cmp #2
    bne !row-
    ldx TURRET_INDEX
    inx
    cpx #TURRET_COUNT
    beq !publish+
    jmp !turret-
!publish:
    jsr publishTurretGlyphs
    jsr publishTurretGlyphs
    jmp publishTurretGlyphs                 // All three are ready before the first gameplay frame.

// Tail of renderStageRowToScreen: TEXT_DST still addresses the installed row.
// This O(1) hook never changes BG_INCOMING_ROW or the metatile decoder. It
// overwrites two CHARACTER cells only. Colour RAM is the single stage-global
// TERRAIN_COLOUR_RAM value everywhere in the playfield, so a turret body - alive
// or destroyed - renders with that same fixed multicolour palette; the turret
// glyph bitmaps (turretArt / the cached underlay) are authored/kept as valid
// multicolour bitmaps. No turret-specific colour-RAM handling exists.
installTurretRow:
    ldx BG_LOGICAL_ROW
    lda turretRowGlyph,x
    beq !done+
    ldy turretRowColumn,x
    sta (TEXT_DST),y
    clc
    adc #1
    iny
    sta (TEXT_DST),y
!done:
    rts

// One dirty body per presented frame gives a fixed upper cost, independent of
// queued aim/hit/death changes. IRQ never reads these main-thread style bytes.
publishTurretGlyphs:
    ldx #0
!scan:
    lda TURRET_DESIRED_STYLE,x
    cmp TURRET_SHOWN_STYLE,x
    bne !publish+
    inx
    cpx #TURRET_COUNT
    bne !scan-
    rts
!publish:
    stx TURRET_PUBLISH_INDEX
    sta TURRET_PUBLISH_STYLE
    cmp #TURRET_DEAD_STYLE
    beq !ground+
    asl
    asl
    asl
    asl
    asl
    sta TEXT_SRC                            // turretArt is page-aligned,7 templates of32 bytes.
    lda #>turretArt
    sta TEXT_SRC + 1
    jmp !sourceReady+
!ground:
    txa
    asl
    asl
    asl
    asl
    asl
    sta TEXT_SRC                            // Underlay glyphs are also page-aligned.
    lda #>turretGroundGlyphs
    sta TEXT_SRC + 1
!sourceReady:
    txa
    asl
    asl
    asl
    asl
    asl
    tax                                     // Private destination offset: instance*32.
    ldy #0
    .for (var b = 0; b < 32; b++) {
        lda (TEXT_SRC),y
        sta STAR_CHARSET + TURRET_GLYPH_BASE*8 + b,x
        .if (b < 31) { iny }
    }
    ldx TURRET_PUBLISH_INDEX
    lda TURRET_PUBLISH_STYLE
    sta TURRET_SHOWN_STYLE,x
    inc TURRET_GLYPH_PUBLICATIONS
backgroundTurretGlyphsPublished:
    rts

// Derive positions from the PRESENTED origin/phase, after coarse finish and
// before the player's hitscan. No logical lifetime is tied to screen presence.
positionBackgroundTurrets:
    ldx #0
!turret:
    lda #0
    sta TURRET_VISIBLE,x
    lda turretWorldRow,x
    sec
    sbc SCROLL_ROW
    bcs !relative+
    adc #STAGE_LOGICAL_ROWS                 // Carry clear: add100 to a negative byte difference.
!relative:
    cmp #STAGE_LOGICAL_ROWS - 1
    beq !above+
    cmp #23
    bcs !next+
    asl
    asl
    asl
    clc
    adc #64
    jmp !fine+
!above:
    lda #56                                 // Top of a body whose bottom world row is the incoming row.
!fine:
    clc
    adc RASTER_DISPLAY_FINE
    sta TURRET_Y,x
    cmp #72
    bcc !next+
    cmp #232
    bcs !next+
    lda #1                                  // Combat only while the full16-pixel body is visible.
    sta TURRET_VISIBLE,x
!next:
    inx
    cpx #TURRET_COUNT
    bne !turret-
    rts

updateBackgroundTurrets:
    ldx #0
!turret:
    stx TURRET_INDEX
    lda TURRET_HEALTH,x
    bne !alive+
    lda #TURRET_DEAD_STYLE
    sta TURRET_DESIRED_STYLE,x
    jmp !next+
!alive:
    lda TURRET_VISIBLE,x
    bne !visible+
    lda #TURRET_FIRE_INTERVAL
    sta TURRET_FIRE_TIMER,x
    jmp !next+
!visible:
    // Static emplacement: no jsr aimBackgroundTurret here any more. The visible
    // body is a fixed orientation unless it is flashing from a hit. Removing the
    // per-frame six-way aim calc is a net CPU saving (aimBackgroundTurret cost
    // ~59..74 cyc per visible turret per frame). aimBackgroundTurret is kept in
    // the source, unreferenced, for the functional test and future use.
    lda TURRET_HIT_TIMER,x
    beq !staticStyle+
    dec TURRET_HIT_TIMER,x
    lda #TURRET_HIT_STYLE
    bne !style+
!staticStyle:
    lda #TURRET_STATIC_STYLE
!style:
    sta TURRET_DESIRED_STYLE,x
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
    // Hold fire when the playfield is already at the sprite-multiplexer
    // threshold. SORTED_COUNT (previous frame's render-eligible object count) of
    // 8 means a 9th sprite would force buildBatchSpriteSchedule to emit a LIVE
    // batch; if that batch lands low it keeps prepareBackgroundCoarse's
    // "all batches consumed" gate from admitting the coarse copy, deferring the
    // background scroll for as long as the extra object persists. A turret shot
    // is the projectile most able to sit low enough to cause this, so it yields
    // one fire cycle rather than add the tipping sprite. Enemy fire is unchanged.
    // -define TURRET_FIRE_NO_MITIGATION compiles this out for the wave-phase A/B.
    lda SORTED_COUNT
    cmp #8
    bcs !next+
#endif
    lda TURRET_X_LO,x
    clc
    adc #4                                  // Centre the existing8-pixel projectile on the16-pixel mount.
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
    cpx #TURRET_COUNT
    beq !done+
    jmp !turret-
!done:
    rts

// --- Routine: pulseTurretColour ------------------------------------------
// A cheap continuous pulse on the fourth multicolour colour (bit-pair 11) of
// the cells occupied by visible, alive turrets, so a static emplacement stays
// visually distinct from ordinary terrain. ONLY the four colour-RAM cells per
// visible turret are written; bit 3 stays set (cell remains multicolour); only
// legal low-3 colours are used. $D021/$D022/$D023 and all other colour RAM are
// untouched, so ordinary terrain colour is completely stable. Called once per
// gameplay frame right after positionBackgroundTurrets (fresh TURRET_Y), at
// ~raster 20 - well before any terrain colour-RAM badline fetch.
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
    lda TURRET_PULSE_COLOUR
    jsr paintTurretCells
!next:
    ldx TURRET_INDEX
    inx
    cpx #TURRET_COUNT
    bne !turret-
    rts

// Y = matrix row (2..24), X = turret index, A = colour byte.
// Writes the turret's four 2x2 colour-RAM cells. Clobbers A, X, Y, TEXT_SRC/DST.
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
    ldy turretWorldCol,x
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

// Six discrete directions; compare the horizontal origins with a24-pixel
// dead band. Subtraction includes the ninth X bit, never an8-bit wrap guess.
aimBackgroundTurret:
    lda #1                                  // Up-centre.
    sta TURRET_AIM,x
    lda OBJECT_Y
    cmp TURRET_Y,x
    bcc !horizontal+
    lda #4                                  // Down-centre.
    sta TURRET_AIM,x
!horizontal:
    lda OBJECT_X
    sec
    sbc TURRET_X_LO,x
    sta TURRET_DX
    lda OBJECT_X_MSB
    sbc TURRET_X_HI,x
    bmi !left+
    bne !right+
    lda TURRET_DX
    cmp #24
    bcc !done+
!right:
    inc TURRET_AIM,x
    rts
!left:
    cmp #$ff
    bne !farLeft+
    lda TURRET_DX
    cmp #$e8
    bcs !done+
!farLeft:
    dec TURRET_AIM,x
!done:
    rts

// Extend the existing nearest-Y hitscan result; high-bit tags are turret IDs,
// not logical object allocations. An enemy wins an exact-origin tie.
traceTurretCannon:
    ldx #0
!turret:
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
    cpx #TURRET_COUNT
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
    lda #4
    sta TURRET_HIT_TIMER,x
    lda #TURRET_HIT_STYLE
    sta TURRET_DESIRED_STYLE,x
!done:
    rts
!destroy:
    lda #TURRET_DEAD_STYLE
    sta TURRET_DESIRED_STYLE,x
    inc TURRET_DESTROYED
    jmp awardKillScore                       // Existing single kill reward, once per destroyed placement.

// Small per-game state; ground pixels below are only the12 replaced glyphs.
TURRET_STATE_BEGIN:
TURRET_HEALTH:          .fill TURRET_COUNT,0
TURRET_VISIBLE:         .fill TURRET_COUNT,0
TURRET_X_LO:            .fill TURRET_COUNT,0
TURRET_X_HI:            .fill TURRET_COUNT,0
TURRET_Y:               .fill TURRET_COUNT,0
TURRET_AIM:             .fill TURRET_COUNT,0
TURRET_FIRE_TIMER:      .fill TURRET_COUNT,0
TURRET_HIT_TIMER:       .fill TURRET_COUNT,0
TURRET_DESIRED_STYLE:   .fill TURRET_COUNT,0
TURRET_SHOWN_STYLE:     .fill TURRET_COUNT,0
TURRET_INDEX:           .byte 0
TURRET_DX:              .byte 0
TURRET_CELL_ROW:        .byte 0
TURRET_COLUMN:          .byte 0
TURRET_CELLS_LEFT:      .byte 0
TURRET_GROUND_OFFSET:  .byte 0
TURRET_PUBLISH_INDEX:  .byte 0
TURRET_PUBLISH_STYLE:  .byte 0
TURRET_SHOTS_FIRED:    .byte 0
TURRET_DESTROYED:      .byte 0
TURRET_GLYPH_PUBLICATIONS: .byte 0
BULLET_SPAWN_X_LO:     .byte 0
BULLET_SPAWN_X_HI:     .byte 0
BULLET_SPAWN_Y:        .byte 0
TURRET_CRAM_ROW:      .fill TURRET_COUNT,0   // Matrix row whose colour RAM currently holds this turret's
                                             // pulse colour (0 = none painted -> restore not needed).
TURRET_PULSE_TIMER:   .byte 0                // Frames until the next pulse-colour step.
TURRET_PULSE_INDEX:   .byte 0                // Index into turretPulseTable.
TURRET_PULSE_COLOUR:  .byte 0                // Current pulse colour byte (bit 3 set).
TURRET_PULSE_WRITE:   .byte 0                // paintTurretCells scratch.
TURRET_STATE_END:
.if (TURRET_STATE_END - TURRET_STATE_BEGIN > 128) {
    .error "Turret state clear loop exceeds signed-X range"
}
turretWorldCol: .fill TURRET_COUNT,turretCols.get(i)
turretWorldRow: .fill TURRET_COUNT,turretRows.get(i)
turretWorldXLo: .fill TURRET_COUNT,<(24+turretCols.get(i)*8)
turretWorldXHi: .fill TURRET_COUNT,>(24+turretCols.get(i)*8)

.align $100
turretRowGlyph:
.for (var row = 0; row < STAGE_LOGICAL_ROWS; row++) {
    .var code = 0
    .for (var t = 0; t < TURRET_COUNT; t++) {
        .if (row == turretRows.get(t)) { .eval code = TURRET_GLYPH_BASE+t*4 }
        .if (row == mod(turretRows.get(t)+1, STAGE_LOGICAL_ROWS)) { .eval code = TURRET_GLYPH_BASE+t*4+2 }
    }
    .byte code
}
turretRowColumn:
.for (var row = 0; row < STAGE_LOGICAL_ROWS; row++) {
    .var col = 0
    .for (var t = 0; t < TURRET_COUNT; t++) {
        .if (row == turretRows.get(t) || row == mod(turretRows.get(t)+1, STAGE_LOGICAL_ROWS)) { .eval col = turretCols.get(t) }
    }
    .byte col
}
.align $100
turretGroundGlyphs: .fill TURRET_COUNT*32,0
.align $100
// Seven 16x16 turret-body bitmaps, 4 glyphs each (TL,TR then BL,BR = 8 rows +
// 8 rows). Authored for GLOBAL multicolour text mode: the turret screen cells
// carry the same fixed TERRAIN_COLOUR_RAM value as the terrain, so these are
// 2-bit multicolour bitmaps against the stage palette (00 black, 01 $D022 dark
// grey, 10 $D023 light grey, 11 white). Common mount = white dome on a
// dark-grey base; only a small light-grey barrel nub differs per aim. Style 7
// (destroyed) is not a template - publishTurretGlyphs restores the cached
// underlying terrain glyphs for that instance instead.
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
    // Style4: down
    .byte $00,$00,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $00,$00,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$02,$02
    .byte $ff,$ff,$ff,$55,$55,$54,$80,$80
    // Style5: down-right
    .byte $00,$00,$0f,$3f,$ff,$ff,$ff,$ff
    .byte $00,$00,$f0,$fc,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$55,$55,$15,$00,$00
    .byte $ff,$ff,$ff,$55,$55,$54,$08,$08
    // Style6: hit (bright white flash)
    .byte $3c,$7e,$ff,$ff,$ff,$ff,$ff,$ff
    .byte $3c,$7e,$ff,$ff,$ff,$ff,$ff,$ff
    .byte $ff,$ff,$ff,$ff,$ff,$ff,$7e,$3c
    .byte $ff,$ff,$ff,$ff,$ff,$ff,$7e,$3c
turretArtEnd:
.if (turretArtEnd - turretArt != 7*32) {
    .error "Turret templates must contain seven16x16 bitmaps"
}
BACKGROUND_TURRETS_END:
.if (BACKGROUND_TURRETS_END > $a000) {
    .error "Background turret code/data overlaps BASIC ROM"
}
