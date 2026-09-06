:BasicUpstart2(start)
start:
    sei
    lda #0
    sta $d01a
    sta $d015
    sta $d021
    lda #6
    sta $d020
    lda #$17
    sta $d011
    lda #$c8
    sta $d016
    lda #$1e
    sta $d018
    lda #3
    sta $dd00
    lda #$33
    sta $01
    ldx #0
romCopy:
    .for(var page=0;page<8;page++) {
        lda $d000+page*256,x
        sta $3800+page*256,x
    }
    inx
    bne romCopy
    lda #$37
    sta $01
    ldx #0
clear:
    lda #32
    sta $0400,x
    sta $0500,x
    sta $0600,x
    sta $0700,x
    lda #1
    sta $d800,x
    sta $d900,x
    sta $da00,x
    sta $db00,x
    inx
    bne clear
    ldx #11
textLoop:
    lda hudText,x
    sta $0402,x
    dex
    bpl textLoop
    ldx #0
rowLoop:
    .for(var row=1;row<25;row++) {
        lda #128+row
        sta $0400+row*40,x
    }
    inx
    cpx #40
    bne rowLoop
    ldx #0
glyphCopy:
    lda glyphs,x
    sta $3c00,x
    inx
    bne glyphCopy
frame:
    bit $d011
    bpl frame
low:
    bit $d011
    bmi low
    lda #$17
    sta $d011
wait60:
    lda $d012
    cmp #60
    bcc wait60
    lda #$11
    sta $d011
wait63:
    lda $d012
    cmp #63
    bcc wait63
    lda #$71
    ldx mask
    bne setMask
    lda #$11
setMask:
    sta $d011
    ldx fine
    cpx #7
    bne fineReady
wait64:
    lda $d012
    cmp #64
    bcc wait64
fineReady:
    txa
    ora #$10
    sta playD011
    ldx mask
    beq setFine
    ora #$60
setFine:
    sta $d011
wait70:
    lda $d012
    cmp #70
    bcc wait70
    ldx fine
    cpx #6
    beq restore
    .fill 18,$ea
restore:
    lda playD011
restoreWrite:
    sta $d011
    jmp frame
fine: .byte 0
mask: .byte 0
playD011: .byte $10
hudText: .byte 19,3,15,18,5,32,48,49,50,53,48,48
// Deliberately varied rows/scanlines give the pixel checker identifiable data.
glyphs:
    .for(var row=0;row<32;row++) {
        .for(var y=0;y<8;y++) { .byte (row*17)^(y*13) }
    }
