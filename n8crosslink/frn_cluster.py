"""FRN Master & Backup erkennen (ADN-FRN-Server ab 2.21) und prüfen, ob der Master wieder bereit ist.

Ein ADN-FRN-Server mit Rolle Master oder Backup sagt in seinem öffentlichen ``/api/info`` unter ``cluster``, welcher Server
Master und welcher Backup ist (Host und FRN-Port). Damit weiß der Crosslink:

* **Master ist immer Priorität 1** – egal, welcher der beiden in den Einstellungen als „Server“ steht.
* Fällt der Master aus, geht es zum Backup (wie bisher über den Backup-Server).
* Läuft er auf dem Backup, prüft er jede Minute, ob der Master wieder **wirklich** bereit ist: FRN-Port erreichbar, Java-FRN-Server
  läuft (``/api/live`` → ``server.running``) ohne Fehler beim SystemManager, keine Wartung. Erst nach mehreren erfolgreichen
  Prüfungen hintereinander wechselt er zurück – und nur zwischen zwei Durchgängen.

Ohne ADN-Dashboard (anderer FRN-Server) bleibt es beim eingetragenen Server und Backup-Server; die Rückkehr prüft dann nur den Port.
"""
from __future__ import annotations

import asyncio
import json
import socket
import ssl
import urllib.request
from typing import Any, Dict, Optional, Tuple

TIMEOUT = 6


def _get(url: str) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "N8Crosslink (FRN master/backup)"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as r:
            d = json.loads(r.read(256 * 1024))
            return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001 – kein Dashboard, kein JSON, kein Netz: einfach nicht erkannt
        return None


def dashboard(host: str, path: str) -> Optional[Dict[str, Any]]:
    """Antwort des Dashboards auf dem FRN-Host (erst https, dann http)."""
    host = (host or "").strip()
    if not host or any(c in host for c in "/?#@ "):
        return None
    for scheme in ("https", "http"):
        d = _get(f"{scheme}://{host}{path}")
        if d is not None:
            return d
    return None


def _hp(x: Any) -> Optional[Tuple[str, int]]:
    if isinstance(x, dict) and x.get("host"):
        try:
            return str(x["host"]), int(x.get("port") or 10024)
        except (TypeError, ValueError):
            return None
    return None


def detect(*hosts: str) -> Optional[Dict[str, Any]]:
    """Fragt die Dashboards der genannten FRN-Hosts nach Master/Backup. Ergebnis: {master: (host, port), backup: (host, port),
    via: host, maintenance} oder None."""
    for h in hosts:
        if not h:
            continue
        d = dashboard(h, "/api/info")
        c = (d or {}).get("cluster") or {}
        if c.get("role") in ("master", "backup"):
            m, b = _hp(c.get("master")), _hp(c.get("backup"))
            if m or b:
                return {"master": m, "backup": b, "via": h, "role_of_via": c["role"], "maintenance": bool(c.get("maintenance"))}
    return None


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True
    except OSError:
        return False


def master_ready(host: str, port: int, adn: bool) -> Tuple[bool, str]:
    """Ist der Master bereit für die Rückkehr? (ok, Grund)"""
    if not _port_open(host, port):
        return False, f"FRN-Port {host}:{port} nicht erreichbar"
    if not adn:
        return True, "FRN-Port erreichbar"
    info = dashboard(host, "/api/info") or {}
    if (info.get("cluster") or {}).get("maintenance"):
        return False, "Master ist in Wartung (Stationen auf dem Backup)"
    live = dashboard(host, "/api/live")
    srv = (live or {}).get("server") or {}
    if live is None:
        return True, "FRN-Port erreichbar (Dashboard nicht abrufbar)"
    if not srv.get("running"):
        return False, "Java-FRN-Server auf dem Master läuft noch nicht"
    if srv.get("error"):
        return False, f"Master meldet: {str(srv['error'])[:120]}"
    return True, "Master läuft"


async def adetect(*hosts: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(detect, *hosts)


async def amaster_ready(host: str, port: int, adn: bool) -> Tuple[bool, str]:
    return await asyncio.to_thread(master_ready, host, port, adn)
