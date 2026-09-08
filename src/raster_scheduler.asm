.filenamespace test
// Shared PAL raster-event dispatcher. See docs/fixed-hud-codex-worklog.md.
// All sprite payloads/masks read by the IRQ belong to LIVE_PLAN. Frame-zero
// is an explicit next-physical-frame event, never an accidentally missed compare.
* = $6000
.const RASTER_EVENT_FRAME = 0
.const RASTER_EVENT_SPRITES = 1
.const RASTER_EVENT_DISPLAY = 2
.const RASTER_DISPLAY_LINE = 56              // After HUD badline55, before the fixed display transition.

// ============================================================================
// BOTTOM-BORDER HUD EXPERIMENT - PHASE 1 "PROVE THE BORDER" (quarantined)
// See /reports/bottom-border-hud-phase1-border-proof-report.md.
// Set BORDER_PROOF_ENABLE = 0 (in variables.asm) to compile the engine exactly
// as before this experiment (every block below is guarded; nothing else in this
// file changes behaviour when it is 0). This is NOT the HUD: it opens the lower
// vertical border via a Slap-Fight-style RSEL 1->0 flip and, only when hardware
// sprite slot BORDER_MARKER_SLOT is provably unused by gameplay this frame
// ($D015 bit clear), shows one static diagnostic marker sprite in the opened
// region.
// ============================================================================
.const RASTER_EVENT_BORDER  = 3
.const RASTER_BORDER_LINE   = 240           // IRQ compare; the hook then polls to 243 / 250.
.const BORDER_MARKER_SLOT   = 7             // Diagnostic only; see report for why this slot is safe.
.const BORDER_MARKER_X      = 160
.const BORDER_MARKER_Y      = 252           // Body raster 252..272, clearly below the RSEL=1 aperture (<=250).
.const BORDER_MARKER_COLOUR = 1             // Solid white block ($D02E for slot 7; bitmap is all %11).

initRasterScheduler:
    lda #1
    sta $dc0d                               // Suspend KERNAL timer-A IRQ only; the timer/random source keeps running.
    lda #0
    ldx #RASTER_STATE_END - RASTER_STATE_BEGIN - 1
!clear:
    sta RASTER_STATE_BEGIN,x
    dex
    bpl !clear-
    lda #1
    sta RASTER_DISPLAY_PENDING
#if BORDER_PROOF_ENABLE
    sta RASTER_BORDER_PENDING
#endif
    rts

// Publish readiness only after observing raster high with IRQs masked. This
// closes the race where a long IRQ crosses frame zero before readiness is set.
waitForGameFrame:
!high:
    sei
    lda VIC_CONTROL_1
    bmi !ready+
    cli
    jmp !high-
!ready:
    lda #1
    sta RASTER_PRESENT_READY
    cli
!low:
    lda VIC_CONTROL_1
    bmi !low-
    rts

publishRasterPlan:
    lda #0
    sta RASTER_PRESENT_READY
    lda #<multiplexIRQ
    sta IRQ_VECTOR
    lda #>multiplexIRQ
    sta IRQ_VECTOR + 1
    lda RASTER_DISPLAY_FINE                 // publishRasterPlan runs every frame (armFirstBatch) at ~line 17,
    ora #GAMEPLAY_D011_BASE                 // before the first badline: install the SAME whole-frame display
    sta VIC_CONTROL_1                        // state as rasterFrameReset (RSEL=1, DEN=1, YSCROL=presented fine;
                                            // compare high always 0) so it never clobbers the fine phase.
    lda #1
    sta IRQ_STATUS
    lda IRQ_ENABLE
    ora #1
    sta IRQ_ENABLE
    jsr startLiveRasterPlan
    jmp dispatchRasterEvents

startLiveRasterPlan:
    lda #0
    sta BATCH_INDEX
    sta RASTER_ASSIGNMENTS_DONE
    sta RASTER_EXPECTED_ASSIGNMENTS
    ldy LIVE_PLAN
    sty RASTER_BATCH_OFFSET
    lda BATCH_COUNT,y
    clc
    adc LIVE_PLAN
    sta RASTER_BATCH_END
    lda BATCH_COUNT,y
    beq !done+
    ldx RASTER_BATCH_END
    dex
    lda BATCH_FIRST_ASSIGN,x
    clc
    adc BATCH_ASSIGN_COUNT,x
    sta RASTER_EXPECTED_ASSIGNMENTS
!done:
    rts

