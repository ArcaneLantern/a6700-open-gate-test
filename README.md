# A6700 open gate: test kit (firmware 2.00)

<p><b>Credit to @resaviews (instagram) | @resaviewsgit (github) for sharing the initial port</b></p>

<p><b>Kit v1 (2026-11-26). Not yet run on an A6700 by this project.</b> This is a <b>contributed port</b>: a contributor ported the open gate of our other kits to the Sony A6700 (ILCE-6700) firmware 2.00 and sent it to us as his own kit ("a6700-opengate v1.0"). Its author reports that it records 3840 × 2560 at 24p, 25p and 50p and 5760 × 3840 at 24p and 25p on an A6700. We have seen no logs or clips from those runs. This repository carries the same memory changes in the shape of our other kits: our helper program, our runner with its read-only check before any write, one USB session per step, Windows, macOS and Android. The patch only changes the running camera's memory; a cold boot (battery out for 10 seconds) removes it.</p>

**What we did with the contributed kit**

- **Checked every byte against the firmware.** All of the more than 1,000 places its designs change, and every guard, hold exactly the stated stock bytes in the 2.00 update's own files (`PORT_NOTES.md`, 57 checks). The few tables the camera builds in memory were checked by running the firmware's own set-up code in emulation.
- **Rebuilt its 16 programs from its source.** They come out byte for byte (with the newer compiler it used), so its programs hold nothing but the source we read. The source has no network access and no write outside the camera's memory and one result file.
- **Re-derived the designs with our own builders** where we have one (sensor records, raw write buffer, encoder tables, MP4 headers, playback decoder, screen). Every byte the contributed kit writes equals our derivation, with the exceptions listed below.
- **Rebuilt everything in our helper**, which is the same one the A7 IV, FX3 and FX30 kits use, unchanged. So the programs in this kit are new builds: they are **not** the programs the contributor ran. `PORT_NOTES.md` has a table of what each of our steps writes against what his step writes.

**What differs from the contributed kit**

| | Contributed kit | This kit |
|---|---|---|
| Which camera it runs on | any Sony camera in Mass Storage mode; the firmware version is typed in | only after a read-only check found the 2.00 software (hashes of three libraries and four code pages) |
| USB sessions | all steps in one | one per step, with an unplug and replug between |
| Result file | on the camera's service flash partition | on the camera's RAM disk |
| Screen step | 5 words, no guard | the same 5 words, 10 guards |
| Sensor step on NTSC | writes the mode record of 24p only; the 30p modes keep stock records over changed tables | writes the records of all five modes that share the tables |
| Playback step | one program changing three code pages | three one-page steps (our helper carries one page per step), same words |
| 4K encoder tables | one design for 24p, 25p, 50p in XAVC HS, S and S-I | **two launchers**: our own design for XAVC HS and S at 24p/25p (`open_gate_apply`), or the contributed design, unchanged (`open_gate_contributed_apply`, `open_gate_50p_apply`) |
| Android | its own app with the USB protocol rewritten in Kotlin | our app, which runs this kit's own scripts on the phone |

**What you should know before testing**

- **The picture is about 2.4% too tall.** The contributed design reads a 5952 × 3876 window (1.536:1) and stores it as 3840 × 2560 (1.5:1). A circle comes out slightly egg-shaped; fix it in the editor by scaling the height to 97.7%. **`open_gate_3x2_test` is our own answer to this:** the same kit with the exact 3:2 window, 5952 × 3968. It is a test: nobody has run that window on an A6700 (see "The exact 3:2 test" below).
- **5.76K is an enlargement**, not more detail: the camera's first stage delivers a 4336 × 2438 picture in every one of these states, and the 5760 × 3840 file is that picture scaled up.
- **Phase-detect rows.** The window carries 80 blocks of autofocus rows where the stock rule gives 79 (the count must be even). The contributor reports working autofocus; if yours misbehaves, tell us.

