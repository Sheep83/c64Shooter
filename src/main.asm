.filenamespace test
:BasicUpstart2(init)

#import "variables.asm"

.const MAX_OBJECTS = 16
.const TYPE_PLAYER = 1
.const TYPE_ENEMY  = 2

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

    jsr setupSprites                        // Call setupSprites; return here when it executes RTS.

    lda #1                                  // Load A from #1.
    sta MOB_X_VEL                           // Enemy horizontal speed

    lda #1                                  // Load A from #1.
    sta OBJECT_ACTIVE                       // Object 0 = player
    lda #TYPE_PLAYER                        // Load A from #TYPE_PLAYER.
    sta OBJECT_TYPE                         // Store A in OBJECT_TYPE.
    lda #playerSprite / 64                  // Load A from #playerSprite / 64.
    sta OBJECT_SPRITE                       // Store A in OBJECT_SPRITE.
    lda #2                                  // Load A from #2.
    sta OBJECT_COLOUR                       // Store A in OBJECT_COLOUR.

    ldx #1                                  // Load X from #1.
!enemyInit:
    lda #1                                  // Load A from #1.
    sta OBJECT_ACTIVE,x                     // Store A in OBJECT_ACTIVE,x.
    lda #TYPE_ENEMY                         // Load A from #TYPE_ENEMY.
    sta OBJECT_TYPE,x                       // Store A in OBJECT_TYPE,x.
    lda spritePointers,x                    // Load A from spritePointers,x.
    sta OBJECT_SPRITE,x                     // Store A in OBJECT_SPRITE,x.
    lda #3                                  // Load A from #3.
    sta OBJECT_COLOUR,x                     // Store A in OBJECT_COLOUR,x.
    inx                                     // Increment X by one.
    cpx #MAX_OBJECTS                        // Compare X with #MAX_OBJECTS; set flags, leaving X unchanged.
    bne !enemyInit-                         // Branch to !enemyInit- if the previous result was non-zero/not equal.

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
    jsr buildSortedObjectList               // Call buildSortedObjectList; return here when it executes RTS.
    jsr sortObjectsByY                      // Call sortObjectsByY; return here when it executes RTS.
    jsr buildInitialSpriteSnapshot          // Call buildInitialSpriteSnapshot; return here when it executes RTS.
    jsr buildBatchSpriteSchedule            // Call buildBatchSpriteSchedule; return here when it executes RTS.

    jsr waitForFrameStart                   // Call waitForFrameStart; return here when it executes RTS.
    jsr swapRenderPlans                     // Call swapRenderPlans; return here when it executes RTS.
    jsr renderSprites                       // Call renderSprites; return here when it executes RTS.
    jsr armFirstBatch                       // Call armFirstBatch; return here when it executes RTS.
    jmp !frameLoop-                         // Jump unconditionally to !frameLoop-.

// --- Routine: setupSprites --------------------------------------------------
// Enable VIC sprites and seed logical object positions.
setupSprites:
    lda #$ff                                // Load A from #$ff.
    sta SPRITE_ENABLE                       // Enable all 8 hardware sprites

    lda #146                                // Load A from #146.
    sta OBJECT_X                            // Player X
    lda #200                                // Load A from #200.
    sta OBJECT_Y                            // Player Y
    lda #0                                  // Load A from #0.
    sta OBJECT_X_MSB                        // Store A in OBJECT_X_MSB.

    lda #31                                 // Load A from #31.
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
    jsr moveEnemy                           // Call moveEnemy; return here when it executes RTS.

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

// --- Routine: moveEnemy -----------------------------------------------------
// Move one enemy horizontally, handling the ninth X bit and edge reversal.
moveEnemy:
    lda OBJECT_DIR,x                        // Load A from OBJECT_DIR,x.
    beq !right+                             // Branch to !right+ if the previous result was zero/equal.

    sec                                     // Set carry before subtraction or a carry-dependent operation.
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    sbc MOB_X_VEL                           // Subtract MOB_X_VEL from A using carry as the inverted borrow.
    sta OBJECT_X,x                          // Store A in OBJECT_X,x.
    cmp #255                                // Compare A with #255; set flags, leaving A unchanged.
    bne !leftEdge+                          // Branch to !leftEdge+ if the previous result was non-zero/not equal.
    lda #0                                  // Load A from #0.
    sta OBJECT_X_MSB,x                      // 256 -> 255

!leftEdge:
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    cmp #23                                 // Compare A with #23; set flags, leaving A unchanged.
    bne !done+                              // Branch to !done+ if the previous result was non-zero/not equal.
    lda OBJECT_X_MSB,x                      // Load A from OBJECT_X_MSB,x.
    bne !done+                              // Branch to !done+ if the previous result was non-zero/not equal.
    lda OBJECT_DIR,x                        // Load A from OBJECT_DIR,x.
    eor #1                                  // XOR A with #1.
    sta OBJECT_DIR,x                        // Reverse at left edge
!done:
    rts                                     // Return to the calling routine.

