"""Collect Japanese strings from every compiled script (.rtz) in GAMEDATA.CFI.
writes work/script_strings.json: {text: [file, ...]} ordered by first appearance."""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(__file__))
import cfi, strtab

J = re.compile(rb'[\x81-\x9f\xe0-\xef][\x40-\xfc]')
ROOT = os.path.join(os.path.dirname(__file__), '..')


def jp_strings(data):
    r = strtab.find_last(data)
    if not r: return None, []
    out = []
    for h, s in r[1]:
        if not J.search(s): continue
        try: out.append((h, s.decode('cp932')))
        except UnicodeDecodeError: pass
    return r, out


def order_key(name):
    # story order: M (main) chapters, then side stories, then the rest
    b = name.split('/')[-1]
    return (0 if b.startswith('M') else 1 if b[0] in 'STR' else 2, name)


if __name__ == '__main__':
    d, ents, p = cfi.load(os.path.join(ROOT, 'work/iso/PSP_GAME/USRDIR/GAMEDATA.CFI'))
    res = {}
    files = {}
    for e in sorted(ents, key=lambda e: order_key(e[0])):
        if not e[0].endswith('.rtz'): continue
        u = cfi.unz(cfi.raw(d, p, e))
        r, js = jp_strings(u)
        if not js: continue
        files[e[0]] = len(js)
        for h, s in js:
            res.setdefault(s, []).append(e[0])
    json.dump(res, open(os.path.join(ROOT, 'work/script_strings.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(len(files), 'files', len(res), 'unique', sum(len(s) for s in res), 'chars')
