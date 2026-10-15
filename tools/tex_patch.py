"""Redraw Japanese wording inside GIM textures (.giz / GIMs embedded in .gmz).

Spec files: translation/tex/*.json  ->  {"<cfi path>#<gim index>": [op, ...], ...}
ops (coordinates in texture pixels):
  {"op": "erase", "rect": [x, y, w, h], "mode": "clear" | "bg" | [r, g, b, a]}
      clear = transparent, bg = fill with the median colour of the rect border
  {"op": "copy", "src": [x, y, w, h], "dst": [x, y]}
  {"op": "text", "rect": [x, y, w, h], "text": "...", "size": 12,
   "font": "rg" | "bd" | "eb" | "hv" | "lt" | "serif" | "serif_b",
   "color": [r, g, b, a], "outline": [r, g, b, a] | null, "ow": 1,
   "shadow": [r, g, b, a] | null, "align": "l" | "c" | "r", "spacing": 0,
   "vertical": false}
      text is shrunk horizontally (never vertically below 75%) to fit the rect.
usage: python tools/tex_patch.py preview <spec.json>   -> work/tex_preview/*.png
"""
import sys, os, json, glob, struct
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import gimpng, gim_tool as G

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FONTS = {
    'lt': 'NanumSquareNeo-aLt.ttf', 'rg': 'NanumSquareNeo-bRg.ttf', 'bd': 'NanumSquareNeo-cBd.ttf',
    'eb': 'NanumSquareNeo-dEb.ttf', 'hv': 'NanumSquareNeo-eHv.ttf',
    'serif': 'SeoulHangangM.ttf', 'serif_b': 'SeoulHangangEB.ttf', 'serif_l': 'SeoulHangangL.ttf',
}


def gim_offsets(d):
    out = []; i = d.find(G.MAGIC)
    while i >= 0:
        out.append(i); i = d.find(G.MAGIC, i + 1)
    return out


