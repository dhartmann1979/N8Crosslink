"""Öffentliches FRN-Fehlerprotokoll (log.freeradionetwork.de): Auswerten, Zuordnen, Melden."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from n8crosslink import frn_errorlog as el  # noqa: E402
from tests.test_web_security import login, make_client  # noqa: E402

NOW = time.strftime("%Y-%m-%d %H:%M:%S")
SAMPLE = json.dumps({"log": "\n".join([
    "2026-11-25 09:43:35 ERROR - Server [frn-backup.auf-der-nachtschicht.de:10024], DE, Request SC - wrong FRN password - Hint: Perform an FRN password request and use the assigned FRN password !",
    "2026-11-25 09:43:39 ERROR - Client [N8XLINK, Crosslink], DE/DE, Request CC - wrong FRN password - Hint: Perform an FRN password request and use the assigned FRN password !",
    "2026-11-25 09:43:44 ERROR - Server [frn.auf-der-nachtschicht.de:10024], DE, Request SC - multiple connections at the same time with the same connection data are not permitted",
    "2026-11-25 09:50:01 ERROR - Server [uhf3radionet.ddns.net:10024], GR, Request SC - not listening on specified port - Hint: Check the firewall settings and port forwarding settings, if applicable !",
    f"{NOW} ERROR - Client [N8XLINK, Crosslink], DE/DE, Request CC - wrong FRN password - Hint: Perform an FRN password request and use the assigned FRN password !",
    "kaputte Zeile ohne Format",
]) + "\n"})


def test_parse_and_hints():
    e = el.parse(SAMPLE)
    assert len(e) == 5
    c = e[1]
    assert c["kind"] == "Client" and c["id"] == "N8XLINK" and c["name"] == "Crosslink" and c["country"] == "DE/DE" and c["request"] == "CC"
    assert c["message"] == "wrong FRN password" and "password request" in c["hint_en"] and "Passwort anfordern" in c["hint"]
    assert e[2]["id"] == "frn.auf-der-nachtschicht.de:10024" and "Mehrfachverbindung" in e[2]["hint"]
    assert "Portweiterleitung" in e[3]["hint"]
    assert el.parse("Zeile\nohne Format") == [] and el.parse("") == []


def test_relevant_and_summary():
    e = el.parse(SAMPLE)
    mine = el.relevant(e, ["n8xlink"], ["frn.auf-der-nachtschicht.de", "frn-backup.auf-der-nachtschicht.de:10024", ""])
    assert {m["id"] for m in mine} == {"N8XLINK", "frn.auf-der-nachtschicht.de:10024", "frn-backup.auf-der-nachtschicht.de:10024"}
    assert not el.relevant(e, ["DL1ABC"], ["frn.example.org"])
    g = el.summarize([m for m in mine if m["kind"] == "Client"])
    assert len(g) == 1 and g[0]["count"] == 2 and g[0]["first"] == "2026-11-25 09:43:39" and g[0]["ts"] == NOW


def test_endpoint(monkeypatch):
    c, bridge = make_client()

    async def fake(timeout=8, force=False):
        el._cache["t"] = time.time()
        return el.parse(SAMPLE), ""
    monkeypatch.setattr(el, "fetch", fake)
    assert c.get("/api/admin/frn/errorlog").status_code == 401
    login(c)
    d = c.get("/api/admin/frn/errorlog").json()
    assert d["ok"] and d["page"].endswith("error_log.php") and d["total"] == 5
    assert "N8XLINK" in d["scope"]["callsigns"] and any(g["id"] == "N8XLINK" and g["count"] == 2 for g in d["mine"])
    others = [g["id"] for g in d["others"]]
    assert "uhf3radionet.ddns.net:10024" in others and "N8XLINK" not in others


def test_unreachable(monkeypatch):
    def boom(timeout):
        raise OSError("timeout")
    monkeypatch.setattr(el, "_get", boom)
    el._cache.update(t=0.0, entries=[], error="")
    entries, err = asyncio.run(el.fetch(force=True))
    assert entries == [] and "nicht erreichbar" in err


def test_frn_reports_reason(monkeypatch):
    """Nach einer Ablehnung schreibt die FRN-Seite den Grund aus dem Protokoll ins Ereignisprotokoll – einmal je Meldung."""
    from n8crosslink.frn import FrnPort

    class R:
        events = []

        def event(self, lvl, text):
            self.events.append((lvl, text))
    r = R()
    p = FrnPort.__new__(FrnPort)
    p.router, p.errorlog_seen = r, set()
    p.errorlog_scope = lambda: (["N8XLINK"], ["frn.auf-der-nachtschicht.de"])

    async def fake(timeout=8, force=False):
        return el.parse(SAMPLE), ""

    async def nosleep(_):
        return None
    monkeypatch.setattr(el, "fetch", fake)
    monkeypatch.setattr(asyncio, "sleep", nosleep)
    asyncio.run(p._errorlog_task("Login abgelehnt"))
    assert len(r.events) == 1 and "N8XLINK, Crosslink – wrong FRN password" in r.events[0][1] and "Passwort anfordern" in r.events[0][1]
    asyncio.run(p._errorlog_task("Login abgelehnt"))
    assert len(r.events) == 1                       # schon gemeldet
