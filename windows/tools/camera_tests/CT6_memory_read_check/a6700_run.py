"""A6700 (ILCE-6700) firmware 2.00: run one of the two READ-ONLY helper libraries, or one write step, and save what it reports.

  python a6700_run.py check --dry-run | --selftest
  python a6700_run.py dump  --dry-run | --selftest
  python a6700_run.py check --go --firmware-shown 2.00
  python a6700_run.py dump  --go --firmware-shown 2.00 [--clear-result SHA256] [--remove-library SHA256]
  python a6700_run.py <write step> --go --writes-memory --firmware-shown 2.00      (a6700_apply.py runs these)

  check   identity of the camera's software and what every site of the open-gate designs holds now: READY / NOT READY
          (the stored records, the output-size and 5.76K words, the screen words and the playback words are reported as well, not counted)
  dump    the same, plus kernel and memory facts, the coprocessor's logs and some of its tables (sensor registers, stored
          records with the window they program, the movie size table, the memory manager's records, the display: panel type, fit
          words, frame tables) and the playback part of the main processor's log

Both read-only libraries only read. Each creates one file, its result, on the camera's RAM disk; this script fetches it. The
library is written to the camera's service partition, loaded once, and deleted again in the same session.

The A6700 counterpart of fx30_run.py and fx3_run.py (2026-11-26). The A6700 kit is a contributed port: its designs came from a
contributor's own kit (a6700-opengate v1.0) and were conformed to this project's helper, runner and checks (modding/A6700_PORT.md).
Nothing here can send a memory write unless a write step is named with --writes-memory. NOT RUN ON AN A6700.
"""
import argparse
import json
import platform
import re
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "CT1_usb_first_contact"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "helper"))
sys.path.insert(0, str(HERE / "helper_a6700"))
import ct1_common as c  # noqa: E402
import ct6_level1_run as R  # noqa: E402

FIRMWARE, MODEL, BUILD = "2.00", "ILCE-6700", "a6700_200"
S3 = HERE / "helper_a6700"                     # this kit's folder (the name S3 is kept from s3_run.py)
READ_LABELS = ("a6700read_v1 ",)               # read helpers whose READY verdict an apply accepts
PINS = {"check": ("libJit_a6700_check.so", "53448534c8c1ce5b2a653896fa5559fbf9dc249500ef23121e9527026eccef69"),      # a6700read_v1 (2026-11-26)
        "dump": ("libJit_a6700_dump.so", "03f32661cd4ce93d7584a77a6452948b42fc2606cdd2bd70101cfa8bbb66dafe")}
