.filenamespace test
:BasicUpstart2(init)

#import "variables.asm"

.const MAX_OBJECTS = 16
.const TYPE_PLAYER = 1
.const TYPE_ENEMY  = 2
.const TYPE_ENEMY_BULLET = 3

.const MAX_ENEMY_BULLETS = 3
.const ENEMY_FIRE_INTERVAL = 42              // Global frames between successful/attempted enemy shots.
.const ENEMY_BULLET_SPEED_Y = 3              // Fixed downward speed; X is quantised to a smooth -2..+2 slope.
.const ENEMY_BULLET_COLOUR = 7               // Yellow individual sprite colour for the first projectile pass.

.const DEBUG_SCREEN = $0400
.const DEBUG_COLOUR = $d800
.const DEBUG_FRAMES = 50
.const SCORE_SCREEN = $0400 + 29              // Top row, right-aligned: "SCORE 00000".
.const SCORE_COLOUR = $d800 + 29
.const SCORE_PER_KILL = 100                   // First-pass fixed reward for every destroyed enemy.
.const LIVES_SCREEN = $0400 + 17               // Top row between FREE and SCORE: "LIVES 3".
.const LIVES_COLOUR = $d800 + 17
.const PLAYER_START_LIVES = 3                  // Three ships total, including the one currently in play.
.const GAME_OVER_SCREEN = $0400 + (12 * 40) + 15
.const GAME_OVER_HOLD_FRAMES = 180                 // ~3.6 PAL seconds on the GAME OVER screen.
.const HEALTH_SPRITE_BASE = $3000                // Private per-object sprite copies live at $3000-$33ff.
.const HEALTH_SPRITE_BASE_PTR = HEALTH_SPRITE_BASE / 64

.const STAR_COUNT = 16                              // Two-layer background stars; no hardware sprites consumed.
.const STAR_CHARSET = $3800                         // RAM copy of normal charset in VIC bank 0.
.const STAR_CHAR_BASE = 240                         // Custom chars 240-251 = 3 sizes x 4 phases.
.const STAR_GLYPH_BYTES = 96

.const ATTACK_TOP_TURN_LEFT       = 0
.const ATTACK_TOP_TURN_RIGHT      = 1
.const ATTACK_TOP_LOOP_LEFT       = 2
.const ATTACK_TOP_LOOP_RIGHT      = 3
.const ATTACK_TOP_LOOP_TOP        = 4
.const ATTACK_LEFT_U_TURN_UP      = 5
.const ATTACK_RIGHT_U_TURN_UP     = 6
.const ATTACK_LEFT_U_TURN_DOWN    = 7
.const ATTACK_RIGHT_U_TURN_DOWN   = 8
// New curated combinations demonstrating fragment reuse: existing ingress,
// manoeuvre and egress fragments re-paired in ways the old monolithic paths
// never expressed, added at no cost in new path data.
.const ATTACK_TOP_LONG_TURN_RIGHT     = 9   // Loop-family's long straight ingress feeding the tight turn-right manoeuvre.
.const ATTACK_LEFT_SHALLOW_UP_TURN    = 10  // Shallow down-cross ingress feeding the sharper up-turn manoeuvre.
.const ATTACK_RIGHT_SHALLOW_UP_TURN   = 11  // Mirror of the above.

.const ATTACK_COUNT = 12
.const CIA1_TIMER_A_LO = $dc04
.const WAVE_GAP        = 150                 // Frames between completed spawn formations.
.const ENEMY_EXIT_RIGHT_LO = $58            // 344 = $0158, just beyond the right edge.
.const ENEMY_ACCEL_INTERVAL = 12             // Descending enemies gain one pixel/frame of speed every 12 frames.
.const ENEMY_MAX_PATH_SPEED = 3              // Cap integer path velocity so acceleration cannot run away.
.const VIC_SPRITE_COLLISION = $d01e            // Reading clears the latched sprite/sprite collision bits.

// Segmented movement: every enemy attack is an ingress fragment, then a
// manoeuvre fragment, then an egress fragment, chained via OBJECT_STAGE.
.const STAGE_INGRESS   = 0
.const STAGE_MANOEUVRE = 1
.const STAGE_EGRESS    = 2

// Cheap direction-class bitmask used only at assemble time (never at runtime)
// to verify a curated attack's ingress->manoeuvre->egress chain is a sensible
// join: a fragment's exit class must share a bit with the next fragment's
// entry mask.  Diagonal exits/entries set two bits.
.const DIR_UP    = %0001
.const DIR_DOWN  = %0010
.const DIR_LEFT  = %0100
.const DIR_RIGHT = %1000
.const DIR_ANY   = %1111

// Fragment IDs (declared here, not beside their data tables further down,
// because KickAssembler resolves .var/List() attack tables in one pass and
// needs these consts defined before that point).
.const INGRESS_TOP_STRAIGHT_SHORT    = 0   // Short straight dive; feeds the tight top turns.
.const INGRESS_TOP_STRAIGHT_LONG     = 1   // Longer straight dive; feeds the loops (and, reused, attack 9).
.const INGRESS_LEFT_DIAG_CROSS_UP    = 2   // Upper-left cross, feeds an upward U-turn.
.const INGRESS_RIGHT_DIAG_CROSS_UP   = 3   // Mirror.
.const INGRESS_LEFT_DIAG_CROSS_DOWN  = 4   // Upper-left cross, feeds a downward U-turn (shallower/shorter than above).
.const INGRESS_RIGHT_DIAG_CROSS_DOWN = 5   // Mirror.
.const INGRESS_COUNT = 6

.const MANOEUVRE_TURN_LEFT        = 0
.const MANOEUVRE_TURN_RIGHT       = 1
.const MANOEUVRE_LOOP_LEFT        = 2
.const MANOEUVRE_LOOP_RIGHT       = 3
.const MANOEUVRE_LOOP_TOP         = 4
.const MANOEUVRE_UTURN_UP_LEFT    = 5
.const MANOEUVRE_UTURN_UP_RIGHT   = 6
.const MANOEUVRE_UTURN_DOWN_LEFT  = 7
.const MANOEUVRE_UTURN_DOWN_RIGHT = 8
.const MANOEUVRE_COUNT = 9

.const EGRESS_COAST       = 0   // Generic: just inherit whatever velocity the manoeuvre ended with.
.const EGRESS_UPPER_LEFT  = 1   // Shape a shallow up-left tangent before coasting.
.const EGRESS_UPPER_RIGHT = 2   // Mirror.
.const EGRESS_COUNT = 3

.const PLAYER_STATE_ALIVE      = 0
.const PLAYER_STATE_EXPLODING  = 1
.const PLAYER_STATE_RESPAWNING = 2
.const PLAYER_STATE_GAME_OVER  = 3

// Top-level game states, dispatched once per frame by mainLoop in the same
// cmp/beq style as PLAYER_STATE is dispatched inside the game itself.
.const GAME_STATE_MENU           = 0          // Attract screen: starfield + title / high-score pages.
.const GAME_STATE_PLAYING        = 1          // The core game frame loop (gameLoop).
.const GAME_STATE_GAME_OVER      = 2          // Brief "GAME OVER" hold before menu / initials entry.
.const GAME_STATE_ENTER_INITIALS = 3          // Type three initials for a qualifying score.

.const MENU_TITLE_SCREEN  = $0400 + (6 * 40) + 10    // Row 6, centred for "MY FIRST C64 SHOOTER" (20).
.const MENU_PROMPT_SCREEN = $0400 + (20 * 40) + 13   // Row 20, centred for "FIRE TO START" (13).

.const HISCORE_COUNT          = 8                    // High-score table entries.
.const HISCORE_START_SCORE    = 100                  // Every seeded entry starts here.
.const HISCORE_HEADING_SCREEN = $0400 + (4 * 40) + 14 // Row 4, centred for "HIGH SCORES" (11).
.const HISCORE_ROW_WIDTH      = 10                   // "III  DDDDD": 3 initials, 2 spaces, 5 digits.

.const ATTRACT_PAGE_TITLE  = 0
.const ATTRACT_PAGE_SCORES = 1
.const ATTRACT_CYCLE_FRAMES = 250                    // ~5 PAL seconds per attract page.

.const INITIALS_PROMPT_SCREEN = $0400 + (10 * 40) + 10  // Row 10, "ENTER YOUR INITIALS" (19).
.const INITIALS_SLOTS_SCREEN  = $0400 + (14 * 40) + 18  // Row 14: three letters at cols 18/20/22.
.const PLAYER_START_X          = 160
.const PLAYER_START_Y          = 220
.const PLAYER_EXPLOSION_HOLD   = 5              // Frames each explosion bitmap remains visible.
.const PLAYER_RESPAWN_TIME     = 100            // Invulnerable blinking frames after repositioning.

.const PLAYER_FIRE_COOLDOWN    = 8              // Frames between held-fire volleys.
.const PLAYER_MUZZLE_TIME      = 3              // Frames the muzzle-flash sprite remains visible.
.const PLAYER_LEFT_CANNON_X    = 4              // Horizontal ray offset from player sprite X.
.const PLAYER_RIGHT_CANNON_X   = 19             // Horizontal ray offset from player sprite X.
.const ENEMY_START_HEALTH      = 6              // Three centred dual-cannon volleys before future death handling.
.const ENEMY_HIT_FLASH_TIME    = 4              // Short white/yellow impact flash.
.const ENEMY_DEATH_TIME         = 12             // Total frames before the logical enemy slot is released.
.const ENEMY_DEATH_FRAME_TIME   = 4              // Four frames per explosion bitmap.

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

// --- Routine: init --------------------------------------------------------
// One-time hardware bring-up only. Per-game state now lives in startGame, so
// init just configures the VIC, paints the starfield, and drops into the
// attract screen via the mainLoop state router.
init:
    lda VIC_BANK                            // Load A from VIC_BANK.
    and #%11111100                          // AND A with #%11111100.
    ora #%00000011                          // OR A with #%00000011.
    sta VIC_BANK                            // VIC bank 0 ($0000-$3fff)

    jsr setupStarfieldCharset              // Copy ROM charset and install animated star glyphs.

    lda VIC_MEMORY_SETUP
    and #%11110000                          // Preserve screen RAM selection ($0400).
    ora #%00001110                          // Character set at $3800 within VIC bank 0.
    sta VIC_MEMORY_SETUP

    lda #0
    sta BORDER_COLOUR                       // Black border.
    sta BACKGROUND_COLOUR                   // Black playfield.

    jsr setupStarfield                      // Seed star positions/phases and paint them once.
    jsr seedHiscoreTable                    // Fill the high-score table with random initials, all at 100.

    lda #GAME_STATE_MENU                    // Boot straight into the attract screen.
    sta GAME_STATE
    jsr enterMenu                           // Clear screen, repaint stars, draw the first attract page.
    jmp mainLoop                            // Enter the top-level state router.

// --- Routine: startGame --------------------------------------------------
// Reset every per-game variable, wipe leftover menu text, build the first
// render plan, and switch the top-level state to PLAYING. Re-callable for
// each new game from the attract screen.
startGame:
    lda #147                                // Wipe any menu / high-score text from screen RAM.
    jsr $ffd2
    jsr drawStarfield                       // Repaint every star over the freshly cleared screen.

    jsr setupDebugDisplay                   // Draw the FREE-cycle display and initialise its rolling minimum.
    jsr setupScoreDisplay                   // Draw "SCORE 00000" and clear the 16-bit score.
    jsr setupLivesDisplay                   // Draw "LIVES 3" and initialise the player's stock.
    jsr setupSprites                        // Reapply sprite VIC config and seed placeholder positions.
    jsr startRandomWave                      // Choose the first formation/pattern combination.

    ldx #0                                  // Release every logical object slot left over from a previous game.
!clearObjects:
    lda #0
    sta OBJECT_ACTIVE,x
    sta OBJECT_DEATH_TIMER,x
    sta OBJECT_HIT_TIMER,x
    sta OBJECT_HEALTH,x
    inx
    cpx #MAX_OBJECTS
    bne !clearObjects-

    lda #PLAYER_START_X                     // Reset player low X coordinate to its normal start point.
    sta OBJECT_X                            // Object 0 is permanently player-owned.
    lda #0                                  // Player start X is within the low 256-pixel range.
    sta OBJECT_X_MSB
    lda #PLAYER_START_Y                     // Reset player Y coordinate near the bottom of the playfield.
    sta OBJECT_Y

    lda #PLAYER_STATE_ALIVE                 // Begin in the normal controllable/collidable state.
    sta PLAYER_STATE
    lda #0
    sta PLAYER_HIT
    sta PLAYER_STATE_TIMER
    sta PLAYER_EXPLOSION_FRAME
    sta PLAYER_BLINK_TIMER
    sta PLAYER_FIRE_COOLDOWN_TIMER
    sta PLAYER_MUZZLE_TIMER
    sta ENEMY_BULLET_COUNT                  // No hostile projectiles exist at game start.
    lda #ENEMY_FIRE_INTERVAL
    sta ENEMY_FIRE_TIMER                    // Give the opening wave a short grace period before the first shot.

    lda #1                                  // Load A from #1.
    sta OBJECT_ACTIVE                       // Object 0 = player
    lda #TYPE_PLAYER                        // Load A from #TYPE_PLAYER.
    sta OBJECT_TYPE                         // Store A in OBJECT_TYPE.
    lda #playerSprite / 64                  // Load A from #playerSprite / 64.
    sta OBJECT_SPRITE                       // Store A in OBJECT_SPRITE.
    lda #2                                  // Load A from #2.
    sta OBJECT_COLOUR                       // Store A in OBJECT_COLOUR.

    jsr buildSortedObjectList               // Call buildSortedObjectList; return here when it executes RTS.
    jsr sortObjectsByY                      // Call sortObjectsByY; return here when it executes RTS.
    jsr buildInitialSpriteSnapshot          // Call buildInitialSpriteSnapshot; return here when it executes RTS.
    jsr buildBatchSpriteSchedule            // Call buildBatchSpriteSchedule; return here when it executes RTS.
    jsr swapRenderPlans                     // Call swapRenderPlans; return here when it executes RTS.

    lda #GAME_STATE_PLAYING                 // Hand the router the running-game state.
    sta GAME_STATE
    rts

// --- Routine: mainLoop --------------------------------------------------
// Top-level game-state router. Each state's handler owns its own per-frame
// loop and returns here when the state changes, mirroring the PLAYER_STATE
// cmp/beq dispatch used inside the game.
mainLoop:
!router:
    lda GAME_STATE                          // Which top-level state are we in?
    cmp #GAME_STATE_PLAYING
    bne !notPlaying+
    jsr gameLoop                            // Runs until the player reaches GAME OVER.
    jmp !router-
!notPlaying:
    cmp #GAME_STATE_GAME_OVER
    bne !notGameOver+
    jsr gameOverScreen                      // Holds "GAME OVER", then routes to the menu.
    jmp !router-
!notGameOver:
    cmp #GAME_STATE_ENTER_INITIALS
    bne !menuState+
    jsr enterInitialsScreen                 // Type three initials, then routes to the menu.
    jmp !router-
!menuState:
    jsr attractMenu                         // Runs until fire starts a new game.
    jmp !router-

// --- Routine: gameLoop -------------------------------------------------
// The core game frame loop: display LIVE_PLAN while the CPU prepares
// BUILD_PLAN for the next frame. Returns to the router once the player has
// lost every life (PLAYER_STATE_GAME_OVER).
gameLoop:
    jsr waitForFrameStart                   // Call waitForFrameStart; return here when it executes RTS.
    jsr renderSprites                       // Call renderSprites; return here when it executes RTS.
    jsr armFirstBatch                       // Call armFirstBatch; return here when it executes RTS.

!frameLoop:
    jsr updateEnemyHitEffects               // Advance enemy death animation and prior-frame hit colour flash.
    jsr updatePlayerCombatEffects           // Decay prior-frame muzzle-flash and fire-cooldown timers.
    jsr updateObjects                       // Update movement and allow the player to fire this frame.
    jsr updateEnemyFire                     // Let at most one eligible enemy launch an aimed projectile.
    jsr updatePlayerState                   // Advance explosion/respawn state and consume any player-hit event.

    lda PLAYER_STATE                        // Has the last life just been spent?
    cmp #PLAYER_STATE_GAME_OVER
    bne !stillPlaying+
    jsr endGame                             // Tear down the raster IRQ / sprites and set the next state.
    rts                                     // Back to the router.
!stillPlaying:

    jsr updateSpawner                       // Periodically create a new enemy.
    jsr updateStarfield                     // Scroll and twinkle the character background.
    jsr buildSortedObjectList               // Call buildSortedObjectList; return here when it executes RTS.
    jsr sortObjectsByY                      // Call sortObjectsByY; return here when it executes RTS.
    jsr buildInitialSpriteSnapshot          // Call buildInitialSpriteSnapshot; return here when it executes RTS.
    jsr buildBatchSpriteSchedule            // Call buildBatchSpriteSchedule; return here when it executes RTS.
    jsr updateCycleDebug                    // Record the worst-case remaining free-cycle budget this frame.

    jsr waitForFrameStart                   // Call waitForFrameStart; return here when it executes RTS.
    jsr swapRenderPlans                     // Call swapRenderPlans; return here when it executes RTS.
    jsr renderSprites                       // Call renderSprites; return here when it executes RTS.
    jsr armFirstBatch                       // Call armFirstBatch; return here when it executes RTS.
    jmp !frameLoop-                         // Jump unconditionally to !frameLoop-.

// --- Routine: endGame ---------------------------------------------------
// PLAIN ENGLISH: the instant your last life is gone the game freezes. The
// per-scanline interrupt that juggles more than eight sprites is switched
// off, the KERNAL's normal interrupt is put back in charge, and every
// hardware sprite is hidden. Control then moves to the GAME OVER screen,
// which holds for a few seconds before returning to the attract menu.
endGame:
    sei                                     // Change interrupt hardware with IRQs held off.
    lda IRQ_ENABLE
    and #%11111110                          // Clear the VIC raster-interrupt enable bit.
    sta IRQ_ENABLE
    lda #%00000001
    sta IRQ_STATUS                          // Acknowledge any raster interrupt still latched.
    lda #<$ea31                             // Point the KERNAL IRQ vector back at its default handler so a
    sta IRQ_VECTOR                          // stray interrupt can no longer reach multiplexIRQ.
    lda #>$ea31
    sta IRQ_VECTOR + 1
    cli

    lda #0
    sta SPRITE_ENABLE                       // Hide every hardware sprite.
    sta SPRITE_OVERFLOW_REGISTER            // Clear the 9th-bit sprite-X register too.

    lda #GAME_STATE_GAME_OVER
    sta GAME_STATE
    lda #GAME_OVER_HOLD_FRAMES
    sta GAME_OVER_TIMER
    jsr enterGameOver                       // Clear screen, repaint stars, stamp "GAME OVER".
    rts

