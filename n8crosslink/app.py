"""Hauptprogramm: Bridge (Router + Netze + Vocoder) und Webserver in einem Prozess."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

from . import __version__
from .avatars import AvatarStore
from .core import Router
from .db import Database
from .dmr.port import DmrPort
from .frn import FrnPort
from .idlists import IdLists
from .n8_crash import CrashWatch
from .system import System
from .updater import Updater
from . import vocoder as _vocoder_mod
from .vocoder import Vocoder
from .zello import ZelloPort

log = logging.getLogger("app")

# Welcher Teil der Bridge steckt in einem Stack? (Absturz-Befunde: „hängt in Datenbank ← DMR“)
SERVICES = [
    (r"/n8crosslink/frn(_errorlog)?\.py$", "FRN"), (r"/n8crosslink/zello\.py$", "Zello"), (r"/n8crosslink/dmr/", "DMR"),
    (r"/n8crosslink/(vocoder|ambe_worker)\.py$", "Vocoder"), (r"/n8crosslink/audio/", "Audio (GSM/Opus/DSP)"),
    (r"/n8crosslink/db\.py$", "Datenbank"), (r"/n8crosslink/idlists\.py$", "ID-Listen"), (r"/n8crosslink/avatars\.py$", "Avatare"),
    (r"/n8crosslink/updater\.py$", "Update-Prüfung"), (r"/n8crosslink/(announce|preview)\.py$", "Ansage (espeak)"),
    (r"/n8crosslink/backup\.py$", "Backup"), (r"/n8crosslink/core\.py$", "Router"), (r"/n8crosslink/web/", "Webinterface"),
    (r"/(uvicorn|starlette|fastapi|websockets)/", "Webinterface"), (r"/n8crosslink/(app|system|n8_admin)\.py$", "Bridge"),
]


def sd_notify(msg: str) -> None:
    """systemd-Benachrichtigung (READY=1, WATCHDOG=1, STATUS=…) ohne Zusatzpaket."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    import socket
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.sendto(msg.encode(), addr)
    except OSError:
        pass


