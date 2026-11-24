# Vocoder: md380-emu oder USB-Stick

DMR überträgt Sprache als AMBE+2. Für den Übergang zu FRN (GSM) und Zello (Opus) muss N8 Crosslink AMBE+2 dekodieren und kodieren. Die Betriebsart wählst du im **Adminportal → 🎛️ Vocoder** (oder im Installer, Schritt 8). Nach dem Speichern startet die Bridge automatisch neu; mit **🧪 Vocoder testen** wird ein 1-kHz-Ton einmal kodiert und dekodiert und die Laufzeit angezeigt.

| Betriebsart | Wann | Einstellungen |
|---|---|---|
| 🧠 **md380-emu** | keine Zusatzhardware | Adresse/Port (Standard `127.0.0.1:2470`), Init-Pakete aus |
| 🔌 **USB-Stick** | ThumbDV, DVstick 30, DV3000 am selben Rechner | Gerät (`/dev/ttyUSB0` oder `/dev/serial/by-id/…`), Baudrate (460800 bzw. 230400 beim DV3000-Hat) |
| 🌐 **AMBEserver** | AMBE3000 hängt an einem anderen Rechner | Adresse/Port (Standard 2460) |
| 🧪 **Test** | nur Verbindungen testen | DMR-Audio ist stumm |

Alle Varianten sprechen das AMBE3000-Paketformat (Rate 33 = AMBE+2 3600/2450). Fällt der Vocoder aus, prüft die Bridge alle 20 s, ob er wieder antwortet; die Statusleiste zeigt den Zustand.

## md380-emu installieren

md380-emu stammt aus dem **DVSwitch**-Projekt (Emulation der AMBE-Routinen der MD-380-Firmware) und ist nicht in diesem Repository enthalten.

* Der Installer prüft, ob `md380-emu` vorhanden ist. Falls nicht, bietet er an, die DVSwitch-Paketquelle für deine Distribution einzurichten und `md380-emu` per apt zu installieren.
* Klappt das nicht (z. B. weil DVSwitch für deine Version keine Paketquelle anbietet), installiere md380-emu manuell nach der DVSwitch-Anleitung und starte danach `sudo systemctl restart n8crosslink`.
* md380-emu ist ARM-Code: auf dem Raspberry Pi läuft es nativ, auf x86 über `qemu-user-static` (der Installer installiert qemu dann mit).
* Gestartet wird es als Server auf UDP 2470: `md380-emu -S 2470` (Vorlage: `systemd/md380-emu.service`). Bringt DVSwitch bereits einen eigenen Dienst mit, wird dieser verwendet.

## USB-Stick

* Der Dienstbenutzer `n8crosslink` ist in der Gruppe `dialout` – ein zusätzlicher AMBEserver ist **nicht** nötig.
* Stabilen Gerätenamen verwenden: **🔍 USB-Geräte suchen** im Adminportal schlägt `/dev/serial/by-id/…` vor.
* Beim Start sendet die Bridge Reset, Rate 33, Produkt-ID und Version; Gerät und Firmware erscheinen unter *Netze → Vocoder*.

## Pegel

Unter *Vocoder* lassen sich die Pegel vor dem Kodieren und nach dem Dekodieren anpassen; zusätzlich gibt es pro Netz RX/TX-Pegel (FRN, DMR, Zello).