LEVELS = {"check": 101, "dump": 102}              # numbers outside the A7 IV runner's own levels: none of its level-specific code runs
# THE WRITE STEPS. Each is one library built from the A7 IV helper's write code with this camera's tables (helper_a6700/build_a6700_write.sh).
# They change the running camera's memory until a cold boot. They are run through a6700_apply.py, never by a launcher of the read-only kit.
WRITE_STEPS = {
    # The raw write buffer (levels 13/14): the movie raw write buffer's unit holds the stock 3,356-row stage; the taller stage needs 3,884
    # rows, the design gives 3,980. Must run first, from a cold boot with the camera on STILL.
    "L13": ("libJit_a6700_L13.so", "5bc0dfa7c0a9d27b72f18ab85f26edfb3ae5687eb46e6a86709119eae34500a0", "apply the raw write buffer dmmwb_a6700_v1 (four memory-manager words: the movie raw write buffer holds 3,980 rows of 6,016 bytes)"),
    "L14": ("libJit_a6700_L14.so", "ef2c7114c98b283b19a8fd7d975901a69d4d6ff789008f9000d276ee23123680", "put back the raw write buffer dmmwb_a6700_v1"),
    # The sensor side (levels 5/6, MULTI_REC): the 4K window 5952x3876 from row 214 in the five drive modes that share register-matrix
    # column 1 and the picture-record pair (0x820, 0x880, 0x890, 0x8c0, 0x8d0); their stored records, NTSC or PAL as the camera holds them.
    "L5": ("libJit_a6700_L5.so", "5e9fddbba754c1f0c30f2903eb34c8827d895247da090a6f89f82a330709ae46", "apply the sensor-side design ogsq_a6700_v1 (the 4K window 5952x3876 from row 214 in modes 0x820/0x880/0x890/0x8c0/0x8d0: 51 table cells, "
                                        "the two picture records and the five stored records, NTSC or PAL as the camera holds them)"),
    "L6": ("libJit_a6700_L6.so", "f93662a1d3456fa913a2daf8d147127ee4a21a41e446ca04c7864ff93e3fea9a", "put back the sensor-side design ogsq_a6700_v1"),
    # A TEST design of ours in L5's place (levels 5/6, MULTI_REC): the exact 3:2 window 5952x3968 from row 94 (the FX30 kit's window), so the
    # 3840x2560 picture has square pixels; the contributed window (5952x3876) makes it 2.37 % too tall. L5 and T5 refuse each other.
    "T5": ("libJit_a6700_T5.so", "9de735fcd26cb3219301bffd867054e96d5966422b1cc05410cf14180c1dba4a", "apply the exact 3:2 sensor-side TEST design ogsq32_a6700_v1 (the window 5952x3968 from row 94 in the same five modes: 52 table cells, "
                                        "the two picture records and the five stored records)"),
    "T6": ("libJit_a6700_T6.so", "96f5d6118a9435165c62e8a3e82837bbfe412b26810a2b705024abb7c49f123c", "put back the exact 3:2 sensor-side test design ogsq32_a6700_v1"),
    # PAL only (levels 5/6, one stored record): the drive mode 0x830 (4K 50p by the contributor's report) reads 5612x3732 from row 214
    # instead of 5612x3156. On an NTSC camera its stored record is another one and nothing is written.
    "Q5": ("libJit_a6700_Q5.so", "7f41636a85a1f2d0ed0a3b5cad3ab8d30275d12c3250974b0b625dabbca40ce6", "apply the 50p sensor-side design ogsq50_a6700_v1 (PAL: the window 5612x3732 in mode 0x830: 16 table cells, two picture records, one stored record)"),
    "Q6": ("libJit_a6700_Q6.so", "000e445846d95aa1aefdf43c9c7328e2e8972fc497d3e66446fdf161b5a4324e", "put back the 50p sensor-side design ogsq50_a6700_v1"),
    "L16": ("libJit_a6700_L16.so", "74bee2fc5619bcf12aafcfdb3e193f6ad3b101e31e920e94d621d70ca0f7eac7", "apply the output size outsz2560_a6700_v1 (one word: 3840x2560)"),
    "L17": ("libJit_a6700_L17.so", "a82ea7825725798edfd31bdd81f8eb4cbc7954a1735efcfd0337c04ae138c49e", "put back the output size outsz2560_a6700_v1"),
    # L19: this project's encoder side for 3840x2560 (XAVC HS 4K and XAVC S 4K at 24p / 25p; the FX30 kit's shape) with the two MP4 header
    # heights. L20 puts back either version. N19 = the same without the heights (apply --no-meta); its put back is L20 too.
    "L19": ("libJit_a6700_L19.so", "a50adb1214c347c87f542854d7b5447221fb583172da132c44cbb1b4cc5f5cd8", "apply the encoder-side design ogfile2560_hs_s_a6700_v2 (101 + 4 sites, and the MP4 headers say 3840x2560: 2 more)"),
    "L20": ("libJit_a6700_L20.so", "0a0c0ffdd0b313147d91eda1fdf370ec347a9f904c877052dbb445d0f1a42886", "put back the encoder-side design ogfile2560_hs_s_a6700_v2 (or v1)"),
    "N19": ("libJit_a6700_N19.so", "9e3a056bcaf40029642bdeaa65b7a000df9e59b04bdbd6422ad29b260a771efd", "apply the encoder-side design ogfile2560_hs_s_a6700_v1 (101 + 4 sites; the MP4 headers keep 3840x2160)"),
    # I19 (optional, on top of L19): XAVC S-I 4K at 24p / 25p, the FX3 kit's S-I step. Its bytes are all inside the contributed design.
    "I19": ("libJit_a6700_I19.so", "a9fd6e5206bf2106a2a6c0572376b94aadd30524dcf842818a6fc7182d063280", "apply the XAVC S-I 4K encoder step ogfilesi2560_a6700_v1 (16 + 1 sites, on top of the encoder side)"),
    "I20": ("libJit_a6700_I20.so", "5f105b7d7d50ee627ecfe307ed7d9e146a51216faac6a2f6e0be9a1aa3680e01", "put back the XAVC S-I 4K encoder step ogfilesi2560_a6700_v1"),
    # M19: the CONTRIBUTED encoder design, complete (24p, 25p and 50p; XAVC HS, S and S-I; the MP4 header heights and the resolution compare
    # in libmpr.so), in L19's place: its unit-type row differs from L19's, so the two refuse each other. Used by apply50.
    "M19": ("libJit_a6700_M19.so", "0159915918db784e3545d5e11533cbaca05391662700a236eb714bbf8d7c519a", "apply the contributed encoder-side design ogfile2560_full_a6700_v1 (475 + 8 sites: 3840x2560 at 24p, 25p and 50p in XAVC HS, S and S-I, MP4 headers at 3840x2560)"),
    "M20": ("libJit_a6700_M20.so", "65bfc657f7bfe46d85cef40e8ebff31b62db22a4fe9f67a2f2b890e8cf580927", "put back the contributed encoder-side design ogfile2560_full_a6700_v1"),
    # The rear-screen step (optional): the level 16/17 code with the screen words.
    "S16": ("libJit_a6700_S16.so", "6559a096eb91b035e0d319537fa911616f4a3f773ccbdc8f2d47fe912ce187fd", "apply the screen words lcdfill_a6700_v2 (the 3:2 rear screen filled with the whole picture, and the focus-frame rectangles: 5 words)"),
    "S17": ("libJit_a6700_S17.so", "8f2dfea7755ddb9647050b81047d2aa5eb2f4686583f170e6315291a570882c4", "put back the screen words lcdfill_a6700_v2"),
    # The 5.76K state: K16 / K19 take the place of L16 / L19 (they share words with them and refuse while those are applied).
    "K16": ("libJit_a6700_K16.so", "2d80ae30f06751975a5d52853900807a220cd4093b168d5cd606218a31df7f8c", "apply the 5.76K coprocessor words og57cp_a6700_v1 (output 5760x3840, four scaler units, the larger output buffer: 5 words)"),
    "K17": ("libJit_a6700_K17.so", "788485df7db31aafee4da5dd05a23eab8ffb2d2a43d139d6f0315e526d69fc71", "put back the 5.76K coprocessor words og57cp_a6700_v1"),
    "K19": ("libJit_a6700_K19.so", "b09a12e680887dff09689d6cf874f7bf6ba37834e92b7be0c17c7654a53739e2", "apply the 5.76K encoder-side design ogfile57r260_a6700_v1 (487 + 14 sites: 5760x3840 at 24p / 25p, 260 Mbps, MP4 headers at 5760x3840)"),
    "K20": ("libJit_a6700_K20.so", "8ff5004ee07aad666dbe197711cfd8e568e009cb61e9fdba008d805dfd2065c1", "put back the 5.76K encoder-side design ogfile57r260_a6700_v1"),
    # In-camera playback of 3840x2560 clips: three one-page steps (readcheck.c levels 29/30 carry one code page each) and one libmpr.so
    # instruction (level 19/20; M19 holds the same instruction).
    "P29": ("libJit_a6700_P29.so", "da6f12578733815454d3923ca0d3962b1b9babf2af3d617493ed61ab512da7af", "apply the playback decoder avdec8k_a6700_v1 (the larger decode channel and its memory: 4 code words and 1 table word of av-cam.bin)"),
    "P30": ("libJit_a6700_P30.so", "a28eb356deb2ba9cab36278a1cb44cb2f5b756c5673d013b87beaed8a05e778d", "put back the playback decoder avdec8k_a6700_v1"),
    "A29": ("libJit_a6700_A29.so", "919029f2254669ee449a7f0264c13bcf9cab34c45e20d209ffb5452aa89efecd", "apply the playback aspect pbaspect_a6700_v1 (the aspect routine takes a 2,560-row clip: 2 code words of av-cam.bin)"),
    "A30": ("libJit_a6700_A30.so", "641edee95525aa879a1ece09c540407613e2f976e9845a84eb3875ba70a128b8", "put back the playback aspect pbaspect_a6700_v1"),
    "F29": ("libJit_a6700_F29.so", "ef55fa011e5b56fbd6e93815f2fb85cbdb3808d092aeefaba96af4038bdecd33", "apply the playback format pbformat_a6700_v1 (the playback format routine takes 3840x2560 as a 4K clip: 1 code word of av-cam.bin)"),
    "F30": ("libJit_a6700_F30.so", "b4292b1578046c7218d98b35ea537cee3bb0845cbb289bc297e47474d797e351", "put back the playback format pbformat_a6700_v1"),
    "R19": ("libJit_a6700_R19.so", "f8d4962b200033e704e9a24d96c9ee9285fd0442501466b024bb67cb1e21339d", "apply the playback resolution compare pbmpr_a6700_v1 (libmpr.so takes a 3840-wide clip of 2,160 rows or more: 1 instruction)"),
    "R20": ("libJit_a6700_R20.so", "fc470b35cf17ddc9914bfbbaef430fb23df45be0b2693871c1d0515d09ed5f90", "put back the playback resolution compare pbmpr_a6700_v1"),
}
PINS.update({k: v[:2] for k, v in WRITE_STEPS.items()})
LEVELS.update({k: {"L": 200, "S": 300, "N": 500, "P": 600, "I": 700, "Q": 1000, "K": 1100, "A": 1200, "F": 1300, "M": 1400, "R": 1500, "T": 1600}[k[0]] + int(k[1:])
               for k in WRITE_STEPS})
