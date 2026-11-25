"""Beschreibung aller Einstellungen – für Dienste wie das HobbyRadioPortal (``GET/PUT /api/admin/settings``).

Format wie bei HBlink4-FreeRadioID: Bereiche mit Feldern
``{key: "abschnitt.schlüssel", label, kind, help, choices, min, max, value, default, depends, advanced, restart}``.
Arten: bool, int, float, text, longtext, choice, json, password. Passwörter werden nie ausgeliefert
(``value`` leer, ``set`` sagt, ob eins gespeichert ist). Die Texte entsprechen dem Adminportal (static/crosslink.js).
"""
from __future__ import annotations

import json
from typing import Any

from .db import DEFAULTS, SECRET_KEYS


class SettingsError(ValueError):
    pass


def _f(key: str, label: str, kind: str = "text", help: str = "", **kw: Any) -> dict:  # noqa: A002
    return {"key": key, "label": label, "kind": kind, "help": help, "choices": kw.get("choices", []),
            "min": kw.get("min"), "max": kw.get("max"), "depends": kw.get("depends"), "advanced": bool(kw.get("advanced")),
            "restart": bool(kw.get("restart"))}


PORT = {"min": 1, "max": 65535}
GAIN = {"min": -30, "max": 30}

SECTIONS: list[dict] = [
    {"id": "general", "title": "🏠 Allgemein", "help": "Name, Zeiten und Hinweis-Banner der Brücke. Wirkt sofort.", "fields": [
        _f("general.title", "Titel im Dashboard"),
        _f("general.server_name", "Servername / Domain"),
        _f("general.hang_time_ms", "Sperrzeit nach Aussendung (ms)", "int", "Schützt vor Ping-Pong zwischen den Netzen", min=0, max=10000),
        _f("general.jitter_ms", "Vorpuffer DMR/Zello-Ausgang (ms)", "int", "FRN liefert 200-ms-Blöcke – 240 ms sind ein guter Wert", min=0, max=2000),
        _f("general.tot_s", "Time-Out-Timer pro Durchgang (s)", "int", "Ein Durchgang wird nach dieser Zeit getrennt", min=10, max=3600),
        _f("general.keep_days", "Last Heard aufbewahren (Tage)", "int", min=1, max=3650),
        _f("general.watchdog_offline_s", "Watchdog: Netz nach … s offline komplett neu aufbauen", "int",
           "Zusätzlich zur normalen Wiederverbindung (Standard 120 s)", min=20, max=3600, advanced=True),
        _f("general.announcement", "Hinweis-Banner im Dashboard", "longtext"),
        _f("general.links", "Links-Menü", "json", "Liste mit name und url"),
        _f("general.web_host", "Web-Adresse (Bind)", help="0.0.0.0 = alle Schnittstellen · Neustart des Dienstes nötig", advanced=True, restart=True),
        _f("general.web_port", "Web-Port", "int", "Neustart des Dienstes nötig", advanced=True, restart=True, **PORT),
        _f("general.update_check", "Stündlich (zur vollen Stunde) auf Updates prüfen", "bool", advanced=True),
        _f("general.update_repo", "GitHub-Repository für Updates", advanced=True),
        _f("general.update_branch", "Branch", advanced=True),
    ]},
    {"id": "announce", "title": "🔊 Sprachansage", "help": "Computerstimme (espeak-ng) sagt das Rufzeichen am Anfang eines Durchgangs an, danach folgt der Ton – "
                                                         "der Durchgang läuft um die Länge der Ansage verzögert. Wirkt sofort.", "fields": [
        _f("general.announce_enabled", "Sprachansage des Rufzeichens am Anfang eines Durchgangs", "bool"),
        _f("general.announce_frn", "Ansage nach FRN", "bool", depends="general.announce_enabled"),
        _f("general.announce_dmr", "Ansage nach DMR", "bool", depends="general.announce_enabled"),
        _f("general.announce_zello", "Ansage nach Zello", "bool", depends="general.announce_enabled"),
        _f("general.announce_spell", "Rufzeichen sprechen als", "choice", depends="general.announce_enabled",
           choices=[["letters", "Buchstaben (D O 1 T E S T)"], ["nato", "NATO-Alphabet (Delta Oscar Eins …)"]]),
        _f("general.announce_text", "Ansagetext", help="Platzhalter: {call} = Rufzeichen, {name} = Name – z. B. „{call}“ oder „{call} {name}“",
           depends="general.announce_enabled"),
        _f("general.announce_repeat_min", "Je Station höchstens alle … Minuten", "int", "0 = bei jedem Durchgang", min=0, max=1440,
           depends="general.announce_enabled"),
        _f("general.announce_without_call", "Auch ohne Rufzeichen (Name ansagen)", "bool", depends="general.announce_enabled"),
        _f("general.announce_voice", "Stimme (espeak-ng)", help="z. B. de, en, de+f3", depends="general.announce_enabled", advanced=True),
        _f("general.announce_speed", "Sprechtempo (Wörter/Min.)", "int", min=80, max=400, depends="general.announce_enabled", advanced=True),
        _f("general.announce_level_db", "Lautstärke (dBFS Spitze)", "float", min=-40, max=0, depends="general.announce_enabled", advanced=True),
        _f("general.announce_pause_ms", "Pause nach der Ansage (ms)", "int", min=0, max=3000, depends="general.announce_enabled", advanced=True),
    ]},
    {"id": "routes", "title": "🔀 Routing", "help": "Welche Quelle wird in welches Netz übertragen? Wirkt sofort.", "fields": [
        _f("routes.frn_dmr", "FRN → DMR", "bool"), _f("routes.frn_zello", "FRN → Zello", "bool"),
        _f("routes.dmr_frn", "DMR → FRN", "bool"), _f("routes.dmr_zello", "DMR → Zello", "bool"),
        _f("routes.zello_frn", "Zello → FRN", "bool"), _f("routes.zello_dmr", "Zello → DMR", "bool"),
    ]},
    {"id": "frn", "title": "📻 FRN", "help": "Verbindung zum Free Radio Network. Änderungen gelten nach einem Neustart der Brücke.", "fields": [
        _f("frn.enabled", "FRN aktiv", "bool", restart=True),
        _f("frn.server", "Server", depends="frn.enabled", restart=True),
        _f("frn.port", "Port", "int", depends="frn.enabled", restart=True, **PORT),
        _f("frn.email", "E-Mail (FRN-Konto)", depends="frn.enabled", restart=True),
        _f("frn.password", "Passwort (FRN)", "password", "leer lassen = unverändert", depends="frn.enabled", restart=True),
        _f("frn.callsign", "Rufzeichen", depends="frn.enabled", restart=True),
        _f("frn.op_name", "Name / Bezeichnung", depends="frn.enabled", restart=True),
        _f("frn.client_type", "Client-Typ", "choice", depends="frn.enabled", restart=True,
           choices=[["0", "0 – Crosslink"], ["1", "1 – Gateway"], ["2", "2 – PC Only"]]),
        _f("frn.band", "Band / Kanal (BC)", help="„Crosslink“ oder z. B. 446.03125FM CTC131.8", depends="frn.enabled", restart=True),
        _f("frn.net", "Raum (Net)", depends="frn.enabled", restart=True),
        _f("frn.description", "Beschreibung", depends="frn.enabled", restart=True),
        _f("frn.country", "Land", depends="frn.enabled", restart=True),
        _f("frn.city", "Ort – Ortsteil / Locator", depends="frn.enabled", restart=True),
        _f("frn.rx_gain_db", "Pegel FRN → Bridge (dB)", "float", depends="frn.enabled", restart=True, **GAIN),
        _f("frn.tx_gain_db", "Pegel Bridge → FRN (dB)", "float", depends="frn.enabled", restart=True, **GAIN),
        _f("frn.text_messages", "Sprechername als FRN-Textnachricht", "bool", "Vor jedem Durchgang aus DMR/Zello, z. B. „DO1TEST Tobias (DMR)“",
           depends="frn.enabled", restart=True),
        _f("frn.text_targets", "Textnachricht nur an diese Stationen (privat)",
           help="Rufzeichen mit Komma, z. B. DL1ABC, DB0XYZ – leer = öffentlich an alle im Raum", depends="frn.enabled", restart=True),
        _f("frn.backup_server", "Backup-Server", depends="frn.enabled", advanced=True, restart=True),
        _f("frn.backup_port", "Backup-Port", "int", depends="frn.enabled", advanced=True, restart=True, **PORT),
        _f("frn.version", "Protokollversion", depends="frn.enabled", advanced=True, restart=True),
        _f("frn.rx_timeout_ms", "Ende-Erkennung RX (ms)", "int", "Kein Sprachpaket für diese Zeit = Durchgang beendet (SvxLink: 1000)",
           min=100, max=10000, depends="frn.enabled", advanced=True, restart=True),
        _f("frn.sysman_server", "System Manager (für „Passwort anfordern“)",
           help="Standard sysman.freeradionetwork.eu – bei eigenem FRN-Netz dessen System Manager", depends="frn.enabled", advanced=True),
        _f("frn.sysman_port", "System-Manager-Port", "int", depends="frn.enabled", advanced=True, **PORT),
    ]},
    {"id": "dmr", "title": "📡 DMR", "help": "Verbindung zum DMR-Server (HBlink4 / FreeDMR) als Repeater. Änderungen gelten nach einem Neustart der Brücke.", "fields": [
        _f("dmr.enabled", "DMR aktiv", "bool", restart=True),
        _f("dmr.host", "Server (HBlink4 / FreeDMR)", depends="dmr.enabled", restart=True),
        _f("dmr.port", "Port", "int", depends="dmr.enabled", restart=True, **PORT),
        _f("dmr.local_port", "Eigener UDP-Port", "int", "0 = beliebiger freier Port · fest z. B. für Firewall-Regeln",
           depends="dmr.enabled", advanced=True, restart=True, min=0, max=65535),
        _f("dmr.password", "Passwort (Passphrase)", "password",
           "leer lassen = unverändert · Bei HBlink4-FreeRadioID: persönliches FreeRadioID-Passwort – mit der Server-Passphrase ist die Bridge nur Gast "
           "und darf nicht in TG 262 senden", depends="dmr.enabled", restart=True),
        _f("dmr.peer_id", "Peer-/Repeater-ID", "int", "7- oder 9-stellig, muss am Server erlaubt sein", min=1, max=4294967295,
           depends="dmr.enabled", restart=True),
        _f("dmr.callsign", "Rufzeichen", depends="dmr.enabled", restart=True),
        _f("dmr.src_id", "Quell-ID für Sendungen ins DMR", "int", min=1, max=16777215, depends="dmr.enabled", restart=True),
        _f("dmr.use_db_id", "Rufzeichen → eigene DMR-ID, falls in der ID-Datenbank", "bool", depends="dmr.enabled", restart=True),
        _f("dmr.slot", "Zeitschlitz", "choice", choices=[["1", "TS1"], ["2", "TS2"]], depends="dmr.enabled", restart=True),
        _f("dmr.tg_rx", "Empfangs-Talkgroup", "int", "0 = alle Gruppenrufe auf dem Zeitschlitz", min=0, max=16777215, depends="dmr.enabled", restart=True),
        _f("dmr.tg_tx", "Sende-Talkgroup", "int", min=1, max=16777215, depends="dmr.enabled", restart=True),
        _f("dmr.color_code", "Color Code", "int", min=0, max=15, depends="dmr.enabled", restart=True),
        _f("dmr.options", "Optionen (RPTO)", help="z. B. TS2=262 – leer = Serverkonfiguration", depends="dmr.enabled", restart=True),
        _f("dmr.talker_alias", "Talker Alias (Stationsname) im Sprachrahmen senden", "bool", depends="dmr.enabled", restart=True),
        _f("dmr.rx_gain_db", "Pegel DMR → Bridge (dB)", "float", depends="dmr.enabled", restart=True, **GAIN),
        _f("dmr.tx_gain_db", "Pegel Bridge → DMR (dB)", "float", depends="dmr.enabled", restart=True, **GAIN),
        _f("dmr.send_dmra", "Zusätzlich DMRA-Pakete senden (nicht für HBlink4!)", "bool", depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.rx_timeout_ms", "Ende-Erkennung RX ohne Terminator (ms)", "int", min=100, max=10000, depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.rx_freq", "RX-Frequenz (Hz)", "int", min=0, max=9999999999, depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.tx_freq", "TX-Frequenz (Hz)", "int", min=0, max=9999999999, depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.power", "Leistung", "int", min=0, max=99, depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.height", "Antennenhöhe (m)", "int", min=0, max=999, depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.latitude", "Breite", depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.longitude", "Länge", depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.location", "Standort", depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.description", "Beschreibung", depends="dmr.enabled", advanced=True, restart=True),
        _f("dmr.url", "URL", depends="dmr.enabled", advanced=True, restart=True),
    ]},
    {"id": "zello", "title": "💬 Zello", "help": "Verbindung zu einem Zello-Kanal (Zello oder Zello Work). Änderungen gelten nach einem Neustart der Brücke.", "fields": [
        _f("zello.enabled", "Zello aktiv", "bool", restart=True),
        _f("zello.server", "WebSocket-Server", help="Zello: wss://zello.io/ws · Zello Work: wss://zellowork.io/ws/NETZ", depends="zello.enabled", restart=True),
        _f("zello.channel", "Kanal", depends="zello.enabled", restart=True),
        _f("zello.username", "Benutzername", depends="zello.enabled", restart=True),
        _f("zello.password", "Passwort", "password", "leer lassen = unverändert", depends="zello.enabled", restart=True),
        _f("zello.auth_mode", "Authentifizierung", "choice", depends="zello.enabled", restart=True,
           choices=[["token", "Entwickler-Token"], ["key", "Issuer + Private Key (JWT)"], ["none", "keine (Zello Work)"]]),
        _f("zello.auth_token", "Auth-Token", "password", "nur für „Entwickler-Token“ – leer lassen = unverändert", depends="zello.enabled", restart=True),
        _f("zello.issuer", "Issuer", help="nur für „Issuer + Private Key“", depends="zello.enabled", restart=True),
        _f("zello.private_key", "Private Key (PEM)", "password", "nur für „Issuer + Private Key“ – leer lassen = unverändert",
           depends="zello.enabled", restart=True),
        _f("zello.send_text", "Sprechername als Textnachricht in den Kanal", "bool", depends="zello.enabled", restart=True),
        _f("zello.text_template", "Text-Vorlage", help="Platzhalter: {name} {callsign} {source} {detail}", depends="zello.enabled", restart=True),
        _f("zello.rx_gain_db", "Pegel Zello → Bridge (dB)", "float", depends="zello.enabled", restart=True, **GAIN),
        _f("zello.tx_gain_db", "Pegel Bridge → Zello (dB)", "float", depends="zello.enabled", restart=True, **GAIN),
        _f("zello.sample_rate", "Abtastrate Senden", "choice", choices=[["16000", "16 kHz (empfohlen)"], ["8000", "8 kHz"]],
           depends="zello.enabled", advanced=True, restart=True),
        _f("zello.bitrate", "Opus-Bitrate (bit/s)", "int", min=6000, max=64000, depends="zello.enabled", advanced=True, restart=True),
        _f("zello.packet_ms", "Paketlänge (ms)", "choice", choices=[["20", "20 ms"], ["40", "40 ms"], ["60", "60 ms"]],
           depends="zello.enabled", advanced=True, restart=True),
        _f("zello.rx_timeout_ms", "Ende-Erkennung ohne stop_stream (ms)", "int", min=100, max=10000, depends="zello.enabled", advanced=True, restart=True),
    ]},
    {"id": "vocoder", "title": "🎛️ Vocoder", "help": "Wandelt Sprache zwischen DMR (AMBE+2) und FRN/Zello. Änderungen gelten nach einem Neustart der Brücke; "
                                                    "den Klang des N8schicht-Vocoders stellst du live über /api/admin/vocoder/options ein.", "fields": [
        _f("vocoder.vocoder_mode", "Vocoder", "choice", restart=True, choices=[
            ["n8vocoder", "🧠 N8schicht-Vocoder (Software)"], ["usb", "🔌 USB-Stick (AMBE3000)"],
            ["ambeserver", "🌐 AMBEserver (Netz)"], ["none", "🧪 Test ohne Vocoder"]]),
        _f("vocoder.n8vocoder_lib", "Bibliothek (leer = automatisch)", help="Standard: /opt/n8crosslink/lib/libn8vocoder.so", restart=True),
        _f("vocoder.usb_device", "Gerät", help="z. B. /dev/ttyUSB0 oder /dev/serial/by-id/…", restart=True),
        _f("vocoder.usb_baud", "Baudrate", "choice", restart=True,
           choices=[["460800", "460800 (ThumbDV / DVstick 30)"], ["230400", "230400 (DV3000 Pi-Hat)"], ["921600", "921600"]]),
        _f("vocoder.usb_send_init", "Init-Pakete (Reset/Rate) senden", "bool", restart=True),
        _f("vocoder.ambeserver_host", "AMBEserver Adresse", restart=True),
        _f("vocoder.ambeserver_port", "AMBEserver Port", "int", restart=True, **PORT),
        _f("vocoder.ambeserver_send_init", "Init-Pakete senden", "bool", restart=True),
        _f("vocoder.vocoder_enc_gain_db", "Pegel vor dem Kodieren (dB)", "float", restart=True, **GAIN),
        _f("vocoder.vocoder_dec_gain_db", "Pegel nach dem Dekodieren (dB)", "float", restart=True, **GAIN),
        _f("vocoder.vocoder_timeout_ms", "Antwortzeit je Rahmen (ms)", "int", "nur USB-Stick und AMBEserver", min=50, max=5000, restart=True),
        _f("vocoder.vocoder_restart_s", "Watchdog: neu öffnen nach (s) ohne Antwort", "int", min=5, max=600, restart=True),
    ]},
    {"id": "ids", "title": "🗂️ ID-Listen & Avatare", "help": "Woher DMR-IDs, Rufzeichen, Talkgroup-Namen und Avatare kommen. 1× täglich automatisch aktualisiert.", "fields": [
        _f("ids.avatars", "Avatare anzeigen", "bool"),
        _f("ids.only_registered", "Nur FreeRadioID-registrierte IDs abfragen", "bool"),
        _f("ids.match_callsign", "FRN-/Zello-Rufzeichen → FreeRadioID-Avatar", "bool"),
        _f("ids.avatar_url", "Avatar-URL DMR ({id})"),
        _f("ids.zello_avatar_url", "Avatar-URL Zello ({username}, optional)",
           help="Die Zello Channel API liefert keine Profilbilder – hier eine eigene Quelle eintragen oder Bilder im Crosslink-Dashboard hochladen"),
        _f("ids.subscriber_csv_url", "FreeRadioID: alle DMR-IDs (CSV)", advanced=True),
        _f("ids.subscriber_json_url", "FreeRadioID: alle DMR-IDs (JSON, Ersatz)", advanced=True),
        _f("ids.local_json_url", "FreeRadioID: registrierte IDs (JSON)", advanced=True),
        _f("ids.local_csv_url", "FreeRadioID: registrierte IDs (CSV, Ersatz)", advanced=True),
        _f("ids.user_api_url", "FreeRadioID: Einzelabfrage unbekannter IDs ({id})", advanced=True),
        _f("ids.radioid_fallback_url", "Ersatzquelle RadioID.net (CSV)", advanced=True),
        _f("ids.talkgroups_url", "Talkgroup-Namen (JSON)", advanced=True),
    ]},
]
FIELDS = {f["key"]: f for s in SECTIONS for f in s["fields"]}
# Für API-Token gesperrt: Netzwerk-Bindung und Update-Quelle des Dienstes
LOCKED_FOR_TOKEN = {"general.web_host", "general.web_port", "general.update_check", "general.update_repo", "general.update_branch"}
# Nicht über die Beschreibung: Aussehen (eigener Editor) und Klang-Regler (eigene Route)
NOT_DESCRIBED = {("general", "theme"), ("https", "email"), ("https", "staging"), ("https", "http_port"), ("https", "https_port"), ("vocoder", "n8vocoder_profile"), ("vocoder", "n8vocoder_options")}


def _split(key: str) -> tuple[str, str]:
    sec, _, k = key.partition(".")
    return sec, k


def describe(cfg: dict, api: bool = False) -> list[dict]:
    out = []
    for s in SECTIONS:
        fields = []
        for f in s["fields"]:
            if api and f["key"] in LOCKED_FOR_TOKEN:
                continue
            sec, k = _split(f["key"])
            val = cfg.get(sec, {}).get(k, DEFAULTS[sec][k])
            d = DEFAULTS[sec][k]
            item = dict(f, value=val, default=d)
            if f["kind"] == "choice":
                item["value"], item["default"] = str(val), str(d)
            if (sec, k) in SECRET_KEYS:
                item["set"] = bool(val)
                item["value"] = item["default"] = ""
            fields.append(item)
        out.append({"id": s["id"], "title": s["title"], "help": s["help"], "fields": fields})
    return out


def validate(changes: dict, api: bool = False) -> dict[str, dict]:
    """{"frn.port": 10024, …} -> {"frn": {"port": 10024}, …}; wirft SettingsError mit verständlicher Meldung."""
    if not isinstance(changes, dict):
        raise SettingsError("changes muss ein Objekt sein")
    out: dict[str, dict] = {}
    for key, raw in changes.items():
        f = FIELDS.get(key)
        if not f:
            raise SettingsError(f"Unbekannte Einstellung {key}")
        if api and key in LOCKED_FOR_TOKEN:
            raise SettingsError(f"{f['label']}: mit einem API-Token nicht änderbar")
        sec, k = _split(key)
        d, kind = DEFAULTS[sec][k], f["kind"]
        try:
            if kind == "bool":
                if isinstance(raw, bool):
                    v = raw
                elif str(raw).lower() in ("1", "true", "on", "ja", "yes", "0", "false", "off", "nein", "no"):
                    v = str(raw).lower() in ("1", "true", "on", "ja", "yes")
                else:
                    raise ValueError
            elif kind in ("int", "float"):
                v = int(float(raw)) if kind == "int" else float(raw)
            elif kind == "choice":
                if str(raw) not in [c[0] for c in f["choices"]]:
                    raise SettingsError(f"{f['label']}: ungültige Auswahl")
                v = int(raw) if isinstance(d, int) and not isinstance(d, bool) else str(raw)
            elif kind == "json":
                v = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(v, type(d)):
                    raise SettingsError(f"{f['label']}: {'Liste' if isinstance(d, list) else 'Objekt'} erwartet")
            else:
                v = "" if raw is None else str(raw)
                if len(v) > 20000:
                    raise SettingsError(f"{f['label']}: zu lang")
        except SettingsError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError):
            raise SettingsError(f"{f['label']}: {'ja oder nein' if kind == 'bool' else 'Zahl' if kind in ('int', 'float') else 'gültiger Wert'} erwartet") from None
        if kind in ("int", "float") and ((f["min"] is not None and v < f["min"]) or (f["max"] is not None and v > f["max"])):
            raise SettingsError(f"{f['label']}: {f['min']:g}–{f['max']:g}")
        if kind == "password" and v in ("", "********"):
            continue   # leer = unverändert
        out.setdefault(sec, {})[k] = v
    return out
