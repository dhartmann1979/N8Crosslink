<p align="center">
  <img src="docs/logo.png" width="160" alt="N8 Crosslink Logo">
</p>

<h1 align="center">N8 Crosslink</h1>
<p align="center"><b>FRN · DMR · Zello – eine Bridge, ein Dashboard, im Die-N8schicht-Design.</b><br>
Reines Python, ohne SvxLink, ohne MMDVM_Bridge, ohne Analog_Bridge.</p>

<p align="center">
  <img src="docs/screenshots/dashboard-live-frn.png" width="900" alt="Dashboard – FRN-Station spricht, wird nach DMR und Zello übertragen">
</p>

N8 Crosslink verbindet einen **FreeRadioNetwork-Raum (FRN)**, eine **DMR-Talkgroup** (HBlink4 / FreeDMR über das HomeBrew-Protokoll) und einen **Zello-Kanal** in alle Richtungen. Es löst damit zwei bisherige Lösungen ab:

* die **SvxLink-FRN↔DMR-Kette** (SvxLink + MMDVM_Bridge + Analog_Bridge) und
* die **bisherige Zello-Bridge**.

Alles läuft in **einem** Python-Dienst mit Live-Dashboard und Adminportal – im gleichen Look wie [dmr.die-n8schicht.de](https://dmr.die-n8schicht.de) und [frn.auf-der-nachtschicht.de](https://frn.auf-der-nachtschicht.de).

---

## Funktionen

| | |
|---|---|
| 🔀 **3-Wege-Routing** | FRN ↔ DMR ↔ Zello, jede der 6 Richtungen einzeln schaltbar (wirkt sofort) |
| 🎙️ **Sendeerkennung ohne VOX** | Beginn und Ende jeder Durchsage kommen aus dem jeweiligen Protokoll – nicht aus dem Audiopegel (Details unten) |
| 🛡️ **Schleifenschutz** | Immer nur eine aktive Quelle; alles andere wird gesperrt und als „blockiert“ protokolliert, plus Sperrzeit nach jeder Aussendung |
| 🏷️ **Stationsnamen überall** | FRN-Sprecher (aus der Raumliste), DMR-Rufzeichen (ID-Datenbank + empfangener Talker Alias) und Zello-Benutzer erscheinen im Dashboard, im Last Heard, als **DMR Talker Alias** (Embedded LC, 7-Bit) und als **Zello-Textnachricht** |
| 🎛️ **N8schicht-Vocoder** | Eigener Software-AMBE+2-Vocoder (Fork des DroidStar-Codecs, Quellen im Repository): nativ auf x86 und ARM (auch 32 Bit), eigener absturzsicherer Prozess, auf **Verständlichkeit gemessen abgestimmt** (ESTOI/PESQ), Frequenzgang bis 4 kHz. **Klang-Popup** mit Reglern, die live wirken, und Probehören (Eingang ↔ Ausgang, eigene WAV-Dateien). Alternativ **USB-Stick** (ThumbDV, DVstick 30, DV3000) oder AMBEserver |
| 📧 **FRN-Passwort anfordern** | Knopf im FRN-Adminbereich: Registrierung beim FRN-System-Manager, Ergebnis als Status-Popup, Passwort kommt per E-Mail |
| 🎧 **Mithören** | Angemeldete Admins hören die aktive Durchsage direkt im Browser mit (aus jedem Netz) – Knopf oben im Menü, Lautstärke im Dropdown am kleinen Pfeil. In der Statusleiste stehen Sprecher und eine **segmentierte Pegelanzeige** mit Spitzenwert |
| 💾 **Backup** | Alles als vollständig verschlüsselte Datei zum Download (AES-256-GCM). **Der Schlüssel ist das Superadmin-Passwort – im Passwortsafe aufbewahren!** Wiederherstellen im Webinterface, per CLI oder direkt im Installer |
| ♻️ **Neuanfang** | Zurücksetzen im Webinterface (Verlauf / Einstellungen / alles) und `uninstall.sh` mit „Daten behalten“ oder „komplett entfernen“, inkl. Wiedereinschalten der alten Dienste |
| 📊 **Dashboard** | On-Air-Anzeige mit Pegel und Zeit, Netzkarten mit RX/TX, Last Heard, FRN-Raumliste, Ereignisse, Statistik (Heute … 90 Tage) |
| ⚙️ **Adminportal** | Alle Einstellungen in SQLite, Benutzerverwaltung, Bridge-/Dienst-Neustart, ID-Datenbank-Update, Export/Import |
| 🔊 **Sprachansage & Sprechername** | Optional: Computerstimme sagt das Rufzeichen am Anfang des Durchgangs an (espeak-ng, Buchstaben oder NATO, je Zielnetz). Sprechername als FRN-Textnachricht – öffentlich oder **privat nur an ausgewählte Stationen** |
| 🐕 **Watchdogs** | Jede Verbindung (FRN, DMR, Zello) baut sich nach einem Abbruch selbst neu auf; zusätzlich baut ein Watchdog ein Netz komplett neu auf, wenn es zu lange offline bleibt oder seine Verbindungsschleife stirbt. Der Vocoder wird bei Ausfall neu geöffnet (AMBEserver im Lockstep mit neuem Socket nach jedem Timeout), und der systemd-Watchdog startet den Dienst neu, falls er hängt |
| 🗂️ **ID-Listen** | Alle Listen der FreeRadioID.net-API (alle DMR-IDs, registrierte IDs, Einzelabfrage unbekannter IDs) plus Talkgroup-Namen aus `n8schicht/talkgroup_ids.json` – 1× täglich und per Knopf |
| 🖼️ **Avatare** | In SQLite zwischengespeichert (192 px WebP), 1× täglich oder per Knopf aktualisiert: FreeRadioID-Bilder für DMR, Rufzeichen-Zuordnung für FRN und Zello, eigene Zello-Bilder per Upload |
| ⬆️ **Updates** | Prüfung stündlich zur vollen Stunde, Banner mit Änderungen, **„Update jetzt“** direkt im Webinterface |
| 🛠️ **Alles im Webinterface** | Dank eng begrenztem `sudo`: Dienst-Neustart, N8schicht-Vocoder bauen, alte Dienste (Start/Stopp/Autostart), Berechtigungen prüfen, Server-Neustart |
| 🧭 **Geführter Installer** | Fragt alles Schritt für Schritt ab, prüft und korrigiert bei jeder Installation und jedem Update die Berechtigungen, richtet sudo ein, löst auf Wunsch SvxLink & alte Zello-Bridge ab |

## Schnellstart

```bash
git clone https://github.com/dhartmann1979/N8Crosslink.git
cd N8Crosslink
sudo ./install.sh
```

Der Installer führt durch 9 Schritte (Pakete → venv → Login → FRN → DMR → Zello → Vocoder → Berechtigungen/sudo/Dienst). **Standard-Login: `n8schicht` / `n8schicht`** – das Dashboard erinnert daran, es zu ändern. Danach ist das Dashboard unter `http://<server>:8080` erreichbar (ist 8080 schon belegt, z. B. vom HBlink4-Dashboard, schlägt der Installer den nächsten freien Port vor).

➡️ Ausführlich: **[docs/INSTALLATION.md](docs/INSTALLATION.md)** · Umstieg von SvxLink/Zello-Bridge: **[docs/MIGRATION.md](docs/MIGRATION.md)**

## Wie die Sendeerkennung funktioniert (kein VOX)

| Netz | Durchsage beginnt | Durchsage endet |
|---|---|---|
| **FRN** | erstes Sprachpaket (`DT_VOICE_BUFFER`) mit Client-Index | kein Sprachpaket mehr für 1000 ms (wie SvxLink, einstellbar) |
| **DMR** | neue Stream-ID bzw. Voice-LC-Header | Terminator-with-LC (Fallback: 500 ms ohne Paket) |
| **Zello** | `on_stream_start` | `on_stream_stop` |

Der Audiopegel wird **nur angezeigt**, nie zum Schalten benutzt. Dadurch gibt es kein Abschneiden von Silben und kein Hängenbleiben bei Rauschen.

Senden in die Netze:

* **FRN:** `TX0` → Freigabe `DT_DO_TX` abwarten → je 200 ms `TX1` + 325 Byte GSM (WAV49) → `RX0`. Kommt keine Freigabe (Raum belegt), wird verworfen und gemeldet.
* **DMR:** 3× Voice-LC-Header, dann Sprach-Superframes im festen 60-ms-Takt (Vorpuffer einstellbar, Lücken werden mit AMBE-Stille gefüllt, damit Funkgeräte nicht abbrechen), Embedded LC und Talker Alias abwechselnd, Terminator-with-LC.
* **Zello:** optional Textnachricht mit dem Sprechernamen, `start_stream` (Opus 16 kHz, 60 ms) → Pakete im Takt → `stop_stream`.

## Screenshots

| Live (DMR-Station) | Live (Zello-Station) |
|---|---|
| ![DMR](docs/screenshots/dashboard-live-dmr.png) | ![Zello](docs/screenshots/dashboard-live-zello.png) |

| Statistik | Netze |
|---|---|
| ![Statistik](docs/screenshots/statistik.png) | ![Netze](docs/screenshots/netze.png) |

| Admin – Vocoder (N8schicht-Vocoder / USB-Stick) | Admin – Routing |
|---|---|
| ![Vocoder](docs/screenshots/admin-vocoder.png) | ![Routing](docs/screenshots/admin-routing.png) |

| Mithören (nur Admins) | Admin – Backup & Neuanfang |
|---|---|
| ![Mithören](docs/screenshots/dashboard-mithoeren.png) | ![Backup](docs/screenshots/admin-backup.png) |

| Admin – FRN: Passwort anfordern | Admin – FRN |
|---|---|
| ![FRN-Passwort](docs/screenshots/admin-frn-passwort-anfordern.png) | ![FRN](docs/screenshots/admin-frn.png) |

| Admin – ID-Listen & Avatare | Admin – Updates |
|---|---|
| ![ID-Listen](docs/screenshots/admin-idlisten-avatare.png) | ![Updates](docs/screenshots/admin-updates.png) |
| **🎨 Aussehen** – N8 Theme 2, gleiche Farbprofile wie die anderen N8-Seiten | **🌐 Englisch** – Umschalter DE \| EN oben rechts |
| ![Aussehen](docs/screenshots/admin-aussehen.png) | ![Englisch](docs/screenshots/dashboard-englisch.png) |

| Admin – System (Dienste über sudo, Demo ohne systemd) | Admin – DMR |
|---|---|
| ![System](docs/screenshots/admin-system.png) | ![DMR](docs/screenshots/admin-dmr.png) |

| Hinweise: Update & Standard-Login | Mobil |
|---|---|
| ![Banner](docs/screenshots/banner-update-passwort.png) | <img src="docs/screenshots/mobil.png" width="300"> |

## Dokumentation

* [Installation & Update](docs/INSTALLATION.md)
* [Konfiguration / Adminportal](docs/KONFIGURATION.md)
* [Vocoder: N8schicht-Vocoder (Klang, Messwerte, Test mit WAV) oder USB-Stick](docs/VOCODER.md)
* [Zello verbinden – Schritt für Schritt](docs/ZELLO.md)
* [Umstieg von SvxLink und der alten Zello-Bridge](docs/MIGRATION.md)
* [Technik & Protokolle](docs/TECHNIK.md)
* [Betrieb: Watchdogs, Updates, sudo & Berechtigungen](docs/BETRIEB.md)
* [Sicherheit, Sprache DE/EN & N8 Kit (gemeinsam mit HBlink4, adn-frn-server, N8-HotSpot)](docs/SICHERHEIT.md)
* [Backup & Wiederherstellung](docs/BACKUP.md)
* [Deinstallation & von vorn beginnen](docs/DEINSTALLATION.md)
* [Branding & Site-Icons](docs/BRANDING.md)
* [Fehlersuche](docs/FEHLERSUCHE.md)
* [Changelog](CHANGELOG.md)

## Tests

```bash
python3 tests/sim_e2e.py
```

Startet einen simulierten FRN-Server, einen simulierten HBlink-Master, einen simulierten Zello-Server und einen simulierten AMBE3000 und prüft alle Richtungen, Talker Alias, Textnachrichten, Start/Stop-Erkennung und den Schleifenschutz (aktuell 57/57 Prüfungen: FRN-Passwortanforderung, private FRN-Textnachricht, Sprachansage, alle Richtungen, zwei Durchsagen direkt hintereinander, Mithören, ID-Listen, Avatare, Verbindungsabbrüche mit Watchdog, Updateprüfung, verschlüsseltes Backup, Zurücksetzen und Wiederherstellen). `tests/test_vocoder.py` prüft den N8schicht-Vocoder (Ton, Bitfehler, Regler, Absturz/Neustart), `tools/vocoder_test.py` misst Eingang gegen Ausgang mit WAV-Dateien. `tests/test_fec.py` vergleicht die DMR-FEC bitgenau mit dmr_utils3. `tests/demo_server.py` startet dieselbe Simulation mit echtem Dashboard (Login `demo` / `demo12345`).

## Lizenz & Danksagung

**GPL-3.0-or-later** (siehe [LICENSE](LICENSE); bis Version 1.5 GPL-2.0). Die DMR-Fehlerschutzroutinen (BPTC, RS(12,9), Golay, QR, Embedded LC, Talker Alias) sind ein Python-Port aus [MMDVMHost](https://github.com/g4klx/MMDVMHost) von G4KLX; das FRN-Protokoll folgt dem FRN-Modul von [SvxLink](https://github.com/sm0svx/svxlink). Der **N8schicht-Vocoder** ist ein Fork des Software-Codecs aus [DroidStar](https://github.com/nostar/DroidStar) von Doug McLain (GPL-3.0-or-later); Quellen, Herkunft und Änderungen in [`third_party/n8schicht-vocoder`](third_party/n8schicht-vocoder/).

© Die N8schicht
