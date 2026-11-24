#!/usr/bin/env python3
"""Eingang gegen Ausgang: WAV-Dateien durch den N8schicht-Vocoder schicken und messen.

Simuliert den Weg FRN/Zello → DMR → FRN/Zello (8 kHz → AMBE+2 → 8 kHz) und schreibt
die Ergebnisse als WAV. Gemessen werden Bandbreite (bis wohin der Frequenzgang
innerhalb von 6 dB bleibt), Abweichung je Frequenzband, Pegel und – wenn die Pakete
``pystoi`` und ``pesq`` installiert sind – Verständlichkeit (ESTOI) und Qualität (PESQ).

Beispiele (auf dem Server):
  cd /opt/n8crosslink
  sudo -u n8crosslink venv/bin/python tools/vocoder_test.py                     # Testsätze aus tests/audio
  sudo -u n8crosslink venv/bin/python tools/vocoder_test.py meine.wav --compare  # N8schicht gegen DroidStar
  … tools/vocoder_test.py meine.wav --set dec.output_gain=1.6 --set post.bwe_db=-40 --out /tmp/test
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from n8crosslink import preview  # noqa: E402
from n8crosslink.vocoder import PROFILES, effective_options, find_n8vocoder_lib  # noqa: E402


def parse_set(items: list[str]) -> dict:
    own: dict = {"enc": {}, "dec": {}, "post": {}}
    for it in items:
        try:
            k, v = it.split("=", 1)
            side, key = k.split(".", 1)
            own[side][key] = float(v)
        except (ValueError, KeyError):
            sys.exit(f"--set erwartet seite.name=wert (seite = enc | dec | post), nicht {it!r}")
    return own


def line(name: str, m: dict) -> str:
    q = "".join([f"  ESTOI {m['estoi']:.3f}" if "estoi" in m else "", f"  PESQ {m['pesq_nb']:.2f}" if "pesq_nb" in m else ""])
    bands = " ".join(f"{b['dev_db']:+5.1f}" for b in m.get("bands", []))
    return f"{name:28s} bis {m.get('bandwidth_hz', 0):4d} Hz  {m.get('level_in_dbfs', 0):6.1f}→{m.get('level_out_dbfs', 0):6.1f} dBFS{q}   Bänder: {bands}"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav", nargs="*", help="WAV-Dateien (Standard: tests/audio/*.wav)")
    ap.add_argument("--profile", default="n8schicht", choices=list(PROFILES))
    ap.add_argument("--set", action="append", default=[], help="eigener Wert, z. B. dec.output_gain=1.6")
    ap.add_argument("--compare", action="store_true", help="alle Profile nebeneinander")
    ap.add_argument("--out", default="", help="Ordner für die Ergebnis-WAVs (Standard: keine Ausgabe)")
    ap.add_argument("--json", action="store_true", help="Ergebnis als JSON")
    a = ap.parse_args()
    files = a.wav or sorted(glob.glob(os.path.join(os.path.dirname(HERE), "tests", "audio", "*.wav")))
    if not files:
        sys.exit("Keine WAV-Dateien gefunden")
    if not find_n8vocoder_lib():
        sys.exit("N8schicht-Vocoder nicht gebaut (sudo /opt/n8crosslink/install.sh --build-vocoder)")
    profiles = list(PROFILES) if a.compare else [a.profile]
    own = parse_set(a.set)
    print("Bänder (Abweichung zum Eingang, bezogen auf 300–1000 Hz): "
          + " ".join(f"{x}-{y}" for x, y in preview.BANDS))
    result = []
    for prof in profiles:
        opts = effective_options({"n8vocoder_profile": prof, "n8vocoder_options": own})
        print(f"\n== Profil {prof}: {json.dumps(opts, ensure_ascii=False)}")
        for f in files:
            with open(f, "rb") as fh:
                pcm = preview.wav_to_pcm8k(fh.read())
            out = await preview.process(pcm, opts)
            m = preview.metrics(pcm, out)
            result.append({"file": f, "profile": prof, **m})
            print(line(os.path.basename(f), m))
            if a.out:
                os.makedirs(a.out, exist_ok=True)
                base = os.path.splitext(os.path.basename(f))[0]
                with open(os.path.join(a.out, f"{base}.eingang.wav"), "wb") as fh:
                    fh.write(preview.to_wav(pcm))
                with open(os.path.join(a.out, f"{base}.{prof}.wav"), "wb") as fh:
                    fh.write(preview.to_wav(out))
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
