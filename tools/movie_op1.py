"""Replace the burned-in Japanese narration of op1.pmf with Korean.
The Japanese caption is left untouched; the Korean line is drawn just above it
(NanumSquareNeo Bold, white with a black outline, no background box).  The new H.264
stream is put back into the original PMF slots (op_mux), so the file size is unchanged.
usage: python tools/movie_op1.py  -> work/movie/op1.pmf"""
import os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
import op_mux
from build_movies import decode, encode, seconds, FPS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'work/iso/PSP_GAME/USRDIR/movie/op1.pmf')
OUT = os.path.join(ROOT, 'work/movie/op1.pmf')
FONT = os.path.join(ROOT, 'NanumSquareNeo-cBd.ttf')

CUES = [
    (3.37, 5.27, '옛날, 성전이라 불리는 거대한 전쟁이 있었다'),
    (7.77, 10.44, '신계와 마계의 침략으로부터 인간계를 지켜 낸 그 전쟁은'),
    (12.11, 13.48, '각 세계를 가르는 『마벽』이 세워지면서'),
    (14.05, 18.49, '일단 막을 내리게 된다'),
    (19.99, 22.46, '이렇게 인간계에 평화가 찾아왔다'),
    (22.72, 25.99, '――그렇게 보였지만, 이계의 위협이 사라진 세상에서는'),
    (26.23, 29.70, '인간끼리 다투는 역사가 이어지고 있었다'),
    (30.93, 34.30, '그리고 성전이 끝난 지 수백 년'),
    (36.40, 38.81, '이곳 그란츠리터 반도에서는'),
    (38.87, 42.88, '베르나르 3세가 이끄는 블랑샤르드 황국과'),
    (43.04, 46.45, '질드 평의장이 이끄는 연합국가 아우라가 패권을 다투고 있었다'),
    (47.51, 49.62, '그 다툼이 5년 전부터 휴전 상태인 것은'),
    (49.82, 52.85, '지쳐 버린 두 나라가 전선을 유지할 수 없게 되었을 뿐이다'),
    (54.79, 57.56, '여전히 전쟁의 불씨는 꺼지지 않고 있었다……'),
    (59.43, 60.15, '그리고 사람들은'),
    (60.26, 62.80, '머지않아 찾아올 전란의 날들을 떠올리며'),
    (62.90, 65.43, '잠시뿐인 평화로운 나날을 보내고 있었다'),
]
Y0, Y1 = 228, 268          # caption band (frame is 480x272)


def caption(text):
    size = 16
    while True:
        f = ImageFont.truetype(FONT, size)
        w = f.getlength(text) + 4
        if w <= 468 or size <= 11: break
        size -= 1
    im = Image.new('RGBA', (480, 272), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    x = (480 - w) / 2; y = Y0 - size - 8
    d.text((x, y), text, font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    a = np.array(im).astype(np.float32) / 255
    return a[..., 3:4], a[..., :3][..., ::-1] * 255   # alpha, BGR


def text_mask(f):
    g = f[Y0:Y1].min(axis=2)
    return g > 190


def main():
    pmf = open(SRC, 'rb').read()
    es = op_mux.video_es(pmf)
    keyint, _ = op_mux.gop(es)
    tmp = tempfile.mkdtemp(prefix='rgnmov_')
    fr = decode(es, tmp)
    n = len(fr)
    caps = [(int(a * FPS), int(b * FPS) + 1, caption(t)) for a, b, t in CUES]
    for s, e, (a, rgb) in caps:
        for i in range(max(0, s), min(n, e)):
            f = fr[i].astype(np.float32)
            fr[i] = (f * (1 - a) + rgb * a).astype(np.uint8)
    kbps = max(200, int(len(es) * 0.97 * 8 / seconds(pmf) / 1000))
    for attempt in range(12):
        out = os.path.join(tmp, 'out.264')
        encode(fr, out, tmp, keyint, kbps)
        try:
            blob = op_mux.build(pmf, open(out, 'rb').read())[0]; break
        except ValueError as ex:
            if 'lower the bitrate' not in str(ex): raise
            kbps = int(kbps * 0.92)
    else:
        raise SystemExit('does not fit')
    assert len(blob) == len(pmf)
    open(OUT, 'wb').write(blob)
    for k, (s, e, _) in enumerate(caps[:3] + caps[10:11]):
        cv2.imencode('.png', fr[(s + e) // 2])[1].tofile(os.path.join(ROOT, f'work/movie/check_{k}.png'))
    shutil.rmtree(tmp, ignore_errors=True)
    print('op1', kbps, 'kbps')


main()
