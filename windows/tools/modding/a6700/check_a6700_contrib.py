"""Check the contributed A6700 2.00 open-gate kit against the 2.00 update's own files (A6700 port, 2026-11-26). Reads only.

  work\\venv\\Scripts\\python.exe -I -B build\\check_a6700_contrib.py [--json evidence\\a6700\\contrib_check.json]

The kit is a contributor's port of ours (work/contrib/a6700_v1.0, unpacked from A6700_OpenGate.zip; untrusted data: nothing of
it is imported or run here, its files are only parsed). This answers four questions, each with counts:

  1. files     the four firmware files its designs name by SHA-256 are the ones of our extraction of the 2.00 update
  2. sites     every site and guard of every design holds, in those files, the "old" bytes the design states
               (a site outside the files, i.e. a table the coprocessor builds in RAM, is listed as RAM-ONLY: not checkable here)
  3. headers   the C headers its helper is compiled from (src/gen/*.h) carry exactly the designs' sites
               (differences are listed: e.g. the screen design's guards, which its generator drops)
  4. kit       the 16 libraries are the ones its manifest pins (SHA-256, size)

Exit status 0 when 1, 2 and 4 hold without exception; the header differences of 3 are findings, printed, not failures.
"""
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "work/extracted/a6700_200/0700_part_image/dev"
KIT = ROOT / "work/contrib/a6700_v1.0/A6700 OpenGate/a6700-opengate_v1.0"
DES, GEN, OGK = KIT / "designs", KIT / "src/gen", KIT / "build/og_kit"
BASE = 0x108000
FILES = {"cpapp-b.bin": EX / "nflasha8/cpapp-b.bin", "DmmCfg.bin": EX / "nflasha8/DmmCfg.bin",
         "av-cam.bin": EX / "nflasha3/av-cam.bin", "libmpr.so": EX / "nflasha15/lib/libmpr.so"}


def load():
    return {k: p.read_bytes() for k, p in FILES.items()}


def design(name):
    return json.loads((DES / name).read_text(encoding="utf8"))


def c_arrays(text):
    """{array name: rows}: for an array of structs, one flat list of numbers per element; for a plain array, the numbers."""
    out = {}
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for m in re.finditer(r"static const [\w\s\*]+?\b(\w+)\s*\[[^\]]*\]\s*=\s*\{", text):
        depth, i, start = 1, m.end(), m.end()
        rows, row_start = [], None
        while depth:
            ch = text[i]
            if ch == "{":
                depth += 1
                if depth == 2:
                    row_start = i
            elif ch == "}":
                depth -= 1
                if depth == 1 and row_start is not None:
                    rows.append([int(x.rstrip("UL"), 0) for x in re.findall(r"0x[0-9a-fA-F]+U?L?|\b\d+U?L?\b", text[row_start:i])])
                    row_start = None
            i += 1
        body = text[start:i - 1]
        if not rows and "{" not in body:
            rows = [int(x.rstrip("UL"), 0) for x in re.findall(r"0x[0-9a-fA-F]+U?L?|\b\d+U?L?\b", body)]
        out[m.group(1)] = rows
    return out


class Report:
    def __init__(self):
        self.rows, self.bad, self.findings = [], 0, []

    def add(self, section, what, ok, detail=""):
        self.rows.append({"section": section, "what": what, "ok": bool(ok), "detail": detail})
        self.bad += 0 if ok else 1
        print("%-4s %-8s %s%s" % ("ok" if ok else "FAIL", section, what, ("  " + detail) if detail else ""))

    def finding(self, text):
        self.findings.append(text)
        print("NOTE          " + text)


def check_files(f, r):
    sha = {k: hashlib.sha256(v).hexdigest() for k, v in f.items()}
    named = {}
    for p in sorted(DES.glob("*.json")):
        d = design(p.name)
        a = d.get("artifact_sha256")
        if isinstance(a, dict):
            for k, v in a.items():
                named.setdefault(k, set()).add(v)
        elif isinstance(a, str):
            named.setdefault("av-cam.bin" if d.get("artifact") == "av-cam.bin" else "cpapp-b.bin", set()).add(a)
        if "dmmcfg_sha256" in d:
            named.setdefault("DmmCfg.bin", set()).add(d["dmmcfg_sha256"])
        if "cpapp_sha256" in d:
            named.setdefault("cpapp-b.bin", set()).add(d["cpapp_sha256"])
    for k in FILES:
        r.add("files", "%s: SHA-256 %s..., %d bytes" % (k, sha[k][:16], len(f[k])), named.get(k) == {sha[k]},
              "" if named.get(k) == {sha[k]} else "designs name %s" % sorted(named.get(k, [])))
    return sha


