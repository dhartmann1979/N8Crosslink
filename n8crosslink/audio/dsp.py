"""DSP-Helfer: Pegelmessung (nur Anzeige), Verstärkung, Resampling 8k <-> 16k."""
from __future__ import annotations

import math

import numpy as np

FRAME = 160            # 20 ms @ 8 kHz
FRAME_BYTES = FRAME * 2


def level_dbfs(pcm: bytes) -> float:
    if not pcm:
        return -90.0
    a = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    rms = float(np.sqrt(np.mean(a * a))) if a.size else 0.0
    return -90.0 if rms < 1 else max(-90.0, 20 * math.log10(rms / 32768.0))


class SpectrumMeter:
    """Live-Anzeige: Pegel, Spitze und Audio-Spektrum der sprechenden Station (nur Anzeige, nie zum Schalten).

    Hält die letzten ``size`` Abtastwerte (512 = 64 ms @ 8 kHz), rechnet mit Hann-Fenster eine FFT und fasst
    sie in ``bands`` logarithmisch verteilte Bänder zwischen ``f_lo`` und ``f_hi`` zusammen. Die Bänder kommen
    als ganze Zahlen 0…100 heraus (0 = −70 dB, 100 = Vollaussteuerung) – klein genug für 25 Meldungen je Sekunde.
    """

    def __init__(self, bands: int = 32, size: int = 512, rate: int = 8000,
                 f_lo: float = 120.0, f_hi: float = 3900.0, floor_db: float = -70.0) -> None:
        self.size, self.floor = size, floor_db
        self.buf = np.zeros(size, dtype=np.float32)
        self.win = np.hanning(size).astype(np.float32)
        # Vollaussteuerungs-Sinus -> 0 dB (kohärente Verstärkung Hann = 0,5)
        self.ref = (32768.0 * size / 4.0) ** 2
        freqs = np.fft.rfftfreq(size, 1.0 / rate)
        edges = np.geomspace(f_lo, f_hi, bands + 1)
        self.idx: list[tuple[int, int]] = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            a, b = int(np.searchsorted(freqs, lo)), int(np.searchsorted(freqs, hi))
            if b <= a:                       # schmales Band unten: nächstgelegenen Bin nehmen
                a = int(np.argmin(np.abs(freqs - (lo + hi) / 2)))
                b = a + 1
            self.idx.append((a, b))
        self.edges = [round(float(e)) for e in edges]
        self.level, self.peak = -90.0, -90.0

    def reset(self) -> None:
        self.buf[:] = 0
        self.level, self.peak = -90.0, -90.0

    def push(self, pcm: bytes) -> None:
        a = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        if not a.size:
            return
        if a.size >= self.size:
            self.buf[:] = a[-self.size:]
        else:
            self.buf[:-a.size] = self.buf[a.size:]
            self.buf[-a.size:] = a
        rms = float(np.sqrt(np.mean(a * a)))
        self.level = -90.0 if rms < 1 else max(-90.0, 20 * math.log10(rms / 32768.0))
        pk = float(np.max(np.abs(a)))
        self.peak = -90.0 if pk < 1 else max(-90.0, 20 * math.log10(pk / 32768.0))

    def bands(self) -> list[int]:
        spec = np.fft.rfft(self.buf * self.win)
        pw = (spec.real * spec.real + spec.imag * spec.imag) / self.ref
        out = []
        for a, b in self.idx:
            v = float(np.max(pw[a:b]))
            db = 10 * math.log10(v) if v > 1e-12 else -120.0
            out.append(int(max(0, min(100, round((db - self.floor) / -self.floor * 100)))))
        return out


def gain(pcm: bytes, db: float) -> bytes:
    if not db:
        return pcm
    a = np.frombuffer(pcm, dtype="<i2").astype(np.float32) * (10 ** (db / 20.0))
    return np.clip(a, -32767, 32767).astype("<i2").tobytes()


