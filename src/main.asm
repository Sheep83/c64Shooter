.filenamespace test                     // KickAssembler namespace: labels/symbols in this file live under "test".
:BasicUpstart2(init)                    // Generate a BASIC stub at $0801 that executes SYS <address of init>.

#import "variables.asm"                 // Import the symbolic names for VIC-II/CIA registers and our RAM variables.
.const MAX_OBJECTS = 16                 // Maximum number of logical objects.
.const TYPE_NONE   = 0                  // Object slot is unused.
.const TYPE_PLAYER = 1                  // Object is the player.
.const TYPE_ENEMY  = 2                  // Object is an enemy.
.const MAX_EVENTS = MAX_OBJECTS - 8     // At most 8 objects need multiplexing.
.const FLAG_RENDER    = %00000001
.const FLAG_COLLIDE   = %00000010

// ============================================================================
// CURRENT ENGINE SHAPE
// ============================================================================
//
// Logical objects live in RAM (OBJECT_X, OBJECT_Y, etc.).  They are not tied
// permanently to any of the C64's eight hardware sprites.
//
// Late in each PAL frame:
//   updateObjects()             - change logical game state
//   buildSortedObjectList()     - collect active object numbers
//   sortObjectsByY()            - order those numbers from top to bottom
//   prepareNinthSpriteEvent()   - decide how the ninth object can reuse a slot
//
// At the start of the next frame:
//   renderSprites()             - map the first eight objects to VIC sprites 0-7
//   armPreparedEvent()          - tell VIC-II which raster line should IRQ
//
// Later, asynchronously:
//   multiplexIRQ()              - VIC-II reaches that raster line; the CPU
//                                 temporarily leaves mainLoop, rewrites one
//                                 hardware sprite for object #9, acknowledges
//                                 the IRQ, then returns through the KERNAL.
//
// This is deliberately still a ONE-EVENT prototype.  It proves the separation
// between logical objects and hardware sprites before we generalise it into a
// full multiplexer.


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
    lda #01                             // Init player object
    sta OBJECT_ACTIVE                   // Mark player object active.
    lda #TYPE_PLAYER                    // Load player object type.
    sta OBJECT_TYPE                     // Set object 0 as the player.
    lda #playerSprite / 64              // Load player sprite pointer.
    sta OBJECT_SPRITE                   // Store player's sprite graphic.
    lda #02                             // Load player colour.
    sta OBJECT_COLOUR                   // Store player colour.
    ldx #00                             // Start before first enemy slot.
    !:                                  // Local loop label.
    inx                                 // Advance to next enemy object.
    lda #01                             // Load active flag.
    sta OBJECT_ACTIVE,x                 // Mark enemy object active.
    lda #TYPE_ENEMY                     // Load enemy object type.
    sta OBJECT_TYPE,x                   // Set current object as enemy.
    lda spritePointers,x                // Load this enemy's sprite pointer.
    sta OBJECT_SPRITE,x                 // Store enemy sprite graphic.
    lda #03                             // Load enemy colour.
    sta OBJECT_COLOUR,x                 // Store enemy colour.
    cpx #15                             // Finished enemy object 8?
    bne !-                              // No: initialise next enemy.

    jsr mainLoop                        // Enter the game loop. It never returns in the current program.

mainLoop:
    // The frame is deliberately split into two phases.
    //
    // 1. During raster lines 256-311 (the bottom of the PAL frame), update
    //    logical game state and prepare the sprite layout for the NEXT frame.
    //    Doing the variable-duration work here prevents us from missing an
    //    early sprite such as an enemy at Y=40.
    //
    // 2. At raster 0-19, copy the first eight sorted objects to the VIC-II and
    //    arm the one prepared raster event.  The IRQ later recycles one of
    //    those hardware sprites for the ninth logical object.
    //
    // waitForFrameEnd followed by waitForFrameStart also guarantees that this
    // loop cannot update the game twice during the same frame.

    jsr waitForFrameEnd

    jsr updateObjects
    jsr buildSortedObjectList
    jsr sortObjectsByY
    //jsr buildBatchSpriteSchedule

    jsr waitForFrameStart

    jsr renderSprites
    jsr armFirstBatch

    jmp mainLoop

// ------------------------------------------------------------
// Update player position from joystick inputs
// ------------------------------------------------------------

