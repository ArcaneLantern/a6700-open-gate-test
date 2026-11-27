"""A6700 (ILCE-6700) firmware 2.00: apply, or put back, the open-gate state in the camera's MEMORY.

  python a6700_apply.py apply      [--no-screen] [--no-meta] [--dry-run] [--no-movie-session]
  python a6700_apply.py putback    [--no-screen] [--dry-run]
  python a6700_apply.py screen | screen-putback  [--dry-run]
  python a6700_apply.py test1 | test2  [--dry-run]                    (DIAGNOSTICS, not usable states: see below)
  python a6700_apply.py si | si-putback  [--dry-run]                  (XAVC S-I 4K, on top of apply)
  python a6700_apply.py apply32 | putback32  [--no-screen] [--no-meta] [--dry-run]   (TEST: apply with the exact 3:2 sensor window)
  python a6700_apply.py applyfull | putbackfull  [--no-screen] [--dry-run]   (the contributed 4K state, NTSC or PAL)
  python a6700_apply.py apply50 | putback50  [--no-screen] [--dry-run]   (PAL only: the contributed 4K state with open gate at 50p)
  python a6700_apply.py apply57 | putback57  [--no-screen] [--dry-run]   (5760x3840 files)
  python a6700_apply.py playback | playback-putback  [--dry-run]      (in-camera playback of 3840x2560 clips)

The A6700 kit is a CONTRIBUTED PORT, conformed to the shape of the other kits (fx30_apply.py, fx2_apply.py). The contributor's kit
(a6700-opengate v1.0) carried its own helper and runner; its author reports 3840x2560 files at 24/25/50p and 5760x3840 files at 24/25p on
an A6700 2.00. We have seen no logs of those runs. Here the same memory changes are carried by this project's helper (readcheck.c) and
runner: every site was compared with the 2.00 update's own files, and each step was emulated. NOTHING OF THIS KIT HAS RUN ON AN A6700.

  apply     five steps, each its own USB session: L13 raw write buffer (dmmwb_a6700_v1), L5 sensor side (ogsq_a6700_v1: the 5952x3876
            window from row 214 in the five drive modes that share it, 0x820, 0x880, 0x890, 0x8c0, 0x8d0), L16 output size
            (outsz2560_a6700_v1), L19 encoder side with the MP4 headers (ogfile2560_hs_s_a6700_v2: this project's own encoder design, the
            FX30 kit's shape), S16 rear screen at 3:2 with the focus frames (lcdfill_a6700_v2). Afterwards: XAVC HS 4K or XAVC S 4K at
            24p (25p on PAL). With --no-screen only the first four; with --no-meta the encoder step without the MP4 header sizes (N19).
            A step that finds its bytes already applied says NOTHING TO DO and counts as passed.
  apply32   A TEST OF OUR OWN: apply with T5 (ogsq32_a6700_v1) in L5's place: the window 5952x3968 from row 94 (exactly 3:2, the FX30 kit's
            window) instead of the contributed 5952x3876 from row 214, whose 3840x2560 picture is 2.37 % too tall. Nobody has run this
            window on an A6700: the sensor's first-row register gets a value no stock movie mode uses. Put back with putback32.
  si        one more step on top of apply: I19 (ogfilesi2560_a6700_v1), XAVC S-I 4K at 24p (25p on PAL). Put it back (si-putback, I20)
            before putback.
  putback   the reverse: S17, L20, L17, L6, L14 (with --no-screen the last four). A cold boot (battery out for 10 seconds) also undoes everything.
  screen / screen-putback   only the screen step (S16) or its put back (S17).
  test1, test2   DIAGNOSTICS for a camera on which apply does not work. They apply only the first steps of apply, to show which step
            a camera does not take. Neither is a state to shoot with; for open gate itself use apply.
  test1     diagnostic 1 = L13 + L5: the taller sensor window with the stock output size. Expected: a steady picture on MOVIE and
            3840x2160 clips that hold the 3:2 window squeezed. Then one read-only dump on MOVIE.
  test2     diagnostic 2 = L13 + L5 + L16: plus the output size, WITHOUT the encoder step. Expected, and the correct result: a steady
            picture, and a recording that STOPS BY ITSELF AFTER ABOUT A SECOND, because the encoder is still set for 2,160 rows. That
            stop shows the output-size step took effect; it is not a fault. Then the dump. (A tester's A6700 gave exactly these two
            results on 2026-11-27.)
  applyfull THE CONTRIBUTED 4K STATE: L13, L5, L16, then M19 in L19's place (ogfile2560_full_a6700_v1: the contributed encoder design,
            complete: 24p, 25p and 50p in XAVC HS, S and S-I, with the MP4 header heights and the resolution compare), S16. On an NTSC
            camera this writes what the contributor's kit writes for its 4K mode, and the cells and records of the drive modes it leaves
            out. It cannot be mixed with apply: M19 and L19 refuse each other. Put back with putbackfull.
  apply50   PAL ONLY, THE CONTRIBUTED STATE WITH 50p: L13, L5, Q5 (ogsq50_a6700_v1: the drive mode 0x830, 4K 50p by the contributor's report,
            reads 5612x3732 instead of 5612x3156), L16, then M19 in L19's place (ogfile2560_full_a6700_v1: the contributed encoder
            design, complete: 24p, 25p and 50p in XAVC HS, S and S-I), S16. Q5 writes nothing on an NTSC camera (its stored record is
            not the PAL one). It cannot be mixed with apply: M19 and L19 refuse each other. Put back with putback50.
  apply57   the 5.76K state: L13, L5, then K16 (og57cp_a6700_v1: output 5760x3840, four scaler units, the larger output buffer) and K19
            (ogfile57r260_a6700_v1: the encoder side for 5760x3840 at 24/25p, 260 Mbps), S16. It cannot be mixed with apply: K16 and K19
            refuse while L16 or L19 is applied (their words do not hold the stock bytes). Put back with putback57. 5.76K clips do not play
            in the camera.
  playback  four steps on top of apply, applyfull or apply50: P29 (avdec8k_a6700_v1: the playback decoder's larger channel), A29
            (pbaspect_a6700_v1), F29 (pbformat_a6700_v1) and R19 (pbmpr_a6700_v1: one instruction of libmpr.so; after applyfull or apply50 it
            says NOTHING TO DO, M19 holds it): the camera plays 3840x2560 clips. The first three change instructions of av-cam.bin in memory
            and refuse unless the processor's caches can be made to fetch them. Put back with playback-putback.

The closing session (apply, apply50, apply57, screen, tests): one read-only dump taken on MOVIE, so that the first A6700 results show the
window the sensor was programmed with and the rear panel's type. Nothing is written in that session.

Rules it keeps:
- It starts only if the newest saved read-only check of this kit says VERDICT READY.
- It stops at the first step that does not end in DONE or NOTHING TO DO, and says what state that leaves.
- Each step is one pinned library; the runner (a6700_run.py) refuses any other bytes.
Nothing is written to a firmware file or to the camera's settings. What is written lives in the running camera's memory. A cold
boot (battery out for 10 seconds) removes it. Whether the power switch alone does is not known on the A6700 (on the A7 IV it does not,
on the A7S III it does), so keep the camera switched on from the first step to the last.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "CT1_usb_first_contact"))
sys.path.insert(0, str(HERE))
import ct1_common as c  # noqa: E402
import a6700_run  # noqa: E402

FIRMWARE = a6700_run.FIRMWARE
STEPS = {"apply": ("L13", "L5", "L16", "L19"), "putback": ("L20", "L17", "L6", "L14"), "screen": ("S16",), "screen-putback": ("S17",),
         "test1": ("L13", "L5"), "test2": ("L13", "L5", "L16"),
         # a test of our own: the exact 3:2 sensor window (T5 / T6) in L5's place
         "apply32": ("L13", "T5", "L16", "L19"), "putback32": ("L20", "L17", "T6", "L14"),
         # XAVC S-I 4K on top of apply (the FX3 kit's I19)
         "si": ("I19",), "si-putback": ("I20",),
         # PAL only, the contributed state: the 50p drive mode's window as well (Q5 after L5; Q6 before L6) and the contributed encoder
         # design, complete, in L19's place (M19 / M20)
         "applyfull": ("L13", "L5", "L16", "M19"), "putbackfull": ("M20", "L17", "L6", "L14"),
         "apply50": ("L13", "L5", "Q5", "L16", "M19"), "putback50": ("M20", "L17", "Q6", "L6", "L14"),
         # the 5.76K state: K16 / K19 in the place of L16 / L19
         "apply57": ("L13", "L5", "K16", "K19"), "putback57": ("K20", "K17", "L6", "L14"),
         "playback": ("P29", "A29", "F29", "R19"), "playback-putback": ("R20", "F30", "A30", "P30")}
APPLY_SETS, PUTBACK_SETS = ("apply", "apply32", "applyfull", "apply50", "apply57"), ("putback", "putback32", "putbackfull", "putback50", "putback57")
TESTS = ("test1", "test2")
EXPECT = {"test1": "the taller sensor window (5952x3876) with the stock output size. Expected: a steady picture on MOVIE and 3840x2160 clips that hold the 3:2 window squeezed.",
          "test2": "diagnostic 1 plus the output size 3840x2560, WITHOUT the encoder step. Expected, and the correct result: a steady picture, and a recording that "
                   "STOPS BY ITSELF AFTER ABOUT A SECOND (the encoder is still set for 2,160 rows)."}
# what the result means and what to run next, said once the diagnostic has run
AFTER = {"test1": ("A steady picture and a clip that records mean the sensor takes the taller window: the first two steps of open gate work on this camera.",),
         "test2": ("A recording that stopped by itself after about a second is the EXPECTED result: the output size took effect and the encoder step is not applied.",
                   "This state is not for recording, and nothing is wrong with the camera.")}
RUNNER = HERE / "a6700_run.py"
LISTER = HERE.parent / "CT1_usb_first_contact" / "ct1_stage2_service.py"
STILL = "STILL (the Still/Movie/S&Q dial on the still-camera position)"
MOVIE = "MOVIE (the Still/Movie/S&Q dial on Movie; File Format XAVC HS 4K or XAVC S 4K; 24p, or 25p on PAL)"


def say(text=""):
    print(text, flush=True)


def sessions():
    """Saved sessions of this kit, newest first: (folder, manifest)."""
    root = c.PRIVATE_ROOT
    out = []
    if root.is_dir():
        for folder in sorted((p for p in root.iterdir() if p.is_dir() and p.name.startswith("CT6_")), reverse=True):
            try:
                out.append((folder, json.loads((folder / "manifest.json").read_text(encoding="utf8"))))
            except (OSError, ValueError):
                continue
    return out


def last_check():
    """The newest saved read-only check of this kit that fetched a result: (folder name, ready?) or None. A check that stopped before the
    camera answered says nothing and is skipped. A check made with another kit does not count: its header is not this helper's."""
    for folder, man in sessions():
        res = man.get("results", {})
        f = (res.get("ct6", {}).get("result") or {}).get("s3")
        if res.get("which") in ("check", "dump") and f:       # a dump makes every check the check makes, and gives the same verdict
            current = any(v in f.get("header", "") for v in a6700_run.READ_LABELS) and "ILCE-6700 2.00" in f.get("header", "")
            return folder.name, current and bool(f.get("ready")) and not f.get("identity_differs"), f
    return None


