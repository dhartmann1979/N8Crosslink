"""FastAPI-Webserver: Dashboard, WebSocket-Livedaten, Login und Adminportal."""
from __future__ import annotations

import asyncio
import base64
import glob
import json
import os
import time
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import __version__
from .. import backup as bk
from ..db import DEFAULTS, Database

HERE = Path(__file__).parent
COOKIE = "n8x_session"
RANGES = {"today": None, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400, "90d": 90 * 86400}


def _since(rng: str) -> float:
    if rng == "today" or rng not in RANGES:
        lt = time.localtime()
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    return time.time() - RANGES[rng]


def create_app(bridge) -> FastAPI:  # noqa: ANN001, C901
    db: Database = bridge.db
    app = FastAPI(title="N8 Crosslink", version=__version__, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))

    # ------------------------------------------------------------ Auth
    def current_user(request: Request) -> str | None:
        return db.session_user(request.cookies.get(COOKIE))

    def require_admin(request: Request) -> str:
        u = current_user(request)
        if not u:
            raise HTTPException(401, "Bitte anmelden")
        return u

    def require_superadmin(request: Request, password: str) -> str:
        u = require_admin(request)
        if db.user_role(u) != "superadmin":
            raise HTTPException(403, "Nur für Superadmins")
        if not db.check_login(u, password):
            raise HTTPException(401, "Superadmin-Passwort falsch")
        return u

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        g = bridge.cfg["general"]
        return env.get_template("index.html").render(title=g.get("title", "N8 Crosslink"),
                                                     server_name=g.get("server_name", ""), version=__version__)

    ICONS = HERE / "static" / "icons"
    LONG = {"Cache-Control": "public, max-age=604800"}

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response((ICONS / "favicon.ico").read_bytes(), media_type="image/x-icon", headers=LONG)

    @app.get("/apple-touch-icon.png")
    @app.get("/apple-touch-icon-precomposed.png")
    async def apple_icon() -> Response:
        return Response((ICONS / "apple-touch-icon.png").read_bytes(), media_type="image/png", headers=LONG)

    @app.get("/site.webmanifest")
    @app.get("/manifest.json")
    async def manifest() -> Response:
        m = json.loads((ICONS / "site.webmanifest").read_text())
        m["name"] = bridge.cfg["general"].get("title", m["name"])
        return Response(json.dumps(m, ensure_ascii=False), media_type="application/manifest+json")

    @app.get("/api/me")
    async def me(request: Request) -> dict:
        u = current_user(request)
        return {"user": u, "setup_required": not db.has_users(), "version": __version__,
                "default_password": bool(u) and db.default_password_active()}

    @app.post("/api/setup")
    async def setup(data: dict = Body(...)) -> JSONResponse:
        if db.has_users():
            raise HTTPException(403, "Superadmin existiert bereits")
        user, pw = str(data.get("username", "")).strip(), str(data.get("password", ""))
        if len(user) < 3 or len(pw) < 8:
            raise HTTPException(400, "Benutzername min. 3, Passwort min. 8 Zeichen")
        db.set_user(user, pw, "superadmin")
        resp = JSONResponse({"ok": True, "user": user})
        resp.set_cookie(COOKIE, db.new_session(user), httponly=True, samesite="lax", max_age=12 * 3600)
        return resp

    @app.post("/api/login")
    async def login(data: dict = Body(...)) -> JSONResponse:
        user, pw = str(data.get("username", "")), str(data.get("password", ""))
        await asyncio.sleep(0.3)  # Bremse gegen Durchprobieren
        if not db.check_login(user, pw):
            raise HTTPException(401, "Benutzername oder Passwort falsch")
        resp = JSONResponse({"ok": True, "user": user})
        resp.set_cookie(COOKIE, db.new_session(user), httponly=True, samesite="lax", max_age=12 * 3600)
        return resp

    @app.post("/api/logout")
    async def logout(request: Request) -> JSONResponse:
        tok = request.cookies.get(COOKIE)
        if tok:
            db.end_session(tok)
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        return resp

    # ------------------------------------------------------------ öffentliche Daten
    @app.get("/api/state")
    async def state() -> dict:
        return bridge.router.snapshot()

    @app.get("/api/lastheard")
    async def lastheard(limit: int = 50) -> list:
        return db.lh_recent(min(max(limit, 1), 500))

    @app.get("/api/stats")
    async def stats(range: str = "today") -> dict:  # noqa: A002
        return db.stats(_since(range))

    @app.get("/api/info")
    async def info() -> dict:
        g = bridge.cfg["general"]
        return {"title": g.get("title"), "server_name": g.get("server_name"), "announcement": g.get("announcement"),
                "links": g.get("links", []), "version": __version__, "routes": bridge.cfg["routes"]}

    @app.get("/api/avatar/{source}/{key}")
    async def avatar(source: str, key: str) -> Response:
        if source not in ("dmr", "frn", "zello"):
            raise HTTPException(404)
        res = await bridge.avatars.get(source, key)
        if not res:
            return Response(status_code=404, headers={"Cache-Control": "public, max-age=3600"})
        mime, data = res
        return Response(data, media_type=mime or "image/png", headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/events")
    async def public_events(limit: int = 20) -> list:
        return db.events(min(max(limit, 1), 30))

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        q: asyncio.Queue = asyncio.Queue()
        bridge.router.listeners.add(q)
        try:
            await sock.send_text(json.dumps(bridge.router.snapshot()))
            while True:
                msg = await q.get()
                await sock.send_text(json.dumps(msg, default=str))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            bridge.router.listeners.discard(q)

    @app.websocket("/ws/audio")
    async def ws_audio(sock: WebSocket) -> None:
        """Mithören: 8 kHz / 16 Bit mono PCM der aktiven Durchsage – nur für angemeldete Admins."""
        user = db.session_user(sock.cookies.get(COOKIE))
        if not user:
            await sock.close(code=4401)
            return
        await sock.accept()
        q: asyncio.Queue = asyncio.Queue()
        bridge.router.audio_listeners.add(q)
        try:
            a = bridge.router.active
            if a:
                await sock.send_text(json.dumps({"type": "start", "source": a.source.key, "talker": a.talker.to_dict()}))
            while True:
                item = await q.get()
                if isinstance(item, dict):
                    await sock.send_text(json.dumps(item))
                    continue
                chunk = [item]                      # bis zu 3 Rahmen (60 ms) bündeln
                while len(chunk) < 3 and not q.empty() and not isinstance(q._queue[0], dict):  # noqa: SLF001
                    chunk.append(q.get_nowait())
                await sock.send_bytes(b"".join(chunk))
                if db.session_user(sock.cookies.get(COOKIE)) is None:
                    break                           # abgemeldet -> Mithören beenden
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            bridge.router.audio_listeners.discard(q)
            try:
                await sock.close()
            except RuntimeError:
                pass

    # ------------------------------------------------------------ Admin
    @app.get("/api/admin/config")
    async def get_config(_: str = Depends(require_admin)) -> dict:
        return {"config": Database.public_config(db.load_config()), "defaults": Database.public_config(DEFAULTS)}

    @app.post("/api/admin/config")
    async def save_config(data: dict = Body(...), _: str = Depends(require_admin)) -> dict:
        for section, values in data.items():
            if section in DEFAULTS and isinstance(values, dict):
                db.save_section(section, _coerce(section, values))
        new = db.load_config()
        # Routing, Texte und Pegel greifen sofort, der Rest nach Neustart
        bridge.cfg["routes"].update(new["routes"])
        bridge.cfg["general"].update({k: new["general"][k] for k in
                                      ("hang_time_ms", "tot_s", "jitter_ms", "announcement", "links", "title",
                                       "server_name", "keep_days")})
        bridge.router.notify()
        restart = any(s in data for s in ("frn", "dmr", "zello", "vocoder"))
        return {"ok": True, "restart_required": restart}

    @app.post("/api/admin/restart")
    async def restart(_: str = Depends(require_admin)) -> dict:
        asyncio.create_task(bridge.restart())
        return {"ok": True}

    @app.post("/api/admin/service-restart")
    async def service_restart(_: str = Depends(require_admin)) -> dict:
        async def _go() -> None:
            await asyncio.sleep(0.5)
            if await bridge.system.sudo_ok():
                ok, _out = await bridge.system.unit_action("n8crosslink.service", "restart")
                if ok:
                    return
            os._exit(3)  # Fallback: systemd startet den Dienst neu (Restart=always)
        asyncio.create_task(_go())
        return {"ok": True}

    # ---- Systemsteuerung (sudo, nur freigegebene Befehle)
    @app.get("/api/admin/system")
    async def system_status(_: str = Depends(require_admin)) -> dict:
        return await bridge.system.status()

    @app.post("/api/admin/system/unit")
    async def system_unit(data: dict = Body(...), user: str = Depends(require_admin)) -> dict:
        unit, action = str(data.get("unit", "")), str(data.get("action", ""))
        ok, out = await bridge.system.unit_action(unit, action)
        bridge.router.event("info" if ok else "warn", f"System: {action} {unit} durch {user} – {'ok' if ok else out[:120]}")
        return {"ok": ok, "message": out[:500]}

    @app.post("/api/admin/system/reboot")
    async def system_reboot(user: str = Depends(require_admin)) -> dict:
        bridge.router.event("warn", f"System-Neustart angefordert von {user}")
        ok, out = await bridge.system.reboot()
        return {"ok": ok, "message": out[:300]}

    @app.post("/api/admin/system/fix-perms")
    async def system_fix_perms(user: str = Depends(require_admin)) -> dict:
        ok, out = await bridge.system.fix_perms()
        bridge.router.event("info" if ok else "warn", f"Berechtigungsprüfung durch {user}: {'ok' if ok else 'Fehler'}")
        return {"ok": ok, "message": out}

    # ---- ID-Listen & Avatare
    @app.get("/api/admin/ids")
    async def ids_info(_: str = Depends(require_admin)) -> dict:
        return {"lists": db.idlists_info(), "avatars": db.avatar_stats(),
                "uploads": [r["key"].split(":", 2)[2] for r in db.avatar_list() if r["key"].startswith("upload:zello:")],
                "busy": bridge.idlists.lock.locked(), "avatars_busy": bridge.avatars.lock.locked()}

    @app.post("/api/admin/ids/update")
    async def ids_update(_: str = Depends(require_admin)) -> dict:
        if bridge.idlists.lock.locked():
            return {"ok": False, "message": "Aktualisierung läuft bereits"}
        asyncio.create_task(bridge.idlists.update_all())
        return {"ok": True, "message": "ID-Listen werden geladen …"}

    @app.post("/api/admin/avatars/refresh")
    async def avatars_refresh(_: str = Depends(require_admin)) -> dict:
        if bridge.avatars.lock.locked():
            return {"ok": False, "message": "Aktualisierung läuft bereits"}
        asyncio.create_task(bridge.avatars.refresh_all())
        return {"ok": True, "message": "Avatare werden neu geladen …"}

    @app.post("/api/admin/avatars/upload")
    async def avatar_upload(data: dict = Body(...), _: str = Depends(require_admin)) -> dict:
        user = str(data.get("username", "")).strip()
        try:
            raw = base64.b64decode(str(data.get("image", "")).split(",")[-1])
        except ValueError:
            raw = b""
        if not user or len(raw) > 5 * 1024 * 1024 or not bridge.avatars.upload("zello", user, raw):
            raise HTTPException(400, "Bitte Zello-Benutzername und ein PNG/JPEG/WebP/GIF (max. 5 MB) angeben")
        return {"ok": True}

    @app.delete("/api/admin/avatars/upload/{user}")
    async def avatar_upload_delete(user: str, _: str = Depends(require_admin)) -> dict:
        db.avatar_delete(f"upload:zello:{user.lower()}")
        return {"ok": True}

    # ---- Backup / Wiederherstellung / Zurücksetzen (nur Superadmin, Passwort erneut)
    @app.post("/api/admin/backup")
    async def make_backup(request: Request, data: dict = Body(...)) -> Response:
        pw = str(data.get("password", ""))
        user = require_superadmin(request, pw)
        data_dir = os.path.dirname(os.path.abspath(db.path))
        name, blob = await asyncio.to_thread(bk.create, db, data_dir, pw, user)
        bridge.router.event("info", f"Verschlüsseltes Backup erstellt von {user} ({len(blob) // 1024} KB)")
        return Response(blob, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

    def _blob(data: dict) -> bytes:
        try:
            return base64.b64decode(str(data.get("file", "")).split(",")[-1])
        except ValueError:
            raise HTTPException(400, "Datei unlesbar") from None

    @app.post("/api/admin/restore/inspect")
    async def restore_inspect(request: Request, data: dict = Body(...)) -> dict:
        require_admin(request)
        try:
            manifest, _ = await asyncio.to_thread(bk.inspect, _blob(data), str(data.get("password", "")))
        except bk.BackupError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True, "manifest": manifest}

    @app.post("/api/admin/restore")
    async def restore(request: Request, data: dict = Body(...)) -> dict:
        u = require_admin(request)
        if db.user_role(u) != "superadmin":
            raise HTTPException(403, "Nur für Superadmins")
        try:
            manifest, dbbytes = await asyncio.to_thread(bk.inspect, _blob(data), str(data.get("password", "")))
        except bk.BackupError as e:
            raise HTTPException(400, str(e)) from None
        await bridge.stop()
        await asyncio.to_thread(bk.restore_into, db, dbbytes)
        bridge.router.event("info", f"Backup vom {time.strftime('%d.%m.%Y %H:%M', time.localtime(manifest.get('created', 0)))} "
                                    f"(Version {manifest.get('version')}) eingespielt von {u}")
        await bridge.restart()
        return {"ok": True, "manifest": manifest, "relogin": True}

    @app.post("/api/admin/reset")
    async def reset(request: Request, data: dict = Body(...)) -> dict:
        scope = str(data.get("scope", ""))
        if scope not in ("history", "settings", "all"):
            raise HTTPException(400, "Unbekannter Bereich")
        user = require_superadmin(request, str(data.get("password", "")))
        await bridge.stop()
        await asyncio.to_thread(db.reset, scope)
        bridge.router.event("warn", {"history": "Last Heard, Statistik und Ereignisse gelöscht",
                                     "settings": "Alle Einstellungen auf Standard zurückgesetzt",
                                     "all": "Komplett zurückgesetzt (Standard-Login n8schicht/n8schicht)"}[scope] + f" von {user}")
        await bridge.restart()
        return {"ok": True, "relogin": scope == "all"}

    # ---- FRN: Passwort anfordern (Registrierung beim System Manager)
    last_frn_req = {"t": 0.0}

    @app.post("/api/admin/frn/request-password")
    async def frn_request_password(data: dict = Body(...), user: str = Depends(require_admin)) -> dict:
        from ..frn import request_password
        if time.time() - last_frn_req["t"] < 60:
            return {"ok": False, "title": "Bitte warten",
                    "message": f"Eine Anforderung ist erst vor {int(time.time() - last_frn_req['t'])} s gelaufen – bitte eine Minute warten."}
        v = dict(db.load_config()["frn"])
        v.update({k: str(val) for k, val in data.items() if k in v and val not in (None, "")})
        last_frn_req["t"] = time.time()
        ok, title, msg = await request_password(v)
        bridge.router.event("info" if ok else "warn", f"FRN-Passwort angefordert von {user} für {v.get('callsign')}: {title}")
        return {"ok": ok, "title": title, "message": msg}

    @app.post("/api/admin/frn/identity-test")
    async def frn_identity_test(user: str = Depends(require_admin)) -> dict:
        p = bridge.router.ports.get("frn")
        if p is None or not getattr(p, "enabled", False):
            return {"ok": False, "title": "FRN aus", "message": "FRN ist nicht aktiviert."}
        ok, title, msg = await p.test_identity()
        bridge.router.event("info" if ok else "warn", f"FRN Operator-Wechsel getestet von {user}: {title}")
        return {"ok": ok, "title": title, "message": msg}

    @app.post("/api/admin/announce/preview")
    async def announce_preview(data: dict = Body(...), _: str = Depends(require_admin)) -> Response:
        from .. import announce
        if not announce.available():
            raise HTTPException(503, "espeak-ng ist nicht installiert – sudo /opt/n8crosslink/update.sh ausführen")
        cfg = dict(bridge.cfg["general"])
        cfg.update({k: v for k, v in data.items() if k.startswith("announce_") and v not in (None, "")})
        cs = str(data.get("callsign") or "DO1TEST")[:20]
        text = announce.speech_text(cs, cs, cfg)
        pcm = await asyncio.get_running_loop().run_in_executor(None, announce.synth, text, cfg)
        if not pcm:
            raise HTTPException(500, "Ansage konnte nicht erzeugt werden")
        import io as _io
        import wave as _wave
        buf = _io.BytesIO()
        with _wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(pcm)  # noqa: E702
        return Response(buf.getvalue(), media_type="audio/wav", headers={"Cache-Control": "no-store"})

    # ---- Software-Vocoder
    @app.post("/api/admin/vocoder/build")
    async def vocoder_build(user: str = Depends(require_admin)) -> dict:
        ok, out = await bridge.system.build_vocoder()
        bridge.router.event("info" if ok else "warn", f"DroidStar-Vocoder gebaut durch {user}: {'ok' if ok else 'Fehler'}")
        return {"ok": ok, "message": out}

    # ---- Updates
    @app.get("/api/admin/update")
    async def update_state(_: str = Depends(require_admin)) -> dict:
        return {**bridge.updater.state, "systemd": bridge.updater.systemd_ready() or await bridge.system.sudo_ok(),
                "log": bridge.updater.log_tail()}

    @app.post("/api/admin/update/check")
    async def update_check(_: str = Depends(require_admin)) -> dict:
        return await bridge.updater.check()

    @app.post("/api/admin/update/now")
    async def update_now(user: str = Depends(require_admin)) -> dict:
        return await bridge.updater.request_update(user, bridge.system)

    @app.post("/api/admin/vocoder-test")
    async def vocoder_test(_: str = Depends(require_admin)) -> dict:
        v = bridge.vocoder
        if v is None or not v.running:
            return {"ok": False, "message": "Vocoder ist nicht gestartet (DMR deaktiviert?)"}
        from ..vocoder import tone_test
        r = await tone_test(v)
        msg = (f"1-kHz-Ton über {r['frames']} Rahmen: {r['ms']} ms je Rahmen, Ergebnis {r['hz']} Hz"
               if r["frames"] else "Keine Antwort vom Vocoder")
        return {"ok": r["ok"], "ms": r["ms"], "status": v.status(), "message": msg}

    @app.get("/api/admin/serial-ports")
    async def serial_ports(_: str = Depends(require_admin)) -> list:
        ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/serial/by-id/*"))
        return ports

    @app.get("/api/admin/events")
    async def events(limit: int = 200, _: str = Depends(require_admin)) -> list:
        return db.events(min(limit, 1000))

    @app.get("/api/admin/users")
    async def users(_: str = Depends(require_admin)) -> list:
        return db.list_users()

    @app.post("/api/admin/users")
    async def add_user(data: dict = Body(...), _: str = Depends(require_admin)) -> dict:
        user, pw = str(data.get("username", "")).strip(), str(data.get("password", ""))
        if len(user) < 3 or len(pw) < 8:
            raise HTTPException(400, "Benutzername min. 3, Passwort min. 8 Zeichen")
        db.set_user(user, pw, data.get("role", "admin"))
        return {"ok": True}

    @app.delete("/api/admin/users/{name}")
    async def del_user(name: str, me_: str = Depends(require_admin)) -> dict:
        if name == me_:
            raise HTTPException(400, "Eigenes Konto kann nicht gelöscht werden")
        db.delete_user(name)
        return {"ok": True}

    @app.get("/api/admin/export")
    async def export(_: str = Depends(require_admin)) -> Response:
        cfg = Database.public_config(db.load_config())
        return Response(json.dumps(cfg, indent=2, ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=n8crosslink-config.json"})

    @app.post("/api/admin/import")
    async def import_cfg(data: dict = Body(...), _: str = Depends(require_admin)) -> dict:
        for section, values in data.items():
            if section in DEFAULTS and isinstance(values, dict):
                db.save_section(section, _coerce(section, values))
        return {"ok": True, "restart_required": True}

    return app


def _coerce(section: str, values: dict) -> dict:
    """Formularwerte auf die Typen der Standardwerte bringen."""
    out = {}
    for k, v in values.items():
        if k not in DEFAULTS[section]:
            continue
        d = DEFAULTS[section][k]
        try:
            if isinstance(d, bool):
                out[k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "ja", "yes")
            elif isinstance(d, int):
                out[k] = int(float(v)) if v not in ("", None) else d
            elif isinstance(d, float):
                out[k] = float(v) if v not in ("", None) else d
            elif isinstance(d, list):
                out[k] = v if isinstance(v, list) else json.loads(v)
            else:
                out[k] = "" if v is None else str(v)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return out
