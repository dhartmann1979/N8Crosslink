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