WHICH = "check"
DESIGN_MODES = ("0x820", "0x880", "0x890", "0x8c0", "0x8d0")
# The contributor's own kit (a6700-opengate v1.0) loads its libraries the same way. A run of that kit which was cut off can have left one on
# the camera's service partition: with PINS these are the files a run of this kit may delete there (R.KNOWN_LIBS). None of them is in this kit.
EARLIER_LIBS = {}
try:
    EARLIER_LIBS = {sha: "a library of the contributor's kit a6700-opengate v1.0 (%s)" % name
                    for name, sha in json.loads((S3 / "contrib_libs.json").read_text(encoding="utf8")).items()}
except (OSError, ValueError):
    pass
EXTRA_LIBS = {}                                   # --remove-library: one more file, named by its SHA-256 on the command line


def known_libs():
    out = {sha: "this kit's %s library (%s)" % ("read-only " + k if k in ("check", "dump") else "step " + k, name) for k, (name, sha) in PINS.items()}
    out.update(EARLIER_LIBS)
    out.update(EXTRA_LIBS)
    return out


def write_result(data):
    """The facts of a write step's result (the A7 IV helper's report format)."""
    import hashlib
    text = data.decode("utf8", "replace")
    lines = text.split("\n")
    pick = lambda start: next((ln for ln in lines if ln.startswith(start)), None)
    outcome = ("UNDO INCOMPLETE" if pick("!! UNDO INCOMPLETE") or pick("UNDO INCOMPLETE") else "DONE" if pick("DONE: ") else "NOTHING TO DO" if pick("NOTHING TO DO") else
               "NOT DONE (everything put back)" if pick("NOT DONE: ") else "NOTHING WRITTEN" if any("nothing is written" in ln for ln in lines) else "UNKNOWN")
    problems = [ln for ln in lines if ln.startswith("!!")]
    variant = pick("the stored records are the ")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "header_ok": lines[0].startswith("readcheck 1 level %s" % WHICH[1:]),
            "euid": "see the result", "sections": [ln for ln in lines if ln.startswith("== ")], "problems": len(problems),
            "complete": any(ln.startswith("== done") for ln in lines[-3:]),
            "s3": {"step": WHICH, "what": WRITE_STEPS[WHICH][2], "outcome": outcome, "ok": outcome in ("DONE", "NOTHING TO DO"),
                   "outcome_line": pick("DONE: ") or pick("NOTHING TO DO") or pick("NOT DONE: ") or pick("!! UNDO INCOMPLETE") or pick("UNDO INCOMPLETE"),
                   "timing_variant": variant, "problem_lines": problems}}


def reference():
    return json.loads((S3 / "a6700_reference.json").read_text(encoding="utf8"))


def expected():
    return json.loads((S3 / "a6700_expected.json").read_text(encoding="utf8"))


# ------------------------------------------------------------ reading a result

def check_result(data):
    """The facts of a result file. Keys the A7 IV runner prints, plus this helper's own under "s3"."""
    if WHICH in WRITE_STEPS:
        return write_result(data)
    text = data.decode("utf8", "replace")
    lines = text.split("\n")
    head = lines[0] if lines else ""
    count = lambda pat: sum(1 for ln in lines if re.search(pat, ln))
    verdict = next((ln for ln in lines if ln.startswith("VERDICT ")), "no verdict line")
    pages = {}
    for ln in lines:
        if ln.startswith("cppage "):
            _, name, addr, hx = ln.split(" ", 3)
            pages[int(addr, 16)] = (name, bytes.fromhex(hx.strip()))
    sites, other = [], {}
    for ln in lines:
        m = re.match(r"site (\S+) (0x[0-9a-f]+) len (\d+)(?: bytes (?:differing from stock )?(\S+))?  (STOCK|TARGET32|TARGET|OTHER.*|NOT READ)$", ln)
        if m:
            sites.append({"name": m.group(1), "address": m.group(2), "length": int(m.group(3)), "shown": m.group(4), "state": m.group(5)})
        m = re.match(r"other (\S+) ([0-9a-f]+)$", ln)
        if m:
            other[m.group(1)] = bytes.fromhex(m.group(2))
    def mp(tag):
        """The spans of one file: how many are stock, in no known state, and per design how many hold its bytes."""
        c = {"spans": 0, "stock": 0, "other": 0, "designs": [0] * len(designs)}
        for ln in lines:
            if not ln.startswith(tag + " "):
                continue
            c["spans"] += 1
            m = re.search(r"  DESIGNS ([0-9a-f]{2})$", ln)
            if ln.endswith("  STOCK"):
                c["stock"] += 1
            elif m:
                for k in range(len(designs)):
                    c["designs"][k] += int(m.group(1), 16) >> k & 1
            else:
                c["other"] += 1
        return c
    designs = expected()["mp_designs"]
    pb = lambda state: count(r"^pb .*  %s$" % state)
    s3 = {"header": head, "verdict": verdict, "ready": verdict.startswith("VERDICT READY"),
          "identity_same": count(r"SAME as the 2\.00 update$"), "identity_differs": count(r"DIFFERS from the 2\.00 update$"),
          "coprocessor_sites": sites,
          "libmpr": mp("lm"), "avcam": mp("av"),
          "playback_words": {"stock": pb("STOCK"), "target": pb("TARGET"), "other": count(r"^pb .*  (OTHER|NOT READ)")},
          "avcam_guards": [ln for ln in lines if ln.startswith("guard ")], "problem_lines": [ln for ln in lines if ln.startswith("!!")],
          "pages": len(pages)}
    s3["encoder_designs"], s3["encoder_state"] = encoder_state(s3["libmpr"], s3["avcam"], designs)
    s3["stored_records"] = stored_record_states(sites, other)
    cmd = re.search(r"== file /proc/cmdline\n(.*?)\n== end", text, re.S)
    ver = re.search(r"== file /proc/version\n(.*?)\n== end", text, re.S)
    s3["kernel_command_line"], s3["kernel_version"] = (cmd.group(1).strip() if cmd else None), (ver.group(1).strip() if ver else None)
    log = re.search(r"== main-processor log.*?\n(.*?)\n== end of the main-processor log", text, re.S)
    if log:
        s3["main_log_lines"] = log.group(1).count("\n") + 1
    if pages:
        s3["decoded"] = decode_pages(pages)
    import hashlib
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "header_ok": head.startswith("a6700read ") and "ILCE-6700 2.00" in head, "euid": "not read",
            "sections": [ln for ln in lines if ln.startswith("== ")], "problems": len(s3["problem_lines"]), "complete": "== done" in lines[-3:],
            "s3": s3, "_pages": pages}


