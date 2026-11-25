"""Neueinrichtung ohne Fragen: install.sh N8X_SETUP_FILE → cli apply-setup (Web-Installer des HobbyRadioPortals)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from n8crosslink.cli import apply_setup
from n8crosslink.db import Database

ROOT = Path(__file__).resolve().parent.parent


def test_apply_setup_sections_and_superadmin(tmp_path):
    db = Database(str(tmp_path / "c.db"))
    out = apply_setup(db, {"general": {"title": "N8 Crosslink", "web_port": "8070"},
                           "frn": {"enabled": True, "server": "127.0.0.1", "port": 10024, "email": "x@example.org", "password": "geheim",
                                   "callsign": "N8XLINK", "net": "Nachtschicht"},
                           "dmr": {"enabled": "true", "host": "127.0.0.1", "peer_id": "262000101", "password": "pass"},
                           "zello": {"enabled": False}, "vocoder": {"vocoder_mode": "n8vocoder"},
                           "admin_user": "sysop", "admin_password": "Lang-genug-1"})
    assert out["superadmin"] == "sysop" and set(out["sections"]) == {"general", "frn", "dmr", "zello", "vocoder"}
    c = db.load_config(); g, f, d = c["general"], c["frn"], c["dmr"]
    assert g["web_port"] == 8070 and f["net"] == "Nachtschicht" and d["enabled"] is True and d["peer_id"] == 262000101
    users = {u["username"]: u["role"] for u in db.list_users()}
    assert users.get("sysop") == "superadmin" and "n8schicht" not in users          # Standard-Login weg


@pytest.mark.parametrize("bad", [{"frn": {"nope": 1}}, {"gibtsnicht": {}}, {"admin_password": "kurz"}, {"frn": "x"}])
def test_apply_setup_rejects(tmp_path, bad):
    db = Database(str(tmp_path / "c.db"))
    with pytest.raises(ValueError):
        apply_setup(db, bad)


def test_cli_and_installer(tmp_path):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"general": {"title": "X"}, "admin_password": "Lang-genug-1"}))
    r = subprocess.run([sys.executable, "-m", "n8crosslink.cli", "--db", str(tmp_path / "c.db"), "apply-setup", str(f)],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and json.loads(r.stdout)["superadmin"] == "n8schicht", r.stderr
    s = (ROOT / "install.sh").read_text()
    assert 'elif [[ -n "${N8X_SETUP_FILE:-}" ]]' in s and "cli apply-setup" in s
    assert subprocess.run(["bash", "-n", str(ROOT / "install.sh")]).returncode == 0