class Bridge:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.cfg = db.load_config()
        self.router = Router(db, self.cfg)
        self.vocoder: Vocoder | None = None
        self.pub_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        data_dir = os.path.dirname(os.path.abspath(db.path))
        self.idlists = IdLists(self.router)
        self.avatars = AvatarStore(self.router)
        self.updater = Updater(self.router, data_dir)
        self.system = System(data_dir)
        self.router.idlists = self.idlists
        self.router.avatars = self.avatars
        self.router.updater = self.updater
        self.voc_offline_since: float | None = None
        self.wd_interval = 10.0
        self.bg_tasks: list[asyncio.Task] = []
        self.crash: CrashWatch | None = None

    def crash_note(self, service: str, reason: str, detail: str = "", kind: str = "task") -> None:
        if self.crash is not None:
            self.crash.note(service, reason, detail, kind=kind)

    async def start(self) -> None:
        async with self.lock:
            await self._start()

    async def _start(self) -> None:
        self.cfg = self.db.load_config()
        r = self.router
        r.cfg = self.cfg
        r.active = None
        r.blocked.clear()
        r.guard_until.clear()
        self.vocoder = Vocoder(self.cfg["vocoder"])
        r.vocoder = self.vocoder
        r.ports = {
            "frn": FrnPort(r, self.cfg),
            "dmr": DmrPort(r, self.cfg, self.vocoder),
            "zello": ZelloPort(r, self.cfg),
        }
        if self.cfg["dmr"].get("enabled"):
            await self.vocoder.start()
            v = self.vocoder.status()
            r.event("info" if v["online"] else "warn",
                    f"Vocoder {v['name']}: {'bereit' if v['online'] else 'nicht erreichbar'} {v['product']}".strip())
        for p in r.ports.values():
            await p.start()
        if self.pub_task is None or self.pub_task.done():
            self.pub_task = asyncio.create_task(r.publisher())
        r.notify()

    async def stop(self) -> None:
        r = self.router
        if r.active:
            r._finish(r.active, status="restart")
        for p in r.ports.values():
            await p.stop()
        if self.vocoder:
            await self.vocoder.stop()

    async def restart(self) -> None:
        async with self.lock:
            self.router.event("info", "Bridge wird mit neuen Einstellungen neu gestartet …")
            await self.stop()
            await asyncio.sleep(0.5)
            await self._start()

    async def restart_port(self, key: str, reason: str) -> None:
        p = self.router.ports.get(key)
        if p is None:
            return
        p.wd_restarts += 1
        p.last_wd_reason = reason
        self.router.event("warn", f"Watchdog: {p.label} wird neu aufgebaut ({reason})")
        if self.router.active and (self.router.active.source is p):
            self.router._finish(self.router.active, status="watchdog")
        await p.stop()
        p.offline_since = __import__("time").time()
        await p.start()

    async def watchdog(self) -> None:
        """Überwacht alle Verbindungen, den Vocoder und meldet sich beim systemd-Watchdog."""
        import time as _t
        while True:
            await asyncio.sleep(self.wd_interval)
            if self.lock.locked():
                continue
            limit = float(self.cfg["general"].get("watchdog_offline_s", 120))
            try:
                for key, p in list(self.router.ports.items()):
                    if not p.enabled:
                        continue
                    t = p.main_task
                    if t is not None and t.done():
                        exc = None if t.cancelled() else t.exception()
                        if exc is not None and self.crash is not None:
                            self.crash.note_exc(exc, f"Verbindungsschleife {p.label} abgestürzt: {type(exc).__name__}: {exc}"[:300],
                                                service=p.label)
                        elif self.crash is not None:
                            self.crash_note(p.label, f"Verbindungsschleife {p.label} unerwartet beendet")
                        await asyncio.wait_for(self.restart_port(key, f"Verbindungsschleife beendet: {exc!r}" if exc else
                                                                 "Verbindungsschleife beendet"), 45)
                    elif not p.online and p.offline_since and _t.time() - p.offline_since > limit:
                        await asyncio.wait_for(self.restart_port(key, f"seit {int(_t.time() - p.offline_since)} s offline"), 45)
                v = self.vocoder
                if v is not None and v.running is not None and self.cfg["dmr"].get("enabled") and v.mode != "none":
                    if v.online:
                        self.voc_offline_since = None
                    elif self.voc_offline_since is None:
                        self.voc_offline_since = _t.time()
                    elif _t.time() - self.voc_offline_since > float(self.cfg["vocoder"].get("vocoder_restart_s", 20)):
                        self.voc_offline_since = _t.time()
                        await asyncio.wait_for(self.recover_vocoder(v), 45)
                if self.pub_task is not None and self.pub_task.done():
                    exc = None if self.pub_task.cancelled() else self.pub_task.exception()
                    self.crash_note("Router", f"Live-Daten (Publisher) beendet: {exc!r}" if exc else "Live-Daten (Publisher) beendet")
                    self.pub_task = asyncio.create_task(self.router.publisher())
                online = [p.label for p in self.router.ports.values() if p.enabled and p.online]
                sd_notify("STATUS=" + (", ".join(online) + " online" if online else "keine Verbindung"))
            except asyncio.TimeoutError:
                self.crash_note("Bridge", "Watchdog: Neuaufbau dauerte länger als 45 s – abgebrochen, nächster Versuch folgt",
                                kind="stall")
            except Exception as e:  # noqa: BLE001
                log.exception("Watchdog: %s", e)
                if self.crash is not None:
                    self.crash.note_exc(e, f"Watchdog: {type(e).__name__}: {e}"[:300], service="Bridge", kind="intern")

    async def recover_vocoder(self, v: Vocoder) -> None:
        """Hängender oder ausgefallener Vocoder: komplett neu öffnen."""
        self.router.event("warn", f"Watchdog: Vocoder ({v.mode}) antwortet nicht – wird neu geöffnet")
        await v.reopen()

    def start_background(self) -> None:
        self.bg_tasks.append(asyncio.create_task(self.sd_ping(), name="systemd-watchdog"))
        for name, factory in (("Aufräumen", self.housekeeping), ("Watchdog", self.watchdog), ("ID-Listen", self.idlists.loop),
                              ("Avatare", self.avatars.loop), ("Update-Prüfung", self.updater.loop)):
            self.bg_tasks.append(asyncio.create_task(self.supervise(name, factory), name=name))

    async def sd_ping(self) -> None:
        """Lebenszeichen für den systemd-Watchdog – eigene, schlanke Aufgabe: ein langsamer Neuaufbau einer Verbindung
        hält es nicht mehr auf. Bleibt es trotzdem 60 s aus, steht die Event-Loop wirklich (der Hänger-Wächter hält fest, wo)."""
        while True:
            sd_notify("WATCHDOG=1")
            await asyncio.sleep(10)

    async def supervise(self, name: str, factory) -> None:  # noqa: ANN001
        """Hintergrundaufgabe am Leben halten: stirbt sie, wird das festgehalten und sie startet nach 5 s neu."""
        while True:
            try:
                await factory()
                self.crash_note(name, f"Hintergrundaufgabe {name} hat sich beendet – wird neu gestartet")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("%s: %s", name, e)
                if self.crash is not None:
                    self.crash.note_exc(e, f"Hintergrundaufgabe {name} abgestürzt: {type(e).__name__}: {e}"[:300], service=name)
            await asyncio.sleep(5)

    async def housekeeping(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.db.cleanup, int(self.cfg["general"].get("keep_days", 90)))
            except Exception as e:  # noqa: BLE001
                log.warning("Aufräumen: %s", e)
            await asyncio.sleep(6 * 3600)


