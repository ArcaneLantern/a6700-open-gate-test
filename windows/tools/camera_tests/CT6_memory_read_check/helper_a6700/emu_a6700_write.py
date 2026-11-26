"""Run the built A6700 2.00 write libraries (build_a6700_write.sh) in Unicorn against a model camera. Offline; no camera. (A6700 port, 2026-11-26)

  C:\\Python313\\python.exe -B emu_a6700_write.py

helper_fx2/emu_fx2_write.py and helper_fx30/emu_fx30_write.py with this camera's models and steps:
  - coprocessor transfers must be whole 64-byte lines to or from the allocated buffer; a transfer TOWARDS the coprocessor may change only
    bytes of a listed site, and only to that site's stock or new bytes;
  - T5/T6: the exact 3:2 test design at L5's places (and one cell more): the same cases, and L5 and T5 refusing each other;
  - L5/L6 (MULTI_REC): the sensor object 0x17fab08 -> control -> +0x684 -> parameter object {vtable, 31, ids, system, records} -> the
    0x170-byte stored records, those of modes 0x820/0x880/0x890/0x8c0/0x8d0 holding the A6700's emulated stock records of an NTSC or of a
    PAL camera (build/emu_drvparam.py a6700_200); Q5/Q6: the record of mode 0x830, PAL only;
  - L13/L14: the memory manager's pages as the A6700's OWN DMM code leaves them after parsing its DmmCfg.bin (build/emu_dmm_server.py
    --build a6700_200); after L13 the same code must hand out units of the new size;
  - L16/L17, K16/K17, S16/S17: the movie size table as the A6700's set-up fills it (build/emu_size_table.py a6700_200), the memory
    manager's id rows and key lists from the same DMM model, and the loaded image for the screen words. The stock bytes of the words in
    RAM tables come from those models, NOT from the designs: a design whose stock bytes were wrong would be refused here;
  - level 19/20 steps (L19/L20, N19, I19/I20, M19/M20, K19/K20, R19/R20): av-cam.bin at its physical address and libmpr.so in the
    process's own mapping;
  - level 29/30 steps (P, A, F): emu_a6700_playback.py's cases.
Cases per library: apply on stock, apply again (nothing to do), put back (byte for byte), a site holding foreign bytes, a lost write
(undo), a guard wrong; which steps refuse on top of which; and the other kits' libraries of the same steps, which must write nothing here.
"""
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "helper"))
sys.path.insert(0, str(ROOT / "build"))
import emu_built as E  # noqa: E402
from unicorn import arm64_const as R  # noqa: E402
import emu_dmm_server  # noqa: E402
import emu_size_table  # noqa: E402
import parse_dmmcfg  # noqa: E402
import emu_a6700_playback  # noqa: E402

BUILD = "a6700_200"
BASE, CP_HI = 0x108000, 0x10000000
DES = ROOT / "modding/designs"
IMAGER, CTRL, OBJ, CTRL_DRVPARAM = 0x17FAB08, 0x1500000, 0x1500800, 0x684
IDS, RECS, REC, COUNT, VTABLE = 0xDC7B5C, 0x25DABCC, 0x170, 31, 0xDC8E64
MODES = ("0x820", "0x880", "0x890", "0x8c0", "0x8d0")
LM_AT = 0x7F82D15000
RESULT = E.RESULT
DEFAULT_DESIGN = E.DESIGN


def ex(rel, build=BUILD):
    return (ROOT / f"work/extracted/{build}/0700_part_image/dev" / rel).read_bytes()


def design(name):
    return json.loads((DES / f"{name}.json").read_text(encoding="utf8"))


def lib(name, folder="helper_a6700", prefix="a6700"):
    return (HERE.parent / folder / f"libJit_{prefix}_{name}.so").read_bytes()


class Mem:
    """Coprocessor memory: the image at 0x108000, zeros elsewhere, with what the model camera adds."""

    def __init__(self, image):
        self.pages, self.image = {}, image

    def page(self, a):
        a &= ~0xFFF
        if a not in self.pages:
            p = bytearray(4096)
            if BASE <= a < BASE + len(self.image):
                chunk = self.image[a - BASE:a - BASE + 4096]
                p[:len(chunk)] = chunk
            self.pages[a] = p
        return self.pages[a]

    def read(self, a, n):
        return bytes(self.page(a + k)[(a + k) & 0xFFF] for k in range(n))

    def write(self, a, data):
        for k, v in enumerate(data):
            self.page(a + k)[(a + k) & 0xFFF] = v

    def snapshot(self):
        return {a: bytes(p) for a, p in self.pages.items()}


