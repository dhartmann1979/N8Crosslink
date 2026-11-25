"""Klangaufbereitung der Bridge: schnelle AGC mit Limiter, Klangfilter (Hochpass, Präsenz, Höhen).

Alles arbeitet auf 8 kHz / 16 bit mono in Rahmen beliebiger Länge (die Bridge nutzt 20 ms = 160 Samples) und hält
seinen Zustand zwischen den Rahmen – also ohne Knackser an den Rahmengrenzen.

* ``ToneEQ``   – Hochpass (Rumpeln/Brummen weg), Präsenz-Glocke (Mitten, Verständlichkeit) und Höhen-Kuhschwanz
                 (Brillanz). RBJ-Biquads, Direktform II transponiert.
* ``AGC``      – schnelle Pegelregelung in 5-ms-Schritten: misst den RMS-Pegel, regelt mit kurzer Angriffs- und längerer
                 Rückstellzeit auf den Zielpegel, verstärkt höchstens ``max_gain_db`` und hebt Pausen/Rauschen unter der
                 Torschwelle nicht an (die Verstärkung bleibt dann stehen). Danach ein Spitzenbegrenzer (Limiter) mit
                 sofortigem Ansprechen und weicher Kennlinie knapp unter der Decke – es übersteuert nichts.
* ``Limiter``  – nur der Spitzenbegrenzer (z. B. nach einer Höhenanhebung vor dem AMBE-Encoder).
"""
from __future__ import annotations

import math

import numpy as np

RATE = 8000
SUB = 40                 # 5 ms – Regelschritt der AGC


def _db(x: float) -> float:
    return 20 * math.log10(max(x, 1e-9))


def _lin(db: float) -> float:
    return 10 ** (db / 20)


class Biquad:
    """RBJ-Biquad (Audio EQ Cookbook) mit Zustand."""

    def __init__(self, kind: str, f0: float, db: float = 0.0, q: float = 0.707) -> None:
        w = 2 * math.pi * f0 / RATE
        c, s = math.cos(w), math.sin(w)
        a = _lin(db / 2)
        if kind == "hp":
            al = s / (2 * q)
            b0, b1, b2 = (1 + c) / 2, -(1 + c), (1 + c) / 2
            a0, a1, a2 = 1 + al, -2 * c, 1 - al
        elif kind == "peak":
            al = s / (2 * q)
            b0, b1, b2 = 1 + al * a, -2 * c, 1 - al * a
            a0, a1, a2 = 1 + al / a, -2 * c, 1 - al / a
        elif kind == "shelf":                      # Höhen-Kuhschwanz, Steilheit S = 1
            al = s / 2 * math.sqrt(2)
            sa = 2 * math.sqrt(a) * al
            b0 = a * ((a + 1) + (a - 1) * c + sa)
            b1 = -2 * a * ((a - 1) + (a + 1) * c)
            b2 = a * ((a + 1) + (a - 1) * c - sa)
            a0 = (a + 1) - (a - 1) * c + sa
            a1 = 2 * ((a - 1) - (a + 1) * c)
            a2 = (a + 1) - (a - 1) * c - sa
        else:
            raise ValueError(kind)
        self.b = (b0 / a0, b1 / a0, b2 / a0)
        self.a = (a1 / a0, a2 / a0)
        self.z1 = self.z2 = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        b0, b1, b2 = self.b
        a1, a2 = self.a
        z1, z2 = self.z1, self.z2
        y = np.empty_like(x)
        for i, v in enumerate(x.tolist()):
            o = b0 * v + z1
            z1 = b1 * v - a1 * o + z2
            z2 = b2 * v - a2 * o
            y[i] = o
        self.z1, self.z2 = z1, z2
        return y


class ToneEQ:
    """Hochpass + Präsenz + Höhen. Jeder Teil fällt weg, wenn er 0 ist."""

    def __init__(self, hpf_hz: float = 0, presence_db: float = 0, presence_hz: float = 2200,
                 treble_db: float = 0, treble_hz: float = 2800) -> None:
        self.stages: list[Biquad] = []
        if hpf_hz and hpf_hz > 20:
            self.stages.append(Biquad("hp", float(hpf_hz)))
        if presence_db:
            self.stages.append(Biquad("peak", float(presence_hz), float(presence_db), 0.9))
        if treble_db:
            self.stages.append(Biquad("shelf", float(treble_hz), float(treble_db)))

    def __bool__(self) -> bool:
        return bool(self.stages)

    def process_f(self, x: np.ndarray) -> np.ndarray:
        for st in self.stages:
            x = st.process(x)
        return x


