//----------------------------------------------------------
// C64 hardware registers and working zero-page variables
//----------------------------------------------------------

// VIC-II / CIA hardware registers used by the current program.
.var BORDER_COLOUR            = $d020
.var RASTER                   = $d012
.var HW_SPRITE_COLOUR         = $d027
.var SPRITE_ENABLE            = $d015
.var SPRITE_OVERFLOW_REGISTER = $d010
.var VIC_MEMORY_SETUP         = $d018
.var SPRITE_MODE              = $d01c
.var SPRITE_COLOUR_1          = $d025
.var SPRITE_COLOUR_2          = $d026
.var SPR_X                    = $d000
.var SPR_Y                    = $d001
.var STICK_2                  = $dc00
.var VIC_BANK                 = $dd00
.var HW_SPRITE_POINTER        = $07f8
.var IRQ_VECTOR               = $0314
.var IRQ_ENABLE               = $d01a
.var IRQ_STATUS               = $d019
.var VIC_CONTROL_1            = $d011

// Working state / scratch bytes.
// NOTE: these are in BASIC's zero-page workspace. That is acceptable while
// this program owns the machine, but moving them to a deliberately reserved
// area is a sensible later cleanup before the engine grows.
.var TEMP_Y_REG               = $002e
.var TEMP_MSB                 = $002f
.var JOY_STATE                = $0030
.var TEMP_OBJECT              = $0031
.var TEMP_SORT_Y              = $0032
.var TEMP_OBJECT_Y            = $0034
.var TEMP_EVENT_INDEX         = $0035
.var TEMP_FREE_RASTER         = $0036
// Menu/HUD text blitting (drawTextRow): source screen-code pointer and
// destination screen-RAM pointer. $fb-$fe are genuinely free zero page on the
// C64 (no KERNAL/BASIC use) while this program owns the machine.
.var TEXT_SRC                 = $fb
.var TEXT_DST                 = $fd
// $f9/$fa are likewise free while this program owns the machine; used as the
// indirect pointer to whichever movement-fragment table is currently active.
.var FRAG_PTR                 = $f9
// $f7/$f8 are free for the same reason. Main-thread-only indirect pointer to
// the raw stage row currently being copied to screen RAM; multiplexIRQ never
// touches it, so the raster IRQ cannot corrupt it mid-copy.
.var STAGE_SRC                = $f7
.const BACKGROUND_COLOUR      = $D021
