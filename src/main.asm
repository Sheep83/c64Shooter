.filenamespace test
:BasicUpstart2(init)

#import "variables.asm"

.const MAX_OBJECTS = 16
.const TYPE_PLAYER = 1
.const TYPE_ENEMY  = 2

.const DEBUG_SCREEN = $0400
.const DEBUG_COLOUR = $d800
.const DEBUG_FRAMES = 50
.const PATTERN_DIVE_LEFT  = 0
.const PATTERN_DIVE_RIGHT = 1
.const PATTERN_ZIGZAG     = 2
.const PATTERN_SWEEP      = 3

.const FORMATION_COUNT = 4
.const PATTERN_COUNT   = 4
.const CIA1_TIMER_A_LO = $dc04
.const WAVE_GAP        = 90                 // Frames between completed spawn formations.
.const ENEMY_EXIT_RIGHT_LO = $58            // 344 = $0158, just beyond the right edge.

.const WAVE_COUNT          = 0
.const WAVE_INTERVAL       = 1
.const WAVE_START_X        = 2
.const WAVE_START_Y        = 3
.const WAVE_ADD_X          = 4
.const WAVE_ADD_Y          = 5

// ============================================================================
// ENGINE SHAPE
// ============================================================================
//
// Logical objects live in OBJECT_* RAM and are never permanently tied to a
// VIC-II sprite. Active objects are collected and sorted by Y each frame.
//
// Two render plans are maintained:
//   LIVE_PLAN  - immutable plan currently being displayed by VIC-II/IRQ.
//   BUILD_PLAN - next frame's plan, built concurrently by the main loop.
//
// At each frame boundary BUILD_PLAN and LIVE_PLAN swap. renderSprites writes
// the first eight sorted objects to VIC sprites 0-7, then armFirstBatch starts
// the prepared raster schedule. multiplexIRQ recycles hardware sprite slots in
// one or more batches for objects beyond the first eight.
//
// Game state -> sorted object list -> BUILD_PLAN -> swap -> VIC-II renderer.
// ============================================================================

// --- Routine: init ----------------------------------------------------------
// Configure VIC-II, seed the object pool, and prepare the first render plan.
init:
    lda VIC_BANK                            // Load A from VIC_BANK.
    and #%11111100                          // AND A with #%11111100.
    ora #%00000011                          // OR A with #%00000011.
    sta VIC_BANK                            // VIC bank 0 ($0000-$3fff)

    lda VIC_MEMORY_SETUP                    // Load A from VIC_MEMORY_SETUP.
    and #%11110000                          // AND A with #%11110000.
    ora #%00000100                          // OR A with #%00000100.
    sta VIC_MEMORY_SETUP                    // Existing screen/character layout

    lda #147                                // Load A from #147.
    jsr $ffd2                               // Clear screen

    lda #0                                  // Load A from #0.
    sta BORDER_COLOUR                       // Debug border off

    jsr setupDebugDisplay                   // Draw the FREE-cycle display and initialise its rolling minimum.
    jsr setupSprites                        // Call setupSprites; return here when it executes RTS.
    jsr startRandomWave                      // Choose the first formation/pattern combination.

    //lda #1                                  // Load A from #1.
    //sta MOB_X_VEL                           // Enemy horizontal speed

    lda #1                                  // Load A from #1.
    sta OBJECT_ACTIVE                       // Object 0 = player
    lda #TYPE_PLAYER                        // Load A from #TYPE_PLAYER.
    sta OBJECT_TYPE                         // Store A in OBJECT_TYPE.
    lda #playerSprite / 64                  // Load A from #playerSprite / 64.
    sta OBJECT_SPRITE                       // Store A in OBJECT_SPRITE.
    lda #2                                  // Load A from #2.
    sta OBJECT_COLOUR                       // Store A in OBJECT_COLOUR.

    ldx #1                                  // Load X from #1.
//!enemyInit:
    //lda #1                                  // Load A from #1.
    //sta OBJECT_ACTIVE,x                     // Store A in OBJECT_ACTIVE,x.
    //lda #TYPE_ENEMY                         // Load A from #TYPE_ENEMY.
    //sta OBJECT_TYPE,x                       // Store A in OBJECT_TYPE,x.
    //lda spritePointers,x                    // Load A from spritePointers,x.
    //sta OBJECT_SPRITE,x                     // Store A in OBJECT_SPRITE,x.
    //lda #3                                  // Load A from #3.
    //sta OBJECT_COLOUR,x                     // Store A in OBJECT_COLOUR,x.
    //lda #0
    //sta OBJECT_PATTERN,x
    //sta OBJECT_PATH_STEP,x
    //sta OBJECT_PATH_TIMER,x
    //inx                                     // Increment X by one.
    //cpx #MAX_OBJECTS                        // Compare X with #MAX_OBJECTS; set flags, leaving X unchanged.
    ////cpx #02
    //bne !enemyInit-                         // Branch to !enemyInit- if the previous result was non-zero/not equal.

    jsr buildSortedObjectList               // Call buildSortedObjectList; return here when it executes RTS.
    jsr sortObjectsByY                      // Call sortObjectsByY; return here when it executes RTS.
    jsr buildInitialSpriteSnapshot          // Call buildInitialSpriteSnapshot; return here when it executes RTS.
    jsr buildBatchSpriteSchedule            // Call buildBatchSpriteSchedule; return here when it executes RTS.
    jsr swapRenderPlans                     // Call swapRenderPlans; return here when it executes RTS.
    jmp mainLoop                            // Jump unconditionally to mainLoop.

// --- Routine: mainLoop ------------------------------------------------------
// Display LIVE_PLAN while the CPU prepares BUILD_PLAN for the next frame.
mainLoop:
    jsr waitForFrameStart                   // Call waitForFrameStart; return here when it executes RTS.
    jsr renderSprites                       // Call renderSprites; return here when it executes RTS.
    jsr armFirstBatch                       // Call armFirstBatch; return here when it executes RTS.

!frameLoop:
    jsr updateObjects                       // Call updateObjects; return here when it executes RTS.
    jsr updateSpawner                       // Periodically create a new enemy.
    jsr buildSortedObjectList               // Call buildSortedObjectList; return here when it executes RTS.
    jsr sortObjectsByY                      // Call sortObjectsByY; return here when it executes RTS.
    jsr buildInitialSpriteSnapshot          // Call buildInitialSpriteSnapshot; return here when it executes RTS.
    jsr buildBatchSpriteSchedule            // Call buildBatchSpriteSchedule; return here when it executes RTS.
    jsr updateCycleDebug                    // Record remaining frame budget; refresh the display every 50 frames.

    jsr waitForFrameStart                   // Call waitForFrameStart; return here when it executes RTS.
    jsr swapRenderPlans                     // Call swapRenderPlans; return here when it executes RTS.
    jsr renderSprites                       // Call renderSprites; return here when it executes RTS.
    jsr armFirstBatch                       // Call armFirstBatch; return here when it executes RTS.
    jmp !frameLoop-                         // Jump unconditionally to !frameLoop-.

// --- Routine: setupSprites --------------------------------------------------
// Enable VIC sprites and seed logical object positions.
setupSprites:
    lda #$0                              // Load A from #$ff.
    sta SPRITE_ENABLE                       // Enable all 8 hardware sprites
    lda #%11111111
    sta SPRITE_MODE                         // $D01C: all hardware sprites use multicolour mode
    lda #$0b
    sta SPRITE_COLOUR_1
    lda #$0f
    sta SPRITE_COLOUR_2

    lda #146                                // Load A from #146.
    sta OBJECT_X                            // Player X
    lda #200                                // Load A from #200.
    sta OBJECT_Y                            // Player Y
    lda #0                                  // Load A from #0.
    sta OBJECT_X_MSB                        // Store A in OBJECT_X_MSB.

    lda #31                                 // Load A from #31.
    //lda #255
    ldx #1                                  // Load X from #1.
!xLoop:
    sta OBJECT_X,x                          // Store A in OBJECT_X,x.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc #28                                 // Add #28 to A, including carry.
    inx                                     // Increment X by one.
    cpx #MAX_OBJECTS                        // Compare X with #MAX_OBJECTS; set flags, leaving X unchanged.
    bne !xLoop-                             // Branch to !xLoop- if the previous result was non-zero/not equal.

    lda #40                                 // Load A from #40.
    ldx #1                                  // Load X from #1.
!yLoop:
    sta OBJECT_Y,x                          // Store A in OBJECT_Y,x.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc #12                                 // Add #12 to A, including carry.
    inx                                     // Increment X by one.
    cpx #MAX_OBJECTS                        // Compare X with #MAX_OBJECTS; set flags, leaving X unchanged.
    bne !yLoop-                             // Branch to !yLoop- if the previous result was non-zero/not equal.
    rts                                     // Return to the calling routine.

// --- Routine: updateObjects -------------------------------------------------
// Dispatch active logical objects to their type-specific update routine.
updateObjects:
    ldx #0                                  // Load X from #0.
!objectLoop:
    lda OBJECT_ACTIVE,x                     // Load A from OBJECT_ACTIVE,x.
    beq !next+                              // Branch to !next+ if the previous result was zero/equal.

    lda OBJECT_TYPE,x                       // Load A from OBJECT_TYPE,x.
    cmp #TYPE_PLAYER                        // Compare A with #TYPE_PLAYER; set flags, leaving A unchanged.
    bne !enemy+                             // Branch to !enemy+ if the previous result was non-zero/not equal.
    jsr updatePlayer                        // Call updatePlayer; return here when it executes RTS.
    jmp !next+                              // Jump unconditionally to !next+.

!enemy:
    cmp #TYPE_ENEMY                         // Compare A with #TYPE_ENEMY; set flags, leaving A unchanged.
    bne !next+                              // Branch to !next+ if the previous result was non-zero/not equal.
    //jsr moveEnemy                           // Call moveEnemy; return here when it executes RTS.
    jsr moveEnemyPath
