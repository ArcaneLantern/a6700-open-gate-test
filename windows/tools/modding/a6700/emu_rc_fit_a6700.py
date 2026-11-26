"""A6700 2.00 port (2026-11-26): build/emu_rc_fit.py's resize calculation run on the A6700's own code.

  C:\\Python313\\python.exe -B build\\emu_rc_fit_a6700.py [--trace]     -> evidence/a6700/sensor/rc_fit_a6700_emu.json

build/emu_rc_fit_fx30.py with this build's addresses (modding/A6700_PORT_SENSOR.md). The A6700's resize calculation is the FX30's (and so
the A7 IV's): the entry 0xb1d4ee equals the FX30's 0xa8c274 (match_thumb, one exact hit) and the core 0xb1cf6a lines up with 0xa8bcee
(diff_consts, 471 of 497 instructions). Its working structure is 0x16a70e8 (FX30 0x12ddef8), its module settings 0x19b7388.. (FX30
0x1573a30.., A7 IV 0x1452488..), its target calculation 0x13e6e0 (FX30 0x13d6f0).

Run with the same assumed settings as the A7 IV and FX30 runs (they reproduce the A7 IV camera's result blocks in all three camera cases)
and the A7 IV's input block with this sensor's reference width (5952, or 5612 for mode 0x830) and rows. As on the FX30 the path makes a
hardware-command call (0xb2137e, the FX30's 0xa8f67e) through the message buffer (get 0x559190 = FX30 0x5077e4): the buffer get is handed a
scratch buffer. Everything else is the firmware's own code, run as it is: no other call is stubbed (a call that left the image's code would
return 0 and be counted; --trace lists them: none in these runs).
No A6700 camera block exists to compare with; the A7 IV's code is run on the same cases for comparison.

What it answers: the stored record's vertical sampling ratio (+6/+7) decides whether the second scaler takes every row of the front end.
  - ogsq_a6700_v1:   5952 x 3876 with 165/191 (5952 x 3876 x 165/191 = 5952 x 3348.4, 16:9)
  - ogsq50_a6700_v1: 5612 x 3732 with 137/162 (5612 x 3732 x 137/162 = 5612 x 3156.1, 16:9)
Pass: with the design's ratio the second scaler takes the whole 2,438-row front end from row 0; with 1/1 it takes a 16:9 cut.
"""
import json
import struct
import sys
from pathlib import Path

from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import locate_file  # noqa: E402
import emu_rc_fit as AIV  # noqa: E402

IMG = locate_file.locate("a6700_200", "cpapp-b.bin").read_bytes()
BASE = 0x108000
MAP_LO, MAP_HI = 0x100000, 0x2800000
STACK_TOP, INP, PRM, OUTB, AUX, RET, SCRATCH = 0x2700000, 0x2710000, 0x2710100, 0x2710200, 0x2710400, 0x2720000, 0x2730000
ENTRY, WORK = 0xB1D4EE, 0x16A70E8
MSG_GET = 0x559190
# code the run may execute: the image's code (the resize module, its target calculation, getters and the compiler's arithmetic helpers)
OWN = ((0x108000, 0xD00000),)
STUB = set()                                   # nothing needs a stub on this build
SHIFT = 0x19B7388 - 0x1452488
SETTINGS = {a + SHIFT: b for a, b in AIV.SETTINGS.items()}


