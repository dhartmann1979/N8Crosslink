"""Hauptprogramm: Bridge (Router + Netze + Vocoder) und Webserver in einem Prozess."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

from . import __version__
from .core import Router
from .db import Database
from .dmr.port import DmrPort
from .frn import FrnPort
from .vocoder import Vocoder
from .zello import ZelloPort

log = logging.getLogger("app")


class Bridge:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.cfg = db.load_config()
        self.router = Router(db, self.cfg)
        self.vocoder: Vocoder | None = None
        self.pub_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()

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

    async def housekeeping(self) -> None:
        while True:
            try:
                self.db.cleanup(int(self.cfg["general"].get("keep_days", 90)))
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
    cfg = db.load_config()
    host = args.host or cfg["general"].get("web_host", "0.0.0.0")
    port = args.port or int(cfg["general"].get("web_port", 8080))

    import uvicorn

    from .web.server import create_app
    bridge = Bridge(db)
    app = create_app(bridge)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", proxy_headers=True,
                            forwarded_allow_ips="*")
    server = uvicorn.Server(config)

    async def runner() -> None:
        await bridge.start()
        hk = asyncio.create_task(bridge.housekeeping())
        log.info("N8 Crosslink %s – Dashboard auf http://%s:%s", __version__, host, port)
        try:
            await server.serve()
        finally:
            hk.cancel()
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
