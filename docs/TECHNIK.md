# Technik & Protokolle

## Aufbau

```
n8crosslink/
  app.py          Start: Bridge + Webserver (uvicorn) in einem asyncio-Prozess
  core.py         Router: aktive Quelle, Ziele, Sperrzeit, Time-Out, Last Heard
  frn.py          FRN-Client (TCP) – GSM 06.10 WAV49 über libgsm
  zello.py        Zello Channel API (WebSocket) – Opus über libopus
  dmr/port.py     HomeBrew-Peer (UDP), RX/TX-Streams, ID-Datenbank
  dmr/burst.py    DMR-Bursts, AMBE-Extraktion, Talker Alias
  dmr/fec.py      BPTC(196,96), RS(12,9), Embedded LC, Golay(20,8), QR(16,7)
  vocoder.py      N8schicht-Vocoder (Client, Profile, Regler) · AMBE3000-Paketprotokoll: USB / AMBEserver
  ambe_worker.py  eigener Prozess: lib/libn8vocoder.so per ctypes (absturzsicher)
  preview.py      Probehören/Messen (Eingang ↔ Ausgang, Bandbreite, ESTOI/PESQ)
  db.py           SQLite: Einstellungen, Benutzer, Sitzungen, Last Heard, Ereignisse, DMR-IDs
  web/            FastAPI, WebSocket, Dashboard (HTML/CSS/JS)
```

Internes Audioformat: 8 kHz, 16 Bit mono, Rahmen zu 20 ms (160 Samples).

### 📊 Live-Anzeige: Pegel und Audio-Spektrum (seit 1.29.0)

Während einer Durchsage schickt der Router über `/ws` bis zu **25× je Sekunde** eine kleine Meldung
`{"type":"meter","src":"frn","l":-24.3,"p":-9.8,"b":[…32 Werte…]}`:

- `l` Pegel (RMS, dBFS) und `p` Spitze (dBFS) des letzten Rahmens der sprechenden Station (nach der Eingangs-Aufbereitung),
- `b` das Spektrum: FFT über die letzten 512 Abtastwerte (64 ms, Hann-Fenster), zusammengefasst in **32 logarithmisch verteilte
  Bänder von 120 Hz bis 3,9 kHz**, je 0…100 (0 = −70 dB, 100 = Vollaussteuerung).

Die Werte sind reine Anzeige – geschaltet wird nie über den Pegel. Sie enthalten keine Adressen und gehen deshalb an alle Besucher,
nicht nur an Admins (hören lässt sich daraus nichts). Kommt ein Client nicht hinterher, werden Spektrum-Meldungen ausgelassen
(Warteschlange > 25), Statusmeldungen nie. Die Seite zeichnet mit der Bildwiederholrate des Bildschirms (`requestAnimationFrame`)
und glättet dazwischen: Anstieg ~40 ms, Abfall 26 dB/s, Spitzenmarken mit Haltezeit. Ist alles in Ruhe, zeichnet sie nichts.

| Netz | Codec | Paket |
|---|---|---|
| FRN | GSM 06.10 (MS-GSM/WAV49) | 325 Byte = 10 Rahmen = 200 ms |
| DMR | AMBE+2 (72 Bit inkl. FEC) | Burst = 3 Rahmen = 60 ms |
| Zello | Opus, 16 kHz (8→16 kHz FIR-Resampler) | 60 ms |

## FRN

Login `CT:<VX>2014003</VX><EA>…</EA><PW>…</PW><ON>Call, Name</ON><CL>0</CL><BC>Crosslink</BC>…<NT>Raum</NT>`, Antwort Protokollversion + `<AL>OK|ADMIN|OWNER|NETOWNER|WRONG|BLOCK</AL>`. Danach `RX0`, `ST:0` und Polling mit `P`. Der Server antwortet mit einem Typ-Byte: 0 Idle, 1 DO_TX (+2 Byte), 2 Voice (+2 Byte Client-Index + 325 Byte), 3 Client-Liste (+2 Byte, Zähler, Zeilen), 4–10 weitere Listen. Der Sprechername kommt über den Client-Index aus der Raumliste (`<ON>Call, Name</ON>`).

## DMR (HomeBrew)

`RPTL` → `RPTACK`+Salt → `RPTK` sha256(Salt+Passwort) → `RPTACK` → `RPTC` (302 Byte, Felder wie DMRGateway) → `RPTACK` → optional `RPTO` → verbunden; Keepalive `RPTPING`/`MSTPONG` alle 5 s, nach 30 s ohne Pong neuer Login. `DMRD`-Pakete (55 Byte) mit Slot/Calltype/Frametype/dtype-vseq im Byte 15.

Gesendet wird: 3× Voice-LC-Header (BPTC + RS(12,9) mit Maske 0x969696, Slot-Type Golay(20,8), Data-Sync), Superframes A–F (A mit Voice-Sync, B–E mit EMB QR(16,7) und Embedded-LC-Fragmenten, F mit Null-Embedded), jedes zweite Superframe trägt statt des LC einen Talker-Alias-Block (FLCO 0x04–0x07, wie MMDVMHost), zum Schluss Terminator-with-LC (Maske 0x999999). Alle FEC-Routinen sind gegen eine unabhängige Implementierung (dmr_utils3) geprüft.

Empfangen: Talker Alias aus dem Embedded LC wird dekodiert und ersetzt den Namen aus der ID-Datenbank, sobald er vollständig ist.

## Zello

`logon` (Token, JWT RS256 aus Issuer + Key, oder Benutzer/Passwort bei Zello Work), `on_channel_status`, `on_stream_start`/Binärpakete `0x01|stream_id|packet_id|opus`/`on_stream_stop`; Senden mit `send_text_message` (Sprechername), `start_stream` (Codec-Header `{rate LE16, 1, 60}`), Binärpaketen im 60-ms-Takt und `stop_stream`.

## Router

* genau eine aktive Quelle; Ziele = alle anderen Netze, die online sind und deren Route eingeschaltet ist
* während einer Durchsage wird jeder andere Beginn **blockiert** (Last-Heard-Status „blockiert“)
* ein Netz, in das gerade noch gesendet wird (Puffer läuft leer), nimmt nichts an; danach gilt die Sperrzeit
* Time-Out-Timer beendet überlange Durchgänge