rasterIRQ:
    lda IRQ_ENABLE
    and #1
    beq !cia+
    lda IRQ_STATUS
    and #1
    bne !vic+
!cia:
    jmp $ea31                               // CIA timer/keyboard service retains its normal lifecycle.
!vic:
    lda #1
    sta IRQ_STATUS                          // Acknowledge before chaining, never erase the next event's latch.
    lda RASTER_EVENT
    beq rasterFrameReset
    cmp #RASTER_EVENT_DISPLAY
    beq !display+
#if BORDER_PROOF_ENABLE
    cmp #RASTER_EVENT_BORDER
    beq !border+
#endif
    jsr applyLiveRasterBatch
    jmp !next+
#if BORDER_PROOF_ENABLE
!border:
    jsr borderOpenHook
    jmp !next+
#endif
!display:
    jsr rasterDisplayHook
!next:
    jsr dispatchRasterEvents
    jmp $ea81                               // VIC events do not run a second full KERNAL service.

rasterFrameReset:
    // Phase 1.5: establish the whole-frame RSEL=1 display state at line 0, before
    // the line-51 top border/display compare. YSCROL = the presented fine phase
    // (RASTER_DISPLAY_FINE, published by applyFineScroll) so the entire visible
    // character field — matrix rows 0..24 — scrolls uniformly with no mid-frame
    // $D011 split. This is also the RSEL 0->1 restore after borderOpenHook's late
    // RSEL 1->0 lower-border dodge. DEN=1, RSEL=1, raster-compare MSB stays 0.
    lda RASTER_DISPLAY_FINE
    ora #GAMEPLAY_D011_BASE
    sta VIC_CONTROL_1                        // Every physical frame, including replay with main still building.
    lda RASTER_EXPECTED_ASSIGNMENTS
    sta RASTER_LAST_EXPECTED
    cmp RASTER_ASSIGNMENTS_DONE
    beq !complete+
    inc RASTER_INCOMPLETE_FRAMES
    bne !complete+
    inc RASTER_INCOMPLETE_FRAMES + 1
!complete:
    lda RASTER_ASSIGNMENTS_DONE
    sta RASTER_LAST_DONE
    inc RASTER_FRAME
    bne !epoch+
    inc RASTER_FRAME + 1
!epoch:
    lda #0
    sta RASTER_EXPECTED_ASSIGNMENTS
    sta RASTER_ASSIGNMENTS_DONE
    lda #1
    sta RASTER_DISPLAY_PENDING
#if BORDER_PROOF_ENABLE
    sta RASTER_BORDER_PENDING               // Re-arm the terminal border event every physical frame.
#endif
    lda RASTER_PRESENT_READY
    beq !replay+
    // Main is already waiting at this boundary. It will publish LIVE before
    // the first gameplay batch. Keep the unconditional display/reset chain.
    ldy LIVE_PLAN
    lda BATCH_COUNT,y
    sta BATCH_INDEX
    clc
    adc LIVE_PLAN
    sta RASTER_BATCH_OFFSET
    sta RASTER_BATCH_END
    jmp !next+
!replay:
    // renderSprites predates IRQ replay and uses main scratch. Preserve it;
    // BUILD may be interrupted anywhere. CPU registers are saved by KERNAL.
    lda TEMP_OBJECT
    pha
    lda TEMP_MSB
    pha
    lda TEMP_SORT_Y
    pha
    lda TEMP_OBJECT_Y
    pha
    lda TEMP_Y_REG
    pha
    jsr renderSprites
    pla
    sta TEMP_Y_REG
    pla
    sta TEMP_OBJECT_Y
    pla
    sta TEMP_SORT_Y
    pla
    sta TEMP_MSB
    pla
    sta TEMP_OBJECT
    jsr startLiveRasterPlan
    inc RASTER_REPLAY_FRAMES
    bne !next+
    inc RASTER_REPLAY_FRAMES + 1
!next:
    jsr dispatchRasterEvents
    jmp $ea81

// Merge the fixed display hook with the next ordinary batch. A future compare
// needs >=3 raster lines of lead for the programming sequence, including DMA.
// Near targets are waited for, so a slot is never reused before its release.
// Past targets are serviced immediately in this physical frame.
dispatchRasterEvents:
!select:
    ldx RASTER_BATCH_OFFSET
    cpx RASTER_BATCH_END
    bcs !noBatch+
    lda BATCH_RASTER,x
    sta RASTER_TARGET
    lda RASTER_DISPLAY_PENDING
    beq !sprite+
    lda #RASTER_DISPLAY_LINE
    cmp RASTER_TARGET
    bcc !display+
