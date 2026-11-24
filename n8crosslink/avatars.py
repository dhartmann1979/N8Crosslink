"""Avatare – zwischengespeichert in SQLite, täglich aktualisiert (oder per Knopf im Adminportal).

Quellen
  * DMR:   FreeRadioID-Profilbild https://freeradioid.net/api/idimg-<ID>.png (nur bei FreeRadioID
           registrierte IDs haben eines; sonst liefert FreeRadioID einen grauen Platzhalter, der erkannt wird)
  * FRN:   Rufzeichen -> DMR-ID aus der ID-Liste -> FreeRadioID-Bild
  * Zello: 1. im Adminportal hochgeladenes Bild, 2. optionale URL-Vorlage mit {username},
           3. Zello-Benutzername als Rufzeichen -> FreeRadioID-Bild
           (Die Zello Channel API liefert selbst keine Profilbilder.)

Schlüssel in der Tabelle: "dmr:<id>", "zello:<benutzer>", "upload:zello:<benutzer>".
Bilder werden auf 192 px WebP verkleinert (Pillow), sonst unverändert gespeichert.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import time

log = logging.getLogger("avatars")
SIZE = 192
DAY = 86400
CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,4}[A-Z]$")


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def shrink(data: bytes) -> tuple[str | None, bytes]:
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
        w, h = im.size
        side = min(w, h)
        im = im.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
        im.thumbnail((SIZE, SIZE), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "WEBP", quality=82, method=4)
        return "image/webp", out.getvalue()
    except Exception:  # noqa: BLE001
        return sniff(data), data


def callsign_of(text: str) -> str:
    """Erstes Wort, das wie ein Rufzeichen aussieht (z. B. aus 'dl1abc_hans' oder 'DL1ABC Hans')."""
    for tok in re.split(r"[\s_\-./,]+", (text or "").upper()):
        if CALLSIGN_RE.match(tok):
            return tok
    return ""


class AvatarStore:
    def __init__(self, router) -> None:  # noqa: ANN001
        self.router = router
        self.db = router.db
        self.placeholder_md5: str | None = None
        self.lock = asyncio.Lock()
        self.inflight: set[str] = set()

    @property
    def cfg(self) -> dict:
        return self.router.cfg["ids"]

    async def _fetch(self, url: str) -> bytes | None:
        import aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20),
                                             headers={"User-Agent": "N8-Crosslink avatars"}) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        return None
                    return await r.content.read(4 * 1024 * 1024)
        except Exception as e:  # noqa: BLE001
            log.debug("Avatar %s: %s", url, e)
            return None

    async def _placeholder(self) -> str:
        if self.placeholder_md5 is None:
            tpl = self.cfg.get("avatar_url", "")
            ph = await self._fetch(tpl.replace("{id}", "0")) if tpl else None
            self.placeholder_md5 = hashlib.md5(ph).hexdigest() if ph else ""
        return self.placeholder_md5

    # ------------------------------------------------------------ Auflösung
    def resolve(self, source: str, key: str) -> list[tuple[str, str]]:
        """Liste möglicher (cache_key, url) in Prioritätsreihenfolge."""
        tpl = self.cfg.get("avatar_url", "")
        out: list[tuple[str, str]] = []
        if not self.cfg.get("avatars", True):
            return out
        if source == "dmr":
            try:
                rid = int(key)
            except ValueError:
                return out
            if tpl:
                out.append((f"dmr:{rid}", tpl.replace("{id}", str(rid))))
            return out
        if source == "zello":
            user = key.strip()
            out.append((f"upload:zello:{user.lower()}", ""))
            ztpl = self.cfg.get("zello_avatar_url", "")
            if ztpl:
                out.append((f"zello:{user.lower()}", ztpl.replace("{username}", user)))
        cs = callsign_of(key) if self.cfg.get("match_callsign", True) else ""
        if cs:
            u = self.db.userdb_by_callsign(cs)
            if u and tpl:
                out.append((f"dmr:{u['id']}", tpl.replace("{id}", str(u["id"]))))
        return out

    async def get(self, source: str, key: str) -> tuple[str, bytes] | None:
        for ck, url in self.resolve(source, key):
            row = self.db.avatar_get(ck)
            if row is not None:
                if row["has"]:
                    return row["mime"], row["data"]
                continue
            if not url:
                continue
            if ck.startswith("dmr:") and self.cfg.get("only_registered", True):
                if not self.db.frid_is_registered(int(ck[4:])):
                    continue
            if await self.fetch(ck, url):
                row = self.db.avatar_get(ck)
                return row["mime"], row["data"]
        return None

    async def fetch(self, ck: str, url: str) -> bool:
        if ck in self.inflight:
            return False
        self.inflight.add(ck)
        try:
            data = await self._fetch(url)
            ph = await self._placeholder() if ck.startswith("dmr:") else ""
            if not data or not sniff(data) or (ph and hashlib.md5(data).hexdigest() == ph):
                self.db.avatar_put(ck, False, None, None, url)
                return False
            mime, small = await asyncio.to_thread(shrink, data)
            self.db.avatar_put(ck, True, mime, small, url)
            return True
        finally:
            self.inflight.discard(ck)

    def upload(self, source: str, key: str, data: bytes) -> bool:
        if not sniff(data):
            return False
        mime, small = shrink(data)
        self.db.avatar_put(f"upload:{source}:{key.strip().lower()}", True, mime, small, "upload")
        return True

    # ------------------------------------------------------------ Tages-Refresh
    async def loop(self) -> None:
        await asyncio.sleep(60)
        while True:
            last = float(self.db.meta_get("avatars_refreshed") or 0)
            if time.time() - last > DAY - 300:
                await self.refresh_all()
            await asyncio.sleep(3600)

    async def refresh_all(self) -> dict:
        """Alle zwischengespeicherten Avatare neu laden (Uploads bleiben unverändert)."""
        if self.lock.locked():
            return {"busy": True}
        async with self.lock:
            self.placeholder_md5 = None
            rows = self.db.avatar_list()
            sem = asyncio.Semaphore(4)
            found = 0

            async def one(r) -> None:  # noqa: ANN001
                nonlocal found
                async with sem:
                    if await self.fetch(r["key"], r["url"]):
                        found += 1
            await asyncio.gather(*(one(r) for r in rows if r["url"] and r["url"] != "upload"))
            self.db.meta_set("avatars_refreshed", str(time.time()))
            n = len([r for r in rows if r["url"] != "upload"])
            self.router.event("info", f"Avatare aktualisiert: {found} Bilder bei {n} geprüften Stationen")
            return {"checked": n, "with_avatar": found}
