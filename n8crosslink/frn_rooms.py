"""Räume (Nets) eines FRN-Servers auslesen – für das Raum-Auswahlmenü im Admin.

Drei Quellen, in dieser Reihenfolge:

1. **live** – der Crosslink ist mit genau diesem Server verbunden: die Raumliste, die der Server nach dem Login schickt
   (Listentyp 5), steht schon bereit.
2. **dashboard** – der Server hat ein ADN-FRN-Server-Dashboard (``/api/live`` → ``rooms``): Räume mit Stationszahl,
   ohne FRN-Anmeldung. Versteckte Räume zeigt das öffentliche Dashboard nicht.
3. **login** – kurze FRN-Anmeldung mit dem eingetragenen Konto, Raumliste lesen, sofort wieder abmelden. Nur wenn der
   Crosslink gerade *nicht* mit demselben Konto online ist (der System Manager erlaubt jedes Konto nur einmal).
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from . import frn_cluster

DT_IDLE, DT_DO_TX, DT_VOICE, DT_CLIENT_LIST, DT_NETS = 0, 1, 2, 3, 5
GSM_BYTES = 325
TIMEOUT = 10.0


def _clean(names: list[str]) -> list[str]:
    out = []
    for n in names:
        n = re.sub(r"<[^>]+>", "", str(n or "")).strip()
        if n and n not in out:
            out.append(n)
    return out


def from_dashboard_data(d: dict | None) -> list[dict]:
    rooms = (d or {}).get("rooms")
    if not isinstance(rooms, list):
        return []
    out = []
    for r in rooms:
        if isinstance(r, dict) and r.get("name") and not r.get("hidden"):
            out.append({"name": str(r["name"]), "clients": len(r.get("clients") or [])})
    return out


async def _probe(host: str, port: int, s: dict) -> list[str]:
    """Kurz am FRN-Server anmelden und die Raumliste lesen."""
    on = f"{s.get('callsign', '')}, {s.get('op_name', '')}"
    login = ("CT:" + f"<VX>{s.get('version') or '2014003'}</VX>" + f"<EA>{s.get('email', '')}</EA>"
             + f"<PW>{s.get('password', '')}</PW>" + f"<ON>{on}</ON>" + f"<CL>{s.get('client_type', 0)}</CL>"
             + f"<BC>{s.get('band', '')}</BC>" + f"<DS>{s.get('description', '')}</DS>" + f"<NN>{s.get('country', '')}</NN>"
             + f"<CT>{s.get('city', '')}</CT>" + f"<NT>{s.get('net') or 'Test'}</NT>")
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), TIMEOUT)

    def cmd(t: str) -> None:
        writer.write(t.encode("latin-1", errors="replace") + b"\r\n")

    async def read_list() -> list[str]:
        first = (await asyncio.wait_for(reader.readline(), TIMEOUT)).decode("latin-1").strip()
        try:
            n = int(first)
        except ValueError:
            return []
        return [(await asyncio.wait_for(reader.readline(), TIMEOUT)).decode("latin-1", "replace").rstrip("\r\n")
                for _ in range(min(n, 200))]

    try:
        cmd(login)
        await writer.drain()
        await asyncio.wait_for(reader.readline(), TIMEOUT)                     # Server-Version
        resp = (await asyncio.wait_for(reader.readline(), TIMEOUT)).decode("latin-1", "replace")
        al = (re.search(r"<AL>(.*?)</AL>", resp) or [None, ""])[1]
        if al in ("", "WRONG", "BLOCK"):
            raise PermissionError(f"Anmeldung abgelehnt ({al or 'keine Antwort'}) – E-Mail/Passwort prüfen")
        cmd("RX0")
        cmd("P")
        loop = asyncio.get_running_loop()
        end = loop.time() + TIMEOUT
        while loop.time() < end:
            b = await asyncio.wait_for(reader.readexactly(1), max(0.5, end - loop.time()))
            dt = b[0]
            if dt == DT_IDLE:
                cmd("P")
            elif dt == DT_DO_TX:
                await reader.readexactly(2)
            elif dt == DT_VOICE:
                await reader.readexactly(2 + GSM_BYTES)
                cmd("P")
            elif dt == DT_CLIENT_LIST:
                await reader.readexactly(2)
                await read_list()
                cmd("P")
            elif dt == DT_NETS:
                return await read_list()
            elif 4 <= dt <= 10:
                await read_list()
                cmd("P")
            else:
                break
        return []
    finally:
        try:
            writer.close()
        except Exception:  # noqa: BLE001
            pass


async def rooms(host: str, port: int, section: dict, frn_port: Any = None) -> dict:
    """Raumliste für ``host:port``. Rückgabe ``{rooms: [{name, clients?}], source, note}``."""
    host = (host or "").strip()
    if not host:
        return {"rooms": [], "source": "", "note": "Erst einen Server eintragen"}
    online_same = bool(frn_port and getattr(frn_port, "online", False) and getattr(frn_port, "target", None)
                       and str(frn_port.target[0]).lower() == host.lower())
    live = _clean(getattr(frn_port, "nets", []) or []) if online_same else []
    if live:
        return {"rooms": [{"name": n} for n in live], "source": "live",
                "note": f"vom FRN-Server {host} (aktuelle Verbindung)"}
    dash = from_dashboard_data(await asyncio.to_thread(frn_cluster.dashboard, host, "/api/live"))
    if dash:
        return {"rooms": dash, "source": "dashboard", "note": f"vom Dashboard {host} (ohne versteckte Räume)"}
    if frn_port and getattr(frn_port, "online", False) and section.get("email"):
        return {"rooms": [], "source": "", "note": "Der Crosslink ist gerade mit diesem FRN-Konto online – eine zweite Anmeldung "
                                                   "würde abgelehnt. Raumliste kommt nach dem Verbinden mit diesem Server."}
    if not section.get("email") or not section.get("password"):
        return {"rooms": [], "source": "", "note": "Für das Auslesen per FRN-Anmeldung E-Mail und Passwort eintragen und speichern"}
    try:
        names = _clean(await _probe(host, int(port or 10024), section))
    except PermissionError as e:
        return {"rooms": [], "source": "", "note": str(e)}
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
        return {"rooms": [], "source": "", "note": f"{host}:{port} nicht erreichbar ({e.__class__.__name__})"}
    if not names:
        return {"rooms": [], "source": "", "note": "Der Server hat keine Raumliste geschickt"}
    return {"rooms": [{"name": n} for n in names], "source": "login", "note": f"vom FRN-Server {host} (kurze Anmeldung)"}
