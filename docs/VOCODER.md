# Vocoder: md380-emu oder USB-Stick

DMR überträgt Sprache als AMBE+2. Für den Übergang zu FRN (GSM) und Zello (Opus) muss N8 Crosslink AMBE+2 dekodieren und kodieren. Die Betriebsart wählst du im **Adminportal → 🎛️ Vocoder** (oder im Installer, Schritt 8). Nach dem Speichern startet die Bridge automatisch neu; mit **🧪 Vocoder testen** wird ein 1-kHz-Ton einmal kodiert und dekodiert und die Laufzeit angezeigt.

| Betriebsart | Wann | Einstellungen |
|---|---|---|
| 🧠 **md380-emu** | keine Zusatzhardware | Adresse/Port (Standard `127.0.0.1:2470`), Init-Pakete aus |
| 🔌 **USB-Stick** | ThumbDV, DVstick 30, DV3000 am selben Rechner | Gerät (`/dev/ttyUSB0` oder `/dev/serial/by-id/…`), Baudrate (460800 bzw. 230400 beim DV3000-Hat) |
| 🌐 **AMBEserver** | AMBE3000 hängt an einem anderen Rechner | Adresse/Port (Standard 2460) |
| 🧪 **Test** | nur Verbindungen testen | DMR-Audio ist stumm |

Alle Varianten sprechen das AMBE3000-Paketformat (Rate 33 = AMBE+2 3600/2450). Fällt der Vocoder aus, prüft die Bridge alle 20 s, ob er wieder antwortet; die Statusleiste zeigt den Zustand.

## Stabilität (ab 1.3.1)

Das AMBE3000-Paketformat hat **keine Sequenznummer**. Bis 1.3.0 wurde jede Antwort einfach der ältesten offenen Anfrage zugeordnet. Ging bei md380-emu ein UDP-Paket verloren oder kam eine Antwort zu spät, verschob sich die Zuordnung um einen Rahmen – und blieb verschoben. Hörbar war das als Knacken, Roboterstimme oder Aussetzer, die erst nach einem Neustart weg waren. Im Test mit absichtlich verlorenen und verspäteten Paketen waren 97 von 120 Rahmen falsch zugeordnet.

Jetzt gilt bei md380-emu und AMBEserver:

* **Eine Anfrage nach der anderen** (Lockstep) – md380-emu arbeitet ohnehin nur einen Rahmen gleichzeitig ab.
* **Nach einem Timeout neuer UDP-Socket** (neuer Quellport): Eine verspätete Antwort landet am alten Socket und wird verworfen; sie kann keiner neuen Anfrage mehr zugeordnet werden.
* **Ein zweiter Versuch** bei einem verlorenen Paket (abgeschaltet, sobald der Vocoder mehrfach hintereinander schweigt).
* **Watchdog:** Antwortet md380-emu länger als *Watchdog: neu starten nach* (Standard 20 s) nicht, startet die Bridge den Dienst `md380-emu` über die sudo-Freigabe neu und verbindet sich danach neu. Abschaltbar mit *Hängenden md380-emu-Dienst automatisch neu starten*.
* *Antwortzeit je Rahmen* (Standard 300 ms) einstellbar. md380-emu braucht normalerweise wenige Millisekunden.

Beim USB-Stick werden nach einem Timeout alle offenen Anfragen verworfen und kurz gewartet, bis der Stick wieder synchron ist.

Im Test ist jetzt kein Rahmen mehr falsch zugeordnet (`tests/test_vocoder.py`). Die Zähler stehen unter *Netze → Vocoder*: Timeouts, Wiederholungen, Dienst-Neustarts.

## Alternativen zu md380-emu

Für DMR braucht es AMBE+2. Ein freier, gleichwertiger Ersatz existiert nicht; Codec 2 oder M17 sind zu DMR **nicht** kompatibel. Was es gibt, nach Stabilität sortiert:

| Option | Stabilität | Aufwand | Bemerkung |
|---|---|---|---|
| **USB-Stick AMBE3000** (ThumbDV, DVstick 30, DV3000-Hat) | ★★★ sehr stabil | ca. 100–150 € | Original-Chip von DVSI, beste Sprachqualität, kein qemu. In N8 Crosslink schon eingebaut (Betriebsart *USB-Stick*). |
| **md380-emu nativ auf ARM** (Raspberry Pi 64 Bit) | ★★☆ stabil | keine Kosten, wenn ein Pi da ist | md380-emu ist ARM-Code. Auf x86 läuft er nur über qemu, das ist die häufigste Absturzursache. Auf einem Pi läuft er ohne Emulation. N8 Crosslink kann ihn über das Netz nutzen: Betriebsart *md380-emu*, Adresse = IP des Pi, Port 2470. |
| **AMBEserver mit USB-Stick an einem anderen Rechner** | ★★★ | Stick + kleiner Rechner | Betriebsart *AMBEserver*. |
| **md380-emu lokal über qemu** (x86) | ★☆☆ bis ★★☆ | keine Kosten | Ab 1.3.1 mit Lockstep, neuem Socket nach Timeout und automatischem Dienst-Neustart deutlich robuster. |

Andere Software-Vocoder (mbelib zum Dekodieren, der AMBE-Encoder aus OP25, die Vocoder-Plugins von DroidStar) sind zum Teil nur Decoder oder klingen deutlich schlechter. Bei allen ist die Patent- bzw. Lizenzlage unklar, deshalb sind sie nicht eingebaut.


## md380-emu installieren (Software-Vocoder)

md380-emu stammt aus dem **DVSwitch**-Projekt (Emulation der AMBE-Routinen der MD-380-Firmware). Er ist nicht in diesem Repository enthalten, sondern kommt als Paket aus der DVSwitch-Paketquelle. Einen öffentlichen Quellcode gibt es dafür nicht.

**Automatisch** – im Installer (Schritt 8 → „md380-emu“), bei jedem Update (wenn md380 eingestellt, aber nicht installiert ist) oder im Webinterface unter **Admin → 🎛️ Vocoder → „md380-emu installieren / reparieren“** (läuft über die sudo-Freigabe). Ablauf:

1. Vorhandenes md380-emu suchen (`md380-emu` im PATH, `/opt/md380-emu/md380-emu`, `/usr/local/bin`, `/usr/bin`).
2. Falls keins da ist: DVSwitch-Paketquelle einrichten mit `http://dvswitch.org/bookworm`. Das gilt für Debian 12 und 13, Raspberry Pi OS sowie Ubuntu 22.04/24.04; für Debian 11 wird `bullseye` genommen. Danach `apt install md380-emu`.
3. Ausführrechte setzen. Auf **x86** wird `qemu-user-static` + `binfmt-support` installiert, weil md380-emu ARM-Code ist. Auf dem Raspberry Pi läuft er nativ.
4. Dienst: Bringt das Paket einen funktionierenden `md380-emu.service` mit, wird er verwendet. Sonst richtet der Installer einen eigenen Dienst ein – so wie DVSwitch ihn startet, **über qemu-arm-static mit `-S 2470`**:
   1. mit dem `qemu-arm-static`, das neuere DVSwitch-Pakete in `/opt/md380-emu/` mitbringen (wichtig unter **Debian 13**: das System-qemu 10 bringt md380-emu zum Absturz),
   2. mit dem System-`qemu-arm-static`,
   3. direkt (ARM nativ).
   Der Dienst läuft als Benutzer `n8crosslink` (nicht als root) mit `NoNewPrivileges`/`ProtectSystem=strict`; `/opt/md380-emu` wird auf root gesetzt, damit ihn kein Benutzer verändern kann.
5. **Funktionstest:** Ein 1-kHz-Ton wird über UDP 2470 kodiert und wieder dekodiert. Erst wenn das klappt, meldet der Installer Erfolg.

Hinweise:
* DVSwitch bietet die Pakete für **amd64 und arm64** an. Auf 32-Bit-Raspberry-Pi-OS (armhf) gibt es keine aktuellen Pakete – dort ein 64-Bit-System oder einen USB-Stick nutzen.
* Von Hand testen: `cd /opt/n8crosslink && sudo -u n8crosslink venv/bin/python -m n8crosslink.cli vocoder-test --mode md380`

## USB-Stick

* Der Dienstbenutzer `n8crosslink` ist in der Gruppe `dialout` – ein zusätzlicher AMBEserver ist **nicht** nötig.
* Stabilen Gerätenamen verwenden: **🔍 USB-Geräte suchen** im Adminportal schlägt `/dev/serial/by-id/…` vor.
* Beim Start sendet die Bridge Reset, Rate 33, Produkt-ID und Version; Gerät und Firmware erscheinen unter *Netze → Vocoder*.

## Pegel

Unter *Vocoder* lassen sich die Pegel vor dem Kodieren und nach dem Dekodieren anpassen; zusätzlich gibt es pro Netz RX/TX-Pegel (FRN, DMR, Zello).