!next:
    inx                                     // Increment X by one.
    cpx #MAX_OBJECTS                        // Compare X with #MAX_OBJECTS; set flags, leaving X unchanged.
    bne !objectLoop-                        // Branch to !objectLoop- if the previous result was non-zero/not equal.
    rts                                     // Return to the calling routine.

// --- Routine: updatePlayer --------------------------------------------------
// Read joystick port 2 once and move object X within the playfield bounds.
updatePlayer:
    lda STICK_2                             // Load A from STICK_2.
    sta JOY_STATE                           // Store A in JOY_STATE.

    lda JOY_STATE                           // Load A from JOY_STATE.
    and #%00000001                          // AND A with #%00000001.
    bne !down+                              // Branch to !down+ if the previous result was non-zero/not equal.
    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    cmp #49                                 // Compare A with #49; set flags, leaving A unchanged.
    beq !down+                              // Branch to !down+ if the previous result was zero/equal.
    dec OBJECT_Y,x                          // Up

!down:
    lda JOY_STATE                           // Load A from JOY_STATE.
    and #%00000010                          // AND A with #%00000010.
    bne !left+                              // Branch to !left+ if the previous result was non-zero/not equal.
    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    cmp #230                                // Compare A with #230; set flags, leaving A unchanged.
    beq !left+                              // Branch to !left+ if the previous result was zero/equal.
    inc OBJECT_Y,x                          // Down

!left:
    lda JOY_STATE                           // Load A from JOY_STATE.
    and #%00000100                          // AND A with #%00000100.
    bne !right+                             // Branch to !right+ if the previous result was non-zero/not equal.
    lda OBJECT_X_MSB,x                      // Load A from OBJECT_X_MSB,x.
    bne !moveLeft+                          // Branch to !moveLeft+ if the previous result was non-zero/not equal.
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    cmp #23                                 // Compare A with #23; set flags, leaving A unchanged.
    beq !right+                             // Branch to !right+ if the previous result was zero/equal.

!moveLeft:
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    bne !decLeft+                           // Branch to !decLeft+ if the previous result was non-zero/not equal.
    lda #0                                  // Load A from #0.
    sta OBJECT_X_MSB,x                      // 256 -> 255
!decLeft:
    dec OBJECT_X,x                          // Decrement OBJECT_X,x by one.

!right:
    lda JOY_STATE                           // Load A from JOY_STATE.
    and #%00001000                          // AND A with #%00001000.
    bne !done+                              // Branch to !done+ if the previous result was non-zero/not equal.
    lda OBJECT_X_MSB,x                      // Load A from OBJECT_X_MSB,x.
    beq !moveRight+                         // Branch to !moveRight+ if the previous result was zero/equal.
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    cmp #65                                 // Compare A with #65; set flags, leaving A unchanged.
    beq !done+                              // Branch to !done+ if the previous result was zero/equal.

!moveRight:
    inc OBJECT_X,x                          // Increment OBJECT_X,x by one.
    bne !done+                              // Branch to !done+ if the previous result was non-zero/not equal.
    lda #1                                  // Load A from #1.
    sta OBJECT_X_MSB,x                      // 255 -> 256

!done:
    rts                                     // Return to the calling routine.

// --- Routine: moveEnemyPath -------------------------------------------------
// Advance one enemy through its table-driven movement pattern.
// Entry: X = logical object index.
moveEnemyPath:
    lda OBJECT_PATH_TIMER,x                 // Load frames remaining in the current path segment.
    bne !move+                              // If non-zero, continue the current segment.

    ldy OBJECT_PATH_STEP,x                  // Y = byte offset of the current path segment.
    lda enemyPatterns,y                     // Read this segment's duration from the selected pattern.
    bne !loadSegment+                       // Non-zero means this is a valid movement segment.
    jmp !finished+                          // Duration zero explicitly ends and deactivates this object.
!loadSegment:
    sta OBJECT_PATH_TIMER,x                 // $ff means this segment continues indefinitely.

!move:
    ldy OBJECT_PATH_STEP,x                  // Y = byte offset of the current path segment.

    lda enemyPatterns+1,y                   // Read signed horizontal delta for this frame.
    beq !moveY+                             // Zero means no horizontal movement.
    bmi !moveXLeft+                         // Bit 7 set means a negative horizontal delta.

!moveXRight:
    clc                                     // Clear carry before adding the positive X delta.
    adc OBJECT_X,x                          // Add delta to the low byte of the 9-bit X coordinate.
    sta OBJECT_X,x                          // Store the new low byte.
    bcc !checkRightEdge+                    // No carry means the ninth X bit is unchanged.
    inc OBJECT_X_MSB,x                      // Carry means low byte crossed $ff -> $00.

!checkRightEdge:
    lda OBJECT_X_MSB,x                      // Inspect the ninth X-coordinate bit/state.
    cmp #2                                  // Values 2+ are beyond the valid 9-bit display region.
    bcc !rightHighValid+                    // Values below two can still represent a visible X position.
    jmp !finished+                          // Deactivate rather than allowing X to wrap around.
!rightHighValid:
    cmp #1                                  // High byte zero means the object is still left of X=256.
    bne !moveY+                             // Only high byte one can have crossed the right exit point.
    lda OBJECT_X,x                          // Read low byte of the 9-bit X position.
    cmp #ENEMY_EXIT_RIGHT_LO                // X >= $0158 (344) is beyond the right-hand edge.
    bcc !moveY+                             // Values below the exit point are still on-screen.
    jmp !finished+                          // Return the object slot once it has naturally exited.

!moveXLeft:
    clc                                     // Clear carry before adding the two's-complement delta.
    adc OBJECT_X,x                          // Add negative delta to the low byte.
    sta OBJECT_X,x                          // Store the new low byte.
    bcs !moveY+                             // Carry set means no borrow across the 256-pixel boundary.
    lda OBJECT_X_MSB,x                      // A borrow while high byte zero means we crossed left of X=0.
    bne !leftHighValid+                     // High byte one can legitimately borrow back into the lower half.
    jmp !finished+                          // Deactivate instead of wrapping from X=0 to X=511.
!leftHighValid:
    dec OBJECT_X_MSB,x                     // Move normally from the upper X half into the lower half.

!moveY:
    lda enemyPatterns+2,y                   // Read signed vertical delta for this frame.
    beq !tick+                              // Zero means no vertical movement.
    bmi !moveYUp+                           // Negative delta means movement towards the top.

!moveYDown:
    clc                                     // Clear carry before adding the positive Y delta.
    adc OBJECT_Y,x                          // Add the downward movement to the current Y position.
    bcs !finished+                          // Carry means Y crossed $ff; deactivate instead of wrapping to $00.
    sta OBJECT_Y,x                          // Store the valid new Y position.
    jmp !tick+                              // Continue the path timer update.

!moveYUp:
    clc                                     // Clear carry before adding the negative two's-complement delta.
    adc OBJECT_Y,x                          // Add the upward movement to the current Y position.
    bcc !finished+                          // No carry means Y crossed below $00; deactivate instead of wrapping to $ff.
    sta OBJECT_Y,x                          // Store the valid new Y position.

!tick:
    lda OBJECT_PATH_TIMER,x                 // Read the active segment duration marker.
    cmp #$ff                                // $ff means retain this final vector indefinitely.
    beq !done+                              // Lifecycle bounds, not path duration, will remove the enemy.

    dec OBJECT_PATH_TIMER,x                 // Consume one frame from a finite path segment.
    bne !done+                              // If frames remain, stay on this segment.

    lda OBJECT_PATH_STEP,x                  // Load current byte offset in the path table.
    clc                                     // Clear carry before adding the segment size.
    adc #3                                  // Advance past duration, dx and dy.
    sta OBJECT_PATH_STEP,x                  // Save offset of the next segment.

!done:
    rts                                     // Current enemy update is complete.

!finished:
    lda #0                                  // Zero represents inactive.
    sta OBJECT_ACTIVE,x                     // Return this logical object to the free pool.
    rts

// --- Routine: buildSortedObjectList ----------------------------------------
// Collect active logical object numbers into SORTED_OBJECTS.
buildSortedObjectList:
    lda #0                                  // Load A from #0.
    sta SORTED_COUNT                        // Store A in SORTED_COUNT.
    ldx #0                                  // Load X from #0.
!collect:
    lda OBJECT_ACTIVE,x                     // Load A from OBJECT_ACTIVE,x.
    beq !next+                              // Branch to !next+ if the previous result was zero/equal.
    ldy SORTED_COUNT                        // Load Y from SORTED_COUNT.
    txa                                     // Copy X into A.
    sta SORTED_OBJECTS,y                    // Store A in SORTED_OBJECTS,y.
    inc SORTED_COUNT                        // Increment SORTED_COUNT by one.
!next:
    inx                                     // Increment X by one.
    cpx #MAX_OBJECTS                        // Compare X with #MAX_OBJECTS; set flags, leaving X unchanged.
    bne !collect-                           // Branch to !collect- if the previous result was non-zero/not equal.
    rts                                     // Return to the calling routine.

// --- Routine: sortObjectsByY ------------------------------------------------
// Insertion-sort SORTED_OBJECTS by each object's Y coordinate.
sortObjectsByY:
    lda SORTED_COUNT                        // Load A from SORTED_COUNT.
    cmp #2                                  // Compare A with #2; set flags, leaving A unchanged.
    bcc !done+                              // Branch to !done+ if carry is clear.
    ldy #1                                  // Load Y from #1.

!outer:
    lda SORTED_OBJECTS,y                    // Load A from SORTED_OBJECTS,y.
    sta TEMP_OBJECT                         // Store A in TEMP_OBJECT.
    tax                                     // Copy A into X.
    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    sta TEMP_SORT_Y                         // Store A in TEMP_SORT_Y.
    dey                                     // Decrement Y by one.

