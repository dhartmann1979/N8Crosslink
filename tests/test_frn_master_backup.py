"""FRN Master & Backup: Master ist Priorität 1 – Ausfall → Backup, Master wieder da → zurück zum Master.

Zwei nachgebaute FRN-Server (Login + Leerlauf) und ein nachgebautes ADN-Dashboard mit /api/info und /api/live."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from n8crosslink import frn_cluster  # noqa: E402
from n8crosslink.frn import FrnPort  # noqa: E402


class FakeFrn:
    """Minimaler FRN-Server: Login → Protokollversion + <AL>OK</AL>, danach IDLE auf jedes P."""
    def __init__(self):
        self.server = None
        self.port = 0
        self.logins = 0

    async def start(self):
        self.server = await asyncio.start_server(self._client, "127.0.0.1", self.port)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.server.close()
        for w in list(getattr(self, "writers", [])):
            w.close()
        try:
            await asyncio.wait_for(self.server.wait_closed(), 2)
        except asyncio.TimeoutError:
            pass

    async def _client(self, reader, writer):
        self.writers = getattr(self, "writers", []) + [writer]
        try:
            await reader.readline()
            self.logins += 1
            writer.write(b"2014003\r\n<AL>OK</AL><SV>test</SV>\r\n")
            while True:
                line = await reader.readline()
                if not line:
                    break
                if line.strip() == b"P":
                    writer.write(bytes([0]))
                    await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()


def dashboard(info: dict, live: dict):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(info if self.path == "/api/info" else live).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Router:
    def __init__(self):
        self.events = []

    def event(self, lvl, text):
        self.events.append((lvl, text))

    def notify(self):
        pass

    def finished_tx(self, port):
        pass


def test_detect_from_dashboard():
    info = {"cluster": {"role": "backup", "master": {"host": "frn.example.org", "port": 10024},
                        "backup": {"host": "frn-backup.example.org", "port": 10025}}}
    srv = dashboard(info, {})
    try:
        c = frn_cluster.detect("", f"127.0.0.1:{srv.server_address[1]}")
        assert c["master"] == ("frn.example.org", 10024) and c["backup"] == ("frn-backup.example.org", 10025)
        assert frn_cluster.detect("127.0.0.1:1") is None                          # kein Dashboard: nichts erkannt
    finally:
        srv.shutdown()


def test_master_ready_checks():
    srv = dashboard({"cluster": {"role": "master", "maintenance": True}}, {"server": {"running": True, "error": ""}})
    try:
        async def run():
            frn = FakeFrn()
            await frn.start()
            host = f"127.0.0.1"
            ok, why = frn_cluster.master_ready(host, frn.port, False)
            assert ok
            await frn.stop()
            ok, why = frn_cluster.master_ready(host, frn.port, False)
            assert not ok and "nicht erreichbar" in why
        asyncio.run(run())
    finally:
        srv.shutdown()


def test_failover_and_back_to_master(monkeypatch):
    async def run():
        master, backup = FakeFrn(), FakeFrn()
        await master.start()
        await backup.start()
        cfg = {"frn": {"enabled": True, "server": "127.0.0.1", "port": master.port, "backup_server": "127.0.0.1",
                       "backup_port": backup.port, "cluster_auto": True, "email": "x@example.org", "password": "p",
                       "callsign": "N8XLINK", "op_name": "Crosslink", "band": "Crosslink", "description": "t",
                       "country": "Germany", "city": "Minden - JO42", "net": "Test", "rx_timeout_ms": 1000}}
        r = Router()
        p = FrnPort(r, cfg)
        # Erkennung: Master = master.port, Backup = backup.port (wie vom ADN-Dashboard gemeldet)
        p.cluster = {"master": ("127.0.0.1", master.port), "backup": ("127.0.0.1", backup.port)}
        p.cluster_at = time.time()
        ready = {"ok": True}

        async def fake_ready(host, port, adn):
            return (ready["ok"], "Master läuft" if ready["ok"] else "Master weg")
        monkeypatch.setattr(frn_cluster, "amaster_ready", fake_ready)
        real_sleep = asyncio.sleep

        async def fast_sleep(t):
            await real_sleep(min(t, 0.05))
        monkeypatch.setattr(asyncio, "sleep", fast_sleep)
        await p.start()
        for _ in range(100):
            if p.online:
                break
            await real_sleep(0.05)
        assert p.online and p.on_master() and master.logins == 1
        # Master fällt aus → Backup
        ready["ok"] = False
        await master.stop()
        for _ in range(200):
            if p.online and not p.on_master():
                break
            await real_sleep(0.05)
        assert p.online and not p.on_master() and backup.logins >= 1, r.events[-5:]
        # Master wieder da → nach 3 Prüfungen zurück
        master2 = FakeFrn()
        master2.port = master.port
        await master2.start()
        ready["ok"] = True
        for _ in range(300):
            if p.online and p.on_master() and master2.logins:
                break
            await real_sleep(0.05)
        assert p.online and p.on_master() and master2.logins == 1, r.events[-6:]
        assert any("zurück zum Master" in t for _, t in r.events)
        assert p.info()["cluster"]["on"] == "master"
        await p.stop()
        await master2.stop()
        await backup.stop()
    asyncio.run(run())


if __name__ == "__main__":
    import types
    mp = types.SimpleNamespace(setattr=lambda o, n, v: setattr(o, n, v))
    test_detect_from_dashboard(); print("✓ Erkennung über das Dashboard")
    test_master_ready_checks(); print("✓ Prüfung, ob der Master bereit ist")
    test_failover_and_back_to_master(mp); print("✓ Ausfall → Backup, Master zurück → Master")
    print("OK")
