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

### 📊 Live-Anzeige: Pegel und Audio-Spektrum in Echtzeit (seit 1.30.0)

Für **jeden 20-ms-Tonrahmen** der sprechenden Station rechnet der Router (`SpectrumMeter` in `audio/dsp.py`):

- Pegel (RMS) und Spitze des Rahmens in dBFS (nach der Eingangs-Aufbereitung),
- das Spektrum: Hann-Fenster über die letzten 256 Abtastwerte (32 ms), FFT mit 512 Punkten, **48 Bänder von 0 Hz bis 4 kHz**
  auf der Mel-Skala (unten feiner, oben gröber – wie man hört), je ein Zeichen `0-9A-Za-z-_` = 0…63 (0 = −72 dB, 63 = 0 dBFS).

Rahmen, die zusammen ankommen, gehen als **eine** Meldung über `/ws` hinaus:
`{"type":"meter","src":"frn","ms":20,"fmax":4000,"f":[[-24.3,-9.8,"…48 Zeichen…"], …]}` – bei FRN 10 Rahmen je 200-ms-Paket,
bei DMR und Zello 3 Rahmen je 60 ms. Die Seite spielt sie **im 20-ms-Takt** ab (wie der Ton), zeichnet mit der Bildwiederholrate,
übernimmt jeden neuen Wert sofort und lässt nur nach unten kurz ausklingen (Pegel 60 dB/s, Bänder volle Höhe in ~0,35 s).
Liegt sie mehr als ~250 ms zurück, springt sie auf den neuesten Stand. Schneller als das Netz liefert geht es nicht:
FRN schickt Ton immer in 200-ms-Paketen.

**Warum 0–4 kHz und nicht mehr?** Alle drei Netze kommen mit **8 kHz Abtastrate** in die Bridge (FRN: GSM 06.10, DMR: AMBE+2,
Zello wird schon beim Dekodieren auf 8 kHz gebracht). Nach Nyquist enthält ein 8-kHz-Signal nur Frequenzen bis **4 kHz** –
das ist der ganze mögliche Bereich. 16 kHz würde eine Abtastrate von 32 kHz voraussetzen, die es in keinem dieser Funknetze gibt.

Die Werte sind reine Anzeige – geschaltet wird nie über den Pegel. Sie enthalten keine Adressen und gehen an alle Besucher
(hören lässt sich daraus nichts). Kommt ein Client nicht hinterher, werden Spektrum-Meldungen ausgelassen (Warteschlange > 60),
Statusmeldungen nie. Ist alles in Ruhe, zeichnet die Seite nichts.

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
