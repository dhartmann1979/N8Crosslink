"""Ohne Anmeldung keine IPs und keine Ports (Live-Daten, Ereignisse, Last Heard, Kopfzeile, WebSocket)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from n8crosslink.web.public import MASK, scrub, text  # noqa: E402
from tests.test_web_security import login, make_client  # noqa: E402

IP_OR_PORT = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|:\d{2,5}\b|\b[Pp]ort\w*\s*[=:]?\s*\d")


def test_text_rules():
    assert text("DMR verbunden mit 127.0.0.1 als 262000101 (TG 262, TS2)") == f"DMR verbunden mit {MASK} als 262000101 (TG 262, TS2)"
    assert text("Verbindung zu frn.auf-der-nachtschicht.de:10024 fehlgeschlagen") == "Verbindung zu frn.auf-der-nachtschicht.de fehlgeschlagen"
    assert text("Zello ws://127.0.0.1:8799/ws") == f"Zello ws://{MASK}" and text("wss://zello.io/ws") == "wss://zello.io/ws"
    assert MASK in text("Anmeldung von 2001:db8::1") and MASK in text("[::1]:8080")
    assert text("Port 8080 und 443") == f"Port {MASK}" and text("dmr.local_port=62032") == f"dmr.local_port={MASK}"
    for keep in ("Update 1.12.0 → 1.13.0 um 10:28:25", "438.950 MHz FM", "TG 26201 · TS2", "https://github.com/dhartmann1979/N8Crosslink"):
        assert text(keep) == keep
    s = scrub({"ports": {"frn": {"server": "x:1", "detail": "verbinde 10.0.0.5:10024", "clients": [{"callsign": "DL1ABC"}]}}})
    assert s == {"ports": {"frn": {"detail": f"verbinde {MASK}", "clients": [{"callsign": "DL1ABC"}]}}}


def _leaks(obj) -> list:
    return [m.group(0) for m in IP_OR_PORT.finditer(json.dumps(obj, ensure_ascii=False))]


def test_anonymous_sees_no_addresses():
    c, bridge = make_client()
    bridge.router.event("info", "DMR verbunden mit 192.168.79.204:62031 als 2657777")
    bridge.router.event("warn", "FRN: Verbindung zu frn.example.org:10024 fehlgeschlagen")
    st = c.get("/api/state").json()
    for p in st["ports"].values():
        assert "server" not in p
    assert not _leaks(st["ports"]), _leaks(st["ports"])
    ev = c.get("/api/events").json()
    assert not _leaks(ev) and any("frn.example.org fehlgeschlagen" in e["text"] for e in ev)
    assert not _leaks(c.get("/api/lastheard").json())
    with c.websocket_connect("/ws") as w:
        assert "server" not in json.dumps(json.loads(w.receive_text())["ports"])
    # angemeldet: alles
    login(c)
    st = c.get("/api/state").json()
    assert set(st["ports"]) == set(bridge.router.snapshot()["ports"])
    assert any("192.168.79.204:62031" in e["text"] for e in c.get("/api/events").json())


def test_server_name_masked_for_guests():
    c, bridge = make_client()
    bridge.cfg["general"]["server_name"] = "89.163.151.243:8080"
    bridge.db.save_section("general", {"server_name": "89.163.151.243:8080"})
    assert "89.163" not in c.get("/").text and "89.163" not in c.get("/api/info").json()["server_name"]
    login(c)
    assert "89.163.151.243:8080" in c.get("/api/info").json()["server_name"]
