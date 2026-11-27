"""Firmware-exact A6700 ISP geometry planner via Unicorn emulation of 0x269db0."""

from __future__ import annotations

import os
import struct
from typing import Dict, Optional, Tuple

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_THUMB, UC_PROT_ALL, Uc
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2,
    UC_ARM_REG_FPEXC,
    UC_ARM_REG_LR,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
    UC_ARM_REG_SP,
)

DEFAULT_FW_PATH = (
    r"a6700fw\out\firmware.tar_unpacked\0700_part_image\dev\nflasha8_unpacked\cpapp-b.bin"
)
FW_BASE = 0x108000
REC_SIZE = 3000

STOCK_MODES: Dict[str, Tuple[int, int, Tuple[int, ...]]] = {
    "5c0":  (0xD3597C, 0xD36534, (5976, 3148, 12, 4, 5952, 3140, 4624, 2438)),
    "7e0":  (0xD370EC, 0xD37CA4, (3864, 2176, 12, 8, 3840, 2160, 3840, 2160)),
    "8c0":  (0xD3885C, 0xD39414, (5976, 3356, 12, 4, 5952, 3348, 4336, 2438)),
    "830":  (0xD39FCC, 0xD3AB84, (5636, 3164, 12, 4, 5612, 3156, 4336, 2438)),
    "2820": (0xD3DA64, 0xD3E61C, (4672, 2628, 12, 6, 4648, 2616, 4336, 2438)),
}


