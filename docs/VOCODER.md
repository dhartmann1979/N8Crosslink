# Vocoder: N8schicht-Vocoder (Software) oder USB-Stick

DMR überträgt Sprache als **AMBE+2** (3600 bit/s mit Fehlerschutz, 2450 bit/s Sprache, 20-ms-Rahmen). Für den Übergang zu FRN (GSM) und Zello (Opus) muss N8 Crosslink AMBE+2 **dekodieren** (DMR → FRN/Zello) und **kodieren** (FRN/Zello → DMR). Die Betriebsart wählst du im **Adminportal → 🎛️ Vocoder** (oder im Installer, Schritt 8).

| Betriebsart | Wann | Einstellungen |
|---|---|---|
| 🧠 **N8schicht-Vocoder** (Standard) | keine Zusatzhardware | Klang-Einstellungen im Popup (unten) |
| 🔌 **USB-Stick** | ThumbDV, DVstick 30, DV3000 am selben Rechner | Gerät (`/dev/ttyUSB0` oder `/dev/serial/by-id/…`), Baudrate (460800 bzw. 230400 beim DV3000-Hat) |
| 🌐 **AMBEserver** | AMBE3000 hängt an einem anderen Rechner | Adresse/Port (Standard 2460) |
| 🧪 **Test** | nur Verbindungen testen | DMR-Audio ist stumm |

Nach *Speichern & neu starten* startet die Bridge neu. **🧪 Vocoder testen** schickt einen 1-kHz-Ton über 25 Rahmen durch Encoder und Decoder und zeigt Laufzeit je Rahmen und die Frequenz, die herauskommt.

---

## 🧠 Der N8schicht-Vocoder

