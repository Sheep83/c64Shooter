.filenamespace test
// Shared PAL raster-event dispatcher. See docs/fixed-hud-codex-worklog.md.
// All sprite payloads/masks read by the IRQ belong to LIVE_PLAN. Frame-zero
// is an explicit next-physical-frame event, never an accidentally missed compare.
* = $6000
.const RASTER_EVENT_FRAME = 0
.const RASTER_EVENT_SPRITES = 1
.const RASTER_EVENT_DISPLAY = 2
#if HUD_PROOF_ENABLE
.const RASTER_DISPLAY_LINE = HUD_HANDOFF_RASTER   // repurposed: the HUD->gameplay slot handoff fires here.
#else
.const RASTER_DISPLAY_LINE = 56              // no-op display event (Phase 1.5).
#endif

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
#if SCROLL_EDGE_MASK
.const RASTER_EVENT_MASK    = 4             // Stage 5A review: aperture-open as a first-class raster event.
#endif
.const RASTER_BORDER_LINE   = 240           // IRQ compare; the hook then polls to 243 / 250.
.const BORDER_MARKER_SLOT   = 7             // Diagnostic only; see report for why this slot is safe.
.const BORDER_MARKER_X      = 160
.const BORDER_MARKER_Y      = 252           // Body raster 252..272, clearly below the RSEL=1 aperture (<=250).
.const BORDER_MARKER_COLOUR = 1             // Solid white block ($D02E for slot 7; bitmap is all %11).

initRasterScheduler:
#if SCROLL_EDGE_MASK
    // Stage 5B: ESTABLISH the gameplay band here, at the single gameplay-entry
    // point (called only from startGame), so the very first presented frame is
    // already masked. publishRasterPlan only PRESERVES the band, and on frame 1
    // it can run before the first rasterFrameReset -- without this the first
    // frame of every game would render with the edges unmasked. endGame clears
    // the bit again, so ownership stays strictly inside gameplay.
    lda VIC_CONTROL_1
    ora #EDGE_MASK_D011_BAND
    and #%01111111                          // never write the raster-compare MSB
    sta VIC_CONTROL_1
#endif
    lda #1
    sta $dc0d                               // Suspend KERNAL timer-A IRQ only; the timer/random source keeps running.
    lda #0
    ldx #RASTER_STATE_END - RASTER_STATE_BEGIN - 1
!clear:
    sta RASTER_STATE_BEGIN,x
    dex
    bpl !clear-
#if SCROLL_EDGE_MASK
    lda #2                                  // 2 = HUD handoff still due, 1 = aperture-open still due, 0 = done.
    sta RASTER_DISPLAY_PENDING
    lda #1
#else
    lda #1
    sta RASTER_DISPLAY_PENDING
#endif
#if BORDER_PROOF_ENABLE
    sta RASTER_BORDER_PENDING
#endif
#if BORDER_FORENSIC
    lda #0
    sta FORENSIC_HEAD
    ldx #127
!forclr:
    sta FORENSIC_RING,x
    dex
    bpl !forclr-
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
#if SCROLL_EDGE_MASK
    lda VIC_CONTROL_1                        // PRESERVE the live band/body state -- forcing the band here would
    and #EDGE_MASK_D011_BAND                 // black the frame if this ever ran after the aperture had opened,
    ora RASTER_DISPLAY_FINE                  // and forcing the body would unmask the top band.
    ora #GAMEPLAY_D011_BASE
    sta VIC_CONTROL_1
#else
    lda RASTER_DISPLAY_FINE                 // publishRasterPlan runs every frame (armFirstBatch) at ~line 17,
    ora #GAMEPLAY_D011_BASE                 // before the first badline: install the SAME whole-frame display
    sta VIC_CONTROL_1                        // state as rasterFrameReset (RSEL=1, DEN=1, YSCROL=presented fine;
