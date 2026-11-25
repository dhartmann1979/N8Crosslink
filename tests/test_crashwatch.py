#!/usr/bin/env python3
"""Absturz-Erkennung: Befunde der Anwendung (n8_crash), Hänger der Event-Loop, Vocoder-Prozess, Liste im Webinterface (n8_admin).

Aufruf:  python3 tests/test_crashwatch.py
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from n8crosslink import vocoder as V  # noqa: E402
from n8crosslink.app import SERVICES  # noqa: E402
from n8crosslink.n8_admin import N8Admin  # noqa: E402
from n8crosslink.n8_crash import CrashWatch  # noqa: E402

ok = True


def check(name: str, cond: bool, info: str = "") -> None:
    global ok
    print(("✓ " if cond else "✗ ") + name + (f"  ({info})" if info else ""))
    ok = ok and bool(cond)


def entries(d: str) -> list[dict]:
    try:
        return [json.loads(x) for x in open(os.path.join(d, "crashes.jsonl"), encoding="utf-8")]
    except OSError:
        return []


def blocking_db_call() -> None:
    time.sleep(3.2)          # steht für eine lange Datenbanksperre in der Event-Loop


async def main() -> None:
    d = tempfile.mkdtemp()
    w = CrashWatch(d, app="Test", unit="test.service",
                   services=SERVICES + [(r"/tests/test_crashwatch\.py$", "Testteil")], stall_s=1.0)
    w.install()

    # Zuordnung zum Teil der Anwendung
    stack = ('File "/opt/n8crosslink/n8crosslink/app.py", line 1\nFile "/opt/n8crosslink/n8crosslink/dmr/port.py", line 290\n'
             'File "/opt/n8crosslink/n8crosslink/db.py", line 430\nFile "/usr/lib/python3/sqlite3/x.py", line 1')
    check("Zuordnung innerste Stelle + Aufrufer", w.service_of(stack) == "Datenbank ← DMR", w.service_of(stack))
    check("Zuordnung ohne Treffer -> Vorgabe", w.service_of('File "/usr/lib/x.py"', "N8") == "N8")
    check("services.json für den crash-hook", json.load(open(os.path.join(d, "crash", "services-test.service.json")))[0][1] == "FRN")
    check("faulthandler schreibt nach crash/fault.log", "gestartet" in open(os.path.join(d, "crash", "fault-test.service.log")).read())

    # eigene Meldung + Doppelte
    cid = w.note("FRN", "Verbindungsschleife abgestürzt", "Traceback …", kind="task")
    w.note("FRN", "Verbindungsschleife abgestürzt", "Traceback …", kind="task")
    e = entries(d)
    check("note() schreibt crashes.jsonl + Protokoll", len(e) == 1 and e[0]["id"] == cid and os.path.exists(os.path.join(d, "crash", cid + ".log")))

    # Ausnahme in einer Task, die niemand abholt
    async def boom() -> None:
        raise RuntimeError("Testfehler in Task")
    t = asyncio.ensure_future(boom())
    await asyncio.sleep(0.05)
    del t
    import gc
    gc.collect()
    await asyncio.sleep(0.05)
    e = entries(d)
    check("unbehandelte Task-Ausnahme wird festgehalten", any(x["kind"] == "task" and "Testfehler" in x["reason"] for x in e),
          str([x["reason"] for x in e]))
    check("…und dem Testteil zugeordnet", any(x["service"] == "Testteil" for x in e if "Testfehler" in x["reason"]))

    # Hänger: Event-Loop 3,2 s blockiert -> last.json während des Hängers, danach Befund „stall“
    seen_last = {}

    def peek() -> None:
        time.sleep(2.2)
        p = os.path.join(d, "crash", "last-test.service.json")
        if os.path.exists(p):
            seen_last.update(json.load(open(p)))
    import threading
    threading.Thread(target=peek, daemon=True).start()
    blocking_db_call()
    await asyncio.sleep(1.6)
    check("Hänger: crash/last.json während des Hängers", seen_last.get("kind") == "stall" and seen_last.get("service") == "Testteil",
          str(seen_last.get("reason")))
    st = [x for x in entries(d) if x["kind"] == "stall"]
    check("Hänger: Befund nach dem Hänger", len(st) == 1 and st[0]["service"] == "Testteil", str(st[:1]))
    check("Hänger: Stack im Protokoll", "blocking_db_call" in open(os.path.join(d, "crash", st[0]["log"])).read() if st else False)
    check("Hänger: last.json danach gelöscht", not os.path.exists(os.path.join(d, "crash", "last-test.service.json")))

    # Vocoder-Prozess stürzt ab (SIGSEGV) -> Befund „helper“ mit Signal
    lib = V.find_n8vocoder_lib()
    if lib:
        V.CRASH_NOTE = w.note
        c = V.N8VocoderWorker(lib, V.effective_options({}))
        r1 = await c.call(b"D", bytes(9))
        os.kill(c.proc.pid, signal.SIGSEGV)
        await asyncio.sleep(0.3)
        r2 = await c.call(b"D", bytes(9))
        await c.close()
        h = [x for x in entries(d) if x["kind"] == "helper"]
        check("Vocoder-Absturz erkannt (Signal 11)", bool(h) and "SIGSEGV" in h[-1]["reason"], h[-1]["reason"] if h else "kein Befund")
        check("Vocoder läuft danach weiter", r1 is not None and r2 is not None and c.restarts >= 1, f"Neustarts {c.restarts}")
    else:
        print("– N8schicht-Vocoder nicht gebaut – Teil übersprungen")

    # Webinterface: Liste, ungelesen, Protokoll, gelesen
    a = N8Admin(d)
    lst = a.crashes()
    check("crashes(): ungelesene gezählt", lst["unacked"] == len(entries(d)) and lst["items"][0]["new"], f"{lst['unacked']}")
    check("crashes(): neueste zuerst", lst["items"][0]["time"] >= lst["items"][-1]["time"])
    check("crash_log() liefert Text", "Verbindungsschleife" in (a.crash_log(cid) or ""))
    check("crash_log() lehnt fremde Namen ab", a.crash_log("../../etc/passwd") is None)
    a.crash_ack(ids=[cid])
    check("einzeln als gelesen markiert", a.crashes()["unacked"] == len(entries(d)) - 1)
    a.crash_ack(all_=True)
    check("alle als gelesen markiert", a.crashes()["unacked"] == 0)
    w.note("DMR", "neuer Befund nach dem Lesen", kind="task")
    check("neuer Befund danach wieder ungelesen", a.crashes()["unacked"] == 1)

    # eigener Dienst neu starten: erst antworten, dann auslösen (kein „Fehler -15“ mehr)
    import n8crosslink.n8_admin as NA
    json.dump({"units": [{"unit": "selbst.service", "actions": ["restart"]}], "systemctl": "/bin/true"}, open(os.path.join(d, "n8-admin.json"), "w"))
    calls = []

    async def fake_sudo(*cmd, timeout=60):
        calls.append(cmd)
        return 0, ""
    a2 = NA.N8Admin(d)
    a2._sudo = fake_sudo
    NA.own_unit, real_own = (lambda: "selbst.service"), NA.own_unit
    ok_, msg = await a2.unit_action("selbst.service", "restart")
    check("eigener Neustart: sofort ok, noch nicht ausgelöst", ok_ and not calls, msg)
    await asyncio.sleep(1.3)
    check("eigener Neustart: nach 1 s ausgelöst", len(calls) == 1 and calls[0][-1] == "selbst.service")
    NA.own_unit = real_own


def hook_test() -> None:
    """scripts/n8-admin.sh crash-hook mit nachgebautem systemctl/journalctl (nur als root – das Skript verlangt root)."""
    import shutil
    import subprocess
    if os.geteuid() != 0 or not shutil.which("bash"):
        print("– crash-hook: nicht als root – übersprungen")
        return
    root = os.path.join(os.path.dirname(__file__), "..")
    t = tempfile.mkdtemp()
    app, data, bin_ = os.path.join(t, "app"), os.path.join(t, "app", "data"), os.path.join(t, "bin")
    for x in (os.path.join(app, "scripts"), os.path.join(data, "crash"), bin_):
        os.makedirs(x)
    shutil.copy(os.path.join(root, "scripts", "n8-admin.sh"), os.path.join(app, "scripts"))
    open(os.path.join(app, "scripts", "n8-admin.conf"), "w").write(
        f'N8_ID=demo; N8_NAME="Demo"; N8_MAIN_UNIT=demo.service; APP={app}; SVC_USER=root\n'
        f'n8_layout() {{ STATE_DIR="{data}"; N8_DATA_DIRS=("{data}"); }}\n')
    open(os.path.join(bin_, "systemctl"), "w").write('#!/bin/bash\ncase "$1" in list-jobs) [[ -n "$JOB" ]] && echo "1 $JOB restart running";; '
                                                    'show) echo always;; esac; exit 0\n')
    open(os.path.join(bin_, "journalctl"), "w").write('#!/bin/bash\necho "demo.service: Watchdog timeout (limit 1min)!"\n')
    for f in ("systemctl", "journalctl"):
        os.chmod(os.path.join(bin_, f), 0o755)
    w = CrashWatch(data, app="Demo", unit="demo.service", services=SERVICES)
    w._mk()
    json.dump([[rx.pattern, lab] for rx, lab in w.services], open(os.path.join(data, "crash", w.f_svcs), "w"))
    open(os.path.join(data, "crash", w.f_fault), "w").write(
        "\n=== Demo gestartet ===\nFatal Python error: Aborted\n\nCurrent thread 0x1 (most recent call first):\n"
        '  File "/opt/n8crosslink/n8crosslink/db.py", line 430 in userdb_lookup\n  File "/opt/n8crosslink/n8crosslink/dmr/port.py", line 290 in _talker\n')
    env = {**os.environ, "PATH": bin_ + ":" + os.environ["PATH"]}
    sh = os.path.join(app, "scripts", "n8-admin.sh")
    run = lambda **e: subprocess.run(["bash", sh, "crash-hook", "demo.service"], env={**env, **e}, capture_output=True, text=True, timeout=60)
    run(SERVICE_RESULT="watchdog", EXIT_CODE="dumped", EXIT_STATUS="ABRT")
    run(SERVICE_RESULT="success", EXIT_CODE="killed", EXIT_STATUS="TERM", JOB="demo.service")      # geplant: nichts festhalten
    run(SERVICE_RESULT="exit-code", EXIT_CODE="exited", EXIT_STATUS="1")
    e = entries(data)
    check("crash-hook: Watchdog festgehalten und zugeordnet", len(e) >= 1 and e[0]["kind"] == "watchdog" and e[0]["service"] == "Datenbank ← DMR",
          str(e[:1]))
    check("crash-hook: geplanter Neustart übergangen", len(e) == 2 and e[1]["kind"] == "crash" and "Fehlercode 1" in e[1]["reason"], str(len(e)))
    check("crash-hook: Protokoll mit Journal und Python-Stack", "Watchdog timeout" in open(os.path.join(data, "crash", e[0]["log"])).read()
          and "userdb_lookup" in open(os.path.join(data, "crash", e[0]["log"])).read() if e else False)
    out = subprocess.run(["bash", sh, "crashes"], env=env, capture_output=True, text=True, timeout=30).stdout
    check("crashes auf der Konsole", "Datenbank ← DMR" in out)


asyncio.run(main())
hook_test()
print("OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