// --- Routine: enterGameOver -------------------------------------------
// One-time setup for the GAME OVER screen.
enterGameOver:
    lda #147
    jsr $ffd2                               // Wipe the game HUD / playfield.
    jsr drawStarfield                       // Keep the starfield running underneath.
    jsr drawGameOverText
    rts

// --- Routine: gameOverScreen -----------------------------------------
// PLAIN ENGLISH: after your last ship is gone, "GAME OVER" sits on screen
// over the drifting stars for a few seconds. Then, if the score beat the
// bottom of the high-score table, the initials-entry screen appears;
// otherwise the attract menu returns.
gameOverScreen:
    jsr waitForFrameStart
    jsr updateStarfield
    jsr drawGameOverText                    // Re-stamp every frame so stars pass behind it.

    dec GAME_OVER_TIMER
    bne !hold+

    jsr scoreQualifies                     // Carry set => this run makes the table.
    bcc !toMenu+
    lda #GAME_STATE_ENTER_INITIALS
    sta GAME_STATE
    jsr enterInitials
    rts
!toMenu:
    lda #GAME_STATE_MENU
    sta GAME_STATE
    jsr enterMenu
    rts
!hold:
    jmp gameOverScreen

// --- Routine: scoreQualifies ---------------------------------------
// Compare the just-finished SCORE (still in SCORE_LO/HI) against the
// descending high-score table. Exit: carry set and NEW_SCORE_RANK = the
// sorted insertion index if SCORE beats some entry; carry clear otherwise.
scoreQualifies:
    ldx #0
!scan:
    lda SCORE_HI
    cmp HISCORE_HI,x
    bcc !next+                              // SCORE high byte smaller -> SCORE < entry here.
    bne !here+                              // SCORE high byte larger  -> SCORE > entry here.
    lda SCORE_LO                            // High bytes equal: decide on the low byte.
    cmp HISCORE_LO,x
    bcc !next+
    beq !next+                             // Equal score does not displace an existing entry.
!here:
    stx NEW_SCORE_RANK
    sec
    rts
!next:
    inx
    cpx #HISCORE_COUNT
    bne !scan-
    clc                                    // Not greater than any entry, including the lowest.
    rts

// --- Routine: enterInitials --------------------------------------
// One-time setup for the initials-entry screen.
enterInitials:
    lda #147
    jsr $ffd2
    jsr drawStarfield

    lda #1                                  // Start every slot on "A".
    sta INITIALS_CHARS + 0
    sta INITIALS_CHARS + 1
    sta INITIALS_CHARS + 2
    lda #0
    sta INITIALS_SLOT                       // Leftmost slot selected.
    lda STICK_2
    sta INITIALS_STICK_PREV                 // Seed edge detection with the current stick state.

    jsr waitFireRelease                     // Ignore any fire still held from the GAME OVER screen.
    jsr drawInitialsScreen
    rts

// --- Routine: enterInitialsScreen ---------------------------------
// PLAIN ENGLISH: "ENTER YOUR INITIALS" with three letters below it. Push the
// stick up/down to change the highlighted letter, left/right to pick which
// letter you are changing, and press fire when all three are right. Your
// score is then slotted into the table and the high-score page is shown.
// Each stick direction only acts once per push (edge-triggered), so holding
// a direction does not race through the alphabet.
enterInitialsScreen:
    jsr waitForFrameStart
    jsr updateStarfield
    jsr drawInitialsScreen

    lda STICK_2                             // Edge-detect: bit becomes 1 only on a fresh press.
    sta INITIALS_STICK_CUR
    eor #$ff                                // ~current (bit set = pressed now).
    and INITIALS_STICK_PREV                 // AND was-released-last-frame.
    sta INITIALS_EDGE
    lda INITIALS_STICK_CUR
    sta INITIALS_STICK_PREV

    lda INITIALS_EDGE
    and #%00000001
    bne !up+
    lda INITIALS_EDGE
    and #%00000010
    bne !down+
    lda INITIALS_EDGE
    and #%00000100
    bne !left+
    lda INITIALS_EDGE
    and #%00001000
    bne !right+
    lda INITIALS_EDGE
    and #%00010000
    bne !commit+
    jmp enterInitialsScreen

!up:
    ldx INITIALS_SLOT                       // Next letter, wrapping Z -> A.
    lda INITIALS_CHARS,x
    cmp #26
    bcc !bumpUp+
    lda #0
!bumpUp:
    clc
    adc #1
    sta INITIALS_CHARS,x
    jmp enterInitialsScreen

!down:
    ldx INITIALS_SLOT                       // Previous letter, wrapping A -> Z.
    lda INITIALS_CHARS,x
    cmp #2
    bcs !bumpDown+
    lda #27
!bumpDown:
    sec
    sbc #1
    sta INITIALS_CHARS,x
    jmp enterInitialsScreen

!left:
    lda INITIALS_SLOT
    beq !nav+
    dec INITIALS_SLOT
!nav:
    jmp enterInitialsScreen

!right:
    lda INITIALS_SLOT
    cmp #2
    bcs !nav-
    inc INITIALS_SLOT
    jmp enterInitialsScreen

!commit:
    jsr insertHiscore                       // Slot SCORE + these initials into the table.

    lda #147                                // Show the updated high-score page straight away.
    jsr $ffd2
    jsr drawStarfield
    lda #ATTRACT_PAGE_SCORES
    sta ATTRACT_PAGE
    lda #ATTRACT_CYCLE_FRAMES
    sta ATTRACT_TIMER
    jsr drawHiscorePage

    lda #GAME_STATE_MENU
    sta GAME_STATE
    jsr waitFireRelease                     // Don't let the commit press also start a new game.
    rts

// --- Routine: drawInitialsScreen --------------------------------
// Prompt on row 10, the three current letters on row 14 (cols 18/20/22).
// The selected slot is drawn yellow, the others white.
drawInitialsScreen:
    lda #<initialsPrompt
    sta TEXT_SRC
    lda #>initialsPrompt
    sta TEXT_SRC + 1
    lda #<INITIALS_PROMPT_SCREEN
    sta TEXT_DST
    lda #>INITIALS_PROMPT_SCREEN
    sta TEXT_DST + 1
    ldx #19                                 // "ENTER YOUR INITIALS".
    lda #1
    jsr drawTextRow

    ldx #0                                  // X = slot 0..2 (also survives the stores below).
!slotLoop:
    txa
    asl                                    // slot * 2 (letters are two columns apart).
    clc
    adc #<INITIALS_SLOTS_SCREEN
    sta initLetterScreen + 1
    sta initLetterColour + 1
    lda #>INITIALS_SLOTS_SCREEN
    adc #0
    sta initLetterScreen + 2
    clc
    adc #$d4                                // Matching colour-RAM page.
    sta initLetterColour + 2

    lda #1                                  // White unless this is the selected slot.
    cpx INITIALS_SLOT
    bne !haveColour+
    lda #7                                  // Yellow highlight.
!haveColour:
    sta initLetterColourVal + 1

    lda INITIALS_CHARS,x
initLetterScreen:
    sta $ffff
initLetterColourVal:
    lda #0
initLetterColour:
    sta $ffff

    inx
    cpx #3
    bne !slotLoop-
    rts

// --- Routine: insertHiscore ------------------------------------
// Insert SCORE + INITIALS_CHARS at NEW_SCORE_RANK, shifting the lower
// entries (and their names) down one slot and dropping the last. Then
// rebuild the pre-rendered attract-page rows.
insertHiscore:
    ldx #HISCORE_COUNT - 1                  // Shift scores down from the bottom to the insert point.
!scoreShift:
    cpx NEW_SCORE_RANK
    beq !scoreShifted+
    lda HISCORE_LO - 1,x
    sta HISCORE_LO,x
    lda HISCORE_HI - 1,x
    sta HISCORE_HI,x
    dex
    jmp !scoreShift-
!scoreShifted:
    ldx NEW_SCORE_RANK
    lda SCORE_LO
    sta HISCORE_LO,x
    lda SCORE_HI
    sta HISCORE_HI,x

    lda NEW_SCORE_RANK                      // rank * 3 = first name byte for this entry.
    asl
    clc
    adc NEW_SCORE_RANK
    sta NAME_RANK_OFF
    clc
    adc #3                                  // Lowest destination byte a shift may fill.
    sta NAME_STOP_OFF

    ldx #HISCORE_COUNT * 3 - 1              // Shift 3-byte name blocks down.
!nameShift:
    cpx NAME_STOP_OFF
    bcc !nameShifted+
    lda HISCORE_NAME - 3,x
    sta HISCORE_NAME,x
    dex
    jmp !nameShift-
!nameShifted:
    ldx NAME_RANK_OFF                       // Write the three new initials.
    ldy #0
!nameWrite:
    lda INITIALS_CHARS,y
    sta HISCORE_NAME,x
    inx
    iny
    cpy #3
    bne !nameWrite-

    jsr formatHiscorePage
    rts


// --- Routine: drawGameOverText -------------------------------------
// Stamp "GAME OVER" centred on row 12.
drawGameOverText:
    lda #<gameOverLabel
    sta TEXT_SRC
    lda #>gameOverLabel
    sta TEXT_SRC + 1
    lda #<GAME_OVER_SCREEN
    sta TEXT_DST
    lda #>GAME_OVER_SCREEN
    sta TEXT_DST + 1
    ldx #9                                  // "GAME OVER".
    lda #2                                  // Red.
    jsr drawTextRow
    rts

// --- Routine: enterMenu -----------------------------------------------
// One-time setup when the attract screen becomes active: clear the screen,
// repaint the starfield, and start on the title page.
enterMenu:
    lda #147
    jsr $ffd2                               // Clear screen RAM (also wipes any game HUD / GAME OVER text).
    jsr drawStarfield                       // Repaint the stars over the cleared screen.

    lda #ATTRACT_PAGE_TITLE                 // Always come back to the title first.
    sta ATTRACT_PAGE
    lda #ATTRACT_CYCLE_FRAMES
    sta ATTRACT_TIMER
    jsr drawTitlePage                       // Draw the first frame's text immediately.
    rts

// --- Routine: attractMenu -----------------------------------------------
// PLAIN ENGLISH: the attract screen. It flips every few seconds between the
// title page and the high-score table. Stars drift past and the text stays
// put on top of them. Press fire on either page and a fresh game begins.
attractMenu:
    jsr waitForFrameStart
    jsr updateStarfield

    lda ATTRACT_PAGE                        // Re-stamp the current page's text every frame, right after
    bne !scoresPage+                        // the stars move, so a vacated text cell never shows a gap.
    jsr drawTitlePage
    jmp !pageDrawn+
!scoresPage:
    jsr drawHiscorePage
!pageDrawn:

    dec ATTRACT_TIMER                       // Time to flip to the other page?
    bne !checkFire+
    lda #ATTRACT_CYCLE_FRAMES
    sta ATTRACT_TIMER
    lda ATTRACT_PAGE
    eor #1                                  // Toggle title <-> scores.
    sta ATTRACT_PAGE
    lda #147                                // Wipe the outgoing page's text, then repaint the stars.
    jsr $ffd2
    jsr drawStarfield

!checkFire:
    lda STICK_2                             // Joystick port 2, fire is active-low bit 4.
    and #%00010000
    bne !noFire+
    jsr waitFireRelease                     // Don't let this same press also fire on game frame 1.
    jsr startGame                           // Build the first game frame and switch state to PLAYING.
    rts                                     // Back to the router, which will now call gameLoop.
!noFire:
    jmp attractMenu

// --- Routine: drawTitlePage -----------------------------------------
// Stamp the title and the "FIRE TO START" prompt over the starfield. Called
// every attract frame immediately after updateStarfield.
drawTitlePage:
    lda #<titleLine
    sta TEXT_SRC
    lda #>titleLine
    sta TEXT_SRC + 1
    lda #<MENU_TITLE_SCREEN
    sta TEXT_DST
    lda #>MENU_TITLE_SCREEN
    sta TEXT_DST + 1
    ldx #20                                 // "MY FIRST C64 SHOOTER".
    lda #14                                 // Light blue.
    jsr drawTextRow

    lda #<fireToStartLine
    sta TEXT_SRC
    lda #>fireToStartLine
    sta TEXT_SRC + 1
    lda #<MENU_PROMPT_SCREEN
    sta TEXT_DST
    lda #>MENU_PROMPT_SCREEN
    sta TEXT_DST + 1
    ldx #13                                 // "FIRE TO START".
    lda #1                                  // White.
    jsr drawTextRow
    rts

// --- Routine: drawTextRow -----------------------------------------------
// Blit one row of screen codes plus a flat colour into screen + colour RAM.
// Entry: TEXT_SRC -> screen-code bytes, TEXT_DST -> screen RAM address,
//        X = length (1..255), A = colour.
// Colour RAM is always the screen page + $d400 ($0400 -> $d800).
drawTextRow:
    sta drawTextRowColourVal + 1            // Patch the per-cell colour immediate.
    stx drawTextRowLen + 1                  // Patch the loop terminator.
    lda TEXT_DST                            // Low byte is shared by the screen and colour stores.
    sta drawTextRowScreen + 1
    sta drawTextRowColour + 1
    lda TEXT_DST + 1
    sta drawTextRowScreen + 2
    clc
    adc #$d4                                // Screen page -> colour-RAM page.
    sta drawTextRowColour + 2

    ldy #0
!loop:
    lda (TEXT_SRC),y                        // Next screen code from the source string.
drawTextRowScreen:
    sta $ffff,y                             // -> screen RAM (address patched above).
drawTextRowColourVal:
    lda #0                                  // Immediate patched from A on entry.
drawTextRowColour:
    sta $ffff,y                             // -> colour RAM (address patched above).
    iny
drawTextRowLen:
    cpy #0                                  // Immediate patched from X on entry.
    bne !loop-
    rts

// --- Routine: waitFireRelease ---------------------------------------------
// Block until joystick-2 fire is released so one physical press cannot be
// consumed by two states across a transition.
waitFireRelease:
!wait:
    jsr waitForFrameStart                   // Sample once per frame.
    lda STICK_2
    and #%00010000                          // Bit set = fire released.
    beq !wait-
    rts

// --- Routine: seedHiscoreTable ------------------------------------------
// Fill the high-score table with HISCORE_COUNT entries: three pseudo-random
// initials each, every score equal to HISCORE_START_SCORE. The table is
// therefore already in descending order (all equal), which the later insert
// logic relies on. Called once from init.
seedHiscoreTable:
    lda CIA1_TIMER_A_LO                     // Any changing byte is a fine seed for throwaway names.
    sta HISCORE_SEED

    ldx #0                                  // X walks HISCORE_NAME byte by byte (0..HISCORE_COUNT*3-1).
    ldy #0                                  // Y is the entry index.
!entryLoop:
    jsr nextRandomLetter                    // First initial.
    sta HISCORE_NAME,x
    inx
    jsr nextRandomLetter                    // Second initial.
    sta HISCORE_NAME,x
    inx
    jsr nextRandomLetter                    // Third initial.
    sta HISCORE_NAME,x
    inx

    lda #<HISCORE_START_SCORE
    sta HISCORE_LO,y
    lda #>HISCORE_START_SCORE
    sta HISCORE_HI,y

    iny
    cpy #HISCORE_COUNT
    bne !entryLoop-

    jsr formatHiscorePage                   // Pre-render the table text for the attract page.
    rts

// --- Routine: nextRandomLetter ----------------------------------------
// Return A = a pseudo-random screen code in 1..26 (A-Z). Cheap LCG-ish mix
// of a running seed and the free-running CIA timer; quality is irrelevant
// for placeholder names.
nextRandomLetter:
    lda HISCORE_SEED
    asl                                     // seed = seed*2 ...
    eor HISCORE_SEED                        // ... xor seed ...
    eor CIA1_TIMER_A_LO                     // ... xor a byte that changes every scanline.
    sta HISCORE_SEED

    and #%00011111                          // 0..31.
!fold:
    cmp #26
    bcc !inRange+
    sbc #26                                 // Carry is set here, so this is a plain subtract. 0..25.
!inRange:
    clc
    adc #1                                  // 1..26 = screen codes for A..Z.
    rts

// --- Routine: formatHiscorePage ---------------------------------------
// Rebuild HISCORE_PAGE_BUF: one HISCORE_ROW_WIDTH-char row per entry, laid
// out "III  DDDDD" (3 initials, 2 spaces, 5 decimal digits). Call whenever
// the table changes.
formatHiscorePage:
    ldx #0                                  // X = entry index.
!rowLoop:
    stx HS_ENTRY

    txa                                     // Buffer offset for this row = entry * HISCORE_ROW_WIDTH (10).
    asl                                     // *2
    sta HS_TMP
    asl                                     // *4
    asl                                     // *8
    clc
    adc HS_TMP                              // *8 + *2 = *10
    sta HS_BUF_OFF

    txa                                     // Name offset = entry * 3.
    asl
    clc
    adc HS_ENTRY
    tay                                     // Y -> HISCORE_NAME for this entry.

    ldx HS_BUF_OFF
    lda HISCORE_NAME,y                      // Three initials.
    sta HISCORE_PAGE_BUF,x
    lda HISCORE_NAME + 1,y
    sta HISCORE_PAGE_BUF + 1,x
    lda HISCORE_NAME + 2,y
    sta HISCORE_PAGE_BUF + 2,x
    lda #32                                 // Two spaces between initials and score.
    sta HISCORE_PAGE_BUF + 3,x
    sta HISCORE_PAGE_BUF + 4,x

    ldy HS_ENTRY                            // Copy this entry's score into the conversion scratch.
    lda HISCORE_LO,y
    sta HS_VAL_LO
    lda HISCORE_HI,y
    sta HS_VAL_HI

    lda HS_BUF_OFF                          // Digits start five characters into the row.
    clc
    adc #5
    tay
    jsr formatScore5                       // Writes 5 screen codes at HISCORE_PAGE_BUF + Y.

    ldx HS_ENTRY
    inx
    cpx #HISCORE_COUNT
    bne !rowLoop-
    rts

// --- Routine: formatScore5 ------------------------------------------
// Convert HS_VAL_LO/HI (destroyed) to exactly five decimal screen codes,
// written to HISCORE_PAGE_BUF + Y .. +Y+4. Shares the decimal divisor table
// with the FREE-cycle / score HUD converters.
formatScore5:
    sty HS_DIGIT_BASE
    ldx #0                                  // X = decimal place: 0=10000s .. 4=1s.
!placeLoop:
    ldy #0                                  // Y counts how many times this divisor fits.
