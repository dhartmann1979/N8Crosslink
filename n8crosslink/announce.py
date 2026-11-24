"""Sprachansage des Rufzeichens am Anfang eines Durchgangs (optional, Standard aus).

Erzeugt die Ansage mit espeak-ng (offline, kein Zusatzdienst), wandelt sie auf
8 kHz / 16 Bit mono und speist sie über ``Feed`` vor dem eigentlichen Ton in das
Ziel ein. ``Feed`` gibt im 20-ms-Takt aus: zuerst die Ansage, danach den
mitgepufferten Live-Ton – das Ziel bekommt also einen gleichmäßigen Strom und
der ganze Durchgang läuft um die Länge der Ansage verzögert.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import time
import wave
from collections import OrderedDict, deque

import numpy as np

log = logging.getLogger("announce")

FRAME = 320                      # 20 ms @ 8 kHz, 16 Bit
NATO_DE = {
    "A": "Alfa", "B": "Bravo", "C": "Charlie", "D": "Delta", "E": "Echo", "F": "Foxtrott", "G": "Golf",
    "H": "Hotel", "I": "India", "J": "Juliett", "K": "Kilo", "L": "Lima", "M": "Mike", "N": "November",
    "O": "Oscar", "P": "Papa", "Q": "Quebec", "R": "Romeo", "S": "Sierra", "T": "Tango", "U": "Uniform",
    "V": "Victor", "W": "Whiskey", "X": "X-Ray", "Y": "Yankee", "Z": "Zulu",
    "0": "Null", "1": "Eins", "2": "Zwo", "3": "Drei", "4": "Vier", "5": "Fünf", "6": "Sechs",
    "7": "Sieben", "8": "Acht", "9": "Neun", "/": "Strich",
}


def available() -> bool:
    return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None


def speech_text(callsign: str, name: str, cfg: dict) -> str:
    """Text der Ansage. Rufzeichen je nach Einstellung Zeichen für Zeichen oder im NATO-Alphabet."""
    cs = re.sub(r"[^A-Za-z0-9/]", "", callsign or "").upper()
    if cs:
        if cfg.get("announce_spell", "letters") == "nato":
            spoken = ", ".join(NATO_DE.get(c, c) for c in cs)
        else:
            spoken = " ".join(cs)
    else:
        spoken = re.sub(r"[^\w .-]", " ", name or "")[:40].strip()
    tpl = str(cfg.get("announce_text") or "{call}")
    first = (name or "").split()
    op = " ".join(first[1:]) if cs and first and first[0].upper() == cs else (name or "")
    return tpl.replace("{call}", spoken).replace("{name}", op[:30]).strip()


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(x) == 0:
        return x
    n = int(round(len(x) * dst / src))
    X = np.fft.rfft(x)
    keep = n // 2 + 1
    Y = np.zeros(keep, dtype=complex)
    m = min(keep, len(X))
    Y[:m] = X[:m]
    # weicher Übergang an der neuen Bandgrenze (gegen Klingeln)
    edge = max(1, m // 20)
    Y[m - edge:m] *= np.linspace(1, 0, edge)
    return np.fft.irfft(Y, n) * (n / len(x))


def synth(text: str, cfg: dict) -> bytes:
    """Text -> PCM 8 kHz s16le. Leer bei Fehler."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe or not text:
        return b""
    import subprocess
    voice = str(cfg.get("announce_voice") or "de")
    speed = int(cfg.get("announce_speed") or 150)
    try:
        wav = subprocess.run([exe, "-v", voice, "-s", str(speed), "--stdout", text],
                             capture_output=True, timeout=10, check=True).stdout
        with wave.open(io.BytesIO(wav)) as w:
            rate, ch = w.getframerate(), w.getnchannels()
            raw = w.readframes(w.getnframes())
    except Exception as e:  # noqa: BLE001
        log.warning("Ansage: espeak-ng fehlgeschlagen: %s", e)
        return b""
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    y = _resample(x, rate, 8000)
    # auf Ziel-Pegel normalisieren (Spitze), Stille am Ende kürzen, kurze Pause anhängen
    peak = float(np.abs(y).max() or 1.0)
    target = 32767 * 10 ** (float(cfg.get("announce_level_db", -6.0)) / 20)
    y = y * (target / peak)
    nz = np.nonzero(np.abs(y) > 200)[0]
    if len(nz):
        y = y[max(0, nz[0] - 160):nz[-1] + 160]
    y = np.concatenate([y, np.zeros(int(8000 * float(cfg.get("announce_pause_ms", 250)) / 1000))])
    pad = (-len(y)) % 160
    y = np.concatenate([y, np.zeros(pad)])
    return np.clip(y, -32767, 32767).astype("<i2").tobytes()


