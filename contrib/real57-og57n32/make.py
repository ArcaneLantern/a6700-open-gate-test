"""Crea og57n32_a6700_v2 (candidato de Carbon con 0x698/a48/ae8/b88 como en ogsq32) y su cabecera, con el generador del propio kit."""
import hashlib, json, struct, sys
from pathlib import Path

KIT = Path(r"a6700fw\a6700-open-gate-test\windows\tools")
H = KIT / "camera_tests/CT6_memory_read_check"
FW = Path(r"a6700fw\out\firmware.tar_unpacked\0700_part_image\dev")
CARBON = Path(r"a6700_6k\og57n32_a6700_v1.json")
OUT = Path(r"a6700fw\og57n32")
REVERT = (0x698, 0xA48, 0xAE8, 0xB88)

d = json.loads(CARBON.read_text(encoding="utf-8"))
t5 = json.loads((KIT / "modding/designs/ogsq32_a6700_v1.json").read_text(encoding="utf-8"))
base = {p["addr"]: p for p in t5["patches"]}
assert [p["addr"] for p in d["patches"]] == [p["addr"] for p in t5["patches"]]
changed = []
for p in d["patches"]:
    b = base[p["addr"]]
    assert p["old"] == b["old"]
    if p["kind"] != "R":
        assert p["new"] == b["new"]
        continue
    n, n5 = bytearray.fromhex(p["new"]), bytes.fromhex(b["new"])
    for o in REVERT:
        assert struct.unpack_from("<H", n, o)[0] == 1992 and struct.unpack_from("<H", n5, o)[0] == 1990
        n[o:o + 2] = n5[o:o + 2]
    p["new"] = n.hex()
    p["note"] = p["note"].replace("bic#7=1992, ", "0x698 family kept at ogsq32's 1990, ")
    changed.append(sum(n[i:i + 2] != n5[i:i + 2] for i in range(0, len(n), 2)))
assert d["stored_records"] == t5["stored_records"] and d["stored_record_extra"] == t5["stored_record_extra"]
d["design"] = "og57n32_a6700_v2"
d["summary"].pop("bic7_sv_align_u16", None)
d["generated_by"] = "a6700fw/og57n32/make.py from a6700_6k/og57n32_a6700_v1.json"
(OUT / "og57n32_a6700_v2.json").write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8", newline="\n")
print("u16 distintos de ogsq32 por registro:", changed)

# generador del kit: mismas funciones, con las rutas de este PC (su modulo parse_dmmcfg no esta publicado y no se usa aqui)
src = (H / "helper_a6700/gen_a6700_write.py").read_text(encoding="utf-8")
for a, b in (("import parse_dmmcfg  # noqa: E402\n", ""),
             ('EX = ROOT / "work/extracted/a6700_200/0700_part_image/dev"', "EX = FW_DIR"),
             ('(EX / "nflasha8/cpapp-b.bin")', '(EX / "nflasha8_unpacked/cpapp-b.bin")')):
    assert src.count(a) == 1, a
    src = src.replace(a, b)
g = {"__name__": "gen", "__file__": str(H / "helper_a6700/gen_a6700_write.py"), "FW_DIR": FW}
exec(compile(src, "gen_a6700_write", "exec"), g)
g["OUT"] = OUT / "build"
g["sites_header"]("ogsq32_a6700_v1")
shipped = (H / "helper/expected_sites_ogsq32_a6700_v1.h").read_bytes().replace(b"\r\n", b"\n")
made = (OUT / "build/expected_sites_ogsq32_a6700_v1.h").read_bytes()
print("cabecera ogsq32 regenerada == la del kit:", made == shipped)
assert made == shipped
g["DES"] = OUT
g["RATIO"]["og57n32_a6700_v2"] = (27, 32)
print("cabecera nueva:", g["sites_header"]("og57n32_a6700_v2"))
