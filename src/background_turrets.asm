.filenamespace test
// World-owned background characters. No object or VIC slot belongs to a body.
// Screen codes enter only through the existing safe row-install path; dynamic
// pixels publish before terrain fetches at frame start. See the turret worklog.
* = $8800
.const TURRET_COUNT = 3
.const TURRET_GLYPH_BASE = 200
.const TURRET_START_HEALTH = 3
.const TURRET_FIRE_INTERVAL = 100
.const TURRET_HIT_STYLE = 6
.const TURRET_DEAD_STYLE = 7

// Editor-facing placement layer: character column and world character row.
// A body covers2x2 cells; its second row wraps modulo STAGE_LOGICAL_ROWS.
.var turretCols = List().add(10,28,6)
.var turretRows = List().add(99,32,65)
.if (turretCols.size() != TURRET_COUNT || turretRows.size() != TURRET_COUNT) {
    .error "Turret placement count does not match TURRET_COUNT"
}
.if (TURRET_GLYPH_BASE < TERRAIN_GLYPH_BASE + TERRAIN_GLYPH_COUNT || TURRET_GLYPH_BASE + TURRET_COUNT*4 > 224) {
    .error "Turret private glyphs overlap terrain or diagnostic characters"
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
// This O(1) hook never changes BG_INCOMING_ROW or the metatile decoder.
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
    jsr aimBackgroundTurret
    ldx TURRET_INDEX
    lda TURRET_HIT_TIMER,x
    beq !aimStyle+
    dec TURRET_HIT_TIMER,x
    lda #TURRET_HIT_STYLE
    bne !style+
!aimStyle:
    lda TURRET_AIM,x
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
turretArt:
    // Style0: up-left
    .byte $00,$60,$30,$7f,$4f,$4e,$4b,$49
    .byte $00,$00,$00,$fe,$c2,$62,$32,$b2
    .byte $48,$4c,$47,$43,$50,$40,$7f,$00
    .byte $32,$62,$c2,$82,$0a,$02,$fe,$00
    // Style1: up
    .byte $01,$01,$01,$7f,$47,$4d,$49,$49
    .byte $80,$80,$80,$fe,$c2,$e2,$b2,$b2
    .byte $48,$4c,$47,$43,$50,$40,$7f,$00
    .byte $32,$62,$c2,$82,$0a,$02,$fe,$00
    // Style2: up-right
    .byte $00,$00,$00,$7f,$47,$4c,$48,$49
    .byte $00,$03,$0e,$fe,$f2,$72,$f2,$b2
    .byte $48,$4c,$47,$43,$50,$40,$7f,$00
    .byte $32,$62,$c2,$82,$0a,$02,$fe,$00
    // Style3: down-left
    .byte $00,$00,$00,$7f,$47,$4c,$48,$49
    .byte $00,$00,$00,$fe,$c2,$62,$32,$b2
    .byte $4b,$4f,$4f,$5b,$70,$70,$7f,$00
    .byte $32,$62,$c2,$82,$0a,$02,$fe,$00
    // Style4: down
    .byte $00,$00,$00,$7f,$47,$4c,$48,$49
    .byte $00,$00,$00,$fe,$c2,$62,$32,$b2
    .byte $49,$4d,$47,$43,$51,$41,$7f,$01
    .byte $b2,$e2,$c2,$82,$8a,$82,$fe,$80
    // Style5: down-right
    .byte $00,$00,$00,$7f,$47,$4c,$48,$49
    .byte $00,$00,$00,$fe,$c2,$62,$32,$b2
    .byte $48,$4c,$47,$43,$50,$40,$7f,$00
    .byte $f2,$62,$f2,$9a,$0e,$06,$ff,$00
    // Style6: hit
    .byte $c0,$ff,$60,$50,$48,$44,$42,$41
    .byte $03,$ff,$06,$0a,$12,$22,$42,$82
    .byte $41,$42,$44,$48,$50,$60,$ff,$c0
    .byte $82,$42,$22,$12,$0a,$06,$ff,$03
turretArtEnd:
.if (turretArtEnd - turretArt != 7*32) {
    .error "Turret templates must contain seven16x16 bitmaps"
}
BACKGROUND_TURRETS_END:
.if (BACKGROUND_TURRETS_END > $a000) {
    .error "Background turret code/data overlaps BASIC ROM"
}
