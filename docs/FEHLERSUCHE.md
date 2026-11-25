# Fehlersuche

**Zuerst immer:** `sudo /opt/n8crosslink/install.sh --diagnose` – zeigt Version, Dienste, Port (inkl. Bind-Test mit den Dienst-Rechten), Stand des N8schicht-Vocoders, Vocoder-Test, Zello-Schlüssel (nur Fingerabdruck) und die letzten Logzeilen; gespeichert in `/tmp/n8crosslink-diagnose.txt`, ohne Passwörter.

| Symptom | Ursache / Lösung |
|---|---|
| Vocoder offline: „N8schicht-Vocoder nicht gebaut“ | `sudo /opt/n8crosslink/install.sh --build-vocoder` oder Admin → Vocoder → „🔨 Vocoder bauen“. Die Quellen liegen im Programmordner, gebraucht wird nur `g++` (installiert der Installer). Bei Fehlern zeigt der Installer die letzten Compiler-Zeilen |
| DMR-Ton klingt gepresst, dumpf oder zu scharf | Admin → Vocoder → 🎚️ Klang-Einstellungen: Grundabstimmung „N8schicht“, dann einzelne Regler; mit Probehören (auch eigene WAV) Eingang und Ausgang vergleichen. Alle Regler sind in [VOCODER.md](VOCODER.md) erklärt |
| md380-emu läuft noch / Dienst `md380-emu` fehlerhaft | Ab 1.4.0 nicht mehr gebraucht – `sudo /opt/n8crosslink/update.sh` entfernt ihn |
| „Bind-Test“ beim Start von Hand meldet Errno 13 auf Port 80 | Beim Start von Hand fehlt das Port-Recht des Dienstes – das ist normal. Maßgeblich ist der Bind-Test in `--diagnose`, der mit den Dienst-Rechten prüft |
| Dienst startet nicht, im Log `[Errno 13] … bind on address ('0.0.0.0', 80): permission denied` | Web-Port unter 1024 (z. B. 80). Ab 1.2.1 erhält der Dienst dafür `CAP_NET_BIND_SERVICE` – `sudo /opt/n8crosslink/update.sh` ausführen. Alternativ Port 8080: `cd /opt/n8crosslink && sudo -u n8crosslink venv/bin/python -m n8crosslink.cli set general web_port 8080 && sudo systemctl restart n8crosslink` |
| Dienst startet nicht, Ursache unklar | Von Hand starten zeigt die Fehlermeldung: `sudo systemctl stop n8crosslink; cd /opt/n8crosslink && sudo -u n8crosslink env N8X_DB=/opt/n8crosslink/data/crosslink.db venv/bin/python -m n8crosslink` |
| FRN „Login abgelehnt (WRONG)“ | E-Mail/Passwort falsch oder Konto nicht freigeschaltet. Das FRN-Passwort ist das dynamische Passwort aus der Registrierung. |
| FRN „BLOCK“ | Konto im Raum gesperrt – Raum-Admin fragen. |
| FRN: „keine Sendefreigabe vom Server“ | Raum war belegt oder Konto darf nicht senden (Sende-Rechte am Server prüfen). |
| Nach einem Update ist das Dashboard nicht erreichbar | Ab 1.5.1 stellt `update.sh` automatisch die vorige Version wieder her, wenn die neue nicht startet (siehe Update-Log). Sonst: `sudo systemctl status n8crosslink`, `sudo journalctl -u n8crosslink -n 60`, `sudo /opt/n8crosslink/install.sh --diagnose` |
| DMR-Teilnehmer erscheinen nur als Nummer | Bis 1.5.0 scheiterte das Laden der FreeRadioID-CSV am Zeilenende `\n\r` – auf 1.5.1 aktualisieren, dann Admin → ID-Listen → „Jetzt aktualisieren“ |
| DMR bleibt in „Login“ | Server/Port falsch oder UDP gesperrt. `journalctl -u n8crosslink -f` |
| DMR „MSTNAK“ | Peer-ID am Server nicht erlaubt, Passwort falsch oder die ID ist bereits durch eine andere Bridge (MMDVM_Bridge) belegt. |
| Von DMR kommt alles an, **nach DMR geht nichts** (FRN/Zello → DMR) | Der Server verwirft die Sendungen der Bridge. Im Log des Servers nachsehen: `journalctl -u hblink4 --since "1 hour ago" \| grep -E "<Peer-ID>\|GUEST\|Inbound routing denied\|contention\|hijacking"`. Häufigste Ursache bei **HBlink4-FreeRadioID** mit Secure Login: Die Bridge meldet sich mit der lokalen Passphrase an und ist damit **Gast** – Gäste dürfen nur in die Gast-Talkgroups senden (Standard 26501–26503), Empfang geht trotzdem. Abhilfe: Peer-ID mit dem persönlichen FreeRadioID-Passwort anmelden, das Muster der Bridge am Server mit `"freeradioid": false` von FreeRadioID ausnehmen, oder die Sende-TG in die Gast-Talkgroups aufnehmen. Achtung: HBlink4 schreibt dabei nur „Inbound routing denied … not in allowed list [262, …]“ – auch wenn 262 in der Liste steht; entscheidend ist die Zeile „logged in as FreeRadioID GUEST“ beim Login. Andere Ursachen: Sende-TG/Zeitschlitz nicht in der Liste des Musters („Inbound routing denied“), Zeitschlitz gerade belegt („Stream contention“/„Hang time hijacking“). In *Netze → DMR* zeigt die Zeile „Pakete“ hinter ⇡, ob die Bridge überhaupt sendet. |
| DMR-Audio stumm | Vocoder offline (Statusleiste). Admin → Vocoder → 🧪 Testen. |
| DMR-Audio abgehackt | Vorpuffer (Allgemein) auf 300–400 ms erhöhen; CPU-Last prüfen (der N8schicht-Vocoder braucht unter 1 ms je Rahmen). |
| DMR-Audio verzerrt, Roboterstimme, wird erst nach Neustart besser | Bis 1.3.0 mit md380-emu bekannt – aktualisieren (N8schicht-Vocoder). Klingt der Software-Vocoder zu dünn: Pegel unter *Vocoder* anpassen oder USB-Stick nutzen ([VOCODER.md](VOCODER.md)). |
| Zello „not authorized“ | Token abgelaufen (Entwickler-Token gilt 30 Tage) → neuen Token eintragen oder Issuer + Private Key verwenden. |
| Zello-Kanal „offline“ | Konto ist nicht Mitglied des Kanals oder der Kanal erlaubt keine API-Clients. |
| Durchsagen werden „blockiert“ | Gleichzeitig wurde auf einem anderen Netz gesprochen – gewollter Schleifenschutz. Sperrzeit ggf. verkleinern. |
| „sudo nicht eingerichtet“ im Adminportal | Einmal `sudo /opt/n8crosslink/update.sh` ausführen (legt sudo-Freigaben und Update-Dienst an). |
| „Update jetzt“ passiert nichts | Admin → System → ⬆️ Update → Update-Protokoll; sonst `journalctl -u n8crosslink-update -n 50`. |
| Login n8schicht geht nicht | Es gibt schon andere Benutzer (der Standard-Login wird nur beim allerersten Start angelegt). Passwort neu setzen: `echo 'neu12345' \| sudo -u n8crosslink /opt/n8crosslink/venv/bin/python -m n8crosslink.cli admin n8schicht` |
| Keine Avatare | ID-Listen noch nicht geladen (Admin → ID-Listen & Avatare), Station nicht bei FreeRadioID registriert oder ohne Profilbild. |
| Dashboard ohne Live-Daten hinter nginx | WebSocket-Weiterleitung fehlt (`Upgrade`/`Connection`-Header, siehe `systemd/nginx-n8crosslink.conf`). |

Mehr Details im Log: in `/etc/systemd/system/n8crosslink.service` an `ExecStart` ein ` --debug` anhängen, `systemctl daemon-reload && systemctl restart n8crosslink`.
