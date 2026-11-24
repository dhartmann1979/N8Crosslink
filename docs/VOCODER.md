# Vocoder: DroidStar (Software) oder USB-Stick

DMR überträgt Sprache als AMBE+2. Für den Übergang zu FRN (GSM) und Zello (Opus) muss N8 Crosslink AMBE+2 dekodieren und kodieren. Die Betriebsart wählst du im **Adminportal → 🎛️ Vocoder** (oder im Installer, Schritt 8). Nach dem Speichern startet die Bridge automatisch neu. **🧪 Vocoder testen** schickt einen 1-kHz-Ton über 25 Rahmen durch Encoder und Decoder und zeigt die Laufzeit je Rahmen und die Frequenz, die herauskommt.

| Betriebsart | Wann | Einstellungen |
|---|---|---|
| 🧠 **DroidStar** (Standard) | keine Zusatzhardware | keine – Bibliothek wird automatisch gefunden |
| 🔌 **USB-Stick** | ThumbDV, DVstick 30, DV3000 am selben Rechner | Gerät (`/dev/ttyUSB0` oder `/dev/serial/by-id/…`), Baudrate (460800 bzw. 230400 beim DV3000-Hat) |
| 🌐 **AMBEserver** | AMBE3000 hängt an einem anderen Rechner | Adresse/Port (Standard 2460) |
| 🧪 **Test** | nur Verbindungen testen | DMR-Audio ist stumm |

> **md380-emu wird ab Version 1.4.0 nicht mehr unterstützt.** Er lief auf x86 nur über den ARM-Emulator qemu und war die häufigste Ursache für Abstürze und Aussetzer. Beim Update wird eine md380-Einstellung automatisch auf DroidStar umgestellt und md380-emu deinstalliert (siehe unten).

## DroidStar-Vocoder