!subLoop:
    lda HS_VAL_HI
    cmp debugDivisorHi,x
    bcc !emit+
    bne !doSub+
    lda HS_VAL_LO
    cmp debugDivisorLo,x
    bcc !emit+
!doSub:
    lda HS_VAL_LO
    sec
    sbc debugDivisorLo,x
    sta HS_VAL_LO
    lda HS_VAL_HI
    sbc debugDivisorHi,x
    sta HS_VAL_HI
    iny
    bne !subLoop-
!emit:
    tya
    clc
    adc #48                                 // Screen codes 48-57 are digits 0-9.
    pha
    txa
    clc
    adc HS_DIGIT_BASE                       // Destination index = base + decimal place.
    tay
    pla
    sta HISCORE_PAGE_BUF,y
    inx
    cpx #5
    bne !placeLoop-
    rts

// --- Routine: drawHiscorePage ---------------------------------------
// Stamp the "HIGH SCORES" heading and every pre-rendered table row over the
// starfield. Called every attract frame while the scores page is showing.
drawHiscorePage:
    lda #<hiscoreHeading
    sta TEXT_SRC
    lda #>hiscoreHeading
    sta TEXT_SRC + 1
    lda #<HISCORE_HEADING_SCREEN
    sta TEXT_DST
    lda #>HISCORE_HEADING_SCREEN
    sta TEXT_DST + 1
    ldx #11                                 // "HIGH SCORES".
    lda #7                                  // Yellow heading.
    jsr drawTextRow

    ldx #0                                  // X = entry index.
!rowLoop:
    stx HS_ENTRY

    txa                                     // Row source = HISCORE_PAGE_BUF + entry * HISCORE_ROW_WIDTH.
    asl
    sta HS_TMP
    asl
    asl
    clc
    adc HS_TMP                              // entry * 10
    clc
    adc #<HISCORE_PAGE_BUF
    sta TEXT_SRC
    lda #>HISCORE_PAGE_BUF
    adc #0
    sta TEXT_SRC + 1

    ldx HS_ENTRY                            // Row destination address from the precomputed table.
    lda hiscoreRowLo,x
    sta TEXT_DST
    lda hiscoreRowHi,x
    sta TEXT_DST + 1

    ldx #HISCORE_ROW_WIDTH
    lda #1                                  // White rows.
    jsr drawTextRow

    ldx HS_ENTRY
    inx
    cpx #HISCORE_COUNT
    bne !rowLoop-
    rts

// Screen addresses for the eight table rows: rows 7,9,11,...,21, column 15.
hiscoreRowLo:
    .fill HISCORE_COUNT, <($0400 + (7 + i * 2) * 40 + 15)
hiscoreRowHi:
    .fill HISCORE_COUNT, >($0400 + (7 + i * 2) * 40 + 15)

.encoding "screencode_upper"
titleLine:
    .text "MY FIRST C64 SHOOTER"            // 20 screen codes; keep drawTitlePage's ldx in step.
fireToStartLine:
    .text "FIRE TO START"                   // 13 screen codes.
hiscoreHeading:
    .text "HIGH SCORES"                     // 11 screen codes.
initialsPrompt:
    .text "ENTER YOUR INITIALS"             // 19 screen codes.
.encoding "petscii_upper"

// --- Routine: setupStarfieldCharset ---------------------------------------
// Copy the standard upper-case/graphics character ROM to $3800, then replace
// chars 240-251 with animated star glyphs.
setupStarfieldCharset:
    sei                                     // Keep IRQs out while VIC I/O is banked away.
    lda $01
    pha
    and #%11111011                          // CHAREN=0 exposes character ROM at $d000.
    sta $01

    ldx #0
!copyCharset:
    lda $d000,x
    sta STAR_CHARSET + $000,x
    lda $d100,x
    sta STAR_CHARSET + $100,x
    lda $d200,x
    sta STAR_CHARSET + $200,x
    lda $d300,x
    sta STAR_CHARSET + $300,x
    lda $d400,x
    sta STAR_CHARSET + $400,x
    lda $d500,x
    sta STAR_CHARSET + $500,x
    lda $d600,x
    sta STAR_CHARSET + $600,x
    lda $d700,x
    sta STAR_CHARSET + $700,x
    inx
    bne !copyCharset-

    pla
    sta $01                                 // Restore normal I/O mapping.
    cli

    ldx #0
!copyStarGlyphs:
    lda starGlyphData,x
    sta STAR_CHARSET + (STAR_CHAR_BASE * 8),x
    inx
    cpx #STAR_GLYPH_BYTES
    bne !copyStarGlyphs-
    rts

// --- Routine: setupStarfield ------------------------------------------------
setupStarfield:
    lda #0
    sta STAR_FRAME

    ldx #0
!phaseLoop:
    txa                                     // Stagger initial sub-cell phases.
    and #%00000011
    sta STAR_PHASE,x
    inx
    cpx #STAR_COUNT
    bne !phaseLoop-

    jsr drawStarfield
    rts

// --- Routine: updateStarfield ----------------------------------------------
// Optimised version: each star is only erased/redrawn when it actually moves.
// Far stars therefore cost almost nothing on three frames out of four, medium
// stars on alternate frames, while near stars retain full-speed movement.
updateStarfield:
    inc STAR_FRAME

    ldx #0
!updateLoop:
    lda STAR_STYLE,x
    and #%00000001                          // 0=far, 1=middle. Near/large layer removed.
    beq !small+
    jmp !medium+

!small:
    lda STAR_FRAME                          // Far stars move every fourth frame.
    and #%00000011
    bne !twinkleOnly+
    jmp !moveStar+

!medium:
    lda STAR_FRAME                          // Middle stars move every second frame.
    and #%00000001
    bne !twinkleOnly+

!moveStar:
    jsr eraseOneStar                        // Remove only this star's old character cell.

    inc STAR_PHASE,x                        // Advance by two pixels inside its current character cell.
    lda STAR_PHASE,x
    cmp #4
    bcc !redraw+

    lda #0
    sta STAR_PHASE,x
    inc STAR_Y,x                            // Four phases completed: enter the next character row.
    lda STAR_Y,x
    cmp #25
    bcc !redraw+

    lda #1                                  // Wrap below row 0 HUD.
    sta STAR_Y,x

    lda CIA1_TIMER_A_LO                     // Vary X at wrap to break obvious vertical lanes.
    eor STAR_FRAME
    clc
    adc STAR_STYLE,x
    and #%00111111
    cmp #40
    bcc !storeX+
    sbc #40
!storeX:
    sta STAR_X,x

!redraw:
    jsr drawOneStar                         // Draw only the star that changed.
    jmp !next+

!twinkleOnly:
    lda STAR_STYLE,x
    bpl !next+                              // Non-twinkling stationary stars need no work at all.

    txa
    clc
    adc STAR_FRAME
    and #%00011111
    beq !twinkleOn+

    cmp #1                                  // One frame after sparkle, restore normal colour.
    bne !next+
    jsr setOneStarNormalColour
    jmp !next+

!twinkleOn:
    jsr setOneStarTwinkleColour

!next:
    inx
    cpx #STAR_COUNT
    beq !done+
    jmp !updateLoop-
!done:
    rts

// --- Routine: eraseOneStar --------------------------------------------------
// X = logical star index. Erase just that star's current screen cell.
eraseOneStar:
    ldy STAR_Y,x
    lda starRowLo,y
    clc
    adc STAR_X,x
    sta starEraseStore + 1
    lda starRowHi,y
    adc #0
    sta starEraseStore + 2

    lda #32                                 // Screen code for space.
starEraseStore:
    sta $ffff
    rts

// --- Routine: drawOneStar ---------------------------------------------------
// X = logical star index. Draw its current glyph and normal/twinkle colour.
drawOneStar:
    ldy STAR_Y,x
    lda starRowLo,y
    clc
    adc STAR_X,x
    sta starDrawScreen + 1
    sta starDrawColour + 1

    lda starRowHi,y
    adc #0
    sta starDrawScreen + 2
    clc
    adc #$d4                                // Matching colour RAM page.
    sta starDrawColour + 2

    lda STAR_STYLE,x
    and #%00000011
    tay
    lda starBaseColour,y
    sta STAR_DRAW_COLOUR

    tya
    asl
    asl                                     // Four glyph phases per size.
    clc
    adc STAR_PHASE,x
    adc #STAR_CHAR_BASE
starDrawScreen:
    sta $ffff

    lda STAR_STYLE,x
    bpl !normalColour+
    txa
    clc
    adc STAR_FRAME
    and #%00011111
    bne !normalColour+
    lda #7                                  // Brief yellow-white sparkle.
    sta STAR_DRAW_COLOUR

!normalColour:
    lda STAR_DRAW_COLOUR
starDrawColour:
    sta $ffff
    rts

// --- Routine: drawStarfield -------------------------------------------------
// Used only during setup: render every star once.
drawStarfield:
    ldx #0
!drawLoop:
    jsr drawOneStar
    inx
    cpx #STAR_COUNT
    bne !drawLoop-
    rts

// --- Routine: setOneStarTwinkleColour --------------------------------------
// X = logical star index. Change colour RAM only; glyph/screen RAM is untouched.
setOneStarTwinkleColour:
    ldy STAR_Y,x
    lda starRowLo,y
    clc
    adc STAR_X,x
    sta starTwinkleStore + 1
    lda starRowHi,y
    adc #0
    clc
    adc #$d4
    sta starTwinkleStore + 2

    lda #7
starTwinkleStore:
    sta $ffff
    rts

// --- Routine: setOneStarNormalColour ---------------------------------------
// X = logical star index. Restore the colour appropriate to this depth layer.
setOneStarNormalColour:
    ldy STAR_Y,x
    lda starRowLo,y
    clc
    adc STAR_X,x
    sta starNormalColourStore + 1
    lda starRowHi,y
    adc #0
    clc
    adc #$d4
    sta starNormalColourStore + 2

    lda STAR_STYLE,x
    and #%00000011
    tay
    lda starBaseColour,y
starNormalColourStore:
    sta $ffff
    rts

// Three sizes, each with four vertical phases spaced two pixels apart.
starGlyphData:
    // Small/far.
    .byte $10,$00,$00,$00,$00,$00,$00,$00
    .byte $00,$00,$10,$00,$00,$00,$00,$00
    .byte $00,$00,$00,$00,$10,$00,$00,$00
    .byte $00,$00,$00,$00,$00,$00,$10,$00

    // Medium.
    .byte $18,$18,$00,$00,$00,$00,$00,$00
    .byte $00,$00,$18,$18,$00,$00,$00,$00
    .byte $00,$00,$00,$00,$18,$18,$00,$00
    .byte $00,$00,$00,$00,$00,$00,$18,$18

    // Large/near.
    .byte $38,$10,$00,$00,$00,$00,$00,$00
    .byte $00,$00,$38,$10,$00,$00,$00,$00
    .byte $00,$00,$00,$00,$38,$10,$00,$00
    .byte $00,$00,$00,$00,$00,$00,$38,$10

starBaseColour:
    .byte 12,15,1                           // Grey far, light-grey middle; white near entry retained but unused.

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
    bne !bullet+                            // Other active object types have their own movement rules.
    lda OBJECT_DEATH_TIMER,x                // A dying enemy remains renderable but no longer follows its path.
    bne !next+
    jsr moveEnemyPath
    jmp !next+

!bullet:
    cmp #TYPE_ENEMY_BULLET                  // Hostile projectile objects use their stored fixed launch vector.
    bne !next+
    jsr moveEnemyBullet
!next:
    inx                                     // Increment X by one.
    cpx #MAX_OBJECTS                        // Compare X with #MAX_OBJECTS; set flags, leaving X unchanged.
    bne !objectLoop-                        // Branch to !objectLoop- if the previous result was non-zero/not equal.
    rts                                     // Return to the calling routine.

// --- Routine: updatePlayer --------------------------------------------------
// Read joystick port 2 once and move object X within the playfield bounds.
updatePlayer:
    lda PLAYER_STATE                        // Explosion freezes the ship; respawn invulnerability still permits movement.
    cmp #PLAYER_STATE_EXPLODING
    bne !readJoystick+
    rts

!readJoystick:
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
    jsr updatePlayerFire
    ldx #0                                  // updatePlayer belongs to reserved object 0; restore object-loop index.
    rts

// --- Routine: updatePlayerFire ---------------------------------------------
// Hold joystick fire to emit a dual-cannon hitscan volley whenever cooldown is
// zero. Each cannon resolves independently, so alignment can deal 0, 1 or 2 HP.
updatePlayerFire:
    lda PLAYER_STATE                        // Keep the recovery window about movement/survival for this first pass.
    cmp #PLAYER_STATE_ALIVE
    beq !stateOkay+
    rts

!stateOkay:
    lda PLAYER_FIRE_COOLDOWN_TIMER          // A previous volley still owns the fire cadence.
    beq !checkButton+
    rts

!checkButton:
    lda JOY_STATE                           // Joystick port 2 fire is active-low bit 4.
    and #%00010000
    beq !fire+
    rts

!fire:
    lda #PLAYER_FIRE_COOLDOWN               // Arm cadence before resolving either cannon.
    sta PLAYER_FIRE_COOLDOWN_TIMER
    lda #PLAYER_MUZZLE_TIME                 // Hold the firing bitmap for a few frames.
    sta PLAYER_MUZZLE_TIMER
    lda #playerFireSprite / 64
    sta OBJECT_SPRITE                       // Object 0 remains the player; only its presentation changes.

    lda OBJECT_X                            // Build the left-cannon 9-bit world X coordinate.
    clc
    adc #PLAYER_LEFT_CANNON_X
    sta HITSCAN_X_LO
    lda OBJECT_X_MSB
    adc #0
    sta HITSCAN_X_MSB
    jsr tracePlayerCannon                   // X = nearest intersected enemy when carry is clear.
    bcs !rightCannon+
    jsr hitEnemyFromLeft                    // Left-side impact kicks the enemy slightly right/down.

!rightCannon:
    lda OBJECT_X                            // Build the right-cannon 9-bit world X coordinate.
    clc
    adc #PLAYER_RIGHT_CANNON_X
    sta HITSCAN_X_LO
    lda OBJECT_X_MSB
    adc #0
    sta HITSCAN_X_MSB
    jsr tracePlayerCannon
    bcs !done+
    jsr hitEnemyFromRight                   // Right-side impact kicks the enemy slightly left/down.

!done:
    rts

// --- Routine: tracePlayerCannon --------------------------------------------
// Find the nearest active enemy above the player whose 24-pixel sprite width
// intersects HITSCAN_X. Returns X = logical enemy index and C clear on hit.
tracePlayerCannon:
    lda #$ff
    sta HITSCAN_TARGET                      // $ff means no target has intersected this ray yet.
    lda #0
    sta HITSCAN_TARGET_Y                    // Greatest qualifying Y wins: nearest enemy above player.

    ldx #1                                  // Slot 0 is permanently the player.
!scan:
    lda OBJECT_ACTIVE,x
    beq !next+
    lda OBJECT_TYPE,x
    cmp #TYPE_ENEMY
    bne !next+

    lda OBJECT_Y,x                          // Hitscan only travels upward from the player's current position.
    cmp OBJECT_Y
    bcs !next+

    lda HITSCAN_X_LO                        // Compute rayX - enemyX as a 9-bit subtraction.
    sec
    sbc OBJECT_X,x
    sta HITSCAN_DELTA_LO
    lda HITSCAN_X_MSB
    sbc OBJECT_X_MSB,x
    bne !next+                              // Negative or >=256 cannot lie within a 24-pixel sprite width.

    lda HITSCAN_DELTA_LO
    cmp #24
    bcs !next+                              // Valid horizontal intersection is enemyX .. enemyX+23.

    lda OBJECT_Y,x
    cmp HITSCAN_TARGET_Y
    bcc !next+                              // Smaller Y is farther away; keep the nearer target.
    sta HITSCAN_TARGET_Y
    stx HITSCAN_TARGET

!next:
    inx
    cpx #MAX_OBJECTS
    bne !scan-

    ldx HITSCAN_TARGET
    cpx #$ff
    beq !miss+
    clc
    rts

!miss:
    sec
    rts

// --- Routine: hitEnemyFromLeft ---------------------------------------------
// Apply one HP of ballistic damage from the left cannon.
hitEnemyFromLeft:
    jsr damageEnemy
    rts

// --- Routine: hitEnemyFromRight --------------------------------------------
// Apply one HP of ballistic damage from the right cannon.
hitEnemyFromRight:
    jsr damageEnemy
    rts

// --- Routine: damageEnemy ---------------------------------------------------
// X = logical enemy. A hit removes one HP; reaching zero starts a short death
// state. OBJECT_ACTIVE remains set until the animation finishes, preserving the
// normal renderer/allocator ownership rules.
damageEnemy:
    lda OBJECT_HEALTH,x
    beq !done+                              // Already dead/dying: never underflow health.
    dec OBJECT_HEALTH,x
    beq !beginDeath+                        // Final HP consumed: switch immediately to death presentation.

    jsr updateEnemyHealthSprite             // Reveal/update this enemy's private in-sprite health bar.
    lda #ENEMY_HIT_FLASH_TIME
    sta OBJECT_HIT_TIMER,x
    lda #1                                  // VIC colour 1 = white initial ballistic impact flash.
    sta OBJECT_COLOUR,x
!done:
    rts

!beginDeath:
    lda #0
    sta OBJECT_HIT_TIMER,x                  // Death animation now owns sprite colour/presentation.

    lda #ENEMY_DEATH_TIME
    sta OBJECT_DEATH_TIMER,x                // Keep the logical slot active until the animation completes.
    lda #playerExplosion1 / 64              // Reuse existing explosion art for the first functional death pass.
    sta OBJECT_SPRITE,x
    lda #7                                  // Yellow initial blast.
    sta OBJECT_COLOUR,x
    rts

// --- Routine: updateEnemyHealthSprite --------------------------------------
// X = logical enemy. Copy its original 64-byte bitmap into a private sprite slot
// and overwrite the two blank bottom rows with a six-segment health bar.
// Each HP is two multicolour pixels wide; no extra VIC sprite is consumed.
updateEnemyHealthSprite:
    stx HEALTH_OBJECT_INDEX                 // Preserve caller's logical enemy index.

    lda OBJECT_BASE_SPRITE,x                // Convert source sprite pointer back into a bank-0 RAM address.
    sta HEALTH_SOURCE_SPRITE
    and #%00000011                          // Pointer bits 0-1 become address bits 6-7.
    asl
    asl
    asl
    asl
    asl
    asl
    sta healthCopySource + 1                // Patch low byte of LDA absolute,Y source operand.
    lda HEALTH_SOURCE_SPRITE
    lsr
    lsr                                     // Pointer / 4 is the source address high byte.
    sta healthCopySource + 2                // Patch high byte of LDA absolute,Y source operand.

    txa
    clc
    adc #HEALTH_SPRITE_BASE_PTR             // Give this logical slot its own 64-byte sprite bitmap.
    sta HEALTH_DEST_SPRITE
    sta OBJECT_SPRITE,x                     // Renderer now uses the private health-bar copy.
    and #%00000011
    asl
    asl
    asl
    asl
    asl
    asl
    sta healthCopyDest + 1                  // Patch low byte of STA absolute,Y destination operand.
    lda HEALTH_DEST_SPRITE
    lsr
    lsr
    sta healthCopyDest + 2                  // Patch high byte of STA absolute,Y destination operand.
    sta healthBarStore + 2                  // Health-bar writes target the same private sprite.
    lda healthCopyDest + 1
    sta healthBarStore + 1

    ldy #0                                  // Clone all 64 bytes of the formation's original sprite art.
