# Betrieb: Watchdogs, Updates, sudo & Berechtigungen

## Watchdogs

| Ebene | Was passiert |
|---|---|
| **FRN** | TCP-Keepalive, Polling mit `P`; bricht die Verbindung ab oder kommt 30 s nichts, wird neu verbunden (Backoff 5 s → 2 min, abwechselnd Haupt- und Backup-Server) |
| **DMR** | `RPTPING` alle 5 s; 30 s ohne `MSTPONG` → neuer Login; `MSTNAK`/`MSTCL` → neuer Login; DNS wird bei jedem Neuaufbau neu aufgelöst |
| **Zello** | WebSocket-Heartbeat 30 s; Abbruch oder Kanal „offline“ → neu verbinden (mit Refresh-Token) |
| **Bridge-Watchdog** (alle 10 s) | stirbt die Verbindungsschleife eines Netzes → sofortiger Neuaufbau; ist ein Netz länger als *Watchdog-Zeit* (Standard 120 s) offline → kompletter Neuaufbau (neue Sockets) |
| **Vocoder** | Gesundheitsprüfung alle 20 s; antwortet er 60 s nicht → wird neu geöffnet (z. B. USB-Stick ab- und wieder angesteckt) |
| **systemd** | `WatchdogSec=60`: meldet sich die Bridge nicht mehr (Event-Loop hängt), startet systemd den Dienst neu; `Restart=always` bei Absturz |

Jeder Verbindungsverlust und jede Wiederherstellung steht in den Ereignissen; Zähler (Wiederverbindungen, Neuaufbauten, letzter Grund, online/offline seit) unter **Netze**.

## Updates

Hinweis, Updates-Seite und Fortschritt kommen aus dem **N8 Kit** und sehen in N8 Crosslink, HBlink4-FreeRadioID, adn-frn-server und N8-HotSpot gleich aus (siehe [SICHERHEIT.md](SICHERHEIT.md#n8-kit)).

* Prüfung **stündlich zur vollen Stunde** (und kurz nach dem Start): Versionsnummer in `n8crosslink/__init__.py` auf GitHub (`dhartmann1979/N8Crosslink`, Branch `main`) gegen die installierte Version.
* Neue Version → Hinweis unter der Statusleiste für angemeldete Admins: *Update verfügbar: 1.6.0 → 1.7.0* mit **Was ist neu?** (aus `CHANGELOG.md`), **Jetzt aktualisieren**, **Details** (öffnet Admin → Updates) und **Später** (blendet den Hinweis für diese Version einen Tag aus).
* **Jetzt aktualisieren** öffnet ein Fenster mit den Neuerungen; nach der Bestätigung drei Schritte mit Fortschritt: *Update wird geladen und eingespielt → Dienst startet neu → Weboberfläche wird geprüft*. Technisch startet es über sudo `n8crosslink-update.service` (als root) → `update.sh --auto`: Quellen holen, Installer im Update-Modus (Abhängigkeiten, Berechtigungen, sudo-Freigaben), Dienst neu starten, Weboberfläche per HTTP prüfen. Antwortet sie nicht, stellt `update.sh` die vorige Version wieder her. Die Seite lädt danach von selbst neu.
* Ergebnis unter **Admin → Updates → Letztes Update** (*erfolgreich* oder *zurückgenommen*), gespeichert in `data/update.result` – dasselbe Format wie in den anderen N8schicht-Projekten.
* Ersatzweg ohne sudo: `n8crosslink-update.path` reagiert auf `data/update.request`.

![Updates](screenshots/admin-updates.png)

## sudo – alles über das Webinterface

Die Bridge läuft als eigener Benutzer **ohne** root-Rechte. Damit trotzdem alles im Webinterface geht, schreibt der Installer `/etc/sudoers.d/n8crosslink` mit **einzelnen, vollständigen Befehlen** (keine Platzhalter, keine Shell), z. B.

```
n8crosslink ALL=(root) NOPASSWD: /usr/bin/systemctl --no-block restart n8crosslink.service
n8crosslink ALL=(root) NOPASSWD: /usr/bin/systemctl --no-block start n8crosslink-update.service
n8crosslink ALL=(root) NOPASSWD: /opt/n8crosslink/install.sh --build-vocoder
n8crosslink ALL=(root) NOPASSWD: /opt/n8crosslink/install.sh --fix-perms
```

Freigegeben werden: Neustart der Bridge, Bauen des N8schicht-Vocoders (`install.sh --build-vocoder`), Update-Dienst und die bei der Installation erkannten alten Dienste (Start/Stopp/Neustart/Autostart), Berechtigungsprüfung und – nur wenn bei der Installation bestätigt – `systemctl reboot`. Die Datei wird vor dem Einspielen mit `visudo` geprüft und bei jedem Update neu erzeugt. Alles andere (Shell, andere Dienste) ist verboten.

## Berechtigungen

Programm, venv und Skripte gehören root und sind für den Dienst nur lesbar – wichtig, weil `update.sh` als root läuft. Nur `data/` gehört dem Dienst. Geprüft und korrigiert wird bei jeder Installation, jedem Update und auf Knopfdruck (siehe [INSTALLATION.md](INSTALLATION.md#berechtigungen)).
