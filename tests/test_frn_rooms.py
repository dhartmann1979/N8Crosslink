"""Raum-Auswahl FRN: Raumliste per kurzer FRN-Anmeldung, aus dem Dashboard und aus der laufenden Verbindung."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from n8crosslink import frn_rooms  # noqa: E402

ACC = {"email": "a@b.de", "password": "x", "callsign": "DO1TEST", "op_name": "Test", "net": "Test"}


async def _fake_server(answer_al: str, logins: list):
    async def handle(r, w):
        logins.append((await r.readline()).decode())
        w.write(b"2014003\r\n" + f"<SV>1</SV><AL>{answer_al}</AL>\r\n".encode())
        await w.drain()
        if answer_al != "OK":
            w.close()
            return
        await r.readline()                                    # RX0
        w.write(bytes([3]) + b"\x00\x01" + b"1\r\n<ON>DL1ABC, Hans</ON>\r\n")       # Teilnehmerliste zuerst
        w.write(bytes([5]) + b"3\r\nKrabbelgruppe\r\nLagerfeuer\r\nTest\r\n")       # dann die Raumliste
        await w.drain()
        try:
            await asyncio.wait_for(r.read(), 5)
        except Exception:  # noqa: BLE001
            pass
        w.close()
    return await asyncio.start_server(handle, "127.0.0.1", 0)


def test_probe_login_reads_rooms():
    async def run():
        logins = []
        srv = await _fake_server("OK", logins)
        port = srv.sockets[0].getsockname()[1]
        with mock.patch.object(frn_rooms.frn_cluster, "dashboard", return_value=None):
            d = await frn_rooms.rooms("127.0.0.1", port, ACC, None)
        srv.close()
        return d, logins
    d, logins = asyncio.run(run())
    assert [r["name"] for r in d["rooms"]] == ["Krabbelgruppe", "Lagerfeuer", "Test"] and d["source"] == "login"
    assert "<EA>a@b.de</EA>" in logins[0]


def test_probe_wrong_password():
    async def run():
        srv = await _fake_server("WRONG", [])
        port = srv.sockets[0].getsockname()[1]
        with mock.patch.object(frn_rooms.frn_cluster, "dashboard", return_value=None):
            d = await frn_rooms.rooms("127.0.0.1", port, ACC, None)
        srv.close()
        return d
    d = asyncio.run(run())
    assert not d["rooms"] and "abgelehnt" in d["note"]


def test_dashboard_and_live_and_no_double_login():
    dash = {"rooms": [{"name": "A", "clients": [1, 2]}, {"name": "Geheim", "hidden": True, "clients": []}]}
    with mock.patch.object(frn_rooms.frn_cluster, "dashboard", return_value=dash):
        d = asyncio.run(frn_rooms.rooms("frn.example.de", 10024, ACC, None))
    assert d["rooms"] == [{"name": "A", "clients": 2}] and d["source"] == "dashboard"
    live = SimpleNamespace(online=True, target=("FRN.example.de", 10024), nets=["X", "Y"])
    d = asyncio.run(frn_rooms.rooms("frn.example.de", 10024, ACC, live))
    assert [r["name"] for r in d["rooms"]] == ["X", "Y"] and d["source"] == "live"
    other = SimpleNamespace(online=True, target=("anderer.de", 10024), nets=["X"])
    with mock.patch.object(frn_rooms.frn_cluster, "dashboard", return_value=None), \
         mock.patch.object(frn_rooms, "_probe", side_effect=AssertionError("keine zweite Anmeldung")):
        d = asyncio.run(frn_rooms.rooms("frn.example.de", 10024, ACC, other))
    assert not d["rooms"] and "online" in d["note"]