!copyLoop:
healthCopySource:
    lda $ffff,y                             // Self-modified source address.
healthCopyDest:
    sta $ffff,y                             // Self-modified private destination address.
    iny
    cpy #64
    bne !copyLoop-

    ldx HEALTH_OBJECT_INDEX                 // Recover logical enemy to read its remaining HP.
    lda OBJECT_HEALTH,x
    tax                                     // X = 1..5 after a normal non-lethal hit.

    lda healthBarByte0,x                    // Left third of the six-segment bar.
    ldy #0                                  // Sprite row 0, byte 0.
    jsr storeHealthBarByte
    ldy #3                                  // Duplicate on row 1 for a two-pixel-high bar.
    jsr storeHealthBarByte

    lda healthBarByte1,x                    // Middle third.
    ldy #1
    jsr storeHealthBarByte
    ldy #4
    jsr storeHealthBarByte

    lda healthBarByte2,x                    // Right third.
    ldy #2
    jsr storeHealthBarByte
    ldy #5
    jsr storeHealthBarByte

    ldx HEALTH_OBJECT_INDEX                 // Preserve damageEnemy's register contract.
    rts

// --- Routine: storeHealthBarByte -------------------------------------------
// A = bar byte, Y = byte offset inside the already-patched private sprite.
// Reuse the destination operand patched by updateEnemyHealthSprite.
storeHealthBarByte:
healthBarStore:
    sta $ffff,y                             // Self-modified private sprite destination.
    rts

// Six HP occupy six equal two-multicolour-pixel chunks across the 24-pixel sprite.
// Value %11 uses the sprite's individual VIC colour; zero remains transparent.
// Index 0 is retained for completeness although zero HP immediately explodes.
healthBarByte0:
    .byte $00,$f0,$ff,$ff,$ff,$ff,$ff
healthBarByte1:
    .byte $00,$00,$00,$f0,$ff,$ff,$ff
healthBarByte2:
    .byte $00,$00,$00,$00,$00,$f0,$ff
healthBarByteEnd:

// --- Compile-time bounds guard: enemy health-bar segment tables ----------
// updateEnemyHealthSprite indexes healthBarByte0/1/2 by an enemy's remaining
// HP (1 .. ENEMY_START_HEALTH-1 on a non-lethal hit; index 0 is the unused
// dead slot).  Each row holds one byte per representable HP value, and the bar
// art itself is six segments, so the tables can show at most (row length - 1)
// HP.  If ENEMY_START_HEALTH is ever tuned past that, the indexed reads would
// silently walk into neighbouring data instead of failing loudly here.
.if (((healthBarByte2 - healthBarByte1) != (healthBarByte1 - healthBarByte0))
        || ((healthBarByteEnd - healthBarByte2) != (healthBarByte1 - healthBarByte0))) {
    .error "healthBarByte0/1/2 rows must all be the same length"
}
.if (ENEMY_START_HEALTH > (healthBarByte1 - healthBarByte0 - 1)) {
    .error "ENEMY_START_HEALTH exceeds the healthBarByte0/1/2 segment tables"
}

// --- Routine: updatePlayerCombatEffects ------------------------------------
// Decay fire cadence and restore the normal player bitmap after muzzle flash.
updatePlayerCombatEffects:
    lda PLAYER_FIRE_COOLDOWN_TIMER
    beq !muzzle+
    dec PLAYER_FIRE_COOLDOWN_TIMER

!muzzle:
    lda PLAYER_MUZZLE_TIMER
    beq !done+
    dec PLAYER_MUZZLE_TIMER
    bne !done+

    lda PLAYER_STATE                        // Explosion/respawn presentation owns OBJECT_SPRITE in other states.
    cmp #PLAYER_STATE_ALIVE
    bne !done+
    lda #playerSprite / 64
    sta OBJECT_SPRITE

!done:
    rts

// --- Routine: updateEnemyHitEffects ----------------------------------------
// Advance enemy death presentation first. Living enemies then restore their hit
// flash colour back to the formation's base colour.
updateEnemyHitEffects:
    ldx #1                                  // Logical object 0 is permanently the player.
!loop:
    lda OBJECT_ACTIVE,x
    bne !active+
    jmp !next+                              // Routine is too large to branch directly to !next.
!active:
    lda OBJECT_TYPE,x
    cmp #TYPE_ENEMY
    beq !enemy+
    jmp !next+
!enemy:

    lda OBJECT_DEATH_TIMER,x                // Non-zero means this enemy has exhausted its health.
    beq !living+
    dec OBJECT_DEATH_TIMER,x
    beq !removeEnemy+                       // Animation finished: release the logical object slot.

    lda OBJECT_DEATH_TIMER,x
    cmp #8
    bcs !deathFrame1+
    cmp #4
    bcs !deathFrame2+

!deathFrame3:
    lda #playerExplosion3 / 64
    sta OBJECT_SPRITE,x
    lda #2                                  // Red final breakup.
    sta OBJECT_COLOUR,x
    jmp !next+

!deathFrame2:
    lda #playerExplosion2 / 64
    sta OBJECT_SPRITE,x
    lda #8                                  // Orange middle blast.
    sta OBJECT_COLOUR,x
    jmp !next+

!deathFrame1:
    lda #playerExplosion1 / 64
    sta OBJECT_SPRITE,x
    lda #7                                  // Yellow initial blast.
    sta OBJECT_COLOUR,x
    jmp !next+

!removeEnemy:
    jsr awardKillScore                      // Death completed: award this enemy exactly once before releasing its slot.
    lda #0
    sta OBJECT_ACTIVE,x                     // Generic allocator can reuse this slot from the next spawn onward.
    sta OBJECT_DEATH_TIMER,x
    sta OBJECT_HIT_TIMER,x
    sta OBJECT_HEALTH,x
    jmp !next+

!living:
    lda OBJECT_HIT_TIMER,x
    beq !next+
    dec OBJECT_HIT_TIMER,x
    lda OBJECT_HIT_TIMER,x
    cmp #2
    bcs !white+
    cmp #1
    beq !yellow+

    lda OBJECT_BASE_COLOUR,x                // Timer reached zero: restore formation colour.
    sta OBJECT_COLOUR,x
    jmp !next+

!white:
    lda #1
    sta OBJECT_COLOUR,x
    jmp !next+

!yellow:
    lda #7
    sta OBJECT_COLOUR,x

!next:
    inx
    cpx #MAX_OBJECTS
    beq !done+
    jmp !loop-                              // Absolute jump avoids the 6502's ±128-byte branch limit.
!done:
    rts

// --- Routine: updateEnemyFire ----------------------------------------------
// Enemy fire is globally capped at three active bullets.  A shot is aimed once
// at the player's current X and the bottom of the screen, then follows a fixed,
// smooth integer vector; it never homes after launch.
//
// For v1, only enemies in the useful central playfield window may fire and an
// enemy already coasting out of its attack is ignored.  The CIA timer chooses
// the first logical slot inspected so the same formation member does not always
// get first refusal.
updateEnemyFire:
    lda ENEMY_FIRE_TIMER                    // Global cadence prevents every enemy firing independently.
    beq !tryFire+
    dec ENEMY_FIRE_TIMER                    // Consume one frame of the current fire delay.
    rts

!tryFire:
    lda #ENEMY_FIRE_INTERVAL                // Restart cadence even if no suitable shooter exists this frame.
    sta ENEMY_FIRE_TIMER

    lda ENEMY_BULLET_COUNT                  // Respect the hard global projectile ceiling.
    cmp #MAX_ENEMY_BULLETS
    bcs !done+

    lda CIA1_TIMER_A_LO                     // Cheap changing seed is sufficient for choosing a shooter.
    and #%00001111                          // Restrict candidate logical index to 0..15.
    bne !haveStart+
    lda #1                                  // Object 0 is permanently the player.
!haveStart:
    tax
    lda #15                                 // At most inspect every non-player logical slot once.
    sta ENEMY_FIRE_SCAN_COUNT

!scan:
    lda OBJECT_ACTIVE,x                     // Candidate must currently exist.
    beq !next+
    lda OBJECT_TYPE,x                       // Only living enemy craft may originate shots.
    cmp #TYPE_ENEMY
    bne !next+
    lda OBJECT_DEATH_TIMER,x                // Dying/exploding enemies cannot fire.
    bne !next+
    lda OBJECT_STAGE,x                      // Egress fragments (shaped or plain coast) never fire.
    cmp #STAGE_EGRESS
    beq !next+
    lda OBJECT_Y,x                          // Keep firing to the readable middle of an attack.
    cmp #64
    bcc !next+
    cmp #190
    bcs !next+

    stx ENEMY_FIRE_SOURCE                   // Preserve shooter while the allocator searches for a bullet slot.
    jsr spawnEnemyBullet
    rts                                     // One global firing attempt per cadence is enough.

!next:
    inx                                     // Move to the next logical slot.
    cpx #MAX_OBJECTS
    bne !noWrap+
    ldx #1                                  // Wrap around while continuing to exclude player object 0.
!noWrap:
    dec ENEMY_FIRE_SCAN_COUNT
    bne !scan-

!done:
    rts

// --- Routine: spawnEnemyBullet ---------------------------------------------
// Allocate one hostile projectile and choose the nearest clean integer slope
// toward the player's X at firing time.  Vertical speed is always +3.
// Horizontal speed is quantised to -2,-1,0,+1,+2 so every bullet moves smoothly
// every frame instead of using a visibly irregular fractional stepping pattern.
spawnEnemyBullet:
    jsr findFreeObject                      // Bullets share the logical pool and renderer with every other sprite.
    bcc !allocated+                         // Keep the short relative branch local.
    jmp !failed+                            // Absolute jump handles the longer failure path safely.

!allocated:
    stx ENEMY_BULLET_OBJECT                 // X now belongs to the newly allocated projectile.
    ldy ENEMY_FIRE_SOURCE                   // Y addresses the enemy that actually fired.

    lda OBJECT_X,y                          // Launch from the shooter's sprite origin.
    sta OBJECT_X,x
    lda OBJECT_X_MSB,y
    sta OBJECT_X_MSB,x
    lda OBJECT_Y,y
    clc
    adc #12                                 // Start just below the enemy body.
    sta OBJECT_Y,x

    lda #TYPE_ENEMY_BULLET
    sta OBJECT_TYPE,x
    lda #enemyBulletSprite / 64
    sta OBJECT_SPRITE,x
    sta OBJECT_BASE_SPRITE,x                // Harmless bookkeeping consistency for the generic object arrays.
    lda #ENEMY_BULLET_COLOUR
    sta OBJECT_COLOUR,x
    sta OBJECT_BASE_COLOUR,x

    lda #0
    sta OBJECT_HEALTH,x
    sta OBJECT_HIT_TIMER,x
    sta OBJECT_DEATH_TIMER,x
    sta OBJECT_PATH_TIMER,x
    sta OBJECT_PATH_STEP,x
    sta OBJECT_ACCEL_TIMER,x
    sta OBJECT_VEL_X,x                      // Default trajectory is straight down.
    lda #ENEMY_BULLET_SPEED_Y
    sta OBJECT_VEL_Y,x

    // Work out whether the player is left or right of the projectile using the
    // full 9-bit X coordinate.  The magnitude is reduced to a practical byte;
    // anything beyond 255 pixels is necessarily in the steepest X bucket.
    lda OBJECT_X                            // playerX low
    sec
    sbc OBJECT_X,x                          // playerX - bulletX low
    sta ENEMY_AIM_DELTA_LO
    lda OBJECT_X_MSB
    sbc OBJECT_X_MSB,x                      // signed high byte of the 9-bit difference
    beq !targetRight+
    cmp #$ff
    beq !targetLeft+

    // A larger 9-bit separation: direction is determined by the sign/high byte
    // and the nearest useful trajectory is necessarily the strongest slope.
    bmi !farLeft+
    lda #2
    sta OBJECT_VEL_X,x
    jmp !activate+
!farLeft:
    lda #$fe                                // -2
    sta OBJECT_VEL_X,x
    jmp !activate+

!targetRight:
    lda ENEMY_AIM_DELTA_LO                  // Positive low-byte separation.
    jsr chooseEnemyBulletSlope
    sta OBJECT_VEL_X,x
    jmp !activate+

!targetLeft:
    lda ENEMY_AIM_DELTA_LO                  // Convert two's-complement low byte to positive magnitude.
    eor #$ff
    clc
    adc #1
    jsr chooseEnemyBulletSlope              // A returns positive 0..2 magnitude.
    beq !activate+
    eor #$ff                                // Negate the chosen magnitude for a leftward trajectory.
    clc
    adc #1
    sta OBJECT_VEL_X,x

!activate:
    lda #1
    sta OBJECT_ACTIVE,x                     // Publish the projectile only after every field is complete.
    inc ENEMY_BULLET_COUNT
    clc
    rts

!failed:
    sec
    rts

// --- Routine: chooseEnemyBulletSlope ---------------------------------------
// Entry: A = absolute horizontal distance to the player's snapshotted X.
// Exit:  A = clean horizontal velocity magnitude 0, 1 or 2.
//
// These thresholds intentionally favour smooth-looking trajectories over exact
// mathematical interception.  They correspond to nearby "good" aiming points;
// later difficulty levels can bias the target X before this quantisation to lead
// a moving player.
chooseEnemyBulletSlope:
    cmp #24                                 // Close enough horizontally: a vertical shot is the cleanest trajectory.
    bcc !straight+
    cmp #72                                 // Moderate separation: one pixel sideways per frame.
    bcc !medium+
    lda #2                                  // Wide separation: two pixels sideways per frame.
    rts
!medium:
    lda #1
    rts
!straight:
    lda #0
    rts

// --- Routine: moveEnemyBullet ----------------------------------------------
// Apply the projectile's immutable launch vector.  Bullets disappear when they
// leave either horizontal side or reach the bottom of the visible playfield.
moveEnemyBullet:
    lda OBJECT_VEL_X,x
    beq !moveY+
    bmi !left+

    clc                                     // Positive bullet X velocity.
    adc OBJECT_X,x
    sta OBJECT_X,x
    bcc !rightEdge+
    inc OBJECT_X_MSB,x
!rightEdge:
    lda OBJECT_X_MSB,x
    cmp #2
    bcs !remove+
    cmp #1
    bne !moveY+
    lda OBJECT_X,x
    cmp #$59                                // 345+, beyond the useful right edge.
    bcs !remove+
    jmp !moveY+

!left:
    clc                                     // Add signed negative velocity to the low byte.
    adc OBJECT_X,x
    sta OBJECT_X,x
    bcs !moveY+                             // No borrow means high byte remains unchanged.
    lda OBJECT_X_MSB,x
    beq !remove+                            // Borrow from X=0 means projectile has left the screen.
    dec OBJECT_X_MSB,x

!moveY:
    lda OBJECT_Y,x
    clc
    adc #ENEMY_BULLET_SPEED_Y
    bcs !remove+                            // Byte overflow is definitely below the screen.
    sta OBJECT_Y,x
    cmp #250
    bcs !remove+
    rts

!remove:
    lda #0
    sta OBJECT_ACTIVE,x
    lda ENEMY_BULLET_COUNT
    beq !done+                              // Defensive guard against an accidental double release.
    dec ENEMY_BULLET_COUNT
!done:
    rts

// --- Routine: moveEnemyPath -------------------------------------------------
// Advance one enemy through its segmented ingress/manoeuvre/egress movement.
// OBJECT_STAGE selects which of the three fragment tables OBJECT_PATH_STEP
// indexes; setFragmentPointer resolves that into FRAG_PTR each time a new
// segment header must be read.  Finite segments set a new TARGET velocity,
// which easeVelocityTowardTarget then bends the live velocity towards by one
// unit per frame, rather than snapping instantly.  A final $ff segment is a
// coast: it deliberately keeps the velocity produced by the preceding
// fragment so an enemy leaves the playfield carrying its existing momentum
// rather than snapping to an unrelated canned exit vector.  A duration of
// zero means the current fragment has ended: ingress hands off to the
// object's manoeuvre fragment, manoeuvre hands off to its egress fragment,
// and egress ending this way (rather than by screen-edge exit) deactivates
// the object exactly as path completion always has.
// Entry: X = logical object index.
moveEnemyPath:
    lda OBJECT_PATH_TIMER,x                 // Load frames remaining in the current path segment.
    bne !ramp+                              // If non-zero, ease velocity then continue the current segment.

    jsr setFragmentPointer                  // FRAG_PTR now points at OBJECT_STAGE's active fragment table.
    ldy OBJECT_PATH_STEP,x                  // Y = byte offset of the current path segment.
    lda (FRAG_PTR),y                        // Read this segment's duration from the selected fragment.
    bne !loadSegment+                       // Non-zero means this is a valid movement segment.
    jmp !advanceStage+                      // Duration zero means this fragment/stage has finished.

!loadSegment:
    sta OBJECT_PATH_TIMER,x                 // Save duration; $ff is the momentum-preserving coast marker.
    cmp #$ff                                // Final coast segments do not replace the current target velocity.
    beq !ramp+

    iny                                     // Advance to the segment's signed vx byte.
    lda (FRAG_PTR),y                        // Read signed horizontal velocity for this manoeuvre segment.
    sta OBJECT_TARGET_VEL_X,x               // Ease towards this rather than snapping to it directly.
    iny                                     // Advance to the segment's signed vy byte.
    lda (FRAG_PTR),y                        // Read signed vertical velocity for this manoeuvre segment.
    sta OBJECT_TARGET_VEL_Y,x               // Subsequent acceleration may increase this target further.

!ramp:
    jsr easeVelocityTowardTarget            // Bend live velocity one unit/frame towards the target vector.

!move:
    lda OBJECT_VEL_X,x                      // Read the enemy's current signed horizontal velocity.
    beq !moveY+                             // Zero means no horizontal movement this frame.
    bmi !moveXLeft+                         // Bit 7 set means a negative horizontal velocity.

