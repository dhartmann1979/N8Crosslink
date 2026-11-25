# Installation & Update

## Voraussetzungen

| | |
|---|---|
| Betriebssystem | Debian 12/13, Ubuntu 22.04/24.04, Raspberry Pi OS, DietPi |
| Architektur | amd64, arm64, armhf |
| Hardware | ab Raspberry Pi 3 oder jeder x86-Server; der N8schicht-Vocoder läuft auf beiden nativ (auch 32-Bit-ARM) |
| Netz | ausgehend: FRN-Server (TCP 10024), DMR-Server (UDP 62031), Zello (wss/443) |
| Zugangsdaten | FRN-Konto (E-Mail + Passwort), Peer-ID + Passwort am HBlink4/FreeDMR, Zello-Konto (+ Token) |

## Installation

```bash
git clone https://github.com/dhartmann1979/N8Crosslink.git
cd N8Crosslink
sudo ./install.sh
```

Der Installer fragt Schritt für Schritt:

| Schritt | Inhalt |
|---|---|
| 1 | Systempakete: python3, venv, libgsm (FRN), libopus (Zello), sqlite3, git |
| 2 | Dienstbenutzer `n8crosslink` (Gruppe `dialout` für den USB-Stick), Dateien nach `/opt/n8crosslink` |
| 3 | Python-venv, Abhängigkeiten, Selbsttest von GSM- und Opus-Codec |
| 3a | **Backup einspielen?** – bei Neuinstallation optional eine `.n8xbak`-Datei + Superadmin-Passwort; dann werden die Schritte 4–8 übersprungen |
| 4 | Web-Port (freier Port wird vorgeschlagen; Ports unter 1024 wie 80 sind möglich – der Dienst bekommt dafür nur `CAP_NET_BIND_SERVICE`, kein root), Titel, Domain; Standard-Login **n8schicht / n8schicht** (optional gleich eigenes Passwort) |
| 5 | **FRN**: Server, Port, Backup, E-Mail, Passwort, Rufzeichen, Name, Raum, Ort, Land |
| 6 | **DMR**: Server, Port, Passphrase, Peer-ID, Rufzeichen, Quell-ID, Zeitschlitz, RX-/TX-TG, Color Code, RPTO |
| 7 | **Zello**: Variante (Token / Issuer+Key / Zello Work), Kanal, Benutzer, Passwort |
| 8 | **Vocoder**: N8schicht-Vocoder (Software – wird aus den mitgelieferten Quellen gebaut und getestet, siehe [VOCODER.md](VOCODER.md)), USB-Stick, AMBEserver oder später |
| 9 | Erkennung alter Dienste (`svxlink`, `mmdvm_bridge`, `analog_bridge`, `*zello*`) mit Rückfrage zum Abschalten, **sudo fürs Webinterface**, **Berechtigungen prüfen & korrigieren**, systemd-Dienst mit Watchdog, Update-Auslöser, optional nginx + Let's Encrypt |

Alle Einstellungen liegen danach in `/opt/n8crosslink/data/crosslink.db` und sind im Adminportal änderbar.

### Ohne Rückfragen aus einem Backup (Umzug)

