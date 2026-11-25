"""Keep-Alive (N8 Admin-Kit): Einstellungen, Health nur lokal, Halt bei manuellem Stopp, Installer richtet den Timer ein."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_web_security import login, make_client  # noqa: E402


def test_keepalive_api_and_health():
    c, bridge = make_client()
    assert c.get("/api/admin/keepalive").status_code == 401
    login(c)
    d = c.get("/api/admin/keepalive").json()
    assert d["conf"]["enabled"] is True
    d = c.post("/api/admin/keepalive", json={"heartbeat_url": "https://hc-ping.com/x-1", "net_restart": False}).json()
    assert d["conf"]["heartbeat_url"] == "https://hc-ping.com/x-1" and d["conf"]["net_restart"] is False
    assert c.post("/api/admin/keepalive", json={"heartbeat_url": "https://x/$(id)"}).status_code == 400
    assert c.get("/api/n8/health").status_code == 403          # TestClient ist nicht 127.0.0.1


def test_kit_and_installer():
    kit = ROOT / "scripts" / "n8-admin.sh"
    assert subprocess.run(["bash", "-n", str(kit)]).returncode == 0
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / "n8-admin.conf")]).returncode == 0
    for repo in ("hobbyradioportal", "adn-frn-server", "hblink4-freeradioid", "n8-hotspot"):
        o = ROOT.parent / repo / "scripts" / "n8-admin.sh"
        if o.exists():
            assert o.read_bytes() == kit.read_bytes(), repo
    inst = (ROOT / "install.sh").read_text()
    assert 'n8-admin.sh" setup-keepalive' in inst and "n8crosslink-keepalive.timer" in inst
    conf = (ROOT / "scripts" / "n8-admin.conf").read_text()
    for k in ("#frn", "#dmr", "#zello", "N8_KA_NET_UNITS=(n8crosslink.service)"):
        assert k in conf
