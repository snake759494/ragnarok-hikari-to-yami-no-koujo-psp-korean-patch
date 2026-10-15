"""Check a translated batch.  usage: python -I tools/check_batch.py s00 [s01 ...]
Reports: missing ids, line width/count, EBOOT byte cap, characters the game font
cannot show, changed name token / format specifiers, leftover Japanese."""
import sys, os, json, re, struct
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TOKEN = '＊＊＊＊リト＊＊＊＊'


def font_chars():
    cache = os.path.join(ROOT, 'work', 'font_chars.json')
    if os.path.exists(cache):
        return set(json.load(open(cache, encoding='utf-8')))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from merge_pgf_fonts import PGF
    from pathlib import Path
    f = PGF(Path(ROOT) / 'work/iso/PSP_GAME/USRDIR/system/fonts/JPN7pt.PGF')
    have = {f.charmap_min + i for i, v in enumerate(f.charmap) if v < len(f.charptr)}
    j2u = struct.unpack('<65536H', open(os.path.join(ROOT, 'work/iso/PSP_GAME/USRDIR/system/ccc/jis2ucs.bin'), 'rb').read())
    ok = set()
    for cp in range(0x20, 0x10000):
        ch = chr(cp)
        try: b = ch.encode('cp932')
        except UnicodeEncodeError: continue
        if len(b) == 1:
            if cp in have: ok.add(ch)
            continue
        s1, s2 = b
        # sjis -> jis
        r = (s1 - (0x70 if s1 < 0xa0 else 0xb0)) * 2 - 1
        if s2 >= 0x9f: r += 1; c = s2 - 0x7e
        else: c = s2 - (0x1f if s2 < 0x80 else 0x20)
        u = j2u[(r << 8) | c]
        if u in have: ok.add(ch)
    json.dump(sorted(ok), open(cache, 'w', encoding='utf-8'), ensure_ascii=False)
    return ok


def width(line):
    return sum(0.5 if ord(c) < 0x80 else 1 for c in line)


def nbytes(t):
    return sum(2 if '가' <= c <= '힣' else len(c.encode('cp932')) for c in t)


FMT = re.compile(r'%[0-9]*[sdxc]|@[a-z]')
JP = re.compile(r'[぀-ヺー-ヿ一-鿿]')  # '・' allowed


def check(name):
    src = json.load(open(os.path.join(ROOT, 'work/batches', name + '.json'), encoding='utf-8'))
    path = os.path.join(ROOT, 'translation', name + '.json')
    if not os.path.exists(path):
        return [f'{name}: translation/{name}.json 없음']
    tr = json.load(open(path, encoding='utf-8'))
    ok = font_chars()
    errs = []
    for e in src:
        i = e['id']; jp = e['jp']; ko = tr.get(i)
        if not ko:
            errs.append(f'{i}: 번역 없음'); continue
        lines = ko.split('\n')
        if len(lines) > e['maxl']: errs.append(f'{i}: 줄 수 {len(lines)} > {e["maxl"]}')
        for l in lines:
            if width(l) > e['maxw']: errs.append(f'{i}: 줄 폭 {width(l)} > {e["maxw"]}: {l}')
        if 'cap' in e and nbytes(ko) > e['cap']: errs.append(f'{i}: {nbytes(ko)}바이트 > cap {e["cap"]}')
        if jp.count(TOKEN) != ko.count(TOKEN): errs.append(f'{i}: 이름 토큰 개수 다름')
        if sorted(FMT.findall(jp)) != sorted(FMT.findall(ko)): errs.append(f'{i}: 서식 문자열 다름 {FMT.findall(jp)}')
        rest = FMT.sub('', ko.replace(TOKEN, ''))
        bad = sorted({c for c in rest if c != '\n' and not ('가' <= c <= '힣') and c not in ok})
        if bad: errs.append(f'{i}: 표시 불가 문자 {bad}')
        if JP.search(rest):
            errs.append(f'{i}: 일본어 문자 남음: {"".join(JP.findall(rest))}')
        if '  ' in ko or ko != ko.strip(' '): errs.append(f'{i}: 공백 이상')
    extra = set(tr) - {e['id'] for e in src}
    if extra: errs.append(f'모르는 id {sorted(extra)[:5]}')
    return errs


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    tot = 0
    for n in sys.argv[1:]:
        es = check(n); tot += len(es)
        for x in es: print(x)
        print(f'{n}: 오류 {len(es)}건')
    sys.exit(1 if tot else 0)
