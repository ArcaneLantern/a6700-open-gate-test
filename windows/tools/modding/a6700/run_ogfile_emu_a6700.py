"""A6700 2.00: function-level emulation of the encoder-side designs, stock against changed, in the A6700's own av-cam.bin and libmpr.so. The
changes are applied in emulated memory only. 2026-11-26 (A6700 port, modding/A6700_PORT_ENCODER.md); made from run_ogfile_emu_fx30.py.

Designs:
  ogfile2560_hs_s_a6700_v1 / _v2   our builder's (build_ogfile.py --build a6700_200 [--meta]): the FX30 run's checks, unchanged
  ogfile2560_full_a6700_v1         the contributed 3840x2560 design (build_ogfile_a6700.py): 24/25/50p, HS / S / S-I, input-rate-120 rows
  ogfile57r260_a6700_v1            the contributed 5760x3840 design;  ogfile57r300_a6700_v1  ours (build_og57.py --build a6700_200 --rate300)

The A6700's av-cam.bin is the FX30's code moved (its unit-type table, descriptors and clip table are the FX30's byte for byte), so the
functions are found by the FX30's bodies (build/avcam_fnport.py's normaliser) and asserted first:
  descriptor matcher   0x2248c0  = FX30 0x224490 (A7 IV 0x21b780, whole body);  reads the descriptors at 0x3936e8
  memory-class         0x21c808  = FX30 0x21c40c (A7 IV 0x2136c4, whole body);  reads the unit-type table at 0x393648
  allocator (DMM open) 0x22bcd4  = FX30 0x22b8a4;  log 0x27b890 = FX30 0x27b418;  log head 0x27b850
  clip format          0x1956ac  = FX30 0x1956c0;  reads the clip table at 0x39156c
  start-block builder  0x220604  = FX30 0x220208, called from the command fill 0x21e318 (the A7 IV's six instructions before the call)
  memcpy / memset      0x27bdac / 0x27bdc4
  codec memory         vcd_firmware_imola2.bin against the A6700's main-processor blocks (frame rates 0x3311a0)
  libmpr.so            the encoder request's raster (g_videoParamComb 0x27e590), the MP4 track config 0x1ec14c, CompareResolution 0x15e494
Run with the Python that has Unicorn:  C:\\Python313\\python.exe -B build/run_ogfile_emu_a6700.py     writes evidence/a6700/encoder/ogfile_emu_a6700.json
Nothing was run on a camera.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import avcam_fnport  # noqa: E402
import emu_mp4_meta  # noqa: E402
import emu_vcd_chmem as V  # noqa: E402
import locate_file  # noqa: E402
from run_ogfile_emu import AVB, AvCam, D, pokes  # noqa: E402

BUILD = "a6700_200"
DESC, NDESC, UNIT_TABLE, FPS_TABLE, CLIP = 0x3936E8, 689, 0x393648, 0x3311A0, 0x39156C
PROFILES = ((0x3ABA78, 373), (0x3C3078, 316))
COMB, COMPARE_RES = 0x27E590, 0x15E494
FN = {"DESC": AVB + DESC, "MATCH": AVB + 0x2248C0, "CLIPFN": AVB + 0x1956AC, "UNITFN": AVB + 0x21C808, "BUILDER": AVB + 0x220604,
      "DMM_OPEN": AVB + 0x22BCD4, "LOGF": AVB + 0x27B890, "LOGH": AVB + 0x27B850, "MEMSET": AVB + 0x27BDC4, "MEMCPY": AVB + 0x27BDAC}
# FX30 6.01 function -> A6700 2.00 function, compared whole (the FX30 run found its own against the A7 IV's)
FX30_FN = {"matcher": (0x224490, 0x2248C0, 624), "memory_ids": (0x21C40C, 0x21C808, 1304), "allocator": (0x22B8A4, 0x22BCD4, 568), "log": (0x27B418, 0x27B890, 96),
           "clip_format": (0x1956C0, 0x1956AC, 212), "log_head": (0x27B3D8, 0x27B850, 32)}
V.DESC, V.NDESC, V.UNIT_TABLE, V.FPS_TABLE = AVB + DESC, NDESC, AVB + UNIT_TABLE, AVB + FPS_TABLE
STRICT = ("ogfile2560_hs_s_a6700_v1", "ogfile2560_hs_s_a6700_v2")
OTHERS = ("ogfilesi2560_a6700_v1", "ogfile2560_full_a6700_v1", "ogfile57r260_a6700_v1", "ogfile57r300_a6700_v1")
W0, H0 = 3840, 2160


def bl_target(img, at):
    w = struct.unpack_from("<I", img, at)[0]
    assert w & 0xFC000000 == 0x94000000, hex(w)
    return at + 4 * ((w & 0x3FFFFFF) - ((w & 0x2000000) << 1))


def adrp_add(img, add_at):
    w2 = struct.unpack_from("<I", img, add_at)[0]
    assert w2 & 0xFFC00000 == 0x91000000, hex(w2)
    rn = (w2 >> 5) & 31
    for at in range(add_at - 4, add_at - 36, -4):
        w = struct.unpack_from("<I", img, at)[0]
        if w & 0x9F000000 == 0x90000000 and (w & 31) == rn:
            imm = ((w >> 29) & 3) | (((w >> 5) & 0x7FFFF) << 2)
            imm -= (1 << 21) if imm & (1 << 20) else 0
            return (at & ~0xFFF) + (imm << 12) + ((w2 >> 10) & 0xFFF)
    raise AssertionError("no ADRP before %#x" % add_at)


def find_functions(a7, fx, av):
    """Assert where the A6700's functions are. Returns a dict for the report."""
    exact = avcam_fnport.port(BUILD, [0x21B780, 0x2136C4, 0x222BD0, 0x27278C], a7, av)
    assert {k: v[0] for k, v in exact.items()} == {0x21B780: 0x2248C0, 0x2136C4: 0x21C808, 0x222BD0: 0x22BCD4, 0x27278C: 0x27B890}, exact
    for name, (f_at, a_at, size) in FX30_FN.items():
        n = size // 4
        assert avcam_fnport.normalise(struct.unpack_from("<%dI" % n, fx, f_at)) == avcam_fnport.normalise(struct.unpack_from("<%dI" % n, av, a_at)), name
    # the tables they read: the same ADRP/ADD places as the FX30's, moved with the function
    assert adrp_add(av, 0x1956AC + (0x1956D4 - 0x1956C0)) == CLIP and adrp_add(av, 0x2248C0 + (0x2245B8 - 0x224490)) == DESC \
        and adrp_add(av, 0x21C808 + (0x21C500 - 0x21C40C)) == UNIT_TABLE
    # the tables themselves are the FX30's bytes
    assert av[UNIT_TABLE:UNIT_TABLE + 0xA0] == fx[0x3926B8:0x3926B8 + 0xA0] and av[DESC:DESC + NDESC * 0x90] == fx[0x392758:0x392758 + NDESC * 0x90]
    assert av[CLIP:CLIP + 0x80] == fx[0x39061C:0x39061C + 0x80]
    # the start-block builder: the call in the command fill, after the A7 IV's six instructions
    seq = struct.unpack_from("<6I", a7, 0x2151D4)
    sites = [x for x in range(0x210000, 0x230000, 4) if struct.unpack_from("<6I", av, x) == seq]
    assert sites == [0x21E318], sites
    assert bl_target(av, 0x21E318 + 0x18) == 0x220604
    n = 181                                              # the builder's first 181 instructions are the A7 IV's (as on the FX30)
    assert avcam_fnport.normalise(struct.unpack_from("<%dI" % n, fx, 0x220208)) == avcam_fnport.normalise(struct.unpack_from("<%dI" % n, av, 0x220604))
    for f_at, a_at in ((0x27B934, 0x27BDAC), (0x27B94C, 0x27BDC4)):
        wf, wa = struct.unpack_from("<6I", fx, f_at), struct.unpack_from("<6I", av, a_at)
        assert wf[:2] == wa[:2] and wf[3:] == wa[3:] and bl_target(fx, f_at + 8) - 0 >= 0 and bl_target(av, a_at + 8) >= 0, (hex(f_at), hex(a_at))
    assert av[FPS_TABLE:FPS_TABLE + 60] == a7[0x3220A0:0x3220A0 + 60]
    return {"matcher": "0x2248c0 (= FX30 0x224490, A7 IV 0x21b780)", "memory_ids": "0x21c808 (= FX30 0x21c40c, A7 IV 0x2136c4)", "allocator": "0x22bcd4",
            "log": "0x27b890, head 0x27b850", "clip_format": "0x1956ac (= FX30 0x1956c0)", "start_block": "0x220604 (called at 0x21e330; = FX30 0x220208)",
            "memcpy_memset": "0x27bdac / 0x27bdc4",
            "tables_read": {"descriptors": hex(DESC), "unit_types": hex(UNIT_TABLE), "clip": hex(CLIP), "frame_rates": hex(FPS_TABLE)},
            "tables_equal_the_fx30s": "unit types, 689 descriptors, clip formats: byte for byte"}


