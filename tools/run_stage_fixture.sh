#!/bin/zsh
# Build + probe a deterministic N-metatile-row stage fixture, then restore the
# real stage_test.asm / main.asm. Never commits anything.
#   tools/run_stage_fixture.sh <N>
set -e
cd "${0:A:h}/.."
N=$1
KA=/Users/brianmorrice/dev/tools/kickassembler/KickAss.jar
PORT=$((6600 + N % 60))

# Restore stage_test.asm from git; put STAGE_METATILE_ROWS back to its real
# value WITHOUT touching the rest of the (uncommitted) widening in main.asm.
ORIG_ROWS=$(grep -m1 -oE '^\.const STAGE_METATILE_ROWS = [0-9]+' src/main.asm | grep -oE '[0-9]+')
restore() {
  git checkout -- src/stage_test.asm
  sed -i '' "s/^\.const STAGE_METATILE_ROWS = [0-9]*/.const STAGE_METATILE_ROWS = ${ORIG_ROWS}/" src/main.asm
}
trap restore EXIT

python3 tools/make_stage_fixture.py "$N" > /tmp/stage_fixture_$N.asm
test -s /tmp/stage_fixture_$N.asm || { echo "fixture generation failed"; exit 1; }
cp /tmp/stage_fixture_$N.asm src/stage_test.asm
sed -i '' "s/^\.const STAGE_METATILE_ROWS = [0-9]*/.const STAGE_METATILE_ROWS = $N/" src/main.asm

( cd src && java -jar "$KA" main.asm -odir ../build -o ../build/shooter.prg -vicesymbols ) \
  | grep -E "Error|Writing prg file|\\\$6[0-9a-f]{3}-\\\$|\\\$7[0-9a-f]{3}-\\\$|\\\$8[0-9a-f]{3}-\\\$"

echo "--- probe (arithmetic on real 6502) ---"
python3 tools/vice_stage_widen_probe.py --port "$PORT" --out "build/mc-test/stage-widen-$N"