def encoder_state(lm, av, designs):
    """Per main-processor design how many of its spans hold its bytes, and one line for the whole encoder side. The helper says per span
    whose bytes it holds; here, whether the spans agree with each other."""
    per = {}
    for k, d in enumerate(designs):
        have, of = lm["designs"][k] + av["designs"][k], d["lm_spans"] + d["av_spans"]
        per[d["step"]] = {"design": d["design"], "spans_holding_it": have, "of": of, "state": "applied" if have == of else "not applied" if not have else "partly"}
    other = lm["other"] + av["other"]
    full = [s for s, v in per.items() if v["state"] == "applied"]
    l19 = per.get("L19", {})
    if other:
        line = "other (%d spans in no known state)" % other
    elif lm["stock"] + av["stock"] == lm["spans"] + av["spans"]:
        line = "stock"
    elif "K19" in full:
        line = "5.76K open gate applied (K19, 5760x3840)"
    elif "M19" in full:
        line = "4K open gate applied with the contributed encoder design (M19, 3840x2560 at 24/25/50p)"
    elif "L19" in full:
        line = "4K open gate applied (L19, 3840x2560)" + (" with XAVC S-I (I19)" if "I19" in full else "")
    elif l19.get("of") and l19["spans_holding_it"] == l19["of"] - 2:
        line = "4K open gate applied without the MP4 header heights (N19)" + (" with XAVC S-I (I19)" if "I19" in full else "")
    elif full:
        line = "only %s applied" % ", ".join(full)
    else:
        line = "PARTLY applied: " + ", ".join("%s %d of %d" % (s, v["spans_holding_it"], v["of"]) for s, v in per.items() if v["spans_holding_it"])
    if "R19" in full and "M19" not in full:
        line += "; the playback resolution compare (R19) applied"
    return per, line


def record_state(mode, rec, design=None):
    """What one stored record holds at the design's offsets: stock or applied, and in which timing variant (NTSC 60 Hz / PAL 50 Hz).
    For the five shared modes two designs are known: the sensor step's (L5) and the exact 3:2 test design's (T5)."""
    ref = reference()
    known = [(design, "applied")] if design else [(ref["stored_records_design"][mode], "applied"), (ref.get("stored_records_design_32", {}).get(mode), "applied 3:2 (T5)")]
    for sr, word in known:
        if not sr:
            continue
        offs = [int(x, 16) for x in sr["offsets_that_differ"]]
        got = bytes(rec[k] for k in offs)
        for v in ("ntsc", "pal"):
            if v not in sr:
                continue
            for what, key in (("stock", "stock"), (word, "design")):
                if got == bytes(bytes.fromhex(sr[v][key])[k] for k in offs):
                    return f"{what} ({v.upper()})"
    return "other"


def stored_record_states(sites, other):
    out = {}
    ref = reference()
    for s in sites:
        if not s["name"].startswith("stored_record_"):
            continue
        mode = s["name"][len("stored_record_"):]
        design = ref.get("stored_record_50p") if mode == ref.get("stored_record_50p", {}).get("mode") else None
        if s["state"] in ("STOCK", "TARGET"):
            out[mode] = "stock (NTSC)" if s["state"] == "STOCK" else "applied (NTSC)"
        elif s["name"] in other:
            out[mode] = record_state(mode, other[s["name"]], design)
        else:
            out[mode] = "not read"
    return out


