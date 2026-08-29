.filenamespace test                 // KickAssembler namespace: labels/symbols in this file live under "test".
:BasicUpstart2(init)                  // Generate a BASIC stub at $0801 that executes SYS <address of init>.

#import "variables.asm"               // Import the symbolic names for VIC-II/CIA registers and our RAM variables.
.const MAX_OBJECTS = 16
.const TYPE_NONE   = 0
.const TYPE_PLAYER = 1
.const TYPE_ENEMY  = 2


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
    jsr setupSprites                  // Initialise hardware sprite presentation and seed logical object positions.

    lda #01                           // A = 1 pixel per update.
    sta MOB_X_VEL                     // Store mob horizontal velocity in zero-page variable $002B.
    // --- Init game objects ---
    lda #01                           //Init player object
    sta OBJECT_ACTIVE
    lda #TYPE_PLAYER
    sta OBJECT_TYPE
    ldx #00
    !:
    inx
    lda #01
    sta OBJECT_ACTIVE,x
    lda #TYPE_ENEMY
    sta OBJECT_TYPE,x
    cpx #07
    bne !-

    jsr mainLoop                      // Enter the game loop. It never returns in the current program.

checkRaster:                          // Frame-pacing routine: wait for raster line 255.
    lda RASTER                        // Read current VIC-II raster line low byte from $D012 into A.
    cmp #255                          // Compare A with 255; internally performs A-255 and sets flags, without changing A.
    bne checkRaster                   // If Z=0 (not raster line 255), loop and read it again.
    rts                               // Raster reached 255: return to caller.

mainLoop:                             // Main update loop. One pass is intended roughly once per video frame.
    jsr checkRaster                   // Wait until VIC-II reaches raster line 255.
    jsr checkStick                    // Update logical player object (object 0) from joystick input.
    //jsr renderPlayer                  // Copy logical player position into VIC hardware sprite 0.
    jsr updateObjects                      // Update logical enemy objects 1-7 in RAM.
    //jsr renderMobs                    // Copy enemy object positions into VIC hardware sprites 1-7.
    jsr renderSprites
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
        inc OBJECT_Y                  // Otherwise increment object 0 Y: move player one pixel downward.
        lda OBJECT_Y                     // Reload the resulting Y coordinate into A.
        cmp #231                      // Test lower vertical boundary.
        beq !+                        // If Y reached 231, branch to local '+' label and undo the movement.
        jmp up                        // Otherwise continue with the other half of vertical input processing.
    !:
        dec OBJECT_Y                  // Undo the increment: player is not allowed beyond the lower boundary.
        jmp up                        // Continue with UP/down processing.

    up:                               // Second half of the vertical movement pair.
        lda STICK_2                   // Read joystick port 2 again.
        and #2                        // Keep only bit 1 (DOWN). Z=1 when DOWN is pressed.
        beq right                     // If DOWN is pressed, skip this decrement and proceed to horizontal input.
        dec OBJECT_Y                  // Otherwise decrement object 0 Y: move player one pixel upward.
        lda OBJECT_Y                  // Reload new Y coordinate.
        cmp #49                       // Test upper vertical boundary.
        beq !+                        // If Y reached 49, branch and undo the movement.
        jmp right                     // Otherwise continue to horizontal input.
    !:
        inc OBJECT_Y                  // Undo the decrement at the upper boundary.
        jmp right                     // Continue to horizontal input.

    right:                            // First half of the horizontal movement pair.
        lda STICK_2                   // Read joystick port 2.
        and #4                        // Keep bit 2 (LEFT). Z=1 when LEFT is pressed.
        beq left                      // LEFT pressed: skip the X increment and continue at 'left'.
        inc OBJECT_X                  // Increment object 0 low X byte: one pixel to the right.
        lda OBJECT_X                  // Reload the new low X byte.
        cmp #00                       // Did low byte wrap from 255 to 0 (crossing X=255 -> X=256)?
        beq setOverflow               // Yes: toggle object 0 bit 8 in the logical OBJECT_X_MSB bitfield.
        cmp #66                       // Low byte 66 may mean X=66 or X=322 depending on logical MSB bit 0.
        beq checkRightBounds          // Resolve that ambiguity before enforcing the right boundary.
        jmp left                      // Continue with the other half of horizontal input processing.

    left:                             // Second half of the horizontal movement pair.
        lda STICK_2                   // Read joystick port 2 again.
        and #8                        // Keep bit 3 (RIGHT). Z=1 when RIGHT is pressed.
        beq fire                      // RIGHT pressed: skip the X decrement and proceed to fire processing.
        dec OBJECT_X                  // Decrement object 0 low X byte: one pixel to the left.
        lda OBJECT_X                     // Reload new low X byte.
        cmp #255                      // Did low byte wrap from 0 to 255 (crossing X=256 -> X=255)?
        beq setOverflow               // Yes: toggle object 0 bit 8 in logical RAM.
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
    lda OBJECT_X_MSB                  // A = logical X-MSB bitfield for objects 0-7; bit 0 belongs to player.
    and #%00000001                    // Isolate bit 0, which belongs to player/hardware sprite 0.
    beq !+                            // MSB=0 means actual X=66: not the far-right boundary, so leave it alone.
    dec OBJECT_X                     // MSB=1 means actual X=322: undo movement to keep player inside boundary.
