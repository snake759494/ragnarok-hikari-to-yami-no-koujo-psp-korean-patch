import struct,sys
def parse(d):
    """index: u8 ndirs?, then per dir: len name('/') u8 count, then count*(len name u32 off u32 size)"""
    p=1; out=[]
    for _ in range(d[0]):
        n=d[p]; cur=d[p+1:p+1+n].decode(); cnt=d[p+1+n]; p+=2+n
        if cnt==0xfc: cnt=d[p]|d[p+1]<<8; p+=2
        for _ in range(cnt):
            n=d[p]; name=d[p+1:p+1+n].decode(); off,size=struct.unpack_from('<II',d,p+1+n); p+=1+n+8
            out.append((cur+name,off,size,p-8))
    return out,p
if __name__=='__main__':
    d=open(sys.argv[1],'rb').read()
    ents,p=parse(d); print('hdr end',hex(p),len(ents),d[0])
    for e in ents: print(e[0],hex(e[1]),e[2])

import zlib,gzip
def load(path):
    d=open(path,'rb').read(); e,p=parse(d); return d,e,p
def raw(d,p,ent): return d[p+ent[1]:p+ent[1]+ent[2]]
def unz(b):
    if b[4:6]==b'\x1f\x8b':
        u=gzip.decompress(b[4:]); assert len(u)==int.from_bytes(b[:4],'little'); return u
    return b


def gz(u):
    """4-byte LE uncompressed size + gzip stream (as in the original archive)"""
    c = zlib.compressobj(9, zlib.DEFLATED, 31)
    return len(u).to_bytes(4, 'little') + c.compress(u) + c.flush()


def rebuild(d, ents, p, repl):
    """repl: {name: uncompressed bytes}; files keep their order, 0x800 alignment"""
    hdr = bytearray(d[:p])
    body = bytearray()
    for name, off, size, rec in ents:
        b = raw(d, p, (name, off, size))
        if name in repl:
            b = gz(repl[name]) if b[4:6] == b'\x1f\x8b' else repl[name]
        body += b'\0' * ((-len(body)) % 0x800)
        struct.pack_into('<II', hdr, rec, len(body), len(b))
        body += b
    body += b'\0' * ((-len(body)) % 0x800)
    return bytes(hdr) + bytes(body)
