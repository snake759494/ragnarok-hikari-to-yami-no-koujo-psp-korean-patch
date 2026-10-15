"""EBOOT patches: install-data path and translated data strings."""
import os, json, glob
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INSTALL = b'ms0:PSP/SAVEDATA/NPJH50431DAT/GAMEDATA.CFI'


def patch(elf, tr):
    # the installed copy of GAMEDATA.CFI (PGD encrypted, from INSDIR) would be
    # read instead of the disc one; point the game at a file that never exists
    i = elf.find(INSTALL); assert i > 0
    elf[i:i + len(INSTALL)] = INSTALL.replace(b'GAMEDATA.CFI', b'GAMEDATK.CFI')
    apply_utf8(elf)
    n, over = apply_strings(elf, tr)
    print('eboot strings', n, 'too long', len(over))
    for o in over[:20]: print('  OVER', o)
    return elf


def apply_strings(elf, tr):
    import kcode
    ents = json.load(open(os.path.join(ROOT, 'work/eboot_strings.json'), encoding='utf-8'))
    n = 0; over = []
    for off, text, cap in ents:
        if text not in tr: continue
        b = kcode.encode(tr[text])
        if len(b) > cap:
            over.append((text, tr[text], len(b), cap)); continue
        elf[off:off + cap + 1] = b + b'\0' * (cap + 1 - len(b)); n += 1
    return n, over


def apply_utf8(elf):
    """UTF-8 strings (save/install/message dialogs): same slot, NUL padded"""
    tab = json.load(open(os.path.join(ROOT, 'translation/eboot_utf8.json'), encoding='utf-8'))
    n = 0
    for k, v in tab.items():
        if k.startswith('_'): continue
        off = int(k, 16); jp, ko = v
        old = jp.encode('utf-8'); new = ko.encode('utf-8')
        assert elf[off:off + len(old)] == old and elf[off + len(old)] == 0, k
        cap = len(old)
        while elf[off + cap + 1] == 0 and (off + cap + 1) % 4: cap += 1
        assert len(new) <= cap, (k, len(new), cap)
        elf[off:off + cap + 1] = new + b'\0' * (cap + 1 - len(new)); n += 1
    print('eboot utf8 strings', n)


def patch_sfo(sfo, title):
    import struct
    sfo = bytearray(sfo)
    kt, dt, n = struct.unpack_from('<III', sfo, 8)
    for i in range(n):
        ko, fmt, ln, mx, do = struct.unpack_from('<HHIII', sfo, 20 + i * 16)
        if sfo[kt + ko:sfo.index(b'\0', kt + ko)] == b'TITLE':
            b = title.encode('utf-8') + b'\0'
            assert len(b) <= mx
            sfo[dt + do:dt + do + mx] = b + b'\0' * (mx - len(b))
            struct.pack_into('<I', sfo, 20 + i * 16 + 4, len(b))
    return bytes(sfo)
