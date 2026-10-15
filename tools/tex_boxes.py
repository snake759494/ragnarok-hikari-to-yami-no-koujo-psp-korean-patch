"""Find text-like blobs in a decoded texture and draw numbered boxes.
usage: python tools/tex_boxes.py <png> [gap=3] [crop x,y,w,h] [scale]
  prints  n: x y w h  (texture pixels) and writes <png>.boxes.png (zoomed, on dark bg)
Blobs = 8-connected opaque pixels (alpha > 40) merged when closer than `gap` px
horizontally and overlapping vertically, so a word/line becomes one box."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from collections import deque


def blobs(a, thr=40):
    h, w = a.shape; seen = np.zeros_like(a, bool); out = []
    m = a > thr
    for y in range(h):
        for x in range(w):
            if m[y, x] and not seen[y, x]:
                q = deque([(y, x)]); seen[y, x] = True
                x0 = x1 = x; y0 = y1 = y
                while q:
                    cy, cx = q.popleft()
                    x0 = min(x0, cx); x1 = max(x1, cx); y0 = min(y0, cy); y1 = max(y1, cy)
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True; q.append((ny, nx))
                out.append([x0, y0, x1, y1])
    return out


def merge(bs, gap):
    changed = True
    while changed:
        changed = False; res = []
        for b in bs:
            for r in res:
                vo = min(b[3], r[3]) - max(b[1], r[1])
                hgap = max(b[0], r[0]) - min(b[2], r[2])
                if vo >= -1 and hgap <= gap:
                    r[0] = min(r[0], b[0]); r[1] = min(r[1], b[1]); r[2] = max(r[2], b[2]); r[3] = max(r[3], b[3])
                    changed = True; break
            else:
                res.append(list(b))
        bs = res
    return sorted(bs, key=lambda b: (b[1] // 8, b[0]))


if __name__ == '__main__':
    p = sys.argv[1]; gap = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    im = Image.open(p).convert('RGBA')
    ox = oy = 0
    if len(sys.argv) > 3 and sys.argv[3] != '-':
        x, y, w, h = map(int, sys.argv[3].split(',')); im = im.crop((x, y, x + w, y + h)); ox, oy = x, y
    sc = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    a = np.array(im)[:, :, 3]
    bs = merge(blobs(a), gap)
    bs = [b for b in bs if (b[2] - b[0]) >= 2 or (b[3] - b[1]) >= 2]
    bg = Image.new('RGBA', im.size, (30, 30, 70, 255)); bg.alpha_composite(im)
    z = bg.resize((im.width * sc, im.height * sc), Image.NEAREST); d = ImageDraw.Draw(z)
    for i, b in enumerate(bs):
        d.rectangle([b[0] * sc, b[1] * sc, (b[2] + 1) * sc - 1, (b[3] + 1) * sc - 1], outline=(255, 0, 255, 255))
        d.text((b[0] * sc + 1, b[1] * sc - 10 if b[1] * sc >= 10 else b[3] * sc + 2), str(i), fill=(0, 255, 0, 255))
        print(f'{i}: {b[0] + ox} {b[1] + oy} {b[2] - b[0] + 1} {b[3] - b[1] + 1}')
    z.save(p + '.boxes.png')
