# -*- coding: utf-8 -*-
"""Put a new H.264 stream into a .pmf without disturbing the container.

The film is a program stream of 2048-byte packs, one PES packet each. All of
it -- pack headers and their SCR, the video PES headers and every PTS in them,
the ATRAC3+ packs, the system headers, the padding, the file length -- is kept
byte for byte. Only the coded pixels change.

Getting that right on a real PSP means more than a valid stream. The Media
Engine checks the mux buffer model: a frame's SCR (when the pack arrives) and
its PTS (when it is shown) have to keep the spacing the disc shipped with, or
its fixed video buffer overruns and the hardware faults. PPSSPP grows its
buffers to fit and never notices, which is what makes this easy to get wrong.

So each re-encoded frame is byte-ALIGNED to the offset its counterpart had in
the original elementary stream, and the gaps are filled with zero bytes --
leading_zero_8bits ahead of the next start code, which Annex-B allows anywhere
and every decoder skips. Filler NALs would do the same job on paper but the ME
rejects them. The aligned stream is exactly the original's length, so it drops
straight into the original payload slots and every PES header still describes
what follows it.

Approach and the buffer-model reasoning follow snake7594/vc2-korean-patch,
which worked this out on real hardware for Valkyria Chronicles 2.
"""
import struct

import numpy as np


def slots(pmf):
    """Every video PES packet, as (payload offset, payload length)."""
    off = struct.unpack('>I', pmf[8:12])[0]
    out, p = [], off
    while p + 4 <= len(pmf):
        if pmf[p:p + 3] != b'\x00\x00\x01':
            p += 1
            continue
        sid = pmf[p + 3]
        if sid == 0xBA:
            p += 14 + (pmf[p + 13] & 7)
            continue
        if sid == 0xB9:
            break
        n = struct.unpack('>H', pmf[p + 4:p + 6])[0]
        if sid == 0xE0:
            head = 3 + pmf[p + 8]           # flags, flags, header_data_length
            out.append((p + 6 + head, n - head))
        p += 6 + n
    return out


def bodies(pmf):
    """Every video PES packet as (body offset, PES_packet_length).

    `slots` gives where the payload starts; this gives where the PES header
    starts and how long the whole packet body is, which is what has to be
    rewritten when a packet is given a different timestamp.
    """
    off = struct.unpack('>I', pmf[8:12])[0]
    out, p = [], off
    while p + 4 <= len(pmf):
        if pmf[p:p + 3] != b'\x00\x00\x01':
            p += 1
            continue
        sid = pmf[p + 3]
        if sid == 0xBA:
            p += 14 + (pmf[p + 13] & 7)
            continue
        if sid == 0xB9:
            break
        n = struct.unpack('>H', pmf[p + 4:p + 6])[0]
        if sid == 0xE0:
            out.append((p + 6, n))
        p += 6 + n
    return out


def video_es(pmf):
    return b''.join(pmf[o:o + n] for o, n in slots(pmf))


def frames(es):
    """Offset of each access unit delimiter -- one per frame."""
    out, i = [], 0
    while True:
        i = es.find(b'\x00\x00\x01', i)
        if i < 0:
            break
        if es[i + 3] & 0x1F == 9:
            out.append(i)
        i += 3
    return out


