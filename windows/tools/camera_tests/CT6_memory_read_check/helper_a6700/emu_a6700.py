"""Run the built A6700 read-only helper in Unicorn against a model camera. Offline; no camera. (A6700 port, 2026-11-26)

  C:/Python313/python.exe -B emu_a6700.py [--show]

helper_fx30/emu_fx30.py with this camera's model (same harness: helper/emu_built.py; the same coprocessor model: only a transfer of one
whole page, direction 0, into the allocated buffer is accepted). Cases, for both libraries (check and dump):
  stock        an A6700 with the 2.00 files and stock memory (NTSC stored records)   -> every check same, verdict READY
  stock-pal    the same with the stored records a PAL camera computes                 -> READY (the records are soft sites)
  applied      the 4K open-gate state: L13, L5, L16, L19, S16                         -> its sites TARGET / its spans L19's, READY
  no-screen    the same without the screen step                                       -> screen words STOCK, READY
  no-meta      the encoder side without the MP4 header sites (N19)                    -> L19's spans but the two heights STOCK, READY
  si           the 4K state with the S-I step (I19)                                   -> L19's and I19's spans, READY
  3x2          the exact 3:2 test state: L13, T5, L16, L19, S16                       -> the sensor sites TARGET32 (one cell TARGET), READY
  pal50        a PAL camera with apply50: L13, L5, Q5, L16, M19, S16                   -> Q5's sites TARGET, the spans M19's, READY
  5.76K        apply57: L13, L5, K16, K19, S16                                        -> the spans K19's, READY
  playback     the 4K state with P29, A29, F29, R19                                   -> the eight playback words TARGET, READY
  broken       one byte of an encoder span holding neither stock nor a design's byte   -> OTHER, verdict NOT READY
  fx30 / zve1 / a7iv   another body's files and coprocessor image                      -> identity DIFFERS, verdict NOT READY
  no-reserve   a command line without the av-cam reservation                          -> av-cam.bin not read, NOT READY
  exists       a result file already present                                          -> nothing done
and the other way round, the published check libraries of the FX30, FX3, FX2 and ZV-E1 kits run on a stock A6700: each must say NOT READY
(an A6700 owner might run one of those kits; their apply scripts start only after a READY check).
"""
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "helper"))
import emu_built as E  # noqa: E402
from unicorn import arm64_const as R  # noqa: E402

BASE = 0x108000
FACTS = json.loads((HERE / "a6700_expected.json").read_text(encoding="utf8"))
DES = ROOT / "modding/designs"
CP_RANGE = (0xC0000, 0x2700000)                 # the widest of the kits' read ranges: a foreign helper is modelled too
RECS, REC = 0x25DABCC, 0x170
BITS = {d["step"]: 1 << k for k, d in enumerate(FACTS["mp_designs"])}
ENC = {"L19": "ogfile2560_hs_s_a6700_v2", "N19": "ogfile2560_hs_s_a6700_v1", "I19": "ogfilesi2560_a6700_v1", "M19": "ogfile2560_full_a6700_v1",
       "K19": "ogfile57r260_a6700_v1", "R19": "pbmpr_a6700_v1"}
PB = {"P29": "avdec8k_a6700_v1", "A29": "pbaspect_a6700_v1", "F29": "pbformat_a6700_v1"}


def ex(build, rel):
    return (ROOT / "work/extracted" / build / "0700_part_image/dev" / rel).read_bytes()


def design(name):
    return json.loads((DES / f"{name}.json").read_text(encoding="utf8"))


