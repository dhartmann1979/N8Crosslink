#!/usr/bin/env python3
"""Ende-zu-Ende-Simulation: Fake-FRN-Server, Fake-HBlink (HomeBrew), Fake-Zello und Fake-AMBE3000.

Prüft alle sechs Richtungen, Sprechernamen (Talker Alias, Zello-Text), Start/Stop-Erkennung
und den Schleifenschutz. Aufruf:  python3 tests/sim_e2e.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from n8crosslink.app import Bridge  # noqa: E402
from n8crosslink.frn import parse_tags  # noqa: E402
from n8crosslink.audio import gsm  # noqa: E402
from n8crosslink.audio.dsp import level_dbfs  # noqa: E402
from n8crosslink.audio.opus import OpusEncoder  # noqa: E402
from n8crosslink.db import Database  # noqa: E402
from n8crosslink.dmr import burst as B  # noqa: E402
from n8crosslink.dmr import fec  # noqa: E402

FRN_PORT, HB_PORT, VOC_PORT, ZELLO_PORT = 20024, 62099, 2479, 8799
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    RESULTS.append((name, ok, info))
    print(("  ✅ " if ok else "  ❌ ") + name + (f"  ({info})" if info else ""))


def tone(n: int, f: float = 700, amp: int = 9000, start: int = 0) -> bytes:
    t = (np.arange(n) + start) / 8000
    return (np.sin(2 * np.pi * f * t) * amp).astype("<i2").tobytes()


# ---------------------------------------------------------------------------- Fake-Vocoder
class FakeVocoder(asyncio.DatagramProtocol):
    def connection_made(self, tr):  # noqa: ANN001
        self.tr = tr
        self.enc = self.dec = 0

    def datagram_received(self, d: bytes, addr) -> None:  # noqa: ANN001
        ptype = d[3]
        if ptype == 0x00:
            f = d[4]
            if f == 0x33:
                self.tr.sendto(bytes([0x61, 0, 1, 0, 0x39]), addr)
            elif f == 0x09:
                self.tr.sendto(bytes([0x61, 0, 2, 0, 0x09, 0]), addr)
            elif f == 0x30:
                p = b"\x30AMBE3000R\x00"
                self.tr.sendto(struct.pack(">BHB", 0x61, len(p), 0) + p, addr)
            elif f == 0x31:
                p = b"\x31V120.E100.XXXX.C106.G514.R009.B0010411.C0020208\x00"
                self.tr.sendto(struct.pack(">BHB", 0x61, len(p), 0) + p, addr)
        elif ptype == 0x01:      # AMBE -> PCM
            self.dec += 1
            pcm = np.frombuffer(tone(160, 440), dtype="<i2").astype(">i2").tobytes()
            p = bytes([0x00, 160]) + pcm
            self.tr.sendto(struct.pack(">BHB", 0x61, len(p), 2) + p, addr)
        elif ptype == 0x02:      # PCM -> AMBE
            self.enc += 1
            p = bytes([0x01, 72]) + B.AMBE_SILENCE
            self.tr.sendto(struct.pack(">BHB", 0x61, len(p), 1) + p, addr)


# ---------------------------------------------------------------------------- Fake-HBlink
class FakeHB(asyncio.DatagramProtocol):
    PASS = "testpass"
    tone: list = []

    def __init__(self) -> None:
        self.peer = None
        self.connected = False
        self.salt = os.urandom(4)
        self.rx: list[bytes] = []
        self.options = b""

    def connection_made(self, tr):  # noqa: ANN001
        self.tr = tr

    def datagram_received(self, d: bytes, addr) -> None:  # noqa: ANN001
        self.peer = addr
        if d[:4] == b"RPTL":
            self.tr.sendto(b"RPTACK" + self.salt, addr)
        elif d[:4] == b"RPTK":
            ok = d[8:40] == hashlib.sha256(self.salt + self.PASS.encode()).digest()
            self.tr.sendto((b"RPTACK" if ok else b"MSTNAK") + d[4:8], addr)
        elif d[:5] == b"RPTCL":
            self.connected = False
        elif d[:4] == b"RPTC":
            self.cfg_len = len(d)
            self.tr.sendto(b"RPTACK" + d[4:8], addr)
            self.connected = True
        elif d[:4] == b"RPTO":
            self.options = d[8:]
            self.tr.sendto(b"RPTACK" + d[4:8], addr)
        elif d[:7] == b"RPTPING":
            self.tr.sendto(b"MSTPONG" + d[7:11], addr)
        elif d[:4] == b"DMRD":
            self.rx.append(d)

    async def send_stream(self, src: int, tg: int, seconds: float, alias: str, slot: int = 2) -> None:
        sid = os.urandom(4)
        lc = B.make_lc(src, tg)
        lcf = fec.embedded_lc_encode(lc)
        taf = [fec.embedded_lc_encode(b) for b in B.talker_alias_blocks(alias)]
        sb = 0x80 if slot == 2 else 0

        def pkt(seq: int, bits: int, payload: bytes) -> bytes:
            return (b"DMRD" + bytes([seq & 0xFF]) + src.to_bytes(3, "big") + tg.to_bytes(3, "big")
                    + (311000).to_bytes(4, "big") + bytes([sb | bits]) + sid + payload + b"\x00\x00")
        seq = 0
        for _ in range(2):
            self.tr.sendto(pkt(seq, 0x21, B.build_lc_burst(lc, 1, False)), self.peer); seq += 1
            await asyncio.sleep(0.06)
        n = sf = 0
        t_end = time.time() + seconds
        k = 0
        while time.time() < t_end:
            if self.tone:      # echte AMBE+2-Rahmen (1-kHz-Ton, mit DroidStar kodiert)
                amb = tuple(self.tone[(k + i) % len(self.tone)] for i in range(3)); k += 3
            else:
                amb = (B.AMBE_SILENCE,) * 3
            if n == 0:
                p = pkt(seq, 0x10, B.build_voice_burst(amb, 0, 1, None))
            else:
                frags = taf[(sf // 2) % len(taf)] if sf % 2 == 1 else lcf
                p = pkt(seq, n, B.build_voice_burst(amb, n, 1, frags[n - 1] if n <= 4 else None))
            self.tr.sendto(p, self.peer)
            seq += 1
            n += 1
            if n == 6:
                n, sf = 0, sf + 1
            await asyncio.sleep(0.06)
        self.tr.sendto(pkt(seq, 0x22, B.build_lc_burst(lc, 1, True)), self.peer)


def analyse_dmr(pkts: list[bytes]) -> dict:
    """Wertet die von der Bridge gesendeten DMRD-Pakete aus."""
    out = {"headers": 0, "voice": 0, "terms": 0, "src": set(), "dst": set(), "ta": None, "streams": set(),
           "lc_ok": False, "slot": set()}
    frags: dict[int, list[int]] = {}
    ta = B.TalkerAliasDecoder()
    for d in pkts:
        bits = d[15]
        ftype, dt = (bits >> 4) & 3, bits & 0x0F
        out["src"].add(int.from_bytes(d[5:8], "big")); out["dst"].add(int.from_bytes(d[8:11], "big"))
        out["streams"].add(d[16:20]); out["slot"].add(2 if bits & 0x80 else 1)
        pl = d[20:53]
        if ftype == 2 and dt == 1:
            out["headers"] += 1
            out["lc_ok"] = fec.full_lc_decode(pl, fec.VOICE_LC_HEADER_MASK) is not None
        elif ftype == 2 and dt == 2:
            out["terms"] += 1
        else:
            out["voice"] += 1
            n = 0 if ftype == 1 else dt
            if 1 <= n <= 4:
                frags[n] = B.extract_emb_fragment(pl)
                if n == 4 and len(frags) == 4:
                    lc = fec.embedded_lc_decode([frags[i] for i in (1, 2, 3, 4)])
                    if lc and 4 <= (lc[0] & 0x3F) <= 7:
                        r = ta.add_lc(lc)
                        if r and not r.endswith("…"):
                            out["ta"] = r
                    frags = {}
    return out


# ---------------------------------------------------------------------------- Fake-FRN
class FakeFRN:
    CLIENTS = ["<S>0</S><M>0</M><NN>Germany</NN><CT>Minden - JO42</CT><BC>PC Only</BC><CL>2</CL><ON>DL1ABC, Hans</ON><ID>11</ID><DS></DS>",
               "<S>0</S><M>0</M><NN>Germany</NN><CT>Bielefeld - JO42</CT><BC>Crosslink</BC><CL>0</CL><ON>N8XLINK, Crosslink</ON><ID>12</ID><DS></DS>"]

    def __init__(self) -> None:
        self.writer = None
        self.login = ""
        self.tx_req = self.tx_pkts = self.rx0 = 0
        self.tx_levels: list[float] = []
        self.texts: list[str] = []
        self.sent_list = False
        self.dec = None
        self.logins: list[str] = []
        self.reject_foreign = False
        self.tx_by_on: dict[str, int] = {}
        self.cur_on = ""

    def drop(self) -> None:
        if self.writer:
            self.writer.close()
        self.sent_list = False

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.writer = writer
        self.connects = getattr(self, "connects", 0) + 1
        self.login = (await reader.readline()).decode("latin-1")
        self.logins.append(self.login)
        on = parse_tags(self.login).get("ON", "")
        if self.reject_foreign and not on.startswith("N8XLINK"):
            writer.write(b"2014003\r\n<SV>2014x</SV><AL>WRONG</AL>\r\n")
            await writer.drain()
            writer.close()
            return
        self.cur_on = on
        writer.write(b"2014003\r\n<SV>2014x</SV><AL>OK</AL><MT>Testraum</MT>\r\n")
        try:
            while True:
                line = (await reader.readline()).decode(errors="replace").strip()
                if not line and reader.at_eof():
                    break
                if line == "P":
                    if not self.sent_list:
                        self.sent_list = True
                        body = f"{len(self.CLIENTS)}\r\n" + "\r\n".join(self.CLIENTS) + "\r\n"
                        writer.write(bytes([3, 0, 0]) + body.encode())
                    else:
                        await asyncio.sleep(0.05)
                        writer.write(b"\x00")
                elif line == "TX0":
                    self.tx_req += 1
                    self.dec = gsm.GsmDecoder()
                    writer.write(bytes([1, 0, 2]))
                elif line == "TX1":
                    data = await reader.readexactly(325)
                    self.tx_pkts += 1
                    self.tx_by_on[self.cur_on] = self.tx_by_on.get(self.cur_on, 0) + 1
                    self.tx_levels.append(level_dbfs(self.dec.decode_packet(data)))
                elif line == "RX0":
                    self.rx0 += 1
                elif line.startswith("TM:"):
                    self.texts.append(line)
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass

    async def talk(self, index: int, seconds: float) -> None:
        enc = gsm.GsmEncoder()
        n = int(seconds / 0.2)
        for i in range(n):
            pcm = tone(1600, 600, start=i * 1600)
            self.writer.write(bytes([2, 0, index]) + enc.encode_packet(pcm))
            await self.writer.drain()
            await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------- Fake-System-Manager
class FakeSysman:
    """Antwortet auf IG: beim ersten Mal mit OK, danach mit NU (Rufzeichen vergeben)."""
    def __init__(self) -> None:
        self.lines: list[str] = []

    async def handle(self, reader, writer) -> None:  # noqa: ANN001
        line = (await reader.readline()).decode(errors="replace").strip()
        self.lines.append(line)
        writer.write(b"OK\r\n" if len(self.lines) == 1 else b"NU\r\n")
        await writer.drain()
        writer.close()


# ---------------------------------------------------------------------------- Fake-Zello
class FakeZello:
    def __init__(self) -> None:
        self.ws = None
        self.logon = None
        self.texts: list[str] = []
        self.streams: list[dict] = []
        self.cur = None

    async def handler(self, request):  # noqa: ANN001, ANN201
        from aiohttp import WSMsgType, web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.ws = ws
        sid = 500
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                m = json.loads(msg.data)
                c = m.get("command")
                if c == "logon":
                    self.logon = m
                    await ws.send_str(json.dumps({"seq": m["seq"], "success": True, "refresh_token": "rt"}))
                    await ws.send_str(json.dumps({"command": "on_channel_status", "channel": m["channels"][0],
                                                  "status": "online", "users_online": 3, "texting_supported": True}))
                elif c == "send_text_message":
                    self.texts.append(m["text"])
                    await ws.send_str(json.dumps({"seq": m["seq"], "success": True}))
                elif c == "start_stream":
                    sid += 1
                    self.cur = {"id": sid, "packets": 0, "stopped": False, "header": m["codec_header"]}
                    self.streams.append(self.cur)
                    await ws.send_str(json.dumps({"seq": m["seq"], "success": True, "stream_id": sid}))
                elif c == "stop_stream":
                    if self.cur:
                        self.cur["stopped"] = True
            elif msg.type == WSMsgType.BINARY:
                if self.cur and struct.unpack(">I", msg.data[1:5])[0] == self.cur["id"]:
                    self.cur["packets"] += 1
        return ws

    async def talk(self, user: str, seconds: float) -> None:
        enc = OpusEncoder(16000)
        await self.ws.send_str(json.dumps({"command": "on_stream_start", "type": "audio", "codec": "opus",
                                           "codec_header": "gD4BPA==", "packet_duration": 60, "stream_id": 9001,
                                           "channel": "N8test", "from": user}))
        for i in range(int(seconds / 0.06)):
            t = (np.arange(960) + i * 960) / 16000
            pcm = (np.sin(2 * np.pi * 500 * t) * 9000).astype("<i2").tobytes()
            await self.ws.send_bytes(b"\x01" + struct.pack(">II", 9001, i) + enc.encode(pcm))
            await asyncio.sleep(0.06)
        await self.ws.send_str(json.dumps({"command": "on_stream_stop", "stream_id": 9001}))


# ---------------------------------------------------------------------------- Fake-Web (ID-Listen, Avatare, GitHub)
def _png(color: tuple) -> bytes:
    from PIL import Image
    import io
    b = io.BytesIO()
    Image.new("RGB", (500, 500), color).save(b, "PNG")
    return b.getvalue()


def add_fake_web(app) -> None:  # noqa: ANN001
    from aiohttp import web
    users = "\n".join(["100001,JIGEN,Antonio,Avellino,8,Italy", "2621234,DO1TEST,Tobias,Minden,NRW,Germany",
                       "2625001,DL1ABC,Hans,Minden,NRW,Germany"] + [f"{3000000 + i},X{i}AA,N,C,S,Land" for i in range(1200)])
    local = {"count": 2, "results": [{"id": 2621234, "callsign": "DO1TEST", "fname": "Tobias", "city": "Minden", "country": "Germany"},
                                     {"id": 2625001, "callsign": "DL1ABC", "fname": "Hans", "city": "Minden", "country": "Germany"}]}
    tgs = {"results": [{"TG-id": "262", "callsign": "Deutschland", "id": "262"}, {"TG-id": "26299", "callsign": "N8 Crosslink Test", "id": "26299"},
                       {"TG-id": "3", "callsign": "N/A", "id": "3"}]}
    ph, red, blue = _png((128, 128, 128)), _png((200, 30, 30)), _png((30, 30, 200))
    FakeWeb.hits = {}

    async def h(request):  # noqa: ANN001, ANN202
        p = request.path
        FakeWeb.hits[p] = FakeWeb.hits.get(p, 0) + 1
        if p == "/ids/subscriber_ids.csv":
            return web.Response(text=users)
        if p == "/ids/local.json":
            return web.json_response(local)
        if p == "/ids/tg.json":
            return web.json_response(tgs)
        if p.startswith("/ids/idimg-"):
            rid = p.split("-")[1].split(".")[0]
            return web.Response(body={"2621234": red, "2625001": blue}.get(rid, ph), content_type="image/png")
        if p == "/raw/n8crosslink/__init__.py":
            return web.Response(text=f'__version__ = "{FakeWeb.version}"\n')
        if p == "/raw/CHANGELOG.md":
            return web.Response(text=f"# Changelog\n\n## [{FakeWeb.version}] – 2026-12-01\n### Neu\n- **Testfunktion** für die Simulation\n- Watchdog-Verbesserungen\n\n## [1.0.0] – alt\n- alt\n")
        return web.Response(status=404)
    app.router.add_get("/ids/{x}", h)
    app.router.add_get("/raw/{p:.*}", h)


class FakeWeb:
    hits: dict = {}
    version = "9.9.9"


# ---------------------------------------------------------------------------- Ablauf
async def main() -> int:
    from aiohttp import web
    loop = asyncio.get_running_loop()
    voc = FakeVocoder()
    await loop.create_datagram_endpoint(lambda: voc, local_addr=("127.0.0.1", VOC_PORT))
    hb = FakeHB()
    await loop.create_datagram_endpoint(lambda: hb, local_addr=("127.0.0.1", HB_PORT))
    frn = FakeFRN()
    await asyncio.start_server(frn.handle, "127.0.0.1", FRN_PORT)
    zel = FakeZello()
    app = web.Application()
    app.router.add_get("/ws", zel.handler)
    add_fake_web(app)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", ZELLO_PORT).start()

    tmp = tempfile.mkdtemp()
    db = Database(os.path.join(tmp, "sim.db"))
    db.save_section("frn", {"server": "127.0.0.1", "port": FRN_PORT, "email": "a@b.c", "password": "x", "net": "Test",
                            "text_messages": True})
    db.save_section("dmr", {"host": "127.0.0.1", "port": HB_PORT, "password": FakeHB.PASS, "peer_id": 262000199,
                            "src_id": 2620099, "tg_rx": 262, "tg_tx": 26299, "slot": 2, "options": "TS2=262",
                            "userdb_url": "", "userdb_fallback_url": ""})
    db.save_section("zello", {"enabled": True, "server": f"ws://127.0.0.1:{ZELLO_PORT}/ws", "channel": "N8test",
                              "username": "n8bridge", "password": "pw", "auth_mode": "none"})
    # N8X_SIM_VOCODER=droidstar: echter DroidStar-Vocoder statt Fake-AMBEserver
    use_ds = os.environ.get("N8X_SIM_VOCODER") == "droidstar"
    if use_ds:
        from n8crosslink.vocoder import DroidStarCodec, find_droidstar_lib
        lib = find_droidstar_lib()
        assert lib, "N8X_AMBE_LIB nicht gesetzt / DroidStar-Vocoder nicht gebaut"
        c = DroidStarCodec(lib)
        t = (np.sin(2 * np.pi * 1000 * np.arange(160 * 50) / 8000) * 9000).astype("<i2")
        FakeHB.tone = [c.encode(t[i * 160:(i + 1) * 160].tobytes()) for i in range(50)][5:]
        c.close()
        db.save_section("vocoder", {"vocoder_mode": "droidstar"})
    else:
        db.save_section("vocoder", {"vocoder_mode": "ambeserver", "ambeserver_port": VOC_PORT})
    db.save_section("general", {"hang_time_ms": 400, "watchdog_offline_s": 4})
    web_base = f"http://127.0.0.1:{ZELLO_PORT}/ids"
    db.save_section("ids", {"subscriber_csv_url": f"{web_base}/subscriber_ids.csv", "subscriber_json_url": "",
                            "local_json_url": f"{web_base}/local.json", "local_csv_url": "", "user_api_url": "",
                            "radioid_fallback_url": "", "talkgroups_url": f"{web_base}/tg.json",
                            "avatar_url": f"{web_base}/idimg-{{id}}.png"})
    bridge = Bridge(db)
    await bridge.start()
    r = bridge.router
    bridge.wd_interval = 1.0
    wd_task = asyncio.create_task(bridge.watchdog())

    print("\n▶ Verbindungsaufbau")
    for _ in range(60):
        if all(p.online for p in r.ports.values()):
            break
        await asyncio.sleep(0.1)
    for k, p in r.ports.items():
        check(f"{k} online", p.online, f"{p.state} {p.detail}")
    v = bridge.vocoder.status()
    check("Vocoder bereit (" + ("DroidStar" if use_ds else "AMBEserver-Protokoll") + ")", v["online"], f"{v['product']} {v['version'][:20]}")
    check("FRN-Login als Crosslink (CL=0, BC=Crosslink)", "<CL>0</CL>" in frn.login and "<BC>Crosslink</BC>" in frn.login)
    check("DMR RPTC 302 Byte + RPTO", getattr(hb, "cfg_len", 0) == 302 and hb.options == b"TS2=262",
          f"{getattr(hb, 'cfg_len', 0)} Byte, RPTO={hb.options!r}")
    await asyncio.sleep(0.5)
    check("FRN-Raumliste gelesen", len(r.ports["frn"].clients) == 2,
          ", ".join(c["callsign"] + " " + c["name"] for c in r.ports["frn"].clients))

    # ---------------- ID-Listen & Avatare
    print("\n▶ ID-Listen (FreeRadioID-Format) und Talkgroups")
    res = await bridge.idlists.update_all()
    info = db.idlists_info()
    check("DMR-IDs geladen (CSV ohne Kopfzeile)", info["users"] == 1203 and db.userdb_lookup(2621234)["country"] == "Germany",
          f"{info['users']} IDs, 2621234 = {db.userdb_lookup(2621234)}")
    check("FreeRadioID-Registrierungen", info["registered"] == 2 and db.frid_is_registered(2621234), f"{info['registered']}")
    check("Talkgroup-Namen (N/A ausgelassen)", info["talkgroups"] == 2 and db.tg_name(262) == "Deutschland", f"262 = {db.tg_name(262)!r}")

    # ---------------- A: FRN -> DMR + Zello
    print("\n▶ A: FRN (DL1ABC Hans) spricht 2 s")
    hb.rx.clear()
    t0 = time.time()
    lq: asyncio.Queue = asyncio.Queue()
    r.audio_listeners.add(lq)
    await frn.talk(1, 2.0)
    await asyncio.sleep(2.0)
    r.audio_listeners.discard(lq)
    items = [lq.get_nowait() for _ in range(lq.qsize())]
    pcm_frames = [x for x in items if isinstance(x, bytes)]
    ctrl = [x.get("type") for x in items if isinstance(x, dict)]
    check("Mithören: Start/Ende + Audio", ctrl[:1] == ["start"] and ctrl[-1:] == ["end"] and len(pcm_frames) >= 90,
          f"{len(pcm_frames)} Rahmen à 20 ms, Pegel {level_dbfs(b''.join(pcm_frames)):.0f} dBFS")
    a = analyse_dmr(hb.rx)
    check("DMR: Voice-Header + Terminator", a["headers"] >= 1 and a["terms"] == 1 and a["lc_ok"],
          f"{a['headers']} Header, {a['terms']} Terminator, LC-Prüfsumme ok={a['lc_ok']}")
    check("DMR: Sprachrahmen ≈ Dauer", 28 <= a["voice"] <= 45, f"{a['voice']} Bursts à 60 ms")
    check("DMR: Quelle/Ziel/TS", a["src"] == {2620099} and a["dst"] == {26299} and a["slot"] == {2},
          f"src {a['src']} dst {a['dst']} TS {a['slot']}")
    check("DMR: Talker Alias = Stationsname", a["ta"] == "DL1ABC Hans", repr(a["ta"]))
    z = zel.streams[-1] if zel.streams else {}
    check("Zello: Textnachricht mit Name", bool(zel.texts) and "DL1ABC Hans" in zel.texts[-1], zel.texts[-1] if zel.texts else "")
    check("Zello: Stream gestartet/gestoppt", z.get("stopped", False) and 25 <= z.get("packets", 0) <= 45,
          f"{z.get('packets')} Opus-Pakete, Header {z.get('header')}")
    lh = db.lh_recent(5)[0]
    check("Last Heard: FRN-Eintrag", lh["source"] == "frn" and lh["name"] == "DL1ABC Hans" and set(lh["targets"]) == {"dmr", "zello"},
          f"{lh['name']} → {lh['targets']}, {lh['duration']} s")

    # ---------------- B: DMR -> FRN + Zello
    print("\n▶ B: DMR (ID 2621234, Talker Alias „DO1TEST Test“) spricht 1,5 s")
    await asyncio.sleep(0.6)
    p0, r0, z0 = frn.tx_pkts, frn.rx0, len(zel.streams)
    await hb.send_stream(2621234, 262, 1.5, "DO1TEST Test")
    await asyncio.sleep(1.5)
    check("FRN: TX0 -> TX1-Pakete -> RX0", frn.tx_pkts - p0 >= 6 and frn.rx0 > r0, f"{frn.tx_pkts - p0} Pakete à 200 ms")
    lv = [x for x in frn.tx_levels[-5:] if x > -60]
    check("FRN: Audio kommt an (Ton vom Vocoder)", len(lv) >= 3, f"Pegel {', '.join(f'{x:.0f}' for x in frn.tx_levels[-5:])} dBFS")
    check("FRN: Sprechername als Textnachricht", any("DO1TEST" in t or "2621234" in t for t in frn.texts), frn.texts[-1] if frn.texts else "")
    check("Zello: zweiter Stream", len(zel.streams) == z0 + 1 and zel.streams[-1]["stopped"], f"{zel.streams[-1]['packets']} Pakete")
    lh = db.lh_recent(5)[0]
    check("Last Heard: Talker Alias übernommen", lh["source"] == "dmr" and lh["name"] == "DO1TEST Test", f"{lh['name']} (ID {lh['dmr_id']})")

    # ---------------- C: Zello -> FRN + DMR
    print("\n▶ C: Zello (dj_zello) spricht 1,5 s")
    await asyncio.sleep(0.6)
    hb.rx.clear()
    p0 = frn.tx_pkts
    await zel.talk("dj_zello", 1.5)
    await asyncio.sleep(1.8)
    a = analyse_dmr(hb.rx)
    check("DMR: Stream mit Alias dj_zello", a["terms"] == 1 and a["ta"] == "dj_zello", f"{a['voice']} Bursts, TA {a['ta']!r}")
    check("FRN: Pakete gesendet", frn.tx_pkts - p0 >= 6, f"{frn.tx_pkts - p0} Pakete")

    # ---------------- D: Schleifenschutz / Belegt
    print("\n▶ D: DMR spricht, gleichzeitig FRN -> muss blockiert werden")
    await asyncio.sleep(0.6)
    hb_task = asyncio.create_task(hb.send_stream(2621234, 262, 2.0, "DO1TEST Test"))
    await asyncio.sleep(0.5)
    p0 = frn.tx_pkts
    await frn.talk(1, 0.8)
    await hb_task
    await asyncio.sleep(1.5)
    rows = db.lh_recent(3)
    blocked = [x for x in rows if x["status"] == "blocked"]
    check("FRN-Durchgang während DMR blockiert", bool(blocked) and blocked[0]["source"] == "frn",
          f"{len(blocked)} blockiert: {blocked[0]['name'] if blocked else ''}")
    check("DMR-Durchgang trotzdem vollständig nach FRN", frn.tx_pkts - p0 >= 8, f"{frn.tx_pkts - p0} Pakete")
    check("Bridge danach frei", r.active is None and all(p.tx_talker is None for p in r.ports.values()))

    # ---------------- E: zwei Durchsagen direkt hintereinander
    print("\n▶ E: FRN – zwei Stationen direkt nacheinander (Sendepuffer läuft noch)")
    await asyncio.sleep(1.0)
    hb.rx.clear()
    z0 = len(zel.streams)
    await frn.talk(1, 1.0)
    await asyncio.sleep(1.05)          # FRN-Ende wird erkannt, DMR/Zello-Puffer laufen noch
    await frn.talk(2, 1.0)
    await asyncio.sleep(2.5)
    sids = []
    for d in hb.rx:
        if d[16:20] not in sids:
            sids.append(d[16:20])
    order_ok = True
    if len(sids) == 2:
        last_first = max(i for i, d in enumerate(hb.rx) if d[16:20] == sids[0])
        first_second = min(i for i, d in enumerate(hb.rx) if d[16:20] == sids[1])
        order_ok = last_first < first_second
    a = analyse_dmr(hb.rx)
    check("DMR: zwei getrennte Streams ohne Überlappung", len(sids) == 2 and order_ok and a["terms"] == 2,
          f"{len(sids)} Streams, {a['terms']} Terminatoren, nacheinander={order_ok}")
    new = zel.streams[z0:]
    check("Zello: zwei vollständige Streams", len(new) == 2 and all(x["stopped"] for x in new),
          ", ".join(f"{x['packets']} Pakete" for x in new))
    check("Bridge danach frei (E)", r.active is None and all(p.tx_talker is None for p in r.ports.values()))

    # ---------------- Avatare
    print("\n▶ Avatare (SQLite-Cache)")
    a1 = await bridge.avatars.get("dmr", "2621234")
    check("DMR-Avatar geladen & verkleinert", a1 is not None and a1[0] == "image/webp" and len(a1[1]) < 20000,
          f"{a1[0] if a1 else None}, {len(a1[1]) if a1 else 0} Byte")
    hits = FakeWeb.hits.get("/ids/idimg-2621234.png", 0)
    await bridge.avatars.get("dmr", "2621234")
    check("Zweiter Abruf aus SQLite (kein Download)", FakeWeb.hits.get("/ids/idimg-2621234.png", 0) == hits)
    check("Unregistrierte ID wird nicht angefragt", await bridge.avatars.get("dmr", "3000005") is None
          and "/ids/idimg-3000005.png" not in FakeWeb.hits)
    a2 = await bridge.avatars.get("frn", "DL1ABC")
    check("FRN-Rufzeichen -> FreeRadioID-Avatar", a2 is not None)
    a3 = await bridge.avatars.get("zello", "do1test_tobias")
    check("Zello-Name mit Rufzeichen -> Avatar", a3 is not None)
    ok_up = bridge.avatars.upload("zello", "dj_zello", _png((10, 200, 10)))
    a4 = await bridge.avatars.get("zello", "DJ_Zello")
    check("Zello-Upload hat Vorrang", ok_up and a4 is not None)
    before = FakeWeb.hits.get("/ids/idimg-2621234.png", 0)
    rr = await bridge.avatars.refresh_all()
    check("Tages-Refresh lädt neu", FakeWeb.hits.get("/ids/idimg-2621234.png", 0) == before + 1 and rr["with_avatar"] >= 2, str(rr))

    # ---------------- Watchdog
    print("\n▶ Watchdog: FRN-Server trennt die Verbindung")
    c0, rc0 = frn.connects, r.ports["frn"].reconnects
    frn.drop()
    for _ in range(150):
        if r.ports["frn"].online and frn.connects > c0:
            break
        await asyncio.sleep(0.1)
    check("FRN wieder verbunden", r.ports["frn"].online and frn.connects > c0 and r.ports["frn"].reconnects == rc0 + 1,
          f"{r.ports['frn'].reconnects} Wiederverbindungen")
    print("▶ Watchdog: Verbindungsschleife von DMR stirbt")
    r.ports["dmr"].main_task.cancel()
    await asyncio.sleep(3)
    check("DMR-Port vom Watchdog neu aufgebaut", r.ports["dmr"].wd_restarts >= 1 and r.ports["dmr"].online,
          f"Neuaufbauten {r.ports['dmr'].wd_restarts}, Grund: {r.ports['dmr'].last_wd_reason}")
    print("▶ Watchdog: Zello-Server weg -> nach Limit kompletter Neuaufbau")
    zr0 = r.ports["zello"].reconnects
    await zel.ws.close()
    for _ in range(50):
        if not r.ports["zello"].online:
            break
        await asyncio.sleep(0.1)
    went_off = not r.ports["zello"].online
    for _ in range(150):
        if r.ports["zello"].online:
            break
        await asyncio.sleep(0.1)
    check("Zello: Abbruch erkannt und wieder verbunden", went_off and r.ports["zello"].online and r.ports["zello"].reconnects == zr0 + 1,
          f"{r.ports['zello'].reconnects} Wiederverbindungen")

    # ---------------- Updateprüfung
    print("\n▶ Updateprüfung")
    bridge.updater.raw_url = lambda path: f"http://127.0.0.1:{ZELLO_PORT}/raw/{path}"
    st_u = await bridge.updater.check()
    check("Neue Version erkannt + Änderungen gelesen", st_u["available"] and st_u["latest"] == "9.9.9" and "Testfunktion" in st_u["notes"]
          and "1.0.0" not in st_u["notes"], f"{st_u['current']} → {st_u['latest']}")
    rq = await bridge.updater.request_update("test", bridge.system)
    check("Update jetzt ohne systemd-Unit sauber abgelehnt", not rq["ok"], rq["message"][:50])

    # ---------------- FRN: Passwort anfordern
    # ---------------- Operator-Wechsel per Neuanmeldung
    print("\n▶ FRN: Operator-Wechsel (Neuanmeldung mit Stationsname)")
    fp = r.ports["frn"]
    fp.section.update({"id_override": True, "id_restore_s": 1.5})
    ev0 = len(db.events(1000))
    n_login = len(frn.logins)
    await asyncio.sleep(1.0)
    await hb.send_stream(2621234, 262, 1.5, "DO1TEST Test")
    await asyncio.sleep(1.5)
    new = [parse_tags(x) for x in frn.logins[n_login:]]
    ons = [x.get("ON") for x in new]
    check("Neuanmeldung mit Operator der DMR-Station", len(ons) >= 1 and ons[0] != "N8XLINK, Crosslink" and "," in ons[0],
          f"ON={ons[0] if ons else '-'} · DS={new[0].get('DS') if new else '-'}")
    check("Beschreibung zeigt Quelle", bool(new) and new[0].get("DS", "").startswith("via DMR"), new[0].get("DS", "") if new else "")
    check("Ton unter fremdem Operator gesendet (gepuffert)", frn.tx_by_on.get(ons[0] if ons else "", 0) >= 6,
          f"{frn.tx_by_on.get(ons[0] if ons else '', 0)} Pakete")
    await asyncio.sleep(2.5)
    check("Danach zurück zum eigenen Operator", parse_tags(frn.logins[-1]).get("ON") == "N8XLINK, Crosslink" and fp.identity is None
          and fp.online, f"{len(frn.logins) - n_login} Anmeldungen")
    lost = [e for e in db.events(1000)[: len(db.events(1000)) - ev0] if "Verbindung verloren" in e.get("message", "")]
    check("Kein „Verbindung verloren“ beim Wechsel", not lost, lost[0]["message"] if lost else "")
    # Server lehnt fremden Operator ab -> Rückfall, Ton trotzdem raus
    frn.reject_foreign = True
    own0 = frn.tx_by_on.get("N8XLINK, Crosslink", 0)
    await hb.send_stream(2621234, 262, 1.5, "DO1TEST Test")
    await asyncio.sleep(2.5)
    check("Abgelehnt -> Rückfall auf eigenen Operator, Option aus", fp.override_blocked and fp.online and fp.identity is None)
    check("Ton trotzdem gesendet (eigener Operator)", frn.tx_by_on.get("N8XLINK, Crosslink", 0) - own0 >= 6,
          f"{frn.tx_by_on.get('N8XLINK, Crosslink', 0) - own0} Pakete")
    ok_t, title_t, _ = await fp.test_identity()
    check("Testknopf: Ablehnung erkannt", not ok_t and fp.online and fp.identity is None, title_t)
    frn.reject_foreign = False
    ok_t, title_t, _ = await fp.test_identity()
    check("Testknopf: Annahme erkannt + zurück", ok_t and fp.online and fp.identity is None
          and parse_tags(frn.logins[-1]).get("ON") == "N8XLINK, Crosslink", title_t)
    fp.section["id_override"] = False

    # ---------------- Sprachansage
    print("\n▶ Sprachansage des Rufzeichens")
    from n8crosslink import announce as ann
    if ann.available():
        bridge.cfg["general"].update({"announce_enabled": True, "announce_frn": True})
        await asyncio.sleep(1.0)
        p0 = frn.tx_pkts
        await hb.send_stream(2621234, 262, 1.5, "DO1TEST Test")
        await asyncio.sleep(3.5)
        base = 7   # 1,5 s Ton ≈ 7–8 Pakete à 200 ms
        check("Ansage vor dem Ton (mehr Pakete)", frn.tx_pkts - p0 >= base + 4, f"{frn.tx_pkts - p0} Pakete statt ~{base + 1}")
        txt = ann.speech_text("DO1TEST", "DO1TEST Test", {"announce_spell": "nato"})
        check("NATO-Buchstabiertext", txt.startswith("Delta, Oscar, Eins"), txt)
        bridge.cfg["general"]["announce_enabled"] = False
    else:
        print("  (espeak-ng fehlt – Ansage-Test übersprungen)")

    print("\n▶ FRN: Passwort anfordern (System Manager)")
    from n8crosslink.frn import request_password
    sm = FakeSysman()
    srv = await asyncio.start_server(sm.handle, "127.0.0.1", 20025)
    reg = {"callsign": "DO1NEU", "op_name": "Neu", "email": "neu@example.org", "band": "Crosslink",
           "description": "Test", "country": "Germany", "city": "Minden - JO42",
           "sysman_server": "127.0.0.1", "sysman_port": 20025}
    ok1, t1, _ = await request_password(reg)
    check("Anforderung angenommen (OK) + korrektes IG-Format",
          ok1 and sm.lines[0] == "IG:<ON>DO1NEU, Neu</ON><EA>neu@example.org</EA><BC>Crosslink</BC><DS>Test</DS><NN>Germany</NN><CT>Minden - JO42</CT>",
          f"{t1}: {sm.lines[0][:60]}…")
    ok2, t2, _ = await request_password(reg)
    check("Bereits registriert (NU) erkannt", not ok2 and t2 == "Bereits registriert", t2)
    ok3, t3, m3 = await request_password({**reg, "email": "kaputt", "city": "Minden", "band": "UKW"})
    check("Ungültige Eingaben vor dem Senden abgefangen", not ok3 and t3 == "Eingaben prüfen" and len(sm.lines) == 2
          and m3.count("\n") == 2, m3.replace("\n", " | ")[:90])
    srv.close()
    ok4, t4, _ = await request_password({**reg, "sysman_port": 20099})
    check("System Manager nicht erreichbar sauber gemeldet", not ok4 and t4 == "Keine Verbindung", t4)

    # ---------------- Backup / Wiederherstellung / Zurücksetzen
    print("\n▶ Verschlüsseltes Backup")
    from n8crosslink import backup as bk
    pw = "N8test-Superadmin!"
    db.set_user("chef", pw, "superadmin")
    name, blob = bk.create(db, tmp, pw, "chef")
    plain_hits = [w for w in (b"SQLite format", b"testpass", b"DL1ABC", b"n8schicht", b"manifest", b"crosslink.db")
                  if w in blob]
    check("Backup komplett verschlüsselt (kein Klartext)", blob.startswith(b"N8XBAK") and not plain_hits,
          f"{name}, {len(blob) // 1024} KB, Klartext-Funde: {plain_hits or 'keine'}")
    try:
        bk.inspect(blob, "falsch")
        wrong = False
    except bk.BackupError as e:
        wrong = "Passwort falsch" in str(e)
    check("Falsches Passwort wird abgelehnt", wrong)
    man, dbb = bk.inspect(blob, pw)
    check("Manifest lesbar mit richtigem Passwort", man["version"] and man["counts"]["users"] >= 2, str(man["counts"]))
    lh_before = len(db.lh_recent(500))
    db.reset("all")
    check("Zurücksetzen 'alles' -> Standard-Login", db.list_users()[0]["username"] == "n8schicht" and len(db.lh_recent(500)) == 0
          and db.load_config()["dmr"]["host"] == "dmr.die-n8schicht.de")
    bk.restore_into(db, dbb)
    check("Wiederherstellung: Daten, Benutzer, Einstellungen zurück",
          len(db.lh_recent(500)) == lh_before and db.check_login("chef", pw) and db.load_config()["dmr"]["host"] == "127.0.0.1"
          and db.idlists_info()["users"] == 1203, f"{lh_before} Last-Heard-Einträge, DMR-Host {db.load_config()['dmr']['host']}")

    # ---------------- Statistik
    st = db.stats(0)
    check("Statistik", st["talks"] >= 6 and st["blocked"] >= 1, f"{st['talks']} Durchgänge, {st['blocked']} blockiert, {st['airtime']:.1f} s")

    wd_task.cancel()
    await bridge.stop()
    await runner.cleanup()
    bad = [x for x in RESULTS if not x[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} Prüfungen bestanden")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
