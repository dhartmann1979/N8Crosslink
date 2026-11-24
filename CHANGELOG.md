# Changelog

Alle Änderungen an N8 Crosslink. Versionierung nach [SemVer](https://semver.org/lang/de/).

## [1.1.0] – 2026-11-24

Watchdogs, alle FreeRadioID-Listen, Talkgroup-Namen, Avatare, Updates per Knopf und volle Bedienung über das Webinterface.

### Watchdogs – Verbindungen bauen sich selbst wieder auf
- **Bridge-Watchdog** (alle 10 s): stirbt die Verbindungsschleife eines Netzes, wird es sofort neu aufgebaut; ist ein Netz länger als die *Watchdog-Zeit* (Standard 120 s, einstellbar) offline, wird es komplett neu aufgebaut (neue Sockets, neue DNS-Auflösung).
- **Vocoder-Watchdog**: antwortet md380-emu/USB-Stick/AMBEserver 60 s nicht, wird er neu geöffnet (z. B. nach Ab- und Anstecken des Sticks).
- **systemd-Watchdog**: Dienst läuft als `Type=notify` mit `WatchdogSec=60` – hängt die Bridge, startet systemd sie neu.
- FRN: TCP-Keepalive, sauberes Erkennen getrennter Verbindungen; Zello: Kanal „offline“ löst Neuverbindung aus.
- Jede verlorene und wiederhergestellte Verbindung erscheint in den Ereignissen; unter *Netze* stehen Wiederverbindungen, Neuaufbauten, letzter Grund und online/offline seit.

### ID-Listen
- Alle Listen der **FreeRadioID.net-API**: `subscriber_ids.csv` (alle IDs inkl. RadioID.net, Ersatz `.json`, dann RadioID.net), `local_subscriber_ids.json` (registrierte IDs, Ersatz `.csv`) und die Einzelabfrage `dmr/user/?id=` für unbekannte IDs – deren Name erscheint noch während der Durchsage.
- **Talkgroup-Namen** aus `github.com/dhartmann1979/n8schicht/…/talkgroup_ids.json` – im On Air, Last Heard und auf der DMR-Karte (z. B. „TG 262 Deutschland“).
- Aktualisierung **1× täglich** und per Knopf; Stand und Anzahl im neuen Adminbereich *🗂️ ID-Listen & Avatare*.
- **FRID**-Kennzeichen für bei FreeRadioID registrierte Stationen.
- Behoben: Die FreeRadioID-CSV hat keine Kopfzeile – bisher ging die erste Zeile verloren und das Land landete in der falschen Spalte.

### Avatare
- **In SQLite zwischengespeichert** (auf 192 px WebP verkleinert), **1× täglich** oder per Knopf neu geladen.
- DMR: FreeRadioID-Profilbilder, der graue Platzhalter wird erkannt.
- FRN: Rufzeichen → DMR-ID → FreeRadioID-Bild.
- **Zello**: Die Channel API liefert keine Profilbilder – daher eigene Bilder per Upload im Adminportal, optional eine URL-Vorlage mit `{username}` und automatische Zuordnung, wenn der Zello-Name ein Rufzeichen enthält.
- Avatare in On Air, Last Heard, FRN-Raumliste und Statistik.

### Updates
- **Updateprüfung stündlich zur vollen Stunde** gegen GitHub; Banner „Update verfügbar“ mit Änderungen aus dem Changelog.
- **„Update jetzt“** im Webinterface (Admin → ⬆️ Updates oder Banner): startet `n8crosslink-update.service` als root, Fortschritt und Protokoll im Adminportal, das Dashboard lädt nach dem Neustart automatisch.

### Alles über das Webinterface (sudo)
- Neues `/etc/sudoers.d/n8crosslink` mit ausschließlich einzeln freigegebenen Befehlen, vor dem Einspielen mit `visudo` geprüft, bei jedem Update neu erzeugt.
- Admin → 🛠️ System: Dienste (N8 Crosslink, md380-emu, erkannte alte Dienste wie svxlink/mmdvm_bridge/Zello-Bridge) starten, stoppen, neu starten, Autostart an/aus; Berechtigungen prüfen; Server-Neustart (nur wenn bei der Installation erlaubt).

### Berechtigungen
- Installer und Update **prüfen und korrigieren die Berechtigungen** jedes Mal (auch per Knopf und mit `install.sh --fix-perms`): Programm, venv und Skripte gehören root und sind für den Dienst nur lesbar, `data/` gehört dem Dienst (750, Datenbank 640), systemd-Units 644, Gruppe `dialout` bzw. Gerätegruppe des USB-Sticks.
- **Sicherheit:** In 1.0.0 gehörte `update.sh` dem Dienstbenutzer – da es jetzt als root läuft, ist es root-eigen und schreibgeschützt.

### Login
- **Standard-Login `n8schicht` / `n8schicht`** beim ersten Start (statt Superadmin-Abfrage); das Dashboard erinnert per Banner ans Ändern. Der Installer bietet an, gleich ein eigenes Passwort zu setzen.

### Tests & Doku
- Simulation auf **43 Prüfungen** erweitert: ID-Listen im FreeRadioID-Format, Talkgroups, Avatar-Cache/Refresh/Upload, Verbindungsabbrüche (FRN getrennt, DMR-Schleife abgestürzt, Zello weg) mit Watchdog, Updateprüfung.
- Neue Doku `docs/BETRIEB.md`, aktualisierte Installations-, Konfigurations- und Fehlersuche-Seiten, neue Screenshots (ID-Listen & Avatare, Updates, System, Hinweis-Banner).

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