!inner:
    lda SORTED_OBJECTS,y                    // Load A from SORTED_OBJECTS,y.
    tax                                     // Copy A into X.
    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    cmp TEMP_SORT_Y                         // Compare A with TEMP_SORT_Y; set flags, leaving A unchanged.
    bcc !insert+                            // Branch to !insert+ if carry is clear.
    beq !insert+                            // Branch to !insert+ if the previous result was zero/equal.
    lda SORTED_OBJECTS,y                    // Load A from SORTED_OBJECTS,y.
    sta SORTED_OBJECTS + 1,y                // Store A in SORTED_OBJECTS + 1,y.
    dey                                     // Decrement Y by one.
    bpl !inner-                             // Branch to !inner- if the negative flag is clear.

    lda TEMP_OBJECT                         // Load A from TEMP_OBJECT.
    sta SORTED_OBJECTS                      // Store A in SORTED_OBJECTS.
    jmp !next+                              // Jump unconditionally to !next+.

!insert:
    lda TEMP_OBJECT                         // Load A from TEMP_OBJECT.
    sta SORTED_OBJECTS + 1,y                // Store A in SORTED_OBJECTS + 1,y.

!next:
    iny                                     // Increment Y by one.
    iny                                     // Increment Y by one.
    cpy SORTED_COUNT                        // Compare Y with SORTED_COUNT; set flags, leaving Y unchanged.
    bcc !outer-                             // Branch to !outer- if carry is clear.
!done:
    rts                                     // Return to the calling routine.

// --- Routine: buildInitialSpriteSnapshot -----------------------------------
// Snapshot the first eight sorted objects into BUILD_PLAN.
buildInitialSpriteSnapshot:
    lda SORTED_COUNT                        // Load A from SORTED_COUNT.
    cmp #8                                  // Compare A with #8; set flags, leaving A unchanged.
    bcc !countReady+                        // Branch to !countReady+ if carry is clear.
    lda #8                                  // Load A from #8.
!countReady:
    sta SCHED_RENDER_COUNT                  // Store A in SCHED_RENDER_COUNT.
    ldy BUILD_PLAN                          // Load Y from BUILD_PLAN.
    sta RENDER_COUNT,y                      // Store A in RENDER_COUNT,y.
    lda SCHED_RENDER_COUNT                  // Load A from SCHED_RENDER_COUNT.
    beq !done+                              // Branch to !done+ if the previous result was zero/equal.

    ldx #0                                  // Load X from #0.
!snapshotLoop:
    ldy SORTED_OBJECTS,x                    // Load Y from SORTED_OBJECTS,x.
    sty TEMP_OBJECT                         // Store Y in TEMP_OBJECT.

    txa                                     // Copy X into A.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc BUILD_PLAN                          // Add BUILD_PLAN to A, including carry.
    sta SNAPSHOT_INDEX                      // Store A in SNAPSHOT_INDEX.
    tay                                     // Copy A into Y.

    ldx TEMP_OBJECT                         // Load X from TEMP_OBJECT.
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    sta INITIAL_X,y                         // Store A in INITIAL_X,y.
    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    sta INITIAL_Y,y                         // Store A in INITIAL_Y,y.
    lda OBJECT_X_MSB,x                      // Load A from OBJECT_X_MSB,x.
    sta INITIAL_X_MSB,y                     // Store A in INITIAL_X_MSB,y.
    lda OBJECT_SPRITE,x                     // Load A from OBJECT_SPRITE,x.
    sta INITIAL_SPRITE,y                    // Store A in INITIAL_SPRITE,y.
    lda OBJECT_COLOUR,x                     // Load A from OBJECT_COLOUR,x.
    sta INITIAL_COLOUR,y                    // Store A in INITIAL_COLOUR,y.

    lda SNAPSHOT_INDEX                      // Load A from SNAPSHOT_INDEX.
    sec                                     // Set carry before subtraction or a carry-dependent operation.
    sbc BUILD_PLAN                          // Subtract BUILD_PLAN from A using carry as the inverted borrow.
    tax                                     // Copy A into X.
    inx                                     // Increment X by one.
    cpx SCHED_RENDER_COUNT                  // Compare X with SCHED_RENDER_COUNT; set flags, leaving X unchanged.
    bne !snapshotLoop-                      // Branch to !snapshotLoop- if the previous result was non-zero/not equal.
!done:
    rts                                     // Return to the calling routine.

// --- Routine: buildBatchSpriteSchedule -------------------------------------
// Build BUILD_PLAN's raster batches for sorted objects beyond the first eight.
buildBatchSpriteSchedule:
    lda #0                                  // Load A from #0.
    ldy BUILD_PLAN                          // Load Y from BUILD_PLAN.
    sta BATCH_COUNT,y                       // Store A in BATCH_COUNT,y.
    sta SCHED_ASSIGN_INDEX                  // Store A in SCHED_ASSIGN_INDEX.
    lda RENDER_COUNT,y                      // Load A from RENDER_COUNT,y.
    sta SCHED_RENDER_COUNT                  // Store A in SCHED_RENDER_COUNT.

    ldy #0                                  // Load Y from #0.
!initSlots:
    cpy SCHED_RENDER_COUNT                  // Compare Y with SCHED_RENDER_COUNT; set flags, leaving Y unchanged.
    bcs !unusedSlot+                        // Branch to !unusedSlot+ if carry is set.

    lda SORTED_OBJECTS,y                    // Load A from SORTED_OBJECTS,y.
    tax                                     // Copy A into X.
    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc #24                                 // Conservative slot reuse distance
    bcs !unavailableSlot+                   // Branch to !unavailableSlot+ if carry is set.
    sta SLOT_FREE_RASTER,y                  // Store A in SLOT_FREE_RASTER,y.
    jmp !nextInit+                          // Jump unconditionally to !nextInit+.

!unusedSlot:
    lda #0                                  // Load A from #0.
    sta SLOT_FREE_RASTER,y                  // Store A in SLOT_FREE_RASTER,y.
    jmp !nextInit+                          // Jump unconditionally to !nextInit+.

!unavailableSlot:
    lda #$ff                                // Load A from #$ff.
    sta SLOT_FREE_RASTER,y                  // Store A in SLOT_FREE_RASTER,y.

!nextInit:
    iny                                     // Increment Y by one.
    cpy #8                                  // Compare Y with #8; set flags, leaving Y unchanged.
    bne !initSlots-                         // Branch to !initSlots- if the previous result was non-zero/not equal.

    lda SORTED_COUNT                        // Load A from SORTED_COUNT.
    cmp #9                                  // Compare A with #9; set flags, leaving A unchanged.
    bcs !needsSchedule+                     // Branch to !needsSchedule+ if carry is set.
    rts                                     // Return to the calling routine.

!needsSchedule:
    lda #8                                  // Load A from #8.
    sta SCHED_OBJECT_INDEX                  // Store A in SCHED_OBJECT_INDEX.

!startBatch:
    lda SCHED_OBJECT_INDEX                  // Load A from SCHED_OBJECT_INDEX.
    cmp SORTED_COUNT                        // Compare A with SORTED_COUNT; set flags, leaving A unchanged.
    bcc !objectsRemain+                     // Branch to !objectsRemain+ if carry is clear.
    rts                                     // Return to the calling routine.

!objectsRemain:
    lda #0                                  // Load A from #0.
    sta SCHED_BATCH_SIZE                    // Store A in SCHED_BATCH_SIZE.
    lda #$ff                                // Load A from #$ff.
    sta SCHED_BATCH_LATEST                  // Store A in SCHED_BATCH_LATEST.

!tryObject:
    ldy SCHED_OBJECT_INDEX                  // Load Y from SCHED_OBJECT_INDEX.
    lda SORTED_OBJECTS,y                    // Load A from SORTED_OBJECTS,y.
    sta TEMP_OBJECT                         // Store A in TEMP_OBJECT.
    tax                                     // Copy A into X.

    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    cmp #12                                 // Compare A with #12; set flags, leaving A unchanged.
    bcs !deadlineOk+                        // Branch to !deadlineOk+ if carry is set.
    inc SCHED_OBJECT_INDEX                  // Too high to schedule safely
    jmp !startBatch-                        // Jump unconditionally to !startBatch-.

!deadlineOk:
    sec                                     // Set carry before subtraction or a carry-dependent operation.
    sbc #12                                 // Subtract #12 from A using carry as the inverted borrow.
    sta TEMP_OBJECT_Y                       // Latest legal IRQ raster

    lda #$ff                                // Load A from #$ff.
    sta SCHED_SELECTED_SLOT                 // Store A in SCHED_SELECTED_SLOT.
    lda #0                                  // Load A from #0.
    sta SCHED_SELECTED_FREE                 // Store A in SCHED_SELECTED_FREE.
    ldy #0                                  // Load Y from #0.

!findSlot:
    lda SLOT_FREE_RASTER,y                  // Load A from SLOT_FREE_RASTER,y.
    cmp #$ff                                // Compare A with #$ff; set flags, leaving A unchanged.
    beq !nextSlot+                          // Branch to !nextSlot+ if the previous result was zero/equal.
    cmp TEMP_OBJECT_Y                       // Compare A with TEMP_OBJECT_Y; set flags, leaving A unchanged.
    bcc !checkBatch+                        // Branch to !checkBatch+ if carry is clear.
    beq !checkBatch+                        // Branch to !checkBatch+ if the previous result was zero/equal.
    bne !nextSlot+                          // A > deadline

!checkBatch:
    ldx SCHED_BATCH_SIZE                    // Load X from SCHED_BATCH_SIZE.
    beq !candidate+                         // Branch to !candidate+ if the previous result was zero/equal.
    cmp SCHED_BATCH_LATEST                  // Compare A with SCHED_BATCH_LATEST; set flags, leaving A unchanged.
    bcc !candidate+                         // Branch to !candidate+ if carry is clear.
    beq !candidate+                         // Branch to !candidate+ if the previous result was zero/equal.
    bne !nextSlot+                          // Outside batch window

