"""Öffentliches FRN-Fehlerprotokoll von freeradionetwork.de – zur Fehleranalyse.

Der FRN System Manager schreibt dort jede abgelehnte Anmeldung von Clients und Servern (falsches FRN-Passwort,
Mehrfachverbindung, Port nicht erreichbar …) – also genau die Gründe, die der eigene Server bei der Ablehnung nicht
nennt. Seite: Hilfe → Fehlerprotokoll auf freeradionetwork.de bzw. direkt PAGE. Die Seite lädt die letzten Einträge
als JSON {"log": "Zeile\\nZeile…"} von URL.

Zeilenformat:
    2026-11-25 09:43:39 ERROR - Client [N8XLINK, Crosslink], DE/DE, Request CC - wrong FRN password - Hint: …
    2026-11-25 09:43:44 ERROR - Server [frn.example.de:10024], DE, Request SC - multiple connections at the same time …
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.request

PAGE = "http://log.freeradionetwork.de:60080/error_log.php"
URL = PAGE + "?action=getLog"
LINE_RE = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (?P<level>\w+) - (?P<kind>Server|Client) \[(?P<who>[^\]]*)\], "
                     r"(?P<country>[^,]*), Request (?P<request>\w+) - (?P<message>.*)$")
# bekannte Meldungen -> Erklärung und was zu tun ist
HINTS = [
    (r"wrong FRN password", "Falsches FRN-Passwort – beim System Manager ein Passwort anfordern („📧 Passwort anfordern“) und genau das "
                            "zugeteilte Passwort mit derselben E-Mail und demselben Rufzeichen/Namen eintragen."),
    (r"multiple connections", "Mehrfachverbindung: Mit denselben Zugangsdaten ist schon eine Verbindung aktiv – läuft eine zweite Instanz "
                              "(alte Bridge/SvxLink, zweiter Server, Backup mit gleichen Daten)? Nur eine Verbindung je Zugang."),
    (r"not listening on specified port", "Der Server ist auf dem angegebenen Port von außen nicht erreichbar – Firewall und "
                                         "Portweiterleitung (TCP) im Router prüfen."),
    (r"blocked|banned|locked", "Zugang gesperrt – beim Betreiber des FRN-Netzes nachfragen."),
    (r"unknown|not registered|no account|not found", "Zugang beim System Manager unbekannt – Passwort anfordern bzw. Schreibweise von "
                                                     "E-Mail, Rufzeichen und Name prüfen."),
    (r"version", "Protokollversion wird abgelehnt – Feld „Protokollversion“ prüfen (Standard 2014003)."),
    (r"e-?mail", "E-Mail-Adresse wird abgelehnt – genau die beim FRN-Passwort verwendete Adresse eintragen."),
]
_cache: dict = {"t": 0.0, "entries": [], "error": ""}
CACHE_S = 60


def hint_for(message: str) -> str:
    for rx, text in HINTS:
        if re.search(rx, message, re.I):
            return text
    return ""


def parse(text: str) -> list[dict]:
    """Rohtext oder JSON-Antwort -> Einträge (neueste zuletzt)."""
    try:
        text = json.loads(text).get("log", "")
    except (ValueError, AttributeError):
        pass
    out = []
    for line in str(text).splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        e = m.groupdict()
        parts = [p.strip() for p in e["who"].split(",", 1)]
        e["id"] = parts[0]                                   # Client: Rufzeichen, Server: host:port
        e["name"] = parts[1] if len(parts) > 1 else ""
        e["message"], _, hint_en = e["message"].partition(" - Hint: ")
        e["message"] = e["message"].strip()
        e["hint_en"] = hint_en.strip(" !")
        e["hint"] = hint_for(e["message"])
        try:
            e["time"] = time.mktime(time.strptime(e["ts"], "%Y-%m-%d %H:%M:%S"))   # Zeit des Protokolls (MEZ, wie der Server)
        except ValueError:
            e["time"] = 0
        out.append(e)
    return out


def _get(timeout: float) -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "N8Crosslink (Fehleranalyse)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 – feste URL
        return r.read(1_000_000).decode("utf-8", "replace")


async def fetch(timeout: float = 8, force: bool = False) -> tuple[list[dict], str]:
    """Einträge (gecacht CACHE_S Sekunden) und ggf. Fehlertext, wenn das Protokoll nicht erreichbar ist."""
    if not force and time.time() - _cache["t"] < CACHE_S:
        return _cache["entries"], _cache["error"]
    try:
        entries, err = parse(await asyncio.to_thread(_get, timeout)), ""
    except Exception as e:  # noqa: BLE001 – Netzfehler sind ein Befund, kein Absturz
        entries, err = _cache["entries"], f"Fehlerprotokoll nicht erreichbar ({e.__class__.__name__}: {str(e)[:80]})"
    _cache.update(t=time.time(), entries=entries, error=err)
    return entries, err


def _host(s: str) -> str:
    return s.strip().lower().rstrip(".").split(":")[0]


def relevant(entries: list[dict], callsigns=(), hosts=()) -> list[dict]:
    """Einträge, die uns betreffen: eigene Client-Rufzeichen und die Server, mit denen wir verbunden sind."""
    cs = {c.strip().upper() for c in callsigns if c and c.strip()}
    hs = {_host(h) for h in hosts if h and h.strip()}
    out = []
    for e in entries:
        if e["kind"] == "Client" and e["id"].upper() in cs:
            out.append({**e, "match": "client"})
        elif e["kind"] == "Server" and _host(e["id"]) in hs:
            out.append({**e, "match": "server"})
    return out


def summarize(entries: list[dict]) -> list[dict]:
    """Gleiche Meldungen zusammenfassen: je (Art, Absender, Meldung) Anzahl, erster und letzter Zeitpunkt."""
    groups: dict = {}
    for e in entries:
        k = (e["kind"], e["id"], e["message"])
        g = groups.setdefault(k, {**e, "count": 0, "first": e["ts"]})
        g["count"] += 1
        g["ts"], g["time"] = e["ts"], e["time"]
    return sorted(groups.values(), key=lambda g: g["time"], reverse=True)
