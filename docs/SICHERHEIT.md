# 🔐 Sicherheit & N8 Kit

[← Übersicht](../README.md)

Diese Seite beschreibt, wie das Dashboard sich schützt, was du als Betreiber noch tun kannst (Reverse-Proxy), und das **N8 Kit** – die gemeinsamen Bausteine, die N8 Crosslink, HBlink4-FreeRadioID, adn-frn-server und N8-HotSpot gleich aussehen und sich gleich verhalten lassen.

## Was das Dashboard selbst tut

### Keine offene API-Beschreibung

FastAPI legt normalerweise unter `/docs`, `/redoc` und `/openapi.json` eine vollständige Beschreibung aller Routen an – mit allen Admin-Endpunkten und ihren Datenformaten. Das ist **abgeschaltet**; die drei Adressen antworten mit 404.

Zum Entwickeln lässt sie sich einschalten, nur mit einer Umgebungsvariablen beim Start:

```bash
N8_API_DOCS=1 /opt/n8crosslink/venv/bin/python -m n8crosslink
```

### Sicherheits-Header bei jeder Antwort

| Header | Wert | Wofür |
|---|---|---|
| `Content-Security-Policy` | `default-src 'self'`; Skripte, Styles, Schriften nur vom eigenen Server; Bilder auch `https:` (Kartenkacheln, Avatare); Verbindungen nur zum eigenen Server (`ws:`/`wss:` für Live-Daten); `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'self'` | fremde Skripte, Plugins, `<base>`-Tricks, fremde Formularziele und Einbetten in fremde Seiten werden vom Browser blockiert |
| `Strict-Transport-Security` | `max-age=31536000` | nur wenn die Seite über **HTTPS** kommt (direkt oder über einen Proxy mit `X-Forwarded-Proto: https`); verhindert SSL-Stripping |
| `Permissions-Policy` | Kamera, Mikrofon, Zahlung, USB, Seriell, Sensoren aus; Standort nur für die eigene Seite | Seiten können diese Geräte nicht ansprechen |
| `X-Content-Type-Options` | `nosniff` | Dateien werden nur als das ausgeführt, was sie sind |
| `X-Frame-Options` | `SAMEORIGIN` | kein Einbetten in fremde Seiten (Clickjacking) |
| `Referrer-Policy` | `same-origin` | Adressen des Dashboards gehen nicht an fremde Seiten |
| `Cross-Origin-Opener-Policy` / `-Resource-Policy` | `same-origin` / `same-site` | Fenster und Dateien sind von fremden Seiten getrennt |

Der Header `server: uvicorn` wird **nicht** mehr gesendet.

`'unsafe-inline'` ist für Skripte noch erlaubt, weil die Seiten Klick-Handler direkt im HTML haben. Deshalb ist das Escapen (nächster Abschnitt) die eigentliche Schutzschicht gegen XSS; die CSP sorgt dafür, dass ein Angreifer keine **fremden** Skripte nachladen und keine Daten an fremde Server schicken kann.

### Daten aus den Netzen

Rufzeichen, Namen und Orte kommen von FRN-Clients, aus DMR (ID-Liste, Talker Alias) und von Zello-Benutzern – fremde Eingaben. Jedes dieser Felder geht beim Anzeigen durch `esc()` bzw. wird als `textContent` gesetzt (Live, On Air, Last Heard, Netze, Statistik, Statusleiste, Ereignisse). Das Farbschema wird auf dem Server geprüft (nur bekannte Schlüssel, Farben als `#rrggbb`, Zahlen im erlaubten Bereich), bevor es in die Seite kommt.

### Anmeldung

Sitzungs-Cookie `HttpOnly`/`SameSite`; der Standard-Login `n8schicht / n8schicht` wird angemahnt, bis er geändert ist. Mithören läuft über einen eigenen WebSocket, der nur angemeldete Admins annimmt.

## HobbyRadioPortal auf diesem Rechner (ohne Token)

- Seit 1.11.0 gibt es **keine API-Tokens** mehr (die Tabelle `api_tokens` wird beim Start gelöscht, `cli api-token` gibt es nicht mehr).
- Als Portal gilt nur ein **direkter Aufruf auf diesem Rechner**: Absender und `Host` Loopback (`127.0.0.1`, `::1`, `localhost`),
  Kopfzeile `X-HobbyRadioPortal: 1` und **keine** Proxy-Kopfzeile (`X-Forwarded-For`, `X-Real-IP`, `Forwarded`, `X-Forwarded-Host/-Proto`,
  `Via`, `CF-Connecting-IP`, `True-Client-IP`, `X-Client-IP`). nginx vor der Brücke (auch die Vorlage `systemd/nginx-n8crosslink.conf`)
  setzt `X-Forwarded-For` – über ihn kommt niemand an die Verwaltung. Ein eigener Reverse-Proxy muss das ebenso tun.
- Jedes Programm auf diesem Rechner könnte sich als Portal ausgeben. Wer das nicht will: `N8X_PORTAL_LOCAL=0` in der Umgebung des Dienstes.
- Das Portal erreicht nur diese Pfade: `/api/admin/settings` (lesen/ändern), `/api/admin/restart`
  (Bridge), `/api/admin/vocoder/params|options|preview`, `/api/admin/vocoder-test`, `/api/admin/announce/preview`,
  `/api/admin/frn/request-password`, `/api/admin/events`, `/api/admin/ids`, `/api/admin/ids/update`, `/api/admin/avatars/refresh`,
  `/api/admin/serial-ports`. Alles andere antwortet `401`.
