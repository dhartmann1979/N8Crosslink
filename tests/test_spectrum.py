#!/usr/bin/env python3
"""Live-Anzeige: SpectrumMeter liefert je 20-ms-Rahmen Pegel, Spitze und 48 Bänder von 0 Hz bis 4 kHz am richtigen Platz;
der Router bündelt gemeinsam ankommende Rahmen zu einer Meldung."""
import asyncio
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from n8crosslink.audio.dsp import B64, SpectrumMeter  # noqa: E402


def sine(f: float, amp: float, n: int = 320) -> bytes:
    return (np.sin(2 * np.pi * f * np.arange(n) / 8000) * amp * 32767).astype("<i2").tobytes()


def test_meter():
    m = SpectrumMeter()
    assert m.edges[0] == 0 and m.edges[-1] == 4000 and len(m.idx) == 48
    for f in (150, 300, 1000, 2500, 3800):
        m.reset()
        m.push(sine(f, 0.5))
        b = m.bands()
        k = int(np.argmax(b))
        lo, hi = m.edges[k], m.edges[k + 1]
        assert lo - 40 <= f <= hi + 40, (f, k, lo, hi)
        assert 56 <= b[k] <= 63, b[k]                    # −6 dBFS-Sinus
        assert abs(m.peak + 6) < 0.5 and abs(m.level + 9) < 0.5, (m.peak, m.level)
    m.reset()
    lvl, pk, s = m.frame(b"\x00\x00" * 160)
    assert lvl == -90.0 and pk == -90.0 and s == "0" * 48 and all(c in B64 for c in s)


def test_router_batches_frames():
    from n8crosslink.core import Router  # noqa: F401  (nur Import prüfen)
    import n8crosslink.core as core
    r = core.Router.__new__(core.Router)
    r.meter, r._mq, r._mflush, r._msrc = SpectrumMeter(), [], False, ""
    q: asyncio.Queue = asyncio.Queue()
    r.listeners = {q}

    class P:
        key = "frn"

    async def run():
        for i in range(10):                              # ein FRN-Paket: 10 Rahmen auf einmal
            r._meter(P, sine(700, 0.3, 160), 0.0)
        await asyncio.sleep(0)
        msgs = [q.get_nowait() for _ in range(q.qsize())]
        assert len(msgs) == 1 and len(msgs[0]["f"]) == 10 and msgs[0]["ms"] == 20 and msgs[0]["fmax"] == 4000, msgs
    asyncio.run(run())


if __name__ == "__main__":
    test_meter()
    test_router_batches_frames()
    print("✅ Spektrum: Bänder 0–4 kHz, Pegel, Spitze, Bündelung je Paket")
