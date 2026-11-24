# Konfiguration / Adminportal

Anmelden über **🔐 Login** oben rechts. Beim allerersten Aufruf ohne Benutzer erscheint ein Banner „Superadmin anlegen“. Alle Werte liegen in SQLite (`/opt/n8crosslink/data/crosslink.db`); Passwörter werden nie im Klartext angezeigt (Feld leer lassen = unverändert).

## 🏠 Allgemein
| Feld | Bedeutung |
|---|---|
| Sperrzeit nach Aussendung | Nach dem Ende einer Durchsage nimmt die Bridge so lange nichts aus den Zielnetzen an (Ping-Pong-Schutz). Standard 600 ms |
| Vorpuffer DMR/Zello | Puffer vor dem Senden. FRN liefert 200-ms-Blöcke über TCP, daher 240 ms Standard. Hörbare Lücken → erhöhen |
| Time-Out-Timer | Maximale Dauer eines Durchgangs (Standard 180 s) |
| Hinweis-Banner / Links | erscheinen im Dashboard |

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
| ID-Datenbank | CSV-URL (Standard FreeRadioID, Ersatz radioid.net), tägliche Aktualisierung |

## 💬 Zello
Server (`wss://zello.io/ws` bzw. `wss://zellowork.io/ws/NETZ`), Kanal, Konto, Authentifizierung: *Entwickler-Token* (30 Tage gültig, von developers.zello.com), *Issuer + Private Key* (die Bridge erzeugt selbst JWTs – für den Dauerbetrieb) oder *keine* (Zello Work). Text-Vorlage für den Sprechernamen mit `{name}`, `{callsign}`, `{source}`, `{detail}`.

## 🎛️ Vocoder
siehe [VOCODER.md](VOCODER.md)

## 👥 Benutzer · 🛠️ System
Benutzer anlegen/löschen/Passwort ändern. System: Bridge neu starten (nur die Netze), Dienst neu starten (ganzer Prozess), ID-Datenbank aktualisieren, Konfiguration exportieren/importieren (ohne Passwörter), Ereignisprotokoll.
