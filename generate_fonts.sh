#!/usr/bin/env bash
# generate_fonts.sh — Generate LVGL binary font files for the watch
#
# Prerequisites:
#   npm install -g lv_font_conv
#
# Usage:
#   bash generate_fonts.sh                  # Generate default sizes (42, 32)
#   bash generate_fonts.sh 48 36 24         # Generate custom sizes
#
# The Montserrat-Medium.ttf source file ships with lvgl_micropython.
# Output goes to watch_py/fonts/montserrat_<size>.bin

set -e

# Find the Montserrat TTF source
FONT_SRC="${MONTSERRAT_TTF:-$HOME/lvgl_micropython/lib/lvgl/scripts/built_in_font/Montserrat-Medium.ttf}"
OUT_DIR="watch_py/fonts"

if [ ! -f "$FONT_SRC" ]; then
    echo "ERROR: Montserrat-Medium.ttf not found at $FONT_SRC"
    echo "Set MONTSERRAT_TTF env var to the correct path, or clone lvgl_micropython:"
    echo "  git clone https://github.com/lvgl-micropython/lvgl_micropython ~/lvgl_micropython"
    exit 1
fi

if ! command -v lv_font_conv &>/dev/null; then
    echo "ERROR: lv_font_conv not found. Install it with:"
    echo "  npm install -g lv_font_conv"
    exit 1
fi

# Default sizes if none specified
SIZES=("${@:-42 32}")
if [ $# -eq 0 ]; then
    SIZES=(42 32)
fi

mkdir -p "$OUT_DIR"

for size in "${SIZES[@]}"; do
    out="$OUT_DIR/montserrat_${size}.bin"
    echo "Generating Montserrat ${size}px -> $out"
    lv_font_conv \
        --font "$FONT_SRC" \
        -r 0x20-0x7F \
        --size "$size" \
        --format bin \
        --bpp 4 \
        --no-compress \
        -o "$out"
    echo "  $(ls -lh "$out" | awk '{print $5}') written"
done

echo ""
echo "Done. Upload to device with:"
echo "  PORT=/dev/ttyACM0"
echo "  mpremote connect \$PORT mkdir fonts 2>/dev/null || true"
for size in "${SIZES[@]}"; do
    echo "  mpremote connect \$PORT cp $OUT_DIR/montserrat_${size}.bin :fonts/montserrat_${size}.bin"
done
echo "  mpremote connect \$PORT reset"
