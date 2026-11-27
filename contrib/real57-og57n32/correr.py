"""El runner del kit (a6700_run.py, sin modificar) con dos pasos mas: H5 aplica og57n32_a6700_v2 (6K real, SIN PROBAR en ninguna
camara) y H6 lo deshace. Mismos argumentos que a6700_run.py; los demas pasos son los del kit."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = Path(r"a6700fw\a6700-open-gate-test\windows\tools\camera_tests\CT6_memory_read_check")
sys.path.insert(0, str(KIT))
import a6700_run  # noqa: E402

NEW = {"H5": ("7250203ef108cc5c37f471aedcc48cbe217cce6273ee98e703ef54bef303a0df", "apply og57n32_a6700_v2: UNTESTED real 5760x3840 first stage (52 table cells as T5, two new picture records, five stored records)"),
       "H6": ("f241862e81b37c350582cc31f08e08e46ebc6c462efca23c6a876df8a6b8dc0b", "put back og57n32_a6700_v2")}
for step, (sha, text) in NEW.items():
    name = str(HERE / "build" / ("libJit_a6700_%s.so" % step))
    a6700_run.WRITE_STEPS[step] = (name, sha, text)
    a6700_run.PINS[step] = (name, sha)
    a6700_run.LEVELS[step] = 1700 + int(step[1:])

if __name__ == "__main__":
    a6700_run.main()