!:
    rts                               // Return to joystick routine/main loop.

checkLeftBounds:                      // Called when player's low X byte has become 22.
    lda OBJECT_X_MSB                  // Read logical object X-MSB bitfield from RAM.
    and #%00000001                    // Isolate player's bit 0.
    bne !+                            // MSB=1 means actual X=278, not the left edge; do nothing.
    inc OBJECT_X                     // MSB=0 means actual X=22: undo movement, keeping player at X=23.
!:
    rts                               // Return.

setOverflow:                          // Toggle player's ninth X-coordinate bit when low byte wraps.
    lda OBJECT_X_MSB                  // Read logical object X-MSB bits from RAM.
    eor #%00000001                    // Toggle ONLY bit 0. Other sprites' ninth X bits are preserved.
    sta OBJECT_X_MSB                 // Store updated logical bitfield; renderer later copies it to VIC.
    rts                               // Return.

// ============================================================================
// RENDER LOGICAL OBJECT STATE INTO VIC-II HARDWARE SPRITES
// ============================================================================

renderPlayer:                         // Render logical object 0 into hardware sprite 0.
    lda OBJECT_X                     // A = object 0 low X byte (OBJECT_X+0).
    sta SPR_X                        // Copy it to hardware sprite 0 X register ($D000).
    lda OBJECT_Y                     // A = object 0 Y coordinate (OBJECT_Y+0).
    sta SPR_Y                        // Copy it to hardware sprite 0 Y register ($D001).

    // $D010 is shared by all eight hardware sprites, so renderPlayer must
    // replace only bit 0 and preserve the current hardware values in bits 1-7.
    lda SPRITE_OVERFLOW_REGISTER     // A = current hardware X-MSB bitfield ($D010).
    and #%11111110                   // Clear hardware sprite 0 bit; preserve sprites 1-7.
    sta TEMP_X                       // Save that preserved hardware value in scratch RAM.
    lda OBJECT_X_MSB                 // A = logical X-MSB bits for objects 0-7.
    and #%00000001                   // Keep only logical object 0's ninth X bit.
    ora TEMP_X                       // Merge logical player bit with preserved enemy hardware bits.
    sta SPRITE_OVERFLOW_REGISTER     // Update $D010.
    rts

renderMobs:                           // Render logical objects 1-7 into hardware sprites 1-7.
    ldx #01                         // X = logical object index; object 0 is reserved for player.
    ldy #02                         // Y = VIC coordinate offset: $D000+2 is hardware sprite 1 X.
!:
    lda OBJECT_X,x                  // Read current logical object's low X byte.
    sta SPR_X,y                     // Write it to the corresponding hardware sprite X register.
    lda OBJECT_Y,x                  // Read current logical object's Y coordinate.
    sta SPR_Y,y                     // SPR_Y ($D001) + same even offset reaches that sprite's Y register.

    inx                             // Advance to next logical object: 1,2,3...7.
    iny                             // Advance VIC offset by two because X/Y registers are interleaved.
    iny                             // Hardware offsets therefore run 2,4,6...14.
    cpx #08                         // Object 8 means objects 1-7 are complete.
    bne !-

    // TEMPORARY 1:1 renderer: logical objects 0-7 currently map directly to
    // hardware sprites 0-7, so their eight MSB bits have exactly the layout $D010 expects.
    lda OBJECT_X_MSB                // Read logical X-MSB byte for objects 0-7.
    sta SPRITE_OVERFLOW_REGISTER    // Copy all eight bits to hardware in one operation.
                                      // This stops being sufficient once >8 logical sprites/multiplexing arrive.
    rts

renderSprites:
    ldy #00                  // Y = hardware sprite slot
    lda #00
    sta TEMP_MSB

renderLoop:
    lda HW_OBJECT,y         // Find logical object assigned to this VIC slot.
    tax                     // X = logical object index.
    lda OBJECT_X_MSB
    and objectBitMask,x
    beq !noMsb+

    lda TEMP_MSB
    ora HW_BIT_MASK,y
    sta TEMP_MSB

