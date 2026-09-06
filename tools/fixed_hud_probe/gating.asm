:BasicUpstart2(start)
start:
    sei
    lda #0
    sta $d01a
    sta $d015
    sta $d010
    sta $d017
    sta $d01c
    sta $d01d
    sta $d021
    lda #6
    sta $d020
    lda #$17
    sta $d011
    lda #$c8
    sta $d016
    lda #$14
    sta $d018
    lda #3
    sta $dd00
    lda #100
    sta $d000
    lda #50
    sta $d001
    lda #1
    sta $d027
    lda #$80
    sta $07f8
    ldx #0
    lda #32
clear:
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    inx
    bne clear
    lda #$80
    sta $07f8
frame:
    bit $d011
    bpl frame
low:
    bit $d011
    bmi low
    lda #$80
    sta $07f8
    lda #1
    sta $d015
    lda mode
    cmp #2
    bne enabled
    lda #0
    sta $d015
enabled:
    lda mode
    cmp #3
    bne wait54
    lda #$81
    sta $07f8
wait54:
    lda $d012
    cmp #54
    bcc wait54
    lda mode
    cmp #1
    bne wait70
    lda #0
    sta $d015
wait70:
    lda $d012
    cmp #70
    bcc wait70
    lda #1
    sta $d015
    lda #$80
    sta $07f8
    jmp frame
mode: .byte 0
*=$2000
    .fill 63,$ff
    .byte 0
    .fill 64,0