class Announcer:
    def __init__(self) -> None:
        self.cache: "OrderedDict[str, bytes]" = OrderedDict()
        self.last: dict[tuple[str, str], float] = {}

    def wanted(self, target_key: str, talker, cfg: dict) -> bool:  # noqa: ANN001
        if not cfg.get("announce_enabled") or not cfg.get(f"announce_{target_key}"):
            return False
        if not (talker.callsign or (cfg.get("announce_without_call") and talker.name)):
            return False
        rep = float(cfg.get("announce_repeat_min", 0) or 0)
        key = (target_key, (talker.callsign or talker.name).upper())
        if rep > 0 and time.time() - self.last.get(key, 0) < rep * 60:
            return False
        self.last[key] = time.time()
        return True

    async def pcm(self, talker, cfg: dict) -> bytes:  # noqa: ANN001
        text = speech_text(talker.callsign, talker.name, cfg)
        key = f"{text}|{cfg.get('announce_voice')}|{cfg.get('announce_speed')}|{cfg.get('announce_level_db')}|{cfg.get('announce_pause_ms')}"
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        pcm = await asyncio.get_running_loop().run_in_executor(None, synth, text, cfg)
        self.cache[key] = pcm
        while len(self.cache) > 200:
            self.cache.popitem(last=False)
        return pcm


class Feed:
    """Gibt Ansage + Live-Ton im 20-ms-Takt an ein Ziel weiter."""

    MAX_WAIT_TTS = 0.6           # so lange höchstens auf espeak warten, sonst ohne Ansage

    def __init__(self, port, pcm_future: "asyncio.Future[bytes]") -> None:  # noqa: ANN001
        self.port = port
        self.q: deque[bytes] = deque()
        self.ended = False
        self.closed = False
        self.pcm_future = pcm_future
        self.task = asyncio.ensure_future(self._run())

    def push(self, pcm: bytes) -> None:
        if len(self.q) < 3000:       # 60 s
            self.q.append(pcm)

    def end(self) -> None:
        self.ended = True

    def finish_now(self) -> None:
        """Neuer Durchgang auf demselben Ziel: Rest sofort ausgeben und beenden."""
        if self.closed:
            return
        self.task.cancel()
        while self.q:
            self._out(self.q.popleft())
        self._close()

    def _out(self, pcm: bytes) -> None:
        try:
            self.port.tx_audio(pcm)
        except Exception as e:  # noqa: BLE001
            log.exception("Ansage tx_audio %s: %s", self.port.key, e)

    def _close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.ended:
            try:
                self.port.tx_end()
            except Exception as e:  # noqa: BLE001
                log.exception("Ansage tx_end %s: %s", self.port.key, e)

    async def _run(self) -> None:
        try:
            try:
                ann = await asyncio.wait_for(asyncio.shield(self.pcm_future), self.MAX_WAIT_TTS)
            except asyncio.TimeoutError:
                ann = b""
            frames = deque(ann[i:i + FRAME] for i in range(0, len(ann), FRAME))
            loop = asyncio.get_running_loop()
            t = loop.time()
            while True:
                if frames:
                    self._out(frames.popleft())
                elif self.q:
                    self._out(self.q.popleft())
                elif self.ended:
                    break
                t += 0.02
                await asyncio.sleep(max(0.0, t - loop.time()))
            self._close()
        except asyncio.CancelledError:
            pass