class Run(E.Run):
    """emu_c2_write.py's run: every import is modelled here, against Mem."""

    def __init__(self, libbytes, files, dirs, mem, allowed, lose=None):
        saved, E.DESIGN = E.DESIGN, DEFAULT_DESIGN
        super().__init__(libbytes, 5, files, dirs, cp=b"")
        E.DESIGN = saved
        self.mem, self.allowed, self.lose, self.n_writes = mem, allowed, lose, 0

    def go(self):
        self.uc.reg_write(R.UC_ARM64_REG_SP, E.STACK - 0x1000)
        self.uc.reg_write(R.UC_ARM64_REG_X30, E.RET)
        self.uc.emu_start(self.ctor, E.RET, count=4_000_000_000)
        if not self.bad and self.uc.reg_read(R.UC_ARM64_REG_PC) != E.RET:
            self.bad = "the constructor did not return"
        return self

    def on_import(self, uc, address, size, _):
        x = lambda n: uc.reg_read(getattr(R, "UC_ARM64_REG_X%d" % n))
        name, ret = self.imports.get(address), 0
        if name == "_Z9dmm_allocjPj":
            uc.mem_write(x(1), struct.pack("<I", E.BUF_HANDLE))
            ret = self.buf
        elif name == "_Z8dmm_freej":
            pass
        elif name == "sen_dma_transfer":
            d, src, dst, n = x(0) & 0xFFFFFFFF, x(1), x(2), x(3) & 0xFFFFFFFF
            cp = src if d == 0 else dst
            if d not in (0, 1) or (dst if d == 0 else src) != self.buf or cp & 63 or n & 63 or not 0 < n <= 4096 or cp < BASE or cp + n > CP_HI:
                self.bad = "a transfer that is not whole lines to or from the buffer: dir %d src %#x dst %#x size %d" % (d, src, dst, n)
                uc.emu_stop()
                return
            va = next(v for v, off in self.map_phys.items() if v in self.maps and off <= self.buf < off + self.maps[v]) + self.buf % 4096
            if d == 0:
                uc.mem_write(va, self.mem.read(cp, n))
            else:
                data, now = bytes(uc.mem_read(va, n)), self.mem.read(cp, n)
                for k in range(n):
                    if data[k] != now[k] and data[k] not in self.allowed.get(cp + k, ()):
                        self.bad = "a write that changes %#x to %#x, which is not a listed site's stock or new byte" % (cp + k, data[k])
                        uc.emu_stop()
                        return
                self.n_writes += 1
                if self.lose != self.n_writes:
                    self.mem.write(cp, data)
        else:
            self.bad = "call of an unexpected import %r" % name
            uc.emu_stop()
            return
        uc.reg_write(R.UC_ARM64_REG_X0, ret)
        uc.reg_write(R.UC_ARM64_REG_PC, uc.reg_read(R.UC_ARM64_REG_X30))


def dmm_server(opens=(), frees=()):
    emu_dmm_server.use_build(BUILD)
    cfg = parse_dmmcfg.Config(parse_dmmcfg.find_file(BUILD), BUILD)
    srv = emu_dmm_server.Server(cfg.data, cfg)
    assert srv.init() == 0
    for i in opens:
        assert srv.open(i)["ok"]
    for n in frees:
        assert srv.free(n)["ok"]
    return srv


