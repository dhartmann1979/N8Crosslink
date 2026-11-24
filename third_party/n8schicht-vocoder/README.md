# N8schicht-Vocoder

Software-AMBE+2 (half-rate, DMR) für **N8 Crosslink** – ein Fork des Codecs aus
**[DroidStar](https://github.com/nostar/DroidStar)** von Doug McLain (AD8DP).

| | |
|---|---|
| Version | siehe `VERSION` |
| Herkunft | `github.com/nostar/DroidStar`, Verzeichnis `mbe/`, Commit in `UPSTREAM_COMMIT` |
| Lizenz | **GPL-3.0-or-later** (siehe `LICENSE`); die von mbelib stammenden Teile tragen zusätzlich ihre ISC-Hinweise |
| Schnittstelle | C-API `src/ambe2.h` (`ambe2_encode`, `ambe2_pack`, `ambe2_decode_packed`, `ambe2_*_set_option`, `ambe2_version`) |
| Bauen | `./build.sh <ziel>/libn8vocoder.so` (g++ ≥ 8, C++17, kein Qt) |

## Übernommene Dateien

Alle `*.cc`/`*.h` aus `mbe/` außer `mbevocoder.*` und `vocoder_tables.h` (die gehören zur
DroidStar-App, brauchen IMBE/Qt und werden für AMBE+2 half-rate nicht benötigt).

## Änderungen gegenüber DroidStar

1. `src/decoder_synth.cc`: `#include <QtGlobal>` entfernt; die portable 64×64→128-Bit-
   Multiplikation wird jetzt für **alle** Compiler ohne `__int128` benutzt (bisher nur
   Android-ARMv7 über Qt-Makros). Damit baut der Codec auch auf 32-Bit-ARM (Raspberry Pi
   OS armhf, Tinker Board). Bitgleichheit mit dem `__int128`-Weg geprüft
   (10 Mio. Zufallswerte + Grenzfälle; komplette Encode/Decode-Ausgabe identisch).
2. `src/ambe2.cc`: `ambe2_version()` definiert (im Original nur deklariert); Text kommt aus
   `N8X_AMBE2_VERSION` (setzt `build.sh`).

Die Klang-Abstimmung „N8schicht“ ändert **keinen** Code – sie setzt Optionen über
`ambe2_decoder_set_option()` (siehe `n8crosslink/vocoder.py`, `PROFILES`). Die
Höhen-Ergänzung 3,65–4 kHz läuft in der Bridge (`n8crosslink/audio/dsp.py`,
`BandwidthExtender`). Beschreibung und Messwerte: [`docs/VOCODER.md`](../../docs/VOCODER.md).

## Aktualisieren

`tools/update_n8vocoder.sh <commit>` holt einen neuen DroidStar-Stand, kopiert die Dateien,
spielt die Änderungen 1–2 wieder ein und baut zur Probe.
