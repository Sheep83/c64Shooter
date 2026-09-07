#!/bin/zsh
# Build + probe a deterministic N-metatile-row stage fixture against the widened
# 16-bit stage engine, then restore the generated level files. Never commits.
#   tools/run_stage_fixture.sh <N>
set -e
cd "${0:A:h}/.."
N=$1
KA=/Users/brianmorrice/dev/tools/kickassembler/KickAss.jar
PORT=$((6600 + N % 60))

GEN=src/generated/level1
CFG=$GEN/stage_config.asm
STG=$GEN/stage_test.asm
TUR=$GEN/stage_turrets.asm
WAV=$GEN/stage_waves.asm

# Back up and restore the generated level files. Restore from a byte copy, not
# git, so this works whether or not the generated files are committed yet.
cp "$CFG" /tmp/stage_config_backup.asm
cp "$STG" /tmp/stage_test_backup.asm
cp "$TUR" /tmp/stage_turrets_backup.asm
cp "$WAV" /tmp/stage_waves_backup.asm
restore() {
  cp /tmp/stage_config_backup.asm "$CFG"
  cp /tmp/stage_test_backup.asm "$STG"
  cp /tmp/stage_turrets_backup.asm "$TUR"
  cp /tmp/stage_waves_backup.asm "$WAV"
}
trap restore EXIT

python3 tools/make_stage_fixture.py "$N" > /tmp/stage_fixture_$N.asm
test -s /tmp/stage_fixture_$N.asm || { echo "fixture generation failed"; exit 1; }
cp /tmp/stage_fixture_$N.asm "$STG"
sed -i '' "s/^\.const STAGE_METATILE_ROWS *= *[0-9]*/.const STAGE_METATILE_ROWS = $N/" "$CFG"
# Minimal in-range single-turret placement + no wave triggers for the synthetic
# fixture (the widen probe does not care about either; this just satisfies the
# placement guards for any N).
printf '.const TURRET_TOTAL = 1\n.var turretCols = List().add(1)\n.var turretRows = List().add(1)\n' > "$TUR"
printf '.const WAVE_TRIGGER_COUNT = 0\n.var waveTriggerRowLo = List()\n.var waveTriggerRowHi = List()\n.var waveTriggerAttackId = List()\n.var waveTriggerCount = List()\n.var waveTriggerSprite = List()\n.var waveTriggerInterval = List()\n' > "$WAV"

( cd src && java -jar "$KA" main.asm -odir ../build -o ../build/shooter.prg -vicesymbols ) \
  | grep -E "Error|Writing prg file|\\\$6[0-9a-f]{3}-\\\$|\\\$7[0-9a-f]{3}-\\\$|\\\$8[0-9a-f]{3}-\\\$"

echo "--- probe (arithmetic on real 6502) ---"
python3 tools/vice_stage_widen_probe.py --port "$PORT" --out "build/mc-test/stage-widen-$N"