!candidate:
    cmp SCHED_SELECTED_FREE                 // Compare A with SCHED_SELECTED_FREE; set flags, leaving A unchanged.
    bcc !nextSlot+                          // Branch to !nextSlot+ if carry is clear.
    sta SCHED_SELECTED_FREE                 // Prefer latest reusable slot
    sty SCHED_SELECTED_SLOT                 // Store Y in SCHED_SELECTED_SLOT.

!nextSlot:
    iny                                     // Increment Y by one.
    cpy #8                                  // Compare Y with #8; set flags, leaving Y unchanged.
    bne !findSlot-                          // Branch to !findSlot- if the previous result was non-zero/not equal.

    lda SCHED_SELECTED_SLOT                 // Load A from SCHED_SELECTED_SLOT.
    cmp #$ff                                // Compare A with #$ff; set flags, leaving A unchanged.
    bne !slotFound+                         // Branch to !slotFound+ if the previous result was non-zero/not equal.

    lda SCHED_BATCH_SIZE                    // Load A from SCHED_BATCH_SIZE.
    bne !finishBatch+                       // Branch to !finishBatch+ if the previous result was non-zero/not equal.

!cannotSchedule:
    inc SCHED_OBJECT_INDEX                  // Increment SCHED_OBJECT_INDEX by one.
    jmp !startBatch-                        // Jump unconditionally to !startBatch-.

!slotFound:
    lda TEMP_OBJECT_Y                       // Load A from TEMP_OBJECT_Y.
    cmp SCHED_BATCH_LATEST                  // Compare A with SCHED_BATCH_LATEST; set flags, leaving A unchanged.
    bcs !latestReady+                       // Branch to !latestReady+ if carry is set.
    sta SCHED_BATCH_LATEST                  // Store A in SCHED_BATCH_LATEST.
!latestReady:

    lda SCHED_ASSIGN_INDEX                  // Load A from SCHED_ASSIGN_INDEX.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc BUILD_PLAN                          // Add BUILD_PLAN to A, including carry.
    tax                                     // Buffered assignment index

    lda SCHED_SELECTED_SLOT                 // Load A from SCHED_SELECTED_SLOT.
    sta ASSIGN_SLOT,x                       // Store A in ASSIGN_SLOT,x.

    ldy TEMP_OBJECT                         // Load Y from TEMP_OBJECT.
    lda OBJECT_X,y                          // Load A from OBJECT_X,y.
    sta ASSIGN_X,x                          // Store A in ASSIGN_X,x.
    lda OBJECT_Y,y                          // Load A from OBJECT_Y,y.
    sta ASSIGN_Y,x                          // Store A in ASSIGN_Y,x.
    lda OBJECT_X_MSB,y                      // Load A from OBJECT_X_MSB,y.
    sta ASSIGN_X_MSB,x                      // Store A in ASSIGN_X_MSB,x.
    lda OBJECT_SPRITE,y                     // Load A from OBJECT_SPRITE,y.
    sta ASSIGN_SPRITE,x                     // Store A in ASSIGN_SPRITE,x.
    lda OBJECT_COLOUR,y                     // Load A from OBJECT_COLOUR,y.
    sta ASSIGN_COLOUR,x                     // Store A in ASSIGN_COLOUR,x.

    inc SCHED_ASSIGN_INDEX                  // Increment SCHED_ASSIGN_INDEX by one.
    inc SCHED_BATCH_SIZE                    // Increment SCHED_BATCH_SIZE by one.

    ldx TEMP_OBJECT                         // Load X from TEMP_OBJECT.
    lda OBJECT_Y,x                          // Load A from OBJECT_Y,x.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc #24                                 // Add #24 to A, including carry.
    ldy SCHED_SELECTED_SLOT                 // Load Y from SCHED_SELECTED_SLOT.
    bcc !storeFree+                         // Branch to !storeFree+ if carry is clear.
    lda #$ff                                // Load A from #$ff.
!storeFree:
    sta SLOT_FREE_RASTER,y                  // Store A in SLOT_FREE_RASTER,y.

    inc SCHED_OBJECT_INDEX                  // Increment SCHED_OBJECT_INDEX by one.
    lda SCHED_OBJECT_INDEX                  // Load A from SCHED_OBJECT_INDEX.
    cmp SORTED_COUNT                        // Compare A with SORTED_COUNT; set flags, leaving A unchanged.
    bcs !finishBatch+                       // Branch to !finishBatch+ if carry is set.
    jmp !tryObject-                         // Long loop transfer

!finishBatch:
    ldy BUILD_PLAN                          // Load Y from BUILD_PLAN.
    lda BATCH_COUNT,y                       // Load A from BATCH_COUNT,y.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc BUILD_PLAN                          // Add BUILD_PLAN to A, including carry.
    tax                                     // Buffered batch index

    lda SCHED_BATCH_LATEST                  // Load A from SCHED_BATCH_LATEST.
    sta BATCH_RASTER,x                      // Store A in BATCH_RASTER,x.
    lda SCHED_ASSIGN_INDEX                  // Load A from SCHED_ASSIGN_INDEX.
    sec                                     // Set carry before subtraction or a carry-dependent operation.
    sbc SCHED_BATCH_SIZE                    // Subtract SCHED_BATCH_SIZE from A using carry as the inverted borrow.
    sta BATCH_FIRST_ASSIGN,x                // Store A in BATCH_FIRST_ASSIGN,x.
    lda SCHED_BATCH_SIZE                    // Load A from SCHED_BATCH_SIZE.
    sta BATCH_ASSIGN_COUNT,x                // Store A in BATCH_ASSIGN_COUNT,x.

    ldy BUILD_PLAN                          // Load Y from BUILD_PLAN.
    lda BATCH_COUNT,y                       // Load A from BATCH_COUNT,y.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc #1                                  // Add #1 to A, including carry.
    sta BATCH_COUNT,y                       // Store A in BATCH_COUNT,y.

    lda SCHED_OBJECT_INDEX                  // Load A from SCHED_OBJECT_INDEX.
    cmp SORTED_COUNT                        // Compare A with SORTED_COUNT; set flags, leaving A unchanged.
    bcs !done+                              // Branch to !done+ if carry is set.
    jmp !startBatch-                        // Long loop transfer
!done:
    rts                                     // Return to the calling routine.

// --- Routine: setupDebugDisplay --------------------------------------------
// Draw "FREE 00000", colour it white, and initialise the rolling cycle minimum.
setupDebugDisplay:
    ldx #0                                  // Start at the first character in the debug label.
!labelLoop:
    lda debugLabel,x                        // Load the next prebuilt screen code.
    sta DEBUG_SCREEN,x                      // Write it into the top-left of screen RAM.
    lda #1                                  // Use C64 colour 1: white.
    sta DEBUG_COLOUR,x                      // Set this character's colour RAM entry.
    inx                                     // Advance to the next debug character.
    cpx #10                                 // Label plus five digits occupies ten characters.
    bne !labelLoop-                         // Keep copying until all ten characters are written.

    lda #0                                  // Start the one-second frame counter at zero.
    sta DEBUG_FRAME_COUNT                   // Store the current debug frame count.
    lda #$ff                                // $ffff is higher than any possible PAL-frame free-cycle value.
    sta DEBUG_MIN_LO                        // Initialise low byte of the rolling minimum.
    sta DEBUG_MIN_HI                        // Initialise high byte of the rolling minimum.
    rts                                     // Return to init.

// --- Routine: updateCycleDebug ---------------------------------------------
// Track the lowest approximate free-cycle count and display it every 50 frames.
updateCycleDebug:
    inc DEBUG_FRAME_COUNT                   // Count one completed BUILD_PLAN preparation.
    lda DEBUG_FRAME_COUNT                   // Load the updated frame count.
    cmp #DEBUG_FRAMES                       // Has roughly one PAL second elapsed?
    bne !sample+                            // If not, skip the relatively expensive decimal display update.

    jsr displayCycleMinimum                 // Display the worst free-cycle figure from the previous interval.
    lda #0                                  // Begin a fresh 50-frame interval.
    sta DEBUG_FRAME_COUNT                   // Reset the frame counter.
    lda #$ff                                // Reset the rolling minimum to the largest possible 16-bit value.
    sta DEBUG_MIN_LO                        // Reset minimum low byte.
    sta DEBUG_MIN_HI                        // Reset minimum high byte.

!sample:
!stableRaster:
    lda VIC_CONTROL_1                       // Read raster bit 8 from $d011.
    and #%10000000                          // Keep only raster bit 8.
    sta DEBUG_RASTER_HI                     // Remember the first high-bit reading.
    lda RASTER                              // Read raster bits 0-7 from $d012.
    sta DEBUG_RASTER_LO                     // Save the raster low byte.
    lda VIC_CONTROL_1                       // Read raster bit 8 again in case line 255/256 was crossed.
    and #%10000000                          // Keep only raster bit 8.
    cmp DEBUG_RASTER_HI                     // Did the high bit change between the two reads?
    bne !stableRaster-                      // Retry if the sample straddled the 255/256 boundary.

    lda #$38                                // 312 PAL lines = $0138; start with its low byte.
    sec                                     // Set carry so SBC performs an ordinary subtraction.
    sbc DEBUG_RASTER_LO                     // Low byte of free lines = $38 - raster low byte.
    sta DEBUG_FREE_LO                       // Temporarily store free raster lines, low byte.
    lda #$01                                // Load high byte of PAL's 312-line total.
    sbc #0                                  // Apply any borrow from the low-byte subtraction.
    ldx DEBUG_RASTER_HI                     // Load sampled raster bit 8.
    beq !haveFreeLines+                     // If clear, the sampled raster was below line 256.
    sec                                     // No borrow is wanted for this explicit high-raster subtraction.
    sbc #1                                  // Subtract the raster's 256-line high component.
