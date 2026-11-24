"""Probehören und Messen des N8schicht-Vocoders: Ton → AMBE+2 (DMR) → Ton.

Wird vom Adminportal (Popup „Klang-Einstellungen“ → Probehören) und von
``tools/vocoder_test.py`` benutzt. Läuft mit einem eigenen Vocoder-Prozess, stört
also den laufenden Betrieb nicht.
"""
from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import wave

import numpy as np

from .announce import _resample
from .audio.dsp import BandwidthExtender
from .dmr.burst import AMBE_SILENCE
from .vocoder import N8VocoderWorker, effective_options, find_n8vocoder_lib

MAX_SECONDS = 30
BANDS = [(100, 300), (300, 1000), (1000, 2000), (2000, 3000), (3000, 3500), (3500, 3800), (3800, 4000)]
TEST_TEXT = ("Hallo in die Runde, hier ist Delta Lima eins Alpha Bravo Charlie aus Minden. "
             "Sieben, acht, neun, zehn – Zahlen und Zischlaute sind über Funk oft schwer zu verstehen.")


class PreviewError(Exception):
    pass


def wav_to_pcm8k(raw: bytes) -> np.ndarray:
    """WAV (8/16/24/32 Bit, mono/stereo, beliebige Abtastrate) -> int16 @ 8 kHz mono."""
    try:
        with wave.open(io.BytesIO(raw)) as w:
            rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
            data = w.readframes(min(w.getnframes(), rate * MAX_SECONDS))
    except (wave.Error, EOFError) as e:
        raise PreviewError(f"Keine gültige WAV-Datei ({e})") from e
    if sw == 1:
        x = (np.frombuffer(data, np.uint8).astype(np.float32) - 128) * 256
    elif sw == 2:
        x = np.frombuffer(data, "<i2").astype(np.float32)
    elif sw == 3:
        b = np.frombuffer(data, np.uint8).reshape(-1, 3)
        x = ((b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
             << 8 >> 8).astype(np.float32) / 256
    elif sw == 4:
        x = np.frombuffer(data, "<i4").astype(np.float32) / 65536
    else:
        raise PreviewError("Nicht unterstütztes WAV-Format")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    y = _resample(x, rate, 8000)
    return np.clip(y, -32767, 32767).astype(np.int16)


def speak(text: str) -> np.ndarray:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise PreviewError("espeak-ng ist nicht installiert – eigene WAV-Datei hochladen")
    voice = "mb-de6" if os.path.isdir("/usr/share/mbrola/de6") else "de"
    wav = subprocess.run([exe, "-v", voice, "-s", "150", "--stdout", text[:400]],
                         capture_output=True, timeout=20, check=True).stdout
    x = wav_to_pcm8k(wav).astype(np.float32)
    x = x / (np.sqrt(np.mean(x ** 2)) + 1e-9) * 32767 * 10 ** (-20 / 20)       # -20 dBFS RMS
    return np.clip(x, -32767, 32767).astype(np.int16)


def to_wav(pcm: np.ndarray, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype("<i2").tobytes())
    return buf.getvalue()


async def process(pcm: np.ndarray, options: dict, lib: str | None = None) -> np.ndarray:
    """Ganze Aufnahme durch Encoder und Decoder schicken (wie FRN/Zello → DMR → FRN/Zello)."""
    lib = lib or find_n8vocoder_lib()
    if not lib:
        raise PreviewError("N8schicht-Vocoder ist nicht gebaut")
    n = len(pcm) // 160 * 160
    x = np.concatenate([pcm[:n], np.zeros(320, np.int16)])        # 2 Rahmen Encoder-Verzögerung
    w = N8VocoderWorker(lib, options)
    try:
        frames = []
        for i in range(len(x) // 160):
            a = await w.call(b"E", x[i * 160:(i + 1) * 160].tobytes(), 5.0)
            if a is None:
                raise PreviewError("Vocoder-Prozess antwortet nicht")
            frames.append(a)
        out = []
        db = float((options.get("post") or {}).get("bwe_db", -40))
        bwe = BandwidthExtender(db) if db > -40 else None
        for a in frames[2:] + [AMBE_SILENCE]:          # 1 Rahmen mehr: Latenz der Höhen-Ergänzung
            d = await w.call(b"D", a, 5.0)
            p = d[1:] if d else bytes(320)
            out.append(np.frombuffer(bwe.process(p) if bwe else p, "<i2"))
        y = np.concatenate(out) if out else np.zeros(0, np.int16)
        return y[160:] if bwe else y[:-160]
    finally:
        await w.close()


def align(ref: np.ndarray, deg: np.ndarray, max_lag: int = 1600) -> tuple[np.ndarray, np.ndarray, int]:
    r = ref.astype(np.float64)
    g = deg.astype(np.float64)
    n = 1 << int(np.ceil(np.log2(len(r) + len(g) + 1)))
    c = np.fft.irfft(np.fft.rfft(g, n) * np.conj(np.fft.rfft(r, n)), n)
    lag = int(np.argmax(c[:max_lag]))
    g = g[lag:]
    m = min(len(r), len(g))
    return r[:m], g[:m], lag


def _band_db(x: np.ndarray, edges: list[tuple[int, int]]) -> np.ndarray:
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / 8000)
    return np.array([10 * np.log10(X[(f >= a) & (f < b)].sum() + 1e-9) for a, b in edges])


def metrics(ref: np.ndarray, deg: np.ndarray) -> dict:
    r, g, lag = align(ref, deg)
    if len(r) < 1600:
        return {}
    bi, bo = _band_db(r, BANDS), _band_db(g, BANDS)
    dev = (bo - bo[1]) - (bi - bi[1])           # Abweichung je Band, bezogen auf 300–1000 Hz
    fine = [(f, f + 100) for f in range(2000, 4000, 100)]
    fi, fo = _band_db(r, fine), _band_db(g, fine)
    ref_lvl = _band_db(r, [(300, 1000)])[0], _band_db(g, [(300, 1000)])[0]
    upper = 2000
    for (a, b), di, do in zip(fine, fi, fo):
        if (do - ref_lvl[1]) - (di - ref_lvl[0]) > -6:
            upper = b
        else:
            break
    rms = lambda v: 20 * np.log10(np.sqrt(np.mean(v ** 2)) / 32767 + 1e-12)  # noqa: E731
    out = {"delay_ms": round(lag / 8, 1), "level_in_dbfs": round(float(rms(r)), 1),
           "level_out_dbfs": round(float(rms(g)), 1), "bandwidth_hz": int(upper),
           "bands": [{"from": a, "to": b, "dev_db": round(float(d), 1)} for (a, b), d in zip(BANDS, dev)]}
    try:                                         # optional: objektive Maße, falls installiert
        from pystoi import stoi
        out["estoi"] = round(float(stoi(r, g, 8000, extended=True)), 3)
    except Exception:  # noqa: BLE001
        pass
    try:
        from pesq import pesq
        out["pesq_nb"] = round(float(pesq(8000, r, g, "nb")), 2)
    except Exception:  # noqa: BLE001
        pass
    return out


async def run(data: dict, vcfg: dict) -> dict:
    if data.get("wav"):
        try:
            pcm = wav_to_pcm8k(base64.b64decode(str(data["wav"]).split(",")[-1]))
        except (ValueError, TypeError) as e:
            raise PreviewError("WAV-Datei nicht lesbar") from e
    else:
        pcm = speak(str(data.get("text") or TEST_TEXT))
    if len(pcm) < 1600:
        raise PreviewError("Aufnahme zu kurz (mindestens 0,2 s)")
    cfg = dict(vcfg)
    if data.get("profile"):
        cfg["n8vocoder_profile"] = data["profile"]
    if data.get("options") is not None:
        cfg["n8vocoder_options"] = data["options"]
    out = await process(pcm, effective_options(cfg), vcfg.get("n8vocoder_lib") or None)
    return {"orig": base64.b64encode(to_wav(pcm)).decode(), "out": base64.b64encode(to_wav(out)).decode(),
            "metrics": metrics(pcm, out), "seconds": round(len(pcm) / 8000, 1)}