#endif
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
#if BORDER_FORENSIC
    // Cheap forensic breadcrumb: 32-entry ring of (RASTER_EVENT, $d012, SP,
    // RASTER_FRAME low) captured at every VIC raster-event dispatch. ~24 cy/event.
    // On a future hang, one 64K dump shows the last 32 scheduler events + where
    // the beam was and how deep the stack got. FORENSIC_RING lives at a fixed
    // address (see the RASTER_STATE block); FORENSIC_HEAD is its 0..124 byte
    // cursor (4 bytes/entry).
    ldx FORENSIC_HEAD
    lda RASTER_EVENT
    sta FORENSIC_RING,x
    lda RASTER
    sta FORENSIC_RING + 1,x
    tsx
    txa
    ldx FORENSIC_HEAD
    sta FORENSIC_RING + 2,x
    lda RASTER_FRAME
    sta FORENSIC_RING + 3,x
    txa
    clc
    adc #4
    and #%01111111                          // wrap at 128 bytes (32 entries)
    sta FORENSIC_HEAD
#endif
    lda RASTER_EVENT
    beq rasterFrameReset
#if SCROLL_EDGE_MASK
    cmp #RASTER_EVENT_SPRITES
    beq !batchIrq+
#endif
    cmp #RASTER_EVENT_DISPLAY
    beq !display+
#if BORDER_PROOF_ENABLE
    cmp #RASTER_EVENT_BORDER
    beq !border+
#endif
#if SCROLL_EDGE_MASK
    cmp #RASTER_EVENT_MASK
    beq !mask+
!batchIrq:
#endif
    jsr applyLiveRasterBatch
    jmp !next+
#if BORDER_PROOF_ENABLE
!border:
    jsr borderOpenHook
    jmp !next+
#endif
#if SCROLL_EDGE_MASK
!mask:
    jsr edgeMaskOpenHook
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
#if SCROLL_EDGE_MASK
    ora #EDGE_MASK_D011_BAND                 // Stage 5B: the band is established HERE, inside the gameplay raster
                                             // chain, not in the shared base constant -- so it cannot be inherited
                                             // by init/menu/high-score/GAME OVER. Cleared again at the aperture.
#endif
    sta VIC_CONTROL_1                        // Every physical frame, including replay with main still building.
#if HUD_PROOF_ENABLE
    jsr hudBorderSetup                       // program HUD slots 4..7 at line 1, before their DMA (~raster HUD_Y-1)
#endif
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
#if SCROLL_EDGE_MASK
    lda #2                                  // 2 = HUD handoff still due, 1 = aperture-open still due, 0 = done.
    sta RASTER_DISPLAY_PENDING
    lda #1
#else
    lda #1
    sta RASTER_DISPLAY_PENDING
#endif
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
    beq !sprite+                            // (unchanged cost per dispatch once both phases are done)
#if SCROLL_EDGE_MASK
    cmp #1
    bne !dispPhase+
    jsr edgeMaskArmLine                     // A = arm line for this phase
    cmp RASTER_TARGET
    bcc !mask+
    jmp !sprite+
!dispPhase:
#endif
    lda #RASTER_DISPLAY_LINE
    cmp RASTER_TARGET
    bcc !display+
!sprite:
    lda #RASTER_EVENT_SPRITES
    sta RASTER_EVENT
    jmp !current+
!noBatch:
    lda RASTER_DISPLAY_PENDING
#if SCROLL_EDGE_MASK
    beq !noDisp2+
    cmp #1
    beq !mask+
    jmp !display+
!noDisp2:
#else
    bne !display+
#endif
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
#if SCROLL_EDGE_MASK
!mask:
    jsr edgeMaskArmLine
    sta RASTER_TARGET
    lda #RASTER_EVENT_MASK
    sta RASTER_EVENT
    // Own arm/serve decision: the hook re-polls to its exact line anyway, so a
    // near or past target is simply served now -- WITHOUT counting it as a
    // RASTER_CATCHUPS event (that metric is a scheduler-health signal for sprite
    // batches, and the generic !due path was inflating it ~100x here).
    lda VIC_CONTROL_1
    bmi !service+
    lda RASTER
    clc
    adc #3
    bcs !service+
    cmp RASTER_TARGET
    bcs !service+
    lda RASTER_TARGET
    sta RASTER
    rts
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
#if SCROLL_EDGE_MASK
    cmp #RASTER_EVENT_SPRITES               // batches first: the catch-up chain must not pay for the new event
    beq !batch+