!haveFreeLines:
    sta DEBUG_FREE_HI                       // Store free raster lines, high byte.

    lda DEBUG_FREE_LO                       // Preserve the line count before multiplying it.
    sta DEBUG_LINES_LO                      // Save original free-line low byte.
    lda DEBUG_FREE_HI                       // Load original free-line high byte.
    sta DEBUG_LINES_HI                      // Save original free-line high byte.

    ldx #6                                  // Multiplying by 64 is six 16-bit left shifts.
!times64:
    asl DEBUG_FREE_LO                       // Shift low byte left; outgoing bit 7 enters carry.
    rol DEBUG_FREE_HI                       // Shift high byte left and rotate the carry into bit 0.
    dex                                     // One of the six shifts is complete.
    bne !times64-                           // Repeat until free lines have been multiplied by 64.

    lda DEBUG_FREE_LO                       // Convert x64 to x63 by subtracting the original line count.
    sec                                     // Set carry for an ordinary 16-bit subtraction.
    sbc DEBUG_LINES_LO                      // Subtract original low byte.
    sta DEBUG_FREE_LO                       // Store approximate free cycles, low byte.
    lda DEBUG_FREE_HI                       // Load multiplied high byte.
    sbc DEBUG_LINES_HI                      // Subtract original high byte plus any borrow.
    sta DEBUG_FREE_HI                       // Store approximate free cycles, high byte.

    lda DEBUG_FREE_HI                       // Compare new free-cycle high byte with the rolling minimum.
    cmp DEBUG_MIN_HI                        // Set flags from FREE_HI - MIN_HI.
    bcc !newMinimum+                        // A smaller high byte is definitely a new minimum.
    bne !done+                              // A larger high byte cannot be a new minimum.
    lda DEBUG_FREE_LO                       // High bytes match, so compare low bytes.
    cmp DEBUG_MIN_LO                        // Set flags from FREE_LO - MIN_LO.
    bcs !done+                              // Equal or larger means the existing minimum is still lower.

!newMinimum:
    lda DEBUG_FREE_LO                       // Load the new minimum low byte.
    sta DEBUG_MIN_LO                        // Store it as the rolling worst-case free budget.
    lda DEBUG_FREE_HI                       // Load the new minimum high byte.
    sta DEBUG_MIN_HI                        // Store it as the rolling worst-case free budget.

!done:
    rts                                     // Return to the main loop.

// --- Routine: displayCycleMinimum ------------------------------------------
// Convert the 16-bit rolling minimum to five decimal digits at DEBUG_SCREEN+5.
displayCycleMinimum:
    lda DEBUG_MIN_LO                        // Copy the rolling minimum so conversion can destructively subtract.
    sta DEBUG_VALUE_LO                      // Working decimal value, low byte.
    lda DEBUG_MIN_HI                        // Copy minimum high byte.
    sta DEBUG_VALUE_HI                      // Working decimal value, high byte.

    ldx #0                                  // Begin with the 10000s decimal place.
!digitLoop:
    ldy #0                                  // Y counts how many times this decimal divisor fits.
!subtractLoop:
    lda DEBUG_VALUE_HI                      // Compare the remaining value's high byte first.
    cmp debugDivisorHi,x                    // Compare against this decimal divisor's high byte.
    bcc !emitDigit+                         // Smaller high byte means the divisor no longer fits.
    bne !subtract+                          // Larger high byte means the divisor definitely fits.
    lda DEBUG_VALUE_LO                      // High bytes match, so compare the low bytes.
    cmp debugDivisorLo,x                    // Compare remaining low byte with divisor low byte.
    bcc !emitDigit+                         // Stop when the remaining value is smaller than the divisor.

!subtract:
    lda DEBUG_VALUE_LO                      // Load current working value low byte.
    sec                                     // Set carry for an ordinary 16-bit subtraction.
    sbc debugDivisorLo,x                    // Subtract divisor low byte.
    sta DEBUG_VALUE_LO                      // Store the reduced working low byte.
    lda DEBUG_VALUE_HI                      // Load current working value high byte.
    sbc debugDivisorHi,x                    // Subtract divisor high byte plus any borrow.
    sta DEBUG_VALUE_HI                      // Store the reduced working high byte.
    iny                                     // One more divisor fitted into this decimal digit.
    bne !subtractLoop-                      // Continue until the remaining value is below the divisor.

!emitDigit:
    tya                                     // Copy the decimal digit count into A.
    clc                                     // Clear carry before converting the digit to a screen code.
    adc #48                                 // Screen codes 48-57 display digits 0-9.
    sta DEBUG_SCREEN + 5,x                  // Write this digit after the "FREE " label.
    inx                                     // Advance to the next decimal place.
    cpx #5                                  // Five digits cover every possible PAL-frame cycle count.
    bne !digitLoop-                         // Convert the remaining decimal places.
    rts                                     // Return to updateCycleDebug.

debugLabel:
    .byte 6,18,5,5,32,48,48,48,48,48       // Screen codes for "FREE 00000".

debugDivisorLo:
    .byte $10,$e8,$64,$0a,$01              // Low bytes: 10000, 1000, 100, 10, 1.

debugDivisorHi:
    .byte $27,$03,$00,$00,$00              // High bytes: 10000, 1000, 100, 10, 1.

// --- Routine: swapRenderPlans ----------------------------------------------
// Exchange BUILD_PLAN and LIVE_PLAN at the frame boundary.
swapRenderPlans:
    lda LIVE_PLAN                           // Load A from LIVE_PLAN.
    pha                                     // Push A onto the CPU stack.
    lda BUILD_PLAN                          // Load A from BUILD_PLAN.
    sta LIVE_PLAN                           // Store A in LIVE_PLAN.
    pla                                     // Pull the top stack byte into A.
    sta BUILD_PLAN                          // Store A in BUILD_PLAN.
    rts                                     // Return to the calling routine.

// --- Routine: waitForFrameStart --------------------------------------------
// Wait for the next PAL frame boundary, returning shortly after raster 0.
waitForFrameStart:
!waitHigh:
    lda VIC_CONTROL_1                       // Read current raster high bit from $D011.
    bpl !waitHigh-                          // Wait until raster reaches 256-311.

!waitLow:
    lda VIC_CONTROL_1                       // Read current raster high bit again.
    bmi !waitLow-                           // Wait until raster wraps from 311 back to 0-255.
    rts                                     // New frame has begun; return shortly after raster 0.

// --- Routine: renderSprites -------------------------------------------------
// Write LIVE_PLAN's initial hardware-sprite snapshot to VIC-II.
renderSprites:
    lda #0                                  // Load A from #0.
    sta TEMP_MSB                            // Store A in TEMP_MSB.

    ldy LIVE_PLAN                           // Load Y from LIVE_PLAN.
    lda RENDER_COUNT,y                      // Load the number of initial hardware sprites used by LIVE_PLAN.
    tax                                     // Copy the count into X for the enable-mask lookup.
    lda SPRITE_ENABLE_MASK,x                // Load a mask with the first X hardware sprite bits set.
    sta SPRITE_ENABLE                       // Disable any stale hardware sprites left from the previous frame.
    txa                                     // Restore the live sprite count to A.
    beq !none+                              // If zero sprites are live, there is nothing else to render.
    sta TEMP_OBJECT                         // Cache the live sprite count for the render loop.

    ldx #0                                  // Start rendering into hardware sprite slot 0.
!renderLoop:
    txa                                     // Copy X into A.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc LIVE_PLAN                           // Add LIVE_PLAN to A, including carry.
    tay                                     // Copy A into Y.
    sty TEMP_SORT_Y                         // Keep buffered snapshot index

    lda INITIAL_SPRITE,y                    // Load A from INITIAL_SPRITE,y.
    sta HW_SPRITE_POINTER,x                 // Store A in HW_SPRITE_POINTER,x.
    lda INITIAL_COLOUR,y                    // Load A from INITIAL_COLOUR,y.
    sta HW_SPRITE_COLOUR,x                  // Store A in HW_SPRITE_COLOUR,x.

    lda INITIAL_X,y                         // Load A from INITIAL_X,y.
    sta TEMP_OBJECT_Y                       // Store A in TEMP_OBJECT_Y.
    lda INITIAL_Y,y                         // Load A from INITIAL_Y,y.
    sta TEMP_Y_REG                          // Store A in TEMP_Y_REG.
    ldy HW_SPRITE_OFFSET,x                  // Load Y from HW_SPRITE_OFFSET,x.
    lda TEMP_OBJECT_Y                       // Load A from TEMP_OBJECT_Y.
    sta SPR_X,y                             // Store A in SPR_X,y.
    lda TEMP_Y_REG                          // Load A from TEMP_Y_REG.
    sta SPR_Y,y                             // Store A in SPR_Y,y.

    ldy TEMP_SORT_Y                         // Load Y from TEMP_SORT_Y.
    lda INITIAL_X_MSB,y                     // Load A from INITIAL_X_MSB,y.
    beq !noMsb+                             // Branch to !noMsb+ if the previous result was zero/equal.
    lda TEMP_MSB                            // Load A from TEMP_MSB.
    ora HW_BIT_MASK,x                       // OR A with HW_BIT_MASK,x.
    sta TEMP_MSB                            // Store A in TEMP_MSB.
!noMsb:
    inx                                     // Increment X by one.
    cpx TEMP_OBJECT                         // Compare X with TEMP_OBJECT; set flags, leaving X unchanged.
    bne !renderLoop-                        // Branch to !renderLoop- if the previous result was non-zero/not equal.

    lda TEMP_MSB                            // Load A from TEMP_MSB.
    sta SPRITE_OVERFLOW_REGISTER            // Store A in SPRITE_OVERFLOW_REGISTER.
    rts                                     // Return to the calling routine.

!none:
    sta SPRITE_OVERFLOW_REGISTER            // A is already zero
    rts                                     // Return to the calling routine.