updatePlayer:
        lda STICK_2                     // Read joystick port 2 once and keep the result.
        sta JOY_STATE                   // Save joystick state for this update.
        // ------------------------------------------------------------
        // UP
        // ------------------------------------------------------------
        lda JOY_STATE                   // Isolate joystick bit 0: UP. If UP is not pressed, result is non-zero.
        and #%00000001                  // Keep only joystick UP bit.
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
        and #%00000010                  // Keep only joystick DOWN bit.
        bne !left+                      // DOWN not pressed -> skip DOWN section.
        lda OBJECT_Y,x                  // Load current Y coordinate.
        cmp #230                      // Are we already at the bottom movement limit?
        beq !left+                      // Yes -> don't move further down.
        inc OBJECT_Y,x                  // Otherwise move player down one pixel.
    !left:
        // ------------------------------------------------------------
        // LEFT
        // ------------------------------------------------------------
        lda JOY_STATE                   // Isolate joystick bit 2: LEFT.
        and #%00000100                  // Keep only joystick LEFT bit.
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
        and #%00001000                  // Keep only joystick RIGHT bit.
        bne !fire+                      // RIGHT not pressed -> skip RIGHT section.
        lda OBJECT_X_MSB,x              // Read the ninth X bit.
        beq !moveRight+                 // If MSB is 0, X is below 256, cannot be at the right boundary, safe to move right immediately.
        lda OBJECT_X,x                  // MSB is 1, so inspect the low byte.
        cmp #65                         // Low byte 66 means X = 322
        beq !fire+                      // Already at right boundary -> do not move further right.
    !moveRight:
        inc OBJECT_X,x                  // Move right one pixel. INC updates Z-Flag. Normal example:100 -> 101, Wrap example:255 -> 0, Z-Flag=1
        bne !fire+                      // Branch if the INC result was non-zero. No branch, low byte wrapped 255=>0, x becomes 256
        lda #1                          // Load high X bit value.
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
    lda SORTED_COUNT
    cmp #8
    bcc !countReady+

    lda #8                              // More than 8 objects:
                                        // first pass can render only 8.

!countReady:
    sta RENDER_COUNT

    beq !none+                          // No active objects at all.

    ldy #00                             // Y = hardware sprite slot.
    lda #00
    sta TEMP_MSB

renderLoop:
    lda SORTED_OBJECTS,y                // Find logical object assigned to this VIC slot.
    tax                                 // X = logical object index.

    lda OBJECT_X_MSB,x                  // Read this logical object's ninth X bit.
    beq !noMsb+                         // If clear, this object's X coordinate is below 256.

    lda TEMP_MSB                        // Load the hardware X-MSB byte we're building.
    ora HW_BIT_MASK,y                   // Set the bit for the VIC slot rendering this object.
    sta TEMP_MSB                        // Save the updated hardware X-MSB byte.

!noMsb:
    lda OBJECT_SPRITE,x                 // Get the sprite graphic owned by logical object X.
    sta HW_SPRITE_POINTER,y             // Assign that graphic to hardware sprite slot Y.
    lda OBJECT_COLOUR,x                 // Load this object's colour.
    sta HW_SPRITE_COLOUR,y              // Set hardware sprite colour.
    sty TEMP_Y_REG                      // Preserve the hardware slot number.

    lda HW_SPRITE_OFFSET,y              // Convert slot 0-7 into VIC offset 0,2,4...14.
    tay                                 // Y now indexes the VIC coordinate registers.

    lda OBJECT_X,x                      // Read logical object's X position.
    sta SPR_X,y                         // Write it to this hardware sprite's X register.

    lda OBJECT_Y,x                      // Read logical object's Y position.
    sta SPR_Y,y                         // Write it to this hardware sprite's Y register.

    ldy TEMP_Y_REG                      // Restore Y = hardware slot number.

    iny
    cpy RENDER_COUNT
    bne renderLoop

    lda TEMP_MSB
    sta SPRITE_OVERFLOW_REGISTER
    rts

!none:
    lda #0
    sta SPRITE_OVERFLOW_REGISTER
    rts

// ============================================================================
// SPRITE INITIALISATION
// ============================================================================

setupSprites:

    // --- Enable all eight hardware sprites ---
    lda #$ff                            // A = %11111111.
    sta SPRITE_ENABLE                   // $D015: set all eight enable bits, turning sprites 0-7 on.
    // --- Player starting position ---
    lda #146                          // A = initial player X low byte.
    sta OBJECT_X                        // Seed logical object 0 X low byte; no VIC register is touched here.
    lda #200                          // A = initial player Y.
    sta OBJECT_Y                        // Seed logical object 0 Y.
    lda #0                              // Load clear ninth X bit.
    sta OBJECT_X_MSB                    // Clear X bit 8 for logical object 0.
    // --- Mob starting X positions ---
    lda #31                             // A = first mob's X position.
    ldx #01                             // X = logical object 1, the first enemy.
