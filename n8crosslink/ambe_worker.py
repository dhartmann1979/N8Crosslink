"""Eigener Prozess für den N8schicht-Vocoder (libn8vocoder.so, Fork des DroidStar-Codecs).

Läuft als ``python -m n8crosslink.ambe_worker <lib>`` und spricht über stdin/stdout ein
einfaches Rahmenprotokoll. Stürzt der C-Code ab, endet nur dieser Prozess – die Bridge
startet ihn neu und läuft weiter.

Anfrage/Antwort: 1 Byte Befehl, 2 Byte Länge (big endian), Nutzdaten.

  E  PCM 320 Byte (160 Samples s16le)      -> 9 Byte AMBE+2 (DMR, mit FEC)
  D  9 Byte AMBE+2                         -> 1 Byte Rahmenart + 320 Byte PCM
                                              (0 Sprache/Stille, 1 gelöscht, 3 Ton)
  R  b"e" | b"d" | b"b"                    -> leer   (Encoder/Decoder/beide neu)
  O  JSON {"enc": {...}, "dec": {...}}     -> JSON {"bad": [unbekannte Optionen]}
  V  leer                                  -> Versionstext
"""
from __future__ import annotations

import ctypes
import json
import struct
import sys


class Codec:
    def __init__(self, path: str) -> None:
        L = ctypes.CDLL(path)
        vp, cp = ctypes.c_void_p, ctypes.c_char_p
        L.ambe2_encoder_new.restype = vp
        L.ambe2_decoder_new.restype = vp
        L.ambe2_encoder_free.argtypes = [vp]
        L.ambe2_decoder_free.argtypes = [vp]
        L.ambe2_encode.argtypes = [vp, cp, cp]
        L.ambe2_pack.argtypes = [cp, cp]
        L.ambe2_decode_packed.argtypes = [vp, cp, cp]
        L.ambe2_decode_packed.restype = ctypes.c_int
        L.ambe2_encoder_set_option.argtypes = [vp, cp, ctypes.c_double]
        L.ambe2_decoder_set_option.argtypes = [vp, cp, ctypes.c_double]
        try:
            L.ambe2_version.restype = ctypes.c_char_p
            self.version = L.ambe2_version().decode()
        except AttributeError:
            self.version = "N8schicht-Vocoder"
        self.L = L
        self.opts: dict = {"enc": {}, "dec": {}}
        self.enc = self.dec = None
        self.reset("b")
        self._bits = ctypes.create_string_buffer(49)
        self._frame = ctypes.create_string_buffer(9)
        self._pcm = ctypes.create_string_buffer(320)

    def _apply(self, which: str) -> list[str]:
        bad = []
        obj = self.enc if which == "enc" else self.dec
        fn = self.L.ambe2_encoder_set_option if which == "enc" else self.L.ambe2_decoder_set_option
        for k, v in self.opts[which].items():
            if fn(obj, str(k).encode(), float(v)) != 0:
                bad.append(f"{which}.{k}")
        return bad

    def reset(self, which: str) -> None:
        if which in ("e", "b"):
            if self.enc:
                self.L.ambe2_encoder_free(self.enc)
            self.enc = self.L.ambe2_encoder_new()
            self._apply("enc")
        if which in ("d", "b"):
            if self.dec:
                self.L.ambe2_decoder_free(self.dec)
            self.dec = self.L.ambe2_decoder_new()
            self._apply("dec")

    def set_options(self, o: dict) -> list[str]:
        # Neu anlegen, damit zurückgenommene Optionen wieder auf den Grundwerten stehen
        self.opts = {"enc": dict(o.get("enc") or {}), "dec": dict(o.get("dec") or {})}   # "post" macht die Bridge
        self.reset("b")
        return self._apply("enc") + self._apply("dec")

    def encode(self, pcm: bytes) -> bytes:
        self.L.ambe2_encode(self.enc, pcm, self._bits)
        self.L.ambe2_pack(self._bits.raw, self._frame)
        return self._frame.raw

    def decode(self, ambe9: bytes) -> bytes:
        kind = self.L.ambe2_decode_packed(self.dec, ambe9, self._pcm)
        return bytes([kind & 0xFF]) + self._pcm.raw


def _read(f, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise EOFError
    return b


def main() -> int:
    c = Codec(sys.argv[1])
    rd, wr = sys.stdin.buffer, sys.stdout.buffer
    while True:
        try:
            op, n = struct.unpack(">cH", _read(rd, 3))
            data = _read(rd, n) if n else b""
        except EOFError:
            return 0
        if op == b"E":
            out = c.encode(data)
        elif op == b"D":
            out = c.decode(data)
        elif op == b"R":
            c.reset(data.decode() or "b")
            out = b""
        elif op == b"O":
            out = json.dumps({"bad": c.set_options(json.loads(data or b"{}"))}).encode()
        elif op == b"V":
            out = c.version.encode()
        else:
            out = b""
        wr.write(op + struct.pack(">H", len(out)) + out)
        wr.flush()


if __name__ == "__main__":
    sys.exit(main())
