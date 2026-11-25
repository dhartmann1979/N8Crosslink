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
    check("services.json für den crash-hook", json.load(open(os.path.join(d, "crash", "services.json")))[0][1] == "FRN")
    check("faulthandler schreibt nach crash/fault.log", "gestartet" in open(os.path.join(d, "crash", "fault.log")).read())

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
        p = os.path.join(d, "crash", "last.json")
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
    check("Hänger: last.json danach gelöscht", not os.path.exists(os.path.join(d, "crash", "last.json")))

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


asyncio.run(main())
print("OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
