"""📰 Portal-Feed für den adn-frn-server: Live-Zusammenfassung, verschlüsselt mit dem Sync-Schlüssel (n8crosslink/n8feed.py)."""
from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from n8crosslink import n8feed  # noqa: E402
from tests.test_web_security import make_client  # noqa: E402

KEY = "q" * 32
H = {"X-N8": "1", "Content-Type": n8feed.CTYPE}


def req(key=KEY, ts=None):
    return n8feed.seal({"path": n8feed.PATH, "ts": ts or time.time(), "id": secrets.token_hex(8), "data": {}}, key)


def test_feed_off_wrong_key_and_summary():
    c, bridge = make_client()
    assert c.post(n8feed.PATH, content=req(), headers=H).status_code == 404          # aus
    bridge.db.save_section("general", {"portal_feed": True, "portal_feed_key": KEY})
    assert c.post(n8feed.PATH, content=req("x" * 32), headers=H).status_code == 403
    assert c.post(n8feed.PATH, content=req(ts=1), headers=H).status_code == 403      # abgelaufen
    body = req()
    r = c.post(n8feed.PATH, content=body, headers=H)
    assert r.status_code == 200, r.text
    d = n8feed.unseal(r.content, KEY)["data"]
    assert d["system"] == "crosslink" and d["kpis"][0]["label"] == "Networks online"
    assert c.post(n8feed.PATH, content=body, headers=H).status_code == 403            # nur einmal
    # der Schlüssel erscheint nie in der Konfiguration für das Webinterface
    from n8crosslink.db import Database
    assert Database.public_config(bridge.db.load_config())["general"]["portal_feed_key"] == "********"
