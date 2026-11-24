"""AMBE+2-Vocoder für DMR.

Betriebsarten, im Adminportal wählbar:

* ``n8vocoder``   – N8schicht-Vocoder: Software-AMBE+2 (Fork des DroidStar-Codecs, Quellen in
                   ``third_party/n8schicht-vocoder``), gebaut als ``lib/libn8vocoder.so``, läuft in
                   einem eigenen Prozess (``ambe_worker``) – kein Zusatzdienst, kein qemu
* ``usb``        – AMBE3000-USB-Stick (ThumbDV, DVstick 30, DV3000) direkt seriell
                   (Standard /dev/ttyUSB0, 460800 Baud)
* ``ambeserver`` – AMBE3000 hinter einem AMBEserver (UDP, Standard 2460)
* ``none``       – nur für Tests: liefert Stille

USB-Stick und AMBEserver sprechen das AMBE3000-Paketformat (0x61, Länge, Typ, Felder). DMR nutzt
Rate 33 (AMBE+2 3600/2450). Ein Sprachrahmen = 20 ms = 160 Samples @ 8 kHz;
ein AMBE-Rahmen = 72 Bit = 9 Byte (so wie er im DMR-Burst steht).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import sys
import threading
import time
from collections import deque

import numpy as np

from .audio.dsp import BandwidthExtender
from .dmr.burst import AMBE_SILENCE

log = logging.getLogger("vocoder")

PKT_START = 0x61
TYPE_CONTROL = 0x00
TYPE_CHANNEL = 0x01
TYPE_SPEECH = 0x02

SILENCE_PCM = bytes(320)


def _packet(ptype: int, payload: bytes) -> bytes:
    return struct.pack(">BHB", PKT_START, len(payload), ptype) + payload


def channel_packet(ambe9: bytes) -> bytes:
    return _packet(TYPE_CHANNEL, bytes([0x01, 72]) + ambe9)


def speech_packet(pcm_le: bytes) -> bytes:
    be = np.frombuffer(pcm_le, dtype="<i2").astype(">i2").tobytes()
    return _packet(TYPE_SPEECH, bytes([0x00, 160]) + be)


PKT_RESET = _packet(TYPE_CONTROL, b"\x33")
PKT_PRODID = _packet(TYPE_CONTROL, b"\x30")
PKT_VERSTRING = _packet(TYPE_CONTROL, b"\x31")
PKT_RATET33 = _packet(TYPE_CONTROL, b"\x09\x21")


class _Parser:
    """Zerlegt einen Bytestrom in AMBE3000-Pakete (für die serielle Variante)."""

    def __init__(self) -> None:
        self.buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buf.extend(data)
        out = []
        while True:
            while self.buf and self.buf[0] != PKT_START:
                self.buf.pop(0)
            if len(self.buf) < 4:
                break
            length = (self.buf[1] << 8) | self.buf[2]
            if length > 400:
                self.buf.pop(0)
                continue
            if len(self.buf) < 4 + length:
                break
            out.append(bytes(self.buf[:4 + length]))
            del self.buf[:4 + length]
        return out


LIB_NAME = "libn8vocoder.so"
LEGACY_LIBS = ("libambe2.so",)
SOFT_MODES = ("n8vocoder",)


def find_n8vocoder_lib(cfg: dict | None = None) -> str | None:
    """Sucht die gebaute N8schicht-Vocoder-Bibliothek."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands = [(cfg or {}).get("n8vocoder_lib") or "", os.environ.get("N8X_AMBE_LIB", "")]
    for name in (LIB_NAME, *LEGACY_LIBS):
        cands += [os.path.join(here, "lib", name), "/opt/n8crosslink/lib/" + name]
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


find_droidstar_lib = find_n8vocoder_lib          # alter Name (Tests, Fremdskripte)

