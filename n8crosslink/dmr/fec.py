"""DMR-Fehlerschutz (FEC) – Python-Port der relevanten Teile aus MMDVMHost (G4KLX).

Enthalten:
  * BPTC(196,96)          – Voice-LC-Header / Terminator
  * Reed-Solomon (12,9)   – Prüfsumme des Full-LC
  * Embedded LC (128,77)  – LC-Fragmente in den Sprach-Bursts B–E (Talker Alias)
  * Golay(20,8)           – Slot-Type
  * QR(16,7)              – EMB
  * 5-Bit-Prüfsumme       – Embedded LC

Bits werden als Listen von 0/1 behandelt (MSB zuerst), das ist bei 16,7 Bursts/s
mehr als schnell genug und bleibt nah am Original lesbar.
"""
from __future__ import annotations

from .tables import GOLAY2087, QR1676

# --------------------------------------------------------------------------
# Bit-Helfer
# --------------------------------------------------------------------------

def bytes_to_bits(data: bytes) -> list[int]:
    out: list[int] = []
    for b in data:
        for i in range(7, -1, -1):
            out.append((b >> i) & 1)
    return out


def bits_to_bytes(bits: list[int]) -> bytes:
    out = bytearray((len(bits) + 7) // 8)
    for i, bit in enumerate(bits):
        if bit:
            out[i >> 3] |= 0x80 >> (i & 7)
    return bytes(out)


# --------------------------------------------------------------------------
# Hamming-Codes (aus Hamming.cpp)
# --------------------------------------------------------------------------

def _enc15113_2(d: list[int], o: int) -> None:
    d[o + 11] = d[o + 0] ^ d[o + 1] ^ d[o + 2] ^ d[o + 3] ^ d[o + 5] ^ d[o + 7] ^ d[o + 8]
    d[o + 12] = d[o + 1] ^ d[o + 2] ^ d[o + 3] ^ d[o + 4] ^ d[o + 6] ^ d[o + 8] ^ d[o + 9]
    d[o + 13] = d[o + 2] ^ d[o + 3] ^ d[o + 4] ^ d[o + 5] ^ d[o + 7] ^ d[o + 9] ^ d[o + 10]
    d[o + 14] = d[o + 0] ^ d[o + 1] ^ d[o + 2] ^ d[o + 4] ^ d[o + 6] ^ d[o + 7] ^ d[o + 10]


def _enc1393(d: list[int]) -> None:
    d[9] = d[0] ^ d[1] ^ d[3] ^ d[5] ^ d[6]
    d[10] = d[0] ^ d[1] ^ d[2] ^ d[4] ^ d[6] ^ d[7]
    d[11] = d[0] ^ d[1] ^ d[2] ^ d[3] ^ d[5] ^ d[7] ^ d[8]
    d[12] = d[0] ^ d[2] ^ d[4] ^ d[5] ^ d[8]


def _enc16114(d: list[int], o: int) -> None:
    d[o + 11] = d[o + 0] ^ d[o + 1] ^ d[o + 2] ^ d[o + 3] ^ d[o + 5] ^ d[o + 7] ^ d[o + 8]
    d[o + 12] = d[o + 1] ^ d[o + 2] ^ d[o + 3] ^ d[o + 4] ^ d[o + 6] ^ d[o + 8] ^ d[o + 9]
    d[o + 13] = d[o + 2] ^ d[o + 3] ^ d[o + 4] ^ d[o + 5] ^ d[o + 7] ^ d[o + 9] ^ d[o + 10]
    d[o + 14] = d[o + 0] ^ d[o + 1] ^ d[o + 2] ^ d[o + 4] ^ d[o + 6] ^ d[o + 7] ^ d[o + 10]
    d[o + 15] = d[o + 0] ^ d[o + 2] ^ d[o + 5] ^ d[o + 6] ^ d[o + 8] ^ d[o + 9] ^ d[o + 10]


def _chk16114(d: list[int], o: int) -> bool:
    c = d[:]  # Kopie
    _enc16114(c, o)
    return c[o + 11:o + 16] == d[o + 11:o + 16]


# --------------------------------------------------------------------------
# Reed-Solomon (12,9) über GF(256), Polynom 0x11D (aus RS129.cpp)
# --------------------------------------------------------------------------

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]