class Run(E.Run):
    """E.Run with this helper's coprocessor model: cp_image (bytes at 0x108000) and cp_ram {address: bytes} over zeros."""

    def on_import(self, uc, address, size, _):
        x = lambda n: uc.reg_read(getattr(R, "UC_ARM64_REG_X%d" % n))
        name, ret = self.imports.get(address), 0
        if name == "_Z9dmm_allocjPj":
            self.lib_calls.append(("alloc", x(0) & 0xFFFFFFFF))
            uc.mem_write(x(1), struct.pack("<I", E.BUF_HANDLE))
            ret = self.buf
        elif name == "_Z8dmm_freej":
            self.lib_calls.append(("free", x(0) & 0xFFFFFFFF))
        elif name == "sen_dma_transfer":
            direction, src, dst, n = x(0) & 0xFFFFFFFF, x(1), x(2), x(3) & 0xFFFFFFFF
            self.lib_calls.append(("transfer", direction, src, dst, n))
            if direction != 0 or dst != self.buf or n != 4096 or src & 0xFFF or not CP_RANGE[0] <= src < CP_RANGE[1]:
                self.bad = "a transfer that is not a read of one whole page in range: dir %d src %#x dst %#x size %d" % (direction, src, dst, n)
                uc.emu_stop()
                return
            page = bytearray(4096)
            img = self.cp["image"]
            if BASE <= src < BASE + len(img):
                chunk = img[src - BASE:src - BASE + 4096]
                page[:len(chunk)] = chunk
            for a, blob in self.cp["ram"].items():
                lo, hi = max(a, src), min(a + len(blob), src + 4096)
                if lo < hi:
                    page[lo - src:hi - src] = blob[lo - a:hi - a]
            va = next(v for v, off in self.map_phys.items() if v in self.maps and off <= self.buf < off + self.maps[v]) + self.buf % 4096
            uc.mem_write(va, bytes(page))
        else:
            self.bad = "call of an unexpected import %r" % name
            uc.emu_stop()
            return
        uc.reg_write(R.UC_ARM64_REG_X0, ret)
        uc.reg_write(R.UC_ARM64_REG_PC, uc.reg_read(R.UC_ARM64_REG_X30))

    def go(self):
        self.uc.reg_write(R.UC_ARM64_REG_SP, E.STACK - 0x1000)
        self.uc.reg_write(R.UC_ARM64_REG_X30, E.RET)
        self.uc.emu_start(self.ctor, E.RET, count=6_000_000_000)
        if not self.bad and self.uc.reg_read(R.UC_ARM64_REG_PC) != E.RET:
            self.bad = "the constructor did not return (pc %#x)" % self.uc.reg_read(R.UC_ARM64_REG_PC)
        return self