- Gesperrt auch innerhalb der Einstellungen: Web-Adresse, Web-Port und Update-Quelle.
- Passwörter (FRN, DMR, Zello, Private Key) gehen nie hinaus; leer gelassen bleiben sie unverändert.
- Jede Änderung im Ereignisprotokoll als `api:HobbyRadioPortal (<Portal-Benutzer>)` (`X-Portal-User`, bereinigt).

## Reverse-Proxy davor (empfohlen)

N8 Crosslink bringt kein eigenes HTTPS mit. Soll das Dashboard aus dem Internet erreichbar sein, gehört ein **Reverse-Proxy** mit HTTPS davor: Zertifikate, Header und Protokolle an einer Stelle. Das Dashboard lauscht dann nur lokal (Admin → Allgemein → Web-Adresse `127.0.0.1`, Port z. B. 8080; Neustart des Dienstes). Die Weiterleitungs-Header (`X-Forwarded-Proto`) wertet N8 Crosslink aus.

**Caddy** (holt das Zertifikat selbst):

```caddy
crosslink.example.org {
    encode zstd gzip
    header {
        Strict-Transport-Security "max-age=31536000"
        -Server
    }
    reverse_proxy 127.0.0.1:8080
}
```

**nginx**:

```nginx
server {
    listen 443 ssl http2;
    server_name crosslink.example.org;
    ssl_certificate     /etc/letsencrypt/live/crosslink.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crosslink.example.org/privkey.pem;
    server_tokens off;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;          # Live-Daten (WebSocket)
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;      # damit das Dashboard HSTS setzt
        proxy_read_timeout 1h;
    }
}
server { listen 80; server_name crosslink.example.org; return 301 https://$host$request_uri; }
```

Die übrigen Sicherheits-Header setzt das Dashboard selbst; der Proxy muss sie nur durchreichen (beide Beispiele tun das). FRN (TCP 10024), DMR (UDP) und Zello (WebSocket nach außen) laufen **nicht** über den Proxy. Der Proxy muss WebSockets durchreichen (Live-Daten und Mithören) – beide Beispiele tun das.

## N8 Kit

Gemeinsame Bausteine für **HBlink4-FreeRadioID, adn-frn-server, N8-HotSpot und N8 Crosslink**. Die Dateien sind in allen vier Repositories **identisch**; wer eine ändert, kopiert sie in die anderen.

| Datei | Inhalt |
|---|---|
| `n8crosslink/web/static/n8-kit.js` | Sprache DE/EN, Übersetzung, Sprachumschalter, Update-Hinweis, Updates-Kachel, Update-Fortschritt |
| `n8crosslink/web/static/n8-kit.css` | Aussehen dieser Bausteine, auf Basis der N8-Theme-2-Farben |
| `n8crosslink/web/static/n8-theme.js`, `n8-theme.css`, `n8-light.css` | N8 Theme 2: Farbprofile, Farbeditor, helles Profil Daylight |
| `n8crosslink/web/n8_security.py` | Sicherheits-Header, API-Doku aus, kein `server`-Header |
| `update.sh` | Prüfung nach dem Update und Rollback (bei N8 Crosslink schon seit 1.5.1; schreibt jetzt `data/update.result` im gemeinsamen Format) |
| `n8crosslink/web/static/i18n-crosslink.js` | die englischen Texte dieser Oberfläche (eigene Datei je Projekt; hier ist Deutsch die Grundsprache) |

### Sprache DE | EN

<p align="center"><img src="screenshots/dashboard-englisch.png" alt="Dashboard auf Englisch" width="95%"></p>

- Der Umschalter steht in der Kopfzeile neben 🔗 Links und dem Login, auch ohne Anmeldung.
- **Standard ist Deutsch.** Die Wahl gilt **sofort**, ohne Neuladen, und wird im Cookie `n8_lang` gespeichert. Cookies gelten für alle Ports eines Servers – wer also hier Englisch wählt, sieht auch die anderen N8schicht-Oberflächen auf diesem Server auf Englisch.
- Für einen Link in einer bestimmten Sprache: `?lang=en` oder `?lang=de` an die Adresse hängen.
- Übersetzt wird die fertige Seite: Texte und die Attribute `title`, `placeholder`, `aria-label`, `alt`. Neue Inhalte (Live-Daten, Fenster) werden übersetzt, sobald sie erscheinen; auch Rückfragen (`confirm`) folgen der Sprache. Rufzeichen, Namen, Raum-/Kanal-/TG-Namen und Code bleiben, wie sie sind.
- Fehlt ein Wort, erscheint das Original. Ergänzen: in `i18n-crosslink.js` eine Zeile `'Deutscher Text': 'English text',` – ohne führende Emojis und ohne Satzzeichen am Ende, Zahlen über die `rules` am Ende der Datei.

### Updates – überall gleich

| | |
|---|---|
| Prüfen | jede volle Stunde, auch ohne Anmeldung; installiert wird nur auf Knopfdruck |
| Hinweis | unter der Statusleiste, nur für Admins: *Update verfügbar: alt → neu* · Was ist neu? · Jetzt aktualisieren · Details · Später (ein Tag) |
| Installieren | Fenster mit Neuerungen, dann drei Schritte mit Fortschritt; die Seite lädt danach neu |
| Prüfung danach | die neue Version ruft ihre eigene Weboberfläche auf |
| Rollback | `update.sh` prüft die Weboberfläche per HTTP und stellt sonst die vorige Version wieder her |
| Ergebnis | *Letztes Update* in Admin → Updates: erfolgreich oder zurückgenommen, mit Zeit |

---

Weiter: [Betrieb](BETRIEB.md) · [Fehlersuche](FEHLERSUCHE.md)