def align(orig_es, new_es, early=0, slack=0):
    """`new_es` scheduled so each frame arrives when the original's did.

    Not nailed to the original offset -- placed in a window around it. A frame
    may run up to `early` bytes ahead, and must not fall behind at all:

      * behind is starvation, up to a point. The header holds the first frame
        back a second after the stream starts, so the decoder is a second's
        worth of data ahead of itself before it draws anything; `slack` is how
        much of that margin a frame may eat into. Past it the frame is not all
        there when it is due and the picture stops. This is what a straight
        alignment could not prevent -- a re-encode that spends more than the
        original did on one stretch pushes everything after it later, and the
        debt only grows.
      * too far ahead is the opposite failure: the Media Engine's video buffer
        is a fixed size and overruns.

    Running early on the cheap stretches is what pays for the expensive ones,
    so within the window each frame is placed as early as it is allowed.
    Returns the bytes and how far behind the worst frame ended up.
    """
    o, a = frames(orig_es), frames(new_es)
    if not o or len(a) != len(o):
        raise ValueError('frame count %d does not match the original %d'
                         % (len(a), len(o)))
    ends = a[1:] + [len(new_es)]
    size = [ends[k] - a[k] for k in range(len(a))]
    left, need = 0, [0] * (len(a) + 1)
    for k in range(len(a) - 1, -1, -1):
        left += size[k]
        need[k] = left
    budget = len(orig_es)
    if need[0] > budget:
        raise ValueError('stream is %d bytes, the slots hold %d; lower the '
                         'bitrate' % (need[0], budget))
    # The slack is spread a few bytes at a time between every frame rather than
    # banked into whatever gap the original's larger frames happen to leave.
    # Pushing each frame back onto its original offset piled the difference up:
    # where the disc spent fifteen kilobytes on a key frame and x264 spends
    # three, twelve kilobytes of zeros go in between, and the lower the bitrate
    # the worse it gets. The disc's own streams never carry more than three
    # zeros in a row, and the Media Engine evidently expects that.
    room = budget - need[0]
    per, extra = divmod(room, len(a) + 1)
    out, p, late, worst, over = bytearray(), 0, 0, 0, per
    for k in range(len(a)):
        pad = per + (1 if k < extra else 0)
        out += b'\x00' * pad
        p += pad
        if p > o[k]:
            late += 1
            worst = max(worst, p - o[k])
        out += new_es[a[k]:ends[k]]
        p += size[k]
    return bytes(out) + b'\x00' * (budget - len(out)), late, worst, over


BASE, STEP = 90000, 3003          # first PTS, and 29.97 fps in 90 kHz ticks
GAP = 14                          # frames between anchors, as the original


def _ts(v, marker):
    return bytes([marker | ((v >> 29) & 0x0E) | 1,
                  (v >> 22) & 0xFF, ((v >> 14) & 0xFE) | 1,
                  (v >> 7) & 0xFF, ((v << 1) & 0xFE) | 1])


