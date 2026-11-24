"""DMR-Bursts (33 Byte Nutzlast) bauen und zerlegen, inkl. Talker Alias."""
from __future__ import annotations

from . import fec

# Sync-Muster (7 Byte, um 4 Bit versetzt – wie in MMDVMHost DMRDefines.h)
BS_AUDIO_SYNC = bytes([0x07, 0x55, 0xFD, 0x7D, 0xF7, 0x5F, 0x70])
BS_DATA_SYNC = bytes([0x0D, 0xFF, 0x57, 0xD7, 0x5D, 0xF5, 0xD0])
SYNC_MASK = bytes([0x0F, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xF0])

DT_VOICE_LC_HEADER = 0x01
DT_TERMINATOR_WITH_LC = 0x02

# Stille-Frame AMBE+2 (72 Bit) aus MMDVMHost
AMBE_SILENCE = bytes.fromhex("B9E881526173002A6B")

FLCO_GROUP = 0x00
FLCO_UNIT = 0x03
FLCO_TA_HEADER = 0x04  # 0x04..0x07 = Header, Block 1..3


def _apply_sync(burst: bytearray, sync: bytes) -> None:
    for i in range(7):
        burst[13 + i] = (burst[13 + i] & ~SYNC_MASK[i] & 0xFF) | sync[i]


def make_lc(src: int, dst: int, group: bool = True) -> bytes:
    return bytes([FLCO_GROUP if group else FLCO_UNIT, 0x00, 0x00,
                  (dst >> 16) & 0xFF, (dst >> 8) & 0xFF, dst & 0xFF,
                  (src >> 16) & 0xFF, (src >> 8) & 0xFF, src & 0xFF])


def build_lc_burst(lc9: bytes, color_code: int, terminator: bool) -> bytes:
    burst = bytearray(33)
    mask = fec.TERMINATOR_MASK if terminator else fec.VOICE_LC_HEADER_MASK
    fec.bptc19696_encode(fec.full_lc_encode(lc9, mask), burst)
    fec.slot_type_apply(burst, color_code, DT_TERMINATOR_WITH_LC if terminator else DT_VOICE_LC_HEADER)
    _apply_sync(burst, BS_DATA_SYNC)
    return bytes(burst)


def build_voice_burst(ambe: tuple[bytes, bytes, bytes], n: int, color_code: int,
                      emb_frag: list[int] | None) -> bytes:
    """n = 0..5 (A..F). Für B..E wird ein 32-Bit-Fragment des Embedded LC eingesetzt."""
    a1 = fec.bytes_to_bits(ambe[0])
    a2 = fec.bytes_to_bits(ambe[1])
    a3 = fec.bytes_to_bits(ambe[2])
    bits = a1 + a2[:36] + [0] * 48 + a2[36:] + a3
    burst = bytearray(fec.bits_to_bytes(bits))
    if n == 0:
        _apply_sync(burst, BS_AUDIO_SYNC)
        return bytes(burst)
    if 1 <= n <= 4 and emb_frag is not None:
        lcss = {1: 1, 2: 3, 3: 3, 4: 2}[n]
        frag = fec.bits_to_bytes([0, 0, 0, 0] + emb_frag + [0, 0, 0, 0])  # 40 Bit
        burst[14] = (burst[14] & 0xF0) | (frag[0] & 0x0F)
        burst[15] = frag[1]
        burst[16] = frag[2]
        burst[17] = frag[3]
        burst[18] = (burst[18] & 0x0F) | (frag[4] & 0xF0)
    else:
        lcss = 0
        burst[14] &= 0xF0
        burst[15] = burst[16] = burst[17] = 0
        burst[18] &= 0x0F
    fec.emb_apply(burst, color_code, lcss)
    return bytes(burst)


def extract_ambe(burst: bytes) -> tuple[bytes, bytes, bytes]:
    bits = fec.bytes_to_bits(burst)
    return (fec.bits_to_bytes(bits[0:72]),
            fec.bits_to_bytes(bits[72:108] + bits[156:192]),
            fec.bits_to_bytes(bits[192:264]))


def extract_emb_fragment(burst: bytes) -> list[int]:
    return fec.bytes_to_bits(burst)[116:148]


# --------------------------------------------------------------------------
# Talker Alias (ETSI TS 102 361-2, 7.2.18) – Port von CDMRTA
# --------------------------------------------------------------------------

def _to_latin1(text: str) -> str:
    out = []
    for ch in text:
        o = ord(ch)
        if 0x20 <= o < 0x7F or 0xA0 <= o <= 0xFF:
            out.append(ch)
        else:
            # Umlaute & Co. sind Latin-1, alles andere ersetzen
            out.append("?")
    return "".join(out)


def talker_alias_blocks(text: str) -> list[bytes]:
    """Liefert 1..4 Embedded-LC (9 Byte) mit FLCO 0x04..0x07."""
    text = _to_latin1(text.strip())
    seven = all(ord(c) < 0x80 for c in text)
    maxlen = 31 if seven else 27
    text = text[:maxlen]
    if not text:
        return []
    blocks = bytearray(28)
    pos = 0

    def put(value: int, count: int) -> None:
        nonlocal pos
        while count > 0:
            count -= 1
            if (value >> count) & 1:
                blocks[pos // 8] |= 0x80 >> (pos % 8)
            pos += 1

    put(0 if seven else 1, 2)
    put(len(text), 5)
    if not seven:
        pos = 8
    for ch in text:
        put(ord(ch), 7 if seven else 8)
    count = (pos + 55) // 56
    out = []
    for i in range(count):
        out.append(bytes([FLCO_TA_HEADER + i, 0x00]) + bytes(blocks[i * 7:(i + 1) * 7]))
    return out


class TalkerAliasDecoder:
    def __init__(self) -> None:
        self.buf = bytearray(32)
        self.seen: set[int] = set()

    def reset(self) -> None:
        self.buf = bytearray(32)
        self.seen.clear()

    def add_lc(self, lc9: bytes) -> str | None:
        flco = lc9[0] & 0x3F
        if not 4 <= flco <= 7:
            return None
        block = flco - 4
        self.buf[block * 7:block * 7 + 7] = lc9[2:9]
        self.seen.add(block)
        return self.decode()

    def decode(self) -> str | None:
        fmt = (self.buf[0] >> 6) & 0x03
        size = (self.buf[0] >> 1) & 0x1F
        if size == 0:
            return None
        if fmt == 0:
            chars = []
            t1 = 0
            c = 0
            for i in range(32):
                for j in range(7, -1, -1):
                    c = (c << 1) | ((self.buf[i] >> j) & 1)
                    t1 += 1
                    if t1 == 7:
                        if i > 0:
                            chars.append(chr(c & 0x7F))
                        t1 = 0
                        c = 0
                    if len(chars) >= size:
                        break
                if len(chars) >= size:
                    break
            # Nur vollständig, wenn alle benötigten Blöcke da sind
            needed = (7 + size * 7 + 55) // 56
            text = "".join(chars).replace("\x00", "").strip()
            return text if len(self.seen) >= needed else (text + "…" if text else None)
        if fmt in (1, 2):
            raw = bytes(self.buf[1:1 + size])
            try:
                text = raw.decode("utf-8" if fmt == 2 else "latin-1", errors="replace")
            except Exception:
                return None
            return text.replace("\x00", "").strip() or None
        return None