def last_result_sha():
    """The SHA-256 of the result the newest session fetched: the runner deletes a result left on the RAM disk only if it has this hash."""
    for _, man in sessions():
        try:
            return man["results"]["ct6"]["result"]["sha256"]
        except (KeyError, TypeError):
            continue
    return None


def usb_state():
    r = subprocess.run([sys.executable, "-I", "-B", str(LISTER), "--list"], capture_output=True, text=True, encoding="utf8", errors="replace", cwd=str(LISTER.parent))
    import re
    m = re.search(r"libusb sees: (\d+) Sony mass-storage device\(s\).*?, (\d+) Sony service device\(s\)", r.stdout)
    if not m:
        return "other"
    return "drive" if int(m.group(1)) == 1 and int(m.group(2)) == 0 else "service" if int(m.group(2)) else "other"


def wait_for_drive(first, timeout=600):
    asked, end = False, time.time() + timeout
    while usb_state() != "drive":
        if not asked:
            say()
            if first:
                say("The camera is not showing as a USB drive. Turn it on with the dial on %s, connect USB (USB Connection Mode: Mass Storage)." % STILL)
            else:
                say(">>> Unplug the USB cable from the camera and plug it in again.")
                say(">>> Do NOT power the camera off or pull the battery: that would leave the steps half done.")
            say("Waiting for the camera (Ctrl+C to stop) ...")
            asked = True
        if time.time() > end:
            return False
        time.sleep(2)
    return True


