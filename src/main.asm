.filenamespace test
:BasicUpstart2(init)

#import "variables.asm"

init:
	//set VIC bank and memory config
	lda VIC_BANK
	and #%11111100 // mask for bits 2-8
	ora #%00000011 // the first 2 bits are your desired VIC bank value (Bank 0 default)
	sta VIC_BANK
	lda VIC_MEMORY_SETUP
	and #%11110000 // mask for bits 4-8
	ora #%00000100 // bits 1-3 (001) = character memory 2: $0800 – $0FFF
	sta VIC_MEMORY_SETUP
	//clear screen
	lda #147
	jsr $ffd2
	jsr setupSprites
	//screen text
	lda #24
	sta SCREEN_START
	lda #58
	sta SCREEN_START + 1
	sta SCREEN_START + 41
	lda #25
	sta SCREEN_START + 40
	lda #01
	sta MOB_X_VEL
	jsr mainLoop

checkRaster:
	//wait until raster 255
	lda RASTER
	cmp #255
	bne checkRaster
	rts

mainLoop:
	jsr checkRaster
	jsr checkStick
	jsr moveMobs
	lda SPR_X
	// jsr $ffd2
	sta SCREEN_START + 3
	lda SPR_Y
	sta SCREEN_START + 43
	jmp mainLoop

checkStick:
	down:
			lda STICK_2
    		and #1
    		beq up
    		inc SPR_Y
    		lda SPR_Y
        	cmp #231
        	beq !+
        	jmp up
        	!:
        		dec SPR_Y
        		jmp up

	up:
			lda STICK_2
    		and #2
        	beq right
        	dec SPR_Y
        	lda SPR_Y
        	cmp #49
        	beq !+
        	jmp right
        	!:
        		inc SPR_Y
        		jmp right

	right:
			lda STICK_2
        	and #4
        	beq left
        	inc SPR_X
        	lda SPR_X
        	cmp #00
        	beq setOverflow
        	cmp #66
        	beq checkRightBounds
        	jmp left

	left:
			lda STICK_2
        	and #8
        	beq fire
        	dec SPR_X
        	lda SPR_X
        	cmp #255
        	beq setOverflow
        	cmp #22
        	beq checkLeftBounds
        	jmp fire

    fire:
    		lda STICK_2
        	and #16
        	bne !+
        	inc BORDER_COLOUR

    	!:	rts

checkRightBounds:
    lda SPRITE_OVERFLOW_REGISTER
    and #%00000001
    beq !+
    dec SPR_X
!:
    rts

checkLeftBounds:
    lda SPRITE_OVERFLOW_REGISTER
    and #%00000001
    bne !+
    inc SPR_X
!:
    rts

setOverflow:
    lda SPRITE_OVERFLOW_REGISTER
    eor #%00000001
    sta SPRITE_OVERFLOW_REGISTER
    rts

setupSprites:
	//enable sprites 1-8
	lda #$ff
	sta SPRITE_ENABLE
	//set sprite 1-8 pointers
	ldx	#00
	lda #$80
	pointerLoop:
	sta $07f8,x
	inx
	adc #01
	cpx #08
	bne pointerLoop
	//set sprite colours
	lda #02
	sta SPRITE_1_COLOUR
	lda #03
	ldx #00
	colourLoop:
	sta SPRITE_2_COLOUR,x
	inx
	cpx #07
	bne colourLoop
	// set initial mob direction
	lda #%00000000
	sta SPRITES_DIR
	lda #146
	sta SPR_X
	lda #200
	sta SPR_Y
	//set mob sprite pos
	lda #31
	ldx #00
	xposLoop:
	clc
	sta SPR_2_X,x
	inx
	inx
	adc #28
	cpx #14
	bne xposLoop
	lda #54
	ldx #00
	yposLoop:
	sta SPR_2_Y,x
	inx
	inx
	cpx #14
	bne yposLoop
	rts

moveMobs:
	ldx #02
	ldy #01
	mobLoop:
	tya
	asl
	sta CURRENT_SPRITE
	tay
	jsr move
	// jsr overflowMob
	inx
	inx
	cpx #16
	bne mobLoop
	rts

move:
	lda SPRITES_DIR
	and CURRENT_SPRITE
	bne !+
	beq !++
	!:
	//moving left//check for x=0 & x=255//reverse at 255, overflow flip at 0
	sec
	lda SPR_X,x
	sbc MOB_X_VEL
	sta SPR_X,x
	cmp #255
	beq overflowMob
	cmp #23
	beq checkMobLeftBoundary
	rts
	!:
	//moving right//check for x=66 & x=0//reverse at 66, overflow flip at 0
	clc
	lda SPR_X,x
	adc MOB_X_VEL
	sta SPR_X,x
	cmp #0
	beq overflowMob
	cmp #66
	beq checkMobRightBoundary
	rts

overflowMob:
	lda SPRITE_OVERFLOW_REGISTER
	eor CURRENT_SPRITE
	sta SPRITE_OVERFLOW_REGISTER
	rts

reverseMob:
    lda SPR_Y,x
		clc
    adc #24
    sta SPR_Y,x

    lda SPRITES_DIR
    eor CURRENT_SPRITE
    sta SPRITES_DIR
    rts

checkMobRightBoundary:
    lda SPRITE_OVERFLOW_REGISTER
    and CURRENT_SPRITE
    beq !+              // MSB clear: this is X=66, not X=322
    jmp reverseMob
!:
    rts

checkMobLeftBoundary:
    lda SPRITE_OVERFLOW_REGISTER
    and CURRENT_SPRITE
    bne !+              // MSB set: this is X=279, not X=23
    jmp reverseMob
!:
    rts

jsr init

* = $2000

//sprite 1
.byte $00,$00,$00,$7f,$ff,$fe,$40,$18
.byte $02,$40,$18,$02,$40,$18,$02,$40
.byte $18,$02,$40,$18,$02,$40,$18,$02
.byte $40,$18,$02,$40,$18,$02,$7f,$ff
.byte $fe,$40,$18,$02,$40,$18,$02,$40
.byte $18,$02,$40,$18,$02,$40,$18,$02
.byte $40,$18,$02,$40,$18,$02,$40,$18
.byte $02,$7f,$ff,$fe,$00,$00,$00,$0a
//sprite 2
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$00,$00
.byte $00,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$04
//sprite 3
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$00,$00
.byte $00,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$04
//sprite 4
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$00,$00
.byte $00,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$04
//sprite 5
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$00,$00
.byte $00,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$04
//sprite 6
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$00,$00
.byte $00,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$04
//sprite 7
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$00,$00
.byte $00,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$04
//sprite 8
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$00,$00
.byte $00,$ff,$e7,$ff,$ff,$e7,$ff,$ff
.byte $e7,$ff,$ff,$e7,$ff,$ff,$e7,$ff
.byte $ff,$e7,$ff,$ff,$e7,$ff,$ff,$e7
.byte $ff,$ff,$e7,$ff,$ff,$e7,$ff,$04

// reverseMob:
// 	lda SPR_X,x
// 	cmp #76
// 	beq !+
// 	rts
// 	!:
// 	lda SPRITES_DIR
// 	eor CURRENT_SPRITE
// 	sta SPRITES_DIR
// 	and CURRENT_SPRITE
// 	bne !+
// 	rts
// 	!:	lda SPRITE_1_VEL,x
// 		eor #%10000000
// 		sta SPRITE_1_VEL,x
// 		// adc SPR_X,x
// 		rts
