"""AMBE+2-Vocoder für DMR.

Zwei Betriebsarten, im Adminportal wählbar:

* ``md380``  – Software-Vocoder md380-emu (DVSwitch), UDP, Standard 127.0.0.1:2470
* ``usb``    – AMBE3000-USB-Stick (ThumbDV, DVstick 30, DV3000) direkt seriell
               (Standard /dev/ttyUSB0, 460800 Baud)
* ``ambeserver`` – AMBE3000 hinter einem AMBEserver (UDP, Standard 2460)
* ``none``   – nur für Tests: liefert Stille

Alle sprechen das AMBE3000-Paketformat (0x61, Länge, Typ, Felder). DMR nutzt
Rate 33 (AMBE+2 3600/2450). Ein Sprachrahmen = 20 ms = 160 Samples @ 8 kHz;
ein AMBE-Rahmen = 72 Bit = 9 Byte (so wie er im DMR-Burst steht).
"""
from __future__ import annotations

import asyncio
import logging
import socket
import struct
import threading
import time
from collections import deque

import numpy as np

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


class Vocoder:
    def __init__(self, cfg: dict) -> None:
        self.mode = cfg.get("vocoder_mode", "md380")
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
                      "late": 0, "retries": 0, "restarts": 0}
        self.consec_timeouts = 0
        # UDP (md380-emu, AMBEserver): strikt eine Anfrage nach der anderen, damit eine
        # verspätete Antwort nie der falschen Anfrage zugeordnet wird.
        self.lockstep = self.mode in ("md380", "ambeserver")
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
            if self.mode in ("md380", "ambeserver"):
                host = self.cfg.get("md380_host" if self.mode == "md380" else "ambeserver_host", "127.0.0.1")
                port = int(self.cfg.get("md380_port" if self.mode == "md380" else "ambeserver_port",
                                        2470 if self.mode == "md380" else 2460))
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
                # md380-emu kennt keine Steuerpakete – Probe-Dekodierung als Lebenszeichen
                pcm = await self.decode(AMBE_SILENCE, timeout=1.5)
                self.online = pcm is not None
                self.product = "md380-emu" if self.mode == "md380" else "AMBE"
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
        key = {"md380": "md380_send_init", "usb": "usb_send_init", "ambeserver": "ambeserver_send_init"}[self.mode]
        default = self.mode != "md380"
        return bool(self.cfg.get(key, default))

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
        ambe = await self._request(self.enc_q, speech_packet(pcm_le), timeout or self._timeout())
        if ambe is None or len(ambe) != 9:
            return None
        self.stats["enc"] += 1
        self.online = True
        return ambe

    def _timeout(self) -> float:
        return float(self.cfg.get("vocoder_timeout_ms", 300 if self.lockstep else 500)) / 1000.0

    async def reopen(self) -> None:
        """Vocoder komplett neu öffnen (Watchdog), z. B. nachdem der USB-Stick neu eingesteckt wurde."""
        await self.stop()
        self.transport = None
        self.serial = None
        self.write_q.clear()
        self.consec_timeouts = 0
        self._drain_until = 0.0
        self.stats["reopens"] = self.stats.get("reopens", 0) + 1
        await self.start()

    def status(self) -> dict:
        names = {"md380": "md380-emu (Software)", "usb": "USB-Stick (AMBE3000)",
                 "ambeserver": "AMBEserver (UDP)", "none": "Test (ohne Vocoder)"}
        return {"mode": self.mode, "name": names.get(self.mode, self.mode), "online": self.online,
                "product": self.product, "version": self.version, "consec_timeouts": self.consec_timeouts,
                **self.stats}


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