#endif
    cmp #RASTER_EVENT_DISPLAY
    beq !hook+
#if BORDER_PROOF_ENABLE
    cmp #RASTER_EVENT_BORDER
    beq !borderHook+
#endif
#if SCROLL_EDGE_MASK
    cmp #RASTER_EVENT_MASK
    beq !maskHook+
#endif
!batch:
    jsr applyLiveRasterBatch
    jmp !select-
#if SCROLL_EDGE_MASK
!maskHook:
    jsr edgeMaskOpenHook
    jmp !select-
#endif
#if BORDER_PROOF_ENABLE
!borderHook:
    // Scheduler-level hardening (residual whole-border flicker). borderOpenHook's
    // RSEL dodge can only land when the beam is still in raster ~237..245. A BORDER
    // event reaches this !due/!service path only when a heavy replay/catchup frame
    // has pushed dispatchRasterEvents to the BORDER arm at or past its target (240).
    // If the beam is already >= 246 (or wrapped past 255) the dodge is physically
    // impossible this frame: do NOT enter the hook (no reliance on its internal
    // bail, no in-IRQ busy-wait). Mark BORDER finished, count it, and fall through
    // to the epoch -- the lower border closes for that one frame only and the
    // scheduler stays perfectly in sync. In-window (240..245) is still serviced
    // normally: the dodge lands and the border opens.
    lda VIC_CONTROL_1
    bmi !borderSkip+                        // $d011 bit7 = raster bit8 => beam >= 256
    lda RASTER
    cmp #246
    bcs !borderSkip+                        // beam >= 246 => cannot dodge this frame
    jsr borderOpenHook
    jmp !select-
!borderSkip:
    lda #0
    sta RASTER_BORDER_PENDING               // BORDER is complete for this frame.
    inc RASTER_BORDER_SKIPS
    bne !borderSkipDone+
    inc RASTER_BORDER_SKIPS + 1
!borderSkipDone:
    jmp !select-                            // !noBatch: DISPLAY & BORDER done -> epoch
#endif
!hook:
    jsr rasterDisplayHook
    jmp !select-

// Phase 1.5 retired the legacy RSEL=0 HUD/terrain $D011 split; the display event
// became a scheduled no-op at ~raster 56. The top-border-HUD proof REPURPOSES it:
// RASTER_DISPLAY_LINE is now HUD_HANDOFF_RASTER and this hook runs
// hudBorderHandoff -- the deferred gameplay sprites are re-applied into hardware
// slots HUD_SLOT_FIRST..7 here, after the HUD sprites' DMA/display has completed.
// The dispatcher plumbing (event merge with the next sprite batch) is unchanged.
// RASTER_DISPLAY_NORMAL / RASTER_DISPLAY_LATE remain declared for capture-tool
// symbol parity.
rasterDisplayHook:
#if SCROLL_EDGE_MASK
    dec RASTER_DISPLAY_PENDING              // 2 -> 1: the aperture-open phase is still due
#else
    lda #0
    sta RASTER_DISPLAY_PENDING
#endif
#if HUD_PROOF_ENABLE
    jsr hudBorderHandoff
#endif
#if SOFT_EDGE_MASK
    // SOFT-EDGE MASK, leave the top band. rasterFrameReset / publishRasterPlan
    // install $D011 with ECM=1, so the idle strip (rasters ~16..47) and matrix
    // row 0's blankable top glyph rows (rasters ~48..54) render as $D021
    // backdrop. Clear ECM here, at raster ~55, so the clean scrolling body
    // 55..246 renders normally (full 128-code multicolour text). This hook fires
    // at raster ~46-49; a short bounded poll + pad lands the switch after row 0's
    // raster-54 g-access and before row 1's raster-55/56 g-access. If the hook
    // entered late, switch immediately (a rare heavy-frame catchup).
    lda VIC_CONTROL_1
    bmi !softEdgeBodyNow+                   // beam >= 256: switch now.
    lda RASTER
    cmp #(SOFT_EDGE_BODY_RESTORE_RASTER + 2)
    bcs !softEdgeBodyNow+                   // already past raster 56: switch now (late catchup).
