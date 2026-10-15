"""Decode every GIM (standalone .giz or embedded in .gmz) to work/tex/<path>__<n>.png
and write contact sheets work/tex_sheets/NN.png with labels."""
import sys, os, glob, re
sys.path.insert(0, os.path.dirname(__file__))
import gimpng
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'work/cfi')
OUT = os.path.join(ROOT, 'work/tex')
MAG = b'MIG.00.1PSP\0'
SKIP = ('btlmap/radar/', 'bs/bs_bg', 'chr/', 'skill/', 'btlmap/bm/', 'event/ch/', 'event/bg/', 'bs_eff/', 'effect/', 'sound/')


def gims(d):
    i = d.find(MAG)
    while i >= 0:
        yield i
        i = d.find(MAG, i + 1)


def main():
    os.makedirs(OUT, exist_ok=True)
    items = []
    for fn in sorted(glob.glob(SRC + '/**/*', recursive=True)):
        rel = os.path.relpath(fn, SRC).replace(os.sep, '/')
        if not os.path.isfile(fn) or rel.startswith(SKIP): continue
        if not re.search(r'\.(giz|gmz)$', rel): continue
        d = open(fn, 'rb').read()
        for n, off in enumerate(gims(d)):
            try:
                im = gimpng.decode(d[off:])[0]
            except Exception as e:
                print('fail', rel, n, e); continue
            name = rel.replace('/', '_') + f'__{n}.png'
            im.save(os.path.join(OUT, name))
            items.append((name, im))
    print(len(items), 'textures')
    # contact sheets
    sd = os.path.join(ROOT, 'work/tex_sheets'); os.makedirs(sd, exist_ok=True)
    W = 1600; x = y = 0; rowh = 0; sheet = None; k = 0
    def flush():
        nonlocal sheet, k
        if sheet: sheet.save(os.path.join(sd, f'{k:02d}.png')); k += 1
    sheet = Image.new('RGB', (W, 1600), (60, 60, 60)); dr = ImageDraw.Draw(sheet)
    for name, im in items:
        t = im.copy(); t.thumbnail((380, 380))
        if x + t.width > W: x = 0; y += rowh + 14; rowh = 0
        if y + t.height + 14 > 1600:
            flush(); sheet = Image.new('RGB', (W, 1600), (60, 60, 60)); dr = ImageDraw.Draw(sheet); x = y = rowh = 0
        bg = Image.new('RGB', t.size, (60, 60, 60)); bg.paste(t, mask=t.split()[3])
        sheet.paste(bg, (x, y + 12)); dr.text((x, y), name[:60], fill=(255, 255, 0))
        x += max(t.width, 120) + 6; rowh = max(rowh, t.height)
    flush()
    print(k, 'sheets')


main()
