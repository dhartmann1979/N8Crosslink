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
    assert d["ok"] and calls[-1] == ("status", "8080", "80", "443") and d["settings"] == {"email": "", "staging": False, "http_port": 80, "https_port": 443}
    r = c.post("/api/admin/domains", json={"domain": "Crosslink.Example.org.", "email": "a@b.de", "staging": True}, headers=H).json()
    assert r["ok"] and calls[-1] == ("add", "crosslink.example.org", "a@b.de", "8080", "80", "443", "staging")
    assert bridge.db.load_config()["https"] == {"email": "a@b.de", "staging": True, "http_port": 80, "https_port": 443}
    for bad in ({"domain": "evil;rm -rf", "email": "a@b.de"}, {"domain": "x.example.org", "email": "nope"}, {"domain": "-x.org", "email": "a@b.de"}):
        assert c.post("/api/admin/domains", json=bad, headers=H).status_code == 400, bad
    assert c.post("/api/admin/domains/x.example.org/renew", headers=H).json()["ok"] and calls[-1] == ("renew", "x.example.org")
    assert c.delete("/api/admin/domains/x.example.org", headers=H).json()["ok"] and calls[-1] == ("remove", "x.example.org")
    assert c.post("/api/admin/domains/Bad_Domain/renew", headers=H).status_code == 400


@pytest.mark.skipif(os.geteuid() != 0, reason="der Helfer läuft nur als root")
def test_helper_validates_input():
    sh = str(ROOT / "n8x-certs.sh")
    def run(*a):
        p = subprocess.run([sh, *a], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])
    A = ("80", "443")
    for args, msg in ((("add", "Evil;rm", "a@b.de", "8070", *A), "Ungültige Domain"), (("add", "x.example.org", "nope", "8070", *A), "E-Mail"),
                      (("add", "x.example.org", "a@b.de", "80", *A), "Port 80"), (("add", "x.example.org", "a@b.de", "8070", *A, "--evil"), "unbekannte Option"),
                      (("add", "x.example.org", "a@b.de", "8070"), "add DOMAIN"), (("add", "x.example.org", "a@b.de", "8070", "81", "81"), "verschieden"),
                      (("add", "x.example.org", "a@b.de", "8070", "80", "99999"), "Ungültiger Port"), (("ports", "8070", "80"), "ports PORT"),
                      (("ports", "8070", "8070", "443"), "verschieden"), (("status", "8070", "x", "443"), "Ungültiger Port"),
                      (("renew", "../etc"), "Ungültige Domain"), (("status", "abc"), "Ungültiger Port"), (("rm",), "Aufruf")):
        rc, j = run(*args)
        assert rc != 0 and not j["ok"] and msg in j["message"], (args, j)
    rc, j = run("remove", "nicht-verwaltet.example.org")
    assert rc != 0 and "nicht verwaltet" in j["message"]


def test_ports_page(monkeypatch):
    c, bridge = make_client()
    calls = []

    async def fake(*args, timeout=300):
        calls.append(args)
        if args[0] == "status":
            return {"ok": True, "sites": [{"domain": "x.example.org"}]}
        return {"ok": True, "message": "umgestellt"}
    monkeypatch.setattr(bridge.system, "certs", fake)
    assert c.get("/api/admin/ports").status_code == 401
    login(c)
    d = c.get("/api/admin/ports").json()
    assert d["values"]["https.http_port"] == 80 and d["values"]["dmr.local_port"] == 0 and d["values"]["general.web_host"]
    # Konflikte und ungültige Werte
    for bad in ({"https.http_port": 8080}, {"https.https_port": 80}, {"frn.port": 0}, {"dmr.local_port": -1}, {"dmr.port": 70000},
                {"frn.port": "abc"}, {"general.web_host": "evil host"}):
        assert c.post("/api/admin/ports", json=bad, headers=H).status_code == 400, bad
    r = c.post("/api/admin/ports", json={"dmr.local_port": 62032, "frn.port": 10024}, headers=H).json()
    assert r["ok"] and r["changed"] == ["dmr.local_port"] and r["restart_bridge"] and "nginx" not in r
    assert bridge.db.load_config()["dmr"]["local_port"] == 62032
    r = c.post("/api/admin/ports", json={"https.http_port": 8081, "https.https_port": 8443}, headers=H).json()
    assert r["nginx"]["ok"] and calls[-1] == ("ports", "8080", "8081", "8443") and not r["restart_service"]
    assert c.post("/api/admin/ports", json={}, headers=H).json()["changed"] == []
    assert c.post("/api/admin/ports/apply", headers=H).json()["ok"] and calls[-1] == ("ports", "8080", "8081", "8443")


def test_dmr_local_port_binds():
    import asyncio
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 0)); srv = s.getsockname()[1]
    f = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); f.bind(("0.0.0.0", 0)); lp = f.getsockname()[1]; f.close()

    async def main():
        loop = asyncio.get_running_loop()
        t, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, remote_addr=("127.0.0.1", srv), local_addr=("0.0.0.0", lp))
        t.sendto(b"x"); await asyncio.sleep(0.05)
        _, addr = s.recvfrom(10); t.close()
        return addr[1]
    assert asyncio.run(main()) == lp
