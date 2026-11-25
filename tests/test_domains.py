"""Domains & HTTPS (Let's Encrypt): Webinterface → root-Helfer n8x-certs.sh."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_web_security import login, make_client  # noqa: E402

H = {"X-N8": "1"}


def test_domain_endpoints(monkeypatch):
    c, bridge = make_client()
    calls = []

    async def fake(*args, timeout=300):
        calls.append(args)
        if args[0] == "status":
            return {"ok": True, "nginx": True, "certbot": True, "sites": [{"domain": "localhost.localdomain.example", "https": True, "cert": None}]}
        return {"ok": True, "message": "ok"}
    monkeypatch.setattr(bridge.system, "certs", fake)
    assert c.get("/api/admin/domains").status_code == 401                      # nur angemeldet
    login(c)
    d = c.get("/api/admin/domains").json()
    assert d["ok"] and calls[-1] == ("status", "8080") and d["settings"] == {"email": "", "staging": False}
    r = c.post("/api/admin/domains", json={"domain": "Crosslink.Example.org.", "email": "a@b.de", "staging": True}, headers=H).json()
    assert r["ok"] and calls[-1] == ("add", "crosslink.example.org", "a@b.de", "8080", "staging")
    assert bridge.db.load_config()["https"] == {"email": "a@b.de", "staging": True}
    for bad in ({"domain": "evil;rm -rf", "email": "a@b.de"}, {"domain": "x.example.org", "email": "nope"}, {"domain": "-x.org", "email": "a@b.de"}):
        assert c.post("/api/admin/domains", json=bad, headers=H).status_code == 400, bad
    assert c.post("/api/admin/domains/x.example.org/renew", headers=H).json()["ok"] and calls[-1] == ("renew", "x.example.org")
    assert c.delete("/api/admin/domains/x.example.org", headers=H).json()["ok"] and calls[-1] == ("remove", "x.example.org")
    assert c.post("/api/admin/domains/Bad_Domain/renew", headers=H).status_code == 400


def test_not_for_the_portal():
    from fastapi.testclient import TestClient
    from n8crosslink.web.server import create_app
    _, bridge = make_client()
    local = TestClient(create_app(bridge), base_url="http://127.0.0.1:8070", client=("127.0.0.1", 5000))
    assert local.get("/api/admin/domains", headers={"X-HobbyRadioPortal": "1"}).status_code == 401


@pytest.mark.skipif(os.geteuid() != 0, reason="der Helfer läuft nur als root")
def test_helper_validates_input():
    sh = str(ROOT / "n8x-certs.sh")
    def run(*a):
        p = subprocess.run([sh, *a], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])
    for args, msg in ((("add", "Evil;rm", "a@b.de", "8070"), "Ungültige Domain"), (("add", "x.example.org", "nope", "8070"), "E-Mail"),
                      (("add", "x.example.org", "a@b.de", "80"), "Port 80"), (("add", "x.example.org", "a@b.de", "8070", "--evil"), "unbekannte Option"),
                      (("renew", "../etc"), "Ungültige Domain"), (("status", "abc"), "Ungültiger Port"), (("rm",), "Aufruf")):
        rc, j = run(*args)
        assert rc != 0 and not j["ok"] and msg in j["message"], (args, j)
    rc, j = run("remove", "nicht-verwaltet.example.org")
    assert rc != 0 and "nicht verwaltet" in j["message"]
