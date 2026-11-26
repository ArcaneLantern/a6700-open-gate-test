# A6700 2.00 open gate: port notes (2026-11-26)

Sony A6700 (ILCE-6700), firmware 2.00. **Nothing in this kit has run on an A6700 by this project.** It is a contributed port (kit
"a6700-opengate v1.0" by its author, who reports it working on his camera), checked against the firmware and rebuilt in the helper and
runner of our other kits. These notes say what was checked, how, and what is not known. The README is for testers.

## What the A6700 is

- The FX30's sensor family and sensor tables (31 drive modes), on the coprocessor software generation of the A7C II and ZV-E1
  (0x170-byte stored mode records). The main processor's `av-cam.bin` is the FX30's with every table 0xf90 further on; `libmpr.so` is
  another compile of the same source.
- The service route, the loader, the RAM disk (`/tmp_wbshd`) and the memory reserved for `av-cam.bin` (physical `0x401000000`) are as on
  the other bodies.

## How open gate is done here

In 4K the A6700 reads a 5952 × 3348 window of its 6192 × 4128 sensor and scales it to 4K in two stages (first to 4336 × 2438).

| | Stock 4K | This kit (the contributed design) |
|---|---|---|
| Sensor window | 5952 × 3348 from row 406 | **5952 × 3876 from row 214** |
| Rows the sensor reads | 3,360 | 3,888 |
| Raw write buffer | 6016 × 3356 | 6016 × 3980 (the first step) |
| First-stage picture | 4336 × 2438 | 4336 × 2438 (the window is squeezed 165/191 vertically) |
| File | 3840 × 2160 | **3840 × 2560**, or 5760 × 3840 in the 5.76K state |

The window is set in two places, and the design changes both: seven cells of the sensor's register matrix (first row, line pairs,
phase-detect rows, lead-in), and the per-mode tables and picture records that tell the image processor what the sensor sends.

Three things follow from the numbers:

- **Shape.** 5952:3876 is 1.536:1 and the file is 1.5:1, so the picture is 2.37% too tall. The exact 3:2 window is offered as a test
  step of our own (below).
- **5.76K holds no more detail than 4K.** Its 3,840 rows are the 2,438-row first-stage picture enlarged.
- **Phase-detect blocks.** By the rule the stock windows obey, this window carries 79 blocks; the count must be even and the design uses
  80, so one block sits where a stock window would leave it out. The 50p window (76 blocks) obeys the rule.

## The exact 3:2 test window (ours, not the contributor's)

`open_gate_3x2_test` runs `open_gate_apply` with step T5 (`ogsq32_a6700_v1`) in the place of L5: the window **5952 × 3968 from row 94**,
the FX30 kit's window (`ogsq_fx30_v2`) on the same sensor family, with every byte derived from the A6700's own files.

- **Rules it obeys.** The start row is 2 more than a multiple of 4, as every stock window's. By the margin rule the four stock movie
  windows obey, it carries blocks 2 to 83: 82 blocks, an even count, so no block has to be added or dropped (the contributed window
  needs one more than the rule gives). The rows read end at row 4,068; stock modes end at or below 4,096.
- **What it changes.** The same places as L5 with other values, and one register cell more: the high byte of the first-row register,
  which becomes 0 (first row + 81 = 175). L5 and T5 therefore refuse each other. The vertical sampling ratio is 27/32 (3968 × 27/32 =
  3348 exactly).
- **Checked.** The mode records come from the camera's own calculator with these cells (NTSC and PAL); the scaler set-up in emulation
  takes all 2,438 rows with 27/32; the first stage (3,976 rows) fits the 3,980-row buffer of the first step; the built step passes the
  same emulated cases as L5, and the two refuse each other in both orders.
- **Not known.** Whether the sensor takes a first-row register below 256 (no stock movie mode has one) and 3,980 rows at this line rate.
  The firmware routine that sends the registers to the sensor was not run in emulation for this body. Neither this window on an A6700
  nor the FX30 kit's on an FX30 has run.

## What was checked

| Check | Result |
|---|---|
| The four firmware files the contributed designs name by hash | They are the files of the 2.00 update |
| Stock bytes at every place the designs change, and every guard (57 checks) | All as stated |
| The contributed C headers against the contributed designs | Equal, except that its generator drops the screen design's guards |
| The contributed kit's 16 programs rebuilt from its own source | 16 of 16 byte for byte (ziglang 0.17.1); nothing in them but the source |
| Mode records, by running the camera's own calculator in emulation, NTSC and PAL | Its records equal ours; it leaves out records ours writes (below) |
| Raw write buffer: the camera's own allocator code in emulation | Hands out the new size; the same number of buffers as stock |
| Size table and memory-id tables: the camera's own set-up code in emulation | Hold the stock words the designs expect |
| Resize: the camera's own scaler set-up in emulation | Takes all 2,438 rows with the design's ratio |
| Encoder tables: our own builder on this firmware | 214 of our 217 bytes are in the contributed design; the rest is one table row with another, equally valid, order |
| MP4 writer in emulation, 520 requests | Headers say 3840 × 2560 and 5760 × 3840 |
| Playback: disassembly and emulation of the three changed routines | 3840 × 2560 is taken as a 4K clip of ratio 3:2; other sizes unchanged |
| Screen: the fit and frame routines in emulation, 21 cases | The rear screen is filled, the focus frames follow |

## What each step writes, against the contributed kit's step

Bytes that change (`windows/tools/modding/a6700/compare_a6700_contrib.py`):

