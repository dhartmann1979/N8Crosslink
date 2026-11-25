"""FastAPI-Webserver: Dashboard, WebSocket-Livedaten, Login und Adminportal."""
from __future__ import annotations

import asyncio
import re
import base64
import glob
import json
import os
import time
from pathlib import Path

from . import n8_security as _sec
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


NET_LABELS = (("frn", "FRN"), ("dmr", "DMR"), ("zello", "Zello"))


def nets_label(cfg: dict) -> str:
    """Nur die eingeschalteten Netze, z. B. „FRN · DMR“ – für Titel, Untertitel und Fußzeile."""
    on = [lbl for key, lbl in NET_LABELS if (cfg.get(key) or {}).get("enabled")]
    return " · ".join(on) if on else "keine Netze aktiv"


def create_app(bridge) -> FastAPI:  # noqa: ANN001, C901
    db: Database = bridge.db
    app = FastAPI(title="N8 Crosslink", version=__version__,
                  **{"docs_url": None, "redoc_url": None, "openapi_url": None, **_sec.FASTAPI_KWARGS})

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):  # noqa: ANN001, ANN202
        resp = await call_next(request)
        _sec.headers(resp, https=_sec.is_https(request))
        return resp
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]))

    # ------------------------------------------------------------ Auth
    def current_user(request: Request) -> str | None:
        u = db.session_user(request.cookies.get(COOKIE))
        return u or None

    def require_human(request: Request) -> str:      # nur angemeldete Menschen (früher: nicht das Portal) – heute wie require_admin
        return require_admin(request)

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
    async def index(request: Request) -> str:
        from .public import text as _public_text
        g = bridge.cfg["general"]
        sn = g.get("server_name", "") or ""
        if not db.session_user(request.cookies.get(COOKIE)):
            sn = _public_text(sn)          # ohne Anmeldung keine IPs/Ports, auch nicht im Servernamen
        return env.get_template("index.html").render(title=g.get("title", "N8 Crosslink"), nets=nets_label(db.load_config()),
                                                     server_name=sn, version=__version__,
                                                     theme=_theme(g.get("theme")))

    # ------------------------------------------------------------ N8 Theme 2 (gleiche Farbtechnik wie die anderen N8-Seiten)
    @app.get("/api/theme")
    async def theme_get() -> dict:
        return {"theme": _theme(bridge.cfg["general"].get("theme"))}

    @app.post("/api/admin/theme")
    async def theme_save(data: dict = Body(...), _: str = Depends(require_admin)) -> dict:
        t = _theme(data.get("theme"))
        db.save_section("general", {"theme": t})
        bridge.cfg["general"]["theme"] = t
        return {"ok": True, "theme": t}

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
    # Ohne Anmeldung keine IPs und Ports (public.scrub); angemeldete Admins sehen alles.
    from . import public

    def sees_all(request: Request) -> bool:
        return bool(db.session_user(request.cookies.get(COOKIE)))

    @app.get("/api/state")
    async def state(request: Request) -> dict:
        snap = bridge.router.snapshot()
        return snap if sees_all(request) else public.scrub(snap)

    @app.get("/api/lastheard")
    async def lastheard(request: Request, limit: int = 50) -> list:
        rows = db.lh_recent(min(max(limit, 1), 500))
        return rows if sees_all(request) else public.scrub(rows)

    @app.get("/api/stats")
    async def stats(range: str = "today") -> dict:  # noqa: A002
        return db.stats(_since(range))

    @app.get("/api/info")
    async def info(request: Request) -> dict:
        g = bridge.cfg["general"]
        cfg = db.load_config()
        sn = g.get("server_name") or ""
        return {"title": g.get("title"), "server_name": sn if sees_all(request) else public.text(sn), "announcement": g.get("announcement"),
                "nets": [k for k, _ in NET_LABELS if (cfg.get(k) or {}).get("enabled")], "nets_label": nets_label(cfg),
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
    async def public_events(request: Request, limit: int = 20) -> list:
        ev = db.events(min(max(limit, 1), 30))
        return ev if sees_all(request) else public.scrub(ev)

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        # angemeldet? – sonst ohne IPs und Ports. Nach An-/Abmelden baut die Seite die Verbindung neu auf.
        full = bool(db.session_user(sock.cookies.get(COOKIE)))
        view = (lambda m: m) if full else public.scrub
        await sock.accept()
        q: asyncio.Queue = asyncio.Queue()
        bridge.router.listeners.add(q)
        try:
            await sock.send_text(json.dumps(view(bridge.router.snapshot()), default=str))
            while True:
                msg = await q.get()
                await sock.send_text(json.dumps(view(msg), default=str))
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
        # Allgemein wirkt komplett sofort (auch Sprachansage) – nur Web-Adresse/-Port brauchen einen Dienst-Neustart
        bridge.cfg["general"].update({k: v for k, v in new["general"].items() if k not in ("web_host", "web_port")})
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
    # ---- Domains & HTTPS (Let's Encrypt) – nur angemeldete Admins
    def _resolve(domain: str) -> list[str]:
        import socket
        try:
            return sorted({a[4][0] for a in socket.getaddrinfo(domain, None)})
        except OSError:
            return []

    def _nginx_ports() -> tuple[str, str, str]:
        """Web-Port von N8 Crosslink (aus der Datenbank, auch vor dem Neustart) und die Ports von nginx."""
        c = db.load_config()
        h = c.get("https") or {}
        return (str(int(c["general"].get("web_port") or 8080)), str(int(h.get("http_port") or 80)), str(int(h.get("https_port") or 443)))

    @app.get("/api/admin/domains")
    async def domains_get(_: str = Depends(require_human)) -> dict:
        st = await bridge.system.certs("status", *_nginx_ports(), timeout=60)
        for s_ in st.get("sites") or []:
            s_["dns"] = await asyncio.to_thread(_resolve, s_["domain"])
        st["settings"] = db.load_config().get("https") or {}
        st["web_host"] = bridge.cfg["general"].get("web_host", "0.0.0.0")
        return st

    @app.post("/api/admin/domains")
    async def domains_add(data: dict = Body(...), user: str = Depends(require_human)) -> dict:
        domain = str(data.get("domain") or "").strip().lower().rstrip(".")
        email = str(data.get("email") or "").strip()
        if not re.fullmatch(bridge.system.DOMAIN_RE, domain) or len(domain) > 253:
            raise HTTPException(400, "Domain bitte wie crosslink.example.org angeben")
        if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", email):
            raise HTTPException(400, "Bitte eine gültige E-Mail-Adresse für Let's Encrypt angeben")
        staging = bool(data.get("staging"))
        db.save_section("https", {"email": email, "staging": staging})
        args = ["add", domain, email, *_nginx_ports()] + (["staging"] if staging else [])
        r = await bridge.system.certs(*args, timeout=420)
        r["dns"] = await asyncio.to_thread(_resolve, domain)
        bridge.router.event("info" if r.get("ok") else "warn", f"Domain {domain} von {user}: {r.get('message', '')[:160]}")
        return r

    @app.post("/api/admin/domains/deps")
    async def domains_deps(user: str = Depends(require_human)) -> dict:
        r = await bridge.system.certs("deps", timeout=900)
        bridge.router.event("info" if r.get("ok") else "warn", f"nginx/certbot installieren ({user}): {r.get('message', '')[:160]}")
        return r

    @app.post("/api/admin/domains/{domain}/renew")
    async def domains_renew(domain: str, user: str = Depends(require_human)) -> dict:
        if not re.fullmatch(bridge.system.DOMAIN_RE, domain):
            raise HTTPException(400, "Ungültige Domain")
        r = await bridge.system.certs("renew", domain, timeout=420)
        bridge.router.event("info" if r.get("ok") else "warn", f"Zertifikat {domain} erneuern ({user}): {r.get('message', '')[:160]}")
        return r

    @app.delete("/api/admin/domains/{domain}")
    async def domains_remove(domain: str, user: str = Depends(require_human)) -> dict:
        if not re.fullmatch(bridge.system.DOMAIN_RE, domain):
            raise HTTPException(400, "Ungültige Domain")
        r = await bridge.system.certs("remove", domain, timeout=120)
        bridge.router.event("info" if r.get("ok") else "warn", f"Domain {domain} entfernt ({user}): {r.get('message', '')[:160]}")
        return r

    # ---- 🔌 Ports: alle Ports an einer Stelle (wie „HTTPS & web“ bei HBlink4)
    PORT_KEYS = {  # Abschnitt.Schlüssel -> (kleinster Wert, Neustart: "service" = Dienst, "bridge" = Brücke, "nginx")
        "general.web_port": (1, "service"), "https.http_port": (1, "nginx"), "https.https_port": (1, "nginx"),
        "frn.port": (1, "bridge"), "frn.backup_port": (1, "bridge"), "frn.sysman_port": (1, "bridge"),
        "dmr.port": (1, "bridge"), "dmr.local_port": (0, "bridge"), "vocoder.ambeserver_port": (1, "bridge"),
    }

    @app.get("/api/admin/ports")
    async def ports_get(_: str = Depends(require_human)) -> dict:
        c = db.load_config()
        vals = {k: c[k.split(".")[0]].get(k.split(".")[1]) for k in PORT_KEYS}
        vals["general.web_host"] = c["general"].get("web_host", "0.0.0.0")
        return {"values": vals, "running": {"web_host": bridge.cfg["general"].get("web_host"), "web_port": bridge.cfg["general"].get("web_port")},
                "zello_server": c["zello"].get("server", ""), "frn_server": c["frn"].get("server", ""), "dmr_host": c["dmr"].get("host", ""),
                "vocoder_mode": c["vocoder"].get("vocoder_mode", ""), "ambeserver_host": c["vocoder"].get("ambeserver_host", "")}

    @app.post("/api/admin/ports")
    async def ports_save(data: dict = Body(...), user: str = Depends(require_human)) -> dict:
        import ipaddress
        c = db.load_config()
        changes: dict = {}
        for k, (lo, _) in PORT_KEYS.items():
            if k not in data:
                continue
            try:
                v = int(data[k])
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k}: bitte eine Zahl") from None
            if not lo <= v <= 65535:
                raise HTTPException(400, f"{k}: {lo}–65535")
            sec, key = k.split(".")
            if c[sec].get(key) != v:
                changes[k] = v
        host = str(data.get("general.web_host", c["general"].get("web_host", "0.0.0.0"))).strip()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            raise HTTPException(400, "Web-Adresse: eine IP-Adresse, z. B. 0.0.0.0 (alle), 127.0.0.1 (nur lokal) oder :: (alle, IPv6)") from None
        if host != c["general"].get("web_host", "0.0.0.0"):
            changes["general.web_host"] = host
        merged = {k: changes.get(k, c[k.split(".")[0]].get(k.split(".")[1])) for k in ("general.web_port", "https.http_port", "https.https_port")}
        if len({merged["general.web_port"], merged["https.http_port"], merged["https.https_port"]}) < 3:
            raise HTTPException(400, "Web-Port, HTTP-Port und HTTPS-Port (nginx) müssen verschieden sein")
        if not changes:
            return {"ok": True, "changed": [], "message": "Nichts geändert"}
        by_sec: dict = {}
        for k, v in changes.items():
            sec, key = k.split(".")
            by_sec.setdefault(sec, {})[key] = v
        for sec, vals in by_sec.items():
            db.save_section(sec, vals)
        kinds = {PORT_KEYS.get(k, (0, "service"))[1] for k in changes}
        res = {"ok": True, "changed": sorted(changes), "restart_bridge": "bridge" in kinds, "restart_service": "service" in kinds}
        if kinds & {"nginx", "service"}:      # Domains auf die neuen Ports umschreiben (nur wenn es welche gibt)
            st = await bridge.system.certs("status", *_nginx_ports(), timeout=60)
            if st.get("ok") and st.get("sites"):
                res["nginx"] = await bridge.system.certs("ports", *_nginx_ports(), timeout=180)
        bridge.router.event("info", f"Ports geändert von {user}: " + ", ".join(f"{k}={v}" for k, v in sorted(changes.items()))[:240])
        return res

    @app.post("/api/admin/ports/apply")
    async def ports_apply(user: str = Depends(require_human)) -> dict:
        r = await bridge.system.certs("ports", *_nginx_ports(), timeout=180)
        bridge.router.event("info" if r.get("ok") else "warn", f"nginx-Ports angewandt ({user}): {r.get('message', '')[:160]}")
        return r

    @app.post("/api/admin/domains/local-only")
    async def domains_local_only(data: dict = Body(...), user: str = Depends(require_human)) -> dict:
        """Webinterface nur noch über die HTTPS-Domain (bindet auf 127.0.0.1) – oder wieder an allen Schnittstellen."""
        host = "127.0.0.1" if data.get("on") else "0.0.0.0"
        db.save_section("general", {"web_host": host})
        bridge.cfg["general"]["web_host"] = host
        bridge.router.event("info", f"Web-Adresse auf {host} gestellt von {user} – Dienst startet neu")
        asyncio.get_running_loop().call_later(1.0, lambda: asyncio.ensure_future(bridge.system.unit_action("n8crosslink.service", "restart")))
        return {"ok": True, "web_host": host}

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

    @app.get("/api/admin/system/perms")
    async def system_perms(_: str = Depends(require_admin)) -> dict:
        return await bridge.system.check_perms()

    @app.post("/api/admin/system/fix-perms")
    async def system_fix_perms(user: str = Depends(require_admin)) -> dict:
        ok, out = await bridge.system.fix_perms()
        bridge.router.event("info" if ok else "warn", f"Berechtigungen geprüft und korrigiert durch {user}: {'alles in Ordnung' if ok else 'Fehler bleiben'}")
        res = {"ok": ok, "message": out}
        if bridge.system.config().get("check_perms"):
            res["check"] = await bridge.system.check_perms()
        return res

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

    # ---- FRN: öffentliches Fehlerprotokoll von freeradionetwork.de (Grund für abgelehnte Anmeldungen)
    @app.get("/api/admin/frn/errorlog")
    async def frn_errorlog(force: bool = False, _: str = Depends(require_admin)) -> dict:
        from .. import frn_errorlog as el
        s = db.load_config()["frn"]
        cs, hosts = [s.get("callsign", "")], [s.get("server", ""), s.get("backup_server", "")]
        entries, err = await el.fetch(force=force)
        mine = el.relevant(entries, cs, hosts)
        seen = {(e["ts"], e["kind"], e["id"]) for e in mine}
        return {"ok": not err, "error": err, "page": el.PAGE, "fetched": el._cache["t"], "total": len(entries),
                "span": [entries[0]["ts"], entries[-1]["ts"]] if entries else None,
                "scope": {"callsigns": [c for c in cs if c], "servers": [h for h in hosts if h]},
                "mine": el.summarize(mine), "others": el.summarize([e for e in entries if (e["ts"], e["kind"], e["id"]) not in seen])[:15]}

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

    # ---- N8schicht-Vocoder: Klang-Einstellungen (live) und Probehören
    @app.get("/api/admin/vocoder/params")
    async def vocoder_params(_: str = Depends(require_admin)) -> dict:
        from ..vocoder import PROFILES, effective_options, params_for_ui
        c = db.load_config()["vocoder"]
        v = bridge.vocoder
        return {"mode": c.get("vocoder_mode"), "profile": c.get("n8vocoder_profile", "n8schicht"),
                "profiles": list(PROFILES), "params": params_for_ui(c), "effective": effective_options(c),
                "active": bool(v and v.mode == "n8vocoder" and v.online),
                "bad": getattr(getattr(v, "codec", None), "bad_options", [])}

    @app.post("/api/admin/vocoder/options")
    async def vocoder_options(data: dict = Body(...), user: str = Depends(require_admin)) -> dict:
        from ..vocoder import PROFILES, effective_options
        prof = str(data.get("profile") or "n8schicht")
        if prof not in PROFILES:
            raise HTTPException(400, "Unbekanntes Profil")
        own = data.get("options") or {}
        own = {side: {str(k): float(val) for k, val in (own.get(side) or {}).items()} for side in ("enc", "dec", "post")}
        db.save_section("vocoder", {"n8vocoder_profile": prof, "n8vocoder_options": own})
        bridge.cfg["vocoder"].update({"n8vocoder_profile": prof, "n8vocoder_options": own})
        eff = effective_options(bridge.cfg["vocoder"])
        v = bridge.vocoder
        bad = await v.set_options(eff) if v and v.mode == "n8vocoder" else []
        bridge.router.event("info", f"Vocoder-Klang geändert von {user} (Profil {prof})")
        return {"ok": not bad, "bad": bad, "live": bool(v and v.mode == "n8vocoder"), "effective": eff}

    @app.post("/api/admin/vocoder/preview")
    async def vocoder_preview(data: dict = Body(...), _: str = Depends(require_admin)) -> dict:
        from .. import preview
        try:
            return await preview.run(data, bridge.cfg["vocoder"])
        except preview.PreviewError as e:
            raise HTTPException(400, str(e)) from e

    # ---- Software-Vocoder
    @app.post("/api/admin/vocoder/build")
    async def vocoder_build(user: str = Depends(require_admin)) -> dict:
        ok, out = await bridge.system.build_vocoder()
        bridge.router.event("info" if ok else "warn", f"N8schicht-Vocoder gebaut durch {user}: {'ok' if ok else 'Fehler'}")
        return {"ok": ok, "message": out}

    # ---- Updates
    @app.get("/api/admin/update")
    async def update_state(_: str = Depends(require_admin)) -> dict:
        res = None
        try:
            with open(os.path.join(bridge.updater.data_dir, "update.result"), encoding="utf-8") as f:
                res = json.load(f)
        except (OSError, ValueError):
            pass
        return {**bridge.updater.state, "systemd": bridge.updater.systemd_ready() or await bridge.system.sudo_ok(),
                "log": bridge.updater.log_tail(), "result": res}

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


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_PRESETS = ("n8", "ocean", "aurora", "ember", "violet", "graphite", "daylight")


def _theme(t) -> dict:  # noqa: ANN001
    """Theme-Objekt von N8 Theme 2 prüfen: nur bekannte Schlüssel, Farben als #rrggbb, Zahlen im Bereich."""
    t = t if isinstance(t, dict) else {}
    out = {"preset": t.get("preset") if t.get("preset") in _PRESETS else "n8"}
    for k in ("accent", "accent2", "background", "glow1", "glow2", "glow3", "text", "panel"):
        v = str(t.get(k) or "")
        out[k] = v.lower() if _HEX.match(v) else ""

    def num(k: str, lo: float, hi: float, d: float) -> float:
        try:
            return max(lo, min(hi, float(t.get(k, d))))
        except (TypeError, ValueError):
            return d
    out.update(glow=num("glow", 0, 150, 100), glass=num("glass", 0, 100, 50), radius=num("radius", 0, 28, 22),
               blur=t.get("blur") not in (False, "false", 0))
    return out


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
            elif isinstance(d, dict):
                out[k] = v if isinstance(v, dict) else json.loads(v)
            else:
                out[k] = "" if v is None else str(v)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return out
