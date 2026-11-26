"""Build the A6700 2.00 playback designs (in-camera playback of the kit's 3840 x 2560 clips), three one-page designs for readcheck.c levels
29 / 30 (A6700 port, 2026-11-26; modding/A6700_PORT_ENCODER.md):

  C:/Python313/python.exe -B build/build_avdec_a6700.py

  avdec8k_a6700_v1    P29  the A7 IV's 8K decode channel: our FX30 design avdec8k_fx30_v1 (= the FX3's avdec8k_fx3_v1) at the A6700's addresses.
                           The A6700's decode functions are the FX30's, 0x3fc higher; the caller and the allocator 0x430 higher.
                             code page 0x217000   0x217578 mov w2,  #0x47d -> #0x47c     0x217584 mov w20, #0x47d -> #0x47c   (first allocation, its log copy)
                                                  0x2175f4 mov w2,  #0x47f -> #0x47e     0x217600 mov w21, #0x47f -> #0x47e   (second allocation, its log copy)
                             data page 0xc00000   0xc00350 decode size table row 0: 4096 x 2160 -> 7690 x 4320
  pbaspect_a6700_v1   A29  imola_dec_state get_aspect_ratio 0x23e4f0 (width, height): a picture 2,560 rows high is taken as one 2,160 rows high
                             code page 0x23e000   0x23e520 mov w8, #0x10e0 -> cmp w21, #0xa00     0x23e524 cmp w21, w8 -> b.eq 0x23e598
                           The 4,320-row case (7680 / 8192 wide) is given up for it: no format of this camera.
  pbformat_a6700_v1   F29  sfmc_dec_timing_ext_isp's playback-format set-up 0x115cfc: a 3840-wide picture of 2,160 rows OR MORE gets clip size 0x17
                             code page 0x115000   0x115dac b.ne 0x115db8 -> b.lo 0x115db8

The contributed A6700 kit (work/contrib/a6700_v1.0, design avdec8k_a6700_v2) carries the same seven instruction words and the data word in ONE
library that maps three code pages. readcheck.c's level 29 carries one code page per library (the whole page is its guard), so they are three
designs here; their bytes are compared with the contributed design's below (parsed only, nothing of it is run). A29 and F29 have no data
site: their data tables hold guards only (the functions' own log texts), which level 29 allows (kind 0 entries).

Every check of build_avdec_fx30.py is made again on the A6700's file, against the FX30's (whose design was built from the FX3's and the A7 IV's).
The two new functions are run in Unicorn, stock and changed, for 3840x2160, 3840x2560, 1920x1080, 4096x2160, 5760x3840 and 7680x4320.
Nothing is run on a camera.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm64_const as R

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avcam_fnport  # noqa: E402
import parse_dmmcfg as P  # noqa: E402
from build_avdec_fx30 import adrp_refs, asm, movz_w, strip, word  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUILD, FX30, REF = "a6700_200", "fx30_601", "a7iv_602"
KVA = 0xFFFFFFC001000000
AVCAM_PHYS = 0x401000000                  # update/0800_appli/setting/kemco.txt: memrsv=0x01000000@0x401000000:ex
D_DEC, D_CALL = 0x3FC, 0x430              # A6700 = FX30 + delta: the decode functions, and the caller / allocator
TABLE, ROW = 0xC00350, 20
ALLOC, CREATE, CALLER, ALLOCATOR = 0x217548, 0x217788, 0x228AD8, 0x22BCD4
LOGF, LOGH = 0x27B890, 0x27B850
ASPECT_FN, PBFMT_FN = 0x23E4F0, 0x115CFC
KIT = ROOT / "work/contrib/a6700_v1.0/A6700 OpenGate/a6700-opengate_v1.0/designs/avdec8k_a6700_v1.json"
DES = ROOT / "modding/designs"
SIZES = ((3840, 2160), (3840, 2560), (1920, 1080), (4096, 2160), (5760, 3840), (7680, 4320))
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)


def avcam(build):
    return (ROOT / f"work/extracted/{build}/0700_part_image/dev/nflasha3/av-cam.bin").read_bytes()


def run(img, start, regs, stops, stack=()):
    """Run av-cam code at file offset `start` until a stop offset or the return; the two log functions return at once. Returns (where, registers)."""
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(KVA, (len(img) + 0xFFFF) & ~0xFFFF)
    uc.mem_write(KVA, img)
    WORK, RET = 0x10000000, 0x10200000
    uc.mem_map(WORK, 0x100000)
    uc.mem_map(RET, 0x1000)
    uc.mem_write(WORK, struct.pack("<Q", WORK + 0x100))          # an object whose first word points at readable memory (the error path's log reads it)
    sp = WORK + 0x80000
    for k, v in enumerate(stack):
        uc.mem_write(sp + 8 * k, struct.pack("<Q", v))
    uc.reg_write(R.UC_ARM64_REG_SP, sp)
    uc.reg_write(R.UC_ARM64_REG_LR, RET)
    for k, v in regs.items():
        uc.reg_write(getattr(R, "UC_ARM64_REG_X%d" % k), v)
    state = {"at": None, "logged": 0}

    def hook(u, addr, size, _):
        off = addr - KVA
        if off in (LOGF, LOGH):
            state["logged"] += off == LOGF
            u.reg_write(R.UC_ARM64_REG_PC, u.reg_read(R.UC_ARM64_REG_LR))
        elif off in stops or addr == RET:
            state["at"] = off if addr != RET else "return"
            u.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook)
    try:
        uc.emu_start(KVA + start, RET, count=20000)
    except UcError as e:
        state["at"] = "fault: %s" % e
    if state["at"] is None and uc.reg_read(R.UC_ARM64_REG_PC) == RET:       # the run ends at the return address before the hook sees it
        state["at"] = "return"
    return state, {k: uc.reg_read(getattr(R, "UC_ARM64_REG_X%d" % k)) & 0xFFFFFFFF for k in (0, 8)}


def patched(img, sites):
    b = bytearray(img)
    for s in sites:
        o = int(s["file_off"], 16)
        b[o:o + 4] = bytes.fromhex(s["new"])
    return bytes(b)


def site(av, off, new, what):
    old = av[off:off + 4]
    i_old, i_new = next(md.disasm(old, KVA + off)), next(md.disasm(new, KVA + off))
    assert off % 4 == 0 and old != new
    fix = lambda i: ("%s %s" % (i.mnemonic, i.op_str)).replace("#0x%x" % (KVA + (i.address - KVA & ~0)), "")
    txt = lambda i: ("%s %s" % (i.mnemonic, i.op_str)).replace("0xffffffc001", "@").replace("#@", "@")
    return {"file_off": hex(off), "kernel_address": hex(KVA + off), "old": old.hex(), "new": new.hex(), "asm_old": txt(i_old), "asm_new": txt(i_new), "what": what}


def guards_of(av, start, n, what):
    """Data guards over n bytes of a text of the file from `start`, 16 bytes each, all in one page."""
    out = []
    for o in range(start, start + n, 16):
        m = min(16, start + n - o)
        out.append({"file_off": hex(o), "bytes": av[o:o + m].hex(), "what": "%s, bytes %d to %d: %r" % (what, o - start, o - start + m - 1, av[o:o + m].decode("ascii", "replace"))})
    assert start & ~0xFFF == (start + n - 1) & ~0xFFF
    return out


def write(name, body, av, sha):
    code_page = int(body["code_page"], 16)
    assert all(int(s["file_off"], 16) & ~0xFFF == code_page for s in body["code_sites"])
    out = {"design": name, "build": BUILD, "camera": "ILCE-6700 (A6700), firmware 2.00", "kind": "avcam_code_data", **body,
           "artifact": "av-cam.bin", "artifact_sha256": sha, "kernel_va_base": hex(KVA), "avcam_phys": hex(AVCAM_PHYS), "generated_by": "build/build_avdec_a6700.py",
           "code_guard": "the whole code page %s apart from the sites must be as in the file, in the mapping and in the kernel's own view" % body["code_page"],
           "icache": {"processors": "see /proc/cpuinfo in the step's result; kernel as the FX30's",
                      "alias": "the code page is mapped at a user address with the kernel's offset from a 2 MB boundary (%#x), so a virtually indexed instruction "
                               "cache is invalidated at the same index as the kernel's fetches" % ((KVA + code_page) & 0x1FFFFF),
                      "refuse": "an instruction cache that CTR_EL0 says is neither PIPT nor VIPT"},
           "restore": "readcheck.c level 30 (put back), or a cold boot: av-cam.bin is loaded again from flash"}
    (DES / f"{name}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf8", newline="\n")
    print("wrote", name, "| code", [s["file_off"] for s in out["code_sites"]], "| data sites", [s["file_off"] for s in out["data_sites"]],
          "| data guards", len(out["data_guards"]), "in page", out["data_page"])
    return out


def main():
    av, fx, a4 = avcam(BUILD), avcam(FX30), avcam(REF)
    sha = hashlib.sha256(av).hexdigest()
    og = json.loads((DES / "ogfile2560_hs_s_a6700_v2.json").read_text(encoding="utf8"))
    assert sha == og["artifact_sha256"]["av-cam.bin"], "not the av-cam.bin of the A6700 kit's other designs"
    fx30_design = json.loads((DES / "avdec8k_fx30_v1.json").read_text(encoding="utf8"))
    kit = json.loads(KIT.read_text(encoding="utf8"))
    assert kit["artifact_sha256"] == sha
    norm = lambda d, a, n: avcam_fnport.normalise(struct.unpack_from("<%dI" % n, d, a))

    # ---------------------------------------------------------------- P29: the decode channel (build_avdec_fx30.py's checks, against the FX30)
    # 1. the allocation: the FX30's sequences, here with the A6700's targets
    want = {0x217168: ["mov w8, #0x1070", "ldr x0, [x19, #0x10a0]", "add x4, x19, x8", "mov w1, #0x610000", "movk w1, #0x3c",
                       "mov w2, #0x47d", "mov w3, #-0x7f980000", "movk w3, #0xf3", "mov w20, #0x47d", "bl", "tbz w0, #0"],
            0x2171E4: ["mov w8, #0x1090", "ldr x0, [x19, #0x10a0]", "add x4, x19, x8", "mov w1, #0x610000", "movk w1, #0x3c",
                       "mov w2, #0x47f", "mov w3, #-0x7f980000", "movk w3, #0xf3", "mov w21, #0x47f", "bl", "tbnz w0, #0"]}
    for at30, seq in want.items():
        ref = asm(fx, at30, len(seq))
        assert strip(ref) == seq, "the FX30 reference moved"
        got = asm(av, at30 + D_DEC, len(seq))
        assert strip(got) == seq, "the A6700's decode allocation at %#x is not the FX30's" % (at30 + D_DEC)
        assert got[9] == "bl @%x" % ALLOCATOR and got[10].endswith("@%x" % (int(ref[10].rsplit("@", 1)[1], 16) + D_DEC)), got
    assert asm(av, ALLOC, 4) == ["sub sp, sp, #0x30", "stp x21, x20, [sp, #0x10]", "stp x19, x30, [sp, #0x20]", "mov x19, x0"]
    assert asm(av, 0x2171C0 + D_DEC, 1) == ["str w20, [sp, #8]"] and asm(av, 0x217234 + D_DEC, 1) == ["str w21, [sp, #8]"]   # the log copies' only use
    assert strip(asm(av, ALLOCATOR, 24)) == strip(asm(a4, 0x222BD0, 24)), "the allocators differ"
    assert norm(av, ALLOC, 48) == norm(fx, ALLOC - D_DEC, 48) and norm(av, CREATE, 120) == norm(fx, CREATE - D_DEC, 120)
    # 2. the clip type: the caller makes 11, 12, 13 or 10, never 14 (the FX30's / FX3's caller)
    fx_caller, a_caller = asm(fx, CALLER - D_CALL, 14), asm(av, CALLER, 14)
    assert strip(a_caller) == strip(fx_caller) and asm(av, 0x22870C + D_CALL, 1) == asm(fx, 0x22870C, 1) == ["stp w22, w23, [sp, #0xf4]"]
    assert [s for s in a_caller if s.startswith("mov w22") or s.startswith("mov w8")] == ["mov w22, #0xb", "mov w8, #0xc", "mov w22, #0xa"]
    assert "cmp w8, #0x27" not in " ".join(a_caller)
    # 3. the row: row 0 whenever the A7 IV takes row 0 or 3; the table read only by create-ch
    assert strip(asm(av, 0x2174B4 + D_DEC, 11)) == strip(asm(fx, 0x2174B4, 11)) == strip(["tbz w0, #0, @0", "ldrh w8, [x20, #0x48]", "ldrh w9, [x20, #0x4a]", "mul w8, w9, w8",
                                                                                       "cmp w8, #0x1fe, lsl #12", "mov w8, #1", "mov w22, #1", "cinc x23, x8, ls", "b @0",
                                                                                       "mov w22, wzr", "mov x23, xzr"])
    assert asm(av, 0x217518 + D_DEC, 2) == ["adrp x9, page@%x" % (TABLE & ~0xFFF), "add x9, x9, #0x%x" % (TABLE & 0xFFF)]
    assert asm(av, 0x21752C + D_DEC, 1) == ["mov w8, #0x14"] and asm(av, 0x217540 + D_DEC, 1) == ["madd x8, x23, x8, x9"]
    rows = [av[TABLE + ROW * k:TABLE + ROW * (k + 1)] for k in range(3)]
    fx_rows = [fx[0xBF6570 + ROW * k:0xBF6570 + ROW * (k + 1)] for k in range(3)]
    a4_rows = [a4[0xBACEB0 + ROW * k:0xBACEB0 + ROW * (k + 1)] for k in range(4)]
    assert rows == fx_rows == a4_rows[:3], "the A6700's three rows are not the FX30's / the A7 IV's rows 0 to 2"
    assert struct.unpack_from("<HH", rows[0]) == (4096, 2160) and a4_rows[3][4:] == rows[0][4:] and struct.unpack_from("<HH", a4_rows[3]) == (7690, 4320)
    refs = adrp_refs(av, KVA + (TABLE & ~0xFFF), TABLE, TABLE + 3 * ROW, 0xA00000)
    assert refs == [(0x21751C + D_DEC, TABLE)], "the table is read elsewhere too: %s" % refs
    # 4. memory: the ids exist in the A6700's main-processor DmmCfg with the A7 IV's sizes
    mem = {}
    for b in (BUILD, REF):
        cfg = P.Config(P.find_file(b, "setting"), b)
        assert cfg.exact()
        row = {}
        for i in (0x47C, 0x47D, 0x47E, 0x47F):
            (k,) = cfg.id_rows[i]["keys"]
            row[i] = [(u["group"]["parent"], u["size"]) for u in cfg.units_by_key[k]]
        mem[b] = row
    assert mem[BUILD] == mem[REF], "the decode memory differs from the A7 IV's"
    assert mem[BUILD][0x47C] == [(0x6C4, 536182784)] and mem[BUILD][0x47E] == [(0x6DD, 135036928)]
    # 5. no other code asks for these ids: the other `mov wN, #0x47c..0x47f` are the FX30's, in the same order with the same registers
    #    (there each was shown to be a line number of a log or assert call, or the A7 IV's twin)
    #    Each is shown to be a line number of a log call (w7, with the call to the log function 0x27b890 within the next six instructions), or one of
    #    the three `mov w3` the FX30 has too (w3 of a log call; the same four instructions as the FX30's, which were compared with the A7 IV's there).
    others = []
    fx_w3 = [int(o, 16) for o, a, _ in fx30_design["checked"]["other_id_immediates"] if a.startswith("mov w3,")]
    for off in range(0, 0xA00000, 4):
        x = word(av, off)
        if x & 0xFFE00000 == 0x52800000 and (x >> 5) & 0xFFFF in (0x47C, 0x47D, 0x47E, 0x47F) and not (ALLOC <= off < ALLOC + 0xC0):
            a = asm(av, off, 1)[0]
            if x & 31 == 7:
                nxt = asm(av, off + 4, 12)
                call = next((k for k, s in enumerate(nxt) if s.startswith("bl @")), None)
                assert call is not None and not any("w7" in s or "x7" in s for s in nxt[:call]), "a w7 id-like immediate at %#x that is not a call's eighth argument" % off
                role = "eighth argument (the line number) of the call that follows (%s); the allocation passes its ids in w2" % nxt[call]
            elif x & 31 == 3 and fx_w3:
                twin = fx_w3.pop(0)
                assert strip(asm(av, off, 4)) == strip(asm(fx, twin, 4)), "the FX30's twin of %#x differs" % off
                role = "w3 of a log call; the same at the FX30's %#x" % twin
            else:
                raise AssertionError("an id-like immediate at %#x that is not a line number: %s" % (off, a))
            others.append((off, a, role))
    assert not fx_w3 and len(others) == 12, others
    fx_others = [(o, a, r) for o, a, r in others]
    # the sites: the FX30 design's, moved; and the contributed design's page-0 words
    code_sites = []
    for s30 in fx30_design["code_sites"]:
        off = int(s30["file_off"], 16) + D_DEC
        assert av[off:off + 4] == bytes.fromhex(s30["old"])
        code_sites.append({"file_off": hex(off), "kernel_address": hex(KVA + off), "old": s30["old"], "new": s30["new"], "asm_old": s30["asm_old"], "asm_new": s30["asm_new"],
                           "what": s30["what"].split(" (str ")[0]})
    kit0 = [(s["file_off"], s["old"], s["new"]) for s in kit["code_sites"] if s["page_idx"] == 0]
    assert kit0 == [(s["file_off"], s["old"], s["new"]) for s in code_sites], "the contributed decode-channel words are not ours"
    data_sites = [{"file_off": hex(TABLE), "kernel_address": hex(KVA + TABLE), "old": struct.pack("<HH", 4096, 2160).hex(), "new": struct.pack("<HH", 7690, 4320).hex(),
                   "what": "decode size table row 0: width, height (the A7 IV's row 3)"}]
    data_guards = [{"file_off": hex(TABLE + 4), "bytes": av[TABLE + 4:TABLE + 16].hex(), "what": "row 0 after the size"},
                   {"file_off": hex(TABLE + 16), "bytes": av[TABLE + 16:TABLE + 32].hex(), "what": "row 0 end, row 1"},
                   {"file_off": hex(TABLE + 32), "bytes": av[TABLE + 32:TABLE + 48].hex(), "what": "row 1, row 2"},
                   {"file_off": hex(TABLE + 48), "bytes": av[TABLE + 48:TABLE + 60].hex(), "what": "row 2"}]
    assert [(d["file_off"], d["old"], d["new"]) for d in kit["data_sites"]] == [(d["file_off"], d["old"], d["new"]) for d in data_sites]
    assert [(g["file_off"], g["bytes"]) for g in kit["data_guards"]] == [(g["file_off"], g["bytes"]) for g in data_guards]
    assert [g["bytes"] for g in data_guards] == [g["bytes"] for g in fx30_design["data_guards"]]
    p29 = write("avdec8k_a6700_v1", {
        "title": "In-camera playback of 3840 x 2560 clips, part 1 of 3 (P29): the A7 IV's 8K decode channel (7690 x 4320, memory ids 0x47c / 0x47e)",
        "status": "the FX30 design avdec8k_fx30_v1 at the A6700's addresses (decode functions 0x3fc higher); the same words are page 0 and the data word of the "
                  "contributed avdec8k_a6700_v2, whose author reports playback on an A6700 (no logs seen). Not run by us on any camera",
        "ported_from": "avdec8k_fx30_v1 (FX30 6.01) = avdec8k_fx3_v1 (FX3 7.02): the same bytes",
        "code_page": "0x217000", "code_sites": code_sites, "data_page": hex(TABLE & ~0xFFF), "data_sites": data_sites, "data_guards": data_guards,
        "order": fx30_design["order"],
        "checked": {"type_never_14": "the A6700 caller %#x makes types 11 / 12 / 13 / 10 (the FX30's 0x2286a8)" % CALLER,
                    "rows_equal": "A6700 rows 0-2 = FX30 rows 0-2 = A7 IV rows 0-2; A7 IV row 3 = row 0 with 7690 x 4320",
                    "table_readers": ["%#x (create-ch)" % refs[0][0]],
                    "allocator": "A6700 0x22bcd4 = A7 IV 0x222bd0 (24 instructions, branch targets aside)",
                    "dmm": {hex(k): [[hex(p), s] for p, s in v] for k, v in mem[BUILD].items()},
                    "other_id_immediates": [[hex(o), a, r] for o, a, r in fx_others],
                    "same_bytes_as_fx30_design": True, "same_bytes_as_the_contributed_design": True}}, av, sha)

    # ---------------------------------------------------------------- A29: get_aspect_ratio
    seq = asm(av, 0x23E504, 19)
    assert seq == ["and w21, w2, #0xffff", "cmp w21, #0x437", "b.le @23e550", "cmp w21, #0x438", "b.eq @23e570", "cmp w21, #0x870", "b.eq @23e598",
                   "mov w8, #0x10e0", "cmp w21, w8", "b.ne @23e5e8", "and w8, w19, #0xffff", "mov w9, #0x1e00", "mov w10, #6", "cmp w8, w9", "mov w9, #2",
                   "csel w0, w9, w10, eq", "cmp w8, #2, lsl #12", "b.eq @23e590", "b @23e5dc"], seq
    assert asm(av, 0x23E598, 7) == ["and w8, w19, #0xffff", "cmp w8, #1, lsl #12", "mov w9, #5", "cinc w0, w9, ne", "cmp w8, #0xf00", "b.ne @23e5dc", "mov w0, #2"]
    assert asm(av, ASPECT_FN, 5) == ["sub sp, sp, #0x40", "stp x21, x20, [sp, #0x20]", "stp x19, x30, [sp, #0x30]", "mov w19, w1", "mov x20, x0"]
    new_a = [struct.pack("<I", 0x7100001F | (0xA00 << 10) | (21 << 5)),                     # cmp w21, #0xa00
             struct.pack("<I", 0x54000000 | (((0x23E598 - 0x23E524) // 4) << 5))]           # b.eq 0x23e598
    a_sites = [site(av, 0x23E520, new_a[0], "the 4,320-row case's constant becomes the test for 2,560 rows"),
               site(av, 0x23E524, new_a[1], "2,560 rows: to the 2,160-row case (width 3840 -> aspect code 2, width 4096 -> 5); any other height falls to the "
                                            "`b.ne` after it, which the test above now sends to the unsupported exit")]
    assert (a_sites[0]["asm_new"], a_sites[1]["asm_new"]) == ("cmp w21, #0xa00", "b.eq @23e598"), a_sites
    # nothing branches into the two words or the one after them
    for off in range(0, 0xA00000, 4):
        i = next(md.disasm(av[off:off + 4], off), None)
        if i is not None and (i.mnemonic in ("b", "bl", "cbz", "cbnz", "tbz", "tbnz") or i.mnemonic.startswith("b.")):
            t = int(i.op_str.rsplit("#", 1)[1], 16)
            assert t not in (0x23E520, 0x23E524), "a branch into the changed words at %#x" % off
    kit1 = [(s["file_off"], s["old"], s["new"]) for s in kit["code_sites"] if s["page_idx"] == 1]
    assert kit1 == [(s["file_off"], s["old"], s["new"]) for s in a_sites], "the contributed get_aspect_ratio words are not these"
    callers = [off for off in range(0, 0xA00000, 4) if word(av, off) & 0xFC000000 == 0x94000000
               and off + 4 * ((word(av, off) & 0x3FFFFFF) - ((word(av, off) & 0x2000000) << 1)) == ASPECT_FN]
    changed_a = patched(av, a_sites)
    aspect = {}
    for w, h in SIZES:
        got = {}
        for k, img in (("stock", av), ("changed", changed_a)):
            st, regs = run(img, ASPECT_FN, {0: 0x10000000, 1: w, 2: h}, ())
            assert st["at"] == "return", st
            got[k] = {"aspect_code": regs[0] & 0xFF, "error_logged": bool(st["logged"])}
        aspect["%dx%d" % (w, h)] = got
    assert aspect["3840x2160"]["stock"] == aspect["3840x2160"]["changed"] == {"aspect_code": 2, "error_logged": False}
    assert aspect["3840x2560"]["stock"] == {"aspect_code": 6, "error_logged": True} and aspect["3840x2560"]["changed"] == {"aspect_code": 2, "error_logged": False}
    assert aspect["1920x1080"]["stock"] == aspect["1920x1080"]["changed"] and aspect["4096x2160"]["stock"] == aspect["4096x2160"]["changed"]
    assert aspect["5760x3840"]["changed"] == aspect["5760x3840"]["stock"] == {"aspect_code": 6, "error_logged": True}
    a_text = 0x4418C5
    assert av[a_text:a_text + 48] == b"[IMLDECSTAT]get_aspect_ratio() unsupported width" and (0x23E61C, a_text) in adrp_refs(av, KVA + 0x441000, a_text, a_text + 1, 0xA00000) or \
        asm(av, 0x23E61C, 2) == ["adrp x8, page@441000", "add x8, x8, #0x8c5"]
    a29 = write("pbaspect_a6700_v1", {
        "title": "In-camera playback of 3840 x 2560 clips, part 2 of 3 (A29): get_aspect_ratio takes a picture 2,560 rows high as one 2,160 rows high",
        "status": "the two words of page 1 of the contributed avdec8k_a6700_v2 (its author reports playback on an A6700; no logs seen), split off because "
                  "readcheck.c level 29 carries one code page. Disassembled and emulated here; not run by us on any camera",
        "code_page": "0x23e000", "code_sites": a_sites, "data_page": "0x441000", "data_sites": [],
        "data_guards": guards_of(av, a_text, 48, "the function's own error text (read at 0x23e61c)"),
        "order": {"apply": ["the two code words, each one aligned 32-bit store, in address order", "data cache clean and instruction cache invalidate at each, all processors; isb"],
                  "put_back": ["the two code words", "data cache clean and instruction cache invalidate at each; isb"],
                  "between_the_two_stores": "level 29 and level 30 both store 0x23e520 first. Apply, one word in: `cmp w21, #0xa00` then the stock `cmp w21, w8` "
                                            "(w8 no longer set to 4320 here) then `b.ne`. Put back, one word in: the stock `mov w8, #0x10e0` then `b.eq 0x23e598` on "
                                            "the flags of the 2,160-row test before it (never taken) then `b.ne`. In both a height above 2,160 rows may go to the "
                                            "unsupported exit for that moment; every instruction executed is one of the function's own or one of the two new ones"},
        "function": {"get_aspect_ratio": hex(ASPECT_FN), "arguments": "x0 the decoder state, w1 width, w2 height; returns an aspect code, 6 = unsupported (logged)",
                     "callers": [hex(c) for c in callers]},
        "emulated": aspect,
        "given_up": "the 4,320-row case (7680 wide -> 2, 8192 wide -> 5): with the step applied a 4,320-row picture is unsupported. The A6700 records nothing that high",
        "checked": {"same_bytes_as_the_contributed_design": True, "no_branch_into_the_changed_words": True}}, av, sha)

    # ---------------------------------------------------------------- F29: the playback format's clip size
    seq = asm(av, 0x115D9C, 7)
    assert seq == ["cmp w8, #0xf00", "b.ne @115db8", "and w8, w24, #0xffff", "cmp w8, #0x870", "b.ne @115db8", "mov w8, #0x17", "b @115e44"], seq
    assert asm(av, 0x115E44, 1) == ["strb w8, [x25, #8]"] and asm(av, PBFMT_FN, 1) == ["sub sp, sp, #0x70"]
    assert asm(av, 0x115D1C, 1) == ["mov w24, w5"] and asm(av, 0x115D34, 1) == ["and w27, w4, #0xffff"] and asm(av, 0x115D14, 1) == ["ldr x25, [sp, #0x78]"]
    new_f = struct.pack("<I", 0x54000003 | (((0x115DB8 - 0x115DAC) // 4) << 5))             # b.lo (b.cc) 0x115db8
    f_sites = [site(av, 0x115DAC, new_f, "a 3840-wide picture: `not 2,160 rows` becomes `fewer than 2,160 rows`, so 2,160 rows or more gets clip size 0x17")]
    assert f_sites[0]["asm_new"] in ("b.lo @115db8", "b.cc @115db8"), f_sites
    kit2 = [(s["file_off"], s["old"], s["new"]) for s in kit["code_sites"] if s["page_idx"] == 2]
    assert kit2 == [(s["file_off"], s["old"], s["new"]) for s in f_sites], "the contributed playback-format word is not this"
    assert sorted(kit0 + kit1 + kit2) == sorted((s["file_off"], s["old"], s["new"]) for s in kit["code_sites"]) and len(kit["code_sites"]) == 7
    changed_f = patched(av, f_sites)
    OUT = 0x10000000 + 0x1000
    fmt = {}
    for w, h in SIZES:
        got = {}
        for k, img in (("stock", av), ("changed", changed_f)):
            # arguments as the prologue takes them: w4 width, w5 height, the output record at [sp+8] (the function reads [sp, #0x78] after sub sp, #0x70)
            st, regs = run(img, PBFMT_FN, {0: 0x10000000, 1: 0, 2: 0, 3: 1, 4: w, 5: h, 6: 0, 7: 1}, (0x115E44, 0x1160E0, 0x116140), stack=(0, OUT))
            got[k] = "clip size %#x" % regs[8] if st["at"] == 0x115E44 else "not a 4K or HD size here (goes on to the smaller sizes / `Unexpected picture size`)"
        fmt["%dx%d" % (w, h)] = got
    assert fmt["3840x2160"]["stock"] == fmt["3840x2160"]["changed"] == "clip size 0x17" and fmt["3840x2560"]["changed"] == "clip size 0x17"
    assert fmt["3840x2560"]["stock"].startswith("not a 4K") and fmt["1920x1080"]["stock"] == fmt["1920x1080"]["changed"] and fmt["4096x2160"]["stock"] == fmt["4096x2160"]["changed"]
    assert fmt["5760x3840"]["stock"] == fmt["5760x3840"]["changed"] and fmt["7680x4320"]["stock"] == fmt["7680x4320"]["changed"]
    f_text, f_file = 0x413D3A, 0x41351B
    assert av[f_text:f_text + 32] == b"Unexpected picture size %d x %d\0" and av[f_file:f_file + 32] == b"dec/sfmc_dec_timing_ext_isp.cpp\0"
    assert asm(av, 0x116234, 2) == ["adrp x8, page@413000", "add x8, x8, #0xd3a"] or (0x116238, f_text) in adrp_refs(av, KVA + 0x413000, f_text, f_text + 1, 0xA00000)
    f29 = write("pbformat_a6700_v1", {
        "title": "In-camera playback of 3840 x 2560 clips, part 3 of 3 (F29): the playback format set-up gives a 3840-wide picture of 2,160 rows or more clip size 0x17",
        "status": "the one word of page 2 of the contributed avdec8k_a6700_v2 (its author reports playback on an A6700; no logs seen), split off because "
                  "readcheck.c level 29 carries one code page. Disassembled and emulated here; not run by us on any camera",
        "code_page": "0x115000", "code_sites": f_sites, "data_page": "0x413000", "data_sites": [],
        "data_guards": guards_of(av, f_file, 32, "the function's source-file text (read at 0x115ea4 and on)") + guards_of(av, f_text, 32, "its error text (read at 0x116234)"),
        "order": {"apply": ["the code word, one aligned 32-bit store", "data cache clean and instruction cache invalidate, all processors; isb"],
                  "put_back": ["the code word", "data cache clean and instruction cache invalidate; isb"]},
        "function": {"playback_format_set_up": hex(PBFMT_FN), "arguments": "w4 width, w5 height, the output record at [sp, #8]; the clip size is stored at record +8 (0x115e44)"},
        "emulated": fmt,
        "checked": {"same_bytes_as_the_contributed_design": True}}, av, sha)
    ev = ROOT / "evidence/a6700/encoder/playback_emu_a6700.json"
    ev.parent.mkdir(parents=True, exist_ok=True)
    ev.write_text(json.dumps({"about": "A6700 2.00 playback designs: get_aspect_ratio 0x23e4f0 and the playback-format set-up 0x115cfc run in Unicorn, stock and "
                                       "changed. Generated by build/build_avdec_a6700.py.",
                              "get_aspect_ratio": aspect, "playback_format_clip_size": fmt,
                              "alias_offsets_from_a_2MB_boundary": {d["design"]: hex((KVA + int(d["code_page"], 16)) & 0x1FFFFF) for d in (p29, a29, f29)}}, indent=1) + "\n",
                  encoding="utf8", newline="\n")
    print("get_aspect_ratio:", {k: (v["stock"]["aspect_code"], v["changed"]["aspect_code"]) for k, v in aspect.items()})
    print("playback format:", {k: (v["stock"][:14], v["changed"][:14]) for k, v in fmt.items()})
    print("wrote", ev)


if __name__ == "__main__":
    sys.exit(main())
