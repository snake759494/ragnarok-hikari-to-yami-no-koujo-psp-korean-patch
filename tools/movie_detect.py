"""Detect burned-in subtitle intervals (white text in the bottom band) of a PMF.
usage: python tools/movie_detect.py op1 [op2 ...] -> work/movie/<name>_cues.json + sample frames"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, cv2
import op_mux
from build_movies import decode, FPS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'work/iso/PSP_GAME/USRDIR/movie')
OUT = os.path.join(ROOT, 'work/movie')


def band_signature(f, y0=228, y1=268):
    g = f[y0:y1, :, :].astype(np.int16)
    white = (g.min(axis=2) > 200)
    return white


def detect(name):
    pmf = open(os.path.join(SRC, name + '.pmf'), 'rb').read()
    es = op_mux.video_es(pmf)
    tmp = tempfile.mkdtemp()
    fr = decode(es, tmp)
    n = len(fr)
    on = []; sig = []
    for f in fr:
        w = band_signature(f)
        on.append(w.sum() > 120); sig.append(w)
    cues = []; i = 0
    while i < n:
        if on[i]:
            j = i
            while j + 1 < n and on[j + 1] and (np.logical_xor(sig[j + 1], sig[i]).sum() < max(250, sig[i].sum() * 0.5)):
                j += 1
            if j - i >= 10:
                xs = np.where(sig[(i + j) // 2].any(axis=0))[0]
                ys = np.where(sig[(i + j) // 2].any(axis=1))[0]
                cues.append({'start': round(i / FPS, 3), 'end': round((j + 1) / FPS, 3), 'f0': i, 'f1': j,
                             'x0': int(xs.min()), 'x1': int(xs.max()), 'y0': int(ys.min()) + 228, 'y1': int(ys.max()) + 228})
            i = j + 1
        else:
            i += 1
    os.makedirs(OUT, exist_ok=True)
    for k, c in enumerate(cues):
        cv2.imencode('.png', fr[(c['f0'] + c['f1']) // 2][200:272])[1].tofile(os.path.join(OUT, f'{name}_{k:02d}.png'))
    json.dump(cues, open(os.path.join(OUT, name + '_cues.json'), 'w'), indent=0)
    print(name, n, 'frames', len(cues), 'cues', round(n / FPS, 1), 's')


if __name__ == '__main__':
    for nm in sys.argv[1:]: detect(nm)
