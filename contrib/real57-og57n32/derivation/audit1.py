"""audit1: auditoria previa (sin camara) del candidato 6K A6700. Escribe audit1_report.json."""
import hashlib, json, struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_PROT_ALL
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP,
                               UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC)

HERE = Path(__file__).parent
NF = Path(r"a6700fw\out\firmware.tar_unpacked\0700_part_image\dev")
FW = (NF / r"nflasha8_unpacked\cpapp-b.bin").read_bytes()
DMM = (NF / r"nflasha8_unpacked\DmmCfg.bin").read_bytes()
AV = (NF / r"nflasha3_unpacked\av-cam.bin").read_bytes()
LM = (NF / r"nflasha15_unpacked\lib\libmpr.so").read_bytes()
DUMP = Path(r"a6700fw\a6700-open-gate-test\windows\camera_private\CT6_20261126T175312Z_a6700_dump")
DES = Path(r"a6700fw\a6700-open-gate-test\windows\tools\modding\designs")
BASE = 0x108000
rep = {}

# (a)/(c) invariantes del diseno
d = json.loads((HERE / "og57n32_a6700_v1.json").read_text(encoding="utf-8"))
lrc = d["summary"]["lrc"]
for h in "LR":
    assert lrc[h]["input"] == [3016, 3976] and lrc[h]["output"] == [2912, 3844]
    assert lrc[h]["step_q12"] == [4233, 4233]
assert d["summary"]["front_end"] == [5760, 3840]
extra = {e["offset"]: e["new"] for e in d["stored_record_extra"]}
assert extra == {"0x6": "1b", "0x7": "20"}
assert d["artifact_sha256"] == hashlib.sha256(FW).hexdigest()
rep["design_invariants"] = "OK (Lrc L/R 3016x3976->2912x3844, step 4233, +6/+7=27/32, sha cpapp)"

# (b) rc_fit 0xb1d4ee
rs = (DUMP / "cp_resizestate_019b7000.bin").read_bytes()
rw = (DUMP / "cp_resizework_016a7000.bin").read_bytes()
st = (DUMP / "cp_sizetable_0199e000.bin").read_bytes()

