#!/usr/bin/env python3
"""HobbyRadioPortal auf demselben Rechner (ohne Token, ab 1.11.0) und die Einstellungs-Beschreibung (GET/PUT /api/admin/settings)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from n8crosslink.db import DEFAULTS, SECRET_KEYS  # noqa: E402
from n8crosslink.settings_schema import FIELDS, NOT_DESCRIBED, SettingsError, validate  # noqa: E402
from tests.test_web_security import login, make_client  # noqa: E402


H = {"X-HobbyRadioPortal": "1", "X-Portal-User": "dirk<x>"}


def _local():
    """Client wie das Portal: von 127.0.0.1 an http://127.0.0.1:8070/."""
    from fastapi.testclient import TestClient
    from n8crosslink.web.server import create_app
    c, bridge = make_client()
    return TestClient(create_app(bridge), base_url="http://127.0.0.1:8070", client=("127.0.0.1", 50000)), bridge, c


def test_schema_covers_all_settings():
    for sec, vals in DEFAULTS.items():
        for k in vals:
            if (sec, k) in NOT_DESCRIBED:
                continue
            assert f"{sec}.{k}" in FIELDS, f"{sec}.{k} fehlt in settings_schema.py"
    for key in FIELDS:
        sec, _, k = key.partition(".")
        assert k in DEFAULTS[sec], key


def test_validate():
    assert validate({"frn.port": "10025", "dmr.slot": "1", "routes.frn_dmr": "false"}) == {"frn": {"port": 10025}, "dmr": {"slot": 1}, "routes": {"frn_dmr": False}}
    assert validate({"frn.password": ""}) == {}
    for bad in ({"frn.port": 70000}, {"dmr.slot": "3"}, {"x.y": 1}, {"general.links": "{}"}, {"frn.enabled": "vielleicht"}):
        try:
            validate(bad)
        except SettingsError:
            continue
        raise AssertionError(bad)
    try:
        validate({"general.web_port": 80}, api=True)
        raise AssertionError("gesperrt")
    except SettingsError:
        pass


def test_portal_paths_and_settings():
    c, bridge, _ = _local()
    d = c.get("/api/admin/settings", headers=H).json()
    ids = [s["id"] for s in d["sections"]]
    assert ids == ["general", "announce", "routes", "frn", "dmr", "zello", "vocoder", "ids"]
    keys = {f["key"] for s in d["sections"] for f in s["fields"]}
    assert "general.web_port" not in keys and "frn.server" in keys
    pw = next(f for s in d["sections"] for f in s["fields"] if f["key"] == "dmr.password")
    assert pw["value"] == "" and pw["set"] is True
    r = c.put("/api/admin/settings", headers=H, json={"changes": {"routes.zello_dmr": False, "frn.port": 10025}}).json()
    assert set(r["changed"]) == {"routes.zello_dmr", "frn.port"} and r["restart_required"]
    assert bridge.cfg["routes"]["zello_dmr"] is False
    assert c.put("/api/admin/settings", headers=H, json={"changes": {"general.web_port": 81}}).status_code == 400
    assert c.get("/api/admin/vocoder/params", headers=H).status_code == 200
    for path in ("/api/admin/users", "/api/admin/config", "/api/admin/system", "/api/admin/update"):
        assert c.get(path, headers=H).status_code == 401, path
    assert c.get("/api/admin/api-tokens", headers=H).status_code in (401, 404)        # gibt es nicht mehr
    assert c.post("/api/admin/backup", headers=H, json={}).status_code in (401, 422)
    ev = [e["text"] for e in bridge.db.events(50)]
    assert any("api:HobbyRadioPortal (dirkx)" in t for t in ev), ev[:3]


def test_not_the_portal():
    c, bridge, remote = _local()
    assert c.get("/api/admin/settings").status_code == 401                              # ohne Kennung
    assert remote.get("/api/admin/settings", headers=H).status_code == 401              # anderer Rechner
    for extra in ({"X-Forwarded-For": "203.0.113.9"}, {"X-Real-IP": "203.0.113.9"}, {"Forwarded": "for=1.2.3.4"},
                  {"Via": "1.1 nginx"}, {"Host": "crosslink.example.org"}):
        assert c.get("/api/admin/settings", headers={**H, **extra}).status_code == 401, extra


def test_switch_off_and_info_nets(monkeypatch):
    c, bridge, _ = _local()
    monkeypatch.setenv("N8X_PORTAL_LOCAL", "0")
    assert c.get("/api/admin/settings", headers=H).status_code == 401
    bridge.db.save_section("zello", {"enabled": False})
    i = c.get("/api/info").json()
    assert i["nets"] == ["frn", "dmr"] and i["nets_label"] == "FRN · DMR"
    assert "FRN · DMR · " in c.get("/").text and "Zello Bridge" not in c.get("/").text


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("✓", n)
