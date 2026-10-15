"""Build the Korean ISO.  usage: python tools/build.py [out.iso]"""
import sys, os, json, glob, shutil, struct
sys.path.insert(0, os.path.dirname(__file__))
import cfi, strtab, kcode, build_font, isobuild, tex_patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC_ISO = os.path.join(ROOT, 'Ragnarok - Hikari to Yami no Koujo (Japan).iso')
OUT_ISO = os.path.join(ROOT, 'Ragnarok - Hikari to Yami no Koujo (Korean).iso')
USR = os.path.join(ROOT, 'work/iso/PSP_GAME/USRDIR')
TMP = os.path.join(ROOT, 'work/build')


def load_tr(pattern, idfile):
    """translation/<batch>.json {id: ko} -> {jp: ko}"""
    ids = json.load(open(os.path.join(ROOT, 'work', idfile), encoding='utf-8'))
    tr = {}
    for fn in sorted(glob.glob(os.path.join(ROOT, 'translation', pattern))):
        for k, v in json.load(open(fn, encoding='utf-8')).items():
            jp = ids[k][0] if isinstance(ids[k], list) else ids[k]
            if v: tr[jp] = v
    return tr


def main(out_iso):
    os.makedirs(TMP, exist_ok=True)
    import eboot_text
    tr = load_tr('s[0-9]*.json', 'script_ids.json')
    etr = load_tr('e[0-9]*.json', 'eboot_ids.json')
    korean = ''.join(tr.values()) + ''.join(etr.values())
    kcode.make_map([c for c in korean if '가' <= c <= '힣'])
    print('hangul syllables', len(kcode.load()))

    # scripts
    d, ents, p = cfi.load(os.path.join(USR, 'GAMEDATA.CFI'))
    repl = {}; nrep = 0
    for e in ents:
        if not e[0].endswith('.rtz'): continue
        u = cfi.unz(cfi.raw(d, p, e))
        r = strtab.find_last(u)
        if not r: continue
        pos, tab = r; new = []; ch = False
        for h, s in tab:
            try: js = s.decode('cp932')
            except UnicodeDecodeError: js = None
            if js in tr:
                s = kcode.encode(tr[js]); ch = True; nrep += 1
            new.append((h, s))
        if ch: repl[e[0]] = strtab.build(u, pos, new)
    print('scripts', len(repl), 'files', nrep, 'strings')
    byname = {e[0]: e for e in ents}
    tex = tex_patch.patched_files(lambda n: repl.get(n) or cfi.unz(cfi.raw(d, p, byname[n])))
    repl.update(tex)
    print('textures', len(tex), 'files')
    cfi_new = cfi.rebuild(d, ents, p, repl)

    # fonts + conversion tables
    build_font.build_all([ord(c) for c in kcode.load()], os.path.join(TMP, 'fonts'))
    j2u, u2j = kcode.tables(os.path.join(USR, 'system/ccc'))

    # eboot (plain ELF)
    elf = eboot_text.patch(bytearray(open(os.path.join(ROOT, 'work/eboot_dec.elf'), 'rb').read()), etr)

    iso = isobuild.Iso(SRC_ISO, out_iso)
    for path, data in [
        ('/PSP_GAME/USRDIR/GAMEDATA.CFI', cfi_new),
        ('/PSP_GAME/USRDIR/system/fonts/JPN7pt.PGF', open(os.path.join(TMP, 'fonts/JPN7pt.PGF'), 'rb').read()),
        ('/PSP_GAME/USRDIR/system/fonts/JPN12.PGF', open(os.path.join(TMP, 'fonts/JPN12.PGF'), 'rb').read()),
        ('/PSP_GAME/USRDIR/system/ccc/jis2ucs.bin', j2u),
        ('/PSP_GAME/USRDIR/system/ccc/ucs2jis.bin', u2j),
        ('/PSP_GAME/SYSDIR/EBOOT.BIN', bytes(elf)),
        ('/PSP_GAME/PARAM.SFO', eboot_text.patch_sfo(open(os.path.join(ROOT, 'work/iso/PSP_GAME/PARAM.SFO'), 'rb').read(), '라그나로크 ～빛과 어둠의 황녀～')),
    ]:
        print(path, iso.replace(path, data))
    iso.close()
    shutil.rmtree(TMP)
    print('done', out_iso, os.path.getsize(out_iso))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else OUT_ISO)