Ein **Fork des Software-Codecs aus [DroidStar](https://github.com/nostar/DroidStar)** von Doug McLain (Verzeichnis `mbe/`, C-Schnittstelle `ambe2.h`, Lizenz GPL-3.0-or-later). Die Quellen liegen im Repository unter [`third_party/n8schicht-vocoder/`](../third_party/n8schicht-vocoder/) – mit Herkunft (Commit), Lizenz und allen Änderungen.

**Was der Fork gegenüber DroidStar ändert**

| Änderung | Warum |
|---|---|
| **Eigene Klang-Abstimmung „N8schicht“** (gemessen, s. u.) | bessere Verständlichkeit, weniger „komprimierter“ Klang, glatter Frequenzgang bis zur AMBE-Grenze |
| **Höhen-Ergänzung 3,65–4 kHz** (in der Bridge) | AMBE+2 endet bei ≈ 3,65 kHz; das Band bis 4 kHz wird ergänzt → mehr „Luft“ bei s, z, f |
| Kein Qt nötig, **32-Bit-ARM** (Raspberry Pi OS armhf, Tinker Board) | die 128-Bit-Multiplikation hat jetzt einen portablen Weg für alle Compiler ohne `__int128` (bitgleich geprüft) |
| `ambe2_version()` vorhanden | war im Original nur deklariert |
| **Eigener Prozess** (`n8crosslink.ambe_worker`) | stürzt der C-Code ab, startet nur der Vocoder-Prozess neu – die Bridge läuft weiter |
| **Encoder-Nachlauf** | der Encoder gibt 2 Rahmen (40 ms) verzögert aus; am Ende jedes Durchgangs werden 2 Stille-Rahmen nachgeschoben, damit nach DMR nichts abgeschnitten wird |
| Rücksetzen je Durchgang | Encoder/Decoder beginnen jede Übertragung sauber |
| Klang live einstellbar | Regler im Popup wirken sofort, ohne Neustart |

**Bauen:** Installer und Update bauen die Bibliothek mit `g++` direkt aus dem Repository (kein Download): `/opt/n8crosslink/lib/libn8vocoder.so` (root, 644). Neu gebaut wird nur, wenn sich die Quellen geändert haben (Prüfsumme in `libn8vocoder.ref`). Von Hand:

```
sudo /opt/n8crosslink/install.sh --build-vocoder
```

oder **Admin → 🎛️ Vocoder → „🔨 Vocoder bauen / aktualisieren“**. Bauzeit wenige Sekunden auf x86, einige Minuten auf einem Raspberry Pi.

Von Hand testen:
```
cd /opt/n8crosslink && sudo -u n8crosslink venv/bin/python -m n8crosslink.cli vocoder-test --mode n8vocoder
→ OK n8vocoder: 0.5 ms je Rahmen, 1 kHz -> 997 Hz N8schicht-Vocoder 1.0.0 (DroidStar fc8e340a61d6)
```

---

## 🎚️ Klang-Einstellungen (Popup)

Im Vocoder-Bereich auf der Karte **N8schicht-Vocoder** auf **„🎚️ Klang-Einstellungen“** klicken. Das Popup zeigt:

* **Grundabstimmung:** ⭐ *N8schicht* (verständlich, Standard) oder *DroidStar-Original*.
* **Regler** für jede Einstellung – mit Erklärung und den Werten beider Grundabstimmungen. Geänderte Werte sind gelb markiert. Ist der N8schicht-Vocoder aktiv, wirkt jede Änderung **sofort** im laufenden Betrieb.
* **Probehören:** einen Testsatz (Standard oder eigener Text, gesprochen mit espeak-ng) oder **eine eigene WAV-Datei** einmal durch Encoder → Decoder schicken. Du hörst **Eingang und Ausgang** nebeneinander und siehst die Messwerte: Bandbreite, Abweichung je Frequenzband (grün ≤ 3 dB, gelb ≤ 8 dB, rot darüber), Pegel und Laufzeit. Das Probehören läuft in einem eigenen Vocoder-Prozess und stört den Betrieb nicht.
* **↺ Eigene Werte löschen** setzt alles auf die gewählte Grundabstimmung zurück.

### Was jeder Regler verändert

**🔊 Decoder – DMR → FRN / Zello (was man hört)**

| Regler | DroidStar | N8schicht | Wirkung |
|---|---|---|---|
| Lautstärke (Ausgang) | 2,07 | 2,07 | Verstärkung aller Obertöne. Zu hoch = Übersteuerung (der weiche Begrenzer greift), zu niedrig = leise |
| Kompressor (Frame-Limiter) | an | **aus** | Drückt laute Rahmen zusammen (ab ≈ 78 dB Rahmenpegel, Verhältnis 0,3). **An = „komprimierter“, gepresster Klang**; aus = natürliche Dynamik. Übersteuerung verhindert weiterhin der weiche Begrenzer |
| Höhen anheben (Brillanz) | 0,50 | **0,80** | Hebt die oberen Obertöne an. Mit 0,8 bleibt der Frequenzgang bis ≈ 3,65 kHz innerhalb ±1 dB; mehr = heller/schärfer |
| Höhen ab (Anteil der Obertöne) | 0,66 | 0,66 | Ab welchem Teil der Obertöne die Anhebung beginnt |
| Klarheit (Formantverstärkung) | 0,61 | 0,61 | Betont die Formanten (Vokalklang). 0 = dumpf, viel = scharf/blechern |
| Tonhöhen-Übergang (Samples) | 160 | **120** | Interpolation der Grundfrequenz zwischen zwei Rahmen (160 Samples = 20 ms). Kürzer = die Sprachmelodie wird schneller nachgeführt → natürlicher, verständlicher |
| Lautstärke-Übergang (Samples) | 160 | 160 | Interpolation der Obertonpegel zwischen zwei Rahmen. Kürzer klingt härter (gemessen schlechter) |
| Übergang stimmhaft → stimmlos | 50 | **80** | Wie weich ein Oberton ausblendet, wenn er stimmlos wird (Vokal → „s“). Länger = weichere, natürlichere Übergänge |
| Übergang stimmlos → stimmhaft | 90 | 90 | Wie weich ein Oberton einblendet |
| Phasenstreuung | 0,30 | 0,30 | Wenig = „summend/brummig“, viel = rau |
| Zischlaute / Rauschanteil | 0,85 | 0,85 | Pegel der stimmlosen Anteile (s, f, sch, t). Höher = deutlichere Konsonanten, aber mehr Rauschen |
| Komfortrauschen bei Ausfall | 1,0 | 1,0 | Leises Rauschen statt harter Stille, wenn Rahmen wegen Funkfehlern ausfallen |
| Fehlerrahmen überbrücken | 3 | 3 | So viele kaputte Rahmen werden durch Wiederholen überbrückt, danach stumm |

**✨ Nachbearbeitung (in der Bridge)**

| Regler | DroidStar | N8schicht | Wirkung |
|---|---|---|---|
| Höhen-Ergänzung 3,65–4 kHz (dB) | aus (−40) | **0** | Füllt das Band oberhalb der AMBE-Grenze bis 4 kHz mit Rauschen, das der Hüllkurve des Bands 3,0–3,65 kHz folgt und zur Obergrenze ausblendet. Mehr „Luft“ bei Zischlauten. −40 = aus |

**🎙️ Encoder – FRN / Zello → DMR (was ins DMR geht)**

| Regler | DroidStar | N8schicht | Wirkung |
|---|---|---|---|
| Tiefen-Filter (Hz) | 135 | 135 | Entfernt Brummen/Rumpeln vor dem Kodieren. Höher = dünner, aber bei verbrummten FRN-Stationen klarer |
| Rauschsperre (dBFS) | −70 | −70 | Leisere Rahmen werden als Stille gesendet. Höher = mehr Rauschunterdrückung, aber leise Silben können verschwinden |
| Glättung (vorheriger Rahmen) | 0,05 | 0,05 | Mischt die Pegel des vorigen Rahmens bei – ruhiger, aber verwaschener |

Gespeichert wird in der Datenbank (`vocoder.n8vocoder_profile`, `vocoder.n8vocoder_options`), also auch im verschlüsselten Backup.

---

## 📏 Wie gemessen wurde

**Messlatte:** FRN liefert 8000 Hz Abtastrate. Damit ist **4000 Hz** der höchste mögliche Ton (halbe Abtastrate). Ziel: möglichst viel vom Band 0–4000 Hz erhalten und dabei verständlich bleiben.

* **Testmaterial:** 35 deutsche Sätze (Funkbetrieb, Zahlen, Zischlaute, Buchstabieren), gesprochen von 7 Stimmen (6 natürliche Diphon-Stimmen männlich/weiblich, 1 Formant-Stimme), −20 dBFS, 8 kHz.
* **Weg:** Eingang → Encoder → AMBE+2 → Decoder → Ausgang, zeitlich ausgerichtet.
* **Maße:** **ESTOI** (Verständlichkeit, 0–1), **PESQ-NB** (Sprachqualität, 1–4,5), Abweichung je Frequenzband, Bandbreite (bis wohin der Ausgang höchstens 6 dB unter dem Eingang bleibt).
* Jeder Regler wurde einzeln verändert und auf zwei getrennten Stimmgruppen geprüft; übernommen wurde nur, was auf **beiden** Gruppen besser war (kein Überanpassen an einzelne Sätze). Danach Gegenprobe mit Bitfehlern (2 % wie bei schwachem Signal).

| | DroidStar-Original | **N8schicht** |
|---|---|---|
| Verständlichkeit ESTOI (alle 35 Sätze) | 0,777 | **0,790** |
| Sprachqualität PESQ-NB | 2,78 | **2,85** |
| ESTOI mit 2 % Bitfehlern (jeder 2. Satz) | 0,751 | **0,768** |
| Frequenzgang 3,5–3,8 kHz (natürliche Stimmen) | −1,9 dB | **+1,0 dB** |
| Frequenzgang 3,8–4,0 kHz | −20,4 dB | **−2,4 dB** |
| Pegel (Eingang −20 dBFS) | −20 dBFS | −20 dBFS |

Die größten Gewinne brachten: **Kompressor aus** (genau der „komprimierte“ Klang), **schnellere Tonhöhen-Interpolation** und **weicherer Übergang stimmhaft → stimmlos**. Bei einzelnen Sätzen kann das Ergebnis anders ausfallen – deshalb gibt es das Probehören mit eigenen Aufnahmen.

**Grenze von AMBE+2:** Der Codec überträgt Obertöne nur bis ≈ 3,65–3,7 kHz. Was darüber lag, ist nach DMR nicht mehr im Signal; die Höhen-Ergänzung stellt dort einen passenden Rauschanteil her – echte Information kommt nicht zurück.

---

## 🧪 Selbst testen: Eingang gegen Ausgang

Das Werkzeug [`tools/vocoder_test.py`](../tools/vocoder_test.py) schickt WAV-Dateien durch den N8schicht-Vocoder, misst und schreibt die Ergebnisse als WAV:

```
cd /opt/n8crosslink
# mitgelieferte Testsätze (tests/audio/*.wav), N8schicht gegen DroidStar:
sudo -u n8crosslink venv/bin/python tools/vocoder_test.py --compare
# eigene Aufnahme, Ergebnisse als WAV nach /tmp/vt:
sudo -u n8crosslink venv/bin/python tools/vocoder_test.py /pfad/aufnahme.wav --compare --out /tmp/vt
# einzelne Regler ausprobieren:
sudo -u n8crosslink venv/bin/python tools/vocoder_test.py aufnahme.wav --set dec.output_gain=1.6 --set post.bwe_db=-40
```

WAV-Dateien in jedem Format (8–32 Bit, mono/stereo, jede Abtastrate) werden auf 8 kHz mono umgerechnet. Am aussagekräftigsten sind **echte Aufnahmen aus FRN** (z. B. mit dem FRN-Client mitgeschnitten). ESTOI/PESQ werden angezeigt, wenn die Python-Pakete `pystoi` und `pesq` installiert sind (`venv/bin/pip install pystoi pesq`); Bandbreite, Bänder und Pegel immer.

Automatische Tests: `tests/test_vocoder.py` (Ton 1 kHz → 997 Hz, Stille-Rahmen, Bitfehler ohne Übersteuerung, Regler live, Absturz und Neustart des Vocoder-Prozesses) und `tests/sim_e2e.py` mit `N8X_SIM_VOCODER=n8vocoder`.

---

## 🔄 Aktualisieren des Forks (für Entwickler)

`tools/update_n8vocoder.sh <commit>` holt einen neuen Stand von DroidStar, übernimmt die Codec-Dateien nach `third_party/n8schicht-vocoder/src`, spielt die N8-Änderungen wieder ein und prüft mit einem Testbau. Danach Tests laufen lassen und `VERSION` erhöhen.

---

## md380-emu (bis 1.3) wurde entfernt

Beim Update werden alte Einstellungen (md380-emu, „DroidStar“ aus 1.4/1.5) automatisch auf den N8schicht-Vocoder umgestellt; md380-emu wird deinstalliert (Dienst, Paket, `/opt/md380-emu`, sudo-Freigaben). Die DVSwitch-Paketquelle bleibt nur, wenn noch andere DVSwitch-Pakete installiert sind; `qemu-user-static` bleibt (`sudo apt purge qemu-user-static binfmt-support` zum Entfernen).

## 🔌 USB-Stick

* Der Dienstbenutzer `n8crosslink` ist in der Gruppe `dialout` – ein zusätzlicher AMBEserver ist **nicht** nötig.
* Stabilen Gerätenamen verwenden: **🔍 USB-Geräte suchen** schlägt `/dev/serial/by-id/…` vor.
* Beim Start sendet die Bridge Reset, Rate 33, Produkt-ID und Version; Gerät und Firmware erscheinen unter *Netze → Vocoder*.
* Nach einem Timeout werden offene Anfragen verworfen und der Stick neu synchronisiert.
* Der Original-Chip von DVSI klingt am natürlichsten – wer höchste Qualität will, nimmt den Stick.

## 🌐 AMBEserver

AMBE3000-Paketprotokoll über UDP. Weil es keine Sequenznummern hat, arbeitet N8 Crosslink **im Lockstep** (immer nur eine Anfrage unterwegs), öffnet nach jedem Timeout einen **neuen UDP-Socket** (verspätete Antworten können keinem falschen Rahmen zugeordnet werden) und wiederholt ein verlorenes Paket einmal. *Antwortzeit je Rahmen* (Standard 300 ms) ist einstellbar.

## 🐕 Watchdog

Antwortet der Vocoder länger als *Watchdog: neu öffnen nach* (Standard 20 s) nicht, öffnet die Bridge ihn komplett neu. Beim N8schicht-Vocoder startet zusätzlich der Vocoder-Prozess sofort neu, wenn er abstürzt oder hängt (Zähler „Neustarts“). *Netze → Vocoder* zeigt Encode, Decode, **Fehlrahmen** (Rahmen, die der Decoder wegen Bitfehlern überbrücken musste – ein Maß für die Funkqualität), Timeouts und Neustarts.

## Pegel

Unter *Vocoder* gibt es zusätzlich Pegel vor dem Kodieren und nach dem Dekodieren (dB), und pro Netz RX/TX-Pegel (FRN, DMR, Zello).