!softEdgeBodyWait:
    ldx RASTER
    cpx #SOFT_EDGE_BODY_RESTORE_RASTER      // 55: row 0's g-access at fine 7 ends here.
    bcc !softEdgeBodyWait-
    ldy #10                                 // Pad so the switch lands AFTER raster 55's g-access and
!softEdgeBodyPad:                            // before raster 56's: raster <=55 stays ECM-blank, raster
    dey                                     // 56 (first body row) gets its real terrain g-fetch. Clean
    bne !softEdgeBodyPad-                    // full lines either side -- no jittery mid-scanline split.
!softEdgeBodyNow:
    lda VIC_CONTROL_1
    and #%00111111                          // ECM = 0 (bit 7 = raster-compare MSB, always 0 for this scheduler).
    sta VIC_CONTROL_1
    lda VIC_CONTROL_2
    ora #%00010000                          // MCM = 1 (global multicolour terrain for the body).
    sta VIC_CONTROL_2
    lda #TERRAIN_MC_COLOUR_1
    sta EXTRA_COLOUR_1                      // $D022 restored for the body.
    lda #TERRAIN_MC_COLOUR_2
    sta EXTRA_COLOUR_2                      // $D023 restored for the body.
#endif
rasterDisplayRestored:
rasterBadlineRestored:
    rts

#if SCROLL_EDGE_MASK
// --- edgeMaskOpenHook (Stage 5A review) --------------------------------------
// The aperture-open transition as its own raster event, armed by
// dispatchRasterEvents 2 lines (3 on the badline phase) before
// EDGE_MASK_BODY_RASTER, so the IRQ returns to the main thread for the gap after
// the HUD handoff instead of busy-waiting it away. IRQ entry + rasterIRQ +
// dispatch + this hook's preamble is ~90 cycles, which is why the arm line is
// two lines early rather than one.
edgeMaskOpenHook:
    dec RASTER_DISPLAY_PENDING              // 1 -> 0: both display-phase events done this frame
    // STAGE 5A -- open the fixed aperture. $D011 currently carries the whole-frame
    // BAND state (ECM=1 -> invalid text mode -> black), installed by
    // rasterFrameReset / publishRasterPlan. Clear ECM at EDGE_MASK_BODY_RASTER so
    // every raster from there to EDGE_MASK_BAND_RASTER-1 shows normal multicolour
    // terrain. The switch MUST land between the previous line's last g-access
    // (cycle 55) and this line's first (cycle 16), so the body value is computed
    // BEFORE the poll and published by a single 4-cycle store.
edgeMaskEntry:                              // Stage 5A trace point: raster on entry to the mask block.
    lda VIC_CONTROL_1
    and #%00111111                          // ECM=0, RST8=0; DEN/RSEL/YSCROL preserved.
    tax                                     // X = body $D011, ready to store.
    lda VIC_CONTROL_1
    bmi !edgeBodyLate+                      // beam >= 256: hopeless, store now.
    lda RASTER_DISPLAY_FINE
    and #7
    cmp #(EDGE_MASK_BODY_RASTER & 7)        // Is the body raster itself a BADLINE this frame? A badline
    beq !edgeBodyBadline+                   // steals cycles 12..54, so a store polled into that line is
                                            // not reliably ahead of its g-accesses -- take the early path.
    lda #EDGE_MASK_BODY_RASTER - 2          // PRIME the poll one line early. The final loop must already
    cmp RASTER                              // be spinning when the beam crosses into the body raster:
    bcc !edgeBodyFinal+                     // its reads are then 7 cycles apart from a point inside the
