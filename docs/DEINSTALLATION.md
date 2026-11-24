# Deinstallation & von vorn beginnen

Es gibt drei Wege – vom sanften Zurücksetzen bis zum kompletten Entfernen. **Vorher immer ein Backup erstellen** (siehe [BACKUP.md](BACKUP.md)).

| Ziel | Weg | Was bleibt |
|---|---|---|
| Verlauf leeren | Admin → 💾 Backup & Neuanfang → „Last Heard, Statistik und Ereignisse löschen“ | Einstellungen, Benutzer |
| Einstellungen neu machen | dort „Alle Einstellungen auf Standard“ | Benutzer, Verlauf |
| Wie frisch installiert | dort „Alles“ → Login danach **n8schicht / n8schicht** | Programm, Dienste, sudo |
| Programm neu installieren, Daten behalten | `sudo /opt/n8crosslink/uninstall.sh` → **1** | `/opt/n8crosslink/data` |
| Komplett entfernen | `sudo /opt/n8crosslink/uninstall.sh` → **2** | nur die Backups in `/root/n8crosslink-backups` |

Das Zurücksetzen im Webinterface verlangt das Superadmin-Passwort zur Bestätigung.

## Ablauf von `uninstall.sh`

1. **Auswahl:** Daten behalten oder alles entfernen.
2. **Backup anbieten:** Es wird mit dem Superadmin-Passwort verschlüsselt und nach `/root/n8crosslink-backups/` geschrieben.
3. **Dienste entfernen:** `n8crosslink`, Update-Auslöser (`n8crosslink-update.path/.service`) und sudo-Freigaben (`/etc/sudoers.d/n8crosslink`).
4. **nginx-Konfiguration** entfernen, optional auch das Let's-Encrypt-Zertifikat.
5. **Programm** entfernen. Bei „alles“ zusätzlich Daten, Dienstbenutzer `n8crosslink` und optional den Quellcode in `/usr/local/src/N8Crosslink`.
6. **md380-emu** nur auf Nachfrage entfernen. Standard ist nein, falls DVSwitch/Analog_Bridge ihn noch nutzt. Optional auch die DVSwitch-Paketquelle.
7. **Alte Dienste wieder einschalten:** SvxLink, MMDVM_Bridge, Analog_Bridge und die Zello-Bridge, die der Installer abgeschaltet hatte. Er hat sie sich in `/var/lib/n8crosslink/disabled-services` gemerkt.

Ohne Rückfragen:

```bash
sudo /opt/n8crosslink/uninstall.sh --keep-data --yes     # Programm weg, Daten bleiben
sudo /opt/n8crosslink/uninstall.sh --purge --yes         # alles weg (ohne Backup-Frage: --no-backup)
```

## Neu beginnen

```bash
git clone https://github.com/dhartmann1979/N8Crosslink.git
cd N8Crosslink
sudo ./install.sh
```

* Wurden die Daten behalten, erkennt der Installer die vorhandene Datenbank und fragt: aktualisieren oder neu einrichten.
* Nach einem kompletten Entfernen fragt der Installer gleich zu Beginn nach einem **Backup (.n8xbak)**. Mit dem Superadmin-Passwort von damals wird alles wiederhergestellt (Einstellungen, Zugangsdaten, Benutzer, Last Heard, Avatare). Ist md380-emu eingestellt, wird er automatisch mitinstalliert.
