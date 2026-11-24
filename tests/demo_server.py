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


async def main(port: int) -> None:
    from aiohttp import web
    loop = asyncio.get_running_loop()
    voc = sim.FakeVocoder()
    await loop.create_datagram_endpoint(lambda: voc, local_addr=("127.0.0.1", sim.VOC_PORT))
    hb = sim.FakeHB()
    await loop.create_datagram_endpoint(lambda: hb, local_addr=("127.0.0.1", sim.HB_PORT))
    frn = sim.FakeFRN()
    frn.CLIENTS = FRN_ROOM
    await asyncio.start_server(frn.handle, "127.0.0.1", sim.FRN_PORT)
    zel = sim.FakeZello()
    app = web.Application()
    app.router.add_get("/ws", zel.handler)
    r = web.AppRunner(app)
    await r.setup()
    await web.TCPSite(r, "127.0.0.1", sim.ZELLO_PORT).start()

    db = Database(os.path.join(tempfile.mkdtemp(), "demo.db"))
    db.save_section("general", {"title": "N8 Crosslink", "server_name": "crosslink.die-n8schicht.de", "hang_time_ms": 400})
    db.save_section("frn", {"server": "127.0.0.1", "port": sim.FRN_PORT, "email": "a@b.c", "password": "x", "net": "Nachtschicht"})
    db.save_section("dmr", {"host": "127.0.0.1", "port": sim.HB_PORT, "password": sim.FakeHB.PASS, "peer_id": 262000101,
                            "src_id": 2620001, "tg_rx": 262, "tg_tx": 262, "userdb_url": "", "userdb_fallback_url": ""})
    db.save_section("zello", {"enabled": True, "server": f"ws://127.0.0.1:{sim.ZELLO_PORT}/ws", "channel": "N8schicht",
                              "username": "n8crosslink", "password": "pw", "auth_mode": "none"})
    db.save_section("vocoder", {"vocoder_mode": "ambeserver", "ambeserver_port": sim.VOC_PORT})
    db.userdb_replace([(2621234, "DO1TEST", "Tobias", "Minden", "Germany"), (2625001, "DL9NS", "Sven", "Herford", "Germany")])
    db.set_user("demo", "demo12345", "superadmin")
    bridge = Bridge(db)
    await bridge.start()
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
