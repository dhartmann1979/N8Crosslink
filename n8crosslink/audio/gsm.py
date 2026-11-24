"""GSM 06.10 im MS-GSM/WAV49-Format über libgsm (ctypes) – so wie FRN es nutzt.

Ein FRN-Sprachpaket = 325 Byte = 5 × 65 Byte = 10 GSM-Rahmen à 20 ms
= 1600 Samples (200 ms) bei 8 kHz, 16 Bit.
"""
from __future__ import annotations

import ctypes
import ctypes.util

GSM_OPT_WAV49 = 4
FRAME_COUNT = 5          # 65-Byte-Doppelrahmen pro Paket
GSM_FRAME_SIZE = 65
PCM_PAIR = 320           # Samples pro 65-Byte-Doppelrahmen
PACKET_BYTES = FRAME_COUNT * GSM_FRAME_SIZE   # 325
PACKET_SAMPLES = FRAME_COUNT * PCM_PAIR       # 1600

_lib = None


def _load():
    global _lib
    if _lib is None:
        name = ctypes.util.find_library("gsm") or "libgsm.so.1"
        _lib = ctypes.CDLL(name)
        _lib.gsm_create.restype = ctypes.c_void_p
        _lib.gsm_destroy.argtypes = [ctypes.c_void_p]
        _lib.gsm_option.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        _lib.gsm_encode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        _lib.gsm_decode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        _lib.gsm_decode.restype = ctypes.c_int
    return _lib


class _Gsm:
    def __init__(self) -> None:
        lib = _load()
        self.h = lib.gsm_create()
        one = ctypes.c_int(1)
        lib.gsm_option(self.h, GSM_OPT_WAV49, ctypes.byref(one))

    def __del__(self) -> None:
        try:
            if self.h:
                _load().gsm_destroy(self.h)
        except Exception:  # noqa: BLE001
            pass


class GsmEncoder(_Gsm):
    def encode_packet(self, pcm: bytes) -> bytes:
        """1600 Samples (3200 Byte, s16le) -> 325 Byte."""
        assert len(pcm) == PACKET_SAMPLES * 2
        lib = _load()
        src = ctypes.create_string_buffer(pcm, len(pcm))
        out = ctypes.create_string_buffer(PACKET_BYTES)
        base_s = ctypes.addressof(src)
        base_d = ctypes.addressof(out)
        for n in range(FRAME_COUNT):
            s = base_s + n * PCM_PAIR * 2
            d = base_d + n * GSM_FRAME_SIZE
            lib.gsm_encode(self.h, s, d)
            lib.gsm_encode(self.h, s + 320, d + 32)
        return out.raw


class GsmDecoder(_Gsm):
    def decode_packet(self, data: bytes) -> bytes:
        """325 Byte -> 1600 Samples (3200 Byte, s16le)."""
        assert len(data) == PACKET_BYTES
        lib = _load()
        src = ctypes.create_string_buffer(data, len(data))
        out = ctypes.create_string_buffer(PACKET_SAMPLES * 2)
        base_s = ctypes.addressof(src)
        base_d = ctypes.addressof(out)
        for n in range(FRAME_COUNT):
            s = base_s + n * GSM_FRAME_SIZE
            d = base_d + n * PCM_PAIR * 2
            lib.gsm_decode(self.h, s, d)
            lib.gsm_decode(self.h, s + 33, d + 320)
        return out.raw
