"""A6700 2.00 (a6700_200) open gate, coprocessor side: the five designs of the A6700 kit (A6700 port, 2026-11-26).

  C:\\Python313\\python.exe -B build\\build_og_a6700.py            (needs Unicorn and capstone: C:\\Python313 has them)

writes modding/designs/{dmmwb_a6700_v1, ogsq_a6700_v1, ogsq50_a6700_v1, outsz2560_a6700_v1, og57cp_a6700_v1}.json and
evidence/a6700/sensor/*.json. Nothing is written to a firmware file or sent to a camera.

Where the designs come from. A contributor ported our kit to the A6700 (work/contrib/a6700_v1.0; reported as run on a PAL A6700, no logs
seen). This builder does NOT copy that kit's bytes. It takes the kit's four CHOICES -- the 4K window 5952 x 3876 from sensor row 214 with 80
phase-detect rows, the 50p window 5612 x 3732 from row 214 with 76, the raw write buffer 6016 x 3980, and the A7 IV's og57cp_v3 for 5.7K --
and derives every byte again from the A6700 2.00 files with the tools of the FX30 and A7C II ports. Where the contributed kit is on disk
each derived byte is then compared with it; every difference is listed in the design ("against_the_contributed_kit") and printed.

What the A6700 is (read from cpapp-b.bin 2.00, every fact asserted below):
  - The FX30's sensor family and table layout: the same 31 mode ids (0xdc7b5c), crop / stream-0 / stream-1 / LC tables byte-identical to the
    FX30 6.01's, 14-byte read-out rows, the same record selector (0x7938f4 = FX30 0x73ccde) and picture records (each differs from the
    FX30's in six words, 0x948..0x952). Modes 0x820, 0x880, 0x890, 0x8c0, 0x8d0 (indices 2, 4, 5, 6, 7) share the picture-record pair
    0xd3885c / 0xd39414 and register-matrix column 1; mode 0x830 (index 3) has its own pair 0xd39fcc / 0xd3ab84 and column 2.
  - NOT the FX30's register matrix: the A6700's (0x10cd634, 154 rows of 20 bytes, column map 0x10ce250) has 15 more rows at its start, and
    they hold the window per column: rows 3/4 the first row + 81, rows 5/6 half the rows read, row 7 the first phase-detect block, row 8
    half the phase-detect rows, row 10 the read-out lead f2. So the window is in the matrix AND in the per-mode tables, and a design has
    to change both (on the FX30 the columns are byte-identical and only the tables count).
  - The A7C II / ZV-E1 generation's stored record: 0x170 bytes (0x9718fc), control object as the ZV-E1 (configuration +0x54c, the
    drive-parameter object pointer at +0x684).

The sensor-side design ogsq_a6700_v1 changes, for all FIVE modes that share the pair and the column:
  matrix column 1   rows 3, 5, 6, 7, 8, 10 (one byte each)   first row + 81 (487 -> 295), half the rows (1680 -> 1944), first block (9 -> 5),
                                                             half the phase-detect rows (34 -> 40), f2 (41 -> 47)
  geometry 0xd77390 (12-byte rows by mode id) +10            window row 406 -> 214
  crop     0xdc7bd8 (20-byte rows) +6 / +18                  window row 406 -> 214 / first phase-detect block 9 -> 5
  stream-0 0xeb4cc2 (38) +26                                 window height 3348 -> 3876
  stream-1 0xeb515c (38) +26                                 phase-detect rows 68 -> 80
  LC       0xeb55f6 (14) +8 / +12                            window row 406 -> 214 / first phase-detect row 457 -> 265
  read-out 0xeb57a8 (14) +4 / +12                            f2 41 -> 47 / read-out length 1704 -> 1968
  the two picture records                                    first stage 3884 rows, squeezed by Lrc into the stock 4336 x 2438 front end
  the five stored records (RAM), NTSC and PAL variants       what the camera's own calculator makes of the cells, and the vertical sampling
                                                             ratio 165/191 at +6/+7 (3876 x 165/191 = 3348.4: the resize fit keeps every row)
The contributed kit changes the table rows of 0x820, 0x880 and 0x8c0 only and leaves those of 0x890 and 0x8d0 stock, although the matrix
column and the picture records it changes are theirs too; on NTSC it writes the stored record of 0x8c0 only. Here every mode that shares
the changed column and records gets its rows and its stored record, in both systems (the FX30 kit's rule).

The 50p design ogsq50_a6700_v1 does the same for mode 0x830 alone (matrix column 2, its table rows, its record pair, its stored record;
window 5612 x 3732 from row 214, ratio 137/162). Its stored record is the PAL one: on an NTSC camera the record's time values differ, the
write level finds neither its stock nor its new bytes and writes nothing (at 59.94p the taller read-out would not fit the frame anyway).
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import locate_file  # noqa: E402
import build_og_fx30 as G  # noqa: E402     (the row model and build_fhnative's planner and packers, pointed at this image below)
import emu_drvparam as E  # noqa: E402
import emu_record_selector as S  # noqa: E402
import emu_size_table  # noqa: E402
import emu_dmm_server as D  # noqa: E402
import parse_dmmcfg as P  # noqa: E402

B, SIZE = 0x108000, G.SIZE
BUILD = "a6700_200"
X = locate_file.locate(BUILD, "cpapp-b.bin").read_bytes()
FX30 = G.X
SHA = hashlib.sha256(X).hexdigest()
IMAGE_END = B + len(X)
KIT = ROOT / "work/contrib/a6700_v1.0/A6700 OpenGate/a6700-opengate_v1.0/designs"
DES, EV = ROOT / "modding/designs", ROOT / "evidence/a6700/sensor"
IDS, NMODES = 0xDC7B5C, 31
MODES, MODE50 = (0x820, 0x880, 0x890, 0x8C0, 0x8D0), 0x830
MATRIX, MROWS, MROW, COLMAP = 0x10CD634, 154, 20, 0x10CE250
FX30_MATRIX, FX30_MROWS = 0x1038E48, 139
M_START_LO, M_START_HI, M_HALF_LO, M_HALF_HI, M_PD_FIRST, M_PD_HALF, M_F2 = 3, 4, 5, 6, 7, 8, 10    # matrix rows of the window registers
GEO = 0xD77390                                     # 12-byte rows: u32 mode id, u16 x3, u16 window row
CROP, S0, S1, LC, RO = (0xDC7BD8, 20), (0xEB4CC2, 38), (0xEB515C, 38), (0xEB55F6, 14), (0xEB57A8, 14)
PAIR = {"L": 0xD3885C, "R": 0xD39414}
DCI = {"L": 0xD3597C, "R": 0xD36534}
P830 = {"L": 0xD39FCC, "R": 0xD3AB84}
# (stage rows, phase-detect rows p, read-out f2, window row) of each stock pair: the FX30's numbers, asserted on this image below
GEOM = {"8c0": (3356, 68, 41, 406), "dci": (3148, 64, 39, 510), "830": (3164, 64, 40, 502)}
# the designs' windows (the contributed kit's choices)
NEW_ROW, NEW_H, NEW_P, PAV = 214, 3876, 80, (165, 191)
ROW50, H50, P50, PAV50 = 214, 3732, 76, (137, 162)
OUT = (4336, 2438)
SENSOR_ROWS_END = 4096                             # the rows a window reads (with its 6-row margins) end at or below this in every stock mode
RAW_PITCH, RAW_ROWS_STOCK, RAW_ROWS_NEW = 6016, 3356, 3980

u16 = lambda b, o: struct.unpack_from("<H", b, o)[0]
rd = lambda a, n: X[a - B:a - B + n]
G.X, G.BUILD, G.PAIR, G.DCI, G.P830, G.GEOM = X, BUILD, PAIR, DCI, P830, GEOM       # the FX30 builder's functions read these at call time


def contrib(name):
    p = KIT / f"{name}.json"
    return json.loads(p.read_text(encoding="utf8")) if p.is_file() else None


def write(name, design, pokes=None):
    DES.mkdir(parents=True, exist_ok=True)
    (DES / f"{name}.json").write_text(json.dumps(design, indent=1) + "\n", encoding="utf8", newline="\n")
    if pokes is not None:
        (DES / f"{name}_pokes_ram.txt").write_text("".join(f"{a} {v}\n" for a, v in pokes), encoding="utf8", newline="\n")


# ---------------------------------------------------------------- what the image holds

def table_row(tbl, i):
    return struct.unpack_from("<%dH" % (tbl[1] // 2), X, tbl[0] - B + tbl[1] * i)


def check_sensor_facts():
    ids = list(struct.unpack_from("<%dI" % NMODES, X, IDS - B))
    assert ids == list(struct.unpack_from("<%dI" % NMODES, FX30, G.IDS - B)), "the mode ids are not the FX30's"
    idx = [ids.index(m) for m in MODES]
    i50 = ids.index(MODE50)
    assert idx == [2, 4, 5, 6, 7] and i50 == 3
    # the per-mode tables: the first four are the FX30's byte for byte
    for a, f in ((CROP, G.CROP), (S0, G.S0), (S1, G.S1), (LC, G.LC)):
        assert rd(a[0], a[1] * NMODES) == FX30[f[0] - B:f[0] - B + f[1] * NMODES], f"table {a[0]:#x} is not the FX30's"
    ro_diff = [i for i in range(NMODES) if rd(RO[0] + RO[1] * i, RO[1]) != FX30[G.RO[0] - B + G.RO[1] * i:G.RO[0] - B + G.RO[1] * (i + 1)]]
    assert not set(ro_diff) & set(idx + [i50]), "a read-out row of the designs' modes differs from the FX30's"
    for tbl in (CROP, S0, S1, LC, RO):
        ref = rd(tbl[0] + tbl[1] * 6, tbl[1])
        assert all(rd(tbl[0] + tbl[1] * i, tbl[1]) == ref for i in idx), f"table {tbl[0]:#x}: the five modes' rows differ"
    geo = {}
    for r in range(25):
        mid = struct.unpack_from("<I", X, GEO - B + 12 * r)[0]
        if mid in MODES + (MODE50,):
            geo[mid] = GEO + 12 * r
    assert sorted(geo) == sorted(MODES + (MODE50,)) and all(u16(X, geo[m] - B + 10) == 406 for m in MODES) and u16(X, geo[MODE50] - B + 10) == 502
    # the register matrix: the FX30's 139 rows after 15 rows of its own, which hold the window per column
    col = struct.unpack_from("<%dI" % NMODES, X, COLMAP - B)
    assert MATRIX + MROW * (MROWS + 1) == COLMAP and rd(MATRIX + MROW * MROWS, MROW) == bytes(MROW), "matrix end row / column map"
    assert all(col[i] == 1 for i in idx) and col[i50] == 2 and [i for i in range(NMODES) if col[i] in (1, 2)] == sorted(idx + [i50]), "columns 1 and 2 have other users"
    rows = [rd(MATRIX + MROW * r, MROW) for r in range(MROWS)]
    frows = [FX30[FX30_MATRIX - B + MROW * r:FX30_MATRIX - B + MROW * (r + 1)] for r in range(FX30_MROWS)]
    same_tail = sum(rows[15 + r][4:18] == frows[r][4:18] for r in range(FX30_MROWS))
    # the window rules of the 15 leading rows, on every column whose modes are movie windows of this family (1, 2, 8, 9)
    reg = lambda r, c: rows[r][4 + c]
    rules = {}
    for c, i in ((1, 6), (2, 3), (8, 14), (9, 16)):
        assert col[i] == c
        crop, s0, s1, ro = (table_row(t, i) for t in (CROP, S0, S1, RO))
        start, half = reg(M_START_LO, c) | reg(M_START_HI, c) << 8, reg(M_HALF_LO, c) | reg(M_HALF_HI, c) << 8
        want = (crop[3] + 81, (s0[13] + sum(s0[11:13]) + sum(s0[14:16])) // 2, crop[9], s1[13] // 2, ro[2])
        got = (start, half, reg(M_PD_FIRST, c), reg(M_PD_HALF, c), reg(M_F2, c))
        assert got == want and s1[13] % 2 == 0, (c, got, want)
        rules[c] = {"mode": hex(ids[i]), "first_row_plus_81": start, "half_rows_read": half, "first_block": got[2], "half_pdaf_rows": got[3], "f2": got[4]}
    # stock rules on the stock movie modes (indices: 0x830 3, 0x8c0 6, 0x28c0 14, 0x5c0 16), as build_og_fx30.check_sensor_facts
    for i in (3, 6, 14, 16):
        crop, lc, s0, s1, ro = (table_row(t, i) for t in (CROP, LC, S0, S1, RO))
        assert lc[6] == 25 + 48 * crop[9] and crop[3] == lc[4], (i, lc, crop)
        inside, unclear = G.pdaf_blocks(crop[3], s0[13], s0[11] + s0[12], s0[14] + s0[15])
        assert not unclear and inside[0] == crop[9] and len(inside) == s1[13], (i, inside, unclear, crop[9], s1[13])
        rows_read = s0[13] + sum(s0[11:13]) + sum(s0[14:16])
        assert crop[3] - sum(s0[11:13]) + rows_read <= SENSOR_ROWS_END
        if i != 3:                                                       # 0x830 runs line 360: 2 f2 = p + 16 and one line more there
            assert 2 * ro[2] == s1[13] + 14 and ro[6] == rows_read // 2 + 24, (i, ro, s1[13])
        else:
            assert 2 * ro[2] == s1[13] + 16 and ro[6] == rows_read // 2 + 25, (i, ro, s1[13])
    sel, _ = S.records(BUILD)
    assert all(sel[m] == [PAIR["L"], PAIR["R"]] for m in MODES) and sel[MODE50] == [P830["L"], P830["R"]]
    others = [hex(m) for m, r in sel.items() if m not in MODES + (MODE50,) and set(r) & (set(PAIR.values()) | set(P830.values()))]
    assert not others, others
    pair_vs_fx30 = {h: [hex(o) for o in range(0, SIZE, 2) if rd(PAIR[h] + o, 2) != FX30[G_FX30_PAIR[h] - B + o:G_FX30_PAIR[h] - B + o + 2]] for h in "LR"}
    facts = {"mode_ids_equal_fx30": True, "tables_equal_fx30": ["crop", "stream-0", "stream-1", "LC"], "readout_rows_differing_from_fx30": [hex(ids[i]) for i in ro_diff],
             "matrix": {"address": hex(MATRIX), "rows": MROWS, "row_bytes": MROW, "column_map": hex(COLMAP), "columns": 14,
                        "rows_15_on_equal_to_the_fx30_matrix": f"{same_tail} of {FX30_MROWS}",
                        "window_rows": {"first_row_plus_81": [M_START_LO, M_START_HI], "half_the_rows_read": [M_HALF_LO, M_HALF_HI], "first_phase_detect_block": M_PD_FIRST,
                                        "half_the_phase_detect_rows": M_PD_HALF, "f2": M_F2}, "rule_holds_on_columns": rules},
             "column_of_each_mode": {hex(ids[i]): col[i] for i in range(NMODES)},
             "picture_record_words_differing_from_fx30": pair_vs_fx30}
    return ids, idx, i50, geo, col, facts


G_FX30_PAIR = {"L": 0xC79440, "R": 0xC79FF8}


def window_cells(modes_idx, geo_addrs, column, row, height, p, line360_own, margin_rule=False):
    """The cells of one window in every mode of `modes_idx` and in matrix column `column`: [(address, old, new, note)] and the facts.
    margin_rule (ogsq32_a6700_v1): the first block and the count are the ones the stock windows' margin rule gives (G.pdaf_blocks), as in the
    FX30 kit's ogsq_fx30_v2; otherwise (the contributed windows) the first block keeps its stock place, 51 rows into the window."""
    inside, unclear = G.pdaf_blocks(row, height)
    rows_read = height + 12
    if margin_rule:
        k = inside[0]
        assert not unclear and len(inside) == p and row % 4 == 2 and rows_read % 4 == 0, (inside[0], inside[-1], len(inside), unclear)
    else:
        k = (row - 406) // 48 + 9 if not line360_own else (row - 502) // 48 + 11      # the first block keeps its place in the window (row + 51)
        assert 25 + 48 * k - row == 51, "the first phase-detect row is not 51 rows into the window, as in the stock windows"
        assert rows_read % 16 == 0
    f2 = (p + 16) // 2 if line360_own else (p + 14) // 2
    ro6 = rows_read // 2 + (25 if line360_own else 24)
    assert p % 2 == 0 and row - 6 + rows_read <= SENSOR_ROWS_END
    facts = {"window": [5952 if not line360_own else 5612, height], "window_row": row, "rows_read": rows_read, "rows_read_from": row - 6, "rows_read_end": row - 6 + rows_read,
             "pdaf_rows": p, "first_block": k, "first_pdaf_row": 25 + 48 * k, "f2": f2, "readout_length": ro6,
             "blocks_inside_by_the_stock_rule": [inside[0], inside[-1], len(inside)], "blocks_unclear_by_the_stock_rule": unclear,
             "last_block_carried": k + p - 1, "last_block_row": 25 + 48 * (k + p - 1), "rows_from_the_last_block_to_the_end_of_the_rows_read": row - 6 + rows_read - (25 + 48 * (k + p - 1))}
    cells = []
    ids = list(struct.unpack_from("<%dI" % NMODES, X, IDS - B))
    names = {CROP: "crop", S0: "stream-0", S1: "stream-1 (phase detect)", LC: "LC", RO: "read-out"}
    edits = {CROP: {3: (row, "window row"), 9: (k, "first phase-detect block")}, S0: {13: (height, "window height")}, S1: {13: (p, "phase-detect rows")},
             LC: {4: (row, "window row"), 6: (25 + 48 * k, "first phase-detect row")}, RO: {2: (f2, "f2"), 6: (ro6, "read-out length in line periods")}}
    for i in modes_idx:
        m = ids[i]
        a = geo_addrs[m] + 10
        cells.append((a, rd(a, 2), struct.pack("<H", row), f"geometry table, mode {m:#x}: window row {u16(X, a - B)} -> {row}"))
        for tbl, ed in edits.items():
            for f, (v, what) in ed.items():
                a = tbl[0] + tbl[1] * i + 2 * f
                cells.append((a, rd(a, 2), struct.pack("<H", v), f"{names[tbl]} table, mode {m:#x}, field {f}: {what} {u16(X, a - B)} -> {v}"))
    start = row + 81
    for r, v, what in ((M_START_LO, start & 0xFF, "first row + 81, low byte"), (M_START_HI, start >> 8, "first row + 81, high byte"),
                       (M_HALF_LO, (rows_read // 2) & 0xFF, "half the rows read, low byte"), (M_HALF_HI, (rows_read // 2) >> 8, "half the rows read, high byte"),
                       (M_PD_FIRST, k, "first phase-detect block"), (M_PD_HALF, p // 2, "half the phase-detect rows"), (M_F2, f2, "read-out lead f2")):
        a = MATRIX + MROW * r + 4 + column
        if X[a - B] != v:
            cells.append((a, rd(a, 1), bytes([v]), f"register matrix row {r}, column {column}: {what} {X[a - B]} -> {v}"))
    cells.sort()
    assert all(a + len(o) <= b for (a, o, _, _), (b, _, _, _) in zip(cells, cells[1:])) and all(o != n and len(o) == len(n) for _, o, n, _ in cells)
    return cells, facts


def stored(cells_by_design):
    """The stored records from the A6700's own calculator: {system: {design or 'stock': {mode: record}}}; NTSC = the 60 Hz timing table, PAL = the 50 Hz one."""
    f = E.CONSTS[BUILD]["fields"]
    pal = [(f[0x2C], rd(f[0x30], 24 * NMODES))]
    out = {}
    for system, base in (("ntsc", []), ("pal", pal)):
        st, log = E.records(BUILD, base)
        assert not log and all(v[2] is None for v in st.values())
        out[system] = {"stock": {m: v[1] for m, v in st.items()}}
        for name, cells in cells_by_design.items():
            de, log = E.records(BUILD, base + [(a, n) for a, _, n, _ in cells])
            assert not log and all(v[2] is None for v in de.values())
            out[system][name] = {m: v[1] for m, v in de.items()}
    return out


def records_pair(M, rules, base, frm, to, frame_w, crop_w):
    mod = G.apply_rules(rules, base, frm, to)
    rows = to[0]
    got, _ = G.N.assemble(M, mod, OUT, frame=(frame_w, rows), crop=(12, 4, crop_w, rows - 8), mirror_as=base)
    return got


def compare_patches(mine, theirs, what):
    """our cells/records against the contributed kit's patches: (equal count, [ours only], [theirs only or different])"""
    t = {int(p["addr"], 16): (bytes.fromhex(p["old"]), bytes.fromhex(p["new"])) for p in theirs}
    m = {a: (o, n) for a, o, n, _ in mine}
    same = [a for a in m if t.get(a) == m[a]]
    ours_only = [a for a in m if a not in t]
    differ = [a for a in t if a not in m or t[a] != m[a]]
    print(f"  {what}: {len(same)} of the contributed kit's {len(t)} patches are byte-equal to ours; ours has {len(ours_only)} more; {len(differ)} of theirs differ or are missing here")
    return {"equal": len(same), "theirs": len(t), "ours_only": [hex(a) for a in ours_only], "theirs_differ_or_missing_here": [hex(a) for a in differ]}


# ---------------------------------------------------------------- the sensor-side designs

def sensor_designs():
    ids, idx, i50, geo, col, facts = check_sensor_facts()
    cells, sfacts = window_cells(idx, geo, 1, NEW_ROW, NEW_H, NEW_P, False)
    cells50, sfacts50 = window_cells([i50], geo, 2, ROW50, H50, P50, True)
    assert not {a for a, _, _, _ in cells} & {a for a, _, _, _ in cells50}
    # the picture records: the FX30 builder's row model (fitted here on the A6700's own three pairs) and build_fhnative's planner and packers
    M = G.F.Model(G.A)
    rules, column_like = G.fit_rules(M)
    p8, pd, p3 = G.pair(PAIR), G.pair(DCI), G.pair(P830)
    selftest = {}
    for name, base, frm, want, to, fw, cw, target in (("dci_from_3356_pair", p8, GEOM["8c0"], pd, GEOM["dci"], 5976, 5952, (4624, 2438)),
                                                      ("3356_pair_from_dci", pd, GEOM["dci"], p8, GEOM["8c0"], 5976, 5952, OUT),
                                                      ("830_pair_from_itself", p3, GEOM["830"], p3, GEOM["830"], 5636, 5612, OUT)):
        mod = G.apply_rules(rules, base, frm, to)
        got, _ = G.N.assemble(M, mod, target, frame=(fw, to[0]), crop=(12, 4, cw, to[0] - 8), mirror_as=base)
        selftest[name] = {h: [hex(o) for o in range(0, SIZE, 2) if got[h][o:o + 2] != want[h][o:o + 2]] for h in "LR"}
        print(f"self-test {name}: fields that differ L {len(selftest[name]['L'])} R {len(selftest[name]['R'])}")
    # +0x5ac follows the output shape (4096 for a 16:9 output, another value for the DCI output): see build_og_fx30.py
    assert selftest["dci_from_3356_pair"] == {"L": ["0x5ac"], "R": ["0x5ac"]} == selftest["3356_pair_from_dci"] and selftest["830_pair_from_itself"] == {"L": [], "R": []}
    new = (NEW_H + 8, NEW_P, sfacts["f2"], NEW_ROW)
    new50 = (H50 + 8, P50, sfacts50["f2"], ROW50)
    rec = records_pair(M, rules, p8, GEOM["8c0"], new, 5976, 5952)
    rec50 = records_pair(M, rules, p3, GEOM["830"], new50, 5636, 5612)
    out = {}
    for name, r, stock, at, n, row in (("ogsq", rec, p8, PAIR, new, NEW_ROW), ("ogsq50", rec50, p3, P830, new50, ROW50)):
        lint, _ = G.LINT.lint_design_records(r["L"], r["R"])
        broken = {k: d for k, (ok, d) in lint.items() if not ok}
        assert not broken, (name, broken)
        lrc = {}
        for h in "LR":
            k = G.LINT.lrc(r[h])
            lrc[h] = {"input": list(k["in"]), "output": list(k["out"]), "step_q12": list(k["step"]), "start": list(k["start"])}
            assert k["in"][1] == n[0] and u16(r[h], 0x95E) == row and tuple(k["out"]) == tuple(G.LINT.lrc(stock[h])["out"])
            assert r[h][0x174:0x1D8] == stock[h][0x174:0x1D8], "something after the first stage moved"
        out[name] = {"records": [(at[h], stock[h], bytes(r[h]), h) for h in "LR"], "lrc": lrc,
                     "fields": {h: sum(r[h][x:x + 2] != stock[h][x:x + 2] for x in range(0, SIZE, 2)) for h in "LR"}}
    st = stored({"ogsq": cells, "ogsq50": cells50})
    for system in st:                                           # each design changes the records of its own modes and no other
        ch = lambda name: sorted(m for m in st[system]["stock"] if st[system]["stock"][m] != st[system][name][m])
        assert ch("ogsq") == sorted(MODES) and ch("ogsq50") == [MODE50], (system, [hex(m) for m in ch("ogsq")], [hex(m) for m in ch("ogsq50")])
    theirs = contrib("ogsq_a6700_v1")
    against = {}
    # ---- ogsq_a6700_v1
    variants, rec_ev = {}, {}
    for m in MODES:
        variants[m] = {}
        for system in ("ntsc", "pal"):
            s, d = bytearray(st[system]["stock"][m]), bytearray(st[system]["ogsq"][m])
            assert s[4:8] == b"\x01\x01\x01\x01" and len(s) == 0x170
            d[6], d[7] = PAV
            ex = (u16(d, 0x66), u16(d, 0x8C))
            assert ex == (NEW_H, NEW_P), (hex(m), system, ex)
            variants[m][system] = (bytes(s), bytes(d))
    offs = sorted({k for m in MODES for s, d in variants[m].values() for k in range(0x170) if s[k] != d[k]})
    assert offs[:2] == [6, 7] and 2 < len(offs) <= 128
    stored_out = {}
    for m in MODES:
        pick = lambda b: bytes(b[k] for k in offs)
        sets = [pick(variants[m][sy][j]) for sy in ("ntsc", "pal") for j in (0, 1)]
        assert len(set(sets)) == 4, f"{m:#x}: the NTSC/PAL stock/new byte sets are not all different at the sites"
        stored_out[hex(m)] = {"index": ids.index(m), "offsets_that_differ": [hex(k) for k in offs],
                              **{sy: {"stock": variants[m][sy][0].hex(), "design": variants[m][sy][1].hex()} for sy in ("ntsc", "pal")}}
        rec_ev[hex(m)] = {sy: {hex(k): [u16(variants[m][sy][0], k), u16(variants[m][sy][1], k)] for k in range(0, 0x170, 2)
                               if variants[m][sy][0][k:k + 2] != variants[m][sy][1][k:k + 2]} for sy in ("ntsc", "pal")}
    sites = [{"kind": "S", "addr": hex(a), "old": o.hex(), "new": n.hex(), "where": "file", "note": note} for a, o, n, note in cells]
    for a, stock, new_, h in out["ogsq"]["records"]:
        sites.append({"kind": "R", "addr": hex(a), "old": stock.hex(), "new": new_.hex(), "where": "file",
                      "note": f"{'left' if h == 'L' else 'right'} picture record of modes 0x820/0x880/0x890/0x8c0/0x8d0: first stage {new[0]} rows (crop 5952 x {NEW_H}), "
                              f"squeezed by Lrc into the stock {OUT[0]} x {OUT[1]} front end; {out['ogsq']['fields'][h]} fields differ"})
    sites.sort(key=lambda s: int(s["addr"], 16))
    if theirs:
        mine = cells + [(a, s, n, "") for a, s, n, _ in out["ogsq"]["records"]]
        t_main = [p for p in theirs["patches"] if p["kind"] in ("S", "R")]
        against["patches"] = compare_patches(mine, t_main, "ogsq_a6700_v1 (cells and picture records)")
        extra = [next(n for a, _, _, n in cells if a == int(x, 16)) for x in against["patches"]["ours_only"]]
        assert against["patches"]["equal"] == len(t_main) == 35 and not against["patches"]["theirs_differ_or_missing_here"]
        assert len(extra) == 18 and all("0x890" in n or "0x8d0" in n for n in extra), "ours differs from theirs in more than the rows of 0x890 and 0x8d0"
        against["patches"]["ours_only_are"] = "the nine table cells of mode 0x890 and of mode 0x8d0, which the contributed kit leaves stock"
        sr, cmp_ = theirs["stored_records"], {}
        for tag, m, sy in (("ntsc_24p", 0x8C0, "ntsc"), ("pal_50p", 0x820, "pal"), ("pal_25p", 0x880, "pal"), ("pal_08c0", 0x8C0, "pal")):
            to_ = [int(x, 16) for x in sr[tag]["offsets_that_differ"]]
            ts, td = bytes.fromhex(sr[tag]["stock"]), bytes.fromhex(sr[tag]["design"])
            ms, md = variants[m][sy]
            cmp_[tag] = {"mode": hex(m), "system": sy, "whole_stock_record_equal": ts == ms, "whole_design_record_equal": td == md,
                         "their_offsets": len(to_), "their_offsets_all_in_ours": set(to_) <= set(offs),
                         "equal_at_our_offsets": all(ts[k] == ms[k] and td[k] == md[k] for k in offs)}
            assert cmp_[tag]["equal_at_our_offsets"] and cmp_[tag]["their_offsets_all_in_ours"], (tag, cmp_[tag])
        against["stored_records"] = cmp_
        against["stored_records_ours_only"] = "NTSC records of 0x820, 0x880, 0x890, 0x8d0 and PAL records of 0x890, 0x8d0 (the contributed kit writes none of them)"
        print("  stored records: the contributed kit's four (NTSC 0x8c0; PAL 0x820, 0x880, 0x8c0) equal ours at every site offset:",
              {k: (v["whole_stock_record_equal"], v["whole_design_record_equal"]) for k, v in cmp_.items()})
    design = {"design": "ogsq_a6700_v1", "build": BUILD, "camera": "ILCE-6700, firmware 2.00",
              "title": f"A6700 open gate, sensor side: 5952 x {NEW_H} window from row {NEW_ROW} in modes 0x820/0x880/0x890/0x8c0/0x8d0, first stage 5976 x {new[0]} "
                       f"squeezed into the stock {OUT[0]} x {OUT[1]} front end, vertical sampling ratio {PAV[0]}/{PAV[1]}",
              "artifact": "cpapp-b.bin", "artifact_sha256": SHA, "generated_by": "build/build_og_a6700.py",
              "ported_from": {"design": "ogsq_v3 / ogsq_fx30_v1", "how": "the A7 IV's mechanism (taller window, Lrc squeeze, sampling ratio) with the window a contributor chose for the "
                              "A6700 (work/contrib/a6700_v1.0), every byte derived again from the A6700's files with the FX30 port's tools"},
              "modes": [hex(m) for m in MODES], "mode_indices": idx,
              "summary": {"window": [5952, NEW_H], "window_row": NEW_ROW, "stock_window": [5952, 3348], "stock_window_row": 406, "first_stage": [5976, new[0]],
                          "front_end": list(OUT), "pdaf": sfacts, "lrc": out["ogsq"]["lrc"], "record_fields_changed": out["ogsq"]["fields"],
                          "sites": len(sites), "bytes": sum(len(s["old"]) // 2 for s in sites), "sensor_cells": len(cells), "records": 2,
                          "picture_aspect": round(5952 / NEW_H, 4), "file_aspect": 1.5,
                          "aspect_note": f"the window is 5952:{NEW_H} = {5952 / NEW_H:.4f}, the 3840 x 2560 file 1.5: shown at 1:1 pixels the picture is "
                                         f"{(5952 / NEW_H / 1.5 - 1) * 100:.2f} % too tall (a circle is that much higher than wide)",
                          "expected_working_state": {"crop": [5952, NEW_H], "front_end": list(OUT), "second_scaler_takes": "the whole front end", "file": [3840, 2560]}},
              "patches": sites, "record_size": 0x170, "stored_records": stored_out,
              "stored_record_note": "RAM, filled by the camera at start-up from the tables (60 Hz table on NTSC, 50 Hz on PAL); records base = the drive-parameter "
                                    "object's +0x10 (0x25dabcc in the file's table map) + index x 0x170; the write level finds each record through the pointer chain "
                                    "and takes the variant all five hold",
              "stored_record_extra": [{"offset": "0x6", "old": "01", "new": "%02x" % PAV[0], "note": "vertical sampling ratio, numerator"},
                                      {"offset": "0x7", "old": "01", "new": "%02x" % PAV[1], "note": "vertical sampling ratio, denominator"}],
              "against_the_contributed_kit": against or "the contributed kit is not on disk: not compared",
              "evidence": ["evidence/a6700/sensor/ogsq_a6700_v1_selftest.json", "evidence/a6700/sensor/ogsq_a6700_v1_stored_records_emu.json",
                           "evidence/a6700/sensor/rc_fit_a6700_emu.json (build/emu_rc_fit_a6700.py)"]}
    write("ogsq_a6700_v1", design)
    # ---- ogsq50_a6700_v1 (mode 0x830, PAL)
    v50 = {}
    for system in ("ntsc", "pal"):
        s, d = bytearray(st[system]["stock"][MODE50]), bytearray(st[system]["ogsq50"][MODE50])
        assert s[4:8] == b"\x01\x01\x01\x01"
        d[6], d[7] = PAV50
        assert (u16(d, 0x66), u16(d, 0x8C)) == (H50, P50)
        v50[system] = (bytes(s), bytes(d))
    offs50 = [k for k in range(0x170) if v50["pal"][0][k] != v50["pal"][1][k]]
    pick = lambda b: bytes(b[k] for k in offs50)
    refuses_on_ntsc = pick(v50["ntsc"][0]) not in (pick(v50["pal"][0]), pick(v50["pal"][1]))
    assert refuses_on_ntsc and offs50[:2] == [6, 7], "an NTSC camera's 0x830 record would pass for the PAL one at the sites"
    ntsc_differs_at = [hex(k) for k in offs50 if v50["ntsc"][0][k] != v50["pal"][0][k]]
    sites50 = [{"kind": "S", "addr": hex(a), "old": o.hex(), "new": n.hex(), "where": "file", "note": note} for a, o, n, note in cells50]
    for a, stock, new_, h in out["ogsq50"]["records"]:
        sites50.append({"kind": "R", "addr": hex(a), "old": stock.hex(), "new": new_.hex(), "where": "file",
                        "note": f"{'left' if h == 'L' else 'right'} picture record of mode 0x830: first stage {new50[0]} rows (crop 5612 x {H50}), squeezed by Lrc into "
                                f"the stock {OUT[0]} x {OUT[1]} front end; {out['ogsq50']['fields'][h]} fields differ"})
    sites50.sort(key=lambda s: int(s["addr"], 16))
    against50 = {}
    if theirs:
        mine = cells50 + [(a, s, n, "") for a, s, n, _ in out["ogsq50"]["records"]]
        t50 = [p for p in theirs["patches"] if p["kind"] in ("S2", "R2")]
        against50["patches"] = compare_patches(mine, t50, "ogsq50_a6700_v1 (cells and picture records)")
        assert against50["patches"]["equal"] == len(t50) == len(mine) == 18
        t = theirs["stored_records"]["pal_50p_0830"]
        ts, td = bytes.fromhex(t["stock"]), bytes.fromhex(t["design"])
        against50["stored_record"] = {"whole_stock_record_equal": ts == v50["pal"][0], "whole_design_record_equal": td == v50["pal"][1],
                                      "offsets_equal": [int(x, 16) for x in t["offsets_that_differ"]] == offs50,
                                      "equal_at_our_offsets": all(ts[k] == v50["pal"][0][k] and td[k] == v50["pal"][1][k] for k in offs50)}
        assert against50["stored_record"]["equal_at_our_offsets"] and against50["stored_record"]["offsets_equal"], against50
        print("  stored record of 0x830 (PAL): equal to the contributed kit's at every site offset:", against50["stored_record"])
    design50 = {"design": "ogsq50_a6700_v1", "build": BUILD, "camera": "ILCE-6700, firmware 2.00",
                "title": f"A6700 open gate at 50p (PAL), sensor side: 5612 x {H50} window from row {ROW50} in mode 0x830, first stage 5636 x {new50[0]} squeezed into "
                         f"the stock {OUT[0]} x {OUT[1]} front end, vertical sampling ratio {PAV50[0]}/{PAV50[1]}",
                "artifact": "cpapp-b.bin", "artifact_sha256": SHA, "generated_by": "build/build_og_a6700.py",
                "ported_from": {"design": "the 0x830 part of the contributed ogsq_a6700_v1", "how": "derived again as ogsq_a6700_v1 is; a design of its own so that it is a step of its own"},
                "mode_id": hex(MODE50), "mode_index": i50,
                "summary": {"window": [5612, H50], "window_row": ROW50, "stock_window": [5612, 3156], "stock_window_row": 502, "first_stage": [5636, new50[0]],
                            "front_end": list(OUT), "pdaf": sfacts50, "lrc": out["ogsq50"]["lrc"], "record_fields_changed": out["ogsq50"]["fields"],
                            "sites": len(sites50), "bytes": sum(len(s["old"]) // 2 for s in sites50), "sensor_cells": len(cells50), "records": 2,
                            "picture_aspect": round(5612 / H50, 4), "file_aspect": 1.5,
                            "timing": "the 50 Hz table gives mode 0x830 a frame of 4,000 half line periods = 2,000 line periods (20 ms); the read-out takes "
                                      f"{sfacts50['readout_length']} of them. The 60 Hz table gives 1,666: the read-out would not fit (no 59.94p)"},
                "patches": sites50, "record_size": 0x170,
                "stored_record": {"mode": hex(MODE50), "index": i50, "system": "PAL (50 Hz table)", "stock": v50["pal"][0].hex(), "design": v50["pal"][1].hex(),
                                  "offsets_that_differ": [hex(k) for k in offs50]},
                "stored_record_ntsc": {"stock": v50["ntsc"][0].hex(), "site_offsets_where_it_differs_from_the_pal_record": ntsc_differs_at,
                                       "write_level_on_ntsc": "finds neither the stock nor the new bytes at the record's sites in pass 1 and writes nothing"},
                "stored_record_extra": [{"offset": "0x6", "old": "01", "new": "%02x" % PAV50[0], "note": "vertical sampling ratio, numerator"},
                                        {"offset": "0x7", "old": "01", "new": "%02x" % PAV50[1], "note": "vertical sampling ratio, denominator"}],
                "against_the_contributed_kit": against50 or "the contributed kit is not on disk: not compared",
                "evidence": ["evidence/a6700/sensor/ogsq_a6700_v1_selftest.json", "evidence/a6700/sensor/ogsq_a6700_v1_stored_records_emu.json"]}
    write("ogsq50_a6700_v1", design50)
    EV.mkdir(parents=True, exist_ok=True)
    (EV / "ogsq_a6700_v1_selftest.json").write_text(json.dumps({
        "about": "build/build_og_a6700.py: what the image holds (asserted), and the row model's self-test: fitted on the A6700's pairs 0xd3885c (3356 rows), "
                 "0xd3597c (3148 rows, DCI) and 0xd39fcc (3164 rows), with build_fhnative.assemble it rebuilds each real pair from another",
        "image_facts": facts, "rules": {h: {hex(o): f"{k[0]}*{k[1]}" for o, k in sorted(rules[h].items())} for h in "LR"},
        "fields_left_stock_column_or_output_dependent": {h: [hex(o) for o in v] for h, v in column_like.items()},
        "rebuilds": selftest, "exact": True}, indent=1) + "\n", encoding="utf8", newline="\n")
    (EV / "ogsq_a6700_v1_stored_records_emu.json").write_text(json.dumps({
        "about": "Stored drive-parameter records (0x170 bytes) from the A6700's own calculator 0x3910e8 (build/emu_drvparam.py a6700_200), stock and with the "
                 "designs' cells, plus the vertical sampling ratio at +6/+7, with the 60 Hz (ntsc) and the 50 Hz (pal) timing table. Words that change, per mode.",
        "records_base_in_emulation": hex(E.CONSTS[BUILD]["fields"][0x10]), "record_bytes": 0x170, "ogsq_a6700_v1": rec_ev,
        "ogsq50_a6700_v1": {sy: {hex(k): [u16(v50[sy][0], k), u16(v50[sy][1], k)] for k in range(0, 0x170, 2) if v50[sy][0][k:k + 2] != v50[sy][1][k:k + 2]} for sy in v50}},
        indent=1) + "\n", encoding="utf8", newline="\n")
    for system in ("ntsc", "pal"):                                # the stock records of both systems, in emu_drvparam.py's --json format
        (EV / f"drvparam_stock_a6700_200{'' if system == 'ntsc' else '_pal'}.json").write_text(json.dumps({
            "build": BUILD, "system": system, "timing_table": "0xdc831c (60 Hz)" if system == "ntsc" else "0xdc8604 (50 Hz) in place of 0xdc831c",
            "image_patches": [], "log": [], "modes": {hex(m): {"index": ids.index(m), "error": None, "record": r.hex()} for m, r in st[system]["stock"].items()}},
            indent=1) + "\n", encoding="utf8", newline="\n")
    print(f"ogsq_a6700_v1: {len(sites)} sites ({len(cells)} cells, 2 records), {design['summary']['bytes']} bytes; {len(offs)} bytes of each of 5 stored records, 2 variants")
    print(f"ogsq50_a6700_v1: {len(sites50)} sites ({len(cells50)} cells, 2 records), {design50['summary']['bytes']} bytes; {len(offs50)} bytes of the stored record; "
          f"an NTSC record differs from the PAL stock at site offsets {ntsc_differs_at}")
    print("  phase-detect, 4K window:", {k: sfacts[k] for k in ("pdaf_rows", "first_block", "blocks_inside_by_the_stock_rule", "last_block_carried", "rows_from_the_last_block_to_the_end_of_the_rows_read")})
    print("  phase-detect, 50p window:", {k: sfacts50[k] for k in ("pdaf_rows", "first_block", "blocks_inside_by_the_stock_rule", "last_block_carried", "rows_from_the_last_block_to_the_end_of_the_rows_read")})
    return new


# ---------------------------------------------------------------- the exact 3:2 window (a test design of our own)

ROW32, H32, P32, PAV32 = 94, 3968, 82, (27, 32)


def sensor_design_32():
    """ogsq32_a6700_v1: the same five modes with the window 5952 x 3968 (exactly 3:2) from row 94, the FX30 kit's ogsq_fx30_v2 window on
    the same sensor family. NOT from the contributed kit, whose window (5952 x 3876) makes the 3840 x 2560 picture 2.37 % too tall. The
    first block and the block count follow the stock windows' margin rule (82 blocks from block 2); the vertical sampling ratio is 27/32
    (3968 x 27/32 = 3348 exactly). The first-row register becomes 175: its high byte is 0, which no stock movie window has."""
    ids, idx, i50, geo, col, facts = check_sensor_facts()
    cells, sfacts = window_cells(idx, geo, 1, ROW32, H32, P32, False, margin_rule=True)
    M = G.F.Model(G.A)
    rules, _ = G.fit_rules(M)
    p8 = G.pair(PAIR)
    new = (H32 + 8, P32, sfacts["f2"], ROW32)
    assert new[0] <= RAW_ROWS_NEW, "the first stage does not fit the raw write buffer of dmmwb_a6700_v1"
    rec = records_pair(M, rules, p8, GEOM["8c0"], new, 5976, 5952)
    lint, _ = G.LINT.lint_design_records(rec["L"], rec["R"])
    broken = {k: d for k, (ok, d) in lint.items() if not ok}
    assert not broken, broken
    lrc, fields = {}, {}
    for h in "LR":
        k = G.LINT.lrc(rec[h])
        lrc[h] = {"input": list(k["in"]), "output": list(k["out"]), "step_q12": list(k["step"]), "start": list(k["start"])}
        assert k["in"][1] == new[0] and u16(rec[h], 0x95E) == ROW32 and tuple(k["out"]) == tuple(G.LINT.lrc(p8[h])["out"])
        assert rec[h][0x174:0x1D8] == p8[h][0x174:0x1D8], "something after the first stage moved"
        fields[h] = sum(rec[h][x:x + 2] != p8[h][x:x + 2] for x in range(0, SIZE, 2))
    st = stored({"ogsq32": cells})
    variants = {}
    for system in st:
        ch = sorted(m for m in st[system]["stock"] if st[system]["stock"][m] != st[system]["ogsq32"][m])
        assert ch == sorted(MODES), (system, [hex(m) for m in ch])
    for m in MODES:
        variants[m] = {}
        for system in ("ntsc", "pal"):
            s, d = bytearray(st[system]["stock"][m]), bytearray(st[system]["ogsq32"][m])
            assert s[4:8] == b"\x01\x01\x01\x01" and len(s) == 0x170
            d[6], d[7] = PAV32
            assert (u16(d, 0x66), u16(d, 0x8C)) == (H32, P32), (hex(m), system)
            variants[m][system] = (bytes(s), bytes(d))
    offs = sorted({k for m in MODES for s, d in variants[m].values() for k in range(0x170) if s[k] != d[k]})
    assert offs[:2] == [6, 7] and 2 < len(offs) <= 128
    stored_out = {}
    for m in MODES:
        pick = lambda b: bytes(b[k] for k in offs)
        sets = [pick(variants[m][sy][j]) for sy in ("ntsc", "pal") for j in (0, 1)]
        assert len(set(sets)) == 4, f"{m:#x}: the NTSC/PAL stock/new byte sets are not all different at the sites"
        stored_out[hex(m)] = {"index": ids.index(m), "offsets_that_differ": [hex(k) for k in offs],
                              **{sy: {"stock": variants[m][sy][0].hex(), "design": variants[m][sy][1].hex()} for sy in ("ntsc", "pal")}}
    sites = [{"kind": "S", "addr": hex(a), "old": o.hex(), "new": n.hex(), "where": "file", "note": note} for a, o, n, note in cells]
    for h in "LR":
        sites.append({"kind": "R", "addr": hex(PAIR[h]), "old": p8[h].hex(), "new": bytes(rec[h]).hex(), "where": "file",
                      "note": f"{'left' if h == 'L' else 'right'} picture record of modes 0x820/0x880/0x890/0x8c0/0x8d0: first stage {new[0]} rows (crop 5952 x {H32}), "
                              f"squeezed by Lrc into the stock {OUT[0]} x {OUT[1]} front end; {fields[h]} fields differ"})
    sites.sort(key=lambda s: int(s["addr"], 16))
    # the same places as ogsq_a6700_v1 (so the two refuse each other and one check reads both), and at least one byte differs at each
    other = json.loads((DES / "ogsq_a6700_v1.json").read_text(encoding="utf8"))
    o_sites = {p["addr"]: p["new"] for p in other["patches"]}
    mine = {s["addr"]: s["new"] for s in sites}
    assert set(o_sites) <= set(mine), "ogsq_a6700_v1 changes a place this design leaves alone"
    extra = sorted(set(mine) - set(o_sites))                   # here: the high byte of the first-row register, which ogsq_a6700_v1 keeps at 1
    same_new = [a for a in o_sites if o_sites[a] == mine[a]]
    assert len(same_new) < len(o_sites) // 2, "too many places with the same new bytes: the two designs could pass for each other"
    design = {"design": "ogsq32_a6700_v1", "build": BUILD, "camera": "ILCE-6700, firmware 2.00",
              "title": f"A6700 open gate with the exact 3:2 window, sensor side (a TEST design): 5952 x {H32} from row {ROW32} in modes 0x820/0x880/0x890/0x8c0/0x8d0, "
                       f"first stage 5976 x {new[0]} squeezed into the stock {OUT[0]} x {OUT[1]} front end, vertical sampling ratio {PAV32[0]}/{PAV32[1]}",
              "artifact": "cpapp-b.bin", "artifact_sha256": SHA, "generated_by": "build/build_og_a6700.py",
              "ported_from": {"design": "ogsq_fx30_v2", "build": "fx30_601", "how": "the FX30 kit's window on the same sensor family (not run on an FX30 either), every byte derived from "
                              "the A6700's files as ogsq_a6700_v1 is. Not part of the contributed kit."},
              "modes": [hex(m) for m in MODES], "mode_indices": idx,
              "summary": {"window": [5952, H32], "window_row": ROW32, "stock_window": [5952, 3348], "stock_window_row": 406, "first_stage": [5976, new[0]],
                          "front_end": list(OUT), "pdaf": sfacts, "lrc": lrc, "record_fields_changed": fields,
                          "sites": len(sites), "bytes": sum(len(s["old"]) // 2 for s in sites), "sensor_cells": len(cells), "records": 2,
                          "picture_aspect": round(5952 / H32, 4), "file_aspect": 1.5,
                          "first_row_register": {"stock": 406 + 81, "ogsq_a6700_v1": NEW_ROW + 81, "this": ROW32 + 81,
                                                 "note": "its high byte (matrix row 4) becomes 0; every stock movie window has 1, 2 or 3 there"},
                          "rows_read": {"stock": 3360, "ogsq_a6700_v1": NEW_H + 12, "this": H32 + 12, "ends_at_row": ROW32 - 6 + H32 + 12, "limit_in_stock_modes": SENSOR_ROWS_END},
                          "against_ogsq_a6700_v1": {"its_places_all_here": True, "places_only_here": extra, "places_with_the_same_new_bytes": same_new},
                          "expected_working_state": {"crop": [5952, H32], "front_end": list(OUT), "second_scaler_takes": "the whole front end", "file": [3840, 2560]}},
              "patches": sites, "record_size": 0x170, "stored_records": stored_out,
              "stored_record_extra": [{"offset": "0x6", "old": "01", "new": "%02x" % PAV32[0], "note": "vertical sampling ratio, numerator"},
                                      {"offset": "0x7", "old": "01", "new": "%02x" % PAV32[1], "note": "vertical sampling ratio, denominator"}],
              "not_shown": ["anything on a camera: neither this window on an A6700 nor ogsq_fx30_v2 on an FX30 has run",
                            "that the sensor takes a first-row register below 256 and 3,980 rows at this line rate"],
              "evidence": ["evidence/a6700/sensor/rc_fit_a6700_emu.json (build/emu_rc_fit_a6700.py)"]}
    write("ogsq32_a6700_v1", design)
    print(f"ogsq32_a6700_v1: {len(sites)} sites ({len(cells)} cells, 2 records), {design['summary']['bytes']} bytes; {len(offs)} bytes of each of 5 stored records, 2 variants; "
          f"places only here: {extra}; places whose new bytes equal ogsq_a6700_v1's: {same_new}")
    print("  phase-detect, 3:2 window:", {k: sfacts[k] for k in ("pdaf_rows", "first_block", "first_pdaf_row", "blocks_inside_by_the_stock_rule", "last_block_carried", "f2", "readout_length")})
    return new


# ---------------------------------------------------------------- the raw write buffer

def dmm_design(stage_rows):
    KEY, MEM_ID, NEW, STOCK = 0x57F, 0x43E, RAW_PITCH * RAW_ROWS_NEW, RAW_PITCH * RAW_ROWS_STOCK
    D.use_build(BUILD)
    cfg = P.Config(P.find_file(BUILD), BUILD)
    units = cfg.units_by_key[KEY]
    assert cfg.ids_by_key[KEY] == [MEM_ID] and len(units) == 4 and all(u["size"] == STOCK for u in units) and NEW % 128 == 0
    groups = {}
    for u in units:
        groups.setdefault(u["group"]["gid"], []).append(u)
    assert sorted(groups) == [0x8A, 0x8E] and len(groups[0x8A]) == 3 and len(groups[0x8E]) == 1
    g8a, g8e = groups[0x8A][0]["group"], groups[0x8E][0]["group"]
    assert g8a["parent"] == 0x6FA and [x["key"] for x in g8a["units"]] == [KEY] * 3
    assert g8e["parent"] == 0x74D and [x["key"] for x in g8e["units"]] == [KEY, 0x634, 0x634, 0x635, 0x635, 0x2DA]
    need = {0x8A: 3 * NEW, 0x8E: NEW + sum(x["size"] for x in g8e["units"][1:])}
    parent = {0x6FA: min(cfg.parent_sizes(0x6FA)), 0x74D: min(cfg.parent_sizes(0x74D))}
    assert need[0x8A] <= parent[0x6FA] and need[0x8E] <= parent[0x74D], (need, parent)
    assert stage_rows * RAW_PITCH <= NEW
    rec = lambda u: cfg.ram("unit_records", u["seq"] * 0x14)
    sites = [{"ram_address": hex(rec(u) + 12), "what": f"size of a key {KEY:#x} record of group {u['group']['gid']:#x} (parent key {u['group']['parent']:#x})",
              "file_offset_of_the_same_field": hex(u["at"] + 12), "old": struct.pack("<I", STOCK).hex(), "new": struct.pack("<I", NEW).hex(),
              "old_value": STOCK, "new_value": NEW} for u in units]
    parents = [{"ram_address": hex(rec(u)), "key": hex(u["key"]), "size": u["size"], "file_hex": cfg.data[u["at"]:u["at"] + 0x14].hex()}
               for k in (0x6FA, 0x74D) for u in cfg.units_by_key[k]]
    recs = [{"ram_address": hex(rec(u)), "site_off": 12, "file_hex": cfg.data[u["at"]:u["at"] + 0x14].hex()} for u in units]
    busy = sorted({x["key"] for g in (g8a, g8e) for x in g["units"]} - {0x2DA})
    assert busy == [0x57F, 0x634, 0x635] and all(len(cfg.units_by_key[k]) == (4 if k == KEY else 2) for k in busy)      # 0x634, 0x635 exist in group 0x8e only

    def run(plan, apply_first=True):
        s = D.Server(cfg.data, cfg)
        assert s.init() == 0 and s.cur == len(cfg.data) and not s.fatal
        assert all(s.u32(int(x["ram_address"], 16)) == STOCK for x in sites), "the RAM copy is not where parse_dmmcfg.RAM says"
        if apply_first:
            for gid in groups:
                s.set_size(KEY, gid, NEW)
            assert all(bytes(s.uc.mem_read(int(x["ram_address"], 16), 4)).hex() == x["new"] for x in sites)
        out = []
        for step in plan:
            if step == "apply":
                for gid in groups:
                    s.set_size(KEY, gid, NEW)
                out.append({"step": "apply"})
            elif step[0] == "open":
                out.append(s.open(step[1]))
            else:
                out.append(s.free(step[1]))
        return s, out

    n_open = 8
    plan = [("open", MEM_ID)] * n_open + [("open", 0x4B7), ("open", 0x4B8)]
    s, res = run(plan)
    s0, res0 = run(plan, apply_first=False)
    ok = [o for o in res[:n_open] if o["ok"]]
    ok0 = [o for o in res0[:n_open] if o["ok"]]
    assert ok and len(ok) == len(ok0) and all([x["size"] for x in o["extents"]] == [NEW] for o in ok) and all([x["size"] for x in o["extents"]] == [STOCK] for o in ok0)
    spans = sorted((int(x["address"], 16), int(x["address"], 16) + x["size"]) for o in res if o.get("ok") for x in o["extents"])
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "opened units overlap"
    bases = {k: sorted(cfg.bases(k)) for k in parent}
    assert all(any(b <= lo and hi <= b + parent[k] for k in parent for b in bases[k]) for lo, hi in spans), "a unit lies outside its parent"
    frees = [s.free(n) for n in range(len(res)) if res[n].get("ok")]
    assert all(f["ok"] for f in frees) and not s.fatal and not [o for o in s.objects() if o["in_use"]]
    s2, res2 = run([("open", MEM_ID), "apply", ("open", MEM_ID), ("free", 0), ("free", 1), ("open", MEM_ID)], apply_first=False)
    o2 = [o for o in res2 if o.get("step") == "open"]
    theirs = contrib("dmmwb_a6700_v1")
    against = "the contributed kit is not on disk: not compared"
    if theirs:
        same = lambda a, b, keys: sorted(tuple(x[k] for k in keys) for x in a) == sorted(tuple(y[k] for k in keys) for y in b)
        against = {"sites_equal": same(sites, theirs["sites"], ("ram_address", "old", "new")),
                   "unit_records_equal": same(recs, theirs["unit_record_guards"], ("ram_address", "site_off", "file_hex")),
                   "parent_records": "theirs lists 3 of the file's parent records and ours the same 3" if same(parents, theirs["parent_guards"], ("ram_address", "file_hex")) else "DIFFER",
                   "busy_keys_equal": [int(k, 16) for k in theirs["dmm_ram"]["busy_keys"]] == busy}
        assert against["sites_equal"] and against["unit_records_equal"] and against["busy_keys_equal"] and "same" in against["parent_records"], against
        print("  dmmwb_a6700_v1: sites, unit records, parent records and busy keys equal the contributed kit's")
    design = {"design": "dmmwb_a6700_v1", "build": BUILD, "camera": "ILCE-6700, firmware 2.00",
              "title": f"Memory-only DMM change: the movie raw write buffer (memory id {MEM_ID:#x}, key {KEY:#x}) grows from {RAW_PITCH} x {RAW_ROWS_STOCK} to "
                       f"{RAW_PITCH} x {RAW_ROWS_NEW} ({NEW:,} bytes) in both layouts that offer it: group 0x8a (three units, parent key 0x6fa) and group 0x8e (parent key 0x74d)",
              "artifact": "coprocessor RAM (the DMM server's copy of /cp/DmmCfg.bin); no file is changed", "dmmcfg_sha256": hashlib.sha256(cfg.data).hexdigest(),
              "cpapp_sha256": SHA, "generated_by": "build/build_og_a6700.py",
              "summary": {"sites": len(sites), "bytes": 4 * len(sites), "unit_size": NEW, "stock_unit_size": STOCK, "pitch": RAW_PITCH, "stock_rows": RAW_ROWS_STOCK,
                          "new_rows": RAW_ROWS_NEW, "first_stage_rows_of_ogsq_a6700_v1": stage_rows, "first_stage_bytes": stage_rows * RAW_PITCH,
                          "group_0x8a": {"units": 3, "need": need[0x8A], "parent_key": "0x6fa", "parent_size": parent[0x6FA], "left_free": parent[0x6FA] - need[0x8A]},
                          "group_0x8e": {"units": 1, "need": need[0x8E], "parent_key": "0x74d", "parent_size": parent[0x74D], "left_free": parent[0x74D] - need[0x8E],
                                         "other_units": [[hex(x["key"]), x["size"]] for x in g8e["units"][1:]]},
                          "fit_for_the_write_level": {"unit_size": NEW, "units_that_must_fit_each_parent": 3,
                                                      "note": "three units of the new size fit both parents' records (0x6fa: 74,448,896; 0x74d: 81,788,928); group 0x8e's "
                                                              "own need (one unit and the five others) is checked here, not by the level"}},
              "dmm_ram": {"unit_records_base": hex(cfg.ram("unit_records", 0)), "group_records_base": hex(cfg.ram("group_records", 0)), "workspace_ptr_addr": "0x19d8058",
                          "units_ptr_addr": "0x19d7bac", "ws_units_at": "0x107e0", "n_obj": 0x580, "obj_size": 0x50, "busy_keys": [hex(k) for k in busy]},
              "precondition": "no unit object of key 0x57f, 0x634 or 0x635 exists in a division still in force when the words are written (the write level checks the DMM "
                              "server's unit objects and writes nothing otherwise): with the camera on stills after a cold boot, no movie buffer is open",
              "restore": "write the old words back under the same condition, or cold boot (the tables are rebuilt from /cp/DmmCfg.bin)",
              "sites": sites, "unit_record_guards": recs, "parent_guards": parents,
              "checked_in_the_firmware_allocator": {
                  "tool": "build/emu_dmm_server.py --build a6700_200 (the A6700's own DMM server code, alone; see its header for what is made up)",
                  "applied_before_any_open": {"opens_of_0x43e": [o["extents"] or o["result"] for o in res[:n_open]], "open_0x4b7": res[n_open]["extents"] or res[n_open]["result"],
                                              "open_0x4b8": res[n_open + 1]["extents"] or res[n_open + 1]["result"], "all_inside_a_parent_and_disjoint": True, "all_freed": True},
                  "stock_control": {"opens_of_0x43e": [o["extents"] or o["result"] for o in res0[:n_open]]},
                  "same_number_of_buffers_as_stock": len(ok) == len(ok0), "same_places_as_stock_for_the_first_of_each_parent": [o["extents"][0]["address"] for o in ok][0] == [o["extents"][0]["address"] for o in ok0][0],
                  "written_while_a_stock_buffer_is_open": {"open_before": o2[0]["extents"], "open_while_it_is_in_use": o2[1]["extents"] or o2[1]["result"],
                                                           "open_after_both_were_freed": o2[2]["extents"] or o2[2]["result"]}},
              "against_the_contributed_kit": against,
              "not_shown": ["that the image hardware takes the taller stage once the buffer is large enough (reported by the contributor, no logs seen)",
                            "what the camera has open when the words are written (the write level checks it and writes nothing if a movie buffer exists)"]}
    write("dmmwb_a6700_v1", design, [(x["ram_address"], x["new"]) for x in sites])
    print(f"dmmwb_a6700_v1: {len(sites)} sites {[x['ram_address'] for x in sites]} {STOCK:,} -> {NEW:,}; buffers opened with the change: {len(ok)} (stock {len(ok0)}); "
          f"left free: 0x6fa {parent[0x6FA] - need[0x8A]:,}, 0x74d {parent[0x74D] - need[0x8E]:,}")
    return cfg


# ---------------------------------------------------------------- the output size and the 5.7K coprocessor words (the A7 IV's designs, translated)

A7IV_SIZE_ENTRIES, A7IV_SETTING = (0x143C7B4, 0x143C7C4), (0x143C9B0, 0x143C9C0)
SETTING = 0x199EEB0                                # the split rule 0x4b5164 reads byte [0x199eea0 + 0x10] (A7 IV: 0x430d5c reads 0x143c9b8)


def dmm_tables(build):
    D.use_build(build)
    cfg = P.Config(P.find_file(build), build)
    s = D.Server(cfg.data, cfg)
    assert s.init() == 0 and not s.fatal
    rows, a = [], P.RAM[build]["id_rows"]
    while True:
        i, p = struct.unpack("<II", s.uc.mem_read(a, 8))
        if i == 0xFFFFFFFF:
            break
        rows.append((a, i, p))
        a += 8
    return s, cfg, rows


def word_designs():
    t, srows, _ = emu_size_table.table(BUILD)
    assert t == 0x199EC7C and srows[8] == (3840, 2160, 0x43E) and srows[9] == (3840, 2160, 0x2D9) and srows[3] == (8192, 4320, 0x43F)
    # the reader of the unit-count setting: movw/movt 0x199eea0, ldrb [.., #0x10], subs #1, cmp #2 (0x4b515c..0x4b516a)
    assert rd(0x4B515C, 14) == bytes.fromhex("4ef6a062c0f29912127c013ad3b2022b"[:28]), "the split rule's read of the setting is not where it was found"
    known = {}
    for k, (w, h, mid) in enumerate(srows):
        for j, b in enumerate(struct.pack("<2HI", w, h, mid)):
            known[t + 8 * k + j] = b
    assert SETTING > IMAGE_END, "the setting is not zero-initialised data"
    for j in range(16):
        known.setdefault(SETTING - 8 + j, 0)                    # zero-initialised data; read as zero on the A7 IV camera (guarded)
    s, cfg, rows_n = dmm_tables(BUILD)
    for a, i, p in rows_n:
        for j, b in enumerate(struct.pack("<II", i, p)):
            known[a + j] = b
        q = p
        while True:
            k = struct.unpack("<I", s.uc.mem_read(q, 4))[0]
            for j, b in enumerate(struct.pack("<I", k)):
                known[q + j] = b
            q += 4
            if k == 0xFFFFFFFF:
                break
    by_id_n = {i: (a, p) for a, i, p in rows_n}
    _, _, rows_a = dmm_tables("a7iv_602")
    by_row_a = {a: (i, p) for a, i, p in rows_a}
    by_id_a = {i: (a, p) for a, i, p in rows_a}
    D.use_build(BUILD)
    KEYS_A = P.RAM["a7iv_602"]["id_keys"]
    moves = [(A7IV_SIZE_ENTRIES, t + 8 * 8 - A7IV_SIZE_ENTRIES[0]), (A7IV_SETTING, SETTING - 8 - A7IV_SETTING[0])]

    def key_list(ptr_a):
        ids_ = [i for i, (a, p) in by_id_a.items() if p == ptr_a]
        assert len(ids_) == 1, (hex(ptr_a), ids_)
        return by_id_n[ids_[0]][1]

    def tr_addr(a, n):
        for (lo, hi), sh in moves:
            if lo <= a and a + n <= hi:
                return a + sh
        if a in by_row_a or a - 4 in by_row_a:
            row = a if a in by_row_a else a - 4
            return by_id_n[by_row_a[row][0]][0] + (a - row)
        if KEYS_A <= a < KEYS_A + 0x2000:
            return key_list(a)
        raise SystemExit(f"no A6700 counterpart for {a:#x}")

    def tr_bytes(b):
        if len(b) in (4, 8):
            return struct.pack("<%dI" % (len(b) // 4), *[key_list(v) if KEYS_A <= v < KEYS_A + 0x2000 else v for v in struct.unpack("<%dI" % (len(b) // 4), b)])
        return b

    def held(a, b, what):
        bad = [hex(a + j) for j, x in enumerate(b) if known.get(a + j) != x]
        assert not bad, f"{what} at {a:#x}: not what the A6700 holds ({bad[:4]})"

    regions = {"size_table": [hex(t), hex(t + 0x80)], "unit_count_setting": [hex(SETTING - 8), hex(SETTING + 8)],
               "dmm_id_rows": [hex(rows_n[0][0]), hex(rows_n[-1][0] + 8)], "dmm_key_lists": [hex(P.RAM[BUILD]["id_keys"]), hex(P.RAM[BUILD]["id_keys"] + 0x2000)]}
    for src, name in (("outsz2560_v1", "outsz2560_a6700_v1"), ("og57cp_v3", "og57cp_a6700_v1")):
        d = json.loads((DES / f"{src}.json").read_text(encoding="utf8"))
        sites, guards = [], []
        for x in d["sites"]:
            a, old, new = int(x["ram_address"], 16), bytes.fromhex(x["old"]), bytes.fromhex(x["new"])
            c = tr_addr(a, 4)
            o2, n2 = tr_bytes(old), tr_bytes(new)
            held(c, o2, f"{name} site")
            sites.append({"ram_address": hex(c), "old": o2.hex(), "new": n2.hex(), "note": x["note"] + f" [A7 IV {a:#x}]"})
        for g in d["guards"]:
            a, b = int(g["ram_address"], 16), bytes.fromhex(g["bytes"])
            c = tr_addr(a, len(b))
            b2 = tr_bytes(b) if (a in by_row_a or a - 4 in by_row_a) else b
            held(c, b2, f"{name} guard")
            guards.append({"ram_address": hex(c), "bytes": b2.hex(), "note": g["note"] + f" [A7 IV {a:#x}]"})
        sa = [int(x["ram_address"], 16) for x in sites]
        assert len(set(sa)) == len(sa) and all(v % 4 == 0 for v in sa) and all(v > IMAGE_END for v in sa), "a site is not a RAM word"
        for g in guards:
            ga, gn = int(g["ram_address"], 16), len(g["bytes"]) // 2
            assert not any(ga < v + 4 and v < ga + gn for v in sa), "a guard overlaps a site"
        res = {"design": name, "build": BUILD, "camera": "ILCE-6700, firmware 2.00", "title": d["title"] + " (A6700 2.00)", "kind": "ram_words",
               "artifact": "cpapp-b.bin, RAM only (tables the coprocessor builds after start-up; none of the words is in the file)", "artifact_sha256": SHA,
               "generated_by": "build/build_og_a6700.py", "ported_from": {"design": src, "build": "a7iv_602"},
               "table": "A6700: movie size table 0x199ec2c + 0x50 (set-up 0x4ab69c), unit-count setting 0x199eeb0 (the split rule 0x4b5164 reads byte [0x199eea0 + 0x10]), "
                        "memory manager id rows 0x25b6a68 and key lists 0x25b8a68",
               "regions_a_site_or_guard_may_lie_in": regions, "summary": dict(d["summary"], sites=len(sites), bytes=4 * len(sites)), "sites": sites, "guards": guards,
               "checked_against": ["build/emu_size_table.py a6700_200 (the A6700's set-up 0x4ab69c run alone): the size-table words and guards",
                                   "build/emu_dmm_server.py --build a6700_200 (the A6700's DMM set-up on its DmmCfg.bin): the id rows and key lists",
                                   "assumed, guarded: the 16 bytes around the unit-count setting are zero on the camera (zero-initialised data; read as zero on the A7 IV)"]}
        if src == "og57cp_v3":
            assert 0x587 not in cfg.units_by_key and by_id_n[0x446][0] and 0x43F not in by_id_n, "id 0x446 / 0x43f are not as on the A7 IV"
            s2, _, _ = dmm_tables(BUILD)
            before = s2.open(0x43F)
            s2, _, _ = dmm_tables(BUILD)
            for x in sites:
                a = int(x["ram_address"], 16)
                if P.RAM[BUILD]["id_rows"] <= a < P.RAM[BUILD]["id_keys"]:
                    assert bytes(s2.uc.mem_read(a, 4)) == bytes.fromhex(x["old"])
                    s2.uc.mem_write(a, bytes.fromhex(x["new"]))
            opens = [s2.open(0x43F) for _ in range(4)]
            got = [[e["size"] for e in o["extents"]] for o in opens if o["ok"]]
            assert not before["ok"] and got and all(g == [30824400] for g in got), (before, opens)
            res["checked_in_the_firmware_allocator"] = {"tool": "build/emu_dmm_server.py --build a6700_200", "open_0x43f_stock": before["result"],
                                                        "opens_0x43f_with_the_change": [o["extents"] or o["result"] for o in opens],
                                                        "id_0x446": "cannot be opened on stock either: no layout has a unit of its key 0x587"}
            res["what_the_file_holds"] = ("the first stage is unchanged: the second scaler ENLARGES the 4336 x 2438 front-end picture to 5760 x 3840 (1.33 x wide, 1.575 x high). "
                                          "The 5760 x 3840 file holds no more detail than the 3840 x 2560 one (the A7 IV's og57cp_v3 state, F710), not real 5.7K rows")
        theirs = contrib(name)
        if theirs:
            ts = sorted((x["ram_address"], x["old"], x["new"]) for x in theirs["sites"])
            tg = sorted((int(g["ram_address"], 16), g["bytes"]) for g in theirs["guards"])
            eq_s = ts == sorted((x["ram_address"], x["old"], x["new"]) for x in sites)
            eq_g = tg == sorted((int(g["ram_address"], 16), g["bytes"]) for g in guards)
            res["against_the_contributed_kit"] = {"sites_equal": eq_s, "guards_equal": eq_g}
            assert eq_s and eq_g, (name, ts, tg)
            print(f"  {name}: {len(sites)} sites and {len(guards)} guards equal the contributed kit's")
        write(name, res, [(x["ram_address"], x["new"]) for x in sites])
        print(name, [(x["ram_address"], x["old"], x["new"]) for x in sites], len(guards), "guards")


def mode_table():
    """evidence/a6700/sensor/modes_a6700_200.json: per drive mode its matrix column, picture records, window and the two timing rows.
    The rate is HMAX x VMAX against the 4K 24p mode's (0x8c0, 60 Hz table = 23.976 fps): it is what the tables give, NOT a reading of
    the code that picks a mode for a menu setting (that choice is made outside these tables and was not traced)."""
    ids = list(struct.unpack_from("<%dI" % NMODES, X, IDS - B))
    col = struct.unpack_from("<%dI" % NMODES, X, COLMAP - B)
    f = E.CONSTS[BUILD]["fields"]
    sel, _ = S.records(BUILD)
    ref = 340 * 4410 * 24000 / 1001
    rows = {}
    for i, m in enumerate(ids):
        ta, tb = (struct.unpack_from("<3I", X, f[k] - B + 24 * i) for k in (0x2C, 0x30))
        crop, s0, ro = table_row(CROP, i), table_row(S0, i), table_row(RO, i)
        rows[hex(m)] = {"index": i, "matrix_column": col[i], "picture_records": [hex(r) for r in sel[m]], "window": [s0[4], s0[13]], "window_row": crop[3],
                        "readout_length": ro[6], "timing_60hz": {"hmax": ta[0], "vmax": ta[1], "word": hex(ta[2]), "frames_per_second_if_0x8c0_is_23.976": round(ref / (ta[0] * ta[1]), 3)},
                        "timing_50hz": {"hmax": tb[0], "vmax": tb[1], "word": hex(tb[2]), "frames_per_second_if_0x8c0_is_23.976": round(ref / (tb[0] * tb[1]), 3)}}
    (EV / "modes_a6700_200.json").write_text(json.dumps({"about": mode_table.__doc__, "modes": rows}, indent=1) + "\n", encoding="utf8", newline="\n")
    for m in MODES + (MODE50,):
        r = rows[hex(m)]
        print(f"  mode {m:#06x}: column {r['matrix_column']}, window {r['window'][0]} x {r['window'][1]} from row {r['window_row']}, read-out {r['readout_length']}; "
              f"60 Hz {r['timing_60hz']['hmax']} x {r['timing_60hz']['vmax']} ({r['timing_60hz']['frames_per_second_if_0x8c0_is_23.976']}), "
              f"50 Hz {r['timing_50hz']['hmax']} x {r['timing_50hz']['vmax']} ({r['timing_50hz']['frames_per_second_if_0x8c0_is_23.976']})")


def main():
    EV.mkdir(parents=True, exist_ok=True)
    mode_table()
    new = sensor_designs()
    sensor_design_32()                                # its 3,976-row first stage fits the same 3,980-row buffer (asserted there)
    dmm_design(new[0])
    word_designs()


if __name__ == "__main__":
    main()
