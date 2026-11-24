#!/usr/bin/env python3
"""Prüft die DMR-FEC gegen die unabhängige Implementierung dmr_utils3 (pip install dmr_utils3)."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from n8crosslink.dmr import burst as B  # noqa: E402
from n8crosslink.dmr import fec  # noqa: E402

try:
    import dmr_utils3.bptc as bptc
    import dmr_utils3.const as const
except ImportError:
    print("dmr_utils3 nicht installiert – übersprungen")
    sys.exit(0)

ok = True
for _ in range(200):
    lc = B.make_lc(random.randint(1, 16777215), random.randint(1, 16777215), random.random() < 0.5)
    h = fec.bytes_to_bits(B.build_lc_burst(lc, 1, False))
    t = fec.bytes_to_bits(B.build_lc_burst(lc, 1, True))
    ok &= bptc.encode_header_lc(lc).tolist() == [bool(x) for x in h[0:98] + h[166:264]]
    ok &= bptc.encode_terminator_lc(lc).tolist() == [bool(x) for x in t[0:98] + t[166:264]]
    e = bptc.encode_emblc(lc)
    f = fec.embedded_lc_encode(lc)
    ok &= all(e[i + 1].tolist() == [bool(x) for x in f[i]] for i in range(4))
    ok &= fec.full_lc_decode(B.build_lc_burst(lc, 1, False), fec.VOICE_LC_HEADER_MASK) == lc
    ok &= fec.embedded_lc_decode(f) == lc
for n, name in zip(range(1, 6), "BCDEF"):
    frag = [0] * 32 if n <= 4 else None
    bits = fec.bytes_to_bits(B.build_voice_burst((B.AMBE_SILENCE,) * 3, n, 1, frag))
    ok &= "".join(map(str, bits[108:116] + bits[148:156])) == const.EMB[f"BURST_{name}"].to01()
print("FEC identisch mit dmr_utils3:", "OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
