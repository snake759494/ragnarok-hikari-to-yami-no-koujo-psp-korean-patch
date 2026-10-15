"""Korean text encoding for the game's Shift-JIS strings.

The game converts SJIS -> JIS -> Unicode with USRDIR/system/ccc/jis2ucs.bin and
draws Unicode glyphs from its own PGF fonts.  Hangul syllables are given JIS
kanji codes (row 0x30 onward, in the order of work/hangul_map.json) and
jis2ucs/ucs2jis are rewritten so those codes map to the real Hangul code points;
the fonts get real Hangul glyphs.  Kana, ASCII and symbols keep their codes."""
import json, struct, os
ROOT = os.path.join(os.path.dirname(__file__), '..')
MAP = os.path.join(ROOT, 'work', 'hangul_map.json')
FIRST_ROW = 0x30


def jis_slots():
    for row in range(FIRST_ROW, 0x75):
        for col in range(0x21, 0x7F):
            yield row << 8 | col


def jis2sjis(j):
    r, c = j >> 8, j & 0xFF
    s1 = (r + 1) // 2 + (0x70 if r <= 0x5E else 0xB0)
    if r & 1: s2 = c + (0x1F if c <= 0x5F else 0x20)
    else: s2 = c + 0x7E
    return bytes([s1, s2])


def make_map(syllables):
    syl = sorted(set(syllables))
    m = {}
    for ch, j in zip(syl, jis_slots()): m[ch] = j
    assert len(m) == len(syl), 'too many syllables'
    json.dump({ch: j for ch, j in m.items()}, open(MAP, 'w', encoding='utf-8'), ensure_ascii=False)
    return m


_m = None


def load():
    global _m
    if _m is None: _m = {k: v for k, v in json.load(open(MAP, encoding='utf-8')).items()}
    return _m


def encode(text):
    m = load(); out = bytearray()
    for ch in text:
        if '가' <= ch <= '힣': out += jis2sjis(m[ch])
        else: out += ch.encode('cp932')
    return bytes(out)


def tables(src_dir):
    """patched jis2ucs.bin / ucs2jis.bin contents"""
    m = load()
    j2u = list(struct.unpack('<65536H', open(os.path.join(src_dir, 'jis2ucs.bin'), 'rb').read()))
    u2j = list(struct.unpack('<65536H', open(os.path.join(src_dir, 'ucs2jis.bin'), 'rb').read()))
    for ch, j in m.items():
        old = j2u[j]
        if old and u2j[old] == j: u2j[old] = 0
        j2u[j] = ord(ch); u2j[ord(ch)] = j
    return struct.pack('<65536H', *j2u), struct.pack('<65536H', *u2j)