!moveXRight:
    clc                                     // Clear carry before adding the positive X velocity.
    adc OBJECT_X,x                          // Add velocity to the low byte of the 9-bit X coordinate.
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
    clc                                     // Clear carry before adding the two's-complement velocity.
    adc OBJECT_X,x                          // Add negative velocity to the low byte.
    sta OBJECT_X,x                          // Store the new low byte.
    bcs !moveY+                             // Carry set means no borrow across the 256-pixel boundary.
    lda OBJECT_X_MSB,x                      // A borrow while high byte zero means we crossed left of X=0.
    bne !leftHighValid+                     // High byte one can legitimately borrow back into the lower half.
    jmp !finished+                          // Deactivate instead of wrapping from X=0 to X=511.
!leftHighValid:
    dec OBJECT_X_MSB,x                      // Move normally from the upper X half into the lower half.

!moveY:
    lda OBJECT_VEL_Y,x                      // Read the enemy's current signed vertical velocity.
    beq !accelerate+                        // Zero means no vertical movement this frame.
    bmi !moveYUp+                           // Negative velocity means movement towards the top.

!moveYDown:
    clc                                     // Clear carry before adding the positive Y velocity.
    adc OBJECT_Y,x                          // Add downward velocity to the current Y position.
    bcs !finished+                          // Carry means Y crossed $ff; deactivate instead of wrapping to $00.
    sta OBJECT_Y,x                          // Store the valid new Y position.
    jmp !accelerate+                        // Descending movement may gradually gain speed.

!moveYUp:
    clc                                     // Clear carry before adding the negative two's-complement velocity.
    adc OBJECT_Y,x                          // Add upward velocity to the current Y position.
    bcc !finished+                          // No carry means Y crossed below $00; deactivate instead of wrapping to $ff.
    sta OBJECT_Y,x                          // Store the valid new Y position.

!accelerate:
    jsr accelerateEnemyDive                 // Only positive-Y motion can build additional speed.

!tick:
    lda OBJECT_PATH_TIMER,x                 // Read the active segment duration marker.
    cmp #$ff                                // $ff means coast on the velocity inherited from the last manoeuvre.
    beq !done+                              // Lifecycle bounds, not path duration, will remove the enemy.

    dec OBJECT_PATH_TIMER,x                 // Consume one frame from a finite path segment.
    bne !done+                              // If frames remain, stay on this segment.

    lda OBJECT_PATH_STEP,x                  // Load current byte offset in the path table.
    clc                                     // Clear carry before adding the segment size.
    adc #3                                  // Advance past duration, vx and vy.
    sta OBJECT_PATH_STEP,x                  // Save offset of the next segment.

!done:
    rts                                     // Current enemy update is complete.

!finished:
    lda #0                                  // Zero represents inactive.
    sta OBJECT_ACTIVE,x                     // Return this logical object to the free pool.
    rts

!advanceStage:
    lda OBJECT_STAGE,x                      // Which stage just ran out of segments?
    cmp #STAGE_INGRESS
    bne !checkManoeuvre+

    lda #STAGE_MANOEUVRE                    // Ingress finished: hand off to the precomputed manoeuvre fragment.
    sta OBJECT_STAGE,x
    lda OBJECT_MANOEUVRE_STEP,x
    sta OBJECT_PATH_STEP,x
    jmp moveEnemyPath                       // Re-enter now: OBJECT_PATH_TIMER,x is still 0, so this loads the
                                             // manoeuvre's first segment header immediately (not next frame) -
                                             // ticking it via !tick's dec would wrap 0 to $ff and strand the
                                             // object forever if we instead fell through past the segment load.

!checkManoeuvre:
    cmp #STAGE_MANOEUVRE
    bne !finished-                          // Already egress: fragment completion means the attack is over.

    lda #STAGE_EGRESS                       // Manoeuvre finished: hand off to the precomputed egress fragment.
    sta OBJECT_STAGE,x
    lda OBJECT_EGRESS_STEP,x
    sta OBJECT_PATH_STEP,x
    jmp moveEnemyPath                       // Re-enter to load the egress's first segment header immediately.

// --- Routine: setFragmentPointer --------------------------------------------
// Point FRAG_PTR at the base of whichever fragment table OBJECT_STAGE,x
// currently selects, so moveEnemyPath can read segments via (FRAG_PTR),y
// regardless of which of the three per-stage tables the object is in.
// Entry/exit: X = logical object index, preserved.
setFragmentPointer:
    ldy OBJECT_STAGE,x                      // 0=ingress, 1=manoeuvre, 2=egress: index straight into
    lda fragmentTableLo,y                   // these two separate parallel lo/hi arrays (no doubling -
                                             // each table is one byte per stage, not an interleaved pair).
    sta FRAG_PTR
    lda fragmentTableHi,y
    sta FRAG_PTR+1
    rts

fragmentTableLo:
    .byte <ingressFragments, <manoeuvreFragments, <egressFragments
fragmentTableHi:
    .byte >ingressFragments, >manoeuvreFragments, >egressFragments

// --- Routine: easeVelocityTowardTarget --------------------------------------
// Nudge OBJECT_VEL_X/Y one unit per frame towards OBJECT_TARGET_VEL_X/Y rather
// than snapping straight to it, so fragment transitions visibly bend instead
// of popping to a new vector.  Cheap signed compare via subtraction; no
// multiply/divide.  Entry/exit: X = logical object index, preserved.
easeVelocityTowardTarget:
    lda OBJECT_TARGET_VEL_X,x
    sec
    sbc OBJECT_VEL_X,x                      // A = target - current (signed; range is small, cannot overflow).
    beq !xDone+
    bmi !xDec+
    inc OBJECT_VEL_X,x                      // Current is below target: nudge up by one.
    jmp !xDone+
!xDec:
    dec OBJECT_VEL_X,x                      // Current is above target: nudge down by one.
!xDone:

    lda OBJECT_TARGET_VEL_Y,x
    sec
    sbc OBJECT_VEL_Y,x
    beq !yDone+
    bmi !yDec+
    inc OBJECT_VEL_Y,x
    jmp !yDone+
!yDec:
    dec OBJECT_VEL_Y,x
!yDone:
    rts

// --- Routine: accelerateEnemyDive ------------------------------------------
// Give descending enemies a small integer acceleration in roughly the direction
// they are already travelling.  Every ENEMY_ACCEL_INTERVAL descending frames we
// increase the dominant component of the vector; a 45-degree vector grows both.
// This deliberately uses cheap compares/increments rather than multiplication or
// fixed-point maths.  Upward/level flight resets the cadence and does not speed up.
// Entry/exit: X = logical object index, preserved.
accelerateEnemyDive:
    lda OBJECT_VEL_Y,x                      // Only positive Y velocity represents a descent.
    beq !reset+
    bmi !reset+

    inc OBJECT_ACCEL_TIMER,x                // Count frames spent travelling downward.
    lda OBJECT_ACCEL_TIMER,x
    cmp #ENEMY_ACCEL_INTERVAL               // Wait until the small acceleration interval has elapsed.
    bcc !done+
    lda #0
    sta OBJECT_ACCEL_TIMER,x                // Restart the cadence before adjusting either component.

    lda OBJECT_VEL_X,x                      // Determine the absolute horizontal speed for angle comparison.
    bpl !xPositive+
    eor #$ff                                // Two's-complement absolute value: invert then add one.
    clc
    adc #1
!xPositive:
    sta PATH_ABS_X                          // Scratch byte is safe because movement runs only in the main thread.

    cmp OBJECT_VEL_Y,x                      // Compare |vx| with positive vy to approximate the descent angle.
    beq !accelerateBoth+                    // Equal components represent an approximately 45-degree dive.
    bcc !accelerateY+                       // Steeper dive: add speed mainly to the vertical component.

!accelerateX:
    lda PATH_ABS_X                          // Shallower dive: increase horizontal magnitude instead.
    cmp #ENEMY_MAX_PATH_SPEED
    bcs !done+                              // Component already sits at the safety cap.
    lda OBJECT_TARGET_VEL_X,x               // Accumulate into the target; easeVelocityTowardTarget will
    bmi !accelerateXLeft+                   // carry the live velocity to it over the next frame or two.
    inc OBJECT_TARGET_VEL_X,x               // Positive horizontal velocity becomes more positive.
    rts
!accelerateXLeft:
    dec OBJECT_TARGET_VEL_X,x               // Negative horizontal velocity becomes more negative.
    rts

!accelerateY:
    lda OBJECT_TARGET_VEL_Y,x
    cmp #ENEMY_MAX_PATH_SPEED
    bcs !done+
    inc OBJECT_TARGET_VEL_Y,x               // Steep dive gains one pixel/frame vertically.
    rts

!accelerateBoth:
    lda OBJECT_TARGET_VEL_Y,x               // Grow vertical speed first when both components are equal.
    cmp #ENEMY_MAX_PATH_SPEED
    bcs !done+
    inc OBJECT_TARGET_VEL_Y,x

    lda PATH_ABS_X                          // A purely vertical vector has |vx|=0 and was handled by BCC above.
    cmp #ENEMY_MAX_PATH_SPEED
    bcs !done+
    lda OBJECT_TARGET_VEL_X,x
    bmi !accelerateBothLeft+
    inc OBJECT_TARGET_VEL_X,x
    rts
!accelerateBothLeft:
    dec OBJECT_TARGET_VEL_X,x
    rts

!reset:
    lda #0                                  // Breaking the descent also breaks the accumulated acceleration cadence.
    sta OBJECT_ACCEL_TIMER,x
!done:
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

    lda OBJECT_X,x                          // Snapshot the path-owned 9-bit X coordinate directly.
    sta INITIAL_X,y
    lda OBJECT_X_MSB,x
    sta INITIAL_X_MSB,y

    lda OBJECT_Y,x                          // Snapshot the path-owned Y coordinate directly.
    sta INITIAL_Y,y
    lda OBJECT_SPRITE,x                     // Load A from OBJECT_SPRITE,x.
    sta INITIAL_SPRITE,y                    // Store A in INITIAL_SPRITE,y.
    lda OBJECT_COLOUR,x                     // Load A from OBJECT_COLOUR,x.
    sta INITIAL_COLOUR,y                    // Store A in INITIAL_COLOUR,y.
    txa                                     // Copy the logical object index into A.
    sta INITIAL_OBJECT,y                    // Remember which logical object owns this hardware snapshot entry.

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
    beq !cannotSchedule+                    // Empty batch: skip this unschedulable object.
    jmp !finishBatch+                       // Non-empty batch: finish it with an absolute jump.

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

    lda OBJECT_X,y                          // Snapshot the path-owned 9-bit X coordinate directly.
    sta ASSIGN_X,x
    lda OBJECT_X_MSB,y
    sta ASSIGN_X_MSB,x

    lda OBJECT_Y,y                          // Snapshot the path-owned Y coordinate directly.
    sta ASSIGN_Y,x
    lda OBJECT_SPRITE,y                     // Load A from OBJECT_SPRITE,y.
    sta ASSIGN_SPRITE,x                     // Store A in ASSIGN_SPRITE,x.
    lda OBJECT_COLOUR,y                     // Load A from OBJECT_COLOUR,y.
    sta ASSIGN_COLOUR,x                     // Store A in ASSIGN_COLOUR,x.
    tya                                     // Copy the logical object index into A.
    sta ASSIGN_OBJECT,x                     // Remember which object will own the recycled hardware slot.

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

// --- Routine: setupLivesDisplay --------------------------------------------
// Initialise the stock and draw the compact top-row lives HUD.
setupLivesDisplay:
    lda #PLAYER_START_LIVES
    sta PLAYER_LIVES
    ldx #0
!labelLoop:
    lda livesLabel,x
    sta LIVES_SCREEN,x
    lda #1
    sta LIVES_COLOUR,x
    inx
    cpx #7                                  // "LIVES " plus one digit.
    bne !labelLoop-
    rts

// --- Routine: displayLives --------------------------------------------------
// Current design only needs a single decimal digit; later upgrades/continues
// can replace this if we ever allow more than nine ships.
displayLives:
    lda PLAYER_LIVES
    clc
    adc #48
    sta LIVES_SCREEN + 6
    rts

livesLabel:
    .byte 12,9,22,5,19,32,51               // Screen codes for "LIVES 3".

// "GAME OVER" screen codes, stamped by drawGameOverText via drawTextRow.
gameOverLabel:
    .byte 7,1,13,5,32,15,22,5,18

// --- Routine: setupScoreDisplay --------------------------------------------
// Clear the 16-bit score and draw "SCORE 00000" at the top-right of screen RAM.
setupScoreDisplay:
    lda #0
    sta SCORE_LO                            // Score begins at zero, low byte.
    sta SCORE_HI                            // Score begins at zero, high byte.

    ldx #0                                  // Copy the fixed label plus five decimal digits.
!labelLoop:
    lda scoreLabel,x
    sta SCORE_SCREEN,x
    lda #1                                  // C64 colour 1 = white.
    sta SCORE_COLOUR,x
    inx
    cpx #11                                 // "SCORE " plus five digits.
    bne !labelLoop-
    rts

// --- Routine: awardKillScore -----------------------------------------------
// Add the fixed kill reward to the 16-bit binary score and refresh the HUD.
// X is the logical enemy index in the caller, so preserve it across conversion.
awardKillScore:
    txa
    pha                                     // Preserve updateEnemyHitEffects' object-loop X index.

    lda SCORE_LO
    clc
    adc #<SCORE_PER_KILL
    sta SCORE_LO
    lda SCORE_HI
    adc #>SCORE_PER_KILL
    sta SCORE_HI

    jsr displayScore

    pla
    tax                                     // Restore the dying enemy's logical object index.
    rts

// --- Routine: displayScore --------------------------------------------------
// Convert the 16-bit binary score to five decimal digits at SCORE_SCREEN+6.
// The existing decimal divisor table is shared with the FREE-cycle display.
displayScore:
    lda SCORE_LO
    sta SCORE_VALUE_LO                      // Conversion works on a disposable copy.
    lda SCORE_HI
    sta SCORE_VALUE_HI

    ldx #0                                  // Start at the 10000s decimal place.
!digitLoop:
    ldy #0                                  // Y counts how many times this divisor fits.
!subtractLoop:
    lda SCORE_VALUE_HI
    cmp debugDivisorHi,x
    bcc !emitDigit+
    bne !subtract+
    lda SCORE_VALUE_LO
    cmp debugDivisorLo,x
    bcc !emitDigit+

!subtract:
    lda SCORE_VALUE_LO
    sec
    sbc debugDivisorLo,x
    sta SCORE_VALUE_LO
    lda SCORE_VALUE_HI
    sbc debugDivisorHi,x
    sta SCORE_VALUE_HI
    iny
    bne !subtractLoop-

!emitDigit:
    tya
    clc
    adc #48                                 // Screen codes 48-57 display digits 0-9.
    sta SCORE_SCREEN + 6,x
    inx
    cpx #5
    bne !digitLoop-
    rts

scoreLabel:
    .byte 19,3,15,18,5,32,48,48,48,48,48  // Screen codes for "SCORE 00000".

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
    jsr capturePlayerCollision              // Consume collisions using the hardware ownership from the previous raster interval.

    lda #0                                  // Load A from #0.
    sta PLAYER_HW_MASK                      // Rebuild the player's current hardware-slot mask from this LIVE snapshot.
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

    lda INITIAL_OBJECT,y                    // Which logical object owns this snapshot entry?
    bne !notPlayer+                         // Object 0 is permanently reserved for the player.
    lda HW_BIT_MASK,x                       // Convert the hardware sprite slot into its collision bit.
    sta PLAYER_HW_MASK                      // Remember where the player currently lives in VIC hardware.
!notPlayer:

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
    jsr capturePlayerCollision              // Consume $D01E before this batch changes hardware-sprite ownership.

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

    lda HW_BIT_MASK,x                       // Get the bit belonging to the hardware slot being recycled.
    eor #$ff                                // Invert it into a clear-mask.
    and PLAYER_HW_MASK                      // Remove this slot from the player mask if the player previously owned it.
    sta PLAYER_HW_MASK                      // Ownership is about to change.

    lda ASSIGN_OBJECT,y                     // Read the logical object taking ownership of this slot.
    bne !assignmentNotPlayer+               // Non-zero means an enemy/other object.
    lda HW_BIT_MASK,x                       // Object 0 is the player, so capture its new hardware slot.
    sta PLAYER_HW_MASK
!assignmentNotPlayer:

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

// --- Routine: capturePlayerCollision ---------------------------------------
// $d01e remains the cheap hardware broad phase.  If the player's current VIC
// slot participated, scan logical gameplay objects and let compact helper
// routines confirm the actual overlap.  Keeping the scan itself short also
// avoids 6502 relative-branch range problems as collision rules grow.
capturePlayerCollision:
    lda VIC_SPRITE_COLLISION                // Always read/clear the VIC latch, even while invulnerable.
    ldy PLAYER_STATE
    beq !playerAlive+
    rts

!playerAlive:
    and PLAYER_HW_MASK
    bne !playerCollision+
    rts

!playerCollision:
    ldx #1
!scan:
    lda OBJECT_ACTIVE,x
    bne !active+
    jmp !next+

!active:
    lda OBJECT_TYPE,x
    cmp #TYPE_ENEMY
    bne !checkBullet+

    lda OBJECT_DEATH_TIMER,x                // Explosion sprites are presentation only.
    bne !next+
    jsr checkEnemyPlayerOverlap             // Carry set means this living enemy overlaps the player.
    bcs !hit+
    jmp !next+

!checkBullet:
    cmp #TYPE_ENEMY_BULLET
    bne !next+
    jsr checkBulletPlayerOverlap            // Carry set means the small projectile box overlaps the player.
    bcc !next+

!hit:
    lda #1
    sta PLAYER_HIT
    rts

!next:
    inx
    cpx #MAX_OBJECTS
    beq !done+
    jmp !scan-

!done:
    rts

// --- Routine: checkEnemyPlayerOverlap --------------------------------------
// Entry: X = logical enemy object.
// Exit:  C set if its 24x21 body overlaps the player's 24x21 body.
checkEnemyPlayerOverlap:
    lda OBJECT_X,x                          // enemyX - playerX, full 9-bit signed delta.
    sec
    sbc OBJECT_X
    tay
    lda OBJECT_X_MSB,x
    sbc OBJECT_X_MSB
    beq !enemyRight+
    cmp #$ff
    beq !enemyLeft+
    clc
    rts

!enemyLeft:
    tya
    cmp #$e9                                // -23..-1 overlaps a 24-pixel player body.
    bcs !enemyVertical+
    clc
    rts

!enemyRight:
    tya
    cmp #24
    bcc !enemyVertical+
    clc
    rts

