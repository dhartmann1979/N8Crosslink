# Changelog

Alle Änderungen an N8 Crosslink. Versionierung nach [SemVer](https://semver.org/lang/de/).

## [1.0.0] – 2026-11-24

Erste Version: FRN, DMR und Zello in einer Python-Bridge mit Dashboard und Adminportal im Die-N8schicht-Design. Löst die SvxLink-FRN↔DMR-Kette (SvxLink + Analog_Bridge + MMDVM_Bridge) und die bisherige Zello-Bridge ab.

### Bridge
- **3-Wege-Routing** FRN ↔ DMR ↔ Zello, alle sechs Richtungen einzeln schaltbar, Änderungen wirken sofort.
- **Sendeerkennung ohne VOX**: Beginn/Ende kommen aus den Protokollen (FRN-Sprachpakete + Timeout wie SvxLink, DMR Voice-Header/Terminator, Zello `on_stream_start`/`on_stream_stop`). Der Pegel dient nur der Anzeige.
- **Schleifenschutz**: eine aktive Quelle, gleichzeitige Durchsagen anderer Netze werden blockiert und protokolliert; Sperrzeit nach jeder Aussendung; ein Netz, dessen Sendepuffer noch läuft, nimmt nichts an; Time-Out-Timer.
- **Stationsnamen auf allen Seiten**: FRN-Sprecher aus der Raumliste, DMR-Rufzeichen aus der ID-Datenbank (FreeRadioID, Ersatz radioid.net) und aus empfangenem Talker Alias, Zello-Benutzername. Weitergabe als DMR Talker Alias (Embedded LC, FLCO 0x04–0x07, abwechselnd mit dem Voice-LC) und als Zello-Textnachricht; optional als FRN-Textnachricht (experimentell).

### FRN
- Eigener FRN-Client in Python (Protokoll nach SvxLink ModuleFrn): Login als Client-Typ *Crosslink*, Raumliste, Polling/Keepalive, Backup-Server, automatische Wiederverbindung mit Backoff.
- Senden mit `TX0` → Freigabe abwarten → `TX1` + GSM WAV49 (325 Byte / 200 ms) → `RX0`; ohne Freigabe wird verworfen und gemeldet.

### DMR
- HomeBrew-Peer für HBlink4/FreeDMR: RPTL/RPTK/RPTC (302 Byte)/RPTO, Ping/Pong, Neu-Login bei Ausfall, MSTNAK/MSTCL-Behandlung.
- Vollständige Burst-Erzeugung: Voice-LC-Header, Superframes mit Sync/EMB/Embedded LC, Terminator – FEC (BPTC 196/96, RS 12/9, Golay 20/8, QR 16/7, Embedded LC 128/77) als Port aus MMDVMHost und gegen dmr_utils3 geprüft.
- Fester 60-ms-Sendetakt mit einstellbarem Vorpuffer, Lücken werden mit AMBE-Stille gefüllt.
- Optional DMRA-Pakete (standardmäßig aus, da HBlink4 darauf mit MSTNAK antwortet).

### Zello
- Zello Channel API über WebSocket: Entwickler-Token, Issuer + Private Key (JWT RS256) oder Zello Work; Refresh-Token bei Wiederverbindung.
- Opus 16 kHz / 60 ms mit FIR-Resampler, Senden im Takt mit Vorpuffer.

### Vocoder
- Im Adminportal wählbar: **md380-emu** (UDP 2470), **USB-Stick** (ThumbDV, DVstick 30, DV3000 direkt seriell) oder **AMBEserver** (UDP 2460); Testmodus ohne Vocoder.
- Init (Reset, Rate 33, Produkt-ID, Version), Gesundheitsprüfung alle 20 s, Test-Knopf mit Laufzeitmessung, Suche nach USB-Geräten.

### Dashboard & Adminportal
- Look 1:1 wie dmr.die-n8schicht.de / frn.auf-der-nachtschicht.de: Glas-Header mit Tabs, Statusleiste (Live, FRN, DMR, Zello, Vocoder), Kennzahlen, On-Air-Karte mit Pegel und Laufzeit, Netzkarten mit RX/TX und aktuellem Sprecher, Last Heard, FRN-Raumliste, Ereignisse.
- Statistik (Heute, 24 h, 7/30/90 Tage): Durchgänge, Sendezeit, Stationen, Blockiert, Aktivität pro Netz, aktivste Stationen, Tagesverlauf.
- Adminportal: Allgemein, Routing-Matrix, FRN, DMR, Zello, Vocoder, Benutzer, System (Bridge-/Dienst-Neustart, ID-Datenbank, Export/Import, Ereignisprotokoll).
- Superadmin-Einrichtung beim ersten Aufruf, Passwörter als PBKDF2-SHA256, Sitzungs-Cookies.
- Neues Logo „N8 Crosslink“ im Stil der N8schicht-Logos (Mond, Antenne, N8, Dreieck FRN·DMR·Zello, Pill „CROSSLINK“).

### Installation
- Geführter Installer in 9 Schritten inkl. Superadmin, aller drei Netze und Vocoder-Auswahl, md380-emu-Einrichtung, Erkennung und optionales Abschalten alter Dienste (svxlink, mmdvm_bridge, analog_bridge, zello), optional nginx + Let's Encrypt.
- `update.sh` (behält Einstellungen), `uninstall.sh` (sichert die Datenbank auf Wunsch), systemd-Dienst mit eigenem Benutzer.

### Tests
- `tests/sim_e2e.py`: Ende-zu-Ende-Simulation mit Fake-FRN-Server, Fake-HBlink, Fake-Zello und Fake-AMBE3000 – 28 Prüfungen (inkl. direkt aufeinanderfolgender Durchsagen ohne Stream-Überlappung).
- `tests/test_fec.py`: DMR-FEC bitgenau gegen dmr_utils3 (200 Zufalls-LCs + EMB-Muster).
- `tests/demo_server.py` + `tests/screenshots.py`: Demo-Betrieb und automatische Doku-Screenshots.
