"""FastAPI-Webserver: Dashboard, WebSocket-Livedaten, Login und Adminportal."""
from __future__ import annotations

import asyncio
import base64
import glob
import json
import os
import time
from pathlib import Path

import numpy as np
from fastapi import Body, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import __version__
from ..db import DEFAULTS, Database
from ..dmr.burst import AMBE_SILENCE

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

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        g = bridge.cfg["general"]
        return env.get_template("index.html").render(title=g.get("title", "N8 Crosslink"),
                                                     server_name=g.get("server_name", ""), version=__version__)

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response((HERE / "static" / "n8crosslink-icon.svg").read_bytes(), media_type="image/svg+xml")

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
        t0 = time.perf_counter()
        tone = (np.sin(2 * np.pi * 1000 * np.arange(160) / 8000) * 9000).astype("<i2").tobytes()
        amb = await v.encode(tone, timeout=1.5)
        pcm = await v.decode(amb or AMBE_SILENCE, timeout=1.5)
        ms = (time.perf_counter() - t0) * 1000
        ok = amb is not None and pcm is not None
        return {"ok": ok, "ms": round(ms, 1), "status": v.status(),
                "message": f"Encode+Decode in {ms:.0f} ms" if ok else "Keine Antwort vom Vocoder"}

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