def decode_pages(pages):
    """What the dump's coprocessor pages say, set against the firmware file's tables (addresses from a6700_reference.json)."""
    ref, out = reference(), {}

    def mem(addr, n):
        b = bytearray()
        while n:
            page = pages.get(addr & ~0xFFF)
            if page is None:
                return None
            take = min(n, 4096 - (addr & 0xFFF))
            b += page[1][addr & 0xFFF:(addr & 0xFFF) + take]
            addr, n = addr + take, n - take
        return bytes(b)

    # the sensor register shadow against each column of the register matrix
    rows = [(a, bytes.fromhex(h)) for a, h in ref["matrix"]]
    ncol = ref["matrix_columns"]
    shadow = [(a, mem(a, 1)) for a, _ in rows]
    if all(v is not None for _, v in shadow):
        score = [sum(1 for (a, cols), (_, v) in zip(rows, shadow) if cols[k] == v[0]) for k in range(ncol)]
        best = max(range(ncol), key=lambda k: score[k])
        users = [ref["mode_ids"][i] for i, col in enumerate(ref["column_map"]) if col == best]
        dz = {}
        for cell in ref.get("matrix_design_cells", []):       # the sensor steps' cells: what the shadow holds where a step's column is in use
            if cell["column"] != best:
                continue
            v = shadow[cell["row"]][1][0]
            s = dz.setdefault(cell["step"], {"stock": 0, "applied": 0, "of": 0})
            s["of"], s["stock"], s["applied"] = s["of"] + 1, s["stock"] + (v == cell["stock"]), s["applied"] + (v == cell["new"])
        out["sensor_registers"] = {"rows": len(rows), "rows_equal_per_column": score, "closest_column": best, "modes_using_it": users,
                                   "columns_with_the_same_score": [k for k in range(ncol) if score[k] == score[best]],
                                   "rows_differing_from_it": [[i, hex(a), cols[best], v[0]] for i, ((a, cols), (_, v)) in enumerate(zip(rows, shadow)) if cols[best] != v[0]][:64],
                                   "design_rows": dz}
    m0 = int(ref["matrix_address"], 16)
    got = mem(m0, ref["matrix_row_bytes"] * len(rows)) if (m0 & ~0xFFF) in pages else None
    if got is not None:
        want = bytearray(b"".join(struct.pack("<I", a) + cols for a, cols in rows))
        steps, at = {}, set()
        for cell in ref.get("matrix_design_cells", []):
            o = cell["row"] * ref["matrix_row_bytes"] + 4 + cell["column"]
            at.add(o)
            s = steps.setdefault(cell["step"], {"stock": 0, "applied": 0, "of": 0})
            s["of"], s["stock"], s["applied"] = s["of"] + 1, s["stock"] + (got[o] == cell["stock"]), s["applied"] + (got[o] == cell["new"])
        out["matrix"] = {"other_bytes_as_file": all(got[o] == want[o] for o in range(len(want)) if o not in at), "steps": steps}
    # the stored drive-parameter records against the emulated ones (NTSC or PAL), and the window the design modes' records program
    r0, size = int(ref["records_address"], 16), ref["record_size"]
    recs, window = {}, {}
    wo = {k: int(v, 16) for k, v in ref["window"]["record_offsets"].items()}
    fifty = ref.get("stored_record_50p", {})
    for i, mid in enumerate(ref["mode_ids"]):
        b = mem(r0 + i * size, size)
        if b is None:
            continue
        best = None
        for system, emu_all in ref["emulated_stock_records"].items():
            emu = bytes.fromhex(emu_all[mid])
            diff = [o for o in range(size) if b[o] != emu[o]]
            if best is None or len(diff) < len(best[1]):
                best = (system, diff)
        recs[mid] = {"index": i, "all_zero": not any(b), "closest_emulation": best[0], "bytes_differing_from_emulation": len(best[1]),
                     "offsets": [hex(o) for o in best[1][:48]], "record": b.hex()}
        if mid in DESIGN_MODES or mid == fifty.get("mode"):
            u = lambda k: struct.unpack_from("<H", b, wo[k])[0]
            window[mid] = {"state": record_state(mid, b, fifty if mid == fifty.get("mode") else None), "window": [u("height"), u("row")],
                           "pdaf_rows": u("pdaf_rows"), "sampling_ratio": [b[4], b[5], b[6], b[7]]}
    out["stored_records"] = recs
    out["design_mode_windows"] = window
    t = mem(int(ref["size_table_address"], 16), 0xC0)
    if t is not None:
        out["size_table"] = [list(struct.unpack_from("<HHI", t, 8 * k)) for k in range(24)]
    # the memory manager's RAM copy: the raw write buffer's four words
    for key, name in (("raw_write_buffer", "raw_write_buffer_words"), ("output_words", "output_words"), ("k16_words", "k16_words")):
        ws = ref.get(key, [])
        if ws and all(mem(int(w["address"], 16), 4) is not None for w in ws):
            got = [mem(int(w["address"], 16), 4).hex() for w in ws]
            out[name] = {"stock": sum(g == w["stock"] for g, w in zip(got, ws)), "new": sum(g == w["new"] for g, w in zip(got, ws)),
                         "other": sum(g not in (w["stock"], w["new"]) for g, w in zip(got, ws)), "held": got}
    # the display: panel-type bytes, the fit words of a 16:9 picture, the frame tables, the screen step's words
    disp = {}
    pt = ref.get("panel_type", {})
    types = [mem(int(pt[k], 16), 1) for k in ("rear", "second") if k in pt]
    if len(types) == 2 and None not in types:
        name = pt.get("codes", {})
        disp["panel_types"] = {"rear": types[0][0], "rear_aspect": name.get(str(types[0][0]), "unknown"), "second": types[1][0], "second_aspect": name.get(str(types[1][0]), "unknown")}
    fw = ref.get("fit_words", {})
    fit = {k: mem(int(a, 16), 4) for k, a in fw.items()}
    if fit and None not in fit.values():
        disp["fit_16x9_picture"] = {k: struct.unpack("<I", v)[0] for k, v in fit.items()}
    frames = {}
    for t in ref.get("frame_tables", []):
        b = mem(int(t["address"], 16), t["bytes"])
        if b is not None:
            frames[t["name"]] = {"row%d" % r: list(struct.unpack_from("<4H", b, o)) for r, o in enumerate(t["rect_offsets"])}
    if frames:
        disp["frame_rectangles_16x9_picture"] = frames
    sw = ref.get("screen_words", [])
    if sw and all(mem(int(w["address"], 16), 4) is not None for w in sw):
        got = [mem(int(w["address"], 16), 4).hex() for w in sw]
        disp["screen_words"] = {"stock": sum(g == w["stock"] for g, w in zip(got, sw)), "new": sum(g == w["new"] for g, w in zip(got, sw)),
                                "other": sum(g not in (w["stock"], w["new"]) for g, w in zip(got, sw))}
    if disp:
        out["display"] = disp
    return out


def movie_notes(decoded):
    """Lines for the closing session of a6700_apply.py: what the dump taken on MOVIE says about the open-gate state."""
    lines = []
    ref = reference()
    win = decoded.get("design_mode_windows") or {}
    wants = [[ref["window"]["design_height"], ref["window"]["design_row"]], ref["window"].get("design_32")]
    applied = [m for m, v in win.items() if v["window"] in wants]
    if win and not applied:
        lines.append("NOTE: no stored record of the 4K 24p/25p modes programs an open-gate window (%d rows from row %d, or %d from row %d): %s."
                     % (wants[0][0], wants[0][1], wants[1][0], wants[1][1], ", ".join("%s %d rows from %d" % (m, v["window"][0], v["window"][1]) for m, v in win.items())))
    elif applied:
        w = win[applied[0]]["window"]
        lines.append("The stored records of %s program the open-gate window: %d rows from row %d%s." % (", ".join(applied), w[0], w[1], " (the exact 3:2 test window)" if w == wants[1] else ""))
    panel = (decoded.get("display") or {}).get("panel_types")
    if panel:
        lines.append("The rear panel reports type %d (%s). Please send this folder: it settles the A6700's panel shape." % (panel["rear"], panel["rear_aspect"]))
    return lines


# ------------------------------------------------------------ the A7 IV runner, pointed at this camera

def known_answer(session, camera):
    want = (S3 / "DeviceInfo.xml").read_bytes()
    there, data = R.read(camera, R.KNOWN_PATH)
    if not there or data != want:
        raise c.StopTest("DeviceInfo.xml is not the file of the 2.00 update (%s); nothing else is sent"
                         % ("the camera returned no file" if not there else "%d bytes, SHA-256 %s" % (len(data), c.sha256(data)[:16])))
    session.say("Known-answer read: DeviceInfo.xml equals the 2.00 file (the A7 IV, FX30 and others have the same file: the helper itself checks which camera this is)")


def run_helper(data):
    """What loading the uploaded bytes gives on a model A6700: the real AArch64 code in Unicorn if it is installed, else a canned text."""
    if WHICH in WRITE_STEPS:                        # the write libraries are emulated by helper_a6700/emu_a6700_write.py; here only the session flow is simulated
        text = "readcheck 1 level %s\neuid 0\n== level %s\nDONE: every site holds the target bytes (canned)\n== done, bytes written before this line: 0\n" % (WHICH[1:], WHICH[1:])
        return text.encode(), "canned"
    try:
        import emu_a6700
    except Exception:
        text = "a6700read a6700read_v1 %s for ILCE-6700 2.00; read-only\n== file /proc/version\nLinux (simulated)\n\n== end 18 bytes\n== summary\nVERDICT READY (canned)\n== done\n" % WHICH
        return text.encode(), "canned"
    r, text = emu_a6700.run(bytes(data))
    if r.bad:
        raise AssertionError("the emulated helper stopped: %s" % r.bad)
    return text.encode(), "emulated"


