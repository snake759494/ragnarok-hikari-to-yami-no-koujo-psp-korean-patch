"""Add Hangul glyphs to the game's own PGF fonts (USRDIR/system/fonts).

JPN7pt.PGF : main text font, 14px cell (advance 896/64), kanji 14x14 with top 12
JPN12.PGF  : 12px cell, kana only, kana 11x11 with top 10
Hangul is rendered from NanumSquareNeo Regular (bRg) at the cell size, the closest
match to the original thin FOT-NewRodin bitmaps in stroke weight and crispness.
All original glyphs are kept; the charmap/charptr bit widths grow as needed.
"""
import sys, os, struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(__file__))
from merge_pgf_fonts import PGF, GlyphRecord, encode_glyph, write_bit_table

ROOT = Path(__file__).resolve().parent.parent
TTF = ROOT / 'NanumSquareNeo-bRg.ttf'
FIXED = 64


def render(cps, px, ref_top, ref_h, size=None, ttf=TTF):
    """ref_top/ref_h: top bearing and height of a full-width kanji in the font"""
    size = size or px
    face = ImageFont.truetype(str(ttf), size)
    ascent, _ = face.getmetrics()
    raw = {}
    for cp in cps:
        cv = Image.new('L', (size * 3, size * 3), 0)
        ImageDraw.Draw(cv).text((size, size - ascent), chr(cp), font=face, fill=255)
        bb = cv.getbbox()
        if bb is None: continue
        crop = cv.crop(bb)
        raw[cp] = (crop.width, crop.height, size - bb[1],
                   [min(15, (v * 15 + 127) // 255) for v in crop.getdata()])
    # vertical: centre the block of "한" on the kanji centre
    _, h, t, _ = raw[0xD55C]
    centre = ref_top - ref_h / 2
    lift = round(centre + h / 2) - t
    out = {}
    for cp, (w, h, t, pix) in raw.items():
        t += lift
        l = (px - w) // 2
        out[cp] = GlyphRecord(0, w, h, l, t, 0, (w * FIXED, h * FIXED), (l * FIXED, 0),
                              (t * FIXED, 0), (px * FIXED, px * FIXED), tuple(pix))
    return out


def build(src_path, dst_path, cps, px, ref_char, size=None, ttf=TTF):
    src = PGF(Path(src_path))
    n = len(src.charptr)
    ref = src.glyph(src.glyph_index(ord(ref_char)))
    hg = render(cps, px, ref.top, ref.height, size, ttf)
    scale = src.charptr_scale
    old_data = bytearray(src.data[src.glyph_data_offset:])
    charptr = list(src.charptr)
    total = len(charptr) + len(hg)
    cm_bpe = max(src.charmap_bpe, (total + 1).bit_length())
    none = (1 << cm_bpe) - 1
    old_none = (1 << src.charmap_bpe) - 1
    # remap the "missing" marker first: a new index may equal the old marker
    charmap = [none if v == old_none else v for v in src.charmap]
    for cp in sorted(hg):
        rec = encode_glyph(hg[cp])
        assert len(rec) % scale == 0
        pos = cp - src.charmap_min
        assert charmap[pos] >= n, hex(cp)
        charmap[pos] = len(charptr)
        charptr.append(len(old_data) // scale)
        old_data += rec
    assert len(charptr) < none
    cp_bpe = max(src.charptr_bpe, max(charptr).bit_length())
    header = bytearray(src.data[:src.header_size])
    struct.pack_into('<iiii', header, 0x10, len(charmap), len(charptr), cm_bpe, cp_bpe)
    out = bytes(header) + src.data[src.header_size:src.charmap_offset]
    out += write_bit_table(charmap, cm_bpe) + write_bit_table(charptr, cp_bpe) + bytes(old_data)
    Path(dst_path).write_bytes(out)
    # verify by reading back
    chk = PGF(Path(dst_path))
    g = chk.glyph(chk.glyph_index(0xD55C))
    assert g.width and chk.glyph_index(ord(ref_char)) is not None
    print(f'{Path(dst_path).name}: {n} + {len(hg)} glyphs, bpe {cm_bpe}/{cp_bpe}, {len(out)} bytes')


def build_all(cps, outdir):
    fonts = ROOT / 'work/iso/PSP_GAME/USRDIR/system/fonts'
    os.makedirs(outdir, exist_ok=True)
    cps = sorted(set(cps) | {0xD55C})
    # main text: NanumSquareNeo Bold 15px in the 14px cell (fills the cell, tighter look)
    build(fonts / 'JPN7pt.PGF', Path(outdir) / 'JPN7pt.PGF', cps, 14, '国', 15, ROOT / 'NanumSquareNeo-cBd.ttf')
    build(fonts / 'JPN12.PGF', Path(outdir) / 'JPN12.PGF', cps, 12, 'ア')


if __name__ == '__main__':
    txt = Path(sys.argv[1]).read_text(encoding='utf-8')
    build_all([ord(c) for c in txt if 0xAC00 <= ord(c) <= 0xD7A3], sys.argv[2])
