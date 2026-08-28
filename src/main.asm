.filenamespace test                 // KickAssembler namespace: labels/symbols in this file live under "test".
:BasicUpstart2(init)                  // Generate a BASIC stub at $0801 that executes SYS <address of init>.

#import "variables.asm"               // Import the symbolic names for VIC-II/CIA registers and our RAM variables.


// ============================================================================
// INITIALISATION
// ============================================================================

init:                                 // Program entry point called by the BASIC stub.

    // --- Select VIC-II bank 0 ($0000-$3FFF) ---
    lda VIC_BANK                      // A = current CIA2 port value at $DD00. Its low 2 bits select the VIC bank.
    and #%11111100                    // Clear bits 0-1 while preserving bits 2-7. Affected flags: Z, N.
    ora #%00000011                    // Set bits 0-1 to %11. VIC bank selection is inverted, so %11 selects bank 0.
    sta VIC_BANK                      // Write the modified value back to $DD00; VIC-II now uses bank 0.

    // --- Configure VIC-II character/screen memory layout ---
    lda VIC_MEMORY_SETUP              // A = current VIC memory setup register ($D018).
    and #%11110000                    // Clear the low nibble while preserving the upper nibble.
    ora #%00000100                    // Set character-memory selector bits to the desired character generator location.
    sta VIC_MEMORY_SETUP              // Store the new VIC-II memory configuration in $D018.

    // --- Clear the screen ---
    lda #147                          // A = PETSCII control code 147 ("clear screen").
    jsr $ffd2                         // Call KERNAL CHROUT; it interprets A and clears the screen.

    jsr setupSprites                  // Initialise sprite enable flags, pointers, colours and starting positions.

    // --- Crude on-screen debug markers ---
    lda #24                           // A = screen-code value 24.
    sta SCREEN_START                  // Store it at the first screen cell ($0400).
    lda #58                           // A = screen-code value 58.
    sta SCREEN_START + 1              // Put it in column 1 of row 0.
    sta SCREEN_START + 41             // Put the same value in column 1 of row 1.
    lda #25                           // A = screen-code value 25.
    sta SCREEN_START + 40             // Put it in column 0 of row 1.

    lda #01                           // A = 1 pixel per update.
    sta MOB_X_VEL                     // Store mob horizontal velocity in zero-page variable $002B.

    jsr mainLoop                      // Enter the game loop. NOTE: mainLoop never returns, so JMP would also suit this.


checkRaster:                          // Frame-pacing routine: wait for raster line 255.
    lda RASTER                        // Read current VIC-II raster line low byte from $D012 into A.
    cmp #255                          // Compare A with 255; internally performs A-255 and sets flags, without changing A.
    bne checkRaster                   // If Z=0 (not raster line 255), loop and read it again.
    rts                               // Raster reached 255: return to caller.


mainLoop:                             // Main update loop. One pass is intended roughly once per video frame.
    jsr checkRaster                   // Wait until VIC-II reaches raster line 255.
    jsr checkStick
    jsr renderPlayer                    // Read joystick port 2 and update player position/fire state.
    jsr moveMobs                      // Move all seven enemy sprites.
    //lda SPR_X                         // A = player sprite's 8-bit X coordinate from VIC register $D000.
    //sta SCREEN_START + 3              // Display raw X byte as a screen code in row 0, column 3.
    //lda SPR_Y                         // A = player sprite's Y coordinate from VIC register $D001.
    //sta SCREEN_START + 43             // Display raw Y byte as a screen code in row 1, column 3.
    jmp mainLoop                      // Repeat forever. JMP is correct here: unlike JSR it does not leak return addresses.


/*
    JOYSTICK PORT 2 ($DC00)

    Joystick inputs are ACTIVE LOW:
        bit 0 = up
        bit 1 = down
        bit 2 = left
        bit 3 = right
        bit 4 = fire

    A pressed direction therefore produces a 0 bit.

    This routine's control flow is slightly counter-intuitive. For movement,
    the test branches over one of two opposing operations. With no direction
    pressed the opposing changes cancel one another; pressing a direction
    prevents the opposite change, leaving the desired movement.
*/