def make_sim(lib, files=None, fault=None):
    sim = _make_sim(lib, files, fault)
    if "/usr/share/pmbp/DeviceInfo.xml" not in (files or {}):
        sim.fs["/usr/share/pmbp/DeviceInfo.xml"] = (S3 / "DeviceInfo.xml").read_bytes()
    return sim


def use(which):
    """Point the runner's module state at one of this camera's libraries."""
    global WHICH
    WHICH = which
    name, sha = PINS[which]
    if not (S3 / name).is_file():
        raise SystemExit("%s is not in this kit%s. Nothing was sent." % (name, " (the write steps are not published yet)" if which in WRITE_STEPS else ""))
    R.LEVEL, R.DESIGN, R.LIB, R.LIB_SHA256 = LEVELS[which], "og4k_data_v1", S3 / name, sha
    R.check_result, R.known_answer, R.run_helper, R.make_sim = check_result, known_answer, run_helper, make_sim
    R.KNOWN_LIBS = known_libs()
    c.EXPECTED_FIRMWARE = FIRMWARE
    return R.library()


_make_sim = R.make_sim


def selftest(lib):
    done = []

    def check(cond, what):
        if not cond:
            raise AssertionError("self-test failed: " + what)
        done.append(what)

    W, D = "SET_FILE2", "FILE_DELETE2"
    lp = R.LIB_PATH.decode()
    s, sim, stopped = R.simulate(lib, R.body_run)
    r = s.results.get("ct6", {})
    check(not stopped and not sim.unexpected and R.sent(s).count(W) == 1 and R.sent(s).count(D) == 1, "normal run: one write, one delete, nothing off the list")
    check(R.sent(s).index(D) < len(R.sent(s)) - 2 and R.sent(s)[-1] == "GET_FILE2", "normal run: the delete comes before the result is read")
    check(lp not in sim.fs and sim.loads == 1, "normal run: the library was loaded once and is gone afterwards")
    f = r.get("result", {}).get("s3", {})
    if WHICH in WRITE_STEPS:
        check(f.get("ok") and r["result"]["header_ok"], "normal run: the step's result is read as DONE")
    else:
        check(f.get("ready") and not f.get("identity_differs"), "normal run: the %s helper reports a stock 2.00 camera as READY" % sim.how)
    if sim.how == "emulated":
        e = expected()
        check(len(f["coprocessor_sites"]) == len(e["cp_sites"]) and f["avcam"]["stock"] == f["avcam"]["spans"] == e["av_sites"]
              and f["libmpr"]["stock"] == f["libmpr"]["spans"] == e["lm_sites"] and f["encoder_state"] == "stock",
              "normal run: every coprocessor site, %d libmpr.so spans and %d av-cam.bin spans are reported, all stock" % (e["lm_sites"], e["av_sites"]))
        check(f["playback_words"] == {"stock": e["pb_sites"], "target": 0, "other": 0}, "normal run: the %d playback words are reported stock" % e["pb_sites"])
        check(sum(1 for x in f["coprocessor_sites"] if x["name"].startswith("rawbuf_") and x["state"] == "STOCK") == 4,
              "normal run: the raw write buffer's four memory-manager words are reported STOCK")
        check({m: v for m, v in f.get("stored_records", {}).items() if m in DESIGN_MODES} == {m: "stock (NTSC)" for m in DESIGN_MODES},
              "normal run: the five stored records of the sensor step read as stock (NTSC)")
        if WHICH == "dump":
            d = f.get("decoded", {})
            ref = reference()
            check(d.get("matrix", {}).get("other_bytes_as_file") and all(v["applied"] == 0 and v["stock"] == v["of"] for v in d["matrix"]["steps"].values())
                  and len(d.get("stored_records", {})) == len(ref["mode_ids"]) and d.get("size_table"),
                  "dump: the pages decode (matrix, %d records, size table)" % len(ref["mode_ids"]))
            stock = [ref["window"]["stock_height"], ref["window"]["stock_row"]]
            check(all(d.get("design_mode_windows", {}).get(m, {}).get("window") == stock and d["design_mode_windows"][m]["state"] == "stock (NTSC)" for m in DESIGN_MODES),
                  "dump: the five design modes' records program the stock window (%d rows from row %d)" % tuple(stock))
            check(d.get("raw_write_buffer_words", {}).get("stock") == 4 and d["raw_write_buffer_words"]["new"] == 0, "dump: the raw write buffer's words decode as stock")
            dp = d.get("display", {})
            check(dp.get("screen_words") == {"stock": len(ref["screen_words"]), "new": 0, "other": 0} and "panel_types" in dp and dp.get("fit_16x9_picture")
                  and dp.get("frame_rectangles_16x9_picture"), "dump: the display pages decode (panel types, fit words, frame tables, the %d screen words)" % len(ref["screen_words"]))
    s, sim, stopped = R.simulate(lib, R.body_run, files={lp: b"someone else's"})
    check(stopped and W not in R.sent(s) and D not in R.sent(s), "a foreign libJit.so on the camera: stops, nothing written, nothing deleted")
    s, sim, stopped = R.simulate(lib, R.body_run, files={"/tmp_wbshd/readcheck_result.txt": b"old"})
    check(stopped and W not in R.sent(s), "a result already on the RAM disk: stops, nothing written")
    s, sim, stopped = R.simulate(lib, R.body_run, files={"/tmp/jbusy": b""})
    check(stopped and W not in R.sent(s), "/tmp/jbusy present: stops, nothing written")
    s, sim, stopped = R.simulate(lib, R.body_run, files={"/usr/share/pmbp/DeviceInfo.xml": b"<other camera/>"})
    check(stopped and len(R.sent(s)) == 2, "another DeviceInfo.xml: stops after the known-answer read")
    s, sim, stopped = R.simulate(lib, R.body_run, fault="load")
    check(stopped and R.sent(s).count(D) == 1 and lp not in sim.fs, "a camera that cannot load the library: it is still deleted")
    # a library an earlier session left on the service partition (the FX3 kit's fix, 2026-11-26): one of this kit's, or one of the contributor's kit
    other = next((S3 / name).read_bytes() for k, (name, sha) in PINS.items() if k != WHICH and (S3 / name).is_file())
    lefts = [(other, "another library of this kit")]
    if EARLIER_LIBS:
        lefts.append((None, "a library of the contributor's kit"))
    for left, what in lefts:
        if left is None:                              # the contributor's library is not in this kit: its hash is known, its bytes are stood in for
            left = b"stand-in for a contributor library"
            saved = dict(R.KNOWN_LIBS)
            R.KNOWN_LIBS[c.sha256(left)] = next(iter(EARLIER_LIBS.values()))
        else:
            saved = None
        try:
            s, sim, stopped = R.simulate(lib, R.body_run, files={lp: left})
            names, lr = R.sent(s), s.results["ct6"].get("leftover_removed") or {}
            check(not stopped and not sim.unexpected and names.count(D) == 2 and names.count(W) == 1 and names.index(D) < names.index(W) and lp not in sim.fs
                  and sim.loads == 1 and lr.get("gone") and lr.get("sha256") == c.sha256(left) and s.results["ct6"]["library_on_camera_after"] is False,
                  "%s left on the camera: deleted first, then the normal run (one write, loaded once, gone afterwards)" % what)
        finally:
            if saved is not None:
                R.KNOWN_LIBS.clear()
                R.KNOWN_LIBS.update(saved)
    s, sim, stopped = R.simulate(lib, R.body_run, files={lp: other}, fault="sticky")
    check(stopped and W not in R.sent(s) and R.sent(s).count(D) == 1 and sim.fs.get(lp) == other, "a left library the camera will not delete: stops, nothing written")
    named = b"a file named with --remove-library"
    saved = dict(R.KNOWN_LIBS)
    try:
        R.KNOWN_LIBS[c.sha256(named)] = "the file named with --remove-library"
        s, sim, stopped = R.simulate(lib, R.body_run, files={lp: named})
        check(not stopped and R.sent(s).count(D) == 2 and R.sent(s).count(W) == 1 and lp not in sim.fs, "--remove-library with the file's SHA-256: deleted, then the normal run")
        s, sim, stopped = R.simulate(lib, R.body_run, files={lp: named + b"!"})
        check(stopped and W not in R.sent(s) and D not in R.sent(s) and c.sha256(named + b"!") in stopped, "--remove-library with another SHA-256: stops, nothing deleted, the file's SHA-256 is shown")
    finally:
        R.KNOWN_LIBS.clear()
        R.KNOWN_LIBS.update(saved)
    s, sim, stopped = R.simulate(lib, R.body_remove_only, files={lp: other})
    check(not stopped and R.sent(s).count(D) == 1 and W not in R.sent(s) and lp not in sim.fs and s.results["ct6"]["library_on_camera_after"] is False,
          "--remove-only: deletes another step's library of this kit too, writes nothing")
    s, sim, stopped = R.simulate(lib, R.body_remove_only, files={lp: b"someone else's"})
    check(stopped and D not in R.sent(s) and lp in sim.fs, "--remove-only: leaves a file that is none of this kit's")
    check(set(EARLIER_LIBS) <= set(R.KNOWN_LIBS) and all(sha in R.KNOWN_LIBS for _, sha in PINS.values()) and not set(EARLIER_LIBS) & {sha for _, sha in PINS.values()},
          "every library of this kit (%d) and of the contributor's kit (%d) is one a run may delete" % (len(PINS), len(EARLIER_LIBS)))
    check(len(R.refusals(lib)) == 15, "the guard refuses the 15 listed packets (changed library, other paths, backup, flash and debug writes ...)")
    return done


