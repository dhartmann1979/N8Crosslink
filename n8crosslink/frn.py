"""FreeRadioNetwork-Client (Crosslink) – Protokoll nach SvxLink QsoFrn / freeradionetwork.eu.

Ablauf:
  CT:<VX>..</VX><EA>..</EA><PW>..</PW><ON>Call, Name</ON><CL>0</CL><BC>Crosslink</BC>...\\r\\n
  Server: Protokollversion, dann Zeile mit <AL>OK|ADMIN|OWNER|NETOWNER|WRONG|BLOCK</AL>
  Client: RX0 – danach Polling mit P, Server antwortet mit einem DataType-Byte:
    0 IDLE · 1 DO_TX (+2 Byte) · 2 VOICE (+2 Byte Index +325 Byte GSM) · 3 CLIENT_LIST (+2 Byte, Zähler, Zeilen)
    4..10 Listen (Zähler, Zeilen)
  Senden: TX0 (Anfrage) -> DO_TX -> je 200 ms "TX1" + 325 Byte GSM -> RX0
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from .audio import gsm
from .audio.dsp import FRAME_BYTES, FrameBuffer, gain
from .core import Port, Talker

log = logging.getLogger("frn")

DT_IDLE, DT_DO_TX, DT_VOICE, DT_CLIENT_LIST, DT_TEXT = 0, 1, 2, 3, 4
LIST_TYPES = {4: "text", 5: "nets", 6: "admins", 7: "access", 8: "blocks", 9: "mutes", 10: "access_mode"}
TAG_RE = re.compile(r"<(\w+)>(.*?)</\1>")
CLIENT_TYPES = {"0": "Crosslink", "1": "Gateway", "2": "PC Only"}


def parse_tags(line: str) -> dict:
    return {m.group(1): m.group(2) for m in TAG_RE.finditer(line)}


def split_on(on: str) -> tuple[str, str]:
    if "," in on:
        cs, name = on.split(",", 1)
        return cs.strip(), name.strip()
    return on.strip(), ""


BC_RE = re.compile(r"^(PC Only|Crosslink|[0-9]+\.[0-9]+(AM|FM|DIG)( (CTC[0-9.]+|DSC[0-9]+|CID[0-9]+|NONE))?)$")
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def validate_registration(v: dict) -> list[str]:
    """Prüft die Angaben wie das SvxLink-Skript frn-register."""
    errs = []
    if not v.get("callsign", "").strip() or not v.get("op_name", "").strip():
        errs.append("Rufzeichen und Name müssen ausgefüllt sein (FRN: „Rufzeichen, Name“)")
    if not EMAIL_RE.match(v.get("email", "").strip()):
        errs.append("E-Mail-Adresse ist ungültig")
    if not BC_RE.match(v.get("band", "").strip()):
        errs.append("Band/Kanal muss „PC Only“, „Crosslink“ oder z. B. „446.03125FM CTC131.8“ sein")
    if not v.get("country", "").strip():
        errs.append("Land fehlt")
    if not re.match(r"^.+ - .+$", v.get("city", "").strip()):
        errs.append("Ort muss die Form „Ort - Ortsteil“ haben (z. B. „Minden - JO42“)")
    for k in ("callsign", "op_name", "email", "band", "description", "country", "city"):
        if "<" in str(v.get(k, "")) or ">" in str(v.get(k, "")):
            errs.append(f"„{k}“ darf keine spitzen Klammern enthalten")
    return errs


async def request_password(v: dict) -> tuple[bool, str, str]:
    """FRN-Registrierung beim System Manager: das Passwort kommt per E-Mail.

    Rückgabe: (erfolgreich, Kurzstatus, Meldung)."""
    errs = validate_registration(v)
    if errs:
        return False, "Eingaben prüfen", "\n".join(errs)
    on = f"{v['callsign'].strip()}, {v['op_name'].strip()}"
    cmd = ("IG:" + f"<ON>{on}</ON>" + f"<EA>{v['email'].strip()}</EA>" + f"<BC>{v['band'].strip()}</BC>"
           + f"<DS>{v.get('description', '').strip()}</DS>" + f"<NN>{v['country'].strip()}</NN>"
           + f"<CT>{v['city'].strip()}</CT>")
    host, port = v.get("sysman_server") or "sysman.freeradionetwork.eu", int(v.get("sysman_port") or 10025)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 15)
    except (OSError, asyncio.TimeoutError) as e:
        return False, "Keine Verbindung", f"System Manager {host}:{port} nicht erreichbar ({e or 'Zeitüberschreitung'})"
    try:
        writer.write(cmd.encode("latin-1", errors="replace") + b"\n")
        await writer.drain()
        ans = (await asyncio.wait_for(reader.readline(), 30)).decode("latin-1", errors="replace").strip()
    except (OSError, asyncio.TimeoutError):
        return False, "Keine Antwort", f"Der System Manager {host}:{port} hat nicht geantwortet"
    finally:
        writer.close()
    if ans == "OK":
        return True, "Passwort angefordert", (f"Die Registrierung für „{on}“ wurde angenommen. Das Passwort wird an "
                                              f"{v['email'].strip()} geschickt – bitte auch im Spam-Ordner nachsehen. "
                                              "Danach das Passwort hier eintragen und speichern.")
    if ans == "NU":
        return False, "Bereits registriert", (f"„{on}“ bzw. die E-Mail ist beim FRN schon vergeben. Das vorhandene "
                                              "Passwort verwenden (steht in der damaligen E-Mail) oder den FRN-Admin fragen.")
    return False, "Abgelehnt", f"Der System Manager hat die Daten abgelehnt (Antwort: „{ans or 'leer'}“). Angaben prüfen."


class FrnPort(Port):
    key = "frn"
    label = "FRN"

    def __init__(self, router, cfg) -> None:  # noqa: ANN001
        super().__init__(router, cfg)
        self.writer: asyncio.StreamWriter | None = None
        self.clients: list[dict] = []
        self.access = ""
        self.server_version = ""
        self.net_info = ""
        self.nets: list[str] = []
        self.using_backup = False
        # RX
        self.rx_dec: gsm.GsmDecoder | None = None
        self.rx_index = 0
        self.rx_last = 0.0
        self.rx_accepted = False
        # TX
        self.tx_state = "idle"          # idle | waiting | tx
        self.tx_enc: gsm.GsmEncoder | None = None
        self.tx_buf = FrameBuffer(gsm.PACKET_SAMPLES * 2)
        self.tx_pending: list[bytes] = []
        self.tx_late_grant = False
        self.tx_packets = 0
        self.tx_gen = 0
        self.last_rx = 0.0

    # ------------------------------------------------------------ Lebenszyklus
    async def start(self) -> None:
        if not self.enabled:
            self.set_state(False, "deaktiviert")
            return
        self.main_task = self.spawn(self._run())
        self.spawn(self._watchdog())

    async def _run(self) -> None:
        delay = 5
        while True:
            s = self.section
            host, port = s["server"], int(s["port"])
            if self.using_backup and s.get("backup_server"):
                host, port = s["backup_server"], int(s.get("backup_port") or port)
            try:
                self.set_state(False, "verbinde", f"{host}:{port}")
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 15)
                sock = writer.get_extra_info("socket")
                if sock is not None:
                    import socket as _s
                    sock.setsockopt(_s.SOL_SOCKET, _s.SO_KEEPALIVE, 1)
                self.writer = writer
                await self._session(reader)
                delay = 5
            except asyncio.IncompleteReadError:
                self.router.event("warn", f"FRN: Server {host}:{port} hat die Verbindung getrennt")
            except (OSError, asyncio.TimeoutError, ConnectionError) as e:
                self.router.event("warn", f"FRN: Verbindung zu {host}:{port} fehlgeschlagen ({e or type(e).__name__})")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("FRN-Fehler: %s", e)
                self.router.event("warn", f"FRN: Fehler {e}")
            finally:
                self._drop_connection()
            if self.section.get("backup_server"):
                self.using_backup = not self.using_backup
            self.set_state(False, "getrennt", f"neuer Versuch in {delay} s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120)

    def _drop_connection(self) -> None:
        if self.rx_accepted or self.rx_active:
            self._rx_stop()
        if self.tx_state != "idle":
            self.tx_state = "idle"
            self.router.finished_tx(self)
        if self.writer:
            try:
                self.writer.close()
            except Exception:  # noqa: BLE001
                pass
        self.writer = None
        self.clients = []

    def send(self, data: bytes) -> None:
        if self.writer and not self.writer.is_closing():
            self.writer.write(data)

    def cmd(self, text: str) -> None:
        self.send(text.encode("latin-1", errors="replace") + b"\r\n")

    async def _session(self, reader: asyncio.StreamReader) -> None:
        s = self.section
        on = f"{s['callsign']}, {s['op_name']}"
        login = ("CT:" + f"<VX>{s.get('version', '2014003')}</VX>" + f"<EA>{s['email']}</EA>"
                 + f"<PW>{s['password']}</PW>" + f"<ON>{on}</ON>" + f"<CL>{s.get('client_type', 0)}</CL>"
                 + f"<BC>{s['band']}</BC>" + f"<DS>{s['description']}</DS>" + f"<NN>{s['country']}</NN>"
                 + f"<CT>{s['city']}</CT>" + f"<NT>{s['net']}</NT>")
        self.set_state(False, "Login", s["net"])
        self.cmd(login)
        ver = (await asyncio.wait_for(reader.readline(), 20)).decode("latin-1").strip()
        resp = (await asyncio.wait_for(reader.readline(), 20)).decode("latin-1").strip()
        tags = parse_tags(resp)
        self.access = tags.get("AL", "")
        self.server_version = tags.get("SV", ver)
        self.net_info = re.sub(r"<[^>]+>", " ", tags.get("MT", "")).strip()[:300]
        if self.access in ("WRONG", "BLOCK", ""):
            self.router.event("warn", f"FRN-Login abgelehnt ({self.access or resp[:60]}) – E-Mail/Passwort/Raum prüfen")
            await asyncio.sleep(25)
            raise ConnectionError(f"Login {self.access or 'fehlgeschlagen'}")
        self.router.event("info", f"FRN verbunden mit Raum „{s['net']}“ ({self.access})")
        self.set_state(True, "online", f"Raum {s['net']}")
        self.cmd("RX0")
        self.cmd("ST:0")
        self.cmd("P")
        self.last_rx = time.time()
        ka = asyncio.create_task(self._keepalive())
        try:
            await self._read_loop(reader)
        finally:
            ka.cancel()

    async def _keepalive(self) -> None:
        """Pollt mit P, falls der Server länger nichts geschickt hat (Protokoll: Client fragt ab)."""
        while True:
            await asyncio.sleep(0.5)
            if time.time() - self.last_rx > 1.0:
                self.cmd("P")
                self.last_rx = time.time()

    # ------------------------------------------------------------ Empfang
    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while True:
            b = await asyncio.wait_for(reader.readexactly(1), 30)
            self.last_rx = time.time()
            dt = b[0]
            if dt == DT_IDLE:
                self.cmd("P")
            elif dt == DT_DO_TX:
                await reader.readexactly(2)
                self._on_do_tx()
            elif dt == DT_VOICE:
                head = await reader.readexactly(2)
                data = await reader.readexactly(gsm.PACKET_BYTES)
                self._on_voice((head[0] << 8) | head[1], data)
                self.cmd("P")
            elif dt == DT_CLIENT_LIST:
                await reader.readexactly(2)
                lines = await self._read_list(reader)
                self._on_client_list(lines)
                self.cmd("P")
            elif dt in LIST_TYPES:
                lines = await self._read_list(reader)
                self._on_list(LIST_TYPES[dt], lines)
                self.cmd("P")
            else:
                log.debug("FRN: unbekannter Typ %s", dt)

    @staticmethod
    async def _read_list(reader: asyncio.StreamReader) -> list[str]:
        first = (await asyncio.wait_for(reader.readline(), 10)).decode("latin-1").strip()
        try:
            n = int(first)
        except ValueError:
            return []
        out = []
        for _ in range(n):
            out.append((await asyncio.wait_for(reader.readline(), 10)).decode("latin-1", errors="replace").rstrip("\r\n"))
        return out

    def _on_client_list(self, lines: list[str]) -> None:
        clients = []
        for ln in lines:
            t = parse_tags(ln)
            cs, name = split_on(t.get("ON", ""))
            clients.append({"callsign": cs, "name": name, "city": t.get("CT", ""), "country": t.get("NN", ""),
                            "band": t.get("BC", ""), "type": CLIENT_TYPES.get(t.get("CL", ""), t.get("CL", "")),
                            "status": t.get("S", ""), "muted": t.get("M", "") == "1", "id": t.get("ID", ""),
                            "description": t.get("DS", "")})
        self.clients = clients
        self.detail = f"Raum {self.section['net']} · {len(clients)} Stationen"
        self.router.notify()

    def _on_list(self, kind: str, lines: list[str]) -> None:
        if kind == "nets":
            self.nets = lines
        elif kind == "text" and lines:
            self.router.event("info", "FRN-Text: " + " | ".join(re.sub(r"<[^>]+>", " ", l) for l in lines)[:200])

    def _talker_for(self, index: int) -> Talker:
        c = self.clients[index - 1] if 0 < index <= len(self.clients) else {}
        cs = c.get("callsign", "") or f"#{index}"
        name = f"{cs} {c.get('name', '')}".strip()
        return Talker(source="frn", name=name, callsign=cs, city=c.get("city", ""),
                      detail=f"Raum {self.section['net']}",
                      extra={"band": c.get("band", ""), "country": c.get("country", "")})

    def _on_voice(self, index: int, data: bytes) -> None:
        now = time.time()
        if self.rx_active and index != self.rx_index:
            self._rx_stop()                       # Sprecherwechsel ohne Pause
        if not self.rx_active:
            self.rx_index = index
            self.rx_dec = gsm.GsmDecoder()
            self.rx_accepted = self.router.rx_begin(self, self._talker_for(index))
        self.rx_last = now
        pcm = gain(self.rx_dec.decode_packet(data), float(self.section.get("rx_gain_db", 0)))
        for i in range(0, len(pcm), FRAME_BYTES):
            self.router.rx_audio(self, pcm[i:i + FRAME_BYTES])

    def _rx_stop(self) -> None:
        self.rx_accepted = False
        self.rx_dec = None
        self.router.rx_end(self)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            to = float(self.section.get("rx_timeout_ms", 1000)) / 1000.0
            if self.rx_active and time.time() - self.rx_last > to:
                self._rx_stop()

    # ------------------------------------------------------------ Senden
    def tx_begin(self, talker: Talker) -> None:
        self.tx_gen += 1
        self.tx_late_grant = False
        self.tx_enc = gsm.GsmEncoder()
        self.tx_buf = FrameBuffer(gsm.PACKET_SAMPLES * 2)
        self.tx_pending = []
        self.tx_packets = 0
        self.tx_state = "waiting"
        if self.section.get("text_messages"):
            self.send_text(f"{talker.short()} ({talker.to_dict()['label']})")
        self.cmd("TX0")
        self.state = "TX angefragt"

    def text_targets(self) -> list[str] | None:
        """Client-IDs für private Textnachrichten – None = öffentlich an alle."""
        want = [c.strip().upper() for c in str(self.section.get("text_targets") or "").replace(";", ",").split(",") if c.strip()]
        if not want:
            return None
        return [c["id"] for c in self.clients if c.get("id") and c.get("callsign", "").upper() in want]

    def send_text(self, msg: str) -> None:
        """FRN-Textnachricht: leere <ID> = öffentlich an alle, sonst privat an die Station mit dieser Client-ID."""
        msg = re.sub(r"[<>\r\n]", "", msg)[:200]
        ids = self.text_targets()
        if ids is None:
            self.cmd(f"TM:<ID></ID><MS>{msg}</MS>")
            return
        for cid in ids:                        # nur an die eingetragenen Stationen – bei den übrigen ploppt nichts auf
            self.cmd(f"TM:<ID>{cid}</ID><MS>{msg}</MS>")

    def _on_do_tx(self) -> None:
        if self.tx_state == "waiting":
            self.tx_state = "tx"
            self.state = "sendet"
            for pkt in self.tx_pending:
                self._send_voice(pkt)
            self.tx_pending.clear()
            if self.tx_late_grant:
                self._tx_close()
        elif self.tx_state == "idle":
            self.cmd("RX0")  # verspätete Freigabe – sofort wieder abgeben
        self.router.notify()

    def _send_voice(self, pcm3200: bytes) -> None:
        self.send(b"TX1\r\n" + self.tx_enc.encode_packet(pcm3200))
        self.tx_packets += 1

    def tx_audio(self, pcm: bytes) -> None:
        if self.tx_state == "idle":
            return
        pcm = gain(pcm, float(self.section.get("tx_gain_db", 0)))
        for pkt in self.tx_buf.push(pcm):
            if self.tx_state == "tx":
                self._send_voice(pkt)
            elif len(self.tx_pending) < 50:     # max. 10 s vorhalten
                self.tx_pending.append(pkt)

    def tx_end(self) -> None:
        if self.tx_state == "idle":
            return
        rest = self.tx_buf.flush(pad=True)
        if rest:
            if self.tx_state == "tx":
                self._send_voice(rest)
            else:
                self.tx_pending.append(rest)
        if self.tx_state == "waiting":
            # Noch keine Freigabe: kurz warten, danach verwerfen
            self.tx_late_grant = True
            gen = self.tx_gen
            asyncio.get_running_loop().call_later(2.0, lambda: self._tx_give_up(gen))
            return
        self._tx_close()

    def _tx_give_up(self, gen: int) -> None:
        if self.tx_state == "waiting" and gen == self.tx_gen:
            self.router.event("warn", "FRN: keine Sendefreigabe vom Server (Raum belegt?) – Durchsage verworfen")
            self._tx_close()

    def _tx_close(self) -> None:
        self.cmd("RX0")
        self.tx_state = "idle"
        self.tx_late_grant = False
        self.tx_pending.clear()
        self.state = "online" if self.online else self.state
        self.router.finished_tx(self)

    def extra_info(self) -> dict:
        return {"clients": self.clients, "access": self.access, "server_version": self.server_version,
                "net": self.section.get("net"), "net_info": self.net_info,
                "server": f"{self.section.get('server')}:{self.section.get('port')}",
                "tx_state": self.tx_state}
