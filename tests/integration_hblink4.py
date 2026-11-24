"""Integrationstest: FRN (Fake) -> N8 Crosslink -> echtes HBlink4 -> zweiter Peer.

HBlink4(-FreeRadioID) lokal starten (UDP 62071, Passphrase passw0rd, TS2 TG 262), dann:
  N8X_AMBE_LIB=/opt/n8crosslink/lib/libambe2.so python3 tests/integration_hblink4.py
Umgebungsvariablen: HBPORT, HBPW, RPTO. Ergebnis: Pakete, die der zweite Peer empfängt.
Mit FreeRadioID-Secure-Login und der Server-Passphrase ist die Bridge Gast -> 0 Pakete.
"""
import asyncio, hashlib, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import sim_e2e as sim
from n8crosslink.app import Bridge
from n8crosslink.db import Database

HB = ("127.0.0.1", int(os.environ.get("HBPORT", 62071)))
PW = os.environ.get("HBPW", "passw0rd")

class Peer(asyncio.DatagramProtocol):
    def __init__(s, rid): s.rid = rid.to_bytes(4, "big"); s.rx = []; s.ok = asyncio.Event()
    def connection_made(s, tr): s.tr = tr; tr.sendto(b"RPTL" + s.rid)
    def datagram_received(s, d, a):
        if d.startswith(b"RPTACK") and not hasattr(s, "salted"):
            s.salted = 1; salt = d[6:10]
            s.tr.sendto(b"RPTK" + s.rid + hashlib.sha256(salt + PW.encode()).digest())
        elif d.startswith(b"RPTACK") and getattr(s, "salted") == 1:
            s.salted = 2
            cfg = (b"RPTC" + s.rid + b"DL0PEER ".ljust(8) + b"000000000" * 2 + b"01" + b"01" + b"52.0000" + b"008.0000" + b"000"
                   + b"Test".ljust(20) + b"Test".ljust(19) + b"1" + b"http://x".ljust(124) + b"20230101".ljust(40) + b"MMDVM".ljust(40))
            s.tr.sendto(cfg.ljust(302, b" ")[:302])
        elif d.startswith(b"RPTACK") and getattr(s, "salted") == 2:
            s.salted = 3; s.ok.set()
        elif d.startswith(b"DMRD"):
            s.rx.append(d)


async def main():
    loop = asyncio.get_running_loop()
    frn = sim.FakeFRN()
    srv = await asyncio.start_server(frn.handle, "127.0.0.1", 20124)
    d = tempfile.mkdtemp(); db = Database(os.path.join(d, "t.db"))
    db.save_section("frn", {"server": "127.0.0.1", "port": 20124, "email": "a@b.de", "password": "x", "net": "Test"})
    db.save_section("dmr", {"host": HB[0], "port": HB[1], "password": PW, "peer_id": 262000101, "src_id": 2620099,
                            "tg_rx": 262, "tg_tx": 262, "slot": 2, "options": os.environ.get("RPTO", ""),
                            "userdb_url": "", "userdb_fallback_url": ""})
    db.save_section("zello", {"enabled": False})
    db.save_section("vocoder", {"vocoder_mode": "n8vocoder"})
    db.save_section("ids", {k: "" for k in ("subscriber_csv_url","subscriber_json_url","local_json_url","local_csv_url","user_api_url","radioid_fallback_url","talkgroups_url")})
    br = Bridge(db); await br.start()
    peer = Peer(262000202)
    await loop.create_datagram_endpoint(lambda: peer, remote_addr=HB)
    await asyncio.wait_for(peer.ok.wait(), 10)
    for _ in range(100):
        if br.router.ports["dmr"].online and br.router.ports["frn"].online: break
        await asyncio.sleep(0.1)
    print("online:", {k: p.online for k, p in br.router.ports.items()}, "voc", br.vocoder.status()["online"])
    await asyncio.sleep(1)
    n0 = len(peer.rx); tx0 = br.router.ports["dmr"].stats["tx_pkts"]
    await frn.talk(1, 2.0)
    await asyncio.sleep(2.5)
    got = peer.rx[n0:]
    print(f"FRN->DMR: Bridge sendete {br.router.ports['dmr'].stats['tx_pkts']-tx0} DMRD, zweiter Peer empfing {len(got)}")
    if got:
        print("  erstes:", got[0][:20].hex(), "dst", int.from_bytes(got[0][8:11],'big'))
    await br.stop(); srv.close()
asyncio.run(main())