!right:
    clc                                     // Clear carry before an addition or shift-dependent operation.
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    adc MOB_X_VEL                           // Add MOB_X_VEL to A, including carry.
    sta OBJECT_X,x                          // Store A in OBJECT_X,x.
    cmp #0                                  // Compare A with #0; set flags, leaving A unchanged.
    bne !rightEdge+                         // Branch to !rightEdge+ if the previous result was non-zero/not equal.
    lda #1                                  // Load A from #1.
    sta OBJECT_X_MSB,x                      // 255 -> 256

!rightEdge:
    lda OBJECT_X,x                          // Load A from OBJECT_X,x.
    cmp #66                                 // Compare A with #66; set flags, leaving A unchanged.
    bne !done-                              // Branch to !done- if the previous result was non-zero/not equal.
    lda OBJECT_X_MSB,x                      // Load A from OBJECT_X_MSB,x.
    beq !done-                              // Branch to !done- if the previous result was zero/equal.
    lda OBJECT_DIR,x                        // Load A from OBJECT_DIR,x.
    eor #1                                  // XOR A with #1.
    sta OBJECT_DIR,x                        // Reverse at right edge
    rts                                     // Return to the calling routine.

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
// Return during raster 0-19 of the next frame.
waitForFrameStart:
!wait:
    lda VIC_CONTROL_1                       // Load A from VIC_CONTROL_1.
    bmi !wait-                              // Still in raster 256-311
    lda RASTER                              // Load A from RASTER.
    cmp #20                                 // Compare A with #20; set flags, leaving A unchanged.
    bcs !wait-                              // Branch to !wait- if carry is set.
    rts                                     // Return to the calling routine.

// --- Routine: renderSprites -------------------------------------------------
// Write LIVE_PLAN's initial hardware-sprite snapshot to VIC-II.
renderSprites:
    lda #0                                  // Load A from #0.
    sta TEMP_MSB                            // Store A in TEMP_MSB.

    ldy LIVE_PLAN                           // Load Y from LIVE_PLAN.
    lda RENDER_COUNT,y                      // Load A from RENDER_COUNT,y.
    beq !none+                              // Branch to !none+ if the previous result was zero/equal.
    sta TEMP_OBJECT                         // Cache live sprite count

    ldx #0                                  // Load X from #0.
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

    ldy LIVE_PLAN                           // Load Y from LIVE_PLAN.
    lda BATCH_COUNT,y                       // Load A from BATCH_COUNT,y.
    beq !done+                              // Branch to !done+ if the previous result was zero/equal.

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
    lda IRQ_STATUS                          // Load A from IRQ_STATUS.
    and #%00000001                          // AND A with #%00000001.
    bne !raster+                            // Branch to !raster+ if the previous result was non-zero/not equal.
    jmp $ea31                               // Not our VIC raster IRQ

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
    lda IRQ_ENABLE                          // Load A from IRQ_ENABLE.
    and #%11111110                          // AND A with #%11111110.
    sta IRQ_ENABLE                          // No more batches this frame
    lda #0                                  // Load A from #0.
    sta BATCH_INDEX                         // Store A in BATCH_INDEX.
    jmp $ea31                               // Jump unconditionally to $ea31.

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

LOOKUP_TABLES_END:
.if (LOOKUP_TABLES_END > $2000) {
    .error "Lookup tables overlap engine runtime state"
}

// --- Engine runtime state ---------------------------------------------------
* = $2000
OBJECT_X:              .fill MAX_OBJECTS, 0
OBJECT_Y:              .fill MAX_OBJECTS, 0
OBJECT_X_MSB:          .fill MAX_OBJECTS, 0
OBJECT_DIR:            .fill MAX_OBJECTS, 0
OBJECT_ACTIVE:         .fill MAX_OBJECTS, 0
OBJECT_TYPE:           .fill MAX_OBJECTS, 0
HW_SPRITE_OFFSET:      .byte 0,2,4,6,8,10,12,14
OBJECT_SPRITE:         .fill MAX_OBJECTS, 0
OBJECT_COLOUR:         .fill MAX_OBJECTS, 0
SORTED_OBJECTS:        .fill MAX_OBJECTS, $ff
SORTED_COUNT:          .byte 0

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

ENGINE_STATE_END:
.if (ENGINE_STATE_END > $2400) {
    .error "Engine state overlaps sprite bitmap data"
}

// --- Sprite bitmap data -----------------------------------------------------
* = $2400

playerSprite:
.byte $00,$00,$00,$7f,$ff,$fe,$40,$18
.byte $02,$40,$18,$02,$40,$18,$02,$40
.byte $18,$02,$40,$18,$02,$40,$18,$02
.byte $40,$18,$02,$40,$18,$02,$7f,$ff
.byte $fe,$40,$18,$02,$40,$18,$02,$40
.byte $18,$02,$40,$18,$02,$40,$18,$02
.byte $40,$18,$02,$40,$18,$02,$40,$18
.byte $02,$7f,$ff,$fe,$00,$00,$00,$0a

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
    .byte $00

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
    .byte $00
