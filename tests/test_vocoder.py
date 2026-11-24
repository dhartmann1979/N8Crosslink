"""Vocoder-Robustheit: verlorene und verspätete UDP-Antworten dürfen die
Zuordnung Anfrage/Antwort nicht verschieben.

Der Fake-AMBEserver kodiert die laufende Nummer aus dem ersten PCM-Sample in das
erste AMBE-Byte zurück. Jede 7. Antwort geht verloren, jede 11. kommt 450 ms
zu spät. Erwartet: jede gelieferte Antwort passt zu ihrer Anfrage.
"""
from __future__ import annotations

import asyncio
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from n8crosslink.vocoder import Vocoder  # noqa: E402

PORT = 24701


class FlakyAmbeServer(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.n = 0

    def connection_made(self, tr):  # noqa: ANN001
        self.tr = tr

    def datagram_received(self, d: bytes, addr) -> None:  # noqa: ANN001
        if d[3] == 0x01:   # Probe-Dekodierung beim Start
            p = bytes([0x00, 160]) + bytes(320)
            self.tr.sendto(struct.pack(">BHB", 0x61, len(p), 2) + p, addr)
            return
        self.n += 1
        seq = struct.unpack(">h", d[6:8])[0] & 0xFF
        p = bytes([0x01, 72, seq]) + bytes(8)
        pkt = struct.pack(">BHB", 0x61, len(p), 1) + p
        if self.n % 7 == 0:
            return                                    # verloren
        if self.n % 11 == 0:
            asyncio.get_running_loop().call_later(0.45, self.tr.sendto, pkt, addr)  # zu spät
            return
        self.tr.sendto(pkt, addr)


async def main() -> int:
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(FlakyAmbeServer, local_addr=("127.0.0.1", PORT))
    v = Vocoder({"vocoder_mode": "ambeserver", "ambeserver_port": PORT, "ambeserver_send_init": False,
                 "vocoder_timeout_ms": 200})
    await v.start()
    assert v.online, "Vocoder nicht online"
    futs = []
    for i in range(120):
        pcm = np.full(160, i % 256, dtype="<i2").tobytes()
        futs.append(asyncio.ensure_future(v.encode(pcm)))
        await asyncio.sleep(0.005)
    res = await asyncio.gather(*futs)
    wrong = sum(1 for i, r in enumerate(res) if r is not None and r[0] != i % 256)
    ok = sum(1 for r in res if r is not None)
    print(f"geliefert {ok}/120, falsch zugeordnet {wrong}, Statistik {v.status()}")
    await v.stop()
    if wrong:
        print("FEHLER: Antworten verschoben")
        return 1
    if ok < 110:
        print("FEHLER: zu viele Ausfälle trotz Wiederholung")
        return 1
    print("OK (AMBEserver)")
    return await droidstar()


async def droidstar() -> int:
    """DroidStar-Vocoder (falls gebaut, z. B. N8X_AMBE_LIB=…/libambe2.so)."""
    from n8crosslink.dmr.burst import AMBE_SILENCE
    from n8crosslink.vocoder import find_droidstar_lib, tone_test
    if not find_droidstar_lib():
        print("DroidStar-Vocoder nicht gebaut – Test übersprungen")
        return 0
    v = Vocoder({"vocoder_mode": "droidstar"})
    await v.start()
    assert v.online, "DroidStar-Vocoder nicht online"
    r = await tone_test(v, 50)
    # Stille-Rahmen aus dem DMR-Burst muss Stille ergeben (Bitreihenfolge stimmt)
    v.new_stream("dec")
    pcm = [await v.decode(AMBE_SILENCE) for _ in range(5)]
    rms = float(np.sqrt(np.mean(np.frombuffer(pcm[-1], dtype="<i2").astype(float) ** 2)))
    # parallele Aufrufe bleiben in Reihenfolge
    outs = await asyncio.gather(*[v.encode(bytes(320)) for _ in range(30)])
    await v.stop()
    print(f"DroidStar: {r}, Stille-RMS {rms:.0f}, {sum(o is not None for o in outs)}/30 parallel")
    if not r["ok"] or rms > 50 or not all(outs):
        print("FEHLER DroidStar")
        return 1
    print("OK (DroidStar)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