checkStick:

    down:                             // First half of the vertical movement pair.
        lda STICK_2                   // A = joystick port 2 state from CIA1 $DC00.
        and #1                        // Keep only bit 0 (UP). Z=1 when UP is pressed because input is active-low.
        beq up                        // If UP is pressed, skip this increment and continue at 'up'.
        inc OBJECT_Y                     // Otherwise increment player Y: move one pixel downward.
        lda OBJECT_Y                     // Reload the resulting Y coordinate into A.
        cmp #231                      // Test lower vertical boundary.
        beq !+                        // If Y reached 231, branch to local '+' label and undo the movement.
        jmp up                        // Otherwise continue with the other half of vertical input processing.
    !:
        dec OBJECT_Y                     // Undo the increment: player is not allowed beyond the lower boundary.
        jmp up                        // Continue with UP/down processing.

    up:                               // Second half of the vertical movement pair.
        lda STICK_2                   // Read joystick port 2 again.
        and #2                        // Keep only bit 1 (DOWN). Z=1 when DOWN is pressed.
        beq right                     // If DOWN is pressed, skip this decrement and proceed to horizontal input.
        dec OBJECT_Y                     // Otherwise decrement Y: move one pixel upward.
        lda OBJECT_Y                  // Reload new Y coordinate.
        cmp #49                       // Test upper vertical boundary.
        beq !+                        // If Y reached 49, branch and undo the movement.
        jmp right                     // Otherwise continue to horizontal input.
    !:
        inc OBJECT_Y                     // Undo the decrement at the upper boundary.
        jmp right                     // Continue to horizontal input.

    right:                            // First half of the horizontal movement pair.
        lda STICK_2                   // Read joystick port 2.
        and #4                        // Keep bit 2 (LEFT). Z=1 when LEFT is pressed.
        beq left                      // LEFT pressed: skip the X increment and continue at 'left'.
        inc OBJECT_X                     // Otherwise increment low X byte: one pixel to the right.
        lda OBJECT_X                  // Reload the new low X byte.
        cmp #00                       // Did low byte wrap from 255 to 0 (crossing X=255 -> X=256)?
        beq setOverflow               // Yes: toggle player bit 0 in $D010, the ninth X-coordinate bit.
        cmp #66                       // Low byte 66 may mean X=66 or X=322 depending on $D010 bit 0.
        beq checkRightBounds          // Resolve that ambiguity before enforcing the right boundary.
        jmp left                      // Continue with the other half of horizontal input processing.

    left:                             // Second half of the horizontal movement pair.
        lda STICK_2                   // Read joystick port 2 again.
        and #8                        // Keep bit 3 (RIGHT). Z=1 when RIGHT is pressed.
        beq fire                      // RIGHT pressed: skip the X decrement and proceed to fire processing.
        dec OBJECT_X                     // Otherwise decrement low X byte: one pixel to the left.
        lda OBJECT_X                     // Reload new low X byte.
        cmp #255                      // Did low byte wrap from 0 to 255 (crossing X=256 -> X=255)?
        beq setOverflow               // Yes: toggle player bit 0 in $D010.
        cmp #22                       // Low byte 22 is the attempted position beyond the desired left edge.
        beq checkLeftBounds           // Check the ninth X bit to determine whether this really is left-side X=22.
        jmp fire                      // Continue to fire processing.

    fire:
        lda STICK_2                   // Read joystick port 2.
        and #16                       // Keep bit 4 (FIRE). Z=1 when fire is pressed.
        bne !+                        // If bit is 1, fire is NOT pressed; skip the debug effect.
        inc BORDER_COLOUR             // Fire pressed: increment VIC border colour ($D020) as a visible test.

    !:
        rts                           // Return to mainLoop.


checkRightBounds:                     // Called when player's low X byte has become 66.
    lda OBJECT_X_MSB      // A = $D010, containing the ninth X bit for all eight hardware sprites.
    and #%00000001                    // Isolate bit 0, which belongs to player/hardware sprite 0.
    beq !+                            // MSB=0 means actual X=66: not the far-right boundary, so leave it alone.
    dec OBJECT_X                         // MSB=1 means actual X=322: undo movement to keep player inside boundary.
!:
    rts                               // Return to joystick routine/main loop.


checkLeftBounds:                      // Called when player's low X byte has become 22.
    lda OBJECT_X_MSB     // Read shared sprite X-MSB register $D010.
    and #%00000001                    // Isolate player's bit 0.
    bne !+                            // MSB=1 means actual X=278, not the left edge; do nothing.
    inc OBJECT_X                        // MSB=0 means actual X=22: undo movement, keeping player at X=23.
!:
    rts                               // Return.