def u16(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def u32(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


class FirmwareRecordPlanner:
    """Emulates A6700 cpapp-b.bin 0x269db0 (Case 0), 0x76316a, and 0x26944c."""

    def __init__(self, fw_path: str = DEFAULT_FW_PATH) -> None:
        self.fw_path = fw_path
        with open(fw_path, "rb") as f:
            self.fw = f.read()

        self.mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        cpacr = self.mu.reg_read(UC_ARM_REG_C1_C0_2)
        self.mu.reg_write(UC_ARM_REG_C1_C0_2, cpacr | 0x00F00000)
        self.mu.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

        fw_map_size = ((len(self.fw) + 0xFFF) // 0x1000) * 0x1000
        self.mu.mem_map(FW_BASE, fw_map_size, UC_PROT_ALL)
        self.mu.mem_write(FW_BASE, self.fw)

        self.mem_base = 0x02000000
        self.mu.mem_map(self.mem_base, 0x100000, UC_PROT_ALL)
        self.stop_addr = self.mem_base + 0x100
        self.mu.mem_write(self.stop_addr, b"\x00\xbf" * 8)

        names = [
            "arg0", "arg1", "arg2", "arg4", "arg5", "arg6", "arg7", "arg8",
            "OUT2_L", "OUT1_L", "OUT2_R", "OUT1_R", "OUT3",
            "in354_tmp", "scratch_out",
        ]
        self.bufs = {n: self.mem_base + 0x40000 + i * 0x2000 for i, n in enumerate(names)}
        self.sp_top = self.mem_base + 0x20000

    def _run_26944c(self, in354: bytes, tag: int) -> Tuple[int, bytes]:
        buf = bytearray(in354)
        struct.pack_into("<I", buf, 0x18, tag)
        self.mu.mem_write(self.bufs["in354_tmp"], bytes(buf))
        self.mu.mem_write(self.bufs["scratch_out"], b"\x00" * 0x800)

        self.mu.reg_write(UC_ARM_REG_SP, self.sp_top)
        self.mu.reg_write(UC_ARM_REG_LR, self.stop_addr | 1)
        self.mu.reg_write(UC_ARM_REG_R0, self.bufs["in354_tmp"])
        self.mu.reg_write(UC_ARM_REG_R1, self.bufs["scratch_out"] - 0x538)
        self.mu.emu_start(0x26944C | 1, self.stop_addr, timeout=500_000, count=100_000)
        ret = self.mu.reg_read(UC_ARM_REG_R0)
        data = bytes(self.mu.mem_read(self.bufs["scratch_out"], 0x9C))
        return ret, data

    def build_records(
        self,
        base_L: bytes,
        base_R: bytes,
        S: int,
        Sv: int,
        crop_x: int,
        crop_y: int,
        crop_w: int,
        crop_h: int,
        out_w: int,
        out_h: int,
        preserve_timing: bool = True,
        require_zero_ret: bool = True,
    ) -> Tuple[bytearray, bytearray, dict]:
        assert len(base_L) == REC_SIZE and len(base_R) == REC_SIZE
        assert crop_x >= 0 and crop_y >= 0
        assert crop_x + crop_w <= S, f"crop_x+crop_w={crop_x+crop_w} > S={S}"
        assert crop_y + crop_h <= Sv, f"crop_y+crop_h={crop_y+crop_h} > Sv={Sv}"

        right_crop = S - crop_x - crop_w
        bottom_crop = Sv - crop_y - crop_h

        v_top_0 = u16(base_L, 0x022)
        v_top_all = u16(base_L, 0x00A)
        assert v_top_all >= v_top_0, f"Invalid base vertical trim: 0x00a={v_top_all} < 0x022={v_top_0}"

        w_a0 = [
            0,
            u16(base_L, 0x01A),
            0,
            crop_x,
            crop_w,
            right_crop,
            0,
            u16(base_L, 0x018),
            0,
            0,
            v_top_0,
            v_top_all - v_top_0,
            crop_y,
            crop_h,
            bottom_crop,
            0,
        ]

        f46 = 1 if u16(base_L, 0x01C) != 0 else 0
        a0 = bytearray(0x60)
        struct.pack_into("<16H", a0, 0, *w_a0)
        struct.pack_into("<ff", a0, 0x38, 1.0, 1.0)
        struct.pack_into("<H", a0, 0x46, f46)
        a1 = bytearray(0x60)
        struct.pack_into("<16H", a1, 0, *w_a0)
        struct.pack_into("<ff", a1, 0x38, 1.0, 1.0)

        a4 = bytearray(self.fw[0xCD62A8 - FW_BASE : 0xCD62A8 - FW_BASE + 0x24])
        out3_flags = u32(base_L, 0x248)
        a4[0x0C] = 1 if (out3_flags & 1) == 0 else 0
        a4[0x11] = 1 if (out3_flags & 4) != 0 else 0
        a4[0x18] = 1 if (out3_flags & 8) == 0 else 0
        a4[0x1C] = 1 if (u16(base_L, 0x0C4) - u16(base_L, 0x160)) > 128 else 0
        a4[0x1D] = 1
        a4[0x1E] = 1

        a5 = struct.pack("<IIHH", 0, 0, 4096, 4096)
        a6 = struct.pack("<II", 1, 0)

        a7 = bytearray(self.fw[0xCD62D0 - FW_BASE : 0xCD62D0 - FW_BASE + 0x14])
        dev2_pack = u16(base_L, 0x83E)
        div_h = (dev2_pack & 0xFF) + 1
        div_v = (dev2_pack >> 8) + 1
        struct.pack_into("<HH", a7, 4, div_h, div_v)

        a8 = struct.pack("<HHHH", out_w, out_h, 0, 0)

        for n in ("OUT2_L", "OUT1_L", "OUT2_R", "OUT1_R", "OUT3"):
            self.mu.mem_write(self.bufs[n], b"\x00" * 0x1000)
        for k, v in (
            ("arg0", a0), ("arg1", a1), ("arg2", b""),
            ("arg4", a4), ("arg5", a5), ("arg6", a6), ("arg7", a7), ("arg8", a8),
        ):
            self.mu.mem_write(self.bufs[k], bytes(v).ljust(0x100, b"\x00"))

        captured: Dict[str, Optional[bytes]] = {"L": None, "R": None}
        sub_rets: Dict[str, int] = {}
        watch_calls = {
            0x26A678: "L_78edf2", 0x26A6A6: "L_78b6bc", 0x26A6CA: "L_78ba20",
            0x26A6EA: "L_78ba60", 0x26A714: "L_78bab2", 0x26A736: "L_78d236",
            0x26A744: "L_78a5bc", 0x26A756: "L_CamArc", 0x26A764: "L_269040",
            0x26A798: "L_26944c", 0x26A7A8: "L_CamNrs", 0x26A7B6: "L_CamSig",
            0x26A7C4: "L_CamLrc", 0x26A7D2: "L_Dev1",   0x26A7E0: "L_Dev2",
            0x26A814: "R_78b6bc", 0x26A82E: "R_78ba20", 0x26A84A: "R_78ba60",
            0x26A872: "R_78bab2", 0x26AE38: "R_78d236", 0x26AE42: "R_78a5bc",
            0x26AE54: "R_CamArc", 0x26AE5E: "R_269040", 0x26AE8E: "R_26944c",
            0x26AE98: "R_CamNrs", 0x26AEA2: "R_CamSig", 0x26AEAC: "R_CamLrc",
            0x26AEB6: "R_Dev1",   0x26AEC0: "R_Dev2",
        }
        ret_addrs = {addr + 4: name for addr, name in watch_calls.items()}

        def hook_code(uc: Uc, addr: int, size: int, user_data: object) -> None:
            if addr == 0x26A798:
                captured["L"] = bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R0), 0x40))
            elif addr == 0x26AE8E:
                captured["R"] = bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R0), 0x40))
            if addr in ret_addrs:
                sub_rets[ret_addrs[addr]] = uc.reg_read(UC_ARM_REG_R0)

        h = self.mu.hook_add(UC_HOOK_CODE, hook_code, begin=0x26A600, end=0x26AECC)
        try:
            stack_args = [
                self.bufs[k]
                for k in ("arg4", "arg5", "arg6", "arg7", "arg8", "OUT2_L", "OUT1_L", "OUT2_R", "OUT1_R", "OUT3")
            ]
            sp = self.sp_top - 4 * len(stack_args)
            self.mu.mem_write(sp, struct.pack("<10I", *stack_args))
            self.mu.reg_write(UC_ARM_REG_SP, sp)
            self.mu.reg_write(UC_ARM_REG_LR, self.stop_addr | 1)
            self.mu.reg_write(UC_ARM_REG_R0, self.bufs["arg0"])
            self.mu.reg_write(UC_ARM_REG_R1, self.bufs["arg1"])
            self.mu.reg_write(UC_ARM_REG_R2, self.bufs["arg2"])
            self.mu.reg_write(UC_ARM_REG_R3, 0)
            self.mu.emu_start(0x269DB0 | 1, self.stop_addr, timeout=2_000_000, count=500_000)
            r0_main = self.mu.reg_read(UC_ARM_REG_R0)
        finally:
            self.mu.hook_del(h)

        if require_zero_ret:
            assert r0_main == 0, f"0x269db0 returned non-zero 0x{r0_main:08x}, sub_rets={sub_rets}"

        for key in ("OUT2_L", "OUT2_R"):
            self.mu.reg_write(UC_ARM_REG_SP, self.sp_top)
            self.mu.reg_write(UC_ARM_REG_LR, self.stop_addr | 1)
            self.mu.reg_write(UC_ARM_REG_R0, self.bufs[key])
            self.mu.reg_write(UC_ARM_REG_R1, self.bufs["OUT3"])
            self.mu.emu_start(0x76316A | 1, self.stop_addr, timeout=500_000, count=10_000)

        out2_L = bytes(self.mu.mem_read(self.bufs["OUT2_L"], 0x234))
        out2_R = bytes(self.mu.mem_read(self.bufs["OUT2_R"], 0x234))
        out1_L = bytes(self.mu.mem_read(self.bufs["OUT1_L"], 0x84C))
        out1_R = bytes(self.mu.mem_read(self.bufs["OUT1_R"], 0x84C))
        out3 = bytes(self.mu.mem_read(self.bufs["OUT3"], 12))

        gen_L = bytearray(base_L)
        gen_R = bytearray(base_R)

        # Apply OUT2 (0x000..0x1d8; note 0x1d8..0x234 is AF/PD secondary crop handled statically)
        gen_L[0x000:0x1D8] = out2_L[0x000:0x1D8]
        gen_R[0x000:0x1D8] = out2_R[0x000:0x1D8]

        # Apply OUT1[0x3cc:0x84c] -> ROM[0x4c0:0x940] (includes Dev2 tail up to 0x93c)
        gen_L[0x4C0:0x940] = out1_L[0x3CC:0x84C]
        gen_R[0x4C0:0x940] = out1_R[0x3CC:0x84C]

        if preserve_timing:
            gen_L[0x5A4:0x5AE] = base_L[0x5A4:0x5AE]
            gen_R[0x5A4:0x5AE] = base_R[0x5A4:0x5AE]

        # Alternate 0x26944c blocks at 0x9d8, 0xa78, 0xb18
        alt_rets = {}
        if a4[0x18] == 1:
            for side, gen_X, cap in (("L", gen_L, captured["L"]), ("R", gen_R, captured["R"])):
                assert cap is not None, f"Failed to capture 0x26944c input for {side}"
                for slot in (0x9D8, 0xA78, 0xB18):
                    tag = u32(base_L if side == "L" else base_R, slot)
                    if 1 <= tag <= 6:
                        ret_alt, block = self._run_26944c(cap, tag)
                        alt_rets[f"{side}_0x{slot:03x}_tag{tag}"] = ret_alt
                        if require_zero_ret:
                            assert ret_alt == 0, f"0x26944c tag {tag} on {side} returned {ret_alt}"
                        gen_X[slot + 4 : slot + 0xA0] = block

        info = {
            "r0_main": r0_main,
            "sub_rets": sub_rets,
            "alt_rets": alt_rets,
            "out3": struct.unpack("<3I", out3),
            "div_hv": (div_h, div_v),
            "a4_1c": a4[0x1C],
        }
        return gen_L, gen_R, info


