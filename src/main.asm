.filenamespace test                     // KickAssembler namespace: labels/symbols in this file live under "test".
:BasicUpstart2(init)                    // Generate a BASIC stub at $0801 that executes SYS <address of init>.

#import "variables.asm"                 // Import the symbolic names for VIC-II/CIA registers and our RAM variables.
.const MAX_OBJECTS = 16
.const TYPE_NONE   = 0
.const TYPE_PLAYER = 1
.const TYPE_ENEMY  = 2


// ============================================================================
// INITIALISATION
// ============================================================================

init:                                   // Program entry point called by the BASIC stub.

    // --- Select VIC-II bank 0 ($0000-$3FFF) ---
    lda VIC_BANK                        // A = current CIA2 port value at $DD00. Its low 2 bits select the VIC bank.
    and #%11111100                      // Clear bits 0-1 while preserving bits 2-7. Affected flags: Z, N.
    ora #%00000011                      // Set bits 0-1 to %11. VIC bank selection is inverted, so %11 selects bank 0.
    sta VIC_BANK                        // Write the modified value back to $DD00; VIC-II now uses bank 0.

    // --- Configure VIC-II character/screen memory layout ---
    lda VIC_MEMORY_SETUP                // A = current VIC memory setup register ($D018).
    and #%11110000                      // Clear the low nibble while preserving the upper nibble.
    ora #%00000100                      // Set character-memory selector bits to the desired character generator location.
    sta VIC_MEMORY_SETUP                // Store the new VIC-II memory configuration in $D018.

    // --- Clear the screen ---
    lda #147                          // A = PETSCII control code 147 ("clear screen").
    jsr $ffd2                           // Call KERNAL CHROUT; it interprets A and clears the screen.
    jsr setupSprites                    // Initialise hardware sprite presentation and seed logical object positions.

    lda #01                             // A = 1 pixel per update.
    sta MOB_X_VEL                       // Store mob horizontal velocity in zero-page variable $002B.
    // --- Init game objects ---
    lda #01                             //Init player object
    sta OBJECT_ACTIVE
    lda #TYPE_PLAYER
    sta OBJECT_TYPE
    lda #playerSprite / 64
    sta OBJECT_SPRITE
    lda #02
    sta OBJECT_COLOUR
    ldx #00
    !:
    inx
    lda #01
    sta OBJECT_ACTIVE,x
    lda #TYPE_ENEMY
    sta OBJECT_TYPE,x
    lda spritePointers,x
    sta OBJECT_SPRITE,x
    lda #03
    sta OBJECT_COLOUR,x
    cpx #07
    bne !-

    jsr mainLoop                        // Enter the game loop. It never returns in the current program.

checkRaster:                            // Frame-pacing routine: wait for raster line 255.
    lda RASTER                          // Read current VIC-II raster line low byte from $D012 into A.
    cmp #255                          // Compare A with 255; internally performs A-255 and sets flags, without changing A.
    bne checkRaster                     // If Z=0 (not raster line 255), loop and read it again.
    rts                                 // Raster reached 255: return to caller.

mainLoop:                               // Main update loop. One pass is intended roughly once per video frame.
    jsr checkRaster                     // Wait until VIC-II reaches raster line 255.
    jsr updateObjects                   // Update logical enemy objects 1-7 in RAM.
    jsr renderSprites
    jmp mainLoop                        // Repeat forever. JMP is correct here: unlike JSR it does not leak return addresses.

// ------------------------------------------------------------
// Update player position from joystick inputs
// ------------------------------------------------------------