xposLoop:
    sta OBJECT_X,x                      // Store low X byte in the current logical object.
    clc                                 // Clear carry so the following ADC performs exactly A + 28.
    adc #28                             // A = previous mob X + 28; spaces mobs horizontally.
    inx                                 // Advance to next enemy object.
    cpx #16                             // Finished enemy object 8?
    bne xposLoop                        // Repeat until all eight enemy X positions are set.
    // --- Mob starting Y positions ---
    lda #40                             // A = common starting Y coordinate for every enemy object.
    ldx #01                             // X = logical object 1 again.
yposLoop:
    sta OBJECT_Y,x                      // Store Y directly in the current logical object.
    clc
    adc #12
    inx                                 // Next logical object.
    cpx #16                             // Reached object 8? Then objects 1-8 are initialised.
    bne yposLoop                        // No: repeat.
    rts                                 // Sprite setup complete; return to init.

// ============================================================================
// MOB UPDATE DISPATCH
// ============================================================================

updateObjects:
    ldx #0                              // Begin with logical object 0.

objectLoop:
    lda OBJECT_ACTIVE,x                 // Read current object's active flag.
    beq nextObject                      // Inactive: skip this object.
    lda OBJECT_TYPE,x                   // Read current object's type.
    cmp #TYPE_PLAYER                    // Is this the player?
    beq updatePlayerObject              // Yes: run player update.
    cmp #TYPE_ENEMY                     // Is this an enemy?
    beq updateEnemyObject               // Yes: run enemy update.
    jmp nextObject                      // Unknown type: skip object.

updatePlayerObject:
    jsr updatePlayer                    // Update player object in X.
    jmp nextObject                      // Continue object scan.

updateEnemyObject:
    jsr moveEnemy                       // Update enemy object in X.

nextObject:
    inx                                 // Advance to the next object slot.
    cpx #MAX_OBJECTS                    // Have we scanned the entire pool?
    bne objectLoop                      // No: process next object.
    rts                                 // Object update pass complete.

// ============================================================================
// INDIVIDUAL MOB MOVEMENT
// ============================================================================

moveEnemy:
    lda OBJECT_DIR,x                    // Read this object's direction directly
    bne !+                              // Non-zero => this mob's direction bit is set: take left-moving branch.
    beq !++                             // Zero => direction bit clear: take right-moving branch. One of these branches must occur; the BEQ is effectively unconditional here.
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
    lda OBJECT_X_MSB,x                  // Read this logical object's ninth X bit.
    eor #01                             // Toggle 0 <=> 1
    sta OBJECT_X_MSB,x                  // Store new direction
    rts                                 // Return directly to moveMobs (because this routine was reached by branch).


reverseMob:                             // Reverse horizontal direction at a screen edge.
    lda OBJECT_DIR,x                    // Read this logical object's direction.
    eor #01                             // Toggle left/right
    sta OBJECT_DIR,x                    // Store new direction
    rts                                 // Return to moveMobs.

checkMobRightBoundary:
    lda OBJECT_X_MSB,x                  // Read this object's ninth X bit.
    beq !+                              // 0 => X=66, not right boundary.
    jmp reverseMob                      // 1 => X=322, reverse direction.
!:                                      // Local continuation label.
    rts                                 // Right boundary check complete.

checkMobLeftBoundary:
    lda OBJECT_X_MSB,x                  // Read this object's ninth X bit.
    bne !+                              // 1 => X=279, not left boundary.
    jmp reverseMob                      // 0 => X=23, reverse direction.
!:                                      // Local continuation label.
    rts                                 // Left boundary check complete.

// ============================================================================
// Sort objects by Y value
// ============================================================================
buildSortedObjectList:
    lda #0
    sta SORTED_COUNT

    ldx #0

!collect:
    lda OBJECT_ACTIVE,x
    beq !next+

    ldy SORTED_COUNT
    txa
    sta SORTED_OBJECTS,y

    inc SORTED_COUNT

!next:
    inx
    cpx #MAX_OBJECTS
    bne !collect-

    rts

sortObjectsByY:
    lda SORTED_COUNT
    cmp #2
    bcc !done+

    ldy #1

!outer:
    lda SORTED_OBJECTS,y
    sta TEMP_OBJECT

    tax
    lda OBJECT_Y,x
    sta TEMP_SORT_Y

    dey

!inner:
    lda SORTED_OBJECTS,y
    tax

    lda OBJECT_Y,x
    cmp TEMP_SORT_Y
    bcc !insert+
    beq !insert+

    lda SORTED_OBJECTS,y
    sta SORTED_OBJECTS + 1,y

    dey
    bpl !inner-

    lda TEMP_OBJECT
    sta SORTED_OBJECTS

    jmp !next+

!insert:
    lda TEMP_OBJECT
    sta SORTED_OBJECTS + 1,y

!next:
    iny
    iny
    cpy SORTED_COUNT
    bcc !outer-