def report(session, facts, which):
    f = facts["s3"]
    if which in WRITE_STEPS:
        lines = ["A6700 2.00 step %s: %s" % (which, f["what"]), "OUTCOME: %s" % f["outcome"], str(f["outcome_line"])]
        if f.get("timing_variant"):
            lines.append(f["timing_variant"])
        lines += ["  " + ln for ln in f["problem_lines"]]
        session.save_bytes("a6700_report.txt", ("\n".join(lines) + "\n").encode())
        for ln in lines:
            session.say(ln)
        return
    lines = ["A6700 2.00 %s, %s" % (which, time.strftime("%Y-%m-%d %H:%M:%S")), f["header"], f["verdict"],
             "identity: %d same, %d differ" % (f["identity_same"], f["identity_differs"]),
             "kernel: %s" % f["kernel_version"], "command line: %s" % f["kernel_command_line"],
             "encoder side: %s" % f["encoder_state"]]
    for s in f["coprocessor_sites"]:
        lines.append("  coprocessor %-22s %s len %-4d %s%s" % (s["name"], s["address"], s["length"], s["state"], "" if s["shown"] is None else "  (" + s["shown"] + ")"))
    lines.append("stored records: " + ", ".join("%s %s" % kv for kv in f.get("stored_records", {}).items()))
    lines += ["  " + ln for ln in f["avcam_guards"]]
    lines.append("  libmpr.so spans: %(spans)d, %(stock)d stock, %(other)d in no known state; av-cam.bin spans: " % f["libmpr"] + "%(spans)d, %(stock)d stock, %(other)d in no known state" % f["avcam"])
    for step, v in f["encoder_designs"].items():
        lines.append("  %-4s %-28s %s (%d of %d spans hold its bytes)" % (step, v["design"], v["state"], v["spans_holding_it"], v["of"]))
    lines.append("  playback words (optional steps): %(stock)d stock, %(target)d applied, %(other)d other" % f["playback_words"])
    lines += ["problem lines:"] + ["  " + ln for ln in f["problem_lines"]] if f["problem_lines"] else ["no problem lines"]
    d = f.get("decoded")
    if d:
        sr = d.get("sensor_registers")
        if sr:
            lines.append("sensor register shadow: closest matrix column %d (%d of %d rows equal; columns with the same score %s; modes %s); the sensor steps' rows in that column: %s"
                         % (sr["closest_column"], sr["rows_equal_per_column"][sr["closest_column"]], sr["rows"], sr["columns_with_the_same_score"], ", ".join(sr["modes_using_it"]),
                            "; ".join("%s %d stock, %d applied of %d" % (k, v["stock"], v["applied"], v["of"]) for k, v in sr["design_rows"].items()) or "none"))
        mx = d.get("matrix")
        if mx:
            lines.append("register matrix: every other byte as the file: %s; %s" % (mx["other_bytes_as_file"], "; ".join("%s cells %d stock, %d applied of %d" % (k, v["stock"], v["applied"], v["of"])
                                                                                                                 for k, v in mx["steps"].items())))
        zero = [m for m, v in d.get("stored_records", {}).items() if v["all_zero"]]
        same = [m for m, v in d.get("stored_records", {}).items() if not v["bytes_differing_from_emulation"]]
        systems = sorted({v["closest_emulation"] for v in d.get("stored_records", {}).values()})
        lines.append("stored drive-parameter records: %d read, %d equal to the emulated ones (%s), %d all zero" % (len(d.get("stored_records", {})), len(same), "/".join(systems), len(zero)))
        for m, v in d.get("design_mode_windows", {}).items():
            lines.append("  mode %s: %s; window %d rows from row %d, %d phase-detect rows, sampling %s" % (m, v["state"], v["window"][0], v["window"][1], v["pdaf_rows"], v["sampling_ratio"]))
        if d.get("size_table"):
            lines.append("movie size table: " + "; ".join("%dx%d id %#x" % tuple(r) for r in d["size_table"]))
        for key, text in (("raw_write_buffer_words", "raw write buffer words (memory manager)"), ("output_words", "output-size word"), ("k16_words", "5.76K coprocessor words")):
            if d.get(key):
                lines.append("%s: %d stock, %d applied, %d other (%s)" % (text, d[key]["stock"], d[key]["new"], d[key]["other"], " ".join(d[key]["held"])))
        dp = d.get("display")
        if dp:
            lines.append("display (what the screen step changes):")
            if "panel_types" in dp:
                t = dp["panel_types"]
                lines.append("  panel types: rear %d (%s), second %d (%s)" % (t["rear"], t["rear_aspect"], t["second"], t["second_aspect"]))
            if "fit_16x9_picture" in dp:
                lines.append("  a 16:9 picture, fit words (3 letterbox, 0 fill): %s" % ", ".join("%s %d" % kv for kv in dp["fit_16x9_picture"].items()))
            if "screen_words" in dp:
                lines.append("  screen step words: %(stock)d stock, %(new)d applied, %(other)d other" % dp["screen_words"])
            for t, rw in dp.get("frame_rectangles_16x9_picture", {}).items():
                lines.append("  frame table %s: %s" % (t, ", ".join("%s %s" % kv for kv in rw.items())))
    if "main_log_lines" in f:
        lines.append("main-processor log: %d lines copied (in the result file)" % f["main_log_lines"])
    session.save_bytes("a6700_report.txt", ("\n".join(lines) + "\n").encode())
    for ln in lines[:9] + lines[-6:]:
        session.say(ln)