def model(build="a6700_200", steps=(), reserve=True, exists=False, system="ntsc", flip=None):
    """A model camera. steps: the write steps whose target bytes it holds (e.g. ("L13", "L5", "L16", "L19", "S16"))."""
    cp = bytearray(ex(build, "nflasha8/cpapp-b.bin"))
    av = bytearray(ex(build, "nflasha3/av-cam.bin"))
    libs = {n: ex(build, "nflasha15/lib" + n) for n in ("/libmpr.so", "/libsencore.so", "/libJiritsu.so")}
    lm = bytearray(libs["/libmpr.so"])
    og, og50, dm, oz, k16, sc = (design(n) for n in ("ogsq_a6700_v1", "ogsq50_a6700_v1", "dmmwb_a6700_v1", "outsz2560_a6700_v1", "og57cp_a6700_v1", "lcdfill_a6700_v2"))
    og32 = design("ogsq32_a6700_v1")
    ram = {}
    if build == "a6700_200":                      # the A6700's RAM tables; a foreign body keeps its own image and zeros
        for m, sr in og["stored_records"].items():
            ram[RECS + sr["index"] * REC] = bytes.fromhex(sr[system]["design" if "L5" in steps else "stock"])
            if "T5" in steps:
                ram[RECS + sr["index"] * REC] = bytes.fromhex(og32["stored_records"][m][system]["design"])
        s50 = og50["stored_record"]
        if system == "pal":
            ram[RECS + s50["index"] * REC] = bytes.fromhex(s50["design" if "Q5" in steps else "stock"])
        else:
            ram[RECS + s50["index"] * REC] = bytes.fromhex(og50["stored_record_ntsc"]["stock"])
        for d in (oz, k16):                        # the size table and the memory manager's id rows, as the set-ups leave them
            for g in d["guards"]:
                ram[int(g["ram_address"], 16)] = bytes.fromhex(g["bytes"])
            for s in d["sites"]:
                ram[int(s["ram_address"], 16)] = bytes.fromhex(s["old"])
        if "L16" in steps:
            for s in oz["sites"]:
                ram[int(s["ram_address"], 16)] = bytes.fromhex(s["new"])
        if "K16" in steps:
            for s in k16["sites"]:
                ram[int(s["ram_address"], 16)] = bytes.fromhex(s["new"])
        for s in dm["sites"]:
            ram[int(s["ram_address"], 16)] = bytes.fromhex(s["new" if "L13" in steps else "old"])
    for step, d in (("L5", og), ("Q5", og50), ("T5", og32)):
        if step in steps:
            for p in d["patches"]:
                a, new = int(p["addr"], 16), bytes.fromhex(p["new"])
                cp[a - BASE:a - BASE + len(new)] = new
    if "S16" in steps:
        for s in sc["sites"]:
            a = int(s["ram_address"], 16)
            cp[a - BASE:a - BASE + 4] = bytes.fromhex(s["new"])
    for step, name in ENC.items():
        if step in steps:
            for p in design(name)["patches"]:
                o, new = int(p["file_off"], 16), bytes.fromhex(p["new"])
                (lm if p["binary"] == "libmpr.so" else av)[o:o + len(new)] = new
    for step, name in PB.items():
        if step in steps:
            d = design(name)
            for s in d["code_sites"] + d["data_sites"]:
                o, new = int(s["file_off"], 16), bytes.fromhex(s["new"])
                av[o:o + len(new)] = new
    if flip is not None:
        av[flip] ^= 0x55
    lm_at = 0x7F82D15000
    maps = b"".join(b"%x-%x r-xp 00000000 b3:0f 100 /usr/lib%s\n" % (a, a + ((len(libs[n]) + 0xFFF) & ~0xFFF), n.encode())
                    for n, a in (("/libsencore.so", 0x7F80000000), ("/libJiritsu.so", 0x7F81000000), ("/libmpr.so", lm_at)))
    files = E.tree()
    files["/proc/self/maps"] = maps
    files["/proc/meminfo"] = b"MemTotal: 1 kB\n"
    files["/dev/mem"] = b""
    files["/proc/cmdline"] = b"console=ttyS0 " + (b"memrsv=0x01000000@0x401000000:ex " if reserve else b"") + b"warm.mode=2"
    for n, b in libs.items():
        files["/usr/lib" + n] = b
    dirs = {"/tmp_wbshd", "/proc", "/proc/self", "/sys/module/liro/parameters", "/log", "/usr/lib"}
    if exists:
        files[E.RESULT] = b"earlier result\n"
    log = bytearray(0x300000)                     # the main processor's log buffer: a few lines where the dump looks
    for off, line in ((0x232100, b"[IMLDECSTAT]start_command model line"), (0x232200, b"[ENCHANDLER] a repeating line the dump leaves out"),
                      (0x1CE100, b"MPR model line naming Play"), (0x1000, b"application model line naming an ERR")):
        log[off:off + len(line)] = line
    phys = {FACTS["avcam_phys"]: bytes([0x5A]) * 0x1000 + bytes(av[0x1000:]),      # the first page is not as in the file on a camera (A7S III, 2026-11-21)
            0x405000000: bytes(log),
            E.BUF_PHYS & ~0xFFF: bytes(0x2000)}
    own = {lm_at: bytes(lm)}
    return files, dirs, phys, {"image": bytes(cp), "ram": ram}, own


def run(lib, **kw):
    files, dirs, phys, cp, own = model(**kw)
    r = Run(lib, 22, files, dirs, phys=phys, cp=cp, own=own)      # level 22: the A7 IV harness's rules for a read-only helper that maps /dev/mem
    r.go()
    return r, r.writes.get(E.RESULT, b"").decode("utf8", "replace")


def spans(text):
    """Counts of the encoder spans' states in a result: {"stock": n, "other": n, mask: n}."""
    out = {"stock": 0, "other": 0}
    for ln in text.split("\n"):
        if ln.startswith(("lm ", "av ")):
            if ln.endswith("  STOCK"):
                out["stock"] += 1
            elif "  DESIGNS " in ln:
                m = int(ln.rsplit(" ", 1)[1], 16)
                out[m] = out.get(m, 0) + 1
            else:
                out["other"] += 1
    return out


def holds(text, step):
    """How many spans hold the bytes of this step's design."""
    return sum(n for m, n in spans(text).items() if isinstance(m, int) and m & BITS[step])


