"""Systemsteuerung aus dem Webinterface über eng begrenztes sudo.

Der Installer legt /etc/sudoers.d/n8crosslink an. Darin stehen NUR einzelne, vollständige Befehle
(z. B. „systemctl restart n8crosslink.service“) – keine Platzhalter, keine Shell. Die erlaubten
Dienste schreibt er zusätzlich nach data/system.json, damit das Webinterface weiß, was es anbieten darf.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil

ACTIONS = ("start", "stop", "restart", "enable", "disable")


class System:
    def __init__(self, data_dir: str) -> None:
        self.file = os.path.join(data_dir, "system.json")

    def config(self) -> dict:
        try:
            with open(self.file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"systemctl": shutil.which("systemctl") or "/usr/bin/systemctl", "units": [], "sudo": False}

    async def _run(self, *cmd: str, timeout: float = 60) -> tuple[int, str]:
        try:
            p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.STDOUT)
            out, _ = await asyncio.wait_for(p.communicate(), timeout)
            return p.returncode or 0, out.decode(errors="replace").strip()
        except asyncio.TimeoutError:
            return 124, "Zeitüberschreitung"
        except OSError as e:
            return 127, str(e)

    async def sudo(self, *cmd: str, timeout: float = 120) -> tuple[int, str]:
        return await self._run("sudo", "-n", *cmd, timeout=timeout)

    async def sudo_ok(self) -> bool:
        c = self.config()
        if not c.get("sudo") or not shutil.which("sudo"):
            return False
        rc, _ = await self.sudo("-l", c["systemctl"], "--no-block", "restart", "n8crosslink.service", timeout=10)
        return rc == 0

    async def status(self) -> dict:
        c = self.config()
        units = []
        for u in c.get("units", []):
            name = u["unit"]
            _, active = await self._run(c["systemctl"], "is-active", name, timeout=5)
            _, enabled = await self._run(c["systemctl"], "is-enabled", name, timeout=5)
            known_a = {"active", "inactive", "failed", "activating", "deactivating", "reloading"}
            known_e = {"enabled", "disabled", "static", "masked", "not-found", "indirect", "generated"}
            a = active.splitlines()[0] if active else ""
            e = enabled.splitlines()[0] if enabled else ""
            units.append({**u, "active": a if a in known_a else "unbekannt",
                          "enabled": e if e in known_e else "unbekannt"})
        return {"sudo": await self.sudo_ok(), "units": units, "reboot": c.get("reboot", False),
                "fix_perms": c.get("fix_perms", False), "check_perms": c.get("check_perms", False)}

    def allowed(self, unit: str, action: str) -> bool:
        for u in self.config().get("units", []):
            if u["unit"] == unit:
                return action in u.get("actions", [])
        return False

    async def unit_action(self, unit: str, action: str) -> tuple[bool, str]:
        if action not in ACTIONS or not self.allowed(unit, action):
            return False, "Aktion nicht erlaubt"
        c = self.config()
        args = [c["systemctl"], action, unit]
        if action in ("start", "restart"):
            args.insert(1, "--no-block")
        rc, out = await self.sudo(*args)
        return rc == 0, out or ("ok" if rc == 0 else f"Fehler {rc}")

    async def reboot(self) -> tuple[bool, str]:
        c = self.config()
        if not c.get("reboot"):
            return False, "Neustart des Systems ist nicht freigegeben"
        rc, out = await self.sudo(c["systemctl"], "reboot")
        return rc == 0, out or "Neustart wird ausgeführt"

    async def build_vocoder(self) -> tuple[bool, str]:
        if not self.config().get("build_vocoder"):
            return False, ("Bauen des N8schicht-Vocoders über das Webinterface ist nicht freigegeben – "
                           "einmal sudo /opt/n8crosslink/update.sh ausführen")
        rc, out = await self.sudo("/opt/n8crosslink/install.sh", "--build-vocoder", timeout=1200)
        return rc == 0, out[-3000:]

    async def check_perms(self) -> dict:
        """Berechtigungen und sudo prüfen (ändert nichts) – Liste aus install.sh --check-perms --json."""
        if not self.config().get("check_perms"):
            return {"ok": False, "missing": True, "checks": [],
                    "message": "Prüfung im Webinterface noch nicht freigegeben – einmal sudo /opt/n8crosslink/install.sh --fix-perms ausführen"}
        rc, out = await self.sudo("/opt/n8crosslink/install.sh", "--check-perms", "--json", timeout=120)
        for line in reversed(out.strip().splitlines()):
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except ValueError:
                    break
        return {"ok": False, "checks": [], "message": ("sudo verweigert – auf der Konsole: sudo /opt/n8crosslink/install.sh --fix-perms"
                                                     if "password" in out or "sudo" in out else out[-300:] or f"Fehler {rc}")}

    async def fix_perms(self) -> tuple[bool, str]:
        if not self.config().get("fix_perms"):
            return False, "Berechtigungsprüfung nicht freigegeben"
        rc, out = await self.sudo("/opt/n8crosslink/install.sh", "--fix-perms", timeout=180)
        return rc == 0, out[-3000:]

    # ---- Domains & HTTPS (Let's Encrypt) über /opt/n8crosslink/n8x-certs.sh -------------------------------
    CERTS = os.environ.get("N8X_CERTS_HELPER", "/opt/n8crosslink/n8x-certs.sh")   # anderer Pfad nur zum Testen
    DOMAIN_RE = r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"

    async def certs(self, *args: str, timeout: float = 300) -> dict:
        """Ruft den root-Helfer für Domains und Zertifikate auf; Antwort ist eine Zeile JSON."""
        if not self.config().get("certs"):
            return {"ok": False, "missing": True,
                    "message": "Domains & HTTPS sind noch nicht freigegeben – einmal sudo /opt/n8crosslink/update.sh ausführen"}
        rc, out = await self.sudo(self.CERTS, *args, timeout=timeout)
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    break
        return {"ok": False, "message": (out[-400:] or f"Fehler {rc}")}
