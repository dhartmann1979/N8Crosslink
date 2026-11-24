# Vocoder: md380-emu oder USB-Stick

DMR überträgt Sprache als AMBE+2. Für den Übergang zu FRN (GSM) und Zello (Opus) muss N8 Crosslink AMBE+2 dekodieren und kodieren. Die Betriebsart wählst du im **Adminportal → 🎛️ Vocoder** (oder im Installer, Schritt 8). Nach dem Speichern startet die Bridge automatisch neu; mit **🧪 Vocoder testen** wird ein 1-kHz-Ton einmal kodiert und dekodiert und die Laufzeit angezeigt.

| Betriebsart | Wann | Einstellungen |
|---|---|---|
| 🧠 **md380-emu** | keine Zusatzhardware | Adresse/Port (Standard `127.0.0.1:2470`), Init-Pakete aus |
| 🔌 **USB-Stick** | ThumbDV, DVstick 30, DV3000 am selben Rechner | Gerät (`/dev/ttyUSB0` oder `/dev/serial/by-id/…`), Baudrate (460800 bzw. 230400 beim DV3000-Hat) |
| 🌐 **AMBEserver** | AMBE3000 hängt an einem anderen Rechner | Adresse/Port (Standard 2460) |
| 🧪 **Test** | nur Verbindungen testen | DMR-Audio ist stumm |

Alle Varianten sprechen das AMBE3000-Paketformat (Rate 33 = AMBE+2 3600/2450). Fällt der Vocoder aus, prüft die Bridge alle 20 s, ob er wieder antwortet; die Statusleiste zeigt den Zustand.

## md380-emu installieren (Software-Vocoder)

md380-emu stammt aus dem **DVSwitch**-Projekt (Emulation der AMBE-Routinen der MD-380-Firmware). Er ist nicht in diesem Repository enthalten, sondern kommt als Paket aus der DVSwitch-Paketquelle. Einen öffentlichen Quellcode gibt es dafür nicht.

**Automatisch** – im Installer (Schritt 8 → „md380-emu“), bei jedem Update (wenn md380 eingestellt, aber nicht installiert ist) oder im Webinterface unter **Admin → 🎛️ Vocoder → „md380-emu installieren / reparieren“** (läuft über die sudo-Freigabe). Ablauf:

1. Vorhandenes md380-emu suchen (`md380-emu` im PATH, `/opt/md380-emu/md380-emu`, `/usr/local/bin`, `/usr/bin`).
2. Falls keins da ist: DVSwitch-Paketquelle einrichten mit `http://dvswitch.org/bookworm`. Das gilt für Debian 12 und 13, Raspberry Pi OS sowie Ubuntu 22.04/24.04; für Debian 11 wird `bullseye` genommen. Danach `apt install md380-emu`.
3. Ausführrechte setzen. Auf **x86** wird `qemu-user-static` + `binfmt-support` installiert, weil md380-emu ARM-Code ist. Auf dem Raspberry Pi läuft er nativ.
4. Dienst: Bringt das Paket einen eigenen `md380-emu.service` mit, wird er verwendet. Sonst richtet der Installer einen Dienst auf UDP 2470 ein und probiert die bekannten Startvarianten durch.
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