| Our step | Against | Result |
|---|---|---|
| L13 raw write buffer | its L13 | equal |
| L5 sensor, NTSC camera | its L5 | its 712 bytes and 142 more: the table cells of drive modes 0x890 and 0x8d0, and the mode records of 0x820, 0x880, 0x890, 0x8d0 |
| L5 sensor, PAL camera | its L5 (shared part) | its 768 bytes and 80 more: the cells and records of 0x890 and 0x8d0 |
| Q5 50p sensor (PAL) | the 50p part of its L5 | equal |
| L16 output size, K16 5.76K words, S16 screen | its L16, L26, S16 | equal; S16 checks 10 guards first |
| M19 contributed encoder design | its L19 | equal (931 bytes) |
| L19 our encoder design | its L19 | 214 bytes the same, 3 differ, 714 only in its (50p, S-I, HEVC 8-bit, the resolution compare) |
| K19 5.76K encoder | its L28 | equal (1,725 bytes) |
| P29 + A29 + F29 playback | its P29 | equal (17 bytes), as three steps |
| R19 | one instruction of its L19 | equal |

**Why L5 writes more.** Five drive modes (0x820, 0x880, 0x890, 0x8c0, 0x8d0) share one column of the register matrix and one pair of
picture records. The contributed kit changes the shared parts but the per-mode cells of only three modes, and on an NTSC camera the mode
record of 0x8c0 alone. By the timing tables 0x820 and 0x880 are the 29.97p modes on NTSC, so there its 30p would run changed tables over
stock records. Ours keeps all five consistent. (30p is still not for recording: the encoder is not set for it.)

**Why there are two encoder designs.** The contributed one covers 24p, 25p, 50p and S-I in one piece. Applied without the 50p sensor step
it lets a 50p recording take 2,560 rows from a 16:9 read-out; and 161 of its bytes belong to slow-and-quick rows the camera can never
match at this size. Our own design (`open_gate_apply`) is the one the A7 IV, FX3 and FX30 kits use, for XAVC HS and S at 24p / 25p. The
contributed one is offered unchanged (`open_gate_contributed_apply`, and with the 50p step `open_gate_50p_apply`).

## Address map

| What | A6700 2.00 |
|---|---|
| Register matrix / column map / mode ids | `0x10cd634` (154 rows × 20) / `0x10ce250` / `0xdc7b5c` |
| Crop, stream-0, stream-1, LC, read-out tables | `0xdc7bd8`, `0xeb4cc2`, `0xeb515c`, `0xeb55f6`, `0xeb57a8` |
| Picture records (4K column / 50p column) | `0xd3885c`, `0xd39414` / `0xd39fcc`, `0xd3ab84` |
| Mode records (RAM) | `0x25dabcc`, 0x170 bytes each; sensor object `0x17fab08` → control `+0x684` → `{count, ids, system, records}` |
| Mode-record calculator / constructor block | `0x3910e8` / `0x9709c0` |
| Memory manager | pointers `0x19d8058` (workspace), `0x19d7bac` (unit objects); unit records `0x257bca4`; id rows `0x25b6a68`; key lists `0x25b8a68` |
| Movie size table / its set-up | `0x199ec7c` / `0x4ab69c`; unit-count setting `0x199eeb0` |
| Screen: fit function / fit words / frame tables | `0x1f5f48` / `0x1f5f98` / `0xe99e30`, `0xe99e90` |
| Screen: panel type bytes (rear / viewfinder) | `0x1a7c0e0` / `0x1a7c210` (3 = 3:2, 2 = 4:3, 1 = 16:9; expected 3 and 2, not read on a camera) |
| av-cam.bin: unit-type table / descriptors / clip table | `0x393648` / `0x3936e8` (689 × 0x90) / `0x39156c` |
| av-cam.bin: decode allocation / aspect routine / playback format | `0x217548` / `0x23e4f0` / `0x115cfc`; decode size table `0xc00350` |
| libmpr.so: comb table / MP4 heights / resolution compare | `0x27e590` / `0x1ec1b8`, `0x1ec2e8` / `0x15e4e4` |

## The helper and the runner

- The write steps are `helper/readcheck.c`, the helper of the A7 IV, FX3 and FX30 kits, unchanged, compiled with this camera's tables.
  Each step compares every byte it will change with its stock value before writing anything, writes whole 64-byte lines, reads back, and
  undoes its own writes on any mismatch.
- The read-only check (`helper_a6700/a6700read.c`) hashes three libraries and four code pages against the 2.00 update, then reports every
  site. The encoder side is listed as 634 spans; per span it says which design's bytes it holds, so one check tells the stock state and
  each applied state apart. A sensor site is reported STOCK, TARGET (the contributed window) or TARGET32 (the exact 3:2 test window).
- The dump adds the camera's logs and tables, and the playback part of the main processor's log (the reads of the contributor's own
  diagnostic).
- Emulation of the built programs against a model camera: 36 cases for the read-only pair, 226 checks for the write steps (97 of them for
  the three playback steps, including every order of applying them).
- The dump library is 65,112 bytes, 408 under the camera's upload bound of 65,520: anything added to it has to be paid for elsewhere.

## Not known without a camera

- Whether the sensor accepts 3,888 rows at this line rate, and the extra phase-detect block.
- The 50p timing; the 5.76K buffers; long recordings, heat, rolling shutter (the sensor reads 16% more rows per frame).
- In-camera playback with the three steps applied.
- The rear panel's and the viewfinder's type bytes. If the rear panel reports 4:3, the screen step's fit word is not read.
- Whether the power switch removes the patch.
- Which menu setting picks which drive mode (the labels above come from the timing tables and the contributor's report).
- The contributor's reports themselves: no logs or clips were seen.
