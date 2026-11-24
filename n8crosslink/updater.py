"""Updateprüfung (stündlich zur vollen Stunde) und „Update jetzt“.

Prüfung: Versionsnummer aus n8crosslink/__init__.py im GitHub-Repository (Branch main) wird mit der
laufenden Version verglichen; die Änderungen werden aus CHANGELOG.md gelesen.

„Update jetzt“: Der Dienst läuft absichtlich ohne root-Rechte. Er legt deshalb nur die Datei
data/update.request an. Die systemd-Path-Unit n8crosslink-update.path sieht das und startet
n8crosslink-update.service (als root), das update.sh ausführt: git pull, Installer im Update-Modus,
Dienst-Neustart. Fortschritt steht in data/update.log.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time

from . import __version__

log = logging.getLogger("updater")


def vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


class Updater:
    def __init__(self, router, data_dir: str) -> None:  # noqa: ANN001
        self.router = router
        self.data_dir = data_dir
        self.request_file = os.path.join(data_dir, "update.request")
        self.log_file = os.path.join(data_dir, "update.log")
        self.state = {"current": __version__, "latest": None, "available": False, "checked": None,
                      "error": "", "notes": "", "running": False}

    @property
    def g(self) -> dict:
        return self.router.cfg["general"]

    def raw_url(self, path: str) -> str:
        return f"https://raw.githubusercontent.com/{self.g.get('update_repo')}/{self.g.get('update_branch', 'main')}/{path}"

    async def loop(self) -> None:
        await asyncio.sleep(20)
        await self.check()                       # einmal kurz nach dem Start
        while True:
            now = time.time()
            nxt = (int(now // 3600) + 1) * 3600 + 5  # volle Stunde (+5 s)
            await asyncio.sleep(max(1, nxt - now))
            if self.g.get("update_check", True):
                await self.check()

    async def check(self) -> dict:
        import aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20),
                                             headers={"User-Agent": "N8-Crosslink updater",
                                                      "Cache-Control": "no-cache"}) as s:
                async with s.get(self.raw_url("n8crosslink/__init__.py")) as r:
                    r.raise_for_status()
                    text = await r.text()
                m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
                if not m:
                    raise ValueError("Versionsnummer nicht gefunden")
                latest = m.group(1)
                notes = ""
                if vtuple(latest) > vtuple(__version__):
                    async with s.get(self.raw_url("CHANGELOG.md")) as r:
                        if r.status == 200:
                            notes = self._notes(await r.text())
            was = self.state["available"]
            self.state.update(latest=latest, available=vtuple(latest) > vtuple(__version__),
                              checked=time.time(), error="", notes=notes)
            if self.state["available"] and not was:
                self.router.event("info", f"Update verfügbar: {__version__} → {latest}")
        except Exception as e:  # noqa: BLE001
            self.state.update(checked=time.time(), error=str(e)[:200])
            log.warning("Updateprüfung: %s", e)
        self.router.notify()
        return self.state

    @staticmethod
    def _notes(changelog: str) -> str:
        """Alle Abschnitte neuer als die laufende Version."""
        out, take = [], False
        for line in changelog.splitlines():
            m = re.match(r"^## \[([^\]]+)\]", line)
            if m:
                take = vtuple(m.group(1)) > vtuple(__version__)
            if take:
                out.append(line)
        return "\n".join(out)[:6000]

    def systemd_ready(self) -> bool:
        return os.path.exists("/etc/systemd/system/n8crosslink-update.path")

    async def request_update(self, user: str, system=None) -> dict:  # noqa: ANN001
        if system is not None and await system.sudo_ok():
            ok, out = await system.unit_action("n8crosslink-update.service", "start")
            if ok:
                self.state["running"] = True
                self.router.event("info", f"Update angestoßen von {user} (sudo) – der Dienst startet gleich neu")
                return {"ok": True, "message": "Update läuft – das Dashboard lädt nach dem Neustart neu."}
        if not self.systemd_ready():
            return {"ok": False, "message": "Update-Dienst nicht eingerichtet – bitte einmal „sudo /opt/n8crosslink/update.sh“ ausführen."}
        with open(self.request_file, "w") as f:
            f.write(f"{time.time()} {user}\n")
        self.state["running"] = True
        self.router.event("info", f"Update angestoßen von {user} – der Dienst startet gleich neu")
        return {"ok": True, "message": "Update läuft – das Dashboard lädt nach dem Neustart neu."}

    def log_tail(self, lines: int = 60) -> str:
        try:
            with open(self.log_file, errors="replace") as f:
                return "".join(f.readlines()[-lines:])
        except OSError:
            return ""