updatePlayer:
        lda STICK_2                     // Read joystick port 2 once and keep the result.
        sta JOY_STATE
        // ------------------------------------------------------------
        // UP
        // ------------------------------------------------------------
        lda JOY_STATE                   // Isolate joystick bit 0: UP. If UP is not pressed, result is non-zero.
        and #%00000001
        bne !down+                      // UP not pressed -> skip the entire UP section.
        lda OBJECT_Y,x                  // Load this player's current Y coordinate.
        cmp #49                         // Are we already at the upper movement limit?
        beq !down+                      // Yes -> don't move any further upward.
        dec OBJECT_Y,x                  // Otherwise move player up one pixel.
    !down:
        // ------------------------------------------------------------
        // DOWN
        // ------------------------------------------------------------
        lda JOY_STATE                   // Isolate joystick bit 1: DOWN.
        and #%00000010
        bne !left+                      // DOWN not pressed -> skip DOWN section.
        lda OBJECT_Y,x                  // Load current Y coordinate.
        cmp #231                      // Are we already at the bottom movement limit?
        beq !left+                      // Yes -> don't move further down.
        inc OBJECT_Y,x                  // Otherwise move player down one pixel.
    !left:
        // ------------------------------------------------------------
        // LEFT
        // ------------------------------------------------------------
        lda JOY_STATE                   // Isolate joystick bit 2: LEFT.
        and #%00000100
        bne !right+                     // LEFT not pressed -> skip LEFT section.
        lda OBJECT_X_MSB,x              // Read the ninth X bit for this logical object. 0 = X is in range 0-255, 1 = X is in range 256-511
        bne !moveLeft+                  // If MSB is 1, x>255, so we cannot be at the left boundary (X=23), safe to move left immediately.
        lda OBJECT_X,x                  // MSB was 0, so now inspect the low X byte.
        cmp #23                         // Are we already at the left boundary?
        beq !right+                     // Yes -> don't move left; branch to RIGHT processing.
    !moveLeft:
        lda OBJECT_X,x                  // Load current low X byte.
        bne !noLeftWrap+                // If low byte is NOT zero, decrementing it will not wrap x, so skip MSB flip. x=0, full coordinate is currently 256 as left is allowed here.
        lda #0                          // We are about to move 256 -> 255.
        sta OBJECT_X_MSB,x              // Clear the ninth X bit before decrementing the low byte.
    !noLeftWrap:
        dec OBJECT_X,x                  // Move left one pixel. Normal example:100 -> 99. Wrap example:low byte 0 -> 255. MSB was just cleared, 256 -> 255.
    !right:
        // ------------------------------------------------------------
        // RIGHT
        // ------------------------------------------------------------
        lda JOY_STATE                   // Isolate joystick bit 3: RIGHT.
        and #%00001000
        bne !fire+                      // RIGHT not pressed -> skip RIGHT section.
        lda OBJECT_X_MSB,x              // Read the ninth X bit.
        beq !moveRight+                 // If MSB is 0, X is below 256, cannot be at the right boundary, safe to move right immediately.
        lda OBJECT_X,x                  // MSB is 1, so inspect the low byte.
        cmp #66                         // Low byte 66 means X = 322
        beq !fire+                      // Already at right boundary -> do not move further right.
    !moveRight:
        inc OBJECT_X,x                  // Move right one pixel. INC updates Z-Flag. Normal example:100 -> 101, Wrap example:255 -> 0, Z-Flag=1
        bne !fire+                      // Branch if the INC result was non-zero. No branch, low byte wrapped 255=>0, x becomes 256
        lda #1
        sta OBJECT_X_MSB,x              // Set the ninth X bit to complete the 255 -> 256 transition.
    !fire:
        // ------------------------------------------------------------
        // FIRE
        // ------------------------------------------------------------
        lda JOY_STATE                   // Reload the stored joystick state.
        and #16                         // Isolate bit 4: FIRE.
        bne !+                          // Fire not pressed -> skip debug effect.
        inc BORDER_COLOUR               // Fire pressed. Inc border colour as a temporary visible test.
    !:
        rts                             // Return to mainLoop.

// ============================================================================
// RENDER LOGICAL OBJECT STATE INTO VIC-II HARDWARE SPRITES
// ============================================================================

renderSprites:
    ldy #00                             // Y = hardware sprite slot
    lda #00
    sta TEMP_MSB

renderLoop:
    lda HW_OBJECT,y                     // Find logical object assigned to this VIC slot.
    tax                                 // X = logical object index.

    lda OBJECT_X_MSB,x                  // Load packed X-MSB flags for logical objects 0-7.
    //and objectBitMask,x               // Test the X-MSB bit belonging to logical object X.
    beq !noMsb+                         // If clear, this object's X coordinate is below 256.

    lda TEMP_MSB                        // Load the hardware X-MSB byte we're building.
    ora HW_BIT_MASK,y                   // Set the bit for the VIC slot rendering this object.
    sta TEMP_MSB                        // Save the updated hardware X-MSB byte.