!done:
    rts

// ============================================================================
// buildBatchSpriteSchedule
// ============================================================================
//
// Builds the multiplex schedule for logical objects beyond the first eight.
//
// IMPORTANT:
//   This routine does NOT touch VIC registers.
//   The existing single-event multiplexer remains responsible for the live
//   display while we test this.
//
// For each additional object we need:
//
//      old sprite finished
//              |
//              v
//      SLOT_FREE_RASTER
//              <=
//      chosen IRQ raster
//              <=
//      OBJECT_Y - 12
//              ^
//              |
//      new sprite prepared in time
//
// Several assignments can therefore share one IRQ whenever their valid
// raster ranges overlap.
//
// The resulting schedule is stored in:
//
//      BATCH_RASTER[]
//      BATCH_FIRST_ASSIGN[]
//      BATCH_ASSIGN_COUNT[]
//
// with the actual slot/object pairs in:
//
//      ASSIGN_SLOT[]
//      ASSIGN_OBJECT[]
//
// ============================================================================

buildBatchSpriteSchedule:

    // Start with an empty schedule.

    lda #0
    sta BATCH_COUNT
    sta BATCH_INDEX
    sta SCHED_ASSIGN_INDEX


    // ------------------------------------------------------------------------
    // Work out when each of the eight VIC sprite slots becomes reusable.
    //
    // renderSprites maps:
    //
    //      SORTED_OBJECTS[0] -> VIC slot 0
    //      SORTED_OBJECTS[1] -> VIC slot 1
    //      ...
    //
    // A normal sprite is 21 raster lines tall. We retain our existing
    // conservative 24-line reuse distance.
    // ------------------------------------------------------------------------

    ldy #0

!initSlots:

    cpy RENDER_COUNT
    bcs !unusedSlot+

    lda SORTED_OBJECTS,y
    tax

    lda OBJECT_Y,x
    clc
    adc #24

    // If Y+24 crosses 255, don't attempt to reuse this slot during the
    // current low-raster scheduler.

    bcs !unavailableSlot+

    sta SLOT_FREE_RASTER,y
    jmp !nextInit+


!unusedSlot:

    // No initial object occupies this VIC slot.
    // It is available immediately.

    lda #0
    sta SLOT_FREE_RASTER,y
    jmp !nextInit+


!unavailableSlot:

    lda #$ff
    sta SLOT_FREE_RASTER,y


!nextInit:

    iny
    cpy #8
    bne !initSlots-


    // ------------------------------------------------------------------------
    // If there are at most eight objects, renderSprites can display all of
    // them at frame start and no multiplex schedule is required.
    // ------------------------------------------------------------------------

    lda SORTED_COUNT
    cmp #9
    bcs !needsSchedule+

    jmp !done+

!needsSchedule:


    // SORTED_OBJECTS[0..7] are the initial eight.
    // Start scheduling at SORTED_OBJECTS[8].

    lda #8
    sta SCHED_OBJECT_INDEX


// ============================================================================
// Begin a new batch.
// ============================================================================

!startBatch:

    lda SCHED_OBJECT_INDEX
    cmp SORTED_COUNT
    bcc !objectsRemain+

    jmp !done+

!objectsRemain:

    lda #0
    sta SCHED_BATCH_SIZE
    sta SCHED_BATCH_EARLIEST

    lda #$ff
    sta SCHED_BATCH_LATEST


// ============================================================================
// Try to add the current object to this batch.
// ============================================================================

!tryObject:

    ldy SCHED_OBJECT_INDEX

    lda SORTED_OBJECTS,y
    sta TEMP_OBJECT
    tax


    // ------------------------------------------------------------------------
    // Latest acceptable IRQ line for this object:
    //
    //      OBJECT_Y - 12
    //
    // 12 is our already-tested IRQ preparation margin.
    // ------------------------------------------------------------------------

    lda OBJECT_Y,x
    cmp #12
    bcs !deadlineOk+

    jmp !cannotSchedule+

!deadlineOk:

    sec
    sbc #12
    sta TEMP_OBJECT_Y             // Scratch now contains this object's deadline.


    // ------------------------------------------------------------------------
    // Find the BEST available VIC slot.
    //
    // A candidate slot must:
    //
    //      SLOT_FREE_RASTER <= object deadline
    //
    // and, if this batch already contains assignments, its free time must
    // still overlap the batch's common timing window.
    //
    // Of the valid candidates, choose the one with the LATEST free raster.
    //
    // Why latest?
    //
    // If slots are free at 60, 80 and 100 and this object can use any of
    // them, consuming the 100 slot leaves 60 and 80 available for later
    // objects with tighter requirements.
    // ------------------------------------------------------------------------

    lda #$ff
    sta SCHED_SELECTED_SLOT

    lda #0
    sta SCHED_SELECTED_FREE

    ldy #0