def sizes_of(table_row, cfg):
    def size_of(i):
        units = [u for kk in cfg.id_json(i).get("keys", []) for u in kk["units"]] if i else []
        return max(u["size_bytes"] for u in units) if units else None
    return [size_of(i) for i in table_row]


def avcam_checks(name, av, strict):
    design = json.loads((D / f"{name}.json").read_text(encoding="utf8"))
    assert design["build"] == BUILD
    W1, H1 = design["raster"]
    big = "%dx%d" % (W1, H1)
    changed = bytearray(av)
    for off, new_bytes in pokes(D / f"{name}_pokes_avcam.txt"):
        changed[off:off + len(new_bytes)] = new_bytes
    changed = bytes(changed)
    s, c = AvCam(av, FN), AvCam(changed, FN)
    res = {"design": name, "format": design["format"], "raster": [W1, H1]}
    changed_set = {p["descriptor"] for p in design["descriptors"]}
    part = {p["descriptor"]: p.get("part", "builder") for p in design["descriptors"]}
    # ---- the matcher. The request is built from the stock descriptor's own fields (what libmpr sends does not change) with the raster replaced.
    sel = []
    for p in design["descriptors"]:
        k = p["descriptor"]
        d = s.desc(k)
        row = {"descriptor": k, "part": part[k], "key": d["key"], "stock_3840x2160": s.select(d, W0, H0), "stock_" + big: s.select(d, W1, H1),
               "changed_" + big: c.select(d, W1, H1), "changed_3840x2160": c.select(d, W0, H0)}
        # as designed: stock finds a row only at 3840x2160, changed only at the new size, and it is the same row (a twin that the matcher reaches
        # first counts for both: XAVC S-I rows are there twice, keys 105xxx before 205xxx)
        # A design that changes only the first of two twins (our S-I builder's: the UseCore 2 rows, not their UseCore 0 twins) leaves the twin to
        # answer a 3840x2160 request; that request no longer comes once the comb row says the new size (the FX3 kit's I19 has the same property).
        left = row["changed_3840x2160"]
        row["twin_left_at_3840x2160"] = left is not None and left not in changed_set and s.select(s.desc(left), W0, H0) == row["stock_3840x2160"]
        row["as_designed"] = (row["stock_3840x2160"] is not None and row["stock_" + big] is None and (left is None or row["twin_left_at_3840x2160"])
                              and row["changed_" + big] == row["stock_3840x2160"] and row["changed_" + big] in changed_set)
        row["reaches_itself"] = row["changed_" + big] == k
        sel.append(row)
    untouched, twins = [], 0
    codecs = {s.desc(k)["codec"] for k in changed_set}
    for k in range(NDESC):
        d = s.desc(k)
        if (d["w"], d["h"]) != (W0, H0) or k in changed_set or d["codec"] not in codecs:
            continue
        a, b = s.select(d, W0, H0), c.select(d, W0, H0)
        if a in changed_set:                              # an untouched twin of a changed row: stock never reaches it; see above
            twins += 1
            continue
        untouched.append({"descriptor": k, "codec": hex(d["codec"]), "input_rate": d["infr"], "coding_rate_code": d["codfr"], "stock": a, "changed": b,
                          "changed_" + big: c.select(d, W1, H1)})
    res["encoder_selection"] = {"every_changed_descriptor_as_designed": all(r["as_designed"] for r in sel),
                                "not_as_designed": [r for r in sel if not r["as_designed"]][:12],
                                "rows_that_reach_an_earlier_twin": sum(1 for r in sel if r["as_designed"] and not r["reaches_itself"]),
                                "untouched_twins_of_changed_rows": twins,
                                "changed": sel, "untouched_checked": len(untouched),
                                "untouched_same_answer": all(u["stock"] == u["changed"] for u in untouched),
                                "untouched_refuse_" + big: all(u["changed_" + big] is None for u in untouched),
                                "untouched_by_rate_code": {str(rc): sum(1 for u in untouched if u["coding_rate_code"] == rc) for rc in sorted({u["coding_rate_code"] for u in untouched})}}
    res["clip_code"] = [{"raster": [w, h], "stock": s.clip(w, h), "changed": c.clip(w, h)} for w, h in ((W1, H1), (W0, H0), (8192, 4320), (1920, 1080))]
    # ---- the memory class av-cam asks for: one request per (codec, input rate, coding rate) of the changed rows
    mc, seen = [], set()
    for p in design["descriptors"]:
        d = s.desc(p["descriptor"])
        sig = (d["codec"], d["infr"], d["codfr"])
        if sig in seen:
            continue
        seen.add(sig)
        mc.append({"descriptor": p["descriptor"], "part": part[p["descriptor"]], "codec": hex(d["codec"]), "input_rate": d["infr"], "coding_rate_code": d["codfr"],
                   "request_" + big: {"stock": s.unit_ids(d, W1, H1), "changed": c.unit_ids(d, W1, H1)},
                   "request_3840x2160": {"stock": s.unit_ids(d, W0, H0), "changed": c.unit_ids(d, W0, H0)}})
    res["memory_class"] = mc
    # ---- the codec firmware's own calculation for every changed row, against the blocks of the unit type av-cam's rule gives it
    assert locate_file.locate(BUILD, "vcd_firmware_imola2.bin").read_bytes() == locate_file.locate("a7iv_602", "vcd_firmware_imola2.bin").read_bytes()
    fw = V.Firmware()
    table = [struct.unpack_from("<4I", changed, UNIT_TABLE + 0x10 * k) for k in range(10)]
    cfg = V.parse_dmmcfg.Config(V.parse_dmmcfg.find_file(BUILD, "setting"), BUILD)
    have = {t: sizes_of(table[t], cfg) for t in range(10)}
    mem = []
    for dd in V.descriptors(changed):
        if dd["index"] not in changed_set:
            continue
        need = fw.need(dd)
        t, why = V.unit_type(dd)
        h = have.get(t)
        fits = None if t is None else all(need[k] <= (h[i] or 0) for i, k in enumerate(("cd", "ld", "multi")) if need[k])
        mem.append({"descriptor": dd["index"], "part": part[dd["index"]], "raster": [dd["w"], dd["h"]], "fps": dd["fps"], "use_core": dd["use_core"], "unit_type": t, "why": why,
                    "need": {k: need[k] for k in ("cd", "ld", "multi")}, "blocks": h, "fits": fits, "firmware_asserts": need["asserts"]})
    by_part = {}
    for m in mem:
        e = by_part.setdefault(m["part"], {"rows": 0, "fit": 0, "do_not_fit": 0, "refused_by_the_memory_rule": 0, "wrong_raster": 0, "firmware_asserts": 0,
                                           "unit_types": [], "largest_need": {"cd": 0, "ld": 0, "multi": 0}})
        e["rows"] += 1
        e["fit"] += m["fits"] is True
        e["do_not_fit"] += m["fits"] is False
        e["refused_by_the_memory_rule"] += m["unit_type"] is None
        e["wrong_raster"] += m["raster"] != [W1, H1]
        e["firmware_asserts"] += bool(m["firmware_asserts"])
        e["unit_types"] = sorted(set(e["unit_types"]) | {str(m["unit_type"])})
        for k in e["largest_need"]:
            e["largest_need"][k] = max(e["largest_need"][k], m["need"][k])
    res["codec_memory"] = {"unit_type_rows_after_the_change": {str(t): {"ids": [hex(i) for i in table[t]], "bytes": have[t]} for t in (2, 3, 4, 9)},
                           "by_part": by_part, "rows": mem}
    # ---- the start-block builder
    prof = {}
    for base, n in PROFILES:
        for k in range(n):
            prof[struct.unpack_from("<I", av, base + k * 0x100 + 0x20)[0]] = base + k * 0x100
    starts = []
    for p in design["descriptors"]:
        d = s.desc(p["descriptor"])
        o = prof[d["key"]]
        ten = d["bitl"] == 1
        try:
            a, _ = s.start_block(av[o:o + 0x100], d, W0, H0, ten)
            b, seq_b = c.start_block(changed[o:o + 0x100], d, W1, H1, ten)
        except RuntimeError as e:
            starts.append({"descriptor": p["descriptor"], "part": part[p["descriptor"]], "error": str(e), "accepted": False})
            continue
        ok = a["returned"] == 1 and not a["errors_logged"] and a["crop_size"] == [W0, H0] and b["returned"] == 1 and not b["errors_logged"] and b["crop_size"] == [W1, H1]
        starts.append({"descriptor": p["descriptor"], "part": part[p["descriptor"]], "key": d["key"], "stock_2160": a, "changed": b,
                       "rows_for_first_core_in_the_block": struct.unpack_from("<H", seq_b, 0xC)[0], "accepted": ok})
    res["start_block"] = {"every_changed_profile_accepted": all(x["accepted"] for x in starts),
                          "not_accepted_by_part": {k: sum(1 for x in starts if x["part"] == k and not x["accepted"]) for k in sorted({x["part"] for x in starts})},
                          "rows": starts}
    if strict:
        m_ok = all(m["fits"] and m["unit_type"] == 3 and m["raster"] == [W1, H1] and not m["firmware_asserts"] for m in mem)
        res["strict"] = {"matcher": res["encoder_selection"]["every_changed_descriptor_as_designed"] and all(r["reaches_itself"] for r in sel)
                         and res["encoder_selection"]["untouched_same_answer"] and res["encoder_selection"]["untouched_refuse_" + big] and len(untouched) > 0,
                         "clip": [x["changed"] for x in res["clip_code"]] == [23, 23, 0, 26] and [x["stock"] for x in res["clip_code"]] == [0, 23, 3, 26],
                         "memory class": all(v["request_" + big]["changed"]["memory_ids_asked"][:4] == ["0x486", "0x474", "0x47a", "0x477"]
                                             and v["request_3840x2160"]["changed"] == v["request_3840x2160"]["stock"] for v in mc),
                         "codec memory": m_ok, "start block": res["start_block"]["every_changed_profile_accepted"]}
    return res


