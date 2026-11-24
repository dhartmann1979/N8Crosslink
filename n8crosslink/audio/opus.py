"""Schlanker Opus-Wrapper (ctypes auf libopus) für Zello."""
from __future__ import annotations

import ctypes
import ctypes.util

OPUS_APPLICATION_VOIP = 2048
OPUS_SET_BITRATE = 4002

_lib = None


def _load():
    global _lib
    if _lib is None:
        _lib = ctypes.CDLL(ctypes.util.find_library("opus") or "libopus.so.0")
        _lib.opus_encoder_create.restype = ctypes.c_void_p
        _lib.opus_encoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        _lib.opus_encode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        _lib.opus_encode.restype = ctypes.c_int
        _lib.opus_decoder_create.restype = ctypes.c_void_p
        _lib.opus_decoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        _lib.opus_decode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        _lib.opus_decode.restype = ctypes.c_int
        _lib.opus_encoder_destroy.argtypes = [ctypes.c_void_p]
        _lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
    return _lib


class OpusEncoder:
    def __init__(self, rate: int = 16000, bitrate: int = 16000) -> None:
        lib = _load()
        err = ctypes.c_int(0)
        self.rate = rate
        self.h = lib.opus_encoder_create(rate, 1, OPUS_APPLICATION_VOIP, ctypes.byref(err))
        if err.value != 0 or not self.h:
            raise RuntimeError(f"opus_encoder_create Fehler {err.value}")
        lib.opus_encoder_ctl(ctypes.c_void_p(self.h), ctypes.c_int(OPUS_SET_BITRATE), ctypes.c_int(bitrate))

    def encode(self, pcm: bytes) -> bytes:
        samples = len(pcm) // 2
        out = ctypes.create_string_buffer(1500)
        src = ctypes.create_string_buffer(pcm, len(pcm))
        n = _load().opus_encode(self.h, src, samples, out, 1500)
        if n < 0:
            raise RuntimeError(f"opus_encode Fehler {n}")
        return out.raw[:n]

    def __del__(self) -> None:
        try:
            _load().opus_encoder_destroy(self.h)
        except Exception:  # noqa: BLE001
            pass


class OpusDecoder:
    def __init__(self, rate: int = 8000) -> None:
        lib = _load()
        err = ctypes.c_int(0)
        self.rate = rate
        self.h = lib.opus_decoder_create(rate, 1, ctypes.byref(err))
        if err.value != 0 or not self.h:
            raise RuntimeError(f"opus_decoder_create Fehler {err.value}")

    def decode(self, data: bytes) -> bytes:
        max_samples = self.rate * 120 // 1000
        out = ctypes.create_string_buffer(max_samples * 2)
        src = ctypes.create_string_buffer(data, len(data))
        n = _load().opus_decode(self.h, src, len(data), out, max_samples, 0)
        if n < 0:
            return b""
        return out.raw[:n * 2]

    def __del__(self) -> None:
        try:
            _load().opus_decoder_destroy(self.h)
        except Exception:  # noqa: BLE001
            pass