!findSlot:

    lda SLOT_FREE_RASTER,y

    cmp #$ff
    beq !nextSlot+

    // Must be free no later than this object's deadline.

    cmp TEMP_OBJECT_Y
    bcc !checkBatch+
    beq !checkBatch+

    jmp !nextSlot+


!checkBatch:

    // If a batch already exists, the candidate's free raster must not be
    // later than the batch's current latest permissible IRQ line.

    ldx SCHED_BATCH_SIZE
    beq !candidate+

    cmp SCHED_BATCH_LATEST
    bcc !candidate+
    beq !candidate+

    jmp !nextSlot+


!candidate:

    // Prefer the candidate with the latest free raster.

    cmp SCHED_SELECTED_FREE
    bcc !nextSlot+

    sta SCHED_SELECTED_FREE
    sty SCHED_SELECTED_SLOT


!nextSlot:

    iny
    cpy #8
    bne !findSlot-


    // Did we find anything?

    lda SCHED_SELECTED_SLOT
    cmp #$ff
    beq !noSlot+


    // ------------------------------------------------------------------------
    // Work out the common timing interval after adding this assignment.
    //
    // earliest = max(current earliest, selected slot free)
    // latest   = min(current latest, object deadline)
    // ------------------------------------------------------------------------

    lda SCHED_SELECTED_FREE
    cmp SCHED_BATCH_EARLIEST
    bcc !earliestReady+
    sta SCHED_BATCH_EARLIEST

!earliestReady:

    lda TEMP_OBJECT_Y
    cmp SCHED_BATCH_LATEST
    bcs !latestReady+
    sta SCHED_BATCH_LATEST

!latestReady:


    // ------------------------------------------------------------------------
    // Record the assignment.
    // ------------------------------------------------------------------------

    ldx SCHED_ASSIGN_INDEX

    lda SCHED_SELECTED_SLOT
    sta ASSIGN_SLOT,x

    lda TEMP_OBJECT
    sta ASSIGN_OBJECT,x

    inc SCHED_ASSIGN_INDEX
    inc SCHED_BATCH_SIZE


    // ------------------------------------------------------------------------
    // This hardware slot will now contain the new object.
    //
    // Its next safe reuse point becomes:
    //
    //      OBJECT_Y + 24
    // ------------------------------------------------------------------------

    ldx TEMP_OBJECT

    lda OBJECT_Y,x
    clc
    adc #24

    ldy SCHED_SELECTED_SLOT

    bcs !markUnavailable+

    sta SLOT_FREE_RASTER,y
    jmp !assignmentDone+


!markUnavailable:

    lda #$ff
    sta SLOT_FREE_RASTER,y


!assignmentDone:

    inc SCHED_OBJECT_INDEX

    // Have we scheduled every object?

    lda SCHED_OBJECT_INDEX
    cmp SORTED_COUNT
    bcs !finishBatch+

    // Otherwise see whether the next object can join this batch.

    jmp !tryObject-


// ============================================================================
// No slot can accept this object in the CURRENT batch.
// ============================================================================

!noSlot:

    // If the current batch already contains assignments, finish it.
    //
    // The same object will then be reconsidered as the first object of a new
    // batch.

    lda SCHED_BATCH_SIZE
    bne !finishBatch+


    // If even an empty batch cannot find a slot, this object genuinely cannot
    // be represented this frame with the available eight VIC sprites.
    //
    // Skip it rather than corrupting the schedule.

!cannotSchedule:

    inc SCHED_OBJECT_INDEX

    lda SCHED_OBJECT_INDEX
    cmp SORTED_COUNT
    bcs !done+

    jmp !startBatch-


// ============================================================================
// Commit the completed batch.
// ============================================================================

!finishBatch:

    lda SCHED_BATCH_SIZE
    bne !commitBatch+

    jmp !startBatch-

!commitBatch:


    ldx BATCH_COUNT


    // ------------------------------------------------------------------------
    // Run the batch at the LATEST raster line common to every assignment.
    //
    // This maximises the time available for outgoing sprites to finish while
    // preserving the 12-line lead for incoming sprites.
    // ------------------------------------------------------------------------

    lda SCHED_BATCH_LATEST
    sta BATCH_RASTER,x


    // First assignment = current assignment index - batch size.

    lda SCHED_ASSIGN_INDEX
    sec
    sbc SCHED_BATCH_SIZE
    sta BATCH_FIRST_ASSIGN,x


    lda SCHED_BATCH_SIZE
    sta BATCH_ASSIGN_COUNT,x

    inc BATCH_COUNT


    // If objects remain, start another batch.
    //
    // Notice that SCHED_OBJECT_INDEX was NOT incremented when !noSlot caused
    // us to finish a batch. Therefore that object is reconsidered here.

    lda SCHED_OBJECT_INDEX
    cmp SORTED_COUNT
    bcs !done+

    jmp !startBatch-

