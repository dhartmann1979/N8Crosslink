"""Öffentliche Ansicht ohne Anmeldung: keine IP-Adressen und keine Ports.

Wer nicht angemeldet ist, sieht Live-Daten, Last Heard und Ereignisse – aber Serveradressen, IPs und Ports werden
entfernt bzw. maskiert. Hostnamen (z. B. dmr.die-n8schicht.de) bleiben lesbar, nur der Port fällt weg; IPv4/IPv6
werden durch MASK ersetzt. Angemeldete Admins sehen alles.
"""
from __future__ import annotations

import re
from typing import Any

MASK = "•••"
# Felder mit Adressen/Geräten, die öffentlich ganz wegfallen
DROP_KEYS = {"server", "host", "address", "ip", "peer", "peer_ip", "remote", "ambeserver_host", "ambeserver_port",
             "usb_device", "device", "web_host", "web_port", "port", "local_port", "backup_server", "backup_port", "cluster"}

_URL = re.compile(r"\b(?:wss?|https?|udp|tcp)://[^\s,;)\]\"'<>]+", re.I)
_IP4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\w.])")
_IP6 = re.compile(r"(?<![\w:.])\[?(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}\]?(?::\d{1,5})?(?![\w:])")
_HOSTPORT = re.compile(r"(?<![\w.-])((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}|localhost):\d{1,5}\b")
_PORTKV = re.compile(r"\b([\w.]*port[\w]*)(\s*[=:]\s*)\d{1,5}\b", re.I)
_PORTWORD = re.compile(r"\b(Ports?|port|UDP|TCP)(\s*)(\d{1,5}(?:\s*(?:/|,|und|and|→)\s*\d{1,5})*)\b")


def _ip6(m: re.Match) -> str:
    s = m.group(0)
    core = s.strip("[]").split("]")[0]
    # Uhrzeiten (10:28:25) und Ähnliches haben höchstens zwei Doppelpunkte und kein „::“
    if "::" not in core and core.count(":") < 3:
        return s
    return MASK


def _url(m: re.Match) -> str:
    """Adressen wie ws://127.0.0.1:8799/ws maskieren; normale Links (https://github.com/…) bleiben."""
    u = m.group(0)
    scheme, rest = u.split("://", 1)
    netloc = rest.split("/", 1)[0]
    if _IP4.fullmatch(netloc) or "[" in netloc or ":" in netloc or netloc.lower().startswith("localhost"):
        return scheme + "://" + MASK
    return u


def text(s: str) -> str:
    """IPs und Ports aus einem Text entfernen (Hostnamen bleiben, ohne Port)."""
    if not s or not isinstance(s, str):
        return s
    s = _URL.sub(_url, s)
    s = _IP4.sub(MASK, s)
    s = _IP6.sub(_ip6, s)
    s = _HOSTPORT.sub(lambda m: m.group(1), s)
    s = _PORTKV.sub(lambda m: m.group(1) + m.group(2) + MASK, s)
    s = _PORTWORD.sub(lambda m: m.group(1) + m.group(2) + MASK, s)
    return s


def scrub(obj: Any) -> Any:
    """Kopie von obj ohne Adressfelder, alle Texte ohne IPs/Ports."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in DROP_KEYS}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return text(obj)
    return obj