setOverflow:                          // Toggle player's ninth X-coordinate bit when low byte wraps.
    lda OBJECT_X_MSB      // Read all eight sprite X-MSB bits from $D010.
    eor #%00000001                    // Toggle ONLY bit 0. Other sprites' ninth X bits are preserved.
    sta OBJECT_X_MSB      // Write modified bitfield back to $D010.
    rts                               // Return.

// ============================================================================
// Sprite Render Routines
// ============================================================================
renderPlayer:
    lda OBJECT_X
    sta SPR_X
    lda OBJECT_Y
    sta SPR_Y
    lda SPRITE_OVERFLOW_REGISTER
    and #%11111110          // clear bit 0, preserve bits 1-7
    sta TEMP_X              // keep the cleaned hardware value
    lda OBJECT_X_MSB
    and #%00000001          // isolate player MSB only
    ora TEMP_X              // combine it with preserved hardware bits
    sta SPRITE_OVERFLOW_REGISTER
    rts

// ============================================================================
// SPRITE INITIALISATION
// ============================================================================

setupSprites:

    // --- Enable all eight hardware sprites ---
    lda #$ff                          // A = %11111111.
    sta SPRITE_ENABLE                 // $D015: set all eight enable bits, turning sprites 0-7 on.

    // --- Set sprite pointers $07F8-$07FF to $80-$87 ---
    //
    // In VIC bank 0, pointer $80 means $80 * 64 = $2000.
    // Therefore pointers $80-$87 select the eight 64-byte blocks beginning
    // at $2000, $2040, $2080 ... $21C0.

   ldx #$00                           // X = 0: index into the eight sprite-pointer bytes.

pointerLoop:
    lda spritePointers,x
    sta HW_SPRITE_POINTER,x
    inx
    cpx #$08
    bne pointerLoop
                                      // Yes: fall through. X is now 8.

    // --- Set sprite colours ---
    lda #02                           // A = C64 colour 2 (red).
    sta SPRITE_1_COLOUR               // $D027: player/hardware sprite 0 colour = red.

    lda #03                           // A = C64 colour 3 (cyan).
    ldx #00                           // X = 0, used as offset from sprite 1's colour register.

colourLoop:
    sta SPRITE_2_COLOUR,x             // Write cyan to $D028 + X (sprites 1 through 7).
    inx                               // Advance to next sprite colour register.
    cpx #07                           // Have seven mob colour registers been written?
    bne colourLoop                    // No: repeat.

    // --- Initialise mob direction bitfield ---
    lda #%00000000                    // A = all direction bits clear.
    sta SPRITES_DIR                   // Every mob therefore begins in the routine's "moving right" state.

    // --- Player starting position ---
    lda #146                          // A = initial player X low byte.
    sta OBJECT_X                         // $D000: hardware sprite 0 X = 146. $D010 bit 0 remains clear initially.
    lda #200                          // A = initial player Y.
    sta OBJECT_Y                        // $D001: hardware sprite 0 Y = 200.
    lda #0
    sta OBJECT_X_MSB

    // --- Mob starting X positions ---
    lda #31                           // A = first mob's X position.
    ldx #00                           // X = offset 0 into interleaved sprite coordinate registers.

xposLoop:
    clc                               // Clear carry so the following ADC performs exactly A + 28.
    sta SPR_2_X,x                     // Store A at $D002 + X: X coordinate of current mob.
    inx                               // X += 1...
    inx                               // ...and X += 1 again, because VIC sprite coordinates are X,Y pairs.
    adc #28                           // A = previous mob X + 28; spaces mobs horizontally.
    cpx #14                           // Offsets used are 0,2,4,6,8,10,12: seven mobs total.
    bne xposLoop                      // Repeat until all seven mob X positions are set.

    // --- Mob starting Y positions ---
    lda #54                           // A = common starting Y coordinate for every mob.
    ldx #00                           // Reset coordinate-register offset to zero.

yposLoop:
    sta SPR_2_Y,x                     // Store A at $D003 + X: current mob's Y coordinate.
    inx                               // X += 1...
    inx                               // ...X += 1 again to reach next sprite's Y register.
    cpx #14                           // Seven mobs written?
    bne yposLoop                      // No: repeat.

    rts                               // Sprite setup complete; return to init.


// ============================================================================
// MOB UPDATE DISPATCH
// ============================================================================

moveMobs:
    ldx #02                           // X = 2, the offset from SPR_X ($D000) to sprite 1's X register ($D002).
    ldy #01                           // Y = 1; used to generate a one-bit mask for each mob.