!sprite:
    lda #RASTER_EVENT_SPRITES
    sta RASTER_EVENT
    jmp !current+
!noBatch:
    lda RASTER_DISPLAY_PENDING
    bne !display+
#if BORDER_PROOF_ENABLE
    lda RASTER_BORDER_PENDING               // Terminal border event: after every sprite batch AND the
    bne !border+                            // display hook, before the epoch/frame-zero transition.
#endif
    // Explicit epoch transition: all events are finished; compare0 belongs
    // to the next physical frame. No gameplay compare is allowed this wrap.
    lda #RASTER_EVENT_FRAME
    sta RASTER_EVENT
    sta RASTER
    rts
#if BORDER_PROOF_ENABLE
!border:
    lda #RASTER_BORDER_LINE
    sta RASTER_TARGET
    lda #RASTER_EVENT_BORDER
    sta RASTER_EVENT
    jmp !current+
#endif
!display:
    lda #RASTER_DISPLAY_LINE
    sta RASTER_TARGET
    lda #RASTER_EVENT_DISPLAY
    sta RASTER_EVENT
!current:
    lda VIC_CONTROL_1
    bmi !due+                               // All service targets are <256.
    lda RASTER
    cmp RASTER_TARGET
    bcs !due+
    clc
    adc #3
    bcs !near+
    cmp RASTER_TARGET
    bcs !near+
    lda RASTER_TARGET
    sta RASTER                              // At least four lines ahead of the sampled beam.
    rts
!near:
    lda VIC_CONTROL_1
    bmi !due+
    lda RASTER
    cmp RASTER_TARGET
    bcc !near-
!due:
    inc RASTER_CATCHUPS
    bne !service+
    inc RASTER_CATCHUPS + 1
!service:
    lda RASTER_EVENT
    cmp #RASTER_EVENT_DISPLAY
    beq !hook+
#if BORDER_PROOF_ENABLE
    cmp #RASTER_EVENT_BORDER
    beq !borderHook+
#endif
    jsr applyLiveRasterBatch
    jmp !select-
#if BORDER_PROOF_ENABLE
!borderHook:
    jsr borderOpenHook
    jmp !select-
#endif
!hook:
    jsr rasterDisplayHook
    jmp !select-

// Phase 1.5: the legacy RSEL=0 HUD/terrain $D011 split is retired. The whole
// visible field now scrolls uniformly with YSCROL=fine installed at line 0 by
// rasterFrameReset (matrix rows 0..24; rows 0 and 24 are blank $D021 spacers),
// so the display raster event has no mid-frame work. It is kept as a scheduled
// no-op — the dispatcher plumbing (event merge with the next sprite batch) is
// deliberately left intact so the sprite scheduler is not touched — that simply
// consumes RASTER_DISPLAY_PENDING at ~raster 56. The invalid BMM+ECM separator,
// the $11/$71/$70|fine/$77/$10|fine write chain, rasterHblankDelay and the HUD
// polling page-cross guards are all removed. RASTER_DISPLAY_NORMAL and
// RASTER_DISPLAY_LATE remain declared (always 0) for capture-tool symbol parity.
rasterDisplayHook:
    lda #0
    sta RASTER_DISPLAY_PENDING
rasterDisplayRestored:
rasterBadlineRestored:
    rts

