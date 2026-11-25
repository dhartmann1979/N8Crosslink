"""DMR-Seite: HomeBrew-Peer zu HBlink4 / FreeDMR inkl. Sprach-Streams.

Login: RPTL -> RPTACK+Salt -> RPTK sha256(salt+passwort) -> RPTACK -> RPTC (Config)
       -> RPTACK -> [RPTO Optionen -> RPTACK] -> verbunden. Keepalive RPTPING/MSTPONG.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import socket
import time
from collections import deque

from ..audio.dsp import FRAME_BYTES, gain
from ..core import Port, Talker
from . import burst as B
from . import fec

log = logging.getLogger("dmr")


def _pad_text(v, n: int) -> bytes:  # noqa: ANN001
    return str(v).encode()[:n].ljust(n)


def _pad_num(v, n: int) -> bytes:  # noqa: ANN001
    return str(int(v or 0)).encode()[:n].rjust(n, b"0")


def _pad_dec(v, n: int) -> bytes:  # noqa: ANN001
    return str(v).encode()[:n].rjust(n)


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, port: "DmrPort") -> None:
        self.port = port

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        try:
            self.port._on_packet(data)
        except Exception as e:  # noqa: BLE001
            log.exception("DMR-Paketfehler: %s", e)

    def error_received(self, exc: Exception) -> None:
        log.debug("UDP-Fehler: %s", exc)


class RxStream:
    def __init__(self, stream_id: bytes, src: int, dst: int, accepted: bool) -> None:
        self.stream_id = stream_id
        self.src = src
        self.dst = dst
        self.accepted = accepted
        self.last = time.time()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.frags: dict[int, list[int]] = {}
        self.ta = B.TalkerAliasDecoder()
        self.ta_text = ""
        self.ended = False


class TxStream:
    def __init__(self, talker: Talker, src: int, dst: int, cfg: dict) -> None:
        self.talker = talker
        self.stream_id = random.randint(1, 0xFFFFFFFE).to_bytes(4, "big")
        self.src = src
        self.dst = dst
        self.lc = B.make_lc(src, dst, True)
        self.lc_frags = fec.embedded_lc_encode(self.lc)
        self.ta_frags = []
        if cfg.get("talker_alias", True):
            self.ta_frags = [fec.embedded_lc_encode(b) for b in B.talker_alias_blocks(talker.short())]
        self.frames: deque[asyncio.Future] = deque()
        self.ending = False
        self.task: asyncio.Task | None = None


class DmrPort(Port):
    key = "dmr"
    label = "DMR"

    def __init__(self, router, cfg, vocoder) -> None:  # noqa: ANN001
        super().__init__(router, cfg)
        self.vocoder = vocoder
        self.transport = None
        self.addr = None
        self.login_state = "idle"
        self.salt = b""
        self.last_pong = 0.0
        self.seq = 0
        self.rx: RxStream | None = None
        self.tx: TxStream | None = None
        self.ignored_streams: deque[bytes] = deque(maxlen=16)
        self.stats = {"pings": 0, "pongs": 0, "rx_pkts": 0, "tx_pkts": 0}
        self.connected_since = 0.0

    @property
    def peer_id(self) -> bytes:
        return int(self.section["peer_id"]).to_bytes(4, "big")

    # ------------------------------------------------------------ Lebenszyklus
    async def start(self) -> None:
        if not self.enabled:
            self.set_state(False, "deaktiviert")
            return
        self.main_task = self.spawn(self._run())
        self.spawn(self._watchdog())

    async def stop(self) -> None:
        if self.transport and self.login_state == "connected":
            self.transport.sendto(b"RPTCL" + self.peer_id)
        await super().stop()
        if self.transport:
            self.transport.close()
            self.transport = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            host, port = self.section["host"], int(self.section["port"])
            try:
                infos = await loop.getaddrinfo(host, port, type=socket.SOCK_DGRAM, family=socket.AF_INET)
                self.addr = infos[0][4]
                if self.transport is None:
                    lp = int(self.section.get("local_port") or 0)       # 0 = beliebiger freier Port (Standard)
                    self.transport, _ = await loop.create_datagram_endpoint(
                        lambda: _Proto(self), remote_addr=self.addr, local_addr=("0.0.0.0", lp) if lp else None)
                self._login()
                # Keepalive / Login-Wiederholung
                while True:
                    await asyncio.sleep(5)
                    if self.login_state == "connected":
                        self.transport.sendto(b"RPTPING" + self.peer_id)
                        self.stats["pings"] += 1
                        if time.time() - self.last_pong > 30:
                            self.router.event("warn", "DMR: keine Antwort vom Server (MSTPONG) – neuer Login")
                            self._disconnected("Timeout")
                            self._login()
                    else:
                        self._login()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.router.event("warn", f"DMR: {host}:{port} nicht erreichbar ({e})")
                self.set_state(False, "Fehler", str(e)[:80])
                if self.transport:
                    self.transport.close()
                    self.transport = None
                await asyncio.sleep(15)

    def _login(self) -> None:
        self.login_state = "login"
        self.set_state(False, "Login", f"{self.section['host']}:{self.section['port']}")
        self.transport.sendto(b"RPTL" + self.peer_id)

    def _send_config(self) -> None:
        s = self.section
        pkt = (b"RPTC" + self.peer_id + _pad_text(s["callsign"], 8) + _pad_num(s.get("rx_freq"), 9)
               + _pad_num(s.get("tx_freq"), 9) + _pad_num(s.get("power", 1), 2) + _pad_num(s.get("color_code", 1), 2)
               + _pad_dec(s.get("latitude", "0"), 8) + _pad_dec(s.get("longitude", "0"), 9)
               + _pad_num(s.get("height", 0), 3) + _pad_text(s.get("location", ""), 20)
               + _pad_text(s.get("description", ""), 19) + b"4" + _pad_text(s.get("url", ""), 124)
               + _pad_text("N8-Crosslink", 40) + _pad_text("N8Crosslink FRN-DMR-Zello", 40))
        self.transport.sendto(pkt)

    def _disconnected(self, why: str) -> None:
        if self.rx:
            self._rx_finish()
        self.login_state = "idle"
        self.set_state(False, "getrennt", why)

    # ------------------------------------------------------------ Pakete
    def _on_packet(self, data: bytes) -> None:
        if data[:4] == b"DMRD":
            self.stats["rx_pkts"] += 1
            if self.login_state == "connected":
                self._on_dmrd(data)
            return
        if data[:6] == b"RPTACK":
            st = self.login_state
            if st == "login" and len(data) >= 10:
                self.salt = data[6:10]
                digest = hashlib.sha256(self.salt + self.section["password"].encode()).digest()
                self.transport.sendto(b"RPTK" + self.peer_id + digest)
                self.login_state = "auth"
            elif st == "auth":
                self._send_config()
                self.login_state = "config"
            elif st == "config":
                opts = (self.section.get("options") or "").strip()
                if opts:
                    self.transport.sendto(b"RPTO" + self.peer_id + opts.encode()[:300])
                    self.login_state = "options"
                else:
                    self._connected()
            elif st == "options":
                self._connected()
            return
        if data[:7] == b"MSTPONG":
            self.last_pong = time.time()
            self.stats["pongs"] += 1
            return
        if data[:6] == b"MSTNAK":
            was = self.login_state
            self.router.event("warn", f"DMR: Server lehnt ab (MSTNAK, Phase {was}) – ID/Passwort prüfen")
            self._disconnected("abgelehnt (MSTNAK)")
            return
        if data[:5] == b"MSTCL":
            self.router.event("warn", "DMR: Server hat die Verbindung beendet (MSTCL)")
            self._disconnected("vom Server getrennt")
            return

    def _connected(self) -> None:
        self.login_state = "connected"
        self.last_pong = time.time()
        self.connected_since = time.time()
        s = self.section
        self.set_state(True, "online", f"{self.tg_label(int(s['tg_rx'] or 0))} · TS{s['slot']}")
        self.router.event("info", f"DMR verbunden mit {s['host']} als {s['peer_id']} (TG {s['tg_rx']}, TS{s['slot']})")

    # ------------------------------------------------------------ Empfang
    def _on_dmrd(self, d: bytes) -> None:
        if len(d) < 53:
            return
        src = int.from_bytes(d[5:8], "big")
        dst = int.from_bytes(d[8:11], "big")
        bits = d[15]
        stream_id = d[16:20]
        payload = d[20:53]
        slot = 2 if bits & 0x80 else 1
        group = not (bits & 0x40)
        ftype = (bits >> 4) & 0x03
        dtype = bits & 0x0F
        s = self.section
        tg_rx = int(s.get("tg_rx") or 0)
        if slot != int(s["slot"]) or not group or (tg_rx and dst != tg_rx):
            return
        if ftype == 2 and dtype not in (B.DT_VOICE_LC_HEADER, B.DT_TERMINATOR_WITH_LC):
            return  # Daten (z. B. GPS/SMS) ignorieren
        if stream_id in self.ignored_streams:
            return
        rx = self.rx
        if rx is None or rx.stream_id != stream_id:
            if ftype == 2 and dtype == B.DT_TERMINATOR_WITH_LC:
                return
            if rx is not None:
                self._rx_finish()
            talker = self._talker(src, dst)
            accepted = self.router.rx_begin(self, talker)
            rx = self.rx = RxStream(stream_id, src, dst, accepted)
            if accepted and hasattr(self.vocoder, "new_stream"):
                self.vocoder.new_stream("dec")
            self.spawn(self._rx_worker(rx))
        rx.last = time.time()
        if ftype == 2 and dtype == B.DT_TERMINATOR_WITH_LC:
            self._rx_finish()
            return
        if ftype == 2:
            return  # Header
        n = 0 if ftype == 1 else dtype
        if rx.accepted:
            for amb in B.extract_ambe(payload):
                rx.queue.put_nowait(asyncio.ensure_future(self.vocoder.decode(amb)))
        if 1 <= n <= 4:
            rx.frags[n] = B.extract_emb_fragment(payload)
            if n == 4 and len(rx.frags) == 4:
                lc = fec.embedded_lc_decode([rx.frags[i] for i in (1, 2, 3, 4)])
                rx.frags.clear()
                if lc:
                    txt = rx.ta.add_lc(lc)
                    if txt and txt != rx.ta_text and not txt.endswith("…"):
                        rx.ta_text = txt
                        self.router.rx_update_talker(self, name=txt)
        elif n == 5:
            rx.frags.clear()

    def tg_label(self, tg: int) -> str:
        name = self.router.db.tg_name(tg)
        return f"TG {tg} {name}".strip()

    def _talker(self, src: int, dst: int) -> Talker:
        db = self.router.db
        detail = f"{self.tg_label(dst)} · TS{self.section['slot']}"
        u = db.userdb_lookup(src)
        if u:
            name = f"{u['callsign']} {u['name']}".strip()
            return Talker(source="dmr", name=name, callsign=u["callsign"], dmr_id=src, city=u.get("city") or "",
                          detail=detail, extra={"frid": u.get("frid", False), "tg": dst})
        ids = getattr(self.router, "idlists", None)
        if ids is not None:
            ids.lookup_later(src)       # unbekannt -> FreeRadioID-Einzelabfrage
        return Talker(source="dmr", name=str(src), callsign=str(src), dmr_id=src, detail=detail,
                      extra={"frid": False, "tg": dst})

    async def _rx_worker(self, rx: RxStream) -> None:
        g = float(self.section.get("rx_gain_db", 0))
        try:
            while True:
                item = await rx.queue.get()
                if item is None:
                    break
                try:
                    pcm = await item
                except Exception as e:  # noqa: BLE001 – ein kaputter Rahmen beendet nicht den Durchgang
                    log.warning("DMR-RX: Rahmen nicht dekodierbar: %r", e)
                    pcm = None
                self.router.rx_audio(self, gain(pcm, g) if pcm else bytes(FRAME_BYTES))
        finally:
            # Ende erst melden, wenn alle Rahmen dekodiert und weitergegeben sind – auch nach einem Fehler,
            # sonst bliebe der Durchgang „aktiv“ und sperrte alle anderen Netze
            self.router.rx_end(self)

    def _rx_finish(self) -> None:
        rx = self.rx
        if not rx or rx.ended:
            return
        rx.ended = True
        self.ignored_streams.append(rx.stream_id)
        self.rx = None
        rx.queue.put_nowait(None)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            to = float(self.section.get("rx_timeout_ms", 500)) / 1000.0
            if self.rx and time.time() - self.rx.last > to:
                self._rx_finish()
            # erledigte Tasks aufräumen
            self._tasks = [t for t in self._tasks if not t.done()]

    # ------------------------------------------------------------ Senden
    def can_tx(self) -> bool:
        return super().can_tx() and self.login_state == "connected" and self.vocoder is not None

    def tx_begin(self, talker: Talker) -> None:
        s = self.section
        src = int(s["src_id"])
        if s.get("use_db_id") and talker.callsign:
            u = self.router.db.userdb_by_callsign(talker.callsign)
            if u:
                src = int(u["id"])
        prev = self.tx.task if self.tx else None
        if self.tx and not self.tx.ending:
            self.tx.ending = True
        self.tx = TxStream(talker, src, int(s["tg_tx"]), s)
        if hasattr(self.vocoder, "new_stream"):
            self.vocoder.new_stream("enc")
        self.tx.task = self.spawn(self._tx_loop(self.tx, prev))
        if s.get("send_dmra"):
            for i, blk in enumerate(B.talker_alias_blocks(talker.short())):
                self.transport.sendto(b"DMRA" + src.to_bytes(3, "big") + bytes([i]) + blk[2:9])

    def tx_audio(self, pcm: bytes) -> None:
        tx = self.tx
        if not tx or tx.ending:
            return
        pcm = gain(pcm, float(self.section.get("tx_gain_db", 0)))
        if len(tx.frames) > 1500:      # > 30 s Rückstau: Vocoder hängt – nicht endlos puffern
            return
        tx.frames.append(asyncio.ensure_future(self.vocoder.encode(pcm)))

    def tx_end(self) -> None:
        tx = self.tx
        if tx and not tx.ending:
            # Software-Vocoder gibt 2 Rahmen verzögert aus: mit Stille nachschieben,
            # damit das Ende des Durchgangs nicht abgeschnitten wird
            for _ in range(getattr(self.vocoder, "encoder_delay_frames", 0)):
                tx.frames.append(asyncio.ensure_future(self.vocoder.encode(bytes(320))))
        if tx:
            tx.ending = True

    def _dmrd(self, tx: TxStream, bits: int, payload: bytes) -> None:
        s = self.section
        slot_bit = 0x80 if int(s["slot"]) == 2 else 0x00
        pkt = (b"DMRD" + bytes([self.seq & 0xFF]) + tx.src.to_bytes(3, "big") + tx.dst.to_bytes(3, "big")
               + self.peer_id + bytes([slot_bit | bits]) + tx.stream_id + payload + b"\x00\x00")
        self.seq = (self.seq + 1) & 0xFF
        if self.transport and self.login_state == "connected":
            self.transport.sendto(pkt)
            self.stats["tx_pkts"] += 1

    async def _tx_loop(self, tx: TxStream, prev: asyncio.Task | None = None) -> None:
        loop = asyncio.get_running_loop()
        if prev is not None and not prev.done():
            try:
                await prev      # vorherige Aussendung erst sauber mit Terminator beenden
            except BaseException:  # noqa: BLE001
                pass
        cc = int(self.section.get("color_code", 1))
        jitter_frames = max(3, int(self.router.g.get("jitter_ms", 240)) // 20)
        tick = 0.06
        t = loop.time()
        try:
            hdr = B.build_lc_burst(tx.lc, cc, terminator=False)
            # Voice-LC-Header (3x) – währenddessen füllt sich der Vorpuffer
            for _ in range(3):
                self._dmrd(tx, 0x20 | B.DT_VOICE_LC_HEADER, hdr)
                t += tick
                await asyncio.sleep(max(0, t - loop.time()))
            waited = 0
            while len(tx.frames) < jitter_frames and not tx.ending and waited < 40:
                await asyncio.sleep(0.02)
                waited += 1
            t = loop.time()
            n = 0
            sf = 0
            underrun = 0
            while True:
                if tx.ending and not tx.frames:
                    break
                ambe: list[bytes] = []
                for _ in range(3):
                    if tx.frames and tx.frames[0].done():
                        amb = tx.frames.popleft().result() or B.AMBE_SILENCE
                    elif tx.frames and tx.ending:
                        amb = (await tx.frames.popleft()) or B.AMBE_SILENCE
                    else:
                        amb = B.AMBE_SILENCE       # Unterlauf -> Stille, Timing bleibt stabil
                        underrun += 1
                    ambe.append(amb)
                if n == 0:
                    payload = B.build_voice_burst((ambe[0], ambe[1], ambe[2]), 0, cc, None)
                    self._dmrd(tx, 0x10, payload)
                else:
                    use_ta = tx.ta_frags and sf % 2 == 1
                    frags = tx.ta_frags[(sf // 2) % len(tx.ta_frags)] if use_ta else tx.lc_frags
                    frag = frags[n - 1] if 1 <= n <= 4 else None
                    payload = B.build_voice_burst((ambe[0], ambe[1], ambe[2]), n, cc, frag)
                    self._dmrd(tx, n, payload)
                n += 1
                if n == 6:
                    n = 0
                    sf += 1
                t += tick
                await asyncio.sleep(max(0, t - loop.time()))
            term = B.build_lc_burst(tx.lc, cc, terminator=True)
            self._dmrd(tx, 0x20 | B.DT_TERMINATOR_WITH_LC, term)
            if underrun > 9:
                log.info("DMR-TX: %s Rahmen mit Stille aufgefüllt (Jitter-Puffer ggf. erhöhen)", underrun)
        finally:
            if self.tx is tx:
                self.tx = None
                self.router.finished_tx(self)

    def on_lookup_result(self, dmr_id: int, name: str, callsign: str, city: str) -> None:
        """Ergebnis der FreeRadioID-Einzelabfrage für eine bis dahin unbekannte ID."""
        rx = self.rx
        if rx and rx.src == dmr_id and not rx.ta_text and name:
            self.router.rx_update_talker(self, name=name, callsign=callsign, city=city)

    def extra_info(self) -> dict:
        s = self.section
        return {"server": f"{s.get('host')}:{s.get('port')}", "peer_id": s.get("peer_id"), "slot": s.get("slot"),
                "tg_rx": s.get("tg_rx"), "tg_tx": s.get("tg_tx"), "login": self.login_state,
                "since": self.connected_since if self.login_state == "connected" else None,
                "tg_rx_name": self.router.db.tg_name(int(s.get("tg_rx") or 0)),
                "tg_tx_name": self.router.db.tg_name(int(s.get("tg_tx") or 0)),
                "stats": self.stats, "userdb": self.router.db.userdb_info()}

