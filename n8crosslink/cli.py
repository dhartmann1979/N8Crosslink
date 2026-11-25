"""Kommandozeile für Installer und Wartung.

  python -m n8crosslink.cli --db DB set SECTION KEY WERT
  python -m n8crosslink.cli --db DB admin BENUTZER        (Passwort über stdin)
  python -m n8crosslink.cli --db DB show [SECTION]
  python -m n8crosslink.cli --db DB users
  python -m n8crosslink.cli --db DB apply-setup DATEI     (Neueinrichtung ohne Fragen aus JSON – install.sh N8X_SETUP_FILE)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from .db import DEFAULTS, Database
from .web.server import _coerce


SETUP_SECTIONS = ("general", "frn", "dmr", "zello", "vocoder")


def apply_setup(db: Database, data: dict) -> dict:
    """Neueinrichtung ohne Fragen (install.sh mit N8X_SETUP_FILE, z. B. aus dem Web-Installer des HobbyRadioPortals).

    {"general": {...}, "frn": {...}, "dmr": {...}, "zello": {...}, "vocoder": {...},
     "admin_user": "n8schicht", "admin_password": "…"}   – Schlüssel wie im Adminportal (DEFAULTS), unbekannte werden abgewiesen.
    Ein anderer Superadmin-Name ersetzt den Standard-Login n8schicht/n8schicht; ohne Passwort bleibt der Standard-Login."""
    if not isinstance(data, dict):
        raise ValueError("JSON-Objekt erwartet")
    unknown = [k for k in data if k not in SETUP_SECTIONS + ("admin_user", "admin_password")]
    if unknown:
        raise ValueError("unbekannte Schlüssel: " + ", ".join(unknown))
    done: dict = {"sections": {}}
    for sec in SETUP_SECTIONS:
        vals = data.get(sec) or {}
        if not isinstance(vals, dict):
            raise ValueError(f"{sec}: Objekt erwartet")
        bad = [k for k in vals if k not in DEFAULTS[sec]]
        if bad:
            raise ValueError(f"{sec}: unbekannte Felder " + ", ".join(bad))
        if vals:
            db.save_section(sec, _coerce(sec, vals))
            done["sections"][sec] = sorted(vals)
    pw = str(data.get("admin_password") or "")
    user = str(data.get("admin_user") or "n8schicht").strip()
    if pw:
        if len(pw) < 8:
            raise ValueError("admin_password: mindestens 8 Zeichen")
        if not user.replace(".", "").replace("_", "").replace("-", "").isalnum() or len(user) > 32:
            raise ValueError("admin_user: nur Buchstaben, Ziffern, . _ -")
        db.set_user(user, pw, "superadmin")
        if user != "n8schicht":
            db.delete_user("n8schicht")          # Standard-Login n8schicht/n8schicht gibt es dann nicht mehr
        done["superadmin"] = user
    return done


def main() -> int:
    ap = argparse.ArgumentParser(prog="n8crosslink-cli")
    ap.add_argument("--db", default=os.environ.get("N8X_DB", "/opt/n8crosslink/data/crosslink.db"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("section")
    s.add_argument("key")
    s.add_argument("value")
    a = sub.add_parser("admin")
    a.add_argument("username")
    sh = sub.add_parser("show")
    sh.add_argument("section", nargs="?")
    sub.add_parser("users")
    ik = sub.add_parser("import-zello-key", help="PEM-Private-Key prüfen und in die Datenbank übernehmen")
    ik.add_argument("file")
    ik.add_argument("--issuer", default=None)
    sub.add_parser("zello-key-info")
    vt = sub.add_parser("vocoder-test")
    vt.add_argument("--mode", default=None, help="n8vocoder | usb | ambeserver (Standard: aus der Konfiguration)")
    vt.add_argument("--host", default=None)
    vt.add_argument("--port", type=int, default=None)
    b = sub.add_parser("backup")
    b.add_argument("--out", default=".")
    r = sub.add_parser("restore")
    r.add_argument("file")
    st = sub.add_parser("apply-setup", help="Neueinrichtung ohne Fragen aus einer JSON-Datei (install.sh N8X_SETUP_FILE)")
    st.add_argument("file")
    args = ap.parse_args()
    db = Database(args.db)

    if args.cmd == "set":
        if args.section not in DEFAULTS or args.key not in DEFAULTS[args.section]:
            print(f"Unbekannt: {args.section}.{args.key}", file=sys.stderr)
            return 2
        vals = _coerce(args.section, {args.key: args.value})
        db.save_section(args.section, vals)
        return 0
    if args.cmd == "admin":
        pw = sys.stdin.readline().rstrip("\n") if not sys.stdin.isatty() else getpass.getpass("Passwort: ")
        if len(pw) < 8:
            print("Passwort muss mindestens 8 Zeichen haben", file=sys.stderr)
            return 2
        db.set_user(args.username, pw, "superadmin")
        print(f"Superadmin „{args.username}“ gespeichert")
        return 0
    if args.cmd == "show":
        cfg = Database.public_config(db.load_config())
        print(json.dumps(cfg[args.section] if args.section else cfg, indent=2, ensure_ascii=False))
        return 0
    if args.cmd in ("import-zello-key", "zello-key-info"):
        import hashlib

        from cryptography.hazmat.primitives import serialization

        def fingerprint(pem: str) -> str:
            key = serialization.load_pem_private_key(pem.encode(), password=None)
            pub = key.public_key().public_bytes(serialization.Encoding.DER,
                                                serialization.PublicFormat.SubjectPublicKeyInfo)
            return "SHA256:" + hashlib.sha256(pub).hexdigest()[:32]
        if args.cmd == "zello-key-info":
            pem = db.load_config()["zello"].get("private_key") or ""
            if not pem:
                print("kein Zello-Schlüssel in der Datenbank")
                return 1
            print(f"Zello-Schlüssel in der Datenbank: {fingerprint(pem)}")
            return 0
        try:
            with open(args.file) as f:
                pem = f.read().strip() + "\n"
            fp = fingerprint(pem)
        except Exception as e:  # noqa: BLE001
            print(f"Keine gültige PEM-Private-Key-Datei: {e}", file=sys.stderr)
            return 2
        vals = {"private_key": pem, "auth_mode": "key"}
        if args.issuer:
            vals["issuer"] = args.issuer
        db.save_section("zello", vals)
        # Gegenprüfung: genau dieser Schlüssel steht jetzt in der Datenbank
        if fingerprint(db.load_config()["zello"]["private_key"]) != fp:
            print("Gegenprüfung fehlgeschlagen – Datei NICHT löschen", file=sys.stderr)
            return 3
        issuer = db.load_config()["zello"].get("issuer")
        print(f"OK {fp}" + ("" if issuer else " – Hinweis: Issuer fehlt noch (Admin → Zello)"))
        return 0
    if args.cmd == "vocoder-test":
        import asyncio

        from .vocoder import Vocoder, tone_test
        cfg = dict(db.load_config()["vocoder"])
        if args.mode:
            cfg["vocoder_mode"] = args.mode
        m = cfg["vocoder_mode"]
        if args.host:
            cfg["ambeserver_host"] = args.host
        if args.port:
            cfg["ambeserver_port"] = args.port

        async def run() -> int:
            v = Vocoder(cfg)
            await v.start()
            r = await tone_test(v) if v.running else {"ok": False, "frames": 0}
            await v.stop()
            if r["ok"]:
                print(f"OK {m}: {r['ms']} ms je Rahmen, 1 kHz -> {r['hz']} Hz {v.product} {v.version}".strip())
                return 0
            print(f"FEHLER {m}: {r.get('frames', 0)} Rahmen, {r.get('hz', 0)} Hz – {v.product or 'keine Antwort'}")
            return 1
        return asyncio.run(run())
    if args.cmd in ("backup", "restore"):
        from . import backup as bk
        pw = sys.stdin.readline().rstrip("\n") if not sys.stdin.isatty() else getpass.getpass("Superadmin-Passwort: ")
        if args.cmd == "backup":
            supers = [u["username"] for u in db.list_users() if u["role"] == "superadmin"]
            user = next((u for u in supers if db.check_login(u, pw)), None)
            if not user:
                print("Passwort passt zu keinem Superadmin", file=sys.stderr)
                return 2
            name, blob = bk.create(db, os.path.dirname(os.path.abspath(args.db)), pw, user)
            path = os.path.join(args.out, name)
            with open(path, "wb") as f:
                f.write(blob)
            print(f"Backup verschlüsselt gespeichert: {path}")
            return 0
        try:
            with open(args.file, "rb") as f:
                manifest, dbbytes = bk.inspect(f.read(), pw)
            bk.restore_into(db, dbbytes)
        except (OSError, bk.BackupError) as e:
            print(f"Wiederherstellung fehlgeschlagen: {e}", file=sys.stderr)
            return 2
        print(f"Backup vom {manifest.get('created')} (Version {manifest.get('version')}) eingespielt")
        return 0
    if args.cmd == "apply-setup":
        try:
            done = apply_setup(db, json.load(open(args.file, encoding="utf-8")))
        except (OSError, ValueError) as e:
            print(f"Einrichtung fehlgeschlagen: {e}", file=sys.stderr)
            return 2
        print(json.dumps(done, ensure_ascii=False))
        return 0
    if args.cmd == "users":
        for u in db.list_users():
            print(f"{u['username']}\t{u['role']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
