"""Burn Korean subtitles into the PMF movies (container kept byte for byte).

Cues: translation/movie_subs.json  {"LUNAR_SSS_01": [{"start": s, "end": s, "ko": "line1\\nline2"}, ...]}
Font: same as dialogue -- NanumSquareNeo Bold, 18px, white with a dark outline.
Re-encode: x264 Main@2.1, no B-frames, AUD + repeated headers, then op_mux.build
places the new stream into the original video PES slots (after Time Travelers).
usage: python build_movies.py [NAME ...]   -> work/movie_out/NAME.PMF
"""
import os, sys, json, gc, shutil, subprocess, tempfile
from pathlib import Path
import numpy as np, cv2, imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import op_mux

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'work/ext/PSP_GAME/USRDIR/LUNAR/DATA/PMF'
OUT = ROOT / 'work/movie_out'
SUBS = ROOT / 'translation/movie_subs.json'
FONT = ImageFont.truetype(str(ROOT / 'NanumSquareNeo-cBd.ttf'), 18)
RATE = '30000/1001'
FPS = 30000 / 1001
X264 = ('no-scenecut:bframes=0:cabac=1:ref=1:no-open-gop:repeat-headers=1:'
        'aud=1:weightp=0:pic-struct:nal-hrd=vbr')
FF = imageio_ffmpeg.get_ffmpeg_exe()


def seconds(pmf):
    a = int.from_bytes(pmf[0x54:0x5A], 'big') / 90000.0
    b = int.from_bytes(pmf[0x5A:0x60], 'big') / 90000.0
    return max(0.1, b - a)


def overlay(text, w=480, h=272):
    """RGBA 480x272 layer with the cue at the bottom centre."""
    lines = text.split('\n')
    lh = 22
    im = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(im)
    y0 = h - 8 - lh * len(lines)
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=FONT)
        d.text(((w - tw) / 2, y0 + i * lh), ln, font=FONT, fill=255)
    edge = im.filter(ImageFilter.MaxFilter(5))
    a = np.maximum(np.asarray(edge, np.float32) / 255 * 0.9, np.asarray(im, np.float32) / 255)
    col = np.asarray(im, np.float32) / 255          # 1 = white text, 0 = outline
    return a, col


def render(frames, cues):
    cache = {}
    for c in cues:
        a0, a1 = int(c['start'] * FPS), int(c['end'] * FPS) + 1
        if c['ko'] not in cache:
            cache[c['ko']] = overlay(c['ko'])
        a, col = cache[c['ko']]
        rgb = (col * 255)[..., None]
        for i in range(max(0, a0), min(len(frames), a1)):
            f = frames[i].astype(np.float32)
            frames[i] = (f * (1 - a[..., None]) + rgb * a[..., None]).astype(np.uint8)
    return frames


def decode(es, tmp):
    p = os.path.join(tmp, 'in.264')
    open(p, 'wb').write(es)
    cap = cv2.VideoCapture(p)
    fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    cap.release()
    return np.stack(fr)


def encode(frames, out, tmp, keyint, kbps):
    mr, buf = kbps, max(64, int(kbps * 0.35))
    opts = 'keyint=%d:%s:vbv-maxrate=%d:vbv-bufsize=%d' % (keyint, X264, mr, buf)
    log = os.path.join(tmp, 'x264')
    for p in (1, 2):
        cmd = [FF, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo',
               '-pix_fmt', 'bgr24', '-s', '480x272', '-r', RATE, '-i', '-', '-an',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'main', '-level', '2.1',
               '-b:v', '%dk' % kbps, '-maxrate', '%dk' % mr, '-bufsize', '%dk' % buf,
               '-x264opts', opts, '-pass', str(p), '-passlogfile', log, '-f', 'h264',
               os.devnull if p == 1 else out]
        q = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for f in frames:
            q.stdin.write(np.ascontiguousarray(f).tobytes())
        q.stdin.close()
        if q.wait():
            raise SystemExit('x264 failed')


def one(name, cues):
    pmf = (SRC / (name + '.PMF')).read_bytes()
    es = op_mux.video_es(pmf)
    keyint, _ = op_mux.gop(es)
    tmp = tempfile.mkdtemp(prefix='lunmov_')
    frames = decode(es, tmp)
    frames = render(frames, cues)
    kbps = max(200, int(len(es) * 0.97 * 8 / seconds(pmf) / 1000))
    for attempt in range(12):
        out = os.path.join(tmp, 'out.264')
        encode(frames, out, tmp, keyint, kbps)
        new = open(out, 'rb').read()
        try:
            blob = op_mux.build(pmf, new)[0]
            break
        except ValueError as e:
            if 'lower the bitrate' not in str(e):
                raise
            kbps = int(kbps * 0.92)
    else:
        raise SystemExit(name + ': does not fit')
    assert len(blob) == len(pmf)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (name + '.PMF')).write_bytes(blob)
    del frames
    gc.collect()
    shutil.rmtree(tmp, ignore_errors=True)
    print(name, len(cues), 'cues', kbps, 'kbps', flush=True)


if __name__ == '__main__':
    subs = json.loads(SUBS.read_text(encoding='utf-8'))
    names = sys.argv[1:] or sorted(k for k, v in subs.items() if v)
    for n in names:
        one(n, subs.get(n, []))
