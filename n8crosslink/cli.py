"""Kommandozeile für Installer und Wartung.

  python -m n8crosslink.cli --db DB set SECTION KEY WERT
  python -m n8crosslink.cli --db DB admin BENUTZER        (Passwort über stdin)
  python -m n8crosslink.cli --db DB show [SECTION]
  python -m n8crosslink.cli --db DB users
  python -m n8crosslink.cli --db DB api-token NAME        (legt einen Portal-Token an und gibt ihn aus)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from .db import DEFAULTS, Database
from .web.server import _coerce


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
    t = sub.add_parser("api-token", help="API-Token für das HobbyRadioPortal anlegen (wird einmal ausgegeben)")
    t.add_argument("name")
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
    if args.cmd == "api-token":
        try:
            print(db.create_api_token(args.name, "installer")["token"])
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        return 0
    if args.cmd == "users":
        for u in db.list_users():
            print(f"{u['username']}\t{u['role']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