def _lowpass(taps: int = 33, cutoff: float = 0.23) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff * n) * np.hamming(taps)
    return (h / h.sum()).astype(np.float32)


class Resampler:
    """Ganzzahliges Resampling (Faktor 2) mit FIR-Tiefpass und Zustand zwischen Blöcken."""

    def __init__(self, up: bool) -> None:
        self.up = up
        self.h = _lowpass()
        self.hist = np.zeros(len(self.h) - 1, dtype=np.float32)

    def process(self, pcm: bytes) -> bytes:
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        if self.up:
            z = np.zeros(x.size * 2, dtype=np.float32)
            z[::2] = x * 2.0
            x = z
        buf = np.concatenate([self.hist, x])
        y = np.convolve(buf, self.h, mode="valid")
        self.hist = buf[-(len(self.h) - 1):]
        if not self.up:
            y = y[::2]
        return np.clip(y, -32767, 32767).astype("<i2").tobytes()


class FrameBuffer:
    """Sammelt beliebig lange PCM-Stücke und gibt feste Rahmen zurück."""

    def __init__(self, frame_bytes: int = FRAME_BYTES) -> None:
        self.n = frame_bytes
        self.buf = bytearray()

    def push(self, pcm: bytes) -> list[bytes]:
        self.buf.extend(pcm)
        out = []
        while len(self.buf) >= self.n:
            out.append(bytes(self.buf[:self.n]))
            del self.buf[:self.n]
        return out

    def flush(self, pad: bool = True) -> bytes | None:
        if not self.buf:
            return None
        data = bytes(self.buf) + (bytes(self.n - len(self.buf)) if pad else b"")
        self.buf.clear()
        return data

    def __len__(self) -> int:
        return len(self.buf)


class BandwidthExtender:
    """Ergänzt das Band oberhalb der AMBE+2-Grenze (≈ 3,65 kHz) bis 4 kHz.

    AMBE+2 überträgt Obertöne nur bis ca. 3,65–3,7 kHz. Für mehr „Luft“ bei Zischlauten
    wird das Band 3,65–4 kHz mit Rauschen gefüllt, dessen Hüllkurve dem Band 3,0–3,65 kHz
    folgt (``level_db`` relativ dazu, ausblendend zur Obergrenze). Arbeitet rahmenweise
    (160 Samples) mit 50 % Überlappung (Wurzel-Hann), Latenz 20 ms."""

    N = 320
    H = 160

    def __init__(self, level_db: float = -6.0, seed: int = 0) -> None:
        self.g = 10 ** (level_db / 20)
        n = np.arange(self.N)
        self.win = np.sqrt(0.5 - 0.5 * np.cos(2 * np.pi * n / self.N))     # periodisch, Summe² = 1
        f = np.fft.rfftfreq(self.N, 1 / 8000)
        self.src = (f >= 3000) & (f < 3650)
        self.dst = (f >= 3650) & (f < 4000)
        self.fade = np.linspace(1.0, 0.35, int(self.dst.sum()))   # fällt zur Obergrenze wie natürliche Sprache
        self.rng = np.random.default_rng(seed)
        self.inbuf = np.zeros(self.N)
        self.ola = np.zeros(self.N)

    def reset(self) -> None:
        self.inbuf[:] = 0
        self.ola[:] = 0

    def process(self, pcm: bytes) -> bytes:
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
        self.inbuf = np.concatenate([self.inbuf[self.H:], x])
        X = np.fft.rfft(self.inbuf * self.win)
        e = np.sqrt(np.mean(np.abs(X[self.src]) ** 2))
        ph = np.exp(1j * self.rng.uniform(0, 2 * np.pi, int(self.dst.sum())))
        X[self.dst] = X[self.dst] + self.g * e * self.fade * ph
        y = np.fft.irfft(X, self.N) * self.win
        self.ola = np.concatenate([self.ola[self.H:], np.zeros(self.H)]) + y
        out = self.ola[:self.H]
        return np.clip(out, -32767, 32767).astype("<i2").tobytes()
