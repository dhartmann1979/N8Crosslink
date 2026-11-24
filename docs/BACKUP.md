# Backup & Wiederherstellung

> ## 🔐 WICHTIG – das Superadmin-Passwort ist der Schlüssel
> Jedes Backup ist **vollständig verschlüsselt**. Der Schlüssel ist das **Passwort des Superadmins zum Zeitpunkt des Backups**.
> **Ohne dieses Passwort lässt sich das Backup nicht wiederherstellen** – auch nicht durch den Entwickler.
> Bewahre das Superadmin-Passwort im **Passwortsafe** auf, am besten zusammen mit dem Namen der Backupdatei.
> Wird das Passwort später geändert, brauchen ältere Backups weiterhin das alte Passwort.

## Inhalt

Gesichert wird alles, was N8 Crosslink ausmacht:

* Einstellungen inkl. Zugangsdaten (FRN, DMR, Zello)
* Benutzer
* Last Heard, Statistik, Ereignisse
* ID-Listen, Talkgroups, Avatare

Die Datenbank wird im laufenden Betrieb konsistent kopiert (SQLite-Backup-API).

## Format – kein Klartext

```
<name>.n8xbak = "N8XBAK" | Version | Salt (16) | Nonce (12) | AES-256-GCM( tar.gz: crosslink.db, manifest.json, system.json )
Schlüssel     = scrypt(Superadmin-Passwort, Salt, N=2^15, r=8, p=1) → 256 Bit
```

Auch das Manifest (Datum, Version, Umfang) ist verschlüsselt. Ein falsches Passwort und jede Veränderung der Datei fallen beim Entschlüsseln auf (GCM-Authentifizierung).

## Im Webinterface (Admin → 💾 Backup & Neuanfang, nur Superadmin)

* **Backup erstellen:** Superadmin-Passwort eingeben → „Verschlüsseltes Backup erstellen“ → Download `n8crosslink-backup-<rechner>-<datum>.n8xbak`.
* **Wiederherstellen:** Datei und Passwort angeben → **Prüfen** (zeigt Datum, Version, Umfang) → **Wiederherstellen**. Die Bridge startet neu, danach neu anmelden.

## Auf der Kommandozeile

```bash
cd /opt/n8crosslink
sudo -u n8crosslink venv/bin/python -m n8crosslink.cli backup --out /tmp        # fragt das Superadmin-Passwort
sudo -u n8crosslink venv/bin/python -m n8crosslink.cli restore /tmp/<datei>.n8xbak
sudo systemctl restart n8crosslink
```

Beim Neuinstallieren fragt `install.sh` direkt nach einem Backup, und `uninstall.sh` bietet vorher eines an.

## Umzug ins HobbyRadioPortal

Ziehst du N8 Crosslink auf den Server des [HobbyRadioPortals](https://github.com/dhartmann1979/HobbyRadioPortal) um (dort laufen meist
auch FRN-Server und HBlink4), ist dieses Backup das **Umzugspaket** (ab 1.9.0):

1. Hier als Superadmin **⚙️ Admin → 💾 Backup & Neuanfang → Verschlüsseltes Backup erstellen** und die `.n8xbak`-Datei herunterladen.
2. Im Web-Installer des Portals (`http://<neuer Server>/setup`) im Schritt **🔀 Crosslink** die Datei hochladen, das Superadmin-Passwort
   eingeben und **🔍 Prüfen** – das Portal zeigt Version, Rechner, Datum und Zahlen aus dem Backup.
3. *N8 Crosslink auf diesen Server umziehen* wählen; Haken **FRN- und DMR-Server über 127.0.0.1**, wenn beide auf den neuen Server
   kommen. Beim Umzug holt der Root-Helfer des Portals N8 Crosslink von GitHub und ruft `install.sh` ohne Rückfragen auf:

```bash
N8X_RESTORE=/root/hrp-xl.…/backup.n8xbak N8X_RESTORE_PASSWORD_FILE=/root/hrp-xl.…/pw \
N8X_WEB_PORT=8070 N8X_LOCAL_LINKS=1 N8X_PORTAL_TOKEN_FILE=/root/hrp-xl.…/token ./install.sh
```

4. Danach den **alten Crosslink abschalten**, sonst laufen zwei Bridges im selben Raum: `sudo systemctl disable --now n8crosslink`.

Das Passwort liegt nur kurz in einer Datei (600, nur root bzw. der Dienst des Portals) und wird nach dem Umzug gelöscht, ebenso die
hochgeladene Backupdatei. Diese Variablen gehen auch ohne Portal – z. B. für einen eigenen Umzug per Skript.