#if BORDER_PROOF_ENABLE
// ============================================================================
// borderOpenHook - PHASE 1.5 terminal event. Fires from an IRQ compare at
// RASTER_BORDER_LINE (240). Two jobs, in order:
//
//   1. (diagnostic) if hardware slot BORDER_MARKER_SLOT is NOT enabled for
//      gameplay this frame ($D015 bit clear -> renderSprites gave the frame
//      <8 initial sprites, so the mux never touches this slot), program it as
//      one static solid marker in the opened lower border. If the bit IS set,
//      a gameplay sprite owns the slot right now (its body may still be
//      DMAing) -> leave it completely alone; the marker simply blinks out for
//      that frame. No HUD_SAFE_RASTER, no handoff, no reservation, no limit
//      change. renderSprites rewrites $D015 from the LIVE plan every frame, so
//      the marker's enable bit cannot leak into a gameplay frame that needs 8.
//      Same conditions as the Phase-1 marker so the deep-border corruption
//      result is directly comparable.
//
//   2. (the proof) Lower-border open, single late RSEL 1->0 dodge. Gameplay is
//      now genuine RSEL=1 throughout (rasterFrameReset installs RSEL=1 |
//      YSCROL=fine at line 0), so the RSEL=0 close compare at raster 247 is
//      already irrelevant. Poll to ~raster 250 and clear RSEL (bit 3) before
//      the RSEL=1 close compare at raster 251 -> that compare is missed too ->
//      the vertical border FF is never set this frame -> the lower border stays
//      open into the overscan region (and, as a single-FF consequence, the top
//      border also stays open above raster 51). rasterFrameReset restores
//      RSEL=1 at the next line 0, before the line-51 top compare. There is NO
//      Phase-1-style RSEL 0->1 setup write. Read-modify-write of $D011 keeps
//      YSCROL / DEN / BMM / ECM exactly; only bit 3 moves. No ECM. The write
//      lands in the blank-row-24 / border region (raster ~250) so its exact
//      cycle is not visible-pixel critical.
// ============================================================================
borderOpenHook:
    lda #0
    sta RASTER_BORDER_PENDING

    lda SPRITE_ENABLE
    and #%10000000                          // Slot 7 already live for gameplay this frame?
    bne !skipMarker+
    lda #BORDER_MARKER_SPRITE / 64
    sta HW_SPRITE_POINTER + BORDER_MARKER_SLOT
    lda #BORDER_MARKER_COLOUR
    sta HW_SPRITE_COLOUR + BORDER_MARKER_SLOT
    lda #BORDER_MARKER_X
    sta SPR_X + BORDER_MARKER_SLOT * 2
    lda #BORDER_MARKER_Y
    sta SPR_Y + BORDER_MARKER_SLOT * 2
    lda SPRITE_OVERFLOW_REGISTER
    and #%01111111                          // Marker X < 256.
    sta SPRITE_OVERFLOW_REGISTER
    lda SPRITE_ENABLE
    ora #%10000000
    sta SPRITE_ENABLE
!skipMarker:

#if GAMEPLAY_BOTTOM_EXTEND
    // Part-D asymmetric bottom-extend candidate (GAMEPLAY_RSEL = 0 only).
!wait242:
    ldx RASTER
    cpx #242
    bcc !wait242-
    lda VIC_CONTROL_1
    ora #%00001000                          // RSEL 0 -> 1 before the raster-247 RSEL=0 close compare.
    sta VIC_CONTROL_1
!wait252:
    ldx RASTER
    cpx #252
    bcc !wait252-
    lda VIC_CONTROL_1
    and #%11110111                          // RSEL 1 -> 0 AFTER the raster-251 RSEL=1 close compare (FF set at 251).
    sta VIC_CONTROL_1                        // => aperture 55..250; next-frame top compare is still RSEL=0's line 55.
borderOpenRestored:
    rts
#else
!wait250:
    ldx RASTER
    cpx #250
    bcc !wait250-
    lda VIC_CONTROL_1
    and #%11110111                          // GAMEPLAY_RSEL=1: RSEL 1 -> 0 before the raster-251 close -> border open.
    sta VIC_CONTROL_1                        // GAMEPLAY_RSEL=0: no-op (bit already clear); border closes normally at 247.
borderOpenRestored:
    rts
#endif
#endif

// The assignment payload/order is unchanged. Final batch masks are prepared
// in BUILD instead of repeatedly recalculated in the time-critical IRQ loop.
applyLiveRasterBatch:
    lda VIC_SPRITE_COLLISION                // Fast no-player-hit path; preserve the existing hit tests.
    and PLAYER_HW_MASK
    beq !noHit+
    jsr checkCapturedPlayerCollision
!noHit:
    ldx RASTER_BATCH_OFFSET
    lda BATCH_FIRST_ASSIGN,x
    clc
    adc LIVE_PLAN
    tay
    clc
    adc BATCH_ASSIGN_COUNT,x
    sta IRQ_ASSIGN_END
!assignment:
    ldx ASSIGN_SLOT,y
    lda ASSIGN_SPRITE,y
    sta HW_SPRITE_POINTER,x
    lda ASSIGN_COLOUR,y
    sta HW_SPRITE_COLOUR,x
    txa
    asl
    tax
    lda ASSIGN_X,y
    sta SPR_X,x
    lda ASSIGN_Y,y
    sta SPR_Y,x