!edgeBodyPrime:                             // previous line, so the first read that sees the new raster
    cmp RASTER                              // lands in cycles 0..6 -- ahead of both the sprite-DMA steal
    bcs !edgeBodyPrime-                     // (0..10) and a badline stall (12..54) on that line.
!edgeBodyFinal:
    lda #EDGE_MASK_BODY_RASTER - 1
    cmp RASTER
    bcc !edgeBodyLate+                      // already at/past the body raster: store now, and count it.
!edgeBodyWait:
    cmp RASTER                              // 4 cy; C=1 while target-1 >= beam.
    bcs !edgeBodyWait-                      // 3/2 cy -> 7-cycle loop.
edgeMaskBodyApplied:                        // Stage 5A trace point: exact raster/cycle of the switch.
    stx VIC_CONTROL_1                       // single store: band -> body.
    jmp !edgeBodyDone+
!edgeBodyLate:
    stx VIC_CONTROL_1                       // Late: the aperture opens a line or two low on this frame.
    inc EDGE_MASK_LATE                      // Diagnostic only; must stay 0 in the regression suite.
    bne !edgeBodyDone+
    inc EDGE_MASK_LATE + 1
    jmp !edgeBodyDone+
!edgeBodyBadline:
    // The body raster is a badline this frame, so land the store in the PREVIOUS
    // line's tail instead: after that line's last g-access (cycle 55) and before
    // the body raster's first (cycle 16). The previous line provably is NOT a
    // badline (two badlines cannot be adjacent), so the fixed delay below is not
    // stretched and the landing point is deterministic.
    lda #EDGE_MASK_BODY_RASTER - 3
    cmp RASTER
    bcc !edgeBodyPrevFinal+                 // already past: fall straight into the final poll.
!edgeBodyPrevPrime:
    cmp RASTER                              // prime, exactly as the normal path does.
    bcs !edgeBodyPrevPrime-
!edgeBodyPrevFinal:
    lda #EDGE_MASK_BODY_RASTER - 2
    cmp RASTER
    bcc !edgeBodyLate2+                     // already at/past the previous line: too late to place it.
!edgeBodyPrevWait:
    cmp RASTER
    bcs !edgeBodyPrevWait-                  // exits at cycle 3..9 of the previous line.
    ldy #10                                 // +51 cycles -> store starts at cycle 54..60 of that line,
!edgeBodyPad:                               // so its write lands at cycle 57..62 (or 0..2 of the body
    dey                                     // raster) -- past the previous line's g-accesses, ahead of
    bne !edgeBodyPad-                       // the body raster's, and clear of the badline stall entirely.
edgeMaskBodyAppliedEarly:                   // Stage 5A trace point (badline-phase path).
    stx VIC_CONTROL_1
    jmp !edgeBodyDone+
!edgeBodyLate2:
    // Too late to place the store in the previous line's tail. Degrade to the
    // normal in-line path rather than storing blind: on this phase that risks the
    // body raster's own badline stall (aperture one line low for this frame), but
    // never opens the aperture EARLY. Counted separately; must stay 0.
    inc EDGE_MASK_FALLBACK
    bne !edgeBodyFallback+
    inc EDGE_MASK_FALLBACK + 1
!edgeBodyFallback:
    lda #EDGE_MASK_BODY_RASTER - 1
    cmp RASTER
    bcc !edgeBodyLate-                      // even the body raster has passed: store now.
!edgeBodyFallbackWait:
    cmp RASTER
    bcs !edgeBodyFallbackWait-
    stx VIC_CONTROL_1
    jmp !edgeBodyDone+
!edgeBodyDone:
    rts

// A = the $D012 compare to arm for the aperture-open event this frame.
edgeMaskArmLine:
    lda RASTER_DISPLAY_FINE
    and #7
    cmp #(EDGE_MASK_BODY_RASTER & 7)
    beq !badline+
    lda #EDGE_MASK_BODY_RASTER - 5          // measured compare->hook latency is 2..3 lines (7-cycle entry +
    rts                                     // KERNAL $FF48 stub + dispatcher, +43 when a badline sits in the