// --- Routine: armFirstBatch -------------------------------------------------
// Install/arm LIVE_PLAN's first raster batch, if one exists.
armFirstBatch:
    sei                                     // Block maskable IRQs while critical state is changed.
    lda IRQ_ENABLE                          // Load A from IRQ_ENABLE.
    and #%11111110                          // AND A with #%11111110.
    sta IRQ_ENABLE                          // Disable raster IRQ while arming

    ldy LIVE_PLAN
    lda BATCH_COUNT,y
    bne !hasBatch+

    lda #%00000001                          // Select raster interrupt latch.
    sta IRQ_STATUS                          // Clear any stale raster condition.
    jmp !done+

!hasBatch:

    lda #0                                  // Load A from #0.
    sta BATCH_INDEX                         // Store A in BATCH_INDEX.

    lda #<multiplexIRQ                      // Load A from #<multiplexIRQ.
    sta IRQ_VECTOR                          // Store A in IRQ_VECTOR.
    lda #>multiplexIRQ                      // Load A from #>multiplexIRQ.
    sta IRQ_VECTOR + 1                      // Store A in IRQ_VECTOR + 1.

    lda VIC_CONTROL_1                       // Load A from VIC_CONTROL_1.
    and #%01111111                          // AND A with #%01111111.
    sta VIC_CONTROL_1                       // Raster compare below 256

    ldy LIVE_PLAN                           // Load Y from LIVE_PLAN.
    lda BATCH_RASTER,y                      // Load A from BATCH_RASTER,y.
    sta RASTER                              // Store A in RASTER.

    lda #%00000001                          // Load A from #%00000001.
    sta IRQ_STATUS                          // Clear stale raster IRQ
    lda IRQ_ENABLE                          // Load A from IRQ_ENABLE.
    ora #%00000001                          // OR A with #%00000001.
    sta IRQ_ENABLE                          // Store A in IRQ_ENABLE.
!done:
    cli                                     // Allow maskable IRQs.
    rts                                     // Return to the calling routine.

// --- Routine: multiplexIRQ --------------------------------------------------
// Apply one prepared LIVE_PLAN batch and chain to the next raster batch.
multiplexIRQ:
    lda IRQ_ENABLE                          // Check whether raster IRQ generation is currently enabled.
    and #%00000001                          // Isolate the VIC raster IRQ enable bit.
    beq !notRaster+                         // If disabled, this must be some other IRQ source.

    lda IRQ_STATUS                          // Read VIC interrupt status.
    and #%00000001                          // Isolate the raster interrupt flag.
    bne !raster+                            // Enabled + pending means this is one of our raster IRQs.

!notRaster:
    jmp $ea31                               // Let the normal KERNAL IRQ handler deal with it.

!raster:
    lda BATCH_INDEX                         // Load A from BATCH_INDEX.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc LIVE_PLAN                           // Add LIVE_PLAN to A, including carry.
    tax                                     // Buffered batch index

    lda BATCH_FIRST_ASSIGN,x                // Load A from BATCH_FIRST_ASSIGN,x.
    tay                                     // First ordinary assignment index
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc BATCH_ASSIGN_COUNT,x                // Add BATCH_ASSIGN_COUNT,x to A, including carry.
    sta IRQ_ASSIGN_END                      // Store A in IRQ_ASSIGN_END.

!assignmentLoop:
    sty IRQ_ASSIGN_INDEX                    // Store Y in IRQ_ASSIGN_INDEX.
    tya                                     // Copy Y into A.
    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc LIVE_PLAN                           // Add LIVE_PLAN to A, including carry.
    tay                                     // Buffered assignment index

    lda ASSIGN_SLOT,y                       // Load A from ASSIGN_SLOT,y.
    sta IRQ_SELECTED_SLOT                   // Store A in IRQ_SELECTED_SLOT.
    ldx IRQ_SELECTED_SLOT                   // Load X from IRQ_SELECTED_SLOT.

    lda ASSIGN_SPRITE,y                     // Load A from ASSIGN_SPRITE,y.
    sta HW_SPRITE_POINTER,x                 // Store A in HW_SPRITE_POINTER,x.
    lda ASSIGN_COLOUR,y                     // Load A from ASSIGN_COLOUR,y.
    sta HW_SPRITE_COLOUR,x                  // Store A in HW_SPRITE_COLOUR,x.

    lda HW_SPRITE_OFFSET,x                  // Load A from HW_SPRITE_OFFSET,x.
    tax                                     // Copy A into X.
    lda ASSIGN_X,y                          // Load A from ASSIGN_X,y.
    sta SPR_X,x                             // Store A in SPR_X,x.
    lda ASSIGN_Y,y                          // Load A from ASSIGN_Y,y.
    sta SPR_Y,x                             // Store A in SPR_Y,x.

    ldx IRQ_SELECTED_SLOT                   // Load X from IRQ_SELECTED_SLOT.
    lda SPRITE_OVERFLOW_REGISTER            // Load A from SPRITE_OVERFLOW_REGISTER.
    and HW_CLEAR_MASK,x                     // AND A with HW_CLEAR_MASK,x.
    sta SPRITE_OVERFLOW_REGISTER            // Store A in SPRITE_OVERFLOW_REGISTER.
    lda ASSIGN_X_MSB,y                      // Load A from ASSIGN_X_MSB,y.
    beq !msbDone+                           // Branch to !msbDone+ if the previous result was zero/equal.
    lda SPRITE_OVERFLOW_REGISTER            // Load A from SPRITE_OVERFLOW_REGISTER.
    ora HW_BIT_MASK,x                       // OR A with HW_BIT_MASK,x.
    sta SPRITE_OVERFLOW_REGISTER            // Store A in SPRITE_OVERFLOW_REGISTER.
!msbDone:

    ldy IRQ_ASSIGN_INDEX                    // Load Y from IRQ_ASSIGN_INDEX.
    iny                                     // Increment Y by one.
    cpy IRQ_ASSIGN_END                      // Compare Y with IRQ_ASSIGN_END; set flags, leaving Y unchanged.
    bne !assignmentLoop-                    // Branch to !assignmentLoop- if the previous result was non-zero/not equal.

    lda #%00000001                          // Load A from #%00000001.
    sta IRQ_STATUS                          // Acknowledge raster IRQ

    inc BATCH_INDEX                         // Increment BATCH_INDEX by one.
    ldy LIVE_PLAN                           // Load Y from LIVE_PLAN.
    lda BATCH_INDEX                         // Load A from BATCH_INDEX.
    cmp BATCH_COUNT,y                       // Compare A with BATCH_COUNT,y; set flags, leaving A unchanged.
    bcs !allDone+                           // Branch to !allDone+ if carry is set.

    clc                                     // Clear carry before an addition or shift-dependent operation.
    adc LIVE_PLAN                           // Add LIVE_PLAN to A, including carry.
    tax                                     // Copy A into X.
    lda BATCH_RASTER,x                      // Load A from BATCH_RASTER,x.
    sta RASTER                              // Arm next batch
    jmp $ea31                               // Jump unconditionally to $ea31.

!allDone:
    lda IRQ_ENABLE                          // Load the VIC interrupt-enable register.
    and #%11111110                          // Clear raster interrupt enable bit.
    sta IRQ_ENABLE                          // Disable further raster IRQ generation.

    lda #%00000001                          // Select the VIC raster interrupt latch.
    sta IRQ_STATUS                          // Clear any pending/stale raster condition.

    lda #0                                  // Reset batch position for the next frame.
    sta BATCH_INDEX                         // Store zero in BATCH_INDEX.
    jmp $ea31                               // Continue through the normal KERNAL IRQ handler.

// --- Routine: startRandomWave ------------------------------------------------
// Choose one spawn formation and one movement pattern independently.
// CIA1 timer bits provide a lightweight changing seed; gameplay does not need
// deterministic cryptographic-quality randomness here.
startRandomWave:
    lda CIA1_TIMER_A_LO                     // Sample the continuously changing CIA timer.
    pha                                     // Preserve the sample while loading formation state.
    and #%00000011                          // Bottom two bits select one of four formations.
    tay                                     // Y = formation index 0-3.

    lda formationSpriteStart,y               // Read this formation's first visual-sequence entry.
    sta WAVE_SPRITE_INDEX                    // Seed sprite/colour selection for its first member.

    lda formationEnemyCount,y               // Read number of enemies in this formation.
    sta WAVE_ENEMY_COUNT                    // Store target number of successful spawns.

    lda formationInterval,y                 // Read frames between formation members.
    sta WAVE_SPAWN_INTERVAL                 // Preserve interval for each timer reload.

    lda formationStartX,y                   // Read first enemy's starting X coordinate.
    sta WAVE_SPAWN_X                        // Seed cumulative horizontal spawn position.

    lda formationStartY,y                   // Read first enemy's starting Y coordinate.
    sta WAVE_SPAWN_Y                        // Seed cumulative vertical spawn position.

    lda formationAddX,y                     // Read horizontal offset between successive members.
    sta WAVE_ADD_X_VALUE                    // Preserve horizontal formation offset.

    lda formationAddY,y                     // Read vertical offset between successive members.
    sta WAVE_ADD_Y_VALUE                    // Preserve vertical formation offset.

    pla                                     // Recover the original timer sample.
    lsr                                     // Move a different pair of timer bits down.
    lsr                                     // Bits 2-3 now occupy bits 0-1.
    and #%00000011                          // Select one of four movement patterns independently.
    sta WAVE_PATTERN_ID                     // Save pattern number for each spawned object.

    lda #0                                  // A new wave has not spawned any members yet.
    sta WAVE_SPAWNED                        // Reset successful member count.
    sta SPAWN_TIMER                         // Zero makes the first member spawn immediately.
    rts

// --- Routine: findFreeObject ------------------------------------------------
// Find the first inactive logical object slot.
// Returns: X = free object index, carry clear.
//          Carry set if no free slot exists.
findFreeObject:
    ldx #1                                  // Object 0 is permanently reserved for the player.