def diff_u16_offsets(a: bytes | bytearray, b: bytes | bytearray) -> list[tuple[int, int, int]]:
    diffs = []
    for o in range(0, len(a), 2):
        va, vb = u16(a, o), u16(b, o)
        if va != vb:
            diffs.append((o, va, vb))
    return diffs


def main() -> None:
    planner = FirmwareRecordPlanner()
    print("plan1.py: A6700 stock dual-half self-test via cpapp-b.bin 0x269db0 Case 0")
    for name, (va_L, va_R, geom) in STOCK_MODES.items():
        base_L = planner.fw[va_L - FW_BASE : va_L - FW_BASE + REC_SIZE]
        base_R = planner.fw[va_R - FW_BASE : va_R - FW_BASE + REC_SIZE]
        gen_L, gen_R, info = planner.build_records(base_L, base_R, *geom)
        dL = diff_u16_offsets(gen_L, base_L)
        dR = diff_u16_offsets(gen_R, base_R)
        print(
            f"  {name:4s}: r0=0x{info['r0_main']:x} out3={[hex(x) for x in info['out3']]} "
            f"diffs_L={len(dL)} {[(hex(o), a, b) for o, a, b in dL[:6]]} "
            f"diffs_R={len(dR)} {[(hex(o), a, b) for o, a, b in dR[:6]]}"
        )
        assert gen_L == base_L, f"{name} L mismatch: {[(hex(o), a, b) for o, a, b in dL]}"
        assert gen_R == base_R, f"{name} R mismatch: {[(hex(o), a, b) for o, a, b in dR]}"
    print("PASS: 5/5 A6700 stock dual-half modes matched 3000/3000 exact bytes on L and R.")


if __name__ == "__main__":
    main()