rasterAssignmentApplied:
    inc RASTER_ASSIGNMENTS_DONE             // Trace this label to verify each assignment's physical frame.
    iny
    cpy IRQ_ASSIGN_END
    bne !assignment-
    ldx RASTER_BATCH_OFFSET
    lda BATCH_X_MSB_MASK,x
    sta SPRITE_OVERFLOW_REGISTER
    lda BATCH_PLAYER_MASK,x
    sta PLAYER_HW_MASK
rasterBatchMasksApplied:
    inc BATCH_INDEX
    inc RASTER_BATCH_OFFSET
    rts

// BUILD helpers. They never run from the IRQ and do not change slot choice.
beginRasterPlanMasks:
    lda #0
    sta SCHED_PLAYER_MASK
    sta SCHED_X_MSB_MASK
    ldx #0
!slot:
    ldy BUILD_PLAN
    txa
    cmp RENDER_COUNT,y
    bcs !done+
    clc
    adc BUILD_PLAN
    tay
    lda INITIAL_OBJECT,y
    bne !x+
    lda HW_BIT_MASK,x
    sta SCHED_PLAYER_MASK
!x:
    lda INITIAL_X_MSB,y
    beq !next+
    lda SCHED_X_MSB_MASK
    ora HW_BIT_MASK,x
    sta SCHED_X_MSB_MASK
!next:
    inx
    cpx #8
    bcc !slot-
!done:
    rts

extendRasterPlanMasks:
    txa
    tay                                     // Buffered assignment index.
    ldx ASSIGN_SLOT,y
    lda SCHED_PLAYER_MASK
    and HW_CLEAR_MASK,x
    sta SCHED_PLAYER_MASK
    lda ASSIGN_OBJECT,y
    bne !x+
    lda HW_BIT_MASK,x
    sta SCHED_PLAYER_MASK
!x:
    lda SCHED_X_MSB_MASK
    and HW_CLEAR_MASK,x
    sta SCHED_X_MSB_MASK
    lda ASSIGN_X_MSB,y
    beq !done+
    lda SCHED_X_MSB_MASK
    ora HW_BIT_MASK,x
    sta SCHED_X_MSB_MASK
!done:
    rts

// Separate allocation leaves the protected $2000..$23ff state layout intact.
RASTER_STATE_BEGIN:
RASTER_EVENT:                  .byte 0
RASTER_TARGET:                 .byte 0
RASTER_PRESENT_READY:          .byte 0
RASTER_DISPLAY_PENDING:        .byte 0
#if BORDER_PROOF_ENABLE
RASTER_BORDER_PENDING:         .byte 0        // Phase-1 bottom-border experiment; see borderOpenHook.
#endif
RASTER_EXPECTED_ASSIGNMENTS:   .byte 0
RASTER_ASSIGNMENTS_DONE:        .byte 0
RASTER_LAST_EXPECTED:          .byte 0
RASTER_LAST_DONE:              .byte 0
RASTER_FRAME:                  .word 0
RASTER_INCOMPLETE_FRAMES:      .word 0
RASTER_REPLAY_FRAMES:          .word 0
RASTER_CATCHUPS:               .word 0
RASTER_DISPLAY_LATE:           .byte 0
RASTER_BATCH_OFFSET:           .byte 0
RASTER_BATCH_END:              .byte 0
RASTER_DISPLAY_FINE:           .byte 0
RASTER_DISPLAY_NORMAL:         .byte 0
SCHED_PLAYER_MASK:             .byte 0
SCHED_X_MSB_MASK:              .byte 0
BATCH_PLAYER_MASK:             .fill 16, 0
BATCH_X_MSB_MASK:              .fill 16, 0
// Top-clipped sprite bookkeeping (see buildClippedInitialSprite in main.asm).
// Zeroed here at game start; CLIP_SHADOW_PTR=0 means the matching pool slot
// does not currently mirror a straddler bitmap.
CLIP_DEPTH:                    .byte 0
CLIP_DEPTH_BYTES:              .byte 0
CLIP_OLD_BYTES:                .byte 0
CLIP_FULL_BUDGET:              .byte 0
CLIP_SHADOW_PTR:               .fill 16, 0
CLIP_SHADOW_D:                 .fill 16, 0
RASTER_STATE_END:
.if (RASTER_STATE_END - RASTER_STATE_BEGIN > 128) {
    .error "Raster state clear loop exceeds signed X range"
}
.if (* > $6600) {
    .error "Raster dispatcher exceeds its $6000-$65ff allocation (the metatile stage data now begins at $6600)"
}