!scan:
    lda OBJECT_ACTIVE,x                     // Check whether this logical object is currently in use.
    beq !found+                             // Zero means this slot is free.

    inx                                     // Try the next logical object.
    cpx #MAX_OBJECTS                        // Have we reached the end of the object pool?
    bne !scan-                              // No: continue scanning.

    sec                                     // Carry set means allocation failed.
    rts                                     // No free logical object slots remain.

!found:
    clc                                     // Carry clear means X contains a valid free slot.
    rts

// --- Routine: spawnEnemy ----------------------------------------------------
// Allocate and initialise one enemy from the current wave state.
// Returns: carry clear if spawned, carry set if the object pool was full.
spawnEnemy:
    jsr findFreeObject                      // Find an unused logical object slot.
    bcs !failed+                            // Abort if all logical object slots are occupied.

    lda WAVE_SPAWN_X                        // Read this wave member's current X position.
    sta OBJECT_X,x                          // Store low byte of enemy X position.
    lda #0                                  // Current wave format uses the low 256-pixel X region.
    sta OBJECT_X_MSB,x                      // Clear ninth X-coordinate bit.

    lda WAVE_SPAWN_Y                        // Read this wave member's current Y position.
    sta OBJECT_Y,x                          // Store initial enemy Y position.

    lda #TYPE_ENEMY                         // This logical object behaves as an enemy.
    sta OBJECT_TYPE,x                       // Store enemy object type.

    ldy WAVE_SPRITE_INDEX                  // Y selects this formation member's visual variant.
    lda enemySpriteSequence,y               // Read the sprite pointer chosen for this member.
    sta OBJECT_SPRITE,x                     // Store sprite bitmap index.

    lda enemyColourSequence,y               // Read this member's individual multicolour value.
    sta OBJECT_COLOUR,x                     // Store enemy colour.

    inc WAVE_SPRITE_INDEX                   // Advance only after a successful allocation/spawn.

    lda WAVE_PATTERN_ID                     // Read the movement pattern selected for this wave.
    sta OBJECT_PATTERN,x                    // Retain the pattern number for gameplay/debugging.
    tay                                     // Y = pattern number while X remains the allocated object slot.
    lda patternStartOffset,y                // Convert pattern number to its master-table byte offset.
    sta OBJECT_PATH_STEP,x                  // Begin this object at the selected pattern's first segment.
    lda #0                                  // Zero forces the first segment duration to load next update.
    sta OBJECT_PATH_TIMER,x                 // Reset movement path timer.

    lda #1                                  // Mark object active only after every field is initialised.
    sta OBJECT_ACTIVE,x                     // Object now participates in update/render processing.

    clc                                     // Signal successful spawn.
    rts

!failed:
    sec                                     // Preserve allocation-failed result.
    rts

// --- Routine: updateSpawner -------------------------------------------------
// Spawn the current formation, then leave a short gap before choosing another.
updateSpawner:
    lda WAVE_SPAWNED                        // Read how many members of this formation have spawned.
    cmp WAVE_ENEMY_COUNT                    // Compare against the current formation's requested count.
    bcc !waveActive+                        // Carry clear means this formation still has members to spawn.

    lda WAVE_GAP_TIMER                      // Formation is complete: read inter-formation delay.
    beq !startNext+                         // Zero means the director may choose another attack now.
    dec WAVE_GAP_TIMER                      // Consume one frame of breathing room between formations.
    bne !done+                              // Keep waiting while any gap remains.

!startNext:
    jsr startRandomWave                     // Choose a fresh formation + movement pattern combination.

!waveActive:
    lda SPAWN_TIMER                         // Read frames remaining until the next formation member.
    beq !spawn+                             // Zero means this member is ready to spawn.

    dec SPAWN_TIMER                         // Consume one frame of the inter-enemy delay.
    bne !done+                              // Non-zero means the delay is still running.

!spawn:
    jsr spawnEnemy                          // Try to allocate and initialise the next formation member.
    bcs !done+                              // Pool full: keep this position and retry next frame.

    inc WAVE_SPAWNED                        // Record one successfully created formation member.

    clc                                     // Clear carry before adding the horizontal formation offset.
    lda WAVE_SPAWN_X                        // Read the position used by the enemy just spawned.
    adc WAVE_ADD_X_VALUE                    // Add this formation's per-enemy horizontal offset.
    sta WAVE_SPAWN_X                        // Save the next member's starting X position.

    clc                                     // Clear carry before adding the vertical formation offset.
    lda WAVE_SPAWN_Y                        // Read the position used by the enemy just spawned.
    adc WAVE_ADD_Y_VALUE                    // Add this formation's per-enemy vertical offset.
    sta WAVE_SPAWN_Y                        // Save the next member's starting Y position.

    lda WAVE_SPAWNED                        // Re-check count before a possible same-frame spawn.
    cmp WAVE_ENEMY_COUNT                    // Has this formation now spawned every requested member?
    bcc !moreMembers+                       // No: prepare the interval before the next member.

    lda #WAVE_GAP                           // Final member launched: start the inter-formation gap.
    sta WAVE_GAP_TIMER                      // Director will remain idle until this expires.
    rts                                     // Do not begin another formation in this frame.

!moreMembers:
    lda WAVE_SPAWN_INTERVAL                 // Read this formation's delay between successful spawns.
    sta SPAWN_TIMER                         // Start the delay before the next member.
    beq !spawn-                             // Interval zero: spawn another member in this same frame.

!done:
    rts

// --- Sprite pointer lookup --------------------------------------------------
spritePointers:
    .byte playerSprite / 64             // Object 0
    .byte enemySpriteA / 64             // Object 1
    .byte enemySpriteB / 64             // Object 2
    .byte enemySpriteA / 64             // Object 3
    .byte enemySpriteB / 64             // Object 4
    .byte enemySpriteA / 64             // Object 5
    .byte enemySpriteB / 64             // Object 6
    .byte enemySpriteA / 64             // Object 7
    .byte enemySpriteB / 64             // Object 8
    .byte enemySpriteA / 64             // Object 9
    .byte enemySpriteB / 64             // Object 10
    .byte enemySpriteA / 64             // Object 11
    .byte enemySpriteB / 64             // Object 12
    .byte enemySpriteA / 64             // Object 13
    .byte enemySpriteB / 64             // Object 14
    .byte enemySpriteA / 64             // Object 15

// --- Read-only engine lookup tables ----------------------------------------
* = $1f00
HW_BIT_MASK:
    .byte %00000001,%00000010,%00000100,%00001000
    .byte %00010000,%00100000,%01000000,%10000000

HW_CLEAR_MASK:
    .byte %11111110,%11111101,%11111011,%11110111
    .byte %11101111,%11011111,%10111111,%01111111

SPRITE_ENABLE_MASK:
    .byte %00000000,%00000001,%00000011,%00000111,%00001111
    .byte %00011111,%00111111,%01111111,%11111111

LOOKUP_TABLES_END:
.if (LOOKUP_TABLES_END > $2000) {
    .error "Lookup tables overlap engine runtime state"
}

// --- Engine runtime state ---------------------------------------------------
* = $2000
OBJECT_X:              .fill MAX_OBJECTS, 0
OBJECT_Y:              .fill MAX_OBJECTS, 0
OBJECT_X_MSB:          .fill MAX_OBJECTS, 0
//OBJECT_DIR:            .fill MAX_OBJECTS, 0
OBJECT_ACTIVE:         .fill MAX_OBJECTS, 0
OBJECT_TYPE:           .fill MAX_OBJECTS, 0
HW_SPRITE_OFFSET:      .byte 0,2,4,6,8,10,12,14
OBJECT_SPRITE:         .fill MAX_OBJECTS, 0
OBJECT_COLOUR:         .fill MAX_OBJECTS, 0
SORTED_OBJECTS:        .fill MAX_OBJECTS, $ff
SORTED_COUNT:          .byte 0

OBJECT_PATTERN:        .fill MAX_OBJECTS, 0
OBJECT_PATH_STEP:      .fill MAX_OBJECTS, 0
OBJECT_PATH_TIMER:     .fill MAX_OBJECTS, 0

SPAWN_TIMER:           .byte 0
WAVE_GAP_TIMER:        .byte 0
WAVE_ENEMY_COUNT:      .byte 0
WAVE_SPAWN_INTERVAL:   .byte 0
WAVE_SPAWNED:          .byte 0
WAVE_SPAWN_X:          .byte 0
WAVE_SPAWN_Y:          .byte 0
WAVE_ADD_X_VALUE:      .byte 0
WAVE_ADD_Y_VALUE:      .byte 0
WAVE_PATTERN_ID:       .byte 0
WAVE_SPRITE_INDEX:      .byte 0              // Current entry in the formation's visual sequence.

BATCH_COUNT:           .fill 16, 0
BATCH_INDEX:           .byte 0
BATCH_RASTER:          .fill 16, 0
BATCH_FIRST_ASSIGN:    .fill 16, $ff
BATCH_ASSIGN_COUNT:    .fill 16, 0
ASSIGN_SLOT:           .fill 16, $ff
SLOT_FREE_RASTER:      .fill 8, $ff

LIVE_PLAN:             .byte 0          // Plan offsets are 0 or 8
BUILD_PLAN:            .byte 8
SNAPSHOT_INDEX:        .byte 0

INITIAL_X:             .fill 16, 0
INITIAL_Y:             .fill 16, 0
INITIAL_X_MSB:         .fill 16, 0
INITIAL_SPRITE:        .fill 16, 0
INITIAL_COLOUR:        .fill 16, 0

ASSIGN_X:              .fill 16, 0
ASSIGN_Y:              .fill 16, 0
ASSIGN_X_MSB:          .fill 16, 0
ASSIGN_SPRITE:         .fill 16, 0
ASSIGN_COLOUR:         .fill 16, 0