Für Skripte und den Web-Installer des HobbyRadioPortals: `N8X_RESTORE` (Backupdatei), `N8X_RESTORE_PASSWORD_FILE` (Passwort in der
ersten Zeile), optional `N8X_WEB_PORT`, `N8X_LOCAL_LINKS=1` und `N8X_PORTAL_TOKEN_FILE` – siehe [Backup → Umzug](BACKUP.md#umzug-ins-hobbyradioportal).

### Ohne Rückfragen neu einrichten (ab 1.10.0)

`N8X_SETUP_FILE=/pfad/setup.json` ersetzt die Fragen der Schritte 4–8. Die Felder heißen wie im Adminportal; unbekannte werden
abgewiesen. So installiert der Web-Installer des HobbyRadioPortals (ab 0.11.0, *Crosslink → ✨ N8 Crosslink neu installieren*):

```bash
cat > /root/xl.json <<'JSON'
{"general": {"title": "N8 Crosslink"},
 "frn": {"enabled": true, "server": "127.0.0.1", "port": 10024, "email": "bridge@example.org", "password": "…",
         "callsign": "N8XLINK", "op_name": "Crosslink", "net": "Nachtschicht", "city": "Minden - JO42", "country": "Germany"},
 "dmr": {"enabled": true, "host": "127.0.0.1", "port": 62031, "password": "…", "peer_id": 262000101, "callsign": "N8XLINK",
         "src_id": 2620001, "slot": 2, "tg_rx": 262, "tg_tx": 262},
 "zello": {"enabled": false}, "vocoder": {"vocoder_mode": "n8vocoder"},
 "admin_user": "sysop", "admin_password": "mindestens-8-Zeichen"}
JSON
chmod 600 /root/xl.json
sudo N8X_SETUP_FILE=/root/xl.json N8X_WEB_PORT=8070 N8X_PORTAL_TOKEN_FILE=/root/xl.token ./install.sh
rm /root/xl.json
```

Mit `admin_user` ≠ `n8schicht` ersetzt der neue Superadmin den Standard-Login `n8schicht/n8schicht`. Der N8schicht-Vocoder wird
gebaut, wenn er gewählt ist. Prüfen geht auch ohne Installer: `python -m n8crosslink.cli --db … apply-setup setup.json`.

## Standard-Login

Beim ersten Start gibt es den Superadmin **`n8schicht`** mit Passwort **`n8schicht`**. Solange dieses Passwort aktiv ist, zeigt das Dashboard nach dem Login einen Hinweis mit Knopf „Passwort ändern“ (Admin → 👥 Benutzer).

## Berechtigungen

Bei jeder Installation und jedem Update (auch „Update jetzt“ aus dem Webinterface) werden die Rechte geprüft und korrigiert:

| Pfad | Besitzer | Rechte |
|---|---|---|
| `/opt/n8crosslink` (Programm, venv) | root | nur lesbar für den Dienst |
| `install.sh`, `update.sh`, `uninstall.sh` | root | 755 – **nicht** vom Dienst änderbar (sie laufen als root) |
| `/opt/n8crosslink/data` | n8crosslink | 750, Datenbank 640 |
| `/etc/systemd/system/n8crosslink*` | root | 644 |
| `/etc/sudoers.d/n8crosslink` | root | 440, mit `visudo` geprüft |
| USB-Stick | Gruppe `dialout` (bzw. Gerätegruppe) | Dienstbenutzer wird ergänzt |

Von Hand: `sudo /opt/n8crosslink/install.sh --fix-perms` oder Admin → 🛠️ System → „Berechtigungen prüfen & korrigieren“.

## Wichtige Befehle

```bash
systemctl status n8crosslink         # Status
journalctl -u n8crosslink -f         # Log live
sudo systemctl restart n8crosslink   # Neustart
sudo /opt/n8crosslink/update.sh      # Update (behält alle Einstellungen)
sudo /opt/n8crosslink/uninstall.sh   # Entfernen / von vorn beginnen – siehe DEINSTALLATION.md
```

Kommandozeile für Einstellungen (z. B. per SSH):

```bash
cd /opt/n8crosslink
sudo -u n8crosslink venv/bin/python -m n8crosslink.cli show dmr
sudo -u n8crosslink venv/bin/python -m n8crosslink.cli set dmr tg_tx 26299
echo 'NeuesPasswort' | sudo -u n8crosslink venv/bin/python -m n8crosslink.cli admin n8schicht
```

## Update

Am einfachsten im Webinterface: Die Bridge prüft **stündlich zur vollen Stunde**, ob auf GitHub eine neue Version liegt, zeigt dann ein Banner mit den Änderungen und installiert sie per **„Jetzt aktualisieren“** (Admin → ⬆️ Updates). Von Hand geht es mit `sudo /opt/n8crosslink/update.sh`.

`update.sh` holt die neueste Version aus GitHub und startet den Installer im Update-Modus: Dateien und Abhängigkeiten werden erneuert, Berechtigungen und sudo-Freigaben neu geprüft, die Datenbank bleibt unverändert. Das Protokoll des letzten Web-Updates steht in `/opt/n8crosslink/data/update.log` und im Adminportal. Wird `install.sh` erneut von Hand gestartet, fragt er, ob aktualisiert oder neu eingerichtet werden soll.

## HTTPS / Domain

Im letzten Schritt kann der Installer nginx als Reverse-Proxy mit Let's Encrypt einrichten. Weitere Domains, Erneuern und Entfernen gehen
danach jederzeit im Webinterface unter **⚙️ Admin → 🔒 Domains & HTTPS** (ab 1.12.0) – siehe [KONFIGURATION.md](KONFIGURATION.md#-domains--https).
Beides nutzt denselben Helfer `n8x-certs.sh` (inkl. WebSocket-Weiterleitung für die Live-Daten). Voraussetzung: DNS zeigt auf den Server
und Port 80/443 sind erreichbar.
