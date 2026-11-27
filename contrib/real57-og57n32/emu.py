"""Ejecuta las bibliotecas de escritura (H5/H6, y las T5/T6 fijadas del kit como control) en Unicorn contra una camara modelo:
imagen cpapp-b.bin + paginas leidas de la camara (volcado de solo lectura en estado de fabrica). Nada toca la camara."""
import json
import struct
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn import arm64_const as A

KIT = Path(r"a6700fw\a6700-open-gate-test\windows")
H = KIT / "tools/camera_tests/CT6_memory_read_check"
DUMP = KIT / "camera_private/CT6_20261126T175312Z_a6700_dump"
OUT = Path(r"a6700fw\og57n32")
IMG = Path(r"a6700fw\out\firmware.tar_unpacked\0700_part_image\dev\nflasha8_unpacked\cpapp-b.bin").read_bytes()
CPBASE, IMAGER, CTRL, OBJ, IDS, RECS, REC = 0x108000, 0x17FAB08, 0x1500000, 0x1500800, 0xDC7B5C, 0x25DABCC, 0x170
MODES = ("0x820", "0x880", "0x890", "0x8c0", "0x8d0")
BUFPHYS, LIB, STUB, STACK, RET, VA = 0x410000000, 0x10000000, 0x20000000, 0x30000000, 0x40000000, 0x50000000


class Mem:
    def __init__(self):
        self.p = {}
        self.dumped = {int(f.stem.rsplit("_", 1)[1], 16): f.read_bytes() for f in DUMP.glob("cp_*.bin")}

    def page(self, a):
        a &= ~0xFFF
        if a not in self.p:
            b = bytearray(4096)
            if CPBASE <= a < CPBASE + len(IMG):
                c = IMG[a - CPBASE:a - CPBASE + 4096]
                b[:len(c)] = c
            if a in self.dumped:
                b = bytearray(self.dumped[a])
            self.p[a] = b
        return self.p[a]

    def read(self, a, n):
        return bytes(self.page(a + k)[(a + k) & 0xFFF] for k in range(n))

    def write(self, a, d):
        for k, v in enumerate(d):
            self.page(a + k)[(a + k) & 0xFFF] = v


