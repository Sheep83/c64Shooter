#!/bin/zsh
# Build one player-layer-count variant into a FIXED scratch location.
#   tools/build_layer_variant.sh <1|2|3> <outdir>
# Leaves src/main.asm exactly as it found it, and never writes per-run files
# into build/ (the repo build dir keeps only the last normal build).
set -e
cd "${0:A:h}/.."
N=$1
OUT=${2:?output dir required}
KA=/Users/brianmorrice/Dev/Tools/KickAssembler/KickAss.jar
mkdir -p "$OUT"
cp src/main.asm /tmp/main_layer_backup.asm
trap 'cp /tmp/main_layer_backup.asm src/main.asm; rm -f /tmp/main_layer_backup.asm' EXIT
sed -i '' "s|^\.const PLAYER_LAYER_COUNT = [0-9]*|.const PLAYER_LAYER_COUNT = $N|" src/main.asm
( cd src && java -jar "$KA" main.asm -odir "$OUT" -o "$OUT/layer$N.prg" -vicesymbols ) | grep -iE "^error" && exit 1
mv "$OUT/main.vs" "$OUT/layer$N.vs"
rm -f "$OUT/main.sym"
echo "layer$N: $(shasum -a 256 "$OUT/layer$N.prg" | cut -d' ' -f1)"