# ------------------------------------------------------------------ Klang-Einstellungen
# Abstimmung „N8schicht“: Grundlage mit STOI/PESQ an deutschen Testsätzen gemessen (docs/VOCODER.md),
# seit 1.9.1 im Livebetrieb nach Gehör nachgeschärft (etwas lauter, heller, klarer, robuster bei Bitfehlern).
PROFILES = {
    "n8schicht": {"dec": {"output_gain": 2.2, "frame_limiter": 0, "high_band_tilt": 0.9,
                          "high_band_start": 0.6, "enhance_strength": 0.65, "pitch_glide_end": 120,
                          "voicing_off_end": 80, "repeat_max": 4},
                  "enc": {"highpass_hz": 150},
                  "post": {"bwe_db": 0.0}},
    "droidstar": {"dec": {}, "enc": {}, "post": {}},
}
# Regler im Adminportal: Seite, Schlüssel, Bezeichnung, min, max, Schritt, Grundwert DroidStar, Erklärung
PARAMS = [
    ("dec", "output_gain", "Lautstärke (Ausgang)", 0.5, 3.0, 0.01, 2.07,
     "Verstärkung aller Obertöne beim Dekodieren (DMR → FRN/Zello). Zu hoch = Übersteuerung, zu niedrig = leise."),
    ("dec", "frame_limiter", "Kompressor (Frame-Limiter)", 0, 1, 1, 1,
     "Drückt laute Rahmen zusammen. Aus = natürlichere Dynamik, weniger „komprimierter“ Klang (N8schicht: aus)."),
    ("dec", "high_band_tilt", "Höhen anheben (Brillanz)", 0.0, 1.5, 0.05, 0.5,
     "Hebt die oberen Obertöne an (log2 an der Obergrenze). 0,8 ergibt einen glatten Frequenzgang bis ≈ 3,8 kHz, "
     "mehr = heller (N8schicht: 0,9)."),
    ("dec", "high_band_start", "Höhen ab (Anteil der Obertöne)", 0.3, 0.9, 0.01, 0.66,
     "Ab welchem Teil der Obertöne die Höhenanhebung beginnt (0,66 = oberes Drittel)."),
    ("dec", "enhance_strength", "Klarheit (Formantverstärkung)", 0.0, 1.0, 0.01, 0.61,
     "Betont die Formanten (Vokalklang). 0 = dumpf/verwaschen, zu hoch = scharf/blechern."),
    ("dec", "pitch_glide_end", "Tonhöhen-Übergang (Samples)", 40, 160, 1, 160,
     "Interpolation der Grundfrequenz von Rahmen zu Rahmen. Kürzer = folgt der Sprachmelodie schneller (N8schicht: 120)."),
    ("dec", "amplitude_glide_end", "Lautstärke-Übergang (Samples)", 40, 160, 1, 160,
     "Interpolation der Obertonpegel zwischen zwei Rahmen. Kürzer = härtere Übergänge."),
    ("dec", "voicing_off_end", "Übergang stimmhaft → stimmlos (Samples)", 10, 140, 1, 50,
     "Wie weich ein Oberton ausblendet, wenn er stimmlos wird (z. B. von Vokal zu „s“). Länger = natürlicher (N8schicht: 80)."),
    ("dec", "voicing_on_end", "Übergang stimmlos → stimmhaft (Samples)", 60, 160, 1, 90,
     "Wie weich ein Oberton einblendet, wenn er stimmhaft wird."),
    ("dec", "phase_dispersion", "Phasenstreuung", 0.0, 0.6, 0.01, 0.3,
     "Streut die Phasen der Obertöne. Wenig = „summend“, viel = rauer. Grundwert passt meist."),
    ("dec", "unvoiced_gain", "Zischlaute / Rauschanteil", 0.4, 1.3, 0.01, 0.85,
     "Pegel der stimmlosen Anteile (s, f, sch, t). Höher = deutlichere Konsonanten, aber mehr Rauschen."),
    ("dec", "comfort_noise_level", "Komfortrauschen bei Ausfall", 0.0, 3.0, 0.1, 1.0,
     "Leises Rauschen statt harter Stille, wenn Rahmen wegen Funkfehlern ausfallen."),
    ("dec", "repeat_max", "Fehlerrahmen überbrücken", 0, 8, 1, 3,
     "So viele kaputte Rahmen werden durch Wiederholen des letzten guten überbrückt, danach Stummschalten."),
    ("post", "bwe_db", "Höhen-Ergänzung 3,65–4 kHz (dB, −40 = aus)", -40, 6, 1, -40,
     "AMBE+2 endet bei ≈ 3,65 kHz. Füllt das Band bis 4 kHz mit Rauschen nach der Hüllkurve von 3,0–3,65 kHz "
     "(mehr „Luft“ bei s/z/f). Pegel relativ zu diesem Band; −40 = aus (N8schicht: 0)."),
    ("enc", "highpass_hz", "Tiefen-Filter vor dem Kodieren (Hz)", 0, 300, 5, 135,
     "Entfernt Brummen und Rumpeln vor dem Kodieren (FRN/Zello → DMR). 0 = aus; höher = dünner, aber oft klarer."),
    ("enc", "gate_level_db", "Rauschsperre (dBFS)", -90, -30, 1, -70,
     "Rahmen leiser als dieser Pegel werden als Stille gesendet. Höher = unterdrückt Hintergrundrauschen stärker."),
    ("enc", "smooth_previous", "Glättung (vorheriger Rahmen)", 0.0, 0.3, 0.01, 0.05,
     "Mischt die Obertonpegel des vorigen Rahmens bei – ruhiger, aber verwaschener."),
]