def run(lib, mem, allowed, lose=None):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for base, size in ((LIB, 0x100000), (STUB, 0x1000), (STACK, 0x100000), (RET, 0x1000), (VA, 0x10000)):
        uc.mem_map(base, size)
    phoff = struct.unpack_from("<Q", lib, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", lib, 54)
    dyn = {}
    for i in range(phnum):
        t, _, off, vaddr, _, fsz, _, _ = struct.unpack_from("<IIQQQQQQ", lib, phoff + i * phentsize)
        if t == 1:
            uc.mem_write(LIB + vaddr, lib[off:off + fsz])
        if t == 2:
            for k in range(off, off + fsz, 16):
                tag, val = struct.unpack_from("<QQ", lib, k)
                if tag == 0:
                    break
                dyn.setdefault(tag, val)
    rd = lambda a, n: bytes(uc.mem_read(LIB + a, n))
    stubs, imports = {}, {}
    for tab, size in ((dyn.get(7), dyn.get(8)), (dyn.get(23), dyn.get(2))):      # RELA, JMPREL
        for k in range(0, size or 0, 24):
            off, info, add = struct.unpack("<QQq", rd(tab + k, 24))
            kind, sym = info & 0xFFFFFFFF, info >> 32
            if kind == 1027:                                                     # RELATIVE
                val = LIB + add
            else:
                assert kind in (257, 1025, 1026), kind
                nm, _, _, shndx, value, _ = struct.unpack("<IBBHQQ", rd(dyn[6] + 24 * sym, 24))
                name = rd(dyn[5] + nm, 64).split(b"\0")[0].decode()
                if shndx:
                    val = LIB + value + add
                else:
                    val = stubs.setdefault(name, STUB + 16 * len(stubs))
                    imports[val] = name
            uc.mem_write(LIB + off, struct.pack("<Q", val))
    for a in imports:
        uc.mem_write(a, bytes.fromhex("c0035fd6"))
    st = {"bad": None, "out": bytearray(), "writes": 0}
    reg = lambda n: uc.reg_read(getattr(A, "UC_ARM64_REG_X%d" % n))

    def stop(why):
        st["bad"] = why
        uc.emu_stop()

    def on_import(_, addr, size, __):
        name = imports.get(addr)
        if name is None:
            return
        ret = 0
        if name == "_Z9dmm_allocjPj":
            uc.mem_write(reg(1), struct.pack("<I", 7))
            ret = BUFPHYS
        elif name == "sen_dma_transfer":
            d, src, dst, n = reg(0) & 0xFFFFFFFF, reg(1), reg(2), reg(3) & 0xFFFFFFFF
            cp = src if d == 0 else dst
            if d not in (0, 1) or (dst if d == 0 else src) != BUFPHYS or cp & 63 or n & 63 or not 0 < n <= 4096:
                return stop("transferencia no valida")
            if d == 0:
                uc.mem_write(VA, mem.read(cp, n))
            else:
                data, now = bytes(uc.mem_read(VA, n)), mem.read(cp, n)
                for k in range(n):
                    if data[k] != now[k] and data[k] not in allowed.get(cp + k, ()):
                        return stop("escritura fuera de lo listado en %#x" % (cp + k))
                st["writes"] += 1
                if lose != st["writes"]:
                    mem.write(cp, data)
        elif name != "_Z8dmm_freej":
            return stop("import inesperado " + name)
        uc.reg_write(A.UC_ARM64_REG_X0, ret)

    def on_svc(_, no, __):
        n, x0, x1, x2 = reg(8), reg(0), reg(1), reg(2)
        ret = 0
        if n == 56:                                   # openat
            path = bytes(uc.mem_read(x1, 200)).split(b"\0")[0].decode()
            ret = 3 if path == "/tmp_wbshd/readcheck_result.txt" else 4 if path == "/dev/mem" else -2
        elif n == 64:                                 # write
            if x0 != 3:
                return stop("write a un fichero que no es el resultado")
            st["out"] += uc.mem_read(x1, x2)
            ret = x2
        elif n == 222:                                # mmap del buffer propio
            if reg(4) != 4 or reg(5) != BUFPHYS:
                return stop("mmap inesperado")
            ret = VA
        elif n not in (57, 175, 215):
            return stop("syscall inesperada %d" % n)
        uc.reg_write(A.UC_ARM64_REG_X0, ret & (2 ** 64 - 1))

    uc.hook_add(UC_HOOK_CODE, on_import, begin=STUB, end=STUB + 0xFFF)
    uc.hook_add(UC_HOOK_INTR, on_svc)
    init = struct.unpack("<Q", bytes(uc.mem_read(LIB + dyn[25], 8)))[0]           # DT_INIT_ARRAY
    uc.reg_write(A.UC_ARM64_REG_CPACR_EL1, 3 << 20)
    uc.reg_write(A.UC_ARM64_REG_SP, STACK + 0xFF000)
    uc.reg_write(A.UC_ARM64_REG_X30, RET)
    uc.emu_start(init, RET, count=2_000_000_000)
    if not st["bad"] and uc.reg_read(A.UC_ARM64_REG_PC) != RET:
        st["bad"] = "no volvio"
    return st["bad"], st["out"].decode("utf8", "replace"), st["writes"]


def main():
    design = lambda p: json.loads(Path(p).read_text(encoding="utf8"))
    d32 = design(KIT / "tools/modding/designs/ogsq32_a6700_v1.json")
    new = design(OUT / "og57n32_a6700_v2.json")
    ids = list(struct.unpack_from("<31I", IMG, IDS - CPBASE))

    def camera():
        m = Mem()
        m.write(IMAGER, struct.pack("<I", CTRL))
        m.write(CTRL + 0x684, struct.pack("<I", OBJ))
        m.write(OBJ, struct.pack("<6I", 0xDC8E6C, 31, IDS, 1, RECS, 0xDC7BD8))
        return m

    def sites(d):
        al = {}
        for p in d["patches"]:
            for k, (o, n) in enumerate(zip(bytes.fromhex(p["old"]), bytes.fromhex(p["new"]))):
                if o != n:
                    al[int(p["addr"], 16) + k] = (o, n)
        for mode in MODES:
            sr = d["stored_records"][mode]
            for k, (o, n) in enumerate(zip(bytes.fromhex(sr["pal"]["stock"]), bytes.fromhex(sr["pal"]["design"]))):
                if o != n:
                    al[RECS + ids.index(int(mode, 16)) * REC + k] = (o, n)
        return al

    real = camera()
    for mode in MODES:                                   # los registros guardados REALES de la camara (volcado de fabrica)
        assert (RECS + ids.index(int(mode, 16)) * REC) & ~0xFFF in real.dumped, "pagina de registros no volcada"
    al_new, al_32 = sites(new), sites(d32)
    print("la camara real (volcado) tiene los bytes de fabrica en los %d bytes que cambiaria:" % len(al_new),
          all(real.read(a, 1)[0] == o for a, (o, n) in al_new.items()))
    fails = []

    def ok(c, text):
        print(("PASS  " if c else "FAIL  ") + text)
        if not c:
            fails.append(text)

    def diff(m):
        """direcciones que difieren de la camara de partida"""
        ref, out = camera(), set()
        for a, p in m.p.items():
            q = ref.page(a)
            out |= {a + k for k in range(4096) if p[k] != q[k]}
        return out

    libs = {"T": ((H / "helper_a6700/libJit_a6700_T5.so").read_bytes(), (H / "helper_a6700/libJit_a6700_T6.so").read_bytes(), al_32, al_new),
            "H": ((OUT / "build/libJit_a6700_H5.so").read_bytes(), (OUT / "build/libJit_a6700_H6.so").read_bytes(), al_new, al_32)}
    for tag, (a5, a6, al, other) in libs.items():
        print("== %s5 / %s6%s" % (tag, tag, " (control: bibliotecas fijadas del kit)" if tag == "T" else " (nuevas)"))
        m = camera()
        bad, t, w = run(a5, m, al)
        ok(not bad and "DONE: all" in t and "PAL" in t and diff(m) == set(al) and all(m.read(a, 1)[0] == n for a, (o, n) in al.items()),
           "aplicar en fabrica: exactamente los %d bytes previstos (%d escrituras) %s" % (len(al), w, bad or ""))
        bad, t, w = run(a5, m, al)
        ok(not bad and "NOTHING TO DO" in t and w == 0, "aplicar otra vez: nada que hacer")
        bad, t, w = run(a6, m, al)
        ok(not bad and "(put back)" in t and "DONE" in t and not diff(m), "deshacer: todo igual que antes, byte a byte")
        bad, t, w = run(a6, m, al)
        ok(not bad and "NOTHING TO DO" in t and w == 0, "deshacer en fabrica: nada que hacer")
        for lose in (1, 7, 30, 53, 54, 59):
            m = camera()
            bad, t, w = run(a5, m, al, lose=lose)
            ok(not bad and "NOT DONE: a step failed" in t and not diff(m), "escritura %d perdida: lo detecta y lo devuelve todo" % lose)
        for a in (min(al), max(al)):
            m = camera()
            m.write(a, bytes([next(v for v in range(256) if v not in al[a])]))
            snap = m.read(a, 1)
            bad, t, w = run(a5, m, al)
            ok(not bad and w == 0 and "nothing is written" in t and m.read(a, 1) == snap, "byte ajeno en %#x: no escribe nada" % a)
        m = camera()
        run(libs["T" if tag == "H" else "H"][0], m, other)
        before = diff(m)
        for lib, what in ((a5, "aplicar"), (a6, "deshacer")):
            bad, t, w = run(lib, m, {**al, **other})
            ok(bool(before) and not bad and w == 0 and "nothing is written" in t and diff(m) == before, "%s sobre el estado del otro diseno: se niega" % what)
    print("\n%d fallos" % len(fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
