"""Designs lcdfill_a6700_v2 and lcdfill_a6700_v3: the A6700 2.00 rear screen (a 3:2 panel) shows the open-gate live view at 3:2 with the
focus frames (v2); v3 adds the viewfinder (a 4:3 panel). A6700 port, 2026-11-26; notes: modding/A6700_PORT_SCREEN.md.

  work\\venv\\Scripts\\python.exe -I -B build\\build_lcd_a6700.py      writes modding/designs/lcdfill_a6700_v2.json, lcdfill_a6700_v3.json
                                                                       and camera_tests/CT6_memory_read_check/helper_a6700/lcd_regions_a6700.json

The open-gate live view is a 16:9 frame (picture aspect code 2) holding the taller sensor area squeezed vertically, as on the A7 IV.
The A6700's display code is the A7 IV / A7C II / ZV-E1 form, not the FX3 / FX30 form (every fact below is asserted against cpapp-b.bin
2.00, loaded at 0x108000; all words are in the file and are changed in coprocessor RAM only):

(a) The fit-mode function 0x1f5f48 with its three word tables is the A7 IV's 0x1e4b78 byte for byte (0x94 bytes; the only copy in the
    image). The table of a 16:9 picture is 0x1f5f98 = 3, 3, 0, 0, 0, 2 for panel codes 0..5; the function reads it each call
    (`adr r0, 0x1f5f98; ldr.w r0, [r0, r2, lsl #2]` at 0x1f5f74). The word for panel code 1 (3:2):
        0x1f5f9c   3 (letterbox) -> 0 (fill)                                      = the A7 IV's working lcdfill word 0x1e4bcc (F791)
    With fit 0 the picture-ratio function 0x1f6170 gives the whole output: the 3:2 panel stretches the 16:9 frame to 3:2.
(b) The frame widgets. The A6700 has TWO rectangle tables, as the ZV-E1 (no cpActAfWindowRemoteSend in this firmware), and each has
    FOUR aspect columns, not five (the A7 IV's table without its fifth column): 3 rows x 4 x (x, y, w, h) u16 on a 640 x 480 grid.
        cpActAfWindow       check 0x128438, table 0xe99e30, column table 0xcae880 (model aspect - 1 -> 2, 1, 0, 3, 0, 3)
        cpActTrackingFrame  check 0x129288, table 0xe99e90, column table 0xcae9c0 (the same values)
    Row = 0 or 1 for the rear output (a model word; 1 on a 3:2 panel, as on the A7 IV), 2 for the second output (the viewfinder).
    The 16:9 column is 3. Row 1's entry (0, 38, 640, 404) -> (0, 0, 640, 480), so both checks accept the filled live view (without
    this no focus frame is drawn: the A7 IV's F966, fixed by lcdfill_v2, F969):
        0xe99e68 / 0xe99e6c  and  0xe99ec8 / 0xe99ecc
    These five words are exactly the contributed kit's lcdfill_a6700_v2 sites (work/contrib; compared below when it is there). The
    contributed design lists 7 guards, which its header generator drops; here they are kept, with three more of the A7 IV design's kind.
(c) v3 only, the viewfinder. Its panel code is 0 (4:3): fit stays 3 (letterbox), and the letterbox of a 16:9 picture gets the height
    width x 9/16, so the viewfinder shows the squeezed frame (as the A7 IV's does). The picture-ratio function 0x1f6170 is the A7S III's
    instruction form; its 16:9 constants become the function's own 3:2 pair, the change that works on the A7S III (lcdratio32_s3_v1):
        0x1f61a4  moveq.w lr, #9 -> #2          0x1f61a8  it eq; moveq r0, #16 -> #3
    and row 2's 16:9 entry (0, 60, 640, 360) -> (0, 26, 640, 428) in both tables (the firmware's own rectangle of a 3:2 picture there).
    On the 3:2 rear panel the ratio then gives the whole panel as well, so (a)'s word and (c)'s constants agree there.
Panel shape: a byte the camera sets at start-up. Rear: RAM 0x1a7c0e0 ([0x1a7c0c4 + 0x1c], read by 0x69ed42; >= 4 counts as 1);
second output (viewfinder): 0x1a7c210 ([0x1a7c1f4 + 0x1c], 0x69ed54; >= 2 counts as 2). Type -> panel code (0x1f6a18, tables 0x1f6abc
and 0xd04cdc): 3 -> 1 (3:2), 2 -> 0 (4:3), 1 -> 2 (16:9). Sony gives the A6700's monitor as 1,036,800 dots = 720 x 480 x 3 (3:2) and
the viewfinder as 2,359,296 dots = 1024 x 768 x 3 (4:3). Not read on a camera.
No De-Squeeze Display words: the A6700 2.00 menu has no such setting (appFw.so holds only the shared EXTERN_VAL_DE_SQUEEZE_DISP names,
no setting_de_squeeze_disp), so the calculator 0x6ba392 (codes 1 and 2 only) is never taken. That is why this design has 5 words where
the FX2's has 18 and the FX30's 30.
While applied, every 16:9 picture on the rear screen is stretched to 3:2 (other movie formats and 16:9 playback look wrong there
until the step is put back). Checked by build/emu_lcd_a6700.py (Unicorn, the A6700's own functions). Nothing here talks to a camera.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import locate_file  # noqa: E402

B, BUILD = 0x108000, "a6700_200"
FX = locate_file.locate(BUILD, "cpapp-b.bin").read_bytes()
A4 = locate_file.locate("a7iv_602", "cpapp-b.bin").read_bytes()
SHA = "61b7fe5c0ce227ea865d799b81fe77ae359b7c5dcd39d13c9c2241d9cad23559"
MD = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
fx = lambda a, n: FX[a - B:a - B + n]
a4 = lambda a, n: A4[a - B:a - B + n]

FIT_FN, FIT_TABLE, FIT_SITE, A4_FIT_FN, FIT_LEN = 0x1F5F48, 0x1F5F98, 0x1F5F9C, 0x1E4B78, 0x94
RATIO_FN, RATIO_END, LAYOUT_FN, PANEL_FN, PANEL_BY_TYPE, DSQ_FN, DSQ_ACTIVE, FORCE_FN, FORCE_TEST = \
    0x1F6170, 0x1F6272, 0x1F6274, 0x6B9A5E, 0x1F6A18, 0x6BA392, 0x6CED2E, 0x6BA32A, 0x6CECCA
PANEL_TYPE_REAR, PANEL_TYPE_SECOND = 0x1A7C0E0, 0x1A7C210
# (name, table, check function, where the check forms the table's address, its column table, A7 IV table)
TABLES = (("cpActAfWindow (focus area frames)", 0xE99E30, 0x128438, 0x12854C, 0xCAE880, 0xD7B560),
          ("cpActTrackingFrame (tracking and face frames)", 0xE99E90, 0x129288, 0x1293BE, 0xCAE9C0, 0xD7B650))
ROWS, COLS, COL_169 = 3, 4, 3
TABLE_LEN = 8 * ROWS * COLS
RECT_169 = {0: (0, 60, 640, 360), 1: (0, 38, 640, 404), 2: (0, 60, 640, 360)}
RECT_FILL, RECT_32_ON_43 = (0, 0, 640, 480), (0, 26, 640, 428)
ROW_NAME = {0: "rear output, row 0", 1: "rear output, 3:2 panel", 2: "second output (the viewfinder)"}
rect = lambda r: struct.pack("<4H", *r)
entry = lambda t, row, col=COL_169: t + 8 * (COLS * row + col)
CONTRIB = ROOT / "work/contrib/a6700_v1.0/A6700 OpenGate/a6700-opengate_v1.0/designs/lcdfill_a6700_v2.json"
REGIONS = ROOT / "camera_tests/CT6_memory_read_check/helper_a6700/lcd_regions_a6700.json"


def insn(a, n=4):
    i = next(MD.disasm(fx(a, n), a), None)
    return (i.mnemonic, i.op_str) if i else None


def movw_movt(addr):
    i = list(MD.disasm(fx(addr, 24), addr))
    assert i[0].mnemonic == "movw", (hex(addr), i[0].mnemonic)
    rd, lo = i[0].op_str.split(", #")
    hi = next(x for x in i[1:] if x.mnemonic == "movt" and x.op_str.startswith(rd + ","))
    return int(hi.op_str.split("#")[1], 16) << 16 | int(lo, 16)


def calls(a, n):
    return ["%s %s" % (i.mnemonic, i.op_str) for i in MD.disasm(fx(a, n), a) if i.mnemonic in ("bl", "b.w")]


def check_context():
    """Facts the designs rest on, each read from the A6700 2.00 image (and the A7 IV 6.02 image where it is the reference)."""
    assert hashlib.sha256(FX).hexdigest() == SHA
    facts = {}
    # (a) fit function and tables: the A7 IV's, the only copy; the 16:9 table and how it is read
    assert fx(FIT_FN, FIT_LEN) == a4(A4_FIT_FN, FIT_LEN) and FX.count(fx(FIT_FN, FIT_LEN)) == 1
    assert struct.unpack("<6I", fx(FIT_TABLE, 24)) == (3, 3, 0, 0, 0, 2)
    assert fx(0x1F5F70, 10) == bytes.fromhex("062a" "ecd2" "08a0" "50f82200")            # cmp r2, #6; bhs; adr r0, table; ldr.w r0, [r0, r2, lsl #2]
    assert insn(0x1F5F74, 2) == ("adr", "r0, #0x20") and ((0x1F5F74 + 4) & ~3) + 0x20 == FIT_TABLE
    # the layout 0x1f6274: panel code, fit, the forced-letterbox test, de-squeeze active -> calculator, else the picture-ratio function
    got = calls(LAYOUT_FN, 0x2F0)
    for t in (PANEL_FN, FIT_FN, FORCE_FN, DSQ_ACTIVE, DSQ_FN, RATIO_FN):
        assert "bl #%#x" % t in got, hex(t)
    facts["layout_calls"] = [hex(t) for t in (PANEL_FN, FIT_FN, FORCE_FN, DSQ_ACTIVE, DSQ_FN, RATIO_FN)]
    # the fit is overridden to 3 only for a 1920 x 816 or 3840 x 1632 picture (0x6ba32a -> 0x6cecca): not the open-gate picture
    assert fx(FORCE_TEST + 0x10, 4) == bytes.fromhex("b1f54c7f") and fx(FORCE_TEST + 0x16, 4) == bytes.fromhex("b2f5f06f")      # 0x330, 0x780
    assert fx(FORCE_TEST + 0x22, 4) == bytes.fromhex("b1f5cc6f") and fx(FORCE_TEST + 0x28, 4) == bytes.fromhex("b2f5706f")      # 0x660, 0xf00
    # panel code: outputs 1, 2, 4 and 0x20 go to 0x1f6a18; rear type byte [0x1a7c0c4 + 0x1c] (>= 4 -> 1), second [0x1a7c1f4 + 0x1c] (>= 2 -> 2)
    assert "b.w #%#x" % PANEL_BY_TYPE in calls(PANEL_FN, 0x2C)
    c = calls(PANEL_BY_TYPE, 0x40)
    assert "bl #0x69ed42" in c and "bl #0x69ed54" in c
    assert movw_movt(0x69ED42) == PANEL_TYPE_REAR - 0x1C and fx(0x69ED4A, 8) == bytes.fromhex("007f" "0428" "28bf" "0120")
    assert movw_movt(0x69ED54) == PANEL_TYPE_SECOND - 0x1C and fx(0x69ED5C, 8) == bytes.fromhex("007f" "0228" "28bf" "0220")
    t1, t2 = struct.unpack("<4I", fx(0x1F6ABC, 16)), struct.unpack("<3I", fx(0xD04CDC, 12))
    assert insn(0x1F6A4E, 2) == ("adr", "r1, #0x6c") and ((0x1F6A4E + 4) & ~3) + 0x6C == 0x1F6ABC and movw_movt(0x1F6A54) == 0xD04CDC
    assert [t2[t1[k]] for k in (1, 2, 3)] == [2, 0, 1]
    facts["panel_code_by_type"] = {"1": 2, "2": 0, "3": 1}
    # (b) two frame tables of 3 rows x 4 columns: the A7 IV's without its fifth column; each check forms its table and its column table
    assert b"cpActAfWindowRemoteSend" not in FX and b"cpActAfWindow" in FX and b"cpActTrackingFrame" in FX
    assert FX.count(rect(RECT_169[1])) == 2
    for name, t, chk, mv, ct, t4 in TABLES:
        for r in range(ROWS):
            assert fx(t + 8 * COLS * r, 8 * COLS) == a4(t4 + 40 * r, 8 * COLS), (name, r)
            assert fx(entry(t, r), 8) == rect(RECT_169[r])
        assert movw_movt(mv) == t and struct.unpack("<6I", fx(ct, 24)) == (2, 1, 0, 3, 0, 3), name
    assert fx(0xE99E30, TABLE_LEN) == fx(0xE99E90, TABLE_LEN) and not any(fx(0xE99EF0, 8))
    assert fx(0x128554, 8) == bytes.fromhex("02eb4010" "30f93120")       # add.w r0, r2, r0, lsl #5; ldrsh.w r2, [r0, r1, lsl #3]: row x 32 + column x 8
    assert fx(0x1293C6, 8) == bytes.fromhex("01eb4511" "31f93020")
    assert movw_movt(0x12853C) == 0xCAE880 and movw_movt(0x1293AE) == 0xCAE9C0
    # the model's aspect: movw r1, #0x1c10 ... ldr.w r1, [r8, r1]; subs r1, #1; cmp r1, #5
    assert fx(0x128516, 4) == bytes.fromhex("41f61041") and fx(0x128522, 4) == bytes.fromhex("58f80110") and fx(0x12852E, 2) == bytes.fromhex("0139") \
        and fx(0x128534, 2) == bytes.fromhex("0529")
    assert struct.unpack("<3d", fx(0x128618, 24)) == (480.0, 640.0, 0.0) and fx(0x128568, 4) == bytes.fromhex("b1ee044b")   # 640 x 480 grid, 5.0
    assert struct.unpack("<2d", fx(0x129488, 16)) == (480.0, 640.0) and fx(0x1293DA, 4) == bytes.fromhex("b1ee040b")
    # (c) the picture-ratio function: the A7S III's instruction form, its own 3:2 pair (lr 2, r0 3) and the 16:9 constants
    assert fx(RATIO_FN, 4) == bytes.fromhex("80b56f46") and insn(0x1F618C) == ("mov.w", "lr, #2") and insn(0x1F6190, 2) == ("movs", "r0, #3")
    assert fx(0x1F61A2, 10) == bytes.fromhex("08bf" "4ff0090e" "08bf" "1020") and FX.count(bytes.fromhex("4ff0090e08bf1020")) == 1
    # no De-Squeeze Display setting on this camera: the calculator reads its code at slot 0x778 and knows codes 1 and 2 only
    assert fx(DSQ_FN + 0x10, 4) == bytes.fromhex("d0f87817") and fx(DSQ_FN + 0x1E, 6) == bytes.fromhex("0228" "15d0" "0128")
    try:
        app = locate_file.locate(BUILD, "appFw.so").read_bytes()
        assert b"setting_de_squeeze_disp" not in app and b"EXTERN_VAL_DE_SQUEEZE_DISP_OFF" in app
        facts["appfw_has_desqueeze_setting"] = False
    except SystemExit:
        facts["appfw_has_desqueeze_setting"] = "appFw.so not located: not checked"
    return facts


def G(a, n, note):
    return {"ram_address": hex(a), "bytes": fx(a, n).hex(), "note": note + ", as in the file"}


def fill_sites():
    sites = [{"ram_address": hex(FIT_SITE), "old": "03000000", "new": "00000000",
              "note": "VDF fit mode for a 16:9 picture on a 3:2 panel (table 0x1f5f98 for picture code 2, entry for panel code 1): 3 letterbox to 0 fill. "
                      "The rear screen then stretches the 16:9 live view over the whole 3:2 panel [A7 IV 0x1e4bcc]"}]
    for name, t, chk, _, _, _ in TABLES:
        e = entry(t, 1)
        old, new = rect(RECT_169[1]), rect(RECT_FILL)
        for off, part in ((0, "x, y"), (4, "w, h")):
            sites.append({"ram_address": hex(e + off), "old": old[off:off + 4].hex(), "new": new[off:off + 4].hex(),
                          "note": "%s, check %#x: expected live-view rectangle for a 16:9 picture on the rear 3:2 panel (row 1, column 3), %s: "
                                  "stock %s to %s" % (name, chk, part, RECT_169[1], RECT_FILL)})
    return sites


def fill_guards(ratio_case=True):
    g = [G(FIT_FN, 16, "first 16 bytes of the fit-mode function 0x1f5f48 [A7 IV 0x1e4b78]"),
         G(0x1F5F88, 16, "last 16 bytes of the fit-mode function before its tables [A7 IV 0x1e4bb8]"),
         G(FIT_TABLE, 4, "picture code 2 (16:9), panel code 0 (4:3): 3 letterbox (the viewfinder's entry, left alone)"),
         G(0x1F5FA0, 16, "picture code 2, panel codes 2 to 5: 0, 0, 0, 2"),
         G(0x1F5FB0, 16, "the table for picture code 1 (3:2), panel codes 0 to 3: 3, 0, 2, 0")]
    if ratio_case:
        g.append(G(0x1F61A4, 16, "the picture-ratio function's 16:9 constants (moveq.w lr, #9; it eq; moveq r0, #16) and the 1:1 case"))
    for name, t, _, _, _, _ in TABLES:
        e = entry(t, 1)
        g += [G(e - 8, 8, "%s: the entry before (1:1 on the rear 3:2 panel: 107, 0, 426, 480)" % name.split(" ")[0]),
              G(e + 8, 8, "%s: the entry after (row 2, a 3:2 picture: 0, 26, 640, 428)" % name.split(" ")[0])]
    return g


def finish(name, title, sites, guards, facts, extra):
    spans = sorted([(int(s["ram_address"], 16), 4) for s in sites] + [(int(g["ram_address"], 16), len(g["bytes"]) // 2) for g in guards])
    assert all(a + n <= b for (a, n), (b, _) in zip(spans, spans[1:])), "a guard overlaps a site or a guard"
    assert all(int(s["ram_address"], 16) % 4 == 0 and fx(int(s["ram_address"], 16), 4) == bytes.fromhex(s["old"]) and s["old"] != s["new"] for s in sites)
    assert all(int(g["ram_address"], 16) % 4 == 0 and 0 < len(g["bytes"]) // 2 <= 16 for g in guards)
    d = {"design": name, "build": BUILD, "camera": "ILCE-6700 (A6700), firmware 2.00", "title": title, "kind": "ram_words",
         "artifact": "cpapp-b.bin 2.00 (ILCE-6700), its loaded image in coprocessor RAM: the words are in the file, the change is made in RAM only",
         "artifact_sha256": SHA, "generated_by": "build/build_lcd_a6700.py", "checked_in_the_image": facts}
    d.update(extra)
    d["sites"], d["guards"] = sites, guards
    return d


def design_v2(facts):
    sites, guards = fill_sites(), fill_guards()
    contributed = "the contributed file is not on this machine: not compared"
    if CONTRIB.is_file():                              # data only: the contributed design's sites and guards, compared
        c = json.loads(CONTRIB.read_text(encoding="utf8"))
        assert sorted((s["ram_address"], s["old"], s["new"]) for s in c["sites"]) == sorted((s["ram_address"], s["old"], s["new"]) for s in sites)
        ours = {g["ram_address"]: g["bytes"] for g in guards}
        assert all(ours.get(g["ram_address"], "").startswith(g["bytes"]) for g in c["guards"]) and len(c["guards"]) == 7
        contributed = ("the 5 sites equal the contributed lcdfill_a6700_v2's (work/contrib/a6700_v1.0), and each of its 7 guards is covered by one of these %d "
                       "(same address, the same bytes; its 8-byte guard at 0x1f61a4 is 16 bytes here)" % len(guards))
    assert len(sites) == 5 and len(guards) == 10
    return finish("lcdfill_a6700_v2",
                  "Rear screen (LCD) at 3:2 in movie mode with the focus frames: VDF fills the 3:2 panel with the 16:9 live view, and the two frame "
                  "widgets expect the live view there (A6700 2.00)", sites, guards, facts,
                  {"ported_from": {"design": "lcdfill_v2", "build": "a7iv_602", "note": "works on an A7 IV (F791, F969); the ZV-E1's lcdfill_zv_v2 is the same two-table form"},
                   "contributed": contributed,
                   "table": "VDF fit-mode table 0x1f5f98 (function 0x1f5f48 = A7 IV 0x1e4b78) and the frame widgets' rectangle tables 0xe99e30 (cpActAfWindow) and "
                            "0xe99e90 (cpActTrackingFrame): 3 rows x 4 aspect columns, entry row 1 (rear 3:2 panel), column 3 (16:9)",
                   "summary": {"sites": len(sites), "bytes": 4 * len(sites), "guards": len(guards), "panel": "rear LCD, 3:2 (panel code 1 from type byte 3 at RAM 0x1a7c0e0, expected)",
                               "picture": "16:9 live view (picture code 2)", "fit_stock": "letterbox (3)", "fit_new": "fill (0)",
                               "frame_rectangle_stock": list(RECT_169[1]), "frame_rectangle_new": list(RECT_FILL),
                               "viewfinder": "unchanged: a 4:3 panel (panel code 0) keeps the 16:9 letterbox and shows the squeezed frame, as on the A7 IV",
                               "goes_with": ["the A6700 open-gate state"]},
                   "while_applied": "every 16:9 picture on the rear screen is stretched over the 3:2 panel (other movie formats and 16:9 playback look wrong there until the "
                                    "step is put back); the viewfinder and HDMI are unchanged",
                   "not_shown": ["anything on a camera by us (the contributor reports the rear screen filled with working focus and tracking frames)",
                                 "the rear panel type byte 0x1a7c0e0 (expected 3 = 3:2 from Sony's 1,036,800 dots = 720 x 480; a dump should read it): if it "
                                 "says 2 (4:3) the fit word is not read and the screen stays letterboxed, as on the A7S III with lcdfill_s3_v1",
                                 "that the frame widgets use row 1 on this body (a model word; carried over from the A7 IV)"]})


def design_v3(facts):
    sites, guards = fill_sites(), fill_guards(ratio_case=False)
    for a, old, new, what in ((0x1F61A4, ("moveq.w", "lr, #9"), "4ff0020e", "picture-ratio function 0x1f6170, 16:9 picture: `moveq.w lr, #9` to `#2` (the numerator of height = width x n / d)"),
                              (0x1F61A8, None, "08bf0320", "picture-ratio function, 16:9 picture: `it eq; moveq r0, #16` to `#3` (the denominator): the function's own 3:2 pair, "
                                                           "so a 4:3 panel's letterbox gets the 3:2 height [A7S III 0x1e4f9c, lcdratio32_s3_v1]")):
        assert fx(a, 4) == bytes.fromhex("4ff0090e" if old else "08bf1020")
        sites.append({"ram_address": hex(a), "old": fx(a, 4).hex(), "new": new, "note": what})
    for name, t, chk, _, _, _ in TABLES:
        e = entry(t, 2)
        old, new = rect(RECT_169[2]), rect(RECT_32_ON_43)
        for off, part in ((0, "x, y"), (4, "w, h")):
            sites.append({"ram_address": hex(e + off), "old": old[off:off + 4].hex(), "new": new[off:off + 4].hex(),
                          "note": "%s, check %#x: expected live-view rectangle for a 16:9 picture on the second output (the viewfinder; row 2, column 3), %s: "
                                  "stock %s to %s" % (name, chk, part, RECT_169[2], RECT_32_ON_43)})
        guards.append(G(e - 8, 8, "%s: the entry before the second output's 16:9 entry (1:1: 106, 26, 428, 428)" % name.split(" ")[0]))
    guards += [G(RATIO_FN, 16, "first 16 bytes of the picture-ratio function 0x1f6170"),
               G(0x1F6194, 16, "the 16 bytes before the constants: the flag test and the 100/235 case"),
               G(0x1F61AC, 16, "the 16 bytes after the constants (1:1 and 17:9 cases)"),
               G(0xE99EF0, 8, "the 8 zero bytes after the second table")]
    assert len(sites) == 11
    return finish("lcdfill_a6700_v3",
                  "Rear screen (3:2 panel) AND viewfinder (4:3 panel) show the open-gate live view at 3:2 with the focus frames: lcdfill_a6700_v2 plus the "
                  "16:9 letterbox ratio 9/16 -> 2/3 and the second output's frame rectangles (A6700 2.00)", sites, guards, facts,
                  {"ported_from": {"rear": "lcdfill_v2 (a7iv_602; works on an A7 IV)", "viewfinder": "lcdratio32_s3_v1 (a7s3_501; works on an A7S III, whose panels are 4:3): "
                                                                                                     "the same instruction form of the ratio function"},
                   "summary": {"sites": len(sites), "bytes": 4 * len(sites), "guards": len(guards), "includes": "the 5 words of lcdfill_a6700_v2",
                               "ratio_stock": "9/16", "ratio_new": "2/3", "viewfinder_frame_rectangle_stock": list(RECT_169[2]),
                               "viewfinder_frame_rectangle_new": list(RECT_32_ON_43), "goes_with": ["the A6700 open-gate state"]},
                   "status": "OPTIONAL, not the shipped screen step: nobody has reported it on an A6700, and nothing here was asked for by the contributed kit. "
                             "It takes lcdfill_a6700_v2's place. Applied over v2 the five shared words are found already changed and the other six are written; "
                             "its put back restores all eleven. v2's own put back refuses while v3 is applied (v2's guard at 0x1f61a4 is a v3 site)",
                   "while_applied": "every 16:9 picture on the rear screen and in the viewfinder is shown at 3:2; HDMI is unchanged (its panel code gives fit 0 or 2, "
                                    "where the ratio is not used)",
                   "not_shown": ["anything on a camera", "the viewfinder's panel type byte 0x1a7c210 (expected 2 = 4:3)",
                                 "that the viewfinder is the output the frame checks call the second one (row 2)"]})


def regions(v2, v3):
    fit = [hex(FIT_TABLE), hex(FIT_TABLE + 24)]
    tabs = [[hex(t), hex(t + TABLE_LEN)] for _, t, _, _, _, _ in TABLES]
    return {"about": "Where the A6700 2.00 screen designs may have a site, and where only a guard (cpapp-b.bin addresses; build/build_lcd_a6700.py, "
                     "modding/A6700_PORT_SCREEN.md). Read by helper_a6700/gen_a6700_write.py as gen_fx2_write.py reads lcd_regions_fx2.json.",
            "lcdfill_a6700_v2": {"sites": [fit] + tabs,
                                 "sites_note": "the fit words of a 16:9 picture (the site is 0x1f5f9c); the two frame tables (cpActAfWindow 0xe99e30, cpActTrackingFrame 0xe99e90)",
                                 "guards": [[hex(FIT_FN), hex(FIT_FN + FIT_LEN)], [hex(RATIO_FN), hex(RATIO_END)]],
                                 "guards_note": "a guard may also lie in the fit-mode function with its tables or in the picture-ratio function"},
            "lcdfill_a6700_v3": {"sites": [fit, ["0x1f61a4", "0x1f61ac"]] + tabs,
                                 "sites_note": "v2's regions and the two words holding the ratio function's 16:9 constants",
                                 "guards": [[hex(FIT_FN), hex(FIT_FN + FIT_LEN)], [hex(RATIO_FN), hex(RATIO_END)], ["0xe99ef0", "0xe99ef8"]],
                                 "guards_note": "as v2, and the zero bytes after the second table"},
            "dump_decoder": {
                "about": "A6700 2.00 coprocessor RAM the read-only dump should copy and decode for the screen step. Panel type: 3 = 3:2, 2 = 4:3, 1 = 16:9 "
                         "(type -> panel code 0x1f6a18, tables 0x1f6abc / 0xd04cdc: 3 -> 1, 2 -> 0, 1 -> 2).",
                "panel_type_rear": hex(PANEL_TYPE_REAR),
                "panel_type_rear_note": "byte [0x1a7c0c4 + 0x1c], read by 0x69ed42 (>= 4 counts as 1). Expected 3 (3:2): Sony gives the monitor as 1,036,800 dots = 720 x 480 x 3",
                "panel_type_second": hex(PANEL_TYPE_SECOND),
                "panel_type_second_note": "byte [0x1a7c1f4 + 0x1c], read by 0x69ed54 (>= 2 counts as 2): the viewfinder. Expected 2 (4:3): 2,359,296 dots = 1024 x 768 x 3",
                "panel_codes": {"1": "16:9", "2": "4:3", "3": "3:2"},
                "pages": ["0x1f5000", "0x1f6000", "0xe99000", "0x1a7c000"],
                "fit_words_169": [hex(FIT_TABLE), hex(FIT_SITE)],
                "fit_words_note": "fit mode of a 16:9 picture on panel code 0 (4:3) and 1 (3:2): 3, 3 stock; the screen step sets the second to 0 (3 letterbox, 0 fill)",
                "ratio_169": {"address": "0x1f61a4", "stock": "4ff0090e08bf1020", "patched_v3": "4ff0020e08bf0320", "note": "moveq.w lr, #9 / it eq; moveq r0, #16 -> #2 / #3 (v3 only)"},
                "frame_tables": {"cpActAfWindow": "0xe99e30", "cpActTrackingFrame": "0xe99e90"},
                "frame_table_layout": "3 rows (0 and 1 rear output: 1 on the 3:2 panel; 2 second output) x 4 aspect columns (3:2, 4:3, 1:1, 16:9) x (x, y, w, h) u16 "
                                      "on a 640 x 480 grid; the 16:9 column is entry 3: row r at table + 8 * (4 * r + 3)",
                "frame_rows_169_stock": {str(r): list(v) for r, v in RECT_169.items()},
                "frame_rows_169_v2": {"0": list(RECT_169[0]), "1": list(RECT_FILL), "2": list(RECT_169[2])},
                "frame_rows_169_v3": {"0": list(RECT_169[0]), "1": list(RECT_FILL), "2": list(RECT_32_ON_43)},
                "screen_words_v2": [{"address": s["ram_address"], "stock": s["old"], "new": s["new"]} for s in v2["sites"]],
                "screen_words_v3": [{"address": s["ram_address"], "stock": s["old"], "new": s["new"]} for s in v3["sites"]],
                "desqueeze_note": "no De-Squeeze Display on the A6700 2.00: nothing to read"}}


def check_regions(reg, d):
    """helper gen_*_write.words_header's rules, applied here so the header generator cannot fail on them."""
    r = reg[d["design"]]
    sr = [(int(a, 16), int(b, 16)) for a, b in r["sites"]]
    gr = sr + [(int(a, 16), int(b, 16)) for a, b in r["guards"]]
    within = lambda a, n, regs: any(lo <= a and a + n <= hi for lo, hi in regs)
    assert all(within(int(s["ram_address"], 16), 4, sr) for s in d["sites"]), d["design"]
    assert all(within(int(g["ram_address"], 16), len(g["bytes"]) // 2, gr) for g in d["guards"]), d["design"]


def designs():
    facts = check_context()
    return design_v2(facts), design_v3(facts)


if __name__ == "__main__":
    v2, v3 = designs()
    reg = regions(v2, v3)
    for d in (v2, v3):
        check_regions(reg, d)
        out = ROOT / "modding" / "designs" / (d["design"] + ".json")
        out.write_text(json.dumps(d, indent=1) + "\n", encoding="utf8", newline="\n")
        print("%s: %d sites, %d guards; sha %s" % (out.name, len(d["sites"]), len(d["guards"]), SHA[:16]))
        for s in d["sites"]:
            print("  %s %s -> %s  %s" % (s["ram_address"], s["old"], s["new"], s["note"][:100]))
    REGIONS.parent.mkdir(parents=True, exist_ok=True)
    REGIONS.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf8", newline="\n")
    print("wrote", REGIONS)
    print("contributed:", v2["contributed"])
