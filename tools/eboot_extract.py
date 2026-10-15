"""Extract Japanese strings of the EBOOT string pool (plain ELF from eboot_decrypt).
Each string starts right after a NUL; its slot runs to the next 4-byte boundary
after the terminator (the pool is 4-byte aligned).  cap = usable bytes (no NUL).
writes work/eboot_strings.json: [[offset, text, cap], ...]"""
import re, json, os
ROOT = os.path.join(os.path.dirname(__file__), '..')
d = open(os.path.join(ROOT, 'work/eboot_dec.elf'), 'rb').read()
LO, HI = 0x37a000, 0x398000
JP = re.compile(r'[぀-ヿ一-鿿！-～]')
out = []
p = LO
while p < HI:
    if d[p] == 0 or d[p - 1] != 0:
        p += 1; continue
    q = d.index(b'\0', p)
    s = d[p:q]
    try:
        t = s.decode('cp932')
    except UnicodeDecodeError:
        p = q + 1; continue
    ok = len(JP.findall(t)) >= 1 and all(c >= ' ' or c == '\n' for c in t) and p % 4 == 0
    if ok and len(t) >= 1:
        # need either two+ JP chars or a clear text string
        if len(JP.findall(t)) >= 2 or (len(t) <= 2 and not re.search(r'[!-~]', t)):
            cap = ((q + 1 + 3) & ~3) - p - 1
            out.append([p, t, cap])
    p = q + 1
json.dump(out, open(os.path.join(ROOT, 'work/eboot_strings.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print(len(out), sum(len(t) for _, t, _ in out), hex(out[0][0]), hex(out[-1][0]))
