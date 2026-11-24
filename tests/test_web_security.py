#!/usr/bin/env python3
"""Weboberfläche: Sicherheits-Header, keine API-Doku, N8 Theme 2 (Speichern/Prüfen), N8 Kit eingebunden.

  python3 tests/test_web_security.py      (oder pytest)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from n8crosslink.app import Bridge  # noqa: E402
from n8crosslink.db import Database  # noqa: E402
from n8crosslink.web import n8_security  # noqa: E402
from n8crosslink.web.server import _theme, create_app  # noqa: E402


def make_client():
    db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
    db.set_user("chef", "chef-passwort", "superadmin")
    bridge = Bridge(db)
    return TestClient(create_app(bridge)), bridge


def login(c):
    r = c.post("/api/login", json={"username": "chef", "password": "chef-passwort"})
    assert r.status_code == 200, r.text


def test_no_api_docs():
    c, _ = make_client()
    for p in ("/docs", "/redoc", "/openapi.json"):
        r = c.get(p)
        assert r.status_code == 404, p


def test_security_headers():
    c, _ = make_client()
    h = c.get("/").headers
    csp = h["content-security-policy"]
    for part in ("default-src 'self'", "object-src 'none'", "base-uri 'self'", "frame-ancestors 'self'", "form-action 'self'"):
        assert part in csp
    assert "camera=()" in h["permissions-policy"] and "microphone=()" in h["permissions-policy"]
    assert h["x-frame-options"] == "SAMEORIGIN" and h["x-content-type-options"] == "nosniff"
    assert "strict-transport-security" not in h and "server" not in h
    assert "max-age" in c.get("/", headers={"X-Forwarded-Proto": "https"}).headers["strict-transport-security"]
    assert n8_security.UVICORN_KWARGS == {"server_header": False}
    assert "UVICORN_KWARGS" in (ROOT / "n8crosslink" / "app.py").read_text()


def test_theme_validation_and_save():
    t = _theme({"preset": "ember", "accent": "#FF0000", "accent2": "red", "glow": 999, "radius": -3, "blur": False, "evil": "<x>"})
    assert t["preset"] == "ember" and t["accent"] == "#ff0000" and t["accent2"] == ""
    assert t["glow"] == 150 and t["radius"] == 0 and t["blur"] is False and "evil" not in t
    assert _theme("<script>")["preset"] == "n8"
    c, bridge = make_client()
    assert c.post("/api/admin/theme", json={"theme": {"preset": "ocean"}}).status_code == 401
    login(c)
    r = c.post("/api/admin/theme", json={"theme": {"preset": "ocean", "accent": "#123456"}})
    assert r.status_code == 200 and r.json()["theme"]["accent"] == "#123456"
    assert c.get("/api/theme").json()["theme"]["preset"] == "ocean"
    html = c.get("/").text
    assert 'N8Theme.apply({"accent": "#123456"' in html or '"preset": "ocean"' in html


def test_page_loads_kit():
    c, _ = make_client()
    html = c.get("/").text
    for f in ("/static/n8-theme.js", "/static/n8-theme.css", "/static/n8-kit.js", "/static/n8-kit.css", "/static/i18n-crosslink.js", 'id="updateBanner"'):
        assert f in html, f
    assert c.get("/static/n8-kit.js").status_code == 200
    js = (ROOT / "n8crosslink" / "web" / "static" / "i18n-crosslink.js").read_text()
    assert "base: 'de'" in js and "'Statistik': 'Statistics'" in js


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("✓", name)
