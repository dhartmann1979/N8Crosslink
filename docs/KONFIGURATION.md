# Konfiguration / Adminportal

Anmelden über **🔐 Login** oben rechts – Standard **n8schicht / n8schicht** (bitte ändern, das Dashboard erinnert daran). Alle Werte liegen in SQLite (`/opt/n8crosslink/data/crosslink.db`); Passwörter werden nie im Klartext angezeigt (Feld leer lassen = unverändert).

## 🏠 Allgemein
| Feld | Bedeutung |
|---|---|
| Sperrzeit nach Aussendung | Nach dem Ende einer Durchsage nimmt die Bridge so lange nichts aus den Zielnetzen an (Ping-Pong-Schutz). Standard 600 ms |
| Vorpuffer DMR/Zello | Puffer vor dem Senden. FRN liefert 200-ms-Blöcke über TCP, daher 240 ms Standard. Hörbare Lücken → erhöhen |
| Time-Out-Timer | Maximale Dauer eines Durchgangs (Standard 180 s) |
| Hinweis-Banner / Links | erscheinen im Dashboard |
| Watchdog | Netz nach so vielen Sekunden offline komplett neu aufbauen (Standard 120 s) |
| Updateprüfung | stündlich zur vollen Stunde, Repository und Branch einstellbar |

Diese Werte wirken sofort; Web-Adresse und -Port erst nach *Dienst neu starten*.

## 🔀 Routing
Matrix mit allen sechs Richtungen. Wirkt sofort, ohne Neustart.

## 📻 FRN
Server, Backup-Server, Konto, Rufzeichen/Name (erscheint im FRN-Raum als „Rufzeichen, Name“), Client-Typ (0 = Crosslink, 1 = Gateway, 2 = PC Only), Band/Kanal, Raum. *Ende-Erkennung RX* ist die Zeit ohne Sprachpaket, nach der ein Durchgang als beendet gilt. Die FRN-Textnachricht mit dem Sprechernamen ist experimentell (nicht jeder FRN-Server/Client zeigt sie an).

## 📡 DMR
| Feld | Bedeutung |
|---|---|
| Peer-ID / Passwort | Zugang am HBlink4/FreeDMR |
| Quell-ID | DMR-ID, mit der Durchsagen aus FRN/Zello gesendet werden |
| Rufzeichen → eigene DMR-ID | Wenn das Rufzeichen des Sprechers in der ID-Datenbank steht, wird dessen ID als Quelle benutzt (aus = immer Quell-ID) |
| Empfangs-/Sende-TG, Zeitschlitz | 0 als Empfangs-TG = alle Gruppenrufe auf dem Zeitschlitz |
| RPTO | Optionen beim Login, z. B. `TS2=262` |
| Talker Alias | Stationsname im Sprachrahmen (Embedded LC, max. 31 Zeichen 7-Bit) – Funkgeräte zeigen ihn an |
| DMRA-Pakete | Talker Alias zusätzlich als Netzpaket. **Für HBlink4 ausgeschaltet lassen** – HBlink4 beantwortet DMRA mit MSTNAK |

## 💬 Zello
Server (`wss://zello.io/ws` bzw. `wss://zellowork.io/ws/NETZ`), Kanal, Konto, Authentifizierung: *Entwickler-Token* (30 Tage gültig, von developers.zello.com), *Issuer + Private Key* (die Bridge erzeugt selbst JWTs – für den Dauerbetrieb) oder *keine* (Zello Work). Text-Vorlage für den Sprechernamen mit `{name}`, `{callsign}`, `{source}`, `{detail}`.

## 🗂️ ID-Listen & Avatare
| Quelle | Verwendung |
|---|---|
| FreeRadioID `subscriber_ids.csv` (Ersatz `.json`, dann RadioID.net) | alle DMR-IDs → Rufzeichen + Vorname in Last Heard, On Air, Talker Alias |
| FreeRadioID `local_subscriber_ids.json` (Ersatz `.csv`) | bei FreeRadioID registrierte IDs → **FRID**-Kennzeichen, Avatare |
| FreeRadioID `dmr/user/?id=` | unbekannte ID wird live nachgeschlagen, der Name erscheint noch während der Durchsage |
| `n8schicht/talkgroup_ids.json` | Talkgroup-Namen (z. B. „TG 262 Deutschland“) |

Aktualisierung 1× täglich automatisch und per **„ID-Listen jetzt aktualisieren“**.

**Avatare** liegen in SQLite (192 px WebP) und werden 1× täglich oder per **„Avatare jetzt aktualisieren“** neu geladen:
* **DMR:** FreeRadioID-Profilbild (`idimg-<ID>.png`); der graue Platzhalter wird erkannt und nicht gespeichert.
* **FRN:** Rufzeichen → ID aus der Liste → FreeRadioID-Bild.
* **Zello:** Die Zello Channel API liefert keine Profilbilder. Daher: 1. eigenes Bild hochladen (pro Zello-Benutzer), 2. optionale URL-Vorlage mit `{username}`, 3. enthält der Zello-Name ein Rufzeichen (z. B. `dl1abc_hans`), dessen FreeRadioID-Bild.

## ⬆️ Updates
Installierte und neueste Version, Zeitpunkt der letzten Prüfung, Änderungen aus dem Changelog, **„Jetzt prüfen“**, **„Update jetzt installieren“** und das Protokoll des letzten Updates.

## 🎛️ Vocoder
siehe [VOCODER.md](VOCODER.md)

## 👥 Benutzer · 🛠️ System
Benutzer anlegen/löschen/Passwort ändern. System: **Dienste** (N8 Crosslink, md380-emu, erkannte alte Dienste wie svxlink/mmdvm_bridge/Zello-Bridge) mit Start, Stopp, Neustart, Autostart an/aus; **Berechtigungen prüfen & korrigieren**; **Server neu starten** (falls bei der Installation erlaubt); Bridge neu starten (nur die Netze), Dienst neu starten, ID-Listen aktualisieren, Konfiguration exportieren/importieren (ohne Passwörter), Ereignisprotokoll. Siehe [BETRIEB.md](BETRIEB.md).