!noMsb:
    sty TEMP_Y_REG          // Preserve the hardware slot number.

    lda HW_SPRITE_OFFSET,y  // Convert slot 0-7 into VIC offset 0,2,4...14.
    tay                     // Y now indexes the VIC coordinate registers.

    lda OBJECT_X,x          // Read logical object's X position.
    sta SPR_X,y             // Write it to this hardware sprite's X register.

    lda OBJECT_Y,x          // Read logical object's Y position.
    sta SPR_Y,y             // Write it to this hardware sprite's Y register.

    ldy TEMP_Y_REG          // Restore Y = hardware slot number.

    iny                     // Next hardware slot.
    cpy #8
    bne renderLoop
    lda TEMP_MSB
    sta SPRITE_OVERFLOW_REGISTER
    rts

// ============================================================================
// SPRITE INITIALISATION
// ============================================================================

setupSprites:

    // --- Enable all eight hardware sprites ---
    lda #$ff                          // A = %11111111.
    sta SPRITE_ENABLE                 // $D015: set all eight enable bits, turning sprites 0-7 on.

    // --- Set hardware sprite pointers $07F8-$07FF ---
    // Each VIC sprite pointer is the bitmap address divided by 64.
    // The assembler calculates the values from playerSprite/enemySpriteA/B,
    // so moving the bitmap block does not require hand-editing pointer numbers.

   ldx #$00                           // X = 0: index into the eight sprite-pointer bytes.

pointerLoop:
    lda spritePointers,x              // A = pointer value for this hardware sprite slot.
    sta HW_SPRITE_POINTER,x          // Store into $07F8+X (hardware sprite pointer table).
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

    // --- Initialise logical direction bitfield ---
    // OBJECT_DIR is two bytes because the pool can hold 16 objects. For this
    // prototype only objects 1-7 are active, but clear both bytes now.
    ldx #01                           // X=1 selects the second direction byte (objects 8-15).
    lda #%00000000                    // A = all direction bits clear = initial "moving right" state.
    sta OBJECT_DIR                    // Clear direction bits for objects 0-7.
    sta OBJECT_DIR,x                  // Clear direction bits for objects 8-15.

    // --- Player starting position ---
    lda #146                          // A = initial player X low byte.
    sta OBJECT_X                     // Seed logical object 0 X low byte; no VIC register is touched here.
    lda #200                          // A = initial player Y.
    sta OBJECT_Y                     // Seed logical object 0 Y.
    lda #0
    sta OBJECT_X_MSB                 // Clear X bit 8 for logical objects 0-7.

    // --- Mob starting X positions ---
    lda #31                           // A = first mob's X position.
    ldx #01                           // X = logical object 1, the first enemy.

xposLoop:
    sta OBJECT_X,x                    // Store low X byte in the current logical object.
    clc                               // Clear carry so the following ADC performs exactly A + 28.
    adc #28                           // A = previous mob X + 28; spaces mobs horizontally.
    inx
    cpx #08
    bne xposLoop                      // Repeat until all seven mob X positions are set.

    // --- Mob starting Y positions ---
    lda #54                           // A = common starting Y coordinate for every enemy object.
    ldx #01                           // X = logical object 1 again.

yposLoop:
    sta OBJECT_Y,x                    // Store Y directly in the current logical object.
    inx                               // Next logical object.
    cpx #08                           // Reached object 8? Then objects 1-7 are initialised.
    bne yposLoop                      // No: repeat.

    rts                               // Sprite setup complete; return to init.


// ============================================================================
// MOB UPDATE DISPATCH
// ============================================================================

updateObjects:
    ldx #0                      // Begin with logical object 0.

objectLoop:
    lda OBJECT_ACTIVE,x         // Is this object slot currently occupied?
    beq nextObject              // No: ignore it.

    lda OBJECT_TYPE,x           // What kind of object occupies this slot?
    cmp #TYPE_ENEMY
    bne nextObject              // Not an enemy: nothing to update here yet.
    lda objectBitMask,x
    sta CURRENT_SPRITE
    jsr moveEnemy               // X remains the current logical object index.

nextObject:
    inx                         // Advance to the next object slot.
    cpx #MAX_OBJECTS            // Have we scanned the entire pool?
    bne objectLoop

    rts

// ============================================================================
// INDIVIDUAL MOB MOVEMENT
// ============================================================================

moveEnemy:
    lda OBJECT_DIR                   // A = packed direction bits for logical objects 0-7.
    and CURRENT_SPRITE                // Keep only the bit belonging to the current mob.
    bne !+                            // Non-zero => this mob's direction bit is set: take left-moving branch.
    beq !++                           // Zero => direction bit clear: take right-moving branch.
                                      // One of these branches must occur; the BEQ is effectively unconditional here.