def main():
    ok = True
    n_spans = FACTS["lm_sites"] + FACTS["av_sites"]
    of = {d["step"]: d["lm_spans"] + d["av_spans"] for d in FACTS["mp_designs"]}
    site = lambda text, prefix, state: sum(1 for ln in text.split("\n") if ln.startswith("site " + prefix) and ln.endswith("  " + state))
    n_cells = sum(1 for s in FACTS["cp_sites"] if s["name"].startswith(("cell", "record_")) and not s["name"].startswith(("cell50_", "cell32_")))
    n_cells50 = sum(1 for s in FACTS["cp_sites"] if s["name"].startswith(("cell50_", "record50")))
    n_cells32 = sum(1 for s in FACTS["cp_sites"] if s["name"].startswith("cell32_"))       # cells only the 3:2 test design changes
    n_screen = sum(1 for s in FACTS["cp_sites"] if s["name"].startswith("screen"))
    K4 = ("L13", "L5", "L16", "L19", "S16")
    flip_at = next(int(p["file_off"], 16) for p in design(ENC["L19"])["patches"] if p["binary"] == "av-cam.bin")
    cases = (("stock", {}), ("stock-pal", {"system": "pal"}), ("applied", {"steps": K4}), ("no-screen", {"steps": K4[:-1]}),
             ("no-meta", {"steps": ("L13", "L5", "L16", "N19", "S16")}), ("si", {"steps": K4 + ("I19",)}),
             ("3x2", {"steps": ("L13", "T5", "L16", "L19", "S16")}),
             ("pal50", {"steps": ("L13", "L5", "Q5", "L16", "M19", "S16"), "system": "pal"}), ("5.76K", {"steps": ("L13", "L5", "K16", "K19", "S16")}),
             ("playback", {"steps": K4 + ("P29", "A29", "F29", "R19")}), ("broken", {"flip": flip_at}),
             ("fx30", {"build": "fx30_601"}), ("zve1", {"build": "zve1_202"}), ("a7iv", {"build": "a7iv_602"}),
             ("no-reserve", {"reserve": False}), ("exists", {"exists": True}))
    for which in ("check", "dump"):
        lib = (HERE / f"libJit_a6700_{which}.so").read_bytes()
        ok &= len(lib) <= 65520
        for case, kw in cases:
            r, text = run(lib, **kw)
            problems = []
            if r.bad:
                problems.append("stopped: " + r.bad)
            if set(r.writes) - {E.RESULT}:
                problems.append("wrote other files: %s" % sorted(set(r.writes) - {E.RESULT}))
            if any(c[0] == "transfer" and c[1] != 0 for c in r.lib_calls):
                problems.append("a transfer towards the coprocessor")
            sp = spans(text)
            ready = "VERDICT READY" in text
            want_ready = case not in ("broken", "fx30", "zve1", "a7iv", "no-reserve")
            if case == "exists":
                if r.writes or r.lib_calls:
                    problems.append("did something although a result existed")
            else:
                if "== done" not in text:
                    problems.append("result not complete")
                if ready != want_ready or ("VERDICT NOT READY" in text) == want_ready:
                    problems.append("verdict: wanted %s" % ("READY" if want_ready else "NOT READY"))
                steps = kw.get("steps", ())
                if case in ("fx30", "zve1", "a7iv"):
                    if "DIFFERS from the 2.00 update" not in text:
                        problems.append("identity not reported as differing")
                elif case == "no-reserve":
                    if "av-cam.bin is not read" not in text:
                        problems.append("the missing reservation is not reported")
                else:
                    if "DIFFERS" in text or sp["stock"] + sum(n for m, n in sp.items() if isinstance(m, int)) + sp["other"] != n_spans:
                        problems.append("identity or span count: %s" % sp)
                    if sp["other"] != (1 if case == "broken" else 0):
                        problems.append("spans in no known state: %d" % sp["other"])
                    # the sensor design's places (cellNN, record_left/right) and the cell only the 3:2 test design changes (cell32_NN)
                    l5 = lambda state: sum(1 for ln in text.split("\n") if ln.startswith(("site cell", "site record_")) and not ln.startswith(("site cell50_", "site cell32_"))
                                           and ln.endswith("  " + state))
                    only32 = lambda state: site(text, "cell32_", state)
                    if "T5" in steps:                      # its bytes at L5's places (TARGET at the one place where both designs write the same), and its own cell
                        if (l5("TARGET32"), l5("TARGET"), only32("TARGET")) != (n_cells - 1, 1, n_cells32):
                            problems.append("3:2 sensor sites: %d TARGET32, %d TARGET, own cells %d TARGET (want %d, 1, %d)" % (l5("TARGET32"), l5("TARGET"), only32("TARGET"), n_cells - 1, n_cells32))
                    elif l5("TARGET" if "L5" in steps else "STOCK") != n_cells or only32("STOCK") != n_cells32:
                        problems.append("sensor sites not all %s, or the 3:2 design's own cell not stock" % ("TARGET" if "L5" in steps else "STOCK"))
                    if site(text, "rawbuf_", "TARGET" if "L13" in steps else "STOCK") != 4:
                        problems.append("raw-buffer words")
                    c50 = sum(1 for ln in text.split("\n") if ln.startswith(("site cell50_", "site record50")) and ln.endswith("  " + ("TARGET" if "Q5" in steps else "STOCK")))
                    if c50 != n_cells50:
                        problems.append("50p sites: %d of %d" % (c50, n_cells50))
                    if site(text, "screen", "TARGET" if "S16" in steps else "STOCK") != n_screen:
                        problems.append("screen words")
                    recs = [ln for ln in text.split("\n") if ln.startswith("site stored_record_")]
                    if len(recs) != 6:
                        problems.append("stored records listed: %d" % len(recs))
                    if kw.get("system") == "pal" and not all("OTHER (not counted" in ln for ln in recs[:5]):
                        problems.append("a PAL camera's records should read as not counted")
                    if "L19" in steps and holds(text, "L19") != of["L19"]:
                        problems.append("L19's spans: %d of %d" % (holds(text, "L19"), of["L19"]))
                    if "N19" in steps and holds(text, "L19") != of["L19"] - 2:
                        problems.append("N19: %d of L19's %d spans (want all but the two heights)" % (holds(text, "L19"), of["L19"]))
                    if "I19" in steps and holds(text, "I19") != of["I19"]:
                        problems.append("I19's spans: %d of %d" % (holds(text, "I19"), of["I19"]))
                    if "M19" in steps and holds(text, "M19") != of["M19"]:
                        problems.append("M19's spans: %d of %d" % (holds(text, "M19"), of["M19"]))
                    if "K19" in steps and holds(text, "K19") != of["K19"]:
                        problems.append("K19's spans: %d of %d" % (holds(text, "K19"), of["K19"]))
                    if not steps and case != "broken" and sp["stock"] != n_spans:
                        problems.append("a stock camera's spans are not all stock")
                    pb = [ln for ln in text.split("\n") if ln.startswith("pb ")]
                    want_pb = "TARGET" if "P29" in steps else "STOCK"
                    if len(pb) != FACTS["pb_sites"] or not all(ln.endswith("  " + want_pb) for ln in pb):
                        problems.append("playback words: %s" % [ln[-8:] for ln in pb])
                    if which == "dump":
                        if text.count("cppage ") != sum(k for _, _, k in FACTS["dump_ranges"]):
                            problems.append("dump pages: %d" % text.count("cppage "))
                        if "IMLDECSTAT" not in text or "ENCHANDLER" in text or "naming Play" not in text or "naming an ERR" not in text:
                            problems.append("the main-processor log lines are not as the filter gives them")
            n_tr = sum(1 for c in r.lib_calls if c[0] == "transfer")
            print(f"{which:5} {case:10} {'ok' if not problems else 'FAILED'}  result {len(text):7} bytes, {n_tr:3} page reads  {'; '.join(problems)}")
            ok &= not problems
            if "--show" in sys.argv and case == "stock":
                print("\n".join(ln[:150] for ln in text.split("== identity")[1].splitlines()[:120]))
    # ---- the other kits' check libraries on an A6700
    for kit, path, verdict in (("FX30 kit", HERE.parent / "helper_fx30/libJit_fx30_check.so", "DIFFERS from the 6.01 update"),
                               ("FX3 kit", HERE.parent / "helper_fx3/libJit_fx3_check.so", "DIFFERS from the 7.02 update"),
                               ("FX2 kit", HERE.parent / "helper_fx2/libJit_fx2_check.so", "DIFFERS from the 1.01 update"),
                               ("ZV-E1 kit", HERE.parent / "helper_zv/libJit_zv_check.so", "DIFFERS from the 2.02 update")):
        if not path.is_file():
            print(f"foreign {kit}: library not here, skipped")
            continue
        r, text = run(path.read_bytes())
        good = not r.bad and "VERDICT NOT READY" in text and verdict in text and not (set(r.writes) - {E.RESULT})
        print(f"foreign {kit:12} on a stock A6700: {'ok, NOT READY' if good else 'FAILED'}  {r.bad or ''}")
        ok &= good
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
