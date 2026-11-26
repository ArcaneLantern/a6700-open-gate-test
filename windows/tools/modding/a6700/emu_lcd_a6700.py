"""Emulate the A6700 2.00 rear-screen layout pieces, stock and with lcdfill_a6700_v2 / lcdfill_a6700_v3 applied, in Unicorn on the
A6700's own code. (A6700 port, 2026-11-26; made from build/emu_lcd_fx2.py.)

  C:\\Python313\\python.exe -B build\\emu_lcd_a6700.py [--save]        (--save writes evidence/a6700/screen/lcdfill_a6700_emu.json)

Functions run (cpapp-b.bin 2.00, loaded at 0x108000), each called the way its caller calls it:
  0x1f5f48  fit mode (panel code, picture aspect code)                                   (the A7 IV's 0x1e4b78, byte for byte)
  0x1f6170  picture ratio: (_, w | h << 16, panel code, aspect, [fit, flags, out])       -> out = x, y, w, h     (layout 0x1f6274)
  0x1f6a18  panel code of an output: (output, accessor); output 1 reads the rear type byte RAM 0x1a7c0e0, output 2 the second one's
            0x1a7c210, through the tables 0x1f6abc and 0xd04cdc
  0x6cecca  the test that forces the letterbox (0x6ba32a): a picture record with the sizes at +0x38 / +0x3e / +0x40
  0x128438  frame check of cpActAfWindow: 0x63e13c -> output kind (0 rear, 2 second output), 0x634b36 -> the live-view rectangle
            (y0, y1, x0, x1) and the output size, 0x634dbc -> table row (0 or 1); the model's aspect at +0x1c10 (4 = the 16:9 column)
  0x129288  frame check of cpActTrackingFrame: 0x63cb2a -> the live-view rectangle on the 640 x 480 grid (as the real one gives it),
            0x63cb94 -> the output size, 0x63cf44 -> table row, 0x63cf52 -> the model's aspect
Panels: 720 x 480 (3:2: the A6700's rear monitor, panel code 1, frame row 1) and 1024 x 768 (4:3: the viewfinder, panel code 0, the
second output, frame row 2). Picture aspect 2 (16:9) is the open-gate live view. Every expected value is asserted. Read-only apart from
the evidence file.
"""
import json
import struct
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import locate_file  # noqa: E402

B = 0x108000
FX = locate_file.locate("a6700_200", "cpapp-b.bin").read_bytes()
DESIGNS = {n: json.loads((ROOT / "modding/designs" / (n + ".json")).read_text(encoding="utf8")) for n in ("lcdfill_a6700_v2", "lcdfill_a6700_v3")}
RET, STK, OBJ = 0x2410000, 0x2300000, 0x2440000
PANELS = {"3:2 (rear monitor)": (720, 480, 1, 0, 1), "4:3 (viewfinder)": (1024, 768, 0, 2, 0)}      # w, h, panel code, output kind for the checks, row selector
FIT, RATIO, PANEL_BY_TYPE, FORCE_TEST, CHECK_AF, CHECK_TRK = 0x1F5F48, 0x1F6170, 0x1F6A18, 0x6CECCA, 0x128438, 0x129288
TYPE_REAR, TYPE_SECOND = 0x1A7C0E0, 0x1A7C210


