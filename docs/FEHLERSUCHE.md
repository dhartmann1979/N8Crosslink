# Fehlersuche

| Symptom | Ursache / Lösung |
|---|---|
| Dienst startet nicht, im Log `[Errno 13] … bind on address ('0.0.0.0', 80): permission denied` | Web-Port unter 1024 (z. B. 80). Ab 1.2.1 erhält der Dienst dafür `CAP_NET_BIND_SERVICE` – `sudo /opt/n8crosslink/update.sh` ausführen. Alternativ Port 8080: `cd /opt/n8crosslink && sudo -u n8crosslink venv/bin/python -m n8crosslink.cli set general web_port 8080 && sudo systemctl restart n8crosslink` |
| Dienst startet nicht, Ursache unklar | Von Hand starten zeigt die Fehlermeldung: `sudo systemctl stop n8crosslink; cd /opt/n8crosslink && sudo -u n8crosslink env N8X_DB=/opt/n8crosslink/data/crosslink.db venv/bin/python -m n8crosslink` |
| FRN „Login abgelehnt (WRONG)“ | E-Mail/Passwort falsch oder Konto nicht freigeschaltet. Das FRN-Passwort ist das dynamische Passwort aus der Registrierung. |
| FRN „BLOCK“ | Konto im Raum gesperrt – Raum-Admin fragen. |
| FRN: „keine Sendefreigabe vom Server“ | Raum war belegt oder Konto darf nicht senden (Sende-Rechte am Server prüfen). |
| DMR bleibt in „Login“ | Server/Port falsch oder UDP gesperrt. `journalctl -u n8crosslink -f` |
| DMR „MSTNAK“ | Peer-ID am Server nicht erlaubt, Passwort falsch oder die ID ist bereits durch eine andere Bridge (MMDVM_Bridge) belegt. |
| DMR-Audio stumm | Vocoder offline (Statusleiste). Admin → Vocoder → 🧪 Testen. |
| DMR-Audio abgehackt | Vorpuffer (Allgemein) auf 300–400 ms erhöhen; bei md380-emu auf x86 CPU-Last prüfen. |
| Zello „not authorized“ | Token abgelaufen (Entwickler-Token gilt 30 Tage) → neuen Token eintragen oder Issuer + Private Key verwenden. |
| Zello-Kanal „offline“ | Konto ist nicht Mitglied des Kanals oder der Kanal erlaubt keine API-Clients. |
| Durchsagen werden „blockiert“ | Gleichzeitig wurde auf einem anderen Netz gesprochen – gewollter Schleifenschutz. Sperrzeit ggf. verkleinern. |
| „sudo nicht eingerichtet“ im Adminportal | Einmal `sudo /opt/n8crosslink/update.sh` ausführen (legt sudo-Freigaben und Update-Dienst an). |
| „Update jetzt“ passiert nichts | Admin → ⬆️ Updates → Protokoll; sonst `journalctl -u n8crosslink-update -n 50`. |
| Login n8schicht geht nicht | Es gibt schon andere Benutzer (der Standard-Login wird nur beim allerersten Start angelegt). Passwort neu setzen: `echo 'neu12345' \| sudo -u n8crosslink /opt/n8crosslink/venv/bin/python -m n8crosslink.cli admin n8schicht` |
| Keine Avatare | ID-Listen noch nicht geladen (Admin → ID-Listen & Avatare), Station nicht bei FreeRadioID registriert oder ohne Profilbild. |
| Dashboard ohne Live-Daten hinter nginx | WebSocket-Weiterleitung fehlt (`Upgrade`/`Connection`-Header, siehe `systemd/nginx-n8crosslink.conf`). |

Mehr Details im Log: in `/etc/systemd/system/n8crosslink.service` an `ExecStart` ein ` --debug` anhängen, `systemctl daemon-reload && systemctl restart n8crosslink`.