def main():
    fail = []
    ok = lambda cond, text: (print(("PASS  " if cond else "FAIL  ") + text), fail.append(text) if not cond else None)
    image = ex("nflasha8/cpapp-b.bin")
    files = E.tree()
    files["/dev/mem"] = b""
    dirs = {"/tmp_wbshd", "/sys/module/liro/parameters", "/proc/driver/pcie"}

    def go(libbytes, mem, allowed, **kw):
        r = Run(libbytes, files, dirs, mem, allowed, **kw).go()
        return r, r.writes.get(RESULT, b"").decode("utf8", "replace")

    def changed_only(mem, before, allowed):
        for a, p in mem.pages.items():
            b = before.get(a)
            if b is None:
                b = image[a - BASE:a - BASE + 4096].ljust(4096, b"\0") if BASE <= a < BASE + len(image) else bytes(4096)
            if any(p[k] != b[k] and (a + k) not in allowed for k in range(4096)):
                return False
        return True

    def state(mem, allowed):
        vals = [(mem.read(a, 1)[0], pr) for a, pr in allowed.items()]
        return "stock" if all(v == pr[0] for v, pr in vals) else "new" if all(v == pr[1] for v, pr in vals) else "mixed"

    # ---- L5 / L6: the sensor sites and the five stored records (MULTI_REC), NTSC and PAL
    d = design("ogsq_a6700_v1")
    d50 = design("ogsq50_a6700_v1")
    stock_all = {s: json.loads((ROOT / f"evidence/a6700/sensor/drvparam_stock_a6700_200{'_pal' if s == 'pal' else ''}.json").read_text(encoding="utf8"))["modes"] for s in ("ntsc", "pal")}
    ids = struct.unpack_from("<%dI" % COUNT, image, IDS - BASE)

    def sites_of(dsg):
        al = {}
        for p in dsg["patches"]:
            a = int(p["addr"], 16)
            for k, (o, n) in enumerate(zip(bytes.fromhex(p["old"]), bytes.fromhex(p["new"]))):
                if o != n:
                    al[a + k] = (o, n)
        return al

    def allowed_for(system):
        al = sites_of(d)
        for m in MODES:
            sr = d["stored_records"][m]
            st, nw = bytes.fromhex(sr[system]["stock"]), bytes.fromhex(sr[system]["design"])
            for k in range(REC):
                if st[k] != nw[k]:
                    al[RECS + sr["index"] * REC + k] = (st[k], nw[k])
        return al

    def allowed50():
        al = sites_of(d50)
        sr = d50["stored_record"]
        st, nw = bytes.fromhex(sr["stock"]), bytes.fromhex(sr["design"])
        for k in range(REC):
            if st[k] != nw[k]:
                al[RECS + sr["index"] * REC + k] = (st[k], nw[k])
        return al

    def camera(system="ntsc", img=image, imager=IMAGER):
        """The pointer chain and all 31 stored records as the A6700's own calculator gives them for this system (emulated)."""
        m = Mem(img)
        m.write(imager, struct.pack("<I", CTRL))
        m.write(CTRL + CTRL_DRVPARAM, struct.pack("<I", OBJ))
        m.write(OBJ, struct.pack("<6I", VTABLE + 8, COUNT, IDS, 1 if system == "pal" else 0, RECS, 0xDC7BD8))
        for i, mid in enumerate(ids):
            m.write(RECS + i * REC, bytes.fromhex(stock_all[system][hex(mid)]["record"]))
        return m

    # the design's stock records are the emulated ones at every site offset (the calculator's output, not the design, seeds the model)
    same = all(bytes.fromhex(d["stored_records"][m][s]["stock"])[int(o, 16)] == bytes.fromhex(stock_all[s][m]["record"])[int(o, 16)]
               for m in MODES for s in ("ntsc", "pal") for o in d["stored_records"][m]["offsets_that_differ"])
    ok(same, "the sensor design's stock stored-record bytes equal the A6700 calculator's output at every site offset (5 modes, NTSC and PAL)")
    L5, L6, Q5, Q6 = lib("L5"), lib("L6"), lib("Q5"), lib("Q6")
    n_sites = len(d["patches"])
    for system in ("ntsc", "pal"):
        al = allowed_for(system)
        mem = camera(system)
        before = mem.snapshot()
        r, t = go(L5, mem, al)
        ok(not r.bad and "DONE: all %d sites hold the target bytes (apply)" % (n_sites + 5) in t and state(mem, al) == "new" and changed_only(mem, before, al)
           and ("NTSC" if system == "ntsc" else "PAL") in t.split("the stored records are the ")[1].split("\n")[0],
           f"L5 on a stock {system.upper()} A6700: {n_sites} sites and the five stored records new, nothing else changed, the variant named ({r.n_writes} line writes)")
        r, t = go(L5, mem, al)
        ok(not r.bad and "NOTHING TO DO" in t and r.n_writes == 0, f"L5 again ({system.upper()}): nothing to do, no write")
        r, t = go(L6, mem, al)
        ok(not r.bad and "(put back)" in t and "DONE" in t and state(mem, al) == "stock" and changed_only(mem, before, {}), f"L6 ({system.upper()}): everything stock again, byte for byte")
        r, t = go(L6, mem, al)
        ok(not r.bad and "NOTHING TO DO" in t and r.n_writes == 0, f"L6 on a stock camera ({system.upper()}): nothing to do, no write")
    al = allowed_for("ntsc")
    mem = camera()
    mem.write(int(d["patches"][0]["addr"], 16), b"\x55")
    r, t = go(L5, mem, al)
    ok(not r.bad and r.n_writes == 0 and "holds neither the stock nor the new bytes; nothing is written" in t, "L5 with a site holding other bytes: nothing is written")
    for lose in (1, 7, n_sites + 5):
        mem = camera()
        before = mem.snapshot()
        r, t = go(L5, mem, al, lose=lose)
        ok(not r.bad and "NOT DONE: a step failed; every site this run touched was put back" in t and state(mem, al) == "stock" and changed_only(mem, before, {}),
           f"L5 with line write {lose} lost: reported, every site put back")
    mem = camera()
    mem.write(OBJ + 0x10, bytes(4))
    r, t = go(L5, mem, al)
    ok(not r.bad and r.n_writes == 0 and "was not found" in t, "L5 with a null records pointer: nothing is written")
    mem = camera()
    mem.write(IDS + 4 * d["stored_records"]["0x890"]["index"], struct.pack("<I", 0x1234))
    r, t = go(L5, mem, al)
    ok(not r.bad and r.n_writes == 0, "L5 when one of the five modes is not in the id table: nothing is written")
    mem = camera()                                          # one record of the other system among the five: no variant fits all
    sr = d["stored_records"]["0x880"]
    mem.write(RECS + sr["index"] * REC, bytes.fromhex(sr["pal"]["stock"]))
    r, t = go(L5, mem, al)
    ok(not r.bad and r.n_writes == 0 and "neither timing variant" in t, "L5 with one stored record of the other system: nothing is written")
    mem = camera(imager=0x13BD0D8)                          # the pointer where the FX30 has it, not where the A6700 has it
    mem.write(IMAGER, bytes(4))
    r, t = go(L5, mem, al)
    ok(not r.bad and r.n_writes == 0 and "was not found" in t, "L5 with the A6700's sensor object empty (the chain at the FX30's address): nothing is written")
    # T5 / T6: the exact 3:2 test design (ogsq32_a6700_v1), in L5's place
    d32 = design("ogsq32_a6700_v1")

    def allowed32(system):
        al_ = sites_of(d32)
        for m in MODES:
            sr = d32["stored_records"][m]
            st, nw = bytes.fromhex(sr[system]["stock"]), bytes.fromhex(sr[system]["design"])
            for k in range(REC):
                if st[k] != nw[k]:
                    al_[RECS + sr["index"] * REC + k] = (st[k], nw[k])
        return al_
    same32 = all(bytes.fromhex(d32["stored_records"][m][s]["stock"])[int(o, 16)] == bytes.fromhex(stock_all[s][m]["record"])[int(o, 16)]
                 for m in MODES for s in ("ntsc", "pal") for o in d32["stored_records"][m]["offsets_that_differ"])
    ok(same32, "the 3:2 test design's stock stored-record bytes equal the A6700 calculator's output at every site offset")
    T5, T6 = lib("T5"), lib("T6")
    n32 = len(d32["patches"])
    for system in ("ntsc", "pal"):
        al3 = allowed32(system)
        mem = camera(system)
        before = mem.snapshot()
        r, t = go(T5, mem, al3)
        ok(not r.bad and "DONE: all %d sites hold the target bytes (apply)" % (n32 + 5) in t and state(mem, al3) == "new" and changed_only(mem, before, al3),
           f"T5 (ogsq32_a6700_v1) on a stock {system.upper()} A6700: {n32} sites and the five stored records new, nothing else changed ({r.n_writes} line writes)")
        r, t = go(T5, mem, al3)
        ok(not r.bad and "NOTHING TO DO" in t and r.n_writes == 0, f"T5 again ({system.upper()}): nothing to do, no write")
        both3 = {**allowed_for(system), **al3}
        snap = mem.snapshot()
        r, t = go(L5, mem, both3)
        ok(not r.bad and r.n_writes == 0 and "nothing is written" in t and mem.snapshot() == snap, f"L5 on a camera holding T5's state ({system.upper()}): refused, nothing written")
        r, t = go(L6, mem, both3)
        ok(not r.bad and r.n_writes == 0 and mem.snapshot() == snap, f"L6 on a camera holding T5's state ({system.upper()}): nothing written (T6 is its put back)")
        r, t = go(T6, mem, al3)
        ok(not r.bad and "(put back)" in t and "DONE" in t and state(mem, al3) == "stock" and changed_only(mem, before, {}), f"T6 ({system.upper()}): everything stock again, byte for byte")
        mem = camera(system)
        go(L5, mem, allowed_for(system))
        snap = mem.snapshot()
        r, t = go(T5, mem, both3)
        ok(not r.bad and r.n_writes == 0 and "nothing is written" in t and mem.snapshot() == snap, f"T5 on a camera holding L5's state ({system.upper()}): refused, nothing written")
    al3 = allowed32("ntsc")
    for lose in (1, 9, n32 + 5):
        mem = camera()
        before = mem.snapshot()
        r, t = go(T5, mem, al3, lose=lose)
        ok(not r.bad and "NOT DONE: a step failed; every site this run touched was put back" in t and state(mem, al3) == "stock" and changed_only(mem, before, {}),
           f"T5 with line write {lose} lost: reported, every site put back")
    mem = camera("pal")                                     # T5 with the 50p step: disjoint places
    before = mem.snapshot()
    alq = {**allowed32("pal"), **allowed50()}
    r1, t1 = go(T5, mem, alq)
    r2, t2 = go(Q5, mem, alq)
    ok(not r1.bad and not r2.bad and "DONE" in t1 and "DONE" in t2 and state(mem, alq) == "new" and changed_only(mem, before, alq), "T5 then Q5 on PAL: both applied (disjoint places)")
    # Q5 / Q6: PAL only
    al50 = allowed50()
    mem = camera("pal")
    before = mem.snapshot()
    r, t = go(Q5, mem, al50)
    ok(not r.bad and "DONE: all %d sites hold the target bytes (apply)" % (len(d50["patches"]) + 1) in t and state(mem, al50) == "new" and changed_only(mem, before, al50),
       f"Q5 on a stock PAL A6700: {len(d50['patches'])} sites and the stored record of mode 0x830 new, nothing else changed ({r.n_writes} line writes)")
    r, t = go(Q5, mem, al50)
    ok(not r.bad and "NOTHING TO DO" in t and r.n_writes == 0, "Q5 again: nothing to do")
    r, t = go(Q6, mem, al50)
    ok(not r.bad and "(put back)" in t and "DONE" in t and state(mem, al50) == "stock" and changed_only(mem, before, {}), "Q6: everything stock again, byte for byte")
    mem = camera("ntsc")
    before = mem.snapshot()
    r, t = go(Q5, mem, al50)
    ok(not r.bad and r.n_writes == 0 and "nothing is written" in t and changed_only(mem, before, {}), "Q5 on an NTSC A6700: its stored record is not the PAL one, nothing is written")
    # L5 and Q5 together on PAL, in both orders, and their put backs
    alp = {**allowed_for("pal"), **al50}
    for first, second, fa, sa in ((L5, Q5, "L5", "Q5"), (Q5, L5, "Q5", "L5")):
        mem = camera("pal")
        before = mem.snapshot()
        r1, t1 = go(first, mem, alp)
        r2, t2 = go(second, mem, alp)
        good = not r1.bad and not r2.bad and "DONE" in t1 and "DONE" in t2 and state(mem, alp) == "new" and changed_only(mem, before, alp)
        r1, t1 = go(Q6, mem, alp)
        r2, t2 = go(L6, mem, alp)
        ok(good and not r1.bad and not r2.bad and state(mem, alp) == "stock" and changed_only(mem, before, {}), f"{fa} then {sa} on PAL: both applied (disjoint sites); Q6 and L6 give stock")
    # the other kits' sensor steps on an A6700: they must write nothing
    for label, path, their_imager in (("FX30 kit L5 (ogsq_fx30_v1)", HERE.parent / "helper_fx30/libJit_fx30_L5.so", 0x13BD0D8),
                                      ("ZV-E1 kit L5 (ogsq_zv_v2)", HERE.parent / "helper_zv/libJit_zv_L5.so", 0x17F1F64),
                                      ("FX2 kit L5 (ogsq_fx2_v1)", HERE.parent / "helper_fx2/libJit_fx2_L5.so", 0x1750860)):
        if not path.is_file():
            print("NOTE  %s not built: skipped" % label)
            continue
        mem = camera(imager=their_imager)                  # even with its pointer chain made to reach the A6700's real parameter object
        for off in (0x684, 0x690, 0x6AC):
            mem.write(CTRL + off, struct.pack("<I", OBJ))
        before = mem.snapshot()
        r, t = go(path.read_bytes(), mem, {})
        ok(not r.bad and r.n_writes == 0 and changed_only(mem, before, {}), f"{label} on an A6700, its chain led to the A6700's records: nothing is written")

    # ---- L13 / L14: the memory manager
    dd = design("dmmwb_a6700_v1")
    E.DESIGN = "dmmwb_a6700_v1"
    sites = [(int(s["ram_address"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"])) for s in dd["sites"]]
    d_allowed = {a + k: (o[k], n[k]) for a, o, n in sites for k in range(4)}

    def dmm_mem(srv):
        m = Mem(image)
        for a, b in srv.snapshot().values():
            m.write(a, b)
        # On the A6700 the server's pointers lie in two pages (unit objects 0x19d7bac, workspace 0x19d8058) and the 5.76K step reads the id
        # rows and key lists (0x25b6a68.., 0x25b8a68..): the snapshot's regions are the A7 IV's, so these come from the same emulator.
        for a, n in ((0x19D8000, 0x1000), (0x25B6000, 0x5000)):
            m.write(a, bytes(srv.uc.mem_read(a, n)))
        return m

    srv = dmm_server()
    mem = dmm_mem(srv)
    ok(all(mem.read(a, 4) == o for a, o, _ in sites), "the A6700's own DMM set-up leaves the stock sizes at the four words of dmmwb_a6700_v1 (the model is not seeded from the design)")
    before = mem.snapshot()
    L13, L14 = lib("L13"), lib("L14")
    r, t = go(L13, mem, d_allowed)
    ok(not r.bad and "DONE" in t and "three units of the new size fit" in t and all(mem.read(a, 4) == n for a, _, n in sites) and changed_only(mem, before, d_allowed),
       f"L13 on the A6700's own DMM state (nothing open): the four words new, nothing else changed ({r.n_writes} line writes)")
    srv2 = dmm_server()
    for a, _, n in sites:
        srv2.uc.mem_write(a, n)
    o = srv2.open(0x43E)
    ok(o["ok"] and [e["size"] for e in o["extents"]] == [dd["summary"]["unit_size"]], "after L13 the A6700's allocator code hands out a write buffer of %s bytes" % format(dd["summary"]["unit_size"], ","))
    r, t = go(L13, mem, d_allowed)
    ok(not r.bad and r.n_writes == 0 and ("NOTHING TO DO" in t or "already" in t), "L13 again: no write")
    r, t = go(L14, mem, d_allowed)
    ok(not r.bad and "DONE" in t and all(mem.read(a, 4) == o_ for a, o_, _ in sites) and changed_only(mem, before, {}), "L14: the four words stock again, byte for byte")
    busy = dmm_server(opens=(0x43E,))
    mem = dmm_mem(busy)
    r, t = go(L13, mem, d_allowed)
    ok(not r.bad and r.n_writes == 0 and "nothing is written" in t, "L13 while a movie write buffer is open (a block divided as the old layout): refused, nothing written")
    mem = dmm_mem(dmm_server())
    a0 = sites[0][0]
    mem.write(a0 - 12 + 4, b"\x99")                          # a byte of the record that is not the site: not as in the file
    r, t = go(L13, mem, d_allowed)
    ok(not r.bad and r.n_writes == 0 and "nothing is written" in t, "L13 with a unit record not as in the file: nothing is written")
    mem = dmm_mem(dmm_server())
    pa = int(dd["parent_guards"][-1]["ram_address"], 16)
    mem.write(pa + 12, struct.pack("<I", 3 * dd["summary"]["unit_size"] - 128))
    r, t = go(L13, mem, d_allowed)
    ok(not r.bad and r.n_writes == 0 and "nothing is written" in t, "L13 with a parent record changed (too small for three units): nothing is written")
    for lose in (1, 3):
        mem = dmm_mem(dmm_server())
        r, t = go(L13, mem, d_allowed, lose=lose)
        ok(not r.bad and "NOT DONE" in t and all(mem.read(a, 4) == o_ for a, o_, _ in sites), f"L13 with line write {lose} lost: everything put back")
    for label, path in (("ZV-E1 kit L13 (dmmwb_zv_v1)", HERE.parent / "helper_zv/libJit_zv_L13.so"), ("FX2 kit L13 (dmmwb4688_fx2_v1)", HERE.parent / "helper_fx2/libJit_fx2_L13.so")):
        if path.is_file():
            mem = dmm_mem(dmm_server())
            before = mem.snapshot()
            r, t = go(path.read_bytes(), mem, {})
            ok(not r.bad and r.n_writes == 0 and changed_only(mem, before, {}), f"{label} on an A6700's DMM state: nothing is written")

    # ---- L16 / L17 (output size), K16 / K17 (5.76K words), S16 / S17 (screen words)
    E.DESIGN = DEFAULT_DESIGN
    t_, srows, _ = emu_size_table.table(BUILD)

    def words_mem():
        m = dmm_mem(dmm_server())                           # the memory manager's id rows and key lists, as its own set-up leaves them
        for k, (w, h, mid) in enumerate(srows):
            m.write(t_ + 8 * k, struct.pack("<2HI", w, h, mid))
        return m
    wd = {}
    for name, s_apply, s_back in (("outsz2560_a6700_v1", "L16", "L17"), ("og57cp_a6700_v1", "K16", "K17"), ("lcdfill_a6700_v2", "S16", "S17")):
        dw = design(name)
        w_allowed = {}
        for s in dw["sites"]:
            a = int(s["ram_address"], 16)
            for k, (o, n) in enumerate(zip(bytes.fromhex(s["old"]), bytes.fromhex(s["new"]))):
                w_allowed[a + k] = (o, n)
        wd[s_apply] = (dw, w_allowed)
        La, Lb = lib(s_apply), lib(s_back)
        mem = words_mem()
        ok(all(mem.read(int(s["ram_address"], 16), 4) == bytes.fromhex(s["old"]) for s in dw["sites"])
           and all(mem.read(int(g["ram_address"], 16), len(g["bytes"]) // 2) == bytes.fromhex(g["bytes"]) for g in dw["guards"]),
           f"{name}: the A6700's own set-ups (size table, memory manager) and its image hold the design's stock words and guards")
        before = mem.snapshot()
        r, t = go(La, mem, w_allowed)
        ok(not r.bad and "DONE" in t and state(mem, w_allowed) == "new" and changed_only(mem, before, w_allowed),
           f"{s_apply} ({name}) on the model: {len(dw['sites'])} word(s) new, nothing else changed ({r.n_writes} line writes)")
        r, t = go(La, mem, w_allowed)
        ok(not r.bad and "NOTHING TO DO" in t and r.n_writes == 0, f"{s_apply} again: nothing to do")
        r, t = go(Lb, mem, w_allowed)
        ok(not r.bad and "DONE" in t and state(mem, w_allowed) == "stock" and changed_only(mem, before, {}), f"{s_back}: stock again, byte for byte")
        bad_guard = None
        for g in dw["guards"]:
            mem = words_mem()
            ga = int(g["ram_address"], 16)
            mem.write(ga, bytes([mem.read(ga, 1)[0] ^ 1]))
            r, t = go(La, mem, w_allowed)
            if r.bad or r.n_writes:
                bad_guard = ga
                break
        ok(bad_guard is None, f"{s_apply} with any one of its {len(dw['guards'])} guards wrong: nothing is written")
        mem = words_mem()
        a0 = int(dw["sites"][0]["ram_address"], 16)
        mem.write(a0, b"\x5a\x5a\x5a\x5a")
        r, t = go(La, mem, w_allowed)
        ok(not r.bad and r.n_writes == 0, f"{s_apply} with its first word holding other bytes: nothing is written")
        mem = words_mem()
        r, t = go(La, mem, w_allowed, lose=1)
        ok(not r.bad and "NOT DONE" in t and state(mem, w_allowed) == "stock", f"{s_apply} with the first line write lost: everything put back")
    both = {**wd["L16"][1], **wd["K16"][1]}
    mem = words_mem()
    go(lib("L16"), mem, wd["L16"][1])
    snap = mem.snapshot()
    r, t = go(lib("K16"), mem, both)
    ok(not r.bad and r.n_writes == 0 and "nothing is written" in t and mem.snapshot() == snap, "K16 on a camera holding L16's output size: refused, nothing written (the two states cannot be mixed)")
    mem = words_mem()
    go(lib("K16"), mem, wd["K16"][1])
    snap = mem.snapshot()
    r, t = go(lib("L16"), mem, both)
    ok(not r.bad and r.n_writes == 0 and "nothing is written" in t and mem.snapshot() == snap, "L16 on a camera holding K16's words: refused, nothing written")
    for label, path in (("FX30 kit S16 (lcd32dsq_fx30_v1)", HERE.parent / "helper_fx30/libJit_fx30_S16.so"), ("FX30 kit L16 (outsz2560_fx30_v1)", HERE.parent / "helper_fx30/libJit_fx30_L16.so"),
                        ("ZV-E1 kit S16 (lcdfill_zv_v2)", HERE.parent / "helper_zv/libJit_zv_S16.so"), ("ZV-E1 kit L16 (outsz2560_zv_v1)", HERE.parent / "helper_zv/libJit_zv_L16.so")):
        if path.is_file():
            mem = words_mem()
            before = mem.snapshot()
            r, t = go(path.read_bytes(), mem, {})
            ok(not r.bad and r.n_writes == 0 and changed_only(mem, before, {}), f"{label} on an A6700: nothing is written")

    # ---- the level 19/20 steps: encoder side
    av, lm = ex("nflasha3/av-cam.bin"), ex("nflasha15/lib/libmpr.so")
    av = bytes([0x5A]) * 0x1000 + av[0x1000:]
    phoff, phentsize, phnum = struct.unpack_from("<Q", lm, 0x20)[0], *struct.unpack_from("<HH", lm, 0x36)
    span = next(struct.unpack_from("<IIQQQQQQ", lm, phoff + k * phentsize) for k in range(phnum) if struct.unpack_from("<I", lm, phoff + k * phentsize)[0] == 1)[5]
    lspan = (span + 0xFFF) & ~0xFFF
    lm0 = lm[:span].ljust(lspan, b"\0")
    mfiles = dict(files)
    mfiles["/proc/self/mem"] = b""
    mfiles["/proc/self/maps"] = (b"00400000-00409000 r-xp 00000000 fc:8f 81970                              /usr/bin/im.elf\n"
                                 + b"%x-%x r-xp 00000000 fc:8f 55354                          /usr/lib/libmpr.so\n" % (LM_AT, LM_AT + lspan)
                                 + b"%x-%x ---p %08x fc:8f 55354                          /usr/lib/libmpr.so\n" % (LM_AT + lspan, LM_AT + lspan + 0x10000, lspan)
                                 + b"7f8b936000-7f8b991000 r-xp 00000000 fc:8f 55344                          /usr/lib/libsencore.so\n")
    V2, V1, SI, FULL, K57, PBM = ("ogfile2560_hs_s_a6700_v2", "ogfile2560_hs_s_a6700_v1", "ogfilesi2560_a6700_v1", "ogfile2560_full_a6700_v1",
                                 "ogfile57r260_a6700_v1", "pbmpr_a6700_v1")
    sts = {}
    for dn in (V2, V1, SI, FULL, K57, PBM):
        fl = design(dn)
        sts[dn] = {"av-cam.bin": [], "libmpr.so": []}
        for p in fl["patches"]:
            sts[dn][p["binary"]].append((int(p["file_off"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])))

    def applied(blob, dn, which):
        b = bytearray(blob)
        for o, old, new in sts[dn][which]:
            b[o:o + len(new)] = new
        return bytes(b)

    def mp(step, av_mem, lm_mem, libpath=None, **wrong):
        r = E.Run(libpath.read_bytes() if libpath else lib(step), int(step[1:]), mfiles, dirs, {E.AVCAM_PHYS: av_mem}, own={LM_AT: lm_mem})
        r.kview_fail = False
        r.stale = {E.AVCAM_PHYS + o for o in wrong.get("stale", ())}
        r.pwrite_lost = {LM_AT + o for o in wrong.get("pwrite_lost", ())}
        r.go()
        return r, r.writes.get(RESULT, b"").decode("utf8", "replace"), bytes(r.phys[E.AVCAM_PHYS]), bytes(r.uc.mem_read(LM_AT, lspan))

    def on(dn, a=av, m=lm0):
        return applied(a, dn, "av-cam.bin"), applied(m, dn, "libmpr.so")
    av2, lm2 = on(V2)
    av1, lm1 = on(V1)
    ok(av1 == av2 and lm1 != lm2, "the two 4K encoder designs differ only in libmpr.so (the two MP4 header heights)")
    for apply_, back, dn in (("L19", "L20", V2), ("M19", "M20", FULL), ("K19", "K20", K57), ("R19", "R20", PBM)):
        a_new, m_new = on(dn)
        r, t, a, m = mp(apply_, av, lm0)
        ok(not r.bad and a == a_new and m == m_new and "DONE" in t, f"{apply_} ({dn}): {len(sts[dn]['av-cam.bin'])} + {len(sts[dn]['libmpr.so'])} sites new, every other byte unchanged")
        r, t, a, m = mp(apply_, a_new, m_new)
        ok(not r.bad and a == a_new and m == m_new and not r.pwrites and not r.map_writes, f"{apply_} again: no write")
        r, t, a, m = mp(back, a_new, m_new)
        ok(not r.bad and a == av and m == lm0 and "DONE" in t, f"{back}: both stock again, byte for byte")
        r, t, a, m = mp(back, av, lm0)
        ok(not r.bad and a == av and m == lm0 and not r.pwrites and not r.map_writes, f"{back} on a stock camera: no write")
        if sts[dn]["libmpr.so"]:
            r, t, a, m = mp(apply_, av, lm0, pwrite_lost=[sts[dn]["libmpr.so"][0][0]])
            ok(not r.bad and a == av and m == lm0 and "NOT DONE" in t, f"{apply_} with a libmpr.so write lost: everything put back")
        if len(sts[dn]["av-cam.bin"]) > 3:
            r, t, a, m = mp(apply_, av, lm0, stale=[sts[dn]["av-cam.bin"][3][0]])
            ok(not r.bad and a == av and m == lm0 and "NOT DONE" in t, f"{apply_} with the kernel's view not following a write: everything put back")
    r, t, a, m = mp("N19", av, lm0)
    ok(not r.bad and a == av1 and m == lm1 and "DONE" in t, f"N19 ({V1}, --no-meta): its {len(sts[V1]['av-cam.bin'])} + {len(sts[V1]['libmpr.so'])} sites new, the heights stock")
    r, t, a, m = mp("L20", av1, lm1)
    ok(not r.bad and a == av and m == lm0 and "DONE" in t, "L20 on a camera holding N19's state: both stock again, byte for byte")
    r, t, a, m = mp("L19", av1, lm1)
    ok(not r.bad and a == av2 and m == lm2 and "DONE" in t and len(r.pwrites) == 2 and not r.map_writes, "L19 on a camera holding N19's state: only the two heights written")
    # I19 on top of L19, and in the other order; its put back
    av2s, lm2s = on(SI, av2, lm2)
    r, t, a, m = mp("I19", av2, lm2)
    ok(not r.bad and a == av2s and m == lm2s and "DONE" in t, f"I19 ({SI}) on a camera holding L19's state: its {len(sts[SI]['av-cam.bin'])} + {len(sts[SI]['libmpr.so'])} sites new, L19's untouched")
    r, t, a, m = mp("L20", av2s, lm2s)
    avs, lms = on(SI)
    ok(not r.bad and a == avs and m == lms and "DONE" in t, "L20 on a camera holding L19 and I19: L19's sites stock, I19's untouched (I20 is its put back)")
    r, t, a, m = mp("I20", av2s, lm2s)
    ok(not r.bad and a == av2 and m == lm2 and "DONE" in t, "I20: I19's sites stock again, L19's untouched")
    r, t, a, m = mp("I19", av, lm0)
    ok(not r.bad and a == avs and m == lms and "DONE" in t, "I19 on a stock camera: applied (its sites do not depend on L19's)")
    # which encoder states refuse each other: M19 (the contributed design, complete) and K19 stand in L19's place
    avf, lmf = on(FULL)
    avk, lmk = on(K57)
    for step, am, mm, label in (("M19", av2, lm2, "L19's state"), ("L19", avf, lmf, "M19's state"), ("K19", av2, lm2, "L19's state"), ("L19", avk, lmk, "K19's state"),
                                ("K19", avf, lmf, "M19's state"), ("M19", avk, lmk, "K19's state"), ("I19", avk, lmk, "K19's state")):
        r, t, a, m = mp(step, am, mm)
        ok(not r.bad and a == am and m == mm and not r.pwrites and not r.map_writes and "nothing is written" in t, f"{step} on a camera holding {label}: refused, nothing written")
    r, t, a, m = mp("M19", *on(SI))
    ok(not r.bad and a == avf and m == lmf and "DONE" in t, "M19 on a camera holding only I19's state: applied (I19's bytes are M19's at those sites)")
    r, t, a, m = mp("R19", avf, lmf)
    ok(not r.bad and a == avf and m == lmf and not r.pwrites and "NOTHING TO DO" in t, "R19 on a camera holding M19's state: nothing to do (M19 holds the same instruction)")
    avr, lmr = on(PBM, av2, lm2)
    r, t, a, m = mp("R19", av2, lm2)
    ok(not r.bad and a == avr and m == lmr and len(r.pwrites) == 1 and not r.map_writes and "DONE" in t, "R19 on a camera holding L19's state: one libmpr.so instruction written, av-cam.bin untouched")
    bad_av = bytearray(av)
    bad_av[design(V2)["descriptors"][0]["descriptor"] * 0x90 + 0x3936E8 + 0x28] ^= 1
    for step in ("L19", "M19", "K19"):
        dn = {"L19": V2, "M19": FULL, "K19": K57}[step]
        x = bytearray(av)
        x[design(dn)["descriptors"][0]["descriptor"] * 0x90 + 0x3936E8 + 0x28] ^= 1
        r, t, a, m = mp(step, bytes(x), lm0)
        ok(not r.bad and a == bytes(x) and m == lm0 and not r.pwrites and not r.map_writes, f"{step} with a guard of av-cam.bin wrong (a descriptor's profile key): nothing is written")
    for label, path in (("FX30 kit L19 (ogfile2560_hs_s_fx30_v2)", HERE.parent / "helper_fx30/libJit_fx30_L19.so"),
                        ("FX3 kit L19 (ogfile2560_hs_s_fx3_v2)", HERE.parent / "helper_fx3/libJit_fx3_L19.so"),
                        ("ZV-E1 kit L19 (ogfile2560_hs_s_zv_v1)", HERE.parent / "helper_zv/libJit_zv_L19.so")):
        if path.is_file():
            r, t, a, m = mp("L19", av, lm0, libpath=path)
            ok(not r.bad and a == av and m == lm0 and not r.pwrites and not r.map_writes, f"{label} on an A6700: nothing is written")

    # ---- the level 29/30 steps
    emu_a6700_playback.cases(ok)
    print("ALL PASS" if not fail else "FAILED: %d" % len(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
