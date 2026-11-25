"""Berechtigungsprüfer: install.sh --check-perms/--fix-perms und die Anzeige im Webinterface."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_web_security import login, make_client  # noqa: E402

H = {"X-N8": "1"}


def test_perm_endpoints(monkeypatch):
    c, bridge = make_client()
    calls = []

    async def fake_sudo(*args, timeout=60):
        calls.append(args)
        if "--check-perms" in args:
            return 0, 'Hinweis\n{"ok": false, "bad": 1, "warn": 0, "checks": [{"status": "bad", "area": "sudo", "text": "Freigaben fehlen"}]}'
        return 0, "alles korrigiert"
    monkeypatch.setattr(bridge.system, "sudo", fake_sudo)
    monkeypatch.setattr(bridge.system, "config", lambda: {"sudo": True, "fix_perms": True, "check_perms": True, "systemctl": "/bin/systemctl"})
    assert c.get("/api/admin/system/perms").status_code == 401
    login(c)
    r = c.get("/api/admin/system/perms").json()
    assert r["bad"] == 1 and r["checks"][0]["area"] == "sudo"
    assert calls[-1] == ("/opt/n8crosslink/install.sh", "--check-perms", "--json")
    r = c.post("/api/admin/system/fix-perms", headers=H).json()
    assert r["ok"] and r["message"] == "alles korrigiert" and r["check"]["bad"] == 1
    assert ("/opt/n8crosslink/install.sh", "--fix-perms") in calls


def test_perm_not_released(monkeypatch):
    c, bridge = make_client()
    monkeypatch.setattr(bridge.system, "config", lambda: {"sudo": True, "fix_perms": True})
    login(c)
    r = c.get("/api/admin/system/perms").json()
    assert not r["ok"] and r["missing"] and "--fix-perms" in r["message"]


def test_sudo_refused(monkeypatch):
    c, bridge = make_client()

    async def refused(*args, timeout=60):
        return 1, "sudo: a password is required"
    monkeypatch.setattr(bridge.system, "sudo", refused)
    monkeypatch.setattr(bridge.system, "config", lambda: {"sudo": True, "check_perms": True})
    login(c)
    assert "sudo verweigert" in c.get("/api/admin/system/perms").json()["message"]


def test_sudoers_rules_cover_webinterface():
    """Jeder Aufruf, den das Webinterface per sudo macht, steht in den Freigaben – und nicht mehr."""
    src = (ROOT / "install.sh").read_text()
    for rule in ("install.sh --fix-perms", "install.sh --check-perms --json", "install.sh --build-vocoder", "n8x-certs.sh *"):
        assert f'NOPASSWD: $APP_DIR/{rule}"' in src, rule
    assert "ALL=(root) NOPASSWD: ALL" not in src
    sysp = (ROOT / "n8crosslink" / "system.py").read_text()
    assert '"--check-perms", "--json"' in sysp and '"--fix-perms"' in sysp


@pytest.mark.skipif(os.geteuid() != 0 or not shutil.which("visudo"), reason="nur als root mit sudo")
def test_check_perms_json_runs():
    p = subprocess.run(["bash", str(ROOT / "install.sh"), "--check-perms", "--json"], capture_output=True, text=True, timeout=120)
    d = json.loads(p.stdout.strip().splitlines()[-1])
    assert set(d) >= {"ok", "bad", "warn", "checks"} and d["checks"]
    assert all(c["status"] in ("ok", "warn", "bad") and c["area"] and c["text"] for c in d["checks"])
    assert (p.returncode == 0) == d["ok"]


def test_root_helpers_leave_service_sandbox():
    """ProtectSystem=full macht /etc und /usr im Dienst schreibgeschützt – das erbt sudo. Beide root-Helfer müssen
    sich dann per systemd-run außerhalb der Sandbox neu starten (sonst „Read-only file system“ in /etc/nginx)."""
    unit = (ROOT / "systemd" / "n8crosslink.service").read_text()
    for name, flag in (("install.sh", "--fix-perms|"), ("n8x-certs.sh", "")):
        src = (ROOT / name).read_text()
        assert '! -w /etc' in src and "exec systemd-run --quiet --wait --pipe --collect" in src and "N8X_UNSANDBOXED=1" in src, name
        assert flag in src
    if "ProtectSystem=" in unit:
        assert "ReadWritePaths=/etc" not in unit       # Schutz bleibt, die Helfer verlassen die Sandbox selbst
