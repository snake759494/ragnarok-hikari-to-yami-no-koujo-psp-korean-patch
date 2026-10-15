"""Scan the built Korean ISO for Japanese text that is still left.
Hangul is stored in JIS kanji codes, so a string is decoded with the patched
jis2ucs table: anything that still decodes to kana / real kanji is untranslated."""
import sys, os, re, json, struct
sys.path.insert(0, os.path.dirname(__file__))
import isobuild, cfi, strtab

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ISO = os.path.join(ROOT, 'Ragnarok - Hikari to Yami no Koujo (Korean).iso')
TOKEN = '＊＊＊＊リト＊＊＊＊'
JP = re.compile(r'[぀-ヺー-ヿ一-鿿]')


def main():
    f = open(ISO, 'rb')
    iso = isobuild.Iso.__new__(isobuild.Iso); iso.f = f
    def rd(p):
        _, _, _, lba, size = iso.find(p); f.seek(lba * 2048); return f.read(size)
    j2u = struct.unpack('<65536H', rd('/PSP_GAME/USRDIR/system/ccc/jis2ucs.bin'))

    def dec(b):
        out = []; i = 0
        while i < len(b):
            c = b[i]
            if (0x81 <= c <= 0x9f or 0xe0 <= c <= 0xfc) and i + 1 < len(b):
                s1, s2 = c, b[i + 1]
                r = (s1 - (0x70 if s1 < 0xa0 else 0xb0)) * 2 - 1
                if s2 >= 0x9f: r += 1; cc = s2 - 0x7e
                else: cc = s2 - (0x1f if s2 < 0x80 else 0x20)
                u = j2u[(r << 8 | cc) & 0xffff] if 0 < r < 128 else 0
                out.append(chr(u) if u else '�'); i += 2
            else:
                out.append(chr(c)); i += 1
        return ''.join(out)

    res = {'script': [], 'other_rtz': [], 'eboot': []}
    d = rd('/PSP_GAME/USRDIR/GAMEDATA.CFI')
    ents, p = cfi.parse(d)
    for e in ents:
        if not e[0].endswith('.rtz'): continue
        u = cfi.unz(cfi.raw(d, p, e))
        r = strtab.find_last(u)
        if r:
            for h, s in r[1]:
                t = dec(s).replace(TOKEN, '')
                if JP.search(t) and '�' not in t: res['script'].append((e[0], dec(s)))
    elf = rd('/PSP_GAME/SYSDIR/EBOOT.BIN')
    for off, jp, cap in json.load(open(os.path.join(ROOT, 'work/eboot_strings.json'), encoding='utf-8')):
        b = elf[off:elf.index(b'\0', off)]
        t = dec(b)
        if JP.search(t): res['eboot'].append((hex(off), t))
    json.dump(res, open(os.path.join(ROOT, 'work/untranslated.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    for k, v in res.items():
        print(k, len(v))
        for x in v[:40]: print('  ', x[0], repr(x[1][:60]))


main()
