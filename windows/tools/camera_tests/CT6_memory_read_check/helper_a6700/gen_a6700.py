"""Write a6700_expected.h for a6700read.c from the A6700 2.00 files and the port designs (A6700 port, 2026-11-26).

  C:\\Python313\\python.exe -B gen_a6700.py

helper_fx30/gen_fx30.py with this build's files, designs and addresses (modding/A6700_PORT*.md). Everything the helper compares against is
taken here from the extracted 2.00 update and from the kit's designs in modding/designs. The helper holds no other constant about the
camera except the addresses listed at the top of this file.
  - Hard sites (stock or target, counted): the sensor design's cells and picture records (L5), the 50p design's (Q5), the raw write
    buffer's four memory-manager words (L13).
  - Soft sites (reported, not counted): the stored drive-parameter records (the camera computes them at start-up from its NTSC or PAL
    table and keeps run-time bytes in them; the PC reads the design offsets), the output-size word and its guards (zero until a movie mode
    has run), the five words of the 5.76K step, the screen words.
  - Main processor: the encoder side is listed as SPANS, the runs of bytes that any of the kit's main-processor designs changes; per
    span the stock bytes and each design's bytes, as packed records. The helper reports STOCK, or which designs' bytes a span holds. The
    words of the three playback designs are listed apart and never counted.
  - The library must stay under the upload bound of 65,520 bytes, so a site longer than 16 bytes (a picture record, a stored record) is
    held as the SHA-256 of its stock and of its target bytes.
Also writes a6700_expected.json (what the PC checks against) and a6700_reference.json (what the PC needs to read a dump). Read-only on
the inputs.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EX = ROOT / "work/extracted/a6700_200/0700_part_image/dev"
DES = ROOT / "modding/designs"
sys.path.insert(0, str(ROOT / "build"))

BASE = 0x108000
LABEL = "a6700read_v1"
CP_LO, CP_HI = 0xC0000, 0x2700000                     # coprocessor addresses a read may have: its logs, image and RAM tables
AVCAM_PHYS, AVCAM_RESERVE = 0x401000000, "@0x401000000"   # kemco.txt: memrsv=0x01000000@0x401000000:ex (A6700_PORT_ENCODER.md)
ID_FILES = {"/libmpr.so": "nflasha15/lib/libmpr.so", "/libsencore.so": "nflasha15/lib/libsencore.so", "/libJiritsu.so": "nflasha15/lib/libJiritsu.so"}
# four 4 KB pages of coprocessor CODE that no design touches and no other build of the fourteen mapped has: a low code page, and the pages of
# three set-ups the kit depends on (0x793000, the movie size table's set-up 0x4ab69c, the drive-parameter constructor block 0x9709c0)
ID_PAGES = (0x128000, 0x793000, 0x4AB000, 0x970000)
# The sensor's register matrix: 154 rows of 20 bytes (the register shadow's address, then one byte per column, 14 columns, 2 spare) and a
# zero row, then the column map (31 words, one per drive mode). A6700_PORT_SENSOR.md.
MATRIX, MATRIX_ROWS, MROW, COLMAP, IDS, NMODES = 0x10CD634, 154, 20, 0x10CE250, 0xDC7B5C, 31
RECS, REC = 0x25DABCC, 0x170
SIZE_TABLE = 0x199EC7C
SENSOR, SENSOR50, DMM, OUTSZ, K16, SCREEN = "ogsq_a6700_v1", "ogsq50_a6700_v1", "dmmwb_a6700_v1", "outsz2560_a6700_v1", "og57cp_a6700_v1", "lcdfill_a6700_v2"
SENSOR32 = "ogsq32_a6700_v1"                           # the exact 3:2 test design (T5): L5's places with other bytes, and one cell more
# the main-processor designs, in the order of the helper's DESIGNS mask (bit k = design k), each with the step that applies it
# (N19's design ogfile2560_hs_s_a6700_v1 is L19's without its two MP4 header sites: the PC reads that state from L19's spans)
MP_DESIGNS = (("ogfile2560_hs_s_a6700_v2", "L19"), ("ogfilesi2560_a6700_v1", "I19"),
              ("ogfile2560_full_a6700_v1", "M19"), ("ogfile57r260_a6700_v1", "K19"), ("pbmpr_a6700_v1", "R19"))
LIB_MAX = 65520                                       # the upload bound (ct6_level1_run.LIB_MAX): the header is kept compact for it
PB_DESIGNS = (("avdec8k_a6700_v1", "P29"), ("pbaspect_a6700_v1", "A29"), ("pbformat_a6700_v1", "F29"))
UNIT, DESC, DSIZE, CLIP, NDESC = 0x393648, 0x3936E8, 0x90, 0x39156C, 689    # build_ogfile.OTHER_BUILDS["a6700_200"] (A6700_PORT_ENCODER.md)
# The pages the dump reads beyond the display pages (those come from the screen builder's lcd_regions file):
DUMP_FIXED = (("matrix", 0x10CD000, 2), ("sizetable", 0x199E000, 1), ("records", 0x25DA000, 4),
              ("kprint", 0xE0000, 32), ("bootlog", 0xC0000, 8),
              # the memory manager: its page of pointers (workspace 0x19d8058, unit objects 0x19d7bac), the unit records with the four sites
              # 0x2580cd8.., the parents' records 0x257e954.., and the id rows / key lists the 5.76K step changes (0x25b71d8, 0x25b92b0)
              ("dmmglobals", 0x19D7000, 2), ("dmmrecs", 0x2580000, 1), ("dmmparents", 0x257E000, 1), ("dmmids", 0x25B7000, 1), ("dmmkeys", 0x25B9000, 1),
              # the resize module's working structure 0x16a70e8 and settings 0x19b7388 (build/emu_rc_fit_a6700.py)
              ("resizework", 0x16A7000, 1), ("resizestate", 0x19B7000, 1))


def c_bytes(b):
    return "{" + ",".join(str(x) for x in b) + "}"


def design(n):
    d = json.loads((DES / f"{n}.json").read_text(encoding="utf8"))
    assert d.get("build") == "a6700_200", n
    return d


def spans(designs, av, lm):
    """The encoder side as spans: {binary: [(offset, stock, [bytes of design k or None])]}. A span is a maximal run of adjacent bytes that
    at least one design changes; a design's bytes for a span are the file's with that design's sites laid over it."""
    out = {}
    for binary, data in (("av-cam.bin", av), ("libmpr.so", lm)):
        changed = [dict() for _ in designs]                      # per design: {offset: new byte}
        for k, d in enumerate(designs):
            for p in d["patches"]:
                if p["binary"] != binary:
                    continue
                o, old, new = int(p["file_off"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])
                assert data[o:o + len(old)] == old
                for i, v in enumerate(new):
                    changed[k][o + i] = v
        offs = sorted(set().union(*[set(c) for c in changed]))
        runs = []
        for o in offs:
            if runs and o == runs[-1][1]:
                runs[-1][1] = o + 1
            else:
                runs.append([o, o + 1])
        rows = []
        for lo, hi in runs:
            stock = data[lo:hi]
            alts = []
            for c in changed:
                b = bytes(c.get(o, data[o]) for o in range(lo, hi))
                alts.append(b if b != stock else None)
            assert any(a is not None for a in alts)
            rows.append((lo, stock, alts))
        out[binary] = rows
    return out