| Launcher | What it does | Writes to the camera? |
|---|---|---|
| `check_readonly.cmd` | Confirms the camera runs the 2.00 software the port was made from and reads what every patch site holds. Verdict READY / NOT READY | No |
| `dump_info.cmd` | **The debug dump for testers.** The same as the check, plus: memory map, the camera's own logs, the sensor's register state, the mode records and the window they program, the memory manager's records, the display (panel type, fit words, frame tables), the playback part of the main processor's log | No |
| `test1_sensor_window.cmd` | **Test 1:** raw write buffer and sensor steps only. Expected: a steady picture and 3840 × 2160 clips that hold the 3:2 window squeezed | **Yes: memory only** |
| `test2_output_size.cmd` | **Test 2:** test 1 plus the output size. Expected: a steady picture; a recording may stop after a second (the encoder is still set for 2,160 rows) | **Yes: memory only** |
| `open_gate_apply.cmd` | Open gate in five steps: raw write buffer, sensor, output size, **our** encoder design (XAVC HS 4K and XAVC S 4K at 24p / 25p, MP4 headers at 3840 × 2560), rear screen at 3:2. Ends with one read-only dump | **Yes: memory only** |
| `open_gate_apply_no_screen.cmd` | The same without the screen step | **Yes: memory only** |
| `open_gate_apply_no_meta.cmd` | The same, MP4 headers left at 3840 × 2160 | **Yes: memory only** |
| `open_gate_putback.cmd`, `screen_putback.cmd` | Put the steps back | Yes: memory only |
| `open_gate_3x2_test.cmd`, `open_gate_3x2_putback.cmd` | **A test of our own:** `open_gate_apply` with the exact 3:2 sensor window (5952 × 3968) in the place of the contributed one. Square pixels, 2.4% more height. Nobody has run this window on an A6700 | **Yes: memory only** |
| `xavc_si_apply.cmd`, `xavc_si_putback.cmd` | Optional, after `open_gate_apply`: XAVC S-I 4K at 24p / 25p. Put it back before `open_gate_putback` | **Yes: memory only** |
| `open_gate_contributed_apply.cmd`, `open_gate_contributed_putback.cmd` | **The 4K state as the contributor's kit applies it**, NTSC or PAL: the contributed encoder design (24p / 25p in XAVC HS, S and S-I) in the place of ours | **Yes: memory only** |
| `open_gate_50p_apply.cmd`, `open_gate_50p_putback.cmd` | **PAL only**: the contributed state with the 50p step (50p reads a 5612 × 3732 window). On an NTSC camera the 50p step writes nothing and the run stops | **Yes: memory only** |
| `open_gate_57k_apply.cmd`, `open_gate_57k_putback.cmd` | The 5.76K state: 5760 × 3840 files at 24p / 25p, 260 Mbps. Clips do not play in the camera | **Yes: memory only** |
| `playback_fix_apply.cmd`, `playback_fix_putback.cmd` | Optional, after a 4K apply: the camera plays 3840 × 2560 clips. Changes 7 instructions and 1 table word of the main processor's program in memory, and 1 instruction of a library | **Yes: memory only** |

The four 4K states (`open_gate_apply`, `open_gate_3x2_test`, `open_gate_contributed_apply`, `open_gate_50p_apply`) and the 5.76K state cannot be mixed: each one's steps write nothing while another is applied. Put one back, or cold boot, before applying another.

Nothing in this kit writes to the camera's firmware or to its settings. Like every kit of this kind, each step writes one small program file to the camera's service partition, which the camera loads once; the step deletes it again in the same session.

**Kits cannot be mixed up.** The FX30, FX3, FX2 and ZV-E1 kits' check libraries say NOT READY on an A6700, and their write steps write nothing on one. This kit's check says NOT READY on an FX30, ZV-E1 or A7 IV. Every write step writes nothing unless each byte it changes holds exactly the A6700 2.00 stock value. All of this was checked in emulation. If a cut-off run of the contributor's kit left one of its programs on the camera, a run of this kit removes it first (it knows the 17 files by their hashes).

## Before you start

1. The camera's menu must show **Ver. 2.00** (MENU > Setup > Setup Option > Version). On any other version, stop and tell us the version.
2. **USB Connection Mode: Mass Storage** (MENU > Setup > USB).
3. A charged battery. Do not record or play back while a step runs.
4. **Modes.** "STILL" below means the Still/Movie/S&Q dial (under the mode dial) on the still-camera position; "MOVIE" means that dial on Movie.
5. **Cold boot on STILL before an apply:** dial on STILL, battery out for 10 seconds, battery in, switch on. The first step changes the memory manager and refuses once Movie has been entered.

## Windows, once