[DroidStar](https://github.com/nostar/DroidStar) von Doug McLain (AD8DP) bringt einen eigenen Software-Vocoder für AMBE+2 half-rate mit – genau das Format, das DMR benutzt (3600 bit/s mit FEC, 2450 bit/s Sprache). N8 Crosslink verwendet davon nur den Codec (Verzeichnis `mbe/`, C-Schnittstelle `ambe2.h`), nicht die DroidStar-App.

**Vorteile gegenüber md380-emu**

* läuft **nativ** auf x86 und ARM – kein qemu, keine Fremd-Firmware
* läuft **direkt in der Bridge** (per ctypes) – kein Zusatzdienst, kein UDP, nichts kann „hängen bleiben“ oder Pakete verlieren
* schnell: unter 1 ms je 20-ms-Rahmen für Encode + Decode auf einem normalen x86-Server
* Encoder und Decoder werden bei jeder neuen Übertragung zurückgesetzt; der Decoder überbrückt kaputte Rahmen (Wiederholen, Stummschalten, Komfortrauschen)

**Woher er kommt:** Der Vocoder ist **nicht** in diesem Repository enthalten. Der Installer lädt einen festen, geprüften Stand der DroidStar-Quellen von GitHub (`/usr/local/src/n8crosslink-droidstar`). Er übersetzt nur die Codec-Dateien mit `g++` – ohne Qt, die App wird nicht gebaut. Das Ergebnis ist `/opt/n8crosslink/lib/libambe2.so` (root, 644); daneben steht `libambe2.ref` mit dem Quellstand. Der Code von DroidStar steht unter GPL-3.0-or-later.

**Bauen / aktualisieren**

* automatisch im Installer (Schritt 8 → „DroidStar“) und bei jedem Update. Beim Update wird nur gebaut, wenn sich der festgelegte Quellstand geändert hat oder der Test fehlschlägt.
* im Webinterface: **Admin → 🎛️ Vocoder → „🔨 DroidStar-Vocoder bauen / aktualisieren“** (läuft über die sudo-Freigabe `install.sh --build-vocoder`)
* von Hand: `sudo /opt/n8crosslink/install.sh --build-vocoder`

Ablauf: `g++` und `git` installieren (falls nötig) → DroidStar-Quellen auf den festgelegten Stand bringen → Bibliothek bauen (ca. 30 s auf x86, 2–5 Min. auf einem Raspberry Pi) → Funktionstest mit 1-kHz-Ton. Erst wenn der Test eine Frequenz um 1 kHz zurückliefert, meldet der Installer Erfolg.

Von Hand testen: `cd /opt/n8crosslink && sudo -u n8crosslink venv/bin/python -m n8crosslink.cli vocoder-test --mode droidstar`
Ausgabe z. B. `OK droidstar: 0.6 ms je Rahmen, 1 kHz -> 997 Hz DroidStar AMBE+2 Quelle fc8e340a61d6`.

Einen anderen DroidStar-Stand bauen (nur für Tests): `sudo N8X_DROIDSTAR_REF=<commit> /opt/n8crosslink/install.sh --build-vocoder`.

**Klang:** Ein Software-Codec klingt nicht ganz wie der Original-Chip von DVSI. Wer die beste Sprachqualität will, nimmt einen USB-Stick (unten). Pegel lassen sich unter *Vocoder* (vor dem Kodieren / nach dem Dekodieren) und je Netz (RX/TX) anpassen.

## md380-emu wurde entfernt

Beim Update auf 1.4.0 (und bei `install.sh --build-vocoder`) geschieht automatisch:

1. Steht der Vocoder auf md380-emu, wird er auf **DroidStar** umgestellt; alte `md380_*`-Einstellungen werden aus der Datenbank gelöscht.
2. Der DroidStar-Vocoder wird gebaut und getestet.
3. **md380-emu wird deinstalliert:** Dienst `md380-emu` stoppen und deaktivieren, Unit-Datei löschen, Paket `md380-emu` entfernen (`apt purge`), `/opt/md380-emu` löschen und die sudo-Freigaben für md380-emu entfernen.
4. Die **DVSwitch-Paketquelle** wird nur entfernt, wenn keine anderen DVSwitch-Pakete mehr installiert sind (z. B. Analog_Bridge, MMDVM_Bridge). Sonst bleibt sie, und der Installer sagt, wer sie noch nutzt.
5. `qemu-user-static` bleibt installiert, weil es auch von anderen Programmen genutzt werden kann. Der Installer zeigt den Befehl zum Entfernen: `sudo apt purge qemu-user-static binfmt-support`.

> Hinweis: Eine alte DVSwitch-Kette (SvxLink → MMDVM_Bridge → Analog_Bridge → md380-emu) funktioniert danach nicht mehr. N8 Crosslink ersetzt sie ja; zum Zurückwechseln müsste md380-emu neu installiert werden.

## USB-Stick

* Der Dienstbenutzer `n8crosslink` ist in der Gruppe `dialout` – ein zusätzlicher AMBEserver ist **nicht** nötig.
* Stabilen Gerätenamen verwenden: **🔍 USB-Geräte suchen** im Adminportal schlägt `/dev/serial/by-id/…` vor.
* Beim Start sendet die Bridge Reset, Rate 33, Produkt-ID und Version; Gerät und Firmware erscheinen unter *Netze → Vocoder*.
* Nach einem Timeout werden offene Anfragen verworfen und der Stick neu synchronisiert.

## AMBEserver

AMBE3000-Paketprotokoll über UDP. Weil dieses Protokoll keine Sequenznummern hat, arbeitet N8 Crosslink hier **im Lockstep**: Es ist immer nur eine Anfrage unterwegs. Nach jedem Timeout wird ein **neuer UDP-Socket** geöffnet, damit eine verspätete Antwort keinem falschen Rahmen zugeordnet wird. Ein verlorenes Paket wird einmal wiederholt. *Antwortzeit je Rahmen* (Standard 300 ms) ist einstellbar.

## Watchdog

Antwortet der Vocoder länger als *Watchdog: neu öffnen nach* (Standard 20 s) nicht, öffnet die Bridge ihn komplett neu – beim DroidStar-Vocoder heißt das: Bibliothek neu laden, Encoder/Decoder neu anlegen. Die Zähler stehen unter *Netze → Vocoder* und *Admin → Vocoder*: Encode, Decode, Timeouts, Wiederholungen.

## Pegel

Unter *Vocoder* lassen sich die Pegel vor dem Kodieren und nach dem Dekodieren anpassen; zusätzlich gibt es pro Netz RX/TX-Pegel (FRN, DMR, Zello).