!done:
    rts

// ============================================================================
// Batch multiplex IRQ - PHASE 1
// ============================================================================
//
// Executes every slot -> object assignment belonging to BATCH 0.
//
// For this first live test we deliberately stop after the first batch.
// Later we will chain to BATCH 1, BATCH 2, etc.
// ============================================================================

multiplexIRQ:

    lda IRQ_STATUS
    and #%00000001
    beq !notRaster+

    // We're only executing batch zero in this test.
    ldx #0

    // Y = first assignment belonging to this batch.
    lda BATCH_FIRST_ASSIGN,x
    tay

    // Work out the assignment index immediately after this batch.
    //
    // TEMP_OBJECT_Y is safe scratch here:
    //
    //     end = first + count

    clc
    adc BATCH_ASSIGN_COUNT,x
    sta TEMP_OBJECT_Y


// ---------------------------------------------------------------------------
// Execute one assignment.
// ---------------------------------------------------------------------------

!assignmentLoop:

    // Preserve the assignment-table index while we use Y for VIC slot work.
    sty TEMP_Y_REG

    // Which hardware slot are we rewriting?
    lda ASSIGN_SLOT,y
    sta SCHED_SELECTED_SLOT

    // Which logical object will occupy it?
    lda ASSIGN_OBJECT,y
    tax


    // ------------------------------------------------------------------------
    // Sprite graphic and colour.
    // ------------------------------------------------------------------------

    ldy SCHED_SELECTED_SLOT

    lda OBJECT_SPRITE,x
    sta HW_SPRITE_POINTER,y

    lda OBJECT_COLOUR,x
    sta HW_SPRITE_COLOUR,y


    // ------------------------------------------------------------------------
    // X / Y position.
    //
    // VIC sprite coordinate registers are interleaved:
    //
    //     slot 0 -> offsets 0,1
    //     slot 1 -> offsets 2,3
    //     ...
    // ------------------------------------------------------------------------

    lda HW_SPRITE_OFFSET,y
    tay

    lda OBJECT_X,x
    sta SPR_X,y

    lda OBJECT_Y,x
    sta SPR_Y,y


    // ------------------------------------------------------------------------
    // Update this hardware sprite's ninth X bit.
    // ------------------------------------------------------------------------

    ldy SCHED_SELECTED_SLOT

    lda SPRITE_OVERFLOW_REGISTER
    and HW_CLEAR_MASK,y
    sta SPRITE_OVERFLOW_REGISTER

    lda OBJECT_X_MSB,x
    beq !msbDone+

    lda SPRITE_OVERFLOW_REGISTER
    ora HW_BIT_MASK,y
    sta SPRITE_OVERFLOW_REGISTER

!msbDone:


    // ------------------------------------------------------------------------
    // Restore assignment index and move to the next assignment.
    // ------------------------------------------------------------------------

    ldy TEMP_Y_REG
    iny

    cpy TEMP_OBJECT_Y
    bne !assignmentLoop-


    // ------------------------------------------------------------------------
    // Acknowledge this raster IRQ.
    // ------------------------------------------------------------------------

    lda #%00000001
    sta IRQ_STATUS


    // ------------------------------------------------------------------------
    // PHASE 1 ONLY:
    //
    // Disable raster IRQs after batch zero.
    //
    // Later this becomes:
    //
    //     advance BATCH_INDEX
    //     arm BATCH_RASTER[next]
    //
    // ------------------------------------------------------------------------

    lda IRQ_ENABLE
    and #%11111110
    sta IRQ_ENABLE


!notRaster:

    jmp $ea31

// ============================================================================
// Prepare the single multiplex event used by the current prototype
//
// Builds a frozen description of the ninth sprite event in RAM.
// Does NOT arm an IRQ or alter any VIC-II state.
// ============================================================================

prepareNinthSpriteEvent:

    lda #0
    sta PREP_EVENT_VALID                // Assume no usable event until proven otherwise.

    lda #$ff
    sta PREP_EVENT_SLOT
    sta PREP_EVENT_OBJECT               // Helpful when inspecting RAM in the monitor.

    lda SORTED_COUNT
    cmp #9
    bcc !done+                          // Fewer than 9 objects: no multiplexing required.

    lda SORTED_OBJECTS + 8              // Ninth object in vertical order.
    sta PREP_EVENT_OBJECT

    tax
    lda OBJECT_Y,x
    sta TEMP_OBJECT_Y                   // Y of object waiting to be rendered.

    ldy #0                              // Begin searching hardware slots 0-7.

