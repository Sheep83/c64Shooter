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
.var MOB_X_VEL                = $002b
.var TEMP_Y_REG               = $002e
.var TEMP_MSB                 = $002f
.var JOY_STATE                = $0030
.var TEMP_OBJECT              = $0031
.var TEMP_SORT_Y              = $0032
.var TEMP_OBJECT_Y            = $0034
.var TEMP_EVENT_INDEX         = $0035
.var TEMP_FREE_RASTER         = $0036