def in_image(f, addr, n):
    return BASE <= addr and addr + n <= BASE + len(f["cpapp-b.bin"])


def cp_bytes(f, addr, n):
    return f["cpapp-b.bin"][addr - BASE:addr - BASE + n]


def check_sites(f, r):
    """Every 'old' byte and every guard byte of every design against the files. Returns the per-design site lists for the header check."""
    D = {}
    # --- the raw write buffer (memory manager): the file's records and the RAM address of each
    d = design("dmmwb_a6700_v1.json")
    cfg = f["DmmCfg.bin"]
    ok = bad = 0
    for s, g in zip(d["sites"], d["unit_record_guards"]):
        off = int(s["file_offset_of_the_same_field"], 16)
        good = cfg[off:off + 4] == bytes.fromhex(s["old"]) and s["old_value"] == struct.unpack("<I", bytes.fromhex(s["old"]))[0] and s["new_value"] == struct.unpack("<I", bytes.fromhex(s["new"]))[0]
        # the record the word lies in: the file's 20 bytes, and the word at site_off inside it
        good &= cfg[off - g["site_off"]:off - g["site_off"] + 20] == bytes.fromhex(g["file_hex"]) and int(s["ram_address"], 16) - int(g["ram_address"], 16) == g["site_off"]
        ok, bad = ok + good, bad + (not good)
    r.add("sites", "dmmwb_a6700_v1: %d size words and the unit records around them hold the stated bytes in DmmCfg.bin" % ok, not bad and ok == 4 == len(d["unit_record_guards"]))
    ok = sum(cfg.count(bytes.fromhex(g["file_hex"])) >= 1 and struct.unpack_from("<I", bytes.fromhex(g["file_hex"]), 8)[0] == int(g["key"], 16)
             and struct.unpack_from("<I", bytes.fromhex(g["file_hex"]), 12)[0] == g["size"] for g in d["parent_guards"])
    r.add("sites", "dmmwb_a6700_v1: %d of %d parent records are records of the file with the stated key and size" % (ok, len(d["parent_guards"])), ok == len(d["parent_guards"]))
    # the RAM address of each record: our own reader of the file (build/parse_dmmcfg.py), once it knows this build's RAM copy
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import parse_dmmcfg
    if "a6700_200" in parse_dmmcfg.RAM:
        c = parse_dmmcfg.Config(parse_dmmcfg.find_file("a6700_200"), "a6700_200")
        by_ram = {c.ram("unit_records", u["seq"] * 0x14): u for g in c.groups for u in g["units"]}
        ok = sum(int(g["ram_address"], 16) in by_ram and c.data[by_ram[int(g["ram_address"], 16)]["at"]:by_ram[int(g["ram_address"], 16)]["at"] + 20] == bytes.fromhex(g["file_hex"])
                 for g in d["unit_record_guards"] + d["parent_guards"])
        r.add("sites", "dmmwb_a6700_v1: %d of %d records (units and parents) sit at the RAM address parse_dmmcfg.py gives for the same record of the file"
              % (ok, len(d["unit_record_guards"]) + len(d["parent_guards"])), ok == len(d["unit_record_guards"]) + len(d["parent_guards"]))
    else:
        r.finding("dmmwb_a6700_v1: the RAM addresses of its records are not checked here yet (build/parse_dmmcfg.py has no RAM copy for a6700_200)")
    D["dmmwb"] = d
    # --- the sensor side
    d = design("ogsq_a6700_v1.json")
    in_file = [p for p in d["patches"] if in_image(f, int(p["addr"], 16), len(p["old"]) // 2)]
    ok = sum(cp_bytes(f, int(p["addr"], 16), len(p["old"]) // 2) == bytes.fromhex(p["old"]) and len(p["old"]) == len(p["new"]) and p["old"] != p["new"] for p in in_file)
    r.add("sites", "ogsq_a6700_v1: %d of %d patches lie in cpapp-b.bin and hold the stated old bytes (%d bytes)"
          % (ok, len(d["patches"]), sum(len(p["old"]) // 2 for p in d["patches"])), ok == len(d["patches"]) == d["summary"]["sites"])
    spans = sorted((int(p["addr"], 16), len(p["old"]) // 2) for p in d["patches"])
    r.add("sites", "ogsq_a6700_v1: no two patches overlap", all(a + n <= b for (a, n), (b, _) in zip(spans, spans[1:])))
    recs = d["stored_records"]
    n = d["record_size"]
    good = True
    for k, sr in recs.items():
        st, nw = bytes.fromhex(sr["stock"]), bytes.fromhex(sr["design"])
        offs = [int(x, 16) for x in sr["offsets_that_differ"]]
        good &= len(st) == len(nw) == n and offs == [i for i in range(n) if st[i] != nw[i]]
        good &= bytes(st[i] for i in offs).hex() == sr["stock_diff_bytes"] and bytes(nw[i] for i in offs).hex() == sr["design_diff_bytes"]
        good &= int(sr["address"], 16) == int(d["records_base"], 16) + sr["mode_index"] * n
        good &= struct.unpack_from("<I", st, 0x24)[0] == int(sr["mode_id"], 16)
    r.add("sites", "ogsq_a6700_v1: the %d stored records are self-consistent (offsets, bytes, address = base + index * %#x, mode id at +0x24); RAM-ONLY: computed at start-up, checked by emu_drvparam.py"
          % (len(recs), n), good)
    D["ogsq"] = d
    # --- words designs
    for name in ("outsz2560_a6700_v1", "og57cp_a6700_v1", "og4k50cp_a6700_v1", "lcdfill_a6700_v2"):
        d = design(name + ".json")
        fs = [(int(s["ram_address"], 16), bytes.fromhex(s["old"])) for s in d["sites"]]
        gs = [(int(g["ram_address"], 16), bytes.fromhex(g["bytes"])) for g in d["guards"]]
        fin = [(a, b) for a, b in fs + gs if in_image(f, a, len(b))]
        ok = sum(cp_bytes(f, a, len(b)) == b for a, b in fin)
        r.add("sites", "%s: %d site(s) + %d guard(s); %d lie in cpapp-b.bin and %d of them hold the stated bytes; %d are RAM-ONLY"
              % (name, len(fs), len(gs), len(fin), ok, len(fs) + len(gs) - len(fin)), ok == len(fin),
              "in file: " + ", ".join(hex(a) for a, _ in fin) if fin else "")
        r.add("sites", "%s: every site is a 4-byte word at a 4-aligned address, old != new, no guard overlaps a site" % name,
              all(len(b) == 4 and a % 4 == 0 for a, b in fs) and all(s["old"] != s["new"] for s in d["sites"])
              and not any(a < sa + 4 and sa < a + len(b) for a, b in gs for sa, _ in fs))
        D[name] = d
    # --- encoder side
    for name in ("ogfile2560_hs_s_pal50_a6700_v1", "ogfile57r260_a6700_v1"):
        d = design(name + ".json")
        cnt = {"av-cam.bin": [0, 0, 0], "libmpr.so": [0, 0, 0]}
        for s in d["sites"]:
            data, off, old = f[s["binary"]], int(s["file_off"], 16), bytes.fromhex(s["old"])
            c = cnt[s["binary"]]
            c[0] += 1
            c[1] += data[off:off + len(old)] == old and len(s["old"]) == len(s["new"]) and s["old"] != s["new"] and len(old) <= 16
            c[2] += len(old)
        for b, c in cnt.items():
            r.add("sites", "%s: %d of %d %s sites hold the stated old bytes (%d bytes)" % (name, c[1], c[0], b, c[2]),
                  c[0] == c[1] == d["summary"][b]["sites"] and c[2] == d["summary"][b]["bytes"])
        ok = sum(f["libmpr.so"][int(g["file_off"], 16):int(g["file_off"], 16) + len(g["bytes"]) // 2] == bytes.fromhex(g["bytes"]) for g in d["libmpr_guards"])
        r.add("sites", "%s: %d of %d libmpr.so instruction guards equal the file" % (name, ok, len(d["libmpr_guards"])), ok == len(d["libmpr_guards"]))
        for b in cnt:
            sp = sorted((int(s["file_off"], 16), len(s["old"]) // 2) for s in d["sites"] if s["binary"] == b)
            r.add("sites", "%s: no two %s sites overlap" % (name, b), all(a + n <= c for (a, n), (c, _) in zip(sp, sp[1:])))
        code = [s for s in d["sites"] if s.get("code")]
        r.add("sites", "%s: %d code site(s), all in libmpr.so" % (name, len(code)), all(s["binary"] == "libmpr.so" for s in code) and len(code) == d["summary"]["libmpr.so"]["code_sites"])
        D[name] = d
    # --- playback
    d = design("avdec8k_a6700_v1.json")
    av = f["av-cam.bin"]
    ok = sum(av[int(s["file_off"], 16):int(s["file_off"], 16) + 4] == bytes.fromhex(s["old"]) for s in d["code_sites"])
    r.add("sites", "avdec8k (file _v1, design name %s): %d of %d code words hold the stated old bytes in av-cam.bin" % (d["design"], ok, len(d["code_sites"])), ok == len(d["code_sites"]))
    ok = sum(av[int(s["file_off"], 16):int(s["file_off"], 16) + len(s["old"]) // 2] == bytes.fromhex(s["old"]) for s in d["data_sites"])
    okg = sum(av[int(g["file_off"], 16):int(g["file_off"], 16) + len(g["bytes"]) // 2] == bytes.fromhex(g["bytes"]) for g in d["data_guards"])
    r.add("sites", "avdec8k: %d of %d data word(s) and %d of %d data guards equal av-cam.bin" % (ok, len(d["data_sites"]), okg, len(d["data_guards"])),
          ok == len(d["data_sites"]) and okg == len(d["data_guards"]))
    pages = [int(p, 16) for p in d["code_pages"]]
    r.add("sites", "avdec8k: every code word lies in the code page its page_idx names (%s)" % ", ".join(hex(p) for p in pages),
          all(pages[s["page_idx"]] <= int(s["file_off"], 16) < pages[s["page_idx"]] + 4096 and int(s["kernel_address"], 16) == int(d["kernel_va_base"], 16) + int(s["file_off"], 16)
              for s in d["code_sites"]))
    D["avdec"] = d
    return D


def check_headers(f, D, r):
    H = {p.name: c_arrays(p.read_text(encoding="utf8")) for p in sorted(GEN.glob("*.h"))}
    pad = lambda b, n: list(b.ljust(n, b"\0"))

    def same(section, got, want):
        got, want = sorted(map(tuple, got)), sorted(map(tuple, want))
        r.add("headers", "%s: %d row(s) in the header, %d in the design" % (section, len(got), len(want)), got == want)
        return got == want

    # words designs
    for hname, dname in (("a6700_outsz_sites.h", "outsz2560_a6700_v1"), ("a6700_og57cp_sites.h", "og57cp_a6700_v1"),
                         ("a6700_og4k50cp_sites.h", "og4k50cp_a6700_v1"), ("a6700_lcdfill_sites.h", "lcdfill_a6700_v2")):
        h, d = H[hname], D[dname]
        same("%s words" % dname, h["rw_words"], [[int(s["ram_address"], 16)] + list(bytes.fromhex(s["old"])) + list(bytes.fromhex(s["new"])) for s in d["sites"]])
        hg = [g for g in h["rw_guards"] if g[1]]                                   # a zero-length row is a placeholder
        dg = [[int(g["ram_address"], 16), len(g["bytes"]) // 2] + pad(bytes.fromhex(g["bytes"]), 8) for g in d["guards"] if len(g["bytes"]) // 2 <= 8]
        long_ = [g for g in d["guards"] if len(g["bytes"]) // 2 > 8]
        if sorted(map(tuple, hg)) != sorted(map(tuple, dg)) or long_:
            r.finding("%s: the design lists %d guard(s), the compiled header carries %d (%s)"
                      % (dname, len(d["guards"]), len(hg), "its helper checks no guard for this step" if not hg else "guards longer than 8 bytes cannot be carried"))
        else:
            r.add("headers", "%s guards: %d" % (dname, len(hg)), True)
    # the raw write buffer
    h, d = H["a6700_dmmwb_sites.h"], D["dmmwb"]
    same("dmmwb sites", h["dmm_sites"], [[int(s["ram_address"], 16)] + list(bytes.fromhex(s["old"])) + list(bytes.fromhex(s["new"])) for s in d["sites"]])
    same("dmmwb unit records", h["dmm_recs"], [[int(g["ram_address"], 16), g["site_off"]] + list(bytes.fromhex(g["file_hex"])) for g in d["unit_record_guards"]])
    same("dmmwb parent records", [[x[0]] + x[2:] for x in h["dmm_parents"]], [[int(g["ram_address"], 16)] + list(bytes.fromhex(g["file_hex"])) for g in d["parent_guards"]])
    same("dmmwb busy keys", [h["dmm_busy_keys"]], [[int(k, 16) for k in d["dmm_ram"]["busy_keys"]]])
    # the sensor side
    h, d = H["a6700_ogsq_sites.h"], D["ogsq"]
    small = [p for p in d["patches"] if len(p["old"]) // 2 <= 4]
    big = [p for p in d["patches"] if len(p["old"]) // 2 > 4]
    same("ogsq cells (both tables)", h["ogsq_small"] + h["ogsq_small_pal2"],
         [[int(p["addr"], 16), len(p["old"]) // 2] + pad(bytes.fromhex(p["old"]), 4) + pad(bytes.fromhex(p["new"]), 4) for p in small])
    hrec = {}
    for addrs, tag in (("ogsq_rec_addr", "ogsq_rec"), ("ogsq_rec2_addr", "ogsq_rec2")):
        for k, a in enumerate(h[addrs]):
            hrec[a] = (bytes(h["%s_old_%d" % (tag, k)]), bytes(h["%s_new_%d" % (tag, k)]))
    r.add("headers", "ogsq records: %d in the header, %d in the design, all bytes equal" % (len(hrec), len(big)),
          hrec == {int(p["addr"], 16): (bytes.fromhex(p["old"]), bytes.fromhex(p["new"])) for p in big})
    sr = d["stored_records"]
    offs = lambda k: [int(x, 16) for x in sr[k]["offsets_that_differ"]]
    good = (h["ogsq_drv_offs"] == offs("pal_25p") == offs("pal_50p") == offs("pal_08c0") == offs("ntsc_24p")
            and bytes(h["ogsq_drv_pal_old"]).hex() == sr["pal_25p"]["stock_diff_bytes"] == sr["pal_50p"]["stock_diff_bytes"] == sr["pal_08c0"]["stock_diff_bytes"]
            and bytes(h["ogsq_drv_pal_new"]).hex() == sr["pal_25p"]["design_diff_bytes"] == sr["pal_50p"]["design_diff_bytes"] == sr["pal_08c0"]["design_diff_bytes"]
            and bytes(h["ogsq_drv_ntsc_old"]).hex() == sr["ntsc_24p"]["stock_diff_bytes"] and bytes(h["ogsq_drv_ntsc_new"]).hex() == sr["ntsc_24p"]["design_diff_bytes"]
            and h["ogsq_drv0830_offs"] == offs("pal_50p_0830") and bytes(h["ogsq_drv0830_old"]).hex() == sr["pal_50p_0830"]["stock_diff_bytes"]
            and bytes(h["ogsq_drv0830_new"]).hex() == sr["pal_50p_0830"]["design_diff_bytes"])
    r.add("headers", "ogsq stored-record bytes: PAL (one set for 0x820, 0x880, 0x8c0), NTSC (0x8c0), 0x830", good)
    r.finding("ogsq: on NTSC the helper writes the stored record of mode 0x8c0 only (ogsq_ntsc_ids = %s), on PAL those of %s and 0x830; the cells it writes are shared by 0x820, 0x880 and 0x8c0 in both systems"
              % (", ".join(hex(x) for x in h["ogsq_ntsc_ids"]), ", ".join(hex(x) for x in h["ogsq_pal_ids"])))
    # the encoder side
    for hname, dname in (("a6700_enc_sites.h", "ogfile2560_hs_s_pal50_a6700_v1"), ("a6700_enc57_sites.h", "ogfile57r260_a6700_v1")):
        h, d = H[hname], D[dname]
        for arr, b in (("mp_av", "av-cam.bin"), ("mp_lm", "libmpr.so")):
            same("%s %s" % (dname, b), h[arr], [[int(s["file_off"], 16), len(s["old"]) // 2] + pad(bytes.fromhex(s["old"]), 16) + pad(bytes.fromhex(s["new"]), 16)
                                                 for s in d["sites"] if s["binary"] == b])
        same("%s libmpr.so guards" % dname, h["mp_lm_guards"], [[int(g["file_off"], 16), len(g["bytes"]) // 2] + pad(bytes.fromhex(g["bytes"]), 4) for g in d["libmpr_guards"]])
    # playback
    h, d = H["a6700_avdec8k_sites.h"], D["avdec"]
    same("avdec8k code words", h["ad_code"], [[int(s["file_off"], 16), 4, 1, s["page_idx"]] + pad(bytes.fromhex(s["old"]), 16) + pad(bytes.fromhex(s["new"]), 16) for s in d["code_sites"]])
    same("avdec8k data word and guards", h["ad_data"],
         [[int(s["file_off"], 16), len(s["old"]) // 2, 1, 0] + pad(bytes.fromhex(s["old"]), 16) + pad(bytes.fromhex(s["new"]), 16) for s in d["data_sites"]]
         + [[int(g["file_off"], 16), len(g["bytes"]) // 2, 0, 0] + pad(bytes.fromhex(g["bytes"]), 16) + [0] * 16 for g in d["data_guards"]])
    av = f["av-cam.bin"]
    pages = h["ad_code_pages"]
    r.add("headers", "avdec8k: the %d code pages carried in the header (%s) equal av-cam.bin, 4,096 bytes each" % (len(pages), ", ".join(hex(p) for p in pages)),
          all(bytes(h["ad_code_file_%d" % k]) == av[p:p + 4096] for k, p in enumerate(pages)) and pages == [int(p, 16) for p in d["code_pages"]])


def check_kit(r):
    man = json.loads((OGK / "og_manifest.json").read_text(encoding="utf8"))
    ok = 0
    for k, m in man["modules"].items():
        b = (OGK / m["file"]).read_bytes()
        ok += hashlib.sha256(b).hexdigest() == m["sha256"] and len(b) == m["size"] and b[:4] == b"\x7fELF" and b[18:20] == b"\xb7\x00"
    r.add("kit", "%d of %d libraries are the manifest's (SHA-256, size, AArch64 ELF)" % (ok, len(man["modules"])), ok == len(man["modules"]) == 16)
    extra = sorted(p.name for p in OGK.glob("*.so") if p.name not in {m["file"] for m in man["modules"].values()})
    if extra:
        r.finding("kit: %s is in the folder but not in the manifest (not hash-pinned)" % ", ".join(extra))
    return {k: m["sha256"] for k, m in man["modules"].items()} | {p: hashlib.sha256((OGK / p).read_bytes()).hexdigest() for p in extra}


def main():
    r = Report()
    f = load()
    sha = check_files(f, r)
    D = check_sites(f, r)
    check_headers(f, D, r)
    libs = check_kit(r)
    fails = [x for x in r.rows if not x["ok"]]
    hard = [x for x in fails if x["section"] != "headers"]
    print("\n%d checks, %d failed (%d outside the header comparison), %d notes" % (len(r.rows), len(fails), len(hard), len(r.findings)))
    if "--json" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--json") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"build": "a6700_200", "files": sha, "contributed_libraries": libs, "checks": r.rows, "notes": r.findings}, indent=1) + "\n",
                       encoding="utf8", newline="\n")
        print("wrote", out)
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