def wait_for_replug(timeout=900):
    """Wait until the camera has been unplugged and shows up as a USB drive again. False on timeout."""
    end = time.time() + timeout
    while usb_state() != "other":                    # still plugged in, as a drive or in service mode
        if time.time() > end:
            return False
        time.sleep(1)
    while usb_state() != "drive":
        if time.time() > end:
            return False
        time.sleep(2)
    return True


def movie_session(test=None):
    """The closing read-only session, taken in movie mode: it shows the window the sensor is programmed with and the panel type."""
    say()
    say("=" * 78)
    say("One more session, and it only READS: it records the sensor's state in Movie, the memory manager's state and the rear panel's type.")
    say(">>> 1. Unplug the USB cable.")
    say(">>> 2. Set %s." % MOVIE)
    if test:
        say("       Watch the rear screen for ten seconds. Write down: a picture? flashing? does the camera switch itself off and on?")
        say("       If there is a steady picture: press REC, record about five seconds, press REC again.")
        if test == "test2":
            say("       In this diagnostic the recording is EXPECTED to stop by itself after about a second (there is no encoder step). That is the correct result.")
        say("       If the camera restarts by itself: do NOT pull the battery. Wait until it is on again, leave the dial on Movie.")
    else:
        say("       Look at the rear screen for five seconds and remember what it shows (the whole 3:2 picture? anything wrong?).")
    say(">>> 3. Plug the USB cable in again, still on Movie (after a restart too; choose Mass Storage if the camera asks).")
    say(">>> Do NOT switch the camera off: that may remove the patch.")
    say("Waiting for the unplug and the replug (Ctrl+C to stop; the patch stays applied either way) ...")
    if not wait_for_replug():
        say("The camera did not come back as a USB drive. The steps are applied all the same.")
        return
    cmd = [sys.executable, "-I", "-B", str(RUNNER), "dump", "--go", "--firmware-shown", FIRMWARE]
    clear = last_result_sha()
    if clear:
        cmd += ["--clear-result", clear]
    rc = subprocess.run(cmd).returncode
    which, f = step_outcome()
    say()
    if rc or which != "dump" or not f:
        say("The read-only session did not finish. The steps are applied all the same.")
        return
    decoded = f.get("decoded") or {}
    for line in a6700_run.movie_notes(decoded):
        say(line)
    say(">>> Unplug USB now.")


