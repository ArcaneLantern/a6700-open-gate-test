"""A6700 2.00: the contributed encoder-side designs, compared site by site with our own builders' output and written in our design schema
(A6700 port, 2026-11-26; modding/A6700_PORT_ENCODER.md). Design only: nothing is written to a firmware file, nothing is sent to a camera.

  work\\venv\\Scripts\\python.exe -I -B build\\build_ogfile_a6700.py

Run first (they write the designs this compares against):
  build\\build_ogfile.py --build a6700_200 --meta      ogfile2560_hs_s_a6700_v1 / _v2: XAVC HS 4K + XAVC S 4K at 23.98p and 25p (our L19 / N19 shape)
  build\\build_og57.py --build a6700_200 --rate300     ogfile57r300_a6700_v1: the A7 IV's 5760x3840 two-core design at the A6700's addresses

The contributed kit (work/contrib/a6700_v1.0, unpacked from A6700_OpenGate.zip) is DATA here: its two design files are parsed, nothing of it
is imported or run. Its designs are supersets of ours:

  ogfile2560_hs_s_pal50_a6700_v1  ->  modding/designs/ogfile2560_full_a6700_v1.json
      our 29 descriptors (the same bytes), plus 50p (rate code 1), XAVC S-I 4K (codec 0x18), HEVC 4:2:0 8-bit, and the rows a slow-and-quick
      recording uses (input rate 120); the 50p long-GOP rows are made two-core; unit-type row 3 in the two-core order of our A7 IV 5.7K design
      (ours: := row 2); level bytes raised for 50p and S-I; the MP4 track heights (ours) and one more libmpr instruction, CompareResolution
  ogfile57r260_a6700_v1           ->  modding/designs/ogfile57r260_a6700_v1.json
      our A7 IV two-core 5760x3840 design (build_og57.py) with 260 / 290 / 290 million in place of 300 / 340 / 340, plus S-I, HEVC 8-bit and
      the input-rate-120 rows, and the nine MP4 size sites (build/mp4_meta_sites.py A6700)

Every statement above is asserted below against the 2.00 files; what is only in the contributed designs is labelled per site ("part") and
counted, so a kit can carry a part or leave it out. Also checked: every old byte, no overlap, each profile site lies in the profile row of the
key its descriptor names, and which changed profiles are shared with descriptors the design does not change.
Writes the two designs, their poke lists (for the emulators), and evidence/a6700/encoder/contrib_enc_compare.json.
"""
import collections
import hashlib
import json
import struct
import sys
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import build_ogfile as B  # noqa: E402
import locate_file  # noqa: E402
import mp4_meta_sites  # noqa: E402

BUILD = "a6700_200"
B.use_build(BUILD)
DESC, NDESC, DSIZE, UNIT, CLIP, COMB, PROFILES = B.DESC, B.NDESC, B.DSIZE, B.UNIT_TABLE, B.CLIP, B.COMB, B.PROFILE_TABLES
AVB = B.AVB
KIT = ROOT / "work/contrib/a6700_v1.0/A6700 OpenGate/a6700-opengate_v1.0/designs"
DES = ROOT / "modding/designs"
COMPARE_RESOLUTION = 0x15E4E4          # LibMediaProfileIf::xavcIfo_CommonMediaProfile::CompareResolution (0x15e494), the QFHD case's `cset w0, eq`
RATE_NAME = {1: "50p", 3: "25p", 5: "23.98p"}
TWO_CORE_ROW = (0x477, 0x486, 0x474, 0x47A)      # {CD, LD, multi, ES}: the order of build_og57.py (A7 IV 5.7K), which holds a two-core picture
PART_TEXT = {
    "builder": "XAVC HS 4K / XAVC S 4K at 23.98p and 25p, normal speed: the descriptors our builder changes",
    "s_i": "XAVC S-I 4K (codec 0x18) at 23.98p and 25p, normal speed (both the UseCore 2 rows and their UseCore 0 twins)",
    "hevc8": "HEVC 4:2:0 8-bit rows at 23.98p and 25p (no menu format of this camera that we know of)",
    "p50": "50p (coding-rate code 1), normal speed: HEVC, AVC and S-I; the one-core long-GOP rows are made two-core",
    "sq120": "rows with input rate 120 (slow and quick recording at 100/120 frames a second coded as 23.98p, 25p or 50p)",
}


