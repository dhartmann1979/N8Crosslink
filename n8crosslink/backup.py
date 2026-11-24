"""Verschlüsseltes Backup und Wiederherstellung.

Inhalt (vor der Verschlüsselung ein tar.gz):
  crosslink.db   – vollständige, konsistente Kopie der SQLite-Datenbank (Einstellungen inkl. Passwörter/Tokens,
                   Benutzer, Last Heard, Statistik, Ereignisse, ID-Listen, Talkgroups, Avatare)
  system.json    – freigegebene Dienste (nur zur Information, wird nicht zurückgespielt)
  manifest.json  – Version, Zeitpunkt, Rechnername, Inhalt

Die GESAMTE Datei ist verschlüsselt – auch das Manifest; es gibt keinen Klartext außer einer Kennung:
  Datei = b"N8XBAK" + Version(1) + scrypt-Salt(16) + Nonce(12) + AES-256-GCM(tar.gz)
Schlüssel = scrypt(Superadmin-Passwort, Salt, n=2^15, r=8, p=1, 32 Byte).

WICHTIG: Ohne das Superadmin-Passwort zum Zeitpunkt des Backups lässt sich die Datei nicht öffnen.
"""
from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
import tarfile
import tempfile
import time

from . import __version__

MAGIC = b"N8XBAK"
VERSION = 1
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1


class BackupError(Exception):
    pass


def _key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(password.encode("utf-8"))


def encrypt(data: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + bytes([VERSION]) + salt + nonce
    return header + AESGCM(_key(password, salt)).encrypt(nonce, data, header)


def decrypt(blob: bytes, password: str) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(blob) < 35 or not blob.startswith(MAGIC):
        raise BackupError("Keine N8-Crosslink-Backupdatei")
    if blob[6] != VERSION:
        raise BackupError(f"Unbekannte Backup-Version {blob[6]}")
    header, salt, nonce = blob[:35], blob[7:23], blob[23:35]
    try:
        return AESGCM(_key(password, salt)).decrypt(nonce, blob[35:], header)
    except InvalidTag:
        raise BackupError("Passwort falsch oder Datei beschädigt") from None


def create(db, data_dir: str, password: str, user: str) -> tuple[str, bytes]:  # noqa: ANN001
    """Erzeugt das verschlüsselte Backup. Rückgabe: (Dateiname, Inhalt)."""
    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "crosslink.db")
        dst = sqlite3.connect(snap)
        with db.lock:
            db.conn.backup(dst)          # konsistente Kopie im laufenden Betrieb
        dst.close()
        info = db.idlists_info()
        manifest = {"app": "N8 Crosslink", "version": __version__, "created": time.time(),
                    "created_by": user, "host": socket.gethostname(),
                    "contents": ["Einstellungen (inkl. Zugangsdaten)", "Benutzer", "Last Heard & Statistik",
                                 "Ereignisse", "ID-Listen", "Talkgroups", "Avatare"],
                    "counts": {"users": len(db.list_users()), "dmr_ids": info["users"],
                               "talkgroups": info["talkgroups"], "avatars": db.avatar_stats()["with_avatar"]}}
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(snap, arcname="crosslink.db")
            sysjson = os.path.join(data_dir, "system.json")
            if os.path.exists(sysjson):
                tar.add(sysjson, arcname="system.json")
            m = json.dumps(manifest, indent=2, ensure_ascii=False).encode()
            ti = tarfile.TarInfo("manifest.json")
            ti.size = len(m)
            ti.mtime = int(time.time())
            tar.addfile(ti, io.BytesIO(m))
    name = time.strftime(f"n8crosslink-backup-{socket.gethostname()}-%Y%m%d-%H%M.n8xbak")
    return name, encrypt(buf.getvalue(), password)


def inspect(blob: bytes, password: str) -> tuple[dict, bytes]:
    """Entschlüsselt, prüft den Inhalt und gibt (Manifest, DB-Bytes) zurück."""
    raw = decrypt(blob, password)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            names = tar.getnames()
            if "crosslink.db" not in names or "manifest.json" not in names:
                raise BackupError("Backup unvollständig")
            manifest = json.loads(tar.extractfile("manifest.json").read())
            dbbytes = tar.extractfile("crosslink.db").read()
    except (tarfile.TarError, json.JSONDecodeError) as e:
        raise BackupError(f"Backup beschädigt: {e}") from None
    if not dbbytes.startswith(b"SQLite format 3"):
        raise BackupError("Datenbank im Backup ungültig")
    return manifest, dbbytes


def restore_into(db, dbbytes: bytes) -> None:  # noqa: ANN001
    """Spielt die Datenbank aus dem Backup in die laufende Datenbank ein (gleiche Datei, gleiche Verbindung)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "restore.db")
        with open(p, "wb") as f:
            f.write(dbbytes)
        src = sqlite3.connect(p)
        ok = src.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            src.close()
            raise BackupError(f"Datenbank im Backup fehlerhaft: {ok}")
        with db.lock:
            src.backup(db.conn)
            db.conn.commit()
        src.close()
    # Schema ergänzen, falls das Backup von einer älteren Version stammt
    db.__init__(db.path)
