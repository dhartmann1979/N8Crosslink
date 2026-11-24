"""Bridge-Kern: Talker, Port-Basisklasse und der 3-Wege-Router.

Sendeerkennung ohne VOX
-----------------------
Jede Seite meldet Beginn und Ende einer Durchsage über ihr Protokoll:

* FRN   – erstes Sprachpaket (DT_VOICE_BUFFER) mit Client-Index = Beginn,
          kein Paket mehr für ``rx_timeout_ms`` (Standard 1000 ms, wie SvxLink) = Ende
* DMR   – neue Stream-ID / Voice-LC-Header = Beginn, Terminator-with-LC = Ende
          (Fallback: ``rx_timeout_ms`` ohne Paket)
* Zello – ``on_stream_start`` = Beginn, ``on_stream_stop`` = Ende

Der Audiopegel wird nur angezeigt, nie zum Schalten benutzt.

Schleifenschutz
---------------
Es gibt immer nur eine aktive Quelle. Solange sie spricht, wird alles, was auf
den Zielnetzen ankommt, verworfen (und als "blockiert" protokolliert). Nach dem
Ende bleibt jedes Zielnetz noch ``hang_time_ms`` lang für Empfang gesperrt.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field

from .audio.dsp import level_dbfs

log = logging.getLogger("router")

PORT_LABELS = {"frn": "FRN", "dmr": "DMR", "zello": "Zello"}


@dataclass
class Talker:
    source: str
    name: str                 # Anzeigename, z. B. "DL1ABC Hans"
    callsign: str = ""
    detail: str = ""          # Raum / TG / Kanal
    dmr_id: int | None = None
    city: str = ""
    extra: dict = field(default_factory=dict)

    def short(self) -> str:
        return self.name or self.callsign or "unbekannt"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label"] = PORT_LABELS.get(self.source, self.source)
        return d


class Port:
    key = "port"
    label = "Port"

    def __init__(self, router: "Router", cfg: dict) -> None:
        self.router = router
        self.cfg = cfg
        self.section = cfg.get(self.key, {})
        self.online = False
        self.state = "aus"
        self.detail = ""
        self.rx_active = False
        self.tx_active = False
        self.rx_level = -90.0
        self.tx_level = -90.0
        self.tx_talker: Talker | None = None
        self.counters = {"rx": 0, "tx": 0, "rx_s": 0.0, "tx_s": 0.0}
        self._tasks: list[asyncio.Task] = []
        self.main_task: asyncio.Task | None = None
        # Watchdog-Daten
        self.offline_since: float | None = time.time()
        self.online_since: float | None = None
        self.was_online = False
        self.reconnects = 0
        self.wd_restarts = 0
        self.last_wd_reason = ""

    @property
    def enabled(self) -> bool:
        return bool(self.section.get("enabled", False))

    async def start(self) -> None:  # pragma: no cover - überschrieben
        pass

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except BaseException:  # noqa: BLE001
                pass
        self._tasks.clear()
        self.main_task = None
        if self.online:
            self.offline_since = time.time()
        self.online = False
        self.online_since = None
        self.state = "gestoppt"

    def spawn(self, coro) -> asyncio.Task:  # noqa: ANN001
        t = asyncio.create_task(coro)
        self._tasks.append(t)
        return t

    # --- TX-Seite (vom Router aufgerufen) -----------------------------------
    def tx_begin(self, talker: Talker) -> None:
        raise NotImplementedError

    def tx_audio(self, pcm: bytes) -> None:
        raise NotImplementedError

    def tx_end(self) -> None:
        raise NotImplementedError

    def can_tx(self) -> bool:
        return self.enabled and self.online

    def info(self) -> dict:
        return {"key": self.key, "label": self.label, "enabled": self.enabled, "online": self.online,
                "state": self.state, "detail": self.detail, "rx": self.rx_active, "tx": self.tx_active,
                "rx_level": round(self.rx_level, 1), "tx_level": round(self.tx_level, 1),
                "tx_talker": self.tx_talker.to_dict() if self.tx_talker else None,
                "counters": self.counters, "watchdog": self.watchdog_info(), **self.extra_info()}

    def extra_info(self) -> dict:
        return {}

    def set_state(self, online: bool, state: str, detail: str = "") -> None:
        changed = (online, state, detail) != (self.online, self.state, self.detail)
        if online and not self.online:
            if self.was_online:
                self.reconnects += 1
                self.router.event("info", f"{self.label}: Verbindung wiederhergestellt"
                                  + (f" nach {int(time.time() - self.offline_since)} s" if self.offline_since else ""))
            self.was_online = True
            self.online_since = time.time()
            self.offline_since = None
        elif not online and self.online:
            self.offline_since = time.time()
            self.online_since = None
            self.router.event("warn", f"{self.label}: Verbindung verloren ({state}{' – ' + detail if detail else ''}) – Watchdog baut sie neu auf")
        self.online, self.state, self.detail = online, state, detail
        if changed:
            self.router.notify()

    def watchdog_info(self) -> dict:
        return {"reconnects": self.reconnects, "wd_restarts": self.wd_restarts, "wd_reason": self.last_wd_reason,
                "online_since": self.online_since, "offline_since": self.offline_since}


@dataclass
class Session:
    source: Port
    talker: Talker
    targets: list[Port]
    started: float
    lh_id: int
    last_audio: float
    frames: int = 0


class Router:
    def __init__(self, db, cfg: dict) -> None:  # noqa: ANN001
        self.db = db
        self.cfg = cfg
        self.ports: dict[str, Port] = {}
        self.active: Session | None = None
        self.guard_until: dict[str, float] = {}
        self.blocked: dict[str, tuple[int, float]] = {}
        self.listeners: set[asyncio.Queue] = set()
        self.audio_listeners: set[asyncio.Queue] = set()   # Mithören (nur angemeldete Admins)
        self._dirty = asyncio.Event()
        self.started = time.time()
        self.vocoder = None

    # ------------------------------------------------------------ Konfiguration
    @property
    def g(self) -> dict:
        return self.cfg["general"]

    def route_ok(self, src: str, dst: str) -> bool:
        return bool(self.cfg["routes"].get(f"{src}_{dst}", False))

    # ------------------------------------------------------------ Ereignisse
    def notify(self) -> None:
        self._dirty.set()

    def event(self, level: str, text: str) -> None:
        log.log(logging.WARNING if level == "warn" else logging.INFO, text)
        try:
            self.db.event(level, text)
        except Exception:  # noqa: BLE001
            pass
        self.broadcast({"type": "event", "ts": time.time(), "level": level, "text": text})

    def broadcast(self, msg: dict) -> None:
        for q in list(self.listeners):
            if q.qsize() < 200:
                q.put_nowait(msg)

    def snapshot(self) -> dict:
        s = self.active
        return {
            "type": "state",
            "ts": time.time(),
            "uptime": time.time() - self.started,
            "ports": {k: p.info() for k, p in self.ports.items()},
            "vocoder": self.vocoder.status() if self.vocoder else None,
            "active": None if not s else {
                "source": s.source.key, "talker": s.talker.to_dict(), "since": s.started,
                "targets": [t.key for t in s.targets],
            },
            "routes": self.cfg["routes"],
            "update": {k: v for k, v in getattr(self, "updater").state.items() if k != "notes"}
                      if getattr(self, "updater", None) else None,
        }

    async def publisher(self) -> None:
        """Schickt Statusänderungen sofort, Pegel 5x pro Sekunde während einer Durchsage."""
        while True:
            try:
                await asyncio.wait_for(self._dirty.wait(), timeout=0.2 if self.active else 2.0)
            except asyncio.TimeoutError:
                pass
            self._dirty.clear()
            self.broadcast(self.snapshot())
            self._check_tot()

    def _check_tot(self) -> None:
        s = self.active
        if s and time.time() - s.started > float(self.g.get("tot_s", 180)):
            self.event("warn", f"Time-Out: {s.talker.short()} ({s.source.label}) nach {int(time.time()-s.started)} s getrennt")
            self._finish(s, status="timeout")

    # ------------------------------------------------------------ RX-Schnittstelle
    def rx_begin(self, port: Port, talker: Talker) -> bool:
        now = time.time()
        port.rx_active = True
        port.counters["rx"] += 1
        reason = None
        if self.active is not None:
            reason = f"belegt durch {self.active.talker.short()} ({self.active.source.label})"
        elif port.tx_talker is not None:
            reason = "eigene Aussendung läuft noch"
        elif now < self.guard_until.get(port.key, 0):
            reason = "Sperrzeit nach eigener Aussendung"
        if reason:
            lh = self.db.lh_insert({"ts_start": now, "source": port.key, "name": talker.name,
                                    "callsign": talker.callsign, "detail": talker.detail,
                                    "dmr_id": talker.dmr_id, "targets": [], "status": "blocked"})
            self.blocked[port.key] = (lh, now)
            self.event("warn", f"{talker.short()} auf {port.label} nicht übertragen – {reason}")
            self.notify()
            return False
        targets = [p for k, p in self.ports.items()
                   if k != port.key and self.route_ok(port.key, k) and p.can_tx()]
        lh = self.db.lh_insert({"ts_start": now, "source": port.key, "name": talker.name,
                                "callsign": talker.callsign, "detail": talker.detail,
                                "dmr_id": talker.dmr_id, "targets": [t.key for t in targets], "status": "live"})
        self.active = Session(port, talker, targets, now, lh, now)
        for t in targets:
            try:
                t.tx_active = True
                t.tx_talker = talker
                t.counters["tx"] += 1
                t.tx_begin(talker)
            except Exception as e:  # noqa: BLE001
                log.exception("tx_begin %s: %s", t.key, e)
        dest = ", ".join(t.label for t in targets) or "– (kein Ziel online)"
        log.info("RX %s: %s -> %s", port.label, talker.short(), dest)
        self.broadcast({"type": "talk_start", "source": port.key, "talker": talker.to_dict(),
                        "targets": [t.key for t in targets], "ts": now})
        for q in list(self.audio_listeners):
            q.put_nowait({"type": "start", "source": port.key, "talker": talker.to_dict()})
        self.notify()
        return True

    def rx_audio(self, port: Port, pcm: bytes) -> None:
        s = self.active
        lvl = level_dbfs(pcm)
        port.rx_level = lvl
        if not s or s.source is not port:
            return
        s.last_audio = time.time()
        s.frames += 1
        for q in list(self.audio_listeners):
            if q.qsize() < 100:          # ~2 s Rückstau, danach verwerfen (langsamer Client)
                q.put_nowait(pcm)
        for t in s.targets:
            t.tx_level = lvl
            try:
                t.tx_audio(pcm)
            except Exception as e:  # noqa: BLE001
                log.exception("tx_audio %s: %s", t.key, e)

    def rx_update_talker(self, port: Port, **kw) -> None:  # noqa: ANN003
        s = self.active
        if s and s.source is port:
            for k, v in kw.items():
                setattr(s.talker, k, v)
            self.db.lh_update(s.lh_id, **{k: v for k, v in kw.items() if k in ("name", "callsign")})
            self.notify()

    def rx_end(self, port: Port) -> None:
        port.rx_active = False
        port.rx_level = -90.0
        if port.key in self.blocked:
            lh, t0 = self.blocked.pop(port.key)
            self.db.lh_update(lh, ts_end=time.time(), duration=round(time.time() - t0, 1))
            self.notify()
        s = self.active
        if s and s.source is port:
            self._finish(s)

    def _finish(self, s: Session, status: str = "ok") -> None:
        now = time.time()
        dur = now - s.started
        hang = float(self.g.get("hang_time_ms", 600)) / 1000.0
        for t in s.targets:
            try:
                t.tx_end()
            except Exception as e:  # noqa: BLE001
                log.exception("tx_end %s: %s", t.key, e)
            t.tx_active = False
            t.tx_level = -90.0
            t.counters["tx_s"] += dur
            self.guard_until[t.key] = now + hang
        s.source.counters["rx_s"] += dur
        self.db.lh_update(s.lh_id, ts_end=now, duration=round(dur, 1), status=status)
        self.active = None
        for q in list(self.audio_listeners):
            q.put_nowait({"type": "end"})
        self.broadcast({"type": "talk_end", "source": s.source.key, "talker": s.talker.to_dict(),
                        "duration": round(dur, 1), "ts": now})
        log.info("Ende %s: %s (%.1f s)", s.source.label, s.talker.short(), dur)
        self.notify()

    def finished_tx(self, port: Port) -> None:
        """Ein Ziel hat seine Aussendung tatsächlich beendet (z. B. Puffer leer)."""
        port.tx_talker = None
        hang = float(self.g.get("hang_time_ms", 600)) / 1000.0
        self.guard_until[port.key] = max(self.guard_until.get(port.key, 0), time.time() + hang)
        self.notify()
