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
                            "net": "Nachtschicht", "sysman_server": "127.0.0.1", "sysman_port": 20025})
    db.save_section("dmr", {"host": "127.0.0.1", "port": sim.HB_PORT, "password": sim.FakeHB.PASS, "peer_id": 262000101,
                            "src_id": 2620001, "tg_rx": 262, "tg_tx": 262, "userdb_url": "", "userdb_fallback_url": ""})
    db.save_section("zello", {"enabled": True, "server": f"ws://127.0.0.1:{sim.ZELLO_PORT}/ws", "channel": "N8schicht",
                              "username": "n8crosslink", "password": "pw", "auth_mode": "none"})
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
    open(os.path.join(os.path.dirname(db.path), "system.json"), "w").write(_j.dumps({"sudo": False, "systemctl": "/usr/bin/systemctl", "reboot": True, "fix_perms": True, "units": [
        {"unit": "n8crosslink.service", "label": "N8 Crosslink", "actions": ["restart"]},
        {"unit": "md380-emu.service", "label": "md380-emu (Vocoder)", "actions": ["start", "stop", "restart", "enable", "disable"]},
        {"unit": "svxlink.service", "label": "svxlink (alt)", "actions": ["start", "stop", "restart", "enable", "disable"]}]}))
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
