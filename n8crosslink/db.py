"""SQLite-Speicher: Einstellungen, Benutzer, Last Heard, Ereignisse, DMR-ID-Datenbank."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time

DEFAULTS: dict = {
    "general": {
        "title": "N8 Crosslink",
        "server_name": "crosslink.die-n8schicht.de",
        "web_host": "0.0.0.0",
        "web_port": 8080,
        "hang_time_ms": 600,        # Sperrzeit nach einer Durchsage (Ping-Pong-Schutz)
        "tot_s": 180,               # Time-Out-Timer pro Durchgang
        "jitter_ms": 240,           # Vorpuffer für DMR-/Zello-Ausgang
        "announcement": "",
        # Sprachansage des Rufzeichens am Anfang eines Durchgangs (espeak-ng)
        "announce_enabled": False,
        "announce_frn": True, "announce_dmr": False, "announce_zello": False,
        "announce_spell": "letters",     # letters | nato
        "announce_text": "{call}",
        "announce_repeat_min": 0,        # 0 = jedes Mal, sonst je Station höchstens alle X Minuten
        "announce_without_call": False,  # auch ohne Rufzeichen (Name) ansagen
        "announce_voice": "de", "announce_speed": 165,
        "announce_level_db": -6.0, "announce_pause_ms": 250,
        "keep_days": 90,
        "watchdog_offline_s": 120,   # Netz so lange offline -> Watchdog baut es komplett neu auf
        "update_check": True,        # stündlich zur vollen Stunde auf GitHub prüfen
        "update_repo": "dhartmann1979/N8Crosslink",
        "update_branch": "main",
        "links": [
            {"name": "Auf der Nachtschicht FRN", "url": "https://frn.auf-der-nachtschicht.de"},
            {"name": "DMR Die N8schicht", "url": "https://dmr.die-n8schicht.de"},
        ],
    },
    "routes": {
        "frn_dmr": True, "frn_zello": True,
        "dmr_frn": True, "dmr_zello": True,
        "zello_frn": True, "zello_dmr": True,
    },
    "frn": {
        "enabled": True,
        "server": "frn.auf-der-nachtschicht.de", "port": 10024,
        "backup_server": "", "backup_port": 10024,
        "email": "", "password": "",
        "callsign": "N8XLINK", "op_name": "Crosslink",
        "client_type": 0,            # 0 = Crosslink, 1 = Gateway, 2 = PC Only
        "band": "Crosslink",
        "description": "N8 Crosslink FRN-DMR-Zello",
        "country": "Germany", "city": "Minden - JO42",
        "net": "Test",
        "version": "2014003",
        "rx_timeout_ms": 1000,
        "text_messages": False,     # experimentell: Sprechername als FRN-Textnachricht
        "id_override": False,       # Operator (ON) je Durchgang per Neuanmeldung auf die Station setzen
        "id_override_desc": True,   # dabei auch die Beschreibung (DS) setzen
        "id_desc_template": "via {quelle} {detail}",
        "id_restore_s": 10,         # so lange nach dem Durchgang warten, dann eigener Operator
        "sysman_server": "sysman.freeradionetwork.eu",   # System Manager für „Passwort anfordern“
        "sysman_port": 10025,
        "rx_gain_db": 0.0, "tx_gain_db": 0.0,
    },
    "dmr": {
        "enabled": True,
        "host": "dmr.die-n8schicht.de", "port": 62031,
        "password": "passw0rd",
        "peer_id": 262000101,
        "callsign": "N8XLINK",
        "src_id": 2620001,          # Quell-ID für Sendungen ins DMR
        "use_db_id": False,         # FRN/Zello-Rufzeichen -> eigene DMR-ID, falls in der DB
        "slot": 2, "tg_rx": 262, "tg_tx": 262, "color_code": 1,
        "rx_freq": 0, "tx_freq": 0, "power": 1,
        "latitude": "52.2833", "longitude": "8.9167", "height": 0,
        "location": "Minden", "description": "N8 Crosslink",
        "url": "https://dmr.die-n8schicht.de",
        "options": "",              # RPTO, z. B. "TS2=262"
        "talker_alias": True,
        "send_dmra": False,         # DMRA-Pakete (nicht für HBlink4!)
        "rx_timeout_ms": 500,
        "rx_gain_db": 0.0, "tx_gain_db": 0.0,
    },
    "ids": {
        # FreeRadioID.net API – https://freeradioid.net/api-index.html
        "subscriber_csv_url": "https://freeradioid.net/api/subscriber_ids.csv",
        "subscriber_json_url": "https://freeradioid.net/api/subscriber_ids.json",
        "local_json_url": "https://freeradioid.net/api/local_subscriber_ids.json",
        "local_csv_url": "https://freeradioid.net/api/local_subscriber_ids.csv",
        "user_api_url": "https://freeradioid.net/api/dmr/user/?id={id}",
        "radioid_fallback_url": "https://radioid.net/static/user.csv",
        "talkgroups_url": "https://github.com/dhartmann1979/n8schicht/raw/refs/heads/main/talkgroup_ids.json",
        "avatars": True,
        "avatar_url": "https://freeradioid.net/api/idimg-{id}.png",
        "only_registered": True,      # nur FreeRadioID-registrierte IDs abfragen (andere haben kein Bild)
        "match_callsign": True,       # FRN-/Zello-Namen mit Rufzeichen -> FreeRadioID-Avatar
        "zello_avatar_url": "",       # optional, Platzhalter {username}
    },
    "zello": {
        "enabled": False,
        "server": "wss://zello.io/ws",
        "username": "", "password": "", "channel": "",
        "auth_mode": "token",        # token | key | none (Zello Work)
        "auth_token": "", "issuer": "", "private_key": "",
        "sample_rate": 16000, "bitrate": 16000, "packet_ms": 60,
        "send_text": True,
        "text_template": "🎙 {name} · {source}",
        "rx_timeout_ms": 1500,
        "rx_gain_db": 0.0, "tx_gain_db": 0.0,
    },
    "vocoder": {
        "vocoder_mode": "droidstar",   # droidstar | usb | ambeserver | none
        "droidstar_lib": "",           # leer = automatisch (/opt/n8crosslink/lib/libambe2.so)
        "usb_device": "/dev/ttyUSB0", "usb_baud": 460800, "usb_send_init": True,
        "ambeserver_host": "127.0.0.1", "ambeserver_port": 2460, "ambeserver_send_init": True,
        "vocoder_enc_gain_db": 0.0, "vocoder_dec_gain_db": 0.0,
        "vocoder_timeout_ms": 300, "vocoder_restart_s": 20,
    },
}

DEFAULT_USER = "n8schicht"
DEFAULT_PASSWORD = "n8schicht"

SECRET_KEYS = {("frn", "password"), ("dmr", "password"), ("zello", "password"),
               ("zello", "auth_token"), ("zello", "private_key")}


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    it = 200_000
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), it).hex()
    return f"pbkdf2_sha256${it}${salt}${h}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:  # noqa: BLE001
        return False


class Database:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (section TEXT, key TEXT, value TEXT, PRIMARY KEY(section, key));
        CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, pw_hash TEXT, role TEXT DEFAULT 'admin', created REAL);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS lastheard (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts_start REAL, ts_end REAL, duration REAL,
            source TEXT, name TEXT, callsign TEXT, detail TEXT, dmr_id INTEGER,
            targets TEXT, status TEXT);
        CREATE INDEX IF NOT EXISTS lh_ts ON lastheard(ts_start);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, level TEXT, text TEXT);
        CREATE TABLE IF NOT EXISTS dmr_users (id INTEGER PRIMARY KEY, callsign TEXT, name TEXT, city TEXT, country TEXT);
        CREATE INDEX IF NOT EXISTS du_cs ON dmr_users(callsign);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS frid_registered (id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS talkgroups (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE IF NOT EXISTS avatars (key TEXT PRIMARY KEY, has INTEGER, mime TEXT, data BLOB, url TEXT, fetched_at REAL);
        """)
        self.conn.commit()
        if not self.has_users():
            # Standard-Login beim ersten Start – im Adminportal ändern!
            self.set_user(DEFAULT_USER, DEFAULT_PASSWORD, "superadmin")

    # ------------------------------------------------------------ Einstellungen
    def load_config(self) -> dict:
        cfg = copy.deepcopy(DEFAULTS)
        with self.lock:
            for row in self.conn.execute("SELECT section, key, value FROM settings"):
                if row["section"] in cfg:
                    try:
                        cfg[row["section"]][row["key"]] = json.loads(row["value"])
                    except json.JSONDecodeError:
                        pass
        # 1.4.0: md380-emu entfällt – alte Einstellungen auf den DroidStar-Vocoder umstellen
        v = cfg["vocoder"]
        for k in [k for k in v if k.startswith("md380_")]:
            del v[k]
        if v.get("vocoder_mode") == "md380":
            v["vocoder_mode"] = "droidstar"
        return cfg

    def migrate_vocoder(self) -> bool:
        """Entfernt md380-emu-Einstellungen aus der Datenbank. True, wenn umgestellt wurde."""
        with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE section='vocoder' AND key='vocoder_mode'").fetchone()
            changed = bool(row and json.loads(row["value"]) == "md380")
            if changed:
                self.conn.execute("UPDATE settings SET value=? WHERE section='vocoder' AND key='vocoder_mode'",
                                  (json.dumps("droidstar"),))
            self.conn.execute("DELETE FROM settings WHERE section='vocoder' AND key LIKE 'md380\\_%' ESCAPE '\\'")
            self.conn.commit()
        return changed

    def save_section(self, section: str, values: dict) -> None:
        if section not in DEFAULTS:
            raise KeyError(section)
        with self.lock:
            for key, val in values.items():
                if key not in DEFAULTS[section]:
                    continue
                if (section, key) in SECRET_KEYS and val in ("", None, "********"):
                    continue  # leeres Feld = Passwort unverändert lassen
                self.conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?,?)",
                                  (section, key, json.dumps(val)))
            self.conn.commit()

    @staticmethod
    def public_config(cfg: dict) -> dict:
        out = copy.deepcopy(cfg)
        for sec, key in SECRET_KEYS:
            if out.get(sec, {}).get(key):
                out[sec][key] = "********"
        return out

    # ------------------------------------------------------------ Benutzer
    def has_users(self) -> bool:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0

    def set_user(self, username: str, password: str, role: str = "admin") -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?)",
                              (username, hash_password(password), role, time.time()))
            self.conn.commit()

    def delete_user(self, username: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM users WHERE username=?", (username,))
            self.conn.execute("DELETE FROM sessions WHERE username=?", (username,))
            self.conn.commit()

    def list_users(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT username, role, created FROM users ORDER BY username")]

    def user_role(self, username: str) -> str | None:
        with self.lock:
            r = self.conn.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
        return r[0] if r else None

    def reset(self, scope: str) -> None:
        """Zurücksetzen: 'history' (Last Heard, Statistik, Ereignisse), 'settings' (alle Einstellungen
        auf Standard), 'all' (alles inkl. Benutzer -> Standard-Login n8schicht/n8schicht, ID-Listen, Avatare)."""
        with self.lock:
            c = self.conn
            if scope in ("history", "all"):
                c.execute("DELETE FROM lastheard")
                c.execute("DELETE FROM events")
            if scope in ("settings", "all"):
                c.execute("DELETE FROM settings")
            if scope == "all":
                for t in ("users", "sessions", "dmr_users", "frid_registered", "talkgroups", "avatars", "meta"):
                    c.execute(f"DELETE FROM {t}")
            c.commit()
            if scope == "all":
                c.execute("VACUUM")
        if scope == "all":
            self.set_user(DEFAULT_USER, DEFAULT_PASSWORD, "superadmin")

    def check_login(self, username: str, password: str) -> bool:
        with self.lock:
            row = self.conn.execute("SELECT pw_hash FROM users WHERE username=?", (username,)).fetchone()
        return bool(row) and verify_password(password, row["pw_hash"])

    def new_session(self, username: str, hours: int = 12) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.conn.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            self.conn.execute("INSERT INTO sessions VALUES (?,?,?)", (token, username, time.time() + hours * 3600))
            self.conn.commit()
        return token

    def session_user(self, token: str | None) -> str | None:
        if not token:
            return None
        with self.lock:
            row = self.conn.execute("SELECT username, expires FROM sessions WHERE token=?", (token,)).fetchone()
        if row and row["expires"] > time.time():
            return row["username"]
        return None

    def end_session(self, token: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            self.conn.commit()

    # ------------------------------------------------------------ Last Heard
    def lh_insert(self, entry: dict) -> int:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO lastheard (ts_start, ts_end, duration, source, name, callsign, detail, dmr_id, targets, status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (entry["ts_start"], None, 0, entry["source"], entry.get("name"), entry.get("callsign"),
                 entry.get("detail"), entry.get("dmr_id"), json.dumps(entry.get("targets", [])),
                 entry.get("status", "live")))
            self.conn.commit()
            return cur.lastrowid

    def lh_update(self, row_id: int, **kw) -> None:
        if not kw:
            return
        if "targets" in kw:
            kw["targets"] = json.dumps(kw["targets"])
        cols = ", ".join(f"{k}=?" for k in kw)
        with self.lock:
            self.conn.execute(f"UPDATE lastheard SET {cols} WHERE id=?", (*kw.values(), row_id))
            self.conn.commit()

    def lh_recent(self, limit: int = 50) -> list[dict]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM lastheard ORDER BY ts_start DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["targets"] = json.loads(d["targets"] or "[]")
            out.append(d)
        return out

    def stats(self, since: float) -> dict:
        with self.lock:
            c = self.conn
            total = c.execute("SELECT COUNT(*), COALESCE(SUM(duration),0), COUNT(DISTINCT COALESCE(callsign,name))"
                              " FROM lastheard WHERE ts_start>=? AND status!='blocked'", (since,)).fetchone()
            by_src = {r[0]: {"talks": r[1], "airtime": r[2]} for r in c.execute(
                "SELECT source, COUNT(*), COALESCE(SUM(duration),0) FROM lastheard WHERE ts_start>=? AND status!='blocked'"
                " GROUP BY source", (since,))}
            top = [dict(name=r[0], callsign=r[1], talks=r[2], airtime=r[3], source=r[4], dmr_id=r[5]) for r in c.execute(
                "SELECT MAX(name), COALESCE(callsign,name) cs, COUNT(*), COALESCE(SUM(duration),0), MAX(source), MAX(dmr_id)"
                " FROM lastheard WHERE ts_start>=? AND status!='blocked' GROUP BY cs ORDER BY 4 DESC LIMIT 15", (since,))]
            hours = [0] * 24
            for r in c.execute("SELECT CAST(strftime('%H', ts_start, 'unixepoch', 'localtime') AS INT), COUNT(*)"
                               " FROM lastheard WHERE ts_start>=? GROUP BY 1", (since,)):
                if r[0] is not None:
                    hours[r[0]] = r[1]
            blocked = c.execute("SELECT COUNT(*) FROM lastheard WHERE ts_start>=? AND status='blocked'", (since,)).fetchone()[0]
        return {"talks": total[0], "airtime": total[1], "stations": total[2], "by_source": by_src,
                "top": top, "hours": hours, "blocked": blocked}

    def cleanup(self, keep_days: int) -> None:
        cutoff = time.time() - keep_days * 86400
        with self.lock:
            self.conn.execute("DELETE FROM lastheard WHERE ts_start < ?", (cutoff,))
            self.conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            self.conn.commit()

    # ------------------------------------------------------------ Ereignisse
    def event(self, level: str, text: str) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO events (ts, level, text) VALUES (?,?,?)", (time.time(), level, text))
            self.conn.commit()

    def events(self, limit: int = 100) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------ Meta
    def meta_get(self, key: str) -> str | None:
        with self.lock:
            r = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

    def meta_set(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
            self.conn.commit()

    def default_password_active(self) -> bool:
        with self.lock:
            row = self.conn.execute("SELECT pw_hash FROM users WHERE username=?", (DEFAULT_USER,)).fetchone()
        return bool(row) and verify_password(DEFAULT_PASSWORD, row["pw_hash"])

    # ------------------------------------------------------------ DMR-ID-Listen
    def userdb_replace(self, rows: list[tuple]) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM dmr_users")
            self.conn.executemany("INSERT OR REPLACE INTO dmr_users VALUES (?,?,?,?,?)", rows)
            self.conn.execute("INSERT OR REPLACE INTO meta VALUES ('users_updated', ?)", (str(time.time()),))
            self.conn.commit()

    def userdb_upsert(self, row: tuple) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO dmr_users VALUES (?,?,?,?,?)", row)
            self.conn.commit()

    def userdb_lookup(self, dmr_id: int) -> dict | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM dmr_users WHERE id=?", (dmr_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["frid"] = self.frid_is_registered(dmr_id)
        return d

    def userdb_by_callsign(self, callsign: str) -> dict | None:
        cs = callsign.upper()
        with self.lock:
            # bevorzugt eine bei FreeRadioID registrierte ID (hat ggf. einen Avatar)
            r = self.conn.execute("SELECT u.* FROM dmr_users u JOIN frid_registered f ON f.id=u.id "
                                  "WHERE u.callsign=? ORDER BY u.id LIMIT 1", (cs,)).fetchone()
            if not r:
                r = self.conn.execute("SELECT * FROM dmr_users WHERE callsign=? ORDER BY id LIMIT 1", (cs,)).fetchone()
        return dict(r) if r else None

    def frid_replace(self, rows: list[tuple]) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM frid_registered")
            self.conn.executemany("INSERT OR IGNORE INTO frid_registered VALUES (?)", [(r[0],) for r in rows])
            # registrierte Nutzer auch in die Gesamtliste übernehmen (falls dort neuer)
            self.conn.executemany("INSERT OR REPLACE INTO dmr_users VALUES (?,?,?,?,?)", rows)
            self.conn.execute("INSERT OR REPLACE INTO meta VALUES ('frid_updated', ?)", (str(time.time()),))
            self.conn.commit()

    def frid_add(self, dmr_id: int) -> None:
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO frid_registered VALUES (?)", (dmr_id,))
            self.conn.commit()

    def frid_is_registered(self, dmr_id: int) -> bool:
        with self.lock:
            return self.conn.execute("SELECT 1 FROM frid_registered WHERE id=?", (dmr_id,)).fetchone() is not None

    def talkgroups_replace(self, rows: list[tuple]) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM talkgroups")
            self.conn.executemany("INSERT OR REPLACE INTO talkgroups VALUES (?,?)", rows)
            self.conn.execute("INSERT OR REPLACE INTO meta VALUES ('tg_updated', ?)", (str(time.time()),))
            self.conn.commit()

    def tg_name(self, tg: int) -> str:
        with self.lock:
            r = self.conn.execute("SELECT name FROM talkgroups WHERE id=?", (tg,)).fetchone()
        return r[0] if r else ""

    def idlists_info(self) -> dict:
        with self.lock:
            c = self.conn
            n_u = c.execute("SELECT COUNT(*) FROM dmr_users").fetchone()[0]
            n_r = c.execute("SELECT COUNT(*) FROM frid_registered").fetchone()[0]
            n_t = c.execute("SELECT COUNT(*) FROM talkgroups").fetchone()[0]
        f = lambda k: float(self.meta_get(k) or 0) or None  # noqa: E731
        return {"users": n_u, "registered": n_r, "talkgroups": n_t, "users_updated": f("users_updated"),
                "frid_updated": f("frid_updated"), "tg_updated": f("tg_updated"),
                "users_source": self.meta_get("users_source") or ""}

    # Kompatibilität (Dashboard/DMR-Karte)
    def userdb_info(self) -> dict:
        i = self.idlists_info()
        return {"count": i["users"], "updated": i["users_updated"], "registered": i["registered"],
                "talkgroups": i["talkgroups"]}

    # ------------------------------------------------------------ Avatare
    def avatar_get(self, key: str) -> dict | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM avatars WHERE key=?", (key,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["data"] = bytes(d["data"]) if d["data"] is not None else None
        return d

    def avatar_put(self, key: str, has: bool, mime: str | None, data: bytes | None, url: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO avatars VALUES (?,?,?,?,?,?)",
                              (key, 1 if has else 0, mime, sqlite3.Binary(data) if data else None, url, time.time()))
            self.conn.commit()

    def avatar_delete(self, key: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM avatars WHERE key=?", (key,))
            self.conn.commit()

    def avatar_list(self) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT key, has, url, fetched_at FROM avatars ORDER BY key")]

    def avatar_stats(self) -> dict:
        with self.lock:
            rows = self.conn.execute("SELECT has, COUNT(*), COALESCE(SUM(LENGTH(data)),0) FROM avatars GROUP BY has").fetchall()
        d = {r[0]: (r[1], r[2]) for r in rows}
        last = self.meta_get("avatars_refreshed")
        return {"with_avatar": d.get(1, (0, 0))[0], "without": d.get(0, (0, 0))[0],
                "bytes": d.get(1, (0, 0))[1], "refreshed": float(last) if last else None}