def libmpr_checks(name, lm):
    design = json.loads((D / f"{name}.json").read_text(encoding="utf8"))
    W1, H1 = design["raster"]
    changed = bytearray(lm)
    for off, new_bytes in pokes(D / f"{name}_pokes_libmpr.txt"):
        changed[off:off + len(new_bytes)] = new_bytes
    changed = bytes(changed)
    comb_rows = sorted({(int(p["file_off"], 16) - COMB) // 0x18 for p in design["patches"] if p["kind"] == "L1-comb"})
    rows = {comb: {"stock": list(struct.unpack_from("<HH", lm, COMB + 0x18 * comb + 4)), "changed": list(struct.unpack_from("<HH", changed, COMB + 0x18 * comb + 4))}
            for comb in range(12)}
    libs = {"stock": emu_mp4_meta.Lib(lm, BUILD), "changed": emu_mp4_meta.Lib(changed, BUILD)}
    mp4 = {}
    for comb in (0, 2, 5, 7, 9):
        for rate_code in (0, 2):
            got = {}
            for k, lib in libs.items():
                r, cfg = lib.config(comb, rate_code, 0x20)
                got[k] = [struct.unpack_from("<H", cfg, 0x2A)[0], struct.unpack_from("<H", cfg, 0x28)[0]]
            mp4[f"comb {comb} rate code {rate_code}"] = got
    has_meta = any(p["kind"] == "L4-mp4size" for p in design["patches"])
    want = [W1, H1] if has_meta else [W0, H0]
    # CompareResolution(this, resolution = height << 16 | width, class): which classes each size is, stock and changed
    cr = {}
    for w, h in ((3840, 2160), (3840, 2560), (5760, 3840), (1920, 1080), (7680, 4320)):
        cr["%dx%d" % (w, h)] = {k: [cls for cls in range(7) if lib.call(COMPARE_RES, 0, (h << 16) | w, cls) & 1] for k, lib in libs.items()}
    ok = (all(rows[r]["stock"] == [W0, H0] and rows[r]["changed"] == [W1, H1] for r in comb_rows)
          and all(rows[r]["stock"] == rows[r]["changed"] for r in range(12) if r not in comb_rows)
          and all(v["stock"] == [W0, H0] and v["changed"] == want for v in mp4.values()))
    return {"comb_rows_changed": comb_rows, "encoder_request_raster_by_comb": {str(k): v for k, v in rows.items() if k in (0, 2, 5, 7, 9)},
            "mp4_track_config_by_comb": mp4, "mp4_size_expected": want, "compare_resolution_classes": cr, "as_designed": ok}


def main():
    a7 = locate_file.locate("a7iv_602", "av-cam.bin").read_bytes()
    fx = locate_file.locate("fx30_601", "av-cam.bin").read_bytes()
    av = locate_file.locate(BUILD, "av-cam.bin").read_bytes()
    lm = locate_file.locate(BUILD, "libmpr.so").read_bytes()
    out = {"about": "A6700 2.00: function-level emulation of the encoder-side designs, stock against changed, in the A6700's own av-cam.bin and libmpr.so "
                    "(build/run_ogfile_emu_a6700.py). The requests are built from the descriptors' own fields, not from a traced caller. Nothing was run on a camera.",
           "functions": find_functions(a7, fx, av), "designs": []}
    names = [n for n in STRICT + OTHERS if (D / f"{n}.json").exists()]
    bad = []
    for name in names:
        r = avcam_checks(name, av, name in STRICT)
        r["libmpr"] = libmpr_checks(name, lm)
        out["designs"].append(r)
        e = r["encoder_selection"]
        big = "%dx%d" % tuple(r["raster"])
        print("==", name)
        print("   matcher: changed rows as designed: %s (%d rows; %d reach an earlier twin) | untouched %d, same answer %s, refuse %s: %s"
              % (e["every_changed_descriptor_as_designed"], len(e["changed"]), e["rows_that_reach_an_earlier_twin"], e["untouched_checked"], e["untouched_same_answer"],
                 big, e["untouched_refuse_" + big]))
        for row in e["not_as_designed"][:6]:
            print("      NOT as designed:", {k: v for k, v in row.items() if k != "key"})
        print("   clip code:", [(x["raster"], x["stock"], x["changed"]) for x in r["clip_code"]])
        for v in r["memory_class"]:
            print("   memory class, #%d %s codec %s in %d rate %d: %s stock %s -> changed %s%s" % (
                v["descriptor"], v["part"], v["codec"], v["input_rate"], v["coding_rate_code"], big, v["request_" + big]["stock"]["memory_ids_asked"],
                v["request_" + big]["changed"]["memory_ids_asked"], "" if not v["request_" + big]["changed"]["errors_logged"] else " ERRORS " + str(v["request_" + big]["changed"]["errors_logged"])))
        cm = r["codec_memory"]
        print("   unit-type rows:", {t: (v["ids"], v["bytes"]) for t, v in cm["unit_type_rows_after_the_change"].items()})
        for k, v in cm["by_part"].items():
            print("   codec memory, %-8s rows %d: fit %d, do not fit %d, refused by the memory rule %d, asserts %d; unit types %s; largest need %s"
                  % (k, v["rows"], v["fit"], v["do_not_fit"], v["refused_by_the_memory_rule"], v["firmware_asserts"], v["unit_types"], v["largest_need"]))
        print("   start block: every changed profile accepted:", r["start_block"]["every_changed_profile_accepted"], r["start_block"]["not_accepted_by_part"])
        print("   libmpr: as designed:", r["libmpr"]["as_designed"], "| comb rows", r["libmpr"]["comb_rows_changed"], "| MP4 config", r["libmpr"]["mp4_size_expected"],
              "| CompareResolution classes:", r["libmpr"]["compare_resolution_classes"])
        if "strict" in r:
            bad += [f"{name}: {k}" for k, v in r["strict"].items() if not v]
        if not r["libmpr"]["as_designed"]:
            bad.append(f"{name}: libmpr")
    dst = ROOT / "evidence/a6700/encoder/ogfile_emu_a6700.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=1) + "\n", encoding="utf8", newline="\n")
    print("wrote", dst)
    print("ALL STRICT CHECKS PASS (our builder's designs; the contributed designs are reported above)" if not bad else "FAILED: " + "; ".join(bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