class Limiter:
    """Spitzenbegrenzer: sofortiges Ansprechen, Rückstellung ``release_ms``, weiche Kennlinie über 90 % der Decke."""

    def __init__(self, ceiling_dbfs: float = -1.0, release_ms: float = 60) -> None:
        self.ceil = 32767 * _lin(ceiling_dbfs)
        self.rel = math.exp(-SUB / (RATE * max(release_ms, 1) / 1000))
        self.g = 1.0
        self.hits = 0

    def process_f(self, x: np.ndarray) -> np.ndarray:
        out = np.empty_like(x)
        for i in range(0, len(x), SUB):
            blk = x[i:i + SUB]
            pk = float(np.max(np.abs(blk))) if blk.size else 0.0
            need = min(1.0, self.ceil / pk) if pk > 0 else 1.0
            g0 = self.g
            g1 = need if need < g0 else min(need, 1 - (1 - g0) * self.rel)
            if need < 1:
                self.hits += 1
            out[i:i + SUB] = blk * np.linspace(g0, g1, blk.size, endpoint=True) if g1 < g0 else blk * g1
            self.g = g1
        # weiche Kennlinie für einzelne Spitzen, die zwischen zwei Regelschritten durchrutschen
        knee = 0.9 * self.ceil
        over = np.abs(out) > knee
        if over.any():
            s = np.sign(out[over])
            m = np.abs(out[over]) - knee
            out[over] = s * (knee + (self.ceil - knee) * np.tanh(m / (self.ceil - knee)))
        return out


class AGC:
    """Schnelle automatische Pegelregelung mit Torschwelle und Limiter."""

    def __init__(self, target_dbfs: float = -20, max_gain_db: float = 15, max_cut_db: float = 20,
                 attack_ms: float = 10, release_ms: float = 300, gate_dbfs: float = -50,
                 ceiling_dbfs: float = -1.0) -> None:
        self.target = float(target_dbfs)
        self.max_gain = float(max_gain_db)
        self.max_cut = float(max_cut_db)
        step = SUB / RATE
        self.att = math.exp(-step / max(attack_ms / 1000, 1e-3))
        self.rel = math.exp(-step / max(release_ms / 1000, 1e-3))
        self.gate = float(gate_dbfs)
        self.limiter = Limiter(ceiling_dbfs)
        self.gain_db = 0.0
        self.gated = True

    def reset(self) -> None:
        self.gain_db = 0.0
        self.limiter.g = 1.0

    def process_f(self, x: np.ndarray) -> np.ndarray:
        out = np.empty_like(x)
        for i in range(0, len(x), SUB):
            blk = x[i:i + SUB]
            if not blk.size:
                continue
            rms = float(np.sqrt(np.mean(blk * blk)))
            lvl = _db(rms / 32768)
            g0 = self.gain_db
            self.gated = lvl < self.gate
            if not self.gated:                       # Pausen/Rauschen: Verstärkung bleibt stehen (kein „Pumpen“)
                want = max(-self.max_cut, min(self.max_gain, self.target - lvl))
                k = self.att if want < g0 else self.rel
                self.gain_db = want + (g0 - want) * k
            out[i:i + SUB] = blk * np.linspace(_lin(g0), _lin(self.gain_db), blk.size)
        return self.limiter.process_f(out)


def to_f(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float64)


def to_pcm(x: np.ndarray) -> bytes:
    return np.clip(np.round(x), -32767, 32767).astype("<i2").tobytes()


class Chain:
    """EQ → AGC (oder nur Limiter) für eine Richtung eines Netzes."""

    def __init__(self, eq: ToneEQ | None = None, agc: AGC | None = None, limiter: Limiter | None = None) -> None:
        self.eq = eq if eq else None
        self.agc = agc
        self.limiter = limiter if agc is None else None

    def __bool__(self) -> bool:
        return bool(self.eq or self.agc or self.limiter)

    def reset(self) -> None:
        if self.agc:
            self.agc.reset()

    @property
    def gain_db(self) -> float:
        return self.agc.gain_db if self.agc else 0.0

    def process(self, pcm: bytes) -> bytes:
        if not self or not pcm:
            return pcm
        x = to_f(pcm)
        if self.eq:
            x = self.eq.process_f(x)
        if self.agc:
            x = self.agc.process_f(x)
        elif self.limiter:
            x = self.limiter.process_f(x)
        return to_pcm(x)


def chain_from(cfg: dict, net: str, direction: str) -> Chain:
    """Kette für Netz ``net`` (frn/dmr/zello) und Richtung ``in`` (vom Netz) oder ``out`` (ins Netz) aus der
    Konfiguration ``audio``."""
    a = cfg or {}
    eq = None
    if direction == "in" and net == "frn":            # FRN (GSM 6.10) klingt dumpf: Rumpeln weg, Mitten und Höhen vor
        eq = ToneEQ(a.get("frn_hpf_hz", 120), a.get("frn_presence_db", 3), 2200, a.get("frn_treble_db", 2), 3000)
    elif direction == "in" and a.get("in_hpf_hz"):
        eq = ToneEQ(a.get("in_hpf_hz", 0))
    agc = None
    if a.get(f"agc_{direction}_{net}", False):
        agc = AGC(a.get(f"{direction}_target_dbfs", -20 if direction == "in" else -18), a.get("agc_max_gain_db", 15),
                  a.get("agc_max_cut_db", 20), a.get("agc_attack_ms", 10), a.get("agc_release_ms", 300),
                  a.get("agc_gate_dbfs", -50), a.get("limiter_dbfs", -1.0))
    elif eq:
        return Chain(eq, None, Limiter(a.get("limiter_dbfs", -1.0)))
    return Chain(eq, agc)
