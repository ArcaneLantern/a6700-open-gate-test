"""Mandatory blind validation gate for plan1.py before building A6700 6K."""

from __future__ import annotations

import json
import sys
from typing import Tuple

sys.path.insert(0, r"a6700_6k")
import plan1

A7IV_Q7_PATH = r"a6700fw\work\ref\a7iv_ogsq_v3.json"
A7IV_N7_PATH = r"a6700fw\work\ref\a7iv_og57n_v1.json"


def load_patch_rec(patches: list[dict], addr_hex: str, field: str) -> bytes:
    for p in patches:
        if str(p.get("addr", "")).lower() == addr_hex.lower():
            return bytes.fromhex(p[field])
    raise KeyError(f"Patch {addr_hex} not found")


def main() -> None:
    planner = plan1.FirmwareRecordPlanner()

    # --- 1. A6700 self & cross checks ---
    va8_L, va8_R, geom8 = plan1.STOCK_MODES["8c0"]
    va5_L, va5_R, geom5 = plan1.STOCK_MODES["5c0"]
    va83_L, va83_R, geom83 = plan1.STOCK_MODES["830"]
    r8_L = planner.fw[va8_L - plan1.FW_BASE : va8_L - plan1.FW_BASE + plan1.REC_SIZE]
    r8_R = planner.fw[va8_R - plan1.FW_BASE : va8_R - plan1.FW_BASE + plan1.REC_SIZE]
    r5_L = planner.fw[va5_L - plan1.FW_BASE : va5_L - plan1.FW_BASE + plan1.REC_SIZE]
    r5_R = planner.fw[va5_R - plan1.FW_BASE : va5_R - plan1.FW_BASE + plan1.REC_SIZE]
    r83_L = planner.fw[va83_L - plan1.FW_BASE : va83_L - plan1.FW_BASE + plan1.REC_SIZE]
    r83_R = planner.fw[va83_R - plan1.FW_BASE : va83_R - plan1.FW_BASE + plan1.REC_SIZE]

    g83_L, g83_R, _ = planner.build_records(r83_L, r83_R, *geom83)
    assert bytes(g83_L) == r83_L and bytes(g83_R) == r83_R, "830 self-rebuild failed"
    print("A6700 830 self-rebuild: PASS (3000/3000 L & R)")

    def stage1_diffs(a: bytes | bytearray, b: bytes | bytearray) -> list[int]:
        out = []
        for o, _, _ in plan1.diff_u16_offsets(a, b):
            if o < 0x1D8 or (0x4C0 <= o < 0x940) or (0x9D8 <= o < 0xBB8):
                out.append(o)
        return out

    g8to5_L, g8to5_R, _ = planner.build_records(r8_L, r8_R, *geom5)
    d85_L = stage1_diffs(g8to5_L, r5_L)
    d85_R = stage1_diffs(g8to5_R, r5_R)
    print("A6700 8c0->5c0 stage1 diffs (expected only 0x5ac):", [hex(o) for o in d85_L], [hex(o) for o in d85_R])
    assert set(d85_L) <= {0x5AC} and set(d85_R) <= {0x5AC}

    g5to8_L, g5to8_R, _ = planner.build_records(r5_L, r5_R, *geom8)
    d58_L = stage1_diffs(g5to8_L, r8_L)
    d58_R = stage1_diffs(g5to8_R, r8_R)
    print("A6700 5c0->8c0 stage1 diffs (expected only 0x5ac):", [hex(o) for o in d58_L], [hex(o) for o in d58_R])
    assert set(d58_L) <= {0x5AC} and set(d58_R) <= {0x5AC}

    # --- 2. A7 IV stock (s7 -> s7) check (from ogsq_v3 old) ---
    with open(A7IV_Q7_PATH, "r", encoding="utf-8") as f:
        q7_json = json.load(f)
    s7_L = load_patch_rec(q7_json["patches"], "0xbf7638", "old")
    s7_R = load_patch_rec(q7_json["patches"], "0xbf81f0", "old")
    q7_L = load_patch_rec(q7_json["patches"], "0xbf7638", "new")
    q7_R = load_patch_rec(q7_json["patches"], "0xbf81f0", "new")

    gs7_L, gs7_R, _ = planner.build_records(s7_L, s7_R, 7032, 3958, 12, 8, 7008, 3942, 4336, 2438)
    assert bytes(gs7_L) == s7_L and bytes(gs7_R) == s7_R, (
        f"s7 self-rebuild diffs L={plan1.diff_u16_offsets(gs7_L, s7_L)} R={plan1.diff_u16_offsets(gs7_R, s7_R)}"
    )
    print("A7 IV stock s7 self-rebuild: PASS (3000/3000 L & R)")

    # --- 3. BLIND GATE: generate n7 (5760x3840) purely from q7 + external target geometry ---
    gen_n7_L, gen_n7_R, info = planner.build_records(
        q7_L, q7_R,
        S=7032, Sv=4688,
        crop_x=12, crop_y=8, crop_w=7008, crop_h=4672,
        out_w=5760, out_h=3840,
    )
    print(f"Blind n7 generation complete: r0=0x{info['r0_main']:x}, out3={[hex(x) for x in info['out3']]}")

    # Load real a7iv_og57n_v1.json ONLY now for final comparison
    with open(A7IV_N7_PATH, "r", encoding="utf-8") as f:
        n7_json = json.load(f)
    real_n7_L = load_patch_rec(n7_json["patches"], "0xbf7638", "new")
    real_n7_R = load_patch_rec(n7_json["patches"], "0xbf81f0", "new")

    diffs_L = plan1.diff_u16_offsets(gen_n7_L, real_n7_L)
    diffs_R = plan1.diff_u16_offsets(gen_n7_R, real_n7_R)
    exact_L = sum(1 for a, b in zip(gen_n7_L, real_n7_L) if a == b)
    exact_R = sum(1 for a, b in zip(gen_n7_R, real_n7_R) if a == b)
    print(f"BLIND GATE A7 IV n7 L: {exact_L}/3000 exact bytes, u16_diffs={len(diffs_L)} {[(hex(o), a, b) for o, a, b in diffs_L]}")
    print(f"BLIND GATE A7 IV n7 R: {exact_R}/3000 exact bytes, u16_diffs={len(diffs_R)} {[(hex(o), a, b) for o, a, b in diffs_R]}")

    assert plan1.u16(gen_n7_L, 0x93C) == 732 and plan1.u16(real_n7_L, 0x93C) == 732, "0x93C mismatch L"
    assert plan1.u16(gen_n7_R, 0x93C) == 732 and plan1.u16(real_n7_R, 0x93C) == 732, "0x93C mismatch R"

    expected_sv_diffs = {
        (0x698, 2344, 2349),
        (0xA48, 2344, 2349),
        (0xAE8, 2344, 2349),
        (0xB88, 2344, 2349),
    }
    assert set(diffs_L) == expected_sv_diffs and exact_L == 2996, f"Unexpected L diffs: {diffs_L}"
    assert set(diffs_R) == expected_sv_diffs and exact_R == 2996, f"Unexpected R diffs: {diffs_R}"

    # Verify preserving q7's pre-existing input-height Sv slots (0x698/0xa48/0xae8/0xb88) gives 3000/3000
    stage1_out_L = bytearray(gen_n7_L)
    stage1_out_R = bytearray(gen_n7_R)
    for o in (0x698, 0xA48, 0xAE8, 0xB88):
        stage1_out_L[o : o + 2] = q7_L[o : o + 2]
        stage1_out_R[o : o + 2] = q7_R[o : o + 2]
    assert bytes(stage1_out_L) == real_n7_L, "Stage-1 output update L failed 3000/3000"
    assert bytes(stage1_out_R) == real_n7_R, "Stage-1 output update R failed 3000/3000"
    print("PASS: BLIND GATE A7 IV og57n_v1 2996/3000 full (exact 4 q7 bic-#7 Sv artifacts) and 3000/3000 stage-1 output on L & R!")


if __name__ == "__main__":
    main()
