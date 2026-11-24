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
    return await n8vocoder()


async def n8vocoder() -> int:
    """N8schicht-Vocoder (falls gebaut, z. B. N8X_AMBE_LIB=…/libn8vocoder.so)."""
    from n8crosslink.dmr.burst import AMBE_SILENCE
    from n8crosslink.vocoder import effective_options, find_n8vocoder_lib, tone_test
    if not find_n8vocoder_lib():
        print("N8schicht-Vocoder nicht gebaut – Test übersprungen")
        return 0
    fails = []
    v = Vocoder({"vocoder_mode": "n8vocoder"})
    await v.start()
    if not v.online:
        print("FEHLER: N8schicht-Vocoder nicht online")
        return 1
    r = await tone_test(v, 50)
    if not r["ok"]:
        fails.append(f"Tontest {r}")
    # Stille-Rahmen aus dem DMR-Burst muss Stille ergeben (Bitreihenfolge stimmt)
    v.new_stream("dec")
    pcm = [await v.decode(AMBE_SILENCE) for _ in range(5)]
    rms = float(np.sqrt(np.mean(np.frombuffer(pcm[-1], dtype="<i2").astype(float) ** 2)))
    if rms > 50:
        fails.append(f"Stille-RMS {rms:.0f}")
    # parallele Aufrufe bleiben in Reihenfolge und gehen nicht verloren
    outs = await asyncio.gather(*[v.encode(bytes(320)) for _ in range(30)])
    if not all(outs):
        fails.append("parallele Aufrufe")
    # Bitfehler (schwaches Funksignal): kein Absturz, Pegel bleibt begrenzt
    rng = np.random.default_rng(1)
    worst = 0
    for _ in range(300):
        f = bytes(rng.integers(0, 256, 9, dtype=np.uint8))
        p = await v.decode(f)
        if p is None:
            fails.append("Bitfehler: keine Ausgabe"); break
        worst = max(worst, int(np.abs(np.frombuffer(p, dtype="<i2")).max()))
    if worst >= 32767:
        fails.append(f"Bitfehler: Übersteuerung {worst}")
    # Optionen live setzen: halbe Ausgangsverstärkung -> deutlich leiser
    async def level() -> float:
        v.new_stream("both")
        t = (np.sin(2 * np.pi * 440 * np.arange(160 * 40) / 8000) * 9000).astype("<i2")
        ys = []
        for i in range(40):
            a = await v.encode(t[i * 160:(i + 1) * 160].tobytes())
            ys.append(np.frombuffer(await v.decode(a), dtype="<i2").astype(float))
        y = np.concatenate(ys[10:])
        return float(np.sqrt(np.mean(y ** 2)))
    l1 = await level()
    o = effective_options({"n8vocoder_options": {"dec": {"output_gain": 1.0}}})
    bad = await v.set_options(o)
    l2 = await level()
    if bad or not l2 < l1 * 0.7:
        fails.append(f"Optionen live: {l1:.0f} -> {l2:.0f} {bad}")
    # Absturz des Vocoder-Prozesses: Bridge läuft weiter, Prozess startet neu
    v.codec.proc.kill()
    await asyncio.sleep(0.2)
    first = await v.encode(bytes(320))          # darf None sein (Absturz bemerkt)
    again = await v.encode(bytes(320))
    if again is None or v.codec.restarts < 1:
        fails.append(f"Neustart nach Absturz: {first is not None}/{again is not None}, restarts={v.codec.restarts}")
    st = v.status()
    await v.stop()
    print(f"N8schicht-Vocoder {st['version']}: {r}, Stille-RMS {rms:.0f}, Bitfehler-Spitze {worst}, "
          f"Pegel {l1:.0f}->{l2:.0f}, Neustarts {st['restarts']}, Fehlrahmen {st['erasures']}")
    if fails:
        print("FEHLER N8schicht-Vocoder:", "; ".join(fails))
        return 1
    print("OK (N8schicht-Vocoder)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
