"""Logos der verbundenen Systeme für die Netz-Karten: das Icon-Set des jeweiligen Servers.

Jedes N8-System (ADN-FRN-Server, HBlink4-FreeRadioID …) bringt ein vollständiges Icon-Set mit (apple-touch-icon, icon-192 …).
Der Crosslink holt sich davon das größte Bild vom Server, mit dem er gerade verbunden ist – so bekommt jede Karte das Logo
ihrer Plattform: FRN das Logo des FRN-Servers, DMR das des DMR-Servers, Zello das von zello.com.

Gesucht wird: <link rel="apple-touch-icon|icon"> der Startseite (größtes), dann /apple-touch-icon.png, /icons/icon-192.png,
/static/icons/icon-192.png, /favicon.ico. Nur echte Bilder (PNG, JPEG, WebP, GIF, ICO, SVG ohne Skript), höchstens 512 kB.
Zwischenspeicher: <daten>/neticons/<host>.img + .json, einmal am Tag erneuert; fehlt ein Bild, nach 1 Stunde neuer Versuch.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import ssl
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

log = logging.getLogger("neticons")
MAX = 512 * 1024
TIMEOUT = 8
REFRESH = 86400
RETRY = 3600
PATHS = ("/apple-touch-icon.png", "/icons/icon-192.png", "/static/icons/icon-192.png", "/icon-192.png", "/favicon.ico")
# Zello: Verbindung über zello.io / *.zellowork.com, das Logo hat zello.com
HOST_MAP = {"zello.io": "zello.com"}


def _ctype(b: bytes) -> str:
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if b[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    head = b[:400].lstrip().lower()
    if (head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head)) and b"<script" not in b.lower():
        return "image/svg+xml"
    return ""


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower()
        if "icon" not in rel or "mask-icon" in rel or not a.get("href"):
            return
        size = 0
        m = re.search(r"(\d+)x\d+", a.get("sizes", ""))
        if m:
            size = int(m.group(1))
        elif "apple-touch-icon" in rel:
            size = 180
        elif a.get("href", "").endswith(".svg"):
            size = 150
        self.icons.append((size, a["href"]))


def _get(url: str, limit: int = MAX) -> Tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "N8Crosslink (net icon)", "Accept": "image/*,text/html;q=0.8"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as r:
        return r.read(limit + 1), r.geturl()


def fetch(host: str) -> Optional[Tuple[bytes, str]]:
    """Größtes Icon des Servers holen: (Bild, Content-Type) oder None."""
    host = HOST_MAP.get(host, host)
    if not re.fullmatch(r"[A-Za-z0-9.\-]+", host or "") or re.fullmatch(r"[\d.]+", host) or host == "localhost":
        return None                              # keine IP-Adressen und nichts Lokales
    for scheme in ("https", "http"):
        base = f"{scheme}://{host}/"
        cands: list[str] = []
        try:
            html, final = _get(base, 400 * 1024)
            p = _Links()
            p.feed(html.decode("utf-8", "replace"))
            cands = [urljoin(final, h) for _, h in sorted(p.icons, key=lambda x: -x[0])]
        except Exception:  # noqa: BLE001
            pass
        cands += [urljoin(base, x) for x in PATHS]
        for u in dict.fromkeys(cands):
            if urlparse(u).scheme not in ("http", "https"):
                continue
            try:
                b, _ = _get(u)
            except Exception:  # noqa: BLE001
                continue
            ct = _ctype(b)
            if ct and len(b) <= MAX:
                return b, ct
    return None


class NetIcons:
    def __init__(self, data_dir: str):
        self.dir = Path(data_dir) / "neticons"

    def _paths(self, host: str) -> Tuple[Path, Path]:
        h = hashlib.sha1(host.lower().encode()).hexdigest()[:16]
        return self.dir / f"{h}.img", self.dir / f"{h}.json"

    def cached(self, host: str) -> Optional[Tuple[bytes, str, float]]:
        img, meta = self._paths(host)
        try:
            m = json.loads(meta.read_text())
            if m.get("ctype") and img.exists():
                return img.read_bytes(), m["ctype"], float(m.get("time") or 0)
        except (OSError, ValueError):
            pass
        return None

    def due(self, host: str) -> bool:
        _, meta = self._paths(host)
        try:
            m = json.loads(meta.read_text())
            return time.time() - float(m.get("time") or 0) > (REFRESH if m.get("ctype") else RETRY)
        except (OSError, ValueError):
            return True

    def refresh(self, host: str) -> bool:
        """Im Hintergrund (Thread) aufrufen."""
        if not host:
            return False
        self.dir.mkdir(parents=True, exist_ok=True)
        img, meta = self._paths(host)
        r = fetch(host)
        if r:
            img.write_bytes(r[0])
        meta.write_text(json.dumps({"host": host, "ctype": r[1] if r else "", "time": time.time()}))
        log.info("Netz-Logo %s: %s", host, r[1] if r else "keins gefunden")
        return bool(r)