!enemyVertical:
    lda OBJECT_Y,x
    sec
    sbc OBJECT_Y
    bcs !enemyBelow+
    cmp #$ec                                // -20..-1 overlaps a 21-pixel player body.
    bcs !enemyHit+
    clc
    rts

!enemyBelow:
    cmp #21
    bcc !enemyHit+
    clc
    rts

!enemyHit:
    sec
    rts

// --- Routine: checkBulletPlayerOverlap -------------------------------------
// Entry: X = logical hostile projectile.
// Exit:  C set if its compact 8x8 lethal area overlaps the 24x21 player body.
checkBulletPlayerOverlap:
    lda OBJECT_X,x
    sec
    sbc OBJECT_X
    tay
    lda OBJECT_X_MSB,x
    sbc OBJECT_X_MSB
    beq !bulletRight+
    cmp #$ff
    beq !bulletLeft+
    clc
    rts

!bulletLeft:
    tya
    cmp #$f9                                // -7..-1.
    bcs !bulletVertical+
    clc
    rts

!bulletRight:
    tya
    cmp #24
    bcc !bulletVertical+
    clc
    rts

!bulletVertical:
    lda OBJECT_Y,x
    sec
    sbc OBJECT_Y
    bcs !bulletBelow+
    cmp #$f9                                // Bullet may begin up to 7 pixels above the player.
    bcs !bulletHit+
    clc
    rts

!bulletBelow:
    cmp #21
    bcc !bulletHit+
    clc
    rts

!bulletHit:
    sec
    rts

// --- Routine: updatePlayerState --------------------------------------------
// Consume PLAYER_HIT and run the player death presentation. Object 0 is never
// freed: it changes sprite/state, then returns to the fixed player start point.
updatePlayerState:
    lda PLAYER_STATE                        // Dispatch the player's current gameplay state.
    cmp #PLAYER_STATE_ALIVE
    beq !alive+
    cmp #PLAYER_STATE_EXPLODING
    beq !exploding+
    cmp #PLAYER_STATE_RESPAWNING
    bne !notRespawning+                     // Keep relative branch local; respawn handler is now too far away.
    jmp !respawning+                        // Absolute jump safely reaches the larger respawn block.
!notRespawning:
    rts                                     // GAME OVER is terminal in this first-pass gameplay test.

!alive:
    lda PLAYER_HIT                          // Has collision capture reported a vulnerable-player impact?
    bne !beginExplosion+                    // Yes: start the death presentation.
    rts                                     // No: normal play continues.

!beginExplosion:

    lda #0                                  // Consume the latched collision event.
    sta PLAYER_HIT

    lda #PLAYER_STATE_EXPLODING             // Freeze controls and begin the explosion animation.
    sta PLAYER_STATE
    lda #0
    sta PLAYER_EXPLOSION_FRAME
    lda #PLAYER_EXPLOSION_HOLD
    sta PLAYER_STATE_TIMER

    lda #playerExplosion1 / 64              // First explosion frame replaces the ship in object 0.
    sta OBJECT_SPRITE
    lda #7                                  // Yellow flash for the initial blast.
    sta OBJECT_COLOUR
    rts

!exploding:
    dec PLAYER_STATE_TIMER                  // Hold the current explosion frame for a few video frames.
    beq !advanceExplosion+                  // Timer expired: select the next bitmap.
    rts                                     // Otherwise keep showing the current frame.

!advanceExplosion:

    inc PLAYER_EXPLOSION_FRAME              // Advance to the next explosion bitmap.
    lda PLAYER_EXPLOSION_FRAME
    cmp #1
    beq !explosion2+
    cmp #2
    beq !explosion3+
    cmp #3
    beq !explosion4+

    dec PLAYER_LIVES                        // The destroyed ship is now consumed.
    jsr displayLives                        // Keep the HUD in sync with the remaining stock.
    lda PLAYER_LIVES
    beq !gameOver+                          // No ships remain: do not reposition or respawn.
    jmp !startRespawn+                      // Otherwise reposition and enter invulnerability.

!explosion2:
    lda #playerExplosion2 / 64
    sta OBJECT_SPRITE
    lda #8                                  // Orange.
    sta OBJECT_COLOUR
    jmp !reloadExplosion+

!explosion3:
    lda #playerExplosion3 / 64
    sta OBJECT_SPRITE
    lda #2                                  // Red.
    sta OBJECT_COLOUR
    jmp !reloadExplosion+

!explosion4:
    lda #playerExplosion4 / 64
    sta OBJECT_SPRITE
    lda #9                                  // Brown/dark blast fringe.
    sta OBJECT_COLOUR

!reloadExplosion:
    lda #PLAYER_EXPLOSION_HOLD
    sta PLAYER_STATE_TIMER
    rts

!gameOver:
    lda #PLAYER_STATE_GAME_OVER             // Signal gameLoop to hand control back to the state router.
    sta PLAYER_STATE
    lda #blankSprite / 64                   // Remove the ship after its final explosion has completed.
    sta OBJECT_SPRITE
    rts                                     // endGame (game level) owns teardown and the GAME OVER screen now.

!startRespawn:
    lda #PLAYER_START_X                     // Move the permanently-owned player object back to start.
    sta OBJECT_X
    lda #0
    sta OBJECT_X_MSB
    lda #PLAYER_START_Y
    sta OBJECT_Y

    lda #playerSprite / 64                  // Restore the normal player ship bitmap.
    sta OBJECT_SPRITE
    lda #2                                  // Restore the normal player individual colour.
    sta OBJECT_COLOUR

    lda #PLAYER_RESPAWN_TIME                // Start the invulnerable blinking period.
    sta PLAYER_STATE_TIMER
    lda #0
    sta PLAYER_BLINK_TIMER
    lda #PLAYER_STATE_RESPAWNING
    sta PLAYER_STATE
    rts

!respawning:
    dec PLAYER_STATE_TIMER                  // Count down invulnerability.
    beq !finishRespawn+

    inc PLAYER_BLINK_TIMER                  // Toggle visibility every four frames.
    lda PLAYER_BLINK_TIMER
    and #%00000100
    beq !showPlayer+

    lda #blankSprite / 64                   // Keep object 0 active; only its presentation blinks off.
    sta OBJECT_SPRITE
    rts

!showPlayer:
    lda #playerSprite / 64                  // Restore the visible ship for this blink phase.
    sta OBJECT_SPRITE
    rts

!finishRespawn:
    lda #playerSprite / 64                  // Guarantee the normal ship bitmap when vulnerability returns.
    sta OBJECT_SPRITE
    lda #0
    sta PLAYER_HIT                          // Discard any stale hit state.
    lda #PLAYER_STATE_ALIVE
    sta PLAYER_STATE
    rts

!done:
    rts

// --- Routine: startRandomWave ------------------------------------------------
// Choose one complete curated attack.  An attack owns its entry geometry,
// enemy count, spawn cadence, path and visual sequence; movement and spacing
// are therefore always combinations we have deliberately approved.
//
// CIA1 timer bits still provide cheap variety for the development director.
// Later, a stage script can simply load a chosen attack ID instead.
startRandomWave:
    lda CIA1_TIMER_A_LO                     // Sample the continuously changing CIA timer.
    and #%00001111                          // Reduce it to a compact 0-15 lookup index.
    tay                                     // Y indexes the cheap random-to-attack mapping table.
    lda randomAttackMap,y                   // Convert 16 possible values into attack IDs 0-8.
    sta WAVE_ATTACK_ID                      // Remember the selected attack for debugging/stage logic.
    tay                                     // Y = curated attack index.

    lda attackSpriteStart,y                 // Read this attack's first visual-sequence entry.
    sta WAVE_SPRITE_INDEX                   // Seed sprite/colour selection for its first member.

    lda attackEnemyCount,y                  // Read number of enemies in this attack.
    sta WAVE_ENEMY_COUNT                    // Store target number of successful spawns.

    lda attackInterval,y                    // Read frames between attack members.
    sta WAVE_SPAWN_INTERVAL                 // Preserve interval for each timer reload.

    lda attackStartXLo,y                    // Read low byte of first enemy's 9-bit X coordinate.
    sta WAVE_SPAWN_X                        // Seed cumulative horizontal spawn position.

    lda attackStartXMsb,y                   // Read ninth X bit for left/top/right-side entry.
    sta WAVE_SPAWN_X_MSB                    // Preserve full spawn coordinate for upper-right attacks.

    lda attackStartY,y                      // Read first enemy's starting Y coordinate.
    sta WAVE_SPAWN_Y                        // Seed cumulative vertical spawn position.

    lda attackAddX,y                        // Read signed horizontal offset between members.
    sta WAVE_ADD_X_VALUE                    // Top entries may spread in X; side entries currently do not.

    lda attackAddY,y                        // Read signed vertical offset between members.
    sta WAVE_ADD_Y_VALUE                    // Side entries deliberately stagger Y to avoid raster-line walls.

    lda attackIngressId,y                   // Read the ingress fragment assigned to this curated attack.
    sta WAVE_INGRESS_ID                      // Each spawned object begins on this fragment.
    lda attackManoeuvreId,y                 // Read the manoeuvre fragment chained after ingress.
    sta WAVE_MANOEUVRE_ID
    lda attackEgressId,y                    // Read the egress fragment chained after manoeuvre.
    sta WAVE_EGRESS_ID

    lda #0                                  // A new attack has not spawned any members yet.
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

    lda WAVE_SPAWN_X                        // Read low byte of this attack member's 9-bit X position.
    sta OBJECT_X,x                          // Store low byte of enemy X position.
    lda WAVE_SPAWN_X_MSB                    // Read ninth bit of the spawn position.
    sta OBJECT_X_MSB,x                      // Preserve right-side/off-screen entry coordinates correctly.

    lda WAVE_SPAWN_Y                        // Read this wave member's current Y position.
    sta OBJECT_Y,x                          // Store initial enemy Y position.

    lda #TYPE_ENEMY                         // This logical object behaves as an enemy.
    sta OBJECT_TYPE,x                       // Store enemy object type.

    ldy WAVE_SPRITE_INDEX                  // Y selects this formation member's visual variant.
    lda enemySpriteSequence,y               // Read the sprite pointer chosen for this member.
    sta OBJECT_SPRITE,x                     // Store currently rendered sprite bitmap index.
    sta OBJECT_BASE_SPRITE,x                // Preserve original art for private health-bar sprite copies.

    lda enemyColourSequence,y               // Read this member's individual multicolour value.
    sta OBJECT_COLOUR,x                     // Store currently rendered enemy colour.
    sta OBJECT_BASE_COLOUR,x                // Preserve it so impact flashes can restore the formation colour.

    lda #ENEMY_START_HEALTH
    sta OBJECT_HEALTH,x                     // Every current enemy begins with the same provisional health.
    lda #0
    sta OBJECT_HIT_TIMER,x
    sta OBJECT_DEATH_TIMER,x                // Freshly spawned objects are alive, not inheriting a reused slot's death state.

    inc WAVE_SPRITE_INDEX                   // Advance only after a successful allocation/spawn.

    lda WAVE_ATTACK_ID                      // Read the curated attack selected for this wave.
    sta OBJECT_PATTERN,x                    // Retain the attack number for gameplay/debugging.

    lda #STAGE_INGRESS                      // Every enemy begins life on its ingress fragment.
    sta OBJECT_STAGE,x

    ldy WAVE_INGRESS_ID                     // Y = this attack's ingress fragment ID.
    lda ingressStartOffset,y                // Convert fragment ID to its byte offset in ingressFragments.
    sta OBJECT_PATH_STEP,x                  // Begin this object at the selected ingress fragment's first segment.

    ldy WAVE_MANOEUVRE_ID                   // Precompute where to jump once ingress finishes.
    lda manoeuvreStartOffset,y
    sta OBJECT_MANOEUVRE_STEP,x

    ldy WAVE_EGRESS_ID                      // Precompute where to jump once the manoeuvre finishes.
    lda egressStartOffset,y
    sta OBJECT_EGRESS_STEP,x

    lda #0                                  // Zero forces the first segment duration to load next update.
    sta OBJECT_PATH_TIMER,x                 // Reset movement path timer.
    sta OBJECT_VEL_X,x                      // Reused slots must not inherit velocity from a previous enemy.
    sta OBJECT_VEL_Y,x                      // Start stationary until the first path segment loads its vector.
    sta OBJECT_TARGET_VEL_X,x               // Target starts at zero too so the first segment's ease has a clean base.
    sta OBJECT_TARGET_VEL_Y,x
    sta OBJECT_ACCEL_TIMER,x                // Fresh enemy begins a new acceleration cadence.

    lda #1                                  // Mark object active only after every field is initialised.
    sta OBJECT_ACTIVE,x                     // Object now participates in update/render processing.

    clc                                     // Signal successful spawn.
    rts

!failed:
    sec                                     // Preserve allocation-failed result.
    rts

// --- Routine: updateSpawner -------------------------------------------------
// Spawn the current curated attack, then leave a short gap before choosing another.
updateSpawner:
    lda WAVE_SPAWNED                        // Read how many members of this formation have spawned.
    cmp WAVE_ENEMY_COUNT                    // Compare against the current attack's requested count.
    bcc !waveActive+                        // Carry clear means this attack still has members to spawn.

    lda WAVE_GAP_TIMER                      // Attack is complete: read inter-attack delay.
    beq !startNext+                         // Zero means the director may choose another attack now.
    dec WAVE_GAP_TIMER                      // Consume one frame of breathing room between attacks.
    bne !done+                              // Keep waiting while any gap remains.

!startNext:
    jsr startRandomWave                     // Choose a fresh curated attack.

!waveActive:
    lda SPAWN_TIMER                         // Read frames remaining until the next formation member.
    beq !spawn+                             // Zero means this member is ready to spawn.

    dec SPAWN_TIMER                         // Consume one frame of the inter-enemy delay.
    bne !done+                              // Non-zero means the delay is still running.

!spawn:
    jsr spawnEnemy                          // Try to allocate and initialise the next attack member.
    bcs !done+                              // Pool full: keep this position and retry next frame.

    inc WAVE_SPAWNED                        // Record one successfully created attack member.

    lda WAVE_ADD_X_VALUE                    // Read signed horizontal offset for the next attack member.
    beq !xOffsetDone+                       // Zero is common for side-entry streams; avoid needless 9-bit work.
    bmi !xOffsetLeft+                       // Negative two's-complement offsets require borrow handling.

!xOffsetRight:
    clc                                     // Clear carry before adding a positive horizontal offset.
    adc WAVE_SPAWN_X                        // Add to the low byte of the 9-bit spawn coordinate.
    sta WAVE_SPAWN_X                        // Save the next member's low X byte.
    bcc !xOffsetDone+                       // No carry means the ninth bit is unchanged.
    inc WAVE_SPAWN_X_MSB                    // Carry crosses X=255 into the upper half.
    jmp !xOffsetDone+

!xOffsetLeft:
    clc                                     // Clear carry before adding the signed negative offset.
    adc WAVE_SPAWN_X                        // Two's-complement addition updates the low X byte.
    sta WAVE_SPAWN_X                        // Save the next member's low X byte.
    bcs !xOffsetDone+                       // Carry set means no borrow from the ninth bit.
    dec WAVE_SPAWN_X_MSB                    // Borrow crosses from the upper half into the lower half.

!xOffsetDone:
    clc                                     // Clear carry before adding the vertical attack offset.
    lda WAVE_SPAWN_Y                        // Read the position used by the enemy just spawned.
    adc WAVE_ADD_Y_VALUE                    // Add this attack's per-enemy vertical offset.
    sta WAVE_SPAWN_Y                        // Save the next member's starting Y position.

    lda WAVE_SPAWNED                        // Re-check count before a possible same-frame spawn.
    cmp WAVE_ENEMY_COUNT                    // Has this attack now spawned every requested member?
    bcc !moreMembers+                       // No: prepare the interval before the next member.

    lda #WAVE_GAP                           // Final member launched: start the inter-attack gap.
    sta WAVE_GAP_TIMER                      // Director will remain idle until this expires.
    rts                                     // Do not begin another formation in this frame.

!moreMembers:
    lda WAVE_SPAWN_INTERVAL                 // Read this attack's delay between successful spawns.
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

starRowLo:
    .byte $00,$28,$50,$78,$a0,$c8,$f0,$18,$40,$68,$90,$b8,$e0,$08,$30,$58,$80,$a8,$d0,$f8,$20,$48,$70,$98,$c0
starRowHi:
    .byte $04,$04,$04,$04,$04,$04,$04,$05,$05,$05,$05,$05,$05,$06,$06,$06,$06,$06,$06,$06,$07,$07,$07,$07,$07

LOOKUP_TABLES_END:
.if (LOOKUP_TABLES_END > $2000) {
    .error "Lookup tables overlap engine runtime state"
}

// --- Engine runtime state ---------------------------------------------------
* = $2000
OBJECT_X:              .fill MAX_OBJECTS, 0
OBJECT_Y:              .fill MAX_OBJECTS, 0
OBJECT_X_MSB:          .fill MAX_OBJECTS, 0
OBJECT_ACTIVE:         .fill MAX_OBJECTS, 0
OBJECT_TYPE:           .fill MAX_OBJECTS, 0
HW_SPRITE_OFFSET:      .byte 0,2,4,6,8,10,12,14
OBJECT_SPRITE:         .fill MAX_OBJECTS, 0
OBJECT_COLOUR:         .fill MAX_OBJECTS, 0
OBJECT_BASE_COLOUR:    .fill MAX_OBJECTS, 0     // Formation colour restored after impact flashing.
OBJECT_BASE_SPRITE:    .fill MAX_OBJECTS, 0     // Immutable formation bitmap used to rebuild private health sprites.
OBJECT_HEALTH:         .fill MAX_OBJECTS, 0     // Current enemy HP; player slot is presently unused.
OBJECT_HIT_TIMER:      .fill MAX_OBJECTS, 0     // Remaining colour-flash frames after ballistic impact.
OBJECT_DEATH_TIMER:    .fill MAX_OBJECTS, 0     // Non-zero while an enemy death animation owns the active slot.
SORTED_OBJECTS:        .fill MAX_OBJECTS, $ff
SORTED_COUNT:          .byte 0

