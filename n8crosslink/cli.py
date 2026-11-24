"""Kommandozeile für Installer und Wartung.

  python -m n8crosslink.cli --db DB set SECTION KEY WERT
  python -m n8crosslink.cli --db DB admin BENUTZER        (Passwort über stdin)
  python -m n8crosslink.cli --db DB show [SECTION]
  python -m n8crosslink.cli --db DB users
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
    if args.cmd == "users":
        for u in db.list_users():
            print(f"{u['username']}\t{u['role']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