mobLoop:
    tya                               // A = Y. First pass A=1, then 2,4,8,... due to TAY below.
    asl                               // Shift A left one bit: 1->2->4->8->16->32->64->128.
                                      // ASL also moves old bit 7 into Carry and sets Z/N from result.
    sta CURRENT_SPRITE                // Save this mob's bit mask in RAM ($2300).
                                      // Masks correspond to $D010 bits for hardware sprites 1-7.
    tay                               // Y = generated mask, ready to become the basis for next iteration.
    jsr move                          // Move the mob whose VIC register offset is in X.
    // jsr overflowMob                // Disabled old experiment/debug call.
    inx                               // X += 1...
    inx                               // ...X += 1: advance from one sprite's X register to the next.
    cpx #16                           // After offsets 2,4,6,8,10,12,14, X becomes 16.
    bne mobLoop                       // If X != 16, process another mob.
    rts                               // All seven mobs updated; return to mainLoop.


// ============================================================================
// INDIVIDUAL MOB MOVEMENT
// ============================================================================

move:
    lda SPRITES_DIR                   // A = direction bitfield for all mobs.
    and CURRENT_SPRITE                // Keep only the bit belonging to the current mob.
    bne !+                            // Non-zero => this mob's direction bit is set: take left-moving branch.
    beq !++                           // Zero => direction bit clear: take right-moving branch.
                                      // One of these branches must occur; the BEQ is effectively unconditional here.

!:                                    // Local '+' label: current mob is moving LEFT.
    sec                               // Set Carry before SBC. On 6502, C=1 means "no borrow in".
    lda SPR_X,x                       // A = current mob's low X byte. X selects $D002,$D004,...,$D00E.
    sbc MOB_X_VEL                     // A = A - velocity - (1-C). With SEC and velocity=1, subtract exactly 1.
    sta SPR_X,x                       // Write updated low X byte back to the VIC-II register.

    cmp #255                          // Did low byte become 255? This is the 256->255 crossing when MSB was set.
    beq overflowMob                   // Toggle this mob's $D010 bit to move from X>=256 back into X<256.

    cmp #23                           // Low byte 23 is a possible left reversal coordinate.
    beq checkMobLeftBoundary          // Check $D010 because low=23 could mean X=23 or X=279.

    rts                               // No overflow/reversal event: movement for this mob is complete.


!:                                    // Second local '+' label: current mob is moving RIGHT.
    clc                               // Clear Carry before ADC so addition is exactly A + velocity.
    lda SPR_X,x                       // A = current mob's low X byte.
    adc MOB_X_VEL                     // Add horizontal velocity (currently 1).
    sta SPR_X,x                       // Store updated low X byte.

    cmp #0                            // Did low byte wrap 255->0, crossing X=255 -> X=256?
    beq overflowMob                   // Toggle this mob's ninth X bit in $D010.

    cmp #66                           // Low byte 66 is a possible right reversal coordinate.
    beq checkMobRightBoundary         // Check MSB because low=66 could mean X=66 or X=322.

    rts                               // Normal movement complete.


overflowMob:                          // Toggle the ninth X-coordinate bit for CURRENT_SPRITE.
    lda SPRITE_OVERFLOW_REGISTER      // A = all eight sprite X-MSB bits from $D010.
    eor CURRENT_SPRITE                // Toggle only the bit represented by CURRENT_SPRITE.
    sta SPRITE_OVERFLOW_REGISTER      // Write the updated shared bitfield back to $D010.
    rts                               // Return directly to moveMobs (because this routine was reached by branch).


reverseMob:                           // Reverse current mob and drop it down one row.
    lda SPR_Y,x                       // A = current mob's Y coordinate.
                                      // X points at its X register; SPR_Y ($D001) + same X reaches its Y register.
    clc                               // Clear carry so the vertical displacement is exactly 24.
    adc #24                           // A = Y + 24 pixels.
    sta SPR_Y,x                       // Store the new lower Y coordinate.

    lda SPRITES_DIR                   // A = direction bits for all mobs.
    eor CURRENT_SPRITE                // Toggle only the current mob's direction bit.
    sta SPRITES_DIR                   // Save the changed direction bitfield.
    rts                               // Return to moveMobs.


checkMobRightBoundary:                // Resolve ambiguity when mob low X byte is 66.
    lda SPRITE_OVERFLOW_REGISTER      // A = shared ninth-X-bit register $D010.
    and CURRENT_SPRITE                // Isolate the current mob's ninth X bit.
    beq !+                            // Bit clear => actual X=66, so this is NOT the right boundary.
    jmp reverseMob                    // Bit set => actual X=256+66=322: reverse and descend.