1. Install Python 3.10 or later from python.org (with the "py launcher").
2. Run `windows/setup.cmd`.
3. Install the libusb-win32 driver for the camera with [Zadig](https://zadig.akeo.ie): Options, List All Devices, pick the camera, choose libusb-win32, Replace Driver. The first run switches the camera to service mode, where it shows up as a new device (054C:0336): install the driver for that one too, then run the step again.

## macOS, once (not run with an A6700)

The macOS kit is the A7 IV kit's macOS port, carried over unchanged apart from the launcher names. It runs the same scripts as Windows (`windows/tools`).

1. Python 3.9 or later: the one macOS offers with the Xcode Command Line Tools (`xcode-select --install` in Terminal) works.
2. Double-click `macos/setup.command`. No Homebrew and no driver are needed.
3. Each Windows launcher has a macOS twin with the same name (`.command` for `.cmd`).

Each live run asks for your Mac password: macOS keeps its own driver on the camera's USB connection, and only an administrator can hand the camera over to the script. If macOS refuses to open a .command file, open System Settings > Privacy & Security and click "Open Anyway".

## Android (app 0.1, not run with a camera)

`android/A6700-OpenGate.apk` runs this kit from a phone connected to the camera by USB-C. It carries exactly the files in `windows/tools` and runs them unchanged; only the USB access, the dialogs and the folder for the results are the phone's.

1. **If the contributor's app is installed, uninstall it first**: it has the same application id and Android will not install ours over it.
2. Install the APK (allow installing from unknown sources). Set the camera as for the PC, and also **USB Power Supply: Off**.
3. **1. Read-only check** first: an apply starts only after a check on this phone said READY. The buttons mirror the launchers above.
4. When Android asks to open *A6700 Open Gate* for the camera, tick **Always** and press OK. It comes up twice: once in Mass Storage, once in service mode.
5. When the log says **unplug and plug in again**, do that with the phone cable. Never switch the camera off.
6. Afterwards, **Export logs** writes a zip to `Download/A6700-OpenGate/` on the phone: send that zip back.

**Self-test** and **Dry run** need no camera and send nothing.

## A suggested order for the first tester

1. `check_readonly.cmd` on STILL. It must say **VERDICT READY**. Then `dump_info.cmd`, also on STILL. Send both folders if anything is not READY, and stop.
2. Cold boot on STILL, `test1_sensor_window.cmd`. It ends with a dump taken on MOVIE: follow what the script says. Note what the screen shows.
3. Cold boot on STILL, `test2_output_size.cmd`.
4. Cold boot on STILL, `open_gate_contributed_apply.cmd` (on a PAL camera you may use `open_gate_50p_apply.cmd` instead). This is the state closest to what its author reports working.
5. Cold boot on STILL, `open_gate_apply.cmd`: the same sensor side with our own encoder design.
6. Cold boot on STILL, `open_gate_3x2_test.cmd`: our exact 3:2 window. Do this one only after step 5 gave good clips, so that a fault can be put down to the window alone.
7. Later, if you like: `playback_fix_apply.cmd` after a 4K apply, and the 5.76K state.

Between tests: battery out for 10 seconds, switch on with the dial on STILL.

## While it is applied

- Record only what the applied state sets up:
  - `open_gate_apply` and `open_gate_3x2_test`: **XAVC HS 4K or XAVC S 4K at 24p (23.98p), or 25p on a PAL camera**; XAVC S-I 4K after `xavc_si_apply`.
  - `open_gate_contributed_apply`: XAVC HS, S or S-I 4K at 24p / 25p. On PAL do **not** record 50p in this state: its picture would be a 16:9 read-out stretched to 3:2.
  - `open_gate_50p_apply` (PAL): 25p or 50p.
  - `open_gate_57k_apply`: 24p / 25p; its author recommends XAVC S-I 4K, long-GOP formats may drop frames.
- **30p, 60p, 100p, 120p, S&Q, HD formats and Proxy Recording are not set up.** 30p reads the taller window too, but the encoder is not set for it: do not record it.
- **Do not open playback** unless the playback steps are applied, and never in the 5.76K state (its author reports a freeze that needs the battery out). If a clip says "Unable to display", do not try again; check the clips on a computer.
- With the screen step every 16:9 picture is shown stretched to 3:2 on the rear screen, so other movie formats look wrong there. The viewfinder is not changed and shows the picture squeezed.
- **Keep the camera switched on** from the first step to the last. Whether the power switch alone removes the patch on the A6700 is not known (on the A7 IV it does not, on the A7S III it does).
- **If the camera stops or restarts, do not pull the battery first.** Set STILL, plug in USB, run `dump_info.cmd`, then pull the battery. The dump holds the camera's own crash record.

## The exact 3:2 test (`open_gate_3x2_test`)

The contributed window is 5952 × 3876 from sensor row 214. Ours for this test is **5952 × 3968 from row 94**, exactly 3:2, the window the FX30 kit uses on the same sensor family (that kit's version with this window has not run on a camera either). Everything else is `open_gate_apply`: the same raw write buffer step (its 3,980 rows hold the 3,976-row first stage), output size, encoder design and screen step.

| | Contributed window | Exact 3:2 test |
|---|---|---|
| Sensor window | 5952 × 3876 from row 214 | 5952 × 3968 from row 94 |
| Shape of the 3840 × 2560 picture | 2.4% too tall | square pixels |
| Rows the sensor reads | 3,888 | 3,980 |
| Phase-detect blocks | 80 (the stock rule gives 79) | 82, as the stock rule gives |
| Sensor's first-row register | 295 | **175** |

What is new and untried: the first-row register drops below 256, which no stock movie mode of this camera has (every exact 3:2 window needs that, there is no room otherwise), and the sensor reads 92 more rows per frame. If the sensor does not take it, expect a broken or black picture or a restart on MOVIE, not lasting harm: a battery pull clears it. Then set STILL, run `dump_info.cmd`, and send the folder: that result is as useful to us as a good clip.

If it works, please send: a clip, a photo of a round object filling part of the frame (to check the shape), and the same scene shot with `open_gate_apply` for comparison.

## To return to stock

Battery out for 10 seconds. Or run the matching put-back launcher.

## What to send back

- The zipped `windows/camera_private` folder (or the app's exported zip): every session's report and raw result.
- What the rear screen showed on MOVIE (a photo of it helps), and whether the focus and tracking frames sat on the subject.
- A clip's properties: `mediainfo --Inform="Video;%Width% x %Height%, %FrameRate% fps, %Format%" clip.MP4` (MediaInfo, not ffprobe, for the header sizes), and whether it opens at 3:2 in your editor.
- A still photo of the same scene from the same position, so the field of view can be compared.
- Whether the patch was still there after switching the camera off and on with the power switch (run `check_readonly.cmd` afterwards and send it).
- The settings you used: NTSC or PAL, file format, frame rate, SteadyShot, lens.

## If something stops

- **"VERDICT NOT READY"**: nothing was written. Send the folder.
- **"The newest saved read-only check of this kit does not say READY"**: run `check_readonly.cmd` first.
- **"L13 refuses while the movie memory is laid out from the present records"**: the camera has been on Movie since it was switched on. Cold boot on STILL and apply again.
- **"nothing is written" at a later step**: a byte did not hold its stock value, or another state is applied. The steps before it stay applied; cold boot to be sure, and send the folder.
- **"A library from an earlier session is still on the service partition"**: the run removes it and goes on. If it says the file is none of this kit's, it names its hash: run the check again with `--remove-library` and that hash.
- **"UNDO INCOMPLETE"**: cold boot the camera before anything else, and send the folder.

## What is in here

- `windows/`, `macos/`: the launchers. `windows/tools/camera_tests/`: the session scripts (`a6700_run.py`, `a6700_apply.py`), the helper's source (`helper/readcheck.c`, `helper_a6700/a6700read.c`), the 33 pinned programs with the tables they were built from, and the emulations that run them against a model camera.
- `windows/tools/modding/designs/`: the 16 designs, one per step, each with the stock and new bytes of every place it changes. `windows/tools/modding/a6700/`: the builders and the checks against the contributed kit.
- `android/A6700-OpenGate.apk`.
- `PORT_NOTES.md`: the address map, what was checked and how, what is not known.

Nothing of the contributor's kit is in this repository: not its programs, not its runner, not its app. `helper_a6700/contrib_libs.json` holds only the hashes of its 17 programs.

## Credits

The A6700 port (the window choice, the address map, the 50p mode, the 5.76K state, the playback fix) is the contributor's work. USB service mode access uses [Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) by ma1co (vendored under `windows/tools/third_party`, MIT licence, pinned by hash).