!badline:                                   // way, which it does on half the phases), hence 5 lines of lead;
    lda #EDGE_MASK_BODY_RASTER - 6          // the badline-phase early-store path needs one more line still.
    rts
#endif

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
    // --- ROBUSTNESS GUARD (hard-lock fix + residual whole-border-flicker fix) --
    // !wait245 / !wait250 below are `ldx $d012 / cpx #target / bcc loop`. $d012 is
    // the raster counter MOD 256: for beam rasters 256..311 it reads 0..55, all
    // < 245, so !wait245 then spins until the beam wraps back up to raster 245 --
    // ~250..300 scanlines, INSIDE the IRQ. That stall crosses the frame boundary
    // and cascades into a permanent hard lock (captured PC=$61F7, RASTER_EVENT=
    // BORDER; see /reports/intermittent-lock-and-hud-flicker-investigation-report.md).
    // The dodge is only physically possible in raster ~237..245 (just before the
    // raster-247 RSEL close compare). Three-way classify the entry beam:
    //
    //   beam >= 246 (or bit8 set)  -> TOO LATE. The dodge cannot land this frame.
    //     Abandon BORDER for the frame (clear pending), count RASTER_BORDER_BAILS.
    //     The lower/upper border closes for that one frame; nothing hangs.
    //
    //   beam < 237                 -> TOO EARLY. Under a run of main-thread-late
    //     frames (heavy RC=8 wave + coarse cost; armFirstBatch's sei window pushed
    //     to raster ~40-58) an armed BORDER compare can fire early (observed
    //     beam ~58, RASTER_EVENT=3). Previously this hit the "bail" path, cleared
    //     RASTER_BORDER_PENDING and abandoned the border -> a 1-8 frame WHOLE-
    //     BORDER FLASH. Instead: leave RASTER_BORDER_PENDING SET and just return.
    //     rasterIRQ / dispatchRasterEvents re-arm the BORDER compare (240) right
    //     after this, so the border still opens on the same frame. Count
    //     RASTER_BORDER_EARLY. Bounded: the beam only advances, so at most a few
    //     wasted IRQs per frame before an in-window fire.
    //
    //   237 <= beam <= 245         -> IN WINDOW. Clear pending, do the dodge.
#if SOFT_EDGE_MASK
    // The SOFT_EDGE band-swap block below (and, when HUD_PROOF is off, the marker
    // block) can push !bail / !early past 8-bit branch range -- route via jmp.
    lda VIC_CONTROL_1
    bpl !guardLo+
    jmp !bail+                              // $d011 bit7 = raster bit8 => beam >= 256 => far too late.
!guardLo:
    lda RASTER
    cmp #237
    bcs !guardHi+
    jmp !early+                            // beam < 237 => spurious early fire: re-arm, keep pending.
!guardHi:
    cmp #246
    bcc !inWindow+
    jmp !bail+                             // beam >= 246 => too late to dodge this frame.
!inWindow:
#else
    lda VIC_CONTROL_1
    bmi !bail+                              // $d011 bit7 = raster bit8 => beam >= 256 => far too late.
    lda RASTER
    cmp #237
    bcc !early+                            // beam < 237 => spurious early fire: re-arm, keep pending.
    cmp #246
    bcs !bail+                             // beam >= 246 => too late to dodge this frame.
#endif
    // beam is now provably in [237 .. 245]; both polls below wait at most ~13
    // lines (usually <5) and can never wrap.
    lda #0
    sta RASTER_BORDER_PENDING