def main() -> None:
    ap = argparse.ArgumentParser(prog="n8crosslink", description="N8 Crosslink – FRN · DMR · Zello")
    ap.add_argument("--db", default=os.environ.get("N8X_DB", "/opt/n8crosslink/data/crosslink.db"))
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)-8s %(message)s", stream=sys.stdout)
    db = Database(args.db)
    if db.migrate_vocoder():
        log.info("Vocoder auf den N8schicht-Vocoder umgestellt")
    cfg = db.load_config()
    host = args.host or cfg["general"].get("web_host", "0.0.0.0")
    port = args.port or int(cfg["general"].get("web_port", 8080))

    import uvicorn

    from .web.server import create_app
    bridge = Bridge(db)
    app = create_app(bridge)
    from .web.n8_security import UVICORN_KWARGS
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", proxy_headers=True,
                            forwarded_allow_ips="127.0.0.1", **UVICORN_KWARGS)   # kein "server: uvicorn"
    server = uvicorn.Server(config)

    async def runner() -> None:
        bridge.crash = CrashWatch(os.path.dirname(os.path.abspath(db.path)), app="N8 Crosslink", unit="n8crosslink.service",
                                  services=SERVICES)
        bridge.crash.install()
        _vocoder_mod.CRASH_NOTE = bridge.crash.note
        await bridge.start()
        bridge.start_background()
        log.info("N8 Crosslink %s – Dashboard auf http://%s:%s", __version__, host, port)

        async def ready() -> None:
            while not server.started:
                await asyncio.sleep(0.2)
            sd_notify("READY=1")
        asyncio.create_task(ready())
        try:
            await server.serve()
        finally:
            sd_notify("STOPPING=1")
            for t in bridge.bg_tasks:
                t.cancel()
            await bridge.stop()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: setattr(server, "should_exit", True))
        except NotImplementedError:
            pass
    loop.run_until_complete(runner())


if __name__ == "__main__":
    main()
