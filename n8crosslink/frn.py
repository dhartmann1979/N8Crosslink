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


class _Relogin(Exception):
    """Gewollte Neuanmeldung (Operator wechseln) – kein Fehler."""


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _clean(text: str, n: int) -> str:
    return re.sub(r"[<>\r\n]", "", str(text or "")).strip()[:n]


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
        # Operator-Wechsel per Neuanmeldung (optional)
        self.identity: dict | None = None        # angemeldet mit fremdem Operator (None = eigener)
        self.want_identity: dict | None = None   # beim nächsten Login verwenden
        self.switching = False
        self._switch_tries = 0
        self.override_blocked = False            # Server hat fremden Operator abgelehnt
        self._restore_h: asyncio.TimerHandle | None = None
        self._ident_waiter: asyncio.Future | None = None

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
                if self.switching:
                    self.state = "meldet an als " + (self.want_identity or {}).get("on", "eigener Operator")
                    self.router.notify()
                else:
                    self.set_state(False, "verbinde", f"{host}:{port}")
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 15)
                sock = writer.get_extra_info("socket")
                if sock is not None:
                    import socket as _s
                    sock.setsockopt(_s.SOL_SOCKET, _s.SO_KEEPALIVE, 1)
                self.writer = writer
                await self._session(reader)
                delay = 5
            except _Relogin:
                pass
            except asyncio.IncompleteReadError:
                if self.switching:
                    self._switch_error("Server hat die Neuanmeldung getrennt")
                else:
                    self.router.event("warn", f"FRN: Server {host}:{port} hat die Verbindung getrennt")
            except (OSError, asyncio.TimeoutError, ConnectionError) as e:
                if self.switching:
                    self._switch_error(f"Neuanmeldung fehlgeschlagen ({e or type(e).__name__})")
                if not self.switching:
                    self.router.event("warn", f"FRN: Verbindung zu {host}:{port} fehlgeschlagen ({e or type(e).__name__})")
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("FRN-Fehler: %s", e)
                self.router.event("warn", f"FRN: Fehler {e}")
            finally:
                self._drop_connection()
            if self.switching:
                await asyncio.sleep(0.3)        # Server kurz Zeit zum Aufräumen lassen
                continue
            if self.section.get("backup_server"):
                self.using_backup = not self.using_backup
            self.set_state(False, "getrennt", f"neuer Versuch in {delay} s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 120)

    def _drop_connection(self) -> None:
        if self.rx_accepted or self.rx_active:
            self._rx_stop()
        if self.tx_state != "idle" and not self.switching:
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
        ident = self.want_identity
        on = ident["on"] if ident else f"{s['callsign']}, {s['op_name']}"
        ds = ident["ds"] if ident else s["description"]
        login = ("CT:" + f"<VX>{s.get('version', '2014003')}</VX>" + f"<EA>{s['email']}</EA>"
                 + f"<PW>{s['password']}</PW>" + f"<ON>{on}</ON>" + f"<CL>{s.get('client_type', 0)}</CL>"
                 + f"<BC>{s['band']}</BC>" + f"<DS>{ds}</DS>" + f"<NN>{s['country']}</NN>"
                 + f"<CT>{s['city']}</CT>" + f"<NT>{s['net']}</NT>")
        if not self.switching:
            self.set_state(False, "Login", s["net"])
        self.cmd(login)
        ver = (await asyncio.wait_for(reader.readline(), 20)).decode("latin-1").strip()
        resp = (await asyncio.wait_for(reader.readline(), 20)).decode("latin-1").strip()
        tags = parse_tags(resp)
        self.access = tags.get("AL", "")
        self.server_version = tags.get("SV", ver)
        self.net_info = re.sub(r"<[^>]+>", " ", tags.get("MT", "")).strip()[:300]
        if self.access in ("WRONG", "BLOCK", ""):
            if ident:
                self._ident_result(False, self.access or resp[:60])
                if not ident.get("test"):
                    self.override_blocked = True
                    self.router.event("warn", f"FRN: Anmeldung als „{on}“ abgelehnt ({self.access or resp[:60]}) – "
                                      "Operator-Wechsel bis zum nächsten Neustart abgeschaltet, melde mit eigenem Operator an")
                self.want_identity = None
                self.switching = True       # sofort mit eigenem Operator neu anmelden
                raise _Relogin()
            self.router.event("warn", f"FRN-Login abgelehnt ({self.access or resp[:60]}) – E-Mail/Passwort/Raum prüfen")
            self.switching = False
            await asyncio.sleep(25)
            raise ConnectionError(f"Login {self.access or 'fehlgeschlagen'}")
        self.identity = ident
        was_switch = self.switching
        self.switching = False
        self._switch_tries = 0
        if ident:
            self._ident_result(True, self.access)
        if not was_switch:
            self.router.event("info", f"FRN verbunden mit Raum „{s['net']}“ ({self.access})")
        self.set_state(True, "online", f"Raum {s['net']}" + (f" · als {on}" if ident else ""))
        self.cmd("RX0")
        self.cmd("ST:0")
        self.cmd("P")
        if self.tx_state == "waiting":
            self._send_tx_request()
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
        self.tx_talker_now = talker
        if self._restore_h:
            self._restore_h.cancel()
            self._restore_h = None
        want = self.identity_for(talker)
        if self.switching:                 # Neuanmeldung läuft schon – TX0 folgt nach dem Login
            if want is not None:
                self.want_identity = want
            return
        cur = (self.identity or {})
        if want and self.writer and (cur.get("on"), cur.get("ds")) != (want["on"], want["ds"]):
            # Mit dem Operator der Station neu anmelden; der Ton wird so lange gepuffert
            self.want_identity = want
            self._switch()
            return
        self._send_tx_request()

    def _send_tx_request(self) -> None:
        t = getattr(self, "tx_talker_now", None)
        if self.section.get("text_messages") and t is not None:
            self.cmd(f"TM:<ID></ID><MS>{t.short()} ({t.to_dict()['label']})</MS>")
        self.cmd("TX0")
        self.state = "TX angefragt"
        if self.tx_late_grant:
            gen = self.tx_gen
            asyncio.get_running_loop().call_later(3.0, lambda: self._tx_give_up(gen))

    # ------------------------------------------------------------ Operator-Wechsel
    def identity_for(self, talker: Talker) -> dict | None:
        """Operator (<ON>) und Beschreibung (<DS>) für eine Station – None, wenn die Option aus ist."""
        s = self.section
        if not s.get("id_override") or self.override_blocked:
            return None
        label = talker.to_dict()["label"]
        cs = _clean(talker.callsign, 20).replace(",", " ")
        name = talker.name or ""
        if cs and name.upper().startswith(cs.upper()):
            op = name[len(cs):].strip()
        else:
            op = name if not cs else ""
        if not cs:
            parts = name.split()
            cs = _clean(parts[0] if parts else "", 20).replace(",", " ") or label
            op = " ".join(parts[1:])
        op = _clean(op.replace(",", " "), 30) or label
        ds = s.get("description", "")
        if s.get("id_override_desc", True):
            tpl = str(s.get("id_desc_template") or "via {quelle} {detail}")
            ds = tpl.format_map(_SafeDict(quelle=label, detail=talker.detail or "", id=talker.dmr_id or "",
                                          call=cs, name=op, ort=talker.city or ""))
            ds = re.sub(r"\s+", " ", ds)
        return {"on": f"{cs}, {op}", "ds": _clean(ds, 60)}

    def _switch(self) -> None:
        """Verbindung gezielt trennen – _run meldet sofort mit want_identity neu an."""
        self.switching = True
        self._switch_tries = 0
        self.state = "meldet neu an"
        if self.writer:
            try:
                self.writer.close()
            except Exception:  # noqa: BLE001
                pass

    def _switch_error(self, why: str) -> None:
        """Fehler während einer Neuanmeldung. Der erste gehört zum gewollten Trennen."""
        self._switch_tries += 1
        if self._switch_tries > 3:
            self._switch_failed(why)

    def _switch_failed(self, why: str) -> None:
        self._switch_tries = 0
        self.router.event("warn", f"FRN: {why} – melde mit eigenem Operator an")
        self._ident_result(False, why)
        self.want_identity = None
        self.switching = False
        if self.tx_state != "idle":
            self.tx_state = "idle"
            self.tx_pending.clear()
            self.router.finished_tx(self)

    def _ident_result(self, ok: bool, info: str) -> None:
        w = self._ident_waiter
        if w is not None and not w.done():
            w.set_result((ok, info))

    def _schedule_restore(self) -> None:
        if self.identity is None or self.want_identity is not None and self.want_identity is not self.identity:
            return
        delay = float(self.section.get("id_restore_s", 10) or 10)
        gen = self.tx_gen
        if self._restore_h:
            self._restore_h.cancel()
        self._restore_h = asyncio.get_running_loop().call_later(delay, lambda: self._restore(gen))

    def _restore(self, gen: int) -> None:
        self._restore_h = None
        if gen != self.tx_gen or self.identity is None or self.tx_state != "idle":
            return
        if self.rx_active:           # jemand spricht auf FRN – später zurückwechseln
            self._restore_h = asyncio.get_running_loop().call_later(2.0, lambda: self._restore(gen))
            return
        self.want_identity = None
        self._switch()

    async def test_identity(self) -> tuple[bool, str, str]:
        """Einmal mit einem fremden Testoperator an- und danach wieder normal anmelden."""
        s = self.section
        if not self.online or self.writer is None:
            return False, "FRN nicht verbunden", "Die Bridge ist gerade nicht mit dem FRN-Server verbunden."
        if self.tx_state != "idle" or self.rx_active or self.switching:
            return False, "Gerade belegt", "Es läuft ein Durchgang – bitte gleich noch einmal versuchen."
        test = {"on": "DL0TEST, N8 Crosslink Test", "ds": "Test Operator-Wechsel", "test": True}
        loop = asyncio.get_running_loop()
        self._ident_waiter = loop.create_future()
        self.want_identity = test
        self._switch()
        try:
            ok, info = await asyncio.wait_for(self._ident_waiter, 25)
        except asyncio.TimeoutError:
            ok, info = False, "keine Antwort"
        finally:
            self._ident_waiter = None
        await asyncio.sleep(2.5 if ok else 0)
        self.want_identity = None
        if self.identity is not None:
            self._switch()
        for _ in range(100):
            if self.online and not self.switching and self.identity is None:
                break
            await asyncio.sleep(0.2)
        back = self.online and self.identity is None
        if ok:
            if s.get("id_override"):
                self.override_blocked = False
            return True, "Server nimmt fremden Operator an", (
                f"Anmeldung als „{test['on']}“ wurde angenommen ({info}). "
                + ("Danach wieder mit eigenem Operator angemeldet." if back else "Rückwechsel läuft noch – siehe Status.")
                + " Der Operator-Wechsel kann eingeschaltet werden.")
        return False, "Server lehnt fremden Operator ab", (
            f"Anmeldung als „{test['on']}“ wurde abgelehnt ({info}). Der Operator-Wechsel funktioniert mit diesem "
            "Server/Konto nicht. " + ("Die Bridge ist wieder normal angemeldet." if back else "Die Bridge meldet sich wieder normal an."))

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
            # Noch keine Freigabe: kurz warten, danach verwerfen (bei Neuanmeldung erst nach TX0)
            self.tx_late_grant = True
            if not self.switching:
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
        if self.identity is not None:
            self._schedule_restore()

    def extra_info(self) -> dict:
        return {"clients": self.clients, "access": self.access, "server_version": self.server_version,
                "net": self.section.get("net"), "net_info": self.net_info,
                "server": f"{self.section.get('server')}:{self.section.get('port')}",
                "tx_state": self.tx_state,
                "identity": (self.identity or {}).get("on", ""), "override_blocked": self.override_blocked}