#if !HUD_PROOF_ENABLE
    // Diagnostic lower-border marker in slot 7. Disabled by the HUD proof, which
    // owns slot 7 (see main.asm HUD_SLOT_FIRST); the deep-lower-border corruption
    // it demonstrated is already documented.
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
#endif

    // Open BOTH vertical borders (commercial "no-border" dodge -- see Slap Fight
    // $1802 / Terra Cresta $483c). Gameplay is RSEL=0, so the border FF close
    // compare is raster 247. Flip RSEL 0->1 before raster 247 (that compare then
    // misses); flip RSEL 1->0 before the RSEL=1 compare at raster 251 (that one
    // misses too). Neither close fires -> the vertical border FF is never set
    // this frame -> both the lower AND (single-FF consequence) the upper border
    // stay open into overscan. rasterFrameReset re-establishes RSEL=0 |
    // YSCROL=fine at line 0. The exposed region below the last badline is VIC
    // idle graphics whose g-fetch byte ($3FFF / $39FF) is forced to $00 in init,
    // so it renders as solid $D021 backdrop (not $3FFF stripes). The visible
    // gameplay TERRAIN aperture is still the raster 55..246 body (the finite
    // 25-row fetch cannot present a temporally-clean scrolling edge past it --
    // see the report); the opened border is sprite / player / future-top-HUD
    // room. The two writes land in raster ~245 / ~250, past every row's g-fetch,
    // so their exact cycle is not visible-pixel critical.
!wait245:
    ldx RASTER
    cpx #245
    bcc !wait245-
    lda VIC_CONTROL_1
    ora #%00001000                          // RSEL 0 -> 1  (raster-247 RSEL=0 close compare now misses).
    sta VIC_CONTROL_1
#if SOFT_EDGE_MASK
    // SOFT-EDGE MASK, bottom band. Row 24's terrain g-fetch spans rasters
    // 240+fine .. 247+fine; its outermost pixels (rasters >=248) have no world
    // row to scroll into and pop once per coarse 7->0. Enter Extended Color Mode
    // here (raster ~247, after row 24's continuity-relevant g-accesses <=247) so
    // every raster from ~248 through the border and the next frame's top band
    // (until softEdgeBodyRestore at raster 55) renders each cell as pure $D021
    // backdrop: char code masked to 6 bits indexes the zeroed $3800..$39FF
    // window. MCM must be cleared first (ECM+MCM is the invalid black mode);
    // $D022/$D023 become the backdrop colour so mixed code bits 6-7 don't stripe.
!wait247:
    ldx RASTER
    cpx #(SOFT_EDGE_BAND_RASTER - 1)        // 247: row 24's last continuity g-access.
    bcc !wait247-
    ldy #10                                 // Pad so the mode switch lands AFTER raster 248's g-access
!softEdgeBandPad:                            // (cycle ~55) and before raster 249's: raster <=248 keeps
    dey                                     // its real terrain g-fetch, raster >=249 is a clean full
    bne !softEdgeBandPad-                    // ECM-blank line (no jittery mid-scanline split).
    lda VIC_CONTROL_2
    and #%11101111                          // MCM = 0 first (ECM+MCM is the invalid all-black mode).
    sta VIC_CONTROL_2
    lda VIC_CONTROL_1
    ora #%01000000                          // ECM = 1.
    sta VIC_CONTROL_1
    lda #TERRAIN_BACKGROUND_COLOUR
    sta EXTRA_COLOUR_1                      // $D022 = backdrop for the band (mixed code bits 6-7 must not stripe).
    sta EXTRA_COLOUR_2                      // $D023 = backdrop for the band.
#endif
#if SCROLL_EDGE_MASK
    // STAGE 5A -- close the fixed aperture. A still holds the $D011 value just
    // written at raster 245 (RSEL=1 for the dodge), so OR in ECM to build the band
    // value without re-reading. Row 24's last continuity g-access is raster 247;
    // raster 248 is the first that alternates terrain/idle with the fine phase, so
    // the band must be live for 248's g-accesses. The beam is provably in [245,246]
    // here, so the poll is bounded to ~3 lines and cannot wrap. !wait250 below is a
    // read-modify-write, so it preserves ECM when it clears RSEL.
    ora #%01000000                          // ECM=1 (invalid text mode -> black), RSEL=1 kept.
    and #%01111111                          // RST8=0.
    tax                                     // X = band $D011, ready to store.
    lda #EDGE_MASK_BAND_RASTER - 1          // 247: last body raster.