!:
    rts                               // X=66: continue moving right on future frames.


checkMobLeftBoundary:                 // Resolve ambiguity when mob low X byte is 23.
    lda SPRITE_OVERFLOW_REGISTER      // A = shared ninth-X-bit register $D010.
    and CURRENT_SPRITE                // Isolate current mob's ninth X bit.
    bne !+                            // Bit set => actual X=256+23=279, so this is NOT the left boundary.
    jmp reverseMob                    // Bit clear => actual X=23: reverse and descend.
!:
    rts                               // X=279: continue moving left on future frames.

// ============================================================================
// SPRITE LOOKUP POINTER TABLE
// ============================================================================

spritePointers:
    .byte playerSprite / 64
    .byte enemySpriteA / 64
    .byte enemySpriteB / 64
    .byte enemySpriteA / 64
    .byte enemySpriteB / 64
    .byte enemySpriteA / 64
    .byte enemySpriteB / 64
    .byte enemySpriteA / 64

// ---------------------------------------------------------
// Logical object state
// ---------------------------------------------------------

.const MAX_OBJECTS = 16

* = $2000

OBJECT_X:
    .fill MAX_OBJECTS, 0       // $2000-$200F : X low byte for objects 0-15

OBJECT_Y:
    .fill MAX_OBJECTS, 0       // $2010-$201F : Y position for objects 0-15

OBJECT_X_MSB:
    .fill 2, 0                 // $2020-$2021 : X bit 8 for objects 0-15

// ============================================================================
// SPRITE BITMAP DATA
// ============================================================================

* = $2400                            // Assemble following data beginning at address $2400.
                                      // Each VIC-II sprite occupies a 64-byte slot:
                                      // 63 bytes = 24x21 one-bit bitmap (3 bytes per row x 21 rows),
                                      // byte 64 = unused by the VIC and serves as padding/alignment.

playerSprite:
.byte $00,$00,$00,$7f,$ff,$fe,$40,$18 // Raw bitmap bytes. Each group of 3 bytes represents one 24-pixel sprite row.
.byte $02,$40,$18,$02,$40,$18,$02,$40 // Bits set to 1 are foreground pixels; 0 bits are transparent.
.byte $18,$02,$40,$18,$02,$40,$18,$02 // These data bytes are not CPU instructions; VIC-II reads them directly.
.byte $40,$18,$02,$40,$18,$02,$7f,$ff
.byte $fe,$40,$18,$02,$40,$18,$02,$40
.byte $18,$02,$40,$18,$02,$40,$18,$02
.byte $40,$18,$02,$40,$18,$02,$40,$18
.byte $02,$7f,$ff,$fe,$00,$00,$00,$0a // Final byte is padding; VIC uses only the first 63 bytes of the slot.

enemySpriteA:
    .byte $00,$18,$00
    .byte $00,$3c,$00
    .byte $00,$7e,$00
    .byte $01,$ff,$80
    .byte $03,$ff,$c0
    .byte $07,$db,$e0
    .byte $0f,$ff,$f0
    .byte $1f,$ff,$f8
    .byte $3f,$ff,$fc
    .byte $3c,$ff,$3c
    .byte $3c,$ff,$3c
    .byte $3f,$ff,$fc
    .byte $1f,$ff,$f8
    .byte $0f,$ff,$f0
    .byte $07,$bd,$e0
    .byte $03,$18,$c0
    .byte $06,$18,$60
    .byte $0c,$00,$30
    .byte $18,$00,$18
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00              // 64th byte padding

    enemySpriteB:
    .byte $00,$00,$00
    .byte $0c,$00,$30
    .byte $06,$00,$60
    .byte $03,$00,$c0
    .byte $03,$81,$c0
    .byte $07,$c3,$e0
    .byte $0f,$e7,$f0
    .byte $1f,$ff,$f8
    .byte $3f,$ff,$fc
    .byte $7f,$ff,$fe
    .byte $7e,$7e,$7e
    .byte $7f,$ff,$fe
    .byte $3f,$ff,$fc
    .byte $1f,$ff,$f8
    .byte $0f,$ff,$f0
    .byte $07,$e7,$e0
    .byte $03,$c3,$c0
    .byte $01,$81,$80
    .byte $03,$00,$c0
    .byte $06,$00,$60
    .byte $00,$00,$00
    .byte $00              // 64th byte padding
