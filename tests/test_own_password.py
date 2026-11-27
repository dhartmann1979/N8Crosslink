#!/usr/bin/env python3
"""👥 Eigenes Konto: auch ein Superadmin ändert sein Passwort selbst – nur mit dem aktuellen Passwort,
andere Anmeldungen enden, die aktuelle bleibt, Rolle/Sperre des eigenen Kontos bleiben tabu.

  python3 tests/test_own_password.py      (oder pytest)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from n8crosslink.app import Bridge  # noqa: E402
from n8crosslink.db import Database  # noqa: E402
from n8crosslink.web.server import create_app  # noqa: E402


def client(app):
    return TestClient(app, headers={"X-N8": "1"})


def test_superadmin_changes_own_password():
    db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))
    db.set_user("chef", "altes-passwort", "superadmin")
    app = create_app(Bridge(db))
    a, b = client(app), client(app)
    for c in (a, b):
        assert c.post("/api/login", json={"username": "chef", "password": "altes-passwort"}).status_code == 200
    url = "/api/admin/users/chef"
    # ohne / mit falschem aktuellem Passwort: abgelehnt
    assert a.patch(url, json={"password": "neues-passwort1"}).status_code == 403
    assert a.patch(url, json={"password": "neues-passwort1", "current_password": "falsch"}).status_code == 403
    # Wiederholung passt nicht / zu kurz / gleich wie alt
    assert a.patch(url, json={"password": "neues-passwort1", "password2": "anders", "current_password": "altes-passwort"}).status_code == 400
    assert a.patch(url, json={"password": "kurz", "current_password": "altes-passwort"}).status_code == 400
    assert a.patch(url, json={"password": "altes-passwort", "current_password": "altes-passwort"}).status_code == 400
    # eigene Rolle / Sperre: nein
    assert a.patch(url, json={"role": "admin"}).status_code == 400
    assert a.patch(url, json={"disabled": True}).status_code == 400
    # richtig
    r = a.patch(url, json={"password": "neues-passwort1", "password2": "neues-passwort1", "current_password": "altes-passwort",
                           "role": "superadmin", "disabled": False, "display_name": "Der Chef"})
    assert r.status_code == 200 and r.json()["password_changed"] and r.json()["sessions_ended"] == 1, r.text
    assert db.check_login("chef", "neues-passwort1") and not db.check_login("chef", "altes-passwort")
    assert db.user_role("chef") == "superadmin"
    assert a.get("/api/me").json()["user"] == "chef"          # diese Anmeldung bleibt
    assert b.get("/api/me").json()["user"] is None            # die andere ist beendet
    h = db.conn.execute("SELECT pw_hash FROM users WHERE username='chef'").fetchone()[0]
    assert h.startswith("pbkdf2_sha256$") and "neues-passwort1" not in h
    # nur Anzeigename, ohne Passwort: geht ohne aktuelles Passwort
    assert a.patch(url, json={"display_name": "Chef"}).json()["password_changed"] is False


if __name__ == "__main__":
    test_superadmin_changes_own_password()
    print("✅ Eigenes Passwort: Prüfungen ok")