!findSlot:
    lda SORTED_OBJECTS,y                // Object initially assigned to this hardware slot.
    tax

    lda OBJECT_Y,x
    clc
    adc #24
    bcs !nextSlot+                   // Safe point is after raster 255:
                                 // don't use this slot in this simple event search.

    cmp TEMP_OBJECT_Y
    bcc !slotFound+

!nextSlot:
    iny
    cpy #8
    bne !findSlot-

    lda #$ff
    sta PREP_EVENT_OBJECT               // No legal slot: discard candidate.
    rts

!slotFound:
    sty PREP_EVENT_SLOT                  // Hardware slot that will be recycled.

    // Trigger comfortably before the waiting object reaches its Y position.
    // A four-line lead occasionally flickered because another IRQ could delay
    // ours; twelve lines proved stable in testing.
    lda TEMP_OBJECT_Y
    sec
    sbc #12
    sta PREP_EVENT_RASTER

    lda #1
    sta PREP_EVENT_VALID

!done:
    rts

// ============================================================================
// Arm first sprite batch
// ============================================================================
//
// Arms BATCH 0 only.
//
// The IRQ itself currently executes that batch and then disables raster IRQs.
// ============================================================================

armFirstBatch:

    sei

    // Disable raster IRQ while configuring it.
    lda IRQ_ENABLE
    and #%11111110
    sta IRQ_ENABLE


    // No batches this frame?
    lda BATCH_COUNT
    beq !done+


    // Start with batch zero.
    lda #0
    sta BATCH_INDEX


    // Install batch IRQ handler.
    lda #<multiplexIRQ
    sta IRQ_VECTOR

    lda #>multiplexIRQ
    sta IRQ_VECTOR + 1


    // Current scheduler only creates raster events below 256.
    lda VIC_CONTROL_1
    and #%01111111
    sta VIC_CONTROL_1


    // Arm first batch raster.
    ldx #0
    lda BATCH_RASTER,x
    sta RASTER


    // Clear any stale raster IRQ flag.
    lda #%00000001
    sta IRQ_STATUS


    // Enable VIC raster IRQ.
    lda IRQ_ENABLE
    ora #%00000001
    sta IRQ_ENABLE


!done:

    cli
    rts

// ============================================================================
// Establish frame lock
// ============================================================================
waitForFrameStart:

!wait:
    lda VIC_CONTROL_1
    bmi !wait-                       // Bit 7 set = raster 256-311.

    lda RASTER
    cmp #20
    bcs !wait-                       // Wait until raster 0-19 of genuine next frame.

    rts

waitForFrameEnd:

!wait:
    lda VIC_CONTROL_1
    bpl !wait-                       // Wait until raster bit 8 becomes 1:
                                    // we've entered raster 256-311.
    rts

// ============================================================================
// SPRITE LOOKUP POINTER TABLE
// ============================================================================

spritePointers:
    .byte playerSprite / 64     // Object 0
    .byte enemySpriteA / 64     // Object 1
    .byte enemySpriteB / 64     // Object 2
    .byte enemySpriteA / 64     // Object 3
    .byte enemySpriteB / 64     // Object 4
    .byte enemySpriteA / 64     // Object 5
    .byte enemySpriteB / 64     // Object 6
    .byte enemySpriteA / 64     // Object 7
    .byte enemySpriteB / 64     // Object 8
    .byte enemySpriteA / 64     // Object 9
    .byte enemySpriteB / 64     // Object 10
    .byte enemySpriteA / 64     // Object 11
    .byte enemySpriteB / 64     // Object 12
    .byte enemySpriteA / 64     // Object 13
    .byte enemySpriteB / 64     // Object 14
    .byte enemySpriteA / 64     // Object 15

// ============================================================================
// Read Only Engine Lookup Tables
// ============================================================================
* = $1f00
HW_BIT_MASK:
    .byte %00000001                     // Hardware sprite 0 MSB mask.
    .byte %00000010                     // Hardware sprite 1 MSB mask.
    .byte %00000100                     // Hardware sprite 2 MSB mask.
    .byte %00001000                     // Hardware sprite 3 MSB mask.
    .byte %00010000                     // Hardware sprite 4 MSB mask.
    .byte %00100000                     // Hardware sprite 5 MSB mask.
    .byte %01000000                     // Hardware sprite 6 MSB mask.
    .byte %10000000                     // Hardware sprite 7 MSB mask.

HW_CLEAR_MASK:
    .byte %11111110
    .byte %11111101
    .byte %11111011
    .byte %11110111
    .byte %11101111
    .byte %11011111
    .byte %10111111
    .byte %01111111

