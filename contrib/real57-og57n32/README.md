# A6700 (fw 2.00): exact 3:2 window test result, and an independent 5760×3840 first-stage design

**Not first:** @resaviewsgit announced a working native 5.76K build in issue #3 (2026-11-26 21:54 UTC), before our run.
This is a separate derivation, published so the two can be compared. It is **experimental**, run on **one camera** (PAL).
RAM only; a 10 s battery pull restores stock. No binaries here: rebuild and review. Paths (`a6700fw/...`, `a6700_6k`)
must be adjusted; after removing local paths the scripts were syntax-checked, **not re-run**. Comments are partly in
Spanish. Run against kit commit `17be2dc`.

## Results

| Test | Result |
|---|---|
| The kit's exact 3:2 window `ogsq32_a6700_v1`: L13, T5, L16, L19, S16 | **Works at 25p.** `C5114.MP4`: 3840×2560, H.264 4:2:2 10-bit, 696 frames, full decode, no bands or duplicates. Read-only dump in movie mode: T5 7/7 in the sensor registers |
| 6K: L13, **H5**, K16, K19, S16 | `C5115.MP4`: 5760×3840 25p, H.264 High 4:2:2 **Intra** 10-bit L6.1, ~234 Mbps, 372 frames all I, full decode, no duplicates by `mpdecimate`, no centre seam seen, no bottom band |

An earlier T5 attempt, with the camera in 50p (a mode that state does not prepare), restarted the camera on record.

**What is and is not shown for 6K.** After apply, the picture records in RAM equal the design, the camera log shows the
second scaler taking the full 5760×3840 without crop, and the video encoder task runs at 5760×3840. But a comparison on
a real scene **did not show clearly more detail** than the upscaled 4K: the spectrum shows no cut-off where an upscale
would have one, yet compression noise weakens that test (~0.40 bit/px at 6K against ~1.05 at 4K). Treat the real
resolution gain as **unproven** until there is a chart test.

**Problems seen:** the camera gets **very hot**. Once, live view had a pink/white band at the bottom left; it was gone
after unplugging USB (cause unknown), and the clip had none. Sony's XML still says 3840×2160. In-camera playback was not
tried. Use XAVC S-I 4K 25p (@resaviewsgit reports Long-GOP drops or repeats frames at 5.76K). Long takes were not tested.

## How it works

1. **L13** grows the movie raw write buffer to 3,980 rows.
2. **H5** = the sensor side of `ogsq32` (window 5952×3968 from row 94, stage 5976×3976) with two new picture records whose
   first-stage output is 5760×3840 instead of 4336×2438: step 4233 (Q12) in both directions, so square pixels.
   Per half: 3016×3976 in, 2912×3844 out. Stored record bytes +6/+7 = 27/32; in emulation, without it the second scaler crops.
3. **K16** (kit) sets the 5760×3840 output and its buffers; **K19** (kit) the encoder for 5760×3840.
4. **S16** (kit) fills the rear screen at 3:2.

**Derivation** (`derivation/`): `plan1.py` runs the firmware's own planner (`cpapp-b` `0x269db0`) in Unicorn.
`gate1.py` checks it blind against the A7 IV `og57n_v1`: 2996 of 3000 bytes; the other four fields
(`0x698/a48/ae8/b88`) match once the A7 IV input-height values are fixed. Stock A6700 modes reproduce 3000/3000.
`build1.py` builds v1, `audit1.py` checks it, `make.py` makes v2 (those four fields kept at `ogsq32`'s 1990) and its
header with the kit's generator. `emu.py` runs the H5/H6 libraries against a model built from a stock read-only dump
(not published).

## Step by step

1. The menu shows Ver. 2.00 and the kit's `check_readonly` says READY. PAL. USB Mass Storage.
2. Run `derivation/gate1.py`, `build1.py`, `audit1.py`, then `make.py`. Build `libJit_a6700_H5.so` / `H6.so` with the kit's
   helper (with ziglang 0.13.0 the same build reproduced the kit's T5/T6 byte for byte). Put the hashes in `correr.py`;
   run `emu.py`.
3. `python todo.py L13 H5 K16 K19 S16 --simular`
4. Battery out 10 s. Boot on **stills**. Connect.
5. `python todo.py L13 H5 K16 K19 S16 --go --writes-memory --firmware-shown 2.00` runs five steps in **one USB session**
   and stops at the first step that is not DONE.
6. Unplug. Movie mode, **XAVC S-I 4K 25p**. Record a short clip. Do not open playback. Watch the temperature.
7. Back to stock: battery out 10 s.

## Credits

**@resaviewsgit**: the initial A6700 port, the 5.76K state (K16/K19) and the first announced native 5.76K.
**ArcaneLantern**: the kit, helper, runner, `ogsq32_a6700_v1`, and the A7 IV `og57n_v1` used as the reference (GPL-3.0).
USB service access builds on [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) by ma1co. Done with AI assistance
(Claude, Gemini); tested on camera by the contributor. GPL-3.0. Use at your own risk: heat and crashes are possible.
