"""Hashed string table at the end of compiled scripts (.rtz in script/).
layout: varint count, count*(u32 hash, varint len, bytes), sorted by hash,
last entry is hash 0xffffffff len 0, which ends the file."""
import struct


def vi(d, p):
    b = d[p]
    if b == 0xfc: return struct.unpack_from('<H', d, p + 1)[0], p + 3
    if b == 0xfd: return struct.unpack_from('<I', d, p + 1)[0], p + 5
    return b, p + 1


def wvi(n):
    if n < 0xfc: return bytes([n])
    if n < 0x10000: return b'\xfc' + struct.pack('<H', n)
    return b'\xfd' + struct.pack('<I', n)


def try_parse(d, p, end):
    try:
        n, q = vi(d, p)
        if n == 0: return None
        out = []; last = -1
        for i in range(n):
            h = struct.unpack_from('<I', d, q)[0]
            if h <= last: return None
            last = h; l, q = vi(d, q + 4)
            out.append((h, d[q:q + l])); q += l
            if q > end: return None
        return (q, out)
    except Exception:
        return None


def find_last(d):
    """earliest position after the symbol table whose hashed table runs exactly to EOF
    (some files end with the 0xffffffff/len 0 sentinel, some do not)"""
    end = len(d)
    r = try_parse(d, 0, end)
    if not r: return None
    for p in range(r[0], end - 5):
        t = try_parse(d, p, end)
        if t and t[0] == end and len(t[1]) > 1: return p, t[1]
    return None


def build(d, p, ents):
    out = bytearray(d[:p]) + wvi(len(ents))
    for h, s in ents: out += struct.pack('<I', h) + wvi(len(s)) + s
    return bytes(out)