def build(pmf, new_es, early=0, slack=0):
    """The .pmf with `new_es` as its video: same length, same everything else.

    The timestamps are written fresh rather than inherited. A PTS in a PES
    header applies to whichever access unit begins inside that packet, so
    keeping the original headers only works if every frame lands exactly where
    its counterpart lay -- and it cannot: x264 needs more bytes than the disc's
    encoder did on the cheap frames no matter how far the bitrate is dropped,
    so the frames shift and the inherited anchors come to name the wrong
    pictures. That is what stopped the film a few seconds in. Each packet is
    now stamped for the frame that actually starts in it, at the cadence the
    original used, and everything else in the container is still untouched.
    """
    body = new_es
    au = {f: i for i, f in enumerate(frames(body))}
    starts = sorted(au)
    pack = bodies(pmf)
    room = sum(n - 3 for _, n in pack)
    if len(body) > room:
        raise ValueError('stream is %d bytes, the slots hold %d; lower the '
                         'bitrate' % (len(body), room))

    # Spare room becomes padding-stream packets, spread evenly through the film
    # -- the same 0xBE packets the disc itself uses for the purpose. Filling the
    # slack with zeroes inside the video instead left runs of them thousands of
    # bytes long, where the disc never has more than three together, and the
    # decoder gave up part way through the film.
    want = min(len(pack), -(-len(body) * len(pack) // room) + 2)
    out = bytearray(pmf)
    pos, k, last, acc = 0, 0, -GAP, 0
    for off, n in pack:
        acc += want
        use = acc >= len(pack)
        if use:
            acc -= len(pack)
        if not use or pos >= len(body):
            out[off - 3] = 0xBE                       # padding stream
            out[off:off + n] = b'\xff' * n
            continue
        head, take = b'\x81\x00\x00', n - 3
        while k < len(starts) and starts[k] < pos:
            k += 1
        if k < len(starts) and starts[k] < pos + n - 13:
            fr = au[starts[k]]
            if fr - last >= GAP or fr == 0:
                head = (b'\x81\xc0\x0a' + _ts(BASE + fr * STEP, 0x30)
                        + _ts(BASE + (fr - 1) * STEP, 0x10))
                take, last = n - 13, fr
        chunk = body[pos:pos + take]
        pos += len(chunk)
        out[off:off + n] = head + chunk + b'\xff' * (take - len(chunk))
    assert len(out) == len(pmf)
    if pos < len(body):
        raise ValueError('only %d of %d bytes placed; lower the bitrate'
                         % (pos, len(body)))
    return bytes(out), 0, 0, 0


def padding(pmf):
    """Total zero bytes in the video stream, and the longest unbroken run.

    The disc's own streams never carry more than three zeros together. A long
    run is padding, and the Media Engine will not chew through it -- which is
    what stops a film that otherwise checks out.
    """
    es = np.frombuffer(video_es(pmf), np.uint8)
    z = (es == 0).view(np.int8)
    edge = np.flatnonzero(np.diff(np.concatenate(([0], z, [0]))))
    run = int((edge[1::2] - edge[0::2]).max()) if len(edge) else 0
    return int(z.sum()), run, len(es)


def capacity(pmf):
    return sum(n for _, n in slots(pmf))


def gop(es):
    """Frames between IDRs, as the original was encoded."""
    f, idr, i, cur = frames(es), [], 0, -1
    at = {v: k for k, v in enumerate(f)}
    while True:
        i = es.find(b'\x00\x00\x01', i)
        if i < 0:
            break
        if es[i + 3] & 0x1F == 5:
            prev = max(x for x in f if x <= i)
            if at[prev] != cur:
                cur = at[prev]
                idr.append(cur)
        i += 3
    return (idr[1] - idr[0]) if len(idr) > 1 else len(f), len(idr)

def stamped(pmf):
    """(payload length, PTS) for every video PES packet, PTS None if absent."""
    def ts(b):
        return ((((b[0] >> 1) & 7) << 30) | (b[1] << 22) |
                ((b[2] >> 1) << 15) | (b[3] << 7) | (b[4] >> 1))
    off = struct.unpack('>I', pmf[8:12])[0]
    p, out = off, []
    while p + 4 <= len(pmf):
        if pmf[p:p + 3] != b'\x00\x00\x01':
            p += 1
            continue
        sid = pmf[p + 3]
        if sid == 0xBA:
            p += 14 + (pmf[p + 13] & 7)
            continue
        if sid == 0xB9:
            break
        n = struct.unpack('>H', pmf[p + 4:p + 6])[0]
        b = pmf[p + 6:p + 6 + n]
        if sid == 0xE0:
            hl = 3 + b[2]
            out.append((n - hl, ts(b[3:8]) if b[1] & 0x80 else None))
        p += 6 + n
    return out


def mislabelled(pmf, base=90000, step=3003):
    """PTS anchors that do not name the frame beginning in their own packet.

    The original PES headers are kept as they are, so a frame has to sit where
    its counterpart sat: the timestamp in a packet applies to whichever access
    unit starts inside it. Move the frames about and the anchors come to label
    the wrong pictures, which is what stalls the decoder seconds in.
    """
    es = video_es(pmf)
    order = {f: i for i, f in enumerate(frames(es))}
    bad, pos = 0, 0
    for n, pts in stamped(pmf):
        if pts is not None:
            want = (pts - base) // step
            here = [order[f] for f in order if pos <= f < pos + n]
            if not here or min(here) != want:
                bad += 1
        pos += n
    return bad