def main():
    cp = (EX / "nflasha8/cpapp-b.bin").read_bytes()
    av = (EX / "nflasha3/av-cam.bin").read_bytes()
    lm = (EX / "nflasha15/lib/libmpr.so").read_bytes()
    og, og50, dm, oz, k16, sc = (design(n) for n in (SENSOR, SENSOR50, DMM, OUTSZ, K16, SCREEN))
    og32 = design(SENSOR32)
    alt32 = {int(p["addr"], 16): bytes.fromhex(p["new"]) for p in og32["patches"]}
    assert og32["artifact_sha256"] == hashlib.sha256(cp).hexdigest()
    mp = [design(n) for n, _ in MP_DESIGNS]
    pb = [design(n) for n, _ in PB_DESIGNS]
    sha_cp = hashlib.sha256(cp).hexdigest()
    assert og["artifact_sha256"] == og50["artifact_sha256"] == sha_cp
    want = {"libmpr.so": hashlib.sha256(lm).hexdigest(), "av-cam.bin": hashlib.sha256(av).hexdigest()}
    assert all(d["artifact_sha256"] == want for d in mp) and all(d["artifact_sha256"] == want["av-cam.bin"] for d in pb)
    out, blobs = [], []

    def blob(b):
        blobs.append(f"static const unsigned char B{len(blobs)}[] = {c_bytes(b)};")
        return f"B{len(blobs) - 1}"

    out.append(f'#define A6700_LABEL "{LABEL}"\n#define CP_LO {CP_LO:#x}U\n#define CP_HI {CP_HI:#x}U\n#define AVCAM_PHYS {AVCAM_PHYS:#x}UL\n'
               f'#define AVCAM_RESERVE "{AVCAM_RESERVE}"\n#define MP_ALTS {len(mp)}')
    out.append("struct id_file { const char *name; unsigned char sha256[32]; };\nstruct id_page { unsigned int address; unsigned char sha256[32]; };\n"
               "struct cp_site { const char *name; unsigned int address, length; const unsigned char *stock, *target, *alt; int soft; };\n"
               "struct pb_site { unsigned long offset; unsigned int length; const unsigned char *stock, *target; };\n"
               "struct av_guard { const char *name; unsigned long offset; unsigned int length; unsigned char sha256[32]; };\n"
               "struct dump_range { const char *name; unsigned int address, pages; };")
    rows = [f'    {{"{n}", {c_bytes(hashlib.sha256((EX / p).read_bytes()).digest())}}},' for n, p in ID_FILES.items()]
    out.append("static const struct id_file id_files[] = {\n" + "\n".join(rows) + "\n};")
    # ---- coprocessor sites
    sites = []
    for d, cell, rec in ((og, "cell", "record"), (og50, "cell50_", "record50")):
        n = 0
        for p in sorted(d["patches"], key=lambda p: int(p["addr"], 16)):
            a, old, new = int(p["addr"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])
            assert cp[a - BASE:a - BASE + len(old)] == old and len(old) == len(new)
            if p["kind"] == "R":
                name = rec + ("_left" if "left" in p["note"] else "_right")
            else:
                name, n = "%s%02d" % (cell, n), n + 1
            sites.append((name, a, old, new, 0))
    seen = {a for _, a, _, _, _ in sites}
    for k, p in enumerate(sorted((p for p in og32["patches"] if int(p["addr"], 16) not in seen), key=lambda p: int(p["addr"], 16))):
        a, old, new = int(p["addr"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])       # a cell only the 3:2 design changes: stock or its bytes
        assert cp[a - BASE:a - BASE + len(old)] == old and p["kind"] == "S"
        sites.append(("cell32_%02d" % k, a, old, new, 0))
    alts = {a: alt32[a] for _, a, _, _, _ in sites if a in alt32 and a in seen}
    assert len(alts) == len(og["patches"]), "the 3:2 design does not cover every place of the sensor design"
    for k, s in enumerate(dm["sites"]):                   # hard: the memory manager's RAM copy of DmmCfg.bin, filled at start-up
        sites.append((f"rawbuf_size{k}", int(s["ram_address"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"]), 0))
    ids = list(struct.unpack_from("<%dI" % NMODES, cp, IDS - BASE))
    for m, sr in og["stored_records"].items():            # soft: computed at start-up, run-time bytes; the PC reads the design offsets
        assert sr["index"] == ids.index(int(m, 16))
        sites.append((f"stored_record_{m}", RECS + sr["index"] * REC, bytes.fromhex(sr["ntsc"]["stock"]), bytes.fromhex(sr["ntsc"]["design"]), 1))
    s50 = og50["stored_record"]
    assert s50["index"] == ids.index(0x830)
    sites.append(("stored_record_0x830", RECS + s50["index"] * REC, bytes.fromhex(s50["stock"]), bytes.fromhex(s50["design"]), 1))
    for s in oz["sites"]:                                 # soft: the size table is zero until a movie mode has run
        sites.append(("outsize", int(s["ram_address"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"]), 1))
    for k, g in enumerate(oz["guards"]):
        sites.append((f"outsize_guard{k}", int(g["ram_address"], 16), bytes.fromhex(g["bytes"]), None, 1))
    for k, s in enumerate(k16["sites"]):                  # soft: RAM tables; one of them is the output-size word with another target
        sites.append((f"k16_word{k}", int(s["ram_address"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"]), 1))
    for k, s in enumerate(sc["sites"]):                   # soft: the screen step is optional (apply --no-screen); reported, not counted
        a, old = int(s["ram_address"], 16), bytes.fromhex(s["old"])
        if BASE <= a < BASE + len(cp):
            assert cp[a - BASE:a - BASE + 4] == old
        sites.append((f"screen{k}", a, old, bytes.fromhex(s["new"]), 1))
    pages = {x & ~0xFFF for _, a, o, _, _ in sites for x in (a, a + len(o) - 1) if a < BASE + len(cp)}
    assert not any(p in pages for p in ID_PAGES), "an identity page holds a design site"
    rows = [f"    {{{a:#x}, {c_bytes(hashlib.sha256(cp[a - BASE:a - BASE + 4096]).digest())}}}," for a in ID_PAGES]
    out.append("static const struct id_page id_pages[] = {\n" + "\n".join(rows) + "\n};")
    rows = []
    for name, a, old, new, soft in sites:
        assert CP_LO <= a and a + len(old) <= CP_HI and len(old) <= 3072
        held = (lambda b: hashlib.sha256(b).digest()) if len(old) > 16 else (lambda b: b)        # a long site: the digests of its bytes
        shared = name.startswith(("cell", "record_")) and not name.startswith(("cell50_", "cell32_"))       # a place of the sensor design L5 (names cellNN, record_left/right)
        alt = alts.get(a) if shared else None
        assert alt is None or (len(alt) == len(old) and alt != old)
        if alt is not None and alt == new:               # a place where both designs write the same bytes: TARGET says it for both
            alt = None
        rows.append(f'    {{"{name}", {a:#x}, {len(old)}, {blob(held(old))}, {blob(held(new)) if new is not None else "0"}, '
                    f'{blob(held(alt)) if alt is not None else "0"}, {soft}}},')
    out.append("static const struct cp_site cp_sites[] = {\n" + "\n".join(rows) + "\n};")
    # ---- main-processor spans
    sp = spans(mp, av, lm)
    per_design = [{"design": n, "step": st, "lm_spans": 0, "av_spans": 0} for n, st in MP_DESIGNS]
    for var, binary, key in (("lm_spans", "libmpr.so", "lm_spans"), ("av_spans", "av-cam.bin", "av_spans")):
        packed = bytearray()                                 # per span: offset (4, little-endian), length, designs mask, stock, each design's bytes
        for o, stock, alts in sp[binary]:
            mask = 0
            for k, a in enumerate(alts):
                per_design[k][key] += a is not None
                mask |= (a is not None) << k
            assert len(stock) <= 255 and o < 1 << 32 and len(alts) <= 8
            packed += struct.pack("<IBB", o, len(stock), mask) + stock + b"".join(a for a in alts if a is not None)
        out.append("#define %s %d\nstatic const unsigned char %s[] = %s;" % (var.upper(), len(sp[binary]), var, c_bytes(packed)))
    av_spans = [(o, len(s)) for o, s, _ in sp["av-cam.bin"]]
    free = lambda k: all(DESC + DSIZE * (k + 4) <= so or so + sn <= DESC + DSIZE * k for so, sn in av_spans)
    d0 = next(k for k in range(NDESC - 4) if free(k))
    guards = (("unit_rows_0_2", UNIT, 0x30), ("clip_rows_2_7", CLIP + 0x20, 0x60), (f"descriptors_{d0}_{d0 + 3}", DESC + DSIZE * d0, 4 * DSIZE))
    rows, av_hi = [], max(so + sn for so, sn in av_spans)
    for name, o, n in guards:
        assert all(o + n <= so or so + sn <= o for so, sn in av_spans), name
        rows.append(f'    {{"{name}", {o:#x}UL, {n}, {c_bytes(hashlib.sha256(av[o:o + n]).digest())}}},')
        av_hi = max(av_hi, o + n)
    out.append("static const struct av_guard av_guards[] = {\n" + "\n".join(rows) + "\n};")
    av_lo = min([so for so, _ in av_spans] + [o for _, o, _ in guards]) & ~0xFFF
    out.append(f"#define AV_LO {av_lo:#x}UL\n#define AV_HI {av_hi:#x}UL")
    # ---- the playback designs' words (one target each; alt[0])
    rows, pb_list = [], []
    for d, (name, step) in zip(pb, PB_DESIGNS):
        for s in d["code_sites"] + d["data_sites"]:
            o, old, new = int(s["file_off"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"])
            assert av[o:o + len(old)] == old and len(old) == len(new) == 4
            rows.append("    {%#xUL, 4, %s, %s}," % (o, blob(old), blob(new)))
            pb_list.append({"offset": hex(o), "design": name, "step": step, "stock": old.hex(), "new": new.hex()})
    out.append("static const struct pb_site pb_sites[] = {\n" + "\n".join(rows) + "\n};")
    # ---- the dump's pages: the fixed ranges, the register shadow's pages, the display pages
    matrix = []
    for k in range(MATRIX_ROWS):
        a = struct.unpack_from("<I", cp, MATRIX - BASE + MROW * k)[0]
        matrix.append([a, cp[MATRIX - BASE + MROW * k + 4:MATRIX - BASE + MROW * k + MROW].hex()])
    assert not any(cp[MATRIX - BASE + MROW * MATRIX_ROWS:MATRIX - BASE + MROW * (MATRIX_ROWS + 1)]) and MATRIX + MROW * (MATRIX_ROWS + 1) == COLMAP
    shadow_pages = sorted({a & ~0xFFF for a, _ in matrix})
    assert len(shadow_pages) <= 3 and all(CP_LO <= p < CP_HI for p in shadow_pages)
    lcd = json.loads((HERE / "lcd_regions_a6700.json").read_text(encoding="utf8"))["dump_decoder"]
    disp_pages = sorted(int(p, 16) for p in lcd["pages"])
    dump_ranges = list(DUMP_FIXED) + [(f"shadow{k}", p, 1) for k, p in enumerate(shadow_pages)] + [(f"display{k}", p, 1) for k, p in enumerate(disp_pages)]
    rows = [f'    {{"{n}", {a:#x}, {k}}},' for n, a, k in dump_ranges]
    assert all(CP_LO <= a and a + 4096 * k <= CP_HI for _, a, k in dump_ranges)
    starts = sorted((a, a + 4096 * k) for _, a, k in dump_ranges)
    assert all(e <= s for (_, e), (s, _) in zip(starts, starts[1:])), "two dump ranges overlap"
    out.append("#if DUMP\nstatic const struct dump_range dump_ranges[] = {\n" + "\n".join(rows) + "\n};\n#endif")
    text = ("/* Generated by gen_a6700.py from the A6700 2.00 files and the port designs. Do not edit. */\n#ifndef DUMP\n#define DUMP 0\n#endif\n"
            + "\n".join(blobs) + "\n" + "\n".join(out) + "\n")
    (HERE / "a6700_expected.h").write_text(text, encoding="utf8", newline="\n")
    names = [d["design"] for d in (og, og50, og32, dm, oz, k16, sc)] + [n for n, _ in MP_DESIGNS + PB_DESIGNS]
    facts = {"label": LABEL, "cp_lo": CP_LO, "cp_hi": CP_HI, "avcam_phys": AVCAM_PHYS, "avcam_reserve": AVCAM_RESERVE,
             "id_files": {n: hashlib.sha256((EX / p).read_bytes()).hexdigest() for n, p in ID_FILES.items()},
             "id_pages": {hex(a): hashlib.sha256(cp[a - BASE:a - BASE + 4096]).hexdigest() for a in ID_PAGES},
             "cp_sites": [{"name": n, "address": hex(a), "length": len(o), "soft": s} for n, a, o, _, s in sites],
             "lm_sites": len(sp["libmpr.so"]), "av_sites": len(sp["av-cam.bin"]), "mp_designs": per_design, "pb_sites": len(pb_list),
             "av_guards": [g[0] for g in guards], "dump_ranges": [[n, hex(a), k] for n, a, k in dump_ranges],
             "designs": {n: hashlib.sha256((DES / (n + ".json")).read_bytes()).hexdigest() for n in names}}
    (HERE / "a6700_expected.json").write_text(json.dumps(facts, indent=1) + "\n", encoding="utf8", newline="\n")
    # ---- what the PC needs to read a dump without the firmware files
    emu = {"ntsc": json.loads((ROOT / "evidence/a6700/sensor/drvparam_stock_a6700_200.json").read_text(encoding="utf8"))["modes"],
           "pal": json.loads((ROOT / "evidence/a6700/sensor/drvparam_stock_a6700_200_pal.json").read_text(encoding="utf8"))["modes"]}
    assert all(len(v) == NMODES and not any(r["error"] for r in v.values()) for v in emu.values())
    cells = []
    for d, step in ((og, "L5"), (og50, "Q5"), (og32, "T5")):
        for p in d["patches"]:
            a = int(p["addr"], 16)
            if MATRIX <= a < MATRIX + MROW * MATRIX_ROWS:
                row, col = divmod(a - MATRIX, MROW)
                assert col >= 4 and len(p["old"]) == 2
                cells.append({"row": row, "column": col - 4, "stock": int(p["old"], 16), "new": int(p["new"], 16), "step": step})
    assert {c["column"] for c in cells if c["step"] in ("L5", "T5")} == {1} and {c["column"] for c in cells if c["step"] == "Q5"} == {2}
    # where the stored record holds the window: found from the stock and design records of mode 0x8c0, not assumed
    st, dz = bytes.fromhex(og["stored_records"]["0x8c0"]["ntsc"]["stock"]), bytes.fromhex(og["stored_records"]["0x8c0"]["ntsc"]["design"])
    sw, srow = og["summary"]["stock_window"][1], og["summary"]["stock_window_row"]
    dw, drow = og["summary"]["window"][1], og["summary"]["window_row"]
    u = lambda b, o: struct.unpack_from("<H", b, o)[0]
    find = lambda a, b: [o for o in range(0, REC - 1, 2) if u(st, o) == a and u(dz, o) == b]
    off_h, off_row, off_pd = find(sw, dw), find(srow, drow), find(68, og["summary"]["pdaf"]["pdaf_rows"])
    assert len(off_h) >= 1 and len(off_row) >= 1 and len(off_pd) >= 1, (off_h, off_row, off_pd)
    sr_design = {m: {"index": v["index"], "offsets_that_differ": v["offsets_that_differ"], "ntsc": v["ntsc"], "pal": v["pal"]} for m, v in og["stored_records"].items()}
    ref = {"about": "A6700 2.00 reference data for reading an a6700read dump; from cpapp-b.bin, the designs and build/emu_drvparam.py a6700_200",
           "matrix_address": hex(MATRIX), "matrix_row_bytes": MROW, "matrix_columns": 14, "matrix": matrix,
           "column_map": list(struct.unpack_from("<%dI" % NMODES, cp, COLMAP - BASE)), "matrix_design_cells": cells,
           "mode_ids": [hex(x) for x in ids], "records_address": hex(RECS), "record_size": REC,
           "emulated_stock_records": {s: {m: v["record"] for m, v in e.items()} for s, e in emu.items()}, "size_table_address": hex(SIZE_TABLE),
           "stored_records_design": sr_design,
           "stored_records_design_32": {m: {"index": v["index"], "offsets_that_differ": v["offsets_that_differ"], "ntsc": v["ntsc"], "pal": v["pal"]}
                                        for m, v in og32["stored_records"].items()},
           "stored_record_50p": {"mode": "0x830", "index": s50["index"], "offsets_that_differ": s50["offsets_that_differ"],
                                 "pal": {"stock": s50["stock"], "design": s50["design"]},
                                 "ntsc": {"stock": og50["stored_record_ntsc"]["stock"], "design": og50["stored_record_ntsc"]["stock"]}},
           "window": {"stock_row": srow, "stock_height": sw, "design_row": drow, "design_height": dw,
                      "design_32": [og32["summary"]["window"][1], og32["summary"]["window_row"]],
                      "stock_50p": og50["summary"]["stock_window"], "design_50p": og50["summary"]["window"],
                      "record_offsets": {"height": hex(off_h[0]), "row": hex(off_row[0]), "pdaf_rows": hex(off_pd[0])}},
           "raw_write_buffer": [{"address": s["ram_address"], "stock": s["old"], "new": s["new"]} for s in dm["sites"]],
           "output_words": [{"address": s["ram_address"], "stock": s["old"], "new": s["new"]} for s in oz["sites"]],
           "k16_words": [{"address": s["ram_address"], "stock": s["old"], "new": s["new"], "note": s.get("note", "")} for s in k16["sites"]],
           "screen_words": [{"address": s["ram_address"], "stock": s["old"], "new": s["new"], "note": s.get("note", "")} for s in sc["sites"]],
           "screen_design": sc["design"],
           "panel_type": {"rear": lcd["panel_type_rear"], "second": lcd["panel_type_second"], "codes": lcd["panel_codes"]},
           "fit_words": {"on_4x3_panel": lcd["fit_words_169"][0], "on_3x2_panel": lcd["fit_words_169"][1]},
           # 3 rows x 4 aspect columns x (x, y, w, h): the 16:9 entry of row r is at table + 8 * (4 * r + 3)
           "frame_tables": [{"name": n, "address": a, "bytes": 0x60, "rect_offsets": [8 * (4 * r + 3) for r in range(3)]} for n, a in lcd["frame_tables"].items()],
           "playback_words": pb_list,
           "ram": {"resize_work": "0x16a70e8", "resize_settings": "0x19b7388", "dmm_workspace_pointer": "0x19d8058", "dmm_units_pointer": "0x19d7bac",
                   "shadow_pages": [hex(p) for p in shadow_pages]}}
    (HERE / "a6700_reference.json").write_text(json.dumps(ref) + "\n", encoding="utf8", newline="\n")
    print(f"a6700_expected.h: {len(sites)} coprocessor sites ({sum(1 for s in sites if not s[4])} counted), {len(sp['libmpr.so'])} libmpr.so spans, "
          f"{len(sp['av-cam.bin'])} av-cam.bin spans, {len(pb_list)} playback words, {len(dump_ranges)} dump ranges ({sum(k for _, _, k in dump_ranges)} pages), "
          f"{len(text)} bytes of header")
    print("record offsets: height %s, row %s, phase-detect rows %s; designs' spans: %s"
          % (hex(off_h[0]), hex(off_row[0]), hex(off_pd[0]), ", ".join("%s %d+%d" % (d["step"], d["lm_spans"], d["av_spans"]) for d in per_design)))


if __name__ == "__main__":
    main()
