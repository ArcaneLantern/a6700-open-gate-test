"""Build A6700 Open Gate 6K (5760x3840) candidate design og57n32_a6700_v1.json and evaluate row-214 fallback."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, r"a6700_6k")
import plan1

OGSQ32_PATH = Path(r"a6700fw\a6700-open-gate-test\windows\tools\modding\designs\ogsq32_a6700_v1.json")
OGSQ214_PATH = Path(r"a6700fw\a6700-open-gate-test\windows\tools\modding\designs\ogsq_a6700_v1.json")
OUT_JSON_PATH = Path(r"a6700_6k\og57n32_a6700_v1.json")


def find_record_patches(patches: list[dict]) -> tuple[dict, dict]:
    by_addr = {str(p["addr"]).lower(): p for p in patches if p.get("kind") == "R"}
    return by_addr["0xd3885c"], by_addr["0xd39414"]


def extract_lrc_summary(rec: bytes | bytearray) -> dict:
    return {
        "input": [plan1.u16(rec, 0x77E), plan1.u16(rec, 0x77C)],
        "output": [plan1.u16(rec, 0x782), plan1.u16(rec, 0x780)],
        "step_q12": [plan1.u16(rec, 0x786), plan1.u16(rec, 0x784)],
        "start": [plan1.u16(rec, 0x788), plan1.u16(rec, 0x78C)],
    }


def evaluate_row214_fallback(planner: plan1.FirmwareRecordPlanner) -> dict:
    with OGSQ214_PATH.open("r", encoding="utf-8") as f:
        ogsq = json.load(f)
    pL, pR = find_record_patches(ogsq["patches"])
    base_L = bytes.fromhex(pL["new"])
    base_R = bytes.fromhex(pR["new"])
    gen_L, gen_R, info = planner.build_records(
        base_L,
        base_R,
        S=5976,
        Sv=3884,
        crop_x=12,
        crop_y=4,
        crop_w=5952,
        crop_h=3876,
        out_w=5760,
        out_h=3840,
        require_zero_ret=False,
    )
    sh_L, sv_L = plan1.u16(gen_L, 0x786), plan1.u16(gen_L, 0x784)
    sh_R, sv_R = plan1.u16(gen_R, 0x786), plan1.u16(gen_R, 0x784)
    return {
        "design": ogsq["design"],
        "geometry": {"S": 5976, "Sv": 3884, "crop": [12, 4, 5952, 3876], "out": [5760, 3840]},
        "r0_main": info["r0_main"],
        "all_sub_rets_zero": all(v == 0 for v in info["sub_rets"].values()),
        "all_alt_rets_zero": all(v == 0 for v in info["alt_rets"].values()),
        "out3": [hex(x) for x in info["out3"]],
        "lrc_L": extract_lrc_summary(gen_L),
        "lrc_R": extract_lrc_summary(gen_R),
        "step_q12_L": [sh_L, sv_L],
        "step_q12_R": [sh_R, sv_R],
        "out_h_0x17a": [plan1.u16(gen_L, 0x17A), plan1.u16(gen_R, 0x17A)],
        "dev2_0x93c": [plan1.u16(gen_L, 0x93C), plan1.u16(gen_R, 0x93C)],
        "bic7_0x698": [plan1.u16(gen_L, o) for o in (0x698, 0xA48, 0xAE8, 0xB88)],
        "picture_aspect": round(5952 / 3876, 4),
        "aspect_distortion_pct": round((5952 / 3876 / 1.5 - 1.0) * 100.0, 2),
    }


def main() -> None:
    with OGSQ32_PATH.open("r", encoding="utf-8") as f:
        ogsq32 = json.load(f)

    planner = plan1.FirmwareRecordPlanner()

    p32_L, p32_R = find_record_patches(ogsq32["patches"])
    stock_L = bytes.fromhex(p32_L["old"])
    stock_R = bytes.fromhex(p32_R["old"])
    base32_L = bytes.fromhex(p32_L["new"])
    base32_R = bytes.fromhex(p32_R["new"])

    # Sanity check against stock table bytes in loaded cpapp-b.bin
    assert stock_L == planner.fw[0xD3885C - plan1.FW_BASE : 0xD3885C - plan1.FW_BASE + plan1.REC_SIZE]
    assert stock_R == planner.fw[0xD39414 - plan1.FW_BASE : 0xD39414 - plan1.FW_BASE + plan1.REC_SIZE]

    gen_L, gen_R, info = planner.build_records(
        base32_L,
        base32_R,
        S=5976,
        Sv=3976,
        crop_x=12,
        crop_y=4,
        crop_w=5952,
        crop_h=3968,
        out_w=5760,
        out_h=3840,
        require_zero_ret=True,
    )

    assert info["r0_main"] == 0, f"r0_main={info['r0_main']}"
    assert all(v == 0 for v in info["sub_rets"].values()), f"sub_rets non-zero: {info['sub_rets']}"
    assert all(v == 0 for v in info["alt_rets"].values()), f"alt_rets non-zero: {info['alt_rets']}"

    # Hardware-specific assertions
    assert plan1.u16(gen_L, 0x17A) == 3844 and plan1.u16(gen_R, 0x17A) == 3844, "pad_v=2 check failed"
    assert plan1.u16(gen_L, 0x786) == 4233 and plan1.u16(gen_L, 0x784) == 4233, "L sh/sv != 4233"
    assert plan1.u16(gen_R, 0x786) == 4233 and plan1.u16(gen_R, 0x784) == 4233, "R sh/sv != 4233"
    assert plan1.u16(gen_L, 0x93C) == 732 and plan1.u16(gen_R, 0x93C) == 732, "Dev2 0x93c != 732"

    expected_bic7 = ((3976 // 2) + 7) & ~7
    assert expected_bic7 == 1992
    for o in (0x698, 0xA48, 0xAE8, 0xB88):
        assert plan1.u16(gen_L, o) == 1992, f"L[{hex(o)}] != 1992"
        assert plan1.u16(gen_R, o) == 1992, f"R[{hex(o)}] != 1992"

    lrc_L = extract_lrc_summary(gen_L)
    lrc_R = extract_lrc_summary(gen_R)
    for side, lrc_s, rec in (("L", lrc_L, gen_L), ("R", lrc_R, gen_R)):
        assert lrc_s["input"][0] <= 4800 and lrc_s["output"][0] <= 4800, f"{side} width > 4800: {lrc_s}"
        assert plan1.u16(rec, 0x160) <= 4800, f"{side} 0x160 > 4800"

    fields_L = len(plan1.diff_u16_offsets(stock_L, gen_L))
    fields_R = len(plan1.diff_u16_offsets(stock_R, gen_R))

    # Row-214 fallback evaluation
    fb = evaluate_row214_fallback(planner)

    # Construct og57n32_a6700_v1.json preserving ogsq32 schema
    out_design = copy.deepcopy(ogsq32)
    out_design["design"] = "og57n32_a6700_v1"
    out_design["title"] = (
        "A6700 Open Gate 6K (5760x3840) candidate from exact 3:2 window (row 94): "
        "5952x3968 crop -> 5760x3840 stage-1 Lrc front end (1:1 square pixels, sh=sv=4233) "
        "in modes 0x820/0x880/0x890/0x8c0/0x8d0, vertical sampling ratio 27/32"
    )
    out_design["generated_by"] = "a6700_6k/build1.py (plan1.FirmwareRecordPlanner)"
    out_design["ported_from"] = {
        "sensor_base": "ogsq32_a6700_v1",
        "reference": "a7iv_og57n_v1",
        "how": "ogsq32_a6700_v1 T5 sensor cells + PDAF/aux base records with stage-1 Lrc output replanned via Unicorn emulation of A6700 cpapp-b.bin 0x269db0 Case 0 for 5760x3840",
    }

    for p in out_design["patches"]:
        addr_lo = str(p["addr"]).lower()
        if addr_lo == "0xd3885c":
            p["new"] = bytes(gen_L).hex()
            p["note"] = (
                f"left picture record of modes 0x820/0x880/0x890/0x8c0/0x8d0: first stage 5976x3976 "
                f"(crop 5952x3968 from row 94), native 5760x3840 Lrc front end (pad_v=2 -> 3844, "
                f"sh=sv=4233, bic#7=1992, Dev2_0x93c=732); {fields_L} fields differ from stock"
            )
        elif addr_lo == "0xd39414":
            p["new"] = bytes(gen_R).hex()
            p["note"] = (
                f"right picture record of modes 0x820/0x880/0x890/0x8c0/0x8d0: first stage 5976x3976 "
                f"(crop 5952x3968 from row 94), native 5760x3840 Lrc front end (pad_v=2 -> 3844, "
                f"sh=sv=4233, bic#7=1992, Dev2_0x93c=732); {fields_R} fields differ from stock"
            )

    sensor_cells = [p for p in out_design["patches"] if p.get("kind") == "S"]
    rec_patches = [p for p in out_design["patches"] if p.get("kind") == "R"]
    assert len(sensor_cells) == 52 and len(rec_patches) == 2

    total_bytes = sum(len(bytes.fromhex(p["old"])) for p in out_design["patches"])
    s = out_design["summary"]
    s["front_end"] = [5760, 3840]
    s["lrc"] = {"L": lrc_L, "R": lrc_R}
    s["record_fields_changed"] = {"L": fields_L, "R": fields_R}
    s["sites"] = len(out_design["patches"])
    s["bytes"] = total_bytes
    s["sensor_cells"] = len(sensor_cells)
    s["records"] = len(rec_patches)
    s["picture_aspect"] = 1.5
    s["file_aspect"] = 1.5
    s["lrc_out_h_0x17a"] = 3844
    s["lrc_step_q12"] = [4233, 4233]
    s["bic7_sv_align_u16"] = 1992
    s["dev2_0x93c"] = 732
    s["expected_working_state"] = {
        "crop": [5952, 3968],
        "first_stage": [5976, 3976],
        "front_end": [5760, 3840],
        "second_scaler_takes": "the whole 5760x3840 front end (1:1 to 5760x3840 file with K16, or 3840x2560 with L16)",
        "file": [5760, 3840],
    }
    s["row214_fallback_eval"] = fb
    out_design["not_shown"] = [
        "anything on a physical camera (untested on hardware)",
        "whether the IMX671-family sensor accepts first-row register 175 (<256) and 3980 rows read at 25p line rate",
        "real-time bus/DRAM/encoder bandwidth and thermal behavior at 552.96 MP/s (5760x3840x25p)",
        "live dual-half seam alignment and PDAF focus accuracy in real capture",
    ]

    OUT_JSON_PATH.write_text(json.dumps(out_design, indent=1) + "\n", encoding="utf-8", newline="\n")

    print(f"build1.py: wrote {OUT_JSON_PATH}")
    print(
        f"  og57n32_a6700_v1: sites={len(out_design['patches'])} ({len(sensor_cells)} S + 2 R), "
        f"bytes={total_bytes}, r0=0x{info['r0_main']:x}, out3={[hex(x) for x in info['out3']]}"
    )
    print(f"  Lrc L={lrc_L}")
    print(f"  Lrc R={lrc_R}")
    print(f"  0x17a=3844, sh=sv=4233, 0x93c=732, bic#7(0x698/a48/ae8/b88)=1992, changed u16 L={fields_L} R={fields_R}")
    print(
        f"  row214 fallback ({fb['design']}): r0=0x{fb['r0_main']:x}, sub_ok={fb['all_sub_rets_zero']}, "
        f"alt_ok={fb['all_alt_rets_zero']}, step_q12_L={fb['step_q12_L']} (aspect={fb['picture_aspect']}, "
        f"distortion={fb['aspect_distortion_pct']:+.2f}%), bic7={fb['bic7_0x698']}"
    )


if __name__ == "__main__":
    main()