LOOKUP_TABLES_END:

.if (LOOKUP_TABLES_END > $2000) {
    .error "Lookup tables overlap engine runtime state"
}

// ---------------------------------------------------------
// LOGICAL OBJECT STATE POOL
// ---------------------------------------------------------

* = $2000

OBJECT_X:
    .fill MAX_OBJECTS, 0                // $2000-$200F : X low byte for objects 0-15

OBJECT_Y:
    .fill MAX_OBJECTS, 0                // $2010-$201F : Y position for objects 0-15

OBJECT_X_MSB:
    .fill MAX_OBJECTS, 0                // $2020-$202F : X bit 8 for objects 0-15

OBJECT_DIR:
    .fill MAX_OBJECTS, 0                // $2030-$203F : direction for objects 0-15

OBJECT_ACTIVE:
    .fill MAX_OBJECTS, 0                // Object active flags.

OBJECT_TYPE:
    .fill MAX_OBJECTS, 0                // Object type values.

HW_SPRITE_OFFSET:
    .byte 0,2,4,6,8,10,12,14            // VIC X/Y register offsets by slot.

OBJECT_SPRITE:
    .fill MAX_OBJECTS, 0                // Sprite pointer owned by each object.

OBJECT_COLOUR:
    .fill MAX_OBJECTS, 0                // Sprite colour owned by each object.

SORTED_OBJECTS:
    .fill MAX_OBJECTS, $ff

SORTED_COUNT:
    .byte 0

PREP_EVENT_VALID:
    .byte 0                  // 0 = no multiplex event this frame, 1 = event prepared

PREP_EVENT_RASTER:
    .byte 0                  // Raster line at which slot becomes reusable

PREP_EVENT_SLOT:
    .byte $ff                // Hardware sprite slot to recycle

PREP_EVENT_OBJECT:
    .byte $ff                // Logical object to put into that slot

// ============================================================================
// FUTURE BATCH SPRITE SCHEDULE
// ============================================================================
//
// A batch is one raster IRQ.
//
// Each batch can update one or more hardware sprite slots.
// This lets several logical objects be installed during a single IRQ when
// their safe timing windows overlap.
//
// Example:
//
//   batch 0 @ raster 88
//      slot 0 -> object 8
//      slot 1 -> object 9
//      slot 2 -> object 10
//
//   batch 1 @ raster 148
//      slot 0 -> object 11
//      slot 3 -> object 12
//
// With 16 logical objects:
//   - first 8 can be rendered at frame start
//   - at most 8 further assignments are needed
//   - therefore at most 8 batches are ever required
// ============================================================================

BATCH_COUNT:
    .byte 0                              // Number of raster batches this frame.

BATCH_INDEX:
    .byte 0                              // Batch currently being executed by IRQ.

BATCH_RASTER:
    .fill MAX_EVENTS, 0                  // Raster line for each batch.

BATCH_FIRST_ASSIGN:
    .fill MAX_EVENTS, $ff                // First assignment belonging to batch.

BATCH_ASSIGN_COUNT:
    .fill MAX_EVENTS, 0                  // Number of assignments in batch.

ASSIGN_SLOT:
    .fill MAX_EVENTS, $ff                // Hardware slot for each assignment.

ASSIGN_OBJECT:
    .fill MAX_EVENTS, $ff                // Logical object for each assignment.

SLOT_FREE_RASTER:
    .fill 8, $ff                         // Earliest safe reuse point for each VIC slot.


// ---------------------------------------------------------------------------
// Scheduler working state
//
// This is ordinary RAM rather than more zero-page scratch. Scheduler code
// runs outside the raster-critical IRQ, so readability is more important than
// saving a cycle here.
// ---------------------------------------------------------------------------

SCHED_OBJECT_INDEX:
    .byte 0                              // SORTED_OBJECTS entry being considered.

SCHED_ASSIGN_INDEX:
    .byte 0                              // Next free ASSIGN_* entry.

SCHED_BATCH_SIZE:
    .byte 0                              // Assignments currently in working batch.

SCHED_BATCH_EARLIEST:
    .byte 0                              // Earliest raster common to current batch.

SCHED_BATCH_LATEST:
    .byte $ff                            // Latest raster common to current batch.

SCHED_SELECTED_SLOT:
    .byte $ff                            // Candidate hardware slot.

SCHED_SELECTED_FREE:
    .byte $ff                            // Candidate slot's free raster.

RENDER_COUNT:
    .byte 0

OBJECT_FLAGS:
    .fill MAX_OBJECTS, 0

ENGINE_STATE_END:

.if (ENGINE_STATE_END > $2400) {
    .error "Engine state overlaps sprite bitmap data"
}




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