def effective_options(cfg: dict) -> dict:
    """Profil + eigene Werte aus dem Adminportal -> {"enc": {...}, "dec": {...}}."""
    prof = PROFILES.get(str(cfg.get("n8vocoder_profile") or "n8schicht"), PROFILES["n8schicht"])
    own = cfg.get("n8vocoder_options") or {}
    keys = {(side, k) for side, k, *_ in PARAMS}
    out = {"enc": dict(prof["enc"]), "dec": dict(prof["dec"]), "post": dict(prof.get("post", {}))}
    for side in ("enc", "dec", "post"):
        for k, v in (own.get(side) or {}).items():
            if (side, k) in keys:
                out[side][k] = float(v)
    return out


def params_for_ui(cfg: dict) -> list[dict]:
    eff = effective_options(cfg)
    out = []
    for side, k, label, lo, hi, step, base, help_ in PARAMS:
        prof = PROFILES["n8schicht"].get(side, {}).get(k, base)
        out.append({"side": side, "key": k, "label": label, "min": lo, "max": hi, "step": step,
                    "droidstar": base, "n8schicht": prof, "value": eff.get(side, {}).get(k, base), "help": help_})
    return out


class N8VocoderWorker:
    """Client für ``n8crosslink.ambe_worker`` – der Codec läuft in einem eigenen Prozess.

    Alle Aufrufe laufen nacheinander (Lock, FIFO). Antwortet der Prozess nicht oder ist er
    abgestürzt, wird er beendet und beim nächsten Aufruf neu gestartet."""

    def __init__(self, lib: str, options: dict) -> None:
        self.lib = lib
        self.options = options
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.version = ""
        self.restarts = 0
        self.bad_options: list[str] = []

    async def _spawn(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "n8crosslink.ambe_worker", self.lib,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        r = await self._xfer(b"O", json.dumps(self.options).encode(), 10.0)
        if r is not None:
            self.bad_options = json.loads(r or b"{}").get("bad", [])
            if self.bad_options:
                log.warning("N8schicht-Vocoder: unbekannte Optionen %s", self.bad_options)
        v = await self._xfer(b"V", b"", 5.0)
        self.version = (v or b"").decode(errors="replace")

    async def _xfer(self, op: bytes, data: bytes, timeout: float) -> bytes | None:
        p = self.proc
        if p is None or p.returncode is not None:
            return None
        try:
            p.stdin.write(op + struct.pack(">H", len(data)) + data)
            await p.stdin.drain()
            hdr = await asyncio.wait_for(p.stdout.readexactly(3), timeout)
            n = struct.unpack(">H", hdr[1:3])[0]
            return await asyncio.wait_for(p.stdout.readexactly(n), timeout) if n else b""
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, BrokenPipeError, ConnectionResetError) as e:
            log.error("N8schicht-Vocoder: Prozess antwortet nicht (%s) – wird neu gestartet", type(e).__name__)
            await self._kill()
            return None

    async def _kill(self) -> None:
        p, self.proc = self.proc, None
        if p is not None and p.returncode is None:
            try:
                p.kill()
                await asyncio.wait_for(p.wait(), 2)
            except (ProcessLookupError, asyncio.TimeoutError):
                pass

    async def call(self, op: bytes, data: bytes = b"", timeout: float = 2.0) -> bytes | None:
        async with self.lock:
            if self.proc is None or self.proc.returncode is not None:
                if self.proc is not None or self.version:
                    self.restarts += 1
                await self._kill()
                await self._spawn()
            return await self._xfer(op, data, timeout)

    async def set_options(self, options: dict) -> list[str]:
        self.options = options
        r = await self.call(b"O", json.dumps(options).encode(), 5.0)
        self.bad_options = json.loads(r or b"{}").get("bad", []) if r is not None else ["Prozess"]
        return self.bad_options

    async def close(self) -> None:
        async with self.lock:
            p = self.proc
            if p is not None and p.returncode is None:
                try:
                    p.stdin.close()
                    await asyncio.wait_for(p.wait(), 2)
                except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError):
                    pass
            await self._kill()


