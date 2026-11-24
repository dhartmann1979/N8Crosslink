/* N8 Crosslink – English words for the web interface (N8 Kit, base language German),
 * plus the German words of the shared N8 Theme 2 editor (which is written in English).
 * Keys are the texts without leading emoji and trailing punctuation; see n8-kit.js. */
N8Kit.i18n.add({
    base: 'de',
    en: {
        // Kopfzeile, Statusleiste, Live
        'Live-Daten': 'Live data', 'Statistik': 'Statistics', 'Netze': 'Networks', 'Mithören': 'Listen in', 'Mithören (nur für angemeldete Admins)': 'Listen in (logged-in admins only)',
        'Lautstärke': 'Volume', 'Lautstärke Mithören': 'Listen-in volume', 'Ruhe': 'Quiet', 'Pegel der sprechenden Station': 'Level of the talking station', 'Anmelden': 'Log in', 'Abmelden': 'Log out',
        'Ruhe auf allen Netzen': 'Quiet on all networks', 'Gerade aktiv': 'Active now', 'On Air · über DMR': 'On air · via DMR', 'On Air · über FRN': 'On air · via FRN', 'On Air · über Zello': 'On air · via Zello',
        'Netze online': 'Networks online', 'Durchgänge heute': 'Talks today', 'Sendezeit heute': 'Airtime today', 'Stationen heute': 'Stations today', 'Blockiert heute': 'Blocked today',
        'Durchgänge': 'Talks', 'Durchg': 'Talks', 'Sendezeit': 'Airtime', 'Stationen': 'Stations', 'Blockiert': 'Blocked', 'Mehr anzeigen': 'Show more', 'Zuletzt': 'Last',
        'Zeit': 'Time', 'Station': 'Station', 'Quelle': 'Source', 'Übertragen nach': 'Sent to', 'Dauer': 'Duration', 'Raum / TG / Kanal': 'Room / TG / channel', 'Stationen im Raum': 'Stations in the room',
        'sendet': 'transmitting', 'empfängt': 'receiving', 'sendet:': 'transmitting:', 'empfängt:': 'receiving:', 'bereit': 'ready', 'unbekannt': 'unknown', 'fehlt': 'missing', 'nicht': 'not',
        'Noch kein Superadmin angelegt – jetzt einrichten, um das Adminportal zu nutzen.': 'No superadmin yet – set one up now to use the admin portal.', 'Superadmin anlegen': 'Create superadmin',
        'Einstellungen gespeichert. Für FRN/DMR/Zello/Vocoder ist ein Neustart der Bridge nötig.': 'Settings saved. FRN/DMR/Zello/vocoder need a restart of the bridge.', 'Jetzt neu starten': 'Restart now',
        'Standard-Login': 'Default login', 'ist noch aktiv – bitte unter Admin → Benutzer ein eigenes Passwort setzen.': 'is still active – please set your own password under Admin → Users.', 'Passwort ändern': 'Change password',

        // Statistik, Netze
        'Heute': 'Today', '7 Tage': '7 days', '30 Tage': '30 days', '90 Tage': '90 days', 'Aktivität pro Netz': 'Activity per network', 'Aktivste Stationen': 'Most active stations',
        'Meist über': 'Mostly via', 'Wann wird gesprochen': 'When people talk', 'Aktueller Zustand': 'Current state', 'Verbunden seit': 'Connected since', 'Online seit': 'Online since', 'Pakete': 'Packets',
        'Rahmen': 'Frames', 'Server-Version': 'Server version', 'Protokollversion': 'Protocol version', 'Kanal-Status': 'Channel status', 'Sende-Status': 'Transmit state', 'Login-Phase': 'Login phase',
        'Zugang OK': 'Access OK', 'Benutzer online': 'Users online', 'Ping / Pong': 'Ping / pong', 'Ereignisse': 'Events', 'Ereignisprotokoll': 'Event log', 'Peer-ID': 'Peer ID', 'Zeitschlitz': 'Time slot',
        'Raum': 'Room', 'Kanal': 'Channel', 'Konto': 'Account', 'Status': 'Status', 'Typ': 'Type', 'Info': 'Info', 'Bridge': 'Bridge',

        // Admin: Navigation
        'Allgemein': 'General', 'Routing': 'Routing', 'ID-Listen & Avatare': 'ID lists & avatars', 'Updates': 'Updates', 'Backup & Neuanfang': 'Backup & start over', 'Benutzer': 'Users', 'System': 'System',
        'Aussehen': 'Appearance', 'Vocoder': 'Vocoder', 'Adminbereich der N8 Crosslink.': 'Admin area of N8 Crosslink.', 'Änderungen wirken sofort im laufenden Betrieb.': 'Changes take effect at once, while running.',

        // Admin: Allgemein
        'Titel im Dashboard': 'Title in the dashboard', 'Servername / Domain': 'Server name / domain', 'Web-Adresse (Bind)': 'Web address (bind)', 'Web-Port': 'Web port',
        '0.0.0.0 = alle Schnittstellen · Neustart des Dienstes nötig': '0.0.0.0 = all interfaces · service restart needed', 'Neustart des Dienstes nötig': 'service restart needed',
        'Hinweis-Banner im Dashboard': 'Notice banner in the dashboard', 'Links-Menü (JSON-Liste mit name/url)': 'Link menu (JSON list with name/url)', 'Last Heard aufbewahren (Tage)': 'Keep last heard (days)',
        'Stündlich (zur vollen Stunde) auf Updates prüfen': 'Check for updates every full hour', 'GitHub-Repository für Updates': 'GitHub repository for updates', 'Branch': 'Branch',
        'Sprachansage des Rufzeichens am Anfang eines Durchgangs': 'Spoken callsign at the start of a talk',
        'Computerstimme (espeak-ng) sagt das Rufzeichen an, danach folgt der Ton – der Durchgang läuft um die Länge der Ansage verzögert': 'A computer voice (espeak-ng) says the callsign, then the audio follows – the talk is delayed by the length of the announcement',
        'Ansage nach FRN': 'Announce to FRN', 'Ansage nach DMR': 'Announce to DMR', 'Ansage nach Zello': 'Announce to Zello', 'Ansagetext': 'Announcement text',
        'Platzhalter: {call} = Rufzeichen, {name} = Name – z. B. „{call}“ oder „{call} {name}“': 'Placeholders: {call} = callsign, {name} = name – e.g. "{call}" or "{call} {name}"',
        'Rufzeichen sprechen als': 'Speak callsigns as', 'Buchstaben (D O 1 T E S T)': 'Letters (D O 1 T E S T)', 'NATO-Alphabet (Delta Oscar Eins …)': 'NATO alphabet (Delta Oscar One …)',
        'Auch ohne Rufzeichen (Name ansagen)': 'Also without callsign (announce the name)', 'Je Station höchstens alle … Minuten': 'At most every … minutes per station', 'Sprechtempo (Wörter/Min.)': 'Speaking rate (words/min)',
        'Lautstärke (dBFS Spitze)': 'Volume (dBFS peak)', 'Pause nach der Ansage (ms)': 'Pause after the announcement (ms)', 'Ansage probehören – mit den Werten aus dem Formular:': 'Preview the announcement – with the values from the form:',
        'Ansage anhören': 'Play announcement', 'Speichern': 'Save', 'Speichern & neu starten': 'Save & restart', 'Übernehmen': 'Apply',

        // Admin: FRN
        'FRN – FreeRadioNetwork': 'FRN – FreeRadioNetwork', 'Server': 'Server', 'Port': 'Port', 'Backup-Server': 'Backup server', 'Backup-Port': 'Backup port', 'E-Mail (FRN-Konto)': 'E-mail (FRN account)',
        'Passwort (FRN)': 'Password (FRN)', 'Rufzeichen': 'Callsign', 'Name / Bezeichnung': 'Name / description', 'Band / Kanal (BC)': 'Band / channel (BC)', 'Band / Kanal': 'Band / channel',
        '„Crosslink“ oder z. B. 446.03125FM CTC131.8': '"Crosslink" or e.g. 446.03125FM CTC131.8', 'Client-Typ': 'Client type', 'Land': 'Country', 'Ort': 'City', 'Ort – Ortsteil / Locator': 'City – district / locator',
        'Beschreibung': 'Description', 'FRN-Raum': 'FRN room', 'Raum (Net)': 'Room (net)', 'Sprechername als FRN-Textnachricht': "Talker's name as FRN text message",
        'Textnachricht nur an diese Stationen (privat)': 'Text message only to these stations (private)',
        'Rufzeichen mit Komma, z. B. DL1ABC, DB0XYZ – leer = öffentlich an alle im Raum. Privat ploppt bei den übrigen Stationen nichts auf.': 'Callsigns separated by commas, e.g. DL1ABC, DB0XYZ – empty = public to everybody in the room. Private messages pop up nowhere else.',
        'Ende-Erkennung RX (ms)': 'End detection RX (ms)', 'FRN liefert 200-ms-Blöcke – 240 ms sind ein guter Wert': 'FRN delivers 200 ms blocks – 240 ms is a good value',
        'Kein Sprachpaket für diese Zeit = Durchgang beendet (SvxLink: 1000)': 'No voice packet for this long = talk ended (SvxLink: 1000)', 'Pegel FRN → Bridge (dB)': 'Level FRN → bridge (dB)', 'Pegel Bridge → FRN (dB)': 'Level bridge → FRN (dB)',
        'System Manager (für „Passwort anfordern“)': 'System Manager (for "request password")', 'System-Manager-Port': 'System Manager port',
        'Standard sysman.freeradionetwork.eu – bei eigenem FRN-Netz dessen System Manager': 'Default sysman.freeradionetwork.eu – with an own FRN network its System Manager',
        'Noch kein FRN-Passwort? Rufzeichen, Name, E-Mail, Band/Kanal, Land und Ort ausfüllen und anfordern – das Passwort kommt per E-Mail.': 'No FRN password yet? Fill in callsign, name, e-mail, band/channel, country and city and request it – the password comes by e-mail.',
        'Passwort anfordern': 'Request password', 'Watchdog: neu öffnen nach (s) ohne Antwort': 'Watchdog: reopen after (s) without answer', 'Watchdog: Netz nach … s offline komplett neu aufbauen': 'Watchdog: rebuild the network completely after … s offline',
        'Zusätzlich zur normalen Wiederverbindung (Standard 120 s)': 'In addition to the normal reconnect (default 120 s)', 'Watchdog': 'Watchdog',

        // Admin: DMR
        'DMR – HomeBrew (HBlink4 / FreeDMR)': 'DMR – HomeBrew (HBlink4 / FreeDMR)', 'Server (HBlink4 / FreeDMR)': 'Server (HBlink4 / FreeDMR)', 'Passwort (Passphrase)': 'Password (passphrase)',
        'leer lassen = unverändert · Bei HBlink4-FreeRadioID: persönliches FreeRadioID-Passwort – mit der Server-Passphrase ist die Bridge nur Gast und darf nicht in TG 262 senden': 'leave empty = unchanged · With HBlink4-FreeRadioID: personal FreeRadioID password – with the server passphrase the bridge is only a guest and may not transmit on TG 262',
        'Peer-/Repeater-ID': 'Peer/repeater ID', '7- oder 9-stellig, muss am Server erlaubt sein': '7 or 9 digits, must be allowed on the server', 'Sende-Talkgroup': 'Transmit talkgroup', 'Empfangs-Talkgroup': 'Receive talkgroup',
        '0 = alle Gruppenrufe auf dem Zeitschlitz': '0 = all group calls on the time slot', 'Optionen (RPTO)': 'Options (RPTO)', 'z. B. TS2=262 – leer = Serverkonfiguration': 'e.g. TS2=262 – empty = server configuration',
        'Color Code': 'Colour code', 'RX-Frequenz (Hz)': 'RX frequency (Hz)', 'TX-Frequenz (Hz)': 'TX frequency (Hz)', 'Breite': 'Latitude', 'Länge': 'Longitude', 'Standort': 'Location',
        'Quell-ID für Sendungen ins DMR': 'Source ID for transmissions into DMR', 'Rufzeichen → eigene DMR-ID, falls in der ID-Datenbank': 'callsign → own DMR ID, if in the ID database',
        'Talker Alias (Stationsname) im Sprachrahmen senden': 'Send talker alias (station name) in the voice frames', 'Zusätzlich DMRA-Pakete senden (nicht für HBlink4!)': 'Also send DMRA packets (not for HBlink4!)',
        'Ende-Erkennung RX ohne Terminator (ms)': 'End detection RX without terminator (ms)', 'Pegel DMR → Bridge (dB)': 'Level DMR → bridge (dB)', 'Pegel Bridge → DMR (dB)': 'Level bridge → DMR (dB)',
        'Time-Out-Timer pro Durchgang (s)': 'Time-out timer per talk (s)', 'Vorpuffer DMR/Zello-Ausgang (ms)': 'Pre-buffer DMR/Zello output (ms)', 'RX-/TX-Talkgroup-Name': 'RX/TX talkgroup name',

        // Admin: Zello
        'Zello – Channel API': 'Zello – Channel API', 'WebSocket-Server': 'WebSocket server', 'Zello: wss://zello.io/ws · Zello Work: wss://zellowork.io/ws/NETZ': 'Zello: wss://zello.io/ws · Zello Work: wss://zellowork.io/ws/NETWORK',
        'Zello-Benutzername': 'Zello username', 'Passwort': 'Password', 'Authentifizierung': 'Authentication', 'Entwickler-Token': 'Developer token', 'Issuer + Private Key (JWT)': 'Issuer + private key (JWT)',
        'keine (Zello Work)': 'none (Zello Work)', 'Auth-Token': 'Auth token', 'Issuer': 'Issuer', 'Private Key (PEM)': 'Private key (PEM)', 'nur für „Issuer + Private Key“ – leer lassen = unverändert': 'only for "Issuer + private key" – leave empty = unchanged',
        'Abtastrate Senden': 'Sample rate for sending', '16 kHz (empfohlen)': '16 kHz (recommended)', 'Opus-Bitrate (bit/s)': 'Opus bitrate (bit/s)', 'Paketlänge (ms)': 'Packet length (ms)',
        'Sprechername als Textnachricht in den Kanal': "Talker's name as text message into the channel", 'Text-Vorlage': 'Text template', 'Platzhalter: {name} {callsign} {source} {detail}': 'Placeholders: {name} {callsign} {source} {detail}',
        'Ende-Erkennung ohne stop_stream (ms)': 'End detection without stop_stream (ms)', 'Pegel Zello → Bridge (dB)': 'Level Zello → bridge (dB)', 'Pegel Bridge → Zello (dB)': 'Level bridge → Zello (dB)',
        'leer lassen = unverändert': 'leave empty = unchanged', 'gesetzt – leer lassen = unverändert': 'set – leave empty = unchanged',

        // Admin: Routing
        'Welche Quelle wird in welches Netz übertragen? Änderungen wirken sofort.': 'Which source goes into which network? Changes take effect at once.', 'Sperrzeit nach Aussendung (ms)': 'Lock time after transmitting (ms)',
        'Schützt vor Ping-Pong zwischen den Netzen': 'Prevents ping-pong between the networks', 'Zeitplan': 'Schedule',

        // Admin: Vocoder
        'Vocoder (AMBE+2)': 'Vocoder (AMBE+2)', 'Betriebsart': 'Mode', 'N8schicht-Vocoder (Software)': 'N8schicht vocoder (software)', 'USB-Stick (AMBE3000)': 'USB stick (AMBE3000)', 'AMBEserver (Netz)': 'AMBEserver (network)',
        'Test ohne Vocoder': 'Test without vocoder', 'AMBE+2 in Software – Fork des DroidStar-Codecs, auf Verständlichkeit abgestimmt. Ohne Zusatzhardware und ohne qemu; läuft als eigener Prozess (x86 und ARM).': 'AMBE+2 in software – fork of the DroidStar codec, tuned for intelligibility. No extra hardware and no qemu; runs as its own process (x86 and ARM).',
        'ThumbDV, DVstick 30, DV3000 direkt per USB/seriell. Beste Qualität, kein Zusatzdienst nötig.': 'ThumbDV, DVstick 30, DV3000 directly via USB/serial. Best quality, no extra service needed.',
        'AMBE3000 an einem anderen Rechner hinter AMBEserver (UDP 2460).': 'AMBE3000 on another computer behind AMBEserver (UDP 2460).', 'Nur zum Testen der Verbindungen – DMR-Audio ist dann stumm.': 'Only for testing the connections – DMR audio is silent then.',
        'Bibliothek (leer = automatisch)': 'Library (empty = automatic)', 'Standard: /opt/n8crosslink/lib/libn8vocoder.so': 'Default: /opt/n8crosslink/lib/libn8vocoder.so', 'Klang-Einstellungen': 'Sound settings',
        'Pegel vor dem Kodieren (dB)': 'Level before encoding (dB)', 'Pegel nach dem Dekodieren (dB)': 'Level after decoding (dB)', 'Vocoder testen': 'Test vocoder', 'Vocoder bauen / aktualisieren': 'Build / update vocoder',
        'Probehören (Eingang → DMR → Ausgang)': 'Preview (input → DMR → output)', 'WAV-Datei': 'WAV file', 'Eigener Testsatz (leer = Standardsatz)': 'Own test sentence (empty = default sentence)', 'Testen': 'Test',

        // Admin: ID-Listen, Avatare
        'ID-Listen': 'ID lists', 'DMR-IDs': 'DMR IDs', 'Bei FreeRadioID registriert': 'Registered at FreeRadioID', 'Registriert bei FreeRadioID.net': 'Registered at FreeRadioID.net', 'Talkgroup-Namen': 'Talkgroup names',
        'ID-Listen aktualisieren': 'Update ID lists', 'ID-Listen jetzt aktualisieren': 'Update ID lists now', 'Avatare jetzt aktualisieren': 'Update avatars now', 'Avatare anzeigen': 'Show avatars', 'Avatare im Cache': 'Avatars cached',
        'ID-Listen und Avatare 1× täglich automatisch, sofort per Knopf': 'ID lists and avatars automatically once a day, at once with the button', 'Quellen': 'Sources',
        'FreeRadioID: alle DMR-IDs (CSV)': 'FreeRadioID: all DMR IDs (CSV)', 'FreeRadioID: alle DMR-IDs (JSON, Ersatz)': 'FreeRadioID: all DMR IDs (JSON, fallback)', 'FreeRadioID: registrierte IDs (JSON)': 'FreeRadioID: registered IDs (JSON)',
        'FreeRadioID: registrierte IDs (CSV, Ersatz)': 'FreeRadioID: registered IDs (CSV, fallback)', 'FreeRadioID: Einzelabfrage unbekannter IDs ({id})': 'FreeRadioID: single lookup of unknown IDs ({id})',
        'Ersatzquelle RadioID.net (CSV)': 'Fallback source RadioID.net (CSV)', 'Talkgroup-Namen (JSON)': 'Talkgroup names (JSON)', 'Nur FreeRadioID-registrierte IDs abfragen': 'Look up FreeRadioID-registered IDs only',
        'Avatar-URL DMR ({id})': 'Avatar URL DMR ({id})', 'Avatar-URL Zello ({username}, optional)': 'Avatar URL Zello ({username}, optional)', 'FRN-/Zello-Rufzeichen → FreeRadioID-Avatar': 'FRN/Zello callsign → FreeRadioID avatar',
        'Die Zello Channel API liefert keine Profilbilder – hier eine eigene Quelle eintragen oder unten Bilder hochladen': 'The Zello Channel API delivers no profile pictures – enter an own source here or upload pictures below',
        'Zello-Avatare (eigene Bilder)': 'Zello avatars (own pictures)', 'Bild (PNG/JPEG/WebP/GIF)': 'Picture (PNG/JPEG/WebP/GIF)', 'Hochladen': 'Upload', 'Noch keine eigenen Bilder.': 'No own pictures yet.', 'Löschen': 'Delete',

        // Admin: Updates (N8 Kit), Backup, Benutzer, System
        'Update-Dienst': 'Update service', 'eingerichtet': 'set up', 'Update-Dienst fehlt – einmal': 'Update service missing – run once', 'ausführen': '', 'zurückgesetzt auf': 'rolled back to',
        'Verschlüsseltes Backup erstellen': 'Create encrypted backup', 'Backup herunterladen': 'Download backup', 'Backup wiederherstellen': 'Restore backup', 'Backupdatei (.n8xbak)': 'Backup file (.n8xbak)',
        'WICHTIG – Superadmin-Passwort = Schlüssel des Backups': 'IMPORTANT – superadmin password = key of the backup',
        'Das Backup wird vollständig verschlüsselt (AES-256-GCM, kein Klartext). Der Schlüssel ist das': 'The backup is fully encrypted (AES-256-GCM, no plain text). The key is the',
        'Superadmin-Passwort': 'superadmin password', 'zum Zeitpunkt des Backups. Ohne dieses Passwort lässt sich das Backup': 'at the time of the backup. Without this password the backup cannot be',
        'wiederherstellen – auch nicht vom Entwickler. Bitte das Superadmin-Passwort im': 'restored – not even by the developer. Please keep the superadmin password in the',
        'Passwortsafe': 'password safe', 'aufbewahren (z. B. zusammen mit dem Backup-Dateinamen).': '(e.g. together with the backup file name).',
        'Enthält alles: Einstellungen inkl. Zugangsdaten (FRN, DMR, Zello), Benutzer, Last Heard, Statistik, Ereignisse, ID-Listen, Talkgroups und Avatare.': 'Contains everything: settings incl. credentials (FRN, DMR, Zello), users, last heard, statistics, events, ID lists, talkgroups and avatars.',
        'Superadmin-Passwort (dein aktuelles Passwort)': 'Superadmin password (your current password)', 'Superadmin-Passwort zum Zeitpunkt des Backups': 'Superadmin password at the time of the backup',
        'Superadmin-Passwort zur Bestätigung': 'Superadmin password to confirm', 'Wiederherstellen': 'Restore', 'Von vorn beginnen': 'Start over', 'Was zurücksetzen?': 'What to reset?',
        'Last Heard, Statistik und Ereignisse löschen': 'Delete last heard, statistics and events', 'Alle Einstellungen auf Standard (Benutzer und Verlauf bleiben)': 'All settings to default (users and history stay)',
        'Alles – wie neu installiert (Login danach n8schicht / n8schicht)': 'Everything – like freshly installed (login afterwards n8schicht / n8schicht)', 'Zurücksetzen': 'Reset',
        'Vorher am besten ein Backup erstellen. Komplett deinstallieren geht auf dem Server mit': 'Best create a backup first. A complete uninstall works on the server with', '(siehe Doku „Deinstallation“).': '(see the docs "Uninstall").',
        'Konfiguration exportieren': 'Export configuration', 'Importieren': 'Import',
        'Neuer Benutzer / Passwort ändern': 'New user / change password', 'Benutzername': 'Username', 'Passwort (min. 8 Zeichen)': 'Password (min. 8 characters)', 'Passwort wiederholen': 'Repeat password',
        'Rolle': 'Role', 'Angelegt': 'Created', 'du': 'you',
        'Dienste': 'Services', 'Dienst': 'Service', 'Autostart': 'Autostart', 'Autostart an': 'Autostart on', 'Autostart aus': 'Autostart off', 'Start': 'Start', 'Stopp': 'Stop', 'Neustart': 'Restart',
        'Dienst neu starten': 'Restart service', 'Bridge neu starten': 'Restart bridge', 'Server neu starten': 'Restart server', 'Berechtigungen prüfen & korrigieren': 'Check & fix permissions', 'Prüfen': 'Check',
        'sudo nicht eingerichtet – einmal sudo /opt/n8crosslink/update.sh ausführen': 'sudo not set up – run sudo /opt/n8crosslink/update.sh once', 'Version': 'Version',
        'Bitte warten …': 'Please wait …', 'Gleiche Farbtechnik wie HBlink4-FreeRadioID, adn-frn-server und N8-HotSpot: Profil wählen, dann jede Farbe ändern – die ganze Seite zeigt es sofort, gespeichert wird erst mit „Speichern“.': 'Same colour engine as HBlink4-FreeRadioID, adn-frn-server and N8-HotSpot: pick a profile, then change any colour – the whole page shows it at once, it is only stored with "Save".',
        'Aussehen speichern': 'Save appearance', 'N8-Standard': 'N8 standard', 'Aussehen gespeichert': 'Appearance saved', 'Eigene Werte löschen': 'Clear own values',
        'Titel': 'Title', 'Untertitel': 'Subtitle',
    },
    rules: [
        [/^(\d+)–(\d+) Uhr: (\d+)$/, '$1–$2 h: $3'], [/^Stand (.+)$/, 'as of $1'], [/^(.+) · Stand (.+)$/, '$1 · as of $2'],
        [/^Raum (.+) · (\d+) Stationen$/, 'Room $1 · $2 stations'], [/^Raum (.+)$/, 'Room $1'], [/^Kanal (.+)$/, 'Channel $1'],
        [/^FRN verbunden mit Raum „(.+)“ \((.+)\)$/, 'FRN connected to room "$1" ($2)'], [/^Zello verbunden mit Kanal „(.+)“$/, 'Zello connected to channel "$1"'],
        [/^DMR verbunden mit (.+) als (\d+) \((.+)\)$/, 'DMR connected to $1 as $2 ($3)'], [/^(FRN|DMR|Zello) aktiv$/, '$1 active'],
        [/^⇣ (\d+) empfangen · ⇡ (\d+) gesendet$/, '⇣ $1 received · ⇡ $2 sent'], [/^(\d+) Wiederverbindungen · (\d+) Neuaufbauten$/, '$1 reconnects · $2 rebuilds'],
        [/^(\d+)× neu geöffnet$/, 'reopened $1×'], [/^vor (.+)$/, (m, a) => a === 'gerade eben' ? 'just now' : `${a} ago`], [/^· vor gerade eben$/, '· just now'],
        [/^Vocoder (.+): bereit$/, 'Vocoder $1: ready'], [/^(.+) · aktiv$/, '$1 · active'],
        [/^Encode (\d+) · Decode (\d+) · Timeouts (\d+) · Wiederholt (\d+) · Neu geöffnet (\d+)$/, 'Encode $1 · decode $2 · timeouts $3 · repeated $4 · reopened $5'],
        [/^(\d+) mit Bild \((.+)\) · (\d+) ohne · zuletzt aktualisiert (.+)$/, (m, a, b, c, d) => `${a} with picture (${b}) · ${c} without · last updated ${d === 'noch nie' ? 'never' : d}`],
        [/^ID-Listen aktualisiert: ([\d.,]+) DMR-IDs\. (\d+) bei FreeRadioID registriert\. (\d+) Talkgroups$/, 'ID lists updated: $1 DMR IDs. $2 registered at FreeRadioID. $3 talkgroups'],
        [/^([\d.,]+) DMR-IDs · (\d+) FreeRadioID · (\d+) Talkgroups · Stand (.+)$/, '$1 DMR IDs · $2 FreeRadioID · $3 talkgroups · as of $4'],
        [/^Update verfügbar: (.+)$/, 'Update available: $1'], [/^Aktualisiert auf (.+)$/, 'Updated to $1'],
    ],
});

