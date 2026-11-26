#!/bin/bash
# Build the A6700 2.00 write libraries from the A7 IV helper's source (helper/readcheck.c), with this build's tables and constants
# (A6700 port, 2026-11-26). Run gen_a6700_write.py first.
# usage: build_a6700_write.sh        (writes libJit_a6700_<step>.so into this folder and prints SHA-256, size, step)
# Flags are those of helper/rebuild.sh. Differences from an A7 IV build: the headers of gen_a6700_write.py, the A6700 2.00 libsencore.so to
# link against, and these constants (modding/A6700_PORT_SENSOR.md, A6700_PORT_DMM_SIZE.md, A6700_PORT_ENCODER.md):
#   L13/L14  the DMM server's page of pointers 0x19d7000: workspace +0x1058, unit objects +0xbac; the four words of dmmwb_a6700_v1 with texts
#            for this body's rule (three units of the new size must fit each parent record)
#   L5/L6    IMAGER 0x17fab08, drive-parameter pointer at control +0x684, stored record 0x170 bytes. The header sets MULTI_REC: five stored
#            records (0x820, 0x880, 0x890, 0x8c0, 0x8d0), each in an NTSC and a PAL variant.
#   T5/T6    the same levels with ogsq32_a6700_v1: the exact 3:2 window 5952 x 3968 from row 94 (a test design of ours, in L5's place)
#   Q5/Q6    the same levels with ogsq50_a6700_v1: one stored record, of mode 0x830, as a PAL camera computes it (on NTSC nothing is written)
#   level 19/20 and 29/30 steps   av-cam.bin at physical 0x401000000 (kemco.txt: memrsv=0x01000000@0x401000000:ex)
# Steps: L = open gate (13/14 raw write buffer, 5/6 sensor side, 16/17 output size, 19/20 encoder side with the MP4 header heights);
# N19 = the encoder side without the heights (--no-meta; put back by L20); I19/I20 = XAVC S-I 4K on top of L19; M19/M20 = the contributed
# encoder design, complete (24/25/50p, HS / S / S-I), in L19's place; Q5/Q6 = the 50p sensor side (PAL); S16/S17 = the screen words;
# K16/K17 and K19/K20 = the 5.76K coprocessor words and encoder side; P29/P30, A29/A30, F29/F30 = the three playback code pages;
# R19/R20 = the playback resolution compare in libmpr.so.
set -e
H="$(cd "$(dirname "$0")" && pwd)"
SEN="$H/../../../work/extracted/a6700_200/0700_part_image/dev/nflasha15/lib/libsencore.so"
cd "$H/../helper"
CC=(../../../work/venv_zig/Scripts/python.exe -m ziglang cc -target aarch64-linux-gnu -std=gnu11 -O1 -Wall -Wextra -Werror -fPIC -shared -nostdlib -ffreestanding
    -fno-stack-protector -fno-builtin -fno-asynchronous-unwind-tables -Wl,-soname,libJit.so -Wl,--no-undefined -Wl,-z,now -g0 -s -Wl,-z,max-page-size=4096)
AV=-DAVCAM_PHYS=0x401000000UL
for L in 13 14; do
  "${CC[@]}" -DLEVEL=$L '-DDMM_SITES_H="expected_dmm_dmmwb_a6700_v1.h"' -DDMM_GLOBALS=0x019d7000UL -DG_WORKSPACE=0x1058U -DG_UNITS=0xbacU \
    '-DDMM_WORDS_TEXT="the four memory-manager words (the movie raw write buffer size in both layouts)"' '-DDMM_DONE_TEXT="all four sites hold"' \
    '-DDMM_RECS_TEXT="the four records and the parents'"'"' are as in the file; three units of the new size fit"' \
    '-DDMM_NOFIT_TEXT="three units of the new size do not fit the parent"' readcheck.c "$SEN" -o "$H/libJit_a6700_L$L.so"
done
for L in 5 6; do
  "${CC[@]}" -DLEVEL=$L '-DSITES_H="expected_sites_ogsq_a6700_v1.h"' '-DDESIGN_LABEL="ogsq_a6700_v1"' -DIMAGER=0x17fab08UL -DCTRL_DRVPARAM=0x684U -DREC=0x170U \
    readcheck.c "$SEN" -o "$H/libJit_a6700_L$L.so"
  "${CC[@]}" -DLEVEL=$L '-DSITES_H="expected_sites_ogsq32_a6700_v1.h"' '-DDESIGN_LABEL="ogsq32_a6700_v1"' -DIMAGER=0x17fab08UL -DCTRL_DRVPARAM=0x684U -DREC=0x170U \
    readcheck.c "$SEN" -o "$H/libJit_a6700_T$L.so"
  "${CC[@]}" -DLEVEL=$L '-DSITES_H="expected_sites_ogsq50_a6700_v1.h"' '-DDESIGN_LABEL="ogsq50_a6700_v1"' -DIMAGER=0x17fab08UL -DCTRL_DRVPARAM=0x684U -DREC=0x170U \
    readcheck.c "$SEN" -o "$H/libJit_a6700_Q$L.so"
done
for L in 16 17; do
  "${CC[@]}" -DLEVEL=$L '-DWORDS_H="expected_words_outsz2560_a6700_v1.h"' readcheck.c "$SEN" -o "$H/libJit_a6700_L$L.so"
  "${CC[@]}" -DLEVEL=$L '-DWORDS_H="expected_words_lcdfill_a6700_v2.h"' readcheck.c "$SEN" -o "$H/libJit_a6700_S$L.so"
  "${CC[@]}" -DLEVEL=$L '-DWORDS_H="expected_words_og57cp_a6700_v1.h"' readcheck.c "$SEN" -o "$H/libJit_a6700_K$L.so"
done
for L in 19 20; do
  "${CC[@]}" -DLEVEL=$L '-DMP_H="expected_mp_ogfile2560_hs_s_a6700_v2.h"' $AV readcheck.c -o "$H/libJit_a6700_L$L.so"
  "${CC[@]}" -DLEVEL=$L '-DMP_H="expected_mp_ogfilesi2560_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_I$L.so"
  "${CC[@]}" -DLEVEL=$L '-DMP_H="expected_mp_ogfile2560_full_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_M$L.so"
  "${CC[@]}" -DLEVEL=$L '-DMP_H="expected_mp_ogfile57r260_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_K$L.so"
  "${CC[@]}" -DLEVEL=$L '-DMP_H="expected_mp_pbmpr_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_R$L.so"
done
"${CC[@]}" -DLEVEL=19 '-DMP_H="expected_mp_ogfile2560_hs_s_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_N19.so"
for L in 29 30; do
  "${CC[@]}" -DLEVEL=$L '-DAD_H="expected_ad_avdec8k_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_P$L.so"
  "${CC[@]}" -DLEVEL=$L '-DAD_H="expected_ad_pbaspect_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_A$L.so"
  "${CC[@]}" -DLEVEL=$L '-DAD_H="expected_ad_pbformat_a6700_v1.h"' $AV readcheck.c -o "$H/libJit_a6700_F$L.so"
done
cd "$H"
for N in L13 L14 L5 L6 T5 T6 Q5 Q6 L16 L17 S16 S17 K16 K17 L19 L20 N19 I19 I20 M19 M20 K19 K20 R19 R20 P29 P30 A29 A30 F29 F30; do
  echo "$(sha256sum libJit_a6700_$N.so | cut -d' ' -f1) $(stat -c %s libJit_a6700_$N.so) $N"
done
