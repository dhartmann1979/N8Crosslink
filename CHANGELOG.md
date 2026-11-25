# Changelog

Alle Änderungen an N8 Crosslink. Versionierung nach [SemVer](https://semver.org/lang/de/).

## [1.15.0] – 2026-11-25

**📋 Öffentliches FRN-Fehlerprotokoll eingebunden – der Grund für abgelehnte FRN-Anmeldungen steht jetzt direkt im Adminportal.**

### 📋 FRN-Fehlerprotokoll (freeradionetwork.de)
- Der FRN-Server nennt bei einer Ablehnung meist keinen Grund; der FRN System Manager schreibt ihn aber in das öffentliche Fehlerprotokoll
  (<http://log.freeradionetwork.de:60080/error_log.php>, auf freeradionetwork.de unter *Hilfe → Fehlerprotokoll*). N8 Crosslink nutzt es jetzt
  überall, wo FRN im Spiel ist:
  - **Admin → 📻 FRN → 📋 FRN-Fehlerprotokoll:** Einträge zu eigenem Rufzeichen (Client) und den eigenen FRN-Servern (Server, Backup-Server),
    gleiche Meldungen zusammengefasst („7× seit 09:47“), mit deutscher Erklärung und Abhilfe; Abzeichen „nichts zu dir“ / „8 Einträge zu dir“ /
    „nicht erreichbar“; **🔄 Neu laden** und **📋 Komplettes Fehlerprotokoll öffnen**.
  - **Automatisch nach jedem FRN-Problem** (Login `WRONG`/`BLOCK`, Trennung, Verbindungsfehler): ein paar Sekunden später Blick ins Protokoll
    (höchstens alle 2 Minuten) und der Grund als Eintrag im **Ereignisprotokoll** – jede Meldung nur einmal. Die Meldung „FRN-Login abgelehnt“
    verweist darauf.
  - **`install.sh --diagnose`** gibt die passenden Einträge mit aus.
- Bekannte Meldungen mit Abhilfe: *wrong FRN password* (Passwort anfordern, genau das zugeteilte eintragen), *multiple connections …*
  (zweite Instanz mit denselben Zugangsdaten), *not listening on specified port* (Firewall/Portweiterleitung); weitere (gesperrt, unbekannt,
  Version, E-Mail) per Stichwort; Unbekanntes erscheint unverändert mit dem englischen Hinweis.
- Neues Modul `n8crosslink/frn_errorlog.py` (Abruf als JSON `?action=getLog`, 60 s Zwischenspeicher, Auswertung, Zuordnung, Zusammenfassung).
  API: `GET /api/admin/frn/errorlog[?force=1]` – Admins und das HobbyRadioPortal auf demselben Rechner.
- Tests: `tests/test_frn_errorlog.py` (Format, Zuordnung, Zusammenfassen, API, nicht erreichbar, automatische Meldung nur einmal).
  Die Demo zeigt ein Beispielprotokoll.

## [1.14.1] – 2026-11-25

**🐛 Domains & HTTPS und Berechtigungskorrektur scheiterten aus dem Webinterface mit „Read-only file system“.**

### 🐛 Behoben
- Der Dienst läuft mit `ProtectSystem=full`: `/etc` und `/usr` sind für ihn schreibgeschützt – und das erbt auch alles, was er per sudo
  startet, selbst als root. Dadurch konnte
  - **Domains & HTTPS** die nginx-Seite nicht schreiben (`n8x-certs.sh: line 100/121: /etc/nginx/sites-available/…: Read-only file system`)
    und **„Benötigte Pakete installieren“** nichts nach `/usr` installieren,
  - **Berechtigungen prüfen & korrigieren** die systemd-Units in `/etc/systemd/system` nicht korrigieren (`chown: … Read-only file system`) –
    und meldete trotzdem „alles in Ordnung“.
- Lösung: `n8x-certs.sh` und `install.sh --fix-perms/--check-perms/--build-vocoder` erkennen die Sandbox (`/etc` nicht beschreibbar) und starten
  sich als eigener kurzlebiger systemd-Dienst außerhalb der Sandbox neu (`systemd-run --quiet --wait --pipe --collect`). Ausgabe und
  Rückgabewert kommen wie bisher ans Webinterface. Die sudo-Freigaben bleiben unverändert eng, der Schutz des Dienstes bleibt an.
- Der Berechtigungsprüfer meldet zusätzlich, ob `systemd-run` vorhanden ist und ob die Prüfung wirklich außerhalb der Sandbox lief
  (`/etc` beschreibbar) – ein falsches „alles in Ordnung“ gibt es so nicht mehr.

### ⬆️ Aktualisieren
- Einfach **Admin → ⬆️ Updates → Jetzt aktualisieren**: Das Update läuft über `n8crosslink-update.service` (ohne Sandbox). Danach
  **🔒 Domains & HTTPS → Domain anlegen** erneut ausführen und unter **🛠️ System → 🔐 Berechtigungen & sudo** einmal **🛠️ Korrigieren**.

## [1.14.0] – 2026-11-25

**🔐 Berechtigungsprüfer mit Korrektur – und sudo wird mitgeprüft und eingerichtet.**

### 🔐 Berechtigungen & sudo prüfen und korrigieren
- Neuer Prüfer im Installer: **`install.sh --check-perms`** prüft, ohne etwas zu ändern, und meldet jede Regel einzeln (✔/⚠/✖, Rückgabe 1 bei
  Fehlern); **`install.sh --fix-perms`** prüft, korrigiert gezielt und prüft danach erneut („alle 3 Fehler korrigiert – erneut geprüft, alles in
  Ordnung“ oder was übrig bleibt). Mit `--check-perms --json` als Liste für das Webinterface.
- Geprüft werden (Details in BETRIEB.md): Dienstbenutzer (vorhanden, Gruppe `dialout`, keine Login-Shell), Programmdateien (`root:root`, nicht
  beschreibbar, Ordner 755, Skripte 755, venv, keine lesbaren Schlüsseldateien, kein `.cache`), Daten (`n8crosslink`, 750, Datenbank 640,
  `update.log` 644), systemd-Units (vorhanden, `root:root` 644, Dienst nicht als root, „Update jetzt“ aktiv), Quellordner (root), USB-Vocoder
  (Gerätegruppe), Domains & HTTPS (Prüfordner, nginx-Seiten).
- **sudo wird mitgeprüft und eingerichtet:** sudo installiert, `/etc/sudoers` bindet `/etc/sudoers.d` ein (fehlt es, wird `@includedir` ergänzt –
  vorher mit `visudo` geprüft), `/etc/sudoers.d/n8crosslink` `root:root` 440, gültig, **aktuell** (Vergleich mit den Freigaben, die der Installer
  jetzt schreiben würde) und **wirksam** (`sudo -l -U n8crosslink`), `system.json` vollständig. Bei einem Fehler werden Freigaben und
  `system.json` neu geschrieben; fehlt sudo, wird es installiert.
- Fehlende systemd-Units spielt die Korrektur aus `/opt/n8crosslink/systemd/` wieder ein (der Installer legt die Vorlagen dort jetzt ab) und
  aktiviert `n8crosslink-update.path`.
- Installer und Update prüfen am Ende automatisch noch einmal und korrigieren, was übrig ist.

### 🛠️ Webinterface: Admin → System → 🔐 Berechtigungen & sudo
- Neue Liste aller Prüfungen nach Bereichen, oben ein Abzeichen („alles in Ordnung“ / „2 Fehler“). Wird beim Öffnen geprüft;
  **🔍 Erneut prüfen** und **🛠️ Korrigieren** (zeigt die Ausgabe und das Ergebnis der zweiten Prüfung). Ersetzt den alten Knopf
  „Berechtigungen prüfen & korrigieren“.
- Ist sudo nicht eingerichtet oder verweigert, steht der Konsolenbefehl `sudo /opt/n8crosslink/install.sh --fix-perms` da.
- Neue sudo-Freigabe genau für `install.sh --check-perms --json` (andere Argumente verweigert sudo). API: `GET /api/admin/system/perms`;
  `POST /api/admin/system/fix-perms` liefert jetzt zusätzlich das Prüfergebnis. Nur Admins, Ereignisprotokoll.

### 🧰 Intern
- `setup_sudo` aufgeteilt in `sudo_rules` (Freigaben erzeugen) und `system_json`, damit Einrichten und Prüfen dieselben Regeln nutzen.
- Doku: Freigaben-Beschreibung in BETRIEB.md korrigiert (`n8x-certs.sh *` ist der einzige Platzhalter).
- Tests: `tests/test_perms.py` (API, nicht freigegeben, sudo verweigert, Freigaben decken jeden sudo-Aufruf ab, `--check-perms --json` als root).

## [1.13.0] – 2026-11-25

**🔌 Alle Ports einstellbar – an einer Stelle, wie beim DMR-Server.**

### 🔌 Neue Seite ⚙️ Admin → Ports
- Ein Bereich für alle Ports von N8 Crosslink, aufgebaut wie *HTTPS & web* bei HBlink4-FreeRadioID:
  - **🌐 Webinterface:** Web-Adresse (Bind, `0.0.0.0` / `::` / `127.0.0.1`) und Web-Port.
  - **🔒 nginx:** **HTTP-Port** und **HTTPS-Port** der Domains (Standard 80/443). Bei einem HTTPS-Port ≠ 443 leitet http:// auf
    `https://domain:Port` um.
  - **📻 FRN:** Server-, Backup- und System-Manager-Port. **📡 DMR:** Server-Port und neu der **eigene UDP-Port** der Brücke
    (`dmr.local_port`, 0 = beliebig wie bisher; fest z. B. für Firewall-Regeln oder NAT). **🎛️ Vocoder:** AMBEserver-Port.
    **💬 Zello:** Port aus der WebSocket-Adresse (Anzeige).
  - Je Zeile **⬇ eingehend / ⬆ ausgehend** und **TCP/UDP** – direkt als Liste für die Firewall.
- **💾 Ports speichern** prüft alles vorher (1–65535, Web-/HTTP-/HTTPS-Port verschieden, Web-Adresse als IP), speichert in einem Rutsch,
  schreibt vorhandene Domains sofort auf die neuen nginx-Ports um und sagt danach, ob die Brücke oder der Dienst neu starten muss
  (mit Knopf **♻️ Dienst neu starten**, solange Web-Adresse/-Port noch nicht aktiv sind). Jede Änderung im Ereignisprotokoll.
- API: `GET/POST /api/admin/ports`, `POST /api/admin/ports/apply` – nur angemeldete Admins, nicht das HobbyRadioPortal.

### 🔒 Domains & HTTPS
- Domains nutzen die eingestellten Ports; die Liste zeigt je Domain `Ports 80/443 → 127.0.0.1:8080` und warnt, wenn eine Domain noch andere
  Ports nutzt (**🔁 Ports auf alle Domains anwenden**). Link zu *🔌 Ports* direkt auf der Seite.
- Zertifikate holt certbot jetzt über eine **Prüfdatei (webroot, `/var/www/n8crosslink-acme`)** statt über das nginx-Plugin – N8 Crosslink
  schreibt die nginx-Seite selbst (HTTP-Block mit ACME-Pfad und Umleitung, HTTPS-Block mit TLS 1.2/1.3, HTTP/2, HSTS, WebSocket) und
  certbot fasst sie nicht mehr an. Dadurch funktionieren eigene Ports, und `python3-certbot-nginx` wird nicht mehr gebraucht.
- Hinweis auf der Seite: Let's Encrypt prüft immer über Port 80 – ein anderer HTTP-Port braucht eine Weiterleitung im Router.
- Belegungs- und Konflikt-Hinweise beziehen sich auf den eingestellten HTTP-/HTTPS-Port.

### 🛠️ root-Helfer `n8x-certs.sh`
- Neue Aufrufe: `status PORT HTTP HTTPS`, `add DOMAIN EMAIL PORT HTTP HTTPS [staging]`, **`ports PORT HTTP HTTPS`** (alle Domains umschreiben).
  Alle Ports werden geprüft (Zahl 1–65535, Web-, HTTP- und HTTPS-Port verschieden).
- Löschen nur noch über geprüfte Namen (`n8crosslink` bzw. `n8crosslink-<domain>`) und feste Pfade unter `/etc/nginx`.
- Die nginx-Seite des alten Installers wird beim nächsten Schreiben ins neue Format übernommen (alte Datei bleibt als `.bak`).
- Status liefert je Domain die Ports (`listen`, `ports_ok`) sowie `http_port`/`https_port`.

### 🧰 Installer
- Die HTTPS-Frage im Installer ruft den Helfer mit den Standard-Ports 80/443 auf; Berechtigungen des Helfers prüft `fix_perms` wie bisher.

### ✅ Tests
- `tests/test_domains.py`: Ports-API (Konflikte, ungültige Werte, Neustart-Hinweise, nginx-Umstellung), eigener DMR-UDP-Port, Eingabeprüfung
  des Helfers für `add`/`ports`/`status` mit Ports. Helfer zusätzlich gegen nginx/certbot-Stubs geprüft (Anlegen mit 8081/8443, Umstellen
  auf 80/443, Übernahme der alten Installer-Seite, Entfernen).

## [1.12.0] – 2026-11-25

**🔒 Domains & HTTPS mit Let's Encrypt im Adminportal – und neue LED-Farben: Rot = Senden, Magenta = Empfangen, Grün = Dienst ok.**

### 🔒 Domains & HTTPS (Let's Encrypt)
- Neuer Bereich **⚙️ Admin → 🔒 Domains & HTTPS**: eigene Domains für das Webinterface mit kostenlosem Zertifikat, ohne Konsole.
  - **📦 Benötigte Pakete installieren**: `nginx`, `certbot`, `python3-certbot-nginx`, automatische Erneuerung (certbot-Timer) an,
    nginx-Standardseite aus.
  - **Domain anlegen & Zertifikat holen**: nginx-Weiterleitung `Domain → 127.0.0.1:<Web-Port>` (mit WebSocket, `X-Forwarded-For`,
    `X-Forwarded-Proto`), dann certbot mit Umleitung http → https. Optional **Test-Zertifikat** (Let's-Encrypt-Staging).
  - Liste je Domain: wohin der DNS-Eintrag zeigt, HTTPS an/aus, Aussteller, Ablaufdatum und Resttage (rot unter 14 Tagen),
    **🔄 Erneuern**, **🔒 Zertifikat holen** (neuer Versuch), **Entfernen** (Weiterleitung und Zertifikat).
  - **🛡️ Nur noch über HTTPS**: Web-Adresse auf `127.0.0.1` – `http://IP:Port` ist dann von außen zu (Dienst startet neu).
  - Hinweise, wenn N8 Crosslink selbst auf Port 80/443 lauscht, Port 80 von einem anderen Programm belegt ist oder ein HobbyRadioPortal
    auf dem Rechner die Domains übernimmt. Die nginx-Seite des alten Installers wird erkannt.
- Neuer **root-Helfer `n8x-certs.sh`** (`status`, `deps`, `add`, `renew`, `remove`): eine sudo-Zeile, prüft Domain, E-Mail und Port selbst,
  schreibt nur `/etc/nginx/sites-available/n8crosslink-<domain>`, übernimmt nichts ohne `nginx -t` (sonst alter Stand zurück). Installer
  (Frage „HTTPS einrichten“) und Webinterface nutzen denselben Helfer; `fix_perms` setzt ihn auf root:root 755; `uninstall.sh` entfernt alle
  `n8crosslink*`-Seiten und fragt nach den Zertifikaten.
- Nur angemeldete Admins, nie das HobbyRadioPortal; jede Aktion steht im Ereignisprotokoll. API: `GET/POST /api/admin/domains`,
  `POST /api/admin/domains/deps`, `POST /api/admin/domains/{domain}/renew`, `DELETE /api/admin/domains/{domain}`, `POST /api/admin/domains/local-only`.
- E-Mail und Staging-Wahl werden gemerkt (neuer Einstellungsbereich `https`).

### 🟣 LEDs: Rot = Senden, Magenta = Empfangen, Grün = Dienst ok
- Statusleiste, RX/TX-Chips und Glühen der Netzkarten: **Empfangen jetzt Magenta** (vorher Grün – nicht von „Dienst ok“ zu unterscheiden),
  **Senden Rot**, **Grün** nur noch für „verbunden / bereit“. Auch „🟣 empfängt“ in der Netzkarte, die aktive Zeile in *Zuletzt gehört* und
  in der FRN-Raumliste. Farben zentral als `--led-tx`, `--led-rx`, `--led-ok` in `crosslink.css`.

### 📚 Doku
- [KONFIGURATION.md → Domains & HTTPS](docs/KONFIGURATION.md#-domains--https), [INSTALLATION.md](docs/INSTALLATION.md#https--domain),
  [SICHERHEIT.md](docs/SICHERHEIT.md#reverse-proxy-davor-empfohlen), [BETRIEB.md → LEDs](docs/BETRIEB.md#leds-in-statusleiste-und-netzkarten), README.
  Neue Screenshots *Domains & HTTPS* und *LEDs*.

## [1.11.0] – 2026-11-25

**🔌 HobbyRadioPortal ohne Token.** Läuft das [HobbyRadioPortal](https://github.com/dhartmann1979/HobbyRadioPortal) auf demselben
Rechner, verwaltet es die Brücke direkt – kein Token anlegen, kopieren und eintragen mehr.
Ausführlich: [docs/SICHERHEIT.md](docs/SICHERHEIT.md#hobbyradioportal-auf-diesem-rechner-ohne-token).

### Was sich ändert
- **API-Tokens sind weg:** Bereich *🔌 Portal-Zugang (API-Token)* unter Benutzer, `GET/POST /api/admin/api-tokens`,
  `DELETE /api/admin/api-tokens/{id}`, `python -m n8crosslink.cli api-token` und `N8X_PORTAL_TOKEN_FILE` im Installer; die Tabelle
  `api_tokens` wird beim Start gelöscht. Unter Benutzer steht stattdessen ein kurzer Hinweis.
- **Als Portal gilt nur ein direkter Aufruf auf diesem Rechner:** Absender und `Host` Loopback (`127.0.0.1`, `::1`, `localhost`),
  Kopfzeile `X-HobbyRadioPortal: 1`, **keine** Proxy-Kopfzeile (`X-Forwarded-For`, `X-Real-IP`, `Forwarded`, `X-Forwarded-Host/-Proto`,
  `Via`, `CF-Connecting-IP`, `True-Client-IP`, `X-Client-IP`). Auch wenn uvicorn die Adresse aus `X-Forwarded-For` übernimmt, bleibt die
  Kopfzeile da – ein vorgetäuschtes „127.0.0.1“ von außen wird so abgelehnt. Die nginx-Vorlage setzt `X-Forwarded-For`.
- **Was das Portal darf, bleibt gleich:** Einstellungen (ohne Web-Adresse/-Port und Update-Quelle), Routing, Vocoder-Klang und Probehören,
  Sprachansage, FRN-Passwort anfordern, ID-Listen & Avatare, Ereignisse, Neustart der Brücke – nie Benutzer, Backup/Neuanfang, System,
  Updates, Aussehen, Export/Import. Im Ereignisprotokoll: `api:HobbyRadioPortal (<Portal-Benutzer>)`.
- **Abschalten:** `N8X_PORTAL_LOCAL=0` in der Umgebung des Dienstes.

### Doku und Tests
- [KONFIGURATION.md](docs/KONFIGURATION.md#-im-hobbyradioportal-verwalten-ohne-token) und [SICHERHEIT.md](docs/SICHERHEIT.md) umgestellt,
  Screenshot *Benutzer* neu.
- `tests/test_portal_local.py` statt `test_api_tokens.py`: Pfade und Einstellungen über das Portal, gesperrte Pfade, Proxy-Kopfzeilen und
  öffentlicher Host abgelehnt, ohne Kennung oder von einem anderen Rechner kein Zugriff, Abschalten.

## [1.10.0] – 2026-11-25

**Installer: Neueinrichtung ohne Rückfragen mit `N8X_SETUP_FILE`.** Bisher ging „ohne Fragen“ nur als Umzug aus einem Backup.
Jetzt kann der Web-Installer des [HobbyRadioPortals](https://github.com/dhartmann1979/HobbyRadioPortal) (ab 0.11.0) N8 Crosslink auch
**frisch installieren** (*Crosslink → ✨ N8 Crosslink neu installieren*). Ausführlich: [docs/INSTALLATION.md](docs/INSTALLATION.md#ohne-rückfragen-neu-einrichten-ab-1100).

### ⌨️ `N8X_SETUP_FILE=/pfad/setup.json`
- Ersetzt die Fragen der Schritte 4–8 (Dashboard, FRN, DMR, Zello, Vocoder). Abschnitte `general`, `frn`, `dmr`, `zello`, `vocoder` mit den
  Feldnamen des Adminportals, dazu `admin_user` und `admin_password`.
- Die Werte laufen durch dieselbe Typprüfung wie im Adminportal (`_coerce`); unbekannte Abschnitte oder Felder brechen mit einer klaren
  Meldung ab, statt still ignoriert zu werden.
- Ein eigener Superadmin-Name ersetzt den Standard-Login `n8schicht/n8schicht`. Ohne Passwort bleibt der Standard-Login, und das
  Dashboard erinnert wie gewohnt ans Ändern.
- Ist der N8schicht-Vocoder gewählt, wird er gleich gebaut. Die nginx-Frage am Ende entfällt (im Portal übernimmt nginx des Portals).
- Kombinierbar mit `N8X_WEB_PORT`, `N8X_LOCAL_LINKS=1` und `N8X_PORTAL_TOKEN_FILE`.
- Die Datei wird mit Rechten 600 an den Dienstbenutzer übergeben und sofort wieder gelöscht.

### ⌨️ `python -m n8crosslink.cli apply-setup DATEI`
- Neuer CLI-Befehl, den der Installer dafür nutzt. Er gibt aus, welche Abschnitte gesetzt wurden und wer Superadmin ist.

### 🧪 Tests
- `tests/test_apply_setup.py`: Abschnitte samt Typen (Ports, IDs, Schalter), Superadmin ersetzt den Standard-Login, fehlerhafte Eingaben
  werden abgewiesen, CLI-Aufruf und `install.sh` (Zweig vorhanden, Syntax in Ordnung).

## [1.9.1] – 2026-11-25

**N8schicht-Vocoder: neue Standard-Abstimmung „N8schicht“ – die im Livebetrieb nach Gehör eingestellten Klangwerte sind jetzt der Standard.**

### 🎚️ Admin → 🎛️ Vocoder → Klang-Einstellungen
Die Grundabstimmung ⭐ *N8schicht* hat neue Werte (in Klammern der bisherige N8schicht-Wert):

| Regler | DroidStar | N8schicht bisher | **N8schicht neu** | Wirkung |
|---|---|---|---|---|
| Lautstärke (Ausgang) | 2,07 | 2,07 | **2,20** | etwas lauter auf FRN/Zello |
| Höhen anheben (Brillanz) | 0,50 | 0,80 | **0,90** | heller, Zischlaute deutlicher |
| Höhen ab (Anteil der Obertöne) | 0,66 | 0,66 | **0,60** | Anhebung setzt etwas früher ein |
| Klarheit (Formantverstärkung) | 0,61 | 0,61 | **0,65** | Vokale klarer, weniger verwaschen |
| Fehlerrahmen überbrücken | 3 | 3 | **4** | ein kaputter Rahmen mehr wird überbrückt, bevor stummgeschaltet wird – ruhiger bei schwachem Signal |
| Tiefen-Filter vor dem Kodieren | 135 Hz | 135 Hz | **150 Hz** | weniger Brummen/Rumpeln von FRN/Zello ins DMR |

Unverändert bleiben: Kompressor aus, Tonhöhen-Übergang 120, Lautstärke-Übergang 160, stimmhaft → stimmlos 80, stimmlos → stimmhaft 90,
Phasenstreuung 0,30, Zischlaute 0,85, Komfortrauschen 1,0, Höhen-Ergänzung 0 dB, Rauschsperre −70 dBFS, Glättung 0,05.

- Wer bisher eigene Werte gesetzt hatte, behält sie. Mit **↺ Eigene Werte löschen** gilt die neue Standard-Abstimmung.
- Die Abstimmung *DroidStar-Original* ist unverändert.
- `docs/VOCODER.md`: Reglertabelle mit den neuen N8schicht-Werten, Hinweis zur Nachschärfung.

## [1.9.0] – 2026-11-24

**Umzug ins HobbyRadioPortal: das verschlüsselte Backup ist das Umzugspaket – der Web-Installer des Portals richtet N8 Crosslink damit
auf seinem Server ein, ohne eine einzige Rückfrage.** Ausführlich: [docs/BACKUP.md](docs/BACKUP.md#umzug-ins-hobbyradioportal) und
die [Umzugsanleitung des Portals](https://github.com/dhartmann1979/HobbyRadioPortal/blob/main/docs/UMZUG.md).

### 📦 Admin → 💾 Backup & Neuanfang → Umzug ins HobbyRadioPortal
- Neuer Abschnitt: Crosslink läuft meist nur im LAN, das Portal kann ihn von seinem Server aus nicht erreichen – deshalb geht der Umzug
  per Datei: **Verschlüsseltes Backup erstellen**, im Web-Installer des Portals im Schritt **🔀 Crosslink** hochladen und dasselbe
  Superadmin-Passwort eingeben. **Hier bleibt alles, wie es ist**, bis du den alten Crosslink abschaltest.

### 🛠️ Installer ohne Rückfragen (für den Umzug)
- `install.sh` liest auf Wunsch alles aus der Umgebung und fragt nichts:
  - `N8X_RESTORE=/pfad/backup.n8xbak` – Backup einspielen (wie „Backup einspielen“ im Installer)
  - `N8X_RESTORE_PASSWORD_FILE=/pfad/datei` – Superadmin-Passwort des Backups (erste Zeile; nie über die Kommandozeile)
  - `N8X_WEB_PORT=8070` – Web-Port auf dem neuen Server (dort belegt das HBlink4-Dashboard meist 8080)
  - `N8X_LOCAL_LINKS=1` – FRN- und DMR-Server auf `127.0.0.1` umstellen (laufen jetzt auf demselben Rechner)
  - `N8X_PORTAL_TOKEN_FILE=/pfad/datei` – API-Token „HobbyRadioPortal“ anlegen und dorthin schreiben (600)
- Falsches Passwort oder kaputte Datei: der Installer bricht mit klarer Meldung ab, statt neu einzurichten.
- Der Rest bleibt wie beim normalen Installieren: Pakete, Dienstbenutzer, venv, Vocoder bauen, Dienste, **Rechte prüfen und korrigieren**.

### ⌨️ Kommandozeile
- `python -m n8crosslink.cli api-token NAME` – legt einen Portal-Token an und gibt ihn einmal aus (nutzt der Installer).

### 🧪 Tests
- `tests/test_api_tokens.py`: Token über die Kommandozeile, ungültiger Name.
- Mit dem Portal geprüft: ein echtes Backup dieser Version wird dort entschlüsselt und gelesen (Manifest, Zahlen); falsches Passwort wird erkannt.

## [1.8.0] – 2026-11-24

**Portal-Zugang: N8 Crosslink lässt sich komplett im HobbyRadioPortal einstellen – und der Titel nennt nur noch die eingeschalteten Netze.**

### 🔌 API-Token (Benutzer → Portal-Zugang)
- Token anlegen (Name), **einmal anzeigen und kopieren**, Liste mit den letzten vier Zeichen, angelegt von/wann, zuletzt benutzt,
  letzte IP, **Widerrufen**. Höchstens 20. Gespeichert nur als SHA-256 (neue Tabelle `api_tokens`, kommt mit ins Backup).
- Anmeldung per `Authorization: Bearer n8x_…` **nur** auf: Einstellungen, Bridge neu starten, Vocoder-Klang (Regler, Profil,
  Probehören), Vocoder testen, Ansage probehören, FRN-Passwort anfordern, Ereignisse, ID-Listen und Avatare aktualisieren,
  serielle Geräte. **Nie:** Benutzer, Token, Backup/Neuanfang/Wiederherstellen, System (Dienste, Server-Neustart, Rechte),
  Updates, Aussehen, Export/Import. Web-Adresse/-Port und Update-Quelle sind auch in den Einstellungen gesperrt.
- Jede Änderung im Ereignisprotokoll als `api:<Name> (<Portal-Benutzer>)`.

### 📋 Einstellungen als Beschreibung
- `GET /api/admin/settings`: alle Einstellungen in acht Bereichen (Allgemein, Sprachansage, Routing, FRN, DMR, Zello, Vocoder,
  ID-Listen & Avatare) mit Art, Grenzen, Hilfetexten, Abhängigkeiten, *Erweitert* und „Neustart nötig“ – im selben Format wie
  HBlink4-FreeRadioID. Passwörter nie im Klartext (`set` sagt, ob eins gespeichert ist).
- `PUT /api/admin/settings {"changes": {…}}`: prüft jeden Wert (Typ, Bereich, Auswahl, JSON) mit verständlicher Meldung, speichert,
  übernimmt Routing, Allgemein, Ansage und ID-Listen sofort und meldet, ob die Bridge neu starten muss.
- Neu: `n8crosslink/settings_schema.py` – ein Test stellt sicher, dass jede Einstellung aus `DEFAULTS` beschrieben ist.

### 🏷️ Titel nur mit den eingeschalteten Netzen
- Untertitel (*FRN · DMR · servername*), Fußzeile und Seitenbeschreibung nennen nur noch die Netze, die an sind – z. B. *FRN · DMR*,
  wenn Zello aus ist. `/api/info` liefert dazu `nets` und `nets_label`; die Seite aktualisiert sich nach dem Speichern.

### 🧪 Tests
- `tests/test_api_tokens.py`: Beschreibung deckt alle Einstellungen ab, Prüfung (Grenzen, Auswahl, JSON, gesperrte Felder),
  Token-Pfade erlaubt/verboten, Passwörter verdeckt, Protokolleintrag mit Portal-Benutzer, Widerrufen, Titel ohne Zello.
  `sim_e2e.py` weiter 57/57.

### 📖 Doku
- [KONFIGURATION.md → Portal-Zugang](docs/KONFIGURATION.md#-portal-zugang-api-token--im-hobbyradioportal-verwalten) mit Screenshot,
  [SICHERHEIT.md → API-Token](docs/SICHERHEIT.md#api-token-für-das-hobbyradioportal).

## [1.7.1] – 2026-11-24

### 🌐 N8 Kit 1.0.1
- Absätze, die im Quelltext über mehrere Zeilen gehen, werden beim Umschalten **DE | EN** als Ganzes übersetzt (vorher Zeile für Zeile,
  deshalb blieben längere Hilfetexte manchmal in der Originalsprache). `n8-kit.js` ist wieder in allen vier N8schicht-Projekten gleich
  (HBlink4-FreeRadioID 1.6.0, adn-frn-server, N8-HotSpot, N8 Crosslink).

## [1.7.0] – 2026-11-24

N8 Crosslink zieht auf **N8 Theme 2** und das **N8 Kit** um – dieselben Bausteine wie HBlink4-FreeRadioID, adn-frn-server und
N8-HotSpot. Wer zwischen den vier Oberflächen wechselt, findet überall dieselben Farbprofile, denselben Sprachumschalter, denselben
Update-Hinweis und dieselbe Updates-Seite – die Grundlage für ein gemeinsames Portal. Ausführlich: [docs/SICHERHEIT.md](docs/SICHERHEIT.md).

### 🎨 N8 Theme 2
- Neue Admin-Seite **🎨 Aussehen** mit dem gemeinsamen Farbeditor: sieben Profile (N8 Night, Ocean, Aurora, Ember, Violet, Graphite,
  Daylight), jede Farbe einzeln, Hintergrundleuchten, Kartenhelligkeit, Rundung, Glasunschärfe, Vorschau mit Lesbarkeits-Prüfung.
  Änderungen sind sofort auf der ganzen Seite zu sehen, **💾 Aussehen speichern** übernimmt sie.
- Das Farbschema steht in der Datenbank (`general.theme`), wird auf dem Server geprüft und schon im Seitenkopf angewendet (kein Flackern).
  Neue Routen: `GET /api/theme`, `POST /api/admin/theme`. Helles Profil *Daylight* mit `n8-light.css`.

### 🌐 Sprache DE | EN
- Umschalter **DE | EN** oben rechts neben *Links*, **Standard Deutsch**. Umschalten ohne Neuladen; die Wahl gilt per Cookie (`n8_lang`)
  für alle N8schicht-Oberflächen auf dem Server. `?lang=en` für Links.
- Englische Texte für Kopfzeile, Statusleiste, Live, Statistik, Netze und das ganze Adminportal (Allgemein mit Sprachansage, FRN, DMR,
  Zello, Routing, Vocoder, ID-Listen & Avatare, Aussehen, Updates, Backup, Benutzer, System) in `n8crosslink/web/static/i18n-crosslink.js`.
  Der gemeinsame Farbeditor bekommt umgekehrt deutsche Texte.
- Statusleiste: Kurz- und Langtext getrennt (*Live-Daten* / *Live*).

### ⬆️ Updates im N8-Kit-Stil
- **Hinweis** unter der Statusleiste: *Update verfügbar: alt → neu* mit **Was ist neu?**, **Jetzt aktualisieren**, **Details**, **Später**
  (einen Tag) – ersetzt das bisherige Banner.
- **Admin → Updates**: gleiche Kachel wie in den anderen Projekten, mit **Letztes Update** (erfolgreich/zurückgenommen) und Protokoll.
- **Fortschritt** statt `confirm()` und Toast: Fenster mit Neuerungen, dann *geladen und eingespielt → Dienst startet neu → Weboberfläche
  wird geprüft*; meldet, wenn `update.sh` die vorige Version wiederhergestellt hat.
- `update.sh` schreibt das Ergebnis jedes Updates nach `data/update.result` (gleiches Format wie der N8 update guard der anderen Projekte).

### 🔐 Sicherheit
- **`/openapi.json` war offen** (nur `/docs` und `/redoc` waren aus) – jetzt 404. Zum Entwickeln `N8_API_DOCS=1`.
- Neue Header bei jeder Antwort: `Content-Security-Policy`, `Strict-Transport-Security` über HTTPS bzw. hinter einem Proxy mit
  `X-Forwarded-Proto: https`, `Permissions-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`,
  `Cross-Origin-Opener-Policy`/`-Resource-Policy` (vorher gar keine). Kein `server: uvicorn` mehr.
- Doku mit Beispielen für **Caddy** und **nginx** als Reverse-Proxy (inklusive WebSocket für Live-Daten und Mithören).

### 🧪 Tests
- `tests/test_web_security.py`: keine API-Doku, alle Header, HSTS hinter Proxy, kein `server`-Header, Prüfung und Speichern des
  Farbschemas (nur mit Login), Kit-Dateien eingebunden. `tests/sim_e2e.py` weiter 57/57.
- `tests/screenshots.py` erzeugt zusätzlich *Aussehen* und die englische Ansicht.

## [1.6.0] – 2026-11-24

### Neu: N8schicht-Vocoder (eigener Fork, Quellen im Repository)
- Der Software-Vocoder heißt jetzt **N8schicht-Vocoder**. Er ist ein Fork des AMBE+2-Codecs aus [DroidStar](https://github.com/nostar/DroidStar) (Doug McLain), Version 1.0.0 auf Basis von DroidStar `fc8e340a61d6`.
- **Quellen liegen im Repository** unter `third_party/n8schicht-vocoder/`, mit Lizenz, Herkunft und Änderungsliste. Installer und Update bauen die Bibliothek `lib/libn8vocoder.so` mit `g++` direkt daraus; GitHub wird dafür nicht mehr gebraucht. Neu gebaut wird nur, wenn sich die Quellen ändern.
- **Läuft auf 32-Bit-ARM** (Raspberry Pi OS armhf, Tinker Board): Die 128-Bit-Multiplikation hat einen portablen Weg ohne Qt; Bitgleichheit ist geprüft. `ambe2_version()` ist ergänzt.
- **Eigener Prozess** (`n8crosslink.ambe_worker`): Stürzt der C-Code ab oder hängt er, startet nur der Vocoder-Prozess neu und die Bridge läuft weiter. Zähler „Neustarts“ und „Fehlrahmen“ (vom Decoder überbrückte Rahmen = Maß für Bitfehler auf Funk).
- **Ende des Durchgangs nicht mehr abgeschnitten:** Der Encoder arbeitet 40 ms verzögert, deshalb werden am Ende jedes Durchgangs nach DMR 2 Stille-Rahmen nachgeschoben.
- `tools/update_n8vocoder.sh` übernimmt neue DroidStar-Stände und spielt die Änderungen wieder ein.

### Neu: Klang-Abstimmung „N8schicht“ – verständlicher, weniger komprimiert, bis 4 kHz
- Gemessen mit ESTOI (Verständlichkeit) und PESQ (Qualität) an 35 deutschen Sätzen von 7 Stimmen. Übernommen wurde nur, was auf zwei getrennten Stimmgruppen besser war.
- **Kompressor (Frame-Limiter) aus:** Er war die Ursache des „komprimierten“ Klangs.
- **Natürlichere Interpolation:** schnellerer Tonhöhen-Übergang (120 statt 160 Samples) und weicherer Übergang stimmhaft → stimmlos (80 statt 50).
- **Höhenanhebung 0,8:** glatter Frequenzgang bis zur AMBE-Grenze bei ≈ 3,65 kHz.
- **Höhen-Ergänzung 3,65–4 kHz** in der Bridge: Rauschen nach der Hüllkurve des Bands 3,0–3,65 kHz. Damit ist das Band bis zur 8-kHz-Grenze von 4000 Hz gefüllt.
- Ergebnis gegenüber DroidStar-Original: ESTOI 0,777 → **0,790**, PESQ 2,78 → **2,85**, mit 2 % Bitfehlern ESTOI 0,751 → **0,768**; Frequenzgang 3,8–4 kHz −20,4 dB → **−2,4 dB**. Messverfahren und Tabelle in `docs/VOCODER.md`.

### Neu: Klang-Popup mit Reglern und Probehören
- Auf der Karte **N8schicht-Vocoder** öffnet **„🎚️ Klang-Einstellungen“** ein Popup: Grundabstimmung (N8schicht / DroidStar-Original) und 17 Regler für Decoder, Nachbearbeitung und Encoder, jeweils mit Erklärung und den Werten beider Abstimmungen. Die Regler **wirken sofort** im laufenden Betrieb.
- **Probehören:** Standardsatz, eigener Text oder **eigene WAV-Datei** durch Encoder → Decoder schicken. Eingang und Ausgang werden nebeneinander abgespielt, dazu Bandbreite, Abweichung je Frequenzband, Pegel, Laufzeit sowie ESTOI/PESQ, falls installiert.
- `tools/vocoder_test.py`: Eingang gegen Ausgang auf der Kommandozeile (WAV in jedem Format, `--compare`, `--set`, Ergebnis-WAVs). Testsätze in `tests/audio/`.

### Geändert
- **Lizenz jetzt GPL-3.0-or-later** (bisher GPL-2.0), damit der GPL-3-Vocoder im Repository liegen darf.
- **Operator-Wechsel per Neuanmeldung entfernt** (aus 1.5.0, hat in der Praxis nicht funktioniert).
- **FRN-Textnachricht privat:** Neues Feld *Textnachricht nur an diese Stationen*. Die Nachricht geht dann nur an diese Rufzeichen (`TM:` mit deren Client-ID), bei den anderen ploppt nichts auf. Leer = öffentlich an alle wie bisher.
- Einstellungen unter *Allgemein* (auch Sprachansage) wirken jetzt **sofort** nach dem Speichern; nur Web-Adresse und -Port brauchen einen Dienst-Neustart.
- Alte Vocoder-Einstellungen (md380-emu, „DroidStar“) werden automatisch auf den N8schicht-Vocoder umgestellt.

### Dashboard
- **Mithören im Kopfmenü:** Der Knopf sitzt jetzt oben neben *Links*. Der kleine Pfeil ▾ rechts daran öffnet die Lautstärke als Dropdown (0–200 %, im Browser gemerkt).
- **Segmentierte Pegelanzeige in der Statusleiste:** Hinter dem Namen der sprechenden Station stehen 20 Segmente à 3 dB (−60 … 0 dBFS, grün/gelb/rot), dazu Spitzenwert und dB-Zahl. Sie ersetzt den Balken in der On-Air-Karte.

### Doku
- `docs/VOCODER.md` neu: jeder Regler erklärt, Messverfahren, Ergebnisse, Test mit WAV-Dateien, Fork-Pflege.
- **Neu `docs/ZELLO.md`:** Zello Schritt für Schritt verbinden (Bridge-Konto, Kanal, Entwickler-Token oder Issuer + Private Key, Zello Work, Felder, Test, Fehlersuche).
- Konfiguration, Installation, Fehlersuche, Technik, Deinstallation und README angepasst; neue Screenshots (Klang-Popup, Probehören, Mithören-Menü, Pegelanzeige).

### Tests
- `tests/test_vocoder.py`: 1-kHz-Ton → 997 Hz, Stille-Rahmen, 300 Zufallsrahmen ohne Übersteuerung, Regler live, Absturz und Neustart des Vocoder-Prozesses.
- Simulation **57/57**, auch mit echtem N8schicht-Vocoder (`N8X_SIM_VOCODER=n8vocoder`), dazu private und öffentliche FRN-Textnachricht.
- Update von 1.5 (DroidStar-Einstellung) auf 1.6 im Installer durchgespielt: umgestellt, gebaut, getestet, Weboberfläche antwortet.

## [1.5.1] – 2026-11-24

### Behoben
- **DMR-ID-Liste wurde nicht geladen:** FreeRadioID liefert `subscriber_ids.csv` inzwischen mit `\n\r` als Zeilenende. Der CSV-Parser brach deshalb ab („new-line character seen in unquoted field“), und Rufzeichen und Namen zu DMR-IDs fehlten. Alle Zeilenende-Varianten werden jetzt vereinheitlicht; geprüft mit der echten Liste (339 677 IDs).

### Update sicherer
- Der Installer prüft am Ende, ob die Weboberfläche **wirklich antwortet** (HTTP auf `/api/info`, bis 45 s), nicht nur, ob der Port offen ist. Wenn nicht, zeigt er `systemctl status` und die letzten 40 Logzeilen.
- **Automatisches Zurücksetzen:** Startet die neue Version beim Update nicht, stellt `update.sh` die vorige Version wieder her und installiert sie erneut, damit das Dashboard erreichbar bleibt. Im Update-Log steht dann „Update auf X fehlgeschlagen – Y wiederhergestellt“; zusätzlich wird `data/update.rollback` geschrieben.
- `install.sh --diagnose` zeigt zusätzlich, ob die Weboberfläche antwortet, und `systemctl status n8crosslink`.

### DMR-Senden geprüft
- Neuer Integrationstest `tests/integration_hblink4.py` gegen ein **echtes HBlink4-FreeRadioID**: FRN → N8 Crosslink → HBlink4 → zweiter Peer. Ohne FreeRadioID-Login kommen alle 48 Pakete an. Mit Secure Login und der Server-Passphrase wird die Bridge Gast und HBlink4 verwirft alles. Im Server-Log steht dann irreführend „Inbound routing denied … not in allowed list [262, …]“, obwohl 262 in der Liste steht.
- Hinweis direkt am DMR-Passwortfeld im Adminportal.

## [Doku] – 2026-11-24
- Fehlersuche und Konfiguration: „Von DMR kommt alles an, nach DMR geht nichts“. Bei HBlink4-FreeRadioID mit Secure Login wird die Bridge mit der lokalen Passphrase zum FreeRadioID-Gast und darf nur in die Gast-Talkgroups senden. Mit Log-Befehl und drei Lösungen.

## [1.5.0] – 2026-11-24

### Neu: FRN-Operator-Wechsel (Standard aus)
- FRN überträgt Operator (`<ON>`) und Beschreibung (`<DS>`) nur bei der Anmeldung. Mit der neuen Option **„Operator-Wechsel“** meldet sich die Bridge bei jedem Durchgang aus DMR/Zello mit **Rufzeichen und Name der sprechenden Station** neu an, z. B. `DO1TEST, Tobias`. Die Beschreibung wird aus einer Vorlage gesetzt (Standard `via {quelle} {detail}` → `via DMR TG 262 Deutschland · TS2`).
- Der Ton wird während der Neuanmeldung gepuffert (bis 10 s) und danach vollständig gesendet. Nach einer einstellbaren Ruhezeit (Standard 10 s) geht es zurück zum eigenen Operator. Spricht dieselbe Station vorher erneut, bleibt die Anmeldung bestehen. Spricht gerade jemand auf FRN, wird der Rückwechsel verschoben.
- **Automatischer Rückfall:** Lehnt der Server den fremden Operator ab, meldet sich die Bridge sofort wieder normal an, sendet den gepufferten Ton und schaltet die Option bis zum nächsten Neustart ab.
- **„🧪 Operator-Wechsel testen“** im FRN-Adminbereich: meldet einmal als `DL0TEST, N8 Crosslink Test` an und wieder zurück. Ein Status-Popup zeigt, ob der Server das mit dem Konto annimmt.
- Ein gewollter Wechsel erzeugt weder „Verbindung verloren“ noch Watchdog-Aktionen; im Status steht „als DO1TEST, Tobias“.

### Neu: Sprachansage des Rufzeichens (Standard aus)
- Am Anfang eines Durchgangs sagt eine Computerstimme (espeak-ng, offline) das Rufzeichen an, danach folgt der Ton. Wählbar je Zielnetz (FRN/DMR/Zello): Buchstaben oder NATO-Alphabet, eigener Text (`{call}`, `{name}`), höchstens alle X Minuten je Station, Tempo, Lautstärke, Pause.
- Die Ansage wird im gleichmäßigen 20-ms-Takt vor den Live-Ton gesetzt (kein Paket-Burst ins Zielnetz). Ansagen werden zwischengespeichert. Folgt direkt der nächste Durchgang, wird der Rest sofort ausgegeben.
- **„▶ Ansage anhören“** unter *Allgemein* spielt die Ansage mit den Formularwerten im Browser ab.
- Der Installer installiert `espeak-ng` mit (auch beim Update).

### Tests & Doku
- Simulation um 11 Prüfungen erweitert (jetzt **64/64**; ab 1.6.0 ohne Operator-Wechsel **57/57**): Neuanmeldung mit Stations-Operator und Beschreibung, Ton unter fremdem Operator, Rückwechsel, kein Verbindungsverlust-Ereignis, Ablehnung → Rückfall mit Ton, Testknopf (Annahme/Ablehnung), Ansage vor dem Ton, NATO-Text.
- Doku: Konfiguration (Abschnitte Operator-Wechsel und Sprachansage), README, Screenshots.

## [1.4.0] – 2026-11-24

### Neu: DroidStar-Vocoder statt md380-emu
- **Software-Vocoder aus [DroidStar](https://github.com/nostar/DroidStar)** (Doug McLain): AMBE+2 half-rate für DMR, Encoder und Decoder über die C-Schnittstelle `ambe2.h`. Er läuft **nativ auf x86 und ARM direkt in der Bridge** (ctypes, eigener Arbeitsthread). Es gibt kein qemu, keinen Zusatzdienst und kein UDP mehr, also auch keine verlorenen oder verschobenen Rahmen.
- Unter 1 ms je 20-ms-Rahmen (Encode + Decode) auf x86. Encoder und Decoder werden bei jeder neuen Übertragung zurückgesetzt; der Decoder überbrückt kaputte Rahmen.
- **Nicht im Repository enthalten:** Installer und Update laden einen festen, geprüften Stand der DroidStar-Quellen (`fc8e340a61d6`). Daraus bauen sie nur den Codec, ohne Qt: `/opt/n8crosslink/lib/libambe2.so`, root, 644. Neu gebaut wird nur, wenn sich der Stand ändert oder der Test fehlschlägt.
- Bauen im Webinterface: **Admin → 🎛️ Vocoder → „🔨 DroidStar-Vocoder bauen / aktualisieren“**; von Hand mit `sudo /opt/n8crosslink/install.sh --build-vocoder`. Neue sudo-Freigabe statt `--install-md380`.
- **Vocoder-Test verbessert:** 1-kHz-Ton über 25 Rahmen. Angezeigt werden Laufzeit je Rahmen und die zurückgelieferte Frequenz; beim DroidStar-Vocoder muss sie bei 1 kHz liegen.
- `install.sh --diagnose` zeigt den Stand des DroidStar-Vocoders und ob md380-emu noch vorhanden ist.

### Entfernt: md380-emu
- Die Betriebsart md380-emu entfällt. Eine bestehende md380-Einstellung wird beim Update **automatisch auf DroidStar umgestellt**; alte `md380_*`-Einstellungen werden aus der Datenbank gelöscht.
- **md380-emu wird deinstalliert:** Dienst stoppen und deaktivieren, Unit-Datei löschen, Paket entfernen (`apt purge md380-emu`), `/opt/md380-emu` löschen, sudo-Freigaben entfernen. Die DVSwitch-Paketquelle wird nur entfernt, wenn keine anderen DVSwitch-Pakete mehr installiert sind. `qemu-user-static` bleibt; der Installer nennt den Befehl zum Entfernen.
- `systemd/md380-emu.service` und der md380-Watchdog-Neustart aus 1.3.1 sind entfallen. Der Watchdog öffnet jetzt jeden Vocoder bei Ausfall neu.
- Deinstallation: entfernt auch die DroidStar-Quellen in `/usr/local/src/n8crosslink-droidstar`.

### Sonstiges
- Update-Dienst darf bis zu 30 Minuten laufen (Bauen auf langsamen Raspberry Pis).
- Tests: `tests/test_vocoder.py` prüft den DroidStar-Vocoder (1-kHz-Ton → 997 Hz, Stille-Rahmen aus dem DMR-Burst → Stille, 30 parallele Aufrufe in Reihenfolge). Die Simulation läuft mit `N8X_SIM_VOCODER=droidstar` komplett mit dem echten Vocoder (DMR→FRN mit echtem AMBE-Ton) – 53/53.
- Doku: `docs/VOCODER.md` neu geschrieben; Installation, Betrieb, Fehlersuche, Deinstallation, Migration, README und Vocoder-Screenshot angepasst.

## [1.3.1] – 2026-11-24

### Behoben: Vocoder instabil (md380-emu)
- **Ursache:** Das AMBE3000-Paketformat hat keine Sequenznummer. Antworten wurden der ältesten offenen Anfrage zugeordnet. Ein verlorenes oder verspätetes UDP-Paket von md380-emu verschob die Zuordnung dauerhaft um einen Rahmen → Roboterstimme, Knacken, Aussetzer bis zum Neustart. Im Test mit Paketverlust waren 97 von 120 Rahmen falsch zugeordnet.
- **Lockstep** bei md380-emu und AMBEserver: immer nur eine Anfrage unterwegs.
- **Neuer UDP-Socket nach jedem Timeout**: verspätete Antworten landen am alten Socket und werden verworfen. Im selben Test jetzt **0 falsch zugeordnete Rahmen**.
- **Ein Wiederholungsversuch** bei verlorenem Paket.
- USB-Stick: nach einem Timeout werden offene Anfragen verworfen und neu synchronisiert.

### Neu
- **Watchdog startet md380-emu neu**: Antwortet der lokale md380-emu länger als 20 s nicht, startet die Bridge den Dienst über die sudo-Freigabe neu und verbindet sich neu (Ereignis im Log, Zähler „Neustarts“).
- Neue Einstellungen unter *Vocoder*: *Antwortzeit je Rahmen (ms)*, *Watchdog: neu starten nach (s)*, *Hängenden md380-emu-Dienst automatisch neu starten*.
- Vocoder-Status zeigt zusätzlich Wiederholungen, verspätete Antworten und Dienst-Neustarts.

### Doku & Tests
- `docs/VOCODER.md`: Abschnitte „Stabilität“ und „Alternativen zu md380-emu“ (USB-Stick, md380-emu nativ auf einem Raspberry Pi über das Netz, AMBEserver).
- Neuer Test `tests/test_vocoder.py` mit absichtlich verlorenen und verspäteten Antworten; Simulation weiter 53/53.

## [1.3.0] – 2026-11-24

### Neu: FRN-Passwort anfordern
- Knopf **„📧 Passwort anfordern“** im FRN-Adminbereich. Registriert die Station beim FRN-System-Manager (`IG:`-Befehl, gleiches Format wie das SvxLink-Skript `frn-register`); das Passwort kommt per E-Mail.
- Nimmt die Werte direkt aus dem Formular (auch ungespeichert) und prüft sie vor dem Senden: Rufzeichen + Name, E-Mail, Band/Kanal („PC Only“, „Crosslink“ oder Frequenzformat), Land, Ort („Ort - Ortsteil“), keine spitzen Klammern.
- **Status-Popup** mit Fortschritt (Spinner) und Ergebnis: angenommen (`OK`), bereits registriert (`NU`), Eingaben prüfen, keine Verbindung/Antwort, abgelehnt (mit Antwortcode). Jede Anforderung erscheint in den Ereignissen.
- System Manager einstellbar (Standard `sysman.freeradionetwork.eu:10025`) für eigene FRN-Netze; Schutz gegen Mehrfachklicks (1 Anforderung pro Minute).
- Wiederverwendbares Status-Popup für weitere Admin-Aktionen.

### Tests & Doku
- Simulation mit Fake-System-Manager: OK, NU, ungültige Eingaben (nichts gesendet), Server nicht erreichbar – jetzt **53/53 Prüfungen**.
- Doku (Konfiguration → FRN-Passwort anfordern), README und neuer Screenshot.

## [1.2.2] – 2026-11-24

### Behoben
- **md380-emu startete nicht (Debian 13):** md380-emu wird jetzt so gestartet wie bei DVSwitch – über `qemu-arm-static` mit `-S 2470`. Bevorzugt wird das `qemu-arm-static`, das neuere DVSwitch-Pakete in `/opt/md380-emu/` mitbringen, weil das System-qemu 10 unter Debian 13 md380-emu abstürzen lässt. Danach System-qemu, zuletzt direkt (ARM). Ungültige Startvarianten (`2470`, `-p 2470`) entfernt; jede Variante wird mit einem echten Encode/Decode-Test geprüft, Fehlversuche zeigen die Logzeile.
- **Sicherheit md380-emu:** Der Dienst läuft jetzt als Benutzer `n8crosslink` statt als root (mit `NoNewPrivileges`, `ProtectSystem=strict`). `/opt/md380-emu` wird auf root gesetzt – dort lag ein `qemu-arm-static`, das einem normalen Benutzer gehörte und vom root-Dienst ausgeführt wurde.

### Neu
- **Zello-Schlüssel nur noch in der Datenbank:** `zello*.key`/`zello*.pem` im Programm-, Daten- oder Quellordner werden bei Installation, Update und Berechtigungsprüfung automatisch erkannt → an einen sicheren Ort verschoben (nur root) → in SQLite übernommen → per Fingerabdruck gegengeprüft → mit `shred` gelöscht. Neue CLI-Befehle `import-zello-key` (prüft, ob es ein gültiger PEM-Private-Key ist) und `zello-key-info` (zeigt nur den Fingerabdruck).
- **Diagnose:** `sudo /opt/n8crosslink/install.sh --diagnose` – System, Version, Dienste, Web-Port mit Bind-Test unter den echten Dienst-Rechten, md380-emu-Startzeile, Vocoder-Test, Zello-Schlüssel-Fingerabdruck, sudo-Freigaben, letzte Logzeilen; ohne Passwörter.
- Nach jeder Installation/jedem Update prüft der Installer, ob die Weboberfläche wirklich auf ihrem Port lauscht, und zeigt sonst das Log.

## [1.2.1] – 2026-11-24

Fehlerbehebung: Dienst startete mit Web-Port 80 nicht.

### Behoben
- **Start mit Port unter 1024:** Die Bridge läuft ohne root-Rechte und durfte deshalb Port 80 nicht öffnen (`[Errno 13] … permission denied`). Der Dienst erhält jetzt ausschließlich das Recht `CAP_NET_BIND_SERVICE` (`AmbientCapabilities`), damit funktionieren auch Ports wie 80. Der Installer erklärt das bei der Port-Abfrage und weicht auf einen freien Port aus, wenn 80 schon belegt ist (z. B. durch nginx/Apache).
- **Schlüsseldateien nicht mehr weltlesbar:** Die Berechtigungsprüfung hat alle Dateien in `/opt/n8crosslink` auf 644 gesetzt – dadurch wurde z. B. eine dort abgelegte `zello.key` für alle Benutzer lesbar. Private Schlüssel (`*.key`, `*.pem`, `*.p12`) werden jetzt erkannt, auf 600 gesetzt und gemeldet. Der Installer bietet nach dem Import des Zello-Schlüssels an, die Datei zu löschen (der Schlüssel liegt in der Datenbank und im verschlüsselten Backup).

### Doku
- Fehlersuche: Eintrag zu `Errno 13` und Anleitung zum Start von Hand, damit die eigentliche Fehlermeldung sichtbar wird.

## [1.2.0] – 2026-11-24

Mithören, verschlüsseltes Backup, geplante Deinstallation, vollständige Software-Vocoder-Installation und komplettes Site-Icon-Set.

### 🎧 Mithören (nur angemeldete Admins)
- Knopf „Mithören“ mit Lautstärkeregler in der On-Air-Karte; der Ton der aktiven Durchsage kommt aus jedem Netz (FRN, DMR, Zello).
- Eigener WebSocket `/ws/audio`, geschützt per Login-Cookie: Ohne Anmeldung wird die Verbindung abgelehnt, beim Abmelden endet sie. 8 kHz / 16 Bit, im Browser mit 250-ms-Jitterpuffer über Web Audio abgespielt.
- Statusleiste zeigt „🎧 Mithören“, solange aktiv.

### 💾 Verschlüsseltes Backup & Wiederherstellung
- **Alles in einer Datei** (`.n8xbak`): Einstellungen inkl. Zugangsdaten, Benutzer, Last Heard, Statistik, Ereignisse, ID-Listen, Talkgroups, Avatare.
- **Kein Klartext:** Die gesamte Datei inkl. Manifest ist mit AES-256-GCM verschlüsselt. Der Schlüssel wird per scrypt aus dem **Superadmin-Passwort** abgeleitet. Deutliche Hinweise im Webinterface, im Installer, in `uninstall.sh` und in der Doku: Passwort im Passwortsafe aufbewahren.
- Webinterface (Admin → 💾 Backup & Neuanfang, nur Superadmin, Passwort erneut): Backup herunterladen, Backup prüfen (Datum, Version, Umfang), wiederherstellen.
- CLI `cli backup` / `cli restore`; der Installer bietet bei Neuinstallation das Einspielen eines Backups an.

### ♻️ Deinstallation & Neuanfang
- Zurücksetzen im Webinterface in drei Stufen: Verlauf, Einstellungen, alles (danach Standard-Login).
- Neues `uninstall.sh`:
  - „Daten behalten“ oder „komplett entfernen“, Backup vorher anbieten
  - entfernt Dienste, Update-Auslöser, sudo-Freigaben und nginx-Konfiguration, optional auch Zertifikat, Dienstbenutzer und Quellcode
  - md380-emu und DVSwitch-Paketquelle nur auf Nachfrage
  - **schaltet die vom Installer abgeschalteten alten Dienste (SvxLink, Bridges) wieder ein**
  - Optionen `--keep-data`, `--purge`, `--yes`, `--no-backup`
- Neue Doku `docs/DEINSTALLATION.md`.

### 🧠 Software-Vocoder md380-emu – vollständige Installation
- DVSwitch-Paketquelle über `dvswitch.org/bookworm` für Debian 12/13, Raspberry Pi OS und Ubuntu 22.04/24.04 (bisher wurde der jeweilige Codename aufgerufen und lief bei Trixie/Noble ins Leere). Debian 11 nutzt `bullseye`.
- Auf x86 automatisch `qemu-user-static` + `binfmt-support`; Ausführrechte werden gesetzt.
- Der Paket-Dienst wird bevorzugt, sonst eigener Dienst mit automatischem Durchprobieren der Startvarianten.
- **Echter Funktionstest** (Encode/Decode über UDP 2470) statt Annahme; neue CLI `cli vocoder-test`.
- Im Webinterface: **„md380-emu installieren / reparieren“** (über sudo, `install.sh --install-md380`); bei Update und Wiederherstellung wird md380-emu nachinstalliert, wenn er eingestellt, aber nicht vorhanden ist.

### 🖼️ Site-Icons (für alle N8schicht-Repos)
- Komplettes Set: `favicon.ico` (16/32/48), PNG-Favicons, vereinfachtes Favicon-SVG für kleine Größen, `apple-touch-icon` (180 px, randlos), PWA-Icons 192/512, maskable 512, Open-Graph-Vorschau 1200×630, `site.webmanifest`, Theme-/Tile-Farben.
- Ausgeliefert auch unter den Standardpfaden `/favicon.ico`, `/apple-touch-icon.png`, `/site.webmanifest`.
- Wiederverwendbares Skript `tools/make_icons.py` und Doku `docs/BRANDING.md` für die anderen N8schicht-Repositories.

### Tests & Doku
- Simulation auf **49 Prüfungen** erweitert: Mithören-Audio, Backup ohne Klartext, falsches Passwort, Zurücksetzen, Wiederherstellen.
- Live geprüft: Ohne Login wird Mithören abgelehnt, mit Login kommt Audio an; Backup-Download und -Prüfung funktionieren über die Web-API; alle Icon-Pfade antworten.
- Neue Doku `BACKUP.md`, `DEINSTALLATION.md`, `BRANDING.md`; `VOCODER.md`, `INSTALLATION.md`, `KONFIGURATION.md` und README aktualisiert, neue Screenshots.

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