OBJECT_PATTERN:        .fill MAX_OBJECTS, 0
OBJECT_PATH_STEP:      .fill MAX_OBJECTS, 0     // Byte offset into the CURRENT stage's fragment table.
OBJECT_PATH_TIMER:     .fill MAX_OBJECTS, 0
OBJECT_VEL_X:          .fill MAX_OBJECTS, 0     // Signed current (ramped) horizontal path velocity.
OBJECT_VEL_Y:          .fill MAX_OBJECTS, 0     // Signed current (ramped) vertical path velocity.
OBJECT_ACCEL_TIMER:    .fill MAX_OBJECTS, 0     // Frames accumulated while descending before the next speed increase.
OBJECT_STAGE:          .fill MAX_OBJECTS, 0     // STAGE_INGRESS/MANOEUVRE/EGRESS: which fragment table OBJECT_PATH_STEP indexes.
OBJECT_MANOEUVRE_STEP: .fill MAX_OBJECTS, 0     // Precomputed manoeuvreFragments start offset, applied when ingress finishes.
OBJECT_EGRESS_STEP:    .fill MAX_OBJECTS, 0     // Precomputed egressFragments start offset, applied when manoeuvre finishes.
OBJECT_TARGET_VEL_X:   .fill MAX_OBJECTS, 0     // Signed horizontal velocity a segment/acceleration is easing towards.
OBJECT_TARGET_VEL_Y:   .fill MAX_OBJECTS, 0     // Signed vertical velocity a segment/acceleration is easing towards.

ENEMY_FIRE_TIMER:      .byte 0                  // Global cadence until another enemy may attempt to fire.
ENEMY_BULLET_COUNT:    .byte 0                  // Hard cap is MAX_ENEMY_BULLETS.
ENEMY_FIRE_SOURCE:     .byte 0                  // Logical enemy index preserved across bullet allocation.
ENEMY_BULLET_OBJECT:   .byte 0                  // Newly allocated projectile index for debugging/future use.
ENEMY_FIRE_SCAN_COUNT: .byte 0                  // Bounded candidate search so shooter selection always terminates.
ENEMY_AIM_DELTA_LO:    .byte 0                  // Scratch low byte of playerX - projectileX.

SPAWN_TIMER:           .byte 0
WAVE_GAP_TIMER:        .byte 0
WAVE_ENEMY_COUNT:      .byte 0
WAVE_SPAWN_INTERVAL:   .byte 0
WAVE_SPAWNED:          .byte 0
WAVE_SPAWN_X:          .byte 0
WAVE_SPAWN_X_MSB:      .byte 0              // Ninth bit permits genuine upper-right/off-screen attack entry.
WAVE_SPAWN_Y:          .byte 0
WAVE_ADD_X_VALUE:      .byte 0
WAVE_ADD_Y_VALUE:      .byte 0
WAVE_ATTACK_ID:        .byte 0              // Curated attack currently being emitted.
WAVE_INGRESS_ID:       .byte 0              // Ingress fragment ID copied into each spawned enemy.
WAVE_MANOEUVRE_ID:     .byte 0              // Manoeuvre fragment ID copied into each spawned enemy.
WAVE_EGRESS_ID:        .byte 0              // Egress fragment ID copied into each spawned enemy.
WAVE_SPRITE_INDEX:     .byte 0              // Current entry in the attack's visual sequence.
PATH_ABS_X:           .byte 0              // Main-thread scratch used by directional enemy acceleration.

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
INITIAL_OBJECT:        .fill 16, $ff    // Logical owner for each initial LIVE/BUILD hardware snapshot entry.

ASSIGN_X:              .fill 16, 0
ASSIGN_Y:              .fill 16, 0
ASSIGN_X_MSB:          .fill 16, 0
ASSIGN_SPRITE:         .fill 16, 0
ASSIGN_COLOUR:         .fill 16, 0
ASSIGN_OBJECT:         .fill 16, $ff    // Logical owner installed by each raster assignment.

GAME_STATE:            .byte 0         // Top-level state: MENU / PLAYING / GAME_OVER / ENTER_INITIALS.
ATTRACT_PAGE:          .byte 0         // 0 = title page, 1 = high-score page.
ATTRACT_TIMER:         .byte 0         // Frames left before the attract screen flips pages.
GAME_OVER_TIMER:       .byte 0         // Frames left on the GAME OVER screen.

NEW_SCORE_RANK:        .byte 0         // Sorted insert index for a qualifying score.
NAME_RANK_OFF:         .byte 0         // NEW_SCORE_RANK * 3 (first HISCORE_NAME byte).
NAME_STOP_OFF:         .byte 0         // Lowest HISCORE_NAME byte a name shift may fill.
INITIALS_CHARS:        .fill 3, 1      // The three initials being edited (screen codes 1..26).
INITIALS_SLOT:         .byte 0         // Which initial (0..2) the stick is currently editing.
INITIALS_STICK_PREV:   .byte 0         // Previous joystick reading for press-edge detection.
INITIALS_STICK_CUR:    .byte 0         // Current joystick reading (scratch).
INITIALS_EDGE:         .byte 0         // Bits that went released -> pressed this frame.

HISCORE_SEED:          .byte 0         // Running seed for placeholder-initial generation.
HS_ENTRY:              .byte 0         // Scratch: current entry index during table formatting.
HS_BUF_OFF:            .byte 0         // Scratch: current row's byte offset into HISCORE_PAGE_BUF.
HS_TMP:                .byte 0         // Scratch: multiply-by-10 partial.
HS_VAL_LO:             .byte 0         // Scratch: score being converted to decimal.
HS_VAL_HI:             .byte 0
HS_DIGIT_BASE:         .byte 0         // Scratch: buffer index of a score's first digit.
HISCORE_LO:            .fill HISCORE_COUNT, 0            // Per-entry score, low byte (kept descending).
HISCORE_HI:            .fill HISCORE_COUNT, 0            // Per-entry score, high byte.
HISCORE_NAME:          .fill HISCORE_COUNT * 3, 0        // Three initials (screen codes) per entry.
HISCORE_PAGE_BUF:      .fill HISCORE_COUNT * HISCORE_ROW_WIDTH, 32  // Pre-rendered attract-page rows.

PLAYER_HW_MASK:        .byte 0         // Current VIC hardware bit occupied by logical object 0.
PLAYER_HIT:            .byte 0         // Latched vulnerable-player collision event.
PLAYER_STATE:          .byte 0         // Alive, exploding, respawning, or terminal game-over.
PLAYER_LIVES:          .byte 0         // Ships remaining, including the currently active ship.
PLAYER_STATE_TIMER:    .byte 0         // Explosion-frame hold or respawn-invulnerability countdown.
PLAYER_EXPLOSION_FRAME:.byte 0         // Current explosion bitmap index 0-3.
PLAYER_BLINK_TIMER:    .byte 0         // Free-running respawn visibility phase.
PLAYER_FIRE_COOLDOWN_TIMER: .byte 0     // Held-fire cadence.
PLAYER_MUZZLE_TIMER:   .byte 0         // Remaining player muzzle-flash frames.

HITSCAN_X_LO:          .byte 0         // Current cannon ray 9-bit X low byte.
HITSCAN_X_MSB:         .byte 0         // Current cannon ray ninth X bit.
HITSCAN_DELTA_LO:      .byte 0         // Low byte of rayX - enemyX during intersection test.
HITSCAN_TARGET:        .byte $ff       // Logical object selected by the current ray.
HITSCAN_TARGET_Y:      .byte 0         // Y of nearest qualifying target.

HEALTH_OBJECT_INDEX:    .byte 0         // Logical enemy currently receiving a private health sprite.
HEALTH_SOURCE_SPRITE:   .byte 0         // Original sprite pointer being copied.
HEALTH_DEST_SPRITE:     .byte 0         // Private sprite pointer assigned to that logical slot.

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

SCORE_LO:              .byte 0            // 16-bit binary score, low byte.
SCORE_HI:              .byte 0            // 16-bit binary score, high byte.
SCORE_VALUE_LO:        .byte 0            // Scratch copy used by decimal HUD conversion.
SCORE_VALUE_HI:        .byte 0            // Scratch copy used by decimal HUD conversion.

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

STAR_FRAME:             .byte 0
STAR_DRAW_COLOUR:       .byte 0
STAR_X:
    .byte 2,7,12,18,25,31,37,4,10,15,22,28,34,39,6,14
STAR_Y:
    .byte 2,5,8,11,14,17,20,23,4,7,10,13,16,19,22,3
STAR_PHASE:
    .fill STAR_COUNT,0
STAR_STYLE:
    // 0=small/far, 1=medium; bit 7 enables twinkle.
    .byte $00,$81,$00,$01,$80,$01,$00,$81
    .byte $00,$01,$80,$01,$00,$81,$00,$01

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

playerFireSprite:
    .byte $0c,$3c,$30
    .byte $03,$3c,$c0
    .byte $0c,$ff,$30
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
    .byte $00                              // 64th padding byte

blankSprite:
    .fill 64, $00                          // Invisible respawn blink while object 0 remains active.

playerExplosion1:
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00,$10,$00
    .byte $00,$b8,$00
    .byte $02,$fe,$00
    .byte $03,$ef,$00
    .byte $0b,$ab,$80
    .byte $1e,$ba,$d0
    .byte $0b,$ff,$80
    .byte $02,$ee,$00
    .byte $03,$bb,$00
    .byte $0b,$ef,$80
    .byte $1e,$fe,$d0
    .byte $0b,$ab,$80
    .byte $03,$ef,$00
    .byte $02,$fe,$00
    .byte $00,$b8,$00
    .byte $00,$10,$00
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00,$00,$00
    .byte $00                              // 64th padding byte

playerExplosion2:
    .byte $00,$41,$00
    .byte $04,$00,$10
    .byte $00,$82,$00
    .byte $12,$eb,$84
    .byte $0b,$82,$e0
    .byte $0e,$3c,$b0
    .byte $68,$eb,$29
    .byte $33,$82,$cc
    .byte $22,$3c,$88
    .byte $0c,$eb,$30
    .byte $48,$be,$21
    .byte $0c,$eb,$30
    .byte $22,$3c,$88
    .byte $33,$82,$cc
    .byte $68,$eb,$29
    .byte $0e,$3c,$b0
    .byte $0b,$82,$e0
    .byte $12,$eb,$84
    .byte $00,$82,$00
    .byte $04,$00,$10
    .byte $00,$41,$00
    .byte $00                              // 64th padding byte

playerExplosion3:
    .byte $40,$00,$01
    .byte $02,$00,$80
    .byte $10,$3c,$04
    .byte $08,$c3,$20
    .byte $03,$28,$c0
    .byte $20,$82,$08
    .byte $0e,$00,$b0
    .byte $40,$3c,$01
    .byte $30,$c3,$0c
    .byte $08,$00,$20
    .byte $08,$00,$20
    .byte $30,$c3,$0c
    .byte $40,$3c,$01
    .byte $0e,$00,$b0
    .byte $20,$82,$08
    .byte $03,$28,$c0
    .byte $08,$c3,$20
    .byte $10,$3c,$04
    .byte $02,$00,$80
    .byte $40,$00,$01
    .byte $00,$00,$00
    .byte $00                              // 64th padding byte

playerExplosion4:
    .byte $04,$00,$10
    .byte $40,$00,$01
    .byte $00,$82,$00
    .byte $20,$00,$08
    .byte $03,$00,$c0
    .byte $08,$00,$20
    .byte $40,$3c,$01
    .byte $00,$00,$00
    .byte $30,$00,$0c
    .byte $02,$00,$80
    .byte $02,$00,$80
    .byte $30,$00,$0c
    .byte $00,$00,$00
    .byte $40,$3c,$01
    .byte $08,$00,$20
    .byte $03,$00,$c0
    .byte $20,$00,$08
    .byte $00,$82,$00
    .byte $40,$00,$01
    .byte $04,$00,$10
    .byte $00,$00,$00
    .byte $00                              // 64th padding byte

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

// --- Enemy projectile sprite ------------------------------------------------
// Compact 8x8-ish multicolour bolt kept at the sprite origin so the software
// collision box can remain small instead of treating the whole 24x21 cell as lethal.
enemyBulletSprite:
    .byte $3c,$00,$00
    .byte $ff,$00,$00
    .byte $ff,$00,$00
    .byte $3c,$00,$00
    .byte $3c,$00,$00
    .byte $18,$00,$00
    .byte $18,$00,$00
    .byte $00,$00,$00
    .fill 39,$00
    .byte $00                              // 64th padding byte

// --- Curated attack definitions --------------------------------------------
// Parallel tables indexed by ATTACK_* ID.  These are deliberately kept as
// plain bytes so balancing remains as easy as the old formation system.
//
// Rules:
//   * Top-entry attacks always have addY = 0.  Members may share X or fan in X.
//   * Side-entry attacks use addY > 0 so several enemies never form a long
//     horizontal raster band while entering.
//   * Side-entry attacks currently use addX = 0, but the runtime supports a
//     signed 9-bit X offset if we want it later.
//   * Movement geometry is no longer one full path per attack: each attack
//     instead names an ingress fragment, a manoeuvre fragment and an egress
//     fragment (see "Segmented movement fragments" below), chained at
//     runtime by moveEnemyPath.  Attacks 0-8 are the original families
//     re-expressed on the new fragments; 9-11 are new combinations built
//     from the very same fragment data, demonstrating the reuse the
//     segmented architecture exists for.
//
// IDs:
// 0  top -> dive -> turn -> exit upper-left
// 1  top -> dive -> turn -> exit upper-right
// 2  top -> dive -> loop -> exit left
// 3  top -> dive -> loop -> exit right
// 4  top -> dive -> loop -> exit top
// 5  upper-left  -> cross screen -> smooth U-turn -> exit upper-left
// 6  upper-right -> cross screen -> smooth U-turn -> exit upper-right
// 7  upper-left  -> cross screen -> smooth U-turn -> exit lower-left
// 8  upper-right -> cross screen -> smooth U-turn -> exit lower-right
// 9  top -> long dive (loop ingress) -> turn -> exit upper-right
// 10 upper-left  -> shallow cross (down-turn ingress) -> sharp up-turn -> exit
// 11 upper-right -> shallow cross (down-turn ingress) -> sharp up-turn -> exit

// attackEnemyCount and attackSpriteStart are declared as assembler lists so the
// compile-time guard further down can bounds-check every entry against the
// 8-entries-per-visual-set enemySpriteSequence layout.  The emitted bytes are
// identical to a plain .byte row.
.var attackEnemyCountData  = List().add(6, 6, 5, 5, 6, 6, 6, 5, 5, 6, 5, 5)
.var attackSpriteStartData = List().add(0, 8, 16, 24, 0, 8, 16, 24, 0, 8, 16, 24)

attackEnemyCount:
    .fill attackEnemyCountData.size(), attackEnemyCountData.get(i)

attackInterval:
    .byte 18,18,16,16,18,15,15,17,17,18,16,16

attackStartXLo:
    .byte 150,150,164,136,150,12,$4a,12,$4a,150,12,$4a // $014a = 330 for right-side entry.

attackStartXMsb:
    .byte 0,0,0,0,0,0,1,0,1,0,0,1

attackStartY:
    .byte 38,38,38,38,38,58,58,58,58,38,58,58

attackAddX:
    .byte 0,0,$04,$fc,0,0,0,0,0,0,0,0       // Top loop pair fans by +/-4; $fc = -4.

attackAddY:
    .byte 0,0,0,0,0,7,7,9,9,0,7,7           // NEVER stagger top entry in Y.

// Each attack names its ingress/manoeuvre/egress fragment IDs (see the
// *_ID consts alongside their fragment tables below) rather than a single
// monolithic path ID.  Declared as assembler lists (like attackEnemyCountData
// above) so the fragment-join compatibility guard further down can walk the
// exact same data used to emit these bytes, instead of a second hand-copied
// list that could silently drift out of sync.
.var attackIngressIdData = List().add(
    INGRESS_TOP_STRAIGHT_SHORT, INGRESS_TOP_STRAIGHT_SHORT,
    INGRESS_TOP_STRAIGHT_LONG,  INGRESS_TOP_STRAIGHT_LONG,  INGRESS_TOP_STRAIGHT_LONG,
    INGRESS_LEFT_DIAG_CROSS_UP, INGRESS_RIGHT_DIAG_CROSS_UP,
    INGRESS_LEFT_DIAG_CROSS_DOWN, INGRESS_RIGHT_DIAG_CROSS_DOWN,
    INGRESS_TOP_STRAIGHT_LONG,                                     // 9: reused long ingress ...
    INGRESS_LEFT_DIAG_CROSS_DOWN, INGRESS_RIGHT_DIAG_CROSS_DOWN)    // 10/11: reused shallow-cross ingress ...

.var attackManoeuvreIdData = List().add(
    MANOEUVRE_TURN_LEFT, MANOEUVRE_TURN_RIGHT,
    MANOEUVRE_LOOP_LEFT, MANOEUVRE_LOOP_RIGHT, MANOEUVRE_LOOP_TOP,
    MANOEUVRE_UTURN_UP_LEFT, MANOEUVRE_UTURN_UP_RIGHT,
    MANOEUVRE_UTURN_DOWN_LEFT, MANOEUVRE_UTURN_DOWN_RIGHT,
    MANOEUVRE_TURN_RIGHT,                                     // 9: ... feeding the tight turn-right manoeuvre.
    MANOEUVRE_UTURN_UP_LEFT, MANOEUVRE_UTURN_UP_RIGHT)        // 10/11: ... feeding the sharper up-turn manoeuvre.

.var attackEgressIdData = List().add(
    EGRESS_UPPER_LEFT, EGRESS_UPPER_RIGHT,
    EGRESS_COAST, EGRESS_COAST, EGRESS_COAST,
    EGRESS_UPPER_LEFT, EGRESS_UPPER_RIGHT,                    // 5/6: U-turn-up manoeuvres end on only a shallow
                                                               // (-1,-1)/(1,-1) tangent - the shaped egress reasserts
                                                               // the stronger (-2,-1)/(2,-1) diagonal used by the top
                                                               // turns, so both "exit upper-left/right" families leave
                                                               // the screen at the same speed instead of this one
                                                               // visibly crawling off at ~70% of the other's rate.
    EGRESS_COAST, EGRESS_COAST,
    EGRESS_UPPER_RIGHT,                                       // 9
    EGRESS_COAST, EGRESS_COAST)                               // 10/11

attackIngressId:
    .fill attackIngressIdData.size(), attackIngressIdData.get(i)
attackManoeuvreId:
    .fill attackManoeuvreIdData.size(), attackManoeuvreIdData.get(i)
attackEgressId:
    .fill attackEgressIdData.size(), attackEgressIdData.get(i)

// Four reusable visual palettes.  Attack geometry and visuals remain separate
// so stage data can later swap either independently.
attackSpriteStart:
    .fill attackSpriteStartData.size(), attackSpriteStartData.get(i)

