#!/bin/zsh
# Standard scroller/mux regression captures.
#
# Build/test hygiene: EVERY capture goes to a scratch root OUTSIDE the repo
# (default $TMPDIR/c64-regression), is analysed, and is then DELETED. Nothing
# accumulates under build/. Only the small JSON summaries are kept.
#
#   tools/run_regression_suite.sh <scratch-root> [prg] [symbols]
set -e
cd "${0:A:h}/.."
ROOT=${1:-${TMPDIR:-/tmp}/c64-regression}
PRG=${2:-build/shooter.prg}
SYM=${3:-build/main.vs}
mkdir -p "$ROOT/summaries"
X64SC=/opt/homebrew/bin/x64sc

# The terrain oracle reads the RAM charset from here.
capture() {                     # capture <name> <port> <frames> <extra flags...>
  local name=$1 port=$2 frames=$3; shift 3
  local out="$ROOT/$name"
  rm -rf "$out"; mkdir -p "$out"
  # Direct launch, never `open -a`: does not steal macOS keyboard focus.
  "$X64SC" -default -pal -warp +sound -remotemonitor \
      -remotemonitoraddress "ip4://127.0.0.1:$port" \
      -autostartprgmode 1 -autostart "$PRG" >/dev/null 2>&1 &
  local pid=$!
  sleep 3
  python3 tools/vice_scroll_test.py --port "$port" --frames "$frames" \
      --prg "$PRG" --symbols "$SYM" --out "$out" "$@" >/dev/null
  # vice_scroll_test detaches (sends 'x', closes the socket) but does not quit
  # VICE, so wait would block forever. Kill only the instance THIS function
  # launched, by pid -- never an unrelated user-launched VICE.
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  cp "$out/00000.charset" /tmp/shooter-charset.bin 2>/dev/null || true
  echo "=== $name ==="
  python3 tools/check_raster_capture.py "$out" > "$ROOT/summaries/$name.raster.json" 2>&1 || true
  # NOT check_scroll_capture.py: that tool still reads BG_COARSE_* from a $2920
  # dump and OPT_SS_RELOCATE moved that block to $9000+, so it IndexErrors on
  # every current capture (baseline included). check_stage_wrap covers the
  # scroll-position half of it from the $2000 state dump.
  python3 tools/check_stage_wrap.py "$out" > "$ROOT/summaries/$name.scroll.json" 2>&1 || true
  python3 - "$ROOT/summaries/$name" <<'PY'
import json, sys
base = sys.argv[1]
for kind in ('raster', 'scroll'):
    try:
        d = json.load(open(f'{base}.{kind}.json'))
    except Exception as e:
        print(f'  {kind}: UNPARSEABLE ({e})'); continue
    keep = ('frames','frame_cycle_deltas','service_failure_count','sprite_start_miss_count',
            'max_objects','max_batches','catchups','replay_frames','page_aware',
            'page_a_frames','page_b_frames','wraps','max_active','failure_count',
            'stage_step_errors','first_transition_ok')
    print(f'  {kind}: ' + '  '.join(f'{k}={d[k]}' for k in keep if k in d))
PY
  # aperture check where a body/edge oracle applies
  if [[ -n "$APERTURE" ]]; then
    python3 tools/check_scroll_edges_rsel1.py "$out" --aperture 55 246 \
      > "$ROOT/summaries/$name.aperture.json" 2>&1 || true
    python3 -c "
import json,sys
d=json.load(open('$ROOT/summaries/$name.aperture.json'))
print('  aperture: ' + '  '.join(f'{k}={v}' for k,v in d.items() if 'diff' in k or 'frames' in k))
" 2>/dev/null || echo "  aperture: (see $name.aperture.json)"
  fi
  du -sh "$out" | sed 's/^/  capture size: /'
  rm -rf "$out"                 # <-- transient capture removed immediately
}

# WHICH may name a subset, e.g. WHICH="dense y199" tools/run_regression_suite.sh ...
WHICH=${WHICH:-"ordinary dense y199 wrap wrap352 aperture-passive aperture-dense"}
echo "PRG: $PRG"
echo "captures: $WHICH"
run_one() {
  case $1 in
    ordinary)         capture ordinary 6710 1400 --physical --trace ;;
    dense)            capture dense    6711 900  --physical --dense --trace ;;
    y199)             capture y199     6712 400  --physical --y199 --trace ;;
    wrap)             capture wrap     6713 1200 --physical --trace --seed-scroll 30 ;;
    wrap352)          capture wrap352  6716 900  --physical --trace --seed-scroll 352 ;;
    aperture-passive) APERTURE=1 capture aperture-passive 6714 400 --physical --passive --trace ;;
    aperture-dense)   APERTURE=1 capture aperture-dense   6715 400 --physical --dense --trace ;;
    *) echo "unknown capture: $1"; return 1 ;;
  esac
}
for name in ${=WHICH}; do run_one "$name"; done
echo
echo "scratch root: $ROOT"
du -sh "$ROOT"