def border_median(im, x, y, w, h):
    px = []
    for xx in range(x, x + w):
        for yy in (y, y + h - 1):
            if 0 <= xx < im.width and 0 <= yy < im.height: px.append(im.getpixel((xx, yy)))
    for yy in range(y, y + h):
        for xx in (x, x + w - 1):
            if 0 <= xx < im.width and 0 <= yy < im.height: px.append(im.getpixel((xx, yy)))
    if not px: return (0, 0, 0, 0)
    return tuple(sorted(c[i] for c in px)[len(px) // 2] for i in range(4))


def render_text(op):
    """returns an RGBA image of the text, sized to the rect"""
    x, y, w, h = op['rect']
    size = op.get('size', max(8, h - 2))
    font = ImageFont.truetype(os.path.join(ROOT, FONTS[op.get('font', 'bd')]), size * 4)
    text = op['text'].replace('・', '·'); sp = op.get('spacing', 0) * 4
    ow = op.get('ow', 1) * 4 if op.get('outline') else 0
    sh = 4 if op.get('shadow') else 0
    lines = text.split('\n')
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * op.get('lh', 1.0))
    # measure
    def line_w(t):
        return sum(font.getlength(c) for c in t) + sp * max(0, len(t) - 1)
    tw = int(max(line_w(l) for l in lines)) + 2 * ow + sh + 8
    th = lh * len(lines) + 2 * ow + sh + 8
    big = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    def draw_layer(color, dx, dy, stroke):
        layer = Image.new('RGBA', (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        for li, l in enumerate(lines):
            lw = line_w(l)
            cx = {'l': 0, 'c': (tw - 2 * ow - sh - 8 - lw) / 2, 'r': tw - 2 * ow - sh - 8 - lw}[op.get('align', 'c')]
            cx += ow + 4 + dx
            for c in l:
                d.text((cx, ow + 4 + dy + li * lh), c, font=font, fill=tuple(color),
                       stroke_width=stroke, stroke_fill=tuple(color))
                cx += font.getlength(c) + sp
        return layer
    if op.get('shadow'): big.alpha_composite(draw_layer(op['shadow'], sh, sh, ow))
    if op.get('outline'): big.alpha_composite(draw_layer(op['outline'], 0, 0, ow))
    if op.get('gradient'):
        mask = draw_layer((255, 255, 255, 255), 0, 0, 0).split()[3]
        (r0, g0, b0, a0), (r1, g1, b1, a1) = op['gradient']
        ys = [y for y in range(th) if any(mask.getpixel((x, y)) for x in range(0, tw, 2))] or [0, th - 1]
        top, bot = ys[0], max(ys[-1], ys[0] + 1)
        grad = Image.new('RGBA', (tw, th))
        for y in range(th):
            t = min(1, max(0, (y - top) / (bot - top)))
            grad.paste((round(r0 + (r1 - r0) * t), round(g0 + (g1 - g0) * t), round(b0 + (b1 - b0) * t), 255), (0, y, tw, y + 1))
        grad.putalpha(mask)
        big.alpha_composite(grad)
    else:
        big.alpha_composite(draw_layer(op.get('color', (255, 255, 255, 255)), 0, 0, 0))
    bb = big.getbbox() or (0, 0, 1, 1)
    big = big.crop(bb)
    # scale to target: font size given in px means cap height ~ size; fit rect
    sc = 1 / 4
    nw, nh = max(1, round(big.width * sc)), max(1, round(big.height * sc))
    if nw > w: nw = w
    if nh > h: nh = h
    if op.get('fit', True) and nh > h: nh = h
    out = big.resize((nw, nh), Image.LANCZOS)
    return out


def apply_ops(im, ops):
    im = im.copy()
    for op in ops:
        if op['op'] == 'erase':
            x, y, w, h = op['rect']; mode = op.get('mode', 'clear')
            col = (0, 0, 0, 0) if mode == 'clear' else border_median(im, x, y, w, h) if mode == 'bg' else tuple(mode)
            ImageDraw.Draw(im).rectangle([x, y, x + w - 1, y + h - 1], fill=col)
        elif op['op'] == 'heal':
            # close holes in a soft glow: dilate + blur the alpha inside rect, colour = op colour
            x, y, w, h = op['rect']; r = op.get('radius', 3)
            reg = im.crop((x - 8, y - 8, x + w + 8, y + h + 8))
            a = reg.split()[3].filter(ImageFilter.MaxFilter(2 * r + 1)).filter(ImageFilter.GaussianBlur(r))
            col = Image.new('RGBA', reg.size, tuple(op.get('color', (255, 255, 255, 255))))
            col.putalpha(a)
            inner = col.crop((8, 8, 8 + w, 8 + h))
            orig = im.crop((x, y, x + w, y + h))
            from PIL import ImageChops
            inner.putalpha(ImageChops.lighter(orig.split()[3], inner.split()[3].point(lambda v: v * 0.92)))
            im.paste(inner, (x, y))
        elif op['op'] == 'copy':
            x, y, w, h = op['src']; dx, dy = op['dst']
            im.paste(im.crop((x, y, x + w, y + h)), (dx, dy))
        elif op['op'] == 'text':
            x, y, w, h = op['rect']
            rot = op.get('rotate', 0)
            if rot in (90, -90, 270):
                t = render_text(dict(op, rect=[0, 0, h, w])).rotate(rot, expand=True)
            else:
                t = render_text(op)
            al = op.get('align', 'c')
            px = x if al == 'l' else x + w - t.width if al == 'r' else x + (w - t.width) // 2
            py = y + (h - t.height) // 2 + op.get('dy', 0)
            layer = Image.new('RGBA', im.size, (0, 0, 0, 0)); layer.paste(t, (px, py))
            im.alpha_composite(layer)
    return im


# textures whose palette order matters to the game (title logo fades/shines through it):
# keep the original palette and map pixels to its nearest colours
KEEP_PALETTE = {'title/ti.gmz', 'title/ti2.gmz'}


def encode_into(blob, im, keep_palette=False):
    """quantise RGBA image back into the GIM (same format, same sizes)"""
    image = G.find_chunk(blob, G.IMAGE); h = image.start + 16
    _, _, fmt, order, w, hh, bpp, pa, ha = struct.unpack_from('<HHHHHHHHH', blob, h)
    pitch = (w * bpp // 8 + pa - 1) // pa * pa; rows = (hh + ha - 1) // ha * ha
    po = image.start + image.data_offset + struct.unpack_from('<I', blob, h + 0x1C)[0]
    pc = G.find_chunk(blob, G.PALETTE); ph = pc.start + 16
    pofs = pc.start + pc.data_offset + struct.unpack_from('<I', blob, ph + 0x1C)[0]
    ncol = 256 if fmt == 5 else 16
    assert struct.unpack_from('<H', blob, ph + 4)[0] == 3
    if keep_palette:
        import numpy as np
        pal = list(blob[pofs:pofs + ncol * 4])
        P = np.array(pal, dtype=np.int32).reshape(ncol, 4)
        A = np.array(im.convert('RGBA'), dtype=np.int32).reshape(-1, 4)
        # weight alpha strongly so transparency is kept exact
        wgt = np.array([1, 1, 1, 3])
        best = np.empty(len(A), dtype=np.uint8)
        for s0 in range(0, len(A), 65536):
            chunk = A[s0:s0 + 65536]
            dist = (((chunk[:, None, :] - P[None, :, :]) ** 2) * wgt).sum(axis=2)
            best[s0:s0 + 65536] = dist.argmin(axis=1)
        idx = best.tobytes()
    else:
        q = im.quantize(colors=ncol, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        pal = q.getpalette('RGBA')[:ncol * 4]
        pal += [0] * (ncol * 4 - len(pal))
        idx = q.tobytes()
    raw = bytearray(pitch * rows)
    for yy in range(hh):
        if fmt == 5:
            raw[yy * pitch: yy * pitch + w] = idx[yy * w:(yy + 1) * w]
        else:
            row = idx[yy * w:(yy + 1) * w]
            for xx in range(0, w, 2):
                lo = row[xx]; hi = row[xx + 1] if xx + 1 < w else 0
                raw[yy * pitch + xx // 2] = lo | hi << 4
    if order: raw = G.swizzle(raw, pitch, rows)
    out = bytearray(blob)
    out[po:po + len(raw)] = raw
    out[pofs:pofs + ncol * 4] = bytes(pal)
    return bytes(out)


def load_specs():
    spec = {}
    for fn in sorted(glob.glob(os.path.join(ROOT, 'translation/tex/*.json'))):
        for k, v in json.load(open(fn, encoding='utf-8')).items():
            spec.setdefault(k, []).extend(v)
    return spec


def patched_files(get_file, preview_dir=None, spec=None):
    """get_file(cfi_path) -> uncompressed bytes.  returns {cfi_path: new bytes}"""
    spec = spec if spec is not None else load_specs()
    by_file = {}
    for key, ops in spec.items():
        path, n = key.rsplit('#', 1); by_file.setdefault(path, []).append((int(n), ops))
    out = {}
    for path, items in by_file.items():
        d = bytearray(get_file(path)); offs = gim_offsets(bytes(d))
        for n, ops in items:
            o = offs[n]
            blob = bytes(d[o:])
            im = gimpng.decode(blob)[0]
            new = apply_ops(im, ops)
            if preview_dir:
                new.save(os.path.join(preview_dir, path.replace('/', '_') + f'__{n}.png'))
            enc = encode_into(blob, new, path in KEEP_PALETTE)
            d[o:o + len(enc)] = enc[:len(d) - o] if len(enc) > len(d) - o else enc
        out[path] = bytes(d)
    return out


if __name__ == '__main__':
    if sys.argv[1] == 'preview':
        pd = os.path.join(ROOT, 'work/tex_preview'); os.makedirs(pd, exist_ok=True)
        only = json.load(open(sys.argv[2], encoding='utf-8')) if len(sys.argv) > 2 else None
        res = patched_files(lambda p: open(os.path.join(ROOT, 'work/cfi', p), 'rb').read(), pd, only)
        print('patched', len(res), 'files ->', pd)
