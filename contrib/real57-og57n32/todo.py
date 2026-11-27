"""Varios pasos de escritura del kit en UNA sesion USB (una sola conexion del cable).

  python todo.py L13 T5 L16 L19 S16 --simular
  python todo.py L13 T5 L16 L19 S16 --go --writes-memory --firmware-shown 2.00

Cada paso es la misma biblioteca fijada del kit, enviada con el mismo body_run y con una guardia nueva que solo admite esa
biblioteca (la guardia del kit sigue permitiendo una sola escritura de fichero por guardia). Para en el primer paso que no
termine en DONE / NOTHING TO DO. Probado en una A6700 real (fw 2.00): cinco pasos DONE en una sola sesion."""
import argparse
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from correr import a6700_run as K  # noqa: E402  (correr anade H5/H6 y las rutas del kit)

R, c = K.R, K.c


def pasos_en_sesion(session, inner, steps, clear_sha):
    """Como R.service_session, pero con varios pasos entre la autenticacion y la orden de parada."""
    from pmca.usb.sony import SonySenserAuthDevice, SonySenserCamera, SonySenserDevice
    driver = c.GuardedDriver(inner, session, "senser")
    session.results["service_usb_id"] = "%04x:%04x" % driver.getId()
    auth = SonySenserAuthDevice(driver)
    session.say("Authenticating")
    auth.start()
    save = session.save_bytes
    done = session.results["steps"] = {}
    try:
        auth.authenticate()
        device = SonySenserDevice(driver)
        camera = SonySenserCamera(device)
        for n, step in enumerate(steps, 1):
            lib = K.use(step)
            session.say("===== paso %d de %d: %s" % (n, len(steps), step))
            session.save_bytes = lambda name, data, step=step: save("%s_%s" % (step, name), data)
            R.Guard(device, session, R.rules(lib), lib)
            R.CLEAR_SHA = clear_sha
            R.body_run(session, camera, lib)
            out = done[step] = session.results["ct6"]
            facts = out.get("result")
            if facts:
                facts.pop("_pages", None)
                K.report(session, facts, step)
            if not facts or not facts["s3"]["ok"] or not facts["header_ok"] or not facts["complete"]:
                raise c.StopTest("el paso %s no termino en DONE: no se envia ningun paso mas" % step)
            if out.get("library_on_camera_after") is not False:
                raise c.StopTest("no se ha confirmado el borrado de la biblioteca tras %s: no se envia ningun paso mas" % step)
            clear_sha = facts["sha256"]
    finally:
        session.save_bytes = save
        auth.stop()
        session.say("Stop request sent")


def simular(steps):
    """La camara simulada del kit. Dos casos: carga cada biblioteca; o solo ejecuta la primera (como si no recargara)."""
    import contextlib
    import io
    c.use_pmca()
    for solo_primera in (False, True):
        lib = K.use(steps[0])
        sim = R.make_sim(lib)
        base_handle = sim._handle

        def handle(pfunc, body, sim=sim, base_handle=base_handle, solo_primera=solo_primera):
            sim.rules = R.rules(R.LIB.read_bytes())          # las reglas del paso en curso
            if solo_primera and sim.loads >= 1:
                sim.fs.setdefault("/tmp_wbshd/readcheck_result.txt", None)
                keep = sim.fs["/tmp_wbshd/readcheck_result.txt"]
                if keep is None:                             # marcador: impide que el simulador cree el resultado
                    del sim.fs["/tmp_wbshd/readcheck_result.txt"]
                    real = R.run_helper
                    R.run_helper = lambda data: (None, "no recargada")
                    try:
                        answer = base_handle(pfunc, body)
                    finally:
                        R.run_helper = real
                    if sim.fs.get("/tmp_wbshd/readcheck_result.txt", b"") is None:
                        del sim.fs["/tmp_wbshd/readcheck_result.txt"]
                    return answer
            return base_handle(pfunc, body)

        sim._handle = handle
        session = c.Session("simulated", write=False, test="CT6")
        stopped = None
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                pasos_en_sesion(session, sim, steps, None)
            except c.StopTest as exc:
                stopped = str(exc)
        sent = [e["name"] for e in session.events if e["kind"] == "service_out"]
        ok = [s for s, v in session.results["steps"].items() if v.get("result", {}).get("s3", {}).get("ok")]
        print("caso %s: cargas %d, envios de biblioteca %d, pasos DONE %s, parada: %s, ordenes fuera de lista %d"
              % ("'solo ejecuta la primera'" if solo_primera else "'recarga cada vez'", sim.loads, sent.count("SET_FILE2"), ok, stopped, len(sim.unexpected)))
        assert not sim.unexpected and R.LIB_PATH.decode() not in sim.fs
        if solo_primera:
            assert ok == steps[:1] and stopped and sent.count("SET_FILE2") == 2
        else:
            assert ok == steps and not stopped and sim.loads == sent.count("SET_FILE2") == len(steps)
    print("simulacion correcta; no se ha enviado nada a ningun dispositivo")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+", choices=sorted(K.WRITE_STEPS))
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--writes-memory", action="store_true")
    ap.add_argument("--firmware-shown")
    a = ap.parse_args()
    if a.simular:
        simular(a.steps)
        return
    if not (a.go and a.writes_memory and a.firmware_shown == K.FIRMWARE):
        raise SystemExit("hacen falta --go --writes-memory --firmware-shown %s. No se ha enviado nada." % K.FIRMWARE)
    for step in a.steps:                                     # todas las comprobaciones del runner ANTES de conectar
        lib = K.use(step)
        R.refusals(lib)
        K.selftest(lib)
    clear = K.last_saved_sha()
    import ct1_stage2_service as service
    with c.Session("a6700_multi", test="CT6") as session:
        session.results.update(firmware_shown_on_camera=a.firmware_shown, model=K.MODEL, which="multi", steps_asked=a.steps,
                               pc={"platform": platform.platform(), "python": sys.version.split()[0]})
        inner = service.connect(session)
        try:
            pasos_en_sesion(session, inner, a.steps, clear)
        finally:
            time.sleep(3)
            c.print_pnp(session, "after the stop request")


if __name__ == "__main__":
    main()