class Cp:
    def __init__(self, design=None):
        img = bytearray(FX)
        if design:
            for s in DESIGNS[design]["sites"]:
                a = int(s["ram_address"], 16)
                assert img[a - B:a - B + 4] == bytes.fromhex(s["old"])
                img[a - B:a - B + 4] = bytes.fromhex(s["new"])
            for g in DESIGNS[design]["guards"]:
                a = int(g["ram_address"], 16)
                assert img[a - B:a - B + len(g["bytes"]) // 2] == bytes.fromhex(g["bytes"])
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        try:
            uc.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A15)
        except Exception:
            pass
        uc.mem_map(0x100000, 0x2500000)
        uc.mem_write(B, bytes(img))
        uc.reg_write(A.UC_ARM_REG_C1_C0_2, uc.reg_read(A.UC_ARM_REG_C1_C0_2) | (0xF << 20))
        uc.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.stubs, self.log = {}, []
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, acc, addr, sz, v, _: self.log.append(f"unmapped {addr:#x} pc={u.reg_read(A.UC_ARM_REG_PC):#x}") or False)

    def stub(self, addr, fn):
        """fn(uc) -> r0 (or None to leave r0); the stubbed function returns to LR at once"""
        if addr not in self.stubs:
            self.uc.hook_add(UC_HOOK_CODE, lambda u, ad, sz, _: self._run_stub(ad), begin=addr, end=addr)
        self.stubs[addr] = fn

    def _run_stub(self, addr):
        u = self.uc
        r0 = self.stubs[addr](u)
        if r0 is not None:
            u.reg_write(A.UC_ARM_REG_R0, r0 & 0xFFFFFFFF)
        u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))

    def call(self, fn, regs, stack=()):
        u = self.uc
        sp = STK - 0x800
        for i, v in enumerate(stack):
            u.mem_write(sp + 4 * i, struct.pack("<I", v & 0xFFFFFFFF))
        for r, v in zip((A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3), regs):
            u.reg_write(r, v & 0xFFFFFFFF)
        u.reg_write(A.UC_ARM_REG_SP, sp)
        u.reg_write(A.UC_ARM_REG_LR, RET | 1)
        u.emu_start(fn | 1, RET, count=200000)
        assert not self.log, self.log
        assert u.reg_read(A.UC_ARM_REG_PC) == RET, hex(u.reg_read(A.UC_ARM_REG_PC))
        return u.reg_read(A.UC_ARM_REG_R0)

    def fit(self, panel, aspect):
        return self.call(FIT, (panel, aspect))

    def ratio(self, w, h, panel, aspect, flags=0, fit=None):
        out = OBJ + 0x8000
        self.uc.mem_write(out, bytes(8))
        self.call(RATIO, (0, w | h << 16, panel, aspect), (self.fit(panel, aspect) if fit is None else fit, flags, out))
        return list(struct.unpack("<4H", bytes(self.uc.mem_read(out, 8))))

    def panel_code(self, output, type_byte):
        self.uc.mem_write(TYPE_REAR if output == 1 else TYPE_SECOND, bytes([type_byte]))
        return self.call(PANEL_BY_TYPE, (output, 0))

    def force_letterbox(self, w, h, first=0):
        rec = OBJ + 0x9000
        self.uc.mem_write(rec, bytes(0x80))
        self.uc.mem_write(rec + 0x38, struct.pack("<H", first))
        self.uc.mem_write(rec + 0x3E, struct.pack("<HH", w, h))
        return self.call(FORCE_TEST, (rec,))

    def check_af(self, live, out_w, out_h, kind, row_sel, model_aspect=4):
        """cpActAfWindow's check; live = (x, y, w, h) in output pixels; 1 when the widget accepts it"""
        m = OBJ + 0x10000
        u = self.uc
        u.mem_write(m, bytes(0x3000))
        u.mem_write(m + 0x1C10, struct.pack("<I", model_aspect))
        x, y, w, h = live

        def lv(uc):
            sp = uc.reg_read(A.UC_ARM_REG_SP)
            p_h = struct.unpack("<I", bytes(uc.mem_read(sp, 4)))[0]
            uc.mem_write(uc.reg_read(A.UC_ARM_REG_R1), struct.pack("<4i", y, y + h, x, x + w))
            uc.mem_write(uc.reg_read(A.UC_ARM_REG_R3), struct.pack("<H", out_w))
            uc.mem_write(p_h, struct.pack("<H", out_h))
            return 1
        self.stub(0x63E13C, lambda uc: kind)
        self.stub(0x634B36, lv)
        self.stub(0x634DBC, lambda uc: row_sel)
        return self.call(CHECK_AF, (m,))

    def check_tracking(self, live, out_w, out_h, kind, row_sel, model_aspect=4):
        """cpActTrackingFrame's check; its getter hands the rectangle over on the 640 x 480 grid, as the real 0x63cb2a computes it"""
        m = OBJ + 0x10000
        u = self.uc
        u.mem_write(m, bytes(0x3000))
        x, y, w, h = live

        def lv(uc):
            y0, x0 = y * 480 // out_h, x * 640 // out_w
            uc.mem_write(uc.reg_read(A.UC_ARM_REG_R1), struct.pack("<4i", y0, y0 + h * 480 // out_h, x0, x0 + w * 640 // out_w))
            return 1

        def size(uc):
            uc.mem_write(uc.reg_read(A.UC_ARM_REG_R2), struct.pack("<H", out_w))
            uc.mem_write(uc.reg_read(A.UC_ARM_REG_R3), struct.pack("<H", out_h))
            return None
        self.stub(0x63E13C, lambda uc: kind)
        self.stub(0x63CB2A, lv)
        self.stub(0x63CB94, size)
        self.stub(0x63CF44, lambda uc: row_sel)
        self.stub(0x63CF52, lambda uc: model_aspect)
        return self.call(CHECK_TRK, (m,))


def run():
    st, v2, v3 = Cp(), Cp("lcdfill_a6700_v2"), Cp("lcdfill_a6700_v3")
    res = {"designs": {n: d["artifact_sha256"] for n, d in DESIGNS.items()}, "cases": []}
    case = lambda **k: res["cases"].append(k)
    rear, evf = "3:2 (rear monitor)", "4:3 (viewfinder)"
    # ---- the panel code of the two outputs from their type bytes (stock code; the designs do not touch it)
    want_code = {1: 2, 2: 0, 3: 1}
    for t, code in want_code.items():
        assert st.panel_code(1, t) == code, (t, st.panel_code(1, t))
    assert st.panel_code(1, 4) == 2 and st.panel_code(2, 2) == 0 and st.panel_code(2, 1) == 2 and st.panel_code(2, 3) == 0
    case(what="panel code from the type byte (0x1f6a18)", rear_output={"type 1": 2, "type 2": 0, "type 3": 1, "type 4 or more (counted as 1)": 2},
         second_output={"type 1": 2, "type 2 or more (counted as 2)": 0}, panel_codes={"0": "4:3", "1": "3:2", "2": "16:9"})
    # ---- fit mode: of the 36 (panel code, aspect) pairs exactly one changes, in both designs
    changed = {name: [(p, a, st.fit(p, a), cp.fit(p, a)) for p in range(6) for a in range(6) if st.fit(p, a) != cp.fit(p, a)] for name, cp in (("v2", v2), ("v3", v3))}
    assert changed["v2"] == changed["v3"] == [(1, 2, 3, 0)], changed
    case(what="fit mode, all 36 pairs of panel code 0..5 and picture aspect code 0..5", changed_pairs=1,
         the_one="16:9 picture (code 2) on the 3:2 panel (code 1): 3 letterbox -> 0 fill", v2_equals_v3=True)
    for name, (w, h, pc, _, _) in PANELS.items():
        case(what="fit mode, 16:9 picture", panel=name, stock=st.fit(pc, 2), v2=v2.fit(pc, 2), v3=v3.fit(pc, 2))
    assert st.fit(2, 2) == v2.fit(2, 2) == v3.fit(2, 2) == 0 and st.fit(5, 2) == v3.fit(5, 2) == 2          # HDMI's kinds of panel code: untouched
    # ---- the live view (de-squeeze does not exist on this camera)
    want = {rear: ([0, 38, 720, 404], [0, 0, 720, 480], [0, 0, 720, 480]), evf: ([0, 96, 1024, 576], [0, 96, 1024, 576], [0, 42, 1024, 684])}
    for name, (w, h, pc, _, _) in PANELS.items():
        got = [cp.ratio(w, h, pc, 2) for cp in (st, v2, v3)]
        assert got == list(want[name]), (name, got)
        case(what="live view, 16:9 picture (the open-gate frame)", panel=name, stock=got[0], v2=got[1], v3=got[2],
             shown_aspect={"stock": round(got[0][2] / got[0][3], 4), "v2": round(got[1][2] / got[1][3], 4), "v3": round(got[2][2] / got[2][3], 4)},
             note="v2 and v3: the whole 3:2 panel" if name == rear else "v2 leaves the viewfinder's 16:9 letterbox (the squeezed frame, as on the A7 IV); v3 gives it the 3:2 height")
        for asp in (0, 1, 3, 5):                                          # every other picture shape is untouched
            assert st.ratio(w, h, pc, asp) == v2.ratio(w, h, pc, asp) == v3.ratio(w, h, pc, asp), (name, asp)
        case(what="live view, other picture aspect codes 0, 1, 3, 5", panel=name, stock_equals_v2_equals_v3=True)
    assert abs(want[rear][1][2] / want[rear][1][3] - 1.5) < 0.001 and abs(want[evf][2][2] / want[evf][2][3] - 1.5) < 0.01
    # the 100/235 case of a 16:9 picture (flag bit 0) is not the designs' business: unchanged, on the 4:3 panel with a letterbox
    w, h, pc = PANELS[evf][:3]
    a = [cp.ratio(w, h, pc, 2, flags=1) for cp in (st, v2, v3)]
    assert a[0] == a[1] == a[2] == [0, 167, 1024, 434], a
    case(what="live view, 16:9 picture with the 2.35:1 flag (letterbox 100/235)", panel=evf, stock=a[0], v2=a[1], v3=a[2])
    # v3 on a 3:2 panel if the fit word were not read (fit 3): the ratio alone also gives the whole panel
    assert v3.ratio(720, 480, 1, 2, fit=3) == [0, 0, 720, 480] and st.ratio(720, 480, 1, 2, fit=3) == [0, 38, 720, 404]
    case(what="v3's ratio words alone on the 3:2 panel (fit left at 3)", stock=[0, 38, 720, 404], v3=[0, 0, 720, 480])
    # ---- the test that forces the letterbox: only 1920 x 816 and 3840 x 1632 pictures
    forced = {"%dx%d" % s: st.force_letterbox(*s) for s in ((1920, 816), (3840, 1632), (1920, 1080), (3840, 2160), (3840, 2560), (5760, 3840), (1920, 1280))}
    assert forced == {"1920x816": 1, "3840x1632": 1, "1920x1080": 0, "3840x2160": 0, "3840x2560": 0, "5760x3840": 0, "1920x1280": 0}, forced
    case(what="forced letterbox test 0x6cecca (would override the fill)", results=forced)
    # ---- the two frame checks
    for label, chk in (("cpActAfWindow 0x128438", "check_af"), ("cpActTrackingFrame 0x129288", "check_tracking")):
        w, h, pc, kind, row = PANELS[rear]
        s_live, f_live = want[rear][0], want[rear][1]
        ok = lambda cp, live, k=kind, rs=row, ow=w, oh=h: getattr(cp, chk)(live, ow, oh, k, rs)
        r = {"stock_tables_stock_view": ok(st, s_live), "v2_tables_filled_view": ok(v2, f_live), "v3_tables_filled_view": ok(v3, f_live),
             "stock_tables_filled_view": ok(st, f_live), "v2_tables_stock_view": ok(v2, s_live)}
        assert r == {"stock_tables_stock_view": 1, "v2_tables_filled_view": 1, "v3_tables_filled_view": 1, "stock_tables_filled_view": 0, "v2_tables_stock_view": 0}, (label, r)
        case(what="frame check (%s), rear output, table row 1" % label, panel=rear, **r,
             note="stock tables with the filled view fail: the fit word alone would lose the focus frames (the A7 IV's F966)")
        for asp, col in ((3, "3:2"), (2, "4:3"), (1, "1:1")):             # the other columns of row 1 are untouched: a 3:2, 4:3 and 1:1 picture
            lv_ = st.ratio(w, h, pc, {3: 1, 2: 0, 1: 3}[asp])
            assert getattr(st, chk)(lv_, w, h, kind, row, asp) == getattr(v2, chk)(lv_, w, h, kind, row, asp) == getattr(v3, chk)(lv_, w, h, kind, row, asp) == 1, (label, col, lv_)
        case(what="frame check (%s), rear output, the 3:2, 4:3 and 1:1 pictures" % label, panel=rear, stock=1, v2=1, v3=1)
        w, h, pc, kind, row = PANELS[evf]
        s_live, t_live = want[evf][0], want[evf][2]
        r = {"stock_tables_stock_view": ok(st, s_live, kind, row, w, h), "v2_tables_stock_view": ok(v2, s_live, kind, row, w, h),
             "v3_tables_v3_view": ok(v3, t_live, kind, row, w, h), "v3_tables_stock_view": ok(v3, s_live, kind, row, w, h),
             "stock_tables_v3_view": ok(st, t_live, kind, row, w, h)}
        assert r == {"stock_tables_stock_view": 1, "v2_tables_stock_view": 1, "v3_tables_v3_view": 1, "v3_tables_stock_view": 0, "stock_tables_v3_view": 0}, (label, r)
        case(what="frame check (%s), second output (the viewfinder), table row 2" % label, panel=evf, **r)
        # Which row each panel uses, from the stock geometry alone (the stock camera draws its frames on both): only row 1 takes the stock
        # 16:9 view of a 3:2 panel, and only row 2 takes the centred 3:2 picture of a 4:3 panel (row 0's 3:2 entry is top-aligned)
        rw, rh, rpc = PANELS[rear][:3]
        rear_rows = {"row 0": getattr(st, chk)(want[rear][0], rw, rh, 0, 0), "row 1": getattr(st, chk)(want[rear][0], rw, rh, 0, 1)}
        still = st.ratio(w, h, pc, 1)                                     # a 3:2 picture in the viewfinder: centred
        evf_rows = {"row 0": getattr(st, chk)(still, w, h, 0, 0, 3), "row 2": getattr(st, chk)(still, w, h, kind, row, 3)}
        assert rear_rows == {"row 0": 0, "row 1": 1} and evf_rows == {"row 0": 0, "row 2": 1} and still == [0, 42, 1024, 684], (rear_rows, evf_rows, still)
        case(what="frame check (%s), stock: which table row fits each panel's stock view" % label,
             rear_3x2_panel_16x9_view=rear_rows, viewfinder_4x3_panel_3x2_picture=evf_rows, viewfinder_3x2_picture_view=still)
        # the same viewfinder checks on an 800 x 600 output (the tables are on a 640 x 480 grid: the output size does not matter)
        s8, t8 = st.ratio(800, 600, 0, 2), v3.ratio(800, 600, 0, 2)
        assert ok(st, s8, kind, row, 800, 600) == ok(v2, s8, kind, row, 800, 600) == ok(v3, t8, kind, row, 800, 600) == 1 and ok(v3, s8, kind, row, 800, 600) == 0
        case(what="frame check (%s), second output at 800 x 600" % label, stock_view=s8, v3_view=t8, stock=1, v2=1, v3=1)
    return res


if __name__ == "__main__":
    res = run()
    for c in res["cases"]:
        print(json.dumps(c))
    print(f"{len(res['cases'])} cases as expected")
    if "--save" in sys.argv:
        out = ROOT / "evidence" / "a6700" / "screen" / "lcdfill_a6700_emu.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf8", newline="\n")
        print("wrote", out)