!:                                    // Local '+' label: current mob is moving LEFT.
    sec                               // Set Carry before SBC. On 6502, C=1 means "no borrow in".
    lda OBJECT_X,x                   // A = current logical object's low X byte.
    sbc MOB_X_VEL                     // A = A - velocity - (1-C). With SEC and velocity=1, subtract exactly 1.
    sta OBJECT_X,x                   // Store updated low X byte back into logical RAM.

    cmp #255                          // Did low byte become 255? This is the 256->255 crossing when MSB was set.
    beq overflowMob                   // Toggle this object's logical ninth-X bit (256 -> 255 crossing).

    cmp #23                           // Low byte 23 is a possible left reversal coordinate.
    beq checkMobLeftBoundary          // Check logical MSB because low=23 could mean X=23 or X=279.

    rts                               // No overflow/reversal event: movement for this mob is complete.


!:                                    // Second local '+' label: current mob is moving RIGHT.
    clc                               // Clear Carry before ADC so addition is exactly A + velocity.
    lda OBJECT_X,x                   // A = current logical object's low X byte.
    adc MOB_X_VEL                     // Add horizontal velocity (currently 1).
    sta OBJECT_X,x                   // Store updated low X byte in logical RAM.

    cmp #0                            // Did low byte wrap 255->0, crossing X=255 -> X=256?
    beq overflowMob                   // Toggle this object's logical ninth-X bit.

    cmp #66                           // Low byte 66 is a possible right reversal coordinate.
    beq checkMobRightBoundary         // Check MSB because low=66 could mean X=66 or X=322.

    rts                               // Normal movement complete.


overflowMob:                          // Toggle current logical object's ninth X-coordinate bit.
    lda OBJECT_X_MSB                 // A = packed X-MSB bits for logical objects 0-7.
    eor CURRENT_SPRITE                // Toggle only the bit represented by CURRENT_SPRITE.
    sta OBJECT_X_MSB                 // Save the updated logical X-MSB bitfield in RAM.
    rts                               // Return directly to moveMobs (because this routine was reached by branch).


reverseMob:                           // Reverse current mob and drop it down one row.
    lda OBJECT_Y,x                   // A = current logical object's Y coordinate.
    clc                               // Clear carry so the vertical displacement is exactly 24.
    adc #24                           // A = Y + 24 pixels.
    sta OBJECT_Y,x                   // Store new logical Y coordinate.

    lda OBJECT_DIR                   // A = packed direction bits for logical objects 0-7.
    eor CURRENT_SPRITE                // Toggle only the current mob's direction bit.
    sta OBJECT_DIR                   // Save the changed direction bitfield.
    rts                               // Return to moveMobs.


checkMobRightBoundary:                // Resolve ambiguity when mob low X byte is 66.
    lda OBJECT_X_MSB                 // A = logical X-MSB bitfield for objects 0-7.
    and CURRENT_SPRITE                // Isolate the current mob's ninth X bit.
    beq !+                            // Bit clear => actual X=66, not the far-right boundary.
    jmp reverseMob                    // Bit set => actual X=256+66=322: reverse and descend.
!:
    rts                               // X=66: continue moving right on future frames.


checkMobLeftBoundary:                 // Resolve ambiguity when mob low X byte is 23.
    lda OBJECT_X_MSB                 // A = logical X-MSB bitfield for objects 0-7.
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

// ============================================================================
// LOGICAL OBJECT BIT-MASK LOOKUP TABLE
// ============================================================================

objectBitMask:
    .byte %00000001
    .byte %00000010
    .byte %00000100
    .byte %00001000
    .byte %00010000
    .byte %00100000
    .byte %01000000
    .byte %10000000

HW_BIT_MASK:
    .byte %00000001
    .byte %00000010
    .byte %00000100
    .byte %00001000
    .byte %00010000
    .byte %00100000
    .byte %01000000
    .byte %10000000

// ---------------------------------------------------------
// LOGICAL OBJECT STATE POOL
// ---------------------------------------------------------

* = $2000

OBJECT_X:
    .fill MAX_OBJECTS, 0       // $2000-$200F : X low byte for objects 0-15

OBJECT_Y:
    .fill MAX_OBJECTS, 0       // $2010-$201F : Y position for objects 0-15

OBJECT_X_MSB:
    .fill 2, 0                 // $2020-$2021 : X bit 8 for objects 0-15

OBJECT_DIR:
    .fill 2, 0                 // $2022-$2023 : one packed direction bit per logical object

OBJECT_ACTIVE:
    .fill MAX_OBJECTS, 0

OBJECT_TYPE:
    .fill MAX_OBJECTS, 0

HW_OBJECT:
    .byte 0,1,2,3,4,5,6,7

HW_SPRITE_OFFSET:
    .byte 0,2,4,6,8,10,12,14

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
