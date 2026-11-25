"""Klangaufbereitung: AGC regelt leise und laute Quellen auf den Zielpegel, Limiter hält die Decke, Pausen werden nicht
hochgezogen, Mitten-/Höhenanhebung vor dem Encoder übersteuert nicht."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from n8crosslink.audio.agc import AGC, ToneEQ, chain_from, to_f  # noqa: E402
from n8crosslink.db import DEFAULTS  # noqa: E402
from n8crosslink.vocoder import PROFILES, effective_options, pre_chain  # noqa: E402

T = np.arange(16000) / 8000


def _run(chain, x):
    pcm = x.astype("<i2").tobytes()
    out = b"".join(chain.process(pcm[i:i + 320]) for i in range(0, len(pcm), 320))
    return np.frombuffer(out, "<i2").astype(float)


def _rms_db(a):
    return 20 * np.log10(np.sqrt(np.mean(a * a)) / 32768 + 1e-12)


def test_agc_levels_and_limiter():
    a = DEFAULTS["audio"]
    for net in ("frn", "dmr", "zello"):
        for amp in (600, 3000, 30000):                 # −35, −21, −1 dBFS Spitze
            c = chain_from(a, net, "in")
            y = _run(c, np.sin(2 * np.pi * 700 * T) * amp)
            tail = y[8000:]
            assert abs(_rms_db(tail) - a["in_target_dbfs"]) < 4, (net, amp, _rms_db(tail))
            assert np.max(np.abs(y)) <= 32767 * 10 ** (a["limiter_dbfs"] / 20) + 2


def test_gate_keeps_noise_down():
    c = chain_from(DEFAULTS["audio"], "dmr", "in")
    y = _run(c, np.random.default_rng(1).normal(0, 40, 16000))
    assert _rms_db(y) < -50


def test_eq_is_continuous_and_pre_lift_safe():
    eq = ToneEQ(120, 3, 2200, 2, 3000)
    x = np.sin(2 * np.pi * 3000 * T) * 8000
    whole = eq.process_f(x.copy())
    eq2 = ToneEQ(120, 3, 2200, 2, 3000)
    parts = np.concatenate([eq2.process_f(x[i:i + 160].copy()) for i in range(0, len(x), 160)])
    assert np.allclose(whole, parts)                  # keine Knackser an den Rahmengrenzen
    assert _rms_db(whole[4000:]) > _rms_db(x) + 1.5   # Mitten/Höhen angehoben
    assert PROFILES["n8schicht"]["pre"]["treble_db"] > 0
    pre = pre_chain(effective_options({"n8vocoder_profile": "n8schicht"}))
    y = _run(pre, np.sin(2 * np.pi * 3200 * T) * 32000)
    assert np.max(np.abs(y)) <= 32767 * 10 ** (-1 / 20) + 2   # Höhenanhebung übersteuert nicht


def test_agc_reset_per_talk():
    g = AGC()
    g.process_f(to_f((np.sin(2 * np.pi * 500 * T) * 300).astype("<i2").tobytes()))
    assert g.gain_db > 5
    g.reset()
    assert g.gain_db == 0