SCHED_OBJECT_INDEX:    .byte 0
SCHED_ASSIGN_INDEX:    .byte 0
SCHED_BATCH_SIZE:      .byte 0
SCHED_BATCH_LATEST:    .byte $ff
SCHED_SELECTED_SLOT:   .byte $ff
SCHED_SELECTED_FREE:   .byte $ff
SCHED_RENDER_COUNT:    .byte 0
RENDER_COUNT:          .fill 16, 0      // Initial hardware-sprite count per plan

IRQ_ASSIGN_INDEX:      .byte 0
IRQ_ASSIGN_END:        .byte 0
IRQ_SELECTED_SLOT:     .byte $ff

DEBUG_FRAME_COUNT:     .byte 0
DEBUG_RASTER_LO:       .byte 0
DEBUG_RASTER_HI:       .byte 0
DEBUG_LINES_LO:        .byte 0
DEBUG_LINES_HI:        .byte 0
DEBUG_FREE_LO:         .byte 0
DEBUG_FREE_HI:         .byte 0
DEBUG_MIN_LO:          .byte $ff
DEBUG_MIN_HI:          .byte $ff
DEBUG_VALUE_LO:        .byte 0
DEBUG_VALUE_HI:        .byte 0

ENGINE_STATE_END:
.if (ENGINE_STATE_END > $2400) {
    .error "Engine state overlaps sprite bitmap data"
}

// --- Sprite bitmap data -----------------------------------------------------
* = $2400

playerSprite:

    .byte $00,$3c,$00
    .byte $00,$3c,$00
    .byte $00,$ff,$00
    .byte $00,$eb,$00
    .byte $03,$eb,$c0
    .byte $03,$eb,$c0
    .byte $0f,$eb,$f0
    .byte $0f,$d7,$f0
    .byte $3f,$d7,$fc
    .byte $3f,$d7,$fc
    .byte $ff,$d7,$ff
    .byte $ff,$d7,$ff
    .byte $3f,$d7,$fc
    .byte $3f,$ff,$fc
    .byte $0f,$d7,$f0
    .byte $0f,$d7,$f0
    .byte $0f,$c3,$f0
    .byte $03,$c3,$c0
    .byte $03,$c3,$c0
    .byte $02,$82,$80
    .byte $02,$82,$80
    .byte $00            // 64th padding byte

enemySpriteA:
    .byte $00,$28,$00
    .byte $00,$aa,$00
    .byte $00,$be,$00
    .byte $02,$be,$80
    .byte $02,$7d,$80
    .byte $0a,$7d,$a0
    .byte $29,$69,$68
    .byte $a5,$aa,$5a
    .byte $96,$be,$96
    .byte $06,$ff,$90
    .byte $06,$eb,$90
    .byte $06,$aa,$90
    .byte $01,$aa,$40
    .byte $01,$69,$40
    .byte $00,$69,$00
    .byte $00,$7d,$00
    .byte $01,$41,$40
    .byte $05,$00,$50
    .byte $14,$00,$14
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00                              // 64th padding byte

enemySpriteB:
    .byte $00,$28,$00
    .byte $00,$be,$00
    .byte $02,$be,$80
    .byte $0a,$7d,$a0
    .byte $29,$69,$68
    .byte $a5,$28,$5a
    .byte $94,$28,$16
    .byte $50,$be,$05
    .byte $42,$ff,$81
    .byte $0b,$eb,$e0
    .byte $2b,$aa,$e8
    .byte $26,$be,$98
    .byte $05,$aa,$50
    .byte $01,$69,$40
    .byte $00,$7d,$00
    .byte $01,$41,$40
    .byte $05,$00,$50
    .byte $04,$00,$10
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00                              // 64th padding byte

enemySpriteC:
    .byte $00,$14,$00
    .byte $00,$69,$00
    .byte $01,$aa,$40
    .byte $06,$be,$90
    .byte $1a,$ff,$a4
    .byte $6b,$eb,$e9
    .byte $6f,$aa,$f9
    .byte $6e,$96,$b9
    .byte $6a,$55,$a9
    .byte $7a,$69,$ad
    .byte $7e,$aa,$bd
    .byte $6f,$aa,$f9
    .byte $1b,$eb,$e4
    .byte $06,$ff,$90
    .byte $01,$be,$40
    .byte $01,$69,$40
    .byte $05,$28,$50
    .byte $14,$00,$14
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00                              // 64th padding byte

enemySpriteD:
    .byte $00,$3c,$00
    .byte $00,$eb,$00
    .byte $01,$eb,$40
    .byte $05,$eb,$50
    .byte $14,$eb,$14
    .byte $50,$eb,$05
    .byte $41,$be,$41
    .byte $06,$be,$90
    .byte $1a,$ff,$a4
    .byte $6b,$eb,$e9
    .byte $1b,$aa,$e4
    .byte $06,$be,$90
    .byte $01,$aa,$40
    .byte $01,$69,$40
    .byte $05,$3c,$50
    .byte $14,$3c,$14
    .byte $50,$14,$05
    .byte $40,$00,$01
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00                              // 64th padding byte

// --- Spawn formations -------------------------------------------------------
// Formation data is stored as parallel tables indexed 0-3.  Movement is not
// encoded here: startRandomWave chooses a movement pattern independently.
//
// 0: tight stream from one entry point.
// 1: staggered diagonal entry.
// 2: simultaneous horizontal line.
// 3: descending diagonal stream moving left between successive spawns.
formationEnemyCount:
    .byte 8, 6, 7, 5
formationInterval:
    .byte 50, 24, 0, 18
formationStartX:
    .byte 120, 80, 65, 180
formationStartY:
    .byte 40, 35, 45, 25
formationAddX:
    .byte 0, 14, 28, $f8                   // $f8 = -8 for formation 3.
formationAddY:
    .byte 0, 5, 0, 4

// --- Formation visual sequences --------------------------------------------
// Each formation has eight visual entries. Shorter formations simply consume
// the prefix they need. Sprite shape and individual colour are independent of
// movement pattern, so the same attack geometry can still look varied.
formationSpriteStart:
    .byte 0, 8, 16, 24

enemySpriteSequence:
    // Formation 0: alternating spear/scout with heavier ships in the middle.
    .byte enemySpriteA/64, enemySpriteB/64, enemySpriteA/64, enemySpriteC/64
    .byte enemySpriteC/64, enemySpriteA/64, enemySpriteB/64, enemySpriteA/64

    // Formation 1: four visibly different ships cycling through the stagger.
    .byte enemySpriteB/64, enemySpriteC/64, enemySpriteD/64, enemySpriteA/64
    .byte enemySpriteB/64, enemySpriteC/64, enemySpriteD/64, enemySpriteA/64

    // Formation 2: symmetric-looking instant line.
    .byte enemySpriteD/64, enemySpriteC/64, enemySpriteB/64, enemySpriteA/64
    .byte enemySpriteB/64, enemySpriteC/64, enemySpriteD/64, enemySpriteA/64

    // Formation 3: heavier-looking descending group.
    .byte enemySpriteC/64, enemySpriteD/64, enemySpriteC/64, enemySpriteB/64
    .byte enemySpriteD/64, enemySpriteC/64, enemySpriteB/64, enemySpriteA/64

enemyColourSequence:
    // Individual VIC colour for each matching sprite-sequence entry.
    .byte 2, 6, 10, 7, 7, 10, 6, 2
    .byte 6, 13, 7, 10, 6, 13, 7, 10
    .byte 14, 13, 7, 2, 7, 13, 14, 2
    .byte 7, 14, 7, 10, 14, 7, 10, 2

// --- Movement pattern offsets ----------------------------------------------
// Each object stores a byte offset into enemyPatterns as OBJECT_PATH_STEP.
// This lets the existing path interpreter read any pattern without pointers.
patternStartOffset:
    .byte patternDiveLeft-enemyPatterns
    .byte patternDiveRight-enemyPatterns
    .byte patternZigzag-enemyPatterns
    .byte patternSweep-enemyPatterns

// --- Enemy movement patterns ------------------------------------------------
// Segments: duration, signed dx, signed dy.  Duration $ff means keep applying
// that final vector until normal off-screen lifecycle logic removes the enemy.
// Duration 0 remains an explicit terminator if a future pattern needs one.
enemyPatterns:

patternDiveLeft:
    .byte 80,  0,  2                       // Dive vertically.
    .byte  6,  0,  2                       // Hold downward direction into the turn.
    .byte  6, $ff, 2                       // Begin bending left.
    .byte  6, $ff, 1                       // Diagonal down-left.
    .byte  6, $fe, 1                       // Turn more strongly left.
    .byte  6, $fe, 0                       // Complete the turn.
    .byte $ff,$fe, 0                       // Keep flying left until X lifecycle removes it.

patternDiveRight:
    .byte 60,  0,  2                       // Dive before beginning the mirrored turn.
    .byte  6,  0,  2                       // Hold downward direction.
    .byte  6,  1,  2                       // Begin bending right.
    .byte  6,  1,  1                       // Diagonal down-right.
    .byte  6,  2,  1                       // Turn more strongly right.
    .byte  6,  2,  0                       // Complete the turn.
    .byte $ff, 2,  0                       // Keep flying right until X lifecycle removes it.

patternZigzag:
    .byte 36,  1,  2                       // Sweep down-right.
    .byte 36, $ff, 2                       // Reverse into a down-left sweep.
    .byte 36,  1,  2                       // Sweep right again.
    .byte $ff,$ff, 2                       // Continue final down-left vector until naturally off-screen.

patternSweep:
    .byte 28, $ff, 1                       // Shallow down-left opening sweep.
    .byte 28,  1,  1                       // Cross back down-right.
    .byte 28,  1,  2                       // Steepen the rightward dive.
    .byte $ff,$ff, 2                       // Continue final steep down-left vector until off-screen.
