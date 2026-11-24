"""Zello-Seite über die offizielle Zello Channel API (WebSocket, Opus).

Empfang: on_stream_start (from = Benutzername) -> Binärpakete 0x01 -> on_stream_stop
Senden:  send_text_message (Sprechername, optional) -> start_stream -> Opus-Pakete -> stop_stream
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import struct
import time
from collections import deque

from .audio.dsp import FRAME_BYTES, FrameBuffer, Resampler, gain
from .audio.opus import OpusDecoder, OpusEncoder
from .core import Port, Talker

log = logging.getLogger("zello")


def codec_header(rate: int, frames: int, ms: int) -> str:
    return base64.b64encode(struct.pack("<HBB", rate, frames, ms)).decode()


class ZelloPort(Port):
    key = "zello"
    label = "Zello"

    def __init__(self, router, cfg) -> None:  # noqa: ANN001
        super().__init__(router, cfg)
        self.ws = None
        self.seq = 0
        self.pending: dict[int, asyncio.Future] = {}
        self.refresh_token = ""
        self.users_online = 0
        self.channel_status = ""
        self.texting = False
        # RX
        self.rx_stream_id: int | None = None
        self.rx_dec: OpusDecoder | None = None
        self.rx_buf = FrameBuffer(FRAME_BYTES)
        self.rx_last = 0.0
        self.rx_from = ""
        # TX
        self.tx_stream_id: int | None = None
        self.tx_task: asyncio.Task | None = None
        self.tx_cur: _ZTx | None = None

    # ------------------------------------------------------------ Lebenszyklus
    async def start(self) -> None:
        if not self.enabled:
            self.set_state(False, "deaktiviert")
            return
        self.spawn(self._run())
        self.spawn(self._watchdog())

    def _auth(self) -> dict:
        s = self.section
        mode = s.get("auth_mode", "token")
        if self.refresh_token:
            return {"refresh_token": self.refresh_token}
        if mode == "token" and s.get("auth_token"):
            return {"auth_token": s["auth_token"]}
        if mode == "key" and s.get("issuer") and s.get("private_key"):
            import jwt
            tok = jwt.encode({"iss": s["issuer"], "exp": int(time.time()) + 60}, s["private_key"], algorithm="RS256")
            return {"auth_token": tok}
        return {}

    async def _run(self) -> None:
        import aiohttp
        delay = 5
        while True:
            s = self.section
            try:
                self.set_state(False, "verbinde", s["server"])
                async with aiohttp.ClientSession() as sess:
                    async with sess.ws_connect(s["server"], heartbeat=30, timeout=20) as ws:
                        self.ws = ws
                        logon = {"command": "logon", "seq": self._next_seq(), "channels": [s["channel"]],
                                 "version": "N8-Crosslink", "platform_type": "server",
                                 "platform_name": "N8 Crosslink Gateway"}
                        if s.get("username"):
                            logon.update(username=s["username"], password=s.get("password", ""))
                        logon.update(self._auth())
                        fut = self._expect(logon["seq"])
                        await ws.send_str(json.dumps(logon))
                        reader = asyncio.create_task(self._reader(ws))
                        try:
                            resp = await asyncio.wait_for(fut, 15)
                        except asyncio.TimeoutError:
                            resp = {"error": "keine Antwort"}
                        if not resp.get("success"):
                            self.refresh_token = ""
                            self.router.event("warn", f"Zello-Login fehlgeschlagen: {resp.get('error')}")
                            reader.cancel()
                            raise ConnectionError(resp.get("error"))
                        self.refresh_token = resp.get("refresh_token", self.refresh_token)
                        self.set_state(True, "online", f"Kanal {s['channel']}")
                        self.router.event("info", f"Zello verbunden mit Kanal „{s['channel']}“")
                        delay = 5
                        await reader
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("Zello: %s", e)
                self.router.event("warn", f"Zello: Verbindung getrennt ({e})")
            finally:
                self.ws = None
                if self.rx_stream_id is not None:
                    self._rx_stop()
                self._tx_abort()
            self.set_state(False, "getrennt", f"neuer Versuch in {delay} s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120)

    def _next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def _expect(self, seq: int) -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        self.pending[seq] = fut
        return fut

    async def _send(self, obj: dict) -> None:
        if self.ws is not None and not self.ws.closed:
            await self.ws.send_str(json.dumps(obj))

    async def _reader(self, ws) -> None:  # noqa: ANN001
        import aiohttp
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    self._on_json(json.loads(msg.data))
                except Exception as e:  # noqa: BLE001
                    log.exception("Zello JSON: %s", e)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                self._on_binary(msg.data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    # ------------------------------------------------------------ Empfang
    def _on_json(self, m: dict) -> None:
        if "seq" in m and m["seq"] in self.pending:
            fut = self.pending.pop(m["seq"])
            if not fut.done():
                fut.set_result(m)
            return
        cmd = m.get("command")
        if cmd == "on_channel_status":
            self.users_online = m.get("users_online", 0)
            self.channel_status = m.get("status", "")
            self.texting = bool(m.get("texting_supported"))
            self.detail = f"Kanal {self.section['channel']} · {self.users_online} online"
            if m.get("status") != "online":
                self.router.event("warn", f"Zello-Kanal {m.get('status')}: {m.get('error', '')}")
            self.router.notify()
        elif cmd == "on_stream_start":
            if self.rx_stream_id is not None:
                self._rx_stop()
            self.rx_stream_id = m.get("stream_id")
            self.rx_from = m.get("from", "?")
            self.rx_dec = OpusDecoder(8000)
            self.rx_buf = FrameBuffer(FRAME_BYTES)
            self.rx_last = time.time()
            talker = Talker(source="zello", name=self.rx_from, callsign=self.rx_from.upper(),
                            detail=f"Kanal {m.get('channel', self.section['channel'])}")
            self.rx_accepted = self.router.rx_begin(self, talker)
        elif cmd == "on_stream_stop":
            if m.get("stream_id") == self.rx_stream_id:
                self._rx_stop()
        elif cmd == "on_text_message":
            self.router.event("info", f"Zello-Text von {m.get('from')}: {str(m.get('text'))[:160]}")
        elif cmd == "on_error":
            self.router.event("warn", f"Zello-Fehler: {m.get('error')}")

    def _on_binary(self, data: bytes) -> None:
        if len(data) < 9 or data[0] != 0x01:
            return
        sid = struct.unpack(">I", data[1:5])[0]
        if sid != self.rx_stream_id or self.rx_dec is None:
            return
        self.rx_last = time.time()
        pcm = self.rx_dec.decode(data[9:])
        pcm = gain(pcm, float(self.section.get("rx_gain_db", 0)))
        for fr in self.rx_buf.push(pcm):
            self.router.rx_audio(self, fr)

    def _rx_stop(self) -> None:
        rest = self.rx_buf.flush(pad=True)
        if rest:
            self.router.rx_audio(self, rest)
        self.rx_stream_id = None
        self.rx_dec = None
        self.router.rx_end(self)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            to = float(self.section.get("rx_timeout_ms", 1500)) / 1000.0
            if self.rx_stream_id is not None and time.time() - self.rx_last > to:
                self._rx_stop()
            self._tasks = [t for t in self._tasks if not t.done()]

    # ------------------------------------------------------------ Senden
    def tx_begin(self, talker: Talker) -> None:
        s = self.section
        rate = int(s.get("sample_rate", 16000))
        ms = int(s.get("packet_ms", 60))
        prev = self.tx_task
        tx = _ZTx(rate, ms, int(s.get("bitrate", 16000)))
        if self.tx_cur is not None:
            self.tx_cur.end()
        self.tx_cur = tx
        self.tx_task = self.spawn(self._tx_loop(tx, talker, prev))

    def tx_audio(self, pcm: bytes) -> None:
        tx = self.tx_cur
        if tx is None or tx.ending:
            return
        tx.push(gain(pcm, float(self.section.get("tx_gain_db", 0))))

    def tx_end(self) -> None:
        if self.tx_cur is not None:
            self.tx_cur.end()

    def _tx_abort(self) -> None:
        if self.tx_cur is not None:
            self.tx_cur.queue.clear()
            self.tx_cur.ending = True

    async def _tx_loop(self, tx: "_ZTx", talker: Talker, prev: asyncio.Task | None) -> None:
        loop = asyncio.get_running_loop()
        s = self.section
        try:
            if prev is not None and not prev.done():
                try:
                    await prev
                except BaseException:  # noqa: BLE001
                    pass
            if s.get("send_text", True) and self.texting:
                text = s.get("text_template", "🎙 {name} · {source}").format(
                    name=talker.short(), callsign=talker.callsign, source=talker.to_dict()["label"],
                    detail=talker.detail)
                await self._send({"command": "send_text_message", "seq": self._next_seq(),
                                  "channel": s["channel"], "text": text})
            seq = self._next_seq()
            fut = self._expect(seq)
            await self._send({"command": "start_stream", "seq": seq, "channel": s["channel"], "type": "audio",
                              "codec": "opus", "codec_header": codec_header(tx.rate, 1, tx.ms),
                              "packet_duration": tx.ms})
            try:
                resp = await asyncio.wait_for(fut, 5)
            except asyncio.TimeoutError:
                resp = {"error": "keine Antwort"}
            if not resp.get("success"):
                self.router.event("warn", f"Zello: Senden nicht möglich ({resp.get('error')})")
                return
            sid = resp["stream_id"]
            self.tx_stream_id = sid
            jitter = max(1, int(self.router.g.get("jitter_ms", 240)) // tx.ms)
            waited = 0
            while len(tx.queue) < jitter and not tx.ending and waited < 50:
                await asyncio.sleep(0.02)
                waited += 1
            tick = tx.ms / 1000.0
            t = loop.time()
            while True:
                if tx.queue:
                    pkt = tx.queue.popleft()
                    if self.ws is not None and not self.ws.closed:
                        await self.ws.send_bytes(b"\x01" + struct.pack(">II", sid, 0) + pkt)
                elif tx.ending:
                    break
                t += tick
                await asyncio.sleep(max(0, t - loop.time()))
            await self._send({"command": "stop_stream", "stream_id": sid})
        except Exception as e:  # noqa: BLE001
            log.exception("Zello TX: %s", e)
        finally:
            self.tx_stream_id = None
            if self.tx_cur is tx:
                self.tx_cur = None
                self.router.finished_tx(self)

    def extra_info(self) -> dict:
        s = self.section
        return {"server": s.get("server"), "channel": s.get("channel"), "users_online": self.users_online,
                "channel_status": self.channel_status, "username": s.get("username")}


class _ZTx:
    """Zustand einer einzelnen Aussendung nach Zello."""

    def __init__(self, rate: int, ms: int, bitrate: int) -> None:
        self.rate, self.ms = rate, ms
        self.enc = OpusEncoder(rate, bitrate)
        self.rs = Resampler(up=True) if rate == 16000 else None
        self.buf = FrameBuffer(rate * ms // 1000 * 2)
        self.queue: deque[bytes] = deque()
        self.ending = False

    def push(self, pcm: bytes) -> None:
        if self.rs:
            pcm = self.rs.process(pcm)
        for fr in self.buf.push(pcm):
            self.queue.append(self.enc.encode(fr))

    def end(self) -> None:
        if not self.ending:
            rest = self.buf.flush(pad=True)
            if rest:
                self.queue.append(self.enc.encode(rest))
            self.ending = True