def descriptor(av, k):
    o = DESC + k * DSIZE
    codec, infr, codfr, f0c, f10, chroma, bitl = struct.unpack_from("<7I", av, o)
    return {"descriptor": k, "codec": codec, "input_rate": infr, "coding_rate_code": codfr, "f0c": f0c, "quality_class": f10, "chroma_req": chroma, "bit_len_req": bitl,
            "profile_key": struct.unpack_from("<I", av, o + 0x28)[0], "raster": list(struct.unpack_from("<HH", av, o + 0x7E)), "use_core": av[o + 0x78],
            "pred_mode": av[o + 0x85], "f38": list(struct.unpack_from("<II", av, o + 0x38))}


def part_of(d):
    if d["input_rate"]:
        return "sq120"
    if d["coding_rate_code"] == 1:
        return "p50"
    if d["codec"] == 0x18:
        return "s_i"
    if d["codec"] == 0xE and (d["chroma_req"], d["bit_len_req"]) == (0, 0):
        return "hevc8"
    return "builder"


def fmt_of(d):
    name = {4: "XAVC S 4K (AVC)", 0xE: "XAVC HS 4K (HEVC)", 0x18: "XAVC S-I 4K (AVC intra)"}[d["codec"]]
    return name + ", " + {(0, 0): "4:2:0 8-bit", (0, 1): "4:2:0 10-bit", (1, 1): "4:2:2 10-bit"}[(d["chroma_req"], d["bit_len_req"])]


def bytemap(patches):
    m = {}
    for p in patches:
        o, old, new = int(p["file_off"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])
        for i in range(len(old)):
            if old[i] != new[i]:
                m[(p["binary"], o + i)] = (old[i], new[i])
    return m


