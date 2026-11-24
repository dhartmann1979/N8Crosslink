# Zello verbinden – Schritt für Schritt

N8 Crosslink meldet sich über die **Zello Channel API** (WebSocket) wie eine eigene Zello-Station in **einem Kanal** an. Was im Kanal gesprochen wird, geht nach FRN und DMR; was aus FRN/DMR kommt, spricht die Bridge in den Kanal – mit dem Namen der Station als Textnachricht (abschaltbar).

```
Zello-App(s) ──► Zello-Server ──WebSocket──► N8 Crosslink ──► FRN / DMR
```

Du brauchst:

1. ein **eigenes Zello-Konto für die Bridge** (nicht dein persönliches – ein Konto kann nicht gleichzeitig in der App und in der Bridge angemeldet sein, sonst werfen sie sich gegenseitig hinaus),
2. einen **Kanal**, in dem dieses Konto sprechen darf,
3. einen **Zugang zur Channel API** (Entwickler-Token oder Issuer + Private Key) – bei Zello Work nicht nötig.

---

## 1. Konto für die Bridge anlegen

1. Zello-App installieren (Handy oder PC) und **ein neues Konto** registrieren, z. B. `n8crosslink` oder `DB0XYZ-Bridge`.
2. Profil ausfüllen (Name, Bild) – Name und Bild sieht man im Kanal, wenn die Bridge spricht.
3. Benutzername und Passwort notieren; beides kommt später ins Adminportal.
4. Danach in der App wieder **abmelden** (die Bridge braucht das Konto für sich).

## 2. Kanal vorbereiten

* **Eigener Kanal:** In der App mit dem Bridge-Konto oder deinem eigenen Konto einen Kanal anlegen (z. B. `N8schicht`). Wer ihn mit deinem Konto anlegt, macht das Bridge-Konto danach zum **Moderator** oder erlaubt allen das Sprechen.
* **Vorhandener Kanal:** Das Bridge-Konto muss Mitglied sein und **sprechen dürfen**. Bei Kanälen mit Passwort oder „nur Moderatoren sprechen“ den Kanal-Admin bitten, das Bridge-Konto freizuschalten.
* Den Kanal mit dem Bridge-Konto **einmal in der App betreten** (Kanal hinzufügen). Danach wieder abmelden.

Der Kanalname muss **exakt** (Groß/Kleinschreibung, Leerzeichen) so im Adminportal stehen wie in Zello.

## 3. Zugang zur Channel API

### a) Entwickler-Token (schnell, zum Testen)

1. Auf **developers.zello.com** mit einem Zello-Konto anmelden (das darf dein persönliches sein) und das Entwicklerprofil ausfüllen.
2. Unter **Keys** auf **Add Key** klicken.
3. Den **Sample Development Token** vollständig kopieren.
4. Im Adminportal: *Authentifizierung = Entwickler-Token*, Token in *Auth-Token* einfügen.

> ⚠️ Der Entwickler-Token läuft nach **30 Tagen** ab. Danach verbindet sich Zello nicht mehr („not authorized“), bis ein neuer Token eingetragen ist. Für den Dauerbetrieb Variante b) nehmen.

### b) Issuer + Private Key (Dauerbetrieb, empfohlen)

Hier erzeugt die Bridge ihren Anmelde-Token bei jeder Verbindung selbst (JWT, RS256, 60 s gültig) – nichts läuft ab.

1. Auf **developers.zello.com → Keys** denselben Schlüssel öffnen (oder neu anlegen).
2. **Issuer** kopieren.
3. **Private Key** kopieren – den kompletten Block von `-----BEGIN PRIVATE KEY-----` bis `-----END PRIVATE KEY-----`.
4. Im Adminportal: *Authentifizierung = Issuer + Private Key*, Issuer und Private Key eintragen, speichern.

Alternativ die Schlüsseldatei als `zello.key` (oder `zello*.pem`) nach `/opt/n8crosslink/` legen und `sudo /opt/n8crosslink/install.sh --fix-perms` ausführen: Der Installer verschiebt sie an einen sicheren Ort, übernimmt sie in die Datenbank, prüft den Fingerabdruck und löscht die Datei sicher (`shred`). Ab dann liegt der Schlüssel nur noch in der Datenbank – und verschlüsselt im Backup. Fingerabdruck anzeigen:

```
cd /opt/n8crosslink && sudo -u n8crosslink venv/bin/python -m n8crosslink.cli zello-key-info
```

> 🔐 Der Private Key ist ein Geheimnis wie ein Passwort: nicht in Chats, Screenshots oder Git-Repositorys.

### c) Zello Work

Bei einem eigenen Zello-Work-Netz (`NETZ.zellowork.com`) braucht es keinen Entwickler-Schlüssel:

* *Server* = `wss://zellowork.io/ws/NETZ` (NETZ = Name deines Netzes),
* *Authentifizierung = keine (Zello Work)*,
* Benutzer und Kanal im Zello-Work-Dashboard anlegen und das Bridge-Konto dem Kanal zuweisen.

## 4. Im Adminportal eintragen

**Admin → 💬 Zello:**

| Feld | Eintrag |
|---|---|
| Zello aktiv | an |
| WebSocket-Server | `wss://zello.io/ws` (Zello) bzw. `wss://zellowork.io/ws/NETZ` (Zello Work) |
| Kanal | exakter Kanalname |
| Benutzername / Passwort | Bridge-Konto aus Schritt 1 |
| Authentifizierung | Entwickler-Token, Issuer + Private Key oder keine |
| Abtastrate Senden | 16 kHz (empfohlen). FRN und DMR liefern 8 kHz, die Bridge rechnet hoch – mehr als 4 kHz Tonumfang entsteht dadurch nicht |
| Opus-Bitrate | 16000–24000 bit/s reichen für Sprache |
| Paketlänge | 60 ms (Standard der Zello-Apps) |
| Sprechername als Textnachricht | an (Standard) = vor jedem Durchgang aus FRN/DMR erscheint z. B. „🎙 DO1TEST Tobias · DMR“ im Kanal |
| Text-Vorlage | Platzhalter `{name}` `{callsign}` `{source}` `{detail}` |
| Ende-Erkennung | so viele ms ohne Audio = Durchgang zu Ende (falls Zello kein `stop_stream` schickt) |
| Pegel | Zello → Bridge bzw. Bridge → Zello in dB |

**Speichern & neu starten.** In der Statusleiste steht nach wenigen Sekunden **Zello online**; unter *Netze → Zello* siehst du Kanalstatus und Anzahl der Benutzer im Kanal.

## 5. Testen

1. In der Zello-App (mit deinem persönlichen Konto) den Kanal öffnen und kurz sprechen → im Dashboard erscheint **ON AIR · Zello** mit deinem Namen und Avatar; FRN und DMR bekommen den Ton.
2. Auf FRN oder DMR sprechen → in der App hörst du den Ton, davor (wenn eingeschaltet) die Textnachricht mit dem Stationsnamen.
3. Als Admin oben im Menü **🎧 Mithören** einschalten (Lautstärke über den Pfeil ▾ daneben), um selbst mitzuhören.

## 6. Fehlersuche

| Meldung / Verhalten | Ursache und Abhilfe |
|---|---|
| `not authorized` / `invalid token` | Entwickler-Token abgelaufen (30 Tage) oder falsch kopiert → neuer Token oder auf *Issuer + Private Key* umstellen |
| `channel is not ready` / `channel not found` | Kanalname falsch geschrieben, Kanal existiert nicht oder Bridge-Konto ist kein Mitglied |
| Verbindung steht, aber Zello hört nichts von FRN/DMR | Bridge-Konto darf im Kanal nicht sprechen (Moderation, „Listen only“) → im Kanal freischalten |
| Zello bricht ständig ab | Bridge-Konto ist gleichzeitig in einer App angemeldet → dort abmelden |
| Zello verbindet nicht mit *Issuer + Private Key* | Nicht der vollständige PEM-Block kopiert (die Zeilen BEGIN und END müssen dabei sein) oder Issuer passt nicht zum Schlüssel |
| Kein Avatar | Die Channel API liefert keine Profilbilder – unter *Admin → ID-Listen & Avatare* eigene Bilder je Zello-Name hochladen |

Logs: `journalctl -u n8crosslink -f | grep -i zello`. Der Watchdog verbindet Zello nach Abbrüchen selbst neu.