def step_outcome():
    for _, man in sessions():
        f = man.get("results", {}).get("ct6", {}).get("result", {}).get("s3")
        return (man.get("results", {}).get("which"), f) if f else (None, None)
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=sorted(STEPS))
    ap.add_argument("--dry-run", action="store_true", help="show the steps and what each would send; nothing is sent")
    ap.add_argument("--no-screen", action="store_true", help="with an apply or putback: without the screen step")
    ap.add_argument("--no-movie-session", action="store_true", help="leave out the closing read-only session in movie mode")
    ap.add_argument("--no-meta", action="store_true", help="with apply or apply50: the encoder step without the MP4 header sizes (N19); the headers keep saying 3840x2160")
    a = ap.parse_args()
    steps = STEPS[a.what]
    if a.no_screen and a.what not in APPLY_SETS + PUTBACK_SETS:
        raise SystemExit("--no-screen goes with apply, apply32, applyfull, apply50, apply57 or their putbacks. Nothing was sent.")
    if a.no_meta and a.what not in ("apply", "apply32", "apply50"):
        raise SystemExit("--no-meta goes with apply, apply32 or apply50 (the put back L20 puts back either encoder step). Nothing was sent.")
    if a.no_meta:
        steps = tuple("N19" if k == "L19" else k for k in steps)
    if not a.no_screen:
        if a.what in APPLY_SETS:
            steps = steps + STEPS["screen"]
        elif a.what in PUTBACK_SETS:
            steps = STEPS["screen-putback"] + steps
    applying = a.what in APPLY_SETS + ("screen", "playback", "si") + TESTS
    closing = a.what in APPLY_SETS + ("screen",) + TESTS
    for k in steps:                                  # every library must be the pinned one before anything starts
        name, sha, _ = a6700_run.WRITE_STEPS[k]
        p = a6700_run.S3 / name
        if not p.is_file() or c.sha256(p.read_bytes()) != sha:
            raise SystemExit("%s is missing or is not the pinned build. Nothing was sent." % name)
    say("A6700 2.00, %s: %d steps" % (a.what, len(steps)))
    for n, k in enumerate(steps, 1):
        say("  %d. %s  %s  (library %s...)" % (n, k, a6700_run.WRITE_STEPS[k][2], a6700_run.WRITE_STEPS[k][1][:16]))
    if closing and not a.no_movie_session:
        say("  then one read-only session (dump) on MOVIE: the sensor's window and the panel type for the first A6700 results. Nothing is written in it.")
    if a.dry_run:
        for k in steps:
            say()
            say("--- %s, what the session would send:" % k)
            r = subprocess.run([sys.executable, "-I", "-B", str(RUNNER), k, "--dry-run"], capture_output=True, text=True, encoding="utf8", errors="replace")
            say(r.stdout.rstrip() or r.stderr.rstrip())
        say()
        say("Dry run only: nothing was sent to any device.")
        return
    chk = last_check()
    if applying and (chk is None or not chk[1]):
        raise SystemExit("The newest saved read-only check of this kit %s. Run check_readonly first and get VERDICT READY. Nothing was sent."
                         % ("does not exist" if chk is None else "(%s) does not say READY" % chk[0]))
    say()
    say("This WRITES into the running camera's memory (not its firmware, not its settings).")
    say("NOT YET RUN ON AN A6700 by this project. The kit carries a contributor's port, whose author reports that it works on an A6700 2.00;")
    say("  every site was compared with the 2.00 update's files and each step was emulated, but these libraries have not run on a camera.")
    say("  A restart is possible and harmless (the patch is gone after it). Each step writes nothing unless its bytes are exactly the stock bytes.")
    if a.what in TESTS:
        say("This is DIAGNOSTIC %s (%s), NOT A STATE TO SHOOT WITH: it applies only the first steps of open gate, to show which step a camera" % (a.what[-1], " + ".join(steps)))
        say("  does not take. For open gate itself use open_gate_apply. What it does: %s" % EXPECT[a.what])
    elif a.what == "apply50":
        say("apply50 is for a camera set to PAL: step Q5 changes the 50p drive mode and writes nothing on an NTSC camera (the run then stops at Q5).")
        say("  It is the state the contributor's kit applies (its complete encoder design, M19). It cannot follow apply: put that back first, or cold boot.")
    elif a.what == "apply32":
        say("apply32 is a TEST of this project's own: the open-gate state with the exact 3:2 sensor window (5952x3968 from row 94) in the place of the")
        say("  contributed one (5952x3876 from row 214). Expected: the same as apply, with a picture that is not 2.4 % too tall, and 2.4 % more field of view in height.")
        say("  Nobody has run this window on an A6700, and the FX30 kit that uses it has not run either. If the picture is broken, black or the camera")
        say("  restarts: that is the result we need. Do not pull the battery first; follow the lines at the end.")
    elif a.what == "applyfull":
        say("applyfull is the 4K state with the contributed encoder design (M19) in the place of this project's (L19): 24p or 25p in XAVC HS, S and S-I.")
        say("  It cannot follow apply: put that back first, or cold boot. On a PAL camera 50p needs apply50 instead (its sensor step Q5).")
    elif a.what == "si":
        say("The S-I step follows apply (the 4K open-gate state): XAVC S-I 4K at 24p, or 25p on PAL. Put it back (si-putback) before putback.")
    elif a.what == "apply57":
        say("apply57 is the 5.76K state (5760x3840 files at 24p, or 25p on PAL). It cannot follow apply: put that back first, or cold boot.")
        say("  5.76K clips do not play in the camera: do NOT open playback while it is applied (the contributor reports a freeze that needs the battery out).")
        say("  The contributor recommends XAVC S-I 4K for it: long-GOP formats may drop frames.")
    elif a.what == "playback":
        say("The playback steps follow apply or apply50 (a 4K open-gate state). Three of them change instructions of av-cam.bin in memory.")
    elif not applying:
        say("It has to follow the matching apply of this kit.")
    say("A cold boot (battery out for 10 seconds) returns the camera to stock. Whether the power switch alone does on the A6700 is not known:")
    say("so KEEP THE CAMERA SWITCHED ON from now until the script says it is finished.")
    if a.what in APPLY_SETS + TESTS:
        say("Before you go on: the dial on %s, a charged battery," % STILL)
        say("and a camera that was cold booted and has not been on Movie or S&Q since. (If it starts on Movie: set the dial to the still position,")
        say("pull the battery for 10 seconds, put it back and switch on.) Step L13 changes the memory manager and needs that state.")
        say("(If the open-gate state is already applied in this power-on, its steps will say NOTHING TO DO: that is fine.)")
    else:
        say("Before you go on: a charged battery, and the dial on %s." % STILL)
    if input("Firmware version in the camera's menu: ").strip() != FIRMWARE:
        raise SystemExit("Not %s. Nothing was sent." % FIRMWARE)
    if input("Type YES to write to the camera's memory: ").strip() != "YES":
        raise SystemExit("Not confirmed. Nothing was sent.")
    for n, k in enumerate(steps, 1):
        if not wait_for_drive(n == 1):
            raise SystemExit("The camera did not show up as a USB drive. Stopped before step %d (%s)." % (n, k))
        say()
        say("=" * 78)
        say("Step %d of %d: %s, %s" % (n, len(steps), k, a6700_run.WRITE_STEPS[k][2]))
        cmd = [sys.executable, "-I", "-B", str(RUNNER), k, "--go", "--writes-memory", "--firmware-shown", FIRMWARE]
        clear = last_result_sha()
        if clear:
            cmd += ["--clear-result", clear]
        rc = subprocess.run(cmd).returncode
        which, f = step_outcome()
        if rc or which != k or not f or not f.get("ok"):
            say()
            say("STOPPED at step %d (%s): %s" % (n, k, "the session did not finish" if rc or which != k or not f else "outcome " + f["outcome"]))
            say("Steps before it are %s. To be sure of the camera's state: cold boot it (battery out for 10 seconds)." % ("applied" if applying else "put back"))
            text = " ".join((f or {}).get("problem_lines", []) + [str((f or {}).get("outcome_line"))])
            if k == "L13" and "nothing is written" in text:
                say("L13 refuses while the movie memory is laid out from the present records: cold boot with the dial on the still position, then apply again.")
            if k in ("Q5", "Q6") and "nothing is written" in text:
                say("Q5 / Q6 are for a PAL camera: on NTSC the 50p drive mode's stored record is not the one the step knows, and nothing is written.")
            if k in ("L5", "T5") and "nothing is written" in text:
                say("L5 (the contributed window) and T5 (the exact 3:2 test window) change the same places: put the other one back first, or cold boot.")
            if k in ("K16", "K19", "L16", "L19", "N19", "M19") and "nothing is written" in text:
                say("The states of apply, apply50 and apply57 cannot be mixed: put the other one back first, or cold boot.")
            say("Please send the newest folders in camera_private.")
            raise SystemExit(1)
    say()
    say("All %d steps passed (%s)." % (len(steps), a.what))
    if a.what in ("apply", "apply32", "applyfull", "apply50"):
        if a.no_meta:
            say("The files' MP4 headers say 3840x2160 (--no-meta): editors may open them squeezed; a remux to 3840x2560 fixes that.")
        else:
            say("The files' MP4 headers (tkhd, stsd, Sony's PROF) now say 3840x2560: editors should open them at 3:2 without a remux.")
        say("In-camera playback of these clips needs the playback steps (playback_fix_apply). Without them: if a clip says 'Unable to display',")
        say("  do NOT try again (on an FX3 a retry froze the camera); check the clips on a computer.")
    if a.what == "apply57":
        say("The files are 5760x3840. They do not play in the camera: check them on a computer. Do not open playback while this is applied.")
    if a.what == "playback":
        say("Playback: open one 3840x2560 clip in the camera. If it says 'Unable to display', do NOT try again; run dump_info and send camera_private.")
    if "S16" in steps:
        say("The screen step: on Movie the 3:2 rear screen should now be filled with the whole picture at its true shape. A circle should look round.")
        say("  While it is applied every 16:9 picture is shown stretched to 3:2 (other movie formats look wrong on the rear screen).")
        say("  Please report whether the focus and tracking frames sit on the subject, and what the viewfinder shows.")
    if closing:
        if a.no_movie_session:
            say(">>> Unplug USB, set %s, then run dump_info on Movie (after a restart too)." % MOVIE)
        else:
            movie_session(a.what if a.what in TESTS else None)
        say()
        if a.what in TESTS:
            for line in AFTER[a.what]:
                say(line)
            say("NEXT, for open gate itself: battery out for 10 seconds, switch on with the dial on the still position, and run open_gate_apply.")
            say("Please send the newest folders in camera_private, and what the screen did on Movie: a picture (which shape?), flashing,")
            say("  a restart? If it recorded: the clip's properties (size, frame rate), or the clip. To return to stock: battery out for 10 seconds.")
            return
        say({"applyfull": "Use only the 4K formats (XAVC HS, S or S-I) at 24p (25p on PAL) while it is applied: other frame rates are not set up and fail. "
                          "On PAL do NOT record 50p: without the 50p sensor step its picture is a 16:9 read-out stretched to 3:2.",
             "apply50": "Use only the 4K formats (XAVC HS, S or S-I) at 25p or 50p while it is applied: other frame rates are not set up and fail.",
             "apply57": "Use only the 4K formats at 24p (25p on PAL) while it is applied (XAVC S-I 4K recommended): other frame rates are not set up and fail."}
            .get(a.what, "Use only XAVC HS 4K or XAVC S 4K at 24p (25p on PAL) while it is applied (XAVC S-I 4K after the S-I step): other formats and frame rates are not set up and fail."))
        say("If the camera stops or restarts: do NOT pull the battery yet. Set the dial to the still position, replug USB and run dump_info, then send camera_private.")
        say("To return to stock: battery out for 10 seconds.")


if __name__ == "__main__":
    main()