// The shared colour editor (N8 Theme 2) is written in English: German words for it
N8Kit.i18n.add({
    base: 'en',
    de: {
        'Colour profile': 'Farbprofil', 'Own colours': 'Eigene Farben', 'Accent': 'Akzent', 'Accent 2': 'Akzent 2', 'Background': 'Hintergrund', 'Text': 'Text',
        'Buttons, numbers, active tabs': 'Schaltflächen, Zahlen, aktive Tabs', 'Second colour of buttons and the title': 'Zweite Farbe von Schaltflächen und Titel', 'Page colour behind everything': 'Seitenfarbe hinter allem',
        'Glow top left': 'Leuchten oben links', 'Glow top right': 'Leuchten oben rechts', 'Glow bottom': 'Leuchten unten', 'Card tint': 'Kartentönung', 'Colour mixed into the glass cards': 'In die Glaskarten gemischte Farbe',
        'Card brightness': 'Kartenhelligkeit', 'How strongly the glass cards stand out': 'Wie stark die Glaskarten hervortreten', 'Glass blur': 'Glasunschärfe', 'Off = faster on old phones': 'Aus = schneller auf alten Handys',
        'Background glow': 'Hintergrundleuchten', '0 = flat background': '0 = flacher Hintergrund', 'Roundness': 'Rundung', 'Corners of cards and buttons': 'Ecken von Karten und Schaltflächen',
        'Click a colour to change it; ↺ takes it from the profile again.': 'Farbe anklicken zum Ändern; ↺ nimmt sie wieder aus dem Profil.', 'Back to the profile colour': 'Zurück zur Profilfarbe',
        'Empty = suits the background automatically': 'Leer = passt sich automatisch dem Hintergrund an', 'from profile': 'aus dem Profil', 'Readable (contrast 18.3 : 1)': 'Gut lesbar (Kontrast 18,3 : 1)',
        'Title': 'Titel', 'Subtitle': 'Untertitel', 'Save': 'Speichern', 'Live': 'Live',
    },
    rules: [[/^Readable \(contrast ([\d.]+) : 1\)$/, (m, a) => `Gut lesbar (Kontrast ${a.replace('.', ',')} : 1)`], [/^Hard to read \(contrast ([\d.]+) : 1\)$/, (m, a) => `Schwer lesbar (Kontrast ${a.replace('.', ',')} : 1)`]],
});
