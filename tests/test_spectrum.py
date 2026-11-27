#!/usr/bin/env python3
"""Live-Anzeige: SpectrumMeter liefert Pegel, Spitze und das Spektrum am richtigen Platz."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from n8crosslink.audio.dsp import SpectrumMeter  # noqa: E402


def sine(f: float, amp: float, n: int = 800) -> bytes:
    return (np.sin(2 * np.pi * f * np.arange(n) / 8000) * amp * 32767).astype("<i2").tobytes()


m = SpectrumMeter()
for f in (300, 1000, 3000):
    m.reset()
    m.push(sine(f, 0.5))
    b = m.bands()
    k = int(np.argmax(b))
    lo, hi = m.edges[k], m.edges[k + 1]
    assert len(b) == 32 and lo <= f * 1.15 and hi >= f / 1.15, (f, k, lo, hi)
    assert 85 <= b[k] <= 100, b[k]                       # −6 dBFS-Sinus ≈ 91
    assert abs(m.peak + 6) < 0.5 and abs(m.level + 9) < 0.5, (m.peak, m.level)
m.reset()
m.push(b"\x00\x00" * 160)
assert max(m.bands()) == 0 and m.level == -90.0
print("✅ Spektrum: Bänder, Pegel und Spitze stimmen")
