"""ID-Listen: FreeRadioID.net (alle API-Listen) und Talkgroup-Namen aus dem n8schicht-Repository.

FreeRadioID-API (https://freeradioid.net/api-index.html):
  * subscriber_ids.csv / .json        – alle DMR-IDs inkl. RadioID.net  -> Tabelle dmr_users
  * local_subscriber_ids.json / .csv  – nur bei FreeRadioID registriert -> Tabelle frid_registered (FRID-Kennzeichen, Avatare)
  * dmr/user/?id=<ID>                 – Einzelabfrage für unbekannte IDs (live, Ergebnis wird gespeichert)
  * dmrids.dat                        – gleicher Inhalt wie subscriber_ids, wird nicht zusätzlich gebraucht
Talkgroups: talkgroup_ids.json aus github.com/dhartmann1979/n8schicht -> Tabelle talkgroups

Aktualisierung einmal am Tag (und beim Start, wenn leer) sowie per Knopf im Adminportal.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time

log = logging.getLogger("idlists")
UA = {"User-Agent": "N8-Crosslink (+https://github.com/dhartmann1979/N8Crosslink)"}
DAY = 86400


async def _get(url: str, timeout: int = 180) -> bytes:
    import aiohttp
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=UA) as s:
        async with s.get(url) as r:
            r.raise_for_status()
            return await r.read()


def parse_subscriber_csv(text: str) -> list[tuple]:
    """FreeRadioID/RadioID-CSV, mit oder ohne Kopfzeile."""
    # FreeRadioID liefert teils "\n\r" als Zeilenende – alle Varianten vereinheitlichen
    text = text.replace("\r\n", "\n").replace("\n\r", "\n").replace("\r", "\n")
    rows = [r for r in csv.reader(io.StringIO(text, newline="")) if r and any(c.strip() for c in r)]
    if not rows:
        return []
    head = [c.strip().lower() for c in rows[0]]
    has_header = not head[0].isdigit()
    if has_header:
        def idx(*names: str, default=None):  # noqa: ANN202
            for n in names:
                if n in head:
                    return head.index(n)
            for n in names:
                for i, c in enumerate(head):
                    if n in c:
                        return i
            return default
        i_id, i_cs = idx("radio_id", "id", default=0), idx("callsign", default=1)
        i_fn, i_city = idx("first_name", "fname", "name", default=2), idx("city", default=3)
        i_cty = idx("country", default=len(head) - 1)
        data = rows[1:]
    else:
        # FreeRadioID: id,callsign,vorname,ort,bundesland,land (Land = letzte Spalte)
        i_id, i_cs, i_fn, i_city, i_cty = 0, 1, 2, 3, -1
        data = rows
    out = []
    for r in data:
        try:
            rid = int(r[i_id])
        except (ValueError, IndexError):
            continue
        g = lambda i: (r[i].strip() if i is not None and -len(r) <= i < len(r) else "")  # noqa: E731
        out.append((rid, g(i_cs).upper(), g(i_fn), g(i_city), g(i_cty) if len(r) > 4 else ""))
    return out


def parse_subscriber_json(raw: bytes) -> list[tuple]:
    d = json.loads(raw)
    res = d.get("results", d) if isinstance(d, dict) else d
    out = []
    for u in res:
        try:
            out.append((int(u["id"]), str(u.get("callsign", "")).upper(), u.get("fname") or u.get("name") or "",
                        u.get("city") or "", u.get("country") or ""))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def parse_talkgroups(raw: bytes) -> list[tuple]:
    d = json.loads(raw)
    res = d.get("results", d) if isinstance(d, dict) else d
    out = []
    if isinstance(res, dict):            # {"262": "Deutschland"}
        for k, v in res.items():
            try:
                out.append((int(k), str(v)))
            except ValueError:
                pass
        return out
    for t in res:
        try:
            tg = int(t.get("TG-id") or t.get("tg") or t.get("id"))
        except (TypeError, ValueError):
            continue
        name = str(t.get("callsign") or t.get("name") or "").strip()
        if name and name.upper() != "N/A":
            out.append((tg, name))
    return out


class IdLists:
    def __init__(self, router) -> None:  # noqa: ANN001
        self.router = router
        self.db = router.db
        self.lock = asyncio.Lock()
        self.status: dict = {}
        self._lookup_pending: set[int] = set()

    @property
    def cfg(self) -> dict:
        return self.router.cfg["ids"]

    # ------------------------------------------------------------ Planung
    async def loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                info = self.db.idlists_info()
                if info["users"] == 0 or time.time() - (info["users_updated"] or 0) > DAY - 300:
                    await self.update_all()
            except Exception as e:  # noqa: BLE001
                log.exception("ID-Listen: %s", e)
            await asyncio.sleep(3600)

    async def update_all(self) -> dict:
        if self.lock.locked():
            return {"busy": True}
        async with self.lock:
            res = {"users": await self._users(), "registered": await self._registered(),
                   "talkgroups": await self._talkgroups()}
            self.router.event("info", "ID-Listen aktualisiert: {:,} DMR-IDs, {:,} bei FreeRadioID registriert, {:,} Talkgroups"
                              .format(res["users"], res["registered"], res["talkgroups"]).replace(",", "."))
            self.router.notify()
            return res

    # ------------------------------------------------------------ Listen
    async def _users(self) -> int:
        c = self.cfg
        for url, kind in ((c.get("subscriber_csv_url"), "csv"), (c.get("subscriber_json_url"), "json"),
                          (c.get("radioid_fallback_url"), "csv")):
            if not url:
                continue
            try:
                raw = await _get(url)
                rows = await asyncio.to_thread(
                    parse_subscriber_csv if kind == "csv" else parse_subscriber_json,
                    raw.decode("utf-8", errors="replace") if kind == "csv" else raw)
                if len(rows) > 1000:
                    await asyncio.to_thread(self.db.userdb_replace, rows)
                    self.db.meta_set("users_source", url)
                    return len(rows)
                log.warning("ID-Liste %s: nur %s Einträge – verworfen", url, len(rows))
            except Exception as e:  # noqa: BLE001
                self.router.event("warn", f"DMR-ID-Liste von {url} nicht ladbar: {e}")
        return self.db.idlists_info()["users"]

    async def _registered(self) -> int:
        c = self.cfg
        for url, kind in ((c.get("local_json_url"), "json"), (c.get("local_csv_url"), "csv")):
            if not url:
                continue
            try:
                raw = await _get(url, 60)
                rows = parse_subscriber_json(raw) if kind == "json" else parse_subscriber_csv(raw.decode(errors="replace"))
                await asyncio.to_thread(self.db.frid_replace, rows)
                return len(rows)
            except Exception as e:  # noqa: BLE001
                self.router.event("warn", f"FreeRadioID-Registrierungen von {url} nicht ladbar: {e}")
        return self.db.idlists_info()["registered"]

    async def _talkgroups(self) -> int:
        url = self.cfg.get("talkgroups_url")
        if not url:
            return 0
        try:
            rows = parse_talkgroups(await _get(url, 60))
            if rows:
                await asyncio.to_thread(self.db.talkgroups_replace, rows)
            return len(rows)
        except Exception as e:  # noqa: BLE001
            self.router.event("warn", f"Talkgroup-Liste nicht ladbar: {e}")
            return self.db.idlists_info()["talkgroups"]

    # ------------------------------------------------------------ Einzelabfrage
    def lookup_later(self, dmr_id: int) -> None:
        """Unbekannte ID live bei FreeRadioID nachschlagen (einmal, im Hintergrund)."""
        tpl = self.cfg.get("user_api_url")
        if not tpl or dmr_id in self._lookup_pending or dmr_id <= 0:
            return
        self._lookup_pending.add(dmr_id)

        async def run() -> None:
            try:
                d = json.loads(await _get(tpl.replace("{id}", str(dmr_id)), 15))
                for u in d.get("results", []):
                    row = (int(u["id"]), str(u.get("callsign", "")).upper(), u.get("fname") or "",
                           u.get("city") or "", u.get("country") or "")
                    self.db.userdb_upsert(row)
                    name = f"{row[1]} {row[2]}".strip()
                    dmr = self.router.ports.get("dmr")
                    if dmr is not None:
                        dmr.on_lookup_result(dmr_id, name, row[1], row[3])
                    if d.get("reg"):
                        self.db.frid_add(dmr_id)
            except Exception as e:  # noqa: BLE001
                log.debug("Einzelabfrage %s: %s", dmr_id, e)
        asyncio.create_task(run())