!edgeBandWait:
    cmp RASTER                              // 7-cycle poll, as above.
    bcs !edgeBandWait-
edgeMaskBandApplied:                        // Stage 5A trace point: exact raster/cycle of the switch.
    stx VIC_CONTROL_1                       // single store: body -> band, before raster 248's g-accesses.
#endif
!wait250:
    ldx RASTER
    cpx #250
    bcc !wait250-
    lda VIC_CONTROL_1
    and #%11110111                          // RSEL 1 -> 0 before the raster-251 RSEL=1 close compare (misses too).
    sta VIC_CONTROL_1
borderOpenRestored:
    rts
!bail:
    lda #0
    sta RASTER_BORDER_PENDING               // Too late: abandon BORDER for this frame.
    inc RASTER_BORDER_BAILS                 // Forensic: a late / beam-wrapped border event was skipped.
    bne !bailDone+
    inc RASTER_BORDER_BAILS + 1
!bailDone:
    rts
!early:
    // Spurious early fire: DO NOT clear RASTER_BORDER_PENDING -- the caller
    // (rasterIRQ / dispatchRasterEvents) re-arms the BORDER compare at 240 next,
    // so the border still opens this frame.
    inc RASTER_BORDER_EARLY
    bne !earlyDone+
    inc RASTER_BORDER_EARLY + 1
!earlyDone:
    rts
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
#if OPT_SS_ALLOW_PENDING_LIVE_FLIP
ssBatchPtrStore:
    sta $07f8,x                            // 4F: hi byte self-modified to the ACTIVE page's pointer table
                                           // ($07F8 / $2BF8) once per $D018 flip (main thread, IRQ armed but
                                           // its batches not yet firing -> no race). ZERO per-assignment cost.
#else
    sta HW_SPRITE_POINTER,x
#endif
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
RASTER_DISPLAY_PENDING:        .byte 0        // (SCROLL_EDGE_MASK: 2 = handoff due, 1 = aperture-open due, 0 = done)
#if BORDER_PROOF_ENABLE
RASTER_BORDER_PENDING:         .byte 0        // Phase-1 bottom-border experiment; see borderOpenHook.
RASTER_BORDER_BAILS:           .word 0        // Forensic: borderOpenHook internal late-entry guard trips (hard-lock net).
RASTER_BORDER_SKIPS:           .word 0        // Forensic: dispatchRasterEvents skipped a late BORDER before entering the hook.
RASTER_BORDER_EARLY:           .word 0        // Forensic: borderOpenHook saw a spurious early fire and re-armed (border still opens).
#endif
#if SCROLL_EDGE_MASK
EDGE_MASK_FALLBACK:            .word 0        // Stage 5A forensic: the badline-phase early store could not be
                                              // placed, so the in-line path was used. MUST stay 0.
EDGE_MASK_LATE:                .word 0        // Stage 5A forensic: rasterDisplayHook reached the aperture-open
                                              // poll at/after EDGE_MASK_BODY_RASTER, so the band ran a line or
                                              // two into the body on that frame. MUST stay 0.
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
#if HUD_PROOF_ENABLE
HUD_HO_RC:                     .byte 0        // hudBorderHandoff scratch (IRQ-owned; not the TEMP_* main scratch)
HUD_HO_MSB:                    .byte 0
#endif
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

#if BORDER_FORENSIC
// OUTSIDE the RASTER_STATE clear loop (it would blow the 128-byte X range).
// 32 x (event, $d012, SP, RASTER_FRAME-low). Zeroed explicitly in
// initRasterScheduler. Survives in a 64K dump for post-mortem.
FORENSIC_HEAD:                 .byte 0
FORENSIC_RING:                 .fill 128, 0
#endif

.if (* > $6600) {
    .error "Raster dispatcher exceeds its $6000-$65ff allocation (the metatile stage data now begins at $6600)"
}