_POLY = [64, 56, 14, 1]


def _gmult(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def rs129_parity(msg: bytes) -> list[int]:
    """Liefert parity[0..2] wie CRS129::encode (Reihenfolge beachten!)."""
    par = [0, 0, 0, 0]
    for i in range(9):
        dbyte = msg[i] ^ par[2]
        for j in range(2, 0, -1):
            par[j] = par[j - 1] ^ _gmult(_POLY[j], dbyte)
        par[0] = _gmult(_POLY[0], dbyte)
    return par


def rs129_check(data12: bytes) -> bool:
    p = rs129_parity(data12[:9])
    return data12[9] == p[2] and data12[10] == p[1] and data12[11] == p[0]


# --------------------------------------------------------------------------
# BPTC(196,96)
# --------------------------------------------------------------------------

_DATA_POS = (list(range(4, 12)) + list(range(16, 27)) + list(range(31, 42)) + list(range(46, 57))
             + list(range(61, 72)) + list(range(76, 87)) + list(range(91, 102))
             + list(range(106, 117)) + list(range(121, 132)))
assert len(_DATA_POS) == 96


def bptc19696_encode(data12: bytes, burst: bytearray) -> None:
    """Kodiert 12 Byte (LC + RS) und schreibt sie in die Info-Felder des Bursts."""
    bdata = bytes_to_bits(data12)
    deint = [0] * 196
    for pos, bit in zip(_DATA_POS, bdata):
        deint[pos] = bit
    for r in range(9):
        _enc15113_2(deint, r * 15 + 1)
    for c in range(15):
        col = [deint[c + 1 + a * 15] for a in range(13)]
        _enc1393(col)
        for a in range(13):
            deint[c + 1 + a * 15] = col[a]
    raw = [0] * 196
    for a in range(196):
        raw[(a * 181) % 196] = deint[a]
    rb = bits_to_bytes(raw[:96])
    burst[0:12] = rb
    byte = bits_to_bytes(raw[96:104])[0]
    burst[12] = (burst[12] & 0x3F) | (byte & 0xC0)
    burst[20] = (burst[20] & 0xFC) | ((byte >> 4) & 0x03)
    burst[21:33] = bits_to_bytes(raw[100:196])


def bptc19696_decode(burst: bytes) -> bytes:
    """Extrahiert 12 Byte ohne Fehlerkorrektur (Netzdaten sind fehlerfrei)."""
    raw = bytes_to_bits(burst[0:13])[:98] + bytes_to_bits(burst[20:21])[6:8] + bytes_to_bits(burst[21:33])
    deint = [raw[(a * 181) % 196] for a in range(196)]
    return bits_to_bytes([deint[p] for p in _DATA_POS])


# --------------------------------------------------------------------------
# Full LC (Header/Terminator)
# --------------------------------------------------------------------------

VOICE_LC_HEADER_MASK = (0x96, 0x96, 0x96)
TERMINATOR_MASK = (0x99, 0x99, 0x99)


def full_lc_encode(lc9: bytes, mask: tuple[int, int, int]) -> bytes:
    p = rs129_parity(lc9)
    return bytes(lc9) + bytes([p[2] ^ mask[0], p[1] ^ mask[1], p[0] ^ mask[2]])


def full_lc_decode(burst: bytes, mask: tuple[int, int, int]) -> bytes | None:
    d = bytearray(bptc19696_decode(burst))
    for i in range(3):
        d[9 + i] ^= mask[i]
    return bytes(d[:9]) if rs129_check(bytes(d)) else None


# --------------------------------------------------------------------------
# Embedded LC (aus DMREmbeddedData.cpp)
# --------------------------------------------------------------------------

def _crc5(lc_bits: list[int]) -> int:
    total = sum(bits_to_bytes(lc_bits[i:i + 8])[0] for i in range(0, 72, 8))
    return total % 31


_EMB_DATA_RANGES = [(0, 11), (16, 27), (32, 42), (48, 58), (64, 74), (80, 90), (96, 106)]


def embedded_lc_encode(lc9: bytes) -> list[list[int]]:
    """Gibt 4 Fragmente à 32 Bit zurück (für Burst B, C, D, E)."""
    m = bytes_to_bits(lc9)
    crc = _crc5(m)
    data = [0] * 128
    data[106] = crc & 1
    data[90] = (crc >> 1) & 1
    data[74] = (crc >> 2) & 1
    data[58] = (crc >> 3) & 1
    data[42] = (crc >> 4) & 1
    b = 0
    for lo, hi in _EMB_DATA_RANGES:
        for a in range(lo, hi):
            data[a] = m[b]
            b += 1
    for a in range(0, 112, 16):
        _enc16114(data, a)
    for a in range(16):
        data[a + 112] = (data[a] ^ data[a + 16] ^ data[a + 32] ^ data[a + 48]
                         ^ data[a + 64] ^ data[a + 80] ^ data[a + 96])
    raw = [0] * 128
    b = 0
    for a in range(128):
        raw[a] = data[b]
        b += 16
        if b > 127:
            b -= 127
    return [raw[i * 32:(i + 1) * 32] for i in range(4)]


def embedded_lc_decode(frags: list[list[int]]) -> bytes | None:
    raw = frags[0] + frags[1] + frags[2] + frags[3]
    data = [0] * 128
    b = 0
    for a in range(128):
        data[b] = raw[a]
        b += 16
        if b > 127:
            b -= 127
    for a in range(0, 112, 16):
        if not _chk16114(data, a):
            return None
    for a in range(16):
        if (data[a] ^ data[a + 16] ^ data[a + 32] ^ data[a + 48] ^ data[a + 64]
                ^ data[a + 80] ^ data[a + 96] ^ data[a + 112]):
            return None
    m: list[int] = []
    for lo, hi in _EMB_DATA_RANGES:
        m.extend(data[lo:hi])
    crc = (data[42] << 4) | (data[58] << 3) | (data[74] << 2) | (data[90] << 1) | data[106]
    if _crc5(m) != crc:
        return None
    return bits_to_bytes(m)


# --------------------------------------------------------------------------
# Golay(20,8) Slot-Type und QR(16,7) EMB
# --------------------------------------------------------------------------

def slot_type_apply(burst: bytearray, color_code: int, data_type: int) -> None:
    st0 = ((color_code << 4) & 0xF0) | (data_type & 0x0F)
    ck = GOLAY2087[st0]
    st1 = ck & 0xFF
    st2 = ck >> 8
    burst[12] = (burst[12] & 0xC0) | ((st0 >> 2) & 0x3F)
    burst[13] = (burst[13] & 0x0F) | ((st0 << 6) & 0xC0) | ((st1 >> 2) & 0x30)
    burst[19] = (burst[19] & 0xF0) | ((st1 >> 2) & 0x0F)
    burst[20] = (burst[20] & 0x03) | ((st1 << 6) & 0xC0) | ((st2 >> 2) & 0x3C)


def slot_type_read(burst: bytes) -> tuple[int, int]:
    b0 = ((burst[12] << 2) & 0xFC) | ((burst[13] >> 6) & 0x03)
    return (b0 >> 4) & 0x0F, b0 & 0x0F


def emb_apply(burst: bytearray, color_code: int, lcss: int, pi: bool = False) -> None:
    e0 = ((color_code << 4) & 0xF0) | (0x08 if pi else 0) | ((lcss << 1) & 0x06)
    ck = QR1676[(e0 >> 1) & 0x7F]
    e0, e1 = ck >> 8, ck & 0xFF
    burst[13] = (burst[13] & 0xF0) | ((e0 >> 4) & 0x0F)
    burst[14] = (burst[14] & 0x0F) | ((e0 << 4) & 0xF0)
    burst[18] = (burst[18] & 0xF0) | ((e1 >> 4) & 0x0F)
    burst[19] = (burst[19] & 0x0F) | ((e1 << 4) & 0xF0)


def emb_read(burst: bytes) -> tuple[int, int]:
    """(color_code, lcss) ohne Fehlerkorrektur."""
    e0 = ((burst[13] << 4) & 0xF0) | ((burst[14] >> 4) & 0x0F)
    return (e0 >> 4) & 0x0F, (e0 >> 1) & 0x03