!noMsb:
    lda OBJECT_SPRITE,x                 // Get the sprite graphic owned by logical object X.
    sta HW_SPRITE_POINTER,y             // Assign that graphic to hardware sprite slot Y.
    lda OBJECT_COLOUR,x
    sta HW_SPRITE_COLOUR,y
    sty TEMP_Y_REG                      // Preserve the hardware slot number.

    lda HW_SPRITE_OFFSET,y              // Convert slot 0-7 into VIC offset 0,2,4...14.
    tay                                 // Y now indexes the VIC coordinate registers.

    lda OBJECT_X,x                      // Read logical object's X position.
    sta SPR_X,y                         // Write it to this hardware sprite's X register.

    lda OBJECT_Y,x                      // Read logical object's Y position.
    sta SPR_Y,y                         // Write it to this hardware sprite's Y register.

    ldy TEMP_Y_REG                      // Restore Y = hardware slot number.

    iny                                 // Next hardware slot.
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
    lda #$ff                            // A = %11111111.
    sta SPRITE_ENABLE                   // $D015: set all eight enable bits, turning sprites 0-7 on.

    // --- Set hardware sprite pointers $07F8-$07FF ---
    // Each VIC sprite pointer is the bitmap address divided by 64.
    // The assembler calculates the values from playerSprite/enemySpriteA/B,
    // so moving the bitmap block does not require hand-editing pointer numbers.

   ldx #$00                             // X = 0: index into the eight sprite-pointer bytes.

pointerLoop:
    lda spritePointers,x                // A = pointer value for this hardware sprite slot.
    sta HW_SPRITE_POINTER,x             // Store into $07F8+X (hardware sprite pointer table).
    inx
    cpx #$08
    bne pointerLoop                     // Yes: fall through. X is now 8.
    // --- Player starting position ---
    lda #146                          // A = initial player X low byte.
    sta OBJECT_X                        // Seed logical object 0 X low byte; no VIC register is touched here.
    lda #200                          // A = initial player Y.
    sta OBJECT_Y                        // Seed logical object 0 Y.
    lda #0
    sta OBJECT_X_MSB                    // Clear X bit 8 for logical objects 0-7.
    // --- Mob starting X positions ---
    lda #31                             // A = first mob's X position.
    ldx #01                             // X = logical object 1, the first enemy.
xposLoop:
    sta OBJECT_X,x                      // Store low X byte in the current logical object.
    clc                                 // Clear carry so the following ADC performs exactly A + 28.
    adc #28                             // A = previous mob X + 28; spaces mobs horizontally.
    inx
    cpx #08
    bne xposLoop                        // Repeat until all seven mob X positions are set.
    // --- Mob starting Y positions ---
    lda #54                             // A = common starting Y coordinate for every enemy object.
    ldx #01                             // X = logical object 1 again.
yposLoop:
    sta OBJECT_Y,x                      // Store Y directly in the current logical object.
    inx                                 // Next logical object.
    cpx #08                             // Reached object 8? Then objects 1-7 are initialised.
    bne yposLoop                        // No: repeat.
    rts                                 // Sprite setup complete; return to init.

// ============================================================================
// MOB UPDATE DISPATCH
// ============================================================================

updateObjects:
    ldx #0                              // Begin with logical object 0.

objectLoop:
    lda OBJECT_ACTIVE,x
    beq nextObject
    lda OBJECT_TYPE,x
    cmp #TYPE_PLAYER
    beq updatePlayerObject
    cmp #TYPE_ENEMY
    beq updateEnemyObject
    jmp nextObject

updatePlayerObject:
    jsr updatePlayer
    jmp nextObject

updateEnemyObject:
    jsr moveEnemy

nextObject:
    inx                                 // Advance to the next object slot.
    cpx #MAX_OBJECTS                    // Have we scanned the entire pool?
    bne objectLoop
    rts

// ============================================================================
// INDIVIDUAL MOB MOVEMENT
// ============================================================================

moveEnemy:
    lda OBJECT_DIR,x                    // Read this object's direction directly
    bne !+                              // Non-zero => this mob's direction bit is set: take left-moving branch.
    beq !++                             // Zero => direction bit clear: take right-moving branch.
                                        // One of these branches must occur; the BEQ is effectively unconditional here.

!:                                      // Local '+' label: current mob is moving LEFT.
    sec                                 // Set Carry before SBC. On 6502, C=1 means "no borrow in".
    lda OBJECT_X,x                      // A = current logical object's low X byte.
    sbc MOB_X_VEL                       // A = A - velocity - (1-C). With SEC and velocity=1, subtract exactly 1.
    sta OBJECT_X,x                      // Store updated low X byte back into logical RAM.

    cmp #255                          // Did low byte become 255? This is the 256->255 crossing when MSB was set.
    beq overflowMob                     // Toggle this object's logical ninth-X bit (256 -> 255 crossing).

    cmp #23                             // Low byte 23 is a possible left reversal coordinate.
    beq checkMobLeftBoundary            // Check logical MSB because low=23 could mean X=23 or X=279.

    rts                                 // No overflow/reversal event: movement for this mob is complete.


