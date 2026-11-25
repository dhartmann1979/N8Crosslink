#!/usr/bin/env python3
"""Demo: Simulierte Netze + echtes Dashboard (für Screenshots und Oberflächentests).

  python3 tests/demo_server.py [--port 8098]

Superadmin der Demo: demo / demo12345
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sim_e2e as sim  # noqa: E402
import uvicorn  # noqa: E402

from n8crosslink.app import Bridge  # noqa: E402
from n8crosslink.db import Database  # noqa: E402
from n8crosslink.web.server import create_app  # noqa: E402

FRN_ROOM = [
    "<S>0</S><M>0</M><NN>Germany</NN><CT>Minden - JO42</CT><BC>PC Only</BC><CL>2</CL><ON>DL1ABC, Hans</ON><ID>11</ID><DS></DS>",
    "<S>0</S><M>0</M><NN>Germany</NN><CT>Bielefeld - JO42</CT><BC>446.03125FM CTC88.5</BC><CL>1</CL><ON>DO7MKS, Markus</ON><ID>14</ID><DS></DS>",
    "<S>0</S><M>0</M><NN>Germany</NN><CT>Hannover - JO42</CT><BC>PC Only</BC><CL>2</CL><ON>DB4NN, Nina</ON><ID>15</ID><DS></DS>",
    "<S>0</S><M>1</M><NN>Austria</NN><CT>Wien - JN88</CT><BC>PC Only</BC><CL>2</CL><ON>OE3XYZ, Franz</ON><ID>16</ID><DS></DS>",
    "<S>0</S><M>0</M><NN>Germany</NN><CT>Minden - JO42</CT><BC>Crosslink</BC><CL>0</CL><ON>N8XLINK, Crosslink</ON><ID>12</ID><DS></DS>",
]


COLORS = {"2621234": ((10, 132, 255), (94, 92, 230)), "2625001": ((48, 209, 88), (10, 132, 255)),
          "2625101": ((255, 159, 10), (191, 90, 242)), "dj_nachtfalke": ((255, 159, 10), (255, 69, 58))}


async def demo_avatar(request):  # noqa: ANN001, ANN201
    """Generierte Beispiel-Avatare (keine echten Fotos) für Demo und Screenshots."""
    from aiohttp import web
    from PIL import Image, ImageDraw
    import io
    name = request.match_info["name"].split(".")[0]
    if name not in COLORS:
        return web.Response(status=404)
    c1, c2 = COLORS[name]
    im = Image.new("RGB", (256, 256))
    d = ImageDraw.Draw(im)
    for y in range(256):
        t = y / 255
        d.line([(0, y), (256, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
    d.ellipse((88, 48, 168, 128), fill=(245, 247, 251))
    d.pieslice((48, 136, 208, 296), 180, 360, fill=(245, 247, 251))
    b = io.BytesIO()
    im.save(b, "PNG")
    return web.Response(body=b.getvalue(), content_type="image/png")


async def main(port: int) -> None:
    from aiohttp import web
    loop = asyncio.get_running_loop()
    voc = sim.FakeVocoder()
    await loop.create_datagram_endpoint(lambda: voc, local_addr=("127.0.0.1", sim.VOC_PORT))
    hb = sim.FakeHB()
    await loop.create_datagram_endpoint(lambda: hb, local_addr=("127.0.0.1", sim.HB_PORT))
    frn = sim.FakeFRN()
    frn.CLIENTS = FRN_ROOM
    sm = sim.FakeSysman()
    await asyncio.start_server(sm.handle, "127.0.0.1", 20025)
    await asyncio.start_server(frn.handle, "127.0.0.1", sim.FRN_PORT)
    zel = sim.FakeZello()
    app = web.Application()
    app.router.add_get("/ws", zel.handler)
    app.router.add_get("/demo-av/{name}", demo_avatar)
    sim.add_fake_web(app)
    r = web.AppRunner(app)
    await r.setup()
    await web.TCPSite(r, "127.0.0.1", sim.ZELLO_PORT).start()

    db = Database(os.path.join(tempfile.mkdtemp(), "demo.db"))
    db.save_section("general", {"title": "N8 Crosslink", "server_name": "crosslink.die-n8schicht.de", "hang_time_ms": 400})
    db.save_section("frn", {"server": "127.0.0.1", "port": sim.FRN_PORT, "email": "n8xlink@die-n8schicht.de", "password": "x",
                            "net": "Krabbelgruppe", "sysman_server": "127.0.0.1", "sysman_port": 20025})
    db.save_section("dmr", {"host": "127.0.0.1", "port": sim.HB_PORT, "password": sim.FakeHB.PASS, "peer_id": 262000101,
                            "src_id": 2620001, "tg_rx": 262, "tg_tx": 262, "userdb_url": "", "userdb_fallback_url": ""})
    db.save_section("zello", {"enabled": True, "server": f"ws://127.0.0.1:{sim.ZELLO_PORT}/ws", "channel": "N8schicht",
                              "username": "n8crosslink", "password": "pw", "auth_mode": "none"})
    from n8crosslink.vocoder import find_n8vocoder_lib
    if find_n8vocoder_lib():   # N8X_AMBE_LIB=/pfad/libn8vocoder.so -> echter N8schicht-Vocoder
        db.save_section("vocoder", {"vocoder_mode": "n8vocoder"})
    else:
        db.save_section("vocoder", {"vocoder_mode": "ambeserver", "ambeserver_port": sim.VOC_PORT})
    base = f"http://127.0.0.1:{sim.ZELLO_PORT}"
    db.save_section("ids", {"subscriber_csv_url": f"{base}/ids/subscriber_ids.csv", "subscriber_json_url": "",
                            "local_json_url": f"{base}/ids/local.json", "local_csv_url": "", "user_api_url": "",
                            "radioid_fallback_url": "", "talkgroups_url": f"{base}/ids/tg.json",
                            "avatar_url": f"{base}/demo-av/{{id}}", "only_registered": False,
                            "zello_avatar_url": f"{base}/demo-av/{{username}}"})
    db.set_user("demo", "demo12345", "superadmin")
    bridge = Bridge(db)
    await bridge.start()
    await bridge.idlists.update_all()
    db.userdb_upsert((2625001, "DL9NS", "Sven", "Herford", "Germany"))
    db.userdb_upsert((2625101, "DB4NN", "Nina", "Hannover", "Germany"))
    db.frid_add(2625001); db.frid_add(2625101)
    sim.FakeWeb.version = "1.2.0"
    bridge.updater.raw_url = lambda path: f"{base}/raw/{path}"
    await bridge.updater.check()
    import json as _j
    # öffentliches FRN-Fehlerprotokoll (Demo ohne Internet): Beispiel mit den typischen Meldungen
    from n8crosslink import frn_errorlog as _el
    import time as _t
    _c = db.load_config()["frn"]["callsign"]
    _ago = lambda m: _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(_t.time() - m * 60))
    _demo_log = "\n".join([f"{_ago(52 - i * 6)} ERROR - Client [{_c}, Crosslink], DE/DE, Request CC - wrong FRN password - Hint: Perform an FRN password request and use the assigned FRN password !" for i in range(7)]
                           + [f"{_ago(40)} ERROR - Server [127.0.0.1:{sim.FRN_PORT}], DE, Request SC - multiple connections at the same time with the same connection data are not permitted",
                              f"{_ago(12)} ERROR - Server [uhf3radionet.ddns.net:10024], GR, Request SC - not listening on specified port - Hint: Check the firewall settings and port forwarding settings, if applicable !",
                              f"{_ago(3)} ERROR - Client [DL9XYZ, Gateway], DE/DE, Request CC - wrong FRN password - Hint: Perform an FRN password request and use the assigned FRN password !"])
    _el._get = lambda timeout: _j.dumps({"log": _demo_log})
    open(os.path.join(os.path.dirname(db.path), "system.json"), "w").write(_j.dumps({"sudo": True, "systemctl": "/usr/bin/systemctl", "reboot": True, "fix_perms": True, "build_vocoder": True, "certs": True, "check_perms": True, "units": [
        {"unit": "n8crosslink.service", "label": "N8 Crosslink", "actions": ["start", "stop", "restart", "enable", "disable"]},
        {"unit": "n8crosslink-update.path", "label": "Update-Auslöser („Update jetzt“)", "actions": ["start", "stop", "restart", "enable", "disable"]},
        {"unit": "n8crosslink-update.service", "label": "Update-Dienst", "actions": ["start"], "hidden": True},
        {"unit": "svxlink.service", "label": "svxlink (alt)", "actions": ["start", "stop", "restart", "enable", "disable"]}]}))
    # Demo ohne systemd: Zustände der Dienste vorspielen (Start/Stopp/Autostart wirken im Speicher)
    _units = {"n8crosslink.service": ["active", "enabled"], "n8crosslink-update.path": ["active", "enabled"],
              "n8crosslink-update.service": ["inactive", "static"], "svxlink.service": ["inactive", "disabled"]}

    async def _fake_run(*cmd, timeout=60):
        if len(cmd) >= 3 and cmd[-2] in ("is-active", "is-enabled"):
            st = _units.get(cmd[-1], ["inactive", "disabled"])
            return 0, st[0] if cmd[-2] == "is-active" else st[1]
        if cmd and cmd[0] == "sudo":
            act, unit = cmd[-2], cmd[-1]
            if unit in _units:
                _units[unit][0] = {"start": "active", "restart": "active", "stop": "inactive"}.get(act, _units[unit][0])
                _units[unit][1] = {"enable": "enabled", "disable": "disabled"}.get(act, _units[unit][1])
            return 0, ""
        return 1, ""
    bridge.system._run = _fake_run
    # Abstürze (Demo): Absturz-Wächter eingerichtet, ein paar typische Befunde
    from n8crosslink.app import SERVICES
    from n8crosslink.n8_crash import CrashWatch
    ddir = os.path.dirname(db.path)
    bridge.crash = CrashWatch(ddir, app="N8 Crosslink", unit="n8crosslink.service", services=SERVICES)
    bridge.crash.install()
    open(os.path.join(ddir, "crashwatch.json"), "w").write(_j.dumps({"version": 1, "time": _t.time(), "units": [
        {"unit": "n8crosslink.service", "label": "N8 Crosslink", "restart": "always"}]}))
    _demo_crashes = [
        (_t.time() - 26 * 3600, "watchdog", "Datenbank ← ID-Listen", "systemd-Watchdog: keine Rückmeldung mehr – der Prozess hing und wurde beendet (SIGABRT) – "
         "Event-Loop steht seit 64 s (hängt in Datenbank ← ID-Listen)", "systemd"),
        (_t.time() - 5 * 3600, "keepalive", "N8 Crosslink", "Keep-Alive: Zello verbunden – Zello: getrennt – Kanal offline (seit 5 min) – neu gestartet", "keepalive"),
        (_t.time() - 3 * 3600, "stall", "Datenbank ← DMR", "Event-Loop 19 s blockiert – Webinterface und Verbindungen standen still", "app"),
        (_t.time() - 40 * 60, "helper", "Vocoder", "Vocoder-Prozess abgestürzt: Signal 11 (SIGSEGV) – wird neu gestartet", "app"),
    ]
    for ts, kind, svc, reason, src in _demo_crashes:
        cid = _t.strftime("%Y%m%d-%H%M%S", _t.localtime(ts)) + "-" + kind[:2] + "01"
        open(os.path.join(ddir, "crash", cid + ".log"), "w").write(
            f"N8 Crosslink – Befund {cid}\nZeit:     {_t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime(ts))}\nDienst:   n8crosslink.service\n"
            f"Teil:     {svc}\nUrsache:  {reason}\nQuelle:   {src}\n\n=== Python-Stack ===\n"
            '  File "/opt/n8crosslink/n8crosslink/db.py", line 430 in userdb_lookup\n'
            '  File "/opt/n8crosslink/n8crosslink/dmr/port.py", line 290 in _talker\n  File "/opt/n8crosslink/n8crosslink/dmr/port.py", line 244 in _on_dmrd\n'
            "\n=== Journal des Dienstes (Auszug) ===\n2026-11-25T03:12:40+0100 crosslink systemd[1]: n8crosslink.service: Watchdog timeout (limit 1min)!\n")
        with open(os.path.join(ddir, "crashes.jsonl"), "a") as f:
            f.write(_j.dumps({"id": cid, "time": ts, "unit": "n8crosslink.service", "app": "N8 Crosslink", "service": svc, "kind": kind,
                              "reason": reason, "source": src, "restarted": True, "log": cid + ".log"}, ensure_ascii=False) + "\n")
    server = uvicorn.Server(uvicorn.Config(create_app(bridge), host="127.0.0.1", port=port, log_level="warning"))

    async def scenario() -> None:
        await asyncio.sleep(3)
        while True:
            await frn.talk(1, 3.0); await asyncio.sleep(2)
            await hb.send_stream(2621234, 262, 2.5, "DO1TEST Tobias"); await asyncio.sleep(2)
            await zel.talk("dj_nachtfalke", 2.5); await asyncio.sleep(2)
            await frn.talk(3, 2.2); await asyncio.sleep(2)
            await hb.send_stream(2625001, 262, 2.0, "DL9NS Sven"); await asyncio.sleep(random.uniform(2, 4))
    asyncio.create_task(scenario())
    await server.serve()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8098)
    asyncio.run(main(ap.parse_args().port))
