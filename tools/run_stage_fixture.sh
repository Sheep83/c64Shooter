#!/bin/zsh
# Build + probe a deterministic N-metatile-row stage fixture against the widened
# 16-bit stage engine, then restore the generated level files. Never commits.
#   tools/run_stage_fixture.sh <N>
set -e
cd "${0:A:h}/.."
N=$1
KA=/Users/brianmorrice/dev/tools/kickassembler/KickAss.jar
PORT=$((6600 + N % 60))

CFG=src/generated/stage_config.asm
STG=src/generated/stage_test.asm

# Back up and restore the generated level files (they own STAGE_METATILE_ROWS
# and the stage map now). Restore from a byte copy, not git, so this works
# whether or not the generated files are committed yet.
cp "$CFG" /tmp/stage_config_backup.asm
cp "$STG" /tmp/stage_test_backup.asm
restore() {
  cp /tmp/stage_config_backup.asm "$CFG"
  cp /tmp/stage_test_backup.asm "$STG"
}
trap restore EXIT

python3 tools/make_stage_fixture.py "$N" > /tmp/stage_fixture_$N.asm
test -s /tmp/stage_fixture_$N.asm || { echo "fixture generation failed"; exit 1; }
cp /tmp/stage_fixture_$N.asm "$STG"
sed -i '' "s/^\.const STAGE_METATILE_ROWS *= *[0-9]*/.const STAGE_METATILE_ROWS = $N/" "$CFG"

( cd src && java -jar "$KA" main.asm -odir ../build -o ../build/shooter.prg -vicesymbols ) \
  | grep -E "Error|Writing prg file|\\\$6[0-9a-f]{3}-\\\$|\\\$7[0-9a-f]{3}-\\\$|\\\$8[0-9a-f]{3}-\\\$"

echo "--- probe (arithmetic on real 6502) ---"
python3 tools/vice_stage_widen_probe.py --port "$PORT" --out "build/mc-test/stage-widen-$N"