def convert(src_name, dst_name, ours_name, av, lm, sha):
    src = json.loads((KIT / f"{src_name}.json").read_text(encoding="utf8"))
    ours = json.loads((DES / f"{ours_name}.json").read_text(encoding="utf8"))
    W1, H1 = src["raster"]
    assert src["build"] == BUILD and src["artifact_sha256"] == sha == ours["artifact_sha256"], "another file"
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    prof_row, key_users = {}, {}
    for base, n in PROFILES:
        for k in range(n):
            prof_row[struct.unpack_from("<I", av, base + k * 0x100 + 0x20)[0]] = base + k * 0x100
    for k in range(NDESC):
        key_users.setdefault(struct.unpack_from("<I", av, DESC + k * DSIZE + 0x28)[0], []).append(k)
    row_key = {o: key for key, o in prof_row.items()}
    # ---- the descriptors the design changes, read from the file (the contributed list gives only the indices)
    descs = []
    for x in src["descriptors"]:
        d = descriptor(av, x["idx"])
        assert int(x["desc_off"], 16) == DESC + x["idx"] * DSIZE and x["key"] == d["profile_key"] and d["raster"] == [3840, 2160]
        d.update(part=part_of(d), format=fmt_of(d), rate=RATE_NAME[d["coding_rate_code"]])
        descs.append(d)
    changed_set = {d["descriptor"] for d in descs}
    part_by_desc = {d["descriptor"]: d["part"] for d in descs}
    part_by_key = {}
    for d in descs:
        part_by_key.setdefault(d["profile_key"], set()).add(d["part"])
    assert {d["descriptor"] for d in descs if d["part"] == "builder"} == {p["descriptor"] for p in ours["descriptors"]}, "our builder's descriptors are not the 'builder' part"
    # ---- the sites
    meta = {a: (new, want, why) for a, new, want, why in mp4_meta_sites.sites(W1, H1, BUILD)}
    patches, shared = [], []
    for s in src["sites"]:
        off, old, new = int(s["file_off"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"])
        data = av if s["binary"] == "av-cam.bin" else lm
        assert len(old) == len(new) <= 16 and old != new and data[off:off + len(old)] == old, (s["binary"], hex(off))
        kind, part, note = s["kind"], None, s["note"]
        if s["binary"] == "libmpr.so":
            if s["code"]:
                assert len(old) == 4 and off % 4 == 0
                i_old, i_new = next(md.disasm(old, off)), next(md.disasm(new, off))
                if off in meta:
                    assert new == meta[off][0] and (i_old.mnemonic, i_old.op_str) == meta[off][1], hex(off)
                    part, note = "mp4_header", meta[off][2] + f" (`{i_old.mnemonic} {i_old.op_str}` -> `{i_new.mnemonic} {i_new.op_str}`)"
                else:
                    assert off == COMPARE_RESOLUTION and (i_old.mnemonic, i_old.op_str, i_new.mnemonic, i_new.op_str) == ("cset", "w0, eq", "cset", "w0, hs")
                    kind, part = "L5-mediaprofile", "media_profile"
                    note = ("LibMediaProfileIf CompareResolution (0x15e494), the 3840-wide case: `cmp w1, #0x870; cset w0, eq` -> `cset w0, hs`: a 3840-wide "
                            "picture of 2,160 rows OR MORE counts as the QFHD class (contributed: for in-camera playback of a file whose headers say 2,560 rows)")
            else:
                row = (off - COMB) // 0x18
                assert kind == "L1-comb" and row in (0, 2, 5, 7, 9) and off - COMB - row * 0x18 in (4, 6) and struct.unpack_from("<HH", lm, COMB + row * 0x18 + 4) == (3840, 2160)
                part = "s_i" if row == 9 else "builder"
        elif kind == "A0-unit":
            assert off == UNIT + 0x30 and struct.unpack("<4I", new) == TWO_CORE_ROW
            part = "unit_row"
            note = ("unit-type table row 3 (above 8,847,360 pixels; ids 0, 0x473, 0x476, 0x479, none of which has memory on this camera) := the 4K class's four "
                    "blocks in the two-core order of build_og57.py: frame buffer CD 0x477 (14.2 MB), LD 0x486 (100.8 MB), multi 0x474 (50.8 MB), ES 0x47a")
        elif kind == "A3-clip":
            assert off == CLIP + 0x14 and struct.unpack("<3I", new) == (W1, H1, B.CLIP_4K)
            part = "clip_row"
        elif kind == "A1-desc":
            k = (off - DESC) // DSIZE
            assert k in changed_set and DESC <= off < DESC + NDESC * DSIZE and (off - DESC) % DSIZE in (0x38, 0x78, 0x7E, 0x80)
            part = part_by_desc[k]
        else:
            row = next(o for o in row_key if o <= off < o + 0x100)
            key = row_key[row]
            assert kind in ("A2-profile", "A2-level", "A2-rate") and ("profile key %d:" % key) in s["note"] and key in part_by_key, (hex(off), s["note"])
            part = "+".join(sorted(part_by_key[key]))
            others = [u for u in key_users[key] if u not in changed_set]
            if others and key not in [x["profile_key"] for x in shared]:
                shared.append({"profile_key": key, "also_used_by_descriptors": others,
                               "their_fields": [{q: descriptor(av, u)[q] for q in ("codec", "input_rate", "coding_rate_code", "raster", "use_core")} for u in others]})
        patches.append({"binary": s["binary"], "kind": kind, "part": part, "file_off": hex(off), "va": hex(off + AVB) if s["binary"] == "av-cam.bin" else hex(off),
                        "old": old.hex(), "new": new.hex(), "note": note, "code": bool(s["code"])})
    for b in ("av-cam.bin", "libmpr.so"):
        sp = sorted((int(p["file_off"], 16), len(p["old"]) // 2) for p in patches if p["binary"] == b)
        assert all(a + n <= c for (a, n), (c, _) in zip(sp, sp[1:])), "sites overlap"
    # every changed descriptor has its raster site and its profile's raster sites
    assert all(any(p["kind"] == "A1-desc" and (int(p["file_off"], 16) - DESC) // DSIZE == d["descriptor"] for p in patches) for d in descs)
    # the code sites: exactly the MP4 size sites of build/mp4_meta_sites.py (and CompareResolution in the 3840x2560 design)
    code = sorted(int(p["file_off"], 16) for p in patches if p["code"])
    assert code == sorted(list(meta) + ([COMPARE_RESOLUTION] if (W1, H1) == (3840, 2560) else [])), [hex(x) for x in code]
    guards = [{"file_off": g["file_off"], "bytes": g["bytes"]} for g in src["libmpr_guards"]]
    assert all(lm[int(g["file_off"], 16):int(g["file_off"], 16) + 4] == bytes.fromhex(g["bytes"]) and int(g["file_off"], 16) not in code for g in guards)
    assert all(any(abs(int(g["file_off"], 16) - c) <= 8 for g in guards) for c in code), "a code site without a guard beside it"
    # ---- against our builder's design
    mo, mt = bytemap(ours["patches"]), bytemap(patches)
    same = sum(1 for k in mo if mt.get(k) == mo[k])
    other = {k: (mo[k], mt[k]) for k in mo if k in mt and mt[k] != mo[k]}
    missing = [k for k in mo if k not in mt]
    assert not missing, "a byte our builder changes is not in the contributed design"
    where = collections.Counter()
    for (b, o), _ in other.items():
        if b == "av-cam.bin" and UNIT + 0x30 <= o < UNIT + 0x40:
            where["unit-type row 3 (ours := row 2 or the same two-core order)"] += 1
        else:
            row = next((r for r in row_key if r <= o < r + 0x100), None)
            assert row is not None and (o - row) in range(0xAC, 0xC8), (b, hex(o))
            where["profile bit-rate figures (ours 300 / 340 / 340 million, contributed 260 / 290 / 290)"] += 1
    by_part = collections.OrderedDict()
    for p in patches:
        e = by_part.setdefault(p["part"], {"sites": 0, "bytes": 0})
        e["sites"] += 1
        e["bytes"] += len(p["old"]) // 2
    kinds = collections.Counter(p["kind"] for p in patches)
    by = {b: [p for p in patches if p["binary"] == b] for b in ("libmpr.so", "av-cam.bin")}
    parts_present = sorted({d["part"] for d in descs})
    out = {"design": dst_name, "build": BUILD, "camera": "ILCE-6700 (A6700), firmware 2.00",
           "title": src["title"],
           "generated_by": "build/build_ogfile_a6700.py from the contributed design %s (work/contrib/a6700_v1.0); compared with %s" % (src_name, ours_name),
           "family": "hs_s_si", "format": "XAVC HS 4K (HEVC), XAVC S 4K (AVC) and XAVC S-I 4K (AVC intra)", "raster": [W1, H1], "rates": src["rates"],
           "artifact_sha256": sha,
           "summary": {b: {"sites": len(ps), "bytes": sum(len(p["new"]) // 2 for p in ps), "code_sites": sum(p["code"] for p in ps)} for b, ps in by.items()},
           "sites_by_kind": dict(kinds), "sites_by_part": by_part,
           "parts": {k: PART_TEXT[k] for k in parts_present},
           "descriptors_by_part": dict(collections.Counter(d["part"] for d in descs)),
           "compared_with_our_builder": {"design": ours_name, "bytes_ours_changes": len(mo), "the_same_in_both": same, "same_place_other_value": dict(where),
                                         "only_in_the_contributed_design": len(mt) - len(mo)},
           "profiles_shared_with_descriptors_the_design_does_not_change": shared,
           "status": "contributed; its author reports it running on an A6700 2.00 (no logs seen). Converted and checked against the 2.00 files here; "
                     "emulated by build/run_ogfile_emu_a6700.py and build/emu_mp4_meta.py --build a6700_200. Never run on a camera by us.",
           "descriptors": descs, "patches": patches, "optional_sites": [],
           "libmpr_code_guards": [{"site": hex(a), "guards": guards if k == 0 else []} for k, a in enumerate(code)]}
    (DES / f"{dst_name}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf8", newline="\n")
    for b, ps in by.items():
        (DES / f"{dst_name}_pokes_{b.split('.')[0].replace('-', '')}.txt").write_text("".join(f"{p['file_off']} {p['new']}\n" for p in ps), encoding="utf8", newline="\n")
    print(dst_name, out["summary"], dict(kinds))
    print("   descriptors by part:", out["descriptors_by_part"])
    print("   sites by part:", {k: (v["sites"], v["bytes"]) for k, v in by_part.items()})
    print("   against %s: %d of its %d changed bytes are the same; other value: %s; only contributed: %d bytes" % (ours_name, same, len(mo), dict(where), len(mt) - len(mo)))
    print("   changed profiles also used by descriptors the design leaves alone:", [(x["profile_key"], x["also_used_by_descriptors"]) for x in shared] or "none")
    return out


def main():
    lm = locate_file.locate(BUILD, "libmpr.so").read_bytes()
    av = locate_file.locate(BUILD, "av-cam.bin").read_bytes()
    sha = {"libmpr.so": hashlib.sha256(lm).hexdigest(), "av-cam.bin": hashlib.sha256(av).hexdigest()}
    res = [convert("ogfile2560_hs_s_pal50_a6700_v1", "ogfile2560_full_a6700_v1", "ogfile2560_hs_s_a6700_v2", av, lm, sha),
           convert("ogfile57r260_a6700_v1", "ogfile57r260_a6700_v1", "ogfile57r300_a6700_v1", av, lm, sha)]
    # ---- pbmpr_a6700_v1: the one libmpr.so instruction of the contributed 3840x2560 design that is about playback, as a design of its own, so a
    # kit whose encoder step is ours (ogfile2560_hs_s_a6700_v2) can carry the whole contributed playback fix as separate steps. A level 19 / 20
    # design with one libmpr.so code site and no av-cam.bin site (the av-cam.bin table then holds the generator's two guards only).
    full = res[0]
    cr = next(p for p in full["patches"] if p["kind"] == "L5-mediaprofile")
    near = [g for g in full["libmpr_code_guards"][0]["guards"] if abs(int(g["file_off"], 16) - COMPARE_RESOLUTION) <= 8]
    assert [g["file_off"] for g in near] == ["0x15e4dc", "0x15e4e0", "0x15e4e8", "0x15e4ec"]
    pb = {"design": "pbmpr_a6700_v1", "build": BUILD, "camera": "ILCE-6700 (A6700), firmware 2.00",
          "title": "In-camera playback of 3840 x 2560 clips, the libmpr.so part: CompareResolution counts a 3840-wide picture of 2,160 rows or more as QFHD",
          "generated_by": "build/build_ogfile_a6700.py (the L5-mediaprofile site of ogfile2560_full_a6700_v1, alone)", "family": "playback", "raster": [3840, 2560],
          "artifact_sha256": sha, "summary": {"libmpr.so": {"sites": 1, "bytes": 4, "code_sites": 1}, "av-cam.bin": {"sites": 0, "bytes": 0, "code_sites": 0}},
          "sites_by_kind": {"L5-mediaprofile": 1},
          "goes_with": "avdec8k_a6700_v1 (P29), pbaspect_a6700_v1 (A29) and pbformat_a6700_v1 (F29) in av-cam.bin; needed only while the files' MP4 headers say "
                       "3840x2560 (ogfile2560_hs_s_a6700_v2). ogfile2560_full_a6700_v1 already holds this site: do not apply both",
          "function": "LibMediaProfileIf::xavcIfo_CommonMediaProfile::CompareResolution(mpr::Resolution, T_MPF_RESOLUTION) 0x15e494: resolution = height << 16 | width; "
                      "class 1 is 3840 x 2160. Emulated (build/run_ogfile_emu_a6700.py): 3840x2560 is class 1 with the site, no class without; 3840x2160, 1920x1080, "
                      "7680x4320 and 5760x3840 answer as before",
          "status": "contributed (its author reports in-camera playback on an A6700 2.00; no logs seen); what calls the function was not followed (virtual call); "
                    "never run on a camera by us",
          "descriptors": [], "patches": [dict(cr)], "optional_sites": [], "libmpr_code_guards": [{"site": hex(COMPARE_RESOLUTION), "guards": near}]}
    (DES / "pbmpr_a6700_v1.json").write_text(json.dumps(pb, indent=1) + "\n", encoding="utf8", newline="\n")
    (DES / "pbmpr_a6700_v1_pokes_libmpr.txt").write_text("%s %s\n" % (cr["file_off"], cr["new"]), encoding="utf8", newline="\n")
    (DES / "pbmpr_a6700_v1_pokes_avcam.txt").write_text("", encoding="utf8", newline="\n")
    print("pbmpr_a6700_v1", pb["summary"])
    ev = ROOT / "evidence/a6700/encoder/contrib_enc_compare.json"
    ev.parent.mkdir(parents=True, exist_ok=True)
    keep = ("design", "raster", "rates", "summary", "sites_by_kind", "sites_by_part", "parts", "descriptors_by_part", "compared_with_our_builder",
            "profiles_shared_with_descriptors_the_design_does_not_change")
    ev.write_text(json.dumps({"about": "The contributed A6700 encoder-side designs against our builders' output, site by site. Generated by build/build_ogfile_a6700.py.",
                              "tables": {"unit_type": hex(UNIT), "descriptors": hex(DESC), "descriptor_count": NDESC, "descriptor_bytes": DSIZE,
                                         "profiles": [[hex(o), n] for o, n in PROFILES], "clip_format": hex(CLIP), "g_videoParamComb": hex(COMB)},
                              "designs": [{k: r[k] for k in keep} for r in res]}, indent=1) + "\n", encoding="utf8", newline="\n")
    print("wrote", ev)


if __name__ == "__main__":
    main()