def run(ref, pa=(1, 1, 1, 1), width=5952, trace=None):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    try:
        uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A15)
    except Exception:
        pass
    uc.mem_map(MAP_LO, MAP_HI - MAP_LO)
    uc.mem_write(BASE, IMG)
    uc.reg_write(A.UC_ARM_REG_C1_C0_2, uc.reg_read(A.UC_ARM_REG_C1_C0_2) | (0xF << 20))
    uc.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
    for a, b in SETTINGS.items():
        uc.mem_write(a, b)
    w = list(AIV.INPUT_4K)
    w[13], w[14] = width, ref
    w[1], w[2], w[3], w[4] = pa[1], pa[3], pa[0], pa[2]
    uc.mem_write(INP, struct.pack("<20I", *w))
    uc.mem_write(PRM, AIV.PARAM_4K + bytes(0xBC - len(AIV.PARAM_4K)))
    uc.mem_write(OUTB, b"\0" * 0x200)
    log = {"unmapped": [], "stubbed": {}}
    state = {"last": ENTRY}

    def on_code(u, addr, size, _):
        if addr == RET:
            u.emu_stop()
            return
        if addr == MSG_GET:                              # message-buffer get: hand out a scratch buffer
            u.mem_write(u.reg_read(A.UC_ARM_REG_R1), struct.pack("<I", SCRATCH))
            log["stubbed"][hex(addr)] = log["stubbed"].get(hex(addr), 0) + 1
            u.reg_write(A.UC_ARM_REG_R0, 0)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
            return
        if addr in STUB or not any(lo <= addr < hi for lo, hi in OWN):   # a stubbed call: returns 0
            log["stubbed"][hex(addr)] = log["stubbed"].get(hex(addr), 0) + 1
            if trace is not None:
                trace.append((hex(state["last"]), hex(addr)))
            u.reg_write(A.UC_ARM_REG_R0, 0)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
            return
        state["last"] = addr

    def on_unmapped(u, access, addr, size, value, _):
        log["unmapped"].append(hex(addr))
        return False

    uc.hook_add(UC_HOOK_CODE, on_code)
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
    for r, v in zip((A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3), (INP, PRM, OUTB, AUX)):
        uc.reg_write(r, v)
    uc.reg_write(A.UC_ARM_REG_SP, STACK_TOP - 0x800)
    uc.reg_write(A.UC_ARM_REG_LR, RET | 1)
    err = None
    try:
        uc.emu_start(ENTRY | 1, RET, count=20_000_000)
    except UcError as e:
        err = f"{e} pc={uc.reg_read(A.UC_ARM_REG_PC):#x}"
    out = bytes(uc.mem_read(OUTB, 0x40))
    ws = bytes(uc.mem_read(WORK, 0xDC))
    r = struct.unpack_from("<10H", out)
    return {"words": list(r), "start": [round(r[2] + r[6] / 4096, 4), round(r[3] + r[7] / 4096, 4)],
            "size": [round(r[4] + r[8] / 4096, 4), round(r[5] + r[9] / 4096, 4)],
            "pixel_aspect_q12": struct.unpack_from("<i", ws, 0x48)[0], "error": err, "unmapped": log["unmapped"][:4], "calls_out_stubbed": log["stubbed"]}


CASES = (("stock 16:9 window 5952x3348", 3348, (1, 1, 1, 1), 5952, 3942, "stock"),
         ("open gate 5952x3876, ratio 1/1", 3876, (1, 1, 1, 1), 5952, 4672, "cut"),
         ("open gate 5952x3876, ratio 165/191 (ogsq_a6700_v1)", 3876, (1, 1, 165, 191), 5952, None, "whole"),
         ("open gate 5952x3968, ratio 27/32 (the FX30 design's window, for comparison)", 3968, (1, 1, 27, 32), 5952, 4672, "whole"),
         ("mode 0x830 stock 5612x3156", 3156, (1, 1, 1, 1), 5612, None, "stock"),
         ("mode 0x830 open gate 5612x3732, ratio 1/1", 3732, (1, 1, 1, 1), 5612, None, "cut"),
         ("mode 0x830 open gate 5612x3732, ratio 137/162 (ogsq50_a6700_v1)", 3732, (1, 1, 137, 162), 5612, None, "whole"))


def main():
    trace = [] if "--trace" in sys.argv else None
    res = {"about": __doc__, "assumed_settings": {hex(a): b.hex() for a, b in SETTINGS.items()}, "cases": {}}
    ok = True
    for name, ref, pa, width, a7iv_rows, want in CASES:
        e = run(ref, pa, width, trace)
        entry = {"a6700": e, "expected": want}
        cmp_ = ""
        if a7iv_rows:
            a = AIV.run(a7iv_rows, pa)
            entry["a7iv_same_case_7008_wide"] = {k: a[k] for k in ("start", "size", "pixel_aspect_q12")}
            cmp_ = f" | A7 IV {a['size']} from {a['start']}"
        good = e["error"] is None and ((want in ("stock", "whole") and e["size"][1] > 2437.9 and e["start"][1] < 1) or (want == "cut" and e["size"][1] < 2437))
        entry["as_expected"] = good
        ok &= good
        res["cases"][name] = entry
        print(f"{name:76} takes {e['size']} from {e['start']} (pixel aspect {e['pixel_aspect_q12']}) {'ok' if good else 'NOT AS EXPECTED'} {e['error'] or ''}{cmp_}")
    if trace is not None:
        seen = sorted(set(trace))
        print("calls out of the module (from, to):", seen)
    res["design_ratios_keep_every_row"] = ok
    out = ROOT / "evidence/a6700/sensor/rc_fit_a6700_emu.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf8", newline="\n")
    print("the designs' ratios keep every row:", ok)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
