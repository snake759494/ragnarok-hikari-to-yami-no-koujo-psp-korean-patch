"""Create translation batches.
work/script_ids.json : {id: jp}           (scripts, story order, first occurrence)
work/eboot_ids.json  : {id: [jp, cap]}    (EBOOT pool, unique text, smallest slot)
work/batches/sNN.json / eNN.json : [{id, jp, spk?, maxw, maxl[, cap]}]
Width unit: full-width / Hangul = 1, ASCII = 0.5 (7px of the 14px cell)."""
import sys, os, json, struct, re
sys.path.insert(0, os.path.dirname(__file__))
import cfi, strtab

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
J = re.compile(rb'[\x81-\x9f\xe0-\xef][\x40-\xfc]')


def width(line):
    return sum(0.5 if ord(c) < 0x80 else 1 for c in line)


def limits(jp):
    lines = jp.split('\n')
    W = max(width(l) for l in lines); L = len(lines)
    if L > 1 or W >= 14:
        return min(28, max(W, 26)), max(L, 3)
    return W + 2, L


def ordered_refs(u):
    pos, tab = strtab.find_last(u)
    H = {struct.pack('<I', h): s for h, s in tab if s}
    seq = []
    for i in range(pos - 3):
        s = H.get(u[i:i + 4])
        if s is not None: seq.append(s)
    seen = set(); out = []
    for s in seq + [s for h, s in tab]:
        if s in seen: continue
        seen.add(s); out.append(s)
    return out, seq


def order_key(name):
    b = name.split('/')[-1]
    return (0 if name.startswith('script/M') else 1 if name.startswith('script/S') else
            2 if name.startswith('script/T') else 3, name)


def script_entries():
    d, ents, p = cfi.load(os.path.join(ROOT, 'work/iso/PSP_GAME/USRDIR/GAMEDATA.CFI'))
    done = set(); out = []
    for e in sorted(ents, key=lambda e: order_key(e[0])):
        if not e[0].endswith('.rtz'): continue
        u = cfi.unz(cfi.raw(d, p, e))
        if not strtab.find_last(u): continue
        order, seq = ordered_refs(u)
        # speaker hint: short string referenced right before a dialogue line
        prev = {}
        for a, b in zip(seq, seq[1:]):
            if b not in prev and J.search(a) and len(a) <= 24 and b'\n' not in a: prev[b] = a
        for s in order:
            if not J.search(s) or s in done: continue
            try: jp = s.decode('cp932')
            except UnicodeDecodeError: continue
            done.add(s)
            ent = {'file': e[0].split('/')[-1], 'jp': jp}
            sp = prev.get(s)
            if sp and sp != s and len(jp) > len(sp.decode('cp932', 'replace')):
                ent['spk'] = sp.decode('cp932', 'replace')
            out.append(ent)
    return out


def batches(entries, size, prefix):
    cur = []; n = 0; res = []
    for e in entries:
        cur.append(e); n += len(e['jp'])
        if n >= size:
            res.append(cur); cur = []; n = 0
    if cur: res.append(cur)
    os.makedirs(os.path.join(ROOT, 'work/batches'), exist_ok=True)
    for i, b in enumerate(res):
        json.dump(b, open(os.path.join(ROOT, f'work/batches/{prefix}{i:02d}.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
    return len(res)


if __name__ == '__main__':
    ents = script_entries()
    ids = {}
    for i, e in enumerate(ents):
        e['id'] = f's{i:05d}'; ids[e['id']] = e['jp']
        e['maxw'], e['maxl'] = limits(e['jp'])
    json.dump(ids, open(os.path.join(ROOT, 'work/script_ids.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    ents = [{k: e[k] for k in ('id', 'file', 'spk', 'jp', 'maxw', 'maxl') if k in e} for e in ents]
    print('script', len(ents), 'batches', batches(ents, 8000, 's'))

    ev = json.load(open(os.path.join(ROOT, 'work/eboot_strings.json'), encoding='utf-8'))
    uniq = {}
    for off, t, cap in ev:
        if not re.search(r'[぀-ヿ一-鿿]', t): continue
        uniq[t] = min(cap, uniq.get(t, cap))
    eids = {}; eents = []
    for i, (t, cap) in enumerate(uniq.items()):
        k = f'e{i:04d}'; eids[k] = [t, cap]
        lines = t.split('\n'); W = max(width(l) for l in lines)
        eents.append({'id': k, 'jp': t, 'cap': cap, 'maxw': W + (1 if W >= 8 else 2), 'maxl': len(lines)})
    json.dump(eids, open(os.path.join(ROOT, 'work/eboot_ids.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('eboot', len(eents), 'batches', batches(eents, 8000, 'e'))