class Vocoder:
    def __init__(self, cfg: dict) -> None:
        mode = cfg.get("vocoder_mode", "n8vocoder")
        # md380-emu (bis 1.3) und „droidstar“ (1.4–1.5) heißen jetzt N8schicht-Vocoder
        self.mode = "n8vocoder" if mode in ("md380", "droidstar") else mode
        self.cfg = cfg
        self.loop: asyncio.AbstractEventLoop | None = None
        self.enc_q: deque[asyncio.Future] = deque()
        self.dec_q: deque[asyncio.Future] = deque()
        self.ctrl_q: deque[asyncio.Future] = deque()
        self.transport = None
        self.serial = None
        self.write_q: "deque[bytes]" = deque()
        self.write_evt = threading.Event()
        self.running = False
        self.online = False
        self.product = ""
        self.version = ""
        self.stats = {"enc": 0, "dec": 0, "timeouts": 0, "errors": 0, "reopens": 0,
                      "late": 0, "retries": 0, "restarts": 0, "erasures": 0}
        self.consec_timeouts = 0
        # UDP (AMBEserver): strikt eine Anfrage nach der anderen, damit eine
        # verspätete Antwort nie der falschen Anfrage zugeordnet wird.
        self.lockstep = self.mode == "ambeserver"
        self.codec: N8VocoderWorker | None = None
        self.bwe: BandwidthExtender | None = None
        self._req_lock = asyncio.Lock()
        self._drain_until = 0.0
        self._renew = False
        self._udp_addr = None
        self.last_rx = 0.0
        self.offline_since: float | None = time.time()
        self._lock = asyncio.Lock()
        self.enc_gain = float(cfg.get("vocoder_enc_gain_db", 0.0))
        self.dec_gain = float(cfg.get("vocoder_dec_gain_db", 0.0))

    # ------------------------------------------------------------------ setup
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.running = True
        try:
            if self.mode == "n8vocoder":
                lib = find_n8vocoder_lib(self.cfg)
                if not lib:
                    raise RuntimeError("N8schicht-Vocoder nicht gebaut – Admin → Vocoder → „Vocoder bauen“ "
                                       "oder sudo /opt/n8crosslink/install.sh --build-vocoder")
                eff = effective_options(self.cfg)
                self.codec = N8VocoderWorker(lib, eff)
                self._set_post(eff)
                pcm = await self.decode(AMBE_SILENCE)
                self.product = ""
                self.version = self.codec.version
                self.online = pcm is not None and len(pcm) == 320
                log.info("N8schicht-Vocoder (%s, %s) bereit: %s", lib, self.version, self.online)
                return
            if self.mode == "ambeserver":
                host = self.cfg.get("ambeserver_host", "127.0.0.1")
                port = int(self.cfg.get("ambeserver_port", 2460))
                self._udp_addr = (host, port)
                await self._open_udp()
                log.info("Vocoder %s über UDP %s:%s", self.mode, host, port)
            elif self.mode == "usb":
                import serial  # pyserial
                dev = self.cfg.get("usb_device", "/dev/ttyUSB0")
                baud = int(self.cfg.get("usb_baud", 460800))
                self.serial = serial.Serial(dev, baud, timeout=0.05)
                threading.Thread(target=self._serial_reader, daemon=True).start()
                threading.Thread(target=self._serial_writer, daemon=True).start()
                log.info("Vocoder USB-Stick %s @ %s Baud", dev, baud)
            else:
                self.online = True
                self.product = "Test (Stille)"
                return
            if self._send_init():
                await self._init_chip()
            else:
                # ohne Steuerpakete: Probe-Dekodierung als Lebenszeichen
                pcm = await self.decode(AMBE_SILENCE, timeout=1.5)
                self.online = pcm is not None
                self.product = "AMBE"
        except Exception as e:  # noqa: BLE001
            self.online = False
            self.stats["errors"] += 1
            log.error("Vocoder-Start fehlgeschlagen: %s", e)
        if self.mode != "none" and (self.transport or self.serial):
            self._health_task = asyncio.create_task(self._health())

    async def _open_udp(self) -> None:
        """Neuer UDP-Socket (neuer Quellport): verspätete Antworten an den alten
        Socket können so keiner neuen Anfrage mehr zugeordnet werden."""
        old = self.transport
        self.transport, _ = await self.loop.create_datagram_endpoint(
            lambda: _UdpProto(self), remote_addr=self._udp_addr)
        if old:
            old.close()
        self._renew = False

    async def _health(self) -> None:
        """Prüft alle 20 s, ob ein ausgefallener Vocoder wieder antwortet."""
        while self.running:
            await asyncio.sleep(20)
            if not self.online or time.time() - self.last_rx > 120:
                was = self.online
                if self.mode == "usb" and self._send_init() and not was:
                    await self._init_chip()
                else:
                    self.online = (await self.decode(AMBE_SILENCE, timeout=1.0)) is not None
                if self.online and not was:
                    log.info("Vocoder wieder erreichbar")

    def _send_init(self) -> bool:
        key = {"usb": "usb_send_init", "ambeserver": "ambeserver_send_init"}[self.mode]
        return bool(self.cfg.get(key, True))

    async def _init_chip(self) -> None:
        if self.mode == "usb":
            r = await self._control(PKT_RESET, timeout=2.0)
            if r is None:
                log.warning("AMBE3000: keine Antwort auf Reset")
        await self._control(PKT_RATET33, timeout=1.0)
        prod = await self._control(PKT_PRODID, timeout=1.0)
        if prod:
            self.product = prod[5:].split(b"\x00")[0].decode(errors="replace")
        ver = await self._control(PKT_VERSTRING, timeout=1.0)
        if ver:
            self.version = ver[5:].split(b"\x00")[0].decode(errors="replace")[:40]
        pcm = await self.decode(AMBE_SILENCE, timeout=1.5)
        self.online = pcm is not None
        log.info("Vocoder bereit: %s %s (online=%s)", self.product, self.version, self.online)

    async def stop(self) -> None:
        self.running = False
        if getattr(self, "_health_task", None):
            self._health_task.cancel()
        self.online = False
        if self.codec:
            codec, self.codec = self.codec, None
            await codec.close()
        if self.transport:
            self.transport.close()
        if self.serial:
            try:
                self.serial.close()
            except Exception:  # noqa: BLE001
                pass
        for q in (self.enc_q, self.dec_q, self.ctrl_q):
            while q:
                f = q.popleft()
                if not f.done():
                    f.set_result(None)

    # ------------------------------------------------------------------ I/O
    def _write(self, data: bytes) -> None:
        if self.transport:
            self.transport.sendto(data)
        elif self.serial:
            self.write_q.append(data)
            self.write_evt.set()

    def _serial_writer(self) -> None:
        while self.running:
            self.write_evt.wait(0.5)
            self.write_evt.clear()
            while self.write_q:
                try:
                    self.serial.write(self.write_q.popleft())
                except Exception as e:  # noqa: BLE001
                    log.error("USB-Stick Schreibfehler: %s", e)
                    self.online = False
                    return

    def _serial_reader(self) -> None:
        parser = _Parser()
        while self.running:
            try:
                data = self.serial.read(512)
            except Exception as e:  # noqa: BLE001
                log.error("USB-Stick Lesefehler: %s", e)
                self.online = False
                return
            if data:
                for pkt in parser.feed(data):
                    self.loop.call_soon_threadsafe(self._on_packet, pkt)

    def _on_packet(self, pkt: bytes) -> None:
        if len(pkt) < 4 or pkt[0] != PKT_START:
            return
        self.last_rx = time.time()
        ptype = pkt[3]
        if time.time() < self._drain_until:
            # Nach einem Timeout: verspätete Antworten verwerfen, sonst verschiebt sich
            # die Zuordnung Anfrage/Antwort dauerhaft um einen Rahmen.
            self.stats["late"] += 1
            return
        if ptype == TYPE_CHANNEL:
            q = self.enc_q
            # Felder: 0x01 CHAND, Bitanzahl, Daten
            data = None
            if len(pkt) >= 6 and pkt[4] == 0x01:
                data = pkt[6:6 + (pkt[5] + 7) // 8]
        elif ptype == TYPE_SPEECH:
            q = self.dec_q
            raw = pkt[6:6 + 320] if len(pkt) >= 326 else None
            data = np.frombuffer(raw, dtype=">i2").astype("<i2").tobytes() if raw else None
        else:
            q = self.ctrl_q
            data = pkt
        while q:
            fut = q.popleft()
            if not fut.done():
                fut.set_result(data)
                return

    async def _request(self, q: deque, packet: bytes, timeout: float):
        if not self.running:
            return None
        if self.lockstep:
            async with self._req_lock:
                r = await self._request_once(q, packet, timeout)
                if r is None and self.running and self.consec_timeouts <= 3:
                    # UDP kann ein Paket verlieren – genau ein zweiter Versuch
                    self.stats["retries"] += 1
                    r = await self._request_once(q, packet, timeout)
                return r
        return await self._request_once(q, packet, timeout)

    async def _request_once(self, q: deque, packet: bytes, timeout: float):
        if self.lockstep and self._renew:
            await self._open_udp()
        wait = self._drain_until - time.time()
        if wait > 0 and not self.lockstep:
            await asyncio.sleep(wait)
        fut = self.loop.create_future()
        q.append(fut)
        self._write(packet)
        try:
            r = await asyncio.wait_for(asyncio.shield(fut), timeout)
            self.consec_timeouts = 0
            return r
        except asyncio.TimeoutError:
            self.stats["timeouts"] += 1
            self.consec_timeouts += 1
            try:
                q.remove(fut)
            except ValueError:
                pass
            if not self.lockstep:
                # USB-Stick: alle offenen Anfragen dieser Art verwerfen und neu synchronisieren
                while q:
                    f = q.popleft()
                    if not f.done():
                        f.set_result(None)
            if self.lockstep:
                self._renew = True
            else:
                self._drain_until = time.time() + 0.12
            if self.stats["timeouts"] % 50 == 1:
                log.warning("Vocoder antwortet nicht (Timeouts: %s)", self.stats["timeouts"])
            if self.consec_timeouts >= 5:
                self.online = False
            return None

    async def _control(self, packet: bytes, timeout: float = 1.0):
        return await self._request(self.ctrl_q, packet, timeout)

    # ------------------------------------------------------------------ API
    async def decode(self, ambe9: bytes, timeout: float | None = None) -> bytes | None:
        if self.mode == "none":
            return SILENCE_PCM
        if self.mode == "n8vocoder":
            return await self._local(b"D", ambe9)
        pcm = await self._request(self.dec_q, channel_packet(ambe9), timeout or self._timeout())
        if pcm is None:
            return None
        self.stats["dec"] += 1
        self.online = True
        if self.dec_gain:
            pcm = _gain(pcm, self.dec_gain)
        return pcm

    async def encode(self, pcm_le: bytes, timeout: float | None = None) -> bytes | None:
        if self.mode == "none":
            return AMBE_SILENCE
        if self.enc_gain:
            pcm_le = _gain(pcm_le, self.enc_gain)
        if self.mode == "n8vocoder":
            return await self._local(b"E", pcm_le)
        ambe = await self._request(self.enc_q, speech_packet(pcm_le), timeout or self._timeout())
        if ambe is None or len(ambe) != 9:
            return None
        self.stats["enc"] += 1
        self.online = True
        return ambe

    async def _local(self, op: bytes, data: bytes) -> bytes | None:
        c = self.codec
        if c is None or not self.running:
            return None
        out = await c.call(op, data)
        self.stats["restarts"] = c.restarts
        if out is None:
            self.stats["errors"] += 1
            return None
        self.last_rx = time.time()
        self.online = True
        if op == b"D":
            if len(out) != 321:
                return None
            self.stats["dec"] += 1
            if out[0] == 1:
                self.stats["erasures"] += 1
            pcm = out[1:]
            if self.bwe is not None:
                pcm = self.bwe.process(pcm)
            return _gain(pcm, self.dec_gain) if self.dec_gain else pcm
        if len(out) != 9:
            return None
        self.stats["enc"] += 1
        return out

    @property
    def encoder_delay_frames(self) -> int:
        """Rahmen, die der Encoder verzögert ausgibt – so viele Stille-Rahmen am Ende nachschieben."""
        return 2 if self.mode == "n8vocoder" else 0

    def new_stream(self, which: str) -> None:
        """Neue Übertragung beginnt (``enc`` = nach DMR senden, ``dec`` = von DMR empfangen).
        Der Software-Vocoder setzt dann seinen Zustand zurück; die Chips brauchen das nicht."""
        c = self.codec
        if c is not None and self.running:
            asyncio.ensure_future(c.call(b"R", {"enc": b"e", "dec": b"d"}.get(which, b"b")))
            if self.bwe is not None and which in ("dec", "both"):
                self.bwe.reset()

    async def set_options(self, options: dict) -> list[str]:
        """Klang-Einstellungen sofort übernehmen (ohne Neustart)."""
        if self.codec is None:
            return ["Vocoder nicht aktiv"]
        self._set_post(options)
        return await self.codec.set_options(options)

    def _set_post(self, options: dict) -> None:
        db = float((options.get("post") or {}).get("bwe_db", -40))
        self.bwe = BandwidthExtender(db) if db > -40 else None

    def _timeout(self) -> float:
        return float(self.cfg.get("vocoder_timeout_ms", 300 if self.lockstep else 500)) / 1000.0

    async def reopen(self) -> None:
        """Vocoder komplett neu öffnen (Watchdog), z. B. nachdem der USB-Stick neu eingesteckt wurde."""
        await self.stop()
        self.transport = None
        self.serial = None
        self.write_q.clear()
        self.codec = None
        self.consec_timeouts = 0
        self._drain_until = 0.0
        self.stats["reopens"] = self.stats.get("reopens", 0) + 1
        await self.start()

    def status(self) -> dict:
        names = {"n8vocoder": "N8schicht-Vocoder (Software)", "usb": "USB-Stick (AMBE3000)",
                 "ambeserver": "AMBEserver (UDP)", "none": "Test (ohne Vocoder)"}
        return {"mode": self.mode, "name": names.get(self.mode, self.mode), "online": self.online,
                "product": self.product, "version": self.version, "consec_timeouts": self.consec_timeouts,
                **self.stats}


async def tone_test(v: "Vocoder", frames: int = 25) -> dict:
    """1-kHz-Ton über ``frames`` Rahmen kodieren und wieder dekodieren.
    Liefert ok, ms (je Rahmen), hz (stärkste Frequenz im Ergebnis)."""
    t0 = time.perf_counter()
    n = np.arange(160 * frames)
    tone = (np.sin(2 * np.pi * 1000 * n / 8000) * 9000).astype("<i2")
    out, okc = [], 0
    if v.codec is not None:
        await v.codec.call(b"R", b"b")
    for i in range(frames):
        amb = await v.encode(tone[i * 160:(i + 1) * 160].tobytes(), timeout=1.5)
        pcm = await v.decode(amb or AMBE_SILENCE, timeout=1.5)
        if amb is not None and pcm is not None:
            okc += 1
            out.append(np.frombuffer(pcm, dtype="<i2"))
    ms = (time.perf_counter() - t0) * 1000 / frames
    hz = 0.0
    if len(out) > 8:
        y = np.concatenate(out[len(out) // 3:]).astype(np.float32)
        if np.abs(y).max() > 50:
            f = np.abs(np.fft.rfft(y * np.hanning(len(y))))
            hz = float(np.fft.rfftfreq(len(y), 1 / 8000)[int(np.argmax(f))])
    ok = okc == frames and (v.mode != "n8vocoder" or 850 <= hz <= 1150)
    return {"ok": ok, "ms": round(ms, 2), "hz": round(hz), "frames": okc}


def _gain(pcm: bytes, db: float) -> bytes:
    a = np.frombuffer(pcm, dtype="<i2").astype(np.float32) * (10 ** (db / 20.0))
    return np.clip(a, -32767, 32767).astype("<i2").tobytes()


class _UdpProto(asyncio.DatagramProtocol):
    def __init__(self, voc: Vocoder) -> None:
        self.voc = voc

    def connection_made(self, transport) -> None:  # noqa: ANN001
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        if self.voc.transport is not None and self.transport is not self.voc.transport:
            self.voc.stats["late"] += 1      # Antwort an einen bereits ersetzten Socket
            return
        for pkt in _Parser().feed(data):
            self.voc._on_packet(pkt)

    def error_received(self, exc: Exception) -> None:
        self.voc.stats["errors"] += 1
