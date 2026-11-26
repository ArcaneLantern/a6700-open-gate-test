#!/bin/bash
# Recompile the contributed A6700 kit's 16 libraries from ITS OWN source and headers and compare each with the library its manifest pins
# (A6700 port, 2026-11-26; check 4 of modding/A6700_PORT.md). The source is compiled, never run; the output goes to a scratch folder.
#   usage: rebuild_a6700_contrib.sh <python with ziglang> <scratch output folder>
# The compile line is the one of its build_og_kit.py, which is the line of camera_tests/CT6_memory_read_check/helper/rebuild.sh.
# Its libraries say "clang version 22.1.8" (ziglang 0.17.x); this project's are built with ziglang 0.13.0 (clang 18.1.6), so the
# comparison needs the newer compiler: with 0.13.0 every library differs in size.
set -e
PY="$1"; OUT="$2"
M="$(cd "$(dirname "$0")/.." && pwd)"
C="$M/work/contrib/a6700_v1.0/A6700 OpenGate/a6700-opengate_v1.0"
SEN="$M/work/extracted/a6700_200/0700_part_image/dev/nflasha15/lib/libsencore.so"
mkdir -p "$OUT"
"$PY" -m ziglang version
CC=("$PY" -m ziglang cc -target aarch64-linux-gnu -std=gnu11 -O1 -Wall -Wextra -Werror -fPIC -shared -nostdlib -ffreestanding -fno-stack-protector
    -fno-builtin -fno-asynchronous-unwind-tables -Wl,-soname,libJit.so -Wl,--no-undefined -Wl,-z,now -g0 -s -Wl,-z,max-page-size=4096)
same=0; total=0
while read step kind pb sen file; do
  if [ "$sen" = 1 ]; then "${CC[@]}" -DMOD_KIND=$kind -DMOD_PUTBACK=$pb "$C/src/a6700_og_mod.c" "$SEN" -o "$OUT/$file"
  else "${CC[@]}" -DMOD_KIND=$kind -DMOD_PUTBACK=$pb "$C/src/a6700_og_mod.c" -o "$OUT/$file"; fi
  a=$(sha256sum "$OUT/$file" | cut -c1-64); b=$(sha256sum "$C/build/og_kit/$file" | cut -c1-64)
  total=$((total + 1))
  if [ "$a" = "$b" ]; then same=$((same + 1)); echo "SAME    $step  $file  $a"
  else echo "DIFFERS $step  $file  rebuilt ${a:0:16} ($(stat -c %s "$OUT/$file") bytes)  theirs ${b:0:16} ($(stat -c %s "$C/build/og_kit/$file") bytes)"; fi
done <<'EOF'
L13 1 0 1 libJit_a6700_L13_dmmwb_apply.so
L14 1 1 1 libJit_a6700_L14_dmmwb_putback.so
L5 2 0 1 libJit_a6700_L5_ogsq_apply.so
L6 2 1 1 libJit_a6700_L6_ogsq_putback.so
L16 3 0 1 libJit_a6700_L16_outsz_apply.so
L17 3 1 1 libJit_a6700_L17_outsz_putback.so
L19 5 0 0 libJit_a6700_L19_enc_apply.so
L20 5 1 0 libJit_a6700_L20_enc_putback.so
L26 6 0 1 libJit_a6700_L26_og57cp_apply.so
L27 6 1 1 libJit_a6700_L27_og57cp_putback.so
L28 7 0 0 libJit_a6700_L28_enc57_apply.so
L29 7 1 0 libJit_a6700_L29_enc57_putback.so
S16 4 0 1 libJit_a6700_S16_lcd_apply.so
S17 4 1 1 libJit_a6700_S17_lcd_putback.so
P29 10 0 0 libJit_a6700_P29_avdec8k_apply.so
P30 10 1 0 libJit_a6700_P30_avdec8k_putback.so
EOF
echo "$same of $total libraries rebuild to the manifest's SHA-256"