def last_saved_sha():
    """The SHA-256 of the result the newest saved session of this kit fetched, or None."""
    root = c.PRIVATE_ROOT
    if not root.is_dir():
        return None
    for folder in sorted((p for p in root.iterdir() if p.is_dir() and p.name.startswith("CT6_")), reverse=True):
        try:
            return json.loads((folder / "manifest.json").read_text(encoding="utf8"))["results"]["ct6"]["result"]["sha256"]
        except (OSError, KeyError, TypeError, ValueError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=sorted(PINS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--remove-only", action="store_true")
    ap.add_argument("--clear-result", metavar="SHA256", help="first delete the result file of an earlier run from the RAM disk, only if its SHA-256 is this")
    ap.add_argument("--remove-library", metavar="SHA256", help="a libJit.so left on the camera's service partition that is none of this kit's: delete it first, "
                                                               "only if its SHA-256 is this (a library of this kit or of the contributor's kit is deleted without being named)")
    ap.add_argument("--firmware-shown")
    ap.add_argument("--writes-memory", action="store_true", help="needed for a write step (%s): it changes the running camera's memory" % ", ".join(WRITE_STEPS))
    a = ap.parse_args()
    if a.which in WRITE_STEPS and a.go and not (a.dry_run or a.selftest) and not a.writes_memory:
        raise SystemExit("%s is a write step: %s. It needs --writes-memory as well. Use a6700_apply.py. Nothing was sent." % (a.which, WRITE_STEPS[a.which][2]))
    if a.remove_library:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", a.remove_library):
            raise SystemExit("--remove-library takes the 64 hexadecimal digits of the file's SHA-256 (the stopped run prints them). Nothing was sent.")
        EXTRA_LIBS[a.remove_library.lower()] = "the file named with --remove-library"
    lib = use(a.which)
    if a.dry_run or a.selftest:
        if a.selftest:                              # --dry-run and --selftest win over --go (the launchers always pass --go): nothing is sent
            for line in selftest(lib):
                print("PASS  " + line)
            print("all checks passed; nothing was sent to any device")
        else:
            print("\n".join(R.dry_run_lines(lib)))
        return
    if not a.go or a.firmware_shown != FIRMWARE:
        raise SystemExit("A live run needs --go and --firmware-shown %s (the version the camera's menu shows). Nothing was sent." % FIRMWARE)
    R.refusals(lib)
    selftest(lib)                                   # the flow must pass on the simulated camera on the day, before the real one
    import ct1_stage2_service as service
    # A result left on the RAM disk by the run before stops a new run. Without --clear-result the newest result saved on this PC is named: the
    # runner deletes the camera's file only if its SHA-256 is that one, i.e. only a result already here.
    R.CLEAR_SHA = a.clear_result or last_saved_sha()
    body = R.body_remove_only if a.remove_only else R.body_run
    with c.Session("remove_only" if a.remove_only else "a6700_%s" % a.which, test="CT6") as session:
        session.results.update(firmware_shown_on_camera=a.firmware_shown, model=MODEL, which=a.which, library_sha256=PINS[a.which][1],
                               pc={"platform": platform.platform(), "python": sys.version.split()[0]})
        inner = service.connect(session)
        try:
            R.service_session(session, inner, lambda cam: body(session, cam, lib), lib)
            facts = session.results.get("ct6", {}).get("result")
            if facts and not a.remove_only:
                pages = facts.pop("_pages", {})
                for addr, (name, blob) in sorted(pages.items()):
                    session.save_bytes("cp_%s_%08x.bin" % (name, addr), blob)
                report(session, facts, a.which)
        finally:
            time.sleep(3)
            c.print_pnp(session, "after the stop request")
            out = session.results.get("ct6", {})
            print("Library sent: %s. On the camera now: %s." % (
                "yes" if out.get("library_sent") else "no",
                {False: "no (confirmed)", True: "YES", None: "not sent" if not out.get("library_sent") and not a.remove_only else "UNKNOWN"}[out.get("library_on_camera_after")]))
            lr = out.get("leftover_removed")
            if lr:
                print("A library an earlier session had left on the camera (%s) was %s." % (lr["name"], "deleted first" if lr["gone"] else "NOT deleted: it is still there"))
            if a.which in WRITE_STEPS:
                print("This was a WRITE step. A cold boot (battery out for 10 seconds) undoes everything written. Whether the power switch alone does on the A6700 is not known (on the A7 IV it does not, on the A7S III it does): keep the camera on between steps.")
            else:
                print("Nothing on the camera was changed. Unplug and replug the USB cable before another run; a cold boot (battery out) clears the result file.")


if __name__ == "__main__":
    main()