!:                                      // Second local '+' label: current mob is moving RIGHT.
    clc                                 // Clear Carry before ADC so addition is exactly A + velocity.
    lda OBJECT_X,x                      // A = current logical object's low X byte.
    adc MOB_X_VEL                       // Add horizontal velocity (currently 1).
    sta OBJECT_X,x                      // Store updated low X byte in logical RAM.

    cmp #0                              // Did low byte wrap 255->0, crossing X=255 -> X=256?
    beq overflowMob                     // Toggle this object's logical ninth-X bit.

    cmp #66                             // Low byte 66 is a possible right reversal coordinate.
    beq checkMobRightBoundary           // Check MSB because low=66 could mean X=66 or X=322.

    rts                                 // Normal movement complete.


overflowMob:                            // Toggle current logical object's ninth X-coordinate bit.
    lda OBJECT_X_MSB,x                  // A = packed X-MSB bits for logical objects 0-7.
    eor #01                             // Toggle 0 <=> 1
    sta OBJECT_X_MSB,x                  // Store new direction
    rts                                 // Return directly to moveMobs (because this routine was reached by branch).


reverseMob:                             // Reverse current mob and drop it down one row.
    lda OBJECT_Y,x                      // A = current logical object's Y coordinate.
    clc                                 // Clear carry so the vertical displacement is exactly 24.
    adc #24                             // A = Y + 24 pixels.
    sta OBJECT_Y,x                      // Store new logical Y coordinate.

    lda OBJECT_DIR,x                    // A = packed direction bits for logical objects 0-7.
    eor #01                             // Toggle left/right
    sta OBJECT_DIR,x                    // Store new direction
    rts                                 // Return to moveMobs.

checkMobRightBoundary:
    lda OBJECT_X_MSB,x                  // Read this object's ninth X bit.
    beq !+                              // 0 => X=66, not right boundary.
    jmp reverseMob                      // 1 => X=322, reverse and descend.
!:
    rts

checkMobLeftBoundary:
    lda OBJECT_X_MSB,x                  // Read this object's ninth X bit.
    bne !+                              // 1 => X=279, not left boundary.
    jmp reverseMob                      // 0 => X=23, reverse and descend.
!:
    rts

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
    .fill MAX_OBJECTS, 0                // $2000-$200F : X low byte for objects 0-15

OBJECT_Y:
    .fill MAX_OBJECTS, 0                // $2010-$201F : Y position for objects 0-15

OBJECT_X_MSB:
    .fill MAX_OBJECTS, 0                // $2020-$2021 : X bit 8 for objects 0-15

OBJECT_DIR:
    .fill MAX_OBJECTS, 0                // $2022-$2023 : one packed direction bit per logical object

OBJECT_ACTIVE:
    .fill MAX_OBJECTS, 0

OBJECT_TYPE:
    .fill MAX_OBJECTS, 0

HW_OBJECT:
    .byte 0,1,2,3,4,5,6,7

HW_SPRITE_OFFSET:
    .byte 0,2,4,6,8,10,12,14

OBJECT_SPRITE:
    .fill MAX_OBJECTS, 0

OBJECT_COLOUR:
    .fill MAX_OBJECTS, 0

// ============================================================================
// SPRITE BITMAP DATA
// ============================================================================

* = $2400                               // Assemble following data beginning at address $2400.
                                        // Each VIC-II sprite occupies a 64-byte slot:
                                        // 63 bytes = 24x21 one-bit bitmap (3 bytes per row x 21 rows),
                                        // byte 64 = unused by the VIC and serves as padding/alignment.

playerSprite:
.byte $00,$00,$00,$7f,$ff,$fe,$40,$18   // Raw bitmap bytes. Each group of 3 bytes represents one 24-pixel sprite row.
.byte $02,$40,$18,$02,$40,$18,$02,$40   // Bits set to 1 are foreground pixels; 0 bits are transparent.
.byte $18,$02,$40,$18,$02,$40,$18,$02   // These data bytes are not CPU instructions; VIC-II reads them directly.
.byte $40,$18,$02,$40,$18,$02,$7f,$ff
.byte $fe,$40,$18,$02,$40,$18,$02,$40
.byte $18,$02,$40,$18,$02,$40,$18,$02
.byte $40,$18,$02,$40,$18,$02,$40,$18
.byte $02,$7f,$ff,$fe,$00,$00,$00,$0a   // Final byte is padding; VIC uses only the first 63 bytes of the slot.

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
    .byte $00                           // 64th byte padding

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
    .byte $00                           // 64th byte padding