enemySpriteSequence:
    // Visual set 0.
    .byte enemySpriteA/64, enemySpriteB/64, enemySpriteA/64, enemySpriteC/64
    .byte enemySpriteC/64, enemySpriteA/64, enemySpriteB/64, enemySpriteA/64

    // Visual set 1.
    .byte enemySpriteB/64, enemySpriteC/64, enemySpriteD/64, enemySpriteA/64
    .byte enemySpriteB/64, enemySpriteC/64, enemySpriteD/64, enemySpriteA/64

    // Visual set 2.
    .byte enemySpriteD/64, enemySpriteC/64, enemySpriteB/64, enemySpriteA/64
    .byte enemySpriteB/64, enemySpriteC/64, enemySpriteD/64, enemySpriteA/64

    // Visual set 3.
    .byte enemySpriteC/64, enemySpriteD/64, enemySpriteC/64, enemySpriteB/64
    .byte enemySpriteD/64, enemySpriteC/64, enemySpriteB/64, enemySpriteA/64
enemySpriteSequenceEnd:

enemyColourSequence:
    .byte 2, 6,10, 7, 7,10, 6, 2
    .byte 6,13, 7,10, 6,13, 7,10
    .byte 14,13,7, 2, 7,13,14, 2
    .byte 7,14, 7,10,14, 7,10, 2
enemyColourSequenceEnd:

// Cheap mapping from a four-bit CIA timer sample to twelve attack IDs.
// Uneven distribution is intentional/irrelevant for the temporary chaos
// director; real stages will choose attacks explicitly.
randomAttackMap:
    .byte 0,1,2,3,4,5,6,7,8,9,10,11,0,4,9,7

// --- Compile-time bounds guard: curated attack visual sequences -----------
// spawnEnemy reads attackEnemyCount[id] consecutive entries from
// enemySpriteSequence / enemyColourSequence, starting at attackSpriteStart[id]
// and advancing WAVE_SPRITE_INDEX once per spawn.  A visual set is 8 entries;
// the whole sequence is 4 sets = 32 entries.  These checks mirror the
// fragment-table size guards below so tuning data can never silently walk
// off the end of these parallel tables at runtime.
.const ENEMY_SPRITE_SEQUENCE_LEN = 32

.if ((enemySpriteSequenceEnd - enemySpriteSequence) != ENEMY_SPRITE_SEQUENCE_LEN) {
    .error "enemySpriteSequence is not " + toIntString(ENEMY_SPRITE_SEQUENCE_LEN) + " entries"
}
.if ((enemyColourSequenceEnd - enemyColourSequence) != ENEMY_SPRITE_SEQUENCE_LEN) {
    .error "enemyColourSequence length does not match enemySpriteSequence"
}
.if (attackEnemyCountData.size() != ATTACK_COUNT || attackSpriteStartData.size() != ATTACK_COUNT) {
    .error "attack parameter tables must have ATTACK_COUNT entries"
}

.for (var i = 0; i < ATTACK_COUNT; i++) {
    .if (attackEnemyCountData.get(i) > 8) {
        .error "attackEnemyCount[" + toIntString(i) + "] > 8 exceeds one enemySpriteSequence visual set"
    }
    .if ((attackSpriteStartData.get(i) + attackEnemyCountData.get(i)) > ENEMY_SPRITE_SEQUENCE_LEN) {
        .error "attack " + toIntString(i) + " sprite window runs past enemySpriteSequence"
    }
}

// ============================================================================
// Segmented movement fragments: ingress / manoeuvre / egress
// ============================================================================
// Every enemy attack chains three independently-reusable fragments instead of
// one monolithic canned path:
//   ingress   - how the formation enters the playfield.
//   manoeuvre - the interesting on-screen motion.
//   egress    - how the enemy leaves.
// Each stage lives in its own byte-indexed table (ingressFragments,
// manoeuvreFragments, egressFragments), so each table gets its own 256-byte
// budget instead of all paths sharing one - the old ~252/256-byte ceiling on
// total attack variety no longer applies.
//
// Segment format is unchanged: duration, signed vx, signed vy (3 bytes).
// Ingress/manoeuvre fragments end with a 0,0,0 terminator: duration zero now
// means "this fragment is finished", and moveEnemyPath hands the object off
// to its next stage (ingress->manoeuvre->egress) rather than despawning it.
// Egress fragments are still terminal and end in the original $ff coast
// marker (placeholder vx/vy, momentum preserved), exactly as before; reaching
// duration zero there (which should not normally happen) still despawns.
//
// Compatibility metadata: every fragment that can end a stage declares an
// "exit class" (which way it's travelling when it finishes) and every
// fragment that can start manoeuvre/egress declares an "entry mask" (which
// exit classes it accepts).  DIR_UP/DOWN/LEFT/RIGHT bitmasks (see near
// ATTACK_COUNT) are combined for diagonals.  A compile-time guard below
// verifies every curated attack's chain actually joins cleanly - this is
// the "cheap representation suitable for a 6502" the join-compatibility
// concept needed, with zero runtime cost, and it's the same metadata a
// future runtime director could reuse for player-aware/weighted selection.

// --- Ingress fragments -------------------------------------------------------
// (INGRESS_* IDs are declared in the top constants block.)
ingressStartOffset:
    .byte ingressTopStraightShort-ingressFragments
    .byte ingressTopStraightLong-ingressFragments
    .byte ingressLeftDiagonalCrossUp-ingressFragments
    .byte ingressRightDiagonalCrossUp-ingressFragments
    .byte ingressLeftDiagonalCrossDown-ingressFragments
    .byte ingressRightDiagonalCrossDown-ingressFragments

// Direction the enemy is travelling when each ingress fragment hands off.
// Declared as an assembler list, like the attack tables above, so the
// fragment-join compatibility guard further down can walk this exact data
// instead of a second hand-copied copy that could drift out of sync.
.var ingressExitClassData = List().add(
    DIR_DOWN,                    // ingressTopStraightShort
    DIR_DOWN,                    // ingressTopStraightLong
    DIR_DOWN | DIR_RIGHT,        // ingressLeftDiagonalCrossUp
    DIR_DOWN | DIR_LEFT,         // ingressRightDiagonalCrossUp
    DIR_RIGHT,                   // ingressLeftDiagonalCrossDown
    DIR_LEFT)                    // ingressRightDiagonalCrossDown

ingressExitClass:
    .fill ingressExitClassData.size(), ingressExitClassData.get(i)

ingressFragments:

ingressTopStraightShort:
    .byte 48,  0,  2                       // Straight dive from common top entry Y.
    .byte  0,  0,  0                       // End of fragment: hand off to the manoeuvre stage.

ingressTopStraightLong:
    .byte 30,  0,  2                       // Enter higher so a larger manoeuvre (loop) stays clear of respawn Y.
    .byte  0,  0,  0

ingressLeftDiagonalCrossUp:
    .byte 30,  2,  1                       // Enter from upper-left and cross toward the right half.
    .byte 24,  2,  2                       // Dive through centre, giving the player a useful firing window.
    .byte 18,  2,  1                       // Flatten as the formation approaches its turn point.
    .byte  0,  0,  0

ingressRightDiagonalCrossUp:
    .byte 30,$fe,  1                       // Enter from upper-right and cross toward the left half.
    .byte 24,$fe,  2                       // Dive through centre, mirroring the left-entry attack.
    .byte 18,$fe,  1                       // Flatten as the formation approaches its turn point.
    .byte  0,  0,  0

ingressLeftDiagonalCrossDown:
    .byte 28,  2,  1                       // Enter from upper-left and cross toward the right half.
    .byte 22,  2,  1                       // Keep this variant shallower before the turn.
    .byte 16,  2,  0                       // Level out near the far side.
    .byte  0,  0,  0

ingressRightDiagonalCrossDown:
    .byte 28,$fe,  1                       // Enter from upper-right and cross toward the left half.
    .byte 22,$fe,  1                       // Keep this mirrored variant shallower before the turn.
    .byte 16,$fe,  0                       // Level out near the far side.
    .byte  0,  0,  0

ingressFragmentsEnd:
.if ((ingressFragmentsEnd - ingressFragments) > 256) {
    .error "ingressFragments exceeds one-byte OBJECT_PATH_STEP range"
}

// --- Manoeuvre fragments -----------------------------------------------------
// (MANOEUVRE_* IDs are declared in the top constants block.)
manoeuvreStartOffset:
    .byte manoeuvreTurnLeft-manoeuvreFragments
    .byte manoeuvreTurnRight-manoeuvreFragments
    .byte manoeuvreLoopLeft-manoeuvreFragments
    .byte manoeuvreLoopRight-manoeuvreFragments
    .byte manoeuvreLoopTop-manoeuvreFragments
    .byte manoeuvreUTurnUpLeft-manoeuvreFragments
    .byte manoeuvreUTurnUpRight-manoeuvreFragments
    .byte manoeuvreUTurnDownLeft-manoeuvreFragments
    .byte manoeuvreUTurnDownRight-manoeuvreFragments

// Which ingress exit classes each manoeuvre can cleanly continue from, and
// which direction it's travelling when it hands off to egress.  Declared as
// assembler lists for the same reason as ingressExitClassData above.
.var manoeuvreEntryMaskData = List().add(
    DIR_DOWN,                    // manoeuvreTurnLeft
    DIR_DOWN,                    // manoeuvreTurnRight
    DIR_DOWN,                    // manoeuvreLoopLeft
    DIR_DOWN,                    // manoeuvreLoopRight
    DIR_DOWN,                    // manoeuvreLoopTop
    DIR_DOWN | DIR_RIGHT,        // manoeuvreUTurnUpLeft
    DIR_DOWN | DIR_LEFT,         // manoeuvreUTurnUpRight
    DIR_RIGHT,                   // manoeuvreUTurnDownLeft
    DIR_LEFT)                    // manoeuvreUTurnDownRight

.var manoeuvreExitClassData = List().add(
    DIR_UP | DIR_LEFT,           // manoeuvreTurnLeft
    DIR_UP | DIR_RIGHT,          // manoeuvreTurnRight
    DIR_UP | DIR_LEFT,           // manoeuvreLoopLeft
    DIR_UP | DIR_RIGHT,          // manoeuvreLoopRight
    DIR_UP,                      // manoeuvreLoopTop
    DIR_UP | DIR_LEFT,           // manoeuvreUTurnUpLeft
    DIR_UP | DIR_RIGHT,          // manoeuvreUTurnUpRight
    DIR_DOWN | DIR_LEFT,         // manoeuvreUTurnDownLeft
    DIR_DOWN | DIR_RIGHT)        // manoeuvreUTurnDownRight

manoeuvreEntryMask:
    .fill manoeuvreEntryMaskData.size(), manoeuvreEntryMaskData.get(i)
manoeuvreExitClass:
    .fill manoeuvreExitClassData.size(), manoeuvreExitClassData.get(i)

manoeuvreFragments:

manoeuvreTurnLeft:
    .byte  7,$ff,  2                       // Begin curving down-left.
    .byte  7,$fe,  1                       // Increase horizontal component.
    .byte  7,$fe,  0                       // Level out.
    .byte  5,$fe,$ff                       // Hook upward through the turn.
    .byte  0,  0,  0

manoeuvreTurnRight:
    .byte  7,  1,  2                       // Begin curving down-right.
    .byte  7,  2,  1                       // Increase horizontal component.
    .byte  7,  2,  0                       // Level out.
    .byte  5,  2,$ff                       // Hook upward through the turn.
    .byte  0,  0,  0

manoeuvreLoopLeft:
    .byte  9,  2,  1                       // First loop: arc down-right.
    .byte  9,  2,  0                       // First loop: right.
    .byte  9,  1,$fe                       // First loop: arc up-right.
    .byte  9,$ff,$fe                       // First loop: arc up-left.
    .byte  9,$fe,  0                       // First loop: left.
    .byte  9,$fe,  1                       // First loop: arc down-left.
    .byte  9,$ff,  2                       // First loop: bottom-left arc.
    .byte  9,  1,  2                       // Complete one full loop still moving down-right.
    .byte  9,  2,  1                       // Continue into the second loop instead of reversing.
    .byte  9,  2,  0                       // Carry around the right-hand side.
    .byte  9,  1,$fe                       // Climb through the upper-right quadrant.
    .byte  9,$ff,$fe                       // Finish roughly 1.5 loops later on a natural up-left tangent.
    .byte  0,  0,  0

manoeuvreLoopRight:
    .byte  9,$fe,  1                       // First loop: arc down-left.
    .byte  9,$fe,  0                       // First loop: left.
    .byte  9,$ff,$fe                       // First loop: arc up-left.
    .byte  9,  1,$fe                       // First loop: arc up-right.
    .byte  9,  2,  0                       // First loop: right.
    .byte  9,  2,  1                       // First loop: arc down-right.
    .byte  9,  1,  2                       // First loop: bottom-right arc.
    .byte  9,$ff,  2                       // Complete one full loop still moving down-left.
    .byte  9,$fe,  1                       // Continue into the second loop instead of reversing.
    .byte  9,$fe,  0                       // Carry around the left-hand side.
    .byte  9,$ff,$fe                       // Climb through the upper-left quadrant.
    .byte  9,  1,$fe                       // Finish roughly 1.5 loops later on a natural up-right tangent.
    .byte  0,  0,  0

manoeuvreLoopTop:
    .byte  9,  2,  1                       // First loop: arc down-right.
    .byte  9,  2,  0                       // First loop: right.
    .byte  9,  1,$fe                       // First loop: arc up-right.
    .byte  9,$ff,$fe                       // First loop: arc up-left.
    .byte  9,$fe,  0                       // First loop: left.
    .byte  9,$fe,  1                       // First loop: arc down-left.
    .byte  9,$ff,  2                       // First loop: bottom-left arc.
    .byte  9,  1,  2                       // Complete one full loop still moving down-right.
    .byte  9,  2,  1                       // Continue naturally into the second loop.
    .byte  9,  2,  0                       // Carry around the right-hand side.
    .byte  9,  1,$fe                       // Climb through the upper-right quadrant.
    .byte  9,  0,$fe                       // Ease onto a vertical upward tangent rather than snapping to it.
    .byte  0,  0,  0

manoeuvreUTurnUpLeft:
    .byte  8,  2,  0                       // Begin the near-180 turn while still travelling right.
    .byte  8,  1,$ff                       // Arc upward and bleed off horizontal speed.
    .byte 10,$fe,$ff                       // Complete the reversal onto the same-speed up-left tangent the top-turn
                                            // family exits on ($fe,$ff = -2,-1); held for a full 10 frames, not just
                                            // the ~1 frame the egress ease would otherwise need to catch up from -1.
    .byte  0,  0,  0

manoeuvreUTurnUpRight:
    .byte  8,$fe,  0                       // Begin the near-180 turn while still travelling left.
    .byte  8,$ff,$ff                       // Arc upward and bleed off horizontal speed.
    .byte 10,  2,$ff                       // Mirror: same-speed up-right tangent (2,-1), held for the full 10 frames.
    .byte  0,  0,  0

manoeuvreUTurnDownLeft:
    .byte  8,  2,  0                       // Hold the outward tangent briefly before curving back.
    .byte  8,  1,  1                       // Arc downward while shedding horizontal speed.
    .byte 10,$ff,  1                       // Reverse onto a shallow down-left tangent.
    .byte  0,  0,  0

manoeuvreUTurnDownRight:
    .byte  8,$fe,  0                       // Hold the outward tangent briefly before curving back.
    .byte  8,$ff,  1                       // Arc downward while shedding horizontal speed.
    .byte 10,  1,  1                       // Reverse onto a shallow down-right tangent.
    .byte  0,  0,  0

manoeuvreFragmentsEnd:
.if ((manoeuvreFragmentsEnd - manoeuvreFragments) > 256) {
    .error "manoeuvreFragments exceeds one-byte OBJECT_PATH_STEP range"
}

// --- Egress fragments --------------------------------------------------------
// (EGRESS_* IDs are declared in the top constants block.)
egressStartOffset:
    .byte egressCoast-egressFragments
    .byte egressUpperLeft-egressFragments
    .byte egressUpperRight-egressFragments

// Which manoeuvre exit classes each egress can cleanly continue from.
// Declared as an assembler list for the same reason as ingressExitClassData.
.var egressEntryMaskData = List().add(
    DIR_ANY,                     // egressCoast: momentum-only, joins from anywhere.
    DIR_UP | DIR_LEFT,           // egressUpperLeft
    DIR_UP | DIR_RIGHT)          // egressUpperRight

egressEntryMask:
    .fill egressEntryMaskData.size(), egressEntryMaskData.get(i)

egressFragments:

egressCoast:
    .byte $ff, 0,  0                       // Coast on the velocity already established by the manoeuvre.

egressUpperLeft:
    .byte  6,$fe,$ff                       // Leave on a shallow up-left tangent rather than a flat row.
    .byte $ff, 0,  0                       // Coast on that inherited up-left exit vector.

egressUpperRight:
    .byte  6,  2,$ff                       // Leave on a shallow up-right tangent rather than a flat row.
    .byte $ff, 0,  0                       // Coast on that inherited up-right exit vector.

egressFragmentsEnd:
.if ((egressFragmentsEnd - egressFragments) > 256) {
    .error "egressFragments exceeds one-byte OBJECT_PATH_STEP range"
}

// --- Compile-time bounds guard: fragment-join compatibility ----------------
// Verifies every curated attack's ingress->manoeuvre->egress chain actually
// joins cleanly (exit class shares a bit with the next fragment's entry
// mask), so a bad hand-authored combination fails the build instead of
// merely looking wrong at runtime.  Reuses the exact *Data lists that emitted
// the runtime tables above, rather than a second hand-copied list.
.for (var a = 0; a < ATTACK_COUNT; a++) {
    .var ingressId = attackIngressIdData.get(a)
    .var manoeuvreId = attackManoeuvreIdData.get(a)
    .var egressId = attackEgressIdData.get(a)

    .var ingressExit = ingressExitClassData.get(ingressId)
    .var manoeuvreEntry = manoeuvreEntryMaskData.get(manoeuvreId)
    .var manoeuvreExit = manoeuvreExitClassData.get(manoeuvreId)
    .var egressEntry = egressEntryMaskData.get(egressId)

    .if ((ingressExit & manoeuvreEntry) == 0) {
        .error "attack " + toIntString(a) + ": ingress " + toIntString(ingressId) + " does not join manoeuvre " + toIntString(manoeuvreId)
    }
    .if ((manoeuvreExit & egressEntry) == 0) {
        .error "attack " + toIntString(a) + ": manoeuvre " + toIntString(manoeuvreId) + " does not join egress " + toIntString(egressId)
    }
}

// --- Private per-object health-bar sprite RAM -------------------------------
// Object 0 is the player and does not use its slot, but reserving all 16 keeps
// pointer calculation trivial: private pointer = HEALTH_SPRITE_BASE_PTR + objectID.
* = HEALTH_SPRITE_BASE
healthSpritePool:
    .fill MAX_OBJECTS * 64, $00
HEALTH_SPRITE_POOL_END:
.if (HEALTH_SPRITE_POOL_END > $4000) {
    .error "Health sprite pool exceeds VIC bank 0"
}