def rc_fit(pa, s1, tgt, prm, mode):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.reg_write(UC_ARM_REG_C1_C0_2, uc.reg_read(UC_ARM_REG_C1_C0_2) | (0xF << 20))
    uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    end = (BASE + len(FW) + 0xfff) & ~0xfff
    uc.mem_map(BASE, end - BASE, UC_PROT_ALL); uc.mem_write(BASE, FW)
    uc.mem_map(0x1600000, 0x500000, UC_PROT_ALL)
    uc.mem_write(0x19b7000, rs); uc.mem_write(0x16a7000, rw); uc.mem_write(0x199e000, st)
    uc.mem_write(0x1957324, struct.pack("<IIII", 0, 0, 3, 0))
    S = 0x3000000; uc.mem_map(S, 0x20000, UC_PROT_ALL)
    inp = bytearray(0x50)
    for o, v in ((0, 1), (4, pa[0]), (8, pa[1]), (0xc, pa[2]), (0x10, pa[3]), (0x14, s1[0]), (0x18, s1[1]),
                 (0x1c, s1[0]), (0x20, s1[1]), (0x34, tgt[0]), (0x38, tgt[1]), (0x3c, s1[0]), (0x40, s1[1]),
                 (0x44, s1[0]), (0x48, s1[1])):
        struct.pack_into("<I", inp, o, v)
    inp[0x4c] = 1
    uc.mem_write(S + 0x11000, bytes(inp))
    p = bytearray(rw[0x320:0x3c0])
    struct.pack_into("<I", p, 0x2c, mode); struct.pack_into("<HH", p, 0x30, prm[0], prm[1])
    struct.pack_into("<I", p, 0x34, 0x1000)
    uc.mem_write(S + 0x11100, bytes(p))
    uc.mem_write(S + 0x11300, struct.pack("<HH", *tgt))

    def hk(uc, a, sz, ud):
        lr = uc.reg_read(UC_ARM_REG_LR)
        if a in (0xb287b4, 0xb21dbc, 0xb26a0e, 0xb26a4c, 0xb21990):
            uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_PC, lr)
        else:
            r0, r1, r2 = (uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            uc.mem_write(r0, bytes(uc.mem_read(r1, r2)) if a == 0x612240 else b"\0" * r1)
            uc.reg_write(UC_ARM_REG_PC, lr)
    for a in (0xb287b4, 0xb21dbc, 0xb26a0e, 0xb26a4c, 0xb21990, 0x612240, 0x612934):
        uc.hook_add(UC_HOOK_CODE, hk, begin=a, end=a + 2)
    uc.reg_write(UC_ARM_REG_SP, S + 0x10000)
    for r, v in ((UC_ARM_REG_R0, S + 0x11000), (UC_ARM_REG_R1, S + 0x11100), (UC_ARM_REG_R2, S + 0x11200),
                 (UC_ARM_REG_R3, S + 0x11300)):
        uc.reg_write(r, v)
    uc.mem_write(S + 0x100, b"\0\xbf\0\xbf"); uc.reg_write(UC_ARM_REG_LR, (S + 0x100) | 1)
    uc.emu_start(0xb1d4ee | 1, S + 0x100, count=300000)
    u = struct.unpack_from("<10H", bytes(uc.mem_read(S + 0x11200, 0x14)), 0)
    return {"xy": [u[2], u[3]], "wh": [u[4], u[5]]}

stock = rc_fit((1, 1, 1, 1), (3840, 2160), (3840, 2160), (16, 9), 1)
assert stock["wh"] == [3840, 2160] and stock["xy"] == [0, 0]
ok = rc_fit((1, 32, 1, 27), (5760, 3840), (5760, 3840), (16, 9), 1)
assert ok["wh"] == [5760, 3840] and ok["xy"] == [0, 0], ok
bad = rc_fit((1, 1, 1, 1), (5760, 3840), (5760, 3840), (16, 9), 1)
assert bad["wh"][1] == 3240, bad
rep["rc_fit"] = {"stock_4k": stock, "og57n32_pa27_32_PRM16_9": ok, "if_pa_1_1_would_crop": bad,
                 "note": "27/32 necesario. Si [Resize+0xa36]!=0 (PRM=5760x3348) recorta a 5574 de ancho (no probado como activo)"}

# (d) DMM
def recs(key):
    out, pos = [], 0
    pat = struct.pack("<I", key)
    while (i := DMM.find(pat, pos)) != -1:
        if i % 4 == 0 and i >= 4:
            k, kk, sz, f = struct.unpack_from("<4I", DMM, i - 4)
            if f == 0x10f:
                out.append(sz)
        pos = i + 4
    return out
k57f, k5f2 = recs(0x57f), recs(0x5f2)
assert set(k57f) == {0x1341200} and 0x16d5a00 >= 5976 * 3976 * 1.0
parents = {}
for off in range(0, len(DMM) - 16, 4):
    w = struct.unpack_from("<4I", DMM, off)
    if w[0] == 0x14 and w[3] == 0x10f and w[1] in (0x6fa, 0x74d):
        parents[w[1]] = w[2]
raw_bytes = 3 * 0x16d5a00
assert raw_bytes <= parents[0x6fa], "L13 3 unidades no caben en 0x6fa"
need_s1 = 5760 * 3840 * 3 // 2
rep["dmm"] = {"DmmCfg_sha256": hashlib.sha256(DMM).hexdigest(), "key_0x57f_stock": k57f[0],
              "L13_size": 0x16d5a00, "L13_raw_min": 5976 * 3976, "parent_0x6fa": parents[0x6fa],
              "parent_0x74d": parents[0x74d], "L13_3units_total": raw_bytes,
              "key_0x5f2_K16_0x43f": k5f2[0], "yuv420_8b_5760x3840": need_s1,
              "UNRESOLVED": ["tamano/bpp real del buffer 0x43f (30,824,400 B < 33,177,600 NV12 8b: formato/compresion no confirmado)",
                             "pool intermedio stage1->stage2 con 5760x3840 (K16 se diseno para intermedio 4336x2438)"]}

# (e) K19
k = json.loads((DES / "ogfile57r260_a6700_v1.json").read_text(encoding="utf-8"))
assert k["artifact_sha256"]["libmpr.so"] == hashlib.sha256(LM).hexdigest()
assert k["artifact_sha256"]["av-cam.bin"] == hashlib.sha256(AV).hexdigest()
cnt = {"libmpr.so": 0, "av-cam.bin": 0}
for p in k["patches"]:
    b = {"libmpr.so": LM, "av-cam.bin": AV}[p["binary"]]
    o, old = int(p["file_off"], 16), bytes.fromhex(p["old"])
    assert b[o:o + len(old)] == old
    cnt[p["binary"]] += 1
assert cnt == {"libmpr.so": 14, "av-cam.bin": 487}
rep["k19"] = {"patches_ok": cnt, "raster": k["raster"], "pixel_rate_MPs": 5760 * 3840 * 25 / 1e6,
              "stock_4k120_MPs": 3840 * 2160 * 120 / 1e6}

(HERE / "audit1_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
print(json.dumps(rep, indent=1))
